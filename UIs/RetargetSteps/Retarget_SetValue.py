"""Assign one Maya attribute directly to a value in a selected namespace."""
import math
import re

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Set Value"


def DefaultSetting():
    return {"items": [{"source": "Rig", "object": "",
                       "attribute": "", "value": "0"}]}


def Fields():
    return [("Sub Items", "items", "set_values")]


def _namespace(role, context):
    refs = context.get("reference_namespaces") or {}
    if role == "Rig":
        namespace = context.get("target_namespace") or refs.get("new_rig")
    elif role == "Anim":
        namespace = (context.get("source_namespace_animation")
                     or refs.get("old_animations")
                     or context.get("source_namespace"))
    elif role == "REF":
        if context.get("reference_pose_loaded") is False:
            raise ValueError("Reference Pose has not been imported.")
        namespace = context.get("reference_pose_namespace") or refs.get(
            "reference_pose")
    else:
        raise ValueError("Choose Rig, Anim or REF namespace.")
    if not namespace:
        raise ValueError("{} namespace is not available.".format(role))
    return str(namespace).strip(":")


def _attribute_value(kind, text, plug):
    raw = str(text)
    stripped = raw.strip()
    if kind == "string":
        return raw
    if kind == "bool":
        if stripped.lower() in ("1", "true", "yes", "on"):
            return True
        if stripped.lower() in ("0", "false", "no", "off"):
            return False
        raise ValueError("Set Value bool needs True/False or 1/0: " + plug)
    if kind in ("enum", "byte", "char", "short", "long", "longLong"):
        if not re.fullmatch(r"[+-]?\d+", stripped):
            raise ValueError("Set Value requires an integer: " + plug)
        return int(stripped)
    if kind in ("double", "float", "doubleLinear", "doubleAngle", "time"):
        value = float(stripped)
        if not math.isfinite(value):
            raise ValueError("Set Value requires a finite number: " + plug)
        return value
    if kind in ("double3", "float3", "long3", "short3"):
        parts = [part for part in re.split(r"[,;\s]+", stripped) if part]
        if len(parts) != 3:
            raise ValueError("Set Value needs three XYZ values: " + plug)
        if kind in ("long3", "short3"):
            if not all(re.fullmatch(r"[+-]?\d+", part) for part in parts):
                raise ValueError("Set Value XYZ must be integers: " + plug)
            return tuple(int(part) for part in parts)
        values = tuple(float(part) for part in parts)
        if not all(math.isfinite(number) for number in values):
            raise ValueError("Set Value XYZ requires finite values: " + plug)
        return values
    raise ValueError("Set Value does not support attribute type {!r}: {}".format(
        kind, plug))



def _items(settings):
    """Accept current sub-items and one-value settings from older saved JSON."""
    if "items" in settings:
        items = settings["items"]
    elif any(key in settings for key in ("source", "object", "attribute", "value")):
        items = [settings]
    else:
        items = []
    if not isinstance(items, list):
        raise ValueError("Set Value items must be a list.")
    return items


def Run(settings, context):
    changes = []
    for index, item in enumerate(_items(settings), start=1):
        if not isinstance(item, dict):
            raise ValueError("Set Value Sub Item {} is invalid.".format(index))
        namespace = _namespace(item.get("source", "Rig"), context)
        name = str(item.get("object") or "").strip()
        attribute = str(item.get("attribute") or "").strip()
        if not name or not attribute or "." in attribute:
            raise ValueError(
                "Set Value Sub Item {} needs an object and attribute.".format(
                    index))
        node = rt.resolve(namespace, name)
        plug = "{}.{}".format(node, attribute)
        if not cmds.objExists(plug):
            raise ValueError("Set Value attribute not found: " + plug)
        if not cmds.getAttr(plug, settable=True):
            raise ValueError("Set Value attribute locked or connected: " + plug)
        kind = cmds.getAttr(plug, type=True)
        value = _attribute_value(kind, item.get("value", ""), plug)
        changes.append((plug, kind, value))

    # Resolve every sub-item before making scene changes.
    for plug, kind, value in changes:
        if kind == "string":
            cmds.setAttr(plug, value, type="string")
        elif kind in ("double3", "float3", "long3", "short3"):
            cmds.setAttr(plug, *value, type=kind)
        else:
            cmds.setAttr(plug, value)
    return {"changed": len(changes), "attributes": [
        plug for plug, _, _ in changes]}
