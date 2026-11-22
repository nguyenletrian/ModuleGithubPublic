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
    name = "Visibility Toggle"
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

def BuildVisibilityToggle(datas):
    """Drive object or proxy-group visibility from the saved bool control."""
    if not datas:
        return
    for item in datas:
        controller = item["contentAttr"]
        attribute = item["attribute"]
        if not cmds.objExists(controller):
            continue
        if not cmds.attributeQuery(attribute, node=controller, exists=True):
            cmds.addAttr(controller, ln=attribute, at="bool", dv=True, k=True)
        objects = item["objects"].splitlines()
        for obj in objects:
            obj = obj.strip()
            if not obj or not cmds.objExists(obj):
                continue
            targets = []
            if item["meshOnly"]:
                targets.append(obj)
                meshes = cmds.listRelatives(obj, children=True, type="mesh") or []
                targets.extend(meshes)
            else:
                # Wrap the object in a visibility group, preserving its transform.
                group = cmds.group(em=True, name=_unique_name("{}_VisToggleOffsetGrp".format(obj)))
                cmds.delete(cmds.parentConstraint(obj, group))
                parent = cmds.listRelatives(obj, parent=True, type="transform")
                if parent:
                    parent = parent[0]
                    cmds.parent(group, parent)
                    _zero_transform(group)
                if item["ignoreChildren"]:
                    children = cmds.listRelatives(obj, children=True, type="transform") or []
                    if children:
                        replacement = cmds.group(em=True, name=_unique_name("{}_VisToggleReplaceGrp".format(obj)))
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
            # Keep any already connected visibility target unchanged.
            for target in targets:
                plug = "{}.visibility".format(target)
                source = "{}.{}".format(controller, attribute)
                if cmds.isConnected(source, plug):
                    continue
                cmds.connectAttr(source, plug, force=True)

def Run(data, *args):
    """Execute the same Maya builder used in standalone ExportPython."""
    items = NLTA_General.readJsonFile(_pattern_data_path(data))
    return BuildVisibilityToggle(items)


def ExportPython(data, *args):
    """Export the saved pattern as independently executable Maya Python."""
    data_path = _pattern_data_path(data)
    items = NLTA_General.readJsonFile(data_path)
    if not isinstance(items, list) or not items:
        cmds.warning("VisibilityToggle Export: no saved pattern items")
        return None

    # Keep each saved record on exactly one line.
    data_text = "[\n" + ",\n".join("        " + repr(item) for item in items) + "\n    ]"
    functions = (_unique_name, _zero_transform, BuildVisibilityToggle)
    code = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # VisibilityToggle data\n"
        "    PATTERN_DATA = " + data_text + "\n\n"
        + code
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildVisibilityToggle(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in generated:
        generated = generated.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(generated, filename, "exec")
    output = os.path.join(os.path.dirname(data_path), filename)
    with open(output, "w", encoding="utf-8") as file:
        file.write(generated)
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
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject, itemData["objects"]))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd, itemData["objects"]))
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
    cmds.textField(text="Attribute", editable=False)
    itemData["attribute"] = cmds.textField(text=data.get("attribute",""))
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