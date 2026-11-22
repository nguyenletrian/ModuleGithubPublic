# -*- coding: utf-8 -*-
import os
import json
import inspect
import pprint
import maya.cmds as cmds
import maya.mel as mel
from functools import partial
from datetime import datetime

import NLTA_General, NLTA_UI
for module in [NLTA_General, NLTA_UI]:
    try:
        import importlib
        importlib.reload(module)
    except Exception:
        from importlib import reload
        reload(module)

ITEMS = {"items": {}, "order": []}


def DefaultSetting(path, *arr):
    moduleName = os.path.basename(__file__).replace('.py', '')
    ext = 'json'
    name = 'Create Proxy'
    return {
        'ext': ext,
        'path': path + moduleName + '.' + ext,
        'moduleName': moduleName,
        'order': 0,
        'title': name,
        'name': name,
        'id': datetime.now().strftime('%Y%m%d%H%M%S')
    }


def Load(data, listUI, *arr):
    newestData = NLTA_General.JsonGetByID({
        'path': data['sceneDataPath'] + '/ScenePatternData.json',
        'id': data['id']
    })
    path = newestData['path']
    if '.json' in path:
        children = cmds.layout(listUI, q=True, ca=True) or []
        for child in children:
            if cmds.control(child, exists=True):
                cmds.deleteUI(child)
        itemDatas = NLTA_General.readJsonFile(path)
        if itemDatas:
            for item in itemDatas:
                Add(listUI, item)


def Form(data, *arr):
    def Save(data, *arr):
        itemData = NLTA_General.JsonGetByID({
            'path': data['sceneDataPath'] + '/ScenePatternData.json',
            'id': data['id']
        })
        returnData = NLTA_UI.GetData(ITEMS['items'])
        NLTA_General.writeJsonFile(itemData['path'], returnData)

    def SaveAndExport(*arr):
        Save(data)
        ExportPython(data)

    def OpenExportFolder(data, *args):
        newestData = NLTA_General.JsonGetByID({
            "path": data["sceneDataPath"] + "/ScenePatternData.json",
            "id": data["id"]
        })

        if not newestData or not newestData.get("path"):
            cmds.warning("Data path not found!")
            return

        folder = os.path.dirname(os.path.normpath(newestData["path"]))

        if os.path.isdir(folder):
            os.startfile(folder)
        else:
            cmds.warning("Folder does not exist: " + folder)

    mainForm = NLTA_General.LoadModule('Scene_Form')
    dataBack = mainForm.Create(data)
    buttonUI = dataBack['buttonUI']
    listUI = dataBack['listUI']

    cmds.rowColumnLayout(numberOfColumns=4, parent=buttonUI)
    cmds.button(label='Add', width=90, c=partial(Add, listUI, {}))
    cmds.button(label='Save', width=90, c=partial(Save, data))
    cmds.button(label='Run', width=90, c=partial(Run, data))
    exportBtn = cmds.button(label="Export Py",width=110,c=SaveAndExport)
    cmds.popupMenu(parent=exportBtn,button=3)
    cmds.menuItem(label="Open Folder",c=partial(OpenExportFolder, data))
    cmds.setParent('..')
    Load(data, listUI)


def _proxy_source_skin(mesh):
    escaped = str(mesh).replace("\\", "\\\\").replace('"', '\\"')
    skin = mel.eval('findRelatedSkinCluster "{}"'.format(escaped))
    return skin if skin and cmds.objExists(skin) else None


