"""Temporary animation tests for Maya controls and Paint Skin influences.

Generated keys live on disposable driver transforms rather than on the rig.
Delete Keys removes only these drivers (and supported legacy test helpers).
"""
import maya.cmds as cmds

_TEST_SOURCE = "NLTA_TestAnimSource"
_TEST_CONSTRAINT = "NLTA_TestAnimConstraint"
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


def _remove_drivers(drivers):
    removed = 0
    for driver in drivers:
        if not cmds.objExists(driver):
            continue
        if cmds.objExists(driver + "." + _TEST_CONSTRAINT):
            constraint = cmds.getAttr(driver + "." + _TEST_CONSTRAINT)
            if constraint and cmds.objExists(constraint):
                cmds.delete(constraint)
        cmds.delete(driver)
        removed += 1
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


def _make_driver(control, space, kind, channels):
    parent = (cmds.listRelatives(control, parent=True, fullPath=True) or [None])[0]
    name = "NLTA_TestAnim_" + control.rsplit("|", 1)[-1].replace(":", "_") + "_DRV"
    kwargs = {"name": name, "skipSelect": True}
    if space == "local" and parent:
        kwargs["parent"] = parent
    driver = cmds.createNode("transform", **kwargs)
    constraint = None
    try:
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

        cmds.addAttr(driver, longName=_TEST_SOURCE, dataType="string")
        cmds.setAttr(driver + "." + _TEST_SOURCE, control, type="string")
        cmds.addAttr(driver, longName=_TEST_CONSTRAINT, dataType="string")
        cmds.setAttr(driver + "." + _TEST_CONSTRAINT, constraint, type="string")
        cmds.setAttr(driver + ".visibility", 0)
        return driver
    except RuntimeError:
        if constraint and cmds.objExists(constraint):
            cmds.delete(constraint)
        if cmds.objExists(driver):
            cmds.delete(driver)
        raise


def _animate_driver(driver, kind, channels, start, end):
    amplitude = 90 if kind == "rotate" else None
    original = {attr: cmds.getAttr(driver + "." + attr) for attr in channels}
    for attr in channels:
        value = original[attr]
        for frame in (start, end):
            cmds.setKeyframe(driver, attribute=attr, time=frame, value=value)
    for i, attr in enumerate(channels):
        base = original[attr]
        amount = amplitude if amplitude is not None else _distance
        at = start + (i * 4 * _STEP)
        for index, offset in enumerate((0, -amount, 0, amount, 0)):
            cmds.setKeyframe(
                driver, attribute=attr, time=at + index * _STEP,
                value=base + offset)


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

    duration = 3 * 4 * _STEP
    simultaneous = not keyInput.get("inturn", False)
    end = origin + (duration if simultaneous else duration * len(controls))
    generated = []
    try:
        for control in controls:
            _remove_drivers(_driver_for_control(control))
        for i, control in enumerate(controls):
            available = _available_channels(control, kind)
            if not available:
                cmds.warning("{} has no free {} channels; skipped."
                             .format(control, kind))
                continue
            driver = None
            try:
                driver = _make_driver(control, space, kind, available)
                start = origin if simultaneous else origin + i * duration
                _animate_driver(driver, kind, available, start, start + duration)
                if start > origin:
                    for attr in available:
                        neutral = cmds.getAttr(driver + "." + attr)
                        cmds.setKeyframe(
                            driver, attribute=attr, time=origin, value=neutral)
                if start + duration < end:
                    for attr in available:
                        neutral = cmds.getAttr(driver + "." + attr)
                        cmds.setKeyframe(
                            driver, attribute=attr, time=end, value=neutral)
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
            cmds.playbackOptions(min=origin, max=end, ast=origin, aet=end)
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
    """Delete only generated animation tests, not the rig's existing keys."""
    drivers = _test_drivers()
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
