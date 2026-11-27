# -*- coding: utf-8 -*-
"""Scene Pattern: Rivet directly on an existing quad face, with standalone export.

Export Py saves UI data to JSON and exports Python_<module_name>.py
alongside the JSON. Right-click Export Py > Open Folder.
"""
import os
import importlib
import inspect
import maya.api.OpenMaya as om
import maya.cmds as cmds
from functools import partial
from datetime import datetime

import NLTA_General, NLTA_UI
for module in (NLTA_General, NLTA_UI):
    importlib.reload(module)

ITEMS = {"items": {}, "order": []}


def faceEdges(face):
    selection = om.MSelectionList()
    selection.add(face)
    dag, component = selection.getComponent(0)
    polygon = om.MItMeshPolygon(dag, component)
    return dag.fullPathName(), dag.instanceNumber(), polygon.getEdges()


def validateFace(face):
    faces = cmds.ls(face, flatten=True, long=True) or []
    if len(faces) != 1 or ".f[" not in faces[0]:
        raise ValueError("RigRivet From Face: pick exactly one polygon face.")
    if len(faceEdges(faces[0])[2]) != 4:
        raise ValueError("RigRivet From Face: pick a quad face (four edges).")
    return faces[0]


def pickFace(field, *args):
    selected = cmds.ls(selection=True, flatten=True, long=True) or []
    if len(selected) != 1:
        cmds.warning("RigRivet From Face: select one quad face.")
        return
    try:
        face = validateFace(selected[0])
    except (ValueError, RuntimeError) as exc:
        cmds.warning(str(exc))
        return
    cmds.textField(field, edit=True, text=face)


def followMode(info):
    """Resolve one checked follow type; old Rivet JSON defaults to Parent."""
    keys = (("parent", "followParent"), ("position", "followPosition"),
            ("rotation", "followRotation"))
    if (info.get("followMatrixDelta") or str(info.get("followMode", "")).strip().lower() == "matrixdelta") and not any(info.get(key, False) for _, key in keys):
        return "parent"
    present = [key for _, key in keys if key in info]
    if present:
        for key in present:
            if not isinstance(info[key], bool):
                raise ValueError("RigRivet From Face: {} must be a checkbox boolean".format(key))
        chosen = [mode for mode, key in keys if info.get(key, False)]
        if len(chosen) != 1:
            raise ValueError("RigRivet From Face: select exactly one follow type "
                             "(Parent, Position, Rotation)")
        return chosen[0]
    mode = str(info.get("followMode", "parent")).strip().lower()
    if mode not in ("parent", "position", "rotation"):
        raise ValueError("RigRivet From Face: invalid follow type: " + mode)
    return mode


def connectRivetFollow(locator, offset, child, name, constraintCommand):
    # Blend the rivet and rest with AutoFollow.
    parents = cmds.listRelatives(offset, parent=True, fullPath=True) or []
    rest_name = child.rsplit("|", 1)[-1].replace(":", "_") + "_RivetRest"
    rest = cmds.createNode("transform", name=rest_name, parent=parents[0]) if parents else cmds.createNode("transform", name=rest_name)
    bind_matrix = cmds.xform(offset, query=True, worldSpace=True, matrix=True)
    cmds.xform(rest, worldSpace=True, matrix=bind_matrix)

    # Keep the bind offset in the parent scale space.
    follow_name = name + "_FollowSpace"
    follow_space = (cmds.createNode("transform", name=follow_name, parent=parents[0])
                    if parents else cmds.createNode("transform", name=follow_name))
    cmds.parentConstraint(locator, follow_space, maintainOffset=False)
    follow_target = cmds.createNode("transform", name=name + "_FollowTarget",
                                   parent=follow_space)
    cmds.xform(follow_target, worldSpace=True, matrix=bind_matrix)

    if not cmds.attributeQuery("AutoFollow", node=child, exists=True):
        cmds.addAttr(child, longName="AutoFollow", attributeType="double", min=0, max=1, defaultValue=1, keyable=True)

    constraint = constraintCommand(follow_target, rest, offset, maintainOffset=False)[0]
    weights = constraintCommand(constraint, query=True, weightAliasList=True)

    reverse = cmds.createNode("reverse", name=name + "_RestWeightReverse")
    cmds.connectAttr(child + ".AutoFollow", constraint + "." + weights[0], force=True)
    cmds.connectAttr(child + ".AutoFollow", reverse + ".inputX", force=True)
    cmds.connectAttr(reverse + ".outputX", constraint + "." + weights[1], force=True)
    return constraint, rest


