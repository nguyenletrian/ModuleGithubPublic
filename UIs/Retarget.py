"""Retarget PySide inline ordered modules embedded in the NLTA Tools form.

Each step's settings and local move up/down controls live in a collapsible card.
The V2 engine remains shared; reference assets can use distinct namespaces.
"""
import copy
import importlib.util
import json
import math
import os
import re
import tempfile
from pathlib import Path
import traceback
import uuid

import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui
import NLTA_RetargetV2 as rt

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import getCppPointer
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import getCppPointer


UIs = {}
_STATE = {"steps": [], "path": "", "context": {}, "general": {},
          "expanded": {}, "selected_id": None}
STEP_FILES = (
    ("Scale", "Retarget_Scale.py"),
    ("Rotate", "Retarget_Rotate.py"),
    ("Transform", "Retarget_Transform.py"),  # Legacy kind: Extra Transform.
    ("SetValue", "Retarget_SetValue.py"),
    ("OffsetPosition", "Retarget_OffsetPosition.py"),
    ("Mapping", "Retarget_Mapping.py"),
    ("MatchRotatePair", "Retarget_MatchRotatePair.py"),
    ("Animation", "Retarget_Animation.py"),
    ("Bake", "Retarget_Bake.py"),
    ("Script", "Retarget_Script.py"),
    ("PythonFile", "Retarget_PythonFile.py"),
    ("Save", "Retarget_Save.py"),
)
STEP_MAP = dict(STEP_FILES)
# This identifier is accepted only while migrating older saved JSONs.
LEGACY_STEP_MAP = dict(STEP_MAP, Reference="Retarget_Reference.py")


def _module(kind):
    """Load only a whitelisted step module, relative to this file."""
    if kind not in STEP_MAP:
        raise ValueError("Unknown Retarget step: " + str(kind))
    path = Path(__file__).resolve().parent / "RetargetSteps" / STEP_MAP[kind]
    if not path.is_file():
        raise FileNotFoundError("Missing Retarget submodule: " + str(path))
    spec = importlib.util.spec_from_file_location("NLTA_Retarget_" + kind,
                                                  str(path))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load Retarget module: " + str(path))
    module = importlib.util.module_from_spec(spec)
    # Compile the source, not __pycache__ bytecode. This also avoids Maya
    # reusing an older step implementation after a repository update.
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    required = ("LABEL", "DefaultSetting", "Fields", "Run")
    missing = [name for name in required
               if not hasattr(module, name) or
               (name != "LABEL" and not callable(getattr(module, name)))]
    if missing:
        raise ImportError(
            "Retarget step {!r} is outdated or incomplete: {}. "
            "Missing: {}. Update the entire UIs/RetargetSteps folder "
            "together with UIs/Retarget.py, then reopen the tool.".format(
                kind, path, ", ".join(missing)))
    return module


def _new_step(kind, order):
    module = _module(kind)
    # Stable 64-bit UUID suffix: unique per instance, even for Script copies.
    identifier = uuid.uuid4().hex[:16]
    while any(item["id"] == identifier for item in _STATE["steps"]):
        identifier = uuid.uuid4().hex[:16]
    return {"id": identifier, "kind": kind,
            "name": module.LABEL, "order": int(order), "enabled": True,
            "data": module.DefaultSetting()}


def _default_steps():
    steps = [_new_step(kind, (index + 1) * 10)
             for index, (kind, _) in enumerate(STEP_FILES)]
    # Optional modules require an object/file or a later Bake stage.
    for step in steps:
        if step["kind"] in ("Bake", "PythonFile", "Transform",
                            "OffsetPosition", "SetValue", "MatchRotatePair"):
            step["enabled"] = False
    return steps


def _sorted_steps():
    return sorted(_STATE["steps"], key=lambda item: (
        int(item["order"]), _STATE["steps"].index(item)))


def _general_defaults():
    """Fields owned by the main Retarget form, not an execution module."""
    return {
        "new_path": "", "new_namespace": rt.NEW_NS,
        "old_animations_path": "", "old_animations_mode": "File",
        "old_animations_namespace": rt.OLD_NS,
        "reference_pose_path": "", "reference_pose_namespace": "RT_REF_POSE",
        "output_folder": "",
    }


def _normalize_general(data):
    defaults = _general_defaults()
    if isinstance(data, dict):
        normalized = dict(data)
        if "old_animations_path" not in normalized:
            normalized["old_animations_path"] = normalized.get("old_path", "")
        if "old_animations_namespace" not in normalized:
            normalized["old_animations_namespace"] = normalized.get(
                "old_namespace", rt.OLD_NS)
        defaults.update({key: value for key, value in normalized.items()
                         if key in defaults})
    return defaults


