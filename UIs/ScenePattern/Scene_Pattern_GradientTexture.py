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
    name = "Gradient Texture"
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


def BuildGradientTexture(datas):
    """Reproduce the saved Maya ramp texture and remap network."""
    if not datas:
        return
    typeList = ["V Ramp","U Ramp","Diagonal Ramp","Radial Ramp","Circular Ramp","BoxRamp","UV Ramp","Four Corner Ramp","Tartan Ramp"]
    interList = ["None","Linear","Exponential UP","Exponential Down","Smooth","Bump","Spike"]
    runList = ["Black","White"]
    for data in datas:
        obj = data["object"]
        shapes = cmds.listRelatives(obj,shapes=True,fullPath=True) or []
        sgs = cmds.listConnections(shapes[0],type="shadingEngine") or []
        material = cmds.ls(cmds.listConnections(sgs[0] + ".surfaceShader"),materials=True)[0]
        # Create a ramp on the object's existing shading material.
        ramp = cmds.shadingNode("ramp",asTexture=True,name="{}_ramp".format(obj))

        if cmds.attributeQuery("transparency", node=material, exists=True):
            cmds.connectAttr("{}.outColor".format(ramp),"{}.transparency".format(material),force=True)
        elif cmds.attributeQuery("opacity", node=material, exists=True):
            cmds.connectAttr("{}.outColor".format(ramp),"{}.opacity".format(material),force=True)            
            

        cmds.setAttr("{}.type".format(ramp),typeList.index(data["type"]))
        #cmds.setAttr(ramp + ".interpolation", 0)
        cmds.setAttr("{}.interpolation".format(ramp),interList.index(data["interpolation"]))
        cmds.setAttr("{}.colorEntryList[0].position".format(ramp),float(data["blackBegin"]))
        cmds.setAttr("{}.colorEntryList[0].color".format(ramp),0, 0, 0,type="double3")
        cmds.setAttr("{}.colorEntryList[1].position".format(ramp),float(data["whiteBegin"]))        
        cmds.setAttr("{}.colorEntryList[1].color".format(ramp),1, 1, 1,type="double3")


        # Create the driver attribute and remap its position.
        fullAttr = "{}.{}".format(data["objConnect"],data["attrConnect"])
        if not cmds.objExists(fullAttr):
            cmds.addAttr(data["objConnect"], longName=data["attrConnect"], attributeType="double",min=0,max=10,defaultValue=0,keyable=True)

        remap = cmds.createNode( "remapValue",name="{}_remapValue".format(obj))
        if not data["reverse"]:
            cmds.setAttr(remap + ".inputMin",0)
            cmds.setAttr(remap + ".inputMax",10)
        else:
            cmds.setAttr(remap + ".inputMin",10)
            cmds.setAttr(remap + ".inputMax",0)
        cmds.setAttr(remap + ".outputMin",float(data["minValue"]))
        cmds.setAttr(remap + ".outputMax",float(data["maxValue"]))
        cmds.connectAttr(fullAttr,remap + ".inputValue",force=True)
        cmds.connectAttr(remap + ".outValue","{}.colorEntryList[{}].position".format(ramp,runList.index(data["runColor"])),force=True)


def Run(data, *args):
    return BuildGradientTexture(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("GradientTexture Export: no saved items")
        return None

    # Embed each saved setting without changing the ramp calculation.
    rows = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    source = "\n".join("    " + line if line.strip() else "" for line in inspect.getsource(BuildGradientTexture).rstrip().splitlines())
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # GradientTexture data\n"
        "    PATTERN_DATA = " + rows + "\n\n"
        + source
        + "\n\n    # Recreate the saved ramp texture networks.\n"
        + "    BuildGradientTexture(PATTERN_DATA)\n\n"
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

    cmds.textField(text='object',editable=False)
    itemData['object'] = cmds.textField(text=data.get("object", ""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData['object']))

    cmds.textField(text='Type',editable=False)
    itemData["type"] = cmds.optionMenu()
    for key in ["V Ramp","U Ramp","Diagonal Ramp","Radial Ramp","Circular Ramp","BoxRamp","UV Ramp","Four Corner Ramp","Tartan Ramp"]:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["type"], e=True, value=data.get("type", "V Ramp"))
    cmds.text(label="")

    cmds.textField(text='Interpolation',editable=False)
    itemData["interpolation"] = cmds.optionMenu()
    for key in ["None","Linear","Exponential UP","Exponential Down","Smooth","Bump","Spike"]:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData['interpolation'], e=True, value=data.get('Interpolation',"None"))
    cmds.text(label="")

    cmds.textField(text='White Begin',editable=False)
    itemData['whiteBegin'] = cmds.textField(text=data.get("whiteBegin", "1"))
    cmds.text(label="")

    cmds.textField(text='Black Begin',editable=False)
    itemData['blackBegin'] = cmds.textField(text=data.get("blackBegin", "0"))
    cmds.text(label="")

    cmds.textField(text='Run Color',editable=False)
    itemData["runColor"] = cmds.optionMenu()
    for key in ["Black","White"]:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["runColor"], e=True, value=data.get("runColor","Black"))
    cmds.text(label="")

    cmds.textField(text="Min Value",editable=False)
    itemData["minValue"] = cmds.textField(text=data.get("minValue","0"))
    cmds.text(label="")

    cmds.textField(text="Max Value",editable=False)
    itemData["maxValue"] = cmds.textField(text=data.get("maxValue","1"))
    cmds.text(label="")

    cmds.textField(text="Object Connect",editable=False)
    itemData["objConnect"] = cmds.textField(text=data.get("objConnect",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["objConnect"]))
    
    cmds.textField(text="Attribute Connect",editable=False)
    itemData["attrConnect"] = cmds.textField(text=data.get("attrConnect",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrOnly,itemData["attrConnect"]))

    cmds.textField(text="Reverse",editable=False)
    itemData["reverse"] = cmds.checkBox(value=data.get("reverse",False),label="")
    cmds.text(label="")

    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










