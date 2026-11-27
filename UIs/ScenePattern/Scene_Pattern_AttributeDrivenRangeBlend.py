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


def normalizeItem(item):
    result = {key: item.get(key, "") for key in ("driverObject", "driverAttr", "driverMin", "driverMax", "driverDefault")}
    result["drivens"] = [{"constraint": sub.get("constraint", "")} for sub in item.get("drivens", [{"constraint": item.get("constraint", "")}])]
    return result


def _read_saved(data):
    path = _data_path(data)
    saved = (NLTA_General.readJsonFile(path) or []) if os.path.isfile(path) else []
    return [normalizeItem(item) for item in saved]


def pickConstraint(field, *unused):
    types = ("parentConstraint", "pointConstraint", "orientConstraint")
    objects = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    selected = [node for node in objects if cmds.nodeType(node) in types]
    if not selected and len(objects) == 1:
        selected = [node for node in (cmds.listRelatives(objects[0], children=True, fullPath=True) or [])
                    if cmds.nodeType(node) in types]
    if len(selected) != 1:
        cmds.warning("Driven Range Blend: select one Parent, Point or Orient Constraint.")
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
    fields = ("driverObject", "driverAttr", "driverMin", "driverMax", "driverDefault")
    item = {key: cmds.textField(row[key], query=True, text=True) for key in fields}
    item["drivens"] = [{key: cmds.textField(sub[key], query=True, text=True)
                         for key in ("constraint",)} for sub in row["drivens"]]
    return item


def _duplicate(row, *unused):
    return Add(STATE["list"], _snapshot(row))


def removeDriven(row, sub, *unused):
    row["drivens"].remove(sub)
    cmds.deleteUI(sub["layout"])


def AddDriven(row, item=None, *unused):
    item = item or {}
    layout = cmds.columnLayout(parent=row["drivenList"], adjustableColumn=True, rowSpacing=2)
    sub = {"layout": layout}
    sub["constraint"] = _picker_field(layout, "Constraint", item.get("constraint", ""), pickConstraint)
    cmds.button(parent=layout, label="Remove Driven", height=19, command=partial(removeDriven, row, sub))
    row["drivens"].append(sub)
    return sub


def Add(listUI, item=None, *unused):
    item = normalizeItem(item or {})
    frame = cmds.frameLayout(parent=listUI, label="Driver / Constraint Blend", collapsable=True, collapse=False, marginWidth=4, marginHeight=3)
    column = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=2)
    pair = cmds.rowLayout(parent=column, numberOfColumns=2, columnWidth2=(180, 180))
    driver = cmds.columnLayout(parent=pair, adjustableColumn=True, rowSpacing=2)
    row = {"frame": frame, "drivens": []}
    row["driverObject"] = _picker_field(driver, "Driver Object", item.get("driverObject", ""), _pick_object)
    row["driverAttr"] = _picker_field(driver, "Driver Attribute", item.get("driverAttr", ""), _pick_attribute, row["driverObject"])
    row["driverMin"], row["driverMax"] = _range_fields(driver, "Driver", item.get("driverMin"), item.get("driverMax"))
    row["driverDefault"] = _default_field(driver, "Driver", item.get("driverDefault"))

    driven = cmds.columnLayout(parent=pair, adjustableColumn=True, rowSpacing=2)
    cmds.text(parent=driven, label="Auto Rest | Weight 0 - 1", align="left")
    row["drivenList"] = cmds.columnLayout(parent=driven, adjustableColumn=True, rowSpacing=3)
    for sub in item["drivens"] or [{}]:
        AddDriven(row, sub)
    cmds.button(parent=driven, label="+ Add Driven", height=22, command=lambda *_: AddDriven(row))

    actions = cmds.rowLayout(parent=column, numberOfColumns=2, columnWidth2=(180, 180))
    cmds.button(parent=actions, label="Duplicate", height=22, command=partial(_duplicate, row))
    cmds.button(parent=actions, label="Remove Item", height=22, command=partial(_remove, row))
    STATE["rows"].append(row)
    return row


def _collect():
    items = []
    for row in STATE["rows"]:
        item = _snapshot(row)
        for key in ("driverObject", "driverAttr"):
            item[key] = item[key].strip()
        item["drivens"] = [{key: value.strip() for key, value in sub.items()} for sub in item["drivens"]]
        if not item["driverObject"] or not item["driverAttr"] or not item["drivens"] or any(not all(sub.values()) for sub in item["drivens"]):
            raise ValueError("Driven Range Blend: complete the driver and select at least one constraint.")
        for key, default in (("driverMin", 0), ("driverMax", 1)):
            item[key] = float(item[key].strip() or default)
        item["driverDefault"] = float(item["driverDefault"].strip() or item["driverMin"])
        if not all(math.isfinite(item[key]) for key in ("driverMin", "driverMax", "driverDefault")):
            raise ValueError("Driven Range Blend: enter finite numbers.")
        if not item["driverMin"] < item["driverMax"] or not item["driverMin"] <= item["driverDefault"] <= item["driverMax"]:
            raise ValueError("Driven Range Blend: invalid Driver Min/Max/Default.")
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


