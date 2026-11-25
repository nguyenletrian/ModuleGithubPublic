"""Offline contracts for multi-item Extra Transform."""
import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_Transform.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = dict(math=math, _GROUPS=("translate", "rotate", "scale"),
               _AXES=("X", "Y", "Z"), **dependencies)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(STEP), "exec"), env)
    return env


class TransformItemsTests(unittest.TestCase):
    def test_legacy_settings(self):
        env = scope()
        item = env["NormalizeSettings"]({"source": "REF", "object": "Root",
                                        "offsets": {"rotate": [0, 10, 0]}})["items"][0]
        self.assertEqual(item["source"], "REF")
        self.assertEqual(item["offsets"]["rotate"], [0.0, 10.0, 0.0])
        self.assertEqual(item["offsets"]["scale"], [0.0, 0.0, 0.0])

    def test_multiple_items_accumulate_and_skip_empty(self):
        writes = []
        env = scope(rt=SimpleNamespace(resolve=lambda ns, name: ns + ":" + name),
                    cmds=SimpleNamespace(getAttr=lambda plug, **kw: True if kw else 1.0,
                                         setAttr=lambda plug, value: writes.append((plug, value))))
        result = env["Run"]({"items": [
            {},
            {"object": "Root", "offsets": {"translate": [2, 0, 0]}},
            {"source": "REF", "object": "Root", "offsets": {"scale": [0, 0, 3]}},
            {"object": "Root", "offsets": {"translate": [4, 0, 0]}}]},
            {"target_namespace": "Rig", "reference_pose_namespace": "REF"})
        self.assertEqual(writes, [("Rig:Root.translateX", 7.0), ("REF:Root.scaleZ", 4.0)])
        self.assertEqual(result["items"], 3)

    def test_locked_channel_prevents_partial_write(self):
        writes = []
        env = scope(rt=SimpleNamespace(resolve=lambda ns, name: ns + ":" + name),
                    cmds=SimpleNamespace(getAttr=lambda plug, **kw:
                                         not plug.startswith("Rig:Locked") if kw else 1.0,
                                         setAttr=lambda *args: writes.append(args)))
        with self.assertRaisesRegex(ValueError, "locked/connected"):
            env["Run"]({"items": [
                {"object": "Root", "offsets": {"rotate": [10, 0, 0]}},
                {"object": "Locked", "offsets": {"rotate": [10, 0, 0]}}]},
                {"target_namespace": "Rig"})
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
