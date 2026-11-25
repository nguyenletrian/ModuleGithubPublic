"""Offline contracts for the namespace-based Maya Bake module."""
import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_Bake.py"


def scope(path=STEP, **dependencies):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = dict(math=math, _CHANNELS=tuple(group + axis for group in
               ("translate", "rotate", "scale") for axis in "XYZ"), **dependencies)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), env)
    return env


class BakeTests(unittest.TestCase):
    def test_independent_namespace_and_key_range(self):
        calls = []
        def keyframe(node, **kw):
            self.assertEqual(node, "Anim:Pelvis")
            self.assertEqual(kw["hierarchy"], "none")
            return [-2.5, 10, 50.25]
        def get_attr(plug, **kw):
            self.assertNotIn("settable", kw)
            if kw.get("lock"):
                return plug.endswith("translateX")
            return not plug.endswith("scaleZ")
        def bake(plugs, **kw):
            calls.append((plugs, kw))
            return len(plugs)
        env = scope(rt=SimpleNamespace(resolve=lambda ns, name: ns + ":" + name,
                    namespace_nodes=lambda ns: ["|Rig:Hand", "|Rig:Child", "|Rig:Nested:Other"]),
                    cmds=SimpleNamespace(keyframe=keyframe, getAttr=get_attr,
                        nodeType=lambda node: "transform", bakeResults=bake,
                        currentTime=lambda *args, **kw: 12))
        context = {"reference_namespaces": {"new_rig": "Rig", "old_animations": "Anim"}}
        result = env["Run"]({"range_object": "Pelvis"}, context)
        plugs, kw = calls[0]
        self.assertEqual(result["objects"], 2)
        self.assertEqual(result["channels"], 14)
        self.assertEqual(kw["time"], (-3, 51))
        self.assertTrue(kw["simulation"])
        self.assertEqual(kw["sampleBy"], 1)
        self.assertTrue(kw["minimizeRotation"])
        self.assertTrue(all(not p.endswith(("translateX", "scaleZ")) for p in plugs))
        self.assertNotIn("baked", context)

    def test_no_keys_does_not_guess_playback_range(self):
        env = scope(cmds=SimpleNamespace(keyframe=lambda *args, **kw: []))
        with self.assertRaisesRegex(ValueError, "no animation keys"):
            env["_range"]("Anim:Pelvis")

    def test_bake_is_included_in_batch_without_mapping(self):
        env = scope(ROOT / "UIs/Retarget.py")
        rows = [{"kind": "Constraint", "enabled": True, "order": 10},
                {"kind": "Bake", "enabled": True, "order": 20},
                {"kind": "Save", "enabled": True, "order": 30}]
        self.assertEqual(env["_validate_sequence"](True, rows), rows)


if __name__ == "__main__":
    unittest.main()