def _general_context(settings, context):
    """Validate general metadata and initialize step context without imports."""
    data = _normalize_general(settings)
    mode = str(data["old_animations_mode"] or "File").strip().title()
    if mode not in ("File", "Folder"):
        raise ValueError("Old Animations mode must be File or Folder.")
    namespaces = {}
    files = {}
    for role, path_key, namespace_key in (
        ("new_rig", "new_path", "new_namespace"),
        ("old_animations", "old_animations_path", "old_animations_namespace"),
        ("reference_pose", "reference_pose_path", "reference_pose_namespace"),
    ):
        path = str(data.get(path_key) or "").strip()
        if (path and (role != "old_animations" or mode == "File")
                and not path.lower().endswith((".ma", ".mb", ".fbx"))):
            raise ValueError("{} must be a .ma, .mb or .fbx file.".format(
                role))
        namespace = str(data.get(namespace_key) or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", namespace):
            raise ValueError("Invalid Retarget namespace: " + namespace)
        if namespace == rt.CLIP_NS:
            raise ValueError("Namespace reserved for clips: " + namespace)
        namespaces[role] = namespace
        record = {"path": path, "namespace": namespace}
        if role == "old_animations":
            record["mode"] = mode
        files[role] = record
    if len(set(namespaces.values())) != len(namespaces):
        raise ValueError("Each Retarget input must use a unique namespace.")
    context.update({
        "reference_files": files, "reference_namespaces": namespaces,
        "source_namespace": namespaces["old_animations"],
        "target_namespace": namespaces["new_rig"],
        "reference_pose_namespace": namespaces["reference_pose"],
        "new_path": files["new_rig"]["path"],
        "old_animations_path": files["old_animations"]["path"],
        "old_animations_mode": mode,
        "reference_pose_path": files["reference_pose"]["path"],
        "output_folder": str(data.get("output_folder") or "").strip(),
        "references_loaded": False,
    })
    return context


def _take_general(records, explicit=None):
    """Move obsolete Reference step values to the main form on legacy load."""
    general = _normalize_general(explicit)
    retained = []
    for record in records:
        if record.get("kind") == "Reference":
            previous = record.get("data") or {}
            general.update({key: value for key, value in
                            _normalize_general(previous).items()
                            if key in previous or (
                                key == "old_animations_path" and
                                "old_path" in previous) or (
                                key == "old_animations_namespace" and
                                "old_namespace" in previous)})
            continue
        retained.append(record)
    save = next((record for record in retained
                 if record.get("kind") == "Save"), None)
    if save and not general["output_folder"]:
        general["output_folder"] = str(
            (save.get("data") or {}).get("output") or "").strip()
    _STATE["general"] = general
    return retained


def _validate_entries(records):
    if not isinstance(records, list):
        raise ValueError("Retarget profile steps must be a list.")
    cleaned = []
    ids = set()
    for index, item in enumerate(records):
        if not isinstance(item, dict) or item.get("kind") not in STEP_MAP:
            raise ValueError("Retarget profile contains an unknown step.")
        key = str(item.get("id") or uuid.uuid4().hex[:16])
        if key in ids:
            raise ValueError("Duplicate Retarget step ID: " + key)
        ids.add(key)
        kind = item["kind"]
        defaults = _module(kind).DefaultSetting()
        settings = item.get("data", {})
        if not isinstance(settings, dict):
            raise ValueError("Invalid settings for step " + kind)
        defaults.update(settings)
        if kind == "SetValue" and "items" not in settings:
            defaults["items"] = ([{
                "source": settings.get("source", "Rig"),
                "object": settings.get("object", ""),
                "attribute": settings.get("attribute", ""),
                "value": settings.get("value", "0"),
            }] if any(key in settings for key in (
                "source", "object", "attribute", "value")) else [])
        if kind == "Scale":
            if "scale_target" not in settings:
                defaults["legacy_root_scale"] = True
            if "source_role" not in settings:
                defaults["source_role"] = (
                    "REF" if (_STATE.get("general") or {}).get(
                        "reference_pose_path") else "Anim")
        label = str(item.get("name") or _module(kind).LABEL)
        if kind == "Transform" and label == "Transform":
            label = "Extra Transform"
        cleaned.append({
            "id": key, "kind": kind,
            "name": label,
            "order": int(item.get("order", (index + 1) * 10)),
            "enabled": bool(item.get("enabled", True)),
            "data": defaults,
        })
    return cleaned


def _legacy_v2_profile(profile):
    """Migrate V2 data into current steps plus main form settings."""
    if profile.get("version") != 2:
        raise ValueError("Expected a version 2 Retarget profile.")
    values = copy.deepcopy(profile)
    refs = values.get("refs") or {}
    def ref(key):
        return values.get(key) or refs.get(key, "")
    _STATE["general"] = _normalize_general({
        "new_path": values.get("new_path", ""),
        "old_animations_path": values.get("animation")
                               or values.get("old_path", ""),
        "old_animations_mode": "File",
        "output_folder": values.get("output", ""),
    })
    steps = _default_steps()
    by_kind = {step["kind"]: step for step in steps}
    by_kind["Rotate"]["data"]["bind_frame"] = int(values.get("bind_frame", 0))
    by_kind["Scale"]["data"].update({
        key: ref(key) for key in ("old_low", "old_high", "new_low", "new_high")})
    by_kind["Scale"]["data"]["scale_attribute"] = values.get(
        "scale_attribute", "")
    by_kind["Scale"]["data"]["legacy_root_scale"] = True
    anchor = values.get("anchor", "Lowest").lower()
    by_kind["Rotate"]["data"].update({
        "old_anchor": ref("old_low") if anchor == "lowest" else ref("old_high"),
        "new_anchor": ref("new_low") if anchor == "lowest" else ref("new_high"),
        "old_low": ref("old_low"), "new_low": ref("new_low"),
        "old_forward": ref("old_forward"), "new_forward": ref("new_forward"),
        "up": values.get("up", "Y")})
    by_kind["Mapping"]["data"].update({
        "pairs": values.get("pairs", []),
        "match_world_bind": bool(values.get("match_world_bind", False))})
    by_kind["Animation"]["data"]["animation"] = values.get("animation", "")
    by_kind["Script"]["data"]["code"] = values.get("post_script", "")
    by_kind["Save"]["data"].update({
        "keep_sources": bool(values.get("keep_sources", False))})
    return steps


def _load_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Retarget JSON must contain an object.")
    if payload.get("version") == 2:
        records = _legacy_v2_profile(payload)
    elif payload.get("version") == 3:
        records = payload.get("steps")
    else:
        raise ValueError("Expected Retarget profile version 2 or 3.")
    if not isinstance(records, list):
        raise ValueError("Retarget profile steps must be a list.")
    old_bind = next((
        item["data"]["bind_frame"] for item in records
        if isinstance(item, dict) and item.get("kind") == "Reference"
        and isinstance(item.get("data"), dict)
        and "bind_frame" in item["data"]), None)
    if payload.get("version") == 3:
        records = _take_general(records, payload.get("general"))
    cleaned = _validate_entries(records)
    if old_bind is not None:
        original_rotate = next(
            (item for item in records if item.get("kind") == "Rotate"), None)
        if original_rotate is not None and "bind_frame" not in (
                original_rotate.get("data") or {}):
            rotate = next((item for item in cleaned
                           if item["kind"] == "Rotate"), None)
            if rotate:
                rotate["data"]["bind_frame"] = int(old_bind)
    return cleaned


def _default_path():
    """Use RetargetData next to the current Maya scene, never userAppDir."""
    scene = cmds.file(query=True, sceneName=True) or ""
    if not scene:
        return ""
    return os.path.join(os.path.dirname(os.path.abspath(scene)),
                        "RetargetData", "Retarget.json")


def _module_data_path(folder, kind):
    """Legacy per-type JSON location (for older RetargetData migrations)."""
    return os.path.join(folder, LEGACY_STEP_MAP[kind][:-3] + ".json")


def _instance_data_path(folder, kind, identifier):
    """Stable per-instance JSON; a UUID suffix prevents duplicate filenames."""
    identifier = str(identifier)
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not identifier or len(identifier) > 64 or any(
            character not in allowed for character in identifier):
        raise ValueError("Unsafe Retarget module ID: " + identifier)
    return os.path.join(
        folder, LEGACY_STEP_MAP[kind][:-3] + "_" + identifier + ".json")


def _write_json(path, payload):
    """Atomically replace one JSON file after all data is serialized."""
    temp = path + ".tmp"
    try:
        with open(temp, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def _read_manifest():
    """Read only V7 execution metadata and general settings."""
    path = _default_path()
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as stream:
        profile = json.load(stream)
    if profile.get("version") != 7:
        # Older formats must be migrated through their module JSON layout.
        return _read_profile()
    _STATE["general"] = _normalize_general(profile.get("general"))
    items = profile.get("steps")
    if not isinstance(items, list):
        raise ValueError("Retarget.json must contain a module list: " + path)
    seen = set()
    result = []
    for item in items:
        if not isinstance(item, dict) or item.get("kind") not in STEP_MAP:
            raise ValueError("Unknown module in Retarget.json: " + str(item))
        identifier = str(item.get("id", ""))
        _instance_data_path(os.path.dirname(path), item["kind"], identifier)
        if identifier in seen:
            raise ValueError("Duplicate module ID in Retarget.json: " +
                             identifier)
        if "order" not in item or "enabled" not in item:
            raise ValueError(
                "Retarget.json module lacks order or enabled: " + identifier)
        try:
            order = int(item["order"])
        except (ValueError, TypeError):
            raise ValueError(
                "Invalid order in Retarget.json for module: " + identifier)
        seen.add(identifier)
        label = str(item.get("name") or item["kind"])
        if item["kind"] == "Transform" and label == "Transform":
            label = "Extra Transform"
        result.append({
            "id": identifier,
            "kind": item["kind"],
            "name": label,
            "order": order,
            "enabled": bool(item["enabled"]),
        })
    return result


def _read_instance(item):
    """Resolve one saved module without reading any other instance JSON."""
    if "data" in item:  # Compatibility for V2–V5 loaded profiles.
        return item
    folder = os.path.dirname(_default_path())
    path = _instance_data_path(folder, item["kind"], item["id"])
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing Retarget module JSON: " + path)
    with open(path, "r", encoding="utf-8") as stream:
        stored = json.load(stream)
    if (stored.get("version") != 3
            or stored.get("id") != item["id"]
            or stored.get("kind") != item["kind"]
            or not isinstance(stored.get("data"), dict)):
        raise ValueError("Invalid Retarget module JSON: " + path)
    record = dict(item)
    record["data"] = stored["data"]
    return record


def _write_profile(snapshot=None, verify=None):
    """Publish one consistent profile, or restore the previous JSON files.

    All module data is serialized before writing. The V7 manifest is written
    last, and an optional read-back verifier runs before the save commits.
    A failed write/verification restores every previously existing file.
    """
    source = snapshot if snapshot is not None else _STATE
    path = _default_path()
    if not path:
        raise ValueError(
            "Save the current Maya scene (.ma/.mb) before saving Retarget.")
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)

    previous_paths = set()
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as stream:
            previous = json.load(stream)
        if previous.get("version") in (6, 7):
            for entry in previous.get("steps", []):
                if (isinstance(entry, dict) and
                        entry.get("kind") in LEGACY_STEP_MAP):
                    previous_paths.add(_instance_data_path(
                        folder, entry["kind"], entry.get("id", "")))
        elif previous.get("version") in (4, 5):
            for entry in previous.get("steps", []):
                if (isinstance(entry, dict) and
                        entry.get("kind") in LEGACY_STEP_MAP):
                    previous_paths.add(_module_data_path(
                        folder, entry["kind"]))

    manifest = []
    instance_payloads = []
    current_paths = set()
    used_ids = set()
    for step in source["steps"]:
        file_path = _instance_data_path(folder, step["kind"], step["id"])
        if step["id"] in used_ids:
            raise ValueError("Duplicate Retarget module ID: " + step["id"])
        used_ids.add(step["id"])
        current_paths.add(file_path)
        manifest.append({
            "id": step["id"], "kind": step["kind"],
            "name": step["name"],
            "order": int(step["order"]),
            "enabled": bool(step["enabled"]),
        })
        instance_payloads.append((file_path, {
            "version": 3, "id": step["id"], "kind": step["kind"],
            "data": step["data"],
        }))

    expanded = {
        step["id"]: bool(source.get("expanded", {}).get(
            step["id"], step["kind"] == "Scale"))
        for step in source["steps"]
    }
    manifest_data = {
        "version": 7, "steps": manifest,
        "general": _normalize_general(source["general"]),
        "expanded": expanded,
    }

    # Reject invalid JSON values before any files are replaced.
    for _, payload in instance_payloads:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    json.dumps(manifest_data, ensure_ascii=False, allow_nan=False)

    targets = [filename for filename, _ in instance_payloads] + [path]
    previous_bytes = {}
    for filename in targets:
        if os.path.isfile(filename):
            with open(filename, "rb") as stream:
                previous_bytes[filename] = stream.read()
        else:
            previous_bytes[filename] = None

    try:
        for filename, payload in instance_payloads:
            _write_json(filename, payload)
        # Only Retarget.json controls run order. Publish it last.
        _write_json(path, manifest_data)
        if verify is not None:
            verify(path, source)
    except Exception:
        # Module JSON and Retarget.json must not disagree after a failed
        # Save. Restore originals even if verification (not writing) failed.
        for filename in reversed(targets):
            previous_data = previous_bytes[filename]
            if previous_data is None:
                if os.path.isfile(filename):
                    os.remove(filename)
            else:
                rollback = filename + ".rollback"
                try:
                    with open(rollback, "wb") as stream:
                        stream.write(previous_data)
                    os.replace(rollback, filename)
                finally:
                    if os.path.exists(rollback):
                        os.remove(rollback)
        raise

    # Delete stale instance files only after the new profile is verified.
    for stale_path in sorted(previous_paths - current_paths):
        if os.path.isfile(stale_path):
            os.remove(stale_path)

    if snapshot is None:
        _STATE["path"] = path
        _STATE["dirty"] = False
    return path


def _read_profile():
    """Load every instance JSON when building/reloading the visible editor."""
    path = _default_path()
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as stream:
        profile = json.load(stream)
    version = profile.get("version")
    if version not in (4, 5, 6, 7):
        return _load_payload(profile)  # Older single-file V2/V3 profiles.

    expanded = profile.get("expanded", {})
    if not isinstance(expanded, dict):
        raise ValueError("Invalid Retarget.json expanded state: " + path)
    _STATE["expanded"] = {str(key): bool(value)
                          for key, value in expanded.items()}

    if version == 7:
        manifest = _read_manifest()
        return _validate_entries([_read_instance(item)
                                  for item in manifest])
    if version == 6:
        records = [_read_instance(item) for item in profile.get("steps", [])]
        return _validate_entries(_take_general(records))

    # Read the previous V4/V5 shared-per-type JSON format.
    metadata = profile.get("steps")
    if not isinstance(metadata, list):
        raise ValueError("Invalid Retarget.json module list: " + path)
    folder = os.path.dirname(path)
    per_kind = {}
    records = []
    for entry in metadata:
        if (not isinstance(entry, dict) or
                entry.get("kind") not in LEGACY_STEP_MAP):
            raise ValueError("Unknown module in Retarget.json: " + str(entry))
        kind = entry["kind"]
        if kind not in per_kind:
            data_path = _module_data_path(folder, kind)
            if not os.path.isfile(data_path):
                raise FileNotFoundError(
                    "Missing Retarget module settings: " + data_path)
            with open(data_path, "r", encoding="utf-8") as stream:
                saved = json.load(stream)
            expected = 1 if version == 4 else 2
            if saved.get("version") != expected or not isinstance(
                    saved.get("modules"), list):
                raise ValueError("Invalid Retarget module JSON: " + data_path)
            modules = {}
            for record in saved["modules"]:
                if not isinstance(record, dict) or not isinstance(
                        record.get("data"), dict):
                    raise ValueError("Invalid module data: " + data_path)
                module_id = str(record.get("id", ""))
                if not module_id or module_id in modules:
                    raise ValueError("Duplicate/empty module ID: " + data_path)
                modules[module_id] = record
            per_kind[kind] = modules
        identifier = str(entry.get("id", ""))
        if identifier not in per_kind[kind]:
            raise ValueError("Missing settings for {} ({}) in {}".format(
                kind, identifier, _module_data_path(folder, kind)))
        saved_record = per_kind[kind][identifier]
        if version == 4:
            item = dict(entry)
            item["data"] = saved_record["data"]
        else:
            item = {"id": identifier, "kind": kind,
                    "name": saved_record["name"],
                    "order": saved_record["order"],
                    "enabled": saved_record["enabled"],
                    "data": saved_record["data"]}
        records.append(item)
    return _validate_entries(_take_general(records))


def _status(message):
    """Report full feedback to Script Editor and short feedback in the panel."""
    message = str(message)
    print("[NLTA Retarget] " + message)
    label = UIs.get("status")
    if label is not None:
        try:
            label.setText(message)
            label.setToolTip(message)
        except RuntimeError:
            pass


def _safe(action):
    try:
        return action()
    except Exception as exc:
        traceback.print_exc()
        cmds.warning("Retarget: " + str(exc))
        _status("Error: " + str(exc))
        return None


def _get_step(identifier):
    return next((item for item in _STATE["steps"]
                 if item["id"] == identifier), None)


def _transform_number(text, channel):
    """Validate a Transform text field and preserve a numeric JSON value."""
    raw = str(text).strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError("Transform {} must be a number.".format(channel))
    if not math.isfinite(value):
        raise ValueError("Transform {} must be a finite number.".format(channel))
    return value


def _queue_save(*args):
    """Mark unsaved form changes; only the main Save button writes files."""
    if not UIs.get("building"):
        _STATE["dirty"] = True


def _save_editor(write=False):
    """Collect every card into memory; never auto-save individual changes."""
    for identifier, card in list(UIs.get("cards", {}).items()):
        item = _get_step(identifier)
        if item is not None:
            item.update(card.settings())
    if write:
        _write_profile()


def _selected_step():
    return _get_step(_STATE.get("selected_id"))


def _run_card(identifier):
    """Test one module in the open Maya scene, using unsaved editor values.

    Manual tests preserve context from earlier cards (e.g. Mapping -> Bake),
    but never reset or save the current scene. Save Retarget remains batch-only.
    """
    def work():
        _save_editor(write=False)
        item = _get_step(identifier)
        if item is None:
            raise ValueError("The selected Retarget module no longer exists.")
        # Explicit testing is allowed even when the batch Enabled flag is off.
        general = _general_from_form()
        _general_context(general, _STATE["context"])
        _status("Testing module: " + item["name"])
        return _run_step(item, _STATE["context"])
    return _safe(work)


def _pick_transform(field):
    selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    if len(selected) != 1:
        raise ValueError("Select exactly one Maya transform to Pick.")
    field.setText(rt.leaf(selected[0]))


def _pick_pair_object(field, role):
    """Pick one pair object and infer its Rig/Anim/REF namespace when possible."""
    selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    if len(selected) != 1 or cmds.nodeType(selected[0]) not in (
            "transform", "joint"):
        raise ValueError("Select exactly one Maya transform or joint.")
    node = selected[0].split("|")[-1]
    namespace = node.rsplit(":", 1)[0] if ":" in node else ""
    general = _general_from_form()
    for name, key in (("Rig", "new_namespace"),
                      ("Anim", "old_animations_namespace"),
                      ("REF", "reference_pose_namespace")):
        if namespace == general.get(key, "").strip(":"):
            role.setCurrentText(name)
            break
    field.setText(rt.leaf(node))


def _pick_channel_attribute(attribute_field, object_field):
    """Pick one Channel Box attribute and its object together."""
    selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    if len(selected) != 1:
        raise ValueError("Select one object and one Channel Box attribute.")
    node = selected[0]
    if cmds.nodeType(node) not in ("transform", "joint"):
        raise ValueError("Set Value needs a transform or joint.")
    attributes = cmds.channelBox(
        "mainChannelBox", query=True, selectedMainAttributes=True) or []
    if len(attributes) != 1:
        raise ValueError("Select exactly one attribute in Maya Channel Box.")
    attribute = str(attributes[0]).strip()
    if not attribute or not cmds.objExists("{}.{}".format(node, attribute)):
        raise ValueError("Selected Channel Box attribute does not exist.")
    object_field.setText(rt.leaf(node))
    attribute_field.setText(attribute)


def _pick_scale_reference(field):
    """Pick one transform/joint or one polygon vertex for Match Scale."""
    selected = cmds.ls(selection=True, long=True, flatten=True) or []
    if len(selected) != 1:
        raise ValueError(
            "Select exactly one transform, joint or mesh vertex for "
            "Match Scale Lowest/Highest.")
    node = str(selected[0])
    if ".vtx[" in node or ".cv[" in node:
        match = re.fullmatch(
            r"(.+)\\.(vtx|cv)((?:\\[\\d+\\]){1,2})", node)
        if match is None or (match.group(2) == "vtx" and
                             match.group(3).count("[") != 1):
            raise ValueError(
                "Pick one polygon vertex (mesh.vtx[index]) or NURBS CV.")
        field.setText("{}.{}{}".format(
            rt.leaf(match.group(1)), match.group(2), match.group(3)))
        return
    if cmds.nodeType(node) not in ("transform", "joint"):
        raise ValueError("Pick a transform/joint or a mesh vertex.")
    field.setText(rt.leaf(node))


def _pick_offset_element(field):
    """Pick one DAG transform/joint or supported geometric component."""
    selected = cmds.ls(selection=True, long=True, flatten=True) or []
    if len(selected) != 1:
        raise ValueError(
            "Select exactly one transform, vertex, edge, face, "
            "CV or curve edit point for Offset Position.")
    node = str(selected[0])
    if "." in node:
        match = re.fullmatch(
            r"(.+)\.(vtx|e|f|cv|ep)((?:\[\d+\]){1,2})", node)
        if match is None or (
                match.group(2) != "cv" and
                match.group(3).count("[") != 1):
            raise ValueError(
                "Pick one mesh vertex/edge/face, NURBS CV or curve EP.")
        field.setText("{}.{}{}".format(
            rt.leaf(match.group(1)), match.group(2), match.group(3)))
        return
    if cmds.nodeType(node) not in ("transform", "joint"):
        raise ValueError("Pick one transform/joint or geometric element.")
    field.setText(rt.leaf(node))


def _pick_scale_destination(role_widget, object_widget):
    """Pick a scale object and its Rig/Anim/REF namespace from Maya."""
    selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    if len(selected) != 1:
        raise ValueError("Select one Maya transform for Match Scale.")
    node = selected[0]
    if cmds.nodeType(node) not in ("transform", "joint"):
        raise ValueError("Pick a transform or joint to scale.")

    leaf = str(node).split("|")[-1]
    root_ns = leaf.split(":", 1)[0] if ":" in leaf else ""
    field_keys = (
        ("Rig", "new_namespace"),
        ("Anim", "old_animations_namespace"),
        ("REF", "reference_pose_namespace"),
    )
    fields = UIs.get("general_fields") or {}
    general = _STATE.get("general") or {}
    matches = []
    for role, key in field_keys:
        field = fields.get(key)
        namespace = (field.text().strip() if field is not None
                     else str(general.get(key) or "").strip())
        if namespace and root_ns == namespace.strip(":"):
            matches.append(role)
    if len(matches) != 1:
        raise ValueError(
            "Selected object namespace {!r} does not match Rig/Anim/REF "
            "in General Settings.".format(root_ns))

    role_widget.setCurrentText(matches[0])
    object_widget.setText(rt.leaf(node))


def _pick_scale_axis_attribute(axis, role_widget, object_widget, field):
    """Copy exactly one Channel Box attribute into one X/Y/Z scale slot."""
    if axis not in "XYZ":
        raise ValueError("Invalid Match Scale axis: " + str(axis))
    object_name = object_widget.text().strip()
    if not object_name:
        raise ValueError("Pick the Apply Scale To object first.")
    selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    if len(selected) != 1:
        raise ValueError("Select exactly one Maya object and one attribute.")
    node = selected[0]
    if rt.leaf(node) != rt.leaf(object_name):
        raise ValueError(
            "Selected Maya object does not match the Apply Scale To object.")

    role_keys = {"Rig": "new_namespace",
                 "Anim": "old_animations_namespace",
                 "REF": "reference_pose_namespace"}
    role = role_widget.currentText()
    if role not in role_keys:
        raise ValueError("Select Rig, Anim or REF for the scale object.")
    key = role_keys[role]
    general_field = UIs.get("general_fields", {}).get(key)
    namespace = (
        general_field.text().strip() if general_field is not None
        else str((_STATE.get("general") or {}).get(key) or "").strip()
    ).strip(":")
    selected_leaf = str(node).split("|")[-1]
    selected_namespace = (
        selected_leaf.rsplit(":", 1)[0] if ":" in selected_leaf else "")
    if not namespace or selected_namespace != namespace:
        raise ValueError(
            "Selected object namespace does not match the {} namespace "
            "in General Settings.".format(role))

    try:
        attrs = cmds.channelBox(
            "mainChannelBox", query=True,
            selectedMainAttributes=True) or []
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "Cannot read Maya Channel Box selection.") from exc
    if len(attrs) != 1:
        raise ValueError(
            "Select exactly one attribute in the Maya Channel Box "
            "to Pick for Scale {}.".format(axis))
    attr = str(attrs[0]).strip()
    if not attr or "." in attr:
        raise ValueError("Channel Box must contain one attribute name.")
    field.setText(attr)


