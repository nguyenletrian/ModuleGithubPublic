import os
import inspect
import ast
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
    name = "Rig Basic"
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

def SaveGuideData(guide="NLTA_Guide"):
    if not cmds.objExists(guide):
        cmds.warning("Guide does not exist.")
        return

    dataNode = "NLTA_RigData"
    if cmds.objExists(dataNode):
        cmds.delete(dataNode)
    dataNode = cmds.createNode("network", n=dataNode)
    cmds.addAttr(dataNode, ln="GuideData", dt="string")

    # --------------------------------------------------
    # GUIDE SHAPES
    # --------------------------------------------------
    shapeDatas = []
    shapes = cmds.listRelatives(guide,s=True,ni=True,type="nurbsCurve",f=True) or []
    for shape in shapes:
        selection = om.MSelectionList()
        selection.add(shape)
        dagPath = selection.getDagPath(0)
        curveFn = om.MFnNurbsCurve(dagPath)
        cvs = curveFn.cvPositions(om.MSpace.kObject)
        knots = curveFn.knots()
        shapeDatas.append({"name": shape.split("|")[-1],"degree": curveFn.degree,"form": curveFn.form,"knots": list(knots),"cvs": [[p.x, p.y, p.z] for p in cvs]})

    # --------------------------------------------------
    # DATA
    # --------------------------------------------------
    data = {"version": 3,"guide": {"name": guide,"matrix": cmds.xform(guide, q=True, ws=True, m=True),"shapes": shapeDatas },"joints": [] }
    joints = cmds.listRelatives(guide,ad=True,type="joint",f=True) or []
    joints.reverse()

    # --------------------------------------------------
    # JOINTS
    # --------------------------------------------------
    for joint in joints:
        parent = cmds.listRelatives(joint,p=True,type="joint",f=True)
        jointData = {
            "name": joint.split("|")[-1],
            "parent": parent[0].split("|")[-1] if parent else None,
            "translate": list(cmds.getAttr(joint + ".translate")[0]),
            "rotate": list(cmds.getAttr(joint + ".rotate")[0]),
            "scale": list(cmds.getAttr(joint + ".scale")[0]),
            "jointOrient": list(cmds.getAttr(joint + ".jointOrient")[0]),
            "rotateAxis": list(cmds.getAttr(joint + ".rotateAxis")[0]),
            "rotateOrder": cmds.getAttr(joint + ".rotateOrder"),
            "segmentScaleCompensate": cmds.getAttr(
                joint + ".segmentScaleCompensate"
            ),
            "attrs": {}
        }

        for attr in ["NoJoint","NoControl","NoMirror"]:
            if cmds.attributeQuery(attr, node=joint, exists=True):
                jointData["attrs"][attr] = cmds.getAttr(joint + "." + attr)
        data["joints"].append(jointData)
    cmds.setAttr(dataNode + ".GuideData",json.dumps(data),type="string")
    return dataNode

def CreateJoint(*arr):
    selection = cmds.ls(selection=True)
    if len(selection) != 0:
        if cmds.objectType(selection[0]) == "mesh" or cmds.objectType(selection[0]) == "nurbsCurve":
            cluster_name = cmds.cluster()
            cmds.select(clear=True)
            joint_name = cmds.joint()
            cmds.matchTransform(joint_name, cluster_name, pos=True)
            cmds.delete(cluster_name)
        else:
            cmds.select(clear=True)
            joint_name = cmds.joint()
            cmds.select(clear=True)
            for i in selection:
                cmds.select(i, add=True)
                cmds.select(joint_name, add=True)
                pm.mel.eval('doCreateParentConstraintArgList 1 { "0","0","0","0","0","0","0","0","1","","1" };')
                contraint = pm.mel.eval('parentConstraint -weight 1;')
                cmds.delete(contraint)       
    else:
        cmds.joint(p=(0, 0, 0,))

def Freeze(*arr):
    list_ = cmds.ls(selection=True, type="transform")
    for i in list_:
        cmds.makeIdentity(i, apply=True, t=1, r=1, s=1, n=0)

def MatchThreeVertex(*arr):
    list_object = cmds.ls(fl=1, os=True)
    if len(list_object) != 3:
        print("Please select three vertex or three vertex and one object")
    else: 
        cluster_array = []
        joint_array = []
        for i in list_object:
            cmds.select(i)
            new_cluster = cmds.cluster()[1]
            cluster_array.append(new_cluster)
        for i in cluster_array:
            new_joint = cmds.joint(i)
            joint_array.append(new_joint)           
            cmds.parent(new_joint, w=True)
            cmds.matchTransform(new_joint, i, pos=True)
        cmds.select(joint_array[0])
        cmds.select(joint_array[1], add=True)
        pm.mel.eval('doCreateAimConstraintArgList 1 { "0","0","0","0","0","1","0","0","0","-1","0","0","1","1","object","' + joint_array[2] + '","0","0","0","","1" };')
        constraint_arm = pm.mel.eval('aimConstraint -offset 0 0 0 -weight 1 -aimVector 0 1 0 -upVector 0 0 -1 -worldUpType "object" -worldUpObject ' + joint_array[2] + ';')
        cmds.delete(constraint_arm)
        cmds.delete(cluster_array)
        cmds.delete(joint_array[0], joint_array[2])
        cmds.makeIdentity(joint_array[1], apply=True, t=1, r=1, s=1, n=0)


