"""Skinned actor models (actors_stripped/*.igz) of CTR Nitro-Fueled: read the skeleton and the
draw calls, and write new geometry back.

Object layout in these files (offsets from the object start; refs as in igz.py):

    igModelData             +0x70 vector of igModelDrawCallData refs
                            +0x88 vector of u32 (one per draw call, all zero in the drivers)
                            +0xb8 vector of u32: the bone palettes of all draw calls, back to back
    igModelDrawCallData     +0x10 name (string index), +0x20 two floats (min x, min y of the call)
                            +0x40 material handle (0x80000000 | EXNM index)
                            +0x48 igGraphicsVertexBuffer, +0x50 igGraphicsIndexBuffer
                            +0x60 u16 palette start, u16 palette length (at most 25 bones)
    igGraphicsVertexBuffer  +0x20 igVertexBuffer
    igVertexBuffer          +0x0c vertex count, +0x10 memory (u32 vertex count), +0x20 memory (vertices)
                            +0x30 igVertexFormat
    igVertexFormat          +0x0c stride, +0x10 memory: 12-byte elements
                            {u8 type, u8, u8, u8 count, u8 usage, u8 usage index, u16, u16 offset, u16}
    igGraphicsIndexBuffer   +0x20 igIndexBuffer
    igIndexBuffer           +0x0c index count, +0x10 memory (u32 index count), +0x20 memory (u16 indices)
    CGraphicsSkinInfo       +0x48 six floats: bounds min xyz, max xyz
    igSkeleton2             +0x18 igSkeletonBoneList, +0x20 memory: 4x4 inverse bind matrices,
                            row-major with the translation in the last row (v' = v M)
    igSkeletonBoneList      +0x0c count, +0x18 memory: bone refs
    igSkeletonBone          +0x10 name, +0x18 i32 parent, +0x1c i32 blend matrix index (-1 for none),
                            +0x20 three floats: translation from the parent

Vertices are triangle lists with u16 indices. Bone indices in a vertex are positions in the draw
call's palette; the palette holds blend matrix indices. A vertex has up to 8 influences, u8
weights summing to 255.
"""
import struct

from igz import Igz

# Vertex element types (igVertexElementType) seen in the drivers.
FLOAT3, HALF2, COLOR, UBYTE4N, UINT4, UNUSED = 0x02, 0x2A, 0x04, 0x1A, 0x0D, 0x2C
# Usages.
POSITION, NORMAL, TANGENT, COLOR_USAGE, TEXCOORD, BLENDWEIGHTS, BLENDINDICES = 0, 1, 2, 4, 5, 6, 8
PALETTE_LIMIT = 25


def elements(z, vf):
    size, _, ptr = z.memory(vf, 0x10)
    raw = z.raw(ptr, size)
    out = []
    for i in range(0, size, 12):
        t, _, _, _, usage, index, _, offset, _ = struct.unpack_from('<BBBBBBHHH', raw, i)
        if t == UNUSED:
            break
        out.append((t, usage, index, offset))
    return out


def decode_vertex(raw, elems, palette):
    v = {'joints': [0] * 8, 'weights': [0] * 8}
    for t, usage, index, off in elems:
        if t == FLOAT3:
            value = struct.unpack_from('<3f', raw, off)
        elif t == HALF2:
            value = struct.unpack_from('<2e', raw, off)
        elif t == COLOR:
            value = tuple(raw[off:off + 4])
        elif t == UBYTE4N:
            v['weights'][4 * index:4 * index + 4] = raw[off:off + 4]
            continue
        elif t == UINT4:
            v['joints'][4 * index:4 * index + 4] = [palette[j] for j in struct.unpack_from('<4I', raw, off)]
            continue
        else:
            raise ValueError(f'unknown vertex element type {t:#x}')
        key = {POSITION: 'position', NORMAL: 'normal', TANGENT: 'tangent', COLOR_USAGE: 'color'}.get(usage)
        if usage == TEXCOORD:
            key = 'uv' if index == 0 else 'uv1'
        v[key] = value
    return v


