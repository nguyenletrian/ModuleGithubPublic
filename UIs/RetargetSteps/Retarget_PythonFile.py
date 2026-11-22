"""Execute a user-selected local .py file at its pipeline position.

This is trusted user code with full Maya/Python permissions, not a sandbox.
"""
import os
import runpy
import sys

import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Run Python File"


def DefaultSetting():
    return {"python_file": ""}


def Fields():
    return [("Python File (.py)", "python_file", "python_file")]


def Run(settings, context):
    filename = str(settings.get("python_file") or "").strip()
    if not filename:
        raise ValueError("Select a .py file for the Run Python File module.")
    filename = os.path.abspath(os.path.expanduser(filename))
    if not filename.lower().endswith(".py") or not os.path.isfile(filename):
        raise ValueError("Python File must be an existing .py file: " +
                         filename)

    # Context is shared by reference, so the script can pass data to later
    # Retarget modules using context["key"] = value.
    globals_for_script = {
        "context": context, "cmds": cmds, "rt": rt,
        "source_namespace": context.get("source_namespace_animation")
                            or context.get("source_namespace"),
        "target_namespace": context.get("target_namespace"),
        "reference_pose_namespace": context.get("reference_pose_namespace"),
        "reference_namespaces": context.get("reference_namespaces", {}),
        "reference_files": context.get("reference_files", {}),
        "source_root": context.get("source_root"),
        "target_root": context.get("target_root"),
        "pairs": context.get("pairs", []),
        "animation_path": context.get("animation_path", ""),
        "start_frame": context.get("start_frame"),
        "end_frame": context.get("end_frame"),
        "alignment": context.get("alignment", {}),
        "output_folder": context.get("output_folder", ""),
    }

    # Allow ordinary imports from sibling files beside the selected script.
    folder = os.path.dirname(filename)
    sys.path.insert(0, folder)
    try:
        runpy.run_path(filename, init_globals=globals_for_script,
                       run_name="__main__")
    finally:
        sys.path.remove(folder)
    return {"executed": filename}
