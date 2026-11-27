import maya.cmds as cmds
import importlib
import os
import io
import shutil
import builtins
import sys
import subprocess
import pymel.core as pm
from functools import partial


import NLTA_General, NLTA_UI
for module in [NLTA_General,NLTA_UI]:
    try:
        importlib.reload(module)
    except:
        reload(module)


currentFile = os.path.abspath(__file__)
currentFolder = os.path.dirname(currentFile)
for folder in ["ScenePattern","SceneDefaultFunctions"]:
    folderTemp = os.path.join(currentFolder,folder)
    if folderTemp not in sys.path:
        sys.path.insert(0, folderTemp)


defaultFunctionsFolder = os.path.join(currentFolder,"SceneDefaultFunctions")+"/"
scenePatternFolder = os.path.join(currentFolder,"ScenePattern")+"/"
projectPath =  NLTA_General.GetProjectFunctionPath()
if not projectPath:
    print("#### Please save the scene!~")

upDataFolder = ("/").join(os.path.dirname(pm.sceneName()).split('/')[0:-1])+ "/SceneData/"
currentDataFolder = ("/").join(os.path.dirname(pm.sceneName()).split('/'))+ "/SceneData/"

patterns = {
    "Scene_Pattern_ClearOffset":"Clear Offset",
    "Scene_Pattern_Delete":"Delete",
    "Scene_Pattern_SDK":"SDK",
    "Scene_Pattern_PoseEditor":"Pose Editor",
    "Scene_Pattern_SDK_2D":"SDK 2D",
    "Scene_Pattern_SDK_Simultaneous2D":"SDK Simultaneous 2D",
    "Scene_Pattern_SDKModulo":"SDK Modulo",
    "Scene_Pattern_Global":"Global",
    "Scene_Pattern_Group":"Group",
    "Scene_Pattern_Layer":"Layer",
    "Scene_Pattern_Note":"Note",
    "Scene_Pattern_Replace":"Replace",
    "Scene_Pattern_Rename":"Rename",
    "Scene_Pattern_Visibility":"Visibility",
    "Scene_Pattern_VisibilityToggle":"Visibility Toggle", 


    "Scene_Pattern_AttributeCreate":"Attribute Create",
    "Scene_Pattern_AttributeDrivenRange":"Attribute Driven Range",
    "Scene_Pattern_AttributeDelete":"Attribute Delete",
    "Scene_Pattern_AttributeDefaultValue":"Attribute Default Value",
    "Scene_Pattern_AttributeTransfer":"Attribute Transfer",
    "Scene_Pattern_AttributeRename":"Attribute Rename",
    "Scene_Pattern_AttributeUnlock":"Attribute Unlock",
    "Scene_Pattern_AttributeProxy":"Attribute Proxy",
    "Scene_Pattern_AttributeSetMaxInfluence":"Attribute Set Max Influence",


    "Scene_Pattern_BackupTransform":"Back Transform",
    "Scene_Pattern_BackupAnimation":"Back Animation",

    "Scene_Pattern_BSSequenceFromObjKeys":"BS Sequel from obj keys",

    "Scene_Pattern_CreateRef":"Create Ref",
    "Scene_Pattern_CreateCurve":"Create Curve",
    "Scene_Pattern_CreateOffset":"Create Offset",
    "Scene_Pattern_CreateSplineIKFromObjs":"Create Spline IK From Objs",
    "Scene_Pattern_CreateSplineControlsFromSplineIK":"Create Spline Controls From Spline IK",
    "Scene_Pattern_CreateProxy":"Create Proxy",


    "Scene_Pattern_ConstraintAim":"Constraint Aim",
    "Scene_Pattern_ConstraintOrient":"Constraint Orient",
    "Scene_Pattern_FollowOrient":"Follow Orient",
    "Scene_Pattern_FollowTranslate":"Follow Translate",
    "Scene_Pattern_FollowDistance":"Follow Distance", 

    "Scene_Pattern_ControlShape":"Control Shape",
    "Scene_Pattern_ControlShapeAS":"AS Control Shape",

    "Scene_Pattern_DeformSine":"Deform Sine",
    "Scene_Pattern_DeformSineForControls":"Deform Sine For Controls",

    "Scene_Pattern_PathReplace":"Path Replace",
    "Scene_Pattern_PathLink":"Path Links",

    "Scene_Pattern_RigBasic":"Rig Basic",
    "Scene_Pattern_RigAutoRoll":"Rig Auto Roll",
    "Scene_Pattern_RigAutoSkirt":"Rig Auto Skirt",
    "Scene_Pattern_RigAutoSkirtFunc":"Rig Auto Skirt Func",
    "Scene_Pattern_RigAutoSkirtFnc":"Rig Auto Skirt Fnc",
    "Scene_Pattern_RigAutoSkirtVector":"Rig Auto Skirt Vector",
    "Scene_Pattern_RigIK":"Rig IK",
    "Scene_Pattern_RigFold":"Rig Fold",
    "Scene_Pattern_RigGradientTexture":"Rig Gradient Texture",
    "Scene_Pattern_RigCurveGuide":"Rig Curve Guide",
    "Scene_Pattern_RigRivet":"Rig Rivet",
    "Scene_Pattern_RigRivetFromFace":"Rig Rivet From Face",
    "Scene_Pattern_RigRopeRoll":"Rig Rope Roll",
    "Scene_Pattern_RigRopeStraight":"Rig Rope Straight",
    "Scene_Pattern_RigSpline":"Rig Spline",
    "Scene_Pattern_RigFollicles":"Rig Follicles",
    "Scene_Pattern_RigSlideSurface":"Rig Slide Surface",
    "Scene_Pattern_RigSlideSurfaceFunc":"Rig Slide Surface Func",
    "Scene_Pattern_RigSlideSurfaceFnc":"Rig Slide Surface Fnc",
 




    "Scene_Pattern_SwitchIKFK":"Switch IK/FK",
    "Scene_Pattern_SwitchIKFKNew":"Switch IK/FK New",
    "Scene_Pattern_SwitchSpace":"Switch Space",
    "Scene_Pattern_SwitchVisibility":"Switch Visibility",


    "Scene_Pattern_ToolMatchPairs":"Tool Match Pairs",
    "Scene_Pattern_ToolMeshVertex":"Tool Mesh Vertex",

    "Scene_Pattern_SkinJointToNearestComponent":"Skin joint to nearest component",

   


    




    "Scene_Pattern_SplineCurveFromObjs":"Spline CurveFromObjs",
    "Scene_Pattern_SplineControlFromObjs":"Spline Controls From Objs",
    "Scene_Pattern_SpaceSwitch":"Space Switch",    
    "Scene_Pattern_VisibilitySwitch":"Visibility Switch",      
    #"Scene_Pattern_Drivenkey":"Driven Key",        
    "Scene_Pattern_Rivet":"Rivet",    
    "Scene_Pattern_GradientTexture":"Gradient Texture",
    "Scene_Pattern_RopeStraight":"Rope Straight",
    "Scene_Pattern_RopeRoll":"Rope Roll",     
    "Scene_Pattern_CreateIK":"Create IK",
    "Scene_Pattern_ReplacePath":"Replace Path",    
    "Scene_Pattern_SplineRig":"Spline Rig",

}


