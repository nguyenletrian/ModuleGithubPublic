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
    name = "Rig Follicle"
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


def _create_offset_group(obj, offset_name):
    """Match a new offset to the object and preserve its parent hierarchy."""
    parent = cmds.listRelatives(obj, parent=True)
    if parent and parent[0] == offset_name:
        return offset_name
    if cmds.objExists(offset_name):
        children = cmds.listRelatives(offset_name, children=True, fullPath=False) or []
        if obj in children:
            return offset_name
        # Use the same suffix rule as the original Maya utility.
        base = offset_name
        index = 1
        while cmds.objExists(base + "_" + str(index)):
            index += 1
        offset_name = base + "_" + str(index)

    group = cmds.group(em=True, name=offset_name)
    cmds.delete(cmds.parentConstraint(obj, group, mo=False))
    cmds.delete(cmds.scaleConstraint(obj, group, mo=False))
    if parent:
        cmds.parent(group, parent[0])
    cmds.parent(obj, group)
    return group

def BuildRigFollicles(datas):
    """Create driver surfaces, follicles, and follow constraints."""
    if not datas:
        return

    def GetWorldAxis(obj, axis):
        matrix = cmds.xform(obj, q=True, ws=True, m=True)
        vectors = {
            "x": om.MVector(matrix[0], matrix[1], matrix[2]),
            "y": om.MVector(matrix[4], matrix[5], matrix[6]),
            "z": om.MVector(matrix[8], matrix[9], matrix[10]),
        }

        sign = -1 if axis.startswith("-") else 1
        axisName = axis.replace("-", "").lower()

        if axisName not in vectors:
            return None

        vector = vectors[axisName] * sign
        if vector.length() < 1e-8:
            return None

        vector.normalize()
        return vector

    def CreateFollicle(surfaceShape, name, u, v, parent=None):
        if cmds.objExists(name):
            follicleTransform = name
            shapes = cmds.listRelatives(
                follicleTransform,
                shapes=True,
                type="follicle"
            ) or []

            if not shapes:
                return None

            follicleShape = shapes[0]

        else:
            follicleShape = cmds.createNode(
                "follicle",
                n=name + "Shape"
            )

            follicleTransform = cmds.listRelatives(
                follicleShape,
                parent=True
            )[0]

            follicleTransform = cmds.rename(
                follicleTransform,
                name
            )

            follicleShape = cmds.listRelatives(
                follicleTransform,
                shapes=True,
                type="follicle"
            )[0]

        if parent and cmds.objExists(parent):
            currentParent = cmds.listRelatives(
                follicleTransform,
                parent=True
            )

            if not currentParent or currentParent[0] != parent:
                cmds.parent(
                    follicleTransform,
                    parent
                )

        cmds.setAttr(
            follicleTransform + ".translate",
            0, 0, 0
        )

        cmds.setAttr(
            follicleTransform + ".rotate",
            0, 0, 0
        )

        cmds.setAttr(
            follicleTransform + ".scale",
            1, 1, 1
        )

        cmds.connectAttr(
            surfaceShape + ".local",
            follicleShape + ".inputSurface",
            f=True
        )

        cmds.connectAttr(
            surfaceShape + ".worldMatrix[0]",
            follicleShape + ".inputWorldMatrix",
            f=True
        )

        cmds.connectAttr(
            follicleShape + ".outTranslate",
            follicleTransform + ".translate",
            f=True
        )

        cmds.connectAttr(
            follicleShape + ".outRotate",
            follicleTransform + ".rotate",
            f=True
        )

        cmds.setAttr(
            follicleShape + ".parameterU",
            float(u)
        )

        cmds.setAttr(
            follicleShape + ".parameterV",
            float(v)
        )

        return follicleTransform

    for item in datas:
        objectsString = item.get(
            "objects",
            item.get("children", "")
        )

        objects = [
            x.strip()
            for x in objectsString.split("\n")
            if x.strip()
        ]

        reference = item.get("reference", "")
        upAxis = item.get("upAxis", "y").lower()
        width = float(item.get("width", 1.0))
        rebuildCount = max(
            int(item.get("rebuild", 4)),
            1
        )

        parent = item.get("parent", "")

        attrHolders = [
            x.strip()
            for x in item.get(
                "attrHolders",
                ""
            ).split("\n")
            if x.strip()
        ]

        attr = item.get(
            "attr",
            "FollicleFollow"
        )

        validObjects = [
            obj
            for obj in objects
            if cmds.objExists(obj)
        ]

        if len(validObjects) < 2:
            cmds.warning(
                "Folico requires at least 2 valid objects."
            )
            continue

        if not cmds.objExists(reference):
            cmds.warning(
                "Reference does not exist: {}".format(
                    reference
                )
            )
            continue

        # --------------------------------------------------------
        # REFERENCE AXIS
        # --------------------------------------------------------
        upVector = GetWorldAxis(
            reference,
            upAxis
        )

        if upVector is None:
            cmds.warning(
                "Cannot get axis {} from {}".format(
                    upAxis,
                    reference
                )
            )
            continue

        # --------------------------------------------------------
        # ORIGINAL POSITIONS
        # --------------------------------------------------------
        positions = [
            om.MVector(
                *cmds.xform(
                    obj,
                    q=True,
                    ws=True,
                    t=True
                )
            )
            for obj in validObjects
        ]

        # --------------------------------------------------------
        # EXACT DRIVER ROWS
        # --------------------------------------------------------
        halfWidth = width * 0.5
        rowA = []
        rowB = []

        for position in positions:
            pointA = position - upVector * halfWidth
            pointB = position + upVector * halfWidth

            rowA.append(
                (
                    pointA.x,
                    pointA.y,
                    pointA.z
                )
            )

            rowB.append(
                (
                    pointB.x,
                    pointB.y,
                    pointB.z
                )
            )

        # --------------------------------------------------------
        # NAMES
        # --------------------------------------------------------
        baseName = validObjects[0] + "_Folico"

        systemGrp = baseName + "_Grp"
        follicleGrp = baseName + "_FolliclesGrp"

        driverSurfaceName = (
            baseName +
            "_DriverSurface"
        )

        rebuildSurfaceName = (
            baseName +
            "_Surface"
        )

        # --------------------------------------------------------
        # GROUPS
        # --------------------------------------------------------
        if not cmds.objExists(systemGrp):
            systemGrp = cmds.group(
                em=True,
                n=systemGrp
            )

            if parent and cmds.objExists(parent):
                cmds.parent(
                    systemGrp,
                    parent
                )

        if not cmds.objExists(follicleGrp):
            follicleGrp = cmds.group(
                em=True,
                n=follicleGrp,
                p=systemGrp
            )

        # --------------------------------------------------------
        # DRIVER SURFACE
        #
        # Linear / exact.
        # Các edge đi đúng qua positions offset.
        # --------------------------------------------------------
        if cmds.objExists(driverSurfaceName):
            cmds.delete(
                driverSurfaceName
            )

        curveA = cmds.curve(
            d=1,
            p=rowA,
            n=baseName + "_A_Temp"
        )

        curveB = cmds.curve(
            d=1,
            p=rowB,
            n=baseName + "_B_Temp"
        )

        driverSurface = cmds.loft(
            curveA,
            curveB,
            n=driverSurfaceName,
            ch=False,
            u=True,
            c=False,
            ar=True,
            d=1,
            ss=1
        )[0]

        cmds.delete(
            curveA,
            curveB
        )

        cmds.parent(
            driverSurface,
            systemGrp
        )

        # --------------------------------------------------------
        # REBUILD SURFACE
        #
        # DriverSurface vẫn giữ nguyên.
        #
        # U = width
        #   1 span
        #   degree 1
        #
        # V = chain
        #   rebuildCount spans
        #   degree 3
        #
        # kc=False:
        # surface được phép smooth hơn,
        # không ép corner bám cứng input.
        # --------------------------------------------------------
        if cmds.objExists(rebuildSurfaceName):
            cmds.delete(
                rebuildSurfaceName
            )

        rebuilt = cmds.rebuildSurface(
            driverSurface,
            ch=True,
            rpo=False,
            rt=0,
            dir=2,
            end=1,
            kr=0,
            kcp=False,
            kc=False,

            # WIDTH
            su=1,
            du=1,

            # LENGTH
            sv=rebuildCount,
            dv=3,

            tol=0.1
        )

        rebuildSurface = cmds.rename(
            rebuilt[0],
            rebuildSurfaceName
        )

        cmds.parent(
            rebuildSurface,
            systemGrp
        )

        rebuildShapes = cmds.listRelatives(
            rebuildSurface,
            shapes=True,
            noIntermediate=True
        ) or []

        if not rebuildShapes:
            cmds.warning(
                "Cannot find rebuilt surface shape."
            )
            continue

        rebuildShape = rebuildShapes[0]

        # --------------------------------------------------------
        # FOLLOW ATTRIBUTE
        # --------------------------------------------------------
        masterHolder = (
            attrHolders[0]
            if attrHolders
            else None
        )

        if (
            masterHolder
            and cmds.objExists(masterHolder)
        ):
            if not cmds.attributeQuery(
                attr,
                node=masterHolder,
                exists=True
            ):
                cmds.addAttr(
                    masterHolder,
                    ln=attr,
                    at="bool",
                    dv=1,
                    k=True
                )

            for holder in attrHolders[1:]:
                if not cmds.objExists(holder):
                    continue

                if not cmds.attributeQuery(
                    attr,
                    node=holder,
                    exists=True
                ):
                    cmds.addAttr(
                        holder,
                        ln=attr,
                        proxy="{}.{}".format(
                            masterHolder,
                            attr
                        )
                    )

        # --------------------------------------------------------
        # FOLLICLES
        # --------------------------------------------------------
        for obj in validObjects:
            objPos = cmds.xform(
                obj,
                q=True,
                ws=True,
                t=True
            )

            # ----------------------------------------------------
            # CLOSEST UV
            # ----------------------------------------------------
            cps = cmds.createNode(
                "closestPointOnSurface",
                n=obj + "_Folico_CPOS"
            )

            cmds.connectAttr(
                rebuildShape + ".worldSpace[0]",
                cps + ".inputSurface",
                f=True
            )

            cmds.setAttr(
                cps + ".inPosition",
                objPos[0],
                objPos[1],
                objPos[2],
                type="double3"
            )

            u = float(
                cmds.getAttr(
                    cps + ".parameterU"
                )
            )

            v = float(
                cmds.getAttr(
                    cps + ".parameterV"
                )
            )

            cmds.delete(cps)

            # ----------------------------------------------------
            # FOLLICLE
            # ----------------------------------------------------
            follicle = CreateFollicle(
                rebuildShape,
                obj + "_Follicle",
                u,
                v,
                follicleGrp
            )

            if not follicle:
                continue

            # ----------------------------------------------------
            # OBJECT OFFSET
            # ----------------------------------------------------
            offsetGrp = (
                obj +
                "_FollicleGrp"
            )

            if not cmds.objExists(offsetGrp):
                _create_offset_group(
                    obj,
                    offsetGrp
                )

            # ----------------------------------------------------
            # CONSTRAINT
            # ----------------------------------------------------
            constraintName = (
                obj +
                "_FollicleConstraint"
            )

            existing = cmds.listConnections(
                offsetGrp,
                type="parentConstraint"
            ) or []

            if existing:
                constraint = existing[0]

            else:
                constraint = cmds.parentConstraint(
                    follicle,
                    offsetGrp,
                    mo=True,
                    n=constraintName
                )[0]

            # ----------------------------------------------------
            # FOLLOW ON / OFF
            # ----------------------------------------------------
            if (
                masterHolder
                and cmds.objExists(masterHolder)
            ):
                weights = cmds.parentConstraint(
                    constraint,
                    q=True,
                    weightAliasList=True
                ) or []

                if not weights:
                    continue

                followPlug = "{}.{}".format(
                    masterHolder,
                    attr
                )

                weightPlug = "{}.{}".format(
                    constraint,
                    weights[0]
                )

                if not cmds.isConnected(
                    followPlug,
                    weightPlug
                ):
                    cmds.connectAttr(
                        followPlug,
                        weightPlug,
                        f=True
                    )

