# -*- coding: utf-8 -*-
"""Reusable normalized curve editor for Maya (PySide2/PySide6).

Function-only public API; Qt is imported lazily. No Maya dependency.
CreateGraph() creates independent graphs with selectable Bezier tangent handles.

    graph = CreateGraph(parent=parent, mode='bezier')
    layout.addWidget(graph['widget'])
    y = GetValue(.35, graph)

Click a key to display its tangent handles; drag key/handles. Right-click a
key for tangent types, Break/Link, and Delete. Graph data is JSON-serializable
via GetData()/SetData(). SkirtCurve/SkirtEndCurve/FlipX/FlipY work on any graph.
"""
from __future__ import absolute_import

import bisect
import math

_MIN_X_GAP = 0.02
_DEFAULT = {'points': [(0.0, 0.0), (1.0, 1.0)], 'mode': 'smooth'}
_DEMO = None


def _limit(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Graph values must be finite')
    return max(0.0, min(1.0, value))


def _graph(graph):
    return _DEFAULT if graph is None else graph


def _validate(points):
    pts = [(float(x), float(y)) for x, y in points]
    pts.sort(key=lambda p: p[0])
    if len(pts) < 2 or abs(pts[0][0]) > 1e-9 or abs(pts[-1][0] - 1.0) > 1e-9:
        raise ValueError('Graph needs endpoints at X=0 and X=1')
    if any(not (math.isfinite(x) and math.isfinite(y) and
                    0 <= x <= 1 and 0 <= y <= 1) for x, y in pts):
        raise ValueError('Point coordinates must be in 0..1')
    if any(b[0] - a[0] < _MIN_X_GAP - 1e-9 for a, b in zip(pts, pts[1:])):
        raise ValueError('Graph points have overlapping X coordinates')
    return pts


def _slopes(points):
    """Monotone cubic slopes for automatic tangents and legacy smooth mode."""
    if len(points) == 2:
        delta = (points[1][1] - points[0][1]) / (points[1][0] - points[0][0])
        return [delta, delta]
    h = [points[i+1][0] - points[i][0] for i in range(len(points)-1)]
    d = [(points[i+1][1] - points[i][1])/h[i] for i in range(len(h))]
    m = [0.0]*len(points)
    for i in range(1, len(points)-1):
        if d[i-1]*d[i] > 0:
            a, b = 2*h[i] + h[i-1], h[i] + 2*h[i-1]
            m[i] = (a+b)/(a/d[i-1] + b/d[i])
    for end,h0,h1,d0,d1 in ((0,h[0],h[1],d[0],d[1]),
                             (-1,h[-1],h[-2],d[-1],d[-2])):
        v = ((2*h0+h1)*d0-h0*d1)/(h0+h1)
        if v*d0 <= 0:
            v = 0.0
        elif d0*d1 < 0 and abs(v) > 3*abs(d0):
            v = 3*d0
        m[end] = v
    return m


def _fresh_tangent():
    return {'in': (0.0, 0.0), 'out': (0.0, 0.0),
            'type': 'auto', 'broken': False}


def _vector(pair):
    a, b = float(pair[0]), float(pair[1])
    if not math.isfinite(a) or not math.isfinite(b):
        raise ValueError('Tangent coordinates must be finite')
    return a, b


def _tangents(graph):
    if graph.get('_tangents_fresh'):
        return graph['tangents']
    pts = graph['points']
    if len(graph.get('tangents', [])) != len(pts):
        graph['tangents'] = [_fresh_tangent() for _ in pts]
    slopes = _slopes(pts)
    for i, tangent in enumerate(graph['tangents']):
        typ = tangent.get('type', 'auto')
        if typ not in ('auto', 'flat', 'linear', 'free'):
            raise ValueError('Unknown tangent type: %s' % typ)
        tangent['type'] = typ
        tangent['broken'] = bool(tangent.get('broken', False))
        for side in ('in', 'out'):
            neighbor = i-1 if side == 'in' else i+1
            if neighbor < 0 or neighbor >= len(pts):
                tangent[side] = (0.0, 0.0)
                continue
            gap = abs(pts[i][0] - pts[neighbor][0])
            sign = -1.0 if side == 'in' else 1.0
            if typ != 'free':
                dx = sign*gap/3.0
                if typ == 'flat':
                    slope = 0.0
                elif typ == 'linear':
                    slope = (pts[neighbor][1]-pts[i][1])/(pts[neighbor][0]-pts[i][0])
                else:
                    slope = slopes[i]
                tangent[side] = (dx, dx*slope)
            else:
                old_dx, old_dy = _vector(tangent.get(side, (sign*gap/3, 0)))
                # Both control points are kept ordered in X for unambiguous x->y.
                max_dx = gap*0.49
                dx = sign*max(gap*0.025, min(max_dx, abs(old_dx)))
                dy = old_dy*(dx/old_dx) if abs(old_dx) > 1e-12 else old_dy
                tangent[side] = (dx, dy)
    graph['_tangents_fresh'] = True
    return graph['tangents']


def GetPoints(graph=None):
    return list(_graph(graph)['points'])


def GetTangents(graph=None):
    return [{k: (tuple(v) if k in ('in', 'out') else v) for k, v in t.items()}
            for t in _tangents(_graph(graph))]


def _cubic(a, b, c, d, t):
    s = 1.0-t
    return s*s*s*a + 3*s*s*t*b + 3*s*t*t*c + t*t*t*d


def GetValue(x, graph=None):
    """Evaluate at normalized X, using true weighted Bezier when enabled."""
    g, x = _graph(graph), _limit(x)
    pts = g['points']
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    i = bisect.bisect_right([p[0] for p in pts], x)-1
    x0,y0 = pts[i]
    x3,y3 = pts[i+1]
    width = x3-x0
    t = (x-x0)/width
    mode = g.get('mode','smooth')
    if mode == 'linear':
        return _limit(y0+(y3-y0)*t)
    if mode == 'bezier':
        tangents = _tangents(g)
        out_dx,out_dy = tangents[i]['out']
        in_dx,in_dy = tangents[i+1]['in']
        x1,y1 = x0+out_dx, y0+out_dy
        x2,y2 = x3+in_dx, y3+in_dy
        # X-control ordering was constrained in _tangents; a binary search
        # finds Bezier's parameter even for weighted/nonuniform handles.
        lo,hi = 0.0,1.0
        for _ in range(32):
            t = (lo+hi)*0.5
            if _cubic(x0,x1,x2,x3,t) < x:
                lo = t
            else:
                hi = t
        return _limit(_cubic(y0,y1,y2,y3,(lo+hi)*0.5))
    slopes = g.get('_slopes')
    if slopes is None:
        slopes = _slopes(pts)
        g['_slopes'] = slopes
    a,b = slopes[i]*width, slopes[i+1]*width
    t2,t3 = t*t,t*t*t
    return _limit((2*t3-3*t2+1)*y0+(t3-2*t2+t)*a+
                  (-2*t3+3*t2)*y3+(t3-t2)*b)


def _changed(g):
    callback = g.get('on_change')
    if callback:
        callback(GetPoints(g))


def SetPoints(points, graph=None):
    g = _graph(graph)
    g['points'] = _validate(points)
    g['tangents'] = [_fresh_tangent() for _ in g['points']]
    g['_tangents_fresh'] = False
    g.pop('_slopes',None)
    g['selected'] = max(0,min(g.get('selected',0),len(g['points'])-1))
    _draw(g,rebuild=True)
    _changed(g)
    return GetPoints(g)


def SetMode(mode, graph=None):
    if mode not in ('smooth','linear','bezier'):
        raise ValueError('Mode must be smooth, linear or bezier')
    g = _graph(graph)
    g['mode'] = mode
    _draw(g)
    _changed(g)


def SetTangentMode(mode, graph=None, index=None):
    """Set one key tangent type: auto, flat, linear, free."""
    if mode not in ('auto','flat','linear','free'):
        raise ValueError('Tangent mode must be auto, flat, linear or free')
    g = _graph(graph)
    i = g.get('selected',0) if index is None else int(index)
    if not 0 <= i < len(g['points']):
        raise IndexError('Key index out of range')
    _tangents(g)[i]['type'] = mode
    g['_tangents_fresh'] = False
    _tangents(g)
    _draw(g)
    _changed(g)


def BreakTangents(index=None, broken=True, graph=None):
    """Unlink the in/out handles of a key, like Maya Break Tangents."""
    g = _graph(graph)
    i = g.get('selected',0) if index is None else int(index)
    if not 0 <= i < len(g['points']):
        raise IndexError('Key index out of range')
    tangent = _tangents(g)[i]
    tangent['broken'] = bool(broken)
    if not broken:
        left_dx,left_dy = tangent['in']
        right_dx,right_dy = tangent['out']
        if left_dx and right_dx:
            slope = right_dy/right_dx
            slope = _clamp_slope(slope,g['points'][i][1],left_dx,right_dx)
            tangent['in'] = (left_dx,slope*left_dx)
            tangent['out'] = (right_dx,slope*right_dx)
            tangent['type'] = 'free'
    _draw(g)
    _changed(g)
    return bool(broken)


def _clamp_slope(slope, y, left, right):
    """With linked handles, constrain both visible ends to [0, 1]."""
    low, high = -float('inf'),float('inf')
    for dx in (left,right):
        if abs(dx) < 1e-12:
            continue
        a,b = (0.0-y)/dx, (1.0-y)/dx
        low,high = max(low,min(a,b)),min(high,max(a,b))
    return max(low,min(high,slope))


def MoveTangent(index, side, dx, dy, graph=None):
    """Move one tangent handle in normalized point-relative XY coordinates."""
    g = _graph(graph)
    if side not in ('in','out'):
        raise ValueError("Tangent side must be 'in' or 'out'")
    pts = g['points']
    i = int(index)
    neighbor = i-1 if side == 'in' else i+1
    if not 0 <= i < len(pts) or not 0 <= neighbor < len(pts):
        return False
    dx,dy = _vector((dx,dy))
    gap = abs(pts[i][0]-pts[neighbor][0])
    sign = -1.0 if side == 'in' else 1.0
    dx = sign*max(gap*.025,min(gap*.49,abs(dx)))
    tangent = _tangents(g)[i]
    tangent['type'] = 'free'
    old = tangent[side]
    opposite = 'out' if side == 'in' else 'in'
    other_dx,other_dy = tangent[opposite]
    if not tangent['broken'] and abs(other_dx)>1e-12:
        slope = _clamp_slope(dy/dx,pts[i][1],dx,other_dx)
        dy = slope*dx
        tangent[opposite] = (other_dx,slope*other_dx)
    else:
        dy = max(-pts[i][1],min(1.0-pts[i][1],dy))
    tangent[side] = (dx,dy)
    if (abs(old[0]-dx)+abs(old[1]-dy)<1e-9 and
            (tangent['broken'] or abs(other_dy-tangent[opposite][1])<1e-9)):
        return False
    _draw(g)
    _changed(g)
    return True


def SetTangents(tangents, graph=None):
    """Restore tangent data (e.g. from JSON) without requiring Qt."""
    g = _graph(graph)
    if len(tangents) != len(g['points']):
        raise ValueError('Tangent count must match points')
    result = []
    for tangent in tangents:
        kind = tangent.get('type','free')
        if kind not in ('auto','flat','linear','free'):
            raise ValueError('Invalid tangent type: %s'%kind)
        result.append({'in':_vector(tangent.get('in',(0,0))),
                       'out':_vector(tangent.get('out',(0,0))),
                       'type':kind,'broken':bool(tangent.get('broken',False))})
    g['tangents'] = result
    g['_tangents_fresh'] = False
    _tangents(g)
    _draw(g)
    _changed(g)


def GetData(graph=None):
    g = _graph(graph)
    return {'version':1,'mode':g.get('mode','smooth'),
            'points':[list(p) for p in GetPoints(g)],
            'tangents':[{k:(list(v) if k in ('in','out') else v)
                         for k,v in t.items()} for t in GetTangents(g)]}


def SetData(data, graph=None):
    """Load JSON-style graph data atomically; keeps existing Qt widget."""
    g = _graph(graph)
    mode = data.get('mode','bezier')
    if mode not in ('smooth','linear','bezier'):
        raise ValueError('Invalid graph mode')
    pts = _validate(data['points'])
    temp = {'points':pts,'mode':mode}
    if 'tangents' in data:
        SetTangents(data['tangents'],temp)
    else:
        _tangents(temp)
    g['points'],g['mode'],g['tangents'] = pts,mode,temp['tangents']
    g['_tangents_fresh'] = False
    g.pop('_slopes',None)
    g['selected'] = max(0,min(g.get('selected',0),len(pts)-1))
    _draw(g,rebuild=True)
    _changed(g)


def AddPoint(x,y,graph=None):
    g,x,y = _graph(graph),_limit(x),_limit(y)
    pts = GetPoints(g)
    i = bisect.bisect_left([p[0] for p in pts],x)
    if i==0 or i==len(pts) or min(x-pts[i-1][0],pts[i][0]-x)<_MIN_X_GAP:
        return None
    tangents = GetTangents(g)
    pts.insert(i,(x,y))
    tangents.insert(i,_fresh_tangent())
    g['points'],g['tangents'] = pts,tangents
    g['_tangents_fresh'] = False
    g['selected'] = i
    g.pop('_slopes',None)
    _tangents(g)
    _draw(g,rebuild=True)
    _changed(g)
    return i


def RemovePoint(index,graph=None):
    g = _graph(graph)
    if not 0 < index < len(g['points'])-1:
        return False
    tangents = GetTangents(g)
    pts = GetPoints(g)
    pts.pop(index)
    tangents.pop(index)
    g['points'],g['tangents'] = pts,tangents
    g['_tangents_fresh'] = False
    g['selected'] = max(0,min(index-1,len(pts)-1))
    g.pop('_slopes',None)
    _tangents(g)
    _draw(g,rebuild=True)
    _changed(g)
    return True


def MovePoint(index,x,y,graph=None):
    g,x,y = _graph(graph),_limit(x),_limit(y)
    pts = GetPoints(g)
    if not 0 <= index < len(pts):
        return False
    if index==0:
        x = 0.0
    elif index==len(pts)-1:
        x = 1.0
    else:
        x = max(pts[index-1][0]+_MIN_X_GAP,
                min(pts[index+1][0]-_MIN_X_GAP,x))
    if abs(pts[index][0]-x)+abs(pts[index][1]-y)<1e-9:
        return False
    _tangents(g)
    pts[index] = (x,y)
    g['points'] = pts
    g['_tangents_fresh'] = False
    g.pop('_slopes',None)
    _tangents(g)
    _draw(g)
    _changed(g)
    return True



# ---------------------------------------------------------------------------
# Lightweight curve presets and mirrors. These operate on graph data, not on
# Maya animCurve nodes. Coordinates always remain in the normalized 0..1 range.
# ---------------------------------------------------------------------------

_PRESETS = (
    ('Linear', 'linear'),
    ('Skirt', 'skirt'),
    ('Skirt End', 'skirt_end'),
    ('Ease In', 'ease_in'),
    ('Ease Out', 'ease_out'),
    ('S Curve', 's_curve'),
)


def PresetNames():
    return list(_PRESETS)


def SetPreset(name, graph=None):
    """Replace keys with a reusable Bézier shape, keeping the graph widget."""
    valid = dict(_PRESETS)
    aliases = {v: v for v in valid.values()}
    aliases.update({k.lower(): v for k, v in _PRESETS})
    token = str(name).strip().lower()
    token = aliases.get(token, token)
    if token not in valid.values():
        raise ValueError('Unknown graph preset: %s' % name)

    if token == 's_curve':
        data = {
            'mode': 'bezier',
            'points': [[0.0, 0.0], [0.28, 0.08],
                       [0.72, 0.92], [1.0, 1.0]],
            'tangents': [dict(_fresh_tangent(), type='auto') for _ in range(4)],
        }
    else:
        if token == 'linear':
            tangents = ['linear', 'linear']
        elif token == 'skirt':
            tangents = ['flat', 'flat']
        elif token == 'skirt_end':
            tangents = ['linear', 'flat']
        elif token == 'ease_in':
            tangents = ['free', 'free']
        else:  # ease_out
            tangents = ['free', 'free']
        data = {
            'mode': 'bezier',
            'points': [[0.0, 0.0], [1.0, 1.0]],
            'tangents': [dict(_fresh_tangent(), type=typ) for typ in tangents],
        }
        if token == 'ease_in':
            data['tangents'][0]['out'] = (1.0/3.0, 0.0)
            data['tangents'][1]['in'] = (-1.0/3.0, -0.65)
        elif token == 'ease_out':
            data['tangents'][0]['out'] = (1.0/3.0, 0.65)
            data['tangents'][1]['in'] = (-1.0/3.0, 0.0)
    SetData(data, graph)
    return GetData(graph)


def SkirtCurve(graph=None, *args):
    """Skirt gradient: flat Out tangent at 0, flat In at 1."""
    return SetPreset('skirt', graph)


def SkirtEndCurve(graph=None, *args):
    """Skirt end: linear Out tangent at 0, flat In at 1."""
    return SetPreset('skirt_end', graph)


def _reflect(graph, axis):
    g = _graph(graph)
    pts = GetPoints(g)
    tangents = GetTangents(g)
    if axis == 'x':
        new_points = [(1.0-x, y) for x,y in reversed(pts)]
        new_tangents = []
        for t in reversed(tangents):
            new_tangents.append({
                'in': (-t['out'][0], t['out'][1]),
                'out': (-t['in'][0], t['in'][1]),
                'type': t['type'], 'broken': t['broken']})
    elif axis == 'y':
        new_points = [(x, 1.0-y) for x,y in pts]
        new_tangents = [{
            'in': (t['in'][0], -t['in'][1]),
            'out': (t['out'][0], -t['out'][1]),
            'type': t['type'], 'broken': t['broken']} for t in tangents]
    else:
        raise ValueError('Unknown reflection axis')
    SetData({'mode':g.get('mode','bezier'), 'points':new_points,
             'tangents':new_tangents}, g)
    return GetData(g)


def FlipX(graph=None, *args):
    """Mirror the whole curve horizontally: new_y(x) = old_y(1-x)."""
    return _reflect(graph, 'x')


def FlipY(graph=None, *args):
    """Reverse normalized values: new_y(x) = 1 - old_y(x)."""
    return _reflect(graph, 'y')


def Reverse(graph=None, *args):
    """Reverse horizontally (Flip X): new_y(x) = old_y(1-x).

    This reverses the key order and swaps in/out tangents. Unlike FlipY,
    it does not invert vertex weight values at the same x coordinate.
    """
    return FlipX(graph)


def _qt():
    try:
        from PySide6 import QtCore,QtGui,QtWidgets
    except ImportError:
        from PySide2 import QtCore,QtGui,QtWidgets
    return QtCore,QtGui,QtWidgets


def _dot(scene,QtGui,QtWidgets,size,color):
    item = QtWidgets.QGraphicsEllipseItem(-size/2,-size/2,size,size)
    item.setBrush(QtGui.QBrush(QtGui.QColor(color)))
    item.setPen(QtGui.QPen(QtGui.QColor('#17212d'),1.4))
    item.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable,True)
    item.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable,True)
    item.setZValue(3)
    scene.addItem(item)
    return item