def _browse_path(field, kind):
    if kind == "folder":
        path = QtWidgets.QFileDialog.getExistingDirectory(
            UIs.get("widget"), "Select Folder", field.text().strip())
    else:
        file_filter = (
            "Python Files (*.py)" if kind == "python_file" else
            "Maya ASCII / FBX (*.ma *.fbx)" if kind == "ma_fbx" else
            "Maya / FBX (*.ma *.mb *.fbx)")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            UIs.get("widget"), "Select Maya / FBX File", field.text().strip(),
            file_filter)
    if path:
        field.setText(path)


def _new_tool_button(text, tip, callback=None, arrow=None):
    button = QtWidgets.QToolButton()
    button.setToolTip(tip)
    button.setFixedSize(48 if text == "Run" else 29, 28)
    button.setAutoRaise(True)
    if arrow is not None:
        button.setArrowType(arrow)
    else:
        button.setText(text)
    if callback is not None:
        button.clicked.connect(lambda checked=False: _safe(callback))
    return button


def _mapping_item(pair):
    old = rt.leaf(pair.get("old", ""))
    new = rt.leaf(pair.get("new", ""))
    row = QtWidgets.QTreeWidgetItem([old, new, ""])
    row.setFlags(row.flags() | QtCore.Qt.ItemIsEditable |
                 QtCore.Qt.ItemIsUserCheckable)
    row.setCheckState(2, QtCore.Qt.Checked if pair.get("translate")
                      else QtCore.Qt.Unchecked)
    return row


def _module_field_columns(kind, descriptors):
    """Partition UI fields without changing their keys or JSON values."""
    if kind in ("SetValue", "MatchRotatePair"):
        return "", [], "", [], descriptors
    paired = {
        "Scale": (("source_role", "old_low", "old_high"),
                  ("target_role", "new_low", "new_high"),
                  "Scale Ref", "Scale Object"),
        "OffsetPosition": (("ref_role", "ref_root", "ref_object"),
                           ("affect_role", "affect_root", "affect_object"),
                           "Ref", "Affect"),
        "Rotate": (("old_anchor", "old_forward", "old_low"),
                   ("new_anchor", "new_forward", "new_low"),
                   "Old", "New"),
        "Transform": (("source",), ("object",),
                      "Namespace", "Object"),
    }
    if kind in paired:
        left_keys, right_keys, left_title, right_title = paired[kind]
        left = [field for field in descriptors if field[1] in left_keys]
        right = [field for field in descriptors if field[1] in right_keys]
        shared = [field for field in descriptors
                  if field[1] not in left_keys + right_keys]
        return left_title, left, right_title, right, shared

    # Long editors (mapping, scripts, the additive TRS grid) need width.
    # Other modules use two balanced columns when they have paired fields.
    full_width_kinds = {"pairs", "script", "transform9", "scale_target"}
    narrow = [field for field in descriptors if field[2] not in full_width_kinds]
    shared = [field for field in descriptors if field[2] in full_width_kinds]
    if len(narrow) < 2:
        return "", [], "", [], narrow + shared
    halfway = (len(narrow) + 1) // 2
    return "", narrow[:halfway], "", narrow[halfway:], shared


