# -*- coding: utf-8 -*-
"""Scene Pattern: Rivet, with standalone Python export.

Export Py saves UI data to JSON and exports Python_<module_name>.py
alongside the JSON. Right-click Export Py > Open Folder.
"""
import os
import importlib
import inspect
import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel
from functools import partial
from datetime import datetime

import NLTA_General, NLTA_UI
for module in (NLTA_General, NLTA_UI):
    importlib.reload(module)

ITEMS = {"items": {}, "order": []}


def createRivetPlane(vertices, plane_name):
    mesh = vertices[0].split(".vtx[", 1)[0]
    vertex_ids = [int(vertex.rsplit("[", 1)[1][:-1]) for vertex in vertices]
    shape = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True, type="mesh")[0]
    selection = om.MSelectionList()
    selection.add(shape)
    points = om.MFnMesh(selection.getDagPath(0)).getPoints(om.MSpace.kWorld)
    positions = [points[index] for index in vertex_ids]
    new_object = om.MFnMesh().create(positions, [len(positions)], list(range(len(positions))))
    plane = cmds.rename(om.MFnDagNode(new_object).fullPathName(), plane_name)
    plane_shape = cmds.listRelatives(plane, shapes=True, noIntermediate=True, fullPath=True, type="mesh")[0]
    return plane, plane_shape

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
                raise ValueError("RigRivet: {} must be a checkbox boolean".format(key))
        chosen = [mode for mode, key in keys if info.get(key, False)]
        if len(chosen) != 1:
            raise ValueError("RigRivet: select exactly one follow type "
                             "(Parent, Position, Rotation)")
        return chosen[0]
    mode = str(info.get("followMode", "parent")).strip().lower()
    if mode not in ("parent", "position", "rotation"):
        raise ValueError("RigRivet: invalid follow type: " + mode)
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
    name = "Rivet"
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
        raise ValueError("RigRivet: cannot find JSON data path in ScenePatternData.json")
    return os.path.normpath(newestData["path"])


def Load(data, listUI, *arr):
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
        cmds.warning("RigRivet: folder does not exist: " + folder)


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


def sourceSkin(mesh):
    # Use Maya's stock findRelatedSkinCluster MEL procedure.
    escaped = mesh.replace('\\', '\\\\').replace('"', '\\"')
    skin = mel.eval('findRelatedSkinCluster "{}"'.format(escaped))
    return skin

def offsetGroup(child, name):
    # Preserve the child's world pose while inserting its offset group.
    world_matrix = cmds.xform(child, query=True, worldSpace=True, matrix=True)
    parents = cmds.listRelatives(child, parent=True, fullPath=True) or []
    offset = cmds.createNode('transform', name=name)
    if parents:
        offset = cmds.parent(offset, parents[0])[0]
    cmds.xform(offset, worldSpace=True, matrix=world_matrix)
    cmds.parent(child, offset, absolute=True)
    return offset



