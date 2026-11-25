"""Align From -> From Child and To -> To Child using a one-time rotation."""
import math

import maya.cmds as cmds
import maya.api.OpenMaya as om
import NLTA_RetargetV2 as rt

LABEL = "Match Rotate Pair"
_AXES = "XYZ"
_KEYS = ("from", "from_child", "to", "to_child")


def PairData(pair):
    """Preserve old source/target selections; child inputs are new."""
    from_role = pair.get("from_role") or pair.get("source_role") or "Anim"
    to_role = pair.get("to_role") or pair.get("target_role") or "Rig"
    return {
        "from_role": from_role,
        "from": str(pair.get("from", pair.get("source", "")) or ""),
        "from_child_role": pair.get("from_child_role") or from_role,
        "from_child": str(pair.get("from_child") or ""),
        "to_role": to_role,
        "to": str(pair.get("to", pair.get("target", "")) or ""),
        "to_child_role": pair.get("to_child_role") or to_role,
        "to_child": str(pair.get("to_child") or ""),
    }


def DefaultSetting():
    return {"pairs": [PairData({})]}


def Fields():
    return [("Rotation Pairs", "pairs", "rotate_pairs")]


def _namespace(role, context):
    references = context.get("reference_namespaces") or {}
    if role == "Rig":
        namespace = context.get("target_namespace") or references.get("new_rig")
    elif role == "Anim":
        namespace = (context.get("source_namespace_animation")
                     or references.get("old_animations")
                     or context.get("source_namespace"))
    elif role == "REF":
        if context.get("reference_pose_loaded") is False:
            raise ValueError("Reference Pose has not been imported.")
        namespace = (context.get("reference_pose_namespace")
                     or references.get("reference_pose"))
    else:
        raise ValueError("Pair namespace must be Rig, Anim or REF.")
    if not namespace:
        raise ValueError("{} namespace is not available.".format(role))
    return str(namespace).strip(":")


def _resolve_pair(pair, context):
    data = PairData(pair)
    nodes = {}
    for key in _KEYS:
        if not data[key].strip():
            raise ValueError("Select {} object.".format(key.replace("_", " ").title()))
        nodes[key] = rt.resolve(_namespace(data[key + "_role"], context),
                                data[key].strip())
    if nodes["from"] == nodes["to"]:
        raise ValueError("From and To must be different objects.")
    return nodes


def _direction(node, child):
    vector = om.MVector(*rt.position(child)) - om.MVector(*rt.position(node))
    if vector.length() <= 1e-10:
        raise ValueError("Zero-length direction: {} -> {}".format(node, child))
    return vector.normal()


def _post_rotation_matrix(node):
    """Linear basis after the rotate channels, in Maya row-vector order.

    Transform: R * offsetParentMatrix * parentWorld.
    Joint: R * jointOrient * inverseScale * offsetParentMatrix * parentWorld.
    Translation terms do not affect MVector multiplication.
    """
    matrix = om.MMatrix()
    if cmds.nodeType(node) == "joint":
        orient = cmds.getAttr(node + ".jointOrient")[0]
        matrix = om.MEulerRotation(
            *(math.radians(value) for value in orient)).asMatrix()
        if cmds.getAttr(node + ".segmentScaleCompensate"):
            scale = cmds.getAttr(node + ".inverseScale")[0]
            if any(abs(value) <= 1e-10 for value in scale):
                raise ValueError("Invalid inverseScale: " + node)
            x, y, z = (1.0 / value for value in scale)
            matrix = matrix * om.MMatrix([
                x, 0, 0, 0, 0, y, 0, 0,
                0, 0, z, 0, 0, 0, 0, 1])
    if cmds.objExists(node + ".offsetParentMatrix"):
        offset = cmds.getAttr(node + ".offsetParentMatrix")
        if len(offset) == 1:
            offset = offset[0]
        matrix = matrix * om.MMatrix(offset)
    parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
    if parents and cmds.getAttr(node + ".inheritsTransform"):
        matrix = matrix * om.MMatrix(cmds.xform(
            parents[0], query=True, worldSpace=True, matrix=True))
    if abs(matrix.det4x4()) <= 1e-12:
        raise ValueError("Singular rotation basis: " + node)
    return matrix


def _match_pair(nodes):
    target = nodes["to"]
    desired = _direction(nodes["from"], nodes["from_child"])
    current = _direction(target, nodes["to_child"])
    if current * desired >= 1.0 - 1e-10:
        return

    # Solve the direction in the rotate-channel frame, including jointOrient
    # and scaled parents, instead of copying world Euler angles.
    inverse = _post_rotation_matrix(target).inverse()
    delta = (current * inverse).normal().rotateTo((desired * inverse).normal())
    order = int(cmds.getAttr(target + ".rotateOrder"))
    angles = cmds.getAttr(target + ".rotate")[0]
    before = om.MEulerRotation(
        *(math.radians(value) for value in angles), order)
    after = (before.asQuaternion() * delta).asEulerRotation()
    after.reorderIt(order)
    after = after.closestSolution(before)
    for axis, value in zip(_AXES, (after.x, after.y, after.z)):
        cmds.setAttr(target + ".rotate" + axis, math.degrees(value))


def _similarity(nodes):
    return (_direction(nodes["from"], nodes["from_child"]) *
            _direction(nodes["to"], nodes["to_child"]))


def Run(settings, context):
    pairs = settings.get("pairs") or []
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("Match Rotate Pair needs at least one added Pair.")
    pending = []
    used = set()
    for index, pair in enumerate(pairs, start=1):
        if not isinstance(pair, dict):
            raise ValueError("Invalid Match Rotate Pair item {}.".format(index))
        nodes = _resolve_pair(pair, context)
        target = nodes["to"]
        if target in used:
            raise ValueError("Repeated To in Match Rotate Pair: " + target)
        used.add(target)
        _direction(nodes["from"], nodes["from_child"])
        _direction(target, nodes["to_child"])
        for axis in _AXES:
            plug = target + ".rotate" + axis
            if not cmds.getAttr(plug, settable=True):
                raise ValueError("Rotate channel is locked/connected: " + plug)
        pending.append(nodes)

    # Parent rotations must be applied before descendant rotations.
    for nodes in sorted(pending, key=lambda item: item["to"].count("|")):
        _match_pair(nodes)

    results = []
    for nodes in pending:
        similarity = max(-1.0, min(1.0, _similarity(nodes)))
        if similarity < 1.0 - 1e-6:
            raise ValueError(
                "Directions are not aligned: {} -> {}. Check that To Child "
                "follows To and that later pairs do not move its direction."
                .format(nodes["to"], nodes["to_child"]))
        result = dict(nodes, similarity=similarity)
        results.append(result)
        print("[Match Rotate Pair] {} -> {} | angle {:.4f} deg".format(
            rt.leaf(nodes["from"]), rt.leaf(nodes["to"]),
            math.degrees(math.acos(similarity))))

    # Preserve the existing bind refresh for the subsequent animation steps.
    if context.get("pairs") and context.get("bind"):
        context["bind"] = rt.capture_bind(
            context["pairs"], context["source_namespace"],
            context["target_namespace"])
    context.pop("axis_maps", None)
    context["vector_matches"] = results
    return {"matched": len(results), "vector_matches": results}
