import os
import importlib
import inspect
import maya.mel as mel
import maya.cmds as cmds
import maya.mel as mel
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
    name = "Unlock Attribute"
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

def _attribute_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def BuildAttributeUnlock(datas):
    """Unlock the saved object's transform channels and remove their input links."""
    for item in datas:
        objects = item["objects"].split("\n")
        for obj in objects:
            if not cmds.objExists(obj):
                continue
            # Load the channel box commands when available.
            try:
                mel.eval('source "channelBoxCommand.mel";')
            except Exception:
                pass
            for attribute in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
                plug = "{}.{}".format(obj, attribute)
                if cmds.objExists(plug):
                    # Unlock and disconnect the transform channel.
                    cmds.setAttr(plug, lock=False, keyable=True)
                    mel.eval('CBunlockAttr "{0}";CBdeleteConnection "{0}";'.format(plug))
                    sources = cmds.listConnections(plug, s=True, d=False, p=True) or []
                    for source in sources:
                        cmds.disconnectAttr(source, plug)

def Run(data, *args):
    """Run the same attribute builder used by standalone ExportPython."""
    datas = NLTA_General.readJsonFile(_attribute_data_path(data))
    return BuildAttributeUnlock(datas)


def ExportPython(data, *args):
    """Export standalone Maya Python with the saved attribute settings."""
    data_path = _attribute_data_path(data)
    datas = NLTA_General.readJsonFile(data_path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("AttributeUnlock Export: no saved attribute items")
        return None

    # Keep each complete saved data record on one line.
    embedded = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    builder_source = inspect.getsource(BuildAttributeUnlock).rstrip()
    builder_source = "\n".join("    " + line if line.strip() else "" for line in builder_source.splitlines())
    source = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.mel as mel\n"
        + "\n"
        + "    # AttributeUnlock data\n"
        + "    ATTRIBUTE_DATA = " + embedded + "\n\n"
        + builder_source
        + "\n\n    # Build the saved attributes.\n"
        + "    BuildAttributeUnlock(ATTRIBUTE_DATA)\n\n"
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

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI)

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--

    cmds.textField(text='Objects',editable=False)
    itemData['objects'] = cmds.scrollField(text=data.get("objects", ""),ww=True,height=200)
    cmds.rowColumnLayout(1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objects']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.AddObject,itemData['objects']))
    cmds.setParent("..")
    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










