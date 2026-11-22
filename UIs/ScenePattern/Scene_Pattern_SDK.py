import os
import importlib
import inspect
import pprint
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
    name = "Driven Key"
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
                "drivenAttrs":cmds.scrollField(item["drivenAttrs"],q=True,text=True),
                "keyData":[],
                "switchAttr":cmds.textField(item["switchAttr"],q=True,text=True),
            }
            for keyUI in item["keyUI"]:
                keyDict = {
                    "driverValue":cmds.textField(keyUI["driverValue"],q=True,text=True),
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
    exportButton = cmds.button(label="Export Py", width=100, c=SaveAndExport)
    cmds.popupMenu(parent=exportButton, button=3)
    cmds.menuItem(label="Open Folder", c=partial(OpenExportFolder, data))
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

        mirrorDrivenAttrs.append(
            mirrorObj + "." + attr
        )

    # -----------------------------------
    # Key Data
    # -----------------------------------
    mirrorKeyData = []

    for keyUI in item["keyUI"]:

        # GIỮ NGUYÊN driverValue
        driverValue = cmds.textField(
            keyUI["driverValue"],
            q=True,
            text=True
        )

        keyData = {
            "driverValue": driverValue,
            "drivenValues": {}
        }

        for obj, attrUIs in keyUI["drivenValues"].items():

            mirrorObj = NLTA_General.GetMirrorName(obj)

            keyData["drivenValues"][mirrorObj] = {}

            for attr, valueUI in attrUIs.items():

                # GIỮ NGUYÊN driven value
                value = cmds.textField(
                    valueUI,
                    q=True,
                    text=True
                )

                keyData["drivenValues"][mirrorObj][attr] = value

        mirrorKeyData.append(keyData)

    mirrorData = {
        "driverAttr": mirrorDriverObj + "." + driverName,
        "drivenAttrs": "\n".join(mirrorDrivenAttrs),
        "keyData": mirrorKeyData
    }

    Add(listUI, mirrorData)

def CreateMirrorAll(listUI, *args):
    global ITEMS

    # Quan trọng:
    # copy list trước, vì CreateMirror sẽ append Item mới
    currentItems = list(ITEMS["order"])

    count = 0

    for itemUI in currentItems:
        before = len(ITEMS["order"])

        CreateMirror(itemUI, listUI)

        if len(ITEMS["order"]) > before:
            count += 1

    cmds.warning(
        "Mirror All SDK Data Done! Created : {}".format(count)
    )

def GetItemData(itemUI):
    global ITEMS

    item = ITEMS["items"][itemUI]

    data = {
        "driverAttr": cmds.textField(
            item["driverAttr"], q=True, text=True
        ).strip(),

        "drivenAttrs": cmds.scrollField(
            item["drivenAttrs"], q=True, text=True
        ),

        "keyData": []
    }

    for keyUI in item["keyUI"]:
        keyData = {
            "driverValue": cmds.textField(
                keyUI["driverValue"], q=True, text=True
            ),
            "drivenValues": {}
        }

        for obj, attrUIs in keyUI["drivenValues"].items():
            keyData["drivenValues"][obj] = {}

            for attr, valueUI in attrUIs.items():
                keyData["drivenValues"][obj][attr] = cmds.textField(
                    valueUI, q=True, text=True
                )

        data["keyData"].append(keyData)

    return data

def MergeDuplicate(listUI, *args):
    global ITEMS

    # Lấy toàn bộ data đang có trên UI
    allData = [
        GetItemData(itemUI)
        for itemUI in ITEMS["order"]
        if itemUI in ITEMS["items"]
    ]

    merged = {}
    order = []

    for item in allData:
        driverAttr = item["driverAttr"]

        if driverAttr not in merged:
            merged[driverAttr] = {
                "driverAttr": driverAttr,
                "drivenAttrs": [],
                "keyData": {}
            }
            order.append(driverAttr)

        target = merged[driverAttr]

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

            if valueKey not in target["keyData"]:
                target["keyData"][valueKey] = {
                    "driverValue": driverValue,
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

    for driverAttr in order:
        item = merged[driverAttr]

        result.append({
            "driverAttr": driverAttr,
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

    cmds.window(
        win,
        title="Replace Object",
        widthHeight=(360,130),
        sizeable=False
    )

    cmds.columnLayout(
        adjustableColumn=True,
        rowSpacing=5
    )

    cmds.rowLayout(
        numberOfColumns=2,
        columnWidth2=(90,250)
    )
    cmds.text(label="Old Name")
    oldUI = cmds.textField()
    cmds.setParent("..")

    cmds.rowLayout(
        numberOfColumns=2,
        columnWidth2=(90,250)
    )
    cmds.text(label="New Name")
    newUI = cmds.textField()
    cmds.setParent("..")

    def DoReplace(*args):
        global ITEMS

        oldName = cmds.textField(
            oldUI,
            q=True,
            text=True
        ).strip()

        newName = cmds.textField(
            newUI,
            q=True,
            text=True
        ).strip()

        if not oldName or not newName:
            cmds.warning("Old Name / New Name cannot be empty")
            return

        replaceCount = 0

        for itemUI in list(ITEMS["order"]):

            if itemUI not in ITEMS["items"]:
                continue

            item = ITEMS["items"][itemUI]

            # --------------------------------
            # Driver Attr
            # --------------------------------
            driverAttr = cmds.textField(
                item["driverAttr"],
                q=True,
                text=True
            ).strip()

            if "." in driverAttr:

                obj, attr = driverAttr.rsplit(".", 1)

                if obj == oldName:
                    driverAttr = newName + "." + attr

                    cmds.textField(
                        item["driverAttr"],
                        e=True,
                        text=driverAttr
                    )

                    cmds.frameLayout(
                        itemUI,
                        e=True,
                        label=driverAttr
                    )

                    replaceCount += 1

            # --------------------------------
            # Driven Attrs
            # --------------------------------
            drivenAttrs = cmds.scrollField(
                item["drivenAttrs"],
                q=True,
                text=True
            ).splitlines()

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

                newDrivenAttrs.append(
                    obj + "." + attr
                )

            cmds.scrollField(
                item["drivenAttrs"],
                e=True,
                text="\n".join(newDrivenAttrs)
            )

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
                objectUIs = keyUI.get(
                    "drivenObjectUIs",
                    {}
                )

                if oldName in objectUIs:

                    objUI = objectUIs[oldName]

                    objectUIs[newName] = objUI
                    del objectUIs[oldName]

                    # tìm text label đầu tiên trong object block
                    children = cmds.layout(
                        objUI,
                        q=True,
                        ca=True
                    ) or []

                    for child in children:
                        if cmds.objectTypeUI(child) == "text":
                            cmds.text(
                                child,
                                e=True,
                                label="  " + newName
                            )
                            break

                replaceCount += 1

        if cmds.window(win, exists=True):
            cmds.deleteUI(win)

        cmds.warning(
            "Replace Object Done : {} -> {} | Changed : {}".format(
                oldName,
                newName,
                replaceCount
            )
        )

    cmds.rowLayout(
        numberOfColumns=2,
        columnWidth2=(175,175)
    )

    cmds.button(
        label="Replace",
        c=DoReplace
    )

    cmds.button(
        label="Cancel",
        c=lambda *x: cmds.deleteUI(win)
    )

    cmds.setParent("..")

    cmds.showWindow(win)


def _sdk_data_path(data):
    newestData = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]
    })
    if not newestData or not newestData.get("path"):
        raise ValueError("SDK: cannot find data path in ScenePatternData.json")
    return os.path.normpath(newestData["path"])


def _sdk_read_data(data):
    return NLTA_General.readJsonFile(_sdk_data_path(data))


def OpenExportFolder(data, *args):
    folder = os.path.dirname(_sdk_data_path(data))
    if os.path.isdir(folder):
        os.startfile(folder)
    else:
        cmds.warning("SDK: folder does not exist: " + folder)


def _format_sdk_data(datas, line_width=130):
    """Keep every channel dictionary and multiline-string value on one Python line."""
    lines = ["["]
    for item in datas:
        lines.append("    {")
        for key, value in item.items():
            if key == "keyData" and isinstance(value, (list, tuple)):
                lines.append("        'keyData': [")
                for frame in value:
                    if (not isinstance(frame, dict) or "drivenValues" not in frame
                            or "driverValue" not in frame):
                        lines.append("            " + repr(frame) + ",")
                        continue
                    lines.append(
                        "            {'driverValue': " + repr(frame.get("driverValue"))
                        + ", 'drivenValues': {"
                    )
                    for obj, channels in frame["drivenValues"].items():
                        lines.append(
                            "                " + repr(obj) + ": " + repr(channels) + ","
                        )
                    extras = "".join(
                        ", " + repr(key) + ": " + repr(value)
                        for key, value in frame.items()
                        if key not in ("driverValue", "drivenValues")
                    )
                    lines.append("            }" + extras + "},")
                lines.append("        ],")
            elif isinstance(value, str):
                # The original text stays exact; repr escapes embedded newlines.
                lines.append("        " + repr(key) + ": " + repr(value) + ",")
            else:
                lines.append("        " + repr(key) + ": " + repr(value) + ",")
        lines.append("    },")
    lines.append("]")
    return "\n".join(lines)


def ExportPython(data, *args):
    sdk_data = _sdk_read_data(data)
    if not isinstance(sdk_data, list) or not sdk_data:
        cmds.warning("SDK Export: no saved SDK items")
        return None

    for index, item in enumerate(sdk_data, 1):
        if not isinstance(item, dict) or "driverAttr" not in item or "keyData" not in item:
            raise ValueError("SDK item {} requires driverAttr and keyData".format(index))

    # Emit one keyframe header and one full channel dict per line.
    formatted = _format_sdk_data(sdk_data).replace("\n", "\n    ")
    builder = inspect.getsource(_build_sdk).rstrip()
    builder = "\n".join("    " + line if line.strip() else ""
                        for line in builder.splitlines())
    source = (
        "def main():\n"
        "    import maya.cmds as cmds\n\n"
        "    # SDK data\n"
        "    SDK_DATA = " + formatted + "\n\n"
        + builder
        + "\n\n    # Build the driven keys.\n"
        + "    _build_sdk(SDK_DATA)\n\n\n"
        + 'if __name__ == "__main__":\n    main()\n'
    )
    export_name = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, export_name, "exec")
    output_path = os.path.join(os.path.dirname(_sdk_data_path(data)), export_name)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(source)
    return output_path


