"""XNALara / XPS binary models (.mesh, as Fortnite rips are often shared), read with no
dependencies. Layout follows the XNALara-io-Tools Blender add-on (read_bin_xps.py).

    header      u32 magic 323232, u16 major, u16 minor, string "XNAaral", u32 settings length (in
                u32), string machine, string user, string files, then the settings block
                (settings length * 4 bytes; versions up to 2.12 have no header at all)
    bones       u32 count, then {string name, i16 parent (-1: none), 3 f32 position}
    meshes      u32 count, then {string name, u32 UV layers, u32 textures,
                {string file, u32 UV layer} per texture, u32 vertices, per vertex
                {3 f32 position, 3 f32 normal, 4 u8 colour, 2 f32 per UV layer,
                 4 f32 tangent per UV layer (versions up to 2.12),
                 bone weights (when there are bones): i16 count (version 3+, else 4),
                 count i16 bone indices, count f32 weights},
                u32 triangles, 3 u32 per triangle}

A string is a 1-2 byte length (7 bits each, low first) and its bytes. Positions are Y up.
"""
import struct

MAGIC = 323232


class Reader:
    def __init__(self, data):
        self.data, self.p = data, 0

    def take(self, fmt):
        values = struct.unpack_from('<' + fmt, self.data, self.p)
        self.p += struct.calcsize('<' + fmt)
        return values

    def string(self):
        n = self.data[self.p]
        self.p += 1
        if n >= 128:
            n = n % 128 + self.data[self.p] * 128
            self.p += 1
        s = self.data[self.p:self.p + n].decode('utf-8', 'replace')
        self.p += n
        return s


def read(data):
    """{'bones': [(name, parent, (x, y, z))], 'meshes': [{'name', 'textures': [(file, layer)],
    'positions', 'normals', 'uvs': [[(u, v)] per layer], 'joints', 'weights', 'triangles'}]}"""
    r = Reader(data)
    major, minor = 2, 12
    if struct.unpack_from('<I', data, 0)[0] == MAGIC:
        _, major, minor = r.take('IHH')
        r.string()
        settings, = r.take('I')
        r.string(), r.string(), r.string()
        r.p += settings * 4
    tangents = major <= 2 and minor <= 12
    variable = major >= 3
    count, = r.take('I')
    bones = []
    for _ in range(count):
        name = r.string()
        parent, = r.take('h')
        bones.append((name, parent, r.take('3f')))
    meshes = []
    for _ in range(r.take('I')[0]):
        mesh = {'name': r.string()}
        layers, textures = r.take('II')
        mesh['textures'] = [(r.string(), r.take('I')[0]) for _ in range(textures)]
        n, = r.take('I')
        pos, nor, uvs, joints, weights = [], [], [[] for _ in range(layers)], [], []
        for _ in range(n):
            pos.append(r.take('3f'))
            nor.append(r.take('3f'))
            r.p += 4
            for layer in uvs:
                layer.append(r.take('2f'))
            if tangents:
                r.p += 16 * layers
            if bones:
                k = r.take('h')[0] if variable else 4
                joints.append(r.take(f'{k}h'))
                weights.append(r.take(f'{k}f'))
        tris, = r.take('I')
        mesh.update(positions=pos, normals=nor, uvs=uvs, joints=joints, weights=weights,
                    triangles=[r.take('3I') for _ in range(tris)])
        meshes.append(mesh)
    if r.p != len(data):
        raise ValueError(f'{len(data) - r.p} bytes left after the last mesh')
    return {'version': (major, minor), 'bones': bones, 'meshes': meshes}


if __name__ == '__main__':
    import sys
    model = read(open(sys.argv[1], 'rb').read())
    print('version', model['version'], len(model['bones']), 'bones')
    for m in model['meshes']:
        print(f'  {m["name"]}: {len(m["positions"])} vertices, {len(m["triangles"])} triangles, '
              f'{len(m["uvs"])} UV, textures {[t for t, _ in m["textures"]]}')
