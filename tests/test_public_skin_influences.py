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

    def ls(self, *args, **kwargs):
        if kwargs.get("selection"):
            return self.selected
        return list(args)

    def objExists(self, name):
        if name == "skin1":
            return True
        if name.endswith(".liw"):
            return name[:-4] in self.locks
        return name in self.influences

    def skinCluster(self, skin, **kwargs):
        assert skin == "skin1" and kwargs.get("query") and kwargs.get("influence")
        return self.influences

    def nodeType(self, joint):
        return "joint"

    def getAttr(self, attribute):
        return self.locks[attribute[:-4]]

    def setAttr(self, attribute, value):
        self.locks[attribute[:-4]] = bool(value)

    def warning(self, message):
        self.warning_messages.append(message)


def load_logic(cmds):
    parsed = ast.parse(BOARD.read_text(encoding="utf-8"))
    names = ("_skin_from_selection", "_skin_influence_rows", "_set_influence_locks")
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

    def test_board_has_joint_column_and_maya_scriptjob_lifecycle(self):
        text = BOARD.read_text(encoding="utf-8")
        for expected in (
                "class InfluencePanel(QtWidgets.QFrame):",
                'self.workspace = QtWidgets.QSplitter(QtCore.Qt.Horizontal)',
                'self.filter_box.addItems(("All", "Locked", "Unlocked"))',
                '"SkinningInfluenceTree"',
                '"Lock All"', '"Unlock All"', '"Reverse All"',
                '"Lock"', '"Unlock"', '"Reverse"',
                'self.tree.itemChanged.connect(self.change_item_lock)',
                'self.tree.itemDoubleClicked.connect(self.select_joint)',
                'event=[event, self.on_selection_changed]',
                "self.influences.deactivate()",
                '("SelectionChanged", "SceneOpened", "NewSceneOpened")',
                ):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