def AddGuide(*args):
    name = "NLTA_Guide"
    guide = cmds.circle(n=name, nr=(0, 1, 0), r=10, ch=False)[0]
    cmds.select(clear=True)
    joint = cmds.joint(n="Body")
    joint = cmds.parent(joint, guide)[0]
    cmds.setAttr(joint + ".translate", 0, 0, 0)
    cmds.setAttr(joint + ".rotate", 0, 0, 0)
    cmds.setAttr(joint + ".jointOrient", 90, 0, 90)
    cmds.select(guide)
    return guide

def AddAttribute(attrUI, *args):
    selected = cmds.ls(sl=True) or []
    if not selected:
        cmds.warning("Please select at least one object.")
        return
    attrType = cmds.optionMenu(attrUI, q=True, value=True)
    attrMap = {
        "NoControl": [
            {"name": "NoControl", "type": "bool", "default":True},
        ],
        "NoJoint": [
            {"name": "NoJoint", "type": "bool", "default":True},
        ],
        "NoMirror": [
            {"name": "NoMirror", "type": "bool", "default":True},
        ],
    }
    attrs = attrMap.get(attrType, [])
    if not attrs:
        cmds.warning("No attributes defined for: {}".format(attrType))
        return
    for obj in selected:
        for attr in attrs:
            name = attr["name"]
            if cmds.attributeQuery(name, node=obj, exists=True):
                continue
            if attr["type"] == "bool":
                cmds.addAttr(obj, ln=name, at="bool", dv=attr.get("default", False), k=True)
    print("Added {} attributes to: {}".format(attrType, ", ".join(selected)))

# ============================================================
# SKIN DATA
# ============================================================

def GetSkinCluster(mesh):
    history = cmds.listHistory(mesh) or []
    skins = cmds.ls(history, type="skinCluster") or []
    return skins[0] if skins else None


def GetSkinFolder():
    return os.path.join(
        cmds.internalVar(userTmpDir=True),
        "NLTA_RigBasicSkin"
    )


def ExportSkinData():
    dataNode = "NLTA_SkinData"
    skinFolder = GetSkinFolder()

    if cmds.objExists(dataNode):
        cmds.delete(dataNode)

    if os.path.exists(skinFolder):
        import shutil
        shutil.rmtree(skinFolder)

    os.makedirs(skinFolder)

    if not cmds.objExists("Geo"):
        return

    meshShapes = cmds.listRelatives(
        "Geo",
        ad=True,
        type="mesh",
        f=True
    ) or []

    data = {}

    for shape in meshShapes:
        parent = cmds.listRelatives(
            shape,
            p=True,
            f=True
        )

        if not parent:
            continue

        mesh = parent[0]
        skin = GetSkinCluster(mesh)

        if not skin:
            continue

        meshName = mesh.split("|")[-1]

        influences = cmds.skinCluster(
            skin,
            q=True,
            inf=True
        ) or []

        influences = [
            j.split("|")[-1]
            for j in influences
        ]

        fileName = meshName + ".xml"

        cmds.deformerWeights(
            fileName,
            export=True,
            deformer=skin,
            path=skinFolder
        )

        data[meshName] = {
            "file": fileName,
            "skinCluster": skin.split("|")[-1],
            "influences": influences,
            "maxInfluences": cmds.getAttr(
                skin + ".maxInfluences"
            ),
            "normalizeWeights": cmds.getAttr(
                skin + ".normalizeWeights"
            )
        }

    dataNode = cmds.createNode(
        "network",
        n=dataNode
    )

    cmds.addAttr(
        dataNode,
        ln="SkinData",
        dt="string"
    )

    cmds.setAttr(
        dataNode + ".SkinData",
        json.dumps(data),
        type="string"
    )

    return dataNode


