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


def _removal_indices(values, trim_tail=True):
    """Keep both boundaries of holds before a value change."""
    if not values:
        return [], False
    if all(value == values[0] for value in values):
        if values[0] == 0:
            return list(range(len(values))), True
        return list(range(1, len(values))), False
    end = len(values) - 1
    indices = [i for i in range(1, end)
               if values[i - 1] == values[i] == values[i + 1]]
    # Constant post-infinity extends the last pose without a trailing key.
    if trim_tail and values[end] == values[end - 1]:
        indices.append(end)
    return indices, False


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
                print("[Clean Animation] Skipped {}: multiple curves or non-time curve".format(plug))
                continue
            curve = curves[0]
            if curve in seen:
                continue
            seen.add(curve)
            outputs = cmds.listConnections(curve + ".output", source=False,
                                           destination=True, plugs=True) or []
            if len(set(outputs)) != 1:
                skipped += 1
                print("[Clean Animation] Skipped {}: shared or missing curve output".format(plug))
                continue
            values = cmds.keyframe(curve, query=True, valueChange=True) or []
            indices, zero = _removal_indices(
                values, trim_tail=(cmds.getAttr(curve + ".postInfinity") == 0))

            # Bake may leave a tiny floating-point residual displayed as 0.
            if len(values) == 1 and abs(values[0]) <= 1e-6 and not zero:
                times = cmds.keyframe(curve, query=True, timeChange=True) or []
                zero = times == [0]
                if zero:
                    indices = [0]

            if not indices:
                continue

            # A baked animation curve may drive a pairBlend input rather
            # than the controller itself. Preserve that input at zero,
            # leaving the blend, constraints and all other channels intact.
            destination = None
            if cmds.isConnected(curve + ".output", plug):
                destination = plug
            else:
                output = outputs[0]
                if cmds.nodeType(output.split(".", 1)[0]) in ("pairBlend", "unitConversion"):
                    destination = output

            if zero:
                if destination and not cmds.getAttr(destination, lock=True):
                    cmds.delete(curve)
                    cmds.setAttr(destination, 0)
                    removed += len(values)
                    zero_channels += 1
                    cleaned.add(node)
                else:
                    skipped += 1
                    print("[Clean Animation] Retained zero curve {}: {} (protected or unsupported connection)".format(plug, outputs))
                continue

            for first, last in _ranges(indices):
                cmds.cutKey(curve, index=(first, last), animation="objects",
                            option="keys", clear=True)
            remaining = (cmds.keyframe(curve, query=True, valueChange=True) or []
                         if cmds.objExists(curve) else [])
            if len(remaining) == 1 and abs(remaining[0]) <= 1e-6:
                times = cmds.keyframe(curve, query=True, timeChange=True) or []
                if times == [0] and destination and not cmds.getAttr(destination, lock=True):
                    cmds.delete(curve)
                    cmds.setAttr(destination, 0)
                    remaining = []
                    zero_channels += 1
            removed += len(values) - len(remaining)
            cleaned.add(node)
    return {"namespace": namespace, "controls": len(controls),
            "cleaned_controls": len(cleaned), "removed_keys": removed,
            "zero_channels": zero_channels, "skipped_channels": skipped}