def _pos(g,x,y):
    left,top,w,h = g['rect']
    return left+x*w, top+(1-y)*h


def _draw(g,rebuild=False):
    if 'scene' not in g or g.get('_drawing'):
        return
    g['_drawing'] = True
    try:
        QtCore,QtGui,QtWidgets = g['qt']
        scene = g['scene']
        pts = g['points']
        if rebuild:
            for item in g['handles']:
                scene.removeItem(item)
            g['handles'] = [_dot(scene,QtGui,QtWidgets,11,'#e2e8f0') for _ in pts]
        for i,(item,(x,y)) in enumerate(zip(g['handles'],pts)):
            item.setPos(*_pos(g,x,y))
            item.setBrush(QtGui.QBrush(QtGui.QColor('#f6cb70' if i==g.get('selected',0)
                                                   else '#e2e8f0')))
        path = QtGui.QPainterPath()
        path.moveTo(*_pos(g,*pts[0]))
        mode = g.get('mode','smooth')
        if mode=='bezier':
            tangents = _tangents(g)
            for i in range(len(pts)-1):
                x0,y0 = pts[i]
                x3,y3 = pts[i+1]
                dx1,dy1 = tangents[i]['out']
                dx2,dy2 = tangents[i+1]['in']
                path.cubicTo(*_pos(g,x0+dx1,y0+dy1),
                             *_pos(g,x3+dx2,y3+dy2),*_pos(g,x3,y3))
        elif mode=='linear':
            for p in pts[1:]:
                path.lineTo(*_pos(g,*p))
        else:
            for i in range(1,121):
                x=i/120.0
                path.lineTo(*_pos(g,x,GetValue(x,g)))
        g['path'].setPath(path)
        select = g.get('selected',0)
        for side,item in g['tangent_items'].items():
            is_valid = (mode=='bezier' and
                        (select>0 if side=='in' else select<len(pts)-1))
            item.setVisible(is_valid)
            g['tangent_lines'][side].setVisible(is_valid)
            if is_valid:
                p = pts[select]
                dx,dy = _tangents(g)[select][side]
                a,b = _pos(g,*p),_pos(g,p[0]+dx,p[1]+dy)
                item.setPos(*b)
                g['tangent_lines'][side].setLine(a[0],a[1],b[0],b[1])
    finally:
        g['_drawing'] = False


