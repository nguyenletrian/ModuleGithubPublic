import os
import re
import json
import pprint
import runpy
import ast
import io
import tokenize
import inspect
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import maya.api.OpenMaya as om

import NLTA_General


STATE = {"top": {}, "rows": [], "list": None, "data": None}
DEFAULT_CONTROL = {"refV": 0.5, "minDistance": 0.2, "maxDistance": 1.5, "startAngle": 10.0}
EXTRA_SCRIPT_PREFIX = "Scene_Pattern_RigAutoSkirt_"


def DefaultSetting(path, *args):
    module_name = os.path.splitext(os.path.basename(__file__))[0]
    return {
        "ext": "json", "path": os.path.join(path, module_name + ".json"),
        "moduleName": module_name, "order": 0, "title": "Auto Skirt",
        "name": "Auto Skirt", "id": datetime.now().strftime("%Y%m%d%H%M%S"),
    }


def _data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    if not entry or not entry.get("path"):
        raise ValueError("AutoSkirt: ScenePatternData.json has no path for this pattern")
    return os.path.normpath(entry["path"])


def _initial():
    return {
        "name": "AutoSkirt", "group": "RigUtil", "pelvis": "Pelvis",
        "control": "Pelvis_IK", "masterAttr": "autoSkirt",
        "masterDefault": 1.1, "axis": "rotateZ", "targetSuffix": "_Target",
        "equatorU": 0.5, "items": [],
    }


def _get_data(data):
    path = _data_path(data)
    if not os.path.isfile(path):
        return _initial()
    saved = NLTA_General.readJsonFile(path)
    if not isinstance(saved, dict):
        return _initial()
    out = _initial()
    out.update(saved)
    return out


def _pick_single(widget, *args):
    selection = cmds.ls(selection=True, objectsOnly=True) or []
    if len(selection) != 1:
        cmds.warning("AutoSkirt: select exactly one Maya object")
        return
    cmds.textField(widget, edit=True, text=selection[0])


def _pick_controls(widget, *args):
    selection = cmds.ls(selection=True, objectsOnly=True) or []
    if not selection:
        cmds.warning("AutoSkirt: select one or more FK controls")
        return
    cmds.scrollField(widget, edit=True, text="\n".join(dict.fromkeys(selection)))


def _extra_scripts_folder():
    module_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(module_dir, "..", "SceneExtraFunction"))


def _extra_script_files():
    directory = _extra_scripts_folder()
    if not os.path.isdir(directory):
        return {}
    scripts = {}
    for filename in sorted(os.listdir(directory)):
        if not filename.startswith(EXTRA_SCRIPT_PREFIX) or not filename.endswith(".py"):
            continue
        label = filename[len(EXTRA_SCRIPT_PREFIX):-3]
        path = os.path.join(directory, filename)
        if label and os.path.isfile(path):
            scripts[label] = path
    return scripts


def _run_extra_script(*args):
    menu = STATE["top"].get("extraScripts")
    if not menu:
        cmds.warning("AutoSkirt: Sphere Scripts menu is not available")
        return
    selected = cmds.optionMenu(menu, query=True, value=True)
    script = _extra_script_files().get(selected)
    if not script:
        cmds.warning("AutoSkirt: sphere script not found: {} in {}".format(
            selected, _extra_scripts_folder()))
        return
    print("AutoSkirt: running {}".format(script))
    try:
        runpy.run_path(script, run_name="__main__")
    except Exception as exc:
        cmds.warning("AutoSkirt: {} failed: {}".format(selected, exc))
        raise


def _line_field(parent, label, initial, picker=True):
    cmds.rowLayout(parent=parent, numberOfColumns=3,
                   adjustableColumn=2, columnWidth3=(105, 160, 55))
    cmds.text(label=label, align="left")
    widget = cmds.textField(text=str(initial))
    if picker:
        cmds.button(label="Pick", command=partial(_pick_single, widget))
    else:
        cmds.text(label="")
    cmds.setParent("..")
    return widget


def _add_row(parent, record=None):
    record = record or {}
    raw_items = record.get("joints", [])
    if isinstance(raw_items, str):
        raw_items = [line.strip() for line in raw_items.splitlines() if line.strip()]
    settings = {}
    for index, joint in enumerate(raw_items):
        refs = record.get("refV", [])
        ranges = record.get("distanceRanges", [])
        starts = record.get("startAngles", [])
        dmin, dmax = ranges[index] if index < len(ranges) else (0.2, 1.5)
        settings[joint] = {
            "refV": float(refs[index]) if index < len(refs) else 0.5,
            "minDistance": float(dmin), "maxDistance": float(dmax),
            "startAngle": float(starts[index]) if index < len(starts) else 10.0,
        }
    row = {"settings": settings}
    frame = cmds.frameLayout(parent=parent, label="Pose Reader", collapsable=True,
                             marginHeight=5, marginWidth=5)
    column = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    row["frame"] = frame
    row["id"] = _line_field(column, "Reader ID", record.get("id", "Knee{}".format(len(STATE["rows"]) + 1)), False)
    row["sphere"] = _line_field(column, "NURBS Sphere", record.get("sphere", ""))
    row["target"] = _line_field(column, "Knee Target", record.get("target", ""))
    row["follow"] = _line_field(
        column, "Sphere Follow",
        record.get("follow", STATE.get("defaultFollow", "Pelvis"))
    )
    row["control"] = _line_field(
        column, "Master Control",
        record.get("control", STATE.get("defaultControl", "Pelvis_IK"))
    )
    cmds.rowLayout(parent=column, numberOfColumns=3, adjustableColumn=2,
                   columnWidth3=(105, 155, 76))
    cmds.text(label="FK Controls", align="left")
    row["controls"] = cmds.scrollField(text="\n".join(raw_items), height=75, wordWrap=False)
    cmds.button(label="Pick All", command=partial(_pick_controls, row["controls"]))
    cmds.setParent("..")
    cmds.rowLayout(parent=column, numberOfColumns=2)
    cmds.button(label="Edit Control Settings (Live)", width=235,
                command=partial(_edit_settings, row))
    cmds.button(label="Remove Reader", width=125,
                command=partial(_remove_row, row))
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
    STATE["rows"].append(row)
    return row


