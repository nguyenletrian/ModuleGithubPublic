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
    name = "Control Shape"
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

    def SaveAndExport(*args):
        Save(data)
        ExportPython(data)

    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]

    cmds.rowColumnLayout(numberOfColumns=1,parent=buttonUI)
    cmds.rowColumnLayout(nc=4)    
    cmds.button(label="Add",c=partial(Add,listUI,{}),width=100)
    cmds.button(label="Save",c=partial(Save,data),width=100)
    cmds.button(label="Run",width=100, c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=100,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.button(label="Mirror",c=NLTA_Control.MirrorShape,width=100)
    cmds.button(label="Copy",c=NLTA_Control.CopyShape,width=100)
    cmds.button(label="Quick Export",c=partial(NLTA_Control.QuickExportCurve,data))
    cmds.button(label="Quick Import",c=partial(NLTA_Control.QuickImportCurve,data))
    cmds.button(label="Import File",c=NLTA_Control.ImportCurveFromFile)
    cmds.setParent("..")
    colorParent = cmds.rowColumnLayout(nc=1)
    colorPick = NLTA_Control.IndexColorPick({"parent":colorParent,"width":400,"height":100})
    cmds.setParent("..")
    cmds.setParent("..")
    Load(data,listUI)

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def _shape_change_single(data, curveTemplates, *arr):
    shape = data["shape"]
    objs = data["objs"]
    if shape not in curveTemplates:
        cmds.warning("Shape not found: " + shape)
        return
    points = curveTemplates[shape]
    for obj in objs:
        if cmds.objExists(obj):
            if cmds.nodeType(obj) == "nurbsCurve":
                shape = obj
                transform = cmds.listRelatives(shape, p=True, f=True)[0]
            else:
                transform = obj
                shapes = cmds.listRelatives(transform,s=True,type="nurbsCurve",f=True) or []
                if not shapes:
                    cmds.warning("No curve shape found under: " + transform)
                    continue
                shape = shapes[0]

            if not cmds.objExists(shape):
                continue
            incoming = cmds.listConnections(shape,s=True,d=False,p=True,c=True) or []
            outgoing = cmds.listConnections(shape,s=False,d=True,p=True,c=True) or []
            cmds.delete(shape)

            new_curve = cmds.curve(d=1,p=points,name=transform.split("|")[-1] + "_crvTmp")
            new_shape = cmds.listRelatives(new_curve,s=True,f=True)[0]
            cmds.parent(new_shape,transform,shape=True,r=True)
            cmds.delete(new_curve)
            new_shape = cmds.listRelatives(transform,s=True,type="nurbsCurve",f=True)[-1]

            for i in range(0, len(incoming), 2):
                dst_attr = incoming[i]
                src_attr = incoming[i + 1]
                dst_attr = dst_attr.replace(shape,new_shape)
                try:
                    cmds.connectAttr(src_attr,dst_attr,f=True)
                except:
                    pass

            for i in range(0, len(outgoing), 2):
                src_attr = outgoing[i]
                dst_attr = outgoing[i + 1]
                src_attr = src_attr.replace(shape,new_shape)
                try:
                    cmds.connectAttr(src_attr,dst_attr,f=True)
                except:
                    pass
            cmds.rename(new_shape,shape.split("|")[-1])


def BuildControlShape(datas, templates):
    """Replace saved controller curve shapes while preserving connections."""
    if datas:
        for item in datas:
            objects = item["object"].split("\n")
            shape = item["shape"]
            _shape_change_single({"objs": objects, "shape": shape}, templates)


def Run(data, *args):
    result = BuildControlShape(NLTA_General.readJsonFile(_pattern_data_path(data)), NLTA_Control.ShapeData())
    cmds.warning("Change control shapes done!~")
    return result


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("ControlShape Export: no saved items")
        return None

    # Include only requested templates, with their original CV positions.
    templates = NLTA_Control.ShapeData()
    selected = {name: templates[name] for name in sorted({item["shape"] for item in records}) if name in templates}
    data_source = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    template_source = "{\n" + ",\n".join("        " + repr(name) + ": " + repr(points) for name, points in selected.items()) + "\n    }"
    helpers = (_shape_change_single, BuildControlShape)
    body = "\n\n".join(inspect.getsource(helper).rstrip() for helper in helpers)
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    output = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # ControlShape saved items\n"
        "    SHAPE_DATA = " + data_source + "\n\n"
        + "    # Selected original curve templates\n"
        + "    CURVE_TEMPLATES = " + template_source + "\n\n"
        + body
        + "\n\n    # Replace the original curve shapes and reconnect their inputs.\n"
        + "    BuildControlShape(SHAPE_DATA, CURVE_TEMPLATES)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in output:
        output = output.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(output, filename, "exec")
    output_path = os.path.join(os.path.dirname(path), filename)
    with open(output_path, "w", encoding="utf-8") as writer:
        writer.write(output)
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
    cmds.textField(text='Object',editable=False)
    itemData['object'] = cmds.scrollField(wordWrap=True,height=100,text=data.get("object", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['object']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['object']))
    cmds.setParent("..")
    cmds.textField(text='Shape',editable=False)
    itemData["shape"] = cmds.optionMenu()
    shapeData = NLTA_Control.ShapeData()
    for key in shapeData:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["shape"], e=True, value=data.get("shape", "circle"))
    cmds.text(label="")

    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










