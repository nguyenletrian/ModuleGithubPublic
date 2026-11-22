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
    def Save(data, *arr):
        itemData = NLTA_General.JsonGetByID({
            "path":data["sceneDataPath"]+"/ScenePatternData.json",
            "id":data["id"]
        })
        returnData = NLTA_UI.GetData(ITEMS['items'])
        NLTA_General.writeJsonFile(itemData["path"],returnData)

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

###########################

def DefaultSetting(path,*arr):
    moduleName = os.path.basename(__file__).replace(".py","")
    ext = "json"
    name = "Transfer Attribute"
    return({
        "ext":ext,
        "path":path+moduleName+"."+ext,
        "moduleName":moduleName,
        "order":0,
        "title":name,
        "name":name,
        "id":datetime.now().strftime("%Y%m%d%H%M%S")
    })

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def BuildAttributeTransfer(datas):
    """Copy saved attribute values and connections to the target objects."""
    source_objects_to_delete = []
    for item in datas:
        source_plug = item["attribute"]
        if "." not in source_plug:
            continue
        source, attr = source_plug.split(".", 1)
        target = item["target"]
        new_name = item.get("newName", attr)
        remove_source = item.get("delete", False)
        if not (cmds.objExists(source_plug) and cmds.objExists(target)):
            continue
        target_plug = "{}.{}".format(target, new_name)
        if not cmds.attributeQuery(new_name, node=target, exists=True):
            # Recreate the original numeric or enum attribute type.
            attr_type = cmds.getAttr(source_plug, type=True)
            options = {"ln": new_name, "k": True}
            if attr_type == "enum":
                options["at"] = "enum"
                options["en"] = cmds.attributeQuery(attr, node=source, listEnum=True)[0]
            else:
                options["at"] = attr_type
            cmds.addAttr(target, **options)

        # Transfer the value and reconnect both input and output links.
        cmds.setAttr(target_plug, cmds.getAttr(source_plug))
        for link in cmds.listConnections(source_plug, s=True, d=False, p=True) or []:
            cmds.connectAttr(link, target_plug, force=True)
        for link in cmds.listConnections(source_plug, s=False, d=True, p=True) or []:
            cmds.connectAttr(target_plug, link, force=True)
        if remove_source:
            source_objects_to_delete.append(source)
    # Preserve the original deletion behavior, including an empty list.
    cmds.delete(source_objects_to_delete)

def Run(data, *args):
    """Execute the same Maya builder used in standalone ExportPython."""
    items = NLTA_General.readJsonFile(_pattern_data_path(data))
    return BuildAttributeTransfer(items)


def ExportPython(data, *args):
    """Export the saved pattern as independently executable Maya Python."""
    data_path = _pattern_data_path(data)
    items = NLTA_General.readJsonFile(data_path)
    if not isinstance(items, list) or not items:
        cmds.warning("AttributeTransfer Export: no saved pattern items")
        return None

    # Keep each saved record on exactly one line.
    data_text = "[\n" + ",\n".join("        " + repr(item) for item in items) + "\n    ]"
    functions = (BuildAttributeTransfer,)
    code = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # AttributeTransfer data\n"
        "    PATTERN_DATA = " + data_text + "\n\n"
        + code
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildAttributeTransfer(PATTERN_DATA)\n\n"
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


def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    def PickAttribute(attributeUI,*arr):
        data = NLTA_UI.GetSelectedAttribute()
        if data["main"]:
            fullAttr = data["objs"][0]+"."+data["main"][0]
            cmds.textField(attributeUI,edit=True,text=fullAttr)
        else:
            Print("Please select a attribute")

    def SelectObject(attributeUI,*arr):
        text = cmds.textField(attributeUI,query=True,text=True)
        if text:
            obj = text.split(".")[0]
            cmds.select(obj)

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI)

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,260),(3,35)]) #--

    cmds.textField(text='Attribute',editable=False)
    itemData['attribute'] = cmds.textField(text=data.get('attribute',""),height=30)
    cmds.button(label="->",w=30,c=partial(PickAttribute,itemData['attribute']))

    cmds.textField(text='Target',editable=False)
    itemData['target'] = cmds.textField(text=data.get("target",""),width=255,height=30)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['target']))

    cmds.textField(text='New Name',editable=False)
    itemData['newName'] = cmds.textField(text=data.get("newName",""),width=255,height=30)
    cmds.text(label="")

    cmds.textField(text='Delete',editable=False)
    itemData['delete'] = cmds.checkBox('delete', value=data.get('delete',False))
    cmds.text(label="")


    cmds.setParent("..") #--    
    cmds.button(label="X",w=30,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










