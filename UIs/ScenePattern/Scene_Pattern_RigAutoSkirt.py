import os
import re
import json
import math
import inspect
import ast
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General

STATE = {"top": {}, "rows": [], "list": None, "data": None}


def DefaultSetting(path, *args):
    module_name = os.path.splitext(os.path.basename(__file__))[0]
    return {
        "ext": "json", "path": os.path.join(path, module_name + ".json"),
        "moduleName": module_name, "order": 0, "title": "Auto Skirt",
        "name": "Auto Skirt", "id": datetime.now().strftime("%Y%m%d%H%M%S"),
    }

def _data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    if not entry or not entry.get("path"):
        raise ValueError("AutoSkirt: ScenePatternData.json has no path for this pattern")
    return os.path.normpath(entry["path"])

def _initial():
    return {"version": 2, "name": "AutoSkirt", "group": "RigUtil", "items": []}


def _get_data(data):
    path = _data_path(data)
    if not os.path.isfile(path):
        return _initial()
    saved = NLTA_General.readJsonFile(path)
    if not isinstance(saved, dict) or saved.get("version") != 2:
        return _initial()
    return saved


def _pick_single(widget, *args):
    selection = cmds.ls(selection=True, objectsOnly=True) or []
    if len(selection) != 1:
        cmds.warning("AutoSkirt: select exactly one Maya object")
        return
    cmds.textField(widget, edit=True, text=selection[0])

def _capture_extra_transform(name):
    if cmds.nodeType(name) not in ("transform", "joint"):
        raise ValueError("AutoSkirt: Extra Offset reference must be a transform or joint")
    values = [float(value) for value in cmds.xform(
        name, query=True, worldSpace=True, matrix=True)]
    if len(values) != 16 or not all(math.isfinite(value) for value in values):
        raise ValueError("AutoSkirt: invalid Extra Offset world matrix")
    return values


def _format_extra_matrix(matrix):
    """Display a captured 4x4 world matrix as four readable rows."""
    if not matrix:
        return ""
    return "\n".join(", ".join(format(float(v), ".17g") for v in matrix[i:i + 4])
                     for i in range(0, 16, 4))


def _parse_extra_matrix(value):
    """Parse an editable 16-number matrix, without querying a Maya object."""
    text = str(value).strip()
    if not text:
        return []
    parts = [part for part in re.split(r"[,;\s\[\]()]+", text) if part]
    if len(parts) != 16:
        raise ValueError("AutoSkirt: Extra Offset Matrix needs exactly 16 numbers")
    try:
        matrix = [float(value) for value in parts]
    except (TypeError, ValueError):
        raise ValueError("AutoSkirt: Extra Offset Matrix contains invalid numbers")
    if not all(math.isfinite(value) for value in matrix):
        raise ValueError("AutoSkirt: Extra Offset Matrix values must be finite")
    return matrix


def _pick_controls(widget, *args):
    selection = cmds.ls(selection=True, objectsOnly=True) or []
    if not selection:
        cmds.warning("AutoSkirt: select one or more FK controls")
        return
    cmds.scrollField(widget, edit=True, text="\n".join(dict.fromkeys(selection)))

def _add_selected_drivens(row, *args):
    """Append selected Driven controls and create one default Sub Item each."""
    selection = cmds.ls(selection=True, objectsOnly=True) or []
    if not selection:
        cmds.warning("AutoSkirt: select Driven controls before Add")
        return
    existing = [name.strip() for name in cmds.scrollField(row["controls"], query=True, text=True).splitlines() if name.strip()]
    added = [name for name in dict.fromkeys(selection) if name not in existing]
    if not added: return
    editor = row.get("subEditor")
    if editor and cmds.window(editor["window"], exists=True):
        editor["sync"]()
        cmds.deleteUI(editor["window"])
        row.pop("subEditor", None)
    axis = str(STATE.get("defaultAxis", "rotateZ"))[-1:].upper()
    for name in added:
        row["settings"].setdefault(name, {"startAngle": 10.0})
        row["subItems"].setdefault(name, _normalize_sub_items(None, axis))
    cmds.scrollField(row["controls"], edit=True, text="\n".join(existing + added))


def _mirror_lr_name(name):
    """Swap L/R name tokens without replacing letters inside ordinary words."""
    def flip(match):
        token = match.group(0)
        return {"L": "R", "R": "L", "l": "r", "r": "l",
                "Left": "Right", "Right": "Left",
                "left": "right", "right": "left"}[token]
    name = re.sub(r"(?<![A-Za-z0-9])[LRlr](?=$|[|:_.-])", flip, name)
    return re.sub(r"(?<![A-Za-z0-9])(?:Left|Right|left|right)(?=$|[|:_.-]|[A-Z])",
                  flip, name)


def _mirror_reader_data(reader, existing_ids):
    """Copy one reader to its opposite side; leave UV and rotation signs editable."""
    controls = list(reader["joints"])
    converted = [_mirror_lr_name(control) for control in controls]
    if not controls or any(a == b for a, b in zip(controls, converted)):
        raise ValueError("AutoSkirt Mirror: every Driven must contain an L/R side token")
    if len(set(converted)) != len(converted):
        raise ValueError("AutoSkirt Mirror: mirrored Driven names are not unique")
    # Prevent swapping both directions in the same source reader.
    def side_of(name):
        parts = re.search(r"(?<![A-Za-z0-9])([LRlr])(?=$|[|:_.-])", name)
        if parts: return parts.group(1).upper()
        words = re.search(r"(?<![A-Za-z0-9])(Left|Right|left|right)(?=$|[|:_.-]|[A-Z])", name)
        return words.group(1)[0].upper() if words else None
    sides = {side_of(name) for name in controls}
    if None in sides or len(sides) != 1:
        raise ValueError("AutoSkirt Mirror: Driven controls must all belong to the same side")
    target_side = "L" if "R" in sides else "R"
    result = json.loads(json.dumps(reader))
    result["id"] = _mirror_lr_name(reader["id"])
    if result["id"] == reader["id"]:
        result["id"] = target_side + "_" + reader["id"]
    if result["id"] in existing_ids:
        raise ValueError("AutoSkirt Mirror: Reader ID already exists: " + result["id"])
    for key in ("sphere", "parent", "start", "end"):
        result[key] = _mirror_lr_name(reader.get(key, ""))
    if result["sphere"] == reader["sphere"]:
        result["sphere"] = target_side + "_" + reader["sphere"]
    result["joints"] = converted
    # Extra matrices are side-specific. Never copy an L matrix to the R side.
    # Legacy saved source names can locate a mirrored reference; otherwise Pick
    # the Extra Offset Matrix independently after mirroring the reader.
    for entries in result.get("subItems", []):
        for sub in entries:
            if not sub.get("extraOffsetMatrix"):
                continue
            source = sub.pop("extraOffsetObject", "")
            opposite = _mirror_lr_name(source) if source else ""
            if opposite and opposite != source and cmds.objExists(opposite):
                sub["extraOffsetMatrix"] = _capture_extra_transform(opposite)
            else:
                sub.pop("extraOffsetMatrix", None)
    # A new side needs its own bind-pose V projection.
    result["refV"] = []
    # Keep manually edited Sub Item Ref V; nullable Auto values remain Auto.
    return result


def _mirror_row(row, *args):
    """Add the mirrored reader to the form and persist it in one transaction."""
    try:
        config = _read_ui()  # Also synchronizes an open Sub Item editor.
        source_id = cmds.textField(row["id"], query=True, text=True).strip()
        reader = next(item for item in config["items"] if item["id"] == source_id)
        clone = _mirror_reader_data(reader, {item["id"] for item in config["items"]})
        # Distinct Pose Readers may intentionally share the same Driven.
        # Only duplicate controls inside one Reader remain invalid.
        added = _add_row(STATE["holder"], clone)
        try:
            _save(STATE["data"])
        except (OSError, ValueError, RuntimeError):
            _remove_row(added)
            raise
        print("AutoSkirt Mirror: {} -> {} (configuration saved; Run to build)".format(
            source_id, clone["id"]))
        return added
    except (StopIteration, ValueError, RuntimeError, OSError) as exc:
        cmds.warning("AutoSkirt Mirror: {}".format(exc))
        return None


def _live_follicle_size(row, *args):
    """Update follicle display markers for a built Pose Reader."""
    size = float(cmds.floatField(row["follicleSize"], query=True, value=True))
    if not math.isfinite(size) or not 0.01 <= size <= 100:
        cmds.warning("AutoSkirt: Follicle Display Size must be 0.01..100")
        return False
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    plug = "{}_{}_ROOT.follicleSize".format(system, rid)
    if cmds.objExists(plug):
        cmds.setAttr(plug, size)
        return True
    return False


def _line_field(parent, label, initial, picker=True):
    cmds.rowLayout(parent=parent, numberOfColumns=3,
                   adjustableColumn=2, columnWidth3=(105, 160, 55))
    cmds.text(label=label, align="left")
    widget = cmds.textField(text=str(initial))
    if picker:
        cmds.button(label="Pick", command=partial(_pick_single, widget))
    else:
        cmds.text(label="")
    cmds.setParent("..")
    return widget

def _normalize_sub_items(entries, axis="Z", start_angle=10.0):
    """Validate one Sub Item; Max Distance of zero enables geometry Auto mode."""
    default = [{"axis": str(axis).upper()[-1:], "outputType": "rotate",
                "reverseU": False, "invertRotate": False, "strength": 1.0,
                "startAngle": float(start_angle), "maxDistance": 0.0,
                "minDistance": 0.0, "refV": None}]
    if entries is None:
        entries = default
    if not isinstance(entries, (list, tuple)) or not entries:
        raise ValueError("AutoSkirt: every Driven needs at least one Sub Item")
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("AutoSkirt: Sub Item must contain settings")
        output_axis = str(entry.get("axis", axis)).upper()[-1:]
        output_type = entry.get("outputType", "rotate")
        if not isinstance(output_type, str) or output_type.lower() not in ("rotate", "translate"):
            raise ValueError("AutoSkirt: Sub Item Output Type must be Rotate or Translate")
        output_type = output_type.lower()
        reverse = entry.get("reverseU", False)
        invert = entry.get("invertRotate", False)
        strength = float(entry.get("strength", 1.0))
        start = float(entry.get("startAngle", start_angle))
        max_distance = float(entry.get("maxDistance", 0.0))
        min_distance = float(entry.get("minDistance", 0.0))
        ref_v = entry.get("refV")
        ref_v = None if ref_v is None else float(ref_v)
        extra_matrix = entry.get("extraOffsetMatrix") or []
        if extra_matrix:
            if not isinstance(extra_matrix, (list, tuple)) or len(extra_matrix) != 16:
                raise ValueError("AutoSkirt: Extra Offset Matrix needs 16 values")
            try:
                extra_matrix = [float(value) for value in extra_matrix]
            except (TypeError, ValueError):
                raise ValueError("AutoSkirt: Extra Offset Matrix values must be numbers")
            if not all(math.isfinite(value) for value in extra_matrix):
                raise ValueError("AutoSkirt: Extra Offset Matrix values must be finite")
        if output_axis not in ("X", "Y", "Z"):
            raise ValueError("AutoSkirt: Sub Item Output Axis must be X, Y or Z")
        if not isinstance(reverse, bool):
            raise ValueError("AutoSkirt: Reverse U must be a checkbox value")
        if not isinstance(invert, bool):
            raise ValueError("AutoSkirt: Invert Rotate must be a checkbox value")
        if not math.isfinite(strength) or not 0 <= strength <= 2:
            raise ValueError("AutoSkirt: Angle Strength must be between 0 and 2")
        if not math.isfinite(start) or not 0 <= start < 180:
            raise ValueError("AutoSkirt: Sub Item Start Angle must be 0..180")
        if not math.isfinite(max_distance) or max_distance < 0 or 0 < max_distance < 0.001:
            raise ValueError("AutoSkirt: Max Distance must be 0 (Auto) or at least 0.001")
        if not math.isfinite(min_distance) or min_distance < 0:
            raise ValueError("AutoSkirt: Max Effect Range must be nonnegative")
        if max_distance > 0 and min_distance >= max_distance:
            raise ValueError("AutoSkirt: Max Effect Range must be below Max Distance")
        if ref_v is not None and (not math.isfinite(ref_v) or not 0 <= ref_v <= 1):
            raise ValueError("AutoSkirt: Ref V must be between 0 and 1")
        normalized = {"axis": output_axis, "outputType": output_type, "reverseU": reverse,
                      "invertRotate": invert, "strength": strength,
                      "startAngle": start, "maxDistance": max_distance,
                      "minDistance": min_distance, "refV": ref_v}
        if extra_matrix:
            normalized["extraOffsetMatrix"] = extra_matrix
        result.append(normalized)
    shared_matrices = [sub["extraOffsetMatrix"] for sub in result
                       if sub.get("extraOffsetMatrix")]
    if shared_matrices:
        if any(matrix != shared_matrices[0] for matrix in shared_matrices[1:]):
            cmds.warning("AutoSkirt: multiple saved Extra Offset matrices for one Driven; "
                         "using the first matrix for all Sub Item channels")
        for sub in result:
            sub.pop("extraOffsetMatrix", None)
        result[0]["extraOffsetMatrix"] = shared_matrices[0]
    return result

def _fallback_live_reference(row, control, index, system, rid):
    """Reconnect to an exported/built rig that has no patternData metadata.

    Resolve only the exact deterministic Reader/Driven/Sub Item names and
    require the live DG plugs to exist. Never create nodes or rebuild a rig.
    """
    controls = _controls(row)
    if control not in controls:
        return None
    slot = controls.index(control)
    tag = "{}_{}_{:02d}".format(system, rid, slot + 1)
    ref = tag + "_Ref_Follicle"
    subtag = "{}_Sub{:02d}".format(tag, index + 1)
    required = (system + "_System", ref + ".sub{:02d}MaxDistance".format(index + 1),
                subtag + "_NeutralDistance.distance",
                subtag + "_ZeroNeutral.input1D[1]")
    if not all(cmds.objExists(plug) for plug in required):
        return None
    references = {}
    for position, driven in enumerate(controls, 1):
        candidate = "{}_{}_{:02d}_Ref_Follicle".format(system, rid, position)
        if cmds.objExists(candidate):
            references[driven] = candidate
    return slot, ref, references


