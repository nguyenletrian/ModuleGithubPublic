"""Bake animation controls, not the internal rigging hierarchy."""
import math

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Bake Animation"
_CHANNELS = tuple(group + axis for group in ("translate", "rotate", "scale") for axis in "XYZ")


def DefaultSetting():
    return {"namespace_role": "Rig", "range_role": "Anim", "range_object": ""}


def NormalizeSettings(settings):
    data = DefaultSetting()
    for key in data:
        if key in settings:
            data[key] = str(settings[key] or "").strip()
    for key in ("namespace_role", "range_role"):
        if data[key] not in ("Rig", "Anim", "REF"):
            raise ValueError("Bake: choose Rig, Anim or REF.")
    return data


def Fields():
    return [("Bake", "bake_settings", "bake_settings")]


def _namespace(role, context):
    roles = {"Rig": ("new_rig", "target_namespace"),
             "Anim": ("old_animations", "source_namespace_animation"),
             "REF": ("reference_pose", "reference_pose_namespace")}
    key, fallback = roles[role]
    namespace = (context.get("reference_namespaces") or {}).get(key) or context.get(fallback)
    if not namespace:
        raise ValueError("Bake namespace unavailable: " + role)
    return str(namespace).strip(":")


def _range(node):
    keys = cmds.keyframe(node, query=True, timeChange=True) or []
    if not keys:
        raise ValueError("Bake range object has no animation keys: " + node)
    return int(math.floor(min(keys))), int(math.ceil(max(keys)))


def _channels(namespace, role="Rig"):
    nodes = []
    plugs = []
    for node in dict.fromkeys(rt.mapping_candidates(namespace)):
        if node.split("|")[-1].lstrip(":").rpartition(":")[0] != namespace:
            continue
        kind = cmds.nodeType(node)
        # Rig animation is authored on curve controllers, never deform/IK joints.
        # Anim and REF may themselves be skeletons, so allow their joints too.
        if kind == "joint":
            if role == "Rig":
                continue
        elif kind != "transform" or not cmds.listRelatives(
                node, shapes=True, noIntermediate=True, type="nurbsCurve"):
            continue
        if rt.leaf(node).endswith("_extraJoint"):
            continue
        unlocked = []
        for attr in _CHANNELS:
            plug = node + "." + attr
            # Constraint-driven channels are not necessarily settable.
            # Keyable + unlocked is the relevant test, not settable.
            if not cmds.getAttr(plug, lock=True) and cmds.getAttr(plug, keyable=True):
                unlocked.append(plug)
        if unlocked:
            nodes.append(node)
            plugs.extend(unlocked)
    return nodes, plugs


def Run(settings, context):
    data = NormalizeSettings(settings)
    namespace = _namespace(data["namespace_role"], context)
    range_ns = _namespace(data["range_role"], context)
    if not data["range_object"]:
        raise ValueError("Pick an animation object to determine Bake Start / End.")
    range_node = rt.resolve(range_ns, data["range_object"])
    start, end = _range(range_node)
    nodes, plugs = _channels(namespace, data["namespace_role"])
    if not plugs:
        raise ValueError("No animation controls with unlocked keyable TRS in namespace " + namespace)
    print("[Bake] {}: {} animation objects, {} TRS channels, frames {}-{}".format(
        namespace, len(nodes), len(plugs), start, end))
    previous_time = cmds.currentTime(query=True)
    try:
        count = cmds.bakeResults(plugs, animation="objects", hierarchy="none", shape=False,
                                 time=(start, end), simulation=True, sampleBy=1,
                                 minimizeRotation=True, preserveOutsideKeys=True,
                                 sparseAnimCurveBake=False)
    finally:
        cmds.currentTime(previous_time, edit=True)
    result = {"namespace": namespace, "range_object": range_node,
              "start_frame": start, "end_frame": end, "objects": len(nodes),
              "channels": int(count or 0), "requested_channels": len(plugs)}
    context.update({"start_frame": start, "end_frame": end})
    context.setdefault("bake_results", []).append(result)
    # Do not set the legacy 'baked' cleanup flag here: Bake alone does not
    # prove that every source can safely be removed by Save Retarget.
    return result