def _on_selection(g):
    if g.get('_drawing'):
        return
    for i,item in enumerate(g['handles']):
        if item.isSelected() and g.get('selected')!=i:
            g['selected']=i
            _draw(g)
            return


def _sync_handles(g):
    """Observe built-in QGraphicsItem drag through scene.changed, no classes."""
    if g.get('_drawing'):
        return
    left,top,w,h = g['rect']
    for i,item in enumerate(g['handles']):
        p = item.pos()
        x,y = (p.x()-left)/w,1-(p.y()-top)/h
        old = g['points'][i]
        if abs(x-old[0])+abs(y-old[1])>1e-5:
            g['selected']=i
            MovePoint(i,x,y,g)
            return
    if g.get('mode')!='bezier':
        return
    i = g.get('selected',0)
    t = _tangents(g)[i]
    for side,item in g['tangent_items'].items():
        if not item.isVisible():
            continue
        p = item.pos()
        x,y = (p.x()-left)/w,1-(p.y()-top)/h
        key = g['points'][i]
        dx,dy = x-key[0],y-key[1]
        expected = t[side]
        if abs(dx-expected[0])+abs(dy-expected[1])>1e-5:
            MoveTangent(i,side,dx,dy,g)
            return



def _point_index_at(g, view_pos, radius=13):
    """Find a graph key using QGraphicsView viewport-local mouse coordinates.

    In Maya the view can be scaled/embedded by a layout, so the fallback hit
    test uses viewport pixels rather than requiring an exact scene-item hit.
    """
    view = g['widget']
    scene_pos = view.mapToScene(view_pos)

    # Prefer the actual QGraphicsItem hit, including overlaid scene items.
    for item in g['scene'].items(scene_pos):
        if item in g['handles']:
            return g['handles'].index(item)
        if item in g['tangent_items'].values():
            return g.get('selected', 0)

    # The painted point is small; right-clicking just beside it should work.
    best, best_sq = None, radius * radius
    for i, item in enumerate(g['handles']):
        p = view.mapFromScene(item.scenePos())
        dist_sq = (float(p.x()) - float(view_pos.x()))**2 + \
                  (float(p.y()) - float(view_pos.y()))**2
        if dist_sq <= best_sq:
            best, best_sq = i, dist_sq
    return best


