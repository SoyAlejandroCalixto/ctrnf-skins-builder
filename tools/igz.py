"""Alchemy IGZ version 10 (PS4) files with any number of sections, read and written back.

    header      u32 magic 0x49475A01, u32 version 10, u32 type hash, u32 platform, u32 fixup count,
                then section descriptors {u32 a, u32 b, u32 offset, u32 length} from 0x10, until offset 0
    section 0   fixups: {char[4] tag, u32 count, u32 length, u32 data start} + data, one after another
    section 1+  objects and memory blocks

A reference stored in the file is (section - 1) << 27 | offset inside that section. The packed
fixups (RVTB, ROFS, RPID, ...) hold such references, so they can point into any section.
Layout taken from kishimisu/Crash-NST-Modding-Tool (src/igz).
"""
import struct

MAGIC = 0x49475A01
STRING_LISTS = ('TSTR', 'TMET', 'EXNM', 'TDEP')
# ROOT and ONAM hold plain u32 lists, not packed ones.
PACKED = ('RVTB', 'ROFS', 'RSTT', 'RPID', 'RHND', 'REXT')


def unpack_offsets(data, count):
    """Nibbles (low first): 3 value bits + a continuation bit. The first value is an offset / 4,
    each next one the distance from the previous / 4."""
    out, prev, i = [], 0, 0
    for _ in range(count):
        v, shift = 0, 0
        while True:
            b = data[i >> 1]
            n = b >> 4 if i & 1 else b & 15
            i += 1
            v |= (n & 7) << shift
            shift += 3
            if not n & 8:
                break
        prev = prev + v * 4 if out else v * 4
        out.append(prev)
    return out


def pack_offsets(offsets):
    nibbles, prev = [], 0
    for k, off in enumerate(offsets):
        delta = (off - prev) // 4 if k else off // 4
        if off % 4 or delta < 0:
            raise ValueError('offsets must be ascending multiples of 4')
        prev = off
        while True:
            n = delta & 7
            delta >>= 3
            nibbles.append(n | (8 if delta else 0))
            if not delta:
                break
    if len(nibbles) % 2:
        nibbles.append(0)
    return bytes(nibbles[i] | nibbles[i + 1] << 4 for i in range(0, len(nibbles), 2))


def read_strings(data, count):
    out, p = [], 0
    for _ in range(count):
        end = data.index(b'\0', p)
        out.append(data[p:end].decode('latin-1'))
        p = end + 1
        if p & 1:
            p += 1
    return out