def DefaultSetting(path, *arr):
    moduleName = os.path.basename(__file__).replace(".py", "")
    ext = "json"
    name = "Rig Rivet From Face"
    return {
        "ext": ext,
        "path": path + moduleName + "." + ext,
        "moduleName": moduleName,
        "order": 0,
        "title": name,
        "name": name,
        "id": datetime.now().strftime("%Y%m%d%H%M%S")
    }


def dataPath(data):
    newestData = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]
    })
    if not newestData or not newestData.get("path"):
        raise ValueError("RigRivet From Face: cannot find JSON data path in ScenePatternData.json")
    return os.path.normpath(newestData["path"])


def Load(data, listUI, *arr):
    ITEMS["items"].clear()
    ITEMS["order"].clear()
    path = dataPath(data)
    children = cmds.layout(listUI, q=True, ca=True) or []
    for child in children:
        if cmds.control(child, exists=True):
            cmds.deleteUI(child)
    itemDatas = NLTA_General.readJsonFile(path)
    if itemDatas:
        for item in itemDatas:
            Add(listUI, item)


def OpenExportFolder(data, *args):
    try:
        folder = os.path.dirname(dataPath(data))
    except Exception as exc:
        cmds.warning(str(exc))
        return
    if os.path.isdir(folder):
        os.startfile(folder)  # Windows Explorer, consistent with CreateProxy.
    else:
        cmds.warning("RigRivet From Face: folder does not exist: " + folder)


def Form(data, *args):
    def Save(data, *args):
        saveData = NLTA_UI.GetData(ITEMS["items"])
        NLTA_General.writeJsonFile(dataPath(data), saveData)

    def SaveAndExport(*args):
        Save(data)
        ExportPython(data)

    mainForm = NLTA_General.LoadModule("Scene_Form")
    dataBack = mainForm.Create(data)
    buttonUI = dataBack["buttonUI"]
    listUI = dataBack["listUI"]

    cmds.rowColumnLayout(numberOfColumns=4, parent=buttonUI)
    cmds.button(label="Add", width=90, c=partial(Add, listUI, {}))
    cmds.button(label="Save", width=90, c=partial(Save, data))
    cmds.button(label="Run", width=90, c=lambda *unused: (Save(data), Run(data)))
    exportBtn = cmds.button(label="Export Py", width=110, c=SaveAndExport)
    cmds.popupMenu(parent=exportBtn, button=3)
    cmds.menuItem(label="Open Folder", c=partial(OpenExportFolder, data))
    cmds.setParent("..")
    Load(data, listUI)


