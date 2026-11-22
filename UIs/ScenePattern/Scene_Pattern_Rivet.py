import os
import importlib
import inspect
import maya.mel as mel
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
    name = "Rivet"
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

def Form(data,*args):
    def Save(data,*args):
        itemData = NLTA_General.JsonGetByID({
            "path": data["sceneDataPath"]+"/ScenePatternData.json",
            "id": data["id"]
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
    item = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(item["path"])


def _unique_name(name):
    if not cmds.objExists(name):
        return name
    index = 1
    while cmds.objExists(name + "_" + str(index)):
        index += 1
    return name + "_" + str(index)


def _group_match_object(obj, name):
    group = cmds.group(em=True, name=name)
    cmds.delete(cmds.parentConstraint(obj, group, mo=False))
    cmds.delete(cmds.scaleConstraint(obj, group, mo=False))
    return group


def _create_offset_group(obj, offset_name):
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


def _bind_skin():
    joints = cmds.ls(sl=True, type="joint")
    meshes = []
    for obj in cmds.ls(sl=True, type="transform"):
        shapes = cmds.listRelatives(obj, s=True, ni=True) or []
        if not shapes:
            continue
        if cmds.nodeType(shapes[0]) == "mesh":
            meshes.append(obj)
    for mesh in meshes:
        cmds.select(mesh)
        cmds.select(joints, add=True)
        cmds.skinCluster(joints, mesh, toSelectedBones=True, bindMethod=3, normalizeWeights=1, weightDistribution=0, mi=4, dr=4, rui=False)


def _copy_joint_bind():
    # Match the original selection-driven skin copy, using Maya MEL directly.
    selection = cmds.ls(selection=True)
    source_mesh = cmds.ls(selection=True)[0]
    target_meshes = cmds.ls(selection=True)[1:]
    source_skin = mel.eval("findRelatedSkinCluster " + source_mesh)
    bind_joints = cmds.skinCluster(source_skin, query=True, inf=True)
    for mesh in target_meshes:
        cmds.select(clear=True)
        cmds.select(mesh)
        mel.eval("DeleteHistory;")
        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
            cmds.setAttr(mesh + "." + attr, lock=False)
        mel.eval("makeIdentity -apply true -t 1 -r 1 -s 1 -n 0 -pn 1;")
        mel.eval("ResetTransformations;")
        cmds.select(bind_joints, add=True)
        _bind_skin()
        cmds.select(clear=True)
        cmds.select(source_mesh)
        cmds.select(mesh, add=True)
        dest_skin = mel.eval("findRelatedSkinCluster " + mesh)
        mel.eval("copySkinWeights -ss " + source_skin + " -ds " + dest_skin + " -noMirror -surfaceAssociation closestPoint -influenceAssociation closestJoint -influenceAssociation oneToOne -normalize;")
        cmds.select(selection)


def BuildRivet(datas):
    """Build an original aim-based rivet, offset controls and copied skin."""
    if not datas:
        return

    for itemData in datas:
        vertexs = [
            x.strip()
            for x in itemData["vertexs"].split("\n")
            if x.strip()
        ]
        if len(vertexs) < 3:
            continue

        mesh = vertexs[0].split(".")[0]
        name = itemData["name"]
        copyTransform = itemData["copyTransform"]
        child = itemData["child"]
        parent = itemData["parent"]

        # Construct the rivet surface from the recorded mesh vertices.
        positions = [cmds.pointPosition(v,w=True)for v in vertexs]
        plane = cmds.polyCreateFacet(p=positions,n=name+"_Plane")[0]

        cmds.select( plane+".e[0]",plane+".e[2]")
        sel_edges = cmds.filterExpand(sm=32)

        cfme1 = cmds.createNode("curveFromMeshEdge")
        cfme2 = cmds.createNode("curveFromMeshEdge")
        loft = cmds.createNode("loft")
        posi = cmds.createNode("pointOnSurfaceInfo")
        e1 = 0
        e2 = 2
        cmds.setAttr(cfme1+".ei[0]",e1)
        cmds.setAttr(cfme2+".ei[0]",e2)

        cmds.setAttr(posi+".turnOnPercentage",1)
        cmds.setAttr(posi+".parameterU",0.5)
        cmds.setAttr(posi+".parameterV",0.5)

        cmds.connectAttr(plane+".worldMesh[0]",cfme1+".inputMesh",f=True)
        cmds.connectAttr(plane+".worldMesh[0]",cfme2+".inputMesh",f=True)
        cmds.connectAttr(cfme1+".outputCurve",loft+".inputCurve[0]",f=True)
        cmds.connectAttr(cfme2+".outputCurve",loft+".inputCurve[1]",f=True)
        cmds.connectAttr(loft+".outputSurface",posi+".inputSurface",f=True)

        # Align the locator to the surface normal and tangent.
        loc = cmds.spaceLocator(n=name+"_Loc")[0]
        ac = cmds.createNode("aimConstraint",p=loc)

        cmds.setAttr(ac+".a",0,1,0,type="double3")
        cmds.setAttr(ac+".u",0,0,1,type="double3")
        cmds.connectAttr(posi+".position",loc+".translate",f=True)
        cmds.connectAttr(posi+".n",ac+".tg[0].tt",f=True)
        cmds.connectAttr(posi+".tv",ac+".wu",f=True)
        cmds.connectAttr(ac+".crx",loc+".rx",f=True)
        cmds.connectAttr(ac+".cry",loc+".ry",f=True)
        cmds.connectAttr(ac+".crz",loc+".rz",f=True)
        if copyTransform:
            grp = _group_match_object(copyTransform,name+"_CopyTransform")
            cmds.parent(grp,loc)

        if child:
            offset = _create_offset_group(child,child+"_RivetOffset")
            cmds.parentConstraint(loc,offset,mo=True)
        # Bind the rivet plane to the source mesh skin influences.
        cmds.select(mesh)
        cmds.select(plane,add=True)
        _copy_joint_bind()
        if parent:
            cmds.parent([plane,loc],parent)


def Run(data, *args):
    return BuildRivet(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("Rivet Export: no saved items")
        return None

    helpers = (_unique_name, _group_match_object, _create_offset_group, _bind_skin, _copy_joint_bind, BuildRivet)
    source = "\n\n".join(inspect.getsource(helper).rstrip() for helper in helpers)
    source = "\n".join("    " + line if line.strip() else "" for line in source.splitlines())
    items = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.mel as mel\n\n"
        "    # Rivet data\n"
        "    RIVET_DATA = " + items + "\n\n"
        + source
        + "\n\n    # Build the recorded surface rivets and skin transfer.\n"
        + "    BuildRivet(RIVET_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in generated:
        generated = generated.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(generated, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(generated)
    return output


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
    cmds.textField(text="Vertexs",editable=False)
    itemData["vertexs"] = cmds.scrollField(text=data.get("vertexs",""),h=80)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["vertexs"]))
    cmds.setParent("..")
    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Name",editable=False)
    itemData["name"] = cmds.textField(text=data.get("name",""))
    cmds.setParent("..")
    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Copy Trans",editable=False)
    itemData["copyTransform"] = cmds.textField(text=data.get("copyTransform",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["copyTransform"]))
    cmds.setParent("..")
    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Child",editable=False)
    itemData["child"] = cmds.textField(text=data.get("child",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["child"]))
    cmds.setParent("..")
    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Parent",editable=False)
    itemData["parent"] = cmds.textField(text=data.get("parent",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["parent"]))
    cmds.setParent("..")

    cmds.button(label="X",w=380,bgc=(0.5,0.2,0.2),c=partial(Delete,itemUI))
    cmds.setParent("..")
    cmds.setParent("..")

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)










