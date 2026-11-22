import os
import importlib
import inspect
import ast
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
    name = "Rig Curve Guilde"
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


def GetAimUpVectors(obj, aimTarget, upTarget):
    matrix = cmds.xform(obj, q=True, ws=True, m=True)
    pos = om.MVector(matrix[12], matrix[13], matrix[14])

    axes = {
        "x": om.MVector(matrix[0], matrix[1], matrix[2]),
        "y": om.MVector(matrix[4], matrix[5], matrix[6]),
        "z": om.MVector(matrix[8], matrix[9], matrix[10]),
    }

    for axis in axes.values():
        axis.normalize()

    aimPos = om.MVector(*cmds.xform(aimTarget, q=True, ws=True, t=True))
    upPos = om.MVector(*cmds.xform(upTarget, q=True, ws=True, t=True))

    aimDir = aimPos - pos
    upDir = upPos - pos

    if aimDir.length() < 1e-8 or upDir.length() < 1e-8:
        return None

    aimDir.normalize()
    upDir.normalize()

    # --------------------------------------------------------
    # FIND AIM AXIS
    # --------------------------------------------------------
    bestAimName = None
    bestAimDot = -1
    bestAimSign = 1

    for name, axis in axes.items():
        dot = axis * aimDir

        if abs(dot) > bestAimDot:
            bestAimDot = abs(dot)
            bestAimName = name
            bestAimSign = 1 if dot >= 0 else -1

    # --------------------------------------------------------
    # FIND UP AXIS
    # Chỉ xét 2 axis còn lại
    # --------------------------------------------------------
    bestUpName = None
    bestUpDot = -1
    bestUpSign = 1

    for name, axis in axes.items():
        if name == bestAimName:
            continue

        dot = axis * upDir

        if abs(dot) > bestUpDot:
            bestUpDot = abs(dot)
            bestUpName = name
            bestUpSign = 1 if dot >= 0 else -1

    vectors = {
        "x": (1, 0, 0),
        "y": (0, 1, 0),
        "z": (0, 0, 1),
    }

    aimVector = tuple(v * bestAimSign for v in vectors[bestAimName])
    upVector = tuple(v * bestUpSign for v in vectors[bestUpName])

    return {
        "aimAxis": ("-" if bestAimSign < 0 else "") + bestAimName,
        "upAxis": ("-" if bestUpSign < 0 else "") + bestUpName,
        "aimVector": aimVector,
        "upVector": upVector,
        "aimScore": bestAimDot,
        "upScore": bestUpDot
    }


def _pattern_data_path(data):
    item = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(item["path"])


def _unique_name(name):
    if not cmds.objExists(name):
        return name
    index = 1
    while cmds.objExists(name + "_" + str(index)):
        index += 1
    return name + "_" + str(index)


def _group_match_object(obj, name):
    group = cmds.group(em=True, name=name)
    cmds.delete(cmds.parentConstraint(obj, group, mo=False))
    cmds.delete(cmds.scaleConstraint(obj, group, mo=False))
    return group


def _create_offset_group(obj, offset_name):
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


