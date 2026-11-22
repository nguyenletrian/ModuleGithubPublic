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

    def assert_preset_only(self, function, value, operation):
        before = dict(self.cmds.weights)
        selected = list(self.cmds.selection)
        self.assertTrue(self.brush[function](value))
        self.assertEqual(self.cmds.weights, before)
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertEqual(self.cmds.selection, selected)
        self.assertEqual(self.cmds.refreshed, 0)
        self.assertEqual(self.mel.eval_calls, [])
        self.assertEqual(self.cmds.brush_value, float(value))
        self.assertEqual(self.cmds.context_edits[-1], {
            "edit": True, "skinPaintMode": 1,
            "selectedattroper": operation, "stampProfile": "solid",
            "minvalue": -1.0, "value": float(value), "opacity": 1.0,
        })

    def test_every_preset_resets_custom_stamp_to_solid(self):
        # The artist may have previously selected a soft brush.
        # Every preset should return to the requested solid default.
        self.cmds.context_edits.clear()
        self.assert_preset_only("ReplaceWeight", 0, "absolute")
        self.assertEqual(self.cmds.context_edits[-1]["stampProfile"], "solid")
        self.assert_preset_only("AddWeight", -0.01, "additive")
        self.assertEqual(self.cmds.context_edits[-1]["stampProfile"], "solid")

    def test_set_zero_sets_replace_value_only_at_full_opacity(self):
        self.assert_preset_only("ReplaceWeight", 0, "absolute")

    def test_set_one_uses_original_add_mode_at_full_opacity(self):
        self.assert_preset_only("AddWeight", 1, "additive")

    def test_all_sixteen_signed_presets_set_value_only_at_full_opacity(self):
        steps = (0.0001, 0.0005, 0.001, 0.005, 0.01, 0.03, 0.05, 0.1)
        for step in steps:
            for sign in (-1, 1):
                value = sign * step
                with self.subTest(value=value):
                    self.cmds.context_edits.clear()
                    self.cmds.brush_value = 0.4
                    self.assert_preset_only("AddWeight", value, "additive")

    def test_unselected_mesh_still_allows_setting_brush_preset(self):
        self.cmds.selection = [MESH]
        self.assert_preset_only("AddWeight", -0.03, "additive")
        self.assert_preset_only("ReplaceWeight", 0, "absolute")

    def test_locked_influence_does_not_block_setting_brush_value(self):
        self.cmds.liw = True
        self.assert_preset_only("AddWeight", 0.05, "additive")
        self.assert_preset_only("ReplaceWeight", 0, "absolute")

    def test_existing_mel_procedure_does_not_trigger_vertex_edit(self):
        self.mel.loaded = True
        self.assert_preset_only("AddWeight", 0.1, "additive")
        self.assert_preset_only("ReplaceWeight", 0, "absolute")

    def test_switching_brush_value_always_restores_opacity_one(self):
        self.cmds.brush_value = 0.25
        self.brush["SwitchBrush"]()
        self.assertEqual(self.cmds.brush_value, -0.25)
        self.assertEqual(self.cmds.context_edits[-1]["opacity"], 1.0)
        self.brush["SwitchBrush"]()
        self.assertEqual(self.cmds.brush_value, 0.25)
        self.assertEqual(self.cmds.context_edits[-1]["opacity"], 1.0)
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertEqual(self.mel.eval_calls, [])

    def test_uninitialized_context_does_not_change_skin_or_value(self):
        original = dict(self.cmds.weights)
        self.cmds.exists = False
        self.assertFalse(self.brush["AddWeight"](-0.1))
        self.assertFalse(self.brush["ReplaceWeight"](0))
        self.assertEqual(self.cmds.weights, original)
        self.assertEqual(self.cmds.context_edits, [])
        self.assertEqual(self.cmds.skin_writes, [])

    def test_smooth_preserves_context_only(self):
        self.brush["smooth"]("solid")
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "skinPaintMode": 1,
            "stampProfile": "solid", "selectedattroper": "smooth",
        }])

    def test_flood_requires_separate_explicit_action(self):
        self.brush["flood"]()
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "skinPaintMode": 1, "clear": True,
        }])
        self.assertEqual(self.mel.eval_calls, [])

    def test_pick_value_preserves_existing_behavior(self):
        self.brush["pickValue"]()
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "selectedattroper": "absolute",
            "pickValue": True, "opacity": 1,
        }])

    def test_no_direct_skin_writes_or_optional_mel_procedures(self):
        source = SOURCE.read_text(encoding="utf-8")
        for unsafe in (
            "skinPercent(", "artSkinSetSelectionValue",
            "artAttrSkinPaintModePaintSelect",
            "artAttrPaintOperation",
        ):
            self.assertNotIn(unsafe, source)
        self.assertIn("opacity=1.0", source)


if __name__ == "__main__":
    unittest.main()
