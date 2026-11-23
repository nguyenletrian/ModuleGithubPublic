# -*- coding: utf-8 -*-
"""NLTA Graph Skinning — compact graph window and separate operation pickers.

    import NLTA_GraphSkinning as GS
    GS.CreateUI()

Requires existing NLTA_Graph.py and NLTA_UI.py for the embedded Bezier graph.
Skirt procedures additionally require NLTA_Mesh.py (existing topology helpers).
Pickers use explicit inputs; Skin Children defaults to unlocked influence chains, or explicitly picked joints.
Copy Ratio uses topological loops; Copy Ratio Plane uses rest-pose perpendicular planes.
Transfer has no UI button; private weight transfer helpers support skirt algorithms.
"""
from __future__ import absolute_import

import contextlib
import bisect
import math
import re
import heapq

import maya.cmds as cmds
import NLTA_Graph
import NLTA_UI

_WINDOW = 'NLTA_GraphSkinning_Standalone'


def _close_graph_skinning_forms_on_load():
    """Close all owned Maya cmds windows on both import and importlib.reload.

    A reload reuses the module namespace. Stop the previous live-smooth timer
    BEFORE replacing its old session/UI globals, to avoid stale callbacks.
    """
    previous_stop = globals().get('_stop_live_smooth')
    if callable(previous_stop):
        try:
            previous_stop()
        except (RuntimeError, ReferenceError, AttributeError):
            pass  # Previously deleted Maya widgets are normal during reload.

    owned = {_WINDOW}
    for state in (globals().get('_DIALOGS') or {}).values():
        if isinstance(state, dict):
            timer = state.get('radius_timer')
            if timer is not None:
                try:
                    timer.stop()
                except (RuntimeError, ReferenceError):
                    pass
            if state.get('window'):
                owned.add(state['window'])
    old_ui = globals().get('_UI')
    if isinstance(old_ui, dict) and old_ui.get('window'):
        owned.add(old_ui['window'])

    # Existing UIs may have been created by a previous version of this file,
    # when their Python state is no longer in _DIALOGS.
    list_windows = getattr(cmds, 'lsUI', None)
    if callable(list_windows):
        for name in (list_windows(windows=True) or []):
            short = name.split('|')[-1]
            if (short == _WINDOW or short.startswith(_WINDOW + '_') or
                    short == 'NLTA_GraphSkinning' or
                    short.startswith('NLTA_GraphSkinning_')):
                owned.add(name)

    closed = []
    maya_window = getattr(cmds, 'window', None)
    maya_delete = getattr(cmds, 'deleteUI', None)
    if not callable(maya_window) or not callable(maya_delete):
        return closed
    for window in sorted(owned):
        try:
            if maya_window(window, exists=True):
                maya_delete(window, window=True)
                closed.append(window)
        except (RuntimeError, ValueError) as exc:
            cmds.warning('NLTA GraphSkinning: could not close {}: {}'.format(window, exc))
    return closed


# Importing or reloading NLTA_GraphSkinning closes only its own windows.
_close_graph_skinning_forms_on_load()

_DIALOGS = {}
_ACTIVE_GRAPH = None
_UI = None
_SMOOTH_LIVE = None  # Captured once when RUN Smooth succeeds; never inferred from paint locks.
_WRITE_SERIAL = 0
_EPS = 1e-9
_VTX = re.compile(r'\.vtx\[(\d+)\]$')


def _graph(graph=None):
    g = _ACTIVE_GRAPH if graph is None else graph
    if isinstance(g, dict) and g.get('_nlta_type') == 'curveGraph':
        return g['graph']
    if g is not None and (not isinstance(g, dict) or 'points' not in g):
        raise TypeError('Expected an NLTA_UI graph handle or NLTA_Graph data')
    return g


def SetGraph(graph=None, *args):
    global _ACTIVE_GRAPH
    _graph(graph)
    if graph is not _ACTIVE_GRAPH:
        _stop_live_smooth()
    _ACTIVE_GRAPH = graph
    return graph


def GetGraph(*args):
    return _ACTIVE_GRAPH


def CreateGraphUI(parent, *args, **kwargs):
    kwargs.setdefault('label', 'Skin Weight Curve (0..1)')
    kwargs.setdefault('controls', True)
    # The PySide graph already emits changes for key/tangent dragging,
    # presets, Reverse and add/delete. Forward them only after a successful
    # RUN Smooth; no geometry or skin weight is touched when no session exists.
    requested_callback = kwargs.pop('onChange', None)
    def changed(points):
        if requested_callback:
            requested_callback(points)
        _queue_live_smooth()
    graph = NLTA_UI.CreateCurveGraphUI(parent, onChange=changed, **kwargs)
    SetGraph(graph)
    # NLTA Graph Skinning opens on the legacy Skirt (flat / flat) profile.
    # Set through NLTA_UI so the Shape dropdown stays in sync.
    SkirtCurve(graph)
    return graph


def GetGraphValue(value, graph=None):
    return NLTA_Graph.GetValue(max(0.0, min(1.0, float(value))), _graph(graph))


def SetGraphPreset(preset, graph=None):
    source = _ACTIVE_GRAPH if graph is None else graph
    if isinstance(source, dict) and source.get('_nlta_type') == 'curveGraph':
        result = NLTA_UI.SetCurveGraphPreset(source, preset)
        if 'preset_menu' in source:
            labels = {value: label for label, value in NLTA_Graph.PresetNames()}
            if preset in labels:
                cmds.optionMenu(source['preset_menu'], e=True, value=labels[preset])
        return result
    return NLTA_Graph.SetPreset(preset, _graph(source))


def SkirtCurve(graph=None, *args):
    return SetGraphPreset('skirt', graph)


def SkirtEndCurve(graph=None, *args):
    return SetGraphPreset('skirt_end', graph)


def GetGraphData(graph=None):
    return NLTA_Graph.GetData(_graph(graph))


def SetGraphData(data, graph=None):
    return NLTA_Graph.SetData(data, _graph(graph))


def _canonical(node):
    if not isinstance(node, str) or not node.strip():
        raise ValueError('A mesh or joint is missing; capture it in the UI')
    result = cmds.ls(node, long=True) or []
    if not result:
        raise ValueError('Object does not exist: {}'.format(node))
    return result[0]


def _mesh_of(node):
    return _canonical(node.split('.', 1)[0])


def _vertices(mesh, components):
    """Convert explicit polygon vertex/edge/face components to unique vertices."""
    mesh = _canonical(mesh)
    if not components:
        return []
    converted = cmds.polyListComponentConversion(components, toVertex=True)
    flattened = cmds.ls(converted, flatten=True, long=True) or []
    result = []
    seen = set()
    for vertex in flattened:
        if not _VTX.search(vertex):
            continue
        if _mesh_of(vertex) != mesh:
            raise ValueError('Selected components must belong to mesh {}'.format(mesh))
        vertex = '{}.vtx[{}]'.format(mesh, _VTX.search(vertex).group(1))
        if vertex not in seen:
            seen.add(vertex)
            result.append(vertex)
    return result


def _require_mesh(mesh):
    mesh = _canonical(mesh)
    shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True) or []
    if not shapes or not any(cmds.nodeType(shape) == 'mesh' for shape in shapes):
        raise ValueError('Expected a polygon mesh transform: {}'.format(mesh))
    return mesh


def _skin(mesh):
    mesh = _require_mesh(mesh)
    skins = cmds.ls(cmds.listHistory(mesh) or [], type='skinCluster') or []
    skins = list(dict.fromkeys(skins))
    if len(skins) != 1:
        raise ValueError('Expected exactly 1 skinCluster on {} (found {})'.format(mesh, len(skins)))
    return skins[0]


def _influences(skin):
    return [_canonical(j) for j in (cmds.skinCluster(skin, q=True, influence=True) or [])]


def _validate_joints(skin, joints):
    group = [_canonical(j) for j in joints]
    if not group or len(group) != len(set(group)):
        raise ValueError('Choose a non-empty list of unique joints')
    influence_set = set(_influences(skin))
    missing = [j for j in group if j not in influence_set]
    if missing:
        raise ValueError('Joints are not influences on {}: {}'.format(skin, missing))
    return group


def _weight(skin, vertex, joint):
    value = cmds.skinPercent(skin, vertex, query=True, transform=joint)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else 0.0
    return float(value or 0.0)


def _get_pair_pool(skin, vertex, joints):
    return {j: _weight(skin, vertex, j) for j in joints}


def _ratio_values(source_weights, target_weights):
    """Redistribute only the selected group; preserve the group's old total."""
    source_total = sum(source_weights.values())
    target_total = sum(target_weights.values())
    if source_total <= _EPS or target_total <= _EPS:
        return None
    return {j: target_total * source_weights[j] / source_total for j in source_weights}


def _gradient_plan(mesh, vertices, main_joint, other_joints, graph=None,
                   reference_vertex=None, capture=None):
    """Prepare weight changes without mutating current weights.

    reference_vertex:
        None  -> legacy joint-distance gradient (used by Skirt helpers).
        vtx   -> distance from that vertex (used by the Smooth button).
    """
    mesh = _require_mesh(mesh)
    skin = _skin(mesh)
    main = _canonical(main_joint)
    others = [_canonical(j) for j in other_joints]
    if main in others:
        raise ValueError('Main joint cannot also be a blend joint')
    if not others:
        raise ValueError('Choose at least one Blend Joint')
    joints = _validate_joints(skin, [main] + others)
    vertices = _vertices(mesh, vertices)
    if not vertices:
        raise ValueError('Capture Gradient Vertices or Edges first')

    # Get all positions on the undeformed mesh, then restore envelope BEFORE
    # reading or writing any weights. The Smooth button uses its FIRST selected
    # vertex as the distance origin, never the joint's world position.
    source = None
    if reference_vertex is not None:
        resolved = _vertices(mesh, [reference_vertex])
        if len(resolved) != 1 or resolved[0] not in vertices:
            raise ValueError('Smooth reference must be the FIRST selected vertex')
        if len(vertices) < 2:
            raise ValueError('Smooth requires at least 2 vertices')
        source = resolved[0]
    env = skin + '.envelope'
    old_env = cmds.getAttr(env)
    positions = []
    try:
        cmds.setAttr(env, 0)
        if source is None:
            # Preserve joint-based interpolation for existing Skirt algorithms.
            origin = cmds.xform(main, q=True, ws=True, t=True)
        else:
            origin = cmds.xform(source, q=True, ws=True, t=True)
        for vertex in vertices:
            point = cmds.xform(vertex, q=True, ws=True, t=True)
            dist = math.sqrt(sum((a-b)**2 for a, b in zip(point, origin)))
            positions.append((vertex, dist))
    finally:
        cmds.setAttr(env, old_env)
    distances = [d for _, d in positions]
    lower, upper = min(distances), max(distances)
    width = upper if source is not None else upper - lower
    if source is not None and width <= _EPS:
        raise ValueError('Smooth vertices have no distance from first vertex')
    plan = {}
    if capture is not None:
        capture.clear()
        capture.update({'mesh': mesh, 'skin': skin, 'main': main,
                        'others': list(others), 'joints': list(joints),
                        'graph': graph, 'samples': {}})
    for vertex, distance in positions:
        ratio = (1.0 - distance / width if source is not None else
                 1.0 - (distance - lower) / width if width > _EPS else 1.0)
        ratio = max(0.0, min(1.0, ratio))
        value = GetGraphValue(ratio, graph)
        old = _get_pair_pool(skin, vertex, joints)
        if capture is not None:
            # Stable initial total and other-influence proportions, avoiding
            # accumulating errors through repeated curve drag updates.
            capture['samples'][vertex] = (ratio, dict(old))
        new = _gradient_weights(old, main, others, value)
        if new is not None and any(abs(new[j]-old[j]) > 1e-7 for j in joints):
            plan[vertex] = new
    return skin, plan


def _gradient_weights(old, main, others, value):
    """Compute the same explicit-influence split for initial and live Smooth."""
    total = sum(old.values())
    if total <= _EPS:
        return None
    remain = total * (1.0-value)
    other_total = sum(old[j] for j in others)
    new = {main: total*value}
    for joint in others:
        new[joint] = (remain * old[joint]/other_total if other_total > _EPS
                      else remain/len(others))
    return new



# ----------------------- Distance Smooth -----------------------

def _distance_smooth_plan(mesh, target_object, vertices, parent_joint,
                          child_joint, graph=None, capture=None):
    """Blend an existing Parent/Child weight pool by distance to an object's pivot.

    Nearest picked vertex => graph input 1 => favors Child.
    Farthest picked vertex => graph input 0 => favors Parent.
    Other skinCluster influences are preserved, as is Parent+Child total.
    Positions come from the undeformed mesh (skin envelope temporarily 0).
    """
    mesh = _require_mesh(mesh)
    skin = _skin(mesh)
    parent, child = _validate_joints(skin, [parent_joint, child_joint])
    vertices = _vertices(mesh, vertices)
    if len(vertices) < 2:
        raise ValueError('Distance Smooth: Pick at least 2 distinct vertices')

    target = _canonical(target_object)
    # xform rotatePivot requires a transform. A shape picked in the Outliner
    # is converted to its transform; ordinary controls, joints and locators
    # already have their own meaningful rotate pivot.
    if cmds.nodeType(target) in ('mesh', 'nurbsCurve', 'nurbsSurface', 'locator'):
        parents = cmds.listRelatives(target, parent=True, fullPath=True) or []
        if not parents:
            raise ValueError('Distance Smooth: Object shape has no transform')
        target = _canonical(parents[0])

    envelope = skin + '.envelope'
    saved_envelope = cmds.getAttr(envelope)
    try:
        cmds.setAttr(envelope, 0)
        origin = cmds.xform(target, q=True, ws=True, rp=True)
        if not origin or len(origin) < 3:
            raise ValueError('Distance Smooth: Cannot read object pivot position')
        points = []
        for vertex in vertices:
            point = cmds.xform(vertex, q=True, ws=True, t=True)
            distance = math.sqrt(sum((float(a)-float(b))**2
                                     for a, b in zip(point[:3], origin[:3])))
            points.append((vertex, distance))
    finally:
        cmds.setAttr(envelope, saved_envelope)

    lower = min(d for _, d in points)
    upper = max(d for _, d in points)
    width = upper - lower
    if width <= _EPS:
        raise ValueError('Distance Smooth: Pick vertices at different distances from Object')

    plan = {}
    samples = {}
    joints = [parent, child]
    for vertex, distance in points:
        normalized = max(0.0, min(1.0, (upper - distance) / width))
        old = _get_pair_pool(skin, vertex, joints)
        samples[vertex] = (normalized, dict(old))
        value = GetGraphValue(normalized, graph)
        new = _gradient_weights(old, child, [parent], value)
        if new is not None and any(abs(new[j] - old[j]) > 1e-7 for j in joints):
            plan[vertex] = new

    if capture is not None:
        capture.clear()
        capture.update({'mesh':mesh, 'skin':skin, 'main':child,
                        'others':[parent], 'joints':[child, parent],
                        'graph':graph, 'samples':samples,
                        'operation':'distance', 'object':target,
                        'minDistance':lower, 'maxDistance':upper})
    return skin, plan


