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
        self.assertIn("('Proxy.f[7]', 'Control', '', '', 'orientConstraint')", source)
        self.assertIn("for face, child, parent, copy_transform, command in RIVET_DATA:", source)
        self.assertIn("constraintCommand = commands[command]", source)
        self.assertNotIn("getattr(", source)
        self.assertIn("cmds.parentConstraint", source)
        self.assertIn("cmds.pointConstraint", source)
        self.assertIn("cmds.orientConstraint", source)
        self.assertIn("mesh_shape, instance, edges = dag.fullPathName(), dag.instanceNumber(), polygon.getEdges()", source)
        self.assertIn("offset = cmds.createNode('transform', name=offset_name)", source)
        self.assertIn("child = cmds.parent(child, offset, absolute=True)[0]", source)
        self.assertIn("def connectRivetFollow(", source)
        for helper in ("createRivet", "offsetGroup", "faceEdges"):
            self.assertNotIn("def " + helper + "(", source)
            self.assertNotIn(helper + "(", source)
        compile(env["buildScript"]([]), "<empty rivet export>", "exec")
        self.assertNotIn("copySkinWeights", source)
        self.assertNotIn("createRivetPlane", source)
        self.assertNotIn("validateFace", source)
        self.assertNotIn("NLTA_", source)


    def test_vertex_rivet_single_pass_export(self):
        path = STEP.with_name("Scene_Pattern_RigRivet.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        env = dict(inspect=inspect)
        exec(compile(ast.Module(body=[node for node in tree.body
                                      if isinstance(node, ast.FunctionDef)],
                                type_ignores=[]), str(path), "exec"), env)
        data = {"vertexs": "Proxy.vtx[0]\nProxy.vtx[1]\nProxy.vtx[2]\nProxy.vtx[3]",
                "child": "Control", "followParent": True}
        source = env["buildScript"]([data])
        compile(source, "<vertex rivet export>", "exec")
        self.assertIn("for vertex_names, child, parent, copy_transform, command in RIVET_DATA:", source)
        self.assertIn("def createRivetPlane(", source)
        self.assertIn("def connectRivetFollow(", source)
        self.assertIn("offset = cmds.createNode('transform', name=offset_name)", source)
        self.assertIn("findRelatedSkinCluster", source)
        self.assertIn("cmds.copySkinWeights(", source)
        for helper in ("createRivet", "offsetGroup", "sourceSkin"):
            self.assertNotIn(helper + "(", source)
        self.assertNotIn("raise ", source)
        self.assertNotIn("try:", source)
        compile(env["buildScript"]([]), "<empty vertex rivet export>", "exec")

if __name__ == "__main__":
    unittest.main()
