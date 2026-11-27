"""Copy current attribute values between two objects with independent namespaces."""
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Copy Attribute"


def DefaultSetting():
    return {"source_role": "Rig", "target_role": "Rig", "from": "", "to": "", "attributes": [""]}


def NormalizeSettings(settings):
    data = dict(DefaultSetting(), **settings)
    if "target_role" not in settings:
        data["target_role"] = data["source_role"]
    return data


def Fields():
    return [("Namespace From", "source_role", "choice", ("Rig", "Anim", "REF")),
            ("Object From", "from", "copy_object"),
            ("Namespace To", "target_role", "choice", ("Rig", "Anim", "REF")),
            ("Object To", "to", "copy_object"),
            ("Attributes", "attributes", "copy_attributes")]


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


def Run(settings, context):
    data = NormalizeSettings(settings)
    source = rt.resolve(_namespace(data["source_role"], context), data["from"])
    target = rt.resolve(_namespace(data["target_role"], context), data["to"])
    attributes = list(dict.fromkeys(str(name).strip() for name in data["attributes"]
                                    if str(name).strip()))
    if not attributes:
        raise ValueError("Copy Attribute needs at least one attribute.")
    scalars = ("bool", "enum", "byte", "char", "short", "long", "longLong",
               "double", "float", "doubleLinear", "doubleAngle", "time")
    vectors = ("double2", "float2", "long2", "short2",
               "double3", "float3", "long3", "short3")
    changes = []
    for attribute in attributes:
        if "." in attribute or "[" in attribute or "]" in attribute:
            raise ValueError("Enter an attribute name, not a plug: " + attribute)
        src = source + "." + attribute
        dst = target + "." + attribute
        if not cmds.objExists(src) or not cmds.objExists(dst):
            raise ValueError("Copy Attribute requires existing channels: {} -> {}".format(src, dst))
        if not cmds.getAttr(dst, settable=True):
            raise ValueError("Copy Attribute destination locked or connected: " + dst)
        kind = cmds.getAttr(src, type=True)
        target_kind = cmds.getAttr(dst, type=True)
        if kind != target_kind:
            raise ValueError("Copy Attribute type mismatch: {} ({}) -> {} ({})".format(
                src, kind, dst, target_kind))
        if kind not in scalars + vectors + ("string",):
            raise ValueError("Unsupported Copy Attribute type: " + kind)
        value = cmds.getAttr(src)
        if kind in vectors:
            value = tuple(value[0])
        changes.append((dst, kind, value))

    for dst, kind, value in changes:
        if kind == "string":
            cmds.setAttr(dst, value or "", type="string")
        elif kind in vectors:
            cmds.setAttr(dst, *value, type=kind)
        else:
            cmds.setAttr(dst, value)
    return {"from": source, "to": target, "attributes": attributes,
            "changed": len(changes)}
