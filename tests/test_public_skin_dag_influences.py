"""Offline regression for Maya Skinning joint names shared by different DAG branches."""
import ast
from pathlib import Path
import types
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "Libs/NLTA_Skinning.py"
ROOT = "|Rig|joint1"
CHILD = "|Rig|joint1|joint2"
OTHER = "|OtherRig|joint2"
EXTRA = "|Rig|joint1|joint3"


class FakeDag:
    def __init__(self, path):
        self.path = path

    def fullPathName(self):
        return self.path

    def hasFn(self, kind):
        return kind == "joint"


class SelectionList:
    def __init__(self):
        self.node = None

    def add(self, name):
        self.node = name

    def getDependNode(self, index):
        assert index == 0
        return self.node


class FakeMaya:
    def __init__(self, influences=None):
        self.skin = "skinCluster1"
        self.influences = list(influences or [ROOT, CHILD])
        self.scene_joints = [ROOT, CHILD, OTHER, EXTRA]
        self.active = ROOT
        self.selected = ["|Body|Mesh"]
        self.locks = {path: True for path in self.scene_joints}
        self.warning_messages = []
        self.connected = []
        self.native_active = ROOT
        self.native_tree = None
        self.native_items = [ROOT, CHILD, OTHER]
        self.native_selected = [ROOT, CHILD]  # Replicate the Maya multi-selection bug.
        self.native_events = []
        self.mel_calls = []
        self.weight_map = {ROOT: 0.25, CHILD: 0.75, OTHER: 0.0, EXTRA: 0.0}

    def ls(self, *args, **kwargs):
        if kwargs.get("sl") or kwargs.get("selection"):
            if kwargs.get("type") == "joint":
                return [x for x in self.selected if x in self.scene_joints]
            return list(self.selected)
        if not args:
            return []
        node = args[0]
        if isinstance(node, (tuple, list)):
            return [x for x in node if x in self.scene_joints]
        if kwargs.get("type") == "joint":
            return [x for x in self.scene_joints
                    if x == node or ("|" not in node and
                                     x.rsplit("|", 1)[-1] == node)]
        return [node]

    def objExists(self, node):
        if node == self.skin:
            return True
        if node.endswith(".liw"):
            return node[:-4] in self.locks
        return node in self.scene_joints

    def getAttr(self, attr):
        return self.locks[attr[:-4]]

    def skinPercent(self, skin, vertex, **kwargs):
        assert skin == self.skin
        assert kwargs.get("q")
        return self.weight_map.get(kwargs["transform"], 0.0)

    def setAttr(self, attr, value):
        self.locks[attr[:-4]] = bool(value)

    def listRelatives(self, name, **kw):
        if kw.get("children"):
            return [CHILD, EXTRA] if name == ROOT else []
        if kw.get("parent"):
            return [ROOT] if name in (CHILD, EXTRA) else []
        return []

    def connectionInfo(self, attr, **kw):
        assert attr == self.skin + ".paintTrans"
        return self.active + ".message"

    def connectAttr(self, source, dest, **kw):
        assert dest == self.skin + ".paintTrans"
        assert kw.get("force") is True
        self.active = source.rsplit(".", 1)[0]
        self.connected.append(source)

    def artAttrSkinPaintCtx(self, name, **kw):
        assert name == "artAttrSkinContext"
        if kw.get("edit"):
            self.active = kw["influence"]

    def treeView(self, tree, **kw):
        assert tree == self.native_tree
        if kw.get("exists"):
            return True
        if kw.get("query") and kw.get("children") == "":
            return list(self.native_items)
        if kw.get("query") and kw.get("selectItem") is True:
            return list(self.native_selected)
        if kw.get("edit") and kw.get("clearSelection"):
            self.native_selected = []
            self.native_events.append("clear")
            return
        if kw.get("edit") and "selectItem" in kw:
            name, state = kw["selectItem"]
            assert name in self.native_items
            if state:
                if name not in self.native_selected:
                    self.native_selected.append(name)
            elif name in self.native_selected:
                self.native_selected.remove(name)
            self.native_events.append(("select", name, state))
            return
        raise AssertionError("Unexpected treeView call {}".format(kw))

    def select(self, *names, **kw):
        if kw.get("clear"):
            self.selected = []
        elif names:
            self.selected = [names[0]] if isinstance(names[0], str) else list(names[0])

    def warning(self, text):
        self.warning_messages.append(text)


