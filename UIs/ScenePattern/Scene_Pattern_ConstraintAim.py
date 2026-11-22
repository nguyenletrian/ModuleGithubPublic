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
    name = "Aim Constraint"
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
    cmds.button(label="Run",width=100,c=partial(Run,data))
    export_button = cmds.button(label="Export Py", width=110, c=SaveAndExport)
    cmds.popupMenu(parent=export_button, button=3)
    cmds.menuItem(label="Open Folder", c=partial(OpenExportFolder, data))
    cmds.setParent("..")
    Load(data,listUI)

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def _create_offset_group(obj, offset_name):
    """Match a new offset to the object and preserve its parent hierarchy."""
    parent = cmds.listRelatives(obj, parent=True)
    if parent and parent[0] == offset_name:
        return offset_name
    if cmds.objExists(offset_name):
        children = cmds.listRelatives(offset_name, children=True, fullPath=False) or []
        if obj in children:
            return offset_name
        # Use the same suffix rule as the original Maya utility.
        base = offset_name
        index = 1
        while cmds.objExists(base + "_" + str(index)):
            index += 1
        offset_name = base + "_" + str(index)

    group = cmds.group(em=True, name=offset_name)
    cmds.delete(cmds.parentConstraint(obj, group, mo=False))
    cmds.delete(cmds.scaleConstraint(obj, group, mo=False))
    if parent:
        cmds.parent(group, parent[0])
    cmds.parent(obj, group)
    return group

def BuildConstraintAim(datas):
    """Create the saved aim constraints and their AimEnable switches."""
    axes = {"x": (1, 0, 0), "-x": (-1, 0, 0), "y": (0, 1, 0),
            "-y": (0, -1, 0), "z": (0, 0, 1), "-z": (0, 0, -1)}
    created = []
    for item in datas:
        child = item["child"]
        target = item["parent"]
        reference = item["reference"]
        container = item["constraintContent"]
        aim = axes[item["mainAxis"]]
        up = axes[item["secondAxis"]]

        # Match the original offset transform before applying the aim.
        group = _create_offset_group(child, child + "_AimGrp")
        constraint = cmds.aimConstraint(target, group, aimVector=aim, upVector=up, worldUpType="object", worldUpObject=reference, mo=item["maintain"])[0]

        # Drive the constraint weight using the child's AimEnable attribute.
        if not cmds.attributeQuery("AimEnable", node=child, exists=True):
            cmds.addAttr(child, ln="AimEnable", at="bool", dv=1, k=True)
        alias = cmds.aimConstraint(constraint, q=True, weightAliasList=True)[0]
        cmds.connectAttr(child + ".AimEnable", constraint + "." + alias, f=True)
        if container:
            cmds.parent(constraint, container)
        created.append(constraint)
    return created


def Run(data, *args):
    datas = NLTA_General.readJsonFile(_pattern_data_path(data)) or []
    return BuildConstraintAim(datas)


def ExportPython(data, *args):
    """Export an independent Maya aim builder from the same Run functions."""
    data_path = _pattern_data_path(data)
    datas = NLTA_General.readJsonFile(data_path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("ConstraintAim Export: no saved items")
        return None

    # Include readable records and only the Maya builder functions.
    data_text = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    functions = (_create_offset_group, BuildConstraintAim)
    functions_text = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    functions_text = "\n".join("    " + line if line.strip() else "" for line in functions_text.splitlines())
    output_text = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # ConstraintAim data\n"
        "    PATTERN_DATA = " + data_text + "\n\n"
        + functions_text
        + "\n\n    # Build the saved aim constraints.\n"
        + "    BuildConstraintAim(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in output_text:
        output_text = output_text.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(output_text, filename, "exec")
    output_path = os.path.join(os.path.dirname(data_path), filename)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(output_text)
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


    cmds.textField(text='Child',editable=False)
    itemData['child'] = cmds.textField(text=data.get('child', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['child']))

    cmds.textField(text='Parent',editable=False)
    itemData['parent'] = cmds.textField(text=data.get('parent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['parent']))

    cmds.textField(text='Reference',editable=False)
    itemData['reference'] = cmds.textField(text=data.get('reference', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['reference']))

    cmds.textField(text='Main Axis',editable=False)
    itemData["mainAxis"] = cmds.optionMenu()
    for key in ["x","y","x","-x","-y","-z"]:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["mainAxis"], e=True, value=data.get("mainAxis","x"))
    cmds.text(label="")

    cmds.textField(text='Second Axis',editable=False)
    itemData["secondAxis"] = cmds.optionMenu()
    for key in ["x","y","x","-x","-y","-z"]:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["secondAxis"], e=True, value=data.get("secondAxis","x"))
    cmds.text(label="")

    cmds.textField(text='Maintain',editable=False)
    itemData['Maintain'] = cmds.checkBox("Maintain", value=data.get("maintain",True))
    cmds.text(label="")

    cmds.textField(text='Cons Content',editable=False)
    itemData['constraintContent'] = cmds.textField(text=data.get('constraintContent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['constraintContent']))

    cmds.setParent("..") #--
    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