ITEMS_PATTERN = {"items":{},"order":[]}
ITEMS = {}
sceneData = {}

_PATTERN_RENAMES = {
    "Scene_Pattern_RigAutoFnc": ("Scene_Pattern_RigAutoSkirtFnc", "Rig Auto Fnc", "Rig Auto Skirt Fnc"),
    "Scene_Pattern_RigAutoSkirt_": ("Scene_Pattern_RigAutoSkirtFunc", "Auto Skirt_", "Auto Skirt Func"),
    "Scene_Pattern_RigSlideSurface_": ("Scene_Pattern_RigSlideSurfaceFunc", "Rig Slide Surface_", "Rig Slide Surface Func"),
}


def _upgrade_pattern_names(entries, dataFolder):
    changed = False
    for entry in entries:
        old_name = entry.get("moduleName")
        rename = _PATTERN_RENAMES.get(old_name)
        if not rename:
            continue
        new_name, old_label, new_label = rename
        entry["moduleName"] = new_name
        old_path = entry.get("path", "")
        if old_path and os.path.basename(old_path) == old_name + ".json":
            new_path = os.path.join(os.path.dirname(old_path), new_name + ".json")
            if old_name == "Scene_Pattern_RigAutoFnc" and os.path.isfile(old_path):
                # Keep existing data accessible; do not overwrite another JSON.
                if not os.path.exists(new_path):
                    os.rename(old_path, new_path)
                    entry["path"] = new_path
            else:
                entry["path"] = new_path
        for field in ("title", "name"):
            if entry.get(field) == old_label:
                entry[field] = new_label
        changed = True
    if changed:
        NLTA_General.writeJsonFile(os.path.join(dataFolder, "ScenePatternData.json"), entries)
    return entries


