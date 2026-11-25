"""Offline contracts for Match Rotate Vector mirror expansion."""
import ast
import math
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


class VectorCorrectionTests(unittest.TestCase):
    def test_iterative_correction_stops_at_alignment(self):
        from types import SimpleNamespace
        rotation = [0.0, 0.0, 0.0]
        calls = []

        def match(nodes):
            calls.append(nodes["to"])
            rotation[0] += (10.0 - rotation[0]) * 0.9

        env = scope("_fit_pair", _ALIGNMENT=1.0 - 1e-6,
                    _MAX_CORRECTIONS=4, _match_pair=match,
                    _similarity=lambda nodes: math.cos(math.radians(10.0 - rotation[0])),
                    cmds=SimpleNamespace(getAttr=lambda plug: [tuple(rotation)]),
                    _set_rotation=lambda node, values: rotation.__setitem__(slice(None), values))
        self.assertTrue(env["_fit_pair"]({"to": "Thumb1"}))
        self.assertEqual(len(calls), 3)
        self.assertAlmostEqual(rotation[0], 9.99)

    def test_nonimproving_rotation_is_restored(self):
        from types import SimpleNamespace
        rotation = [2.0, 0.0, 0.0]

        def match(nodes):
            rotation[0] = -20.0

        env = scope("_fit_pair", _ALIGNMENT=1.0 - 1e-6,
                    _MAX_CORRECTIONS=4, _match_pair=match,
                    _similarity=lambda nodes: math.cos(math.radians(10.0 - rotation[0])),
                    cmds=SimpleNamespace(getAttr=lambda plug: [tuple(rotation)]),
                    _set_rotation=lambda node, values: rotation.__setitem__(slice(None), values))
        self.assertFalse(env["_fit_pair"]({"to": "Thumb1"}))
        self.assertEqual(rotation, [2.0, 0.0, 0.0])

    def test_revisits_parent_when_later_pair_disturbs_direction(self):
        parent = {"to": "|rig|Thumb1"}
        child = {"to": "|rig|Thumb1|Thumb2"}
        scores = {parent["to"]: 0.0, child["to"]: 0.0}
        calls = []

        def fit(nodes):
            name = nodes["to"]
            calls.append(name)
            if scores[name] == 1.0:
                return False
            scores[name] = 1.0
            if name == child["to"]:
                scores[parent["to"]] = 0.9
            return True

        env = scope("_fit_pairs", _MAX_PASSES=4, _ALIGNMENT=1.0 - 1e-6,
                    _fit_pair=fit, _similarity=lambda nodes: scores[nodes["to"]])
        env["_fit_pairs"]([child, parent])
        self.assertEqual(calls, [parent["to"], child["to"], parent["to"], child["to"]])
        self.assertEqual(list(scores.values()), [1.0, 1.0])

    def test_residual_is_reported_not_raised(self):
        from types import SimpleNamespace
        warnings = []
        env = scope("_result", _ALIGNMENT=1.0 - 1e-6, math=math,
                    _similarity=lambda nodes: 0.99,
                    rt=SimpleNamespace(leaf=lambda node: node),
                    cmds=SimpleNamespace(warning=warnings.append))
        result = env["_result"]({"from": "OldThumb", "to": "Thumb1", "to_child": "Thumb2"})
        self.assertFalse(result["matched"])
        self.assertGreater(result["angle_degrees"], 0.0)
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