def _apply_live_sub_item(row, control, index, *args, restore_auto_ref=False):
    """Update a built reader after reopening Maya, preserving the neutral pose."""
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    meta = _meta_from_scene({"name": system})
    original = None
    if meta:
        original = next((item for item in meta.get("data", {}).get("items", [])
                         if item.get("id") == rid), None)
        if not original or control not in original.get("joints", []):
            return False
        slot = original["joints"].index(control)
        built_subs = original.get("subItems", [])
        if slot >= len(built_subs) or index >= len(built_subs[slot]):
            return False
        spec = row["subItems"][control][index]
        built_spec = built_subs[slot][index]
        if (spec["axis"] != built_spec["axis"] or
                spec.get("outputType", "rotate") != built_spec.get("outputType", "rotate") or
                spec.get("extraOffsetMatrix", []) != built_spec.get("extraOffsetMatrix", [])):
            return False  # Changing output wiring or Extra Offset requires a clean rebuild.
        reference = meta.get("refs", {}).get(rid, {}).get(control)
        if not reference:
            return False
        ref = reference[0]
        references = {name: entry[0] for name, entry in
                      meta.get("refs", {}).get(rid, {}).items() if entry}
    else:
        # Standalone ExportPython builds can lack patternData on _System.
        resolved = _fallback_live_reference(row, control, index, system, rid)
        if not resolved:
            return False
        slot, ref, references = resolved
        spec = row["subItems"][control][index]
    tag = "{}_{}_{:02d}".format(system, rid, slot + 1)
    subtag = "{}_Sub{:02d}".format(tag, index + 1)
    suffix = "sub{:02d}".format(index + 1)
    attrs = {
        "start": ref + (".raiseStartAngle" if index == 0 else "." + suffix + "StartAngle"),
        "distance": ref + "." + suffix + "MaxDistance",
        "minDistance": ref + "." + suffix + "MinDistance",
        "strength": ref + "." + suffix + "Strength",
        "refV": ref + (".refV" if index == 0 else "." + suffix + "RefV"),
        "neutralSpatial": subtag + "_NeutralDistance.distance",
        "rotateSign": (ref + ".rotateSign" if index == 0
                       else ref + "." + suffix + "RotateSign"),
        "neutralDistance": ref + (".neutralDistance" if index == 0
                                   else "." + suffix + "NeutralDistance"),
        "neutralU": "{}_{}_ROOT.neutralU".format(system, rid),
        "zero": subtag + "_ZeroNeutral.input1D[1]",
        "angleMin": subtag + "_AngleFromU.outputMin",
        "angleMax": subtag + "_AngleFromU.outputMax",
        "autoDistance": ref + (".autoMaxDistance" if index == 0
                               else "." + suffix + "AutoMaxDistance"),
    }
    new_ref_v = spec["refV"]
    if new_ref_v is None and restore_auto_ref and index == 0:
        # JSON's saved Ref V is authoritative for Sub 01. Preserve Auto
        # (None) for other Sub Items: their original projection was not
        # serialized, and replacing it with Sub 01's V would be incorrect.
        new_ref_v = row.get("referenceV", {}).get(control)
        if new_ref_v is None and original:
            captured = original.get("refV", [])
            if slot < len(captured):
                new_ref_v = float(captured[slot])
    if new_ref_v is not None:
        cmds.setAttr(attrs["refV"], new_ref_v)
        # Auto range follows the moved Ref without changing the saved Auto sentinel.
        neighbours = [value for key, value in references.items() if key != control]
        if neighbours:
            sub_ref = ref if index == 0 else subtag + "_Ref_Follicle"
            position = cmds.xform(sub_ref, query=True, worldSpace=True, rotatePivot=True)
            distances = [math.sqrt(sum((a - b) ** 2 for a, b in zip(
                position, cmds.xform(other, query=True, worldSpace=True, rotatePivot=True))))
                for other in neighbours]
            cmds.setAttr(attrs["autoDistance"], max(min(distances), 0.001))
    auto_distance = max(float(cmds.getAttr(attrs["autoDistance"])), 0.001)
    effective = (spec["maxDistance"] if spec["maxDistance"] > 0 else auto_distance)
    min_distance = spec["minDistance"]
    if min_distance >= effective:
        raise ValueError("AutoSkirt: Max Effect Range must be below Max Distance "
                         "({:.3f}). Lower Max Effect Range or increase Max Distance."
                         .format(effective))
    neutral_u = float(cmds.getAttr(attrs["neutralU"]))
    neutral_distance = float(cmds.getAttr(attrs["neutralSpatial"]))
    cmds.setAttr(attrs["neutralDistance"], neutral_distance)
    neutral_angle = 180.0 * ((1.0 - neutral_u) if spec["reverseU"] else neutral_u)
    neutral_weight = max(0.0, min(1.0, (effective - neutral_distance) /
                                   (effective - min_distance)))
    neutral_value = max(0.0, neutral_angle - spec["startAngle"]) * neutral_weight
    cmds.setAttr(attrs["start"], spec["startAngle"])
    cmds.setAttr(attrs["distance"], effective)
    cmds.setAttr(attrs["minDistance"], min_distance)
    cmds.setAttr(attrs["strength"], spec["strength"])
    cmds.setAttr(attrs["rotateSign"], -1.0 if spec["invertRotate"] else 1.0)
    cmds.setAttr(subtag + "_DistanceWeight.outputMin", 1.0)
    cmds.setAttr(attrs["angleMin"], 180.0 if spec["reverseU"] else 0.0)
    cmds.setAttr(attrs["angleMax"], 0.0 if spec["reverseU"] else 180.0)
    cmds.setAttr(attrs["zero"], neutral_value)
    return True

def _auto_max_distance_for_display(row, control, index):
    """Return the computed scene distance for an unmodified Auto Sub Item."""
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    meta = _meta_from_scene({"name": system})
    if not meta:
        resolved = _fallback_live_reference(row, control, index, system, rid)
        if not resolved:
            return None
        _, ref, _ = resolved
        plug = ref + ".sub{:02d}MaxDistance".format(index + 1)
        value = float(cmds.getAttr(plug))
        return value if math.isfinite(value) and value >= 0.001 else None
    original = next((item for item in meta.get("data", {}).get("items", [])
                     if item.get("id") == rid), None)
    if not original or control not in original.get("joints", []):
        return None
    slot = original["joints"].index(control)
    subs = original.get("subItems", [])
    if slot >= len(subs) or index >= len(subs[slot]):
        return None
    ref = meta.get("refs", {}).get(rid, {}).get(control)
    if not ref:
        return None
    plug = ref[0] + ".sub{:02d}MaxDistance".format(index + 1)
    value = float(cmds.getAttr(plug))
    return value if math.isfinite(value) and value >= 0.001 else None


def _ref_v_for_display(row, control, index):
    """Read a built Ref V without changing the automatic JSON default."""
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    meta = _meta_from_scene({"name": system})
    if not meta:
        resolved = _fallback_live_reference(row, control, index, system, rid)
        if not resolved:
            return None
        _, ref, _ = resolved
        plug = ref + (".refV" if index == 0 else ".sub{:02d}RefV".format(index + 1))
        value = float(cmds.getAttr(plug))
        return value if math.isfinite(value) and 0 <= value <= 1 else None
    original = next((item for item in meta.get("data", {}).get("items", [])
                     if item.get("id") == rid), None)
    if not original or control not in original.get("joints", []):
        return None
    slot = original["joints"].index(control)
    subs = original.get("subItems", [])
    if slot >= len(subs) or index >= len(subs[slot]):
        return None
    reference = meta.get("refs", {}).get(rid, {}).get(control)
    if not reference:
        return None
    plug = reference[0] + (".refV" if index == 0 else ".sub{:02d}RefV".format(index + 1))
    value = float(cmds.getAttr(plug))
    return value if math.isfinite(value) and 0 <= value <= 1 else None


def _mirror_ref_position(point, source_start, target_start):
    """Reflect a point across the plane halfway between opposite Starts."""
    delta = [float(b) - float(a) for a, b in zip(source_start, target_start)]
    length = math.sqrt(sum(v*v for v in delta))
    if length < 1e-6:
        raise ValueError("Opposite Start positions coincide; cannot infer mirror plane")
    normal = [v / length for v in delta]
    center = [(float(a) + float(b)) * 0.5 for a, b in zip(source_start, target_start)]
    offset = sum((float(p) - center[i]) * normal[i] for i, p in enumerate(point))
    return [float(p) - 2.0 * offset * normal[i] for i, p in enumerate(point)]


def _mirror_ref_v_from_scene(source, target, source_v, source_control, target_control):
    """Map opposite Ref position across a symmetry plane to target sphere V."""
    source_sphere, target_sphere = source["sphere"], target["sphere"]
    if not all(cmds.objExists(name) for name in (source_sphere, target_sphere)):
        return None
    # Start may be a shared Pelvis, so try End and Driven as backup plane anchors.
    mirror_anchors = ((source["start"], target["start"]),
                      (source["end"], target["end"]),
                      (source_control, target_control))
    axis = None
    for left, right in mirror_anchors:
        if not cmds.objExists(left) or not cmds.objExists(right):
            continue
        a = cmds.xform(left, query=True, worldSpace=True, rotatePivot=True)
        b = cmds.xform(right, query=True, worldSpace=True, rotatePivot=True)
        if sum((x - y) ** 2 for x, y in zip(a, b)) > 1e-10:
            axis = (a, b)
            break
    if axis is None:
        return None
    src_shapes = cmds.listRelatives(source_sphere, shapes=True, noIntermediate=True,
                                    type="nurbsSurface", fullPath=True) or []
    dst_shapes = cmds.listRelatives(target_sphere, shapes=True, noIntermediate=True,
                                    type="nurbsSurface", fullPath=True) or []
    if not src_shapes or not dst_shapes:
        return None
    src_shape, dst_shape = src_shapes[0], dst_shapes[0]
    src_u0, src_u1 = (float(cmds.getAttr(src_shape + "." + field))
                      for field in ("minValueU", "maxValueU"))
    src_v0, src_v1 = (float(cmds.getAttr(src_shape + "." + field))
                      for field in ("minValueV", "maxValueV"))
    dst_v0, dst_v1 = (float(cmds.getAttr(dst_shape + "." + field))
                      for field in ("minValueV", "maxValueV"))
    if src_u1 <= src_u0 or src_v1 <= src_v0 or dst_v1 <= dst_v0:
        raise ValueError("Mirror Ref: invalid NURBS UV domain")
    sample_u = (src_u0 + src_u1) * 0.5
    sample_v = src_v0 + (src_v1 - src_v0) * source_v
    sampler = cmds.createNode("pointOnSurfaceInfo", name="AutoSkirt_MirrorSource_Sampler#")
    destination = None
    try:
        cmds.connectAttr(src_shape + ".worldSpace[0]", sampler + ".inputSurface", force=True)
        cmds.setAttr(sampler + ".parameterU", sample_u)
        cmds.setAttr(sampler + ".parameterV", sample_v)
        point = cmds.getAttr(sampler + ".position")[0]
        mirrored = _mirror_ref_position(point, axis[0], axis[1])
        destination = cmds.createNode("closestPointOnSurface", name="AutoSkirt_MirrorTarget_Sampler#")
        cmds.connectAttr(dst_shape + ".worldSpace[0]", destination + ".inputSurface", force=True)
        cmds.setAttr(destination + ".inPosition", *mirrored, type="double3")
        raw_v = float(cmds.getAttr(destination + ".parameterV"))
    finally:
        cmds.delete(sampler)
        if destination: cmds.delete(destination)
    return max(0.0, min(1.0, (raw_v - dst_v0) / (dst_v1 - dst_v0)))


def _source_ref_v_from_driven(sphere, driven):
    """Project the opposite Driven to its sphere when its Ref is still Auto."""
    if not cmds.objExists(sphere) or not cmds.objExists(driven):
        return None
    shapes = cmds.listRelatives(sphere, shapes=True, noIntermediate=True,
                                type="nurbsSurface", fullPath=True) or []
    if not shapes: return None
    shape = shapes[0]
    low = float(cmds.getAttr(shape + ".minValueV"))
    high = float(cmds.getAttr(shape + ".maxValueV"))
    if high <= low: return None
    point = cmds.xform(driven, query=True, worldSpace=True, rotatePivot=True)
    node = cmds.createNode("closestPointOnSurface", name="AutoSkirt_MirrorSourceDriven_Sampler#")
    try:
        cmds.connectAttr(shape + ".worldSpace[0]", node + ".inputSurface", force=True)
        cmds.setAttr(node + ".inPosition", *point, type="double3")
        v = float(cmds.getAttr(node + ".parameterV"))
    finally:
        cmds.delete(node)
    return max(0.0, min(1.0, (v - low) / (high - low)))


def _get_mirror_ref_v(row, control, index):
    """Resolve the opposite Sub Item Ref; prefer scene geometry over V inversion."""
    config = _read_ui()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    opposite_control = _mirror_lr_name(control)
    matches = [(reader, reader["joints"].index(opposite_control))
               for reader in config["items"]
               if reader["id"] != rid and opposite_control in reader["joints"]]
    if len(matches) != 1:
        raise ValueError("Get Mirror Ref: expected one opposite Driven: " + opposite_control)
    opposite, slot = matches[0]
    if index >= len(opposite["subItems"][slot]):
        raise ValueError("Get Mirror Ref: opposite Driven has no Sub Item {:02d}".format(index + 1))
    sub = opposite["subItems"][slot][index]
    value = sub.get("refV")
    if value is None:
        # Auto source: use the built Ref when available, else its saved projection.
        for other_row in STATE["rows"]:
            if cmds.textField(other_row["id"], query=True, text=True).strip() == opposite["id"]:
                value = _ref_v_for_display(other_row, opposite_control, index)
                break
        if value is None:
            projected = opposite.get("refV", [])
            if slot < len(projected):
                value = projected[slot]
        if value is None:
            value = _source_ref_v_from_driven(opposite["sphere"], opposite_control)
    if value is None:
        raise ValueError("Get Mirror Ref: opposite Ref V is unavailable; build or set it first")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Get Mirror Ref: opposite Ref V must be 0..1")
    target = next((reader for reader in config["items"] if reader["id"] == rid), None)
    if target is None:
        raise ValueError("Get Mirror Ref: current Reader was not found")
    projected = _mirror_ref_v_from_scene(opposite, target, value, opposite_control, control)
    return (projected, "scene position") if projected is not None else (
        1.0 - value, "1 - opposite Ref V")


def _mute_gate_plug(row, control, index):
    """Find the existing scene gate for one built Sub Item."""
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    meta = _meta_from_scene({"name": system})
    if not meta:
        resolved = _fallback_live_reference(row, control, index, system, rid)
        if not resolved:
            return None
        slot = resolved[0]
        gate = "{}_{}_{:02d}_Sub{:02d}_MuteGate.input2X".format(
            system, rid, slot + 1, index + 1)
        return gate if cmds.objExists(gate) else None
    original = next((item for item in meta["data"].get("items", [])
                     if item["id"] == rid), None)
    if not original or control not in original["joints"]: return None
    slot = original["joints"].index(control)
    subs = original.get("subItems", [])
    if slot >= len(subs) or index >= len(subs[slot]): return None
    gate = "{}_{}_{:02d}_Sub{:02d}_MuteGate.input2X".format(
        system, rid, slot + 1, index + 1)
    return gate if cmds.objExists(gate) else None


def _read_sub_item_mute(row, control, index):
    """Muted state is a scene override, never a JSON Sub Item field."""
    gate = _mute_gate_plug(row, control, index)
    return bool(gate and float(cmds.getAttr(gate)) < 0.5)


