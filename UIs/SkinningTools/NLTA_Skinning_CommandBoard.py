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
LEFT_DOCK_SECTIONS = frozenset(("paint", "weight", "animation"))
# Visual order only: preserve each group's existing action ID and callback.
LEFT_DOCK_GROUP_ORDER = (
    ("animation", "local"), ("animation", "world"),
    ("animation", "timeline"),
    ("paint", "extras"), ("weight", "increment"),
)
INFLUENCE_LOCK_WIDTH = 48  # Native checkbox only.
INFLUENCE_CELL_HEIGHT = 24
PAINT_STRIP_WIDTH = 145  # Half of the former 290-px action strip.

# These buttons operate on the joint currently highlighted in the hierarchy.
INFLUENCE_LOCK_ACTIONS = {
    "Unlock": "unlock",
    "Add Unlock": "add_unlock",
    "Add Up": "add_up",
    "Add Down": "add_down",
    "Unlock All": "unlock_all",
    "Isolate": "isolate",
}


def command_catalog(tools, distance_ui):
    """Declarative action map; preset buttons set brush Value and opacity 1."""
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

    # MayaScriptNew brush operations: 0 = Replace, +/- and 1 = Add.
    # Every preset only sets the Paint Skin brush Value with opacity 1.
    increments = (0.0001, 0.0005, 0.001, 0.005, 0.01, 0.03, 0.05, 0.1)
    weight_commands = [
        ("Set 0", partial(b.ReplaceWeight, 0),
         "Replace brush Value 0 · Opacity 1", "primary"),
        ("Set 1", partial(b.AddWeight, 1),
         "Add brush Value 1 · Opacity 1", "primary"),
    ]
    for amount in increments:
        weight_commands.extend((
            ("-" + str(amount), partial(b.AddWeight, -amount),
             "Add brush Value -{} · Opacity 1".format(amount), ""),
            ("+" + str(amount), partial(b.AddWeight, amount),
             "Add brush Value +{} · Opacity 1".format(amount), ""),
        ))
    weight_commands.extend((
        ("Switch Joint", s.switchJoint,
         "Advance to the next unlocked influence on the selected skin", ""),
        ("Switch Brush", b.SwitchBrush,
         "Switch the active Paint Skin brush", ""),
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
                ("Rotate Together", partial(k.CreateKeyframe, {
                    "space": space, "type": "rotate", "inturn": False, "ui": distance_ui}), "", ""),
                ("Translate Together", partial(k.CreateKeyframe, {
                    "space": space, "type": "translate", "inturn": False, "ui": distance_ui}), "", ""),
            ],
        ))

    return [
        ("paint", "PAINT & BRUSH", [
            ("quick", "Default Brush", [
                ("Smooth", partial(b.smooth, "solid"), "Smooth painted weights", "primary"),
                ("Flood", b.flood, "Flood with current brush value", ""),
                ("Pick Value", b.pickValue, "Sample a skin weight", ""),
                ("Copy Weight", b.CopyWeight, "Copy skin weight", ""),
            ]),
            ("locks", "Influence locks", [
                # Two columns / four rows under the influence hierarchy.
                # Column 1: Unlock, Add Unlock, Add Up, Add Down.
                # Column 2: Unlock All, Isolate, Unlock 2, Unlock Affect.
                ("Unlock", s.unlock, "Unlock only this joint; lock all other influences", ""),
                ("Add Unlock", s.addUnlock, "Unlock this joint without changing the others", ""),
                ("Add Up", s.addUnlockUp, "Unlock this joint and its bound parent", ""),
                ("Add Down", s.addUnlockDown, "Unlock this joint and its bound child", ""),
                ("Unlock All", s.unlockAll, "Unlock all influences in the current skin", ""),
                ("Isolate", s.IsolateEffectVertex, "Isolate vertices weighted to this joint", ""),
                ("Unlock 2", s.UnlockTwoJoints,
                 "Unlock the two strongest influences of the selected vertex", ""),
                ("Unlock Affect", s.UnlockInfluenceJoints,
                 "Unlock every influence affecting any selected vertex (weight > 0)", ""),
            ]),
            ("helpers", "Advance Tool", [
                ("Middle Weight", s.setMiddleWeight, "", ""),
                ("Transfer", t.CreateUI, "Open transfer tool", ""),
                ("Eye Lid", e.EyelidSurfaceSkinUI, "Open eyelid skin tool", ""),
                ("Graph Skinning", graph.CreateUI, "Open graph editor", "primary"),
            ]),
            ("extras", "Paint helpers", [
                ("Copy Ratio", b.CopyRatio, "Copy weight ratio", ""),
                ("Prune", s.pruneSmallWeights, "", ""),
            ]),
        ]),
        ("weight", "WEIGHT ADJUSTMENTS", [
            ("increment", "Weight - / +", weight_commands),
        ]),
        ("skin", "SKIN & JOINTS", [
            ("bind", "Skin and influences", [
                ("Bind Skin", g.bindSkin, "", ""),
                ("Copy Skin", g.copyJointBind, "Select source mesh first, then destination mesh(es)", ""),
                ("Add Joint", s.AddJoint, "Joint(s) and mesh(es)", ""),
                ("Add Mesh Joint", s.AddMeshJoint, "Select source skinned mesh, then destination skinned mesh(es)", ""),
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
                ("Delete Keys", k.deleteSenceKeyframe, "Delete generated animation tests, not existing control animation", ""),
                ("Zoom Range", k.ZoomRangeAnim, "Zoom to nearby keys on controls or test drivers", ""),
                ("Delete Attr Keys", k.DeleteAttrKeyframes, "Delete generated tests for selected controls, else cut selected animation keys", ""),
                ("Fit Range", k.FitRangeAnim, "Fit keys on selected controls or animation-test drivers", ""),
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
    ("paint", "extras"): 88,
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
    ("paint", "quick"): 1,
    ("paint", "locks"): 2,
    ("paint", "helpers"): 1,
    ("paint", "extras"): 2,
    ("weight", "increment"): 2,
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
    "Rotate Together": "Rotate Tog",
    "Translate Together": "Trans Tog",
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

    def __init__(self, parent=None, cell_width=86, compact=True,
                 max_columns=2, force_two_columns=False, height_reduction=0):
        super(ResponsiveButtons, self).__init__(parent)
        self.items = []
        self.cell_width = cell_width
        self.max_columns = max_columns
        self.force_two_columns = force_two_columns
        self.height_reduction = height_reduction
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
        columns = (min(len(active), self.max_columns)
                   if self.force_two_columns and active else
                   max(1, min(len(active), self.max_columns,
                              (width + gap) // (min_width + gap))))
        positions = tuple(active)
        # Refresh text even when the column count stays the same after resizing.
        cell_width = max(24, (width - max(0, columns - 1) * gap) // columns)
        for button in active:
            button.setFixedHeight((23 if self.compact else 29) - self.height_reduction)
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
        QtWidgets.QWidget.resizeEvent(self, event)
        self.reflow()


WEIGHT_STEPS = ("0.0001", "0.0005", "0.001", "0.005",
                "0.01", "0.03", "0.05", "0.1")


def weight_grid_position(name):
    """Switches share their own top row; signed weight steps stay paired."""
    if name == "Switch Joint":
        return 0, 0
    if name == "Switch Brush":
        return 0, 1
    if name == "Set 0":
        return 1, 0
    if name == "Set 1":
        return 1, 1
    if name[:1] in ("-", "+") and name[1:] in WEIGHT_STEPS:
        return WEIGHT_STEPS.index(name[1:]) + 2, int(name[0] == "+")
    return len(WEIGHT_STEPS) + 2, 0


class WeightPairButtons(ResponsiveButtons):
    """Keep legacy +/- weight steps paired in two columns."""

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
            button.setFixedHeight((23 if self.compact else 29) - self.height_reduction)
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



def _skin_from_selection():
    """Return only a skinCluster actually bound to the selected mesh."""
    import NLTA_Skinning
    for component in cmds.ls(selection=True, long=True) or []:
        node = component.split(".", 1)[0]
        try:
            data = NLTA_Skinning.GetSkinData(node)
        except (RuntimeError, ValueError, TypeError):
            continue
        if data.get("skinCluster"):
            return data
    return None


def _selected_unskinned_mesh():
    """Distinguish a new unbound mesh from a joint selection."""
    for component in cmds.ls(selection=True, long=True) or []:
        node = component.split(".", 1)[0]
        if not cmds.objExists(node):
            continue
        node_type = cmds.nodeType(node)
        if node_type == "mesh":
            return True
        if node_type == "transform":
            shapes = cmds.listRelatives(
                node, shapes=True, noIntermediate=True, fullPath=True) or []
            if any(cmds.nodeType(shape) == "mesh" for shape in shapes):
                return True
    return False


def _skin_influence_rows(skin):
    """Use the same authoritative full DAG influence paths as paint callbacks."""
    if not skin or not cmds.objExists(skin):
        return []
    try:
        import NLTA_Skinning
        names = NLTA_Skinning._SkinInfluencePaths(skin)
    except (ImportError, AttributeError):
        # Compatibility for older installations; current public library
        # resolves these identities through MFnSkinCluster.
        names = []
        for name in cmds.skinCluster(skin, query=True, influence=True) or []:
            matches = cmds.ls(name, long=True, type="joint") or []
            if len(matches) == 1:
                names.append(matches[0])
    rows = []
    for joint in names:
        if not cmds.objExists(joint) or cmds.nodeType(joint) != "joint":
            continue
        attr = joint + ".liw"
        locked = bool(cmds.getAttr(attr)) if cmds.objExists(attr) else None
        rows.append((joint, locked))
    return rows


def _set_influence_locks(skin, joints, mode):
    """Edit skinCluster influences only; 1 means locked, 0 means unlocked."""
    if mode not in ("lock", "unlock", "reverse"):
        raise ValueError("Unsupported influence lock mode: " + mode)
    available = dict(_skin_influence_rows(skin))
    changed = 0
    for joint in dict.fromkeys(joints):
        if joint not in available or available[joint] is None:
            continue
        current = available[joint]
        locked = (not current if mode == "reverse" else mode == "lock")
        if locked == current:
            continue
        try:
            cmds.setAttr(joint + ".liw", int(locked))
            changed += 1
        except RuntimeError as exc:
            cmds.warning("Cannot change skin influence lock {}: {}".format(
                joint, exc))
    return changed


def _influence_action_plan(skin, joint, action):
    """Resolve each inline action against the exact bound DAG joint.

    Exclusive operations match the original singleUnlock behavior. Add Unlock
    keeps existing locks, while Add Up/Down unlock the clicked joint and its
    directly adjacent bound parent/child (then focus the latter).
    """
    available = [name for name, _ in _skin_influence_rows(skin)]
    if joint not in available:
        cmds.warning("The clicked joint is no longer bound to this skinCluster.")
        return None
    bound = set(available)
    if action in ("unlock", "lock_inverse"):
        # Exclusive: clicked joint unlocked; every other bound influence locked.
        return True, [joint], joint
    if action == "unlock_all":
        return False, available, joint
    if action == "add_unlock":
        return False, [joint], joint
    if action in ("add_up", "add_down"):
        if action == "add_up":
            relatives = cmds.listRelatives(
                joint, parent=True, type="joint", fullPath=True) or []
        else:
            relatives = cmds.listRelatives(
                joint, children=True, type="joint", fullPath=True) or []
        linked = [candidate for name in relatives
                  for candidate in [_resolve_skin_influence(skin, name, bound)]
                  if candidate]
        if not linked:
            cmds.warning("No bound {} joint found for {}.".format(
                "parent" if action == "add_up" else "child", joint))
            return None
        return True, [joint, linked[0]], linked[0]
    cmds.warning("Unsupported inline influence action: " + action)
    return None


def _resolve_skin_influence(skin, name, bound=None):
    """Resolve Maya's short paint-influence names against this skin's full DAG paths."""
    if not name or not skin:
        return None
    if isinstance(name, (list, tuple)):
        name = name[0] if len(name) == 1 else None
    if not isinstance(name, str):
        return None
    name = name.split(".", 1)[0]
    if bound is None:
        bound = {joint for joint, _ in _skin_influence_rows(skin)}
    if name in bound:
        return name
    try:
        candidates = cmds.ls(name, long=True, type="joint") or []
    except RuntimeError:
        return None
    resolved = [joint for joint in candidates if joint in bound]
    return resolved[0] if len(resolved) == 1 else None


def _active_skin_paint_influence(skin, bound=None):
    """Read Maya Paint Skin Weights selection; fall back to skin.paintTrans."""
    if not skin or not cmds.objExists(skin):
        return None
    context = "artAttrSkinContext"
    try:
        if cmds.artAttrSkinPaintCtx(context, exists=True):
            active = cmds.artAttrSkinPaintCtx(
                context, query=True, influence=True)
            resolved = _resolve_skin_influence(skin, active, bound)
            if resolved:
                return resolved
    except (RuntimeError, ValueError, TypeError):
        pass
    try:
        connection = cmds.connectionInfo(
            skin + ".paintTrans", sourceFromDestination=True) or ""
        return _resolve_skin_influence(
            skin, connection.split(".", 1)[0], bound)
    except (RuntimeError, ValueError):
        return None


def _activate_skin_paint_influence(skin, mesh, joint, bound=None):
    """Activate painting on a bound joint, preserving mesh/vertex selection."""
    if not skin or not mesh:
        return False
    joint = _resolve_skin_influence(skin, joint, bound)
    if not joint:
        cmds.warning("Choose a joint bound to the current skinCluster.")
        return False
    try:
        import NLTA_Skinning
        select = getattr(NLTA_Skinning, "SelectPaintInfluence", None)
        if not callable(select):
            cmds.warning("Update NLTA_Skinning.py to enable native Paint Skin synchronization.")
            return False
        return bool(select(mesh, joint))
    except (RuntimeError, ValueError) as exc:
        cmds.warning("Unable to select paint influence {}: {}".format(
            joint, exc))
        return False


def _influence_hierarchy(rows):
    """Use the nearest bound DAG ancestor; omit non-skin influences."""
    joints = {joint for joint, _ in rows}
    parents = {}
    for joint, _ in rows:
        ancestor = joint.rsplit("|", 1)[0] if "|" in joint else ""
        while ancestor and ancestor not in joints:
            ancestor = ancestor.rsplit("|", 1)[0]
        parents[joint] = ancestor if ancestor in joints else None
    return parents


class InfluencePanel(QtWidgets.QFrame):
    """Live influence list for the selected skinned mesh; no weight edits."""

    def __init__(self, parent=None):
        super(InfluencePanel, self).__init__(parent)
        self.setObjectName("SkinningInfluencePanel")
        self.setMinimumWidth(450)
        self.setMaximumWidth(800)
        self.skin = None
        self.mesh = None
        self._rows = []
        self._items = {}
        self._parents = {}
        self._tree_skin = None
        self._populating = False
        self._syncing = False
        self._editing_locks = False
        self._pending_locks = {}
        self._pending_lock_skin = None
        self._pending_context_action = None
        self._context_timer = QtCore.QTimer(self)
        self._context_timer.setSingleShot(True)
        self._context_timer.timeout.connect(self._apply_influence_action)
        self._lock_timer = QtCore.QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._apply_pending_locks)
        self._active_joint = None
        self._live_ticks = 0
        self._jobs = []
        self._live_timer = QtCore.QTimer(self)
        self._live_timer.setInterval(300)
        self._live_timer.timeout.connect(self.sync_live)

        column = QtWidgets.QVBoxLayout(self)
        column.setContentsMargins(7, 7, 7, 7)
        column.setSpacing(5)

        heading = QtWidgets.QHBoxLayout()
        self.heading_label = QtWidgets.QLabel("SKIN INFLUENCES")
        heading.addWidget(self.heading_label)
        heading.addStretch()
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.setObjectName("SkinningInfluenceRefresh")
        refresh.setToolTip("Read the skinned mesh from current Maya selection")
        refresh.clicked.connect(lambda checked=False: self.refresh())
        heading.addWidget(refresh)
        column.addLayout(heading)

        self.search = QtWidgets.QLineEdit()
        self.search.setObjectName("SkinningInfluenceSearch")
        self.search.setPlaceholderText("Filter joint names...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_rows)
        column.addWidget(self.search)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setObjectName("SkinningInfluenceTree")
        self.tree.setHeaderLabels(("Influence joint", "Lock"))
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(14)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)
        self.tree.setColumnWidth(1, INFLUENCE_LOCK_WIDTH)
        self.tree.headerItem().setTextAlignment(1, QtCore.Qt.AlignCenter)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tree.setToolTip(
            "The blue row is the active influence in Maya Paint Skin Weights.\n"
            "A black mesh can mean this joint has no weight in the viewed area.\n"
            "Use the Lock checkbox to change this joint\'s lock state.")
        self.tree.itemChanged.connect(self.change_item_lock)
        self.tree.currentItemChanged.connect(self.change_active_influence)
        self.tree.itemDoubleClicked.connect(self.select_joint)
        column.addWidget(self.tree, 1)

        self.status = QtWidgets.QLabel("0 joints")
        self.status.setObjectName("SkinningInfluenceStatus")
        column.addWidget(self.status)

        # Four visual columns: two Influence Locks, one Default Brush,
        # one Advance Tool. Build group frames directly into this layout.
        self.lock_area = QtWidgets.QHBoxLayout()
        self.lock_area.setContentsMargins(0, 2, 0, 0)
        self.lock_area.setSpacing(3)
        column.addLayout(self.lock_area)

    def activate(self):
        if not self._jobs:
            for event in ("SelectionChanged", "SceneOpened", "NewSceneOpened"):
                callback = (self.on_selection_changed if event == "SelectionChanged"
                            else self.reset_scene)
                try:
                    self._jobs.append(cmds.scriptJob(
                        event=[event, callback]))
                except RuntimeError:
                    pass
        self.refresh()
        self._live_timer.start()
        self.sync_live()

    def deactivate(self):
        self._live_timer.stop()
        self._context_timer.stop()
        self._pending_context_action = None
        self._lock_timer.stop()
        self._pending_locks.clear()
        self._pending_lock_skin = None
        for job in self._jobs:
            if cmds.scriptJob(exists=job):
                cmds.scriptJob(kill=job, force=True)
        self._jobs = []

    def reset_scene(self):
        self._context_timer.stop()
        self._pending_context_action = None
        self._lock_timer.stop()
        self._pending_locks.clear()
        self._pending_lock_skin = None
        self.skin = None
        self.mesh = None
        self._active_joint = None
        self.refresh(prefer_selection=False)

    def on_selection_changed(self):
        # A Maya SelectionChanged scriptJob may be fired synchronously while
        # artAttrSkinPaintCtx or setAttr is still processing a Qt item signal.
        # Never clear/rebuild that signal's QTreeWidgetItem.
        if (self._populating or self._syncing or self._editing_locks
                or self._pending_locks):
            return
        data = _skin_from_selection()
        if data:
            skin = data["skinCluster"]
            mesh = data["mesh"]
            if skin != self.skin or mesh != self.mesh:
                self.skin = skin
                self.mesh = mesh
                self.refresh(prefer_selection=False)
            else:
                self.sync_from_paint()
        elif _selected_unskinned_mesh() or (
                self.skin and not cmds.objExists(self.skin)):
            self.reset_scene()

    def refresh(self, prefer_selection=True):
        if prefer_selection:
            data = _skin_from_selection()
            if data:
                self.skin = data["skinCluster"]
                self.mesh = data["mesh"]
            elif _selected_unskinned_mesh():
                self.skin = None
                self.mesh = None
        if self.skin and not cmds.objExists(self.skin):
            self.skin = None
            self.mesh = None
        rows = _skin_influence_rows(self.skin)
        self.heading_label.setToolTip(
            "{}\nSkin: {}".format(self.mesh, self.skin) if self.skin
            else "Select a skinned mesh or vertices")
        # Reuse existing items when only .liw has changed. A clear() from
        # inside itemChanged/currentItemChanged can crash Maya in native Qt.
        if (self.skin == self._tree_skin
                and {joint for joint, _ in rows} == set(self._items)):
            self.sync_lock_states(rows)
        else:
            self._rows = rows
            self.populate()
        self.sync_from_paint()

    def populate(self):
        # Hierarchy topology changed: never apply actions to old rows.
        self._context_timer.stop()
        self._pending_context_action = None
        self._lock_timer.stop()
        self._pending_locks.clear()
        self._pending_lock_skin = None
        selected = {item.data(0, QtCore.Qt.UserRole)
                    for item in self.tree.selectedItems()}
        expanded = {joint for joint, item in self._items.items()
                    if item.isExpanded()}
        first_load = self._tree_skin != self.skin
        if first_load:
            self._active_joint = None
        self._parents = _influence_hierarchy(self._rows)
        self._populating = True
        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            self._items = {}
            for joint, locked in sorted(self._rows,
                                        key=lambda entry: entry[0].casefold()):
                item = QtWidgets.QTreeWidgetItem(
                    [joint.rsplit("|", 1)[-1], ""])
                item.setData(0, QtCore.Qt.UserRole, joint)
                item.setToolTip(0, joint)
                item.setTextAlignment(1, QtCore.Qt.AlignCenter)
                item.setSizeHint(
                    1, QtCore.QSize(INFLUENCE_LOCK_WIDTH, INFLUENCE_CELL_HEIGHT))
                if locked is not None:
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                    item.setCheckState(
                        1, QtCore.Qt.Checked if locked else QtCore.Qt.Unchecked)
                self._items[joint] = item

            for joint in sorted(self._items, key=str.casefold):
                item = self._items[joint]
                parent = self._parents.get(joint)
                if parent:
                    self._items[parent].addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                if joint in selected:
                    item.setSelected(True)

            if first_load:
                self.tree.expandToDepth(1)
            else:
                for joint in expanded:
                    if joint in self._items:
                        self._items[joint].setExpanded(True)
        finally:
            self.tree.blockSignals(False)
            self.tree.setUpdatesEnabled(True)
            self._populating = False
        self._tree_skin = self.skin
        self.filter_rows()

    def filter_rows(self, *_):
        # Filtering a tree must never change Maya's active paint influence.
        blocked = self.tree.blockSignals(True)
        try:
            phrase = self.search.text().strip().casefold()
            matched = {joint for joint, _ in self._rows
                       if phrase in joint.casefold()}
    
            # Keep the live active influence visible even while filtering.
            visible = set(matched)
            if self._active_joint in self._items:
                visible.add(self._active_joint)
            for joint in visible.copy():
                parent = self._parents.get(joint)
                while parent:
                    visible.add(parent)
                    if phrase:
                        self._items[parent].setExpanded(True)
                    parent = self._parents.get(parent)
    
            for joint, item in self._items.items():
                item.setHidden(joint not in visible)
                if joint not in visible:
                    item.setSelected(False)
    
            locked_count = sum(locked is True for _, locked in self._rows)
            unlocked_count = sum(locked is False for _, locked in self._rows)
            self.status.setText("{} matched / {} joints  |  {} locked  |  {} unlocked".format(
                len(matched), len(self._rows), locked_count, unlocked_count))
    
        finally:
            self.tree.blockSignals(blocked)

    def run_selected_action(self, action):
        """Apply Influence Locks buttons to the highlighted bound joint."""
        if not self.skin or not cmds.objExists(self.skin):
            cmds.warning("Choose a skinned mesh first")
            return
        if action == "unlock_all":
            self.change_locks("unlock", False)
            return
        current = self.tree.currentItem()
        joint = current.data(0, QtCore.Qt.UserRole) if current else None
        if joint not in self._items:
            joint = self._active_joint if self._active_joint in self._items else None
        if joint is None:
            cmds.warning("Select an influence joint in the list first")
            return
        if action == "toggle_lock":
            self.queue_inline_lock(joint)
        else:
            self.queue_influence_action(joint, action)

    def queue_inline_lock(self, joint):
        """Preview checkbox state now, defer the Maya setAttr until Qt is idle."""
        if not self.skin or joint not in self._items:
            return
        if self._pending_lock_skin != self.skin:
            self._pending_locks.clear()
            self._pending_lock_skin = self.skin
        item = self._items[joint]
        current = self._pending_locks.get(
            joint, item.checkState(1) == QtCore.Qt.Checked)
        next_locked = not current
        self._pending_locks[joint] = next_locked
        blocked = self.tree.blockSignals(True)
        try:
            item.setCheckState(
                1, QtCore.Qt.Checked if next_locked else QtCore.Qt.Unchecked)
        finally:
            self.tree.blockSignals(blocked)
        self._lock_timer.start(0)

    def queue_influence_action(self, joint, action, *args):
        """Defer Maya edits until after the viewport mouse event has unwound."""
        if not self.skin or joint not in self._items:
            return
        self._pending_context_action = (self.skin, joint, action)
        self._context_timer.start(0)

    def _apply_influence_action(self):
        request = self._pending_context_action
        self._pending_context_action = None
        if not request:
            return
        skin, joint, action = request
        if skin != self.skin or joint not in self._items or not cmds.objExists(skin):
            return
        # A context menu operation supersedes an uncommitted checkbox click.
        self._lock_timer.stop()
        self._pending_locks.clear()
        self._pending_lock_skin = None
        self._editing_locks = True
        try:
            if action in ("isolate", "un_isolate"):
                import NLTA_Skinning
                if action == "isolate":
                    NLTA_Skinning.IsolateEffectVertex(
                        mesh=self.mesh, joint=joint)
                else:
                    NLTA_Skinning.UnIsolateEffectVertex(
                        mesh=self.mesh, joint=joint)
                focused = joint
            else:
                plan = _influence_action_plan(skin, joint, action)
                if plan is None:
                    return
                exclusive, targets, focused = plan
                if exclusive:
                    others = [name for name, _ in _skin_influence_rows(skin)
                              if name not in targets]
                    _set_influence_locks(skin, others, "lock")
                _set_influence_locks(skin, targets, "unlock")
                self.sync_lock_states()
            if _activate_skin_paint_influence(
                    skin, self.mesh, focused, self._items):
                self._active_joint = focused
                live_item = self._items.get(focused)
                if live_item is not None:
                    blocked = self.tree.blockSignals(True)
                    try:
                        self.tree.clearSelection()
                        self.tree.setCurrentItem(live_item)
                        live_item.setSelected(True)
                        self.filter_rows()
                    finally:
                        self.tree.blockSignals(blocked)
        finally:
            self._editing_locks = False

    def change_item_lock(self, item, column):
        if (self._populating or self._syncing or self._editing_locks
                or column != 1 or not self.skin):
            return
        joint = item.data(0, QtCore.Qt.UserRole)
        if joint not in self._items or not cmds.objExists(self.skin):
            return
        # Do not call cmds.setAttr, Maya MEL, refresh or tree.clear from
        # QTreeWidget.itemChanged: all can re-enter Maya's Qt event loop and
        # invalidate the item whose checkbox is still being processed.
        if self._pending_lock_skin != self.skin:
            self._pending_locks.clear()
            self._pending_lock_skin = self.skin
        self._pending_locks[joint] = item.checkState(1) == QtCore.Qt.Checked
        self._lock_timer.start(0)

    def _apply_pending_locks(self):
        """Commit checked states after the native Qt itemChanged signal unwinds."""
        queued = self._pending_locks
        skin = self._pending_lock_skin
        self._pending_locks = {}
        self._pending_lock_skin = None
        if not queued or skin != self.skin or not cmds.objExists(skin):
            return
        self._editing_locks = True
        try:
            bound = set(self._items)
            locked = [joint for joint, value in queued.items()
                      if joint in bound and value]
            unlocked = [joint for joint, value in queued.items()
                        if joint in bound and not value]
            if locked:
                _set_influence_locks(skin, locked, "lock")
            if unlocked:
                _set_influence_locks(skin, unlocked, "unlock")
            self.sync_lock_states()
        finally:
            self._editing_locks = False

    def change_locks(self, mode, selected_only):
        # A batch operation supersedes pending individual checkbox changes.
        self._lock_timer.stop()
        self._pending_locks.clear()
        self._pending_lock_skin = None
        if not self.skin:
            cmds.warning("Choose a skinned mesh first")
            return
        if selected_only:
            joints = [item.data(0, QtCore.Qt.UserRole)
                      for item in self.tree.selectedItems() if not item.isHidden()]
            if not joints:
                cmds.warning("Select influence rows in the table first")
                return
        else:
            joints = [joint for joint, _ in self._rows]
        self._editing_locks = True
        try:
            _set_influence_locks(self.skin, joints, mode)
            self.sync_lock_states()
        finally:
            self._editing_locks = False

    def change_active_influence(self, item, previous):
        """A click/keyboard selection switches Maya's active paint influence."""
        if (self._populating or self._syncing or self._editing_locks
                or self._pending_locks or not item or not self.skin):
            return
        joint = item.data(0, QtCore.Qt.UserRole)
        if joint not in self._items:
            return
        # Keep the guard active throughout Maya MEL and Qt selection updates.
        # Both can synchronously invoke scriptJobs and nested UI signals.
        self._syncing = True
        blocked = self.tree.blockSignals(True)
        try:
            if not _activate_skin_paint_influence(
                    self.skin, self.mesh, joint, self._items):
                return
            self._active_joint = joint
            live_item = self._items.get(joint)
            if live_item is not None:
                self.tree.clearSelection()
                self.tree.setCurrentItem(live_item)
                live_item.setSelected(True)
            self.filter_rows()
        finally:
            self.tree.blockSignals(blocked)
            self._syncing = False

    def select_joint(self, item, column):
        """Double-click also activates painting; do not select the DAG joint."""
        self.change_active_influence(item, None)

    def sync_from_paint(self):
        """Highlight an influence selected in Maya's Paint Skin Weights UI."""
        if (self._syncing or self._populating or self._editing_locks
                or self._pending_locks or not self.skin):
            return
        joint = _active_skin_paint_influence(self.skin, self._items)
        if not joint or joint not in self._items:
            return
        if joint == self._active_joint and self.tree.currentItem() is self._items[joint]:
            return
        self._syncing = True
        self.tree.blockSignals(True)
        try:
            self._active_joint = joint
            self.filter_rows()
            item = self._items[joint]
            self.tree.clearSelection()
            self.tree.setCurrentItem(item)
            item.setSelected(True)
            parent = item.parent()
            while parent:
                parent.setExpanded(True)
                parent = parent.parent()
            self.tree.scrollToItem(
                item, QtWidgets.QAbstractItemView.PositionAtCenter)
        finally:
            self.tree.blockSignals(False)
            self._syncing = False

    def sync_lock_states(self, rows=None):
        """Update checkboxes without rebuilding the hierarchy on .liw changes."""
        if not self.skin or self._populating:
            return
        if rows is None:
            rows = _skin_influence_rows(self.skin)
        if rows == self._rows and all(
                joint not in self._items or locked is None
                or self._items[joint].checkState(1) == (
                    QtCore.Qt.Checked if locked else QtCore.Qt.Unchecked)
                for joint, locked in rows):
            return
        if {joint for joint, _ in rows} != set(self._items):
            self._rows = rows
            self.populate()
            self.sync_from_paint()
            return
        self._rows = rows
        blocked = self.tree.blockSignals(True)
        try:
            for joint, locked in rows:
                item = self._items.get(joint)
                if item and locked is not None:
                    state = QtCore.Qt.Checked if locked else QtCore.Qt.Unchecked
                    if item.checkState(1) != state:
                        item.setCheckState(1, state)
        finally:
            self.tree.blockSignals(blocked)
        self.filter_rows()

    def sync_live(self):
        """Lightweight Maya polling, only while the Skinning window is visible."""
        if (self._populating or self._syncing or self._editing_locks
                or self._pending_locks or not self.skin):
            return
        self.sync_from_paint()
        self._live_ticks += 1
        if self._live_ticks % 3 == 0:
            self.sync_lock_states()


class SkinningBoard(QtWidgets.QWidget):
    def __init__(self, catalog, distance_ui, uis):
        super(SkinningBoard, self).__init__()
        self.setObjectName("NLTA_SkinningCommandBoard")
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMinimumWidth(900)
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
        # Small title only; global search/density/max width/paint toolbar removed.
        self.title = QtWidgets.QLabel("SKINNING")
        self.title.setObjectName("SkinningBoardTitle")
        outer.addWidget(self.title)
        self.max_width_value = int(self.settings.value("max_region_width", 230))

        self.workspace = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.workspace.setObjectName("SkinningWorkspaceSplitter")
        self.workspace.setChildrenCollapsible(False)
        outer.addWidget(self.workspace, 1)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setObjectName("SkinningBoardScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        # Compact Paint/Weight strip to the LEFT of the joint hierarchy.
        # Keep the original buttons and callbacks; no duplicate commands.
        self.paint_scroll = QtWidgets.QScrollArea()
        self.paint_scroll.setObjectName("SkinningPaintWeightScroll")
        self.paint_scroll.setWidgetResizable(True)
        self.paint_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.paint_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.paint_scroll.setFixedWidth(PAINT_STRIP_WIDTH)
        self.paint_scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        paint_host = QtWidgets.QWidget()
        paint_host.setObjectName("SkinningPaintWeightContent")
        self.paint_stack = QtWidgets.QVBoxLayout(paint_host)
        self.paint_stack.setContentsMargins(1, 1, 1, 3)
        self.paint_stack.setSpacing(1)
        self.paint_stack.addStretch()
        self.paint_scroll.setWidget(paint_host)

        # Seamless left-side dock: narrow two-column actions + joint hierarchy.
        # Remaining tool sections appear to the right of the dock.
        self.influence_actions = QtWidgets.QFrame(self.workspace)
        self.influence_actions.setObjectName("SkinningInfluenceActionsDock")
        dock_layout = QtWidgets.QHBoxLayout(self.influence_actions)
        dock_layout.setContentsMargins(0, 0, 0, 0)
        dock_layout.setSpacing(0)
        self.influences = InfluencePanel(self.influence_actions)
        dock_layout.addWidget(self.paint_scroll, 0)
        dock_layout.addWidget(self.influences, 1)
        self.workspace.addWidget(self.influence_actions)
        self.workspace.addWidget(self.scroll)
        self.workspace.setStretchFactor(0, 0)
        self.workspace.setStretchFactor(1, 1)
        self.workspace.setSizes([720, 440])
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

        left_groups = {}
        for key, section_title, groups in catalog:
            left_dock = key in LEFT_DOCK_SECTIONS
            if not left_dock:
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
                # Build each left group directly in its permanent container.
                # This avoids reparenting Qt widgets after creation (important
                # for Maya hot reload and QTreeWidget signal stability).
                if left_dock:
                    group_frame = QtWidgets.QFrame()
                    group_frame.setObjectName(
                        "SkinningDockGroup_{}_{}".format(key, group_key))
                    group_vertical = QtWidgets.QVBoxLayout(group_frame)
                    group_vertical.setContentsMargins(3, 3, 3, 3)
                    group_vertical.setSpacing(2)
                    if (key, group_key) in (
                            ("animation", "local"), ("weight", "increment")):
                        heading_label = QtWidgets.QLabel(section_title)
                        heading_label.setObjectName("SkinningSectionTitle")
                        group_vertical.addWidget(heading_label)
                else:
                    group_vertical = vertical
                subheading = QtWidgets.QLabel(heading)
                subheading.setObjectName("SkinningSubheading")
                group_vertical.addWidget(subheading)
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
                    group_vertical.addLayout(spin_row)
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
                    group_vertical.addLayout(distance_row)

                # Two columns per Paint group; +/- weights retain paired rows.
                grid_type = WeightPairButtons if key == "weight" else ResponsiveButtons
                grid = grid_type(
                    cell_width=GROUP_CELL_WIDTHS.get((key, group_key), 86),
                    compact=self.compact,
                    max_columns=GROUP_MAX_COLUMNS.get((key, group_key), 2),
                    force_two_columns=(
                        key == "animation" or (key, group_key) == ("paint", "locks")),
                    height_reduction=2 if key in LEFT_DOCK_SECTIONS else 0)
                self.grids.append(grid)
                group_vertical.addWidget(grid)
                entries = []
                ordered_items = (sorted(
                    items, key=lambda item: weight_grid_position(item[0]))
                    if key == "weight" else items)
                for label, callback, tooltip, role in ordered_items:
                    if (key, group_key) == ("paint", "locks") and label in INFLUENCE_LOCK_ACTIONS:
                        callback = partial(self.influences.run_selected_action,
                                           INFLUENCE_LOCK_ACTIONS[label])
                    action_id = "/".join((key, group_key, label))
                    button = self.make_button(label, callback, tooltip, role, action_id)
                    grid.add_button(button)
                    self.buttons[action_id] = (button, callback, label, tooltip, role)
                    entries.append((action_id, button))
                group_records.append((subheading, grid, entries))
                if left_dock:
                    if (key, group_key) in (
                            ("paint", "locks"), ("paint", "quick"),
                            ("paint", "helpers")):
                        # Creation order is quick/locks/helpers; insert into
                        # locks/quick/helpers order without later reparenting.
                        position = {"locks": 0, "quick": 1, "helpers": 2}[group_key]
                        stretch = 2 if group_key == "locks" else 1
                        group_frame.setMinimumWidth(160 if stretch == 2 else 80)
                        self.influences.lock_area.insertWidget(
                            position, group_frame, stretch)
                    else:
                        left_groups[(key, group_key)] = group_frame
            if not left_dock:
                self.sections.append((section, section_title, group_records))
                self.section_visibility[section] = True

        # Requested top-to-bottom order, independent of the legacy catalog
        # and without touching any Paint Skin influence item or callback.
        if set(left_groups) != set(LEFT_DOCK_GROUP_ORDER):
            raise ValueError("Skinning left dock groups must match the display order")
        for group_id in LEFT_DOCK_GROUP_ORDER:
            self.paint_stack.insertWidget(
                self.paint_stack.count() - 1, left_groups[group_id])

        self.content.addStretch()
        self.apply_style()
        self.scroll.viewport().installEventFilter(self)
        self.reflow_sections(force=True)
        shortcut_cls = getattr(QtWidgets, "QShortcut", None) or QtGui.QShortcut
        search_shortcut = shortcut_cls(QtGui.QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self.influences.search.setFocus)
        clear_shortcut = shortcut_cls(
            QtGui.QKeySequence("Esc"), self.influences.search)
        clear_shortcut.activated.connect(self.influences.search.clear)
        self.shortcuts = (search_shortcut, clear_shortcut)

    def eventFilter(self, watched, event):
        if (watched is self.scroll.viewport()
                and event.type() == QtCore.QEvent.Resize):
            self.reflow_sections()
        return QtWidgets.QWidget.eventFilter(self, watched, event)

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
        return total

    def reflow_sections(self, force=False):
        """Repack regions using persistent columns; never destroy cards on resize."""
        if self._reflowing:
            return
        available = max(1, self.scroll.viewport().width() - 3)
        region_width = max(210, min(440, self.max_width_value))
        visible = [record for record in self.sections
                   if self.section_visibility.get(record[0], True)
                   and record[0].objectName().replace(
                       "SkinningSection_", "") not in LEFT_DOCK_SECTIONS]
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

    def activate_paint(self, quiet=False):
        """Enter Paint Skin context without opening Maya Paint Tool Settings."""
        import NLTA_Skinning
        ensure = getattr(NLTA_Skinning, "EnsurePaintContext", None)
        if not callable(ensure):
            cmds.warning(
                "NLTA Skinning library is outdated: {}. "
                "Reinstall NLTA with AutoInstall.py and reopen Skinning."
                .format(getattr(NLTA_Skinning, "__file__", "<unknown>")))
            return False
        # A non-skin action (e.g. Clear Skins or export) can leave no skin in
        # the scene. Do not open Tool Settings or warn in that situation.
        if quiet and not NLTA_Skinning.EnsureSkinSession(warn=False):
            return False
        return bool(ensure())

    def dispatch(self, action_id, callback):
        # Read joint/vertex/control selections BEFORE entering Paint Skin for
        # operations that need them. Return to Paint Skin only afterward.
        needs_paint = (
            (action_id.startswith("weight/increment/")
             and action_id != "weight/increment/Switch Joint") or
            action_id in {
                "paint/quick/Smooth", "paint/quick/Flood",
                "paint/quick/Pick Value", "paint/extras/Prune"
            }
        )
        run_callback = True
        try:
            if action_id == "skin/max/Check":
                return callback(maxValue=self.max_influences.value())
            if action_id == "skin/max/Fix":
                return callback(maxInfluence=self.max_influences.value())
            if needs_paint and cmds.currentCtx() != "artAttrSkinContext":
                if not self.activate_paint():
                    run_callback = False
                    return
            return callback()
        finally:
            if run_callback:
                # Use only the Artisan paint context: never launch native
                # ArtPaintSkinWeightsToolOptions or the Tool Settings window.
                if cmds.currentCtx() != "artAttrSkinContext":
                    self.activate_paint(quiet=True)
                if action_id.startswith(("paint/locks/", "skin/bind/")):
                    self.influences.refresh()

    def showEvent(self, event):
        QtWidgets.QWidget.showEvent(self, event)
        self.influences.activate()

    def hideEvent(self, event):
        self.influences.deactivate()
        QtWidgets.QWidget.hideEvent(self, event)

    def closeEvent(self, event):
        self.influences.deactivate()
        self.settings.setValue("geometry_masonry", self.saveGeometry())
        QtWidgets.QWidget.closeEvent(self, event)

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
        left_dock = action_id.split("/", 1)[0] in LEFT_DOCK_SECTIONS
        button.setProperty("dock", "left" if left_dock else "main")
        button.setToolTip(label + ("\n" + tooltip if tooltip and tooltip != label else ""))
        button.full_label = label
        button.short_label = COMPACT_LABELS.get(label, label)
        button.setMinimumWidth(0)
        button.setMinimumHeight(20 if left_dock else 22)
        button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        # Do not pass the Qt clicked(bool) to legacy Maya callbacks.
        button.clicked.connect(
            lambda checked=False, key=action_id, fn=callback: self.dispatch(key, fn))
        return button

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
            QFrame#SkinningInfluenceActionsDock {
                background-color: #202020;
                border: 1px solid #454545;
                border-radius: 4px;
            }
            QScrollArea#SkinningPaintWeightScroll {
                background-color: #202020;
                border: none;
                border-right: 1px solid #454545;
            }
            QWidget#SkinningPaintWeightContent {
                background-color: #202020;
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
            QFrame#SkinningSection_animation {
                background-color: transparent;
                border: none;
                border-radius: 0;
            }
            QFrame#SkinningSection_skin, QFrame#SkinningSection_files,
            QFrame#SkinningSection_proxy, QFrame#SkinningSection_mesh {
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
            QPushButton#SkinningAction[dock="left"] {
                padding: 0px 3px;
                min-height: 17px;
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
            QFrame#SkinningInfluencePanel {
                background-color: #202020;
                border: none;
                border-radius: 0;
            }
            QFrame#SkinningDockGroup_paint_locks,
            QFrame#SkinningDockGroup_paint_quick,
            QFrame#SkinningDockGroup_paint_helpers {
                background-color: #202020;
                border-top: 1px solid #454545;
            }
            QLabel#SkinningInfluenceStatus {
                color: #B5B5B5;
                font-size: 10px;
            }
            QTreeWidget#SkinningInfluenceTree {
                background-color: #252525;
                alternate-background-color: #2D2D2D;
                color: #E5E5E5;
                border: 1px solid #454545;
                selection-background-color: #267AA5;
                selection-color: #FFFFFF;
            }
            QTreeWidget#SkinningInfluenceTree::item {
                min-height: 20px;
            }
            QTreeWidget#SkinningInfluenceTree::item:selected,
            QTreeWidget#SkinningInfluenceTree::item:selected:!active {
                background-color: #267AA5;
                color: #FFFFFF;
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
            if widget.objectName() != "NLTA_SkinningCommandBoard":
                continue
            # Older instances may still have event methods referring to the
            # new module's SkinningBoard class through super(). Patch only the
            # obsolete window class before calling hide/close.
            old_class = type(widget)
            if (old_class is not SkinningBoard
                    and old_class.__name__ == "SkinningBoard"):
                for handler in ("eventFilter", "showEvent", "hideEvent",
                                "closeEvent"):
                    setattr(old_class, handler, getattr(QtWidgets.QWidget, handler))
                for child in widget.findChildren(QtWidgets.QWidget):
                    child_class = type(child)
                    if child_class.__name__ in ("ResponsiveButtons",
                                                "WeightPairButtons"):
                        setattr(child_class, "resizeEvent",
                                QtWidgets.QWidget.resizeEvent)
            # Disconnect live callbacks before disposing of the old board.
            influences = getattr(widget, "influences", None)
            if influences is not None:
                influences.deactivate()  # Kill Maya scriptJobs as well as Qt timer.
            old_scroll = getattr(widget, "scroll", None)
            if old_scroll is not None:
                old_scroll.viewport().removeEventFilter(widget)
            widget.blockSignals(True)
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
        board.resize(1180, 790)
    _BOARD = board
    uis["board"] = board
    board.show()
    board.raise_()
    board.activateWindow()
    return board


def CreateUI(data, tools, uis):
    """Compatibility entry point: open only the floating Skinning board."""
    return OpenWindow(tools, uis)
