import os
import math
import json
import inspect
import importlib.util
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General

# Reuse the input form with isolated state.
_path = os.path.join(os.path.dirname(__file__), "Scene_Pattern_RigAutoSkirtFunc.py")
_spec = importlib.util.spec_from_file_location("_nlta_rig_auto_fnc_form", _path)
_form = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_form)
STATE = _form.STATE

# This form edits data only; do not modify the full module graph.
_form.applyLiveSubItem = lambda *args, **kwargs: False
_form.buildLiveAddedSubItem = lambda *args, **kwargs: False
_form.setSubItemMute = lambda *args, **kwargs: False
_form.readSubItemMute = lambda *args, **kwargs: False
_form.liveFollicleSize = lambda *args, **kwargs: None
_form.restoreJsonLive = lambda data, list_ui, *args: _form.Load(data, list_ui)


def DefaultSetting(path, *args):
    module_name = "Scene_Pattern_RigAutoFnc"
    return dict(ext="json", path=os.path.join(path, module_name + ".json"),
                moduleName=module_name, order=0, title="Rig Auto Fnc",
                name="Rig Auto Fnc", id=datetime.now().strftime("%Y%m%d%H%M%S"))


def dataPath(data):
    return _form.dataPath(data)


def getData(data):
    return _form.getData(data)


def saveSettings(data, *args):
    config = _form.readUi()
    config["originalStyle"] = cmds.optionMenu(STATE["style"], q=True, value=True)
    with open(dataPath(data), "w", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, separators=(",", ":"))
    return config


_form.saveSettings = saveSettings


def importJson(data, list_ui, *args):
    paths = cmds.fileDialog2(fileMode=1, fileFilter="JSON (*.json)", caption="Import AutoSkirtFunc JSON")
    if not paths:
        return
    with open(paths[0], encoding="utf-8") as stream:
        config = json.load(stream)
    if config.get("version") != 2 or not config.get("items"):
        cmds.warning("Rig Auto Fnc: select an AutoSkirtFunc version 2 JSON")
        return
    with open(dataPath(data), "w", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, separators=(",", ":"))
    _form.Load(data, list_ui)
    cmds.optionMenu(STATE["style"], e=True, value=config.get("originalStyle", "Diana"))


def _short(node):
    return node.rsplit("|", 1)[-1]


def _point(shape, v):
    import maya.api.OpenMaya as om
    selection = om.MSelectionList()
    selection.add(shape)
    surface = om.MFnNurbsSurface(selection.getDagPath(0))
    point = surface.getPointAtParam(0.5, v, om.MSpace.kWorld)
    return (point.x, point.y, point.z)


def _distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def _resolve(config, reader):
    sphere = _short(reader["sphere"])
    shape = cmds.listRelatives(sphere, shapes=True, noIntermediate=True, type="nurbsSurface", fullPath=True)[0]
    controls = [_short(node) for node in reader["joints"]]
    refs = []
    for index, (control, entries) in enumerate(zip(controls, reader["subItems"])):
        for sub_index, sub in enumerate(entries, 1):
            name = control if sub_index == 1 else control + "_Sub{:02d}".format(sub_index)
            ref = sphere + "_" + name + "_ref_follicle"
            v = sub.get("refV")
            if v is None:
                if cmds.objExists(ref + ".refV"):
                    v = cmds.getAttr(ref + ".refV")
                elif cmds.objExists(ref):
                    follicle = cmds.listRelatives(ref, shapes=True, type="follicle")[0]
                    v = cmds.getAttr(follicle + ".parameterV")
                elif index < len(reader.get("refV", [])):
                    v = reader["refV"][index]
                else:
                    v = _form.sourceRefVFromDriven(sphere, control)
            refs.append(dict(control=control, name=name, index=index, sub_index=sub_index,
                             ref=ref, v=float(v), spec=sub))
    base = [r for r in refs if r["sub_index"] == 1]
    for r in refs:
        sub = r["spec"]
        maximum = float(sub.get("maxDistance", 0))
        if maximum == 0:
            plug = r["ref"] + ".maxDistance"
            if cmds.objExists(plug):
                maximum = float(cmds.getAttr(plug))
            else:
                position = _point(shape, r["v"])
                bounds = cmds.exactWorldBoundingBox(sphere)
                radius = max(bounds[i+3]-bounds[i] for i in range(3)) * 0.5
                maximum = max(min((_distance(position, _point(shape, other["v"]))
                                   for other in base if other["index"] != r["index"]),
                                  default=radius), 0.001)
        minimum = float(sub.get("minDistance", 0))
        if minimum >= maximum:
            raise ValueError("Rig Auto Fnc: Min Distance must be below Max Distance: " + r["name"])
        r["range"] = (minimum, maximum)
    return refs


