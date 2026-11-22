"""Github.py - legacy NLTA loader, Python 3 error reporting update.

Keeps the public functions and CreateUI(data) contract used by MayaScriptNew.
This file does not automatically modify a GitHub repository.
"""

import os
import sys
import base64
import importlib
import json
import traceback
import hashlib
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib import error as urllib_error

import maya.cmds as cmds

setting = {
    'token': '',
    'headers': {},
    'owner': 'nguyenletrian',
    'repo': 'ModuleGithubPublic',
    'source_root': '',
    'branch': 'main',
}


def convertISO2Time(ISOString):
    dt = datetime.strptime(ISOString, '%Y-%m-%dT%H:%M:%SZ')
    return int((dt - datetime(1970, 1, 1)).total_seconds())


def GetToolFiles(toolFolder, recursive=True):
    result = {}
    for root, _, files in os.walk(toolFolder):
        for fileName in files:
            if fileName.endswith('.py'):
                full_path = os.path.join(root, fileName)
                relative_path = os.path.relpath(full_path, toolFolder)
                result[relative_path.replace('\\', '/')] = int(os.path.getmtime(full_path))
        if not recursive:
            break
    return result


def _github_credentials():
    """Public repository: no credentials are ever forwarded."""
    return "", ""


def make_request(url, timeout=20):
    req = urllib_request.Request(url)
    token, explicit_authorization = _github_credentials()
    for key, value in setting['headers'].items():
        if value:
            req.add_header(key, value)
    if token and not explicit_authorization:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            return response.getcode(), response.read()
    except urllib_error.HTTPError as exc:
        print('HTTP Error: {}-{}'.format(exc.code, exc.reason))
        return exc.code, exc.read()
    except urllib_error.URLError as exc:
        print('HTTP Error: {}'.format(exc.reason))
        return None, None



def _IsRepoFileSyncable(path):
    # Retain .py, .json, .mel, icons and other project files; reject only caches.
    parts = path.replace('\\', '/').split('/')
    return not (any(part in ('__pycache__', '.git') for part in parts)
                or path.lower().endswith(('.pyc', '.pyo')))


def CleanIncompatibleBytecode(toolFolder):
    """Remove only stale .pyc files that have a matching .py source."""
    removed, orphan = [], []
    for folder, _dirs, files in os.walk(os.path.abspath(toolFolder)):
        for filename in files:
            if not filename.lower().endswith('.pyc'):
                continue
            pyc = os.path.join(folder, filename)
            with open(pyc, 'rb') as stream:
                magic = stream.read(4)
            if magic == importlib.util.MAGIC_NUMBER:
                continue
            if os.path.basename(folder) == '__pycache__':
                source = os.path.join(os.path.dirname(folder), filename.split('.', 1)[0] + '.py')
            else:
                source = pyc[:-1]
            if os.path.isfile(source):
                os.remove(pyc)
                removed.append(pyc)
                print('[NLTA PYC] Removed outdated cache: {}'.format(pyc))
            else:
                orphan.append((pyc, source))
                print('[NLTA PYC] Missing source: {} | expected {}'.format(pyc, source))
    importlib.invalidate_caches()
    if removed or orphan:
        print('[NLTA PYC] removed={} orphan={}'.format(len(removed), len(orphan)))
    return {'removed': removed, 'orphan': orphan}


def GetRepoFiles():
    url = 'https://api.github.com/repos/{}/{}/git/trees/main?recursive=1'.format(
        setting['owner'], setting['repo'])
    status, data = make_request(url)
    if status == 200:
        tree_data = json.loads(data)
        if tree_data.get('truncated'):
            raise RuntimeError('GitHub tree result truncated; cannot safely sync.')
        # Never sync compiled Python caches from GitHub: these are version-specific.
        return [item['path'] for item in tree_data.get('tree', [])
                if item.get('type') == 'blob' and _IsRepoFileSyncable(item['path'])]
    print('Failed to fetch file list: {}'.format(status))
    return None


