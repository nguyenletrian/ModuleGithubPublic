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
    name = "Create Attibute"
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


def BuildAttributeCreate(datas):
    """Create attributes with the saved types, limits, and channel settings."""
    for item in datas:
        objects = item["objects"].splitlines()
        attr_name = item["attrName"]
        attr_type = item["attrType"]
        for obj in objects:
            if not cmds.objExists(obj):
                continue
            if cmds.attributeQuery(attr_name, node=obj, exists=True):
                continue

            # Configure the attribute type, limits, and default value.
            options = {"ln": attr_name, "k": item["keyable"]}
            if attr_type in ("string", "matrix"):
                options["dt"] = attr_type
            else:
                options["at"] = attr_type
            if attr_type == "enum":
                options["en"] = item["enum"]
            if item["default"] not in ("", None):
                options["dv"] = float(item["default"])
            if item["min"] not in ("", None):
                options["min"] = float(item["min"])
            if item["max"] not in ("", None):
                options["max"] = float(item["max"])
            cmds.addAttr(obj, **options)

            # Apply locking and visibility for the new channel.
            plug = "{}.{}".format(obj, attr_name)
            cmds.setAttr(plug, lock=item["lock"])
            if not cmds.getAttr(plug, keyable=True):
                cmds.setAttr(plug, channelBox=item["channelBox"])

def Run(data, *args):
    datas = NLTA_General.readJsonFile(_attribute_data_path(data)) or []
    return BuildAttributeCreate(datas)


def ExportPython(data, *args):
    """Write readable standalone Python that builds the saved attributes."""
    path = _attribute_data_path(data)
    datas = NLTA_General.readJsonFile(path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("AttributeCreate Export: no saved items")
        return None

    # Keep each saved attribute record on one line.
    saved = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    import ast
    source = ast.unparse(ast.parse(inspect.getsource(BuildAttributeCreate))).strip()
    # Add brief English notes after compacting commands.
    section_notes = (
        ("            options = ", "            # Configure the attribute type and value limits."),
        ("            plug = ", "            # Apply lock and channel visibility settings."),
    )
    for marker, note in section_notes:
        if marker in source:
            source = source.replace(marker, note + "\n" + marker, 1)
    source = "\n".join("    " + line if line.strip() else "" for line in source.splitlines())
    result = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # AttributeCreate data\n"
        "    ATTRIBUTE_DATA = " + saved + "\n\n"
        + source
        + "\n\n    # Create custom attributes on the saved Maya objects.\n"
        + "    BuildAttributeCreate(ATTRIBUTE_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(result, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(result)
    return output


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_attribute_data_path(data)))


def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    def PickAttrInfo(name, type, keyable, lock, channelBox, minUI, maxUI, defaultUI, enumUI, *args):
        pickData = NLTA_UI.GetSelectedAttribute()
        attr = pickData["allAttr"][0]
        obj = pickData["objs"][0]
        attrInfo = NLTA_UI.GetAttributeInfo(obj, attr)
        uiMap = {"name": name,"type": type,"keyable": keyable,"lock": lock,"channelBox": channelBox,"min": minUI,"max": maxUI,"default": defaultUI,"enum": enumUI,}
        for key, ui in uiMap.items():
            NLTA_UI.FillUI(ui, attrInfo.get(key, None))

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--

    cmds.textField(text='Objects',editable=False)
    itemData['objects'] = cmds.scrollField(wordWrap=True,height=150,text=data.get("objects", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objects']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['objects']))
    cmds.setParent("..")

    cmds.textField(text='Attr Name',editable=False)
    itemData['attrName'] = cmds.textField(text=data.get('attrName', ""))
    buttonGetInfo = cmds.button(label="->",w=30)

    cmds.textField(text='Attr Type',editable=False)
    itemData["attrType"] = cmds.optionMenu()
    array = ["bool","byte","short","long","float","double","doubleAngle","doubleLinear","time","enum","string",
                            "message","float2","float3","double2","double3","matrix"]
    for key in array:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["attrType"], e=True, value=data.get("attrType", "bool"))
    cmds.text(label="")

    cmds.textField(text='Keyable',editable=False)
    itemData['keyable'] = cmds.checkBox("keyable", value=data.get("keyable",True))
    cmds.text(label="")

    cmds.textField(text='Lock',editable=False)
    itemData['lock'] = cmds.checkBox("lock", value=data.get("lock",True))
    cmds.text(label="")

    cmds.textField(text='Channel Box',editable=False)
    itemData['channelBox'] = cmds.checkBox("channelBox", value=data.get("channelBox",True))
    cmds.text(label="")

    cmds.textField(text='Min',editable=False)
    itemData['min'] = cmds.textField(text=data.get('min', ""))
    cmds.text(label="")

    cmds.textField(text='Max',editable=False)
    itemData['max'] = cmds.textField(text=data.get('max', ""))
    cmds.text(label="")

    cmds.textField(text='Default',editable=False)
    itemData['default'] = cmds.textField(text=data.get('default', ""))
    cmds.text(label="")

    cmds.textField(text='Enum',editable=False)
    itemData['enum'] = cmds.textField(text=data.get('enum', ""))
    cmds.text(label="")

    cmds.button(buttonGetInfo,e=True,c=partial(PickAttrInfo,
        itemData['attrName'],
        itemData['attrType'],
        itemData['keyable'],
        itemData['lock'],
        itemData['channelBox'],
        itemData['min'],
        itemData['max'],
        itemData['default'],
        itemData['enum'],
    ))
    


    cmds.setParent("..") #--
    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










