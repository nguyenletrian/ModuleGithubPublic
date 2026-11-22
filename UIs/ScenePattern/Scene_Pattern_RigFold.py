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
    name = "Fold Rig"
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
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def BuildRigFold(datas):
    """Build the original fold constraints and driven keyframes."""
    if not datas:
        return
    for data in datas:
        objEnd = data["objEnd"]
        objs = [x.strip() for x in data["objsRun"].split("\n") if x.strip()]
        dests = [x.strip() for x in data["destinations"].split("\n") if x.strip()]
        if len(objs) != len(dests):
            cmds.error("objsRun count must equal destinations count.")
        attrContent = data["attrContent"]
        attr = data["attr"]
        constraintContent = data["constraintContent"]
        # Create the saved fold channel and its original helper network.
        if not cmds.attributeQuery(attr, node=attrContent, exists=True):
            count = len(objs)
            if not cmds.attributeQuery(attr, node=attrContent, exists=True):
                cmds.addAttr(attrContent,ln=attr,at="long",min=0,max=count,dv=count,k=True)
            driverAttr = "{}.{}".format(attrContent, attr)
            reverseNode = "{}_{}_Reverse".format(attrContent.replace("|", "_"), attr)
            if not cmds.objExists(reverseNode):
                reverseNode = cmds.createNode("plusMinusAverage",n=reverseNode)
                cmds.setAttr(reverseNode + ".operation", 2)          # Subtract
                cmds.setAttr(reverseNode + ".input1D[0]", count)     # count - value
                cmds.connectAttr("{}.{}".format(attrContent, attr),reverseNode + ".input1D[1]",f=True)
            driverAttr = reverseNode + ".output1D"

        driverAttr = "{}.{}".format(attrContent, attr)

        # Build the parent constraints and key their individual weights.
        for runIndex, obj in enumerate(objs, start=1):
            con = cmds.parentConstraint(*([objEnd] + dests),obj,mo=False)[0]
            cmds.setAttr(con + ".interpType", 2)
            if constraintContent:
                cmds.parent(con, constraintContent)
            aliases = cmds.parentConstraint(con,q=True,weightAliasList=True)
            count = len(objs)
            for attrValue in range(count + 1):
                sdkValue = count - attrValue
                cmds.setAttr(driverAttr, sdkValue)
                driver = runIndex - attrValue
                for alias in aliases:
                    cmds.setAttr("{}.{}".format(con, alias), 0)
                if driver <= 0:
                    index = 0
                else:
                    index = driver
                cmds.setAttr("{}.{}".format(con, aliases[index]),1)
                for alias in aliases:
                    cmds.setDrivenKeyframe("{}.{}".format(con, alias),currentDriver=driverAttr)
        cmds.setAttr(driverAttr,count)


def Run(data, *args):
    return BuildRigFold(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("RigFold Export: no saved items")
        return None

    # The standalone script embeds the exact UI builder and saved records.
    rows = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    code = "\n".join("    " + line if line.strip() else "" for line in inspect.getsource(BuildRigFold).rstrip().splitlines())
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # RigFold data\n"
        "    FOLD_DATA = " + rows + "\n\n"
        + code
        + "\n\n    # Rebuild the original fold constraints and driven keys.\n"
        + "    BuildRigFold(FOLD_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in script:
        script = script.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(script)
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

    def PickChild(ui,*arr):
        NLTA_UI.PickObject(ui)
        offsetGroup = cmds.textField(itemData["Child"],query=True,text=True)+"_Offset"
        cmds.textField(itemData["OffsetName"],edit=True,text=offsetGroup)

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--

    cmds.textField(text='Object End',editable=False)
    itemData['objEnd'] = cmds.textField(text=data.get('objEnd', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objEnd']))

    cmds.textField(text='Objects Run',editable=False)
    itemData['objsRun'] = cmds.scrollField(text=data.get('objsRun', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objsRun']))

    cmds.textField(text='Destinations',editable=False)
    itemData['destinations'] = cmds.scrollField(text=data.get('destinations', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['destinations']))

    cmds.textField(text='Attribute Content',editable=False)
    itemData['attrContent'] = cmds.textField(text=data.get('attrContent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['attrContent']))

    cmds.textField(text='Attribute',editable=False)
    itemData["attr"] = cmds.textField(text=data.get("attr", ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickAttrOnly,itemData["attr"]))

    cmds.textField(text="constraintContent",editable=False)
    itemData["constraintContent"] = cmds.textField(text=data.get("constraintContent", ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData["constraintContent"]))

    cmds.setParent("..") #--
    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










