import os
import json
import inspect
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General

STATE = {"rows": []}


def DefaultSetting(path, *args):
    module_name = "Scene_Pattern_RigAutoFnc"
    return dict(ext="json", path=os.path.join(path, module_name + ".json"),
                moduleName=module_name, order=0, title="Rig Auto Fnc",
                name="Rig Auto Fnc", id=datetime.now().strftime("%Y%m%d%H%M%S"))


def dataPath(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def getData(data):
    path = dataPath(data)
    if not os.path.isfile(path):
        return {"version": 2, "group": "RigUtil", "items": []}
    with open(path, encoding="utf-8") as stream:
        config = json.load(stream)
    return config if isinstance(config, dict) else {"version": 2, "group": "RigUtil", "items": []}


def writeData(data, config):
    with open(dataPath(data), "w", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, separators=(",", ":"))
    return config


def shortName(node):
    return node.rsplit("|", 1)[-1]


def jointName(control):
    name = shortName(control)
    return name[:-3] if name.endswith("_FK") else name


def referenceName(sphere, control, index=1):
    suffix = "" if index == 1 else "_Sub{:02d}".format(index)
    names = [sphere + "_" + name + suffix + "_ref_follicle" for name in (jointName(control), shortName(control))]
    return next((name for name in names if cmds.objExists(name)), names[0])


def pick(field, *args):
    selection = cmds.ls(sl=True, objectsOnly=True) or []
    if selection:
        cmds.textField(field, e=True, text=selection[0])


def textField(parent, label, value="", picker=True):
    row = cmds.rowLayout(parent=parent, numberOfColumns=3, adjustableColumn=2, columnWidth3=(85, 190, 45))
    cmds.text(parent=row, label=label, align="left")
    field = cmds.textField(parent=row, text=value)
    if picker:
        cmds.button(parent=row, label="Pick", command=partial(pick, field))
    else:
        cmds.text(parent=row, label="")
    return field


def removeDriven(row, driven, *args):
    row["drivens"].remove(driven)
    cmds.deleteUI(driven["frame"])


def addDriven(row, spec=None, *args):
    spec = spec or {}
    frame = cmds.frameLayout(parent=row["holder"], label="Driven", collapsable=True, marginWidth=4)
    col = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=3)
    driven = {"frame": frame}
    control = spec.get("control", "")
    driven["control"] = textField(col, "Control", control)
    driven["target"] = textField(col, "Target", spec.get("target", shortName(control) + "_Target" if control else ""))
    line = cmds.rowLayout(parent=col, numberOfColumns=2, adjustableColumn=2, columnWidth2=(85, 150))
    cmds.text(parent=line, label="Output", align="left")
    driven["output"] = cmds.optionMenu(parent=line)
    for channel in ("rotateX", "rotateY", "rotateZ"):
        cmds.menuItem(parent=driven["output"], label=channel)
    cmds.optionMenu(driven["output"], e=True, value=spec.get("output", "rotateZ"))
    for key, label, default in (("refV", "Ref V", -1.0), ("minDistance", "Min Distance", 0.0),
                                ("maxDistance", "Max Distance", 0.0), ("startAngle", "Start Angle", 10.0)):
        line = cmds.rowLayout(parent=col, numberOfColumns=2, adjustableColumn=2, columnWidth2=(85, 150))
        cmds.text(parent=line, label=label, align="left")
        value = spec.get(key, default)
        driven[key] = cmds.floatField(parent=line, value=default if value is None else float(value), precision=6)
    cmds.button(parent=col, label="Remove Driven", command=partial(removeDriven, row, driven))
    row["drivens"].append(driven)


def addSelected(row, *args):
    for control in cmds.ls(sl=True, objectsOnly=True) or []:
        addDriven(row, {"control": control})


def removeReader(row, *args):
    STATE["rows"].remove(row)
    cmds.deleteUI(row["frame"])


def addReader(spec=None, *args):
    spec = spec or {}
    frame = cmds.frameLayout(parent=STATE["holder"], label="Pose Reader", collapsable=True, marginWidth=5)
    col = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=4)
    row = {"frame": frame, "drivens": []}
    row["id"] = textField(col, "Reader ID", spec.get("id", "Reader{}".format(len(STATE["rows"]) + 1)), False)
    row["attributeName"] = textField(col, "Attribute Name", spec.get("attributeName", "autoShoulderGuard"), False)
    for key, label in (("sphere", "Sphere"), ("parent", "Parent"), ("end", "End")):
        row[key] = textField(col, label, spec.get(key, ""))
    actions = cmds.rowLayout(parent=col, numberOfColumns=3)
    cmds.button(parent=actions, label="Add Driven", command=lambda *unused: addDriven(row))
    cmds.button(parent=actions, label="Add Selected", command=partial(addSelected, row))
    cmds.button(parent=actions, label="Remove Reader", command=partial(removeReader, row))
    row["holder"] = cmds.columnLayout(parent=col, adjustableColumn=True, rowSpacing=3)
    STATE["rows"].append(row)
    for driven in spec.get("drivens", []):
        addDriven(row, driven)


