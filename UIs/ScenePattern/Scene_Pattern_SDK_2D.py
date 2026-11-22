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
    name = "Driven Key 2D"
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
        global ITEMS
        itemData = NLTA_General.JsonGetByID({
            "path":data["sceneDataPath"]+"/ScenePatternData.json",
            "id":data["id"]
        })
        saveData = []
        for itemUI in ITEMS["order"]:
            item = ITEMS["items"][itemUI]
            itemDict = {
                "driverAttr":cmds.textField(item["driverAttr"],q=True,text=True),
                "driverAttr1":cmds.textField(item["driverAttr1"],q=True,text=True),
                "drivenAttrs":cmds.scrollField(item["drivenAttrs"],q=True,text=True),
                "keyData":[],
                "switchAttr":cmds.textField(item["switchAttr"],q=True,text=True),
            }
            for keyUI in item["keyUI"]:
                keyDict = {
                    "driverValue":cmds.textField(keyUI["driverValue"],q=True,text=True),
                    "driverValue1":cmds.textField(keyUI["driverValue1"],q=True,text=True),
                    "drivenValues":{}
                }
                for obj,attrUIs in keyUI["drivenValues"].items():
                    keyDict["drivenValues"][obj] = {}
                    for attr,valueUI in attrUIs.items():
                        keyDict["drivenValues"][obj][attr] = cmds.textField(valueUI,q=True,text=True)
                itemDict["keyData"].append(keyDict)
            saveData.append(itemDict)
        NLTA_General.writeJsonFile(itemData["path"],saveData)

    def SaveAndExport(*args):
        Save(data)
        ExportPython(data)

    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]
    cmds.rowColumnLayout(numberOfColumns=4,parent=buttonUI)
    cmds.button(label="Add",width=100,c=partial(Add,listUI,{}))
    cmds.button(label="Save",width=100,c=partial(Save,data))
    cmds.button(label="Run",width=100,c=partial(Run,data))
    export_button = cmds.button(label="Export Py",width=100,c=SaveAndExport)
    cmds.popupMenu(parent=export_button,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder,data))
    cmds.button(label="Mirror All",width=100,c=partial(CreateMirrorAll,listUI))
    cmds.button(label="Merge Duplicate",width=100,c=partial(MergeDuplicate,listUI))
    cmds.button(label="Remove Object",width=100,backgroundColor=(.5,.2,.2),c=partial(RemoveObjectFromAllData,listUI))
    cmds.button(label="Replace Object",width=100,c=partial(ReplaceObjectInAllData,listUI))
    cmds.setParent("..")
    Load(data,listUI)


def CreateMirror(itemUI, listUI, *args):
    global ITEMS
    item = ITEMS["items"][itemUI]
    driverAttr = cmds.textField(item["driverAttr"], q=True, text=True).strip()
    if "." not in driverAttr:
        return
    driverObj, driverName = driverAttr.rsplit(".", 1)
    mirrorDriverObj = NLTA_General.GetMirrorName(driverObj)
    driverAttr1 = cmds.textField(item["driverAttr1"], q=True, text=True).strip()
    mirrorDriverAttr1 = ""
    if driverAttr1 and "." in driverAttr1:
        obj1, attr1 = driverAttr1.rsplit(".", 1)
        mirrorDriverAttr1 = NLTA_General.GetMirrorName(obj1) + "." + attr1

    if mirrorDriverObj == driverObj:
        cmds.warning("Skip Mirror : " + driverObj)
        return

    if not cmds.objExists(mirrorDriverObj):
        cmds.warning("Mirror object not found : " + mirrorDriverObj)
        return

    # -----------------------------------
    # Driven Attrs
    # -----------------------------------
    mirrorDrivenAttrs = []

    drivenAttrs = cmds.scrollField(item["drivenAttrs"],q=True,text=True).splitlines()
    for drivenAttr in drivenAttrs:
        drivenAttr = drivenAttr.strip()
        if "." not in drivenAttr:
            continue
        obj, attr = drivenAttr.rsplit(".", 1)
        mirrorObj = NLTA_General.GetMirrorName(obj)
        mirrorDrivenAttrs.append(mirrorObj + "." + attr)
    mirrorKeyData = []

    for keyUI in item["keyUI"]:
        driverValue = cmds.textField(keyUI["driverValue"],q=True,text=True)
        keyData = {"driverValue": driverValue,"driverValue1": cmds.textField(keyUI["driverValue1"], q=True, text=True),"drivenValues": {}}
        for obj, attrUIs in keyUI["drivenValues"].items():
            mirrorObj = NLTA_General.GetMirrorName(obj)
            keyData["drivenValues"][mirrorObj] = {}
            for attr, valueUI in attrUIs.items():
                value = cmds.textField(valueUI,q=True,text=True)
                keyData["drivenValues"][mirrorObj][attr] = value
        mirrorKeyData.append(keyData)
    mirrorData = {
        "driverAttr": mirrorDriverObj + "." + driverName,
        "driverAttr1": mirrorDriverAttr1,
        "drivenAttrs": "\n".join(mirrorDrivenAttrs),
        "switchAttr": cmds.textField(item["switchAttr"], q=True, text=True),
        "keyData": mirrorKeyData
    }

    Add(listUI, mirrorData)

def CreateMirrorAll(listUI, *args):
    global ITEMS
    currentItems = list(ITEMS["order"])
    count = 0
    for itemUI in currentItems:
        before = len(ITEMS["order"])
        CreateMirror(itemUI, listUI)
        if len(ITEMS["order"]) > before:
            count += 1
    cmds.warning("Mirror All SDK Data Done! Created : {}".format(count))

