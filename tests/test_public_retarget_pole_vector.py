"""Offline contracts for the live Pole Vector builder (no Maya required)."""
import ast
import math
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_PoleVector.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = dict(math=math, re=re, **dependencies)
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

    def test_mirror_creates_two_independent_chains_with_same_ratio(self):
        cmds = SimpleNamespace(ls=lambda name, **kw: [name], objExists=lambda name: False)
        env = scope(cmds=cmds, rt=SimpleNamespace(leaf=lambda name: name.split(":")[-1]))
        calls = []
        def create(*args):
            calls.append(args)
            return args[3], []
        env["createPoleVector"] = create
        context = {"source_namespace_animation": "Anim"}
        result = env["Run"]({"start": "L_Thigh", "middle": "L_Knee", "end": "L_Ankle",
                             "name": "L_Knee_PV", "distance_ratio": 1.25, "mirror": True}, context)
        self.assertEqual(calls, [
            (":Anim:L_Thigh", ":Anim:L_Knee", ":Anim:L_Ankle", ":Anim:L_Knee_PV", 1.25),
            (":Anim:R_Thigh", ":Anim:R_Knee", ":Anim:R_Ankle", ":Anim:R_Knee_PV", 1.25)])
        self.assertEqual(len(context["pole_vectors"]), 2)
        self.assertEqual(result["mirror"]["locator"], ":Anim:R_Knee_PV")
        self.assertEqual(env["mirrorName"]("Bip001FBXASC032LFBXASC032Calf"),
                         "Bip001FBXASC032RFBXASC032Calf")
        self.assertFalse(env["DefaultSetting"]()["mirror"])

    def test_mirror_checks_both_sides_before_building(self):
        cmds = SimpleNamespace(ls=lambda name, **kw: [name] if "R_Ankle" not in name else [],
                               objExists=lambda name: False)
        env = scope(cmds=cmds, rt=SimpleNamespace(leaf=lambda name: name.split(":")[-1]))
        calls = []
        env["createPoleVector"] = lambda *args: calls.append(args)
        with self.assertRaisesRegex(ValueError, "expected one joint"):
            env["Run"]({"start": "L_Thigh", "middle": "L_Knee", "end": "L_Ankle", "mirror": True},
                       {"source_namespace_animation": "Anim"})
        self.assertEqual(calls, [])

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
        self.assertEqual(nodes[name + "_StartEndLength"], "multiplyDivide")
        self.assertEqual(attrs[name + "_StartEndLength.operation"], 3)
        self.assertEqual(attrs[name + "_StartEndLength.input2X"], 0.5)
        self.assertEqual(connections[name + "_StartEndLength.input1X"], name + "_ChordLengthSquared.outputX")
        self.assertEqual(nodes[name + "_PoleDistance"], "multiplyDivide")
        self.assertEqual(attrs[name + "_PoleDistance.input2X"], 0.5)
        self.assertEqual(connections[name + "_PoleDistance.input1X"], name + "_StartEndLength.outputX")
        for axis in "XYZ":
            self.assertEqual(connections[name + "_PoleOffset.input2" + axis], name + "_PoleDistance.outputX")
        self.assertFalse(attrs[name + ".inheritsTransform"])
        self.assertNotIn("multDoubleLinear", nodes.values())
        self.assertNotIn("distanceBetween", nodes.values())
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