class RetargetCard(QtWidgets.QFrame):
    """One collapsible submodule with local order arrows and inline settings."""

    def __init__(self, record, parent=None):
        super(RetargetCard, self).__init__(parent)
        self.identifier = record["id"]
        self.kind = record["kind"]
        self.widgets = {}
        self.setObjectName("RetargetCard_" + self.identifier)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Preferred)
        self.setMinimumWidth(0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 6)
        layout.setSpacing(3)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(2)
        self.expand = QtWidgets.QToolButton()
        self.expand.setCheckable(True)
        self.expand.setFixedSize(24, 28)
        header.addWidget(self.expand)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.setChecked(bool(record.get("enabled", True)))
        self.enabled.setToolTip("Enable this module in the ordered pipeline")
        header.addWidget(self.enabled)

        self.title = QtWidgets.QLabel()
        self.title.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                                 QtWidgets.QSizePolicy.Preferred)
        self.title.setMinimumWidth(0)
        self.title.setToolTip(record["name"])
        self.title.setWordWrap(False)
        header.addWidget(self.title, 1)

        # Keep execution order with Mute / Up / Down / Run / Delete.
        order_label = QtWidgets.QLabel("Order")
        header.addWidget(order_label)
        self.order = QtWidgets.QSpinBox()
        self.order.setRange(0, 100000)
        self.order.setValue(int(record["order"]))
        self.order.setFixedWidth(64)
        self.order.setToolTip("Execution order; press Enter to reorder cards")
        header.addWidget(self.order)
        self.order.editingFinished.connect(
            lambda: _safe(_apply_manual_order))

        index = _sorted_steps().index(record)
        up = _new_tool_button("", "Move module up", lambda: _move_step(
            self.identifier, -1), arrow=QtCore.Qt.UpArrow)
        down = _new_tool_button("", "Move module down", lambda: _move_step(
            self.identifier, 1), arrow=QtCore.Qt.DownArrow)
        up.setEnabled(index > 0)
        down.setEnabled(index < len(_STATE["steps"]) - 1)
        header.addWidget(up)
        header.addWidget(down)
        header.addWidget(_new_tool_button(
            "Run", "Test only this module using current form values",
            lambda: _run_card(self.identifier)))
        header.addWidget(_new_tool_button("X", "Delete this module",
                                          lambda: _delete_step(self.identifier)))
        layout.addLayout(header)

        self.details = QtWidgets.QWidget(self)
        detail = QtWidgets.QVBoxLayout(self.details)
        detail.setContentsMargins(7, 5, 5, 3)
        detail.setSpacing(6)
        name_label = QtWidgets.QLabel("Module Name")
        detail.addWidget(name_label)
        self.name = QtWidgets.QLineEdit(record["name"])
        detail.addWidget(self.name)
        self.name.textChanged.connect(_queue_save)

        fields = list(_module(self.kind).Fields())
        left_title, left, right_title, right, shared = (
            _module_field_columns(self.kind, fields))
        if left or right:
            columns = QtWidgets.QGridLayout()
            columns.setContentsMargins(0, 0, 0, 0)
            columns.setHorizontalSpacing(8)
            columns.setColumnStretch(0, 1)
            columns.setColumnStretch(1, 1)
            for column, (heading, descriptors) in enumerate(
                    ((left_title, left), (right_title, right))):
                panel = QtWidgets.QGroupBox(heading) if heading else (
                    QtWidgets.QWidget())
                field_layout = QtWidgets.QVBoxLayout(panel)
                field_layout.setContentsMargins(7, 6, 7, 6)
                field_layout.setSpacing(5)
                for descriptor in descriptors:
                    label, key, kind = descriptor[:3]
                    options = descriptor[3] if len(descriptor) > 3 else ()
                    self._add_field(
                        field_layout, label, key, kind,
                        record["data"].get(key), options)
                field_layout.addStretch(1)
                columns.addWidget(panel, 0, column)
            detail.addLayout(columns)
        for descriptor in shared:
            label, key, kind = descriptor[:3]
            options = descriptor[3] if len(descriptor) > 3 else ()
            self._add_field(
                detail, label, key, kind, record["data"].get(key), options)

        layout.addWidget(self.details)

        expanded = _STATE.get("expanded", {}).get(
            self.identifier, False)
        self.expand.setChecked(bool(expanded))
        self._set_expanded(bool(expanded))
        self.expand.toggled.connect(self._set_expanded)
        self.enabled.toggled.connect(_queue_save)
        self.refresh_title(record)

    def refresh_title(self, record):
        # Keep friendly labels but identify repeatable instances by UUID.
        suffix = ("  [{}]".format(record["id"][:8])
                  if record["kind"] in ("Script", "PythonFile") else "")
        self.title.setText("{}{}".format(record["name"], suffix))
        self.title.setToolTip(record["name"])
        self.title.setEnabled(record.get("enabled", True))

    def _set_expanded(self, expanded):
        self.details.setVisible(expanded)
        self.expand.setArrowType(QtCore.Qt.DownArrow if expanded
                                 else QtCore.Qt.RightArrow)
        _STATE.setdefault("expanded", {})[self.identifier] = bool(expanded)

    def _add_field(self, parent, label, key, kind, value, options):
        if kind == "rotate_pairs":
            self._make_rotate_pairs(parent, value)
            self.widgets[key] = (kind, self.rotate_pair_rows)
            return
        if kind == "set_values":
            self._make_set_values(parent, value)
            self.widgets[key] = (kind, self.set_value_rows)
            return
        if kind == "pairs":
            self._make_mapping(parent, value or [])
            self.widgets[key] = (kind, self.pairs_tree)
            return
        if kind == "scale_target":
            group = QtWidgets.QGroupBox(label)
            layout = QtWidgets.QGridLayout(group)
            layout.setContentsMargins(7, 8, 7, 7)
            layout.setHorizontalSpacing(5)
            data = value if isinstance(value, dict) else {}
            role = QtWidgets.QComboBox()
            role.addItems(["Rig", "Anim", "REF"])
            role.setCurrentText(str(data.get("role") or "Rig"))
            role.currentIndexChanged.connect(_queue_save)
            object_field = QtWidgets.QLineEdit(str(data.get("object") or ""))
            object_field.setMinimumWidth(0)
            object_field.setPlaceholderText("Pick scale object")
            object_field.textChanged.connect(_queue_save)
            pick_button = QtWidgets.QPushButton("Pick Object")
            pick_button.setToolTip(
                "Pick a transform or joint to capture its namespace and "
                "object name. Assign X/Y/Z attributes independently below.")
            pick_button.clicked.connect(
                lambda checked=False: _safe(
                    lambda: _pick_scale_destination(role, object_field)))

            layout.addWidget(QtWidgets.QLabel("Namespace"), 0, 0)
            layout.addWidget(role, 0, 1)
            layout.addWidget(pick_button, 0, 2)
            layout.addWidget(QtWidgets.QLabel("Object"), 1, 0)
            layout.addWidget(object_field, 1, 1, 1, 2)

            previous = data.get("attributes")
            if not isinstance(previous, dict):
                # A saved single-channel Match Scale must keep its behavior.
                legacy_attr = str(data.get("attribute") or "").strip()
                previous = ({"X": legacy_attr, "Y": "-", "Z": "-"}
                            if legacy_attr else {})
            attribute_widgets = {}
            for index, axis in enumerate("XYZ", start=2):
                field = QtWidgets.QLineEdit(
                    str(previous.get(axis) or ""))
                field.setMinimumWidth(0)
                field.setPlaceholderText("scale" + axis)
                field.setToolTip(
                    "If ALL Scale X/Y/Z fields are empty, use native "
                    "scaleX/scaleY/scaleZ. If ANY custom channel is filled, "
                    "other blank fields are ignored. Duplicate channels "
                    "(including GlobalScale) are applied only once. "
                    "'-' explicitly skips an axis.")
                field.textChanged.connect(_queue_save)
                pick_axis = QtWidgets.QPushButton("Pick")
                pick_axis.setFixedWidth(50)
                pick_axis.setToolTip(
                    "Select exactly one attribute of the scale object "
                    "in the Maya Channel Box, then Pick Scale {}.".format(
                        axis))
                pick_axis.clicked.connect(
                    lambda checked=False, current_axis=axis, target=field:
                    _safe(lambda: _pick_scale_axis_attribute(
                        current_axis, role, object_field, target)))
                layout.addWidget(QtWidgets.QLabel("Scale " + axis), index, 0)
                layout.addWidget(field, index, 1)
                layout.addWidget(pick_axis, index, 2)
                attribute_widgets[axis] = field
            hint = QtWidgets.QLabel(
                "All empty = scale XYZ. Custom channel(s) = apply each "
                "unique attribute once; blank axes are ignored.")
            hint.setWordWrap(True)
            layout.addWidget(hint, 5, 0, 1, 3)
            parent.addWidget(group)
            self.widgets[key] = (
                kind, (role, object_field, attribute_widgets))
            return
        if kind == "transform9":
            parent.addWidget(QtWidgets.QLabel(label))
            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(5)
            grid.setVerticalSpacing(4)
            for column, axis in enumerate(("X", "Y", "Z"), start=1):
                grid.addWidget(QtWidgets.QLabel(axis), 0, column)
            mapping = {}
            stored = value if isinstance(value, dict) else {}
            for row_number, group in enumerate(
                    ("translate", "rotate", "scale"), start=1):
                grid.addWidget(QtWidgets.QLabel(group.capitalize()),
                               row_number, 0)
                numbers = stored.get(group, [0.0, 0.0, 0.0])
                if not isinstance(numbers, (list, tuple)) or len(numbers) != 3:
                    numbers = [0.0, 0.0, 0.0]
                controls = []
                for column in range(3):
                    # Plain numeric text field: no spin buttons and no
                    # wheel-driven value changes while hovering the form.
                    field = QtWidgets.QLineEdit(str(numbers[column]))
                    validator = QtGui.QDoubleValidator(field)
                    validator.setLocale(QtCore.QLocale.c())
                    field.setValidator(validator)
                    field.setAlignment(QtCore.Qt.AlignRight)
                    field.setToolTip(
                        "Type a numeric offset for local {} {}. "
                        "Mouse wheel does not change this field.".format(
                            group, ("X", "Y", "Z")[column]))
                    field.textChanged.connect(_queue_save)
                    field.setMinimumWidth(0)
                    grid.addWidget(field, row_number, column + 1)
                    controls.append(field)
                mapping[group] = controls
            parent.addLayout(grid)
            self.widgets[key] = (kind, mapping)
            return
        if kind == "animation_source":
            # A single picker with a persistent mode and a shared path edit.
            parent.addWidget(QtWidgets.QLabel(label))
            row = QtWidgets.QHBoxLayout()
            mode = QtWidgets.QComboBox()
            mode.addItems(["File", "Folder"])
            saved_mode = str(_get_step(self.identifier)["data"].get(
                "old_animations_mode", "File")).title()
            index = mode.findText(saved_mode)
            mode.setCurrentIndex(max(index, 0))
            mode.setToolTip("File: one animation; Folder: every supported file")
            row.addWidget(mode)
            field = QtWidgets.QLineEdit(str(value or ""))
            field.setMinimumWidth(0)
            field.textChanged.connect(_queue_save)
            row.addWidget(field, 1)
            browse = QtWidgets.QPushButton("Browse")
            browse.clicked.connect(
                lambda checked=False: _safe(
                    lambda: _browse_path(field, mode.currentText().lower())))
            row.addWidget(browse)
            parent.addLayout(row)
            self.widgets[key] = ("text", field)
            self.widgets["old_animations_mode"] = ("choice", mode)
            # A path selected for the previous mode is no longer valid.
            mode.currentIndexChanged.connect(lambda _: field.clear())
            mode.currentIndexChanged.connect(_queue_save)
            return
        if kind == "bool":
            widget = QtWidgets.QCheckBox(label)
            widget.setChecked(bool(value))
            widget.toggled.connect(_queue_save)
            parent.addWidget(widget)
            self.widgets[key] = (kind, widget)
            return

        caption = QtWidgets.QLabel(label)
        caption.setWordWrap(True)
        parent.addWidget(caption)
        if kind == "script":
            widget = QtWidgets.QPlainTextEdit()
            widget.setPlainText(str(value or ""))
            widget.setMinimumHeight(130)
            widget.setMaximumHeight(360)
            widget.textChanged.connect(_queue_save)
            parent.addWidget(widget)
            self.widgets[key] = (kind, widget)
            return

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        if kind == "int":
            widget = QtWidgets.QSpinBox()
            widget.setRange(-100000, 100000)
            widget.setValue(int(value or 0))
            widget.valueChanged.connect(_queue_save)
        elif kind == "float":
            widget = QtWidgets.QDoubleSpinBox()
            widget.setDecimals(5)
            widget.setRange(-100000.0, 100000.0)
            widget.setValue(float(value or 0.0))
            widget.valueChanged.connect(_queue_save)
        elif kind == "choice":
            widget = QtWidgets.QComboBox()
            widget.addItems([str(x) for x in options])
            current = widget.findText(str(value or ""))
            if current >= 0:
                widget.setCurrentIndex(current)
            widget.currentIndexChanged.connect(_queue_save)
        else:
            widget = QtWidgets.QLineEdit(str(value or ""))
            widget.setMinimumWidth(0)
            widget.textChanged.connect(_queue_save)
        widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                             QtWidgets.QSizePolicy.Fixed)
        row.addWidget(widget, 1)

        modes = []
        if kind == "pick":
            modes = [("Pick", "pick")]
        elif kind == "pick_ref":
            modes = [("Pick", "pick_ref")]
        elif kind == "pick_element":
            modes = [("Pick", "pick_element")]
        elif kind == "pick_attr":
            modes = [("Pick", "pick_attr")]
        elif kind in ("file", "ma_fbx", "folder", "python_file"):
            modes = [("Browse", kind)]
        elif kind == "file_or_folder":
            modes = [("File", "file"), ("Folder", "folder")]
        for caption, mode in modes:
            button = QtWidgets.QPushButton(caption)
            button.setFixedWidth(58 if caption == "Browse" else
                                 52 if caption == "Folder" else 46)
            button.clicked.connect(
                lambda checked=False, target=widget, way=mode: _safe(
                    lambda: _pick_transform(target) if way == "pick"
                    else _pick_scale_reference(target) if way == "pick_ref"
                    else _pick_offset_element(target) if way == "pick_element"
                    else _pick_channel_attribute(
                        target, self.widgets["object"][1])
                    if way == "pick_attr"
                    else _browse_path(target, way)))
            row.addWidget(button)
        parent.addLayout(row)
        self.widgets[key] = (kind, widget)

    def _make_rotate_pairs(self, parent, pairs):
        """One freely editable direction-pair list owned by Match Rotate Pair."""
        self.rotate_pair_rows = []
        self.rotate_pair_layout = QtWidgets.QVBoxLayout()
        self.rotate_pair_layout.setSpacing(5)
        for item in pairs if isinstance(pairs, list) else []:
            self._add_rotate_pair_row(item)
        parent.addLayout(self.rotate_pair_layout)
        add = QtWidgets.QPushButton("+ Add Pair")
        add.clicked.connect(
            lambda checked=False: self._add_rotate_pair_row())
        parent.addWidget(add)

    def _add_rotate_pair_row(self, data=None):
        data = data if isinstance(data, dict) else {}
        frame = QtWidgets.QFrame(self.details)
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        content = QtWidgets.QVBoxLayout(frame)
        content.setContentsMargins(6, 5, 6, 6)
        content.setSpacing(4)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel()
        header.addWidget(title)
        header.addStretch(1)
        delete = QtWidgets.QPushButton("X")
        delete.setFixedWidth(28)
        delete.setToolTip("Delete this rotation pair")
        header.addWidget(delete)
        content.addLayout(header)

        data = _module("MatchRotatePair").PairData(data)
        row = {"frame": frame, "title": title}
        for key, label in (("from", "From"), ("from_child", "From Child"),
                           ("to", "To"), ("to_child", "To Child")):
            role = QtWidgets.QComboBox()
            role.addItems(["Rig", "Anim", "REF"])
            role.setCurrentText(data[key + "_role"])
            role.currentIndexChanged.connect(_queue_save)
            field = QtWidgets.QLineEdit(data[key])
            field.setPlaceholderText(label + " object")
            field.setMinimumWidth(0)
            field.textChanged.connect(_queue_save)
            pick = QtWidgets.QPushButton("Pick")
            pick.setFixedWidth(44)
            pick.clicked.connect(
                lambda checked=False, f=field, r=role: _safe(
                    lambda: _pick_pair_object(f, r)))
            line = QtWidgets.QHBoxLayout()
            line.setSpacing(4)
            caption = QtWidgets.QLabel(label)
            caption.setMinimumWidth(72)
            line.addWidget(caption)
            line.addWidget(role)
            line.addWidget(field, 1)
            line.addWidget(pick)
            content.addLayout(line)
            row[key + "_role"] = role
            row[key] = field
        delete.clicked.connect(
            lambda checked=False, selected=row:
            self._remove_rotate_pair_row(selected))
        self.rotate_pair_rows.append(row)
        self.rotate_pair_layout.addWidget(frame)
        self._number_rotate_pairs()
        _queue_save()

    def _remove_rotate_pair_row(self, row):
        self.rotate_pair_rows.remove(row)
        self.rotate_pair_layout.removeWidget(row["frame"])
        row["frame"].deleteLater()
        self._number_rotate_pairs()
        _queue_save()

    def _number_rotate_pairs(self):
        for index, row in enumerate(self.rotate_pair_rows, start=1):
            row["title"].setText("Pair {:02d}".format(index))

    def _make_set_values(self, parent, value):
        """Build editable, ordered values inside one Set Value module."""
        self.set_value_rows = []
        self.set_value_list = QtWidgets.QVBoxLayout()
        self.set_value_list.setSpacing(5)
        saved = _get_step(self.identifier)["data"]
        items = value if isinstance(value, list) else (
            [saved] if any(key in saved for key in (
                "source", "object", "attribute", "value")) else [])
        for item in items:
            self._add_set_value_row(item)
        parent.addLayout(self.set_value_list)

        add = QtWidgets.QPushButton("+ Add Sub Item")
        add.clicked.connect(lambda checked=False: self._add_set_value_row())
        parent.addWidget(add)

    def _add_set_value_row(self, data=None):
        data = data if isinstance(data, dict) else {}
        frame = QtWidgets.QFrame(self.details)
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        content = QtWidgets.QVBoxLayout(frame)
        content.setContentsMargins(6, 5, 6, 6)
        content.setSpacing(4)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel()
        header.addWidget(title)
        header.addStretch(1)
        delete = QtWidgets.QPushButton("X")
        delete.setToolTip("Remove this Set Value sub-item")
        delete.setFixedWidth(28)
        header.addWidget(delete)
        content.addLayout(header)

        namespace = QtWidgets.QComboBox()
        namespace.addItems(["Rig", "Anim", "REF"])
        namespace.setCurrentText(str(data.get("source") or "Rig"))
        namespace.currentIndexChanged.connect(_queue_save)
        obj = QtWidgets.QLineEdit(str(data.get("object") or ""))
        obj.setMinimumWidth(0)
        obj.setPlaceholderText("Object")
        obj.textChanged.connect(_queue_save)
        pick_obj = QtWidgets.QPushButton("Pick")
        pick_obj.setFixedWidth(44)
        pick_obj.clicked.connect(
            lambda checked=False: _safe(lambda: _pick_transform(obj)))

        first = QtWidgets.QHBoxLayout()
        first.setSpacing(4)
        first.addWidget(QtWidgets.QLabel("Namespace"))
        first.addWidget(namespace)
        first.addWidget(QtWidgets.QLabel("Object"))
        first.addWidget(obj, 1)
        first.addWidget(pick_obj)
        content.addLayout(first)

        attribute = QtWidgets.QLineEdit(str(data.get("attribute") or ""))
        attribute.setMinimumWidth(0)
        attribute.setPlaceholderText("Attribute")
        attribute.textChanged.connect(_queue_save)
        pick_attr = QtWidgets.QPushButton("Pick")
        pick_attr.setFixedWidth(44)
        pick_attr.setToolTip("Pick one attribute in Maya Channel Box")
        pick_attr.clicked.connect(
            lambda checked=False: _safe(
                lambda: _pick_channel_attribute(attribute, obj)))
        value = QtWidgets.QLineEdit(str(data.get("value", "0")))
        value.setMinimumWidth(75)
        value.setPlaceholderText("Value")
        value.textChanged.connect(_queue_save)

        second = QtWidgets.QHBoxLayout()
        second.setSpacing(4)
        second.addWidget(QtWidgets.QLabel("Attribute"))
        second.addWidget(attribute, 1)
        second.addWidget(pick_attr)
        second.addWidget(QtWidgets.QLabel("Value"))
        second.addWidget(value, 1)
        content.addLayout(second)

        row = {"frame": frame, "title": title, "source": namespace,
               "object": obj, "attribute": attribute, "value": value}
        delete.clicked.connect(
            lambda checked=False, selected=row:
            self._remove_set_value_row(selected))
        self.set_value_rows.append(row)
        self.set_value_list.addWidget(frame)
        self._number_set_value_rows()
        _queue_save()

    def _remove_set_value_row(self, row):
        self.set_value_rows.remove(row)
        self.set_value_list.removeWidget(row["frame"])
        row["frame"].deleteLater()
        self._number_set_value_rows()
        _queue_save()

    def _number_set_value_rows(self):
        for index, row in enumerate(self.set_value_rows, start=1):
            row["title"].setText("Sub Item {:02d}".format(index))

    def _make_mapping(self, parent, pairs):
        parent.addWidget(QtWidgets.QLabel(
            "Mapping pairs  |  double-click names to edit; T = translation"))
        self.pairs_tree = QtWidgets.QTreeWidget()
        self.pairs_tree.setObjectName("RetargetMappingPairs")
        self.pairs_tree.setHeaderLabels(["Old Source", "New Driven", "T"])
        self.pairs_tree.setRootIsDecorated(False)
        self.pairs_tree.setAlternatingRowColors(True)
        self.pairs_tree.setMinimumHeight(165)
        self.pairs_tree.setMaximumHeight(280)
        self.pairs_tree.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection)
        header = self.pairs_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(2, 32)
        for pair in pairs:
            self.pairs_tree.addTopLevelItem(_mapping_item(pair))
        self.pairs_tree.itemChanged.connect(_queue_save)
        parent.addWidget(self.pairs_tree)

        for which, caption in (("old", "Old Source"),
                               ("new", "New Driven")):
            parent.addWidget(QtWidgets.QLabel(caption))
            row = QtWidgets.QHBoxLayout()
            edit = QtWidgets.QLineEdit()
            edit.setMinimumWidth(0)
            row.addWidget(edit, 1)
            pick = QtWidgets.QPushButton("Pick")
            pick.setFixedWidth(46)
            pick.clicked.connect(lambda checked=False, field=edit: _safe(
                lambda: _pick_transform(field)))
            row.addWidget(pick)
            parent.addLayout(row)
            self.widgets["mapping_" + which] = ("text", edit)

        self.pair_translate = QtWidgets.QCheckBox(
            "Transfer Translate for new pair (root motion)")
        parent.addWidget(self.pair_translate)
        row = QtWidgets.QHBoxLayout()
        for name, action in (("Add Pair", self._pair_add),
                             ("Update Pair", self._pair_update),
                             ("Remove", self._pair_remove),
                             ("Auto Map", self._pair_auto_map)):
            button = QtWidgets.QPushButton(name)
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Fixed)
            button.clicked.connect(lambda checked=False, fn=action:
                                   _safe(fn))
            row.addWidget(button)
        parent.addLayout(row)
        self.pairs_tree.itemSelectionChanged.connect(self._show_pair)

    def _pairs(self):
        result = []
        for i in range(self.pairs_tree.topLevelItemCount()):
            entry = self.pairs_tree.topLevelItem(i)
            old = rt.leaf(entry.text(0).strip())
            new = rt.leaf(entry.text(1).strip())
            if not old or not new:
                raise ValueError("Mapping pairs require both Old and New.")
            result.append({"old": old, "new": new,
                           "translate": entry.checkState(2) ==
                                        QtCore.Qt.Checked})
        if len({item["new"] for item in result}) != len(result):
            raise ValueError("Each target control can be mapped only once.")
        return result

    def _new_pair(self):
        old = rt.leaf(self.widgets["mapping_old"][1].text().strip())
        new = rt.leaf(self.widgets["mapping_new"][1].text().strip())
        if not old or not new:
            raise ValueError("Pick or type both mapping controls.")
        return {"old": old, "new": new,
                "translate": self.pair_translate.isChecked()}

    def _show_pair(self):
        selected = self.pairs_tree.currentItem()
        if selected is None:
            return
        self.widgets["mapping_old"][1].setText(selected.text(0))
        self.widgets["mapping_new"][1].setText(selected.text(1))
        self.pair_translate.setChecked(
            selected.checkState(2) == QtCore.Qt.Checked)

    def _pair_add(self):
        pair = self._new_pair()
        if pair["new"] in {item["new"] for item in self._pairs()}:
            raise ValueError("Target already mapped: " + pair["new"])
        self.pairs_tree.addTopLevelItem(_mapping_item(pair))
        _save_editor()

    def _pair_update(self):
        selected = self.pairs_tree.currentItem()
        if selected is None:
            raise ValueError("Select a pair to update.")
        pair = self._new_pair()
        if pair["new"] in {item["new"] for item in self._pairs()
                           if item["new"] != rt.leaf(selected.text(1))}:
            raise ValueError("Target already mapped: " + pair["new"])
        selected.setText(0, pair["old"])
        selected.setText(1, pair["new"])
        selected.setCheckState(2, QtCore.Qt.Checked if pair["translate"]
                               else QtCore.Qt.Unchecked)
        _save_editor()

    def _pair_remove(self):
        selected = self.pairs_tree.currentItem()
        if selected is None:
            return
        index = self.pairs_tree.indexOfTopLevelItem(selected)
        self.pairs_tree.takeTopLevelItem(index)
        _save_editor()

    def _pair_auto_map(self):
        source = {}
        target = {}
        for obj in rt.mapping_candidates(rt.OLD_NS):
            source.setdefault(rt.leaf(obj), []).append(obj)
        for obj in rt.mapping_candidates(rt.NEW_NS):
            target.setdefault(rt.leaf(obj), []).append(obj)
        existing = {item["new"] for item in self._pairs()}
        added = 0
        for name in sorted(set(source) & set(target)):
            if (len(source[name]) == len(target[name]) == 1
                    and name not in existing):
                self.pairs_tree.addTopLevelItem(_mapping_item(
                    {"old": name, "new": name, "translate": False}))
                added += 1
        _save_editor()
        _status("{} mapping pair(s) added.".format(added))

    def settings(self):
        """Return JSON-compatible data collected from this card."""
        record = _get_step(self.identifier)
        values = copy.deepcopy(record["data"])
        name = self.name.text().strip()
        if not name:
            raise ValueError("Module Name cannot be empty.")
        for key, (kind, widget) in self.widgets.items():
            if key.startswith("mapping_"):
                continue
            if kind == "pairs":
                value = self._pairs()
            elif kind == "rotate_pairs":
                value = [
                    {key: (row[key].currentText() if key.endswith("_role")
                           else row[key].text().strip())
                     for key in ("from_role", "from", "from_child_role",
                                 "from_child", "to_role", "to",
                                 "to_child_role", "to_child")}
                    for row in widget]
            elif kind == "set_values":
                value = [
                    {"source": row["source"].currentText(),
                     "object": row["object"].text().strip(),
                     "attribute": row["attribute"].text().strip(),
                     "value": row["value"].text()}
                    for row in widget]
            elif kind == "bool":
                value = widget.isChecked()
            elif kind == "script":
                value = widget.toPlainText()
            elif kind in ("int", "float"):
                value = widget.value()
            elif kind == "transform9":
                value = {
                    group: [
                        _transform_number(control.text(),
                                          "{} {}".format(group, "XYZ"[index]))
                        for index, control in enumerate(controls)
                    ]
                    for group, controls in widget.items()
                }
            elif kind == "scale_target":
                role, obj, attrs = widget
                value = {
                    "role": role.currentText(),
                    "object": obj.text().strip(),
                    "attributes": {axis: field.text().strip()
                                   for axis, field in attrs.items()},
                }
            elif kind == "choice":
                value = widget.currentText()
            else:
                value = widget.text()
            values[key] = value
        if self.kind == "SetValue":
            values = {"items": values.get("items", [])}
        elif self.kind == "MatchRotatePair":
            values = {"pairs": values.get("pairs", [])}
        return {"name": name, "order": self.order.value(),
                "enabled": self.enabled.isChecked(), "data": values}


