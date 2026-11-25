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
                    _save_editor=lambda: None, _rebuild_cards=lambda **kw: None,
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
