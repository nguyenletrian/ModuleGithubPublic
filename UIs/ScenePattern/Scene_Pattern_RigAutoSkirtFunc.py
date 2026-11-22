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
        "moduleName": module_name, "order": 0, "title": "Auto Skirt Func",
        "name": "Auto Skirt Func", "id": datetime.now().strftime("%Y%m%d%H%M%S"),
    }

def dataPath(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    if not entry or not entry.get("path"):
        raise ValueError("AutoSkirt: ScenePatternData.json has no path for this pattern")
    return os.path.normpath(entry["path"])

def initialConfig():
    return {"version": 2, "name": "AutoSkirt_", "group": "RigUtil", "items": []}


def getData(data):
    path = dataPath(data)
    if not os.path.isfile(path):
        return initialConfig()
    saved = NLTA_General.readJsonFile(path)
    if not isinstance(saved, dict) or saved.get("version") != 2:
        return initialConfig()
    for item in saved.get("items", []):
        for entries in item.get("subItems", []):
            for sub in entries:
                sub.pop("extraOffsetMatrix", None)
                sub.pop("extraOffsetObject", None)
    return saved


def pickSingle(widget, *args):
    selection = cmds.ls(selection=True, objectsOnly=True) or []
    if len(selection) != 1:
        cmds.warning("AutoSkirt: select exactly one Maya object")
        return
    cmds.textField(widget, edit=True, text=selection[0])

def pickControls(widget, *args):
    selection = cmds.ls(selection=True, objectsOnly=True) or []
    if not selection:
        cmds.warning("AutoSkirt: select one or more FK controls")
        return
    cmds.scrollField(widget, edit=True, text="\n".join(dict.fromkeys(selection)))

def addSelectedDrivens(row, *args):
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
        row["subItems"].setdefault(name, normalizeSubItems(None, axis))
    cmds.scrollField(row["controls"], edit=True, text="\n".join(existing + added))


def mirrorLrName(name):
    """Swap L/R name tokens without replacing letters inside ordinary words."""
    def flip(match):
        token = match.group(0)
        return {"L": "R", "R": "L", "l": "r", "r": "l",
                "Left": "Right", "Right": "Left",
                "left": "right", "right": "left"}[token]
    name = re.sub(r"(?<![A-Za-z0-9])[LRlr](?=$|[|:_.-])", flip, name)
    return re.sub(r"(?<![A-Za-z0-9])(?:Left|Right|left|right)(?=$|[|:_.-]|[A-Z])",
                  flip, name)


def mirrorReaderData(reader, existing_ids):
    """Copy one reader to its opposite side; leave UV and rotation signs editable."""
    controls = list(reader["joints"])
    converted = [mirrorLrName(control) for control in controls]
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
    result["id"] = mirrorLrName(reader["id"])
    if result["id"] == reader["id"]:
        result["id"] = target_side + "_" + reader["id"]
    if result["id"] in existing_ids:
        raise ValueError("AutoSkirt Mirror: Reader ID already exists: " + result["id"])
    for key in ("sphere", "parent", "start", "end"):
        result[key] = mirrorLrName(reader.get(key, ""))
    if result["sphere"] == reader["sphere"]:
        result["sphere"] = target_side + "_" + reader["sphere"]
    result["joints"] = converted
    # A new side needs its own bind-pose V projection.
    result["refV"] = []
    # Keep manually edited Sub Item Ref V; nullable Auto values remain Auto.
    return result


def mirrorRow(row, *args):
    """Add the mirrored reader to the form and persist it in one transaction."""
    try:
        config = readUi()  # Also synchronizes an open Sub Item editor.
        source_id = cmds.textField(row["id"], query=True, text=True).strip()
        reader = next(item for item in config["items"] if item["id"] == source_id)
        clone = mirrorReaderData(reader, {item["id"] for item in config["items"]})
        # Distinct Pose Readers may intentionally share the same Driven.
        # Only duplicate controls inside one Reader remain invalid.
        added = addRow(STATE["holder"], clone)
        try:
            saveSettings(STATE["data"])
        except (OSError, ValueError, RuntimeError):
            removeRow(added)
            raise
        print("AutoSkirt Mirror: {} -> {} (configuration saved; Run to build)".format(
            source_id, clone["id"]))
        return added
    except (StopIteration, ValueError, RuntimeError, OSError) as exc:
        cmds.warning("AutoSkirt Mirror: {}".format(exc))
        return None


def liveFollicleSize(row, *args):
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


def lineField(parent, label, initial, picker=True, action=None):
    cmds.rowLayout(parent=parent, numberOfColumns=3, adjustableColumn=2,
                   columnWidth3=(105, 160, 92 if action else 55))
    cmds.text(label=label, align="left")
    widget = cmds.textField(text=str(initial))
    if action:
        cmds.button(label="Create Sphere", width=90, height=24,
                    annotation="Create and aim the NURBS sphere; rebuild U/V to 0-1",
                    command=action)
    elif picker:
        cmds.button(label="Pick", command=partial(pickSingle, widget))
    else:
        cmds.text(label="")
    cmds.setParent("..")
    return widget

def normalizeSubItems(entries, axis="Z", start_angle=10.0):
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
        result.append(normalized)
    return result

def skirtNodePrefix(sphere, driven, sub_number):
    """source convention: poseReader + real Driven name (+ Sub02, Sub03...)."""
    joint_name = driven.rsplit("|", 1)[-1]
    if sub_number > 1:
        joint_name += "_Sub{:02d}".format(sub_number)
    return "{}_{}".format(sphere.rsplit("|", 1)[-1], joint_name)


def fallbackLiveReference(row, control, index, system, rid):
    """Reconnect to an exported/built rig that has no patternData metadata.

    Resolve only the exact deterministic Reader/Driven/Sub Item names and
    require the live DG plugs to exist. Never create nodes or rebuild a rig.
    """
    controls = getControls(row)
    if control not in controls:
        return None
    slot = controls.index(control)
    tag = "{}_{}_{:02d}".format(system, rid, slot + 1)
    sphere = cmds.textField(row["sphere"], query=True, text=True).strip()
    ref = skirtNodePrefix(sphere, control, index + 1) + "_ref_follicle"
    subtag = "{}_Sub{:02d}".format(tag, index + 1)
    required = (system + "_System", ref + ".maxDistance",
                ref + ".autoMaxDistance", subtag + "_NeutralDistance.distance",
                subtag + "_ZeroNeutral.input1D[1]")
    if not all(cmds.objExists(plug) for plug in required):
        return None
    references = {}
    for position, driven in enumerate(controls, 1):
        core_candidate = skirtNodePrefix(sphere, driven, 1) + "_ref_follicle"
        candidate = (core_candidate if cmds.objExists(core_candidate)
                     else "{}_{}_{:02d}_Ref_Follicle".format(system, rid, position))
        if cmds.objExists(candidate):
            references[driven] = candidate
    return slot, ref, references


def applyLiveSubItem(row, control, index, *args, restore_auto_ref=False):
    """Update a built reader after reopening Maya, preserving the neutral pose."""
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    meta = metaFromScene({"name": system})
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
                spec.get("outputType", "rotate") != built_spec.get("outputType", "rotate")):
            return False  # Changing output wiring requires a clean rebuild.
        reference = meta.get("refs", {}).get(rid, {}).get(control)
        if not reference:
            return False
        ref = reference[0]
        references = {name: entry[0] for name, entry in
                      meta.get("refs", {}).get(rid, {}).items() if entry}
    else:
        # Standalone ExportPython builds can lack patternData on _System.
        resolved = fallbackLiveReference(row, control, index, system, rid)
        if not resolved:
            return False
        slot, ref, references = resolved
        spec = row["subItems"][control][index]
    tag = "{}_{}_{:02d}".format(system, rid, slot + 1)
    subtag = "{}_Sub{:02d}".format(tag, index + 1)
    suffix = "sub{:02d}".format(index + 1)
    sphere = (original.get("sphere") if original else None) or cmds.textField( row["sphere"], query=True, text=True).strip()
    core_prefix = skirtNodePrefix(sphere, control, index + 1)
    ref = core_prefix + "_ref_follicle"
    core_graph = cmds.objExists(core_prefix + "_Remap_Raise")
    attrs = {
        "start": ref + ".raiseStartAngle",
        "distance": ref + ".maxDistance",
        "minDistance": ref + ".minDistance",
        "strength": ref + ".strength",
        "refV": ref + ".refV",
        "neutralSpatial": subtag + "_NeutralDistance.distance",
        "rotateSign": ref + ".rotateSign",
        "neutralDistance": ref + ".neutralDistance",
        "neutralU": "{}_{}_ROOT.neutralU".format(system, rid),
        "zero": subtag + "_ZeroNeutral.input1D[1]",
        "angleMin": (core_prefix + "_Remap_Raise.outputMin" if core_graph
                     else subtag + "_AngleFromU.outputMin"),
        "angleMax": (core_prefix + "_Remap_Raise.outputMax" if core_graph
                     else subtag + "_AngleFromU.outputMax"),
        "autoDistance": ref + ".autoMaxDistance",
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
            position = cmds.xform(ref, query=True, worldSpace=True, rotatePivot=True)
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
    cmds.setAttr((core_prefix + "_Remap_Distance" if core_graph else subtag + "_DistanceWeight") + ".outputMin", 1.0)
    cmds.setAttr(attrs["angleMin"], 180.0 if spec["reverseU"] else 0.0)
    cmds.setAttr(attrs["angleMax"], 0.0 if spec["reverseU"] else 180.0)
    cmds.setAttr(attrs["zero"], neutral_value)
    return True

def autoMaxDistanceForDisplay(row, control, index):
    """Show the effective Max Distance stored on this Sub Item Ref."""
    plug = subItemRefName(row, control, index) + ".maxDistance"
    if not cmds.objExists(plug):
        return None
    value = float(cmds.getAttr(plug))
    return value if math.isfinite(value) and value >= 0.001 else None


def refVForDisplay(row, control, index):
    """Read V from this Sub Item Ref without changing the saved Auto sentinel."""
    plug = subItemRefName(row, control, index) + ".refV"
    if not cmds.objExists(plug):
        return None
    value = float(cmds.getAttr(plug))
    return value if math.isfinite(value) and 0 <= value <= 1 else None


def mirrorRefPosition(point, source_start, target_start):
    """Reflect a point across the plane halfway between opposite Starts."""
    delta = [float(b) - float(a) for a, b in zip(source_start, target_start)]
    length = math.sqrt(sum(v*v for v in delta))
    if length < 1e-6:
        raise ValueError("Opposite Start positions coincide; cannot infer mirror plane")
    normal = [v / length for v in delta]
    center = [(float(a) + float(b)) * 0.5 for a, b in zip(source_start, target_start)]
    offset = sum((float(p) - center[i]) * normal[i] for i, p in enumerate(point))
    return [float(p) - 2.0 * offset * normal[i] for i, p in enumerate(point)]


def mirrorRefVFromScene(source, target, source_v, source_control, target_control):
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
    src_shapes = cmds.listRelatives(source_sphere, shapes=True, noIntermediate=True, type="nurbsSurface", fullPath=True) or []
    dst_shapes = cmds.listRelatives(target_sphere, shapes=True, noIntermediate=True, type="nurbsSurface", fullPath=True) or []
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
        mirrored = mirrorRefPosition(point, axis[0], axis[1])
        destination = cmds.createNode("closestPointOnSurface", name="AutoSkirt_MirrorTarget_Sampler#")
        cmds.connectAttr(dst_shape + ".worldSpace[0]", destination + ".inputSurface", force=True)
        cmds.setAttr(destination + ".inPosition", *mirrored, type="double3")
        raw_v = float(cmds.getAttr(destination + ".parameterV"))
    finally:
        cmds.delete(sampler)
        if destination: cmds.delete(destination)
    return max(0.0, min(1.0, (raw_v - dst_v0) / (dst_v1 - dst_v0)))


def sourceRefVFromDriven(sphere, driven):
    """Project the opposite Driven to its sphere when its Ref is still Auto."""
    if not cmds.objExists(sphere) or not cmds.objExists(driven):
        return None
    shapes = cmds.listRelatives(sphere, shapes=True, noIntermediate=True, type="nurbsSurface", fullPath=True) or []
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


def getMirrorRefV(row, control, index):
    """Resolve the opposite Sub Item Ref; prefer scene geometry over V inversion."""
    config = readUi()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    opposite_control = mirrorLrName(control)
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
                value = refVForDisplay(other_row, opposite_control, index)
                break
        if value is None:
            projected = opposite.get("refV", [])
            if slot < len(projected):
                value = projected[slot]
        if value is None:
            value = sourceRefVFromDriven(opposite["sphere"], opposite_control)
    if value is None:
        raise ValueError("Get Mirror Ref: opposite Ref V is unavailable; build or set it first")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Get Mirror Ref: opposite Ref V must be 0..1")
    target = next((reader for reader in config["items"] if reader["id"] == rid), None)
    if target is None:
        raise ValueError("Get Mirror Ref: current Reader was not found")
    projected = mirrorRefVFromScene(opposite, target, value, opposite_control, control)
    return (projected, "scene position") if projected is not None else (
        1.0 - value, "1 - opposite Ref V")


def muteGatePlug(row, control, index):
    """Find the existing scene gate for one built Sub Item."""
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    meta = metaFromScene({"name": system})
    if not meta:
        resolved = fallbackLiveReference(row, control, index, system, rid)
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


def readSubItemMute(row, control, index):
    """Muted state is a scene override, never a JSON Sub Item field."""
    gate = muteGatePlug(row, control, index)
    return bool(gate and float(cmds.getAttr(gate)) < 0.5)


def setSubItemMute(row, control, index, muted):
    """Block only this Sub Item's output without changing Angle Strength."""
    gate = muteGatePlug(row, control, index)
    if not gate:
        cmds.warning("AutoSkirt Mute: run the updated builder to create Mute gates")
        return False
    cmds.setAttr(gate, 0.0 if muted else 1.0)
    return True


def readSubItemFields(fields, auto_unchanged, ref_v_unchanged):
    """Read one Sub Item output channel."""
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


def buildLiveAddedSubItem(row, control, index, spec):
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
    control_list = getControls(row)
    if control not in control_list:
        raise ValueError("AutoSkirt Live Add: unknown Driven " + control)
    slot = control_list.index(control)
    meta = metaFromScene({"name": system})
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
    sphere = ((original or {}).get("sphere")
              or cmds.textField(row["sphere"], query=True, text=True).strip())
    source_ref = skirtNodePrefix(sphere, control, 1) + "_ref_follicle"
    ref = ((meta.get("refs", {}).get(rid, {}).get(control, [None])[0]
            if meta else None) or (source_ref if cmds.objExists(source_ref)
                                  else tag + "_Ref_Follicle"))
    root = prefix + "_ROOT"
    marker_size = prefix + "_MarkerSize"
    source_moving = skirtNodePrefix(sphere, control_list[0], 1) + "_equator_follicle"
    moving = (source_moving if cmds.objExists(source_moving)
              else prefix + "_Moving_Follicle")
    neutral_moving = prefix + "_NeutralMoving_Follicle"
    source_cp = sphere.rsplit("|", 1)[-1] + "_CP_follicle"
    cp = source_cp if cmds.objExists(source_cp) else prefix + "_CP_Follicle"
    offset = tag + "_DrivenOffset"
    required = (root, marker_size, moving, neutral_moving,
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
    new_source = skirtNodePrefix(sphere, control, index + 1)
    if (cmds.objExists(new_source + "_ref_follicle")
            or cmds.objExists(subtag + "_Ref_Follicle")
            or cmds.objExists(subtag + "_MuteGate")):
        raise ValueError("AutoSkirt Live Add: Sub Item {} already exists".format(index + 1))
    spec = normalizeSubItems([spec])[0]
    kind, axis = spec["outputType"], spec["axis"]
    output = offset + "." + kind + axis
    sum_node = tag + "_" + kind.capitalize() + axis + "_Sum"
    # Plan the final routing before creating any follicle or DG node.
    incoming = cmds.listConnections(output, source=True, destination=False, plugs=True, skipConversionNodes=True) or []
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
        reference_v = original.get("refV", [])
        projected = reference_v[slot] if slot < len(reference_v) else None
    else:
        projected = row.get("referenceV", {}).get(control)
    if not sphere or not cmds.objExists(sphere):
        raise ValueError("AutoSkirt Live Add: built NURBS sphere is missing")
    surface = cmds.listRelatives(sphere, shapes=True, noIntermediate=True, fullPath=True, type="nurbsSurface") or []
    cp_shape = cmds.listRelatives(cp, shapes=True, noIntermediate=True, fullPath=True, type="follicle") or []
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
        core_candidate = skirtNodePrefix(sphere, driven, 1) + "_ref_follicle"
        candidate = ((meta.get("refs", {}).get(rid, {}).get(driven, [None])[0]
                      if meta else None) or (core_candidate
                      if cmds.objExists(core_candidate)
                      else "{}_{:02d}_Ref_Follicle".format(prefix, pos)))
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
        args = dict(longName=name, attributeType="double",
                    defaultValue=float(value), keyable=True)
        if minimum is not None:
            args["minValue"] = float(minimum)
        if maximum is not None:
            args["maxValue"] = float(maximum)
        cmds.addAttr(reference, **args)
        return reference + "." + name

    def linear(node):
        for i in range(2):
            point = node + ".value[{}]".format(i)
            cmds.setAttr(point + ".value_Position", float(i))
            cmds.setAttr(point + ".value_FloatValue", float(i))
            cmds.setAttr(point + ".value_Interp", 1)

    # Stage: The same original source graph creates every live Sub Item.
    if not (cmds.objExists(root + ".skirtCore") or
            cmds.objExists(root + ".dianaCore")):
        raise ValueError("AutoSkirt Live Add: this rig predates the source core; "
                         "rebuild on a clean scene")
    cmds.undoInfo(openChunk=True, chunkName="AutoSkirt source Add Live Sub Item")
    changed = False
    try:
        sphere_name = sphere.rsplit("|", 1)[-1]
        raw_prefix = skirtNodePrefix(sphere_name, control, index + 1)
        source_id = raw_prefix[len(sphere_name) + 1:]
        original_rig = skirtRigCore
        original_rig(sphere_name, cp_shape[0], sphere_name + "_cpos",
                     [source_id], [sub_v], [(0.0, 1.0)],
                     [spec["startAngle"]],
                     rig_group=cmds.textField(STATE["top"]["group"], query=True, text=True).strip())
        changed = True
        # source keeps its exact source node names and parents Follicles to rig_group.
        reference = raw_prefix + "_ref_follicle"
        equator = raw_prefix + "_equator_follicle"

        actual_shape = (cmds.listRelatives(reference, shapes=True, type="follicle", fullPath=True) or [None])[0]
        equator_shape = (cmds.listRelatives(equator, shapes=True, type="follicle", fullPath=True) or [None])[0]
        if not actual_shape or not equator_shape:
            raise RuntimeError("AutoSkirt Live Add: source follicle missing")
        connect(root + ".equatorU", actual_shape + ".parameterU", force=True)
        connect(root + ".equatorU", equator_shape + ".parameterU", force=True)
        connect(setting("RefV", sub_v, 0, 1),
                actual_shape + ".parameterV", force=True)
        marker = cmds.createNode("locator", name=subtag + "_Ref_MarkerShape", parent=reference)
        for coordinate in "XYZ":
            connect(marker_size + ".outputX", marker + ".localScale" + coordinate)
        cmds.setAttr(marker + ".overrideEnabled", 1)
        cmds.setAttr(marker + ".overrideColor", 17)

        # Stage: Preserve the source's DG, extend only its live settings/output.
        cmds.addAttr(reference + ".maxDistance", edit=True, hasMaxValue=False)
        cmds.addAttr(reference + ".minDistance", edit=True, hasMaxValue=False)
        pos = cmds.xform(reference, query=True, worldSpace=True, rotatePivot=True)
        spatial_distances = [
            math.sqrt(sum((float(a)-float(b))**2 for a, b in
                 zip(pos, cmds.xform(other, query=True, worldSpace=True, rotatePivot=True))))
            for other in other_refs]
        auto_distance = max(min(spatial_distances, default=radius), 0.001)
        setting("AutoMaxDistance", auto_distance, 0.001)
        maximum = spec["maxDistance"] if spec["maxDistance"] > 0 else auto_distance
        if spec["minDistance"] >= maximum:
            raise ValueError("AutoSkirt Live Add: Min Distance must be below Max Distance")
        cmds.setAttr(reference + ".minDistance", spec["minDistance"])
        cmds.setAttr(reference + ".maxDistance", maximum)
        cmds.setAttr(reference + ".raiseStartAngle", spec["startAngle"])
        angle = raw_prefix + "_Remap_Raise"
        cmds.setAttr(angle + ".outputMin", 180 if spec["reverseU"] else 0)
        cmds.setAttr(angle + ".outputMax", 0 if spec["reverseU"] else 180)
        neutral = cmds.createNode("distanceBetween", name=subtag + "_NeutralDistance")
        connect(reference + ".worldMatrix[0]", neutral + ".inMatrix1")
        connect(neutral_moving + ".worldMatrix[0]", neutral + ".inMatrix2")
        neutral_distance = float(cmds.getAttr(neutral + ".distance"))
        setting("NeutralDistance", neutral_distance, 0)
        neutral_u = float(cmds.getAttr(root + ".neutralU"))
        neutral_angle = 180.0 * ((1.0 - neutral_u)
                                 if spec["reverseU"] else neutral_u)
        neutral_weight = max(0.0, min(1.0, (maximum - neutral_distance) /
                                      (maximum - spec["minDistance"])))
        neutral_value = max(0.0, neutral_angle - spec["startAngle"]) * neutral_weight
        zero = cmds.createNode("plusMinusAverage", name=subtag + "_ZeroNeutral")
        cmds.setAttr(zero + ".operation", 2)
        connect(raw_prefix + "_md_Raise.outputX", zero + ".input1D[0]")
        cmds.setAttr(zero + ".input1D[1]", neutral_value)
        strength = setting("Strength", spec["strength"], 0, 2)
        connect(zero + ".output1D", raw_prefix + "_md_RaiseInfluence.input1X",
                force=True)
        connect(strength, raw_prefix + "_md_RaiseInfluence.input2X", force=True)
        follower = cmds.createNode("multiplyDivide", name=subtag + "_AutoFollow")
        connect(raw_prefix + "_md_RaiseInfluence.outputX", follower + ".input1X")
        connect(auto_follow, follower + ".input2X")
        master = cmds.createNode("multiplyDivide", name=subtag + "_Master")
        connect(follower + ".outputX", master + ".input1X")
        connect(root + ".autoSkirt", master + ".input2X")
        sign = setting("RotateSign", -1 if spec["invertRotate"] else 1, -1, 1)
        signed = cmds.createNode("multiplyDivide", name=subtag + "_Signed")
        connect(master + ".outputX", signed + ".input1X")
        connect(sign, signed + ".input2X")
        gate = cmds.createNode("multiplyDivide", name=subtag + "_MuteGate")
        connect(signed + ".outputX", gate + ".input1X")
        cmds.setAttr(gate + ".input2X", 1)
        gate_output = gate + ".outputX"

        if route == "direct":
            connect(gate_output, output)
        elif route == "sum":
            used = cmds.getAttr(sum_node + ".input1D", multiIndices=True) or []
            connect(gate_output, sum_node + ".input1D[{}]".format(max(used, default=-1) + 1))
        else:
            combined = cmds.createNode("plusMinusAverage", name=sum_node)
            connect(previous, combined + ".input1D[0]")
            connect(gate_output, combined + ".input1D[1]")
            connect(combined + ".output1D", output, force=True)
        if original:
            original["subItems"][slot].append(dict(spec))
            cmds.setAttr(system_root + ".patternData", json.dumps(meta, ensure_ascii=False), type="string")
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if changed:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)

    return True


def finishSubItems(row, sync, window):
    """Save all Sub Item edits to JSON; keep the editor window open."""
    try:
        sync()
        saveSettings(STATE["data"])
    except (ValueError, RuntimeError, OSError) as exc:
        cmds.warning("AutoSkirt Save Sub Items: {}".format(exc))
        return False
    print("AutoSkirt Sub Items: JSON saved; editor remains open.")
    return True


def subItemRefCandidates(row, control, index):
    """Resolve current Skin200 names, then existing legacy names."""
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    rid = cmds.textField(row["id"], query=True, text=True).strip()
    controls = getControls(row)
    if control not in controls:
        raise ValueError("AutoSkirt: Driven not found in this Reader: " + control)
    slot = controls.index(control)
    sphere = cmds.textField(row["sphere"], query=True, text=True).strip()
    meta = metaFromScene({"name": system}) or {}
    original = next((item for item in meta.get("data", {}).get("items", [])
                     if item.get("id") == rid and control in item.get("joints", [])), None)
    candidates = []

    # The built Reader's Sphere takes priority over the current form.
    if original:
        sphere = original.get("sphere") or sphere
        slot = original["joints"].index(control)
    candidates.append(skirtNodePrefix(sphere, control, index + 1) + "_ref_follicle")
    form_sphere = cmds.textField(row["sphere"], query=True, text=True).strip()
    if form_sphere != sphere:
        candidates.append(skirtNodePrefix(form_sphere, control, index + 1) + "_ref_follicle")

    # The stored Sub 01 reference can locate the renamed Sub 02+ follicle.
    reference = meta.get("refs", {}).get(rid, {}).get(control)
    if reference and reference[0]:
        base = reference[0].rsplit("|", 1)[-1]
        if index == 0:
            candidates.insert(0, reference[0])
        elif base.endswith("_ref_follicle"):
            candidates.insert(0, base[:-len("_ref_follicle")] +
                              "_Sub{:02d}_ref_follicle".format(index + 1))

    # Old names remain selectable only if they actually exist in Maya.
    tag = "{}_{}_{:02d}".format(system, rid, slot + 1)
    legacy = (tag + "_Ref_Follicle" if index == 0
              else "{}_Sub{:02d}_Ref_Follicle".format(tag, index + 1))
    candidates.append(legacy)
    return list(dict.fromkeys(candidates))


def subItemRefName(row, control, index):
    """Display the existing Ref, or its expected current name."""
    candidates = subItemRefCandidates(row, control, index)
    for name in candidates:
        if len(cmds.ls(name, long=True, type="transform") or []) == 1:
            return name
    return candidates[0]


def selectSubItemRef(row, control, index, *args):
    """Select a built Ref; never treat a guessed legacy name as real."""
    candidates = subItemRefCandidates(row, control, index)
    for name in candidates:
        matches = cmds.ls(name, long=True, type="transform") or []
        if len(matches) > 1:
            cmds.warning("AutoSkirt: ambiguous Ref: " + name)
            return False
        if len(matches) == 1:
            cmds.select(matches[0], replace=True)
            return matches[0]
    cmds.warning("AutoSkirt: Ref not built for {} Sub {:02d}; expected {}. "
                 "Run or Add Sub Item Live.".format(control, index + 1, candidates[0]))
    return False


def editSubItems(row, *args):
    """Edit any number of axis/UV-direction responses per Driven."""
    controls = getControls(row)
    window = "NLTA_AutoSkirt_Alt_SubItems"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    window = cmds.window(window, title="AutoSkirt - Driven Sub Items", widthHeight=(550, 555))
    body = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    scroll = cmds.scrollLayout(parent=body, childResizable=True, height=460)
    holder = cmds.columnLayout(parent=scroll, adjustableColumn=True, rowSpacing=4)
    editor = {"window": window, "widgets": {}}
    row["subEditor"] = editor
    # A built Auto value appears as a number, but remains 0 in JSON until edited.
    auto_display = {}
    ref_v_auto_display = {}
    manual_max_distance = set()
    manual_ref_v = set()
    axis = str(STATE.get("defaultAxis", "rotateZ"))[-1:].upper()
    for control in controls:
        row["subItems"].setdefault(control, normalizeSubItems(
            None, axis, getSettings(row, control)["startAngle"]))

    def sync():
        for control, widgets in editor["widgets"].items():
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
                captured.append(readSubItemFields(fields, auto_unchanged, ref_v_unchanged))
            row["subItems"][control] = normalizeSubItems(captured, axis)

    def live(control, index, changed=None, *unused):
        try:
            if changed == "refV": manual_ref_v.add((control, index))
            if changed == "maxDistance": manual_max_distance.add((control, index))
            sync()
            if applyLiveSubItem(row, control, index):
                # Entering 0 resets the value to Auto; show its resolved distance.
                spec = row["subItems"][control][index]
                if spec["maxDistance"] == 0:
                    resolved = autoMaxDistanceForDisplay(row, control, index)
                    if resolved is not None:
                        auto_display.setdefault(control, {})[index] = resolved
                        fields = editor["widgets"][control][index]
                        cmds.floatSliderGrp(fields["distance"], edit=True, value=resolved)
        except (ValueError, RuntimeError) as exc:
            cmds.warning("AutoSkirt Live: {}".format(exc))
            return False

    def change_mute(control, index, widget, *unused):
        muted = bool(cmds.checkBox(widget, query=True, value=True))
        if not setSubItemMute(row, control, index, muted):
            cmds.checkBox(widget, edit=True, value=False)

    def mirror_ref(control, index, *unused):
        try:
            sync()
            value, method = getMirrorRefV(row, control, index)
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
            spec = normalizeSubItems(None, axis)[0]
            index = len(row["subItems"][control])
            built = buildLiveAddedSubItem(row, control, index, spec)
            row["subItems"][control].append(spec)
            draw()
            if built:
                if not applyLiveSubItem(row, control, index):
                    cmds.warning("AutoSkirt: new Sub Item was built, but Live " "reconnection could not be verified")
                print("AutoSkirt: Sub {:02d} added Live for {}. "
                      "Use Save Sub Items to persist JSON.".format(index + 1, control))
        except (ValueError, RuntimeError, KeyError) as exc:
            cmds.warning("AutoSkirt Add Sub Item: {}".format(exc))

    def remove(control, index, *unused):
        sync()
        if len(row["subItems"][control]) <= 1:
            cmds.warning("AutoSkirt: at least one Sub Item is required")
            return
        row["subItems"][control].pop(index)
        draw()

    def draw():
        for child in cmds.layout(holder, query=True, childArray=True) or []:
            cmds.deleteUI(child)
        editor["widgets"] = {}
        auto_display.clear()
        ref_v_auto_display.clear()
        manual_max_distance.clear()
        manual_ref_v.clear()
        for control in controls:
            frame = cmds.frameLayout(parent=holder, label=control, collapsable=True, marginWidth=6, marginHeight=4)
            column = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=4)
            editor["widgets"][control] = []
            for index, sub in enumerate(row["subItems"][control]):
                item_col = cmds.columnLayout(parent=column, adjustableColumn=True, rowSpacing=5)
                first_row = cmds.rowLayout(parent=item_col, numberOfColumns=2, columnWidth2=(220, 135))
                reverse = cmds.checkBox(parent=first_row, label="Reverse U (1->0)", value=sub["reverseU"])
                muted = cmds.checkBox(parent=first_row, label="Mute", value=readSubItemMute(row, control, index))
                cmds.checkBox(muted, edit=True, changeCommand=partial(change_mute, control, index, muted))
                cmds.setParent(item_col)
                output_row = cmds.rowLayout(parent=item_col, numberOfColumns=4, columnWidth4=(82, 112, 75, 84))
                cmds.text(parent=output_row, label="Output Type", align="left")
                output_type = cmds.optionMenu(parent=output_row, width=108)
                for name in ("Rotate", "Translate"):
                    cmds.menuItem(parent=output_type, label=name)
                cmds.optionMenu(output_type, edit=True, value=sub.get("outputType", "rotate").capitalize())
                cmds.text(parent=output_row, label="Axis", align="right")
                menu = cmds.optionMenu(parent=output_row, width=76)
                for name in "XYZ": cmds.menuItem(parent=menu, label=name)
                cmds.optionMenu(menu, edit=True, value=sub["axis"])
                cmds.setParent(item_col)
                invert = cmds.checkBox(parent=item_col, label="Invert Output", value=sub["invertRotate"])
                # Ref is an existing follicle transform, not a JSON setting.
                ref_node_row = cmds.formLayout(parent=item_col, height=28)
                ref_caption = cmds.text(parent=ref_node_row, label="Ref Node", align="left", width=73)
                ref_name = cmds.textField(parent=ref_node_row, text=subItemRefName(row, control, index), editable=False)
                ref_select = cmds.button( parent=ref_node_row, label="Select", width=66, command=partial(selectSubItemRef, row, control, index))
                cmds.formLayout(ref_node_row, edit=True, attachForm=[(ref_caption, "left", 3), (ref_caption, "top", 6), (ref_name, "top", 2), (ref_name, "bottom", 2), (ref_select, "top", 2), (ref_select, "bottom", 2), (ref_select, "right", 3)], attachControl=[(ref_name, "left", 4, ref_caption), (ref_name, "right", 4, ref_select)])
                cmds.setParent(item_col)

                # Single-column slider controls with exact numeric input.
                start = cmds.floatSliderGrp(parent=item_col, label="Start Angle", field=True, minValue=0, maxValue=179.99, fieldMinValue=0, fieldMaxValue=179.99, value=sub["startAngle"], precision=2, columnWidth3=(145, 68, 285), adjustableColumn3=3)
                strength_field = cmds.floatSliderGrp(parent=item_col, label="Angle Strength", field=True, minValue=0, maxValue=2, fieldMinValue=0, fieldMaxValue=2, value=sub["strength"], precision=8, columnWidth3=(135, 125, 235), adjustableColumn3=3)
                projected_v = refVForDisplay(row, control, index) if sub["refV"] is None else None
                shown_ref_v = projected_v if projected_v is not None else (
                    row["referenceV"].get(control, 0.5) if sub["refV"] is None else sub["refV"])
                if sub["refV"] is None:
                    ref_v_auto_display.setdefault(control, {})[index] = shown_ref_v
                ref_row = cmds.rowLayout(parent=item_col, numberOfColumns=2, columnWidth2=(392, 108))
                ref_v_field = cmds.floatSliderGrp(parent=ref_row, label="Ref V", field=True, minValue=0, maxValue=1, fieldMinValue=0, fieldMaxValue=1, value=shown_ref_v, precision=3, columnWidth3=(136, 68, 180), adjustableColumn3=3)
                cmds.button(parent=ref_row, label="Get Mirror Ref", width=102, command=partial(mirror_ref, control, index))
                cmds.setParent(item_col)
                resolved = autoMaxDistanceForDisplay(row, control, index) if sub["maxDistance"] == 0 else None
                if resolved is not None: auto_display.setdefault(control, {})[index] = resolved
                shown_max = resolved if resolved is not None else sub["maxDistance"]
                slider_max = max(1.0, shown_max, sub["minDistance"] * 1.5)
                field_limit = max(1000000.0, slider_max * 2)
                min_distance_field = cmds.floatSliderGrp(parent=item_col, label="Max Effect Range", field=True, minValue=0, maxValue=slider_max, fieldMinValue=0, fieldMaxValue=field_limit, value=sub["minDistance"], precision=3, columnWidth3=(145, 68, 285), adjustableColumn3=3)
                distance_field = cmds.floatSliderGrp(parent=item_col, label="Max Distance", field=True, minValue=0, maxValue=slider_max * 2, fieldMinValue=0, fieldMaxValue=field_limit, value=shown_max, precision=3, columnWidth3=(145, 68, 285), adjustableColumn3=3)
                # Keep both Sub Item actions together.
                actions = cmds.rowLayout(parent=item_col, numberOfColumns=2, columnWidth2=(145, 145))
                cmds.button(parent=actions, label="Remove Sub Item", width=140, height=24, command=partial(remove, control, index))
                cmds.button(parent=actions, label="+ Add Sub Item", width=140, height=24, command=partial(add, control))
                cmds.setParent(item_col)
                editor["widgets"][control].append(
                    {"axis": menu, "outputType": output_type, "reverse": reverse, "invert": invert, "mute": muted,
                     "refNode": ref_name, "strength": strength_field, "start": start, "refV": ref_v_field,
                     "distance": distance_field, "minDistance": min_distance_field})
                # Numeric settings are live; output type, axis and item count require a fresh Run.
                cmds.checkBox(reverse, edit=True, changeCommand=partial(live, control, index))
                cmds.checkBox(invert, edit=True, changeCommand=partial(live, control, index))
                # changeCommand fires on slider release; dragCommand is intentionally omitted.
                for field, widget in (("startAngle", start), ("strength", strength_field),
                                      ("refV", ref_v_field), ("minDistance", min_distance_field),
                                      ("maxDistance", distance_field)):
                    cmds.floatSliderGrp(widget, edit=True, changeCommand=partial(live, control, index, field))
                cmds.setParent(column)
            cmds.setParent(holder)

    def finish(*unused):
        return finishSubItems(row, sync, window)

    editor["sync"] = sync
    editor["refresh"] = draw
    draw()
    cmds.text(parent=body, label="Sliders apply Live on release. Strength: 1 = normal; Max Distance: 0 = Auto.", align="left")
    cmds.text(parent=body, label="Output Type / Axis: Save JSON, then Run on a clean scene to rewire.", align="left")
    cmds.button(parent=body, label="Restore from JSON + Live", height=28, command=lambda *unused: restoreJsonLive( STATE["data"], STATE["listUI"], cmds.textField(row["id"], query=True, text=True).strip()))
    cmds.button(parent=body, label="Save Sub Items", height=28, command=finish)
    cmds.showWindow(window)

