"""Build live retarget constraints using a bind-pose-aligned extra joint."""
import re
import maya.cmds as cmds
import maya.api.OpenMaya as om
import NLTA_RetargetV2 as rt

LABEL = "Constraint"


def PairData(pair):
    return {"from": str(pair.get("from") or ""),
            "to": str(pair.get("to") or ""),
            "translate": bool(pair.get("translate", False)),
            "rotate": bool(pair.get("rotate", True)),
            "scale": bool(pair.get("scale", False)),
            "mirror": bool(pair.get("mirror", False))}


def DefaultSetting():
    return {"from_role": "REF", "to_role": "Rig", "maintain_offset": True,
            "pairs": [PairData({})]}


def NormalizeSettings(settings):
    # Older UI accidentally stored the edited Pair list in to_role,
    # leaving pairs stale. Recover the latest edited list, including [].
    rows = settings.get("to_role")
    if not isinstance(rows, list):
        rows = settings.get("pairs", [PairData({})])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid Constraint Pair data.")
    role = settings.get("from_role", "REF")
    if role not in ("REF", "Anim"):
        raise ValueError("Invalid Constraint From namespace.")
    return {"from_role": role, "to_role": "Rig",
            "maintain_offset": bool(settings.get("maintain_offset", True)),
            "pairs": [PairData(row) for row in rows]}


def Fields():
    return [("Constraint Pairs", "pairs", "constraint_pairs")]


def _namespaces(context, from_role="REF"):
    refs = context.get("reference_namespaces") or {}
    # Resolve the selected driver only. REF -> Rig never needs Animation.
    if from_role == "REF":
        source = refs.get("reference_pose") or context.get("reference_pose_namespace")
        if context.get("reference_pose_loaded") is False:
            raise ValueError("Constraint requires a Reference Pose.")
    elif from_role == "Anim":
        source = refs.get("old_animations") or context.get("source_namespace_animation")
    else:
        raise ValueError("Invalid Constraint From namespace.")
    rig = refs.get("new_rig") or context.get("target_namespace")
    if not source or not rig:
        raise ValueError("Constraint requires the selected From and Rig namespaces.")
    source, rig = (str(ns).strip(":") for ns in (source, rig))
    if source == rig:
        raise ValueError("Constraint From and To must use different namespaces.")
    return source, rig


def _resolve(namespace, name):
    leaf = rt.leaf(name)
    if not leaf:
        raise ValueError("Constraint requires an object name in " + namespace)
    # Absolute namespace lookup avoids Maya's current namespace and any
    # stale aliases or similarly named objects in REF / Anim / Rig.
    qualified = ":" + namespace + ":" + leaf
    matches = cmds.ls(qualified, long=True, objectsOnly=True) or []
    matches = [node for node in dict.fromkeys(matches)
               if node.split("|")[-1].lstrip(":") == qualified.lstrip(":")
               and cmds.nodeType(node) in ("joint", "transform")]
    if len(matches) != 1:
        raise ValueError("Constraint: expected one object at {}, found {}".format(
            qualified, len(matches)))
    return matches[0]


def _world(node):
    return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))


def _offset(source, target):
    return list(_world(target) * _world(source).inverse())


def _build_extra(source, target, matrix):
    namespace = source.split("|")[-1].rpartition(":")[0]
    name = ":" + (namespace + ":" if namespace else "") + rt.leaf(target) + "_extraJoint"
    joint = cmds.createNode("joint", name=name, parent=source, skipSelect=True)
    joint = source + "|" + joint.split("|")[-1] if not joint.startswith("|") else joint
    # A fresh joint has identity local TRS and jointOrient. Store the entire
    # bind offset without Euler decomposition or joint scale compensation.
    cmds.setAttr(joint + ".segmentScaleCompensate", False)
    cmds.setAttr(joint + ".offsetParentMatrix", *matrix, type="matrix")
    return joint


def _connect(extra, target, pair, maintain_offset=True):
    nodes = []
    if pair["translate"] and pair["rotate"]:
        nodes.extend(cmds.parentConstraint(extra, target, maintainOffset=maintain_offset))
    elif pair["translate"]:
        nodes.extend(cmds.pointConstraint(extra, target, maintainOffset=maintain_offset))
    elif pair["rotate"]:
        nodes.extend(cmds.orientConstraint(extra, target, maintainOffset=maintain_offset))
    if pair["scale"]:
        nodes.extend(cmds.scaleConstraint(extra, target, maintainOffset=maintain_offset))
    return nodes


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

def _expand_pairs(rows):
    pairs = [PairData(row) for row in rows]
    pairs = [pair for pair in pairs
             if any(pair[key] for key in ("translate", "rotate", "scale"))]
    explicit = {rt.leaf(pair["to"]) for pair in pairs}
    generated = set()
    result = []
    for pair in pairs:
        result.append(pair)
        if not pair["mirror"]:
            continue
        target = rt.leaf(pair["to"])
        opposite = _mirror_name(target)
        if opposite == target or opposite in explicit or opposite in generated:
            continue
        source = rt.leaf(pair["from"])
        mirrored_source = _mirror_name(source)
        if mirrored_source == source:
            raise ValueError("Constraint Mirror needs a side token on From: " + source)
        result.append(dict(pair, **{"from": mirrored_source, "to": opposite, "mirror": False}))
        generated.add(opposite)
    return result


def Run(settings, context):
    settings = NormalizeSettings(settings)
    from_role = settings["from_role"]
    source_ns, rig_ns = _namespaces(context, from_role)
    pending = []
    targets = set()
    existing = {entry["target"] for entry in context.get("constraint_pairs", [])
                if any(cmds.objExists(node) for node in entry["constraints"])}
    for pair in _expand_pairs(settings.get("pairs", [])):
        source = _resolve(source_ns, pair["from"])
        target = _resolve(rig_ns, pair["to"])
        if target in targets or target in existing:
            raise ValueError("Constraint already configured for: " + target)
        targets.add(target)
        pending.append((pair, source, target, _offset(source, target)))

    # Capture all source/rig offsets before any control receives a constraint.
    entries = []
    print("[Constraint] From {}={} -> Rig={}".format(from_role, source_ns, rig_ns))
    for pair, source, target, offset in pending:
        extra = _build_extra(source, target, offset)
        print("[Constraint] Source parent: {} | Driver: {} | Driven: {}".format(
            source, extra, target))
        constraints = _connect(extra, target, pair, settings["maintain_offset"])
        entries.append({"reference": source if from_role == "REF" else None,
                        "source_role": from_role, "source": source,
                        "target": target, "extra_joint": extra,
                        "constraints": constraints,
                        "translate": pair["translate"], "rotate": pair["rotate"],
                        "scale": pair["scale"]})
    context.setdefault("constraint_pairs", []).extend(entries)
    if entries:
        context["baked"] = False
    return {"pairs": len(entries), "joints": [entry["extra_joint"] for entry in entries],
            "constraints": sum(len(entry["constraints"]) for entry in entries)}
