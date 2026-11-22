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
    name = "Global"
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
    """Find the saved Global pattern data."""
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
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

def BuildGlobal(datas):
    """Build the saved global orientation constraints and slider attributes."""
    if not datas:
        return
    for itemData in datas:
        ctrls = itemData["child"].split("\n")
        parent = itemData["parent"]
        if not cmds.objExists(parent):
            cmds.warning("Parent doesn't exist: {}".format(parent))
            continue

        for ctrl in ctrls:
            ctrl = ctrl.strip()
            if not ctrl or not cmds.objExists(ctrl):
                continue
            if not cmds.attributeQuery(itemData["attrSlide"],node=ctrl,exists=True):
                cmds.addAttr(ctrl,ln=itemData["attrSlide"],at="double",min=0,max=1,dv=float(itemData["defaultValue"]))
                cmds.setAttr(ctrl+"."+itemData["attrSlide"],e=True,keyable=True)
            ctrlParent = cmds.listRelatives(ctrl,parent=True,fullPath=False)
            if not ctrlParent:
                cmds.warning("Can't find parent of {}".format(ctrl))
                continue
            rootParent = ctrlParent[0]
            ctrlPosition = cmds.xform(ctrl,q=True,ws=True,t=True)
            parentRotation = cmds.xform(parent,q=True,ws=True,ro=True)
            globalFirstName = "{}_GlobalFirstParentGrp".format(ctrl)

            if cmds.objExists(globalFirstName):
                globalFirst = globalFirstName
            else:
                globalFirst = cmds.group(em=True,n=globalFirstName)

            # Parent under rootParent
            currentParent = cmds.listRelatives(globalFirst,parent=True)

            if not currentParent or currentParent[0] != rootParent:
                cmds.parent(globalFirst,rootParent)

            # Same position as CTRL
            cmds.xform(globalFirst,ws=True,t=ctrlPosition)

            # Same orientation as parent
            cmds.xform(globalFirst,ws=True,ro=parentRotation)
            offset = _create_offset_group(ctrl,"{}_GlobalGrp".format(ctrl))
            constraintName = "{}_GlobalOrientConstraint".format(ctrl)
            if cmds.objExists(constraintName):
                cmds.delete(constraintName)
            orientConstr = cmds.orientConstraint(globalFirst,parent,offset,mo=itemData["maintain"],n=constraintName)[0]
            cmds.setAttr(orientConstr+".interpType",2)
            weights = cmds.orientConstraint(orientConstr,q=True,weightAliasList=True)
            reverseName = "{}_GlobalReverse".format(ctrl)
            if cmds.objExists(reverseName):
                reverseNode = reverseName
            else:
                reverseNode = cmds.createNode("reverse",n=reverseName)
            slideAttr = ctrl+"."+itemData["attrSlide"]
            cmds.connectAttr(slideAttr,reverseNode+".inputX",force=True)
            cmds.connectAttr(reverseNode+".outputX",orientConstr+"."+weights[0],force=True)
            cmds.connectAttr(slideAttr,orientConstr+"."+weights[1],force=True)


def Run(data, *args):
    """Use the same rig builder as the exported standalone script."""
    return BuildGlobal(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    """Write the Global pattern as independent Maya Python code."""
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("Global Export: no saved items")
        return None

    import ast
    rows = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    functions = (_create_offset_group, BuildGlobal)
    source = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions))
    class RemoveExportWarnings(ast.NodeTransformer):
        def visit_Expr(self, node):
            call = node.value
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name) and call.func.value.id == "cmds"
                    and call.func.attr == "warning"):
                return None
            return self.generic_visit(node)
    source = RemoveExportWarnings().visit(source)
    ast.fix_missing_locations(source)
    source_text = ast.unparse(source)
    notes = (
        ("for itemData in datas:", "# Configure the Global orientation for each saved control."),
        ("globalFirstName =", "# Match a reference group to the parent orientation."),
        ("offset = _create_offset_group(", "# Insert an offset above the driven control."),
        ("orientConstr =", "# Blend the reference and target orientations."),
        ("reverseName =", "# Connect slider and inverse weights."),
    )
    lines = source_text.splitlines()
    for anchor, note in notes:
        for index, line in enumerate(lines):
            if line.lstrip().startswith(anchor):
                indent = line[:len(line) - len(line.lstrip())]
                lines.insert(index, indent + note)
                break
    source_text = "\n".join("    " + line if line.strip() else "" for line in lines)
    content = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # Global data\n"
        "    PATTERN_DATA = " + rows + "\n\n"
        + source_text
        + "\n\n    # Build the saved global orientation network.\n"
        + "    BuildGlobal(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in content:
        content = content.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(content, filename, "exec")
    dest = os.path.join(os.path.dirname(path), filename)
    with open(dest, "w", encoding="utf-8") as output:
        output.write(content)
    return dest


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
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--


    cmds.textField(text='Parent',editable=False)
    itemData['Parent'] = cmds.textField(text=data.get("parent", ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['Parent']))

    cmds.textField(text='Child',editable=False)
    itemData['Child'] = cmds.scrollField(wordWrap=True,height=350,text=data.get("child", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['Child']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['Child']))
    cmds.setParent("..")

    cmds.textField(text='Attr Slide',editable=False)
    itemData['AttrSlide'] = cmds.textField(text=data.get("attrSlide", "Global"))
    cmds.text(label="")

    cmds.textField(text='Default Value',editable=False)
    itemData['DefaultValue'] = cmds.textField(text=data.get("defaultValue", "0"))
    cmds.text(label="")

    cmds.textField(text='Maintain',editable=False)
    itemData['Maintain'] = cmds.checkBox("Maintain", value=data.get("maintain",True))
    cmds.text(label="")

    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










