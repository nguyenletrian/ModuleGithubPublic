import os
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
    name = "Path Links"
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

    def SaveAndExport(*args):
        Save(data)
        ExportPython(data)

    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]

    cmds.rowColumnLayout(numberOfColumns=3,parent=buttonUI)
    cmds.button(label="Add",width=130,c=partial(Add,listUI,{}))
    cmds.button(label="Save", width=130,c=partial(Save,data))
    cmds.button(label="Run",width=105,c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=110,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.setParent("..")
    Load(data,listUI)

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def _pathlink_open(path):
    path = os.path.normpath(path)
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if os.path.isdir(path):
        os.startfile(path)
    else:
        cmds.warning("Path does not exist: {}".format(path))


def _pathlink_send(path):
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        cmds.warning("Path does not exist: {}".format(path))
        return
    currentScene = cmds.file(q=True, sn=True)
    if not currentScene:
        cmds.warning("Current scene has not been saved yet.")
        return
    fileName = os.path.basename(currentScene)
    name, ext = os.path.splitext(fileName)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    savePath = os.path.join(path, "{}_{}{}".format(name,timestamp,ext))
    try:
        cmds.file(rename=savePath)
        cmds.file(save=True)
    finally:
        cmds.file(rename=currentScene)
    os.startfile(path)

# ============================================================
# DYNAMIC SCROLL FIELD LIST (generic, reusable)
# ============================================================


def BuildPathLink(records):
    """Keep old Run inert by default; require explicit open/send actions."""
    results = []
    for record in records or []:
        operation = str(record.get("operation") or "none").lower()
        path = record.get("path", "")
        if operation == "none":
            continue
        if operation == "open":
            results.append(_pathlink_open(path))
        elif operation == "send":
            results.append(_pathlink_send(path))
        else:
            raise ValueError("Unsupported PathLink operation: " + operation)
    return results


def Run(data, *args):
    return BuildPathLink(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("PathLink Export: no saved items")
        return None
    if not any(str(record.get("operation") or "none").lower() in ("open", "send") for record in records):
        cmds.warning("PathLink Export: choose open or send explicitly")
        return None

    functions = (_pathlink_open, _pathlink_send, BuildPathLink)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions))
    code = ast.unparse(tree)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    embedded = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import os\n"
        "    from datetime import datetime\n"
        "    import maya.cmds as cmds\n\n"
        "    # PathLink data: send changes/saves the Maya scene.\n"
        "    PATH_LINK_DATA = " + embedded + "\n\n"
        + code
        + "\n\n    # Explicitly execute only saved open/send actions.\n"
        + "    return BuildPathLink(PATH_LINK_DATA)\n\n"
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


    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))
    cmds.rowColumnLayout( numberOfColumns=2,columnWidth=[(1,300),(2,150)]) #--

    itemData['name'] = cmds.textField(text=data.get("name", "Tên link"))
    cmds.text(label="")
    itemData['path'] = cmds.scrollField(text=data.get("path","Đường dẫn"),height=30)
    itemData["operation"] = cmds.optionMenu()
    for label in ("none", "open", "send"):
        cmds.menuItem(label=label)
    cmds.optionMenu(itemData["operation"], e=True, value=data.get("operation", "none"))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="Open",w=80,height=29,c=partial(NLTA_UI.OpenFolder,itemData['path']))
    cmds.button(label="Send",w=80,height=29,c=partial(NLTA_UI.SendFile,itemData['path']))
    cmds.button(label="X",w=80,height=29,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))

    cmds.setParent("..")

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










