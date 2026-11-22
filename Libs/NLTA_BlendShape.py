import os
import json
import importlib
import maya.cmds as cmds
import maya.mel as mel
import pymel.core as pm
import maya.api.OpenMaya as om

import NLTA_General,NLTA_OpenMaya,NLTA_Mesh
for module in [NLTA_General,NLTA_OpenMaya,NLTA_Mesh]:
    try:
        importlib.reload(module)
    except:
        reload(module)

def ImportBlendShape(*arr):
    folder_temp = os.path.dirname(pm.sceneName())
    if not folder_temp:
        folder_temp = mel.eval("SaveSceneAs;")
    folder_temp = os.path.dirname(pm.sceneName())
    jsonPath = folder_temp+'/BlendShapeData.json'
    data = NLTA_General.readJsonFile(jsonPath)
    if data:
        for entry in data:
            base_mesh = entry["mesh"]
            targets = entry["targets"]
            target_meshes = [t["target_mesh"] for t in targets]
            bs_node = cmds.blendShape(
                target_meshes,
                base_mesh,
                name=entry["BS"]
            )[0]
            for i, t in enumerate(targets):
                alias_list = cmds.aliasAttr(bs_node, q=True) or []
                alias_dict = {alias_list[i+1]: alias_list[i] for i in range(0, len(alias_list), 2)}
                plug_name = "weight[%s]" % i
                if plug_name in alias_dict:
                    cmds.aliasAttr(bs_node+'.'+alias_dict[plug_name], remove=True)
                cmds.aliasAttr(t["name"], "%s.w[%s]" % (bs_node, i))
                cmds.setAttr("%s.%s" % (bs_node, t["name"]), t["value"])

def GetBSSingle(mesh):
    history = cmds.listHistory(mesh)
    BS = cmds.ls(history, type="blendShape")
    if not BS:
        return
    BSNode = BS[0]
    attrs = cmds.listAttr(BSNode + '.w', m=True) or []
    alias_list = cmds.aliasAttr(BSNode, q=True) or []
    alias_dict = {}
    for i in range(0, len(alias_list), 2):
        name = alias_list[i]
        plug = alias_list[i+1]
        index = int(plug.split("[")[1].split("]")[0])
        alias_dict[name] = index    
    data = {
        "mesh": mesh,
        "BS": BSNode,
        "targets": []
    }

    for attr in attrs:
        index = alias_dict.get(attr)
        if index is None:
            continue
        targetMeshes = cmds.blendShape(BSNode, q=True, target=True) or []
        if index >= len(targetMeshes):
            continue    
        targetMesh = targetMeshes[index]
        value = cmds.getAttr("%s.%s" % (BSNode, attr))
        data["targets"].append({
            "name": attr,
            "target_mesh": targetMesh,
            "value": value
        })
    return(data)

def GetAllBSData():    
    data = []    
    meshs = list(set(cmds.listRelatives(cmds.ls(type="mesh"),parent=True)))
    for mesh in meshs:
        if GetBSSingle(mesh) != None:
            data.append(GetBSSingle(mesh))
    return(data)


def ExportBlendShape(*arr):
    folder_temp = os.path.dirname(pm.sceneName())
    if not folder_temp:
        folder_temp = mel.eval("SaveSceneAs;")
    folder_temp = os.path.dirname(pm.sceneName())
    if folder_temp:
        jsonPath = folder_temp+'/BlendShapeData.json'
        BSData = GetAllBSData()
        NLTA_General.writeJsonFile(jsonPath,BSData)
        cmds.warning("Done!!!")

def ExportBSToXML(*arr):
    folder_temp = os.path.dirname(pm.sceneName())
    if not folder_temp:
        folder_temp = mel.eval("SaveSceneAs;")
    folder_temp = os.path.dirname(pm.sceneName())
    if folder_temp:
        jsonPath = folder_temp+'/BlendShapeData.xml'
        BSData = GetAllBSData()
        root = ET.Element("Meshes")
        for item in BSData:
            mesh_elem = ET.SubElement(root, "Mesh", name=item.get("mesh", ""), BS=item.get("BS", ""))
            for target in item.get("targets", []):
                ET.SubElement(
                    mesh_elem,
                    "Target",
                    name=target.get("name", ""),
                    target_mesh=target.get("target_mesh", ""),
                    value=str(target.get("value", "0.0"))
                )
        tree = ET.ElementTree(root)
        tree.write(jsonPath, encoding="utf-8", xml_declaration=True)
        print("XML file saved to: %s" % jsonPath)