def GetItemData(itemUI):
    global ITEMS
    item = ITEMS["items"][itemUI]
    data = {
        "driverAttr": cmds.textField(
            item["driverAttr"], q=True, text=True
        ).strip(),
        "driverAttr1": cmds.textField(
            item["driverAttr1"], q=True, text=True
        ).strip(),
        "switchAttr": cmds.textField(item["switchAttr"], q=True, text=True),
        "drivenAttrs": cmds.scrollField(
            item["drivenAttrs"], q=True, text=True
        ),
        "keyData": []
    }
    for keyUI in item["keyUI"]:
        keyData = {
            "driverValue": cmds.textField(keyUI["driverValue"], q=True, text=True),
            "driverValue1": cmds.textField(keyUI["driverValue1"], q=True, text=True),
            "drivenValues": {}
        }
        for obj, attrUIs in keyUI["drivenValues"].items():
            keyData["drivenValues"][obj] = {}
            for attr, valueUI in attrUIs.items():
                keyData["drivenValues"][obj][attr] = cmds.textField(valueUI, q=True, text=True)
        data["keyData"].append(keyData)
    return data

def MergeDuplicate(listUI, *args):
    global ITEMS
    allData = [
        GetItemData(itemUI)
        for itemUI in ITEMS["order"]
        if itemUI in ITEMS["items"]
    ]

    merged = {}
    order = []
    for item in allData:
        driverAttr = item["driverAttr"]
        driverAttr1 = item.get("driverAttr1", "")
        driverKey = (driverAttr, driverAttr1)
        if driverKey not in merged:
            merged[driverKey] = {
                "driverAttr": driverAttr,
                "driverAttr1": driverAttr1,
                "switchAttr": item.get("switchAttr", ""),
                "drivenAttrs": [],
                "keyData": {}
            }
            order.append(driverKey)
        target = merged[driverKey]

        # --------------------------------
        # Merge drivenAttrs
        # --------------------------------
        for drivenAttr in item["drivenAttrs"].splitlines():
            drivenAttr = drivenAttr.strip()

            if drivenAttr and drivenAttr not in target["drivenAttrs"]:
                target["drivenAttrs"].append(drivenAttr)

        # --------------------------------
        # Merge keyData theo driverValue
        # --------------------------------
        for keyData in item["keyData"]:

            driverValue = keyData["driverValue"]

            # 0, 0.0, 0.000 phải xem là cùng value
            try:
                valueKey = float(driverValue)
            except:
                valueKey = driverValue

            driverValue1 = keyData.get("driverValue1", "0")
            try:
                valueKey1 = float(driverValue1)
            except (TypeError, ValueError):
                valueKey1 = driverValue1
            valueKey = (valueKey1, valueKey)

            if valueKey not in target["keyData"]:
                target["keyData"][valueKey] = {
                    "driverValue": driverValue,
                    "driverValue1": driverValue1,
                    "drivenValues": {}
                }

            targetKey = target["keyData"][valueKey]

            # --------------------------------
            # Merge driven objects + attrs
            # --------------------------------
            for obj, attrData in keyData["drivenValues"].items():

                if obj not in targetKey["drivenValues"]:
                    targetKey["drivenValues"][obj] = {}

                for attr, value in attrData.items():

                    targetKey["drivenValues"][obj][attr] = value

    # --------------------------------
    # Convert về format cũ
    # --------------------------------
    result = []

    for driverKey in order:
        item = merged[driverKey]

        result.append({
            "driverAttr": item["driverAttr"],
            "driverAttr1": item["driverAttr1"],
            "switchAttr": item["switchAttr"],
            "drivenAttrs": "\n".join(item["drivenAttrs"]),
            "keyData": list(item["keyData"].values())
        })

    # --------------------------------
    # Clear UI + ITEMS
    # --------------------------------
    children = cmds.layout(listUI, q=True, ca=True) or []

    for child in children:
        if cmds.control(child, exists=True) or cmds.layout(child, exists=True):
            cmds.deleteUI(child)

    ITEMS = {
        "items": {},
        "order": []
    }

    # Rebuild
    for item in result:
        Add(listUI, item)

    cmds.warning(
        "Merge Duplicate Done! {} -> {} Items".format(
            len(allData),
            len(result)
        )
    )


def RemoveObjectFromAllData(listUI, *args):
    global ITEMS

    sel = cmds.ls(sl=True, long=True) or []

    if not sel:
        result = cmds.promptDialog(
            title="Remove Object From All Data",
            message="Object Name:",
            button=["Remove", "Cancel"],
            defaultButton="Remove",
            cancelButton="Cancel",
            dismissString="Cancel"
        )

        if result != "Remove":
            return

        objName = cmds.promptDialog(q=True, text=True).strip()
        if not objName:
            return

        sel = [objName]

    removeNames = set()

    for obj in sel:
        removeNames.add(obj)
        removeNames.add(obj.split("|")[-1])

    removedObjects = 0
    removedValues = 0

    for itemUI in list(ITEMS["order"]):

        if itemUI not in ITEMS["items"]:
            continue

        item = ITEMS["items"][itemUI]

        # --------------------------------
        # Remove khỏi Driven Attrs
        # --------------------------------
        drivenAttrs = cmds.scrollField(
            item["drivenAttrs"],
            q=True,
            text=True
        ).splitlines()

        keepAttrs = []

        for drivenAttr in drivenAttrs:

            drivenAttr = drivenAttr.strip()

            if "." not in drivenAttr:
                if drivenAttr:
                    keepAttrs.append(drivenAttr)
                continue

            obj, attr = drivenAttr.rsplit(".", 1)
            shortObj = obj.split("|")[-1]

            if obj in removeNames or shortObj in removeNames:
                continue

            keepAttrs.append(drivenAttr)

        cmds.scrollField(
            item["drivenAttrs"],
            e=True,
            text="\n".join(keepAttrs)
        )

        # --------------------------------
        # Remove khỏi tất cả Value
        # --------------------------------
        for keyUI in list(item["keyUI"]):

            found = False

            for obj in list(keyUI["drivenValues"].keys()):

                shortObj = obj.split("|")[-1]

                if obj not in removeNames and shortObj not in removeNames:
                    continue

                objectUI = keyUI.get(
                    "drivenObjectUIs", {}
                ).get(obj)

                if objectUI and cmds.layout(objectUI, exists=True):
                    cmds.deleteUI(objectUI)

                del keyUI["drivenValues"][obj]

                if obj in keyUI.get("drivenObjectUIs", {}):
                    del keyUI["drivenObjectUIs"][obj]

                found = True
                removedObjects += 1

            # Value rỗng -> delete luôn
            if not keyUI["drivenValues"]:

                keyName = keyUI["keyName"]

                if cmds.layout(keyName, exists=True):
                    cmds.deleteUI(keyName)

                item["keyUI"].remove(keyUI)
                removedValues += 1

        remainingDrivenAttrs = cmds.scrollField(
            item["drivenAttrs"],
            q=True,
            text=True
        ).strip()

        if not remainingDrivenAttrs:

            if cmds.layout(itemUI, exists=True):
                cmds.deleteUI(itemUI)

            if itemUI in ITEMS["items"]:
                del ITEMS["items"][itemUI]

            if itemUI in ITEMS["order"]:
                ITEMS["order"].remove(itemUI)

            continue

    cmds.warning(
        "Remove Object From All Data Done! Objects: {} | Empty Values: {}".format(
            removedObjects,
            removedValues
        )
    )


        