def _set_sub_item_mute(row, control, index, muted):
    """Block only this Sub Item's output without changing Angle Strength."""
    gate = _mute_gate_plug(row, control, index)
    if not gate:
        cmds.warning("AutoSkirt Mute: run the updated builder to create Mute gates")
        return False
    cmds.setAttr(gate, 0.0 if muted else 1.0)
    return True


def _read_sub_item_fields(fields, auto_unchanged, ref_v_unchanged):
    """Read one output channel; Extra Offset is shared at the Driven level."""
    result = {
        "axis": cmds.optionMenu(fields["axis"], query=True, value=True),
        "outputType": cmds.optionMenu(fields["outputType"], query=True, value=True).lower(),
        "reverseU": bool(cmds.checkBox(fields["reverse"], query=True, value=True)),
        "invertRotate": bool(cmds.checkBox(fields["invert"], query=True, value=True)),
        "strength": float(cmds.floatSliderGrp(fields["strength"], query=True, value=True)),
        "startAngle": float(cmds.floatSliderGrp(fields["start"], query=True, value=True)),
        "maxDistance": 0.0 if auto_unchanged else float(
            cmds.floatSliderGrp(fields["distance"], query=True, value=True)),
        "minDistance": float(cmds.floatSliderGrp(fields["minDistance"], query=True, value=True)),
        "refV": None if ref_v_unchanged else float(
            cmds.floatSliderGrp(fields["refV"], query=True, value=True)),
    }
    return result


def _build_live_added_sub_item(row, control, index, spec):
    """Append one Sub Item DG branch to an existing rig without rebuilding it.

    Return False when the Reader has not been built yet (UI-only addition).
    Existing Sub Items and Driven offsets are not rebuilt or zeroed.
    """
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    system_root = system + "_System"
    if not cmds.objExists(system_root):
        return False
    prefix = "{}_{}".format(system, rid)
    if not cmds.objExists(prefix + "_ROOT"):
        # The system exists, but this Reader has not been built yet.
        return False
    if index < 1:
        raise ValueError("AutoSkirt Live Add: an existing Sub 01 is required")
    control_list = _controls(row)
    if control not in control_list:
        raise ValueError("AutoSkirt Live Add: unknown Driven " + control)
    slot = control_list.index(control)
    meta = _meta_from_scene({"name": system})
    original = None
    if meta:
        original = next((item for item in meta.get("data", {}).get("items", [])
                         if item.get("id") == rid), None)
        if original is None:
            return False  # Newly configured Reader; normal Run builds it later.
        if control not in original.get("joints", []):
            raise ValueError("AutoSkirt Live Add: Driven differs from the built scene")
        slot = original["joints"].index(control)
        stored = original.get("subItems", [])
        if slot >= len(stored) or len(stored[slot]) != index:
            raise ValueError("AutoSkirt Live Add: built Sub Item count differs from the "
                             "editor; restore JSON or use a clean build")
        for older_index, old_spec in enumerate(stored[slot]):
            current = row["subItems"][control][older_index]
            if (current["axis"] != old_spec["axis"] or
                    current.get("outputType", "rotate") !=
                    old_spec.get("outputType", "rotate")):
                raise ValueError("AutoSkirt Live Add: existing output wiring has changed; "
                                 "a clean rebuild is required")

    tag = "{}_{:02d}".format(prefix, slot + 1)
    subtag = "{}_Sub{:02d}".format(tag, index + 1)
    suffix = "sub{:02d}".format(index + 1)
    ref = (meta.get("refs", {}).get(rid, {}).get(control, [None])[0]
           if meta else None) or tag + "_Ref_Follicle"
    root = prefix + "_ROOT"
    fol_group = prefix + "_Follicles"
    marker_size = prefix + "_MarkerSize"
    moving = prefix + "_Moving_Follicle"
    neutral_moving = prefix + "_NeutralMoving_Follicle"
    cp = prefix + "_CP_Follicle"
    offset = tag + "_DrivenOffset"
    required = (root, fol_group, marker_size, moving, neutral_moving,
                cp, ref, offset, ref + ".refV", root + ".equatorU",
                root + ".neutralU", root + ".autoSkirt")
    for name in required:
        if not cmds.objExists(name):
            raise ValueError("AutoSkirt Live Add: missing built node/plug " + name)
    if not cmds.objExists("{}_Sub{:02d}_MuteGate".format(tag, index)):
        raise ValueError("AutoSkirt Live Add: previous Sub Item network is missing; "
                         "rebuild the Reader on a clean scene")
    # Later Pose Readers can insert additional offset groups between this
    # Reader and its Driven. Locate the named control among all descendants.
    offset_paths = cmds.ls(offset, long=True, type="transform") or []
    if len(offset_paths) != 1:
        raise ValueError("AutoSkirt Live Add: missing/ambiguous DrivenOffset " + offset)
    full_offset = offset_paths[0]
    leaf_control = control.rsplit("|", 1)[-1]
    candidates = cmds.ls(leaf_control, long=True, type="transform") or []
    driven_matches = [node for node in candidates
                      if node.rsplit("|", 1)[-1] == leaf_control
                      and node.startswith(full_offset + "|")
                      and cmds.objExists(node + ".AutoFollow")]
    if len(driven_matches) != 1:
        raise ValueError("AutoSkirt Live Add: expected one named Driven below {}: {} (found {})"
                         .format(offset, control, len(driven_matches)))
    auto_follow = driven_matches[0] + ".AutoFollow"
    if cmds.objExists(subtag + "_Ref_Follicle") or cmds.objExists(subtag + "_MuteGate"):
        raise ValueError("AutoSkirt Live Add: Sub Item {} already exists".format(index + 1))
    for attr in ("RefV", "StartAngle", "AutoMaxDistance", "NeutralDistance",
                 "MaxDistance", "MinDistance", "Strength", "RotateSign"):
        if cmds.objExists(ref + "." + suffix + attr):
            raise ValueError("AutoSkirt Live Add: existing attribute {}{}".format(suffix, attr))

    spec = _normalize_sub_items([spec])[0]
    if spec.get("extraOffsetMatrix"):
        raise ValueError("AutoSkirt Live Add: Extra Offset requires a clean Run")
    kind, axis = spec["outputType"], spec["axis"]
    output_target = offset
    # Reuse a single existing Extra Offset for every output channel, even
    # when the newly added Sub Item did not capture a matrix.
    if original:
        previous_specs = original.get("subItems", [])[slot]
        extra_indices = [i for i, old in enumerate(previous_specs)
                         if old.get("extraOffsetMatrix")]
    else:
        extra_indices = [i for i in range(index)
                         if cmds.objExists("{}_Sub{:02d}_autoskirtExtraTransform".format(tag, i + 1))]
    if len(extra_indices) == 1:
        candidate = "{}_Sub{:02d}_autoskirtExtraTransform".format(
            tag, extra_indices[0] + 1)
        if not cmds.objExists(candidate):
            raise ValueError("AutoSkirt Live Add: missing Extra Transform " + candidate)
        output_target = candidate
    output = output_target + "." + kind + axis
    sum_node = (tag if output_target == offset else output_target) + "_" + kind.capitalize() + axis + "_Sum"
    # Plan the final routing before creating any follicle or DG node.
    incoming = cmds.listConnections(output, source=True, destination=False,
                                    plugs=True, skipConversionNodes=True) or []
    if len(incoming) > 1:
        raise ValueError("AutoSkirt Live Add: multiple inputs on " + output)
    previous = incoming[0] if incoming else None
    route = "direct"
    if previous:
        source_name = previous.split(".")[0].rsplit("|", 1)[-1]
        if source_name == sum_node and previous.endswith(".output1D"):
            route = "sum"
        elif (previous.endswith(".outputX") and
              source_name in [tag + "_Sub{:02d}_MuteGate".format(i + 1)
                              for i in range(index)]):
            route = "create_sum"
            if cmds.objExists(sum_node):
                raise ValueError("AutoSkirt Live Add: existing sum node " + sum_node)
        else:
            raise ValueError("AutoSkirt Live Add: refusing to replace foreign "
                             "connection {} -> {}".format(previous, output))

    if original:
        sphere = original.get("sphere", "")
        reference_v = original.get("refV", [])
        projected = reference_v[slot] if slot < len(reference_v) else None
    else:
        sphere = cmds.textField(row["sphere"], query=True, text=True).strip()
        projected = row.get("referenceV", {}).get(control)
    if not sphere or not cmds.objExists(sphere):
        raise ValueError("AutoSkirt Live Add: built NURBS sphere is missing")
    surface = cmds.listRelatives(sphere, shapes=True, noIntermediate=True,
                                 fullPath=True, type="nurbsSurface") or []
    cp_shape = cmds.listRelatives(cp, shapes=True, noIntermediate=True,
                                  fullPath=True, type="follicle") or []
    if len(surface) != 1 or len(cp_shape) != 1:
        raise ValueError("AutoSkirt Live Add: expected one surface and one CP follicle")
    if projected is None:
        projected = float(cmds.getAttr(ref + ".refV"))
    sub_v = float(projected if spec["refV"] is None else spec["refV"])
    other_refs = []
    reference_controls = original["joints"] if original else control_list
    for pos, driven in enumerate(reference_controls, 1):
        if driven == control:
            continue
        candidate = (meta.get("refs", {}).get(rid, {}).get(driven, [None])[0]
                     if meta else None) or "{}_{:02d}_Ref_Follicle".format(prefix, pos)
        if not cmds.objExists(candidate):
            raise ValueError("AutoSkirt Live Add: missing neighbor Ref " + candidate)
        other_refs.append(candidate)
    bounds = cmds.exactWorldBoundingBox(sphere)
    radius = max(bounds[3] - bounds[0], bounds[4] - bounds[1],
                 bounds[5] - bounds[2]) * 0.5
    if radius < 0.0001:
        raise ValueError("AutoSkirt Live Add: invalid sphere dimensions")

    def connect(source, destination, force=False):
        cmds.connectAttr(source, destination, force=force)

    def setting(name, value, minimum=None, maximum=None):
        args = dict(longName=suffix + name, attributeType="double",
                    defaultValue=float(value), keyable=True)
        if minimum is not None:
            args["minValue"] = float(minimum)
        if maximum is not None:
            args["maxValue"] = float(maximum)
        cmds.addAttr(ref, **args)
        return ref + "." + suffix + name

    def linear(node):
        for i in range(2):
            point = node + ".value[{}]".format(i)
            cmds.setAttr(point + ".value_Position", float(i))
            cmds.setAttr(point + ".value_FloatValue", float(i))
            cmds.setAttr(point + ".value_Interp", 1)

    # Single undo chunk: on a Maya command failure, restore the old DG.
    cmds.undoInfo(openChunk=True, chunkName="AutoSkirt Add Live Sub Item")
    changed = False
    try:
        # Stage: Additional Ref at the stored bind projection.
        ref_shape = cmds.createNode("follicle", name=subtag + "_Ref_FollicleShape")
        changed = True
        ref_transform = cmds.listRelatives(ref_shape, parent=True, fullPath=True)[0]
        ref_transform = cmds.rename(ref_transform, subtag + "_Ref_Follicle")
        ref_transform = cmds.parent(ref_transform, fol_group)[0]
        ref_shape = (cmds.listRelatives(ref_transform, shapes=True,
                     type="follicle", fullPath=True) or [None])[0]
        if not ref_shape:
            raise RuntimeError("AutoSkirt Live Add: new follicle shape missing")
        cmds.setAttr(ref_shape + ".visibility", 0)
        cmds.setAttr(ref_transform + ".inheritsTransform", 0)
        connect(surface[0] + ".local", ref_shape + ".inputSurface")
        connect(surface[0] + ".worldMatrix[0]", ref_shape + ".inputWorldMatrix")
        connect(ref_shape + ".outTranslate", ref_transform + ".translate")
        connect(ref_shape + ".outRotate", ref_transform + ".rotate")
        connect(root + ".equatorU", ref_shape + ".parameterU")
        v_attr = setting("RefV", sub_v, 0, 1)
        connect(v_attr, ref_shape + ".parameterV")
        marker = cmds.createNode("locator", name=subtag + "_Ref_MarkerShape",
                                 parent=ref_transform)
        for coordinate in "XYZ":
            cmds.setAttr(marker + ".localPosition" + coordinate, 0)
            connect(marker_size + ".outputX", marker + ".localScale" + coordinate)
        cmds.setAttr(marker + ".overrideEnabled", 1)
        cmds.setAttr(marker + ".overrideColor", 17)

        # Stage: Live and neutral distances, identical to the existing builder.
        spatial = cmds.createNode("distanceBetween", name=subtag + "_InfluenceDistance")
        connect(ref_transform + ".worldMatrix[0]", spatial + ".inMatrix1")
        connect(moving + ".worldMatrix[0]", spatial + ".inMatrix2")
        neutral = cmds.createNode("distanceBetween", name=subtag + "_NeutralDistance")
        connect(ref_transform + ".worldMatrix[0]", neutral + ".inMatrix1")
        connect(neutral_moving + ".worldMatrix[0]", neutral + ".inMatrix2")
        neutral_distance = float(cmds.getAttr(neutral + ".distance"))
        setting("NeutralDistance", neutral_distance, 0)
        pos = cmds.xform(ref_transform, query=True, worldSpace=True, rotatePivot=True)
        distances = []
        for other in other_refs:
            pivot = cmds.xform(other, query=True, worldSpace=True, rotatePivot=True)
            distances.append(math.sqrt(sum((float(a)-float(b))**2
                                           for a, b in zip(pos, pivot))))
        auto_distance = max(min(distances, default=radius), 0.001)
        setting("AutoMaxDistance", auto_distance, 0.001)
        effective = spec["maxDistance"] if spec["maxDistance"] > 0 else auto_distance
        if spec["minDistance"] >= effective:
            raise ValueError("AutoSkirt Live Add: Max Effect Range must be below "
                             "Max Distance ({:.3f})".format(effective))
        min_plug = setting("MinDistance", spec["minDistance"], 0)
        dist_plug = setting("MaxDistance", effective, 0.001)
        weight = cmds.createNode("remapValue", name=subtag + "_DistanceWeight")
        connect(spatial + ".distance", weight + ".inputValue")
        connect(min_plug, weight + ".inputMin")
        connect(dist_plug, weight + ".inputMax")
        cmds.setAttr(weight + ".outputMin", 1.0)
        cmds.setAttr(weight + ".outputMax", 0.0)
        linear(weight)

        # Stage: Angle, threshold, and the ORIGINAL bind-pose neutralU.
        start = setting("StartAngle", spec["startAngle"], 0, 180)
        angle = cmds.createNode("remapValue", name=subtag + "_AngleFromU")
        connect(cp_shape[0] + ".parameterU", angle + ".inputValue")
        cmds.setAttr(angle + ".inputMin", 0)
        cmds.setAttr(angle + ".inputMax", 1)
        cmds.setAttr(angle + ".outputMin", 180 if spec["reverseU"] else 0)
        cmds.setAttr(angle + ".outputMax", 0 if spec["reverseU"] else 180)
        linear(angle)
        clamp = cmds.createNode("clamp", name=subtag + "_AngleClamp")
        connect(angle + ".outValue", clamp + ".inputR")
        connect(start, clamp + ".minR")
        cmds.setAttr(clamp + ".maxR", 180)
        subtract = cmds.createNode("plusMinusAverage", name=subtag + "_SubtractStart")
        cmds.setAttr(subtract + ".operation", 2)
        connect(clamp + ".outputR", subtract + ".input1D[0]")
        connect(start, subtract + ".input1D[1]")
        raised = cmds.createNode("multiplyDivide", name=subtag + "_WeightedRaise")
        connect(subtract + ".output1D", raised + ".input1X")
        connect(weight + ".outValue", raised + ".input2X")
        neutral_u = float(cmds.getAttr(root + ".neutralU"))
        neutral_angle = 180.0 * ((1.0 - neutral_u)
                                 if spec["reverseU"] else neutral_u)
        neutral_weight = max(0.0, min(1.0, (effective-neutral_distance) /
                                      (effective-spec["minDistance"])))
        neutral_value = max(0.0, neutral_angle - spec["startAngle"]) * neutral_weight
        zero = cmds.createNode("plusMinusAverage", name=subtag + "_ZeroNeutral")
        cmds.setAttr(zero + ".operation", 2)
        connect(raised + ".outputX", zero + ".input1D[0]")
        cmds.setAttr(zero + ".input1D[1]", neutral_value)

        # Stage: Strength, AutoFollow, master, sign and per-Sub mute.
        strength = setting("Strength", spec["strength"], 0, 2)
        gain = cmds.createNode("multiplyDivide", name=subtag + "_AngleStrength")
        connect(zero + ".output1D", gain + ".input1X")
        connect(strength, gain + ".input2X")
        follower = cmds.createNode("multiplyDivide", name=subtag + "_AutoFollow")
        connect(gain + ".outputX", follower + ".input1X")
        connect(auto_follow, follower + ".input2X")
        master = cmds.createNode("multiplyDivide", name=subtag + "_Master")
        connect(follower + ".outputX", master + ".input1X")
        connect(root + ".autoSkirt", master + ".input2X")
        sign = setting("RotateSign", -1.0 if spec["invertRotate"] else 1.0, -1, 1)
        signed = cmds.createNode("multiplyDivide", name=subtag + "_Signed")
        connect(master + ".outputX", signed + ".input1X")
        connect(sign, signed + ".input2X")
        gate = cmds.createNode("multiplyDivide", name=subtag + "_MuteGate")
        connect(signed + ".outputX", gate + ".input1X")
        cmds.setAttr(gate + ".input2X", 1.0)
        gate_output = gate + ".outputX"

        # Stage: Preserve old output branches and extend only the matching axis.
        if route == "direct":
            connect(gate_output, output)
        elif route == "sum":
            used = cmds.getAttr(sum_node + ".input1D", multiIndices=True) or []
            next_index = max(used, default=-1) + 1
            connect(gate_output, sum_node + ".input1D[{}]".format(next_index))
        else:
            combined = cmds.createNode("plusMinusAverage", name=sum_node)
            connect(previous, combined + ".input1D[0]")
            connect(gate_output, combined + ".input1D[1]")
            connect(combined + ".output1D", output, force=True)

        if original:
            original["subItems"][slot].append(dict(spec))
            cmds.setAttr(system_root + ".patternData",
                         json.dumps(meta, ensure_ascii=False), type="string")
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if changed:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)
    return True


