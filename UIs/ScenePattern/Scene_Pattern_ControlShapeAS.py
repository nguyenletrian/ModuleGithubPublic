import os
import inspect
import ast
import maya.mel as mel
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
from datetime import datetime
import maya.api.OpenMaya as om


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
    name = "AS Control Shape"
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
    cmds.button(label="Run",width=100,c=partial(Run,data))
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
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def BuildControlShapeAS(datas):
    """Execute the unchanged original Advanced Skeleton MEL shape replacement."""
    if datas:
        mel.eval("AdvancedSkeleton;asControllerGalleryImport;")
        for data in datas:
            objs = data["object"].split("\n")
            shape = data["shape"]            
            for obj in objs:
                cmds.select(obj)
                cmds.select(shape,add=True)
                mel.eval("asSwapCurve;")

        cmds.delete("deleteThis")

    cmds.warning("Change control shapes done!~")


def Run(data, *arr):
    return BuildControlShapeAS(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("ControlShapeAS Export: no saved records")
        return None

    # This variant requires Advanced Skeleton to be installed inside Maya.
    tree = ast.parse(inspect.getsource(BuildControlShapeAS))
    code = ast.unparse(tree)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    embedded = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.mel as mel\n\n"
        "    # Requires Advanced Skeleton's Maya MEL procedures.\n"
        "    # ControlShapeAS data\n"
        "    SHAPE_DATA = " + embedded + "\n\n"
        + code
        + "\n\n    # Swap shapes using the original Advanced Skeleton tools.\n"
        + "    BuildControlShapeAS(SHAPE_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in script:
        script = script.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(script)
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
    cmds.textField(text='Object',editable=False)
    itemData['object'] = cmds.scrollField(wordWrap=True,height=100,text=data.get("object", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['object']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['object']))
    cmds.setParent("..")
    cmds.textField(text='Shape',editable=False)
    itemData["shape"] = cmds.optionMenu()
    shapeData = NLTA_Control.ShapeASData()
    for key in shapeData:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["shape"], e=True, value=data.get("shape",shapeData[0]))
    cmds.text(label="")

    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