def _capture_pattern_python(module, exporter, settings):
    previous_open = module.__dict__.get("open")
    had_open = "open" in module.__dict__
    captured = []

    class _MemoryOutput(io.StringIO):
        def close(self):
            if not self.closed:
                captured.append(self.getvalue())
            super().close()

    def _intercept_open(file, mode="r", *args, **kwargs):
        try:
            basename = os.path.basename(os.fspath(file))
            basename = os.fsdecode(basename)
        except TypeError:
            basename = ""
        if (basename.startswith("Python_") and basename.endswith(".py")
                and ("w" in mode or "x" in mode) and "b" not in mode):
            return _MemoryOutput()
        base_open = previous_open if had_open else builtins.open
        return base_open(file, mode, *args, **kwargs)

    module.__dict__["open"] = _intercept_open
    try:
        result = exporter(settings)
    finally:
        if had_open:
            module.__dict__["open"] = previous_open
        else:
            module.__dict__.pop("open", None)

    if not result:
        raise RuntimeError("ExportPython returned no result")
    if len(captured) != 1:
        raise RuntimeError(
            "ExportPython must write exactly one Python source via open(); captured {}".format(
                len(captured)))
    return captured[0]


def _label_export_data(source, function_name):
    """Keep one recipient-facing data note above the exported data."""
    import ast
    import re

    # Remove generic labels and comments about internal storage.
    lines = [
        line for line in source.splitlines()
        if not (line.lstrip().startswith("#") and (
            re.fullmatch(r"#\s*[A-Za-z0-9_]+\s+data", line.strip(), re.I)
            or any(term in line.lower() for term in (
                "scene data", "scenedata", "scenepatterndata",
                "scene-pattern data", "scene-pattern settings"))
        ))
    ]
    tree = ast.parse("\n".join(lines) + "\n")
    assignments = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(isinstance(target, ast.Name) and target.id.endswith("_DATA")
                for target in (node.targets if isinstance(node, ast.Assign)
                               else [node.target]))
    ]
    note = "# {} data".format(function_name)
    if assignments:
        index = min(assignments) - 1
        indent = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
        lines.insert(index, indent + note)
    else:
        lines.insert(0, note)
    result = "\n".join(lines) + "\n"
    if ast.dump(ast.parse(result)) != ast.dump(tree):
        raise ValueError("Export comments must not alter executable code")
    return result


def _batch_pattern_entrypoint(source):
    """Unwrap a standalone guarded main() when embedding it in a batch stage."""
    import ast
    import textwrap

    tree = ast.parse(source)
    guarded = [
        node for node in tree.body if isinstance(node, ast.If)
        and not node.orelse
        and ast.unparse(node.test) in (
            '__name__ == "__main__"', "__name__ == '__main__'")
        and len(node.body) == 1 and ast.unparse(node.body[0]) == "main()"
    ]
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "main"]
    if len(tree.body) == 2 and len(functions) == 1 and len(guarded) == 1:
        # The standalone main() may contain multiline string literals and
        # source-preserving comments. Dedenting may silently change those
        # literals, so unwrapping is only a lossless optimization.
        lines = source.splitlines()
        main = functions[0]
        if not main.body:
            raise ValueError("Cannot export an empty pattern main()")
        start = main.body[0].lineno - 1
        body = textwrap.dedent("\n".join(lines[start:main.end_lineno])).strip("\n")
        try:
            unchanged = ast.dump(ast.parse(body), include_attributes=False) == ast.dump(
                ast.Module(body=main.body, type_ignores=[]), include_attributes=False)
        except SyntaxError:
            unchanged = False
        if unchanged:
            return body + "\n"
        # Safe fallback: keep the local main() definition inside this pattern
        # stage and replace only its __name__ guard with a direct main() call.
        # Each batch stage has an isolated scope, so main() names do not clash.
        lines[guarded[0].lineno - 1:guarded[0].end_lineno] = ["main()"]
        preserved = "\n".join(lines) + "\n"
        compile(preserved, "<scene-pattern-stage>", "exec")
        return preserved

    # Older exports without a single main() retain their original code.
    lines = source.splitlines()
    for node in reversed(guarded):
        lines[node.lineno - 1:node.end_lineno] = ["main()"]
    return "\n".join(lines) + "\n"


def _indent_pattern_source(source, prefix):
    """Indent a standalone script without changing multi-line literal contents."""
    import ast
    import io
    import tokenize

    original = ast.parse(source)
    string_lines = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.STRING and token.start[0] < token.end[0]:
            # Interior and closing literal lines are already part of the
            # string token. Indenting them changes the literal's value.
            string_lines.update(range(token.start[0] + 1, token.end[0] + 1))
    indented = "\n".join(
        line if line_number in string_lines or not line.strip() else prefix + line
        for line_number, line in enumerate(source.splitlines(), 1)) + "\n"
    # Compare the stage body against the original script, not merely compile().
    nested = ast.parse("def _scene_batch_stage():\n" + indented).body[0]
    if ast.dump(ast.Module(body=nested.body, type_ignores=[]), include_attributes=False) != ast.dump(
            original, include_attributes=False):
        raise ValueError("Embedding the pattern changed its executable instructions")
    return indented