def ImportSkinData():
    dataNode = "NLTA_SkinData"
    skinFolder = GetSkinFolder()

    if not cmds.objExists(dataNode):
        return

    if not cmds.attributeQuery(
        "SkinData",
        node=dataNode,
        exists=True
    ):
        cmds.delete(dataNode)
        return

    text = cmds.getAttr(
        dataNode + ".SkinData"
    )

    if not text:
        cmds.delete(dataNode)
        return

    data = json.loads(text)

    for meshName, skinData in data.items():
        if not cmds.objExists(meshName):
            cmds.warning(
                "Mesh not found: {}".format(meshName)
            )
            continue

        influences = []

        for influence in skinData.get(
            "influences",
            []
        ):
            if cmds.objExists(influence):
                influences.append(influence)

        if not influences:
            cmds.warning(
                "No influences found for {}".format(meshName)
            )
            continue

        # --------------------------------------------------
        # REMOVE OLD SKIN
        # --------------------------------------------------

        oldSkin = GetSkinCluster(meshName)

        if oldSkin:
            try:
                cmds.skinCluster(
                    oldSkin,
                    e=True,
                    ub=True
                )
            except:
                try:
                    cmds.delete(oldSkin)
                except:
                    pass

        # --------------------------------------------------
        # CREATE NEW SKIN
        # --------------------------------------------------

        cmds.select(clear=True)

        skin = cmds.skinCluster(
            influences,
            meshName,
            tsb=True,
            mi=skinData.get(
                "maxInfluences",
                4
            ),
            nw=skinData.get(
                "normalizeWeights",
                1
            ),
            n=skinData.get(
                "skinCluster",
                meshName + "_SkinCluster"
            )
        )[0]

        # --------------------------------------------------
        # IMPORT WEIGHTS
        # --------------------------------------------------

        fileName = skinData.get("file")

        if not fileName:
            continue

        filePath = os.path.join(
            skinFolder,
            fileName
        )

        if not os.path.exists(filePath):
            cmds.warning(
                "Skin file not found: {}".format(filePath)
            )
            continue

        cmds.deformerWeights(
            fileName,
            im=True,
            deformer=skin,
            path=skinFolder,
            method="index"
        )

        try:
            cmds.skinCluster(
                skin,
                e=True,
                forceNormalizeWeights=True
            )
        except:
            pass

    # --------------------------------------------------
    # CLEAN SKIN DATA
    # --------------------------------------------------

    if cmds.objExists(dataNode):
        cmds.delete(dataNode)

    if os.path.exists(skinFolder):
        import shutil
        shutil.rmtree(skinFolder)




def SaveControlShapeData():
    dataNode = "NLTA_ControlShapeData"

    if cmds.objExists(dataNode):
        cmds.delete(dataNode)

    if not cmds.objExists("Motion"):
        return

    controls = ["Main"]
    controls += cmds.listRelatives(
        "Motion",
        ad=True,
        type="transform",
        f=True
    ) or []

    data = {}

    for ctrl in controls:
        if not cmds.objExists(ctrl):
            continue

        shapes = cmds.listRelatives(
            ctrl,
            s=True,
            ni=True,
            type="nurbsCurve",
            f=True
        ) or []

        if not shapes:
            continue

        ctrlName = ctrl.split("|")[-1]
        shapeDatas = []

        for shape in shapes:
            selection = om.MSelectionList()
            selection.add(shape)
            dagPath = selection.getDagPath(0)

            curveFn = om.MFnNurbsCurve(dagPath)
            cvs = curveFn.cvPositions(om.MSpace.kObject)
            knots = curveFn.knots()

            shapeDatas.append({
                "name": shape.split("|")[-1],
                "degree": curveFn.degree,
                "form": curveFn.form,
                "knots": list(knots),
                "cvs": [[p.x, p.y, p.z] for p in cvs],

                "color": {
                    "overrideEnabled": cmds.getAttr(shape + ".overrideEnabled"),
                    "overrideRGBColors": cmds.getAttr(shape + ".overrideRGBColors"),
                    "overrideColor": cmds.getAttr(shape + ".overrideColor"),
                    "overrideColorRGB": list(cmds.getAttr(shape + ".overrideColorRGB")[0]),
                }
            })

        data[ctrlName] = shapeDatas

    dataNode = cmds.createNode(
        "network",
        n=dataNode
    )

    cmds.addAttr(
        dataNode,
        ln="ShapeData",
        dt="string"
    )

    cmds.setAttr(
        dataNode + ".ShapeData",
        json.dumps(data),
        type="string"
    )

    return dataNode


