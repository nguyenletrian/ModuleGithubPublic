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
    name = "BS Sequel From Obj Keys"
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



def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def BuildBSSequenceFromObjKeys(datas):
    """Create keyed blendshape samples using the original active Run behavior."""
    if not datas:
        return
    for item in datas:
        mesh = item["mesh"]
        meshAnimation = item["meshAnimation"]
        objectAnimation = item["objectAnimation"]
        attrHolders = [holder for holder in item["attrHolder"].split("\n") if holder and cmds.objExists(holder)]
        if not attrHolders:
            cmds.warning("No valid attrHolder for {}".format(mesh))
            continue
        mainAttrHolder = attrHolders[0]
        jointHolder = item["jointHolder"]
        attr = item["attr"]
        bsParent = item["bsParent"]

        # -----------------------------------------------------
        # Get animation keyframes
        # -----------------------------------------------------
        if not cmds.objExists(objectAnimation):
            cmds.warning("Object animation not found: {}".format(objectAnimation))
            continue

        keyframes = set()
        transformAttrs = [
            "tx", "ty", "tz",
            "rx", "ry", "rz",
            "sx", "sy", "sz"
        ]
        for transformAttr in transformAttrs:
            plug = "{}.{}".format(objectAnimation,transformAttr)
            if not cmds.objExists(plug):
                continue
            frames = cmds.keyframe(plug,query=True,timeChange=True) or []
            keyframes.update(frames)

        keyframes = sorted(frame for frame in keyframes if frame != 0)
        if not keyframes:
            cmds.warning("No animation keyframes found on {}".format(objectAnimation))
            continue

        # -----------------------------------------------------
        # Current frame
        # -----------------------------------------------------

        currentFrame = cmds.currentTime(query=True)
        generatedMeshes = []

        # -----------------------------------------------------
        # Generate meshes from animation
        # -----------------------------------------------------

        for index, frame in enumerate(keyframes, 1):
            cmds.currentTime(frame, edit=True)
            duplicate = cmds.duplicate( meshAnimation,rr=True,inputConnections=False,upstreamNodes=False)[0]
            duplicate = cmds.rename(duplicate,"{}_Shoot_{:02d}".format(mesh, index))
            generatedMeshes.append(duplicate)


        # -----------------------------------------------------
        # Restore current frame
        # -----------------------------------------------------

        cmds.currentTime(currentFrame,edit=True)
        if not generatedMeshes:
            cmds.warning("No generated meshes for {}".format(mesh))
            continue

        # -----------------------------------------------------
        # Create BS group
        # -----------------------------------------------------
        bsGroup = "{}_BSs".format(mesh)
        if cmds.objExists(bsGroup):
            cmds.delete(bsGroup)
        bsGroup = cmds.group(generatedMeshes,name=bsGroup)

        if bsParent and cmds.objExists(bsParent):
            cmds.parent(bsGroup,bsParent)

        # -----------------------------------------------------
        # Create blendShape
        # -----------------------------------------------------

        blendShapeName = "{}_{}_BS".format(mesh,attr)
        blendShape = cmds.blendShape(generatedMeshes,mesh,name=blendShapeName)[0]
        # -----------------------------------------------------
        # Main attribute
        # -----------------------------------------------------

        mainAttr = "{}.{}".format(mainAttrHolder,attr)
        if not cmds.attributeQuery(attr,node=mainAttrHolder,exists=True):
            cmds.addAttr(mainAttrHolder,longName=attr,attributeType="double",minValue=0,maxValue=10,defaultValue=0)
        cmds.setAttr(mainAttr,edit=True,keyable=True)

        # -----------------------------------------------------
        # Proxy attributes
        # -----------------------------------------------------
        for holder in attrHolders[1:]:
            if not cmds.attributeQuery(attr,node=holder,exists=True):
                cmds.addAttr(holder,longName=attr,attributeType="double",proxy=mainAttr)
            cmds.setAttr("{}.{}".format(holder,attr),edit=True,keyable=True)

        # -----------------------------------------------------
        # Joint holder attribute
        # -----------------------------------------------------

        jointAttr = "{}.{}".format(jointHolder,attr)
        if not cmds.attributeQuery(attr,node=jointHolder,exists=True):
            cmds.addAttr(jointHolder,longName=attr,attributeType="double",minValue=0,maxValue=10,defaultValue=0)
        cmds.setAttr(jointAttr,edit=True,keyable=True)
        cmds.connectAttr(mainAttr,jointAttr,force=True)        
        # -----------------------------------------------------
        # Driven keys
        # -----------------------------------------------------

        driver = mainAttr
        numShapes = len(generatedMeshes)
        segment = 10.0 / numShapes

        # -----------------------------------------------------
        # Initial state
        # -----------------------------------------------------
        cmds.setAttr(driver,0)
        for index in range(numShapes):
            blendAttr = "{}.w[{}]".format(blendShape,index)
            cmds.setAttr(blendAttr,0)
            cmds.setDrivenKeyframe(blendAttr,currentDriver=driver)

        # -----------------------------------------------------
        # Shoot states
        # -----------------------------------------------------
        for step in range(numShapes):
            shootValue = segment * (step + 1)
            if step == numShapes - 1:
                shootValue -= (segment * 0.5)
            cmds.setAttr(driver,shootValue)
            for index in range(numShapes):
                blendAttr = "{}.w[{}]".format(blendShape,index)
                if index == step:
                    value = 1.0
                elif index == step - 1:
                    value = 0.5
                elif index == step + 1:
                    value = 0.5
                else:
                    value = 0.0
                cmds.setAttr(blendAttr,value)
                cmds.setDrivenKeyframe(blendAttr,currentDriver=driver)

        # -----------------------------------------------------
        # End state
        # -----------------------------------------------------
        cmds.setAttr(driver,10)
        for index in range(numShapes):
            blendAttr = "{}.w[{}]".format(blendShape,index)
            cmds.setAttr(blendAttr,0)
            cmds.setDrivenKeyframe(blendAttr,currentDriver=driver)

        # -----------------------------------------------------
        # Show BS attribute
        # -----------------------------------------------------

        showAttr = "{}ShowBS".format(attr)
        mainShowAttr = "{}.{}".format(mainAttrHolder,showAttr)
        if not cmds.attributeQuery(showAttr,node=mainAttrHolder,exists=True):
            cmds.addAttr(mainAttrHolder,longName=showAttr,attributeType="bool",defaultValue=False)
        cmds.setAttr(mainShowAttr,edit=True,keyable=True)

        for holder in attrHolders[1:]:
            proxyShowAttr = "{}.{}".format(holder,showAttr)
            if not cmds.attributeQuery(showAttr,node=holder,exists=True):
                cmds.addAttr(holder,longName=showAttr,attributeType="bool",proxy=mainShowAttr)
            cmds.setAttr(proxyShowAttr,edit=True,keyable=True)
        cmds.connectAttr(mainShowAttr,bsGroup + ".visibility",force=True)
        cmds.setAttr(driver,0)
        cmds.currentTime(currentFrame,edit=True)

