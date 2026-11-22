# -*- coding: utf-8 -*-
"""Slide Surface for existing Maya controls. MarkerFK V3 matrix correction."""
import inspect
import os
import pprint
import re
import textwrap
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General

ITEMS = {"rows": [], "list": None}


def DefaultSetting(path, *args):
    module = os.path.splitext(os.path.basename(__file__))[0]
    return {"ext": "json", "path": os.path.join(path, module + ".json"),
            "moduleName": module, "order": 0, "title": "Slide Surface",
            "name": "Slide Surface", "id": datetime.now().strftime("%Y%m%d%H%M%S")}


def _data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    if not entry or not entry.get("path"):
        raise ValueError("Slide Surface: missing pattern data path")
    return os.path.normpath(entry["path"])


def _pick(field, *unused):
    selected = cmds.ls(selection=True, long=True) or []
    if len(selected) != 1:
        cmds.warning("Slide Surface: select one transform or NURBS surface")
        return
    name = selected[0]
    if cmds.nodeType(name) == "nurbsSurface":
        name = (cmds.listRelatives(name, parent=True, fullPath=True) or [name])[0]
    if cmds.nodeType(name) != "transform":
        cmds.warning("Slide Surface: selection is not a transform")
        return
    cmds.textField(field, edit=True, text=name.rsplit("|", 1)[-1])


def _field(parent, label, value, pick=True):
    if pick:
        layout = cmds.rowLayout(numberOfColumns=3, columnWidth3=(97, 210, 43), parent=parent)
    else:
        layout = cmds.rowLayout(numberOfColumns=2, columnWidth2=(97, 253), parent=parent)
    cmds.text(label=label, align="left", parent=layout)
    field = cmds.textField(text=str(value), parent=layout)
    if pick:
        cmds.button(label="Pick", parent=layout, command=partial(_pick, field))
    return field


def _remove_item(row, *unused):
    if row in ITEMS["rows"]:
        ITEMS["rows"].remove(row)
    if cmds.layout(row["ui"], exists=True):
        cmds.deleteUI(row["ui"])


def _remove_control(row, sub, *unused):
    if sub in row["controls"]:
        row["controls"].remove(sub)
    if cmds.layout(sub["ui"], exists=True):
        cmds.deleteUI(sub["ui"])


def _add_control(row, item=None, *unused):
    item = item or {}
    frame = cmds.frameLayout(label="Control " + str(len(row["controls"]) + 1),
                             collapsable=True, collapse=False, parent=row["controlsUI"])
    column = cmds.columnLayout(adjustableColumn=True, parent=frame)
    sub = {"ui": frame}
    sub["control"] = _field(column, "Control", item.get("control", ""))
    sub["parent"] = _field(column, "Hierarchy parent", item.get("parent", ""))
    weights = cmds.rowLayout(numberOfColumns=4, columnWidth4=(83, 73, 94, 73), parent=column)
    cmds.text(label="Parent blend", parent=weights)
    sub["blendWeight"] = cmds.floatField(value=float(item.get("blendWeight", 1.0)),
                                          minValue=0, maxValue=1, precision=3, parent=weights)
    cmds.text(label="Surface follow", parent=weights)
    sub["surfaceFollow"] = cmds.floatField(value=float(item.get("surfaceFollow", 1.0)),
                                            minValue=0, maxValue=1, precision=3, parent=weights)
    cmds.button(label="Remove control", parent=column, command=partial(_remove_control, row, sub))
    row["controls"].append(sub)
    return sub


def _selected_controls(row, *unused):
    selected = cmds.ls(orderedSelection=True, long=True, selection=True) or []
    if not selected:
        cmds.warning("Slide Surface: select controls from root to tip")
        return
    if not cmds.selectPref(query=True, trackSelectionOrder=True):
        cmds.warning("Slide Surface: enable Track Selection Order to preserve selection order")
        return
    parent = (cmds.textField(row["driver"], query=True, text=True).strip()
              if not row["controls"] else
              cmds.textField(row["controls"][-1]["control"], query=True, text=True).strip())
    for obj in selected:
        name = obj.rsplit("|", 1)[-1]
        if cmds.nodeType(obj) != "transform":
            continue
        _add_control(row, {"control": name, "parent": parent})
        parent = name


