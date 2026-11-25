"""Offline tests for automatic Match Rotate mapping."""
import ast
import itertools
import math
import re
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
        pairs = env["_resolve_pairs"]({"mirror": False, "pairs": [
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
        self.assertEqual(env["DefaultSetting"](), {"mirror": True, "pairs": [
            {"from_role": "REF", "from": "", "to_role": "Rig", "to": ""}]})
        self.assertEqual(env["Fields"](), [
            ("Mirror", "mirror", "bool"),
            ("Rotation Pairs", "pairs", "match_rotate_pairs")])

    def test_shared_mirror_expands_all_side_pairs_and_skips_center(self):
        env = scope("PairData", "_mirror_name", "_resolve_pairs", re=re,
                    _namespace=lambda role, context: role,
                    rt=SimpleNamespace(resolve=lambda ns, name: ns + ":" + name,
                                       leaf=lambda node: node.split(":")[-1]))
        rows = [
            {"from": "Bip001FBXASC032RFBXASC032UpperArm", "to": "R_Shoulder_FK"},
            {"from": "R_Hand", "to": "R_Wrist_FK"},
            {"from": "Spine", "to": "Chest_FK"}]
        resolve = env["_resolve_pairs"]
        pairs = resolve({"pairs": rows}, {})
        self.assertEqual(len(pairs), 5)
        self.assertIn(("REF:Bip001FBXASC032LFBXASC032UpperArm",
                       "Rig:L_Shoulder_FK"), pairs)
        self.assertIn(("REF:L_Hand", "Rig:L_Wrist_FK"), pairs)
        self.assertEqual(len(resolve({"mirror": False, "pairs": rows}, {})), 3)
        rows.append({"from": "LeftHand", "to": "L_Wrist_FK"})
        pairs = resolve({"mirror": True, "pairs": rows}, {})
        self.assertEqual(len(pairs), 5)
        self.assertIn(("REF:LeftHand", "Rig:L_Wrist_FK"), pairs)
        self.assertNotIn(("REF:L_Hand", "Rig:L_Wrist_FK"), pairs)

    def test_preserves_hand_before_fingers_in_user_pair_order(self):
        # Hand is deeper in the DAG, but drives the shallow Finger Root.
        hand = "|Rig|World|Spine|Chest|Arm|Hand"
        thumb = "|Rig|Fingers|Thumb1"
        tip = thumb + "|Thumb2"
        rotations = {hand: 0.0, thumb: 0.0, tip: 0.0}
        goals = {hand: 16.538, thumb: 25.0, tip: 40.0}
        writes = []

        def xform(node, **kw):
            desired = kw["rotation"]
            delta = desired - rotations[node]
            rotations[node] = desired
            if node == hand:
                rotations[thumb] += delta
                rotations[tip] += delta
            if node == thumb:
                rotations[tip] += delta
            writes.append(node)

        env = scope("_apply_orientations",
                    _MAX_PASSES=6, _ANGLE_TOLERANCE=0.01,
                    _orientation_error=lambda actual, desired: abs(actual - desired),
                    rt=SimpleNamespace(_rotation=rotations.__getitem__,
                                       _euler_angles=lambda desired, order: desired),
                    cmds=SimpleNamespace(getAttr=lambda plug: 0, xform=xform))
        pending = [("old", node, goals[node], {}) for node in (hand, thumb, tip)]
        self.assertEqual(env["_apply_orientations"](pending), 1)
        self.assertEqual(rotations, goals)
        self.assertEqual(writes, [hand, thumb, tip])

        # Explicitly reversing the user order is still honored on pass one;
        # subsequent correction passes resolve the resulting dependency.
        rotations.update({node: 0.0 for node in rotations})
        writes.clear()
        self.assertEqual(env["_apply_orientations"](list(reversed(pending))), 3)
        self.assertEqual(writes[:3], [tip, thumb, hand])
        self.assertEqual(writes.count(hand), 1)
        self.assertEqual(writes.count(thumb), 2)
        self.assertEqual(rotations, goals)

    def test_correction_is_bounded_if_control_does_not_follow(self):
        calls = []
        env = scope("_apply_orientations",
                    _MAX_PASSES=6, _ANGLE_TOLERANCE=0.01,
                    _orientation_error=lambda actual, desired: abs(actual - desired),
                    rt=SimpleNamespace(_rotation=lambda node: 0.0,
                                       _euler_angles=lambda desired, order: desired),
                    cmds=SimpleNamespace(getAttr=lambda plug: 0,
                                         xform=lambda node, **kw: calls.append(node)))
        self.assertEqual(env["_apply_orientations"]([("old", "|rig|ctrl", 20.0, {})]), 6)
        self.assertEqual(len(calls), 6)

    def test_quaternion_error_ignores_equivalent_quaternion_sign(self):
        def q(x, y, z, w):
            return SimpleNamespace(x=x, y=y, z=z, w=w)
        f = scope("_orientation_error", math=math)["_orientation_error"]
        self.assertAlmostEqual(f(q(0, 0, 0, 1), q(0, 0, 0, -1)), 0.0)
        self.assertAlmostEqual(f(q(0, 0, 0, 1),
                                 q(0, 0, math.sin(math.radians(8.269)),
                                   math.cos(math.radians(8.269)))), 16.538)

    def test_new_module_is_registered_and_optional(self):
        ui = (ROOT / "UIs/Retarget.py").read_text(encoding="utf-8")
        self.assertIn('("MatchRotate", "Retarget_MatchRotate.py")', ui)
        self.assertIn('"SetValue", "MatchRotatePair", "MatchRotate")', ui)


if __name__ == "__main__":
    unittest.main()
