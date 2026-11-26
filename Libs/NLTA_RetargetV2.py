"""Retarget V2 engine for Maya 2022+; independent from legacy NLTA_Retarget.

Assets are loaded into isolated namespaces. Batch processing is destructive only
after the UI asks for consent and refuses scenes containing unsaved changes.
The source rigs and animation files are never overwritten.
"""
import math
import os
import re
import time

import maya.cmds as cmds
import maya.mel as mel

EXTENSIONS = (".ma", ".mb", ".fbx")
NEW_NS = "RT_NEW"
OLD_NS = "RT_OLD"
CLIP_NS = "RT_CLIP"


def animation_files(path):
    path = os.path.abspath(os.path.expanduser(str(path).strip()))
    if os.path.isdir(path):
        files = [os.path.join(path, name) for name in sorted(os.listdir(path))
                 if os.path.isfile(os.path.join(path, name))
                 and os.path.splitext(name)[1].lower() in EXTENSIONS]
        if not files:
            raise ValueError("No .fbx, .ma or .mb animation files in " + path)
        return files
    if not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in EXTENSIONS:
        raise ValueError("Select an existing .fbx, .ma or .mb file or a folder: " + path)
    return [path]


def ensure_file(path):
    files = animation_files(path)
    if len(files) != 1 or os.path.isdir(path):
        raise ValueError("Select one rig file (.fbx, .ma or .mb).")
    return files[0]


def leaf(name):
    return str(name).split("|")[-1].split(":")[-1]


def namespace_nodes(namespace):
    prefix = namespace.strip(":") + ":"
    transforms = (cmds.ls(dag=True, long=True, type="transform") or [])
    joints = (cmds.ls(dag=True, long=True, type="joint") or [])
    return list(dict.fromkeys(
        node for node in transforms + joints
        if node.split("|")[-1].startswith(prefix)))


def mapping_candidates(namespace):
    """Auto-map only joints or curve controllers, never utility groups/locators."""
    result = []
    for node in namespace_nodes(namespace):
        if cmds.nodeType(node) == "joint":
            result.append(node)
        elif cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                type="nurbsCurve") or []:
            result.append(node)
    return result