FUNCTIONS = (
    "_SkinInfluencePaths", "_BoundJoint", "GetActivePaintJoint",
    "singleUnlock", "unlock", "UnlockJoints", "addUnlockUp",
    "addUnlockDown", "ActiveJoint", "switchJoint", "GetVertexWeights",
    "UnlockTwoJoints", "UnlockInfluenceJoints", "SelectPaintInfluence",
    "_SelectNativePaintInfluence"
)


def load_logic(fake):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in FUNCTIONS]
    assert len(nodes) == len(FUNCTIONS)
    class OM:
        MSelectionList = SelectionList
        MFn = types.SimpleNamespace(kJoint="joint")

    class SkinFn:
        def __init__(self, skin):
            assert skin == fake.skin

        def influenceObjects(self):
            return [FakeDag(name) for name in fake.influences]

    class OMA:
        MFnSkinCluster = SkinFn

    class MEL:
        def eval(self, statement):
            fake.mel_calls.append(statement)
            if "$gArtSkinInfluencesList" in statement:
                return fake.native_tree
            if statement.startswith("setSmoothSkinInfluence"):
                fake.native_active = statement.split('"')[1]

    session = {"mesh": "|Body|Mesh", "skinCluster": fake.skin,
               "joints": list(fake.influences)}
    scope = {"cmds": fake, "om": OM, "oma": OMA,
             "mel": MEL(), "skinSession": session}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"),
         scope)
    scope["EnsureSkinSession"] = lambda **kw: session
    scope["GetSkinCluster"] = lambda mesh: fake.skin
    scope["_SetSkinSession"] = lambda mesh, skin: session
    scope["EnsurePaintContext"] = lambda *args, **kw: True
    scope["GetSkinData"] = lambda mesh=None: {
        "mesh": "|Body|Mesh", "skinCluster": fake.skin,
        "joints": scope["_SkinInfluencePaths"](fake.skin)}
    return scope


class DagBoundInfluenceTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeMaya()
        self.logic = load_logic(self.fake)

    def test_api_returns_only_the_exact_bound_paths(self):
        self.assertEqual(
            self.logic["_SkinInfluencePaths"](self.fake.skin), [ROOT, CHILD])
        self.assertEqual(
            self.logic["_BoundJoint"](self.fake.skin, "joint2"), CHILD)
        self.assertIsNone(
            self.logic["_BoundJoint"](self.fake.skin, OTHER))

    def test_short_joint_names_are_never_guessed_if_both_are_bound(self):
        self.fake.influences = [ROOT, CHILD, OTHER]
        self.assertIsNone(self.logic["_BoundJoint"](self.fake.skin, "joint2"))
        self.assertEqual(
            self.logic["_BoundJoint"](self.fake.skin, CHILD), CHILD)
        self.assertEqual(
            self.logic["_BoundJoint"](self.fake.skin, OTHER), OTHER)

    def test_add_down_activates_actual_bound_child_and_locks_only_other_influences(self):
        self.logic["addUnlockDown"]()
        self.assertEqual(self.fake.active, CHILD)
        self.assertFalse(self.fake.locks[ROOT])
        self.assertFalse(self.fake.locks[CHILD])
        self.assertTrue(self.fake.locks[OTHER])
        self.assertFalse(any("not an influence" in text
                             for text in self.fake.warning_messages))

    def test_native_paint_influence_selection_updates_tool_settings(self):
        before = list(self.fake.selected)
        self.assertTrue(self.logic["SelectPaintInfluence"](
            "|Body|Mesh", CHILD))
        self.assertEqual(self.fake.active, CHILD)
        self.assertEqual(self.fake.native_active, CHILD)
        self.assertEqual(self.fake.selected, before)
        self.assertEqual(
            self.fake.mel_calls,
            ['setSmoothSkinInfluence "{}";'.format(CHILD),
             'global string $gArtSkinInfluencesList; $gArtSkinInfluencesList;'])

    def test_single_native_row_after_repeated_influence_clicks(self):
        self.fake.native_tree = "artSkinInfluencesTree"
        self.fake.native_items = [ROOT, CHILD, OTHER]
        self.fake.native_selected = [ROOT, CHILD]
        before_scene_selection = list(self.fake.selected)
        self.assertTrue(self.logic["SelectPaintInfluence"]("|Body|Mesh", CHILD))
        self.assertEqual(self.fake.native_selected, [CHILD])
        self.assertEqual(self.fake.active, CHILD)
        self.assertEqual(self.fake.native_events[-2:], [
            "clear", ("select", CHILD, True)])
        self.assertEqual(self.fake.selected, before_scene_selection)

        self.assertTrue(self.logic["SelectPaintInfluence"]("|Body|Mesh", ROOT))
        self.assertEqual(self.fake.native_selected, [ROOT])
        self.assertEqual(self.fake.active, ROOT)
        self.assertEqual(self.fake.selected, before_scene_selection)

    def test_native_tree_resolves_partial_dag_item_without_confusing_names(self):
        self.fake.native_tree = "artSkinInfluencesTree"
        self.fake.native_items = ["joint1", "joint1|joint2"]
        self.fake.native_selected = ["joint1"]
        old_ls = self.fake.ls

        def ls(path, **kwargs):
            if path == "joint1":
                return [ROOT]
            if path == "joint1|joint2":
                return [CHILD]
            return old_ls(path, **kwargs)
        self.fake.ls = ls
        self.assertTrue(self.logic["SelectPaintInfluence"]("|Body|Mesh", CHILD))
        self.assertEqual(self.fake.native_selected, ["joint1|joint2"])

    def test_native_tree_refuses_ambiguous_item_without_multi_select(self):
        self.fake.native_tree = "artSkinInfluencesTree"
        self.fake.native_items = ["joint2", "joint1|joint2"]
        self.fake.native_selected = ["joint2", "joint1|joint2"]
        old_ls = self.fake.ls

        def ls(path, **kwargs):
            if path in self.fake.native_items:
                return [CHILD]
            return old_ls(path, **kwargs)
        self.fake.ls = ls
        self.assertFalse(self.logic["SelectPaintInfluence"]("|Body|Mesh", CHILD))
        self.assertEqual(self.fake.native_selected,
                         ["joint2", "joint1|joint2"])
        self.assertTrue(any("cannot uniquely locate" in msg
                            for msg in self.fake.warning_messages))

    def test_native_selection_rejects_unbound_duplicate_name(self):
        self.fake.native_active = ROOT
        self.assertFalse(self.logic["SelectPaintInfluence"](
            "|Body|Mesh", OTHER))
        self.assertEqual(self.fake.native_active, ROOT)
        self.assertEqual(self.fake.mel_calls, [])

    def test_switch_joint_updates_native_ui_as_well_as_painttrans(self):
        self.fake.locks[ROOT] = False
        self.fake.locks[CHILD] = False
        self.logic["switchJoint"]()
        self.assertEqual(self.fake.native_active, CHILD)
        self.assertEqual(self.fake.active, CHILD)

    def test_add_up_returns_to_actual_parent(self):
        self.fake.active = CHILD
        self.logic["addUnlockUp"]()
        self.assertEqual(self.fake.active, ROOT)
        self.assertFalse(self.fake.locks[ROOT])
        self.assertFalse(self.fake.locks[CHILD])
        self.assertTrue(self.fake.locks[OTHER])

    def test_add_down_selects_first_bound_child_and_does_not_use_unbound_child(self):
        self.fake.influences = [ROOT, EXTRA]
        self.logic["addUnlockDown"]()
        self.assertEqual(self.fake.active, EXTRA)
        self.assertTrue(self.fake.locks[CHILD])
        self.assertFalse(self.fake.locks[EXTRA])

    def test_add_down_with_unbound_children_leaves_skin_locks_unchanged(self):
        self.fake.influences = [ROOT]
        before = dict(self.fake.locks)
        self.logic["addUnlockDown"]()
        self.assertEqual(self.fake.active, ROOT)
        self.assertEqual(self.fake.locks, before)
        self.assertIn("No child", self.fake.warning_messages[-1])

    def test_active_joint_can_resolve_short_influence_name_without_wrong_branch(self):
        self.assertTrue(self.logic["ActiveJoint"]("|Body|Mesh", "joint2"))
        self.assertEqual(self.fake.active, CHILD)
        self.fake.active = ROOT
        self.assertFalse(self.logic["ActiveJoint"]("|Body|Mesh", OTHER))
        self.assertEqual(self.fake.active, ROOT)

    def test_switch_joint_cycles_through_actual_unlocked_full_paths(self):
        self.fake.locks[ROOT] = False
        self.fake.locks[CHILD] = False
        self.logic["switchJoint"]()
        self.assertEqual(self.fake.active, CHILD)
        self.logic["switchJoint"]()
        self.assertEqual(self.fake.active, ROOT)

    def test_unlock_joint_uses_selected_full_path_not_identical_leaf_names(self):
        self.fake.selected = [OTHER]
        self.logic["unlock"]()
        self.assertEqual(self.fake.active, ROOT)
        self.assertTrue(all(self.fake.locks.values()))
        self.assertIn("not influences", self.fake.warning_messages[-1])

    def test_single_unlock_rejects_unbound_short_name_and_keeps_all_locks(self):
        self.fake.influences = [ROOT, CHILD, OTHER]
        before = dict(self.fake.locks)
        self.assertEqual(self.logic["singleUnlock"](["joint2"]), [])
        self.assertEqual(before, self.fake.locks)

    def test_vertex_weights_keep_two_same_named_bound_joints_separate(self):
        self.fake.influences = [ROOT, CHILD, OTHER]
        self.fake.weight_map = {ROOT: 0.1, CHILD: 0.7, OTHER: 0.2}
        weights = self.logic["GetVertexWeights"](
            self.fake.skin, "|Body|Mesh.vtx[3]")
        self.assertEqual(weights, self.fake.weight_map)
        self.assertEqual(len(weights), 3)

    def test_unlock_two_joints_handles_two_bound_joint2_nodes(self):
        self.fake.influences = [ROOT, CHILD, OTHER]
        self.fake.weight_map = {ROOT: 0.1, CHILD: 0.7, OTHER: 0.2}
        self.fake.selected = ["|Body|Mesh.vtx[3]"]
        joints = self.logic["UnlockTwoJoints"]()
        self.assertEqual(joints, (CHILD, OTHER))
        self.assertEqual(self.fake.active, OTHER)
        self.assertTrue(self.fake.locks[ROOT])
        self.assertFalse(self.fake.locks[CHILD])
        self.assertFalse(self.fake.locks[OTHER])

    def test_unlock_joints_unlocks_only_influences_weighting_vertex(self):
        self.fake.influences = [ROOT, CHILD, OTHER]
        self.fake.weight_map = {ROOT: 0.0, CHILD: 0.8, OTHER: 0.2}
        self.fake.selected = ["|Body|Mesh.vtx[3]"]
        unlocked = self.logic["UnlockInfluenceJoints"]()
        self.assertEqual(set(unlocked), {CHILD, OTHER})
        self.assertEqual(self.fake.active, CHILD)
        self.assertTrue(self.fake.locks[ROOT])
        self.assertFalse(self.fake.locks[CHILD])
        self.assertFalse(self.fake.locks[OTHER])

    def test_other_skin_joint_actions_use_canonical_membership(self):
        source = SOURCE.read_text(encoding="utf-8")
        for fragment in (
            "sourceJoints = set(_SkinInfluencePaths(sourceSkin))",
            "destinationJoints = set(_SkinInfluencePaths(destinationSkin))",
            "existing = set(_SkinInfluencePaths(skin))",
            "sourceName = _BoundJoint(skin, joint, influences)",
            "sourceIndex = (fullNames.index(sourceName)",
            "parentIndex = (fullNames.index(parentName)",
            "influences[i].fullPathName()",
            "skinJoints = bound",
            "influences = _SkinInfluencePaths(skinCluster)",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
