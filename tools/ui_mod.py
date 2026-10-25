"""A driver's name and portrait, for the character mods made with character_mod.py.

    python ui_mod.py names <game archives> <mods folder>/<Mod name> <character>=<Name> ...
        A mod of its own that renames drivers (and their default outfit) in every language. The
        game keeps all the names of a language in one file, looseData/systemData_<lang>.lng, and
        the launcher refuses two enabled mods that change the same file, so the names of every
        character mod go together in this one. Run it again with the full list after adding one.

    python ui_mod.py portrait <character> <game archives> <image.png> <mods folder>/<Mod name>
        Adds the character's portrait (character select icon, 148x148; race HUD: racerportrait,
        128x128; minimap: 64x64) to an existing mod, in every archive that has a copy. The image
        (8-bit RGBA PNG, square, transparent background) goes in as it is: the game's portraits
        are stored upside down, so give it upside down too. Running it again replaces the portrait.

    python ui_mod.py merge <mods folder>/<Pack name> <mod folder> <mod folder> ...
        One mod with every operation of the given mods (which must not change the same entry).

    python ui_mod.py repack <game archives> <mod folder> ...
        Rebuilds the nested archives of mods built before pak.rebuild kept compression (the
        launcher refuses an archive's overlay of 64 MB or more).

<character> is one of character_mod.CHARACTERS.

A .lng file is an IGZ file of igLocalizedStringData objects {+0x10 TSTR index of the text,
+0x18 handle of the object, +0x20 handle of the field}. EXNM lists the object names (namespace
SystemData) and field names (namespace metafield) together; each handle is an index in its own
kind's list. A driver's name is the _displayName/_storeDisplayName of its systemData object and
the _storeDisplayName of its default outfit.
"""
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
import pak  # noqa: E402
import texture  # noqa: E402
from character_mod import CHARACTERS, write_package  # noqa: E402
from igz import Igz  # noqa: E402

FIELDS = ('CRacerBaseData::_displayName', 'CMarketplaceItem::_storeDisplayName')
LANGUAGE = re.compile(r'looseData/systemData_\w+\.lng', re.I)

# name: the systemData objects named after the driver. portrait: the textures' name
# (octane_ui_hud_racerportrait_<portrait>, octane_ui_minimaps_portrait_<portrait>); icon: the
# number of the character select icon (octane_ui_custo_ico_char_racer_<icon>, material Racer_<X>
# of materialinstances/UI/RacerPortraits_materials.igz); archives: those with a copy of any of
# them (the menu archives each carry the icons they show).
MENUS = ['juicedomain_hub.pak', 'juicedomain_onlinemenus.pak', 'juicedomain_race.pak',
         'juicedomain_race_flareday.pak', 'juicedomain_race_flarenight.pak', 'juicedomain_startscreen.pak']
