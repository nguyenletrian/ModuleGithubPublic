"""NLTA Scene Replace pattern. Requires NLTA_General and NLTA_UI."""
import os
import codecs
import inspect
import ast
from datetime import datetime
from functools import partial
import maya.cmds as cmds
import NLTA_General
import NLTA_UI

ITEMS = {"items": {}, "order": []}


def DefaultSetting(path, *arr):
    moduleName = os.path.splitext(os.path.basename(__file__))[0]
    return {
        "ext": "json", "path": os.path.join(path, moduleName + ".json"),
        "moduleName": moduleName, "order": 0, "title": "Replace",
        "name": "Replace", "id": datetime.now().strftime("%Y%m%d%H%M%S")
    }


def Load(data, listUI, *arr):
    newest = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]
    })
    ITEMS["items"].clear()
    ITEMS["order"][:] = []
    for child in cmds.layout(listUI, q=True, childArray=True) or []:
        cmds.deleteUI(child)
    path = newest.get("path", "")
    if path and os.path.isfile(path):
        for record in NLTA_General.readJsonFile(path) or []:
            Add(listUI, record)


def Form(data, *arr):
    def Save(*_):
        newest = NLTA_General.JsonGetByID({
            "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
            "id": data["id"]
        })
        ordered = {key: ITEMS["items"][key] for key in ITEMS["order"]}
        NLTA_General.writeJsonFile(newest["path"], NLTA_UI.GetData(ordered))

    def SaveAndExport(*args):
        Save()
        ExportPython(data)

    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI, listUI = dataBack["buttonUI"], dataBack["listUI"]
    cmds.rowColumnLayout(numberOfColumns=3, parent=buttonUI)
    cmds.button(label="Add", width=130, c=partial(Add, listUI, {}))
    cmds.button(label="Save", width=130, c=Save)
    cmds.button(label="Run", width=115, c=partial(Run, data))
    export_button = cmds.button(label="Export Py", width=115, c=SaveAndExport)
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", c=partial(OpenExportFolder, data))
    cmds.setParent("..")
    Load(data, listUI)


def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def _find_replace_tokens(text, pattern):
    pattern = pattern.strip()

    if not pattern:
        raise ValueError("Pattern cannot be empty")

    # Accept NLTA_Replace or NLTA_Replace(...)
    function_name = pattern.split("(", 1)[0].strip()
    prefix = function_name + "("

    matches = []
    cursor = 0

    while True:
        start = text.find(prefix, cursor)

        if start == -1:
            break

        value_start = start + len(prefix)

        depth = 1
        quote = None
        triple = False
        escaped = False
        i = value_start

        while i < len(text):
            char = text[i]

            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif triple and text.startswith(quote * 3, i):
                    quote = None
                    triple = False
                    i += 2
                elif not triple and char == quote:
                    quote = None

            elif char in ("'", '"'):
                quote = char
                triple = text.startswith(char * 3, i)
                if triple:
                    i += 2

            elif char == "(":
                depth += 1

            elif char == ")":
                depth -= 1

                if depth == 0:
                    matches.append((
                        start,
                        i + 1,
                        text[value_start:i]
                    ))
                    cursor = i + 1
                    break

            i += 1

        else:
            cursor = value_start

    return matches



def BuildReplace(records, warn):
    """Write the same UTF-8 token replacements and validation as the original Run."""
    for index, record in enumerate(records, 1):
        try:
            source = os.path.abspath(os.path.expanduser(record["sourcePath"].strip()))
            output_value = record["outputPath"].strip()
            if not output_value:
                raise ValueError("Output path is empty")
            output = os.path.abspath(os.path.expanduser(output_value))
            if not os.path.isfile(source):
                raise ValueError("Source file not found: {}".format(source))
            if os.path.normcase(source) == os.path.normcase(output):
                raise ValueError("Source and output paths must be different")
            if not os.path.isdir(os.path.dirname(output)):
                raise ValueError("Output directory does not exist")
            with open(source, "rb") as stream:
                raw = stream.read()
            bom = raw.startswith(codecs.BOM_UTF8)
            content = raw.decode("utf-8-sig")
            matches = _find_replace_tokens(content, record["pattern"].strip())
            values = record["replacements"]
            if len(matches) != len(values):
                raise ValueError("{} tokens but {} fields; scan again".format(
                    len(matches), len(values)))
            parts, previous = [], 0
            for (start, end, _), value in zip(matches, values):
                parts.extend((content[previous:start], str(value)))
                previous = end
            parts.append(content[previous:])
            result = "".join(parts)
            with open(output, "wb") as stream:
                stream.write(result.encode("utf-8-sig" if bom else "utf-8"))
            print("NLTA Replace: saved {} ({} replacements)".format(output, len(matches)))
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            warn("Replace item {}: {}".format(index, exc))


