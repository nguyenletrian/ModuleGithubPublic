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

    def artAttrSkinPaintCtx(self, context, **flags):
        assert context == "artAttrSkinContext"
        if flags.get("exists"):
            return self.exists
        if flags.get("edit"):
            self.context_edits.append(flags)
        else:
            raise AssertionError("Unexpected paint flags " + str(flags))

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
        "_skinPaintContext", "_setSelectedWeights", "ReplaceWeight",
        "AddWeight", "smooth", "pickValue", "flood",
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

    def test_set_zero_without_tool_settings_sets_selected_vertices_only(self):
        before = self.cmds.weights[MESH + ".vtx[3]"]
        self.assertTrue(self.brush["ReplaceWeight"](0))
        self.assertEqual(self.cmds.weights[MESH + ".vtx[1]"], 0.0)
        self.assertEqual(self.cmds.weights[MESH + ".vtx[2]"], 0.0)
        self.assertEqual(self.cmds.weights[MESH + ".vtx[3]"], before)
        self.assertEqual(len(self.cmds.skin_writes), 2)
        self.assertEqual(self.cmds.refreshed, 1)
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "skinPaintMode": 1,
            "selectedattroper": "absolute", "value": 0.0,
        }])

    def test_set_zero_uses_native_mel_when_present(self):
        self.mel.loaded = True
        self.assertTrue(self.brush["ReplaceWeight"](0))
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertIn(
            "artSkinSetSelectionValue 0.0 false artAttrSkinPaintCtx artAttrSkin;",
            self.mel.eval_calls)

    def test_add_and_subtract_clamp_per_vertex_to_zero_one(self):
        self.brush["AddWeight"](0.1)
        self.assertAlmostEqual(self.cmds.weights[MESH + ".vtx[1]"], 0.3)
        self.assertEqual(self.cmds.weights[MESH + ".vtx[2]"], 1.0)
        self.brush["AddWeight"](-0.5)
        self.assertEqual(self.cmds.weights[MESH + ".vtx[1]"], 0.0)
        self.assertEqual(self.cmds.weights[MESH + ".vtx[2]"], 0.5)
        self.assertEqual(self.cmds.context_edits[-1]["selectedattroper"], "additive")

    def test_lock_prevents_fallback_modify(self):
        self.cmds.liw = True
        self.assertFalse(self.brush["ReplaceWeight"](0))
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertTrue(any("locked" in x for x in self.cmds.warnings))

    def test_no_selected_vertices_does_not_flood_whole_mesh(self):
        self.cmds.selection = [MESH]
        self.assertFalse(self.brush["ReplaceWeight"](0))
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertEqual(self.cmds.refreshed, 0)
        self.assertTrue(self.cmds.warnings)

    def test_missing_context_does_not_write(self):
        self.cmds.exists = False
        self.assertFalse(self.brush["ReplaceWeight"](0))
        self.assertEqual(self.cmds.skin_writes, [])
        self.assertEqual(self.mel.eval_calls, [])

    def test_smooth_uses_native_supported_context_flags(self):
        self.brush["smooth"]("solid")
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "skinPaintMode": 1,
            "stampProfile": "solid", "selectedattroper": "smooth",
        }])
        self.assertEqual(self.mel.eval_calls, [])

    def test_flood_uses_clear_not_incorrect_mel_ui_proc(self):
        self.brush["flood"]()
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "skinPaintMode": 1, "clear": True,
        }])
        self.assertEqual(self.mel.eval_calls, [])

    def test_pick_value_does_not_depend_on_tool_settings(self):
        self.brush["pickValue"]()
        self.assertEqual(self.cmds.context_edits, [{
            "edit": True, "selectedattroper": "absolute",
            "pickValue": True, "opacity": 1,
        }])
        self.assertEqual(self.mel.eval_calls, [])

    def test_old_missing_mel_procedures_are_absent(self):
        source = SOURCE.read_text(encoding="utf-8")
        for outdated in ("artAttrSkinPaintModePaintSelect",
                         "artAttrPaintOperation",
                         "artUpdateStampProfile"):
            self.assertNotIn(outdated, source)


if __name__ == "__main__":
    unittest.main()
