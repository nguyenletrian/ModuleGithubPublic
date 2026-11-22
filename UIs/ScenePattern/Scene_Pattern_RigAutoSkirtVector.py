# -*- coding: utf-8 -*-
"""AutoSkirt with bilinear X/Y Pose 2D and legacy Start-End Vector modes.

Pose 2D reads a control's local rotateX/rotateY, captures neutral on build,
and blends Neutral, X Max, Y Max and XY Max rotation values on DrivenOffset.
Legacy Vector items retain their original panel math. Neither mode uses a sphere.
Run and standalone ExportPython embed the same Maya builder functions.
"""

import os
import json
import inspect
import ast
from datetime import datetime

_UI_ROWS = {}


def _adapt_item(item):
    """Normalize old axes dictionaries and new dynamic panel lists.

    Every panel owns a persistent P001/P002/... ID. These IDs are used
    as stable node names, even when the UI order changes.
    """
    data = dict(item or {})
    for old, new in (("pelvis", "parent"), ("hip", "start"),
                     ("knee", "end"), ("joint", "driven"),
                     ("name", "prefix")):
        if new not in data and old in data:
            data[new] = data[old]
        data.pop(old, None)

    defaults = {
        "startAxis": "+X", "outputAxis": "None",
        "startAngle": 10.0, "fullAngle": 60.0,
        "maxRotate": 45.0, "falloff": "smooth",
    }
    raw = data.get("panels")
    if not isinstance(raw, list):
        old_axes = data.get("axes")
        if isinstance(old_axes, dict):
            raw = []
            for index, axis in enumerate("XYZ", 1):
                old = dict(old_axes.get(axis) or {})
                old.setdefault("startAxis", "+" + axis)
                old.setdefault(
                    "outputAxis", axis if old.get("active", False) else "None")
                raw.append(dict(old, id="P%03d" % index))
        else:
            # An EMPTY new Item must not create an active Z rotation.
            # Only migrate the old one-axis reader when its legacy
            # rotation/angle keys are actually present.
            is_legacy = any(key in data for key in (
                "rotateAxis", "startAngle", "fullAngle", "maxRotate",
                "influenceAngle", "rotateSign", "falloff",
            ))
            if is_legacy:
                old_axis = str(data.get("rotateAxis", "Z")).upper()
                raw = [dict(data, id="P001", startAxis="+Z",
                            outputAxis=old_axis if old_axis in "XYZ" else "None")]
            else:
                raw = [dict(id="P001", startAxis="-X", outputAxis="None")]
    if not raw:
        raw = [dict(id="P001", startAxis="-X", outputAxis="None")]

    normalized = []
    used = set()
    for i, previous in enumerate(raw, 1):
        record = dict(previous or {})
        identifier = str(record.get("id") or "P%03d" % i)
        if not identifier.isalnum() or not identifier[0].isalpha():
            raise ValueError("AutoSkirtVector: panel ID must be alphanumeric")
        if identifier in used:
            raise ValueError("AutoSkirtVector: duplicate panel ID: " + identifier)
        used.add(identifier)
        row = dict(defaults)
        row["startAxis"] = "+" + "XYZ"[(i-1) % 3]
        for key in defaults:
            if key in record:
                row[key] = record[key]
        row["startAxis"] = str(row["startAxis"]).upper()
        if row["startAxis"] in ("NONE", ""):
            row["startAxis"] = "None"
        row["outputAxis"] = str(row["outputAxis"]).upper()
        # Old JSON used Output Axis X/Y/Z plus a separate rotateSign.
        # Fold the sign into the output choice; never reverse a
        # value that already explicitly starts with '-'.
        old_sign = int(record.get("rotateSign", 1))
        if old_sign not in (-1, 1):
            raise ValueError("AutoSkirtVector: invalid legacy Rotate Sign")
        if (old_sign == -1 and
                row["outputAxis"] in ("X", "Y", "Z")):
            row["outputAxis"] = "-" + row["outputAxis"]
        if row["outputAxis"] == "NONE":
            row["outputAxis"] = "None"
        if row["outputAxis"] not in (
                "None", "X", "-X", "Y", "-Y", "Z", "-Z"):
            raise ValueError("AutoSkirtVector: invalid Output Axis: " +
                             row["outputAxis"])
        normalized.append(dict(row, id=identifier))

    if "zoneWidth" not in data:
        data["zoneWidth"] = float(
            item.get("influenceAngle", 75.0)) if item else 75.0
    for key in ("rotateAxis", "startAngle", "fullAngle", "influence",
                "maxRotate", "rotateSign", "falloff", "axes",
                "active", "influenceAngle"):
        data.pop(key, None)
    data["panels"] = normalized
    mode = data.get("mode")
    if not mode:
        old_config = isinstance(item, dict) and any(
            key in item for key in ("panels", "axes", "rotateAxis", "hip"))
        mode = "vector" if old_config else "pose2d"
    if mode not in ("vector", "pose2d"):
        raise ValueError("AutoSkirtVector: mode must be vector or pose2d")
    data["mode"] = mode
    data["poseDriver"] = str(data.get("poseDriver") or data.get("start") or "")
    for name in ("xMaxAngle", "yMaxAngle"):
        value = float(data.get(name, 90.0))
        if abs(value) < 0.001 or abs(value) > 180:
            raise ValueError("AutoSkirtVector: " + name + " must be between -180 and 180, excluding zero")
        data[name] = value
    source_poses = data.get("poses") or {}
    poses = {}
    for key in ("neutral", "x90", "y90", "xy90"):
        values = source_poses.get(key, [0.0, 0.0, 0.0])
        if not isinstance(values, (tuple, list)) or len(values) != 3:
            raise ValueError("AutoSkirtVector: pose " + key + " must have X/Y/Z rotation")
        poses[key] = [float(value) for value in values]
    data["poses"] = poses
    return data


