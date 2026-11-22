import os
import importlib
import inspect
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

###########################

def DefaultSetting(path,*arr):
    moduleName = os.path.basename(__file__).replace(".py","")
    ext = "json"
    name = "Replace Path"
    return({
        "ext":ext,
        "path":path+moduleName+"."+ext,
        "moduleName":moduleName,
        "order":0,
        "title":name,
        "name":name,
        "id":datetime.now().strftime("%Y%m%d%H%M%S")
    })

def _pattern_data_path(data):
    entry = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(entry["path"])


def BuildPathReplace(datas):
    for item in datas:
        path = item["path"]
        file_map = {}
        # Find supported texture files by filename.
        for root, _, files in os.walk(path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in (".tga", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".dds", ".bmp", ".exr", ".hdr"):
                    continue
                file_map[f.lower()] = os.path.join(root, f).replace("\\", "/")

        # Update matching Maya file nodes.
        for node in cmds.ls(type="file"):
            value = cmds.getAttr(node + ".fileTextureName")
            if not value:
                continue
            value = value.replace("\\", "/")
            filename = os.path.basename(value).lower()
            if filename not in file_map:
                continue
            new_path = file_map[filename]
            if value == new_path:
                continue
            cmds.setAttr(node + ".fileTextureName", new_path, type="string")


def Run(data, *arr):
    return BuildPathReplace(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *arr):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("PathReplace Export: no saved items")
        return None

    # Embed the same builder used by Run without UI or JSON dependencies.
    rows = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    builder_source = "\n".join("    " + line if line.strip() else "" for line in inspect.getsource(BuildPathReplace).rstrip().splitlines())
    source = (
        "def main():\n"
        "    import os\n"
        "    import maya.cmds as cmds\n\n"
        "    # PathReplace data\n"
        "    PATTERN_DATA = " + rows + "\n\n"
        + builder_source
        + "\n\n    # Reconnect matching texture paths.\n"
        + "    BuildPathReplace(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in source:
        source = source.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as writer:
        writer.write(source)
    return output


def OpenExportFolder(data, *arr):
    os.startfile(os.path.dirname(_pattern_data_path(data)))


def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI)

    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,260),(3,35)]) #--

    cmds.textField(text='Path',editable=False)
    itemData['path'] = cmds.scrollField(wordWrap=True,height=100,text=data.get("path", ""))
    cmds.text("")

    cmds.setParent("..") #--

    
    cmds.separator(height=10, style='none')

    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










