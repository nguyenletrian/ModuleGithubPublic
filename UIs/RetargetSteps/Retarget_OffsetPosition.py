"""Align a point in Affect hierarchy to a point in Ref hierarchy.

Reference points may be DAG pivots, mesh vertices/edges/faces or NURBS CVs.
Only Affect Root is translated, in world space; no constraints are created.
"""
import math
import re

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Offset Position"


def DefaultSetting():
    return {
        "ref_role": "REF",
        "ref_root": "",
        "ref_object": "",
        "affect_role": "Rig",
        "affect_root": "",
        "affect_object": "",
    }


def Fields():
    return [
        ("Ref Namespace", "ref_role", "choice", ("Rig", "Anim", "REF")),
        ("Ref Root", "ref_root", "pick"),
        ("Ref Obj", "ref_object", "pick_element"),
        ("Affect Namespace", "affect_role", "choice", ("Rig", "Anim", "REF")),
        ("Affect Root", "affect_root", "pick"),
        ("Affect Obj", "affect_object", "pick_element"),
    ]


def _namespace(role, context):
    refs = context.get("reference_namespaces") or {}
    if role == "Rig":
        value = context.get("target_namespace") or refs.get("new_rig")
    elif role == "Anim":
        value = (context.get("source_namespace_animation")
                 or refs.get("old_animations")
                 or context.get("source_namespace"))
    elif role == "REF":
        if context.get("reference_pose_loaded") is False:
            raise ValueError("Reference Pose has not been imported.")
        value = context.get("reference_pose_namespace") or refs.get(
            "reference_pose")
    else:
        raise ValueError("Choose Rig, Anim or REF namespace.")
    if not value:
        raise ValueError("{} namespace is not available.".format(role))
    return str(value).strip(":")


_COMPONENT = re.compile(
    r"^(?P<node>.+)\.(?P<kind>vtx|e|f|cv|ep)"
    r"(?P<indices>(?:\[\d+\]){1,2})$")


def _point(namespace, name):
    """Measure one object or component in world coordinates.

    Edge = midpoint of its two vertices. Face = mean position of all
    face vertices. Each is one stable, JSON-friendly component reference.
    """
    value = str(name or "").strip()
    if not value:
        raise ValueError("Pick Ref Obj and Affect Obj before Run.")

    match = _COMPONENT.fullmatch(value)
    if match is None:
        if "." in value:
            raise ValueError(
                "Use a transform/joint or one vertex, edge, face, CV "
                "or curve edit point: " + value)
        return tuple(rt.position(rt.resolve(namespace, value)))

    kind = match.group("kind")
    indices = match.group("indices")
    if kind in ("vtx", "e", "f", "ep") and indices.count("[") != 1:
        raise ValueError("Select one {} element: {}".format(kind, value))
    node = rt.resolve(namespace, match.group("node"))
    component = "{}.{}{}".format(node, kind, indices)
    selected = cmds.ls(component, long=True, flatten=True) or []
    if len(selected) != 1:
        raise ValueError("Element is missing or ambiguous: " + component)

    if kind in ("e", "f"):
        # Maya returns a range for some face/edge conversions. Flatten and
        # deduplicate to measure the actual polygon corner positions.
        conversion = {"toVertex": True}
        conversion["fromEdge" if kind == "e" else "fromFace"] = True
        vertices = cmds.polyListComponentConversion(
            selected[0], **conversion) or []
        components = list(dict.fromkeys(
            cmds.ls(vertices, long=True, flatten=True) or []))
        minimum = 2 if kind == "e" else 3
        if len(components) < minimum:
            raise ValueError(
                "Cannot find the {} vertices of {}".format(kind, component))
    else:
        components = selected

    positions = []
    for element in components:
        xyz = cmds.xform(
            element, query=True, worldSpace=True, translation=True)
        if not xyz or len(xyz) != 3:
            raise ValueError("Cannot read world position: " + element)
        xyz = tuple(float(x) for x in xyz)
        if not all(math.isfinite(x) for x in xyz):
            raise ValueError("Invalid element position: " + element)
        positions.append(xyz)

    size = float(len(positions))
    return tuple(sum(p[i] for p in positions) / size for i in range(3))


def _finite_position(values, label):
    if len(values) != 3 or not all(math.isfinite(float(x)) for x in values):
        raise ValueError("{} has an invalid world-space position.".format(label))
    return tuple(float(x) for x in values)


def Run(settings, context):
    ref_ns = _namespace(settings.get("ref_role", "REF"), context)
    affect_ns = _namespace(settings.get("affect_role", "Rig"), context)
    ref_root = rt.resolve(ref_ns, settings.get("ref_root", ""))
    affect_root = rt.resolve(affect_ns, settings.get("affect_root", ""))

    for root, label in ((ref_root, "Ref Root"), (affect_root, "Affect Root")):
        if cmds.nodeType(root) not in ("transform", "joint"):
            raise ValueError("{} must be a transform or joint.".format(label))

    ref_origin = _finite_position(rt.position(ref_root), "Ref Root")
    affect_origin = _finite_position(rt.position(affect_root), "Affect Root")
    ref_point = _finite_position(
        _point(ref_ns, settings.get("ref_object", "")), "Ref Obj")
    affect_point = _finite_position(
        _point(affect_ns, settings.get("affect_object", "")), "Affect Obj")

    # These offsets are relative to their respective roots. The required
    # world displacement reduces to Ref Obj world - Affect Obj world.
    ref_offset = [p - root for p, root in zip(ref_point, ref_origin)]
    affect_offset = [
        p - root for p, root in zip(affect_point, affect_origin)]
    intended_root_pivot = [
        root + ref_delta - affect_delta
        for root, ref_delta, affect_delta in zip(
            ref_origin, ref_offset, affect_offset)]
    delta = [
        destination - current
        for destination, current in zip(intended_root_pivot, affect_origin)]

    if any(abs(value) > 1e-10 for value in delta):
        # Validate before moving: constraints/locks must not cause a partial
        # update across different translate axes.
        for axis, component in zip("XYZ", delta):
            if abs(component) > 1e-10 and not cmds.getAttr(
                    affect_root + ".translate" + axis, settable=True):
                raise ValueError(
                    "Affect Root translation is locked/connected on "
                    + axis + ": " + affect_root)
        # Apply in world coordinates, accounting for rotated/scaled parents.
        root_translate = _finite_position(
            cmds.xform(affect_root, query=True, worldSpace=True,
                       translation=True), "Affect Root translate")
        new_translate = [
            current + offset
            for current, offset in zip(root_translate, delta)]
        cmds.xform(
            affect_root, worldSpace=True, translation=new_translate)

    return {
        "ref_namespace": ref_ns,
        "affect_namespace": affect_ns,
        "ref_root": ref_root,
        "affect_root": affect_root,
        "ref_position": list(ref_point),
        "affect_position_before": list(affect_point),
        "world_delta": delta,
    }
