"""Offline tests for public one-file AutoInstall.py, without Maya."""
import ast
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock
from urllib.request import Request

AUTO = Path(__file__).resolve().parents[1] / "AutoInstall.py"
NAMES = ("_install_folder", "_git_sha", "_download_loader",
         "_save_loader", "_load_local_github", "_required_files",
         "_prepare_runtime", "_shelf_command", "_installed_shelf_buttons",
         "_create_shelf", "install")


class MayaShelf:
    def __init__(self):
        self.buttons = []

    def internalVar(self, **kwargs):
        return "/home/maya/scripts/"

    def tabLayout(self, *args, **kwargs):
        return "Shelf1"

    def shelfLayout(self, *args, **kwargs):
        return [b["name"] for b in self.buttons]

    def objectTypeUI(self, *args, **kwargs):
        return "shelfButton"

    def shelfButton(self, *args, **kwargs):
        if kwargs.get("query"):
            button = next(b for b in self.buttons if b["name"] == args[0])
            field = next(k for k in ("label", "annotation", "command")
                         if kwargs.get(k))
            return button[field]
        if kwargs.get("edit"):
            button = next(b for b in self.buttons if b["name"] == args[0])
            button.update({k: v for k, v in kwargs.items() if k != "edit"})
            return button["name"]
        button = dict(kwargs, name="button{}".format(len(self.buttons) + 1))
        self.buttons.append(button)
        return button["name"]

    def deleteUI(self, name):
        self.buttons = [b for b in self.buttons if b["name"] != name]


def load_installer(fake):
    module = ast.parse(AUTO.read_text(encoding="utf-8"), filename=str(AUTO))
    group = [n for n in module.body if isinstance(n, ast.FunctionDef)
             and n.name in NAMES]
    assert len(group) == len(NAMES)
    scope = {
        "cmds": fake,
        "TOOLS": ("Skinning", "Setup", "Scene", "Research", "Retarget"),
        "LOADER_URL": (
            "https://api.github.com/repos/nguyenletrian/"
            "ModuleGithubPublic/contents/Github.py?ref=main"),
        "os": os, "sys": sys, "base64": base64, "hashlib": hashlib,
        "importlib": importlib, "json": json, "shutil": shutil,
        "tempfile": tempfile, "Request": Request,
    }
    exec(compile(ast.Module(body=group, type_ignores=[]),
                 str(AUTO), "exec"), scope)
    return scope


class PublicInstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cmds = MayaShelf()
        self.scope = load_installer(self.cmds)

    def test_default_maya_scripts_path_is_not_hardcoded(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.scope["_install_folder"](),
                             os.path.abspath("/home/maya/scripts/NLTA"))
        self.assertEqual(self.scope["_install_folder"](str(self.root)),
                         str(self.root))

    def test_shelf_commands_compile_and_reinstall_is_idempotent(self):
        self.assertEqual(self.scope["_create_shelf"](str(self.root)), "Shelf1")
        self.assertEqual(len(self.cmds.buttons), 5)
        self.scope["_create_shelf"](str(self.root))
        self.assertEqual(len(self.cmds.buttons), 5)
        for button in self.cmds.buttons:
            script = button["command"]
            compile(script, "shelf_" + button["label"], "exec")
            self.assertIn("GH.CreateTool(", script)
            self.assertIn("'updateFromGitHub': True", script)
            self.assertIn("'module': '{}'".format(button["label"]), script)
            self.assertIn("toolFolder = " + repr(str(self.root)), script)

    def test_public_download_verifies_blob_sha(self):
        content = b"# downloadable public Github.py\n"
        digest = self.scope["_git_sha"](content)
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return None
        def urlopen(req, timeout=15):
            self.assertEqual(timeout, 15)
            self.assertIn("ModuleGithubPublic", req.full_url)
            response = FakeResponse()
            response.payload = {
                "sha": digest, "encoding": "base64",
                "content": base64.b64encode(content).decode()}
            return response
        self.scope["urlopen"] = urlopen
        self.scope["json"] = types.SimpleNamespace(
            load=lambda response: response.payload)
        self.assertEqual(self.scope["_download_loader"](), content)
        self.scope["json"] = types.SimpleNamespace(
            load=lambda response: dict(response.payload, sha="0" * 40))
        with self.assertRaisesRegex(ValueError, "SHA"):
            self.scope["_download_loader"]()

    def test_fresh_install_checks_runtime_before_creating_shelf(self):
        calls = []
        self.scope["_download_loader"] = lambda: b"# fake public loader"
        self.scope["_load_local_github"] = lambda folder: types.SimpleNamespace(
            SyncWindowModules=lambda folder, requested: {
                "updated": 0, "files": [], "error": "missing"})
        self.scope["_create_shelf"] = lambda folder: calls.append(folder)
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            self.scope["install"](str(self.root))
        self.assertEqual(calls, [])

    def test_installer_has_no_private_repo_or_license_dependency(self):
        text = AUTO.read_text(encoding="utf-8")
        self.assertIn("ModuleGithubPublic", text)
        self.assertNotIn("MayaScriptBefore", text)
        self.assertNotIn("NLTA_GITHUB_TOKEN", text)
        self.assertNotIn("LicenseClient", text)
        self.assertNotIn("LicenseServer", text)
        self.assertNotIn("_prompt_private_repo_token", text)


if __name__ == "__main__":
    unittest.main()
