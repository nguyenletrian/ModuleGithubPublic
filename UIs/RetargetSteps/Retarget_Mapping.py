"""Mapping of old joints/controls to new controls; capture the relative bind."""
import NLTA_RetargetV2 as rt

LABEL = "Control / Joint Mapping"


def DefaultSetting():
    return {"pairs": [], "match_world_bind": False}


def Fields():
    return [
        ("Mapping Pairs", "pairs", "pairs"),
        ("Match World Rotation", "match_world_bind", "bool"),
    ]


def Run(settings, context):
    pairs = [dict(item) for item in settings.get("pairs", [])]
    if not pairs:
        raise ValueError("Mapping step has no source/target pairs.")
    old_ns = context["source_namespace"]
    new_ns = context["target_namespace"]
    if settings.get("match_world_bind", False):
        rt.match_world_rotations(pairs, old_ns, new_ns)
    bind = rt.capture_bind(pairs, old_ns, new_ns)
    context.update({"pairs": pairs, "bind": bind})
    return {"pairs": len(bind)}
