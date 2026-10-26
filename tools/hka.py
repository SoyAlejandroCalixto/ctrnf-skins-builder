"""Havok 2014.1 packfiles (.hka, PS4: 64-bit pointers, little-endian): a driver's skeleton and
its spline-compressed animations (anims/Drivers/Driver<X>.hka in the driver's archive or an
update), to see a model in the driver's real kart pose.

    python hka.py <game archives> <character> [animation [frame]]
        Lists the animations, or prints a frame's bone positions in the game's bind space.

Packfile: a header, then section headers (__classnames__, __types__, __data__), each
{char[20] tag, u32 data start, then local / global / virtual fixups, exports, imports, end
offsets relative to the start}. In __data__ a pointer is 8 zero bytes plus a local fixup
{u32 where, u32 to} (or a global one {where, section, to}); a virtual fixup {object, section,
class name offset} gives an object's class. hkArray is {pointer, u32 size, u32 capacity}.

hkaSplineCompressedAnimation: per block (maxFramesPerBlock frames), a mask of 4 bytes per
transform track {quantization: position bits 0-1, rotation 2-5, scale 6-7; position flags,
rotation flags, scale flags: bit i (x, y, z, w) static, bit i + 4 spline}, one byte per float
track, then per track its position, rotation and scale: a spline is {u16 control points - 1,
u8 degree, knots (n + degree + 2 bytes)}, the axes' {min, max} (static axes: the value) and the
control points quantized to 8 / 16 bits (rotations: THREECOMP40 etc.); a static value alone
otherwise. Positions and scales are 4-byte aligned after each track part.
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


class Packfile:
    def __init__(self, blob):
        self.blob = blob
        magic0, magic1 = struct.unpack_from('<2I', blob, 0)
        if (magic0, magic1) != (0x57E0E057, 0x10C0C010):
            raise ValueError('not a Havok packfile')
        sections = struct.unpack_from('<i', blob, 0x14)[0]
        # 2014 header: 0x40 bytes, then predicate padding (u16 at 0x3e, here 0x10).
        pad = struct.unpack_from('<h', blob, 0x3e)[0]
        self.sections = {}
        for i in range(sections):
            at = 0x40 + pad + 0x40 * i
            tag = blob[at:at + 19].split(b'\0')[0].decode()
            start, *offs = struct.unpack_from('<7I', blob, at + 20)
            self.sections[tag] = (start, offs)
        start, (local, glob, virt, exports, imports, end) = self.sections['__data__']
        self.data = blob[start:start + local]
        self.pointers = {}
        for i in range(local, glob - 7, 8):
            src, dst = struct.unpack_from('<2i', blob, start + i)
            if src >= 0:
                self.pointers[src] = dst
        for i in range(glob, virt - 11, 12):
            src, sec, dst = struct.unpack_from('<3i', blob, start + i)
            if src >= 0 and sec == 2:
                self.pointers[src] = dst
        cstart = self.sections['__classnames__'][0]
        self.objects = []  # (offset, class)
        for i in range(virt, exports - 11, 12):
            src, sec, name = struct.unpack_from('<3i', blob, start + i)
            if src >= 0:
                n = blob[cstart + name:blob.index(b'\0', cstart + name)].decode()
                self.objects.append((src, n))

    def of(self, cls):
        return [o for o, c in self.objects if c == cls]

    def u32(self, at):
        return struct.unpack_from('<I', self.data, at)[0]

    def f32(self, at):
        return struct.unpack_from('<f', self.data, at)[0]

    def string(self, at):
        p = self.pointers.get(at)
        return None if p is None else self.data[p:self.data.index(b'\0', p)].decode()

    def array(self, at):
        """(data offset, count) of an hkArray."""
        return self.pointers.get(at), self.u32(at + 8)

    def raw(self, at, item):
        p, n = self.array(at)
        return b'' if p is None else self.data[p:p + n * item]


class Skeleton:
    def __init__(self, pf, at):
        self.name = pf.string(at + 16)
        self.parents = list(struct.unpack('<%dh' % pf.u32(at + 32), pf.raw(at + 24, 2)))
        if not self.parents:
            p, n = pf.array(at + 40)
            self.bones, self.pose = [pf.string(p + 16 * i) for i in range(n)], []
            return
        p, n = pf.array(at + 40)
        self.bones = [pf.string(p + 16 * i) for i in range(n)]
        pose = pf.raw(at + 56, 48)
        self.pose = [qs(pose, 48 * i) for i in range(len(self.bones))]


def qs(raw, at):
    """hkQsTransform: (translation xyz, rotation xyzw, scale xyz)."""
    v = struct.unpack_from('<12f', raw, at)
    return v[0:3], v[4:8], v[8:11]


ROT_ALIGN = {0: 4, 1: 1, 2: 2, 3: 1, 4: 2, 5: 4}
ROT_SIZE = {0: 4, 1: 5, 2: 6, 3: 3, 4: 2, 5: 16}


def rotation(raw, at, kind):
    if kind == 1:  # THREECOMP40
        v = int.from_bytes(raw[at:at + 5], 'little')
        mask = (1 << 12) - 1
        c = [((v >> s) & mask) for s in (0, 12, 24)]
        shift, sign = (v >> 36) & 3, (v >> 38) & 1
        c = [(x - 2047) * (1 / 2047 / math.sqrt(2)) for x in c]
    elif kind == 2:  # THREECOMP48
        x, y, z = struct.unpack_from('<3H', raw, at)
        shift, sign = ((y >> 14) & 2) | ((x >> 15) & 1), z >> 15
        c = [((s & 0x7FFF) - 16383) * (1 / 16383 / math.sqrt(2)) for s in (x, y, z)]
    elif kind == 5:
        return struct.unpack_from('<4f', raw, at)
    else:
        raise ValueError('rotation quantization %d not supported' % kind)
    w = math.sqrt(max(0.0, 1 - sum(x * x for x in c)))
    if sign:
        w = -w
    c.insert(shift, w)
    return tuple(c)


def bspline(knots, degree, points, t):
    """de Boor: the point at t of a clamped B-spline (points: lists of floats)."""
    n = len(points) - 1
    span = degree
    while span < n and knots[span + 1] <= t:
        span += 1
    d = [list(points[j + span - degree]) for j in range(degree + 1)]
    for r in range(1, degree + 1):
        for j in range(degree, r - 1, -1):
            i = j + span - degree
            den = knots[i + degree - r + 1] - knots[i]
            a = 0 if den == 0 else (t - knots[i]) / den
            d[j] = [(1 - a) * x + a * y for x, y in zip(d[j - 1], d[j])]
    return d[degree]


class Reader:
    def __init__(self, raw, at):
        self.raw, self.at = raw, at

    def align(self, n):
        self.at += (-self.at) % n

    def take(self, fmt):
        v = struct.unpack_from('<' + fmt, self.raw, self.at)
        self.at += struct.calcsize('<' + fmt)
        return v

    def spline(self):
        n, degree = self.take('HB')
        knots = self.take('%dB' % (n + degree + 2))
        return n, degree, knots


class Animation:
    def __init__(self, pf, at):
        # hkReferencedObject is 12 bytes: type at 12, then duration, tracks, float tracks.
        self.duration = pf.f32(at + 16)
        self.tracks = pf.u32(at + 20)
        self.floats = pf.u32(at + 24)
        self.frames, self.blocks, self.per_block, self.mask_size = struct.unpack_from('<4I', pf.data, at + 56)
        self.block_duration, _, self.frame_duration = struct.unpack_from('<3f', pf.data, at + 72)
        self.block_offsets = struct.unpack('<%dI' % self.blocks, pf.raw(at + 88, 4))
        self.data = pf.raw(at + 152, 1)

    def frame(self, f):
        """[(translation, rotation, scale)] of every transform track at frame f."""
        b = min(f // (self.per_block - 1), self.blocks - 1)
        t = (f - b * (self.per_block - 1))
        r = Reader(self.data, self.block_offsets[b])
        masks = [r.take('4B') for _ in range(self.tracks)]
        r.take('%dB' % self.floats)
        r.align(4)
        out = []
        for quant, pflags, rflags, sflags in masks:
            pos = self.vector(r, pflags, quant & 3, t, (0, 0, 0))
            rot = self.rotation(r, rflags, (quant >> 2) & 15, t)
            scale = self.vector(r, sflags, (quant >> 6) & 3, t, (1, 1, 1))
            out.append((pos, rot, scale))
        return out

    def vector(self, r, flags, quant, t, identity):
        if flags & 0xF0:
            n, degree, knots = r.spline()
            r.align(4)
            ranges = []
            for i in range(3):
                if flags & (0x10 << i):
                    ranges.append(('s', r.take('2f')))
                elif flags & (1 << i):
                    ranges.append(('c', r.take('f')[0]))
                else:
                    ranges.append(('c', identity[i]))
            fmt, top = ('B', 255) if quant == 0 else ('H', 65535)
            pts = []
            for _ in range(n + 1):
                p = []
                for kind, v in ranges:
                    if kind == 's':
                        q = r.take(fmt)[0]
                        p.append(v[0] + (v[1] - v[0]) * q / top)
                    else:
                        p.append(v)
                pts.append(p)
            r.align(4)
            return tuple(bspline(knots, degree, pts, t))
        out = []
        for i in range(3):
            out.append(r.take('f')[0] if flags & (1 << i) else identity[i])
        r.align(4)
        return tuple(out)

    def rotation(self, r, flags, quant, t):
        if flags & 0xF0:
            n, degree, knots = r.spline()
            r.align(ROT_ALIGN[quant])
            pts = []
            for _ in range(n + 1):
                pts.append(rotation(r.raw, r.at, quant))
                r.at += ROT_SIZE[quant]
            # Neighbouring control points on the same hemisphere before blending.
            for i in range(1, len(pts)):
                if sum(a * b for a, b in zip(pts[i - 1], pts[i])) < 0:
                    pts[i] = tuple(-x for x in pts[i])
            q = bspline(knots, degree, pts, t)
        elif flags & 0x0F:
            r.align(ROT_ALIGN[quant])
            q = rotation(r.raw, r.at, quant)
            r.at += ROT_SIZE[quant]
        else:
            q = (0, 0, 0, 1)
        r.align(4)
        s = math.sqrt(sum(x * x for x in q)) or 1
        return tuple(x / s for x in q)


def load(blob):
    """(skeleton, {animation name: (Animation, track -> bone index)})."""
    pf = Packfile(blob)
    skeletons = [Skeleton(pf, at) for at in pf.of('hkaSkeleton')]
    # The drivers' files carry a second, boneless skeleton named animTable whose "bones" are
    # the animations' names, in the order of the container's bindings.
    skeleton = next(s for s in skeletons if s.name != 'animTable')
    table = next((s.bones for s in skeletons if s.name == 'animTable'), [])
    container = pf.of('hkaAnimationContainer')[0]
    p, n = pf.array(container + 48)
    bindings = [pf.pointers[p + 8 * i] for i in range(n)]
    anims = {}
    for i, at in enumerate(bindings):
        name = table[i] if i < len(table) else 'animation %d' % i
        anim = Animation(pf, pf.pointers[at + 24])
        bones = list(struct.unpack('<%dh' % pf.u32(at + 40), pf.raw(at + 32, 2)))
        anims[name] = (anim, bones or list(range(anim.tracks)))
    return skeleton, anims


def world(skeleton, locals_):
    """Bone (translation, rotation matrix 3x3, scale) in model space from local qs transforms.
    As Havok's hkQsTransform, a parent's scale scales its children (and the skin) but not
    their translations."""
    out = []
    for i, (t, q, s) in enumerate(locals_):
        x, y, z, w = q
        m = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
             [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
             [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
        p = skeleton.parents[i]
        if p < 0:
            out.append((list(t), m, list(s)))
            continue
        pt, pm, ps = out[p]
        out.append(([pt[r] + sum(pm[r][c] * t[c] for c in range(3)) for r in range(3)],
                    [[sum(pm[r][k] * m[k][c] for k in range(3)) for c in range(3)] for r in range(3)],
                    [a * b for a, b in zip(ps, s)]))
    return out


def skinning(skeleton, locals_, unit=1 / 2.54):
    """{bone: 4x4 row-major matrix} taking a bind-pose point (in the game models' units: the
    skeleton's / 2.54) to the posed one."""
    def matrix(t, m, s):
        return [[m[r][c] * s[c] for c in range(3)] + [t[r] * unit] for r in range(3)] + [[0, 0, 0, 1]]

    def inverse(t, m):
        mt = [[m[c][r] for c in range(3)] for r in range(3)]
        tt = [-sum(mt[r][c] * t[c] * unit for c in range(3)) for r in range(3)]
        return [mt[r] + [tt[r]] for r in range(3)] + [[0, 0, 0, 1]]

    def mul(a, b):
        return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
    bind = world(skeleton, skeleton.pose)
    posed = world(skeleton, locals_)
    return {name: mul(matrix(*posed[i]), inverse(bind[i][0], bind[i][1]))
            for i, name in enumerate(skeleton.bones)}


def pose(skeleton, anim, bones, f):
    """Local transforms of every bone at frame f (bind pose for bones without a track)."""
    locals_ = list(skeleton.pose)
    for track, value in enumerate(anim.frame(f)):
        if bones[track] >= 0:
            locals_[bones[track]] = value
    return locals_


def driver(archives, character):
    """load() of a driver's anims/Drivers/<driver>.hka: the newest copy in the update
    archives, else in the driver's own archive (<driver>.pak, nested in an update or not)."""
    import pak
    from character_mod import CHARACTERS
    name = Path(next(iter(CHARACTERS[character]['models'].values()))).name.split('_')[0]
    wanted = ('anims/drivers/%s.hka' % name).lower()
    for archive in (*pak.UPDATES, name + '.pak'):
        try:
            arc, _ = pak.open_archive(archives, archive)
        except (FileNotFoundError, KeyError, ValueError):
            continue
        for f in arc.files:
            if f['path'].lower() == wanted:
                return load(arc.extract(f))
    raise FileNotFoundError(wanted)


if __name__ == '__main__':
    archives, character = sys.argv[1], sys.argv[2]
    skeleton, anims = driver(archives, character)
    if len(sys.argv) < 4:
        for n, (a, _) in sorted(anims.items()):
            print(n, a.frames, 'frames', a.tracks, 'tracks')
    else:
        anim, bones = anims[sys.argv[3]]
        f = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        for b, (t, _, _) in zip(skeleton.bones, world(skeleton, pose(skeleton, anim, bones, f))):
            print(b, [round(x / 2.54, 3) for x in t])
