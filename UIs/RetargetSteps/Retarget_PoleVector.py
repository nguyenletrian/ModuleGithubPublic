"""Create a live pole-vector locator from three joint world matrices."""
import math

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Pole Vector"


def DefaultSetting():
    return {"source_role": "Anim", "start": "", "middle": "", "end": "",
            "name": "", "distance_ratio": 0.5}


def Fields():
    return [("Namespace", "source_role", "choice", ("Rig", "Anim", "REF")),
            ("Start Joint", "start", "pick"),
            ("Middle Joint", "middle", "pick"),
            ("End Joint", "end", "pick"),
            ("Locator Name", "name", "text"),
            ("Distance Ratio", "distance_ratio", "float")]


def namespaceForRole(role, context):
    roles = {"Rig": ("new_rig", "target_namespace"),
             "Anim": ("old_animations", "source_namespace_animation"),
             "REF": ("reference_pose", "reference_pose_namespace")}
    key, fallback = roles[role]
    namespace = (context.get("reference_namespaces") or {}).get(key) or context.get(fallback)
    if not namespace:
        raise ValueError("Pole Vector namespace unavailable: " + role)
    return str(namespace).strip(":")


def resolveJoint(namespace, name):
    if not str(name or "").strip():
        raise ValueError("Pick Start, Middle and End joints.")
    qualified = namespace + ":" + rt.leaf(name)
    matches = cmds.ls(":" + qualified, long=True, type="joint") or []
    matches = [node for node in dict.fromkeys(matches)
               if node.split("|")[-1].lstrip(":") == qualified]
    if len(matches) != 1:
        raise ValueError("Pole Vector: expected one joint at " + qualified)
    return matches[0]


