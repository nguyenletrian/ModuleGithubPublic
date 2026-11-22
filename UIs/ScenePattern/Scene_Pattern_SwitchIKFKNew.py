import os
import importlib
import inspect
import ast
import re
import sys
import json
import copy
import maya.cmds as cmds
import pymel.core as pm
import maya.api.OpenMaya as om
from functools import partial
from datetime import datetime


import NLTA_General,NLTA_UI,NLTA_ScriptJob
for module in [NLTA_General,NLTA_UI,NLTA_ScriptJob]:
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
    name = "New Switch IK FK"
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
                "switchControl": "FKIKLeg_R",
                "switchAttr": "FKIKBlend",
                "valueActive": "0",
                "refObjects": "IKLeg_R\nPoleLeg_R",
                "sources": "FKHip_R\nFKKnee_R\nFKAnkle_R",
                "targets": "Hip_R\nKnee_R\nAnkle_R",
                "mirror": True
            },
            {
                "controlParent":"Main",
                "switchControl":"FKIKLeg_R",
                "switchAttr":"FKIKBlend",
                "valueActive":"10",
                "refObjects":"FKHip_R\nFKKnee_R\nFKAnkle_R",
                "sources":"PoleLeg_R\nIKLeg_R",
                "targets":"Knee_R\nAnkle_R",
                "mirror": True
            },
            {
                "controlParent":"Main",
                "switchControl":"FKIKArm_R",
                "switchAttr":"FKIKBlend",
                "valueActive":"0",
                "refObjects":"IKArm_R\nPoleArm_R",
                "sources":"FKShoulder_R\nFKElbow_R\nFKWrist_R",
                "targets":"Shoulder_R\nElbow_R\nWrist_R",
                "mirror": True
            },
            {
                "controlParent": "Main",
                "switchControl": "FKIKArm_R",
                "switchAttr": "FKIKBlend",
                "valueActive": "10",
                "refObjects": "FKShoulder_R\nFKElbow_R\nFKWrist_R",
                "sources": "PoleArm_R\nIKArm_R",
                "targets": "Elbow_R\nWrist_R",
                "mirror": True
            }
        ]
        for ASData in ASDatas:
            Add(listUI,ASData)

    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]
    cmds.rowColumnLayout(numberOfColumns=3,parent=buttonUI)
    cmds.button(label="Add",width=130,c=partial(Add,listUI,{}))
    cmds.button(label="Save", width=130,c=partial(Save,data))
    cmds.button(label="Run",width=110,c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=110,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.button(label="Add AS",width=100,c=partial(AddAS,listUI))
    cmds.setParent("..")
    Load(data,listUI)


def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def _mirror_name(name):
    swap = {
        "L": "R", "R": "L",
        "l": "r", "r": "l",
        "Left": "Right", "Right": "Left",
        "left": "right", "right": "left",
        "LEFT": "RIGHT", "RIGHT": "LEFT",
        "Lf": "Rt", "Rt": "Lf",
        "lf": "rt", "rt": "lf",
        "LF": "RT", "RT": "LF",
    }
    patterns = [
        # _L_  _R_
        r'(?<=_)(L|R|l|r)(?=_)',
        # Hand_L
        r'(?<=_)(L|R|l|r)$',
        # L_Hand
        r'^(L|R|l|r)(?=_)',
        # _Left_
        r'(?<=_)(Left|Right|left|right|LEFT|RIGHT)(?=_)',
        # Hand_Left
        r'(?<=_)(Left|Right|left|right|LEFT|RIGHT)$',
        # Left_Hand
        r'^(Left|Right|left|right|LEFT|RIGHT)(?=_)',
        # _Lf_ _Rt_
        r'(?<=_)(Lf|Rt|lf|rt|LF|RT)(?=_)',
        # Hand_Lf
        r'(?<=_)(Lf|Rt|lf|rt|LF|RT)$',
        # Lf_Hand
        r'^(Lf|Rt|lf|rt|LF|RT)(?=_)',
        # RigRArm RigLArm
        r'(?<=Rig)(L|R|l|r)',
        # RigRightArm
        r'(?<=Rig)(Left|Right|left|right|LEFT|RIGHT)',
        # RigLfArm
        r'(?<=Rig)(Lf|Rt|lf|rt|LF|RT)',
        # RightArm LeftArm (camelCase/PascalCase)
        r'^(Left|Right|left|right|LEFT|RIGHT)',
        # LArm RArm
        r'^(L|R|l|r)(?=[A-Z])',
        # LfArm RtArm
        r'^(Lf|Rt|lf|rt|LF|RT)(?=[A-Z])',
    ]
    for pattern in patterns:
        m = re.search(pattern, name)
        if m:
            value = m.group(1)
            start, end = m.span(1)
            return name[:start] + swap[value] + name[end:]
    return name


def BuildSwitchIKFKNew(datas):
    """Reproduce the original snap-data, matrix offsets and Maya scriptJob."""
    def CtrlUI(*arr):
        if cmds.objExists("Rig_UI"):
            return "Rig_UI"

        curve = cmds.createNode("transform", n="Rig_UI")
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

        # Create shapes and parent into Rig_UI
        for points in shapesData:
            temp = cmds.curve(d=1, p=points)
            shape = cmds.listRelatives(temp, s=True, ni=True)[0]

            cmds.parent(shape, curve, s=True, r=True)
            cmds.delete(temp)

        # Setup shapes
        shapes = cmds.listRelatives(curve, s=True, ni=True) or []
        for i, shape in enumerate(shapes):
            newShape = "{}Shape{}".format(curve, i + 1) if i else "{}Shape".format(curve)
            shape = cmds.rename(shape, newShape)
            cmds.setAttr(shape + ".isHistoricallyInteresting", 0)
            cmds.setAttr(shape + ".overrideEnabled", 1)
            cmds.setAttr(shape + ".overrideColor", 17)
            
        # Lock transforms
        for attr in ["tx", "ty", "tz","rx", "ry", "rz","sx", "sy", "sz","v"]:
            cmds.setAttr(curve + "." + attr,lock=True,keyable=False,channelBox=False)

        # Add Snap IK/FK attribute
        if not cmds.attributeQuery("snapIKFK", node=curve, exists=True):
            cmds.addAttr(curve, ln="snapIKFK", at="bool", dv=0, keyable=True)

        return curve

    def CreateDataNode(nodeName):
        rigUI = "Rig_UI"
        if cmds.objExists(nodeName):
            cmds.delete(nodeName)
        node = cmds.createNode("network", n=nodeName)
        if not cmds.attributeQuery("rigUI", node=nodeName, exists=True):
            cmds.addAttr(nodeName, ln="rigUI", at="message")
        cmds.connectAttr(
            "{}.message".format(rigUI),
            "{}.rigUI".format(nodeName),
            force=True
        )
        
    def AddData(data):
        jsonString = json.dumps(data, indent=2)
        node = "NLTA_DataNode"
        attr = "IKFKData"
        if not cmds.attributeQuery(attr, node=node, exists=True):
            cmds.addAttr(node, ln=attr, dt="string")
        cmds.setAttr("{}.{}".format(node, attr),jsonString,type="string")

    def CreateScriptNode(nodeName,mainControl,windowString):        
        if not cmds.attributeQuery("IKFKSnapWindow", node=nodeName, exists=True):
            cmds.addAttr(nodeName, ln="IKFKSnapWindow", dt="string")
        cmds.setAttr("{}.IKFKSnapWindow".format(nodeName),windowString,type="string")   
        if cmds.objExists("NLTA_RebuildSnapJob"):
            cmds.delete("NLTA_RebuildSnapJob")
        cmds.scriptNode(n="NLTA_RebuildSnapJob",st=2,bs="""
string $all[] = `ls`;
string $node = "";

for ($n in $all)
{
    string $parts[];
    tokenize($n, ":", $parts);

    if ($parts[size($parts)-1] == "NLTA_DataNode")
    {
        $node = $n;
        break;
    }
}

if ($node != "")
{
    string $code = `getAttr ($node + ".IKFKSnapWindow")`;
    python($code);
}
        """)

        

    mainControl = 'Rig_UI'
    nodeName = "NLTA_DataNode"
    windowString = rf'''
import json
import maya.cmds as cmds
import maya.api.OpenMaya as om
from functools import partial

mainControl = [n for n in cmds.ls() if n.rsplit(":", 1)[-1] == "{mainControl}"][0]
mainControlAttr = mainControl+".snapIKFK"
nodeName = [n for n in cmds.ls() if n.rsplit(":", 1)[-1] == "{nodeName}"][0]

def callback():
    mainControl = [n for n in cmds.ls() if n.rsplit(":", 1)[-1] == "{mainControl}"][0]
    mainControlAttr = mainControl+".snapIKFK"
    nodeName = [n for n in cmds.ls() if n.rsplit(":", 1)[-1] == "{nodeName}"][0]
    def CreateWindow(*arr):
        def FindObject(name):
            objs = [n for n in cmds.ls() if n.rsplit(":", 1)[-1] == name]
            return objs[0] if objs else None

        def WorldPosition(obj):
            # World-space joint position; no assumed X/Y/Z rotation plane.
            return om.MVector(*cmds.xform(obj, q=True, ws=True, t=True))

        def PoleFrom3Joints(shoulder, elbow, wrist, poleControl):
            # The FK bend plane is derived from the THREE joint positions.
            # For a nearly straight chain the plane becomes ambiguous: use
            # the current pole direction, then a joint-local axis as backup.
            s = WorldPosition(shoulder)
            e = WorldPosition(elbow)
            w = WorldPosition(wrist)
            oldPole = WorldPosition(poleControl)
            upperLength = (e - s).length()
            lowerLength = (w - e).length()
            chainLength = upperLength + lowerLength
            if chainLength < 1.0e-8:
                return None

            axis = w - s
            if axis.length() < chainLength * 1.0e-7:
                axis = e - s
            if axis.length() < 1.0e-8:
                return None
            axis = axis.normal()

            projectedElbow = s + axis * ((e - s) * axis)
            bendDirection = e - projectedElbow
            tolerance = max(chainLength * 1.0e-4, 1.0e-7)
            if bendDirection.length() <= tolerance:
                # At full extension the 3 points do not define a unique plane.
                # Maintain the previously animated pole's plane if possible.
                bendDirection = oldPole - s
                bendDirection -= axis * (bendDirection * axis)
                if bendDirection.length() <= tolerance:
                    matrix = cmds.xform(elbow, q=True, ws=True, matrix=True)
                    for index in (0, 4, 8):
                        candidate = om.MVector(*matrix[index:index + 3])
                        candidate -= axis * (candidate * axis)
                        if candidate.length() > tolerance:
                            bendDirection = candidate
                            break
            if bendDirection.length() <= tolerance:
                return None

            # Keep the pole outside the chain; preserve a larger prior distance.
            distance = max(chainLength * 0.75, (oldPole - e).length())
            return e + bendDirection.normal() * distance

        def FindFKShoulder(node, snapData, targetsArray):
            # In Add AS, the opposite (IK -> FK) entry stores the full chain:
            # Shoulder, Elbow, Wrist. This avoids hardcoded rig joint names.
            try:
                allSnapData = json.loads(cmds.getAttr(node + ".IKFKData") or "[]")
            except (TypeError, ValueError, RuntimeError):
                return None
            for other in allSnapData:
                if other.get("switchControl") != snapData["switchControl"]:
                    continue
                if other.get("switchAttr") != snapData["switchAttr"]:
                    continue
                otherTargets = [x.strip() for x in other.get("targets", "").split("\n") if x.strip()]
                if len(otherTargets) >= 3 and otherTargets[-2:] == targetsArray:
                    return FindObject(otherTargets[-3])
            # For custom setups without the opposite snap entry, use the
            # elbow's parent joint as the shoulder when available.
            elbow = FindObject(targetsArray[0]) if targetsArray else None
            parents = cmds.listRelatives(elbow, p=True, type="joint", fullPath=True) if elbow else None
            return parents[0] if parents else None

        def Snap(snapData, *arr):
            node = FindObject("{nodeName}")
            switchControl = FindObject(snapData["switchControl"])
            if not node or not switchControl:
                return
            switchAttr = switchControl + "." + snapData["switchAttr"]
            sourcesArray = [x.strip() for x in snapData["sources"].split("\n") if x.strip()]
            targetsArray = [x.strip() for x in snapData["targets"].split("\n") if x.strip()]
            if len(sourcesArray) != len(targetsArray):
                cmds.warning("IKFK Snap: mismatched Sources/Targets count")
                return

            # Standard matrix snapping remains unchanged for FK controls / IK wrist.
            dataMatch = {{}}
            for source, target in zip(sourcesArray, targetsArray):
                sourceReal = FindObject(source)
                targetReal = FindObject(target)
                if not sourceReal or not targetReal:
                    cmds.warning("IKFK Snap: missing source or target: " + source + " / " + target)
                    return
                matrixAttr = node + "." + source + "_Matrix"
                if not cmds.objExists(matrixAttr):
                    cmds.warning("IKFK Snap: missing matrix offset " + matrixAttr)
                    return
                targetMatrix = om.MMatrix(cmds.getAttr(targetReal + ".worldMatrix[0]"))
                offset = om.MMatrix(cmds.getAttr(matrixAttr))
                dataMatch[sourceReal] = offset * targetMatrix

            # FK -> IK in Add AS has two sources: [Pole, IK Wrist],
            # targeting [Elbow, Wrist]. Compute Pole separately in true 3D.
            poleControl = None
            polePosition = None
            if len(sourcesArray) == 2 and len(targetsArray) == 2:
                shoulder = FindFKShoulder(node, snapData, targetsArray)
                poleControl = FindObject(sourcesArray[0]) if shoulder else None
                elbow = FindObject(targetsArray[0]) if shoulder else None
                wrist = FindObject(targetsArray[1]) if shoulder else None
                if poleControl and elbow and wrist:
                    polePosition = PoleFrom3Joints(shoulder, elbow, wrist, poleControl)
                    if polePosition is None:
                        cmds.warning("IKFK Snap: FK bend plane is undefined; using original Pole offset")

            # Capture all transforms BEFORE switching to avoid FK/IK feedback.
            cmds.setAttr(switchAttr, int(snapData["valueActive"]))
            if poleControl and polePosition is not None:
                # Set the bend plane first, then place the IK wrist into it.
                # Position only: pole controls need not share elbow orientation.
                cmds.xform(poleControl, ws=True,
                           t=(polePosition.x, polePosition.y, polePosition.z))
            for sourceReal, matrix in dataMatch.items():
                if sourceReal == poleControl and polePosition is not None:
                    continue
                cmds.xform(sourceReal, ws=True, matrix=list(matrix))

            selectIndex = 1 if len(sourcesArray) == 2 else 2
            if len(sourcesArray) > selectIndex:
                selectObj = FindObject(sourcesArray[selectIndex])
                if selectObj:
                    cmds.select(selectObj)

        def Run(*arr):
            objs = cmds.ls(selection=True)
            if not objs:
                return
            node = FindObject("{nodeName}")
            if not node:
                return
            jsonString = cmds.getAttr(node + ".IKFKData")
            snapDatas = json.loads(jsonString)
            snapWorks = []
            for snapData in snapDatas:
                switchControlName = snapData["switchControl"]
                switchControl = FindObject(switchControlName)
                if not switchControl:
                    continue
                switchAttr = switchControl + "." + snapData["switchAttr"]
                valueActive = int(snapData["valueActive"])
                currentValue = int(cmds.getAttr(switchAttr))
                refs = snapData["refObjects"].split("\n") + [switchControlName]
                for obj in objs:
                    shortName = obj.rsplit(":", 1)[-1]
                    if shortName in refs and valueActive != currentValue:
                        snapWorks.append(snapData)
                        break
            for snapWork in snapWorks:
                Snap(snapWork)

        mainControl = [n for n in cmds.ls() if n.rsplit(":", 1)[-1] == "{mainControl}"][0]
        mainControlAttr = mainControl+".snapIKFK"
        nodeName = [n for n in cmds.ls() if n.rsplit(":", 1)[-1] == "{nodeName}"][0]

        if cmds.window("SnapIKFK", exists=True):
            cmds.deleteUI("SnapIKFK")

        win = cmds.window("SnapIKFK",title="Snap IK/FK",width=130,sizeable=True)
        cmds.columnLayout(adjustableColumn=True)
        cmds.button(label="Snap",command=Run,height=40)
        cmds.showWindow(win)
        cmds.window(win,e=True,widthHeight=(130, 40))

    if cmds.getAttr(mainControlAttr)==1:
        CreateWindow()
        cmds.setAttr(mainControlAttr, 0)

cmds.scriptJob(
    attributeChange=[
        mainControlAttr,
        callback
    ],
    protected=True
)

''' 
    expandedDatas = []
    for itemData in datas:
        sourcesArray = itemData["sources"].split("\n")
        targetsArray = itemData["targets"].split("\n")
        valid = True
        for source, target in zip(sourcesArray, targetsArray):
            if not cmds.objExists(source):
                cmds.warning("Source does not exist: {}".format(source))
                valid = False
                break
            if not cmds.objExists(target):
                cmds.warning("Target does not exist: {}".format(target))
                valid = False
                break
        if not valid:
            continue

        expandedDatas.append(itemData)
        if not itemData.get("mirror"):
            continue
        mirrorData = copy.deepcopy(itemData)
        mirrorFields = [
            "switchControl",
            "sources",
            "targets",
            "refObjects",
        ]
        for field in mirrorFields:
            if field not in mirrorData:
                continue
            value = mirrorData[field]
            if not value:
                continue
            if "\n" in str(value):
                mirrorData[field] = "\n".join(
                    _mirror_name(x)
                    for x in value.split("\n")
                    if x.strip()
                )
            else:
                mirrorData[field] = _mirror_name(value)
        expandedDatas.append(mirrorData)

    if expandedDatas:
        CtrlUI()
        CreateDataNode(nodeName)
        CreateScriptNode(nodeName,mainControl,windowString)    
        AddData(expandedDatas)
        for itemData in expandedDatas:
            if "controlParent" in itemData:
                try:
                    cmds.parent(mainControl,itemData["controlParent"])
                except:pass
            sourcesArray = itemData["sources"].split("\n")
            targetsArray = itemData["targets"].split("\n")
            for i in range(len(sourcesArray)):
                source = sourcesArray[i]
                target = targetsArray[i]
                if not cmds.attributeQuery(source+"_Matrix", node=nodeName, exists=True):
                    cmds.addAttr(nodeName, ln=source+"_Matrix", at="matrix")
                targetMtx = om.MMatrix(cmds.getAttr(target + ".worldMatrix[0]"))
                sourceMtx = om.MMatrix(cmds.getAttr(source + ".worldMatrix[0]"))
                offset = sourceMtx * targetMtx.inverse()
                cmds.setAttr(nodeName+"."+source+"_Matrix",list(offset),type="matrix")
        exec(windowString)


def Run(data, *args):
    return BuildSwitchIKFKNew(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("SwitchIKFKNew Export: no saved items")
        return None

    # Serialize the active rig builder, preserving the embedded runtime Snap code.
    helpers = (_mirror_name, BuildSwitchIKFKNew)
    source_tree = ast.parse("\n\n".join(inspect.getsource(func).rstrip() for func in helpers))
    body = ast.unparse(source_tree)
    # Standalone main() uses local imports; an exec-created scriptJob callback
    # must retain its own global namespace after main() has returned.
    if body.count("exec(windowString)") != 1:
        raise ValueError("Expected one embedded snap-window initialization")
    body = body.replace(
        "exec(windowString)",
        "exec(windowString, {'cmds': cmds, 'om': om, 'json': json})"
    )
    # The code of each Maya command must remain on one physical line.
    rows = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    script = (
        "def main():\n"
        "    import re\n"
        "    import json\n"
        "    import copy\n"
        "    import maya.cmds as cmds\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    # SwitchIKFKNew data\n"
        "    SNAP_DATA = " + rows + "\n\n"
        + "    # Define the mirror matcher and original snap setup.\n"
        + body
        + "\n\n    # Store matrix offsets and register the original Snap job.\n"
        + "    BuildSwitchIKFKNew(SNAP_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in script:
        script = script.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as f:
        f.write(script)
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
    cmds.textField(text="Switch Control",editable=False)
    itemData["switchControl"] = cmds.textField(text=data.get("switchControl",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["switchControl"]))
    cmds.setParent("..")
    
    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Switch Attribute",editable=False)
    itemData["switchAttr"] = cmds.textField(text=data.get("switchAttr",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrOnly,itemData["switchAttr"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Value Active",editable=False)
    itemData["valueActive"] = cmds.textField(text=data.get("valueActive",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["valueActive"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Ref Objects",editable=False)
    itemData["refObjects"] = cmds.scrollField(text=data.get("refObjects",""),height=65)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["refObjects"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Sources",editable=False)
    itemData["sources"] = cmds.scrollField(text=data.get("sources","Controls..."),height=65)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["sources"]))
    cmds.setParent("..")



    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,100),(2,235),(3,32)])
    cmds.textField(text="Targets",editable=False)
    itemData["targets"] = cmds.scrollField(text=data.get("targets","Joints..."),height=65)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["targets"]))
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










