# NLTA Tools — Maya Public Test Distribution

**Public test build** of Skinning, Setup, Scene, Research and Retarget
modules. The source of truth for development remains the **private**
\`MayaScriptBefore/ModuleGithub\` workspace; this repository is used to test
portable Maya installations before licensing is enabled.

Anyone can view or download the Python code in this public repository.
There is **no password, GitHub personal access token or License Server** in
this build.

## Install on another computer (Maya 2024, Python 3)

1. Download **[AutoInstall.py](AutoInstall.py)** from this repository using
   the GitHub **Raw** button and save it locally.
2. Open **Maya → Script Editor → Python**, select your target Shelf and run:

\`\`\`python
path = r"C:\Downloads\AutoInstall.py"
with open(path, "r", encoding="utf-8") as file:
    exec(compile(file.read(), path, "exec"))
\`\`\`

3. AutoInstall creates \`<maya user scripts>/NLTA/\`, downloads **Github.py**
   and the required tool source files from this public repository, then adds
   five Shelf buttons: **Skinning, Setup, Scene, Research, Retarget**.
4. Click a Shelf button. Its loader checks GitHub blob SHAs and refreshes
   changed modules before launching the UI. Reinstalling updates matching NLTA
   Shelf buttons instead of duplicating them.

The installer stores **no GitHub password or token**. Existing local code is
backed up to \`*.nlta-local-backup\` before it is replaced. Scene files,
user-defined JSON, skin weights and settings are not downloaded/overwritten
by the module updater.

### Optional custom folder

By default the files go to \`cmds.internalVar(userScriptDir=True) + "NLTA"\`.
To use an isolated public test installation, in Maya Python before running
AutoInstall:

\`\`\`python
import os
os.environ["NLTA_TOOL_FOLDER"] = os.path.join(
    __import__("maya.cmds", fromlist=["cmds"]).internalVar(userScriptDir=True),
    "NLTA_Public")
\`\`\`

This prevents the public test installation from sharing its directory with
any older private or licensed build. To disable network checks for an existing
complete installation only, set \`NLTA_SKIP_GITHUB_UPDATE=1\` before opening
Maya.

## Runtime layout

\`\`\`text
AutoInstall.py       single-file Maya installer
Github.py            Maya Shelf loader + public SHA updater
RetargetTool.py      compatibility launcher
Libs/                common Maya modules
UIs/                 Skinning, Setup, Scene, Research, Retarget and submodules
tests/               offline tests + a Maya smoke-check helper
\`\`\`

Files that do **not** belong here: LicenseServer, LicenseClient, GitHub tokens,
private .env files, vendor packages, user JSON, project scene files or compiled
Python caches. The License Server is intentionally postponed.

## Validation

GitHub Actions compiles shipped Python files with Python 3.10 and runs
the offline updater/installer tests. This checks Python syntax, manifest
selection, Git blob SHA integrity, backups, path isolation and Shelf command
generation — **it does not emulate Maya**.

For a live Maya 2024 smoke check after installation, in Maya Python:

\`\`\`python
path = r"C:\Downloads\maya_smoke.py"
with open(path, "r", encoding="utf-8") as file:
    exec(compile(file.read(), path, "exec"))
\`\`\`

Download [tests/maya_smoke.py](tests/maya_smoke.py) first, and update the
local path. The check only inspects the installation and imports the Skinning
backend; it does not modify the scene. Then open each Shelf tool and test
actions in a disposable Maya scene. Report the Script Editor traceback
and module path for failures.

**Status:** this is a testing release, not a verified Maya production build.
