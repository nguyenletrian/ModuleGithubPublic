# -*- coding: utf-8 -*-
"""Standalone all-visible Skinning command board for Autodesk Maya.

Adaptive multi-column regions use compact vertical action grids. This UI
handles presentation, search and density; rig algorithms remain
in the existing NLTA libraries.
"""
from functools import partial

import maya.cmds as cmds
import maya.OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance


_BOARD = None
_BRIDGE = "NLTA_SkinningCommandBridge"


def command_catalog(tools, distance_ui):
    """Declarative action map. The 105 original Skinning operations live here."""
    b = tools["NLTA_Brush"]
    s = tools["NLTA_Skinning"]
    g = tools["NLTA_General"]
    k = tools["NLTA_Keyframes"]
    p = tools["NLTA_Proxy"]
    m = tools["NLTA_Mesh"]
    t = tools["NLTA_Skinning_Transfer"]
    e = tools["NLTA_Skinning_Eyelid"]
    graph = tools["NLTA_GraphSkinning"]
    sets = tools["NLTA_Set"]
    bs = tools["NLTA_BlendShape"]

    increments = (0.0001, 0.0005, 0.001, 0.005, 0.01, 0.03, 0.05, 0.1)
    weight_commands = [
        ("Set 0", partial(b.ReplaceWeight, 0), "Replace weight with 0", "primary"),
        ("Add +1", partial(b.AddWeight, 1), "Add weight by 1", ""),
    ]
    for amount in increments:
        weight_commands.extend((
            ("-" + str(amount), partial(b.AddWeight, -amount), "Decrease weight", ""),
            ("+" + str(amount), partial(b.AddWeight, amount), "Increase weight", ""),
        ))

    animation_groups = []
    for key, space in (("local", "local"), ("world", "world")):
        animation_groups.append((
            key, space.title() + " space",
            [
                ("Rotate", partial(k.CreateKeyframe, {
                    "space": space, "type": "rotate", "inturn": True, "ui": distance_ui}), "", ""),
                ("Translate", partial(k.CreateKeyframe, {
                    "space": space, "type": "translate", "inturn": True, "ui": distance_ui}), "", ""),
                ("Rotate All", partial(k.CreateKeyframe, {
                    "space": space, "type": "rotate", "inturn": False, "ui": distance_ui}), "", ""),
                ("Move All", partial(k.CreateKeyframe, {
                    "space": space, "type": "translate", "inturn": False, "ui": distance_ui}), "", ""),
            ],
        ))

    return [
        ("paint", "PAINT & BRUSH", [
            ("quick", "Paint actions", [
                ("Smooth", partial(b.smooth, "solid"), "Smooth painted weights", "primary"),
                ("Flood", b.flood, "Flood with current brush value", ""),
                ("Copy Weight", b.CopyWeight, "Copy skin weight", ""),
                ("Copy Ratio", b.CopyRatio, "Copy weight ratio", ""),
                ("Graph Skinning", graph.CreateUI, "Open graph editor", "primary"),
                ("Pick Value", b.pickValue, "Sample a skin weight", ""),
            ]),
            ("locks", "Influence locks", [
                ("Unlock", s.unlock, "", ""),
                ("Add Unlock", s.addUnlock, "", ""),
                ("Add Down", s.addUnlockDown, "", ""),
                ("Add Up", s.addUnlockUp, "", ""),
                ("Unlock All", s.unlockAll, "", ""),
                ("Unlock 2 Joints", s.UnlockTwoJoints, "", ""),
                ("Unlock Joints", s.UnlockInfluenceJoints, "Unlock all influence joints", ""),
                ("Isolate", s.IsolateEffectVertex, "", ""),
            ]),
            ("helpers", "Paint helpers", [
                ("Switch Joint", s.switchJoint, "", ""),
                ("Switch Brush", b.SwitchBrush, "", ""),
                ("Middle Weight", s.setMiddleWeight, "", ""),
                ("Prune", s.pruneSmallWeights, "", ""),
                ("Transfer", t.CreateUI, "Open transfer tool", ""),
                ("Eye Lid", e.EyelidSurfaceSkinUI, "Open eyelid skin tool", ""),
            ]),
        ]),
        ("weight", "WEIGHT ADJUSTMENTS", [
            ("increment", "Weight - / +", weight_commands),
        ]),
        ("skin", "SKIN & JOINTS", [
            ("bind", "Skin and influences", [
                ("Bind Skin", g.bindSkin, "", ""),
                ("Copy Skin", g.copyJointBind, "", ""),
                ("Add Joint", s.AddJoint, "Joint(s) and mesh(es)", ""),
                ("Add Mesh Joint", s.AddMeshJoint, "", ""),
                ("Remove Joint", s.RemoveJoint,
                 "Transfers selected joint weights bottom-up and removes skin influences", "primary"),
                ("Clear Unused", s.removeUnneedJoint, "", ""),
                ("Mirror +X", partial(s.mirrorSkin, "x", "+"), "", ""),
                ("Mirror -X", partial(s.mirrorSkin, "x", "-"), "", ""),
                ("Clear Weight", s.ClearWeight, "", ""),
                ("Clear Skins", s.clearSkin, "Unbind skinClusters across the scene", "danger"),
            ]),
            ("max", "Max influences", [
                ("Check", s.checkMaxInfluent, "Check using value above", ""),
                ("Fix", s.fixMaxInfluence, "Fix using value above", ""),
            ]),
            ("sets", "Selection sets", [
                ("Create Set", sets.CreateSet, "", ""),
                ("Next Set", sets.NextSet, "", ""),
                ("Back Set", sets.BackSet, "", ""),
                ("Delete Sets", sets.DeleteSets, "", ""),
            ]),
        ]),
        ("files", "SKIN DATA & EXPORT", [
            ("io", "Skin weights and files", [
                ("Export Skin", s.ExportAllSkin, "", ""),
                ("Import Skin", s.ImportAllSkin, "", ""),
                ("Import Existing", s.ImportAllSkinExist, "Import Skin Existing", ""),
                ("Export Folder", s.ExportFolderSkin, "", ""),
                ("Import Folder", s.ImportFolderSkin, "", ""),
                ("Quick Export", s.ExportFolderSkinQuick, "Quick Export Folder", ""),
                ("Quick Import", s.ImportFolderSkinQuick, "Quick Import Folder", ""),
                ("Export FBX", s.ExportSkinFbx, "", ""),
                ("Export Scene", s.ObjToNewScene, "", ""),
            ]),
        ]),
        ("proxy", "PROXY & CURVES", [
            ("proxy", "Proxy", [
                ("Proxy", p.singleProxy, "", ""),
                ("Proxy X", partial(p.createProxy, "x"), "", ""),
                ("Copy Proxy", p.copyProxy, "", ""),
                ("Paste Proxy", p.pastProxy, "", ""),
                ("Closest Faces", p.SelectClosetFaces, "", ""),
            ]),
            ("curve", "Curve / loft", [
                ("Edges to Curve", p.EdgesToCurve, "", ""),
                ("Verts to Curve", p.VertsToCurve, "", ""),
                ("Create Circle", p.CreateCircle, "", ""),
                ("Draw Curve", p.DrawCurve, "", ""),
                ("Close Curve", p.CloseCurve, "", ""),
                ("Fit to Mesh", partial(p.FitCurveToMesh, "surface"), "", ""),
                ("Create Loft", p.CreateLoft, "", ""),
                ("Flip Loft", p.FlipLoftNormal, "", ""),
                ("Flip Curve", p.FlipCurveNormal, "", ""),
                ("Rotate CVs +", p.RotateCVsPositive, "", ""),
                ("Rotate CVs -", p.RotateCVsNegative, "", ""),
                ("Add Loft Curve", p.AddLoftCurve, "", ""),
                ("Clear Loft", p.ClearAllLoft, "Clear loft helpers", "danger"),
            ]),
        ]),
        ("animation", "ANIMATION & POSES", animation_groups + [
            ("timeline", "Timeline", [
                ("Delete Keys", k.deleteSenceKeyframe, "Delete Scene Keys", ""),
                ("Zoom Range", k.ZoomRangeAnim, "", ""),
                ("Delete Attr Keys", k.DeleteAttrKeyframes, "", ""),
                ("Fit Range", g.FitRangeAnim, "", ""),
                ("Bind Pose", s.goToBindPose, "", ""),
            ]),
        ]),
        ("mesh", "MESH & BLEND SHAPE", [
            ("mesh", "Mesh utilities", [
                ("Component", s.component, "", ""),
                ("Load UI", b.loadUi, "", ""),
                ("Fix Quad", m.ShowQuardraw, "", ""),
                ("Fix Initial", g.fixInitial, "", ""),
            ]),
            ("blend", "Blend shapes / vertices", [
                ("Import BS", bs.ImportBlendShape, "", ""),
                ("Export BS", bs.ExportBlendShape, "", ""),
                ("Export BS XML", bs.ExportBSToXML, "", ""),
                ("Export Vtx Pos", bs.ExportVertexsPosition, "Export Vertices Position", ""),
                ("Import Vtx Pos", bs.ImportVertexsPosition, "Import Vertices Position", ""),
                ("Mirror Vtx UV", m.MirrorVertexByUv, "Mirror Vertices by UV", ""),
                ("Mirror Vert Pos", m.MirrorMeshPosition, "", ""),
            ]),
        ]),
    ]


