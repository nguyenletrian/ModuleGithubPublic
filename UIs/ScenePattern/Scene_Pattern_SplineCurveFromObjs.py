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
    name = "Spline Curve From Objs"
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
    """Resolve this pattern's saved settings for Run and Export."""
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


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

def BuildSplineCurveFromObjs(datas):
    """Build the saved spline scene using Maya commands."""
    if not datas:
        return
    for splineData in datas:
        parent = splineData["parent"]
        controls = splineData["controls"].split("\n")
        rebuild = splineData["rebuild"]
        for ctrl in controls:
            if not cmds.objExists(ctrl + "_SplineOffset"):
                _create_offset_group(ctrl,ctrl + "_SplineOffset")
        splineJoints = []
        for ctrl in controls:
            pos = cmds.xform(ctrl,q=True,ws=True,t=True)
            cmds.select(cl=True)
            jnt = cmds.joint(p=pos,n=ctrl + "_SplineJnt")
            splineJoints.append(jnt)
        for i in range(1,len(splineJoints)):
            cmds.parent(splineJoints[i],splineJoints[i-1])
        cmds.joint(splineJoints[0],e=True,oj="xyz",sao="yup",ch=True,zso=True)
        cmds.joint(splineJoints[-1],e=True,oj="none")
        followGroups = []
        for ctrl,jnt in zip(controls,splineJoints):
            grp = _group_match_object(ctrl,ctrl + "_SplineRef")
            cmds.parent(grp,jnt)
            followGroups.append(grp)
        points = []
        for jnt in splineJoints:
            points.append(cmds.xform(jnt,q=True,ws=True,t=True))
        degree = min(3,len(points)-1)
        curve = cmds.curve(d=degree,p=points,n=splineJoints[0] + "_SplineCurve")

        # Rebuild curve
        result = cmds.rebuildCurve(curve,ch=True,rpo=False,rt=0,end=True,kr=False,kcp=False,kep=True,kt=False,s=100,d=3,tol=0.01)
        rebuildNode = result[0]
        newCurve = cmds.rename(rebuildNode, curve + "_Rebuild")

        cmds.setAttr(curve + ".inheritsTransform",0)
        cmds.setAttr(newCurve + ".inheritsTransform",0)
        
        ikHandle = cmds.ikHandle(sj=splineJoints[0],ee=splineJoints[-1],sol="ikSplineSolver",c=newCurve,ccv=False,pcv=False)[0]        
        rigGrp = cmds.group(em=True, n=controls[0] + "_SplineRig")
        visibleGrp = cmds.group(em=True, n=controls[0] + "_SplineRigVisible", p=rigGrp)
        hiddenGrp = cmds.group(em=True, n=controls[0] + "_SplineRigHidden", p=rigGrp)
        cmds.setAttr(hiddenGrp + ".visibility", 0)
        cmds.parent(curve,ikHandle,splineJoints[0],newCurve,hiddenGrp)
        cmds.parent(rigGrp,parent)


def Run(data, *args):
    """Run the same builder used by the standalone Python export."""
    return BuildSplineCurveFromObjs(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    """Export standalone Maya Python from the shared rig builder."""
    data_path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(data_path)
    if not isinstance(records, list) or not records:
        cmds.warning("SplineCurveFromObjs Export: no saved items")
        return None

    import ast
    rows = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    functions = (_unique_name, _group_match_object, _create_offset_group, BuildSplineCurveFromObjs)
    code = ast.unparse(ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)))
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # SplineCurveFromObjs data\n"
        "    SPLINE_DATA = " + rows + "\n\n"
        + code
        + "\n\n    # Create the spline joint chain, curve, and IK handle.\n"
        + "    BuildSplineCurveFromObjs(SPLINE_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in generated:
        generated = generated.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(generated, filename, "exec")
    output_path = os.path.join(os.path.dirname(data_path), filename)
    with open(output_path, "w", encoding="utf-8") as writer:
        writer.write(generated)
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



    cmds.textField(text='Parent',editable=False)
    itemData['parent'] = cmds.textField(text=data.get('parent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['parent']))

    cmds.textField(text='Controls',editable=False)
    itemData['controls'] = cmds.scrollField(text=data.get('controls', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['controls']))

    cmds.textField(text='Rebuild',editable=False)
    itemData['rebuild'] = cmds.textField(text=data.get('rebuild', "100"))
    cmds.text(label="")

    cmds.setParent("..") #--
    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