def _finish_sub_items(row, sync, window):
    """Save all Sub Item edits to JSON; keep the editor window open."""
    try:
        sync()
        _save(STATE["data"])
    except (ValueError, RuntimeError, OSError) as exc:
        cmds.warning("AutoSkirt Save Sub Items: {}".format(exc))
        return False
    print("AutoSkirt Sub Items: JSON saved; editor remains open.")
    return True


def _sub_item_ref_name(row, control, index):
    """Get the Ref transform for one Sub Item, including reopened rigs."""
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    controls = _controls(row)
    if control not in controls:
        raise ValueError("AutoSkirt: Driven not found in this Reader: " + control)
    slot = controls.index(control)
    meta = _meta_from_scene({"name": system})
    if meta:
        original = next((item for item in meta.get("data", {}).get("items", [])
                         if item.get("id") == rid), None)
        if original and control in original.get("joints", []):
            slot = original["joints"].index(control)
            if index == 0:
                reference = meta.get("refs", {}).get(rid, {}).get(control)
                if reference and reference[0] and cmds.objExists(reference[0]):
                    return reference[0]
    tag = "{}_{}_{:02d}".format(system, rid, slot + 1)
    if index == 0:
        return tag + "_Ref_Follicle"
    return "{}_Sub{:02d}_Ref_Follicle".format(tag, index + 1)


def _select_sub_item_ref(row, control, index, *args):
    """Select this Sub Item's Ref follicle, without changing its settings."""
    name = _sub_item_ref_name(row, control, index)
    matches = cmds.ls(name, long=True) or []
    if len(matches) != 1:
        cmds.warning("AutoSkirt: Ref not found or ambiguous: " + name)
        return False
    cmds.select(matches[0], replace=True)
    return matches[0]


def _edit_sub_items(row, *args):
    """Edit any number of axis/UV-direction responses per Driven."""
    controls = _controls(row)
    window = "NLTA_AutoSkirt_SubItems"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    window = cmds.window(window, title="AutoSkirt - Driven Sub Items", widthHeight=(550, 555))
    body = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    scroll = cmds.scrollLayout(parent=body, childResizable=True, height=460)
    holder = cmds.columnLayout(parent=scroll, adjustableColumn=True, rowSpacing=4)
    editor = {"window": window, "widgets": {}, "extraOffsets": {}}
    row["subEditor"] = editor
    # A built Auto value appears as a number, but remains 0 in JSON until edited.
    auto_display = {}
    ref_v_auto_display = {}
    manual_max_distance = set()
    manual_ref_v = set()
    axis = str(STATE.get("defaultAxis", "rotateZ"))[-1:].upper()
    for control in controls:
        row["subItems"].setdefault(control, _normalize_sub_items(
            None, axis, _settings(row, control)["startAngle"]))

    def sync():
        for control, widgets in editor["widgets"].items():
            shared_field = editor["extraOffsets"][control]
            shared_matrix = _parse_extra_matrix(
                cmds.scrollField(shared_field, query=True, text=True))
            captured = []
            for index, fields in enumerate(widgets):
                shown = float(cmds.floatSliderGrp(fields["distance"], query=True, value=True))
                key = (control, index)
                computed = auto_display.get(control, {}).get(index)
                # Explicit slider edits always win over rounded Auto display values.
                auto_unchanged = (shown == 0 or (key not in manual_max_distance and
                                  computed is not None and abs(shown - computed) <= 0.000501))
                if shown == 0: manual_max_distance.discard(key)
                if not auto_unchanged: auto_display.get(control, {}).pop(index, None)
                shown_ref_v = float(cmds.floatSliderGrp(fields["refV"], query=True, value=True))
                projected_v = ref_v_auto_display.get(control, {}).get(index)
                ref_v_unchanged = (key not in manual_ref_v and projected_v is not None and
                                   abs(shown_ref_v - projected_v) <= 0.000501)
                if not ref_v_unchanged: ref_v_auto_display.get(control, {}).pop(index, None)
                captured.append(_read_sub_item_fields(fields, auto_unchanged, ref_v_unchanged))
            if shared_matrix and captured:
                captured[0]["extraOffsetMatrix"] = shared_matrix
            row["subItems"][control] = _normalize_sub_items(captured, axis)

    def live(control, index, changed=None, *unused):
        try:
            if changed == "refV": manual_ref_v.add((control, index))
            if changed == "maxDistance": manual_max_distance.add((control, index))
            sync()
            if _apply_live_sub_item(row, control, index):
                # Entering 0 resets the value to Auto; show its resolved distance.
                spec = row["subItems"][control][index]
                if spec["maxDistance"] == 0:
                    resolved = _auto_max_distance_for_display(row, control, index)
                    if resolved is not None:
                        auto_display.setdefault(control, {})[index] = resolved
                        fields = editor["widgets"][control][index]
                        cmds.floatSliderGrp(fields["distance"], edit=True, value=resolved)
        except (ValueError, RuntimeError) as exc:
            cmds.warning("AutoSkirt Live: {}".format(exc))
            return False

    def pick_extra_offset(control, *unused):
        selection = cmds.ls(selection=True, objectsOnly=True) or []
        if len(selection) != 1:
            cmds.warning("AutoSkirt: select exactly one Extra Offset reference")
            return
        try:
            matrix = _capture_extra_transform(selection[0])
            cmds.scrollField(editor["extraOffsets"][control], edit=True,
                             text=_format_extra_matrix(matrix))
            sync()
            print("AutoSkirt: shared Extra Offset matrix captured for {}; reference can be deleted.".format(control))
        except (ValueError, RuntimeError) as exc:
            cmds.warning("AutoSkirt Extra Offset: " + str(exc))

    def clear_extra_offset(control, *unused):
        cmds.scrollField(editor["extraOffsets"][control], edit=True, text="")
        sync()

    def change_mute(control, index, widget, *unused):
        muted = bool(cmds.checkBox(widget, query=True, value=True))
        if not _set_sub_item_mute(row, control, index, muted):
            cmds.checkBox(widget, edit=True, value=False)

    def mirror_ref(control, index, *unused):
        try:
            sync()
            value, method = _get_mirror_ref_v(row, control, index)
            fields = editor["widgets"][control][index]
            manual_ref_v.add((control, index))
            cmds.floatSliderGrp(fields["refV"], edit=True, value=value)
            live(control, index)
            print("AutoSkirt Get Mirror Ref: {} Sub {:02d} V={:.4f} ({})".format(
                control, index + 1, value, method))
        except (ValueError, RuntimeError, IndexError) as exc:
            cmds.warning("AutoSkirt Get Mirror Ref: {}".format(exc))

    def add(control, *unused):
        try:
            sync()
            spec = _normalize_sub_items(None, axis)[0]
            index = len(row["subItems"][control])
            built = _build_live_added_sub_item(row, control, index, spec)
            row["subItems"][control].append(spec)
            draw()
            if built:
                if not _apply_live_sub_item(row, control, index):
                    cmds.warning("AutoSkirt: new Sub Item was built, but Live "
                                 "reconnection could not be verified")
                print("AutoSkirt: Sub {:02d} added Live for {}. "
                      "Use Save Sub Items to persist JSON.".format(index + 1, control))
        except (ValueError, RuntimeError, KeyError) as exc:
            cmds.warning("AutoSkirt Add Sub Item: {}".format(exc))

    def remove(control, index, *unused):
        sync()
        if len(row["subItems"][control]) <= 1:
            cmds.warning("AutoSkirt: at least one Sub Item is required")
            return
        shared_matrix = row["subItems"][control][0].get("extraOffsetMatrix")
        row["subItems"][control].pop(index)
        for sub in row["subItems"][control]:
            sub.pop("extraOffsetMatrix", None)
        if shared_matrix:
            row["subItems"][control][0]["extraOffsetMatrix"] = shared_matrix
        draw()

    def draw():
        for child in cmds.layout(holder, query=True, childArray=True) or []:
            cmds.deleteUI(child)
        editor["widgets"] = {}
        editor["extraOffsets"] = {}
        auto_display.clear()
        ref_v_auto_display.clear()
        manual_max_distance.clear()
        manual_ref_v.clear()
        for control in controls:
            frame = cmds.frameLayout(parent=holder, label=control, collapsable=True, marginWidth=6, marginHeight=4)
            column = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=4)
            editor["widgets"][control] = []
            shared_matrix = next((sub["extraOffsetMatrix"] for sub in row["subItems"][control]
                                  if sub.get("extraOffsetMatrix")), [])
            extra_row = cmds.rowLayout(parent=column, numberOfColumns=4,
                                       adjustableColumn=2,
                                       columnWidth4=(125, 285, 48, 48))
            cmds.text(parent=extra_row, label="Extra Offset Matrix", align="left")
            extra_field = cmds.scrollField(parent=extra_row, height=64, wordWrap=False,
                                           text=_format_extra_matrix(shared_matrix))
            cmds.button(parent=extra_row, label="Pick", width=45,
                        command=partial(pick_extra_offset, control))
            cmds.button(parent=extra_row, label="Clear", width=45,
                        command=partial(clear_extra_offset, control))
            editor["extraOffsets"][control] = extra_field
            cmds.setParent(column)
            cmds.text(parent=column, label="Shared by all Sub Item output channels", align="left")
            for index, sub in enumerate(row["subItems"][control]):
                item_col = cmds.columnLayout(parent=column, adjustableColumn=True, rowSpacing=5)
                first_row = cmds.rowLayout(parent=item_col, numberOfColumns=2,
                                            columnWidth2=(220, 135))
                reverse = cmds.checkBox(parent=first_row, label="Reverse U (1->0)",
                                         value=sub["reverseU"])
                muted = cmds.checkBox(parent=first_row, label="Mute",
                                      value=_read_sub_item_mute(row, control, index))
                cmds.checkBox(muted, edit=True,
                              changeCommand=partial(change_mute, control, index, muted))
                cmds.setParent(item_col)
                output_row = cmds.rowLayout(parent=item_col, numberOfColumns=4,
                                            columnWidth4=(82, 112, 75, 84))
                cmds.text(parent=output_row, label="Output Type", align="left")
                output_type = cmds.optionMenu(parent=output_row, width=108)
                for name in ("Rotate", "Translate"):
                    cmds.menuItem(parent=output_type, label=name)
                cmds.optionMenu(output_type, edit=True,
                                value=sub.get("outputType", "rotate").capitalize())
                cmds.text(parent=output_row, label="Axis", align="right")
                menu = cmds.optionMenu(parent=output_row, width=76)
                for name in "XYZ": cmds.menuItem(parent=menu, label=name)
                cmds.optionMenu(menu, edit=True, value=sub["axis"])
                cmds.setParent(item_col)
                invert = cmds.checkBox(parent=item_col, label="Invert Output",
                                       value=sub["invertRotate"])
                # Ref is an existing follicle transform, not a JSON setting.
                ref_node_row = cmds.formLayout(parent=item_col, height=28)
                ref_caption = cmds.text(parent=ref_node_row, label="Ref Node",
                                        align="left", width=73)
                ref_name = cmds.textField(parent=ref_node_row,
                                          text=_sub_item_ref_name(row, control, index),
                                          editable=False)
                ref_select = cmds.button(
                    parent=ref_node_row, label="Select", width=66,
                    command=partial(_select_sub_item_ref, row, control, index))
                cmds.formLayout(ref_node_row, edit=True,
                    attachForm=[(ref_caption, "left", 3), (ref_caption, "top", 6),
                                (ref_name, "top", 2), (ref_name, "bottom", 2),
                                (ref_select, "top", 2), (ref_select, "bottom", 2),
                                (ref_select, "right", 3)],
                    attachControl=[(ref_name, "left", 4, ref_caption),
                                   (ref_name, "right", 4, ref_select)])
                cmds.setParent(item_col)

                # Single-column slider controls with exact numeric input.
                start = cmds.floatSliderGrp(parent=item_col, label="Start Angle", field=True,
                                            minValue=0, maxValue=179.99, fieldMinValue=0,
                                            fieldMaxValue=179.99, value=sub["startAngle"], precision=2,
                                            columnWidth3=(145, 68, 285), adjustableColumn3=3)
                strength_field = cmds.floatSliderGrp(parent=item_col, label="Angle Strength", field=True,
                                                      minValue=0, maxValue=2, fieldMinValue=0,
                                                      fieldMaxValue=2, value=sub["strength"], precision=8,
                                                      columnWidth3=(135, 125, 235), adjustableColumn3=3)
                projected_v = _ref_v_for_display(row, control, index) if sub["refV"] is None else None
                shown_ref_v = projected_v if projected_v is not None else (
                    row["referenceV"].get(control, 0.5) if sub["refV"] is None else sub["refV"])
                if sub["refV"] is None:
                    ref_v_auto_display.setdefault(control, {})[index] = shown_ref_v
                ref_row = cmds.rowLayout(parent=item_col, numberOfColumns=2,
                                         columnWidth2=(392, 108))
                ref_v_field = cmds.floatSliderGrp(parent=ref_row, label="Ref V", field=True,
                                                   minValue=0, maxValue=1, fieldMinValue=0,
                                                   fieldMaxValue=1, value=shown_ref_v, precision=3,
                                                   columnWidth3=(136, 68, 180), adjustableColumn3=3)
                cmds.button(parent=ref_row, label="Get Mirror Ref", width=102,
                            command=partial(mirror_ref, control, index))
                cmds.setParent(item_col)
                resolved = _auto_max_distance_for_display(row, control, index) if sub["maxDistance"] == 0 else None
                if resolved is not None: auto_display.setdefault(control, {})[index] = resolved
                shown_max = resolved if resolved is not None else sub["maxDistance"]
                slider_max = max(1.0, shown_max, sub["minDistance"] * 1.5)
                field_limit = max(1000000.0, slider_max * 2)
                min_distance_field = cmds.floatSliderGrp(parent=item_col, label="Max Effect Range", field=True,
                                                          minValue=0, maxValue=slider_max, fieldMinValue=0,
                                                          fieldMaxValue=field_limit, value=sub["minDistance"],
                                                          precision=3, columnWidth3=(145, 68, 285),
                                                          adjustableColumn3=3)
                distance_field = cmds.floatSliderGrp(parent=item_col, label="Max Distance", field=True,
                                                      minValue=0, maxValue=slider_max * 2, fieldMinValue=0,
                                                      fieldMaxValue=field_limit, value=shown_max,
                                                      precision=3, columnWidth3=(145, 68, 285),
                                                      adjustableColumn3=3)
                # Keep both Sub Item actions together.
                actions = cmds.rowLayout(parent=item_col, numberOfColumns=2, columnWidth2=(145, 145))
                cmds.button(parent=actions, label="Remove Sub Item", width=140, height=24,
                            command=partial(remove, control, index))
                cmds.button(parent=actions, label="+ Add Sub Item", width=140, height=24,
                            command=partial(add, control))
                cmds.setParent(item_col)
                editor["widgets"][control].append(
                    {"axis": menu, "outputType": output_type, "reverse": reverse, "invert": invert, "mute": muted,
                     "refNode": ref_name, "strength": strength_field, "start": start, "refV": ref_v_field,
                     "distance": distance_field, "minDistance": min_distance_field})
                # Numeric settings are live; output type, axis and item count require a fresh Run.
                cmds.checkBox(reverse, edit=True,
                              changeCommand=partial(live, control, index))
                cmds.checkBox(invert, edit=True,
                              changeCommand=partial(live, control, index))
                # changeCommand fires on slider release; dragCommand is intentionally omitted.
                for field, widget in (("startAngle", start), ("strength", strength_field),
                                      ("refV", ref_v_field), ("minDistance", min_distance_field),
                                      ("maxDistance", distance_field)):
                    cmds.floatSliderGrp(widget, edit=True,
                                       changeCommand=partial(live, control, index, field))
                cmds.setParent(column)
            cmds.setParent(holder)

    def finish(*unused):
        return _finish_sub_items(row, sync, window)

    editor["sync"] = sync
    editor["refresh"] = draw
    draw()
    cmds.text(parent=body, label="Sliders apply Live on release. Strength: 1 = normal; Max Distance: 0 = Auto.", align="left")
    cmds.text(parent=body, label="Output Type / Axis / shared Extra Offset: Save JSON, then Run on a clean scene to rewire.", align="left")
    cmds.button(parent=body, label="Restore from JSON + Live", height=28,
                command=lambda *unused: _restore_json_live(
                    STATE["data"], STATE["listUI"],
                    cmds.textField(row["id"], query=True, text=True).strip()))
    cmds.button(parent=body, label="Save Sub Items", height=28,
                command=finish)
    cmds.showWindow(window)

