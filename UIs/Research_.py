import ast
import importlib.machinery
import json
import os
import re
import sys
from functools import partial

import maya.cmds as cmds
import NLTA_General


session = {"currentPaths": [],"currentFiles": [],"pinnedPaths": [],"pinnedFiles": []}
UI = {"view": "files"}

def CreateUI(data):
    global UI
    def BrowseFolder(*_):
        current = cmds.textField("researchFolder", q=True, text=True).strip()
        options = {"fileMode": 3, "dialogStyle": 2,"caption": "Choose research folder"}
        if os.path.isdir(current):
            options["startingDirectory"] = current
        selected = cmds.fileDialog2(**options)
        if selected:
            cmds.textField("researchFolder", e=True, text=selected[0])

    def PinCurrentFolder(*_):
        raw = cmds.textField("researchFolder", q=True, text=True).strip()
        path = os.path.normpath(raw) if raw else ""
        if not os.path.isdir(path):
            cmds.warning("Research: folder not found: {}".format(path))
            return
        if path not in session["pinnedPaths"]:
            session["pinnedPaths"].append(path)
        if UI.get("view") == "paths":
            LoadPaths()
        cmds.inViewMessage(amg="Pinned folder: <hl>{}</hl>".format(path),pos="midCenter", fade=True)

    def RefreshResults(*_):
        if UI.get("view") == "paths":
            LoadPaths()
        else:
            LoadFiles()

    def ClearFilter(*_):
        cmds.textField("researchSearchText", e=True, text="")
        RefreshResults()

    def ClearSettings(*_):
        for name in ("researchDataName", "researchFolder", "researchText","researchExts", "researchSearchText"):
            cmds.textField(name, e=True, text="")
        cmds.optionMenu("researchSearchMode", e=True, select=1)
        cmds.checkBox("researchMatchCase", e=True, value=False)
        session.clear()
        session.update({
            "currentPaths": [], "currentFiles": [],
            "pinnedPaths": [], "pinnedFiles": []
        })
        LoadFiles()

    def FilterOnEnter(*_):
        RefreshResults()
        cmds.evalDeferred(lambda: cmds.setFocus("researchSearchText"))

    titles, buttons, inputs = [], [], []
    titleFlags = data.get("titleFlags", {})
    buttonFlags = data.get("buttonFlags", {})
    inputFlags = data.get("inputFlags", {})

    module = data["module"]
    if cmds.layout(module, exists=True):
        cmds.deleteUI(module)

    root = cmds.rowColumnLayout(module, numberOfColumns=1, parent=data["parent"])
    if data.get("layoutFlags"):
        cmds.rowColumnLayout(root, e=True, **data["layoutFlags"])

    UI = {"root": root, "view": "files", "summary": None, "title": None}

    UI["title"] = cmds.textField(text="NLTA / RESEARCH", editable=False, height=28, parent=root)
    titles.append(UI["title"])
    cmds.separator(height=7, style="in", parent=root)

    titles.append(cmds.textField(text="SEARCH SETTINGS", editable=False, height=22, parent=root))
    cmds.textField("researchDataName", text="", manage=False, parent=root)

    settings = cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1, 86), (2, 265), (3, 107)],columnSpacing=[(1, 3), (2, 4)],parent=root)

    titles.append(cmds.textField(text="Folder", editable=False, parent=settings))
    inputs.append(cmds.textField("researchFolder", text=data.get("folder", ""), parent=settings))
    buttons.append(cmds.button(label="Browse", command=BrowseFolder, parent=settings))

    titles.append(cmds.textField(text="Find Text", editable=False, parent=settings))
    inputs.append(cmds.textField("researchText", text="", parent=settings,annotation="Text, Python module or MEL procedure"))
    buttons.append(cmds.button(label="Locate Module", command=LocateResearchModule,annotation="Find module path without a folder", parent=settings))

    titles.append(cmds.textField(text="Search By", editable=False, parent=settings))
    UI["search_mode"] = cmds.optionMenu("researchSearchMode", height=24,annotation="Search content, filenames or both", parent=settings)
    for label in ("Content", "File / Module Name", "Both"):
        cmds.menuItem(label=label, parent=UI["search_mode"])
    cmds.checkBox("researchMatchCase", label="Match Case", value=False,annotation="Case-sensitive search", parent=settings)

    titles.append(cmds.textField(text="Extensions", editable=False, parent=settings))
    inputs.append(cmds.textField("researchExts", text="", parent=settings,annotation="Examples: .py, .mel (blank = all files)"))
    cmds.text(label="", parent=settings)


    cmds.separator(height=5, style="none", parent=root)
    actions = cmds.rowColumnLayout(numberOfColumns=4,columnWidth=[(1, 115), (2, 115), (3, 115), (4, 115)],parent=root)
    buttons.append(cmds.button("SearchOK", label="Search", height=30,backgroundColor=(0.26, 0.44, 0.34), command=CheckItems,parent=actions))
    buttons.append(cmds.button("SearchSave", label="Save Preset", height=30,command=SaveResearchData, parent=actions))
    buttons.append(cmds.button("SearchClear", label="Pin Folder", height=30,command=PinCurrentFolder, parent=actions))
    buttons.append(cmds.button("SearchSettingsClear", label="Clear Settings", height=30,command=ClearSettings, parent=actions))

    tools = cmds.rowColumnLayout(numberOfColumns=4,columnWidth=[(1, 115), (2, 115), (3, 115), (4, 115)],parent=root)
    buttons.append(cmds.button("LoadAllPaths", label="All Paths", command=LoadAllPaths,parent=tools))
    buttons.append(cmds.button("LoadPinnedPaths", label="Pinned Paths", command=LoadPinnedPaths,parent=tools))
    buttons.append(cmds.button("LoadPinnedFiles", label="Pinned Files", command=LoadPinnedFiles,parent=tools))
    buttons.append(cmds.button("ResearchLiveUIInspector", label="Live UI Inspector",command=OpenLiveInspector, parent=tools))

    buttons.append(cmds.button("ResearchUIAutomation", label="UI Automation / Open Customer Window",height=28, command=OpenUIAutomation, parent=root))


    cmds.separator(height=8, style="in", parent=root)
    titles.append(cmds.textField(text="SAVED PRESETS", editable=False, height=22, parent=root))
    saved_scroll = cmds.scrollLayout("dataList", height=90, childResizable=True, parent=root)
    cmds.columnLayout("dataListContent", adjustableColumn=True,rowSpacing=2, parent=saved_scroll)


    cmds.separator(height=8, style="in", parent=root)
    titles.append(cmds.textField(text="SEARCH RESULTS", editable=False, height=22, parent=root))
    filter_row = cmds.rowColumnLayout(numberOfColumns=2, columnWidth=[(1, 360), (2, 100)], parent=root)
    inputs.append(cmds.textField("researchSearchText", text="",placeholderText="Filter results - Enter",enterCommand=FilterOnEnter, parent=filter_row))
    buttons.append(cmds.button(label="Clear Filter", command=ClearFilter, parent=filter_row))

    UI["summary"] = cmds.text(label="Ready", align="left", height=22, parent=root)
    results = cmds.scrollLayout("researchItemList", height=360, childResizable=True, parent=root)
    cmds.columnLayout("researchItemListContent", adjustableColumn=True,rowSpacing=3, parent=results)


    for title in titles:
        if titleFlags:
            cmds.textField(title, e=True, **titleFlags)
    for button in buttons:
        if buttonFlags:
            cmds.button(button, e=True, **buttonFlags)
    for field in inputs:
        if inputFlags:
            cmds.textField(field, e=True, **inputFlags)

    LoadResearchData()
    return root