def DistanceSmooth(data=None, *args):
    """Distance-based Parent/Child blending for explicitly captured vertices.

    Call directly with e.g.:
      DistanceSmooth({'object':'locator1', 'vertices':['body.vtx[1]', ...],
                      'parentJoint':'Root', 'childJoint':'Tip',
                      'graph':GetGraph()})
    No separate Mesh picker is needed; the vertices identify their mesh.
    Calling through the UI also enables non-cumulative Live Graph edits.
    """
    from_ui = data is None
    if from_ui:
        _stop_live_smooth()
        data = _inputs_distance()
    vertices = data.get('vertices') or []
    if not vertices:
        raise ValueError('Distance Smooth: Pick Vertices first')
    mesh = _require_mesh(_mesh_of(vertices[0]))
    if data.get('mesh') and _require_mesh(data['mesh']) != mesh:
        raise ValueError('Distance Smooth: Vertices do not belong to provided Mesh')
    snapshot = {} if from_ui else None
    with _transaction('NLTA Distance Smooth'):
        skin, plan = _distance_smooth_plan(
            mesh, data['object'], vertices, data['parentJoint'],
            data['childJoint'], data.get('graph', GetGraph()), capture=snapshot)
        changed = _apply_plan(skin, plan)
    if from_ui:
        global _SMOOTH_LIVE
        _SMOOTH_LIVE = snapshot
        _status('Distance Smooth ready: {} vertices; Graph edits are Live'.format(
                len(snapshot['samples'])), 'distance')
    if changed:
        _refresh(mesh)
    return changed


def PreviewDistanceSmooth(data=None, *args):
    """Calculate a distance-weight plan without modifying the mesh."""
    data = _inputs_distance() if data is None else data
    vertices = data.get('vertices') or []
    if not vertices:
        raise ValueError('Distance Smooth: Pick Vertices first')
    mesh = _require_mesh(_mesh_of(vertices[0]))
    skin, plan = _distance_smooth_plan(
        mesh, data['object'], vertices, data['parentJoint'],
        data['childJoint'], data.get('graph', GetGraph()))
    return {'skinCluster':skin, 'changed':len(plan),
            'vertices':list(plan), 'weights':plan}


# ------------------------- Radial Smooth -------------------------

def _radial_triangle_candidate(point, a, b, da, db):
    """Fast-marching-like surface update across one triangular face.

    A path may cross the face from any position of edge A-B, rather than
    being forced to walk along just the polygon edges. Approximate intrinsic
    distance, not an exact global mesh geodesic.
    """
    ab = [b[i] - a[i] for i in range(3)]
    length = math.sqrt(sum(x*x for x in ab))
    if length <= _EPS:
        return min(da + math.dist(point, a), db + math.dist(point, b))
    ap = [point[i] - a[i] for i in range(3)]
    parallel = sum(ap[i]*ab[i] for i in range(3)) / length
    altitude2 = max(0.0, sum(v*v for v in ap) - parallel*parallel)
    candidate = min(da + math.dist(point, a), db + math.dist(point, b))
    slope = (db - da) / length
    if abs(slope) >= 1.0 - 1e-12:
        return candidate
    along = parallel - slope * math.sqrt(altitude2 / (1.0 - slope*slope))
    if 0.0 <= along <= length:
        candidate = min(candidate, da + along*slope +
                        math.sqrt((parallel-along)**2 + altitude2))
    return candidate


def _radial_surface_faces(points, adjacency, faces):
    """Create virtual diagonal links and triangles WITHOUT changing Maya mesh.

    Four-sided faces expose both diagonals to avoid a Manhattan/square falloff.
    Polygons larger than quads retain their original edges to avoid invalid
    shortcuts through concave n-gons. Disconnected shells stay separate.
    """
    neighbors = [set(row) for row in adjacency]
    triangles = []
    vertex_faces = [[] for _ in points]

    def add_edge(a, b):
        if a != b:
            neighbors[a].add(b)
            neighbors[b].add(a)

    def add_triangle(a, b, c):
        if len({a, b, c}) != 3:
            return
        triangle_id = len(triangles)
        triangles.append((a, b, c))
        for v in (a, b, c):
            vertex_faces[v].append(triangle_id)

    for face in faces or []:
        indices = [int(i) for i in face]
        if len(indices) == 3:
            add_triangle(*indices)
        elif len(indices) == 4:
            a, b, c, d = indices
            add_edge(a, c)
            add_edge(b, d)
            add_triangle(a, b, c)
            add_triangle(a, c, d)
            add_triangle(a, b, d)
            add_triangle(b, c, d)
    return neighbors, triangles, vertex_faces


def _radial_distances(points, source_id, radius, mode, adjacency=None, faces=None):
    """Radial distances on undeformed mesh in World units.

    sphere = direct 3D Euclidean distance (true sphere on rest geometry).
    surface = shortest connected-surface approximation, using faces to
              avoid the square/diamond footprint of 4-neighbor quad grids.
    If faces are unavailable, falls back to old edge-only surface behavior.
    """
    if mode not in ('surface', 'sphere'):
        raise ValueError('Radial Smooth mode must be Surface or Sphere')
    radius = float(radius)
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError('Radial Smooth Radius must be greater than zero')
    if source_id < 0 or source_id >= len(points):
        raise ValueError('Radial Smooth source vertex index is invalid')
    origin = points[source_id]
    if mode == 'sphere':
        result = {}
        for index, point in enumerate(points):
            distance = math.dist(origin, point)
            if distance <= radius + 1e-8:
                result[index] = distance
        return result

    if adjacency is None or len(adjacency) != len(points):
        raise ValueError('Surface mode needs mesh edge connectivity')
    neighbors, triangles, vertex_faces = _radial_surface_faces(
        points, adjacency, faces)
    best = {source_id: 0.0}
    settled = set()
    pending = [(0.0, source_id)]

    def improve(index, distance):
        if (index not in settled and distance <= radius + 1e-8 and
                distance + 1e-9 < best.get(index, float('inf'))):
            best[index] = distance
            heapq.heappush(pending, (distance, index))

    while pending:
        distance, index = heapq.heappop(pending)
        if distance > radius + 1e-8:
            break
        if index in settled or distance > best[index] + 1e-9:
            continue
        settled.add(index)
        for other in neighbors[index]:
            if other not in settled:
                improve(other, distance + math.dist(points[index], points[other]))
        for triangle_id in vertex_faces[index]:
            trio = triangles[triangle_id]
            for target in trio:
                if target in settled:
                    continue
                a, b = [v for v in trio if v != target]
                if a not in settled or b not in settled:
                    continue
                candidate = _radial_triangle_candidate(
                    points[target], points[a], points[b], best[a], best[b])
                # Enforce outward propagation; edge relaxation above remains
                # available if this triangle doesn't yield a causal update.
                if candidate + 1e-8 >= max(best[a], best[b]):
                    improve(target, candidate)
    return {v: best[v] for v in settled}


def _radial_geometry(mesh, skin, origin_vertex, radius, mode):
    """Sample undeformed mesh geometry; always restore skin envelope.

    Uses the same Maya API 2.0 mesh interface as Copy Ratio Plane. The mesh
    is never modified and the old envelope value is restored on exceptions.
    """
    import maya.api.OpenMaya as om
    env_attr = skin + '.envelope'
    old_env = cmds.getAttr(env_attr)
    try:
        cmds.setAttr(env_attr, 0)
        sel = om.MSelectionList()
        sel.add(mesh)
        fn_mesh = om.MFnMesh(sel.getDagPath(0))
        points = [(p.x, p.y, p.z) for p in fn_mesh.getPoints(om.MSpace.kWorld)]
        adjacency = None
        if mode == 'surface':
            adjacency = [[] for _ in points]
            for edge_id in range(fn_mesh.numEdges):
                a, b = fn_mesh.getEdgeVertices(edge_id)
                adjacency[a].append(b)
                adjacency[b].append(a)
        faces = None
        if mode == 'surface' and hasattr(fn_mesh, 'getPolygonVertices'):
            faces = [fn_mesh.getPolygonVertices(i)
                     for i in range(fn_mesh.numPolygons)]
        source_id = int(_VTX.search(origin_vertex).group(1))
        return _radial_distances(points, source_id, radius, mode,
                                 adjacency, faces)
    finally:
        cmds.setAttr(env_attr, old_env)


def _radial_smooth_plan(mesh, origin_vertex, base_joint, main_joint, radius,
                        mode='surface', graph=None, capture=None):
    """Create a two-joint radial gradient; preserve all other influences.

    Main is highest at the center; fade is calculated from the user Radius,
    not the farthest sampled vertex or square boundary of a finite mesh.
    """
    mesh = _require_mesh(mesh)
    skin = _skin(mesh)
    if not isinstance(origin_vertex, str) or not _VTX.search(origin_vertex):
        raise ValueError('Radial Smooth: Pick exactly one source vertex')
    sources = _vertices(mesh, [origin_vertex])
    if len(sources) != 1:
        raise ValueError('Radial Smooth: Pick exactly one valid source vertex')
    origin = sources[0]
    base, main = _validate_joints(skin, [base_joint, main_joint])
    distances = _radial_geometry(mesh, skin, origin, radius, mode)
    if len(distances) < 2:
        raise ValueError('No other vertex within Radius. Increase Radius and retry')
    samples = {}
    plan = {}
    for index, distance in distances.items():
        vertex = '{}.vtx[{}]'.format(mesh, index)
        t = max(0.0, min(1.0, 1.0 - distance / float(radius)))
        old = _get_pair_pool(skin, vertex, [base, main])
        samples[vertex] = (t, dict(old))
        value = GetGraphValue(t, graph)
        new = _gradient_weights(old, main, [base], value)
        if new is not None and any(abs(new[j]-old[j]) > 1e-7 for j in [base, main]):
            plan[vertex] = new
    if capture is not None:
        capture.clear()
        capture.update({'mesh': mesh, 'skin': skin, 'main': main,
                        'others': [base], 'joints': [main, base],
                        'graph': graph, 'samples': samples, 'operation': 'radial'})
    return skin, plan


def RadialSmooth(data=None, *args):
    """Spread from a single picked vertex, then Smooth via shared Graph.

    data={'originVertex': 'mesh.vtx[0]', 'baseJoint': 'base',
          'mainJoint': 'main', 'mode': 'surface'|'sphere',
          'radius': 5.0, 'graph': GetGraph()}.
    No mesh input: inferred from origin vertex. Explicit calls are one-shot;
    the picker RUN also arms Live Smooth, like the existing Smooth tool.
    """
    from_ui = data is None
    if from_ui:
        _stop_radial_radius_timer()
        _stop_live_smooth()
        data = _inputs_radial()
    origin = data['originVertex']
    mesh = _require_mesh(_mesh_of(origin))
    if data.get('mesh') and _require_mesh(data['mesh']) != mesh:
        raise ValueError('Radial Smooth: Mesh differs from origin vertex')
    snapshot = {} if from_ui else None
    with _transaction('NLTA Radial Smooth'):
        skin, plan = _radial_smooth_plan(
            mesh, origin, data['baseJoint'], data['mainJoint'],
            data['radius'], data.get('mode', 'surface'), data.get('graph', GetGraph()),
            capture=snapshot)
        changed = _apply_plan(skin, plan)
    if from_ui:
        global _SMOOTH_LIVE
        # Keep untouched originals for every vertex ever reached during this
        # Apply session. Changing Radius can now both extend and shrink the
        # footprint without accumulating earlier Smooth values.
        snapshot['baseline'] = {
            vertex: dict(weights) for vertex, (_, weights) in snapshot['samples'].items()
        }
        snapshot['originVertex'] = origin
        snapshot['radius'] = float(data['radius'])
        snapshot['mode'] = data.get('mode', 'sphere')
        _SMOOTH_LIVE = snapshot
        _status('Radial Applied: edit Radius, mode or Graph live ({} vertices)'.format(
                len(snapshot['samples'])), 'radial')
    if changed:
        _refresh(mesh)
    return changed



def ResetRadialToBase(data=None, *args):
    """Give ALL skin weight to Base Joint within the current Radial Radius.

    This is intentionally different from RadialSmooth: it zeroes *every*
    other influence, not only the Main Joint. Vertices outside the selected
    Surface/Sphere area are untouched. Safe with Hold Weights and Maya Undo.
    """
    from_ui = data is None
    if from_ui:
        _stop_radial_radius_timer()
        _stop_live_smooth()  # Reset must not be overwritten by Graph live.
        data = _inputs_radial()
    origin = data['originVertex']
    mesh = _require_mesh(_mesh_of(origin))
    if data.get('mesh') and _require_mesh(data['mesh']) != mesh:
        raise ValueError('Radial Reset: Mesh differs from origin vertex')
    skin = _skin(mesh)
    base = _validate_joints(skin, [data['baseJoint']])[0]
    radius = float(data['radius'])
    mode = data.get('mode', 'sphere')
    distances = _radial_geometry(mesh, skin, origin, radius, mode)
    all_joints = _influences(skin)
    plan = {}
    for index in distances:
        vertex = '{}.vtx[{}]'.format(mesh, index)
        current = _get_pair_pool(skin, vertex, all_joints)
        desired = {joint: 1.0 if joint == base else 0.0 for joint in all_joints}
        if any(abs(current[j] - desired[j]) > 1e-7 for j in all_joints):
            plan[vertex] = desired
    with _transaction('NLTA Radial Reset to Base'):
        changed = _apply_plan(skin, plan)
    if changed:
        _refresh(mesh)
    if from_ui:
        _status('Reset to Base: {} vertices; Base = 100%'.format(len(distances)), 'radial')
    return changed


