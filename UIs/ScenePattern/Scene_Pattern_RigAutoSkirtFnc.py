import os
import json
import inspect
import math
import re
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General

STATE = {"top": {}, "rows": []}


def DefaultSetting(path, *args):
    module_name = "Scene_Pattern_RigAutoSkirtFnc"
    return dict(ext="json", path=os.path.join(path, module_name + ".json"),
                moduleName=module_name, order=0, title="Rig Auto Skirt Fnc",
                name="Rig Auto Skirt Fnc", id=datetime.now().strftime("%Y%m%d%H%M%S"))


def dataPath(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def getData(data):
    path = dataPath(data)
    if not os.path.isfile(path):
        return {"version": 2, "name": "AutoSkirt_", "group": "RigUtil", "items": []}
    with open(path, encoding="utf-8") as stream:
        config = json.load(stream)
    return config if isinstance(config, dict) else {"version": 2, "group": "RigUtil", "items": []}


def writeData(data, config):
    with open(dataPath(data), "w", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, separators=(",", ":"))
    return config


def shortName(node):
    return node.rsplit("|", 1)[-1]


def jointName(control):
    name = shortName(control)
    return name[:-3] if name.endswith("_FK") else name


def referenceName(sphere, control, index=1):
    suffix = "" if index == 1 else "_Sub{:02d}".format(index)
    names = [sphere + "_" + name + suffix + "_ref_follicle" for name in (jointName(control), shortName(control))]
    return next((name for name in names if cmds.objExists(name)), names[0])


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
    for entries in result.get("subItems", []):
        for sub in entries:
            if sub.get("target"): sub["target"] = mirrorLrName(sub["target"])
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


def lineField(parent, label, initial, picker=True):
    cmds.rowLayout(parent=parent, numberOfColumns=3, adjustableColumn=2, columnWidth3=(105, 160, 55))
    cmds.text(label=label, align="left")
    widget = cmds.textField(text=str(initial))
    if picker:
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
        weight = float(entry.get("weight", strength))
        if not math.isfinite(weight):
            raise ValueError("AutoSkirt: Weight must be finite")
        # Migrate signed weights from the previous Fnc version.
        if weight < 0:
            weight, invert = -weight, True
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
                      "invertRotate": invert, "strength": strength, "weight": weight,
                      "startAngle": start, "maxDistance": max_distance,
                      "minDistance": min_distance, "refV": ref_v}
        if entry.get("target"): normalized["target"] = entry["target"]
        for key in ("extraOffsetMatrix", "extraOffsetObject"):
            if entry.get(key): normalized[key] = entry[key]
        result.append(normalized)
    return result


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


def setFollicleDisplaySize(sphere, size):
    if not cmds.objExists(sphere): return
    bounds = cmds.exactWorldBoundingBox(sphere)
    radius = max(bounds[i+3] - bounds[i] for i in range(3)) * 0.5
    marker_size = radius * 0.045 * size
    follicles = cmds.ls(sphere + "_*_follicle", type="transform", long=True) or []
    for follicle in follicles:
        if not cmds.listRelatives(follicle, shapes=True, type="follicle"): continue
        name = shortName(follicle) + "_DisplayShape"
        marker = follicle + "|" + name
        if not cmds.objExists(marker):
            marker = cmds.createNode("locator", name=name, parent=follicle)
        cmds.setAttr(marker + ".localScale", marker_size, marker_size, marker_size, type="double3")


def liveFollicleSize(row, *args):
    sphere = shortName(cmds.textField(row["sphere"], q=True, text=True).strip())
    size = cmds.floatSliderGrp(row["follicleSize"], q=True, value=True)
    if sphere: setFollicleDisplaySize(sphere, size)


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
           "referenceV": {control: float(v) for control, v in zip(raw_controls, saved_ref_values) if v is not None}}
    frame = cmds.frameLayout(parent=parent, label="Pose Reader", collapsable=True, marginHeight=5, marginWidth=5)
    col = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    row["frame"] = frame
    rid = record.get("id") or "Knee{}".format(len(STATE["rows"]) + 1)
    system = cmds.textField(STATE["top"]["name"], query=True, text=True).strip()
    row["id"] = lineField(col, "Reader ID", rid, False)
    row["sphere"] = lineField(col, "Sphere Name",
                                record.get("sphere") or system + "_" + rid + "_Sphere", False)
    row["attributeName"] = lineField(col, "Attribute Name", record.get("attributeName", "autoShoulderGuard"), False)
    row["parent"] = lineField(col, "Parent", record.get("parent", ""))
    row["start"] = lineField(col, "Start", record.get("start", ""))
    row["end"] = lineField(col, "End", record.get("end", ""))
    size = float(record.get("follicleSize", 1.0))
    row["follicleSize"] = cmds.floatSliderGrp(parent=col, label="Follicle Display Size", field=True, minValue=0.01, maxValue=max(2.0, size), fieldMinValue=0.01, fieldMaxValue=100, value=size, precision=3, step=0.01, columnWidth3=(145, 85, 210), adjustableColumn3=3, changeCommand=partial(liveFollicleSize, row), dragCommand=partial(liveFollicleSize, row))
    line = cmds.rowLayout(parent=col, numberOfColumns=3, adjustableColumn=2, columnWidth3=(115, 180, 74))
    cmds.text(parent=line, label="Driven Controls")
    row["controls"] = cmds.scrollField(parent=line, height=75, text="\n".join(raw_controls), wordWrap=False)
    actions = cmds.columnLayout(parent=line, adjustableColumn=True, rowSpacing=4)
    cmds.button(parent=actions, label="Pick All", width=68, height=34, command=partial(pickControls, row["controls"]))
    cmds.button(parent=actions, label="Add", width=68, height=34, command=partial(addSelectedDrivens, row))
    cmds.setParent(col)
    line = cmds.rowLayout(parent=col, numberOfColumns=4,
                         columnWidth4=(90, 90, 90, 90))
    cmds.button(parent=line, label="Edit Sub Items", width=88, command=partial(editSubItems, row))
    cmds.button(parent=line, label="Mirror Reader", width=88, command=partial(mirrorRow, row))
    cmds.button(parent=line, label="Remove Reader", width=88, command=partial(removeRow, row))
    cmds.button(parent=line, label="Create Sphere", width=88,
                annotation="Create and aim a NURBS sphere; rebuild its UV to 0-1",
                command=partial(createSphereFromRow, row))
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")
    STATE["rows"].append(row)
    return row


