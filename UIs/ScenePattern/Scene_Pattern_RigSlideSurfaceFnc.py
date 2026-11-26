# -*- coding: utf-8 -*-
"""Slide Surface with original Gragas source export and shared chain bias."""
import os
import re
import inspect
import json

import pymel.core as pm
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General

STATE = {"rows": [], "top": {}, "list": None}


def DefaultSetting(path, *unused):
    name = os.path.splitext(os.path.basename(__file__))[0]
    return {"ext": "json", "path": os.path.join(path, name + ".json"),
            "moduleName": name, "order": 0, "title": "Rig Slide Surface Fnc",
            "name": "Rig Slide Surface Fnc", "id": datetime.now().strftime("%Y%m%d%H%M%S")}


def _data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]})
    if not entry or not entry.get("path"):
        raise ValueError("Slide Surface: no data path in ScenePatternData.json")
    return os.path.normpath(entry["path"])


def _empty():
    return {"version": 1, "group": "RigUtil", "driverGroup": "Hair_Driver_Group",
            "items": []}


def _read_saved(data):
    path = _data_path(data)
    if not os.path.isfile(path):
        return _empty()
    result = NLTA_General.readJsonFile(path)
    if not isinstance(result, dict) or result.get("version") != 1:
        raise ValueError("Slide Surface: unsupported JSON settings version")
    return result


def _pick_surface(field, *unused):
    selected = cmds.ls(selection=True, objectsOnly=True) or []
    if len(selected) != 1:
        cmds.warning("Slide Surface: select one NURBS Surface transform")
        return
    name = selected[0]
    if cmds.nodeType(name) == "nurbsSurface":
        name = cmds.listRelatives(name, parent=True)[0]
    cmds.textField(field, edit=True, text=name)


def _pick_roots(field, *unused):
    selected = cmds.ls(selection=True, objectsOnly=True) or []
    roots = [node for node in selected if cmds.nodeType(node) == "joint"]
    if not roots:
        cmds.warning("Slide Surface: select one or more root joints")
        return
    previous = [x.strip() for x in cmds.scrollField(field, query=True, text=True).splitlines() if x.strip()]
    merged = list(dict.fromkeys(previous + roots))
    cmds.scrollField(field, edit=True, text="\n".join(merged))


def _field(parent, label, value, pick=None):
    row = cmds.rowLayout(parent=parent, numberOfColumns=3, columnWidth3=(112, 227, 52))
    cmds.text(parent=row, label=label, align="left")
    field = cmds.textField(parent=row, text=str(value))
    if pick:
        cmds.button(parent=row, label="Pick", command=partial(pick, field))
    else:
        cmds.text(parent=row, label="")
    return field


def _remove(row, *unused):
    if row in STATE["rows"]:
        STATE["rows"].remove(row)
    cmds.deleteUI(row["frame"])


def Add(listUI, item=None, *unused):
    item = item or {}
    frame = cmds.frameLayout(parent=listUI, label="Slide Surface Surface / Joint Chains", collapsable=True, collapse=False, marginWidth=5, marginHeight=5)
    col = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=5)
    row = {"frame": frame}
    row["component"] = _field(col, "Component", item.get("component", ""))
    row["surface"] = _field(col, "NURBS Surface", item.get("surface", ""), _pick_surface)
    joint_row = cmds.rowLayout(parent=col, numberOfColumns=3, columnWidth3=(112, 227, 52))
    cmds.text(parent=joint_row, label="Root Joints", align="left")
    roots = item.get("roots") or []
    row["roots"] = cmds.scrollField(parent=joint_row, height=78, text="\n".join(roots), wordWrap=False)
    cmds.button(parent=joint_row, label="Add", command=partial(_pick_roots, row["roots"]))
    curve_rows = [root + " = " + curve for root, curve
                  in (item.get("curves") or {}).items()]
    curve_row = cmds.rowLayout(parent=col, numberOfColumns=2, columnWidth2=(112, 279))
    cmds.text(parent=curve_row, label="Curve Overrides", align="left")
    row["curves"] = cmds.scrollField(parent=curve_row, height=58, text="\n".join(curve_rows), wordWrap=False)
    cmds.text(parent=col, label="Leave blank for <RootJoint>_curve. FK nodes use Slide Surface names.", align="left")
    cmds.button(parent=col, label="Remove Component", command=partial(_remove, row))
    STATE["rows"].append(row)
    return row


