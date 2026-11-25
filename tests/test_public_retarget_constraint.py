"""Offline contracts for REF-aligned live retarget constraints."""
import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "UIs/RetargetSteps/Retarget_Constraint.py"


def scope(*names, **dependencies):
    tree = ast.parse(STEP.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    env = dict(dependencies)
    module = ast.Module(body=[functions[name] for name in names],
                        type_ignores=[])
    exec(compile(module, str(STEP), "exec"), env)
    return env


class ConstraintTests(unittest.TestCase):
    def test_defaults(self):
        env = scope("PairData", "DefaultSetting", "Fields")
        settings = env["DefaultSetting"]()
        pair = settings["pairs"][0]
        self.assertEqual((settings["from_role"], settings["to_role"]), ("REF", "Rig"))
        self.assertNotIn("from_role", pair)
        self.assertNotIn("to_role", pair)
        self.assertEqual((pair["translate"], pair["rotate"], pair["scale"]),
                         (False, True, False))
        self.assertFalse(pair["mirror"])

    def test_constraint_types(self):
        calls = []
        def make(kind):
            def constraint(source, target, **kw):
                self.assertEqual((source, target), ("Extra", "Control"))
                self.assertFalse(kw["maintainOffset"])
                calls.append(kind)
                return [kind]
            return constraint
        env = scope("_connect", cmds=SimpleNamespace(
            **{name + "Constraint": make(name) for name in
               ("parent", "point", "orient", "scale")}))
        for tr, ro, sc, expected in [
            (True, True, True, ["parent", "scale"]),
            (True, False, False, ["point"]),
            (False, True, False, ["orient"]),
            (False, False, True, ["scale"])]:
            calls.clear()
            result = env["_connect"]("Extra", "Control",
                                    {"translate": tr, "rotate": ro, "scale": sc})
            self.assertEqual(result, expected)
            self.assertEqual(calls, expected)

    def test_offsets_captured_before_constraints_and_anim_resolution(self):
        events = []
        def offset(ref, target):
            events.append(("offset", ref, target))
            return [1.0] * 16
        def extra(anim, target, matrix):
            events.append(("extra", anim, target))
            return anim + "|extra"
        def connect(joint, target, pair):
            events.append(("constraint", joint, target))
            return ["constraint_" + target]
        env = scope("PairData", "_mirror_name", "_expand_pairs", "_namespaces", "Run",
                    re=re,
                    _offset=offset, _build_extra=extra, _connect=connect,
                    rt=SimpleNamespace(resolve=lambda ns, name: ns + ":" + name,
                                       leaf=lambda node: node.split(":")[-1]),
                    cmds=SimpleNamespace(objExists=lambda node: True))
        context = {"reference_pose_namespace": "REF",
                   "source_namespace_animation": "Anim", "target_namespace": "Rig"}
        result = env["Run"]({"pairs": [
            {"from": "Hand", "to": "HandFK"},
            {"from": "Finger", "to": "FingerFK"},
            {"from": "", "to": "", "rotate": False}]}, context)
        self.assertEqual(events[:2], [
            ("offset", "REF:Hand", "Rig:HandFK"),
            ("offset", "REF:Finger", "Rig:FingerFK")])
        self.assertEqual(events[2], ("extra", "Anim:Hand", "Rig:HandFK"))
        self.assertEqual(result["pairs"], 2)
        self.assertFalse(context["baked"])
        self.assertEqual(len(context["constraint_pairs"]), 2)
        events.clear()
        context["constraint_pairs"] = []
        env["Run"]({"from_role": "Anim", "to_role": "Rig", "pairs": [
            {"from": "Hand", "to": "HandFK"}]}, context)
        self.assertEqual(events[0], ("offset", "REF:Hand", "Rig:HandFK"))
        self.assertEqual(events[1], ("extra", "Anim:Hand", "Rig:HandFK"))

    def test_mirror_copies_trs_and_respects_explicit_opposite(self):
        env = scope("PairData", "_mirror_name", "_expand_pairs", re=re,
                    rt=SimpleNamespace(leaf=lambda node: node.split(":")[-1]))
        expand = env["_expand_pairs"]
        right = {"from": "Bip001FBXASC032RFBXASC032Hand",
                 "to": "R_Hand_FK", "mirror": True,
                 "translate": True, "rotate": False, "scale": True}
        pairs = expand([right])
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[1]["from"], "Bip001FBXASC032LFBXASC032Hand")
        self.assertEqual(pairs[1]["to"], "L_Hand_FK")
        self.assertEqual((pairs[1]["translate"], pairs[1]["rotate"], pairs[1]["scale"]),
                         (True, False, True))
        explicit = {"from": "CustomLeft", "to": "L_Hand_FK", "mirror": True}
        self.assertEqual(len(expand([right, explicit])), 2)
        self.assertEqual(expand([right, explicit])[1]["from"], "CustomLeft")
        self.assertEqual(len(expand([{"from": "Pelvis", "to": "Root", "mirror": True}])), 1)
        self.assertEqual(len(expand([{"from": "R_Hand", "to": "R_Hand_FK"}])), 1)

    def test_extra_joint_uses_bind_offset_matrix(self):
        calls = []
        parent = "|Anim:Root|Anim:Hand"
        def create(kind, **kw):
            calls.append((kind, kw))
            return "Anim:HandFK_extraJoint"
        env = scope("_build_extra",
                    rt=SimpleNamespace(leaf=lambda node: node.split(":")[-1]),
                    cmds=SimpleNamespace(createNode=create,
                        setAttr=lambda *args, **kw: calls.append((args, kw))))
        matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 3, 4, 1]
        joint = env["_build_extra"](parent, "Rig:HandFK", matrix)
        self.assertEqual(joint, parent + "|Anim:HandFK_extraJoint")
        self.assertEqual(calls[0], ("joint", {"name": ":Anim:HandFK_extraJoint",
                                              "parent": parent, "skipSelect": True}))
        self.assertEqual(calls[2], ((joint + ".offsetParentMatrix", *matrix),
                                    {"type": "matrix"}))


if __name__ == "__main__":
    unittest.main()
