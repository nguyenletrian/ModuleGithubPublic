import os
from datetime import datetime
from functools import partial

import maya.cmds as cmds
import NLTA_General
import NLTA_UI


STATE = {"rows": [], "list": None}


def DefaultSetting(path, *unused):
    name = os.path.splitext(os.path.basename(__file__))[0]
    return {"ext": "json", "path": os.path.join(path, name + ".json"),
            "moduleName": name, "order": 0, "title": "Attribute Driven Range",
            "name": "Attribute Driven Range", "id": datetime.now().strftime("%Y%m%d%H%M%S")}


def _data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]})
    return os.path.normpath(entry["path"])


def _read_saved(data):
    path = _data_path(data)
    saved = NLTA_General.readJsonFile(path) or [] if os.path.isfile(path) else []
    items = []
    for entry in saved:
        item = dict(entry)
        if "drivens" not in item:
            item["drivens"] = [{"object": item.pop("drivenObject", ""), "attr": item.pop("drivenAttr", "")}]
        items.append(item)
    return items


def _pick_object(field, *unused):
    selected = cmds.ls(selection=True, objectsOnly=True) or []
    if not selected:
        cmds.warning("Driven Range: select an object")
        return
    cmds.textField(field, edit=True, text=selected[0])


def _pick_attribute(node_field, attr_field, *unused):
    selected = NLTA_UI.GetSelectedAttribute() or {}
    if not selected.get("allAttr"):
        cmds.warning("Driven Range: select an attribute in the Channel Box")
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
    cmds.warning("Driven Range: cannot resolve the selected attribute and its node")


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


def _remove_driven(row, sub, *unused):
    row["drivens"].remove(sub)
    cmds.deleteUI(sub["layout"])


def _snapshot(row):
    fields = ("driverObject", "driverAttr", "driverMin", "driverMax", "driverDefault", "drivenMin", "drivenMax")
    item = {key: cmds.textField(row[key], query=True, text=True) for key in fields}
    item["drivens"] = [{"object": cmds.textField(sub["object"], query=True, text=True),
                         "attr": cmds.textField(sub["attr"], query=True, text=True)} for sub in row["drivens"]]
    return item


def _duplicate(row, *unused):
    return Add(STATE["list"], _snapshot(row))


def AddDriven(row, item=None, *unused):
    item = item or {}
    layout = cmds.columnLayout(parent=row["drivenList"], adjustableColumn=True, rowSpacing=1)
    sub = {"layout": layout}
    sub["object"] = _picker_field(layout, "Driven Object", item.get("object", ""), _pick_object)
    sub["attr"] = _picker_field(layout, "Driven Attribute", item.get("attr", ""), _pick_attribute, sub["object"])
    cmds.button(parent=layout, label="Remove Driven", height=19, command=partial(_remove_driven, row, sub))
    row["drivens"].append(sub)
    return sub


def Add(listUI, item=None, *unused):
    item = item or {}
    frame = cmds.frameLayout(parent=listUI, label="Driver / Drivens", collapsable=True, collapse=False, marginWidth=4, marginHeight=3)
    column = cmds.columnLayout(parent=frame, adjustableColumn=True, rowSpacing=2)
    pair = cmds.rowLayout(parent=column, numberOfColumns=2, columnWidth2=(180, 180))
    driver = cmds.columnLayout(parent=pair, adjustableColumn=True, rowSpacing=2)
    row = {"frame": frame, "drivens": []}
    row["driverObject"] = _picker_field(driver, "Driver Object", item.get("driverObject", ""), _pick_object)
    row["driverAttr"] = _picker_field(driver, "Driver Attribute", item.get("driverAttr", ""), _pick_attribute, row["driverObject"])
    row["driverMin"], row["driverMax"] = _range_fields(driver, "Driver", item.get("driverMin"), item.get("driverMax"))
    row["driverDefault"] = _default_field(driver, "Driver", item.get("driverDefault"))

    driven = cmds.columnLayout(parent=pair, adjustableColumn=True, rowSpacing=2)
    row["drivenMin"], row["drivenMax"] = _range_fields(driven, "Driven", item.get("drivenMin"), item.get("drivenMax"))
    row["drivenList"] = cmds.columnLayout(parent=driven, adjustableColumn=True, rowSpacing=3)
    for sub in item.get("drivens") or [{"object": "", "attr": ""}]:
        AddDriven(row, sub)
    cmds.button(parent=driven, label="+ Add Driven", height=22, command=partial(AddDriven, row))

    actions = cmds.rowLayout(parent=column, numberOfColumns=2, columnWidth2=(180, 180))
    cmds.button(parent=actions, label="Duplicate", height=22, command=partial(_duplicate, row))
    cmds.button(parent=actions, label="Remove Item", height=22, command=partial(_remove, row))
    STATE["rows"].append(row)
    return row


def _collect():
    items = []
    for row in STATE["rows"]:
        item = {key: cmds.textField(row[key], query=True, text=True).strip() for key in ("driverObject", "driverAttr")}
        defaults = {"driverMin": 0, "driverMax": 1, "drivenMin": 0, "drivenMax": 1}
        item.update({key: float(cmds.textField(row[key], query=True, text=True).strip() or defaults[key]) for key in defaults})
        raw_default = cmds.textField(row["driverDefault"], query=True, text=True).strip()
        item["driverDefault"] = float(raw_default) if raw_default else item["driverMin"]
        item["drivens"] = [{"object": cmds.textField(sub["object"], query=True, text=True).strip(),
                            "attr": cmds.textField(sub["attr"], query=True, text=True).strip()} for sub in row["drivens"]]
        if not item["driverObject"] or not item["driverAttr"] or not item["drivens"] or any(not sub["object"] or not sub["attr"] for sub in item["drivens"]):
            raise ValueError("Driven Range: select a driver and at least one complete driven")
        if item["driverMin"] >= item["driverMax"]:
            raise ValueError("Driven Range: Driver Min must be below Driver Max")
        if not item["driverMin"] <= item["driverDefault"] <= item["driverMax"]:
            raise ValueError("Driven Range: Driver Default must be within Driver Min/Max")
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


