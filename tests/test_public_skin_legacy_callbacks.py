"""Callback contract captured from MayaScriptBefore/modules/UIs/Skinning.py.

This test pins all 105 legacy button-to-function bindings and the meaningful
partial arguments. Labels may be compacted, but must not silently change the
command they invoke. The reference repository is not fetched in CI.
"""
import ast
from functools import partial
from pathlib import Path
import unittest

BOARD = Path(__file__).resolve().parents[1] / "UIs/SkinningTools/NLTA_Skinning_CommandBoard.py"

# (new button id, original NLTA function, positional partial arguments)
LEGACY_CALLBACKS = [
  [
    "animation/local/Rotate",
    "NLTA_Keyframes.CreateKeyframe",
    [
      {
        "space": "local",
        "type": "rotate",
        "inturn": True,
        "ui": "fake_distance_ui"
      }
    ]
  ],
  [
    "animation/local/Translate",
    "NLTA_Keyframes.CreateKeyframe",
    [
      {
        "space": "local",
        "type": "translate",
        "inturn": True,
        "ui": "fake_distance_ui"
      }
    ]
  ],
  [
    "animation/local/Rotate Together",
    "NLTA_Keyframes.CreateKeyframe",
    [
      {
        "space": "local",
        "type": "rotate",
        "inturn": False,
        "ui": "fake_distance_ui"
      }
    ]
  ],
  [
    "animation/local/Translate Together",
    "NLTA_Keyframes.CreateKeyframe",
    [
      {
        "space": "local",
        "type": "translate",
        "inturn": False,
        "ui": "fake_distance_ui"
      }
    ]
  ],
  [
    "animation/world/Rotate",
    "NLTA_Keyframes.CreateKeyframe",
    [
      {
        "space": "world",
        "type": "rotate",
        "inturn": True,
        "ui": "fake_distance_ui"
      }
    ]
  ],
  [
    "animation/world/Translate",
    "NLTA_Keyframes.CreateKeyframe",
    [
      {
        "space": "world",
        "type": "translate",
        "inturn": True,
        "ui": "fake_distance_ui"
      }
    ]
  ],
  [
    "animation/world/Rotate Together",
    "NLTA_Keyframes.CreateKeyframe",
    [
      {
        "space": "world",
        "type": "rotate",
        "inturn": False,
        "ui": "fake_distance_ui"
      }
    ]
  ],
  [
    "animation/world/Translate Together",
    "NLTA_Keyframes.CreateKeyframe",
    [
      {
        "space": "world",
        "type": "translate",
        "inturn": False,
        "ui": "fake_distance_ui"
      }
    ]
  ],
  [
    "animation/timeline/Delete Keys",
    "NLTA_Keyframes.deleteSenceKeyframe",
    []
  ],
  [
    "animation/timeline/Zoom Range",
    "NLTA_Keyframes.ZoomRangeAnim",
    []
  ],
  [
    "animation/timeline/Delete Attr Keys",
    "NLTA_Keyframes.DeleteAttrKeyframes",
    []
  ],
  [
    "animation/timeline/Fit Range",
    "NLTA_Keyframes.FitRangeAnim",
    []
  ],
  [
    "animation/timeline/Bind Pose",
    "NLTA_Skinning.goToBindPose",
    []
  ],
  [
    "paint/locks/Unlock",
    "NLTA_Skinning.unlock",
    []
  ],
  [
    "paint/locks/Add Unlock",
    "NLTA_Skinning.addUnlock",
    []
  ],
  [
    "paint/locks/Add Down",
    "NLTA_Skinning.addUnlockDown",
    []
  ],
  [
    "paint/locks/Add Up",
    "NLTA_Skinning.addUnlockUp",
    []
  ],
  [
    "paint/locks/Unlock All",
    "NLTA_Skinning.unlockAll",
    []
  ],
  [
    "paint/locks/Unlock 2 Joints",
    "NLTA_Skinning.UnlockTwoJoints",
    []
  ],
  [
    "paint/locks/Unlock Joints",
    "NLTA_Skinning.UnlockInfluenceJoints",
    []
  ],
  [
    "paint/locks/Isolate",
    "NLTA_Skinning.IsolateEffectVertex",
    []
  ],
  [
    "paint/quick/Smooth",
    "NLTA_Brush.smooth",
    [
      "solid"
    ]
  ],
  [
    "paint/quick/Pick Value",
    "NLTA_Brush.pickValue",
    []
  ],
  [
    "paint/quick/Copy Weight",
    "NLTA_Brush.CopyWeight",
    []
  ],
  [
    "paint/quick/Copy Ratio",
    "NLTA_Brush.CopyRatio",
    []
  ],
  [
    "paint/quick/Flood",
    "NLTA_Brush.flood",
    []
  ],
  [
    "paint/helpers/Switch Joint",
    "NLTA_Skinning.switchJoint",
    []
  ],
  [
    "paint/helpers/Switch Brush",
    "NLTA_Brush.SwitchBrush",
    []
  ],
  [
    "paint/helpers/Middle Weight",
    "NLTA_Skinning.setMiddleWeight",
    []
  ],
  [
    "paint/helpers/Prune",
    "NLTA_Skinning.pruneSmallWeights",
    []
  ],
  [
    "paint/helpers/Transfer",
    "NLTA_Skinning_Transfer.CreateUI",
    []
  ],
  [
    "paint/helpers/Eye Lid",
    "NLTA_Skinning_Eyelid.EyelidSurfaceSkinUI",
    []
  ],
  [
    "paint/quick/Graph Skinning",
    "NLTA_GraphSkinning.CreateUI",
    []
  ],
  [
    "weight/increment/Set 0",
    "NLTA_Brush.ReplaceWeight",
    [
      0
    ]
  ],
  [
    "weight/increment/-0.0001",
    "NLTA_Brush.AddWeight",
    [
      -0.0001
    ]
  ],
  [
    "weight/increment/-0.0005",
    "NLTA_Brush.AddWeight",
    [
      -0.0005
    ]
  ],
  [
    "weight/increment/-0.001",
    "NLTA_Brush.AddWeight",
    [
      -0.001
    ]
  ],
  [
    "weight/increment/-0.005",
    "NLTA_Brush.AddWeight",
    [
      -0.005
    ]
  ],
  [
    "weight/increment/-0.01",
    "NLTA_Brush.AddWeight",
    [
      -0.01
    ]
  ],
  [
    "weight/increment/-0.03",
    "NLTA_Brush.AddWeight",
    [
      -0.03
    ]
  ],
  [
    "weight/increment/-0.05",
    "NLTA_Brush.AddWeight",
    [
      -0.05
    ]
  ],
  [
    "weight/increment/-0.1",
    "NLTA_Brush.AddWeight",
    [
      -0.1
    ]
  ],
  [
    "weight/increment/+0.0001",
    "NLTA_Brush.AddWeight",
    [
      0.0001
    ]
  ],
  [
    "weight/increment/+0.0005",
    "NLTA_Brush.AddWeight",
    [
      0.0005
    ]
  ],
  [
    "weight/increment/+0.001",
    "NLTA_Brush.AddWeight",
    [
      0.001
    ]
  ],
  [
    "weight/increment/+0.005",
    "NLTA_Brush.AddWeight",
    [
      0.005
    ]
  ],
  [
    "weight/increment/+0.01",
    "NLTA_Brush.AddWeight",
    [
      0.01
    ]
  ],
  [
    "weight/increment/+0.03",
    "NLTA_Brush.AddWeight",
    [
      0.03
    ]
  ],
  [
    "weight/increment/+0.05",
    "NLTA_Brush.AddWeight",
    [
      0.05
    ]
  ],
  [
    "weight/increment/+0.1",
    "NLTA_Brush.AddWeight",
    [
      0.1
    ]
  ],
  [
    "weight/increment/Add +1",
    "NLTA_Brush.AddWeight",
    [
      1
    ]
  ],
  [
    "skin/bind/Mirror +X",
    "NLTA_Skinning.mirrorSkin",
    [
      "x",
      "+"
    ]
  ],
  [
    "skin/bind/Mirror -X",
    "NLTA_Skinning.mirrorSkin",
    [
      "x",
      "-"
    ]
  ],
  [
    "proxy/proxy/Proxy",
    "NLTA_Proxy.singleProxy",
    []
  ],
  [
    "proxy/proxy/Proxy X",
    "NLTA_Proxy.createProxy",
    [
      "x"
    ]
  ],
  [
    "proxy/proxy/Copy Proxy",
    "NLTA_Proxy.copyProxy",
    []
  ],
  [
    "proxy/proxy/Paste Proxy",
    "NLTA_Proxy.pastProxy",
    []
  ],
  [
    "proxy/proxy/Closest Faces",
    "NLTA_Proxy.SelectClosetFaces",
    []
  ],
  [
    "skin/bind/Copy Skin",
    "NLTA_General.copyJointBind",
    []
  ],
  [
    "files/io/Export Skin",
    "NLTA_Skinning.ExportAllSkin",
    []
  ],
  [
    "files/io/Import Skin",
    "NLTA_Skinning.ImportAllSkin",
    []
  ],
  [
    "skin/bind/Bind Skin",
    "NLTA_General.bindSkin",
    []
  ],
  [
    "skin/bind/Add Joint",
    "NLTA_Skinning.AddJoint",
    []
  ],
  [
    "skin/bind/Remove Joint",
    "NLTA_Skinning.RemoveJoint",
    []
  ],
  [
    "skin/bind/Add Mesh Joint",
    "NLTA_Skinning.AddMeshJoint",
    []
  ],
  [
    "skin/bind/Clear Unused",
    "NLTA_Skinning.removeUnneedJoint",
    []
  ],
  [
    "skin/bind/Clear Skins",
    "NLTA_Skinning.clearSkin",
    []
  ],
  [
    "files/io/Import Existing",
    "NLTA_Skinning.ImportAllSkinExist",
    []
  ],
  [
    "files/io/Export Folder",
    "NLTA_Skinning.ExportFolderSkin",
    []
  ],
  [
    "files/io/Import Folder",
    "NLTA_Skinning.ImportFolderSkin",
    []
  ],
  [
    "files/io/Quick Export",
    "NLTA_Skinning.ExportFolderSkinQuick",
    []
  ],
  [
    "files/io/Quick Import",
    "NLTA_Skinning.ImportFolderSkinQuick",
    []
  ],
  [
    "files/io/Export FBX",
    "NLTA_Skinning.ExportSkinFbx",
    []
  ],
  [
    "files/io/Export Scene",
    "NLTA_Skinning.ObjToNewScene",
    []
  ],
  [
    "mesh/mesh/Component",
    "NLTA_Skinning.component",
    []
  ],
  [
    "mesh/mesh/Load UI",
    "NLTA_Brush.loadUi",
    []
  ],
  [
    "mesh/mesh/Fix Quad",
    "NLTA_Mesh.ShowQuardraw",
    []
  ],
  [
    "mesh/mesh/Fix Initial",
    "NLTA_General.fixInitial",
    []
  ],
  [
    "skin/bind/Clear Weight",
    "NLTA_Skinning.ClearWeight",
    []
  ],
  [
    "skin/sets/Create Set",
    "NLTA_Set.CreateSet",
    []
  ],
  [
    "skin/sets/Next Set",
    "NLTA_Set.NextSet",
    []
  ],
  [
    "skin/sets/Back Set",
    "NLTA_Set.BackSet",
    []
  ],
  [
    "skin/sets/Delete Sets",
    "NLTA_Set.DeleteSets",
    []
  ],
  [
    "skin/max/Check",
    "NLTA_Skinning.checkMaxInfluent",
    []
  ],
  [
    "skin/max/Fix",
    "NLTA_Skinning.fixMaxInfluence",
    []
  ],
  [
    "proxy/curve/Edges to Curve",
    "NLTA_Proxy.EdgesToCurve",
    []
  ],
  [
    "proxy/curve/Verts to Curve",
    "NLTA_Proxy.VertsToCurve",
    []
  ],
  [
    "proxy/curve/Create Circle",
    "NLTA_Proxy.CreateCircle",
    []
  ],
  [
    "proxy/curve/Draw Curve",
    "NLTA_Proxy.DrawCurve",
    []
  ],
  [
    "proxy/curve/Close Curve",
    "NLTA_Proxy.CloseCurve",
    []
  ],
  [
    "proxy/curve/Fit to Mesh",
    "NLTA_Proxy.FitCurveToMesh",
    [
      "surface"
    ]
  ],
  [
    "proxy/curve/Create Loft",
    "NLTA_Proxy.CreateLoft",
    []
  ],
  [
    "proxy/curve/Flip Loft",
    "NLTA_Proxy.FlipLoftNormal",
    []
  ],
  [
    "proxy/curve/Flip Curve",
    "NLTA_Proxy.FlipCurveNormal",
    []
  ],
  [
    "proxy/curve/Rotate CVs +",
    "NLTA_Proxy.RotateCVsPositive",
    []
  ],
  [
    "proxy/curve/Rotate CVs -",
    "NLTA_Proxy.RotateCVsNegative",
    []
  ],
  [
    "proxy/curve/Add Loft Curve",
    "NLTA_Proxy.AddLoftCurve",
    []
  ],
  [
    "proxy/curve/Clear Loft",
    "NLTA_Proxy.ClearAllLoft",
    []
  ],
  [
    "mesh/blend/Import BS",
    "NLTA_BlendShape.ImportBlendShape",
    []
  ],
  [
    "mesh/blend/Export BS",
    "NLTA_BlendShape.ExportBlendShape",
    []
  ],
  [
    "mesh/blend/Export BS XML",
    "NLTA_BlendShape.ExportBSToXML",
    []
  ],
  [
    "mesh/blend/Export Vtx Pos",
    "NLTA_BlendShape.ExportVertexsPosition",
    []
  ],
  [
    "mesh/blend/Import Vtx Pos",
    "NLTA_BlendShape.ImportVertexsPosition",
    []
  ],
  [
    "mesh/blend/Mirror Vtx UV",
    "NLTA_Mesh.MirrorVertexByUv",
    []
  ],
  [
    "mesh/blend/Mirror Vert Pos",
    "NLTA_Mesh.MirrorMeshPosition",
    []
  ]
]