def _controls(row):
    raw = cmds.scrollField(row["controls"], query=True, text=True)
    result = [name.strip() for name in raw.splitlines() if name.strip()]
    if not result or len(result) != len(set(result)):
        raise ValueError("AutoSkirt: each reader requires unique Driven controls")
    return result


def _settings(row, control):
    return row["settings"].setdefault(control, {"startAngle": 10.0})


def _add_row(parent, record=None):
    record = record or {}
    raw_controls = record.get("joints", [])
    if isinstance(raw_controls, str):
        raw_controls = [x.strip() for x in raw_controls.splitlines() if x.strip()]
    saved_subs = record.get("subItems", [])
    settings = {c: {"startAngle": 10.0} for c in raw_controls}
    subs = {}
    for i, control in enumerate(raw_controls):
        entries = saved_subs[i] if i < len(saved_subs) else None
        subs[control] = _normalize_sub_items(entries)
    saved_ref_values = record.get("refV", [])
    row = {"settings": settings, "subItems": subs,
           "referenceV": {control: float(v) for control, v in zip(raw_controls, saved_ref_values)}}
    frame = cmds.frameLayout(parent=parent, label="Pose Reader", collapsable=True,
                             marginHeight=5, marginWidth=5)
    col = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    row["frame"] = frame
    rid = record.get("id") or "Knee{}".format(len(STATE["rows"]) + 1)
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    row["id"] = _line_field(col, "Reader ID", rid, False)
    row["sphere"] = _line_field(col, "Sphere Name",
                                record.get("sphere") or system + "_" + rid + "_Sphere", False)
    row["createSphere"] = cmds.checkBox(parent=col, label="Create Sphere",
                                         value=bool(record.get("createSphere", True)))
    row["parent"] = _line_field(col, "Parent", record.get("parent", ""))
    row["start"] = _line_field(col, "Start", record.get("start", ""))
    row["end"] = _line_field(col, "End", record.get("end", ""))
    for key, label, default in (("radiusScale", "Sphere Radius Scale", 1.0),
                                ("tiltAwayDegrees", "Tilt Away (deg)", 10.0),
                                ("follicleSize", "Follicle Display Size", 1.0)):
        line = cmds.rowLayout(parent=col, numberOfColumns=2, columnWidth2=(120, 165))
        cmds.text(parent=line, label=label)
        row[key] = cmds.floatField(parent=line, value=float(record.get(key, default)),
                                   precision=3, width=100)
        cmds.setParent("..")
    def toggle_sphere(*unused):
        enabled = cmds.checkBox(row["createSphere"], query=True, value=True)
        for key in ("radiusScale", "tiltAwayDegrees"):
            cmds.floatField(row[key], edit=True, enable=enabled)
    cmds.checkBox(row["createSphere"], edit=True, changeCommand=toggle_sphere)
    cmds.floatField(row["follicleSize"], edit=True, minValue=0.01, maxValue=100,
                    changeCommand=partial(_live_follicle_size, row))
    toggle_sphere()
    line = cmds.rowLayout(parent=col, numberOfColumns=3,
                          adjustableColumn=2, columnWidth3=(115, 180, 74))
    cmds.text(parent=line, label="Driven Controls")
    row["controls"] = cmds.scrollField(parent=line, height=75,
                                       text="\n".join(raw_controls), wordWrap=False)
    actions = cmds.columnLayout(parent=line, adjustableColumn=True, rowSpacing=4)
    cmds.button(parent=actions, label="Pick All", width=68, height=34,
                command=partial(_pick_controls, row["controls"]))
    cmds.button(parent=actions, label="Add", width=68, height=34,
                command=partial(_add_selected_drivens, row))
    cmds.setParent(col)
    line = cmds.rowLayout(parent=col, numberOfColumns=3, columnWidth3=(115, 115, 115))
    cmds.button(parent=line, label="Edit Sub Items", width=113,
                command=partial(_edit_sub_items, row))
    cmds.button(parent=line, label="Mirror Reader", width=113,
                command=partial(_mirror_row, row))
    cmds.button(parent=line, label="Remove Reader", width=113,
                command=partial(_remove_row, row))
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
    STATE["rows"].append(row)
    return row


def _remove_row(row, *args):
    if row in STATE["rows"]:
        STATE["rows"].remove(row)
    if cmds.layout(row["frame"], exists=True):
        cmds.deleteUI(row["frame"])

def _read_ui():
    top = STATE["top"]
    if not top:
        raise RuntimeError("AutoSkirt: form is not open")
    cfg = {"version": 2,
           "name": cmds.textField(top["name"], query=True, text=True).strip(),
           "group": cmds.textField(top["group"], query=True, text=True).strip(),
           "items": []}
    for row in STATE["rows"]:
        editor = row.get("subEditor")
        if editor and callable(editor.get("sync")):
            if cmds.window(editor["window"], exists=True):
                editor["sync"]()
            else:
                row.pop("subEditor", None)
        controls = _controls(row)
        reader = {
            "mode": "autoSphere",
            "id": cmds.textField(row["id"], query=True, text=True).strip(),
            "sphere": cmds.textField(row["sphere"], query=True, text=True).strip(),
            "createSphere": bool(cmds.checkBox(row["createSphere"], query=True, value=True)),
            "parent": cmds.textField(row["parent"], query=True, text=True).strip(),
            "start": cmds.textField(row["start"], query=True, text=True).strip(),
            "end": cmds.textField(row["end"], query=True, text=True).strip(),
            "radiusScale": float(cmds.floatField(row["radiusScale"], query=True, value=True)),
            "tiltAwayDegrees": float(cmds.floatField(row["tiltAwayDegrees"], query=True, value=True)),
            "follicleSize": float(cmds.floatField(row["follicleSize"], query=True, value=True)),
            "equatorU": 0.5,
            "joints": controls,
            "subItems": [_normalize_sub_items(row["subItems"].get(c)) for c in controls],
            "refV": ([row["referenceV"][c] for c in controls]
                     if all(c in row["referenceV"] for c in controls) else [])}
        if not all(reader.get(key) for key in ("id", "sphere", "parent", "start", "end")):
            raise ValueError("AutoSkirt: Reader ID, Sphere Name, Parent, Start and End required")
        cfg["items"].append(reader)
    if not cfg["items"]:
        raise ValueError("AutoSkirt: add at least one Pose Reader")
    return cfg


def _save(data, *args):
    value = _read_ui()
    NLTA_General.writeJsonFile(_data_path(data), value)
    return value

def _scene_root(value):
    return value["name"] + "_System"


def _meta_from_scene(value):
    root = _scene_root(value)
    if not cmds.objExists(root) or not cmds.attributeQuery("patternData", node=root, exists=True):
        return None
    encoded = cmds.getAttr(root + ".patternData")
    try:
        saved = json.loads(encoded)
    except (TypeError, ValueError):
        return None
    return saved if isinstance(saved, dict) else None

def _write_scene_meta(root, meta):
    cmds.addAttr(root, longName="patternData", dataType="string")
    cmds.setAttr(root + ".patternData", json.dumps(meta, ensure_ascii=False), type="string")

def Load(data, listUI, *args):
    # Opening the AutoSkirt form closes its independent Sub Item editor.
    if cmds.window("NLTA_AutoSkirt_SubItems", exists=True): cmds.deleteUI("NLTA_AutoSkirt_SubItems")
    for child in cmds.layout(listUI, query=True, childArray=True) or []: cmds.deleteUI(child)
    STATE["top"], STATE["rows"], STATE["data"], STATE["listUI"] = {}, [], data, listUI
    # The JSON is authoritative for the Form. Built Maya attributes are only
    # read for Auto display and optional export baking, never to replace saved edits.
    config = _get_data(data)
    frame = cmds.frameLayout(parent=listUI, label="AutoSkirt Settings",
                             collapsable=True, marginWidth=5, marginHeight=5)
    col = cmds.columnLayout(parent=frame, adjustableColumn=True)
    STATE["top"]["name"] = _line_field(col, "System Name", config.get("name", "AutoSkirt"), False)
    STATE["top"]["group"] = _line_field(col, "Contain", config.get("group", "RigUtil"))
    cmds.setParent("..")
    cmds.setParent("..")
    holder = cmds.columnLayout(parent=listUI, adjustableColumn=True)
    STATE["holder"] = holder
    for entry in config["items"]:
        _add_row(holder, entry)
    if not config["items"]:
        _add_row(holder)


def _restore_json_live(data, list_ui, reader_id=None, *args):
    """Discard unsaved widget edits, reload disk JSON, and reapply built Live.

    This never rewrites the source JSON or rebuilds a rig. The active Sub Item
    editor is reopened for the same Reader so restored values are visible.
    """
    saved = _get_data(data)
    if not saved.get("items"):
        cmds.warning("AutoSkirt Restore: no saved Pose Readers in JSON.")
        return False

    reopen = reader_id
    if reopen is None and cmds.window("NLTA_AutoSkirt_SubItems", exists=True):
        for current in STATE.get("rows", []):
            editor = current.get("subEditor")
            if editor and cmds.window(editor["window"], exists=True):
                reopen = cmds.textField(current["id"], query=True, text=True).strip()
                break

    # Load intentionally discards the old Sub Item editor without syncing it.
    Load(data, list_ui)
    updated, skipped = 0, []
    target = None
    for row in STATE["rows"]:
        rid = cmds.textField(row["id"], query=True, text=True).strip()
        if rid == reopen:
            target = row
        try:
            _live_follicle_size(row)
        except (RuntimeError, ValueError) as exc:
            skipped.append("{} display: {}".format(rid, exc))
        for control in _controls(row):
            for index in range(len(row["subItems"].get(control, []))):
                try:
                    if _apply_live_sub_item(row, control, index,
                                            restore_auto_ref=True):
                        updated += 1
                    else:
                        skipped.append("{} / {} Sub {:02d}: no matching built "
                                       "network or axis differs".format(
                                           rid, control, index + 1))
                except (RuntimeError, ValueError, KeyError) as exc:
                    skipped.append("{} / {} Sub {:02d}: {}".format(
                        rid, control, index + 1, exc))
    if target is not None:
        _edit_sub_items(target)
    print("AutoSkirt Restore JSON + Live: {} Sub Item(s) updated; "
          "{} skipped. JSON unchanged.".format(updated, len(skipped)))
    if skipped:
        for message in skipped:
            print("[AutoSkirt Restore] " + message)
        cmds.warning("AutoSkirt Restore: {} item(s) have no matching "
                     "built graph; see Script Editor.".format(len(skipped)))
    return {"updated": updated, "skipped": skipped}


