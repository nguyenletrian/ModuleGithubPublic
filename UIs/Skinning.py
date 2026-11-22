import os
import sys
import json
import shutil
import importlib
import maya.utils
import maya.cmds as cmds
import maya.mel as mel
import pymel.core as pm
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

import xml.dom.minidom as xd
import xml.etree.ElementTree as ET
from functools import partial
from math import pow,sqrt


currentFile = os.path.abspath(__file__)
currentFolder = os.path.dirname(currentFile)
for folder in ["SkinningTools"]:
    folderTemp = os.path.join(currentFolder,folder)
    if folderTemp not in sys.path:
        sys.path.insert(0, folderTemp)



import NLTA_General,NLTA_Mesh, NLTA_Brush,NLTA_Set,NLTA_Proxy,NLTA_Keyframes,NLTA_BlendShape
import NLTA_Graph,NLTA_GraphSkinning,NLTA_Skinning,NLTA_Skinning_Eyelid,NLTA_Skinning_Transfer
for module in [
    NLTA_General, NLTA_Mesh, NLTA_Brush,NLTA_Set,NLTA_Proxy,NLTA_Keyframes,NLTA_BlendShape,
    NLTA_Graph,NLTA_GraphSkinning,NLTA_Skinning,NLTA_Skinning_Eyelid,NLTA_Skinning_Transfer
]:
    importlib.reload(module)


###################
UIs = {
    "animationDistance":None,
}

def _board_tools():
    return {
        "NLTA_General": NLTA_General,
        "NLTA_Mesh": NLTA_Mesh,
        "NLTA_Brush": NLTA_Brush,
        "NLTA_Set": NLTA_Set,
        "NLTA_Proxy": NLTA_Proxy,
        "NLTA_Keyframes": NLTA_Keyframes,
        "NLTA_BlendShape": NLTA_BlendShape,
        "NLTA_GraphSkinning": NLTA_GraphSkinning,
        "NLTA_Skinning": NLTA_Skinning,
        "NLTA_Skinning_Eyelid": NLTA_Skinning_Eyelid,
        "NLTA_Skinning_Transfer": NLTA_Skinning_Transfer,
    }



def OpenWindow(*args):
    """Open Skinning directly, without creating or displaying NLTA_Form."""
    import NLTA_Skinning_CommandBoard
    return NLTA_Skinning_CommandBoard.OpenWindow(_board_tools(), UIs)


def CreateUI(data):
    """Legacy loader entry point: open Skinning directly without a Maya form."""
    return OpenWindow()