def _proxy_parse_faces(info):
    # Resolve the source mesh and the faces to keep.
    raw_faces = info.get("faces") or ""
    if isinstance(raw_faces, (list, tuple)):
        selected = [str(value).strip() for value in raw_faces if str(value).strip()]
    else:
        selected = [part.strip() for part in str(raw_faces).splitlines() if part.strip()]
    if not selected:
        raise ValueError("CreateProxy: no selected faces")

    expanded = []
    for entry in selected:
        faces = cmds.ls(entry, flatten=True, long=True) or []
        if not faces:
            raise ValueError("CreateProxy: face component not found: " + entry)
        expanded.extend(faces)

    source = None
    keep_ids = set()
    for face in expanded:
        if ".f[" not in face or not face.endswith("]"):
            raise ValueError("CreateProxy: expected polygon face: " + face)
        node, number = face.rsplit(".f[", 1)
        try:
            face_id = int(number[:-1])
        except ValueError:
            raise ValueError("CreateProxy: unsupported face component: " + face)

        if cmds.nodeType(node) == "mesh":
            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            if len(parents) != 1:
                raise ValueError("CreateProxy: cannot resolve parent mesh: " + node)
            node = parents[0]
        resolved = cmds.ls(node, long=True) or []
        if len(resolved) != 1 or cmds.nodeType(resolved[0]) != "transform":
            raise ValueError("CreateProxy: ambiguous mesh transform: " + node)
        node = resolved[0]
        if source is None:
            source = node
        elif source != node:
            raise ValueError("CreateProxy: selected faces must belong to one mesh")
        keep_ids.add(face_id)

    shapes = cmds.listRelatives(source, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
    if len(shapes) != 1:
        raise ValueError("CreateProxy: expected one polygon mesh shape: " + source)
    total = int(cmds.polyEvaluate(source, face=True) or 0)
    if total <= 0 or any(index < 0 or index >= total for index in keep_ids):
        raise ValueError("CreateProxy: face indices are invalid for " + source)
    if len(keep_ids) == total:
        raise ValueError(
            "CreateProxy: all {} faces were selected on {}; "
            "a proxy must contain a subset of the source".format(total, source)
        )
    return source, keep_ids, total


def _proxy_delete_ranges(proxy, total, keep_ids):
    # Remove every face outside the saved selection.
    remove_ids = [i for i in range(total) if i not in keep_ids]
    if not remove_ids:
        raise RuntimeError("CreateProxy: refusing to keep the entire mesh")
    ranges = []
    start = previous = remove_ids[0]
    for index in remove_ids[1:]:
        if index > previous + 1:
            ranges.append((start, previous))
            start = index
        previous = index
    ranges.append((start, previous))
    targets = [
        "{}.f[{}]".format(proxy, first) if first == last
        else "{}.f[{}:{}]".format(proxy, first, last)
        for first, last in ranges
    ]
    cmds.delete(targets)


def _proxy_verify_face_count(proxy, expected, stage):
    actual = int(cmds.polyEvaluate(proxy, face=True) or 0)
    if actual != expected:
        raise RuntimeError(
            "CreateProxy {}: expected {} faces, found {} on {}".format(
                stage, expected, actual, proxy)
        )


def _make_proxy(info):
    name = str(info.get("name") or "").strip()
    contain = str(info.get("contain") or "").strip()
    if not name:
        raise ValueError("CreateProxy: output Name is empty")
    if cmds.objExists(name):
        raise RuntimeError("CreateProxy: output object already exists: " + name)
    source, face_ids, total = _proxy_parse_faces(info)
    source_skin = _proxy_source_skin(source)
    joints = (cmds.skinCluster(source_skin, query=True, influence=True) or []) if source_skin else []

    # Duplicate the source and keep only the selected faces.
    proxy = cmds.duplicate(source, name=name, returnRootsOnly=True)[0]
    try:
        shapes = cmds.listRelatives(proxy, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise RuntimeError("CreateProxy: duplicate has unexpected mesh shapes: " + proxy)
        _proxy_verify_face_count(proxy, total, "after duplicate")
        _proxy_delete_ranges(proxy, total, face_ids)
        _proxy_verify_face_count(proxy, len(face_ids), "after face deletion")
        cmds.delete(proxy, constructionHistory=True)
        _proxy_verify_face_count(proxy, len(face_ids), "after deleting history")

        # Transfer skin weights from the source mesh.
        if source_skin and joints:
            new_skin = cmds.skinCluster(joints, proxy, toSelectedBones=True, normalizeWeights=1, name=name + "_SkinCluster")[0]
            cmds.copySkinWeights(sourceSkin=source_skin, destinationSkin=new_skin, noMirror=True, surfaceAssociation="closestPoint", influenceAssociation="closestJoint")
            cmds.skinCluster(new_skin, edit=True, removeUnusedInfluence=True)
            _proxy_verify_face_count(proxy, len(face_ids), "after skinning")

        if contain:
            if not cmds.objExists(contain):
                cmds.group(empty=True, name=contain)
            cmds.parent(proxy, contain, absolute=True)
        cmds.setAttr(proxy + ".visibility", 0)
        return proxy
    except Exception:
        if cmds.objExists(proxy):
            cmds.delete(proxy)
        raise


def BuildProxy(datas):
    """Build proxy meshes from the saved face selections."""
    created = []
    for info in datas:
        created.append(_make_proxy(info))
    return created


def ExportPython(data, *arr):
    newest = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]
    })
    if not newest or not newest.get("path"):
        cmds.warning("CreateProxy: no valid pattern data path")
        return None
    data_path = os.path.normpath(newest["path"])
    datas = NLTA_General.readJsonFile(data_path)
    if not isinstance(datas, list) or not datas:
        cmds.warning("CreateProxy: no saved proxy items")
        return None

    import ast
    functions = (_proxy_source_skin, _proxy_parse_faces, _proxy_delete_ranges,
                 _make_proxy, BuildProxy)
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
            return node if node.body else node.orelse

        def visit_While(self, node):
            self.generic_visit(node)
            return node if node.body else node.orelse

        def visit_Assign(self, node):
            if any(isinstance(target, ast.Name) and target.id in ("shapes", "actual")
                   for target in node.targets):
                return None
            return self.generic_visit(node)

        def visit_Expr(self, node):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return None
            if isinstance(value, ast.Call):
                fn = value.func
                if isinstance(fn, ast.Name) and fn.id == "_proxy_verify_face_count":
                    return None
                if (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                        and fn.value.id == "cmds" and fn.attr == "warning"):
                    return None
            return self.generic_visit(node)

        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            if not node.body:
                node.body = [ast.Pass()]
            return node

    tree = ExportCode().visit(tree)
    ast.fix_missing_locations(tree)
    body = ast.unparse(tree)
    body = "\n".join("    " + line if line.strip() else "" for line in body.splitlines())
    saved = repr(datas)
    source = (
        "def main():\n"
        "    import maya.cmds as cmds\n"
        "    import maya.mel as mel\n\n"
        "    PROXY_DATA = " + saved + "\n\n"
        + body + "\n\n"
        "    BuildProxy(PROXY_DATA)\n\n"
        'if __name__ == "__main__":\n    main()\n'
    )
    filename = "Python_" + os.path.splitext(os.path.basename(__file__))[0] + ".py"
    compile(source, filename, "exec")
    output = os.path.join(os.path.dirname(data_path), filename)
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(source)
    return output


