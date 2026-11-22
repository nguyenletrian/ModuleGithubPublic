import os
import maya.cmds as cmds
from datetime import datetime

def FillUI(ui,value,*arr):
    # Composite widget: same entry point as ordinary Maya controls.
    if isinstance(ui, dict):
        if ui.get("_nlta_type") == "scrollList":
            SetScrollListUI(ui, value)
            return
        if ui.get("_nlta_type") == "path":
            SetPathUI(ui, value)
            return
        if ui.get("_nlta_type") == "curveGraph":
            SetCurveGraphUI(ui, value)
            return
    ui_type = cmds.objectTypeUI(ui)
    if ui_type in ["textField", "textFieldGrp","field"]:
        cmds.textField(ui, e=True, text=value)
    elif ui_type == "cmdScrollField":
        cmds.scrollField(ui, e=True, text=value)
    elif ui_type in ["intField", "intFieldGrp"]:
        cmds.intField(ui, e=True, value=value)
    elif ui_type in ["floatField", "floatFieldGrp"]:
        cmds.floatField(ui, e=True, value=float(value))
    elif ui_type == "text":
        cmds.text(ui, e=True, label=value)
    elif ui_type == "checkBox":
        cmds.checkBox(ui, e=True, value=value)
    elif ui_type == "scrollField":
        cmds.scrollField(ui, e=True, text=value)
    elif ui_type == "radioButtonGrp":
        cmds.radioButtonGrp(ui, e=True, select=value)
    elif ui_type == "popupMenu":
        cmds.optionMenu(ui,e=True,value=value)        
    else:
        print(f"UI type '{ui_type}' chưa support")

def PickObject(ui, *args):
    objs = cmds.ls(flatten=True,os=True)
    if not objs:
        return
    string = "\n".join(objs)
    FillUI(ui,string)

def PickObjectAdd(ui,*args):
    objs = cmds.ls(flatten=True,os=True)
    if not objs:
        return
    oldValue = GetUIValue(ui)
    oldObjs = [x.strip() for x in oldValue.split("\n") if x.strip()]
    result = oldObjs[:]
    for obj in objs:
        if obj not in result:
            result.append(obj)
    FillUI(
        ui,
        "\n".join(result)
    )

def PickPos(ui, *args):
    objs = cmds.ls(os=True, flatten=True)
    if not objs:
        return
    positions = []
    for obj in objs:
        pos = cmds.xform(obj, q=True, ws=True, t=True)
        positions.append("{:.6f} {:.6f} {:.6f}".format(*pos))

    FillUI(ui, "\n".join(positions))


def PickPosAdd(ui, *args):
    objs = cmds.ls(os=True, flatten=True)
    if not objs:
        return
    oldValue = GetUIValue(ui)
    result = [line.strip() for line in oldValue.splitlines() if line.strip()]

    for obj in objs:
        pos = cmds.xform(obj, q=True, ws=True, t=True)
        posStr = "{:.6f} {:.6f} {:.6f}".format(*pos)

        if posStr not in result:
            result.append(posStr)

    FillUI(ui, "\n".join(result))

def PickTransform(ui, *args):
    objs = cmds.ls(os=True, flatten=True)
    if not objs:
        return

    values = []
    for obj in objs:
        t = cmds.xform(obj, q=True, ws=True, t=True)
        r = cmds.xform(obj, q=True, ws=True, ro=True)
        values.append("{:.6f} {:.6f} {:.6f} {:.6f} {:.6f} {:.6f}".format(*(t + r)))

    FillUI(ui, "\n".join(values))


def PickTransformAdd(ui, *args):
    objs = cmds.ls(os=True, flatten=True)
    if not objs:
        return

    oldValue = GetUIValue(ui)
    result = [line.strip() for line in oldValue.splitlines() if line.strip()]

    for obj in objs:
        t = cmds.xform(obj, q=True, ws=True, t=True)
        r = cmds.xform(obj, q=True, ws=True, ro=True)
        valueStr = "{:.6f} {:.6f} {:.6f} {:.6f} {:.6f} {:.6f}".format(*(t + r))

        if valueStr not in result:
            result.append(valueStr)

    FillUI(ui, "\n".join(result))

