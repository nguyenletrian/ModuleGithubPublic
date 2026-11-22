# -*- coding: utf-8 -*-
"""Rig Slide Surface: Gragas200 arc spacing with animator FK hierarchy follow."""
import inspect
import os
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
            "moduleName": module, "order": 0, "title": "Rig Slide Surface",
            "name": "Rig Slide Surface", "id": datetime.now().strftime("%Y%m%d%H%M%S")}


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


def _pick_joint_bind(field, *unused):
    selected = cmds.ls(selection=True, long=True) or []
    if not selected or any(cmds.nodeType(node) != "joint" for node in selected):
        cmds.warning("Slide Surface: select one or more joints for Joint Bind")
        return
    names = [node.rsplit("|", 1)[-1] for node in selected]
    cmds.scrollField(field, edit=True, text="\n".join(dict.fromkeys(names)))


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
    line = cmds.rowLayout(numberOfColumns=4, columnWidth4=(55, 198, 45, 55),
                          parent=row["controlsUI"])
    sub = {"ui": line, "parent": str(item.get("parent", "")).strip(),
           "matrixMode": item.get("matrixMode", "Hierarchy" if item.get("parent") else "Auto")}
    cmds.text(label="Control %d" % (len(row["controls"]) + 1), parent=line)
    sub["control"] = cmds.textField(text=item.get("control", ""), parent=line)
    cmds.button(label="Pick", parent=line, command=partial(_pick, sub["control"]))
    cmds.button(label="Remove", parent=line, command=partial(_remove_control, row, sub))
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
        _add_control(row, {"control": name, "parent": parent, "matrixMode": "Auto"})
        parent = name


def Add(listUI, data=None, *unused):
    data = data or {}
    frame = cmds.frameLayout(label="Slide Surface", collapsable=True,
                             collapse=False, parent=listUI)
    column = cmds.columnLayout(adjustableColumn=True, parent=frame)
    row = {"ui": frame, "controls": [], "surfaceSnapshot": data.get("surfaceSnapshot")}
    row["prefix"] = _field(column, "Prefix", data.get("prefix", "SlideSurface"), False)
    row["surface"] = _field(column, "Surface", data.get("surface", ""))
    joints = data.get("jointBind") or []
    if isinstance(joints, str):
        joints = [v.strip() for v in re.split(r"[,;\n]+", joints) if v.strip()]
    joint_row = cmds.rowLayout(numberOfColumns=3, columnWidth3=(97, 210, 43), parent=column)
    cmds.text(label="Joint Bind", align="left", parent=joint_row)
    row["jointBind"] = cmds.scrollField(parent=joint_row, height=63, wordWrap=False,
                                        text="\n".join(joints))
    cmds.button(label="Pick", parent=joint_row, command=partial(_pick_joint_bind, row["jointBind"]))
    row["rootParent"] = _field(column, "Root Parent", data.get("rootParent", ""))
    row["driver"] = _field(column, "Driver", data.get("driver", ""))
    row["contain"] = _field(column, "Contain", data.get("contain", ""))
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
                 "contain": cmds.textField(row["contain"], query=True, text=True).strip(),
                 "controls": []}
        if row.get("surfaceSnapshot"):
            entry["surfaceSnapshot"] = row["surfaceSnapshot"]
        joint_bind = [name.strip() for name in re.split(
            r"[,;\n]+", cmds.scrollField(row["jointBind"], query=True, text=True)) if name.strip()]
        if joint_bind:
            entry["jointBind"] = list(dict.fromkeys(joint_bind))
        for sub in row["controls"]:
            item = {"control": cmds.textField(sub["control"], query=True, text=True).strip()}
            if sub["parent"]:
                item["parent"] = sub["parent"]
            mode = sub["matrixMode"]
            implicit = "Hierarchy" if sub["parent"] else "Auto"
            if mode != implicit:
                item["matrixMode"] = mode
            entry["controls"].append(item)
        output.append(entry)
    return output


def Save(data, *unused):
    entries = _ui_data()
    for row, entry in zip(ITEMS["rows"], entries):
        surface = entry["surface"]
        if not surface:
            entry.pop("surfaceSnapshot", None)
            continue
        matches = cmds.ls(surface, long=True, type="transform") or []
        if matches:
            # Save evaluated NURBS geometry automatically for future builds.
            entry["surfaceSnapshot"] = _capture_slide_surface(surface)
        else:
            # On a fresh scene, retain valid previously saved geometry.
            snapshot = entry.get("surfaceSnapshot")
            if not snapshot or snapshot.get("name") != surface.rsplit("|", 1)[-1]:
                raise ValueError("Slide Surface: pick a NURBS surface and Save once "
                                 "before building without the source: " + surface)
    NLTA_General.writeJsonFile(_data_path(data), entries)
    for row, entry in zip(ITEMS["rows"], entries):
        row["surfaceSnapshot"] = entry.get("surfaceSnapshot")
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
    return (str(data["prefix"]).strip(), str(data["rootParent"]).strip(),
            str(data["surface"]).strip(), str(data["driver"]).strip(),
            data["controls"])

