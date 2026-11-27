"""Create a joint from a captured world matrix under a chosen parent."""
import math
import re
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Create Joint"


def JointData(data):
    return {"matrix": list(data.get("matrix") or []),
            "parent_role": data.get("parent_role") or "Rig",
            "parent": str(data.get("parent") or ""),
            "name": str(data.get("name") or ""),
            "mirror": bool(data.get("mirror", False))}


def DefaultSetting():
    return {"items": [JointData({})]}


def NormalizeSettings(settings):
    items = settings.get("items")
    if items is None:
        items = [settings.get("joint") or {}]
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Create Joint items must be a list of objects.")
    return {"items": [JointData(item) for item in items]}


def Fields():
    return [("Joints", "items", "create_joint_items")]


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


def mirrorName(name):
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

def mirrorMatrix(matrix):
    # Maya row-vector matrices: reflect world X and local X (S * M * S).
    signs = (-1, 1, 1, 1)
    return [matrix[row * 4 + column] * signs[row] * signs[column]
            for row in range(4) for column in range(4)]


def prepareJoint(data, context):
    matrix = data["matrix"]
    if len(matrix) != 16 or not all(isinstance(value, (int, float)) and
                                    math.isfinite(value) for value in matrix):
        raise ValueError("Create Joint: Pick Matrix first (16 finite values).")
    parent = rt.resolve(_namespace(data["parent_role"], context), data["parent"])
    name = data["name"].strip() or rt.leaf(parent) + "_extraJoint"
    if "|" in name or ":" in name:
        raise ValueError("Create Joint: enter a joint name without DAG path or namespace.")

    # Use the parent's actual namespace, independent of Maya's current namespace.
    parent_name = parent.split("|")[-1]
    namespace = parent_name.rpartition(":")[0]
    qualified = ":" + (namespace + ":" if namespace else "") + name

    return parent, qualified, matrix


def createJoint(parent, qualified, matrix):
    # Create directly under the parent to avoid joint reparenting inserting
    # an intermediate transform. Solve the matrix in the final hierarchy.
    joint = cmds.createNode("joint", name=qualified, parent=parent, skipSelect=True)
    joint = (cmds.ls(joint, long=True) or [joint])[0]
    cmds.setAttr(joint + ".segmentScaleCompensate", False)
    cmds.xform(joint, worldSpace=True, matrix=matrix)

    return {"joint": joint, "parent": parent}


def Run(settings, context):
    planned = []
    for data in NormalizeSettings(settings)["items"]:
        original = prepareJoint(data, context)
        planned.append(original)
        if data["mirror"]:
            parentName = rt.leaf(original[0])
            opposite = mirrorName(parentName)
            if opposite == parentName:
                raise ValueError("Create Joint Mirror: Parent needs a side token: " + parentName)
            name = data["name"].strip()
            oppositeName = mirrorName(name)
            if name and oppositeName == name:
                raise ValueError("Create Joint Mirror: Name needs a side token: " + name)
            mirrored = dict(data, parent=opposite, name=oppositeName, matrix=mirrorMatrix(data["matrix"]), mirror=False)
            planned.append(prepareJoint(mirrored, context))
    names = set()
    for parent, qualified, matrix in planned:
        key = (parent, qualified)
        if key in names:
            raise ValueError("Create Joint: repeated planned joint: " + qualified)
        names.add(key)
    results = [createJoint(parent, qualified, matrix) for parent, qualified, matrix in planned]
    if len(results) == 1:
        return results[0]
    return {"items": results, "joints": [item["joint"] for item in results]}
