"""User-defined Python step, executed in pipeline order."""
import NLTA_RetargetV2 as rt

LABEL = "Run Python Script"


def DefaultSetting():
    return {"code": ""}


def Fields():
    return [("Python", "code", "script")]


def Run(settings, context):
    scope = {
        "source_namespace": context.get("source_namespace_animation")
                            or context.get("source_namespace"),
        "target_namespace": context.get("target_namespace"),
        "reference_pose_namespace": context.get("reference_pose_namespace"),
        "reference_namespaces": context.get("reference_namespaces", {}),
        "reference_files": context.get("reference_files", {}),
        "source_root": context.get("source_root"),
        "target_root": context.get("target_root"),
        "pairs": context.get("pairs", []),
        "animation_path": context.get("animation_path", ""),
        "start_frame": context.get("start_frame"),
        "end_frame": context.get("end_frame"),
        "alignment": context.get("alignment", {}),
    }
    rt.run_post_script(settings.get("code", ""), scope)
    return {"executed": bool(settings.get("code", "").strip())}