def _add_empty(*args):
    _add_row(STATE["holder"])


def _read_items(config):
    return [(entry["id"], entry) for entry in config["items"]]


def _build_auto_sphere_configuration(configuration):
    """Build independent Start/End auto readers with shared Scene Pattern metadata."""
    name = configuration.get("name", "AutoSkirt")
    group = configuration.get("group", "RigUtil")
    readers = _read_items(configuration)
    # Stage: Resolve Reader inputs without feedback to Parent.
    for item_id, spec in readers:
        parent_path = cmds.ls(spec["parent"], long=True)[0]
        end_path = cmds.ls(spec["end"], long=True)[0]
        driven_paths = [cmds.ls(control, long=True)[0] for control in spec["joints"]]
        if (parent_path == end_path or parent_path.startswith(end_path + "|")
                or any(parent_path == driven or parent_path.startswith(driven + "|")
                       for driven in driven_paths)):
            raise ValueError("{}: Parent would create a dependency cycle".format(item_id))
    # Stage: Create the system container.
    container = (cmds.ls(group, type="transform") or [cmds.createNode("transform", name=group)])[0]
    system_root = cmds.createNode("transform", name=name + "_System", parent=container)
    result = {"root": system_root, "items": {}, "driven": {},
              "drivenReaders": {}, "masters": {}}
    for item_id, spec in readers:
        original_controls = list(spec["joints"])
        auto = AutoSkirtAutoSphere(
            parent=spec["parent"], start=spec["start"], end=spec["end"], drivens=original_controls,
            prefix=name + "_" + item_id,
            sphere_name=spec.get("sphere") or name + "_" + item_id + "_Sphere",
            create_sphere=bool(spec.get("createSphere", True)), sub_items=spec.get("subItems"),
            follicle_size=float(spec.get("follicleSize", 1.0)),
            radius_scale=float(spec.get("radiusScale", 1.0)),
            tilt_away_degrees=float(spec.get("tiltAwayDegrees", 20.0)),
            output_axis=str(spec.get("axis", configuration.get("axis", "rotateZ")))[-1],
            equator_u=0.5,
            raise_start_angle=float(spec.get("raiseStartAngle", 10.0)),
            ref_values=list(spec["refV"]) if spec.get(
                "_export_baked_refs", configuration.get("_export_baked_refs", False)) else None)
        cmds.parent(auto["root"], system_root, absolute=True)
        spec["sphere"] = auto["sphere"]
        info = {"parent": auto["parent"], "sphere": auto["sphere"],
                "sphereFrame": auto["sphereFrame"],
                "radius": auto["radius"], "tiltAwayDegrees": auto["tiltAwayDegrees"],
                "drivenCentroid": auto["drivenCentroid"],
                "nearestDrivenDistance": auto["nearestDrivenDistance"],
                "follicleSize": float(spec.get("follicleSize", 1.0)),
                "referenceUV": {}, "follicles": {}, "outputs": {}, "destinations": {}}
        moving = cmds.ls(auto["movingFollicle"].rsplit("|", 1)[-1], long=True)[0]
        for original_control, driven_info in zip(original_controls, auto["driven"]):
            reference = cmds.ls(driven_info["ref"].rsplit("|", 1)[-1], long=True)[0]
            info["referenceUV"][original_control] = (
                auto["equatorU"], driven_info["refV"])
            info["follicles"][original_control] = (reference, moving)
            info["outputs"][original_control] = driven_info["outputs"]
            info["destinations"][original_control] = driven_info["outputs"]
            # Keep the first entry for legacy callers and retain every
            # independent Reader that contributes to this one control.
            result["driven"].setdefault(original_control, driven_info)
            result["drivenReaders"].setdefault(original_control, {})[item_id] = driven_info
        result["items"][item_id] = info
        result["masters"][item_id] = auto["root"].rsplit("|", 1)[-1] + ".autoSkirt"
    result["master"] = next(iter(result["masters"].values()))
    return result

def Run(data, *args):
    config = _get_data(data)
    result = _build_auto_sphere_configuration(config)
    # Stage: Persist projected Ref values and built reader metadata.
    refs = {}
    for reader in config["items"]:
        rid = reader["id"]
        ref_positions = result["items"][rid]["referenceUV"]
        reader["refV"] = [ref_positions[control][1] for control in reader["joints"]]
        refs[rid] = {}
        for control, (transform, _) in result["items"][rid]["follicles"].items():
            shape = cmds.listRelatives(transform, shapes=True, type="follicle", fullPath=True)[0]
            refs[rid][control] = [transform, shape]
    NLTA_General.writeJsonFile(_data_path(data), config)
    _write_scene_meta(result["root"], {"data": config, "refs": refs})
    cmds.select(clear=True)
    return result


def _run_from_form(data, *args):
    _save(data)
    result = Run(data)
    # Keep projected Ref values available if Sub Items are saved without reopening the Form.
    readers = {item["id"]: item for item in _get_data(data)["items"]}
    for row in STATE["rows"]:
        rid = cmds.textField(row["id"], query=True, text=True).strip()
        item = readers.get(rid, {})
        row["referenceV"] = dict(zip(item.get("joints", []), item.get("refV", [])))
        editor = row.get("subEditor")
        if editor and cmds.window(editor["window"], exists=True):
            editor["refresh"]()
    return result

def _get_built_data(config, bake_ref_v=False):
    """Read Live settings, preserving Auto defaults unless baking export Ref V."""
    result = json.loads(json.dumps(config))
    meta = _meta_from_scene(config)
    if not meta:
        return result
    refs = meta.get("refs", {})
    for item in result["items"]:
        rid = item["id"]
        captured = next((x for x in meta["data"].get("items", []) if x["id"] == rid), {})
        item["refV"] = list(captured.get("refV", []))
        for index, control in enumerate(item["joints"]):
            reference = refs.get(rid, {}).get(control)
            if not reference or not cmds.objExists(reference[0]):
                continue
            node = reference[0]
            if cmds.objExists(node + ".refV"):
                item["refV"][index] = float(cmds.getAttr(node + ".refV"))
            for sub_index, sub in enumerate(item["subItems"][index], 1):
                prefix = "sub{:02d}".format(sub_index)
                source_subs = captured.get("subItems", [])
                original = (source_subs[index][sub_index - 1]
                            if index < len(source_subs)
                            and sub_index <= len(source_subs[index]) else {})
                mapping = {
                    "maxDistance": node + "." + prefix + "MaxDistance",
                    "minDistance": node + "." + prefix + "MinDistance",
                    "strength": node + "." + prefix + "Strength",
                    "refV": node + (".refV" if sub_index == 1 else "." + prefix + "RefV"),
                    "startAngle": node + (".raiseStartAngle" if sub_index == 1 else "." + prefix + "StartAngle")}
                for key, plug in mapping.items():
                    # Saved UI edits take priority over an older built rig.
                    if (key in original and sub.get(key) != original[key]) or (
                            key not in original and sub.get(key) is not None):
                        continue
                    if not cmds.objExists(plug):
                        continue
                    live_value = float(cmds.getAttr(plug))
                    if key == "maxDistance" and original:
                        auto_plug = node + (".autoMaxDistance" if sub_index == 1
                                            else "." + prefix + "AutoMaxDistance")
                        if (original.get("maxDistance", 0) == 0
                                and cmds.objExists(auto_plug)
                                and abs(live_value -
                                        max(float(cmds.getAttr(auto_plug)), 0.001)) < 1e-5):
                            live_value = 0.0
                    if key == "refV" and original:
                        if original.get("refV") is None and index < len(captured.get("refV", [])):
                            projected = float(captured["refV"][index])
                            if abs(live_value - projected) < 1e-5 and not (
                                    bake_ref_v and sub_index > 1):
                                live_value = None
                    sub[key] = live_value
                angle_plug = "{}_{}_{:02d}_Sub{:02d}_AngleFromU.outputMin".format(
                    result["name"], rid, index + 1, sub_index)
                if sub.get("reverseU", False) == original.get("reverseU", False) and cmds.objExists(angle_plug):
                    sub["reverseU"] = float(cmds.getAttr(angle_plug)) > 90
                sign_plug = (node + ".rotateSign" if sub_index == 1
                             else node + "." + prefix + "RotateSign")
                if sub.get("invertRotate", False) == original.get("invertRotate", False) and cmds.objExists(sign_plug):
                    sub["invertRotate"] = float(cmds.getAttr(sign_plug)) < 0
    return result

def _compact_autoskirt_export_source(source):
    """Fold exported multiline append({...}), append(dict(...)), and return dict(...)."""
    lines = source.splitlines()
    tree = ast.parse(source)

    def is_dict_call(value):
        return (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == "dict")

    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Attribute) and call.func.attr == "append"
                    and len(call.args) == 1 and
                    (isinstance(call.args[0], ast.Dict) or is_dict_call(call.args[0]))):
                matches.append(node)
        elif isinstance(node, ast.Return) and is_dict_call(node.value):
            matches.append(node)

    for node in sorted(matches, key=lambda item: item.lineno, reverse=True):
        if node.end_lineno <= node.lineno:
            continue
        indentation = lines[node.lineno - 1][:len(lines[node.lineno - 1]) -
                                              len(lines[node.lineno - 1].lstrip())]
        compact = ast.unparse(node)
        if "\n" not in compact:
            lines[node.lineno - 1:node.end_lineno] = [indentation + compact]
    # Stage: Fold uncomplicated multiline Maya calls while preserving AST.
    import io
    import tokenize
    preliminary = "\n".join(lines)
    parsed = ast.parse(preliminary)
    lines = preliminary.splitlines()
    commented = {token.start[0] for token in tokenize.generate_tokens(io.StringIO(preliminary).readline)
                 if token.type == tokenize.COMMENT}
    maya_calls = []
    for node in ast.walk(parsed):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return)):
            continue
        if node.end_lineno <= node.lineno or any(
                line in commented for line in range(node.lineno, node.end_lineno + 1)):
            continue
        if not any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                   and isinstance(child.func.value, ast.Name)
                   and child.func.value.id == "cmds" for child in ast.walk(node)):
            continue
        compact = ast.unparse(node)
        if "\n" in compact:
            continue
        first, last = node.lineno - 1, node.end_lineno - 1
        if lines[first][:node.col_offset].strip() or lines[last][node.end_col_offset:].strip():
            continue
        maya_calls.append((first, last, lines[first][:node.col_offset] + compact))
    for first, last, compact in sorted(maya_calls, reverse=True):
        lines[first:last + 1] = [compact]
    compacted = "\n".join(lines)
    if ast.dump(ast.parse(compacted), include_attributes=False) != ast.dump(tree, include_attributes=False):
        return source
    return compacted


def ExportPython(data, *args):
    config = _get_data(data) if data.get("_batch_export_from_saved") else _save(data)
    payload = _get_built_data(config, bake_ref_v=True)
    meta = _meta_from_scene(config) or {}
    built_refs = meta.get("refs", {})
    # A newly mirrored reader must project V even if the original reader is built.
    for reader in payload["items"]:
        rid = reader["id"]
        refs = built_refs.get(rid, {})
        reader["_export_baked_refs"] = bool(
            len(reader.get("refV", [])) == len(reader["joints"]) and
            all(control in refs for control in reader["joints"]))
    payload["_export_baked_refs"] = False
    # Keep the original compact Python and only the short stage notes.
    sources = (_read_items, AutoSkirtAutoSphere, _build_auto_sphere_configuration)
    blocks = []
    for fn in sources:
        lines = inspect.getsource(fn).rstrip().splitlines()
        cleaned = "\n".join(line.rstrip() for line in lines
                            if ((not line.lstrip().startswith("#")
                                 or line.lstrip().startswith("# Stage:"))
                                and not (line.strip().startswith('"""')
                                         and line.strip().endswith('"""'))))
        blocks.append(_compact_autoskirt_export_source(cleaned))
    source = "\n".join("    " + line if line.strip() else line for line in "\n\n".join(blocks).splitlines())
    values = repr(payload)
    script = ("def main():\n"
              "    import re\n    import math\n    import maya.cmds as cmds\n\n"
              "    AUTO_SKIRT_DATA = " + values + "\n\n"
              + source + "\n\n"
              + "    _build_auto_sphere_configuration(AUTO_SKIRT_DATA)\n\n"
              + 'if __name__ == "__main__":\n    main()\n')
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(_data_path(data)), filename)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(script)
    return output


def OpenExportFolder(data, *args):
    directory = os.path.dirname(_data_path(data))
    if os.path.isdir(directory):
        os.startfile(directory)
    else:
        cmds.warning("AutoSkirt: export directory does not exist: " + directory)

def Form(data, *args):
    if cmds.window("NLTA_AutoSkirt_SubItems", exists=True): cmds.deleteUI("NLTA_AutoSkirt_SubItems")
    ui = NLTA_General.LoadModule("Scene_Form").Create(data)
    buttons = ui["buttonUI"]
    list_ui = ui["listUI"]
    cmds.rowColumnLayout(parent=buttons, numberOfColumns=4)
    cmds.button(label="Add", width=80, command=_add_empty)
    cmds.button(label="Save", width=80, command=partial(_save, data))
    cmds.button(label="Run", width=80, command=partial(_run_from_form, data))
    export_button = cmds.button(label="Export Py", width=95,
                                command=partial(ExportPython, data))
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", command=partial(OpenExportFolder, data))
    cmds.setParent("..")
    cmds.button(parent=buttons, label="Restore from JSON + Live", height=30,
                command=lambda *unused: _restore_json_live(data, list_ui))
    Load(data, list_ui)

