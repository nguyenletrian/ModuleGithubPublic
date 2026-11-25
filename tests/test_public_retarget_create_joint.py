"""Offline Create Joint module contracts."""
import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_CreateJoint.py"


def scope(*names, **dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    env = dict(dependencies)
    module = ast.Module(body=[functions[name] for name in names],
                        type_ignores=[])
    exec(compile(module, str(STEP), "exec"), env)
    return env


class CreateJointTests(unittest.TestCase):
    def test_captured_matrix_parent_and_default_name(self):
        parent = "|Rig:Root|Rig:Wrist"
        matrix = [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 3, 5, 7, 1]
        calls = []

        def xform(node, **kw):
            self.assertFalse(kw.get("query"), "Run must not query the original object")
            calls.append(("xform", node, kw))

        def create(kind, **kw):
            calls.append(("create", kind, kw))
            return parent + "|" + kw["name"].lstrip(":")

        def resolve(ns, name):
            self.assertEqual((ns, name), ("Rig", "Wrist"))
            return parent

        env = scope("JointData", "Run", math=math,
                    _namespace=lambda role, context: role,
                    rt=SimpleNamespace(
                        resolve=resolve,
                        leaf=lambda name: name.split("|")[-1].split(":")[-1]),
                    cmds=SimpleNamespace(xform=xform, createNode=create,
                                         ls=lambda node, **kw: [node],
                                         setAttr=lambda *args: calls.append(("set", *args))))
        run = env["Run"]
        result = run({"joint": {"matrix": matrix, "parent": "Wrist"}}, {})
        self.assertEqual(result["joint"], parent + "|Rig:Wrist_extraJoint")
        self.assertEqual(calls[0], ("create", "joint", {
            "name": ":Rig:Wrist_extraJoint", "parent": parent, "skipSelect": True}))
        self.assertEqual(calls[1], ("set", result["joint"] + ".segmentScaleCompensate", False))
        self.assertEqual(calls[2], ("xform", result["joint"],
                                    {"worldSpace": True, "matrix": matrix}))
        result = run({"joint": {"matrix": matrix, "parent": "Wrist", "name": "Custom"}}, {})
        self.assertEqual(result["joint"], parent + "|Rig:Custom")
        self.assertEqual(calls[-1][2]["matrix"], matrix)

    def test_missing_matrix_requires_pick_before_creating(self):
        env = scope("JointData", "Run", math=math)
        with self.assertRaisesRegex(ValueError, "Pick Matrix first"):
            env["Run"]({"joint": {"object": "OldObject", "parent": "Wrist"}}, {})

    def test_registered_optional_module(self):
        env = scope("JointData", "DefaultSetting", "Fields")
        self.assertEqual(env["DefaultSetting"]()["joint"]["name"], "")
        self.assertEqual(env["DefaultSetting"]()["joint"]["matrix"], [])
        self.assertNotIn("object", env["DefaultSetting"]()["joint"])
        self.assertEqual(env["Fields"](), [("Joint", "joint", "create_joint")])
        ui = (ROOT / "UIs/Retarget.py").read_text(encoding="utf-8")
        self.assertIn('("CreateJoint", "Retarget_CreateJoint.py")', ui)
        self.assertIn('"MatchRotate", "CreateJoint"):', ui)


if __name__ == "__main__":
    unittest.main()