def convertConfig(config):
    result = {"version": 2, "group": "RigUtil", "items": []}
    if config.get("group", "RigUtil") != "RigUtil":
        cmds.warning("Rig Auto Fnc: original Diana code uses fixed RigUtil.")
    discarded = 0
    simplified = 0
    for item in config.get("items", []):
        reader = {key: item.get(key, "") for key in ("id", "sphere", "parent", "end")}
        reader["attributeName"] = item.get("attributeName", "autoShoulderGuard")
        reader["drivens"] = []
        if "drivens" in item:
            reader["drivens"] = item["drivens"]
        else:
            for index, control in enumerate(item.get("joints", [])):
                entries = item.get("subItems", [])
                subs = entries[index] if index < len(entries) else []
                sub = subs[0] if subs else {}
                discarded += max(0, len(subs) - 1)
                if (sub.get("axis", "Z") != "Z" or sub.get("outputType", "rotate") != "rotate"
                        or sub.get("reverseU") or sub.get("invertRotate") or sub.get("strength", 1) != 1):
                    simplified += 1
                v = sub.get("refV")
                if v is None and index < len(item.get("refV", [])):
                    v = item["refV"][index]
                reader["drivens"].append(dict(control=control, target=shortName(control) + "_Target",
                    refV=v, minDistance=sub.get("minDistance", 0), maxDistance=sub.get("maxDistance", 0),
                    startAngle=sub.get("startAngle", 10)))
        result["items"].append(reader)
    if discarded:
        cmds.warning("Rig Auto Fnc: {} extra Sub Items ignored; only the first is imported.".format(discarded))
    if simplified:
        cmds.warning("Rig Auto Fnc: {} Driven settings simplified to original Rotate Z.".format(simplified))
    return result


def loadForm(config):
    for child in cmds.layout(STATE["list"], q=True, childArray=True) or []:
        cmds.deleteUI(child)
    config = convertConfig(config)
    STATE["rows"] = []
    cmds.text(parent=STATE["list"], label="Contain: RigUtil", align="left")
    STATE["holder"] = cmds.columnLayout(parent=STATE["list"], adjustableColumn=True, rowSpacing=5)
    for spec in config["items"]:
        addReader(spec)
    if not config["items"]:
        addReader()


def saveSettings(data, *args):
    config = {"version": 2, "group": "RigUtil", "items": []}
    for row in STATE["rows"]:
        reader = {key: cmds.textField(row[key], q=True, text=True).strip() for key in ("id", "sphere", "parent", "end", "attributeName")}
        reader["drivens"] = []
        for driven in row["drivens"]:
            spec = {key: cmds.textField(driven[key], q=True, text=True).strip() for key in ("control", "target")}
            spec["output"] = cmds.optionMenu(driven["output"], q=True, value=True)
            for key in ("refV", "minDistance", "maxDistance", "startAngle"):
                spec[key] = cmds.floatField(driven[key], q=True, value=True)
            if spec["refV"] < 0:
                spec["refV"] = None
            if not spec["target"]:
                spec["target"] = shortName(spec["control"]) + "_Target"
            reader["drivens"].append(spec)
        config["items"].append(reader)
    return writeData(data, config)


def importJson(data, *args):
    paths = cmds.fileDialog2(fileMode=1, fileFilter="JSON (*.json)", caption="Import AutoSkirtFunc JSON")
    if paths:
        with open(paths[0], encoding="utf-8") as stream:
            config = convertConfig(json.load(stream))
        writeData(data, config)
        loadForm(config)