def createPoleVector(start, middle, end, name, ratio):
    """Build a live vector projection using the joints' world matrices."""
    created = []

    def node(kind, suffix):
        result = cmds.createNode(kind, name=name + "_" + suffix, skipSelect=True)
        created.append(result)
        return result

    def vector(value, destination):
        if isinstance(value, str):
            cmds.connectAttr(value, destination)
        else:
            cmds.setAttr(destination, *value, type="double3")

    def scalar(value, destination):
        if isinstance(value, str):
            cmds.connectAttr(value, destination)
        else:
            cmds.setAttr(destination, value)

    def position(joint, suffix):
        matrix = node("decomposeMatrix", suffix)
        cmds.connectAttr(joint + ".worldMatrix[0]", matrix + ".inputMatrix")
        return matrix + ".outputTranslate"

    def add(a, b, suffix, subtract=False):
        result = node("plusMinusAverage", suffix)
        cmds.setAttr(result + ".operation", 2 if subtract else 1)
        vector(a, result + ".input3D[0]")
        vector(b, result + ".input3D[1]")
        return result + ".output3D"

    def dot(a, b, suffix):
        result = node("vectorProduct", suffix)
        cmds.setAttr(result + ".operation", 1)
        vector(a, result + ".input1")
        vector(b, result + ".input2")
        return result + ".outputX"

    def scale(value, factor, suffix):
        result = node("multiplyDivide", suffix)
        vector(value, result + ".input1")
        for axis in "XYZ":
            scalar(factor, result + ".input2" + axis)
        return result + ".output"

    def normalized(value, suffix):
        result = node("vectorProduct", suffix)
        cmds.setAttr(result + ".operation", 0)
        cmds.setAttr(result + ".normalizeOutput", True)
        vector(value, result + ".input1")
        return result + ".output"

    def choose(first, second, true_value, false_value, suffix):
        result = node("condition", suffix)
        cmds.setAttr(result + ".operation", 2)
        scalar(first, result + ".firstTerm")
        scalar(second, result + ".secondTerm")
        vector(true_value, result + ".colorIfTrue")
        vector(false_value, result + ".colorIfFalse")
        return result + ".outColor"

    def perpendicular(value, axis, suffix):
        projection = scale(axis, dot(value, axis, suffix + "Dot"), suffix + "Projection")
        return add(value, projection, suffix, subtract=True)

    def worldAxis(local_axis, suffix):
        result = node("vectorProduct", suffix)
        cmds.setAttr(result + ".operation", 3)
        cmds.setAttr(result + ".normalizeOutput", True)
        vector(local_axis, result + ".input1")
        cmds.connectAttr(start + ".worldMatrix[0]", result + ".matrix")
        return result + ".output"

    def distance(a, b, suffix):
        result = node("distanceBetween", suffix)
        cmds.connectAttr(a + ".worldMatrix[0]", result + ".inMatrix1")
        cmds.connectAttr(b + ".worldMatrix[0]", result + ".inMatrix2")
        return result + ".distance"

    a = position(start, "StartMatrix")
    b = position(middle, "MiddleMatrix")
    c = position(end, "EndMatrix")
    chord = add(c, a, "StartEnd", subtract=True)
    arm = add(b, a, "StartMiddle", subtract=True)
    chord_sq = dot(chord, chord, "ChordLengthSquared")
    safe_chord = choose(chord_sq, 1e-12, chord, (1, 0, 0), "SafeChord")
    axis = normalized(safe_chord, "ChainAxis")
    bend = perpendicular(arm, axis, "BendVector")

    # The bend plane is undefined for a straight chain. Choose the more
    # perpendicular of the Start joint's X/Y axes as a deterministic fallback.
    fallback_x = perpendicular(worldAxis((1, 0, 0), "StartX"), axis, "FallbackX")
    fallback_y = perpendicular(worldAxis((0, 1, 0), "StartY"), axis, "FallbackY")
    fallback = choose(dot(fallback_x, fallback_x, "FallbackXLength"),
                      dot(fallback_y, fallback_y, "FallbackYLength"),
                      fallback_x, fallback_y, "FallbackDirection")
    direction = normalized(choose(dot(bend, bend, "BendLengthSquared"), 1e-12,
                                  bend, fallback, "SafeBend"), "PoleDirection")

    total = node("plusMinusAverage", "ChainLength")
    cmds.connectAttr(distance(start, middle, "UpperLength"), total + ".input1D[0]")
    cmds.connectAttr(distance(middle, end, "LowerLength"), total + ".input1D[1]")
    length = node("multDoubleLinear", "PoleDistance")
    cmds.connectAttr(total + ".output1D", length + ".input1")
    cmds.setAttr(length + ".input2", ratio)
    pole_position = add(b, scale(direction, length + ".output", "PoleOffset"), "PolePosition")

    matrix = node("composeMatrix", "PoleMatrix")
    cmds.connectAttr(pole_position, matrix + ".inputTranslate")
    locator = cmds.spaceLocator(name=name)[0]
    locator = cmds.ls(locator, long=True)[0]
    cmds.connectAttr(matrix + ".outputMatrix", locator + ".offsetParentMatrix")
    return locator, created


def Run(settings, context):
    data = dict(DefaultSetting(), **settings)
    namespace = namespaceForRole(data["source_role"], context)
    joints = [resolveJoint(namespace, data[key]) for key in ("start", "middle", "end")]
    if len(set(joints)) != 3:
        raise ValueError("Pole Vector needs three different joints.")
    ratio = float(data["distance_ratio"])
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("Pole Vector Distance Ratio must be greater than zero.")
    name = str(data["name"] or "").strip() or rt.leaf(joints[1]) + "_PoleVector"
    if any(character in name for character in "|:. "):
        raise ValueError("Enter a locator name without namespace or DAG path.")
    qualified = ":" + namespace + ":" + name
    if cmds.objExists(qualified):
        raise ValueError("Pole Vector already exists: " + qualified)
    locator, nodes = createPoleVector(*joints, qualified, ratio)
    result = {"locator": locator, "joints": joints, "nodes": nodes,
              "distance_ratio": ratio}
    context.setdefault("pole_vectors", []).append(result)
    return result
