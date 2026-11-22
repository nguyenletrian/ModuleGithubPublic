# -*- coding: utf-8 -*-
"""Scene Pattern: Rivet, with standalone Python export.

Export Py saves UI data to JSON and exports Python_<module_name>.py
alongside the JSON. Right-click Export Py > Open Folder.
"""
import os
import importlib
import inspect
import pprint
import re
import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel
from functools import partial
from datetime import datetime

import NLTA_General, NLTA_UI
for module in (NLTA_General, NLTA_UI):
    importlib.reload(module)

ITEMS = {"items": {}, "order": []}


def _create_rivet_plane(vertex_names, plane_name):
    """Create a rivet plane at the source vertices' exact world positions."""
    components = []
    for vertex in vertex_names:
        found = cmds.ls(vertex, long=True, flatten=True) or []
        if len(found) != 1:
            raise ValueError("Cannot resolve exactly one vertex: {}".format(vertex))
        components.append(found[0])

    if len(components) < 3:
        raise ValueError("Rivet plane requires at least 3 vertices")

    parsed = []
    for component in components:
        match = re.match(r"^(.+)\.vtx\[(\d+)\]$", component)
        if not match:
            raise ValueError("Expected polygon vertex, got: {}".format(component))
        parsed.append((match.group(1), int(match.group(2))))

    mesh = parsed[0][0]
    if any(source != mesh for source, _ in parsed):
        raise ValueError("Rivet vertices must belong to the same mesh")
    vertex_ids = [index for _, index in parsed]
    if len(set(vertex_ids)) != len(vertex_ids):
        raise ValueError("Rivet vertex list contains duplicates")

    shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
    if len(shapes) != 1:
        raise ValueError("Expected one visible mesh shape under: {}".format(mesh))

    selection = om.MSelectionList()
    selection.add(shapes[0])
    source_dag = selection.getDagPath(0)
    original_points = om.MFnMesh(source_dag).getPoints(om.MSpace.kWorld)
    positions = [original_points[index] for index in vertex_ids]

    # Create the rivet plane using Maya's internal world-space units.
    new_object = om.MFnMesh().create(positions, [len(positions)], list(range(len(positions))))
    plane = cmds.rename(om.MFnDagNode(new_object).fullPathName(), plane_name)

    new_shapes = cmds.listRelatives(plane, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
    if len(new_shapes) != 1:
        cmds.delete(plane)
        raise RuntimeError("Cannot find newly created rivet plane mesh shape")

    new_selection = om.MSelectionList()
    new_selection.add(new_shapes[0])
    created_points = om.MFnMesh(new_selection.getDagPath(0)).getPoints(om.MSpace.kWorld)

    # Verify the new plane matches the original vertex positions.
    max_error_cm = max((a - b).length() for a, b in zip(positions, created_points))
    if max_error_cm > 0.0001:
        cmds.delete(plane)
        raise RuntimeError("Plane does not match source vertices (max error {:.6f} cm)".format(max_error_cm))

    return plane, new_shapes[0]


def _follow_mode(info):
    """Resolve one checked follow type; old Rivet JSON defaults to Parent."""
    keys = (("parent", "followParent"), ("position", "followPosition"),
            ("rotation", "followRotation"), ("matrixdelta", "followMatrixDelta"))
    present = [key for _, key in keys if key in info]
    if present:
        for key in present:
            if not isinstance(info[key], bool):
                raise ValueError("RigRivet: {} must be a checkbox boolean".format(key))
        chosen = [mode for mode, key in keys if info.get(key, False)]
        if len(chosen) != 1:
            raise ValueError("RigRivet: select exactly one follow type "
                             "(Parent, Position, Rotation, Matrix Delta)")
        return chosen[0]
    mode = str(info.get("followMode", "parent")).strip().lower()
    if mode not in ("parent", "position", "rotation", "matrixdelta"):
        raise ValueError("RigRivet: invalid follow type: " + mode)
    return mode


def _connect_rivet_follow(locator, offset, child, name, follow_mode="parent"):
    """Blend only the requested rivet channels with rest via AutoFollow."""
    if follow_mode not in ("parent", "position", "rotation"):
        raise ValueError("RigRivet: unsupported follow mode " + str(follow_mode))
    parents = cmds.listRelatives(offset, parent=True, fullPath=True) or []
    rest_name = child.rsplit("|", 1)[-1].replace(":", "_") + "_RivetRest"
    if cmds.objExists(rest_name):
        raise RuntimeError("Rivet rest transform already exists: " + rest_name)
    rest = cmds.createNode("transform", name=rest_name, parent=parents[0]) if parents else cmds.createNode("transform", name=rest_name)
    bind_matrix = cmds.xform(offset, query=True, worldSpace=True, matrix=True)
    cmds.xform(rest, worldSpace=True, matrix=bind_matrix)

    # Stage: Keep the Rivet's bind offset inside the offset parent's scale space.
    # A world-space parentConstraint maintainOffset does not scale its saved
    # translation offset when the global rig scale changes.
    follow_name = name + "_FollowSpace"
    follow_space = (cmds.createNode("transform", name=follow_name, parent=parents[0])
                    if parents else cmds.createNode("transform", name=follow_name))
    cmds.parentConstraint(locator, follow_space, maintainOffset=False)
    follow_target = cmds.createNode("transform", name=name + "_FollowTarget",
                                   parent=follow_space)
    cmds.xform(follow_target, worldSpace=True, matrix=bind_matrix)

    if not cmds.attributeQuery("AutoFollow", node=child, exists=True):
        cmds.addAttr(child, longName="AutoFollow", attributeType="double", min=0, max=1, defaultValue=1, keyable=True)

    # Stage: Both target and rest match bind pose; drive only chosen channels.
    # Parent keeps the original translate + rotate behavior. Position leaves
    # rotation untouched, and Rotation leaves translation untouched.
    if follow_mode == "parent":
        constraint_type = cmds.parentConstraint
    elif follow_mode == "position":
        constraint_type = cmds.pointConstraint
    else:
        constraint_type = cmds.orientConstraint
    constraint = constraint_type(follow_target, rest, offset, maintainOffset=False)[0]
    weights = constraint_type(constraint, query=True, weightAliasList=True) or []
    if len(weights) != 2:
        raise RuntimeError("Expected locator and rest weights on " + constraint)

    reverse = cmds.createNode("reverse", name=name + "_RestWeightReverse")
    cmds.connectAttr(child + ".AutoFollow", constraint + "." + weights[0], force=True)
    cmds.connectAttr(child + ".AutoFollow", reverse + ".inputX", force=True)
    cmds.connectAttr(reverse + ".outputX", constraint + "." + weights[1], force=True)
    return constraint, rest


def _connect_rivet_matrix_delta(locator, child, name, delta_space="", offset_name=""):
    """Bind-relative Rivet motion in the FK parent's current local space.

    Full row-vector matrix:
        D = ParentNow * RestNow.inverse * RivetNow * ParentNow.inverse
    RestNow is the Rivet bind frame, optionally following Delta Space.
    The new Delta group starts identity, so existing Child FK channels stay
    completely unchanged. Use a space sharing the rivet's normal rigid motion
    (e.g. the rig World control), never the FK child being driven.
    """
    original = list(dict.fromkeys(cmds.ls(child, long=True, type="transform") or []))
    if len(original) != 1:
        raise ValueError("RigRivet Matrix Delta: Child is missing/ambiguous: " + child)
    original = original[0]
    ancestor = (cmds.listRelatives(original, parent=True, fullPath=True) or [None])[0]
    space = None
    if delta_space:
        matches = list(dict.fromkeys(cmds.ls(delta_space, long=True, type="transform") or []))
        if len(matches) != 1:
            raise ValueError("RigRivet Matrix Delta: Delta Space is missing/ambiguous: " + delta_space)
        space = matches[0]
        if space == original or space.startswith(original + "|"):
            raise ValueError("RigRivet Matrix Delta: Delta Space cannot be the driven Child or descendant")
    if not cmds.getAttr(original + ".inheritsTransform"):
        raise ValueError("RigRivet Matrix Delta: Child inheritsTransform must be enabled")
    rest_name = name + "_DeltaRest"
    matrix_name = name + "_Delta_MM"
    blend_name = name + "_Delta_BM"
    offset_name = offset_name or original.rsplit("|", 1)[-1].replace(":", "_") + "_RivetDelta_GRP"
    for saved in (rest_name, offset_name, matrix_name, blend_name):
        if cmds.objExists(saved):
            raise RuntimeError("RigRivet Matrix Delta already exists: " + saved)
    def world(node):
        return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))
    def close(a, b):
        return max(abs(float(x) - float(y)) for x, y in zip(a, b)) < 1e-4
    child_bind = world(original)
    loc_bind = world(locator)
    parent_bind = world(ancestor) if ancestor else om.MMatrix()
    for label, matrix in (("Child", child_bind), ("Rivet", loc_bind), ("Parent", parent_bind)):
        if abs(matrix.det4x4()) < 1e-10:
            raise ValueError("RigRivet Matrix Delta: singular " + label + " matrix")

    # Rest follows only Delta Space, independent of the Child FK and Delta rig.
    rest = (cmds.createNode("transform", name=rest_name, parent=space)
            if space else cmds.createNode("transform", name=rest_name))
    cmds.xform(rest, worldSpace=True, matrix=list(loc_bind))
    cmds.setAttr(rest + ".visibility", 0)

    # The neutral offset is identity in its DAG parent, not matched to Child.
    # Relative parenting keeps Child's keyed translate/rotate/scale unchanged.
    delta = (cmds.createNode("transform", name=offset_name, parent=ancestor)
             if ancestor else cmds.createNode("transform", name=offset_name))
    child_new = cmds.parent(original, delta, relative=True)[0]
    child_new = (cmds.ls(child_new, long=True, type="transform") or [child_new])[0]
    if not close(world(child_new), child_bind):
        raise RuntimeError("RigRivet Matrix Delta: Child moved when inserting offset: " + child_new)

    if not cmds.attributeQuery("AutoFollow", node=child_new, exists=True):
        cmds.addAttr(child_new, longName="AutoFollow", attributeType="double",
                     min=0, max=1, defaultValue=1, keyable=True)

    # Maya row-vector order. The true parent is evaluated live, so moving Head
    # never needs an inverse of a moving MatrixFollow group as a reference.
    matrix = cmds.createNode("multMatrix", name=matrix_name)
    if ancestor:
        cmds.connectAttr(ancestor + ".worldMatrix[0]", matrix + ".matrixIn[0]")
    cmds.connectAttr(rest + ".worldInverseMatrix[0]", matrix + ".matrixIn[1]")
    cmds.connectAttr(locator + ".worldMatrix[0]", matrix + ".matrixIn[2]")
    if ancestor:
        cmds.connectAttr(ancestor + ".worldInverseMatrix[0]", matrix + ".matrixIn[3]")

    blend = cmds.createNode("blendMatrix", name=blend_name)
    cmds.connectAttr(matrix + ".matrixSum", blend + ".target[0].targetMatrix")
    cmds.connectAttr(child_new + ".AutoFollow", blend + ".target[0].weight")
    cmds.connectAttr(blend + ".outputMatrix", delta + ".offsetParentMatrix")
    if not close(world(child_new), child_bind):
        raise RuntimeError("RigRivet Matrix Delta: bind pose changed when wiring: " + child_new)
    return delta, rest, matrix, blend


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