def _apply_radial_radius_update():
    """Re-smooth current Radius/mode using the originals from first Apply.

    Shrink restores now-excluded vertices to their pre-Apply two-joint weights.
    Expansion captures originals for newly reached vertices once. Other
    influences stay untouched by this operation.
    """
    session = _SMOOTH_LIVE
    if not session or session.get('operation') != 'radial' or session.get('running'):
        return 0
    state = _DIALOGS.get('radial')
    if not state or not cmds.window(state['window'], exists=True):
        return 0
    try:
        data = _radial_range_inputs()
    except (ValueError, TypeError):
        # During text entry, intermediate states ('', '-', '1.') are normal.
        return 0
    if data['originVertex'] != session.get('originVertex') or data['mesh'] != session['mesh']:
        return 0
    session['running'] = True
    try:
        distances = _radial_geometry(session['mesh'], session['skin'],
                                     data['originVertex'], data['radius'], data['mode'])
        main = session['main']
        others = session['others']
        joints = session['joints']
        baseline = dict(session['baseline'])
        samples = {}
        plan = {}
        for index, distance in distances.items():
            vertex = '{}.vtx[{}]'.format(session['mesh'], index)
            if vertex not in baseline:
                baseline[vertex] = _get_pair_pool(session['skin'], vertex, joints)
            t = max(0.0, min(1.0, 1.0 - distance / data['radius']))
            samples[vertex] = (t, dict(baseline[vertex]))
            updated = _gradient_weights(baseline[vertex], main, others,
                                        GetGraphValue(t, session['graph']))
            if updated is not None:
                current = _get_pair_pool(session['skin'], vertex, joints)
                if any(abs(updated[j] - current[j]) > 1e-7 for j in joints):
                    plan[vertex] = updated
        # Restore pair weights of vertices that fell outside current radius.
        for vertex in session['samples']:
            if vertex in samples:
                continue
            original = baseline[vertex]
            current = _get_pair_pool(session['skin'], vertex, joints)
            if any(abs(original[j] - current[j]) > 1e-7 for j in joints):
                plan[vertex] = dict(original)
        if plan:
            with _transaction('NLTA Live Radial Radius'):
                changed = _apply_plan(session['skin'], plan)
            _refresh(session['mesh'])
        else:
            changed = 0
        # Update live-Graph footprint only after all Maya writes succeed.
        session['baseline'] = baseline
        session['samples'] = samples
        session['radius'] = data['radius']
        session['mode'] = data['mode']
        _status('Radial Live: {} vertices; Radius {} ({})'.format(
                len(samples), data['radius'], data['mode']), 'radial')
        return changed
    except Exception as error:
        _stop_live_smooth()
        cmds.warning('NLTA Radial Live disabled: {}'.format(error))
        _status('Radial Live stopped: {}'.format(error), 'radial')
        return 0
    finally:
        session['running'] = False


def _copy_ratio_plan(mesh, source_vertex, target_vertices, joints):
    mesh = _require_mesh(mesh)
    skin = _skin(mesh)
    joints = _validate_joints(skin, joints)
    source = _vertices(mesh, [source_vertex])
    if len(source) != 1:
        raise ValueError('Reference must be one vertex')
    target = _vertices(mesh, target_vertices)
    if not target:
        raise ValueError('Capture Ratio Target Vertices first')
    source_weights = _get_pair_pool(skin, source[0], joints)
    if sum(source_weights.values()) <= _EPS:
        raise ValueError('Reference vertex has no weight on selected joints')
    plan = {}
    for vertex in target:
        original = _get_pair_pool(skin, vertex, joints)
        new = _ratio_values(source_weights, original)
        if new and any(abs(new[j]-original[j]) > 1e-7 for j in joints):
            plan[vertex] = new
    return skin, plan


def _transfer_plan(mesh, vertices, source_joint, target_joint):
    mesh = _require_mesh(mesh)
    skin = _skin(mesh)
    source, target = _validate_joints(skin, [source_joint, target_joint])
    vertices = _vertices(mesh, vertices)
    if not vertices:
        raise ValueError('Capture Transfer Vertices first')
    plan = {}
    for vertex in vertices:
        amount = _weight(skin, vertex, source)
        if amount > _EPS:
            plan[vertex] = {source: 0.0, target: _weight(skin, vertex, target)+amount}
    return skin, plan


def _validate_max_influences(skin, plan):
    if not cmds.objExists(skin+'.maintainMaxInfluences') or not cmds.getAttr(skin+'.maintainMaxInfluences'):
        return
    max_count = int(cmds.getAttr(skin+'.maxInfluences'))
    all_influences = _influences(skin)
    for vertex, edited in plan.items():
        count = 0
        for joint in all_influences:
            value = edited[joint] if joint in edited else _weight(skin, vertex, joint)
            if value > 1e-8:
                count += 1
        if count > max_count:
            raise ValueError('{} would require {} influences, max is {}'.format(vertex, count, max_count))


@contextlib.contextmanager
def _transaction(name):
    before = _WRITE_SERIAL
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if _WRITE_SERIAL != before:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)


def _apply_plan(skin, plan):
    """Use undoable native Maya skinPercent. No Paint Skin lock-state dependency."""
    global _WRITE_SERIAL
    if not plan:
        return 0
    _validate_max_influences(skin, plan)
    joints = set(j for row in plan.values() for j in row)
    locked_states = {}
    try:
        for joint in joints:
            attr = joint+'.liw'
            if cmds.objExists(attr):
                locked_states[attr] = cmds.getAttr(attr)
                if locked_states[attr]:
                    cmds.setAttr(attr, False)
        for vertex, row in plan.items():
            _WRITE_SERIAL += 1  # Even a partially failed Maya command needs rollback.
            cmds.skinPercent(skin, vertex,
                             transformValue=list(row.items()),
                             normalize=False, zeroRemainingInfluences=False)
    finally:
        for attr, state in locked_states.items():
            cmds.setAttr(attr, state)
    return len(plan)


def _refresh(mesh):
    cmds.dgdirty(mesh)
    cmds.refresh()


def UpdateView(mesh=None, *args):
    """Refresh one explicit mesh (or mesh captured in standalone UI)."""
    if mesh is None and _UI:
        mesh = _UI['data'].get('mesh')
    if not mesh:
        raise ValueError('Pass a mesh or capture one with CreateUI()')
    _refresh(_require_mesh(mesh))


def GradientActiveJoint(data=None, *args, **kwargs):
    """Smooth: measure from the first vertex; joints only receive the weights.

    A successful UI RUN arms Live Smooth. Editing the shared Graph then
    recalculates that same vertex set from the snapshot made BEFORE RUN.
    Explicit script calls with a data dict remain one-shot and unchanged.
    """
    from_ui = data is None
    if from_ui:
        _stop_live_smooth()
        data = _inputs_gradient()
    mesh = data['mesh']
    vertices = data['vertices']
    reference = data.get('referenceVertex') or (vertices[0] if vertices else None)
    snapshot = {} if from_ui else None
    with _transaction('NLTA Gradient Skin'):
        skin, plan = _gradient_plan(mesh, vertices, data['mainJoint'],
                                    data['blendJoints'], data.get('graph'),
                                    reference_vertex=reference, capture=snapshot)
        changed = _apply_plan(skin, plan)
    if from_ui:
        global _SMOOTH_LIVE
        _SMOOTH_LIVE = snapshot
        _status('Smooth ready: Graph edits will update {} vertices'.format(
                len(snapshot['samples'])), 'smooth')
    if changed:
        _refresh(mesh)
    return changed


def PreviewGradient(data=None, *args):
    data = data or _inputs_gradient()
    vertices = data['vertices']
    reference = data.get('referenceVertex') or (vertices[0] if vertices else None)
    skin, plan = _gradient_plan(data['mesh'], vertices, data['mainJoint'],
                                data['blendJoints'], data.get('graph'),
                                reference_vertex=reference)
    return {'skinCluster':skin, 'changed':len(plan), 'vertices':list(plan), 'weights':plan,
            'referenceVertex':reference}


def _selected_ratio_data():
    """Select source vertex FIRST, then target vertices. Uses all skin influences."""
    # Maya may otherwise return selection in index order, not click order.
    pref = getattr(cmds, 'selectPref', None)
    if pref and not pref(query=True, trackSelectionOrder=True):
        raise ValueError('Enable Track Selection Order and reselect source FIRST')
    selected = cmds.ls(orderedSelection=True, flatten=True, long=True) or []
    if not selected:
        selected = cmds.ls(sl=True, flatten=True, long=True) or []
    if len(selected) < 2:
        raise ValueError('Select reference vertex FIRST, then one or more target vertices')
    if any(not _VTX.search(component) for component in selected):
        raise ValueError('Copy Ratio requires vertices only (select source FIRST)')
    mesh = _mesh_of(selected[0])
    # polyListComponentConversion may reorder vertices; preserve the actual
    # first selected component as the reference rather than trusting its output.
    match = _VTX.search(selected[0])
    source = '{}.vtx[{}]'.format(mesh, match.group(1))
    targets = [v for v in _vertices(mesh, selected[1:]) if v != source]
    if not targets:
        raise ValueError('Select at least one OTHER vertex after the reference')
    skin = _skin(mesh)
    return {'mesh': mesh, 'sourceVertex': source,
            'targetVertices': targets, 'joints': _influences(skin)}

def _unlocked_joints(joints):
    result = []

    for joint in joints:
        attr = joint + ".liw"

        # liw = Lock Influence Weights
        # True: khóa, False: mở khóa.
        if cmds.objExists(attr) and cmds.getAttr(attr):
            continue

        result.append(joint)

    return result


def SmoothUnlocked(mainJoint=None, *args):
    """One-click Smooth: selected vertices + exactly two unlocked skin influences.

    The first SELECTED vertex is the distance origin (requires Maya's Track
    Selection Order). The influence with the greatest weight at that vertex
    becomes Main; ties choose the influence whose joint is physically nearer
    to the origin. Pass mainJoint explicitly to override the auto direction.

    Uses the SAME _gradient_plan, Graph, undo and non-cumulative Live Graph
    updates as picker-based GradientActiveJoint. Never opens a picker window.
    """
    global _SMOOTH_LIVE

    pref = getattr(cmds, 'selectPref', None)
    if pref and not pref(query=True, trackSelectionOrder=True):
        raise ValueError(
            'Smooth: enable Track Selection Order, then reselect the vertices '
            'starting with the gradient origin'
        )

    selected = cmds.ls(orderedSelection=True, flatten=True, long=True) or []
    if len(selected) < 2 or any(not _VTX.search(v) for v in selected):
        raise ValueError('Smooth: select at least 2 VERTICES, origin FIRST')

    mesh = _require_mesh(_mesh_of(selected[0]))
    vertices = []
    seen = set()
    for v in selected:
        if _mesh_of(v) != mesh:
            raise ValueError('Smooth: all selected vertices must be on one mesh')
        vertex = '{}.vtx[{}]'.format(mesh, _VTX.search(v).group(1))
        if vertex not in seen:
            seen.add(vertex)
            vertices.append(vertex)
    if len(vertices) < 2:
        raise ValueError('Smooth: at least 2 DISTINCT vertices are required')

    skin = _skin(mesh)
    unlocked = _unlocked_joints(_influences(skin))
    if len(unlocked) != 2:
        raise ValueError(
            'Smooth: exactly 2 unlocked influences required (found {}). '
            'Unlock just the two joints to blend.'.format(len(unlocked))
        )

    reference = vertices[0]
    if mainJoint is not None:
        main = _canonical(mainJoint)
        if main not in unlocked:
            raise ValueError('Smooth: mainJoint must be one of the 2 unlocked influences')
    else:
        first_weights = [_weight(skin, reference, j) for j in unlocked]
        if abs(first_weights[0] - first_weights[1]) > 1e-7:
            main = unlocked[0] if first_weights[0] > first_weights[1] else unlocked[1]
        else:
            # When the reference has a 50/50 tie (or both weights are 0),
            # choose the spatially nearest joint instead of list ordering.
            attr = skin + '.envelope'
            original = cmds.getAttr(attr)
            try:
                cmds.setAttr(attr, 0)
                position = cmds.xform(reference, query=True, worldSpace=True,
                                      translation=True)
            finally:
                cmds.setAttr(attr, original)
            main = min(unlocked, key=lambda joint: sum(
                (float(a) - float(b)) ** 2 for a, b in zip(
                    position, cmds.xform(joint, query=True, worldSpace=True,
                                         translation=True))))

    other = [j for j in unlocked if j != main][0]
    graph = GetGraph()
    snapshot = {}
    _stop_live_smooth()
    with _transaction('NLTA Smooth Unlocked'):
        skin, plan = _gradient_plan(
            mesh, vertices, main, [other], graph=graph,
            reference_vertex=reference, capture=snapshot)
        changed = _apply_plan(skin, plan)

    # Snapshot is captured from PRE-smooth weights; editing the graph is
    # non-cumulative, as in the existing picker-based Smooth.
    _SMOOTH_LIVE = snapshot
    if changed:
        _refresh(mesh)
    _status('Smooth: {} updated / {} selected (Main: {})'.format(
        changed, len(vertices), main.split('|')[-1]), 'smooth')
    return changed


def CopyRatioWeight(data=None, *args):
    """Copy skin weight ratios using unlocked influences only."""

    # Programmatic API.
    if isinstance(data, dict):
        mesh = data['mesh']
        skin = _skin(mesh)

        # Chỉ lấy những joint đang mở khóa.
        joints = _unlocked_joints(data['joints'])

        if not joints:
            cmds.warning("Copy Ratio: No unlocked joints.")
            return 0

        with _transaction('NLTA Copy Skin Ratio'):
            skin, plan = _copy_ratio_plan(
                mesh,
                data['sourceVertex'],
                data['targetVertices'],
                joints
            )

            changed = _apply_plan(skin, plan)

        if changed:
            _refresh(mesh)

        return changed

    # UI selection.
    selection = cmds.ls(
        sl=True,
        flatten=True,
        long=True
    ) or []

    if any(not _VTX.search(vertex) for vertex in selection):
        raise ValueError(
            'Copy Ratio requires vertex selection only'
        )

    if len(selection) < 2:
        raise ValueError(
            'Select at least 2 adjacent vertices along '
            'the reference row'
        )

    mesh = _mesh_of(selection[0])
    skin = _skin(mesh)

    # Lấy tất cả influence của skinCluster.
    allJoints = _influences(skin)

    # Chỉ giữ các influence chưa khóa.
    joints = _unlocked_joints(allJoints)

    if not joints:
        cmds.warning("Copy Ratio: All joints are locked.")
        return 0

    with _transaction('NLTA Copy Skin Ratio'):
        skin, plan = _topology_ratio_plan(
            mesh,
            selection,
            joints,
            require_mapping=True
        )

        changed = _apply_plan(skin, plan)

    if changed:
        _refresh(mesh)

    return changed




