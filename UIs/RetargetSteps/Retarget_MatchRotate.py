"""One-time world orientation match using automatic signed local-axis mapping."""
import itertools
import math

import maya.cmds as cmds
import maya.api.OpenMaya as om
import NLTA_RetargetV2 as rt

LABEL = "Match Rotate"
_AXES = "XYZ"


def PairData(pair):
    return {"from_role": pair.get("from_role") or "REF",
            "from": str(pair.get("from") or ""),
            "to_role": pair.get("to_role") or "Rig",
            "to": str(pair.get("to") or "")}


def DefaultSetting():
    return {"pairs": [PairData({})]}


def Fields():
    return [("Rotation Pairs", "pairs", "match_rotate_pairs")]


def _namespace(role, context):
    refs = context.get("reference_namespaces") or {}
    if role == "Rig":
        ns = context.get("target_namespace") or refs.get("new_rig")
    elif role == "Anim":
        ns = (context.get("source_namespace_animation") or
              refs.get("old_animations") or context.get("source_namespace"))
    elif role == "REF":
        if context.get("reference_pose_loaded") is False:
            raise ValueError("Reference Pose has not been imported. Select Anim instead.")
        ns = context.get("reference_pose_namespace") or refs.get("reference_pose")
    else:
        raise ValueError("Unknown namespace role: " + str(role))
    if not ns:
        raise ValueError("Namespace is not available: " + str(role))
    return str(ns).strip(":")


def _resolve_pairs(settings, context):
    """Resolve only user-selected objects, never infer object pairings."""
    pairs = settings.get("pairs") or []
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("Match Rotate: add at least one From / To pair.")
    result = []
    for index, raw in enumerate(pairs, start=1):
        if not isinstance(raw, dict):
            raise ValueError("Invalid Match Rotate pair: " + str(index))
        pair = PairData(raw)
        source = pair["from"].strip()
        target = pair["to"].strip()
        if not source or not target:
            raise ValueError("Match Rotate Pair {}: select From and To.".format(index))
        result.append((rt.resolve(_namespace(pair["from_role"], context), source),
                       rt.resolve(_namespace(pair["to_role"], context), target)))
    return result


def _axis_mapping(source_axes, target_axes):
    """Choose the closest of 24 proper signed permutations (no reflection).

    Returns each target axis's source index and sign, plus the desired target
    world basis. Maximizing the trace minimizes the rotation angle.
    """
    best = None
    for order in itertools.permutations(range(3)):
        inversions = sum(order[i] > order[j] for i in range(3)
                         for j in range(i + 1, 3))
        parity = -1 if inversions % 2 else 1
        for signs in itertools.product((1, -1), repeat=3):
            if signs[0] * signs[1] * signs[2] != parity:
                continue
            basis = tuple(tuple(signs[i] * x for x in source_axes[order[i]])
                          for i in range(3))
            score = sum(sum(a * b for a, b in zip(basis[i], target_axes[i]))
                        for i in range(3))
            if best is None or score > best[0] + 1e-12:
                best = (score, order, signs, basis)
    return best[1], best[2], best[3]


def _world_axes(node):
    quaternion = rt._rotation(node)
    return tuple(tuple(om.MVector(*axis).rotateBy(quaternion))
                 for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))


def _quaternion(basis):
    matrix = om.MMatrix([*basis[0], 0.0, *basis[1], 0.0,
                         *basis[2], 0.0, 0.0, 0.0, 0.0, 1.0])
    return om.MTransformationMatrix(matrix).rotation(asQuaternion=True)


def Run(settings, context):
    pairs = _resolve_pairs(settings, context)
    pending = []
    used = set()
    for source, target in pairs:
        if source == target or target in used:
            raise ValueError("Invalid or repeated To: " + target)
        used.add(target)
        for axis in _AXES:
            if not cmds.getAttr(target + ".rotate" + axis, settable=True):
                raise ValueError("Rotate channel is locked/connected: " + target + ".rotate" + axis)
        order, signs, basis = _axis_mapping(_world_axes(source), _world_axes(target))
        mapping = {_AXES[i]: ("+" if signs[i] > 0 else "-") + _AXES[order[i]]
                   for i in range(3)}
        pending.append((source, target, _quaternion(basis), mapping))

    # Freeze each desired world orientation before moving any target parent.
    for source, target, desired, mapping in sorted(
            pending, key=lambda item: item[1].count("|")):
        values = rt._euler_angles(desired, cmds.getAttr(target + ".rotateOrder"))
        cmds.xform(target, worldSpace=True, rotation=values)

    results = []
    for source, target, desired, mapping in pending:
        actual = rt._rotation(target)
        dot = abs(sum(a * b for a, b in zip(
            (actual.x, actual.y, actual.z, actual.w),
            (desired.x, desired.y, desired.z, desired.w))))
        error = math.degrees(2.0 * math.acos(min(1.0, max(0.0, dot))))
        if error > 0.1:
            cmds.warning("Match Rotate: {} orientation error {:.3f} deg".format(
                rt.leaf(target), error))
        print("[Match Rotate] {} -> {} | {}".format(
            rt.leaf(source), rt.leaf(target),
            ", ".join("{}:{}".format(axis, mapping[axis]) for axis in _AXES)))
        results.append({"from": source, "to": target, "axes": mapping,
                        "error_degrees": error})

    if context.get("pairs") and context.get("bind"):
        context["bind"] = rt.capture_bind(context["pairs"], context["source_namespace"],
                                          context["target_namespace"])
    context["rotate_matches"] = results
    return {"matched": len(results), "mapping": "automatic axes",
            "max_error_degrees": max(item["error_degrees"] for item in results)}
