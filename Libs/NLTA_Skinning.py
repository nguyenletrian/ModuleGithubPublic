import os
import re
import shutil
import importlib
import maya.cmds as cmds
import maya.mel as mel
import pymel.core as pm
import xml.dom.minidom as xd
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

########### SCRIPT JOB

import NLTA_General, NLTA_Mesh, NLTA_OpenMaya
for module in [NLTA_General, NLTA_Mesh, NLTA_OpenMaya]:
    try:
        importlib.reload(module)
    except:
        reload(module)



skinSession = {
    "mesh": None,
    "skinCluster": None,
    "joints": [],
}


def _SkinInfluencePaths(skin):
    """Actual bound joint DAG paths from the skinCluster API."""
    if not skin or not cmds.objExists(skin):
        return []
    selection = om.MSelectionList()
    selection.add(skin)
    fn = oma.MFnSkinCluster(selection.getDependNode(0))
    return [dag.fullPathName() for dag in fn.influenceObjects()
            if dag.hasFn(om.MFn.kJoint)]


def _BoundJoint(skin, joint, influences=None):
    """Resolve a joint by DAG identity; never guess between duplicate names."""
    if not joint:
        return None
    if isinstance(joint, (list, tuple)):
        if len(joint) != 1:
            return None
        joint = joint[0]
    if not isinstance(joint, str):
        return None
    bound = _SkinInfluencePaths(skin) if influences is None else influences
    if joint in bound:
        return joint
    matches = cmds.ls(joint, long=True, type="joint") or []
    candidates = [name for name in bound if name in matches]
    return candidates[0] if len(candidates) == 1 else None


def ResetSkinSession():
    skinSession.update({"mesh": None, "skinCluster": None, "joints": []})
    return skinSession


def _SetSkinSession(mesh, skin):
    if not mesh or not skin or not cmds.objExists(skin):
        return None
    skinSession.update({
        "mesh": mesh,
        "skinCluster": skin,
        "joints": _SkinInfluencePaths(skin),
    })
    return skinSession


def GetSkinData(node=None):
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
        "joints": _SkinInfluencePaths(skin),
    }


def _FindPaintSkinSession():
    for skin in cmds.ls(type="skinCluster") or []:
        source = cmds.connectionInfo(skin + ".paintTrans", sourceFromDestination=True) or ""
        if not source:
            continue

        geometries = cmds.skinCluster(skin, q=True, geometry=True) or []
        if not geometries:
            continue

        geo = geometries[0]
        if cmds.nodeType(geo) == "mesh":
            parents = cmds.listRelatives(geo, parent=True, fullPath=True) or []
            mesh = parents[0] if parents else geo
        else:
            mesh = geo
        return _SetSkinSession(mesh, skin)
    return None


def EnsureSkinSession(node=None, warn=True):
    data = GetSkinData(node)
    if data["skinCluster"]:
        return _SetSkinSession(data["mesh"], data["skinCluster"])

    cachedSkin = skinSession.get("skinCluster")
    if cachedSkin and cmds.objExists(cachedSkin):
        mesh = skinSession.get("mesh")
        return _SetSkinSession(mesh, cachedSkin)

    session = _FindPaintSkinSession()
    if session:
        return session

    ResetSkinSession()
    if warn:
        cmds.warning("No active skinCluster found. Select a skinned mesh first.")
    return None


def EnsurePaintContext(mesh=None):
    """Use Maya's paint context without opening the default Paint Skin UI."""
    session = EnsureSkinSession(mesh) if mesh else EnsureSkinSession()
    if not session:
        return False

    context = "artAttrSkinContext"
    if not cmds.artAttrSkinPaintCtx(context, exists=True):
        cmds.artAttrSkinPaintCtx(context)
    cmds.setToolTo(context)

    active = GetActivePaintJoint(session["skinCluster"])
    if not active:
        joints = session["joints"] or []
        active = next((joint for joint in joints
                       if cmds.objExists(joint + ".liw")
                       and not cmds.getAttr(joint + ".liw")), None)
        active = active or (joints[0] if joints else None)
        if active:
            ActiveJoint(session["mesh"], active)
    if active:
        cmds.artAttrSkinPaintCtx(context, edit=True, influence=active)
    return True


def _SelectNativePaintInfluence(joint):
    """Replace, never append, the active row in Maya's Paint Skin tree."""
    try:
        # MEL cannot evaluate a bare global variable as a command. Assign it
        # to a typed temporary variable so maya.mel.eval returns the string.
        tree = mel.eval(
            'global string $gArtSkinInfluencesList; '
            'string $nltaPaintTree = $gArtSkinInfluencesList;')
        if not tree or not cmds.treeView(tree, exists=True):
            return None  # Tool Settings is not showing the native influence tree.
        items = cmds.treeView(tree, query=True, children="") or []
        matches = []
        for item in items:
            paths = cmds.ls(item, long=True, type="joint") or []
            if joint in paths or item == joint or item.lstrip("|") == joint.lstrip("|"):
                matches.append(item)
        if len(matches) != 1:
            cmds.warning(
                "Paint Skin: cannot uniquely locate {} in Maya's influence tree."
                .format(joint))
            return False
        # Setting influence alone leaves old rows selected in Maya. Explicitly
        # clear all native rows before selecting the single intended joint.
        cmds.treeView(tree, edit=True, clearSelection=True)
        cmds.treeView(tree, edit=True, selectItem=(matches[0], True))
        selected = cmds.treeView(tree, query=True, selectItem=True) or []
        if selected != [matches[0]]:
            cmds.warning("Paint Skin: expected only {}, got {}."
                         .format(matches[0], selected))
            return False
        return True
    except (RuntimeError, TypeError, ValueError) as exc:
        cmds.warning("Cannot update Maya Paint Skin influence tree: {}"
                     .format(exc))
        return False


def _RefreshPaintInfluenceDisplay():
    """Reveal the current influence's weights without selecting the joint DAG."""
    context = "artAttrSkinContext"
    try:
        cmds.artAttrSkinPaintCtx(
            context, edit=True, colorfeedback=True, xrayJoints=True)

        # Color feedback needs shaded display; wireframe-only model panels
        # show the skeleton/edges but not the joint's painted weight map.
        model_panels = cmds.getPanel(type="modelPanel") or []
        panel = cmds.getPanel(withFocus=True)
        if panel not in model_panels:
            visible = set(cmds.getPanel(visiblePanels=True) or [])
            panel = next((name for name in model_panels if name in visible), None)
        if panel and cmds.modelEditor(
                panel, query=True, displayAppearance=True) == "wireframe":
            cmds.modelEditor(
                panel, edit=True, displayAppearance="smoothShaded")
        cmds.refresh(force=True)
        return True
    except (RuntimeError, ValueError, TypeError) as exc:
        cmds.warning("Paint Skin display refresh skipped: {}".format(exc))
        return False


def SelectPaintInfluence(mesh, joint):
    """Select exactly one influence in the custom and Maya native skin lists."""
    data = GetSkinData(mesh)
    skin = data["skinCluster"]
    bound = _BoundJoint(skin, joint, data["joints"]) if skin else None
    if not bound:
        cmds.warning("{} is not a bound influence of {}."
                     .format(joint, skin or mesh))
        return False
    if not EnsurePaintContext(mesh):
        return False

    # Use Maya's influence setter, but not artSkinRevealSelected: the latter
    # can leave several native influence rows highlighted.
    mel_name = bound.replace("\\", "\\\\").replace('"', '\\"')
    try:
        mel.eval('setSmoothSkinInfluence "{}";'.format(mel_name))
    except RuntimeError as exc:
        cmds.warning("Unable to set Paint Skin influence: {}".format(exc))
        return False

    selected = _SelectNativePaintInfluence(bound)
    if selected is False:
        return False
    if not ActiveJoint(mesh, bound):
        return False
    cmds.artAttrSkinPaintCtx(
        "artAttrSkinContext", edit=True, influence=bound)
    _RefreshPaintInfluenceDisplay()
    return True