def _existing_target(control):
    target = control + "_Target"
    if cmds.objExists(target):
        parents = cmds.ls(control, long=True) or []
        if len(parents) == 1 and target in parents[0].split("|")[:-1]:
            return target
    return None


def buildScript(config):
    lines = ["import maya.cmds as cmds", "", "", "def main():"]
    emit = lambda line="": lines.append("    " + line if line else "")
    emit("rig_group = " + repr(config.get("group", "RigUtil")))
    style = config.get("originalStyle", "Diana")
    targets = {}
    target_signals = {}
    follow_attrs = {}
    for reader in config["items"]:
        refs = _resolve(config, reader)
        sphere = _short(reader["sphere"])
        if not refs:
            continue
        emit()
        emit("# " + str(reader["id"]).replace("\n", " ").replace("\r", " "))
        emit("pose_reader = " + repr(sphere))
        emit("skirt_joints = " + repr([r["name"] for r in refs]))
        emit("ref_parameterV = " + repr([r["v"] for r in refs]))
        emit("min_max_distance = " + repr([r["range"] for r in refs]))
        emit("raise_start_angle = " + repr([float(r["spec"].get("startAngle", 10)) for r in refs]))
        emit("cp_follicle_shape, cpos = createPoseReaderSystem(pose_reader, {}, {}, rig_group)".format(repr(_short(reader["parent"])), repr(_short(reader["end"]))))
        emit("raise_influence_nodes = createSkirtRigSystem(pose_reader, cp_follicle_shape, cpos, skirt_joints, ref_parameterV, min_max_distance, raise_start_angle, rig_group)")
        for i, r in enumerate(refs):
            control, sub = r["control"], r["spec"]
            prefix = sphere + "_" + r["name"]
            core = prefix + "_md_RaiseInfluence"
            raw = prefix + "_md_Raise.outputX"
            if sub.get("reverseU"):
                emit("cmds.setAttr({!r}, 180)".format(prefix + "_Remap_Raise.outputMin"))
                emit("cmds.setAttr({!r}, 0)".format(prefix + "_Remap_Raise.outputMax"))
            if style == "Akali":
                emit("neutral_value = cmds.getAttr({!r})".format(raw))
                zero = prefix + "_ZeroOut_PMA"
                emit("zero = cmds.createNode('plusMinusAverage', n={!r})".format(zero))
                emit("cmds.setAttr(zero + '.operation', 2)")
                emit("cmds.connectAttr({!r}, zero + '.input1D[0]')".format(raw))
                emit("cmds.setAttr(zero + '.input1D[1]', neutral_value)")
                emit("cmds.connectAttr(zero + '.output1D', {!r}, force=True)".format(core + ".input1X"))
            follow = control + ".AutoFollow"
            if control not in follow_attrs:
                emit("if not cmds.attributeQuery('AutoFollow', node={!r}, exists=True):".format(control))
                emit("    cmds.addAttr({!r}, ln='AutoFollow', at='double', min=0, max=2, dv=1, k=True)".format(control))
                follow_attrs[control] = follow
            emit("cmds.connectAttr({!r}, raise_influence_nodes[{}] + '.input2X')".format(follow, i))
            signal = core + ".outputX"
            factor = float(sub.get("strength", 1)) * (-1 if sub.get("invertRotate") else 1)
            if factor != 1:
                md = prefix + "_Output_MD"
                emit("md = cmds.createNode('multiplyDivide', n={!r})".format(md))
                emit("cmds.connectAttr({!r}, md + '.input1X')".format(signal))
                emit("cmds.setAttr(md + '.input2X', {!r})".format(factor))
                signal = md + ".outputX"
            if control not in targets:
                target = _existing_target(control)
                if target is None:
                    target = control + "_RigAutoFnc_Target"
                    emit("matrix = cmds.xform({!r}, q=True, ws=True, m=True)".format(control))
                    emit("parents = cmds.listRelatives({!r}, parent=True, fullPath=True)".format(control))
                    emit("space = cmds.createNode('transform', n={!r})".format(control + "_RigAutoFnc_Space"))
                    emit("cmds.xform(space, ws=True, m=matrix)")
                    emit("if parents:")
                    emit("    space = cmds.parent(space, parents[0], absolute=True)[0]")
                    emit("target = cmds.createNode('transform', n={!r}, parent=space)".format(target))
                    emit("cmds.parent({!r}, target, absolute=True)".format(control))
                targets[control] = target
            channel = targets[control] + "." + sub.get("outputType", "rotate") + sub.get("axis", "Z").upper()[-1]
            target_signals.setdefault(channel, []).append(signal)
    emit()
    emit("# Connect lift influence")
    for channel, signals in target_signals.items():
        signal = signals[0]
        if len(signals) > 1:
            name = channel.replace(".", "_") + "_Sum"
            emit("summation = cmds.createNode('plusMinusAverage', n={!r})".format(name))
            for i, src in enumerate(signals):
                emit("cmds.connectAttr({!r}, summation + '.input1D[{}]')".format(src, i))
            signal = name + ".output1D"
        emit("cmds.connectAttr({!r}, {!r})".format(signal, channel))
    lines.extend(["", "", inspect.getsource(createPoseReaderSystem).rstrip(),
                  "", "", inspect.getsource(createSkirtRigSystem).rstrip(),
                  "", "", 'if __name__ == "__main__":', "    main()", ""])
    script = "\n".join(lines)
    compile(script, "Python_Scene_Pattern_RigAutoFnc.py", "exec")
    return script