def encode_vertex(v, elems, stride, slot):
    """slot: blend matrix index -> position in the call's palette."""
    out = bytearray(stride)
    for t, usage, index, off in elems:
        if t == UBYTE4N:
            out[off:off + 4] = bytes(v['weights'][4 * index:4 * index + 4])
            continue
        if t == UINT4:
            joints = v['joints'][4 * index:4 * index + 4]
            weights = v['weights'][4 * index:4 * index + 4]
            # A slot with no weight may name any bone; the game's files repeat one of the palette's.
            struct.pack_into('<4I', out, off, *[slot[j] if w else slot.get(j, 0) for j, w in zip(joints, weights)])
            continue
        key = {POSITION: 'position', NORMAL: 'normal', TANGENT: 'tangent', COLOR_USAGE: 'color'}.get(usage)
        if usage == TEXCOORD:
            key = 'uv' if index == 0 else 'uv1'
        if t == FLOAT3:
            # The fur formats carry a second direction in TEXCOORD1; the normal stands in for it.
            value = v.get(key) or (v['normal'] if key == 'uv1' else (0.0, 0.0, 0.0))
            struct.pack_into('<3f', out, off, *value)
        elif t == HALF2:
            struct.pack_into('<2e', out, off, *v.get(key, (0.0, 0.0)))
        elif t == COLOR:
            out[off:off + 4] = bytes(v.get(key, (255, 255, 255, 255)))
    return bytes(out)


