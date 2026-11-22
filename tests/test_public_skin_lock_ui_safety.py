"""Offline regression for Maya/Qt crashes during Skinning Lock checkbox events.

The dangerous operation is QTreeWidget.clear() while itemChanged is still
executing: Qt/C++ may dereference the deleted originating item.
"""
import ast
from pathlib import Path
import types
import unittest


BOARD = (Path(__file__).resolve().parents[1]
         / "UIs/SkinningTools/NLTA_Skinning_CommandBoard.py")
J1 = "|Rig|joint1"
J2 = "|Rig|joint1|joint2"


class FakeItem:
    def __init__(self, panel, name, locked):
        self.panel = panel
        self.name = name
        self.locked = locked
        self.deleted = False
        self.selected = False

    def data(self, col, role):
        assert not self.deleted
        return self.name

    def checkState(self, col):
        assert not self.deleted
        return 2 if self.locked else 0

    def setCheckState(self, col, value):
        assert not self.deleted
        self.locked = value == 2
        if not self.panel.tree.signals_blocked:
            self.panel.change_item_lock(self, col)

    def setSelected(self, selected):
        assert not self.deleted
        self.selected = selected

    def isHidden(self):
        return False


class FakeTimer:
    def __init__(self, panel):
        self.panel = panel
        self.active = False

    def start(self, delay):
        assert delay == 0
        self.active = True

    def stop(self):
        self.active = False

    def fire(self):
        assert self.active
        assert not self.panel.in_emission, "Maya edits may only run after Qt signal"
        self.active = False
        self.panel._apply_pending_locks()


class FakeTree:
    def __init__(self, panel):
        self.panel = panel
        self.signals_blocked = False
        self.cleared = 0
        self.current = None

    def blockSignals(self, value):
        before = self.signals_blocked
        self.signals_blocked = value
        return before

    def clear(self):
        self.cleared += 1
        for item in self.panel._items.values():
            item.deleted = True
        if self.panel.in_emission:
            raise AssertionError("Destroyed emitting QTreeWidgetItem")
        self.panel._items = {}

    def selectedItems(self):
        return [item for item in self.panel._items.values() if item.selected]

    def clearSelection(self):
        for item in self.panel._items.values():
            item.selected = False

    def setCurrentItem(self, item):
        assert not item.deleted
        self.current = item

    def currentItem(self):
        return self.current


class FakeCmds:
    def __init__(self):
        self.panel = None
        self.locks = {J1: False, J2: True}
        self.warnings = []
        self.reentrant_callbacks = 0

    def objExists(self, name):
        return name in ("skin1", J1 + ".liw", J2 + ".liw")

    def getAttr(self, plug):
        return self.locks[plug[:-4]]

    def setAttr(self, plug, value):
        assert not self.panel.in_emission, "Maya setAttr called from Qt itemChanged"
        self.locks[plug[:-4]] = bool(value)
        # Simulate synchronous Maya scriptJob and Qt timer reentry on setAttr.
        self.reentrant_callbacks += 1
        self.panel.on_selection_changed()
        self.panel.sync_live()

    def warning(self, message):
        self.warnings.append(message)


class FakePanel:
    def __init__(self, cmds, methods):
        self.cmds = cmds
        cmds.panel = self
        self.skin = "skin1"
        self.mesh = "|Rig|Mesh"
        self._tree_skin = "skin1"
        self._rows = list(cmds.locks.items())
        self._items = {}
        self._parents = {}
        self._populating = False
        self._syncing = False
        self._editing_locks = False
        self._pending_locks = {}
        self._pending_lock_skin = None
        self._active_joint = None
        self._live_ticks = 0
        self.in_emission = False
        self._lock_timer = FakeTimer(self)
        self.tree = FakeTree(self)
        self.filter_count = 0
        self.sync_count = 0
        self.refresh_count = 0
        self.populate_count = 0
        self.heading_label = types.SimpleNamespace(setToolTip=lambda x: None)
        for name, method in methods.items():
            setattr(self, name, types.MethodType(method, self))
        for name, value in cmds.locks.items():
            self._items[name] = FakeItem(self, name, value)
        self.tree.current = self._items[J1]

    def filter_rows(self, *args):
        self.filter_count += 1

    def populate(self):
        self.populate_count += 1
        self.tree.clear()

    def sync_from_paint(self):
        self.sync_count += 1


def build_methods(cmds):
    module = ast.parse(BOARD.read_text(encoding="utf-8"))
    cls = next(node for node in module.body if isinstance(node, ast.ClassDef)
               and node.name == "InfluencePanel")
    required = (
        "change_item_lock", "_apply_pending_locks", "change_locks",
        "change_active_influence", "on_selection_changed", "sync_live",
        "sync_lock_states", "refresh",
    )
    functions = [node for node in cls.body
                 if isinstance(node, ast.FunctionDef)
                 and node.name in required]
    assert len(functions) == len(required)

    def rows(skin):
        return list(cmds.locks.items())

    def set_locks(skin, joints, mode):
        changed = 0
        for joint in joints:
            current = cmds.locks[joint]
            next_state = not current if mode == "reverse" else mode == "lock"
            if current != next_state:
                cmds.setAttr(joint + ".liw", int(next_state))
                changed += 1
        return changed

    def activate(skin, mesh, joint, bound):
        cmds.panel.on_selection_changed()
        cmds.panel.sync_live()
        return True

    scope = {
        "cmds": cmds,
        "QtCore": types.SimpleNamespace(Qt=types.SimpleNamespace(
            Checked=2, Unchecked=0, UserRole=0)),
        "_skin_influence_rows": rows,
        "_set_influence_locks": set_locks,
        "_skin_from_selection": lambda: {
            "skinCluster": "skin1", "mesh": "|Rig|Mesh"},
        "_selected_unskinned_mesh": lambda: False,
        "_active_skin_paint_influence": lambda skin, bound: J1,
        "_activate_skin_paint_influence": activate,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]),
                 str(BOARD), "exec"), scope)
    return {name: scope[name] for name in required}


