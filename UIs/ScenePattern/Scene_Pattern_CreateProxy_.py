import os
import inspect
import ast
import maya.mel as mel
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
from datetime import datetime

import NLTA_General,NLTA_UI,NLTA_Skinning
for module in [NLTA_General,NLTA_UI,NLTA_Skinning]:
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
    name = "Create Proxy"
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

    cmds.rowColumnLayout(numberOfColumns=3,parent=buttonUI)
    cmds.button(label="Add",width=130,c=partial(Add,listUI,{}))
    cmds.button(label="Save", width=130,c=partial(Save,data))
    cmds.button(label="Run",width=105,c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=105,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.setParent("..")
    Load(data,listUI)

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def _proxy_get_skin_data(node=None):
    if node is None:
        selection = cmds.ls(sl=True, fl=True) or []
        node = selection[0] if selection else None

    if not node:
        return {"mesh": None, "skinCluster": None, "joints": []}

    node = node.split(".")[0]
    if not cmds.objExists(node) or cmds.nodeType(node) == "joint":
        return {"mesh": None, "skinCluster": None, "joints": []}

    nodeType = cmds.nodeType(node)
    if nodeType == "mesh":
        shape = node
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        mesh = parents[0] if parents else node
    else:
        mesh = node
        shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True) or []
        shape = next((item for item in shapes if cmds.nodeType(item) == "mesh"), None)

    if not shape:
        return {"mesh": None, "skinCluster": None, "joints": []}

    skins = cmds.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster") or []
    if not skins:
        return {"mesh": None, "skinCluster": None, "joints": []}

    skin = skins[0]
    return {
        "mesh": mesh,
        "skinCluster": skin,
        "joints": cmds.skinCluster(skin, q=True, inf=True) or [],
    }


def _proxy_get_skin_cluster(node):
    if not node or not cmds.objExists(node.split(".")[0]):
        return None
    return _proxy_get_skin_data(node)["skinCluster"]


def _proxy_get_dag_path(obj):
    sel = om.MSelectionList()
    sel.add(obj)
    return sel.getDagPath(0)


def _proxy_get_skin_api(mesh, skinCluster=None):
    skinCluster = skinCluster or _proxy_get_skin_cluster(mesh)
    if not skinCluster:
        return None, None, None

    dagPath = _proxy_get_dag_path(mesh)
    sel = om.MSelectionList()
    sel.add(skinCluster)
    return dagPath, oma.MFnSkinCluster(sel.getDependNode(0)), skinCluster


def _proxy_create_vertex_component(vertexIds):
    compFn = om.MFnSingleIndexedComponent()
    comp = compFn.create(om.MFn.kMeshVertComponent)
    compFn.addElements(vertexIds)
    return comp


def _proxy_bind_skin(*arr):
    joints = cmds.ls(sl=True, type="joint")
    meshs = []
    for obj in cmds.ls(sl=True, type="transform"):
        shapes = cmds.listRelatives(obj, s=True, ni=True) or []
        if not shapes:
            continue
        if cmds.nodeType(shapes[0]) == "mesh":
            meshs.append(obj)
    for mesh in meshs:
        cmds.select(mesh)
        cmds.select(joints,add=True)
        cmds.skinCluster(
            joints,
            mesh,
            toSelectedBones=True,
            bindMethod=3,
            normalizeWeights=1,
            weightDistribution=0,
            mi=4,
            dr=4,
            rui=False
        )
        #pm.mel.eval('newSkinCluster "-toSelectedBones -bindMethod 3  -normalizeWeights 1 -weightDistribution 0 -mi 4  -dr 4 -rui false    -heatmapFalloff 0.2 -geodesicResolution 256 -geodesicPostVoxelCheck 1, multipleBindPose, 0";')


def _proxy_remove_unused_joint(*arr):
    cmds.currentTime(0)
    selection = cmds.ls(sl=True, long=True) or []
    if selection:
        transforms = list(dict.fromkeys(item.split(".")[0] for item in selection))
    else:
        transforms = cmds.listRelatives(cmds.ls(type="mesh", noIntermediate=True), parent=True, fullPath=True) or []
        transforms = list(dict.fromkeys(transforms))

    removed = {}
    for transform in transforms:
        dagPath, skinFn, skin = _proxy_get_skin_api(transform)
        if skinFn is None:
            continue

        influences = skinFn.influenceObjects()
        if len(influences) <= 1:
            continue

        vertexCount = om.MFnMesh(dagPath).numVertices
        component = _proxy_create_vertex_component(list(range(vertexCount)))
        weights, influenceCount = skinFn.getWeights(dagPath, component)

        used = [False] * influenceCount
        for vertexIndex in range(vertexCount):
            offset = vertexIndex * influenceCount
            for influenceIndex in range(influenceCount):
                if not used[influenceIndex] and weights[offset + influenceIndex] > 0.0:
                    used[influenceIndex] = True

        removeJoints = [
            influences[i].partialPathName()
            for i, isUsed in enumerate(used)
            if not isUsed
        ]

        # Keep at least one influence.
        if len(removeJoints) >= len(influences):
            removeJoints = removeJoints[:-1]

        for joint in removeJoints:
            if cmds.objExists(joint):
                cmds.skinCluster(skin, e=True, removeInfluence=joint)

        if removeJoints:
            removed[transform] = removeJoints
            print("Remove Joint " + " - ".join(removeJoints))

    if transforms:
        existing = [transform for transform in transforms if cmds.objExists(transform)]
        if existing:
            cmds.select(existing, r=True)

    cmds.warning("Done!!!")
    return removed