def GetFileCommits(linkArray):
    results = {}
    for link in linkArray:
        url = 'https://api.github.com/repos/{}/{}/commits?path={}'.format(
            setting['owner'], setting['repo'], urllib_parse.quote(link, safe='/'))
        status, data = make_request(url)
        if status == 200:
            commits = json.loads(data)
            if commits:
                commit_date = commits[0]['commit']['committer']['date']
                results[link] = convertISO2Time(commit_date)
        else:
            print('Failed to fetch commit info for {}: {}'.format(link, status))
    return results


def LoadGHFile(data):
    fileName = data['fileName']
    toolFolder = data['toolFolder']
    url = 'https://api.github.com/repos/{}/{}/contents/{}?ref=main'.format(
        setting['owner'], setting['repo'], urllib_parse.quote(fileName, safe='/'))
    status, data_bytes = make_request(url)
    if status != 200:
        print('Failed downloading {}: {}'.format(fileName, status))
        return False

    encoded = json.loads(data_bytes)['content']
    decoded = base64.b64decode(encoded)
    # Defensive containment: never permit an unexpected GitHub path to escape the tool folder.
    full_path = os.path.abspath(os.path.join(toolFolder, fileName))
    tool_root = os.path.abspath(toolFolder)
    if os.path.commonpath((tool_root, full_path)) != tool_root:
        raise ValueError('Repository path escapes toolFolder: {}'.format(fileName))

    folder = os.path.dirname(full_path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(full_path, 'wb') as stream:
        stream.write(decoded)
    print('{} downloaded and saved!'.format(fileName))
    return True


def _GitBlobSHA(contents):
    """Git's content-addressed blob SHA, independent of local file timestamps."""
    header = ("blob %d\0" % len(contents)).encode("ascii")
    return hashlib.sha1(header + contents).hexdigest()


def _RequestedGithubFiles(tree, requested):
    """Select window source code/dependencies; never fetch scene/user JSON."""
    modules = set(requested or ())
    if not modules:
        modules = {"Skinning", "Setup", "Scene", "Research", "Retarget"}
    root = (setting["source_root"].strip("/") + "/") if setting["source_root"].strip("/") else ""
    prefixes = [root + 'Libs/']
    names = {root + 'Github.py'}
    for module in modules:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', str(module)):
            continue
        names.add(root + 'UIs/' + module + '.py')
        prefixes.append(root + 'UIs/' + module + 'Tools/')
    if 'Scene' in modules:
        prefixes += [root + 'UIs/ScenePattern/',
                     root + 'UIs/SceneDefaultFunctions/',
                     root + 'UIs/SceneExtraFunction/']
    if 'Retarget' in modules:
        prefixes.append(root + 'UIs/RetargetSteps/')
        names.add(root + 'RetargetTool.py')
    if 'Research' in modules:
        names.add(root + 'UIs/ResearchUIHelper.py')
    allowed = ('.py', '.mel', '.ui', '.qss', '.png', '.svg', '.ico', '.jpg', '.jpeg')
    result = {}
    for item in tree:
        path = item.get('path', '')
        if (item.get('type') != 'blob'
                or not path.lower().endswith(allowed)
                or not (path in names or any(path.startswith(p) for p in prefixes))
                or any(segment in ('__pycache__', '.git') for segment in path.split('/'))):
            continue
        sha = item.get('sha', '')
        if re.fullmatch(r'[0-9a-f]{40}', sha):
            result[path] = sha
    return result


def _FetchGitBlob(item):
    path, sha = item
    # GitHub Raw avoids the REST API's low anonymous rate limit when Scene
    # requests many modules. SHA from the tree still verifies every byte.
    raw_url = 'https://raw.githubusercontent.com/{}/{}/{}/{}'.format(
        setting['owner'], setting['repo'], setting['branch'],
        urllib_parse.quote(path, safe='/'))
    status, contents = make_request(raw_url, timeout=8)
    if status == 200 and contents is not None:
        if _GitBlobSHA(contents) == sha:
            return path, contents

    # Raw can be briefly stale after commits.
    url = 'https://api.github.com/repos/{}/{}/git/blobs/{}'.format(
        setting['owner'], setting['repo'], sha)
    status, payload = make_request(url, timeout=8)
    if status != 200 or not payload:
        raise IOError('GitHub blob unavailable: {} ({})'.format(path, status))
    data = json.loads(payload)
    if data.get('encoding') != 'base64':
        raise IOError('GitHub blob encoding unsupported: ' + path)
    contents = base64.b64decode(data['content'])
    if _GitBlobSHA(contents) != sha:
        raise IOError('GitHub SHA mismatch: ' + path)
    return path, contents


def _RemoveBytecodeFor(source):
    if not source.lower().endswith('.py'):
        return
    folder = os.path.join(os.path.dirname(source), '__pycache__')
    stem = os.path.basename(source)[:-3] + '.'
    if os.path.isdir(folder):
        for filename in os.listdir(folder):
            if filename.startswith(stem) and filename.endswith('.pyc'):
                try:
                    os.remove(os.path.join(folder, filename))
                except OSError:
                    pass
    if os.path.isfile(source + 'c'):
        try:
            os.remove(source + 'c')
        except OSError:
            pass


def _AddNLTAPaths(toolFolder):
    """Make existing local UIs, Libs and nested module folders importable."""
    paths = [toolFolder]
    for folder in ('Libs', 'UIs'):
        base = os.path.join(toolFolder, folder)
        if os.path.isdir(base):
            for parent, dirs, _ in os.walk(base):
                dirs[:] = [name for name in dirs if name not in ('__pycache__', '.git')]
                paths.append(parent)
    # Prefer the newly synchronized local mirror over stale Maya script paths.
    for path in reversed(paths):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


def _DropForeignNLTAModules(toolFolder):
    """Drop cached NLTA modules from other installs before importing new UI.

    Updating sys.path alone is insufficient: Maya keeps imported modules in
    sys.modules, which caused EnsurePaintContext to resolve to an older
    NLTA_Skinning.py from a different tool folder.
    """
    local_root = os.path.normcase(os.path.realpath(toolFolder))
    available = set()
    for folder in ("Libs", "UIs"):
        base = os.path.join(toolFolder, folder)
        if not os.path.isdir(base):
            continue
        for parent, dirs, files in os.walk(base):
            dirs[:] = [name for name in dirs if name != "__pycache__"]
            available.update(filename[:-3] for filename in files
                             if filename.endswith(".py"))
    affected = []
    for name, module in list(sys.modules.items()):
        if not (name.startswith("NLTA_") or
                name in ("Skinning", "Setup", "Scene", "Research", "Retarget")):
            continue
        if name not in available:
            continue
        source = getattr(module, "__file__", "")
        if not source:
            continue
        origin = os.path.normcase(os.path.realpath(source))
        try:
            local = os.path.commonpath((local_root, origin)) == local_root
        except ValueError:
            local = False
        if not local:
            sys.modules.pop(name, None)
            affected.append(name)
    if affected:
        print("[NLTA GH] Discarded cached modules from another installation: {}".format(
            ", ".join(sorted(affected))))
    return affected


def SyncWindowModules(toolFolder, requested=None):
    """Fetch changed Maya window modules from the public GitHub repo.

    Public repo UIs -> local UIs, Libs -> local Libs.
    Only code/UI resources are synced; scene JSON, project data and other
    local assets are untouched. If GitHub fails, use current local files.
    """
    toolFolder = os.path.abspath(toolFolder)
    url = 'https://api.github.com/repos/{}/{}/git/trees/{}?recursive=1'.format(
        setting['owner'], setting['repo'], setting['branch'])
    try:
        status, raw = make_request(url, timeout=8)
        if status != 200 or not raw:
            raise IOError("Public GitHub tree status {}".format(status))
        tree = json.loads(raw)
        if tree.get('truncated'):
            raise IOError('GitHub tree truncated')
        files = _RequestedGithubFiles(tree.get('tree', []), requested)
        if not files:
            raise IOError('No matching window modules in GitHub repository')
        pending = []
        root = (setting["source_root"].strip("/") + "/") if setting["source_root"].strip("/") else ""
        for path, sha in sorted(files.items()):
            relative = path[len(root):]
            destination = os.path.abspath(os.path.join(
                toolFolder, *relative.split('/')))
            if os.path.commonpath((toolFolder, destination)) != toolFolder:
                raise ValueError('Unsafe GitHub path: ' + path)
            if os.path.isfile(destination):
                with open(destination, 'rb') as stream:
                    if _GitBlobSHA(stream.read()) == sha:
                        continue
            pending.append((path, sha))

        if not pending:
            print('[NLTA GH] {} up to date ({} files checked)'.format(
                setting['repo'], len(files)))
            return {'updated': 0, 'checked': len(files), 'files': []}

        # Download and verify the *whole* change set before touching local code.
        with ThreadPoolExecutor(max_workers=6) as pool:
            downloaded = dict(pool.map(_FetchGitBlob, pending))

        changed = []
        for path, _ in pending:
            destination = os.path.abspath(os.path.join(
                toolFolder, *path[len(root):].split('/')))
            folder = os.path.dirname(destination)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            if os.path.isfile(destination):
                backup = destination + '.nlta-local-backup'
                if not os.path.exists(backup):
                    shutil.copy2(destination, backup)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                        mode='wb', dir=folder, prefix='.nlta-', delete=False) as temp:
                    temp_path = temp.name
                    temp.write(downloaded[path])
                os.replace(temp_path, destination)
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
            _RemoveBytecodeFor(destination)
            changed.append(path)
        importlib.invalidate_caches()
        print('[NLTA GH] Updated {} window files from {}/{}: {}'.format(
            len(changed), setting['owner'], setting['repo'], ', '.join(changed)))
        return {'updated': len(changed), 'checked': len(files), 'files': changed}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('[NLTA GH] Update unavailable; opening local tools: {}'.format(exc))
        return {'updated': 0, 'error': str(exc)}