def _remove_row(row, *args):
    if row in STATE["rows"]:
        STATE["rows"].remove(row)
    if cmds.layout(row["frame"], exists=True):
        cmds.deleteUI(row["frame"])


def _controls(row):
    raw = cmds.scrollField(row["controls"], query=True, text=True)
    names = [name.strip() for name in raw.splitlines() if name.strip()]
    if not names or len(set(names)) != len(names):
        raise ValueError("AutoSkirt: each reader needs unique FK controls")
    return names


def _settings(row, control):
    if control not in row["settings"]:
        row["settings"][control] = dict(DEFAULT_CONTROL)
    return row["settings"][control]


def _read_ui():
    top = STATE["top"]
    if not top:
        raise RuntimeError("AutoSkirt: form is not open")
    data = {
        "name": cmds.textField(top["name"], query=True, text=True).strip(),
        "group": cmds.textField(top["group"], query=True, text=True).strip(),
        "masterAttr": cmds.textField(top["masterAttr"], query=True, text=True).strip(),
        "masterDefault": cmds.floatField(top["masterDefault"], query=True, value=True),
        "axis": cmds.optionMenu(top["axis"], query=True, value=True),
        "targetSuffix": cmds.textField(top["targetSuffix"], query=True, text=True).strip(),
        "equatorU": cmds.floatField(top["equatorU"], query=True, value=True),
        "items": [],
    }
    for row in STATE["rows"]:
        names = _controls(row)
        values = [_settings(row, ctrl) for ctrl in names]
        for ctrl, v in zip(names, values):
            if not 0 <= v["refV"] <= 1:
                raise ValueError("{}: refV must be in [0,1]".format(ctrl))
            if not 0 <= v["minDistance"] < v["maxDistance"]:
                raise ValueError("{}: minDistance must be >= 0 and < maxDistance".format(ctrl))
            if not 0 <= v["startAngle"] <= 180:
                raise ValueError("{}: startAngle must be in [0,180]".format(ctrl))
        data["items"].append({
            "id": cmds.textField(row["id"], query=True, text=True).strip(),
            "sphere": cmds.textField(row["sphere"], query=True, text=True).strip(),
            "target": cmds.textField(row["target"], query=True, text=True).strip(),
            "follow": cmds.textField(row["follow"], query=True, text=True).strip(),
            "control": cmds.textField(row["control"], query=True, text=True).strip(),
            "joints": names,
            "refV": [v["refV"] for v in values],
            "distanceRanges": [(v["minDistance"], v["maxDistance"]) for v in values],
            "startAngles": [v["startAngle"] for v in values],
        })
    if not data["items"]:
        raise ValueError("AutoSkirt: add at least one pose reader")
    return data


def _save(data, *args):
    value = _read_ui()
    NLTA_General.writeJsonFile(_data_path(data), value)
    return value


def _scene_root(value):
    return value["name"] + "_System"


def _meta_from_scene(value):
    root = _scene_root(value)
    if not cmds.objExists(root) or not cmds.attributeQuery("patternData", node=root, exists=True):
        return None
    encoded = cmds.getAttr(root + ".patternData")
    try:
        saved = json.loads(encoded)
    except (TypeError, ValueError):
        return None
    return saved if isinstance(saved, dict) else None


def _write_scene_meta(root, meta):
    if not cmds.attributeQuery("patternData", node=root, exists=True):
        cmds.addAttr(root, longName="patternData", dataType="string")
    cmds.setAttr(root + ".patternData", json.dumps(meta, ensure_ascii=False), type="string")


def _apply_live(row, control, *args):
    val = _settings(row, control)
    widgets = row.get("editorWidgets", {}).get(control)
    if not widgets:
        return
    for key, widget in widgets.items():
        val[key] = float(cmds.floatSliderGrp(widget, query=True, value=True))
    if not 0 <= val["minDistance"] < val["maxDistance"]:
        return

    system_name = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    meta = _meta_from_scene({"name": system_name})
    if not meta:
        return
    item_id = cmds.textField(row["id"], query=True, text=True).strip()
    reference = meta.get("refs", {}).get(item_id, {}).get(control)
    if not reference:
        return
    ref_transform, ref_shape = reference
    if not cmds.objExists(ref_transform) or not cmds.objExists(ref_shape):
        cmds.warning("AutoSkirt: missing scene follicle for {}".format(control))
        return
    cmds.setAttr(ref_shape + ".parameterV", val["refV"])
    cmds.setAttr(ref_transform + ".minDistance", val["minDistance"])
    cmds.setAttr(ref_transform + ".maxDistance", val["maxDistance"])
    cmds.setAttr(ref_transform + ".raiseStartAngle", val["startAngle"])
    snapshot = meta.get("data", {})
    for item in snapshot.get("items", []):
        if item.get("id") != item_id or control not in item.get("joints", []):
            continue
        index = item["joints"].index(control)
        item["refV"][index] = val["refV"]
        item["distanceRanges"][index] = (val["minDistance"], val["maxDistance"])
        item["startAngles"][index] = val["startAngle"]
        break
    meta["data"] = snapshot
    _write_scene_meta(_scene_root({"name": system_name}), meta)