def _point_menu(g, key):
    """Build the point's native Qt menu; each action changes just this graph."""
    QtCore, QtGui, QtWidgets = g['qt']
    menu = QtWidgets.QMenu(g['widget'])

    for label, kind in (('Auto Tangent', 'auto'),
                        ('Flat Tangent', 'flat'),
                        ('Linear Tangent', 'linear'),
                        ('Free Tangent', 'free')):
        action = menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(_tangents(g)[key]['type'] == kind)
        action.triggered.connect(
            lambda checked=False, i=key, m=kind: SetTangentMode(m, g, i))

    menu.addSeparator()
    broken = _tangents(g)[key]['broken']
    action = menu.addAction('Link Tangents' if broken else 'Break Tangents')
    action.setEnabled(0 < key < len(g['points'])-1)
    action.triggered.connect(
        lambda checked=False, i=key, value=not broken:
            BreakTangents(i, value, g))

    menu.addSeparator()
    action = menu.addAction('Delete Point')
    action.setEnabled(0 < key < len(g['points'])-1)
    action.triggered.connect(
        lambda checked=False, i=key: RemovePoint(i, g))
    return menu


def _show_point_menu(g, view_pos):
    """Open right-click menu on a key (or its tangent handle).

    For QGraphicsView (a QAbstractScrollArea), Qt emits the VIEW's
    customContextMenuRequested with a *viewport-local* QPoint. Connecting
    this signal to viewport() was unreliable in Maya's nested Qt layouts.
    """
    key = _point_index_at(g, view_pos)
    if key is None:
        return False

    g['scene'].clearSelection()
    g['handles'][key].setSelected(True)
    g['selected'] = key
    _draw(g)

    menu = _point_menu(g, key)
    try:
        show = getattr(menu, 'exec_', None) or menu.exec
        show(g['widget'].viewport().mapToGlobal(view_pos))
    finally:
        menu.deleteLater()  # avoid retaining a QMenu per click in long Maya sessions
    return True