def _data_path(data):
    newestData = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]
    })
    if not newestData or not newestData.get("path"):
        raise ValueError("RigRivet: cannot find JSON data path in ScenePatternData.json")
    return os.path.normpath(newestData["path"])


def Load(data, listUI, *arr):
    path = _data_path(data)
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
        folder = os.path.dirname(_data_path(data))
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
        NLTA_General.writeJsonFile(_data_path(data), saveData)

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
    cmds.button(label="Run", width=90, c=partial(Run, data))
    exportBtn = cmds.button(label="Export Py", width=110, c=SaveAndExport)
    cmds.popupMenu(parent=exportBtn, button=3)
    cmds.menuItem(label="Open Folder", c=partial(OpenExportFolder, data))
    cmds.setParent("..")
    Load(data, listUI)


def _source_skin(mesh):
    # Use Maya's stock findRelatedSkinCluster MEL procedure.
    escaped = mesh.replace('\\', '\\\\').replace('"', '\\"')
    skin = mel.eval('findRelatedSkinCluster "{}"'.format(escaped))
    return skin if skin and cmds.objExists(skin) else None

def _mesh_shape(mesh):
    if cmds.nodeType(mesh) == 'mesh':
        return mesh
    shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True, type='mesh') or []
    if len(shapes) != 1:
        raise ValueError('Expected one mesh shape under {}'.format(mesh))
    return shapes[0]