def ExportPython(data, *args):
    config = getData(data) if data.get("_batch_export_from_saved") else saveSettings(data)
    script = buildScript(config)
    output = os.path.join(os.path.dirname(dataPath(data)), "Python_Scene_Pattern_RigAutoFnc.py")
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(script)
    return output


def Run(data, *args):
    script = buildScript(getData(data))
    exec(compile(script, "RigAutoFnc", "exec"), {"__name__": "__main__"})


def runFromForm(data, *args):
    saveSettings(data)
    return Run(data)


def Form(data, *args):
    ui = NLTA_General.LoadModule("Scene_Form").Create(data)
    buttons, list_ui = ui["buttonUI"], ui["listUI"]
    cmds.rowColumnLayout(parent=buttons, numberOfColumns=5)
    cmds.button(label="Add", width=70, command=_form.addEmpty)
    cmds.button(label="Import JSON", width=90, command=partial(importJson, data, list_ui))
    cmds.button(label="Save", width=70, command=partial(saveSettings, data))
    cmds.button(label="Run", width=70, command=partial(runFromForm, data))
    export = cmds.button(label="Export Py", width=80, command=partial(ExportPython, data))
    cmds.popupMenu(parent=export, button=3)
    cmds.menuItem(label="Open Folder", command=partial(_form.OpenExportFolder, data))
    style = cmds.optionMenu(parent=buttons, label="Original Style")
    cmds.menuItem(parent=style, label="Diana")
    cmds.menuItem(parent=style, label="Akali")
    cmds.button(parent=buttons, label="Rebuild Sphere UV 0-1", command=_form.rebuildSphereUVButton)
    cmds.text(parent=buttons, label="Edit data only. Run / Export on a clean rig.", align="left")
    _form.Load(data, list_ui)
    STATE["style"] = style
    cmds.optionMenu(style, e=True, value=getData(data).get("originalStyle", "Diana"))


