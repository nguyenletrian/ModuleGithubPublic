import os
import ast
import inspect
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
from datetime import datetime
from maya.api import OpenMaya as om
import xml.etree.ElementTree as ET

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
    name = "Match Pairs"
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


def _matchpairs_distance(sources, targets):
    # Same nearest-distance and namespace handling as the original UI button.
    result = []
    for source in sources:
        if not cmds.objExists(source):
            result.append("")
            continue
        srcPos = cmds.xform(source, q=True, ws=True, t=True)
        nearest = None
        nearestDist = None
        for target in targets:
            if not cmds.objExists(target):
                continue
            src = om.MVector(cmds.xform(source, q=True, ws=True, t=True))
            tar = om.MVector(cmds.xform(target, q=True, ws=True, t=True))
            dist = (src - tar).length()
            if nearestDist is None or dist < nearestDist:
                nearestDist = dist
                nearest = target
        result.append(nearest.rsplit(":", 1)[-1] if nearest else "")
    return result


def _matchpairs_select(sources, targets, index):
    count = min(len(sources), len(targets))
    if count == 0:
        return index
    if index >= count:
        index = 0
    source = sources[index]
    target = targets[index]
    selects = []
    if cmds.objExists(source):
        selects.append(source)
    if cmds.objExists(target):
        selects.append(target)
    if selects:
        cmds.select(selects, r=True)
    print("[{}] {}  <-->  {}".format(index, source, target))
    return index + 1


def _matchpairs_transfer_xml(sources, targets, xmlPath):
    if len(sources) != len(targets):
        cmds.error("Sources and Targets must have the same number of lines.")
    replaceDict = dict(zip(sources, targets))
    tree = ET.parse(xmlPath)
    root = tree.getroot()
    for elem in root.iter():
        for attr, value in list(elem.attrib.items()):
            if value in replaceDict:
                elem.set(attr, replaceDict[value])
        if elem.text:
            text = elem.text.strip()
            if text in replaceDict:
                elem.text = replaceDict[text]
    base, ext = os.path.splitext(xmlPath)
    newPath = base + "_transferred" + ext
    tree.write(newPath, encoding="utf-8", xml_declaration=True)
    print("Saved:", newPath)
    return newPath


def BuildMatchPairs(datas):
    """Apply the original UI operations to saved source/target rows."""
    results = []
    for record in datas or []:
        sources = [x.strip() for x in record.get("sources", "").splitlines() if x.strip()]
        targets = [x.strip() for x in record.get("targets", "").splitlines() if x.strip()]
        operation = str(record.get("operation") or "distance").lower()
        if operation == "distance":
            selected = cmds.ls(sl=True)
            if not sources or not selected:
                results.append([])
                continue
            matches = _matchpairs_distance(sources, selected)
            for index, (source, match) in enumerate(zip(sources, matches)):
                print("[{}] {}  <-->  {}".format(index, source, match))
            results.append(matches)
        elif operation == "select_pair":
            results.append(_matchpairs_select(sources, targets, int(record.get("pairIndex", 0))))
        elif operation == "transfer_xml":
            paths = cmds.fileDialog2(fileMode=1, caption="Select Skin XML", fileFilter="Skin XML (*.xml)")
            if not paths:
                results.append(None)
                continue
            results.append(_matchpairs_transfer_xml(sources, targets, paths[0]))
        else:
            raise ValueError("Unsupported MatchPairs operation: " + operation)
    return results


def Run(data, *args):
    return BuildMatchPairs(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("MatchPairs Export: no saved items")
        return None

    functions = (_matchpairs_distance, _matchpairs_select,
                 _matchpairs_transfer_xml, BuildMatchPairs)
    tree = ast.parse("\n\n".join(inspect.getsource(func).rstrip() for func in functions))
    body = ast.unparse(tree)
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    embedded = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import os\n"
        "    import maya.cmds as cmds\n"
        "    import maya.api.OpenMaya as om\n"
        "    import xml.etree.ElementTree as ET\n\n"
        "    # MatchPairs data\n"
        "    MATCH_DATA = " + embedded + "\n\n"
        + body
        + "\n\n    # Execute the explicitly selected saved matching action.\n"
        + "    return BuildMatchPairs(MATCH_DATA)\n\n"
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


def OpenExportFolder(data, *arr):
    os.startfile(os.path.dirname(_pattern_data_path(data)))


PAIR_INDEX = 0
def Add(listUI,data,*arr):
    global ITEMS
    def Delete(ui,*arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    def MatchByDistance(sourcesUI, targetsUI, *arr):
        text = cmds.scrollField(sourcesUI, q=True, text=True)
        sources = [x.strip() for x in text.splitlines() if x.strip()]
        targets = cmds.ls(sl=True)
        if not sources or not targets:
            return
        result = _matchpairs_distance(sources, targets)
        cmds.scrollField(targetsUI, e=True, text="\n".join(result))

    def SelectPair(sourcesUI, targetsUI, *args):
        global PAIR_INDEX
        sourceText = cmds.scrollField(sourcesUI, q=True, text=True)
        sources = [x.strip() for x in sourceText.splitlines() if x.strip()]
        targetText = cmds.scrollField(targetsUI, q=True, text=True)
        targets = [x.strip() for x in targetText.splitlines() if x.strip()]
        PAIR_INDEX = _matchpairs_select(sources, targets, PAIR_INDEX)

    def TransferSkinXML(sourcesUI, targetsUI, *args):
        paths = cmds.fileDialog2(fileMode=1,caption="Select Skin XML",fileFilter="Skin XML (*.xml)")
        if not paths:
            return
        sourceText = cmds.scrollField(sourcesUI, q=True, text=True)
        sources = [x.strip() for x in sourceText.splitlines() if x.strip()]
        targetText = cmds.scrollField(targetsUI, q=True, text=True)
        targets = [x.strip() for x in targetText.splitlines() if x.strip()]
        return _matchpairs_transfer_xml(sources, targets, paths[0])

    itemData = {}   
    itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))
    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout(numberOfColumns=2)#-

    cmds.rowColumnLayout( numberOfColumns=2,columnWidth=[(1,150),(2,32)]) #--
    itemData['sources'] = cmds.scrollField(height=300,text=data.get('sources', ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['sources']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd, itemData['sources']))
    cmds.setParent("..")
    cmds.setParent("..") #--


    cmds.rowColumnLayout( numberOfColumns=2,columnWidth=[(1,150),(2,32)]) #--
    itemData['targets'] = cmds.scrollField(height=300,text=data.get('targets', ""))
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickObject,itemData['targets']))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickObjectAdd, itemData['targets']))
    cmds.setParent("..")
    cmds.setParent("..") #--

    cmds.setParent("..") #-

    cmds.rowColumnLayout(nc=4)
    cmds.button(label="X",w=100,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.button(label="Match By Distance",c=partial(MatchByDistance,itemData['sources'],itemData["targets"]))
    cmds.button(label="Select pair",c=partial(SelectPair,itemData['sources'],itemData["targets"]))
    cmds.button(label="Transfer XML",c=partial(TransferSkinXML,itemData['sources'],itemData["targets"]))
    cmds.separator(height=10, style='none')
    
    cmds.setParent("..")    
    cmds.setParent("..")

    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)