def Run(data, *args):
    datas = _sdk_read_data(data)
    if not datas:
        return
    return _build_sdk(datas)


def _build_sdk(datas):
    for itemData in datas:
        driverAttr = itemData["driverAttr"]
        # Preserve the saved control order when creating SDK groups.
        drivenObjects = list(dict.fromkeys(
            obj for keyData in itemData["keyData"]
            for obj in keyData["drivenValues"]
        ))
        sdkDict = {}

        # Create helper groups and constraints for the driven controls.
        for obj in drivenObjects:
            originalParent = cmds.listRelatives(obj, parent=True)
            originalParent = originalParent[0] if originalParent else None
            sdkGrp = obj + "_SDKGrp"
            containGrp = obj + "_SDKGrpContain"
            neutralGrp = obj + "_SDKNeutralGrp"
            if not cmds.objExists(sdkGrp):
                sdkGrp = cmds.group(em=True, n=sdkGrp)
                cmds.delete(cmds.parentConstraint(obj, sdkGrp, mo=False))
                cmds.delete(cmds.scaleConstraint(obj, sdkGrp, mo=False))
            if not cmds.objExists(containGrp):
                containGrp = cmds.group(em=True, n=containGrp)
                cmds.delete(cmds.parentConstraint(obj, containGrp, mo=False))
                cmds.delete(cmds.scaleConstraint(obj, containGrp, mo=False))
            if not cmds.objExists(neutralGrp):
                neutralGrp = cmds.group(em=True, n=neutralGrp)
                cmds.delete(cmds.parentConstraint(obj, neutralGrp, mo=False))
                cmds.delete(cmds.scaleConstraint(obj, neutralGrp, mo=False))

            # Parent helper groups
            if originalParent:
                for grp in [sdkGrp, containGrp, neutralGrp]:
                    parent = cmds.listRelatives(grp, parent=True)
                    if not parent:
                        cmds.parent(grp, originalParent)

            # Put driven object inside contain
            currentParent = cmds.listRelatives(obj, parent=True)
            if not currentParent or currentParent[0] != containGrp:
                cmds.parent(obj, containGrp)

            # Blend the SDK transforms with the original neutral pose.
            switchAttr = itemData.get("switchAttr", "").strip()
            if switchAttr:
                sdkEnable = switchAttr
            else:
                sdkEnable = "SDK_Enable"
            if not cmds.attributeQuery(sdkEnable, node=obj, exists=True):
                cmds.addAttr(obj, ln=sdkEnable, at="double", min=0, max=1, dv=1, keyable=True)
            sdkEnable = obj + "." + sdkEnable
            reverseNode = obj + "_SDK_Enable_REV"
            if not cmds.objExists(reverseNode):
                reverseNode = cmds.createNode("reverse", n=reverseNode)
            if not cmds.isConnected(sdkEnable, reverseNode + ".inputX"):
                cmds.connectAttr(sdkEnable, reverseNode + ".inputX", f=True)

            # Connect the neutral and SDK parent constraints.
            parentConstraints = cmds.listConnections(containGrp, s=True, d=False, type="parentConstraint") or []
            if parentConstraints:
                parentConstraint = parentConstraints[0]
            else:
                parentConstraint = cmds.parentConstraint(neutralGrp, sdkGrp, containGrp, mo=False, n=containGrp + "_parentConstraint")[0]
            parentAliases = cmds.parentConstraint(parentConstraint, q=True, wal=True)
            cmds.connectAttr(reverseNode + ".outputX", parentConstraint + "." + parentAliases[0], f=True)
            cmds.connectAttr(sdkEnable, parentConstraint + "." + parentAliases[1], f=True)

            # Blend neutral and SDK scales.
            scaleConstraints = cmds.listConnections(containGrp, s=True, d=False, type="scaleConstraint") or []
            if scaleConstraints:
                scaleConstraint = scaleConstraints[0]
            else:
                scaleConstraint = cmds.scaleConstraint(neutralGrp, sdkGrp, containGrp, mo=False, n=containGrp + "_scaleConstraint")[0]
            scaleAliases = cmds.scaleConstraint(scaleConstraint, q=True, wal=True)
            cmds.connectAttr(reverseNode + ".outputX", scaleConstraint + "." + scaleAliases[0], f=True)
            cmds.connectAttr(sdkEnable, scaleConstraint + "." + scaleAliases[1], f=True)
            sdkDict[obj] = sdkGrp

        # Keep zero-only channels without unnecessary animation curves.
        keyDatas = itemData["keyData"]
        channelValues = {}

        # Gather each channel's values across all driver keys.
        for keyData in keyDatas:
            for obj, attrData in keyData["drivenValues"].items():
                if obj not in sdkDict:
                    continue
                for attr, value in attrData.items():
                    channelValues.setdefault((obj, attr), []).append(float(value))

        # Identify channels that stay at zero.
        zeroChannels = {
            channel
            for channel, values in channelValues.items()
            if len(values) == len(keyDatas)
            and all(abs(value) < 1e-10 for value in values)
        }
        initializedZero = set()

        # Apply saved driver values to the animated channels.
        for keyData in keyDatas:
            driverValue = float(keyData["driverValue"])
            for obj, attrData in keyData["drivenValues"].items():
                if obj not in sdkDict:
                    continue
                sdkGrp = sdkDict[obj]
                for attr, value in attrData.items():
                    sdkAttr = "{}.{}".format(sdkGrp, attr)
                    channel = (obj, attr)
                    if not cmds.attributeQuery(attr, node=sdkGrp, exists=True):
                        cmds.addAttr(sdkGrp, ln=attr, at="double", keyable=True)

                    # Keep constant-zero channels without animation curves.
                    if channel in zeroChannels:
                        incoming = cmds.listConnections(sdkAttr, s=True, d=False, p=True) or []
                        if not incoming:
                            if channel not in initializedZero:
                                cmds.setAttr(sdkAttr, 0.0)
                                initializedZero.add(channel)
                            continue

                    # Create a linear driven key for this channel.
                    cmds.setDrivenKeyframe(sdkAttr, currentDriver=driverAttr, driverValue=driverValue, value=float(value))
                    cmds.keyTangent(sdkAttr, itt="linear", ott="linear")

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

        for otherUI in ITEMS["order"]:

            if otherUI == itemUI:
                continue

            otherDriver = cmds.textField(
                ITEMS["items"][otherUI]["driverAttr"],
                q=True,
                text=True
            ).strip()

            if otherDriver == mirrorAttr:
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
            label=data["driverAttr"],
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
                label="Value : {}".format(
                    keyData["driverValue"]
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
            keyData = {
                "driverValue":cmds.getAttr(cmds.textField(ITEMS["items"][itemUI]["driverAttr"],q=True,text=True)),
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
        keyUI["keyName"] = cmds.frameLayout(label=str(keyData["driverValue"]),parent=listKey,collapsable=True,collapse=True,w=360)
        cmds.rowColumnLayout(numberOfColumns=1)

        cmds.rowColumnLayout(numberOfColumns=4)
        cmds.textField(text='Value',editable=False,bgc=(0.216, 0.216, 0.216),w=50)                  
        keyUI["driverValue"] = cmds.textField(text=keyData["driverValue"],w=150)
        cmds.button(label="X",c=partial(DeleteKeyItem,itemUI,keyUI["keyName"]),w=60)
        cmds.button(label="Get All",c=partial(GetValue,itemUI,keyUI["keyName"]),w=60)
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
    cmds.textField(text='Driver Attr',editable=False)
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