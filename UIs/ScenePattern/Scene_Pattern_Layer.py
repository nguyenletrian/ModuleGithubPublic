import os
import importlib
import inspect
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
from datetime import datetime

import NLTA_General,NLTA_UI,NLTA_Control
for module in [NLTA_General,NLTA_UI,NLTA_Control]:
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
    name = "Layer"
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

def _pattern_data_path(data):
    """Read the stored pattern file for the UI and exporter."""
    record = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(record["path"])


def BuildLayer(datas):
    """Create saved display layers and assign matching scene objects."""
    if not datas:
        return
    display_map = {"Normal": 0, "Template": 1, "Reference": 2}
    for item in datas:
        layer_name = item["layerName"]
        visibility = item["visibility"]
        display = item["display"]
        contain_type = item.get("containType", "Empty")
        children_text = item.get("children", "") or ""
        # Prefer explicitly saved members; use the selected scene type if empty.
        children = [name.strip() for name in children_text.splitlines() if name.strip() and cmds.objExists(name.strip())]
        if not children:
            if contain_type == "Joints":
                children = cmds.ls(type="joint", long=True) or []
            elif contain_type == "Meshes":
                shapes = cmds.ls(type="mesh", long=True) or []
                children = cmds.listRelatives(shapes, parent=True, fullPath=True) or []
            elif contain_type == "Controls":
                shapes = cmds.ls(type="nurbsCurve", long=True) or []
                children = cmds.listRelatives(shapes, parent=True, fullPath=True) or []
        children = list(dict.fromkeys(children))
        if cmds.objExists(layer_name):
            cmds.delete(layer_name)
        # Set display properties before adding unique members.
        cmds.createDisplayLayer(name=layer_name, empty=True)
        cmds.setAttr(layer_name + ".visibility", visibility)
        cmds.setAttr(layer_name + ".displayType", display_map.get(display, 0))
        if children:
            try:
                cmds.editDisplayLayerMembers(layer_name, children, noRecurse=True)
            except Exception:
                pass

def Run(data, *args):
    """Run the same Maya builder embedded in the exported script."""
    datas = NLTA_General.readJsonFile(_pattern_data_path(data))
    return BuildLayer(datas)


def ExportPython(data, *args):
    """Generate a standalone Python file from the current builder."""
    data_path = _pattern_data_path(data)
    datas = NLTA_General.readJsonFile(data_path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("Layer Export: no saved items")
        return None

    # One complete dictionary per line, preserving the original values.
    entries = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    builder = inspect.getsource(BuildLayer).rstrip()
    builder = "\n".join("    " + line if line.strip() else "" for line in builder.splitlines())
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # Layer data\n"
        "    PATTERN_DATA = " + entries + "\n\n"
        + builder
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildLayer(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in generated:
        generated = generated.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(generated, filename, "exec")
    output_path = os.path.join(os.path.dirname(data_path), filename)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(generated)
    return output_path


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_pattern_data_path(data)))


def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    def PickChild(ui,*arr):
        NLTA_UI.PickObject(ui)
        offsetGroup = cmds.textField(itemData["Child"],query=True,text=True)+"_Offset"
        cmds.textField(itemData["OffsetName"],edit=True,text=offsetGroup)

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))
    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--

    cmds.textField(text='Layer Name',editable=False)
    itemData['layerName'] = cmds.textField(text=data.get("layerName", ""))
    cmds.text(label="")

    cmds.textField(text='Children',editable=False)
    itemData['children'] = cmds.scrollField(wordWrap=True,height=100,text=data.get("children", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['children']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['children']))
    cmds.setParent("..")

    cmds.textField(text='Display Type',editable=False)
    itemData["display"] = cmds.optionMenu()
    cmds.menuItem(label="Normal")
    cmds.menuItem(label="Template")
    cmds.menuItem(label="Reference")
    cmds.optionMenu(itemData["display"], e=True, value=data.get("display", "Normal"))
    cmds.text(label="")

    cmds.textField(text='Visibility',editable=False)
    itemData['visibility'] = cmds.checkBox(label="",value=data.get("visibility",True))
    cmds.text(label="")

    cmds.textField(text='Contain Type',editable=False)
    itemData["containType"] = cmds.optionMenu()
    cmds.menuItem(label="Empty")
    cmds.menuItem(label="Joints")
    cmds.menuItem(label="Meshes")
    cmds.menuItem(label="Controls")
    cmds.optionMenu(itemData["containType"], e=True, value=data.get("containType", "Empty"))
    cmds.text(label="")




    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