def AutoSkirtAutoSphere(start=None, end=None, drivens=None, prefix="AS_AUTO", radius=None,
        output_axis="Z", sphere_follow=True,
        equator_u=0.5, raise_start_angle=10.0, radius_scale=1.0,
        ref_values=None, tilt_away_degrees=20.0, sphere_name=None,
        sub_items=None, parent=None, create_sphere=True, follicle_size=1.0):
    import math
    import re
    import maya.cmds as cmds

    def vec_len(v):
        return math.sqrt(sum(float(x) * float(x) for x in v))

    def distance(a, b):
        return vec_len([float(x) - float(y) for x, y in zip(a, b)])

    def shape_of(transform, shape_type):
        return cmds.listRelatives(transform, shapes=True, noIntermediate=True,
                                  fullPath=True, type=shape_type)[0]

    def connect(source, destination):
        cmds.connectAttr(source, destination)

    def set_linear(remap):
        for i, value in enumerate((0.0, 1.0)):
            node = remap + ".value[{}]".format(i)
            cmds.setAttr(node + ".value_Position", value)
            cmds.setAttr(node + ".value_FloatValue", value)
            cmds.setAttr(node + ".value_Interp", 1)

    def make_follicle(name, surface_shape, group, u=None, v=None,
                      u_source=None, v_source=None):
        follicle_shape = cmds.createNode("follicle", name=name + "Shape")
        transform = (cmds.listRelatives(follicle_shape, parent=True,
                                        fullPath=True) or [None])[0]
        transform = cmds.rename(transform, name)
        transform = cmds.parent(transform, group)[0]
        follicle_shape = shape_of(transform, "follicle")
        # Stage: Hide the native follicle drawing; use one locator shape for every Ref.
        cmds.setAttr(follicle_shape + ".visibility", 0)
        cmds.setAttr(transform + ".inheritsTransform", 0)
        connect(surface_shape + ".local", follicle_shape + ".inputSurface")
        connect(surface_shape + ".worldMatrix[0]", follicle_shape + ".inputWorldMatrix")
        connect(follicle_shape + ".outTranslate", transform + ".translate")
        connect(follicle_shape + ".outRotate", transform + ".rotate")
        if u_source:
            connect(u_source, follicle_shape + ".parameterU")
        else:
            cmds.setAttr(follicle_shape + ".parameterU", float(u))
        if v_source:
            connect(v_source, follicle_shape + ".parameterV")
        else:
            cmds.setAttr(follicle_shape + ".parameterV", float(v))
        return transform, follicle_shape

    def marker(transform, color, label):
        # All follicle markers have the same locator geometry and shared size.
        mark = cmds.createNode("locator", name=label + "_MarkerShape", parent=transform)
        for axis in "XYZ":
            cmds.setAttr(mark + ".localPosition" + axis, 0)
            connect(marker_size + ".outputX", mark + ".localScale" + axis)
        cmds.setAttr(mark + ".overrideEnabled", 1)
        cmds.setAttr(mark + ".overrideColor", color)
        return mark

    def add_setting(node, name, default, minimum=None, maximum=None):
        options = dict(longName=name, attributeType="double",
                       defaultValue=float(default), keyable=True)
        if minimum is not None:
            options["minValue"] = float(minimum)
        if maximum is not None:
            options["maxValue"] = float(maximum)
        cmds.addAttr(node, **options)
        return node + "." + name

    def normalized(value, low, high):
        return max(0.0, min(1.0, (float(value) - low) / (high - low)))

    def rig_offset(driven, name):
        world_matrix = cmds.xform(driven, query=True, worldSpace=True, matrix=True)
        old_parent = (cmds.listRelatives(driven, parent=True, fullPath=True) or [None])[0]
        # Space preserves original world alignment, while DrivenOffset stays zeroed.
        space = cmds.createNode("transform", name=name + "_Space")
        cmds.xform(space, worldSpace=True, matrix=world_matrix)
        if old_parent:
            space = cmds.parent(space, old_parent, absolute=True)[0]
        offset = cmds.createNode("transform", name=name + "_DrivenOffset", parent=space)
        new_driven = cmds.parent(driven, offset, absolute=True)[0]
        new_driven = cmds.ls(new_driven, long=True)[0]
        return space, offset, new_driven

    def current_driven(offset):
        return cmds.listRelatives(offset, children=True, fullPath=True)[0]

    def add_extra_offset(space, subtag, saved_matrix):
        # Stage: One independent reference-space pivot per Extra Offset Sub Item.
        original_parent = (cmds.listRelatives(space, parent=True, fullPath=True) or [None])[0]
        extra_offset = cmds.createNode("transform", name=subtag + "_autoskirtExtraTransformOffset")
        cmds.xform(extra_offset, worldSpace=True, matrix=saved_matrix)
        if original_parent:
            extra_offset = cmds.parent(extra_offset, original_parent, absolute=True)[0]
        extra_group = cmds.createNode(
            "transform", name=subtag + "_autoskirtExtraTransform", parent=extra_offset)
        space = cmds.parent(space, extra_group, absolute=True)[0]
        return space, extra_offset, extra_group

    # Stage: Resolve the bind-pose objects and compute Reader radius.
    if parent is None and start is None and end is None and drivens is None:
        parent, start, end, *drivens = cmds.ls(selection=True, long=True, objectsOnly=True)
    if isinstance(drivens, str):
        drivens = [drivens]
    paths = [cmds.ls(node, long=True)[0] for node in [parent, start, end] + list(drivens)]
    parent, start, end, drivens = paths[0], paths[1], paths[2], paths[3:]
    output_axis = str(output_axis).upper()[-1]
    prefix = re.sub(r"[^A-Za-z0-9_]", "_", str(prefix)).strip("_") or "AS_AUTO"
    if prefix[0].isdigit():
        prefix = "AS_" + prefix
    root_name = prefix + "_ROOT"
    start_position = cmds.xform(start, query=True, worldSpace=True, rotatePivot=True)
    end_position = cmds.xform(end, query=True, worldSpace=True, rotatePivot=True)
    direction = [float(b) - float(a) for a, b in zip(start_position, end_position)]
    length = vec_len(direction)
    driven_pivots = [cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)
                     for node in drivens]
    nearest_distance = min(distance(start_position, pivot) for pivot in driven_pivots)
    sphere_radius = float(radius if radius is not None else nearest_distance * float(radius_scale))
    tilt_away_degrees = float(tilt_away_degrees)
    follicle_size = float(follicle_size)
    if ref_values is not None:
        ref_values = [float(value) for value in ref_values]
    if sub_items is None:
        sub_items = [[{"axis": output_axis, "outputType": "rotate", "reverseU": False,
                       "invertRotate": False, "strength": 1.0,
                       "startAngle": float(raise_start_angle),
                       "maxDistance": 0.0, "minDistance": 0.0, "refV": None}]
                     for _ in drivens]

    # Stage: Normalize each Driven's Sub Items and shared Extra Offset.
    prepared_items = []
    for entries in sub_items:
        current = []
        for entry in entries:
            sub = {"axis": str(entry.get("axis", output_axis)).upper()[-1],
                   "outputType": str(entry.get("outputType", "rotate")).lower(),
                   "reverseU": bool(entry.get("reverseU", False)),
                   "invertRotate": bool(entry.get("invertRotate", False)),
                   "strength": float(entry.get("strength", 1.0)),
                   "startAngle": float(entry.get("startAngle", raise_start_angle)),
                   "maxDistance": float(entry.get("maxDistance", 0.0)),
                   "minDistance": float(entry.get("minDistance", 0.0)),
                   "refV": None if entry.get("refV") is None else float(entry["refV"])}
            if entry.get("extraOffsetMatrix"):
                sub["extraOffsetMatrix"] = [float(value) for value in entry["extraOffsetMatrix"]]
            current.append(sub)
        shared_matrix = next((sub["extraOffsetMatrix"] for sub in current
                              if sub.get("extraOffsetMatrix")), None)
        for sub in current:
            sub.pop("extraOffsetMatrix", None)
        if shared_matrix:
            current[0]["extraOffsetMatrix"] = shared_matrix
        prepared_items.append(current)
    sphere_name = str(sphere_name or prefix + "_Sphere").strip()
    root = cmds.group(empty=True, name=root_name, world=True)
    # Stage: Size all follicle markers from one reader setting.
    size_plug = add_setting(root, "follicleSize", follicle_size, 0.01, 100)
    marker_size = cmds.createNode("multiplyDivide", name=prefix + "_MarkerSize")
    cmds.setAttr(marker_size + ".input1X", sphere_radius * 0.045)
    connect(size_plug, marker_size + ".input2X")
    fol_group = cmds.group(empty=True, name=prefix + "_Follicles", parent=root)
    debug_group = cmds.group(empty=True, name=prefix + "_Debug", parent=root)
    # Stage: Create a sphere or use the existing NURBS sphere unchanged.
    sphere_frame = None
    if create_sphere:
        sphere_frame = cmds.group(empty=True, name=prefix + "_SphereFrame", parent=root)
        cmds.xform(sphere_frame, worldSpace=True, translation=start_position)
        sphere = cmds.sphere(name=sphere_name, radius=sphere_radius, axis=(0, 1, 0),
                             polygon=0, constructionHistory=False)[0]
        cmds.parent(sphere, sphere_frame)
    else:
        sphere = cmds.ls(sphere_name, long=True)[0]
        bounds = cmds.exactWorldBoundingBox(sphere)
        sphere_radius = max(bounds[3] - bounds[0], bounds[4] - bounds[1], bounds[5] - bounds[2]) * 0.5
    # Use the actual NURBS radius for matching display size in both sphere modes.
    cmds.setAttr(marker_size + ".input1X", sphere_radius * 0.045)
    surf_shape = shape_of(sphere, "nurbsSurface")
    u_min = float(cmds.getAttr(surf_shape + ".minValueU"))
    u_max = float(cmds.getAttr(surf_shape + ".maxValueU"))
    v_min = float(cmds.getAttr(surf_shape + ".minValueV"))
    v_max = float(cmds.getAttr(surf_shape + ".maxValueV"))

    # Stage: Aim and freeze only a newly created sphere.
    if create_sphere:
        # Maya Display > NURBS > Surface Origins draws the surface NORMAL
        # in blue, not the transform's local Z axis. Sample that normal just
        # inside the parametric origin (exact Sphere poles are singular).
        # Query BEFORE placing/rotating the Sphere, so the normal is local.
        origin_u = u_min + (u_max - u_min) * 0.002
        origin_v = v_min + (v_max - v_min) * 0.002
        origin_normal = cmds.pointOnSurface(
            surf_shape, parameterU=origin_u, parameterV=origin_v,
            normalizedNormal=True)
        normal_length = vec_len(origin_normal)
        origin_normal = tuple(float(value) / normal_length for value in origin_normal)
    
        def up_perpendicular(aim_vector):
            # Avoid aim/up collinearity even when End points up or down.
            candidate = min(((0.0, 1.0, 0.0), (1.0, 0.0, 0.0),
                             (0.0, 0.0, 1.0)),
                            key=lambda v: abs(sum(a*b for a, b in zip(v, aim_vector))))
            dot = sum(a*b for a, b in zip(candidate, aim_vector))
            result = [a - dot*b for a, b in zip(candidate, aim_vector)]
            magnitude = vec_len(result)
            return tuple(value / magnitude for value in result)
    
        # Stage: Aim the sphere at End and apply the neutral tilt.
        cmds.xform(sphere, worldSpace=True, translation=start_position)
        world_direction = tuple(value / length for value in direction)
        aim = cmds.aimConstraint(
            end, sphere, aimVector=origin_normal,
            upVector=up_perpendicular(origin_normal), worldUpType="vector",
            worldUpVector=up_perpendicular(world_direction),
            maintainOffset=False)[0]
        cmds.delete(aim)
    
        # Rotate 20 degrees *away* from the Driven centroid after aiming End.
        # Remove the axial component to apply the specified tilt.
        centroid = tuple(sum(float(pos[i]) for pos in driven_pivots) /
                         len(driven_pivots) for i in range(3))
        towards_centroid = tuple(centroid[i] - start_position[i] for i in range(3))
        along_end = sum(a*b for a, b in zip(towards_centroid, world_direction))
        sideways = tuple(towards_centroid[i] - along_end * world_direction[i]
                         for i in range(3))
        sideways_length = vec_len(sideways)
        if sideways_length < 1e-6 and tilt_away_degrees:
            # Collinear/symmetrical Drivens have no geometrically unique
            # opposite side; use a deterministic tangent instead.
            sideways = up_perpendicular(world_direction)
            sideways_length = vec_len(sideways)
        away = tuple(-v / sideways_length for v in sideways) if sideways_length else (0.0, 0.0, 0.0)
        radians = math.radians(tilt_away_degrees)
        tilted_direction = tuple(math.cos(radians) * world_direction[i] +
                                 math.sin(radians) * away[i] for i in range(3))
        if tilt_away_degrees:
            tilt_target = cmds.spaceLocator(name=prefix + "_TiltAim")[0]
            cmds.xform(tilt_target, worldSpace=True,
                       translation=[start_position[i] + length * tilted_direction[i] for i in range(3)])
            tilt_aim = cmds.aimConstraint(tilt_target, sphere, aimVector=origin_normal,
                        upVector=up_perpendicular(origin_normal), worldUpType="vector",
                        worldUpVector=up_perpendicular(tilted_direction), maintainOffset=False)[0]
            cmds.delete(tilt_aim, tilt_target)
        # Stage: Freeze the aimed sphere before connecting Parent follow.
        cmds.makeIdentity(sphere, apply=True, translate=True,
                          rotate=True, scale=True)
        if sphere_follow:
            cmds.parentConstraint(parent, sphere_frame, maintainOffset=True,
                                  name=prefix + "_SphereFollow")
    else:
        centroid = tuple(sum(float(p[i]) for p in driven_pivots) / len(driven_pivots) for i in range(3))
        tilted_direction = tuple(float(v) / length for v in direction)

    # Stage: Track End and read the sphere UV.
    target = cmds.spaceLocator(name=prefix + "_EndReader")[0]
    cmds.parent(target, debug_group)
    target_shape = shape_of(target, "locator")
    cmds.setAttr(target_shape + ".localScaleX", sphere_radius * 0.08)
    cmds.setAttr(target_shape + ".localScaleY", sphere_radius * 0.08)
    cmds.setAttr(target_shape + ".localScaleZ", sphere_radius * 0.08)
    cmds.pointConstraint(end, target, maintainOffset=False,
                         name=prefix + "_EndReaderFollow")
    cpos = cmds.createNode("closestPointOnSurface", name=prefix + "_EndClosestPoint")
    connect(target_shape + ".worldPosition[0]", cpos + ".inPosition")
    connect(surf_shape + ".worldSpace[0]", cpos + ".inputSurface")

    # Follicles use normalized coordinates, including on non-[0,1] NURBS.
    uv = cmds.createNode("setRange", name=prefix + "_NormalizeUV")
    for a, channel, low, high in (("U", "X", u_min, u_max),
                                   ("V", "Y", v_min, v_max)):
        connect(cpos + ".parameter" + a, uv + ".value" + channel)
        cmds.setAttr(uv + ".oldMin" + channel, low)
        cmds.setAttr(uv + ".oldMax" + channel, high)
        cmds.setAttr(uv + ".min" + channel, 0)
        cmds.setAttr(uv + ".max" + channel, 1)
    cp_u, cp_v = uv + ".outValueX", uv + ".outValueY"
    neutral_u = float(cmds.getAttr(cp_u))
    neutral_v = float(cmds.getAttr(cp_v))
    cp_transform, cp_shape = make_follicle(
        prefix + "_CP_Follicle", surf_shape, fol_group,
        u_source=cp_u, v_source=cp_v)
    # Diana/Akali: CP tracks both UV, but Moving only tracks the V channel.
    # Ref and Moving are constrained to the SAME U isoline (equator U).
    moving_transform, moving_shape = make_follicle(
        prefix + "_Moving_Follicle", surf_shape, fol_group,
        u=equator_u, v_source=cp_v)
    marker(cp_transform, 13, prefix + "_CP")            # Red: live Knee CP.
    marker(moving_transform, 14, prefix + "_Moving")    # Green: fixed U, live V.
    shared_u = add_setting(root, "equatorU", equator_u, 0, 1)
    connect(shared_u, moving_shape + ".parameterU")
    # Fixed bind-pose Moving follicle for reliable per-Sub Item neutral recalibration.
    neutral_moving, neutral_moving_shape = make_follicle(
        prefix + "_NeutralMoving_Follicle", surf_shape, fol_group, u=equator_u, v=neutral_v)
    marker(neutral_moving, 14, prefix + "_NeutralMoving")
    connect(shared_u, neutral_moving_shape + ".parameterU")
    add_setting(root, "neutralU", neutral_u, 0, 1)
    add_setting(root, "neutralV", neutral_v, 0, 1)
    master = add_setting(root, "autoSkirt", 1.0, 0, 2)

    # Stage: Place Ref follicles using the Driven bind positions.
    sampler = cmds.createNode("closestPointOnSurface", name=prefix + "_RefSampler")
    connect(surf_shape + ".worldSpace[0]", sampler + ".inputSurface")
    if ref_values is None:
        ref_values = []
        for pivot in driven_pivots:
            cmds.setAttr(sampler + ".inPosition", *[float(v) for v in pivot],
                         type="double3")
            raw_v = float(cmds.getAttr(sampler + ".parameterV"))
            ref_values.append(normalized(raw_v, v_min, v_max))
    cmds.delete(sampler)
    refs = []
    for index, (driven, projected_v) in enumerate(zip(drivens, ref_values), 1):
        tag = "{}_{:02d}".format(prefix, index)
        first_v = prepared_items[index - 1][0]["refV"]
        first_v = projected_v if first_v is None else first_v
        ref_transform, ref_shape = make_follicle(
            tag + "_Ref_Follicle", surf_shape, fol_group, u=equator_u, v=first_v)
        marker(ref_transform, 17, tag + "_Ref")
        connect(shared_u, ref_shape + ".parameterU")
        ref_v_plug = add_setting(ref_transform, "refV", first_v, 0, 1)
        connect(ref_v_plug, ref_shape + ".parameterV")
        refs.append((tag, driven, ref_transform, ref_shape, first_v))

    # Stage: Connect each Ref and Driven offset.
    results = []
    for index, (tag, driven, ref_transform, ref_shape, ref_v) in enumerate(refs):
        item_specs = prepared_items[index]
        other_positions = [cmds.xform(other[2], query=True,
                                      worldSpace=True, rotatePivot=True)
                           for other in refs if other[0] != tag]
        my_position = cmds.xform(ref_transform, query=True,
                                 worldSpace=True, rotatePivot=True)
        # Auto uses the closest other Ref, with no distance multiplier.
        # With a single Ref there is no pair to measure: use sphere radius.
        nearest = min((distance(my_position, pos) for pos in other_positions),
                      default=sphere_radius)
        influence_max = max(nearest, 0.001)
        add_setting(ref_transform, "autoMaxDistance", influence_max, 0.001)
        # First sub-item retains original attribute names for Live Settings.
        add_setting(ref_transform, "raiseStartAngle", item_specs[0]["startAngle"], 0, 180)
        add_setting(ref_transform, "rotateSign",
                    -1.0 if item_specs[0]["invertRotate"] else 1.0, -1, 1)

        # Stage: Prepare independent Sub Item Ref and neutral distances.
        space, offset, new_driven = rig_offset(driven, tag)
        # Multiple Pose Readers may share one FK control. AutoFollow belongs
        # to the control, not to an individual Reader; never recreate or reset
        # an existing attribute (which may already be keyed/connected).
        auto_follow_plug = new_driven + ".AutoFollow"
        if not cmds.objExists(auto_follow_plug):
            add_setting(new_driven, "AutoFollow", 1.0, 0, 1)

        axis_sources = {}
        extra_axis_sources = {}
        extra_groups = []
        sub_results = []
        per_sub_outputs = {}
        for sub_index, spec in enumerate(item_specs):
            subtag = "{}_Sub{:02d}".format(tag, sub_index + 1)
            suffix = "sub{:02d}".format(sub_index + 1)
            if sub_index == 0:
                sub_ref = ref_transform
                ref_v_plug = ref_transform + ".refV"
                start_plug = ref_transform + ".raiseStartAngle"
            else:
                sub_v = ref_values[index] if spec["refV"] is None else spec["refV"]
                sub_ref, sub_shape = make_follicle(
                    subtag + "_Ref_Follicle", surf_shape, fol_group, u=equator_u, v=sub_v)
                marker(sub_ref, 17, subtag + "_Ref")
                connect(shared_u, sub_shape + ".parameterU")
                ref_v_plug = add_setting(ref_transform, suffix + "RefV", sub_v, 0, 1)
                connect(ref_v_plug, sub_shape + ".parameterV")
                start_plug = add_setting(ref_transform, suffix + "StartAngle",
                                         spec["startAngle"], 0, 180)
            spatial = cmds.createNode("distanceBetween",
                                     name=tag + "_InfluenceDistance" if sub_index == 0
                                     else subtag + "_InfluenceDistance")
            connect(sub_ref + ".worldMatrix[0]", spatial + ".inMatrix1")
            connect(moving_transform + ".worldMatrix[0]", spatial + ".inMatrix2")
            neutral_spatial = cmds.createNode("distanceBetween", name=subtag + "_NeutralDistance")
            connect(sub_ref + ".worldMatrix[0]", neutral_spatial + ".inMatrix1")
            connect(neutral_moving + ".worldMatrix[0]", neutral_spatial + ".inMatrix2")
            add_setting(ref_transform, "neutralDistance" if sub_index == 0 else suffix + "NeutralDistance",
                        float(cmds.getAttr(neutral_spatial + ".distance")), 0)

            # Stage: Build the per-Sub Item distance weight.
            other_positions = [cmds.xform(other[2], query=True, worldSpace=True, rotatePivot=True)
                               for other in refs if other[0] != tag]
            my_position = cmds.xform(sub_ref, query=True, worldSpace=True, rotatePivot=True)
            auto_max = max(min((distance(my_position, pos) for pos in other_positions),
                               default=sphere_radius), 0.001)
            if sub_index:
                add_setting(ref_transform, suffix + "AutoMaxDistance", auto_max, 0.001)
            effective_distance = spec["maxDistance"] if spec["maxDistance"] > 0 else auto_max
            min_plug = add_setting(
                ref_transform, "sub{:02d}MinDistance".format(sub_index + 1),
                spec["minDistance"], 0)
            dist_plug = add_setting(
                ref_transform, "sub{:02d}MaxDistance".format(sub_index + 1),
                effective_distance, 0.001)
            region_weight = cmds.createNode(
                "remapValue", name=subtag + "_DistanceWeight")
            connect(spatial + ".distance", region_weight + ".inputValue")
            connect(min_plug, region_weight + ".inputMin")
            connect(dist_plug, region_weight + ".inputMax")
            cmds.setAttr(region_weight + ".outputMin", 1.0)
            cmds.setAttr(region_weight + ".outputMax", 0.0)
            set_linear(region_weight)

            # Stage: Read the U-angle and subtract its threshold.
            angle_map = cmds.createNode("remapValue", name=subtag + "_AngleFromU")
            connect(cp_shape + ".parameterU", angle_map + ".inputValue")
            cmds.setAttr(angle_map + ".inputMin", 0)
            cmds.setAttr(angle_map + ".inputMax", 1)
            cmds.setAttr(angle_map + ".outputMin", 180 if spec["reverseU"] else 0)
            cmds.setAttr(angle_map + ".outputMax", 0 if spec["reverseU"] else 180)
            set_linear(angle_map)
            clamp = cmds.createNode("clamp", name=subtag + "_AngleClamp")
            connect(angle_map + ".outValue", clamp + ".inputR")
            connect(start_plug, clamp + ".minR")
            cmds.setAttr(clamp + ".maxR", 180)
            subtract = cmds.createNode("plusMinusAverage", name=subtag + "_SubtractStart")
            cmds.setAttr(subtract + ".operation", 2)
            connect(clamp + ".outputR", subtract + ".input1D[0]")
            connect(start_plug, subtract + ".input1D[1]")

            weighted = cmds.createNode("multiplyDivide", name=subtag + "_WeightedRaise")
            connect(subtract + ".output1D", weighted + ".input1X")
            connect(region_weight + ".outValue", weighted + ".input2X")
            neutral_value = float(cmds.getAttr(weighted + ".outputX"))
            zero = cmds.createNode("plusMinusAverage", name=subtag + "_ZeroNeutral")
            cmds.setAttr(zero + ".operation", 2)
            connect(weighted + ".outputX", zero + ".input1D[0]")
            cmds.setAttr(zero + ".input1D[1]", neutral_value)

            # Stage: Apply strength, AutoFollow, and output sign.
            strength_plug = add_setting(
                ref_transform, "sub{:02d}Strength".format(sub_index + 1),
                spec["strength"], 0, 2)
            gain = cmds.createNode("multiplyDivide", name=subtag + "_AngleStrength")
            connect(zero + ".output1D", gain + ".input1X")
            connect(strength_plug, gain + ".input2X")
            follower = cmds.createNode("multiplyDivide", name=subtag + "_AutoFollow")
            connect(gain + ".outputX", follower + ".input1X")
            connect(current_driven(offset) + ".AutoFollow", follower + ".input2X")
            master_gain = cmds.createNode("multiplyDivide", name=subtag + "_Master")
            connect(follower + ".outputX", master_gain + ".input1X")
            connect(master, master_gain + ".input2X")
            if sub_index == 0:
                sign_plug = ref_transform + ".rotateSign"
            else:
                sign_plug = add_setting(
                    ref_transform, "sub{:02d}RotateSign".format(sub_index + 1),
                    -1.0 if spec["invertRotate"] else 1.0, -1, 1)
            signed = cmds.createNode("multiplyDivide", name=subtag + "_Signed")
            connect(master_gain + ".outputX", signed + ".input1X")
            connect(sign_plug, signed + ".input2X")
            # Stage: Mute the contribution of this Sub Item only.
            gate = cmds.createNode("multiplyDivide", name=subtag + "_MuteGate")
            connect(signed + ".outputX", gate + ".input1X")
            cmds.setAttr(gate + ".input2X", 1.0)
            extra_offset = extra_group = None
            destination = offset + "." + spec["outputType"] + spec["axis"]
            if spec.get("extraOffsetMatrix"):
                space, extra_offset, extra_group = add_extra_offset(
                    space, subtag, spec["extraOffsetMatrix"])
                extra_groups.append(extra_group)
                destination = extra_group + "." + spec["outputType"] + spec["axis"]
                extra_axis_sources.setdefault(
                    (extra_group, spec["outputType"], spec["axis"]), []).append(gate + ".outputX")
            else:
                axis_sources.setdefault((spec["outputType"], spec["axis"]), []).append(gate + ".outputX")
            per_sub_outputs["sub{:02d}".format(sub_index + 1)] = destination
            sub_results.append(dict(extraOffset=extra_offset, extraTransform=extra_group,
                                    destination=destination, axis=spec["axis"], outputType=spec["outputType"], reverseU=spec["reverseU"],
                                    invertRotate=spec["invertRotate"], strength=spec["strength"],
                                    refV=float(cmds.getAttr(ref_v_plug)), ref=sub_ref,
                                    startAngle=spec["startAngle"], maxDistance=effective_distance,
                                    minDistance=spec["minDistance"], influenceDistance=spatial,
                                    distanceWeight=region_weight, neutralValue=neutral_value,
                                    settings=ref_transform, raiseNode=weighted,
                                    muteGate=gate + ".input2X", output=gate + ".outputX"))
        # Stage: All channels for one Driven use its single shared Extra Transform.
        if extra_groups:
            shared_extra = extra_groups[0]
            for (output_type, axis), sources in axis_sources.items():
                extra_axis_sources.setdefault(
                    (shared_extra, output_type, axis), []).extend(sources)
            axis_sources.clear()
            for sub_index, sub in enumerate(sub_results):
                if sub["extraTransform"] is None:
                    destination = shared_extra + "." + sub["outputType"] + sub["axis"]
                    sub["destination"] = destination
                    per_sub_outputs["sub{:02d}".format(sub_index + 1)] = destination

        outputs = {}
        for (output_type, axis), sources in axis_sources.items():
            if len(sources) == 1:
                bound = sources[0]
            else:
                combined = cmds.createNode("plusMinusAverage",
                                           name=tag + "_" + output_type.capitalize() + axis + "_Sum")
                for source_index, source in enumerate(sources):
                    connect(source, combined + ".input1D[{}]".format(source_index))
                bound = combined + ".output1D"
            output = offset + "." + output_type + axis
            # Stage: Connect Rotate or Translate for the selected axis.
            connect(bound, output)
            outputs[axis if output_type == "rotate" else "translate" + axis] = output
        for (extra_group, output_type, axis), sources in extra_axis_sources.items():
            if len(sources) == 1:
                bound = sources[0]
            else:
                combined = cmds.createNode(
                    "plusMinusAverage",
                    name=extra_group + "_" + output_type.capitalize() + axis + "_Sum")
                for source_index, source in enumerate(sources):
                    connect(source, combined + ".input1D[{}]".format(source_index))
                bound = combined + ".output1D"
            destination = extra_group + "." + output_type + axis
            connect(bound, destination)
        outputs.update(per_sub_outputs)
        new_driven = current_driven(offset)
        results.append(dict(driven=new_driven, space=space, offset=offset,
                            ref=ref_transform, refV=ref_v,
                            influenceDistance=sub_results[0]["influenceDistance"],
                            weight=sub_results[0]["distanceWeight"],
                            raiseNode=sub_results[0]["raiseNode"],
                            neutralValue=sub_results[0]["neutralValue"],
                            subItems=sub_results, outputs=outputs,
                            output=sub_results[0]["destination"]))

    cmds.select(clear=True)
    return dict(root=root, parent=parent, sphere=sphere, sphereFrame=sphere_frame,
                sphereShape=surf_shape, tiltAwayDegrees=tilt_away_degrees,
                tiltDirection=tilted_direction, drivenCentroid=centroid,
                radius=sphere_radius, nearestDrivenDistance=nearest_distance,
                start=start, end=end, neutralUV=(neutral_u, neutral_v),
                equatorU=equator_u, closestPoint=cpos, normalizeUV=uv,
                cpFollicle=cp_transform, movingFollicle=moving_transform,
                driven=results)
