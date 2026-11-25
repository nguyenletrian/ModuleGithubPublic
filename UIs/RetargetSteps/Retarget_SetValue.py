"""Assign multiple Maya attribute values per object in a selected namespace."""
import math
import re

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Set Value"


def ItemData(item):
    attributes = item.get("attributes")
    if attributes is None:
        attributes = [{"attribute": item.get("attribute", ""),
                       "value": item.get("value", "0")}]
    if not isinstance(attributes, list) or any(not isinstance(entry, dict) for entry in attributes):
        raise ValueError("Set Value attributes must be a list of Attribute / Value entries.")
    return {"source": item.get("source") or "Rig",
            "object": str(item.get("object") or ""),
            "mirror": bool(item.get("mirror", False)),
            "attributes": [{"attribute": str(entry.get("attribute") or ""),
                            "value": str(entry.get("value", "0"))}
                           for entry in attributes]}


def DefaultSetting():
    return {"items": [ItemData({})]}


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
    elif any(key in settings for key in ("source", "object", "attribute", "value", "attributes")):
        items = [settings]
    else:
        items = []
    if not isinstance(items, list):
        raise ValueError("Set Value items must be a list.")
    return items


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


def Run(settings, context):
    changes = []
    for index, item in enumerate(_items(settings), start=1):
        if not isinstance(item, dict):
            raise ValueError("Set Value Sub Item {} is invalid.".format(index))
        item = ItemData(item)
        namespace = _namespace(item["source"], context)
        name = item["object"].strip()
        if not name or not item["attributes"]:
            raise ValueError("Set Value Sub Item {} needs an object and attributes.".format(index))
        node = rt.resolve(namespace, name)
        nodes = [node]
        if item.get("mirror", False):
            leaf = rt.leaf(node)
            opposite = _mirror_name(leaf)
            if opposite != leaf:
                mirrored = rt.resolve(namespace, opposite)
                if mirrored != node:
                    nodes.append(mirrored)
        for entry in item["attributes"]:
            attribute = entry["attribute"].strip()
            if not attribute or "." in attribute:
                raise ValueError("Set Value Sub Item {} needs a valid attribute.".format(index))
            for destination in nodes:
                plug = "{}.{}".format(destination, attribute)
                if not cmds.objExists(plug):
                    raise ValueError("Set Value attribute not found: " + plug)
                if not cmds.getAttr(plug, settable=True):
                    raise ValueError("Set Value attribute locked or connected: " + plug)
                kind = cmds.getAttr(plug, type=True)
                value = _attribute_value(kind, entry["value"], plug)
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
