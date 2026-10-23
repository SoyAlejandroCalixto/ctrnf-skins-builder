"""glTF 2.0 (.glb) for driver models: export a game model with its skeleton, read a skinned mesh
back.

Game space is Z-up in centimetres; glTF is Y-up in metres: game (x, y, z) = glTF (x, -z, y) * 100.
Game matrices are row-major with v' = v M; glTF matrices are column-major with v' = M v, which is
the same 16 numbers, so only the change of axes and units is applied.
"""
import json
import struct

SCALE = 0.01


# --- 4x4 matrices as 16 floats, column-major (glTF) ----------------------------------------------
def mul(a, b):
    return [sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4)) for c in range(4) for r in range(4)]


def inverse(m):
    """Inverse of an affine matrix."""
    r = [m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]]  # columns of the 3x3 part
    a, b, c, d, e, f, g, h, i = r[0], r[3], r[6], r[1], r[4], r[7], r[2], r[5], r[8]  # rows
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    inv = [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det,
           (f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det,
           (d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]  # rows
    t = m[12:15]
    it = [-(inv[3 * row] * t[0] + inv[3 * row + 1] * t[1] + inv[3 * row + 2] * t[2]) for row in range(3)]
    return [inv[0], inv[3], inv[6], 0, inv[1], inv[4], inv[7], 0, inv[2], inv[5], inv[8], 0, it[0], it[1], it[2], 1]


def to_gltf_point(p):
    x, y, z = p
    return (x * SCALE, z * SCALE, -y * SCALE)


def to_gltf_vector(p):
    x, y, z = p
    return (x, z, -y)


def from_gltf_point(p):
    x, y, z = p
    return (x / SCALE, -z / SCALE, y / SCALE)


def from_gltf_vector(p):
    x, y, z = p
    return (x, -z, y)


# Axes: P maps game to glTF directions.
P = [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1]
P_INV = [1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1]


def matrix_to_gltf(m):
    out = mul(mul(P, list(m)), P_INV)
    out[12:15] = [v * SCALE for v in out[12:15]]
    return out


# --- writing ---------------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.doc = {'asset': {'version': '2.0', 'generator': 'OCTR character_import'},
                    'buffers': [{'byteLength': 0}], 'bufferViews': [], 'accessors': []}
        self.bin = bytearray()

    def accessor(self, fmt, kind, component, values, target=None, minmax=False):
        while len(self.bin) % 4:
            self.bin.append(0)
        start = len(self.bin)
        for v in values:
            self.bin += struct.pack(fmt, *(v if isinstance(v, (tuple, list)) else (v,)))
        view = {'buffer': 0, 'byteOffset': start, 'byteLength': len(self.bin) - start}
        if target:
            view['target'] = target
        self.doc['bufferViews'].append(view)
        acc = {'bufferView': len(self.doc['bufferViews']) - 1, 'componentType': component,
               'count': len(values), 'type': kind}
        if minmax:
            n = len(values[0])
            acc['min'] = [min(v[k] for v in values) for k in range(n)]
            acc['max'] = [max(v[k] for v in values) for k in range(n)]
        self.doc['accessors'].append(acc)
        return len(self.doc['accessors']) - 1

    def glb(self):
        while len(self.bin) % 4:
            self.bin.append(0)
        self.doc['buffers'][0]['byteLength'] = len(self.bin)
        js = json.dumps(self.doc, separators=(',', ':')).encode()
        js += b' ' * ((-len(js)) % 4)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        return (struct.pack('<III', 0x46546C67, 2, total) + struct.pack('<II', len(js), 0x4E4F534A) + js
                + struct.pack('<II', len(self.bin), 0x004E4942) + bytes(self.bin))


def export(model, name='CrashDriver'):
    """The model as a .glb: an armature of its blend bones and one mesh, a primitive per draw
    call, with the game's material names."""
    b = Builder()
    joints = [i for i, bone in enumerate(model.bones) if bone['blend'] >= 0]
    joint_of_blend = {model.bones[i]['blend']: k for k, i in enumerate(joints)}
    globals_ = {i: inverse(matrix_to_gltf(model.bones[i]['inverse_bind'])) for i in joints}
    nodes = []
    for i in joints:
        bone = model.bones[i]
        parent = bone['parent']
        local = globals_[i] if parent not in globals_ else mul(inverse(globals_[parent]), globals_[i])
        nodes.append({'name': bone['name'], 'matrix': [round(v, 7) for v in local]})
    for k, i in enumerate(joints):
        kids = [joints.index(j) for j in joints if model.bones[j]['parent'] == i]
        if kids:
            nodes[k]['children'] = kids
    roots = [k for k, i in enumerate(joints) if model.bones[i]['parent'] not in globals_]
    ibm = b.accessor('<16f', 'MAT4', 5126, [inverse(globals_[i]) for i in joints])
    materials = [{'name': n, 'pbrMetallicRoughness': {'metallicFactor': 0}} for n in model.materials]
    prims = []
    for dc in model.draw_calls:
        verts, indices = model.geometry(dc)
        attrs = {
            'POSITION': b.accessor('<3f', 'VEC3', 5126, [to_gltf_point(v['position']) for v in verts], 34962, True),
            'NORMAL': b.accessor('<3f', 'VEC3', 5126, [to_gltf_vector(v['normal']) for v in verts], 34962),
            'TEXCOORD_0': b.accessor('<2f', 'VEC2', 5126, [v['uv'] for v in verts], 34962),
        }
        for s in (0, 1):
            js = [[joint_of_blend[j] if w else 0 for j, w in zip(v['joints'][4 * s:4 * s + 4], v['weights'][4 * s:4 * s + 4])] for v in verts]
            ws = [[w / 255 for w in v['weights'][4 * s:4 * s + 4]] for v in verts]
            attrs[f'JOINTS_{s}'] = b.accessor('<4H', 'VEC4', 5123, js, 34962)
            attrs[f'WEIGHTS_{s}'] = b.accessor('<4f', 'VEC4', 5126, ws, 34962)
        prims.append({'attributes': attrs, 'material': dc['material'],
                      'indices': b.accessor('<I', 'SCALAR', 5125, indices, 34963)})
    mesh_node = len(nodes)
    nodes.append({'name': name, 'mesh': 0, 'skin': 0})
    arm = len(nodes)
    nodes.append({'name': name + '_Armature', 'children': roots + [mesh_node]})
    b.doc.update({'scene': 0, 'scenes': [{'nodes': [arm]}], 'nodes': nodes, 'materials': materials,
                  'meshes': [{'name': name, 'primitives': prims}],
                  'skins': [{'joints': list(range(len(joints))), 'inverseBindMatrices': ibm, 'skeleton': roots[0]}]})
    return b.glb()


# --- reading ---------------------------------------------------------------------------------
COMPONENTS = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
SIZES = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def read_glb(blob):
    magic, _, _ = struct.unpack_from('<III', blob, 0)
    if magic != 0x46546C67:
        raise ValueError('not a .glb file')
    p, doc, binary = 12, None, b''
    while p < len(blob):
        length, kind = struct.unpack_from('<II', blob, p)
        chunk = blob[p + 8:p + 8 + length]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        p += 8 + length
    return doc, binary


def accessor(doc, binary, index):
    acc = doc['accessors'][index]
    view = doc['bufferViews'][acc['bufferView']]
    fmt = COMPONENTS[acc['componentType']]
    n = SIZES[acc['type']]
    size = struct.calcsize(fmt)
    stride = view.get('byteStride', size * n)
    base = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    out = []
    for i in range(acc['count']):
        vals = struct.unpack_from(f'<{n}{fmt}', binary, base + i * stride)
        if acc.get('normalized'):
            scale = {'B': 255, 'H': 65535, 'b': 127, 'h': 32767}[fmt]
            vals = tuple(v / scale for v in vals)
        out.append(vals if n > 1 else vals[0])
    return out
