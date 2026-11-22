"""Prune must preserve exact DAG influence locks and never change native UI."""
import ast
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "Libs/NLTA_Skinning.py"
ROOT = "|Rig|joint1"
CHILD = "|Rig|joint1|joint2"
DUPLICATE = "|OtherRig|joint2"


class FakeMaya:
    def __init__(self, fail=False):
        self.skin = "skinCluster1"
        self.other_skin = "skinCluster2"
        self.joints = [ROOT, CHILD, DUPLICATE]
        self.locks = {ROOT: True, CHILD: False, DUPLICATE: True}
        self.other_locks = {"|Other|joint1": True}
        self.changes = []
        self.eval_calls = []
        self.warnings = []
        self.fail = fail

    def objExists(self, plug):
        return plug.endswith(".liw") and (
            plug[:-4] in self.locks or plug[:-4] in self.other_locks)

    def getAttr(self, plug):
        name = plug[:-4]
        return self.locks[name] if name in self.locks else self.other_locks[name]

    def setAttr(self, plug, value):
        name = plug[:-4]
        self.changes.append((name, value))
        if name in self.locks:
            self.locks[name] = bool(value)
        else:
            self.other_locks[name] = bool(value)

    def warning(self, message):
        self.warnings.append(message)

    def eval(self, expression):
        self.eval_calls.append(expression)
        if expression != "PruneSmallWeights;":
            raise AssertionError("Unexpected native Paint UI MEL: " + expression)
        self.changes.append(("prune", dict(self.locks)))
        if self.fail:
            raise RuntimeError("Maya prune failed")


def load_prune(fake, has_skin=True):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    proc = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "pruneSmallWeights")
    session = {"skinCluster": fake.skin} if has_skin else None
    context = {
        "cmds": fake,
        "mel": fake,
        "EnsureSkinSession": lambda warn=True: session,
        "_SkinInfluencePaths": lambda skin: list(fake.joints),
    }
    exec(compile(ast.Module(body=[proc], type_ignores=[]),
                 str(SOURCE), "exec"), context)
    return context["pruneSmallWeights"]


class PruneLockTests(unittest.TestCase):
    def test_prune_temporarily_unlocks_all_then_restores_exact_original_state(self):
        maya = FakeMaya()
        before = dict(maya.locks)
        load_prune(maya)()
        self.assertEqual(maya.locks, before)
        self.assertEqual(maya.other_locks, {"|Other|joint1": True})
        self.assertEqual(maya.eval_calls, ["PruneSmallWeights;"])
        pruned = [data for name, data in maya.changes if name == "prune"]
        self.assertEqual(pruned, [{ROOT: False, CHILD: False, DUPLICATE: False}])

    def test_prune_failure_also_restores_locks(self):
        maya = FakeMaya(fail=True)
        before = dict(maya.locks)
        with self.assertRaisesRegex(RuntimeError, "Maya prune failed"):
            load_prune(maya)()
        self.assertEqual(maya.locks, before)
        self.assertEqual(maya.eval_calls, ["PruneSmallWeights;"])

    def test_no_skinned_mesh_does_not_launch_native_paint_ui(self):
        maya = FakeMaya()
        load_prune(maya, has_skin=False)()
        self.assertEqual(maya.eval_calls, [])
        self.assertEqual(maya.changes, [])
        self.assertTrue(maya.warnings)

    def test_originally_unlocked_influences_remain_unlocked(self):
        maya = FakeMaya()
        maya.locks[ROOT] = False
        maya.locks[CHILD] = True
        maya.locks[DUPLICATE] = False
        before = dict(maya.locks)
        load_prune(maya)()
        self.assertEqual(maya.locks, before)
        self.assertEqual(maya.eval_calls, ["PruneSmallWeights;"])


if __name__ == "__main__":
    unittest.main()
