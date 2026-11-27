"""Offline contracts for Copy Attribute."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

STEP = Path(__file__).resolve().parents[1] / "UIs/RetargetSteps/Retarget_CopyAttribute.py"


class CopyAttributeTests(unittest.TestCase):
    def test_copy_current_values_and_validate_before_writing(self):
        values = {"Anim:From.rotateX": 12.5, "Rig:To.rotateX": 0.0,
                  "Anim:From.translate": [(1.0, 2.0, 3.0)],
                  "Rig:To.translate": [(0.0, 0.0, 0.0)],
                  "Anim:From.mode": 2, "Rig:To.mode": 0,
                  "Anim:From.note": "source", "Rig:To.note": ""}
        types = {"rotateX": "doubleAngle", "translate": "double3",
                 "mode": "enum", "note": "string"}
        writes = []
        def get_attr(plug, **kw):
            if kw.get("settable"):
                return True
            if kw.get("type"):
                return types[plug.rsplit(".", 1)[1]]
            return values[plug]
        def set_attr(plug, *args, **kw):
            writes.append((plug, args, kw))
        cmds = SimpleNamespace(objExists=lambda plug: plug in values,
                               getAttr=get_attr, setAttr=set_attr)
        rt = SimpleNamespace(resolve=lambda ns, name: ns + ":" + name)
        env = dict(cmds=cmds, rt=rt)
        tree = ast.parse(STEP.read_text(encoding="utf-8"))
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        exec(compile(ast.Module(body=body, type_ignores=[]), str(STEP), "exec"), env)
        data = dict(env["DefaultSetting"](), **{"source_role": "Anim", "target_role": "Rig",
                    "from": "From", "to": "To",
                    "attributes": ["rotateX", "translate", "mode", "note", "rotateX"]})
        ctx = {"target_namespace": "Rig", "source_namespace_animation": "Anim"}
        self.assertEqual(env["NormalizeSettings"]({"source_role": "Anim"})["target_role"], "Anim")
        result = env["Run"](data, ctx)
        self.assertEqual(result["changed"], 4)
        self.assertEqual(result["from"], "Anim:From")
        self.assertEqual(result["to"], "Rig:To")
        self.assertEqual(writes, [
            ("Rig:To.rotateX", (12.5,), {}),
            ("Rig:To.translate", (1.0, 2.0, 3.0), {"type": "double3"}),
            ("Rig:To.mode", (2,), {}),
            ("Rig:To.note", ("source",), {"type": "string"})])
        writes.clear()
        data["attributes"].append("missing")
        with self.assertRaisesRegex(ValueError, "existing channels"):
            env["Run"](data, ctx)
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
