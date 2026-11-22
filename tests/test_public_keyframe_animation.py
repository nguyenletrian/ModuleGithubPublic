"""Offline Maya regression for temporary Animation & Poses control tests."""
import ast
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "Libs/NLTA_Keyframes.py"

ROOT = "|Rig|Root_CTRL"
ARM = "|Rig|Root_CTRL|Arm_CTRL"
MESH = "|Rig|Body_Mesh"
JOINT = "|Rig|joint1"


class FakeCmds:
    def __init__(self):
        self.type_by_node = {
            ROOT: "transform", ARM: "transform",
            MESH: "transform", JOINT: "joint"
        }
        self.parent_by_node = {ARM: ROOT, ROOT: "|Rig", JOINT: "|Rig"}
        self.selected = [ROOT, ARM]
        self.ctx = "selectSuperContext"
        self.time = 17.0
        self.distance = 6.0
        self.attrs = {}
        self.locked = set()
        self.connected = set()
        self.constraints = {}
        self.key_values = {}
        self.playback = {}
        self.warnings = []
        self.deleted = []
        self.cut_keys = []
        self.create_calls = []
        self.match_calls = []
        self.counter = 0
        self.skin_feedback_changes = 0
        for node in (ROOT, ARM, JOINT):
            for axis in "xyz":
                for prefix in "rt":
                    self.attrs[node + "." + prefix + axis] = 0.0

    def ls(self, *args, **kwargs):
        if kwargs.get("selection"):
            return list(self.selected)
        if args and args[0] == "*.NLTA_TestAnimSource":
            return [name for name in self.type_by_node
                    if name + ".NLTA_TestAnimSource" in self.attrs]
        if args and args[0] in ("*.NLTA_worldKeyframe", "*.NLTA_SourceJoint"):
            return []
        if args and isinstance(args[0], str) and args[0] in self.type_by_node:
            return [args[0]]
        return list(args)

    def objExists(self, name):
        return name in self.type_by_node or name in self.constraints or name in self.attrs

    def nodeType(self, node):
        return self.type_by_node[node]

    def listRelatives(self, node, **kwargs):
        if kwargs.get("shapes") and kwargs.get("type") == "mesh":
            return [node + "Shape"] if node == MESH else []
        if kwargs.get("parent"):
            return [self.parent_by_node[node]] if node in self.parent_by_node else []
        if kwargs.get("allDescendents"):
            return []
        return []

    def currentCtx(self):
        return self.ctx

    def currentTime(self, *args, **kwargs):
        if kwargs.get("query"):
            return self.time
        self.time = args[0]

    def intSliderGrp(self, node, **kwargs):
        assert kwargs == {"query": True, "value": True}
        return self.distance

    def getAttr(self, attr, **kwargs):
        if kwargs.get("lock"):
            return attr in self.locked
        return self.attrs[attr]

    def listConnections(self, node, **kwargs):
        if kwargs.get("type") == "parentConstraint":
            return []
        return ["otherNode.output"] if node in self.connected else []

    def createNode(self, node_type, **kwargs):
        assert node_type == "transform"
        self.counter += 1
        parent = kwargs.get("parent")
        node = ((parent + "|") if parent else "|") + kwargs["name"] + str(self.counter)
        self.type_by_node[node] = node_type
        self.parent_by_node[node] = parent
        self.create_calls.append((node, parent))
        for axis in "xyz":
            for prefix in "rt":
                self.attrs[node + "." + prefix + axis] = 0.0
        return node

    def matchTransform(self, driver, target, **kwargs):
        self.match_calls.append((driver, target, kwargs))

    def orientConstraint(self, driver, control, **kwargs):
        return self._constraint("orientConstraint", driver, control, kwargs)

    def pointConstraint(self, driver, control, **kwargs):
        return self._constraint("pointConstraint", driver, control, kwargs)

    def _constraint(self, kind, driver, target, kwargs):
        assert kwargs.get("maintainOffset") is True
        assert driver in self.type_by_node
        self.counter += 1
        name = "|constraint" + str(self.counter)
        self.constraints[name] = (kind, driver, target, kwargs)
        return [name]

    def addAttr(self, node, **kwargs):
        assert kwargs.get("dataType") == "string"
        self.attrs[node + "." + kwargs["longName"]] = ""

    def setAttr(self, attr, value, **kwargs):
        self.attrs[attr] = value

    def setKeyframe(self, node, **kwargs):
        assert node in self.type_by_node
        key = (node, kwargs["attribute"])
        self.key_values.setdefault(key, {})[float(kwargs["time"])] = kwargs["value"]

    def playbackOptions(self, **kwargs):
        self.playback.update(kwargs)

    def keyframe(self, nodes, **kwargs):
        assert kwargs.get("query") and kwargs.get("timeChange")
        if isinstance(nodes, str):
            nodes = [nodes]
        return [t for (node, attr), times in self.key_values.items()
                if node in nodes for t in times]

    def select(self, nodes=None, **kwargs):
        if kwargs.get("clear"):
            self.selected = []
        elif isinstance(nodes, list):
            self.selected = list(nodes)
        elif nodes is not None:
            self.selected = [nodes]

    def warning(self, text):
        self.warnings.append(text)

    def delete(self, node):
        if node in self.constraints:
            del self.constraints[node]
        self.type_by_node.pop(node, None)
        self.parent_by_node.pop(node, None)
        for attr in list(self.attrs):
            if attr.startswith(node + "."):
                del self.attrs[attr]
        for key in list(self.key_values):
            if key[0] == node:
                del self.key_values[key]
        self.deleted.append(node)

    def cutKey(self, controls, **kwargs):
        self.cut_keys.append((controls, kwargs))