def Add(listUI, data=None, *unused):
    data = data or {}
    frame = cmds.frameLayout(label="Slide Surface", collapsable=True,
                             collapse=False, parent=listUI)
    column = cmds.columnLayout(adjustableColumn=True, parent=frame)
    row = {"ui": frame, "controls": []}
    row["prefix"] = _field(column, "Prefix", data.get("prefix", "SlideSurface"), False)
    row["surface"] = _field(column, "Surface", data.get("surface", ""))
    row["rootParent"] = _field(column, "Root Parent", data.get("rootParent", ""))
    row["driver"] = _field(column, "Driver", data.get("driver", ""))
    uv = cmds.rowLayout(numberOfColumns=4, columnWidth4=(75, 90, 86, 72), parent=column)
    cmds.text(label="Slide UV", parent=uv)
    row["axis"] = cmds.optionMenu(parent=uv)
    for axis in ("Auto", "U", "V"):
        cmds.menuItem(label=axis, parent=row["axis"])
    cmds.optionMenu(row["axis"], edit=True, value=data.get("axis", "Auto"))
    cmds.text(label="UV margin", parent=uv)
    row["uvMargin"] = cmds.floatField(value=float(data.get("uvMargin", 0.01)),
                                     minValue=0, maxValue=0.48, precision=3, parent=uv)
    cmds.text(label="Existing controls + their actual hierarchy parents", align="left", parent=column)
    row["controlsUI"] = cmds.columnLayout(adjustableColumn=True, parent=column)
    for item in data.get("controls", []):
        _add_control(row, item)
    buttons = cmds.rowLayout(numberOfColumns=3, columnWidth3=(118, 115, 112), parent=column)
    cmds.button(label="+ Selected", parent=buttons, command=partial(_selected_controls, row))
    cmds.button(label="+ Control", parent=buttons, command=lambda *_: _add_control(row))
    cmds.button(label="Remove Item", parent=buttons, command=partial(_remove_item, row))
    ITEMS["rows"].append(row)
    return row


def _ui_data():
    output = []
    for row in ITEMS["rows"]:
        entry = {"prefix": cmds.textField(row["prefix"], query=True, text=True).strip(),
                 "surface": cmds.textField(row["surface"], query=True, text=True).strip(),
                 "rootParent": cmds.textField(row["rootParent"], query=True, text=True).strip(),
                 "driver": cmds.textField(row["driver"], query=True, text=True).strip(),
                 "axis": cmds.optionMenu(row["axis"], query=True, value=True),
                 "uvMargin": cmds.floatField(row["uvMargin"], query=True, value=True),
                 "controls": []}
        for sub in row["controls"]:
            entry["controls"].append({
                "control": cmds.textField(sub["control"], query=True, text=True).strip(),
                "parent": cmds.textField(sub["parent"], query=True, text=True).strip(),
                "blendWeight": cmds.floatField(sub["blendWeight"], query=True, value=True),
                "surfaceFollow": cmds.floatField(sub["surfaceFollow"], query=True, value=True)})
        output.append(entry)
    return output


def Save(data, *unused):
    entries = _ui_data()
    NLTA_General.writeJsonFile(_data_path(data), entries)
    return entries


def Load(data, listUI, *unused):
    for child in cmds.layout(listUI, query=True, childArray=True) or []:
        cmds.deleteUI(child)
    ITEMS["rows"][:] = []
    path = _data_path(data)
    entries = NLTA_General.readJsonFile(path) if os.path.isfile(path) else []
    for entry in entries or []:
        Add(listUI, entry)