def removeRow(row, *args):
    editor = row.pop("subEditor", None)
    if editor and cmds.window(editor["window"], exists=True):
        cmds.deleteUI(editor["window"])
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
            "follicleSize": float(cmds.floatSliderGrp(row["follicleSize"], q=True, value=True)),
            "attributeName": cmds.textField(row["attributeName"], query=True, text=True).strip(),
            "equatorU": 0.5,
            "joints": controls,
            "subItems": [normalizeSubItems(row["subItems"].get(c)) for c in controls],
            "refV": [row["referenceV"].get(c) for c in controls]}
        if not all(reader.get(key) for key in ("id", "sphere", "parent", "end")):
            raise ValueError("AutoSkirt: Reader ID, Sphere Name, Parent and End required")
        cfg["items"].append(reader)
    if not cfg["items"]:
        raise ValueError("AutoSkirt: add at least one Pose Reader")
    return cfg


def addEmpty(*args):
    addRow(STATE["holder"])


def skirtShape(transform, kind):
    return cmds.listRelatives(transform, shapes=True, noIntermediate=True, fullPath=True, type=kind)[0]


def legacyConfig(config):
    # Accept the original nested JSON and the previous RigAutoSkirtFnc flat JSON.
    result = json.loads(json.dumps(config))
    result.setdefault("name", "AutoSkirt_")
    result.setdefault("group", "RigUtil")
    for reader in result.get("items", []):
        if "drivens" not in reader:
            if isinstance(reader.get("joints"), str):
                reader["joints"] = [name.strip() for name in reader["joints"].splitlines() if name.strip()]
            continue
        groups = {}
        for spec in reader.pop("drivens"):
            control = spec["control"]
            groups.setdefault(control, []).append(dict(
                axis=spec.get("output", "rotateZ")[-1], outputType=spec.get("output", "rotateZ")[:-1],
                invertRotate=spec.get("invertRotate", False),
                weight=spec.get("weight", spec.get("strength", 1.0)),
                target=spec.get("target", ""), refV=spec.get("refV"),
                minDistance=spec.get("minDistance", 0), maxDistance=spec.get("maxDistance", 0),
                startAngle=spec.get("startAngle", 10)))
        reader["joints"] = list(groups)
        reader["subItems"] = list(groups.values())
        reader.setdefault("start", "")
    return result


def saveSettings(data, *args):
    return writeData(data, readUi())


def liveRef(row, control, index):
    sphere = shortName(cmds.textField(row["sphere"], q=True, text=True).strip())
    suffix = "" if index == 0 else "_Sub{:02d}".format(index+1)
    prefix = sphere + "_" + jointName(control) + suffix
    refs = cmds.ls(prefix + "_ref_follicle", long=True, type="transform") or []
    if len(refs) != 1: return None
    ref = refs[0]
    shapes = cmds.listRelatives(ref, shapes=True, noIntermediate=True, type="follicle", fullPath=True) or []
    if len(shapes) != 1: return None
    if not cmds.isConnected(ref + ".minDistance", prefix + "_Remap_Distance.inputMin"): return None
    return ref, shapes[0]


def pickRef(row, control, index, *args):
    ref = liveRef(row, control, index)
    if ref:
        cmds.select(ref[0], replace=True)
    else:
        cmds.warning("RigAutoSkirtFnc: Ref not built for {} Sub {:02d}".format(control, index+1))


def liveAutoValue(row, control, index, key):
    import maya.api.OpenMaya as om
    sphere = shortName(cmds.textField(row["sphere"], q=True, text=True).strip())
    selection = om.MSelectionList()
    selection.add(skirtShape(sphere, "nurbsSurface"))
    surface = om.MFnNurbsSurface(selection.getDagPath(0))
    if key == "refV":
        if control in row["referenceV"]: return row["referenceV"][control]
        pos = cmds.xform(shortName(control), q=True, ws=True, rp=True)
        _, _, v = surface.closestPoint(om.MPoint(*pos), space=om.MSpace.kWorld)
        return v
    ref = liveRef(row, control, index)
    point = surface.getPointAtParam(0.5, cmds.getAttr(ref[1] + ".parameterV"), om.MSpace.kWorld)
    distances = []
    for other in getControls(row):
        if shortName(other) == shortName(control): continue
        for i, sub in enumerate(row["subItems"].get(other, normalizeSubItems(None))):
            other_ref = liveRef(row, other, i)
            if other_ref:
                v = cmds.getAttr(other_ref[1] + ".parameterV")
                distances.append(point.distanceTo(surface.getPointAtParam(0.5, v, om.MSpace.kWorld)))
    bounds = cmds.exactWorldBoundingBox(sphere)
    radius = max(bounds[i+3] - bounds[i] for i in range(3)) * 0.5
    return max(min(distances, default=radius), 0.001)


