import os
import inspect
import math
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General
import NLTA_UI


STATE = {"rows": [], "list": None}


def DefaultSetting(path, *unused):
    name = os.path.splitext(os.path.basename(__file__))[0]
    return {"ext": "json", "path": os.path.join(path, name + ".json"),
            "moduleName": name, "order": 0, "title": "Attribute Driven Range Blend",
            "name": "Attribute Driven Range Blend", "id": datetime.now().strftime("%Y%m%d%H%M%S")}


def _data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]})
    return os.path.normpath(entry["path"])


def _read_saved(data):
    path = _data_path(data)
    return (NLTA_General.readJsonFile(path) or []) if os.path.isfile(path) else []


def pickConstraint(field, *unused):
    selected = cmds.ls(selection=True, long=True, type="parentConstraint") or []
    if not selected:
        objects = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        if len(objects) == 1:
            selected = cmds.listRelatives(objects[0], children=True, type="parentConstraint", fullPath=True) or []
    if len(selected) != 1:
        cmds.warning("Driven Range Blend: select one parentConstraint.")
        return
    cmds.textField(field, edit=True, text=selected[0])


def _pick_object(field, *unused):
    selected = cmds.ls(selection=True, objectsOnly=True) or []
    if not selected:
        cmds.warning("Driven Range Blend: select an object")
        return
    cmds.textField(field, edit=True, text=selected[0])


def _pick_attribute(node_field, attr_field, *unused):
    selected = NLTA_UI.GetSelectedAttribute() or {}
    if not selected.get("allAttr"):
        cmds.warning("Driven Range Blend: select an attribute in the Channel Box")
        return

    sections = (("main", "mainObjectList"), ("shape", "shapeObjectList"),
                ("input", "historyObjectList"), ("output", "outputObjectList"))
    for section, object_flag in sections:
        attributes = selected.get(section) or []
        if not attributes:
            continue
        nodes = cmds.channelBox("mainChannelBox", query=True, **{object_flag: True}) or []
        if section == "main":
            nodes = selected["objs"]
        elif section == "input":
            visible = cmds.channelBox("mainChannelBox", query=True, inputs=True) or []
            nodes = list(dict.fromkeys(visible + nodes))
        for attribute in attributes:
            for node in nodes:
                if not cmds.objExists(node + "." + attribute):
                    continue
                aliases = cmds.aliasAttr(node, query=True) or []
                actual = next((aliases[i + 1] for i in range(0, len(aliases) - 1, 2)
                               if aliases[i] == attribute), None)
                if actual is None:
                    actual = cmds.attributeName(node + "." + attribute, long=True, leaf=False)
                cmds.textField(node_field, edit=True, text=node)
                cmds.textField(attr_field, edit=True, text=actual)
                return
    cmds.warning("Driven Range Blend: cannot resolve the selected attribute and its node")


def _picker_field(parent, placeholder, value, picker, node_field=None):
    line = cmds.rowLayout(parent=parent, numberOfColumns=2, columnWidth2=(140, 34))
    field = cmds.textField(parent=line, text=str(value), placeholderText=placeholder,
                           width=138, height=22, annotation=placeholder)
    action = partial(picker, node_field, field) if node_field else partial(picker, field)
    cmds.button(parent=line, label="Pick", width=32, height=22, command=action)
    return field


def _range_fields(parent, side, minimum=None, maximum=None):
    line = cmds.rowLayout(parent=parent, numberOfColumns=2, columnWidth2=(87, 87))
    default_min = 0
    default_max = 1
    first = cmds.textField(parent=line, width=85, height=22,
                           text="" if minimum is None else str(minimum),
                           placeholderText="Min ({})".format(default_min),
                           annotation=side + " Min")
    last = cmds.textField(parent=line, width=85, height=22,
                          text="" if maximum is None else str(maximum),
                          placeholderText="Max ({})".format(default_max),
                          annotation=side + " Max")
    return first, last


def _default_field(parent, side, value=None):
    return cmds.textField(parent=parent, text="" if value is None else str(value), placeholderText="Default (" + side + " Min)", annotation=side + " Default Value", width=174, height=22)


