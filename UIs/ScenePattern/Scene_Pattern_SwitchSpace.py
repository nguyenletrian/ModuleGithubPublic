import os
import importlib
import inspect
import ast
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
    name = "Space Switch"
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
    def Save(data,*arr):
        itemData = NLTA_General.JsonGetByID({
            "path":data["sceneDataPath"]+"/ScenePatternData.json",
            "id":data["id"]
        })
        saveData = NLTA_UI.GetData(ITEMS["items"])
        NLTA_General.writeJsonFile(itemData["path"],saveData)
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
    
def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


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


def BuildSwitchSpace(datas):
    """Build original parentConstraint-based space switching controls."""
    if not datas:
        return

    for itemData in datas:
        children = [
            x.strip()
            for x in itemData["child"].split("\n")
            if x.strip()
        ]

        parents = [
            x.strip()
            for x in itemData["parents"].split("\n")
            if x.strip()
        ]

        for child in children:
            # =====================================================
            # VALIDATE
            # =====================================================
            if not cmds.objExists(child):
                cmds.warning("Missing object : {}".format(child))
                continue

            validParents = []

            for parent in parents:
                if cmds.objExists(parent):
                    validParents.append(parent)
                else:
                    cmds.warning("Missing parent : {}".format(parent))

            if not validParents:
                cmds.warning("{} has no valid parents".format(child))
                continue

            # =====================================================
            # DATA
            # =====================================================
            maintain = itemData["maintain"]
            ignoreDefault = itemData.get("ignoreDefault", False)
            attrPick = itemData["attrPick"]
            attrSlide = itemData["attrSlide"]
            defaultValue = float(itemData["defaultValue"])

            # =====================================================
            # CREATE OFFSET
            # =====================================================
            offset = _create_offset_group(child, child + "_SpaceSwitchOffset")

            rootParent = cmds.listRelatives(
                offset,
                parent=True
            )

            rootParent = rootParent[0] if rootParent else None

            # =====================================================
            # DEFAULT SPACE
            #
            # ignoreDefault = True:
            #     Do not create DefaultSpace
            # =====================================================
            defaultSpace = None

            if not ignoreDefault:
                defaultSpace = child + "_DefaultSpace"

                if not cmds.objExists(defaultSpace):
                    if rootParent:
                        defaultSpace = cmds.createNode(
                            "transform",
                            n=defaultSpace,
                            p=rootParent
                        )
                    else:
                        defaultSpace = cmds.createNode(
                            "transform",
                            n=defaultSpace
                        )

                    cmds.matchTransform(
                        defaultSpace,
                        offset
                    )

            # =====================================================
            # ENUM OPTIONS
            # =====================================================
            if itemData["enum"]:
                enumNames = [
                    x.strip()
                    for x in itemData["enum"].split(";")
                    if x.strip()
                ]
            else:
                enumNames = validParents

            if ignoreDefault:
                options = ":".join(enumNames) + ":"
            else:
                options = "Default:" + ":".join(enumNames) + ":"

            # =====================================================
            # PICK ATTRIBUTE
            # =====================================================
            if not cmds.attributeQuery(
                attrPick,
                node=child,
                exists=True
            ):
                cmds.addAttr(
                    child,
                    ln=attrPick,
                    at="enum",
                    en=options
                )

                cmds.setAttr(
                    child + "." + attrPick,
                    e=True,
                    keyable=True
                )

            pickAttr = child + "." + attrPick

            # =====================================================
            # SLIDE ATTRIBUTE
            # =====================================================
            slideAttr = None

            if attrSlide:
                if not cmds.attributeQuery(
                    attrSlide,
                    node=child,
                    exists=True
                ):
                    cmds.addAttr(
                        child,
                        ln=attrSlide,
                        at="double",
                        min=0,
                        max=1,
                        dv=defaultValue
                    )

                    cmds.setAttr(
                        child + "." + attrSlide,
                        e=True,
                        keyable=True
                    )

                slideAttr = child + "." + attrSlide

            # =====================================================
            # PARENT CONSTRAINT
            # =====================================================
            if ignoreDefault:
                targets = validParents
            else:
                targets = [defaultSpace] + validParents

            constraint = cmds.parentConstraint(
                *(targets + [offset]),
                mo=maintain,
                n=child + "_SpaceSwitch_parentConstraint"
            )[0]

            cmds.setAttr(
                constraint + ".interpType",
                2
            )

            # =====================================================
            # GET WEIGHT MAP
            # =====================================================
            weightAttrs = cmds.parentConstraint(
                constraint,
                q=True,
                weightAliasList=True
            )

            targetList = cmds.parentConstraint(
                constraint,
                q=True,
                targetList=True
            )

            weightMap = {}

            for target, weight in zip(
                targetList,
                weightAttrs
            ):
                shortName = target.split("|")[-1]
                weightMap[shortName] = weight

            # =====================================================
            # DEFAULT WEIGHT
            # =====================================================
            defaultWeight = None

            if not ignoreDefault:
                defaultWeight = (
                    constraint + "." +
                    weightMap[defaultSpace.split("|")[-1]]
                )

            # =====================================================
            # WITHOUT SLIDE
            #
            # ignoreDefault = False:
            #   0 = Default
            #   1 = Parent 1
            #   2 = Parent 2
            #
            # ignoreDefault = True:
            #   0 = Parent 1
            #   1 = Parent 2
            #   2 = Parent 3
            # =====================================================
            if not slideAttr:

                # -------------------------------------------------
                # DEFAULT
                # -------------------------------------------------
                if not ignoreDefault:
                    defaultCondition = cmds.shadingNode(
                        "condition",
                        asUtility=True,
                        n=child + "_DefaultSpace_COND"
                    )

                    cmds.connectAttr(
                        pickAttr,
                        defaultCondition + ".firstTerm",
                        f=True
                    )

                    cmds.setAttr(
                        defaultCondition + ".secondTerm",
                        0
                    )

                    cmds.setAttr(
                        defaultCondition + ".operation",
                        0
                    )

                    cmds.setAttr(
                        defaultCondition + ".colorIfTrueR",
                        1
                    )

                    cmds.setAttr(
                        defaultCondition + ".colorIfFalseR",
                        0
                    )

                    cmds.connectAttr(
                        defaultCondition + ".outColorR",
                        defaultWeight,
                        f=True
                    )

                # -------------------------------------------------
                # PARENTS
                # -------------------------------------------------
                for i, parent in enumerate(validParents):
                    parentIndex = i if ignoreDefault else i + 1

                    condition = cmds.shadingNode(
                        "condition",
                        asUtility=True,
                        n=child + "_Space{}_COND".format(i + 1)
                    )

                    cmds.connectAttr(
                        pickAttr,
                        condition + ".firstTerm",
                        f=True
                    )

                    cmds.setAttr(
                        condition + ".secondTerm",
                        parentIndex
                    )

                    cmds.setAttr(
                        condition + ".operation",
                        0
                    )

                    cmds.setAttr(
                        condition + ".colorIfTrueR",
                        1
                    )

                    cmds.setAttr(
                        condition + ".colorIfFalseR",
                        0
                    )

                    parentWeight = (
                        constraint + "." +
                        weightMap[parent.split("|")[-1]]
                    )

                    cmds.connectAttr(
                        condition + ".outColorR",
                        parentWeight,
                        f=True
                    )

            # =====================================================
            # WITH SLIDE
            # =====================================================
            else:

                # =================================================
                # DEFAULT SYSTEM
                #
                # Only create when ignoreDefault == False
                # =================================================
                if not ignoreDefault:

                    # ---------------------------------------------
                    # REVERSE SLIDE
                    # ---------------------------------------------
                    reverseNode = cmds.createNode(
                        "reverse",
                        n=child + "_SpaceSlide_REV"
                    )

                    cmds.connectAttr(
                        slideAttr,
                        reverseNode + ".inputX",
                        f=True
                    )

                    # ---------------------------------------------
                    # DEFAULT WEIGHT
                    #
                    # enum == Default:
                    #     Default = 1
                    #
                    # enum == Parent:
                    #     Default = 1 - slide
                    # ---------------------------------------------
                    defaultCondition = cmds.shadingNode(
                        "condition",
                        asUtility=True,
                        n=child + "_DefaultSpace_COND"
                    )

                    cmds.connectAttr(
                        pickAttr,
                        defaultCondition + ".firstTerm",
                        f=True
                    )

                    cmds.setAttr(
                        defaultCondition + ".secondTerm",
                        0
                    )

                    cmds.setAttr(
                        defaultCondition + ".operation",
                        0
                    )

                    cmds.setAttr(
                        defaultCondition + ".colorIfTrueR",
                        1
                    )

                    cmds.connectAttr(
                        reverseNode + ".outputX",
                        defaultCondition + ".colorIfFalseR",
                        f=True
                    )

                    cmds.connectAttr(
                        defaultCondition + ".outColorR",
                        defaultWeight,
                        f=True
                    )

                # =================================================
                # PARENT WEIGHTS
                # =================================================
                for i, parent in enumerate(validParents):
                    parentIndex = i if ignoreDefault else i + 1

                    condition = cmds.shadingNode(
                        "condition",
                        asUtility=True,
                        n=child + "_Space{}_COND".format(i + 1)
                    )

                    cmds.connectAttr(
                        pickAttr,
                        condition + ".firstTerm",
                        f=True
                    )

                    cmds.setAttr(
                        condition + ".secondTerm",
                        parentIndex
                    )

                    cmds.setAttr(
                        condition + ".operation",
                        0
                    )

                    cmds.connectAttr(
                        slideAttr,
                        condition + ".colorIfTrueR",
                        f=True
                    )

                    cmds.setAttr(
                        condition + ".colorIfFalseR",
                        0
                    )

                    parentWeight = (
                        constraint + "." +
                        weightMap[parent.split("|")[-1]]
                    )

                    cmds.connectAttr(
                        condition + ".outColorR",
                        parentWeight,
                        f=True
                    )