def _fit_form_to_contents():
    """Update the embedded form and Maya window height when General changes."""
    widget = UIs.get("widget")
    if widget is None:
        return
    layout = widget.layout()
    layout.invalidate()
    layout.activate()
    widget.setMinimumHeight(widget.sizeHint().height())
    widget.updateGeometry()
    top_level = widget.window()
    if top_level is not None:
        top_level.adjustSize()


def _build_general_form(parent):
    """Create scene-level fields above the scrollable module list."""
    section = QtWidgets.QGroupBox("General Settings")
    section.setObjectName("RetargetGeneralSettings")
    section_layout = QtWidgets.QVBoxLayout(section)
    section_layout.setContentsMargins(9, 11, 9, 9)
    section_layout.setSpacing(7)
    UIs["general_fields"] = {}

    groups = (
        ("New Rig", (
            ("New Rig (.ma / .mb / .fbx)", "new_path", "file"),
            ("New Rig Namespace", "new_namespace", "text"))),
        ("Old Animations", (
            ("Old Animations (File / Folder)", "old_animations_path",
             "animation_source"),
            ("Old Animations Namespace", "old_animations_namespace", "text"))),
        ("Reference Pose", (
            ("Reference Pose (.ma / .mb / .fbx)", "reference_pose_path",
             "file"),
            ("Reference Pose Namespace", "reference_pose_namespace", "text"))),
        ("Output", (
            ("Output Folder", "output_folder", "folder"),)),
    )
    for title, descriptors in groups:
        if title == "Output":
            # Keep Output Folder without a separate Output heading.
            group = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(group)
            layout.setContentsMargins(10, 4, 10, 4)
        else:
            group = QtWidgets.QFrame()
            group.setFrameShape(QtWidgets.QFrame.StyledPanel)
            layout = QtWidgets.QVBoxLayout(group)
            layout.setContentsMargins(10, 8, 10, 8)
        group.setObjectName("RetargetGeneral_" + title.replace(" ", ""))
        layout.setSpacing(5)
        for label, key, kind in descriptors:
            layout.addWidget(QtWidgets.QLabel(label))
            line = QtWidgets.QHBoxLayout()
            field = QtWidgets.QLineEdit()
            field.setMinimumWidth(0)
            field.textChanged.connect(_queue_save)
            if kind == "animation_source":
                mode = QtWidgets.QComboBox()
                mode.addItems(["File", "Folder"])
                mode.setToolTip("File: one animation. Folder: all valid clips.")
                line.addWidget(mode)
                UIs["general_mode"] = mode
                mode.currentIndexChanged.connect(
                    lambda _, editor=field: editor.clear())
                mode.currentIndexChanged.connect(_queue_save)
            line.addWidget(field, 1)
            if kind in ("file", "folder", "animation_source"):
                button = QtWidgets.QPushButton("Browse")
                button.setFixedWidth(62)
                if kind == "animation_source":
                    button.clicked.connect(
                        lambda checked=False, editor=field, selector=mode:
                        _safe(lambda: _browse_path(
                            editor, selector.currentText().lower())))
                else:
                    button.clicked.connect(
                        lambda checked=False, editor=field, source=kind:
                        _safe(lambda: _browse_path(editor, source)))
                line.addWidget(button)
            layout.addLayout(line)
            UIs["general_fields"][key] = field
        section_layout.addWidget(group)
    parent.addWidget(section)
    _set_general_form()
    return section


