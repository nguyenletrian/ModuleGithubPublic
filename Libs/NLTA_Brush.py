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


def _setBrushValue(value, operation):
    """Configure the Paint Skin brush; do not edit selected vertex weights."""
    context = _skinPaintContext()
    if not context:
        return False
    cmds.artAttrSkinPaintCtx(
        context, edit=True, skinPaintMode=1,
        selectedattroper=operation, value=float(value))
    return True


def ReplaceWeight(value, *arr):
    """Set the absolute Paint Skin brush Value (Set 0 / Set 1)."""
    return _setBrushValue(value, "absolute")


def AddWeight(value, *arr):
    """Add the supplied delta to selected vertex weights as in MayaScriptNew."""
    context = _skinPaintContext()
    if not context:
        return False
    value = float(value)
    cmds.artAttrSkinPaintCtx(
        context, edit=True, skinPaintMode=1,
        selectedattroper="additive", value=value)

    # Preserve the original MayaScriptNew Artisan selection edit when loaded.
    if mel.eval('exists "artSkinSetSelectionValue"'):
        mel.eval(
            "artSkinSetSelectionValue {} false artAttrSkinPaintCtx artAttrSkin;"
            .format(value))
        return True

    # Standalone NLTA must also work without showing Maya Tool Settings:
    # apply the same relative change to the selected vertices only.
    session = NLTA_Skinning.EnsureSkinSession(warn=False)
    skin = session["skinCluster"] if session else None
    influence = NLTA_Skinning.GetActivePaintJoint(skin) if skin else None
    verts = [v for v in (cmds.ls(selection=True, long=True,
                                 flatten=True) or []) if ".vtx[" in v]
    if not skin or not influence or not verts:
        cmds.warning("Add Weight: select vertices on a skinned mesh.")
        return False
    if cmds.objExists(influence + ".liw") and cmds.getAttr(influence + ".liw"):
        cmds.warning("Add Weight: active influence is locked: " + influence)
        return False
    for vert in verts:
        old_weight = float(cmds.skinPercent(
            skin, vert, query=True, transform=influence))
        new_weight = max(0.0, min(1.0, old_weight + value))
        cmds.skinPercent(
            skin, vert, transformValue=(influence, new_weight))
    cmds.refresh(force=True)
    return True


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
        # Switch Brush changes the paint value, not the selected skin weights.
        _setBrushValue(newValue, "additive")        
        
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

