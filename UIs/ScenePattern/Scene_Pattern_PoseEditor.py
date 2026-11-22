"""Scene Pattern Pose Editor -- joint-free pose-space solver with SDK-style offsets.

Drop beside Scene_Pattern_SDK.py and register Scene_Pattern_PoseEditor in
UIs/Scene.py. Designed for Maya 2024 and the NLTA Scene Pattern framework.
"""

import inspect
import math
import os
import pprint
import re
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General

_UI = {"drivers": [], "list": None}
_CHANNELS = ("tx", "ty", "tz", "rx", "ry", "rz")
_AXES = ("rx", "ry", "rz")


def DefaultSetting(path, *args):
    """Create a ScenePatternData.json record using the existing Scene contract."""
    name = os.path.splitext(os.path.basename(__file__))[0]
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return {
        "ext": "json", "path": os.path.join(path, name + "_" + stamp + ".json"),
        "moduleName": name, "order": 0,
        "title": "Pose Editor", "name": "Pose Editor", "id": stamp,
    }


def _data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    if not entry or not entry.get("path"):
        raise ValueError("Pose Editor: Cannot find this item in ScenePatternData.json")
    return os.path.normpath(entry["path"])


def _read_data(data):
    path = _data_path(data)
    return NLTA_General.readJsonFile(path) or [] if os.path.isfile(path) else []


def _parse_channels(text):
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "." not in line:
            raise ValueError("Pose Editor: Expected object.attr, got " + line)
        obj, attr = line.rsplit(".", 1)
        if attr not in _CHANNELS:
            raise ValueError("Pose Editor: Only translate/rotate supported: " + line)
        if line not in result:
            result.append(line)
    return result


def _selected_transforms():
    selected = cmds.ls(selection=True, long=True) or []
    return [node for node in selected
            if cmds.objExists(node) and cmds.nodeType(node) in ("joint", "transform")]


def _add_row(parent, record=None):
    record = record or {}
    frame = cmds.frameLayout(label="Driver", collapsable=True,
                             collapse=False, parent=parent)
    layout = cmds.columnLayout(adjustableColumn=True, parent=frame)
    name_layout = cmds.rowLayout(numberOfColumns=2, parent=layout)
    driver = cmds.textField(text=record.get("driverJoint", ""), width=295,
                            annotation="Control, joint or transform: read-only driver")
    cmds.button(label="Pick Driver", width=100,
                command=lambda *_: _pick_driver(driver))
    cmds.setParent("..")
    cmds.text(label="Driver attrs (1-3 names, e.g. rx,ry,rz or myAttr)",
              align="left", parent=layout)
    driver_attrs = cmds.textField(text=record.get("driverChannels", "rx,ry,rz"),
                                  parent=layout)
    cmds.text(label="Driven channels (one object.attr per line)",
              align="left", parent=layout)
    attrs = cmds.scrollField(text=record.get("drivenAttrs", ""),
                             wordWrap=False, height=95, parent=layout)
    buttons = cmds.rowLayout(numberOfColumns=2, parent=layout)
    cmds.button(label="Add Selected Driven", width=195,
                command=lambda *_: _add_driven_channels(attrs))
    cmds.button(label="Clear Driven", width=195,
                command=lambda *_: cmds.scrollField(attrs, edit=True, text=""))
    cmds.setParent("..")
    poses_parent = cmds.columnLayout(adjustableColumn=True, parent=layout)
    item = {"frame": frame, "driver": driver, "driver_attrs": driver_attrs, "attrs": attrs,
            "poses_parent": poses_parent, "poses": [],
            "id": record.get("id") or datetime.now().strftime("%Y%m%d%H%M%S%f")}
    _UI["drivers"].append(item)
    for pose in record.get("poses", []):
        _add_pose_row(item, pose)
    buttons = cmds.rowLayout(numberOfColumns=2, parent=layout)
    cmds.button(label="Add Current Pose", width=195,
                command=lambda *_: _add_current_pose(item))
    cmds.button(label="Delete Driver", width=195,
                command=lambda *_: _delete_driver(item))
    cmds.setParent("..")
    cmds.setParent("..")
    return item