def _general_from_form():
    """Read all global edits; called only by the main Save action."""
    values = {key: widget.text().strip()
              for key, widget in UIs.get("general_fields", {}).items()}
    mode = UIs.get("general_mode")
    if mode is not None:
        values["old_animations_mode"] = mode.currentText()
    return _normalize_general(values)


def _set_general_form():
    """Restore saved inputs without clearing Old Animations on mode change."""
    general = _normalize_general(_STATE.get("general"))
    prior = UIs.get("building", False)
    UIs["building"] = True
    try:
        mode = UIs.get("general_mode")
        if mode is not None:
            blocked = mode.blockSignals(True)
            mode.setCurrentText(general["old_animations_mode"])
            mode.blockSignals(blocked)
        for key, widget in UIs.get("general_fields", {}).items():
            widget.setText(str(general.get(key) or ""))
    finally:
        UIs["building"] = prior


def _rebuild_cards(focus=None):
    """Stack modules vertically; each expanded module owns its own columns."""
    area = UIs.get("cards_layout")
    if area is None:
        return
    UIs["building"] = True
    try:
        while area.count():
            child = area.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        UIs["cards"] = {}
        if focus is not None:
            _STATE.setdefault("expanded", {})[focus] = True
        for record in _sorted_steps():
            card = RetargetCard(record, UIs["cards_container"])
            UIs["cards"][record["id"]] = card
            area.addWidget(card)
        area.addStretch(1)
    finally:
        UIs["building"] = False