def getControls(row):
    raw = cmds.scrollField(row["controls"], query=True, text=True)
    result = [name.strip() for name in raw.splitlines() if name.strip()]
    if not result or len(result) != len(set(result)):
        raise ValueError("AutoSkirt: each reader requires unique Driven controls")
    return result


def getSettings(row, control):
    return row["settings"].setdefault(control, {"startAngle": 10.0})



def sphereUvDomain(sphere):
    shape = skirtShape(sphere, "nurbsSurface")
    return {axis: (float(cmds.getAttr(shape + ".minValue" + axis)),
                   float(cmds.getAttr(shape + ".maxValue" + axis)))
            for axis in "UV"}


def normalizeSphereUv(sphere):
    """Normalize U/V without changing the Sphere orientation."""
    domain = sphereUvDomain(sphere)
    if all(abs(domain[axis][0]) < 1e-6 and abs(domain[axis][1] - 1.0) < 1e-6 for axis in "UV"):
        return domain
    shape = skirtShape(sphere, "nurbsSurface")
    world = cmds.xform(sphere, query=True, worldSpace=True, matrix=True)
    # Rebuild only the UV range.
    cmds.rebuildSurface(sphere, constructionHistory=False, replaceOriginal=True, rebuildType=0, direction=2, keepControlPoints=True, keepCorners=True, keepRange=0, degreeU=0, degreeV=0, spansU=int(cmds.getAttr(shape + ".spansU")), spansV=int(cmds.getAttr(shape + ".spansV")))
    domain = sphereUvDomain(sphere)
    if not all(abs(domain[axis][0]) < 1e-5 and abs(domain[axis][1] - 1.0) < 1e-5 for axis in "UV"):
        raise RuntimeError("AutoSkirt_: Maya did not normalize the Sphere U/V to 0-1")
    after = cmds.xform(sphere, query=True, worldSpace=True, matrix=True)
    if max(abs(float(a) - float(b)) for a, b in zip(world, after)) > 1e-5:
        raise RuntimeError("AutoSkirt_: Sphere world transform changed during UV rebuild")
    return domain


