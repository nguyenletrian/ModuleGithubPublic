"""Regression: Brush/Weight actions work without opening Paint Skin Tool Settings."""
import ast
from pathlib import Path
import types
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "Libs/NLTA_Brush.py"
MESH = "|Rig|Mesh"
JOINT = "|Rig|joint1"
SKIN = "skinCluster1"


class FakeCommands:
    def __init__(self):
        self.exists = True
        self.liw = False
        self.context_edits = []
        self.selection = [MESH + ".vtx[1]", MESH + ".vtx[2]"]
        self.weights = {
            MESH + ".vtx[1]": 0.2, MESH + ".vtx[2]": 0.95,
            MESH + ".vtx[3]": 0.6,
        }
        self.skin_writes = []
        self.warnings = []
        self.refreshed = 0
        self.brush_value = 0.5

    def artAttrSkinPaintCtx(self, context, **flags):
        assert context == "artAttrSkinContext"
        if flags.get("exists"):
            return self.exists
        if (flags.get("query") or flags.get("q")) and flags.get("value"):
            return self.brush_value
        if flags.get("edit") or flags.get("e"):
            self.context_edits.append(flags)
            if "value" in flags:
                self.brush_value = float(flags["value"])
        else:
            raise AssertionError("Unexpected paint flags " + str(flags))

    def currentCtx(self):
        return "artAttrSkinContext"

    def contextInfo(self, context, **flags):
        assert context == "artAttrSkinContext"
        assert flags == {"c": True}
        return "artAttrSkin"

    def warning(self, value):
        self.warnings.append(value)

    def ls(self, **flags):
        assert flags == {"selection": True, "long": True, "flatten": True}
        return list(self.selection)

    def objExists(self, node):
        return node == JOINT + ".liw"

    def getAttr(self, attr):
        assert attr == JOINT + ".liw"
        return self.liw

    def skinPercent(self, skin, vert, **kwargs):
        assert skin == SKIN
        if kwargs.get("query"):
            assert kwargs["transform"] == JOINT
            return self.weights[vert]
        influence, amount = kwargs["transformValue"]
        assert influence == JOINT
        self.weights[vert] = float(amount)
        self.skin_writes.append((vert, influence, float(amount)))

    def refresh(self, **kwargs):
        assert kwargs == {"force": True}
        self.refreshed += 1


class FakeMel:
    def __init__(self, exists=False):
        self.loaded = exists
        self.eval_calls = []

    def eval(self, source):
        self.eval_calls.append(source)
        if source == 'exists "artSkinSetSelectionValue"':
            return int(self.loaded)
        if source.startswith("artSkinSetSelectionValue "):
            if not self.loaded:
                raise AssertionError("Missing MEL procedure was called")
            return
        raise AssertionError("Unexpected MEL command: " + source)


def load_callbacks(cmds, mel):
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    wanted = {
        "_skinPaintContext", "_setBrushValue", "ReplaceWeight",
        "AddWeight", "SwitchBrush", "smooth", "pickValue", "flood",
    }
    methods = [x for x in module.body if isinstance(x, ast.FunctionDef)
               and x.name in wanted]
    assert len(methods) == len(wanted)
    skinning = types.SimpleNamespace(
        EnsureSkinSession=lambda warn=False: {
            "skinCluster": SKIN, "mesh": MESH,
        },
        GetActivePaintJoint=lambda skin: JOINT if skin == SKIN else None,
    )
    scope = {"cmds": cmds, "mel": mel, "NLTA_Skinning": skinning}
    exec(compile(ast.Module(body=methods, type_ignores=[]),
                 str(SOURCE), "exec"), scope)
    return scope