def _offset_group(child, name):
    # Preserve the child's world pose while inserting its offset group.
    world_matrix = cmds.xform(child, query=True, worldSpace=True, matrix=True)
    parents = cmds.listRelatives(child, parent=True, fullPath=True) or []
    offset = cmds.createNode('transform', name=name)
    if parents:
        offset = cmds.parent(offset, parents[0])[0]
    cmds.xform(offset, worldSpace=True, matrix=world_matrix)
    cmds.parent(child, offset, absolute=True)
    return offset



def _create_rivet(info):
    vertex_lines = [str(line).strip() for line in str(info.get('vertexs') or '').splitlines() if str(line).strip()]
    vertices = cmds.ls(vertex_lines, flatten=True, long=True) or []
    if len(vertices) < 3:
        raise ValueError('At least 3 existing vertices are required')
    if len(set(vertices)) != len(vertices):
        raise ValueError('Duplicate vertices in rivet input')
    if any('.vtx[' not in v for v in vertices):
        raise ValueError('Only mesh vertex components are supported')

    mesh = vertices[0].split('.vtx[', 1)[0]
    if any(v.split('.vtx[', 1)[0] != mesh for v in vertices):
        raise ValueError('All vertices in a rivet must be from one mesh')
    _mesh_shape(mesh)

    child = str(info.get('child') or '').strip()
    parent = str(info.get('parent') or '').strip()
    copy_transform = str(info.get('copyTransform') or '').strip()
    follow_mode = _follow_mode(info)
    delta_space = str(info.get("deltaSpace") or "").strip() if follow_mode == "matrixdelta" else ""
    if follow_mode == "matrixdelta" and not child:
        raise ValueError("RigRivet Matrix Delta requires a Child control")
    for obj in (child, parent, copy_transform, delta_space):
        if obj and not cmds.objExists(obj):
            raise ValueError('Missing Maya object: {}'.format(obj))

    # Use a short name for all rivet nodes.
    short_child = child.rsplit('|', 1)[-1].replace(':', '_')
    name = short_child + '_Rivet'  # Blank child matches original '_Rivet'.
    plane_name = name + '_Plane'
    loc_name = name + '_Loc'
    offset_name = short_child + ('_RivetDelta_GRP' if follow_mode == "matrixdelta" else '_RivetOffset')
    names_to_check = [plane_name, loc_name]
    if child:
        names_to_check.append(offset_name)
    for node in names_to_check:
        if cmds.objExists(node):
            raise RuntimeError('Rivet node already exists: {}'.format(node))

    # Create the one-face rivet plane.
    plane, plane_shape = _create_rivet_plane(vertices, plane_name)

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
    delta_matrix = None
    delta_blend = None
    # Old constraint types are unchanged. Matrix Delta creates a neutral
    # FK-local offset and only applies the Rivet movement relative to Rest.
    if child:
        if follow_mode == "matrixdelta":
            offset, rest, delta_matrix, delta_blend = _connect_rivet_matrix_delta(
                loc, child, name, delta_space, offset_name)
        else:
            offset = _offset_group(child, offset_name)
            constraint, rest = _connect_rivet_follow(
                loc, offset, child, name, follow_mode)

    # Transfer source skin weights to the rivet plane.
    skin = _source_skin(mesh)
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
    return {'plane': plane, 'locator': loc, 'offset': offset, 'constraint': constraint, 'rest': rest, 'copyTransform': matched_group, 'deltaMatrix': delta_matrix, 'deltaBlend': delta_blend, 'deltaSpace': delta_space, 'followMode': follow_mode}