def CreateAutoSkirtVector(parent, start, end, driven, contain=None, prefix=None, zoneWidth=75.0, panels=None, neutralMode='capture'):
    import math, re
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    parent = cmds.ls(parent, long=True)[0]
    start = cmds.ls(start, long=True)[0]
    end = cmds.ls(end, long=True)[0]
    driven = cmds.ls(driven, long=True)[0]
    short = driven.rsplit('|', 1)[-1].replace(':', '_')
    prefix = prefix or 'ASV_' + re.sub(r'[^A-Za-z0-9_]', '_', short)
    panels = panels or []

    def normalize(vector):
        length = math.sqrt(sum(float(x) ** 2 for x in vector))
        return [float(x) / length for x in vector]

    def matrix(plug):
        raw = cmds.getAttr(plug)
        return om.MMatrix(raw[0] if isinstance(raw[0], (tuple, list)) else raw)

    def point(node, parent_inverse):
        local = matrix(node + '.worldMatrix[0]') * parent_inverse
        return [local[12], local[13], local[14]]

    def create(kind, name):
        return cmds.createNode(kind, name=prefix + '_' + name)

    def connect(source, target):
        cmds.connectAttr(source, target)

    def vector_attr(label, values):
        cmds.addAttr(root, longName=label, attributeType='double3')
        for axis in 'XYZ':
            cmds.addAttr(root, longName=label + axis, attributeType='double', parent=label)
        cmds.setAttr(root + '.' + label, *values, type='double3')

    def double_attr(label, value, keyable=True):
        cmds.addAttr(root, longName=label, attributeType='double', defaultValue=value, keyable=keyable)

    def ramp(node, first, last, interpolation):
        for index, value in enumerate((first, last)):
            cmds.setAttr(node + '.value[%d].value_Position' % index, index)
            cmds.setAttr(node + '.value[%d].value_FloatValue' % index, value)
            cmds.setAttr(node + '.value[%d].value_Interp' % index, interpolation)

    # Match Offset 1 to Driven before parenting it into the original hierarchy
    original_parent = (cmds.listRelatives(driven, parent=True, fullPath=True) or [None])[0]
    world_matrix = cmds.xform(driven, query=True, worldSpace=True, matrix=True)
    space = cmds.createNode('transform', name=prefix + '_SpaceOffset')
    cmds.xform(space, worldSpace=True, matrix=world_matrix)
    if original_parent:
        space = cmds.parent(space, original_parent, absolute=True)[0]
    root = space
    values = cmds.getAttr(space + '.translate')[0] + cmds.getAttr(space + '.rotate')[0]
    values += tuple(value - 1 for value in cmds.getAttr(space + '.scale')[0])
    if any(abs(value) > 1e-5 for value in values):
        # Match Offset 2 to Driven, then parent it under Offset 1
        root = cmds.createNode('transform', name=prefix + '_DrivenOffset')
        cmds.xform(root, worldSpace=True, matrix=world_matrix)
        root = cmds.parent(root, space, absolute=True)[0]
        cmds.setAttr(root + '.translate', 0, 0, 0, type='double3')
        cmds.setAttr(root + '.rotate', 0, 0, 0, type='double3')
        cmds.setAttr(root + '.scale', 1, 1, 1, type='double3')
    driven = cmds.parent(driven, root, absolute=True)[0]
    # Capture neutral only after completing the Driven hierarchy
    parent_inverse = matrix(parent + '.worldInverseMatrix[0]')
    start_world = matrix(start + '.worldMatrix[0]')
    neutral = normalize([b - a for a, b in zip(point(start, parent_inverse), point(end, parent_inverse))])
    axes = {}
    for axis, basis in (('X', (1, 0, 0)), ('Y', (0, 1, 0)), ('Z', (0, 0, 1))):
        direction = om.MVector(*basis) * start_world * parent_inverse
        axes[axis] = normalize((direction.x, direction.y, direction.z))
    driven = cmds.ls(driven, long=True)[0]
    cmds.addAttr(driven, longName='AutoFollow', niceName='Auto Follow', attributeType='double', minValue=0, maxValue=1, defaultValue=1, keyable=True)
    cmds.addAttr(root, longName='asvDriven', dataType='string')
    cmds.setAttr(root + '.asvDriven', driven, type='string')
    double_attr('zoneWidth', float(zoneWidth))
    double_attr('liftAngle', 0, False)
    for label, vec in [('neutralVector', neutral)] + [('axis' + axis, axes[axis]) for axis in 'XYZ']:
        vector_attr(label, vec)

    # Read Start-End in Parent space
    samples = {}
    for tag, node in (('Start', start), ('End', end)):
        mm = create('multMatrix', tag + 'Matrix')
        dm = create('decomposeMatrix', tag + 'Local')
        connect(node + '.worldMatrix[0]', mm + '.matrixIn[0]')
        connect(parent + '.worldInverseMatrix[0]', mm + '.matrixIn[1]')
        connect(mm + '.matrixSum', dm + '.inputMatrix')
        samples[tag] = dm
    live = create('plusMinusAverage', 'LiveVector')
    cmds.setAttr(live + '.operation', 2)
    connect(samples['End'] + '.outputTranslate', live + '.input3D[0]')
    connect(samples['Start'] + '.outputTranslate', live + '.input3D[1]')
    # Store the exact neutral vector evaluated by Maya
    rest = cmds.getAttr(live + '.output3D')[0]
    neutral = normalize(rest)
    vector_attr('neutralRawVector', rest)
    cmds.setAttr(root + '.neutralVector', *neutral, type='double3')
    lift = create('angleBetween', 'LiftAngle')
    connect(root + '.neutralRawVector', lift + '.vector1')
    connect(live + '.output3D', lift + '.vector2')
    connect(lift + '.angle', root + '.liftAngle')
    # Subtract the rest vector first so neutral swing is exactly zero
    delta = create('plusMinusAverage', 'DeltaVector')
    cmds.setAttr(delta + '.operation', 2)
    connect(live + '.output3D', delta + '.input3D[0]')
    connect(root + '.neutralRawVector', delta + '.input3D[1]')
    # Project the delta onto the neutral plane
    dot = create('vectorProduct', 'NeutralDot')
    cmds.setAttr(dot + '.operation', 1)
    connect(root + '.neutralVector', dot + '.input1')
    connect(delta + '.output3D', dot + '.input2')
    scale = create('multiplyDivide', 'NeutralScale')
    connect(root + '.neutralVector', scale + '.input1')
    for axis in 'XYZ':
        connect(dot + '.outputX', scale + '.input2' + axis)
    swing = create('plusMinusAverage', 'SwingVector')
    cmds.setAttr(swing + '.operation', 2)
    connect(delta + '.output3D', swing + '.input3D[0]')
    connect(scale + '.output', swing + '.input3D[1]')
    # Create the output sums without driving the offset yet
    for axis in 'XYZ':
        create('plusMinusAverage', 'OutputSum' + axis)

    # Build independent pose panels
    source_options = ('NONE', '+X', '-X', '+Y', '-Y', '+Z', '-Z')
    for slot, panel in enumerate(panels):
        pid = str(panel['id'])
        field, tag = 'panel' + pid, 'Panel' + pid
        selected = panel['startAxis'].upper()
        output = panel['outputAxis'].upper()
        direction = [0.0, 0.0, 0.0]
        if selected != 'NONE':
            basis = axes[selected[-1]]
            along = sum(a * b for a, b in zip(basis, neutral))
            tangent = [basis[i] - along * neutral[i] for i in range(3)]
            magnitude = math.sqrt(sum(v * v for v in tangent))
            sign = -1 if selected[0] == '-' else 1
            if magnitude:
                direction = [sign * v / magnitude for v in tangent]
        vector_attr(field + 'Direction', direction)
        cmds.addAttr(root, longName=field + 'StartAxis', attributeType='enum', enumName='None:PosX:NegX:PosY:NegY:PosZ:NegZ', defaultValue=source_options.index(selected), keyable=True)
        cmds.addAttr(root, longName=field + 'OutputAxis', attributeType='enum', enumName='None:X:Y:Z', defaultValue=('NONE', 'X', 'Y', 'Z').index(output.lstrip('-')), keyable=True)
        for name, value in (('StartAngle', panel['startAngle']), ('FullAngle', panel['fullAngle']), ('MaxRotate', panel['maxRotate'])):
            double_attr(field + name, float(value))
        double_attr(field + 'RotateSign', -1 if output.startswith('-') else 1, False)
        for name in ('ZoneAngle', 'ZoneWeight', 'LiftWeight', 'RotateDelta'):
            double_attr(field + name, 0, False)
        zone_angle = create('angleBetween', tag + 'ZoneAngle')
        connect(root + '.' + field + 'Direction', zone_angle + '.vector1')
        connect(swing + '.output3D', zone_angle + '.vector2')
        zone_remap = create('remapValue', tag + 'ZoneRemap')
        connect(zone_angle + '.angle', zone_remap + '.inputValue')
        connect(root + '.zoneWidth', zone_remap + '.inputMax')
        lift_remap = create('remapValue', tag + 'LiftRemap')
        connect(lift + '.angle', lift_remap + '.inputValue')
        connect(root + '.' + field + 'StartAngle', lift_remap + '.inputMin')
        connect(root + '.' + field + 'FullAngle', lift_remap + '.inputMax')
        connect(zone_angle + '.angle', root + '.' + field + 'ZoneAngle')
        connect(zone_remap + '.outValue', root + '.' + field + 'ZoneWeight')
        connect(lift_remap + '.outValue', root + '.' + field + 'LiftWeight')
        mix = create('multiplyDivide', tag + 'ZoneMix')
        connect(lift_remap + '.outValue', mix + '.input1X')
        connect(zone_remap + '.outValue', mix + '.input2X')
        gain = create('multiplyDivide', tag + 'Gain')
        connect(mix + '.outputX', gain + '.input1X')
        connect(driven + '.AutoFollow', gain + '.input2X')
        maximum = create('multiplyDivide', tag + 'MaxRotate')
        connect(gain + '.outputX', maximum + '.input1X')
        connect(root + '.' + field + 'MaxRotate', maximum + '.input2X')
        flip = create('multiplyDivide', tag + 'RotateSign')
        connect(maximum + '.outputX', flip + '.input1X')
        connect(root + '.' + field + 'RotateSign', flip + '.input2X')
        connect(flip + '.outputX', root + '.' + field + 'RotateDelta')
        # Route each panel to its selected output axis
        for index, axis in enumerate('XYZ', 1):
            gate = create('condition', tag + 'To' + axis)
            connect(root + '.' + field + 'OutputAxis', gate + '.firstTerm')
            cmds.setAttr(gate + '.secondTerm', index)
            connect(flip + '.outputX', gate + '.colorIfTrueR')
            connect(gate + '.outColorR', prefix + '_OutputSum' + axis + '.input1D[%d]' % slot)
        interpolation = 1 if panel['falloff'] == 'linear' else 2
        ramp(lift_remap, 0, 1, interpolation)
        ramp(zone_remap, 1, 0, interpolation)

    # Cancel each neutral output before connecting to the DrivenOffset
    for axis in 'XYZ':
        result = prefix + '_OutputSum' + axis
        cmds.setAttr(result + '.input1D[%d]' % len(panels), -cmds.getAttr(result + '.output1D'))
        connect(result + '.output1D', root + '.rotate' + axis)
    return {'root': root, 'offset': root, 'spaceOffset': space, 'drivenOffset': root, 'driven': driven, 'autoFollow': driven + '.AutoFollow', 'panels': [p['id'] for p in panels]}


