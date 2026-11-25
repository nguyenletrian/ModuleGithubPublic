"""Align From -> From Child and To -> To Child using a one-time rotation."""
import math
import re

import maya.cmds as cmds
import maya.api.OpenMaya as om
import NLTA_RetargetV2 as rt

LABEL = "Match Rotate Vector"
_AXES = "XYZ"
_KEYS = ("from", "from_child", "to", "to_child")
_ALIGNMENT = 1.0 - 1e-6
_MAX_PASSES = 4
_MAX_CORRECTIONS = 4


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
        "mirror": bool(pair.get("mirror", True)),
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


def _mirror_name(name):
    """Swap explicit side tokens without changing unrelated letters."""
    swaps = {"L": "R", "R": "L", "l": "r", "r": "l",
             "Left": "Right", "Right": "Left",
             "left": "right", "right": "left",
             "LEFT": "RIGHT", "RIGHT": "LEFT"}
    patterns = (
        r"(?<=FBXASC032)[LR](?=FBXASC032)",
        r"(?<![A-Za-z0-9])(?:Left|Right|left|right|LEFT|RIGHT|L|R|l|r)(?![A-Za-z0-9])",
        r"^(?:Left|Right)(?=[A-Z0-9])",
        r"(?:Left|Right)$",
    )
    for pattern in patterns:
        mirrored, count = re.subn(pattern, lambda match: swaps[match.group()], name)
        if count:
            return mirrored
    return name


def _mirror_pair(pair, nodes, context):
    data = PairData(pair)
    names = {key: rt.leaf(nodes[key]) for key in _KEYS}
    mirrored = {key: _mirror_name(name) for key, name in names.items()}
    # A center To cannot be rotated twice to independent directions.
    if mirrored["to"] == names["to"]:
        return None
    if all(mirrored[key] == names[key] for key in ("from", "from_child")):
        raise ValueError("Mirror needs a recognizable From-side name: " +
                         names["from"])
    for key in _KEYS:
        data[key] = mirrored[key]
    return _resolve_pair(data, context)


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
    _set_rotation(target, tuple(math.degrees(value)
                                for value in (after.x, after.y, after.z)))


def _set_rotation(node, values):
    for axis, value in zip(_AXES, values):
        cmds.setAttr(node + ".rotate" + axis, value)


def _similarity(nodes):
    return (_direction(nodes["from"], nodes["from_child"]) *
            _direction(nodes["to"], nodes["to_child"]))


def _fit_pair(nodes):
    """Re-evaluate live rig directions and keep only improving rotations."""
    target = nodes["to"]
    best_score = _similarity(nodes)
    if best_score >= _ALIGNMENT:
        return False
    best_rotation = tuple(cmds.getAttr(target + ".rotate")[0])
    improved = False
    for _ in range(_MAX_CORRECTIONS):
        _match_pair(nodes)
        score = _similarity(nodes)
        if score <= best_score + 1e-10:
            # A constrained child may not follow the rotate channels exactly.
            # Never leave a failed correction on the control.
            _set_rotation(target, best_rotation)
            break
        improved = True
        best_score = score
        best_rotation = tuple(cmds.getAttr(target + ".rotate")[0])
        if score >= _ALIGNMENT:
            break
    return improved


def _fit_pairs(pending):
    """Revisit parent-first chains if another pair changes a solved direction."""
    ordered = sorted(pending, key=lambda item: item["to"].count("|"))
    for _ in range(_MAX_PASSES):
        improved = False
        for nodes in ordered:
            if _fit_pair(nodes):
                improved = True
        if all(_similarity(nodes) >= _ALIGNMENT for nodes in ordered):
            break
        if not improved:
            break


def _result(nodes):
    similarity = max(-1.0, min(1.0, _similarity(nodes)))
    angle = math.degrees(math.acos(similarity))
    matched = similarity >= _ALIGNMENT
    print("[Match Rotate Vector] {} -> {} | angle {:.4f} deg{}".format(
        rt.leaf(nodes["from"]), rt.leaf(nodes["to"]), angle,
        "" if matched else " (remaining error)"))
    if not matched:
        cmds.warning(
            "Match Rotate Vector: {} -> {} | remaining angle {:.4f} deg. "
            "Check child follow, constraints or other pairs.".format(
                rt.leaf(nodes["to"]), rt.leaf(nodes["to_child"]), angle))
    return dict(nodes, similarity=similarity, angle_degrees=angle,
                matched=matched)


def Run(settings, context):
    pairs = settings.get("pairs") or []
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("Match Rotate Vector needs at least one added Pair.")
    pending = []
    used = set()
    for index, pair in enumerate(pairs, start=1):
        if not isinstance(pair, dict):
            raise ValueError("Invalid Match Rotate Vector item {}.".format(index))
        nodes = _resolve_pair(pair, context)
        expanded = [nodes]
        if PairData(pair)["mirror"]:
            opposite = _mirror_pair(pair, nodes, context)
            if opposite is not None:
                expanded.append(opposite)
        for nodes in expanded:
            target = nodes["to"]
            if target in used:
                raise ValueError("Repeated To in Match Rotate Vector: " + target)
            used.add(target)
            _direction(nodes["from"], nodes["from_child"])
            _direction(target, nodes["to_child"])
            for axis in _AXES:
                plug = target + ".rotate" + axis
                if not cmds.getAttr(plug, settable=True):
                    raise ValueError("Rotate channel is locked/connected: " + plug)
            pending.append(nodes)

    _fit_pairs(pending)
    results = [_result(nodes) for nodes in pending]

    # Preserve the existing bind refresh for the subsequent animation steps.
    if context.get("pairs") and context.get("bind"):
        context["bind"] = rt.capture_bind(
            context["pairs"], context["source_namespace"],
            context["target_namespace"])
    context.pop("axis_maps", None)
    context["vector_matches"] = results
    matched = sum(item["matched"] for item in results)
    return {"matched": matched, "unmatched": len(results) - matched,
            "max_error_degrees": max(item["angle_degrees"] for item in results),
            "vector_matches": results}