def rebuildSphereUVButton(*unused):
    """Normalize the listed Spheres from the form only."""
    spheres = []
    seen = set()
    for row in STATE["rows"]:
        name = cmds.textField(row["sphere"], query=True, text=True).strip()
        if not name:
            continue
        matches = cmds.ls(name, long=True, type="transform") or []
        if not matches:
            raise ValueError("AutoSkirt_: Sphere does not exist: " + name)
        if len(matches) != 1:
            raise ValueError("AutoSkirt_: Sphere name is ambiguous: " + name)
        sphere = matches[0]
        shapes = cmds.listRelatives(sphere, shapes=True, noIntermediate=True, fullPath=True, type="nurbsSurface") or []
        if len(shapes) != 1:
            raise ValueError("AutoSkirt_: Sphere must have one NURBS Surface: " + sphere)
        if sphere not in seen:
            seen.add(sphere)
            spheres.append(sphere)
    if not spheres:
        cmds.warning("AutoSkirt_: no existing Spheres to rebuild in the main form")
        return []

    cmds.undoInfo(openChunk=True, chunkName="AutoSkirt Sphere UV 0-1")
    try:
        domains = [(sphere, normalizeSphereUv(sphere)) for sphere in spheres]
    except Exception:
        cmds.undoInfo(closeChunk=True)
        cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)
    for sphere, domain in domains:
        print("AutoSkirt_: Sphere UV 0-1, orientation unchanged: {} {}".format(sphere, domain))
    return domains