def _compact_export_calls(source):
    """Put multi-line Maya command statements on one line without losing comments."""
    import ast
    import io
    import tokenize

    tree = ast.parse(source)
    lines = source.splitlines()
    commented = {
        token.start[0] for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    }
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return)):
            continue
        if node.end_lineno <= node.lineno:
            continue
        if not any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                   and isinstance(child.func.value, ast.Name)
                   and child.func.value.id == "cmds" for child in ast.walk(node)):
            continue
        if any(number in commented for number in range(node.lineno, node.end_lineno + 1)):
            continue
        unparsed = ast.unparse(node)
        if "\n" in unparsed:
            continue
        first, last = node.lineno - 1, node.end_lineno - 1
        if lines[first][:node.col_offset].strip() or lines[last][node.end_col_offset:].strip():
            continue
        candidates.append((first, last, lines[first][:node.col_offset] + unparsed))
    for first, last, line in sorted(candidates, reverse=True):
        lines[first:last + 1] = [line]
    result = "\n".join(lines) + "\n"
    if ast.dump(ast.parse(source)) != ast.dump(ast.parse(result)):
        raise ValueError("Formatting Maya calls changed executable code")
    return result


def _compact_export_spacing(source):
    """Allow at most one empty line outside multi-line string literals."""
    import ast
    import io
    import tokenize

    protected = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.STRING and token.start[0] != token.end[0]:
            protected.update(range(token.start[0], token.end[0] + 1))
    lines, blanks = [], 0
    for line_number, line in enumerate(source.splitlines(), 1):
        if line.strip():
            # Trailing whitespace belongs to multi-line string contents.
            lines.append(line if line_number in protected else line.rstrip())
            blanks = 0
        elif line_number in protected or blanks == 0:
            lines.append("")
            blanks += 1
    result = "\n".join(lines).rstrip("\n") + "\n"
    if ast.dump(ast.parse(source)) != ast.dump(ast.parse(result)):
        raise ValueError("Export spacing changed executable code")
    return result


def OpenScenePatternExportFolder(folder, *args):
    if not os.path.isdir(folder):
        cmds.warning("Scene Export: folder not found: " + folder)
        return
    if hasattr(os, "startfile"):
        os.startfile(os.path.normpath(folder))
    else:
        subprocess.Popen(["xdg-open", folder])


def _scene_pattern_ordinal(number, ordinal=True):
    """Generate an English order suffix for each exported module type."""
    cardinal = (
        "zero", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
    ordinals = (
        "zeroth", "first", "second", "third", "fourth", "fifth", "sixth",
        "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth",
        "thirteenth", "fourteenth", "fifteenth", "sixteenth",
        "seventeenth", "eighteenth", "nineteenth")
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty",
            "seventy", "eighty", "ninety")
    tens_ordinals = ("", "", "twentieth", "thirtieth", "fortieth",
                     "fiftieth", "sixtieth", "seventieth", "eightieth",
                     "ninetieth")
    if number < 20:
        return (ordinals if ordinal else cardinal)[number]
    if number < 100:
        quotient, remainder = divmod(number, 10)
        return (tens[quotient] + "_" + _scene_pattern_ordinal(remainder, ordinal)
                if remainder else (tens_ordinals if ordinal else tens)[quotient])
    for base, label in ((1000000000, "billion"), (1000000, "million"),
                        (1000, "thousand"), (100, "hundred")):
        if number >= base:
            quotient, remainder = divmod(number, base)
            prefix = _scene_pattern_ordinal(quotient, False) + "_" + label
            return (prefix + "_" + _scene_pattern_ordinal(remainder, ordinal)
                    if remainder else prefix + ("th" if ordinal else ""))
    raise ValueError(number)