def resolve(reader):
    import maya.api.OpenMaya as om
    sphere = shortName(reader["sphere"])
    shape = cmds.listRelatives(sphere, shapes=True, noIntermediate=True, type="nurbsSurface", fullPath=True)[0]
    selection = om.MSelectionList()
    selection.add(shape)
    surface = om.MFnNurbsSurface(selection.getDagPath(0))
    if any(abs(cmds.getAttr(shape + "." + attr) - expected) > 1e-6 for attr, expected in (
            ("minValueU", 0), ("maxValueU", 1), ("minValueV", 0), ("maxValueV", 1))):
        raise ValueError("Rig Auto Fnc: sphere UV must be 0-1: " + sphere)
    specs = reader["drivens"]
    values = []
    points = []
    counts = {}
    ref_names = []
    for spec in specs:
        control = shortName(spec["control"])
        counts[control] = counts.get(control, 0) + 1
        ref = referenceName(sphere, control, counts[control])
        ref_names.append(ref)
        v = spec.get("refV")
        if v is None or v < 0:
            if cmds.objExists(ref + ".refV"):
                v = cmds.getAttr(ref + ".refV")
            elif cmds.objExists(ref):
                follicle = cmds.listRelatives(ref, shapes=True, type="follicle")[0]
                v = cmds.getAttr(follicle + ".parameterV")
            else:
                pos = cmds.xform(control, q=True, ws=True, rp=True)
                _, _, v = surface.closestPoint(om.MPoint(*pos), space=om.MSpace.kWorld)
        v = float(v)
        if not 0 <= v <= 1:
            raise ValueError("Rig Auto Fnc: Ref V must be 0-1: " + control)
        values.append(v)
        points.append(surface.getPointAtParam(0.5, v, om.MSpace.kWorld))
    bounds = cmds.exactWorldBoundingBox(sphere)
    radius = max(bounds[i+3]-bounds[i] for i in range(3)) * 0.5
    ranges = []
    for index, spec in enumerate(specs):
        minimum, maximum = float(spec["minDistance"]), float(spec["maxDistance"])
        if maximum == 0:
            ref = ref_names[index]
            if cmds.objExists(ref + ".maxDistance"):
                maximum = cmds.getAttr(ref + ".maxDistance")
            else:
                maximum = max(min((points[index].distanceTo(point) for i, point in enumerate(points) if i != index),
                                  default=radius), 0.001)
        if not 0 <= minimum < maximum <= 2:
            raise ValueError("Rig Auto Fnc: original Diana distance attributes require 0 <= Min < Max <= 2: " + spec["control"])
        if not 0 <= float(spec["startAngle"]) <= 180:
            raise ValueError("Rig Auto Fnc: Start Angle must be 0-180")
        ranges.append((minimum, float(maximum)))
    return values, ranges


