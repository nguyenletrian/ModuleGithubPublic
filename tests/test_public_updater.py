"""Offline regression tests for public NLTA updater (no Maya install required)."""
import ast
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib import parse as urllib_parse

ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "Github.py"
FUNCS = ("_GitBlobSHA", "_RequestedGithubFiles", "_FetchGitBlob",
         "_RemoveBytecodeFor", "_AddNLTAPaths", "_DropForeignNLTAModules",
         "SyncWindowModules", "SyschronizeGH")


def isolated_functions(scope):
    tree = ast.parse(LOADER.read_text(encoding="utf-8"))
    group = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in FUNCS]
    assert len(group) == len(FUNCS)
    exec(compile(ast.Module(body=group, type_ignores=[]),
                 str(LOADER), "exec"), scope)
    return scope


class PublicUpdaterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.remote = {}
        self.urls = []
        self.offline = False
        self.setting = {"owner": "nguyenletrian",
                        "repo": "ModuleGithubPublic",
                        "branch": "main", "source_root": ""}

        def request(url, timeout=8):
            self.urls.append(url)
            if self.offline:
                return None, None
            if "/git/trees/" in url:
                return 200, json.dumps({"tree": [{
                    "path": path, "sha": self.sha(blob), "type": "blob"
                } for path, blob in self.remote.items()]}).encode()
            if url.startswith("https://raw.githubusercontent.com/"):
                path = url.split("/main/", 1)[-1]
                if path in self.remote:
                    return 200, self.remote[path]
                return 404, b""
            if "/git/blobs/" in url:
                digest = url.rsplit("/", 1)[-1]
                blob = next((data for data in self.remote.values()
                             if self.sha(data) == digest), None)
                if blob is not None:
                    return 200, json.dumps({
                        "encoding": "base64",
                        "content": base64.b64encode(blob).decode()}).encode()
            return 404, b""

        self.scope = isolated_functions({
            "os": os, "sys": sys, "re": re,
            "base64": base64, "hashlib": hashlib, "json": json,
            "importlib": importlib, "shutil": shutil, "tempfile": tempfile,
            "urllib_parse": urllib_parse,
            "ThreadPoolExecutor": ThreadPoolExecutor,
            "setting": self.setting, "make_request": request})

    @staticmethod
    def sha(data):
        return hashlib.sha1(
            ("blob %d\0" % len(data)).encode("ascii") + data).hexdigest()

    def test_selection_is_repo_root_not_private_development_path(self):
        self.remote = {
            "Github.py": b"# loader",
            "UIs/Skinning.py": b"# skinning",
            "UIs/SkinningTools/NLTA_Skinning_CommandBoard.py": b"# board",
            "Libs/NLTA_Skinning.py": b"# library",
            "UIs/Scene.py": b"# scene",
            "UIs/ScenePattern/Scene_Pattern_Test.py": b"# scene tool",
            "UIs/ScenePattern/local_scene.json": b"{}",
            "LicenseServer/server.py": b"# secret",
        }
        selected = self.scope["_RequestedGithubFiles"]([
            {"path": path, "sha": self.sha(blob), "type": "blob"}
            for path, blob in self.remote.items()], ["Skinning"])
        self.assertEqual(set(selected), {
            "Github.py", "UIs/Skinning.py",
            "UIs/SkinningTools/NLTA_Skinning_CommandBoard.py",
            "Libs/NLTA_Skinning.py"})

    def test_sha_verified_sync_and_one_time_backup(self):
        local = self.root / "UIs/Skinning.py"
        local.parent.mkdir(parents=True)
        local.write_bytes(b"previous local version")
        self.remote = {"Github.py": b"# loader",
                       "UIs/Skinning.py": b"# updated Skinning",
                       "Libs/NLTA_Skinning.py": b"# library"}
        result = self.scope["SyncWindowModules"](str(self.root), ["Skinning"])
        self.assertEqual(result["updated"], 3)
        self.assertEqual(local.read_bytes(), b"# updated Skinning")
        self.assertEqual(Path(str(local) + ".nlta-local-backup").read_bytes(),
                         b"previous local version")
        self.assertEqual(self.scope["SyncWindowModules"](
            str(self.root), ["Skinning"])["updated"], 0)

    def test_sync_is_safe_when_offline(self):
        local = self.root / "UIs/Setup.py"
        local.parent.mkdir(parents=True)
        local.write_bytes(b"kept")
        self.offline = True
        result = self.scope["SyncWindowModules"](str(self.root), ["Setup"])
        self.assertIn("error", result)
        self.assertEqual(local.read_bytes(), b"kept")

    def test_discard_old_cached_maya_library(self):
        libs = self.root / "Libs"
        libs.mkdir()
        local = libs / "NLTA_Skinning.py"
        local.write_bytes(b"# backend")
        fake = types.SimpleNamespace(
            modules={"NLTA_Skinning": types.SimpleNamespace(
                __file__="D:/old/MayaScripts/Libs/NLTA_Skinning.py"),
                     "maya.cmds": object()},
            path=[])
        self.scope["sys"] = fake
        removed = self.scope["_DropForeignNLTAModules"](str(self.root))
        self.assertEqual(removed, ["NLTA_Skinning"])
        self.assertNotIn("NLTA_Skinning", fake.modules)

    def test_public_loader_requires_no_pat(self):
        code = LOADER.read_text(encoding="utf-8")
        self.assertIn("'repo': 'ModuleGithubPublic'", code)
        self.assertIn("'source_root': ''", code)
        self.assertNotIn("MayaScriptBefore", code)
        self.assertNotIn("NLTA_GITHUB_TOKEN", code)
        self.assertNotIn("LicenseServer", code)
        self.assertNotIn("_PromptPrivateRepoToken", code)


if __name__ == "__main__":
    unittest.main()