def SyschronizeGH(data):
    """Update requested windows before loading; fall back to local offline."""
    toolFolder = os.path.abspath(data['toolFolder'])
    requested = [item.get('module') for item in
                 data.get('UI', {}).get('layouts', [])]
    outcome = {'updated': 0, 'files': []}
    if (data.get('UI', {}).get('updateFromGitHub', True)
            and os.environ.get('NLTA_SKIP_GITHUB_UPDATE', '').lower()
            not in ('1', 'true', 'yes')):
        outcome = SyncWindowModules(toolFolder, requested)
    _AddNLTAPaths(toolFolder)
    _DropForeignNLTAModules(toolFolder)
    importlib.invalidate_caches()
    return outcome


def DictToFlags(values):
    return [
        '{}="{}"'.format(key, value) if isinstance(value, str)
        else '{}={}'.format(key, value)
        for key, value in values.items()
    ]


def _ShowOriginalError(module_name, phase, exc):
    """Print full chained traceback AND innermost original exception location."""
    original = exc
    seen = set()
    while id(original) not in seen:
        seen.add(id(original))
        previous = original.__cause__ or original.__context__
        if previous is None:
            break
        original = previous

    frames = traceback.extract_tb(original.__traceback__)
    origin = frames[-1] if frames else None
    print('\n' + '=' * 68)
    print('[NLTA LOADER ERROR] Module: {} | Phase: {}'.format(module_name, phase))
    print('[ROOT CAUSE] {}: {}'.format(type(original).__name__, original))
    if origin:
        print('[ROOT LOCATION] {} : line {} : {}'.format(
            origin.filename, origin.lineno, origin.name))
        if origin.line:
            print('[SOURCE] {}'.format(origin.line.strip()))
    print('--- FULL TRACEBACK (including chained exceptions) ---')
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stdout)
    print('=' * 68 + '\n')


