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
    name = "Modulo SDK New"
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
        global ITEMS
        itemData = NLTA_General.JsonGetByID({
            "path":data["sceneDataPath"]+"/ScenePatternData.json",
            "id":data["id"]
        })
        saveData = []
        for itemUI in ITEMS["order"]:
            item = ITEMS["items"][itemUI]
            itemDict = {
                "driver": cmds.textField(item["driver"], q=True, text=True),
                "attrsData": {}
            }
            for attrItem in item["attrsData"]:
                targetAttr = cmds.scrollField(
                    attrItem["targetAttr"],
                    q=True,
                    text=True
                )
                values = {}
                for i,valueUI in enumerate(attrItem["values"]):
                    value = cmds.textField(valueUI,q=True,text=True)

                    if value != "":
                        values[str(i)] = value

                itemDict["attrsData"][targetAttr] = values

            saveData.append(itemDict)

        NLTA_General.writeJsonFile(
            itemData["path"],
            saveData
        )

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


def BuildSDKModulo(datas):
    """Create original modulo-driven Maya expression and offset groups."""
    if not datas:
        return
    for itemData in datas:
        driver = itemData["driver"]
        attrsData = itemData["attrsData"]
        if "." not in driver:
            cmds.warning("Invalid driver : {}".format(driver))
            continue
        driverObj, driverAttr = driver.rsplit(".", 1)
        if not cmds.attributeQuery(driverAttr, node=driverObj, exists=True):
            cmds.addAttr(driverObj, ln=driverAttr, at="long", dv=0, k=True)

        # -----------------------------------------
        # Expand attrsData
        # -----------------------------------------
        expandedAttrs = {}
        for attrGroup, valuesData in attrsData.items():
            attrs = [a.strip() for a in attrGroup.split("\n") if a.strip()]
            for attr in attrs:
                expandedAttrs[attr] = valuesData

        # -----------------------------------------
        # Create Offset Groups
        # -----------------------------------------
        offsetData = {}
        for targetAttr in expandedAttrs:
            target = targetAttr.rsplit(".", 1)[0]
            offsetName = target + "_Modulo_Grp"
            if target not in offsetData:
                if not cmds.objExists(offsetName):
                    offsetData[target] = _create_offset_group(target,offsetName)
                else:
                    offsetData[target] = offsetName

        # -----------------------------------------
        # Build modulo data
        # -----------------------------------------
        moduloData = {}
        for i in range(10):
            modulo = str(i)
            valueStrings = []
            for targetAttr, valuesData in expandedAttrs.items():
                if modulo not in valuesData:
                    continue
                target, attr = targetAttr.rsplit(".", 1)
                offset = offsetData[target]
                valueStrings.append("{}.{}={}".format(offset,attr,valuesData[modulo]))
            if valueStrings:
                moduloData[modulo] = valueStrings

        # -----------------------------------------
        # Build expression
        # -----------------------------------------
        stringConcat = ""

        for index, modulo in enumerate(sorted(moduloData.keys(), key=int)):
            body = ";".join(moduloData[modulo]) + ";"

            if index == 0:
                stringConcat += (
                    "if ($r == {})\n"
                    "{{\n"
                    "\t{}\n"
                    "}}\n"
                ).format(modulo, body)
            else:
                stringConcat += (
                    "else if ($r == {})\n"
                    "{{\n"
                    "\t{}\n"
                    "}}\n"
                ).format(modulo, body)

        # -----------------------------------------
        # Modulo count
        # -----------------------------------------
        if not moduloData:
            continue

        moduloCount = max(int(k) for k in moduloData.keys()) + 1

        # -----------------------------------------
        # Build expression
        # -----------------------------------------
        script = """
        float $val = {0}.{1};
        int $r = abs((int)$val % {2});
        {3}
        """.format(driverObj,driverAttr,moduloCount,stringConcat)
        cmds.expression(s=script,o="",ae=True,uc="all")