def GetDataPath(*arr):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"Data", "Research")

def LoadResearchData(*arr):
    def load_data(file_name, *_):
        global session
        try:
            with open(os.path.join(folder, file_name), "r", encoding="utf-8") as stream:
                loaded = json.load(stream)
            if not isinstance(loaded, dict):
                raise ValueError("Invalid preset data")
            clean = {"currentPaths": [], "currentFiles": [],"pinnedPaths": [], "pinnedFiles": []}
            for key in clean:
                if isinstance(loaded.get(key), list):
                    clean[key] = loaded[key]
            session = clean
            for name, value in (("researchDataName", os.path.splitext(file_name)[0]),
                                ("researchFolder", loaded.get("folder", "")),
                                ("researchText", loaded.get("text", "")),
                                ("researchExts", loaded.get("exts", ""))):
                cmds.textField(name, e=True, text=str(value or ""))
            saved_mode = str(loaded.get("searchMode", "content")).lower()
            selected_mode = {"content": 1, "name": 2, "both": 3}.get(saved_mode, 1)
            cmds.optionMenu("researchSearchMode", e=True, select=selected_mode)
            cmds.checkBox("researchMatchCase", e=True, value=bool(loaded.get("matchCase", False)))
            UI["view"] = "files"
            LoadFiles()
        except (OSError, ValueError, TypeError) as exc:
            cmds.warning("Cannot load research preset: {}".format(exc))

    def delete_data(file_name, *_):
        try:
            os.remove(os.path.join(folder, file_name))
            LoadResearchData()
        except OSError as exc:
            cmds.warning("Cannot delete research preset: {}".format(exc))

    content = "dataListContent"
    if not cmds.layout(content, exists=True):
        return
    for child in cmds.layout(content, q=True, childArray=True) or []:
        cmds.deleteUI(child)

    folder = GetDataPath()
    if not os.path.isdir(folder):
        return
    for file_name in sorted(os.listdir(folder), key=str.lower):
        if not file_name.lower().endswith(".json"):
            continue
        row = cmds.rowLayout(numberOfColumns=2, adjustableColumn=1,columnWidth2=(370, 28), parent=content)
        cmds.button(label=os.path.splitext(file_name)[0],command=partial(load_data, file_name), parent=row)
        cmds.button(label="X", width=26, backgroundColor=(0.47, 0.23, 0.23),command=partial(delete_data, file_name), parent=row)