def ExportScenePatternBatch(dataFolder, level, *args):
    index_path = os.path.join(dataFolder, "ScenePatternData.json")
    if not os.path.isfile(index_path):
        cmds.warning("Scene Batch Export: data file does not exist: " + index_path)
        return None
    entries = _upgrade_pattern_names(NLTA_General.readJsonFile(index_path) or [], dataFolder)
    if not isinstance(entries, list):
        raise ValueError("ScenePatternData.json must contain a list: " + index_path)
    if not entries:
        cmds.warning("Scene Batch Export: there are no patterns in " + index_path)
        return None

    ordered = sorted(enumerate(entries), key=lambda pair: (int(pair[1].get("order", 0)), pair[0]))
    scripts, issues = [], []

    for position, (_, entry) in enumerate(ordered, 1):
        module_name = entry.get("moduleName", "")
        if module_name == "Scene_Pattern_Note":
            continue
        try:
            if not module_name:
                raise ValueError("missing moduleName")
            module = NLTA_General.LoadModule(module_name)
            exporter = getattr(module, "ExportPython", None)
            if module_name == "Scene_Pattern_Delete" and not callable(exporter):
                # A cached legacy modules/ copy has no exporter; use modulesNew.
                import importlib.util
                source = os.path.join(scenePatternFolder, module_name + ".py")
                spec = importlib.util.spec_from_file_location("_scene_export_" + module_name, source)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                exporter = module.ExportPython
            if not callable(exporter):
                raise ValueError("module has no ExportPython()")

            settings = dict(entry)
            settings["sceneDataPath"] = dataFolder
            if module_name in ("Scene_Pattern_RigAutoSkirt", "Scene_Pattern_RigAutoSkirtFunc", "Scene_Pattern_RigAutoSkirtFnc"):
                settings["_batch_export_from_saved"] = True

            script = _capture_pattern_python(module, exporter, settings)
            if not script.strip():
                raise ValueError("ExportPython generated an empty script")
            compile(script, module_name + ".py", "exec")
            if any(line.lstrip().startswith("from __future__ import ")
                   for line in script.splitlines()):
                raise ValueError("cannot merge a script containing a __future__ import")
            item_id = str(entry.get("id", "")).strip()
            scripts.append((module_name, item_id, script))
            print("[Scene Batch Export] captured {} (id={})".format(module_name, item_id))
        except Exception as exc:
            issues.append("{}: {}: {}".format(position, module_name, exc))

    if not scripts:
        cmds.warning("Scene Batch Export: no standalone scripts generated")
        for issue in issues:
            print("[Scene Batch Export] " + issue)
        return None

    output = os.path.join(dataFolder, "Python_ScenePatternData_{}{}.py".format(
        "UpLevel" if level == "UpLevel" else "Current",
        "_PARTIAL" if issues else ""))
    parts = ["def main():\n", "    import maya.cmds as cmds\n\n"]
    stages = []
    used_names = set()
    type_counts = {}

    for position, (module_name, item_id, script) in enumerate(scripts, 1):
        short_name = module_name
        if short_name.startswith("Scene_Pattern_"):
            short_name = short_name[len("Scene_Pattern_"):]
        type_counts[module_name] = type_counts.get(module_name, 0) + 1
        occurrence = type_counts[module_name]
        # First instance keeps the module name. Add an ordinal from second onward.
        raw_name = (short_name if occurrence == 1 else "{}_{}".format(
            short_name.rstrip("_"), _scene_pattern_ordinal(occurrence)))
        function_name = "".join(
            ch if ch.isascii() and (ch.isalnum() or ch == "_") else "_"
            for ch in raw_name)
        if not function_name or function_name[0].isdigit():
            function_name = "_" + function_name
        original_name = function_name
        unique_index = 2
        while function_name in used_names:
            function_name = "{}_{}".format(original_name, unique_index)
            unique_index += 1
        used_names.add(function_name)
        stages.append(function_name)

        script = _label_export_data(_batch_pattern_entrypoint(script), function_name)
        parts.append("    def {}():\n".format(function_name))
        parts.append(_indent_pattern_source(script.lstrip("\ufeff").rstrip("\n") + "\n",
                                            "        "))
        parts.append("\n")

    parts.append("    # Build the patterns in order.\n")
    for function_name in stages:
        parts.append("    {}()\n".format(function_name))
    parts.append('\n\nif __name__ == "__main__":\n    main()\n')

    original = "".join(parts)
    try:
        combined = _compact_export_spacing(_compact_export_calls(original))
    except (ValueError, SyntaxError) as exc:
        # Compact formatting is optional; never lose a valid batch script
        # merely because a whitespace-only optimization was unsafe.
        compile(original, output, "exec")
        print("[Scene Batch Export] safe unformatted fallback: {}".format(exc))
        combined = original
    compile(combined, output, "exec")
    temporary = output + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(combined)
        os.replace(temporary, output)
    finally:
        if os.path.isfile(temporary):
            os.remove(temporary)

    print("[Scene Batch Export] {} patterns -> {}".format(len(scripts), output))
    if issues:
        print("[Scene Batch Export] INCOMPLETE ({} missing):".format(len(issues)))
        for issue in issues:
            print("  - " + issue)
        cmds.warning("Scene Batch Export: PARTIAL ({} exported, {} missing). See Script Editor.".format(
            len(scripts), len(issues)))
    else:
        cmds.warning("Scene Batch Export: {} patterns exported".format(len(scripts)))
    return output


