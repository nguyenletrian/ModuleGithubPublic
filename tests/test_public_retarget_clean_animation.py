"""Offline contracts for exact consecutive key cleanup."""
import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_CleanAnimation.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = dict(re=re, _TIME_CURVES=("animCurveTA", "animCurveTL", "animCurveTT",
                                   "animCurveTU"), **dependencies)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(STEP), "exec"), env)
    return env


class CleanAnimationTests(unittest.TestCase):
    def test_duplicate_values(self):
        env = scope()
        self.assertEqual(env["_removal_indices"]([0, 0, 0, 10, 10, 20, 0, 0]),
                         ([1, 2, 4, 7], False))
        self.assertEqual(env["_removal_indices"]([0, 0, 0]), ([0, 1, 2], True))
        self.assertEqual(env["_removal_indices"]([1, 1, 1]), ([1, 2], False))
        self.assertEqual(env["_removal_indices"]([0, 1e-9]), ([], False))
        self.assertEqual(env["_removal_indices"]([0]), ([0], True))
        self.assertEqual(env["_removal_indices"]([]), ([], False))

    def test_delete_ranges_descending(self):
        self.assertEqual(list(scope()["_ranges"]([1, 2, 4, 7, 8])), [(7, 8), (4, 4), (1, 2)])

    def test_only_controls_and_time_curves(self):
        cuts, writes = [], []
        nodes = ["|Rig:FK", "|Rig:Joint", "|Rig:Group", "|Other:FK"]
        attrs = {"rotateX": "moving", "rotateY": "zero", "scaleX": "one",
                 "rotateZ": "sdk", "translateX": "layered", "translateY": "shared"}
        values = {"moving": [0, 0, 5, 5], "zero": [0, 0, 0], "one": [1, 1]}
        def keyframe(name, **kw):
            if kw.get("name"):
                attr = name.rsplit(".", 1)[-1]
                return ["layer1", "layer2"] if attr == "translateX" else [attrs[attr]]
            return values[name]
        def node_type(node):
            if node.endswith(":Joint"):
                return "joint"
            if node.startswith("|"):
                return "transform"
            return "animCurveUU" if node == "sdk" else "animCurveTA"
        env = scope(rt=SimpleNamespace(mapping_candidates=lambda ns: nodes,
                        leaf=lambda node: node.rsplit(":", 1)[-1]),
                    cmds=SimpleNamespace(nodeType=node_type,
                        listRelatives=lambda node, **kw: ["shape"] if node.endswith(":FK") else [],
                        listAttr=lambda node, **kw: list(attrs),
                        keyframe=keyframe,
                        listConnections=lambda plug, **kw: ["a", "b"] if plug.startswith("shared") else ["a"],
                        cutKey=lambda curve, **kw: cuts.append((curve, kw["index"])),
                        getAttr=lambda *args, **kw: True,
                        setAttr=lambda *args: writes.append(args)))
        result = env["Run"]({}, {"target_namespace": "Rig"})
        self.assertEqual(result["controls"], 1)
        self.assertEqual(result["removed_keys"], 6)
        self.assertEqual(result["zero_channels"], 1)
        self.assertEqual(result["skipped_channels"], 3)
        self.assertEqual(cuts, [("moving", (3, 3)), ("moving", (1, 1)),
                                ("zero", (0, 2)), ("one", (1, 1))])
        self.assertEqual(writes, [("|Rig:FK.rotateY", 0)])


if __name__ == "__main__":
    unittest.main()
