# -*- coding: utf-8 -*-
"""Scene Pattern: Distance Follow (static weights, Translate + Rotate).

Each item: multiple parents, one child. Weights calculated once from the initial
world-space distances. AutoFollow (0..1) blends between the original rest
hierarchy and the weighted parentConstraint; no continuously evaluated distances.
"""

import importlib
import inspect
import os
import pprint
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General
import NLTA_UI

for module in (NLTA_General, NLTA_UI):
    importlib.reload(module)

ITEMS = {"items": {}, "order": []}


def DefaultSetting(path, *args):
    module_name = os.path.splitext(os.path.basename(__file__))[0]
    return {
        "ext": "json",
        "path": os.path.join(path, module_name + ".json"),
        "moduleName": module_name,
        "order": 0,
        "title": "Distance Follow",
        "name": "Distance Follow",
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
    }


def _data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    if not entry or not entry.get("path"):
        raise RuntimeError("Distance Follow: cannot find data path")
    return os.path.normpath(entry["path"])


def Load(data, listUI, *args):
    for ui in cmds.layout(listUI, query=True, childArray=True) or []:
        if cmds.control(ui, exists=True):
            cmds.deleteUI(ui)

    ITEMS["items"].clear()
    ITEMS["order"][:] = []
    path = _data_path(data)
    items = NLTA_General.readJsonFile(path) if os.path.isfile(path) else []
    for item in items or []:
        Add(listUI, item)


def Form(data, *args):
    def Save(*unused):
        items = NLTA_UI.GetData(ITEMS["items"])
        NLTA_General.writeJsonFile(_data_path(data), items)
        return items

    def SaveAndExport(*unused):
        Save()
        ExportPython(data)

    form = NLTA_General.LoadModule("Scene_Form").Create(data)
    button_ui, list_ui = form["buttonUI"], form["listUI"]

    cmds.rowColumnLayout(numberOfColumns=4, parent=button_ui)
    cmds.button(label="Add", width=90, command=partial(Add, list_ui, {}))
    cmds.button(label="Save", width=90, command=Save)
    cmds.button(label="Run", width=90, command=partial(Run, data))
    export_button = cmds.button(label="Export Py", width=110, command=SaveAndExport)
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", command=partial(OpenExportFolder, data))
    cmds.setParent("..", menu=True)
    cmds.setParent("..")
    Load(data, list_ui)


def Add(listUI, data, *args):
    def Delete(ui, *unused):
        cmds.deleteUI(ui)
        ITEMS["items"].pop(ui, None)
        if ui in ITEMS["order"]:
            ITEMS["order"].remove(ui)

    item_data = {}
    item_ui = cmds.rowColumnLayout(
        numberOfColumns=1, parent=listUI, backgroundColor=(0.15, 0.15, 0.15)
    )
    cmds.rowColumnLayout(
        numberOfColumns=3,
        columnWidth=[(1, 80), (2, 265), (3, 32)],
    )
    cmds.text(label="Parents")
    item_data["parents"] = cmds.scrollField(
        wordWrap=True, height=85, text=data.get("parents", "")
    )
    cmds.columnLayout()
    cmds.button(
        label="->", width=30,
        command=partial(NLTA_UI.PickObject, item_data["parents"]),
    )
    cmds.button(
        label="+", width=30,
        command=partial(NLTA_UI.PickObjectAdd, item_data["parents"]),
    )
    cmds.setParent("..")

    cmds.text(label="Child")
    item_data["child"] = cmds.textField(text=data.get("child", ""))
    cmds.button(
        label="->", width=30,
        command=partial(NLTA_UI.PickObject, item_data["child"]),
    )
    cmds.text(label="Power")
    item_data["power"] = cmds.textField(text=str(data.get("power", "2")))
    cmds.text(label="")
    cmds.text(label="Min Dist")
    item_data["minDistance"] = cmds.textField(
        text=str(data.get("minDistance", "0.001"))
    )
    cmds.text(label="")
    cmds.setParent("..")

    cmds.button(
        label="X", width=380, backgroundColor=(0.5, 0.2, 0.2),
        command=partial(Delete, item_ui),
    )
    cmds.separator(height=10, style="none")
    cmds.setParent("..")

    ITEMS["items"][item_ui] = item_data
    ITEMS["order"].append(item_ui)