def _remove(row, *unused):
    STATE["rows"].remove(row)
    cmds.deleteUI(row["frame"])


def _snapshot(row):
    fields = ("driverObject", "driverAttr", "driverMin", "driverMax", "driverDefault",
              "constraint", "target", "blendMin", "blendMax")
    item = {key: cmds.textField(row[key], query=True, text=True) for key in fields}
    item["smooth"] = cmds.checkBox(row["smooth"], query=True, value=True)
    item["maintainOffset"] = cmds.checkBox(row["maintainOffset"], query=True, value=True)
    return item


def _duplicate(row, *unused):
    return Add(STATE["list"], _snapshot(row))


def Add(listUI, item=None, *unused):
    item = item or {}
    frame = cmds.frameLayout(parent=listUI, label="Driver / Constraint Blend", collapsable=True, collapse=False, marginWidth=4, marginHeight=3)
    column = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=2)
    pair = cmds.rowLayout(parent=column, numberOfColumns=2, columnWidth2=(180, 180))
    driver = cmds.columnLayout(parent=pair, adjustableColumn=True, rowSpacing=2)
    row = {"frame": frame}
    row["driverObject"] = _picker_field(driver, "Driver Object", item.get("driverObject", ""), _pick_object)
    row["driverAttr"] = _picker_field(driver, "Driver Attribute", item.get("driverAttr", ""), _pick_attribute, row["driverObject"])
    row["driverMin"], row["driverMax"] = _range_fields(driver, "Driver", item.get("driverMin"), item.get("driverMax"))
    row["driverDefault"] = _default_field(driver, "Driver", item.get("driverDefault"))

    driven = cmds.columnLayout(parent=pair, adjustableColumn=True, rowSpacing=2)
    row["constraint"] = _picker_field(driven, "Parent Constraint", item.get("constraint", ""), pickConstraint)
    row["target"] = _picker_field(driven, "New Target Object", item.get("target", ""), _pick_object)
    row["blendMin"], row["blendMax"] = _range_fields(driven, "New Target Weight", item.get("blendMin"), item.get("blendMax"))
    row["smooth"] = cmds.checkBox(parent=driven, label="Smooth", value=bool(item.get("smooth", True)))
    row["maintainOffset"] = cmds.checkBox(parent=driven, label="Maintain Offset", value=bool(item.get("maintainOffset", True)))

    actions = cmds.rowLayout(parent=column, numberOfColumns=2, columnWidth2=(180, 180))
    cmds.button(parent=actions, label="Duplicate", height=22, command=partial(_duplicate, row))
    cmds.button(parent=actions, label="Remove Item", height=22, command=partial(_remove, row))
    STATE["rows"].append(row)
    return row


def _collect():
    items = []
    for row in STATE["rows"]:
        item = _snapshot(row)
        for key in ("driverObject", "driverAttr", "constraint", "target"):
            item[key] = item[key].strip()
        if not all(item[key] for key in ("driverObject", "driverAttr", "constraint", "target")):
            raise ValueError("Driven Range Blend: complete the driver, constraint and new target.")
        for key, default in (("driverMin", 0), ("driverMax", 1), ("blendMin", 0), ("blendMax", 1)):
            item[key] = float(item[key].strip() or default)
        item["driverDefault"] = float(item["driverDefault"].strip() or item["driverMin"])
        if not all(math.isfinite(item[key]) for key in ("driverMin", "driverMax", "driverDefault", "blendMin", "blendMax")):
            raise ValueError("Driven Range Blend: enter finite numbers.")
        if not item["driverMin"] < item["driverMax"] or not item["driverMin"] <= item["driverDefault"] <= item["driverMax"]:
            raise ValueError("Driven Range Blend: invalid Driver Min/Max/Default.")
        if not all(0 <= item[key] <= 1 for key in ("blendMin", "blendMax")):
            raise ValueError("Driven Range Blend: new target weights must be within 0–1.")
        items.append(item)
    return items


def Save(data, *unused):
    items = _collect()
    NLTA_General.writeJsonFile(_data_path(data), items)
    return items


