"""Textures (igImage2 in IGZ files): read them as RGBA and write new pixels.

    igImage2    +0x18 u16 width, +0x1a u16 height, +0x1e u16 mip levels, +0x38 memory: the pixels
                (the file's last section)

Pixels are BC1 (8 bytes per 4x4 block), BC3 or BC5 (16 bytes; normal maps are BC5), every mip
level in PS4 tiles of 8x8 blocks (Morton order inside a tile; partial tiles padded with zero
blocks), top row first: a vertex UV (u, v) samples row v * height counted from the top, as glTF
does. Tiling as found by kyogre21/ctrnf-modkit (autocollants/ctrnf_stickers/texture.py), which
flips its images vertically; the game showed that flip to be wrong for character textures.
Images here are lists of rows of (r, g, b, a) tuples, top row first.
"""
import struct

from igz import Igz


def _morton(t):
    return (t & 1) | (t >> 1 & 2) | (t >> 2 & 4), (t >> 1 & 1) | (t >> 2 & 2) | (t >> 3 & 4)


MORTON = [_morton(t) for t in range(64)]


def level_sizes(w, h, levels):
    return [(max(w >> k, 4), max(h >> k, 4)) for k in range(levels)]


def tiled_blocks(w, h):
    return -(-w // 32) * -(-h // 32) * 64


class Texture:
    def __init__(self, blob):
        self.z = z = Igz(blob)
        self.image = next(r for r, t in z.objects() if t == 'igImage2')
        self.width, self.height = z.u16(self.image, 0x18), z.u16(self.image, 0x1a)
        self.levels = z.u16(self.image, 0x1e)
        size, _, self.pixels = z.memory(self.image, 0x38)
        blocks = sum(tiled_blocks(w, h) for w, h in level_sizes(self.width, self.height, self.levels))
        if size == blocks * 8:
            self.block = 8
        elif size == blocks * 16:
            self.block = 16
        else:
            raise ValueError(f'unsupported texture layout ({size} bytes for {self.width}x{self.height})')
        self.size = size

    def level_blocks(self, level):
        """Linear (row-major, image top first) blocks of a mip level."""
        z, bpb = self.z, self.block
        sizes = level_sizes(self.width, self.height, self.levels)
        start = sum(tiled_blocks(w, h) for w, h in sizes[:level]) * bpb
        w, h = sizes[level]
        wb, hb = w // 4, h // 4
        raw = z.raw(self.pixels, tiled_blocks(w, h) * bpb, start)
        rows = [[None] * wb for _ in range(hb)]
        src = 0
        for ty in range(0, hb, 8):
            for tx in range(0, wb, 8):
                for x, y in MORTON:
                    if tx + x < wb and ty + y < hb:
                        rows[ty + y][tx + x] = raw[src:src + bpb]
                    src += bpb
        return rows

    def read(self, level=0):
        rows = self.level_blocks(level)
        out = [[None] * (len(rows[0]) * 4) for _ in range(len(rows) * 4)]
        for by, row in enumerate(rows):
            for bx, blk in enumerate(row):
                px = decode_block(blk)
                for i in range(16):
                    out[by * 4 + i // 4][bx * 4 + i % 4] = px[i]
        return out

    def write(self, image):
        """New pixels: image must be width x height; the mip levels are made by halving."""
        if len(image) != self.height or len(image[0]) != self.width:
            raise ValueError(f'image must be {self.width}x{self.height}')
        out = bytearray()
        level = image
        cache = {}
        for w, h in level_sizes(self.width, self.height, self.levels):
            if len(level) != h:
                level = halve(level, w, h)
            wb, hb = w // 4, h // 4
            blocks = []
            for by in range(hb):
                y = by * 4
                row = []
                for bx in range(wb):
                    px = tuple(level[y + i // 4][bx * 4 + i % 4] for i in range(16))
                    blk = cache.get(px)
                    if blk is None:
                        blk = cache[px] = (encode_bc1 if self.block == 8 else encode_bc3)(px)
                    row.append(blk)
                blocks.append(row)
            for ty in range(0, hb, 8):
                for tx in range(0, wb, 8):
                    for x, yy in MORTON:
                        out += blocks[ty + yy][tx + x] if tx + x < wb and ty + yy < hb else bytes(self.block)
        assert len(out) == self.size
        self.z.write(self.pixels, 0, bytes(out))
        return self.z.build()


    def fill(self, block):
        """Every block of every level set to one block (a flat colour or a flat normal)."""
        if len(block) != self.block:
            raise ValueError('block size does not match the texture')
        self.z.write(self.pixels, 0, block * (self.size // self.block))
        return self.z.build()

    def average(self):
        """Mean (r, g, b, a) of the smallest level at least 16x16."""
        level = max(k for k, (w, h) in enumerate(level_sizes(self.width, self.height, self.levels)) if min(w, h) >= 16)
        px = [p for row in self.read(level) for p in row]
        return tuple(sum(p[k] for p in px) // len(px) for k in range(4))


def flat_normal_bc5():
    """BC5 block of the normal (0, 0, 1): both channels 128."""
    return (bytes([128, 128]) + bytes(6)) * 2


def read_png(path):
    """8-bit RGB / RGBA PNG (no interlace) as rows of (r, g, b, a), top row first."""
    import zlib
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path} is not a PNG')
    p, idat, w = 8, b'', 0
    while p < len(data):
        n, kind = struct.unpack_from('>I4s', data, p)
        body = data[p + 8:p + 8 + n]
        if kind == b'IHDR':
            w, h, depth, color, _, _, interlace = struct.unpack('>IIBBBBB', body)
            if depth != 8 or color not in (2, 6) or interlace:
                raise ValueError(f'{path}: only 8-bit RGB/RGBA, non-interlaced PNGs')
            bpp = 4 if color == 6 else 3
        elif kind == b'IDAT':
            idat += body
        p += 12 + n
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev, at = [], bytearray(stride), 0
    for _ in range(h):
        f, line = raw[at], bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * bpp:x * bpp + bpp]) + ((255,) if bpp == 3 else ()) for x in range(w)])
        prev = line
    return rows


def write_png(path, image):
    """Rows of (r, g, b, a), top row first, as an RGBA PNG."""
    import zlib
    raw = b''.join(b'\0' + bytes(c for p in row for c in p) for row in image)

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', len(image[0]), len(image), 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def resize(image, w, h):
    """Box-filtered when shrinking by a whole factor, nearest-neighbour otherwise."""
    sh, sw = len(image), len(image[0])
    while sh >= 2 * h and sw >= 2 * w and sh % 2 == 0 and sw % 2 == 0:
        image = halve(image, sw // 2, sh // 2)
        sh, sw = sh // 2, sw // 2
    return [[image[y * sh // h][x * sw // w] for x in range(w)] for y in range(h)]


def halve(image, w, h):
    sh, sw = len(image), len(image[0])
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            ys, xs = [min(2 * y, sh - 1), min(2 * y + 1, sh - 1)], [min(2 * x, sw - 1), min(2 * x + 1, sw - 1)]
            p = [image[a][b] for a in ys for b in xs]
            row.append(tuple((sum(c[k] for c in p) + 2) // 4 for k in range(4)))
        out.append(row)
    return out


# --- BC1 / BC3 ---------------------------------------------------------------------------------
def _565(c):
    return (c[0] >> 3) << 11 | (c[1] >> 2) << 5 | c[2] >> 3


def _rgb(v):
    r, g, b = v >> 11 & 31, v >> 5 & 63, v & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


def _palette(c0, c1):
    a, b = _rgb(c0), _rgb(c1)
    if c0 > c1:
        return [a, b, tuple((2 * x + y + 1) // 3 for x, y in zip(a, b)), tuple((x + 2 * y + 1) // 3 for x, y in zip(a, b))]
    return [a, b, tuple((x + y) // 2 for x, y in zip(a, b)), (0, 0, 0)]


def decode_block(blk):
    if len(blk) == 16:
        alpha = _decode_alpha(blk[:8])
        blk = blk[8:]
    else:
        alpha = None
    c0, c1, bits = struct.unpack('<HHI', blk)
    pal = _palette(c0, c1)
    out = []
    for i in range(16):
        k = bits >> 2 * i & 3
        a = alpha[i] if alpha else (0 if c0 <= c1 and k == 3 else 255)
        out.append(pal[k] + (a,))
    return out


def _decode_alpha(blk):
    a0, a1 = blk[0], blk[1]
    bits = int.from_bytes(blk[2:8], 'little')
    if a0 > a1:
        pal = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
    else:
        pal = [a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
    return [pal[bits >> 3 * i & 7] for i in range(16)]


def encode_bc1(px):
    """Colour block: the two ends of the colour box's main diagonal, nearest of 4 colours."""
    lo = [min(p[k] for p in px) for k in range(3)]
    hi = [max(p[k] for p in px) for k in range(3)]
    c0, c1 = _565(hi), _565(lo)
    if c0 == c1:
        return struct.pack('<HHI', c0, c1, 0)
    if c0 < c1:
        c0, c1 = c1, c0
    pal = _palette(c0, c1)
    bits = 0
    for i, p in enumerate(px):
        k = min(range(4), key=lambda j: sum((p[t] - pal[j][t]) ** 2 for t in range(3)))
        bits |= k << 2 * i
    return struct.pack('<HHI', c0, c1, bits)


def encode_bc3(px):
    a = [p[3] for p in px]
    a0, a1 = max(a), min(a)
    if a0 == a1:
        alpha = bytes([a0, a1]) + bytes(6)
    else:
        pal = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
        bits = 0
        for i, v in enumerate(a):
            bits |= min(range(8), key=lambda j: abs(v - pal[j])) << 3 * i
        alpha = bytes([a0, a1]) + bits.to_bytes(6, 'little')
    return alpha + encode_bc1(px)
