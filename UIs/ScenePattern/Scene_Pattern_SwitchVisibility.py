import os
import importlib
import inspect
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
from datetime import datetime

import NLTA_General,NLTA_UI
for module in [NLTA_General,NLTA_UI]:
    try:
        importlib.reload(module)
    except:
        from importlib import reload
        reload(module)

ITEMS = {
    "items":{},
    "order":[]
}

def DefaultSetting(path,*arr):
    moduleName = os.path.basename(__file__).replace(".py","")
    ext = "json"
    name = "Visibility Switch"
    return({
        "ext":ext,
        "path":path+moduleName+"."+ext,
        "moduleName":moduleName,
        "order":0,
        "title":name,
        "name":name,
        "id":datetime.now().strftime("%Y%m%d%H%M%S")
    })


def Load(data,listUI,*arr):
    newestData = NLTA_General.JsonGetByID({
        "path":data["sceneDataPath"]+"/ScenePatternData.json",
        "id":data["id"]
    })
    path = newestData["path"]
    if ".json" in path:
        children = cmds.layout(listUI,q=True, ca=True) or []
        for child in children:
            if cmds.control(child, exists=True):
                cmds.deleteUI(child)        
        itemDatas = NLTA_General.readJsonFile(path)
        if itemDatas:
            for i in range(len(itemDatas)):
                Add(listUI,itemDatas[i])