def _pick_driver(field):
    picked = _selected_transforms()
    if not picked:
        raise ValueError("Pose Editor: Select a driver joint or transform")
    cmds.textField(field, edit=True, text=picked[0])


def _add_driven_channels(field):
    channels = _parse_channels(cmds.scrollField(field, query=True, text=True))
    for node in _selected_transforms():
        for attr in _CHANNELS:
            plug = node + "." + attr
            if plug not in channels and cmds.objExists(plug):
                channels.append(plug)
    cmds.scrollField(field, edit=True, text="\n".join(channels))


def _add_pose_row(item, pose):
    frame = cmds.frameLayout(label=pose.get("name", "Pose"), collapsable=True,
                             collapse=False, parent=item["poses_parent"])
    layout = cmds.columnLayout(adjustableColumn=True, parent=frame)
    name = cmds.textField(text=pose.get("name", ""), parent=layout)
    cmds.text(label="Driver channel values (up to 3)", align="left", parent=layout)
    rotation = pose.get("driverRotate", (0, 0, 0))
    angles = cmds.floatFieldGrp(numberOfFields=3, value1=float(rotation[0]),
                                 value2=float(rotation[1]), value3=float(rotation[2]),
                                 parent=layout)
    cmds.text(label="Saved Driven values (object.attr = value)", align="left", parent=layout)
    values = cmds.scrollField(text=_format_values(pose.get("drivenValues", {})),
                              wordWrap=False, height=95, parent=layout)
    row = {"frame": frame, "name": name, "angles": angles, "values": values}
    item["poses"].append(row)
    buttons = cmds.rowLayout(numberOfColumns=2, parent=layout)
    cmds.button(label="Update from Scene", width=195,
                command=lambda *_: _capture(item, row))
    cmds.button(label="Remove Pose", width=195,
                command=lambda *_: _remove_pose(item, row))
    cmds.setParent("..")
    cmds.setParent("..")
    return row


def _remove_pose(item, row):
    item["poses"].remove(row)
    cmds.deleteUI(row["frame"])


def _delete_driver(item):
    _UI["drivers"].remove(item)
    cmds.deleteUI(item["frame"])


def _format_values(values):
    return "\n".join("{}.{} = {:g}".format(obj, attr, float(value))
                     for obj, attrs in values.items() for attr, value in attrs.items())