# Individual group minimum widths allow more tools in each region without
# forcing a one-size-fits-all global button grid.
GROUP_CELL_WIDTHS = {
    ("paint", "quick"): 86,
    ("paint", "locks"): 76,
    ("paint", "helpers"): 88,
    ("weight", "increment"): 60,
    ("skin", "bind"): 92,
    ("skin", "max"): 72,
    ("skin", "sets"): 84,
    ("files", "io"): 92,
    ("proxy", "proxy"): 84,
    ("proxy", "curve"): 84,
    ("animation", "local"): 80,
    ("animation", "world"): 80,
    ("animation", "timeline"): 90,
    ("mesh", "mesh"): 84,
    ("mesh", "blend"): 90,
}

# Each action group reads top-to-bottom in columns, like the original UI.
# Cap the column count so a wide window does not turn a group into one long row.
GROUP_MAX_COLUMNS = {
    ("paint", "quick"): 2,
    ("paint", "locks"): 2,
    ("paint", "helpers"): 2,
    ("skin", "bind"): 3,
    ("skin", "max"): 2,
    ("skin", "sets"): 2,
    ("files", "io"): 3,
    ("proxy", "proxy"): 2,
    ("proxy", "curve"): 3,
    ("animation", "local"): 2,
    ("animation", "world"): 2,
    ("animation", "timeline"): 2,
    ("mesh", "mesh"): 2,
    ("mesh", "blend"): 3,
}


