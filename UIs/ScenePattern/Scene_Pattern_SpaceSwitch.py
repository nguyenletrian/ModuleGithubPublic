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
    name = "Space Switch"
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
    def Save(data,*arr):
        itemData = NLTA_General.JsonGetByID({
            "path":data["sceneDataPath"]+"/ScenePatternData.json",
            "id":data["id"]
        })
        saveData = NLTA_UI.GetData(ITEMS["items"])
        NLTA_General.writeJsonFile(itemData["path"],saveData)
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
    record = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(record["path"])


def _unique_name(name):
    """Choose a free Maya node name with the original numeric suffix rule."""
    if not cmds.objExists(name):
        return name
    index = 1
    while cmds.objExists(name + "_" + str(index)):
        index += 1
    return name + "_" + str(index)


def _group_match_object(obj, name):
    """Create a group matched to an object's translation, rotation and scale."""
    group = cmds.group(em=True, name=name)
    cmds.delete(cmds.parentConstraint(obj, group, mo=False))
    cmds.delete(cmds.scaleConstraint(obj, group, mo=False))
    return group


def _create_offset_group(obj, offset_name):
    """Match the active NLTA offset helper, including existing-group reuse."""
    parent = cmds.listRelatives(obj, parent=True)
    if parent and parent[0] == offset_name:
        return offset_name
    if cmds.objExists(offset_name):
        children = cmds.listRelatives(offset_name, children=True, fullPath=False) or []
        if obj in children:
            return offset_name
        offset_name = _unique_name(offset_name)
    offset = _group_match_object(obj, offset_name)
    if parent:
        cmds.parent(offset, parent[0])
    cmds.parent(obj, offset)
    return offset

def BuildSpaceSwitch(datas):
    """Build the saved Maya SpaceSwitch rig operations."""
    if not datas:
        return
    for itemData in datas:
        child = itemData["child"]
        children = [
            x.strip()
            for x in itemData["child"].split("\n")
            if x.strip()
        ]
        for child in children:

            if not cmds.objExists(child):
                cmds.warning("Missing object : {}".format(child))
                continue

            parents = [x.strip() for x in itemData["parents"].split("\n") if x.strip()]

            if not parents:
                cmds.warning("{} has no parents".format(child))
                continue

            offset = _create_offset_group(child,child+"_SpaceSwitchOffset")
            rootParent = cmds.listRelatives(offset,parent=True)
            rootParent = rootParent[0] if rootParent else None
            defaultSpace = cmds.createNode("transform",n=child+"_DefaultSpace",p=rootParent)
            cmds.matchTransform(defaultSpace, offset)

            maintain = itemData["maintain"]
            attrPick = itemData["attrPick"]
            attrSlide = itemData["attrSlide"]
            defaultValue = float(itemData["defaultValue"])

            if not cmds.attributeQuery(attrPick,node=child,exists=True):

                if itemData["enum"]:
                    enumOption = ":".join(itemData["enum"].split(";"))+":"
                else:
                    enumOption =  ":".join(parents)+":"

                if maintain:
                    options = enumOption
                else:
                    options = "Default:"+enumOption
                    
                cmds.addAttr(child,ln=attrPick,at="enum",en=options)
                cmds.setAttr(child+"."+attrPick,e=True,keyable=True)

            if attrSlide and not cmds.attributeQuery(attrSlide,node=child,exists=True):
                cmds.addAttr(child,ln=attrSlide,at="double",min=0,max=1,dv=defaultValue)
                cmds.setAttr(child+"."+attrSlide,e=True,keyable=True)

            targets = [defaultSpace] + parents
            if maintain:
                constraint = cmds.parentConstraint(*targets, offset, mo=True)[0]
            else:
                constraint = cmds.parentConstraint(*targets, offset, mo=False)[0]
            cmds.setAttr(constraint+".interpType",2)
            weightAttrs = cmds.parentConstraint(constraint,q=True,weightAliasList=True)

            targetList = cmds.parentConstraint(constraint,q=True,targetList=True)

            weightMap = {}
            for target, weight in zip(targetList, weightAttrs):
                weightMap[target.split("|")[-1]] = weight

            if not maintain:
                defaultCondition = cmds.shadingNode("condition", asUtility=True)
                cmds.connectAttr(child+"."+attrPick,defaultCondition+".firstTerm",f=True)
                cmds.setAttr(defaultCondition+".secondTerm", 0)
                cmds.setAttr(defaultCondition+".colorIfTrueR", 1)
                cmds.setAttr(defaultCondition+".colorIfFalseR", 0)
                cmds.connectAttr(defaultCondition+".outColorR",constraint+"."+weightMap[defaultSpace],f=True)

            for i,parent in enumerate(parents):
                condition = cmds.shadingNode("condition",asUtility=True)
                cmds.connectAttr(child+"."+attrPick,condition+".firstTerm",f=True)
                cmds.setAttr(condition+".secondTerm",i if maintain else i+1)
                cmds.setAttr(condition+".colorIfFalseR",0)
                if attrSlide:
                    cmds.connectAttr(child+"."+attrSlide,condition+".colorIfTrueR",f=True)
                else:
                    cmds.setAttr(condition+".colorIfTrueR",1)
                cmds.connectAttr(condition+".outColorR",constraint+"."+weightMap[parent],f=True)

            if attrSlide and rootParent:
                plus = cmds.shadingNode("plusMinusAverage",asUtility=True)
                cmds.setAttr(plus+".operation",2)
                cmds.setAttr(plus+".input1D[0]",1)
                cmds.connectAttr(child+"."+attrSlide,plus+".input1D[1]",f=True)

                slideConstraint = cmds.parentConstraint(rootParent,offset,mo=True)[0]
                cmds.setAttr(slideConstraint+".interpType",2)
                slideWeightAttrs = cmds.parentConstraint(slideConstraint,q=True,weightAliasList=True)
                slideTargets = cmds.parentConstraint(slideConstraint,q=True,targetList=True)
                slideWeightMap = dict(zip(slideTargets,slideWeightAttrs))
                cmds.connectAttr(plus+".output1D",slideConstraint+"."+slideWeightMap[rootParent],f=True)


