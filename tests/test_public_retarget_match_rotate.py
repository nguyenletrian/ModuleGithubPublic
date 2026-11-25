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

    def test_auto_names_exclude_ambiguity(self):
        f = scope("_unique_name_pairs", rt=SimpleNamespace(
            leaf=lambda node: node.split(":")[-1]))["_unique_name_pairs"]
        self.assertEqual(f(["a:Arm", "a:Leg", "b:Leg", "a:Head"],
                           ["c:Arm", "c:Leg", "c:Other"]), [("a:Arm", "c:Arm")])

    def test_existing_mapping_used_for_different_names(self):
        env = scope("_resolve_pairs", _namespace=lambda role, context: role,
                    rt=SimpleNamespace(resolve=lambda ns, name: ns + ":" + name))
        pairs, mode = env["_resolve_pairs"]({}, {"pairs": [
            {"old": "Bip001Arm", "new": "R_Shoulder_FK"}]})
        self.assertEqual(pairs, [("REF:Bip001Arm", "Rig:R_Shoulder_FK")])
        self.assertEqual(mode, "existing mapping")

    def test_new_module_is_registered_and_optional(self):
        ui = (ROOT / "UIs/Retarget.py").read_text(encoding="utf-8")
        self.assertIn('("MatchRotate", "Retarget_MatchRotate.py")', ui)
        self.assertIn('"SetValue", "MatchRotatePair", "MatchRotate")', ui)


if __name__ == "__main__":
    unittest.main()