def ReplaceObjectInAllData(listUI, *args):
    global ITEMS
    win = "SDKReplaceObjectWindow"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)
    cmds.window(win,title="Replace Object",widthHeight=(360,130),sizeable=False)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=5)
    cmds.rowLayout(numberOfColumns=2,columnWidth2=(90,250))
    cmds.text(label="Old Name")
    oldUI = cmds.textField()
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=2,columnWidth2=(90,250))
    cmds.text(label="New Name")
    newUI = cmds.textField()
    cmds.setParent("..")

    def DoReplace(*args):
        global ITEMS
        oldName = cmds.textField(oldUI,q=True,text=True).strip()
        newName = cmds.textField(newUI,q=True,text=True).strip()
        if not oldName or not newName:
            cmds.warning("Old Name / New Name cannot be empty")
            return
        replaceCount = 0

        for itemUI in list(ITEMS["order"]):
            if itemUI not in ITEMS["items"]:
                continue
            item = ITEMS["items"][itemUI]
            driverAttr = cmds.textField(item["driverAttr"],q=True,text=True).strip()
            if "." in driverAttr:
                obj, attr = driverAttr.rsplit(".", 1)
                if obj == oldName:
                    driverAttr = newName + "." + attr
                    cmds.textField(item["driverAttr"],e=True,text=driverAttr)
                    cmds.frameLayout(itemUI,e=True,label=driverAttr)
                    replaceCount += 1

            # New 2D Driver 1
            extraDriver = cmds.textField(item["driverAttr1"], q=True, text=True).strip()
            if "." in extraDriver:
                extraObj, extraAttr = extraDriver.rsplit(".", 1)
                if extraObj == oldName:
                    cmds.textField(item["driverAttr1"], e=True,
                                   text=newName + "." + extraAttr)
                    replaceCount += 1

            # --------------------------------
            # Driven Attrs
            # --------------------------------
            drivenAttrs = cmds.scrollField(item["drivenAttrs"],q=True,text=True).splitlines()
            newDrivenAttrs = []
            for drivenAttr in drivenAttrs:
                drivenAttr = drivenAttr.strip()
                if "." not in drivenAttr:
                    if drivenAttr:
                        newDrivenAttrs.append(drivenAttr)
                    continue
                obj, attr = drivenAttr.rsplit(".", 1)
                if obj == oldName:
                    obj = newName
                    replaceCount += 1
                newDrivenAttrs.append(obj + "." + attr)
            cmds.scrollField(item["drivenAttrs"],e=True,text="\n".join(newDrivenAttrs))

            # --------------------------------
            # Key Values
            # --------------------------------
            for keyUI in item["keyUI"]:
                drivenValues = keyUI["drivenValues"]
                if oldName not in drivenValues:
                    continue
                oldAttrUIs = drivenValues[oldName]
                # Nếu newName đã có sẵn
                if newName not in drivenValues:
                    drivenValues[newName] = {}
                for attr, valueUI in oldAttrUIs.items():
                    drivenValues[newName][attr] = valueUI
                del drivenValues[oldName]
                # --------------------------------
                # Update Object UI mapping
                # --------------------------------
                objectUIs = keyUI.get("drivenObjectUIs",{})
                if oldName in objectUIs:
                    objUI = objectUIs[oldName]
                    objectUIs[newName] = objUI
                    del objectUIs[oldName]

                    # tìm text label đầu tiên trong object block
                    children = cmds.layout(objUI,q=True,ca=True) or []
                    for child in children:
                        if cmds.objectTypeUI(child) == "text":
                            cmds.text(child,e=True,label="  " + newName)
                            break
                replaceCount += 1
        if cmds.window(win, exists=True):
            cmds.deleteUI(win)
        cmds.warning("Replace Object Done : {} -> {} | Changed : {}".format(oldName,newName,replaceCount))

    cmds.rowLayout(numberOfColumns=2,columnWidth2=(175,175))
    cmds.button(label="Replace",c=DoReplace)
    cmds.button(label="Cancel",c=lambda *x: cmds.deleteUI(win))
    cmds.setParent("..")
    cmds.showWindow(win)

def _pattern_data_path(data):
    item = NLTA_General.JsonGetByID({"path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"), "id": data["id"]})
    return os.path.normpath(item["path"])