class TaggedModule:
    def __init__(self, name):
        self.name = name

    def __getattr__(self, key):
        def call(*args, **kwargs):
            return args, kwargs
        call.nlta_name = self.name + "." + key
        return call


def catalog():
    tree = ast.parse(BOARD.read_text(encoding="utf-8"))
    definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "command_catalog")
    scope = {"partial": partial}
    exec(compile(ast.Module(body=[definition], type_ignores=[]),
                 str(BOARD), "exec"), scope)
    module_names = {
        "NLTA_Brush", "NLTA_Skinning", "NLTA_General", "NLTA_Keyframes",
        "NLTA_Proxy", "NLTA_Mesh", "NLTA_Skinning_Transfer",
        "NLTA_Skinning_Eyelid", "NLTA_GraphSkinning", "NLTA_Set",
        "NLTA_BlendShape",
    }
    tools = {name: TaggedModule(name) for name in module_names}
    return scope["command_catalog"](tools, "fake_distance_ui")


class LegacyButtonContractTests(unittest.TestCase):
    def test_all_105_buttons_still_call_the_legacy_function_and_arguments(self):
        actual = {}
        for section, _, groups in catalog():
            for group, _, actions in groups:
                for label, fn, _, _ in actions:
                    action = "/".join((section, group, label))
                    self.assertNotIn(action, actual)
                    if isinstance(fn, partial):
                        base = fn.func
                        args = list(fn.args)
                    else:
                        base = fn
                        args = []
                    actual[action] = (base.nlta_name, args)

        self.assertEqual(set(actual), {row[0] for row in LEGACY_CALLBACKS})
        self.assertEqual(len(actual), 105)
        for action, expected_fn, expected_args in LEGACY_CALLBACKS:
            with self.subTest(action=action):
                self.assertEqual(actual[action], (expected_fn, expected_args))