def column_major_position(index, count, columns):
    """Balanced column-first placement preserving the original action order."""
    columns = max(1, min(columns, count))
    short_length, longer_columns = divmod(count, columns)
    long_end = (short_length + 1) * longer_columns
    if index < long_end:
        return index % (short_length + 1), index // (short_length + 1)
    offset = index - long_end
    return offset % short_length, longer_columns + offset // short_length


COMPACT_LABELS = {
    "Graph Skinning": "Graph",
    "Copy Weight": "Copy W",
    "Copy Ratio": "Copy Ratio",
    "Pick Value": "Pick",
    "Add Unlock": "Add Unlk",
    "Unlock 2 Joints": "Unlock 2",
    "Unlock Joints": "Unlk Jnts",
    "Switch Joint": "Switch J",
    "Switch Brush": "Switch B",
    "Middle Weight": "Middle",
    "Add Mesh Joint": "Add Mesh",
    "Remove Joint": "Remove J",
    "Clear Unused": "Clr Unused",
    "Clear Weight": "Clr Wgt",
    "Clear Skins": "Clr Skins",
    "Create Set": "New Set",
    "Delete Sets": "Del Sets",
    "Export Skin": "Export",
    "Import Skin": "Import",
    "Import Existing": "Import Ext",
    "Export Folder": "Exp Folder",
    "Import Folder": "Imp Folder",
    "Quick Export": "Quick Exp",
    "Quick Import": "Quick Imp",
    "Closest Faces": "Near Faces",
    "Edges to Curve": "Edges>Crv",
    "Verts to Curve": "Verts>Crv",
    "Create Circle": "Circle",
    "Create Loft": "Loft",
    "Add Loft Curve": "Add Loft",
    "Rotate CVs +": "CVs +",
    "Rotate CVs -": "CVs -",
    "Delete Attr Keys": "Del Attr",
    "Delete Keys": "Del Keys",
    "Export BS XML": "BS XML",
    "Mirror Vert Pos": "Mirror Pos",
    "Mirror Vtx UV": "Mirror UV",
}