def createSphereFromRow(row, *args):
    """Create the original AutoSkirt-style sphere as a standalone preview.

    Use the nearest Driven for radius, aim the surface-origin normal at End,
    tilt 20 degrees away from Driven centroid and rebuild U/V to 0-1.
    No Parent/SphereFollow constraints: the Func builder adds those on Run.
    """
    sphere_name = cmds.textField(row["sphere"], query=True, text=True).strip()
    start_name = cmds.textField(row["start"], query=True, text=True).strip()
    end_name = cmds.textField(row["end"], query=True, text=True).strip()
    if not sphere_name or not start_name or not end_name:
        cmds.warning("AutoSkirt Create Sphere: set Sphere Name, Start and End")
        return None
    if cmds.objExists(sphere_name):
        cmds.warning("AutoSkirt Create Sphere: already exists: " + sphere_name)
        return None
    try:
        driven_names = getControls(row)
    except ValueError as exc:
        cmds.warning(str(exc))
        return None

    def unique_transform(name):
        found = cmds.ls(name, long=True) or []
        if len(found) != 1 or cmds.nodeType(found[0]) not in ("transform", "joint"):
            raise ValueError("AutoSkirt Create Sphere: missing or ambiguous object: " + name)
        return found[0]

    start = unique_transform(start_name)
    end = unique_transform(end_name)
    drivens = [unique_transform(name) for name in driven_names]
    start_p = [float(x) for x in cmds.xform(start, query=True, worldSpace=True, rotatePivot=True)]
    end_p = [float(x) for x in cmds.xform(end, query=True, worldSpace=True, rotatePivot=True)]
    pivots = [[float(x) for x in cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)]
              for node in drivens]

    def vector_length(vector):
        return math.sqrt(sum(x * x for x in vector))

    def perpendicular(direction):
        candidate = min(((0.0, 1.0, 0.0), (1.0, 0.0, 0.0),
                         (0.0, 0.0, 1.0)),
                        key=lambda vector: abs(sum(a*b for a, b in zip(vector, direction))))
        dot = sum(a*b for a, b in zip(candidate, direction))
        tangent = [a - dot*b for a, b in zip(candidate, direction)]
        length = vector_length(tangent)
        return [value / length for value in tangent]

    direction = [b - a for a, b in zip(start_p, end_p)]
    length = vector_length(direction)
    if length < 1e-7:
        raise ValueError("AutoSkirt Create Sphere: Start and End must differ")
    radius = min(vector_length([a-b for a, b in zip(pivot, start_p)])
                 for pivot in pivots)
    if radius < 1e-6:
        raise ValueError("AutoSkirt Create Sphere: Driven must be away from Start")
    world_aim = [value / length for value in direction]
    centroid = [sum(p[i] for p in pivots) / len(pivots) for i in range(3)]
    toward = [centroid[i] - start_p[i] for i in range(3)]
    projection = sum(a*b for a, b in zip(toward, world_aim))
    sideways = [toward[i] - projection * world_aim[i] for i in range(3)]
    side_length = vector_length(sideways)
    if side_length < 1e-6:
        sideways = perpendicular(world_aim)
        side_length = vector_length(sideways)
    away = [-value / side_length for value in sideways]
    tilt = math.radians(20.0)  # Same default as RigAutoSkirt.
    tilted = [math.cos(tilt)*world_aim[i] + math.sin(tilt)*away[i]
              for i in range(3)]

    selection = cmds.ls(selection=True, long=True) or []
    context = cmds.currentCtx()
    prefix = re.sub(r"[^A-Za-z0-9_]", "_", sphere_name.rsplit("|", 1)[-1])
    sphere = None
    cmds.undoInfo(openChunk=True, chunkName="AutoSkirt Create Sphere")
    try:
        sphere = cmds.sphere(name=sphere_name, radius=radius, axis=(0, 1, 0),
                             polygon=0, constructionHistory=False)[0]
        shape = skirtShape(sphere, "nurbsSurface")
        domain = sphereUvDomain(sphere)
        u = domain["U"][0] + (domain["U"][1] - domain["U"][0]) * 0.002
        v = domain["V"][0] + (domain["V"][1] - domain["V"][0]) * 0.002
        origin_normal = [float(x) for x in cmds.pointOnSurface(
            shape, parameterU=u, parameterV=v, normalizedNormal=True)]
        magnitude = vector_length(origin_normal)
        if magnitude < 1e-7:
            raise RuntimeError("AutoSkirt Create Sphere: cannot read surface-origin normal")
        origin_normal = [x / magnitude for x in origin_normal]
        cmds.xform(sphere, worldSpace=True, translation=start_p)
        # Match the legacy surface-normal orientation, not the sphere's Z axis.
        target = cmds.spaceLocator(name=prefix + "_PreviewAim#")[0]
        try:
            cmds.xform(target, worldSpace=True,
                       translation=[start_p[i] + length * tilted[i] for i in range(3)])
            aim = cmds.aimConstraint(
                target, sphere, aimVector=origin_normal,
                upVector=perpendicular(origin_normal), worldUpType="vector",
                worldUpVector=perpendicular(tilted), maintainOffset=False)[0]
            cmds.delete(aim)
        finally:
            cmds.delete(target)
        # Freeze only rotation/scale: keep the Sphere pivot at Start. Func's
        # existing poseReaderCore constrains this very transform on Run.
        cmds.makeIdentity(sphere, apply=True, translate=False, rotate=True, scale=True)
        normalizeSphereUv(sphere)
    except Exception:
        cmds.undoInfo(closeChunk=True)
        cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)
    finally:
        if selection:
            cmds.select(selection, replace=True)
        else:
            cmds.select(clear=True)
        if cmds.currentCtx() != context:
            cmds.setToolTo(context)
    print("AutoSkirt Create Sphere: {} | radius {:.4f} | UV 0-1".format(
        sphere, radius))
    return sphere


