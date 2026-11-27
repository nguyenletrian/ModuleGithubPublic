"""Offline tests for segment-scale mocap Connect."""
import ast
import math
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

STEP = Path(__file__).resolve().parents[1] / "UIs/RetargetSteps/Retarget_Connect.py"


def scope(**deps):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    env = dict(math=math, re=re, **deps)
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)],
                            type_ignores=[]), str(STEP), "exec"), env)
    return env


class ConnectTests(unittest.TestCase):
    def test_segment_ratio(self):
        env = scope()
        self.assertEqual(env["distance"]((0, 0, 0), (0, 3, 4)), 5)
        self.assertEqual(env["segmentRatio"](5, 10), 2)
        self.assertEqual(env["segmentRatio"](0, 10), 1)

    def test_pair_defaults_and_mirror(self):
        env = scope(rt=SimpleNamespace(leaf=lambda name: name.split(":")[-1]))
        data = env["DefaultSetting"]()
        self.assertEqual((data["from_role"], data["to_role"]), ("Anim", "REF"))
        rows = env["expandPairs"]([{"from": "R_Arm", "to": "R_ArmFK", "mirror": True}])
        self.assertEqual([(p["from"], p["to"]) for p in rows],
                         [("R_Arm", "R_ArmFK"), ("L_Arm", "L_ArmFK")])
        self.assertTrue(all(p["translate"] and p["rotate"] for p in rows))

    def test_matrix_segment_connections(self):
        links, attrs = {}, {}
        def connect(source, dest):
            links[dest] = source
        def set_attr(plug, *values, **kw):
            attrs[plug] = values
        env = scope(cmds=SimpleNamespace(
            createNode=lambda kind, name: name, connectAttr=connect, setAttr=set_attr))
        nodes = env["translateConnectWithScale"]("A", "B", "C", "Loc", 2, "Test")
        self.assertEqual(len(nodes), 6)
        self.assertEqual(links["Test_SourceParent_DM.inputMatrix"], "A.worldMatrix[0]")
        self.assertEqual(links["Test_Source_DM.inputMatrix"], "B.worldMatrix[0]")
        self.assertEqual(links["Test_TargetParent_DM.inputMatrix"], "C.worldMatrix[0]")
        self.assertEqual(attrs["Test_Direction.operation"], (2,))
        self.assertEqual(attrs["Test_ScaleSegment.input2"], (2, 2, 2))
        self.assertEqual(links["Loc.translate"], "Test_Position.output3D")


if __name__ == "__main__":
    unittest.main()