def _finish_edit(data, row, window, *args):
    for ctrl in _controls(row):
        _apply_live(row, ctrl)
    _save(data)
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    row.pop("editorWidgets", None)


def _edit_settings(row, *args):
    data = STATE["data"]
    try:
        controls = _controls(row)
    except ValueError as exc:
        cmds.warning(str(exc))
        return
    window = "NLTA_AutoSkirt_Editor"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    window = cmds.window(window, title="AutoSkirt - Live Settings", widthHeight=(620, 640))
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8)
    cmds.text(label="Drag sliders to update the built rig immediately", align="left")
    scrolling = cmds.scrollLayout(childResizable=True, height=555)
    columns = cmds.columnLayout(adjustableColumn=True)
    row["editorWidgets"] = {}
    system_name = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    meta = _meta_from_scene({"name": system_name})
    reader_id = cmds.textField(row["id"], query=True, text=True).strip()
    for control in controls:
        values = _settings(row, control)
        nodes = meta.get("refs", {}).get(reader_id, {}).get(control) if meta else None
        if nodes and all(cmds.objExists(node) for node in nodes):
            transform, shape = nodes
            values.update({
                "refV": float(cmds.getAttr(shape + ".parameterV")),
                "minDistance": float(cmds.getAttr(transform + ".minDistance")),
                "maxDistance": float(cmds.getAttr(transform + ".maxDistance")),
                "startAngle": float(cmds.getAttr(transform + ".raiseStartAngle")),
            })
        cmds.frameLayout(parent=columns, label=control, collapsable=True, marginHeight=4)
        cmds.columnLayout(adjustableColumn=True)
        fields = {}
        for key, label, lo, hi, field_hi in (
            ("refV", "Ref V", 0.0, 1.0, 1.0),
            ("minDistance", "Min Distance", 0.0, 2.0, 100.0),
            ("maxDistance", "Max Distance", 0.01, 5.0, 1000.0),
            ("startAngle", "Start Angle", 0.0, 180.0, 180.0),
        ):
            fields[key] = cmds.floatSliderGrp(
                label=label, field=True, minValue=lo, maxValue=hi,
                fieldMinValue=lo, fieldMaxValue=field_hi,
                value=values[key], precision=3,
            )
        row["editorWidgets"][control] = fields
        for widget in fields.values():
            cmds.floatSliderGrp(widget, edit=True,
                                dragCommand=partial(_apply_live, row, control),
                                changeCommand=partial(_apply_live, row, control))
        cmds.setParent("..")
        cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.button(label="Save Settings / Close", height=36,
                command=partial(_finish_edit, data, row, window))
    cmds.showWindow(window)


def Load(data, listUI, *args):
    children = cmds.layout(listUI, query=True, childArray=True) or []
    for child in children:
        if cmds.control(child, exists=True) or cmds.layout(child, exists=True):
            cmds.deleteUI(child)
    STATE["top"] = {}
    STATE["rows"] = []
    STATE["list"] = listUI
    STATE["data"] = data
    config = _get_data(data)
    STATE["defaultFollow"] = config.get("pelvis", "Pelvis")
    STATE["defaultControl"] = config.get("control", "Pelvis_IK")

    cmds.frameLayout(parent=listUI, label="AutoSkirt Settings", collapsable=True,
                     marginHeight=5, marginWidth=5)
    top_col = cmds.columnLayout(adjustableColumn=True)
    for key, label in (
        ("name", "System Name"), ("group", "Contain"),
        ("masterAttr", "Master Attribute"), ("targetSuffix", "FK Target Suffix"),
    ):
        STATE["top"][key] = _line_field(top_col, label, config.get(key, ""),
                                         key == "group")
    cmds.rowLayout(numberOfColumns=2, parent=top_col)
    cmds.text(label="Master Default")
    STATE["top"]["masterDefault"] = cmds.floatField(value=float(config.get("masterDefault", 1.1)), precision=3)
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=2, parent=top_col)
    cmds.text(label="Equator U")
    STATE["top"]["equatorU"] = cmds.floatField(value=float(config.get("equatorU", 0.5)), minValue=0, maxValue=1)
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=2, parent=top_col)
    cmds.text(label="Rotate Axis")
    STATE["top"]["axis"] = cmds.optionMenu()
    for axis in ("rotateX", "rotateY", "rotateZ"):
        cmds.menuItem(label=axis)
    cmds.optionMenu(STATE["top"]["axis"], edit=True, value=config.get("axis", "rotateZ"))
    cmds.setParent("..")

    cmds.rowLayout(parent=top_col, numberOfColumns=3,
                   adjustableColumn=2, columnWidth3=(105, 155, 76))
    cmds.text(label="Sphere Scripts", align="left")
    scripts_menu = cmds.optionMenu()
    STATE["top"]["extraScripts"] = scripts_menu
    names = _extra_script_files()
    if names:
        for name in names:
            cmds.menuItem(parent=scripts_menu, label=name)
    else:
        cmds.menuItem(parent=scripts_menu, label="(No scripts found)")
    cmds.button(label="Create", width=72, command=_run_extra_script)
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")

    items_holder = cmds.columnLayout(parent=listUI, adjustableColumn=True)
    STATE["holder"] = items_holder
    saved_items = config.get("items", [])
    if isinstance(saved_items, dict):
        saved_items = [dict(entry, id=key) for key, entry in saved_items.items()]
    for item in saved_items:
        _add_row(items_holder, item)
    if not saved_items:
        _add_row(items_holder)


