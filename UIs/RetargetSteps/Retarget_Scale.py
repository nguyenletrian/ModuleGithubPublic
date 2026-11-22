"""Match scale from Scale Ref and Scale Object Lowest/Highest distances.

Each side independently chooses New Rig, Animation or Reference Pose.
A separate scale destination picks one object and maps X/Y/Z scale attributes.
"""
import math

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Match Scale"


def DefaultSetting():
    return {
        "source_role": "Anim",
        "old_low": "",
        "old_high": "",
        "target_role": "Rig",
        "new_low": "",
        "new_high": "",
        "scale_target": {
            "role": "Rig", "object": "",
            "attributes": {"X": "", "Y": "", "Z": ""},
        },
        # Retain the old field for profiles created with Set Scale.
        "scale_attribute": "",
        "legacy_root_scale": False,
    }


def Fields():
    return [
        ("Scale Ref Namespace", "source_role", "choice",
         ("Rig", "Anim", "REF")),
        ("Scale Ref Lowest", "old_low", "pick_ref"),
        ("Scale Ref Highest", "old_high", "pick_ref"),
        ("Scale Object Namespace", "target_role", "choice",
         ("Rig", "Anim", "REF")),
        ("Scale Object Lowest", "new_low", "pick_ref"),
        ("Scale Object Highest", "new_high", "pick_ref"),
        ("Apply Scale To", "scale_target", "scale_target"),
    ]


def _namespace(role, context):
    role = str(role or "").strip()
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
        raise ValueError("Namespace role must be Rig, Anim or REF.")
    if not namespace:
        raise ValueError("{} namespace is not configured.".format(role))
    return str(namespace).strip(":")


def Run(settings, context):
    source_role = settings.get("source_role", "Anim")
    target_role = settings.get("target_role", "Rig")
    # Previous Set Scale used the bind/source namespace automatically.
    source_ns = (_namespace(source_role, context)
                 if "source_role" in settings else
                 context.get("source_namespace") or _namespace("Anim", context))
    target_ns = _namespace(target_role, context)
    def reference_point(namespace, value):
        """Accept a transform/joint pivot or a single mesh vertex position."""
        name = str(value or "").strip()
        if ".vtx[" not in name:
            return rt.position(rt.resolve(namespace, name))
        mesh, suffix = name.rsplit(".vtx[", 1)
        if not mesh or not suffix.endswith("]") or not suffix[:-1].isdigit():
            raise ValueError("Pick one vertex, such as mesh.vtx[123].")
        mesh_node = rt.resolve(namespace, mesh)
        component = "{}.vtx[{}]".format(mesh_node, int(suffix[:-1]))
        matches = cmds.ls(component, long=True, flatten=True) or []
        if len(matches) != 1:
            raise ValueError("Match Scale vertex missing: " + component)
        return tuple(cmds.xform(
            matches[0], query=True, worldSpace=True, translation=True))

    source_low = reference_point(source_ns, settings.get("old_low", ""))
    source_high = reference_point(source_ns, settings.get("old_high", ""))
    target_low = reference_point(target_ns, settings.get("new_low", ""))
    target_high = reference_point(target_ns, settings.get("new_high", ""))
    source_span = rt._length(rt._vec(source_low, source_high))
    target_span = rt._length(rt._vec(target_low, target_high))
    if not math.isfinite(source_span) or not math.isfinite(target_span):
        raise ValueError("Reference distances must be finite.")
    if min(source_span, target_span) <= 1e-6:
        raise ValueError("Lowest and Highest must be different positions.")
    ratio = source_span / target_span

    destination = settings.get("scale_target") or {}
    if not isinstance(destination, dict):
        raise ValueError("Scale destination settings are invalid.")
    scale_role = destination.get("role", "Rig")
    scale_ns = _namespace(scale_role, context)
    scale_object = str(destination.get("object") or "").strip()
    if scale_object:
        node = rt.resolve(scale_ns, scale_object)
    else:
        # Older Set Scale profiles used the automatically detected root.
        if ("scale_target" in settings
                and not settings.get("legacy_root_scale")):
            raise ValueError("Pick Scale Destination object before Run.")
        node = context.get("target_root")
        scale_ns = context.get("target_namespace", scale_ns)
        if not node:
            raise ValueError("Pick Scale Destination object before Run.")

    axis_attributes = destination.get("attributes")
    if isinstance(axis_attributes, dict):
        # A single GlobalScale-type attribute often drives all three axes.
        # When any channel is explicitly selected, blank fields mean no
        # additional channel; only three completely blank fields fall back
        # to native scaleX/Y/Z.
        attrs = {axis: str(axis_attributes.get(axis) or "").strip()
                 for axis in "XYZ"}
        has_explicit = any(value not in ("", "-")
                           for value in attrs.values())
        requested = [
            (axis, attrs[axis] if attrs[axis] else
             ("" if has_explicit else "scale" + axis))
            for axis in "XYZ"
        ]
        plugs = []
        seen = set()
        for axis, attr in requested:
            if not attr or attr == "-":
                continue
            if "." in attr:
                raise ValueError(
                    "Scale {} Attribute must be a channel name.".format(axis))
            for plug in rt._scale_plugs(node, scale_ns, attr):
                if plug not in seen:
                    plugs.append(plug)
                    seen.add(plug)
        if not plugs:
            raise ValueError("Pick at least one scale attribute.")
    elif destination.get("attribute"):
        # Read a previously saved Match Scale with one custom attribute.
        plugs = rt._scale_plugs(
            node, scale_ns, str(destination["attribute"]).strip())
    else:
        # Unmigrated Set Scale: a single custom attribute or scale XYZ.
        plugs = rt._scale_plugs(
            node, scale_ns, settings.get("scale_attribute", ""))
    changes = []
    for plug in plugs:
        if not cmds.getAttr(plug, settable=True):
            raise ValueError("Scale attribute is locked or connected: " + plug)
        current = cmds.getAttr(plug)
        if not isinstance(current, (int, float)) or not math.isfinite(current):
            raise ValueError("Scale attribute must be a finite scalar: " + plug)
        changes.append((plug, float(current) * ratio))
    for plug, number in changes:
        cmds.setAttr(plug, number)

    context.setdefault("alignment", {})["ratio"] = ratio
    return {
        "ratio": ratio,
        "source_namespace": source_ns,
        "target_namespace": target_ns,
        "scale_namespace": scale_ns,
        "scale_object": node,
        "attributes": plugs,
    }