def resolve(namespace, name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("A mapping or reference name is empty.")
    if cmds.objExists(name):
        qualified = name.split("|")[-1]
        if qualified.startswith(namespace.strip(":") + ":"):
            return (cmds.ls(name, long=True) or [name])[0]
    label = leaf(name)
    matches = [obj for obj in namespace_nodes(namespace) if leaf(obj) == label]
    if len(matches) != 1:
        raise ValueError("{}: {} matches for {!r} in namespace {!r}; "
                         "use a unique control name.".format(
                             len(matches), "ambiguous" if matches else "missing",
                             label, namespace))
    return matches[0]


def auto_root(namespace, preferred=""):
    if preferred:
        return resolve(namespace, preferred)
    names = namespace_nodes(namespace)
    roots = [node for node in names if
             not (cmds.listRelatives(node, parent=True, fullPath=True) or [])
             or not (cmds.listRelatives(node, parent=True, fullPath=True)[0]
                     .split("|")[-1].startswith(namespace + ":"))]
    if len(roots) != 1:
        raise ValueError("Namespace {} has {} root objects. Pick the global "
                         "root/control explicitly.".format(namespace, len(roots)))
    return roots[0]


def _load_file(path, namespace, **options):
    """Load on Maya's main thread without intermediate viewport redraws."""
    start = time.perf_counter()
    operation = "Reference" if options.get("reference") else "Import"
    label = "{} {}: {}".format(operation, namespace, path)
    print("[NLTA Retarget] START " + label, flush=True)
    suspended = False
    try:
        if not cmds.about(batch=True):
            cmds.refresh(suspend=True)
            suspended = True
        nodes = cmds.file(path, namespace=namespace, **options) or []
    except Exception:
        print("[NLTA Retarget] FAILED {} ({:.2f}s)".format(
            label, time.perf_counter() - start), flush=True)
        raise
    finally:
        if suspended:
            cmds.refresh(suspend=False)
    print("[NLTA Retarget] DONE {} ({:.2f}s, {} nodes)".format(
        label, time.perf_counter() - start, len(nodes)), flush=True)
    return nodes


def load_asset(path, namespace, prefer_reference=True):
    path = ensure_file(path)
    namespace = namespace.strip(":")
    if cmds.namespace(exists=namespace):
        raise ValueError("Namespace {} already exists. Use a clean scene or "
                         "remove the earlier preview.".format(namespace))
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
            cmds.loadPlugin("fbxmaya", quiet=True)
        # FBX Merge/Update-animation may update existing nodes instead of
        # creating new transforms in the requested namespace.
        previous_mode = str(mel.eval("FBXImportMode -q;")).strip().lower()
        mel.eval('FBXImportMode -v "add";')
        try:
            new_nodes = _load_file(
                path, namespace, i=True, type="FBX",
                mergeNamespacesOnClash=False, returnNewNodes=True)
        finally:
            if previous_mode in ("add", "merge", "exmerge"):
                mel.eval('FBXImportMode -v "{}";'.format(previous_mode))
    elif prefer_reference:
        new_nodes = _load_file(
            path, namespace, reference=True,
            mergeNamespacesOnClash=False, returnNewNodes=True)
    else:
        new_nodes = _load_file(
            path, namespace, i=True,
            mergeNamespacesOnClash=False, returnNewNodes=True)
    check_start = time.perf_counter()
    print("[NLTA Retarget] CHECK namespace: " + namespace, flush=True)
    loaded_nodes = namespace_nodes(namespace)
    print("[NLTA Retarget] CHECK DONE {} ({:.2f}s, {} transforms)".format(
        namespace, time.perf_counter() - check_start, len(loaded_nodes)), flush=True)
    if not loaded_nodes:
        # Explicit diagnostics: do not silently substitute transforms from
        # another imported rig or accept a pose/clip with no skeleton.
        sample = [str(node) for node in new_nodes[:8]]
        raise ValueError(
            "No transforms in namespace {!r} after importing {!r}. "
            "Imported nodes: {} (sample {}). FBX Import uses Add mode; "
            "check that the file contains joints/transforms and that the "
            "import did not place them into another namespace.".format(
                namespace, path, len(new_nodes), sample))
    return namespace


def load_retarget_assets(general, clip, context):
    """Import one clean scene's rig, optional rest pose and selected clip.

    All three assets are imported, not Maya-referenced. The reference pose
    supplies source bind transforms when available; the clip always supplies
    animated transforms for baking. The caller creates the empty scene first.
    """
    target_ns = str(general["new_namespace"]).strip(":")
    clip_ns = str(general["old_animations_namespace"]).strip(":")
    pose_ns = str(general["reference_pose_namespace"]).strip(":")
    pose_path = str(general.get("reference_pose_path") or "").strip()

    load_asset(general["new_path"], target_ns, prefer_reference=False)
    if pose_path:
        load_asset(pose_path, pose_ns, prefer_reference=False)
    load_asset(clip, clip_ns, prefer_reference=False)

    context.update({
        "source_namespace": pose_ns if pose_path else clip_ns,
        "target_namespace": target_ns,
        "source_namespace_animation": clip_ns,
        "animation_path": clip,
        "animation_loaded": True,
        "new_rig_loaded": True,
        "reference_pose_loaded": bool(pose_path),
        "references_loaded": True,
    })
    return {
        "new_rig": target_ns,
        "reference_pose": pose_ns if pose_path else None,
        "animation": clip_ns,
        "animation_path": clip,
    }


def _vec(a, b):
    return tuple(float(b[i]) - float(a[i]) for i in range(3))


def _length(vector):
    return math.sqrt(sum(x * x for x in vector))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def scale_and_yaw(old_low, old_high, new_low, new_high,
                  old_forward, new_forward, anchor="Lowest", up="Y"):
    """Compute uniform scaling and signed direction about the scene's up axis."""
    axis = "XYZ".index(str(up).upper())
    old_span = _length(_vec(old_low, old_high))
    new_span = _length(_vec(new_low, new_high))
    if min(old_span, new_span) < 1e-6:
        raise ValueError("Lowest and Highest references must be different.")
    if anchor not in ("Lowest", "Highest"):
        raise ValueError("Forward base must be Lowest or Highest.")
    base_old = old_low if anchor == "Lowest" else old_high
    base_new = new_low if anchor == "Lowest" else new_high
    forward_old = list(_vec(base_old, old_forward))
    forward_new = list(_vec(base_new, new_forward))
    forward_old[axis] = 0.0
    forward_new[axis] = 0.0
    if min(_length(forward_old), _length(forward_new)) < 1e-6:
        raise ValueError("Forward marker must not coincide with its Lowest/Highest "
                         "reference on the ground plane.")
    dot = sum(a*b for a, b in zip(forward_new, forward_old))
    signed_cross = _cross(forward_new, forward_old)[axis]
    yaw = math.degrees(math.atan2(signed_cross, dot))
    return old_span / new_span, yaw


def position(node):
    return tuple(cmds.xform(node, query=True, worldSpace=True, rotatePivot=True))


def _scale_plugs(target_root, namespace, scale_attribute):
    attr = str(scale_attribute or "").strip()
    if attr:
        if "." in attr:
            node, attribute = attr.rsplit(".", 1)
            plug = resolve(namespace, node) + "." + attribute
        else:
            plug = target_root + "." + attr
        if not cmds.objExists(plug):
            raise ValueError("Scale attribute not found: " + plug)
        return [plug]
    return [target_root + ".scale" + axis for axis in "XYZ"]


def apply_alignment(source_ns, target_ns, refs, target_root,
                    scale_attribute="", anchor="Lowest", up="Y"):
    """Resize target using Lowest/Highest, rotate toward Forward, align Lowest."""
    old_low = resolve(source_ns, refs["old_low"])
    old_high = resolve(source_ns, refs["old_high"])
    old_forward = resolve(source_ns, refs["old_forward"])
    new_low = resolve(target_ns, refs["new_low"])
    new_high = resolve(target_ns, refs["new_high"])
    new_forward = resolve(target_ns, refs["new_forward"])
    target_root = resolve(target_ns, target_root)
    ratio, angle = scale_and_yaw(position(old_low), position(old_high),
                                 position(new_low), position(new_high),
                                 position(old_forward), position(new_forward),
                                 anchor, up)
    for plug in _scale_plugs(target_root, target_ns, scale_attribute):
        if not cmds.getAttr(plug, settable=True):
            raise ValueError("Scale attribute is locked or connected: " + plug)
    for plug in _scale_plugs(target_root, target_ns, scale_attribute):
        value = cmds.getAttr(plug)
        if not isinstance(value, (float, int)):
            raise ValueError("Scale attribute must be a scalar: " + plug)
        cmds.setAttr(plug, value * ratio)
    rotation = [0.0, 0.0, 0.0]
    rotation["XYZ".index(up.upper())] = angle
    cmds.rotate(*rotation, target_root, worldSpace=True, relative=True)
    difference = _vec(position(new_low), position(old_low))
    cmds.move(*difference, target_root, worldSpace=True, relative=True)
    actual = _length(_vec(position(new_low), position(new_high)))
    expected = _length(_vec(position(old_low), position(old_high)))
    return {"ratio": ratio, "yaw": angle, "residual": abs(actual - expected),
            "scaled_span": actual, "source_span": expected}


def _rotation(node):
    import maya.api.OpenMaya as om
    matrix = om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))
    return om.MTransformationMatrix(matrix).rotation(asQuaternion=True)


