"""Match selected transforms to a source world matrix in explicit Pair order."""
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Match Transform"


def PairData(pair):
    return {"from_role": pair.get("from_role") or "REF",
            "from": str(pair.get("from") or ""),
            "to_role": pair.get("to_role") or "Rig",
            "to": str(pair.get("to") or "")}


def DefaultSetting():
    return {"pairs": [PairData({})]}


def Fields():
    return [("Transform Pairs", "pairs", "match_rotate_pairs")]


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
    pairs = settings.get("pairs") or []
    if not pairs:
        raise ValueError("Match Transform: add at least one From / To pair.")
    resolved = []
    for raw in pairs:
        pair = PairData(raw)
        source = rt.resolve(_namespace(pair["from_role"], context), pair["from"])
        target = rt.resolve(_namespace(pair["to_role"], context), pair["to"])
        if source == target:
            continue
        resolved.append((source, target))

    # Read the current world matrix immediately before each write. Respect
    # the UI order, including dependencies across separate DAG branches.
    for source, target in resolved:
        matrix = cmds.xform(source, query=True, worldSpace=True, matrix=True)
        cmds.xform(target, worldSpace=True, matrix=matrix)
        print("[Match Transform] {} -> {}".format(rt.leaf(source), rt.leaf(target)))

    if resolved and context.get("pairs") and context.get("bind"):
        context["bind"] = rt.capture_bind(context["pairs"], context["source_namespace"],
                                          context["target_namespace"])
    return {"matched": len(resolved)}