UI = {
    'crash': {'name': ['SystemData_availableDrivers_0', 'Skin_Crash_Default'], 'portrait': 'crash', 'icon': '01',
              'archives': ['drivercrash.pak', 'update.pak'] + MENUS},
    'coco': {'name': ['SystemData_availableDrivers_15', 'Skin_Coco_Default'], 'portrait': 'coco', 'icon': '12',
             'archives': ['drivercoco.pak', 'update.pak'] + MENUS},
    'cortex': {'name': ['SystemData_availableDrivers_2', 'Skin_Cortex_Default'], 'portrait': 'cortex', 'icon': '15',
               'archives': ['drivercortex.pak', 'update.pak'] + MENUS},
    'pura': {'name': ['SystemData_availableDrivers_12', 'Skin_Pura_Default'], 'portrait': 'pura', 'icon': '05',
             'archives': ['driverpura.pak', 'update.pak'] + MENUS},
    # Archives added by updates: entries archives/<name> of update.pak / update2.pak.
    'hunter': {'name': ['DriverHunter', 'DriverHunter_skins_0'], 'portrait': 'hunter', 'icon': '36',
               'archives': ['DriverHunter.pak', 'update2.pak']},
    'tawna': {'name': ['SystemData_availableDrivers_34', 'SystemData_availableDrivers_34_skins_0'],
              'portrait': 'tawna', 'icon': '27',
              'archives': ['DriverTawna.pak', 'update.pak', 'juicedomain_hub.pak', 'juicedomain_onlinemenus.pak',
                           'juicedomain_startscreen.pak']},
    'geary': {'name': ['SystemData_availableDrivers_36', 'SystemData_availableDrivers_36_skins_0'],
              'portrait': 'geary', 'icon': '24', 'archives': ['DriverGeary.pak', 'update.pak'] + MENUS},
    'stew': {'name': ['SystemData_availableDrivers_53', 'SystemData_availableDrivers_53_skins_0'],
             'portrait': 'stew', 'icon': '49', 'archives': ['DriverSTW.pak', 'update2.pak']},
    'ami': {'name': ['SystemData_availableDrivers_20', 'SystemData_availableDrivers_20_skins_0'],
            'portrait': 'ami', 'icon': '28',
            'archives': ['DriverAmi.pak', 'update.pak', 'juicedomain_hub.pak', 'juicedomain_onlinemenus.pak',
                         'juicedomain_startscreen.pak']},
    'isabella': {'name': ['SystemData_availableDrivers_23', 'SystemData_availableDrivers_23_skins_0'],
                 'portrait': 'isabella', 'icon': '29',
                 'archives': ['DriverIsabella.pak', 'update.pak', 'juicedomain_hub.pak', 'juicedomain_onlinemenus.pak',
                              'juicedomain_startscreen.pak']},
    'pasadena': {'name': ['SystemData_availableDrivers_46', 'SystemData_availableDrivers_46_skins_0'],
                 'portrait': 'pasadena', 'icon': '42', 'archives': ['DriverPOM.pak', 'update2.pak']},
    # Two entries: 29 ("Dr. Nitrus Brio") and 43 ("Dr. N. Brio"), the one character select shows.
    'brio': {'name': ['SystemData_availableDrivers_29', 'SystemData_availableDrivers_29_skins_0',
                      'SystemData_availableDrivers_43', 'SystemData_availableDrivers_43_skins_0'],
             'portrait': 'nbrio', 'icon': '40', 'archives': ['DriverNBO.pak', 'update2.pak']},
    'megumi': {'name': ['SystemData_availableDrivers_27', 'SystemData_availableDrivers_27_skins_0'],
               'portrait': 'megumi', 'icon': '30',
               'archives': ['DriverMegumi.pak', 'update.pak', 'juicedomain_hub.pak', 'juicedomain_onlinemenus.pak',
                            'juicedomain_startscreen.pak']},
}
assert set(UI) == set(CHARACTERS)


def rename(blob, names):
    """The .lng again with new texts for {systemData object: text}; returns (bytes, [(object,
    old text, new text)])."""
    z = Igz(blob)
    exnm = z.exnm()
    objects = [n for n, space in exnm if space != 'metafield']
    fields = [n for n, space in exnm if space == 'metafield']
    changes = []
    for ref, kind in z.objects():
        if kind != 'igLocalizedStringData':
            continue
        name = objects[z.u64(ref, 0x18) & 0x7FFFFFFF]
        if name in names and fields[z.u64(ref, 0x20) & 0x7FFFFFFF] in FIELDS:
            old = z.strings[z.u64(ref, 0x10)].encode('latin-1').decode('utf-8')
            z.write(ref, 0x10, struct.pack('<Q', z.add_string(names[name])))
            changes.append((name, old, names[name]))
    return z.build(), changes


def names(archives, mod_folder, *pairs):
    wanted = {}
    for pair in pairs:
        character, text = pair.split('=', 1)
        wanted.update({key: text for key in UI[character]['name']})
    arc, source = pak.open_archive(archives, pak.UPDATES[0])
    files = {}
    for f in arc.files:
        if not LANGUAGE.fullmatch(f['path']):
            continue
        blob, source = pak.effective(archives, f['path'], pak.UPDATES[0])
        data, changes = rename(blob, wanted)
        missing = set(wanted) - {name for name, _, _ in changes}
        if missing:
            raise ValueError(f'{f["path"]}: no name for {sorted(missing)}')
        files[f['path']] = (data, source)
        print(f'  {f["path"]}: ' + ', '.join(sorted({f'{old} -> {new}' for _, old, new in changes})))
    write_package(archives, Path(mod_folder), files, None,
                  'Driver names for the character mods: ' + ', '.join(p.split('=', 1)[1] for p in pairs) + '.')


