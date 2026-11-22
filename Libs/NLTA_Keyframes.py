"""Temporary animation tests for Maya controls and Paint Skin influences.

Generated keys live on disposable driver transforms rather than on the rig.
Delete Keys removes only these drivers (and supported legacy test helpers).
"""
import json
import maya.cmds as cmds

_TEST_SOURCE = "NLTA_TestAnimSource"
_TEST_CONSTRAINT = "NLTA_TestAnimConstraint"
_TEST_POSE = "NLTA_TestAnimPose"
_STEP = 30
session = {"drivers": [], "controls": [], "start": None, "end": None}


def _selection_controls():
    """Preserve selection order and DAG identities; mesh selections are not controls."""
    result = []
    for value in cmds.ls(selection=True, long=True) or []:
        node = value.split(".", 1)[0]
        if not cmds.objExists(node) or cmds.nodeType(node) not in ("transform", "joint"):
            continue
        if cmds.listRelatives(node, shapes=True, type="mesh") or []:
            continue
        if node not in result:
            result.append(node)
    return result


def _paint_control():
    """Use the active bound influence when a mesh is selected for Paint Skin."""
    if cmds.currentCtx() != "artAttrSkinContext":
        return None
    import NLTA_Skinning
    data = NLTA_Skinning.EnsureSkinSession(warn=False)
    if not data or not data.get("skinCluster"):
        return None
    return NLTA_Skinning.GetActivePaintJoint(data["skinCluster"])


def _test_drivers():
    return cmds.ls("*." + _TEST_SOURCE, objectsOnly=True, long=True) or []


def _driver_for_control(control):
    drivers = []
    for driver in _test_drivers():
        if cmds.objExists(driver + "." + _TEST_SOURCE):
            if cmds.getAttr(driver + "." + _TEST_SOURCE) == control:
                drivers.append(driver)
    return drivers


def _saved_pose(driver):
    """Read the source pose stored on the test driver in the Maya scene."""
    plug = driver + "." + _TEST_POSE
    if not cmds.objExists(plug):
        return None
    try:
        data = json.loads(cmds.getAttr(plug))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _restore_poses(snapshots):
    """Restore parent-to-child local channels only after constraints are gone."""
    for pose in sorted(snapshots, key=lambda item: item["control"].count("|")):
        control = pose.get("control")
        if not control or not cmds.objExists(control):
            continue
        for channel, value in pose.get("channels", {}).items():
            if channel not in ("tx", "ty", "tz", "rx", "ry", "rz"):
                continue
            plug = control + "." + channel
            if not cmds.objExists(plug) or cmds.getAttr(plug, lock=True):
                continue
            # Never overwrite new connections, keyed channels or other rig inputs.
            if cmds.listConnections(plug, source=True, destination=False) or []:
                continue
            cmds.setAttr(plug, value)


def _remove_drivers(drivers):
    restores = []
    removed = 0
    for driver in drivers:
        if not cmds.objExists(driver):
            continue
        pose = _saved_pose(driver)
        if pose:
            restores.append(pose)
        if cmds.objExists(driver + "." + _TEST_CONSTRAINT):
            constraint = cmds.getAttr(driver + "." + _TEST_CONSTRAINT)
            if constraint and cmds.objExists(constraint):
                cmds.delete(constraint)
        cmds.delete(driver)
        removed += 1
    _restore_poses(restores)
    return removed


def _available_channels(control, kind):
    prefix = "r" if kind == "rotate" else "t"
    channels = []
    for axis in "xyz":
        attr = prefix + axis
        plug = control + "." + attr
        if not cmds.getAttr(plug, lock=True) and not (
                cmds.listConnections(plug, source=True, destination=False) or []):
            channels.append(attr)
    return channels