def Run(data, *arr):
    newest = NLTA_General.JsonGetByID({
        "path": os.path.join(data["sceneDataPath"], "ScenePatternData.json"),
        "id": data["id"]
    })
    if not newest or not newest.get("path"):
        cmds.warning("CreateProxy: missing ScenePatternData.json entry")
        return []
    datas = NLTA_General.readJsonFile(os.path.normpath(newest["path"])) or []
    return BuildProxy(datas)


def Add(listUI, data, *arr):
    global ITEMS

    def Delete(ui, *arr):
        global ITEMS
        cmds.deleteUI(ui)
        del ITEMS['items'][ui]
        ITEMS['order'].remove(ui)

    itemData = {}
    itemUI = cmds.rowColumnLayout(numberOfColumns=1, parent=listUI, backgroundColor=(0.15, 0.15, 0.15))
    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 80), (2, 265), (3, 32)])
    cmds.textField(text='Faces', editable=False)
    itemData['faces'] = cmds.scrollField(text=data.get('faces', ''), h=80)
    cmds.rowColumnLayout(nc=1)
    cmds.button(label='->', w=30, c=partial(NLTA_UI.PickObject, itemData['faces']))
    cmds.button(label='+', w=30, c=partial(NLTA_UI.PickObjectAdd, itemData['faces']))
    cmds.setParent('..')
    cmds.textField(text='Name', editable=False)
    itemData['name'] = cmds.textField(text=data.get('name', ''))
    cmds.text(label='')
    cmds.textField(text='Contain', editable=False)
    itemData['contain'] = cmds.textField(text=data.get('contain', ''))
    cmds.button(label='+', w=30, c=partial(NLTA_UI.PickObject, itemData['contain']))
    cmds.setParent('..')
    cmds.button(label='X', w=35, backgroundColor=(.5, .2, .2), c=partial(Delete, itemUI))
    cmds.separator(height=10, style='none')
    cmds.setParent('..')
    cmds.setParent('..')
    ITEMS['items'][itemUI] = itemData
    ITEMS['order'].append(itemUI)