def _collect():
    if not STATE["top"]:
        raise ValueError("Slide Surface: open the module form first")
    config = {
        "version": 1,
        "group": cmds.textField(STATE["top"]["group"], query=True, text=True).strip(),
        "driverGroup": cmds.textField(STATE["top"]["driverGroup"], query=True, text=True).strip(),
        "items": []}
    for row in STATE["rows"]:
        component = cmds.textField(row["component"], query=True, text=True).strip()
        surface = cmds.textField(row["surface"], query=True, text=True).strip()
        roots = [x.strip() for x in re.split(r"[,;\n]+",
                 cmds.scrollField(row["roots"], query=True, text=True)) if x.strip()]
        curves = {}
        raw = cmds.scrollField(row["curves"], query=True, text=True)
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                raise ValueError("Slide Surface: Curve Override must be RootJoint = CurveName")
            root, curve = [part.strip() for part in line.split("=", 1)]
            if not root or not curve or root in curves:
                raise ValueError("Slide Surface: invalid/duplicate Curve Override: " + line)
            curves[root] = curve
        if not component or not surface or not roots or len(set(roots)) != len(roots):
            raise ValueError("Slide Surface: Component, Surface and unique Root Joints are required")
        if any(root not in roots for root in curves):
            raise ValueError("Slide Surface: Curve Override root must be listed in Root Joints")
        config["items"].append(dict(component=component, surface=surface,
                                    roots=roots, curves=curves))
    _slide_surface_arguments(config)
    return config


def _slide_surface_arguments(config):
    # Read scene inputs.
    dict_setup, surface_names, curve_names = {}, {}, {}
    if not config.get("group") or not config.get("driverGroup"):
        raise ValueError("Slide Surface: Contain and Driver Group are required")
    for entry in config["items"]:
        comp = str(entry["component"]).strip()
        surface = str(entry["surface"]).strip()
        roots = [str(root).strip() for root in entry["roots"]]
        if not comp or not surface or not roots or any(not root for root in roots):
            raise ValueError("Slide Surface: Component, Surface and Root Joints are required")
        if comp in surface_names and surface_names[comp] != surface:
            raise ValueError("Slide Surface: one Component cannot use two Surfaces: " + comp)
        surface_names[comp] = surface
        for root in roots:
            if any(root in previous for previous in dict_setup.values()):
                raise ValueError("Slide Surface: a root joint can only appear once: " + root)
        dict_setup.setdefault(comp, []).extend(roots)
        for root, curve in entry.get("curves", {}).items():
            if root not in roots:
                raise ValueError("Slide Surface: Curve Override has unknown root: " + root)
            curve_names[root] = curve
    if not dict_setup:
        raise ValueError("Slide Surface: add at least one Component")
    return {"dict_setup": dict_setup, "surface_names": surface_names,
            "curve_names": curve_names,
            "group_name": config["driverGroup"], "contain": config["group"]}


def Save(data, *unused):
    config = _collect()
    with open(_data_path(data), "w", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, separators=(",", ":"))
    return config


def Load(data, listUI, *unused):
    for child in cmds.layout(listUI, query=True, childArray=True) or []:
        cmds.deleteUI(child)
    STATE["rows"][:] = []
    config = _read_saved(data)
    for key in ("group", "driverGroup"):
        cmds.textField(STATE["top"][key], edit=True, text=config.get(key, ""))
    for entry in config["items"]:
        Add(listUI, entry)
    if not config["items"]:
        Add(listUI)


def _literal(value):
    return json.dumps(value, ensure_ascii=False)


def _mapping_source(name, mapping):
    return "    " + name + " = " + _literal(mapping)


def buildScript(config):
    arguments = _slide_surface_arguments(config)
    main = inspect.getsource(_gragas_main).rstrip().replace("def _gragas_main():", "def main():", 1)
    main = main.replace('name = "Hair_Driver_Group"', "name = " + _literal(arguments["group_name"]), 1)
    main = main.replace('pm.parent(hair_group, "RigUtil")', "pm.parent(hair_group, " + _literal(arguments["contain"]) + ")", 1)
    setup = _mapping_source("dict_setup", arguments["dict_setup"])
    surfaces = {key: value for key, value in arguments["surface_names"].items() if value != key + "_Surface"}
    curves = {key: value for key, value in arguments["curve_names"].items() if value != key + "_curve"}
    if surfaces:
        setup += "\n" + _mapping_source("surface_names", surfaces)
        main = main.replace('attachToSurface(f"{comp}_Surface",', 'attachToSurface(surface_names.get(comp, f"{comp}_Surface"),', 1)
    if curves:
        setup += "\n" + _mapping_source("curve_names", curves)
        main = main.replace('target_curve = f"{root}_curve"', 'target_curve = curve_names.get(root, f"{root}_curve")', 1)
    start = main.index("    dict_setup = {")
    end = main.index("}", start) + 1
    main = main[:start] + setup + main[end:]
    source = "\n\n".join(inspect.getsource(fn).rstrip() for fn in (createCpos, attachToSurface, followParent))
    script = "import pymel.core as pm\nimport extensions.utils.rigs as rigUtils\n\n" + source + "\n\n" + main + '\n\nif __name__ == "__main__":\n    main()\n'
    compile(script, "Python_Scene_Pattern_RigSlideSurfaceFnc.py", "exec")
    return script