def _make_driver(control, space, kind, channels, initial_pose, origin):
    parent = (cmds.listRelatives(control, parent=True, fullPath=True) or [None])[0]
    name = "NLTA_TestAnim_" + control.rsplit("|", 1)[-1].replace(":", "_") + "_DRV"
    kwargs = {"name": name, "skipSelect": True}
    if space == "local" and parent:
        kwargs["parent"] = parent
    driver = cmds.createNode("transform", **kwargs)
    constraint = None
    try:
        cmds.addAttr(driver, longName=_TEST_SOURCE, dataType="string")
        cmds.setAttr(driver + "." + _TEST_SOURCE, control, type="string")
        cmds.addAttr(driver, longName=_TEST_POSE, dataType="string")
        cmds.setAttr(
            driver + "." + _TEST_POSE,
            json.dumps({"control": control, "channels": {
                attr: initial_pose[attr] for attr in channels}, "origin": origin}),
            type="string")
        if space == "local":
            cmds.matchTransform(driver, control, position=True, rotation=True)
        else:
            cmds.matchTransform(driver, control, position=True)
        skip = [axis for axis in "xyz" if kind[0] + axis not in channels]
        options = {"maintainOffset": True}
        if skip:
            options["skip"] = skip
        if kind == "rotate":
            constraint = cmds.orientConstraint(driver, control, **options)[0]
        else:
            constraint = cmds.pointConstraint(driver, control, **options)[0]

        cmds.addAttr(driver, longName=_TEST_CONSTRAINT, dataType="string")
        cmds.setAttr(driver + "." + _TEST_CONSTRAINT, constraint, type="string")
        cmds.setAttr(driver + ".visibility", 0)
        return driver
    except RuntimeError:
        if constraint and cmds.objExists(constraint):
            cmds.delete(constraint)
        if cmds.objExists(driver):
            cmds.delete(driver)
        _restore_poses([{"control": control, "channels": {
            attr: initial_pose[attr] for attr in channels}}])
        raise


def _animate_driver(driver, kind, channels, start, origin, finish):
    """Legacy MayaScriptBefore rhythm: five keys per X, Y, then Z, 30f apart.

    The five original keys for each axis are at +30..+150, +180..+300,
    and +330..+450 relative to this control's start. The neutral anchors
    at origin/finish keep unselected controls still during serial tests.
    """
    amount = 90 if kind == "rotate" else _distance
    original = {attr: cmds.getAttr(driver + "." + attr) for attr in channels}
    for attr in channels:
        base = original[attr]
        cmds.setKeyframe(driver, attribute=attr, time=origin, value=base)
        offset = "xyz".index(attr[-1]) * 5 * _STEP
        for index, delta in enumerate((0, -amount, 0, amount, 0), 1):
            cmds.setKeyframe(
                driver, attribute=attr,
                time=start + offset + index * _STEP, value=base + delta)
        cmds.setKeyframe(driver, attribute=attr, time=finish, value=base)


_distance = 5.0


def _animation_nodes():
    selected = _selection_controls()
    found = []
    for control in selected:
        found.extend(_driver_for_control(control))
    if found:
        return found
    if selected:
        return selected
    drivers = [name for name in session.get("drivers", []) if cmds.objExists(name)]
    return drivers or _test_drivers()


def _key_times():
    nodes = _animation_nodes()
    if not nodes:
        return []
    times = cmds.keyframe(nodes, query=True, timeChange=True) or []
    return sorted(set(times))