def applyLiveValue(row, control, index, key):
    ref = liveRef(row, control, index)
    if not ref: return False
    spec = row["subItems"][control][index]
    plug = ref[1] + ".parameterV" if key == "refV" else ref[0] + "." + {
        "minDistance": "minDistance", "maxDistance": "maxDistance", "startAngle": "raiseStartAngle"}[key]
    value = spec[key]
    if (key == "refV" and value is None) or (key == "maxDistance" and value == 0):
        value = liveAutoValue(row, control, index, key)
    if key in ("minDistance", "maxDistance"):
        minimum = value if key == "minDistance" else cmds.getAttr(ref[0] + ".minDistance")
        maximum = value if key == "maxDistance" else cmds.getAttr(ref[0] + ".maxDistance")
        if not (math.isfinite(minimum) and math.isfinite(maximum) and 0 <= minimum < maximum):
            raise ValueError("Distance requires 0 <= Min < Max (Min={}, Max={})".format(minimum, maximum))
        limit = cmds.attributeQuery(key, node=ref[0], maximum=True)[0]
        if value > limit:
            cmds.addAttr(plug, edit=True, maxValue=max(3 if key == "minDistance" else 5, value))
    if key == "refV" and not 0 <= value <= 1:
        raise ValueError("Ref V must be 0-1")
    if key == "startAngle" and not 0 <= value <= 180:
        raise ValueError("Start Angle must be 0-180")
    cmds.setAttr(plug, value)
    return True


def weightNodeName(sphere, control, index):
    suffix = "" if index == 0 else "_Sub{:02d}".format(index+1)
    return shortName(sphere) + "_" + jointName(control) + suffix + "_Weight_MD"


def applyLiveWeight(row, control, index):
    sphere = cmds.textField(row["sphere"], q=True, text=True).strip()
    node = weightNodeName(sphere, control, index)
    if not cmds.objExists(node): return False
    raw = node[:-len("_Weight_MD")] + "_md_RaiseInfluence.outputX"
    if not cmds.isConnected(raw, node + ".input1X"): return False
    cmds.setAttr(node + ".input2X", row["subItems"][control][index]["weight"])
    return True


