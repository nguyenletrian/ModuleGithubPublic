"""Offline contracts for Attribute Driven Range Blend."""
import ast
import inspect
import itertools
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

STEP = Path(__file__).resolve().parents[1] / "UIs/ScenePattern/Scene_Pattern_AttributeDrivenRangeBlend.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    env = dict(inspect=inspect, itertools=itertools, **dependencies)
    exec(compile(ast.Module(body=[node for node in tree.body
                                  if isinstance(node, ast.FunctionDef)],
                            type_ignores=[]), str(STEP), "exec"), env)
    return env


class AttributeDrivenRangeBlendTests(unittest.TestCase):
    def test_auto_rest_multiple_constraints(self):
        kinds = {"Parent": "parentConstraint", "Position": "pointConstraint",
                 "Rotation": "orientConstraint"}
        aliases = {name: ["OriginalW0"] for name in kinds}
        nodes, attrs, connections, added, poses, events, mapped = {}, {}, {}, [], {}, [], []
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
                if node.endswith("_Driven"):
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
            setAttr=lambda plug, value: attrs.update({plug: value}),
            connectAttr=connect,
            parentConstraint=constraint_command("Parent"),
            pointConstraint=constraint_command("Position"),
            orientConstraint=constraint_command("Rotation"))
        env = scope(cmds=cmds)
        def map_matrix(rest, target):
            mapped.append((rest, target))
            return rest
        env["mappedRestMatrix"] = map_matrix
        drivens = [(name, "|Rig|RestSpace" if name == "Parent" else "") for name in kinds]
        env["createBlend"]("Driver", "AutoFollow", 0, 1, 1, drivens)
        blend = "Driver_AutoFollow_RangeBlend"
        self.assertEqual(events[:3], [("capture", name + "_Driven") for name in kinds])
        self.assertEqual(added, [(name, (name + "_Rest", name + "_Driven"),
                                 dict(weight=0, **({"maintainOffset": True} if name == "Parent" else {}))) for name in kinds])
        self.assertEqual(mapped, [(matrix, matrix), (matrix, matrix)])
        first_weight = next(i for i, event in enumerate(events) if event[0] == "connect" and event[1].endswith(".OriginalW0"))
        self.assertTrue(all(events.index(("add", name)) < first_weight for name in kinds))
        self.assertEqual(sum(kind == "remapValue" for kind, _ in nodes.values()), 1)
        self.assertEqual(sum(kind == "reverse" for kind, _ in nodes.values()), 1)
        for index in (0, 1):
            prefix = blend + ".value[{}].value_".format(index)
            self.assertEqual(attrs[prefix + "Position"], index)
            self.assertEqual(attrs[prefix + "FloatValue"], index)
            self.assertEqual(attrs[prefix + "Interp"], 1)
        for name in kinds:
            parent = "|Rig|RestSpace" if name == "Parent" else "|Rig|Group"
            self.assertEqual(nodes[name + "_Rest"], ("transform", {"parent": parent}))
            self.assertEqual(poses[name + "_Rest"], matrix)
            self.assertEqual(attrs[name + "_Rest.rotateOrder"], 3)
            if name in ("Parent", "Rotation"):
                self.assertEqual(attrs[name + ".interpType"], 2)
            else:
                self.assertNotIn(name + ".interpType", attrs)
            self.assertEqual(connections[name + ".OriginalW0"], (blend + ".outValue", {"force": True}))
            self.assertEqual(connections[name + ".RestW1"], (blend + "_Reverse.outputX", {}))

    def test_signed_mapping_preserves_rest_tilt(self):
        env = scope()
        c, s = math.cos(math.radians(12)), math.sin(math.radians(12))
        rest = ((c, s, 0), (-s, c, 0), (0, 0, 1))
        target = ((0, 0, 1), (0, 1, 0), (-1, 0, 0))
        self.assertEqual(env["mapAxes"](rest, target), (rest[2], rest[1], (-c, -s, 0)))
        self.assertEqual(env["mapAxes"](rest, ((1, 0, 0), (0, 1, 0), (0, 0, 1))), rest)

    def test_legacy_json_discards_manual_targets(self):
        env = scope()
        data = {"driverObject": "Driver", "driverAttr": "AutoFollow",
                "driverMin": 0, "driverMax": 1, "driverDefault": 1,
                "drivens": [{"constraint": "Constraint", "target": "OldRef"}]}
        self.assertEqual(env["blendArguments"](data),
                         ("Driver", "AutoFollow", 0.0, 1.0, 1.0, [("Constraint", "")]))
        self.assertEqual(env["normalizeItem"](data)["drivens"],
                         [{"constraint": "Constraint", "restParent": ""}])
        data["drivens"][0]["restParent"] = "Uber_att"
        self.assertEqual(env["blendArguments"](data)[-1], [("Constraint", "Uber_att")])

    def test_single_pass_export(self):
        env = scope()
        data = {"driverObject": "Driver", "driverAttr": "AutoFollow",
                "driverMin": 0, "driverMax": 1, "driverDefault": 1,
                "drivens": [{"constraint": "Constraint", "restParent": "Uber_att"}]}
        source = env["buildScript"]([data])
        compile(source, "<range blend export>", "exec")
        self.assertIn("('Driver', 'AutoFollow', 0.0, 1.0, 1.0, [('Constraint', 'Uber_att')])", source)
        self.assertIn("for driverObject, driverAttr, driverMin, driverMax, driverDefault, drivens in BLEND_DATA:", source)
        self.assertNotIn("def createBlend(", source)
        self.assertIn('cmds.setAttr(constraint + ".interpType", 2)', source)
        self.assertNotIn("try:", source)
        self.assertNotIn("except ", source)
        # The single-pass loop must contain exactly the tested runtime builder body.
        main = ast.parse(source).body[0]
        loop = next(node for node in main.body if isinstance(node, ast.For))
        runtime = next(node for node in ast.parse(STEP.read_text(encoding="utf-8")).body
                       if isinstance(node, ast.FunctionDef) and node.name == "createBlend")
        self.assertEqual(ast.dump(ast.Module(body=loop.body, type_ignores=[])),
                         ast.dump(ast.Module(body=runtime.body, type_ignores=[])))
        compile(env["buildScript"]([]), "<empty range blend export>", "exec")
        self.assertNotIn("raise ", source)
        self.assertNotIn("validateItem", source)
        self.assertIn("maintainOffset=True", source)
        self.assertIn("targetList=True", source)
        self.assertIn("def mapAxes(", source)
        self.assertNotIn("cmds.matchTransform", source)
        self.assertNotIn("NLTA_", source)


if __name__ == "__main__":
    unittest.main()
