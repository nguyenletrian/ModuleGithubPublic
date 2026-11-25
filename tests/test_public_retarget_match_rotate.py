"""Offline tests for automatic Match Rotate mapping."""
import ast
import itertools
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_MatchRotate.py"


def scope(*names, **dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    env = dict(dependencies)
    module = ast.Module(body=[functions[name] for name in names], type_ignores=[])
    exec(compile(module, str(STEP), "exec"), env)
    return env


class MatchRotateTests(unittest.TestCase):
    def test_all_24_axis_conventions_preserve_already_aligned_orientation(self):
        f = scope("_axis_mapping", itertools=itertools)["_axis_mapping"]
        source = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        for order in itertools.permutations(range(3)):
            parity = (-1) ** sum(order[i] > order[j] for i in range(3)
                                  for j in range(i + 1, 3))
            for signs in itertools.product((1, -1), repeat=3):
                if signs[0] * signs[1] * signs[2] != parity:
                    continue
                target = tuple(tuple(signs[i] * x for x in source[order[i]])
                               for i in range(3))
                self.assertEqual(f(source, target), (order, signs, target))

    def test_small_rotation_is_aligned_without_swapping_axes(self):
        f = scope("_axis_mapping", itertools=itertools)["_axis_mapping"]
        source = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        target = ((0.8, 0.6, 0), (-0.6, 0.8, 0), (0, 0, 1))
        self.assertEqual(f(source, target), ((0, 1, 2), (1, 1, 1), source))

    def test_only_explicit_pairs_are_resolved(self):
        calls = []
        def resolve(ns, name):
            calls.append((ns, name))
            return ns + ":" + name

        env = scope("PairData", "_resolve_pairs",
                    _namespace=lambda role, context: role,
                    rt=SimpleNamespace(resolve=resolve))
        pairs = env["_resolve_pairs"]({"pairs": [
            {"from_role": "REF", "from": "Bip001Arm",
             "to_role": "Rig", "to": "R_Shoulder_FK"},
            {"from_role": "Rig", "from": "ControlA",
             "to_role": "Rig", "to": "ControlB"}]},
            {"pairs": [{"old": "ignored", "new": "ignored"}]})
        self.assertEqual(pairs, [("REF:Bip001Arm", "Rig:R_Shoulder_FK"),
                                 ("Rig:ControlA", "Rig:ControlB")])
        self.assertEqual(len(calls), 4)
        with self.assertRaisesRegex(ValueError, "add at least one"):
            env["_resolve_pairs"]({}, {"pairs": [{"old": "x", "new": "y"}]})
        with self.assertRaisesRegex(ValueError, "select From and To"):
            env["_resolve_pairs"]({"pairs": [{"from": "x"}]}, {})

    def test_default_has_one_pair_and_no_namespace_wide_auto_mapping(self):
        env = scope("PairData", "DefaultSetting", "Fields")
        self.assertEqual(env["DefaultSetting"](), {"pairs": [
            {"from_role": "REF", "from": "", "to_role": "Rig", "to": ""}]})
        self.assertEqual(env["Fields"](),
                         [("Rotation Pairs", "pairs", "match_rotate_pairs")])

    def test_new_module_is_registered_and_optional(self):
        ui = (ROOT / "UIs/Retarget.py").read_text(encoding="utf-8")
        self.assertIn('("MatchRotate", "Retarget_MatchRotate.py")', ui)
        self.assertIn('"SetValue", "MatchRotatePair", "MatchRotate")', ui)


if __name__ == "__main__":
    unittest.main()