def BuildSDK2D(datas):
    """Build the original single- and dual-driver SDK pose rig."""
    if not datas:
        return

    for itemIndex, itemData in enumerate(datas):
        driverAttr = itemData["driverAttr"]  # Existing input = Driver 2
        driverAttr1 = itemData.get("driverAttr1", "").strip()  # New input = Driver 1

        if driverAttr1 and not cmds.objExists(driverAttr1):
            cmds.warning("Driver 1 attr not found : {}".format(driverAttr1))
            continue
        if driverAttr1 and driverAttr1 == driverAttr:
            cmds.warning("Driver 1 and Driver 2 must be different")
            continue
        if driverAttr1 and any("driverValue1" not in x for x in itemData["keyData"]):
            cmds.warning("Missing driverValue1. Please save 2D poses again.")
            continue

        if not cmds.objExists(driverAttr):
            cmds.warning("Driver attr not found : {}".format(driverAttr))
            continue

        drivenObjects = set()
        for keyData in itemData["keyData"]:
            drivenObjects.update(keyData["drivenValues"].keys())

        sdkDict = {}

        # =========================================================
        # CREATE SDK STRUCTURE
        # =========================================================
        for obj in drivenObjects:
            if not cmds.objExists(obj):
                cmds.warning("Driven object not found : {}".format(obj))
                continue

            originalParent = cmds.listRelatives(obj, parent=True)
            originalParent = originalParent[0] if originalParent else None

            sdkGrp = obj + "_SDKGrp"
            containGrp = obj + "_SDKGrpContain"
            neutralGrp = obj + "_SDKNeutralGrp"

            # -----------------------------------------------------
            # SDK GROUP
            # -----------------------------------------------------
            if not cmds.objExists(sdkGrp):
                sdkGrp = cmds.group(em=True, n=sdkGrp)
                cmds.delete(cmds.parentConstraint(obj, sdkGrp, mo=False))
                cmds.delete(cmds.scaleConstraint(obj, sdkGrp, mo=False))

            # -----------------------------------------------------
            # CONTAIN GROUP
            # -----------------------------------------------------
            if not cmds.objExists(containGrp):
                containGrp = cmds.group(em=True, n=containGrp)
                cmds.delete(cmds.parentConstraint(obj, containGrp, mo=False))
                cmds.delete(cmds.scaleConstraint(obj, containGrp, mo=False))

            # -----------------------------------------------------
            # NEUTRAL GROUP
            # -----------------------------------------------------
            if not cmds.objExists(neutralGrp):
                neutralGrp = cmds.group(em=True, n=neutralGrp)
                cmds.delete(cmds.parentConstraint(obj, neutralGrp, mo=False))
                cmds.delete(cmds.scaleConstraint(obj, neutralGrp, mo=False))

            # -----------------------------------------------------
            # Parent helper groups
            # -----------------------------------------------------
            if originalParent:
                for grp in [sdkGrp, containGrp, neutralGrp]:
                    parent = cmds.listRelatives(grp, parent=True)

                    if not parent:
                        cmds.parent(grp, originalParent)

            # -----------------------------------------------------
            # Put driven object inside contain
            # -----------------------------------------------------
            currentParent = cmds.listRelatives(obj, parent=True)

            if not currentParent or currentParent[0] != containGrp:
                cmds.parent(obj, containGrp)



            # =====================================================
            # SDK ENABLE / SWITCH ATTRIBUTE
            # =====================================================
            switchAttr = itemData.get("switchAttr", "").strip()
            if switchAttr:
                sdkEnable = switchAttr
            else:
                sdkEnable = "SDK_Enable"
            if not cmds.attributeQuery(sdkEnable, node=obj, exists=True):
                cmds.addAttr(
                    obj,
                    ln=sdkEnable,
                    at="double",
                    min=0,
                    max=1,
                    dv=1,
                    keyable=True
                )

            sdkEnable = obj + "." + sdkEnable

            # =====================================================
            # REVERSE
            # =====================================================
            reverseNode = obj + "_SDK_Enable_REV"

            if not cmds.objExists(reverseNode):
                reverseNode = cmds.createNode(
                    "reverse",
                    n=reverseNode
                )

            if not cmds.isConnected(
                sdkEnable,
                reverseNode + ".inputX"
            ):
                cmds.connectAttr(
                    sdkEnable,
                    reverseNode + ".inputX",
                    f=True
                )

            # =====================================================
            # PARENT CONSTRAINT
            # translate + rotate
            # =====================================================
            parentConstraints = cmds.listConnections(
                containGrp,
                s=True,
                d=False,
                type="parentConstraint"
            ) or []

            if parentConstraints:
                parentConstraint = parentConstraints[0]

            else:
                parentConstraint = cmds.parentConstraint(
                    neutralGrp,
                    sdkGrp,
                    containGrp,
                    mo=False,
                    n=containGrp + "_parentConstraint"
                )[0]

            parentAliases = cmds.parentConstraint(
                parentConstraint,
                q=True,
                wal=True
            )

            # Neutral
            cmds.connectAttr(
                reverseNode + ".outputX",
                parentConstraint + "." + parentAliases[0],
                f=True
            )

            # SDK
            cmds.connectAttr(
                sdkEnable,
                parentConstraint + "." + parentAliases[1],
                f=True
            )

            # =====================================================
            # SCALE CONSTRAINT
            # =====================================================
            scaleConstraints = cmds.listConnections(
                containGrp,
                s=True,
                d=False,
                type="scaleConstraint"
            ) or []

            if scaleConstraints:
                scaleConstraint = scaleConstraints[0]

            else:
                scaleConstraint = cmds.scaleConstraint(
                    neutralGrp,
                    sdkGrp,
                    containGrp,
                    mo=False,
                    n=containGrp + "_scaleConstraint"
                )[0]

            scaleAliases = cmds.scaleConstraint(
                scaleConstraint,
                q=True,
                wal=True
            )

            # Neutral
            cmds.connectAttr(
                reverseNode + ".outputX",
                scaleConstraint + "." + scaleAliases[0],
                f=True
            )

            # SDK
            cmds.connectAttr(
                sdkEnable,
                scaleConstraint + "." + scaleAliases[1],
                f=True
            )

            sdkDict[obj] = sdkGrp

        # =========================================================
        # CONDITIONAL + ORDERED SMOOTH BLEND
        # Driver 1 (Hip) selects/blends neighbouring Knee SDK curves.
        # Driver 2 (Knee) drives the actual 1D SDK curves.
        # Numeric sorting makes JSON/UI key order irrelevant.
        # Every stored Hip level reproduces its Knee SDK exactly.
        # =========================================================
        if driverAttr1:
            groups = {}
            try:
                seen = set()
                orderedKeys = sorted(
                    itemData["keyData"],
                    key=lambda k: (
                        float(k["driverValue1"]),
                        float(k["driverValue"])
                    )
                )
                for keyData in orderedKeys:
                    hipValue = float(keyData["driverValue1"])
                    kneeValue = float(keyData["driverValue"])
                    pair = (hipValue, kneeValue)
                    if pair in seen:
                        raise ValueError("Duplicate Driver 1/2 pair: {}".format(pair))
                    seen.add(pair)

                    channels = {}
                    for obj, attrDict in keyData["drivenValues"].items():
                        if obj not in sdkDict:
                            continue
                        for attr, value in attrDict.items():
                            channels[(obj, attr)] = float(value)
                    groups.setdefault(hipValue, {})[kneeValue] = channels

                # Each driven channel must have a value at each stored pose.
                channelSet = set()
                for group in groups.values():
                    for channelValues in group.values():
                        channelSet.update(channelValues)
                for hipValue, group in groups.items():
                    for kneeValue, channelValues in group.items():
                        missing = channelSet - set(channelValues)
                        if missing:
                            raise ValueError(
                                "Missing {} at (Hip={}, Knee={})".format(
                                    sorted(missing)[0], hipValue, kneeValue
                                )
                            )
            except (ValueError, KeyError, TypeError) as exc:
                cmds.warning("Conditional SDK data error: {}".format(exc))
                continue

            if not groups or not channelSet:
                continue

            # Allow other SDK items to drive the same channel.
            # Maya setDrivenKeyframe combines independent drivers via blendWeighted.

            prefix = "NLTA_SmoothGateSDK_{:03d}".format(itemIndex)
            thresholds = sorted(groups)

            # Create blend curves BETWEEN consecutive stored Hip keys.
            # Hip at the key itself always evaluates to the right pose.
            # Example: 0,20,45,65 -> gates [0,20], [20,45], [45,65].
            hipWeights = {}
            for i in range(1, len(thresholds)):
                low = thresholds[i-1]
                high = thresholds[i]
                weightHolder = cmds.createNode(
                    "network", n=prefix + "_HipWeight{:02d}".format(i)
                )
                cmds.addAttr(
                    weightHolder, ln="weight", at="double", keyable=True
                )
                weightPlug = weightHolder + ".weight"
                cmds.setDrivenKeyframe(
                    weightPlug,
                    currentDriver=driverAttr1,
                    driverValue=low,
                    value=0.0
                )
                cmds.setDrivenKeyframe(
                    weightPlug,
                    currentDriver=driverAttr1,
                    driverValue=high,
                    value=1.0
                )
                cmds.keyTangent(weightPlug, itt="flat", ott="flat")
                hipWeights[i] = weightPlug

            # Keep the requirement Hip >= first stored threshold.
            # Maya SDK converts angle units correctly before comparison.
            hipReader = cmds.createNode(
                "network", n=prefix + "_HipReader"
            )
            cmds.addAttr(hipReader, ln="value", at="double", keyable=True)
            hipReaderPlug = hipReader + ".value"
            margin = max(1.0, (thresholds[-1] - thresholds[0]) * 0.1)
            for hipSample in (
                thresholds[0] - margin,
                thresholds[-1] + margin
            ):
                cmds.setDrivenKeyframe(
                    hipReaderPlug,
                    currentDriver=driverAttr1,
                    driverValue=hipSample,
                    value=hipSample
                )
            cmds.keyTangent(hipReaderPlug, itt="linear", ott="linear")

            for channelIndex, (obj, attr) in enumerate(sorted(channelSet)):
                sdkGrp = sdkDict[obj]
                sdkAttr = sdkGrp + "." + attr
                if not cmds.attributeQuery(attr, node=sdkGrp, exists=True):
                    cmds.addAttr(
                        sdkGrp, ln=attr, at="double", keyable=True
                    )

                # Constant-zero channels do not need SDK curves/blend nodes.
                # Keep the original zero output on the SDK group.
                if all(
                    abs(values[(obj, attr)]) < 1e-10
                    for hipGroup in groups.values()
                    for values in hipGroup.values()
                ):
                    # Do not overwrite an SDK already connected by another item.
                    if not cmds.listConnections(
                        sdkAttr, s=True, d=False, p=True
                    ):
                        cmds.setAttr(sdkAttr, 0.0)
                    continue

                selectedPlug = None
                allValues = [0.0]

                for index, hip in enumerate(thresholds):
                    # One ordinary 1D Knee SDK at this Hip level.
                    holder = cmds.createNode(
                        "network",
                        n=prefix + "_Channel{:02d}_Hip{:02d}_KneeSDK".format(
                            channelIndex, index
                        )
                    )
                    cmds.addAttr(holder, ln="value", at="double", keyable=True)
                    curvePlug = holder + ".value"

                    kneeKeys = {
                        knee: channelValues[(obj, attr)]
                        for knee, channelValues in groups[hip].items()
                    }
                    # Keep neutral when Knee is at zero unless
                    # the user specifically provided a Knee=0 pose.
                    if 0.0 not in kneeKeys:
                        kneeKeys[0.0] = 0.0

                    for knee in sorted(kneeKeys):
                        cmds.setDrivenKeyframe(
                            curvePlug,
                            currentDriver=driverAttr,
                            driverValue=knee,
                            value=kneeKeys[knee]
                        )
                        allValues.append(kneeKeys[knee])

                    # Smooth Knee curve between keys; unlike a stepped
                    # condition, rotation updates continuously.
                    cmds.keyTangent(
                        curvePlug, itt="clamped", ott="clamped"
                    )

                    # The first Hip curve is our base. For every
                    # subsequent Hip level, smoothly blend in its Knee
                    # curve between the previous and current Hip keys.
                    if selectedPlug is None:
                        selectedPlug = curvePlug
                        continue

                    blend = cmds.createNode(
                        "blendColors",
                        n=prefix + "_Channel{:02d}_Hip{:02d}_Blend".format(
                            channelIndex, index
                        )
                    )
                    cmds.connectAttr(curvePlug, blend + ".color1R")
                    cmds.connectAttr(selectedPlug, blend + ".color2R")
                    cmds.connectAttr(
                        hipWeights[index], blend + ".blender"
                    )
                    selectedPlug = blend + ".outputR"

                # Hip is a prerequisite: below the first stored Hip
                # value, do not enable the Knee output.
                gate = cmds.createNode(
                    "condition",
                    n=prefix + "_Channel{:02d}_HipGate".format(
                        channelIndex
                    )
                )
                cmds.setAttr(gate + ".operation", 3) # greater or equal
                cmds.connectAttr(hipReaderPlug, gate + ".firstTerm")
                cmds.setAttr(gate + ".secondTerm", thresholds[0])
                cmds.connectAttr(selectedPlug, gate + ".colorIfTrueR")
                cmds.setAttr(gate + ".colorIfFalseR", 0.0)
                selectedPlug = gate + ".outColorR"

                # Convert the unitless blend output back into a
                # transform angle/translate plug, as in the old Run.
                # Two linear identity SDK keys preserve the value.
                lo = min(allValues) - 1.0
                hi = max(allValues) + 1.0
                for value in (lo, hi):
                    cmds.setDrivenKeyframe(
                        sdkAttr,
                        currentDriver=selectedPlug,
                        driverValue=value,
                        value=value
                    )
                cmds.keyTangent(sdkAttr, itt="linear", ott="linear")

            continue

        # =========================================================
        # CREATE SDK KEYS - ORIGINAL 1D MODE
        # =========================================================
        for keyData in itemData["keyData"]:
            driverValue = float(keyData["driverValue"])

            for obj, attrData in keyData["drivenValues"].items():

                if obj not in sdkDict:
                    continue

                sdkGrp = sdkDict[obj]

                for attr, value in attrData.items():

                    sdkAttr = "{}.{}".format(
                        sdkGrp,
                        attr
                    )

                    if not cmds.attributeQuery(
                        attr,
                        node=sdkGrp,
                        exists=True
                    ):
                        cmds.addAttr(
                            sdkGrp,
                            ln=attr,
                            at="double",
                            keyable=True
                        )

                    cmds.setDrivenKeyframe(
                        sdkAttr,
                        currentDriver=driverAttr,
                        driverValue=driverValue,
                        value=float(value)
                    )

                    cmds.keyTangent(
                        sdkAttr,
                        itt="linear",
                        ott="linear"
                    )


