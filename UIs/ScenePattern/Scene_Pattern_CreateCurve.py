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
    name = "Create Curve"
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


def BuildCreateCurve(datas):
    """Create the saved curves and their rebuilt versions."""
    if not datas:
        return
    curves = []
    for item in datas:
        # Read the saved world-space curve points.
        points = []
        for line in item["points"].splitlines():
            line = line.strip()
            if not line:
                continue
            points.append(tuple(map(float, line.split())))
        if len(points) < 2:
            cmds.warning("{}: Need at least 2 points.".format(item["curveName"]))
            continue
        degree = min(3, len(points) - 1)
        curve = cmds.curve(p=points, d=degree, name=item["curveName"])
        cmds.setAttr(curve + ".v", 0)
        if cmds.objExists(item["parent"]):
            cmds.parent(curve, item["parent"])

        # Preserve the original rebuild settings and returned curve names.
        rebuild = int(item.get("rebuild", 0))
        result = cmds.rebuildCurve(curve, ch=True, rpo=False, rt=0, end=True, kr=False, kcp=False, kep=True, kt=False, s=100, d=3, tol=0.01)
        rebuild_node = result[0]
        new_curve = cmds.rename(rebuild_node, curve + "_Rebuild")
        cmds.setAttr(new_curve + ".v", 0)
        if cmds.objExists(item["parent"]):
            cmds.parent(new_curve, item["parent"])
        curves.append(curve)
    return curves

def Run(data, *args):
    """Run the same Maya builder embedded in the exported script."""
    datas = NLTA_General.readJsonFile(_pattern_data_path(data))
    return BuildCreateCurve(datas)


def ExportPython(data, *args):
    """Generate a standalone Python file from the current builder."""
    data_path = _pattern_data_path(data)
    datas = NLTA_General.readJsonFile(data_path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("CreateCurve Export: no saved items")
        return None

    # One complete dictionary per line, preserving the original values.
    entries = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    builder = inspect.getsource(BuildCreateCurve).rstrip()
    # Exclude only the optional Maya warning; the invalid-curve skip remains.
    warning_line = '            cmds.warning("{}: Need at least 2 points.".format(item["curveName"]))\n'
    if warning_line not in builder:
        raise RuntimeError("Cannot identify the optional point-count warning")
    builder = builder.replace(warning_line, "")
    builder = "\n".join("    " + line if line.strip() else "" for line in builder.splitlines())
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # CreateCurve data\n"
        "    PATTERN_DATA = " + entries + "\n\n"
        + builder
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildCreateCurve(PATTERN_DATA)\n\n"
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

    cmds.textField(text='Points',editable=False)
    itemData['points'] = cmds.scrollField(text=data.get('points', ""))
    cmds.rowColumnLayout(2)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickPos,itemData['points']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickPosAdd,itemData['points']))
    cmds.setParent("..")

    cmds.textField(text='Parent',editable=False)
    itemData['parent'] = cmds.textField(text=data.get('parent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['parent']))

    cmds.textField(text='CurveName',editable=False)
    itemData['curveName'] = cmds.textField(text=data.get('curveName', ""))
    cmds.text(label="")

    cmds.textField(text='Rebuild',editable=False)
    itemData['rebuild'] = cmds.textField(text=data.get('rebuild', "0"))
    cmds.text(label="")

    cmds.setParent("..") #--
    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










