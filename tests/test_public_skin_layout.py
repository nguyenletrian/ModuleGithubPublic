"""Offline layout contracts for Maya Skinning's compact joint and action dock."""
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
        self.assertIn('LEFT_DOCK_SECTIONS = frozenset(("paint", "weight", "animation"))',
                      source)
        self.assertIn('self.workspace = QtWidgets.QSplitter(QtCore.Qt.Horizontal)',
                      source)
        self.assertIn('self.paint_scroll.setObjectName("SkinningPaintWeightScroll")',
                      source)
        self.assertIn("self.workspace.addWidget(self.scroll)", source)
        # Left-to-right: paint buttons, influence list, remaining tool form.
        dock = source.index("self.workspace.addWidget(self.influence_actions)")
        tools = source.index("self.workspace.addWidget(self.scroll)")
        self.assertLess(dock, tools)
        paint = source.index("dock_layout.addWidget(self.paint_scroll, 0)")
        influences = source.index("dock_layout.addWidget(self.influences, 1)")
        self.assertLess(paint, influences)
        self.assertIn("self.workspace.setStretchFactor(0, 0)", source)
        self.assertIn("self.workspace.setStretchFactor(1, 1)", source)
        self.assertIn("dock_layout.setSpacing(0)", source)
        self.assertIn("dock_layout.setContentsMargins(0, 0, 0, 0)", source)
        self.assertIn("PAINT_STRIP_WIDTH = 145", source)
        self.assertIn("self.paint_scroll.setFixedWidth(PAINT_STRIP_WIDTH)", source)
        self.assertIn("self.workspace.setSizes([450, 440])", source)
        self.assertIn("if key in LEFT_DOCK_SECTIONS:", source)
        self.assertIn("self.paint_stack.insertWidget(", source)
        self.assertIn("not in LEFT_DOCK_SECTIONS", source)
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
        self.assertIn('force_two_columns=(key in ("paint", "animation"))', source)
        self.assertIn("height_reduction=2 if key in LEFT_DOCK_SECTIONS else 0", source)
        self.assertEqual(
            source.count("button.setFixedHeight((23 if self.compact else 29) - self.height_reduction)"),
            2)
        self.assertIn('button.setProperty("dock", "left" if left_dock else "main")', source)
        self.assertIn('button.setMinimumHeight(20 if left_dock else 22)', source)
        self.assertIn('QPushButton#SkinningAction[dock="left"]', source)
        catalog = load_catalog()
        dock = {key: groups for key, _, groups in catalog
                if key in ("paint", "weight", "animation")}
        count = sum(len(items) for groups in dock.values()
                    for _, _, items in groups)
        self.assertEqual(count, 51)

    def test_hot_reload_can_close_old_maya_widgets_without_super_errors(self):
        source = FILE.read_text(encoding="utf-8")
        self.assertNotIn("super(SkinningBoard, self).", source)
        self.assertNotIn("super(ResponsiveButtons, self).resizeEvent", source)
        for base_call in (
            "QtWidgets.QWidget.eventFilter(self, watched, event)",
            "QtWidgets.QWidget.showEvent(self, event)",
            "QtWidgets.QWidget.hideEvent(self, event)",
            "QtWidgets.QWidget.closeEvent(self, event)",
            "QtWidgets.QWidget.resizeEvent(self, event)",
        ):
            self.assertIn(base_call, source)
        self.assertIn("old_class = type(widget)", source)
        self.assertIn('setattr(old_class, handler, getattr(QtWidgets.QWidget, handler))',
                      source)
        self.assertIn('influences.deactivate()', source)
        self.assertIn('old_scroll.viewport().removeEventFilter(widget)', source)
        self.assertLess(source.index('influences.deactivate()'),
                        source.index('widget.close()'))
        self.assertLess(source.index('widget.close()'),
                        source.index('widget.deleteLater()'))

    def test_keyframes_on_left_and_marked_controls_removed(self):
        source = FILE.read_text(encoding="utf-8")
        self.assertNotIn('self.filter_box = QtWidgets.QComboBox()', source)
        self.assertNotIn('self.mesh_label = QtWidgets.QLabel(', source)
        self.assertNotIn('selected = QtWidgets.QGridLayout()', source)
        self.assertNotIn('all_buttons = QtWidgets.QGridLayout()', source)
        self.assertNotIn('self.density = QtWidgets.QComboBox()', source)
        self.assertNotIn('self.max_width_input = QtWidgets.QSpinBox()', source)
        self.assertNotIn('self.paint_button = QtWidgets.QPushButton(', source)
        self.assertNotIn('Search tools... Ctrl+F', source)
        self.assertIn(
            'search_shortcut.activated.connect(self.influences.search.setFocus)', source)
        self.assertIn('spin.valueChanged.connect(', source)
        self.assertIn('cmds.intSliderGrp(distance_ui, edit=True, value=value)',
                      source)
        self.assertIn('self.paint_stack.insertWidget(', source)
        self.assertIn("grid.add_button(button)", source)
        self.assertIn('self.reflow_sections(force=True)', source)
        self.assertIn('self.workspace.setStretchFactor(0, 0)', source)
        self.assertIn('self.workspace.setStretchFactor(1, 1)', source)
        catalog = load_catalog()
        animation = next(groups for key, _, groups in catalog
                         if key == "animation")
        self.assertEqual(sum(len(items) for _, _, items in animation), 13)


if __name__ == "__main__":
    unittest.main()