def SaveResearchData(*arr):
    previous_name = cmds.textField("researchDataName", q=True, text=True).strip()
    response = cmds.promptDialog(title="Save Research", message="Preset name:", text=previous_name,button=["Save", "Cancel"], defaultButton="Save",cancelButton="Cancel", dismissString="Cancel")
    if response != "Save":
        return
    name = cmds.promptDialog(q=True, text=True).strip()

    if not name or name in (".", "..") or any(char in name for char in '\\/:*?"<>|'):
        cmds.warning("Research: invalid preset name")
        return

    session["folder"] = cmds.textField("researchFolder", q=True, text=True).strip()
    session["text"] = cmds.textField("researchText", q=True, text=True)
    session["exts"] = cmds.textField("researchExts", q=True, text=True)
    session["searchMode"] = ("content", "name", "both")[
        cmds.optionMenu("researchSearchMode", q=True, select=True) - 1]
    session["matchCase"] = bool(cmds.checkBox("researchMatchCase", q=True,value=True))
    path = os.path.join(GetDataPath(), name + ".json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(session, stream, indent=4, ensure_ascii=False)
        cmds.textField("researchDataName", e=True, text=name)
        cmds.inViewMessage(amg="Saved preset: <hl>{}</hl>".format(name),pos="midCenter", fade=True)
        LoadResearchData()
    except OSError as exc:
        cmds.warning("Research preset save failed: {}".format(exc))


def ClearList(*arr):
    content = "researchItemListContent"
    if cmds.layout(content, exists=True):
        for child in cmds.layout(content, q=True, childArray=True) or []:
            cmds.deleteUI(child)


def LoadPaths(*arr):
    def use_path(path, *_):
        cmds.textField("researchFolder", e=True, text=path)

    def toggle_pin(path, *_):
        pinned = session["pinnedPaths"]
        if path in pinned:
            session["pinnedPaths"] = [item for item in pinned if item != path]
        else:
            pinned.append(path)
        LoadPaths()

    def open_path(path, *_):
        if os.path.isdir(path):
            os.startfile(path)
        else:
            cmds.warning("Folder not found: {}".format(path))

    UI["view"] = "paths"
    ClearList()
    keyword = cmds.textField("researchSearchText", q=True, text=True).strip().lower()
    paths = list(dict.fromkeys(session.get("currentPaths", [])))
    visible = [path for path in paths if keyword in path.lower()]
    for path in visible:
        row = cmds.rowLayout(numberOfColumns=4, adjustableColumn=1,columnWidth4=(290, 42, 58, 52),parent="researchItemListContent")
        cmds.textField(text=path, editable=False, parent=row)
        cmds.button(label="Use", width=40, command=partial(use_path, path), parent=row)
        label = "Unpin" if path in session["pinnedPaths"] else "Pin"
        cmds.button(label=label, width=55,command=partial(toggle_pin, path), parent=row)
        cmds.button(label="Open", width=49,command=partial(open_path, path), parent=row)
    cmds.text(UI["summary"], e=True,label="PATHS  |  {} shown / {} total".format(len(visible), len(paths)))


def LoadPinnedPaths(*arr):
    session["currentPaths"] = list(session.get("pinnedPaths", []))
    LoadPaths()


def LoadAllPaths(*arr):
    session["currentPaths"] = list(dict.fromkeys(path for path in sys.path if path))
    LoadPaths()


def PinFile(data, *arr):
    path = data["file"]
    if not any(item.get("file") == path for item in session["pinnedFiles"]):
        session["pinnedFiles"].append(dict(data))
    LoadFiles()


def UnpinFile(data, *arr):
    path = data["file"]
    session["pinnedFiles"] = [item for item in session["pinnedFiles"]
                              if item.get("file") != path]
    LoadFiles()


def LoadFiles(*arr):
    UI["view"] = "files"
    ClearList()
    keyword = cmds.textField("researchSearchText", q=True, text=True).strip().lower()
    items = session.get("currentFiles", [])
    visible = [item for item in items if keyword in
               (str(item.get("file", "")) + " " + str(item.get("text", ""))).lower()]
    pinned_paths = {item.get("file") for item in session.get("pinnedFiles", [])}
    for item in visible:
        path = str(item.get("file", ""))
        line_no = item.get("line")
        preview = str(item.get("text", ""))
        card = cmds.columnLayout(adjustableColumn=True, rowSpacing=3,parent="researchItemListContent")
        cmds.textField(text=path, editable=False, parent=card)
        if item.get("matchType") == "name":
            line_label = "NAME"
        elif item.get("matchType") in ("module", "module-root"):
            line_label = "MODULE"
        else:
            line_label = "L{}".format(line_no) if line_no is not None else "Binary"
        cmds.text(label="{}   |   {}".format(line_label, preview.replace("\n", " ")[:220]),align="left", height=21, parent=card)
        controls = cmds.rowLayout(numberOfColumns=5, adjustableColumn=1,columnWidth=[(1, 88), (2, 106), (3, 108),(4, 82), (5, 52)], parent=card)
        is_file = os.path.isfile(path)
        cmds.button(label="Context", height=25, enable=is_file,command=partial(_ResearchShowContext, dict(item), False),parent=controls)
        cmds.button(label="Trace Callback", height=25,enable=bool(is_file and line_no and path.lower().endswith(".py")),command=partial(_ResearchShowContext, dict(item), True),parent=controls)
        cmds.button(label="Open at Line" if line_no else ("Open Folder" if os.path.isdir(path) else "Open File"),height=25, command=partial(_ResearchOpenAtLine, path, line_no),parent=controls)
        cmds.button(label="Use Folder", height=25,command=lambda *_, f=path: cmds.textField("researchFolder", e=True,text=f if os.path.isdir(f) else os.path.dirname(f)),parent=controls)
        pinned = path in pinned_paths
        cmds.button(label="Unpin" if pinned else "Pin", height=25,command=partial(UnpinFile if pinned else PinFile, dict(item)),parent=controls)
        cmds.separator(style="in", height=4, parent=card)
    cmds.text(UI["summary"], e=True,label="FILES  |  {} shown / {} total  |  {} pinned".format(len(visible), len(items), len(pinned_paths)))


def LoadPinnedFiles(*arr):
    session["currentFiles"] = list(session.get("pinnedFiles", []))
    LoadFiles()


def CheckItems(*arr):
    folder = os.path.normpath(cmds.textField("researchFolder", q=True, text=True).strip())
    term = cmds.textField("researchText", q=True, text=True)
    raw_exts = cmds.textField("researchExts", q=True, text=True).strip()
    mode_index = cmds.optionMenu("researchSearchMode", q=True, select=True)
    search_mode = ("content", "name", "both")[mode_index - 1]
    match_case = cmds.checkBox("researchMatchCase", q=True, value=True)
    if not cmds.textField("researchFolder", q=True, text=True).strip() and search_mode == "name":
        return LocateResearchModule()
    if not os.path.isdir(folder):
        cmds.warning("Research: folder not found: {}".format(folder))
        return
    if not term:
        cmds.warning("Research: enter text to search")
        return

    if raw_exts.startswith(("[", "(")):
        try:
            tokens = ast.literal_eval(raw_exts)
        except (ValueError, SyntaxError):
            cmds.warning("Research: invalid extensions list")
            return
        tokens = [tokens] if isinstance(tokens, str) else tokens
    else:
        tokens = raw_exts.replace(";", ",").split(",")
    exts = []
    for value in tokens:
        value = str(value).strip().strip("'\"").lower()
        if not value or value in ("*", ".*"):
            continue
        if value.startswith("*."):
            value = value[1:]
        elif not value.startswith("."):
            value = "." + value
        exts.append(value)
    exts = tuple(exts)

    found = []
    search_bytes = term.encode("utf-8") if search_mode != "name" else None
    ascii_insensitive = not match_case and term.isascii()
    if ascii_insensitive and search_bytes is not None:
        search_bytes = search_bytes.lower()
    name_query = term if match_case else term.casefold()
    skipped = {".git", "__pycache__", ".idea", ".vs", ".svn", "node_modules"}
    for root, dirs, files in os.walk(folder):
        dirs[:] = [name for name in dirs if name.lower() not in skipped]
        for filename in files:
            if exts and not filename.lower().endswith(exts):
                continue
            path = os.path.join(root, filename)

            name_value = filename if match_case else filename.casefold()
            if search_mode in ("name", "both") and name_query in name_value:
                found.append({"file": path,"line": None,"text": "Filename: {}".format(filename),"matchType": "name",})
            if search_mode == "name":
                continue

            try:
                with open(path, "rb") as stream:
                    for line_number, raw_line in enumerate(stream, start=1):
                        if match_case:
                            matched = search_bytes in raw_line
                        elif ascii_insensitive:
                            matched = search_bytes in raw_line.lower()
                        else:
                            matched = term.casefold() in raw_line.decode(
                                "utf-8", errors="replace").casefold()
                        if matched:
                            binary = b"\x00" in raw_line
                            found.append({
                                "file": path,
                                "line": None if binary else line_number,
                                "text": "FOUND IN BINARY" if binary else
                                        raw_line.decode("utf-8", errors="replace").strip(),
                                "matchType": "binary" if binary else "content",
                            })
                            if binary:
                                break

            except (OSError, ValueError) as exc:
                print("Research skipped {}: {}".format(path, exc))

    session["currentFiles"] = found
    UI["view"] = "files"
    LoadFiles()
    matched_file_count = len({entry["file"] for entry in found})
    print("Research [{}]: {} match(es) across {} file(s) in {}".format(
        search_mode, len(found), matched_file_count, folder))



def _ResearchModuleQuery(raw):
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Enter a module name or MEL command")

    source_match = re.search(r"\bsource\s+[\"']([^\"']+)[\"']", text)
    if source_match:
        return "mel_file", source_match.group(1).strip()

    imports = re.findall(r"\b(?:from|import)\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", text)
    if imports:
        return "python", imports[-1]

    text = text.rstrip(" ;\t\n")
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", text):
        return "python_or_mel", text
    if re.fullmatch(r"[\w.\-/\\: ]+\.mel", text, re.IGNORECASE):
        return "mel_file", text
    if re.fullmatch(r"[A-Za-z_]\w*\(\)", text):
        return "mel_proc", text[:-2]
    raise ValueError("Use a module name (e.g. pymel.core), an import statement, or MEL source/procedure")


def _ResearchLocateModuleFiles(raw):
    kind, name = _ResearchModuleQuery(raw)
    results, seen = [], set()
    def add(path, origin):
        if not path or not isinstance(path, str):
            return
        path = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
        if not os.path.isfile(path) and not os.path.isdir(path):
            return
        key = os.path.normcase(path)
        if key in seen:
            return
        seen.add(key)
        results.append({"file": path, "line": None, "matchType": "module" if os.path.isfile(path) else "module-root","text": "{}  |  {}".format(name, origin)})

    roots = []
    def add_root(path):
        if path and isinstance(path, str):
            path = os.path.abspath(os.path.expanduser(path))
            if os.path.isdir(path) and os.path.normcase(path) not in {
                    os.path.normcase(p) for p in roots}:
                roots.append(path)

    for path in sys.path:
        add_root(path)
    for env_name in ("MAYA_SCRIPT_PATH", "MAYA_MODULE_PATH", "PYTHONPATH"):
        for path in os.environ.get(env_name, "").split(os.pathsep):
            add_root(path)
    try:
        add_root(cmds.internalVar(userScriptDir=True))
    except (AttributeError, RuntimeError, TypeError):
        pass

    if kind in ("python", "python_or_mel"):
        loaded = sys.modules.get(name)
        if loaded is not None:
            add(getattr(loaded, "__file__", None), "already loaded in Maya")
        try:
            paths = None
            spec = None
            parent = ""
            for part in name.split("."):
                parent = part if not parent else parent + "." + part
                cached = sys.modules.get(parent)
                if cached is not None:
                    cached_path = getattr(cached, "__path__", None)
                    cached_file = getattr(cached, "__file__", None)
                    if parent == name:
                        add(cached_file, "already loaded in Maya")
                    if cached_path is not None:
                        paths = list(cached_path)
                        continue
                spec = importlib.machinery.PathFinder.find_spec(parent, paths)
                if spec is None:
                    break
                if parent == name:
                    add(spec.origin, "Python import path")
                    if spec.origin is None:
                        for location in spec.submodule_search_locations or []:
                            add(location, "Python namespace package")
                paths = list(spec.submodule_search_locations or [])
                if not paths and parent != name:
                    break
        except (ImportError, ValueError, TypeError, OSError, AttributeError) as exc:
            print("Research module resolver: {}".format(exc))

    if kind in ("python", "python_or_mel", "mel_file", "mel_proc"):
        try:
            modules = cmds.moduleInfo(listModules=True) or []
        except (AttributeError, RuntimeError, TypeError):
            modules = []
        for maya_name in modules:
            try:
                root = cmds.moduleInfo(path=True, moduleName=maya_name)
            except (RuntimeError, TypeError):
                continue
            if not root or not os.path.isdir(root):
                continue
            add_root(root)
            add_root(os.path.join(root, "scripts"))
            add_root(os.path.join(root, "python"))
            if str(maya_name).casefold() == name.split(".")[0].casefold():
                add(root, "registered Maya module")

    if kind in ("python", "python_or_mel"):
        relative = os.path.join(*name.split("."))
        for root in roots:
            add(os.path.join(root, relative + ".py"), "Python/Maya script path")
            add(os.path.join(root, relative, "__init__.py"), "Python package")
            add(os.path.join(root, name + ".py"), "literal filename")

    if kind in ("mel_file", "mel_proc", "python_or_mel"):
        import maya.mel as mel
        procedure = os.path.basename(name)
        if procedure.lower().endswith(".mel"):
            procedure = procedure[:-4]
        if re.fullmatch(r"[A-Za-z_]\w*", procedure):
            try:
                description = str(mel.eval('whatIs "{}";'.format(procedure)))
                matched = re.search(r"found in:\s*(.+)$", description, re.I)
                if matched:
                    add(matched.group(1).strip(), "MEL whatIs")
            except (RuntimeError, ValueError, TypeError):
                pass
        file_name = name if name.lower().endswith(".mel") else name + ".mel"
        for root in roots:
            add(os.path.join(root, file_name), "MEL script path")
            add(os.path.join(root, "scripts", file_name), "Maya module scripts")

    return results, name


def LocateResearchModule(*arr):
    raw = cmds.textField("researchText", q=True, text=True)
    try:
        found, name = _ResearchLocateModuleFiles(raw)
    except (ValueError, OSError, ImportError) as exc:
        cmds.warning("Research Locate: {}".format(exc))
        return
    session["currentFiles"] = found
    UI["view"] = "files"
    LoadFiles()
    if found:
        first = found[0]["file"]
        directory = first if os.path.isdir(first) else os.path.dirname(first)
        cmds.textField("researchFolder", e=True, text=directory)
        cmds.text(UI["summary"], e=True, label="LOCATED {}  |  {} path(s)  |  Folder set".format(
            name, len(found)))
    else:
        cmds.text(UI["summary"], e=True, label="NOT FOUND  |  {}".format(name))
        cmds.warning("Research: '{}' not found in active Maya/Python paths. "
                     "The MEL command may load a file dynamically or use a custom path.".format(name))

INSPECTOR_UI = {}

def _ResearchReadSource(path):
    with open(path, "rb") as stream:
        raw = stream.read()
    if b"\x00" in raw[:4096]:
        raise ValueError("Binary file: source context is unavailable")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeError:
        return raw.decode("cp1252", errors="replace")


def _ResearchContextText(source, line, radius=9):
    lines = source.splitlines()
    if not lines:
        return "(Empty file)"
    line = max(1, min(int(line or 1), len(lines)))
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    width = len(str(end))
    return "\n".join("{} {} | {}".format(">" if n == line else " ",str(n).rjust(width), lines[n - 1]) for n in range(start, end + 1))


def _ResearchAstName(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _ResearchAstName(node.value)
        return prefix + "." + node.attr if prefix else node.attr
    return ""


def _ResearchCallbackExpression(node, source):
    text = ast.get_source_segment(source, node) or _ResearchAstName(node) or "<expression>"
    if isinstance(node, (ast.Name, ast.Attribute)):
        return text, _ResearchAstName(node)
    if isinstance(node, ast.Lambda):
        body = node.body
        if isinstance(body, ast.Call):
            return text, _ResearchAstName(body.func)
        return text, _ResearchAstName(body)
    if isinstance(node, ast.Call):
        func_name = _ResearchAstName(node.func)
        if func_name.rsplit(".", 1)[-1] == "partial" and node.args:
            _, symbol = _ResearchCallbackExpression(node.args[0], source)
            return text, symbol
        return text, _ResearchAstName(node.func)
    return text, ""


def _ResearchTraceCallback(path, line):
    def scope(node):
        while node is not None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return node
            node = parents.get(id(node))
        return tree

    def ancestor(node, kind):
        while node is not None:
            if isinstance(node, kind):
                return node
            node = parents.get(id(node))
        return None

    def same_owner(a, b, variable):
        if variable.startswith("self."):
            return (ancestor(a, ast.ClassDef) is not None and
                    ancestor(a, ast.ClassDef) is ancestor(b, ast.ClassDef))
        return scope(a) is scope(b)

    def definition_for(symbol, reference):
        if not symbol:
            return None
        tail = symbol.split(".")[-1]
        candidates = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == tail]
        if not candidates:
            return None
        local_class = ancestor(reference, ast.ClassDef)
        if symbol.startswith("self."):
            candidates = [n for n in candidates if ancestor(n, ast.ClassDef) is local_class]
        elif "." in symbol:
            return None
        else:
            local = [n for n in candidates if scope(n) is scope(reference)]
            if local:
                candidates = local
            else:
                candidates = [n for n in candidates if ancestor(n, ast.ClassDef) is None]
        return candidates[0].lineno if len(candidates) == 1 else None

    def add_match(callback, widget, origin, kind):
        display, symbol = _ResearchCallbackExpression(callback, source)
        result["matches"].append({
            "callback": display,
            "symbol": symbol,
            "line": getattr(origin, "lineno", None),
            "definition": definition_for(symbol, origin),
            "kind": kind,
        })
        if widget:
            result["widget"] = widget

    result = {"widget": "", "matches": [], "note": ""}
    if not str(path).lower().endswith(".py"):
        result["note"] = "Callback analysis currently supports Python sources only."
        return result
    try:
        source = _ResearchReadSource(path)
        tree = ast.parse(source, filename=path)
        line = int(line)
    except (SyntaxError, ValueError, OSError, UnicodeError) as exc:
        result["note"] = "Cannot parse Python source: {}".format(exc)
        return result

    parents = {}
    for ancestor in ast.walk(tree):
        for child in ast.iter_child_nodes(ancestor):
            parents[id(child)] = ancestor

    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and n.lineno <= line <= getattr(n, "end_lineno", n.lineno)]
    calls.sort(key=lambda n: (getattr(n, "end_lineno", n.lineno) - n.lineno, -n.lineno))

    callback_keys = {"command", "c", "changeCommand", "cc", "onCommand", "doubleClickCommand", "dcc", "dragCallback", "dropCallback"}
    maya_creators = {"button", "iconTextButton", "symbolButton", "menuItem", "checkBox", "radioButton", "textField", "textFieldGrp", "textFieldButtonGrp", "intField", "floatField", "optionMenu", "optionMenuGrp", "scriptJob"}
    qt_creators = {"QPushButton", "QToolButton", "QAction", "QCheckBox", "QRadioButton", "QComboBox", "QLineEdit"}

    widget = ""
    qt_node = None
    for call in calls:
        func = _ResearchAstName(call.func)
        short = func.rsplit(".", 1)[-1]
        if short in maya_creators:
            entries = [keyword for keyword in call.keywords if keyword.arg in callback_keys]
            if entries:
                for kw in entries:
                    add_match(kw.value, func, call, "Maya {}".format(kw.arg))
                break

            assignment = ancestor(call, ast.Assign)
            variable = (_ResearchAstName(assignment.targets[0]) if assignment is not None and assignment.targets else "")
            literal_name = (call.args[0].value if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str) else None)
            if variable or literal_name:
                for candidate in ast.walk(tree):
                    if not isinstance(candidate, ast.Call) or candidate is call:
                        continue
                    if _ResearchAstName(candidate.func) != func or not candidate.args:
                        continue
                    first = candidate.args[0]
                    same_variable = variable and _ResearchAstName(first) == variable
                    same_literal = (literal_name is not None and isinstance(first, ast.Constant) and first.value == literal_name)
                    if not (same_variable or same_literal):
                        continue
                    if not same_owner(call, candidate, variable or literal_name):
                        continue
                    editing = any(k.arg in ("e", "edit") and isinstance(k.value, ast.Constant) and k.value.value is True for k in candidate.keywords)
                    if not editing:
                        continue
                    for keyword in candidate.keywords:
                        if keyword.arg in callback_keys:
                            add_match(keyword.value, variable or literal_name, candidate, "Maya edited {}".format(keyword.arg))
            if not result["widget"]:
                result["widget"] = variable or literal_name or func
        if short in qt_creators:
            qt_node = call
            break
        if short in ("setText", "setObjectName", "setTitle"):
            widget = _ResearchAstName(call.func.value)
            qt_node = call
            break

    if qt_node is not None:
        if not widget:
            assign = ancestor(qt_node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
            if isinstance(assign, ast.Assign) and assign.targets:
                widget = _ResearchAstName(assign.targets[0])
            elif isinstance(assign, ast.AnnAssign):
                widget = _ResearchAstName(assign.target)
            elif isinstance(assign, ast.NamedExpr):
                widget = _ResearchAstName(assign.target)
        if widget:
            result["widget"] = widget
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call) or not call.args:
                    continue
                if not isinstance(call.func, ast.Attribute) or call.func.attr != "connect":
                    continue
                signal = call.func.value
                if not isinstance(signal, ast.Attribute):
                    continue
                owner = _ResearchAstName(signal.value)
                if owner != widget or not same_owner(qt_node, call, widget):
                    continue
                add_match(call.args[0], widget, call, "Qt {}".format(signal.attr))

    unique, seen = [], set()
    for item in result["matches"]:
        identity = (item["line"], item["callback"], item["kind"])
        if identity not in seen:
            seen.add(identity)
            unique.append(item)
    result["matches"] = unique
    if not unique:
        result["note"] = (
            "No callback could be linked confidently to this match. "
            "The UI may be created dynamically, connected elsewhere, or "
            "use an unsupported callback pattern."
        )
    return result