def Load(data, listUI, *unused):
    for child in cmds.layout(listUI, query=True, childArray=True) or []:
        cmds.deleteUI(child)
    STATE["rows"].clear()
    items = _read_saved(data)
    for item in items:
        Add(listUI, item)
    if not items:
        Add(listUI)


def createBlend(driverObject, driverAttr, driverMin, driverMax, driverDefault, constraint, target, blendMin, blendMax, smooth, maintainOffset):
    driver = driverObject + "." + driverAttr
    if not cmds.objExists(driver):
        cmds.addAttr(driverObject, longName=driverAttr, attributeType="double", keyable=True, minValue=driverMin, maxValue=driverMax, defaultValue=driverDefault)

    driven = cmds.listConnections(constraint + ".constraintParentInverseMatrix", source=True, destination=False)[0]
    oldAliases = cmds.parentConstraint(constraint, query=True, weightAliasList=True)
    oldPlugs = [constraint + "." + alias for alias in oldAliases]
    oldInputs = [(cmds.connectionInfo(plug, sourceFromDestination=True), cmds.getAttr(plug)) for plug in oldPlugs]

    # Add a target to the existing constraint, initially with no influence.
    cmds.parentConstraint(target, driven, maintainOffset=maintainOffset, weight=0)
    newAlias = next(alias for alias in cmds.parentConstraint(constraint, query=True, weightAliasList=True) if alias not in oldAliases)
    name = constraint.rsplit("|", 1)[-1].replace(":", "_") + "_RangeBlend"

    blend = cmds.createNode("remapValue", name=name)
    cmds.setAttr(blend + ".inputMin", driverMin)
    cmds.setAttr(blend + ".inputMax", driverMax)
    cmds.setAttr(blend + ".value[0].value_Position", 0)
    cmds.setAttr(blend + ".value[0].value_FloatValue", blendMin)
    cmds.setAttr(blend + ".value[0].value_Interp", 2 if smooth else 1)
    cmds.setAttr(blend + ".value[1].value_Position", 1)
    cmds.setAttr(blend + ".value[1].value_FloatValue", blendMax)
    cmds.setAttr(blend + ".value[1].value_Interp", 2 if smooth else 1)
    cmds.connectAttr(driver, blend + ".inputValue")
    reverse = cmds.createNode("reverse", name=name + "_Reverse")
    cmds.connectAttr(blend + ".outValue", reverse + ".inputX")

    # Keep each original weight live and preserve its relative contribution.
    total = cmds.createNode("plusMinusAverage", name=name + "_OldTotal")
    for index, (plug, (source, value)) in enumerate(zip(oldPlugs, oldInputs)):
        multiply = cmds.createNode("multiplyDivide", name=name + "_Old{:02d}".format(index + 1))
        if source:
            cmds.disconnectAttr(source, plug)
            cmds.connectAttr(source, multiply + ".input1X")
        else:
            cmds.setAttr(multiply + ".input1X", value)
        cmds.connectAttr(multiply + ".input1X", total + ".input1D[{}]".format(index))
        cmds.connectAttr(reverse + ".outputX", multiply + ".input2X")
        cmds.connectAttr(multiply + ".outputX", plug)

    # Scale the new weight by the original total; use one if all old weights are zero.
    safeTotal = cmds.createNode("condition", name=name + "_SafeTotal")
    cmds.setAttr(safeTotal + ".operation", 2)
    cmds.connectAttr(total + ".output1D", safeTotal + ".firstTerm")
    cmds.connectAttr(total + ".output1D", safeTotal + ".colorIfTrueR")
    cmds.setAttr(safeTotal + ".colorIfFalseR", 1)
    newWeight = cmds.createNode("multiplyDivide", name=name + "_New")
    cmds.connectAttr(safeTotal + ".outColorR", newWeight + ".input1X")
    cmds.connectAttr(blend + ".outValue", newWeight + ".input2X")
    cmds.connectAttr(newWeight + ".outputX", constraint + "." + newAlias)


def blendArguments(item):
    return (item["driverObject"], item["driverAttr"], float(item["driverMin"]), float(item["driverMax"]),
            float(item.get("driverDefault", item["driverMin"])), item["constraint"], item["target"],
            float(item.get("blendMin", 0)), float(item.get("blendMax", 1)),
            bool(item.get("smooth", True)), bool(item.get("maintainOffset", True)))


