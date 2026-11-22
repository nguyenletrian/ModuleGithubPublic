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
    name = "Spline Controls From Objs"
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


def _group_match_object(obj, name):
    """Create a group matched to an object's translation, rotation and scale."""
    group = cmds.group(em=True, name=name)
    cmds.delete(cmds.parentConstraint(obj, group, mo=False))
    cmds.delete(cmds.scaleConstraint(obj, group, mo=False))
    return group

def BuildCreateSplineControlsFromSplineIK(datas):
    """Build the saved spline scene using Maya commands."""
    if not datas:
        return
    for splineData in datas:
        parent = splineData["parent"]
        parentGlobal = splineData["parentGlobal"]
        curve = splineData["curve"]
        splineJoints = [x.strip()for x in splineData["joints"].split("\n")if x.strip()]
        numberCtrls = int(splineData["numberCtrls"])
        base = splineJoints[0].replace("_SplineJnt", "")
        rigGrp = base + "_SplineRig"
        visibleGrp = base + "_SplineRigVisible"
        hiddenGrp = base + "_SplineRigHidden"

        # ---------------------------
        # CHECK GROUP
        # ------------------------------
        for grp, parentGrp in (
            (rigGrp, parent),
            (visibleGrp, rigGrp),
            (hiddenGrp, rigGrp),
        ):
            if not cmds.objExists(grp):
                cmds.group(em=True, n=grp)
                cmds.parent(grp, parentGrp)

        # ---------------------------------------------------
        # CREATE CONTROL JOINTS
        # ---------------------------------------------------

        controlJoints = []
        total = numberCtrls + 2
        for i in range(total):
            u = float(i) / float(total - 1)
            poc = cmds.createNode("pointOnCurveInfo")
            cmds.connectAttr(curve + ".worldSpace[0]", poc + ".inputCurve")
            cmds.setAttr(poc + ".turnOnPercentage", 1)
            cmds.setAttr(poc + ".parameter", u)
            pos = cmds.getAttr(poc + ".position")[0]
            cmds.delete(poc)
            cmds.select(cl=True)
            jnt = cmds.joint(p=pos,n="{}_CtrlJnt_{:02d}".format(base, i + 1))
            controlJoints.append(jnt)

        cmds.skinCluster(controlJoints, curve, tsb=True, mi=2)

        splineCtrls = []
        length = cmds.arclen(curve)
        size = length * 0.03
        for jnt in controlJoints:
            ctrl = cmds.curve(d=1,p=[(-1,0,-1),(-1,0,1),(1,0,1),(1,0,-1),(-1,0,-1)],n=jnt.replace("_CtrlJnt","_Ctrl"))
            cmds.scale(size,size,size,ctrl)
            cmds.makeIdentity(ctrl,apply=True)
            zero = cmds.group(ctrl,n=ctrl + "_Zero")
            matrix = cmds.xform(jnt,q=True,ws=True,m=True)
            cmds.xform(zero,ws=True,m=matrix)
            cmds.parentConstraint(ctrl,jnt,mo=False)
            splineCtrls.append(ctrl)

        ctrlZeros = [cmds.listRelatives(ctrl,p=True)[0]for ctrl in splineCtrls]
        globalGrp = _group_match_object(splineCtrls[0],base + "_SplineControls_GlobalGrp")
        cmds.parent(globalGrp,visibleGrp)
        cmds.parent(ctrlZeros,globalGrp)
        cmds.parent(curve,splineJoints[0],controlJoints,hiddenGrp)

        masterCtrl = splineCtrls[0]
        if not cmds.attributeQuery("Global",node=masterCtrl,exists=True):
            cmds.addAttr(masterCtrl,ln="Global",at="double",min=0,max=1,dv=0,k=True)

        blend = cmds.createNode("blendColors")
        parentCon = cmds.parentConstraint(parentGlobal,globalGrp,mo=True)[0]
        cmds.setAttr(parentCon + ".interpType",2)

        for attr in ("rx","ry","rz"):
            for src in cmds.listConnections(globalGrp + "." + attr,s=True,d=False,p=True) or []:
                cmds.disconnectAttr(src,globalGrp + "." + attr)

        orientCon = cmds.orientConstraint(parent,globalGrp,mo=True)[0]
        for attr in ("rx","ry","rz"):
            for src in cmds.listConnections(globalGrp + "." + attr,s=True,d=False,p=True) or []:
                cmds.disconnectAttr(src,globalGrp + "." + attr)

        cmds.connectAttr(parentCon + ".constraintRotate",blend + ".color1",f=True)
        cmds.connectAttr(orientCon + ".constraintRotate",blend + ".color2",f=True)
        cmds.connectAttr(blend + ".output",globalGrp + ".rotate",f=True)
        cmds.connectAttr(masterCtrl + ".Global",blend + ".blender",f=True)


def Run(data, *args):
    """Run the same builder used by the standalone Python export."""
    return BuildCreateSplineControlsFromSplineIK(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    """Export standalone Maya Python from the shared rig builder."""
    data_path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(data_path)
    if not isinstance(records, list) or not records:
        cmds.warning("CreateSplineControlsFromSplineIK Export: no saved items")
        return None

    import ast
    rows = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    functions = (_group_match_object, BuildCreateSplineControlsFromSplineIK)
    code = ast.unparse(ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)))
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # CreateSplineControlsFromSplineIK data\n"
        "    SPLINE_DATA = " + rows + "\n\n"
        + code
        + "\n\n    # Create the spline controls, skin binding, and global follow.\n"
        + "    BuildCreateSplineControlsFromSplineIK(SPLINE_DATA)\n\n"
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

    cmds.textField(text='Parent Global',editable=False)
    itemData['parentGlobal'] = cmds.textField(text=data.get('parentGlobal', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['parentGlobal']))

    cmds.textField(text='Curve',editable=False)
    itemData['curve'] = cmds.textField(text=data.get('curve', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['curve']))

    cmds.textField(text='Joints',editable=False)
    itemData['joints'] = cmds.scrollField(text=data.get('joints', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['joints']))

    cmds.textField(text='Number Ctrls',editable=False)
    itemData['numberCtrls'] = cmds.textField(text=data.get('numberCtrls', "1"))
    cmds.text(label="")

    cmds.setParent("..") #--
    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