def editSubItems(row, *args):
    controls = getControls(row)
    window = "NLTA_RigAutoSkirtFnc_SubItems"
    for other in STATE["rows"]:
        previous = other.pop("subEditor", None)
        if previous and cmds.window(window, exists=True) and callable(previous.get("sync")):
            previous["sync"]()
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    window = cmds.window(window, title="RigAutoSkirtFnc - Driven Sub Items", widthHeight=(550, 555))
    body = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    scroll = cmds.scrollLayout(parent=body, childResizable=True, height=455)
    holder = cmds.columnLayout(parent=scroll, adjustableColumn=True, rowSpacing=4)
    editor = {"window": window, "widgets": {}, "drawing": False}
    row["subEditor"] = editor
    for control in controls:
        row["subItems"].setdefault(control, normalizeSubItems(None))

    def readStructure(fields):
        return dict(axis=cmds.optionMenu(fields["axis"], q=True, value=True),
                    outputType=cmds.optionMenu(fields["outputType"], q=True, value=True).lower(),
                    invertRotate=cmds.checkBox(fields["invert"], q=True, value=True),
                    target=cmds.textField(fields["target"], q=True, text=True).strip())

    def readNumber(fields, key):
        value = cmds.floatSliderGrp(fields[key], q=True, value=True)
        return None if key == "refV" and value < 0 else value

    def markTopologyDirty(control, *unused):
        row.setdefault("liveTopologyDirty", set()).add(control)

    def sync():
        # Read all fields only when saving or rebuilding the editor.
        updates = {}
        for control, widgets in editor["widgets"].items():
            entries = []
            for sub, fields in zip(row["subItems"][control], widgets):
                candidate = dict(sub, **readStructure(fields))
                for key in ("refV", "minDistance", "maxDistance", "startAngle", "weight"):
                    candidate[key] = readNumber(fields, key)
                entries.append(candidate)
            updates[control] = normalizeSubItems(entries)
        row["subItems"].update(updates)

    def live(control, index, key, *args):
        if editor["drawing"]: return
        fields = editor["widgets"][control][index]
        previous = row["subItems"][control][index]
        value = args[0] if args and isinstance(args[0], (int, float)) and not isinstance(args[0], bool) else readNumber(fields, key)
        if key == "refV" and value is not None and value < 0: value = None
        candidate = dict(previous, **{key: value})
        try:
            candidate = normalizeSubItems([candidate])[0]
            row["subItems"][control][index] = candidate
            # Numeric edits target the existing named nodes, independent of pending output settings.
            if control in row.get("liveTopologyDirty", set()):
                cmds.warning("RigAutoSkirtFnc: Sub Item indices changed; numeric value saved for next Run/Export.")
                return
            applied = applyLiveWeight(row, control, index) if key == "weight" else applyLiveValue(row, control, index, key)
            if not applied:
                cmds.warning("RigAutoSkirtFnc: node not built; saved UI value will be used on Run/Export.")
        except (ValueError, RuntimeError) as exc:
            row["subItems"][control][index] = previous
            value = previous[key]
            cmds.floatSliderGrp(fields[key], e=True, value=-1 if value is None else value)
            cmds.warning("RigAutoSkirtFnc Live: " + str(exc))

    def add(control, *unused):
        sync()
        row["subItems"][control].append(normalizeSubItems(None)[0])
        draw()

    def remove(control, index, *unused):
        sync()
        if len(row["subItems"][control]) > 1:
            markTopologyDirty(control)
            row["subItems"][control].pop(index)
            draw()

    def reset(control, index, *unused):
        sync()
        sub = row["subItems"][control][index]
        sub.update(reverseU=False)
        sub.pop("extraOffsetMatrix", None)
        sub.pop("extraOffsetObject", None)
        draw()

    def draw():
        editor["drawing"] = True
        for child in cmds.layout(holder, q=True, childArray=True) or []:
            cmds.deleteUI(child)
        editor["widgets"] = {}
        for control in controls:
            frame = cmds.frameLayout(parent=holder, label=control, collapsable=True, marginWidth=6)
            column = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=4)
            editor["widgets"][control] = []
            for index, sub in enumerate(row["subItems"][control]):
                item = cmds.frameLayout(parent=column, label="Sub Item {:02d}".format(index+1), collapsable=True)
                col = cmds.columnLayout(parent=item, adjustableColumn=True, rowSpacing=4)
                fields = {"target": lineField(col, "Target", sub.get("target") or shortName(control) + "_Target")}
                line = cmds.rowLayout(parent=col, numberOfColumns=2, columnWidth2=(105, 160))
                cmds.text(parent=line, label="Output Type")
                fields["outputType"] = cmds.optionMenu(parent=line)
                for output_type in ("Rotate", "Translate"): cmds.menuItem(parent=fields["outputType"], label=output_type)
                cmds.optionMenu(fields["outputType"], e=True, value=sub["outputType"].capitalize())
                line = cmds.rowLayout(parent=col, numberOfColumns=2, columnWidth2=(105, 160))
                cmds.text(parent=line, label="Axis")
                fields["axis"] = cmds.optionMenu(parent=line)
                for axis in "XYZ": cmds.menuItem(parent=fields["axis"], label=axis)
                cmds.optionMenu(fields["axis"], e=True, value=sub["axis"])
                fields["invert"] = cmds.checkBox(parent=col, label="Invert Output", value=sub["invertRotate"])
                ref = liveRef(row, control, index)
                line = cmds.rowLayout(parent=col, numberOfColumns=2, adjustableColumn=1, columnWidth2=(365, 90))
                cmds.textField(parent=line, editable=False, text=shortName(ref[0]) if ref else "Ref not built")
                cmds.button(parent=line, label="Pick Ref", command=partial(pickRef, row, control, index))
                distance_max = sub["maxDistance"]
                if distance_max == 0 and ref:
                    distance_max = cmds.getAttr(ref[0] + ".maxDistance")
                distance_range = max(1.0, distance_max, sub["minDistance"] * 1.5)
                weight_range = max(2.0, sub["weight"])
                ranges = (
                    ("weight", "Weight", 0, weight_range, 0, max(1000000.0, weight_range), 8, 0.001),
                    ("refV", "Ref V (-1 Auto)", -1 if sub["refV"] is None else 0, 1, -1, 1, 6, 0.001),
                    ("startAngle", "Start Angle", 0, 179.99, 0, 179.999999, 6, 0.1),
                    ("minDistance", "Min Distance", 0, distance_range, 0, max(1000000.0, distance_range), 6, 0.001),
                    ("maxDistance", "Max Distance", 0, distance_range * 2, 0, max(1000000.0, distance_range * 2), 6, 0.001))
                for key, label, minimum, maximum, field_min, field_max, precision, step in ranges:
                    value = -1 if sub[key] is None else sub[key]
                    fields[key] = cmds.floatSliderGrp(parent=col, label=label, field=True, minValue=minimum, maxValue=max(maximum, value), fieldMinValue=field_min, fieldMaxValue=max(field_max, value), value=value, precision=precision, step=step, columnWidth3=(145, 85, 250), adjustableColumn3=3)
                unsupported = unsupportedSettings(sub)
                if unsupported:
                    cmds.text(parent=col, label="Legacy: " + ", ".join(unsupported), align="left")
                    cmds.button(parent=col, label="Reset unsupported settings", command=partial(reset, control, index))
                actions = cmds.rowLayout(parent=col, numberOfColumns=2)
                cmds.button(parent=actions, label="Remove Sub Item", command=partial(remove, control, index))
                cmds.button(parent=actions, label="+ Add Sub Item", command=partial(add, control))
                editor["widgets"][control].append(fields)
        # Bind only after all widgets and their initial values exist.
        for control, widgets in editor["widgets"].items():
            for index, fields in enumerate(widgets):
                for key in ("weight", "refV", "startAngle", "minDistance", "maxDistance"):
                    callback = partial(live, control, index, key)
                    cmds.floatSliderGrp(fields[key], e=True, changeCommand=callback, dragCommand=callback)
        editor["drawing"] = False
    def finish(*unused):
        sync()
        saveSettings(STATE["data"])
    editor["sync"] = sync
    draw()
    cmds.text(parent=body, label="Live: Weight, Ref V, Min/Max Distance, Start Angle.", align="left")
    cmds.text(parent=body, label="Numeric edits affect built nodes; Add/Remove/Type/Axis/Target/Invert apply on next Run.", align="left")
    cmds.button(parent=body, label="Save Sub Items", height=28, command=finish)
    cmds.showWindow(window)


def unsupportedSettings(sub):
    # Legacy Strength is ignored.
    result = []
    if sub.get("reverseU"): result.append("Reverse U")
    if sub.get("extraOffsetMatrix") or sub.get("extraOffsetObject"): result.append("Extra Offset")
    return result


