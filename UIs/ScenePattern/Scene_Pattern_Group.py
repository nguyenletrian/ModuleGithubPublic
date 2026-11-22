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
    cmds.button(label="Save", width=100,c=partial(Save,data))
    cmds.button(label="Run",width=100, c=partial(Run,data))
    button = cmds.button(label="Export Py", width=110, c=SaveAndExport)
    cmds.popupMenu(parent=button, button=3)
    cmds.menuItem(label="Open Folder", c=partial(OpenExportFolder, data))
    cmds.setParent("..")
    Load(data,listUI)

###########################

def DefaultSetting(path,*arr):
    moduleName = os.path.basename(__file__).replace(".py","")
    ext = "json"
    name = "Emty Group"
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


def BuildGroup(datas):
    """Create empty groups matched to their saved parents."""
    created = []
    for item in datas:
        # Create and align each group before parenting it.
        group = cmds.group(empty=True, name=item["name"])
        cmds.matchTransform(group, item["parent"])
        cmds.parent(group, item["parent"])
        created.append(group)
    return created

def Run(data, *args):
    datas = NLTA_General.readJsonFile(_pattern_data_path(data)) or []
    return BuildGroup(datas)


def ExportPython(data, *args):
    datas = NLTA_General.readJsonFile(_pattern_data_path(data))
    if not isinstance(datas, list) or not datas:
        cmds.warning("Group Export: no saved items")
        return None

    # Embed readable data and the exact builder used by Run.
    embedded = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    builder = inspect.getsource(BuildGroup).rstrip()
    builder = "\n".join("    " + line if line.strip() else "" for line in builder.splitlines())
    source = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # Group data\n"
        "    PATTERN_DATA = " + embedded + "\n\n"
        + builder
        + "\n\n    # Build the saved pattern items.\n"
        + "    BuildGroup(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in source:
        source = source.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(_pattern_data_path(data)), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(source)
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

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI)

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,260),(3,35)]) #--

    cmds.textField(text='Parent',editable=False)
    itemData['parent'] = cmds.textField(text=data.get("parent",""),height=30)    
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['parent']))

    cmds.textField(text='Name',editable=False)
    itemData['name'] = cmds.textField(text=data.get("name",""),height=30)    
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['name']))

    cmds.setParent("..") #--

    
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