def ExportVertexsPositionSingle(mesh, jsonPath, space='world'):
    dag = NLTA_OpenMaya.GetDagPath(mesh)
    fn_mesh = om.MFnMesh(dag)

    space_enum = om.MSpace.kWorld if space == 'world' else om.MSpace.kObject
    pts = fn_mesh.getPoints(space_enum)
    positions = [[p.x, p.y, p.z] for p in pts]
    vcount = fn_mesh.numVertices
    folder = os.path.dirname(jsonPath)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    data = {
        "mesh": mesh,
        "space": space,
        "vertexCount": vcount,
        "positions": positions
    }
    with open(jsonPath, "w") as f:
        json.dump(data, f, indent=2)

def ExportVertexsPosition(*arr):
    folder_temp = os.path.dirname(pm.sceneName())
    if not folder_temp:
        folder_temp = mel.eval("SaveSceneAs;")
    folderTemp = os.path.dirname(pm.sceneName())
    if folderTemp:
        exportPath = folderTemp+"/VertexsPosition/"
        objs = cmds.ls(selection=True)
        for obj in objs:
            ExportVertexsPositionSingle(obj,exportPath+obj+'.json')

    print("Export Vertexs Done!~")

def ImportVertexsPositionSingle(json_path, target_mesh=None, space_override=None):
    with open(json_path, "r") as f:
        data = json.load(f)

    mesh = target_mesh or data.get("mesh")
    if not mesh:
        raise RuntimeError("JSON haven't include mesh name and you didn't paste 'target_mesh'.")
    if cmds.objExists(mesh):
        dag = NLTA_OpenMaya.GetDagPath(mesh)
        fn_mesh = om.MFnMesh(dag)

        positions = data.get("positions")
        vcount_json = data.get("vertexCount")
        vcount_scene = fn_mesh.numVertices

        if vcount_json != vcount_scene:
            raise RuntimeError("Vertex count not match: file={} vs scene={}".format(vcount_json, vcount_scene))
        if not positions or len(positions) != vcount_scene:
            raise RuntimeError("Data 'positions' trong JSON incorrect.")

        
        file_space = data.get("space", "world")
        space = space_override or file_space
        space_enum = om.MSpace.kWorld if space == 'world' else om.MSpace.kObject


        mpoints = om.MPointArray()
        for x, y, z in positions:
            mpoints.append(om.MPoint(x, y, z))


        fn_mesh.setPoints(mpoints, space_enum)

        print(">> Import xong vertex positions into '{}' ({} space) from {}".format(mesh, space, json_path))
        return mesh

def ImportVertexsPositionSingle(jsonPath, targetMesh=None, spaceOverride=None):
    if not os.path.isfile(jsonPath):
        raise RuntimeError("File not found: {}".format(jsonPath))

    with open(jsonPath, "r") as f:
        data = json.load(f)

    mesh = targetMesh or data.get("mesh")
    if not mesh or not cmds.objExists(mesh):
        raise RuntimeError("Mesh not found: {}".format(mesh))

    dag = NLTA_OpenMaya.GetDagPath(mesh)
    fnMesh = om.MFnMesh(dag)

    positions = data.get("positions", [])
    fileCount = data.get("vertexCount")
    sceneCount = fnMesh.numVertices

    if fileCount != sceneCount:
        raise RuntimeError(
            "Vertex count not match: {} file={} scene={}".format(
                mesh, fileCount, sceneCount
            )
        )

    if len(positions) != sceneCount:
        raise RuntimeError(
            "Positions count not match: {} vs {}".format(
                len(positions), sceneCount
            )
        )

    space = spaceOverride or data.get("space", "world")
    spaceEnum = om.MSpace.kWorld if space == "world" else om.MSpace.kObject

    points = om.MPointArray()
    for pos in positions:
        points.append(om.MPoint(pos[0], pos[1], pos[2]))

    fnMesh.setPoints(points, spaceEnum)

    print("Import Vertex Positions: {}".format(mesh))
    return mesh


def ImportVertexsPosition(*arr):
    scenePath = pm.sceneName()

    if not scenePath:
        cmds.warning("Please save scene first.")
        return

    folder = os.path.join(
        os.path.dirname(scenePath),
        "VertexsPosition"
    )

    if not os.path.isdir(folder):
        cmds.warning("VertexsPosition folder not found: {}".format(folder))
        return

    objs = cmds.ls(selection=True, long=False)

    if not objs:
        cmds.warning("Please select mesh.")
        return

    for obj in objs:
        filePath = os.path.join(folder, obj + ".json")

        if os.path.isfile(filePath):
            ImportVertexsPositionSingle(
                filePath,
                targetMesh=obj
            )
        else:
            cmds.warning("Vertex position file not found: {}".format(filePath))

    print("Import Vertexs Done!~")

def CreatePromixityWrap():
    sel = cmds.ls(sl=True)
    driven = sel[0]
    driver = sel[1]

    prox = cmds.deformer(driven, type="proximityWrap")[0]
    driverShape = cmds.listRelatives(driver, s=True, ni=True, f=True)[0]

    cmds.proximityWrap(
        prox,
        e=True,
        addDrivers=[driverShape]
    )

    return prox