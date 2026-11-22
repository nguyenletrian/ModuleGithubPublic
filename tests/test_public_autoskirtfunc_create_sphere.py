"""Offline regression for AutoSkirtFunc's manual NURBS sphere preview button."""
import ast
import math
from pathlib import Path
import re
import types
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "UIs" / "ScenePattern"
          / "Scene_Pattern_RigAutoSkirtFunc.py")


class FakeMaya:
    def __init__(self):
        self.values = {
            "sphere_input": "AutoSkirt_Knee1_Sphere",
            "start_input": "|Rig|Knee",
            "end_input": "|Rig|Foot",
        }
        self.positions = {
            "|Rig|Knee": [1.0, 2.0, 3.0],
            "|Rig|Foot": [1.0, 4.0, 3.0],
            "|Rig|DrivenA": [4.0, 2.0, 3.0],
            "|Rig|DrivenB": [1.0, 2.0, 8.0],
        }
        self.selected = ["|Rig|Body.vtx[1:30]"]
        self.context = "artAttrSkinContext"
        self.objects = set(self.positions)
        self.created = []
        self.xforms = []
        self.aims = []
        self.normalized = []
        self.identity = []
        self.deleted = []
        self.undo_events = []
        self.warnings = []
        self.error_on_normalize = False

    def textField(self, name, **kwargs):
        assert kwargs == {"query": True, "text": True}
        return self.values[name]

    def objExists(self, name):
        return name in self.objects

    def ls(self, name=None, **kwargs):
        if kwargs.get("selection"):
            return list(self.selected)
        return [name] if name in self.objects else []

    def nodeType(self, name):
        return "joint" if name in self.positions else "transform"

    def xform(self, name, **kwargs):
        if kwargs.get("query"):
            assert kwargs.get("rotatePivot") and kwargs.get("worldSpace")
            return list(self.positions[name])
        if kwargs.get("worldSpace") and "translation" in kwargs:
            self.xforms.append((name, tuple(kwargs["translation"])))
            return
        raise AssertionError(kwargs)

    def currentCtx(self):
        return self.context

    def undoInfo(self, **kwargs):
        self.undo_events.append(kwargs)

    def undo(self):
        self.undo_events.append({"undo": True})

    def sphere(self, **kwargs):
        self.created.append(kwargs)
        name = kwargs["name"]
        self.objects.add(name)
        self.selected = [name]
        self.context = "selectSuperContext"
        return [name]

    def pointOnSurface(self, shape, **kwargs):
        self.sample = (shape, kwargs)
        return [0.0, 0.0, 1.0]

    def spaceLocator(self, **kwargs):
        name = kwargs["name"]
        self.objects.add(name)
        return [name]

    def aimConstraint(self, target, sphere, **kwargs):
        self.aims.append((target, sphere, kwargs))
        return ["testAimConstraint"]

    def delete(self, names):
        self.deleted.append(names)

    def makeIdentity(self, sphere, **kwargs):
        self.identity.append((sphere, kwargs))

    def warning(self, message):
        self.warnings.append(message)

    def select(self, values=None, **kwargs):
        if kwargs.get("clear"):
            self.selected = []
        else:
            self.selected = values

    def setToolTo(self, name):
        self.context = name


def isolate_create(fake):
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    proc = next(node for node in module.body if isinstance(node, ast.FunctionDef)
                and node.name == "createSphereFromRow")
    sphere_name = fake.values["sphere_input"]
    def normalize(sphere):
        fake.normalized.append(sphere)
        if fake.error_on_normalize:
            raise RuntimeError("failed 0-1 rebuild")
        return {"U": (0.0, 1.0), "V": (0.0, 1.0)}
    scope = {
        "cmds": fake,
        "math": math,
        "re": re,
        "getControls": lambda row: ["|Rig|DrivenA", "|Rig|DrivenB"],
        "skirtShape": lambda sphere, kind: sphere + "Shape",
        "sphereUvDomain": lambda sphere: {
            "U": (0.0, math.pi*2), "V": (0.0, math.pi)},
        "normalizeSphereUv": normalize,
    }
    exec(compile(ast.Module(body=[proc], type_ignores=[]),
                 str(SOURCE), "exec"), scope)
    row = {"sphere": "sphere_input", "start": "start_input",
           "end": "end_input"}
    return scope["createSphereFromRow"], row


