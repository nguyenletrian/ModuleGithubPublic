"""Offline contracts for per-item Set Value mirror."""
import ast
import math
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_SetValue.py"


def scope(*names, **dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    env = dict(dependencies)
    module = ast.Module(body=[functions[name] for name in names],
                        type_ignores=[])
    exec(compile(module, str(STEP), "exec"), env)
    return env


class SetValueMirrorTests(unittest.TestCase):
    def run_items(self, items, missing=None):
        writes = []
        def resolve(ns, name):
            if name == missing:
                raise ValueError("Missing object: " + name)
            return ns + ":" + name

        env = scope("Run", "_items", "_attribute_value", "_mirror_name",
                    math=math, re=re,
                    _namespace=lambda role, context: role,
                    rt=SimpleNamespace(resolve=resolve,
                                       leaf=lambda node: node.split(":")[-1]),
                    cmds=SimpleNamespace(
                        objExists=lambda plug: True,
                        getAttr=lambda plug, **kw: "double" if kw.get("type") else True,
                        setAttr=lambda *args, **kw: writes.append(args)))
        return env, writes

    def test_per_item_mirror_same_attribute_and_value(self):
        rows = [
            {"source": "Rig", "object": "R_Arm", "attribute": "rx", "value": "25", "mirror": True},
            {"source": "REF", "object": "R_Hand", "attribute": "tx", "value": "-3", "mirror": False},
            {"object": "Chest", "attribute": "ry", "value": "2", "mirror": True},
            {"object": "R_Leg", "attribute": "rz", "value": "0"},
        ]
        env, writes = self.run_items(rows)
        result = env["Run"]({"items": rows}, {})
        self.assertEqual(writes, [
            ("Rig:R_Arm.rx", 25.0), ("Rig:L_Arm.rx", 25.0),
            ("REF:R_Hand.tx", -3.0), ("Rig:Chest.ry", 2.0),
            ("Rig:R_Leg.rz", 0.0)])
        self.assertEqual(result["changed"], 5)

    def test_missing_opposite_prevents_partial_writes(self):
        rows = [{"object": "R_Arm", "attribute": "rx", "value": "25", "mirror": True}]
        env, writes = self.run_items(rows, missing="L_Arm")
        with self.assertRaisesRegex(ValueError, "Missing object"):
            env["Run"]({"items": rows}, {})
        self.assertEqual(writes, [])

    def test_default_preserves_single_side(self):
        env = scope("DefaultSetting", "_mirror_name", re=re)
        self.assertFalse(env["DefaultSetting"]()["items"][0]["mirror"])
        self.assertEqual(env["_mirror_name"]("Bip001FBXASC032RFBXASC032UpperArm"),
                         "Bip001FBXASC032LFBXASC032UpperArm")


if __name__ == "__main__":
    unittest.main()
