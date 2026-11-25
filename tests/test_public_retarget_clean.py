"""Offline contracts for explicit namespace cleanup."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_Clean.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = dict(dependencies)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(STEP), "exec"), env)
    return env


class CleanTests(unittest.TestCase):
    def setUp(self):
        self.removed = []
        self.existing = {"RigNS", "AnimNS", "RefNS"}
        self.context = {"reference_namespaces": {
            "new_rig": "RigNS", "old_animations": "AnimNS", "reference_pose": "RefNS"}}
        def namespace(**kw):
            if "exists" in kw:
                return kw["exists"] in self.existing
        def drop(ns, protected_namespace):
            self.assertIsNone(protected_namespace)
            self.removed.append(ns)
            self.existing.remove(ns)
        self.env = scope(cmds=SimpleNamespace(namespace=namespace),
                         rt=SimpleNamespace(drop_namespace=drop))

    def test_defaults_do_not_delete(self):
        self.assertEqual(self.env["DefaultSetting"](),
                         {"rig": False, "anim": False, "ref": False})
        self.env["Run"]({}, self.context)
        self.assertEqual(self.removed, [])

    def test_selected_namespaces_only(self):
        result = self.env["Run"]({"anim": True, "ref": True}, self.context)
        self.assertEqual(result["removed"], ["AnimNS", "RefNS"])
        self.assertEqual(self.existing, {"RigNS"})
        self.assertEqual(self.env["Run"]({"anim": True}, self.context)["missing"], ["AnimNS"])

    def test_rig_can_be_removed_explicitly(self):
        self.env["Run"]({"rig": True}, self.context)
        self.assertEqual(self.removed, ["RigNS"])

    def test_missing_role_does_not_delete_anything(self):
        with self.assertRaisesRegex(ValueError, "invalid namespace"):
            self.env["Run"]({"rig": True, "ref": True},
                            {"target_namespace": "RigNS"})
        self.assertEqual(self.removed, [])


if __name__ == "__main__":
    unittest.main()
