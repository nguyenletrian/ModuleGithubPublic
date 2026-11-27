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
    def test_multiple_constraint_types_share_one_blend(self):
        nodes, attrs, connections, disconnects, added = {}, {}, {}, [], []
        kinds = {"Parent": "parentConstraint", "Position": "pointConstraint",
                 "Rotation": "orientConstraint"}
        aliases = {name: ["OldAW0", "OldBW1"] for name in kinds}
        def constraint_command(name):
            def command(*args, **kwargs):
                if kwargs.get("query"):
                    return list(aliases[name])
                added.append((name, args, kwargs))
                aliases[name].append("NewW2")
                return [name]
            return command
        def create_node(kind, name):
            nodes[name] = kind
            return name
        def set_attr(plug, value):
            attrs[plug] = value
        def connect(src, dst):
            connections[dst] = src
        cmds = SimpleNamespace(
            objExists=lambda plug: True,
            nodeType=lambda name: kinds[name],
            listConnections=lambda plug, **kwargs: [plug.split(".")[0] + "_Driven"],
            parentConstraint=constraint_command("Parent"),
            pointConstraint=constraint_command("Position"),
            orientConstraint=constraint_command("Rotation"),
            connectionInfo=lambda plug, **kwargs: "Control.AutoFollow" if plug.endswith("OldAW0") else "",
            getAttr=lambda plug: 0.6 if plug.endswith("OldAW0") else 0.4,
            createNode=create_node, setAttr=set_attr, connectAttr=connect,
            disconnectAttr=lambda src, dst: disconnects.append((src, dst)))
        env = scope(cmds=cmds)
        env["createBlend"]("Driver", "rotateX", 0, 90, 0,
                           [(name, name + "_New") for name in kinds])
        blend = "Driver_rotateX_RangeBlend"
        self.assertEqual(added, [(name, (name + "_New", name + "_Driven"),
                                 {"edit": True, "weight": 0}) for name in kinds])
        self.assertEqual(list(nodes.values()).count("remapValue"), 1)
        self.assertEqual(list(nodes.values()).count("reverse"), 1)
        self.assertEqual(attrs[blend + ".value[0].value_Interp"], 1)
        self.assertEqual(attrs[blend + ".inputMax"], 90)
        self.assertEqual(attrs[blend + ".outputMin"], 0)
        self.assertEqual(attrs[blend + ".outputMax"], 1)
        for name in kinds:
            prefix = name + "_RangeBlend"
            self.assertIn(("Control.AutoFollow", name + ".OldAW0"), disconnects)
            self.assertEqual(connections[prefix + "_Normalize01.input1X"], "Control.AutoFollow")
            self.assertEqual(attrs[prefix + "_Normalize02.input1X"], 0.4)
            self.assertEqual(connections[name + ".OldAW0"], prefix + "_Old01.outputX")
            self.assertEqual(connections[prefix + "_Old01.input1X"], prefix + "_Normalize01.outputX")
            self.assertEqual(connections[prefix + "_Old01.input2X"], blend + "_Reverse.outputX")
            self.assertEqual(connections[prefix + "_OldTotal.input1D[0]"], prefix + "_Normalize01.input1X")
            self.assertEqual(connections[prefix + "_Normalize01.input2X"], prefix + "_SafeTotal.outColorR")
            self.assertEqual(connections[name + ".NewW2"], blend + ".outValue")

    def test_legacy_single_driven_and_fixed_weight_range(self):
        env = scope()
        data = {"driverObject": "Driver", "driverAttr": "rotateX",
                "driverMin": -90, "driverMax": 90, "driverDefault": 0,
                "constraint": "Constraint", "target": "New",
                "blendMin": 0.2, "blendMax": 0.7, "smooth": True, "maintainOffset": True}
        self.assertEqual(env["blendArguments"](data),
                         ("Driver", "rotateX", -90.0, 90.0, 0.0, [("Constraint", "New")]))

    def test_single_pass_export(self):
        env = scope()
        data = {"driverObject": "Driver", "driverAttr": "rotateX",
                "driverMin": 0, "driverMax": 90,
                "constraint": "Constraint", "target": "New"}
        source = env["buildScript"]([data])
        compile(source, "<range blend export>", "exec")
        self.assertIn("createBlend(*('Driver', 'rotateX', 0.0, 90.0, 0.0, [('Constraint', 'New')]))", source)
        self.assertNotIn("maintainOffset", source)
        self.assertNotIn("smooth", source)
        self.assertNotIn("raise ", source)
        self.assertNotIn("validateItem", source)
        self.assertNotIn("NLTA_", source)


if __name__ == "__main__":
    unittest.main()
