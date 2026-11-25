"""Remove only the explicitly selected Retarget namespaces from the scene."""
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Clean"


def DefaultSetting():
    return {"rig": False, "anim": False, "ref": False}


def Fields():
    return [("Namespaces", "namespaces", "clean_namespaces")]


def Run(settings, context):
    references = context.get("reference_namespaces") or {}
    roles = (("rig", "new_rig", "target_namespace"),
             ("anim", "old_animations", "source_namespace_animation"),
             ("ref", "reference_pose", "reference_pose_namespace"))
    selected = []
    for flag, key, fallback in roles:
        if not settings.get(flag, False):
            continue
        namespace = str(references.get(key) or context.get(fallback) or "").strip(":")
        if not namespace or namespace in ("UI", "shared"):
            raise ValueError("Clean: invalid namespace for " + flag)
        selected.append((flag, namespace))

    removed, missing = [], []
    if selected:
        cmds.namespace(setNamespace=":")
    for flag, namespace in selected:
        if not cmds.namespace(exists=namespace):
            missing.append(namespace)
            continue
        # Rig is protected by default in the shared helper. Here its removal
        # is intentional only when the user explicitly checks Rig.
        rt.drop_namespace(namespace, protected_namespace=None)
        removed.append(namespace)
        print("[Clean] Removed namespace: " + namespace)
    context.setdefault("cleaned_namespaces", []).extend(removed)
    return {"removed": removed, "missing": missing}