def LoadUI(data):
    """Load/reload one UI module; preserve the underlying exception on failure."""
    module_name = data['module']
    phase = 'import'
    try:
        # Rebuild Skinning's cached Qt callbacks when its Python dependencies
        # have changed; merely reopening the same widget would use old code.
        updated = data.get('syncedFiles') or []
        if module_name == 'Skinning' and any(
                path.startswith('UIs/Skinning')
                or path.startswith('Libs/')
                for path in updated):
            qt_board = sys.modules.get('NLTA_Skinning_CommandBoard')
            if qt_board is not None:
                importlib.reload(qt_board)
        already_loaded = module_name in sys.modules
        module = importlib.import_module(module_name)
        if already_loaded:
            phase = 'reload'
            module = importlib.reload(module)
        direct = data.get('openWindow', False)
        phase = 'OpenWindow' if direct else 'CreateUI'
        entry = 'OpenWindow' if direct else 'CreateUI'
        creator = getattr(module, entry)
        if not callable(creator):
            raise TypeError('{}.{} is not callable'.format(module_name, entry))
        return creator() if direct else creator(data)
    except Exception as exc:
        _ShowOriginalError(module_name, phase, exc)
        raise   # CRITICAL: never fall back to bare reload(module).


def _CloseObsoleteSkinningLauncher(ui):
    """Close only the old NLTA Tools window with a single Skinning launcher."""
    name = ui.get('windowName', 'NLTA_Form')
    if not cmds.window(name, exists=True):
        return
    # Never close a shared Setup/Scene/Retarget window.
    try:
        controls = cmds.lsUI(type='button', long=True) or []
        buttons = [item for item in controls if item.startswith(name + '|')]
        if (len(buttons) == 1
                and cmds.button(buttons[0], query=True, label=True)
                == 'Open Skinning Command Board'):
            cmds.deleteUI(name, window=True)
    except RuntimeError:
        # Inspecting the obsolete Maya UI must never block opening Skinning.
        pass


