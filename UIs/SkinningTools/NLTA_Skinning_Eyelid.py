"""Eyelid Surface Skin Solver (Maya 2024+, Python 3 / Maya API 2.0).

Standalone eyelid weight utility with an optional UI entry point. It does not create proxies,
meshes, joints, or modify the scene during capture()/solve().

Scope v0.4:
    * One upper-lid influence adjusted against one base/head influence.
    * Optional topology-ring smoothing into neighboring upper-lid vertices;
      target loop is unchanged by smoothing and lower-lid reference faces
      are excluded completely.
    * Reports why selected influences cannot reach the target surface gap.
    * Existing weights on all other influences remain unchanged.
    * Classical linear skinning only (skinCluster.skinningMethod == 0).
    * One skinCluster affecting one polygon mesh, no unsupported downstream
      deformer, relative-space skinning, component influence or DQ blending.
    * Reference faces must not contain any upper-lid vertex being solved.
    * Pose MUST be the intended CLOSED pose before capture/solve/apply.

The result is a proposal dict that can be inspected before calling apply().

Basic usage (in Maya Script Editor Python tab):
    import eyelid_surface_skin as lid
    upper = lid.selected_vertices()     # select upper eyelid vertex loop first
    faces = lid.selected_faces()        # select lower-lid reference faces next
    ctx = lid.capture(
        mesh='Head', upper_vertices=upper, reference_faces=faces,
        upper_joint='UpperLid_Jnt', base_joint='Head_Jnt',
        reference_vertex=upper[len(upper)//2],
    )
    plan = lid.solve(ctx)
    print(lid.report(plan))
    lid.apply(plan)  # writes skin weights; one Maya undo chunk

Notes:
    Distance is SIGNED against the closest reference triangle normal. Equal
    signed gap alone does not guarantee attractive curvature at eye corners;
    inspect preview/report and test intermediate blink poses.
    Geometry accuracy is self-checked against Maya's *actual* deformed mesh
    before any weight proposal is trusted. If unsupported deformation is
    detected, capture raises, without modifying the scene.
"""

from __future__ import absolute_import

import math
import re

_VERSION = '0.4.0'
_COMPONENT_RE = re.compile(r'\.vtx\[(\d+)\]$')
_FACE_RE = re.compile(r'\.f\[(\d+)\]$')
_EPS = 1e-12


def _vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vmul(a, t):
    return (a[0] * t, a[1] * t, a[2] * t)


def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1],
            a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def _as_xyz(p):
    return (float(p.x), float(p.y), float(p.z))