def CreateUI(data):
    global upList
    global currentList
    def GetModuleName(ui,*arr):
        label = cmds.menuItem(ui, q=True, label=True)
        return(next(k for k, v in patterns.items() if v == label))

    def ModifyData(data):
        global titleFlags, layoutFlags, buttonFlags, inputFlags
        titleFlags = data.get('titleFlags', {})
        layoutFlags = data.get('layoutFlags', {})
        buttonFlags = data.get('buttonFlags', {})
        inputFlags = data.get('inputFlags', {})
    ModifyData(data) 

    for key in patterns:
        if cmds.window(key, exists=True):
            cmds.deleteUI(key)

    titles, buttons, inputs = [], [], []
    parent = data['parent']
    layoutTempt = cmds.rowColumnLayout(data["module"],parent=parent)#*
    cmds.rowColumnLayout(layoutTempt,edit=True,**layoutFlags)
    titles.append(cmds.textField(text=data['title'],editable=False))    

    cmds.rowColumnLayout(nc=1)
    cmds.textField(text="Project Functions",editable=False)
    cmds.rowColumnLayout(nc=2)#<
    projectFunctionsList = cmds.rowColumnLayout(numberOfColumns=4,width=420)
    cmds.setParent("..")
    cmds.rowColumnLayout(nc=1)
    buttons.append(cmds.button(label="+",bgc=(0.0, 0.4, 0.0),width=40,c=partial(CreateFunction,projectPath,projectFunctionsList)))
    cmds.setParent("..")#>
    cmds.setParent("..")
    FunctionsLoad(projectPath,projectFunctionsList)

    cmds.rowColumnLayout(nc=1)
    cmds.rowColumnLayout(nc=1)

    patternsUI = cmds.optionMenu(width=460)
    for key, value in patterns.items():
        cmds.menuItem(label=value)
    cmds.setParent("..")
    cmds.rowColumnLayout(nc=2)
    buttons.append(cmds.button("AddUpItem",label="Up Level",width=230))
    buttons.append(cmds.button("AddCurrentItem",label="Current",width=230))
    cmds.setParent("..")
    cmds.rowColumnLayout(nc=2)
    upExportButton = cmds.button(label="Export Up Py", width=230,
                                 c=partial(ExportScenePatternBatch, upDataFolder, "UpLevel"))
    buttons.append(upExportButton)
    cmds.popupMenu(parent=upExportButton, button=3)
    cmds.menuItem(label="Open Folder",
                  c=partial(OpenScenePatternExportFolder, upDataFolder))
    currentExportButton = cmds.button(label="Export Current Py", width=230,
                                      c=partial(ExportScenePatternBatch, currentDataFolder, "Current"))
    buttons.append(currentExportButton)
    cmds.popupMenu(parent=currentExportButton, button=3)
    cmds.menuItem(label="Open Folder",
                  c=partial(OpenScenePatternExportFolder, currentDataFolder))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2)#<
    # UP LIST
    cmds.rowColumnLayout(numberOfColumns=1)
    cmds.scrollLayout(horizontalScrollBarThickness=4,h=650,width=240)
    upList = cmds.rowColumnLayout(numberOfColumns=1)
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
    # CURRENT LIST
    cmds.rowColumnLayout(numberOfColumns=1)
    cmds.scrollLayout(horizontalScrollBarThickness=4,h=650,width=240)
    currentList = cmds.rowColumnLayout(numberOfColumns=1)
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")#>

    cmds.button("AddCurrentItem",edit=True,c=partial(
        AddNewItem,
        patternsUI,
        currentDataFolder,
        currentList,
    ))

    cmds.button("AddUpItem",edit=True,c=partial(
        AddNewItem,
        patternsUI,
        upDataFolder,
        upList,
    ))
      
    for title in titles:
        cmds.textField(title,edit=True,**titleFlags)
    for button in buttons:
        cmds.button(button,edit=True,**buttonFlags)
    for input_ in inputs:
        if cmds.objectTypeUI(input_) == 'textField':
            cmds.textField(input_,edit=True,**inputFlags)
        if cmds.objectTypeUI(input_) == 'intField':
            cmds.intField(input_,edit=True,**inputFlags)

    SceneLoad(currentList,currentDataFolder)
    SceneLoad(upList,upDataFolder)

def SceneLoad(ui,folderPath, *arr):
    filePath = folderPath+"/ScenePatternData.json"
    if not os.path.exists(filePath):
        NLTA_General.writeJsonFile(filePath, [])
    dataTemp = _upgrade_pattern_names(NLTA_General.readJsonFile(filePath) or [], folderPath)
    NLTA_UI.ClearUI(ui)
    for item in sorted(dataTemp, key=lambda x: x["order"]):
        moduleName = item.get("moduleName")
        if (not isinstance(moduleName, str)
                or not moduleName.startswith("Scene_Pattern_")
                or not moduleName.replace("_", "").isalnum()):
            cmds.warning("SceneLoad: invalid pattern name; saved record kept")
            continue
        moduleFile = os.path.join(scenePatternFolder, moduleName + ".py")
        if not os.path.isfile(moduleFile):
            cmds.warning("SceneLoad: missing module " + moduleName + "; saved record kept")
            continue
        AddItem(moduleName,folderPath,ui,item)

