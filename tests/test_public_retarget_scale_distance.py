"""Offline checks for the four-vertex scale step."""
import ast
import math
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

STEP = Path(__file__).resolve().parents[1] / "UIs/RetargetSteps/Retarget_ScaleFromObjectDistance.py"


def scope(**deps):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    env = dict(math=math, re=re, **deps)
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)],
                            type_ignores=[]), str(STEP), "exec"), env)
    return env


class ScaleDistanceTests(unittest.TestCase):
    def test_current_scale_multiplied_by_world_distance_ratio(self):
        values = {"Rig:Root.scaleX": 2.0, "Rig:Root.scaleY": 3.0,
                  "Rig:Root.scaleZ": 4.0, "Rig:Root.globalScale": 2.5}
        positions = {"Anim:Mesh.vtx[0]": (0, 0, 0), "Anim:Mesh.vtx[1]": (6, 8, 0),
                     "Rig:Mesh.vtx[2]": (0, 0, 0), "Rig:Mesh.vtx[3]": (0, 3, 4)}
        cmds = SimpleNamespace(
            ls=lambda name, **kwargs: [name.lstrip(":")],
            nodeType=lambda name: "transform",
            xform=lambda name, **kwargs: positions[name],
            getAttr=lambda plug, **kwargs: True if kwargs.get("settable") else values[plug],
            setAttr=lambda plug, value: values.__setitem__(plug, value))
        rt = SimpleNamespace(leaf=lambda name: name.split(":")[-1],
                             resolve=lambda ns, name: ns + ":" + name,
                             _scale_plugs=lambda node, ns, attr: [node + "." + attr])
        env = scope(cmds=cmds, rt=rt)
        settings = env["DefaultSetting"]()
        settings.update(vertex1="Mesh.vtx[0]", vertex2="Mesh.vtx[1]",
                        vertex3="Mesh.vtx[2]", vertex4="Mesh.vtx[3]")
        settings["scale_target"]["object"] = "Root"
        context = {"source_namespace_animation": "Anim", "target_namespace": "Rig"}
        result = env["Run"](settings, context)
        self.assertEqual((result["distance1"], result["distance2"], result["ratio"]), (10, 5, 2))
        self.assertEqual([values["Rig:Root.scale" + a] for a in "XYZ"], [4, 6, 8])
        settings["scale_target"]["attributes"] = dict.fromkeys("XYZ", "globalScale")
        env["Run"](settings, context)
        self.assertEqual(values["Rig:Root.globalScale"], 5)
        settings["vertex4"] = "Mesh.vtx[2]"
        before = dict(values)
        with self.assertRaises(ValueError):
            env["Run"](settings, context)
        self.assertEqual(values, before)

    def test_only_single_vertices_accepted(self):
        env = scope()
        for name in ("Mesh", "Mesh.e[0]", "Mesh.vtx[0:2]"):
            with self.assertRaises(ValueError):
                env["vertexPosition"]("Anim", name)


if __name__ == "__main__":
    unittest.main()