def CreateAutoSkirtPose2D(driven, poseDriver, contain=None, prefix=None,
                          xMaxAngle=90.0,
                          yMaxAngle=90.0, poses=None):
    import re
    import maya.cmds as cmds
    import maya.api.OpenMaya as om

    driven_matches = cmds.ls(driven, long=True) or []
    driver_matches = cmds.ls(poseDriver, long=True) or []
    if not driven_matches or not driver_matches:
        raise ValueError('AutoSkirtVector: Driven and Pose Driver must exist')
    driven = driven_matches[0]
    pose_driver = driver_matches[0]
    if not all(cmds.objExists(pose_driver + '.rotate' + axis) for axis in 'XY'):
        raise ValueError('AutoSkirtVector: Pose Driver needs rotateX and rotateY')
    if abs(float(xMaxAngle)) < 0.001 or abs(float(yMaxAngle)) < 0.001:
        raise ValueError('AutoSkirtVector: X/Y maximum angles cannot be zero')
    short = driven.rsplit('|', 1)[-1].replace(':', '_')
    prefix = prefix or 'ASV_' + re.sub(r'[^A-Za-z0-9_]', '_', short)
    poses = poses or {}
    for key in ('neutral', 'x90', 'y90', 'xy90'):
        values = poses.get(key, [0, 0, 0])
        if len(values) != 3:
            raise ValueError('AutoSkirtVector: pose ' + key + ' requires X/Y/Z')
        poses[key] = [float(value) for value in values]
    pose_selection = om.MSelectionList()
    pose_selection.add(pose_driver)
    pose_handle = om.MObjectHandle(pose_selection.getDependNode(0))

    # Match the existing Driven hierarchy while preserving world transforms
    original_parent = (cmds.listRelatives(driven, parent=True, fullPath=True) or [None])[0]
    world_matrix = cmds.xform(driven, query=True, worldSpace=True, matrix=True)
    space = cmds.createNode('transform', name=prefix + '_SpaceOffset')
    cmds.xform(space, worldSpace=True, matrix=world_matrix)
    if original_parent:
        space = cmds.parent(space, original_parent, absolute=True)[0]
    root = space
    values = cmds.getAttr(space + '.translate')[0] + cmds.getAttr(space + '.rotate')[0]
    values += tuple(value - 1 for value in cmds.getAttr(space + '.scale')[0])
    if any(abs(value) > 1e-5 for value in values):
        root = cmds.createNode('transform', name=prefix + '_DrivenOffset')
        cmds.xform(root, worldSpace=True, matrix=world_matrix)
        root = cmds.parent(root, space, absolute=True)[0]
        cmds.setAttr(root + '.translate', 0, 0, 0, type='double3')
        cmds.setAttr(root + '.rotate', 0, 0, 0, type='double3')
        cmds.setAttr(root + '.scale', 1, 1, 1, type='double3')
    driven = cmds.parent(driven, root, absolute=True)[0]
    driven = cmds.ls(driven, long=True)[0]
    pose_object = pose_handle.object()
    pose_driver = om.MFnDagNode(pose_object).fullPathName()

    # Read both local rotation channels; their values remain independent at 90/90
    rest_x = cmds.getAttr(pose_driver + '.rotateX')
    rest_y = cmds.getAttr(pose_driver + '.rotateY')
    if not cmds.attributeQuery('AutoFollow', node=driven, exists=True):
        cmds.addAttr(driven, longName='AutoFollow', niceName='Auto Follow',
                     attributeType='double', minValue=0, maxValue=1,
                     defaultValue=1, keyable=True)
    cmds.addAttr(root, longName='asvDriven', dataType='string')
    cmds.setAttr(root + '.asvDriven', driven, type='string')
    cmds.addAttr(root, longName='asvPoseMode', attributeType='bool', defaultValue=True)
    for name, value in (('restX', rest_x), ('restY', rest_y),
                        ('xMaxAngle', xMaxAngle), ('yMaxAngle', yMaxAngle)):
        cmds.addAttr(root, longName=name, attributeType='double',
                     defaultValue=float(value), keyable=(name.endswith('MaxAngle')))

    pose_names = (('neutral', 'poseNeutral'), ('x90', 'poseX90'),
                  ('y90', 'poseY90'), ('xy90', 'poseXY90'))
    for key, label in pose_names:
        cmds.addAttr(root, longName=label, attributeType='double3')
        for axis in 'XYZ':
            cmds.addAttr(root, longName=label + axis, attributeType='double',
                         parent=label, keyable=True)
        cmds.setAttr(root + '.' + label, *[float(v) for v in
                     poses.get(key, [0, 0, 0])], type='double3')

    def create(kind, label):
        return cmds.createNode(kind, name=prefix + '_' + label)

    def connect(src, dst):
        cmds.connectAttr(src, dst)

    # Normalize the signed X/Y driver angles to [0,1] for bilinear blending
    normalized = {}
    for axis in 'XY':
        delta = create('plusMinusAverage', 'PoseDelta' + axis)
        cmds.setAttr(delta + '.operation', 2)
        connect(pose_driver + '.rotate' + axis, delta + '.input1D[0]')
        connect(root + '.rest' + axis, delta + '.input1D[1]')
        divide = create('multiplyDivide', 'PoseNormalize' + axis)
        cmds.setAttr(divide + '.operation', 2)
        connect(delta + '.output1D', divide + '.input1X')
        connect(root + '.' + axis.lower() + 'MaxAngle', divide + '.input2X')
        limit = create('clamp', 'PoseClamp' + axis)
        cmds.setAttr(limit + '.minR', 0)
        cmds.setAttr(limit + '.maxR', 1)
        connect(divide + '.outputX', limit + '.inputR')
        normalized[axis] = limit + '.outputR'

    # Interpolate between four independent pose rotations, including the corner
    row_zero = create('blendColors', 'PoseY0Blend')
    row_max = create('blendColors', 'PoseY90Blend')
    combined = create('blendColors', 'PoseXYBlend')
    connect(normalized['X'], row_zero + '.blender')
    connect(normalized['X'], row_max + '.blender')
    connect(normalized['Y'], combined + '.blender')
    for axis, channel in zip('XYZ', 'RGB'):
        connect(root + '.poseNeutral' + axis, row_zero + '.color2' + channel)
        connect(root + '.poseX90' + axis, row_zero + '.color1' + channel)
        connect(root + '.poseY90' + axis, row_max + '.color2' + channel)
        connect(root + '.poseXY90' + axis, row_max + '.color1' + channel)
    connect(row_zero + '.output', combined + '.color2')
    connect(row_max + '.output', combined + '.color1')

    strength = create('multiplyDivide', 'PoseAutoFollow')
    connect(combined + '.output', strength + '.input1')
    for axis in 'XYZ':
        connect(driven + '.AutoFollow', strength + '.input2' + axis)
        connect(strength + '.output' + axis, root + '.rotate' + axis)
    return {'root': root, 'offset': root, 'spaceOffset': space, 'drivenOffset': root,
            'driven': driven, 'poseDriver': pose_driver, 'mode': 'pose2d',
            'autoFollow': driven + '.AutoFollow'}