def _add_empty(*args):
    _add_row(STATE["holder"])


def _get_built_data(value):
    meta = _meta_from_scene(value)
    if not meta:
        return value
    result = json.loads(json.dumps(value))
    refs = meta.get("refs", {})
    for item in result["items"]:
        for index, control in enumerate(item["joints"]):
            nodes = refs.get(item["id"], {}).get(control)
            if not nodes:
                continue
            ref_transform, ref_shape = nodes
            if not cmds.objExists(ref_transform) or not cmds.objExists(ref_shape):
                raise ValueError("AutoSkirt export: missing reference for {}".format(control))
            item["refV"][index] = float(cmds.getAttr(ref_shape + ".parameterV"))
            item["distanceRanges"][index] = (
                float(cmds.getAttr(ref_transform + ".minDistance")),
                float(cmds.getAttr(ref_transform + ".maxDistance")),
            )
            item["startAngles"][index] = float(cmds.getAttr(ref_transform + ".raiseStartAngle"))
            item["equatorU"] = float(cmds.getAttr(ref_shape + ".parameterU"))
    for item in result["items"]:
        master_control = item.get("control", result.get("control", ""))
        if not master_control:
            continue
        master_plug = master_control + "." + result["masterAttr"]
        if cmds.objExists(master_plug):
            item["masterDefault"] = float(cmds.getAttr(master_plug))
    return result


def Run(data, *args):
    configuration = _get_data(data)
    if not configuration.get("items"):
        raise ValueError("AutoSkirt: no saved readers in " + _data_path(data))
    result = AutoSkirt(configuration)
    refs = {}
    for item_id, item_nodes in result["items"].items():
        refs[item_id] = {}
        for control, (ref_transform, _) in item_nodes["follicles"].items():
            shapes = cmds.listRelatives(ref_transform, shapes=True,
                                        fullPath=True, type="follicle") or []
            if len(shapes) != 1:
                raise RuntimeError("AutoSkirt: cannot resolve follicle shape for " + ref_transform)
            refs[item_id][control] = [ref_transform, shapes[0]]
    _write_scene_meta(result["root"], {"data": configuration, "refs": refs})
    cmds.select(clear=True)
    return result


def _run_from_form(data, *args):
    _save(data)
    return Run(data)


def _clean_export_source(source):
    lines = source.splitlines(keepends=True)
    docs = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                val = node.body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    docs.update(range(node.body[0].lineno, node.body[0].end_lineno + 1))
    comments = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            comments.setdefault(token.start[0], []).append(token.start[1])
    for i, line in enumerate(lines, 1):
        if i in docs:
            lines[i-1] = "\n"
        elif i in comments:
            lines[i-1] = line[:min(comments[i])].rstrip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", "".join(lines)).strip() + "\n"


def _capture_nurbs_sphere(transform):
    shape = _nurbs_shape(transform)
    selection = om.MSelectionList()
    selection.add(shape)
    surface = om.MFnNurbsSurface(selection.getDagPath(0))
    if surface.isTrimmedSurface:
        raise ValueError("AutoSkirt cannot export trimmed NURBS surface: " + shape)
    cvs = [[float(p.x), float(p.y), float(p.z), float(p.w)]
           for p in surface.cvPositions(om.MSpace.kObject)]
    if len(cvs) != surface.numCVsInU * surface.numCVsInV:
        raise RuntimeError("AutoSkirt: invalid CV count on " + shape)
    return {
        "source": transform,
        "name": transform.rsplit("|", 1)[-1].replace(":", "_"),
        "degree_u": int(surface.degreeInU),
        "degree_v": int(surface.degreeInV),
        "form_u": int(surface.formInU),
        "form_v": int(surface.formInV),
        "knots_u": list(map(float, surface.knotsInU())),
        "knots_v": list(map(float, surface.knotsInV())),
        "uv_domain_u": list(map(float, surface.knotDomainInU)),
        "uv_domain_v": list(map(float, surface.knotDomainInV)),
        "cvs": cvs,
        "rational": any(abs(point[3] - 1.0) > 1e-10 for point in cvs),
        "world_matrix": list(map(float, cmds.xform(
            transform, query=True, worldSpace=True, matrix=True))),
        "rotate_pivot_world": list(map(float, cmds.xform(
            transform, query=True, worldSpace=True, rotatePivot=True))),
        "scale_pivot_world": list(map(float, cmds.xform(
            transform, query=True, worldSpace=True, scalePivot=True))),
        "visible": bool(cmds.getAttr(transform + ".visibility")),
        "shape_visible": bool(cmds.getAttr(shape + ".visibility")),
    }