def Run(data, *args):
    return BuildSwitchSpace(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("SwitchSpace Export: no saved items")
        return None

    # Export executable code from the exact same builder used by Run.
    helpers = (_unique_name, _group_match_object, _create_offset_group, BuildSwitchSpace)
    tree = ast.parse("\n\n".join(inspect.getsource(helper).rstrip() for helper in helpers))

    class RemoveDiagnostics(ast.NodeTransformer):
        def visit_Expr(self, node):
            call = node.value
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "cmds"
                    and call.func.attr == "warning"):
                return None
            return self.generic_visit(node)

    tree = RemoveDiagnostics().visit(tree)
    ast.fix_missing_locations(tree)
    source = ast.unparse(tree)
    lines = source.splitlines()
    notes = (
        ("    for itemData in datas:", "# Build every saved child/parent space switch."),
        ("            offset = ", "# Create the space-switch offset and default transform."),
        ("            if itemData['enum']:", "# Build the enum labels and optional blend slider."),
        ("            constraint = ", "# Create the parent constraint with its original target order."),
        ("            weightAttrs = ", "# Resolve exact parentConstraint target weight names."),
        ("            if not slideAttr:", "# Select discrete spaces or blend continuously with slide."),
    )
    for needle, note in notes:
        for index, line in enumerate(lines):
            if line.lstrip().startswith(needle.strip()):
                indent = line[:len(line) - len(line.lstrip())]
                lines.insert(index, indent + note)
                break
    source = "\n".join("    " + line if line.strip() else "" for line in lines)
    data_source = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # SwitchSpace data\n"
        "    SPACE_SWITCH_DATA = " + data_source + "\n\n"
        + source
        + "\n\n    # Rebuild the saved space-switch constraint networks.\n"
        + "    BuildSwitchSpace(SPACE_SWITCH_DATA)\n\n"
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

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Child",editable=False)
    itemData["child"] = cmds.scrollField( text=data.get("child",""),h=80)
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["child"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Parents",editable=False)
    itemData["parents"] = cmds.scrollField( text=data.get("parents",""),h=80)
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData["parents"]))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData["parents"]))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Attr Pick",editable=False)
    itemData["attrPick"] = cmds.textField(text=data.get("attrPick","space"))
    cmds.setParent("..")
    
    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Enum",editable=False)
    itemData["enum"] = cmds.textField(text=data.get("enum",""))
    cmds.setParent("..")


    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Attr Slide",editable=False)
    itemData["attrSlide"] = cmds.textField(text=data.get("attrSlide",""))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Default",editable=False)
    itemData["defaultValue"] = cmds.textField(text=data.get("defaultValue","1"))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Maintain",editable=False)
    itemData["maintain"] = cmds.checkBox(value=data.get("maintain",True),label="")
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Ignore Default",editable=False)
    itemData["ignoreDefault"] = cmds.checkBox(value=data.get("ignoreDefault",True),label="")
    cmds.setParent("..")


    cmds.button(label="X",w=380, bgc=(0.5,0.2,0.2),c=partial(Delete,itemUI))

    cmds.setParent("..")
    cmds.setParent("..")

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)