class ResponsiveButtons(QtWidgets.QWidget):
    """Responsive tool columns: read down each column before moving right."""

    def __init__(self, parent=None, cell_width=86, compact=True, max_columns=2):
        super(ResponsiveButtons, self).__init__(parent)
        self.items = []
        self.cell_width = cell_width
        self.max_columns = max_columns
        self.compact = compact
        self.columns = 0
        self.positions = ()
        self.last_width = 0
        self.layout_grid = QtWidgets.QGridLayout(self)
        self.layout_grid.setContentsMargins(0, 0, 0, 0)
        self.layout_grid.setHorizontalSpacing(2)
        self.layout_grid.setVerticalSpacing(2)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

    def add_button(self, button):
        button.setParent(self)
        self.items.append(button)
        button.show()
        self.reflow(force=True)

    def set_density(self, compact):
        self.compact = compact
        self.reflow(force=True)

    def reflow(self, force=False):
        active = [button for button in self.items if not button.isHidden()]
        width = max(1, self.width())
        gap = self.layout_grid.horizontalSpacing()
        min_width = self.cell_width if self.compact else self.cell_width + 28
        columns = max(1, min(len(active), self.max_columns,
                             (width + gap) // (min_width + gap)))
        positions = tuple(active)
        # Refresh text even when the column count stays the same after resizing.
        cell_width = max(24, (width - max(0, columns - 1) * gap) // columns)
        for button in active:
            button.setFixedHeight(23 if self.compact else 29)
            label = (button.short_label if self.compact else button.full_label)
            button.setText(button.fontMetrics().elidedText(
                label, QtCore.Qt.ElideRight, max(15, cell_width - 10)))
        if not force and columns == self.columns and positions == self.positions:
            self.last_width = width
            return
        while self.layout_grid.count():
            self.layout_grid.takeAt(0)
        for column in range(max(columns, self.columns)):
            self.layout_grid.setColumnStretch(column, 0)
        for index, button in enumerate(active):
            row, column = column_major_position(index, len(active), columns)
            self.layout_grid.addWidget(button, row, column)
        for column in range(columns):
            self.layout_grid.setColumnStretch(column, 1)
        self.columns = columns
        self.positions = positions
        self.last_width = width

    def resizeEvent(self, event):
        super(ResponsiveButtons, self).resizeEvent(event)
        self.reflow()


WEIGHT_STEPS = ("0.0001", "0.0005", "0.001", "0.005",
                "0.01", "0.03", "0.05", "0.1")


def weight_grid_position(name):
    """Original layout: 0 above negative column; +1 after positive column."""
    if name == "Set 0":
        return 0, 0
    if name == "Add +1":
        return len(WEIGHT_STEPS) + 1, 1
    if name[:1] in ("-", "+") and name[1:] in WEIGHT_STEPS:
        return WEIGHT_STEPS.index(name[1:]) + 1, int(name[0] == "+")
    return len(WEIGHT_STEPS) + 2, 0


class WeightPairButtons(ResponsiveButtons):
    """Keep subtract/add steps paired in two columns at any window width."""

    def reflow(self, force=False):
        active = [button for button in self.items if not button.isHidden()]
        positions = tuple(active)
        width = max(1, self.width())
        gap = self.layout_grid.horizontalSpacing()
        cell_width = max(28, (width - gap) // 2)
        if not force and positions == self.positions and width == self.last_width:
            return

        while self.layout_grid.count():
            self.layout_grid.takeAt(0)

        for button in active:
            button.setFixedHeight(23 if self.compact else 29)
            label = button.short_label if self.compact else button.full_label
            button.setText(button.fontMetrics().elidedText(
                label, QtCore.Qt.ElideRight, max(15, cell_width - 10)))

            row, column = weight_grid_position(button.full_label)
            self.layout_grid.addWidget(button, row, column)

        self.layout_grid.setColumnStretch(0, 1)
        self.layout_grid.setColumnStretch(1, 1)
        self.positions = positions
        self.columns = 2
        self.last_width = width


def masonry_assignments(cards, columns):
    """Assign ordered (key, estimated_height) panels to the shortest column."""
    heights = [0] * columns
    output = []
    for key, panel_height in cards:
        column = min(range(columns), key=lambda index: (heights[index], index))
        output.append((key, column))
        heights[column] += panel_height + 6
    return output


class SkinningBoard(QtWidgets.QWidget):
    def __init__(self, catalog, distance_ui, uis):
        super(SkinningBoard, self).__init__()
        self.setObjectName("NLTA_SkinningCommandBoard")
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMinimumWidth(690)
        self.setMinimumHeight(440)
        self.catalog = catalog
        self.uis = uis
        self.buttons = {}
        self.sections = []
        self.settings = QtCore.QSettings("NLTA", "SkinningCommandBoard")
        self.grids = []
        self.compact = self.settings.value("density", "Compact") != "Comfort"

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(5, 4, 5, 4)
        outer.setSpacing(3)
        top = QtWidgets.QHBoxLayout()
        top.setSpacing(5)

        title = QtWidgets.QLabel("SKINNING")
        title.setObjectName("SkinningBoardTitle")
        top.addWidget(title)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search tools... Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(140)
        self.search.textChanged.connect(self.filter_actions)
        top.addWidget(self.search, 1)

        self.density = QtWidgets.QComboBox()
        self.density.setObjectName("SkinningDensity")
        self.density.addItems(("Compact", "Comfort"))
        self.density.setCurrentText("Compact" if self.compact else "Comfort")
        self.density.setToolTip("Adjust button sizes and column counts in every group")
        top.addWidget(self.density)

        # Max Width sets the width of each region, not the Maya window.
        # Narrower regions automatically produce more workspace columns.
        self.max_width_value = int(self.settings.value("max_region_width", 230))
        self.max_width_label = QtWidgets.QLabel("Max W")
        self.max_width_label.setToolTip("Maximum width of each tool region in pixels")
        top.addWidget(self.max_width_label)
        self.max_width_input = QtWidgets.QSpinBox()
        self.max_width_input.setObjectName("SkinningMaxRegionWidth")
        self.max_width_input.setRange(210, 440)
        self.max_width_input.setSingleStep(10)
        self.max_width_input.setSuffix(" px")
        self.max_width_input.setValue(max(210, min(440, self.max_width_value)))
        self.max_width_input.setToolTip(
            "Lower values fit more regions across the window")
        top.addWidget(self.max_width_input)
        self.set_max_width = QtWidgets.QPushButton("Set")
        self.set_max_width.setObjectName("SkinningSetMaxWidth")
        self.set_max_width.setToolTip("Apply width and repack all tool regions")
        self.set_max_width.clicked.connect(
            lambda checked=False: self.apply_max_region_width())
        top.addWidget(self.set_max_width)

        self.paint_button = QtWidgets.QPushButton("Paint")
        self.paint_button.setObjectName("SkinningPaintContextButton")
        self.paint_button.setToolTip(
            "Activate Maya skin painting without opening Tool Settings")
        self.paint_button.clicked.connect(lambda checked=False: self.activate_paint())
        top.addWidget(self.paint_button)

        self.count = QtWidgets.QLabel("105")
        self.count.setObjectName("SkinningBoardCount")
        self.count.setToolTip("Number of available tools")
        top.addWidget(self.count)
        outer.addLayout(top)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setObjectName("SkinningBoardScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        outer.addWidget(self.scroll, 1)
        inside = QtWidgets.QWidget()
        inside.setObjectName("SkinningContent")
        self.content = QtWidgets.QVBoxLayout(inside)
        self.scroll.setWidget(inside)
        self.content.setContentsMargins(1, 1, 1, 5)
        self.content.setSpacing(5)

        # All sections share adaptive masonry columns with no empty grid rows.
        self.sections_host = QtWidgets.QWidget()
        self.sections_host.setObjectName("SkinningMasonry")
        self.masonry_row = QtWidgets.QHBoxLayout(self.sections_host)
        self.masonry_row.setContentsMargins(0, 0, 0, 0)
        self.masonry_row.setSpacing(6)
        self.content.addWidget(self.sections_host)
        self.masonry_columns = []
        self.masonry_stacks = []
        self.masonry_signature = None
        self._reflowing = False
        self.section_visibility = {}
        self.action_visibility = {}
        # Create six persistent column widgets once. Moving a Qt widget into
        # a freshly reparented/deleted column during resize can blank the board.
        for index in range(6):
            column = QtWidgets.QWidget(self.sections_host)
            column.setObjectName("SkinningToolColumn")
            column.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                 QtWidgets.QSizePolicy.Preferred)
            stack = QtWidgets.QVBoxLayout(column)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(6)
            stack.addStretch()
            self.masonry_row.addWidget(column)
            self.masonry_columns.append(column)
            self.masonry_stacks.append(stack)
            column.hide()
        self.masonry_row.addStretch()

        for key, section_title, groups in catalog:
            section = QtWidgets.QFrame()
            section.setObjectName("SkinningSection_" + key)
            vertical = QtWidgets.QVBoxLayout(section)
            vertical.setContentsMargins(7, 5, 7, 7)
            vertical.setSpacing(2)
            header = QtWidgets.QLabel(section_title)
            header.setObjectName("SkinningSectionTitle")
            vertical.addWidget(header)
            group_records = []
            for group_key, heading, items in groups:
                subheading = QtWidgets.QLabel(heading)
                subheading.setObjectName("SkinningSubheading")
                vertical.addWidget(subheading)
                if key == "skin" and group_key == "max":
                    spin_row = QtWidgets.QHBoxLayout()
                    spin_label = QtWidgets.QLabel("Limit / vertex")
                    spin_row.addWidget(spin_label)
                    self.max_influences = QtWidgets.QSpinBox()
                    self.max_influences.setObjectName("SkinningMaxInfluences")
                    self.max_influences.setRange(1, 100)
                    self.max_influences.setValue(int(self.settings.value("max_influences", 4)))
                    self.max_influences.valueChanged.connect(
                        lambda value: self.settings.setValue("max_influences", value))
                    spin_row.addWidget(self.max_influences)
                    spin_row.addStretch()
                    vertical.addLayout(spin_row)
                if key == "animation" and group_key == "local":
                    distance_row = QtWidgets.QHBoxLayout()
                    distance_row.addWidget(QtWidgets.QLabel("Distance"))
                    spin = QtWidgets.QSpinBox()
                    spin.setObjectName("SkinningAnimationDistance")
                    spin.setRange(0, 10000)
                    spin.setValue(5)
                    spin.valueChanged.connect(
                        lambda value: cmds.intSliderGrp(distance_ui, edit=True, value=value))
                    distance_row.addWidget(spin)
                    distance_row.addStretch()
                    vertical.addLayout(distance_row)

                grid_type = WeightPairButtons if key == "weight" else ResponsiveButtons
                grid = grid_type(
                    cell_width=GROUP_CELL_WIDTHS.get((key, group_key), 86),
                    compact=self.compact,
                    max_columns=GROUP_MAX_COLUMNS.get((key, group_key), 2))
                self.grids.append(grid)
                vertical.addWidget(grid)
                entries = []
                for label, callback, tooltip, role in items:
                    action_id = "/".join((key, group_key, label))
                    button = self.make_button(label, callback, tooltip, role, action_id)
                    grid.add_button(button)
                    self.buttons[action_id] = (button, callback, label, tooltip, role)
                    entries.append((action_id, button))
                group_records.append((subheading, grid, entries))
            self.sections.append((section, section_title, group_records))
            self.section_visibility[section] = True

        self.content.addStretch()
        self.apply_style()
        self.scroll.viewport().installEventFilter(self)
        self.reflow_sections(force=True)
        self.density.currentTextChanged.connect(self.change_density)
        self.count.setText("{} tools".format(len(self.buttons)))
        shortcut_cls = getattr(QtWidgets, "QShortcut", None) or QtGui.QShortcut
        search_shortcut = shortcut_cls(QtGui.QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self.search.setFocus)
        clear_shortcut = shortcut_cls(QtGui.QKeySequence("Esc"), self.search)
        clear_shortcut.activated.connect(self.search.clear)
        self.shortcuts = (search_shortcut, clear_shortcut)

    def eventFilter(self, watched, event):
        if (watched is self.scroll.viewport()
                and event.type() == QtCore.QEvent.Resize):
            self.reflow_sections()
        return super(SkinningBoard, self).eventFilter(watched, event)

    def apply_max_region_width(self):
        """Apply user-controlled maximum region width and repack the board."""
        self.max_width_value = self.max_width_input.value()
        self.settings.setValue("max_region_width", self.max_width_value)
        self.reflow_sections(force=True)

    def estimate_section_height(self, record, width):
        """Approximate card height to avoid large blank spaces below panels."""
        section, _, groups = record
        total = 33
        for _, grid, entries in groups:
            count = sum(self.action_visibility.get(button, True)
                        for _, button in entries)
            if not count:
                continue
            if isinstance(grid, WeightPairButtons):
                rows = len(WEIGHT_STEPS) + 2
            else:
                gap = grid.layout_grid.horizontalSpacing()
                min_width = grid.cell_width + (0 if self.compact else 28)
                usable = max(1, width - 14)
                columns = max(1, min(count, grid.max_columns,
                                     (usable + gap) // (min_width + gap)))
                rows = (count + columns - 1) // columns
            total += 19 + rows * (25 if self.compact else 31)
        if section.objectName() == "SkinningSection_skin":
            total += 36
        if section.objectName() == "SkinningSection_animation":
            total += 36
        return total

    def reflow_sections(self, force=False):
        """Repack regions using persistent columns; never destroy cards on resize."""
        if self._reflowing:
            return
        available = max(1, self.scroll.viewport().width() - 3)
        region_width = max(210, min(440, self.max_width_value))
        visible = [record for record in self.sections
                   if self.section_visibility.get(record[0], True)]
        minimum = max(200, region_width - 20)
        columns = (max(1, min(len(visible), len(self.masonry_columns),
                              (available + 6) // (minimum + 6)))
                   if visible else 0)
        width = (min(region_width, max(200, (available - (columns - 1) * 6) // columns))
                 if columns else 0)
        order = ("paint", "weight", "animation", "skin", "files", "proxy", "mesh")
        visible.sort(key=lambda record: order.index(
            record[0].objectName().replace("SkinningSection_", "")))
        signature = (columns, width,
                     tuple(record[0].objectName() for record in visible),
                     self.compact)
        if not force and signature == self.masonry_signature:
            return

        self._reflowing = True
        try:
            # Do not delete columns, reparent panels manually, or remove spacers.
            # Move each existing panel between persistent layouts as necessary.
            cards = [(record[0].objectName(),
                      self.estimate_section_height(record, width))
                     for record in visible]
            placements = (masonry_assignments(cards, columns)
                          if columns else [])
            for index, column in enumerate(self.masonry_columns):
                if index < columns:
                    column.setFixedWidth(width)
                    column.show()
                else:
                    column.hide()

            for record, (_, index) in zip(visible, placements):
                panel = record[0]
                target = self.masonry_stacks[index]
                current = panel.parentWidget()
                if current is not self.masonry_columns[index]:
                    if current is not None and current.layout():
                        current.layout().removeWidget(panel)
                    target.insertWidget(target.count() - 1, panel)
                panel.show()

            for record in self.sections:
                if not self.section_visibility.get(record[0], True):
                    record[0].hide()
            self.masonry_signature = signature
        finally:
            self._reflowing = False

    def activate_paint(self):
        """Activate Maya's Artisan context without opening Paint Tool Settings."""
        import NLTA_Skinning
        ensure = getattr(NLTA_Skinning, "EnsurePaintContext", None)
        if not callable(ensure):
            cmds.warning(
                "NLTA Skinning library is outdated: {}. "
                "Reinstall NLTA with AutoInstall.py and reopen Skinning."
                .format(getattr(NLTA_Skinning, "__file__", "<unknown>")))
            return False
        return bool(ensure())

    def dispatch(self, action_id, callback):
        needs_paint = (
            action_id.startswith("weight/increment/") or
            action_id in {
                "paint/quick/Smooth", "paint/quick/Flood",
                "paint/quick/Pick Value", "paint/helpers/Switch Brush",
                "paint/helpers/Prune", "paint/locks/Add Unlock",
                "paint/locks/Unlock All", "paint/locks/Unlock",
                "paint/locks/Add Up", "paint/locks/Add Down",
                "paint/helpers/Switch Joint"
            }
        )
        if action_id == "skin/max/Check":
            return callback(maxValue=self.max_influences.value())
        if action_id == "skin/max/Fix":
            return callback(maxInfluence=self.max_influences.value())
        if needs_paint and not self.activate_paint():
            return
        return callback()

    def closeEvent(self, event):
        self.settings.setValue("geometry_masonry", self.saveGeometry())
        super(SkinningBoard, self).closeEvent(event)

    def change_density(self, value):
        self.compact = value == "Compact"
        self.settings.setValue("density", value)
        for grid in self.grids:
            grid.set_density(self.compact)
        self.reflow_sections(force=True)

    def make_button(self, label, callback, tooltip, role, action_id):
        button = QtWidgets.QPushButton(label)
        button.setObjectName("SkinningAction")
        button.setProperty("role", role or "normal")
        button.setToolTip(label + ("\n" + tooltip if tooltip and tooltip != label else ""))
        button.full_label = label
        button.short_label = COMPACT_LABELS.get(label, label)
        button.setMinimumWidth(0)
        button.setMinimumHeight(22)
        button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        # Do not pass the Qt clicked(bool) to legacy Maya callbacks.
        button.clicked.connect(
            lambda checked=False, key=action_id, fn=callback: self.dispatch(key, fn))
        return button

    def filter_actions(self, value):
        term = value.strip().casefold()
        visible_count = 0
        for section, section_title, groups in self.sections:
            section_count = 0
            for label_widget, grid, entries in groups:
                heading = label_widget.text()
                show_all = bool(term) and term in (section_title + " " + heading).casefold()
                group_count = 0
                for action_id, button in entries:
                    _, _, label, tooltip, _ = self.buttons[action_id]
                    match = (not term or show_all or
                             term in (label + " " + tooltip).casefold())
                    self.action_visibility[button] = match
                    button.setVisible(match)
                    group_count += int(match)
                label_widget.setVisible(group_count > 0)
                grid.setVisible(group_count > 0)
                grid.reflow(force=True)
                section_count += group_count
            self.section_visibility[section] = section_count > 0
            section.setVisible(section_count > 0)
            visible_count += section_count
        self.reflow_sections(force=True)
        self.count.setText("{} / {}".format(visible_count, len(self.buttons))
                           if term else "{} tools".format(len(self.buttons)))

    def apply_style(self):
        """Neutral near-black UI: clear typography and separation, no tinted panels."""
        self.setStyleSheet("""
            QWidget#NLTA_SkinningCommandBoard {
                background-color: #383838;
                color: #E5E5E5;
            }
            QScrollArea#SkinningBoardScroll {
                background-color: #383838;
                border: none;
            }
            QWidget#SkinningMasonry, QWidget#SkinningContent,
            QWidget#SkinningToolColumn {
                background-color: #383838;
            }
            QLabel#SkinningBoardTitle {
                color: #F0F0F0;
                font-size: 12px;
                font-weight: 700;
                padding-right: 6px;
            }
            QLabel#SkinningBoardCount {
                font-size: 10px;
                color: #999999;
            }
            QFrame#SkinningSection_paint, QFrame#SkinningSection_weight,
            QFrame#SkinningSection_skin, QFrame#SkinningSection_files,
            QFrame#SkinningSection_proxy, QFrame#SkinningSection_animation,
            QFrame#SkinningSection_mesh {
                background-color: #202020;
                border: 1px solid #454545;
                border-radius: 4px;
            }
            QLabel#SkinningSectionTitle {
                color: #EAEAEA;
                font-size: 11px;
                font-weight: 700;
                padding: 2px 0 3px;
                border: none;
                border-bottom: 1px solid #494949;
                background: transparent;
            }
            QLabel#SkinningSubheading {
                color: #AAAAAA;
                font-size: 10px;
                padding-top: 1px;
                border: none;
                background: transparent;
            }
            QPushButton#SkinningAction {
                color: #E5E5E5;
                background-color: #303030;
                border: 1px solid #4A4A4A;
                border-radius: 3px;
                padding: 1px 3px;
                min-height: 21px;
            }
            QPushButton#SkinningAction:hover {
                background-color: #424242;
                border-color: #737373;
            }
            QPushButton#SkinningAction:pressed {
                background-color: #545454;
            }
            QPushButton#SkinningAction[role="primary"] {
                border-color: #636363;
            }
            QPushButton#SkinningAction[role="danger"] {
                border-color: #836060;
            }
            QLineEdit {
                background-color: #252525;
                color: #EEEEEE;
                border: 1px solid #4A4A4A;
                padding: 2px 4px;
            }
            QComboBox, QSpinBox {
                background-color: #2A2A2A;
                color: #E7E7E7;
                border: 1px solid #4A4A4A;
                padding: 2px 4px;
            }
        """)


def _maya_window():
    """Parent only to Maya main window, never to NLTA_Form."""
    pointer = omui.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None


def _bridge_controls(uis):
    """Maya controls needed by legacy callbacks, hosted outside the NLTA form."""
    if not cmds.window(_BRIDGE, exists=True):
        cmds.window(_BRIDGE, title="Skinning Callback Bridge", visible=False)
    if not cmds.columnLayout("NLTA_SkinningBridgeLayout", exists=True):
        host = cmds.columnLayout("NLTA_SkinningBridgeLayout",
                                 parent=_BRIDGE, adjustableColumn=True)
    else:
        host = "NLTA_SkinningBridgeLayout"
    slider = "NLTA_SkinningAnimationDistance"
    if not cmds.intSliderGrp(slider, exists=True):
        cmds.intSliderGrp(
            slider, parent=host, label="Distance", field=True,
            minValue=0, maxValue=10000, value=5)
    uis["animationDistance"] = slider
    return slider


def OpenWindow(tools, uis):
    """Reusable floating Skinning window, independent of the module host layout."""
    global _BOARD
    if _BOARD is not None:
        try:
            _BOARD.showNormal()
            _BOARD.raise_()
            _BOARD.activateWindow()
            return _BOARD
        except RuntimeError:
            _BOARD = None

    # A reloaded Python module may still leave an older Qt board visible.
    application = QtWidgets.QApplication.instance()
    if application:
        for widget in application.allWidgets():
            if widget.objectName() == "NLTA_SkinningCommandBoard":
                widget.close()
                widget.deleteLater()

    slider = _bridge_controls(uis)
    board = SkinningBoard(command_catalog(tools, slider), slider, uis)
    board.setParent(_maya_window(), QtCore.Qt.Window)
    board.setWindowTitle("NLTA Skinning  |  Command Board")
    board.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
    saved = board.settings.value("geometry_masonry")
    if saved:
        board.restoreGeometry(saved)
    else:
        board.resize(1020, 790)
    _BOARD = board
    uis["board"] = board
    board.show()
    board.raise_()
    board.activateWindow()
    return board


def CreateUI(data, tools, uis):
    """Compatibility entry point: open only the floating Skinning board."""
    return OpenWindow(tools, uis)