def convertConfig(config):
    if config.get("group", "RigUtil") != "RigUtil":
        raise ValueError("RigAutoSkirtFnc: original Diana core requires RigUtil. Set Contain to RigUtil in JSON.")
    result = {"version": 2, "group": "RigUtil", "items": []}
    items = legacyConfig(config).get("items", [])
    for item in items:
        reader = {key: item.get(key, "") for key in ("id", "sphere", "parent", "end")}
        reader["attributeName"] = item.get("attributeName", "autoShoulderGuard")
        reader["drivens"] = []
        refs = item.get("refV", [])
        for i, control in enumerate(item.get("joints", [])):
            entries = item.get("subItems", [])
            for j, sub in enumerate(normalizeSubItems(entries[i] if i < len(entries) else None)):
                unsupported = unsupportedSettings(sub)
                if unsupported:
                    raise ValueError("RigAutoSkirtFnc: {} Sub {:02d}: unsupported original-core settings: {}".format(control, j+1, ", ".join(unsupported)))
                v = sub.get("refV")
                if v is None and i < len(refs): v = refs[i]
                reader["drivens"].append(dict(control=control, target=sub.get("target") or shortName(control)+"_Target",
                    output=sub["outputType"]+sub["axis"], refV=v, minDistance=sub["minDistance"],
                    maxDistance=sub["maxDistance"], startAngle=sub["startAngle"],
                    weight=sub["weight"], invertRotate=sub["invertRotate"]))
        result["items"].append(reader)
    return result


def Load(data, listUI, *args):
    for child in cmds.layout(listUI, q=True, childArray=True) or []: cmds.deleteUI(child)
    if cmds.window("NLTA_RigAutoSkirtFnc_SubItems", exists=True): cmds.deleteUI("NLTA_RigAutoSkirtFnc_SubItems")
    STATE["top"], STATE["rows"], STATE["data"], STATE["listUI"] = {}, [], data, listUI
    config = legacyConfig(getData(data))
    STATE["group"] = config["group"]
    frame = cmds.frameLayout(parent=listUI, label="AutoSkirt Settings", collapsable=True, marginWidth=5)
    col = cmds.columnLayout(parent=frame, adjustableColumn=True)
    STATE["top"]["name"] = lineField(col, "System Name", config["name"], False)
    STATE["top"]["group"] = lineField(col, "Contain", STATE["group"])
    cmds.text(parent=col, label="Original core requires RigUtil", align="left")
    STATE["holder"] = cmds.columnLayout(parent=listUI, adjustableColumn=True)
    for entry in config["items"]: addRow(STATE["holder"], entry)
    if not config["items"]: addRow(STATE["holder"])


def importJson(data, *args):
    paths = cmds.fileDialog2(fileMode=1, fileFilter="JSON (*.json)", caption="Import AutoSkirtFunc JSON")
    if paths:
        with open(paths[0], encoding="utf-8") as stream:
            config = legacyConfig(json.load(stream))
        writeData(data, config)
        Load(data, STATE["listUI"])


def Form(data, *args):
    ui = NLTA_General.LoadModule("Scene_Form").Create(data)
    buttons = ui["buttonUI"]
    row = cmds.rowColumnLayout(parent=buttons, numberOfColumns=5)
    cmds.button(parent=row, label="Add", command=addEmpty)
    cmds.button(parent=row, label="Import JSON", command=partial(importJson, data))
    cmds.button(parent=row, label="Save", command=partial(saveSettings, data))
    cmds.button(parent=row, label="Run", command=partial(runFromForm, data))
    cmds.button(parent=row, label="Export Py", command=partial(ExportPython, data))
    cmds.button(parent=buttons, label="Rebuild Sphere UV 0-1 (Keep Orientation)", command=rebuildSphereUVButton)
    cmds.text(parent=buttons, label="Original Diana / Akali export. Save then Run on clean rig.", align="left")
    Load(data, ui["listUI"])


def resolve(reader):
    import maya.api.OpenMaya as om
    sphere = shortName(reader["sphere"])
    shape = cmds.listRelatives(sphere, shapes=True, noIntermediate=True, type="nurbsSurface", fullPath=True)[0]
    selection = om.MSelectionList()
    selection.add(shape)
    surface = om.MFnNurbsSurface(selection.getDagPath(0))
    if any(abs(cmds.getAttr(shape + "." + attr) - expected) > 1e-6 for attr, expected in (
            ("minValueU", 0), ("maxValueU", 1), ("minValueV", 0), ("maxValueV", 1))):
        raise ValueError("Rig Auto Skirt Fnc: sphere UV must be 0-1: " + sphere)
    specs = reader["drivens"]
    values = []
    points = []
    counts = {}
    ref_names = []
    for spec in specs:
        control = shortName(spec["control"])
        counts[control] = counts.get(control, 0) + 1
        ref = referenceName(sphere, control, counts[control])
        ref_names.append(ref)
        v = spec.get("refV")
        if v is None or v < 0:
            if cmds.objExists(ref + ".refV"):
                v = cmds.getAttr(ref + ".refV")
            elif cmds.objExists(ref):
                follicle = cmds.listRelatives(ref, shapes=True, type="follicle")[0]
                v = cmds.getAttr(follicle + ".parameterV")
            else:
                pos = cmds.xform(control, q=True, ws=True, rp=True)
                _, _, v = surface.closestPoint(om.MPoint(*pos), space=om.MSpace.kWorld)
        v = float(v)
        if not 0 <= v <= 1:
            raise ValueError("Rig Auto Skirt Fnc: Ref V must be 0-1: " + control)
        values.append(v)
        points.append(surface.getPointAtParam(0.5, v, om.MSpace.kWorld))
    bounds = cmds.exactWorldBoundingBox(sphere)
    radius = max(bounds[i+3]-bounds[i] for i in range(3)) * 0.5
    ranges = []
    for index, spec in enumerate(specs):
        minimum, maximum = float(spec["minDistance"]), float(spec["maxDistance"])
        if maximum == 0:
            ref = ref_names[index]
            if cmds.objExists(ref + ".maxDistance"):
                maximum = cmds.getAttr(ref + ".maxDistance")
            else:
                maximum = max(min((points[index].distanceTo(point) for i, point in enumerate(points) if i != index and shortName(specs[i]["control"]) != shortName(spec["control"])),
                                  default=radius), 0.001)
        if not (math.isfinite(minimum) and math.isfinite(maximum) and 0 <= minimum < maximum):
            raise ValueError("Rig Auto Skirt Fnc: {} requires 0 <= Min < Max (Min={}, Max={})".format(spec["control"], minimum, maximum))
        if not 0 <= float(spec["startAngle"]) <= 180:
            raise ValueError("Rig Auto Skirt Fnc: Start Angle must be 0-180")
        ranges.append((minimum, float(maximum)))
    return values, ranges