def _euler_angles(quaternion, rotate_order):
    import maya.api.OpenMaya as om
    euler = quaternion.asEulerRotation()
    euler.reorderIt(int(rotate_order))
    return [math.degrees(v) for v in (euler.x, euler.y, euler.z)]


def capture_bind(pairs, source_ns, target_ns):
    """Capture per-pair world rotations and positions from matched bind pose."""
    out = []
    targets = set()
    for item in pairs:
        old = resolve(source_ns, item["old"])
        new = resolve(target_ns, item["new"])
        if new in targets:
            raise ValueError("Each new control can only have one source: " + new)
        targets.add(new)
        out.append({"old_name": leaf(old), "new": new,
                    "old_bind_rotation": _rotation(old),
                    "new_bind_rotation": _rotation(new),
                    "old_bind_position": position(old),
                    "new_bind_position": position(new),
                    "translate": bool(item.get("translate", False))})
    # Parent controls must be posed before their children.
    return sorted(out, key=lambda item: item["new"].count("|"))


def match_relative_rotate(bind, source_ns, scale_translation=1.0):
    """Apply the old control's world-space rotation delta to the new bind pose.

    The target bind orientation stays unchanged when the source is at its bind
    pose, even when control axes and original orientations differ.
    """
    for item in bind:
        old = resolve(source_ns, item["old_name"])
        desired = (_rotation(old) * item["old_bind_rotation"].inverse()
                   * item["new_bind_rotation"])
        new = item["new"]
        rotate_order = cmds.getAttr(new + ".rotateOrder")
        values = _euler_angles(desired, rotate_order)
        cmds.xform(new, worldSpace=True, rotation=values)
        if item["translate"]:
            origin = item["new_bind_position"]
            current = position(old)
            previous = item["old_bind_position"]
            target = [origin[i] + (current[i] - previous[i]) * scale_translation
                      for i in range(3)]
            cmds.xform(new, worldSpace=True, translation=target)