def Run(data, *args):
    """Execute the same Maya builder used by the exported Python."""
    return BuildSpaceSwitch(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    """Write a compact, standalone Maya Python script."""
    path = _pattern_data_path(data)
    items = NLTA_General.readJsonFile(path)
    if not isinstance(items, list) or not items:
        cmds.warning("SpaceSwitch Export: no saved items")
        return None

    import ast
    values = "[\n" + ",\n".join("        " + repr(record) for record in items) + "\n    ]"
    functions = (_unique_name, _group_match_object, _create_offset_group, BuildSpaceSwitch)
    code = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    tree = ast.parse(code)
    class RemoveExportWarnings(ast.NodeTransformer):
        def visit_Expr(self, node):
            call = node.value
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "cmds" and call.func.attr == "warning"):
                return None
            return self.generic_visit(node)
    tree = RemoveExportWarnings().visit(tree)
    ast.fix_missing_locations(tree)
    code = ast.unparse(tree)
    # Place short English notes at the matching indentation.
    notes = (
        ("children =", "# Read the driven objects and available parent spaces."),
        ("offset = _create_offset_group", "# Preserve the driven transform while inserting a space offset."),
        ("targets =", "# Build parent constraints and their switch weights."),
        ("if not maintain:", "# Include the default-space condition when maintain is disabled."),
        ("for i, parent in enumerate(", "# Connect each parent-space condition to its weight."),
        ("if attrSlide and rootParent:", "# Blend the original parent with the selected space."),
    )
    lines = code.splitlines()
    for needle, note in notes:
        for index, line in enumerate(lines):
            if line.lstrip().startswith(needle):
                indent = line[:len(line) - len(line.lstrip())]
                lines.insert(index, indent + note)
                break
    code = "\n".join("    " + line if line.strip() else "" for line in lines)
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # SpaceSwitch data\n"
        "    PATTERN_DATA = " + values + "\n\n"
        + code
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildSpaceSwitch(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in generated:
        generated = generated.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(generated, filename, "exec")
    destination = os.path.join(os.path.dirname(path), filename)
    with open(destination, "w", encoding="utf-8") as output:
        output.write(generated)
    return destination


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_pattern_data_path(data)))


def Add(listUI,data,*args):
    global ITEMS

    def Delete(ui,*args):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS["items"][ui]
        ITEMS["order"].remove(ui)

    itemData = {}
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15,0.15,0.15))
    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Child",editable=False)
    itemData["child"] = cmds.scrollField( text=data.get("child",""),h=80)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["child"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Parents",editable=False)
    itemData["parents"] = cmds.scrollField( text=data.get("parents",""),h=80)
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData["parents"]))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData["parents"]))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Attr Pick",editable=False)
    itemData["attrPick"] = cmds.textField(text=data.get("attrPick","space"))
    cmds.setParent("..")
    
    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Enum",editable=False)
    itemData["enum"] = cmds.textField(text=data.get("enum",""))
    cmds.setParent("..")


    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Attr Slide",editable=False)
    itemData["attrSlide"] = cmds.textField(text=data.get("attrSlide",""))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Default",editable=False)
    itemData["defaultValue"] = cmds.textField(text=data.get("defaultValue","1"))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Maintain",editable=False)
    itemData["maintain"] = cmds.checkBox(value=data.get("maintain",True),label="")
    cmds.setParent("..")

    cmds.button(label="X",w=380, bgc=(0.5,0.2,0.2),c=partial(Delete,itemUI))

    cmds.setParent("..")
    cmds.setParent("..")

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)