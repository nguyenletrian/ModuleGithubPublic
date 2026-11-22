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
    name = "Follow Orient"
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
    cmds.button(label="Save", width=100,c=partial(Save,data))
    cmds.button(label="Run",width=100, c=partial(Run,data))
    export_button = cmds.button(label="Export Py", width=110, c=SaveAndExport)
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", c=partial(OpenExportFolder, data))
    cmds.setParent("..")
    Load(data,listUI)

def _follow_data_path(data):
    """Locate this pattern's saved data for Run and Export."""
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def BuildFollowTranslate(datas):
    """Build translation-follow groups for each configured parent and child."""
    created = []
    for item in datas:
        parent = item["parent"].strip()
        children = [name.strip() for name in item["child"].split("\n") if name.strip()]
        parent_name = parent.split("|")[-1].split(":")[-1]
        follow_attr = parent_name + "_TranslateFollow"
        for child in children:
            child_name = child.split("|")[-1].split(":")[-1]
            group_name = "{}_{}_FollowTranslateGrp".format(child_name, parent_name)
            offset_name = "{}_{}_FollowTranslateOffsetGrp".format(child_name, parent_name)

            # Preserve the child's initial transform with a follow and offset group.
            current = cmds.listRelatives(child, parent=True)
            current = current[0] if current else None
            group = cmds.createNode("transform", n=group_name, p=current) if current else cmds.createNode("transform", n=group_name)
            cmds.matchTransform(group, child)
            offset = cmds.createNode("transform", n=offset_name, p=group)
            cmds.matchTransform(offset, child)
            cmds.parent(child, offset)

            # Connect the child's follow attribute to the point constraint.
            constraint = cmds.pointConstraint(parent, group, mo=True)[0]
            if not cmds.attributeQuery(follow_attr, node=child, exists=True):
                cmds.addAttr(child, ln=follow_attr, at="double", min=0, max=1, dv=1)
                cmds.setAttr(child + "." + follow_attr, e=True, keyable=True)
            weights = cmds.pointConstraint(constraint, q=True, weightAliasList=True)
            if weights:
                cmds.connectAttr(child + "." + follow_attr, constraint + "." + weights[0], f=True)
            created.append(constraint)
    return created

def Run(data, *args):
    datas = NLTA_General.readJsonFile(_follow_data_path(data)) or []
    return BuildFollowTranslate(datas)


def ExportPython(data, *args):
    """Export one standalone Maya builder with readable embedded settings."""
    datas = NLTA_General.readJsonFile(_follow_data_path(data))
    if not isinstance(datas, list) or not datas:
        cmds.warning("FollowTranslate Export: no saved items")
        return None

    # Store each record on one line and embed the same builder used by Run.
    values = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    builder = inspect.getsource(BuildFollowTranslate).rstrip()
    builder = "\n".join("    " + line if line.strip() else "" for line in builder.splitlines())
    source = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # FollowTranslate data\n"
        "    FOLLOW_DATA = " + values + "\n\n"
        + builder
        + "\n\n    # Build the follow groups.\n"
        + "    BuildFollowTranslate(FOLLOW_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in source:
        source = source.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(_follow_data_path(data)), filename)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(source)
    return output


def OpenExportFolder(data, *args):
    folder = os.path.dirname(_follow_data_path(data))
    os.startfile(folder)


def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--


    cmds.textField(text='Parent',editable=False)
    itemData['Parent'] = cmds.textField(text=data.get("parent", ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['Parent']))

    cmds.textField(text='Child',editable=False)
    itemData['Child'] = cmds.scrollField(wordWrap=True,height=80,text=data.get("child", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['Child']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['Child']))
    cmds.setParent("..")

    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










