# -*- coding: utf-8 -*-
"""Run in Maya's Python Script Editor after the Public AutoInstall.

Safe checks only: do not create/delete scene nodes or call rigging actions.
"""
import importlib
import os
import sys

import maya.cmds as cmds

folder = os.path.abspath(os.environ.get("NLTA_TOOL_FOLDER") or
    os.path.join(cmds.internalVar(userScriptDir=True), "NLTA"))
required = ["Github.py", "UIs/Skinning.py", "UIs/Setup.py",
            "UIs/Scene.py", "UIs/Research.py", "UIs/Retarget.py",
            "Libs/NLTA_General.py", "Libs/NLTA_Skinning.py",
            "UIs/SkinningTools/NLTA_Skinning_CommandBoard.py"]
missing = [name for name in required if not os.path.isfile(
    os.path.join(folder, *name.split("/")))]
if missing:
    raise RuntimeError("NLTA installation incomplete: " + ", ".join(missing))
if folder not in sys.path:
    sys.path.insert(0, folder)
import Github
Github._AddNLTAPaths(folder)
Github._DropForeignNLTAModules(folder)
import NLTA_Skinning
backend = os.path.normcase(os.path.realpath(NLTA_Skinning.__file__))
root = os.path.normcase(os.path.realpath(folder))
if os.path.commonpath((root, backend)) != root:
    raise RuntimeError("Skinning imported from another installation: " + backend)
if not callable(getattr(NLTA_Skinning, "EnsurePaintContext", None)):
    raise RuntimeError("Skinning backend lacks EnsurePaintContext: " + backend)
print("[NLTA SMOKE] PASS: 5 UI entrypoints and Skinning backend found")
print("[NLTA SMOKE] Folder:", folder)
print("[NLTA SMOKE] Backend:", backend)
print("[NLTA SMOKE] Next: manually open five Shelf windows in a test scene")