def BuildDistanceFollow(datas):
    """Build a weighted parentConstraint and a rest blend for each child."""
    import math
    import maya.cmds as cmds

    def position(node):
        return cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)

    results = []
    for item in datas:
        # Resolve parent controls and the driven child.
        raw_parents = item["parents"]
        names = ([str(p).strip() for p in raw_parents] if isinstance(raw_parents, (list, tuple))
                 else [p.strip() for p in str(raw_parents).splitlines() if p.strip()])
        parents = [cmds.ls(name, long=True)[0] for name in names]
        child = cmds.ls(str(item["child"]).strip(), long=True)[0]
        power = float(item.get("power", 2.0))
        minimum = float(item.get("minDistance", 0.001))

        # Calculate initial distances and normalized follow weights.
        child_pos = position(child)
        distances = [math.sqrt(sum((a - b) ** 2 for a, b in zip(position(p), child_pos)))
                     for p in parents]
        touching = [i for i, d in enumerate(distances) if d <= 1e-8]
        if touching:
            weights = [1.0 / len(touching) if i in touching else 0.0
                       for i in range(len(parents))]
        else:
            effective = [max(d, minimum) for d in distances]
            scale = min(effective)
            raw = [(scale / d) ** power for d in effective]
            weights = [w / sum(raw) for w in raw]

        # Insert independent rest and constrained follow groups.
        short = child.rsplit("|", 1)[-1].replace(":", "_")
        prefix = short + "_DistanceFollow"
        original = cmds.listRelatives(child, parent=True, fullPath=True) or []
        old_parent = original[0] if original else None
        matrix = cmds.xform(child, query=True, worldSpace=True, matrix=True)
        if old_parent:
            rest = cmds.createNode("transform", name=prefix + "Rest", parent=old_parent)
            group = cmds.createNode("transform", name=prefix + "Grp", parent=old_parent)
        else:
            rest = cmds.createNode("transform", name=prefix + "Rest")
            group = cmds.createNode("transform", name=prefix + "Grp")
        cmds.xform(rest, worldSpace=True, matrix=matrix)
        cmds.xform(group, worldSpace=True, matrix=matrix)

        child = cmds.parent(child, group, absolute=True)[0]
        child = (cmds.ls(child, long=True) or [child])[0]
        if not cmds.attributeQuery("AutoFollow", node=child, exists=True):
            cmds.addAttr(child, longName="AutoFollow", attributeType="double",
                         min=0, max=1, defaultValue=1, keyable=True)
        plug = child + ".AutoFollow"
        # Parent weights blend with AutoFollow; rest uses its inverse.
        constraint = cmds.parentConstraint(
            *(parents + [rest, group]), maintainOffset=True,
            name=prefix + "_Constraint")[0]
        aliases = cmds.parentConstraint(constraint, query=True, weightAliasList=True)
        for i, (alias, weight) in enumerate(zip(aliases[:-1], weights)):
            mult = cmds.createNode(
                "multiplyDivide", name="{}_{:02d}_AutoFollowMult".format(prefix, i))
            cmds.setAttr(mult + ".input2X", weight)
            cmds.connectAttr(plug, mult + ".input1X")
            cmds.connectAttr(mult + ".outputX", constraint + "." + alias)

        reverse = cmds.createNode("reverse", name=prefix + "_RestReverse")
        cmds.connectAttr(plug, reverse + ".inputX")
        cmds.connectAttr(reverse + ".outputX", constraint + "." + aliases[-1])
        results.append({"child": child, "group": group, "rest": rest,
                        "constraint": constraint, "autoFollow": plug,
                        "parents": parents, "distances": distances, "weights": weights})

    return results


def Run(data, *args):
    datas = NLTA_General.readJsonFile(_data_path(data)) or []
    return BuildDistanceFollow(datas)


def ExportPython(data, *args):
    path = _data_path(data)
    datas = NLTA_General.readJsonFile(path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("Distance Follow: no items to export")
        return None

    # Export the exact builder used by Run, without UI dependencies.
    builder = inspect.getsource(BuildDistanceFollow).rstrip()
    builder = "\n".join("    " + line if line.strip() else ""
                        for line in builder.splitlines())
    saved = pprint.pformat(datas, width=110, sort_dicts=False).replace("\n", "\n    ")
    source = (
        "def main():\n"
        "    # FollowDistance data\n"
        "    DISTANCE_FOLLOW_DATA = " + saved + "\n\n"
        + builder
        + "\n\n    # Build the distance-weighted follow groups.\n"
        + "    BuildDistanceFollow(DISTANCE_FOLLOW_DATA)\n\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    export_name = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, export_name, "exec")
    output = os.path.join(os.path.dirname(path), export_name)
    with open(output, "w", encoding="utf-8") as file:
        file.write(source)
    return output


def OpenExportFolder(data, *args):
    folder = os.path.dirname(_data_path(data))
    if os.path.isdir(folder):
        os.startfile(folder)
    else:
        cmds.warning("Folder not found: " + folder)