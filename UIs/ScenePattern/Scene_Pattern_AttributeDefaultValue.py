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
    name = "Default Value"
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


def BuildAttributeDefaultValue(datas):
    """Reset saved attribute values and remove incoming compound connections."""
    def disconnectCompoundConnections(attr):
        node, child = attr.split(".", 1)
        attrs = [attr]
        current = child
        while True:
            parent = cmds.attributeQuery(current, node=node, listParent=True)
            if not parent:
                break
            current = parent[0]
            attrs.append("{}.{}".format(node, current))
        attrs.reverse()
        for plug in attrs:
            cmds.setAttr(plug, lock=False)
            conns = cmds.listConnections(plug, source=True, destination=False, plugs=True, connections=True) or []
            for index in range(0, len(conns), 2):
                dest = conns[index]
                src = conns[index + 1]
                cmds.disconnectAttr(src, dest)

    for item in datas:
        plug = item["attribute"]
        value = item["value"]
        node = plug.split(".", 1)[0]
        if cmds.objExists(node):
            # Disconnect compound channels before restoring saved values.
            disconnectCompoundConnections(plug)
            kind = cmds.getAttr(plug, type=True)
            if kind in ("double", "float", "doubleAngle", "doubleLinear"):
                value = float(value)
            elif kind in ("long", "short", "byte", "bool", "enum"):
                value = int(value)
            if kind == "string":
                cmds.setAttr(plug, str(value), type="string")
            else:
                cmds.setAttr(plug, value)

def Run(data, *args):
    datas = NLTA_General.readJsonFile(_attribute_data_path(data)) or []
    return BuildAttributeDefaultValue(datas)


def ExportPython(data, *args):
    """Write readable standalone Python that builds the saved attributes."""
    path = _attribute_data_path(data)
    datas = NLTA_General.readJsonFile(path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("AttributeDefaultValue Export: no saved items")
        return None

    # Keep each saved attribute record on one line.
    saved = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    import ast
    source = ast.unparse(ast.parse(inspect.getsource(BuildAttributeDefaultValue))).strip()
    # Add brief English notes after compacting commands.
    section_notes = (
        ("    def disconnectCompoundConnections(", "    # Disconnect incoming parent and child attribute links."),
        ("            disconnectCompoundConnections(", "            # Restore the saved value using its Maya attribute type."),
    )
    for marker, note in section_notes:
        if marker in source:
            source = source.replace(marker, note + "\n" + marker, 1)
    source = "\n".join("    " + line if line.strip() else "" for line in source.splitlines())
    result = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # AttributeDefaultValue data\n"
        "    ATTRIBUTE_DATA = " + saved + "\n\n"
        + source
        + "\n\n    # Set values after removing existing incoming connections.\n"
        + "    BuildAttributeDefaultValue(ATTRIBUTE_DATA)\n\n"
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

    def GetAttributeValue(attributeUI,valueUI,*arr):
        data = NLTA_UI.GetSelectedAttribute()
        if data["main"]:
            fullAttr = data["objs"][0]+"."+data["main"][0]
            value = cmds.getAttr(fullAttr)
            cmds.textField(attributeUI,edit=True,text=fullAttr)
            cmds.textField(valueUI,edit=True,text=value)
        else:
            Print("Please select a attribute")

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI)

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=4) #--
    cmds.rowColumnLayout(nc=4)
    itemData['attribute'] = cmds.textField(text=data.get("attribute",""),width=240,height=30)
    itemData['value'] = cmds.textField(text=data.get("value",""),width=70,height=30)
    cmds.button(label="->",w=30,height=29,c=partial(GetAttributeValue,itemData['attribute'],itemData['value']))
    cmds.button(label="X",w=30,height=29,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.setParent("..")
    cmds.setParent("..") #--

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










