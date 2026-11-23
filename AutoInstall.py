# -*- coding: utf-8 -*-
"""Public one-file NLTA installer for Autodesk Maya (Python 3)."""

import base64
import hashlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from urllib.request import Request, urlopen

import maya.cmds as cmds


TOOLS = ("Skinning", "Setup", "Scene", "Research", "Retarget")
DEFAULT_INSTALL_FOLDER = r"D:\NLTA"
REPOSITORY_URL = "https://github.com/nguyenletrian/ModuleGithubPublic.git"
LOADER_URL = (
    "https://api.github.com/repos/nguyenletrian/ModuleGithubPublic/"
    "contents/Github.py?ref=main"
)
RAW_LOADER_URL = (
    "https://raw.githubusercontent.com/nguyenletrian/ModuleGithubPublic/"
    "main/Github.py"
)
ZIP_URLS = (
    "https://codeload.github.com/nguyenletrian/ModuleGithubPublic/zip/refs/heads/main",
    "https://github.com/nguyenletrian/ModuleGithubPublic/archive/refs/heads/main.zip",
)
RUNTIME_EXTENSIONS = (".py", ".mel", ".ui", ".qss", ".png", ".svg",
                      ".ico", ".jpg", ".jpeg")


def _install_folder(folder=None):
    """Keep installed code on D:, outside the user's frozen Maya Documents."""
    base = folder or os.environ.get("NLTA_TOOL_FOLDER") or DEFAULT_INSTALL_FOLDER
    return os.path.abspath(os.path.expanduser(os.path.expandvars(base)))


def _git_sha(data):
    return hashlib.sha1(
        ("blob %d\0" % len(data)).encode("ascii") + data
    ).hexdigest()


def _request_bytes(url):
    request = Request(url, headers={"User-Agent": "NLTA-Maya-Installer"})
    with urlopen(request, timeout=20) as response:
        return response.read()


def _download_loader():
    """Try GitHub API, then raw GitHub when the API returns 404/403."""
    errors = []
    for url in (LOADER_URL, RAW_LOADER_URL):
        try:
            content = _request_bytes(url)
            if url == LOADER_URL:
                info = json.loads(content)
                if info.get("encoding") != "base64":
                    raise ValueError("Unsupported Github.py encoding")
                source = base64.b64decode(info["content"])
                if _git_sha(source) != info.get("sha"):
                    raise ValueError("Github.py SHA verification failed")
            else:
                source = content
            if not source:
                raise ValueError("Empty Github.py response")
            return source
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append("{}: {}".format(url, exc))
    raise RuntimeError("Cannot download Github.py:\n" + "\n".join(errors))


def _runtime_file(relative):
    """Only install runtime code/resources; leave JSON and user data untouched."""
    parts = relative.replace("\\", "/").split("/")
    if any(part in ("..", "__pycache__", ".git") for part in parts):
        return False
    return (relative in ("Github.py", "RetargetTool.py")
            or relative.startswith(("Libs/", "UIs/"))) and (
                relative.lower().endswith(RUNTIME_EXTENSIONS))


def _install_runtime_files(folder, files):
    """Stage remote files first; overwrite code atomically and keep local backups."""
    prepared = []
    for relative, content in files:
        relative = relative.replace("\\", "/")
        if not _runtime_file(relative):
            continue
        destination = os.path.abspath(os.path.join(folder, *relative.split("/")))
        if os.path.commonpath((folder, destination)) != folder:
            raise ValueError("Unsafe GitHub path: " + relative)
        prepared.append((destination, content))
    if not prepared or not any(
            os.path.basename(name) == "Github.py" for name, _ in prepared):
        raise RuntimeError("Repository archive has no NLTA runtime")
    updated = 0
    for destination, content in prepared:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if os.path.isfile(destination):
            with open(destination, "rb") as stream:
                if stream.read() == content:
                    continue
            backup = destination + ".nlta-local-backup"
            if not os.path.exists(backup):
                shutil.copy2(destination, backup)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                    mode="wb", dir=os.path.dirname(destination),
                    prefix=".nlta-", delete=False) as stream:
                stream.write(content)
                temp_name = stream.name
            os.replace(temp_name, destination)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.remove(temp_name)
        cache_folder = os.path.join(os.path.dirname(destination), "__pycache__")
        if destination.endswith(".py") and os.path.isdir(cache_folder):
            prefix = os.path.splitext(os.path.basename(destination))[0] + "."
            for name in os.listdir(cache_folder):
                if name.startswith(prefix) and name.endswith(".pyc"):
                    os.remove(os.path.join(cache_folder, name))
        updated += 1
    importlib.invalidate_caches()
    return updated


