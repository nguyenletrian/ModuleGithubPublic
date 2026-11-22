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

def DefaultSetting(path,*arr):
    moduleName = os.path.basename(__file__).replace(".py","")
    ext = "json"
    name = "ProxyAttribute"
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
    """Resolve the saved UI pattern data."""
    entry = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"],
    })
    return os.path.normpath(entry["path"])


def BuildAttributeProxy(datas):
    """Create proxy attributes from the saved source and targets."""
    if not datas:
        return
    for item in datas:
        source_plug = "{}.{}".format(item["source"], item["sourceAttr"])
        targets = [name.strip() for name in item["targets"].split("\n") if name.strip()]
        if not cmds.objExists(source_plug):
            cmds.warning("Missing source attr : {}".format(source_plug))
            continue
        # Keep an existing proxy unchanged if Maya rejects a duplicate.
        for target in targets:
            if not cmds.objExists(target):
                continue
            try:
                cmds.addAttr(target, proxy=source_plug, ln=item["targetAttr"])
            except Exception:
                pass


def Run(data, *args):
    """Build the saved pattern using the standalone builder."""
    items = NLTA_General.readJsonFile(_pattern_data_path(data))
    return BuildAttributeProxy(items)


def ExportPython(data, *args):
    """Write one independent Maya Python export with embedded data."""
    data_path = _pattern_data_path(data)
    items = NLTA_General.readJsonFile(data_path)
    if not isinstance(items, list) or not items:
        cmds.warning("AttributeProxy Export: no saved items")
        return None

    # Embed each saved item as one Python dictionary per line.
    data_text = "[\n" + ",\n".join("        " + repr(item) for item in items) + "\n    ]"
    functions = (BuildAttributeProxy,)
    source_text = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    # The standalone builder silently skips unavailable attributes.
    old_warning = '            cmds.warning("Missing source attr : {}".format(source_plug))\n'
    if old_warning not in source_text:
        raise RuntimeError("Cannot locate optional source-attribute warning")
    source_text = source_text.replace(old_warning, "")
    # Keep English comments and exact builder calls from the runtime version.
    source_text = "\n".join("    " + line if line.strip() else "" for line in source_text.splitlines())
    result = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # AttributeProxy data\n"
        "    PATTERN_DATA = " + data_text + "\n\n"
        + source_text
        + "\n\n    # Build the saved Maya pattern.\n"
        + "    BuildAttributeProxy(PATTERN_DATA)\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(result, filename, "exec")
    output = os.path.join(os.path.dirname(data_path), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(result)
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
    cmds.textField(text="Source",editable=False)
    itemData["source"] = cmds.textField(text=data.get("source",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObject,itemData["source"]))
    cmds.setParent("..")

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Source Attr",editable=False)
    itemData["sourceAttr"] = cmds.textField(text=data.get("sourceAttr",""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrOnly,itemData["sourceAttr"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3,columnWidth=[(1,80),(2,265),(3,32)])
    cmds.textField(text="Targets",editable=False)
    itemData["targets"] = cmds.scrollField(text=data.get("targets",""),h=80)
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData["targets"]))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd,itemData["targets"]))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=2,columnWidth=[(1,80),(2,297)])
    cmds.textField(text="Target Attr",editable=False)
    itemData["targetAttr"] = cmds.textField(text=data.get("targetAttr",""))
    cmds.setParent("..")

    cmds.button(label="X",w=380,bgc=(0.5,0.2,0.2),c=partial(Delete,itemUI))

    cmds.setParent("..")
    cmds.setParent("..")

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)