def RestoreControlShapeData():
    dataNode = "NLTA_ControlShapeData"

    if not cmds.objExists(dataNode):
        return

    if not cmds.attributeQuery(
        "ShapeData",
        node=dataNode,
        exists=True
    ):
        cmds.delete(dataNode)
        return

    text = cmds.getAttr(
        dataNode + ".ShapeData"
    )

    if not text:
        cmds.delete(dataNode)
        return

    data = json.loads(text)

    for ctrlName, shapeDatas in data.items():
        if not cmds.objExists(ctrlName):
            continue

        # Delete default shapes
        oldShapes = cmds.listRelatives(
            ctrlName,
            s=True,
            ni=True,
            type="nurbsCurve",
            f=True
        ) or []

        if oldShapes:
            cmds.delete(oldShapes)

        ctrlSel = om.MSelectionList()
        ctrlSel.add(ctrlName)
        ctrlDag = ctrlSel.getDagPath(0)

        for shapeData in shapeDatas:
            cvs = [
                om.MPoint(*pos)
                for pos in shapeData["cvs"]
            ]

            curveFn = om.MFnNurbsCurve()

            shapeObj = curveFn.create(
                cvs,
                shapeData["knots"],
                shapeData["degree"],
                shapeData["form"],
                False,
                True,
                ctrlDag.node()
            )

            shapeFn = om.MFnDagNode(
                shapeObj
            )

            try:
                shapeFn.setName(
                    shapeData["name"]
                )
            except:
                pass

            shapeName = shapeFn.fullPathName()
            colorData = shapeData.get("color", {})

            if colorData:
                cmds.setAttr(
                    shapeName + ".overrideEnabled",
                    colorData.get("overrideEnabled", False)
                )

                cmds.setAttr(
                    shapeName + ".overrideRGBColors",
                    colorData.get("overrideRGBColors", False)
                )

                cmds.setAttr(
                    shapeName + ".overrideColor",
                    colorData.get("overrideColor", 0)
                )

                rgb = colorData.get("overrideColorRGB", [1, 1, 1])

                cmds.setAttr(
                    shapeName + ".overrideColorRGB",
                    rgb[0],
                    rgb[1],
                    rgb[2]
                )

    cmds.delete(dataNode)


# ============================================================
# RESTORE GUIDE
# ============================================================

def RestoreGuide(*arr):
    dataNode = "NLTA_RigData"

    if not cmds.objExists(dataNode):
        cmds.warning("NLTA_RigData does not exist.")
        return

    if not cmds.attributeQuery(
        "GuideData",
        node=dataNode,
        exists=True
    ):
        cmds.warning("GuideData does not exist.")
        return

    text = cmds.getAttr(
        dataNode + ".GuideData"
    )

    if not text:
        cmds.warning("GuideData is empty.")
        return

    data = json.loads(text)

    # --------------------------------------------------
    # SAVE CONTROL SHAPES
    # --------------------------------------------------

    SaveControlShapeData()

    # --------------------------------------------------
    # SAVE SKIN
    # --------------------------------------------------

    ExportSkinData()

    # --------------------------------------------------
    # RELEASE GEO
    # --------------------------------------------------

    if cmds.objExists("Geo"):
        geoChildren = cmds.listRelatives(
            "Geo",
            c=True,
            f=True
        ) or []

        for obj in geoChildren:
            if cmds.objExists(obj):
                cmds.parent(
                    obj,
                    w=True
                )

    # --------------------------------------------------
    # DELETE BUILD SYSTEM
    # --------------------------------------------------

    for node in [
        "Rig",
        "ControlSet",
        "BindJointSet",
        "BindJoints",
        "Controls",
        "Meshes",
    ]:
        if cmds.objExists(node):
            cmds.delete(node)

    if cmds.objExists("NLTA_Guide"):
        cmds.delete("NLTA_Guide")

    # --------------------------------------------------
    # CREATE GUIDE
    # --------------------------------------------------

    guide = cmds.createNode(
        "transform",
        n=data["guide"]["name"]
    )

    cmds.xform(
        guide,
        ws=True,
        m=data["guide"]["matrix"]
    )

    # --------------------------------------------------
    # RESTORE GUIDE SHAPE
    # --------------------------------------------------

    guideSel = om.MSelectionList()
    guideSel.add(guide)
    guideDag = guideSel.getDagPath(0)

    for shapeData in data["guide"].get(
        "shapes",
        []
    ):
        cvs = [
            om.MPoint(*pos)
            for pos in shapeData["cvs"]
        ]

        curveFn = om.MFnNurbsCurve()

        shapeObj = curveFn.create(
            cvs,
            shapeData["knots"],
            shapeData["degree"],
            shapeData["form"],
            False,
            True,
            guideDag.node()
        )

        shapeFn = om.MFnDagNode(shapeObj)

        try:
            shapeFn.setName(
                shapeData["name"]
            )
        except:
            pass

    # --------------------------------------------------
    # RESTORE JOINTS
    # --------------------------------------------------

    created = {}

    for jointData in data["joints"]:
        cmds.select(clear=True)

        joint = cmds.joint(
            n=jointData["name"]
        )

        parentName = jointData["parent"]

        if parentName:
            joint = cmds.parent(
                joint,
                created[parentName]
            )[0]
        else:
            joint = cmds.parent(
                joint,
                guide
            )[0]

        cmds.setAttr(
            joint + ".rotateOrder",
            jointData.get(
                "rotateOrder",
                0
            )
        )

        if "jointOrient" in jointData:
            cmds.setAttr(
                joint + ".jointOrient",
                *jointData["jointOrient"]
            )

        if "rotateAxis" in jointData:
            cmds.setAttr(
                joint + ".rotateAxis",
                *jointData["rotateAxis"]
            )

        if "translate" in jointData:
            cmds.setAttr(
                joint + ".translate",
                *jointData["translate"]
            )

        if "rotate" in jointData:
            cmds.setAttr(
                joint + ".rotate",
                *jointData["rotate"]
            )

        if "scale" in jointData:
            cmds.setAttr(
                joint + ".scale",
                *jointData["scale"]
            )

        if "segmentScaleCompensate" in jointData:
            cmds.setAttr(
                joint + ".segmentScaleCompensate",
                jointData[
                    "segmentScaleCompensate"
                ]
            )

        for attr, value in jointData.get(
            "attrs",
            {}
        ).items():

            if not cmds.attributeQuery(
                attr,
                node=joint,
                exists=True
            ):
                cmds.addAttr(
                    joint,
                    ln=attr,
                    at="bool",
                    dv=value,
                    k=True
                )

            cmds.setAttr(
                joint + "." + attr,
                value
            )

        created[
            jointData["name"]
        ] = joint

    # --------------------------------------------------
    # DELETE GUIDE DATA
    # --------------------------------------------------

    if cmds.objExists(dataNode):
        cmds.delete(dataNode)

    cmds.select(guide)
    return guide