def _restore_nurbs_spheres(snapshots, linear_unit):
    if cmds.currentUnit(query=True, linear=True) != linear_unit:
        raise RuntimeError("AutoSkirt Sphere unit mismatch: exported in {}, current scene {}".format(
            linear_unit, cmds.currentUnit(query=True, linear=True)))
    created = {}
    for item in snapshots:
        original = item["source"]
        short_name = item["name"]
        if cmds.objExists(original):
            _nurbs_shape(original)
            created[original] = original
            continue
        if cmds.objExists(short_name):
            raise RuntimeError("Sphere name already used by an unexpected object: " + short_name)
        transform = cmds.createNode("transform", name=short_name)
        selection = om.MSelectionList()
        selection.add(transform)
        parent_object = selection.getDependNode(0)
        points = [om.MPoint(*point) for point in item["cvs"]]
        surface = om.MFnNurbsSurface()
        surface_obj = surface.create(
            points, item["knots_u"], item["knots_v"], item["degree_u"],
            item["degree_v"], item["form_u"], item["form_v"],
            item["rational"], parent_object)
        shape = om.MFnDagNode(surface_obj).fullPathName()
        shape = cmds.rename(shape, short_name + "Shape")
        cmds.xform(transform, worldSpace=True, matrix=item["world_matrix"])
        cmds.xform(transform, worldSpace=True,
                   rotatePivot=item["rotate_pivot_world"], preserve=True)
        cmds.xform(transform, worldSpace=True,
                   scalePivot=item["scale_pivot_world"], preserve=True)
        cmds.setAttr(transform + ".visibility", item["visible"])
        cmds.setAttr(shape + ".visibility", item["shape_visible"])
        new_selection = om.MSelectionList()
        new_selection.add(shape)
        new_surface = om.MFnNurbsSurface(new_selection.getDagPath(0))
        if (int(new_surface.degreeInU), int(new_surface.degreeInV),
                int(new_surface.formInU), int(new_surface.formInV)) != (
                item["degree_u"], item["degree_v"], item["form_u"], item["form_v"]):
            cmds.warning("AutoSkirt: rebuilt NURBS degrees/forms differ: " + transform)
        actual_domain = tuple(new_surface.knotDomainInU) + tuple(new_surface.knotDomainInV)
        saved_domain = tuple(item["uv_domain_u"]) + tuple(item["uv_domain_v"])
        if any(abs(a - b) > 1e-7 for a, b in zip(actual_domain, saved_domain)):
            cmds.warning("AutoSkirt: rebuilt NURBS U/V domain differs: " + transform)
        created[original] = transform
        print("[AutoSkirt Sphere] {} -> {}".format(original, transform))
    return created


def _run_exported_auto_skirt(config, spheres, linear_unit):
    resolved = _restore_nurbs_spheres(spheres, linear_unit)
    entries = config["items"].values() if isinstance(config["items"], dict) else config["items"]
    for entry in entries:
        entry["sphere"] = resolved[entry["sphere"]]
    return AutoSkirt(config)


def _format_export_payload(value):
    """Format each saved item and sphere dictionary on one physical line."""
    if isinstance(value, dict):
        result = ["{"]
        for key, child in value.items():
            if key == "items" and isinstance(child, (list, tuple)):
                result.append("    " + repr(key) + ": [")
                result.extend("        " + repr(item) + "," for item in child)
                result.append("    ],")
            elif key == "items" and isinstance(child, dict):
                result.append("    " + repr(key) + ": {")
                result.extend("        " + repr(name) + ": " + repr(item) + ","
                              for name, item in child.items())
                result.append("    },")
            else:
                result.append("    " + repr(key) + ": " + repr(child) + ",")
        result.append("}")
        return "\n".join(result)
    if isinstance(value, list):
        return "[\n" + "\n".join("    " + repr(item) + "," for item in value) + "\n]"
    return repr(value)