def _parse_values(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError("Pose Editor: Expected object.attr = value: " + line)
        plug, raw = [part.strip() for part in line.split("=", 1)]
        if "." not in plug:
            raise ValueError("Pose Editor: Invalid channel: " + plug)
        obj, attr = plug.rsplit(".", 1)
        if attr not in _CHANNELS:
            raise ValueError("Pose Editor: Unsupported channel: " + plug)
        values.setdefault(obj, {})[attr] = float(raw)
    return values


def _capture(item, row):
    driver = cmds.textField(item["driver"], query=True, text=True).strip()
    if not cmds.objExists(driver):
        raise ValueError("Pose Editor: Pick a valid Driver first")
    channels = _parse_channels(cmds.scrollField(item["attrs"], query=True, text=True))
    if not channels:
        raise ValueError("Pose Editor: Add at least one Driven channel first")
    values = {}
    for plug in channels:
        if not cmds.objExists(plug):
            raise ValueError("Pose Editor: Missing channel: " + plug)
        obj, attr = plug.rsplit(".", 1)
        values.setdefault(obj, {})[attr] = float(cmds.getAttr(plug))
    channels = _driver_channels({"driverChannels": cmds.textField(
        item["driver_attrs"], query=True, text=True)})
    for index, flag in enumerate(("value1", "value2", "value3")):
        value = float(cmds.getAttr(driver + "." + channels[index])) if index < len(channels) else 0.0
        cmds.floatFieldGrp(row["angles"], edit=True, **{flag: value})
    cmds.scrollField(row["values"], edit=True, text=_format_values(values))
    name = cmds.textField(row["name"], query=True, text=True).strip()
    cmds.frameLayout(row["frame"], edit=True, label=name or "Pose")


def _add_current_pose(item):
    label = "Neutral" if not item["poses"] else "Pose_{}".format(len(item["poses"]))
    row = _add_pose_row(item, {"name": label, "driverRotate": (0, 0, 0),
                               "drivenValues": {}})
    try:
        _capture(item, row)
    except Exception:
        _remove_pose(item, row)
        raise


def _records_from_ui():
    records = []
    for item in _UI["drivers"]:
        driver = cmds.textField(item["driver"], query=True, text=True).strip()
        if not driver and not item["poses"]:
            continue
        poses = []
        for row in item["poses"]:
            angle = [float(cmds.floatFieldGrp(row["angles"], query=True, **{f: True}))
                     for f in ("value1", "value2", "value3")]
            poses.append({"name": cmds.textField(row["name"], query=True, text=True).strip(),
                          "driverRotate": angle,
                          "drivenValues": _parse_values(cmds.scrollField(
                              row["values"], query=True, text=True))})
        records.append({"id": item["id"], "driverJoint": driver,
                        "driverChannels": cmds.textField(item["driver_attrs"], query=True, text=True),
                        "drivenAttrs": cmds.scrollField(item["attrs"], query=True, text=True),
                        "poses": poses})
    return records


def Save(data, *args):
    records = _records_from_ui()
    NLTA_General.writeJsonFile(_data_path(data), records)
    return records


def Load(data, listUI, *args):
    for child in cmds.layout(listUI, query=True, childArray=True) or []:
        cmds.deleteUI(child)
    _UI["drivers"] = []
    _UI["list"] = listUI
    records = _read_data(data)
    if not isinstance(records, list):
        raise ValueError("Pose Editor: JSON must contain a list")
    if records:
        for record in records:
            _add_row(listUI, record)
    else:
        _add_row(listUI)


def Form(data, *args):
    form = NLTA_General.LoadModule("Scene_Form")
    controls = form.Create(data)
    list_ui = controls["listUI"]
    bar = controls["buttonUI"]
    cmds.text(label="1. Add Neutral  2. Move Driver / Driven  3. Add Pose  4. Save / Run",
              align="left", parent=bar)
    row = cmds.rowLayout(numberOfColumns=4, parent=bar)
    cmds.button(label="Add Driver", width=98, parent=row,
                command=lambda *_: _add_row(list_ui))
    cmds.button(label="Save", width=98, parent=row,
                command=lambda *_: Save(data))
    cmds.button(label="Run", width=98, parent=row,
                command=lambda *_: _save_run(data))
    export_button = cmds.button(label="Export Py", width=98, parent=row,
                                command=lambda *_: _save_export(data))
    menu = cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", parent=menu,
                  command=lambda *_: OpenExportFolder(data))
    cmds.setParent("..")
    Load(data, list_ui)


def _save_run(data):
    # Save a draft safely. Missing poses are an editing step, not a Maya rig failure.
    records = Save(data)
    try:
        _validate_pose_records(records)
    except ValueError as error:
        message = str(error)
        cmds.warning(message)
        cmds.confirmDialog(title="Pose Editor - More Poses Required",
                           message=message, button=["OK"],
                           defaultButton="OK")
        return []
    return BuildPoseEditor(records)


def _save_export(data):
    Save(data)
    return ExportPython(data)


def OpenExportFolder(data, *args):
    folder = os.path.dirname(_data_path(data))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    os.startfile(folder)