def _plane_axis_from_sources(points, selected_ids):
    """Find the world-space best-fit vector through reference vertices.

    This vector is the NORMAL of all perpendicular planes. The endpoints of
    the approximate diameter initialize a tiny covariance power iteration;
    no numpy and no vertex/edge traversal are required.
    """
    samples = [points[index] for index in selected_ids]
    center = tuple(sum(p[i] for p in samples) / len(samples) for i in range(3))
    start = max(samples, key=lambda p: sum((p[i] - center[i])**2 for i in range(3)))
    end = max(samples, key=lambda p: sum((p[i] - start[i])**2 for i in range(3)))
    axis = tuple(end[i] - start[i] for i in range(3))
    length = math.sqrt(sum(v*v for v in axis))
    if length <= _EPS:
        raise ValueError('Copy Ratio Plane: the reference vertices share the same position')
    axis = tuple(v/length for v in axis)

    offsets = [tuple(float(p[i]) - center[i] for i in range(3)) for p in samples]
    for _ in range(16):
        # covariance * axis, evaluated without building a matrix
        vec = [0.0, 0.0, 0.0]
        for offset in offsets:
            scale = sum(offset[i] * axis[i] for i in range(3))
            for i in range(3):
                vec[i] += offset[i] * scale
        norm = math.sqrt(sum(v*v for v in vec))
        if norm <= _EPS:
            break
        axis = tuple(v/norm for v in vec)
    return axis


def _plane_reference_mapping(points, neighbors, selected_ids, plane_width=None):
    """Find mesh vertices NEAR perpendicular world-space reference planes.

    The reference row defines one best-fit world-space VECTOR (axis). Each
    selected vertex P makes a plane with normal=axis passing through P.
    For a mesh vertex V, its signed point-to-plane distance is:

        distance = abs(dot(V - P, axis))

    The closest qualifying plane supplies its reference-vertex ID. This is a
    geometric slice operation: NO graph flood, edge loops or shortest paths.
    Vertices can belong to either side of the source strip or across a bend.

    plane_width: optional maximum *perpendicular distance* in world units.
      None: auto tolerance = 45% of nearest neighboring plane spacing.
    neighbors: unused legacy parameter, retained for existing callers.
    Returns {target_id: reference_id}, excluding every selected source vertex.
    """
    selected_ids = list(dict.fromkeys(int(i) for i in selected_ids))
    if len(selected_ids) < 2:
        raise ValueError('Copy Ratio Plane: select at least 2 reference vertices')
    if any(i < 0 or i >= len(points) for i in selected_ids):
        raise ValueError('Copy Ratio Plane: invalid vertex ID')
    if plane_width is not None:
        plane_width = float(plane_width)
        if not math.isfinite(plane_width) or plane_width <= 0.0:
            raise ValueError('plane_width must be a finite positive world-space distance')

    axis = _plane_axis_from_sources(points, selected_ids)
    stations = sorted(
        (sum(float(points[index][k]) * axis[k] for k in range(3)), index)
        for index in selected_ids
    )
    positions = [item[0] for item in stations]
    spread = positions[-1] - positions[0]
    if spread <= _EPS:
        raise ValueError('Copy Ratio Plane: the selected row has no direction')
    min_spacing = max(_EPS, spread * 1e-7)
    for i in range(1, len(positions)):
        if positions[i] - positions[i-1] <= min_spacing:
            raise ValueError('Copy Ratio Plane: two reference vertices create the same '
                             'plane; select vertices along one direction')

    # Local spacing makes this work with unequally spaced reference points.
    # A slightly smaller-than-half-gap tolerance avoids duplicate ownership
    # of the area between adjacent planes. Explicit planeWidth overrides it.
    widths = []
    for i in range(len(positions)):
        gaps = []
        if i:
            gaps.append(positions[i] - positions[i-1])
        if i + 1 < len(positions):
            gaps.append(positions[i+1] - positions[i])
        widths.append(float(plane_width) if plane_width is not None
                      else 0.45 * min(gaps))

    sources = set(selected_ids)
    mapping = {}
    for target_id, point in enumerate(points):
        if target_id in sources:
            continue  # never edit the reference row itself
        projection = sum(float(point[k]) * axis[k] for k in range(3))
        insertion = bisect.bisect_left(positions, projection)
        candidates = []
        if insertion < len(positions):
            candidates.append(insertion)
        if insertion > 0:
            candidates.append(insertion - 1)
        if not candidates:
            continue
        closest = min(candidates,
                      key=lambda i: (abs(projection - positions[i]), stations[i][1]))
        distance = abs(projection - positions[closest])
        if distance <= widths[closest] + _EPS:
            mapping[target_id] = stations[closest][1]
    return mapping


def _nearest_reference_vertex(points, target_id, reference_ids):
    """Return the 3D-nearest reference vertex in the undeformed mesh pose.

    Stable tie-break by vertex ID makes results independent of pick order.
    """
    target = points[target_id]
    return min(reference_ids, key=lambda source_id: (
        sum((float(target[k]) - float(points[source_id][k])) ** 2
            for k in range(3)), source_id))


def _plane_ratio_plan(mesh, candidates, joints, plane_width=None, target_vertices=None):
    """Copy ratios using reference planes, falling back to nearest source.

    In-range Affected Vertices inherit the nearest perpendicular plane's donor.
    Out-of-range Affected Vertices inherit the geometrically nearest reference
    VERTEX instead of being skipped. Both operations use undeformed positions.
    Only explicitly picked targets can receive fallback weights. Without
    target_vertices, retain the legacy plane-width-limited behavior so an
    existing scripted call cannot unexpectedly overwrite the whole mesh.
    """
    import maya.api.OpenMaya as om
    mesh = _require_mesh(mesh)
    skin = _skin(mesh)
    joints = _validate_joints(skin, joints)
    candidates = _vertices(mesh, candidates)
    source_ids = [int(_VTX.search(vertex).group(1)) for vertex in candidates]
    allowed_ids = None
    if target_vertices is not None:
        if not target_vertices:
            raise ValueError('Copy Ratio Plane: Pick Affected Vertices first')
        allowed = _vertices(mesh, target_vertices)
        if not allowed:
            raise ValueError('Copy Ratio Plane: no valid Affected Vertices on the mesh')
        allowed_ids = {int(_VTX.search(vertex).group(1)) for vertex in allowed}
        allowed_ids.difference_update(source_ids)  # never edit reference vertices
        if not allowed_ids:
            raise ValueError('Copy Ratio Plane: affected vertices must differ from references')

    # Rest-pose geometry only. The envelope is restored before any weight reads.
    env_attr = skin + '.envelope'
    old_env = cmds.getAttr(env_attr)
    try:
        cmds.setAttr(env_attr, 0)
        sel = om.MSelectionList()
        sel.add(mesh)
        dag = sel.getDagPath(0)
        dag.extendToShape()
        fn_mesh = om.MFnMesh(dag)
        rest_points = [(p.x, p.y, p.z)
                       for p in fn_mesh.getPoints(om.MSpace.kWorld)]
        mapping = _plane_reference_mapping(
            rest_points, None, source_ids, plane_width=plane_width)
    finally:
        cmds.setAttr(env_attr, old_env)

    if allowed_ids is not None:
        # Affected Vertices always receive one donor, even outside Plane Width.
        # Keep the original nearest-plane result in-range; outside that range,
        # use the actual nearest REFERENCE VERTEX in rest-pose 3D distance.
        mapping = {target_id: source_id for target_id, source_id in mapping.items()
                   if target_id in allowed_ids}
        for target_id in sorted(allowed_ids.difference(mapping)):
            mapping[target_id] = _nearest_reference_vertex(
                rest_points, target_id, source_ids)
    if not mapping:
        raise ValueError('No vertices matched the reference planes; '
                         'check the Reference and Affected Vertices')

    # Snapshot every donor ratio before applying changes (no overwrite cascades).
    all_donors = set(mapping.values())
    weights_by_id = {}
    for source_id in all_donors:
        source = '{}.vtx[{}]'.format(mesh, source_id)
        weights_by_id[source_id] = _get_pair_pool(skin, source, joints)

    plan = {}
    for target_id, source_id in mapping.items():
        target = '{}.vtx[{}]'.format(mesh, target_id)
        original = _get_pair_pool(skin, target, joints)
        new = _ratio_values(weights_by_id[source_id], original)
        if new and any(abs(new[j]-original[j]) > 1e-7 for j in joints):
            plan[target] = new
    return skin, plan


def CopyRatioPlaneWeight(data=None, *args):
    """Copy ratios onto mesh vertices close to reference perpendicular planes.

    Select 2+ vertices along a straight-ish line (no edge adjacency needed).
    A shared best-fit reference vector is the plane normal. Each source vertex
    defines a separate perpendicular plane; in-range targets inherit its ratio.
    Picked targets beyond Plane Width inherit the nearest source vertex's ratio
    (3D rest-pose distance). No edge loops or topology paths are used.

    Optional dict: {'vertices': [...], 'targetVertices': [...],
                    'joints': [...], 'planeWidth': max point-to-plane distance}.
    The mesh is resolved from reference vertices; an explicit 'mesh' is optional.
    Explicit targetVertices limits writes to that captured group. Without it,
    the old all-mesh behavior is maintained for existing scripts.
    """
    if data is None and 'plane' in _DIALOGS:
        data = _inputs_plane()
    if isinstance(data, dict):
        candidates = data['vertices']
        mesh = _plane_source_mesh(candidates)
        if data.get('mesh') and _require_mesh(data['mesh']) != mesh:
            raise ValueError('Copy Ratio Plane: mesh differs from Reference Vertices mesh')
        joints = data.get('joints') or _influences(_skin(mesh))
        width = data.get('planeWidth')
        targets = data.get('targetVertices')
    else:
        selected = cmds.ls(sl=True, flatten=True, long=True) or []
        if len(selected) < 2 or any(not _VTX.search(v) for v in selected):
            raise ValueError('Copy Ratio Plane: select 2+ reference VERTICES')
        mesh = _mesh_of(selected[0])
        candidates = selected
        joints = _influences(_skin(mesh))
        width = None
        targets = None

    with _transaction('NLTA Copy Ratio Plane'):
        skin, plan = _plane_ratio_plan(mesh, candidates, joints, plane_width=width,
                                       target_vertices=targets)
        changed = _apply_plan(skin, plan)
    if changed:
        _refresh(mesh)
    print('[NLTA Copy Ratio Plane] Copied {} vertices'.format(changed))
    return changed


def PreviewCopyRatioPlane(data=None, select=False, *args):
    """Return (or select) vertices NEAR the perpendicular planes, no skin writes.

    Call GS.PreviewCopyRatioPlane(select=True) with your reference vertices
    selected in Maya. Reselect that row before actually running Copy Ratio Plane.
    """
    import maya.api.OpenMaya as om
    if isinstance(data, dict):
        candidates = data['vertices']
        mesh = _plane_source_mesh(candidates)
        if data.get('mesh') and _require_mesh(data['mesh']) != mesh:
            raise ValueError('Copy Ratio Plane: mesh differs from Reference Vertices mesh')
        width = data.get('planeWidth')
    else:
        candidates = cmds.ls(sl=True, flatten=True, long=True) or []
        if len(candidates) < 2 or any(not _VTX.search(v) for v in candidates):
            raise ValueError('Select 2+ reference vertices')
        mesh = _mesh_of(candidates[0])
        width = None
    mesh = _require_mesh(mesh)
    skin = _skin(mesh)
    vertices = _vertices(mesh, candidates)
    indices = [int(_VTX.search(v).group(1)) for v in vertices]
    env = skin + '.envelope'
    original = cmds.getAttr(env)
    try:
        cmds.setAttr(env, 0)
        sel = om.MSelectionList()
        sel.add(mesh)
        dag = sel.getDagPath(0)
        dag.extendToShape()
        fn = om.MFnMesh(dag)
        points = [(p.x, p.y, p.z) for p in fn.getPoints(om.MSpace.kWorld)]
        mapping = _plane_reference_mapping(points, None, indices, width)
    finally:
        cmds.setAttr(env, original)
    found = ['{}.vtx[{}]'.format(mesh, vid) for vid in sorted(mapping)]
    if select and found:
        cmds.select(found, replace=True)
    print('[NLTA Copy Ratio Plane] Preview: {} target vertices'.format(len(found)))
    return found


def TransferInfluenceWeight(skinCluster=None, verts=None, sourceJoint=None, targetJoint=None, **kwargs):
    """Legacy positional signature remains available. UI uses RunTransfer()."""
    if skinCluster is None:
        return RunTransfer()
    if not verts:
        return 0
    mesh = _mesh_of(verts[0])
    if _skin(mesh) != skinCluster:
        raise ValueError('skinCluster does not belong to target mesh')
    with _transaction('NLTA Transfer Influence'):
        skin, plan = _transfer_plan(mesh, verts, sourceJoint, targetJoint)
        count = _apply_plan(skin, plan)
    if count:
        _refresh(mesh)
    return count


def RunTransfer(data=None, *args):
    """Backward-compatible API only; Transfer is not part of the compact UI."""
    if not isinstance(data, dict):
        raise ValueError('RunTransfer requires explicit mesh, vertices and joints')
    with _transaction('NLTA Transfer Influence'):
        skin, plan = _transfer_plan(data['mesh'], data['vertices'],
                                    data['sourceJoint'], data['targetJoint'])
        changed = _apply_plan(skin, plan)
    if changed:
        _refresh(data['mesh'])
    return changed