def _resolved_object(name):
    if cmds.objExists(name):
        return name
    matches = [node for node in cmds.ls(long=True) or [] if node.lower() == name.lower() or node.rsplit("|", 1)[-1].lower() == name.lower()]
    return matches[0] if len(matches) == 1 else name


def _resolved_plug(obj, attr):
    plug = obj + "." + attr
    if cmds.objExists(plug):
        return plug
    aliases = cmds.aliasAttr(obj, query=True) or []
    names = (cmds.listAttr(obj) or []) + aliases[::2]
    matches = list(dict.fromkeys(name for name in names if name.lower() == attr.lower()))
    return obj + "." + matches[0] if len(matches) == 1 else plug


def BuildAttributeDrivenRange(items):
    for item in items:
        driver_object = _resolved_object(item["driverObject"])
        if not cmds.objExists(driver_object):
            raise ValueError("Driven Range: missing driver object " + driver_object)
        driver = _resolved_plug(driver_object, item["driverAttr"])
        if float(item["driverMin"]) >= float(item["driverMax"]):
            raise ValueError("Driven Range: Driver Min must be below Driver Max")
        if not cmds.objExists(driver):
            cmds.addAttr(driver_object, longName=item["driverAttr"], attributeType="double", keyable=True, minValue=float(item["driverMin"]), maxValue=float(item["driverMax"]), defaultValue=float(item.get("driverDefault", item["driverMin"])))

        for sub in item["drivens"]:
            driven_object = _resolved_object(sub["object"])
            if not cmds.objExists(driven_object):
                raise ValueError("Driven Range: missing driven object " + driven_object)
            driven = _resolved_plug(driven_object, sub["attr"])
            if driver == driven:
                raise ValueError("Driven Range: driver and driven must be different attributes")
            if not cmds.objExists(driven):
                cmds.addAttr(driven_object, longName=sub["attr"], attributeType="double", keyable=True)
            cmds.setDrivenKeyframe(driven, currentDriver=driver, driverValue=float(item["driverMin"]), value=float(item["drivenMin"]))
            cmds.setDrivenKeyframe(driven, currentDriver=driver, driverValue=float(item["driverMax"]), value=float(item["drivenMax"]))
            cmds.keyTangent(driven, edit=True, inTangentType="linear", outTangentType="linear")


def Run(data, *unused):
    return BuildAttributeDrivenRange(_read_saved(data))


def ExportPython(data, *unused):
    items = _read_saved(data)
    create_drivers, create_drivens, sdk_keys = [], [], []
    driver_seen, driven_seen = set(), set()
    for item in items:
        driver_obj = _resolved_object(item["driverObject"])
        driver = _resolved_plug(driver_obj, item["driverAttr"])
        if driver not in driver_seen:
            create_drivers.append((driver_obj, driver[len(driver_obj) + 1:], driver, float(item["driverMin"]), float(item["driverMax"]), float(item.get("driverDefault", item["driverMin"]))))
            driver_seen.add(driver)
        for sub in item["drivens"]:
            driven_obj = _resolved_object(sub["object"])
            driven = _resolved_plug(driven_obj, sub["attr"])
            if driven not in driven_seen and driven not in driver_seen:
                create_drivens.append((driven_obj, driven[len(driven_obj) + 1:], driven))
                driven_seen.add(driven)
            sdk_keys.append((driver, driven, float(item["driverMin"]), float(item["driverMax"]), float(item["drivenMin"]), float(item["drivenMax"])))

    script = ('def main():\n'
              '    import maya.cmds as cmds\n\n'
              '    DRIVER_ATTRS = ' + repr(create_drivers) + '\n'
              '    DRIVEN_ATTRS = ' + repr(create_drivens) + '\n'
              '    SDK_KEYS = ' + repr(sdk_keys) + '\n\n'
              '    for obj, attr, plug, vmin, vmax, default in DRIVER_ATTRS:\n'
              '        if not cmds.objExists(plug):\n'
              '            cmds.addAttr(obj, longName=attr, attributeType="double", keyable=True, minValue=vmin, maxValue=vmax, defaultValue=default)\n'
              '    for obj, attr, plug in DRIVEN_ATTRS:\n'
              '        if not cmds.objExists(plug):\n'
              '            cmds.addAttr(obj, longName=attr, attributeType="double", keyable=True)\n'
              '    for driver, driven, dmin, dmax, vmin, vmax in SDK_KEYS:\n'
              '        cmds.setDrivenKeyframe(driven, currentDriver=driver, driverValue=dmin, value=vmin)\n'
              '        cmds.setDrivenKeyframe(driven, currentDriver=driver, driverValue=dmax, value=vmax)\n'
              '        cmds.keyTangent(driven, edit=True, inTangentType="linear", outTangentType="linear")\n\n'
              'if __name__ == "__main__":\n'
              '    main()\n')
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
