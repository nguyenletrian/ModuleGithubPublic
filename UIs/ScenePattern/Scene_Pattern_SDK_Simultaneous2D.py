import os
import importlib
import inspect
import ast
import math
import re
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
    name = "SDK Simultaneous 2D"
    return({
        "ext":ext,
        "path":os.path.join(path, moduleName + "_" + datetime.now().strftime("%Y%m%d%H%M%S%f") + ".json"),
        "moduleName":moduleName,
        "order":0,
        "title":name,
        "name":name,
        "id":datetime.now().strftime("%Y%m%d%H%M%S%f")
    })


def Load(data,listUI,*arr):
    global ITEMS
    ITEMS["items"].clear()
    ITEMS["order"][:] = []
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
    cmds.button(label="Run",width=100,c=lambda *_: (Save(data), Run(data)))
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


def _sim2d_preflight(datas):
    """Validate sparse X/Y samples before making any Maya scene changes.

    Driver X samples may differ between Y levels. Each captured coordinate
    remains an exact SDK key; absent coordinates are evaluated by the nearest
    saved X keys of that Y row (clamped beyond the row's endpoints).
    driverAttr1/driverValue1 = X; driverAttr/driverValue = Y.
    Saved Driven values are LOCAL TRS values, not additive rotations.
    """
    plans = []
    used_objects = set()
    if not isinstance(datas, list) or not datas:
        raise ValueError("Simultaneous 2D SDK: No saved pose records")

    for item_index, item in enumerate(datas):
        x_attr = str(item.get("driverAttr1") or "").strip()
        y_attr = str(item.get("driverAttr") or "").strip()
        if not x_attr or not y_attr or x_attr == y_attr:
            raise ValueError("Simultaneous 2D SDK: Select TWO different Driver attributes (X and Y)")
        for plug in (x_attr, y_attr):
            if not cmds.objExists(plug):
                raise ValueError("Simultaneous 2D SDK: Driver not found: " + plug)
            try:
                float(cmds.getAttr(plug))
            except (TypeError, ValueError, RuntimeError):
                raise ValueError("Simultaneous 2D SDK: Driver must be a numeric scalar: " + plug)

        keys = item.get("keyData") or []
        grid = {}
        channels = set()
        for key in keys:
            try:
                x = float(key["driverValue1"])
                y = float(key["driverValue"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("Simultaneous 2D SDK: Every pose requires numeric X/Y values")
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Simultaneous 2D SDK: Driver angles must be finite")
            pair = (x, y)
            if pair in grid:
                raise ValueError("Simultaneous 2D SDK: Duplicate pose X={}, Y={}".format(x, y))
            values = {}
            for obj, attrs in (key.get("drivenValues") or {}).items():
                if not isinstance(attrs, dict):
                    raise ValueError("Simultaneous 2D SDK: Invalid Driven channels for " + obj)
                for attr, raw in attrs.items():
                    if attr not in ("tx", "ty", "tz", "rx", "ry", "rz"):
                        raise ValueError("Simultaneous 2D SDK: Unsupported Driven channel: " + obj + "." + attr)
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        raise ValueError("Simultaneous 2D SDK: Invalid value for " + obj + "." + attr)
                    if not math.isfinite(value):
                        raise ValueError("Simultaneous 2D SDK: Non-finite Driven value")
                    values[(obj, attr)] = value
                    channels.add((obj, attr))
            if not values:
                raise ValueError("Simultaneous 2D SDK: Pose ({}, {}) has no Driven values".format(x, y))
            grid[pair] = values

        xs = sorted(set(x for x, _ in grid))
        ys = sorted(set(y for _, y in grid))
        if len(xs) < 2 or len(ys) < 2:
            raise ValueError("Simultaneous 2D SDK: Save at least TWO X levels and TWO Y levels")
        # No full Cartesian grid is required. Use the available X positions
        # independently at each Y level; this allows sparse pose layouts.
        row_xs = {y: sorted(x for x, yy in grid if yy == y) for y in ys}
        if (0.0, 0.0) not in grid:
            raise ValueError("Simultaneous 2D SDK: Capture Neutral at X=0, Y=0 first")
        for pair, sample in grid.items():
            missing = channels - set(sample)
            if missing:
                obj, attr = sorted(missing)[0]
                raise ValueError("Simultaneous 2D SDK: Missing {}.{} at X={}, Y={}".format(
                    obj, attr, pair[0], pair[1]))

        if abs(float(cmds.getAttr(x_attr))) > 0.001 or abs(float(cmds.getAttr(y_attr))) > 0.001:
            raise ValueError("Simultaneous 2D SDK: Return BOTH Drivers to X=0, Y=0 before Run")

        switch = str(item.get("switchAttr") or "SDK2D_Enable").strip()
        if not re.match(r"^[a-zA-Z_][a-zA-Z_0-9]*$", switch):
            raise ValueError("Simultaneous 2D SDK: Switch Attr must be a local attribute name")
        objects = sorted(set(obj for obj, attr in channels))
        for obj in objects:
            if obj in used_objects:
                raise ValueError("Simultaneous 2D SDK: A Driven object may only appear once per build: " + obj)
            used_objects.add(obj)
            if not cmds.objExists(obj) or cmds.nodeType(obj) != "transform":
                raise ValueError("Simultaneous 2D SDK: Driven must be an existing transform control: " + obj)
            if obj == x_attr.rsplit(".", 1)[0] or obj == y_attr.rsplit(".", 1)[0]:
                raise ValueError("Simultaneous 2D SDK: Driver cannot also be a Driven control")
            for other in objects:
                if obj != other and other.startswith(obj + "|"):
                    raise ValueError("Simultaneous 2D SDK: Nested Driven controls not supported: " + obj)
            for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
                plug = obj + "." + attr
                if not cmds.objExists(plug):
                    raise ValueError("Simultaneous 2D SDK: Missing Driven channel: " + plug)
            for obj2, attr in channels:
                if obj2 != obj:
                    continue
                plug = obj + "." + attr
                if abs(float(cmds.getAttr(plug)) - grid[(0.0, 0.0)][(obj, attr)]) > 0.001:
                    raise ValueError("Simultaneous 2D SDK: Return Driven to saved Neutral: " + plug)
            if cmds.attributeQuery(switch, node=obj, exists=True):
                raise ValueError("Simultaneous 2D SDK: Switch attribute already exists on " + obj +
                                 ". Use a clean scene or another switch name.")

        name_prefixes = {}
        for obj_index, obj in enumerate(objects):
            clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", obj.rsplit("|", 1)[-1])[:25]
            prefix = "NLTA_Sim2D_{:03d}_{:03d}_{}".format(item_index, obj_index, clean_name)
            name_prefixes[obj] = prefix
            for suffix in ("_SDKGrp", "_NeutralGrp", "_ContainGrp", "_REV",
                           "_ParentCns", "_ScaleCns"):
                if cmds.objExists(prefix + suffix):
                    raise ValueError("Simultaneous 2D SDK: Rig already exists: " + prefix + suffix)

        plans.append(dict(x_attr=x_attr, y_attr=y_attr, xs=xs, ys=ys,
                          row_xs=row_xs, grid=grid,
                          channels=sorted(channels), objects=objects,
                          prefixes=name_prefixes, switch=switch))
    return plans


def _sim2d_build_one(plan):
    """Create SDK-style neutral/pose/contain groups and simultaneous X/Y curves."""
    x_attr, y_attr = plan["x_attr"], plan["y_attr"]
    grid, ys, row_xs = plan["grid"], plan["ys"], plan["row_xs"]
    groups = {}

    # SDK groups are siblings. This preserves the SDK Neutral/Enable workflow
    # while avoiding connections to the Driven control's existing TRS channels.
    for obj in plan["objects"]:
        prefix = plan["prefixes"][obj]
        parent = (cmds.listRelatives(obj, parent=True, fullPath=True) or [None])[0]
        original_matrix = cmds.xform(obj, query=True, worldSpace=True, matrix=True)
        sdk = cmds.group(empty=True, name=prefix + "_SDKGrp")
        neutral = cmds.group(empty=True, name=prefix + "_NeutralGrp")
        contain = cmds.group(empty=True, name=prefix + "_ContainGrp")
        for helper in (sdk, neutral, contain):
            temp = cmds.parentConstraint(obj, helper, maintainOffset=False)
            cmds.delete(temp)
            temp = cmds.scaleConstraint(obj, helper, maintainOffset=False)
            cmds.delete(temp)
            # Use absolute parenting to preserve the helpers' world transforms.
            if parent:
                cmds.parent(helper, parent, absolute=True)

        # Maya changes a full DAG path when a control is reparented.
        # Rebind the control before adding the switch or querying matrices.
        parented = cmds.parent(obj, contain, absolute=True)
        new_obj = (cmds.ls(parented[0], long=True) or parented)[0]
        if not cmds.attributeQuery(plan["switch"], node=new_obj, exists=True):
            cmds.addAttr(new_obj, longName=plan["switch"], attributeType="double",
                         min=0, max=1, defaultValue=1, keyable=True)
        enable = new_obj + "." + plan["switch"]
        reverse = cmds.createNode("reverse", name=prefix + "_REV")
        cmds.connectAttr(enable, reverse + ".inputX")
        parent_constraint = cmds.parentConstraint(neutral, sdk, contain,
                                                  maintainOffset=False,
                                                  name=prefix + "_ParentCns")[0]
        weight_aliases = cmds.parentConstraint(parent_constraint, query=True, weightAliasList=True)
        cmds.connectAttr(reverse + ".outputX", parent_constraint + "." + weight_aliases[0])
        cmds.connectAttr(enable, parent_constraint + "." + weight_aliases[1])

        scale_constraint = cmds.scaleConstraint(neutral, sdk, contain,
                                               maintainOffset=False,
                                               name=prefix + "_ScaleCns")[0]
        scale_aliases = cmds.scaleConstraint(scale_constraint, query=True, weightAliasList=True)
        cmds.connectAttr(reverse + ".outputX", scale_constraint + "." + scale_aliases[0])
        cmds.connectAttr(enable, scale_constraint + "." + scale_aliases[1])
        groups[obj] = sdk

        result_matrix = cmds.xform(new_obj, query=True, worldSpace=True, matrix=True)
        if max(abs(float(a) - float(b)) for a, b in zip(original_matrix, result_matrix)) > 1e-4:
            raise RuntimeError("Simultaneous 2D SDK: Transform changed during group insertion: " + obj)

    for channel_index, (obj, attr) in enumerate(plan["channels"]):
        prefix = plan["prefixes"][obj] + "_C{:02d}".format(channel_index)
        sample_values = [grid[(x, y)][(obj, attr)]
                         for y in ys for x in row_xs[y]]
        if max(sample_values) - min(sample_values) < 1e-10:
            # SDK group already matches the saved Neutral pose.
            continue
        row_plugs = []
        for row_index, y in enumerate(ys):
            holder = cmds.createNode("network", name=prefix + "_Y{:02d}_XKey".format(row_index))
            cmds.addAttr(holder, longName="value", attributeType="double", keyable=True)
            plug = holder + ".value"
            # A row may have one X pose or fewer X poses than other rows.
            # Maya animCurves hold their endpoint values outside saved keys.
            for x in row_xs[y]:
                cmds.setDrivenKeyframe(plug, currentDriver=x_attr,
                                       driverValue=x, value=grid[(x, y)][(obj, attr)])
            cmds.keyTangent(plug, inTangentType="linear", outTangentType="linear")
            row_plugs.append(plug)

        result_plug = row_plugs[0]
        for row_index in range(1, len(ys)):
            weight = cmds.createNode("network", name=prefix + "_Y{:02d}_Weight".format(row_index))
            cmds.addAttr(weight, longName="value", attributeType="double", keyable=True)
            wplug = weight + ".value"
            cmds.setDrivenKeyframe(wplug, currentDriver=y_attr, driverValue=ys[row_index-1], value=0.0)
            cmds.setDrivenKeyframe(wplug, currentDriver=y_attr, driverValue=ys[row_index], value=1.0)
            cmds.keyTangent(wplug, inTangentType="linear", outTangentType="linear")
            blend = cmds.createNode("blendColors", name=prefix + "_Y{:02d}_Blend".format(row_index))
            cmds.connectAttr(row_plugs[row_index], blend + ".color1R")
            cmds.connectAttr(result_plug, blend + ".color2R")
            cmds.connectAttr(wplug, blend + ".blender")
            result_plug = blend + ".outputR"

        # Use identity SDK keys for the final conversion. Directly connecting
        # unitless blendColors.outputR to an angle plug risks a radians/degrees
        # mismatch and was a source of incorrect rotations in earlier trials.
        output = groups[obj] + "." + attr
        lo = min(sample_values) - 1.0
        hi = max(sample_values) + 1.0
        cmds.setDrivenKeyframe(output, currentDriver=result_plug,
                               driverValue=lo, value=lo)
        cmds.setDrivenKeyframe(output, currentDriver=result_plug,
                               driverValue=hi, value=hi)
        cmds.keyTangent(output, inTangentType="linear", outTangentType="linear")
    return groups


def BuildSDKSimultaneous2D(datas):
    """Build simultaneous 2D SDK without writing to or requiring joint drivers."""
    plans = _sim2d_preflight(datas)
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Simultaneous 2D SDK: Enable Maya Undo before Run")
    chunk = "NLTA Simultaneous 2D SDK Build"
    cmds.undoInfo(openChunk=True, chunkName=chunk)
    try:
        results = [_sim2d_build_one(plan) for plan in plans]
    except Exception:
        try:
            cmds.undoInfo(closeChunk=True)
            if (not cmds.undoInfo(query=True, undoQueueEmpty=True)
                    and cmds.undoInfo(query=True, undoName=True) == chunk):
                cmds.undo()
            else:
                cmds.warning("Simultaneous 2D SDK: Could not safely undo build. "
                             "Check for partial helper nodes in the scene.")
        except Exception as rollback_error:
            cmds.warning("Simultaneous 2D SDK: Rollback failed: " + str(rollback_error))
        raise
    else:
        cmds.undoInfo(closeChunk=True)
        return results


def Run(data, *args):
    return BuildSDKSimultaneous2D(NLTA_General.readJsonFile(_pattern_data_path(data)))


def ExportPython(data, *args):
    """Export the SAME builder and validation logic as Run to standalone Python."""
    path = _pattern_data_path(data)
    records = NLTA_General.readJsonFile(path)
    if not isinstance(records, list) or not records:
        cmds.warning("Simultaneous 2D SDK Export: No saved data")
        return None
    # Validate before exporting, so incomplete grids cannot create an unsafe rig.
    _sim2d_preflight(records)
    definitions = (_sim2d_preflight, _sim2d_build_one, BuildSDKSimultaneous2D)
    code = "\n\n".join(inspect.getsource(fn).rstrip() for fn in definitions)
    code = "\n".join("    " + line if line.strip() else "" for line in code.splitlines())
    data_text = "[\n" + ",\n".join("        " + repr(record) for record in records) + "\n    ]"
    source = (
        "def main():\n"
        "    import re\n"
        "    import math\n"
        "    import maya.cmds as cmds\n\n"
        "    # Saved simultaneous two-driver SDK poses.\n"
        "    SDK_DATA = " + data_text + "\n\n"
        + code +
        "\n\n    # Use the identical preflight and rig builder as Scene.Run.\n"
        "    BuildSDKSimultaneous2D(SDK_DATA)\n\n"
        'if __name__ == "__main__":\n    main()\n'
    )
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(path), filename)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(source)
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
        cmds.textField(text='X',editable=False,bgc=(0.216, 0.216, 0.216),w=55)
        keyUI["driverValue1"] = cmds.textField(text=str(keyData.get("driverValue1", "0")),w=65)
        cmds.textField(text='Y',editable=False,bgc=(0.216, 0.216, 0.216),w=55)
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
    cmds.textField(text='Driver X',editable=False)
    itemData['driverAttr1'] = cmds.textField(text=data.get("driverAttr1", ""))
    cmds.button(label="+",w=30,c=partial(NLTA_UI.PickAttrs,itemData['driverAttr1']))

    cmds.textField(text='Driver Y',editable=False)
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