def _follicles_export_builder():
    """Render the exact builder as compact English-only standalone code."""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(BuildRigFollicles)))

    class OmitWarnings(ast.NodeTransformer):
        def visit_Expr(self, node):
            call = node.value
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "cmds" and call.func.attr == "warning"):
                return None
            return self.generic_visit(node)

    tree = OmitWarnings().visit(tree)
    ast.fix_missing_locations(tree)
    result = ast.unparse(tree).strip()
    # Short English notes are inserted after compacting the Maya commands.
    sections = (
        ("    def GetWorldAxis(", "    # Read the reference axis in world space."),
        ("    def CreateFollicle(", "    # Create or reuse a follicle and connect its outputs."),
        ("        positions =", "        # Read the original positions and construct the driver rows."),
        ("        curveA =", "        # Loft the driver surface from two curves."),
        ("        rebuilt =", "        # Rebuild the smooth surface along the object chain."),
        ("        masterHolder =", "        # Create the shared follow attribute and proxies."),
        ("            cps =", "            # Find the closest surface parameter for each object."),
        ("            follicle =", "            # Attach a follicle to the rebuilt surface."),
        ("            offsetGrp =", "            # Create the original matched offset group."),
        ("            existing =", "            # Create or reuse the parent constraint."),
    )
    for marker, note in sections:
        if marker in result:
            result = result.replace(marker, note + "\n" + marker, 1)
    return result