def Run(data, *args):
    return BuildBSSequenceFromObjKeys(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("BSSequenceFromObjKeys Export: no saved items")
        return None

    # Reuse the Run builder AST and omit nonessential warnings in the export.
    builder_ast = ast.parse(inspect.getsource(BuildBSSequenceFromObjKeys))

    class RemoveDiagnostics(ast.NodeTransformer):
        def visit_Expr(self, node):
            call = node.value
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "cmds" and call.func.attr == "warning"):
                return None
            return self.generic_visit(node)

    builder_ast = RemoveDiagnostics().visit(builder_ast)
    ast.fix_missing_locations(builder_ast)
    builder_source = ast.unparse(builder_ast)

    # Restore short English notes at stable code anchors.
    notes = (
        ("    for item in datas:", "    # Process each saved blendshape sequence."),
        ("        keyframes = set()", "        # Collect unique nonzero transform keyframes."),
        ("        for index, frame in enumerate(", "        # Duplicate the animated mesh at each keyframe."),
        ("        bsGroup =", "        # Replace the original sample group and create the blendshape."),
        ("        driver = mainAttr", "        # Key the initial, sample and final blendshape weights."),
        ("        showAttr =", "        # Make the blendshape sample group visibility controllable."),
    )
    lines = builder_source.splitlines()
    for anchor, comment in notes:
        for index, line in enumerate(lines):
            if line.lstrip().startswith(anchor.strip()):
                indent = line[:len(line) - len(line.lstrip())]
                lines.insert(index, indent + comment.strip())
                break

    builder_source = "\n".join("    " + line if line.strip() else "" for line in lines)
    data_source = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    generated = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # BSSequenceFromObjKeys data\n"
        "    BS_DATA = " + data_source + "\n\n"
        + builder_source
        + "\n\n    # Construct the saved blendshape sequences.\n"
        + "    BuildBSSequenceFromObjKeys(BS_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in generated:
        generated = generated.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(generated, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(generated)
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


    cmds.textField(text='Mesh',editable=False)
    itemData['mesh'] = cmds.textField(text=data.get('mesh', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['mesh']))
    
    cmds.textField(text='Mesh Animation',editable=False)
    itemData['meshAnimation'] = cmds.textField(text=data.get('meshAnimation', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['meshAnimation']))


    cmds.textField(text='Obj Animation',editable=False)
    itemData['objectAnimation'] = cmds.textField(text=data.get('objectAnimation', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objectAnimation']))

    cmds.textField(text='BS Parent',editable=False)
    itemData['bsParent'] = cmds.textField(text=data.get('bsParent', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['bsParent']))


    cmds.textField(text='Attr Holder',editable=False)
    itemData['attrHolder'] = cmds.textField(text=data.get('attrHolder', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['attrHolder']))

    cmds.textField(text='Joint Holder',editable=False)
    itemData['jointHolder'] = cmds.textField(text=data.get('jointHolder', ""))
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['jointHolder']))

    cmds.textField(text='Attr',editable=False)
    itemData['attr'] = cmds.textField(text=data.get('attr', ""))
    cmds.text("..")

    cmds.setParent("..") #--

    cmds.button(label="X",w=35,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










