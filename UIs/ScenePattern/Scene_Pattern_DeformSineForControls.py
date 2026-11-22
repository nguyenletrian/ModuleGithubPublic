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
    name = "Deform Sine Offset"
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

def BuildDeformSineForControls(datas):
    """Build the saved Maya DeformSineForControls rig operations."""
    if not datas:
        return
    for data in datas:

        curve = data["curve"]
        parent = data["parent"]
        controls = [x for x in data["controls"].splitlines() if x]
        translates = data.get("translates", "xyz").lower()
        holder = data["attrHolder"]
        attrName = data["attrName"]
        
        curveShape = cmds.listRelatives(curve, s=True, ni=True)[0]
        count = len(controls)
        refs = []
        offsets = []

        root = cmds.group(em=True, n=controls[0] + "_SplineRefs")

        for ctrl in controls:
            ref = cmds.group(em=True, n=ctrl + "_Ref")
            cmds.matchTransform(ref, ctrl)
            cmds.setAttr(ref+".inheritsTransform",0)

            poc = cmds.createNode("pointOnCurveInfo", n=ctrl + "_POC")
            cmds.connectAttr(curveShape + ".worldSpace[0]", poc + ".inputCurve", f=True)
            cmds.setAttr(poc + ".turnOnPercentage", 0)
            pos = cmds.xform(ctrl, q=True, ws=True, t=True)
            npc = cmds.createNode("nearestPointOnCurve", n=ctrl + "_NPC")
            cmds.connectAttr(curveShape + ".worldSpace[0]", npc + ".inputCurve", f=True)
            cmds.setAttr(npc + ".inPosition", *pos, type="double3")
            parameter = cmds.getAttr(npc + ".parameter")
            cmds.delete(npc)
            cmds.setAttr(poc + ".parameter", parameter)


            # Chỉ RefPos nhận translate từ curve
            cmds.connectAttr(poc + ".position", ref + ".translate", f=True)
            cmds.parent(ref, root)
            refPos = cmds.group(em=True, n=ctrl + "_RefPos")
            refPos2 = cmds.group(em=True, n=ctrl + "_RefPos2")
            cmds.matchTransform(refPos,ref)
            cmds.matchTransform(refPos2,ref)
            cmds.parent(refPos,root)
            cmds.parent(refPos2,refPos)

            cmds.pointConstraint(ref, refPos2, mo=True)
            refs.append(refPos2)

        # Parent cả root sau cùng
        if cmds.objExists(parent):
            cmds.parent(root, parent)

        for ctrl, refPos in zip(controls, refs):
            if not cmds.objExists(ctrl + "_SineDeformOffset"):
                offset = _create_offset_group(ctrl, ctrl + "_SineDeformOffset")
            else:
                offset = ctrl + "_SineDeformOffset"

            for axis in translates:
                cmds.connectAttr(
                    "{}.translate{}".format(refPos, axis.upper()),
                    "{}.translate{}".format(offset, axis.upper()),
                    f=True
                )
            offsets.append(offset)
        
        # Create sine
        sineHandle, sineNode = cmds.nonLinear(curve,type="sine",name=curve + "_Sine")
        if cmds.objExists(parent):
            cmds.parent(sineNode, parent)

        separator = attrName+"Ops"
        if not cmds.attributeQuery(separator, node=holder, exists=True):
            cmds.addAttr(holder,ln=separator,at="enum",en="--------------",)
            cmds.setAttr(f"{holder}.{separator}", e=True, channelBox=True)


        # Envelope
        envAttr = attrName + "_Active"
        if not cmds.attributeQuery(envAttr, node=holder, exists=True):
            cmds.addAttr(holder,ln=envAttr,at="bool",dv=0,k=True)
        cmds.connectAttr(f"{holder}.{envAttr}",f"{sineHandle}.envelope",force=True)

        # Offset
        offsetAttr = attrName + "_Offset"
        if not cmds.attributeQuery(offsetAttr, node=holder, exists=True):
            cmds.addAttr(holder, ln=offsetAttr, at="double", k=True)
        cmds.connectAttr(f"{holder}.{offsetAttr}",f"{sineHandle}.offset",force=True)

        # Visibility
        visAttr = attrName + "_Visible"
        if not cmds.attributeQuery(visAttr, node=holder, exists=True):
            cmds.addAttr(holder,ln=visAttr,at="bool",dv=0,k=True)
        cmds.connectAttr(f"{holder}.{visAttr}",f"{sineNode}.visibility",force=True)


def Run(data, *args):
    """Execute the same Maya builder used by the exported Python."""
    return BuildDeformSineForControls(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    """Write a compact, standalone Maya Python script."""
    path = _pattern_data_path(data)
    items = NLTA_General.readJsonFile(path)
    if not isinstance(items, list) or not items:
        cmds.warning("DeformSineForControls Export: no saved items")
        return None

    import ast
    values = "[\n" + ",\n".join("        " + repr(record) for record in items) + "\n    ]"
    functions = (_unique_name, _group_match_object, _create_offset_group, BuildDeformSineForControls)
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
        ("curveShape =", "# Read the curve shape and locate each control on its surface."),
        ("root = cmds.group", "# Create reference transforms for the curve-driven controls."),
        ("for ctrl, refPos in zip(", "# Connect each control offset to its curve reference."),
        ("sineHandle, sineNode =", "# Create the sine deformer and connect user controls."),
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
        "    # DeformSineForControls data\n"
        "    PATTERN_DATA = " + values + "\n\n"
        + code
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildDeformSineForControls(PATTERN_DATA)\n\n"
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

    cmds.textField(text='Curve',editable=False)
    itemData['curve'] = cmds.textField(text=data.get('curve', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['curve']))

    cmds.textField(text='Controls',editable=False)
    itemData['controls'] = cmds.scrollField(text=data.get('controls', ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['controls']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd, itemData['controls']))
    cmds.setParent("..")

    cmds.textField(text='Parent',editable=False)
    itemData['parent'] = cmds.textField(text=data.get('parent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['parent']))

    cmds.textField(text='Translates',editable=False)
    itemData['translates'] = cmds.textField(text=data.get('translate', "xyz"))
    cmds.text(label="")

    cmds.textField(text='Attr Holder',editable=False)
    itemData['attrHolder'] = cmds.textField(text=data.get('attrHolder', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['attrHolder']))

    cmds.textField(text="Attr Name",editable=False)
    itemData["attrName"] = cmds.textField(text=data.get("attrName",""))
    cmds.text(label="")


    cmds.setParent("..") #--
    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