def BuildSlideSurface(datas):
    """Build independent slide guides, Follicle skin drivers, Spline IK and control correction."""
    import maya.cmds as cmds
    import maya.api.OpenMaya as om

    def unique_node(saved, kind="transform"):
        name = str(saved).strip()
        return (cmds.ls(name, long=True, type=kind) or
                cmds.ls(name.rsplit("|", 1)[-1], long=True, type=kind))[0]

    def mmatrix(node):
        return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))

    def setmatrix(plug, matrix):
        cmds.setAttr(plug, *list(matrix), type="matrix")

    def xyz(node):
        return [float(x) for x in cmds.xform(node, query=True,
                                              worldSpace=True, translation=True)]

    def is_ancestor(ancestor, target):
        return target == ancestor or target.startswith(ancestor + "|")

    # Stage: Resolve saved controls, hierarchy and bind matrices.
    configs = []
    for data in datas:
        prefix, root_name, surface_name, driver_name, items = _validate_item(data)
        root = unique_node(root_name)
        driver = unique_node(driver_name)
        surface = unique_node(surface_name)
        contain_name = str(data.get("contain", "")).strip()
        contain = unique_node(contain_name) if contain_name else None
        bind_driver = mmatrix(driver)
        bind_root = mmatrix(root)
        shapes = cmds.listRelatives(surface, shapes=True, noIntermediate=True,
                                    fullPath=True, type="nurbsSurface") or []
        if any(is_ancestor(surface, node) for node in (root, driver, contain) if node):
            raise ValueError("Slide Surface: surface cannot contain Root, Driver or Contain: " + surface)
        if not is_ancestor(root, driver):
            raise ValueError("Slide Surface: Root Parent must contain Driver in DAG")
        if data.get("axis", "Auto") == "Auto" and len(items) < 2:
            raise ValueError("Slide Surface: Auto UV requires at least two controls; choose U/V for one")
        nodes = [unique_node(item["control"]) for item in items]
        for node in nodes:
            if is_ancestor(node, driver) or is_ancestor(node, surface):
                raise ValueError("Slide Surface: a corrected control cannot contain Driver or Surface: " + node)
            if is_ancestor(surface, node):
                raise ValueError("Slide Surface: surface cannot contain a corrected control: " + node)
            if contain and is_ancestor(node, contain):
                raise ValueError("Slide Surface: Contain cannot be a child of a corrected control: " + node)
        joint_names = data.get("jointBind") or []
        if isinstance(joint_names, str):
            joint_names = [v.strip() for v in re.split(r"[,;\n]+", joint_names) if v.strip()]
        skin_joints = [unique_joint for joint_name in joint_names
                       for unique_joint in [cmds.ls(joint_name, long=True, type="joint")[0]]]
        for joint in skin_joints:
            if is_ancestor(surface, joint) or any(is_ancestor(ctrl, joint) for ctrl in nodes):
                raise ValueError("Slide Surface: Joint Bind would create a cycle: " + joint)
        # Reject invalid existing skin BEFORE creating any setup groups.
        existing_surface_skin = None
        if skin_joints:
            clusters = [name for name in (cmds.listHistory(shapes[0]) or [])
                        if cmds.nodeType(name) == "skinCluster"]
            clusters = list(dict.fromkeys(clusters))
            if len(clusters) > 1:
                raise ValueError("Slide Surface: multiple skinClusters on NURBS surface: " + surface)
            if clusters:
                existing_surface_skin = clusters[0]
                influences = cmds.skinCluster(existing_surface_skin, query=True, influence=True) or []
                influences = {cmds.ls(name, long=True)[0] for name in influences}
                if influences != set(skin_joints):
                    raise ValueError("Slide Surface: existing surface skin influences differ "
                                     "from Joint Bind: " + surface)
        named = {item["control"].strip(): node for item, node in zip(items, nodes)}
        parents, parent_controls, bind_controls, matrix_modes = [], [], [], []
        for item, ctrl in zip(items, nodes):
            original_parent = (cmds.listRelatives(ctrl, parent=True, fullPath=True) or [None])[0]
            chosen = str(item.get("parent", "")).strip()
            requested = str(item.get("matrixMode", "Hierarchy" if chosen else "Auto"))
            parent_ctrl = root if chosen == root_name else driver if chosen == driver_name else named.get(chosen)
            candidates = [root, driver] + [n for n in nodes if n != ctrl]
            nearest = max((n for n in candidates if original_parent and
                           is_ancestor(n, original_parent)),
                          key=lambda n: n.count("|"), default=None)
            # Preserve the exact V6.1 correction for legacy JSON. Auto uses the
            # hierarchy path when provable and falls back to live parent space.
            if requested == "Hierarchy":
                if not is_ancestor(root, ctrl):
                    raise ValueError("Slide Surface: Hierarchy mode needs control under Root: " + ctrl)
                if not original_parent or parent_ctrl is None or not is_ancestor(parent_ctrl, original_parent):
                    raise ValueError("Slide Surface: invalid hierarchy parent for " + ctrl)
                if nearest != parent_ctrl:
                    raise ValueError("Slide Surface: hierarchy parent for %s must be its nearest selected ancestor %s"
                                     % (ctrl, nearest))
                mode = "Hierarchy"
            elif requested == "Auto":
                mode = "Hierarchy" if nearest is not None and (not chosen or parent_ctrl == nearest) else "Universal"
                if mode == "Hierarchy":
                    parent_ctrl = nearest
            else:
                mode = "Universal"
            if not cmds.getAttr(ctrl + ".inheritsTransform"):
                raise ValueError("Slide Surface: Matrix Correct needs inheritsTransform=1: " + ctrl)
            for candidate in (ctrl, original_parent):
                if candidate and abs(mmatrix(candidate).det4x4()) < 1e-10:
                    raise ValueError("Slide Surface: non-invertible control/parent matrix: " + candidate)
            parents.append(original_parent)
            parent_controls.append(parent_ctrl if mode == "Hierarchy" else None)
            matrix_modes.append(mode)
            bind_controls.append(mmatrix(ctrl))
        driver_parent = (cmds.listRelatives(driver, parent=True, fullPath=True) or [None])[0]
        if not driver_parent:
            raise ValueError("Slide Surface: Driver requires a DAG parent")
        configs.append(dict(data=data, prefix=prefix, root=root, driver=driver,
                            contain=contain, surface=surface, shape=shapes[0],
                            skin_joints=skin_joints, existing_surface_skin=existing_surface_skin,
                            nodes=nodes, parents=parents,
                            parent_controls=parent_controls, bind_controls=bind_controls,
                            matrix_modes=matrix_modes,
                            bind_parents=[mmatrix(p) if p else om.MMatrix() for p in parents],
                            bind_parent_ctrl=[mmatrix(p) if p else om.MMatrix() for p in parent_controls],
                            bind_driver=bind_driver, bind_root=bind_root,
                            driver_parent=driver_parent,
                            bind_driver_parent=mmatrix(driver_parent)))

    results = []
    for cfg in configs:
        data, prefix, items = cfg["data"], cfg["prefix"], cfg["data"]["controls"]
        solver = data.get("solver", "Spline IK")
        keep_length = solver == "Spline IK" and bool(data.get("keepLength", True))
        arc_spacing = solver == "Spline IK" and bool(data.get("arcSpacing", True))
        follow_driver_fk = bool(data.get("followDriverFK", True))
        root, driver, shape = cfg["root"], cfg["driver"], cfg["shape"]
        nodes = cfg["nodes"]
        tag = lambda i: "%s_%02d" % (prefix, i + 1)
        guide = cmds.createNode("transform", name=prefix + "_GUIDES_GRP")
        if cfg["contain"]:
            # Contain is an organizational DAG parent, not an extra rig driver.
            # Keep the guide in world space even when Contain moves or scales.
            cmds.setAttr(guide + ".inheritsTransform", 0)
            guide = cmds.parent(guide, cfg["contain"], relative=True)[0]
        # Stage: Move the surface into setup without changing its world matrix.
        surface_group = cmds.createNode("transform", name=prefix + "_SURFACES_GRP", parent=guide)
        surface = cmds.parent(cfg["surface"], surface_group, absolute=True)[0]
        surface = cmds.ls(surface, long=True)[0]
        shape = cmds.listRelatives(surface, shapes=True, noIntermediate=True,
                                   fullPath=True, type="nurbsSurface")[0]
        surface_skin_cluster = cfg["existing_surface_skin"]
        if cfg["skin_joints"] and not surface_skin_cluster:
            surface_skin_cluster = cmds.skinCluster(
                *(cfg["skin_joints"] + [surface]), toSelectedBones=True,
                bindMethod=0, skinMethod=0, normalizeWeights=1,
                maximumInfluences=min(4, len(cfg["skin_joints"])),
                name=prefix + "_SurfaceBind_SC")[0]
        refs_group = cmds.createNode("transform", name=prefix + "_BASELINE_GRP", parent=guide)
        loc_group = cmds.createNode("transform", name=prefix + "_LOCATORS_GRP", parent=guide)
        fol_group = cmds.createNode("transform", name=prefix + "_FOLLICLES_GRP", parent=guide)

        # Stage: optional Root-relative driver rotation limit, before any sliding or IK.
        # Unlike per-control contact blending, this preserves the baseline IK segment lengths.
        driver_source = driver + ".worldMatrix[0]"
        if solver == "Spline IK" and not arc_spacing and bool(data.get("limitSolverAngle", True)):
            bind_driver_root = cfg["bind_driver"] * cfg["bind_root"].inverse()
            max_angle = float(data.get("maxSolverAngle", 65.0))
            cmds.addAttr(guide, longName="MaxSolverAngle", attributeType="double",
                         minValue=1.0, maxValue=179.0, defaultValue=max_angle, keyable=True)
            live_local = cmds.createNode("multMatrix", name=prefix + "_ANGLE_LOCAL_DELTA_MM")
            setmatrix(live_local + ".matrixIn[0]", bind_driver_root.inverse())
            cmds.connectAttr(driver + ".worldMatrix[0]", live_local + ".matrixIn[1]")
            cmds.connectAttr(root + ".worldInverseMatrix[0]", live_local + ".matrixIn[2]")
            local_dcm = cmds.createNode("decomposeMatrix", name=prefix + "_ANGLE_LOCAL_DCM")
            cmds.connectAttr(live_local + ".matrixSum", local_dcm + ".inputMatrix")
            order = int(cmds.getAttr(driver + ".rotateOrder"))
            cmds.setAttr(local_dcm + ".inputRotateOrder", order)
            angle_clamp = cmds.createNode("clamp", name=prefix + "_ANGLE_CLAMP")
            # Child plugs permit Maya to insert the correct angle-unit conversions.
            for color, axis in zip("RGB", "XYZ"):
                cmds.connectAttr(local_dcm + ".outputRotate" + axis, angle_clamp + ".input" + color)
            neg = cmds.createNode("multiplyDivide", name=prefix + "_ANGLE_NEGATE_MD")
            cmds.setAttr(neg + ".input2X", -1.0)
            cmds.connectAttr(guide + ".MaxSolverAngle", neg + ".input1X")
            for channel in "RGB":
                cmds.connectAttr(guide + ".MaxSolverAngle", angle_clamp + ".max" + channel)
                cmds.connectAttr(neg + ".outputX", angle_clamp + ".min" + channel)
            bounded = cmds.createNode("composeMatrix", name=prefix + "_ANGLE_BOUNDED_CM")
            cmds.setAttr(bounded + ".useEulerRotation", 1)
            cmds.setAttr(bounded + ".inputRotateOrder", order)
            cmds.connectAttr(local_dcm + ".outputTranslate", bounded + ".inputTranslate")
            for color, axis in zip("RGB", "XYZ"):
                cmds.connectAttr(angle_clamp + ".output" + color, bounded + ".inputRotate" + axis)
            cmds.connectAttr(local_dcm + ".outputScale", bounded + ".inputScale")
            cmds.connectAttr(local_dcm + ".outputShear", bounded + ".inputShear")
            effective_world = cmds.createNode("multMatrix", name=prefix + "_ANGLE_DRIVER_WORLD_MM")
            setmatrix(effective_world + ".matrixIn[0]", bind_driver_root)
            cmds.connectAttr(bounded + ".outputMatrix", effective_world + ".matrixIn[1]")
            cmds.connectAttr(root + ".worldMatrix[0]", effective_world + ".matrixIn[2]")
            driver_source = effective_world + ".matrixSum"

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

        # Stage: independent projection guide. NEVER feed a solved IK joint into its input.
        guide_points = [xyz(driver)] + bind_points
        path_points = [xyz(driver)] + ([xyz(node) for node in nodes] if keep_length else bind_points)
        cv_count = max(6, 3 * (len(guide_points) - 1) + 1)
        cv_points = []
        for cv_index in range(cv_count):
            progress = float(cv_index) / float(cv_count - 1) * (len(guide_points) - 1)
            span = min(int(progress), len(guide_points) - 2)
            fraction = progress - span
            start, end = guide_points[span], guide_points[span + 1]
            cv_points.append([a * (1.0 - fraction) + b * fraction for a, b in zip(start, end)])
        curve = cmds.curve(name=prefix + "_SplineGuide_CRV", degree=3, point=cv_points)
        curve = cmds.parent(curve, guide)[0]
        curve_shape = (cmds.listRelatives(curve, shapes=True, noIntermediate=True, fullPath=True,
                                          type="nurbsCurve") or [])[0]
        driver_delta = cmds.createNode("multMatrix", name=prefix + "_SPLINE_DRIVER_MM")
        setmatrix(driver_delta + ".matrixIn[0]", cfg["bind_driver"].inverse())
        cmds.connectAttr(driver_source, driver_delta + ".matrixIn[1]")
        root_delta = cmds.createNode("multMatrix", name=prefix + "_SPLINE_ROOT_MM")
        setmatrix(root_delta + ".matrixIn[0]", cfg["bind_root"].inverse())
        cmds.connectAttr(root + ".worldMatrix[0]", root_delta + ".matrixIn[1]")
        for cv_index, bind_point in enumerate(cv_points):
            pfx = "%s_CV%02d" % (prefix, cv_index)
            driver_point = cmds.createNode("pointMatrixMult", name=pfx + "_DRIVER_PMM")
            root_point = cmds.createNode("pointMatrixMult", name=pfx + "_ROOT_PMM")
            cmds.setAttr(driver_point + ".inPoint", *bind_point, type="double3")
            cmds.setAttr(root_point + ".inPoint", *bind_point, type="double3")
            cmds.connectAttr(driver_delta + ".matrixSum", driver_point + ".inMatrix")
            cmds.connectAttr(root_delta + ".matrixSum", root_point + ".inMatrix")
            mix = cmds.createNode("blendColors", name=pfx + "_SPLINE_MIX")
            cmds.connectAttr(driver_point + ".output", mix + ".color1")
            cmds.connectAttr(root_point + ".output", mix + ".color2")
            t = float(cv_index) / float(cv_count - 1)
            tail_blend = t * t * (3.0 - 2.0 * t)
            tail_pin = float(data.get("tailPin", 1.0)) if solver == "Spline IK" else 1.0
            cmds.setAttr(mix + ".blender", 1.0 - tail_pin * tail_blend)
            cmds.connectAttr(mix + ".output", curve_shape + ".controlPoints[%d]" % cv_index)

        # Stage: fix guide parameters at bind; guide motion is independent of Spline IK.
        bind_params = []
        nearest = cmds.createNode("nearestPointOnCurve", name=prefix + "_SPLINE_BIND_NPOC")
        cmds.connectAttr(curve_shape + ".worldSpace[0]", nearest + ".inputCurve")
        for point in bind_points:
            cmds.setAttr(nearest + ".inPosition", *point, type="double3")
            bind_params.append(float(cmds.getAttr(nearest + ".parameter")))
        cmds.delete(nearest)
        if any(b <= a + 1e-5 for a, b in zip(bind_params, bind_params[1:])):
            raise ValueError("Slide Surface: spline guide parameters overlap; check Controls order")

        # Stage: sample one live Surface isoparm and retain bind arc offsets.
        # Only the first guide point determines the slide: other controls do not
        # use independent closestPointOnSurface projections for their UV motion.
        arc_motion = []
        if arc_spacing:
            iso = cmds.createNode("curveFromSurfaceIso", name=prefix + "_SLIDE_ISO")
            cmds.connectAttr(shape + ".worldSpace[0]", iso + ".inputSurface")
            cmds.setAttr(iso + ".isoparmDirection", 0 if moving == "U" else 1)
            cmds.setAttr(iso + ".relativeValue", 1)
            cmds.setAttr(iso + ".isoparmValue", fixed_value)
            cmds.setAttr(iso + ".relative", 1)
            cmds.setAttr(iso + ".minValue", 0.0)
            cmds.setAttr(iso + ".maxValue", 1.0)
            iso_transform = cmds.createNode("transform", name=prefix + "_SLIDE_ISO_CRV", parent=guide)
            iso_shape = cmds.createNode("nurbsCurve", name=prefix + "_SLIDE_ISOShape", parent=iso_transform)
            cmds.connectAttr(iso + ".outputCurve", iso_shape + ".create")
            iso_world = iso_shape + ".worldSpace[0]"
            nearest_bind = cmds.createNode("nearestPointOnCurve", name=prefix + "_SLIDE_ISO_BIND_NPOC")
            cmds.connectAttr(iso_world, nearest_bind + ".inputCurve")
            sample_params = []
            for point in bind_points:
                cmds.setAttr(nearest_bind + ".inPosition", *point, type="double3")
                sample_params.append(float(cmds.getAttr(nearest_bind + ".parameter")))
            cmds.delete(nearest_bind)
            selection = om.MSelectionList()
            selection.add(iso_shape)
            curve_fn = om.MFnNurbsCurve(selection.getDagPath(0))
            bind_length = float(curve_fn.length())
            if bind_length < 1e-8:
                raise ValueError("Slide Surface: Surface isoparm has zero arc length")
            fractions = [float(curve_fn.findLengthFromParam(p)) / bind_length for p in sample_params]
            increasing = all(b > a + 1e-6 for a, b in zip(fractions, fractions[1:]))
            decreasing = all(b < a - 1e-6 for a, b in zip(fractions, fractions[1:]))
            if not (increasing or decreasing):
                raise ValueError("Slide Surface: Controls must follow a monotonic Surface isoparm")
            arc_offsets = [fraction - fractions[0] for fraction in fractions]
            anchor_min = max(margin, margin - min(arc_offsets))
            anchor_max = min(1.0 - margin, 1.0 - margin - max(arc_offsets))
            if anchor_max < anchor_min - 1e-8:
                raise ValueError("Slide Surface: Surface is too short to fit bind arc spacing")

            guide_sample = cmds.createNode("pointOnCurveInfo", name=prefix + "_SLIDE_ANCHOR_GUIDE_POCI")
            cmds.connectAttr(curve_shape + ".worldSpace[0]", guide_sample + ".inputCurve")
            cmds.setAttr(guide_sample + ".parameter", bind_params[0])
            first_position = cmds.getAttr(guide_sample + ".position")[0]
            anchor_offset = [a - b for a, b in zip(bind_points[0], first_position)]
            guide_corrected = cmds.createNode("plusMinusAverage", name=prefix + "_SLIDE_ANCHOR_BIND_OFFSET")
            cmds.setAttr(guide_corrected + ".operation", 1)
            cmds.connectAttr(guide_sample + ".position", guide_corrected + ".input3D[0]")
            cmds.setAttr(guide_corrected + ".input3D[1]", *anchor_offset, type="double3")
            cmds.addAttr(guide, longName="SlideStrength", attributeType="double",
                         minValue=0, maxValue=1, defaultValue=float(data.get("slideStrength", 1.0)), keyable=True)
            anchor_mix = cmds.createNode("blendColors", name=prefix + "_SLIDE_ANCHOR_STRENGTH_MIX")
            cmds.connectAttr(guide_corrected + ".output3D", anchor_mix + ".color1")
            cmds.setAttr(anchor_mix + ".color2", *bind_points[0], type="double3")
            cmds.connectAttr(guide + ".SlideStrength", anchor_mix + ".blender")
            nearest_anchor = cmds.createNode("nearestPointOnCurve", name=prefix + "_SLIDE_ANCHOR_NPOC")
            cmds.connectAttr(iso_world, nearest_anchor + ".inputCurve")
            cmds.connectAttr(anchor_mix + ".output", nearest_anchor + ".inPosition")
            pmin = float(cmds.getAttr(iso_shape + ".minValue"))
            pmax = float(cmds.getAttr(iso_shape + ".maxValue"))
            if pmax - pmin < 1e-8:
                raise ValueError("Slide Surface: Invalid Surface iso curve parameter domain")
            param_clamp = cmds.createNode("clamp", name=prefix + "_SLIDE_ANCHOR_PARAM_CLAMP")
            epsilon = max((pmax - pmin) * 1e-7, 1e-8)
            cmds.setAttr(param_clamp + ".minR", pmin + epsilon)
            cmds.setAttr(param_clamp + ".maxR", pmax)
            cmds.connectAttr(nearest_anchor + ".parameter", param_clamp + ".inputR")
            sub = cmds.createNode("subCurve", name=prefix + "_SLIDE_ANCHOR_SUBCURVE")
            cmds.connectAttr(iso_world, sub + ".inputCurve")
            cmds.setAttr(sub + ".minValue", pmin)
            cmds.connectAttr(param_clamp + ".outputR", sub + ".maxValue")
            part_info = cmds.createNode("curveInfo", name=prefix + "_SLIDE_ANCHOR_LENGTH")
            cmds.connectAttr(sub + ".outputCurve", part_info + ".inputCurve")
            total_info = cmds.createNode("curveInfo", name=prefix + "_SLIDE_TOTAL_LENGTH")
            cmds.connectAttr(iso_world, total_info + ".inputCurve")
            divide = cmds.createNode("multiplyDivide", name=prefix + "_SLIDE_ARC_FRACTION_MD")
            cmds.setAttr(divide + ".operation", 2)
            cmds.connectAttr(part_info + ".arcLength", divide + ".input1X")
            cmds.connectAttr(total_info + ".arcLength", divide + ".input2X")
            clamp_anchor = cmds.createNode("clamp", name=prefix + "_SLIDE_ANCHOR_RANGE_CLAMP")
            cmds.setAttr(clamp_anchor + ".minR", anchor_min)
            cmds.setAttr(clamp_anchor + ".maxR", anchor_max)
            cmds.connectAttr(divide + ".outputX", clamp_anchor + ".inputR")
            for index, arc_offset in enumerate(arc_offsets):
                pfx = tag(index)
                fraction_sum = cmds.createNode("plusMinusAverage", name=pfx + "_SLIDE_ARC_FRACTION_PMA")
                cmds.setAttr(fraction_sum + ".operation", 1)
                cmds.connectAttr(clamp_anchor + ".outputR", fraction_sum + ".input1D[0]")
                cmds.setAttr(fraction_sum + ".input1D[1]", arc_offset)
                motion = cmds.createNode("motionPath", name=pfx + "_SLIDE_ARC_MP")
                cmds.setAttr(motion + ".fractionMode", 1)
                cmds.setAttr(motion + ".follow", 0)
                cmds.connectAttr(iso_world, motion + ".geometryPath")
                cmds.connectAttr(fraction_sum + ".output1D", motion + ".uValue")
                arc_motion.append(motion)
            cmds.addAttr(guide, longName="SurfaceArcBindLength", attributeType="double",
                         defaultValue=bind_length)
            cmds.addAttr(guide, longName="ArcAnchorMinimum", attributeType="double",
                         defaultValue=anchor_min)
            cmds.addAttr(guide, longName="ArcAnchorMaximum", attributeType="double",
                         defaultValue=anchor_max)

        # Stage: each Follicle samples the shared surface path; original Gragas pipeline stays unchanged.
        markers, refs, follicles = [], [], []
        for index, (item, on_surface) in enumerate(zip(items, bind_points)):
            pfx = tag(index)
            ref = cmds.spaceLocator(name=pfx + "_Baseline_REF")[0]
            ref = cmds.parent(ref, refs_group)[0]
            cmds.xform(ref, worldSpace=True, translation=on_surface)
            # All controls follow the computed Marker at weight 1.0.
            # BlendWeight is only needed by the legacy non-Arc Spacing path.
            if not arc_spacing:
                cmds.addAttr(ref, longName="BlendWeight", attributeType="double", minValue=0,
                             maxValue=1, defaultValue=1.0)
            if arc_spacing:
                cmds.connectAttr(arc_motion[index] + ".allCoordinates", ref + ".translate")
            else:
                # Arc Spacing drives the reference directly; do not create
                # three unconnected legacy slide nodes in that mode.
                sample = cmds.createNode("pointOnCurveInfo", name=pfx + "_SPLINE_POCI")
                cmds.connectAttr(curve_shape + ".worldSpace[0]", sample + ".inputCurve")
                cmds.setAttr(sample + ".parameter", bind_params[index])
                rest = cmds.createNode("pointMatrixMult", name=pfx + "_SPLINE_REST_PMM")
                cmds.setAttr(rest + ".inPoint", *on_surface, type="double3")
                cmds.connectAttr(root_delta + ".matrixSum", rest + ".inMatrix")
                slide_blend = cmds.createNode("blendColors", name=pfx + "_SLIDE_INPUT_MIX")
                cmds.connectAttr(sample + ".position", slide_blend + ".color1")
                cmds.connectAttr(rest + ".output", slide_blend + ".color2")
                cmds.connectAttr(ref + ".BlendWeight", slide_blend + ".blender")
                cmds.connectAttr(slide_blend + ".output", ref + ".translate")

            driven = cmds.spaceLocator(name=pfx + "_Driven_LOC")[0]
            driven = cmds.parent(driven, loc_group)[0]
            cmds.xform(driven, worldSpace=True, translation=on_surface)
            driven_mm = cmds.createNode("multMatrix", name=pfx + "_DRIVEN_LOCAL_MM")
            cmds.connectAttr(ref + ".worldMatrix[0]", driven_mm + ".matrixIn[0]")
            cmds.connectAttr(loc_group + ".worldInverseMatrix[0]", driven_mm + ".matrixIn[1]")
            cmds.setAttr(driven + ".translate", 0, 0, 0, type="double3")
            cmds.connectAttr(driven_mm + ".matrixSum", driven + ".offsetParentMatrix")
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
            cmds.setAttr(normalizer + ".minX", 0.0)
            cmds.setAttr(normalizer + ".maxX", 1.0)
            cmds.connectAttr(cpos + ".parameter" + moving, normalizer + ".valueX")
            clamp = cmds.createNode("clamp", name=pfx + "_UV_CLAMP")
            # Arc anchor owns the endpoint safety margin. A second UV-margin
            # clamp could collapse the last few Follicles on a nonuniform surface.
            cmds.setAttr(clamp + ".minR", 0.0 if arc_spacing else margin)
            cmds.setAttr(clamp + ".maxR", 1.0 if arc_spacing else 1.0 - margin)
            cmds.connectAttr(normalizer + ".outValueX", clamp + ".inputR")
            cmds.connectAttr(clamp + ".outputR", fshape + ".parameter" + moving)
            cmds.setAttr(fshape + ".parameter" + fixed, fixed_value)
            marker = cmds.spaceLocator(name=pfx + "_Marker")[0]
            marker = cmds.parent(marker, fol, relative=True)[0]
            cmds.setAttr(marker + ".translate", 0, 0, 0, type="double3")
            cmds.setAttr(marker + ".rotate", 0, 0, 0, type="double3")
            markers.append(marker)
            refs.append(ref)
            follicles.append(fol)

        ik_joints, ik_handle, skin_curve, skin_cluster, skin_drivers = [], None, None, None, []
        if solver == "Spline IK":
            # Stage: Gragas200 layout: Follicle -> Driver Joints -> Skinned Curve -> Spline IK.
            # Only independent Follicles control the SkinCluster; the IK never feeds the UV locators.
            driver_anchor = cmds.createNode("transform", name=prefix + "_SKIN_DRIVER_ANCHOR", parent=guide)
            cmds.connectAttr(driver_source, driver_anchor + ".offsetParentMatrix")
            driver_joint = cmds.createNode("joint", name=prefix + "_SKIN_ROOT_DRIVER_JNT", parent=driver_anchor)
            skin_drivers.append(driver_joint)
            # Stage: Keep driver joint scale connections unchanged.
            skin_scale = cmds.createNode("decomposeMatrix", name=prefix + "_SKIN_SCALE_DCM")
            cmds.connectAttr(driver_anchor + ".worldMatrix[0]", skin_scale + ".inputMatrix")
            for index, fol in enumerate(follicles):
                jnt = cmds.createNode("joint", name=tag(index) + "_SURFACE_DRIVER_JNT", parent=fol)
                cmds.setAttr(jnt + ".translate", 0, 0, 0, type="double3")
                cmds.setAttr(jnt + ".rotate", 0, 0, 0, type="double3")
                cmds.connectAttr(skin_scale + ".outputScale", jnt + ".scale")
                skin_drivers.append(jnt)
            curve_cvs = []
            for cv_index in range(cv_count):
                progress = float(cv_index) / float(cv_count - 1) * (len(path_points) - 1)
                span = min(int(progress), len(path_points) - 2)
                fraction = progress - span
                start, end = path_points[span], path_points[span + 1]
                curve_cvs.append([a * (1.0 - fraction) + b * fraction for a, b in zip(start, end)])
            skin_curve = cmds.curve(name=prefix + "_SurfaceSkin_CRV", degree=3, point=curve_cvs)
            skin_curve = cmds.parent(skin_curve, guide)[0]
            skin_cluster = cmds.skinCluster(*(skin_drivers + [skin_curve]), toSelectedBones=True,
                                            normalizeWeights=1, maximumInfluences=2,
                                            name=prefix + "_SurfaceSkin_SC")[0]
            for cv_index in range(cv_count):
                progress = float(cv_index) / float(cv_count - 1) * (len(skin_drivers) - 1)
                span = min(int(progress), len(skin_drivers) - 2)
                ratio = progress - span
                weights = [(skin_drivers[span], 1.0 - ratio), (skin_drivers[span + 1], ratio)]
                cmds.skinPercent(skin_cluster, skin_curve + ".cv[%d]" % cv_index,
                                 transformValue=weights, normalize=True)

            # Stage: retain original joint segment lengths; the skinned curve drives their IK pose.
            for index, point in enumerate(path_points):
                if index and sum((a-b)**2 for a, b in zip(point, path_points[index-1])) < 1e-8:
                    raise ValueError("Slide Surface: zero-length IK segment at index %d" % index)
                cmds.select(clear=True)
                jnt = cmds.createNode("joint", name=prefix + "_SPLINE_%02d_JNT" % index)
                cmds.xform(jnt, worldSpace=True, translation=point)
                if ik_joints:
                    jnt = cmds.parent(jnt, ik_joints[-1], absolute=True)[0]
                    bind_length = sum((a-b)**2 for a, b in zip(point, path_points[index-1])) ** 0.5
                    cmds.addAttr(jnt, longName="BindSegmentLength", attributeType="double")
                    cmds.setAttr(jnt + ".BindSegmentLength", bind_length)
                ik_joints.append(jnt)
            cmds.joint(ik_joints[0], edit=True, orientJoint="xyz", secondaryAxisOrient="yup",
                       children=True, zeroScaleOrient=True)
            ik_anchor = cmds.createNode("transform", name=prefix + "_IK_DRIVER_ANCHOR", parent=guide)
            cmds.connectAttr(driver_source, ik_anchor + ".offsetParentMatrix")
            cmds.parent(ik_joints[0], ik_anchor, absolute=True)
            handle = cmds.ikHandle(name=prefix + "_SPLINE_IKH", startJoint=ik_joints[0],
                                  endEffector=ik_joints[-1], solver="ikSplineSolver",
                                  curve=skin_curve, createCurve=False, parentCurve=False)
            ik_handle = cmds.parent(handle[0], guide, absolute=True)[0]
            cmds.setAttr(ik_handle + ".dTwistControlEnable", 1)
            cmds.setAttr(ik_handle + ".dWorldUpType", 4)
            cmds.setAttr(ik_handle + ".dForwardAxis", 0)
            cmds.setAttr(ik_handle + ".dWorldUpAxis", 3)
            cmds.setAttr(ik_handle + ".dWorldUpVectorY", 0)
            cmds.setAttr(ik_handle + ".dWorldUpVectorEndY", 0)
            cmds.setAttr(ik_handle + ".dWorldUpVectorZ", 1)
            cmds.setAttr(ik_handle + ".dWorldUpVectorEndZ", 1)
            cmds.connectAttr(skin_drivers[0] + ".worldMatrix[0]", ik_handle + ".dWorldUpMatrix")
            cmds.connectAttr(skin_drivers[-1] + ".worldMatrix[0]", ik_handle + ".dWorldUpMatrixEnd")

            # Stage: IK is downstream of Surface; use its fixed-length positions for control correction.
            for index, (marker, fol) in enumerate(zip(markers, follicles)):
                if keep_length:
                    pfx = tag(index)
                    locked_marker = cmds.createNode("blendMatrix", name=pfx + "_LOCKED_MARKER_BM")
                    cmds.connectAttr(fol + ".worldMatrix[0]", locked_marker + ".inputMatrix")
                    cmds.connectAttr(ik_joints[index + 1] + ".worldMatrix[0]",
                                     locked_marker + ".target[0].targetMatrix")
                    cmds.setAttr(locked_marker + ".target[0].weight", 1.0)
                    cmds.setAttr(locked_marker + ".target[0].translateWeight", 1.0)
                    cmds.setAttr(locked_marker + ".target[0].rotateWeight", 0.0)
                    cmds.setAttr(locked_marker + ".target[0].scaleWeight", 0.0)
                    cmds.setAttr(locked_marker + ".target[0].shearWeight", 0.0)
                    marker_local = cmds.createNode("multMatrix", name=pfx + "_LOCKED_MARKER_LOCAL_MM")
                    cmds.connectAttr(locked_marker + ".outputMatrix", marker_local + ".matrixIn[0]")
                    cmds.connectAttr(fol + ".worldInverseMatrix[0]", marker_local + ".matrixIn[1]")
                    cmds.connectAttr(marker_local + ".matrixSum", marker + ".offsetParentMatrix")

        marker_binds = [mmatrix(marker) for marker in markers]
        # Expected transforms must not read corrected control world matrices.
        # Build them only for controls referenced as virtual FK parents.
        hierarchy_refs = {parent for parent, mode in zip(cfg["parent_controls"],
                           cfg["matrix_modes"]) if mode == "Hierarchy"}
        expected_worlds = [None] * len(markers)
        for index, marker in enumerate(markers):
            if nodes[index] not in hierarchy_refs:
                continue
            pfx = tag(index)
            expected = cmds.createNode("multMatrix", name=pfx + "_EXPECTED_WORLD_MM")
            setmatrix(expected + ".matrixIn[0]", cfg["bind_controls"][index] * marker_binds[index].inverse())
            cmds.connectAttr(marker + ".worldMatrix[0]", expected + ".matrixIn[1]")
            expected_worlds[index] = expected

        # Create the original V6.1 virtual Driver only when it is actually used.
        expected_driver = None
        if follow_driver_fk:
            if driver in hierarchy_refs:
                expected_driver = cmds.createNode("multMatrix", name=prefix + "_FK_EXPECTED_DRIVER_MM")
                setmatrix(expected_driver + ".matrixIn[0]",
                          cfg["bind_driver"] * cfg["bind_driver_parent"].inverse())
                cmds.connectAttr(cfg["driver_parent"] + ".worldMatrix[0]",
                                 expected_driver + ".matrixIn[1]")

        cumulative_shape_scales = {}

        def create_matrix_correct(index, item, marker):
            # One function for FK Hierarchy and Universal constrained-parent modes.
            pfx = tag(index)
            # Stage: corrected group OPM in its original parent space.
            # Hierarchy: keep the V6.1 virtual FK parent for animator inheritance.
            # Universal: invert the actual, potentially constrained parent world.
            parent_ref = cfg["parent_controls"][index]
            parent_mode = cfg["matrix_modes"][index]
            correction = cmds.createNode("multMatrix", name=pfx + "_CORRECT_MM")
            setmatrix(correction + ".matrixIn[0]", cfg["bind_parents"][index] *
                      marker_binds[index].inverse())
            cmds.connectAttr(marker + ".worldMatrix[0]", correction + ".matrixIn[1]")
            if parent_mode == "Hierarchy":
                parent_exp = cmds.createNode("multMatrix", name=pfx + "_EXPECTED_PARENT_MM")
                setmatrix(parent_exp + ".matrixIn[0]", cfg["bind_parents"][index] *
                          cfg["bind_parent_ctrl"][index].inverse())
                upstream = next((j for j, node in enumerate(nodes) if node == parent_ref), None)
                if upstream is not None:
                    cmds.connectAttr(expected_worlds[upstream] + ".matrixSum", parent_exp + ".matrixIn[1]")
                elif follow_driver_fk and parent_ref == driver:
                    cmds.connectAttr(expected_driver + ".matrixSum", parent_exp + ".matrixIn[1]")
                else:
                    cmds.connectAttr(parent_ref + ".worldMatrix[0]", parent_exp + ".matrixIn[1]")
                pinv = cmds.createNode("inverseMatrix", name=pfx + "_EXPECTED_PARENT_INV")
                cmds.connectAttr(parent_exp + ".matrixSum", pinv + ".inputMatrix")
                cmds.connectAttr(pinv + ".outputMatrix", correction + ".matrixIn[2]")
            # Universal parent-space inverse is connected after discovering
            # the control's current parent. Prior corrected ancestors may have
            # changed its full DAG path since the preflight.
            # Stage: insert a neutral group immediately above EXISTING control.
            original = cfg["nodes"][index]
            leaf = original.rsplit("|", 1)[-1]
            live = unique_node(leaf)
            actual_parent = (cmds.listRelatives(live, parent=True, fullPath=True) or [None])[0]
            group = (cmds.createNode("transform", name=pfx + "_SlideOffset", parent=actual_parent)
                     if actual_parent else cmds.createNode("transform", name=pfx + "_SlideOffset"))
            cmds.parent(live, group, relative=True)
            if parent_mode == "Universal" and actual_parent:
                # Current parent path may have changed after an upstream
                # corrected control was wrapped in a neutral group.
                cmds.connectAttr(actual_parent + ".worldInverseMatrix[0]",
                                 correction + ".matrixIn[2]")
            # Stage: Keep the original full correction matrix: it preserves
            # correct FK positions and rotations when the rig changes scale.
            cmds.connectAttr(correction + ".matrixSum", group + ".offsetParentMatrix")
            new_bind = mmatrix(unique_node(leaf))
            error = max(abs(float(a)-float(b)) for a, b in zip(new_bind, cfg["bind_controls"][index]))
            if error > 1e-3:
                raise RuntimeError("Slide Surface: control moved at bind (%.6g): %s" % (error, leaf))
            # Stage: Shape-only scale compensation follows the actual FK DAG,
            # including correction scales inherited from parent SlideOffsets.
            # E4/E5 must not compensate only their own CORRECT_MM and ignore E3.
            control_node = unique_node(leaf)
            shape_scale = cmds.createNode("decomposeMatrix", name=pfx + "_SHAPE_SCALE_DCM")
            cmds.connectAttr(correction + ".matrixSum", shape_scale + ".inputMatrix")
            shape_ratio = cmds.createNode("multiplyDivide", name=pfx + "_SHAPE_SCALE_RATIO_MD")
            cmds.setAttr(shape_ratio + ".operation", 2)
            for coord in "XYZ":
                bind_value = float(cmds.getAttr(shape_scale + ".outputScale" + coord))
                if abs(bind_value) < 1e-8:
                    raise RuntimeError("Slide Surface: singular control shape scale: " + leaf)
                cmds.connectAttr(shape_scale + ".outputScale" + coord,
                                 shape_ratio + ".input1" + coord)
                cmds.setAttr(shape_ratio + ".input2" + coord, bind_value)
            combined_scale = shape_ratio + ".output"
            # Only corrected DAG ancestors contribute inherited correction
            # scale. Never multiply a virtual FK parent from another DAG branch.
            original_path = cfg["nodes"][index]
            ancestor_indices = [j for j in cumulative_shape_scales
                                if is_ancestor(cfg["nodes"][j], original_path)]
            if ancestor_indices:
                nearest = max(ancestor_indices, key=lambda j: cfg["nodes"][j].count("|"))
                accumulated = cmds.createNode("multiplyDivide", name=pfx + "_SHAPE_CUMULATIVE_MD")
                cmds.setAttr(accumulated + ".operation", 1)
                cmds.connectAttr(cumulative_shape_scales[nearest], accumulated + ".input1")
                cmds.connectAttr(shape_ratio + ".output", accumulated + ".input2")
                combined_scale = accumulated + ".output"
            cumulative_shape_scales[index] = combined_scale
            curve_shapes = cmds.listRelatives(control_node, shapes=True, noIntermediate=True,
                                              fullPath=True, type="nurbsCurve") or []
            if curve_shapes:
                inverse_scale = cmds.createNode("composeMatrix", name=pfx + "_SHAPE_SCALE_CM")
                cmds.connectAttr(combined_scale, inverse_scale + ".inputScale")
                for shape_index, visible_shape in enumerate(curve_shapes, 1):
                    source = cmds.listConnections(visible_shape + ".create", source=True,
                                                  destination=False, plugs=True) or []
                    if len(source) > 1:
                        raise RuntimeError("Slide Surface: multiple shape history sources: " + visible_shape)
                    geometry = cmds.createNode("transformGeometry",
                                               name=pfx + "_SHAPE_SCALE_%02d_TG" % shape_index)
                    cmds.setAttr(geometry + ".invertTransform", 1)
                    cmds.connectAttr(inverse_scale + ".outputMatrix", geometry + ".transform")
                    if source:
                        # Keep the original history live, inserting compensation
                        # between its output and the visible NURBS curve shape.
                        cmds.connectAttr(source[0], geometry + ".inputGeometry")
                    else:
                        # No construction history: copy geometry to a hidden
                        # intermediate source without touching visible CVs.
                        shape_selection = om.MSelectionList()
                        shape_selection.add(visible_shape)
                        control_selection = om.MSelectionList()
                        control_selection.add(control_node)
                        original = om.MFnNurbsCurve().copy(
                            shape_selection.getDependNode(0), control_selection.getDependNode(0))
                        original_shape = om.MFnDagNode(original).fullPathName()
                        original_shape = cmds.rename(
                            original_shape, pfx + "_ShapeInput_%02dShape" % shape_index)
                        cmds.setAttr(original_shape + ".intermediateObject", 1)
                        cmds.connectAttr(original_shape + ".local", geometry + ".inputGeometry")
                    cmds.connectAttr(geometry + ".outputGeometry",
                                     visible_shape + ".create", force=True)
            return {"control": leaf, "offset": group,
                    "reference": refs[index], "marker": marker,
                    "driven": tag(index) + "_Driven_LOC",
                    "hierarchyParent": item.get("parent", ""),
                    "matrixMode": parent_mode}

        created = [create_matrix_correct(i, item, marker)
                   for i, (item, marker) in enumerate(zip(items, markers))]
        # Stage: Disconnect only Follicle scale inputs and restore local scale to one.
        for fol in follicles:
            for channel in ("scale", "scaleX", "scaleY", "scaleZ"):
                plug = fol + "." + channel
                incoming = cmds.connectionInfo(plug, sourceFromDestination=True)
                if incoming:
                    cmds.disconnectAttr(incoming, plug)
            cmds.setAttr(fol + ".scale", 1, 1, 1, type="double3")
        cmds.setAttr(guide + ".visibility", 0)
        results.append({"prefix": prefix, "movingUV": moving, "fixedUV": fixed,
                        "controls": created, "guides": guide, "surface": surface,
                        "surfaceGroup": surface_group, "surfaceSkinCluster": surface_skin_cluster,
                        "spline": curve,
                        "skinCurve": skin_curve, "skinCluster": skin_cluster,
                        "skinDrivers": skin_drivers, "solver": solver,
                        "keepLength": keep_length, "arcSpacing": arc_spacing,
                        "followDriverFK": follow_driver_fk,
                        "ikHandle": ik_handle, "ikJoints": ik_joints})
    return results