def _ResearchOpenAtLine(path, line=None, *args):
    if os.path.isdir(path):
        if hasattr(os, "startfile"):
            os.startfile(path)
        else:
            cmds.warning("Research: folder found but cannot open Explorer on this OS")
        return
    if not os.path.isfile(path):
        cmds.warning("Research: file not found: {}".format(path))
        return
    destination = "{}:{}".format(path, int(line)) if line else path
    try:
        NLTA_General.OpenSublime(destination)
    except Exception as exc:
        cmds.warning("Research: cannot open Sublime: {}".format(exc))


def _ResearchShowContext(item, trace=False, *args):
    global INSPECTOR_UI
    path = str(item.get("file", ""))
    line = item.get("line")
    if not os.path.isfile(path):
        cmds.warning("Research: file not found: {}".format(path))
        return
    try:
        source = _ResearchReadSource(path)
    except (OSError, UnicodeError, ValueError) as exc:
        cmds.warning("Research: cannot show context: {}".format(exc))
        return

    window = "NLTA_ResearchContextInspector"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="NLTA / Code Context", sizeable=True, widthHeight=(760, 610))
    root = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
    cmds.text(label="CODE CONTEXT  /  READ-ONLY", align="left", font="boldLabelFont", height=28, parent=root)
    cmds.textField(text=path, editable=False, parent=root)
    cmds.text(label="Match at line {}".format(line if line else "N/A"), align="left", parent=root)
    actions = cmds.rowLayout(numberOfColumns=4, adjustableColumn=1, columnWidth=[(1, 185), (2, 150), (3, 170), (4, 110)], parent=root)
    cmds.button(label="Open at Line", height=28, command=partial(_ResearchOpenAtLine, path, line), parent=actions)
    cmds.button(label="Trace Callback", height=28, enable=bool(line and str(path).lower().endswith(".py")), command=lambda *_: run_trace(), parent=actions)
    definition_button = cmds.button(label="Open Definition", height=28, enable=False, parent=actions)
    cmds.button(label="Close", height=28, command=lambda *_: cmds.deleteUI(window), parent=actions)
    context = cmds.scrollField(editable=False, wordWrap=False, text=_ResearchContextText(source, line, 11), height=345, parent=root)
    cmds.separator(style="in", height=5, parent=root)
    cmds.text(label="STATIC CALLBACK TRACE", align="left", font="boldLabelFont", parent=root)
    output = cmds.scrollField(editable=False, wordWrap=True, text="Select Trace Callback to analyze this code.", height=140, parent=root)

    def run_trace(*_):
        trace_data = _ResearchTraceCallback(path, line)
        entries = trace_data["matches"]
        if not entries:
            cmds.scrollField(output, e=True, text=trace_data["note"])
            cmds.button(definition_button, e=True, enable=False)
            return
        sections = ["Widget: {}".format(trace_data["widget"] or "(not resolved)")]
        locations = []
        for index, entry in enumerate(entries, 1):
            location = entry["definition"]
            sections.append("{}. {}  [line {}]".format(
                index, entry["kind"], entry["line"]))
            sections.append("   Callback: {}".format(entry["callback"]))
            sections.append("   Definition: {}".format(
                "line {}".format(location) if location else "Not located in this file"))
            if location:
                locations.append(location)
        cmds.scrollField(output, e=True, text="\n".join(sections))
        if locations:
            def open_definition(*_):
                _ResearchOpenAtLine(path, locations[0])
            cmds.button(definition_button, e=True, enable=True,command=open_definition)
        else:
            cmds.button(definition_button, e=True, enable=False)

    INSPECTOR_UI = {"window": window, "context": context, "trace": output}
    cmds.showWindow(window)
    if trace and line:
        run_trace()
    return window