def load_logic(cmds):
    parsed = ast.parse(SOURCE.read_text(encoding="utf-8"))
    assert ast.get_docstring(parsed)
    assignments = [node for node in parsed.body if isinstance(node, ast.Assign)]
    defs = [node for node in parsed.body if isinstance(node, ast.FunctionDef)]
    scope = {"cmds": cmds, "json": json}
    exec(compile(ast.Module(body=assignments + defs, type_ignores=[]),
                 str(SOURCE), "exec"), scope)
    return scope


class AnimationControlTests(unittest.TestCase):
    def setUp(self):
        self.cmds = FakeCmds()
        self.logic = load_logic(self.cmds)

    def create(self, space="local", kind="rotate", serial=True):
        return self.logic["CreateKeyframe"]({
            "space": space, "type": kind,
            "inturn": serial, "ui": "mockDistance"
        })

    def test_sequential_parent_child_controls_keep_selection_and_source_keys(self):
        before = list(self.cmds.selected)
        drivers = self.create(serial=True)
        self.assertEqual(len(drivers), 2)
        self.assertEqual(self.cmds.selected, before)
        self.assertEqual(self.cmds.time, 17.0)
        self.assertEqual(len(self.cmds.constraints), 2)
        self.assertTrue(all(x[0] == "orientConstraint"
                            for x in self.cmds.constraints.values()))
        self.assertEqual(self.cmds.parent_by_node[drivers[1]], ROOT)
        self.assertEqual(self.cmds.playback["min"], 0.0)
        self.assertEqual(self.cmds.playback["max"], 917.0)
        first = set(self.cmds.key_values[(drivers[0], "rx")])
        second = set(self.cmds.key_values[(drivers[1], "rx")])
        self.assertIn(47.0, first)
        self.assertIn(497.0, second)
        self.assertNotIn((ARM, "rx"), self.cmds.key_values)
        self.assertNotIn((ROOT, "rx"), self.cmds.key_values)

    def test_together_world_translate_has_world_aligned_independent_drivers(self):
        drivers = self.create(space="world", kind="translate", serial=False)
        self.assertEqual(len(drivers), 2)
        self.assertEqual(self.cmds.playback["max"], 467.0)
        self.assertEqual([self.cmds.parent_by_node[d] for d in drivers],
                         [None, None])
        self.assertTrue(all(x[0] == "pointConstraint"
                            for x in self.cmds.constraints.values()))
        self.assertTrue(all(k[2] == {"position": True}
                            for k in self.cmds.match_calls))
        a = self.cmds.key_values[(drivers[0], "tx")]
        b = self.cmds.key_values[(drivers[1], "tx")]
        self.assertEqual(a[47.0], 0.0)
        self.assertEqual(a[77.0], -6.0)
        self.assertEqual(a[137.0], 6.0)
        self.assertEqual(b[77.0], -6.0)

    def test_exact_legacy_xyz_key_frames_at_zero_and_return_to_frame_zero(self):
        self.cmds.currentTime(0)
        self.cmds.selected = [ARM]
        driver = self.create(kind="rotate", serial=True)[0]
        self.assertEqual(self.cmds.time, 0)
        expected = {
            "rx": [0, 30, 60, 90, 120, 150, 450],
            "ry": [0, 180, 210, 240, 270, 300, 450],
            "rz": [0, 330, 360, 390, 420, 450],
        }
        for attr, frames in expected.items():
            with self.subTest(axis=attr):
                actual = self.cmds.key_values[(driver, attr)]
                self.assertEqual(sorted(actual), frames)
                self.assertEqual(
                    [actual[t] for t in frames[1:-1]],
                    [0, -90, 0, 90, 0])
        self.assertEqual(self.cmds.playback["min"], 0)
        self.assertEqual(self.cmds.playback["max"], 450)
        self.assertEqual(self.cmds.selected, [ARM])

    def test_serial_two_controls_start_second_at_480_after_first_xyz_ends(self):
        self.cmds.currentTime(0)
        a, b = self.create(kind="rotate", serial=True)
        first = self.cmds.key_values[(a, "rx")]
        second = self.cmds.key_values[(b, "rx")]
        self.assertEqual([first[x] for x in (30, 60, 90, 120, 150)],
                         [0, -90, 0, 90, 0])
        self.assertEqual([second[x] for x in (480, 510, 540, 570, 600)],
                         [0, -90, 0, 90, 0])
        self.assertEqual(sorted(self.cmds.key_values[(b, "rz")]),
                         [0, 780, 810, 840, 870, 900])
        self.assertEqual(self.cmds.playback["max"], 900)
        self.assertEqual(self.cmds.time, 0)

    def test_together_controls_both_start_first_axis_at_30(self):
        self.cmds.currentTime(0)
        a, b = self.create(kind="rotate", serial=False)
        for driver in (a, b):
            self.assertEqual(
                [self.cmds.key_values[(driver, "rx")][t]
                 for t in (30, 60, 90, 120, 150)],
                [0, -90, 0, 90, 0])
        self.assertEqual(self.cmds.playback["max"], 450)
        self.assertEqual(self.cmds.time, 0)

    def test_locked_early_axes_preserve_original_z_slot_timing(self):
        self.cmds.currentTime(0)
        self.cmds.selected = [ARM]
        self.cmds.locked.update({ARM + ".rx", ARM + ".ry"})
        driver = self.create()[0]
        self.assertEqual(
            sorted(self.cmds.key_values[(driver, "rz")]),
            [0, 330, 360, 390, 420, 450])
        self.assertNotIn((driver, "rx"), self.cmds.key_values)
        self.assertNotIn((driver, "ry"), self.cmds.key_values)
        self.assertEqual(self.cmds.time, 0)

    def test_paint_skin_mode_uses_active_influence_and_keeps_mesh_selected(self):
        self.cmds.ctx = "artAttrSkinContext"
        self.cmds.selected = [MESH + ".vtx[10]"]
        backend = types.ModuleType("NLTA_Skinning")
        backend.EnsureSkinSession = lambda warn=False: {
            "skinCluster": "skinCluster1", "mesh": MESH
        }
        backend.GetActivePaintJoint = lambda skin: JOINT
        with mock.patch.dict(sys.modules, {"NLTA_Skinning": backend}):
            drivers = self.create(space="local", kind="rotate")
        self.assertEqual(len(drivers), 1)
        self.assertEqual(self.cmds.selected, [MESH + ".vtx[10]"])
        self.assertEqual(self.cmds.ctx, "artAttrSkinContext")
        self.assertEqual(list(self.cmds.constraints.values())[0][2], JOINT)
        self.assertEqual(self.cmds.time, 17.0)

    def test_paint_mode_with_explicit_control_prefers_control_over_joint(self):
        self.cmds.ctx = "artAttrSkinContext"
        self.cmds.selected = [ARM]
        drivers = self.create()
        self.assertEqual(len(drivers), 1)
        self.assertEqual(list(self.cmds.constraints.values())[0][2], ARM)

    def test_locked_and_already_driven_channels_are_not_overwritten(self):
        self.cmds.selected = [ARM]
        self.cmds.locked.add(ARM + ".rx")
        self.cmds.connected.add(ARM + ".ry")
        drivers = self.create()
        self.assertEqual(len(drivers), 1)
        self.assertEqual(
            list(self.cmds.constraints.values())[0][3]["skip"], ["x", "y"])
        self.assertEqual({attr for (node, attr) in self.cmds.key_values
                          if node == drivers[0]}, {"rz"})

    def test_all_channels_driven_skips_target_without_overwriting_rig(self):
        self.cmds.selected = [ARM]
        for ax in "xyz":
            self.cmds.connected.add(ARM + ".r" + ax)
        self.assertEqual(self.create(), [])
        self.assertEqual(self.cmds.constraints, {})
        self.assertTrue(any("no free rotate channels" in m
                            for m in self.cmds.warnings))

    def test_recreate_test_replaces_old_driver_instead_of_stacking_constraints(self):
        self.cmds.selected = [ARM]
        first = self.create()[0]
        second = self.create()[0]
        self.assertNotEqual(first, second)
        self.assertIn(first, self.cmds.deleted)
        self.assertEqual(len(self.cmds.constraints), 1)
        self.assertEqual(len(self.logic["_test_drivers"]()), 1)

    def test_delete_test_does_not_cut_existing_rig_animation(self):
        self.create()
        self.assertEqual(self.logic["deleteSenceKeyframe"](), 2)
        self.assertEqual(self.cmds.constraints, {})
        self.assertEqual(self.logic["_test_drivers"](), [])
        self.assertEqual(self.cmds.cut_keys, [])
        self.assertEqual(self.cmds.selected, [ROOT, ARM])

    def test_delete_keys_restores_original_parent_child_pose_from_mid_animation(self):
        originals = {
            ROOT: {"rx": 18.25, "ry": -21.0, "rz": 5.0},
            ARM: {"rx": -6.0, "ry": 4.0, "rz": 12.75},
        }
        for ctrl, channels in originals.items():
            for channel, value in channels.items():
                self.cmds.attrs[ctrl + "." + channel] = value
        drivers = self.create()
        self.assertEqual(len(drivers), 2)
        # A frame in the middle of an animated test, not its neutral pose.
        self.cmds.currentTime(221)
        for ctrl in originals:
            for channel in originals[ctrl]:
                self.cmds.attrs[ctrl + "." + channel] = 91.0

        count = self.logic["deleteSenceKeyframe"]()
        self.assertEqual(count, 2)
        self.assertEqual(self.cmds.time, 17.0)
        for ctrl, channels in originals.items():
            for channel, original in channels.items():
                self.assertEqual(self.cmds.attrs[ctrl + "." + channel], original)
        self.assertEqual(self.cmds.constraints, {})
        self.assertEqual(self.cmds.selected, [ROOT, ARM])
        self.assertEqual(self.cmds.cut_keys, [])
        self.assertEqual(self.logic["_test_drivers"](), [])

    def test_translate_delete_restores_nonzero_local_position_only(self):
        self.cmds.selected = [ARM]
        starting = {"tx": 8.0, "ty": -2.5, "tz": 3.25}
        for channel, value in starting.items():
            self.cmds.attrs[ARM + "." + channel] = value
        self.cmds.attrs[ARM + ".ry"] = 32.0
        self.create(space="world", kind="translate")
        self.cmds.currentTime(183)
        for channel in starting:
            self.cmds.attrs[ARM + "." + channel] = 999.0
        self.logic["deleteSenceKeyframe"]()
        for channel, value in starting.items():
            self.assertEqual(self.cmds.attrs[ARM + "." + channel], value)
        self.assertEqual(self.cmds.attrs[ARM + ".ry"], 32.0)
        self.assertEqual(self.cmds.time, 17.0)

    def test_pose_snapshot_persists_on_driver_across_session_reload(self):
        self.cmds.selected = [ARM]
        self.cmds.attrs[ARM + ".rz"] = 42.0
        drivers = self.create()
        self.assertEqual(len(drivers), 1)
        self.assertIn(drivers[0] + ".NLTA_TestAnimPose", self.cmds.attrs)
        for channel in "xyz":
            self.cmds.attrs[ARM + ".r" + channel] = 90.0
        self.cmds.currentTime(277)
        # Simulate reimport/reload of the module and loss of in-memory state.
        reloaded = load_logic(self.cmds)
        self.assertEqual(reloaded["session"]["drivers"], [])
        self.assertEqual(reloaded["deleteSenceKeyframe"](), 1)
        self.assertEqual(self.cmds.attrs[ARM + ".rz"], 42.0)
        self.assertEqual(self.cmds.time, 17.0)

    def test_delete_only_restores_its_channels_not_later_external_connections(self):
        self.cmds.selected = [ARM]
        self.cmds.attrs[ARM + ".rx"] = 15.0
        self.create()
        self.cmds.attrs[ARM + ".rx"] = 67.0
        # A separate system has taken over this channel after the test began.
        self.cmds.connected.add(ARM + ".rx")
        self.logic["deleteSenceKeyframe"]()
        self.assertEqual(self.cmds.attrs[ARM + ".rx"], 67.0)
        self.assertEqual(self.cmds.constraints, {})
        self.assertEqual(self.cmds.cut_keys, [])

    def test_delete_attr_keys_on_test_restores_original_pose(self):
        self.cmds.selected = [ARM]
        self.cmds.attrs[ARM + ".ry"] = -13.5
        self.create()
        self.cmds.attrs[ARM + ".ry"] = 71.0
        self.logic["DeleteAttrKeyframes"]()
        self.assertEqual(self.cmds.attrs[ARM + ".ry"], -13.5)
        self.assertEqual(self.logic["_test_drivers"](), [])

    def test_delete_without_test_keeps_current_frame_and_control_pose(self):
        self.cmds.currentTime(221)
        self.cmds.attrs[ARM + ".rx"] = 27.0
        self.assertEqual(self.logic["deleteSenceKeyframe"](), 0)
        self.assertEqual(self.cmds.time, 221)
        self.assertEqual(self.cmds.attrs[ARM + ".rx"], 27.0)

    def test_zoom_and_fit_scope_to_test_driver_not_unrelated_scene_curve(self):
        self.cmds.selected = [ARM]
        self.create()
        self.logic["FitRangeAnim"]()
        self.assertEqual(self.cmds.playback["min"], 17.0)
        self.assertEqual(self.cmds.playback["max"], 467.0)
        self.cmds.currentTime(53.0)
        self.logic["ZoomRangeAnim"]()
        self.assertEqual(self.cmds.playback["min"], 47.0)
        self.assertEqual(self.cmds.playback["max"], 77.0)

    def test_partial_key_failure_cleans_only_failed_driver_and_restores_selection(self):
        original = self.cmds.setKeyframe

        def sometimes_fail(node, **kwargs):
            if "Arm_CTRL" in node and kwargs["attribute"] == "ry":
                raise RuntimeError("simulated keying failure")
            return original(node, **kwargs)

        self.cmds.setKeyframe = sometimes_fail
        drivers = self.create()
        self.assertEqual(len(drivers), 1)
        self.assertEqual(len(self.cmds.constraints), 1)
        self.assertEqual(self.cmds.selected, [ROOT, ARM])
        self.assertTrue(any("Cannot test" in m for m in self.cmds.warnings))
        self.assertEqual(len(self.logic["_test_drivers"]()), 1)

    def test_large_paint_vertex_selection_is_kept_as_component_range(self):
        self.cmds.ctx = "artAttrSkinContext"
        self.cmds.selected = [MESH + ".vtx[1:8000]"]
        backend = types.ModuleType("NLTA_Skinning")
        backend.EnsureSkinSession = lambda warn=False: {
            "skinCluster": "skinCluster1", "mesh": MESH
        }
        backend.GetActivePaintJoint = lambda skin: JOINT
        with mock.patch.dict(sys.modules, {"NLTA_Skinning": backend}):
            drivers = self.create()
        self.assertEqual(len(drivers), 1)
        self.assertEqual(self.cmds.selected, [MESH + ".vtx[1:8000]"])

    def test_helper_creation_does_not_select_new_maya_nodes(self):
        self.create()
        self.assertEqual(self.cmds.selected, [ROOT, ARM])
        self.assertTrue(self.cmds.create_calls)
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('"skipSelect": True', source)

    def test_delete_attr_keys_on_generated_test_removes_driver_not_control(self):
        self.cmds.selected = [ARM]
        self.create()
        self.logic["DeleteAttrKeyframes"]()
        self.assertEqual(self.logic["_test_drivers"](), [])
        self.assertEqual(self.cmds.cut_keys, [])


if __name__ == "__main__":
    unittest.main()