def PickObjectSemi(ui, *args):
    objs = cmds.ls(flatten=True,os=True)
    if not objs:
        return
    string = ";".join(objs)
    FillUI(ui,string)

def PickObjectSemiAdd(ui,*args):
    objs = cmds.ls(flatten=True,os=True)
    if not objs:
        return
    oldValue = GetUIValue(ui)
    string = oldValue+"\n"+";".join(objs)
    FillUI(
        ui,string
    )


def AddObject(ui, *args):
    objs = cmds.ls(flatten=True,os=True)
    if not objs:
        return
    ui_type = cmds.objectTypeUI(ui)
    if ui_type in ["textField", "textFieldGrp", "field"]:
        current = cmds.textField(ui, q=True, text=True)
        values = [x for x in current.split("\n") if x]
        values.extend(objs)
        values = list(dict.fromkeys(values))
        cmds.textField(ui, e=True, text="\n".join(values))
    elif ui_type in ["scrollField", "cmdScrollField"]:
        current = cmds.scrollField(ui, q=True, text=True)
        values = [x for x in current.split("\n") if x]
        values.extend(objs)
        values = list(dict.fromkeys(values))
        cmds.scrollField(ui, e=True, text="\n".join(values))
    elif ui_type == "optionMenu":
        items = cmds.optionMenu(ui, q=True, itemListLong=True) or []
        values = [cmds.menuItem(item, q=True, label=True) for item in items]
        values.extend(objs)
        values = list(dict.fromkeys(values))
        for item in items:
            cmds.deleteUI(item)
        for value in values:
            cmds.menuItem(label=value, parent=ui)
        if values:
            cmds.optionMenu(ui, e=True, value=values[0])
    else:
        print("UI type '{}' chưa support".format(ui_type))

def PickNamespace(ui, *args):
    objs = cmds.ls(flatten=True,os=True)
    if objs:
        obj = objs[0]
        parts = obj.split(":")
        if len(parts) <= 1:
            namespace = ""
        else:
            namespace = ":".join(parts[:-1])
        count = len(objs)
        ui_type = cmds.objectTypeUI(ui)

        if ui_type in ["textField", "textFieldGrp","field"]:
            cmds.textField(ui, e=True, text=namespace)
        elif ui_type in ["intField", "intFieldGrp"]:
            cmds.intField(ui, e=True, value=count)
        elif ui_type in ["floatField", "floatFieldGrp"]:
            cmds.floatField(ui, e=True, value=float(count))
        elif ui_type == "text":
            cmds.text(ui, e=True, label=namespace)
        elif ui_type == "optionMenu":
            items = cmds.optionMenu(ui, q=True, itemListLong=True) or []
            for item in items:
                cmds.deleteUI(item)
            namespaces = []
            for o in objs:
                p = o.split(":")
                ns = ":".join(p[:-1]) if len(p) > 1 else ""
                namespaces.append(ns)
            namespaces = list(set(namespaces))
            for ns in namespaces:
                cmds.menuItem(label=ns, parent=ui)
            if namespaces:
                cmds.optionMenu(ui, e=True, value=namespaces[0])
        elif ui_type == "checkBox":
            cmds.checkBox(ui, e=True, value=bool(namespace))
        elif ui_type == "scrollField":
            cmds.scrollField(ui, e=True, text=namespace)

        else:
            print(f"UI type '{ui_type}' chưa support")

def ClearUI(ui,*arr):
    children = cmds.rowColumnLayout(ui, q=True, childArray=True)
    if children:
        for child in children:
            cmds.deleteUI(child)

def GetData(inputDict,*arr):
    result = []
    for item, controls in inputDict.items():
        values = {}
        for key, ui in controls.items():
            name = key[0].lower() + key[1:] if key else key
            values[name] = GetUIValue(ui)
        result.append(values)
    return result


def SetData(inputDict, data, *arr):
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, (list, tuple)):
        raise TypeError("SetData expects a list of dictionaries or one dictionary")
    for controls, values in zip(inputDict.values(), data):
        if not isinstance(values, dict):
            raise TypeError("Each SetData row must be a dictionary")
        for key, ui in controls.items():
            name = key[0].lower() + key[1:] if key else key
            if name in values:
                FillUI(ui, values[name])


