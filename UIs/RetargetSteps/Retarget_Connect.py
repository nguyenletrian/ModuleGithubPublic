"""Live segment-length retargeting based on the original NLTA_Mocap.py."""
import math
import re

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Connect"


def PairData(pair):
    return {"from": str(pair.get("from") or "").strip(),
            "to": str(pair.get("to") or "").strip(),
            "translate": bool(pair.get("translate", True)),
            "rotate": bool(pair.get("rotate", True)),
            "scale": False, "mirror": bool(pair.get("mirror", False))}


def DefaultSetting():
    return {"from_role": "Anim", "to_role": "REF",
            "source_root": "", "target_root": "", "maintain_offset": True,
            "pairs": [PairData({})]}


def NormalizeSettings(settings):
    data = dict(DefaultSetting(), **settings)
    data["pairs"] = [PairData(pair) for pair in data["pairs"]]
    return data


def Fields():
    return [("Connect Pairs", "pairs", "constraint_pairs")]


def namespaceForRole(role, context):
    roles = {"Rig": ("new_rig", "target_namespace"),
             "Anim": ("old_animations", "source_namespace_animation"),
             "REF": ("reference_pose", "reference_pose_namespace")}
    key, fallback = roles[role]
    ns = (context.get("reference_namespaces") or {}).get(key) or context.get(fallback)
    if not ns:
        raise ValueError("Connect namespace unavailable: " + role)
    return str(ns).strip(":")


def resolveObject(namespace, name):
    if not str(name or "").strip():
        raise ValueError("Connect: pick an object in " + namespace)
    qualified = namespace + ":" + rt.leaf(name)
    matches = cmds.ls(":" + qualified, long=True, objectsOnly=True) or []
    matches = [node for node in dict.fromkeys(matches)
               if node.split("|")[-1].lstrip(":") == qualified
               and cmds.nodeType(node) in ("joint", "transform")]
    if len(matches) != 1:
        raise ValueError("Connect: expected one transform at " + qualified)
    return matches[0]


def mirrorName(name):
    swaps = {"L": "R", "R": "L", "l": "r", "r": "l",
             "Left": "Right", "Right": "Left", "left": "right", "right": "left",
             "LEFT": "RIGHT", "RIGHT": "LEFT"}
    for pattern in (r"(?<=FBXASC032)[LR](?=FBXASC032)",
                    r"(?<![A-Za-z0-9])(?:Left|Right|left|right|LEFT|RIGHT|L|R|l|r)(?![A-Za-z0-9])",
                    r"^(?:Left|Right)(?=[A-Z0-9])", r"(?:Left|Right)$"):
        result, count = re.subn(pattern, lambda m: swaps[m.group()], name)
        if count:
            return result
    return name


def expandPairs(rows):
    rows = [PairData(row) for row in rows]
    rows = [row for row in rows if (row["from"] or row["to"]) and (row["translate"] or row["rotate"])]
    explicit = {rt.leaf(row["to"]) for row in rows}
    generated = set()
    result = []
    for row in rows:
        if not row["from"] or not row["to"]:
            raise ValueError("Connect: each pair needs both From and To.")
        result.append(row)
        if row["mirror"]:
            source, target = rt.leaf(row["from"]), rt.leaf(row["to"])
            mirrored_source, mirrored_target = mirrorName(source), mirrorName(target)
            if mirrored_target != target and mirrored_target not in explicit | generated:
                if mirrored_source == source:
                    raise ValueError("Connect Mirror needs a side token on From: " + source)
                result.append(dict(row, **{"from": mirrored_source, "to": mirrored_target, "mirror": False}))
                generated.add(mirrored_target)
    return result


def worldPosition(obj):
    return tuple(cmds.xform(obj, query=True, worldSpace=True, translation=True))


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def segmentRatio(source_length, target_length):
    # A coincident source pair has no measurable ratio. Preserve unit motion.
    return target_length / source_length if source_length > 1e-8 else 1.0


def groundAnchor(root, group, name):
    position = list(worldPosition(root))
    position[1] = 0
    anchor = cmds.createNode("transform", name=name, parent=group, skipSelect=True)
    cmds.xform(anchor, worldSpace=True, translation=position)
    return anchor