def FunctionsLoad(folder,ui,*arr):
    if folder:
        NLTA_UI.ClearUI(ui)
        fileArrays = NLTA_General.GetFiles(folder,"py")
        if fileArrays:
            for fileTemp in fileArrays:
                btn = cmds.button(label=fileTemp.split("_")[-1],width=105,height=30,c=partial(NLTA_General.RunScriptFile,folder+fileTemp+'.py'),parent=ui)
                popup = cmds.popupMenu(parent=btn)
                cmds.menuItem(label="Edit File", parent=popup,c=partial(NLTA_General.OpenSublime,folder+fileTemp+'.py'))

def AddNewItem(patternsUI,dataFolder,listUI,*arr):
    patternText = cmds.optionMenu(patternsUI,query=True,value=True)
    moduleName = next((k for k, v in patterns.items() if v == patternText), None)
    AddItem(moduleName,dataFolder,listUI,{})


def RunScenePatternItem(moduleName, dataFolder, itemID, *args):
    """Run the selected Scene Pattern from its current saved JSON record."""
    indexPath = os.path.join(dataFolder, "ScenePatternData.json")
    if not os.path.isfile(indexPath):
        raise ValueError("Scene Run: ScenePatternData.json not found: " + indexPath)
    entries = NLTA_General.readJsonFile(indexPath) or []
    if not isinstance(entries, list):
        raise ValueError("Scene Run: ScenePatternData.json must contain a list")
    record = next((entry for entry in entries if entry.get("id") == itemID), None)
    if record is None:
        raise ValueError("Scene Run: saved pattern ID not found: " + str(itemID))
    if record.get("moduleName") != moduleName:
        raise ValueError("Scene Run: module mismatch for pattern " + str(itemID))
    module = NLTA_General.LoadModule(moduleName)
    run = getattr(module, "Run", None)
    if not callable(run):
        raise ValueError("Scene Run: {} does not implement Run()".format(moduleName))
    settings = dict(record)
    settings["sceneDataPath"] = dataFolder
    print("[Scene Run] {} id={} from {}".format(moduleName, itemID, record.get("path")))
    return run(settings)


