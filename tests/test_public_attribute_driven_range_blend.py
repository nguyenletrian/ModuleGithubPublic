"""Offline contracts for Attribute Driven Range Blend."""
import ast
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace

STEP = Path(__file__).resolve().parents[1] / "UIs/ScenePattern/Scene_Pattern_AttributeDrivenRangeBlend.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    env = dict(inspect=inspect, **dependencies)
    exec(compile(ast.Module(body=[node for node in tree.body
                                  if isinstance(node, ast.FunctionDef)],
                            type_ignores=[]), str(STEP), "exec"), env)
    return env


class AttributeDrivenRangeBlendTests(unittest.TestCase):
    def test_add_target_and_preserve_existing_weight_network(self):
        nodes, attrs, connections, disconnects, added = {}, {}, {}, [], []
        aliases = ["OldAW0", "OldBW1"]
        def parent_constraint(*args, **kwargs):
            if kwargs.get("query"):
                return list(aliases)
            added.append((args, kwargs))
            aliases.append("NewW2")
            return ["Constraint"]
        def create_node(kind, name):
            nodes[name] = kind
            return name
        def set_attr(plug, value):
            attrs[plug] = value
        def connect(src, dst):
            connections[dst] = src
        cmds = SimpleNamespace(
            objExists=lambda plug: True,
            listConnections=lambda plug, **kwargs: ["Driven"],
            parentConstraint=parent_constraint,
            connectionInfo=lambda plug, **kwargs: "Control.AutoFollow" if plug.endswith("OldAW0") else "",
            getAttr=lambda plug: 0.6 if plug.endswith("OldAW0") else 0.4,
            createNode=create_node, setAttr=set_attr, connectAttr=connect,
            disconnectAttr=lambda src, dst: disconnects.append((src, dst)))
        env = scope(cmds=cmds)
        env["createBlend"]("Driver", "rotateX", 0, 90, 0,
                           "Constraint", "New", 0, 1, True, True)
        name = "Constraint_RangeBlend"
        self.assertEqual(added, [(("New", "Driven"), {"maintainOffset": True, "weight": 0})])
        self.assertEqual(attrs[name + ".value[0].value_Interp"], 2)
        self.assertEqual(attrs[name + ".inputMax"], 90)
        self.assertEqual(disconnects, [("Control.AutoFollow", "Constraint.OldAW0")])
        self.assertEqual(connections[name + "_Old01.input1X"], "Control.AutoFollow")
        self.assertEqual(attrs[name + "_Old02.input1X"], 0.4)
        self.assertEqual(connections["Constraint.OldAW0"], name + "_Old01.outputX")
        self.assertEqual(connections["Constraint.OldBW1"], name + "_Old02.outputX")
        self.assertEqual(connections[name + "_Old01.input2X"], name + "_Reverse.outputX")
        self.assertEqual(connections[name + "_OldTotal.input1D[0]"], name + "_Old01.input1X")
        self.assertEqual(connections[name + "_OldTotal.input1D[1]"], name + "_Old02.input1X")
        self.assertEqual(connections[name + "_New.input1X"], name + "_SafeTotal.outColorR")
        self.assertEqual(connections[name + "_New.input2X"], name + ".outValue")
        self.assertEqual(connections["Constraint.NewW2"], name + "_New.outputX")
        self.assertNotIn("parentConstraint", nodes.values())

    def test_single_pass_export(self):
        env = scope()
        data = {"driverObject": "Driver", "driverAttr": "rotateX",
                "driverMin": 0, "driverMax": 90,
                "constraint": "Constraint", "target": "New"}
        source = env["buildScript"]([data])
        compile(source, "<range blend export>", "exec")
        self.assertIn("createBlend(*('Driver', 'rotateX', 0.0, 90.0, 0.0, 'Constraint', 'New', 0.0, 1.0, True, True))", source)
        self.assertNotIn("raise ", source)
        self.assertNotIn("validateItem", source)
        self.assertNotIn("NLTA_", source)


if __name__ == "__main__":
    unittest.main()