def _rig_arguments(item):
    item = _adapt_item(item)
    return dict(parent=item["parent"], start=item["start"], end=item["end"], driven=item["driven"],
                contain=item.get("contain"), prefix=item.get("prefix"), zoneWidth=item.get("zoneWidth", 75),
                panels=item["panels"], neutralMode=item.get("neutralMode", "capture"))


def _pose_arguments(item):
    item = _adapt_item(item)
    return dict(driven=item["driven"], poseDriver=item["poseDriver"],
                contain=item.get("contain"), prefix=item.get("prefix"),
                xMaxAngle=item["xMaxAngle"], yMaxAngle=item["yMaxAngle"],
                poses=item["poses"])


def BuildAutoSkirtVectorItem(item):
    item = _adapt_item(item)
    if item["mode"] == "pose2d":
        return CreateAutoSkirtPose2D(**_pose_arguments(item))
    return CreateAutoSkirtVector(**_rig_arguments(item))


def DefaultSetting(path, *args):
    module_name = os.path.splitext(os.path.basename(__file__))[0]
    return {
        "ext": "json", "path": os.path.join(path, module_name + ".json"),
        "moduleName": module_name, "order": 0,
        "title": "Auto Skirt Vector", "name": "Auto Skirt Vector",
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
    }


def _pattern_path(data):
    import NLTA_General
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    if not entry or not entry.get("path"):
        raise RuntimeError("AutoSkirtVector: pattern JSON path not found")
    return os.path.normpath(entry["path"])