def Run(data, *arr):
    if ITEMS["order"]:
        ordered = {key: ITEMS["items"][key] for key in ITEMS["order"]}
        records = NLTA_UI.GetData(ordered)
    else:
        newest = NLTA_General.JsonGetByID({
            "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
            "id": data["id"]
        })
        records = NLTA_General.readJsonFile(newest["path"]) or []
    return BuildReplace(records, cmds.warning)


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("Replace Export: no saved records")
        return None

    # Export file operations, not Maya scene operations.
    funcs = (_find_replace_tokens, BuildReplace)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in funcs))
    body = ast.unparse(tree)
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    embedded = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    source = (
        "def main():\n"
        "    import os\n"
        "    import codecs\n\n"
        "    # Replace data\n"
        "    REPLACE_DATA = " + embedded + "\n\n"
        + body
        + "\n\n    # Files are written only when the script is executed.\n"
        + "    BuildReplace(REPLACE_DATA, print)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in source:
        source = source.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(source)
    return output


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_pattern_data_path(data)))


def Add(listUI, data, *arr):
    data = data or {}


    def find_tokens(text, pattern):
        pattern = pattern.strip()

        if not pattern:
            raise ValueError("Pattern cannot be empty")

        # Accept NLTA_Replace or NLTA_Replace(...)
        function_name = pattern.split("(", 1)[0].strip()
        prefix = function_name + "("

        matches = []
        cursor = 0

        while True:
            start = text.find(prefix, cursor)

            if start == -1:
                break

            value_start = start + len(prefix)

            depth = 1
            quote = None
            triple = False
            escaped = False
            i = value_start

            while i < len(text):
                char = text[i]

                if quote:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif triple and text.startswith(quote * 3, i):
                        quote = None
                        triple = False
                        i += 2
                    elif not triple and char == quote:
                        quote = None

                elif char in ("'", '"'):
                    quote = char
                    triple = text.startswith(char * 3, i)
                    if triple:
                        i += 2

                elif char == "(":
                    depth += 1

                elif char == ")":
                    depth -= 1

                    if depth == 0:
                        matches.append((
                            start,
                            i + 1,
                            text[value_start:i]
                        ))
                        cursor = i + 1
                        break

                i += 1

            else:
                cursor = value_start

        return matches


    def Delete(ui, *args):
        ITEMS["items"].pop(ui, None)
        if ui in ITEMS["order"]:
            ITEMS["order"].remove(ui)
        if cmds.layout(ui, exists=True):
            cmds.deleteUI(ui)

    def Scan(pattern_text=None, source_text=None, keep_values=False, *args):
        """Always read the live UI fields unless explicit text is supplied."""
        try:
            if pattern_text is None:
                pattern_text = NLTA_UI.GetUIValue(itemData["Pattern"])
            if source_text is None:
                source_text = NLTA_UI.GetUIValue(itemData["SourcePath"])

            pattern_text = str(pattern_text).strip()
            source_text = str(source_text).strip()
            source_path = os.path.abspath(os.path.expanduser(source_text))
            if not os.path.isfile(source_path):
                raise ValueError("Source file does not exist: {}".format(source_path))

            with open(source_path, "rb") as stream:
                content = stream.read().decode("utf-8-sig")
            matches = find_tokens(content, pattern_text)

            old_values = (NLTA_UI.GetUIValue(itemData["Replacements"])
                          if keep_values else [])
            values = [old_values[i] if i < len(old_values) else match[2]
                      for i, match in enumerate(matches)]
            NLTA_UI.FillUI(itemData["Replacements"], values)
            cmds.text(foundText, e=True,
                      label="{} replacement(s) found".format(len(matches)))
            return len(matches)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            cmds.text(foundText, e=True, label="Scan failed")
            cmds.warning("Replace scan: {}".format(exc))
            return 0

    def BrowseSource(*args):
        if NLTA_UI.BrowsePathUI(itemData["SourcePath"]):
            Scan(keep_values=False)

    def OpenFile(key, *args):
        path = str(NLTA_UI.GetUIValue(itemData[key])).strip()
        path = os.path.abspath(os.path.expanduser(path)) if path else ""
        if not path or not os.path.isfile(path):
            cmds.warning("File does not exist: {}".format(path))
            return
        try:
            NLTA_General.OpenSublime(path)
        except Exception as exc:
            cmds.warning("Could not open in Sublime: {}".format(exc))

    # Main card follows the existing NLTA pattern: compact labels and inputs.
    itemData = {}
    itemUI = cmds.rowColumnLayout(
        numberOfColumns=1, parent=listUI,
        backgroundColor=(0.15, 0.15, 0.15))
    main = cmds.columnLayout(adjustableColumn=True, rowSpacing=6, parent=itemUI)
    cmds.separator(height=6, style="none")
    cmds.text(label="  FILE REPLACEMENT", align="left", height=24,
              font="boldLabelFont")
    grid = cmds.rowColumnLayout(numberOfColumns=2, columnWidth=[(1, 50), (2, 300)],columnSpacing=[(1, 7), (2, 5)], parent=main)
    cmds.text(label="Pattern", align="right", height=30, parent=grid)
    itemData["Pattern"] = cmds.textField(
        text=data.get("pattern", "NLTA_Replace(*chuỗi ký tự*)"),
        height=27, parent=grid)
    cmds.text(label="Source", align="right", height=36, parent=grid)
    sourceRow = cmds.rowLayout(numberOfColumns=2, adjustableColumn=1,
                               columnWidth2=(245, 54), parent=grid)
    itemData["SourcePath"] = NLTA_UI.CreatePathUI(
        parent=sourceRow, value=data.get("sourcePath", ""),
        mode="file", label="", fileFilter="All Files (*.*)")
    cmds.button(label="Open", width=52, height=27, parent=sourceRow,
                c=lambda *_: OpenFile("SourcePath"))

    cmds.text(label="Output", align="right", height=36, parent=grid)
    outputRow = cmds.rowLayout(numberOfColumns=2, adjustableColumn=1,
                               columnWidth2=(245, 54), parent=grid)
    itemData["OutputPath"] = NLTA_UI.CreatePathUI(
        parent=outputRow, value=data.get("outputPath", ""),
        mode="save", label="", fileFilter="All Files (*.*)")
    cmds.button(label="Open", width=52, height=27, parent=outputRow,
                c=lambda *_: OpenFile("OutputPath"))
    cmds.setParent(main)

    toolbar = cmds.rowLayout(numberOfColumns=3, adjustableColumn=1, parent=main)
    foundText = cmds.text(label="No source scanned", align="left", parent=toolbar)
    cmds.button(label="Scan Source", width=100, height=28,
                c=lambda *_: Scan(keep_values=False), parent=toolbar)
    cmds.button(label="X", width=32, height=28,
                backgroundColor=(0.5, 0.2, 0.2), c=partial(Delete, itemUI), parent=toolbar)
    cmds.setParent(main)
    cmds.separator(height=3, style="in", parent=main)
    itemData["Replacements"] = NLTA_UI.CreateScrollListUI(
        parent=main, values=data.get("replacements", []), height=260,
        fieldHeight=70)
    cmds.separator(height=8, style="none", parent=main)

    # Replace only the source Browse callback; generic PathUI still owns get/set.
    sourceUI = itemData["SourcePath"]
    pathChildren = cmds.rowLayout(sourceUI["row"], q=True, childArray=True) or []
    for child in pathChildren:
        if cmds.objectTypeUI(child) == "button":
            cmds.button(child, e=True, c=BrowseSource)
    cmds.textField(sourceUI["field"], e=True,
                   changeCommand=lambda *_: Scan(keep_values=False))
    cmds.textField(itemData["Pattern"], e=True,
                   changeCommand=lambda *_: Scan(keep_values=False))

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)
    if data.get("sourcePath") and os.path.isfile(data["sourcePath"]):
        Scan(keep_values=True)
    return itemUI