def translateConnectWithScale(source_parent, source, target_parent, locator, ratio, name):
    # Normalize(direction) * distance is equivalent to the original direction.
    # Multiply the world-space segment directly by its bind length ratio.
    matrices = []
    for obj, suffix in ((source_parent, "SourceParent"), (source, "Source"), (target_parent, "TargetParent")):
        node = cmds.createNode("decomposeMatrix", name=name + "_" + suffix + "_DM")
        cmds.connectAttr(obj + ".worldMatrix[0]", node + ".inputMatrix")
        matrices.append(node + ".outputTranslate")
    direction = cmds.createNode("plusMinusAverage", name=name + "_Direction")
    cmds.setAttr(direction + ".operation", 2)
    cmds.connectAttr(matrices[1], direction + ".input3D[0]")
    cmds.connectAttr(matrices[0], direction + ".input3D[1]")
    scaled = cmds.createNode("multiplyDivide", name=name + "_ScaleSegment")
    cmds.connectAttr(direction + ".output3D", scaled + ".input1")
    cmds.setAttr(scaled + ".input2", ratio, ratio, ratio, type="float3")
    position = cmds.createNode("plusMinusAverage", name=name + "_Position")
    cmds.connectAttr(matrices[2], position + ".input3D[0]")
    cmds.connectAttr(scaled + ".output", position + ".input3D[1]")
    cmds.connectAttr(position + ".output3D", locator + ".translate")
    return [direction, scaled, position] + [plug.split(".")[0] for plug in matrices]


def Run(settings, context):
    data = NormalizeSettings(settings)
    source_ns = namespaceForRole(data["from_role"], context)
    target_ns = namespaceForRole(data["to_role"], context)
    if source_ns == target_ns:
        raise ValueError("Connect requires different source and target namespaces.")
    source_root = resolveObject(source_ns, data["source_root"])
    target_root = resolveObject(target_ns, data["target_root"])
    pairs = []
    targets = set()
    for pair in expandPairs(data["pairs"]):
        source = resolveObject(source_ns, pair["from"])
        target = resolveObject(target_ns, pair["to"])
        if target in targets:
            raise ValueError("Connect: duplicate target " + rt.leaf(target))
        targets.add(target)
        pairs.append((pair, source, target))
    if not pairs:
        return {"pairs": 0, "constraints": 0}

    # Snapshot the lengths before any target is driven.
    mapping = {target: source for _, source, target in pairs}
    source_ground = list(worldPosition(source_root))
    target_ground = list(worldPosition(target_root))
    source_ground[1] = target_ground[1] = 0
    prepared = []
    for pair, source, target in pairs:
        parent = (cmds.listRelatives(target, parent=True, fullPath=True) or [None])[0]
        target_parent = parent if parent in mapping else None
        source_parent = mapping.get(target_parent)
        source_pos = worldPosition(source_parent) if source_parent else source_ground
        target_pos = worldPosition(target_parent) if target_parent else target_ground
        ratio = segmentRatio(distance(source_pos, worldPosition(source)),
                             distance(target_pos, worldPosition(target)))
        translate = pair["translate"] and not any(cmds.getAttr(target + ".translate" + axis, lock=True) for axis in "XYZ")
        rotate_axes = [axis.lower() for axis in "XYZ"
                       if cmds.getAttr(target + ".rotate" + axis, lock=True)]
        rotate = pair["rotate"] and len(rotate_axes) < 3
        prepared.append((source, target, source_parent, target_parent, ratio, translate, rotate, rotate_axes))

    # Helpers live with the source so Clean Scene can remove them after Bake.
    group = cmds.createNode("transform", name=":" + source_ns + ":NLTA_Connect_Group", skipSelect=True)
    cmds.setAttr(group + ".inheritsTransform", False)
    source_anchor = groundAnchor(source_root, group, ":" + source_ns + ":NLTA_SourceRoot")
    target_anchor = groundAnchor(target_root, group, ":" + source_ns + ":NLTA_TargetRoot")
    constraints, locators, records = [], [], []
    for source, target, source_parent, target_parent, ratio, translate, rotate, rotate_axes in sorted(
            prepared, key=lambda entry: entry[1].count("|")):
        name = ":" + source_ns + ":NLTA_" + rt.leaf(target) + "_Connect"
        locator = None
        if translate:
            locator = cmds.spaceLocator(name=name + "_Loc")[0]
            locator = cmds.parent(locator, group, relative=True)[0]
            cmds.matchTransform(locator, target, position=True, rotation=True)
            translateConnectWithScale(source_parent or source_anchor, source,
                                      target_parent or target_anchor, locator, ratio, name)
            constraints.extend(cmds.pointConstraint(locator, target, maintainOffset=data["maintain_offset"],
                                                    name=name + "_Point"))
            locators.append(locator)
        if rotate:
            options = {"maintainOffset": data["maintain_offset"], "name": name + "_Orient"}
            if rotate_axes:
                options["skip"] = rotate_axes
            constraints.extend(cmds.orientConstraint(source, target, **options))
        records.append({"source": source, "target": target, "ratio": ratio,
                        "translate": translate, "rotate": rotate})
        print("[Connect] {} -> {} | ratio={:.6f} T={} R={}".format(source, target, ratio, translate, rotate))
    cmds.setAttr(group + ".visibility", 0)
    result = {"pairs": len(records), "constraints": len(constraints), "group": group,
              "locators": locators, "records": records}
    context.setdefault("mocap_connections", []).append(result)
    return result