def Run(data, *unused):
    script = buildScript(_read_saved(data))
    exec(compile(script, "RigSlideSurfaceFnc", "exec"), {"__name__": "__main__"})


def ExportPython(data, *unused):
    script = buildScript(_read_saved(data))
    filename = "Python_Scene_Pattern_RigSlideSurfaceFnc.py"
    output = os.path.join(os.path.dirname(_data_path(data)), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(script)
    return output


def ImportJson(data, listUI, *unused):
    paths = cmds.fileDialog2(fileMode=1, fileFilter="JSON (*.json)", caption="Import SlideSurfaceFunc JSON")
    if paths:
        config = NLTA_General.readJsonFile(paths[0])
        if config.get("version") != 1:
            raise ValueError("Slide Surface: unsupported JSON settings version")
        _slide_surface_arguments(config)
        with open(_data_path(data), "w", encoding="utf-8") as stream:
            json.dump(config, stream, ensure_ascii=False, separators=(",", ":"))
        Load(data, listUI)


def OpenExportFolder(data, *unused):
    folder = os.path.dirname(_data_path(data))
    if hasattr(os, "startfile"):
        os.startfile(folder)
    else:
        cmds.warning("Slide Surface: export folder " + folder)


def Form(data, *unused):
    layout = NLTA_General.LoadModule("Scene_Form").Create(data)
    STATE["list"] = layout["listUI"]
    buttons = cmds.rowLayout(parent=layout["buttonUI"], numberOfColumns=5, columnWidth5=(82, 82, 82, 82, 104))
    STATE["top"].clear()
    top = cmds.frameLayout(parent=STATE["list"], label="Slide Surface Settings", collapsable=True, collapse=False, marginWidth=5)
    col = cmds.columnLayout(parent=top, adjustableColumn=True)
    saved = _read_saved(data)
    STATE["top"]["group"] = _field(col, "Contain", saved.get("group", "RigUtil"))
    STATE["top"]["driverGroup"] = _field(
        col, "Driver Group", saved.get("driverGroup", "Hair_Driver_Group"))
    cmds.text(parent=col, label="Requires existing: NURBS Surface, root joint chains,", align="left")
    cmds.text(parent=col, label="*_curve and Slide Surface *_FK / *_FK_Pos / *_FK_Target nodes.", align="left")
    listUI = cmds.columnLayout(parent=STATE["list"], adjustableColumn=True)
    cmds.button(parent=buttons, label="Add", command=lambda *_: Add(listUI))
    cmds.button(parent=buttons, label="Import JSON", command=partial(ImportJson, data, listUI))
    cmds.button(parent=buttons, label="Save", command=partial(Save, data))
    cmds.button(parent=buttons, label="Run", command=lambda *_: (Save(data), Run(data)))
    export_button = cmds.button( parent=buttons, label="Export Py", command=lambda *_: (Save(data), ExportPython(data)))
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", command=partial(OpenExportFolder, data))
    cmds.setParent("..", menu=True)
    Load(data, listUI)
    return layout


def createCpos(surf, node, connect=False):
    # Closest point
    cpos = pm.createNode('closestPointOnSurface', n='%s_cpos' %node)
    pm.connectAttr('%s.worldSpace' %surf, '%s.inputSurface' %cpos, f=True)
    pos = pm.xform(node, q=True, ws=True, t=True)
    pm.setAttr('%s.inPosition' %cpos, pos[0], pos[1], pos[2])
    if connect:
        dcm = pm.createNode('decomposeMatrix', n='{0}_dcm'.format(node))
        pm.connectAttr('{0}.worldMatrix[0]'.format(node), '{0}.inputMatrix'.format(dcm), f=True)
        pm.connectAttr('{0}.outputTranslate'.format(dcm), '{0}.inPosition'.format(cpos), f=True)
    return cpos

def attachToSurface(meshOrSurface, node, parent, name=""):
    if pm.nodeType(meshOrSurface) == 'transform':
        meshOrSurface = pm.listRelatives(meshOrSurface, s=True, type='nurbsSurface')[0]
    cp = createCpos(meshOrSurface, node)
    # UV
    paramU = pm.getAttr('%s.parameterU' %cp)
    paramV = pm.getAttr('%s.parameterV' %cp)
    pm.delete(cp)
    if not name:
        name = node
    # Create follicle
    follicleShape = pm.createNode('follicle', n=f"{name}_follicleShape")
    follicleTransform = pm.listRelatives(follicleShape, p=True)[0]
    follicleTransform = pm.rename(follicleTransform, f"{name}_follicle")
    pm.hide(follicleShape)
    # Follicle connections
    pm.connectAttr('%s.worldSpace[0]' %meshOrSurface, '%s.inputSurface' %follicleShape, f=True)
    pm.connectAttr('%s.worldMatrix[0]' %meshOrSurface, '%s.inputWorldMatrix' %follicleShape, f=True)
    pm.connectAttr('%s.outTranslate' %follicleShape, '%s.translate' %follicleTransform, f=True)
    pm.connectAttr('%s.outRotate' %follicleShape, '%s.rotate' %follicleTransform, f=True)
    pm.setAttr('%s.parameterU' %follicleShape, paramU)
    pm.setAttr('%s.parameterV' %follicleShape, paramV)
    pm.parent(follicleTransform, parent)
    return [follicleTransform, follicleShape]

def followParent(child_joint, parent_joint):
    # Parent follow matrices
    parentCtrl = f"{parent_joint}_FK"
    parentPos = f"{parentCtrl}_Pos"
    childCtrl = f"{child_joint}_FK"
    childPos = f"{childCtrl}_Pos"
    childTarget = f"{childCtrl}_Target"
    # Create utility node
    child_local = pm.createNode('multMatrix', name=f"{child_joint}_local_multMatrix")
    child_world = pm.createNode('multMatrix', name=f"{child_joint}_world_multMatrix")
    child_local_from_Pos = pm.createNode('multMatrix', name=f"{child_joint}_local_from_POS_multMatrix")
    child_decomp = pm.createNode('decomposeMatrix', name=f"{child_joint}_decomposeMatrix")
    child_blend = pm.createNode('blendMatrix', name=f"{child_joint}_blendMatrix")
    # Make connections
    pm.connectAttr(f"{childPos}.worldMatrix[0]", f"{child_local}.matrixIn[0]", force=True)
    pm.connectAttr(f"{parentPos}.worldInverseMatrix[0]", f"{child_local}.matrixIn[1]", force=True)
    pm.connectAttr(f"{child_local}.matrixSum", f"{child_world}.matrixIn[0]", force=True)
    pm.connectAttr(f"{parentCtrl}.worldMatrix[0]", f"{child_world}.matrixIn[1]", force=True)
    pm.connectAttr(f"{child_world}.matrixSum", f"{child_local_from_Pos}.matrixIn[0]", force=True)
    pm.connectAttr(f"{childPos}.worldInverseMatrix[0]", f"{child_local_from_Pos}.matrixIn[1]", force=True)
    pm.connectAttr(f"{child_local_from_Pos}.matrixSum", f"{child_blend}.inputMatrix", force=True)
    pm.connectAttr(f"{child_blend}.outputMatrix", f"{child_decomp}.inputMatrix", force=True)
    pm.connectAttr(f"{child_decomp}.outputTranslate", f"{childTarget}.translate", force=True)
    pm.connectAttr(f"{child_decomp}.outputRotate", f"{childTarget}.rotate", force=True)

def _gragas_main():
    # Driver group
    hair_group = pm.group(name = "Hair_Driver_Group", empty = 1)
    pm.parent(hair_group, "RigUtil")
    dict_setup = {
                    "Mustache":["C_Mustache1", "L_Mustache1", "R_Mustache1"],
                    "Hair":["L_Hair1", "C_Hair1", "R_Hair1"],
                    "L_Hair":["L_HairA1","L_HairB1"],
                    "R_Hair":["R_HairA1","R_HairB1"]}
    for comp, root_joints in dict_setup.items():
        for root in root_joints:
            # Joint chain
            all_joints = [root]
            children = pm.listRelatives(root, type="joint", allDescendents=True) or []
            if children:
                children.reverse()
                for child in children:
                    all_joints.append(child)
            grp_zero = pm.createNode("transform", name=f"Grp_{root}_spIK_scaleConnect")
            pm.matchTransform(grp_zero, root)
            grp_zero.setParent(hair_group)
            rigUtils.connectUniformScaleTag(grp_zero.name())
            # Driver and spline joints
            driver_joints = []
            spIK_joints = []
            follicle_shapes = []
            for joint in all_joints:
                follicleTransform, follicleShape = attachToSurface(f"{comp}_Surface", joint, hair_group, name=joint)
                follicle_shapes.append(follicleShape)
                driver_joint = pm.duplicate(joint, parentOnly=True, n=f"{joint}_driver")[0]
                spIK_joint = pm.duplicate(joint, parentOnly=True, n=f"{joint}_spIK")[0]
                driver_joints.append(driver_joint)
                spIK_joints.append(spIK_joint)
                pm.parent(driver_joint, follicleTransform)
                pm.parent(spIK_joint, grp_zero)
            # Spline chain
            number_of_joints = len(spIK_joints)
            for i in range(number_of_joints-1, 0, -1):
                pm.parent(spIK_joints[i], spIK_joints[i-1])
            # Spline IK
            start_joint = spIK_joints[0]
            end_joint = spIK_joints[-1]
            target_curve = f"{root}_curve"
            ik_result = pm.ikHandle(name=f"{root}_ikh", startJoint=start_joint, endEffector=end_joint, sol="ikSplineSolver", curve=target_curve, createCurve=False, parentCurve=False)
            ik_handle = ik_result[0]
            effector = ik_result[1]
            effector = pm.rename(effector, f"{root}_effector")
            pm.parent(ik_handle, target_curve, hair_group)
            # Advanced twist
            start_driver = driver_joints[0]
            end_driver = driver_joints[-1]
            pm.setAttr(f"{ik_handle}.dTwistControlEnable", 1)
            pm.setAttr(f"{ik_handle}.dWorldUpType", 4)
            pm.setAttr(f"{ik_handle}.dForwardAxis", 0)
            pm.setAttr(f"{ik_handle}.dWorldUpAxis", 3)
            pm.setAttr(f"{ik_handle}.dWorldUpVectorY", 0)
            pm.setAttr(f"{ik_handle}.dWorldUpVectorEndY", 0)
            pm.setAttr(f"{ik_handle}.dWorldUpVectorZ", 1)
            pm.setAttr(f"{ik_handle}.dWorldUpVectorEndZ", 1)
            pm.connectAttr(f"{start_driver}.worldMatrix[0]", f"{ik_handle}.dWorldUpMatrix", force=True)
            pm.connectAttr(f"{end_driver}.worldMatrix[0]", f"{ik_handle}.dWorldUpMatrixEnd", force=True)
            # Bind curve
            pm.skinCluster(driver_joints, target_curve, toSelectedBones=True)
            # FK follow
            for i in range(number_of_joints-1, 0, -1):
                child_joint = all_joints[i]
                parent_joint = all_joints[i-1]
                followParent(child_joint, parent_joint)
        for root in root_joints:
            all_joints = [root]
            children = pm.listRelatives(root, type="joint", allDescendents=True) or []
            if children:
                children.reverse()
                for child in children:
                    all_joints.append(child)
            # Shared bias
            root_fk_control = f"{root}_FK"
            if not pm.attributeQuery("bias", node=root_fk_control, exists=True):
                pm.addAttr(root_fk_control, longName="bias", min=0, max=1, dv=1, k=True)
            reverse_node = pm.createNode("reverse", name=f"{root}_bias_rev")
            pm.connectAttr(f"{root_fk_control}.bias", reverse_node.inputX, f=True)
            for joint in all_joints:
                spIK_joint = f"{joint}_spIK"
                fk_control_pos = f"{joint}_FK_Pos"
                parent_fk_control_pos = pm.listRelatives(fk_control_pos, parent=True)[0]
                parent_driver = pm.createNode("transform", name=f"Grp_{joint}_bias_rev_driver")
                pm.matchTransform(parent_driver, joint)
                parent_driver.setParent(parent_fk_control_pos)
                pc = pm.parentConstraint(spIK_joint, parent_driver, fk_control_pos, name=f"{fk_control_pos}_parentConstraint", maintainOffset=True)
                pm.connectAttr(f"{root_fk_control}.bias", f"{pc}.{joint}_spIKW0", f=True)
                pm.connectAttr(reverse_node.outputX, f"{pc}.{parent_driver}W1", f=True)
                if joint != root:
                    pm.connectAttr(reverse_node.outputX, f"{joint}_blendMatrix.target[0].weight", f=True)
