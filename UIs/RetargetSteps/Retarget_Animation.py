"""Load a clip from the main form; the Retarget runner selects every clip."""
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Load Animation"


def DefaultSetting():
    return {}


def Fields():
    return []


def Run(settings, context):
    """Confirm the pre-imported clip, or import one for manual card testing."""
    if context.get("animation_loaded"):
        clip = context.get("animation_path")
        if not clip or not context.get("source_namespace_animation"):
            raise ValueError("An imported animation must have a path and namespace.")
        return {"animation_path": clip, "already_loaded": True}

    # Per-module Run can be used without the main batch runner.
    source = context.get("old_animations_path") or settings.get("animation", "")
    files = rt.animation_files(source)
    clip = context.get("animation_path_override") or files[0]
    namespace = (context.get("reference_namespaces") or {}).get(
        "old_animations") or rt.CLIP_NS
    rt.load_asset(clip, namespace, prefer_reference=False)
    context["animation_path"] = clip
    context["source_namespace_animation"] = namespace
    context["animation_loaded"] = True
    if not context.get("reference_pose_loaded"):
        context["source_namespace"] = namespace
    return {"animation_path": clip, "already_loaded": False}