def _validate_pose_records(records):
    """Check saved pose data BEFORE opening Maya's Undo chunk.

    Drafts with only a Neutral are valid for Save, but cannot build a rig.
    No Maya node is created here; all errors preserve the current scene.
    """
    if not isinstance(records, list):
        raise ValueError("Pose Editor: Saved data must be a list of driver records")
    for number, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise ValueError("Pose Editor: Driver record {} is invalid".format(number))
        driver = str(record.get("driverJoint") or "").strip()
        if not driver:
            raise ValueError("Pose Editor: Driver #{} has no selected joint".format(number))
        poses = record.get("poses")
        if not isinstance(poses, list):
            raise ValueError("Pose Editor: Driver #{} has an invalid poses list".format(number))
        if len(poses) < 2:
            short = driver.rsplit("|", 1)[-1]
            captured = ", ".join(str(p.get("name") or "Unnamed")
                                 for p in poses if isinstance(p, dict)) or "none"
            raise ValueError(
                "Pose Editor: {} has {} saved pose(s): {}. "
                "A working rig needs Neutral AND at least one different pose. "
                "Keep the saved Neutral, rotate the Driver to a new angle, "
                "adjust the Driven controls, click 'Add Current Pose', then Save. "
                "Return Driver and Driven to Neutral before Run.".format(
                    short, len(poses), captured))
        _driver_channels(record)
        names = []
        channels = set()
        orientations = set()
        for i, pose in enumerate(poses):
            if not isinstance(pose, dict):
                raise ValueError("Pose Editor: {} has an invalid pose at {}".format(driver, i))
            name = pose.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Pose Editor: {} has an unnamed pose".format(driver))
            if name in names:
                raise ValueError("Pose Editor: Duplicate pose '{}' for {}".format(name, driver))
            names.append(name)
            if i > 0 and name.lower() in ("neutral", "neutralswing", "neutraltwist"):
                raise ValueError("Pose Editor: '{}' is reserved for Maya neutral".format(name))
            angles = pose.get("driverRotate")
            if not isinstance(angles, (tuple, list)) or len(angles) != 3:
                raise ValueError("Pose Editor: '{}' needs 3 driver angles".format(name))
            try:
                orientation = tuple(round(float(v), 5) for v in angles)
            except (TypeError, ValueError):
                raise ValueError("Pose Editor: '{}' has invalid driver angles".format(name))
            if orientation in orientations:
                raise ValueError("Pose Editor: {} and another pose have the same Driver "
                                 "rotation. Move the Driver before capturing a new pose.".format(name))
            orientations.add(orientation)
            values = pose.get("drivenValues")
            if not isinstance(values, dict):
                raise ValueError("Pose Editor: '{}' has invalid Driven values".format(name))
            current = {(obj, attr) for obj, attrs in values.items()
                       for attr in attrs}
            if not current:
                raise ValueError("Pose Editor: '{}' has no captured Driven channels".format(name))
            # Pose samples may drive different channels. Uncaptured channels
            # will hold their Neutral value instead of blocking the rig.
            channels.update(current)
    return records


def _complete_pose_data(poses, scene_neutral):
    """Expand sparse pose channels to a consistent set without changing JSON.

    When a channel was added after Neutral was captured, its rest value is
    read from the scene at build time, while the driver is back at Neutral.
    All other missing samples hold that channel's Neutral value.
    """
    channels = sorted({(obj, attr) for pose in poses
                       for obj, attrs in pose["drivenValues"].items()
                       for attr in attrs})
    first = poses[0]["drivenValues"]
    baseline = {}
    for obj, attr in channels:
        if attr in first.get(obj, {}):
            value = float(first[obj][attr])
        else:
            value = float(scene_neutral[(obj, attr)])
        baseline.setdefault(obj, {})[attr] = value
    completed = []
    for pose in poses:
        values = {}
        for obj, attr in channels:
            value = pose["drivenValues"].get(obj, {}).get(attr,
                                                         baseline[obj][attr])
            values.setdefault(obj, {})[attr] = float(value)
        completed.append({"name": pose["name"],
                          "driverRotate": list(pose["driverRotate"]),
                          "drivenValues": values})
    return completed