def createRivet(vertex_names, child, parent, copy_transform, constraintCommand):
    vertices = cmds.ls(vertex_names, flatten=True, long=True)
    mesh = vertices[0].split(".vtx[", 1)[0]
    short_child = child.rsplit("|", 1)[-1].replace(":", "_")
    name = short_child + "_Rivet"
    plane_name = name + "_Plane"
    loc_name = name + "_Loc"
    offset_name = short_child + "_RivetOffset"

    # Create the one-face rivet plane.
    plane, plane_shape = createRivetPlane(vertices, plane_name)

    # Build a live surface from the rivet plane edges.
    cfme1 = cmds.createNode('curveFromMeshEdge', name=name + '_EdgeA')
    cfme2 = cmds.createNode('curveFromMeshEdge', name=name + '_EdgeB')
    loft = cmds.createNode('loft', name=name + '_Loft')
    posi = cmds.createNode('pointOnSurfaceInfo', name=name + '_POSI')
    cmds.setAttr(cfme1 + '.edgeIndex[0]', 0)
    cmds.setAttr(cfme2 + '.edgeIndex[0]', 2)
    cmds.setAttr(posi + '.turnOnPercentage', 1)
    cmds.setAttr(posi + '.parameterU', 0.5)
    cmds.setAttr(posi + '.parameterV', 0.5)
    cmds.connectAttr(plane_shape + '.worldMesh[0]', cfme1 + '.inputMesh')
    cmds.connectAttr(plane_shape + '.worldMesh[0]', cfme2 + '.inputMesh')
    cmds.connectAttr(cfme1 + '.outputCurve', loft + '.inputCurve[0]')
    cmds.connectAttr(cfme2 + '.outputCurve', loft + '.inputCurve[1]')
    cmds.connectAttr(loft + '.outputSurface', posi + '.inputSurface')

    loc = cmds.spaceLocator(name=loc_name)[0]
    # Drive the locator from the rivet surface.
    cmds.setAttr(loc + '.inheritsTransform', 0)
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
        offset = offsetGroup(child, offset_name)
        constraint, rest = connectRivetFollow(loc, offset, child, name, constraintCommand)

    # Transfer source skin weights to the rivet plane.
    skin = sourceSkin(mesh)
    if skin:
        # Skin history already follows rig joints; do not inherit the parent
        # group's transform again when the surface is parented below it.
        cmds.setAttr(plane + '.inheritsTransform', 0)
        joints = cmds.skinCluster(skin, query=True, influence=True) or []
        if joints:
            plane_skin = cmds.skinCluster(joints, plane, toSelectedBones=True, normalizeWeights=1, name=name + '_SkinCluster')[0]
            cmds.copySkinWeights(sourceSkin=skin, destinationSkin=plane_skin, noMirror=True, surfaceAssociation='closestPoint', influenceAssociation='oneToOne')


    if parent:
        cmds.parent([plane, loc], parent, absolute=True)
    cmds.setAttr(plane + '.visibility', 0)
    cmds.setAttr(loc + '.visibility', 0)
    return {'plane': plane, 'locator': loc, 'offset': offset, 'constraint': constraint, 'rest': rest, 'copyTransform': matched_group}



def rivetArguments(info):
    vertices = [line.strip() for line in str(info.get("vertexs") or "").splitlines() if line.strip()]
    child = str(info.get("child") or "").strip()
    parent = str(info.get("parent") or "").strip()
    copy_transform = str(info.get("copyTransform") or "").strip()
    command = {"parent": "parentConstraint", "position": "pointConstraint", "rotation": "orientConstraint"}[followMode(info)]
    return vertices, child, parent, copy_transform, command


def BuildRigRivet(datas):
    created = []
    for info in datas:
        vertices, child, parent, copy_transform, command = rivetArguments(info)
        created.append(createRivet(vertices, child, parent, copy_transform, getattr(cmds, command)))
    return created


def buildScript(datas):
    functions = (createRivetPlane, sourceSkin, offsetGroup, connectRivetFollow, createRivet)
    builders = "\n\n".join(inspect.getsource(fn).rstrip() for fn in functions)
    calls = []
    for info in datas:
        vertices, child, parent, copy_transform, command = rivetArguments(info)
        calls.append("    createRivet({!r}, {!r}, {!r}, {!r}, cmds.{})".format(vertices, child, parent, copy_transform, command))
    source = (
        "import maya.cmds as cmds\nimport maya.mel as mel\nimport maya.api.OpenMaya as om\n\n"
        + builders + "\n\ndef main():\n"
        + ("\n".join(calls) or "    pass")
        + '\n\nif __name__ == "__main__":\n    main()\n'
    )
    compile(source, "Python_Scene_Pattern_RigRivet.py", "exec")
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
    cmds.textField(text="Vertexs", editable=False)
    itemData["vertexs"] = cmds.scrollField(text=data.get("vertexs", ""), h=80)
    cmds.button(label="+", w=30, c=partial(NLTA_UI.PickObject, itemData["vertexs"]))
    cmds.setParent("..")

    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 80), (2, 265), (3, 32)])
    cmds.textField(text="Child", editable=False)
    itemData["child"] = cmds.textField(text=data.get("child", ""))
    cmds.button(label="+", w=30, c=partial(NLTA_UI.PickObject, itemData["child"]))
    cmds.setParent("..")

    # A single exclusive checkbox controls which channels follow the rivet.
    # Legacy JSON without these fields stays on Parent, matching old rigs.
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
    def select_mode(chosen, *unused):
        for key, control in follow_controls.items():
            cmds.checkBox(control, edit=True, value=(key == chosen))
    for key, control in follow_controls.items():
        cmds.checkBox(control, edit=True, changeCommand=partial(select_mode, key))
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