def createBlend(driverObject, driverAttr, driverMin, driverMax, driverDefault, drivens):
    driver = driverObject + "." + driverAttr
    if not cmds.objExists(driver):
        cmds.addAttr(driverObject, longName=driverAttr, attributeType="double", keyable=True, minValue=driverMin, maxValue=driverMax, defaultValue=driverDefault)

    # Capture all rest poses before changing any constraint weights.
    rests = []
    for constraint in drivens:
        kind = cmds.nodeType(constraint)
        command = getattr(cmds, kind)
        driven = cmds.listConnections(constraint + ".constraintParentInverseMatrix", source=True, destination=False)[0]
        original = command(constraint, query=True, weightAliasList=True)[0]
        originalTarget = command(constraint, query=True, targetList=True)[0]
        matrix = cmds.xform(driven, query=True, worldSpace=True, matrix=True)
        parents = cmds.listRelatives(driven, parent=True, fullPath=True) or []
        restName = constraint.rsplit("|", 1)[-1] + "_Rest"
        rest = cmds.createNode("transform", name=restName, parent=parents[0]) if parents else cmds.createNode("transform", name=restName)
        rest = cmds.ls(rest, long=True)[0]
        cmds.setAttr(rest + ".rotateOrder", cmds.getAttr(originalTarget + ".rotateOrder"))
        cmds.xform(rest, worldSpace=True, matrix=matrix)
        # Match the original target axes without moving the rest position.
        cmds.matchTransform(rest, originalTarget, rotation=True, position=False, scale=False)
        rests.append((constraint, driven, kind, command, original, rest))

    name = driverObject.rsplit("|", 1)[-1].replace(":", "_") + "_" + driverAttr.replace(".", "_").replace("[", "_").replace("]", "") + "_RangeBlend"
    blend = cmds.createNode("remapValue", name=name)
    cmds.setAttr(blend + ".inputMin", driverMin)
    cmds.setAttr(blend + ".inputMax", driverMax)
    cmds.setAttr(blend + ".outputMin", 0)
    cmds.setAttr(blend + ".outputMax", 1)
    cmds.setAttr(blend + ".value[0].value_Position", 0)
    cmds.setAttr(blend + ".value[0].value_FloatValue", 0)
    cmds.setAttr(blend + ".value[0].value_Interp", 1)
    cmds.setAttr(blend + ".value[1].value_Position", 1)
    cmds.setAttr(blend + ".value[1].value_FloatValue", 1)
    cmds.setAttr(blend + ".value[1].value_Interp", 1)
    cmds.connectAttr(driver, blend + ".inputValue")
    reverse = cmds.createNode("reverse", name=name + "_Reverse")
    cmds.connectAttr(blend + ".outValue", reverse + ".inputX")

    weights = []
    for constraint, driven, kind, command, original, rest in rests:
        # Parent constraints have a separate offset for each target.
        if kind == "parentConstraint":
            command(rest, driven, weight=0, maintainOffset=True)
        else:
            command(rest, driven, weight=0)
        restAlias = next(alias for alias in command(constraint, query=True, weightAliasList=True) if alias != original)
        weights.append((constraint + "." + original, constraint + "." + restAlias))

    for originalPlug, restPlug in weights:
        cmds.connectAttr(blend + ".outValue", originalPlug, force=True)
        cmds.connectAttr(reverse + ".outputX", restPlug)


def blendArguments(item):
    item = normalizeItem(item)
    return (item["driverObject"], item["driverAttr"], float(item["driverMin"]), float(item["driverMax"]),
            float(item["driverMin"] if item.get("driverDefault") in (None, "") else item["driverDefault"]),
            [sub["constraint"] for sub in item["drivens"]])


def validateItem(item, seen=None):
    driverObject, driverAttr, dmin, dmax, default, drivens = blendArguments(item)
    if not cmds.objExists(driverObject) or not driverAttr or not drivens:
        raise ValueError("Driven Range Blend: driver and constraints are required.")
    if not (math.isfinite(dmin) and math.isfinite(dmax) and math.isfinite(default) and dmin < dmax and dmin <= default <= dmax):
        raise ValueError("Driven Range Blend: invalid range.")
    if seen is None:
        seen = set()
    for constraint in drivens:
        matches = cmds.ls(constraint, long=True) or []
        if len(matches) != 1 or cmds.nodeType(matches[0]) not in ("parentConstraint", "pointConstraint", "orientConstraint"):
            raise ValueError("Driven Range Blend: select one Parent, Point or Orient Constraint.")
        constraint = matches[0]
        kind = cmds.nodeType(constraint)
        command = getattr(cmds, kind)
        if constraint in seen:
            raise ValueError("Driven Range Blend: repeated constraint: " + constraint)
        seen.add(constraint)
        driven = cmds.listConnections(constraint + ".constraintParentInverseMatrix", source=True, destination=False) or []
        if len(driven) != 1:
            raise ValueError("Driven Range Blend: cannot resolve the constrained object.")
        driven = cmds.ls(driven[0], long=True)[0]
        constraints = cmds.listConnections(driven + ".parentInverseMatrix[0]", source=False, destination=True, type=kind) or []
        if set(cmds.ls(constraints, long=True) or []) != {constraint}:
            raise ValueError("Driven Range Blend: ambiguous existing constraint of the same type.")
        aliases = command(constraint, query=True, weightAliasList=True) or []
        if len(aliases) != 1:
            raise ValueError("Driven Range Blend: Auto Rest requires exactly one existing target: " + constraint)
        if cmds.getAttr(constraint + "." + aliases[0], lock=True):
            raise ValueError("Driven Range Blend: original weight must be unlocked: " + constraint)
        if constraint in (cmds.ls(driverObject, long=True) or []) and driverAttr in aliases:
            raise ValueError("Driven Range Blend: do not drive a blend from its own constraint weight.")


def BuildAttributeDrivenRangeBlend(items):
    seen = set()
    for item in items:
        validateItem(item, seen)
    for item in items:
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