def BuildRigRivet(datas):
    """Build the rivet networks using saved scene-pattern data."""
    # Create one rivet network for each saved item.
    created = []
    for info in datas:
        created.append(_create_rivet(info))
    return created


def ExportPython(data, *args):
    data_path = _data_path(data)
    rivet_data = NLTA_General.readJsonFile(data_path)
    if not isinstance(rivet_data, list) or not rivet_data:
        cmds.warning("RigRivet Export: no saved rivet items")
        return None

    import ast
    functions = (_create_rivet_plane, _source_skin, _mesh_shape, _offset_group,
                 _follow_mode, _connect_rivet_follow, _connect_rivet_matrix_delta,
                 _create_rivet, BuildRigRivet)
    tree = ast.parse("\n\n".join(inspect.getsource(fn).rstrip() for fn in functions))

    class ExportCode(ast.NodeTransformer):
        def visit_Raise(self, node):
            return None

        def visit_Assert(self, node):
            return None

        def visit_Try(self, node):
            self.generic_visit(node)
            return node.body + node.orelse + node.finalbody

        def visit_If(self, node):
            if any(isinstance(stmt, (ast.Raise, ast.Assert)) for stmt in node.body):
                self.generic_visit(node)
                return node.orelse
            self.generic_visit(node)
            return node if node.body else node.orelse

        def visit_For(self, node):
            self.generic_visit(node)
            return node if node.body else node.orelse or None

        def visit_While(self, node):
            self.generic_visit(node)
            return node if node.body else node.orelse

        def visit_Assign(self, node):
            if any(isinstance(target, ast.Name)
                   and target.id in ("new_selection", "created_points", "max_error_cm", "parent_bind")
                   for target in node.targets):
                return None
            return self.generic_visit(node)

        def visit_Expr(self, node):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return None
            if isinstance(value, ast.Call):
                fn = value.func
                if (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                        and fn.value.id == "cmds" and fn.attr == "warning"):
                    return None
                if (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                        and fn.value.id == "new_selection" and fn.attr == "add"):
                    return None
            return self.generic_visit(node)

        def visit_FunctionDef(self, node):
            if node.name == "close":
                return None
            self.generic_visit(node)
            if not node.body:
                node.body = [ast.Pass()]
            return node

    tree = ExportCode().visit(tree)
    ast.fix_missing_locations(tree)
    body = ast.unparse(tree)
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    saved = repr(rivet_data)
    source = (
        "def main():\n"
        "    import re\n"
        "    import maya.cmds as cmds\n"
        "    import maya.mel as mel\n"
        "    import maya.api.OpenMaya as om\n\n"
        "    RIVET_DATA = " + saved + "\n\n"
        + body + "\n\n"
        "    BuildRigRivet(RIVET_DATA)\n\n"
        'if __name__ == "__main__":\n    main()\n'
    )
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(data_path), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(source)
    return output


def Run(data, *args):
    """Build the saved rig using the standalone builder."""
    rivet_data = NLTA_General.readJsonFile(_data_path(data)) or []
    return BuildRigRivet(rivet_data)


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
    mode = _follow_mode(data)
    modes = (("parent", "Parent", "followParent"),
             ("position", "Position", "followPosition"),
             ("rotation", "Rotation", "followRotation"),
             ("matrixdelta", "Matrix Delta", "followMatrixDelta"))
    follow_controls = {}
    follow_row = cmds.rowColumnLayout(numberOfColumns=5,
                                     columnWidth=[(1, 80), (2, 68), (3, 75),
                                                  (4, 76), (5, 100)])
    cmds.text(label="Follow Type", align="left")
    for key, caption, json_key in modes:
        control = cmds.checkBox(label=caption, value=(mode == key))
        follow_controls[key] = control
        itemData[json_key] = control
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
    cmds.textField(text="Delta Space", editable=False)
    itemData["deltaSpace"] = cmds.textField(text=data.get("deltaSpace", ""))
    cmds.button(label="+", w=30, c=partial(NLTA_UI.PickObject, itemData["deltaSpace"]))
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