def _install_from_archive(folder):
    """Install from GitHub ZIP, falling back to git clone if ZIP is blocked."""
    errors = []
    for url in ZIP_URLS:
        try:
            payload = _request_bytes(url)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                files = []
                for member in archive.infolist():
                    if member.is_dir() or "/" not in member.filename:
                        continue
                    relative = member.filename.split("/", 1)[1]
                    if _runtime_file(relative):
                        files.append((relative, archive.read(member)))
            return _install_runtime_files(folder, files)
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
            errors.append("{}: {}".format(url, exc))
    if shutil.which("git"):
        try:
            with tempfile.TemporaryDirectory(prefix="nlta-git-") as temp:
                subprocess.run(
                    ["git", "clone", "--depth", "1", "--branch", "main",
                     REPOSITORY_URL, temp],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=90)
                files = []
                for root, dirs, names in os.walk(temp):
                    dirs[:] = [d for d in dirs if d != ".git"]
                    for name in names:
                        local = os.path.join(root, name)
                        relative = os.path.relpath(local, temp).replace("\\", "/")
                        if _runtime_file(relative):
                            with open(local, "rb") as stream:
                                files.append((relative, stream.read()))
                return _install_runtime_files(folder, files)
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
            errors.append("git clone: {}".format(exc))
    raise RuntimeError("Cannot download NLTA runtime:\n" + "\n".join(errors))


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
    """Install full NLTA runtime, with API/RAW/ZIP/git and offline fallback."""
    os.makedirs(folder, exist_ok=True)
    loader = os.path.join(folder, "Github.py")
    if os.environ.get("NLTA_SKIP_GITHUB_UPDATE", "").lower() in ("1", "true", "yes"):
        missing = [path for path in _required_files(folder)
                   if not os.path.isfile(path)]
        if missing:
            raise RuntimeError(
                "Offline installation requires existing runtime on D:\\NLTA:\n" +
                "\n".join(missing))
        print("[NLTA Install] Offline mode: using local runtime")
        return _load_local_github(folder)

    try:
        source = _download_loader()
        if _save_loader(loader, source):
            print("[NLTA Install] Github.py installed / updated")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print("[NLTA Install] Loader API/RAW unavailable: {}".format(exc))

    if not os.path.isfile(loader):
        print("[NLTA Install] Downloading full runtime archive")
        count = _install_from_archive(folder)
        print("[NLTA Install] Archive installed {} files".format(count))

    github = _load_local_github(folder)
    if not callable(getattr(github, "SyncWindowModules", None)):
        raise RuntimeError("Installed Github.py does not support module sync")

    result = github.SyncWindowModules(folder, requested=TOOLS)
    missing = [path for path in _required_files(folder)
               if not os.path.isfile(path)]
    if result.get("error") or missing:
        try:
            print("[NLTA Install] API sync unavailable; trying ZIP/git fallback")
            count = _install_from_archive(folder)
            github = _load_local_github(folder)
            print("[NLTA Install] Archive synced {} files".format(count))
        except (OSError, ValueError, RuntimeError) as exc:
            if missing:
                raise RuntimeError(
                    "Cannot complete NLTA installation at {}: {}\nMissing:\n{}"
                    .format(folder, exc, "\n".join(missing)))
            print("[NLTA Install] Offline fallback: {}".format(exc))

    missing = [path for path in _required_files(folder)
               if not os.path.isfile(path)]
    if missing:
        raise RuntimeError("NLTA files are missing:\n" + "\n".join(missing))
    print("[NLTA Install] Runtime ready: {}".format(folder))
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