def BuildRigCurveGuide(datas):
    """Create curve/plane aim guides and their original DG networks."""
    if not datas:
        return

    # ------------------------------------------------------------
    # FIND CURVE / CHILD PLANE INTERSECTION
    # ------------------------------------------------------------
    def GetPlaneIntersection(child, curve, curveShape, samples=300, tolerance=0.001):
        matrix = cmds.xform(child, q=True, ws=True, m=True)
        childPos = om.MVector(matrix[12], matrix[13], matrix[14])
        axes = {
            "x": om.MVector(matrix[0], matrix[1], matrix[2]),
            "y": om.MVector(matrix[4], matrix[5], matrix[6]),
            "z": om.MVector(matrix[8], matrix[9], matrix[10]),
        }

        for axis in axes.values():
            if axis.length() > 1e-8:
                axis.normalize()

        # nearest chỉ dùng để lấy tangent gần child
        nearest = cmds.createNode("nearestPointOnCurve",n=child + "_CurveGuide_Temp_NPOC")
        cmds.connectAttr(curveShape + ".worldSpace[0]",nearest + ".inputCurve",f=True)
        cmds.setAttr(nearest + ".inPosition",childPos.x,childPos.y,childPos.z,type="double3")
        nearParam = cmds.getAttr(nearest + ".parameter")
        cmds.delete(nearest)
        tangent = cmds.pointOnCurve(curve,pr=nearParam,nt=True,top=True)
        tangent = om.MVector(*tangent)
        if tangent.length() < 1e-8:
            return None
        tangent.normalize()

        planeData = [("YZ", "x", axes["x"]), ("XZ", "y", axes["y"]),("XY", "z", axes["z"]),]
        planeName = None
        planeAxis = None
        planeNormal = None
        bestDot = -1
        for name, axisName, normal in planeData:
            dot = abs(normal * tangent)
            if dot > bestDot:
                bestDot = dot
                planeName = name
                planeAxis = axisName
                planeNormal = normal

        if planeNormal is None:
            return None

        minMax = cmds.getAttr(curveShape + ".minMaxValue")[0]
        minParam = float(minMax[0])
        maxParam = float(minMax[1])

        def PlaneValue(parameter):
            point = cmds.pointOnCurve(curve,pr=parameter,p=True,top=True)
            point = om.MVector(*point)
            return (point - childPos) * planeNormal

        def GetPoint(parameter):
            point = cmds.pointOnCurve(curve,pr=parameter,p=True,top=True)
            return om.MVector(*point)

        parameters = [minParam + (maxParam - minParam) * (float(i) / samples) for i in range(samples + 1)]
        values = [PlaneValue(p) for p in parameters]
        intersections = []

        for i in range(samples):
            p0 = parameters[i]
            p1 = parameters[i + 1]
            v0 = values[i]
            v1 = values[i + 1]
            if abs(v0) <= tolerance:
                intersections.append(p0)
            if v0 * v1 > 0:
                continue
            if abs(v0) <= tolerance and abs(v1) <= tolerance:
                continue
            left = p0
            right = p1
            leftValue = v0
            for _ in range(30):
                mid = (left + right) * 0.5
                midValue = PlaneValue(mid)
                if abs(midValue) <= 1e-7:
                    left = right = mid
                    break
                if leftValue * midValue <= 0:
                    right = mid
                else:
                    left = mid
                    leftValue = midValue
            intersections.append((left + right) * 0.5)

        if abs(values[-1]) <= tolerance:
            intersections.append(parameters[-1])

        if not intersections:
            return None

        intersections.sort()
        uniqueParams = []

        for parameter in intersections:
            if not uniqueParams or abs(parameter - uniqueParams[-1]) > 0.0001:
                uniqueParams.append(parameter)

        result = None

        for parameter in uniqueParams:
            point = GetPoint(parameter)
            distance = (point - childPos).length()
            if result is None or distance < result["distance"]:
                result = {
                    "plane": planeName,
                    "planeAxis": planeAxis,
                    "normal": (planeNormal.x,planeNormal.y,planeNormal.z),
                    "parameter": parameter,
                    "position": (point.x,point.y,point.z),
                    "distance": distance,
                    "planeScore": bestDot
                }

        return result

    # ------------------------------------------------------------
    # CREATE CUBE CONTROL
    # ------------------------------------------------------------
    def CreateCubeControl(name, size=1.0):
        if cmds.objExists(name):
            return name
        s = size * 0.5
        points = [
            (-s,-s,-s), ( s,-s,-s), ( s, s,-s), (-s, s,-s), (-s,-s,-s),
            (-s,-s, s), ( s,-s, s), ( s,-s,-s), ( s,-s, s), ( s, s, s),
            ( s, s,-s), ( s, s, s), (-s, s, s), (-s, s,-s), (-s, s, s),
            (-s,-s, s)
        ]

        return cmds.curve(n=name,d=1,p=points)

    # ------------------------------------------------------------
    # AUTO DETECT AIM / UP AXIS
    # ------------------------------------------------------------
    def GetAimUpVectors(obj, aimTarget, upTarget, preferredAimAxis=None):
        matrix = cmds.xform(obj,q=True,ws=True,m=True)
        pos = om.MVector(matrix[12],matrix[13],matrix[14])
        axes = {
            "x": om.MVector(matrix[0], matrix[1], matrix[2]),
            "y": om.MVector(matrix[4], matrix[5], matrix[6]),
            "z": om.MVector(matrix[8], matrix[9], matrix[10]),
        }
        for axis in axes.values():
            if axis.length() > 1e-8:
                axis.normalize()
        aimPos = om.MVector(*cmds.xform(aimTarget,q=True,ws=True,t=True))
        upPos = om.MVector(*cmds.xform(upTarget,q=True,ws=True,t=True))
        aimDir = aimPos - pos
        upDir = upPos - pos

        if aimDir.length() < 1e-8:
            return None

        if upDir.length() < 1e-8:
            return None

        aimDir.normalize()
        upDir.normalize()
        vectors = {"x": (1, 0, 0),"y": (0, 1, 0),"z": (0, 0, 1),}

        # --------------------------------------------------------
        # AIM AXIS
        #
        # Nếu GetPlaneIntersection đã tìm được plane normal axis,
        # ưu tiên axis đó làm aim axis.
        # --------------------------------------------------------
        if preferredAimAxis in axes:
            aimAxisName = preferredAimAxis
            aimDot = axes[aimAxisName] * aimDir
            aimSign = 1 if aimDot >= 0 else -1
            aimScore = abs(aimDot)

        else:
            aimAxisName = None
            aimSign = 1
            aimScore = -1
            for name, axis in axes.items():
                dot = axis * aimDir
                if abs(dot) > aimScore:
                    aimScore = abs(dot)
                    aimAxisName = name
                    aimSign = 1 if dot >= 0 else -1

        # --------------------------------------------------------
        # UP AXIS
        #
        # Chỉ xét 2 axis còn lại
        # --------------------------------------------------------
        upAxisName = None
        upSign = 1
        upScore = -1
        for name, axis in axes.items():
            if name == aimAxisName:
                continue
            dot = axis * upDir
            if abs(dot) > upScore:
                upScore = abs(dot)
                upAxisName = name
                upSign = 1 if dot >= 0 else -1

        if not aimAxisName or not upAxisName:
            return None

        aimVector = tuple(value * aimSign for value in vectors[aimAxisName])
        upVector = tuple(value * upSign for value in vectors[upAxisName])

        return {
            "aimAxis": (
                "-" if aimSign < 0 else ""
            ) + aimAxisName,

            "upAxis": (
                "-" if upSign < 0 else ""
            ) + upAxisName,
            "aimVector": aimVector,
            "upVector": upVector,
            "aimScore": aimScore,
            "upScore": upScore
        }

    # ============================================================
    # BUILD
    # ============================================================
    for item in datas:
        curve = item["curve"]
        children = [x.strip() for x in item["children"].split("\n") if x.strip() ]
        parent = item.get("parent", "")
        reference = item.get("reference", "")
        attrHolders = [ x.strip() for x in item.get( "attrHolders", "" ).split("\n") if x.strip() ]
        maintain = bool( item.get("maintain",True))

        if not cmds.objExists(curve):
            # Diagnostic warning omitted in standalone builder.
            continue

        if not cmds.objExists(reference):
            # Diagnostic warning omitted in standalone builder.
            continue

        curveShapes = cmds.listRelatives(curve,shapes=True,noIntermediate=True) or []
        if not curveShapes:
            # Diagnostic warning omitted in standalone builder.
            continue
        curveShape = curveShapes[0]

        # ------------------------------------------------------------
        # AIM CONTROL VISIBILITY
        # ------------------------------------------------------------
        showAttr = "AimControls"
        masterHolder = attrHolders[0] if attrHolders else None
        if masterHolder and cmds.objExists(masterHolder):
            if not cmds.attributeQuery(showAttr,node=masterHolder,exists=True):
                cmds.addAttr(masterHolder,ln=showAttr,at="bool",dv=1,k=True)
            for holder in attrHolders[1:]:
                if not cmds.objExists(holder):
                    continue
                if not cmds.attributeQuery(showAttr,node=holder,exists=True):
                    cmds.addAttr(holder,ln=showAttr,proxy="{}.{}".format(masterHolder,showAttr))

        # ------------------------------------------------------------
        # CHILDREN
        # ------------------------------------------------------------
        for child in children:
            if not cmds.objExists(child):
                # Diagnostic warning omitted in standalone builder.
                continue

            refGrp = child + "_RefGrp"
            aimCtrl = child + "_AimCtrl"
            guildGrp = child + "_CurveGuildGrp"
            pocName = child + "_CurveGuild_POCI"

            # --------------------------------------------------------
            # CURVE / PLANE INTERSECTION
            # --------------------------------------------------------
            hitData = GetPlaneIntersection(child,curve,curveShape)
            if not hitData:
                # Diagnostic warning omitted in standalone builder.
                continue
            parameter = hitData["parameter"]

            # --------------------------------------------------------
            # REF GROUP
            # --------------------------------------------------------
            if not cmds.objExists(refGrp):
                refGrp = cmds.group(em=True,n=refGrp)
                if parent and cmds.objExists(parent):
                    cmds.parent(refGrp,parent)

            # --------------------------------------------------------
            # AIM CONTROL
            # --------------------------------------------------------
            if not cmds.objExists(aimCtrl):
                aimCtrl = CreateCubeControl(aimCtrl,size=1.0)
                cmds.parent(aimCtrl,refGrp)
                cmds.setAttr(aimCtrl + ".translate",0,0,0)
                cmds.setAttr(aimCtrl + ".rotate",0,0, 0)
                cmds.setAttr(aimCtrl + ".scale",1,1,1)

            # Visibility
            if masterHolder and cmds.objExists(masterHolder):
                visibilityPlug = "{}.{}".format(masterHolder,showAttr)
                if not cmds.isConnected(visibilityPlug,aimCtrl + ".visibility"):
                    cmds.connectAttr(visibilityPlug,aimCtrl + ".visibility",f=True)

            # --------------------------------------------------------
            # POINT ON CURVE
            # --------------------------------------------------------
            if cmds.objExists(pocName):
                poc = pocName
            else:
                poc = cmds.createNode("pointOnCurveInfo",n=pocName)

            cmds.connectAttr(curveShape + ".worldSpace[0]",poc + ".inputCurve",f=True)
            cmds.setAttr(poc + ".parameter",parameter)

            # --------------------------------------------------------
            # DRIVE REF GROUP
            # --------------------------------------------------------
            composeName = child + "_CurveGuild_CM"
            multName = child + "_CurveGuild_MM"
            dcmName = child + "_CurveGuild_DCM"

            compose = (composeName if cmds.objExists(composeName) else cmds.createNode( "composeMatrix", n=composeName ) )
            mm = ( multName if cmds.objExists(multName) else cmds.createNode( "multMatrix", n=multName ) )
            dcm = (dcmName  if cmds.objExists(dcmName) else cmds.createNode( "decomposeMatrix", n=dcmName ) )
            cmds.connectAttr(  poc + ".position", compose + ".inputTranslate",  f=True )
            cmds.connectAttr(compose + ".outputMatrix", mm + ".matrixIn[0]", f=True )
            cmds.connectAttr(refGrp + ".parentInverseMatrix[0]", mm + ".matrixIn[1]",f=True)
            cmds.connectAttr(mm + ".matrixSum", dcm + ".inputMatrix",f=True )
            cmds.connectAttr( dcm + ".outputTranslate", refGrp + ".translate", f=True)

            # --------------------------------------------------------
            # CREATE CURVE GUILD OFFSET
            # --------------------------------------------------------
            if not cmds.objExists(guildGrp):
                _create_offset_group(child,guildGrp)

            # --------------------------------------------------------
            # AUTO DETECT AIM + UP
            #
            # Plane normal axis được ưu tiên làm aim axis.
            # Dấu +/- dựa vào AimCtrl.
            # Up axis lấy từ reference.
            # --------------------------------------------------------
            axisData = GetAimUpVectors( guildGrp,aimCtrl,reference,preferredAimAxis=hitData["planeAxis"])
            if not axisData:
                # Diagnostic warning omitted in standalone builder.
                continue

            aimVector = axisData["aimVector"]
            upVector = axisData["upVector"]
            # Orient the child with the detected aim and up axes.

            # --------------------------------------------------------
            # AIM
            # --------------------------------------------------------
            oldAim = cmds.listConnections(guildGrp,type="aimConstraint") or []
            if not oldAim:
                cmds.aimConstraint(aimCtrl,guildGrp,aimVector=aimVector, upVector=upVector,worldUpType="object",worldUpObject=reference,maintainOffset=maintain,n=child + "_CurveGuild_AIM")


