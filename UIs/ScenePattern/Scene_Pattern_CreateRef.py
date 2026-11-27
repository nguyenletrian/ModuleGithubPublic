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
        ITEMS["items"].clear()
        ITEMS["order"].clear()
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
    name = "Create Ref"
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
    """Read the saved UI pattern path."""
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]
    })
    return os.path.normpath(entry["path"])


def BuildCreateRef(datas):
    """Create matched reference groups for the saved Maya objects."""
    for item in datas:
        objects = item["objects"].split("\n")
        for obj in objects:
            # Match the reference group before parenting it.
            group = cmds.group(empty=True, name=obj + "_Ref")
            cmds.matchTransform(group, obj)
            if item["parent"]:
                cmds.parent(group, item["parent"])

def Run(data, *args):
    """Build the saved pattern using the same function as ExportPython."""
    items = NLTA_General.readJsonFile(_pattern_data_path(data))
    return BuildCreateRef(items)


def ExportPython(data, *args):
    """Export standalone Maya Python without runtime UI dependencies."""
    data_path = _pattern_data_path(data)
    items = NLTA_General.readJsonFile(data_path)
    if not isinstance(items, list) or not items:
        cmds.warning("CreateRef Export: no saved pattern items")
        return None

    # Preserve each saved data dictionary as one readable line.
    data_text = "[\n" + ",\n".join("        " + repr(item) for item in items) + "\n    ]"
    builder_text = inspect.getsource(BuildCreateRef).rstrip()
    builder_text = "\n".join("    " + line if line.strip() else "" for line in builder_text.splitlines())
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # CreateRef data\n"
        "    PATTERN_DATA = " + data_text + "\n\n"
        + builder_text
        + "\n\n    # Apply the saved Maya operations.\n"
        + "    BuildCreateRef(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in generated:
        generated = generated.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(generated, filename, "exec")
    output = os.path.join(os.path.dirname(data_path), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(generated)
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

    cmds.textField(text='Objects',editable=False)
    itemData['objects'] = cmds.scrollField(text=data.get("objects", ""),ww=True,height=200)
    cmds.rowColumnLayout(1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objects']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.AddObject,itemData['objects']))
    cmds.setParent("..")

    cmds.textField(text='Parent',editable=False)
    itemData['parent'] = cmds.textField(text=data.get("parent",""),height=30)    
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['parent']))

    cmds.setParent("..") #--

    cmds.button(label="Delete", w=375, bgc=(0.5, 0.2, 0.2), c=partial(Delete, itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