def _move_step(identifier, direction):
    def work():
        _save_editor()
        steps = _sorted_steps()
        record = _get_step(identifier)
        index = steps.index(record)
        target = index + int(direction)
        if target < 0 or target >= len(steps):
            return
        steps[index], steps[target] = steps[target], steps[index]
        for number, item in enumerate(steps, 1):
            item["order"] = number * 10
        _STATE["dirty"] = True
        _rebuild_cards()
        _status("Module order changed. Click Save to keep it.")
    return _safe(work)


def _apply_manual_order():
    if UIs.get("building"):
        return
    _save_editor()
    _rebuild_cards()
    _STATE["dirty"] = True
    _status("Order changed. Click Save to keep it.")


def _delete_step(identifier):
    def work():
        step = _get_step(identifier)
        if step is None:
            return
        _save_editor(write=False)
        _STATE["steps"].remove(step)
        _STATE.get("expanded", {}).pop(identifier, None)
        if _default_path():
            # Deleting is an explicit persistent action. Update the manifest
            # and module JSON now; the last instance removes its JSON file.
            _write_profile()
            message = "Deleted module and saved JSON data: " + step["name"]
        else:
            _STATE["dirty"] = True
            message = "Removed module from form: " + step["name"]
        _rebuild_cards()
        _status(message)
    return _safe(work)


def _add_step(*args):
    def work():
        _save_editor()
        kind = UIs["step_type"].currentData()
        if kind not in ("Script", "PythonFile", "Transform",
                         "OffsetPosition", "SetValue") and any(
                s["kind"] == kind for s in _STATE["steps"]):
            raise ValueError(kind + " already exists; edit its module.")
        record = _new_step(kind, max(
            (s["order"] for s in _STATE["steps"]), default=0) + 10)
        _STATE["steps"].append(record)
        _STATE["dirty"] = True
        _rebuild_cards(focus=record["id"])
        _status("Added module " + record["name"] + ". Click Save to keep it.")
    return _safe(work)


def _reload_current_scene(*args):
    """Force-open the current scene file, discarding unsaved scene edits."""
    def work():
        scene = cmds.file(query=True, sceneName=True) or ""
        if not scene:
            raise ValueError("Current Maya scene has no file path to reopen.")
        if not os.path.isfile(scene):
            raise FileNotFoundError("Current Maya scene file not found: " + scene)
        # This is intentionally destructive: the owner explicitly requested
        # a force reload with no confirmation or modified-scene check.
        cmds.file(scene, open=True, force=True)
        _STATE["context"] = {}
        _status("Reopened current Maya scene: " + scene)
        return scene
    return _safe(lambda: _quiet_file_run(work))


def _load_all(*args):
    """Load a complete profile; don't replace the form on a broken JSON."""
    def work():
        previous = {
            key: copy.deepcopy(_STATE.get(key))
            for key in ("steps", "general", "expanded",
                        "path", "context", "selected_id", "dirty")
        }
        try:
            loaded = _read_profile()
            if loaded is None:
                _status("No RetargetData found beside the current Maya scene.")
                return
            _STATE.update({"steps": loaded, "path": _default_path(),
                           "context": {}, "selected_id": None,
                           "dirty": False,
                           "expanded": {step["id"]: False
                                        for step in loaded}})
            _set_general_form()
            _rebuild_cards()
        except Exception:
            # _read_profile can set general/expanded while still reading
            # instance files. Restore the previously visible editor if
            # even one module JSON is missing or invalid.
            _STATE.update(previous)
            _set_general_form()
            _rebuild_cards()
            raise
        _status("Loaded RetargetData: " + _STATE["path"])
    return _safe(work)


def _collect_editor_snapshot():
    """Collect all live cards exactly once without changing saved _STATE."""
    # Commit a typed spin-box text edit still in progress when Save is pressed.
    focused = QtWidgets.QApplication.focusWidget()
    while focused is not None:
        if isinstance(focused, QtWidgets.QAbstractSpinBox):
            focused.interpretText()
            break
        focused = focused.parentWidget()

    records = copy.deepcopy(_STATE["steps"])
    by_id = {record["id"]: record for record in records}
    if len(by_id) != len(records):
        raise ValueError("Duplicate Retarget module ID in the editor.")
    cards = UIs.get("cards", {})
    if "cards" not in UIs or set(cards) != set(by_id):
        raise ValueError(
            "Retarget UI cards and module records are out of sync. "
            "Reload Retarget before saving.")
    for identifier, card in list(cards.items()):
        if identifier not in by_id:
            raise ValueError("Unknown Retarget module card: " + identifier)
        # Read each module once, including hidden/collapsed card widgets.
        settings = card.settings()
        if not isinstance(settings, dict) or not isinstance(
                settings.get("data"), dict):
            raise ValueError("Invalid Retarget card data: " + identifier)
        by_id[identifier].update(settings)

    general = _general_from_form()
    _general_context(general, {})  # Validate without importing anything.
    snapshot = {
        "steps": records,
        "general": general,
        "expanded": copy.deepcopy(_STATE.get("expanded", {})),
    }
    # Detect unsupported values before changing any JSON files.
    json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
    return snapshot