def _driver_channels(record):
    """Read up to three control attributes; old JSON defaults to RX/RY/RZ."""
    raw = record.get("driverChannels") or "rx,ry,rz"
    if isinstance(raw, (list, tuple)):
        channels = [str(name).strip() for name in raw]
    else:
        channels = [name.strip() for name in str(raw).replace("\n", ",").split(",")]
    channels = [name for name in channels if name]
    if not 1 <= len(channels) <= 3 or len(set(channels)) != len(channels):
        raise ValueError("Pose Editor: Provide 1-3 unique Driver attributes")
    if any("." in name or "|" in name for name in channels):
        raise ValueError("Pose Editor: Enter Driver attribute names only, e.g. rx,ry,rz")
    return channels


def _driver_scale(plug, adapter):
    """Calibrate the read-only DG connection against a Maya UI attribute value."""
    original = float(cmds.getAttr(plug))
    numeric = float(cmds.getAttr(adapter + ".output"))
    if abs(original) > 1e-7:
        factor = numeric / original
        if not math.isfinite(factor) or abs(factor) < 1e-12:
            raise ValueError("Pose Editor: Unsupported Driver conversion: " + plug)
        return factor
    # Maya inserts unitConversion to preserve 1 source UI unit = 1 target UI
    # unit (including angle-to-distance connections). At a zero-valued Driver
    # we cannot divide current output/current value, so the correct fallback
    # for the current scene units is 1, NOT radians-per-degree.
    return 1.0


def _rbf_weights(samples, current):
    """Product-of-squared-distances interpolation; exact at distinct samples."""
    squared = [sum((a - b) ** 2 for a, b in zip(sample, current))
               for sample in samples]
    numerators = [math.prod(squared[j] for j in range(len(squared)) if j != i)
                  for i in range(len(squared))]
    total = sum(numerators)
    if total <= 0 or not math.isfinite(total):
        raise ValueError("Pose Editor: Driver samples are duplicated or too large")
    return [value / total for value in numerators]


def _make_weights(stem, adapters, samples):
    """Pure DG, no poseInterpolator or joints: polynomial normalized weights."""
    distances = []
    for pose_index, sample in enumerate(samples):
        distance = cmds.createNode("plusMinusAverage", name=stem + "_P%d_D2" % pose_index)
        for axis_index, (source, center) in enumerate(zip(adapters, sample)):
            diff = cmds.createNode("addDoubleLinear",
                                   name=stem + "_P%d_A%d_Diff" % (pose_index, axis_index))
            cmds.connectAttr(source, diff + ".input1")
            cmds.setAttr(diff + ".input2", -float(center))
            square = cmds.createNode("multDoubleLinear",
                                     name=stem + "_P%d_A%d_Square" % (pose_index, axis_index))
            cmds.connectAttr(diff + ".output", square + ".input1")
            cmds.connectAttr(diff + ".output", square + ".input2")
            cmds.connectAttr(square + ".output", distance + ".input1D[%d]" % axis_index)
        distances.append(distance + ".output1D")
    numerators = []
    for pose_index in range(len(samples)):
        factors = [value for index, value in enumerate(distances) if index != pose_index]
        current = factors[0]
        for step, factor in enumerate(factors[1:], 1):
            product = cmds.createNode("multDoubleLinear",
                                      name=stem + "_P%d_Product%d" % (pose_index, step))
            cmds.connectAttr(current, product + ".input1")
            cmds.connectAttr(factor, product + ".input2")
            current = product + ".output"
        numerators.append(current)
    denominator = cmds.createNode("plusMinusAverage", name=stem + "_WeightTotal")
    for index, node in enumerate(numerators):
        cmds.connectAttr(node, denominator + ".input1D[%d]" % index)
    weights = []
    for index, numerator in enumerate(numerators):
        divide = cmds.createNode("multiplyDivide", name=stem + "_P%d_Weight" % index)
        cmds.setAttr(divide + ".operation", 2)
        cmds.connectAttr(numerator, divide + ".input1X")
        cmds.connectAttr(denominator + ".output1D", divide + ".input2X")
        weights.append(divide + ".outputX")
    return weights