def addRow(parent, record=None):
    record = record or {}
    raw_controls = record.get("joints", [])
    if isinstance(raw_controls, str):
        raw_controls = [x.strip() for x in raw_controls.splitlines() if x.strip()]
    saved_subs = record.get("subItems", [])
    settings = {c: {"startAngle": 10.0} for c in raw_controls}
    subs = {}
    for i, control in enumerate(raw_controls):
        entries = saved_subs[i] if i < len(saved_subs) else None
        subs[control] = normalizeSubItems(entries)
    saved_ref_values = record.get("refV", [])
    row = {"settings": settings, "subItems": subs,
           "referenceV": {control: float(v) for control, v in zip(raw_controls, saved_ref_values)}}
    frame = cmds.frameLayout(parent=parent, label="Pose Reader", collapsable=True, marginHeight=5, marginWidth=5)
    col = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    row["frame"] = frame
    rid = record.get("id") or "Knee{}".format(len(STATE["rows"]) + 1)
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    row["id"] = lineField(col, "Reader ID", rid, False)
    row["sphere"] = lineField(col, "Sphere Name",
                                record.get("sphere") or system + "_" + rid + "_Sphere",
                                False, action=partial(createSphereFromRow, row))
    row["parent"] = lineField(col, "Parent", record.get("parent", ""))
    row["start"] = lineField(col, "Start", record.get("start", ""))
    row["end"] = lineField(col, "End", record.get("end", ""))
    for key, label, default in (("follicleSize", "Follicle Display Size", 1.0),):
        line = cmds.rowLayout(parent=col, numberOfColumns=2, columnWidth2=(120, 165))
        cmds.text(parent=line, label=label)
        row[key] = cmds.floatField(parent=line, value=float(record.get(key, default)), precision=3, width=100)
        cmds.setParent("..")
    cmds.floatField(row["follicleSize"], edit=True, minValue=0.01, maxValue=100, changeCommand=partial(liveFollicleSize, row))
    line = cmds.rowLayout(parent=col, numberOfColumns=3, adjustableColumn=2, columnWidth3=(115, 180, 74))
    cmds.text(parent=line, label="Driven Controls")
    row["controls"] = cmds.scrollField(parent=line, height=75, text="\n".join(raw_controls), wordWrap=False)
    actions = cmds.columnLayout(parent=line, adjustableColumn=True, rowSpacing=4)
    cmds.button(parent=actions, label="Pick All", width=68, height=34, command=partial(pickControls, row["controls"]))
    cmds.button(parent=actions, label="Add", width=68, height=34, command=partial(addSelectedDrivens, row))
    cmds.setParent(col)
    line = cmds.rowLayout(parent=col, numberOfColumns=3, columnWidth3=(115, 115, 115))
    cmds.button(parent=line, label="Edit Sub Items", width=113, command=partial(editSubItems, row))
    cmds.button(parent=line, label="Mirror Reader", width=113, command=partial(mirrorRow, row))
    cmds.button(parent=line, label="Remove Reader", width=113, command=partial(removeRow, row))
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
    STATE["rows"].append(row)
    return row


def removeRow(row, *args):
    if row in STATE["rows"]:
        STATE["rows"].remove(row)
    if cmds.layout(row["frame"], exists=True):
        cmds.deleteUI(row["frame"])

def readUi():
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
        controls = getControls(row)
        reader = {
            "mode": "autoSphere",
            "id": cmds.textField(row["id"], query=True, text=True).strip(),
            "sphere": cmds.textField(row["sphere"], query=True, text=True).strip(),
            "parent": cmds.textField(row["parent"], query=True, text=True).strip(),
            "start": cmds.textField(row["start"], query=True, text=True).strip(),
            "end": cmds.textField(row["end"], query=True, text=True).strip(),
            "follicleSize": float(cmds.floatField(row["follicleSize"], query=True, value=True)),
            "equatorU": 0.5,
            "joints": controls,
            "subItems": [normalizeSubItems(row["subItems"].get(c)) for c in controls],
            "refV": ([row["referenceV"][c] for c in controls]
                     if all(c in row["referenceV"] for c in controls) else [])}
        if not all(reader.get(key) for key in ("id", "sphere", "parent", "start", "end")):
            raise ValueError("AutoSkirt: Reader ID, Sphere Name, Parent, Start and End required")
        cfg["items"].append(reader)
    if not cfg["items"]:
        raise ValueError("AutoSkirt: add at least one Pose Reader")
    return cfg


def saveSettings(data, *args):
    value = readUi()
    NLTA_General.writeJsonFile(dataPath(data), value)
    return value

def sceneRoot(value):
    return value["name"] + "_System"


def metaFromScene(value):
    root = sceneRoot(value)
    if not cmds.objExists(root) or not cmds.attributeQuery("patternData", node=root, exists=True):
        return None
    encoded = cmds.getAttr(root + ".patternData")
    try:
        saved = json.loads(encoded)
    except (TypeError, ValueError):
        return None
    return saved if isinstance(saved, dict) else None

def writeSceneMeta(root, meta):
    cmds.addAttr(root, longName="patternData", dataType="string")
    cmds.setAttr(root + ".patternData", json.dumps(meta, ensure_ascii=False), type="string")

def Load(data, listUI, *args):
    # Opening the AutoSkirt form closes its independent Sub Item editor.
    if cmds.window("NLTA_AutoSkirt_Alt_SubItems", exists=True): cmds.deleteUI("NLTA_AutoSkirt_Alt_SubItems")
    for child in cmds.layout(listUI, query=True, childArray=True) or []: cmds.deleteUI(child)
    STATE["top"], STATE["rows"], STATE["data"], STATE["listUI"] = {}, [], data, listUI
    # The JSON is authoritative for the Form. Built Maya attributes are only
    # read for Auto display and optional export baking, never to replace saved edits.
    config = getData(data)
    frame = cmds.frameLayout(parent=listUI, label="AutoSkirt Settings", collapsable=True, marginWidth=5, marginHeight=5)
    col = cmds.columnLayout(parent=frame, adjustableColumn=True)
    STATE["top"]["name"] = lineField(col, "System Name", config.get("name", "AutoSkirt_"), False)
    STATE["top"]["group"] = lineField(col, "Contain", config.get("group", "RigUtil"))
    cmds.setParent("..")
    cmds.setParent("..")
    holder = cmds.columnLayout(parent=listUI, adjustableColumn=True)
    STATE["holder"] = holder
    for entry in config["items"]:
        addRow(holder, entry)
    if not config["items"]:
        addRow(holder)


def restoreJsonLive(data, list_ui, reader_id=None, *args):
    """Discard unsaved widget edits, reload disk JSON, and reapply built Live.

    This never rewrites the source JSON or rebuilds a rig. The active Sub Item
    editor is reopened for the same Reader so restored values are visible.
    """
    saved = getData(data)
    if not saved.get("items"):
        cmds.warning("AutoSkirt Restore: no saved Pose Readers in JSON.")
        return False

    reopen = reader_id
    if reopen is None and cmds.window("NLTA_AutoSkirt_Alt_SubItems", exists=True):
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
            liveFollicleSize(row)
        except (RuntimeError, ValueError) as exc:
            skipped.append("{} display: {}".format(rid, exc))
        for control in getControls(row):
            for index in range(len(row["subItems"].get(control, []))):
                try:
                    if applyLiveSubItem(row, control, index,
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
        editSubItems(target)
    print("AutoSkirt Restore JSON + Live: {} Sub Item(s) updated; "
          "{} skipped. JSON unchanged.".format(updated, len(skipped)))
    if skipped:
        for message in skipped:
            print("[AutoSkirt Restore] " + message)
        cmds.warning("AutoSkirt Restore: {} item(s) have no matching " "built graph; see Script Editor.".format(len(skipped)))
    return {"updated": updated, "skipped": skipped}


def addEmpty(*args):
    addRow(STATE["holder"])


def readItems(config):
    return [(entry["id"], entry) for entry in config["items"]]


def buildAutoSkirtSystem(configuration):
    """Build independent Start/End auto readers with shared Scene Pattern metadata."""
    name = configuration.get("name", "AutoSkirt")
    group = configuration.get("group", "RigUtil")
    readers = readItems(configuration)
    # Store Reader metadata.
    system_root = cmds.createNode("network", name=name + "_System")
    result = {"root": system_root, "items": {}, "driven": {},
              "drivenReaders": {}, "masters": {}}
    for item_id, spec in readers:
        original_controls = list(spec["joints"])
        auto = AutoSkirtAutoSphere(
            parent=spec["parent"], start=spec["start"], end=spec["end"], drivens=original_controls,
            prefix=name + "_" + item_id,
            sphere_name=spec.get("sphere") or name + "_" + item_id + "_Sphere",
            sub_items=spec.get("subItems"),
            follicle_size=float(spec.get("follicleSize", 1.0)),
            rig_group=group,
            output_axis=str(spec.get("axis", configuration.get("axis", "rotateZ")))[-1],
            equator_u=0.5,
            raise_start_angle=float(spec.get("raiseStartAngle", 10.0)),
            ref_values=list(spec["refV"]) if spec.get(
                "_export_baked_refs", configuration.get("_export_baked_refs", False)) else None)
        spec["sphere"] = auto["sphere"].rsplit("|", 1)[-1]
        info = {"parent": auto["parent"], "sphere": spec["sphere"],
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
    config = getData(data)
    result = buildAutoSkirtSystem(config)
    # Save projected Ref V.
    refs = {}
    for reader in config["items"]:
        rid = reader["id"]
        ref_positions = result["items"][rid]["referenceUV"]
        reader["refV"] = [ref_positions[control][1] for control in reader["joints"]]
        refs[rid] = {}
        for control, (transform, _) in result["items"][rid]["follicles"].items():
            shape = cmds.listRelatives(transform, shapes=True, type="follicle", fullPath=True)[0]
            refs[rid][control] = [transform, shape]
    NLTA_General.writeJsonFile(dataPath(data), config)
    writeSceneMeta(result["root"], {"data": config, "refs": refs})
    cmds.select(clear=True)
    return result


def runFromForm(data, *args):
    saveSettings(data)
    result = Run(data)
    # Keep projected Ref values available if Sub Items are saved without reopening the Form.
    readers = {item["id"]: item for item in getData(data)["items"]}
    for row in STATE["rows"]:
        rid = cmds.textField(row["id"], query=True, text=True).strip()
        item = readers.get(rid, {})
        row["referenceV"] = dict(zip(item.get("joints", []), item.get("refV", [])))
        editor = row.get("subEditor")
        if editor and cmds.window(editor["window"], exists=True):
            editor["refresh"]()
    return result

def getBuiltData(config, bake_ref_v=False):
    """Read Live settings, preserving Auto defaults unless baking export Ref V."""
    result = json.loads(json.dumps(config))
    meta = metaFromScene(config)
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
                core_angle = skirtNodePrefix(
                    item["sphere"], control, sub_index) + "_Remap_Raise.outputMin"
                legacy_angle = "{}_{}_{:02d}_Sub{:02d}_AngleFromU.outputMin".format(
                    result["name"], rid, index + 1, sub_index)
                angle_plug = core_angle if cmds.objExists(core_angle) else legacy_angle
                if sub.get("reverseU", False) == original.get("reverseU", False) and cmds.objExists(angle_plug):
                    sub["reverseU"] = float(cmds.getAttr(angle_plug)) > 90
                sign_plug = (node + ".rotateSign" if sub_index == 1
                             else node + "." + prefix + "RotateSign")
                if sub.get("invertRotate", False) == original.get("invertRotate", False) and cmds.objExists(sign_plug):
                    sub["invertRotate"] = float(cmds.getAttr(sign_plug)) < 0
    return result

def compactMayaCalls(source):
    """Keep Maya commands on one line when the AST is unchanged."""
    import io
    import tokenize

    tree = ast.parse(source)
    lines = source.splitlines()
    commented = {token.start[0] for token in tokenize.generate_tokens(
        io.StringIO(source).readline) if token.type == tokenize.COMMENT}
    changes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return)):
            continue
        if node.end_lineno <= node.lineno:
            continue
        if any(number in commented for number in range(node.lineno, node.end_lineno + 1)):
            continue
        if not any(isinstance(child, ast.Call) and
                   isinstance(child.func, ast.Attribute) and
                   isinstance(child.func.value, ast.Name) and
                   child.func.value.id == "cmds" for child in ast.walk(node)):
            continue
        compact = ast.unparse(node)
        first, last = node.lineno - 1, node.end_lineno - 1
        if ("\n" in compact or lines[first][:node.col_offset].strip() or
                lines[last][node.end_col_offset:].strip()):
            continue
        changes.append((first, last, lines[first][:node.col_offset] + compact))
    for first, last, compact in sorted(changes, reverse=True):
        lines[first:last + 1] = [compact]
    output = "\n".join(lines)
    if ast.dump(ast.parse(output), include_attributes=False) != ast.dump(tree, include_attributes=False):
        return source

    # Keep one blank line at most between statements.
    compact_lines = []
    for line in output.splitlines():
        if line.strip() or (compact_lines and compact_lines[-1].strip()):
            compact_lines.append(line)
    result = "\n".join(compact_lines)
    return result if ast.dump(ast.parse(result), include_attributes=False) == ast.dump(
        tree, include_attributes=False) else output