def GetUIValue(ui):
    if isinstance(ui, dict):
        if ui.get("_nlta_type") == "scrollList":
            return GetScrollListUI(ui)
        if ui.get("_nlta_type") == "path":
            return GetPathUI(ui)
        if ui.get("_nlta_type") == "curveGraph":
            return GetCurveGraphUI(ui)
    uiType = cmds.objectTypeUI(ui)
    queryMap = {
        "field": lambda x: cmds.textField(x, q=True, text=True),
        "textField": lambda x: cmds.textField(x, q=True, text=True),
        "scrollField": lambda x: cmds.scrollField(x, q=True, text=True),
        "cmdScrollField": lambda x: cmds.scrollField(x, q=True, text=True),
        "checkBox": lambda x: cmds.checkBox(x, q=True, value=True),
        "intField": lambda x: cmds.intField(x, q=True, value=True),
        "floatField": lambda x: cmds.floatField(x, q=True, value=True),
        "optionMenu": lambda x: cmds.optionMenu(x, q=True, value=True),
        "popupMenu": lambda x: cmds.optionMenu(x, q=True, value=True),
        "textFieldGrp": lambda x: cmds.textFieldGrp(x, q=True, text=True),
        "intFieldGrp": lambda x: cmds.intFieldGrp(x, q=True, value1=True),
        "floatFieldGrp": lambda x: cmds.floatFieldGrp(x, q=True, value1=True),
        "radioButtonGrp": lambda x: cmds.radioButtonGrp(x, q=True, select=True),
        "text": lambda x: cmds.text(x, q=True, label=True)
    }
    if uiType not in queryMap:
        raise RuntimeError("Unsupported UI Type: {}".format(uiType))
    return queryMap[uiType](ui)

def GetSelectedAttribute(*arr):
    objs =  cmds.ls(flatten=True,os=True)
    if objs:
        returnData = {
            "allAttr":[]
        }
        mainAttr = cmds.channelBox("mainChannelBox",query=True,sma=True)
        if mainAttr:
            returnData["main"] = mainAttr
            returnData["allAttr"].extend(mainAttr)
        shapeAttr = cmds.channelBox("mainChannelBox",query=True,ssa=True)
        if shapeAttr:
            returnData["shape"] = shapeAttr
            returnData["allAttr"].extend(shapeAttr)
        inputAttr = cmds.channelBox("mainChannelBox",query=True,sha=True)
        if inputAttr:
            returnData["input"] = inputAttr
            returnData["allAttr"].extend(inputAttr)
        outputAttr = cmds.channelBox("mainChannelBox",query=True,soa=True)
        if outputAttr:
            returnData["output"] = outputAttr
            returnData["allAttr"].extend(outputAttr)
        returnData["objs"] = objs
        return(returnData)
    return(None)

def GetAttributeInfo(node, attr):
    full = "{}.{}".format(node, attr)
    data = {}
    data["name"] = attr
    data["type"] = cmds.getAttr(full, type=True)
    data["keyable"] = cmds.getAttr(full, k=True)
    data["lock"] = cmds.getAttr(full, l=True)
    data["channelBox"] = cmds.getAttr(full, cb=True)
    if cmds.attributeQuery(attr, node=node, minExists=True):
        data["min"] = cmds.attributeQuery(attr, node=node, minimum=True)[0]
    if cmds.attributeQuery(attr, node=node, maxExists=True):
        data["max"] = cmds.attributeQuery(attr, node=node, maximum=True)[0]
    if cmds.attributeQuery(attr, node=node, listDefault=True):
        default = cmds.attributeQuery(attr, node=node, listDefault=True)
        if default:
            data["default"] = default[0]
    if data["type"] == "enum":
        enum = cmds.attributeQuery(attr, node=node, listEnum=True)
        if enum:
            data["enum"] = enum[0]
    return data

def PickAttrs(ui,*arr):
    attrData = GetSelectedAttribute()
    returnData = []
    if attrData:
        for obj in attrData["objs"]:         
            for attr in attrData["allAttr"]:
                returnData.append(obj+"."+attr)
        FillUI(ui,("\n").join(returnData))

