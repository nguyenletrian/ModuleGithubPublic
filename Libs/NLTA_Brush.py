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
        selectedattroper=operation, stampProfile="solid",
        minvalue=-1.0, value=float(value), opacity=1.0)
    return True


def ReplaceWeight(value, *arr):
    """Set the absolute Paint Skin brush Value (Set 0 / Set 1)."""
    return _setBrushValue(value, "absolute")


def AddWeight(value, *arr):
    """Set Paint Skin Add operation and Value, without changing mesh weights."""
    return _setBrushValue(value, "additive")


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
    # Work on the known Paint Skin context; contextInfo may differ by Maya version.
    ctx = _skinPaintContext()
    if not ctx:
        return False
    value = cmds.artAttrSkinPaintCtx(ctx, query=True, value=True)
    newValue = -float(value)

    # Use the original MEL UI update when Maya's native controls are available.
    # Standalone NLTA Skinning does not require Tool Settings to be open.
    try:
        mel.eval('artAttrSkinPaintModePaintSelect 1 artAttrSkinPaintCtx;')
        mel.eval('artAttrPaintOperation artAttrSkinPaintCtx Add;')
        mel.eval('artSkinSetSelectionValue {} false artAttrSkinPaintCtx artAttrSkin;'.format(newValue))
    except RuntimeError:
        pass

    # Apply the value even when the native Paint Skin UI does not exist.
    cmds.artAttrSkinPaintCtx(ctx, edit=True, skinPaintMode=1,
                             selectedattroper="additive",
                             minvalue=-1.0, value=newValue, opacity=1.0)
    return newValue

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

