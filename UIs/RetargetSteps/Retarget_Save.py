"""Save the prepared (currently unbaked) Retarget scene safely."""
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Save Retarget"


def DefaultSetting():
    return {"keep_sources": False}


def Fields():
    return [
        ("Keep Source Rigs", "keep_sources", "bool"),
    ]


def Run(settings, context):
    if not context.get("batch"):
        raise ValueError("Save Retarget runs only in the confirmed Run Retarget "
                         "workflow; it does not save over your current scene.")
    if not context.get("animation_path"):
        raise ValueError("Import an animation before saving Retarget.")
    # The main form owns the output directory; the old Save.output key
    # remains a fallback for legacy profiles.
    output_dir = str(context.get("output_folder")
                     or settings.get("output", "")).strip()
    if not output_dir:
        raise ValueError("Set Output Folder in General Setting.")
    # An unbaked output must retain the imported animated source and
    # reference pose; otherwise a later Bake step has nothing to sample.
    # Cleanup is permitted only when a future bake stage marks it baked.
    if context.get("baked", False) and not settings.get("keep_sources", False):
        target_ns = context.get("target_namespace", rt.NEW_NS)
        references = context.get("reference_namespaces") or {}
        source_namespaces = (
            rt.CLIP_NS,
            references.get("old_animations")
            or context.get("source_namespace", rt.OLD_NS),
            references.get("reference_pose"))
        for namespace in dict.fromkeys(source_namespaces):
            if namespace and namespace != target_ns:
                rt.drop_namespace(namespace, protected_namespace=target_ns)
    path = rt.unique_output(output_dir, context["animation_path"])
    cmds.file(rename=path)
    cmds.file(save=True, type="mayaAscii", force=True)
    context["output_path"] = path
    return {"output_path": path, "baked": bool(context.get("baked", False))}