def _build_one(record):
    """Read a control/attribute Driver; drive SDK-style helper groups only."""
    driver = record["driverJoint"]
    poses = record["poses"]
    channels = _driver_channels(record)
    if not cmds.objExists(driver):
        raise ValueError("Pose Editor: Driver not found: " + driver)
    stems = "NLTA_Pose_" + re.sub("[^A-Za-z0-9_]", "_", str(record["id"]))
    if cmds.objExists(stems + "_WeightTotal"):
        raise ValueError("Pose Editor: Rig already exists. Use a new scene: " + stems)
    if not 2 <= len(poses) <= 12:
        raise ValueError("Pose Editor: Capture 2-12 distinct poses")
    driver_plugs = [driver + "." + name for name in channels]
    allowed = {"double", "float", "doubleAngle", "floatAngle", "doubleLinear",
               "floatLinear", "long", "short", "byte", "enum"}
    for plug in driver_plugs:
        if not cmds.objExists(plug) or cmds.getAttr(plug, type=True) not in allowed:
            raise ValueError("Pose Editor: Driver attribute must be numeric: " + plug)
    all_plugs = {(obj, attr) for pose in poses
                 for obj, attrs in pose["drivenValues"].items()
                 for attr in attrs}
    if not all_plugs:
        raise ValueError("Pose Editor: No Driven channels captured")
    original = poses[0]["drivenValues"]
    baseline = {(obj, attr) for obj, attrs in original.items() for attr in attrs}
    missing_rest = all_plugs - baseline
    if missing_rest and any(abs(float(cmds.getAttr(plug)) - float(value)) > 0.001
                            for plug, value in zip(driver_plugs,
                                                   poses[0]["driverRotate"])):
        raise ValueError("Pose Editor: Return Driver to Neutral before adding new Driven")
    rest = {}
    obj_paths = {}
    groups = {}
    drv_path = (cmds.ls(driver, long=True) or [driver])[0]
    for obj, attr in sorted(all_plugs):
        plug = obj + "." + attr
        if attr not in ("tx", "ty", "tz", "rx", "ry", "rz") or not cmds.objExists(plug):
            raise ValueError("Pose Editor: Driven channel missing: " + plug)
        if (obj, attr) in baseline and abs(float(cmds.getAttr(plug)) -
                                           float(original[obj][attr])) > 0.001:
            raise ValueError("Pose Editor: Return Driven to Neutral before Run: " + plug)
        if (obj, attr) in missing_rest:
            rest[(obj, attr)] = float(cmds.getAttr(plug))
        obj_path = (cmds.ls(obj, long=True) or [obj])[0]
        if cmds.nodeType(obj) not in ("joint", "transform"):
            raise ValueError("Pose Editor: Driven must be a transform: " + obj)
        if obj_path == drv_path or drv_path.startswith(obj_path + "|"):
            raise ValueError("Pose Editor: Driven cannot be Driver or its parent: " + obj)
        obj_paths[obj] = obj_path
        short = re.sub("[^A-Za-z0-9_]", "_", obj_path.rsplit("|", 1)[-1])
        groups[obj] = stems + "_" + short
    if len(set(groups.values())) != len(groups):
        raise ValueError("Pose Editor: Multiple Driven controls have the same short name")
    for prefix in groups.values():
        for suffix in ("_PoseGrp", "_NeutralGrp", "_ContainGrp"):
            if cmds.objExists(prefix + suffix):
                raise ValueError("Pose Editor: Helper group exists: " + prefix + suffix)
    poses = _complete_pose_data(poses, rest)
    neutral = poses[0]["drivenValues"]
    adapters = []
    factors = []
    for index, plug in enumerate(driver_plugs):
        reader = cmds.createNode("addDoubleLinear", name=stems + "_Driver%d_Read" % index)
        cmds.connectAttr(plug, reader + ".input1")
        adapters.append(reader + ".output")
        factors.append(_driver_scale(plug, reader))
    samples = [[float(value) * factor for value, factor in
                zip(pose["driverRotate"][:len(channels)], factors)]
               for pose in poses]
    for i in range(len(samples)):
        for j in range(i):
            if sum((a - b) ** 2 for a, b in zip(samples[i], samples[j])) < 1e-10:
                raise ValueError("Pose Editor: Duplicate Driver positions in saved poses")
    weights = _make_weights(stems, adapters, samples)

    for obj in sorted(groups, key=lambda item: obj_paths[item].count("|"), reverse=True):
        prefix = groups[obj]
        parent = cmds.listRelatives(obj, parent=True, fullPath=True) or []
        helpers = []
        for suffix in ("_PoseGrp", "_NeutralGrp", "_ContainGrp"):
            helper = cmds.group(empty=True, name=prefix + suffix)
            if parent:
                helper = cmds.parent(helper, parent[0], relative=True)[0]
            helpers.append(helper)
        pose_group, neutral_group, contain_group = helpers
        moved = cmds.parent(obj, contain_group, relative=True)[0]
        moved = (cmds.ls(moved, long=True) or [moved])[0]
        if not cmds.attributeQuery("Pose_Enable", node=moved, exists=True):
            cmds.addAttr(moved, longName="Pose_Enable", attributeType="double",
                         min=0, max=1, defaultValue=1, keyable=True)
        enable = moved + ".Pose_Enable"
        if cmds.getAttr(enable, lock=True):
            raise ValueError("Pose Editor: Pose_Enable is locked: " + enable)
        inverse = cmds.createNode("reverse", name=prefix + "_EnableReverse")
        cmds.connectAttr(enable, inverse + ".inputX")
        pc = cmds.parentConstraint(neutral_group, pose_group, contain_group,
                                   maintainOffset=False, name=prefix + "_ParentConstraint")[0]
        pc_aliases = cmds.parentConstraint(pc, query=True, weightAliasList=True)
        cmds.connectAttr(inverse + ".outputX", pc + "." + pc_aliases[0])
        cmds.connectAttr(enable, pc + "." + pc_aliases[1])
        sc = cmds.scaleConstraint(neutral_group, pose_group, contain_group,
                                  maintainOffset=False, name=prefix + "_ScaleConstraint")[0]
        sc_aliases = cmds.scaleConstraint(sc, query=True, weightAliasList=True)
        cmds.connectAttr(inverse + ".outputX", sc + "." + sc_aliases[0])
        cmds.connectAttr(enable, sc + "." + sc_aliases[1])
        for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
            if (obj, attr) not in all_plugs:
                continue
            deltas = [float(pose["drivenValues"][obj][attr]) -
                      float(neutral[obj][attr]) for pose in poses]
            if all(abs(delta) < 1e-10 for delta in deltas):
                continue
            summation = cmds.createNode("plusMinusAverage", name=prefix + "_" + attr + "_Sum")
            multipliers = []
            for index, delta in enumerate(deltas[1:], 1):
                if abs(delta) < 1e-10:
                    continue
                mult = cmds.createNode("multDoubleLinear",
                                       name=prefix + "_" + attr + "_P%d_Mult" % index)
                cmds.connectAttr(weights[index], mult + ".input1")
                cmds.connectAttr(mult + ".output", summation + ".input1D[%d]" % index)
                multipliers.append((mult, delta))
            cmds.connectAttr(summation + ".output1D", pose_group + "." + attr)
            cmds.setAttr(summation + ".input1D[0]", 1.0)
            conversion = float(cmds.getAttr(pose_group + "." + attr))
            cmds.setAttr(summation + ".input1D[0]", 0.0)
            if abs(conversion) < 1e-9:
                raise RuntimeError("Pose Editor: Cannot calibrate offset: " + pose_group + "." + attr)
            for mult, delta in multipliers:
                cmds.setAttr(mult + ".input2", delta / conversion)

    current = [float(cmds.getAttr(plug)) * factor
               for plug, factor in zip(driver_plugs, factors)]
    expected = _rbf_weights(samples, current)
    for weight, wanted in zip(weights, expected):
        actual = float(cmds.getAttr(weight))
        if abs(actual - wanted) > 0.04:
            raise RuntimeError("Pose Editor: DG interpolation check failed: " + weight)
    return stems