def _capture_slide_surface(name):
    """Snapshot an evaluated, untrimmed NURBS surface for Save and Export."""
    import maya.api.OpenMaya as om
    matches = list(dict.fromkeys(cmds.ls(str(name).strip(), long=True, type="transform") or []))
    if len(matches) != 1:
        raise ValueError("Slide Surface Export: missing/ambiguous surface: " + str(name))
    source = matches[0]
    shapes = cmds.listRelatives(source, shapes=True, noIntermediate=True,
                                fullPath=True, type="nurbsSurface") or []
    if len(shapes) != 1:
        raise ValueError("Slide Surface Export: expected one NURBS shape: " + source)
    selection = om.MSelectionList()
    selection.add(shapes[0])
    fn = om.MFnNurbsSurface(selection.getDagPath(0))
    if fn.isTrimmedSurface:
        raise ValueError("Slide Surface Export: trimmed NURBS not supported: " + source)
    cvs = [[float(p.x), float(p.y), float(p.z), float(p.w)]
           for p in fn.cvPositions(om.MSpace.kObject)]
    if len(cvs) != int(fn.numCVsInU) * int(fn.numCVsInV):
        raise ValueError("Slide Surface Export: invalid CV count: " + source)
    parent = (cmds.listRelatives(source, parent=True, fullPath=True) or [""])[0]
    return {"name": source.rsplit("|", 1)[-1],
            "shape": shapes[0].rsplit("|", 1)[-1],
            "parent": parent,
            "worldMatrix": [float(x) for x in cmds.xform(source, query=True, worldSpace=True, matrix=True)],
            "inheritsTransform": bool(cmds.getAttr(source + ".inheritsTransform")),
            "cvs": cvs,
            "knotsU": [float(k) for k in fn.knotsInU()],
            "knotsV": [float(k) for k in fn.knotsInV()],
            "degreeU": int(fn.degreeInU), "degreeV": int(fn.degreeInV),
            "formU": int(fn.formInU), "formV": int(fn.formInV),
            "rational": any(abs(p[3] - 1.0) > 1e-10 for p in cvs)}