def _topology_ratio_plan(mesh, candidates, joints, require_mapping=False,
                         donor_joints=None):
    """Project source-row weight ratios onto perpendicular topology loops.

    All geometry queries run in the undeformed state. The original envelope
    is restored BEFORE any skin weight is queried or written.

    donor_joints (optional) are weights which may be converted into the
    requested joint group at *target* vertices. This matters for Skin Parent:
    vertices farther down the skirt can still have only the original hip /
    parent influence, so their two neighbouring skirt joints sum to ZERO.
    Without a donor, those vertices cannot receive the reference ratio.

    Normal Copy Ratio passes no donors and keeps its prior behaviour.
    """
    import NLTA_Mesh
    mesh = _require_mesh(mesh)
    skin = _skin(mesh)
    joints = _validate_joints(skin, joints)
    donors = list(donor_joints or [])
    donors = _validate_joints(skin, donors) if donors else []
    if set(donors) & set(joints):
        raise ValueError('Donor joints must not overlap the ratio joint group')
    candidates = _vertices(mesh, candidates)
    if not candidates:
        if require_mapping:
            raise ValueError('No reference-row vertices to propagate')
        return skin, {}

    envelope_attr = skin + '.envelope'
    previous_envelope = cmds.getAttr(envelope_attr)
    try:
        cmds.setAttr(envelope_attr, 0)
        mapped = NLTA_Mesh.ListToPerVerts(candidates) or {}
    finally:
        cmds.setAttr(envelope_attr, previous_envelope)

    # Keep the reference row intact; only write the vertices below/across it.
    reference_row = set(candidates)
    usable = {}
    for source, targets in mapped.items():
        sources = _vertices(mesh, [source])
        if len(sources) != 1 or sources[0] not in reference_row:
            continue
        outside = [v for v in _vertices(mesh, targets) if v not in reference_row]
        if outside:
            usable[sources[0]] = outside

    if require_mapping and not usable:
        raise ValueError('No perpendicular loops with targets outside the smoothed row; '
                         'check topology and NLTA_Mesh.ListToPerVerts()')

    # Snapshot weights after restoring skin deformation; respect all unrelated
    # influence weights and preserve sum(joints + donors) for every target.
    plan = {}
    valid_source_found = False
    for source, targets in usable.items():
        source_weights = _get_pair_pool(skin, source, joints)
        source_total = sum(source_weights.values())
        if source_total <= _EPS:
            continue
        valid_source_found = True
        for vertex in targets:
            original = _get_pair_pool(skin, vertex, joints + donors)
            target_total = sum(original.values())
            if target_total <= _EPS:
                continue
            new = {j: target_total * source_weights[j] / source_total
                   for j in joints}
            for donor in donors:
                new[donor] = 0.0
            if any(abs(new[j] - original[j]) > 1e-7 for j in new):
                plan[vertex] = new

    if require_mapping and not valid_source_found:
        raise ValueError('Reference row has no weight on the two Skirt joints; '
                         'cannot copy a zero weight ratio')
    return skin, plan


def _skirt_pair_gradient(mesh, vertices, parent, child, graph,
                         donor_joints=None, require_mapping=False):
    """Smooth one skirt pair then copy its resulting ratios down each loop."""
    skin, plan = _gradient_plan(mesh, vertices, child, [parent], graph)
    gradient_count = _apply_plan(skin, plan)
    skin, ratio_plan = _topology_ratio_plan(
        mesh, vertices, [parent, child], require_mapping=require_mapping,
        donor_joints=donor_joints)
    copied_count = _apply_plan(skin, ratio_plan)
    if donor_joints is not None:
        print('[NLTA Skin Parent] {} -> {}: smoothed {}, perpendicular copied {}'
              .format(parent, child, gradient_count, copied_count))
    return gradient_count + copied_count


def _get_skirt_mesh_helpers():
    import NLTA_Mesh
    return NLTA_Mesh


def _skirt_parent_ring(mesh, loop, helpers):
    """Order a single open/closed edge loop using mesh topology (rest pose).

    Returned vertex indices follow real edge connectivity, not lexicographic
    component names or the arbitrary order of VertexFromEdges().
    """
    mesh_fn = helpers.GetMeshFn(mesh)
    adjacency = {}
    for edge in loop:
        edge_id = int(edge.rsplit('[', 1)[-1].split(']', 1)[0])
        a, b = [int(v) for v in mesh_fn.getEdgeVertices(edge_id)]
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    if len(adjacency) < 2:
        raise ValueError('Skin Parent: root edge loop is empty or too small')
    degrees = {v: len(neighbors) for v, neighbors in adjacency.items()}
    if any(degree not in (1, 2) for degree in degrees.values()):
        raise ValueError('Skin Parent: root loop branches or contains non-manifold edges')
    ends = sorted(v for v, degree in degrees.items() if degree == 1)
    if len(ends) not in (0, 2):
        raise ValueError('Skin Parent: root loop must be one open chain or one closed ring')
    closed = not ends
    first = ends[0] if ends else min(adjacency)
    order = [first]
    previous = None
    while True:
        candidates = sorted(v for v in adjacency[order[-1]] if v != previous)
        if not candidates:
            break
        nxt = candidates[0]
        if nxt == first:
            break
        if nxt in order:
            raise ValueError('Skin Parent: root loop revisits a vertex')
        previous = order[-1]
        order.append(nxt)
        if len(order) > len(adjacency):
            raise ValueError('Skin Parent: invalid root loop')
    if len(order) != len(adjacency):
        raise ValueError('Skin Parent: disconnected root edge loop')
    return order, closed, mesh_fn


def _skirt_parent_profile(mesh, ordered_ids, closed, children, points, joint_positions):
    """Rest-pose skirt partition along the REAL edge lengths of the mesh.

    Joint anchors use closest sampled mesh vertices. Ownership boundaries
    use the perpendicular bisector of the REAL two-joint distance, not a
    guessed 0.6 radius. The root edge loop establishes true neighbours.
    """
    if len(children) < 2:
        raise ValueError('Skin Parent needs at least two skirt joints')

    def distance(a, b):
        return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))

    anchors = []
    for joint in children:
        nearest = min(range(len(ordered_ids)),
                      key=lambda i: distance(points[ordered_ids[i]], joint_positions[joint]))
        anchors.append((nearest, joint))
    if len(set(index for index, _ in anchors)) != len(anchors):
        raise ValueError('Skin Parent: multiple joints snap to the same root vertex; '
                         'the edge loop needs higher resolution or different placement')
    anchors.sort()
    n = len(ordered_ids)
    edge_lengths = [distance(points[ordered_ids[i]],
                             points[ordered_ids[(i + 1) % n]])
                    for i in range(n if closed else n - 1)]
    if any(length <= _EPS for length in edge_lengths):
        raise ValueError('Skin Parent: root loop contains zero-length mesh edges')
    samples = {}

    def vertex_at(index):
        return '{}.vtx[{}]'.format(mesh, ordered_ids[index % n])

    # At each joint's own anchor it must own its full parent-weight pool.
    for index, joint in anchors:
        samples[vertex_at(index)] = {'owner': joint, 'pair': None, 't': 0.0}

    if not closed:
        for index in range(anchors[0][0]):
            samples[vertex_at(index)] = {'owner': anchors[0][1], 'pair': None, 't': 0.0}
        for index in range(anchors[-1][0] + 1, n):
            samples[vertex_at(index)] = {'owner': anchors[-1][1], 'pair': None, 't': 0.0}

    edges_to_smooth = []
    for segment in range(len(anchors) if closed else len(anchors) - 1):
        start_index, left = anchors[segment]
        end_index, right = anchors[(segment + 1) % len(anchors)]
        if end_index <= start_index:
            end_index += n
        arc_length = sum(edge_lengths[i % len(edge_lengths)]
                         for i in range(start_index, end_index))
        if arc_length <= _EPS:
            raise ValueError('Skin Parent: joint anchors have no separating edge length')
        a, b = joint_positions[left], joint_positions[right]
        direction = [float(b[axis]) - float(a[axis]) for axis in range(3)]
        joint_distance_sq = sum(component * component for component in direction)
        if joint_distance_sq <= _EPS:
            raise ValueError('Skin Parent: adjacent joints share the same position: '
                             '{} and {}'.format(left, right))
        for i in range(start_index + 1, end_index):
            point = points[ordered_ids[i % n]]
            # Projection onto the real joint-to-joint line. t=0.5 is the
            # exact midpoint plane, regardless of differing joint spacing.
            projection = sum((float(point[axis]) - float(a[axis])) * direction[axis]
                             for axis in range(3))
            t = max(0.0, min(1.0, projection / joint_distance_sq))
            # The geometric midpoint separates parent-weight ownership.
            owner = left if t <= 0.5 else right
            samples[vertex_at(i)] = {
                'owner': owner, 'pair': (left, right), 't': t,
            }
        edges_to_smooth.append((left, right,
                                round(math.sqrt(joint_distance_sq), 6),
                                round(arc_length, 6)))
    if len(samples) != n:
        raise ValueError('Skin Parent: incomplete joint partition on root loop')
    return samples, edges_to_smooth


def _skirt_parent_regions(mesh, skin, children, helpers):
    """Build root-row ownership and perpendicular coverage WITH skin disabled.

    No skin weights are queried or written until the envelope has been restored.
    Multiple candidate loops can meet at a seam: pick the nearest originating
    root vertex in rest-pose space, deterministically, to avoid last-write wins.
    """
    env = skin + '.envelope'
    old_envelope = cmds.getAttr(env)
    try:
        cmds.setAttr(env, 0)
        root_pin = helpers.GetClosestVertex(mesh, children[0])
        loop = helpers.GetPerpendicularEdgeLoop(mesh, children[0], root_pin) or []
        if not loop:
            raise ValueError('Skin Parent: failed to find perpendicular root edge loop')
        order, closed, mesh_fn = _skirt_parent_ring(mesh, loop, helpers)
        points = mesh_fn.getPoints(helpers.om.MSpace.kWorld)
        positions = {joint: cmds.xform(joint, q=True, ws=True, t=True)
                     for joint in children}
        profile, segments = _skirt_parent_profile(
            mesh, order, closed, children, points, positions)
        root_names = ['{}.vtx[{}]'.format(mesh, v) for v in order]
        mapped = helpers.ListToPerVerts(root_names) or {}
        selected = set(root_names)
        target_to_source = {}
        conflicts = 0
        for source, targets in mapped.items():
            # NLTA_Mesh.ListToPerVerts should return sources from root_names.
            source_id_match = _VTX.search(source)
            if not source_id_match:
                continue
            source = '{}.vtx[{}]'.format(mesh, source_id_match.group(1))
            if source not in profile:
                continue
            source_point = points[int(source_id_match.group(1))]
            for target in targets or []:
                match = _VTX.search(target)
                if not match:
                    continue
                target = '{}.vtx[{}]'.format(mesh, match.group(1))
                if target in selected:
                    continue
                target_id = int(match.group(1))
                if target_id >= len(points):
                    continue
                point = points[target_id]
                dist_sq = sum((float(point[i]) - float(source_point[i])) ** 2
                              for i in range(3))
                old = target_to_source.get(target)
                # Stable resolution if perpendicular edge loops intersect.
                if old is not None:
                    conflicts += 1
                if old is None or (dist_sq, source) < old:
                    target_to_source[target] = (dist_sq, source)
        if not target_to_source:
            raise ValueError('Skin Parent: no perpendicular target loops found; '
                             'check topology and NLTA_Mesh.ListToPerVerts()')
        samples = dict(profile)
        for vertex, (_, source) in target_to_source.items():
            samples[vertex] = profile[source]
        return samples, segments, len(root_names), len(target_to_source), conflicts
    finally:
        cmds.setAttr(env, old_envelope)


def _skirt_parent_weight_plan(skin, samples, parent, children, graph):
    """Transfer parent pool into nearest-joint territory, then calculate blend.

    Only the explicitly chosen parent and skirt joint influences are changed;
    their original combined sum is conserved for EACH vertex. Wrong-neighbour
    weights are folded into the appropriate owner/adjacent pair (seam cleanup).
    Other influences are untouched. There is one Maya write per vertex.
    """
    plan = {}
    midpoints = 0
    total_sampled = 0
    group = [parent] + list(children)
    for vertex, region in samples.items():
        old = _get_pair_pool(skin, vertex, group)
        pool = sum(old.values())
        if pool <= _EPS:
            continue
        total_sampled += 1
        updated = {joint: 0.0 for joint in group}
        pair = region['pair']
        if pair:
            left, right = pair
            t = region['t']
            value = float(GetGraphValue(t, graph))
            value = max(0.0, min(1.0, value))
            updated[left] = pool * (1.0 - value)
            updated[right] = pool * value
            midpoints += 1
        else:
            updated[region['owner']] = pool
        if any(abs(updated[j] - old[j]) > 1e-7 for j in group):
            plan[vertex] = updated
    return plan, total_sampled, midpoints


def SkirtParentRun(data, *args):
    """Skirt Parent using real neighbouring joint intervals + seam cleanup.

    1) Resolve a single root loop in rest pose, once.
    2) Each skirt joint owns the interval bounded by actual geometric midpoints
       between its anchor and those of its two neighbouring joints.
    3) Smooth only between adjacent joint anchors with the edited Graph shape.
    4) Propagate to perpendicular vertex loops, clear wrong-neighbour influences
       and any remaining original Parent weight inside that covered skirt area.
    """
    m = _get_skirt_mesh_helpers()
    mesh = _require_mesh(data['mesh'])
    skin = _skin(mesh)
    parent = _canonical(data['jointParent'])
    children = [_canonical(j) for j in data['joints']]
    _validate_joints(skin, [parent] + children)
    if len(children) < 2:
        raise ValueError('Skin Parent requires at least 2 skirt joints')
    with _transaction('NLTA Skirt Parent'):
        samples, segments, root_count, propagated, overlaps = _skirt_parent_regions(
            mesh, skin, children, m)
        plan, sampled, blended = _skirt_parent_weight_plan(
            skin, samples, parent, children, data.get('graph'))
        changed = _apply_plan(skin, plan)
    print('[NLTA Skin Parent] root={} | propagated={} | overlap={} | '
          'weighted={} | blend={} | changed={}'.format(
              root_count, propagated, overlaps, sampled, blended, changed))
    print('[NLTA Skin Parent] joint distances / root arc lengths (world units): {}'.format(segments))
    if changed:
        _refresh(mesh)
    return changed


def SkirtParent(data=None, *args):
    return SkirtParentRun(data or _inputs_skirt_parent())


def _chains_from_selected(joints):
    selected = set(joints)
    roots = []
    for joint in joints:
        parent = cmds.listRelatives(joint, parent=True, type='joint', fullPath=True) or []
        if not parent or _canonical(parent[0]) not in selected:
            roots.append(joint)
    result = []
    def walk(joint, path):
        children = cmds.listRelatives(joint, children=True, type='joint', fullPath=True) or []
        children = [_canonical(child) for child in children if _canonical(child) in selected]
        if not children:
            result.append(path + [joint])
        for child in children:
            walk(child, path + [joint])
    for root in roots:
        walk(root, [])
    return [chain for chain in result if len(chain) > 1]