def BuildPoseEditor(records):
    """Build saved poses with safe rollback, preserving the original error.

    Never call Undo on an unrelated Maya command if the build failed before
    writing anything into the undo chunk. ExportPython uses this same builder.
    """
    if not isinstance(records, list):
        raise ValueError("Pose Editor: Saved data should be a list")
    if not records:
        return []
    # Reject incomplete/invalid pose drafts before opening any Undo chunk.
    _validate_pose_records(records)
    # Building a rig while Maya Undo is disabled cannot be rolled back safely.
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError(
            "Pose Editor: Maya Undo is OFF. Enable Edit > Undo before Run "
            "(or run cmds.undoInfo(state=True) in Script Editor)."
        )

    chunk_name = "NLTA Pose Editor Build"
    cmds.undoInfo(openChunk=True, chunkName=chunk_name)
    try:
        result = [_build_one(record) for record in records]
    except Exception:
        # The original build exception is more important than Undo errors.
        # Close first, then undo ONLY if our own named chunk is on top.
        try:
            cmds.undoInfo(closeChunk=True)
        except Exception as close_error:
            print("Pose Editor: Could not close Undo chunk: {}".format(close_error))
        else:
            try:
                available = (
                    cmds.undoInfo(query=True, state=True)
                    and not cmds.undoInfo(query=True, undoQueueEmpty=True)
                )
                top = cmds.undoInfo(query=True, undoName=True) if available else ""
                if available and top == chunk_name:
                    cmds.undo()
                else:
                    print(
                        "Pose Editor: No matching Undo chunk; skipping rollback "
                        "to protect previous scene edits. Check the scene for "
                        "a partially created Pose Editor rig."
                    )
            except Exception as rollback_error:
                print("Pose Editor: Undo rollback unavailable: {}".format(
                    rollback_error))
        raise
    else:
        cmds.undoInfo(closeChunk=True)
        return result