def match_world_rotations(pairs, source_ns, target_ns):
    """One-time explicit rest-pose alignment; never changes translation or scale."""
    resolved = [(resolve(source_ns, item["old"]),
                 resolve(target_ns, item["new"])) for item in pairs]
    if len({new for old, new in resolved}) != len(resolved):
        raise ValueError("Duplicate target controls in mapping.")
    for old, new in sorted(resolved, key=lambda pair: pair[1].count("|")):
        cmds.xform(new, worldSpace=True,
                   rotation=cmds.xform(old, query=True, worldSpace=True,
                                      rotation=True))
    return len(resolved)


def keyed_range(source_objects):
    frames = cmds.keyframe(source_objects, query=True, timeChange=True) or []
    if not frames:
        raise ValueError("No animation keys found on the mapped source controls.")
    start = int(math.floor(min(frames)))
    end = int(math.ceil(max(frames)))
    if end - start > 100000:
        raise ValueError("Animation exceeds 100,000 frames. Split the clip first.")
    return start, end


def bake_animation(bind, namespace=CLIP_NS, frame_range=None,
                   scale_translation=1.0):
    nodes = [resolve(namespace, item["old_name"]) for item in bind]
    start, end = frame_range or keyed_range(nodes)
    old_time = cmds.currentTime(query=True)
    try:
        for frame in range(start, end + 1):
            cmds.currentTime(frame, edit=True)
            match_relative_rotate(bind, namespace, scale_translation)
            for item in bind:
                node = item["new"]
                names = ["rotateX", "rotateY", "rotateZ"]
                if item["translate"]:
                    names += ["translateX", "translateY", "translateZ"]
                for channel in names:
                    plug = node + "." + channel
                    if cmds.getAttr(plug, settable=True):
                        cmds.setKeyframe(plug, time=frame)
    finally:
        cmds.currentTime(old_time, edit=True)
    return start, end