def createPoseReaderSystem(
    poseReader,
    poseReader_constraint_target,
    closest_point_ref_object,
    rig_group="RigUtil",
):

    # Create a locator that follows the reference object.
    # We use the locator's world position to find the closest point on the pose-reader sphere.
    target_loc_group = cmds.createNode("transform", n=f"{poseReader}_Target_Loc_Group")
    target_loc = cmds.spaceLocator(n=f"{poseReader}_Target_Loc")[0]
    target_loc_shape = cmds.listRelatives(target_loc, shapes=True, fullPath=False)[0]

    cmds.parent(target_loc, target_loc_group)
    cmds.parent(target_loc_group, rig_group)
    cmds.parentConstraint(closest_point_ref_object, target_loc_group, mo=False)

    # Pose reader sphere setup
    # Constrain the pose reader transform to a target (usually the pelvis)
    # Use closestPointOnSurface to find parameterU/V from the target locator position
    pose_reader = poseReader
    pose_reader_shape = cmds.listRelatives(pose_reader, shapes=True, fullPath=False)[0]
    cmds.parentConstraint(poseReader_constraint_target, pose_reader, mo=True)
    cpos = cmds.createNode("closestPointOnSurface", n=f"{poseReader}_cpos")
    cmds.connectAttr(f"{target_loc_shape}.worldPosition[0]", f"{cpos}.inPosition")
    cmds.connectAttr(f"{pose_reader_shape}.worldSpace[0]", f"{cpos}.inputSurface")

    # Create a closest point follicle that stays on the sphere following target locator
    cp_follicleShape = cmds.createNode("follicle", name=f"{poseReader}_CP_follicleShape")
    cp_follicleTransform = cmds.listRelatives(cp_follicleShape, parent=True, fullPath=False)[0]
    cp_follicleTransform = cmds.rename(cp_follicleTransform, f"{poseReader}_CP_follicle")

    cmds.parent(cp_follicleTransform, rig_group)

    cmds.connectAttr(f"{pose_reader_shape}.worldSpace[0]", f"{cp_follicleShape}.inputSurface")
    cmds.connectAttr(f"{pose_reader_shape}.worldMatrix[0]", f"{cp_follicleShape}.inputWorldMatrix")
    cmds.connectAttr(f"{cp_follicleShape}.outTranslate", f"{cp_follicleTransform}.translate")
    cmds.connectAttr(f"{cp_follicleShape}.outRotate", f"{cp_follicleTransform}.rotate")

    cmds.connectAttr(f"{cpos}.parameterU", f"{cp_follicleShape}.parameterU")
    cmds.connectAttr(f"{cpos}.parameterV", f"{cp_follicleShape}.parameterV")

    return cp_follicleShape, cpos