def GetActivePaintJoint(skinCluster=None):
    if skinCluster is None:
        session = EnsureSkinSession(warn=False)
        skinCluster = session["skinCluster"] if session else None
    if not skinCluster or not cmds.objExists(skinCluster):
        return None

    source = cmds.connectionInfo(
        skinCluster + ".paintTrans", sourceFromDestination=True) or ""
    return _BoundJoint(skinCluster, source.split(".", 1)[0]) if source else None


def GetSkinApi(mesh, skinCluster=None):
    skinCluster = skinCluster or GetSkinCluster(mesh)
    if not skinCluster:
        return None, None, None

    dagPath = NLTA_OpenMaya.GetDagPath(mesh)
    sel = om.MSelectionList()
    sel.add(skinCluster)
    return dagPath, oma.MFnSkinCluster(sel.getDependNode(0)), skinCluster


def CreateVertexComponent(vertexIds):
    compFn = om.MFnSingleIndexedComponent()
    comp = compFn.create(om.MFn.kMeshVertComponent)
    compFn.addElements(vertexIds)
    return comp


def DetectCurrentSkin(*args):
    selection = cmds.ls(sl=True, fl=True) or []
    for item in selection:
        data = GetSkinData(item)
        if data["skinCluster"]:
            _SetSkinSession(data["mesh"], data["skinCluster"])
            return data["skinCluster"]

    # Do not clear a valid session when the user selects a joint while painting.
    cachedSkin = skinSession.get("skinCluster")
    if cachedSkin and cmds.objExists(cachedSkin):
        return cachedSkin

    session = _FindPaintSkinSession()
    return session["skinCluster"] if session else None

def OpenSkinToolListen():
    for job in cmds.scriptJob(listJobs=True) or []:
        if "DetectCurrentSkin" in job:
            try:
                cmds.scriptJob(kill=int(job.split(":", 1)[0]), force=True)
            except (TypeError, ValueError, RuntimeError):
                pass

    cmds.scriptJob(event=["ToolChanged", DetectCurrentSkin], protected=True)
    cmds.scriptJob(event=["SelectionChanged", DetectCurrentSkin], protected=True)
    DetectCurrentSkin()
OpenSkinToolListen()


def GetSkinCluster(node):
    if not node or not cmds.objExists(node.split(".")[0]):
        return None
    return GetSkinData(node)["skinCluster"]


def getSkinClusterFn(skinCluster):
    if not skinCluster or not cmds.objExists(skinCluster):
        return None
    sel = om.MSelectionList()
    sel.add(skinCluster)
    return oma.MFnSkinCluster(sel.getDependNode(0))

def GetVertexWeights(skinCluster, vert):
    if not skinCluster or not cmds.objExists(skinCluster):
        return {}
    # Query by full DAG path: mapping by short joint names can overwrite
    # entries when several bound joints share a leaf name (e.g. joint2).
    influences = _SkinInfluencePaths(skinCluster)
    return {joint: cmds.skinPercent(
        skinCluster, vert, q=True, transform=joint)
        for joint in influences}

def SetVertexWeights(skinCluster, vert, weightDict):
    if not skinCluster or not weightDict:
        return
    cmds.skinPercent(skinCluster, vert, transformValue=list(weightDict.items()))

def GetJointsWeight(data):
    skinCluster = data["skinCluster"]
    vert = data["vert"]
    joints = data["joints"]
    if not joints:
        return {}
    values = [
        cmds.skinPercent(skinCluster, vert, q=True, transform=j)
        for j in joints
    ]
    total = sum(values)
    result = {}
    for j, w in zip(joints, values):
        ratio = (w / total) if total != 0 else 0.0
        result[j] = {
            "weight": w,
            "ratio": ratio
        }
    return result

def GetJointsTotalWeight(skinCluster, vert, joints):
    if not joints:
        return 0.0
    values = cmds.skinPercent(
        skinCluster,
        vert,
        q=True,
        transformValue=joints
    )
    if not isinstance(values, (list, tuple)):
        values = [values]
    return sum(values)

def ActiveSkin(mesh,*arr):
    skinData = NLTA_General.GetSkinData(mesh)
    skinCluster = skinData["skinCluster"]
    if skinCluster:
        cmds.setAttr(skinCluster + ".envelope",1)

def DeactiveSkin(mesh,*arr):
    skinData = NLTA_General.GetSkinData(mesh)
    skinCluster = skinData["skinCluster"]
    if skinCluster:
        cmds.setAttr(skinCluster + ".envelope",0)

def component(*arr):    
    mel.eval("ComponentEditor;")
    
def pruneSmallWeights(*arr):    
    mel.eval("artSkinLockInf artAttrSkinPaintCtx 0;")
    mel.eval("artSkinInvLockInf artAttrSkinPaintCtx 0;")
    mel.eval("PruneSmallWeights;")
    mel.eval("artSkinLockInf artAttrSkinPaintCtx 0;")
    mel.eval("artSkinInvLockInf artAttrSkinPaintCtx 1;")  

def unlockAll(*arr):
    mel.eval("artSkinInvLockInf artAttrSkinPaintCtx 0;")
    mel.eval("artSkinLockInf artAttrSkinPaintCtx 0;")

def lockAll(*arr):
    mel.eval("artSkinInvLockInf artAttrSkinPaintCtx 1;")
    mel.eval("artSkinLockInf artAttrSkinPaintCtx 1;")

def singleUnlock(objs, *arr):
    session = EnsureSkinSession()
    if not session:
        return []

    skin = session["skinCluster"]
    joints = _SkinInfluencePaths(skin)
    unlock_set = {joint for name in (objs or [])
                  for joint in [_BoundJoint(skin, name, joints)] if joint}
    if not unlock_set:
        cmds.warning("None of the requested joints are influences of {}."
                     .format(skin))
        return []
    for joint in joints:
        if cmds.objExists(joint + ".liw"):
            cmds.setAttr(joint + ".liw", 0 if joint in unlock_set else 1)
    return [joint for joint in joints if joint in unlock_set]

def unlock(*arr):
    selected_joints = cmds.ls(sl=True, type="joint", long=True) or []
    session = EnsureSkinSession()
    if not session:
        return

    if not selected_joints:
        mel.eval("artSkinLockInf artAttrSkinPaintCtx 0;")
        mel.eval("artSkinInvLockInf artAttrSkinPaintCtx 1;")
        return

    joints = [joint for joint in
              (_BoundJoint(session["skinCluster"], name) for name in selected_joints)
              if joint]
    if not joints:
        cmds.warning("Selected joints are not influences of the active skinCluster.")
        return

    cmds.select(session["mesh"], r=True)
    singleUnlock(joints)
    SelectPaintInfluence(session["mesh"], joints[0])

def UnlockJoints(mesh, jnts):
    skin = GetSkinCluster(mesh)
    if not skin:
        return
    joints = _SkinInfluencePaths(skin)
    targets = {joint for name in (jnts or [])
               for joint in [_BoundJoint(skin, name, joints)] if joint}
    if not targets:
        return
    for joint in joints:
        if cmds.objExists(joint + ".liw"):
            cmds.setAttr(joint + ".liw", 0 if joint in targets else 1)

def addUnlock(*arr):
    mel.eval("artSkinLockInf artAttrSkinPaintCtx 0;")    

def addUnlockUp(*arr):
    session = EnsureSkinSession()
    if not session:
        return

    jointActive = GetActivePaintJoint(session["skinCluster"])
    if not jointActive:
        cmds.warning("No active paint influence found.")
        return

    parents = cmds.listRelatives(
        jointActive, parent=True, type="joint", fullPath=True) or []
    if not parents:
        cmds.warning("{} has no parent joint.".format(jointActive))
        return

    parentJoint = _BoundJoint(session["skinCluster"], parents[0])
    if not parentJoint:
        cmds.warning("Parent {} is not bound to {}."
                     .format(parents[0], session["skinCluster"]))
        return

    singleUnlock([jointActive, parentJoint])
    SelectPaintInfluence(session["mesh"], parentJoint)