class LockUiSafetyTests(unittest.TestCase):
    def setUp(self):
        self.cmds = FakeCmds()
        self.panel = FakePanel(self.cmds, build_methods(self.cmds))

    def toggle(self, name):
        item = self.panel._items[name]
        self.panel.in_emission = True
        try:
            item.setCheckState(1, 0 if item.locked else 2)
        finally:
            self.panel.in_emission = False
        self.assertFalse(item.deleted)
        self.assertIs(self.panel._items[name], item)
        self.assertEqual(self.panel.tree.cleared, 0)
        # The click returned to Qt; now it is safe to invoke Maya setAttr.
        self.assertTrue(self.panel._lock_timer.active)
        self.panel._lock_timer.fire()

    def test_repeated_lock_and_unlock_never_delete_emitting_item(self):
        for i in range(20):
            self.toggle(J1 if i % 2 == 0 else J2)
        self.assertEqual(self.panel.populate_count, 0)
        self.assertGreater(self.cmds.reentrant_callbacks, 0)
        self.assertGreater(self.panel.filter_count, 0)

    def test_repeated_toggles_before_event_loop_apply_last_state(self):
        # Two changes in one event turn must never make stale .liw updates.
        item = self.panel._items[J1]
        self.panel.in_emission = True
        try:
            item.setCheckState(1, 2)
            item.setCheckState(1, 0)
            item.setCheckState(1, 2)
        finally:
            self.panel.in_emission = False
        self.assertFalse(self.cmds.locks[J1])
        self.panel._lock_timer.fire()
        self.assertTrue(self.cmds.locks[J1])
        self.assertTrue(item.locked)
        self.assertEqual(self.panel.tree.cleared, 0)

    def test_batch_lock_cancels_stale_queued_checkbox(self):
        item = self.panel._items[J1]
        item.setCheckState(1, 2)
        self.assertTrue(self.panel._lock_timer.active)
        self.panel.change_locks("unlock", False)
        self.assertFalse(self.panel._lock_timer.active)
        self.assertFalse(self.panel._pending_locks)
        self.assertFalse(self.cmds.locks[J1])
        self.assertFalse(item.locked)

    def test_batch_reverse_and_lock_all_reuse_all_items(self):
        originals = dict(self.panel._items)
        for mode in ("reverse", "lock", "unlock", "reverse"):
            self.panel.change_locks(mode, False)
            self.assertEqual(self.panel.tree.cleared, 0)
            for joint in (J1, J2):
                self.assertIs(self.panel._items[joint], originals[joint])
                self.assertEqual(
                    self.panel._items[joint].locked, self.cmds.locks[joint])
        self.assertGreater(self.cmds.reentrant_callbacks, 0)

    def test_active_influence_sync_does_not_rebuild_on_nested_selection(self):
        item = self.panel._items[J2]
        self.panel.in_emission = True
        try:
            self.panel.change_active_influence(item, self.panel._items[J1])
        finally:
            self.panel.in_emission = False
        self.assertEqual(self.panel._active_joint, J2)
        self.assertIs(self.panel.tree.current, item)
        self.assertTrue(item.selected)
        self.assertEqual(self.panel.tree.cleared, 0)
        self.assertFalse(self.panel._syncing)

    def test_refresh_same_influences_never_rebuilds_tree(self):
        current = dict(self.panel._items)
        self.cmds.locks[J1] = True
        self.panel.refresh(prefer_selection=False)
        self.assertEqual(self.panel.populate_count, 0)
        self.assertEqual(self.panel.tree.cleared, 0)
        self.assertTrue(current[J1].locked)
        self.assertIs(self.panel._items[J1], current[J1])

    def test_native_selection_change_same_skin_keeps_tree_stable(self):
        self.panel.on_selection_changed()
        self.assertEqual(self.panel.populate_count, 0)
        self.assertEqual(self.panel.tree.cleared, 0)
        self.assertEqual(self.panel.sync_count, 1)

    def test_failed_lock_update_restores_checkbox_from_maya(self):
        original = self.cmds.setAttr

        def reject(plug, value):
            raise RuntimeError("joint is referenced")

        self.cmds.setAttr = reject
        # Production _set_influence_locks handles RuntimeError; the test
        # mock for this needs the same recovery behavior.
        def noop_set_locks(skin, joints, mode):
            return 0

        method = self.panel.change_item_lock.__func__
        scope = method.__globals__
        before = scope["_set_influence_locks"]
        scope["_set_influence_locks"] = noop_set_locks
        try:
            self.toggle(J1)
        finally:
            scope["_set_influence_locks"] = before
            self.cmds.setAttr = original
        self.assertFalse(self.panel._items[J1].locked)
        self.assertFalse(self.cmds.locks[J1])


if __name__ == "__main__":
    unittest.main()
