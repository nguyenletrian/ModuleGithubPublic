"""Offline layout contracts for Maya Skinning's side-by-side paint/weight dock."""
import ast
from functools import partial
from pathlib import Path
import unittest


FILE = Path(__file__).resolve().parents[1] / "UIs/SkinningTools/NLTA_Skinning_CommandBoard.py"


class DummyTool:
    def __getattr__(self, name):
        def callback(*args, **kwargs):
            return None
        return callback


def load_catalog():
    tree = ast.parse(FILE.read_text(encoding="utf-8"))
    catalog_def = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "command_catalog")
    scope = {"partial": partial}
    exec(compile(ast.Module(body=[catalog_def], type_ignores=[]),
                 str(FILE), "exec"), scope)
    names = (
        "NLTA_Brush", "NLTA_Skinning", "NLTA_General", "NLTA_Keyframes",
        "NLTA_Proxy", "NLTA_Mesh", "NLTA_Skinning_Transfer",
        "NLTA_Skinning_Eyelid", "NLTA_GraphSkinning", "NLTA_Set",
        "NLTA_BlendShape",
    )
    return scope["command_catalog"](
        {name: DummyTool() for name in names}, "fake_distance_ui")


class SkinningPaintDockTests(unittest.TestCase):
    def test_original_catalog_callbacks_remain_available_exactly_once(self):
        catalog = load_catalog()
        sections = {key: (title, groups) for key, title, groups in catalog}
        self.assertEqual(len(sections), len(catalog))
        self.assertEqual(set(sections), {
            "paint", "weight", "skin", "files", "proxy", "animation", "mesh"})
        self.assertEqual(sections["paint"][0], "PAINT & BRUSH")
        self.assertEqual(sections["weight"][0], "WEIGHT ADJUSTMENTS")
        actions = [
            (key, group, label, callback)
            for key, _, groups in catalog
            for group, _, items in groups
            for label, callback, _, _ in items
        ]
        self.assertEqual(len(actions), 105)
        ids = {"/".join((key, group, label))
               for key, group, label, callback in actions}
        self.assertEqual(len(ids), 105)
        self.assertTrue(all(callable(callback) for _, _, _, callback in actions))

    def test_paint_and_weight_actions_stay_grouped(self):
        catalog = load_catalog()
        actions = {
            key: {name for _, _, items in groups
                  for name, *_ in items}
            for key, _, groups in catalog
        }
        self.assertIn("Smooth", actions["paint"])
        self.assertIn("Flood", actions["paint"])
        self.assertIn("Switch Joint", actions["paint"])
        self.assertIn("Graph Skinning", actions["paint"])
        self.assertIn("Unlock All", actions["paint"])
        self.assertIn("Set 0", actions["weight"])
        self.assertIn("Add +1", actions["weight"])
        self.assertIn("-0.0001", actions["weight"])
        self.assertIn("+0.1", actions["weight"])
        self.assertEqual(len(actions["weight"]), 18)

    def test_dock_owns_original_widget_sections_in_adjacent_column(self):
        source = FILE.read_text(encoding="utf-8")
        self.assertIn('PAINT_WEIGHT_SECTIONS = frozenset(("paint", "weight"))',
                      source)
        self.assertIn('self.workspace = QtWidgets.QSplitter(QtCore.Qt.Horizontal)',
                      source)
        self.assertIn('self.paint_scroll.setObjectName("SkinningPaintWeightScroll")',
                      source)
        self.assertIn("self.workspace.addWidget(self.scroll)", source)
        self.assertIn("self.workspace.addWidget(self.paint_scroll)", source)
        self.assertIn("self.workspace.addWidget(self.influences)", source)
        self.assertIn("if key in PAINT_WEIGHT_SECTIONS:", source)
        self.assertIn("self.paint_stack.insertWidget(", source)
        self.assertIn("not in PAINT_WEIGHT_SECTIONS", source)
        self.assertIn("self.buttons[action_id] = (button, callback", source)
        self.assertIn("self.dispatch(key, fn)", source)

    def test_main_search_and_density_still_use_one_button_collection(self):
        source = FILE.read_text(encoding="utf-8")
        self.assertIn("for section, section_title, groups in self.sections:",
                      source)
        self.assertIn("self.action_visibility[button] = match", source)
        self.assertIn("grid.reflow(force=True)", source)
        self.assertIn("for grid in self.grids:", source)
        self.assertIn("self.reflow_sections(force=True)", source)
        self.assertIn("self.workspace.setStretchFactor(0, 1)", source)
        self.assertIn("self.workspace.setStretchFactor(2, 0)", source)


if __name__ == "__main__":
    unittest.main()
