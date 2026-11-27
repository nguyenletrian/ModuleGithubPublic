"""Scale an object by the ratio of two world-space vertex distances."""
import math
import re

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Scale From Object Distance"


def DefaultSetting():
    return {"source_role": "Anim", "vertex1": "", "vertex2": "",
            "target_role": "Rig", "vertex3": "", "vertex4": "",
            "scale_target": {"role": "Rig", "object": "",
                             "attributes": {"X": "", "Y": "", "Z": ""}}}


def Fields():
    return [("Namespace 1", "source_role", "choice", ("Rig", "Anim", "REF")),
            ("Vertex 1", "vertex1", "pick_vertex"),
            ("Vertex 2", "vertex2", "pick_vertex"),
            ("Namespace 2", "target_role", "choice", ("Rig", "Anim", "REF")),
            ("Vertex 3", "vertex3", "pick_vertex"),
            ("Vertex 4", "vertex4", "pick_vertex"),
            ("Apply Scale To", "scale_target", "scale_target")]


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


def vertexPosition(namespace, value):
    match = re.fullmatch(r"(.+)\.vtx\[(\d+)\]", str(value or "").strip())
    if not match:
        raise ValueError("Pick exactly one mesh vertex: mesh.vtx[index].")
    mesh, index = match.groups()
    qualified = namespace + ":" + rt.leaf(mesh)
    matches = cmds.ls(":" + qualified, long=True, objectsOnly=True) or []
    matches = [node for node in dict.fromkeys(matches)
               if node.split("|")[-1].lstrip(":") == qualified
               and cmds.nodeType(node) in ("transform", "mesh")]
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous mesh: " + qualified)
    component = "{}.vtx[{}]".format(matches[0], int(index))
    vertices = cmds.ls(component, long=True, flatten=True) or []
    if len(vertices) != 1:
        raise ValueError("Missing or ambiguous vertex: " + component)
    return tuple(cmds.xform(vertices[0], query=True, worldSpace=True, translation=True))


def Run(settings, context):
    source_ns = _namespace(settings.get("source_role", "Anim"), context)
    target_ns = _namespace(settings.get("target_role", "Rig"), context)
    points = [vertexPosition(namespace, settings.get(key))
              for namespace, key in ((source_ns, "vertex1"), (source_ns, "vertex2"),
                                     (target_ns, "vertex3"), (target_ns, "vertex4"))]
    distance1 = math.dist(points[0], points[1])
    distance2 = math.dist(points[2], points[3])
    if not all(math.isfinite(d) and d > 1e-6 for d in (distance1, distance2)):
        raise ValueError("Both vertex distances must be finite and greater than zero.")
    ratio = distance1 / distance2

    destination = settings.get("scale_target") or {}
    if not isinstance(destination, dict):
        raise ValueError("Scale destination settings are invalid.")
    scale_role = destination.get("role", "Rig")
    scale_ns = _namespace(scale_role, context)
    scale_object = str(destination.get("object") or "").strip()
    if not scale_object:
        raise ValueError("Pick Apply Scale To object before Run.")
    node = rt.resolve(scale_ns, scale_object)

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
        plugs = rt._scale_plugs(node, scale_ns, "")
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


    print("[Scale From Object Distance] Distance 1: {:.6f} | Distance 2: {:.6f} | Ratio: {:.6f}".format(
        distance1, distance2, ratio))
    context.setdefault("alignment", {})["ratio"] = ratio
    return {"distance1": distance1, "distance2": distance2, "ratio": ratio,
            "source_namespace": source_ns, "target_namespace": target_ns,
            "scale_namespace": scale_ns, "scale_object": node, "attributes": plugs}