def ExportPython(data, *args):
    config = getData(data) if data.get("_batch_export_from_saved") else saveSettings(data)
    payload = getBuiltData(config, bake_ref_v=True)
    meta = metaFromScene(config) or {}
    built_refs = meta.get("refs", {})
    for reader in payload["items"]:
        refs = built_refs.get(reader["id"], {})
        reader["_export_baked_refs"] = (
            len(reader.get("refV", [])) == len(reader["joints"])
            and all(control in refs for control in reader["joints"])
        )
    payload["_export_baked_refs"] = False
    functions = (readItems, skirtShape, skirtAttr, skirtFollicle, skirtOffset,
                 skirtNodePrefix, sphereUvDomain, poseReaderCore, skirtRigCore,
                 setupPoseReaderSystem, setupSkirtRigSystem, AutoSkirtAutoSphere,
                 buildAutoSkirtSystem)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions))

    class ExportCode(ast.NodeTransformer):
        def visit_Raise(self, node):
            return None

        def visit_Assert(self, node):
            return None

        def visit_Try(self, node):
            self.generic_visit(node)
            return node.body + node.orelse + node.finalbody

        def visit_If(self, node):
            self.generic_visit(node)
            return node if node.body else node.orelse

        def visit_For(self, node):
            self.generic_visit(node)
            return node if node.body else node.orelse

        def visit_While(self, node):
            self.generic_visit(node)
            return node if node.body else node.orelse

        def visit_Expr(self, node):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return None
            if (isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Attribute)
                    and isinstance(value.func.value, ast.Name)
                    and value.func.value.id == "cmds"
                    and value.func.attr == "warning"):
                return None
            return self.generic_visit(node)

        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            if not node.body:
                node.body = [ast.Pass()]
            return node

    tree = ExportCode().visit(tree)
    ast.fix_missing_locations(tree)
    source = compactMayaCalls(ast.unparse(tree))
    script = (
        "import maya.cmds as cmds\nimport math\nimport re\n\n"
        "AUTO_SKIRT_DATA = {}\n\n"
        "{}\n\n"
        "def main():\n"
        "    buildAutoSkirtSystem(AUTO_SKIRT_DATA)\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
    ).format(repr(payload), source)
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(dataPath(data)), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(script)
    return output


def OpenExportFolder(data, *args):
    directory = os.path.dirname(dataPath(data))
    if os.path.isdir(directory):
        os.startfile(directory)
    else:
        cmds.warning("AutoSkirt: export directory does not exist: " + directory)

def Form(data, *args):
    if cmds.window("NLTA_AutoSkirt_Alt_SubItems", exists=True): cmds.deleteUI("NLTA_AutoSkirt_Alt_SubItems")
    ui = NLTA_General.LoadModule("Scene_Form").Create(data)
    buttons = ui["buttonUI"]
    list_ui = ui["listUI"]
    cmds.rowColumnLayout(parent=buttons, numberOfColumns=4)
    cmds.button(label="Add", width=80, command=addEmpty)
    cmds.button(label="Save", width=80, command=partial(saveSettings, data))
    cmds.button(label="Run", width=80, command=partial(runFromForm, data))
    export_button = cmds.button(label="Export Py", width=95, command=partial(ExportPython, data))
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", command=partial(OpenExportFolder, data))
    cmds.setParent("..")
    cmds.button(parent=buttons, label="Rebuild Sphere UV 0-1 (Keep Orientation)", height=30, command=rebuildSphereUVButton)
    cmds.button(parent=buttons, label="Restore from JSON + Live", height=30, command=lambda *unused: restoreJsonLive(data, list_ui))
    Load(data, list_ui)

def skirtShape(transform, kind):
    return cmds.listRelatives(transform, shapes=True, noIntermediate=True, fullPath=True, type=kind)[0]


def skirtAttr(node, name, value, minimum=None, maximum=None):
    options = dict(longName=name, attributeType="double",
                   defaultValue=float(value), keyable=True)
    if minimum is not None:
        options["minValue"] = float(minimum)
    if maximum is not None:
        options["maxValue"] = float(maximum)
    cmds.addAttr(node, **options)
    return node + "." + name


def skirtFollicle(name, surface_shape, holder, u=None, v=None,
                  u_source=None, v_source=None, marker_size=None, color=17):
    # Follicle uses local surface and world matrix.
    shape = cmds.createNode("follicle", name=name + "Shape")
    transform = cmds.rename( cmds.listRelatives(shape, parent=True, fullPath=True)[0], name)
    transform = cmds.parent(transform, holder)[0]
    cmds.setAttr(transform + ".inheritsTransform", 0)
    shape = skirtShape(transform, "follicle")
    cmds.setAttr(shape + ".visibility", 0)
    cmds.connectAttr(surface_shape + ".local", shape + ".inputSurface")
    cmds.connectAttr(surface_shape + ".worldMatrix[0]", shape + ".inputWorldMatrix")
    cmds.connectAttr(shape + ".outTranslate", transform + ".translate")
    cmds.connectAttr(shape + ".outRotate", transform + ".rotate")
    if u_source:
        cmds.connectAttr(u_source, shape + ".parameterU")
    else:
        cmds.setAttr(shape + ".parameterU", float(u))
    if v_source:
        cmds.connectAttr(v_source, shape + ".parameterV")
    else:
        cmds.setAttr(shape + ".parameterV", float(v))
    if marker_size:
        marker = cmds.createNode("locator", name=name + "_MarkerShape", parent=transform)
        for axis in "XYZ":
            cmds.connectAttr(marker_size + ".outputX", marker + ".localScale" + axis)
        cmds.setAttr(marker + ".overrideEnabled", 1)
        cmds.setAttr(marker + ".overrideColor", color)
    return transform, shape


def skirtOffset(driven, tag):
    # Preserve the Driven hierarchy.
    matrix = cmds.xform(driven, query=True, worldSpace=True, matrix=True)
    old_parent = (cmds.listRelatives(driven, parent=True, fullPath=True) or [None])[0]
    space = cmds.createNode("transform", name=tag + "_Space")
    cmds.xform(space, worldSpace=True, matrix=matrix)
    if old_parent:
        space = cmds.parent(space, old_parent, absolute=True)[0]
    offset = cmds.createNode("transform", name=tag + "_DrivenOffset", parent=space)
    new_driven = cmds.parent(driven, offset, absolute=True)[0]
    new_driven = cmds.ls(new_driven, long=True)[0]
    return space, offset, new_driven


# Skin200 pose reader.
def poseReaderCore(poseReader, poseReader_constraint_target, closest_point_ref_object,
                   rig_group="RigUtil"):

    # Follow the reference object.
    target_loc_group = cmds.createNode("transform", n=f"{poseReader}_Target_Loc_Group", parent=rig_group)
    target_loc = cmds.spaceLocator(n=f"{poseReader}_Target_Loc")[0]
    target_loc = cmds.parent(target_loc, target_loc_group)[0]
    target_loc_shape = cmds.listRelatives(target_loc, shapes=True, fullPath=True)[0]
    cmds.parentConstraint(closest_point_ref_object, target_loc_group, mo=False)

    # Sphere constraint and UV.
    pose_reader = poseReader
    pose_reader_shape = cmds.listRelatives(pose_reader, shapes=True, fullPath=False)[0]
    cmds.parentConstraint(poseReader_constraint_target, pose_reader, mo=True)
    cpos = cmds.createNode("closestPointOnSurface", n=f"{poseReader}_cpos")
    cmds.connectAttr(f"{target_loc_shape}.worldPosition[0]", f"{cpos}.inPosition")
    cmds.connectAttr(f"{pose_reader_shape}.worldSpace[0]", f"{cpos}.inputSurface")

    # Closest point follicle.
    cp_follicleShape = cmds.createNode("follicle", name=f"{poseReader}_CP_follicleShape")
    cp_follicleTransform = cmds.listRelatives(cp_follicleShape, parent=True, fullPath=False)[0]
    cp_follicleTransform = cmds.rename(cp_follicleTransform, f"{poseReader}_CP_follicle")

    cmds.parent(cp_follicleTransform, rig_group)
    cmds.setAttr(f"{cp_follicleTransform}.inheritsTransform", 0)

    cmds.connectAttr(f"{pose_reader_shape}.local", f"{cp_follicleShape}.inputSurface")
    cmds.connectAttr(f"{pose_reader_shape}.worldMatrix[0]", f"{cp_follicleShape}.inputWorldMatrix")
    cmds.connectAttr(f"{cp_follicleShape}.outTranslate", f"{cp_follicleTransform}.translate")
    cmds.connectAttr(f"{cp_follicleShape}.outRotate", f"{cp_follicleTransform}.rotate")

    cmds.connectAttr(f"{cpos}.parameterU", f"{cp_follicleShape}.parameterU")
    cmds.connectAttr(f"{cpos}.parameterV", f"{cp_follicleShape}.parameterV")

    return cp_follicleShape, cpos