class PaintContextDispatchTests(unittest.TestCase):
    """Every Skinning command returns to Artisan without opening Tool Settings."""

    def load_dispatch(self, start_context):
        tree = ast.parse(BOARD.read_text(encoding="utf-8"))
        board = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                     and node.name == "SkinningBoard")
        method = next(node for node in board.body if isinstance(node, ast.FunctionDef)
                      and node.name == "dispatch")

        class MayaContext:
            context = start_context

            def currentCtx(self):
                return self.context

        cmds = MayaContext()
        namespace = {"cmds": cmds}
        exec(compile(ast.Module(body=[method], type_ignores=[]),
                     str(BOARD), "exec"), namespace)
        return namespace["dispatch"], cmds

    def make_board(self, maya, paint_succeeds=True):
        class Board:
            def __init__(self):
                self.events = []
                self.max_influences = type(
                    "Spin", (), {"value": lambda self: 5})()
                self.influences = type(
                    "Influences", (), {
                        "refresh": lambda inner: self.events.append("refresh")})()

            def activate_paint(self, quiet=False):
                self.events.append("activate_paint_quiet" if quiet else "activate_paint")
                if paint_succeeds:
                    maya.context = "artAttrSkinContext"
                return paint_succeeds

        return Board()

    def test_joint_operations_read_selection_first_and_return_to_skin(self):
        direct_actions = (
            "paint/locks/Unlock",
            "paint/locks/Add Up",
            "paint/locks/Add Down",
            "paint/helpers/Switch Joint",
            "paint/locks/Unlock 2 Joints",
            "paint/locks/Unlock Joints",
            "paint/quick/Copy Weight",
            "paint/quick/Copy Ratio",
            "animation/local/Rotate",
            "animation/timeline/Delete Keys",
            "skin/bind/Add Joint",
            "files/io/Export Skin",
        )
        for action in direct_actions:
            with self.subTest(action=action):
                dispatch, maya = self.load_dispatch("selectSuperContext")
                board = self.make_board(maya)
                dispatch(board, action, lambda: board.events.append("callback"))
                self.assertEqual(board.events[0], "callback")
                self.assertIn("activate_paint_quiet", board.events)
                self.assertEqual(maya.context, "artAttrSkinContext")
                self.assertEqual(board.events.count("callback"), 1)

    def test_brush_and_weight_actions_enter_paint_before_running(self):
        for action in (
            "paint/quick/Smooth", "paint/quick/Flood",
            "paint/quick/Pick Value", "paint/helpers/Switch Brush",
            "paint/helpers/Prune", "paint/locks/Add Unlock",
            "paint/locks/Unlock All", "weight/increment/-0.01",
        ):
            with self.subTest(action=action):
                dispatch, maya = self.load_dispatch("selectSuperContext")
                board = self.make_board(maya)
                dispatch(board, action, lambda: board.events.append("callback"))
                self.assertEqual(board.events[:2], ["activate_paint", "callback"])
                self.assertNotIn("activate_paint_quiet", board.events)
                self.assertEqual(maya.context, "artAttrSkinContext")

    def test_all_actions_restore_skin_when_callback_switches_context(self):
        for action in (
            "paint/quick/Copy Ratio",
            "animation/world/Rotate Together",
            "animation/timeline/Bind Pose",
            "mesh/mesh/Component",
            "skin/max/Fix",
        ):
            with self.subTest(action=action):
                dispatch, maya = self.load_dispatch("artAttrSkinContext")
                board = self.make_board(maya)
                def callback(**kwargs):
                    board.events.append("callback")
                    maya.context = "selectSuperContext"
                dispatch(board, action, callback)
                self.assertEqual(board.events[0], "callback")
                self.assertIn("activate_paint_quiet", board.events)
                self.assertEqual(maya.context, "artAttrSkinContext")

    def test_failed_pre_activation_never_runs_weight_operation(self):
        dispatch, maya = self.load_dispatch("selectSuperContext")
        board = self.make_board(maya, paint_succeeds=False)
        dispatch(board, "weight/increment/-0.1",
                 lambda: board.events.append("callback"))
        self.assertEqual(board.events, ["activate_paint"])

    def test_callback_error_still_restores_skin_context(self):
        dispatch, maya = self.load_dispatch("selectSuperContext")
        board = self.make_board(maya)
        def broken():
            board.events.append("callback")
            raise RuntimeError("test")
        with self.assertRaisesRegex(RuntimeError, "test"):
            dispatch(board, "paint/quick/Copy Weight", broken)
        self.assertEqual(board.events, ["callback", "activate_paint_quiet"])
        self.assertEqual(maya.context, "artAttrSkinContext")

    def test_max_influence_commands_pass_current_field_value(self):
        for action, expected in (
            ("skin/max/Check", {"maxValue": 5}),
            ("skin/max/Fix", {"maxInfluence": 5}),
        ):
            dispatch, maya = self.load_dispatch("selectSuperContext")
            board = self.make_board(maya)
            results = []
            dispatch(board, action, lambda **kw: results.append(kw))
            self.assertEqual(results, [expected])
            self.assertEqual(board.events, ["activate_paint_quiet"])

    def test_activation_uses_artisan_without_opening_native_settings(self):
        source = BOARD.read_text(encoding="utf-8")
        board = next(node for node in ast.parse(source).body
                     if isinstance(node, ast.ClassDef)
                     and node.name == "SkinningBoard")
        activate = next(node for node in board.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "activate_paint")
        implementation = ast.get_source_segment(source, activate)
        self.assertIn('"EnsurePaintContext"', implementation)
        self.assertNotIn("ArtPaintSkinWeightsToolOptions", implementation)
        self.assertNotIn("toolPropertyWindow", implementation)


if __name__ == "__main__":
    unittest.main()
