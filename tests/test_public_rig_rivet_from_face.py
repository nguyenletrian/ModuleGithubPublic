"""Offline contracts for a rivet on an existing mesh face."""
import ast
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace

STEP = Path(__file__).resolve().parents[1] / "UIs/ScenePattern/Scene_Pattern_RigRivetFromFace.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    env = dict(inspect=inspect, **dependencies)
    exec(compile(ast.Module(body=[node for node in tree.body
                                  if isinstance(node, ast.FunctionDef)],
                            type_ignores=[]), str(STEP), "exec"), env)
    return env


class RigRivetFromFaceTests(unittest.TestCase):
    def test_uses_existing_mesh_edges_without_new_geometry(self):
        nodes, attrs, connections = {}, {}, {}
        def create(kind, name, **kwargs):
            nodes[name] = kind
            return name
        def connect(src, dst):
            connections[dst] = src
        def set_attr(plug, *args, **kwargs):
            attrs[plug] = args[0] if len(args) == 1 else args
        cmds = SimpleNamespace(createNode=create, connectAttr=connect,
                               setAttr=set_attr, spaceLocator=lambda name: [name],
                               parent=lambda obj, parent, **kwargs: [parent + "|" + obj])
        env = scope(cmds=cmds)
        env["faceEdges"] = lambda face: ("|Proxy|ProxyShape", 0, [12, 19, 31, 24])
        result = env["createRivet"]("Proxy.f[42]", "", "|Rivets", "", None)
        name = "Proxy_Face42_Rivet"
        self.assertEqual(attrs[name + "_EdgeA.edgeIndex[0]"], 12)
        self.assertEqual(attrs[name + "_EdgeB.edgeIndex[0]"], 31)
        self.assertEqual(connections[name + "_EdgeA.inputMesh"], "|Proxy|ProxyShape.worldMesh[0]")
        self.assertEqual(connections[name + "_EdgeB.inputMesh"], "|Proxy|ProxyShape.worldMesh[0]")
        self.assertEqual(connections["|Rivets|" + name + "_Loc.translate"], name + "_POSI.position")
        self.assertEqual(result["face"], "Proxy.f[42]")
        self.assertNotIn("skinCluster", nodes.values())
        self.assertNotIn("mesh", nodes.values())
        self.assertFalse(any(plug.startswith("|Proxy") for plug in attrs))

    def test_validate_single_quad_and_follow_mode(self):
        cmds = SimpleNamespace(ls=lambda face, **kwargs: [face])
        env = scope(cmds=cmds)
        env["faceEdges"] = lambda face: ("ProxyShape", 0, [4, 9, 3, 8])
        self.assertEqual(env["validateFace"]("Proxy.f[7]"), "Proxy.f[7]")
        env["faceEdges"] = lambda face: ("ProxyShape", 0, [4, 9, 3])
        with self.assertRaisesRegex(ValueError, "quad"):
            env["validateFace"]("Proxy.f[7]")
        self.assertEqual(env["rivetArguments"]({"face": "Proxy.f[7]",
                         "child": "Control", "followPosition": True})[-1], "pointConstraint")

    def test_export_contains_only_direct_face_network(self):
        env = scope()
        source = env["buildScript"]([{"face": "Proxy.f[7]", "child": "Control",
                                     "followRotation": True}])
        compile(source, "<rivet from face export>", "exec")
        self.assertIn("createRivet('Proxy.f[7]', 'Control', '', '', cmds.orientConstraint)", source)
        self.assertNotIn("copySkinWeights", source)
        self.assertNotIn("createRivetPlane", source)
        self.assertNotIn("validateFace", source)
        self.assertNotIn("NLTA_", source)


if __name__ == "__main__":
    unittest.main()