def area_resize(image, w, h):
    """Each output pixel the alpha-weighted mean of the source area it covers (no dark fringes
    around transparent parts)."""
    sh, sw = len(image), len(image[0])
    out = []
    for y in range(h):
        y0, y1 = y * sh // h, max(y * sh // h + 1, (y + 1) * sh // h)
        row = []
        for x in range(w):
            x0, x1 = x * sw // w, max(x * sw // w + 1, (x + 1) * sw // w)
            px = [image[j][i] for j in range(y0, y1) for i in range(x0, x1)]
            a = sum(p[3] for p in px)
            if a:
                rgb = tuple((sum(p[k] * p[3] for p in px) + a // 2) // a for k in range(3))
            else:
                rgb = (0, 0, 0)
            row.append(rgb + ((a + len(px) // 2) // len(px),))
        out.append(row)
    return out


def portrait(character, archives, png, mod_folder):
    ui = UI[character]
    image = texture.read_png(png)
    pattern = re.compile(r'textures/GuiStandard_diffuse,textures@!ui!Octane!('
                         rf'RacerPortrait!octane_ui_hud_racerportrait_{ui["portrait"]}|'
                         rf'Minimaps!(portraits!)?octane_ui_minimaps_portrait_{ui["portrait"]}|'
                         rf'Customization!Icons!octane_ui_custo_ico_char_racer_{ui["icon"]})`tga,101\.igz', re.I)
    entries = {}  # (archive, entry path) -> new bytes
    for name in ui['archives']:
        arc, source = pak.open_archive(archives, name)
        replaced = {}
        for f in arc.files:
            if pattern.fullmatch(f['path']):
                tex = texture.Texture(arc.extract(f))
                replaced[f['path']] = tex.write(area_resize(image, tex.width, tex.height))
                print(f'  {source}: {f["path"].split("!")[-1]} ({tex.width}x{tex.height})')
        if not replaced:
            raise ValueError(f'{source}: no portrait of {character}')
        if '!' in source:  # an archive nested in an update archive: the whole archive changes
            container, inner = source.split('!', 1)
            entries[(container, inner)] = pak.rebuild(arc, replaced)
        else:
            entries.update({(source, path): data for path, data in replaced.items()})
    add_operations(archives, Path(mod_folder), entries)


def add_operations(archives, folder, entries):
    """Adds archive_asset operations to a mod made by write_package, replacing its operations on
    the same entries, and writes its file list again."""
    import mod_format
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    manifest_path = folder / 'mod.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    keys = {(a.lower(), p.lower()) for a, p in entries}
    operations = [op for op in manifest['operations'] if (op['archive'].lower(), op['asset'].lower()) not in keys]
    for (source, path), data in sorted(entries.items()):
        arc, _ = pak.open_archive(archives, source)
        entry = next(f for f in arc.files if f['path'] == path)
        payload = f'assets/{Path(source).stem}_{entry["index"]}{Path(path).suffix}'
        (folder / payload).write_bytes(data)
        operations.append({'kind': 'archive_asset', 'archive': source, 'asset': path, 'index': entry['index'],
                           'original_sha256': sha(arc.extract(entry)), 'patched_sha256': sha(data),
                           'payload': payload})
    manifest['operations'] = operations
    used = {op['payload'] for op in operations if 'payload' in op}
    manifest['files'] = [{'file': p.relative_to(folder).as_posix(), 'sha256': sha(p.read_bytes()),
                          'bytes': p.stat().st_size} for p in sorted(folder.rglob('*'))
                         if p.is_file() and p != manifest_path
                         and (not p.relative_to(folder).as_posix().startswith('assets/')
                              or p.relative_to(folder).as_posix() in used)]
    stale = [p for p in (folder / 'assets').iterdir() if f'assets/{p.name}' not in used]
    if stale:
        raise ValueError(f'unused payloads in {folder / "assets"}: {[p.name for p in stale]}')
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    mod_format.validate_folder(folder)
    print(f'{folder}: {len(entries)} entries added, {len(operations)} in all.')


def repack(archives, *folders):
    """Rebuilds the nested archives a mod replaces (archive_asset operations whose asset is a
    .pak) with pak.rebuild, which keeps unchanged entries compressed: older builds stored every
    entry uncompressed, and the launcher refuses an archive's overlay of 64 MB or more."""
    import tempfile
    from archive_reader import Archive
    for folder in map(Path, folders):
        manifest = json.loads((folder / 'mod.json').read_text(encoding='utf-8'))
        entries = {}
        for op in manifest['operations']:
            if not op['asset'].lower().endswith('.pak'):
                continue
            original, _ = pak.open_archive(archives, Path(op['asset']).name)
            tmp = Path(tempfile.gettempdir()) / f'repack_{op["index"]}.pak'
            tmp.write_bytes((folder / op['payload']).read_bytes())
            mine = Archive(tmp)
            changed = {f['path']: mine.extract(g) for f, g in zip(original.files, mine.files)
                       if original.extract(f) != mine.extract(g)}
            mine.data.close()
            mine._file.close()
            entries[(op['archive'], op['asset'])] = pak.rebuild(original, changed)
            print(f'  {op["asset"]}: {len(changed)} changed, '
                  f'{(folder / op["payload"]).stat().st_size} -> {len(entries[(op["archive"], op["asset"])])} bytes')
        if entries:
            add_operations(archives, folder, entries)


def merge(target, *sources):
    """One mod with the operations of several (they must not change the same entry)."""
    import shutil
    import mod_format
    target = Path(target)
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    manifests = [json.loads((Path(s) / 'mod.json').read_text(encoding='utf-8')) for s in sources]
    claimed = {}
    for source, m in zip(sources, manifests):
        for op in m['operations']:
            key = (op['archive'].lower(), op['asset'].lower())
            if key in claimed:
                raise ValueError(f'{op["asset"]} is changed by both {claimed[key]} and {source}')
            claimed[key] = source
    if target.exists():
        shutil.rmtree(target)
    (target / 'assets').mkdir(parents=True)
    operations = []
    for source, m in zip(sources, manifests):
        for op in m['operations']:
            if 'payload' in op:
                dest = target / op['payload']
                if dest.exists():
                    raise ValueError(f'two payloads named {op["payload"]}')
                shutil.copyfile(Path(source) / op['payload'], dest)
            operations.append(op)
    (target / mod_format.MARKER).write_bytes(mod_format.MARKER_CONTENT)
    manifest = {
        'schemaVersion': 2,
        'id': ''.join(c if c.isalnum() else '-' for c in target.name.lower()).strip('-')[:80],
        'name': target.name, 'version': '1.0.0', 'author': 'character_import',
        'description': 'Contains: ' + ', '.join(m['name'] for m in manifests) + '.',
        'requiresCapabilities': ['archive-assets'],
        'compatibility': {'online': 'allowed'},
        'operations': operations,
    }
    manifest['files'] = [{'file': p.relative_to(target).as_posix(), 'sha256': sha(p.read_bytes()),
                          'bytes': p.stat().st_size} for p in sorted(target.rglob('*')) if p.is_file()]
    (target / 'mod.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    mod_format.validate_folder(target)
    print(f'{target}: {len(operations)} entries from {len(sources)} mods.')


if __name__ == '__main__':
    if len(sys.argv) >= 5 and sys.argv[1] == 'names':
        names(*sys.argv[2:])
    elif len(sys.argv) >= 4 and sys.argv[1] == 'merge':
        merge(*sys.argv[2:])
    elif len(sys.argv) >= 4 and sys.argv[1] == 'repack':
        repack(*sys.argv[2:])
    elif len(sys.argv) == 6 and sys.argv[1] == 'portrait' and sys.argv[2] in UI:
        portrait(*sys.argv[2:])
    else:
        sys.exit(__doc__)
