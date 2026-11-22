import inspect
import os
import textwrap
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General

ITEMS = {"rows": [], "list": None}


def DefaultSetting(path, *args):
    module = os.path.splitext(os.path.basename(__file__))[0]
    return {
        "ext": "json", "path": os.path.join(path, module + ".json"),
        "moduleName": module, "order": 0, "title": "Follow Matrix",
        "name": "Follow Matrix", "id": datetime.now().strftime("%Y%m%d%H%M%S"),
    }


def _data_path(data):
    item = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    if not item or not item.get("path"):
        raise ValueError("FollowMatrix: JSON path not found")
    return os.path.normpath(item["path"])


def _selected_pair():
    names = cmds.ls(selection=True, long=True, type="transform") or []
    if len(names) != 2:
        return "", ""
    return names[0], names[1]


def _pick(field, *args):
    names = cmds.ls(selection=True, long=True, type="transform") or []
    if len(names) != 1:
        cmds.warning("FollowMatrix: select one transform")
        return
    cmds.textField(field, edit=True, text=names[0])


def _remove(row, *args):
    if row in ITEMS["rows"]:
        ITEMS["rows"].remove(row)
    if cmds.layout(row["ui"], exists=True):
        cmds.deleteUI(row["ui"])


def Add(listUI, data=None, *args):
    data = data or {}
    parent, child = _selected_pair() if not data else ("", "")
    frame = cmds.frameLayout(label="Matrix Follow", collapsable=True,
                             collapse=False, parent=listUI)
    column = cmds.columnLayout(adjustableColumn=True, parent=frame)
    row = {"ui": frame}
    for key, label, value in (
        ("parent", "Parent FK", data.get("parent", parent)),
        ("child", "Child FK", data.get("child", child)),
    ):
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2,
                       columnWidth3=(80, 265, 45), parent=column)
        cmds.text(label=label)
        field = cmds.textField(text=value)
        row[key] = field
        cmds.button(label="Pick", command=partial(_pick, field))
        cmds.setParent("..")
    row["mode"] = cmds.optionMenu(label="Matrix Mode", parent=column)
    for value in ("Auto", "Hierarchy", "Additive", "Universal"):
        cmds.menuItem(label=value, parent=row["mode"])
    selected_mode = str(data.get("matrixMode", "Auto"))
    cmds.optionMenu(row["mode"], edit=True,
                    value=selected_mode if selected_mode in (
                        "Auto", "Hierarchy", "Additive", "Universal") else "Auto")
    cmds.button(label="Delete", parent=column, command=partial(_remove, row))
    ITEMS["rows"].append(row)
    return row


def _ui_data():
    result = []
    for row in ITEMS["rows"]:
        item = {"parent": cmds.textField(row["parent"], query=True, text=True).strip(),
                "child": cmds.textField(row["child"], query=True, text=True).strip()}
        mode = cmds.optionMenu(row["mode"], query=True, value=True)
        if mode != "Auto":
            item["matrixMode"] = mode
        result.append(item)
    return result


def _save(data, *args):
    items = _ui_data()
    NLTA_General.writeJsonFile(_data_path(data), items)
    return items


def Load(data, listUI, *args):
    for child in cmds.layout(listUI, query=True, childArray=True) or []:
        cmds.deleteUI(child)
    ITEMS["rows"][:] = []
    path = _data_path(data)
    items = NLTA_General.readJsonFile(path) if os.path.isfile(path) else []
    for entry in items or []:
        Add(listUI, entry)


def Form(data, *args):
    layout = NLTA_General.LoadModule("Scene_Form").Create(data)
    buttons, listUI = layout["buttonUI"], layout["listUI"]
    ITEMS["list"] = listUI
    cmds.rowColumnLayout(numberOfColumns=4, parent=buttons)
    cmds.button(label="Add", width=90, command=partial(Add, listUI))
    cmds.button(label="Save", width=90, command=partial(_save, data))
    cmds.button(label="Run", width=90, command=lambda *unused: (_save(data), Run(data)))
    export_button = cmds.button(label="Export Py", width=110,
                                command=lambda *unused: (_save(data), ExportPython(data)))
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", command=partial(OpenExportFolder, data))
    cmds.setParent("..", menu=True)
    cmds.setParent("..")
    Load(data, listUI)
    return layout


