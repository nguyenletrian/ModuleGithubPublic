"""Pure logic tests for Maya Skinning Board's influence table (no Maya needed)."""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

BOARD = Path(__file__).resolve().parents[1] / "UIs/SkinningTools/NLTA_Skinning_CommandBoard.py"


class FakeCmds:
    def __init__(self):
        self.influences = ["|Rig|Spine_JNT", "|Rig|Arm_JNT", "|Rig|Extra_JNT"]
        self.locks = {"|Rig|Spine_JNT": True, "|Rig|Arm_JNT": False,
                      "|Rig|Extra_JNT": False}
        self.warning_messages = []
        self.selected = ["|Body|Mesh.vtx[11]"]
        self.selected_joint = None
        self.paint_context_exists = True
        self.active_influence = "|Rig|Spine_JNT"
        self.source_joint = "|Rig|Spine_JNT"
        self.paint_edits = []
        self.connections = []

    def ls(self, *args, **kwargs):
        if kwargs.get("selection"):
            return self.selected
        if kwargs.get("type") == "joint" and args:
            name = args[0]
            return [joint for joint in self.influences
                    if joint == name or joint.rsplit("|", 1)[-1] == name]
        return list(args)

    def objExists(self, name):
        if name == "skin1":
            return True
        if name.endswith(".liw"):
            return name[:-4] in self.locks
        return name in self.influences or name in ("|Body|Mesh", "|Body|UnboundMesh")

    def skinCluster(self, skin, **kwargs):
        assert skin == "skin1" and kwargs.get("query") and kwargs.get("influence")
        return self.influences

    def nodeType(self, joint):
        if joint in ("|Body|Mesh", "|Body|UnboundMesh"):
            return "transform"
        if joint.endswith("|Shape"):
            return "mesh"
        return "joint"

    def listRelatives(self, node, **kwargs):
        return [node + "|Shape"] if kwargs.get("shapes") else []

    def getAttr(self, attribute):
        return self.locks[attribute[:-4]]

    def setAttr(self, attribute, value):
        self.locks[attribute[:-4]] = bool(value)

    def warning(self, message):
        self.warning_messages.append(message)

    def artAttrSkinPaintCtx(self, context, **kwargs):
        assert context == "artAttrSkinContext"
        if kwargs.get("exists"):
            return self.paint_context_exists
        if kwargs.get("query") and kwargs.get("influence"):
            return self.active_influence
        if kwargs.get("edit"):
            joint = kwargs.get("influence")
            self.paint_edits.append(joint)
            self.active_influence = joint
            return None
        raise AssertionError("Unexpected context operation")

    def connectionInfo(self, attribute, **kwargs):
        assert attribute == "skin1.paintTrans"
        return self.source_joint + ".message" if self.source_joint else ""

    def connectAttr(self, source, destination, **kwargs):
        assert destination == "skin1.paintTrans" and kwargs.get("force")
        self.source_joint = source.rsplit(".", 1)[0]
        self.connections.append((source, destination))



