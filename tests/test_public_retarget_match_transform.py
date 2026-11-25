"""Offline contracts for Match Transform and legacy alignment compatibility."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_MatchTransform.py"


def scope(*names, **dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    env = dict(dependencies)
    module = ast.Module(body=[functions[name] for name in names],
                        type_ignores=[])
    exec(compile(module, str(STEP), "exec"), env)
    return env


class MatchTransformTests(unittest.TestCase):
    def test_copies_full_live_matrix_in_pair_order(self):
        matrix = [2, 0, 0, 0, 0, 0, -2, 0, 0, 2, 0, 0, 3, 5, 7, 1]
        values = {"REF:A": matrix[:], "Rig:B": [0] * 16, "Rig:C": [0] * 16}
        calls = []

        def xform(node, **kw):
            self.assertTrue(kw["worldSpace"])
            if kw.get("query"):
                self.assertTrue(kw["matrix"])
                calls.append(("query", node))
                return values[node][:]
            calls.append(("apply", node))
            values[node] = kw["matrix"][:]

        env = scope("PairData", "Run",
                    _namespace=lambda role, context: role,
                    rt=SimpleNamespace(resolve=lambda ns, name: ns + ":" + name,
                                       leaf=lambda node: node.split(":")[-1]),
                    cmds=SimpleNamespace(xform=xform))
        result = env["Run"]({"pairs": [
            {"from": "A", "to": "B"},
            {"from_role": "Rig", "from": "B", "to": "C"}]}, {})
        self.assertEqual(result, {"matched": 2})
        self.assertEqual(values["Rig:C"], matrix)
        self.assertEqual(calls, [("query", "REF:A"), ("apply", "Rig:B"),
                                 ("query", "Rig:B"), ("apply", "Rig:C")])

    def test_new_picker_replaces_legacy_but_preserves_existing_profiles(self):
        ui = (ROOT / "UIs/Retarget.py").read_text(encoding="utf-8")
        self.assertIn('("MatchTransform", "Retarget_MatchTransform.py")', ui)
        self.assertIn('STEP_MAP = dict(STEP_FILES, Rotate="Retarget_Rotate.py")', ui)
        self.assertNotIn('("Rotate", "Retarget_Rotate.py"),', ui)
        env = scope("PairData", "DefaultSetting", "Fields")
        self.assertEqual(env["DefaultSetting"]()["pairs"], [
            {"from_role": "REF", "from": "", "to_role": "Rig", "to": ""}])
        self.assertEqual(env["Fields"](), [
            ("Transform Pairs", "pairs", "match_rotate_pairs")])


if __name__ == "__main__":
    unittest.main()