def Form(data, *unused):
    layout = NLTA_General.LoadModule("Scene_Form").Create(data)
    ITEMS["list"] = layout["listUI"]
    buttons = cmds.rowLayout(numberOfColumns=4,
                             columnWidth4=(84, 84, 84, 105), parent=layout["buttonUI"])
    cmds.button(label="Add", parent=buttons, command=lambda *_: Add(ITEMS["list"]))
    cmds.button(label="Save", parent=buttons, command=partial(Save, data))
    cmds.button(label="Run", parent=buttons, command=lambda *_: (Save(data), Run(data)))
    export_button = cmds.button(label="Export Py", parent=buttons,
                                command=lambda *_: (Save(data), ExportPython(data)))
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", command=partial(OpenExportFolder, data))
    cmds.setParent("..", menu=True)
    Load(data, ITEMS["list"])
    return layout


def _validate_item(data):
    prefix = str(data.get("prefix", "")).strip()
    root = str(data.get("rootParent", "")).strip()
    driver = str(data.get("driver", "")).strip()
    surface = str(data.get("surface", "")).strip()
    controls = data.get("controls", [])
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", prefix):
        raise ValueError("Slide Surface: Prefix must contain only letters/digits/underscore")
    if not root or not driver or not surface or not isinstance(controls, list) or not controls:
        raise ValueError("Slide Surface: Surface, Root Parent, Driver and Controls are required")
    if data.get("axis", "Auto") not in ("Auto", "U", "V"):
        raise ValueError("Slide Surface: UV axis must be Auto/U/V")
    if not 0 <= float(data.get("uvMargin", 0.01)) < 0.49:
        raise ValueError("Slide Surface: UV margin out of range")
    keys = [str(item.get("control", "")).strip() for item in controls]
    if len(keys) != len(set(keys)) or any(not k for k in keys):
        raise ValueError("Slide Surface: control names must be distinct and nonempty")
    if driver in keys or root in keys:
        raise ValueError("Slide Surface: Root Parent and Driver cannot be corrected controls")
    for index, item in enumerate(controls):
        parent = str(item.get("parent", "")).strip()
        if not parent or parent == keys[index] or (parent not in (root, driver) and parent not in keys[:index]):
            raise ValueError("Slide Surface: hierarchy parent must be Root/Driver or an earlier control")
        for setting in ("blendWeight", "surfaceFollow"):
            if not 0 <= float(item.get(setting, 1.0)) <= 1:
                raise ValueError("Slide Surface: %s must be between 0 and 1" % setting)
    return prefix, root, surface, driver, controls