def run_post_script(script, context):
    if not str(script or "").strip():
        return
    scope = {"__builtins__": __builtins__, "__name__": "__retarget_post__",
             "cmds": cmds, "math": math, "os": os}
    scope.update(context)
    exec(compile(script, "<Retarget V2 post-script>", "exec"), scope, scope)


def drop_namespace(namespace, protected_namespace=NEW_NS):
    """Remove a source namespace, never the configured destination namespace."""
    if namespace == protected_namespace:
        raise ValueError("Refusing to remove the destination namespace.")
    if not cmds.namespace(exists=namespace):
        return
    nodes = namespace_nodes(namespace)
    references = set()
    for node in nodes:
        try:
            if cmds.referenceQuery(node, isNodeReferenced=True):
                references.add(cmds.referenceQuery(node, referenceNode=True))
        except RuntimeError:
            pass
    for reference_node in sorted(references):
        cmds.file(removeReference=True, referenceNode=reference_node)
    if cmds.namespace(exists=namespace):
        cmds.namespace(setNamespace=":")
        cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)


def unique_output(directory, filename):
    os.makedirs(directory, exist_ok=True)
    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem).strip("_") or "Animation"
    output = os.path.join(directory, stem + "_retarget.ma")
    counter = 2
    while os.path.exists(output):
        output = os.path.join(directory, "{}_retarget_{:02d}.ma".format(stem, counter))
        counter += 1
    return output


def batch_retarget(config, notify=None):
    """Run in a disposable scene per clip; caller must explicitly authorize this."""
    current_scene = cmds.file(query=True, sceneName=True) or ""
    if cmds.file(query=True, modified=True):
        raise ValueError("Save the current Maya scene before running a batch.")
    paths = animation_files(config["animation"])
    ensure_file(config["new_path"])
    ensure_file(config["old_path"])
    if not config["pairs"]:
        raise ValueError("Mapping list is empty.")
    if not config.get("output"):
        raise ValueError("Select an output folder.")
    result = []
    try:
        for clip in paths:
            cmds.file(new=True, force=True)
            load_asset(config["old_path"], OLD_NS)
            load_asset(config["new_path"], NEW_NS)
            target_root = auto_root(NEW_NS, config["new_root"])
            cmds.currentTime(config.get("bind_frame", 0), edit=True)
            info = apply_alignment(OLD_NS, NEW_NS, config["refs"], target_root,
                                   config.get("scale_attribute", ""),
                                   config.get("anchor", "Lowest"),
                                   config.get("up", "Y"))
            # Reproduce the preview bind-pose mode on every new animation file.
            if config.get("match_world_bind", False):
                match_world_rotations(config["pairs"], OLD_NS, NEW_NS)
            bind = capture_bind(config["pairs"], OLD_NS, NEW_NS)
            load_asset(clip, CLIP_NS, prefer_reference=False)
            begin, end = bake_animation(bind, CLIP_NS)
            run_post_script(config.get("post_script", ""), {
                "source_namespace": CLIP_NS, "target_namespace": NEW_NS,
                "source_root": auto_root(OLD_NS, config.get("old_root", "")),
                "target_root": target_root, "pairs": config["pairs"],
                "start_frame": begin, "end_frame": end, "animation_path": clip,
                "alignment": info})
            if not config.get("keep_sources", False):
                drop_namespace(CLIP_NS)
                drop_namespace(OLD_NS)
            output = unique_output(config["output"], clip)
            cmds.file(rename=output)
            cmds.file(save=True, type="mayaAscii", force=True)
            result.append(output)
            if notify:
                notify("{} -> {}".format(os.path.basename(clip), output))
    finally:
        cmds.file(new=True, force=True)
        if current_scene and os.path.isfile(current_scene):
            cmds.file(current_scene, open=True, force=True)
    return result