def buildScript(config):
    config = convertConfig(config)
    if not config["items"]:
        raise ValueError("Rig Auto Fnc: add at least one Pose Reader")
    lines = ["import maya.cmds as cmds", "", "", "def main():"]
    def emit(line=""):
        lines.append("    " + line if line else "")
    seen_spheres = set()
    control_counts = {}
    target_counts = {}
    for reader in config["items"]:
        for spec in reader["drivens"]:
            control = shortName(spec["control"])
            control_counts[control] = control_counts.get(control, 0) + 1
            target = shortName(spec.get("target") or control + "_Target")
            output = spec.get("output", "rotateZ")
            if output not in ("rotateX", "rotateY", "rotateZ"):
                raise ValueError("Rig Auto Fnc: invalid output: " + output)
            plug = target + "." + output
            target_counts[plug] = target_counts.get(plug, 0) + 1
            if target_counts[plug] > 2:
                raise ValueError("Rig Auto Fnc: Akali supports at most two Items per output channel: " + plug)
    paired = {plug: [] for plug, count in target_counts.items() if count == 2}
    pair_numbers = {plug: i for i, plug in enumerate(paired, 1)}
    created_attrs = set()
    for reader in config["items"]:
        if not reader["drivens"]:
            raise ValueError("Rig Auto Fnc: add Driven controls to " + reader["id"])
        attribute_name = reader["attributeName"].strip()
        if not attribute_name.isascii() or not attribute_name.isidentifier():
            raise ValueError("Rig Auto Fnc: invalid Attribute Name: " + attribute_name)
        ref_parameterV, min_max_distance = resolve(reader)
        pose_reader = shortName(reader["sphere"])
        controls = [shortName(d["control"]) for d in reader["drivens"]]
        shoulder_joints = []
        counts = {}
        for control in controls:
            counts[control] = counts.get(control, 0) + 1
            suffix = "" if counts[control] == 1 else "_Sub{:02d}".format(counts[control])
            shoulder_joints.append(jointName(control) + suffix)
        targets = [shortName(d.get("target") or shortName(d["control"]) + "_Target") for d in reader["drivens"]]
        if pose_reader in seen_spheres:
            raise ValueError("Rig Auto Fnc: one item per original pose reader: " + pose_reader)
        seen_spheres.add(pose_reader)
        outputs = [d.get("output", "rotateZ") for d in reader["drivens"]]
        attributes = ["AutoFollow" if control_counts[control] > 1 else attribute_name for control in controls]
        plugs = [target + "." + output for target, output in zip(targets, outputs)]
        direct_indices = tuple(i for i, plug in enumerate(plugs) if plug not in paired)
        if len(set(shoulder_joints)) != len(shoulder_joints):
            raise ValueError("Rig Auto Fnc: duplicate shoulder joint name")
        emit()
        emit("ref_parameterV = " + repr(ref_parameterV) + "  # v values on the sphere, horizontal values")
        emit()
        emit("min_max_distance = " + repr(min_max_distance))
        emit()
        emit("raise_start_angle = " + repr([float(d["startAngle"]) for d in reader["drivens"]]))
        emit()
        emit("shoulder_joints = " + repr(shoulder_joints))
        conventional_controls = controls == [name + "_FK" for name in shoulder_joints]
        conventional_targets = targets == [name + "_Target" for name in controls] and all(output == "rotateZ" for output in outputs)
        create_indices = []
        for i, (control, attribute) in enumerate(zip(controls, attributes)):
            key = (control, attribute)
            if key not in created_attrs:
                create_indices.append(i)
                created_attrs.add(key)
        simple_attributes = len(set(attributes)) == 1 and len(create_indices) == len(controls)
        if not conventional_controls:
            emit("shoulderguard_controls = " + repr(controls))
        if not conventional_targets:
            emit("shoulderguard_targets = " + repr([target + "." + output for target, output in zip(targets, outputs)]))
        if direct_indices and len(direct_indices) != len(controls):
            emit("direct_output_indices = " + repr(direct_indices))
        if not simple_attributes:
            emit("attribute_names = " + repr(attributes))
            emit("create_attribute_indices = " + repr(tuple(create_indices)))
        emit("cp_follicle_shape, cpos = createPoseReaderSystem({!r}, {!r}, {!r})".format(pose_reader, shortName(reader["parent"]), shortName(reader["end"])))
        emit()
        emit("raise_influence_nodes = createSkirtRigSystem(")
        emit("    {!r},".format(pose_reader))
        for argument in ("cp_follicle_shape", "cpos", "shoulder_joints", "ref_parameterV", "min_max_distance"):
            emit("    " + argument + ",")
        emit("    raise_start_angle)")
        emit()
        emit("# Connect master control")
        emit("for i, shoulder_joint in enumerate(shoulder_joints):")
        emit('    shoulderguard_control = f"{shoulder_joint}_FK"' if conventional_controls else "    shoulderguard_control = shoulderguard_controls[i]")
        if simple_attributes:
            emit('    cmds.addAttr(shoulderguard_control, ln="autoShoulderGuard", at="double", min=0, max=2, dv=1, k=True)'.replace("autoShoulderGuard", attributes[0]))
            emit('    cmds.connectAttr(f"{shoulderguard_control}.autoShoulderGuard", f"{raise_influence_nodes[i]}.input2X")'.replace("autoShoulderGuard", attributes[0]))
        else:
            emit("    if i in create_attribute_indices:")
            emit('        cmds.addAttr(shoulderguard_control, ln=attribute_names[i], at="double", min=0, max=2, dv=1, k=True)')
            emit('    cmds.connectAttr(f"{shoulderguard_control}.{attribute_names[i]}", f"{raise_influence_nodes[i]}.input2X")')
        if direct_indices:
            emit()
            emit("    # Connect lift influence")
            connection = 'cmds.connectAttr(f"{raise_influence_nodes[i]}.outputX", f"{shoulderguard_control}_Target.rotateZ")' if conventional_targets else 'cmds.connectAttr(f"{raise_influence_nodes[i]}.outputX", shoulderguard_targets[i])'
            if len(direct_indices) == len(controls):
                emit("    " + connection)
            else:
                emit("    if i in direct_output_indices:")
                emit("        " + connection)
        for i, plug in enumerate(plugs):
            if plug in paired:
                variable = "pair_{:02d}_{}".format(pair_numbers[plug], "left" if not paired[plug] else "right")
                emit("{} = raise_influence_nodes[{}] + '.outputX'".format(variable, i))
                paired[plug].append(variable)
    for plug, (left, right) in paired.items():
        target_base = plug.replace(".", "_")
        emit()
        emit("# Akali: use the greater influence for the shared channel.")
        emit("front_cond = cmds.createNode('condition', n={!r})".format(target_base + "_Condition"))
        emit("cmds.setAttr(f'{front_cond}.operation', 3)")
        emit("cmds.connectAttr({}, f'{{front_cond}}.firstTerm')".format(left))
        emit("cmds.connectAttr({}, f'{{front_cond}}.colorIfTrueR')".format(left))
        emit("cmds.connectAttr({}, f'{{front_cond}}.secondTerm')".format(right))
        emit("cmds.connectAttr({}, f'{{front_cond}}.colorIfFalseR')".format(right))
        emit("front_mult = cmds.createNode('multiplyDivide', n={!r})".format(target_base + "_RaiseValue_Mult"))
        emit("cmds.connectAttr(f'{front_cond}.outColorR', f'{front_mult}.input1X')")
        emit("cmds.setAttr(f'{front_mult}.input2X', 2)")
        emit("raw_src_attr = f'{front_mult}.outputX'")
        emit("val = cmds.getAttr(raw_src_attr) or 0.0")
        emit("if abs(val) >= 0.0001:")
        emit("    pma = cmds.createNode('plusMinusAverage', n={!r})".format(target_base + "_ZeroOut_PMA"))
        emit("    cmds.setAttr(f'{pma}.operation', 2)")
        emit("    cmds.connectAttr(raw_src_attr, f'{pma}.input1D[0]')")
        emit("    cmds.setAttr(f'{pma}.input1D[1]', val)")
        emit("    raw_src_attr = f'{pma}.output1D'")
        emit("cmds.connectAttr(raw_src_attr, {!r})".format(plug))
    lines.extend(["", "", inspect.getsource(createPoseReaderSystem).rstrip(), "", "",
                  inspect.getsource(createSkirtRigSystem).rstrip(), "", "",
                  'if __name__ == "__main__":', "    main()", ""])
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
    buttons = ui["buttonUI"]
    STATE["list"] = ui["listUI"]
    row = cmds.rowColumnLayout(parent=buttons, numberOfColumns=5)
    cmds.button(parent=row, label="Add Reader", command=lambda *unused: addReader())
    cmds.button(parent=row, label="Import JSON", command=partial(importJson, data))
    cmds.button(parent=row, label="Save", command=partial(saveSettings, data))
    cmds.button(parent=row, label="Run", command=partial(runFromForm, data))
    cmds.button(parent=row, label="Export Py", command=partial(ExportPython, data))
    cmds.text(parent=buttons, label="Ref V = -1 / Max Distance = 0: Auto. Two Items on one channel: Akali Max x 2.", align="left")
    loadForm(getData(data))