def BuildFollowMatrix(datas):
    # Stage: Resolve FK pairs and preserve their world-space bind pose.
    import maya.cmds as cmds
    import maya.api.OpenMaya as om

    def resolve(saved):
        saved = str(saved).strip()
        if not saved:
            raise ValueError("FollowMatrix: missing Parent/Child")
        matches = list(dict.fromkeys(cmds.ls(saved, long=True, type="transform") or []))
        if len(matches) != 1:
            leaf = saved.rsplit("|", 1)[-1]
            matches = list(dict.fromkeys(n for n in (cmds.ls(leaf, long=True, type="transform") or [])
                                         if n.rsplit("|", 1)[-1] == leaf))
        if len(matches) != 1:
            raise ValueError("FollowMatrix: missing/ambiguous object: " + saved)
        return matches[0]

    def parent_of(node):
        return (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]

    def lineage(node):
        out = []
        while node:
            out.append(node)
            node = parent_of(node)
        return out

    def leaf(node):
        return str(node).strip().rsplit("|", 1)[-1]

    def mmatrix(node):
        return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True)) if node else om.MMatrix()

    def invertible(matrix, label):
        if abs(matrix.det4x4()) < 1e-10:
            raise ValueError("FollowMatrix: singular matrix: " + label)
        return matrix

    def err(a, b):
        return max(abs(float(x) - float(y)) for x, y in zip(a, b))

    def require_fresh_rivet_order(child):
        immediate = parent_of(child)
        if immediate and leaf(immediate).endswith("_RivetDelta_GRP"):
            raise ValueError(
                "FollowMatrix: RigRivet Matrix Delta already exists above " + leaf(child)
                + ". Please build FollowMatrix FIRST, then RigRivet Matrix Delta."
                + " No existing Rivet connections were modified."
            )

    def choose_base(group, driver, selected):
        if not group:
            return None, "Universal"
        if selected == "Universal":
            return group, "Universal"
        if selected == "Hierarchy" and driver not in lineage(group):
            raise ValueError("FollowMatrix: Hierarchy mode requires Parent as a DAG ancestor")
        if selected in ("Auto", "Hierarchy", "Additive"):
            saw_jiggle = False
            for node in lineage(group):
                label = leaf(node).lower()
                if "jiggle" in label:
                    saw_jiggle = True
                if saw_jiggle and (label.endswith("_target") or label.endswith("_pos")):
                    if node == driver or node in lineage(driver):
                        break
                    return node, "Additive"
        return group, "Universal"

    if not isinstance(datas, list) or not datas:
        raise ValueError("FollowMatrix: no saved items")
    rows = []
    keys = set()
    for item in datas:
        driver = leaf(item.get("parent", ""))
        child = leaf(item.get("child", ""))
        if not driver or not child or driver == child:
            raise ValueError("FollowMatrix: invalid Parent/Child pair")
        if child in keys:
            raise ValueError("FollowMatrix: duplicated Child: " + child)
        keys.add(child)
        mode = str(item.get("matrixMode", "Auto"))
        if mode not in ("Auto", "Hierarchy", "Additive", "Universal"):
            raise ValueError("FollowMatrix: invalid matrixMode: " + mode)
        rows.append(item)

    # Topological order: changed full DAG paths are resolved again per step.
    ordered = []
    while rows:
        pending_children = {leaf(x["child"]) for x in rows}
        ready = [x for x in rows if leaf(x["parent"]) not in pending_children]
        if not ready:
            raise ValueError("FollowMatrix: cyclic Parent/Child definitions")
        ordered.extend(ready)
        rows = [x for x in rows if x not in ready]

    # Stage: Capture original DAG ancestry before inserting Follow offsets.
    original_children = {leaf(item["child"]): resolve(item["child"]) for item in ordered}
    for item in ordered:
        driver = resolve(item["parent"])
        child = resolve(item["child"])
        if driver == child or child in lineage(driver):
            raise ValueError("FollowMatrix: invalid Parent/Child cycle")
        require_fresh_rivet_order(child)
        if not cmds.getAttr(child + ".inheritsTransform"):
            raise ValueError("FollowMatrix: Child inheritsTransform must be enabled: " + child)
        old_parent = parent_of(child)
        short = leaf(child).replace(":", "_")
        if cmds.objExists(short + "_MatrixFollow_GRP"):
            raise ValueError("FollowMatrix: already built for " + short + "; open a clean scene")
        invertible(mmatrix(driver), "Parent " + driver)
        invertible(mmatrix(old_parent), "Group " + str(old_parent))
        invertible(mmatrix(child), "Child " + child)
        choose_base(old_parent, driver, str(item.get("matrixMode", "Auto")))

    results = []
    cumulative_shape_scales = {}
    changed = False
    failed = True
    cmds.undoInfo(openChunk=True, chunkName="Scene Pattern Follow Matrix")
    try:
        for item in ordered:
            driver = resolve(item["parent"])
            child = resolve(item["child"])
            require_fresh_rivet_order(child)
            group = parent_of(child)
            requested = str(item.get("matrixMode", "Auto"))
            base, mode = choose_base(group, driver, requested)
            p_bind, g_bind, b_bind = (invertible(mmatrix(driver), "Parent"),
                                      invertible(mmatrix(group), "Group"),
                                      invertible(mmatrix(base), "Base"))
            before = mmatrix(child)
            short = leaf(child).replace(":", "_")
            if cmds.objExists(short + "_MatrixFollow_GRP"):
                raise ValueError("FollowMatrix: already built for " + short)
            follow = (cmds.createNode("transform", name=short + "_MatrixFollow_GRP", parent=group)
                      if group else cmds.createNode("transform", name=short + "_MatrixFollow_GRP"))
            changed = True
            # Only insert above the chosen control; never reposition other offsets.
            cmds.parent(child, follow, relative=True)
            control_now = resolve(item["child"])
            if err(mmatrix(control_now), before) > 1e-3:
                raise RuntimeError("FollowMatrix: pose changed while parenting " + short)

            # Stage: Correct Child in parent space using the full live Parent matrix.
            mm = cmds.createNode("multMatrix", name=short + "_ParentFollow_MM")
            cmds.setAttr(mm + ".matrixIn[0]", *list(g_bind * p_bind.inverse()), type="matrix")
            cmds.connectAttr(driver + ".worldMatrix[0]", mm + ".matrixIn[1]")
            if base:
                cmds.connectAttr(base + ".worldInverseMatrix[0]", mm + ".matrixIn[2]")
            cmds.setAttr(mm + ".matrixIn[3]", *list(b_bind * g_bind.inverse()), type="matrix")
            cmds.connectAttr(mm + ".matrixSum", follow + ".offsetParentMatrix")
            control_now = resolve(item["child"])
            deviation = err(mmatrix(control_now), before)
            if deviation > 1e-3:
                raise RuntimeError("FollowMatrix: Matrix Correct altered bind pose %.6g: %s" %
                                   (deviation, short))
            # Stage: Compensate only NURBS control shapes, including corrected FK ancestors.
            shape_scale = cmds.createNode("decomposeMatrix", name=short + "_SHAPE_SCALE_DCM")
            cmds.connectAttr(mm + ".matrixSum", shape_scale + ".inputMatrix")
            shape_ratio = cmds.createNode("multiplyDivide", name=short + "_SHAPE_SCALE_RATIO_MD")
            cmds.setAttr(shape_ratio + ".operation", 2)
            for axis in "XYZ":
                scale_plug = shape_scale + ".outputScale" + axis
                bind_scale = float(cmds.getAttr(scale_plug))
                cmds.connectAttr(scale_plug, shape_ratio + ".input1" + axis)
                cmds.setAttr(shape_ratio + ".input2" + axis, bind_scale)
            combined_scale = shape_ratio + ".output"
            child_path = original_children[leaf(item["child"])]
            ancestors = [(path, plug) for path, plug in cumulative_shape_scales.values()
                         if child_path.startswith(path + "|")]
            if ancestors:
                inherited_scale = max(ancestors, key=lambda entry: entry[0].count("|"))[1]
                accumulated = cmds.createNode("multiplyDivide", name=short + "_SHAPE_CUMULATIVE_MD")
                cmds.setAttr(accumulated + ".operation", 1)
                cmds.connectAttr(inherited_scale, accumulated + ".input1")
                cmds.connectAttr(shape_ratio + ".output", accumulated + ".input2")
                combined_scale = accumulated + ".output"
            cumulative_shape_scales[leaf(item["child"])] = (child_path, combined_scale)
            shapes = cmds.listRelatives(control_now, shapes=True, noIntermediate=True,
                                        fullPath=True, type="nurbsCurve") or []
            if shapes:
                shape_matrix = cmds.createNode("composeMatrix", name=short + "_SHAPE_SCALE_CM")
                cmds.connectAttr(combined_scale, shape_matrix + ".inputScale")
                for index, shape in enumerate(shapes, 1):
                    source = cmds.listConnections(shape + ".create", source=True,
                                                  destination=False, plugs=True) or []
                    geometry = cmds.createNode("transformGeometry",
                                               name=short + "_SHAPE_SCALE_%02d_TG" % index)
                    cmds.setAttr(geometry + ".invertTransform", 1)
                    cmds.connectAttr(shape_matrix + ".outputMatrix", geometry + ".transform")
                    if source:
                        cmds.connectAttr(source[0], geometry + ".inputGeometry")
                    else:
                        shape_selection = om.MSelectionList()
                        shape_selection.add(shape)
                        control_selection = om.MSelectionList()
                        control_selection.add(control_now)
                        original = om.MFnNurbsCurve().copy(
                            shape_selection.getDependNode(0), control_selection.getDependNode(0))
                        input_shape = cmds.rename(om.MFnDagNode(original).fullPathName(),
                                                  short + "_ShapeInput_%02dShape" % index)
                        cmds.setAttr(input_shape + ".intermediateObject", 1)
                        cmds.connectAttr(input_shape + ".local", geometry + ".inputGeometry")
                    cmds.connectAttr(geometry + ".outputGeometry", shape + ".create", force=True)
            results.append({"parent": driver, "child": control_now, "follow": follow,
                            "matrix": mm, "modeApplied": mode, "base": base,
                            "bindError": deviation, "shapeScale": combined_scale})
        failed = False
    finally:
        cmds.undoInfo(closeChunk=True)
        if failed and changed:
            cmds.undo()
    return results


