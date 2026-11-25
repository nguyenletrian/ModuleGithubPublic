"""Remove repeated animation keys from controls in a chosen namespace."""
import re

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Clean Animation"
_TIME_CURVES = ("animCurveTA", "animCurveTL", "animCurveTT", "animCurveTU")


def DefaultSetting():
    return {"namespace_role": "Rig"}


def Fields():
    return [("Namespace", "namespace_role", "choice", ("Rig", "Anim", "REF"))]


def _namespace(role, context):
    roles = {"Rig": ("new_rig", "target_namespace"),
             "Anim": ("old_animations", "source_namespace_animation"),
             "REF": ("reference_pose", "reference_pose_namespace")}
    key, fallback = roles[role]
    namespace = (context.get("reference_namespaces") or {}).get(key) or context.get(fallback)
    if not namespace:
        raise ValueError("Clean Animation namespace unavailable: " + role)
    return str(namespace).strip(":")


def _controls(namespace, role):
    for node in dict.fromkeys(rt.mapping_candidates(namespace)):
        if node.split("|")[-1].lstrip(":").rpartition(":")[0] != namespace:
            continue
        kind = cmds.nodeType(node)
        if kind == "joint":
            if role == "Rig":
                continue
        elif kind != "transform" or not cmds.listRelatives(
                node, shapes=True, noIntermediate=True, type="nurbsCurve"):
            continue
        if not re.search(r"_extraJoint\d*$", rt.leaf(node)):
            yield node


def _removal_indices(values):
    """Compare consecutive original keys, not the changing index after deletion."""
    if values and all(value == 0 for value in values):
        return list(range(len(values))), True
    return [i for i in range(1, len(values)) if values[i] == values[i - 1]], False


def _ranges(indices):
    """Coalesce consecutive key indices; delete ranges from last to first."""
    ranges = []
    for i in indices:
        if ranges and i == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], i)
        else:
            ranges.append((i, i))
    return reversed(ranges)


def Run(settings, context):
    role = settings.get("namespace_role", "Rig")
    namespace = _namespace(role, context)
    controls = list(_controls(namespace, role))
    seen = set()
    cleaned = set()
    removed = zero_channels = skipped = 0
    for node in controls:
        for attr in cmds.listAttr(node, scalar=True, keyable=True, unlocked=True) or []:
            plug = node + "." + attr
            curves = list(dict.fromkeys(cmds.keyframe(plug, query=True, name=True) or []))
            if not curves:
                continue
            # Do not reduce a layer stack or a driven-key curve as though it
            # were the final animation of this channel.
            if len(curves) != 1 or cmds.nodeType(curves[0]) not in _TIME_CURVES:
                skipped += 1
                continue
            curve = curves[0]
            if curve in seen:
                continue
            seen.add(curve)
            outputs = cmds.listConnections(curve + ".output", source=False,
                                           destination=True, plugs=True) or []
            if len(set(outputs)) != 1:
                skipped += 1
                continue
            values = cmds.keyframe(curve, query=True, valueChange=True) or []
            indices, zero = _removal_indices(values)
            if not indices:
                continue
            for first, last in _ranges(indices):
                cmds.cutKey(curve, index=(first, last), animation="objects",
                            option="keys", clear=True)
            if zero and cmds.getAttr(plug, settable=True):
                cmds.setAttr(plug, 0)
            removed += len(indices)
            zero_channels += int(zero)
            cleaned.add(node)
    return {"namespace": namespace, "controls": len(controls),
            "cleaned_controls": len(cleaned), "removed_keys": removed,
            "zero_channels": zero_channels, "skipped_channels": skipped}
