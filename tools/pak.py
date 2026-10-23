"""PAK (IGA archive version 13) files: write new archives and find the copy of a resource the
game actually loads.

    header      u32 magic 0x1A414749, u32 version 13, u32 (count * 20 in new files), u32 count,
                u32 sector size, u32 hash divider, u32 hash slop, u32 large/medium/small block
                counts, u64 names offset (40), u32 names size (48), u32 1 (52)
    56          count u32 path hashes (sorted), then count entries
                {u32 offset, u32 ordinal (index << 8 | offset bits 32-39), u32 size, u32 compression},
                then the block tables of compressed entries
    names       count u32 offsets from the names start, then per entry the full build path and the
                game path, NUL-terminated

A path hash is FNV-1a 32 of the lower-cased game path. The game reads update.pak, update2.pak and
update3.pak before the other archives, so a resource in update3.pak replaces every other copy;
community mods ship as update3.pak for that reason, though only one enabled mod can provide it. Layout and the hash search parameters follow
kishimisu/Crash-NST-Modding-Tool (src/pak).
"""
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
from archive_reader import Archive  # noqa: E402

SECTOR = 0x800
BUILD_PREFIX = 'temporary/octane/data/ps4/output/'
UPDATES = ('update2.pak', 'update.pak')  # newest first


def path_hash(path):
    h = 0x811C9DC5
    for c in path.lower().encode('latin-1'):
        h = ((h ^ c) * 0x01000193) & 0xFFFFFFFF
    return h


def _search(hashes, divider, slop, wanted):
    """The game's lookup of a hash in the sorted list (kishimisu's hash_search)."""
    divided = wanted // divider
    start = (divided - slop) & 0xFFFFFFFF if slop < divided else 0
    end = min(len(hashes), divided + slop + 1)
    index, span = start, (end - start) & 0xFFFFFFFF
    i = span
    while i > 0:
        i = span // 2
        if hashes[index + i] < wanted:
            index += i + 1
            i = (span - 1 - i) & 0xFFFFFFFF
        span = i
    return index < len(hashes) and hashes[index] == wanted


def create(target, files):
    """A new archive holding files {game path: bytes}, uncompressed."""
    items = sorted(((path_hash(p), p, data) for p, data in files.items()))
    hashes = [h for h, _, _ in items]
    if len(set(hashes)) != len(hashes):
        raise ValueError('two paths with the same hash')
    count = len(items)
    divider = 0xFFFFFFFF // count
    slop = next(s for s in range(count + 1) if all(_search(hashes, divider, s, h) for h in hashes))
    out = bytearray(56 + count * 20)
    struct.pack_into('<7I', out, 0, 0x1A414749, 13, count * 20, count, SECTOR, divider, slop)
    struct.pack_into(f'<{count}I', out, 56, *hashes)
    out += bytes((-len(out)) % SECTOR)
    for i, (_, path, data) in enumerate(items):
        offset = len(out)
        out += data
        out += bytes((-len(out)) % SECTOR)
        struct.pack_into('<4I', out, 56 + count * 4 + 16 * i,
                         offset & 0xFFFFFFFF, i << 8 | offset >> 32, len(data), 0xFFFFFFFF)
    names = bytearray(4 * count)
    for i, (_, path, _) in enumerate(items):
        struct.pack_into('<I', names, 4 * i, len(names))
        names += (BUILD_PREFIX + path).encode('latin-1') + b'\0' + path.encode('latin-1') + bytes(5)
    struct.pack_into('<QII', out, 40, len(out), len(names), 1)
    out += names
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_bytes(out)
    check = Archive(target)
    for f in check.files:
        if check.extract(f) != files[f['path']]:
            raise RuntimeError(f'{target}: entry {f["path"]} did not read back')


def _span(arc, f):
    """Bytes from a compressed entry's offset to the end of its last block. Block positions in
    the block tables are sectors from the entry's offset, so the span moves as one piece."""
    table, shift = ((arc.tables[2], 7) if f['size'] <= 127 * arc.sector else
                    (arc.tables[1], 15) if f['size'] <= 32767 * arc.sector else (arc.tables[0], 31))
    end = 0
    for i in range((f['size'] + 32767) // 32768):
        entry = table[(f['compression'] & 0xFFFFFFF) + i]
        p = (entry & ((1 << shift) - 1)) * arc.sector
        if entry >> shift:  # u32 length, then (LZMA) 5 bytes of properties, then the data
            n = 4 + int.from_bytes(arc.data[f['offset'] + p:f['offset'] + p + 4], 'little')
            n += 5 if f['compression'] >> 28 == 2 else 0
        else:
            n = min(32768, f['size'] - i * 32768)
        end = max(end, p + n)
    return end


def rebuild(arc, replacements):
    """The archive arc again with some entries' bytes replaced ({game path: bytes}). It keeps the
    hashes, entry order, names and block tables; replaced entries are stored uncompressed, the
    others as they were (compressed ones keep their blocks), each on a sector boundary."""
    b = arc.data
    count = len(arc.files)
    names_off = struct.unpack_from('<Q', b, 40)[0]
    names_size = struct.unpack_from('<I', b, 48)[0]
    tables_end = 56 + count * 20 + sum(len(t) * s for t, s in zip(arc.tables, (4, 2, 1)))
    out = bytearray(b[:56]) + bytes(b[56:56 + count * 4]) + bytes(count * 16) + bytes(b[56 + count * 20:tables_end])
    out += bytes((-len(out)) % arc.sector)
    for f in arc.files:
        payload = replacements.get(f['path'])
        if payload is not None:
            stored, size, compression = payload, len(payload), 0xFFFFFFFF
        elif f['compression'] == 0xFFFFFFFF:
            stored, size, compression = b[f['offset']:f['offset'] + f['size']], f['size'], 0xFFFFFFFF
        else:
            stored, size, compression = b[f['offset']:f['offset'] + _span(arc, f)], f['size'], f['compression']
        offset = len(out)
        out += stored
        out += bytes((-len(out)) % arc.sector)
        struct.pack_into('<4I', out, 56 + count * 4 + 16 * f['index'],
                         offset & 0xFFFFFFFF, (f['ordinal'] & ~0xFF) | offset >> 32, size, compression)
    struct.pack_into('<Q', out, 40, len(out))
    out += b[names_off:names_off + names_size]
    return bytes(out)


def open_archive(archives, name):
    """(Archive, source) for a game archive. Archives added by updates (Hunter's, for example)
    are entries archives/<name> of an update archive: they are read from a temporary copy and
    their source is '<update>!<entry path>'."""
    archives = Path(archives)
    if (archives / name).exists():
        return Archive(archives / name), name
    for update in UPDATES:
        arc = Archive(archives / update)
        for f in arc.files:
            if f['path'].lower() == f'archives/{name}'.lower():
                tmp = Path(tempfile.gettempdir()) / f'character_import_{update}_{f["index"]}.pak'
                data = arc.extract(f)
                if not tmp.exists() or tmp.stat().st_size != len(data):
                    tmp.write_bytes(data)
                return Archive(tmp), f'{update}!{f["path"]}'
    raise KeyError(f'archive {name} not found')


def effective(archives, path, archive):
    """The bytes the game loads for path, normally in archive: an update archive's copy wins.
    Returns (bytes, source) where source is an archive name or '<update>!<nested archive>'."""
    for name in UPDATES + (archive,):
        arc, source = open_archive(archives, name)
        for f in arc.files:
            if f['path'].lower() == path.lower():
                return arc.extract(f), source
    raise KeyError(f'{path} is in neither the updates nor {archive}')
