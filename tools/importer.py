"""A skinned glTF mesh (from Blender, weighted to the armature that gltf.export writes) turned into
new geometry for a driver model.

The mesh is taken in its rest pose: each vertex is skinned with the file's own joint matrices and
inverse bind matrices, which puts it where it sits in the scene, and that scene position is the
game's bind space (gltf.export places the armature at the game's bind pose). So the armature's
bones must keep their exported rest positions; the mesh may be edited freely.
"""
import math
import struct

import gltf

MAX_INFLUENCES = 8
DEFAULT_SLOT = 'Cloth'


# --- glTF scene ------------------------------------------------------------------------------
def quat_matrix(q):
    x, y, z, w = q
    return [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0,
            2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0,
            2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0,
            0, 0, 0, 1]


def node_matrix(node):
    if 'matrix' in node:
        return list(node['matrix'])
    t = node.get('translation', (0, 0, 0))
    s = node.get('scale', (1, 1, 1))
    m = quat_matrix(node.get('rotation', (0, 0, 0, 1)))
    for c in range(3):
        for r in range(3):
            m[4 * c + r] *= s[c]
    m[12:15] = t
    return m


def world_matrices(doc):
    nodes = doc.get('nodes', [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get('children', []):
            parent[c] = i
    cache = {}

    def world(i):
        if i not in cache:
            m = node_matrix(nodes[i])
            cache[i] = gltf.mul(world(parent[i]), m) if i in parent else m
        return cache[i]

    return [world(i) for i in range(len(nodes))], parent


def transform(m, p, w=1.0):
    return tuple(m[r] * p[0] + m[4 + r] * p[1] + m[8 + r] * p[2] + m[12 + r] * w for r in range(3))


def normalize(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def read_scene(blob):
    """Primitives in game bind space: [{'material', 'positions', 'normals', 'uvs', 'influences',
    'indices'}], influences per vertex being [(bone name, weight)]; and {bone: parent bone}."""
    doc, binary = gltf.read_glb(blob)
    worlds, parent = world_matrices(doc)
    nodes = doc['nodes']
    hierarchy = {nodes[i].get('name', ''): nodes[p].get('name', '') for i, p in parent.items()}
    prims = []
    for ni, node in enumerate(nodes):
        if 'mesh' not in node:
            continue
        skin = doc['skins'][node['skin']] if 'skin' in node else None
        if skin is None:
            raise ValueError(f'mesh "{node.get("name")}" has no skin: parent it to the armature '
                             '(Armature deform) and weight it before exporting')
        joints = skin['joints']
        ibm = gltf.accessor(doc, binary, skin['inverseBindMatrices']) if 'inverseBindMatrices' in skin \
            else [[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]] * len(joints)
        skinning = [gltf.mul(worlds[j], list(ibm[k])) for k, j in enumerate(joints)]
        names = [nodes[j].get('name', '') for j in joints]
        for prim in doc['meshes'][node['mesh']]['primitives']:
            if prim.get('mode', 4) != 4:
                continue
            a = prim['attributes']
            pos = gltf.accessor(doc, binary, a['POSITION'])
            nrm = gltf.accessor(doc, binary, a['NORMAL']) if 'NORMAL' in a else [(0, 0, 1)] * len(pos)
            uv = gltf.accessor(doc, binary, a['TEXCOORD_0']) if 'TEXCOORD_0' in a else [(0, 0)] * len(pos)
            sets = []
            for s in range(4):
                if f'JOINTS_{s}' in a:
                    sets.append((gltf.accessor(doc, binary, a[f'JOINTS_{s}']),
                                 gltf.accessor(doc, binary, a[f'WEIGHTS_{s}'])))
            if not sets:
                raise ValueError(f'mesh "{node.get("name")}" has no bone weights')
            idx = gltf.accessor(doc, binary, prim['indices']) if 'indices' in prim else list(range(len(pos)))
            out = {'material': doc['materials'][prim['material']].get('name', '') if 'material' in prim else '',
                   'positions': [], 'normals': [], 'uvs': [], 'influences': [], 'indices': list(idx)}
            for v in range(len(pos)):
                infl = {}
                for js, ws in sets:
                    for j, w in zip(js[v], ws[v]):
                        if w > 0:
                            infl[j] = infl.get(j, 0) + w
                total = sum(infl.values())
                if total <= 0:
                    raise ValueError(f'mesh "{node.get("name")}": a vertex has no bone weights '
                                     '(weight every vertex; Normalize All in weight paint)')
                m = [0.0] * 16
                for j, w in infl.items():
                    for k in range(16):
                        m[k] += skinning[j][k] * w / total
                out['positions'].append(gltf.from_gltf_point(transform(m, pos[v])))
                out['normals'].append(normalize(gltf.from_gltf_vector(transform(m, nrm[v], 0.0))))
                out['uvs'].append(tuple(uv[v]))
                out['influences'].append([(names[j], w / total) for j, w in infl.items()])
            prims.append(out)
    if not prims:
        raise ValueError('no skinned mesh in the file')
    return prims, hierarchy


# --- conversion ------------------------------------------------------------------------------
def quantize(influences, limit=MAX_INFLUENCES):
    """Up to `limit` (blend index, weight) pairs as u8 weights summing to 255 (largest
    remainder), padded to 8."""
    merged = {}
    for j, w in influences:
        merged[j] = merged.get(j, 0) + w
    top = sorted(merged.items(), key=lambda kv: -kv[1])[:limit]
    total = sum(w for _, w in top)
    raw = [w / total * 255 for _, w in top]
    ints = [int(x) for x in raw]
    for k in sorted(range(len(raw)), key=lambda k: ints[k] - raw[k])[:255 - sum(ints)]:
        ints[k] += 1
    pairs = [(j, w) for (j, _), w in zip(top, ints) if w > 0]
    joints = [j for j, _ in pairs] + [pairs[0][0]] * (8 - len(pairs))
    weights = [w for _, w in pairs] + [0] * (8 - len(pairs))
    return joints, weights


def tangents(positions, normals, uvs, indices):
    acc = [[0.0, 0.0, 0.0] for _ in positions]
    for t in range(0, len(indices), 3):
        a, b, c = indices[t:t + 3]
        e1 = [positions[b][k] - positions[a][k] for k in range(3)]
        e2 = [positions[c][k] - positions[a][k] for k in range(3)]
        du1, dv1 = uvs[b][0] - uvs[a][0], uvs[b][1] - uvs[a][1]
        du2, dv2 = uvs[c][0] - uvs[a][0], uvs[c][1] - uvs[a][1]
        det = du1 * dv2 - du2 * dv1
        if abs(det) < 1e-12:
            continue
        r = 1.0 / det
        tan = [(e1[k] * dv2 - e2[k] * dv1) * r for k in range(3)]
        for v in (a, b, c):
            for k in range(3):
                acc[v][k] += tan[k]
    out = []
    for t, n in zip(acc, normals):
        d = sum(t[k] * n[k] for k in range(3))
        t = [t[k] - n[k] * d for k in range(3)]  # Gram-Schmidt against the normal
        if sum(c * c for c in t) < 1e-12:
            t = [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0]
            d = sum(t[k] * n[k] for k in range(3))
            t = [t[k] - n[k] * d for k in range(3)]
        out.append(normalize(t))
    return out


def bone_lookup(model, hierarchy):
    """bone name -> blend index of this model, a bone it lacks falling back to its nearest
    ancestor that it has (LODs 3 and 4 keep half of the skeleton)."""
    blend = {b['name']: b['blend'] for b in model.bones if b['blend'] >= 0}
    parents = dict(hierarchy)
    for b in model.bones:
        if b['parent'] >= 0:
            parents.setdefault(b['name'], model.bones[b['parent']]['name'])
    cache = {}

    def find(name):
        if name not in cache:
            n, seen = name, set()
            while n not in blend:
                if n in seen or n not in parents:
                    raise ValueError(f'bone "{name}" is not in Crash\'s skeleton: weight the mesh only '
                                     'to the bones of the exported armature')
                seen.add(n)
                n = parents[n]
            cache[name] = blend[n]
        return cache[name]

    return find


def chunks(triangles, bones_of, limit, max_vertices=0xFFFF):
    """Triangles grouped so a group uses at most `limit` bones and max_vertices vertices.
    Triangles are taken in order of their main bone, which keeps neighbours together."""
    order = sorted(triangles, key=lambda t: min(bones_of[t[0]]))
    groups, current, used, verts = [], [], set(), set()
    for tri in order:
        need = set().union(*(bones_of[v] for v in tri))
        if current and (len(used | need) > limit or len(verts | set(tri)) > max_vertices):
            groups.append(current)
            current, used, verts = [], set(), set()
        if len(need) > limit:
            raise ValueError('a triangle uses more than 25 bones')
        current.append(tri)
        used |= need
        verts |= set(tri)
    if current:
        groups.append(current)
    return groups


def build_calls(model, prims, hierarchy, slots, default=DEFAULT_SLOT):
    """Draw calls for Model.replace. slots: glTF material name -> the character's material name;
    an unnamed material goes to `default`, and so does a slot this LOD lacks."""
    find = bone_lookup(model, hierarchy)
    templates = {}
    for i, dc in enumerate(model.draw_calls):
        templates.setdefault(model.materials[dc['material']], i)
    calls = []
    for prim in prims:
        slot = slots.get(prim['material'], prim['material'] if prim['material'] in templates else default)
        if slot not in templates:
            slot = default
        template = templates[slot]
        # Some formats hold 4 influences (one weight element), others 8.
        limit = 4 * sum(1 for t, *_ in model.draw_calls[template]['elements'] if t == 0x1A)
        verts = []
        tans = tangents(prim['positions'], prim['normals'], prim['uvs'], prim['indices'])
        for p, n, uv, infl, t in zip(prim['positions'], prim['normals'], prim['uvs'], prim['influences'], tans):
            joints, weights = quantize([(find(name), w) for name, w in infl], limit)
            verts.append({'position': p, 'normal': n, 'uv': uv, 'tangent': t, 'uv1': n,
                          'joints': joints, 'weights': weights})
        bones_of = [{j for j, w in zip(v['joints'], v['weights']) if w} for v in verts]
        tris = [tuple(prim['indices'][k:k + 3]) for k in range(0, len(prim['indices']) - 2, 3)]
        for group in chunks(tris, bones_of, 25):
            remap = {}
            for tri in group:
                for v in tri:
                    remap.setdefault(v, len(remap))
            palette = sorted(set().union(*(bones_of[v] for v in remap)))
            local = [None] * len(remap)
            for old, new in remap.items():
                local[new] = dict(verts[old])
                # Zero-weight slots must still name a palette bone.
                local[new]['joints'] = [j if j in palette else palette[0] for j in local[new]['joints']]
            calls.append({'template': template, 'vertices': local, 'palette': palette,
                          'indices': [remap[v] for tri in group for v in tri]})
    return calls