def Run(data, *args):
    return BuildSDK2D(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("SDK_2D Export: no saved items")
        return None

    # Export the exact live Run builder, excluding only diagnostic warnings.
    tree = ast.parse(inspect.getsource(BuildSDK2D))

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
    lines = ast.unparse(tree).splitlines()
    comments = (
        ("    for itemIndex, itemData in enumerate(datas):", "# Process saved one- or two-driver poses."),
        ("        drivenObjects = set()", "# Create the original neutral and SDK helper groups."),
        ("        if driverAttr1:", "# Blend the ordered Driver 1 levels with Driver 2 SDK curves."),
        ("            groups = {}", "# Check duplicate pose coordinates and missing channel values."),
        ("            hipWeights = {}", "# Interpolate smoothly between successive Driver 1 levels."),
        ("            for channelIndex, (obj, attr) in enumerate(sorted(channelSet)):", "# Build gated SDK outputs for each affected channel."),
        ("        for keyData in itemData['keyData']:", "# Preserve the original one-driver SDK behavior."),
    )
    for anchor, comment in comments:
        for index, line in enumerate(lines):
            if line.lstrip().startswith(anchor.strip()):
                indent = line[:len(line) - len(line.lstrip())]
                lines.insert(index, indent + comment)
                break
    source = "\n".join("    " + line if line.strip() else "" for line in lines)
    data_text = "[\n" + ",\n".join("        " + repr(item) for item in records) + "\n    ]"
    script = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # SDK_2D data\n"
        "    SDK_DATA = " + data_text + "\n\n"
        + source
        + "\n\n    # Recreate the saved one- and two-driver SDK rig.\n"
        + "    BuildSDK2D(SDK_DATA)\n\n"
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

    def RemoveSelectedDriven(itemUI, *args):
        global ITEMS

        sel = cmds.ls(sl=True, long=True) or []

        if not sel:
            result = cmds.promptDialog(
                title="Remove Driven Object",
                message="Object Name:",
                button=["Remove", "Cancel"],
                defaultButton="Remove",
                cancelButton="Cancel",
                dismissString="Cancel"
            )

            if result != "Remove":
                return

            objName = cmds.promptDialog(q=True, text=True).strip()

            if not objName:
                return

            sel = [objName]

        item = ITEMS["items"][itemUI]

        selectedNames = set()
        for obj in sel:
            selectedNames.add(obj)
            selectedNames.add(obj.split("|")[-1])

        # -----------------------------
        # Remove khỏi Driven Attrs
        # -----------------------------
        drivenAttrs = cmds.scrollField(
            item["drivenAttrs"],
            q=True,
            text=True
        ).splitlines()

        keepAttrs = []

        for drivenAttr in drivenAttrs:
            drivenAttr = drivenAttr.strip()

            if "." not in drivenAttr:
                if drivenAttr:
                    keepAttrs.append(drivenAttr)
                continue

            obj, attr = drivenAttr.rsplit(".", 1)
            shortObj = obj.split("|")[-1]

            if obj in selectedNames or shortObj in selectedNames:
                continue

            keepAttrs.append(drivenAttr)

        cmds.scrollField(
            item["drivenAttrs"],
            e=True,
            text="\n".join(keepAttrs)
        )

        # -----------------------------
        # Remove khỏi tất cả Values
        # -----------------------------
        for keyUI in list(item["keyUI"]):
            for obj in list(keyUI["drivenValues"].keys()):
                shortObj = obj.split("|")[-1]
                if obj not in selectedNames and shortObj not in selectedNames:
                    continue
                objectUI = keyUI.get(
                    "drivenObjectUIs", {}
                ).get(obj)

                if objectUI and cmds.layout(objectUI, exists=True):
                    cmds.deleteUI(objectUI)

                del keyUI["drivenValues"][obj]

                if obj in keyUI.get("drivenObjectUIs", {}):
                    del keyUI["drivenObjectUIs"][obj]

            if not keyUI["drivenValues"]:
                keyName = keyUI["keyName"]
                if cmds.layout(keyName, exists=True):
                    cmds.deleteUI(keyName)
                item["keyUI"].remove(keyUI)
            for obj in list(keyUI["drivenValues"].keys()):
                shortObj = obj.split("|")[-1]
                if obj not in selectedNames and shortObj not in selectedNames:
                    continue
                objectUI = keyUI.get( "drivenObjectUIs", {}).get(obj)
                if objectUI:
                    if cmds.layout(objectUI, exists=True):
                        cmds.deleteUI(objectUI)
                del keyUI["drivenValues"][obj]
                if obj in keyUI.get("drivenObjectUIs", {}):
                    del keyUI["drivenObjectUIs"][obj]

        cmds.warning(
            "Removed Driven Object : {}".format(
                ", ".join([x.split("|")[-1] for x in sel])
            )
        )

    def FindMirrorItem(itemUI):
        global ITEMS

        driverAttr = cmds.textField(
            ITEMS["items"][itemUI]["driverAttr"],
            q=True,
            text=True
        ).strip()

        if "." not in driverAttr:
            return None

        obj, attr = driverAttr.rsplit(".", 1)
        mirrorObj = NLTA_General.GetMirrorName(obj)
        mirrorAttr = mirrorObj + "." + attr
        extraDriver = cmds.textField(ITEMS["items"][itemUI]["driverAttr1"],
                                     q=True, text=True).strip()
        mirrorExtra = ""
        if "." in extraDriver:
            extraObj, extraAttr = extraDriver.rsplit(".", 1)
            mirrorExtra = NLTA_General.GetMirrorName(extraObj) + "." + extraAttr

        for otherUI in ITEMS["order"]:

            if otherUI == itemUI:
                continue

            otherDriver = cmds.textField(
                ITEMS["items"][otherUI]["driverAttr"],
                q=True,
                text=True
            ).strip()

            otherExtra = cmds.textField(ITEMS["items"][otherUI]["driverAttr1"],
                                         q=True, text=True).strip()
            if otherDriver == mirrorAttr and otherExtra == mirrorExtra:
                return otherUI

        return None

    def CompareMirror(itemUI, *args):
        global ITEMS

        mirrorUI = FindMirrorItem(itemUI)

        if not mirrorUI:
            cmds.warning("Mirror Item not found")
            return

        leftData = GetItemData(itemUI)
        rightData = GetItemData(mirrorUI)

        win = "SDKCompareWindow"

        if cmds.window(win, exists=True):
            cmds.deleteUI(win)

        cmds.window(
            win,
            title="SDK Mirror Compare",
            widthHeight=(900,700),
            sizeable=True
        )

        cmds.paneLayout(configuration="vertical2")

        BuildCompareSide(leftData)
        BuildCompareSide(rightData)

        cmds.showWindow(win)
    
    def BuildCompareSide(data):
        cmds.scrollLayout(
            horizontalScrollBarThickness=8
        )

        cmds.columnLayout(
            adjustableColumn=True
        )

        # --------------------------------
        # Driver
        # --------------------------------
        cmds.text(
            label=data.get("driverAttr1", "") + " | " + data["driverAttr"],
            height=35,
            font="boldLabelFont",
            align="left"
        )

        # --------------------------------
        # Driven Attrs
        # --------------------------------
        cmds.text(
            label="Driven Attrs",
            align="left"
        )

        cmds.scrollField(
            text=data["drivenAttrs"],
            editable=False,
            height=100
        )

        # --------------------------------
        # Values
        # --------------------------------
        for keyData in data["keyData"]:

            cmds.frameLayout(
                label="Value 1: {} | Value 2: {}".format(
                    keyData.get("driverValue1", "0"), keyData["driverValue"]
                ),
                collapsable=False,
                collapse=False
            )

            cmds.columnLayout(
                adjustableColumn=True
            )

            for obj, attrs in keyData["drivenValues"].items():

                cmds.text(
                    label=obj,
                    align="left",
                    font="boldLabelFont",
                    height=25
                )

                # -------------------------
                # 3 attrs / row
                # -------------------------
                attrItems = list(attrs.items())

                for i in range(0, len(attrItems), 3):

                    row = attrItems[i:i+3]

                    cmds.rowLayout(
                        numberOfColumns=3,
                        adjustableColumn=3
                    )

                    for attr, value in row:

                        cmds.rowLayout(
                            numberOfColumns=2,
                            columnWidth2=(25, 70)
                        )

                        cmds.text(
                            label=attr,
                            width=25,
                            align="left"
                        )

                        cmds.textField(
                            text=str(value),
                            editable=False,
                            width=70
                        )

                        cmds.setParent("..")

                    cmds.setParent("..")

            cmds.setParent("..")
            cmds.setParent("..")

        cmds.setParent("..")
        cmds.setParent("..")



    def AddKeyItem(itemUI,data,listKey,*arr):
        global ITEMS

        def DeleteKeyItem(itemUI, keyName, *args):
            global ITEMS
            cmds.deleteUI(keyName)
            ITEMS["items"][itemUI]["keyUI"] = [
                x for x in ITEMS["items"][itemUI]["keyUI"]
                if x["keyName"] != keyName
            ]
        def GetDirectValue(itemUI, obj, attrData, attrUIs, *args):
            for attr, ui in attrUIs.items():
                fullAttr = obj + "." + attr
                if not cmds.objExists(fullAttr):
                    continue
                try:
                    value = cmds.getAttr(fullAttr)
                    cmds.textField(ui, e=True, text=str(value))
                except:
                    pass

        def GetSelectedDrivenValue(attrUIs,*args):
            sel = cmds.ls(sl=True)
            if not sel:
                return
            obj = sel[0]
            for attr,valueUI in attrUIs.items():
                fullAttr = obj+"."+attr
                if not cmds.objExists(fullAttr):
                    continue
                try:
                    value = cmds.getAttr(fullAttr)
                    cmds.textField(valueUI,e=True,text=str(value))
                except:
                    pass

        def GetValue(itemUI, keyName, *args):
            global ITEMS
            item = ITEMS["items"][itemUI]
            for keyUI in item["keyUI"]:
                if keyUI["keyName"] != keyName:
                    continue
                for obj, attrDict in keyUI["drivenValues"].items():
                    for attr, ui in attrDict.items():
                        drivenAttr = obj + "." + attr
                        if cmds.objExists(drivenAttr):
                            value = cmds.getAttr(drivenAttr)
                            cmds.textField(ui, e=True, text=str(value))
                break

        if data == {}:
            driver1 = cmds.textField(ITEMS["items"][itemUI]["driverAttr1"],
                                     q=True, text=True).strip()
            keyData = {
                "driverValue":cmds.getAttr(cmds.textField(ITEMS["items"][itemUI]["driverAttr"],q=True,text=True)),
                "driverValue1":cmds.getAttr(driver1) if driver1 else 0.0,
                "drivenValues":{}
            }
            drivenAttrs = cmds.scrollField(ITEMS["items"][itemUI]["drivenAttrs"],q=True,text=True).split("\n")
            for drivenAttr in drivenAttrs:
                if "." not in drivenAttr:
                    continue
                obj,attr = drivenAttr.rsplit(".",1)
                if obj not in keyData["drivenValues"]:
                    keyData["drivenValues"][obj] = {}
                keyData["drivenValues"][obj][attr] = cmds.getAttr(drivenAttr)
        else:
            keyData = data

        keyUI = {} 
        keyUI["keyName"] = cmds.frameLayout(
            label="{} | {}".format(keyData.get("driverValue1", "0"), keyData["driverValue"]),
            parent=listKey,collapsable=True,collapse=True,w=360)
        cmds.rowColumnLayout(numberOfColumns=1)

        cmds.rowColumnLayout(numberOfColumns=6)
        cmds.textField(text='Value 1',editable=False,bgc=(0.216, 0.216, 0.216),w=55)
        keyUI["driverValue1"] = cmds.textField(text=str(keyData.get("driverValue1", "0")),w=65)
        cmds.textField(text='Value 2',editable=False,bgc=(0.216, 0.216, 0.216),w=55)
        keyUI["driverValue"] = cmds.textField(text=str(keyData["driverValue"]),w=65)
        cmds.button(label="X",c=partial(DeleteKeyItem,itemUI,keyUI["keyName"]),w=40)
        cmds.button(label="Get All",c=partial(GetValue,itemUI,keyUI["keyName"]),w=65)
        cmds.setParent('..')

        keyUI["drivenValues"] = {}
        keyUI["drivenObjectUIs"] = {}
        for obj,attrData in keyData["drivenValues"].items():
            objectUI = cmds.rowColumnLayout(nc=1,width=380)
            keyUI["drivenObjectUIs"][obj] = objectUI
            cmds.text(label="  " + obj,width=380,bgc=(0.1, 0.1, 0.1),align="left",height=30)
            cmds.rowColumnLayout(numberOfColumns=2)

            cmds.rowColumnLayout(numberOfColumns=3)
            attrUIs = {}
            for attr,value in attrData.items():
                cmds.rowColumnLayout(nc=2)
                cmds.textField(text=attr,editable=False,w=25)
                valueUI = cmds.textField(text=str(value),w=50)
                attrUIs[attr] = valueUI
                cmds.setParent("..")            
            cmds.setParent("..")

            cmds.rowColumnLayout(numberOfColumns=2)
            cmds.button(label="Name",c=partial(GetDirectValue, itemUI, obj, attrData, attrUIs))
            cmds.button(label="Selected",c=partial(GetSelectedDrivenValue,attrUIs))            
            cmds.setParent("..") 

            cmds.setParent("..") 
            cmds.setParent("..")

            keyUI["drivenValues"][obj] = attrUIs


        cmds.setParent('..')
        cmds.setParent('..') 

        ITEMS["items"][itemUI]["keyUI"].append(keyUI)


    itemData = {}
    itemUI = cmds.frameLayout(label=data.get("driverAttr", ""),parent=listUI,collapsable=True,collapse=True,w=380)

    #itemUI = cmds.rowColumnLayout(numberOfColumns=1,parent=listUI,backgroundColor=(0.15, 0.15, 0.15))
    cmds.rowColumnLayout(numberOfColumns=1)

    cmds.rowColumnLayout(nc=2)

    cmds.text(label="",width=20)

    cmds.frameLayout(label="Detail",collapsable=True,collapse=True,w=380)

    cmds.rowColumnLayout( numberOfColumns=3,columnWidth=[(1,80),(2,250),(3,32)]) #--
    cmds.textField(text='Driver 1',editable=False)
    itemData['driverAttr1'] = cmds.textField(text=data.get("driverAttr1", ""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrs,itemData['driverAttr1']))

    cmds.textField(text='Driver 2',editable=False)
    itemData['driverAttr'] = cmds.textField(text=data.get("driverAttr", ""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrs,itemData['driverAttr']))
    
    cmds.textField(text='Driven Attrs',editable=False)
    itemData['drivenAttrs'] = cmds.scrollField(text=data.get("drivenAttrs", ""),height=100)
    cmds.rowColumnLayout(nc=1)
    cmds.button(label="->",w=30,c=partial(NLTA_UI.PickAttrs,itemData["drivenAttrs"]))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrsAdd,itemData["drivenAttrs"]))
    cmds.button(label="X",w=30,backgroundColor=(.5,.2,.2),c=partial(RemoveSelectedDriven,itemUI))
    cmds.setParent("..")

    cmds.textField(text='Swich Attr',editable=False)
    itemData["switchAttr"] = cmds.textField(text=data.get("switchAttr", ""))
    cmds.text("")

    
    cmds.setParent("..") #--

    cmds.rowColumnLayout(nc=3)
    addButton = cmds.button(label="Add Values",w=90)
    cmds.button(label="Create Mirror",w=90,c=partial(CreateMirror, itemUI, listUI))
    cmds.button(label="X",w=90,backgroundColor=(.5,.2,.2),c=partial(Delete,itemUI))
    cmds.button(
        label="Compare",
        w=95,
        c=partial(CompareMirror,itemUI)
    )
    cmds.setParent("..")
    


    cmds.text(label="",width=20)
    listKey = cmds.scrollLayout(horizontalScrollBarThickness=4,w=380,h=300)
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.setParent("..")    
    cmds.setParent("..")

    cmds.button(addButton,edit=True,c=partial(AddKeyItem,itemUI,{},listKey) )

    itemData["keyUI"] = []
    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)

    if data and ('keyData' in data):
        for i in range(len(data['keyData'])):
            AddKeyItem(itemUI,data['keyData'][i],listKey)