def createPoseReaderSystem(
    poseReader,
    poseReader_constraint_target,
    closest_point_ref_object,
):

    # Create a locator that follows the reference object.
    # We use the locator's world position to find the closest point on the pose-reader sphere.
    target_loc_group = cmds.createNode("transform", n=f"{poseReader}_Target_Loc_Group")
    target_loc = cmds.spaceLocator(n=f"{poseReader}_Target_Loc")[0]
    target_loc_shape = cmds.listRelatives(target_loc, shapes=True, fullPath=False)[0]

    cmds.parent(target_loc, target_loc_group)
    cmds.parent(target_loc_group, "RigUtil")
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

    cmds.parent(cp_follicleTransform, "RigUtil")

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
            cmds.parent(follicleTransform, "RigUtil")

            cmds.connectAttr(f"{pose_reader_shape}.worldSpace[0]", f"{follicleShape}.inputSurface")
            cmds.connectAttr(f"{pose_reader_shape}.worldMatrix[0]", f"{follicleShape}.inputWorldMatrix")
            cmds.connectAttr(f"{follicleShape}.outTranslate", f"{follicleTransform}.translate")
            cmds.connectAttr(f"{follicleShape}.outRotate", f"{follicleTransform}.rotate")

            cmds.setAttr(f"{follicleShape}.parameterU", 0.5)

            if follicle_type == "ref":
                cmds.setAttr(f"{follicleShape}.parameterV", ref_parameterV[i])
                cmds.addAttr(follicleTransform, ln="minDistance", at="double", min=0, max=2, dv=0, k=True)
                cmds.addAttr(follicleTransform, ln="maxDistance", at="double", min=0, max=2, dv=1.5, k=True)
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