# ============================================================
# BUILD
# ============================================================

def Build(*args):
    guide = "NLTA_Guide"

    tolerance = 0.001
    controlScale = 0.4
    rootScale = 1.5
    minControlSize = 0.1
    mainScale = 2.0

    if not cmds.objExists(guide):
        cmds.warning(
            "NLTA_Guide does not exist."
        )
        return

    SaveGuideData(guide)

    constraintNodes = []
    rigRoots = []
    allControls = []
    allJoints = []

    # --------------------------------------------------
    # HELPERS
    # --------------------------------------------------

    def GetBoolAttr(
        node,
        attr,
        default=False
    ):
        if not cmds.attributeQuery(
            attr,
            node=node,
            exists=True
        ):
            return default

        return cmds.getAttr(
            node + "." + attr
        )

    def GetName(node):
        return node.split("|")[-1]

    def GetBaseName(node):
        name = GetName(node)

        for suffix in [
            "_M",
            "_L",
            "_R"
        ]:
            if name.endswith(suffix):
                return name[:-2]

        return name

    def GetMatrix(node):
        return cmds.xform(
            node,
            q=True,
            ws=True,
            m=True
        )

    def GetPosition(node):
        return cmds.xform(
            node,
            q=True,
            ws=True,
            t=True
        )

    def GetX(node):
        return GetPosition(node)[0]

    def IsSide(node):
        return abs(
            GetX(node)
        ) > tolerance

    def GetSide(node):
        return (
            "L"
            if GetX(node) > 0
            else "R"
        )

    def GetDistance(
        nodeA,
        nodeB
    ):
        posA = GetPosition(nodeA)
        posB = GetPosition(nodeB)

        return sum(
            (a - b) ** 2
            for a, b in zip(
                posA,
                posB
            )
        ) ** 0.5

    def GetControlSize(
        guideJoint
    ):
        parent = cmds.listRelatives(
            guideJoint,
            p=True,
            type="joint",
            f=True
        )

        if parent:
            distance = GetDistance(
                guideJoint,
                parent[0]
            )

            return max(
                distance *
                controlScale,
                minControlSize
            )

        children = cmds.listRelatives(
            guideJoint,
            c=True,
            type="joint",
            f=True
        ) or []

        if children:
            distances = [
                GetDistance(
                    guideJoint,
                    child
                )
                for child in children
            ]

            return max(
                max(distances) *
                controlScale *
                rootScale,
                minControlSize
            )

        return 1.0

    def MirrorMatrix(matrix):
        m = list(matrix)

        m[12] *= -1
        m[0] *= -1
        m[1] *= -1
        m[2] *= -1

        return m

    # --------------------------------------------------
    # CREATE JOINT
    # --------------------------------------------------

    def CreateRigJoint(name, matrix, parent=None):
        cmds.select(clear=True)
        joint = cmds.joint(n=name)

        if parent:
            joint = cmds.parent(joint, parent)[0]

        cmds.xform(joint, ws=True, m=matrix)

        # Freeze Rotate + Scale
        # Joint orientation sẽ được đưa vào jointOrient
        cmds.makeIdentity(
            joint,
            apply=True,
            t=False,
            r=True,
            s=True,
            n=False
        )

        allJoints.append(joint)
        return joint

    # --------------------------------------------------
    # CREATE CONTROL
    # --------------------------------------------------

    def CreateControl(
        name,
        matrix,
        parentCtrl=None,
        size=1.0
    ):
        ctrl = cmds.circle(
            n=name + "_FK",
            nr=(1, 0, 0),
            r=size,
            ch=False
        )[0]

        offset = cmds.group(
            ctrl,
            n=name + "_OffGrp"
        )

        cmds.xform(
            offset,
            ws=True,
            m=matrix
        )

        if parentCtrl:
            cmds.parent(
                offset,
                parentCtrl
            )

        allControls.append(ctrl)
        return ctrl

    # --------------------------------------------------
    # NO CONTROL -> EMPTY TRANSFORM
    # --------------------------------------------------

    def CreateEmptyControl(
        name,
        matrix,
        parentCtrl=None
    ):
        ctrl = cmds.group(
            em=True,
            n=name + "_FK"
        )

        offset = cmds.group(
            ctrl,
            n=name + "_OffGrp"
        )

        cmds.xform(
            offset,
            ws=True,
            m=matrix
        )

        if parentCtrl:
            cmds.parent(
                offset,
                parentCtrl
            )

        return ctrl

    # --------------------------------------------------
    # CONSTRAINT
    # --------------------------------------------------

    def ConstraintControl(
        ctrl,
        joint
    ):
        parentCon = cmds.parentConstraint(
            ctrl,
            joint,
            mo=True
        )[0]

        scaleCon = cmds.scaleConstraint(
            ctrl,
            joint,
            mo=True
        )[0]

        constraintNodes.extend([
            parentCon,
            scaleCon
        ])

    # --------------------------------------------------
    # CENTER
    # --------------------------------------------------

    def BuildCenter(
        guideJoint,
        parentRig,
        parentCtrl
    ):
        noMirror = GetBoolAttr(
            guideJoint,
            "NoMirror"
        )

        if (
            IsSide(guideJoint)
            and not noMirror
        ):
            BuildMirrorBranch(
                guideJoint,
                parentRig,
                parentCtrl
            )
            return

        base = GetBaseName(
            guideJoint
        )

        noJoint = GetBoolAttr(
            guideJoint,
            "NoJoint"
        )

        noControl = GetBoolAttr(
            guideJoint,
            "NoControl"
        )

        # NoMirror = Mid
        name = base + "_M"

        matrix = GetMatrix(
            guideJoint
        )

        rigJoint = None
        currentRig = parentRig

        # Joint
        if not noJoint:
            rigJoint = CreateRigJoint(
                name,
                matrix,
                parentRig
            )

            currentRig = rigJoint

            if not parentRig:
                rigRoots.append(
                    rigJoint
                )

        # Control / Empty control
        if noControl:
            ctrl = CreateEmptyControl(
                name,
                matrix,
                parentCtrl
            )

        else:
            size = GetControlSize(
                guideJoint
            )

            ctrl = CreateControl(
                name,
                matrix,
                parentCtrl,
                size
            )

        currentCtrl = ctrl

        # Empty control vẫn constraint
        if rigJoint:
            ConstraintControl(
                ctrl,
                rigJoint
            )

        children = cmds.listRelatives(
            guideJoint,
            c=True,
            type="joint",
            f=True
        ) or []

        for child in children:
            BuildCenter(
                child,
                currentRig,
                currentCtrl
            )

    # --------------------------------------------------
    # MIRROR BRANCH
    # --------------------------------------------------

    def BuildMirrorBranch(
        guideJoint,
        parentRig,
        parentCtrl
    ):
        sourceSide = GetSide(
            guideJoint
        )

        mirrorSide = (
            "R"
            if sourceSide == "L"
            else "L"
        )

        def BuildPair(
            guideNode,
            sourceParentRig,
            mirrorParentRig,
            sourceParentCtrl,
            mirrorParentCtrl
        ):
            base = GetBaseName(
                guideNode
            )

            noJoint = GetBoolAttr(
                guideNode,
                "NoJoint"
            )

            noControl = GetBoolAttr(
                guideNode,
                "NoControl"
            )

            sourceName = (
                base +
                "_" +
                sourceSide
            )

            mirrorName = (
                base +
                "_" +
                mirrorSide
            )

            sourceMatrix = GetMatrix(
                guideNode
            )

            mirrorMatrix = MirrorMatrix(
                sourceMatrix
            )

            sourceRig = None
            mirrorRig = None

            sourceCurrentRig = sourceParentRig
            mirrorCurrentRig = mirrorParentRig

            # ------------------------------------------
            # JOINTS
            # ------------------------------------------

            if not noJoint:
                sourceRig = CreateRigJoint(
                    sourceName,
                    sourceMatrix,
                    sourceParentRig
                )

                mirrorRig = CreateRigJoint(
                    mirrorName,
                    mirrorMatrix,
                    mirrorParentRig
                )

                sourceCurrentRig = sourceRig
                mirrorCurrentRig = mirrorRig

                if not sourceParentRig:
                    rigRoots.append(
                        sourceRig
                    )

                if not mirrorParentRig:
                    rigRoots.append(
                        mirrorRig
                    )

            # ------------------------------------------
            # CONTROL / EMPTY CONTROL
            # ------------------------------------------

            if noControl:
                sourceCtrl = CreateEmptyControl(
                    sourceName,
                    sourceMatrix,
                    sourceParentCtrl
                )

                mirrorCtrl = CreateEmptyControl(
                    mirrorName,
                    mirrorMatrix,
                    mirrorParentCtrl
                )

            else:
                size = GetControlSize(
                    guideNode
                )

                sourceCtrl = CreateControl(
                    sourceName,
                    sourceMatrix,
                    sourceParentCtrl,
                    size
                )

                mirrorCtrl = CreateControl(
                    mirrorName,
                    mirrorMatrix,
                    mirrorParentCtrl,
                    size
                )

            sourceCurrentCtrl = sourceCtrl
            mirrorCurrentCtrl = mirrorCtrl

            if sourceRig:
                ConstraintControl(
                    sourceCtrl,
                    sourceRig
                )

            if mirrorRig:
                ConstraintControl(
                    mirrorCtrl,
                    mirrorRig
                )

            # ------------------------------------------
            # CHILDREN
            # ------------------------------------------

            children = cmds.listRelatives(
                guideNode,
                c=True,
                type="joint",
                f=True
            ) or []

            for child in children:
                BuildPair(
                    child,
                    sourceCurrentRig,
                    mirrorCurrentRig,
                    sourceCurrentCtrl,
                    mirrorCurrentCtrl
                )

        BuildPair(
            guideJoint,
            parentRig,
            parentRig,
            parentCtrl,
            parentCtrl
        )

    # --------------------------------------------------
    # MAIN SIZE
    # --------------------------------------------------

    guideJoints = cmds.listRelatives(
        guide,
        ad=True,
        type="joint",
        f=True
    ) or []

    guideRoots = cmds.listRelatives(
        guide,
        c=True,
        type="joint",
        f=True
    ) or []

    sizes = [
        GetControlSize(joint)
        for joint in guideJoints
    ]

    mainSize = max(
        sizes or [1.0]
    ) * mainScale

    # --------------------------------------------------
    # MAIN
    # --------------------------------------------------

    mainCtrl = cmds.circle(
        n="Main",
        nr=(0, 1, 0),
        r=mainSize,
        ch=False
    )[0]

    cmds.xform(
        mainCtrl,
        ws=True,
        m=GetMatrix(guide)
    )

    allControls.append(
        mainCtrl
    )

    # --------------------------------------------------
    # BUILD
    # --------------------------------------------------

    for root in guideRoots:
        BuildCenter(
            root,
            None,
            mainCtrl
        )

    # --------------------------------------------------
    # RIG GROUPS
    # --------------------------------------------------

    rigGrp = cmds.group(
        em=True,
        n="Rig"
    )

    motionGrp = cmds.group(
        em=True,
        n="Motion"
    )

    deformationGrp = cmds.group(
        em=True,
        n="Deformation"
    )

    constraintGrp = cmds.group(
        em=True,
        n="Constraint"
    )

    geoGrp = cmds.group(
        em=True,
        n="Geo"
    )

    cmds.parent(
        motionGrp,
        deformationGrp,
        constraintGrp,
        geoGrp,
        rigGrp
    )

    # --------------------------------------------------
    # WORLD MESHES -> GEO
    # --------------------------------------------------

    meshShapes = cmds.ls(
        type="mesh",
        long=True
    ) or []

    meshTransforms = []

    for shape in meshShapes:
        transform = cmds.listRelatives(
            shape,
            p=True,
            f=True
        )

        if not transform:
            continue

        transform = transform[0]

        parent = cmds.listRelatives(
            transform,
            p=True,
            f=True
        )

        if parent:
            continue

        if transform not in meshTransforms:
            meshTransforms.append(
                transform
            )

    for mesh in meshTransforms:
        cmds.parent(
            mesh,
            geoGrp
        )

    # --------------------------------------------------
    # MAIN -> MOTION
    # --------------------------------------------------

    cmds.parent(
        mainCtrl,
        motionGrp
    )

    # --------------------------------------------------
    # JOINT ROOTS -> DEFORMATION
    # --------------------------------------------------

    for joint in rigRoots:
        if not cmds.objExists(joint):
            continue

        parent = cmds.listRelatives(
            joint,
            p=True
        )

        if not parent:
            cmds.parent(
                joint,
                deformationGrp
            )

    # --------------------------------------------------
    # RESTORE SKIN
    # --------------------------------------------------

    ImportSkinData()


    # --------------------------------------------------
    # CONSTRAINTS
    # --------------------------------------------------

    for constraint in constraintNodes:
        if cmds.objExists(constraint):
            cmds.parent(
                constraint,
                constraintGrp
            )

    # --------------------------------------------------
    # SETS
    # --------------------------------------------------

    for setName in [
        "ControlSet",
        "BindJointSet"
    ]:
        if cmds.objExists(setName):
            cmds.delete(setName)

    cmds.sets(
        allControls,
        n="ControlSet"
    ) if allControls else cmds.sets(
        em=True,
        n="ControlSet"
    )

    cmds.sets(
        allJoints,
        n="BindJointSet"
    ) if allJoints else cmds.sets(
        em=True,
        n="BindJointSet"
    )

    # --------------------------------------------------
    # DISPLAY LAYERS
    # --------------------------------------------------

    for layer in [
        "BindJoints",
        "Controls",
        "Meshes"
    ]:
        if cmds.objExists(layer):
            cmds.delete(layer)

    if allJoints:
        bindJointLayer = cmds.createDisplayLayer(
            allJoints,
            n="BindJoints",
            nr=True
        )
    else:
        bindJointLayer = cmds.createDisplayLayer(
            n="BindJoints",
            empty=True
        )

    cmds.setAttr(
        bindJointLayer +
        ".visibility",
        0
    )

    if allControls:
        cmds.createDisplayLayer(
            allControls,
            n="Controls",
            nr=True
        )
    else:
        cmds.createDisplayLayer(
            n="Controls",
            empty=True
        )

    meshLayer = cmds.createDisplayLayer(
        [geoGrp],
        n="Meshes",
        nr=True
    )

    cmds.setAttr(
        meshLayer +
        ".displayType",
        2
    )

    # --------------------------------------------------
    # RESTORE CUSTOM CONTROL SHAPES
    # --------------------------------------------------

    RestoreControlShapeData()

    # --------------------------------------------------
    # DELETE GUIDE
    # --------------------------------------------------

    if cmds.objExists(guide):
        cmds.delete(guide)

    cmds.select(mainCtrl)
    return mainCtrl

