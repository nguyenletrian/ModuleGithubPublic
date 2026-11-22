import os
import importlib
import inspect
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
    name = "Create IK"
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

    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]

    def SaveAndExport(*args):
        Save(data)
        ExportPython(data)

    cmds.rowColumnLayout(numberOfColumns=4,parent=buttonUI)
    cmds.button(label="Add",width=100,c=partial(Add,listUI,{}))
    cmds.button(label="Save",width=100,c=partial(Save,data))
    cmds.button(label="Run",width=100,c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=110,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.setParent("..")
    Load(data,listUI)


def CreateDiamondCtrl(name, size=2.0):
    s = size
    points = [
        (0,  s, 0),     # Top
        ( s, 0, 0),
        (0, 0,  s),
        (-s, 0, 0),
        (0, 0, -s),
        ( s, 0, 0),
        (0, -s, 0),     # Bottom
        (0, 0,  s),
        (-s, 0, 0),
        (0, -s, 0),
        (0, 0, -s),
        ( s, 0, 0),
        (0,  s, 0),
        (0, 0,  s),
        (0, -s, 0),
        (0, 0, -s),
        (0,  s, 0),
        (-s, 0, 0),
        (0, -s, 0)
    ]
    ctrl = cmds.curve(d=1,p=points,n=name)
    return ctrl

def CreateCircleCtrl(name, radius=2, normal=(1, 0, 0)):
    return cmds.circle(n=name,nr=normal,r=radius,ch=False)[0]

def CreateCubeCtrl(name, size=2):
    s = size * 0.5
    points = [
        (-s,-s,-s),( s,-s,-s),( s, s,-s),(-s, s,-s),(-s,-s,-s),
        (-s,-s, s),( s,-s, s),( s, s, s),(-s, s, s),(-s,-s, s),
        ( s,-s, s),( s,-s,-s),
        ( s, s,-s),( s, s, s),
        (-s, s, s),(-s, s,-s)
    ]
    return cmds.curve(d=1,p=points,n=name)

def DuplicateChain(joints, suffix):
    root = cmds.duplicate(joints[0],rr=True,rc=True)[0]
    newJoints = [root]
    children = cmds.listRelatives(root,ad=True,type="joint",f=False) or []
    newJoints.extend(reversed(children))
    result = []
    for joint in newJoints:
        result.append(cmds.rename(joint,joint+suffix))
    return result


def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def _unique_name(name):
    """Choose a free Maya node name with the original numeric suffix rule."""
    if not cmds.objExists(name):
        return name
    index = 1
    while cmds.objExists(name + "_" + str(index)):
        index += 1
    return name + "_" + str(index)


def _group_match_object(obj, name):
    """Create a group matched to an object's translation, rotation and scale."""
    group = cmds.group(em=True, name=name)
    cmds.delete(cmds.parentConstraint(obj, group, mo=False))
    cmds.delete(cmds.scaleConstraint(obj, group, mo=False))
    return group


def _create_offset_group(obj, offset_name):
    """Match the active NLTA offset helper, including existing-group reuse."""
    parent = cmds.listRelatives(obj, parent=True)
    if parent and parent[0] == offset_name:
        return offset_name
    if cmds.objExists(offset_name):
        children = cmds.listRelatives(offset_name, children=True, fullPath=False) or []
        if obj in children:
            return offset_name
        offset_name = _unique_name(offset_name)
    offset = _group_match_object(obj, offset_name)
    if parent:
        cmds.parent(offset, parent[0])
    cmds.parent(obj, offset)
    return offset

def BuildCreateIK(datas):
    """Create the saved three-object IK/FK rig and its space switches."""
    if not datas:
        return
    for data in datas:
        parent = data["parent"]
        objects = [x for x in data["objects"].splitlines() if x.strip()]

        if len(objects) != 3:
            cmds.warning("This tool currently requires exactly 3 objects.")
            continue

        ### CREATE OBJECT OFFSET
        originOffsetGrps = []
        for obj in objects:
            originOffsetGrp = _create_offset_group(obj,obj+"_IKFKExtraOffset")
            originOffsetGrps.append(originOffsetGrp)
        
        ### CREATE GROUP CONTAIN
        grpContain = objects[0]+"_IKFKSystem"
        _group_match_object(parent,grpContain)
        cmds.parent(grpContain,parent)

        ### CREATE JOINTS ###        
        # Find pos
        pts = []
        for obj in objects:
            p = cmds.xform(obj, q=True, ws=True, t=True)
            pts.append(om.MVector(p))
        A, B, C = pts

        # Get Normal plane
        normal = ((B - A) ^ (C - B))
        if normal.length() < 0.0001:
            cmds.warning("Objects are collinear.")
            continue
        normal.normalize()

        # Create Joint
        joints = []
        connectGrps = []
        for obj, pos in zip(objects, pts):
            jnt = cmds.createNode("joint",n=obj + "_Jnt")
            cmds.xform(jnt,ws=True,t=(pos.x, pos.y, pos.z))
            joints.append(jnt)
            connectGrp = _group_match_object(obj,obj+"_ConnectGroup")
            connectGrps.append(connectGrp)

        # Match to plane
        forwards = [(B - A).normal(),(C - B).normal(),(C - B).normal()]
        for jnt, pos, x in zip(joints, pts, forwards):
            z = (x ^ normal).normal()
            y = (z ^ x).normal()
            matrix = [
                x.x, x.y, x.z, 0,
                y.x, y.y, y.z, 0,
                z.x, z.y, z.z, 0,
                pos.x,pos.y,pos.z,1
            ]
            cmds.xform(jnt,ws=True,matrix=matrix)

        # Parent joint
        cmds.parent(joints[2], joints[1])
        cmds.parent(joints[1], joints[0])
        if cmds.objExists(parent):
            cmds.parent(joints[0], grpContain)
        cmds.makeIdentity(joints[0],apply=True,rotate=True)


        jointFKs = DuplicateChain(joints,"_FK")
        jointIKs = DuplicateChain(joints,"_IK")

        # Parent ConnectGrp to joint:
        for i in range(len(connectGrps)):
            cmds.parent(connectGrps[i],joints[i])


        ### CREATE POLE VECTOR ###
        poleVectorName = objects[1]+"_PoleVector"
        mid = (A + C) * 0.5
        polePos = B + (B - mid)
        poleCtrl = CreateDiamondCtrl(poleVectorName)
        poleOffset = _create_offset_group(poleCtrl,poleCtrl+"_GrpOffset")
        cmds.xform(poleOffset,ws=True,t=(polePos.x, polePos.y, polePos.z))
        cmds.parent(poleOffset,grpContain)

        ### CREATE IK
        IKName = objects[2]+"_IK"
        IKOffset = IKName+"_GrpOffset"
        IKCtrl = CreateCubeCtrl(IKName,size=4)
        _create_offset_group(IKName,IKOffset)
        matrix = cmds.xform(joints[-1],q=True,ws=True, matrix=True)
        cmds.xform(IKOffset,ws=True,matrix=matrix)
        cmds.parent(IKOffset,grpContain)

        ### IK SPACE SWITCH
        if data["worldParent"]:
            worldParent = data["worldParent"]
            for ctrl, offset in [(IKCtrl, IKOffset),(poleCtrl, poleOffset)]:
                spaceGrp = _create_offset_group(offset,ctrl + "_IKFKSpaceSwitch")
                con = cmds.parentConstraint(parent,worldParent,spaceGrp,mo=True)[0]

                attr = "Space"
                if not cmds.attributeQuery(attr, node=ctrl, exists=True):
                    cmds.addAttr(ctrl,ln=attr,at="enum",enumName="Local:World",k=True)

                rev = cmds.createNode("reverse",n=ctrl + "_SpaceReverse")
                cmds.connectAttr(ctrl + "." + attr,rev + ".inputX",f=True)
                weights = cmds.parentConstraint(con,q=True,wal=True)
                cmds.connectAttr(rev + ".outputX",con + "." + weights[0],f=True)
                cmds.connectAttr(ctrl + "." + attr,con + "." + weights[1],f=True)


        ### CREATE FKS
        FKCtrls = []
        FKOffsets = []
        for i in range(len(joints)):
            joint = joints[i]
            FKName = objects[i]+"_FK"
            FKOffset = objects[i]+"_FKOffset"
            FKCtrl = CreateCircleCtrl(FKName,radius=2)
            _create_offset_group(FKCtrl,FKOffset)
            matrix = cmds.xform(joint,q=True,ws=True,matrix=True)
            cmds.xform(FKOffset,ws=True,matrix=matrix)
            FKCtrls.append(FKName)
            FKOffsets.append(FKOffset)
        for i in range(len(FKCtrls)-1):
            cmds.parent(FKOffsets[i+1],FKCtrls[i])
        cmds.parent(FKOffsets[0],grpContain)
        
        ### IK CONSTRAINT
        ikHandle, effector = cmds.ikHandle(sj=jointIKs[0],ee=jointIKs[-1],sol="ikRPsolver",n=jointIKs[0]+"_IKHandle")
        cmds.parent(ikHandle,IKCtrl)
        cmds.poleVectorConstraint(poleCtrl,ikHandle)
        cmds.orientConstraint(IKCtrl,jointIKs[-1],mo=True)

                
        ### FK CONSTRAINT
        for i in range(len(FKCtrls)):
            cmds.parentConstraint(FKCtrls[i],jointFKs[i])


        ### IK / FK SWITCH
        switchAttr = "SwitchIKFK"

        # Create IKFK attribute
        if not cmds.attributeQuery(switchAttr, node=IKCtrl, exists=True):
            cmds.addAttr(IKCtrl,ln=switchAttr,at="double",min=0,max=1,dv=1,k=True)
        
        # Proxy attrbute
        allCtrls = FKCtrls + [IKCtrl, poleCtrl]
        for ctrl in allCtrls:
            if ctrl == IKCtrl:
                continue
            if not cmds.attributeQuery(switchAttr, node=ctrl, exists=True):
                cmds.addAttr(ctrl,ln=switchAttr,proxy=IKCtrl + "." + switchAttr)


        # Reverse node
        reverse = cmds.createNode("reverse",n=IKCtrl + "_IKFK_Reverse")
        cmds.connectAttr(IKCtrl + "." + switchAttr,reverse + ".inputX",f=True)
        constraints = []

        for drv, fk, ik in zip(joints, jointFKs, jointIKs):
            con = cmds.parentConstraint(fk,ik,drv,mo=False)[0]
            constraints.append(con)

        # Connect switch
        for con in constraints:
            weights = cmds.parentConstraint(con,q=True,wal=True)
            cmds.connectAttr(reverse + ".outputX",con + "." + weights[0],f=True)
            cmds.connectAttr(IKCtrl + "." + switchAttr,con + "." + weights[1],f=True)

        ### VISIBILITY
        for offset in FKOffsets:
            cmds.connectAttr(reverse + ".outputX",offset + ".visibility",f=True)
        cmds.connectAttr(IKCtrl + "." + switchAttr,IKOffset + ".visibility",f=True)
        cmds.connectAttr(IKCtrl + "." + switchAttr,poleOffset + ".visibility",f=True)

        ### CONNECT GRP CONSTRAINT ORIGINOFFSET GROUP
        for connectGrp, originOffsetGrp in zip(connectGrps, originOffsetGrps):
            cmds.parentConstraint(connectGrp,originOffsetGrp,mo=True)

        # Hide joints & IK Handle
        for node in joints + jointFKs + jointIKs + [ikHandle]:
            if cmds.objExists(node):
                cmds.setAttr(node + ".visibility", 0)

        # Hide shapes of original controls
        for obj in objects:
            if not cmds.objExists(obj):
                continue

            shapes = cmds.listRelatives(obj, s=True, ni=True, f=True) or []
            for shape in shapes:
                cmds.setAttr(shape + ".visibility", 0)


def Run(data, *args):
    return BuildCreateIK(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    """Export the same IK/FK builder with all required Maya-only helpers."""
    path = _pattern_data_path(data)
    datas = NLTA_General.readJsonFile(path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("CreateIK Export: no saved items")
        return None

    import ast
    entries = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    functions = (_unique_name, _group_match_object, _create_offset_group,
                 CreateDiamondCtrl, CreateCircleCtrl, CreateCubeCtrl,
                 DuplicateChain, BuildCreateIK)
    # Format multiline Maya commands only after building the exact source AST.
    source = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    tree = ast.parse(source)

    class RemoveOptionalWarnings(ast.NodeTransformer):
        def visit_Expr(self, node):
            call = node.value
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "cmds" and call.func.attr == "warning"):
                return None
            return self.generic_visit(node)

    tree = RemoveOptionalWarnings().visit(tree)
    ast.fix_missing_locations(tree)
    source = ast.unparse(tree)
    notes = (
        ("    originOffsetGrps = []", "    # Create the original control offsets."),
        ("    grpContain =", "    # Build the matched IK/FK system group."),
        ("    pts = []", "    # Read the source positions and calculate the joint plane."),
        ("    joints = []", "    # Create and orient the driver joint chain."),
        ("    poleVectorName =", "    # Build the pole-vector control."),
        ("    IKName =", "    # Create the IK wrist control and optional space switches."),
        ("    FKCtrls = []", "    # Create the FK controls and matching offset groups."),
        ("    ikHandle, effector =", "    # Create the IK handle and pole-vector constraint."),
        ("    switchAttr =", "    # Connect the IK/FK blend and constraint weights."),
    )
    # Insert comments at the line's real indentation, never inside a suite header.
    lines = source.splitlines()
    for anchor, note in notes:
        for index, line in enumerate(lines):
            if line.lstrip().startswith(anchor.strip()):
                indent = line[:len(line) - len(line.lstrip())]
                lines.insert(index, indent + note.strip())
                break
    source = "\n".join(lines)
    source = "\n".join("    " + line if line.strip() else "" for line in source.splitlines())
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    # CreateIK data\n"
        "    IK_DATA = " + entries + "\n\n"
        + source
        + "\n\n    # Build the saved IK/FK controls and constraints.\n"
        + "    BuildCreateIK(IK_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in generated:
        generated = generated.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(generated, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(generated)
    return output


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_pattern_data_path(data)))


def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    def PickChild(ui,*arr):
        NLTA_UI.PickObject(ui)
        offsetGroup = cmds.textField(itemData["Child"],query=True,text=True)+"_Offset"
        cmds.textField(itemData["OffsetName"],edit=True,text=offsetGroup)

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--
 
    cmds.textField(text='World Parent',editable=False)
    itemData['worldParent'] = cmds.textField(text=data.get('worldParent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['worldParent']))

    cmds.textField(text='Parent',editable=False)
    itemData['parent'] = cmds.textField(text=data.get('parent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['parent']))

    cmds.textField(text='Objects',editable=False)
    itemData['objects'] = cmds.scrollField(text=data.get('objects', ""),height=70)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objects']))

    cmds.setParent("..") #--
    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










