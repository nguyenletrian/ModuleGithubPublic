import os
import ast
import inspect
import hashlib
import json
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
    name = "Animation Backup"
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
    global sceneDataPath
    def Save(data, *arr):
        itemData = NLTA_General.JsonGetByID({
            "path":data["sceneDataPath"]+"/ScenePatternData.json",
            "id":data["id"]
        })          
        returnData = NLTA_UI.GetData(ITEMS['items'])
        NLTA_General.writeJsonFile(itemData["path"],returnData)

    def SaveAndExport(*args):
        Save(data)
        ExportPython(data)
    sceneDataPath = data["sceneDataPath"]

    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]

    cmds.rowColumnLayout(numberOfColumns=4,parent=buttonUI)
    cmds.button(label="Add",width=130,c=partial(Add,listUI,{}))
    cmds.button(label="Save", width=130,c=partial(Save,data))
    cmds.button(label="Run",width=105,c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=105,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.setParent("..")
    Load(data,listUI)

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def _backup_objects_hash(objects):
    objects = sorted(objects)
    data = "|".join(objects)
    return hashlib.sha1(data.encode("utf-8")).hexdigest()[:12]


def _backup_animation_export(objs, folder):
    """Preserve original animation backup export callback."""
    fileID = _backup_objects_hash(objs)
    filePath = folder + fileID + "_animation.json"
    data = {}
    for obj in objs:
        if not cmds.objExists(obj):
            continue
        longName = cmds.ls(obj,long=True)[0]
        animationData = {}
        attrs = cmds.listAttr(longName,keyable=True) or []
        for attr in attrs:
            plug = "{}.{}".format(longName,attr)
            curves = cmds.listConnections(plug,source=True,destination=False,type="animCurve") or []
            if not curves:
                continue
            curve = curves[0]
            times = cmds.keyframe(curve,query=True,timeChange=True) or []
            values = cmds.keyframe(curve,query=True,valueChange=True) or []
            if not times:
                continue
            animationData[attr] = {"times": times,"values": values}
        if animationData:
            data[obj] = animationData
    with open(filePath, "w") as f:
        json.dump(data,f,indent=4)


def _backup_animation_import(objs, folder):
    """Preserve original animation backup import callback."""
    fileID = _backup_objects_hash(objs)
    filePath = folder + fileID + "_animation.json"
    if not os.path.exists(filePath):
        cmds.warning("File not found: {}".format(filePath))
        return
    with open(filePath, "r") as f:
        data = json.load(f)
    for obj, animationData in data.items():
        if not cmds.objExists(obj):
            continue
        for attr, attrData in animationData.items():
            plug = "{}.{}".format(obj,attr)
            if not cmds.objExists(plug):
                continue
            times = attrData.get("times",[])
            values = attrData.get("values",[])
            if not times:
                continue
            cmds.cutKey(plug,clear=True)
            for time, value in zip(times,values):
                cmds.setKeyframe(plug,time=time,value=value)


def BuildBackupAnimation(records, folder):
    """Run the saved operation; import is opt-in."""
    for record in records or []:
        objects = [obj.strip() for obj in record.get("objects", "").splitlines() if obj.strip()]
        operation = str(record.get("operation") or "export").lower()
        if operation == "export":
            _backup_animation_export(objects, folder)
        elif operation == "import":
            _backup_animation_import(objects, folder)
        else:
            raise ValueError("Unsupported BackupAnimation operation: " + operation)


def Run(data, *args):
    return BuildBackupAnimation(NLTA_General.readJsonFile(_pattern_data_path(data)), data["sceneDataPath"])


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("BackupAnimation Export: no saved records")
        return None

    helpers = (_backup_objects_hash, _backup_animation_export, _backup_animation_import, BuildBackupAnimation)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in helpers))
    body = ast.unparse(tree)
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    rows = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import os\n"
        "    import json\n"
        "    import hashlib\n"
        "    import maya.cmds as cmds\n\n"
        "    # BackupAnimation data\n"
        "    BACKUP_DATA = " + rows + "\n"
        "    BACKUP_FOLDER = " + repr(data["sceneDataPath"]) + "\n\n"
        + body
        + "\n\n    # Restore operations run only when explicitly selected.\n"
        + "    BuildBackupAnimation(BACKUP_DATA, BACKUP_FOLDER)\n\n"
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


def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)


    def Export(ui, *arr):
        objs = cmds.scrollField(ui,query=True,text=True).splitlines()
        objs = [obj.strip() for obj in objs if obj.strip()]
        return _backup_animation_export(objs, sceneDataPath)

    def Import(ui, *arr):
        objs = cmds.scrollField(ui,query=True,text=True).splitlines()
        objs = [obj.strip() for obj in objs if obj.strip()]
        return _backup_animation_import(objs, sceneDataPath)


    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)]) #--

    cmds.textField(text='Objects',editable=False)
    itemData['objects'] = cmds.scrollField(wordWrap=True,height=300,text=data.get("objects", ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['objects']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData['objects']))
    cmds.setParent("..")

    cmds.setParent("..") #--
    cmds.rowColumnLayout(nc=4)
    cmds.button(label="X",width=90,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.button(label="Export",width=90,c=partial(Export,itemData['objects']))
    cmds.button(label="Import",width=90,c=partial(Import,itemData['objects']))
    cmds.setParent("..")
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