def BuildSlideSurface(datas):
    """Build MarkerFK V3 correction around EXISTING controls, without creating control/joint chains."""
    import maya.cmds as cmds
    import maya.api.OpenMaya as om

    def unique_node(saved, kind="transform"):
        saved = str(saved).strip()
        matches = cmds.ls(saved, long=True) or []
        if len(matches) != 1:
            leaf = saved.rsplit("|", 1)[-1]
            matches = cmds.ls(leaf, long=True) or []
        matches = [n for n in list(dict.fromkeys(matches))
                   if cmds.nodeType(n) == "transform"]
        if len(matches) != 1:
            raise ValueError("Slide Surface: missing/ambiguous transform: " + saved)
        return matches[0]

    def mmatrix(node):
        return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))

    def setmatrix(plug, matrix):
        cmds.setAttr(plug, *list(matrix), type="matrix")

    def xyz(node):
        return [float(x) for x in cmds.xform(node, query=True,
                                              worldSpace=True, translation=True)]

    def is_ancestor(ancestor, target):
        return target == ancestor or target.startswith(ancestor + "|")

    if not isinstance(datas, list) or not datas:
        raise ValueError("Slide Surface: no saved data")
    configs = []
    used_prefixes = set()
    used_controls = set()

    # Stage: preflight exact inputs and existing hierarchy before editing Maya DAG.
    for data in datas:
        prefix, root_name, surface_name, driver_name, items = _validate_item(data)
        if prefix in used_prefixes:
            raise ValueError("Slide Surface: repeated prefix " + prefix)
        used_prefixes.add(prefix)
        if cmds.objExists(prefix + "_GUIDES_GRP"):
            raise ValueError("Slide Surface already built: " + prefix)
        root = unique_node(root_name)
        driver = unique_node(driver_name)
        surface = unique_node(surface_name)
        shapes = cmds.listRelatives(surface, shapes=True, noIntermediate=True,
                                    fullPath=True, type="nurbsSurface") or []
        if len(shapes) != 1:
            raise ValueError("Slide Surface: expected one non-intermediate NURBS shape on " + surface)
        if not is_ancestor(root, driver):
            raise ValueError("Slide Surface: Root Parent must contain Driver in DAG")
        if data.get("axis", "Auto") == "Auto" and len(items) < 2:
            raise ValueError("Slide Surface: Auto UV requires at least two controls; choose U/V for one")
        nodes = [unique_node(item["control"]) for item in items]
        if len(set(nodes)) != len(nodes) or any(n in used_controls for n in nodes):
            raise ValueError("Slide Surface: duplicate control across module items")
        used_controls.update(nodes)
        for node in nodes:
            if is_ancestor(node, driver) or is_ancestor(node, surface):
                raise ValueError("Slide Surface: a corrected control cannot contain Driver or Surface: " + node)
            leaf = node.rsplit("|", 1)[-1]
            if len(cmds.ls(leaf, long=True) or []) != 1:
                raise ValueError("Slide Surface: each control leaf name must be unique: " + leaf)
        named = {item["control"].strip(): node for item, node in zip(items, nodes)}
        parents, parent_controls, bind_controls = [], [], []
        for item, ctrl in zip(items, nodes):
            if not is_ancestor(root, ctrl):
                raise ValueError("Slide Surface: control must be below Root Parent: " + ctrl)
            original_parent = (cmds.listRelatives(ctrl, parent=True, fullPath=True) or [None])[0]
            if not original_parent:
                raise ValueError("Slide Surface: control has no original DAG parent: " + ctrl)
            chosen = item["parent"].strip()
            parent_ctrl = root if chosen == root_name else driver if chosen == driver_name else named.get(chosen)
            if parent_ctrl is None:
                raise ValueError("Slide Surface: invalid hierarchy parent: " + chosen)
            if not is_ancestor(parent_ctrl, original_parent):
                raise ValueError("Slide Surface: hierarchy input is not an ancestor of " + ctrl)
            candidates = [root, driver] + [n for n in nodes if n != ctrl]
            nearest = max((n for n in candidates if is_ancestor(n, original_parent)),
                          key=lambda n: n.count("|"))
            if nearest != parent_ctrl:
                raise ValueError("Slide Surface: hierarchy parent for %s must be its nearest selected ancestor %s"
                                 % (ctrl, nearest))
            if not cmds.getAttr(ctrl + ".inheritsTransform"):
                raise ValueError("Slide Surface: control must inherit parent transform: " + ctrl)
            parents.append(original_parent)
            parent_controls.append(parent_ctrl)
            bind_controls.append(mmatrix(ctrl))
        configs.append(dict(data=data, prefix=prefix, root=root, driver=driver,
                            shape=shapes[0], nodes=nodes, parents=parents,
                            parent_controls=parent_controls, bind_controls=bind_controls,
                            bind_parents=[mmatrix(p) for p in parents],
                            bind_parent_ctrl=[mmatrix(p) for p in parent_controls]))

    results = []
    for cfg in configs:
        data, prefix, items = cfg["data"], cfg["prefix"], cfg["data"]["controls"]
        root, driver, shape = cfg["root"], cfg["driver"], cfg["shape"]
        nodes = cfg["nodes"]
        tag = lambda i: "%s_%02d" % (prefix, i + 1)
        guide = cmds.createNode("transform", name=prefix + "_GUIDES_GRP")
        refs_group = cmds.createNode("transform", name=prefix + "_BASELINE_GRP", parent=guide)
        rest_group = cmds.createNode("transform", name=prefix + "_REST_GRP", parent=guide)
        loc_group = cmds.createNode("transform", name=prefix + "_LOCATORS_GRP", parent=guide)
        fol_group = cmds.createNode("transform", name=prefix + "_FOLLICLES_GRP", parent=guide)
        cmds.setAttr(rest_group + ".visibility", 0)

        # Stage: sample UV direction using existing control positions.
        probe = cmds.createNode("closestPointOnSurface", name=prefix + "_UV_PROBE")
        cmds.connectAttr(shape + ".worldSpace[0]", probe + ".inputSurface")
        samples = []
        for node in nodes:
            cmds.setAttr(probe + ".inPosition", *xyz(node), type="double3")
            samples.append((float(cmds.getAttr(probe + ".parameterU")),
                            float(cmds.getAttr(probe + ".parameterV"))))
        domain = {}
        for axis in ("U", "V"):
            lo, hi = cmds.getAttr(shape + ".minMaxRange" + axis)[0]
            domain[axis] = (float(lo), float(hi))
            if hi - lo <= 1e-10:
                raise ValueError("Slide Surface: invalid NURBS UV range " + axis)
        du = abs(samples[-1][0] - samples[0][0]) / (domain["U"][1] - domain["U"][0])
        dv = abs(samples[-1][1] - samples[0][1]) / (domain["V"][1] - domain["V"][0])
        axis = data.get("axis", "Auto")
        moving = ("U" if du >= dv else "V") if axis == "Auto" else axis
        if axis == "Auto" and max(du, dv) < 1e-5:
            raise ValueError("Slide Surface: cannot determine UV axis; set U/V manually")
        fixed = "V" if moving == "U" else "U"
        idx = 0 if fixed == "U" else 1
        flo, fhi = domain[fixed]
        fixed_value = max(0., min(1., (sum(s[idx] for s in samples)/len(samples)-flo)/(fhi-flo)))
        posi = cmds.createNode("pointOnSurfaceInfo", name=prefix + "_BIND_POSI")
        cmds.connectAttr(shape + ".worldSpace[0]", posi + ".inputSurface")
        cmds.setAttr(posi + ".parameter" + fixed, flo + (fhi-flo)*fixed_value)
        margin = float(data.get("uvMargin", 0.01))
        lo, hi = domain[moving]
        bind_points = []
        for sample in samples:
            fraction = max(0., min(1., (sample[0 if moving == "U" else 1]-lo)/(hi-lo)))
            fraction = margin + fraction * (1. - 2.*margin)
            cmds.setAttr(posi + ".parameter" + moving, lo + fraction * (hi-lo))
            value = cmds.getAttr(posi + ".position")
            bind_points.append([float(x) for x in (value[0] if len(value) == 1 else value)])
        cmds.delete([probe, posi])

        markers, refs = [], []
        for index, (item, on_surface) in enumerate(zip(items, bind_points)):
            pfx = tag(index)
            # Stage: uniform baseline source; optional per-control blend for module use.
            ref = cmds.spaceLocator(name=pfx + "_Baseline_REF")[0]
            ref = cmds.parent(ref, refs_group)[0]
            cmds.xform(ref, worldSpace=True, translation=on_surface)
            rest = cmds.spaceLocator(name=pfx + "_Rest_REF")[0]
            rest = cmds.parent(rest, rest_group)[0]
            cmds.xform(rest, worldSpace=True, translation=on_surface)
            cmds.addAttr(ref, longName="BlendWeight", attributeType="double", minValue=0,
                         maxValue=1, defaultValue=float(item.get("blendWeight", 1)), keyable=True)
            cmds.addAttr(ref, longName="SurfaceFollow", attributeType="double", minValue=0,
                         maxValue=1, defaultValue=float(item.get("surfaceFollow", 1)), keyable=True)
            pc = cmds.pointConstraint(driver, rest, ref, maintainOffset=True,
                                      name=pfx + "_Baseline_PC")[0]
            aliases = cmds.pointConstraint(pc, query=True, weightAliasList=True)
            if len(aliases) != 2:
                raise RuntimeError("Slide Surface: unexpected reference constraint weights")
            cmds.connectAttr(ref + ".BlendWeight", pc + "." + aliases[0])
            rev = cmds.createNode("reverse", name=pfx + "_Blend_REV")
            cmds.connectAttr(ref + ".BlendWeight", rev + ".inputX")
            cmds.connectAttr(rev + ".outputX", pc + "." + aliases[1])

            driven = cmds.spaceLocator(name=pfx + "_Driven_LOC")[0]
            driven = cmds.parent(driven, loc_group)[0]
            cmds.xform(driven, worldSpace=True, translation=on_surface)
            cmds.pointConstraint(ref, driven, maintainOffset=True, name=pfx + "_Driven_PC")
            dcm = cmds.createNode("decomposeMatrix", name=pfx + "_DCM")
            cmds.connectAttr(driven + ".worldMatrix[0]", dcm + ".inputMatrix")
            cpos = cmds.createNode("closestPointOnSurface", name=pfx + "_CPOS")
            cmds.connectAttr(shape + ".worldSpace[0]", cpos + ".inputSurface")
            cmds.connectAttr(dcm + ".outputTranslate", cpos + ".inPosition")
            fol = cmds.createNode("transform", name=pfx + "_FOL", parent=fol_group)
            fshape = cmds.createNode("follicle", name=pfx + "_FOLShape", parent=fol)
            cmds.connectAttr(shape + ".local", fshape + ".inputSurface")
            cmds.connectAttr(shape + ".worldMatrix[0]", fshape + ".inputWorldMatrix")
            cmds.connectAttr(fshape + ".outTranslate", fol + ".translate")
            cmds.connectAttr(fshape + ".outRotate", fol + ".rotate")
            normalizer = cmds.createNode("setRange", name=pfx + "_UV_RANGE")
            cmds.setAttr(normalizer + ".oldMinX", lo)
            cmds.setAttr(normalizer + ".oldMaxX", hi)
            cmds.setAttr(normalizer + ".minX", margin)
            cmds.setAttr(normalizer + ".maxX", 1.0 - margin)
            cmds.connectAttr(cpos + ".parameter" + moving, normalizer + ".valueX")
            clamp = cmds.createNode("clamp", name=pfx + "_UV_CLAMP")
            cmds.setAttr(clamp + ".minR", margin)
            cmds.setAttr(clamp + ".maxR", 1.0 - margin)
            cmds.connectAttr(normalizer + ".outValueX", clamp + ".inputR")
            cmds.connectAttr(clamp + ".outputR", fshape + ".parameter" + moving)
            cmds.setAttr(fshape + ".parameter" + fixed, fixed_value)
            marker = cmds.spaceLocator(name=pfx + "_Marker")[0]
            marker = cmds.parent(marker, fol, relative=True)[0]
            cmds.setAttr(marker + ".translate", 0, 0, 0, type="double3")
            cmds.setAttr(marker + ".rotate", 0, 0, 0, type="double3")
            markers.append(marker)
            refs.append(ref)

        marker_binds = [mmatrix(marker) for marker in markers]
        # Expected transforms do not read corrected control world matrices.
        expected_worlds = []
        for index, marker in enumerate(markers):
            pfx = tag(index)
            expected = cmds.createNode("multMatrix", name=pfx + "_EXPECTED_WORLD_MM")
            setmatrix(expected + ".matrixIn[0]", cfg["bind_controls"][index] * marker_binds[index].inverse())
            cmds.connectAttr(marker + ".worldMatrix[0]", expected + ".matrixIn[1]")
            expected_worlds.append(expected)

        created = []
        for index, (item, marker) in enumerate(zip(items, markers)):
            pfx = tag(index)
            # Stage: compute virtual parent reference from explicit hierarchy.
            parent_ref = cfg["parent_controls"][index]
            parent_exp = cmds.createNode("multMatrix", name=pfx + "_EXPECTED_PARENT_MM")
            setmatrix(parent_exp + ".matrixIn[0]", cfg["bind_parents"][index] *
                      cfg["bind_parent_ctrl"][index].inverse())
            upstream = next((j for j, node in enumerate(nodes) if node == parent_ref), None)
            if upstream is not None:
                cmds.connectAttr(expected_worlds[upstream] + ".matrixSum", parent_exp + ".matrixIn[1]")
            else:
                cmds.connectAttr(parent_ref + ".worldMatrix[0]", parent_exp + ".matrixIn[1]")
            pinv = cmds.createNode("inverseMatrix", name=pfx + "_EXPECTED_PARENT_INV")
            cmds.connectAttr(parent_exp + ".matrixSum", pinv + ".inputMatrix")
            correction = cmds.createNode("multMatrix", name=pfx + "_CORRECT_MM")
            setmatrix(correction + ".matrixIn[0]", cfg["bind_parents"][index] *
                      marker_binds[index].inverse())
            cmds.connectAttr(marker + ".worldMatrix[0]", correction + ".matrixIn[1]")
            cmds.connectAttr(pinv + ".outputMatrix", correction + ".matrixIn[2]")
            blend = cmds.createNode("blendMatrix", name=pfx + "_FOLLOW_BLEND")
            cmds.connectAttr(correction + ".matrixSum", blend + ".target[0].targetMatrix")
            cmds.connectAttr(refs[index] + ".SurfaceFollow", blend + ".target[0].weight")
            # Stage: insert a neutral group immediately above EXISTING control.
            original = cfg["nodes"][index]
            leaf = original.rsplit("|", 1)[-1]
            live = unique_node(leaf)
            actual_parent = (cmds.listRelatives(live, parent=True, fullPath=True) or [None])[0]
            group = cmds.createNode("transform", name=pfx + "_SlideOffset", parent=actual_parent)
            cmds.parent(live, group, relative=True)
            cmds.connectAttr(blend + ".outputMatrix", group + ".offsetParentMatrix")
            new_bind = mmatrix(unique_node(leaf))
            error = max(abs(float(a)-float(b)) for a, b in zip(new_bind, cfg["bind_controls"][index]))
            if error > 1e-3:
                raise RuntimeError("Slide Surface: control moved at bind (%.6g): %s" % (error, leaf))
            created.append({"control": leaf, "offset": group,
                            "reference": refs[index], "marker": marker,
                            "hierarchyParent": item["parent"]})
        cmds.setAttr(guide + ".visibility", 0)
        results.append({"prefix": prefix, "movingUV": moving, "fixedUV": fixed,
                        "controls": created, "guides": guide})
    return results