def PickAttr(ui,*arr):
    attrData = GetSelectedAttribute()
    if attrData and attrData["main"]:
        FillUI(
            ui,
            attrData["objs"][0]+"."+attrData["main"][0]
        )

def PickAttrOnly(ui,*arr):
    attrData = GetSelectedAttribute()
    if attrData and attrData["main"]:
        FillUI(
            ui,
            attrData["main"][0]
        )

def PickAttrsAdd(ui,*arr):
    attrData = GetSelectedAttribute()
    returnData = GetUIValue(ui).split("\n")
    if attrData:
        for obj in attrData["objs"]:         
            for attr in attrData["allAttr"]:
                returnData.append(obj+"."+attr)
        FillUI(ui,("\n").join(returnData))


def OpenFolder(ui,*args):
    path = GetUIValue(ui)
    path = os.path.normpath(path)
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if os.path.isdir(path):
        os.startfile(path)
    else:
        cmds.warning("Path does not exist: {}".format(path))

def SendFile(ui,*args):
    path = os.path.normpath(GetUIValue(ui))
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

def CreateScrollListUI(parent, values=None, height=260, fieldHeight=85):
    """Create a reusable list of scrollFields. Returns an in-memory UI handle.

    Use GetScrollListUI(handle) for JSON-serializable list[str], NOT the handle.
    """
    handle = {"_nlta_type": "scrollList", "items": [], "fieldHeight": fieldHeight}
    handle["root"] = cmds.columnLayout(adjustableColumn=True, parent=parent)

    handle["header"] = cmds.rowLayout(
        numberOfColumns=2, adjustableColumn=1, parent=handle["root"])
    handle["count"] = cmds.text(label="0 items", align="left")
    cmds.button(label="+ Add", width=75, height=26,
                command=lambda *_: AddScrollListItem(handle))

    handle["scroll"] = cmds.scrollLayout(
        childResizable=True, height=height, parent=handle["root"])
    handle["content"] = cmds.columnLayout(
        adjustableColumn=True, rowSpacing=5, parent=handle["scroll"])

    SetScrollListUI(handle, values if values is not None else [])
    return handle


def _RefreshScrollListUI(handle):
    items = handle["items"]
    for index, item in enumerate(items, 1):
        cmds.text(item["label"], edit=True, label="Item {:02d}".format(index))
    cmds.text(handle["count"], edit=True,
              label="{} item(s)".format(len(items)))



