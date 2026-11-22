import maya.cmds as cmds
import pymel.core as pm
import maya.mel as mel
import importlib


import NLTA_General, NLTA_Mesh, NLTA_Skinning, NLTA_GraphSkinning
for module in [NLTA_General, NLTA_Mesh, NLTA_Skinning, NLTA_GraphSkinning]:
    importlib.reload(module)


def loadUi(*arr):   
    mel.eval('artAttrSkinPaintCtx -e -minvalue -1 -useColorRamp 1 -colorRamp "1,0,0,1,1,1,0.5,0,0.8,1,1,0.7,0,0.6,1,0,.5,0,0.4,1,0,0,1,0,1"  -rampMaxColor .57 .57 .57  artAttrSkinContext;')
    cmds.artAttrSkinPaintCtx("artAttrSkinContext", e=True, opacity=1)
    mel.eval('setObjectPickMask "Joint" false;')

def ChangeOpacity(ui,*arr):
    value = cmds.floatSliderGrp(ui,query=True,value=True)
    ctx = cmds.currentCtx()
    try:
        cmds.artAttrSkinPaintCtx(ctx, e=True, opacity=value)
    except:pass

def ChangeOpacityValue(ui,value,*arr):
    cmds.floatSliderGrp(ui,edit=True,value=value)
    ChangeOpacity(ui)      
    
def _skinPaintContext():
    """Use the existing Artisan paint context without opening Tool Settings."""
    context = "artAttrSkinContext"
    if not cmds.artAttrSkinPaintCtx(context, exists=True):
        cmds.warning("Skinning: Paint Skin context is not initialized.")
        return None
    return context


def _setSelectedWeights(value, operation):
    """Apply to selected components, keeping the original Replace/Add behavior."""
    context = _skinPaintContext()
    if not context:
        return False
    value = float(value)
    cmds.artAttrSkinPaintCtx(
        context, edit=True, skinPaintMode=1, selectedattroper=operation,
        value=value)
    # Optional native MEL procedure may not be loaded when the standalone
    # NLTA Command Board uses Paint Skin without opening Tool Settings.
    if mel.eval('exists "artSkinSetSelectionValue"'):
        mel.eval(
            "artSkinSetSelectionValue {} false artAttrSkinPaintCtx artAttrSkin;"
            .format(value))
        return True

    # Fallback only touches explicitly selected vertices, never the whole mesh.
    verts = [item for item in (cmds.ls(selection=True, long=True,
                                      flatten=True) or [])
             if ".vtx[" in item]
    session = NLTA_Skinning.EnsureSkinSession(warn=False)
    skin = session["skinCluster"] if session else None
    influence = NLTA_Skinning.GetActivePaintJoint(skin) if skin else None
    if not verts or not influence:
        cmds.warning(
            "Skinning: select skinned vertices to adjust weights. "
            "The Paint Skin Tool Settings window is not required.")
        return False
    if cmds.objExists(influence + ".liw") and cmds.getAttr(influence + ".liw"):
        cmds.warning("Skinning: active influence is locked: " + influence)
        return False
    for vert in verts:
        target = value
        if operation == "additive":
            current = cmds.skinPercent(skin, vert, query=True,
                                       transform=influence)
            target = float(current) + value
        cmds.skinPercent(
            skin, vert, transformValue=(influence, max(0.0, min(1.0, target))))
    cmds.refresh(force=True)
    return True


def ReplaceWeight(value, *arr):
    return _setSelectedWeights(value, "absolute")


def AddWeight(value, *arr):
    return _setSelectedWeights(value, "additive")


def smooth(value, *arr):
    context = _skinPaintContext()
    if context:
        cmds.artAttrSkinPaintCtx(context, edit=True, skinPaintMode=1,
                                 stampProfile=value, selectedattroper="smooth")


def pickValue(*arr):
    context = _skinPaintContext()
    if context:
        cmds.artAttrSkinPaintCtx(context, edit=True, selectedattroper="absolute",
                                 pickValue=True, opacity=1)


def flood(*arr):
    context = _skinPaintContext()
    if context:
        cmds.artAttrSkinPaintCtx(context, edit=True, skinPaintMode=1,
                                 clear=True)


def CopyWeight(*arr):
    mel.eval(r'''
        if (!`exists NLTA_CopyWeight`)
        {
            global proc NLTA_CopyWeight()
            {
                string $sel[] = `ls -os -fl`;
                if (size($sel) < 2)
                {
                    warning "Select one source vertex and one or more destination vertices.";
                    return;
                }
                string $source = $sel[0];
                select -r $source;
                CopyVertexSkinWeights;

                select -cl;
                for ($i = 1; $i < size($sel); $i++)
                {
                    select -add $sel[$i];
                }
                PasteVertexSkinWeights;
            }
        }
        NLTA_CopyWeight();
        repeatLast
            -ac "NLTA_CopyWeight"
            -acl "Copy Vertex Weight";
    ''')


def SwitchBrush(*arr):
    ctx = cmds.currentCtx()
    if cmds.contextInfo(ctx, c=True) == "artAttrSkin":
        value = cmds.artAttrSkinPaintCtx(ctx,q=True,value=True)
        newValue =  value * (-1)
        AddWeight(newValue)
        cmds.artAttrSkinPaintCtx(ctx,e=True,value=newValue)        
        
def CopyRatio(*arr):
    sels = cmds.ls(orderedSelection=True,flatten=True)
    if len(sels) >= 2:
        vertSource = sels[0]
        vertTarget = sels[1:]
        mesh = NLTA_Mesh.GetMesh()[0]        
        skinData = NLTA_General.GetSkinData(mesh)
        jointsWeight = NLTA_Skinning.GetJointsWeight({
            "skinCluster":skinData["skinCluster"],
            "vert":vertSource,
            "joints":skinData["jointsUnlock"]
        })
        ratios = []
        for jointUnlock in skinData["jointsUnlock"]:
            ratios.append(jointsWeight[jointUnlock]["ratio"])
        for vertTemp in vertTarget:
            NLTA_GraphSkinning.WeightFromRatio({
                "skinCluster":skinData["skinCluster"],
                "vert":vertTemp,
                "joints":skinData["jointsUnlock"],
                "ratios":ratios
            })
        cmds.skinCluster(skinData["skinCluster"], e=True, forceNormalizeWeights=True)
        NLTA_GraphSkinning.UpdateView()

