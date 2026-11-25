"""Offline contracts for Match Rotate Vector mirror expansion."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_MatchRotatePair.py"


def scope(*names, **dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    env = dict(dependencies)
    module = ast.Module(body=[functions[name] for name in names],
                        type_ignores=[])
    exec(compile(module, str(STEP), "exec"), env)
    return env


class MatchRotateVectorTests(unittest.TestCase):
    def test_mirror_names(self):
        mirror = scope("_mirror_name", re=re)["_mirror_name"]
        for name, expected in (
                ("R_Shoulder_FK", "L_Shoulder_FK"),
                ("L_Elbow_FK", "R_Elbow_FK"),
                ("arm.R", "arm.L"),
                ("mixamorig:RightArm", "mixamorig:LeftArm"),
                ("Bip001FBXASC032RFBXASC032UpperArm",
                 "Bip001FBXASC032LFBXASC032UpperArm"),
                ("Chest_FK", "Chest_FK")):
            # The production helper receives namespace-free leaf names.
            if ":" in name:
                name, expected = name.split(":")[-1], expected.split(":")[-1]
            self.assertEqual(mirror(name), expected)
            self.assertEqual(mirror(expected), name)

    def test_default_mirror_and_legacy_data(self):
        env = scope("PairData", "DefaultSetting")
        pair = env["PairData"]({"source": "R_arm", "target": "R_fk"})
        self.assertEqual(pair["from"], "R_arm")
        self.assertEqual(pair["to"], "R_fk")
        self.assertTrue(pair["mirror"])
        self.assertFalse(env["PairData"]({"mirror": False})["mirror"])
        self.assertTrue(env["DefaultSetting"]()["pairs"][0]["mirror"])

    def test_expand_opposite_pair(self):
        from types import SimpleNamespace
        keys = ("from", "from_child", "to", "to_child")
        env = scope("PairData", "_mirror_name", "_mirror_pair",
                    re=re, _KEYS=keys,
                    rt=SimpleNamespace(leaf=lambda node: node),
                    _resolve_pair=lambda pair, context: {
                        key: pair[key] for key in keys})
        nodes = dict(zip(keys, ("R_arm", "R_elbow", "R_fk", "R_elbow_fk")))
        self.assertEqual(env["_mirror_pair"]({}, nodes, {}), {
            key: name.replace("R_", "L_") for key, name in nodes.items()})
        nodes["to"] = "Chest"
        self.assertIsNone(env["_mirror_pair"]({}, nodes, {}))


if __name__ == "__main__":
    unittest.main()
