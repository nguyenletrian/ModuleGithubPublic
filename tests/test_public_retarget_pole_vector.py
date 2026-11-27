"""Offline contracts for the live Pole Vector builder (no Maya required)."""
import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_PoleVector.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = dict(math=math, **dependencies)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(STEP), "exec"), env)
    return env


class PoleVectorTests(unittest.TestCase):
    def test_default_and_namespace(self):
        env = scope()
        data = env["DefaultSetting"]()
        self.assertEqual(data["source_role"], "Anim")
        self.assertEqual(data["distance_ratio"], 1.0)
        self.assertEqual(env["namespaceForRole"]("Anim", {
            "reference_namespaces": {"old_animations": "RT_ANIM"}}), "RT_ANIM")
        self.assertEqual({row[1] for row in env["Fields"]()}, set(data))

    def test_live_builder_uses_world_matrices_and_locator_offset_matrix(self):
        nodes, connections, attrs = {}, {}, {}
        def create(kind, name, **kwargs):
            nodes[name] = kind
            return name
        def connect(source, dest):
            self.assertNotIn(dest, connections)
            connections[dest] = source
        def set_attr(plug, *values, **kwargs):
            attrs[plug] = values[0] if len(values) == 1 else values
        cmds = SimpleNamespace(createNode=create, connectAttr=connect,
                               setAttr=set_attr, spaceLocator=lambda name: [name],
                               ls=lambda node, **kw: [node])
        env = scope(cmds=cmds)
        name = ":Anim:Knee_PV"
        locator, created = env["createPoleVector"]("Start", "Middle", "End", name, 0.5)
        self.assertEqual(locator, name)
        self.assertEqual(set(created), set(nodes))
        self.assertEqual(connections[name + "_StartMatrix.inputMatrix"], "Start.worldMatrix[0]")
        self.assertEqual(connections[name + "_MiddleMatrix.inputMatrix"], "Middle.worldMatrix[0]")
        self.assertEqual(connections[name + "_EndMatrix.inputMatrix"], "End.worldMatrix[0]")
        self.assertEqual(connections[name + ".offsetParentMatrix"], name + "_PoleMatrix.outputMatrix")
        self.assertEqual(attrs[name + "_PoleDistance.input2"], 0.5)
        self.assertEqual(connections[name + "_StartEndLength.inMatrix1"], "Start.worldMatrix[0]")
        self.assertEqual(connections[name + "_StartEndLength.inMatrix2"], "End.worldMatrix[0]")
        self.assertEqual(connections[name + "_PoleDistance.input1"], name + "_StartEndLength.distance")
        self.assertEqual(list(nodes.values()).count("distanceBetween"), 1)
        self.assertNotIn("expression", nodes.values())
        self.assertNotIn("parentConstraint", nodes.values())

    def test_run_rejects_same_joint_before_creating_network(self):
        cmds = SimpleNamespace(ls=lambda name, **kw: [name], objExists=lambda name: False)
        env = scope(cmds=cmds, rt=SimpleNamespace(leaf=lambda name: name.split(":")[-1]))
        with self.assertRaisesRegex(ValueError, "three different joints"):
            env["Run"]({"start": "A", "middle": "A", "end": "C"},
                       {"source_namespace_animation": "Anim"})


if __name__ == "__main__":
    unittest.main()