def CreateTool(data):
    for path in data.get('paths', []):
        normalized = os.path.abspath(path)
        if normalized not in sys.path:
            sys.path.append(normalized)

    sync_info = SyschronizeGH(data) or {}
    # Fix caches from older Maya/Python installs BEFORE importing any NLTA modules.
    CleanIncompatibleBytecode(data['toolFolder'])
    ui = data['UI']
    layouts = ui.get('layouts', [])
    # A Skinning-only shelf action opens its floating PySide board directly,
    # even when an old installed shelf button still has standalone=False.
    # Never create NLTA_Form for Skinning-only launches.
    if len(layouts) == 1 and layouts[0].get('module') == 'Skinning':
        _CloseObsoleteSkinningLauncher(ui)
        return LoadUI(dict(layouts[0], openWindow=True,
                           syncedFiles=sync_info.get('files', [])))
    # Other standalone tools retain their existing CreateUI contract.
    if ui.get('standalone', False):
        return [LoadUI(dict(layout_data, syncedFiles=sync_info.get('files', [])))
                for layout_data in layouts]
    window_name = ui['windowName']
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)

    cmds.window(window_name, title=ui['windowTitle'])
    cmds.rowColumnLayout('MainLayout', nc=ui['column'])
    cmds.setParent('..')
    cmds.showWindow(window_name)
    for layout_data in layouts:
        LoadUI(dict(layout_data, syncedFiles=sync_info.get('files', [])))
