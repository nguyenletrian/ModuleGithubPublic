"""Match user-selected source/target rotation pairs by corresponding axes.

Each pair has separate Rig, Anim or REF namespace choices. Two local axes
are compared in the current scene to infer target axis mapping and signs.
AnalyzePair previews the mapping; Run applies it once, without keyframes.
"""
import itertools
import math

import maya.cmds as cmds
import maya.api.OpenMaya as om
import NLTA_RetargetV2 as rt

LABEL = "Match Rotate Pair"
_AXES = "XYZ"


def DefaultSetting():
    return {
        "pairs": [{"source_role": "Anim", "source": "",
                   "target_role": "Rig", "target": ""}],
        "minimum_alignment": 0.7,
    }


def Fields():
    return [
        ("Rotation Pairs", "pairs", "rotate_pairs"),
        ("Minimum Axis Similarity", "minimum_alignment", "float"),
    ]


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


def _world_axes(quaternion):
    return [tuple(om.MVector(*axis).rotateBy(quaternion))
            for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]


def _map_axes(source_axes, target_axes, minimum):
    """Match two source axes against two distinct target axes."""
    minimum = float(minimum)
    if not math.isfinite(minimum) or not 0.0 <= minimum <= 1.0:
        raise ValueError("Minimum Axis Similarity must be between 0 and 1.")
    best = None
    for order in itertools.permutations(range(3)):
        dots = [sum(a * b for a, b in zip(
            source_axes[i], target_axes[order[i]])) for i in range(3)]
        score = (min(abs(dots[0]), abs(dots[1])),
                 abs(dots[0]) + abs(dots[1]), abs(dots[2]))
        if best is None or score > best[0]:
            best = (score, order, dots)
    score, order, dots = best
    if score[0] < minimum:
        raise ValueError(
            "Pair axes are not aligned clearly (score {:.3f} < {:.3f}). "
            "Check the reference pose or reduce the similarity threshold."
            .format(score[0], minimum))
    signs = [1 if dots[i] >= 0 else -1 for i in (0, 1)]
    inversions = sum(order[i] > order[j] for i in range(3)
                     for j in range(i + 1, 3))
    signs.append((1 if inversions % 2 == 0 else -1) *
                 signs[0] * signs[1])
    return order, signs, score[0]


def _remap_rotation(source, target, order, signs):
    source_order = int(cmds.getAttr(source + ".rotateOrder"))
    target_order = int(cmds.getAttr(target + ".rotateOrder"))
    channels = [float(cmds.getAttr(source + ".rotate" + axis))
                for axis in _AXES]
    rotation = om.MEulerRotation(
        *(math.radians(value) for value in channels), source_order)
    quaternion = rotation.asQuaternion()
    vector = [0.0, 0.0, 0.0]
    for source_axis, target_axis in enumerate(order):
        vector[target_axis] = signs[source_axis] * (
            quaternion.x, quaternion.y, quaternion.z)[source_axis]
    converted = om.MQuaternion(*vector, quaternion.w).asEulerRotation()
    converted.reorderIt(target_order)
    values = [math.degrees(value) for value in (
        converted.x, converted.y, converted.z)]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Invalid rotation for target: " + target)
    return values


def AnalyzePair(pair, context, minimum=0.7):
    """Inspect one named pair without modifying either Maya object."""
    source_ns = _namespace(pair.get("source_role", "Anim"), context)
    target_ns = _namespace(pair.get("target_role", "Rig"), context)
    source = rt.resolve(source_ns, str(pair.get("source") or "").strip())
    target = rt.resolve(target_ns, str(pair.get("target") or "").strip())
    if source == target:
        raise ValueError("Source and target must be different objects.")
    source_axes = _world_axes(rt._rotation(source))
    target_axes = _world_axes(rt._rotation(target))
    order, signs, similarity = _map_axes(source_axes, target_axes, minimum)
    mapping = {
        _AXES[index]: ("+" if signs[index] > 0 else "-") +
        _AXES[order[index]] for index in range(3)
    }
    return {
        "source": source, "target": target,
        "order": order, "signs": signs,
        "axes": mapping, "similarity": round(similarity, 4),
    }


def Run(settings, context):
    pairs = settings.get("pairs") or []
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("Match Rotate Pair needs at least one added Pair.")
    minimum = float(settings.get("minimum_alignment", 0.7))
    pending = []
    used = set()

    for index, pair in enumerate(pairs, start=1):
        if not isinstance(pair, dict):
            raise ValueError("Invalid Match Rotate Pair item {}.".format(index))
        mapped = AnalyzePair(pair, context, minimum)
        source, target = mapped["source"], mapped["target"]
        if target in used:
            raise ValueError("Repeated target in Match Rotate Pair: " + target)
        used.add(target)
        values = _remap_rotation(
            source, target, mapped["order"], mapped["signs"])
        for axis in _AXES:
            plug = target + ".rotate" + axis
            if not cmds.getAttr(plug, settable=True):
                raise ValueError("Rotate channel is locked/connected: " + plug)
        pending.append((target, values, mapped))

    for target, values, mapped in pending:
        for axis, value in zip(_AXES, values):
            cmds.setAttr(target + ".rotate" + axis, value)
        print("[Match Rotate Pair] {} -> {} | {}".format(
            rt.leaf(mapped["source"]), rt.leaf(mapped["target"]),
            ", ".join("{}: {}".format(axis, mapped["axes"][axis])
                      for axis in _AXES)))

    # If a separate Control / Joint Mapping was run earlier, refresh its
    # captured target bind orientations for subsequent animation stages.
    if context.get("pairs") and context.get("bind"):
        context["bind"] = rt.capture_bind(
            context["pairs"], context["source_namespace"],
            context["target_namespace"])
    context["axis_maps"] = [mapped for _, _, mapped in pending]
    return {"matched": len(pending), "axis_maps": context["axis_maps"]}