def createRivet(face, child, parent, copy_transform, constraintCommand):
    mesh_shape, instance, edges = faceEdges(face)
    short_child = child.rsplit("|", 1)[-1].replace(":", "_") if child else face.rsplit("|", 1)[-1].replace(":", "_").replace(".f[", "_Face").replace("]", "")
    name = short_child + "_Rivet"
    loc_name = name + "_Loc"
    offset_name = short_child + "_RivetOffset"

    # Use opposite edges of the existing quad.
    cfme1 = cmds.createNode('curveFromMeshEdge', name=name + '_EdgeA')
    cfme2 = cmds.createNode('curveFromMeshEdge', name=name + '_EdgeB')
    loft = cmds.createNode('loft', name=name + '_Loft')
    posi = cmds.createNode('pointOnSurfaceInfo', name=name + '_POSI')
    cmds.setAttr(cfme1 + '.edgeIndex[0]', edges[0])
    cmds.setAttr(cfme2 + '.edgeIndex[0]', edges[2])
    cmds.setAttr(posi + '.turnOnPercentage', 1)
    cmds.setAttr(posi + '.parameterU', 0.5)
    cmds.setAttr(posi + '.parameterV', 0.5)
    cmds.connectAttr(mesh_shape + '.worldMesh[{}]'.format(instance), cfme1 + '.inputMesh')
    cmds.connectAttr(mesh_shape + '.worldMesh[{}]'.format(instance), cfme2 + '.inputMesh')
    cmds.connectAttr(cfme1 + '.outputCurve', loft + '.inputCurve[0]')
    cmds.connectAttr(cfme2 + '.outputCurve', loft + '.inputCurve[1]')
    cmds.connectAttr(loft + '.outputSurface', posi + '.inputSurface')

    loc = cmds.spaceLocator(name=loc_name)[0]
    # Drive the locator from the rivet surface.
    cmds.setAttr(loc + '.inheritsTransform', 0)
    if parent:
        loc = cmds.parent(loc, parent, absolute=True)[0]
    aim = cmds.createNode('aimConstraint', parent=loc, name=name + '_Aim')
    cmds.setAttr(aim + '.aimVector', 0, 1, 0, type='double3')
    cmds.setAttr(aim + '.upVector', 0, 0, 1, type='double3')
    cmds.connectAttr(posi + '.position', loc + '.translate')
    cmds.connectAttr(posi + '.normal', aim + '.target[0].targetTranslate')
    cmds.connectAttr(posi + '.tangentV', aim + '.worldUpVector')
    cmds.connectAttr(aim + '.constraintRotateX', loc + '.rotateX')
    cmds.connectAttr(aim + '.constraintRotateY', loc + '.rotateY')
    cmds.connectAttr(aim + '.constraintRotateZ', loc + '.rotateZ')

    matched_group = None
    if copy_transform:
        matched_group = cmds.group(empty=True, name=name + '_CopyTransform')
        matrix = cmds.xform(copy_transform, query=True, worldSpace=True, matrix=True)
        cmds.xform(matched_group, worldSpace=True, matrix=matrix)
        cmds.parent(matched_group, loc, absolute=True)

    offset = None
    constraint = None
    rest = None
    # Blend rivet motion and rest with AutoFollow.
    if child:
        # Preserve the child's world pose while inserting its offset group.
        world_matrix = cmds.xform(child, query=True, worldSpace=True, matrix=True)
        parents = cmds.listRelatives(child, parent=True, fullPath=True) or []
        offset = cmds.createNode('transform', name=offset_name)
        if parents:
            offset = cmds.parent(offset, parents[0])[0]
        cmds.xform(offset, worldSpace=True, matrix=world_matrix)
        child = cmds.parent(child, offset, absolute=True)[0]
        constraint, rest = connectRivetFollow(loc, offset, child, name, constraintCommand)

    cmds.setAttr(loc + '.visibility', 0)
    return {'face': face, 'locator': loc, 'offset': offset, 'constraint': constraint, 'rest': rest, 'copyTransform': matched_group}



def rivetArguments(info):
    face = str(info.get("face") or "").strip()
    child = str(info.get("child") or "").strip()
    parent = str(info.get("parent") or "").strip()
    copy_transform = str(info.get("copyTransform") or "").strip()
    command = {"parent": "parentConstraint", "position": "pointConstraint", "rotation": "orientConstraint"}[followMode(info)]
    return face, child, parent, copy_transform, command


def BuildRigRivet(datas):
    arguments = [rivetArguments(info) for info in datas]
    faces = [validateFace(face) for face, _, _, _, _ in arguments]
    commands = {"parentConstraint": cmds.parentConstraint, "pointConstraint": cmds.pointConstraint, "orientConstraint": cmds.orientConstraint}
    return [createRivet(face, child, parent, copy_transform, commands[command])
            for face, (_, child, parent, copy_transform, command) in zip(faces, arguments)]