def UnlockTwoJoints(*arr):
    selection = cmds.ls(sl=True, fl=True) or []
    if not selection or ".vtx[" not in selection[0]:
        cmds.warning("Please select one vertex.")
        return

    vertex = selection[0]
    mesh = vertex.split(".")[0]
    skin = GetSkinCluster(mesh)
    if not skin:
        cmds.warning("No skinCluster found.")
        return

    weights = GetVertexWeights(skin, vertex)
    data = sorted(
        ((joint, weight) for joint, weight in weights.items() if weight > 0.0),
        key=lambda item: item[1],
        reverse=True
    )
    if len(data) < 2:
        cmds.warning("Vertex has fewer than two influences.")
        return

    jointA, jointB = data[0][0], data[1][0]
    session = _SetSkinSession(mesh, skin)
    if not session:
        return
    joints = singleUnlock([jointA, jointB])
    if len(joints) != 2:
        return
    jointA = _BoundJoint(skin, jointA, joints)
    jointB = _BoundJoint(skin, jointB, joints)
    cmds.select(mesh, r=True)
    SelectPaintInfluence(mesh, jointB)
    return jointA, jointB

def UnlockInfluenceJoints(*arr):
    selection = cmds.ls(sl=True, fl=True) or []

    # Check selection
    if not selection or ".vtx[" not in selection[0]:
        cmds.warning("Please select one vertex.")
        return

    vertex = selection[0]
    mesh = vertex.split(".")[0]

    # Get skinCluster
    skin = GetSkinCluster(mesh)
    if not skin:
        cmds.warning("No skinCluster found.")
        return

    # Get vertex weights
    weights = GetVertexWeights(skin, vertex)

    # Get all joints affecting this vertex
    data = sorted(
        (
            (joint, weight)
            for joint, weight in weights.items()
            if weight > 0.0
        ),
        key=lambda item: item[1],
        reverse=True
    )

    if not data:
        cmds.warning("Vertex has no influences.")
        return

    joints = [joint for joint, weight in data]

    # Update skin data
    session = _SetSkinSession(mesh, skin)
    if not session:
        return

    # Unlock all affecting joints by DAG identity.
    unlocked = singleUnlock(joints)
    if not unlocked:
        return
    active = _BoundJoint(skin, joints[0], unlocked)
    if not active:
        return

    cmds.select(mesh, r=True)
    SelectPaintInfluence(mesh, active)

    return unlocked

def addUnlockDown(*arr):
    session = EnsureSkinSession()
    if not session:
        return

    jointActive = GetActivePaintJoint(session["skinCluster"])
    if not jointActive:
        cmds.warning("No active paint influence found.")
        return

    children = cmds.listRelatives(
        jointActive, children=True, type="joint", fullPath=True) or []
    if not children:
        cmds.warning("{} has no child joint.".format(jointActive))
        return

    childJoint = next((path for child in children
                       for path in [_BoundJoint(session["skinCluster"], child)]
                       if path), None)
    if not childJoint:
        cmds.warning("No child of {} is bound to {}."
                     .format(jointActive, session["skinCluster"]))
        return

    singleUnlock([jointActive, childJoint])
    SelectPaintInfluence(session["mesh"], childJoint)

def ActiveJoint(mesh, joint, *arr):
    data = GetSkinData(mesh)
    skinCluster = data["skinCluster"]
    if not skinCluster:
        cmds.warning("No skinCluster found on {}.".format(mesh))
        return False
    bound = _BoundJoint(skinCluster, joint, data["joints"])
    if not bound:
        cmds.warning("{} is not an unambiguous influence of {}."
                     .format(joint, skinCluster))
        return False
    cmds.connectAttr(
        bound + ".message", skinCluster + ".paintTrans", force=True)
    skinSession.update(data)
    return True

def switchJoint(*arr):
    selection = cmds.ls(sl=True, fl=True) or []
    if not selection:
        cmds.warning("Select a skinned mesh or component.")
        return

    data = GetSkinData(selection[0])
    skinName = data["skinCluster"]
    if not skinName:
        cmds.warning("No skinCluster found.")
        return

    joints = _SkinInfluencePaths(skinName)
    unlocked = [joint for joint in joints
                if cmds.objExists(joint + ".liw")
                and not cmds.getAttr(joint + ".liw")]
    if not unlocked:
        cmds.warning("No unlocked influences found.")
        return

    jointActive = GetActivePaintJoint(skinName)
    index = (unlocked.index(jointActive) + 1) % len(unlocked) if jointActive in unlocked else 0
    SelectPaintInfluence(data["mesh"], unlocked[index])

def goToBindPose(*arr):
    mel.eval('GoToBindPose;')
    
def GetJointVertexs(mesh, joints, threshold=0.0001):
    dagPath, skinFn, skin = GetSkinApi(mesh)
    if skinFn is None:
        return []

    jointSet = set(joints or [])
    if not jointSet:
        return []

    influences = skinFn.influenceObjects()
    influenceIndices = []
    for i, influence in enumerate(influences):
        name = influence.partialPathName()
        full = influence.fullPathName()
        if name in jointSet or full in jointSet:
            influenceIndices.append(i)

    if not influenceIndices:
        return []

    meshFn = om.MFnMesh(dagPath)
    vertexIds = list(range(meshFn.numVertices))
    component = CreateVertexComponent(vertexIds)
    weights, influenceCount = skinFn.getWeights(dagPath, component)

    result = []
    for row, vertexId in enumerate(vertexIds):
        offset = row * influenceCount
        if any(weights[offset + influenceId] > threshold for influenceId in influenceIndices):
            result.append("{}.vtx[{}]".format(mesh, vertexId))
    return result

def IsolateEffectVertex(*args):
    selection = cmds.ls(selection=True)
    if selection:
        mesh = selection[0]
        currentData = NLTA_General.GetSkinData(mesh)
        jointActive = currentData["jointActive"]
        jointsUnlock = currentData["jointsUnlock"]
        vertexs = GetJointVertexs(mesh,[jointActive])
        cmds.setToolTo('selectSuperContext')
        cmds.select(clear=True)
        cmds.select(vertexs, add=True)
        panelCurrent = cmds.getPanel(withFocus=True)
        state = cmds.isolateSelect(panelCurrent, q=True, state=True)
        if state == 1:
            mel.eval('ToggleIsolateSelect;')
            mel.eval('ToggleIsolateSelect;')
        elif state == 0:
            mel.eval('ToggleIsolateSelect;')
        cmds.select(clear=True)
        cmds.select(mesh)
        try:
            EnsurePaintContext(mesh)
        except:
            pass

def clearMesh(*arr):
    for mesh in cmds.ls(selection=True):
        cmds.select(mesh)
        mel.eval('DeleteHistory;')
        cmds.setAttr(mesh+".translate",e=True,lock=0)
        cmds.setAttr(mesh+".rotate",e=True,lock=0)
        cmds.setAttr(mesh+".scale",e=True,lock=0)
        cmds.setAttr(mesh+".visibility",e=True,lock=0)
        mel.eval('makeIdentity -apply true -t 1 -r 1 -s 1 -n 0 -pn 1;')
        mel.eval('ResetTransformations;')