def skirtRigCore(pose_reader, cp_follicleShape, cpos, skirt_joints, ref_parameterV,
                 min_max_distance, raise_start_angle, rig_group="RigUtil"):
    """Ref/Equator distance and CP angle drive skirt raise."""

    pose_reader_shape = cmds.listRelatives(pose_reader, shapes=True, fullPath=False)[0]
    raise_influence_nodes = []

    # Joint raise influence.
    for i, skirt_joint in enumerate(skirt_joints):

        equator_follicles = []

        # Ref is fixed; Equator follows V.
        for follicle_type in ["ref", "equator"]:
            follicleShape = cmds.createNode("follicle", name=f"{pose_reader}_{skirt_joint}_{follicle_type}_follicleShape")
            follicleTransform = cmds.listRelatives(follicleShape, parent=True, fullPath=False)[0]
            follicleTransform = cmds.rename(follicleTransform, f"{pose_reader}_{skirt_joint}_{follicle_type}_follicle")

            equator_follicles.append(follicleTransform)
            cmds.parent(follicleTransform, rig_group)
            cmds.setAttr(f"{follicleTransform}.inheritsTransform", 0)

            cmds.connectAttr(f"{pose_reader_shape}.local", f"{follicleShape}.inputSurface")
            cmds.connectAttr(f"{pose_reader_shape}.worldMatrix[0]", f"{follicleShape}.inputWorldMatrix")
            cmds.connectAttr(f"{follicleShape}.outTranslate", f"{follicleTransform}.translate")
            cmds.connectAttr(f"{follicleShape}.outRotate", f"{follicleTransform}.rotate")

            cmds.setAttr(f"{follicleShape}.parameterU", 0.5)

            if follicle_type == "ref":
                cmds.setAttr(f"{follicleShape}.parameterV", ref_parameterV[i])
                cmds.addAttr(follicleTransform, ln="minDistance", at="double", min=0, max=2, dv=0, k=True)
                cmds.addAttr(follicleTransform, ln="maxDistance", at="double", min=0, max=2, dv=1.5, k=True)
                cmds.addAttr(follicleTransform, ln="raiseStartAngle", at="double", min=0, max=180, dv=10, k=True)
            else:
                cmds.connectAttr(f"{cpos}.parameterV", f"{follicleShape}.parameterV")

        # Closer follicles increase the raise weight.
        distance = cmds.createNode("distanceBetween", n=f"{pose_reader}_{skirt_joint}_Distance")
        remap_distance = cmds.createNode("remapValue", n=f"{pose_reader}_{skirt_joint}_Remap_Distance")

        cmds.connectAttr(f"{equator_follicles[0]}.worldMatrix[0]", f"{distance}.inMatrix1")
        cmds.connectAttr(f"{equator_follicles[1]}.worldMatrix[0]", f"{distance}.inMatrix2")

        cmds.connectAttr(f"{distance}.distance", f"{remap_distance}.inputValue")
        cmds.connectAttr(f"{equator_follicles[0]}.minDistance", f"{remap_distance}.inputMin")
        cmds.connectAttr(f"{equator_follicles[0]}.maxDistance", f"{remap_distance}.inputMax")
        cmds.setAttr(f"{remap_distance}.outputMin", 1)
        cmds.setAttr(f"{remap_distance}.outputMax", 0)

        # Convert U to raise angle.
        remap_raise = cmds.createNode("remapValue", n=f"{pose_reader}_{skirt_joint}_Remap_Raise")
        clamp_raise = cmds.createNode("clamp", n=f"{pose_reader}_{skirt_joint}_Clamp_Raise")
        pma_raise = cmds.createNode("plusMinusAverage", n=f"{pose_reader}_{skirt_joint}_pma_Raise")

        cmds.connectAttr(f"{cp_follicleShape}.parameterU", f"{remap_raise}.inputValue")
        cmds.setAttr(f"{remap_raise}.outputMin", 0)
        cmds.setAttr(f"{remap_raise}.outputMax", 180)

        cmds.connectAttr(f"{remap_raise}.outValue", f"{clamp_raise}.inputR")
        cmds.connectAttr(f"{equator_follicles[0]}.raiseStartAngle", f"{clamp_raise}.minR")
        cmds.setAttr(f"{clamp_raise}.maxR", 180)

        cmds.setAttr(f"{pma_raise}.operation", 2)
        cmds.connectAttr(f"{clamp_raise}.outputR", f"{pma_raise}.input1D[0]")
        cmds.connectAttr(f"{clamp_raise}.minR", f"{pma_raise}.input1D[1]")

        # Raise angle times distance weight.
        md_raise = cmds.createNode("multiplyDivide", n=f"{pose_reader}_{skirt_joint}_md_Raise")
        md_raise_influence = cmds.createNode("multiplyDivide", n=f"{pose_reader}_{skirt_joint}_md_RaiseInfluence")
        raise_influence_nodes.append(md_raise_influence)

        cmds.connectAttr(f"{pma_raise}.output1D", f"{md_raise}.input1X")
        cmds.connectAttr(f"{remap_distance}.outValue", f"{md_raise}.input2X")

        cmds.connectAttr(f"{md_raise}.outputX", f"{md_raise_influence}.input1X")

        # Joint settings.
        cmds.setAttr(f"{equator_follicles[0]}.minDistance", min_max_distance[i][0])
        cmds.setAttr(f"{equator_follicles[0]}.maxDistance", min_max_distance[i][1])
        cmds.setAttr(f"{equator_follicles[0]}.raiseStartAngle", raise_start_angle[i])

    return raise_influence_nodes


def setupPoseReaderSystem(parent, start, end, drivens, prefix, sphere_name,
                          follicle_size=1.0, equator_u=0.5,
                          rig_group="RigUtil"):
    # Set up the pose reader on the existing NURBS sphere.
    import math
    def vector_length(v):
        return math.sqrt(sum(float(x) ** 2 for x in v))
    def point_distance(a, b):
        return vector_length([x-y for x, y in zip(a, b)])
    paths = [cmds.ls(value, long=True)[0]
             for value in [parent, start, end] + list(drivens)]
    parent, start, end, drivens = paths[0], paths[1], paths[2], paths[3:]
    start_p = cmds.xform(start, query=True, worldSpace=True, rotatePivot=True)
    end_p = cmds.xform(end, query=True, worldSpace=True, rotatePivot=True)
    pivots = [cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)
              for node in drivens]
    direction = [b-a for a, b in zip(start_p, end_p)]
    length = vector_length(direction)
    if length < 1e-7 or not pivots:
        raise ValueError("AutoSkirt_: Start/End must differ and Driven cannot be empty")
    nearest = min(point_distance(start_p, pivot) for pivot in pivots)
    centroid = tuple(sum(float(p[i]) for p in pivots) / len(pivots)
                     for i in range(3))
    # Keep settings on a network node.
    root = cmds.createNode("network", name=prefix + "_ROOT")
    size_plug = skirtAttr(root, "follicleSize", follicle_size, 0.01, 100)
    marker_size = cmds.createNode("multiplyDivide", name=prefix + "_MarkerSize")
    cmds.connectAttr(size_plug, marker_size + ".input2X")

    # Read existing Sphere.
    spheres = cmds.ls(sphere_name, long=True, type="transform") or []
    if len(spheres) != 1:
        raise ValueError("AutoSkirt_: choose one existing NURBS Sphere")
    sphere = spheres[0]
    shape = skirtShape(sphere, "nurbsSurface")
    domain = sphereUvDomain(sphere)
    if any(abs(domain[axis][0]) > 1e-6 or
           abs(domain[axis][1] - 1.0) > 1e-6 for axis in "UV"):
        raise ValueError("AutoSkirt_: Sphere U/V must be 0-1")
    bounds = cmds.exactWorldBoundingBox(sphere)
    sphere_radius = max(bounds[3]-bounds[0], bounds[4]-bounds[1],
                        bounds[5]-bounds[2]) * 0.5
    cmds.setAttr(marker_size + ".input1X", sphere_radius * 0.045)
    sphere_frame = None
    tilt_direction = tuple(x / length for x in direction)
    

    # Locator and closest point follicle.
    source_reader = poseReaderCore
    cp_shape, cpos = source_reader(sphere.rsplit("|", 1)[-1], parent, end,
                                   rig_group=rig_group)
    cp = cmds.listRelatives(cp_shape, parent=True, fullPath=True)[0]
    
    cp_shape = skirtShape(cp, "follicle")
    cmds.setAttr(cp_shape + ".visibility", 0)
    cp_u = float(cmds.getAttr(cp_shape + ".parameterU"))
    cp_v = float(cmds.getAttr(cp_shape + ".parameterV"))
    neutral_moving, _ = skirtFollicle(
        prefix + "_NeutralMoving_Follicle", shape, rig_group,
        u=equator_u, v=cp_v, marker_size=marker_size, color=14)
    shared_u = skirtAttr(root, "equatorU", equator_u, 0, 1)
    skirtAttr(root, "neutralU", cp_u, 0, 1)
    skirtAttr(root, "neutralV", cp_v, 0, 1)
    master = skirtAttr(root, "autoSkirt", 1.0, 0, 2)
    skirtAttr(root, "skirtCore", 1.0)
    return dict(root=root, parent=parent, start=start, end=end, drivens=drivens,
                sphere=sphere, sphereFrame=sphere_frame, sphereShape=shape,
                tiltAwayDegrees=0.0,
                tiltDirection=tilt_direction, drivenCentroid=centroid,
                radius=sphere_radius, nearestDrivenDistance=nearest,
                follicleSize=float(follicle_size), folGroup=rig_group,
                markerSize=marker_size, cpos=cpos, uv=None,
                cpFollicle=cp, cpShape=cp_shape, movingFollicle=None,
                neutralMoving=neutral_moving, equatorU=equator_u,
                sharedU=shared_u, master=master, neutralUV=(cp_u, cp_v),
                domain=domain, rigGroup=rig_group)