def validateItem(item):
    driverObject, driverAttr, dmin, dmax, default, constraint, target, bmin, bmax, _, _ = blendArguments(item)
    if not cmds.objExists(driverObject) or not cmds.objExists(constraint) or cmds.nodeType(constraint) != "parentConstraint":
        raise ValueError("Driven Range Blend: driver and parentConstraint must exist.")
    target = (cmds.ls(target, long=True, type="transform") or cmds.ls(target, long=True, type="joint") or [None])[0]
    if not target:
        raise ValueError("Driven Range Blend: select a new transform target.")
    driven = cmds.listConnections(constraint + ".constraintParentInverseMatrix", source=True, destination=False) or []
    if len(driven) != 1:
        raise ValueError("Driven Range Blend: cannot resolve the constrained object.")
    driven = cmds.ls(driven[0], long=True)[0]
    constraints = cmds.listConnections(driven + ".parentInverseMatrix[0]", source=False, destination=True, type="parentConstraint") or []
    if set(cmds.ls(constraints, long=True) or []) != set(cmds.ls(constraint, long=True) or []):
        raise ValueError("Driven Range Blend: the driven object must have one parentConstraint.")
    targets = cmds.parentConstraint(constraint, query=True, targetList=True) or []
    if target in (cmds.ls(targets, long=True) or []) or target == driven or target.startswith(driven + "|"):
        raise ValueError("Driven Range Blend: target already exists or creates a dependency cycle.")
    aliases = cmds.parentConstraint(constraint, query=True, weightAliasList=True) or []
    if not aliases or any(cmds.getAttr(constraint + "." + alias, lock=True) for alias in aliases):
        raise ValueError("Driven Range Blend: existing weights must be unlocked.")
    if not (dmin < dmax and dmin <= default <= dmax and 0 <= bmin <= 1 and 0 <= bmax <= 1):
        raise ValueError("Driven Range Blend: invalid range.")
    if driverObject in (constraint, driven) and driverAttr in aliases:
        raise ValueError("Driven Range Blend: do not drive a blend from its own constraint weight.")


def BuildAttributeDrivenRangeBlend(items):
    for item in items:
        validateItem(item)
        createBlend(*blendArguments(item))


def Run(data, *unused):
    return BuildAttributeDrivenRangeBlend(_read_saved(data))


def buildScript(items):
    source = inspect.getsource(createBlend).rstrip()
    source = "\n".join("    " + line if line.strip() else "" for line in source.splitlines())
    calls = ["    createBlend(*" + repr(blendArguments(item)) + ")" for item in items]
    return ("def main():\n    import maya.cmds as cmds\n\n" + source + "\n\n"
            + ("\n".join(calls) or "    pass") + '\n\nif __name__ == "__main__":\n    main()\n')


def ExportPython(data, *unused):
    script = buildScript(_read_saved(data))
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(_data_path(data)), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(script)
    return output


def OpenExportFolder(data, *unused):
    folder = os.path.dirname(_data_path(data))
    if hasattr(os, "startfile"):
        os.startfile(folder)
    else:
        cmds.warning("Driven Range export folder: " + folder)


def Form(data, *unused):
    layout = NLTA_General.LoadModule("Scene_Form").Create(data)
    cmds.scrollLayout("SceneFormMain", edit=True, height=550)
    buttons = cmds.rowLayout(parent=layout["buttonUI"], numberOfColumns=4,
                             columnWidth4=(82, 82, 82, 104))
    listUI = cmds.columnLayout(parent=layout["listUI"], adjustableColumn=True)
    STATE["list"] = listUI
    cmds.button(parent=buttons, label="Add", command=lambda *_: Add(listUI))
    cmds.button(parent=buttons, label="Save", command=partial(Save, data))
    cmds.button(parent=buttons, label="Run", command=lambda *_: (Save(data), Run(data)))
    export_button = cmds.button(parent=buttons, label="Export Py",
                                command=lambda *_: (Save(data), ExportPython(data)))
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", command=partial(OpenExportFolder, data))
    Load(data, listUI)
    return layout