def CreateKeyframe(keyInput, *arr):
    """Local/world rotating or translating tests, serial or simultaneous.

    In Paint Skin mode, an active influence is used when no control is selected.
    Control chains are safe because drivers are constrained per-control without
    touching the original animation curves or creating child-joint chains.
    """
    global _distance
    kind = keyInput.get("type")
    space = keyInput.get("space")
    if kind not in ("rotate", "translate") or space not in ("local", "world"):
        cmds.warning("Animation test requires Rotate/Translate and Local/World.")
        return []
    _distance = float(cmds.intSliderGrp(keyInput["ui"], query=True, value=True))
    origin = cmds.currentTime(query=True)
    selection = cmds.ls(selection=True, long=True) or []
    controls = _selection_controls()
    if not controls:
        active = _paint_control()
        if active:
            controls = [active]
    if not controls:
        cmds.warning("Select a control (or an active Paint Skin influence) first.")
        return []

    # Legacy timing: 5 keys × 30 frames × 3 axes = 450f per control.
    duration = 3 * 5 * _STEP
    simultaneous = not keyInput.get("inturn", False)
    end = origin + (duration if simultaneous else duration * len(controls))
    generated = []
    try:
        for control in controls:
            _remove_drivers(_driver_for_control(control))
        # Capture every control BEFORE any new parent/child constraints run.
        # This keeps the neutral pose independent of selected chain order.
        initial_poses = {
            control: {attr: cmds.getAttr(control + "." + attr)
                      for attr in ("tx", "ty", "tz", "rx", "ry", "rz")}
            for control in controls
        }
        for i, control in enumerate(controls):
            available = _available_channels(control, kind)
            if not available:
                cmds.warning("{} has no free {} channels; skipped."
                             .format(control, kind))
                continue
            driver = None
            try:
                driver = _make_driver(
                    control, space, kind, available, initial_poses[control], origin)
                start = origin if simultaneous else origin + i * duration
                _animate_driver(driver, kind, available, start, origin, end)
                generated.append(driver)
            except RuntimeError as exc:
                if driver:
                    _remove_drivers([driver])
                cmds.warning("Cannot test {}: {}".format(control, exc))

        if generated:
            session.update({
                "drivers": generated, "controls": controls,
                "start": origin, "end": end,
            })
            # Keep frame 0 available, as in the original animation test UI.
            cmds.playbackOptions(
                min=min(0, origin), max=end, ast=min(0, origin), aet=end)
        else:
            cmds.warning("No controls could be animated.")
        return generated
    finally:
        cmds.currentTime(origin)
        if selection:
            cmds.select(selection, replace=True)
        else:
            cmds.select(clear=True)


def ZoomRangeAnim(*arr):
    times = _key_times()
    if len(times) < 2:
        cmds.warning("Select animated controls or create an animation test.")
        return
    frame = cmds.currentTime(query=True)
    pairs = list(zip(times[:-1], times[1:]))
    start, end = next(
        ((a, b) for a, b in pairs if a <= frame <= b),
        pairs[0] if frame < times[0] else pairs[-1])
    cmds.playbackOptions(min=start, max=end)


def FitRangeAnim(*arr):
    times = _key_times()
    if not times:
        cmds.warning("No keys on selected controls or animation-test drivers.")
        return
    cmds.playbackOptions(
        min=times[0], max=times[-1], ast=times[0], aet=times[-1])


def deleteSenceKeyframe(*arr):
    """Return controls to their original poses and delete generated tests."""
    drivers = _test_drivers()
    saved = [_saved_pose(driver) for driver in drivers]
    origins = [p["origin"] for p in saved
               if p and isinstance(p.get("origin"), (int, float))]
    # Like the previous implementation, return to the test's starting frame
    # before removing animated constraints, not the frame mid-test.
    if origins:
        cmds.currentTime(min(origins))
    count = _remove_drivers(drivers)
    # Compatible with helpers generated by the older Skinning Animation tool.
    legacy = cmds.ls("*.NLTA_worldKeyframe", objectsOnly=True, long=True) or []
    for node in legacy:
        if not cmds.objExists(node):
            continue
        descendants = cmds.listRelatives(node, allDescendents=True, fullPath=True) or []
        for driver in [node] + descendants:
            constraints = cmds.listConnections(
                driver, source=False, destination=True, type="parentConstraint") or []
            for constraint in constraints:
                if cmds.objExists(constraint):
                    cmds.delete(constraint)
        cmds.delete(node)
        count += 1
    for node in cmds.ls("*.NLTA_SourceJoint", objectsOnly=True, long=True) or []:
        if cmds.objExists(node + ".NLTA_SourceJoint"):
            cmds.deleteAttr(node + ".NLTA_SourceJoint")
    session.update({"drivers": [], "controls": [], "start": None, "end": None})
    if legacy and not origins:
        cmds.currentTime(0)  # Legacy helper tests were created around frame 0.
    if not count:
        cmds.warning("No generated animation tests to delete.")
    return count


def DeleteAttrKeyframes(*arr):
    controls = _selection_controls()
    if not controls:
        active = _paint_control()
        controls = [active] if active else []
    if not controls:
        cmds.warning("Select controls or an active Paint Skin influence.")
        return
    drivers = []
    for control in controls:
        drivers.extend(_driver_for_control(control))
    if drivers:
        _remove_drivers(drivers)
        session["drivers"] = [
            node for node in session["drivers"] if cmds.objExists(node)]
    else:
        cmds.cutKey(controls, clear=True)