def ExportPython(data, *args):
    config = _get_data(data) if data.get("_batch_export_from_saved") else _save(data)
    payload = _get_built_data(config)
    used_spheres = list(dict.fromkeys(item["sphere"] for item in payload["items"]))
    snapshots = [_capture_nurbs_sphere(sphere) for sphere in used_spheres]
    scene_unit = cmds.currentUnit(query=True, linear=True)

    functions = (_nurbs_shape, _restore_nurbs_spheres, _run_exported_auto_skirt,
                 _linear_ramp, _follicle, _read_items, _validate, AutoSkirt)
    source_tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions))
    # Remove verbose docstrings without changing any rig-generation commands.
    for node in ast.walk(source_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    node.body.pop(0)
    ast.fix_missing_locations(source_tree)
    original_builder = ast.unparse(source_tree)
    indented_builder = "\n".join(
        "    " + line if line.strip() else ""
        for line in original_builder.splitlines()
    )

    data_literal = _format_export_payload(payload)
    spheres_literal = _format_export_payload(snapshots)
    data_literal = data_literal.replace("\n", "\n    ")
    spheres_literal = spheres_literal.replace("\n", "\n    ")
    script = (
        "def main():\n"
        "    import re\n"
        "    import maya.cmds as cmds\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    # Saved rig records (each item dictionary is one line).\n"
        "    AUTO_SKIRT_DATA = " + data_literal + "\n\n"
        "    # Original source NURBS sphere CV and transform snapshots.\n"
        "    AUTO_SKIRT_SPHERES = " + spheres_literal + "\n"
        "    AUTO_SKIRT_UNIT = " + repr(scene_unit) + "\n\n"
        + "    # Original Maya-only build helpers and AutoSkirt implementation.\n"
        + indented_builder
        + "\n\n    # Build the saved rig only when main() is explicitly run.\n"
        + "    _run_exported_auto_skirt(AUTO_SKIRT_DATA, AUTO_SKIRT_SPHERES, AUTO_SKIRT_UNIT)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in script:
        script = script.replace("\n\n\n", "\n\n")

    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(_data_path(data)), filename)
    with open(output, "w", encoding="utf-8") as out:
        out.write(script)
    print("AutoSkirt Export: " + output)
    return output


def OpenExportFolder(data, *args):
    directory = os.path.dirname(_data_path(data))
    if os.path.isdir(directory):
        os.startfile(directory)
    else:
        cmds.warning("AutoSkirt: export directory does not exist: " + directory)


def Form(data, *args):
    ui = NLTA_General.LoadModule("Scene_Form").Create(data)
    buttons = ui["buttonUI"]
    list_ui = ui["listUI"]
    cmds.rowColumnLayout(parent=buttons, numberOfColumns=4)
    cmds.button(label="Add", width=80, command=_add_empty)
    cmds.button(label="Save", width=80, command=partial(_save, data))
    cmds.button(label="Run", width=80, command=partial(_run_from_form, data))
    export_button = cmds.button(label="Export Py", width=95,
                                command=partial(ExportPython, data))
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", command=partial(OpenExportFolder, data))
    cmds.setParent("..")
    Load(data, list_ui)





def _nurbs_shape(transform):
    shapes = cmds.listRelatives(
        transform, shapes=True, noIntermediate=True,
        fullPath=True, type="nurbsSurface"
    ) or []
    if len(shapes) != 1:
        raise ValueError("Expected one NURBS surface shape under {!r}".format(transform))
    return shapes[0]


def _linear_ramp(node):
    """Ensure the remap ramp is linear rather than relying on Maya defaults."""
    for index in (0, 1):
        slot = "{}.value[{}]".format(node, index)
        cmds.setAttr(slot + ".value_Position", float(index))
        cmds.setAttr(slot + ".value_FloatValue", float(index))
        cmds.setAttr(slot + ".value_Interp", 1)  # 1 = linear


def _follicle(surface_shape, prefix, parent, u, v=None, v_source=None):
    follicle_shape = cmds.createNode("follicle", name=prefix + "Shape")
    transform = cmds.listRelatives(follicle_shape, parent=True, fullPath=True)[0]
    transform = cmds.rename(transform, prefix)
    transform = cmds.parent(transform, parent)[0]
    follicle_shape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]

    # Follicle outTranslate is world-space; do not apply parent world matrix twice.
    cmds.setAttr(transform + ".inheritsTransform", 0)
    cmds.connectAttr(surface_shape + ".worldSpace[0]", follicle_shape + ".inputSurface")
    cmds.connectAttr(surface_shape + ".worldMatrix[0]", follicle_shape + ".inputWorldMatrix")
    cmds.connectAttr(follicle_shape + ".outTranslate", transform + ".translate")
    cmds.connectAttr(follicle_shape + ".outRotate", transform + ".rotate")
    cmds.setAttr(follicle_shape + ".parameterU", u)
    if v_source is None:
        cmds.setAttr(follicle_shape + ".parameterV", v)
    else:
        cmds.connectAttr(v_source, follicle_shape + ".parameterV")
    return transform, follicle_shape