def _saved_slide_surfaces(records):
    return [record["surfaceSnapshot"] for record in records]


def _recreate_slide_surfaces(snapshots):
    import maya.api.OpenMaya as om

    # Stage: Create saved NURBS surface geometry.
    for snapshot in snapshots:
        transform = cmds.createNode("transform", name=snapshot["name"])
        selection = om.MSelectionList()
        selection.add(transform)
        points = [om.MPoint(*value) for value in snapshot["cvs"]]
        shape = om.MFnNurbsSurface().create(
            points, snapshot["knotsU"], snapshot["knotsV"],
            snapshot["degreeU"], snapshot["degreeV"],
            snapshot["formU"], snapshot["formV"],
            snapshot["rational"], selection.getDependNode(0))
        if snapshot.get("shape"):
            cmds.rename(om.MFnDagNode(shape).fullPathName(),
                        snapshot["shape"].rsplit("|", 1)[-1])
        cmds.setAttr(transform + ".inheritsTransform", int(snapshot.get("inheritsTransform", True)))
        cmds.xform(transform, worldSpace=True, matrix=snapshot["worldMatrix"])


def Run(data, *unused):
    records = NLTA_General.readJsonFile(_data_path(data))
    # Stage: Restore missing saved source geometry.
    missing = [record["surfaceSnapshot"] for record in records
               if not cmds.ls(record["surface"], type="transform")]
    _recreate_slide_surfaces(missing)
    return BuildSlideSurface(records)