class BrushContextTests(unittest.TestCase):
    def setUp(self):
        self.cmds = FakeCommands()
        self.mel = FakeMel()
        self.brush = load_callbacks(self.cmds, self.mel)

    def _assert_brush_only(self, value, operation="absolute"):
        before = dict(self.cmds.weights)
        selection = list(self.cmds.selection)
        self.assertTrue(self.brush["ReplaceWeight"](value))
        self.assertEqual(self.cmds.weights, before)
        self.assertEqual(self.cmds.selection, selection)
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertEqual(self.cmds.refreshed, 0)
        self.assertEqual(self.mel.eval_calls, [])
        self.assertEqual(self.cmds.context_edits[-1], {
            "edit": True, "skinPaintMode": 1,
            "selectedattroper": operation, "value": float(value),
        })

    def test_set_zero_changes_brush_only(self):
        self._assert_brush_only(0)

    def test_set_one_changes_brush_only(self):
        self._assert_brush_only(1)

    def test_set_zero_with_no_selected_vertex_still_changes_brush(self):
        self.cmds.selection = [MESH]
        self._assert_brush_only(0)

    def test_set_one_with_no_selected_vertex_still_changes_brush(self):
        self.cmds.selection = [MESH]
        self._assert_brush_only(1)

    def test_locked_influence_does_not_block_setting_brush_value(self):
        self.cmds.liw = True
        self._assert_brush_only(1)

    def test_native_mel_ui_procedures_are_never_invoked(self):
        self.mel.loaded = True
        self._assert_brush_only(0)
        self._assert_brush_only(1)

    def test_add_preset_modifies_only_selected_weights_with_maya_fallback(self):
        untouched = self.cmds.weights[MESH + ".vtx[3]"]
        original_selection = list(self.cmds.selection)
        self.assertTrue(self.brush["AddWeight"](0.1))
        self.assertAlmostEqual(self.cmds.weights[MESH + ".vtx[1]"], 0.3)
        self.assertEqual(self.cmds.weights[MESH + ".vtx[2]"], 1.0)
        self.assertTrue(self.brush["AddWeight"](-0.5))
        self.assertEqual(self.cmds.weights[MESH + ".vtx[1]"], 0.0)
        self.assertEqual(self.cmds.weights[MESH + ".vtx[2]"], 0.5)
        self.assertEqual(self.cmds.weights[MESH + ".vtx[3]"], untouched)
        self.assertEqual(self.cmds.selection, original_selection)
        self.assertEqual(len(self.cmds.skin_writes), 4)
        self.assertEqual(self.cmds.refreshed, 2)
        self.assertEqual(self.cmds.context_edits[-1], {
            "edit": True, "skinPaintMode": 1,
            "selectedattroper": "additive", "value": -0.5,
        })

    def test_add_preset_uses_original_native_mel_when_available(self):
        self.mel.loaded = True
        originals = dict(self.cmds.weights)
        self.assertTrue(self.brush["AddWeight"](-0.01))
        self.assertEqual(self.cmds.weights, originals)
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertIn(
            "artSkinSetSelectionValue -0.01 false artAttrSkinPaintCtx artAttrSkin;",
            self.mel.eval_calls)

    def test_add_preset_does_not_modify_locked_influence(self):
        self.cmds.liw = True
        originals = dict(self.cmds.weights)
        self.assertFalse(self.brush["AddWeight"](0.03))
        self.assertEqual(self.cmds.weights, originals)
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertTrue(any("locked" in w for w in self.cmds.warnings))

    def test_add_without_vertex_selection_does_not_flood_mesh(self):
        self.cmds.selection = [MESH]
        originals = dict(self.cmds.weights)
        self.assertFalse(self.brush["AddWeight"](0.03))
        self.assertEqual(self.cmds.weights, originals)
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertTrue(any("select vertices" in w for w in self.cmds.warnings))

    def test_all_mayascriptnew_add_step_sizes_are_supported(self):
        increments = (0.0001, 0.0005, 0.001, 0.005,
                      0.01, 0.03, 0.05, 0.1)
        for delta in increments:
            for sign in (-1, 1):
                with self.subTest(delta=delta, sign=sign):
                    self.cmds.weights[MESH + ".vtx[1]"] = 0.5
                    self.assertTrue(self.brush["AddWeight"](delta * sign))
                    self.assertAlmostEqual(
                        self.cmds.weights[MESH + ".vtx[1]"],
                        0.5 + delta * sign)

    def test_switching_zero_and_one_sets_current_value_only(self):
        self._assert_brush_only(0)
        self._assert_brush_only(1)
        self._assert_brush_only(0)
        self.assertEqual(
            [x["value"] for x in self.cmds.context_edits], [0.0, 1.0, 0.0])

    def test_switch_brush_toggles_signed_value_without_editing_skin(self):
        original = dict(self.cmds.weights)
        self.brush["SwitchBrush"]()
        self.assertEqual(self.cmds.brush_value, -0.5)
        self.assertEqual(self.cmds.context_edits[0], {
            "edit": True, "skinPaintMode": 1,
            "selectedattroper": "additive", "value": -0.5,
        })
        self.brush["SwitchBrush"]()
        self.assertEqual(self.cmds.brush_value, 0.5)
        self.assertEqual(self.cmds.weights, original)
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertEqual(self.mel.eval_calls, [])

    def test_uninitialized_context_does_not_touch_weights(self):
        original = dict(self.cmds.weights)
        self.cmds.exists = False
        self.assertFalse(self.brush["ReplaceWeight"](0))
        self.assertFalse(self.brush["AddWeight"](1))
        self.assertEqual(self.cmds.weights, original)
        self.assertEqual(self.cmds.context_edits, [])
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertEqual(self.mel.eval_calls, [])

    def test_smooth_keeps_legacy_solid_profile_without_mel_ui(self):
        self.brush["smooth"]("solid")
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "skinPaintMode": 1,
            "stampProfile": "solid", "selectedattroper": "smooth",
        }])
        self.assertEqual(self.mel.eval_calls, [])

    def test_flood_uses_explicit_clear_only(self):
        self.brush["flood"]()
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "skinPaintMode": 1, "clear": True,
        }])
        self.assertEqual(self.mel.eval_calls, [])

    def test_pick_value_is_not_dependent_on_tool_settings(self):
        self.brush["pickValue"]()
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "selectedattroper": "absolute",
            "pickValue": True, "opacity": 1,
        }])
        self.assertEqual(self.mel.eval_calls, [])

    def test_missing_mel_ui_procedures_stay_unused_but_weight_add_is_restored(self):
        source = SOURCE.read_text(encoding="utf-8")
        for unavailable in (
            "artAttrSkinPaintModePaintSelect",
            "artAttrPaintOperation",
            "artUpdateStampProfile",
        ):
            self.assertNotIn(unavailable, source)
        self.assertIn('exists "artSkinSetSelectionValue"', source)
        self.assertIn("skinPercent(", source)
        self.assertIn("_setBrushValue(newValue", source)


if __name__ == "__main__":
    unittest.main()
