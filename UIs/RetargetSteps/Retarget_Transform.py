"""Add local Translate, Rotate and Scale offsets to one picked Maya object.

Rig = New Rig namespace, Anim = animation namespace, REF = Reference Pose.
Values are additive channel offsets; scale is not multiplied.
"""
import math

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Extra Transform"

_AXES = ("X", "Y", "Z")
_GROUPS = ("translate", "rotate", "scale")


def DefaultSetting():
    return {
        "source": "Rig",
        "object": "",
        "offsets": {
            "translate": [0.0, 0.0, 0.0],
            "rotate": [0.0, 0.0, 0.0],
            "scale": [0.0, 0.0, 0.0],
        },
    }


def Fields():
    return [
        ("Namespace", "source", "choice", ("Rig", "Anim", "REF")),
        ("Object", "object", "pick"),
        ("Additive Transform Offsets", "offsets", "transform9"),
    ]


def _namespace(source, context):
    """Use the namespaces of the assets actually imported by Retarget."""
    source = str(source or "Rig").strip()
    if source == "Rig":
        namespace = (context.get("target_namespace")
                     or context.get("reference_namespaces", {}).get("new_rig"))
    elif source == "Anim":
        namespace = (context.get("source_namespace_animation")
                     or context.get("reference_namespaces", {}).get(
                         "old_animations"))
    elif source == "REF":
        namespace = (context.get("reference_pose_namespace")
                     or context.get("reference_namespaces", {}).get(
                         "reference_pose"))
        if not context.get("reference_pose_loaded", True):
            raise ValueError("Reference Pose has not been imported.")
    else:
        raise ValueError("Choose Rig, Anim or REF.")
    if not namespace:
        raise ValueError("The {} namespace is unavailable.".format(source))
    return str(namespace).strip(":")


def _offsets(data):
    """Return finite numeric offsets in channel order."""
    data = data if isinstance(data, dict) else {}
    result = {}
    for group in _GROUPS:
        values = data.get(group, [0.0, 0.0, 0.0])
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise ValueError("{} offsets must have three values.".format(group))
        result[group] = []
        for value in values:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("Transform offsets must be finite numbers.")
            result[group].append(number)
    return result


def Run(settings, context):
    name = str(settings.get("object") or "").strip()
    if not name:
        raise ValueError("Pick one Transform object.")
    namespace = _namespace(settings.get("source", "Rig"), context)
    node = rt.resolve(namespace, name)
    offsets = _offsets(settings.get("offsets"))
    changes = []

    # Validate all channels before writing anything: a connected or locked
    # channel with a non-zero offset must not cause a partial update.
    for group in _GROUPS:
        for axis, delta in zip(_AXES, offsets[group]):
            if delta == 0.0:
                continue
            plug = "{}.{}{}".format(node, group, axis)
            if not cmds.getAttr(plug, settable=True):
                raise ValueError("Transform channel is locked/connected: " + plug)
            current = cmds.getAttr(plug)
            if not isinstance(current, (float, int)):
                raise ValueError("Transform channel is not numeric: " + plug)
            changes.append((plug, float(current) + delta))

    for plug, value in changes:
        cmds.setAttr(plug, value)
    return {"object": node, "namespace": namespace, "changed": len(changes)}