def _export_stage_source(function):
    import ast
    import io
    import tokenize

    output = []
    for line in inspect.getsource(function).rstrip().splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("# Stage:"):
            continue
        if stripped.startswith('"""') and stripped.endswith('"""'):
            continue
        if not stripped and (not output or not output[-1]):
            continue
        output.append(line.rstrip())
    source = "\n".join(output).rstrip()
    tree = ast.parse(source)
    lines = source.splitlines()
    commented = {token.start[0] for token in tokenize.generate_tokens(io.StringIO(source).readline)
                 if token.type == tokenize.COMMENT}
    substitutions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return)):
            continue
        if node.end_lineno <= node.lineno or any(
                line in commented for line in range(node.lineno, node.end_lineno + 1)):
            continue
        if not any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                   and isinstance(child.func.value, ast.Name)
                   and child.func.value.id == "cmds" for child in ast.walk(node)):
            continue
        compact = ast.unparse(node)
        if "\n" in compact:
            continue
        first, last = node.lineno - 1, node.end_lineno - 1
        if lines[first][:node.col_offset].strip() or lines[last][node.end_col_offset:].strip():
            continue
        substitutions.append((first, last, lines[first][:node.col_offset] + compact))
    for first, last, compact in sorted(substitutions, reverse=True):
        lines[first:last + 1] = [compact]
    result = "\n".join(lines)
    return result if ast.dump(ast.parse(result), include_attributes=False) == ast.dump(
        tree, include_attributes=False) else source


def ExportPython(data, *unused):
    records = NLTA_General.readJsonFile(_data_path(data))
    snapshots = _saved_slide_surfaces(records)
    config = [{key: value for key, value in entry.items() if key != "surfaceSnapshot"}
              for entry in records]
    source = ("def main():\n"
              "    import re\n    import maya.cmds as cmds\n\n"
              "    # Stage: Restore saved NURBS source geometry.\n"
              "    SLIDE_SURFACE_DATA = " + repr(config) + "\n"
              "    SURFACE_SNAPSHOTS = " + repr(snapshots) + "\n\n"
              + textwrap.indent(_export_stage_source(_recreate_slide_surfaces), "    ") + "\n\n"
              + textwrap.indent(_export_stage_source(_validate_item), "    ") + "\n\n"
              + textwrap.indent(_export_stage_source(BuildSlideSurface), "    ") + "\n\n"
              "    _recreate_slide_surfaces(SURFACE_SNAPSHOTS)\n"
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
