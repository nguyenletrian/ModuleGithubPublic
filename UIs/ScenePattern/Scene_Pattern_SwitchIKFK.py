import os
import inspect
import ast
import sys
import SnapIKFK
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
from datetime import datetime

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
    name = "Default Switch IK FK"
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

def Form(data,*args):
    def Save(data,*args):
        itemData = NLTA_General.JsonGetByID({
            "path": data["sceneDataPath"]+"/ScenePatternData.json",
            "id": data["id"]
        })
        saveData = NLTA_UI.GetData(ITEMS["items"])
        NLTA_General.writeJsonFile(itemData["path"],saveData)

    def SaveAndExport(*args):
        Save(data)
        ExportPython(data)

    def AddAS(listUI,*arr):
        ASDatas = [
            {
                "controlParent": "Main",
                "controlSwitch": "FKIKLeg_R",
                "attributeSwitch": "FKIKBlend",
                "fkActive": "0",
                "ikActive": "10",
                "controlUpper": "",
                "controlFK": "FKHip_R\nFKKnee_R\nFKAnkle_R",
                "controlIK": "IKLeg_R\nPoleLeg_R",
                "controlRoll": "",
                "jointIK": "IKXHip_R\nIKXKnee_R\nIKXAnkle_R",
                "mirror":True
            },
            {
                "controlParent": "Main",
                "controlSwitch": "FKIKArm_R",
                "attributeSwitch": "FKIKBlend",
                "fkActive": "0",
                "ikActive": "10",
                "controlUpper": "",
                "controlFK": "FKShoulder_R\nFKElbow_R\nFKWrist_R",
                "controlIK": "IKArm_R\nPoleArm_R",
                "controlRoll": "",
                "jointIK": "IKXShoulder_R\nIKXElbow_R\nIKXWrist_R",
                "mirror":True
            }
        ]
        for ASData in ASDatas:
            Add(listUI,ASData)


    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]
    cmds.rowColumnLayout(numberOfColumns=2,parent=buttonUI)
    cmds.button(label="Add",width=130,c=partial(Add,listUI,{}))
    cmds.button(label="Save", width=130,c=partial(Save,data))
    cmds.button(label="Run",width=110,c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=110,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.button(label="Add AS",width=100,c=partial(AddAS,listUI))
    cmds.setParent("..")
    Load(data,listUI)

def SetFKIKShape(ctrl, color=14):
    if not cmds.objExists(ctrl):
        return

    # Delete old curve shapes
    oldShapes = cmds.listRelatives(ctrl, s=True, ni=True, f=True) or []
    for shape in oldShapes:
        if cmds.nodeType(shape) == "nurbsCurve":
            cmds.delete(shape)

    shapesData = [
        [
            (-10.033802509307861, 0, -5.972314834594727),
            (-16.7083477973938, 0, -5.972314834594727),
            (-16.7083477973938, 0, 5.972314834594727),
            (-15.013471603393555, 0, 5.972314834594727),
            (-15.013471603393555, 0, 0.5488438606262207),
            (-10.832810401916504, 0, 0.5488438606262207),
            (-10.832810401916504, 0, -0.7020654678344727),
            (-15.013471603393555, 0, -0.7020654678344727),
            (-15.013471603393555, 0, -4.705206871032715),
            (-10.033802509307861, 0, -4.705206871032715),
            (-10.033802509307861, 0, -5.972314834594727),
        ],
        [
            (-6.192810535430908, 0, -5.972314834594727),
            (-7.7827277183532715, 0, -5.972314834594727),
            (-7.7827277183532715, 0, 5.972314834594727),
            (-6.192810535430908, 0, 5.972314834594727),
            (-6.192810535430908, 0, -0.08074331283569336),
            (-0.9709925651550293, 0, 5.972314834594727),
            (1.171156406402588, 0, 5.972314834594727),
            (-4.33363676071167, 0, -0.27314043045043945),
            (0.34504175186157227, 0, -5.972314834594727),
            (-1.3584303855895996, 0, -5.972314834594727),
            (-6.192810535430908, 0, -0.09677648544311523),
            (-6.192810535430908, 0, -5.972314834594727),
        ],
        [
            (4.647850513458252, 0, -5.972314834594727),
            (2.952974796295166, 0, -5.972314834594727),
            (2.952974796295166, 0, 5.972314834594727),
            (4.647850513458252, 0, 5.972314834594727),
            (4.647850513458252, 0, -5.972314834594727),
        ],
        [
            (9.344379901885986, 0, -5.972314834594727),
            (7.754461765289307, 0, -5.972314834594727),
            (7.754461765289307, 0, 5.972314834594727),
            (9.344379901885986, 0, 5.972314834594727),
            (9.344379901885986, 0, -0.08074331283569336),
            (14.566196918487549, 0, 5.972314834594727),
            (16.7083477973938, 0, 5.972314834594727),
            (11.203552722930908, 0, -0.27314043045043945),
            (15.882233142852783, 0, -5.972314834594727),
            (14.178761005401611, 0, -5.972314834594727),
            (9.344379901885986, 0, -0.09677648544311523),
            (9.344379901885986, 0, -5.972314834594727),
        ],
    ]

    for points in shapesData:
        temp = cmds.curve(d=1, p=points)
        shape = cmds.listRelatives(temp, s=True, ni=True)[0]
        cmds.parent(shape, ctrl, s=True, r=True)
        cmds.delete(temp)

    # Rename shapes
    shapes = cmds.listRelatives(ctrl, s=True, ni=True) or []
    for i, shape in enumerate(shapes):
        name = "{}Shape{}".format(ctrl, i + 1) if i else "{}Shape".format(ctrl)
        shape = cmds.rename(shape, name)
        cmds.setAttr(shape + ".overrideEnabled", 1)
        cmds.setAttr(shape + ".overrideColor", color)
        cmds.setAttr(shape + ".visibility", keyable=False)
    cmds.select(ctrl)

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def BuildLegacySwitchIKFK(datas):
    """Preserve original SnapIKFK GUI setup and per-record switch creation."""
    tool = SnapIKFK.SetupSnapIKFK()

    controlExist = False
    for itemData in datas:
        cmds.textFieldButtonGrp("TF_ctrlParentUI",e=True,text=itemData.get("controlParent", ""))
        if controlExist == False:
            cmds.radioButtonGrp('TF_ctrlTypeUI',e=True,select=2)
            controlExist = True
        else:
            cmds.radioButtonGrp('TF_ctrlTypeUI',e=True,select=1)


        cmds.textFieldButtonGrp("TF_ctrlSwitchMode",e=True,text=itemData.get("controlSwitch", ""))
        cmds.textFieldGrp('TF_handAttr',e=True,text=itemData.get("attributeSwitch", ""))
        cmds.intFieldGrp('IF_fkValue',e=True,value1=int(itemData.get("fkActive", 0)))
        cmds.intFieldGrp('IF_ikValue',e=True,value1=int(itemData.get("ikActive", 1)))
        cmds.textFieldButtonGrp("TF_ctrlUpper",e=True,text=itemData.get("controlUpper", ""))
        cmds.textFieldButtonGrp("TF_ctrlFK",e=True,text=itemData.get("controlFK", "").replace("\n", ", "))
        cmds.textFieldButtonGrp("TF_ctrlIK",e=True,text=itemData.get("controlIK", "").replace("\n", ", "))
        cmds.textFieldButtonGrp("TF_ctrlRollToes",e=True,text=itemData.get("controlRoll", ""))
        cmds.textFieldButtonGrp("TF_jointIK",e=True,text=itemData.get("jointIK", "").replace("\n", ", "))
        cmds.checkBox('CB_mirror',e=True,value=itemData.get("mirror", False) )

        tool.ctrlParentUI = itemData.get("controlParent", "")
        tool.dict_query_select = {
            "attrBlend": itemData.get("attributeSwitch", ""),
            "fkMode": int(itemData.get("fkActive", 0)),
            "ikMode": int(itemData.get("ikActive", 1)),
        }
        # Control Upper
        if itemData.get("controlUpper"):
            tool.dict_query_select["ctrlUpper"] = [
                itemData["controlUpper"]
            ]
        # FK Controls
        fk_list = [
            x.strip()
            for x in itemData.get("controlFK", "").split("\n")
            if x.strip()
        ]
        if fk_list:
            tool.dict_query_select["ctrlFK"] = fk_list

        # IK Controls
        ik_list = [
            x.strip()
            for x in itemData.get("controlIK", "").split("\n")
            if x.strip()
        ]

        if ik_list:
            tool.dict_query_select["ctrlIK"] = ik_list

        # IK Joints
        joint_list = [
            x.strip()
            for x in itemData.get("jointIK", "").split("\n")
            if x.strip()
        ]

        if joint_list:
            tool.dict_query_select["jointIK"] = joint_list

        # Roll Toes
        if itemData.get("controlRoll"):
            tool.dict_query_select["RollToes"] = [
                itemData["controlRoll"]
            ]

        # Switch Control
        switch_ctrl = (
            itemData.get("controlSwitch")
            or itemData.get("controlParent")
        )

        if switch_ctrl:
            tool.dict_query_select["ctrlSw"] = [switch_ctrl]
        
        tool.setupIKFK()

        SetFKIKShape("Rig_UI")
        
    cmds.deleteUI('ui_snapIKFK')


def Run(data, *args):
    return BuildLegacySwitchIKFK(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("SwitchIKFK Export: no saved items")
        return None

    # SnapIKFK (PyMEL based) is an explicit external runtime dependency.
    functions = (SetFKIKShape, BuildLegacySwitchIKFK)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions))
    code = ast.unparse(tree)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    saved = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import SnapIKFK\n\n"
        "    # Requires the original SnapIKFK library with PyMEL in Maya.\n"
        "    # SwitchIKFK data\n"
        "    SWITCH_DATA = " + saved + "\n\n"
        + code
        + "\n\n    # Run original GUI-driven IK/FK setup.\n"
        + "    BuildLegacySwitchIKFK(SWITCH_DATA)\n\n"
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
    os.startfile(os.path.dirname(_pattern_data_path(data)))


