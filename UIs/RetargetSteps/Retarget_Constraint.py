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
    return {"from_role": "REF", "to_role": "Rig", "pairs": [PairData({})]}


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
            "pairs": [PairData(row) for row in rows]}


def Fields():
    return [("Constraint Pairs", "pairs", "constraint_pairs")]


def _namespaces(context):
    refs = context.get("reference_namespaces") or {}
    ref = context.get("reference_pose_namespace") or refs.get("reference_pose")
    anim = context.get("source_namespace_animation") or refs.get("old_animations")
    rig = context.get("target_namespace") or refs.get("new_rig")
    if context.get("reference_pose_loaded") is False or not ref:
        raise ValueError("Constraint requires a Reference Pose.")
    if not anim or not rig:
        raise ValueError("Constraint requires the Animation and Rig namespaces.")
    ref, anim, rig = (str(ns).strip(":") for ns in (ref, anim, rig))
    if len({ref, anim, rig}) != 3:
        raise ValueError("Constraint requires separate REF, Anim and Rig namespaces.")
    return ref, anim, rig


def _world(node):
    return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))


def _offset(ref, target):
    return list(_world(target) * _world(ref).inverse())


def _build_extra(anim, target, matrix):
    namespace = anim.split("|")[-1].rpartition(":")[0]
    name = ":" + (namespace + ":" if namespace else "") + rt.leaf(target) + "_extraJoint"
    joint = cmds.createNode("joint", name=name, parent=anim, skipSelect=True)
    joint = anim + "|" + joint.split("|")[-1] if not joint.startswith("|") else joint
    # A fresh joint has identity local TRS and jointOrient. Store the entire
    # bind offset without Euler decomposition or joint scale compensation.
    cmds.setAttr(joint + ".segmentScaleCompensate", False)
    cmds.setAttr(joint + ".offsetParentMatrix", *matrix, type="matrix")
    return joint


def _connect(extra, target, pair):
    nodes = []
    if pair["translate"] and pair["rotate"]:
        nodes.extend(cmds.parentConstraint(extra, target, maintainOffset=False))
    elif pair["translate"]:
        nodes.extend(cmds.pointConstraint(extra, target, maintainOffset=False))
    elif pair["rotate"]:
        nodes.extend(cmds.orientConstraint(extra, target, maintainOffset=False))
    if pair["scale"]:
        nodes.extend(cmds.scaleConstraint(extra, target, maintainOffset=False))
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
    ref_ns, anim_ns, rig_ns = _namespaces(context)
    from_role = settings.get("from_role", "REF")
    to_role = settings.get("to_role", "Rig")
    if from_role not in ("REF", "Anim") or to_role != "Rig":
        raise ValueError("Constraint From must be REF or Anim, and To must be Rig.")
    pending = []
    targets = set()
    existing = {entry["target"] for entry in context.get("constraint_pairs", [])
                if any(cmds.objExists(node) for node in entry["constraints"])}
    for pair in _expand_pairs(settings.get("pairs", [])):
        if from_role == "REF":
            ref = rt.resolve(ref_ns, pair["from"])
            anim = rt.resolve(anim_ns, rt.leaf(ref))
        else:
            anim = rt.resolve(anim_ns, pair["from"])
            ref = rt.resolve(ref_ns, rt.leaf(anim))
        target = rt.resolve(rig_ns, pair["to"])
        if target in targets or target in existing:
            raise ValueError("Constraint already configured for: " + target)
        targets.add(target)
        pending.append((pair, anim, target, _offset(ref, target)))

    # Capture every REF/rig offset before any control receives a constraint.
    # The animation can be at any frame when the helpers are created.
    entries = []
    for pair, anim, target, offset in pending:
        extra = _build_extra(anim, target, offset)
        constraints = _connect(extra, target, pair)
        entries.append({"source": anim, "target": target, "extra_joint": extra,
                        "constraints": constraints,
                        "translate": pair["translate"], "rotate": pair["rotate"],
                        "scale": pair["scale"]})
    context.setdefault("constraint_pairs", []).extend(entries)
    if entries:
        context["baked"] = False
    return {"pairs": len(entries), "joints": [entry["extra_joint"] for entry in entries],
            "constraints": sum(len(entry["constraints"]) for entry in entries)}