def createSkirtRigSystem(
    pose_reader,
    cp_follicleShape,
    cpos,
    skirt_joints,
    ref_parameterV,
    min_max_distance,
    raise_start_angle,
    rig_group="RigUtil",
):

    """
    For each skirt joint, builds a small network that outputs a "raise influence" value.
    The influence is based on:
    - Distance between a fixed reference follicle and a moving (equator) follicle
    - A raise angle derived from the pose-reader parameterU (clamped by raiseStartAngle)
    """

    pose_reader_shape = cmds.listRelatives(pose_reader, shapes=True, fullPath=False)[0]
    raise_influence_nodes = []

    # skirt joint range network
    for i, skirt_joint in enumerate(skirt_joints):

        equator_follicles = []

        # Two follicles per joint
        # ref follicle: fixed U,V position (defines the "rest" location on the sphere)
        # equator follicle: param V follows the pose reader and U is fixed at 0.5(equator)
        for follicle_type in ["ref", "equator"]:
            follicleShape = cmds.createNode("follicle", name=f"{pose_reader}_{skirt_joint}_{follicle_type}_follicleShape")
            follicleTransform = cmds.listRelatives(follicleShape, parent=True, fullPath=False)[0]
            follicleTransform = cmds.rename(follicleTransform, f"{pose_reader}_{skirt_joint}_{follicle_type}_follicle")

            equator_follicles.append(follicleTransform)
            cmds.parent(follicleTransform, rig_group)

            cmds.connectAttr(f"{pose_reader_shape}.worldSpace[0]", f"{follicleShape}.inputSurface")
            cmds.connectAttr(f"{pose_reader_shape}.worldMatrix[0]", f"{follicleShape}.inputWorldMatrix")
            cmds.connectAttr(f"{follicleShape}.outTranslate", f"{follicleTransform}.translate")
            cmds.connectAttr(f"{follicleShape}.outRotate", f"{follicleTransform}.rotate")

            cmds.setAttr(f"{follicleShape}.parameterU", 0.5)

            if follicle_type == "ref":
                cmds.setAttr(f"{follicleShape}.parameterV", ref_parameterV[i])
                cmds.addAttr(follicleTransform, ln="minDistance", at="double", min=0, max=max(2, min_max_distance[i][0]), dv=0, k=True)
                cmds.addAttr(follicleTransform, ln="maxDistance", at="double", min=0, max=max(2, min_max_distance[i][1]), dv=1.5, k=True)
                cmds.addAttr(follicleTransform, ln="raiseStartAngle", at="double", min=0, max=180, dv=10, k=True)
                # cmds.addAttr(follicleTransform, ln="falloff", at="double", min=0, max=10, dv=1, k=True)
            else:
                cmds.connectAttr(f"{cpos}.parameterV", f"{follicleShape}.parameterV")

        # Distance network
        # Measure distance between ref and equator follicles, then remap it so
        # - closer -> 1
        # - farther -> 0
        # This remapped output is used as a multiplier for skirt raise.
        distance = cmds.createNode("distanceBetween", n=f"{pose_reader}_{skirt_joint}_Distance")
        remap_distance = cmds.createNode("remapValue", n=f"{pose_reader}_{skirt_joint}_Remap_Distance")

        cmds.connectAttr(f"{equator_follicles[0]}.worldMatrix[0]", f"{distance}.inMatrix1")
        cmds.connectAttr(f"{equator_follicles[1]}.worldMatrix[0]", f"{distance}.inMatrix2")

        cmds.connectAttr(f"{distance}.distance", f"{remap_distance}.inputValue")
        cmds.connectAttr(f"{equator_follicles[0]}.minDistance", f"{remap_distance}.inputMin")
        cmds.connectAttr(f"{equator_follicles[0]}.maxDistance", f"{remap_distance}.inputMax")
        cmds.setAttr(f"{remap_distance}.outputMin", 1)
        cmds.setAttr(f"{remap_distance}.outputMax", 0)

        # Raise network
        # Convert the CP follicle's parameterU into a 0~180 range, clamp it,
        # then subtract raiseStartAngle so we get a "raise amount" past the start angle.
        remap_raise = cmds.createNode("remapValue", n=f"{pose_reader}_{skirt_joint}_Remap_Raise")
        clamp_raise = cmds.createNode("clamp", n=f"{pose_reader}_{skirt_joint}_Clamp_Raise")
        pma_raise = cmds.createNode("plusMinusAverage", n=f"{pose_reader}_{skirt_joint}_pma_Raise")

        cmds.connectAttr(f"{cp_follicleShape}.parameterU", f"{remap_raise}.inputValue")
        cmds.setAttr(f"{remap_raise}.outputMin", 0)
        cmds.setAttr(f"{remap_raise}.outputMax", 180)

        cmds.connectAttr(f"{remap_raise}.outValue", f"{clamp_raise}.inputR")
        cmds.connectAttr(f"{equator_follicles[0]}.raiseStartAngle", f"{clamp_raise}.minR")
        cmds.setAttr(f"{clamp_raise}.maxR", 180)

        cmds.setAttr(f"{pma_raise}.operation", 2)
        cmds.connectAttr(f"{clamp_raise}.outputR", f"{pma_raise}.input1D[0]")
        cmds.connectAttr(f"{clamp_raise}.minR", f"{pma_raise}.input1D[1]")

        # Final output based on distance:
        # raiseAmount * distanceMultiplier -> influence
        md_raise = cmds.createNode("multiplyDivide", n=f"{pose_reader}_{skirt_joint}_md_Raise")
        md_raise_influence = cmds.createNode("multiplyDivide", n=f"{pose_reader}_{skirt_joint}_md_RaiseInfluence")
        raise_influence_nodes.append(md_raise_influence)

        cmds.connectAttr(f"{pma_raise}.output1D", f"{md_raise}.input1X")
        cmds.connectAttr(f"{remap_distance}.outValue", f"{md_raise}.input2X")

        cmds.connectAttr(f"{md_raise}.outputX", f"{md_raise_influence}.input1X")

        # Set 'max distance' and 'raise start angle' values for network
        cmds.setAttr(f"{equator_follicles[0]}.minDistance", min_max_distance[i][0])
        cmds.setAttr(f"{equator_follicles[0]}.maxDistance", min_max_distance[i][1])
        cmds.setAttr(f"{equator_follicles[0]}.raiseStartAngle", raise_start_angle[i])

    return raise_influence_nodes
