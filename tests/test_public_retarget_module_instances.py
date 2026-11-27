"""Retarget module instances must be independent of names and kinds."""
import ast
import copy
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "UIs/Retarget.py"


def scope(*names, **dependencies):
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    env = dict(dependencies)
    module = ast.Module(body=[functions[name] for name in names],
                        type_ignores=[])
    exec(compile(module, str(UI), "exec"), env)
    return env


class ModuleInstanceTests(unittest.TestCase):
    def test_add_same_module_twice_and_independent_json_paths(self):
        state = {"steps": []}
        selected = SimpleNamespace(currentData=lambda: "MatchRotatePair")
        env = scope("_new_step", "_add_step", "_instance_data_path",
                    uuid=uuid, _STATE=state, UIs={"step_type": selected},
                    _module=lambda kind: SimpleNamespace(
                        LABEL="Match Rotate Vector", DefaultSetting=lambda: {"pairs": []}),
                    _collect_card_orders=lambda: None, _append_card=lambda record: None,
                    _status=lambda message: None, _safe=lambda f: f(),
                    os=__import__("os"),
                    LEGACY_STEP_MAP={"MatchRotatePair": "Retarget_MatchRotatePair.py"})
        env["_add_step"]()
        env["_add_step"]()
        first, second = state["steps"]
        self.assertEqual(first["name"], second["name"])
        self.assertEqual(first["kind"], second["kind"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(first["id"]), 32)
        self.assertEqual([first["order"], second["order"]], [10, 20])
        first["data"]["pairs"].append("only-first")
        self.assertEqual(second["data"]["pairs"], [])
        path = env["_instance_data_path"]
        self.assertNotEqual(path("RetargetData", first["kind"], first["id"]),
                            path("RetargetData", second["kind"], second["id"]))

    def test_move_reuses_cards_and_keeps_unsaved_fields(self):
        class Order:
            def __init__(self, value):
                self.current = value
                self.blocked = False
            def value(self):
                return self.current
            def setValue(self, value):
                self.current = value
            def blockSignals(self, flag):
                previous = self.blocked
                self.blocked = flag
                return previous

        class Arrow:
            def setEnabled(self, enabled):
                self.enabled = enabled

        class Layout:
            def __init__(self, widgets):
                self.widgets = list(widgets)
                self.moves = 0
            def indexOf(self, widget):
                return self.widgets.index(widget) if widget in self.widgets else -1
            def removeWidget(self, widget):
                self.widgets.remove(widget)
            def insertWidget(self, index, widget):
                self.widgets.insert(index, widget)
                self.moves += 1

        rows = [{"id": key, "order": order, "data": {"pairs": []}}
                for key, order in (("a", 10), ("b", 20), ("c", 30))]
        cards = {row["id"]: SimpleNamespace(order=Order(row["order"]),
                  up=Arrow(), down=Arrow(), unsaved=["original widget edit"])
                 for row in rows}
        layout = Layout(cards.values())
        redraws = []
        state = {"steps": rows}
        ui = {"cards": cards, "cards_layout": layout,
              "cards_container": SimpleNamespace(updatesEnabled=lambda: True,
                  setUpdatesEnabled=redraws.append)}
        env = scope("_get_step", "_sorted_steps", "_collect_card_orders",
                    "_sync_card_order", "_move_step", "_apply_manual_order",
                    _STATE=state, UIs=ui, _safe=lambda fn: fn(), _status=lambda msg: None)
        env["_move_step"]("b", 1)
        self.assertEqual(layout.widgets, [cards["a"], cards["c"], cards["b"]])
        self.assertEqual(layout.moves, 1)
        self.assertEqual(cards["b"].order.value(), 30)
        self.assertFalse(cards["b"].down.enabled)
        self.assertEqual(cards["b"].unsaved, ["original widget edit"])
        self.assertEqual(redraws, [False, True])
        self.assertTrue(state["dirty"])
        self.assertFalse(cards["b"].order.blocked)
        cards["b"].order.setValue(5)
        env["_apply_manual_order"]()
        self.assertEqual(layout.widgets, [cards["b"], cards["a"], cards["c"]])
        self.assertFalse(cards["b"].up.enabled)

    def test_drag_drop_moves_across_multiple_modules_and_preserves_data(self):
        rows = [{"id": key, "order": index * 10,
                 "data": {"pairs": [key]}}
                for index, key in enumerate("abcde", 1)]
        state = {"steps": rows, "dirty": False}
        synced = []
        env = scope("_get_step", "_sorted_steps", "_drop_step",
                    _STATE=state, _collect_card_orders=lambda: None,
                    _sync_card_order=lambda: synced.append(True),
                    _status=lambda msg: None)
        order = lambda: [row["id"] for row in env["_sorted_steps"]()]
        env["_drop_step"]("b", 5)
        self.assertEqual(order(), list("acdeb"))
        self.assertEqual(len(synced), 1)
        self.assertTrue(state["dirty"])
        self.assertEqual([row["order"] for row in env["_sorted_steps"]()],
                         [10, 20, 30, 40, 50])
        env["_drop_step"]("b", 0)
        self.assertEqual(order(), list("bacde"))
        self.assertEqual(len(synced), 2)
        state["dirty"] = False
        env["_drop_step"]("b", 1)
        self.assertFalse(state["dirty"])
        self.assertEqual(len(synced), 2)
        self.assertEqual([row["data"]["pairs"] for row in rows],
                         [[key] for key in "abcde"])

    def test_same_kind_runs_multiple_times_in_order(self):
        env = scope("_validate_sequence")
        rows = [
            {"id": "c", "kind": "MatchRotatePair", "name": "Same", "enabled": True, "order": 30},
            {"id": "a", "kind": "MatchRotatePair", "name": "Same", "enabled": True, "order": 10},
            {"id": "b", "kind": "MatchRotate", "name": "Same", "enabled": True, "order": 20},
            {"id": "d", "kind": "MatchRotate", "name": "Same", "enabled": True, "order": 40},
            {"id": "e", "kind": "MatchRotate", "name": "Same", "enabled": False, "order": 50},
        ]
        self.assertEqual([x["id"] for x in env["_validate_sequence"](True, rows)],
                         ["a", "b", "c", "d"])

    def test_save_last_constraint_retained(self):
        env = scope("_validate_sequence")
        rows = [{"kind": "Save", "enabled": True, "order": 10},
                {"kind": "MatchRotatePair", "enabled": True, "order": 20}]
        with self.assertRaisesRegex(ValueError, "must be the last"):
            env["_validate_sequence"](True, rows)


if __name__ == "__main__":
    unittest.main()
