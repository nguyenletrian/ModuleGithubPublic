# -*- coding: utf-8 -*-
"""Public one-file NLTA installer for Autodesk Maya (Python 3)."""

import base64
import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import maya.cmds as cmds


TOOLS = ("Skinning", "Setup", "Scene", "Research", "Retarget")
LOADER_URL = (
    "https://api.github.com/repos/nguyenletrian/ModuleGithubPublic/"
    "contents/Github.py?ref=main"
)


def _install_folder(folder=None):
    """Use Maya's own user script directory, not a machine-specific drive."""
    base = folder or os.environ.get("NLTA_TOOL_FOLDER")
    if not base:
        base = os.path.join(cmds.internalVar(userScriptDir=True), "NLTA")
    return os.path.abspath(os.path.expanduser(os.path.expandvars(base)))


def _git_sha(data):
    return hashlib.sha1(
        ("blob %d\0" % len(data)).encode("ascii") + data
    ).hexdigest()


def _download_loader():
    request = Request(LOADER_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "NLTA-Maya-Installer",
    })
    with urlopen(request, timeout=15) as response:
        info = json.load(response)
    if info.get("encoding") != "base64":
        raise ValueError("GitHub returned an unsupported Github.py encoding")
    source = base64.b64decode(info["content"])
    if _git_sha(source) != info.get("sha"):
        raise ValueError("Github.py SHA verification failed")
    return source


def _save_loader(destination, source):
    folder = os.path.dirname(destination)
    os.makedirs(folder, exist_ok=True)
    if os.path.isfile(destination):
        with open(destination, "rb") as stream:
            if stream.read() == source:
                return False
        backup = destination + ".nlta-local-backup"
        if not os.path.exists(backup):
            shutil.copy2(destination, backup)

    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb", dir=folder, prefix=".nlta-", delete=False) as stream:
            stream.write(source)
            temp_name = stream.name
        os.replace(temp_name, destination)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.remove(temp_name)
    cache_folder = os.path.join(folder, "__pycache__")
    if os.path.isdir(cache_folder):
        for name in os.listdir(cache_folder):
            if name.startswith("Github.") and name.endswith(".pyc"):
                os.remove(os.path.join(cache_folder, name))
    legacy_cache = destination + "c"
    if os.path.isfile(legacy_cache):
        os.remove(legacy_cache)
    importlib.invalidate_caches()
    return True


def _load_local_github(folder):
    """Load exactly the Github.py installed in this folder."""
    if folder in sys.path:
        sys.path.remove(folder)
    sys.path.insert(0, folder)
    local_file = os.path.normcase(os.path.abspath(
        os.path.join(folder, "Github.py")))
    previous = sys.modules.get("Github")
    if previous is not None:
        loaded_file = os.path.normcase(os.path.abspath(
            getattr(previous, "__file__", "")))
        if loaded_file != local_file:
            sys.modules.pop("Github", None)
    module = importlib.import_module("Github")
    return importlib.reload(module)


def _required_files(folder):
    names = ["Github.py", os.path.join("Libs", "NLTA_General.py")]
    names.extend(os.path.join("UIs", name + ".py") for name in TOOLS)
    names.append(os.path.join(
        "UIs", "SkinningTools", "NLTA_Skinning_CommandBoard.py"))
    return [os.path.join(folder, name) for name in names]


def _prepare_runtime(folder):
    """Bootstrap the loader, then get the complete NLTA UI runtime from GitHub."""
    loader = os.path.join(folder, "Github.py")
    if os.environ.get("NLTA_SKIP_GITHUB_UPDATE", "").lower() in ("1", "true", "yes"):
        missing = [path for path in _required_files(folder)
                   if not os.path.isfile(path)]
        if missing:
            raise RuntimeError(
                "Offline installation requires an existing NLTA runtime:\n" +
                "\n".join(missing))
        print("[NLTA Install] Offline mode: using installed runtime")
        return _load_local_github(folder)
    try:
        source = _download_loader()
        if _save_loader(loader, source):
            print("[NLTA Install] Github.py installed / updated")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        if not os.path.isfile(loader):
            raise RuntimeError(
                "Cannot install NLTA from public GitHub: {}".format(exc))
        print("[NLTA Install] GitHub unavailable, checking existing files: {}".format(exc))

    github = _load_local_github(folder)
    if not callable(getattr(github, "SyncWindowModules", None)):
        raise RuntimeError("Local Github.py is too old. Reconnect and reinstall.")
    result = github.SyncWindowModules(folder, requested=TOOLS)
    missing = [path for path in _required_files(folder)
               if not os.path.isfile(path)]
    if missing:
        raise RuntimeError(
            "NLTA installation is incomplete; Shelf was not changed:\n" +
            "\n".join(missing))
    if result.get("error"):
        print("[NLTA Install] Existing local runtime will be used offline")
    else:
        print("[NLTA Install] {} files updated / {} checked".format(
            result.get("updated", 0), result.get("checked", 0)))
    return github