def _follicles_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]
    })
    return os.path.normpath(entry["path"])


def Run(data, *args):
    """Build the saved follicle network using the same exported builder."""
    datas = NLTA_General.readJsonFile(_follicles_data_path(data)) or []
    return BuildRigFollicles(datas)


def ExportPython(data, *args):
    """Export a standalone Maya rig builder with compact embedded data."""
    path = _follicles_data_path(data)
    datas = NLTA_General.readJsonFile(path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("RigFollicles Export: no saved items")
        return None

    # Keep one complete data record per line, preserving all saved values.
    embedded_data = "[\n" + ",\n".join("        " + repr(item) for item in datas) + "\n    ]"
    offset_source = inspect.getsource(_create_offset_group).strip()
    builder_source = _follicles_export_builder()
    functions = "\n\n".join((offset_source, builder_source))
    functions = "\n".join("    " + line if line.strip() else "" for line in functions.splitlines())
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    # RigFollicles data\n"
        "    FOLLICLES_DATA = " + embedded_data + "\n\n"
        + functions
        + "\n\n    # Build the saved follicle rig.\n"
        + "    BuildRigFollicles(FOLLICLES_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in script:
        script = script.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(script, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(script)
    return output


def OpenExportFolder(data, *args):
    os.startfile(os.path.dirname(_follicles_data_path(data)))


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


    cmds.textField(text='objects',editable=False)
    itemData['objects'] = cmds.scrollField(wordWrap=True,height=80,text=data.get("objects", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objects']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['objects']))
    cmds.setParent("..")

    cmds.textField(text='Attr Holders',editable=False)
    itemData['attrHolders'] = cmds.scrollField(wordWrap=True,height=80,text=data.get('attrHolders', ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['attrHolders']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['attrHolders']))
    cmds.setParent("..")

    cmds.textField(text='Reference',editable=False)
    itemData['reference'] = cmds.textField(text=data.get('reference', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['reference']))

    cmds.textField(text='Up Axis',editable=False)
    itemData["upAxis"] = cmds.optionMenu()
    for key in ["x","y","x","-x","-y","-z"]:
        cmds.menuItem(label=key)
    cmds.optionMenu(itemData["upAxis"], e=True, value=data.get("upAxis","x"))
    cmds.text(label="")

    cmds.textField(text='Rebuild',editable=False)
    itemData['rebuild'] = cmds.textField(text=data.get('rebuild', "100"))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['rebuild']))



    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










