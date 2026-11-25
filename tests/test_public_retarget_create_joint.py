"""Offline Create Joint module contracts."""
import ast
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
    def test_live_matrix_parent_and_default_name(self):
        source = "|REF:Root|REF:Hand"
        parent = "|Rig:Root|Rig:Wrist"
        matrix = [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 3, 5, 7, 1]
        calls = []

        def xform(node, **kw):
            calls.append(("xform", node, kw))
            if kw.get("query"):
                return list(matrix)

        def create(kind, **kw):
            calls.append(("create", kind, kw))
            return parent + "|" + kw["name"].lstrip(":")

        env = scope("JointData", "Run",
                    _namespace=lambda role, context: role,
                    rt=SimpleNamespace(
                        resolve=lambda ns, name: {"REF": source, "Rig": parent}[ns],
                        leaf=lambda name: name.split("|")[-1].split(":")[-1]),
                    cmds=SimpleNamespace(xform=xform, createNode=create,
                                         ls=lambda node, **kw: [node],
                                         setAttr=lambda *args: calls.append(("set", *args))))
        run = env["Run"]
        result = run({"joint": {"object": "Hand", "parent": "Wrist"}}, {})
        self.assertEqual(result["joint"], parent + "|Rig:Wrist_extraJoint")
        self.assertEqual(calls[0], ("xform", source, {"query": True,
                                                   "worldSpace": True, "matrix": True}))
        self.assertEqual(calls[1], ("create", "joint", {
            "name": ":Rig:Wrist_extraJoint", "parent": parent, "skipSelect": True}))
        self.assertEqual(calls[2], ("set", result["joint"] + ".segmentScaleCompensate", False))
        self.assertEqual(calls[3], ("xform", result["joint"],
                                    {"worldSpace": True, "matrix": matrix}))
        matrix[12] = 20
        result = run({"joint": {"object": "Hand", "parent": "Wrist", "name": "Custom"}}, {})
        self.assertEqual(result["joint"], parent + "|Rig:Custom")
        self.assertEqual(calls[-1][2]["matrix"][12], 20)

    def test_registered_optional_module(self):
        env = scope("JointData", "DefaultSetting", "Fields")
        self.assertEqual(env["DefaultSetting"]()["joint"]["name"], "")
        self.assertEqual(env["Fields"](), [("Joint", "joint", "create_joint")])
        ui = (ROOT / "UIs/Retarget.py").read_text(encoding="utf-8")
        self.assertIn('("CreateJoint", "Retarget_CreateJoint.py")', ui)
        self.assertIn('"MatchRotate", "CreateJoint"):', ui)


if __name__ == "__main__":
    unittest.main()