def AddItem(moduleName,dataFolder,ui,data,*arr):
    global sceneData

    def OpenItem(defaultSetting,*arr):
        module.Form(defaultSetting)

    def ChangeOrder(orderUI,data,dataFile,*arr):
        value = cmds.intField(orderUI,query=True,value=True)
        NLTA_General.JsonUpdateByID({
            "id":data["id"],
            "path":dataFile,
            "values":{
                "order":value
            }
        })

    def DeleteItem(ui,path, *arr):
        cmds.deleteUI(ui)
        itemID = sceneData[ui]['id']
        sceneDatas = NLTA_General.readJsonFile(path) or []        
        del sceneData[ui]        
        returnData = []
        for data in sceneDatas:
            if data.get('id') != itemID:
                returnData.append(data)
        NLTA_General.writeJsonFile(path,returnData)

    def ChangeNote(noteUI,defaultSetting,dataFile,*arr):
        value = cmds.scrollField(noteUI,query=True,text=True)
        NLTA_General.JsonUpdateByID({
            "id":defaultSetting["id"],
            "path":dataFile,
            "values":{
                "name":value
            }
        })

    def ChangeLevel(ui, dataFile, *arr):
        item_id = sceneData[ui]["id"]
        source_folder = os.path.dirname(dataFile)
        target_folder = (currentDataFolder
                         if os.path.normcase(os.path.abspath(source_folder)) ==
                         os.path.normcase(os.path.abspath(upDataFolder))
                         else upDataFolder)
        target_file = os.path.join(target_folder, "ScenePatternData.json")
        source_items = NLTA_General.readJsonFile(dataFile) or []
        target_items = (NLTA_General.readJsonFile(target_file) or []
                        if os.path.isfile(target_file) else [])
        entry = next((item for item in source_items if item.get("id") == item_id), None)
        if entry is None:
            cmds.warning("Scene Change Level: module not found in source data")
            return
        if any(item.get("id") == item_id for item in target_items):
            cmds.warning("Scene Change Level: duplicate module ID in destination")
            return

        moved = dict(entry)
        old_path = moved.get("path", "")
        new_path = ""
        if old_path:
            filename = os.path.basename(os.path.normpath(old_path))
            new_path = os.path.join(target_folder, filename)
            occupied = {os.path.normcase(os.path.abspath(item["path"]))
                        for item in target_items if item.get("path")}
            stem, ext = os.path.splitext(filename)
            number = 2
            while (os.path.normcase(os.path.abspath(new_path)) in occupied
                   or os.path.exists(new_path)):
                new_path = os.path.join(target_folder, "{}_{}{}".format(stem, number, ext))
                number += 1
            moved["path"] = new_path

        copied = False
        if old_path and os.path.isfile(old_path):
            os.makedirs(target_folder, exist_ok=True)
            try:
                shutil.copy2(old_path, new_path)
            except OSError:
                if os.path.exists(new_path):
                    os.remove(new_path)
                raise
            copied = True
        elif old_path:
            cmds.warning("Scene Change Level: JSON not saved yet: " + old_path)

        try:
            NLTA_General.writeJsonFile(target_file, target_items + [moved])
            NLTA_General.writeJsonFile(
                dataFile, [item for item in source_items if item.get("id") != item_id])
        except Exception:
            NLTA_General.writeJsonFile(dataFile, source_items)
            NLTA_General.writeJsonFile(target_file, target_items)
            if copied:
                os.remove(new_path)
            raise

        # Keep a shared source JSON, including paths referenced by the other level.
        if copied:
            old_key = os.path.normcase(os.path.abspath(old_path))
            source_key = os.path.normcase(os.path.abspath(source_folder))
            remaining = [item for item in source_items if item.get("id") != item_id]
            referenced = any(
                os.path.normcase(os.path.abspath(item["path"])) == old_key
                for item in remaining + target_items if item.get("path"))
            if os.path.dirname(old_key) == source_key and not referenced:
                try:
                    os.remove(old_path)
                except OSError as exc:
                    cmds.warning("Scene Change Level: old JSON could not be removed: " + str(exc))

        sceneData[ui]["path"] = moved.get("path", "")
        sceneData[ui]["sceneDataPath"] = target_folder
        SceneLoad(upList, upDataFolder)
        SceneLoad(currentList, currentDataFolder)


    module = NLTA_General.LoadModule(moduleName)
    dataFile =  dataFolder + "/ScenePatternData.json"

    if data!= {}: 
        defaultSetting = data
    else:        
        defaultSetting = module.DefaultSetting(dataFolder)
        NLTA_General.JsonAdd({
            "path":dataFile,
            "values":defaultSetting
        })

    defaultSetting["sceneDataPath"] = dataFolder
    defaultSetting["SceneLoadFunction"] = SceneLoad
    defaultSetting["SceneLoadUI"] = ui
    if moduleName != "Scene_Pattern_Note":
        itemUI = cmds.rowColumnLayout(numberOfColumns=5,parent=ui)
        cmds.button(label="->",c=partial(RunScenePatternItem,moduleName,dataFolder,defaultSetting["id"]),bgc=(0.0, 0.4, 0.0),width=25,height=25)    
        textShow = cmds.button(label=defaultSetting['name'],c=partial(OpenItem,defaultSetting),width=125)
        orderUI = cmds.intField(value=defaultSetting['order'],width=30)
        cmds.button(label="X",c=partial(DeleteItem,itemUI,dataFile),width=25,bgc=(0.4, 0.0, 0.0))
        cmds.button(label="<->",c=partial(ChangeLevel,itemUI,dataFile),width=25,bgc=(0.0, 0.3, 0.3))
        cmds.intField(orderUI,cc=partial(ChangeOrder,orderUI,defaultSetting,dataFile),ec=partial(ChangeOrder,orderUI,defaultSetting,dataFile),edit=True)    
        cmds.setParent('..')
    else: 
        itemUI = cmds.rowColumnLayout(numberOfColumns=4,parent=ui)
        cmds.textField(text="###",width=25)
        textShow = cmds.scrollField(text=defaultSetting['name'],width=125,height=25)
        orderUI = cmds.intField(value=defaultSetting['order'],width=30)
        cmds.button(label="X",c=partial(DeleteItem,itemUI,dataFile),width=25,bgc=(0.4, 0.0, 0.0))
        cmds.intField(orderUI,cc=partial(ChangeOrder,orderUI,defaultSetting,dataFile),ec=partial(ChangeOrder,orderUI,defaultSetting,dataFile),edit=True)   
        cmds.scrollField(textShow,cc=partial(ChangeNote,textShow,defaultSetting,dataFile),ec=partial(ChangeNote,textShow,defaultSetting,dataFile),edit=True,height=50) 
        cmds.setParent('..')
    sceneData[itemUI] = defaultSetting


def CreateFunction(folder,ui, *args):
    result = cmds.promptDialog(
        title='Create Python File',
        message='File Name:',
        button=['OK', 'Cancel'],
        defaultButton='OK',
        cancelButton='Cancel',
        dismissString='Cancel'
    )
    if result != 'OK':
        return
    fileName = cmds.promptDialog(q=True, text=True).strip()
    if not fileName:
        cmds.warning("Please enter a file name.")
        return
    if not fileName.endswith(".py"):
        fileName += ".py"
    if not os.path.exists(folder):
        os.makedirs(folder)
    filePath = os.path.join(folder, fileName)
    if not os.path.exists(filePath):
        with open(filePath, "w") as f:
            f.write(
'''# -*- coding: utf-8 -*-

def Run(*args):
    pass
'''
            )
    NLTA_General.OpenSublime(filePath)
    FunctionsLoad(folder,ui)
    return filePath