def _shelf_command(folder, tool):
    """Shelf command is self-contained and uses the installed local loader."""
    return """import os
import sys
import importlib

toolFolder = {folder!r}
if toolFolder in sys.path:
    sys.path.remove(toolFolder)
sys.path.insert(0, toolFolder)
if "Github" in sys.modules:
    current = os.path.normcase(os.path.abspath(
        getattr(sys.modules["Github"], "__file__", "")))
    expected = os.path.normcase(os.path.abspath(
        os.path.join(toolFolder, "Github.py")))
    if current != expected:
        sys.modules.pop("Github", None)
GH = importlib.reload(importlib.import_module("Github"))

GH.CreateTool({{
    "toolFolder": toolFolder,
    "paths": [],
    "UI": {{
        "windowName": "NLTA_Form",
        "windowTitle": "NLTA Tools",
        "updateFromGitHub": True,
        "standalone": {standalone},
        "column": {columns},
        "layouts": [{{
            "module": {tool!r},
            "title": {tool!r},
            "parent": "MainLayout",
            "titleFlags": {{"backgroundColor": (0.25, 0.25, 0.25), "height": 25}},
            "inputFlags": {{"height": 33}},
            "buttonFlags": {{"height": 33}},
            "layoutFlags": {{"backgroundColor": (0.3, 0.3, 0.3)}},
        }}]
    }}
}})
""".format(
        folder=folder, tool=tool,
        standalone=(tool == "Skinning"),
        columns=(1 if tool == "Retarget" else 4))


def _installed_shelf_buttons(shelf, tool):
    """Find only prior NLTA buttons; never replace an unrelated user's shelf."""
    matches = []
    for button in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.objectTypeUI(button) != "shelfButton":
            continue
        if cmds.shelfButton(button, query=True, label=True) != tool:
            continue
        command = cmds.shelfButton(button, query=True, command=True) or ""
        annotation = cmds.shelfButton(button, query=True, annotation=True) or ""
        if ("GH.CreateTool(" in command or
                annotation.startswith("NLTA / ")):
            matches.append(button)
    return matches


def _create_shelf(folder):
    shelf = cmds.tabLayout("ShelfLayout", query=True, selectTab=True)
    if not shelf:
        raise RuntimeError("Select an active Maya shelf before installing NLTA")
    for tool in TOOLS:
        options = dict(
            label=tool, imageOverlayLabel=tool,
            image1="commandButton.png", image="commandButton.png",
            style="iconAndTextHorizontal", sourceType="python",
            annotation="NLTA / {} - updates from GitHub on open".format(tool),
            command=_shelf_command(folder, tool),
            backgroundColor=(0.25, 0.35, 0.25),
            enableBackground=True,
        )
        matches = _installed_shelf_buttons(shelf, tool)
        if matches:
            cmds.shelfButton(matches[0], edit=True, **options)
            for duplicate in matches[1:]:
                cmds.deleteUI(duplicate)
        else:
            cmds.shelfButton(parent=shelf, **options)
    return shelf


def install(tool_folder=None):
    folder = _install_folder(tool_folder)
    print("[NLTA Install] Folder: " + folder)
    _prepare_runtime(folder)
    shelf = _create_shelf(folder)
    print("[NLTA Install] Ready: {} tools on {} | {}".format(
        len(TOOLS), shelf, folder))
    return folder


# AutoInstall remains directly executable from Maya Script Editor / import.
install()