def RunSelected(*args):
    """Select Parent FK first and Child FK second, then build immediately."""
    parent, child = _selected_pair()
    if not parent or not child:
        raise ValueError("FollowMatrix: select Parent FK then Child FK")
    return BuildFollowMatrix([{"parent": parent, "child": child}])


def Run(data, *args):
    datas = NLTA_General.readJsonFile(_data_path(data)) or []
    return BuildFollowMatrix(datas)


def _export_follow_matrix_source():
    lines = inspect.getsource(BuildFollowMatrix).rstrip().splitlines()
    source = "\n".join(line.rstrip() for line in lines
                       if not line.lstrip().startswith("#")
                       or line.lstrip().startswith("# Stage:"))
    return source


def ExportPython(data, *args):
    datas = NLTA_General.readJsonFile(_data_path(data))
    name = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    content = ("def main():\n"
               "    import maya.cmds as cmds\n\n"
               "    # Stage: Configure the parent-space FK matrix correction.\n"
               "    FOLLOW_MATRIX_DATA = " + repr(datas) + "\n\n"
               + textwrap.indent(_export_follow_matrix_source(), "    ") + "\n\n"
               "    BuildFollowMatrix(FOLLOW_MATRIX_DATA)\n\n"
               'if __name__ == "__main__":\n    main()\n')
    compile(content, name, "exec")
    destination = os.path.join(os.path.dirname(_data_path(data)), name)
    with open(destination, "w", encoding="utf-8") as stream:
        stream.write(content)
    return destination


def OpenExportFolder(data, *args):
    folder = os.path.dirname(_data_path(data))
    if os.path.isdir(folder):
        os.startfile(folder)
    else:
        cmds.warning("FollowMatrix: folder does not exist: " + folder)