def setupSkirtRigSystem(reader, sub_items=None, output_axis="Z",
                        raise_start_angle=10.0, ref_values=None):
    """Call the source's original per-joint graph, then route it through UI offsets."""
    import math
    drivens = reader["drivens"]
    prefix = reader["root"].rsplit("|", 1)[-1][:-5]
    shape = reader["sphereShape"]
    sphere_name = reader["sphere"].rsplit("|", 1)[-1]
    source_ids, sub_specs, parameters, distances, angles = [], [], [], [], []
    if sub_items is None:
        raise ValueError("AutoSkirt_: Sub Items must come from the configured Reader")
    if len(sub_items) != len(drivens):
        raise ValueError("AutoSkirt_: Sub Item groups must match Driven controls")
    if ref_values is not None and len(ref_values) != len(drivens):
        raise ValueError("AutoSkirt_: saved Ref V must match Driven controls")

    # Project Driven pivots to V.
    vmin, vmax = reader["domain"]["V"]
    probe = cmds.createNode("closestPointOnSurface", name=prefix + "_RefSampler")
    cmds.connectAttr(shape + ".worldSpace[0]", probe + ".inputSurface")
    projected = []
    for driven in drivens:
        pivot = cmds.xform(driven, query=True, worldSpace=True, rotatePivot=True)
        cmds.setAttr(probe + ".inPosition", *pivot, type="double3")
        v = float(cmds.getAttr(probe + ".parameterV"))
        projected.append(max(0.0, min(1.0, (v - vmin) / (vmax - vmin))))
    cmds.delete(probe)
    if ref_values is not None:
        projected = [float(value) for value in ref_values]

    # Build each Driven Sub Item.
    for index, entries in enumerate(sub_items):
        if not entries:
            raise ValueError("AutoSkirt_: at least one Sub Item is required per Driven")
        for sub_index, entry in enumerate(entries):
            spec = dict(axis=str(entry.get("axis", output_axis)).upper()[-1:],
                        outputType=str(entry.get("outputType", "rotate")).lower(),
                        reverseU=bool(entry.get("reverseU", False)),
                        invertRotate=bool(entry.get("invertRotate", False)),
                        strength=float(entry.get("strength", 1.0)),
                        startAngle=float(entry.get("startAngle", raise_start_angle)),
                        maxDistance=float(entry.get("maxDistance", 0.0)),
                        minDistance=float(entry.get("minDistance", 0.0)),
                        refV=entry.get("refV"))
            name = skirtNodePrefix(sphere_name, drivens[index],
                                      sub_index + 1)[len(sphere_name) + 1:]
            source_ids.append(name)
            sub_specs.append((index, sub_index, spec))
            value = projected[index] if spec["refV"] is None else float(spec["refV"])
            parameters.append(value)
            # Apply live settings after the graph.
            distances.append((0.0, 1.0))
            angles.append(spec["startAngle"])
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("AutoSkirt_: source Driven/Sub names must be unique")
    source_rig = skirtRigCore
    original_outputs = source_rig(
        sphere_name, reader["cpShape"], reader["cpos"], source_ids,
        parameters, distances, angles, rig_group=reader["rigGroup"])
    if len(original_outputs) != len(source_ids):
        raise RuntimeError("AutoSkirt_: the source rig returned incomplete outputs")

    records, base_refs = [], {}
    for (index, sub_index, spec), identifier, original_output, parameter in zip(
            sub_specs, source_ids, original_outputs, parameters):
        tag = "{}_{:02d}".format(prefix, index + 1)
        subtag = tag + "_Sub{:02d}".format(sub_index + 1)
        original_prefix = skirtNodePrefix(sphere_name, drivens[index],
                                             sub_index + 1)
        
        reference = original_prefix + "_ref_follicle"
        if sub_index == 0:
            base_refs[index] = reference
        # Add Ref locator markers.
        reference_shape = skirtShape(reference, "follicle")
        cmds.setAttr(reference_shape + ".visibility", 0)
        locator = cmds.createNode("locator", name=subtag + "_Ref_MarkerShape", parent=reference)
        for direction in "XYZ":
            cmds.connectAttr(reader["markerSize"] + ".outputX", locator + ".localScale" + direction)
        cmds.setAttr(locator + ".overrideEnabled", 1)
        cmds.setAttr(locator + ".overrideColor", 17)
        original_equator = original_prefix + "_equator_follicle"
        equator = original_equator
        if index == 0 and sub_index == 0:
            reader["movingFollicle"] = equator
        cmds.setAttr(skirtShape(equator, "follicle") + ".visibility", 0)
        
        renamed = {suffix: original_prefix + suffix for suffix in (
            "_Distance", "_Remap_Distance", "_Remap_Raise",
            "_Clamp_Raise", "_pma_Raise", "_md_Raise", "_md_RaiseInfluence")}
        records.append(dict(index=index, subIndex=sub_index,
                            tag=tag, subtag=subtag, spec=spec,
                            ref=reference, equator=equator,
                            core=renamed["_md_RaiseInfluence"],
                            raw=renamed["_md_Raise"],
                            weight=renamed["_Remap_Distance"],
                            angle=renamed["_Remap_Raise"],
                            distance=renamed["_Distance"],
                            parameter=parameter))

    # Each Sub Item keeps its settings on its own Ref.
    results = []
    for index, driven in enumerate(drivens):
        tag = "{}_{:02d}".format(prefix, index + 1)
        ref = base_refs[index]
        own = [record for record in records if record["index"] == index]
        other_refs = [value for slot, value in base_refs.items() if slot != index]
        reference_position = cmds.xform( ref, query=True, worldSpace=True, rotatePivot=True)
        auto_nearest = min(
            (math.sqrt(sum((float(a)-float(b))**2 for a,b in
                zip(reference_position, cmds.xform(other, query=True, worldSpace=True, rotatePivot=True))))
             for other in other_refs), default=reader["radius"])
        auto_nearest = max(auto_nearest, 0.001)
        current = cmds.ls(driven.rsplit("|", 1)[-1], long=True)[0]
        space, offset, current_driven = skirtOffset(current, tag)
        follow = current_driven + ".AutoFollow"
        if not cmds.objExists(follow):
            cmds.addAttr(current_driven, longName="AutoFollow", attributeType="double",
                         minValue=0, maxValue=2, defaultValue=1, keyable=True)
        channels, sub_results, sub_outputs = {}, [], {}
        for record in own:
            sub_index = record["subIndex"] + 1
            subtag = record["subtag"]
            suffix = "sub{:02d}".format(sub_index)
            spec = record["spec"]
            actual_ref = record["ref"]
            actual_shape = skirtShape(actual_ref, "follicle")
            
            auto_distance = auto_nearest
            if sub_index > 1:
                position = cmds.xform(actual_ref, query=True, worldSpace=True, rotatePivot=True)
                auto_distance = min(
                    (math.sqrt(sum((float(a)-float(b))**2 for a,b in
                        zip(position, cmds.xform(other, query=True, worldSpace=True, rotatePivot=True))))
                     for other in other_refs), default=reader["radius"])
                auto_distance = max(auto_distance, 0.001)
            skirtAttr(actual_ref, "autoMaxDistance", auto_distance, 0.001)
            ref_v = skirtAttr(actual_ref, "refV", record["parameter"], 0, 1)
            cmds.connectAttr(ref_v, actual_shape + ".parameterV", force=True)
            cmds.setAttr(actual_ref + ".raiseStartAngle", spec["startAngle"])
            actual_equator_shape = skirtShape(record["equator"], "follicle")
            cmds.connectAttr(reader["sharedU"], actual_equator_shape + ".parameterU", force=True)
            cmds.connectAttr(reader["sharedU"], actual_shape + ".parameterU", force=True)
            # Allow user distance ranges.
            cmds.addAttr(actual_ref + ".maxDistance", edit=True, hasMaxValue=False)
            cmds.addAttr(actual_ref + ".minDistance", edit=True, hasMaxValue=False)
            maximum = (spec["maxDistance"] if spec["maxDistance"] > 0 else auto_distance)
            if spec["minDistance"] >= maximum:
                raise ValueError("AutoSkirt_: Min Distance must be below Max Distance")
            cmds.setAttr(actual_ref + ".minDistance", spec["minDistance"])
            cmds.setAttr(actual_ref + ".maxDistance", maximum)
            strength = skirtAttr(actual_ref, "strength", spec["strength"], 0, 2)
            sign = skirtAttr(actual_ref, "rotateSign",
                             -1 if spec["invertRotate"] else 1, -1, 1)
            # Preserve CP angle and distance remap.
            cmds.setAttr(record["angle"] + ".outputMin", 180 if spec["reverseU"] else 0)
            cmds.setAttr(record["angle"] + ".outputMax", 0 if spec["reverseU"] else 180)
            neutral = cmds.createNode("distanceBetween", name=subtag + "_NeutralDistance")
            cmds.connectAttr(actual_ref + ".worldMatrix[0]", neutral + ".inMatrix1")
            cmds.connectAttr(reader["neutralMoving"] + ".worldMatrix[0]", neutral + ".inMatrix2")
            neutral_distance = float(cmds.getAttr(neutral + ".distance"))
            skirtAttr(actual_ref, "neutralDistance", neutral_distance, 0)
            neutral_value = float(cmds.getAttr(record["raw"] + ".outputX"))
            zero = cmds.createNode("plusMinusAverage", name=subtag + "_ZeroNeutral")
            cmds.setAttr(zero + ".operation", 2)
            cmds.connectAttr(record["raw"] + ".outputX", zero + ".input1D[0]")
            cmds.setAttr(zero + ".input1D[1]", neutral_value)
            cmds.connectAttr(zero + ".output1D", record["core"] + ".input1X", force=True)
            cmds.connectAttr(strength, record["core"] + ".input2X", force=True)
            follower = cmds.createNode("multiplyDivide", name=subtag + "_AutoFollow")
            cmds.connectAttr(record["core"] + ".outputX", follower + ".input1X")
            cmds.connectAttr(follow, follower + ".input2X")
            master = cmds.createNode("multiplyDivide", name=subtag + "_Master")
            cmds.connectAttr(follower + ".outputX", master + ".input1X")
            cmds.connectAttr(reader["master"], master + ".input2X")
            signed = cmds.createNode("multiplyDivide", name=subtag + "_Signed")
            cmds.connectAttr(master + ".outputX", signed + ".input1X")
            cmds.connectAttr(sign, signed + ".input2X")
            mute = cmds.createNode("multiplyDivide", name=subtag + "_MuteGate")
            cmds.connectAttr(signed + ".outputX", mute + ".input1X")
            cmds.setAttr(mute + ".input2X", 1)
            kind, axis = spec["outputType"], spec["axis"]
            if kind not in ("rotate", "translate") or axis not in "XYZ":
                raise ValueError("AutoSkirt_: invalid Sub Item channel")
            target = offset + "." + kind + axis
            channels.setdefault((kind, axis), []).append(mute + ".outputX")
            sub_outputs[suffix] = target
            sub_results.append(dict(ref=actual_ref, destination=target,
                                    axis=axis, outputType=kind,
                                    reverseU=spec["reverseU"], invertRotate=spec["invertRotate"],
                                    strength=spec["strength"], refV=record["parameter"],
                                    startAngle=spec["startAngle"], maxDistance=maximum,
                                    minDistance=spec["minDistance"],
                                    influenceDistance=record["distance"],
                                    distanceWeight=record["weight"],
                                     neutralValue=neutral_value, settings=actual_ref,
                                    raiseNode=record["raw"],
                                    muteGate=mute + ".input2X",
                                    output=mute + ".outputX"))
        outputs = {}
        for (kind, axis), signals in channels.items():
            if len(signals) > 1:
                summation = cmds.createNode( "plusMinusAverage", name=tag + "_" + kind.capitalize() + axis + "_Sum")
                for signal_index, signal in enumerate(signals):
                    cmds.connectAttr(signal, summation + ".input1D[{}]".format(signal_index))
                signal = summation + ".output1D"
            else:
                signal = signals[0]
            destination = offset + "." + kind + axis
            cmds.connectAttr(signal, destination)
            outputs[axis if kind == "rotate" else "translate" + axis] = destination
        outputs.update(sub_outputs)
        results.append(dict(driven=current_driven, space=space, offset=offset,
                            ref=ref, refV=float(cmds.getAttr(ref + ".refV")),
                            influenceDistance=sub_results[0]["influenceDistance"],
                            weight=sub_results[0]["distanceWeight"],
                            raiseNode=sub_results[0]["raiseNode"],
                            neutralValue=sub_results[0]["neutralValue"],
                            subItems=sub_results, outputs=outputs,
                            output=sub_results[0]["destination"]))
    return results


def AutoSkirtAutoSphere(start=None, end=None, drivens=None, prefix="AS_AUTO",
                        output_axis="Z", equator_u=0.5,
                        raise_start_angle=10.0, ref_values=None,
                        sphere_name=None, sub_items=None,
                        parent=None, follicle_size=1.0, rig_group="RigUtil"):
    # Set up the pose reader and skirt graph using the saved configuration.
    import re
    if parent is None and start is None and end is None and drivens is None:
        parent, start, end, *drivens = cmds.ls( selection=True, objectsOnly=True)
    if isinstance(drivens, str):
        drivens = [drivens]
    if sub_items is None:
        raise ValueError("AutoSkirt_: Sub Items must come from the configured Reader")
    prefix = re.sub(r"[^A-Za-z0-9_]", "_", str(prefix)).strip("_") or "AutoSkirt_"
    if prefix[0].isdigit():
        prefix = "AS_" + prefix
    reader = setupPoseReaderSystem(
        parent, start, end, drivens, prefix, sphere_name or prefix + "_Sphere",
        follicle_size=follicle_size, equator_u=equator_u,
        rig_group=rig_group)
    result = setupSkirtRigSystem(
        reader, sub_items=sub_items, output_axis=output_axis,
        raise_start_angle=raise_start_angle, ref_values=ref_values)
    return dict(root=reader["root"], parent=reader["parent"],
                sphere=reader["sphere"], sphereFrame=reader["sphereFrame"],
                sphereShape=reader["sphereShape"],
                tiltAwayDegrees=reader["tiltAwayDegrees"],
                tiltDirection=reader["tiltDirection"],
                drivenCentroid=reader["drivenCentroid"], radius=reader["radius"],
                nearestDrivenDistance=reader["nearestDrivenDistance"],
                start=reader["start"], end=reader["end"],
                neutralUV=reader["neutralUV"], equatorU=reader["equatorU"],
                closestPoint=reader["cpos"], normalizeUV=reader["uv"],
                cpFollicle=reader["cpFollicle"],
                movingFollicle=reader["movingFollicle"], driven=result)
