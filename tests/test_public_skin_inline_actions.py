"""Offline tests for painted per-joint Lock column controls (Maya/PySide-free)."""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


FILE = (Path(__file__).resolve().parents[1]
        / "UIs/SkinningTools/NLTA_Skinning_CommandBoard.py")
ROOT = "|Rig|Jnt"
CHILD = "|Rig|Jnt|Child"
DUPLICATE = "|Other|Child"
SKIN = "skinA"
MESH = "|Rig|Body"


class Rectangle:
    def __init__(self, x, y, width, height):
        self.left, self.top, self.width_, self.height_ = x, y, width, height

    def x(self):
        return self.left

    def y(self):
        return self.top

    def height(self):
        return self.height_

    def contains(self, point):
        return (self.left <= point.x() < self.left + self.width_
                and self.top <= point.y() < self.top + self.height_)


class Point:
    def __init__(self, x, y):
        self.px, self.py = x, y

    def x(self):
        return self.px

    def y(self):
        return self.py


class Timer:
    def __init__(self):
        self.active = False

    def start(self, interval):
        assert interval == 0
        self.active = True

    def stop(self):
        self.active = False


class FakeItem:
    def __init__(self, joint, state):
        self.joint = joint
        self.state = state
        self.selected = False

    def data(self, column, role):
        return self.joint

    def checkState(self, column):
        return 2 if self.state else 0

    def setCheckState(self, column, value):
        self.state = bool(value)

    def setSelected(self, state):
        self.selected = state


class FakeTree:
    def __init__(self, panel):
        self.panel = panel
        self.blocked = False
        self.selected = None
        self.cleared = 0
        self.viewport_widget = object()
        self.header_widget = types.SimpleNamespace(
            sectionViewportPosition=lambda column: 120)

    def blockSignals(self, state):
        original = self.blocked
        self.blocked = state
        return original

    def clearSelection(self):
        self.selected = None

    def setCurrentItem(self, item):
        self.selected = item

    def viewport(self):
        return self.viewport_widget

    def itemAt(self, position):
        return self.panel._items[CHILD]

    def header(self):
        return self.header_widget

    def visualItemRect(self, item):
        return Rectangle(0, 10, 274, 44)

    def columnWidth(self, column):
        return 154


class FakeCmds:
    def __init__(self):
        self.locks = {ROOT: True, CHILD: True, DUPLICATE: False}
        self.select_log = []
        self.warnings = []

    def objExists(self, name):
        return name == SKIN

    def listRelatives(self, joint, **flags):
        if flags.get("parent"):
            return [ROOT] if joint == CHILD else []
        if flags.get("children"):
            return [CHILD] if joint == ROOT else []
        raise AssertionError("Expected parent OR child flags")

    def warning(self, text):
        self.warnings.append(text)


def load_logic(cmds):
    tree = ast.parse(FILE.read_text(encoding="utf-8"))
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id == "INFLUENCE_ROW_ACTIONS":
                    constants[name.id] = ast.literal_eval(node.value)
    qt = types.SimpleNamespace(Qt=types.SimpleNamespace(
        UserRole=0, Checked=2, Unchecked=0, LeftButton=1),
        QRect=Rectangle,
        QEvent=types.SimpleNamespace(
            ToolTip=10, MouseButtonPress=2, MouseButtonRelease=3,
            MouseButtonDblClick=4))
    widget = types.SimpleNamespace(
        QFrame=types.SimpleNamespace(eventFilter=lambda *args: False),
        QToolTip=types.SimpleNamespace(showText=lambda *args: None))
    scope = {
        **constants, "cmds": cmds, "QtCore": qt, "QtWidgets": widget,
        "_skin_influence_rows": lambda skin: list(cmds.locks.items()),
        "_resolve_skin_influence": lambda skin, node, bound: node if node in bound else None,
    }
    names = ("_influence_cell_slots", "_influence_action_plan")
    fns = [node for node in tree.body
           if isinstance(node, ast.FunctionDef) and node.name in names]
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "InfluencePanel")
    methods = (
        "_inline_control_at", "eventFilter", "queue_inline_lock",
        "queue_influence_action", "_apply_influence_action",
    )
    fns.extend(node for node in cls.body
               if isinstance(node, ast.FunctionDef) and node.name in methods)
    assert len(fns) == len(names) + len(methods)
    exec(compile(ast.Module(body=fns, type_ignores=[]),
                 str(FILE), "exec"), scope)
    return scope, methods


