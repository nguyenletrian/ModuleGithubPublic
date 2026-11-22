"""Rotate the target rig toward source forward and align Lowest position."""
import math
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Match Position / Rotate"


def DefaultSetting():
    return {"old_anchor": "", "new_anchor": "",
            "old_forward": "", "new_forward": "",
            "old_low": "", "new_low": "",
            "up": "Y", "align_position": True, "bind_frame": 0}


def Fields():
    return [
        ("Bind Frame", "bind_frame", "int"),
        ("Old Forward Base", "old_anchor", "pick"),
        ("New Forward Base", "new_anchor", "pick"),
        ("Old Forward", "old_forward", "pick"),
        ("New Forward", "new_forward", "pick"),
        ("Old Lowest", "old_low", "pick"),
        ("New Lowest", "new_low", "pick"),
        ("Up Axis", "up", "choice", ("Y", "Z", "X")),
        ("Align Lowest", "align_position", "bool"),
    ]


def yaw_between(old_base, old_forward, new_base, new_forward, up="Y"):
    axis = "XYZ".index(str(up).upper())
    a = [float(old_forward[i]) - float(old_base[i]) for i in range(3)]
    b = [float(new_forward[i]) - float(new_base[i]) for i in range(3)]
    a[axis] = b[axis] = 0.0
    if min(rt._length(a), rt._length(b)) <= 1e-6:
        raise ValueError("Forward markers must differ from their bases.")
    dot = sum(x * y for x, y in zip(b, a))
    angle = rt._cross(b, a)[axis]
    return math.degrees(math.atan2(angle, dot))


def Run(settings, context):
    cmds.currentTime(int(settings.get("bind_frame", 0)), edit=True)
    old_ns = context["source_namespace"]
    new_ns = context["target_namespace"]
    old_base = rt.position(rt.resolve(old_ns, settings.get("old_anchor", "")))
    new_base = rt.position(rt.resolve(new_ns, settings.get("new_anchor", "")))
    old_forward = rt.position(rt.resolve(old_ns, settings.get("old_forward", "")))
    new_forward = rt.position(rt.resolve(new_ns, settings.get("new_forward", "")))
    up = settings.get("up", "Y")
    angle = yaw_between(old_base, old_forward, new_base, new_forward, up)
    rotation = [0.0, 0.0, 0.0]
    rotation["XYZ".index(up.upper())] = angle
    cmds.rotate(*rotation, context["target_root"], worldSpace=True, relative=True)
    if settings.get("align_position", True):
        old_low = rt.position(rt.resolve(old_ns, settings.get("old_low", "")))
        new_low = rt.position(rt.resolve(new_ns, settings.get("new_low", "")))
        delta = tuple(old_low[i] - new_low[i] for i in range(3))
        cmds.move(*delta, context["target_root"], worldSpace=True, relative=True)
    context.setdefault("alignment", {})["yaw"] = angle
    return {"yaw": angle}
