import os
import importlib
import inspect
import json
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
from datetime import datetime
import maya.api.OpenMaya as om

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
    name = "Skin joint to nearest component"
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
    global sceneDataPath
    def Save(data, *arr):
        itemData = NLTA_General.JsonGetByID({
            "path":data["sceneDataPath"]+"/ScenePatternData.json",
            "id":data["id"]
        })          
        returnData = NLTA_UI.GetData(ITEMS['items'])
        NLTA_General.writeJsonFile(itemData["path"],returnData)
    sceneDataPath = data["sceneDataPath"]

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





def GetSkinCluster(mesh):
    history = cmds.listHistory(mesh,pruneDagObjects=True) or []
    for node in history:
        if cmds.nodeType(node) == "skinCluster":
            return node
    return None

def GetMeshPath(mesh):
    sel = om.MSelectionList()
    sel.add(mesh)
    return sel.getDagPath(0)

def GetMeshComponents(mesh):
    path = GetMeshPath(mesh)
    numVertices = om.MFnMesh(path).numVertices
    visited = set()
    components = []
    itVertex = om.MItMeshVertex(path)
    for startVertex in range(numVertices):
        if startVertex in visited:
            continue
        component = []
        stack = [startVertex]
        while stack:
            vertex = stack.pop()
            if vertex in visited:
                continue
            visited.add(vertex)
            component.append(vertex)
            itVertex.setIndex(vertex)
            for neighbor in itVertex.getConnectedVertices():
                if neighbor not in visited:
                    stack.append(neighbor)
        components.append(component)
    return components

def GetWorldVertexPositions(mesh):
    path = GetMeshPath(mesh)
    fnMesh = om.MFnMesh(path)
    points = fnMesh.getPoints(om.MSpace.kWorld)
    return {index: point for index, point in enumerate(points)}


def GetJointWorldPosition(joint):
    position = cmds.xform(joint,query=True,worldSpace=True,translation=True)
    return om.MVector(*position)

def GetClosestDistanceToComponent(jointPosition,component,vertexPositions):
    minDistance = float("inf")
    for vertexID in component:
        point = vertexPositions[vertexID]
        distance = (om.MVector(point) - jointPosition).length()
        if distance < minDistance:
            minDistance = distance
    return minDistance

def AssignComponentsToJoints(mesh,joints):
    components = GetMeshComponents(mesh)
    if not components:
        return []
    vertexPositions = GetWorldVertexPositions(mesh)
    jointPositions = {joint: GetJointWorldPosition(joint) for joint in joints}
    candidates = []
    for joint in joints:
        jointPosition = jointPositions[joint]
        for componentIndex, component in enumerate(components):
            distance = GetClosestDistanceToComponent(jointPosition,component,vertexPositions)
            candidates.append((distance,joint,componentIndex))

    candidates.sort(key=lambda item: item[0])
    assignedJoints = set()
    assignedComponents = set()
    assignments = []
    for distance, joint, componentIndex in candidates:
        if joint in assignedJoints:
            continue
        if componentIndex in assignedComponents:
            continue
        assignedJoints.add(joint)
        assignedComponents.add(componentIndex)
        assignments.append({
            "joint": joint,
            "componentIndex": componentIndex,
            "component": components[componentIndex],
            "distance": distance
        })
        if len(assignedJoints) == len(joints):
            break
        if len(assignedComponents) == len(components):
            break
    return assignments

def BindJointComponents(mesh, joints):
    if not cmds.objExists(mesh):
        return
    joints = [joint for joint in joints if cmds.objExists(joint)]
    if not joints:
        return
    skinCluster = GetSkinCluster(mesh)
    if not skinCluster:
        skinCluster = cmds.skinCluster(joints,mesh,toSelectedBones=True,bindMethod=0,normalizeWeights=1,maximumInfluences=4,obeyMaxInfluences=False)[0]
    else:
        influences = cmds.skinCluster(skinCluster,query=True,influence=True) or []
        for joint in joints:
            if joint in influences:
                continue
            cmds.skinCluster(skinCluster,edit=True,addInfluence=joint,weight=0.0,lockWeights=False)
    assignments = AssignComponentsToJoints(mesh,joints)
    for assignment in assignments:
        joint = assignment["joint"]
        component = assignment["component"]
        distance = assignment["distance"]
        vertices = ["{}.vtx[{}]".format(mesh,vertexID) for vertexID in component]
        cmds.skinPercent(skinCluster,vertices,transformValue=[(joint, 1.0)],normalize=True)
    return skinCluster

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def BuildSkinJointToNearestComponent(datas):
    """Assign mesh islands to nearby joints and bind their skin weights."""
    if not datas:
        return
    for item in datas:
        # Find the mesh and saved joint set for each island assignment.
        mesh = item["mesh"]
        joints = [joint.strip() for joint in item["joints"].splitlines() if joint.strip()]
        BindJointComponents(mesh, joints)


def Run(data, *args):
    return BuildSkinJointToNearestComponent(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("SkinJointToNearestComponent Export: no saved items")
        return None

    # Inline all native Maya mesh helpers used by Run.
    helpers = (
        GetSkinCluster, GetMeshPath, GetMeshComponents,
        GetWorldVertexPositions, GetJointWorldPosition,
        GetClosestDistanceToComponent, AssignComponentsToJoints,
        BindJointComponents, BuildSkinJointToNearestComponent,
    )
    code = "\n\n".join(inspect.getsource(helper).rstrip() for helper in helpers)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    rows = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    # SkinJointToNearestComponent data\n"
        "    SKIN_DATA = " + rows + "\n\n"
        + code
        + "\n\n    # Bind each mesh component to its closest available joint.\n"
        + "    BuildSkinJointToNearestComponent(SKIN_DATA)\n\n"
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

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--

    cmds.textField(text='Mesh',editable=False)
    itemData['mesh'] = cmds.textField(text=data.get("mesh", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['mesh']))
    cmds.setParent("..")

    cmds.textField(text='Joints',editable=False)
    itemData['joints'] = cmds.scrollField(wordWrap=True,height=300,text=data.get("joints", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['joints']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['joints']))
    cmds.setParent("..")

    cmds.setParent("..") #--
    cmds.rowColumnLayout(nc=4)
    cmds.button(label="X",width=90,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.setParent("..")
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