def _read_items(data):
    """Return [(item_id, config), ...]; dictionary or list of named items."""
    raw_items = data["items"]
    if isinstance(raw_items, dict):
        items = list(raw_items.items())
    elif isinstance(raw_items, (tuple, list)):
        items = [(item["id"], item) for item in raw_items]
    else:
        raise TypeError("data['items'] must be a dict or a list of named dicts")
    if not items:
        raise ValueError("data['items'] needs at least one item")
    item_names = set()
    for item_id, spec in items:
        if not isinstance(item_id, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", item_id):
            raise ValueError("Item ID {!r} must be a simple Maya-safe identifier".format(item_id))
        if item_id in item_names:
            raise ValueError("Duplicate item ID: {}".format(item_id))
        item_names.add(item_id)
        if not isinstance(spec, dict):
            raise TypeError("Item {!r} must be a dict".format(item_id))
    return items


def _validate(data):
    """Check everything possible before making any nodes or connections."""
    if not isinstance(data, dict):
        raise TypeError("AutoSkirt(data) expects a dictionary")

    name = data.get("name", "AutoSkirt")
    if not isinstance(name, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise ValueError("name must be a simple Maya-safe identifier")

    group = data.get("group", "RigUtil")
    master_attr = data.get("masterAttr", "autoSkirt")
    master_default = float(data.get("masterDefault", 1.1))
    if not 0 <= master_default <= 2:
        raise ValueError("masterDefault must be between 0 and 2")
    if not isinstance(master_attr, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", master_attr):
        raise ValueError("masterAttr must be a simple attribute name")

    root_name = name + "_System"
    if cmds.objExists(root_name):
        raise RuntimeError("AutoSkirt setup already exists: {}".format(root_name))
    if not cmds.objExists(group):
        raise ValueError("Missing Maya group: {}".format(group))

    processed = []
    destinations = set()
    for item_id, item in _read_items(data):
        sphere = item["sphere"]
        target = item["target"]
        follow = item.get("follow") or data.get("pelvis")
        control = item.get("control") or data.get("control")
        if not follow:
            raise ValueError("{}: Sphere Follow is required".format(item_id))
        if not control:
            raise ValueError("{}: Master Control is required".format(item_id))
        for obj in (sphere, target, follow, control):
            if not cmds.objExists(obj):
                raise ValueError("{}: missing Maya object: {}".format(item_id, obj))
        master_plug = "{}.{}".format(control, master_attr)
        if cmds.attributeQuery(master_attr, node=control, exists=True):
            if cmds.getAttr(master_plug, type=True) not in (
                "double", "float", "doubleLinear", "doubleAngle"
            ):
                raise TypeError("{}: master attribute must be numeric: {}".format(item_id, master_plug))
        item_default = float(item.get("masterDefault", master_default))
        if not 0 <= item_default <= 2:
            raise ValueError("{}: masterDefault must be between 0 and 2".format(item_id))

        axis = item.get("axis", data.get("axis", "rotateZ"))
        if axis not in ("rotateX", "rotateY", "rotateZ"):
            raise ValueError("{}: axis must be rotateX/Y/Z".format(item_id))
        suffix = item.get("targetSuffix", data.get("targetSuffix", "_FK_Target"))
        equator_u = float(item.get("equatorU", data.get("equatorU", 0.5)))
        if not 0 <= equator_u <= 1:
            raise ValueError("{}: equatorU must be within [0,1]".format(item_id))

        joints = list(item["joints"])
        ref_v = list(item["refV"])
        distances = list(item["distanceRanges"])
        starts = list(item["startAngles"])
        count = len(joints)
        if count == 0 or any(len(values) != count for values in (ref_v, distances, starts)):
            raise ValueError(
                "{}: joints ({}), refV ({}), distanceRanges ({}), startAngles ({}) "
                "must have the SAME nonzero length".format(
                    item_id, count, len(ref_v), len(distances), len(starts)
                )
            )
        if len(set(joints)) != count:
            raise ValueError("{}: duplicate joint names within the same item".format(item_id))

        explicit = item.get("destinations")
        if explicit is not None and len(explicit) != count:
            raise ValueError("{}: destinations must have the same length as joints".format(item_id))
        resolved = []
        for index, joint in enumerate(joints):
            plug = explicit[index] if explicit is not None else "{}{}.{}".format(joint, suffix, axis)
            if not cmds.objExists(plug):
                raise ValueError("{}[{}]: destination does not exist: {}".format(item_id, index, plug))
            resolved.append(plug)
            destinations.add(plug)

            v = float(ref_v[index])
            if not 0 <= v <= 1:
                raise ValueError("{}: refV[{}] outside [0,1]".format(item_id, index))
            try:
                dmin, dmax = map(float, distances[index])
            except (TypeError, ValueError):
                raise ValueError("{}: distanceRanges[{}] must be a (min,max) pair".format(item_id, index))
            if dmin < 0 or dmax <= dmin:
                raise ValueError("{}: distanceRanges[{}] needs 0 <= min < max".format(item_id, index))
            start_angle = float(starts[index])
            if not 0 <= start_angle <= 180:
                raise ValueError("{}: startAngles[{}] outside [0,180]".format(item_id, index))

        processed.append({
            "id": item_id,
            "sphere": sphere,
            "surface": _nurbs_shape(sphere),
            "target": target,
            "follow": follow,
            "control": control,
            "masterPlug": master_plug,
            "masterDefault": item_default,
            "axis": axis,
            "equatorU": equator_u,
            "joints": joints,
            "refV": [float(x) for x in ref_v],
            "distanceRanges": [tuple(map(float, x)) for x in distances],
            "startAngles": [float(x) for x in starts],
            "destinations": resolved,
        })

    for plug in sorted(destinations):
        if cmds.listConnections(plug, source=True, destination=False, plugs=True):
            raise RuntimeError("Destination is already driven; will not overwrite: {}".format(plug))

    return name, group, master_attr, processed


def AutoSkirt(data):
    """Build a NURBS-based auto skirt system from multiple independent items.

    Each item is its own pose reader (sphere + tracking target) and controls any
    number of FK Targets. Shared destinations are combined by MAX, regardless
    of their position in the items' joint arrays.

    Returns {root, master, items, driven}. Does not modify the scene on import.
    """
    name, group, master_attr, items = _validate(data)

    cmds.undoInfo(openChunk=True, chunkName="AutoSkirt")
    try:
        for item in items:
            control = item["control"]
            if not cmds.attributeQuery(master_attr, node=control, exists=True):
                cmds.addAttr(
                    control, longName=master_attr, attributeType="double",
                    min=0, max=2, defaultValue=item["masterDefault"], keyable=True
                )
        system_root = cmds.createNode("transform", name=name + "_System", parent=group)
        result = {
            "root": system_root,
            "master": items[0]["masterPlug"],
            "masters": {},
            "items": {}, "driven": {},
        }

        # Collect contributions across *all* items first, connect each destination only once.
        contributions = {}
        for item in items:
            item_id = item["id"]
            master_plug = item["masterPlug"]
            result["masters"][item_id] = master_plug
            prefix = "{}_{}".format(name, item_id)

            target_group = cmds.createNode(
                "transform", name=prefix + "_TargetGrp", parent=system_root
            )
            target_loc = cmds.createNode(
                "transform", name=prefix + "_TargetLoc", parent=target_group
            )
            loc_shape = cmds.createNode(
                "locator", name=prefix + "_TargetLocShape", parent=target_loc
            )
            cmds.parentConstraint(
                item["target"], target_group, maintainOffset=False,
                name=prefix + "_TargetConstraint"
            )
            cmds.parentConstraint(
                item["follow"], item["sphere"], maintainOffset=True,
                name=prefix + "_SphereConstraint"
            )

            cpos = cmds.createNode("closestPointOnSurface", name=prefix + "_ClosestUV")
            cmds.connectAttr(loc_shape + ".worldPosition[0]", cpos + ".inPosition")
            cmds.connectAttr(item["surface"] + ".worldSpace[0]", cpos + ".inputSurface")

            details = {
                "closestPoint": cpos, "locator": target_loc,
                "outputs": {}, "follicles": {}, "destinations": {},
            }
            result["items"][item_id] = details

            for index, joint in enumerate(item["joints"]):
                base = "{}_{:02d}".format(prefix, index)
                ref_fol, _ = _follicle(
                    item["surface"], base + "_RefFollicle", system_root,
                    item["equatorU"], v=item["refV"][index]
                )
                moving_fol, _ = _follicle(
                    item["surface"], base + "_MovingFollicle", system_root,
                    item["equatorU"], v_source=cpos + ".parameterV"
                )
                details["follicles"][joint] = (ref_fol, moving_fol)

                dmin, dmax = item["distanceRanges"][index]
                cmds.addAttr(ref_fol, longName="minDistance", attributeType="double",
                             min=0, defaultValue=dmin, keyable=True)
                cmds.addAttr(ref_fol, longName="maxDistance", attributeType="double",
                             min=0, defaultValue=dmax, keyable=True)
                cmds.addAttr(ref_fol, longName="raiseStartAngle", attributeType="double",
                             min=0, max=180, defaultValue=item["startAngles"][index],
                             keyable=True)

                distance_node = cmds.createNode("distanceBetween", name=base + "_Distance")
                distance_remap = cmds.createNode("remapValue", name=base + "_DistanceRemap")
                cmds.connectAttr(ref_fol + ".worldMatrix[0]", distance_node + ".inMatrix1")
                cmds.connectAttr(moving_fol + ".worldMatrix[0]", distance_node + ".inMatrix2")
                cmds.connectAttr(distance_node + ".distance", distance_remap + ".inputValue")
                cmds.connectAttr(ref_fol + ".minDistance", distance_remap + ".inputMin")
                cmds.connectAttr(ref_fol + ".maxDistance", distance_remap + ".inputMax")
                _linear_ramp(distance_remap)
                cmds.setAttr(distance_remap + ".outputMin", 1.0)
                cmds.setAttr(distance_remap + ".outputMax", 0.0)

                angle_remap = cmds.createNode("remapValue", name=base + "_AngleRemap")
                angle_clamp = cmds.createNode("clamp", name=base + "_AngleClamp")
                angle_subtract = cmds.createNode(
                    "plusMinusAverage", name=base + "_SubtractStart"
                )
                cmds.connectAttr(cpos + ".parameterU", angle_remap + ".inputValue")
                _linear_ramp(angle_remap)
                cmds.setAttr(angle_remap + ".inputMin", 0.0)
                cmds.setAttr(angle_remap + ".inputMax", 1.0)
                cmds.setAttr(angle_remap + ".outputMin", 0.0)
                cmds.setAttr(angle_remap + ".outputMax", 180.0)
                cmds.connectAttr(angle_remap + ".outValue", angle_clamp + ".inputR")
                cmds.connectAttr(ref_fol + ".raiseStartAngle", angle_clamp + ".minR")
                cmds.setAttr(angle_clamp + ".maxR", 180.0)
                cmds.setAttr(angle_subtract + ".operation", 2)  # subtract
                cmds.connectAttr(angle_clamp + ".outputR", angle_subtract + ".input1D[0]")
                cmds.connectAttr(ref_fol + ".raiseStartAngle", angle_subtract + ".input1D[1]")

                by_distance = cmds.createNode("multiplyDivide", name=base + "_ByDistance")
                by_master = cmds.createNode("multiplyDivide", name=base + "_ByMaster")
                cmds.connectAttr(angle_subtract + ".output1D", by_distance + ".input1X")
                cmds.connectAttr(distance_remap + ".outValue", by_distance + ".input2X")
                cmds.connectAttr(by_distance + ".outputX", by_master + ".input1X")
                cmds.connectAttr(master_plug, by_master + ".input2X")

                output = by_master + ".outputX"
                destination = item["destinations"][index]
                details["outputs"][joint] = output
                details["destinations"][joint] = destination
                contributions.setdefault(destination, []).append(output)

        # Never assume that shared destinations are only front/back, or in fixed indices.
        for dest_index, (destination, inputs) in enumerate(contributions.items()):
            combined = inputs[0]
            for input_index, source in enumerate(inputs[1:], start=1):
                maximum = cmds.createNode(
                    "condition", name="{}_Combine_{:02d}_{:02d}_Max".format(
                        name, dest_index, input_index
                    )
                )
                cmds.setAttr(maximum + ".operation", 3)  # greater or equal
                cmds.connectAttr(combined, maximum + ".firstTerm")
                cmds.connectAttr(source, maximum + ".secondTerm")
                cmds.connectAttr(combined, maximum + ".colorIfTrueR")
                cmds.connectAttr(source, maximum + ".colorIfFalseR")
                combined = maximum + ".outColorR"
            cmds.connectAttr(combined, destination)
            result["driven"][destination] = {
                "sources": list(inputs), "output": combined,
            }

        return result
    finally:
        cmds.undoInfo(closeChunk=True)