def CreateGraph(parent=None,points=None,on_change=None,
                width=360,height=200,mode='bezier'):
    """Independent curve widget dictionary; embed with layout.addWidget(g['widget'])."""
    if mode not in ('smooth','linear','bezier'):
        raise ValueError('Mode must be smooth, linear or bezier')
    QtCore,QtGui,QtWidgets = _qt()
    width,height = max(200,int(width)), max(140,int(height))
    pts = _validate(points if points is not None else [(0,0),(1,1)])
    g = {'points':pts,'mode':mode,'on_change':on_change,
         'qt':(QtCore,QtGui,QtWidgets),'handles':[],'selected':0}
    view = QtWidgets.QGraphicsView(parent)
    scene = QtWidgets.QGraphicsScene(view)
    view.setScene(scene)
    view.setMinimumSize(width,height)
    view.setRenderHint(QtGui.QPainter.Antialiasing)
    view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    view.setBackgroundBrush(QtGui.QBrush(QtGui.QColor('#242931')))
    left,top,w,h = 28,24,width-50,height-52
    scene.setSceneRect(0,0,width-4,height-4)
    scene.addRect(left,top,w,h,QtGui.QPen(QtGui.QColor('#64748b')))
    grid_pen = QtGui.QPen(QtGui.QColor('#3c4653'))
    for i in (1,2,3):
        f = i/4.0
        scene.addLine(left+f*w,top,left+f*w,top+h,grid_pen)
        scene.addLine(left,top+f*h,left+w,top+f*h,grid_pen)
    curve = scene.addPath(QtGui.QPainterPath(),QtGui.QPen(QtGui.QColor('#38d6b4'),2.4))
    tangent_pen = QtGui.QPen(QtGui.QColor('#edac5f'),1.3)
    lines = {side:scene.addLine(0,0,0,0,tangent_pen) for side in ('in','out')}
    tangent_items = {side:_dot(scene,QtGui,QtWidgets,8,'#efb86d')
                     for side in ('in','out')}
    g.update(widget=view,scene=scene,path=curve,rect=(left,top,w,h),
             tangent_items=tangent_items,tangent_lines=lines)
    _tangents(g)
    _draw(g,rebuild=True)
    scene.selectionChanged.connect(lambda: _on_selection(g))
    scene.changed.connect(lambda *args: _sync_handles(g))
    # QGraphicsView inherits QAbstractScrollArea. Use the view's signal,
    # not viewport().customContextMenuRequested (which can be swallowed by
    # the graphics scene in Maya). Qt supplies viewport-local coordinates.
    view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
    view.customContextMenuRequested.connect(
        lambda position: _show_point_menu(g, position))
    return g