def Form(data,*arr):
    def Save(data,*arr):
        itemData = NLTA_General.JsonGetByID({
            "path":data["sceneDataPath"]+"/ScenePatternData.json",
            "id":data["id"]
        })
        saveData = NLTA_UI.GetData(ITEMS["items"])
        NLTA_General.writeJsonFile(itemData["path"],saveData)
    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]
    def SaveAndExport(*args):
        Save(data)
        ExportPython(data)

    cmds.rowColumnLayout(numberOfColumns=4,parent=buttonUI)
    cmds.button(label="Add",width=100,c=partial(Add,listUI,{}))
    cmds.button(label="Save",width=100,c=partial(Save,data))
    cmds.button(label="Run",width=100,c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=110,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.setParent("..")
    Load(data,listUI)

def _pattern_data_path(data):
    """Resolve the saved UI pattern data."""
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def _unique_name(name):
    """Follow the original Maya name collision suffix rule."""
    if not cmds.objExists(name):
        return name
    index = 1
    while True:
        candidate = name + "_" + str(index)
        if not cmds.objExists(candidate):
            return candidate
        index += 1


def _zero_transform(obj):
    """Zero translation and rotation, and restore unit scale."""
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        cmds.setAttr(obj + "." + attr, 0)
    for attr in ("sx", "sy", "sz"):
        cmds.setAttr(obj + "." + attr, 1)


def BuildSwitchVisibility(datas):
    """Connect enum switch choices to condition-driven visibility."""
    if not datas:
        return
    for item in datas:
        controller = item["contentAttr"]
        attr_name = item["attrPick"]
        if not cmds.attributeQuery(attr_name, node=controller, exists=True):
            cmds.addAttr(controller, ln=attr_name, at="enum", en=item["options"])
            cmds.setAttr(controller + "." + attr_name, e=True, keyable=True)
        object_rows = item["objects"].splitlines()
        options = [option.strip() for option in item["options"].split(":") if option.strip()]
        for index, option in enumerate(options):
            if index >= len(object_rows) or not object_rows[index]:
                continue
            # Use one condition for each enum choice.
            condition = cmds.shadingNode("condition", asUtility=True)
            cmds.connectAttr(controller + "." + attr_name, condition + ".firstTerm", force=True)
            cmds.setAttr(condition + ".secondTerm", index)
            cmds.setAttr(condition + ".colorIfTrueR", 1)
            cmds.setAttr(condition + ".colorIfFalseR", 0)
            objects = [obj.strip() for obj in object_rows[index].split(";") if obj.strip()]
            for obj in objects:
                targets = []
                if item["meshOnly"]:
                    targets.append(obj)
                    shapes = cmds.listRelatives(obj, children=True, type="mesh") or []
                    targets.extend(shapes)
                else:
                    # Preserve transforms and children when creating an offset group.
                    group = cmds.group(em=True, name=_unique_name("{}_VisSwitchOffsetGrp".format(obj)))
                    cmds.delete(cmds.parentConstraint(obj, group))
                    parent = cmds.listRelatives(obj, parent=True)
                    if parent:
                        parent = parent[0]
                        cmds.parent(group, parent)
                        _zero_transform(group)
                    if item["ignoreChildren"]:
                        children = cmds.listRelatives(obj, children=True, type="transform") or []
                        if children:
                            replacement = cmds.group(em=True, name=_unique_name("{}_VisSwitchReplaceGrp".format(obj)))
                            cmds.delete(cmds.parentConstraint(obj, replacement))
                            if parent:
                                cmds.parent(replacement, parent)
                                _zero_transform(replacement)
                            cmds.parent(children, replacement)
                            constraint = cmds.parentConstraint(obj, replacement, mo=True)[0]
                            cmds.setAttr(constraint + ".interpType", 2)
                            cmds.scaleConstraint(obj, replacement, mo=True)
                    cmds.parent(obj, group)
                    targets.append(group)
                # Send the enum condition output to the visible targets.
                for target in targets:
                    cmds.connectAttr(condition + ".outColorR", target + ".visibility", force=True)


def Run(data, *args):
    """Build the saved pattern using the standalone builder."""
    items = NLTA_General.readJsonFile(_pattern_data_path(data))
    return BuildSwitchVisibility(items)


def ExportPython(data, *args):
    """Write one independent Maya Python export with embedded data."""
    data_path = _pattern_data_path(data)
    items = NLTA_General.readJsonFile(data_path)
    if not isinstance(items, list) or not items:
        cmds.warning("SwitchVisibility Export: no saved items")
        return None

    # Embed each saved item as one Python dictionary per line.
    data_text = "[\n" + ",\n".join("        " + repr(item) for item in items) + "\n    ]"
    functions = (_unique_name, _zero_transform, BuildSwitchVisibility)
    source_text = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    # Keep English comments and exact builder calls from the runtime version.
    source_text = "\n".join("    " + line if line.strip() else "" for line in source_text.splitlines())
    result = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # SwitchVisibility data\n"
        "    PATTERN_DATA = " + data_text + "\n\n"
        + source_text
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildSwitchVisibility(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(result, filename, "exec")
    output = os.path.join(os.path.dirname(data_path), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(result)
    return output


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_pattern_data_path(data)))


def Add(listUI, data, *args):
    global ITEMS
    def Delete(ui, *args):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS["items"][ui]
        ITEMS["order"].remove(ui)

    itemData = {}
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)
    # Objects
    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Objects", editable=False)
    itemData["objects"] = cmds.scrollField(text=data.get("objects",""),h=80)
    cmds.rowColumnLayout(numberOfColumns=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObjectSemi, itemData["objects"]))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectSemiAdd, itemData["objects"]))
    cmds.setParent("..")
    cmds.setParent("..")

    # Content Attr
    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Content", editable=False)
    itemData["contentAttr"] = cmds.textField(text=data.get("contentAttr",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject, itemData["contentAttr"]))
    cmds.setParent("..")

    # Attr Pick
    cmds.rowColumnLayout(numberOfColumns=2, columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Attr Pick", editable=False)
    itemData["attrPick"] = cmds.textField(text=data.get("attrPick",""))
    cmds.setParent("..")

    # Options
    cmds.rowColumnLayout(numberOfColumns=2, columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Options", editable=False)
    itemData["options"] = cmds.textField(text=data.get("options",""))
    cmds.setParent("..")

    # Ignore Children
    cmds.rowColumnLayout(numberOfColumns=2, columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Ignore Child", editable=False)
    itemData["ignoreChildren"] = cmds.checkBox(label="",value=data.get("ignoreChildren", True))
    cmds.setParent("..")

    # Mesh Only
    cmds.rowColumnLayout(numberOfColumns=2, columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Mesh Only", editable=False)
    itemData["meshOnly"] = cmds.checkBox(label="",value=data.get("meshOnly", False))
    cmds.setParent("..")

    cmds.button(label="X",w=380,bgc=(0.5,0.2,0.2),c=partial(Delete, itemUI))

    cmds.setParent("..")
    cmds.setParent("..")

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)