def load_logic(cmds):
    parsed = ast.parse(BOARD.read_text(encoding="utf-8"))
    names = ("_skin_from_selection", "_selected_unskinned_mesh",
             "_skin_influence_rows", "_influence_hierarchy",
             "_resolve_skin_influence", "_active_skin_paint_influence",
             "_activate_skin_paint_influence", "_set_influence_locks")
    nodes = [node for node in parsed.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    globals_ = {"cmds": cmds}
    exec(compile(ast.Module(body=nodes, type_ignores=[]),
                 str(BOARD), "exec"), globals_)
    return globals_


class InfluenceLogicTests(unittest.TestCase):
    def setUp(self):
        self.cmds = FakeCmds()
        self.logic = load_logic(self.cmds)

    def test_reads_only_bound_joint_lock_attributes(self):
        rows = self.logic["_skin_influence_rows"]("skin1")
        self.assertEqual(rows, [
            ("|Rig|Spine_JNT", True),
            ("|Rig|Arm_JNT", False),
            ("|Rig|Extra_JNT", False),
        ])
        self.cmds.locks.pop("|Rig|Extra_JNT")
        self.assertEqual(self.logic["_skin_influence_rows"]("skin1")[-1],
                         ("|Rig|Extra_JNT", None))

    def test_skin_influence_hierarchy_skips_unbound_ancestors(self):
        hierarchy = self.logic["_influence_hierarchy"]
        rows = [
            ("|Rig|Root|Spine|Shoulder|Arm", False),
            ("|Rig|Root", True),
            ("|Rig|Root|Spine|Shoulder|Arm|Hand", False),
            ("|Rig|Other|Finger", True),
            ("|Rig|Root|Spine", False),
        ]
        self.assertEqual(hierarchy(rows), {
            "|Rig|Root|Spine|Shoulder|Arm": "|Rig|Root|Spine",
            "|Rig|Root": None,
            "|Rig|Root|Spine|Shoulder|Arm|Hand":
                "|Rig|Root|Spine|Shoulder|Arm",
            "|Rig|Other|Finger": None,
            "|Rig|Root|Spine": "|Rig|Root",
        })
        self.assertEqual(hierarchy([("UnqualifiedJoint", False)]),
                         {"UnqualifiedJoint": None})

    def test_hierarchy_not_confused_by_similarly_named_nodes(self):
        hierarchy = self.logic["_influence_hierarchy"]
        rows = [
            ("|Character|Left|Arm", True),
            ("|Character|Right|Arm", False),
            ("|Character|Left", False),
            ("|OtherCharacter|Left", True),
        ]
        parents = hierarchy(rows)
        self.assertEqual(parents["|Character|Left|Arm"], "|Character|Left")
        self.assertIsNone(parents["|Character|Right|Arm"])
        self.assertIsNone(parents["|OtherCharacter|Left"])

    def test_reverse_all_and_lock_unlock_selected_only(self):
        change = self.logic["_set_influence_locks"]
        self.assertEqual(change("skin1", self.cmds.influences, "reverse"), 3)
        self.assertEqual(self.cmds.locks, {
            "|Rig|Spine_JNT": False, "|Rig|Arm_JNT": True,
            "|Rig|Extra_JNT": True})
        self.assertEqual(change("skin1", ["|Rig|Spine_JNT"], "lock"), 1)
        self.assertTrue(self.cmds.locks["|Rig|Spine_JNT"])
        self.assertEqual(change("skin1", ["|Rig|Arm_JNT"], "unlock"), 1)
        self.assertFalse(self.cmds.locks["|Rig|Arm_JNT"])

    def test_deduplicates_selection_and_never_touches_non_skin_joint(self):
        change = self.logic["_set_influence_locks"]
        self.assertEqual(change("skin1", ["|Rig|Arm_JNT", "|Rig|Arm_JNT",
                                         "|Other|NotBound_JNT"], "reverse"), 1)
        self.assertTrue(self.cmds.locks["|Rig|Arm_JNT"])
        with self.assertRaises(ValueError):
            change("skin1", self.cmds.influences, "invalid")

    def test_selected_component_resolves_its_bound_mesh(self):
        backend = types.ModuleType("NLTA_Skinning")
        def get_data(node):
            if node == "|Body|Mesh":
                return {"skinCluster": "skin1", "mesh": "|Body|Mesh",
                        "joints": list(self.cmds.influences)}
            return {"skinCluster": None, "mesh": None, "joints": []}
        backend.GetSkinData = get_data
        with mock.patch.dict(sys.modules, {"NLTA_Skinning": backend}):
            data = self.logic["_skin_from_selection"]()
        self.assertEqual(data["skinCluster"], "skin1")

    def test_unbound_mesh_is_distinct_from_joint_selection(self):
        check = self.logic["_selected_unskinned_mesh"]
        self.cmds.selected = ["|Body|UnboundMesh"]
        self.assertTrue(check())
        self.cmds.selected = ["|Rig|Arm_JNT"]
        self.assertFalse(check())

    def test_paint_context_selection_resolves_to_bound_dag_joint(self):
        self.cmds.active_influence = "Arm_JNT"
        active = self.logic["_active_skin_paint_influence"]("skin1")
        self.assertEqual(active, "|Rig|Arm_JNT")

    def test_native_paint_influence_falls_back_to_skin_painttrans(self):
        self.cmds.paint_context_exists = False
        self.cmds.source_joint = "|Rig|Extra_JNT"
        self.assertEqual(self.logic["_active_skin_paint_influence"]("skin1"),
                         "|Rig|Extra_JNT")

    def test_ambiguous_joint_name_is_never_mapped_to_wrong_skin_influence(self):
        self.cmds.influences.append("|Another|Arm_JNT")
        self.cmds.locks["|Another|Arm_JNT"] = False
        self.assertIsNone(self.logic["_resolve_skin_influence"](
            "skin1", "Arm_JNT"))
        self.assertEqual(self.logic["_resolve_skin_influence"](
            "skin1", "|Rig|Arm_JNT"), "|Rig|Arm_JNT")
        self.assertIsNone(self.logic["_resolve_skin_influence"](
            "skin1", "Unbound_JNT"))

    def test_list_selection_sets_paint_joint_without_selecting_scene_joint(self):
        backend = types.ModuleType("NLTA_Skinning")
        ensure_calls = []
        backend.EnsurePaintContext = lambda mesh: (
            ensure_calls.append(mesh) or True)
        before = list(self.cmds.selected)
        with mock.patch.dict(sys.modules, {"NLTA_Skinning": backend}):
            result = self.logic["_activate_skin_paint_influence"](
                "skin1", "|Body|Mesh", "|Rig|Arm_JNT")
        self.assertTrue(result)
        self.assertEqual(ensure_calls, ["|Body|Mesh"])
        self.assertEqual(self.cmds.paint_edits, ["|Rig|Arm_JNT"])
        self.assertEqual(self.cmds.source_joint, "|Rig|Arm_JNT")
        self.assertEqual(self.cmds.selected, before)

    def test_unbound_joint_does_not_edit_skin_paint_context(self):
        backend = types.ModuleType("NLTA_Skinning")
        backend.EnsurePaintContext = lambda mesh: True
        with mock.patch.dict(sys.modules, {"NLTA_Skinning": backend}):
            result = self.logic["_activate_skin_paint_influence"](
                "skin1", "|Body|Mesh", "|Unbound|Other_JNT")
        self.assertFalse(result)
        self.assertEqual(self.cmds.paint_edits, [])
        self.assertEqual(self.cmds.source_joint, "|Rig|Spine_JNT")

    def test_board_has_joint_column_and_maya_scriptjob_lifecycle(self):
        text = BOARD.read_text(encoding="utf-8")
        for expected in (
                "class InfluencePanel(QtWidgets.QFrame):",
                'self.workspace = QtWidgets.QSplitter(QtCore.Qt.Horizontal)',
                'self.filter_box.addItems(("All", "Locked", "Unlocked"))',
                'self.tree.setRootIsDecorated(True)',
                'self.tree.setHeaderLabels(("Influence joint", "Lock"))',
                'QtWidgets.QTreeWidgetItem(',
                '[joint.rsplit("|", 1)[-1], ""]',
                'self._items[parent].addChild(item)',
                'self.tree.expandToDepth(1)',
                'self._parents = _influence_hierarchy(self._rows)',
                '"SkinningInfluenceTree"',
                '"Lock All"', '"Unlock All"', '"Reverse All"',
                '"Lock"', '"Unlock"', '"Reverse"',
                'self.tree.itemChanged.connect(self.change_item_lock)',
                'self.tree.itemDoubleClicked.connect(self.select_joint)',
                'self.tree.currentItemChanged.connect(self.change_active_influence)',
                'self._live_timer.setInterval(300)',
                'self._live_timer.timeout.connect(self.sync_live)',
                'self._live_timer.start()',
                'self._live_timer.stop()',
                'self.tree.blockSignals(True)',
                'self.tree.setCurrentItem(item)',
                'def sync_from_paint(self):',
                'def sync_live(self):',
                'def sync_lock_states(self):',
                'event=[event, callback]',
                "def reset_scene(self):",
                "self.influences.refresh()",
                "self.influences.deactivate()",
                '("SelectionChanged", "SceneOpened", "NewSceneOpened")',
                ):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
