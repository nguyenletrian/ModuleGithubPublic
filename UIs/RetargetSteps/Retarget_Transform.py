"""Add local Translate, Rotate and Scale offsets to ordered Maya objects.

Rig = New Rig namespace, Anim = animation namespace, REF = Reference Pose.
Values are additive channel offsets; scale is not multiplied.
"""
import math

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Extra Transform"

_AXES = ("X", "Y", "Z")
_GROUPS = ("translate", "rotate", "scale")


def ItemData(item):
    return {"source": str(item.get("source") or "Rig"),
            "object": str(item.get("object") or "").strip(),
            "offsets": _offsets(item.get("offsets"))}


def DefaultSetting():
    return {"items": [ItemData({})]}


def NormalizeSettings(settings):
    items = settings.get("items")
    if items is None:
        items = [settings]
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Extra Transform items must be a list of objects.")
    return {"items": [ItemData(item) for item in items]}


def Fields():
    return [("Items", "items", "transform_items")]


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
    changes = {}
    objects = []
    for index, item in enumerate(NormalizeSettings(settings)["items"], 1):
        name = item["object"]
        offsets = item["offsets"]
        if not name:
            if not any(delta for values in offsets.values() for delta in values):
                continue
            raise ValueError("Extra Transform Item {}: pick an object.".format(index))
        namespace = _namespace(item["source"], context)
        node = rt.resolve(namespace, name)
        objects.append(node)
        # Validate all channels before writing. Repeated entries accumulate
        # additive offsets in item order without reading stale scene values.
        for group in _GROUPS:
            for axis, delta in zip(_AXES, offsets[group]):
                if delta == 0.0:
                    continue
                plug = "{}.{}{}".format(node, group, axis)
                if not cmds.getAttr(plug, settable=True):
                    raise ValueError("Transform channel is locked/connected: " + plug)
                current = changes[plug] if plug in changes else cmds.getAttr(plug)
                if not isinstance(current, (float, int)):
                    raise ValueError("Transform channel is not numeric: " + plug)
                changes[plug] = float(current) + delta

    for plug, value in changes.items():
        cmds.setAttr(plug, value)
    return {"items": len(objects), "objects": objects, "changed": len(changes)}