def buildScript(datas):
    helpers = inspect.getsource(connectRivetFollow).rstrip().rsplit("\n", 1)[0]
    body = inspect.getsource(createRivet).split("\n", 1)[1].rstrip().rsplit("\n", 1)[0]
    faceBody = inspect.getsource(faceEdges).split("\n", 1)[1].rstrip()
    faceBody = faceBody.replace("return dag.fullPathName()", "mesh_shape, instance, edges = dag.fullPathName()")
    body = body.replace("    mesh_shape, instance, edges = faceEdges(face)", faceBody)
    for line in ("    matched_group = None", "    offset = None", "    constraint = None", "    rest = None"):
        body = body.replace(line + "\n", "")
    body = body.replace("constraint, rest = connectRivetFollow(", "connectRivetFollow(")
    data = ",\n".join("        " + repr(rivetArguments(info)) for info in datas)
    helpers = "\n".join("    " + line if line.strip() else "" for line in helpers.splitlines())
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    source = ("def main():\n    import maya.cmds as cmds\n    import maya.api.OpenMaya as om\n\n"
              + "    RIVET_DATA = [\n" + data + "\n    ]\n\n" + helpers + "\n\n"
              + '    commands = {"parentConstraint": cmds.parentConstraint, "pointConstraint": cmds.pointConstraint, "orientConstraint": cmds.orientConstraint}\n\n'
              + "    for face, child, parent, copy_transform, command in RIVET_DATA:\n"
              + "        constraintCommand = commands[command]\n" + body
              + '\n\nif __name__ == "__main__":\n    main()\n')
    compile(source, "Python_Scene_Pattern_RigRivetFromFace.py", "exec")
    return source


def ExportPython(data, *args):
    data_path = dataPath(data)
    datas = NLTA_General.readJsonFile(data_path) or []
    source = buildScript(datas)
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    output = os.path.join(os.path.dirname(data_path), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(source)
    return output


def Run(data, *args):
    return BuildRigRivet(NLTA_General.readJsonFile(dataPath(data)) or [])

def Add(listUI, data, *args):
    global ITEMS

    def Delete(ui, *args):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS["items"][ui]
        ITEMS["order"].remove(ui)

    itemData = {}
    itemUI = cmds.rowColumnLayout(
        numberOfColumns=1, parent=listUI, backgroundColor=(0.15, 0.15, 0.15)
    )
    cmds.rowColumnLayout(numberOfColumns=1)
    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 80), (2, 265), (3, 32)])
    cmds.textField(text="Face", editable=False)
    itemData["face"] = cmds.textField(text=data.get("face", ""))
    cmds.button(label="+", w=30, c=partial(pickFace, itemData["face"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 80), (2, 265), (3, 32)])
    cmds.textField(text="Child", editable=False)
    itemData["child"] = cmds.textField(text=data.get("child", ""))
    cmds.button(label="+", w=30, c=partial(NLTA_UI.PickObject, itemData["child"]))
    cmds.setParent("..")

    # A single exclusive checkbox controls which channels follow the rivet.
    # Parent is the default follow mode.
    mode = followMode(data)
    modes = (("parent", "Parent"), ("position", "Position"),
             ("rotation", "Rotation"))
    follow_controls = {}
    follow_row = cmds.rowColumnLayout(numberOfColumns=4,
                                     columnWidth=[(1, 80), (2, 100),
                                                  (3, 100), (4, 100)])
    cmds.text(label="Follow Type", align="left")
    for key, caption in modes:
        name = "follow" + caption
        control = cmds.checkBox(label=caption, value=(mode == key))
        follow_controls[key] = control
        itemData[name] = control
    def selectMode(chosen, *unused):
        for key, control in follow_controls.items():
            cmds.checkBox(control, edit=True, value=(key == chosen))
    for key, control in follow_controls.items():
        cmds.checkBox(control, edit=True, changeCommand=partial(selectMode, key))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 80), (2, 265), (3, 32)])
    cmds.textField(text="Contain", editable=False)
    itemData["parent"] = cmds.textField(text=data.get("parent", ""))
    cmds.button(label="+", w=30, c=partial(NLTA_UI.PickObject, itemData["parent"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 80), (2, 265), (3, 32)])
    cmds.textField(text="Copy Trans", editable=False)
    itemData["copyTransform"] = cmds.textField(text=data.get("copyTransform", ""))
    cmds.button(label="+", w=30, c=partial(NLTA_UI.PickObject, itemData["copyTransform"]))
    cmds.setParent("..")

    cmds.button(label="X", w=380, bgc=(0.5, 0.2, 0.2), c=partial(Delete, itemUI))
    cmds.setParent("..")
    cmds.setParent("..")

    ITEMS["items"][itemUI] = itemData
    ITEMS["order"].append(itemUI)