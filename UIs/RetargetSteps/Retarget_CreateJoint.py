"""Create a joint at an object's live world matrix under a chosen parent."""
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Create Joint"


def JointData(data):
    return {"object_role": data.get("object_role") or "REF",
            "object": str(data.get("object") or ""),
            "parent_role": data.get("parent_role") or "Rig",
            "parent": str(data.get("parent") or ""),
            "name": str(data.get("name") or "")}


def DefaultSetting():
    return {"joint": JointData({})}


def Fields():
    return [("Joint", "joint", "create_joint")]


def _namespace(role, context):
    refs = context.get("reference_namespaces") or {}
    if role == "Rig":
        ns = context.get("target_namespace") or refs.get("new_rig")
    elif role == "Anim":
        ns = (context.get("source_namespace_animation") or
              refs.get("old_animations") or context.get("source_namespace"))
    elif role == "REF":
        if context.get("reference_pose_loaded") is False:
            raise ValueError("Reference Pose has not been imported.")
        ns = context.get("reference_pose_namespace") or refs.get("reference_pose")
    else:
        raise ValueError("Choose Rig, Anim or REF namespace.")
    if not ns:
        raise ValueError("Namespace is not available: " + str(role))
    return str(ns).strip(":")


def Run(settings, context):
    data = JointData(settings.get("joint") or {})
    source = rt.resolve(_namespace(data["object_role"], context), data["object"])
    parent = rt.resolve(_namespace(data["parent_role"], context), data["parent"])
    name = data["name"].strip() or rt.leaf(parent) + "_extraJoint"
    if "|" in name or ":" in name:
        raise ValueError("Create Joint: enter a joint name without DAG path or namespace.")

    # Use the parent's actual namespace, independent of Maya's current namespace.
    parent_name = parent.split("|")[-1]
    namespace = parent_name.rpartition(":")[0]
    qualified = ":" + (namespace + ":" if namespace else "") + name
    matrix = cmds.xform(source, query=True, worldSpace=True, matrix=True)

    # Create directly under the parent to avoid joint reparenting inserting
    # an intermediate transform. Solve the matrix in the final hierarchy.
    joint = cmds.createNode("joint", name=qualified, parent=parent, skipSelect=True)
    joint = (cmds.ls(joint, long=True) or [joint])[0]
    cmds.setAttr(joint + ".segmentScaleCompensate", False)
    cmds.xform(joint, worldSpace=True, matrix=matrix)

    return {"joint": joint, "object": rt.leaf(source),
            "parent": parent}