def _read_settings(data):
    path = _pattern_path(data)
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as stream:
        result = json.load(stream)
    if not isinstance(result, list):
        raise ValueError("AutoSkirtVector: expected a JSON list of items")
    return result


def ApplyLiveSettings(item, panel_id=None):
    """Push UI values onto an EXISTING Maya rig without rebuilding nodes.

    The connected Maya DG already updates the Driven every evaluation:
    editing remap thresholds, directions, zone width or max rotation only
    requires setAttr. Structural Add/Remove Panel still needs a Run.
    """
    import math
    import re
    import maya.cmds as cmds

    item = _adapt_item(item)
    driven_name = str(item.get("driven") or "").strip()
    prefix = str(item.get("prefix") or "").strip()
    if not prefix:
        short = driven_name.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        prefix = re.sub(r"[^a-zA-Z0-9_]", "_", short)
        if prefix and prefix[0].isdigit():
            prefix = "_" + prefix
        prefix = "ASV_" + prefix
    matches = cmds.ls(prefix + "_DrivenOffset", long=True) or cmds.ls(prefix + "_SpaceOffset", long=True) or []
    if not matches:
        return False
    root = matches[0]
    stored_driven = cmds.getAttr(root + ".asvDriven")

    is_pose_rig = cmds.attributeQuery("asvPoseMode", node=root, exists=True)
    if item["mode"] == "pose2d":
        if not is_pose_rig:
            return False
        for name in ("xMaxAngle", "yMaxAngle"):
            value = float(item[name])
            if abs(value) < 0.001 or abs(value) > 180:
                raise ValueError("Pose 2D: invalid " + name)
        for key, label in (("neutral", "poseNeutral"),
                           ("x90", "poseX90"),
                           ("y90", "poseY90"), ("xy90", "poseXY90")):
            values = [float(value) for value in item["poses"][key]]
            cmds.setAttr(root + "." + label, *values, type="double3")
        cmds.setAttr(root + ".xMaxAngle", item["xMaxAngle"])
        cmds.setAttr(root + ".yMaxAngle", item["yMaxAngle"])
        return True
    if is_pose_rig:
        return False

    zone_width = float(item.get("zoneWidth", 75))
    if not 0.001 <= zone_width <= 180:
        raise ValueError("Zone Width must be between 0.001 and 180")
    if panel_id is None:
        cmds.setAttr(root + ".zoneWidth", zone_width)
        return True

    panel = next(
        (p for p in item["panels"] if str(p["id"]) == str(panel_id)),
        None,
    )
    if panel is None:
        return False
    field = "panel" + str(panel_id)
    if not cmds.attributeQuery(field + "OutputAxis", node=root, exists=True):
        return False  # Added panel gets built on the next Run.

    output = str(panel.get("outputAxis", "None")).upper()
    source = str(panel.get("startAxis", "None")).upper()
    if output not in ("NONE", "X", "-X", "Y", "-Y", "Z", "-Z"):
        raise ValueError("Invalid Output Axis")
    if source not in ("NONE", "+X", "-X", "+Y", "-Y", "+Z", "-Z"):
        raise ValueError("Invalid Start Axis")
    if output != "NONE" and source == "NONE":
        raise ValueError("Select a Start Axis for an enabled panel")
    begin = float(panel["startAngle"])
    finish = float(panel["fullAngle"])
    maximum = float(panel["maxRotate"])
    if not (0 <= begin < finish <= 180):
        raise ValueError("Start Angle must be lower than Full Angle")
    if not 0 <= maximum <= 360:
        raise ValueError("Max Rotate must be 0–360")
    falloff = str(panel["falloff"]).lower()
    if falloff not in ("smooth", "linear"):
        raise ValueError("Falloff must be smooth or linear")

    def saved_vec(attribute):
        raw = cmds.getAttr(root + "." + attribute)
        return list(raw[0] if isinstance(raw[0], (tuple, list)) else raw)

    if source == "NONE":
        direction = [0.0, 0.0, 0.0]
    else:
        neutral = saved_vec("neutralVector")
        norm = math.sqrt(sum(x*x for x in neutral))
        neutral = [x/norm for x in neutral]
        basis = saved_vec("axis" + source[-1])
        parallel = sum(a*b for a, b in zip(basis, neutral))
        projected = [basis[i] - parallel*neutral[i] for i in range(3)]
        magnitude = math.sqrt(sum(x*x for x in projected))
        if magnitude < 1e-6:
            if output != "NONE":
                raise ValueError(
                    "Selected Start Axis is parallel to the neutral vector")
            direction = [0.0, 0.0, 0.0]
        else:
            sign = -1.0 if source.startswith("-") else 1.0
            direction = [sign*x/magnitude for x in projected]

    # Validate BOTH remaps before writing any of this panel's live
    # settings; a partially deleted panel should not get a half-update.
    for suffix in ("LiftRemap", "ZoneRemap"):
        ramp = prefix + "_Panel" + str(panel_id) + suffix
        if not cmds.objExists(ramp):
            raise RuntimeError(
                "AutoSkirtVector: missing panel remap node " + ramp)

    source_options = ("NONE", "+X", "-X", "+Y", "-Y", "+Z", "-Z")
    cmds.setAttr(root + ".zoneWidth", zone_width)
    cmds.setAttr(root + "." + field + "Direction",
                 *direction, type="double3")
    cmds.setAttr(root + "." + field + "StartAxis",
                 source_options.index(source))
    cmds.setAttr(root + "." + field + "OutputAxis",
                 ("NONE", "X", "Y", "Z").index(output.lstrip("-")))
    cmds.setAttr(root + "." + field + "RotateSign",
                 -1 if output.startswith("-") else 1)
    cmds.setAttr(root + "." + field + "StartAngle", begin)
    cmds.setAttr(root + "." + field + "FullAngle", finish)
    cmds.setAttr(root + "." + field + "MaxRotate", maximum)
    interp = 1 if falloff == "linear" else 2
    for suffix in ("LiftRemap", "ZoneRemap"):
        ramp = prefix + "_Panel" + str(panel_id) + suffix
        for index in (0, 1):
            cmds.setAttr(
                ramp + ".value[%d].value_Interp" % index, interp)
    return True