class CreateSphereTests(unittest.TestCase):
    def setUp(self):
        self.maya = FakeMaya()
        self.create, self.row = isolate_create(self.maya)

    def test_nearest_driven_radius_aim_tilt_uv_and_restore_paint(self):
        result = self.create(self.row)
        self.assertEqual(result, "AutoSkirt_Knee1_Sphere")
        self.assertEqual(len(self.maya.created), 1)
        created = self.maya.created[0]
        self.assertAlmostEqual(created["radius"], 3.0)
        self.assertEqual(created["polygon"], 0)
        self.assertEqual(created["constructionHistory"], False)
        self.assertEqual(created["axis"], (0, 1, 0))
        self.assertEqual(self.maya.normalized, [result])
        self.assertEqual(self.maya.identity[0][1]["translate"], False)
        self.assertEqual(self.maya.identity[0][1]["rotate"], True)
        self.assertEqual(self.maya.selected, ["|Rig|Body.vtx[1:30]"])
        self.assertEqual(self.maya.context, "artAttrSkinContext")
        self.assertEqual(len(self.maya.aims), 1)
        aim_target, aim_sphere, aim_flags = self.maya.aims[0]
        self.assertEqual(aim_sphere, result)
        self.assertEqual(aim_flags["aimVector"], [0.0, 0.0, 1.0])
        # End aims along +Y. Driven centroid is on +X, so tilt away => -X.
        aimed = [xyz for name, xyz in self.maya.xforms
                 if name == aim_target][-1]
        self.assertAlmostEqual(aimed[0], 1 - 2 * math.sin(math.radians(20)))
        self.assertAlmostEqual(aimed[1], 2 + 2 * math.cos(math.radians(20)))
        self.assertAlmostEqual(aimed[2], 3)
        self.assertFalse(any("parentConstraint" in str(record)
                             for record in self.maya.aims))

    def test_existing_sphere_is_not_overwritten(self):
        self.maya.objects.add(self.maya.values["sphere_input"])
        self.assertIsNone(self.create(self.row))
        self.assertFalse(self.maya.created)
        self.assertFalse(self.maya.normalized)
        self.assertTrue(any("already exists" in x for x in self.maya.warnings))

    def test_missing_start_is_safe(self):
        self.maya.values["start_input"] = ""
        self.assertIsNone(self.create(self.row))
        self.assertFalse(self.maya.created)
        self.assertTrue(self.maya.warnings)

    def test_degenerate_start_end_rejected_before_creation(self):
        self.maya.positions["|Rig|Foot"] = list(self.maya.positions["|Rig|Knee"])
        with self.assertRaisesRegex(ValueError, "must differ"):
            self.create(self.row)
        self.assertFalse(self.maya.created)

    def test_rebuild_failure_undoes_preview_and_restores_selection(self):
        self.maya.error_on_normalize = True
        with self.assertRaisesRegex(RuntimeError, "failed 0-1 rebuild"):
            self.create(self.row)
        self.assertEqual(self.maya.selected, ["|Rig|Body.vtx[1:30]"])
        self.assertEqual(self.maya.context, "artAttrSkinContext")
        self.assertIn({"undo": True}, self.maya.undo_events)

    def test_ui_button_is_local_only_and_not_exported(self):
        code = SOURCE.read_text(encoding="utf-8")
        module = ast.parse(code)
        line_field = next(n for n in module.body
                          if isinstance(n, ast.FunctionDef)
                          and n.name == "lineField")
        add_row = next(n for n in module.body
                       if isinstance(n, ast.FunctionDef)
                       and n.name == "addRow")
        exporter = next(n for n in module.body
                        if isinstance(n, ast.FunctionDef)
                        and n.name == "ExportPython")
        builder = next(n for n in module.body
                       if isinstance(n, ast.FunctionDef)
                       and n.name == "buildAutoSkirtSystem")
        self.assertIn('label="Create Sphere"', ast.get_source_segment(code, line_field))
        self.assertIn("action=partial(createSphereFromRow, row)",
                      ast.get_source_segment(code, add_row))
        self.assertNotIn("createSphereFromRow", ast.get_source_segment(code, exporter))
        self.assertNotIn("createSphereFromRow", ast.get_source_segment(code, builder))
        self.assertIn("normalizeSphereUv(sphere)",
                      ast.get_source_segment(
                          code, next(n for n in module.body
                                     if isinstance(n, ast.FunctionDef)
                                     and n.name == "createSphereFromRow")))


if __name__ == "__main__":
    unittest.main()