class Igz:
    def __init__(self, blob):
        self.blob = bytes(blob)
        magic, self.version, self.type_hash, self.platform, count = struct.unpack_from('<5I', blob, 0)
        if magic != MAGIC or self.version != 10:
            raise ValueError('not an IGZ version 10 file')
        self.sections = []  # [a, b, offset, length]
        at = 0x10
        while at + 16 <= 0x800:
            a, b, off, length = struct.unpack_from('<4I', blob, at)
            if off == 0:
                break
            self.sections.append([a, b, off, length])
            at += 16
        self.fixups = []  # [tag, count, start, raw, length]
        p = self.sections[0][2]
        for _ in range(count):
            tag, n, length, start = struct.unpack_from('<4sIII', blob, p)
            self.fixups.append([tag.decode('ascii'), n, start, bytes(blob[p + start:p + length]), length])
            p += length
        self.data = [bytearray(blob[s[2]:s[2] + s[3]]) for s in self.sections[1:]]
        self.strings = self.list('TSTR', read_strings)
        self.types = self.list('TMET', read_strings)
        self.sizes = list(struct.unpack_from(f'<{len(self.types)}I', self.fixup('MTSZ')[3]))
        self.sites = {t: self.list(t, unpack_offsets) for t in PACKED if self.has(t)}

    # --- fixups ------------------------------------------------------------------------------
    def has(self, tag):
        return any(f[0] == tag for f in self.fixups)

    def fixup(self, tag):
        for f in self.fixups:
            if f[0] == tag:
                return f
        raise KeyError(tag)

    def list(self, tag, reader):
        f = self.fixup(tag)
        return reader(f[3], f[1])

    def exid(self):
        """EXID: [(object hash, namespace hash)]."""
        f = self.fixup('EXID')
        return [struct.unpack_from('<II', f[3], 8 * i) for i in range(f[1])]

    def exnm(self):
        """EXNM: [(object name, namespace name)] as strings."""
        if not self.has('EXNM'):
            return []
        f = self.fixup('EXNM')
        out = []
        for i in range(f[1]):
            a, b = struct.unpack_from('<II', f[3], 8 * i)
            out.append((self.strings[a & 0x7FFFFFFF], self.strings[b & 0x7FFFFFFF]))
        return out

    def add_string(self, text):
        """The TSTR index of text (UTF-8), appended to the list when it is not there. Strings are
        NUL-terminated and each starts on an even offset; references to them are indices, so
        appending moves nothing."""
        value = text.encode('utf-8').decode('latin-1')
        if value in self.strings:
            return self.strings.index(value)
        self.strings.append(value)
        raw = bytearray()
        for s in self.strings:
            raw += s.encode('latin-1') + b'\0'
            raw += bytes(len(raw) & 1)
        f = self.fixup('TSTR')
        f[1], f[3] = len(self.strings), bytes(raw)
        f[4] = f[2] + len(raw) + (-(f[2] + len(raw)) % 4)
        return len(self.strings) - 1

    # --- references --------------------------------------------------------------------------
    @staticmethod
    def split(ref):
        return (ref >> 27) & 0x1F, ref & 0x7FFFFFF

    def u32(self, ref, add=0):
        s, o = self.split(ref)
        return struct.unpack_from('<I', self.data[s], o + add)[0]

    def u64(self, ref, add=0):
        s, o = self.split(ref)
        return struct.unpack_from('<Q', self.data[s], o + add)[0]

    def u16(self, ref, add=0):
        s, o = self.split(ref)
        return struct.unpack_from('<H', self.data[s], o + add)[0]

    def f32(self, ref, add=0, n=1):
        s, o = self.split(ref)
        return struct.unpack_from(f'<{n}f', self.data[s], o + add)

    def raw(self, ref, length, add=0):
        s, o = self.split(ref)
        return bytes(self.data[s][o + add:o + add + length])

    def write(self, ref, add, payload):
        s, o = self.split(ref)
        self.data[s][o + add:o + add + len(payload)] = payload

    def memory(self, ref, add):
        """An igMemoryRef field at ref+add: (size, active, data reference)."""
        size = self.u32(ref, add)
        flags = self.u32(ref, add + 4)
        target = self.u64(ref, add + 8)
        return size, bool((flags >> 24) & 1), target

    # --- objects -----------------------------------------------------------------------------
    def objects(self):
        """[(reference, type name)] in file order."""
        return [(r, self.types[self.u64(r)]) for r in self.sites['RVTB']]

    def type_of(self, ref):
        return self.types[self.u64(ref)]

    def names(self):
        """{reference: name} of the root objects (igObjectList + igNameList)."""
        objs = self.objects()
        olist = objs[0][0]
        nlist = next(r for r, t in objs if t == 'igNameList')
        count = self.u32(olist, 0x10)
        _, _, items = self.memory(olist, 0x18)
        _, _, nitems = self.memory(nlist, 0x18)
        out = {}
        for i in range(count):
            out[self.u64(items, 8 * i)] = self.strings[self.u32(nitems, 16 * i)]
        return out

    # --- writing -----------------------------------------------------------------------------
    def build(self):
        """The file again, with section data that may have grown and the edited fixup lists."""
        fixups = bytearray()
        for tag, count, start, raw, length in self.fixups:
            if tag in self.sites:
                count, raw = len(self.sites[tag]), pack_offsets(self.sites[tag])
                new_length = start + len(raw)
                new_length += (-new_length) % 4
            else:
                new_length = length
            block = struct.pack('<4sIII', tag.encode('ascii'), count, new_length, start)
            block += bytes(start - 16) + raw
            block += bytes(new_length - len(block))
            fixups += block
        header = bytearray(self.blob[:0x800])
        sections = [fixups] + self.data
        # Sections follow each other with no padding, as in the game's files.
        offs = []
        pos = 0x800
        for sec in sections:
            offs.append(pos)
            pos += len(sec)
        out = bytearray(pos)
        out[:0x800] = header
        for i, sec in enumerate(sections):
            out[offs[i]:offs[i] + len(sec)] = sec
            struct.pack_into('<II', out, 0x10 + 16 * i + 8, offs[i], len(sec))
        return bytes(out)