class Panel:
    def __init__(self, scope, cmds, methods):
        self.skin = SKIN
        self.mesh = MESH
        self._populating = False
        self._editing_locks = False
        self._pending_locks = {}
        self._pending_lock_skin = None
        self._pending_context_action = None
        self._lock_timer = Timer()
        self._context_timer = Timer()
        self._active_joint = None
        self._items = {name: FakeItem(name, value)
                       for name, value in cmds.locks.items()}
        self.tree = FakeTree(self)
        self.cmds = cmds
        self.row_clear_count = 0
        for name in methods:
            setattr(self, name, types.MethodType(scope[name], self))

    def filter_rows(self):
        pass

    def sync_lock_states(self):
        for name, state in self.cmds.locks.items():
            self._items[name].state = state


class InlineControlTests(unittest.TestCase):
    def setUp(self):
        self.cmds = FakeCmds()
        self.scope, methods = load_logic(self.cmds)
        self.panel = Panel(self.scope, self.cmds, methods)
        self.focus = []
        def lock(skin, targets, mode):
            self.assertEqual(skin, SKIN)
            for joint in targets:
                self.cmds.locks[joint] = mode == "lock"
        self.scope["_set_influence_locks"] = lock
        self.scope["_activate_skin_paint_influence"] = (
            lambda skin, mesh, joint, bound: self.focus.append(joint) or True)

    def fire(self):
        self.assertTrue(self.panel._context_timer.active)
        self.panel._context_timer.active = False
        self.panel._apply_influence_action()

    def test_button_geometry_fits_one_lock_column_without_overlap(self):
        slots = self.scope["_influence_cell_slots"](Rectangle(120, 10, 154, 44))
        self.assertEqual([x[0] for x in slots], [
            "toggle_lock", "unlock", "add_unlock", "add_up", "add_down",
            "unlock_all", "lock_inverse", "isolate", "un_isolate"])
        top_y = slots[0][3].y()
        bottom_y = slots[5][3].y()
        self.assertEqual([rect.y() for _, _, _, rect in slots[:5]],
                         [top_y] * 5)
        self.assertEqual([rect.y() for _, _, _, rect in slots[5:]],
                         [bottom_y] * 4)
        self.assertGreater(bottom_y, top_y + 18)
        for row in (slots[:5], slots[5:]):
            for index, (_, _, _, rect) in enumerate(row):
                self.assertTrue(rect.contains(Point(rect.x() + 1, rect.y() + 1)))
                self.assertLessEqual(rect.x() + rect.width_, 274)
                self.assertLessEqual(rect.y() + rect.height_, 54)
                if index:
                    prev = row[index - 1][3]
                    self.assertGreaterEqual(rect.x(), prev.x() + prev.width_)

    def test_each_click_resolves_exact_joint_without_rebuilding_tree(self):
        before = dict(self.panel._items)
        slots = self.scope["_influence_cell_slots"](Rectangle(120, 10, 154, 44))
        for action, text, caption, rect in slots:
            hit = self.panel._inline_control_at(
                Point(rect.x() + 1, rect.y() + 1))
            self.assertEqual(hit[0], CHILD)
            self.assertEqual(hit[1], action)
        self.assertEqual(before, self.panel._items)
        self.assertEqual(self.panel.tree.cleared, 0)

    def test_lock_inverse_only_unlocks_clicked_joint(self):
        self.panel.queue_influence_action(CHILD, "lock_inverse")
        self.assertEqual(self.cmds.locks[CHILD], True)  # Deferred.
        self.fire()
        self.assertEqual(self.cmds.locks, {
            ROOT: True, CHILD: False, DUPLICATE: True})
        self.assertEqual(self.focus, [CHILD])
        self.assertEqual(self.panel.tree.cleared, 0)

    def test_unlock_all_and_add_unlock_preserve_expected_scopes(self):
        self.panel.queue_influence_action(ROOT, "unlock_all")
        self.fire()
        self.assertTrue(all(not value for value in self.cmds.locks.values()))
        self.cmds.locks[ROOT] = True
        self.cmds.locks[DUPLICATE] = True
        self.panel.queue_influence_action(CHILD, "add_unlock")
        self.fire()
        self.assertEqual(self.cmds.locks, {
            ROOT: True, CHILD: False, DUPLICATE: True})

    def test_add_up_down_use_bound_parent_child_not_same_short_name(self):
        self.panel.queue_influence_action(CHILD, "add_up")
        self.fire()
        self.assertEqual(self.focus, [ROOT])
        self.assertEqual(self.cmds.locks, {
            ROOT: False, CHILD: False, DUPLICATE: True})
        self.panel.queue_influence_action(ROOT, "add_down")
        self.fire()
        self.assertEqual(self.focus, [ROOT, CHILD])
        self.assertEqual(self.cmds.locks[DUPLICATE], True)

    def test_checkbox_click_queues_without_immediate_maya_write(self):
        self.panel.queue_inline_lock(ROOT)
        self.assertEqual(self.cmds.locks[ROOT], True)
        self.assertFalse(self.panel._items[ROOT].state)
        self.assertEqual(self.panel._pending_locks, {ROOT: False})
        self.assertTrue(self.panel._lock_timer.active)
        self.assertEqual(self.panel.tree.cleared, 0)

    def test_inline_mouse_event_is_handled_without_selecting_tree(self):
        slots = self.scope["_influence_cell_slots"](Rectangle(120, 10, 154, 44))
        target = next(rect for action, _, _, rect in slots
                      if action == "lock_inverse")
        event = types.SimpleNamespace(
            type=lambda: 3, button=lambda: 1,
            pos=lambda: Point(target.x() + 1, target.y() + 1))
        handled = self.panel.eventFilter(self.panel.tree.viewport(), event)
        self.assertTrue(handled)
        self.assertTrue(self.panel._context_timer.active)
        self.assertIsNone(self.panel.tree.selected)
        self.assertTrue(self.cmds.locks[CHILD])
        self.fire()
        self.assertFalse(self.cmds.locks[CHILD])

    def test_un_isolate_uses_same_clicked_joint_without_changing_locks(self):
        calls = []
        previous = dict(self.cmds.locks)
        fake = types.SimpleNamespace(
            UnIsolateEffectVertex=lambda **kwargs: calls.append(kwargs))
        with mock.patch.dict(sys.modules, {"NLTA_Skinning": fake}):
            self.panel.queue_influence_action(CHILD, "un_isolate")
            self.fire()
        self.assertEqual(calls, [{"mesh": MESH, "joint": CHILD}])
        self.assertEqual(self.cmds.locks, previous)
        self.assertEqual(self.panel.tree.cleared, 0)

    def test_isolate_passes_explicit_joint_and_mesh(self):
        isolated = []
        fake = types.SimpleNamespace(
            IsolateEffectVertex=lambda **args: isolated.append(args))
        with mock.patch.dict(sys.modules, {"NLTA_Skinning": fake}):
            self.panel.queue_influence_action(CHILD, "isolate")
            self.fire()
        self.assertEqual(isolated, [{"mesh": MESH, "joint": CHILD}])
        self.assertEqual(self.cmds.locks[CHILD], True)


if __name__ == "__main__":
    unittest.main()