def OpenLiveInspector(*args):
    try:
        import importlib.util
        name = "NLTA_UI_Inspector"
        module_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   name + ".py")
        if name in sys.modules:
            inspector = sys.modules[name]
        elif os.path.isfile(module_path):
            spec = importlib.util.spec_from_file_location(name, module_path)
            if not spec or not spec.loader:
                raise RuntimeError("Cannot load inspector module at {}".format(module_path))
            inspector = importlib.util.module_from_spec(spec)
            sys.modules[name] = inspector
            try:
                spec.loader.exec_module(inspector)
            except Exception:
                sys.modules.pop(name, None)
                raise
        else:
            inspector = __import__(name)
        inspector.ShowUI()
    except Exception as exc:
        cmds.warning("Live UI Inspector: {}. Check NLTA_UI_Inspector.py location.".format(exc))


def OpenUIAutomation(*args):
    try:
        import importlib.util
        name = "NLTA_UI_Automation"
        module_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
        if name in sys.modules:
            automation = sys.modules[name]
        elif os.path.isfile(module_path):
            spec = importlib.util.spec_from_file_location(name, module_path)
            if spec is None or spec.loader is None:
                raise RuntimeError("Cannot load automation module")
            automation = importlib.util.module_from_spec(spec)
            sys.modules[name] = automation
            try:
                spec.loader.exec_module(automation)
            except Exception:
                sys.modules.pop(name, None)
                raise
        else:
            automation = __import__(name)
        panel = automation.ShowUI()
        if cmds.textField("researchText", exists=True):
            raw = cmds.textField("researchText", q=True, text=True).strip()
            if "(" in raw and ("python" in raw.lower() or "import " in raw):
                panel.launcher_edit.setText(raw)
                panel.parse_launcher()
            elif re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", raw):
                if cmds.optionMenu("researchSearchMode", exists=True):
                    if cmds.optionMenu("researchSearchMode", q=True, select=True) == 2:
                        panel.module_edit.setText(raw)
    except Exception as exc:
        cmds.warning("UI Automation: {}. Keep NLTA_UI_Automation.py beside Research.".format(exc))
