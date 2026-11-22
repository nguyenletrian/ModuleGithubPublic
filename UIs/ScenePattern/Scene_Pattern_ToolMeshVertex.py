import os
import inspect
import ast
import maya.api.OpenMaya as om
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
from datetime import datetime

import NLTA_General,NLTA_UI,NLTA_Mesh
for module in [NLTA_General,NLTA_UI,NLTA_Mesh]:
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
    name = "Mesh Vertex"
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
    export_button = cmds.button(label="Export Py",width=110,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.button(label="Get Topo pair",w=35,c=partial(GetTopoPair,data))
    cmds.button(label="Get Mirror pair",w=35)
    cmds.setParent("..")
    Load(data,listUI)

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def _mv_get_id(component):
    if isinstance(component, (int, float)):
        return int(component)
    return int(component.rsplit("[", 1)[-1].split("]", 1)[0])


def _mv_get_dag_path(obj):
    sel = om.MSelectionList()
    sel.add(obj)
    return sel.getDagPath(0)


def _mv_get_mesh_data(mesh):
    dag = _mv_get_dag_path(mesh)
    return {"dag": dag, "fn": om.MFnMesh(dag)}


def _mv_get_mesh_fn(mesh):
    return _mv_get_mesh_data(mesh)["fn"]


def _mv_symmetry_plane(mesh, pairs):
    if len(pairs) != 3:
        raise ValueError("Exactly 3 vertex pairs are required.")

    meshFn = _mv_get_mesh_fn(mesh)
    midpoints = []

    for vertexA, vertexB in pairs:
        pointA = meshFn.getPoint(vertexA, om.MSpace.kWorld)
        pointB = meshFn.getPoint(vertexB, om.MSpace.kWorld)
        midpoints.append(om.MPoint(
            (pointA.x + pointB.x) * 0.5,
            (pointA.y + pointB.y) * 0.5,
            (pointA.z + pointB.z) * 0.5
        ))

    p0, p1, p2 = midpoints
    normal = (p1 - p0) ^ (p2 - p0)

    if normal.length() < 1e-8:
        raise ValueError("The 3 midpoint positions are collinear. Cannot determine symmetry plane.")

    normal.normalize()
    return p0, normal


def _mv_mirror_point(point, planePoint, planeNormal):
    vector = point - planePoint
    distance = vector * planeNormal
    return point - (planeNormal * (2.0 * distance))


def _mv_find_pairs(mesh, vertsA, vertsB):
    if len(vertsA) != 3 or len(vertsB) != 3:
        raise ValueError("Exactly 3 vertices are required on each component.")
    if set(vertsA) & set(vertsB):
        raise ValueError("vertsA and vertsB must belong to different components.")

    # ---------------------------------------------------------
    # Get mesh
    # ---------------------------------------------------------

    sel = om.MSelectionList()
    sel.add(mesh)
    path = sel.getDagPath(0)
    fn = om.MFnMesh(path)

    # ---------------------------------------------------------
    # Build vertex -> faces
    # ---------------------------------------------------------

    vertexFaces = {}
    it = om.MItMeshVertex(path)
    for vertexID in range(fn.numVertices):
        it.setIndex(vertexID)
        vertexFaces[vertexID] = set(it.getConnectedFaces())

    # ---------------------------------------------------------
    # Find common face
    # ---------------------------------------------------------

    def FindCommonFace(vertices):
        common = set(vertexFaces[vertices[0]])
        for vertex in vertices[1:]:
            common &= vertexFaces[vertex]
        if not common:
            return None
        return next(iter(common))
    faceA = FindCommonFace(vertsA)
    faceB = FindCommonFace(vertsB)

    if faceA is None:
        raise ValueError("vertsA are not on the same face.")

    if faceB is None:
        raise ValueError("vertsB are not on the same face.")

    # ---------------------------------------------------------
    # Find center vertex
    #
    # The 3 selected vertices must form 2 connected edges.
    # ---------------------------------------------------------
    def FindCenterVertex(faceID, vertices):
        faceVertices = list(fn.getPolygonVertices(faceID))
        count = len(faceVertices)
        for vertex in vertices:
            index = faceVertices.index(vertex)
            prevVertex = faceVertices[(index - 1) % count]
            nextVertex = faceVertices[(index + 1) % count]
            others = [v for v in vertices if v != vertex]
            if (others[0] in (prevVertex, nextVertex) and others[1] in (prevVertex, nextVertex)):
                return vertex
        return None

    centerA = FindCenterVertex(faceA, vertsA)
    centerB = FindCenterVertex(faceB, vertsB)
    if centerA is None or centerB is None:
        raise ValueError(
            "Each group of 3 vertices must form "
            "2 connected edges on the same face."
        )

    # ---------------------------------------------------------
    # Get connected component
    # ---------------------------------------------------------

    def GetComponent(startVertex):
        component = set()
        stack = [startVertex]
        it = om.MItMeshVertex(path)
        while stack:
            vertex = stack.pop()
            if vertex in component:
                continue
            component.add(vertex)
            it.setIndex(vertex)
            for neighbor in it.getConnectedVertices():
                if neighbor not in component:
                    stack.append(neighbor)
        return component
    componentA = GetComponent(centerA)
    componentB = GetComponent(centerB)

    # Verify seeds
    if not all(vertex in componentA for vertex in vertsA):
        raise ValueError("vertsA are not in the same component.")

    if not all( vertex in componentB for vertex in vertsB):
        raise ValueError("vertsB are not in the same component.")

    if len(componentA) != len(componentB):
        raise ValueError(
            "The two components have different vertex counts: "
            "{} vs {}".format(
                len(componentA),
                len(componentB)
            )
        )

    # ---------------------------------------------------------
    # Build face -> vertices
    # ---------------------------------------------------------

    faceVertices = {}
    componentFacesA = set()
    componentFacesB = set()

    for vertex in componentA:
        componentFacesA.update(vertexFaces[vertex])

    for vertex in componentB:
        componentFacesB.update(vertexFaces[vertex])

    for faceID in componentFacesA | componentFacesB:
        faceVertices[faceID] = list(fn.getPolygonVertices(faceID))

    # ---------------------------------------------------------
    # Initial vertex mapping
    # ---------------------------------------------------------

    mapping = {}
    reverseMapping = {}
    for a, b in zip(vertsA, vertsB):

        if a in mapping and mapping[a] != b:
            raise ValueError("Conflicting mapping on component A.")

        if b in reverseMapping and reverseMapping[b] != a:
            raise ValueError("Conflicting mapping on component B.")
        mapping[a] = b
        reverseMapping[b] = a

    # ---------------------------------------------------------
    # Initial face mapping
    # ---------------------------------------------------------

    faceMapping = {faceA: faceB}
    reverseFaceMapping = {faceB: faceA}

    # ---------------------------------------------------------
    # Map a face using cyclic topology
    # ---------------------------------------------------------

    def MapFace(sourceFace, targetFace):
        source = faceVertices[sourceFace]
        target = faceVertices[targetFace]
        if len(source) != len(target):
            raise RuntimeError("Face topology mismatch: {} -> {}".format(sourceFace,targetFace))
        count = len(source)
        candidates = []
        # -----------------------------------------------------
        # Try both winding directions and all cyclic offsets.
        # -----------------------------------------------------
        for reverse in (False, True):
            sourceOrder = (list(reversed(source)) if reverse else source)
            for offset in range(count):
                candidate = []
                valid = True
                for i in range(count):
                    vertexA = sourceOrder[i]
                    vertexB = target[ (i + offset) % count ]
                    if vertexA in mapping:
                        if mapping[vertexA] != vertexB:
                            valid = False
                            break
                    if vertexB in reverseMapping:
                        if reverseMapping[vertexB] != vertexA:
                            valid = False
                            break
                    candidate.append((vertexA, vertexB))
                if valid:
                    candidates.append(candidate)

        if not candidates:
            raise RuntimeError("Cannot map face {} -> {}.".format(sourceFace,targetFace))

        # -----------------------------------------------------
        # If there is more than one valid solution, topology
        # alone cannot distinguish them.
        # -----------------------------------------------------
        if len(candidates) > 1:
            raise RuntimeError(
                "Ambiguous topology between face {} and {}. "
                "The selected 3 vertices are not enough "
                "to uniquely determine the symmetry.".format(
                    sourceFace,
                    targetFace
                )
            )

        candidate = candidates[0]
        for vertexA, vertexB in candidate:
            if vertexA not in mapping:
                mapping[vertexA] = vertexB
                reverseMapping[vertexB] = vertexA

    # ---------------------------------------------------------
    # Find target face from mapped vertices
    # ---------------------------------------------------------

    def FindMatchingFace(sourceFace):
        sourceVertices = faceVertices[sourceFace]
        mappedVertices = []
        for vertexA in sourceVertices:
            if vertexA in mapping:
                mappedVertices.append(mapping[vertexA])

        if len(mappedVertices) < 2:
            return None
        candidates = None
        for vertexB in mappedVertices:
            faces = ( vertexFaces[vertexB] & componentFacesB)
            if candidates is None:
                candidates = set(faces)
            else:
                candidates &= faces

        if not candidates:
            return None

        for targetFace in candidates:
            if targetFace in reverseFaceMapping:
                continue
            targetVertices = set(faceVertices[targetFace])
            if all(vertexB in targetVertices for vertexB in mappedVertices):
                return targetFace
        return None

    # ---------------------------------------------------------
    # Traverse from component A to component B
    # ---------------------------------------------------------

    processedFaces = set()
    while True:
        progress = False
        for sourceFace in list(faceMapping.keys()):
            if sourceFace in processedFaces:
                continue
            targetFace = faceMapping[sourceFace]
            # Map vertices of this face
            MapFace(sourceFace,targetFace)
            processedFaces.add(sourceFace)
            progress = True
            # Find neighboring faces
            sourceVertices = faceVertices[sourceFace]
            for vertexA in sourceVertices:
                if vertexA not in mapping:
                    continue
                for nextFaceA in vertexFaces[vertexA]:
                    if nextFaceA not in componentFacesA:
                        continue
                    if nextFaceA in faceMapping:
                        continue
                    nextFaceB = FindMatchingFace(nextFaceA)
                    if nextFaceB is None:
                        continue
                    if nextFaceB in reverseFaceMapping:
                        continue
                    faceMapping[nextFaceA] = nextFaceB
                    reverseFaceMapping[nextFaceB] = nextFaceA
                    progress = True
        if not progress:
            break

    # ---------------------------------------------------------
    # Validate
    # ---------------------------------------------------------

    missingA = [vertex for vertex in componentA if vertex not in mapping ]
    if missingA:
        raise RuntimeError(
            "Could not match entire component. "
            "{} vertices remain.".format(
                len(missingA)
            )
        )
    # Make sure every target vertex was mapped
    if len(mapping) != len(componentA):
        raise RuntimeError("Mapping count mismatch.")

    return [
        (vertexA, mapping[vertexA])
        for vertexA in sorted(componentA)
    ]


def _mv_mirror_positions(mesh, pairs):
    if not pairs:
        return
    if len(pairs) < 3:
        raise ValueError("At least 3 vertex pairs are required.")

    planePoint, planeNormal = _mv_symmetry_plane(mesh, pairs[:3])
    meshFn = _mv_get_mesh_fn(mesh)
    points = meshFn.getPoints(om.MSpace.kWorld)

    for vertexA, vertexB in pairs:
        points[vertexB] = _mv_mirror_point(points[vertexA], planePoint, planeNormal)

    meshFn.setPoints(points, om.MSpace.kWorld)
    meshFn.updateSurface()


def BuildMeshVertexPairs(datas):
    """Match two topology components and mirror their vertex positions."""
    if datas:
        for i in range(len(datas)):
            data = datas[i]
            sources = data['sources'].split("\n")
            targets = data['targets'].split("\n")
            mesh = (sources[0].split("."))[0]
            sourceVerts = []
            targetVerts = []
            for i in range(len(sources)):
                sourceVerts.append(int(_mv_get_id(sources[i])))
                targetVerts.append(int(_mv_get_id(targets[i])))
            pairs = _mv_find_pairs(mesh,sourceVerts,targetVerts)
            stringTemp = 'cmds.select("'+mesh+'.vtx[{}]","'+mesh+'.vtx[{}]")'
            for pair in pairs:
                print(stringTemp.format(pair[0],pair[1]))
            _mv_mirror_positions(mesh,pairs)


def Run(data, *arr):
    return BuildMeshVertexPairs(NLTA_General.readJsonFile(_pattern_data_path(data)))


def GetTopoPair(data, *arr):
    return Run(data, *arr)


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("MeshVertex Export: no saved items")
        return None

    functions = (_mv_get_id, _mv_get_dag_path, _mv_get_mesh_data, _mv_get_mesh_fn, _mv_symmetry_plane, _mv_mirror_point, _mv_find_pairs, _mv_mirror_positions, BuildMeshVertexPairs)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions))
    body = ast.unparse(tree)
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    rows = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    # MeshVertex data\n"
        "    VERTEX_DATA = " + rows + "\n\n"
        + "    # Source mesh topology matching and mirrored point placement.\n"
        + body
        + "\n\n    # Mirror matching components from saved vertex seeds.\n"
        + "    BuildMeshVertexPairs(VERTEX_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in script:
        script = script.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(script)
    return output


def OpenExportFolder(data, *arr):
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

    cmds.textField(text='Sources',editable=False)
    itemData['sources'] = cmds.scrollField(wordWrap=True,height=80,text=data.get('sources', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['sources']))

    cmds.textField(text='Targets',editable=False)
    itemData['targets'] = cmds.scrollField(wordWrap=True,height=80,text=data.get('targets', ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['targets']))
    cmds.setParent("..")

    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))

    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










