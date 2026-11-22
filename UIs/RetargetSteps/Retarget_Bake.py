"""Bake the mapped controls frame by frame from the selected animation."""
import NLTA_RetargetV2 as rt

LABEL = "Bake Animation"


def DefaultSetting():
    return {"scale_translation": 1.0}


def Fields():
    return [("Translate Ratio", "scale_translation", "float")]


def Run(settings, context):
    bind = context.get("bind")
    if not bind:
        raise ValueError("Run the Mapping step before Bake Animation.")
    if not context.get("animation_path"):
        raise ValueError("Run the Load Animation step before baking.")
    animation_ns = context.get("source_namespace_animation") or rt.CLIP_NS
    frames = rt.bake_animation(
        bind, animation_ns,
        scale_translation=float(settings.get("scale_translation", 1.0)))
    context.update({"start_frame": frames[0], "end_frame": frames[1],
                    "source_namespace_animation": animation_ns})
    return {"start_frame": frames[0], "end_frame": frames[1]}