def _collect_item(fields):
    """Read a single UI Item so the same values feed Save and live updates."""
    import maya.cmds as cmds

    item = {}
    for name in ("parent", "start", "end", "driven", "contain", "prefix"):
        item[name] = cmds.textField(
            fields[name], query=True, text=True).strip()
    for name in ("contain", "prefix"):
        if not item[name]:
            item.pop(name)
    item["zoneWidth"] = cmds.floatField(
        fields["zoneWidth"], query=True, value=True)
    mode_choice = cmds.optionMenu(fields["mode"], query=True, value=True)
    item["mode"] = "pose2d" if mode_choice == "Pose 2D" else "vector"
    item["poseDriver"] = cmds.textField(
        fields["poseDriver"], query=True, text=True).strip()
    item["xMaxAngle"] = cmds.floatField(
        fields["xMaxAngle"], query=True, value=True)
    item["yMaxAngle"] = cmds.floatField(
        fields["yMaxAngle"], query=True, value=True)
    item["poses"] = {
        key: [cmds.floatField(field, query=True, value=True) for field in controls]
        for key, controls in fields["poses"].items()
    }
    item["panels"] = []
    for controls in fields["panels"]:
        panel = {
            "id": controls["id"],
            "startAxis": cmds.optionMenu(
                controls["startAxis"], query=True, value=True),
            "outputAxis": cmds.optionMenu(
                controls["outputAxis"], query=True, value=True),
            "falloff": cmds.optionMenu(
                controls["falloff"], query=True, value=True),
        }
        for name in ("startAngle", "fullAngle", "maxRotate"):
            panel[name] = cmds.floatField(
                controls[name], query=True, value=True)
        item["panels"].append(panel)
    return item


