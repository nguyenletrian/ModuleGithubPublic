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
    name = "Visibility"
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
    """Resolve the saved UI pattern data."""
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def BuildVisibility(datas):
    """Hide selected objects, preserving driven or locked visibility."""
    for item in datas:
        objects = item["objects"].split("\n")
        for obj in objects:
            if not cmds.objExists(obj):
                continue
            plug = obj + ".visibility"
            connections = cmds.listConnections(plug, source=True, destination=False)
            locked = cmds.getAttr(plug, lock=True)
            if connections or locked:
                # Use visibility groups when the original channel cannot be set.
                group = cmds.group(empty=True, name="{}_VisOffsetGrp".format(obj))
                cmds.delete(cmds.parentConstraint(obj, group))
                replacement = cmds.group(empty=True, name="{}_VisReplaceGrp".format(obj))
                cmds.delete(cmds.parentConstraint(obj, replacement))
                original_parent = cmds.listRelatives(obj, parent=True)[0]
                if original_parent:
                    cmds.parent(group, original_parent)
                children = cmds.listRelatives(obj, children=True)
                if children:
                    cmds.parent(children, replacement)
                    cmds.parent(replacement, original_parent)
                    constraint = cmds.parentConstraint(obj, replacement, mo=True)[0]
                    cmds.setAttr(constraint + ".interpType", 2)
                    cmds.scaleConstraint(obj, replacement, mo=True)
                else:
                    cmds.delete(replacement)
                cmds.parent(obj, group)
                cmds.setAttr(group + ".visibility", 0)
            else:
                cmds.setAttr(plug, 0)


def Run(data, *args):
    """Build the saved pattern using the standalone builder."""
    items = NLTA_General.readJsonFile(_pattern_data_path(data))
    return BuildVisibility(items)


def ExportPython(data, *args):
    """Write one independent Maya Python export with embedded data."""
    data_path = _pattern_data_path(data)
    items = NLTA_General.readJsonFile(data_path)
    if not isinstance(items, list) or not items:
        cmds.warning("Visibility Export: no saved items")
        return None

    # Embed each saved item as one Python dictionary per line.
    data_text = "[\n" + ",\n".join("        " + repr(item) for item in items) + "\n    ]"
    functions = (BuildVisibility,)
    source_text = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    # Keep English comments and exact builder calls from the runtime version.
    source_text = "\n".join("    " + line if line.strip() else "" for line in source_text.splitlines())
    result = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # Visibility data\n"
        "    PATTERN_DATA = " + data_text + "\n\n"
        + source_text
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildVisibility(PATTERN_DATA)\n\n"
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