def AddScrollListItem(handle, value="", *args):
    item = {}
    def AddQuotes(*args):
        text = cmds.scrollField(item["field"], q=True, text=True)
        lines = text.splitlines()
        result = []
        for line in lines:
            if not line.strip():
                result.append(line)
                continue
            # Preserve indentation
            indent = line[:len(line) - len(line.lstrip())]
            content = line.strip()

            if not (content.startswith('"') and content.endswith('"')):
                content = '"{}"'.format(content)

            result.append(indent + content)

        cmds.scrollField(item["field"],e=True,text="\n".join(result))

    def JoinLines(*args):
        result = cmds.promptDialog(
            title="Join Lines",
            message="Separator:",
            button=["Join", "Cancel"],
            defaultButton="Join",
            cancelButton="Cancel",
            dismissString="Cancel",
            text=", "
        )
        if result != "Join":
            return
        separator = cmds.promptDialog(q=True, text=True)
        text = cmds.scrollField(item["field"],q=True,text=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cmds.scrollField( item["field"], e=True, text=separator.join(lines))

    item["root"] = cmds.columnLayout(adjustableColumn=True,parent=handle["content"])
    bar = cmds.rowLayout(
        numberOfColumns=7,
        adjustableColumn=1,
        columnWidth=[
            (1, 90),
            (2, 45),
            (3, 45),
            (4, 65),
            (5, 45),
            (6, 45),
            (7, 28)
        ],
        parent=item["root"]
    )
    item["label"] = cmds.text(label="Item",align="left")
    cmds.button(label="Pick",width=43,command=lambda *_: PickObject(item["field"]))
    cmds.button(label="Add",width=43,command=lambda *_: PickObjectAdd(item["field"]))
    cmds.button(label='Add ""',width=63,command=AddQuotes)
    cmds.button(label="Join",width=43,command=JoinLines)
    cmds.button(label="Clear",width=43,command=lambda *_: FillUI(item["field"], ""))
    cmds.button(label="X",width=26,command=lambda *_: RemoveScrollListItem(handle, item))
    item["field"] = cmds.scrollField(text=str(value),wordWrap=True,height=handle["fieldHeight"],parent=item["root"])
    handle["items"].append(item)
    _RefreshScrollListUI(handle)
    return item["field"]

def RemoveScrollListItem(handle, item, *args):
    if item not in handle["items"]:
        return
    handle["items"].remove(item)
    if cmds.layout(item["root"], exists=True):
        cmds.deleteUI(item["root"])
    _RefreshScrollListUI(handle)


def GetScrollListUI(handle, *args):
    """Get list[str], ordered as displayed (preserves blank items)."""
    return [cmds.scrollField(item["field"], query=True, text=True)
            for item in handle["items"]]


def SetScrollListUI(handle, values, *args):
    """Replace the full list with a list of strings (e.g. loaded JSON data)."""
    if values is None:
        values = []
    if not isinstance(values, (list, tuple)):
        raise TypeError("SetScrollListUI expects a list or tuple of strings")
    for item in handle["items"][:]:
        RemoveScrollListItem(handle, item)
    for value in values:
        AddScrollListItem(handle, "" if value is None else str(value))
    _RefreshScrollListUI(handle)


def ClearScrollListUI(handle, *args):
    SetScrollListUI(handle, [])


def GetScrollListValue(handle, index):
    return cmds.scrollField(handle["items"][index]["field"], q=True, text=True)


def SetScrollListValue(handle, index, value):
    cmds.scrollField(handle["items"][index]["field"],
                     e=True, text=str(value))


# ============================================================
# PATH PICKER (generic, reusable)
# ============================================================

def CreatePathUI(parent, value="", mode="file", label="Path",
                 fileFilter="All Files (*.*)"):
    """Build an editable path input with Browse button.

    mode: 'file' (existing file), 'save' (output file), 'folder'.
    Returned handle works with GetData / SetData / GetUIValue / FillUI.
    """
    if mode not in ("file", "save", "folder"):
        raise ValueError("mode must be 'file', 'save', or 'folder'")
    handle = {"_nlta_type": "path", "mode": mode, "filter": fileFilter}
    handle["root"] = cmds.columnLayout(adjustableColumn=True, parent=parent)
    if label:
        cmds.text(label=label, align="left", parent=handle["root"])
    handle["row"] = cmds.rowLayout(numberOfColumns=2, adjustableColumn=1,
                                    columnAttach=[(1, "both", 0), (2, "both", 2)],
                                    parent=handle["root"])
    handle["field"] = cmds.textField(text=str(value or ""), parent=handle["row"])
    cmds.button(label="...", width=30, parent=handle["row"],
                command=lambda *_: BrowsePathUI(handle))
    return handle


def GetPathUI(handle, *args):
    return cmds.textField(handle["field"], q=True, text=True)


def SetPathUI(handle, value, *args):
    cmds.textField(handle["field"], e=True, text="" if value is None else str(value))


def BrowsePathUI(handle, *args):
    mode = handle["mode"]
    dialog_mode = {"file": 1, "save": 0, "folder": 3}[mode]
    current = GetPathUI(handle).strip()
    options = {"fileMode": dialog_mode, "dialogStyle": 2}
    if current:
        existing = os.path.expanduser(current)
        if os.path.exists(existing):
            options["startingDirectory"] = existing
        elif os.path.isdir(os.path.dirname(existing)):
            options["startingDirectory"] = os.path.dirname(existing)
    if mode != "folder":
        options["fileFilter"] = handle["filter"]
    selected = cmds.fileDialog2(**options)
    if selected:
        SetPathUI(handle, selected[0])
    return selected[0] if selected else None

# ============================================================
# CURVE GRAPH (PySide embedded into cmds layouts)
# ============================================================
# Requires NLTA_Graph.py in the Maya Python path.
# No Qt imports occur until CreateCurveGraphUI is called.
# Returned dictionary supports GetUIValue, FillUI, GetData and SetData.


def _CurveGraphModule():
    import NLTA_Graph
    return NLTA_Graph


def _AddCurveWidgetToMayaLayout(widget, layout):
    """Parent a PySide QWidget to an existing Maya cmds layout.

    MQtUtil.addWidgetToMayaLayout handles Maya's native Qt layout machinery;
    do not replace a cmds layout's pre-existing QLayout.
    """
    from maya import OpenMayaUI as omui

    ptr = omui.MQtUtil.findLayout(layout)
    if ptr is None:
        raise RuntimeError("Cannot find Maya layout: {}".format(layout))

    qt_package = widget.__class__.__module__.split(".")[0]
    if qt_package == "PySide6":
        import shiboken6 as shiboken
    elif qt_package == "PySide2":
        import shiboken2 as shiboken
    else:
        # QWidget subclass types may have a module other than PySide2/6.
        from NLTA_Graph import _qt
        qt_core, _, _ = _qt()
        if qt_core.__name__.startswith("PySide6"):
            import shiboken6 as shiboken
        else:
            import shiboken2 as shiboken

    widget_ptr = shiboken.getCppPointer(widget)[0]
    omui.MQtUtil.addWidgetToMayaLayout(int(widget_ptr), int(ptr))


def CreateCurveGraphUI(parent, points=None, mode="bezier",
                       width=360, height=200, label="", controls=False,
                       onChange=None):
    """Create an editable Graph inside a Maya cmds layout.

    Example:
        graph = CreateCurveGraphUI(column, controls=True)
        result = GetUIValue(graph)  # JSON-ready curve + tangent data
        value = GetCurveGraphValue(graph, 0.5)

    onChange receives the updated list of point pairs (same as the Graph API).
    """
    Graph = _CurveGraphModule()
    root = cmds.columnLayout(adjustableColumn=True, parent=parent)
    if label:
        cmds.text(label=label, align="left", parent=root)

    # Preserve caller callback and mark the shape Custom when manually edited.
    # Preset application uses a guard to avoid changing the dropdown mid-update.
    handle = {"_preset_applying": False}

    def graph_changed(points):
        if not handle.get("_preset_applying") and "preset_menu" in handle:
            cmds.optionMenu(handle["preset_menu"], edit=True, value="Custom")
        if onChange:
            onChange(points)

    graph = Graph.CreateGraph(
        points=points, mode=mode, width=width, height=height,
        on_change=graph_changed
    )
    widget = graph["widget"]
    handle.update({
        "_nlta_type": "curveGraph",
        "root": root,
        "graph": graph,
        "widget": widget,
    })

    try:
        _AddCurveWidgetToMayaLayout(widget, root)
    except Exception:
        cmds.deleteUI(root)
        raise

    if controls:
        CreateCurveGraphControlsUI(handle)
    return handle


def GetCurveGraphUI(handle, *args):
    """Return JSON-serializable points, mode and Bezier tangents."""
    return _CurveGraphModule().GetData(handle["graph"])


def SetCurveGraphUI(handle, value, *args):
    """Set a curve from GetCurveGraphUI() data OR a list of [x,y] points."""
    Graph = _CurveGraphModule()
    if isinstance(value, dict):
        Graph.SetData(value, handle["graph"])
    elif isinstance(value, (list, tuple)):
        Graph.SetPoints(value, handle["graph"])
    else:
        raise TypeError("Curve graph value must be graph data or point pairs")


def GetCurveGraphValue(handle, ratio):
    """Sample the curve at X in [0, 1], returning Y in [0, 1]."""
    return _CurveGraphModule().GetValue(ratio, handle["graph"])


def AddCurveGraphPoint(handle, x=None, y=None, *args):
    """Add an interpolated key in the widest free X interval by default."""
    Graph = _CurveGraphModule()
    points = Graph.GetPoints(handle["graph"])
    if x is None:
        start, end = max(zip(points, points[1:]),
                         key=lambda pair: pair[1][0] - pair[0][0])
        x = (start[0] + end[0]) * 0.5
    if y is None:
        y = Graph.GetValue(x, handle["graph"])
    return Graph.AddPoint(x, y, handle["graph"])


def RemoveCurveGraphPoint(handle, *args):
    Graph = _CurveGraphModule()
    return Graph.RemovePoint(handle["graph"].get("selected", 0), handle["graph"])


def SetCurveGraphTangent(handle, mode, *args):
    """For the selected key: mode = 'auto', 'flat', 'linear', 'free'."""
    return _CurveGraphModule().SetTangentMode(mode, handle["graph"])


def ToggleCurveGraphBreak(handle, *args):
    Graph = _CurveGraphModule()
    graph = handle["graph"]
    selected = graph.get("selected", 0)
    broken = Graph.GetTangents(graph)[selected]["broken"]
    return Graph.BreakTangents(selected, not broken, graph)


def SetCurveGraphPreset(handle, preset, *args):
    """Apply a fresh curve preset, independent of previous reverse clicks."""
    Graph = _CurveGraphModule()
    handle["_preset_applying"] = True
    try:
        return Graph.SetPreset(preset, handle["graph"])
    finally:
        handle["_preset_applying"] = False


def FlipCurveGraphX(handle, *args):
    """Flip around the graph's vertical center (X -> 1-X)."""
    return _CurveGraphModule().FlipX(handle["graph"])


def FlipCurveGraphY(handle, *args):
    """Reflect values around Y=.5; separate from negative legacy animCurve Y."""
    return _CurveGraphModule().FlipY(handle["graph"])


def _CurvePresetPicked(handle, label, *args):
    if label != "Custom":
        SetCurveGraphPreset(handle, dict(_CurveGraphModule().PresetNames())[label])


def ReverseCurveGraph(handle, *args):
    """One-shot horizontal reflection, including weighted in/out tangents."""
    handle["_preset_applying"] = True
    try:
        result = _CurveGraphModule().FlipX(handle["graph"])
        if "preset_menu" in handle:
            cmds.optionMenu(handle["preset_menu"], edit=True, value="Custom")
        return result
    finally:
        handle["_preset_applying"] = False


def CreateCurveGraphControlsUI(handle, *args):
    """Compact controls: Shape dropdown, one-shot Reverse button, Add key.

    Right-click a key for Auto/Flat/Linear/Free Tangents, Break/Link, Delete.
    """
    if "controls" in handle:
        return handle["controls"]
    root = handle["root"]
    row = cmds.rowLayout(numberOfColumns=3, adjustableColumn=1, parent=root,
                         columnWidth=[(2, 90), (3, 70)])
    menu = cmds.optionMenu(label="Shape", parent=row,
                           changeCommand=lambda value: _CurvePresetPicked(handle, value))
    handle["preset_menu"] = menu
    cmds.menuItem(label="Custom", parent=menu)
    for label, _ in _CurveGraphModule().PresetNames():
        cmds.menuItem(label=label, parent=menu)
    cmds.optionMenu(menu, edit=True,
                    value="Custom" if len(handle["graph"]["points"]) != 2 else "Linear")
    handle["reverse_button"] = cmds.button(label="Reverse", parent=row,
                            command=lambda *_: ReverseCurveGraph(handle))
    cmds.button(label="+ Key", command=lambda *_: AddCurveGraphPoint(handle), parent=row)
    handle["controls"] = row
    return row


def TestCurveGraphUI(*args):
    """Standalone Maya test window showing NLTA_UI integration and JSON IO."""
    window = "NLTA_GraphUITest"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    window = cmds.window(window, title="NLTA UI - Curve Graph Test",
                         widthHeight=(470, 365), sizeable=True)
    column = cmds.columnLayout(adjustableColumn=True, rowSpacing=6, parent=window)
    graph = CreateCurveGraphUI(column, label="Bezier 0..1 — right-click point for tangent / delete",
                               width=435, height=220, controls=True)

    def print_data(*_):
        print("Graph data:", GetUIValue(graph))
        print("GetCurveGraphValue(0.5):", GetCurveGraphValue(graph, 0.5))

    cmds.button(label="Print Graph Data / Value at 0.5", parent=column,
                command=print_data)
    cmds.showWindow(window)
    return graph