def Add(listUI, item=None, *args):
    """Compact AutoSkirtVector panel editor."""
    import re
    import maya.cmds as cmds

    item = _adapt_item(item or {})
    frame = cmds.frameLayout(parent=listUI, label="Auto Skirt Vector",
                             collapsable=True, marginWidth=4, marginHeight=4)
    body = cmds.columnLayout(parent=frame, adjustableColumn=True)
    fields = {"panels": [], "nextPanelNumber": 1, "poses": {}}
    label_w, field_w, pick_w = 78, 240, 28

    def sync_prefix(*unused):
        raw = cmds.textField(fields["driven"], query=True, text=True).strip()
        if raw:
            short = raw.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            clean = re.sub(r"[^A-Za-z0-9_]", "_", short)
            if clean and clean[0].isdigit():
                clean = "_" + clean
            if clean:
                cmds.textField(fields["prefix"], edit=True, text=clean)

    def live_update(panel_id=None, *unused):
        try:
            ApplyLiveSettings(_collect_item(fields), panel_id)
        except (ValueError, RuntimeError, TypeError) as exc:
            cmds.warning("AutoSkirtVector Live: " + str(exc))
        except Exception as exc:
            cmds.warning("AutoSkirtVector Live unexpected: " + str(exc))

    def object_row(label):
        layout = cmds.rowLayout(parent=body, numberOfColumns=3,
                                columnWidth3=(label_w, field_w, pick_w),
                                adjustableColumn=2)
        cmds.text(parent=layout, label=label, width=label_w, align="right")
        return layout

    def pick(field, key, *unused):
        selection = cmds.ls(selection=True, long=True) or []
        if len(selection) != 1:
            cmds.warning("Select one object in Maya to pick")
            return
        cmds.textField(field, edit=True, text=selection[0])
        if key == "driven":
            sync_prefix()
        if key == "start" and "poseDriver" in fields:
            current = cmds.textField(fields["poseDriver"], query=True, text=True).strip()
            if not current:
                cmds.textField(fields["poseDriver"], edit=True, text=selection[0])

    object_layouts = {}
    for key, label in (("parent", "Parent"), ("start", "Start"),
                       ("end", "End"), ("driven", "Driven"),
                       ("contain", "Contain")):
        layout = object_row(label)
        object_layouts[key] = layout
        field = cmds.textField(parent=layout, width=field_w,
                               text=str(item.get(key) or ""))
        fields[key] = field
        if key == "driven":
            cmds.textField(field, edit=True, changeCommand=sync_prefix)
        cmds.button(parent=layout, width=pick_w, label="<",
                    command=lambda *unused, f=field, k=key: pick(f, k))

    layout = object_row("Prefix")
    fields["prefix"] = cmds.textField(parent=layout, width=field_w,
                                      text=str(item.get("prefix") or ""))
    cmds.text(parent=layout, label="", width=pick_w)

    layout = object_row("Zone Width")
    zone_layout = layout
    fields["zoneWidth"] = cmds.floatField(
        parent=layout, width=field_w, precision=2,
        value=float(item.get("zoneWidth", 75)),
        changeCommand=lambda *unused: live_update())
    cmds.text(parent=layout, label="", width=pick_w)

    mode_row = object_row("Mode")
    mode_menu = cmds.optionMenu(parent=mode_row, width=field_w)
    for option in ("Pose 2D", "Vector"):
        cmds.menuItem(parent=mode_menu, label=option)
    cmds.optionMenu(mode_menu, edit=True,
                    value="Pose 2D" if item["mode"] == "pose2d" else "Vector")
    fields["mode"] = mode_menu
    cmds.text(parent=mode_row, label="", width=pick_w)

    pose_host = cmds.columnLayout(parent=body, adjustableColumn=True)
    driver_row = cmds.rowLayout(parent=pose_host, numberOfColumns=3,
                                columnWidth3=(label_w, field_w, pick_w),
                                adjustableColumn=2)
    cmds.text(parent=driver_row, label="Pose Driver", width=label_w, align="right")
    fields["poseDriver"] = cmds.textField(
        parent=driver_row, width=field_w,
        text=str(item.get("poseDriver") or item.get("start") or ""))
    cmds.button(parent=driver_row, label="<", width=pick_w,
                command=lambda *unused: pick(fields["poseDriver"], "poseDriver"))

    max_row = cmds.rowLayout(parent=pose_host, numberOfColumns=4,
                             columnWidth4=(80, 95, 80, 95))
    cmds.text(parent=max_row, label="X Max", width=80, align="right")
    fields["xMaxAngle"] = cmds.floatField(
        parent=max_row, width=95, precision=2, value=float(item["xMaxAngle"]),
        changeCommand=lambda *unused: live_update())
    cmds.text(parent=max_row, label="Y Max", width=80, align="right")
    fields["yMaxAngle"] = cmds.floatField(
        parent=max_row, width=95, precision=2, value=float(item["yMaxAngle"]),
        changeCommand=lambda *unused: live_update())

    header = cmds.rowLayout(parent=pose_host, numberOfColumns=4,
                            columnWidth4=(80, 85, 85, 85))
    for text_label in ("Pose", "Rotate X", "Rotate Y", "Rotate Z"):
        cmds.text(parent=header, label=text_label)
    for key, title in (("neutral", "Neutral"), ("x90", "X Max"),
                       ("y90", "Y Max"), ("xy90", "XY Max")):
        pose_row = cmds.rowLayout(parent=pose_host, numberOfColumns=4,
                                  columnWidth4=(80, 85, 85, 85))
        cmds.text(parent=pose_row, label=title, width=80, align="right")
        fields["poses"][key] = [
            cmds.floatField(parent=pose_row, width=85, precision=2,
                            value=float(value),
                            changeCommand=lambda *unused: live_update())
            for value in item["poses"][key]
        ]

    panel_host = cmds.columnLayout(parent=body, adjustableColumn=True)
    ids = [str(panel.get("id", "")) for panel in item.get("panels", [])]
    numbers = [int(pid[1:]) for pid in ids if re.match(r"^P[0-9]+$", pid)]
    fields["nextPanelNumber"] = max(numbers, default=0) + 1

    def remove_panel(entry, *unused):
        if len(fields["panels"]) <= 1:
            cmds.warning("Keep one panel; use Output Axis None to disable it.")
            return
        fields["panels"].remove(entry)
        if cmds.layout(entry["frame"], exists=True):
            cmds.deleteUI(entry["frame"])

    def add_panel(panel_data=None, *unused):
        panel_data = dict(panel_data or {})
        pid = str(panel_data.get("id") or "P%03d" % fields["nextPanelNumber"])
        if not panel_data.get("id"):
            fields["nextPanelNumber"] += 1
        start_axis = str(panel_data.get("startAxis", "+X"))
        output_axis = str(panel_data.get("outputAxis", "None"))
        panel_frame = cmds.frameLayout(
            parent=panel_host, label="PANEL " + pid, collapsable=True,
            collapse=bool(panel_data) and output_axis == "None",
            marginWidth=4, marginHeight=3)
        content = cmds.columnLayout(parent=panel_frame, adjustableColumn=True)
        controls = {"id": pid, "frame": panel_frame}

        def pair_row():
            return cmds.rowLayout(parent=content, numberOfColumns=4,
                                  columnWidth4=(80, 95, 80, 95))

        axes = pair_row()
        cmds.text(parent=axes, label="Start Axis", width=80, align="right")
        start_menu = cmds.optionMenu(parent=axes, width=95)
        for option in ("None", "+X", "-X", "+Y", "-Y", "+Z", "-Z"):
            cmds.menuItem(parent=start_menu, label=option)
        cmds.optionMenu(start_menu, edit=True, value=start_axis,
                        changeCommand=lambda *unused, panel_id=pid:
                        live_update(panel_id))
        controls["startAxis"] = start_menu
        cmds.text(parent=axes, label="Output Axis", width=80, align="right")
        output_menu = cmds.optionMenu(parent=axes, width=95)
        for option in ("None", "X", "-X", "Y", "-Y", "Z", "-Z"):
            cmds.menuItem(parent=output_menu, label=option)
        cmds.optionMenu(output_menu, edit=True, value=output_axis,
                        changeCommand=lambda *unused, panel_id=pid:
                        live_update(panel_id))
        controls["outputAxis"] = output_menu

        angles = pair_row()
        cmds.text(parent=angles, label="Start Angle", width=80, align="right")
        controls["startAngle"] = cmds.floatField(
            parent=angles, width=95, precision=2,
            value=float(panel_data.get("startAngle", 10.0)),
            changeCommand=lambda *unused, panel_id=pid: live_update(panel_id))
        cmds.text(parent=angles, label="Full Angle", width=80, align="right")
        controls["fullAngle"] = cmds.floatField(
            parent=angles, width=95, precision=2,
            value=float(panel_data.get("fullAngle", 60.0)),
            changeCommand=lambda *unused, panel_id=pid: live_update(panel_id))

        settings = pair_row()
        cmds.text(parent=settings, label="Max Rotate", width=80, align="right")
        controls["maxRotate"] = cmds.floatField(
            parent=settings, width=95, precision=2,
            value=float(panel_data.get("maxRotate", 45.0)),
            changeCommand=lambda *unused, panel_id=pid: live_update(panel_id))
        cmds.text(parent=settings, label="Falloff", width=80, align="right")
        falloff_menu = cmds.optionMenu(parent=settings, width=95)
        for option in ("smooth", "linear"):
            cmds.menuItem(parent=falloff_menu, label=option)
        cmds.optionMenu(falloff_menu, edit=True,
                        value=str(panel_data.get("falloff", "smooth")),
                        changeCommand=lambda *unused, panel_id=pid:
                        live_update(panel_id))
        controls["falloff"] = falloff_menu

        cmds.button(parent=content, label="Remove Panel", height=23,
                    command=lambda *unused, entry=controls: remove_panel(entry))
        fields["panels"].append(controls)
        return panel_frame

    for panel in item.get("panels", []):
        add_panel(panel)

    def remove_item(*unused):
        _UI_ROWS.pop(frame, None)
        if cmds.layout(frame, exists=True):
            cmds.deleteUI(frame)

    actions = cmds.rowLayout(parent=body, numberOfColumns=2,
                             columnWidth2=(175, 175))
    add_panel_button = cmds.button(parent=actions, label="+ Add Panel", width=175,
                                   height=26, command=lambda *unused: add_panel())
    cmds.button(parent=actions, label="Remove Item", width=175, height=26,
                command=remove_item)

    def toggle_mode(*unused):
        is_pose = cmds.optionMenu(mode_menu, query=True, value=True) == "Pose 2D"
        cmds.columnLayout(pose_host, edit=True, manage=is_pose)
        cmds.columnLayout(panel_host, edit=True, manage=not is_pose)
        for key in ("parent", "start", "end", "contain"):
            cmds.rowLayout(object_layouts[key], edit=True, manage=not is_pose)
        cmds.rowLayout(zone_layout, edit=True, manage=not is_pose)
        cmds.button(add_panel_button, edit=True, enable=not is_pose)

    cmds.optionMenu(mode_menu, edit=True, changeCommand=toggle_mode)
    toggle_mode()
    _UI_ROWS[frame] = fields
    return frame