def _verify_saved_profile(path, snapshot):
    """Compare persisted JSON with the exact in-memory UI snapshot."""
    with open(path, "r", encoding="utf-8") as stream:
        saved = json.load(stream)
    steps = snapshot["steps"]
    expected_manifest = [
        {"id": item["id"], "kind": item["kind"],
         "name": item["name"], "order": int(item["order"]),
         "enabled": bool(item["enabled"])}
        for item in steps
    ]
    expected_expanded = {
        item["id"]: bool(snapshot.get("expanded", {}).get(
            item["id"], item["kind"] == "Scale"))
        for item in steps
    }
    if (saved.get("version") != 7 or
            saved.get("steps") != expected_manifest or
            saved.get("general") != _normalize_general(snapshot["general"]) or
            saved.get("expanded") != expected_expanded):
        raise ValueError("Retarget.json does not match saved form settings.")

    folder = os.path.dirname(path)
    for item in steps:
        instance = _instance_data_path(folder, item["kind"], item["id"])
        with open(instance, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        expected = {"version": 3, "id": item["id"],
                    "kind": item["kind"], "data": item["data"]}
        if data != expected:
            raise ValueError("Saved module data mismatch: " + instance)


def _save_all(*args):
    """Single main Save for all cards, general settings and order."""
    def work():
        snapshot = _collect_editor_snapshot()
        path = _write_profile(snapshot, verify=_verify_saved_profile)
        _STATE.update({
            "steps": snapshot["steps"],
            "general": snapshot["general"],
            "expanded": snapshot["expanded"],
            "path": path,
            "dirty": False,
        })
        # Editing Name/Order/Enabled must update the card header immediately,
        # without reconstructing every Qt widget and losing edit focus.
        for item in snapshot["steps"]:
            card = UIs.get("cards", {}).get(item["id"])
            if card is not None:
                card.refresh_title(item)
        _status("Saved and verified Retarget form and modules: " + path)
        return path
    return _safe(work)


def _validate_sequence(batch, records=None):
    """Validate the execution sequence sorted by each module's saved order."""
    ordered = (_sorted_steps() if records is None else
               sorted(records, key=lambda item: int(item["order"])))
    steps = [step for step in ordered
             if step.get("enabled")
             and (not batch or step["kind"] != "Bake")]
    seen = set()
    prerequisites = {
        # Bake is a standalone test module for now, not a Run Retarget step.
        "Bake": ("Mapping", "Animation"),
    }
    for item in steps:
        kind = item["kind"]
        if kind not in ("Script", "PythonFile", "Transform",
                        "OffsetPosition", "SetValue") and kind in seen:
            raise ValueError(
                "Only Script, PythonFile, Extra Transform, Set Value and "
                "Offset Position may be repeated: " + kind)
        if kind in ("Scale", "Rotate") and (
                "Mapping" in seen or "Animation" in seen):
            raise ValueError(kind + " must run before Mapping / Animation.")
        if (kind == "Animation"
                and any(step["kind"] == "Mapping" for step in steps)
                and "Mapping" not in seen):
            raise ValueError("Animation must appear after Mapping when "
                             "Mapping is enabled.")
        for needed in prerequisites.get(kind, ()):
            if needed not in seen:
                raise ValueError("{} must appear after {}.".format(kind, needed))
        if "Save" in seen:
            raise ValueError("Save Retarget must be the last enabled step.")
        seen.add(kind)
    # The main runner owns rig/pose/animation imports, so it can run even
    # without any enabled cards. Save is purely an optional final module.
    return steps


def _saved_execution_steps(batch):
    """Sort using Retarget.json alone; defer instance JSON until needed."""
    manifest = _read_manifest()
    if manifest is None:
        raise ValueError(
            "No saved RetargetData for this scene. Click Save on the "
            "Retarget form before running.")
    steps = _validate_sequence(batch, manifest)
    _status("Retarget.json run order: " + " -> ".join(
        "{}({})".format(item["kind"], item["order"]) for item in steps))
    return steps


def _run_step(item, context):
    result = _module(item["kind"]).Run(copy.deepcopy(item["data"]), context)
    _status("{}: {}".format(item["name"], result))
    return result


def _load_retarget_assets(general, clip, context):
    """Load rig, optional bind pose and clip with either RetargetV2 engine.

    Some installed Maya machines still import an older NLTA_RetargetV2
    which has load_asset() but not load_retarget_assets().  Reuse the new
    engine helper when present; otherwise perform the same three imports
    with the existing load_asset() API.
    """
    loader = getattr(rt, "load_retarget_assets", None)
    if callable(loader):
        return loader(general, clip, context)

    load_asset = getattr(rt, "load_asset", None)
    if not callable(load_asset):
        raise RuntimeError(
            "NLTA_RetargetV2 is missing load_asset(). Update the engine "
            "at: {}".format(getattr(rt, "__file__", "<unknown>")))

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


def _import_assets_with_fbx_mode(general, clip, context):
    """Force FBX File Content=Add so pose/clip objects get new namespaces.

    Maya may retain FBX import mode 'merge' / 'exmerge' from an earlier UI
    import, which updates existing animation and produces no new transform
    nodes. Restore the exact previous mode, including if an import fails.
    """
    paths = (general.get("new_path", ""),
             general.get("reference_pose_path", ""), clip)
    if not any(os.path.splitext(str(path))[1].lower() == ".fbx"
               for path in paths):
        return _load_retarget_assets(general, clip, context)

    if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
        cmds.loadPlugin("fbxmaya", quiet=True)
    previous = str(mel.eval("FBXImportMode -q;")).strip().lower()
    mel.eval('FBXImportMode -v "add";')
    try:
        return _load_retarget_assets(general, clip, context)
    finally:
        if previous in ("add", "merge", "exmerge"):
            mel.eval('FBXImportMode -v "{}";'.format(previous))


def _process_clip(general, clip, steps):
    """Process one clip inside the Maya scene that is already open."""
    context = _general_context(
        general, {"batch": True, "animation_path_override": clip,
                  "pre_bake": True})
    # Do not import the clip again inside the Animation step.
    _import_assets_with_fbx_mode(general, clip, context)

    # Alignment stages need a unique top-level controller in the new rig.
    if any(item["kind"] == "Rotate" or
           (item["kind"] == "Scale" and (
               "scale_target" not in (item.get("data") or {}) or
               (item.get("data") or {}).get("legacy_root_scale")))
           for item in steps):
        # Only older Set Scale configurations require auto-detected roots.
        context["target_root"] = rt.auto_root(context["target_namespace"])

    for item in steps:
        if item["kind"] == "Bake":
            continue  # Bake will be designed and run separately later.
        _run_step(item, context)
    if any(item["kind"] == "Save" for item in steps):
        if not context.get("output_path"):
            raise ValueError("Save Retarget did not create an output.")
    return context.get("output_path")


def _quiet_file_run(action):
    """Run without file prompts or noisy Maya warnings; keep real errors.

    Both Maya file prompt state and Script Editor warning suppression are
    global settings, so they must be restored after every Retarget run.
    """
    previous_prompt = bool(cmds.file(query=True, prompt=True))
    cmds.file(prompt=False)
    info = getattr(cmds, "scriptEditorInfo", None)
    previous_warnings = None
    try:
        if callable(info):
            try:
                previous_warnings = bool(
                    info(query=True, suppressWarnings=True))
                info(suppressWarnings=True)
            except (RuntimeError, TypeError):
                # Older/headless Maya builds may lack this Script Editor API.
                previous_warnings = None
        return action()
    finally:
        try:
            if previous_warnings is not None:
                info(suppressWarnings=previous_warnings)
        finally:
            cmds.file(prompt=previous_prompt)


def _current_scene_objects():
    """Return user DAG objects, ignoring Maya's four built-in cameras."""
    roots = cmds.ls(assemblies=True, long=True) or []
    default_cameras = {"persp", "top", "front", "side"}
    return [node for node in roots
            if str(node).split("|")[-1] not in default_cameras]


def _confirm_scene_objects(objects):
    """Warn only when the current scene already contains user objects."""
    if not objects:
        return True
    sample = ", ".join(str(node) for node in objects[:5])
    if len(objects) > 5:
        sample += ", ..."
    answer = cmds.confirmDialog(
        title="Retarget - Scene Contains Objects",
        message=("The current Maya scene already contains {} object(s):\n"
                 "{}\n\nRun Retarget using this scene anyway? "
                 "Existing objects will remain in the scene.").format(
                     len(objects), sample),
        button=["Continue", "Cancel"], defaultButton="Cancel",
        cancelButton="Cancel", dismissString="Cancel")
    return answer == "Continue"


def _scene_template(original, needed):
    """Find a reusable scene base; snapshot modified/unnamed scenes if needed.

    The snapshot is an export, not an opened new scene. It preserves the
    current Maya scene, including unsaved edits, for folder processing.
    """
    if not needed:
        return "", None
    if (original and os.path.isfile(original)
            and not cmds.file(query=True, modified=True)):
        return original, None
    temporary = tempfile.TemporaryDirectory(prefix="nlta_retarget_")
    template = os.path.join(temporary.name, "current_scene.ma")
    try:
        cmds.file(template, exportAll=True, type="mayaAscii", force=True,
                  preserveReferences=True)
    except Exception:
        temporary.cleanup()
        raise
    if not os.path.isfile(template):
        temporary.cleanup()
        raise RuntimeError("Unable to snapshot the current Maya scene.")
    return template, temporary


def _open_scene_template(template, original):
    """Reopen the exact original scene state, even from a temporary snapshot."""
    cmds.file(template, open=True, force=True)
    if template != original:
        # A temporary snapshot must not become the user's scene filename.
        cmds.file(rename=original if original else "untitled")


def _run_retarget(*args):
    """Use the current scene; reopen that same base before each extra clip."""
    def work():
        manifest = _saved_execution_steps(True)
        steps = [_read_instance(item) for item in manifest]
        general = _normalize_general(_STATE["general"])
        _general_context(general, {})

        source = str(general["old_animations_path"] or "").strip()
        mode = str(general["old_animations_mode"] or "File").title()
        if mode == "File" and not os.path.isfile(source):
            raise ValueError("Old Animations File must be an existing file.")
        if mode == "Folder" and not os.path.isdir(source):
            raise ValueError("Old Animations Folder must be an existing folder.")
        clips = rt.animation_files(source)
        rt.ensure_file(general["new_path"])
        pose = str(general.get("reference_pose_path") or "").strip()
        if pose:
            rt.ensure_file(pose)
        save_enabled = any(item["kind"] == "Save" for item in steps)
        if save_enabled and not str(general["output_folder"]).strip():
            raise ValueError("Set Output Folder when Save Retarget is enabled.")

        original = cmds.file(query=True, sceneName=True) or ""
        if not _confirm_scene_objects(_current_scene_objects()):
            return []

        # Processing a folder reopens the same original scene between clips.
        # If the current scene is unnamed/modified, export a temporary copy
        # rather than discarding unsaved contents or requiring a manual Save.
        template, temporary = _scene_template(
            original, needed=(len(clips) > 1 or save_enabled))
        completed = []
        success = False
        try:
            for index, clip in enumerate(clips):
                if index:
                    _open_scene_template(template, original)
                output = _process_clip(general, clip, steps)
                completed.append(output if save_enabled else clip)
            success = True
        finally:
            try:
                # Successful no-Save runs leave the last result in Maya.
                # With Save, or on failure, restore the original scene if
                # a restorable base exists; never create an empty scene.
                if (save_enabled or not success) and template:
                    _open_scene_template(template, original)
            finally:
                if temporary is not None:
                    temporary.cleanup()
                _STATE["context"] = {}
        if save_enabled:
            _status("Retarget setup complete (no Bake): {} scenes saved.".format(
                len(completed)))
        else:
            _status("Retarget complete: {} clip(s) processed.".format(
                len(completed)))
        return completed
    return _safe(lambda: _quiet_file_run(work))


def GetPairsName(*args):
    """Compatibility helper used by older scripts."""
    item = next((step for step in _STATE["steps"]
                 if step["kind"] == "Mapping"), None)
    return [[pair["old"], pair["new"]]
            for pair in item["data"].get("pairs", [])] if item else []


def BakeAnimation(*args):
    """Compatibility helper: explicitly confirmed ordered batch."""
    return _run_retarget(*args)


def CreateUI(data):
    """Embed a responsive PySide module-card editor into the existing NLTA Form."""
    UIs.clear()
    _STATE.update({"steps": [], "path": _default_path(), "context": {},
                   "general": _general_defaults(),
                   "expanded": {}, "selected_id": None, "dirty": False})
    loaded = _read_profile()
    _STATE["steps"] = loaded if loaded is not None else _default_steps()
    _STATE["expanded"] = {
        step["id"]: False for step in _STATE["steps"]
    }

    parent = data["parent"]
    name = data.get("module", "Retarget")
    if cmds.layout(name, exists=True):
        cmds.deleteUI(name)
    root = cmds.rowColumnLayout(
        name, numberOfColumns=1, adjustableColumn=1, parent=parent)
    host = cmds.columnLayout(adjustableColumn=True, parent=root)

    widget = QtWidgets.QWidget()
    widget.setObjectName("NLTA_RetargetWidget")
    widget.setMinimumWidth(1060)
    widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                         QtWidgets.QSizePolicy.Preferred)
    main = QtWidgets.QVBoxLayout(widget)
    main.setContentsMargins(7, 7, 7, 7)
    main.setSpacing(6)

    columns = QtWidgets.QHBoxLayout()
    columns.setSpacing(9)
    general_column = QtWidgets.QVBoxLayout()
    general_column.setContentsMargins(0, 0, 0, 0)
    _build_general_form(general_column)
    general_column.addStretch(1)
    columns.addLayout(general_column, 2)

    module_column = QtWidgets.QVBoxLayout()
    module_column.setContentsMargins(0, 0, 0, 0)
    module_column.setSpacing(6)
    picker_row = QtWidgets.QHBoxLayout()
    UIs["step_type"] = QtWidgets.QComboBox()
    for kind, filename in STEP_FILES:
        UIs["step_type"].addItem(_module(kind).LABEL, kind)
    # The display name is descriptive; Add uses the stable kind ID.
    picker_row.addWidget(UIs["step_type"], 1)
    add = QtWidgets.QPushButton("+ Add Module")
    add.clicked.connect(_add_step)
    picker_row.addWidget(add)
    module_column.addLayout(picker_row)

    area = QtWidgets.QScrollArea()
    area.setFixedHeight(500)
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
    area.setFrameShape(QtWidgets.QFrame.NoFrame)
    cards_container = QtWidgets.QWidget()
    cards_container.setMinimumWidth(580)
    cards_layout = QtWidgets.QVBoxLayout(cards_container)
    cards_layout.setContentsMargins(1, 1, 1, 1)
    cards_layout.setSpacing(6)
    area.setWidget(cards_container)
    module_column.addWidget(area)
    columns.addLayout(module_column, 3)
    main.addLayout(columns)

    # Scene-level actions sit below both General and the module list.
    action_row = QtWidgets.QHBoxLayout()
    action_row.setSpacing(6)
    for label, function in (("Save", _save_all),
                            ("Load", _load_all),
                            ("Reload Current Scene", _reload_current_scene),
                            ("Run Retarget", _run_retarget)):
        button = QtWidgets.QPushButton(label)
        if label == "Reload Current Scene":
            button.setObjectName("RetargetReloadCurrentScene")
            button.setToolTip(
                "Force reopen the currently named Maya scene from disk; "
                "unsaved Maya scene changes are discarded.")
        elif label == "Run Retarget":
            button.setObjectName("RetargetRun")
            button.setToolTip(
                "Process the selected animation file or every file in the "
                "Old Animations folder, then save outputs when enabled.")
        button.clicked.connect(function)
        action_row.addWidget(
            button, 2 if label in ("Reload Current Scene",
                                   "Run Retarget") else 1)
    main.addLayout(action_row)

    startup_message = (
        "Loaded scene RetargetData: " + _STATE["path"]
        if loaded is not None else
        "No saved RetargetData for this scene. Save the Maya scene first, "
        "then use Save to store all modules.")
    UIs["status"] = QtWidgets.QLabel(startup_message)
    UIs["status"].setWordWrap(True)
    main.addWidget(UIs["status"])
    UIs.update({"widget": widget, "root": root, "host": host, "area": area,
                "cards_container": cards_container,
                "cards_layout": cards_layout, "cards": {},
                "building": True})
    _rebuild_cards()

    maya_pointer = omui.MQtUtil.findLayout(host)
    if maya_pointer is None:
        widget.deleteLater()
        raise RuntimeError("Retarget cannot find its Maya host layout.")
    qt_pointer = int(getCppPointer(widget)[0])
    omui.MQtUtil.addWidgetToMayaLayout(qt_pointer, int(maya_pointer))

    # AutoInstall owns NLTA_Form; use a wider, resizable two-column form.
    window_name = data.get("windowName") or "NLTA_Form"
    if cmds.window(window_name, exists=True):
        cmds.window(window_name, edit=True, sizeable=True,
                    resizeToFitChildren=False)
    top_level = widget.window()
    if top_level is not None:
        top_level.setMinimumWidth(1080)
        top_level.resize(max(top_level.width(), 1180), top_level.height())
    _fit_form_to_contents()
    QtCore.QTimer.singleShot(0, _fit_form_to_contents)
    return root