def ShowGraph(*args):
    """Minimal demo: preset combo, one-shot Flip X button, key addition, key menu."""
    global _DEMO, _DEFAULT
    if _DEMO:
        try:
            _DEMO['window'].show()
            _DEMO['window'].raise_()
            return _DEMO['window']
        except RuntimeError:
            _DEMO = None
    QtCore, QtGui, QtWidgets = _qt()
    win = QtWidgets.QDialog()
    win.setWindowTitle('NLTA Curve Graph - Editable Bezier')
    layout = QtWidgets.QVBoxLayout(win)
    graph = CreateGraph(parent=win, mode='bezier', width=490, height=265)
    SetData(GetData(_DEFAULT), graph)
    layout.addWidget(graph['widget'])

    bar = QtWidgets.QHBoxLayout()
    shape = QtWidgets.QComboBox()
    shape.addItem('Custom', None)
    for label, code in PresetNames():
        shape.addItem(label, code)
    reverse = QtWidgets.QPushButton('Reverse')
    add = QtWidgets.QPushButton('+ Point')
    bar.addWidget(QtWidgets.QLabel('Shape'))
    bar.addWidget(shape, 1)
    bar.addWidget(reverse)
    bar.addWidget(add)
    layout.addLayout(bar)

    info = QtWidgets.QLabel('Right-click a point for Tangents / Delete')
    layout.addWidget(info)
    busy = {'preset':False}

    def refresh(*_, mark_custom=True):
        if mark_custom and not busy['preset']:
            shape.blockSignals(True)
            shape.setCurrentIndex(0)
            shape.blockSignals(False)
        info.setText('Key %d | f(0.5) = %.4f  |  Right-click a point to edit tangents' % (
            graph.get('selected', 0), GetValue(0.5, graph)))

    def pick_shape(index):
        name = shape.itemData(index)
        if name is None:
            return
        busy['preset'] = True
        try:
            SetPreset(name, graph)
        finally:
            busy['preset'] = False
        refresh(mark_custom=False)

    def toggle_reverse(*_):
        busy['preset'] = True
        try:
            Reverse(graph)
        finally:
            busy['preset'] = False
        refresh(mark_custom=True)

    def add_midpoint(*_):
        points = GetPoints(graph)
        a,b = max(zip(points, points[1:]),
                  key=lambda pair: pair[1][0]-pair[0][0])
        x = (a[0]+b[0])/2.0
        AddPoint(x, GetValue(x, graph), graph)

    shape.currentIndexChanged.connect(pick_shape)
    reverse.clicked.connect(toggle_reverse)
    add.clicked.connect(add_midpoint)
    graph['on_change'] = refresh
    graph['scene'].selectionChanged.connect(lambda: refresh(mark_custom=False))
    refresh()
    graph['window'] = win
    _DEMO = graph
    _DEFAULT = graph
    win.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    win.show()
    return win


def GraphUI(*args):
    return ShowGraph(*args)