def Run(data, *args):
    return BuildSDKModulo(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("SDKModulo Export: no saved items")
        return None

    # Export the exact builder using its parsed source; remove diagnostics only.
    functions = (_unique_name, _group_match_object, _create_offset_group, BuildSDKModulo)
    tree = ast.parse("\n\n".join(inspect.getsource(func).rstrip() for func in functions))
    class RemoveWarnings(ast.NodeTransformer):
        def visit_Expr(self, node):
            call = node.value
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "cmds"
                    and call.func.attr == "warning"):
                return None
            return self.generic_visit(node)

    tree = RemoveWarnings().visit(tree)
    ast.fix_missing_locations(tree)
    code = ast.unparse(tree)
    lines = code.splitlines()
    notes = (
        ("    for itemData in datas:", "# Build each saved modulo expression."),
        ("        expandedAttrs = {}", "# Expand multi-line attribute groups."),
        ("        offsetData = {}", "# Reuse or create child offset groups."),
        ("        moduloData = {}", "# Collect authored values for each modulo index."),
        ("        stringConcat = ''", "# Create the expression's conditional clauses."),
    )
    for needle, note in notes:
        for index, line in enumerate(lines):
            if line.lstrip().startswith(needle.strip()):
                indent = line[:len(line) - len(line.lstrip())]
                lines.insert(index, indent + note)
                break
    code = "\n".join("    " + line if line.strip() else "" for line in lines)
    records_source = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # SDKModulo data\n"
        "    MODULO_DATA = " + records_source + "\n\n"
        + code
        + "\n\n    # Build the saved modulo SDK expressions.\n"
        + "    BuildSDKModulo(MODULO_DATA)\n\n"
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

    def AddAttrItem(itemUI,data,*args):
        global ITEMS

        def DeleteAttrItem(itemUI,attrUI,*args):
            cmds.deleteUI(attrUI)
            ITEMS["items"][itemUI]["attrsData"] = [
                x for x in ITEMS["items"][itemUI]["attrsData"]
                if x["ui"] != attrUI
            ]

        if not data:
            selectedData = NLTA_UI.GetSelectedAttribute()
            attrs = selectedData["main"]
            if not attrs:
                return
            AddAttrItem(itemUI,{"attr":selectedData["objs"][0]+"."+selectedData["main"][0],"values":{}})
            return

        attrUI = cmds.rowColumnLayout(numberOfColumns=1,parent=itemData["attrList"])

        cmds.rowColumnLayout(numberOfColumns=3)
        cmds.textField(text="Target Attr",editable=False,w=80)
        targetAttr = cmds.scrollField(text=data["attr"],w=170)
        cmds.rowColumnLayout(nc=1)        
        cmds.button(label="->",w=30,c=partial(NLTA_UI.PickAttrs,targetAttr))
        cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrsAdd,targetAttr))
        cmds.button(label="X",w=30,c=partial(DeleteAttrItem,itemUI,attrUI))
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.rowColumnLayout(numberOfColumns=5)
        values = []
        for i in range(10):
            value = data["values"].get(str(i),"")
            values.append(
                cmds.textField(text=value,w=75)
            )
        cmds.setParent("..")
        cmds.setParent("..")

        ITEMS["items"][itemUI]["attrsData"].append({
            "ui":attrUI,
            "targetAttr":targetAttr,
            "values":values
        })

    itemData = {}

    itemUI = cmds.rowColumnLayout(
        numberOfColumns=1,
        parent=listUI,
        backgroundColor=(0.15,0.15,0.15)
    )

    cmds.rowColumnLayout(numberOfColumns=1)

    # ===== DRIVER ONLY =====
    cmds.rowColumnLayout(numberOfColumns=3)
    cmds.textField(text="Driver",editable=False,w=80)

    itemData["driver"] = cmds.textField(text=data.get("driver",""),width=270)

    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickAttr,itemData["driver"])
    )
    cmds.setParent("..")

    # ===== ATTRS =====
    cmds.rowColumnLayout(numberOfColumns=2)
    cmds.button(label="Add Attr",w=189,c=partial(AddAttrItem,itemUI,{}))
    cmds.button(label="X",w=189,bgc=(0.5,0.2,0.2),c=partial(Delete,itemUI))
    cmds.setParent("..")

    itemData["attrList"] = cmds.scrollLayout(horizontalScrollBarThickness=4,w=400,h=700)
    cmds.setParent("..")
    cmds.setParent("..")

    itemData["attrsData"] = []

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)

    for attr,valueData in data.get("attrsData",{}).items():
        AddAttrItem(
            itemUI,
            {
                "attr":attr,
                "values":valueData
            }
        )