def Run(data, *args):
    return BuildRigCurveGuide(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("RigCurveGuide Export: no saved items")
        return None

    # Preserve the shared builder AST and remove original commentary for output.
    functions = (_unique_name, _group_match_object, _create_offset_group, BuildRigCurveGuide)
    source = "\n\n".join(inspect.getsource(function).rstrip() for function in functions)
    tree = ast.parse(source)
    source = ast.unparse(tree)
    lines = source.splitlines()
    notes = (
        ("    def GetPlaneIntersection(", "    # Locate the closest intersection of each child plane and curve."),
        ("    def GetAimUpVectors(", "    # Choose orientation axes using the reference and curve plane."),
        ("    for item in datas:", "    # Construct the curve guides, visibility and aim constraints."),
    )
    for anchor, note in notes:
        for index, line in enumerate(lines):
            if line.lstrip().startswith(anchor.strip()):
                indentation = line[:len(line)-len(line.lstrip())]
                lines.insert(index, indentation + note.strip())
                break
    source = "\n".join("    " + line if line.strip() else "" for line in lines)
    items = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    # RigCurveGuide data\n"
        "    CURVE_GUIDE_DATA = " + items + "\n\n"
        + source
        + "\n\n    # Apply the curve-guide setup in the base scene.\n"
        + "    BuildRigCurveGuide(CURVE_GUIDE_DATA)\n\n"
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

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--


    cmds.textField(text='Curve',editable=False)
    itemData['curve'] = cmds.textField(text=data.get("curve", ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['curve']))

    cmds.textField(text='Children',editable=False)
    itemData['children'] = cmds.scrollField(wordWrap=True,height=80,text=data.get("children", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['children']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['children']))
    cmds.setParent("..")

    cmds.textField(text='Parent',editable=False)
    itemData['Parent'] = cmds.textField(text=data.get("parent", ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['Parent']))

    cmds.textField(text='Reference',editable=False)
    itemData['reference'] = cmds.textField(text=data.get('reference', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['reference']))

    cmds.textField(text='Attr Holders',editable=False)
    itemData['attrHolders'] = cmds.scrollField(wordWrap=True,height=80,text=data.get('attrHolders', ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['attrHolders']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['attrHolders']))
    cmds.setParent("..")


    """
    cmds.textField(text='Main Axis',editable=False)
    itemData["mainAxis"] = cmds.optionMenu()
    for key in ["x","y","x","-x","-y","-z"]:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["mainAxis"], e=True, value=data.get("mainAxis","x"))
    cmds.text(label="")

    cmds.textField(text='Second Axis',editable=False)
    itemData["secondAxis"] = cmds.optionMenu()
    for key in ["x","y","x","-x","-y","-z"]:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["secondAxis"], e=True, value=data.get("secondAxis","x"))
    cmds.text(label="")
    """

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