def _collect_ui():
    """Serialize each Item's current UI values."""
    return [_collect_item(fields) for fields in _UI_ROWS.values()]



def Load(data, listUI, *args):
    import maya.cmds as cmds
    for widget in cmds.layout(listUI, query=True, childArray=True) or []:
        if cmds.layout(widget, exists=True):
            cmds.deleteUI(widget)
    _UI_ROWS.clear()
    for record in _read_settings(data):
        Add(listUI, _adapt_item(record))
    if not _UI_ROWS:
        Add(listUI, {})


def Run(data, *args):
    return [BuildAutoSkirtVectorItem(item) for item in _read_settings(data)]


def _compact_export_source(function):
    source = inspect.getsource(function)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                node.body.pop(0)
    lines = ast.unparse(tree).splitlines()
    # ast.unparse removes comments; restore only the brief workflow notes.
    anchors = (
        ("original_parent = (cmds.listRelatives(", "Match Offset 1 to Driven before parenting it into the original hierarchy"),
        ("root = cmds.createNode('transform', name=prefix + '_DrivenOffset'", "Match Offset 2 to Driven, then parent it under Offset 1"),
        ("parent_inverse = matrix(", "Capture neutral only after completing the Driven hierarchy"),
        ("samples = {}", "Read Start-End in Parent space"),
        ("rest = cmds.getAttr(live", "Store the exact neutral vector evaluated by Maya"),
        ("delta = create('plusMinusAverage', 'DeltaVector')", "Subtract the rest vector first so neutral swing is exactly zero"),
        ("dot = create('vectorProduct', 'NeutralDot')", "Project the delta onto the neutral plane"),
        ("for axis in 'XYZ':", "Create the output sums without driving the offset yet"),
        ("for axis in 'XYZ':", "Cancel each neutral output before connecting to the DrivenOffset"),
        ("source_options = (", "Build independent pose panels"),
        ("for index, axis in enumerate('XYZ', 1):", "Route each panel to its selected output axis"),
    )
    for anchor, note in anchors:
        for index, line in enumerate(lines):
            if line.strip().startswith(anchor) and (
                    anchor != "for axis in 'XYZ':" or
                    (index + 1 < len(lines) and lines[index + 1].strip().startswith(
                        "create('plusMinusAverage', 'OutputSum'") if "Create the output sums" in note
                     else index + 1 < len(lines) and lines[index + 1].strip().startswith(
                        "result = prefix + '_OutputSum'"))):
                lines.insert(index, line[:len(line) - len(line.lstrip())] + "# " + note)
                break
    return "\n".join(lines)


def ExportPython(data, *args):
    configs = []
    for item in _read_settings(data):
        mode = _adapt_item(item)["mode"]
        arguments = _pose_arguments(item) if mode == "pose2d" else _rig_arguments(item)
        configs.append({"mode": mode, "arguments": arguments})
    builders = [_compact_export_source(CreateAutoSkirtVector),
                _compact_export_source(CreateAutoSkirtPose2D)]
    content = "\n\n".join(builders)
    content += "\n\nSETTINGS = " + repr(configs)
    content += ("\n\nfor item in SETTINGS:\n"
                "    if item['mode'] == 'pose2d':\n"
                "        CreateAutoSkirtPose2D(**item['arguments'])\n"
                "    else:\n"
                "        CreateAutoSkirtVector(**item['arguments'])\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(content, filename, "exec")
    output = os.path.join(os.path.dirname(_pattern_path(data)), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(content)
    print("[AutoSkirtVector] Exported " + output)
    return output


def OpenExportFolder(data, *args):
    import maya.cmds as cmds
    folder = os.path.dirname(_pattern_path(data))
    if hasattr(os, "startfile"):
        os.startfile(folder)
    else:
        cmds.warning("Open folder manually: " + folder)


def Form(data, *args):
    import maya.cmds as cmds
    import NLTA_General
    layout = NLTA_General.LoadModule("Scene_Form").Create(data)
    bar, list_ui = layout["buttonUI"], layout["listUI"]
    _UI_ROWS.clear()
    button_row = cmds.rowLayout(parent=bar, numberOfColumns=4,
                                columnWidth4=(82, 82, 82, 102))

    def save(*unused):
        path = _pattern_path(data)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(_collect_ui(), stream, ensure_ascii=False, indent=2)

    def save_run(*unused):
        save()
        return Run(data)

    def save_export(*unused):
        save()
        return ExportPython(data)

    cmds.button(parent=button_row, label="Add", width=82,
                command=lambda *unused: Add(list_ui, {}))
    cmds.button(parent=button_row, label="Save", width=82, command=save)
    cmds.button(parent=button_row, label="Run", width=82, command=save_run)
    export_button = cmds.button(
        parent=button_row, label="Export Py", width=102, command=save_export)
    popup = cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(parent=popup, label="Open Folder",
                  command=lambda *unused: OpenExportFolder(data))
    cmds.setParent("..")
    Load(data, list_ui)
