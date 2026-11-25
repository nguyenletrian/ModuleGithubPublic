"""Build live retarget constraints using a bind-pose-aligned extra joint."""
import maya.cmds as cmds
import maya.api.OpenMaya as om
import NLTA_RetargetV2 as rt

LABEL = "Constraint"


def PairData(pair):
    return {"from": str(pair.get("from") or ""),
            "to": str(pair.get("to") or ""),
            "translate": bool(pair.get("translate", False)),
            "rotate": bool(pair.get("rotate", True)),
            "scale": bool(pair.get("scale", False))}


def DefaultSetting():
    return {"from_role": "REF", "to_role": "Rig", "pairs": [PairData({})]}


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


def Run(settings, context):
    ref_ns, anim_ns, rig_ns = _namespaces(context)
    from_role = settings.get("from_role", "REF")
    to_role = settings.get("to_role", "Rig")
    if from_role not in ("REF", "Anim") or to_role != "Rig":
        raise ValueError("Constraint From must be REF or Anim, and To must be Rig.")
    pending = []
    targets = set()
    existing = {entry["target"] for entry in context.get("constraint_pairs", [])
                if any(cmds.objExists(node) for node in entry["constraints"])}
    for raw in settings.get("pairs", []):
        pair = PairData(raw)
        if not any(pair[key] for key in ("translate", "rotate", "scale")):
            continue
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