def BuildProxyLegacy(datas):
    """Preserve the original face-selection, binding and unused influence removal."""
    if not datas:
        return
    for proxyData in datas:
        faces = proxyData.get("faces", "").splitlines()
        name = proxyData.get("name", "")
        contain = proxyData.get("contain", "")
        faces = [x.strip() for x in faces if x.strip()]
        if not faces:
            continue

        meshTransform = faces[0].split(".")[0]
        if not cmds.objExists(meshTransform):
            cmds.warning("Mesh does not exist: " + meshTransform)
            continue

        # Create contain group if needed
        if contain and not cmds.objExists(contain):
            contain = cmds.group(empty=True, name=contain)

        # Get skin info
        skinCluster = mel.eval("findRelatedSkinCluster " + meshTransform)
        joints = []
        if skinCluster:
            joints = cmds.skinCluster(skinCluster, query=True, inf=True) or []

        # Duplicate original mesh
        meshNew = cmds.duplicate(meshTransform, name=name)[0]

        # Convert original face names -> duplicated mesh face names
        proxyFaces = []
        for face in faces:
            faceId = face.split(".f[")[-1]
            proxyFaces.append(meshNew + ".f[" + faceId)

        # Keep only requested faces
        allFaces = cmds.ls(meshNew + ".f[*]", flatten=True) or []

        cmds.select(allFaces, replace=True)
        cmds.select(proxyFaces, deselect=True)
        cmds.delete()

        cmds.delete(meshNew, constructionHistory=True)

        # Rebind + copy skin
        if skinCluster and joints:
            cmds.select(joints, replace=True)
            cmds.select(meshNew, add=True)
            _proxy_bind_skin()

            newSkinCluster = mel.eval("findRelatedSkinCluster " + meshNew)

            if newSkinCluster:
                mel.eval(
                    'copySkinWeights '
                    '-ss "{0}" '
                    '-ds "{1}" '
                    '-noMirror '
                    '-surfaceAssociation closestPoint '
                    '-influenceAssociation closestJoint;'.format(
                        skinCluster,
                        newSkinCluster
                    )
                )
        cmds.select(meshNew)        
        _proxy_remove_unused_joint()

        # Parent into contain
        if contain:
            cmds.parent(meshNew, contain)

        # Hide proxy
        cmds.setAttr(meshNew + ".visibility", 0)

    cmds.select(clear=True)
    cmds.warning("Proxy creation done!")


def Run(data, *arr):
    return BuildProxyLegacy(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("CreateProxy_ Export: no saved items")
        return None

    # Export the exact helper code that the edited Run uses.
    helpers = (_proxy_get_skin_data, _proxy_get_skin_cluster, _proxy_get_dag_path, _proxy_get_skin_api, _proxy_create_vertex_component, _proxy_bind_skin, _proxy_remove_unused_joint, BuildProxyLegacy)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in helpers))
    code = ast.unparse(tree)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    embedded = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.mel as mel\n"
        "    import maya.api.OpenMaya as om\n"
        "    import maya.api.OpenMayaAnim as oma\n\n"
        "    # CreateProxy_ data\n"
        "    PROXY_DATA = " + embedded + "\n\n"
        + "    # Original native Maya skin and proxy helpers.\n"
        + code
        + "\n\n    # Build only when explicitly executed.\n"
        + "    BuildProxyLegacy(PROXY_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in script:
        script = script.replace("\n\n\n", "\n\n")
    name = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, name, "exec")
    output = os.path.join(os.path.dirname(path), name)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(script)
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
    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--

 
    cmds.textField(text="Faces",editable=False)
    itemData["faces"] = cmds.scrollField(text=data.get("faces",""),h=80)
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData["faces"]))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData["faces"]))
    cmds.setParent("..")
    cmds.textField(text="Name",editable=False)
    itemData["name"] = cmds.textField(text=data.get("name",""))
    cmds.text(label="")

    cmds.textField(text="Contain",editable=False)
    itemData["contain"] = cmds.textField(text=data.get("contain",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["contain"]))


    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