def Run(data, *unused):
    records = NLTA_General.readJsonFile(_data_path(data)) or []
    cmds.undoInfo(openChunk=True, chunkName="Scene Pattern Slide Surface")
    try:
        result = BuildSlideSurface(records)
    except Exception:
        cmds.undoInfo(closeChunk=True)
        cmds.undo()
        raise
    cmds.undoInfo(closeChunk=True)
    return result


def ExportPython(data, *unused):
    records = NLTA_General.readJsonFile(_data_path(data)) or []
    if not isinstance(records, list) or not records:
        cmds.warning("Slide Surface: no saved items to export")
        return None
    for record in records:
        _validate_item(record)
    builder = inspect.getsource(BuildSlideSurface).rstrip()
    validator = inspect.getsource(_validate_item).rstrip()
    values = "[\n" + ",\n".join("        " + pprint.pformat(item, width=120, sort_dicts=False).replace("\n", "\n        ")
                                    for item in records) + "\n    ]"
    source = ("def main():\n"
              "    import re\n"
              "    import maya.cmds as cmds\n\n"
              "    # Slide Surface data\n"
              "    SLIDE_SURFACE_DATA = " + values + "\n\n"
              + textwrap.indent(validator, "    ") + "\n\n"
              + textwrap.indent(builder, "    ") + "\n\n"
              "    BuildSlideSurface(SLIDE_SURFACE_DATA)\n\n"
              'if __name__ == "__main__":\n    main()\n')
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(_data_path(data)), filename)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(source)
    return output


def OpenExportFolder(data, *unused):
    folder = os.path.dirname(_data_path(data))
    if hasattr(os, "startfile"):
        os.startfile(folder)
    else:
        cmds.warning("Slide Surface: folder " + folder)