def _skirt_children_parent_side(mesh, segments, mesh_helpers):
    """Find child-weight leaks on the PARENT side of each blend, at rest pose.

    Works from the current joint direction and the rest-pose mesh. Only vertices
    strictly BEFORE a segment's parent joint are eligible. Vertices belonging
    to the intended transfer or smoothed/perpendicular regions are protected,
    including the neighbouring segment's blend when the child is itself a parent.

    Returns vertex names, NOT weight edits. Called with envelope=0, so it does
    not depend on the current skirt pose. Weight queries/writes happen later.
    """
    m = mesh_helpers
    # Maya MFnMesh returns all points in one API call (avoid thousands of cmds.xform).
    fn = m.GetMeshFn(mesh)
    points = fn.getPoints(m.om.MSpace.kWorld)
    adjacency = {}
    # Cache topology while the envelope is OFF, before any weight writes.
    edge_count = getattr(fn, 'numEdges', None)
    if isinstance(edge_count, int) and edge_count > 0:
        for edge_index in range(edge_count):
            a, b = fn.getEdgeVertices(edge_index)
            adjacency.setdefault(int(a), set()).add(int(b))
            adjacency.setdefault(int(b), set()).add(int(a))

    # Each joint can participate in two smooth regions (as parent/child).
    # Protect both; otherwise cleanup for a middle child erases an earlier blend.
    protected = {}
    for seg in segments:
        smooth = set(seg['smooth_vertices'])
        perpendicular = m.ListToPerVerts(seg['smooth_vertices']) or {}
        for loop in perpendicular.values():
            smooth.update(loop or [])
        for joint in (seg['parent'], seg['child']):
            protected.setdefault(joint, set()).update(smooth)
        protected.setdefault(seg['child'], set()).update(seg['transfer_targets'])

    for seg in segments:
        parent = seg['parent']
        child = seg['child']
        a = cmds.xform(parent, q=True, ws=True, t=True)
        b = cmds.xform(child, q=True, ws=True, t=True)
        direction = [float(b[i]) - float(a[i]) for i in range(3)]
        axis_length_sq = sum(x * x for x in direction)
        if axis_length_sq <= _EPS:
            raise ValueError('Skirt Children: parent and child share a position: '
                             '{} -> {}'.format(parent, child))
        safe = protected.get(child, set())
        candidates = []
        spike_candidates = []
        for index, point in enumerate(points):
            projection = sum((float(point[i]) - float(a[i])) * direction[i]
                             for i in range(3))
            v = '{}.vtx[{}]'.format(mesh, index)
            # Long-smooth and perpendicular regions are protected from the
            # broad parent-side cleanup, but NOT from a proven single-point
            # outlier check. Only look on the parent's half of the pair.
            if v in safe and projection < 0.5 * axis_length_sq:
                spike_candidates.append(v)
            # Dot < 0 is on the parent side of the transition start.
            if projection < -1e-6 * axis_length_sq and v not in safe:
                candidates.append(v)
        seg['parent_leak_candidates'] = candidates
        seg['spike_candidates'] = spike_candidates
        seg['vertex_adjacency'] = adjacency
    return segments


def _skirt_children_regions(mesh, skin, chains, mesh_helpers):
    """Resolve ALL strip / perpendicular regions in the undeformed mesh pose.

    Following the legacy SkirtChains algorithm:
      - one root joint-edge loop and farthest edge per chain;
      - child-to-farthest strip with child's own edge excluded;
      - perpendicular target loops from ListToPerVerts(strip).

    Returns topology only. No weight changes or queries while envelope is off.
    """
    m = mesh_helpers
    envelope = skin + '.envelope'
    previous = cmds.getAttr(envelope)
    prepared = []
    try:
        cmds.setAttr(envelope, 0)
        for chain in chains:
            chain_prepared = []
            pin = m.GetClosestVertex(mesh, chain[0])
            root_loop = m.GetJointEdgeLoop(mesh, chain[0], pin) or []
            if not root_loop:
                raise ValueError('Skirt Children: no joint edge loop for {}'.format(chain[0]))
            root_edge = m.GetClosestEdge(mesh, root_loop, chain[0])
            farthest = m.GetFarthestEdge(mesh, root_edge, root_loop)
            if farthest is None:
                raise ValueError('Skirt Children: cannot find farthest edge for {}'.format(chain[0]))

            for index in range(len(chain) - 1):
                parent = chain[index]
                child = chain[index + 1]
                parent_edge = m.GetClosestEdge(mesh, root_loop, parent)
                current_edge = m.GetClosestEdge(mesh, root_loop, child)
                if parent_edge is None or current_edge is None:
                    raise ValueError('Skirt Children: missing edge for {} -> {}'.format(parent, child))

                # Match legacy transfer: remove the child's closest edge,
                # then follow the original FARTHEST edge (never recalculate it).
                transfer_path = list(m.EdgesBetween(mesh, current_edge, farthest) or [])
                if not transfer_path:
                    raise ValueError('Skirt Children: cannot trace child-to-farthest '
                                     'path for {} -> {}'.format(parent, child))
                distal_edges = [edge for edge in transfer_path if edge != current_edge]
                strip = m.VertexFromEdges(mesh, distal_edges) if distal_edges else []
                mapping = (m.ListToPerVerts(strip) or {}) if strip else {}
                # All mapped perpendicular loops form ONE hard transfer region.
                targets = []
                seen = set()
                for loop_verts in mapping.values():
                    for vertex in loop_verts or []:
                        if vertex not in seen:
                            seen.add(vertex)
                            targets.append(vertex)
                if distal_edges and not targets:
                    raise ValueError('Skirt Children: failed to find perpendicular '
                                     'target loops for {} -> {}'.format(parent, child))

                # Legacy smoothing extends through the CHILD and ends at the
                # child's child (or the original farthest edge on the last pair).
                # The child receives its full distal transfer BEFORE this blend.
                next_edge = (m.GetClosestEdge(mesh, root_loop, chain[index + 2])
                             if index + 2 < len(chain) else farthest)
                if next_edge is None:
                    raise ValueError('Skirt Children: missing next-child edge for '
                                     '{} -> {}'.format(parent, child))
                smooth_path = list(m.EdgesBetween(mesh, parent_edge, next_edge) or [])
                if not smooth_path:
                    raise ValueError('Skirt Children: no smoothing strip for '
                                     '{} -> {}'.format(parent, child))
                smooth = m.VertexFromEdges(mesh, smooth_path) or []
                if not smooth:
                    raise ValueError('Skirt Children: smoothing strip has no vertices '
                                     'for {} -> {}'.format(parent, child))
                chain_prepared.append({
                    'mesh': mesh,
                    'parent': parent,
                    'child': child,
                    'farthest': farthest,
                    'current_edge': current_edge,
                    'smooth_end_edge': next_edge,
                    'distal_edges': distal_edges,
                    'transfer_targets': targets,
                    'smooth_vertices': smooth,
                })

            # Do NOT undo the freshly blended overlap from childEdge to
            # nextChildEdge. Only force parent=0 on perpendicular loops BEYOND
            # the smooth end, i.e. the next segment's distal transfer region.
            # On the last segment smoothing reaches the farthest edge: there is
            # no additional hard-ownership strip beyond that edge.
            for index, segment in enumerate(chain_prepared):
                segment['cleanup_targets'] = (
                    list(chain_prepared[index + 1]['transfer_targets'])
                    if index + 1 < len(chain_prepared) else [])
            prepared.extend(chain_prepared)

        # Cache regions BEFORE skin edits and with the undeformed positions.
        # Keep this separate from distal hard ownership cleanup below.
        _skirt_children_parent_side(mesh, prepared, m)
    finally:
        cmds.setAttr(envelope, previous)
    return prepared


def _skirt_child_gradient(mesh, vertices, parent, child, graph):
    """Blend parent to child through the next child edge, then copy across.

    Unlike Skirt Parent, the parent's gradient is the main influence, matching
    the old SkirtChains() which called ActiveJoint(mesh, parentJoint).
    """
    skin, gradient = _gradient_plan(mesh, vertices, parent, [child], graph)
    smoothed = _apply_plan(skin, gradient)
    skin, perpendicular = _topology_ratio_plan(mesh, vertices, [parent, child])
    copied = _apply_plan(skin, perpendicular)
    return smoothed, copied


def _skirt_child_leak_plan(skin, segments, threshold=1e-6):
    """Return a child -> parent transfer plan for proven parent-side leaks.

    Only child weights are transferred; other influences remain untouched.
    Prepare ONE consolidated plan after every smooth pass is complete.
    """
    plan = {}
    # Deeper leaks must climb through ancestors in order; otherwise a J2 leak
    # can be handed to J1 AFTER we have already cleared J1 from the same vertex.
    for seg in reversed(segments):
        parent, child = seg['parent'], seg['child']
        for vertex in seg.get('parent_leak_candidates', []):
            child_weight = _weight(skin, vertex, child)
            if child_weight <= threshold:
                continue
            # Merge against earlier proposed edits if strips overlap.
            row = plan.setdefault(vertex, {})
            old_child = row.get(child, _weight(skin, vertex, child))
            old_parent = row.get(parent, _weight(skin, vertex, parent))
            if old_child <= threshold:
                continue
            row[parent] = old_parent + old_child
            row[child] = 0.0
    return plan



def _skirt_child_isolated_spike_plan(mesh, skin, segments, helpers,
                                     minimum=0.03, neighbor_ratio=0.25):
    """Return child weight of ONE-VERTEX outliers to its direct parent.

    A child weight inside a legitimate smooth region is never cleared merely
    because it is upstream of the child: we inspect its true connected Maya
    mesh neighbours. The point must be on the PARENT's half of the pair, have
    at least two mesh neighbours, and EVERY neighbour must have far less of
    that child's influence. This is a cleanup for isolated dots, not a general
    smoothing/filter operation.

    Vertex connectivity is topological, independent of the current skin pose.
    Does not read or alter other influences. If topology cannot be examined,
    conservatively skip cleanup rather than silently editing a different area.
    """
    all_candidates = set()
    for segment in segments:
        all_candidates.update(segment.get('spike_candidates', []))
    if not all_candidates:
        return {}

    adjacency = segments[0].get('vertex_adjacency', {})
    if not adjacency:
        return {}

    weight_cache = {}
    proposed = {}

    def current_weight(vertex, joint):
        row = proposed.get(vertex)
        if row is not None and joint in row:
            return row[joint]
        key = (vertex, joint)
        if key not in weight_cache:
            weight_cache[key] = _weight(skin, vertex, joint)
        return weight_cache[key]

    for segment in reversed(segments):
        parent, child = segment['parent'], segment['child']
        for vertex in segment.get('spike_candidates', []):
            match = _VTX.search(vertex)
            if not match:
                continue
            vertex_id = int(match.group(1))
            neighbors = adjacency.get(vertex_id, ())
            if len(neighbors) < 2:
                continue
            child_weight = current_weight(vertex, child)
            if child_weight < minimum:
                continue
            neighbor_weights = [
                current_weight('{}.vtx[{}]'.format(mesh, n), child)
                for n in neighbors
            ]
            # A continuous falloff has adjacent vertices sharing child weight.
            # An isolated hot pixel is substantially stronger than ALL of them.
            if max(neighbor_weights) > max(0.005, child_weight * neighbor_ratio):
                continue
            row = proposed.setdefault(vertex, {})
            row[parent] = current_weight(vertex, parent) + child_weight
            row[child] = 0.0

    return proposed


def SkirtChains(data=None, *args, **kwargs):
    """Transfer parent weight below child, then smooth the chain.

    Like the original SkirtChains, use unlocked bound joints by default.
    Explicitly picked Chain Joints override that selection when provided.
    The blend reaches the next child; only geometry beyond it is hard-owned.
    """
    m = _get_skirt_mesh_helpers()
    data = data or _inputs_chains()
    mesh = _require_mesh(data['mesh'])
    skin = _skin(mesh)
    picked = data.get('joints') or []
    # Legacy Skin Children operates on the unlocked bound influence hierarchy.
    # Picking Chain Joints is an optional override, not a required input.
    joints = (_validate_joints(skin, picked) if picked
              else _unlocked_joints(_influences(skin)))
    chains = _chains_from_selected(joints)
    if not chains:
        source = 'picked' if picked else 'unlocked'
        raise ValueError(
            'Skin Children: no connected parent-child pair among {} joints. '
            'Unlock the parent and child influences, or Pick a connected chain.'
            .format(source))

    # Before ANY weight change, cache every strip in the bind/rest geometry.
    regions = _skirt_children_regions(mesh, skin, chains, m)
    changed = 0
    with _transaction('NLTA Skirt Children'):
        for segment in regions:
            parent = segment['parent']
            child = segment['child']
            targets = segment['transfer_targets']

            # Stage 1: exact transfer of parent -> child on ALL perpendicular
            # loops below the child's nearest edge (not just a sampled row).
            transferred = 0
            if targets:
                skin, transfer = _transfer_plan(mesh, targets, parent, child)
                transferred = _apply_plan(skin, transfer)
                changed += transferred

            # Stage 2: smooth from the PARENT up to the NEXT CHILD's edge,
            # or to farthestEdge for the final segment, as in the legacy tool.
            smooth_count, ratio_count = _skirt_child_gradient(
                mesh, segment['smooth_vertices'], parent, child,
                data.get('graph'))
            changed += smooth_count + ratio_count

            # Stage 3: preserve the newly-smoothed child/next-child overlap.
            # Remove parent weight ONLY beyond the smooth end; cleaning every
            # original transfer target erased the intended longer influence.
            hard_targets = segment['cleanup_targets']
            cleaned = 0
            if hard_targets:
                skin, cleanup = _transfer_plan(mesh, hard_targets, parent, child)
                cleaned = _apply_plan(skin, cleanup)
                changed += cleaned
            print('[NLTA Skin Children] {} -> {} | distal={} | transfer={} | '
                  'smooth={} | ratio={} | hard={} | cleanup={}'.format(
                      parent, child, len(targets), transferred,
                      smooth_count, ratio_count, len(hard_targets), cleaned))

        # Stage 4: parent-side leak cleanup AFTER all overlapping smooth passes.
        # The previous hard ownership step moves parent -> child on the FAR side.
        # This inverse cleanup moves child -> parent only BEFORE the blend start.
        leak_plan = _skirt_child_leak_plan(skin, regions)
        leak_count = _apply_plan(skin, leak_plan)
        changed += leak_count
        print('[NLTA Skin Children] Parent-side child leak cleaned: {} vertex(s)'
              .format(leak_count))

        # Stage 5: one-point spikes can be inside the legitimate long-Smooth
        # region, which the broad stage-4 cleanup MUST keep protected.
        # Check connected-neighbour child weights, and return only truly
        # isolated child dots on the parent's side to the parent.
        spike_plan = _skirt_child_isolated_spike_plan(mesh, skin, regions, m)
        spike_count = _apply_plan(skin, spike_plan)
        changed += spike_count
        print('[NLTA Skin Children] Isolated child-weight dots returned to parent: '
              '{} vertex(s){}'.format(spike_count,
                  ' | ' + ', '.join(sorted(spike_plan)[:8]) if spike_plan else ''))
    if changed:
        _refresh(mesh)
    return changed


