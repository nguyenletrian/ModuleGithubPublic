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
        self.assertTrue(settings["maintain_offset"])

    def test_recover_pairs_saved_in_wrong_namespace_key(self):
        env = scope("PairData", "NormalizeSettings")
        normalize = env["NormalizeSettings"]
        stale = [{"from": "Old", "to": "OldFK"}]
        edited = [{"from": "R_Hand", "to": "R_Hand_FK", "mirror": True}]
        fixed = normalize({"from_role": "Anim", "to_role": edited, "pairs": stale})
        self.assertEqual(fixed["from_role"], "Anim")
        self.assertEqual(fixed["to_role"], "Rig")
        self.assertTrue(fixed["maintain_offset"])
        self.assertFalse(normalize({"maintain_offset": False})["maintain_offset"])
        for source in ("Rig", "Anim", "REF"):
            for target in ("Rig", "Anim", "REF"):
                data = normalize({"from_role": source, "to_role": target})
                self.assertEqual((data["from_role"], data["to_role"]), (source, target))
        self.assertEqual(fixed["pairs"], [env["PairData"](edited[0])])
        self.assertEqual(normalize({"to_role": [], "pairs": stale})["pairs"], [])
        self.assertEqual(normalize({"to_role": "Rig", "pairs": stale})["pairs"],
                         [env["PairData"](stale[0])])

    def test_ui_keeps_pair_and_namespace_widget_keys_separate(self):
        source = (ROOT / "UIs/Retarget.py").read_text(encoding="utf-8")
        self.assertIn("self.widgets[role_key] = (\"choice\", role)", source)
        self.assertIn("self._make_rotate_pairs(parent, data[\"pairs\"])", source)
        self.assertIn("self.widgets[key] = (kind, self.rotate_pair_rows)", source)

    def test_general_namespace_roles_override_stale_context(self):
        env = scope("_namespaces")
        self.assertEqual(env["_namespaces"]({
            "reference_namespaces": {"reference_pose": "REF", "old_animations": "Anim", "new_rig": "Rig"},
            "reference_pose_namespace": "OldREF",
            "source_namespace_animation": "REF",
            "target_namespace": "Anim"}), ("REF", "Rig"))
        self.assertEqual(env["_namespaces"]({
            "reference_namespaces": {"old_animations": "Anim", "new_rig": "Rig"},
            "reference_pose_loaded": False}, "Anim"), ("Anim", "Rig"))
        self.assertEqual(env["_namespaces"]({
            "reference_pose_namespace": "REF", "target_namespace": "Rig"}),
                         ("REF", "Rig"))

    def test_all_namespace_directions(self):
        env = scope("_namespaces")
        context = {"reference_namespaces": {"reference_pose": "PoseNS",
                   "old_animations": "ClipNS", "new_rig": "RigNS"}}
        roles = {"REF": "PoseNS", "Anim": "ClipNS", "Rig": "RigNS"}
        for source in roles:
            for target in roles:
                self.assertEqual(env["_namespaces"](context, source, target),
                                 (roles[source], roles[target]))

    def test_resolve_absolute_namespace_ignores_wrong_namespace_matches(self):
        def ls(name, **kwargs):
            self.assertEqual(name, ":Rig:Hand")
            return ["|REF:Root|REF:Hand", "|Anim:Root|Anim:Hand", "|Rig:Root|Rig:Hand"]
        env = scope("_resolve", rt=SimpleNamespace(leaf=lambda name: name.split(":")[-1]),
                    cmds=SimpleNamespace(ls=ls, nodeType=lambda node: "transform"))
        self.assertEqual(env["_resolve"]("Rig", "REF:Hand"), "|Rig:Root|Rig:Hand")

    def test_constraint_types(self):
        calls = []
        def make(kind):
            def constraint(source, target, **kw):
                self.assertEqual((source, target), ("Extra", "Control"))
                calls.append((kind, kw["maintainOffset"]))
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
            for maintain in (True, False):
                calls.clear()
                result = env["_connect"]("Extra", "Control",
                                        {"translate": tr, "rotate": ro, "scale": sc},
                                        maintain)
                self.assertEqual(result, expected)
                self.assertEqual(calls, [(kind, maintain) for kind in expected])

    def test_offsets_captured_before_constraints_using_selected_driver(self):
        events = []
        def offset(ref, target, maintain_offset):
            events.append(("offset", ref, target, maintain_offset))
            return [1.0] * 16
        def extra(anim, target, matrix):
            events.append(("extra", anim, target))
            return anim + "|extra"
        def connect(joint, target, pair, maintain_offset):
            events.append(("constraint", joint, target, maintain_offset))
            return ["constraint_" + target]
        env = scope("PairData", "NormalizeSettings", "_mirror_name", "_expand_pairs", "_namespaces", "Run",
                    re=re,
                    _offset=offset, _build_extra=extra, _connect=connect,
                    _resolve=lambda ns, name: ns + ":" + name,
                    rt=SimpleNamespace(leaf=lambda node: node.split(":")[-1]),
                    cmds=SimpleNamespace(objExists=lambda node: True))
        context = {"reference_pose_namespace": "REF", "target_namespace": "Rig"}
        result = env["Run"]({"pairs": [
            {"from": "Hand", "to": "HandFK"},
            {"from": "Finger", "to": "FingerFK"},
            {"from": "", "to": "", "rotate": False}]}, context)
        self.assertEqual(events[:2], [
            ("offset", "REF:Hand", "Rig:HandFK", True),
            ("offset", "REF:Finger", "Rig:FingerFK", True)])
        self.assertEqual(events[2], ("extra", "REF:Hand", "Rig:HandFK"))
        self.assertEqual(events[3], ("constraint", "REF:Hand|extra", "Rig:HandFK", True))
        self.assertEqual(context["constraint_pairs"][0]["source"], "REF:Hand")
        self.assertEqual(context["constraint_pairs"][0]["source_role"], "REF")
        self.assertEqual(result["pairs"], 2)
        self.assertFalse(context["baked"])
        self.assertEqual(len(context["constraint_pairs"]), 2)
        events.clear()
        context = {"source_namespace_animation": "Anim", "target_namespace": "Rig",
                   "reference_pose_loaded": False}
        env["Run"]({"from_role": "Anim", "to_role": "Rig", "maintain_offset": False, "pairs": [
            {"from": "Hand", "to": "HandFK"}]}, context)
        self.assertEqual(events[0], ("offset", "Anim:Hand", "Rig:HandFK", False))
        self.assertEqual(events[1], ("extra", "Anim:Hand", "Rig:HandFK"))
        self.assertEqual(events[2], ("constraint", "Anim:Hand|extra", "Rig:HandFK", False))
        events.clear()
        context = {"reference_pose_namespace": "REF", "source_namespace_animation": "Anim"}
        env["Run"]({"from_role": "Anim", "to_role": "REF", "pairs": [
            {"from": "Hand", "to": "Hand"}]}, context)
        self.assertEqual(events[0], ("offset", "Anim:Hand", "REF:Hand", True))
        self.assertEqual(events[2], ("constraint", "Anim:Hand|extra", "REF:Hand", True))
        self.assertEqual(context["constraint_pairs"][0]["target_role"], "REF")
        events.clear()
        context = {"target_namespace": "Rig"}
        env["Run"]({"from_role": "Rig", "to_role": "Rig", "pairs": [
            {"from": "Driver", "to": "Driven"}]}, context)
        self.assertEqual(events[0], ("offset", "Rig:Driver", "Rig:Driven", True))
        with self.assertRaisesRegex(ValueError, "cycle"):
            env["Run"]({"from_role": "Rig", "to_role": "Rig", "pairs": [
                {"from": "Self", "to": "Self"}]}, context)

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

    def test_maintain_off_uses_identity_instead_of_target_offset(self):
        calls = []
        class Matrix:
            def inverse(self):
                calls.append("inverse")
                return self
            def __mul__(self, other):
                return [2.0] * 16
        def world(node):
            calls.append(node)
            return Matrix()
        env = scope("_offset", _world=world)
        identity = [float(i % 5 == 0) for i in range(16)]
        self.assertEqual(env["_offset"]("From", "To", False), identity)
        self.assertEqual(calls, [])
        self.assertEqual(env["_offset"]("From", "To", True), [2.0] * 16)
        self.assertEqual(calls, ["To", "From", "inverse"])

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
