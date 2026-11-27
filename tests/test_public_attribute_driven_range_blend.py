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
    def test_auto_rest_multiple_constraints(self):
        kinds = {"Parent": "parentConstraint", "Position": "pointConstraint",
                 "Rotation": "orientConstraint"}
        aliases = {name: ["OriginalW0"] for name in kinds}
        nodes, attrs, connections, added, poses, events, matched = {}, {}, {}, [], {}, [], []
        matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 3, 4, 1]

        def constraint_command(name):
            def command(*args, **kwargs):
                if kwargs.get("query"):
                    return [name + "_Original"] if kwargs.get("targetList") else list(aliases[name])
                events.append(("add", name))
                added.append((name, args, kwargs))
                aliases[name].append("RestW1")
                return [name]
            return command

        def create_node(kind, name, **kwargs):
            nodes[name] = (kind, kwargs)
            return name

        def xform(node, **kwargs):
            if kwargs.get("query"):
                events.append(("capture", node))
                return matrix[:]
            poses[node] = kwargs["matrix"]

        def connect(src, dst, **kwargs):
            events.append(("connect", dst))
            connections[dst] = (src, kwargs)

        cmds = SimpleNamespace(
            objExists=lambda plug: True,
            nodeType=lambda name: kinds[name],
            ls=lambda name, **kwargs: [name],
            listConnections=lambda plug, **kwargs: [plug.split(".")[0] + "_Driven"],
            listRelatives=lambda node, **kwargs: ["|Rig|Group"],
            xform=xform, createNode=create_node,
            getAttr=lambda plug: 3,
            matchTransform=lambda rest, target, **kwargs: matched.append((rest, target, kwargs)),
            setAttr=lambda plug, value: attrs.update({plug: value}),
            connectAttr=connect,
            parentConstraint=constraint_command("Parent"),
            pointConstraint=constraint_command("Position"),
            orientConstraint=constraint_command("Rotation"))
        env = scope(cmds=cmds)
        env["createBlend"]("Driver", "AutoFollow", 0, 1, 1, list(kinds))
        blend = "Driver_AutoFollow_RangeBlend"
        self.assertEqual(events[:3], [("capture", name + "_Driven") for name in kinds])
        self.assertEqual(added, [(name, (name + "_Rest", name + "_Driven"),
                                 dict(weight=0, **({"maintainOffset": True} if name == "Parent" else {}))) for name in kinds])
        self.assertEqual(matched, [(name + "_Rest", name + "_Original",
                                    {"rotation": True, "position": False, "scale": False}) for name in kinds])
        first_weight = next(i for i, event in enumerate(events) if event[0] == "connect" and event[1].endswith(".OriginalW0"))
        self.assertTrue(all(events.index(("add", name)) < first_weight for name in kinds))
        self.assertEqual(sum(kind == "remapValue" for kind, _ in nodes.values()), 1)
        self.assertEqual(sum(kind == "reverse" for kind, _ in nodes.values()), 1)
        self.assertEqual(attrs[blend + ".value[0].value_Interp"], 1)
        for name in kinds:
            self.assertEqual(nodes[name + "_Rest"], ("transform", {"parent": "|Rig|Group"}))
            self.assertEqual(poses[name + "_Rest"], matrix)
            self.assertEqual(attrs[name + "_Rest.rotateOrder"], 3)
            self.assertEqual(connections[name + ".OriginalW0"], (blend + ".outValue", {"force": True}))
            self.assertEqual(connections[name + ".RestW1"], (blend + "_Reverse.outputX", {}))

    def test_legacy_json_discards_manual_targets(self):
        env = scope()
        data = {"driverObject": "Driver", "driverAttr": "AutoFollow",
                "driverMin": 0, "driverMax": 1, "driverDefault": 1,
                "drivens": [{"constraint": "Constraint", "target": "OldRef"}]}
        self.assertEqual(env["blendArguments"](data),
                         ("Driver", "AutoFollow", 0.0, 1.0, 1.0, ["Constraint"]))
        self.assertEqual(env["normalizeItem"](data)["drivens"],
                         [{"constraint": "Constraint"}])

    def test_single_pass_export(self):
        env = scope()
        data = {"driverObject": "Driver", "driverAttr": "AutoFollow",
                "driverMin": 0, "driverMax": 1, "driverDefault": 1,
                "drivens": [{"constraint": "Constraint"}]}
        source = env["buildScript"]([data])
        compile(source, "<range blend export>", "exec")
        self.assertIn("createBlend(*('Driver', 'AutoFollow', 0.0, 1.0, 1.0, ['Constraint']))", source)
        self.assertNotIn("raise ", source)
        self.assertNotIn("validateItem", source)
        self.assertIn("maintainOffset=True", source)
        self.assertIn("targetList=True", source)
        self.assertNotIn("NLTA_", source)


if __name__ == "__main__":
    unittest.main()