class Model:
    def __init__(self, blob):
        self.z = z = Igz(blob)
        self.objs = z.objects()
        self.starts = [r for r, _ in self.objs]
        self.materials = [name for name, _ in z.exnm()]
        self.model_data = self.first('igModelData')
        self.skin_info = self.first('CGraphicsSkinInfo')
        self.read_skeleton()
        self.read_draw_calls()

    def first(self, type_name):
        return next(r for r, t in self.objs if t == type_name)

    def vector(self, ref, add):
        """An igVector field: (count, data reference)."""
        return self.z.u64(ref, add), self.z.memory(ref, add + 8)[2]

    # --- skeleton ----------------------------------------------------------------------------
    def read_skeleton(self):
        z = self.z
        sk = self.first('igSkeleton2')
        bone_list = z.u64(sk, 0x18)
        count = z.u32(bone_list, 0x0c)
        _, _, items = z.memory(bone_list, 0x18)
        _, _, ibm = z.memory(sk, 0x20)
        self.bones = []
        for i in range(count):
            b = z.u64(items, 8 * i)
            parent, blend = struct.unpack('<ii', z.raw(b, 8, 0x18))
            self.bones.append({
                'name': z.strings[z.u32(b, 0x10)], 'parent': parent, 'blend': blend,
                'translation': z.f32(b, 0x20, 3),
                'inverse_bind': z.f32(ibm, 64 * blend, 16) if blend >= 0 else None,
            })
        self.blend_bones = {b['blend']: i for i, b in enumerate(self.bones) if b['blend'] >= 0}

    # --- draw calls --------------------------------------------------------------------------
    def read_draw_calls(self):
        z = self.z
        count, items = self.vector(self.model_data, 0x70)
        pcount, pitems = self.vector(self.model_data, 0xb8)
        self.palette = [z.u32(pitems, 4 * i) for i in range(pcount)]
        self.draw_calls = []
        for i in range(count):
            dc = z.u64(items, 8 * i)
            vb = z.u64(z.u64(dc, 0x48), 0x20)
            ib = z.u64(z.u64(dc, 0x50), 0x20)
            vf = z.u64(vb, 0x30)
            start, length = struct.unpack('<HH', z.raw(dc, 4, 0x60))
            self.draw_calls.append({
                'ref': dc, 'vb': vb, 'ib': ib, 'vf': vf,
                'material': z.u32(dc, 0x40) & 0x7FFFFFFF,
                'stride': z.u32(vf, 0x0c), 'elements': elements(z, vf),
                'palette': self.palette[start:start + length],
            })

    def geometry(self, dc):
        """(vertices, indices) of a draw call; vertex joints are blend matrix indices."""
        z = self.z
        n = z.u32(dc['vb'], 0x0c)
        _, _, vp = z.memory(dc['vb'], 0x20)
        raw = z.raw(vp, n * dc['stride'])
        verts = [decode_vertex(raw[i * dc['stride']:(i + 1) * dc['stride']], dc['elements'], dc['palette'])
                 for i in range(n)]
        m = z.u32(dc['ib'], 0x0c)
        _, _, ip = z.memory(dc['ib'], 0x20)
        indices = list(struct.unpack_from(f'<{m}H', z.raw(ip, 2 * m)))
        return verts, indices

    # --- writing -----------------------------------------------------------------------------
    def span(self, ref):
        i = self.starts.index(ref)
        if i + 1 < len(self.starts) and self.starts[i + 1] >> 27 == ref >> 27:
            return ref, self.starts[i + 1]
        return ref, (ref & ~0x7FFFFFF) | len(self.z.data[ref >> 27])

    def closure(self, root):
        """The objects reachable from root through references in section 1."""
        z = self.z
        todo, seen = [root], []
        while todo:
            r = todo.pop()
            if r in seen:
                continue
            seen.append(r)
            a, e = self.span(r)
            for s in z.sites['ROFS']:
                if a <= s < e:
                    t = z.u64(s)
                    if t >> 27 == 0 and t in self.starts and t not in seen:
                        todo.append(t)
        return sorted(seen)

    def clone_draw_call(self, dc_ref):
        """A copy of a draw call and every object under it, added at the end of section 1."""
        z = self.z
        spans = [self.span(r) for r in self.closure(dc_ref)]
        data = z.data[0]
        while len(data) % 16:
            data.append(0)
        moved = {}
        for a, e in spans:
            moved[a] = len(data)
            data += z.data[0][a:e]
            while len(data) % 16:
                data.append(0)

        def remap(x):
            for a, e in spans:
                if a <= x < e:
                    return moved[a] + (x - a)
            return None

        for tag, sites in z.sites.items():
            added = [remap(s) for s in sites if remap(s) is not None]
            sites.extend(added)
            sites.sort()
        for a, e in spans:
            for s in z.sites['ROFS']:
                if moved[a] <= s < moved[a] + (e - a):
                    t = remap(z.u64(s))
                    if t is not None:
                        z.write(s, 0, struct.pack('<Q', t))
        self.starts = sorted(set(self.starts) | {moved[a] for a, _ in spans})
        return moved[dc_ref]

    def append_memory(self, section, payload, align=16):
        """payload added at the end of a section: its reference."""
        data = self.z.data[section]
        while len(data) % align:
            data.append(0)
        off = len(data)
        data += payload
        return section << 27 | off

    def set_memory(self, ref, add, payload, section, align=16):
        target = self.append_memory(section, payload, align)
        self.z.write(ref, add, struct.pack('<I', len(payload)))
        self.z.write(ref, add + 8, struct.pack('<Q', target))
        return target

    def set_vector(self, ref, add, payload, count, references=False):
        """references: the elements are object references, which need ROFS entries."""
        self.z.write(ref, add, struct.pack('<Q', count))
        target = self.set_memory(ref, add + 8, payload, 0)
        if references:
            self.z.sites['ROFS'].extend(target + 8 * i for i in range(count))
            self.z.sites['ROFS'].sort()

    def replace(self, calls):
        """New geometry. calls: [{'template': draw call index of this model, 'vertices': [...],
        'indices': [...], 'palette': [blend matrix indices, at most 25]}]. Each new call is a clone
        of its template; the original calls stay in the file, unreferenced."""
        z = self.z
        refs, palette, lo, hi = [], [], [1e9] * 3, [-1e9] * 3
        for call in calls:
            tpl = self.draw_calls[call['template']]
            if len(call['palette']) > PALETTE_LIMIT:
                raise ValueError('a draw call can use at most 25 bones')
            if len(call['vertices']) > 0xFFFF:
                raise ValueError('a draw call can have at most 65535 vertices')
            dc = self.clone_draw_call(tpl['ref'])
            vb = z.u64(z.u64(dc, 0x48), 0x20)
            ib = z.u64(z.u64(dc, 0x50), 0x20)
            slot = {j: i for i, j in enumerate(call['palette'])}
            verts = b''.join(encode_vertex(v, tpl['elements'], tpl['stride'], slot) for v in call['vertices'])
            n, m = len(call['vertices']), len(call['indices'])
            z.write(vb, 0x0c, struct.pack('<I', n))
            z.write(z.memory(vb, 0x10)[2], 0, struct.pack('<I', n))
            self.set_memory(vb, 0x20, verts, 1)
            z.write(ib, 0x0c, struct.pack('<I', m))
            z.write(z.memory(ib, 0x10)[2], 0, struct.pack('<I', m))
            self.set_memory(ib, 0x20, struct.pack(f'<{m}H', *call['indices']), 1)
            z.write(dc, 0x60, struct.pack('<HH', len(palette), len(call['palette'])))
            xs = [v['position'] for v in call['vertices']]
            for k in range(3):
                lo[k] = min([lo[k]] + [p[k] for p in xs])
                hi[k] = max([hi[k]] + [p[k] for p in xs])
            z.write(dc, 0x20, struct.pack('<2f', min(p[0] for p in xs), min(p[1] for p in xs)))
            palette += call['palette']
            refs.append(dc)
        self.set_vector(self.model_data, 0x70, struct.pack(f'<{len(refs)}Q', *refs), len(refs), True)
        self.set_vector(self.model_data, 0x88, bytes(4 * len(refs)), len(refs))
        self.set_vector(self.model_data, 0xb8, struct.pack(f'<{len(palette)}I', *palette), len(palette))
        # Keep the skin bounds at least as large as the game's: they cover the animated poses.
        old = z.f32(self.skin_info, 0x48, 6)
        margin = 40.0
        bounds = [min(old[k], lo[k] - margin) for k in range(3)] + [max(old[3 + k], hi[k] + margin) for k in range(3)]
        z.write(self.skin_info, 0x48, struct.pack('<6f', *bounds))
        self.compact()
        return z.build()

    def compact(self):
        """Drop the replaced geometry: the original draw calls (kept, unreferenced, so no object
        is removed) get one degenerate triangle, and the vertex section is rebuilt with only the
        buffers still referenced. Only vertex and index buffers point into that section. A
        driver's files have to fit the game's per-driver memory pool."""
        z = self.z
        stride = max(dc['stride'] for dc in self.draw_calls)
        dummy_v = self.append_memory(1, bytes(3 * stride))
        dummy_i = self.append_memory(1, bytes(6))
        for dc in self.draw_calls:
            for buf, count, size, target in ((dc['vb'], 3, 3 * dc['stride'], dummy_v), (dc['ib'], 3, 6, dummy_i)):
                z.write(buf, 0x0c, struct.pack('<I', count))
                z.write(z.memory(buf, 0x10)[2], 0, struct.pack('<I', count))
                z.write(buf, 0x20, struct.pack('<I', size))
                z.write(buf, 0x28, struct.pack('<Q', target))
        old, new, moved = z.data[1], bytearray(), {}
        for site in z.sites['ROFS']:
            target = z.u64(site)
            if target >> 27 != 1:
                continue
            if target not in moved:
                size = z.u32(site, -8)
                new += bytes((-len(new)) % 16)
                moved[target] = 1 << 27 | len(new)
                off = target & 0x7FFFFFF
                new += old[off:off + size]
            z.write(site, 0, struct.pack('<Q', moved[target]))
        z.data[1] = new