def Add(listUI,data,*args):
    global ITEMS
    def Delete(ui,*args):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS["items"][ui]
        ITEMS["order"].remove(ui)

    itemData = {}
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15,0.15,0.15))
    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Control Parent",editable=False)
    itemData["controlParent"] = cmds.textField(text=data.get("controlParent",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["controlParent"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Control Switch",editable=False)
    itemData["controlSwitch"] = cmds.textField(text=data.get("controlSwitch",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["controlSwitch"]))
    cmds.setParent("..")
    
    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Attribute Switch",editable=False)
    itemData["attributeSwitch"] = cmds.textField(text=data.get("attributeSwitch",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrOnly,itemData["attributeSwitch"]))
    cmds.setParent("..")


    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="FK Active",editable=False)
    itemData["fkActive"] = cmds.textField(text=data.get("fkActive",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["fkActive"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="IK Active",editable=False)
    itemData["ikActive"] = cmds.textField(text=data.get("ikActive",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["ikActive"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Control Upper",editable=False)
    itemData["controlUpper"] = cmds.textField(text=data.get("controlUpper",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["controlUpper"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Control FK",editable=False)
    itemData["controlFK"] = cmds.scrollField(text=data.get("controlFK",""),height=65)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["controlFK"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Control IK",editable=False)
    itemData["controlIK"] = cmds.scrollField(text=data.get("controlIK",""),height=65)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["controlIK"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Control Roll",editable=False)
    itemData["controlRoll"] = cmds.scrollField(text=data.get("controlRoll",""),height=65)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["controlRoll"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Joint IK",editable=False)
    itemData["jointIK"] = cmds.scrollField(text=data.get("jointIK",""),height=65)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["jointIK"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,245),(3,32)])
    cmds.textField(text="Mirror",editable=False)
    itemData["mirror"] = cmds.checkBox(value=data.get("mirror", True),label="")
    cmds.setParent("..")

    cmds.button(label="X",w=380,bgc=(0.5,0.2,0.2),c=partial(Delete,itemUI))
    cmds.setParent("..")
    cmds.setParent("..")

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)