# ---------------------------- Live Smooth ----------------------------

def _stop_live_smooth():
    """Stop an old session when inputs/UI change or another tool writes skin."""
    global _SMOOTH_LIVE
    _SMOOTH_LIVE = None
    if _UI:
        timer = _UI.get('smooth_timer')
        if timer is not None:
            try:
                timer.stop()
            except RuntimeError:  # Maya may have deleted the QWidget
                pass


def _queue_live_smooth():
    """Called by NLTA_UI's Graph onChange. Debounce the heavy Maya writes."""
    if not _SMOOTH_LIVE or _SMOOTH_LIVE.get('running'):
        return
    graph = GetGraph()
    payload = graph.get('graph', graph) if isinstance(graph, dict) else None
    if not isinstance(payload, dict):
        return
    timer = _UI.get('smooth_timer') if _UI else None
    if timer is None and _UI:
        qt = payload.get('qt')
        widget = payload.get('widget')
        if qt and widget is not None:
            # QTimer belongs to the Graph QWidget and cannot outlive Maya UI.
            timer = qt[0].QTimer(widget)
            timer.setSingleShot(True)
            timer.timeout.connect(_apply_live_smooth)
            _UI['smooth_timer'] = timer
    if timer is not None:
        timer.start(180)
    else:
        # Headless/mock embedding only; real Maya Graph always has Qt.
        _apply_live_smooth()


def _apply_live_smooth():
    """Re-evaluate LIVE Graph on the initial pre-Smooth weight snapshot."""
    session = _SMOOTH_LIVE
    if not session or session.get('running'):
        return 0
    # No effect once the main/picker window has been replaced or closed.
    if _UI and not cmds.window(_UI['window'], exists=True):
        _stop_live_smooth()
        return 0
    session['running'] = True
    try:
        skin = session['skin']
        graph = session['graph']
        main = session['main']
        others = session['others']
        joints = session['joints']
        plan = {}
        for vertex, (ratio, initial_weights) in session['samples'].items():
            new = _gradient_weights(initial_weights, main, others,
                                    GetGraphValue(ratio, graph))
            if new is None:
                continue
            current = _get_pair_pool(skin, vertex, joints)
            if any(abs(new[j]-current[j]) > 1e-7 for j in joints):
                plan[vertex] = new
        if not plan:
            return 0
        with _transaction('NLTA Live Smooth Graph'):
            changed = _apply_plan(skin, plan)
        if changed:
            _refresh(session['mesh'])
            operation = session.get('operation', 'smooth')
            _status('{}: {} vertices updated'.format(
                    ('Radial Live Smooth' if operation == 'radial' else
                     'Distance Live Smooth' if operation == 'distance' else 'Live Smooth'),
                    changed), operation)
        return changed
    except Exception as error:
        _stop_live_smooth()
        cmds.warning('NLTA Live Smooth disabled: {}'.format(error))
        _status('Live Smooth stopped: {}'.format(error),
                session.get('operation', 'smooth'))
        return 0
    finally:
        session['running'] = False


# ----------------------- compact UI and pick dialogs -----------------------

_PICK_FIELDS = {
    'smooth': [
        ('mainJoint', 'Main Joint', 'joint'),
        ('blendJoints', 'Blend Joints', 'joints'),
        ('vertices', 'Vertices (first = origin)', 'vertices'),
    ],
    'parent': [
        ('mesh', 'Mesh', 'mesh'),
        ('jointParent', 'Parent Joint', 'joint'),
        ('joints', 'Skirt Joints', 'joints'),
    ],
    'children': [
        ('mesh', 'Mesh', 'mesh'),
        ('joints', 'Chain Joints (optional: unlocked if empty)', 'joints'),
    ],
    'plane': [
        ('vertices', 'Reference Vertices (2+)', 'source_vertices'),
        ('targetVertices', 'Affected Vertices', 'vertices'),
    ],
    'radial': [
        ('originVertex', 'Origin Vertex', 'vertex'),
        ('baseJoint', 'Base Joint', 'joint'),
        ('mainJoint', 'Main Joint', 'joint'),
    ],
    'distance': [
        ('object', 'Object (distance origin)', 'object'),
        ('vertices', 'Vertices', 'vertices'),
        ('parentJoint', 'Parent Joint', 'joint'),
        ('childJoint', 'Child Joint', 'joint'),
    ],
}


def _status(message, operation=None):
    """Status is displayed in the main graph and relevant pick dialog."""
    message = str(message)[:200]
    if _UI and _UI.get('status'):
        try:
            cmds.text(_UI['status'], e=True, label=message)
        except RuntimeError:
            pass
    state = _DIALOGS.get(operation)
    if state and state.get('status'):
        try:
            cmds.text(state['status'], e=True, label=message)
        except RuntimeError:
            pass


def _selection_joints():
    selected = cmds.ls(orderedSelection=True, long=True) or cmds.ls(sl=True, long=True) or []
    return [node for node in selected if cmds.nodeType(node) == 'joint']


def _pick_state(operation):
    state = _DIALOGS.get(operation)
    if not state:
        raise ValueError('Open the {} picker first'.format(operation))
    return state


def _plane_source_mesh(sources):
    """Resolve a single polygon mesh from the picked reference vertices."""
    if not isinstance(sources, (list, tuple)) or len(sources) < 2:
        raise ValueError('Copy Ratio Plane: Pick at least two Reference Vertices')
    if any(not isinstance(v, str) or not _VTX.search(v) for v in sources):
        raise ValueError('Copy Ratio Plane: Reference must contain vertices only')
    mesh = _require_mesh(_mesh_of(sources[0]))
    if any(_mesh_of(v) != mesh for v in sources[1:]):
        raise ValueError('Copy Ratio Plane: all Reference Vertices must be on the same mesh')
    return mesh


def _capture(operation, key, kind, *args):
    state = _pick_state(operation)
    # The Smooth picker is order-sensitive. Maya's ordinary selection query may
    # return component indices in sorted order rather than click order.
    if operation == 'smooth' and key == 'vertices':
        pref = getattr(cmds, 'selectPref', None)
        if pref and not pref(query=True, trackSelectionOrder=True):
            cmds.warning('NLTA Smooth: enable Track Selection Order, then reselect vertices')
            return
        selection = cmds.ls(orderedSelection=True, flatten=True, long=True) or []
    else:
        selection = cmds.ls(sl=True, flatten=True, long=True) or []
    try:
        if kind == 'mesh':
            if not selection:
                raise ValueError('Select a mesh')
            result = _require_mesh(selection[0].split('.', 1)[0])
        elif kind == 'object':
            if len(selection) != 1:
                raise ValueError('Distance Smooth: Select exactly one Object')
            picked = _canonical(selection[0].split('.', 1)[0])
            if cmds.nodeType(picked) in ('mesh', 'nurbsCurve', 'nurbsSurface', 'locator'):
                parents = cmds.listRelatives(picked, parent=True, fullPath=True) or []
                if not parents:
                    raise ValueError('Distance Smooth: Select an object with a transform')
                picked = _canonical(parents[0])
            result = picked
        elif kind == 'joint':
            joints = _selection_joints()
            if len(joints) != 1:
                raise ValueError('Select exactly one joint')
            result = _canonical(joints[0])
        elif kind == 'joints':
            result = list(dict.fromkeys(_canonical(j) for j in _selection_joints()))
            if not result:
                raise ValueError('Select at least one joint')
        else:
            if operation == 'radial' and kind == 'vertex':
                if len(selection) != 1 or not _VTX.search(selection[0]):
                    raise ValueError('Radial Smooth: Pick exactly ONE vertex')
                mesh = _require_mesh(_mesh_of(selection[0]))
            elif operation == 'plane':
                if kind == 'source_vertices':
                    if not selection or any(not _VTX.search(v) for v in selection):
                        raise ValueError('Copy Ratio Plane: select at least two Reference Vertices')
                    mesh = _plane_source_mesh(selection)
                else:
                    mesh = _plane_source_mesh(state['data'].get('vertices'))
            elif operation == 'distance' and key == 'vertices':
                if not selection or not _VTX.search(selection[0]):
                    raise ValueError('Distance Smooth: Select vertices of one mesh')
                mesh = _require_mesh(_mesh_of(selection[0]))
            elif operation == 'smooth' and key == 'vertices':
                # Smooth uses the first picked vertex as its spatial origin,
                # and infers its mesh without a separate Mesh field.
                if not selection or not _VTX.search(selection[0]):
                    raise ValueError('Smooth: select vertices, FIRST vertex is origin')
                mesh = _require_mesh(_mesh_of(selection[0]))
            else:
                mesh = state['data'].get('mesh')
                if not mesh:
                    raise ValueError('Capture Mesh before capturing components')
            if operation == 'smooth' and key == 'vertices':
                if not selection or any(not _VTX.search(v) for v in selection):
                    raise ValueError('Smooth requires ordered VERTEX selection; select the origin FIRST')
                # Preserve click order even if polyListComponentConversion
                # would reorder vertices. Resolve mesh paths without sorting.
                mesh = _require_mesh(mesh)
                result = []
                seen = set()
                for vertex in selection:
                    if _mesh_of(vertex) != mesh:
                        raise ValueError('Smooth vertices must belong to the same mesh')
                    vertex = '{}.vtx[{}]'.format(mesh, _VTX.search(vertex).group(1))
                    if vertex not in seen:
                        seen.add(vertex)
                        result.append(vertex)
                if len(result) < 2:
                    raise ValueError('Smooth requires at least 2 different vertices')
            elif operation == 'radial' and kind == 'vertex':
                result = _vertices(mesh, selection)
                if len(result) != 1:
                    raise ValueError('Radial Smooth: Pick exactly one vertex')
                result = result[0]
            elif kind == 'source_vertices':
                # _plane_source_mesh() already validates source count/type/mesh.
                result = _vertices(mesh, selection)
                if len(result) < 2:
                    raise ValueError('Copy Ratio Plane requires at least 2 distinct Reference Vertices')
            else:
                result = _vertices(mesh, selection)
                if not result:
                    raise ValueError('Select vertices, edges or faces of captured mesh')
        if operation in ('smooth', 'radial', 'distance'):
            _stop_live_smooth()
        state['data'][key] = result
        if operation == 'plane' and key == 'vertices':
            # Re-picking references on a different mesh invalidates old targets.
            previous_mesh = state.get('mesh')
            state['mesh'] = mesh
            targets = state['data'].get('targetVertices') or []
            if targets and (previous_mesh != mesh or any(_mesh_of(v) != mesh for v in targets)):
                state['data']['targetVertices'] = []
                _render_capture(operation, 'targetVertices')
        _render_capture(operation, key)
        _status('Captured {}'.format(key), operation)
        # Radius/mode don't touch weights until the first Apply.
    except (ValueError, RuntimeError) as error:
        cmds.warning('NLTA Graph Skinning: {}'.format(error))
        _status(error, operation)


def _render_capture(operation, key):
    """Show picked items in the field; empty displays its title as placeholder."""
    state = _pick_state(operation)
    value = state['data'].get(key)
    if isinstance(value, list):
        if not value:
            display = ''
        else:
            preview = ', '.join(str(v).split('|')[-1] for v in value[:2])
            display = '{} item(s): {}{}'.format(len(value), preview,
                                                ' ...' if len(value) > 2 else '')
        # Keep Maya tooltips lightweight even when thousands of vertices are picked.
        description = '\n'.join(map(str, value[:12]))
        if len(value) > 12:
            description += '\n... ({} more)'.format(len(value) - 12)
    else:
        display = str(value).split('|')[-1] if value else ''
        description = str(value or '')
    cmds.textField(state['labels'][key], edit=True, text=display,
                   annotation=description or state['titles'][key])


def _clear(operation, key, *args):
    state = _pick_state(operation)
    if operation in ('smooth', 'radial', 'distance'):
        _stop_live_smooth()
    if operation == 'radial' and key == 'originVertex':
        _stop_radial_radius_timer(state)
    state['data'][key] = [] if key in state['lists'] else None
    if operation == 'plane' and key == 'vertices':
        # Affected vertices are tied to the reference vertices' mesh.
        state['mesh'] = None
        state['data']['targetVertices'] = []
        _render_capture(operation, 'targetVertices')
    _render_capture(operation, key)


def _field(operation, parent, key, label, kind):
    """Compact picker row: [selected value / placeholder] [Pick] [Clear]."""
    row = cmds.rowLayout(numberOfColumns=3, adjustableColumn=1,
                         columnWidth=[(2, 65), (3, 48)], parent=parent)
    info = cmds.textField(parent=row, text='', editable=False,
                          placeholderText=label, height=28,
                          annotation=label)
    _DIALOGS[operation]['labels'][key] = info
    _DIALOGS[operation]['titles'][key] = label
    cmds.button(label='Pick', parent=row, width=65,
                command=lambda *_: _capture(operation, key, kind))
    cmds.button(label='Clear', parent=row, width=48,
                command=lambda *_: _clear(operation, key))
    cmds.setParent('..')
    return row


def _inputs_gradient():
    d = _pick_state('smooth')['data']
    vertices = d.get('vertices') or []
    if len(vertices) < 2:
        raise ValueError('Smooth: Pick at least 2 ordered Vertices (origin first)')
    mesh = _require_mesh(_mesh_of(vertices[0]))
    if any(_mesh_of(v) != mesh for v in vertices[1:]):
        raise ValueError('Smooth: all Vertices must belong to one mesh')
    return {'mesh': mesh, 'vertices': vertices,
            'mainJoint': d['mainJoint'], 'blendJoints': d['blendJoints'],
            'graph': GetGraph()}