def Form(data,*arr):
    def SaveAndExport(data, *args):
        Save(data)
        ExportPython(data)

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
    cmds.scrollLayout("SceneFormMain",edit=True,height=10)


    cmds.rowColumnLayout(nc=1)

    cmds.rowColumnLayout(nc=4)
    cmds.button(label="Add Guide",width=100,c=AddGuide)
    cmds.button(label="Build",width=100,c=Build)
    export_button = cmds.button(label="Export Py",width=100,c=partial(SaveAndExport,data))
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.button(label="Save Guide",width=100,c=SaveGuideData)    
    cmds.button(label="Restore Guide",width=100,c=RestoreGuide)
    cmds.button(label="Create Joint",width=100,c=CreateJoint)
    cmds.button(label="Match 3 Verts",width=100,c=MatchThreeVertex)
    cmds.button(label="Freeze",width=100,c=Freeze)

    cmds.setParent("..")

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,265),(2,50)])
    attrUI = cmds.optionMenu()
    for key in ["NoControl","NoJoint","NoMirror"]:
        cmds.menuItem(label=key)
    cmds.button(label="Add Attr",width=130,c=partial(AddAttribute,attrUI))
    cmds.setParent("..")

    cmds.setParent("..")
    Load(data,listUI)

def _rig_basic_pattern_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def Run(data, *args):
    """Execute the exact original RigBasic.Build used by the Build UI button."""
    return Build()


def ExportPython(data, *args):
    path = _rig_basic_pattern_path(data)
    # RigBasic.Build reads NLTA_Guide and other Maya scene nodes directly.
    # It does not consume the ScenePattern saved UI record data.
    helpers = (GetSkinCluster, GetSkinFolder, ImportSkinData, SaveGuideData, RestoreControlShapeData, Build)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in helpers))
    code = ast.unparse(tree)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    script = (
        "def main():\n"
        "    import os\n"
        "    import json\n"
        "    import maya.cmds as cmds\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    # RigBasic requires an existing NLTA_Guide in the Maya scene.\n"
        + code
        + "\n\n    # Create the rig only when main() is run.\n"
        + "    return Build()\n\n"
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


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_rig_basic_pattern_path(data)))


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