def _closest_on_triangle(p, a, b, c):
    """Closest point on a non-degenerate triangle (Ericson region tests)."""
    ab, ac, ap = _vsub(b, a), _vsub(c, a), _vsub(p, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a
    bp = _vsub(p, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        return _vadd(a, _vmul(ab, d1 / (d1 - d3)))
    cp = _vsub(p, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        return _vadd(a, _vmul(ac, d2 / (d2 - d6)))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        bc = _vsub(c, b)
        return _vadd(b, _vmul(bc, (d4 - d3) / ((d4 - d3) + (d5 - d6))))
    denom = va + vb + vc
    if abs(denom) < _EPS:
        raise ValueError('Degenerate reference triangle')
    v = vb / denom
    w = vc / denom
    return _vadd(a, _vadd(_vmul(ab, v), _vmul(ac, w)))


def _build_reference_triangles(all_points, face_triangles):
    """From vertex-id triangles, make immutable position/normal triples."""
    result = []
    for ids in face_triangles:
        a, b, c = (all_points[ids[0]], all_points[ids[1]], all_points[ids[2]])
        normal = _cross(_vsub(b, a), _vsub(c, a))
        length = _norm(normal)
        if length < _EPS:
            continue
        result.append((a, b, c, _vmul(normal, 1.0 / length)))
    if not result:
        raise ValueError('Reference faces contain no valid triangles')
    return result


def _signed_distance(p, triangles):
    """Signed distance to closest reference triangle, sign from its normal.

    For curved open patches this is LOCAL signed distance, not a global SDF.
    Face orientation must be consistent, and user chooses the intended patch.
    """
    best_d2, best_sign = float('inf'), 1.0
    for a, b, c, n in triangles:
        q = _closest_on_triangle(p, a, b, c)
        delta = _vsub(p, q)
        d2 = _dot(delta, delta)
        if d2 < best_d2:
            best_d2 = d2
            best_sign = -1.0 if _dot(delta, n) < 0.0 else 1.0
    return best_sign * math.sqrt(best_d2)


def _best_scalar(point0, direction, limit, triangles, target, prior,
                 regularization=0.0, samples=33, iterations=36):
    """Bounded 1-D fit with coarse scan plus golden-section refinement."""
    if limit <= _EPS or _dot(direction, direction) <= _EPS:
        return max(0.0, min(limit, prior))

    def objective(w):
        gap = _signed_distance(_vadd(point0, _vmul(direction, w)), triangles)
        # regularization has units [world distance^2 / weight^2]
        return (gap - target)**2 + regularization * (w - prior)**2

    step = limit / float(samples - 1)
    vals = [(objective(k * step), k * step) for k in range(samples)]
    idx = min(range(samples), key=lambda i: vals[i][0])
    best_w = vals[idx][1]
    lo, hi = max(0.0, best_w - step), min(limit, best_w + step)
    phi = (math.sqrt(5.0) - 1.0) * 0.5
    x1, x2 = hi - phi * (hi - lo), lo + phi * (hi - lo)
    f1, f2 = objective(x1), objective(x2)
    for _ in range(iterations):
        if f1 <= f2:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - phi * (hi - lo)
            f1 = objective(x1)
        else:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + phi * (hi - lo)
            f2 = objective(x2)
    candidates = [(objective(w), w) for w in (0.0, limit, prior, best_w, (lo+hi)*0.5)]
    return min(candidates)[1]


def _maya():
    try:
        import maya.cmds as cmds
        import maya.api.OpenMaya as om
        import maya.api.OpenMayaAnim as oma
    except ImportError as exc:
        raise RuntimeError('This operation must run inside Autodesk Maya: %s' % exc)
    return cmds, om, oma


def _dag_path(name, om):
    selection = om.MSelectionList()
    selection.add(name)
    return selection.getDagPath(0)


def _skin_fn(skin, om, oma):
    selection = om.MSelectionList()
    selection.add(skin)
    return oma.MFnSkinCluster(selection.getDependNode(0))


def _component(ids, om):
    fn = om.MFnSingleIndexedComponent()
    result = fn.create(om.MFn.kMeshVertComponent)
    fn.addElements(list(ids))
    return result


def _flat_matrix(val, om):
    """Convert Maya cmds.getAttr matrix result into MMatrix."""
    if isinstance(val, (list, tuple)) and len(val) == 1 and isinstance(val[0], (list, tuple)):
        val = val[0]
    if len(val) != 16:
        raise RuntimeError('Unexpected matrix result: %r' % (val,))
    return om.MMatrix([float(x) for x in val])


def _skin_and_mesh(mesh):
    cmds, om, oma = _maya()
    if not cmds.objExists(mesh):
        raise ValueError('Mesh not found: %s' % mesh)
    node = mesh.split('.', 1)[0]
    if cmds.nodeType(node) == 'mesh':
        parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        if not parent:
            raise ValueError('Mesh shape has no transform')
        node = parent[0]
    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                fullPath=True, type='mesh') or []
    if len(shapes) != 1:
        raise ValueError('Expected exactly one visible polygon mesh shape on %s' % node)
    skins = cmds.ls(cmds.listHistory(shapes[0], pruneDagObjects=True) or [],
                   type='skinCluster') or []
    if len(skins) != 1:
        raise ValueError('Expected exactly one skinCluster on %s' % node)
    return (cmds.ls(node, long=True)[0], shapes[0], skins[0])


def _ids_from_components(parts, suffix, mesh=None):
    cmds, _, _ = _maya()
    if not parts:
        raise ValueError('Component list must not be empty')
    flattened = cmds.ls(parts, flatten=True, long=True) or []
    pattern = _COMPONENT_RE if suffix == 'vtx' else _FACE_RE
    ids, seen_mesh = [], set()
    for part in flattened:
        m = pattern.search(part)
        if not m:
            raise ValueError('Expected %s component, got %s' % (suffix, part))
        seen_mesh.add(part.split('.', 1)[0])
        ids.append(int(m.group(1)))
    if len(seen_mesh) != 1:
        raise ValueError('Components must belong to one mesh')
    if mesh is not None and next(iter(seen_mesh)) not in {mesh, (cmds.ls(mesh, long=True) or [''])[0]}:
        raise ValueError('Component mesh differs from provided mesh')
    return sorted(set(ids)), next(iter(seen_mesh))


def selected_vertices():
    """Read vertex selection (also converts selected edges) without changing it."""
    cmds, _, _ = _maya()
    selection = cmds.ls(selection=True, flatten=True, long=True) or []
    if not selection:
        raise ValueError('Select upper lid vertices or edges first')
    vertices = cmds.polyListComponentConversion(selection, toVertex=True) or []
    ids, mesh = _ids_from_components(vertices, 'vtx')
    return ['%s.vtx[%d]' % (mesh, i) for i in ids]


def selected_faces():
    """Read face selection without changing it."""
    cmds, _, _ = _maya()
    selection = cmds.ls(selection=True, flatten=True, long=True) or []
    ids, mesh = _ids_from_components(selection, 'f')
    return ['%s.f[%d]' % (mesh, i) for i in ids]


def _reference_triangle_ids(mesh_fn, faces):
    tri_counts, tri_vertices = mesh_fn.getTriangles()
    found, cursor, faces = [], 0, set(faces)
    for face_id, n in enumerate(tri_counts):
        for _ in range(n):
            if face_id in faces:
                found.append(tuple(int(tri_vertices[cursor+k]) for k in range(3)))
            cursor += 3
    return found


def _mesh_topology_neighbors(mesh_fn):
    """Read immutable polygon topology once, not via slow per-vertex cmds."""
    counts, flat = mesh_fn.getVertices()
    neighbors = [set() for _ in range(mesh_fn.numVertices)]
    cursor = 0
    for count in counts:
        face = [int(flat[cursor+i]) for i in range(count)]
        cursor += count
        for a, b in zip(face, face[1:]+face[:1]):
            if a != b:
                neighbors[a].add(b)
                neighbors[b].add(a)
    return neighbors


def _topology_rings(neighbors, seeds, blocked, rings):
    """Multi-source BFS; never enters the reference surface nor crosses it."""
    if not isinstance(rings, int) or not 0 <= rings <= 8:
        raise ValueError('smooth_rings must be an integer between 0 and 8')
    seeds, blocked = set(seeds), set(blocked)
    if seeds & blocked:
        raise ValueError('Upper vertices overlap blocked reference-surface vertices')
    distances = {vid: 0 for vid in seeds}
    front = set(seeds)
    for depth in range(1, rings + 1):
        next_front = set()
        for vid in front:
            for other in neighbors[vid]:
                if other not in distances and other not in blocked:
                    distances[other] = depth
                    next_front.add(other)
        front = next_front
        if not front:
            break
    return distances


def _smooth_neighbor_weights(context, proposed, strength=0.65):
    """Spread the solved eyelid pair *share* outward with topology falloff.

    Smoothing is based on the current/solved edge weights, NOT the delta from
    the previous solve. Thus rerunning after v0.3 has already solved the edge
    still smooths nearby vertices. The selected edge itself stays unchanged.
    Reference faces are excluded at BFS capture time. Non-pair influences are
    kept unchanged, as is the total upper+base weight at each vertex.
    """
    if not math.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError('smooth_strength must be a finite number in [0,1]')
    distances = context.get('ring_distances', {})
    adjacency = context.get('ring_neighbors', {})
    base, upper = context['base_index'], context['upper_index']
    old_weights = context['weights']
    seed_ids = set(context['vertices'])
    allowed_rings = int(context.get('smooth_rings', max(distances.values(), default=0)))
    if strength == 0 or not distances or allowed_rings == 0:
        return proposed, {'nearby_count': 0, 'smoothed_count': 0, 'rings': allowed_rings}
    # A seed with no pair capacity is not a useful guide for neighboring skin.
    upper_share = {}
    for vid in seed_ids:
        row = proposed[vid]
        capacity = row[base] + row[upper]
        if capacity > _EPS:
            upper_share[vid] = row[upper] / capacity
    smoothing_candidates = sorted((vid for vid, depth in distances.items() if depth > 0),
                                  key=lambda vid: (distances[vid], vid))
    result = dict(proposed)
    smoothed = 0
    for vid in smoothing_candidates:
        depth = distances[vid]
        parents = [n for n in adjacency.get(vid, ())
                   if distances.get(n) == depth - 1 and n in upper_share]
        if not parents:
            # No influence path from a valid seed: leave this vertex intact.
            continue
        guide_share = sum(upper_share[n] for n in parents) / float(len(parents))
        old = old_weights[vid]
        capacity = old[base] + old[upper]
        if capacity <= _EPS:
            # Do not spread values past vertices owned 100% by other joints.
            continue
        upper_share[vid] = guide_share  # undamped target share for the next ring
        t = depth / float(allowed_rings + 1)
        falloff = strength * (1.0 - (3.0*t*t - 2.0*t*t*t))
        new_upper = max(0.0, min(capacity,
                        (1.0 - falloff) * old[upper] + falloff * capacity * guide_share))
        if abs(new_upper - old[upper]) <= 1e-7:
            continue
        row = list(old)
        row[upper], row[base] = new_upper, capacity - new_upper
        result[vid] = tuple(row)
        smoothed += 1
    return result, {'nearby_count': len(smoothing_candidates),
                    'smoothed_count': smoothed, 'rings': allowed_rings}


def _get_weights(fn, dag, vertices, om):
    arr, count = fn.getWeights(dag, _component(vertices, om))
    return [tuple(float(arr[k*count + i]) for i in range(count))
            for k in range(len(vertices))]


def capture(mesh, upper_vertices, reference_faces, upper_joint, base_joint,
            reference_vertex=None, validation_tolerance=None, smooth_rings=2):
    """Read closed-pose state; NO scene changes. Return immutable-ish context.

    reference_vertex defaults to middle numeric vertex ID (NOT curve center).
    Pass it explicitly for artistic accuracy. All components must be on mesh.
    smooth_rings=0 recovers v0.3 behavior (no neighboring vertices changed).
    """
    if isinstance(smooth_rings, bool) or not isinstance(smooth_rings, int) or not 0 <= smooth_rings <= 8:
        raise ValueError('smooth_rings must be an integer from 0 to 8')
    cmds, om, oma = _maya()
    mesh, shape, skin = _skin_and_mesh(mesh)
    vtx, vmesh = _ids_from_components(upper_vertices, 'vtx', mesh)
    faceids, fmesh = _ids_from_components(reference_faces, 'f', mesh)
    # Resolve components to the same canonical transform even if input used a shape.
    if (cmds.ls(vmesh, long=True) or [None])[0] != mesh:
        raise ValueError('Upper vertex components must use the Head mesh transform')
    if (cmds.ls(fmesh, long=True) or [None])[0] != mesh:
        raise ValueError('Reference faces must use the same Head mesh transform')
    if not cmds.objExists(upper_joint) or not cmds.objExists(base_joint):
        raise ValueError('Both upper_joint and base_joint must exist')
    if upper_joint == base_joint:
        raise ValueError('Upper and base influences must be different')
    if cmds.getAttr(skin + '.skinningMethod') != 0:
        raise RuntimeError('Only classical linear skinning is supported')
    if cmds.attributeQuery('relativeSpaceMode', node=skin, exists=True) and cmds.getAttr(skin+'.relativeSpaceMode') != 0:
        raise RuntimeError('Non-default relative-space skinning is unsupported')
    if cmds.getAttr(skin + '.useComponents'):
        raise RuntimeError('Component influence skinning is unsupported')
    if len(cmds.deformer(skin, query=True, geometry=True) or []) != 1:
        raise RuntimeError('Multi-geometry skinCluster is unsupported')

    if reference_vertex is None:
        reference_vertex = vtx[len(vtx) // 2]
    elif isinstance(reference_vertex, str):
        ids, _ = _ids_from_components([reference_vertex], 'vtx', mesh)
        reference_vertex = ids[0]
    else:
        reference_vertex = int(reference_vertex)
    if reference_vertex not in vtx:
        raise ValueError('reference_vertex must belong to upper_vertices')

    mesh_dag = _dag_path(shape, om)
    fn_mesh = om.MFnMesh(mesh_dag)
    n_points, n_faces = fn_mesh.numVertices, fn_mesh.numPolygons
    if max(vtx) >= n_points or max(faceids) >= n_faces:
        raise ValueError('Vertex or face id is out of bounds')
    tri_ids = _reference_triangle_ids(fn_mesh, faceids)
    if any(set(tri).intersection(vtx) for tri in tri_ids):
        raise ValueError('Reference faces share a vertex with the upper eyelid selection. '
                         'Choose a separate lower-lid surface patch to prevent self-distance=0.')
    evaluated = [_as_xyz(p) for p in fn_mesh.getPoints(om.MSpace.kWorld)]
    ref_tris = _build_reference_triangles(evaluated, tri_ids)
    # Reference polygon vertices are barriers. They must NEVER be modified
    # by smoothing (including their neighboring vertices on that patch).
    reference_vertex_ids = set(k for tri in tri_ids for k in tri)
    if smooth_rings:
        mesh_neighbors = _mesh_topology_neighbors(fn_mesh)
        ring_distances = _topology_rings(mesh_neighbors, vtx, reference_vertex_ids,
                                         smooth_rings)
        ring_neighbors = {i: tuple(sorted(n for n in mesh_neighbors[i]
                                           if n in ring_distances))
                          for i in ring_distances}
    else:
        ring_distances = {i: 0 for i in vtx}
        ring_neighbors = {}

    fn_skin = _skin_fn(skin, om, oma)
    paths = fn_skin.influenceObjects()
    influence_names = [p.fullPathName() for p in paths]
    def lookup(name):
        full = (cmds.ls(name, long=True) or [name])[0]
        if full not in influence_names:
            raise ValueError('%s is not bound to %s' % (name, skin))
        return influence_names.index(full)
    upper_index, base_index = lookup(upper_joint), lookup(base_joint)
    idx = sorted(set(ring_distances) | {reference_vertex})
    weight_rows = _get_weights(fn_skin, mesh_dag, idx, om)
    existing = dict(zip(idx, weight_rows))
    if any(abs(sum(w)-1.0) > 1e-4 for w in weight_rows):
        raise RuntimeError('Vertex weights must be normalized to 1 before solving')

    # Read exact evaluated *input* geometry into memory (upstream of skinCluster).
    plug_sel = om.MSelectionList()
    plug_sel.add(skin + '.input[0].inputGeometry')
    geo_plug = plug_sel.getPlug(0)
    try:
        input_mesh_fn = om.MFnMesh(geo_plug.asMObject())
        original = input_mesh_fn.getPoints(om.MSpace.kObject)
    except Exception as exc:
        raise RuntimeError('Cannot read skinCluster inputGeometry: %s' % exc)
    if len(original) != n_points:
        raise RuntimeError('Skin input/output topology differs')
    original_xyz = [_as_xyz(p) for p in original]

    geom_matrix = _flat_matrix(cmds.getAttr(skin + '.geomMatrix'), om)
    transforms = []
    pose_stamp = []
    for path in paths:
        logical_index = fn_skin.indexForInfluenceObject(path)
        pre = _flat_matrix(cmds.getAttr('%s.bindPreMatrix[%d]' % (skin, logical_index)), om)
        mat = _flat_matrix(cmds.getAttr('%s.matrix[%d]' % (skin, logical_index)), om)
        transforms.append(pre * mat)
        pose_stamp.append(tuple(float(x) for x in mat))
    pose_stamp = tuple(pose_stamp)

    # Maya's SDK documents world bindpoint = geomMatrix * local input point,
    # then weighted per-influence transformation bindPreMatrix * matrix.
    basis = {}
    max_err = 0.0
    for i in vtx:
        bind_world = om.MPoint(*original_xyz[i]) * geom_matrix
        basis_i = [_as_xyz(bind_world * matrix) for matrix in transforms]
        estimated = (0.0, 0.0, 0.0)
        for j, w in enumerate(existing[i]):
            estimated = _vadd(estimated, _vmul(basis_i[j], w))
        err = _norm(_vsub(estimated, evaluated[i]))
        max_err = max(max_err, err)
        basis[i] = basis_i
    xs = [p[0] for p in evaluated]
    ys = [p[1] for p in evaluated]
    zs = [p[2] for p in evaluated]
    diag = _norm((max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)))
    tolerance = float(validation_tolerance) if validation_tolerance is not None else max(1e-4, diag * 1e-4)
    if max_err > tolerance:
        raise RuntimeError('Cannot reproduce Maya closed-pose deformation from linear-skin matrices '
                           '(max error %.6g > tolerance %.6g). Check deformers after skin, '
                           'relative transforms and skin method; no weights changed.' % (max_err, tolerance))

    return {
        'version': _VERSION, 'mesh': mesh, 'shape': shape, 'skin': skin,
        'vertices': tuple(vtx), 'reference_faces': tuple(faceids),
        'reference_vertex': reference_vertex,
        'triangles': tuple(ref_tris), 'basis': basis,
        'smooth_rings': smooth_rings, 'ring_distances': ring_distances,
        'ring_neighbors': ring_neighbors,
        'reference_vertex_ids': frozenset(reference_vertex_ids),
        'weights': existing, 'influences': tuple(influence_names),
        'upper_index': upper_index, 'base_index': base_index,
        'pose_stamp': pose_stamp, 'reference_snapshot': tuple(
            (i, evaluated[i]) for i in sorted(set(k for tri in tri_ids for k in tri))),
        'max_capture_error': max_err,
    }


def _reachable_gap_range(p0, direction, capacity, triangles, samples=65):
    """Sample attainable signed distances. This is a diagnostic, not a proof.

    A trajectory can have local extrema between samples; never use this
    sampled range as a geometric or numerical guarantee.
    """
    if capacity <= _EPS:
        gap = _signed_distance(p0, triangles)
        return (gap, gap)
    gaps = [_signed_distance(_vadd(p0, _vmul(direction, capacity*k/float(samples-1))), triangles)
            for k in range(samples)]
    return min(gaps), max(gaps)


def solve(context, target_distance=None, regularization=0.0, preserve_reference=True,
          target_tolerance=1e-3, smooth_strength=0.65):
    """Non-destructive bounded upper/head pair solve with per-vertex diagnosis.

    The other influences keep their current weights; pair capacity therefore
    may be zero. target_tolerance is in the mesh world-space units. The
    reference vertex is held constant unless preserve_reference=False.
    """
    triangles = context['triangles']
    base, upper = context['base_index'], context['upper_index']
    center = context['reference_vertex']

    def point_of(vid, weights):
        pt = (0., 0., 0.)
        for w, basis in zip(weights, context['basis'][vid]):
            if w:
                pt = _vadd(pt, _vmul(basis, w))
        return pt

    center_gap = _signed_distance(point_of(center, context['weights'][center]), triangles)
    target = center_gap if target_distance is None else float(target_distance)
    if not math.isfinite(target):
        raise ValueError('target_distance must be finite')
    if not math.isfinite(regularization) or regularization < 0:
        raise ValueError('regularization must be non-negative and finite')
    if not math.isfinite(target_tolerance) or target_tolerance <= 0:
        raise ValueError('target_tolerance must be positive and finite')
    if not math.isfinite(smooth_strength) or not 0 <= smooth_strength <= 1:
        raise ValueError('smooth_strength must be in [0, 1]')

    proposed = {}
    reports = []
    for vid in context['vertices']:
        old = context['weights'][vid]
        capacity = max(0.0, old[upper] + old[base])
        orig_pt = point_of(vid, old)
        before_gap = _signed_distance(orig_pt, triangles)
        basis = context['basis'][vid]
        direction = _vsub(basis[upper], basis[base])
        potential_motion = _norm(direction) * capacity
        p0 = _vsub(orig_pt, _vmul(direction, old[upper]))
        min_gap, max_gap = _reachable_gap_range(p0, direction, capacity, triangles)
        is_reference = preserve_reference and vid == center
        proposed_w = old[upper]
        if not is_reference and capacity > _EPS and potential_motion > 1e-9:
            proposed_w = _best_scalar(p0, direction, capacity, triangles, target,
                                      old[upper], regularization=regularization)
        proposed_w = max(0.0, min(capacity, proposed_w))
        new_w = list(old)
        new_w[upper], new_w[base] = proposed_w, capacity - proposed_w
        new_w = tuple(new_w)
        after_gap = _signed_distance(point_of(vid, new_w), triangles)
        before_residual = abs(before_gap - target)
        residual = abs(after_gap - target)
        changed = abs(proposed_w - old[upper]) > 1e-7

        if is_reference:
            reason = 'reference_fixed'
        elif capacity <= _EPS:
            reason = 'no_pair_weight'  # all weight belongs to other joints
        elif potential_motion <= 1e-9:
            reason = 'no_relative_joint_motion'
        elif residual <= target_tolerance:
            reason = 'target_met'
        elif changed and residual < before_residual - 1e-7:
            reason = 'improved_but_unmatched'
        elif changed:
            reason = 'changed_low_gain'
        elif target < min_gap-target_tolerance or target > max_gap+target_tolerance:
            reason = 'gap_outside_sampled_range'
        elif proposed_w <= 1e-7 or proposed_w >= capacity-1e-7:
            reason = 'weight_at_limit'
        else:
            reason = 'no_better_pair_weight'

        proposed[vid] = new_w
        reports.append({
            'vertex': vid, 'before': before_gap, 'after': after_gap,
            'before_residual': before_residual, 'residual': residual,
            'old_upper': old[upper], 'new_upper': proposed_w,
            'old_base': old[base], 'pair_capacity': capacity,
            'other_weight': max(0., 1.0-capacity),
            'potential_motion': potential_motion,
            'reachable_min': min_gap, 'reachable_max': max_gap,
            'changed': changed, 'reason': reason,
        })

    proposed, smoothing = _smooth_neighbor_weights(context, proposed,
                                                   strength=smooth_strength)
    seed_changed_count = sum(int(r['changed']) for r in reports)
    changed_count = sum(1 for vid, weights in proposed.items()
                        if not _matching_close(weights, context['weights'][vid], 1e-7))
    reasons = {}
    for row in reports:
        reasons[row['reason']] = reasons.get(row['reason'], 0)+1
    return {
        'context': context, 'proposed': proposed,
        'target_distance': target, 'target_tolerance': target_tolerance,
        'diagnostics': reports,
        'before_mean_residual': sum(r['before_residual'] for r in reports)/len(reports),
        'mean_residual': sum(r['residual'] for r in reports)/len(reports),
        'max_residual': max(r['residual'] for r in reports),
        'changed_count': changed_count, 'seed_changed_count': seed_changed_count,
        'smoothing': smoothing, 'smooth_strength': smooth_strength,
        'reasons': reasons,
        'status': ('CHANGES_PROPOSED' if changed_count else
                   'ALREADY_MATCHED' if max(r['residual'] for r in reports) <= target_tolerance
                   else 'UNRESOLVED_NO_CHANGES'),
    }


def report(plan):
    """Detailed report, including why the optimizer made zero changes."""
    ctx = plan['context']
    bad = sorted(plan['diagnostics'], key=lambda d: d['residual'], reverse=True)
    reasons = plan.get('reasons', {})
    lines = [
        'Eyelid Surface Skin Solver v%s (PREVIEW)' % _VERSION,
        'Status: %s' % plan.get('status', 'UNKNOWN'),
        'Mesh: %s | Skin: %s' % (ctx['mesh'], ctx['skin']),
        'Lid edge: %d | Total weight changes: %d | Reference vertex: %d' % (
            len(ctx['vertices']), plan['changed_count'], ctx['reference_vertex']),
        'Neighbor smooth: rings=%d | strength=%.2f | candidates=%d | changed=%d' % (
            plan.get('smoothing', {}).get('rings', 0), plan.get('smooth_strength', 0),
            plan.get('smoothing', {}).get('nearby_count', 0),
            plan.get('smoothing', {}).get('smoothed_count', 0)),
        'Target signed gap: %.6f (mesh world units)' % plan['target_distance'],
        'Mean residual BEFORE: %.6f | AFTER: %.6f | Max AFTER: %.6f' % (
            plan['before_mean_residual'], plan['mean_residual'], plan['max_residual']),
        'Linear skin model capture error: %.6g' % ctx['max_capture_error'],
        'Reasons: ' + ', '.join('%s=%d' % (k, v) for k, v in sorted(reasons.items())),
        'Worst 5 vertices (gap, target error, pair capacity, possible displacement):',
    ]
    for x in bad[:5]:
        lines.append('  vtx[%d]: gap %.5f -> %.5f, error %.5f, upper %.3f -> %.3f, '
                     'pair %.3f, moveMax %.5f, sampledGap [%.5f, %.5f], %s' % (
                         x['vertex'], x['before'], x['after'], x['residual'],
                         x['old_upper'], x['new_upper'], x['pair_capacity'],
                         x['potential_motion'], x['reachable_min'], x['reachable_max'],
                         x['reason']))
    if plan['changed_count'] == 0:
        if plan['status'] == 'ALREADY_MATCHED':
            lines.append('NO CHANGES NEEDED: all vertices already match the target.')
        else:
            lines.append('NOT APPLIED: no vertex can improve using the selected pair '
                         'in this pose and with other influence weights preserved.')
        if reasons.get('no_pair_weight'):
            lines.append('  Fix: Upper/Head have zero combined weight at some vertices. '
                         'Inspect the other influences; this mode does NOT steal their weights.')
        if reasons.get('no_relative_joint_motion'):
            lines.append('  Fix: Joint positions are identical on those vertices. '
                         'Check CLOSED POSE and joint selection.')
        if reasons.get('gap_outside_sampled_range') or reasons.get('weight_at_limit'):
            lines.append('  Fix: Target gap is not attainable within 0..pair-capacity. '
                         'Check closed-pose angle, reference faces and reference vertex.')
    else:
        lines.append('No changes made. Call apply(plan) to write weights. (PREVIEW ONLY)')
    return '\n'.join(lines)


def _matching_close(a, b, tol=1e-6):
    return len(a) == len(b) and all(abs(x-y) <= tol for x, y in zip(a, b))


def apply(plan, verify_pose=True):
    """Write only previewed vertex weights; Maya undo chunk + rollback on error.

    Does NOT create or edit other meshes. Rejects stale weights/pose.
    """
    ctx = plan['context']
    if plan.get('changed_count', 0) == 0:
        return {'status': plan.get('status', 'UNRESOLVED_NO_CHANGES'), 'updated_vertices': 0,
                'mesh': ctx['mesh'], 'skin': ctx['skin'],
                'mean_residual': plan['mean_residual'],
                'max_residual': plan['max_residual']}
    cmds, om, oma = _maya()
    mesh, shape, skin = _skin_and_mesh(ctx['mesh'])
    if (mesh, shape, skin) != (ctx['mesh'], ctx['shape'], ctx['skin']):
        raise RuntimeError('Mesh/skin no longer match preview')
    fn = _skin_fn(skin, om, oma)
    mesh_dag = _dag_path(shape, om)
    names = tuple(p.fullPathName() for p in fn.influenceObjects())
    if names != ctx['influences']:
        raise RuntimeError('Skin influences changed after capture; solve again')
    ids = sorted(plan['proposed'])
    actual_rows = _get_weights(fn, mesh_dag, ids, om)
    for vid, row in zip(ids, actual_rows):
        if not _matching_close(row, ctx['weights'][vid]):
            raise RuntimeError('Weight changed after capture at vertex %d; solve again' % vid)
    if verify_pose:
        for j, dag in enumerate(fn.influenceObjects()):
            logical = fn.indexForInfluenceObject(dag)
            mat = _flat_matrix(cmds.getAttr('%s.matrix[%d]' % (skin, logical)), om)
            if not _matching_close(tuple(float(x) for x in mat), ctx['pose_stamp'][j]):
                raise RuntimeError('Joint pose changed after capture; solve again')
        fn_mesh = om.MFnMesh(mesh_dag)
        pts = fn_mesh.getPoints(om.MSpace.kWorld)
        for vid, xyz in ctx['reference_snapshot']:
            if _norm(_vsub(_as_xyz(pts[vid]), xyz)) > 1e-5:
                raise RuntimeError('Reference surface moved after capture; solve again')
    for j in (ctx['base_index'], ctx['upper_index']):
        name = names[j]
        if cmds.attributeQuery('liw', node=name, exists=True) and cmds.getAttr(name+'.liw'):
            raise RuntimeError('Influence locked: %s' % name)
    if cmds.getAttr(skin + '.maintainMaxInfluences'):
        for w in plan['proposed'].values():
            if sum(x > 1e-8 for x in w) > cmds.getAttr(skin + '.maxInfluences'):
                raise RuntimeError('Proposed weights exceed maintainMaxInfluences; aborting')
    before = {i: tuple(w) for i, w in zip(ids, actual_rows)}
    touched = []
    cmds.undoInfo(openChunk=True, chunkName='Eyelid Surface Skin Solve')
    try:
        for vid in ids:
            after = plan['proposed'][vid]
            if _matching_close(after, before[vid], tol=1e-9):
                continue
            component = '%s.vtx[%d]' % (mesh, vid)
            touched.append(vid)  # ensure rollback even if the command partially mutates
            cmds.skinPercent(skin, component,
                             transformValue=list(zip(names, after)),
                             normalize=False)
        # Normalization and max-influence settings can cause unexpected changes.
        new_rows = _get_weights(fn, mesh_dag, ids, om)
        if any(not _matching_close(row, plan['proposed'][vid], 1e-5)
               for vid, row in zip(ids, new_rows)):
            raise RuntimeError('Maya altered the proposed weights; rolling back')
    except Exception:
        failures = []
        for vid in reversed(touched):
            try:
                cmds.skinPercent(skin, '%s.vtx[%d]' % (mesh, vid),
                                 transformValue=list(zip(names, before[vid])),
                                 normalize=False)
            except Exception as exc:
                failures.append((vid, str(exc)))
        if failures:
            raise RuntimeError('Apply failed AND rollback was incomplete at %s. '
                               'Use scene backup before continuing.' % failures)
        raise
    finally:
        cmds.undoInfo(closeChunk=True)
    return {'status': 'APPLIED', 'mesh': mesh, 'skin': skin, 'updated_vertices': len(touched),
            'mean_residual': plan['mean_residual'], 'max_residual': plan['max_residual']}


def run(mesh, upper_vertices, reference_faces, upper_joint, base_joint,
        reference_vertex=None, target_distance=None, regularization=0.0,
        apply_result=False, smooth_rings=2, smooth_strength=0.65):
    """Convenient single entry point for another Skinning Tool to call.

    apply_result=False (default) returns preview plan and does NOT edit skin.
    apply_result=True returns both preview and apply result. Maya must already
    be in the intended closed-eye pose before running.
    """
    context = capture(mesh=mesh, upper_vertices=upper_vertices,
                      reference_faces=reference_faces,
                      upper_joint=upper_joint, base_joint=base_joint,
                      reference_vertex=reference_vertex)
    plan = solve(context, target_distance=target_distance,
                 regularization=regularization)
    return {'plan': plan, 'report': report(plan),
            'applied': apply(plan) if apply_result else None}




def EyelidSurfaceSkinUI(*arr):
    """Open a capture-and-run Eyelid Surface Skin window inside Maya.

    This single function provides the same interaction pattern as the user's
    SkinWeightTransferUI: capture each selection, inspect the captured items,
    Preview, then Run. All geometry/weight calculations stay in capture(),
    solve() and apply() above. Importing this module never opens a UI.

    The scene must be in the CLOSED eye pose before Preview or Run.
    Select reference faces on the *lower lid*, not on the upper-lid vertices.
    """
    cmds, _, _ = _maya()

    window_name = 'NLTA_EyelidSurfaceSkinSolver'
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)

    # Same capture-group workflow as SkinWeightTransferUI; we do not
    # enable trackSelectionOrder globally because no pairing order is needed.
    groups = {
        'reference_vertex': [],
        'upper_vertices': [],
        'reference_faces': [],
        'upper_joint': [],
        'base_joint': [],
    }
    titles = [
        ('reference_vertex', '1 - REFERENCE VERTEX (MIDDLE)'),
        ('upper_vertices', '2 - UPPER EYELID VERTICES'),
        ('reference_faces', '3 - REFERENCE FACES (LOWER LID)'),
        ('upper_joint', '4 - UPPER EYELID JOINT'),
        ('base_joint', '5 - BASE / HEAD JOINT'),
    ]
    widgets = {}
    max_preview_items = 70

    def status(message):
        cmds.text(widgets['status'], edit=True, label=message)

    def refresh():
        for key in groups:
            values = groups[key]
            cmds.textScrollList(widgets[key + '_list'], edit=True, removeAll=True)
            if values:
                lines = ['{:02d}. {}'.format(i, obj.rsplit('|', 1)[-1])
                         for i, obj in enumerate(values[:max_preview_items], start=1)]
                if len(values) > max_preview_items:
                    lines.append('... and {} more'.format(len(values) - max_preview_items))
                cmds.textScrollList(widgets[key + '_list'], edit=True, append=lines)
            cmds.text(widgets[key + '_count'], edit=True,
                      label='{} selected'.format(len(values)))

    def capture_selection(key, *_):
        selection = cmds.ls(selection=True, flatten=True, long=True) or []
        if not selection:
            cmds.warning('Select the requested components or joint first.')
            return
        try:
            if key == 'reference_vertex':
                if len(selection) != 1 or not _COMPONENT_RE.search(selection[0]):
                    raise ValueError('Reference must be exactly ONE polygon vertex.')
                values = selection
            elif key == 'upper_vertices':
                # Edge selection is handy for an eyelid loop, without allowing
                # arbitrary faces/joints to be converted into vertices.
                if not all(_COMPONENT_RE.search(x) or
                           re.search(r'\.e\[\d+\]$', x) for x in selection):
                    raise ValueError('Select only upper-lid vertices or edges.')
                if any('.e[' in x for x in selection):
                    values = cmds.ls(
                        cmds.polyListComponentConversion(selection, toVertex=True) or [],
                        flatten=True, long=True) or []
                else:
                    values = selection
            elif key == 'reference_faces':
                if not all(_FACE_RE.search(x) for x in selection):
                    raise ValueError('Select polygon FACES of the lower lid only.')
                values = selection
            else:
                if len(selection) != 1 or cmds.nodeType(selection[0]) != 'joint':
                    raise ValueError('Select exactly ONE joint for this group.')
                values = selection

            if len(values) != len(set(values)):
                raise ValueError('Duplicate selection entries are not supported.')
            if key in ('reference_vertex', 'upper_vertices', 'reference_faces'):
                mesh_names = {x.split('.', 1)[0] for x in values}
                if len(mesh_names) != 1:
                    raise ValueError('All components in this group must belong to one mesh.')
            groups[key] = list(values)
            refresh()
            status('Captured {} item(s): {}'.format(len(values), key))
        except (ValueError, RuntimeError) as exc:
            status('Capture rejected: {}'.format(exc))
            cmds.warning('Eyelid Skin: {}'.format(exc))

    def clear(key, *_):
        groups[key] = []
        refresh()
        status('Cleared {}'.format(key))

    def clear_all(*_):
        for key in groups:
            groups[key] = []
        refresh()
        cmds.scrollField(widgets['report'], edit=True, text='')
        status('All captures cleared.')

    def make_payload():
        missing = [key for key, label in titles if not groups[key]]
        if missing:
            raise ValueError('Capture all five groups first; missing: {}'.format(', '.join(missing)))
        reference = groups['reference_vertex'][0]
        upper = groups['upper_vertices'][:]
        if reference not in upper:
            # No need to manually re-select the reference vertex after the loop.
            upper.append(reference)
        mesh = reference.split('.', 1)[0]
        if any(obj.split('.', 1)[0] != mesh
               for obj in upper + groups['reference_faces']):
            raise ValueError('Reference, target vertices and reference faces must belong to one Head mesh.')
        if groups['upper_joint'][0] == groups['base_joint'][0]:
            raise ValueError('Upper joint and base joint must be different.')
        return {
            'mesh': mesh,
            'upper_vertices': upper,
            'reference_faces': groups['reference_faces'][:],
            'upper_joint': groups['upper_joint'][0],
            'base_joint': groups['base_joint'][0],
            'reference_vertex': reference,
        }

    def execute(do_apply, *_):
        try:
            payload = make_payload()
            # Always capture a fresh snapshot. No stale Preview is reused when
            # weights or the joint pose have been changed in Maya.
            payload['smooth_rings'] = int(cmds.intSliderGrp(widgets['smooth_rings'],
                                                          query=True, value=True))
            payload['smooth_strength'] = float(cmds.floatSliderGrp(
                widgets['smooth_strength'], query=True, value=True))
            result = run(apply_result=bool(do_apply), **payload)
            message = result['report']
            if result['applied'] is not None:
                applied = result['applied']
                if applied['updated_vertices'] == 0:
                    status('NOT APPLIED - 0 vertices changed. Read diagnosis below.')
                    message += '\n\nRUN SKIPPED - no weight changes, no undo action.'
                else:
                    message = message.replace('(PREVIEW)', '(APPLIED)').replace(
                        'No changes made. Call apply(plan) to write weights. (PREVIEW ONLY)', '')
                    message += ('\nAPPLIED - updated {} vertices. Maya Undo is available.'
                                .format(applied['updated_vertices']))
                    status('DONE - {} vertex weight(s) updated.'.format(applied['updated_vertices']))
            else:
                status('PREVIEW - {} proposed changes. Read diagnosis below.'
                       .format(result['plan']['changed_count']))
            cmds.scrollField(widgets['report'], edit=True, text=message)
            print('\n' + message)
            return result
        except Exception as exc:
            message = 'FAILED - {}\nCheck Maya Script Editor for details.'.format(exc)
            cmds.scrollField(widgets['report'], edit=True, text=message)
            status(message)
            cmds.warning('Eyelid Skin: {}'.format(exc))
            return None

    # ----------- UI layout (same capture / clear / run idea) -----------
    window = cmds.window(window_name, title='Eyelid Surface Skin Solver',
                         sizeable=True, widthHeight=(740, 780))
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=7)
    cmds.text(label='Set the eyelid joints to the CLOSED pose before Preview / Run.',
              align='center', height=26)
    cmds.text(label='Reference Faces = a separate lower-lid patch (no shared upper vertices).',
              align='center', height=22)
    cmds.text(label='The reference vertex & solved lid edge are kept intact by neighbor smoothing.',
              align='center', height=22)

    cmds.rowColumnLayout(numberOfColumns=2,
                         columnWidth=[(1, 353), (2, 353)],
                         columnSpacing=[(1, 6), (2, 6)],
                         rowSpacing=[(1, 7), (2, 7)])

    for key, heading in titles:
        cmds.frameLayout(label=heading, collapsable=False,
                         marginWidth=6, marginHeight=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        cmds.rowLayout(numberOfColumns=3,
                       columnWidth3=(160, 52, 120))
        cmds.button(label='Capture Selection', width=155, height=27,
                    command=lambda *a, k=key: capture_selection(k))
        cmds.button(label='Clear', width=50, height=27,
                    command=lambda *a, k=key: clear(k))
        widgets[key + '_count'] = cmds.text(label='0 selected', align='left')
        cmds.setParent('..')
        widgets[key + '_list'] = cmds.textScrollList(
            allowMultiSelection=False, height=75)
        cmds.setParent('..')
        cmds.setParent('..')

    # Balance the last grid row without putting meaningful controls there.
    cmds.text(label='Tip: reference faces are excluded from neighbor smoothing.',
              align='center')
    cmds.setParent('..')  # rowColumnLayout

    cmds.separator(height=8, style='in')
    widgets['smooth_rings'] = cmds.intSliderGrp(
        label='Neighbor Smooth Rings', field=True, minValue=0, maxValue=6,
        fieldMinValue=0, fieldMaxValue=8, value=2,
        annotation='0 = original solver only. Rings spread only on connected upper-lid mesh; reference faces blocked.')
    widgets['smooth_strength'] = cmds.floatSliderGrp(
        label='Smooth Strength', field=True, minValue=0.0, maxValue=1.0,
        fieldMinValue=0.0, fieldMaxValue=1.0, precision=2, value=0.65,
        annotation='How strongly neighboring vertices blend toward solved edge weights.')
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(355, 355))
    cmds.button(label='PREVIEW - NO SKIN CHANGES', width=347, height=40,
                backgroundColor=(0.25, 0.39, 0.51),
                command=lambda *_: execute(False))
    cmds.button(label='RUN - APPLY SKIN WEIGHTS', width=347, height=40,
                backgroundColor=(0.23, 0.43, 0.33),
                command=lambda *_: execute(True))
    cmds.setParent('..')
    cmds.button(label='Clear All Captures', height=27, command=clear_all)
    widgets['status'] = cmds.text(label='Ready. Capture five groups, then Preview or Run.',
                                  align='left', height=28)
    widgets['report'] = cmds.scrollField(editable=False, wordWrap=True,
                                         text='', height=145)
    cmds.setParent('..')  # columnLayout
    cmds.setParent('..')  # scrollLayout
    cmds.showWindow(window)
    refresh()
    return window


# Short alias if the outer skinning menu wants a minimal callback.
open_ui = EyelidSurfaceSkinUI

__all__ = ['selected_vertices', 'selected_faces', 'capture', 'solve',
           'report', 'apply', 'run', 'EyelidSurfaceSkinUI', 'open_ui']