def _inputs_distance():
    d = _pick_state('distance')['data']
    vertices = d.get('vertices') or []
    if len(vertices) < 2:
        raise ValueError('Distance Smooth: Pick at least 2 Vertices')
    mesh = _require_mesh(_mesh_of(vertices[0]))
    if any(_mesh_of(vertex) != mesh for vertex in vertices[1:]):
        raise ValueError('Distance Smooth: all Vertices must belong to one mesh')
    if not d.get('object'):
        raise ValueError('Distance Smooth: Pick Object first')
    if not d.get('parentJoint') or not d.get('childJoint'):
        raise ValueError('Distance Smooth: Pick Parent Joint and Child Joint')
    return {'object': d['object'], 'mesh':mesh, 'vertices':vertices,
            'parentJoint':d['parentJoint'], 'childJoint':d['childJoint'],
            'graph':GetGraph()}


def _radial_range_inputs():
    """Geometry inputs for Radial Smooth and live Radius changes."""
    state = _pick_state('radial')
    origin = state['data'].get('originVertex')
    if not origin or not _VTX.search(origin):
        raise ValueError('Radial Smooth: Pick one Origin Vertex')
    mesh = _require_mesh(_mesh_of(origin))
    radius_text = cmds.textField(state['radiusField'], query=True, text=True).strip()
    try:
        radius = float(radius_text)
    except (TypeError, ValueError):
        raise ValueError('Radial Smooth: Radius must be a positive number')
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError('Radial Smooth: Radius must be greater than zero')
    mode = cmds.optionMenu(state['modeMenu'], query=True, value=True).lower()
    if mode not in ('surface', 'sphere'):
        raise ValueError('Radial Smooth: invalid spread mode')
    return {'mesh': mesh, 'originVertex': origin, 'radius': radius, 'mode': mode}


def _inputs_radial():
    data = _radial_range_inputs()
    data.update({'baseJoint': _pick_state('radial')['data'].get('baseJoint'),
                 'mainJoint': _pick_state('radial')['data'].get('mainJoint'),
                 'graph': GetGraph()})
    return data


def PreviewRadialSmooth(data=None, select=True, *args):
    """Preview only the Radius selection. Does NOT change any skin weights.

    The preview needs only an Origin Vertex, Radius and mode (Surface/Sphere).
    If select=True, Maya selects the affected vertices so the footprint is
    visible in the viewport. Base/Main joints are checked only by Apply.
    """
    data = _radial_range_inputs() if data is None else data
    origin = data['originVertex']
    mesh = _require_mesh(_mesh_of(origin))
    if data.get('mesh') and _require_mesh(data['mesh']) != mesh:
        raise ValueError('Radial Smooth: Mesh differs from origin vertex')
    source = _vertices(mesh, [origin])
    if len(source) != 1:
        raise ValueError('Radial Smooth: Pick one Origin Vertex')
    skin = _skin(mesh)
    distances = _radial_geometry(mesh, skin, source[0],
                                 data['radius'], data.get('mode', 'sphere'))
    vertices = ['{}.vtx[{}]'.format(mesh, index) for index in sorted(distances)]
    if select and vertices:
        cmds.select(vertices, replace=True)
    return {'mesh': mesh, 'vertices': vertices, 'count': len(vertices),
            'radius': float(data['radius']), 'mode': data.get('mode', 'sphere')}


def _stop_radial_radius_timer(state=None):
    state = state if state is not None else _DIALOGS.get('radial')
    timer = state.get('radius_timer') if state else None
    if timer is not None:
        try:
            timer.stop()
        except (RuntimeError, ReferenceError):
            pass


def _queue_radial_radius_update(*args):
    """Debounced LIVE WEIGHT update after Apply, never preview/select vertices."""
    session = _SMOOTH_LIVE
    if not session or session.get('operation') != 'radial':
        return
    state = _DIALOGS.get('radial')
    if not state:
        return
    timer = state.get('radius_timer')
    if timer is None:
        payload = _graph(GetGraph())
        if isinstance(payload, dict):
            qt = payload.get('qt')
            widget = payload.get('widget')
            if qt and widget is not None:
                timer = qt[0].QTimer(widget)
                timer.setSingleShot(True)
                timer.timeout.connect(_apply_radial_radius_update)
                state['radius_timer'] = timer
    if timer is not None:
        timer.start(170)
    else:
        _apply_radial_radius_update()


def _inputs_skirt_parent():
    d = _pick_state('parent')['data']
    return {'mesh': d['mesh'], 'jointParent': d['jointParent'],
            'joints': d['joints'], 'graph': GetGraph()}


def _inputs_chains():
    d = _pick_state('children')['data']
    return {'mesh': d['mesh'], 'joints': d['joints'], 'graph': GetGraph()}


def _inputs_plane():
    state = _pick_state('plane')
    d = state['data']
    mesh = _plane_source_mesh(d.get('vertices'))
    targets = d.get('targetVertices') or []
    if not targets:
        raise ValueError('Copy Ratio Plane: Pick Affected Vertices first')
    targets = _vertices(mesh, targets)  # reject other-mesh components
    width_field = state.get('widthField')
    width_text = cmds.textField(width_field, query=True, text=True).strip() if width_field else ''
    try:
        width = float(width_text) if width_text else 0.0
    except ValueError:
        raise ValueError('Plane Width must be a number (empty or 0 = Auto)')
    if not math.isfinite(width) or width < 0.0:
        raise ValueError('Plane Width must be 0 (Auto) or a positive distance')
    return {'mesh': mesh, 'vertices': d['vertices'],
            'targetVertices': targets,
            'planeWidth': width if width > 0.0 else None}


def _run_ui(fn, title, operation=None):
    try:
        if operation not in ('smooth', 'distance'):
            _stop_live_smooth()
        result = fn()
        if isinstance(result, dict):
            count = result.get('changed', 0)
            print('{}: {} candidate vertices'.format(title, count))
        else:
            count = result
            print('{}: {} changed vertices'.format(title, count))
        _status('{}: {} vertex updates'.format(title, count), operation)
        return result
    except Exception as error:
        cmds.warning('NLTA {} failed: {}'.format(title, error))
        _status('{}: {}'.format(title, error), operation)
        return None


def _create_picker(operation, title, callback):
    """Create a small, separate cmds window for one operation's inputs."""
    if operation not in ('smooth', 'distance'):
        _stop_live_smooth()
    fields = _PICK_FIELDS[operation]
    window_name = _WINDOW + '_' + operation.title()
    previous = _DIALOGS.get(operation, {})
    previous_data = previous.get('data', {})
    if operation == 'radial' and previous.get('radiusField'):
        try:
            previous['radiusValue'] = cmds.textField(previous['radiusField'],
                                                    query=True, text=True)
            previous['spreadMode'] = cmds.optionMenu(previous['modeMenu'],
                                                      query=True, value=True)
        except RuntimeError:
            pass
    if operation == 'plane' and previous.get('widthField'):
        try:
            previous['planeWidth'] = cmds.textField(previous['widthField'],
                                                  query=True, text=True)
        except RuntimeError:
            previous['planeWidth'] = ''
    if operation == 'radial':
        _stop_radial_radius_timer(previous)
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)
    window = cmds.window(window_name, title=title,
                         sizeable=True, widthHeight=(525, 325 if operation == 'radial'
                                                    else 130 + 38*len(fields)))
    column = cmds.columnLayout(adjustableColumn=True, rowSpacing=7, parent=window)
    lists = {key for key, _, kind in fields if kind in ('joints', 'vertices', 'source_vertices')}
    state = {'window': window, 'data': {}, 'labels': {}, 'titles': {},
             'lists': lists, 'status': None}
    for key, _, _ in fields:
        state['data'][key] = previous_data.get(key, [] if key in lists else None)
    _DIALOGS[operation] = state
    tip = ('Skin Children: Pick Mesh. Leave Chain Joints empty to use unlocked '
           'influences, or Pick a specific parent-child chain.'
           if operation == 'children' else
           'For Smooth: select FIRST vertex as origin, then other vertices.'
           if operation == 'smooth' else
           'Pick Reference Vertices first; mesh is detected automatically. Then Pick Affected.'
           if operation == 'plane' else
           'Pick Object pivot, vertices and joints; near = Child, far = Parent. Graph edits are live.'
           if operation == 'distance' else
           'Pick objects in the viewport, then click Pick for each field.'
           if operation != 'radial' else
           'Apply once; Radius / mode / Graph update live. Reset sends 100% to Base.')
    cmds.text(label=tip, align='left', parent=column)
    for key, label, kind in fields:
        _field(operation, column, key, label, kind)
        _render_capture(operation, key)
    if operation == 'radial':
        state['radiusField'] = cmds.textField(
            text=str(previous.get('radiusValue', '5.0')), editable=True,
            placeholderText='Radius (world units)', height=28,
            annotation='After Apply, changing Radius updates radial skin weights live.',
            textChangedCommand=lambda *_: _queue_radial_radius_update(), parent=column)
        state['modeMenu'] = cmds.optionMenu(
            parent=column, height=29,
            annotation='Surface: distance across connected faces; Sphere: straight 3D radius',
            changeCommand=lambda *_: _queue_radial_radius_update())
        cmds.menuItem(label='Surface', parent=state['modeMenu'])
        cmds.menuItem(label='Sphere', parent=state['modeMenu'])
        cmds.optionMenu(state['modeMenu'], edit=True,
                        value=previous.get('spreadMode', 'Sphere'))
    if operation == 'plane':
        # A plain text field supports the same title-as-placeholder UI.
        # Blank input means automatic tolerance; validate when RUN is clicked.
        state['widthField'] = cmds.textField(
            text=str(previous.get('planeWidth') or ''), editable=True,
            placeholderText='Plane Width (0 = Auto)',
            annotation='Distance tolerance in world units; blank = Auto',
            height=28, parent=column)
    cmds.separator(style='in', height=8, parent=column)
    if operation == 'radial':
        row = cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, parent=column)
        cmds.button(label='Reset to Base', height=36, parent=row,
                    annotation='Set Base Joint to 100% in Radius; zero all other influences.',
                    command=lambda *_: _run_ui(ResetRadialToBase, 'Reset to Base', operation))
        cmds.button(label='Apply', height=36, parent=row,
                    annotation='Write skin weights with the current Radius and Graph.',
                    command=lambda *_: _run_ui(RadialSmooth, 'Radial Smooth', operation))
        cmds.setParent('..')
    else:
        cmds.button(label='RUN ' + title, height=36, parent=column,
                    command=lambda *_: _run_ui(callback, title, operation))
    state['status'] = cmds.text(label='Ready', align='left', height=32, parent=column)
    cmds.showWindow(window)
    return state


def CreateSmoothUI(*args):
    return _create_picker('smooth', 'Smooth Gradient', GradientActiveJoint)


def CreateDistanceSmoothUI(*args):
    return _create_picker('distance', 'Distance Smooth', DistanceSmooth)


def CreateRadialSmoothUI(*args):
    return _create_picker('radial', 'Radial Smooth', RadialSmooth)


def CreateCopyRatioPlaneUI(*args):
    """Open a separate picker for reference and affected vertices."""
    return _create_picker('plane', 'Copy Ratio Plane', CopyRatioPlaneWeight)


def CreateSkinParentUI(*args):
    return _create_picker('parent', 'Skin Parent', SkirtParent)


def CreateSkinChildrenUI(*args):
    return _create_picker('children', 'Skin Children', SkirtChains)


def CreateUI(*args):
    """Compact main window: shared Graph + actions, no pick fields."""
    global _UI
    _stop_live_smooth()
    _stop_radial_radius_timer()
    for state in list(_DIALOGS.values()):
        try:
            if cmds.window(state['window'], exists=True):
                cmds.deleteUI(state['window'])
        except RuntimeError:
            pass
    _DIALOGS.clear()
    # Make the one-click Copy Ratio deterministic for selections made after
    # opening the tool; Maya does not reliably preserve order otherwise.
    pref = getattr(cmds, 'selectPref', None)
    if pref and not pref(query=True, trackSelectionOrder=True):
        pref(trackSelectionOrder=True)
    if cmds.window(_WINDOW, exists=True):
        cmds.deleteUI(_WINDOW)
    window = cmds.window(_WINDOW, title='NLTA Graph Skinning',
                         sizeable=True, widthHeight=(510, 415))
    scroll = cmds.scrollLayout(childResizable=True, parent=window)
    column = cmds.columnLayout(adjustableColumn=True, rowSpacing=7, parent=scroll)
    _UI = {'window': window, 'graph': None, 'status': None}
    _UI['graph'] = CreateGraphUI(column, width=465, height=215, controls=True)
    cmds.separator(style='in', height=7, parent=column)
    row = cmds.rowLayout(numberOfColumns=3, adjustableColumn=1, parent=column)
    cmds.button(label='Smooth', height=33, parent=row,
                annotation='Select vertices (origin first), unlock exactly 2 joints, then Smooth.',
                command=lambda *_: _run_ui(SmoothUnlocked, 'Smooth', 'smooth'))
    cmds.button(label='Copy Ratio', height=33, parent=row,
                command=lambda *_: _run_ui(CopyRatioWeight, 'Copy Ratio'))
    cmds.button(label='Copy Ratio Plane', height=33, parent=row,
                command=lambda *_: CreateCopyRatioPlaneUI())
    cmds.setParent('..')
    row = cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, parent=column)
    cmds.button(label='Radial Smooth', height=33, parent=row,
                command=lambda *_: CreateRadialSmoothUI())
    cmds.button(label='Distance Smooth', height=33, parent=row,
                command=lambda *_: CreateDistanceSmoothUI())
    cmds.setParent('..')
    row = cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, parent=column)
    cmds.button(label='Skin Parent', height=33, parent=row,
                command=lambda *_: CreateSkinParentUI())
    cmds.button(label='Skin Children', height=33, parent=row,
                command=lambda *_: CreateSkinChildrenUI())
    cmds.setParent('..')
    _UI['status'] = cmds.text(
        label='Smooth: select vertices (origin first), unlock 2 joints, click Smooth; Graph stays live.',
        align='left', height=40, parent=column)
    cmds.showWindow(window)
    return _UI


def GraphSkinningUI(*args):
    """Backward-compatible alias."""
    return CreateUI()