def ClearWeight(JointActive=None):
    verts = NLTA_Mesh.GetVertexsSelected() or []
    if not verts:
        return

    mesh = verts[0].split(".")[0]
    verts = [vert for vert in verts if vert.split(".")[0] == mesh]
    dagPath, skinFn, skin = GetSkinApi(mesh)
    if skinFn is None:
        cmds.warning("Haven't skinCluster")
        return

    jointActive = JointActive or GetActivePaintJoint(skin)
    if not jointActive:
        cmds.warning("No active paint influence found.")
        return

    influences = skinFn.influenceObjects()
    names = [influence.partialPathName() for influence in influences]
    fullNames = [influence.fullPathName() for influence in influences]
    sourceIndex = names.index(jointActive) if jointActive in names else (
        fullNames.index(jointActive) if jointActive in fullNames else -1
    )
    if sourceIndex < 0:
        cmds.warning("{} is not an influence of {}.".format(jointActive, skin))
        return

    vertexIds = [int(vert.rsplit("[", 1)[1].rstrip("]")) for vert in verts]
    component = CreateVertexComponent(vertexIds)
    weights, influenceCount = skinFn.getWeights(dagPath, component)
    newWeights = om.MDoubleArray(weights)
    changed = False

    for row in range(len(vertexIds)):
        offset = row * influenceCount
        sourceWeight = weights[offset + sourceIndex]
        if sourceWeight <= 0.0:
            continue

        dominantIndex = max(
            (i for i in range(influenceCount) if i != sourceIndex),
            key=lambda i: weights[offset + i],
            default=None
        )
        if dominantIndex is None:
            continue

        newWeights[offset + dominantIndex] += sourceWeight
        newWeights[offset + sourceIndex] = 0.0
        changed = True

    if changed:
        skinFn.setWeights(
            dagPath,
            component,
            om.MIntArray(range(influenceCount)),
            newWeights,
            False
        )
        cmds.skinCluster(skin, e=True, forceNormalizeWeights=True)

    return changed

def setMiddleWeight(*arr):
    cmds.currentTime(0)
    selection = cmds.ls(os=True, fl=True) or []
    joints = cmds.ls(selection, type="joint") or []
    vertices = [item for item in selection if ".vtx[" in item]

    if not joints or not vertices:
        cmds.warning("Select the middle joint, optional extra joints, and vertices.")
        return

    mesh = vertices[0].split(".")[0]
    vertices = [vertex for vertex in vertices if vertex.split(".")[0] == mesh]
    skinCluster = GetSkinCluster(mesh)
    if not skinCluster:
        cmds.warning("No skinCluster found on {}.".format(mesh))
        return
    bound = _SkinInfluencePaths(skinCluster)
    resolved = [_BoundJoint(skinCluster, joint, bound) for joint in joints]
    if any(joint is None for joint in resolved):
        cmds.warning("Selected joints must be influences of {}.".format(skinCluster))
        return
    middleJoint, jointArray = resolved[0], resolved[1:]

    skinJoints = bound
    lockState = {joint: cmds.getAttr(joint + ".liw") for joint in skinJoints if cmds.objExists(joint + ".liw")}

    try:
        for joint in skinJoints:
            if cmds.objExists(joint + ".liw"):
                cmds.setAttr(joint + ".liw", 0)

        averageWeight = 1.0 / float(len(jointArray) + 1)
        values = [(middleJoint, averageWeight)] + [(joint, averageWeight) for joint in jointArray]
        for vertex in vertices:
            cmds.skinPercent(skinCluster, vertex, transformValue=values, normalize=True)
    finally:
        for joint, state in lockState.items():
            if cmds.objExists(joint + ".liw"):
                cmds.setAttr(joint + ".liw", state)

    cmds.select(jointArray or [middleJoint], r=True)
    component()
    cmds.select(vertices, r=True)

def mirrorSkin(axis, neg_pos, *arr):
    """Mirror skin on the chosen mesh/region, including auto-found opposite vertices.

    Resolve Paint Skin vertices even when Maya also selects their mesh or
    returns shape and transform DAG paths. Keep the Paint Skin tool active.
    Vertices outside the mirrored region retain their original weights.
    """
    selection = cmds.ls(sl=True, fl=True, long=True) or []
    context = cmds.currentCtx()
    try:
        context_type = cmds.contextInfo(context, c=True) or ""
    except RuntimeError:
        context_type = ""
    paint_skin = "artAttrSkin" in (context + " " + context_type)

    def mesh_transform(item):
        node = item.split(".", 1)[0]
        if cmds.nodeType(node) == "mesh":
            return (cmds.listRelatives(node, parent=True, fullPath=True) or [node])[0]
        return (cmds.ls(node, long=True) or [node])[0]

    # Vertex components take precedence over mesh or joint selections.
    components = [item for item in selection if ".vtx[" in item]
    if paint_skin and not components:
        active = om.MGlobal.getActiveSelectionList()
        for index in range(active.length()):
            try:
                dag, component = active.getComponent(index)
            except (RuntimeError, TypeError, ValueError):
                continue
            if component.apiType() == om.MFn.kMeshVertComponent:
                components.extend("{}.vtx[{}]".format(dag.fullPathName(), vertex)
                                  for vertex in om.MFnSingleIndexedComponent(component).getElements())
    if not selection and not components:
        cmds.warning("Select a skinned mesh or some of its vertices.")
        return False

    axis = str(axis).lower()
    faces = {"x": "YZ", "y": "XZ", "z": "XY"}
    if axis not in faces or neg_pos not in ("-", "+"):
        cmds.warning("mirrorSkin expects axis x/y/z and direction +/-.")
        return False

    if components:
        meshes = {mesh_transform(item) for item in components}
        if len(meshes) != 1:
            cmds.warning("Mirror Skin requires vertices from one mesh: {}.".format(", ".join(sorted(meshes))))
            return False
        mesh = next(iter(meshes))
    else:
        mesh = mesh_transform(selection[0])
        if paint_skin:
            cmds.warning("Select vertices in Paint Skin Weights before mirroring.")
            return False
    skin = GetSkinCluster(mesh)
    if not skin:
        cmds.warning("No skinCluster found on {}.".format(mesh))
        return False

    options = dict(sourceSkin=skin, destinationSkin=skin,
                   mirrorMode=faces[axis], mirrorInverse=(neg_pos == "-"),
                   surfaceAssociation="closestPoint",
                   influenceAssociation=["closestJoint", "oneToOne"])

    # An object-only selection outside Paint Skin mirrors the full mesh.
    if not components:
        cmds.copySkinWeights(**options)
        return True

    # Paint Skin selection must stay in its own context; symmetry selection
    # commands can clear the component selection when Artisan is active.
    sourceIds = {int(match.group(1)) for item in components
                 for match in [re.search(r"\.vtx\[(\d+)\]$", item)] if match}
    expanded = set(sourceIds)
    reflected_selection = []
    if not paint_skin:
        try:
            mel.eval("reflectionSetMode object{};".format(axis))
            reflected_selection += cmds.ls(sl=True, fl=True, long=True) or []
        finally:
            mel.eval("reflectionSetMode none;")
        reflected_selection += cmds.ls(sl=True, fl=True, long=True) or []

    for item in reflected_selection:
        if ".vtx[" not in item or mesh_transform(item) != mesh:
            continue
        match = re.search(r"\.vtx\[(\d+)\]$", item)
        if match:
            expanded.add(int(match.group(1)))

    dagPath, skinFn, _ = GetSkinApi(mesh, skin)
    meshFn = om.MFnMesh(dagPath)
    count = meshFn.numVertices
    if any(i >= count for i in expanded):
        cmds.warning("Vertex selection does not match the current mesh.")
        return False

    # Some Maya scenes do not expand an EXISTING selection when reflection
    # is switched on. Find the opposite vertices by object-space position in
    # that case, using Maya's current symmetry tolerance.
    partnerFound = expanded != sourceIds
    if expanded == sourceIds:
        points = meshFn.getPoints(om.MSpace.kObject)
        tolerance = float(cmds.symmetricModelling(q=True, tolerance=True) or 0.001)
        tolerance = max(tolerance, 1e-6)
        axisIndex = {"x": 0, "y": 1, "z": 2}[axis]
        grid = {}
        for i, p in enumerate(points):
            key = tuple(int(round(p[k] / tolerance)) for k in range(3))
            grid.setdefault(key, []).append(i)

        for sourceId in sourceIds:
            p = points[sourceId]
            target = [p[0], p[1], p[2]]
            target[axisIndex] = -target[axisIndex]
            key = tuple(int(round(target[k] / tolerance)) for k in range(3))
            nearest, distance2 = None, tolerance * tolerance
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for i in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                            candidate = points[i]
                            diff2 = sum((candidate[k] - target[k]) ** 2 for k in range(3))
                            if diff2 <= distance2:
                                nearest, distance2 = i, diff2
            if nearest is not None:
                expanded.add(nearest)
                if nearest != sourceId:
                    partnerFound = True

    # Avoid modifying unrelated weights if symmetry did not find any opposite
    # vertices (unless the selection is entirely on the symmetry seam).
    if not partnerFound:
        points = meshFn.getPoints(om.MSpace.kObject)
        axisIndex = {"x": 0, "y": 1, "z": 2}[axis]
        if any(abs(points[i][axisIndex]) > 1e-6 for i in sourceIds):
            cmds.warning("Could not find mirrored vertices. Skin weights were not changed.")
            return False

    # Unlike the old -selectedComponents flag, this works on Maya 2019-2024:
    # mirror normally, then restore all vertices outside the local mirrored area.
    untouched = [i for i in range(count) if i not in expanded]
    untouchedComp = CreateVertexComponent(untouched) if untouched else None
    originalWeights = None
    originalBlendWeights = None
    influenceCount = 0
    if untouchedComp is not None:
        originalWeights, influenceCount = skinFn.getWeights(dagPath, untouchedComp)
        originalBlendWeights = skinFn.getBlendWeights(dagPath, untouchedComp)

    cmds.undoInfo(openChunk=True, chunkName="NLTA Mirror Skin")
    try:
        try:
            cmds.copySkinWeights(**options)
        finally:
            if untouchedComp is not None:
                skinFn.setWeights(dagPath, untouchedComp,
                                  om.MIntArray(range(influenceCount)),
                                  originalWeights, False)
                skinFn.setBlendWeights(dagPath, untouchedComp, originalBlendWeights)
        # Keep the Paint Skin tool and its current vertex selection untouched.
        if not paint_skin:
            cmds.select(["{}.vtx[{}]".format(mesh, i) for i in sorted(expanded)], r=True)
        return True
    finally:
        cmds.undoInfo(closeChunk=True)


