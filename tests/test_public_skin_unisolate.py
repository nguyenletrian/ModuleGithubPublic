"""Un Iso must disable Maya isolate view without changing skin/selection."""
import ast
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1]
          / "Libs/NLTA_Skinning.py")


class MayaPanels:
    def __init__(self):
        self.panels = ["modelPanel1", "modelPanel2"]
        self.focus = "modelPanel1"
        self.isolated = {"modelPanel1": False, "modelPanel2": True}
        self.set_calls = []
        self.selection = ["|Rig|Mesh.vtx[7]"]
        self.influence_locks = {"|Rig|jointA": True, "|Rig|jointB": False}

    def getPanel(self, **options):
        if options == {"type": "modelPanel"}:
            return list(self.panels)
        if options == {"withFocus": True}:
            return self.focus
        raise AssertionError(options)

    def isolateSelect(self, panel, **options):
        assert panel in self.panels
        if options.get("query") and options.get("state"):
            return self.isolated[panel]
        if options == {"state": False}:
            self.set_calls.append((panel, False))
            self.isolated[panel] = False
            return
        raise AssertionError(options)


def load_un_isolate(maya, preferred=None):
    parsed = ast.parse(SOURCE.read_text(encoding="utf-8"))
    fn = next(node for node in parsed.body
              if isinstance(node, ast.FunctionDef)
              and node.name == "UnIsolateEffectVertex")
    scope = {"cmds": maya, "_NLTA_ISOLATE_PANEL": preferred}
    exec(compile(ast.Module(body=[fn], type_ignores=[]),
                 str(SOURCE), "exec"), scope)
    return scope, scope["UnIsolateEffectVertex"]


class UnIsolateTests(unittest.TestCase):
    def test_restores_previous_isolated_panel_first(self):
        maya = MayaPanels()
        maya.isolated["modelPanel1"] = True
        scope, invoke = load_un_isolate(maya, preferred="modelPanel2")
        self.assertTrue(invoke(mesh="|Rig|Mesh", joint="|Rig|jointA"))
        self.assertEqual(maya.set_calls, [("modelPanel2", False)])
        self.assertTrue(maya.isolated["modelPanel1"])
        self.assertFalse(maya.isolated["modelPanel2"])
        self.assertIsNone(scope["_NLTA_ISOLATE_PANEL"])

    def test_stale_panel_after_reload_falls_back_to_isolated_panel(self):
        maya = MayaPanels()
        maya.focus = "someOtherEditor"
        _, invoke = load_un_isolate(maya, preferred="deletedModelPanel")
        self.assertTrue(invoke())
        self.assertEqual(maya.set_calls, [("modelPanel2", False)])

    def test_no_isolate_is_noop(self):
        maya = MayaPanels()
        maya.isolated["modelPanel2"] = False
        _, invoke = load_un_isolate(maya)
        self.assertFalse(invoke())
        self.assertEqual(maya.set_calls, [])

    def test_no_model_panel_is_noop(self):
        maya = MayaPanels()
        maya.panels = []
        _, invoke = load_un_isolate(maya)
        self.assertFalse(invoke())
        self.assertEqual(maya.set_calls, [])

    def test_does_not_touch_skin_or_component_selection(self):
        maya = MayaPanels()
        original_selection = list(maya.selection)
        locks = dict(maya.influence_locks)
        _, invoke = load_un_isolate(maya)
        self.assertTrue(invoke(mesh="|Rig|Mesh", joint="|Rig|jointA"))
        self.assertEqual(maya.selection, original_selection)
        self.assertEqual(maya.influence_locks, locks)

    def test_original_isolate_caches_model_panel_for_un_iso(self):
        source = SOURCE.read_text(encoding="utf-8")
        node = next(item for item in ast.parse(source).body
                    if isinstance(item, ast.FunctionDef)
                    and item.name == "IsolateEffectVertex")
        body = ast.get_source_segment(source, node)
        self.assertIn("global _NLTA_ISOLATE_PANEL", body)
        self.assertIn("_NLTA_ISOLATE_PANEL = panelCurrent", body)


if __name__ == "__main__":
    unittest.main()
