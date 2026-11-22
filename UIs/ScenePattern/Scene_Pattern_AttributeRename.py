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
    name = "Rename Attribute"
    return({
        "ext":ext,
        "path":path+moduleName+"."+ext,
        "moduleName":moduleName,
        "order":0,
        "title":name,
        "name":name,
        "id":datetime.now().strftime("%Y%m%d%H%M%S")
    })


def _attribute_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def BuildAttributeRename(datas):
    """Rename saved attributes without overwriting existing Maya attributes."""
    if not datas:
        return
    for item in datas:
        plug = item["attribute"]
        new_name = item["newName"]
        if not cmds.objExists(plug):
            continue
        node, old_name = plug.split(".", 1)
        if cmds.attributeQuery(new_name, node=node, exists=True):
            cmds.warning("{} already has attribute '{}'".format(node, new_name))
            continue
        # Update the long attribute name and its readable display name.
        cmds.renameAttr(plug, new_name)
        cmds.addAttr("{}.{}".format(node, new_name), e=True, nn=new_name)

def Run(data, *args):
    """Run the same attribute builder used by standalone ExportPython."""
    datas = NLTA_General.readJsonFile(_attribute_data_path(data))
    return BuildAttributeRename(datas)


def ExportPython(data, *args):
    """Export standalone Maya Python with the saved attribute settings."""
    data_path = _attribute_data_path(data)
    datas = NLTA_General.readJsonFile(data_path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("AttributeRename Export: no saved attribute items")
        return None

    # Keep each complete saved data record on one line.
    embedded = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    builder_source = inspect.getsource(BuildAttributeRename).rstrip()
    # Only omit the optional UI warning, never the duplicate-name skip.
    diagnostic = '            cmds.warning("{} already has attribute \'{}\'".format(node, new_name))\n'
    if diagnostic not in builder_source:
        raise RuntimeError("Cannot identify optional rename diagnostic")
    builder_source = builder_source.replace(diagnostic, "")
    builder_source = "\n".join("    " + line if line.strip() else "" for line in builder_source.splitlines())
    source = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        ""
        + "\n"
        + "    # AttributeRename data\n"
        + "    ATTRIBUTE_DATA = " + embedded + "\n\n"
        + builder_source
        + "\n\n    # Build the saved attributes.\n"
        + "    BuildAttributeRename(ATTRIBUTE_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in source:
        source = source.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output_path = os.path.join(os.path.dirname(data_path), filename)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(source)
    return output_path


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_attribute_data_path(data)))


def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    def GetAttributeValue(attributeUI,*arr):
        data = NLTA_UI.GetSelectedAttribute()
        if data["main"]:
            fullAttr = data["objs"][0]+"."+data["main"][0]
            value = cmds.getAttr(fullAttr)
            cmds.textField(attributeUI,edit=True,text=fullAttr)

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
    cmds.rowColumnLayout(nc=1)
    itemData['attribute'] = cmds.textField(text=data.get("attribute",""),width=255,height=30)
    itemData['newName'] = cmds.textField(text=data.get("newName",""),height=30)
    cmds.setParent("..")
    cmds.rowColumnLayout(1)
    cmds.button(label="->",w=30,c=partial(GetAttributeValue,itemData['attribute']))
    cmds.button(label="X",w=30,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.setParent("..")    

    cmds.setParent("..") #--

    
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










