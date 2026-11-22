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
        # Left tools + integrated list/action dock; no third splitter pane.
        left = source.index("self.workspace.addWidget(self.scroll)")
        right = source.index("self.workspace.addWidget(self.influence_actions)")
        self.assertLess(left, right)
        self.assertIn("dock_layout.addWidget(self.influences, 1)", source)
        self.assertIn("dock_layout.addWidget(self.paint_scroll, 0)", source)
        self.assertIn("dock_layout.setSpacing(0)", source)
        self.assertIn("dock_layout.setContentsMargins(0, 0, 0, 0)", source)
        self.assertIn("PAINT_STRIP_WIDTH = 145", source)
        self.assertIn("self.paint_scroll.setFixedWidth(PAINT_STRIP_WIDTH)", source)
        self.assertIn("self.workspace.setSizes([440, 450])", source)
        self.assertIn("if key in PAINT_WEIGHT_SECTIONS:", source)
        self.assertIn("self.paint_stack.insertWidget(", source)
        self.assertIn("not in PAINT_WEIGHT_SECTIONS", source)
        self.assertIn("self.buttons[action_id] = (button, callback", source)
        self.assertIn("self.dispatch(key, fn)", source)

    def test_paint_and_weight_sections_each_use_two_columns(self):
        source = FILE.read_text(encoding="utf-8")
        module = ast.parse(source)
        caps = next(node for node in module.body
                    if isinstance(node, ast.Assign) and
                    any(isinstance(target, ast.Name) and
                        target.id == "GROUP_MAX_COLUMNS"
                        for target in node.targets))
        settings = ast.literal_eval(caps.value)
        self.assertEqual(settings[("paint", "quick")], 2)
        self.assertEqual(settings[("paint", "locks")], 2)
        self.assertEqual(settings[("paint", "helpers")], 2)
        self.assertEqual(settings[("weight", "increment")], 2)
        self.assertIn("grid_type = WeightPairButtons if key == \"weight\" else ResponsiveButtons", source)
        self.assertIn("grid = grid_type(", source)
        self.assertIn("max_columns=GROUP_MAX_COLUMNS.get((key, group_key), 2)", source)
        self.assertIn("weight_grid_position(item[0])", source)
        self.assertIn("row, column = weight_grid_position(button.full_label)", source)
        self.assertIn("self.layout_grid.setColumnStretch(1, 1)", source)
        self.assertIn("self.paint_stack.insertWidget(", source)
        self.assertIn("self.paint_stack.setSpacing(1)", source)
        self.assertIn('force_two_columns=(key == "paint")', source)
        catalog = load_catalog()
        dock = {key: groups for key, _, groups in catalog
                if key in ("paint", "weight")}
        count = sum(len(items) for groups in dock.values()
                    for _, _, items in groups)
        self.assertEqual(count, 38)

    def test_main_search_and_density_still_use_one_button_collection(self):
        source = FILE.read_text(encoding="utf-8")
        self.assertIn("for section, section_title, groups in self.sections:",
                      source)
        self.assertIn("self.action_visibility[button] = match", source)
        self.assertIn("grid.reflow(force=True)", source)
        self.assertIn("for grid in self.grids:", source)
        self.assertIn("self.reflow_sections(force=True)", source)
        self.assertIn("self.workspace.setStretchFactor(0, 1)", source)
        self.assertIn("self.workspace.setStretchFactor(1, 0)", source)


if __name__ == "__main__":
    unittest.main()
