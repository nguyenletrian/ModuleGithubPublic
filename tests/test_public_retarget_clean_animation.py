"""Offline contracts for exact consecutive key cleanup."""
import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_CleanAnimation.py"


def scope(**dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = dict(re=re, _TIME_CURVES=("animCurveTA", "animCurveTL", "animCurveTT",
                                   "animCurveTU"), **dependencies)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(STEP), "exec"), env)
    return env


class CleanAnimationTests(unittest.TestCase):
    def test_duplicate_values(self):
        env = scope()
        self.assertEqual(env["_removal_indices"]([0, 0, 0, 10, 10, 20, 0, 0]),
                         ([1, 7], False))
        self.assertEqual(env["_removal_indices"]([0, 0, 0, 0, 10, 10]),
                         ([1, 2, 5], False))
        self.assertEqual(env["_removal_indices"]([0, 10, 10, 10, 20]),
                         ([2], False))
        self.assertEqual(env["_removal_indices"]([0, 0, 5, 5], trim_tail=False),
                         ([], False))
        self.assertEqual(env["_removal_indices"]([0, 5, 5, 5], trim_tail=False),
                         ([2], False))
        self.assertEqual(env["_removal_indices"]([0, 0, 0]), ([0, 1, 2], True))
        self.assertEqual(env["_removal_indices"]([1, 1, 1]), ([1, 2], False))
        self.assertEqual(env["_removal_indices"]([0, 1e-9]), ([], False))
        self.assertEqual(env["_removal_indices"]([0]), ([0], True))
        self.assertEqual(env["_removal_indices"]([]), ([], False))

    def test_delete_ranges_descending(self):
        self.assertEqual(list(scope()["_ranges"]([1, 2, 4, 7, 8])), [(7, 8), (4, 4), (1, 2)])

    def test_only_controls_and_time_curves(self):
        cuts, writes, deleted = [], [], []
        nodes = ["|Rig:FK", "|Rig:Joint", "|Rig:Group", "|Other:FK"]
        attrs = {"rotateX": "moving", "rotateY": "zero", "scaleX": "one",
                 "rotateZ": "sdk", "translateX": "layered", "translateY": "shared"}
        values = {"moving": [0, 0, 5, 5], "zero": [0, 0, 0], "one": [1, 1]}
        def keyframe(name, **kw):
            if kw.get("name"):
                attr = name.rsplit(".", 1)[-1]
                return ["layer1", "layer2"] if attr == "translateX" else [attrs[attr]]
            return values[name]
        def cut(curve, **kw):
            first, last = kw["index"]
            cuts.append((curve, (first, last)))
            del values[curve][first:last + 1]
        def delete(curve):
            deleted.append(curve)
            del values[curve]
        def node_type(node):
            if node.endswith(":Joint"):
                return "joint"
            if node.startswith("|"):
                return "transform"
            return "animCurveUU" if node == "sdk" else "animCurveTA"
        env = scope(rt=SimpleNamespace(mapping_candidates=lambda ns: nodes,
                        leaf=lambda node: node.rsplit(":", 1)[-1]),
                    cmds=SimpleNamespace(nodeType=node_type,
                        listRelatives=lambda node, **kw: ["shape"] if node.endswith(":FK") else [],
                        listAttr=lambda node, **kw: list(attrs),
                        keyframe=keyframe,
                        listConnections=lambda plug, **kw: ["a", "b"] if plug.startswith("shared") else ["a"],
                        cutKey=cut, delete=delete,
                        objExists=lambda curve: curve in values,
                        isConnected=lambda source, plug: True,
                        getAttr=lambda plug, **kw: 0 if plug.endswith(".postInfinity") or kw.get("lock") else True,
                        setAttr=lambda *args: writes.append(args)))
        result = env["Run"]({}, {"target_namespace": "Rig"})
        self.assertEqual(result["controls"], 1)
        self.assertEqual(result["removed_keys"], 5)
        self.assertEqual(result["zero_channels"], 1)
        self.assertEqual(result["skipped_channels"], 3)
        self.assertEqual(cuts, [("moving", (3, 3)), ("one", (1, 1))])
        self.assertEqual(deleted, ["zero"])
        self.assertEqual(writes, [("|Rig:FK.rotateY", 0)])


    def test_single_zero_key_is_removed_but_nonzero_key_is_preserved(self):
        values = {"zero": [0], "one": [1]}
        deleted, writes = [], []
        def keyframe(name, **kw):
            if kw.get("name"):
                return ["zero" if name.endswith(".rotateX") else "one"]
            return values[name]
        def delete(curve):
            deleted.append(curve)
            del values[curve]
        env = scope(rt=SimpleNamespace(mapping_candidates=lambda ns: ["|Rig:FK"],
                                        leaf=lambda node: "FK"),
                    cmds=SimpleNamespace(nodeType=lambda node: "transform" if node.startswith("|") else "animCurveTA",
                        listRelatives=lambda *a, **kw: ["shape"],
                        listAttr=lambda *a, **kw: ["rotateX", "scaleX"],
                        keyframe=keyframe, listConnections=lambda *a, **kw: ["onePlug"],
                        getAttr=lambda plug, **kw: 0 if plug.endswith(".postInfinity") or kw.get("lock") else True,
                        isConnected=lambda *a: True, delete=delete,
                        setAttr=lambda *a: writes.append(a)))
        result = env["Run"]({}, {"target_namespace": "Rig"})
        self.assertEqual(deleted, ["zero"])
        self.assertEqual(values, {"one": [1]})
        self.assertEqual(writes, [("|Rig:FK.rotateX", 0)])
        self.assertEqual(result["removed_keys"], 1)
        self.assertEqual(result["zero_channels"], 1)


    def test_baked_pairblend_zero_key_and_near_zero_at_frame_zero(self):
        values = {"blendCurve": [0.0], "tinyCurve": [2e-8], "nonzero": [0.01]}
        curves = {"rotateX": "blendCurve", "rotateY": "tinyCurve", "rotateZ": "nonzero"}
        outputs = {"blendCurve": "pairBlend1.inRotateX2", "tinyCurve": "|Rig:FK.rotateY",
                   "nonzero": "|Rig:FK.rotateZ"}
        writes, deleted = [], []
        def keyframe(name, **kw):
            if kw.get("name"):
                return [curves[name.rsplit(".", 1)[-1]]]
            if kw.get("timeChange"):
                return [0]
            return values[name]
        def delete(curve):
            deleted.append(curve)
            del values[curve]
        def node_type(node):
            if node == "pairBlend1":
                return "pairBlend"
            return "transform" if node.startswith("|") else "animCurveTA"
        env = scope(rt=SimpleNamespace(mapping_candidates=lambda ns: ["|Rig:FK"],
                                        leaf=lambda node: "FK"),
                    cmds=SimpleNamespace(nodeType=node_type,
                        listRelatives=lambda *a, **kw: ["shape"],
                        listAttr=lambda *a, **kw: list(curves),
                        keyframe=keyframe,
                        listConnections=lambda plug, **kw: [outputs[plug.split(".")[0]]],
                        getAttr=lambda plug, **kw: False,
                        isConnected=lambda source, plug: outputs[source.split(".")[0]] == plug,
                        delete=delete, setAttr=lambda *a: writes.append(a)))
        result = env["Run"]({}, {"target_namespace": "Rig"})
        self.assertEqual(deleted, ["blendCurve", "tinyCurve"])
        self.assertEqual(writes, [("pairBlend1.inRotateX2", 0), ("|Rig:FK.rotateY", 0)])
        self.assertEqual(values, {"nonzero": [0.01]})
        self.assertEqual(result["removed_keys"], 2)


if __name__ == "__main__":
    unittest.main()