def _SkinGeometryShape(node):
    node = node.split(".", 1)[0]
    if not cmds.objExists(node):
        return None
    if cmds.nodeType(node) in ("mesh", "nurbsSurface"):
        return None if cmds.getAttr(node + ".intermediateObject") else node
    for shape in cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or []:
        if cmds.nodeType(shape) in ("mesh", "nurbsSurface"):
            return shape
    return None


def _SkinGeometryTransforms(selection=None):
    if selection is None:
        selection = cmds.ls(sl=True) or []
        if not selection:
            selection = (cmds.ls(type="mesh", long=True) or []) + (cmds.ls(type="nurbsSurface", long=True) or [])
    result, seen = [], set()
    for item in selection:
        shape = _SkinGeometryShape(item)
        if not shape:
            continue
        transform = (cmds.listRelatives(shape, parent=True, fullPath=True) or [shape])[0]
        transform = (cmds.ls(transform) or [transform])[0]
        if transform not in seen:
            result.append(transform)
            seen.add(transform)
    return result


def _SkinGeometryCluster(transform):
    shape = _SkinGeometryShape(transform)
    if not shape:
        return None
    return (cmds.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster") or [None])[0]


def ExportAllSkinUrl(folder, *arr):
    jsonData = {}
    jsonPath = os.path.join(folder, "skinData.json")
    version = cmds.about(version=True)
    for transform in _SkinGeometryTransforms():
        skin = _SkinGeometryCluster(transform)
        if not skin:
            continue
        transformName = transform.replace("|", "&").replace(":", "%")
        jsonData[transformName] = {"skinName": skin}
        options = dict(export=True, deformer=skin, path=folder)
        if version != "2018":
            options["format"] = "XML"
        cmds.deformerWeights(transformName + ".xml", **options)
    NLTA_General.writeJsonFile(jsonPath, jsonData)
    return jsonData


def ExportAllSkin(*arr):
    folder_temp = os.path.dirname(pm.sceneName())
    if not folder_temp:
        folder_temp = mel.eval("SaveSceneAs;")
    folder_temp = os.path.dirname(pm.sceneName())
    if folder_temp:
        folder_temp = os.path.join(os.path.dirname(pm.sceneName()), 'bnlta_all_skins_export')
        folder_temp = cmds.encodeString(folder_temp)
        if os.path.exists(folder_temp):
            shutil.rmtree(folder_temp)
        if not os.path.exists(folder_temp):
            os.makedirs(folder_temp)
        ExportAllSkinUrl(folder_temp)
        cmds.warning("Done!!!")

def ExportFolderSkinSingle(url, *arr):
    if not url:
        return False

    meshes = _SkinGeometryTransforms()
    if not meshes:
        cmds.warning("Select one or more meshes or NURBS surfaces.")
        return False

    if not os.path.isdir(url):
        os.makedirs(url)

    data = {}
    originalSelection = cmds.ls(sl=True, long=True) or []

    try:
        for mesh in meshes:
            uuid = (cmds.ls(mesh, uuid=True) or [None])[0]
            if not uuid:
                continue

            parent = cmds.listRelatives(mesh, parent=True, fullPath=True) or []
            shortName = mesh.split("|")[-1]
            tempName = shortName if "NLTA_" in shortName else "NLTA_" + shortName

            data[uuid] = {
                "originalName": shortName,
                "parent": parent[0] if parent else None,
                "tempName": tempName
            }

            if parent:
                mesh = cmds.parent(mesh, world=True)[0]
            if mesh.split("|")[-1] != tempName:
                cmds.rename(mesh, tempName)

        targets = [node for uuid in data for node in (cmds.ls(uuid) or [])]
        meshesToExport = [node for node in targets if cmds.nodeType(_SkinGeometryShape(node)) == "mesh"]
        surfacesToExport = [node for node in targets if cmds.nodeType(_SkinGeometryShape(node)) == "nurbsSurface"]
        if not targets:
            cmds.warning("No valid geometry to export.")
            return False
        if meshesToExport:
            cmds.select(meshesToExport, r=True)
            cmds.file(
                os.path.join(url, "mesh.obj"),
                force=True,
                options="groups=1;ptgroups=0;materials=0;smoothing=0;normals=1",
                type="OBJexport",
                exportSelected=True
            )
        if surfacesToExport:
            cmds.select(surfacesToExport, r=True)
            cmds.file(os.path.join(url, "surfaces.ma"), force=True, type="mayaAscii",
                      options="v=0;", exportSelected=True, constructionHistory=False,
                      channels=False, constraints=False, expressions=False)
        cmds.select(targets, r=True)
        ExportAllSkinUrl(url)
        return True

    finally:
        for uuid, item in data.items():
            nodes = cmds.ls(uuid, long=True) or []
            if not nodes:
                continue
            node = nodes[0]
            if node.split("|")[-1] != item["originalName"]:
                node = cmds.rename(node, item["originalName"])
            if item["parent"] and cmds.objExists(item["parent"]):
                try:
                    cmds.parent(node, item["parent"])
                except RuntimeError:
                    pass

        existing = [node for node in originalSelection if cmds.objExists(node)]
        if existing:
            cmds.select(existing, r=True)

def ExportFolderSkin(*arr):
    result = cmds.fileDialog2(dialogStyle=2, fileMode=3, caption="Select Folder") or []
    if result:
        ExportFolderSkinSingle(result[0])

def ExportFolderSkinQuick(*arr):
    scenePath = cmds.file(q=True, sn=True)
    if not scenePath:
        cmds.warning("Please save scene first")
        return
    sceneFolder = os.path.dirname(scenePath)
    exportFolder = os.path.join(
        sceneFolder,
        "NLTA_Data",
        "MeshExport"
    )
    exportFolder = exportFolder.replace("\\", "/")
    if not os.path.exists(exportFolder):
        os.makedirs(exportFolder)
    ExportFolderSkinSingle(exportFolder)
    cmds.warning("Done!!!")

def ImportAllSkinUrl(folder, keepHistory, *arr):
    if not os.path.isdir(folder):
        cmds.confirmDialog(title="Confirm", message="Dont have data!", button=["Yes"], defaultButton="Yes", cancelButton="Yes")
        return False
    jsonPath = os.path.join(folder, "skinData.json")
    jsonData = NLTA_General.readJsonFile(jsonPath) if os.path.exists(jsonPath) else {}
    cmds.currentTime(0)
    imported = False
    for transform in _SkinGeometryTransforms():
        transformName = transform.replace("|", "&").replace(":", "%")
        fileLink = os.path.join(folder, transformName + ".xml")
        if not os.path.exists(fileLink):
            continue
        joints = []
        for element in xd.parse(fileLink).getElementsByTagName("weights"):
            source = element.getAttribute("source")
            if source and source not in joints:
                joints.append(source)
        if not joints:
            continue
        existing = _SkinGeometryCluster(transform)
        isSurface = cmds.nodeType(_SkinGeometryShape(transform)) == "nurbsSurface"
        if keepHistory and not existing:
            cmds.warning("No existing skinCluster on {}.".format(transform))
            continue
        validJoints = [joint for joint in joints if cmds.objExists(joint)]
        for joint in joints:
            if joint not in validJoints:
                cmds.warning("Cannot find skin influence: " + joint)
        if not validJoints:
            continue
        # Keep Surface construction history and existing skin connections intact.
        if not keepHistory and not isSurface:
            cmds.delete(transform, constructionHistory=True)
            for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
                cmds.setAttr(transform + "." + attr, lock=False)
            cmds.makeIdentity(transform, apply=True, translate=True, rotate=True, scale=True, normal=False)
            cmds.xform(transform, zeroTransformPivots=True)
        shapes = [shape for shape in cmds.listRelatives(transform, shapes=True, noIntermediate=True, fullPath=True) or []
                  if cmds.nodeType(shape) in ("mesh", "nurbsSurface")]
        connections = []
        visibility = {shape: cmds.getAttr(shape + ".visibility") for shape in shapes}
        for shape in shapes:
            plug = shape + ".visibility"
            source = cmds.connectionInfo(plug, sourceFromDestination=True)
            if source:
                connections.append((source, plug))
        try:
            for source, plug in connections:
                cmds.disconnectAttr(source, plug)
            for shape in shapes:
                try:
                    cmds.setAttr(shape + ".visibility", 1)
                except RuntimeError:
                    pass
            if keepHistory or (isSurface and existing):
                skinName = existing
            else:
                skinName = cmds.skinCluster(validJoints + [transform], toSelectedBones=True,
                                            bindMethod=0, skinMethod=0, normalizeWeights=1,
                                            maximumInfluences=1)[0]
            cmds.deformerWeights(transformName + ".xml", im=True, method="index",
                                 deformer=skinName, path=folder)
            cmds.skinCluster(skinName, edit=True, forceNormalizeWeights=True)
            if transformName in jsonData:
                desired = jsonData[transformName]["skinName"]
                if desired != skinName and not cmds.objExists(desired):
                    cmds.rename(skinName, desired)
            imported = True
        finally:
            for shape, value in visibility.items():
                try:
                    cmds.setAttr(shape + ".visibility", value)
                except RuntimeError:
                    pass
            for source, plug in connections:
                cmds.connectAttr(source, plug, force=True)
    return imported


def ImportAllSkin(*arr):
    folder = os.path.dirname(pm.sceneName())+"/"+'bnlta_all_skins_export'
    ImportAllSkinUrl(folder,False)
    cmds.warning("Done!!!")

def ImportAllSkinExist(*arr):
    folder = os.path.dirname(pm.sceneName())+"/"+'bnlta_all_skins_export'
    ImportAllSkinUrl(folder,True)
    cmds.warning("Done!!!")

def ImportFolderSkinSingle(url, *arr):
    if not url or not os.path.isdir(url):
        cmds.warning("Import folder not found.")
        return False

    importedNodes = []
    for file_ in NLTA_General.GetFiles(url, "obj") or []:
        filePath = os.path.join(url, file_ + ".obj")
        importedNodes.extend(cmds.file(
            filePath, i=True, type="OBJ", ignoreVersion=True, ra=True,
            mergeNamespacesOnClash=False, namespace=":", options="mo=1",
            pr=True, returnNewNodes=True
        ) or [])
    surfaceFile = os.path.join(url, "surfaces.ma")
    if os.path.isfile(surfaceFile):
        importedNodes.extend(cmds.file(
            surfaceFile, i=True, type="mayaAscii", ignoreVersion=True, ra=True,
            mergeNamespacesOnClash=False, namespace=":", options="v=0;",
            pr=True, returnNewNodes=True
        ) or [])
    importedGeometry = _SkinGeometryTransforms(importedNodes)
    if importedGeometry:
        cmds.select(importedGeometry, r=True)
    ImportAllSkinUrl(url, False)
    cmds.warning("Done!!!")
    return True


def ImportFolderSkin(*arr):
    result = cmds.fileDialog2(dialogStyle=2, fileMode=3, caption="Select Folder") or []
    if result:
        ImportFolderSkinSingle(result[0])

def ImportFolderSkinQuick(*arr):
    scenePath = cmds.file(q=True, sn=True)
    if not scenePath:
        cmds.warning("Please save scene first")
        return
    sceneFolder = os.path.dirname(scenePath)
    importFolder = os.path.join(
        sceneFolder,
        "NLTA_Data",
        "MeshExport"
    )
    importFolder = importFolder.replace("\\", "/")
    if not os.path.exists(importFolder):
        cmds.warning("Import folder not found:\n" + importFolder)
        return
    ImportFolderSkinSingle(importFolder, False)
    cmds.warning("Import Done!!!")


def fixMaxInfluence(*arr, maxInfluence=None):
    if maxInfluence is None:
        if not cmds.intField("maxInfluent", exists=True):
            cmds.warning('UI field "maxInfluent" was not found.')
            return
        maxInfluence = cmds.intField("maxInfluent", q=True, value=True)
    maxInfluence = int(maxInfluence)
    if maxInfluence < 1:
        cmds.warning("maxInfluence must be at least 1.")
        return

    shapes = cmds.ls(sl=True, dag=True, type="mesh", noIntermediate=True) or []
    if not shapes:
        shapes = cmds.ls(type="mesh", noIntermediate=True) or []

    for shape in shapes:
        mesh = (cmds.listRelatives(shape, parent=True, fullPath=True) or [shape])[0]
        dagPath, skinFn, skin = GetSkinApi(mesh)
        if skinFn is None:
            continue

        vertexCount = om.MFnMesh(dagPath).numVertices
        component = CreateVertexComponent(range(vertexCount))
        weights, influenceCount = skinFn.getWeights(dagPath, component)
        newWeights = om.MDoubleArray(weights)
        changed = False

        for vertexIndex in range(vertexCount):
            offset = vertexIndex * influenceCount
            weighted = [(i, weights[offset + i]) for i in range(influenceCount) if weights[offset + i] > 0.0]
            if len(weighted) <= maxInfluence:
                continue

            weighted.sort(key=lambda item: item[1], reverse=True)
            keep = {index for index, _ in weighted[:maxInfluence]}
            total = sum(weights[offset + i] for i in keep)
            if total <= 0.0:
                continue

            for i in range(influenceCount):
                newWeights[offset + i] = weights[offset + i] / total if i in keep else 0.0
            changed = True

        if changed:
            skinFn.setWeights(
                dagPath,
                component,
                om.MIntArray(range(influenceCount)),
                newWeights,
                False
            )

    cmds.warning("Done (OpenMaya)!!!")


def fixMaxInfluenceAll(maxValue,*arr):
    cmds.select(clear=True)
    for a in cmds.ls(type="mesh"):
        if a.endswith("Orig")!=True:
            for b in cmds.listHistory(a) or []:
                if cmds.objExists(b) and cmds.objectType(b) == "skinCluster":
                    cmds.select(cmds.listRelatives(a,parent=True)[0],add=True)
    fixMaxInfluence(maxValue)
    cmds.warning("Done!!!")

def checkMaxInfluentNumber(val, *arr):
    return checkMaxInfluenceNumber(val)


def checkMaxInfluenceNumber(maxValue, *args):
    selection = cmds.ls(sl=True, fl=True) or []
    if not selection:
        cmds.warning("No object selected")
        return []

    mesh = selection[0].split(".")[0]
    dagPath, skinFn, skin = GetSkinApi(mesh)
    if skinFn is None:
        cmds.warning("No skinCluster found")
        return []

    vertexCount = om.MFnMesh(dagPath).numVertices
    component = CreateVertexComponent(list(range(vertexCount)))
    weights, influenceCount = skinFn.getWeights(dagPath, component)

    result = []
    for vertexIndex in range(vertexCount):
        offset = vertexIndex * influenceCount
        count = sum(1 for i in range(influenceCount) if weights[offset + i] > 0.0001)
        if count > maxValue:
            result.append("{}.vtx[{}]".format(mesh, vertexIndex))

    if cmds.objExists("vertexOverMaxInfluence"):
        cmds.delete("vertexOverMaxInfluence")

    if result:
        cmds.select(result, r=True)
        cmds.sets(result, name="vertexOverMaxInfluence")
    else:
        cmds.select(clear=True)

    cmds.warning("Done!!!")
    return result


def checkMaxInfluent(*arr, maxValue=None):
    if not cmds.ls(sl=True):
        cmds.warning("No object selected")
        return []
    if maxValue is None:
        maxValue = cmds.intField("maxInfluent", q=True, value=True)
    return checkMaxInfluenceNumber(int(maxValue))


def TransferTopWeight(vertex=None):
    if not vertex:
        selection = cmds.ls(sl=True, fl=True) or []
        if not selection:
            cmds.warning("Select one vertex.")
            return False
        vertex = selection[0]

    if ".vtx[" not in vertex:
        cmds.warning("Select one vertex.")
        return False

    amount = cmds.artAttrSkinPaintCtx("artAttrSkinContext", q=True, value=True)
    mesh = vertex.split(".")[0]
    skin = GetSkinCluster(mesh)
    if not skin:
        raise RuntimeError("No skinCluster found.")

    influences = cmds.skinCluster(skin, q=True, influence=True) or []
    weights = cmds.skinPercent(skin, vertex, q=True, value=True) or []
    data = sorted(zip(influences, weights), key=lambda item: item[1], reverse=True)

    if len(data) < 2:
        cmds.warning("Vertex has fewer than two influences.")
        return False

    jointA, weightA = data[0]
    jointB, weightB = data[1]
    if weightA <= 0.0:
        return False

    transfer = min(amount, weightA)
    newWeightA = weightA - transfer
    newWeightB = weightB + transfer

    normalize = cmds.getAttr(skin + ".normalizeWeights")
    cmds.setAttr(skin + ".normalizeWeights", 0)
    try:
        cmds.skinPercent(
            skin,
            vertex,
            transformValue=[(jointA, newWeightA), (jointB, newWeightB)],
            normalize=False
        )
    finally:
        cmds.setAttr(skin + ".normalizeWeights", normalize)

    return jointA, jointB, newWeightA, newWeightB
        


def clearSkin(*arr):
    """Unbind skinClusters on every mesh and NURBS surface in the scene.

    Only skin deformers are removed. Deleting an entire surface's
    constructionHistory would also destroy its loft/rebuild/other rig inputs.
    Like the original Clear Skins button, this acts on the whole scene, not
    just the current selection.
    """
    shapes = (cmds.ls(type="mesh", noIntermediate=True, long=True) or [])
    shapes += cmds.ls(type="nurbsSurface", noIntermediate=True, long=True) or []

    clusters = []
    seen = set()
    for shape in shapes:
        history = cmds.listHistory(shape, pruneDagObjects=True) or []
        for skin in cmds.ls(history, type="skinCluster") or []:
            if skin not in seen:
                seen.add(skin)
                clusters.append(skin)

    removed = 0
    failures = []
    cmds.undoInfo(openChunk=True, chunkName="NLTA Clear Skins")
    try:
        for skin in clusters:
            try:
                cmds.skinCluster(skin, edit=True, unbind=True)
                removed += 1
            except RuntimeError as error:
                failures.append("{}: {}".format(skin, error))
    finally:
        cmds.undoInfo(closeChunk=True)

    if failures:
        cmds.warning("Clear Skins: {} skinCluster(s) could not be removed: {}"
                     .format(len(failures), "; ".join(failures)))
    cmds.warning("Clear Skins: removed {} skinCluster(s) from Mesh/NURBS Surface."
                 .format(removed))
    return removed

def removeUnneedJoint(*arr):
    cmds.currentTime(0)
    selection = cmds.ls(sl=True, long=True) or []
    if selection:
        transforms = list(dict.fromkeys(item.split(".")[0] for item in selection))
    else:
        transforms = cmds.listRelatives(cmds.ls(type="mesh", noIntermediate=True), parent=True, fullPath=True) or []
        transforms = list(dict.fromkeys(transforms))

    removed = {}
    for transform in transforms:
        dagPath, skinFn, skin = GetSkinApi(transform)
        if skinFn is None:
            continue

        influences = skinFn.influenceObjects()
        if len(influences) <= 1:
            continue

        vertexCount = om.MFnMesh(dagPath).numVertices
        component = CreateVertexComponent(list(range(vertexCount)))
        weights, influenceCount = skinFn.getWeights(dagPath, component)

        used = [False] * influenceCount
        for vertexIndex in range(vertexCount):
            offset = vertexIndex * influenceCount
            for influenceIndex in range(influenceCount):
                if not used[influenceIndex] and weights[offset + influenceIndex] > 0.0:
                    used[influenceIndex] = True

        removeJoints = [
            influences[i].fullPathName()
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

def AddMeshJoint(*arr):
    cmds.currentTime(0)
    selection = cmds.ls(sl=True, long=True) or []
    if len(selection) < 2:
        cmds.warning("Select source mesh then destination mesh(es).")
        return

    source = selection[0]
    destinations = selection[1:]
    sourceSkin = GetSkinCluster(source)
    if not sourceSkin:
        cmds.warning("Source has no skinCluster.")
        return

    sourceJoints = set(_SkinInfluencePaths(sourceSkin))
    for destination in destinations:
        destinationSkin = GetSkinCluster(destination)
        if not destinationSkin:
            continue

        destinationJoints = set(_SkinInfluencePaths(destinationSkin))
        jointsAdd = sorted(sourceJoints - destinationJoints)
        if jointsAdd:
            cmds.skinCluster(destinationSkin, e=True, addInfluence=jointsAdd, weight=0)
            print("Add Joint " + " - ".join(jointsAdd))

    cmds.warning("Done!!!")

def AddJoint(*arr):
    cmds.currentTime(0)
    selection = cmds.ls(sl=True, long=True) or []
    if len(selection) < 2:
        cmds.warning("Select joint(s) and mesh(es).")
        return

    joints = cmds.ls(selection, type="joint", long=True) or []
    if not joints:
        cmds.warning("No joints selected.")
        return

    meshes = []
    for item in selection:
        if item in joints:
            continue
        shape = (cmds.listRelatives(item, shapes=True, noIntermediate=True, type="mesh", fullPath=True) or [])
        if shape:
            meshes.append(item)

    for mesh in list(dict.fromkeys(meshes)):
        skin = GetSkinCluster(mesh)
        if not skin:
            continue
        existing = set(_SkinInfluencePaths(skin))
        jointsAdd = [joint for joint in joints if joint not in existing]
        if jointsAdd:
            cmds.skinCluster(skin, e=True, addInfluence=jointsAdd, weight=0)
            print("Add Joint " + " - ".join(jointsAdd))

    cmds.warning("Done!!!")

def RemoveJoint(*args):
    cmds.currentTime(0)
    selection = cmds.ls(sl=True, long=True) or []
    if len(selection) < 2:
        cmds.warning("Select one or more joints and one or more meshes.")
        return

    joints = cmds.ls(selection, type="joint", long=True) or []
    if not joints:
        cmds.warning("No joints selected.")
        return

    # Remove descendants before selected ancestors, regardless of selection order.
    joints = sorted(set(joints), key=lambda joint: (-joint.count("|"), joint))

    meshes = []
    for item in selection:
        if item in joints:
            continue
        if cmds.listRelatives(item, shapes=True, noIntermediate=True, type="mesh"):
            meshes.append(item)

    for mesh in list(dict.fromkeys(meshes)):
        skin = GetSkinCluster(mesh)
        if not skin:
            continue

        for joint in joints:
            influences = _SkinInfluencePaths(skin)
            sourceName = _BoundJoint(skin, joint, influences)
            if sourceName is None:
                continue
            if len(influences) <= 1:
                cmds.warning("{} only has one influence.".format(mesh))
                break

            parent = cmds.listRelatives(joint, parent=True, type="joint", fullPath=True) or []
            if not parent:
                cmds.warning("{} has no parent. Skip.".format(joint))
                continue

            parent = parent[0]
            if _BoundJoint(skin, parent, influences) is None:
                cmds.skinCluster(
                    skin, e=True, addInfluence=parent, lockWeights=False, weight=0)
            parentName = _BoundJoint(skin, parent)

            dagPath, skinFn, _ = GetSkinApi(mesh, skin)
            influencesApi = skinFn.influenceObjects()
            fullNames = [item.fullPathName() for item in influencesApi]
            sourceIndex = (fullNames.index(sourceName)
                           if sourceName in fullNames else -1)
            parentIndex = (fullNames.index(parentName)
                           if parentName in fullNames else -1)
            if sourceIndex < 0 or parentIndex < 0:
                continue

            vertexCount = om.MFnMesh(dagPath).numVertices
            component = CreateVertexComponent(list(range(vertexCount)))
            weights, influenceCount = skinFn.getWeights(dagPath, component)
            newWeights = om.MDoubleArray(weights)

            for vertexIndex in range(vertexCount):
                offset = vertexIndex * influenceCount
                sourceWeight = newWeights[offset + sourceIndex]
                if sourceWeight > 0.0:
                    newWeights[offset + parentIndex] += sourceWeight
                    newWeights[offset + sourceIndex] = 0.0

            skinFn.setWeights(
                dagPath,
                component,
                om.MIntArray(range(influenceCount)),
                newWeights,
                False
            )
            cmds.skinCluster(skin, e=True, removeInfluence=sourceName)

    cmds.select(clear=True)
    cmds.warning("Done!")
def ExportSkinFbx(*arr):
    objects = cmds.ls(sl=True, long=True) or []
    if not objects:
        cmds.warning("Nothing is selected.")
        return None

    scenePath = cmds.file(q=True, sn=True)
    if not scenePath:
        cmds.warning("Please save the scene first.")
        return None

    originalSelection = cmds.ls(sl=True, long=True) or []
    disconnected = []
    attrStates = {}
    layerStates = {}

    def ForceVisible(node):
        attr = node + ".visibility"
        if not cmds.objExists(attr):
            return
        if attr not in attrStates:
            attrStates[attr] = cmds.getAttr(attr)
        sources = cmds.listConnections(attr, source=True, destination=False, plugs=True) or []
        for source in sources:
            disconnected.append((source, attr))
            cmds.disconnectAttr(source, attr)
        if not cmds.getAttr(attr, lock=True):
            cmds.setAttr(attr, 1)

    try:
        for obj in objects:
            shapes = cmds.listRelatives(obj, ad=True, type="mesh", fullPath=True) or []
            transforms = set()
            for shape in shapes:
                ForceVisible(shape)
                parent = cmds.listRelatives(shape, parent=True, fullPath=True) or []
                if parent:
                    transforms.add(parent[0])
            for transform in transforms:
                ForceVisible(transform)

        for layer in cmds.ls(type="displayLayer") or []:
            if layer == "defaultLayer":
                continue
            layerStates[layer] = (
                cmds.getAttr(layer + ".visibility"),
                cmds.getAttr(layer + ".displayType")
            )
            cmds.setAttr(layer + ".visibility", 1)
            cmds.setAttr(layer + ".displayType", 0)

        sceneDir = os.path.dirname(scenePath)
        sceneName = os.path.splitext(os.path.basename(scenePath))[0]
        exportPath = os.path.join(sceneDir, sceneName + "_SkinFbx.fbx").replace("\\", "/")

        if not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
            cmds.loadPlugin("fbxmaya", quiet=True)

        mel.eval("FBXExportShapes -v false")
        mel.eval("FBXExportInputConnections -v false")
        mel.eval("FBXExportEmbeddedTextures -v false")
        mel.eval("FBXExportSkins -v true")
        mel.eval("FBXExportSmoothMesh -v true")
        mel.eval("FBXExportSmoothingGroups -v true")
        mel.eval("FBXExportConstraints -v false")
        mel.eval('FBXExport -f "{}" -s'.format(exportPath))
        return exportPath

    finally:
        for layer, (visibility, displayType) in layerStates.items():
            if cmds.objExists(layer):
                cmds.setAttr(layer + ".visibility", visibility)
                cmds.setAttr(layer + ".displayType", displayType)

        for attr, value in attrStates.items():
            if cmds.objExists(attr) and not cmds.getAttr(attr, lock=True):
                try:
                    cmds.setAttr(attr, value)
                except RuntimeError:
                    pass

        for source, destination in disconnected:
            if cmds.objExists(source) and cmds.objExists(destination):
                if not cmds.isConnected(source, destination):
                    try:
                        cmds.connectAttr(source, destination, force=True)
                    except RuntimeError:
                        pass

        existing = [node for node in originalSelection if cmds.objExists(node)]
        if existing:
            cmds.select(existing, r=True)

def ObjToNewScene(*arr):
    objs = cmds.ls(selection=True)
    if objs:
        result = cmds.promptDialog(
            title='New scene name',
            message='Input new sence name:',
            button=['OK', 'Cancel'],
            defaultButton='OK',
            cancelButton='Cancel',
            dismissString='Cancel'
        )
        if result != 'OK':            
            return
        ExportSkinFbx()
        scenePath = cmds.file(q=True, sn=True)
        sceneDir = os.path.dirname(scenePath)
        sceneName = os.path.splitext(os.path.basename(scenePath))[0]
        exportPath = sceneDir+'/'+sceneName+"_SkinFbx.fbx"
        newSceneName = cmds.promptDialog(query=True, text=True)
        if not newSceneName.strip():
            cmds.error("Scene name not correct.")
        newScenePath = sceneDir+'/'+newSceneName+'.ma'
        cmds.file(new=True, force=True)
        cmds.file(rename=newScenePath)
        cmds.file(save=True, type='mayaAscii')
        cmds.file(exportPath, i=True, type="FBX", ignoreVersion=True, options="fbx", ra=True, mergeNamespacesOnClash=False)
    else:
        print('Nothing is selected')