def Run(data, *args):
    # The Scene list Run button is allowed while data is still being captured.
    # Show a useful warning instead of opening an Undo chunk and raising.
    records = _read_data(data)
    try:
        _validate_pose_records(records)
    except ValueError as error:
        cmds.warning(str(error))
        return []
    return BuildPoseEditor(records)


def ExportPython(data, *args):
    """Export the SAME rig builder to a standalone Maya Python file."""
    records = _read_data(data)
    if not records:
        cmds.warning("Pose Editor: Nothing saved to export")
        return None
    try:
        _validate_pose_records(records)
    except ValueError as error:
        cmds.warning("Pose Editor export: " + str(error))
        return None
    # Use one JSON-like Python literal record per line; no compressed data.
    formatted = "[\n" + ",\n".join("        " + pprint.pformat(
        record, width=200, compact=True) for record in records) + "\n    ]"
    functions = (_validate_pose_records, _complete_pose_data, _driver_channels,
                 _driver_scale, _rbf_weights, _make_weights, _build_one,
                 BuildPoseEditor)
    code = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    source = ("def main():\n"
              "    import re\n"
              "    import math\n"
              "    import maya.cmds as cmds\n\n"
              "    # Pose Editor data\n"
              "    POSE_DATA = " + formatted + "\n\n" + code +
              "\n\n    # Build joint-free pose-space driven offsets.\n"
              "    BuildPoseEditor(POSE_DATA)\n\n\n"
              'if __name__ == "__main__":\n    main()\n')
    filename = "Python_Scene_Pattern_PoseEditor.py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(_data_path(data)), filename)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(source)
    return output