def sourceData(value):
    """Format original-style Python data without changing numeric precision."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(sourceData(item) for item in value) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(sourceData(item) for item in value) + ("," if len(value) == 1 else "") + ")"
    return repr(value)


def checkTargetFree(target, controls, channels):
    plugs = [f"{target}.{channel}" for channel in channels]
    if all(cmds.getAttr(p, settable=True) and not cmds.connectionInfo(p, isDestination=True) and abs(cmds.getAttr(p)) <= 1e-8 for p in plugs):
        return target
    path = cmds.ls(target, long=True)[0] + "|"
    branches = list(dict.fromkeys(path + cmds.ls(control, long=True)[0][len(path):].split("|")[0] for control in controls))
    offset = cmds.createNode("transform", n=target + "_Offset", parent=target)
    for branch in branches:
        cmds.parent(branch, offset, relative=True)
    return offset


def sharedChannel(plug, sources):
    name = plug.replace(".", "_")
    raw, weighted = sources[0]
    for i, (next_raw, next_weighted) in enumerate(sources[1:], 1):
        suffix = "" if i == 1 else "{:02d}".format(i)
        cond = cmds.createNode("condition", n=name + "_Condition" + suffix)
        cmds.setAttr(f"{cond}.operation", 3)
        cmds.connectAttr(raw, f"{cond}.firstTerm")
        cmds.connectAttr(raw, f"{cond}.colorIfTrueR")
        cmds.connectAttr(next_raw, f"{cond}.secondTerm")
        cmds.connectAttr(next_raw, f"{cond}.colorIfFalseR")
        cmds.connectAttr(weighted, f"{cond}.colorIfTrueG")
        cmds.connectAttr(next_weighted, f"{cond}.colorIfFalseG")
        raw, weighted = f"{cond}.outColorR", f"{cond}.outColorG"
    mult = cmds.createNode("multiplyDivide", n=name + "_RaiseValue_Mult")
    cmds.connectAttr(weighted, f"{mult}.input1X")
    cmds.setAttr(f"{mult}.input2X", 2)
    output = f"{mult}.outputX"
    val = cmds.getAttr(output) or 0.0
    if abs(val) >= 0.0001:
        pma = cmds.createNode("plusMinusAverage", n=name + "_ZeroOut_PMA")
        cmds.setAttr(f"{pma}.operation", 2)
        cmds.connectAttr(output, f"{pma}.input1D[0]")
        cmds.setAttr(f"{pma}.input1D[1]", val)
        output = f"{pma}.output1D"
    return output


def buildScript(config):
    config = convertConfig(config)
    if not config["items"]:
        raise ValueError("Rig Auto Skirt Fnc: add at least one Pose Reader")
    lines = ["import maya.cmds as cmds", "", "def main():"]
    def emit(line=""):
        lines.append("    " + line if line else "")

    target_controls = {}
    target_channels = {}

    seen_spheres = set()
    control_counts = {}
    target_counts = {}
    for reader in config["items"]:
        for spec in reader["drivens"]:
            control = shortName(spec["control"])
            control_counts[control] = control_counts.get(control, 0) + 1
            target = shortName(spec.get("target") or control + "_Target")
            output = spec.get("output", "rotateZ")
            if output not in ("rotateX", "rotateY", "rotateZ", "translateX", "translateY", "translateZ"):
                raise ValueError("Rig Auto Skirt Fnc: invalid output: " + output)
            controls = target_controls.setdefault(target, [])
            channels = target_channels.setdefault(target, [])
            if control not in controls: controls.append(control)
            if output not in channels: channels.append(output)
            plug = target + "." + output
            target_counts[plug] = target_counts.get(plug, 0) + 1
    paired = {plug: [] for plug, count in target_counts.items() if count > 1}
    target_data = {target: (controls, target_channels[target]) for target, controls in target_controls.items()}
    emit("target_data = " + sourceData(target_data))
    emit("target_nodes = {}")
    emit("shared_sources = " + sourceData(paired))
    created_attrs = set()
    distance_min_limit, distance_max_limit = 2, 2
    for reader in config["items"]:
        if not reader["drivens"]:
            raise ValueError("Rig Auto Skirt Fnc: add Driven controls to " + reader["id"])
        attribute_name = reader["attributeName"].strip()
        if not attribute_name.isascii() or not attribute_name.isidentifier():
            raise ValueError("Rig Auto Skirt Fnc: invalid Attribute Name: " + attribute_name)
        ref_parameterV, min_max_distance = resolve(reader)
        for minimum, maximum in min_max_distance:
            if maximum > 2:
                distance_min_limit = max(distance_min_limit, 3, minimum)
                distance_max_limit = max(distance_max_limit, 5, maximum)
        pose_reader = shortName(reader["sphere"])
        controls = [shortName(d["control"]) for d in reader["drivens"]]
        shoulder_joints = []
        counts = {}
        for control in controls:
            counts[control] = counts.get(control, 0) + 1
            suffix = "" if counts[control] == 1 else "_Sub{:02d}".format(counts[control])
            shoulder_joints.append(jointName(control) + suffix)
        targets = [shortName(d.get("target") or shortName(d["control"]) + "_Target") for d in reader["drivens"]]
        if pose_reader in seen_spheres:
            raise ValueError("Rig Auto Skirt Fnc: one item per original pose reader: " + pose_reader)
        seen_spheres.add(pose_reader)
        outputs = [d.get("output", "rotateZ") for d in reader["drivens"]]
        attributes = ["AutoFollow" if control_counts[control] > 1 else attribute_name for control in controls]
        if len(set(shoulder_joints)) != len(shoulder_joints):
            raise ValueError("Rig Auto Skirt Fnc: duplicate shoulder joint name")
        emit()
        emit("# Pose reader: " + pose_reader)
        emit("ref_parameterV = " + sourceData(ref_parameterV))
        emit("min_max_distance = " + sourceData(min_max_distance))
        emit("raise_start_angle = " + sourceData([float(d["startAngle"]) for d in reader["drivens"]]))
        emit("shoulder_joints = " + sourceData(shoulder_joints))
        master_controls = []
        for control, attribute in zip(controls, attributes):
            key = (control, attribute)
            master_controls.append((control, attribute, key not in created_attrs))
            created_attrs.add(key)
        lift_data = [(target, output, spec["weight"], spec["invertRotate"]) for target, output, spec in zip(targets, outputs, reader["drivens"])]
        emit("pose_reader = " + sourceData(pose_reader))
        emit("cp_follicle_shape, cpos = createPoseReaderSystem(pose_reader, {}, {})".format(sourceData(shortName(reader["parent"])), sourceData(shortName(reader["end"]))))
        emit("raise_influence_nodes = createSkirtRigSystem(pose_reader, cp_follicle_shape, cpos, shoulder_joints, ref_parameterV, min_max_distance, raise_start_angle)")
        emit("# Master control")
        emit("master_controls = " + sourceData(master_controls))
        emit("for i, (control, attribute, create_attr) in enumerate(master_controls):")
        emit('    if create_attr:')
        emit('        cmds.addAttr(control, ln=attribute, at="double", min=0, max=2, dv=1, k=True)')
        emit('    cmds.connectAttr(f"{control}.{attribute}", f"{raise_influence_nodes[i]}.input2X")')
        emit("# Lift influence")
        emit("lift_data = " + sourceData(lift_data))
        emit("for i, (target, channel, weight, invert) in enumerate(lift_data):")
        emit('    name = f"{pose_reader}_{shoulder_joints[i]}"')
        emit('    raw = f"{raise_influence_nodes[i]}.outputX"')
        emit('    weight_md = cmds.createNode("multiplyDivide", n=name + "_Weight_MD")')
        emit('    cmds.connectAttr(raw, f"{weight_md}.input1X")')
        emit('    cmds.setAttr(f"{weight_md}.input2X", weight)')
        emit('    weighted = f"{weight_md}.outputX"')
        emit('    if invert:')
        emit('        invert_md = cmds.createNode("multiplyDivide", n=name + "_Invert_MD")')
        emit('        cmds.connectAttr(weighted, f"{invert_md}.input1X")')
        emit('        cmds.setAttr(f"{invert_md}.input2X", -1)')
        emit('        weighted = f"{invert_md}.outputX"')
        emit('    plug = f"{target}.{channel}"')
        emit('    if plug in shared_sources:')
        emit('        shared_sources[plug].append((raw, weighted))')
        emit('    else:')
        emit('        if target not in target_nodes:')
        emit('            target_nodes[target] = checkTargetFree(target, *target_data[target])')
        emit('        cmds.connectAttr(weighted, f"{target_nodes[target]}.{channel}")')
    if paired:
        emit()
        emit("# Shared channels")
        emit("for plug, sources in shared_sources.items():")
        emit("    raw_src_attr = sharedChannel(plug, sources)")
        emit('    target, channel = plug.rsplit(".", 1)')
        emit('    if target not in target_nodes:')
        emit('        target_nodes[target] = checkTargetFree(target, *target_data[target])')
        emit('    cmds.connectAttr(raw_src_attr, f"{target_nodes[target]}.{channel}")')
    skirt_source = inspect.getsource(createSkirtRigSystem).rstrip()
    if distance_max_limit > 2:
        skirt_source = skirt_source.replace('ln="minDistance", at="double", min=0, max=2,',
            'ln="minDistance", at="double", min=0, max={},'.format(sourceData(distance_min_limit)))
        skirt_source = skirt_source.replace('ln="maxDistance", at="double", min=0, max=2,',
            'ln="maxDistance", at="double", min=0, max={},'.format(sourceData(distance_max_limit)))
    lines.extend(["", inspect.getsource(checkTargetFree).rstrip(), "", inspect.getsource(sharedChannel).rstrip(), "", inspect.getsource(createPoseReaderSystem).rstrip(), "",
                  skirt_source, "",
                  'if __name__ == "__main__":', "    main()", ""])
    script = "\n".join(lines)
    compile(script, "Python_Scene_Pattern_RigAutoSkirtFnc.py", "exec")
    return script


def ExportPython(data, *args):
    config = getData(data) if data.get("_batch_export_from_saved") else saveSettings(data)
    script = buildScript(config)
    output = os.path.join(os.path.dirname(dataPath(data)), "Python_Scene_Pattern_RigAutoSkirtFnc.py")
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(script)
    return output


def Run(data, *args):
    config = getData(data)
    converted = convertConfig(config)
    for reader in converted["items"]:
        cpos = shortName(reader["sphere"]) + "_cpos"
        if cmds.objExists(cpos):
            raise ValueError("RigAutoSkirtFnc: Run on a clean scene; Pose Reader already built: " + cpos)
    script = buildScript(config)
    exec(compile(script, "RigAutoSkirtFnc", "exec"), {"__name__": "__main__"})
    for reader in legacyConfig(config)["items"]:
        setFollicleDisplaySize(shortName(reader["sphere"]), float(reader.get("follicleSize", 1.0)))


def runFromForm(data, *args):
    saveSettings(data)
    result = Run(data)
    for row in STATE["rows"]:
        row.pop("liveDirty", None)
        row.pop("liveDirtyControls", None)
        row.pop("liveTopologyDirty", None)
    return result


def createPoseReaderSystem(poseReader, poseReader_constraint_target, closest_point_ref_object):
    # Target locator
    target_loc_group = cmds.createNode("transform", n=f"{poseReader}_Target_Loc_Group")
    target_loc = cmds.spaceLocator(n=f"{poseReader}_Target_Loc")[0]
    target_loc_shape = cmds.listRelatives(target_loc, shapes=True, fullPath=False)[0]
    cmds.parent(target_loc, target_loc_group)
    cmds.parent(target_loc_group, "RigUtil")
    cmds.parentConstraint(closest_point_ref_object, target_loc_group, mo=False)
    # Pose reader
    pose_reader = poseReader
    pose_reader_shape = cmds.listRelatives(pose_reader, shapes=True, fullPath=False)[0]
    cmds.parentConstraint(poseReader_constraint_target, pose_reader, mo=True)
    cpos = cmds.createNode("closestPointOnSurface", n=f"{poseReader}_cpos")
    cmds.connectAttr(f"{target_loc_shape}.worldPosition[0]", f"{cpos}.inPosition")
    cmds.connectAttr(f"{pose_reader_shape}.worldSpace[0]", f"{cpos}.inputSurface")
    # Closest point follicle
    cp_follicleShape = cmds.createNode("follicle", name=f"{poseReader}_CP_follicleShape")
    cp_follicleTransform = cmds.listRelatives(cp_follicleShape, parent=True, fullPath=False)[0]
    cp_follicleTransform = cmds.rename(cp_follicleTransform, f"{poseReader}_CP_follicle")
    cmds.parent(cp_follicleTransform, "RigUtil")
    cmds.setAttr(f"{cp_follicleTransform}.inheritsTransform", 0)
    cmds.connectAttr(f"{pose_reader_shape}.local", f"{cp_follicleShape}.inputSurface")
    cmds.connectAttr(f"{pose_reader_shape}.worldMatrix[0]", f"{cp_follicleShape}.inputWorldMatrix")
    cmds.connectAttr(f"{cp_follicleShape}.outTranslate", f"{cp_follicleTransform}.translate")
    cmds.connectAttr(f"{cp_follicleShape}.outRotate", f"{cp_follicleTransform}.rotate")
    cmds.connectAttr(f"{cpos}.parameterU", f"{cp_follicleShape}.parameterU")
    cmds.connectAttr(f"{cpos}.parameterV", f"{cp_follicleShape}.parameterV")
    return cp_follicleShape, cpos

def createSkirtRigSystem(pose_reader, cp_follicleShape, cpos, skirt_joints, ref_parameterV, min_max_distance, raise_start_angle):

    pose_reader_shape = cmds.listRelatives(pose_reader, shapes=True, fullPath=False)[0]
    raise_influence_nodes = []
    for i, skirt_joint in enumerate(skirt_joints):
        equator_follicles = []
        # Ref and equator follicles
        for follicle_type in ["ref", "equator"]:
            follicleShape = cmds.createNode("follicle", name=f"{pose_reader}_{skirt_joint}_{follicle_type}_follicleShape")
            follicleTransform = cmds.listRelatives(follicleShape, parent=True, fullPath=False)[0]
            follicleTransform = cmds.rename(follicleTransform, f"{pose_reader}_{skirt_joint}_{follicle_type}_follicle")
            equator_follicles.append(follicleTransform)
            cmds.parent(follicleTransform, "RigUtil")
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
        # Distance weight
        distance = cmds.createNode("distanceBetween", n=f"{pose_reader}_{skirt_joint}_Distance")
        remap_distance = cmds.createNode("remapValue", n=f"{pose_reader}_{skirt_joint}_Remap_Distance")
        cmds.connectAttr(f"{equator_follicles[0]}.worldMatrix[0]", f"{distance}.inMatrix1")
        cmds.connectAttr(f"{equator_follicles[1]}.worldMatrix[0]", f"{distance}.inMatrix2")
        cmds.connectAttr(f"{distance}.distance", f"{remap_distance}.inputValue")
        cmds.connectAttr(f"{equator_follicles[0]}.minDistance", f"{remap_distance}.inputMin")
        cmds.connectAttr(f"{equator_follicles[0]}.maxDistance", f"{remap_distance}.inputMax")
        cmds.setAttr(f"{remap_distance}.outputMin", 1)
        cmds.setAttr(f"{remap_distance}.outputMax", 0)
        # Raise angle
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
        # Raise influence
        md_raise = cmds.createNode("multiplyDivide", n=f"{pose_reader}_{skirt_joint}_md_Raise")
        md_raise_influence = cmds.createNode("multiplyDivide", n=f"{pose_reader}_{skirt_joint}_md_RaiseInfluence")
        raise_influence_nodes.append(md_raise_influence)
        cmds.connectAttr(f"{pma_raise}.output1D", f"{md_raise}.input1X")
        cmds.connectAttr(f"{remap_distance}.outValue", f"{md_raise}.input2X")
        cmds.connectAttr(f"{md_raise}.outputX", f"{md_raise_influence}.input1X")
        # Set ranges
        cmds.setAttr(f"{equator_follicles[0]}.minDistance", min_max_distance[i][0])
        cmds.setAttr(f"{equator_follicles[0]}.maxDistance", min_max_distance[i][1])
        cmds.setAttr(f"{equator_follicles[0]}.raiseStartAngle", raise_start_angle[i])
    return raise_influence_nodes
