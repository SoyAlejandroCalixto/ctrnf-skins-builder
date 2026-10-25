"""Replace a driver's default model with your own.

    python character_mod.py export <character> <game archives> reference.glb
        The character's model and armature, to open in Blender (File > Import > glTF 2.0).

    python character_mod.py info <character> <game archives>
        The vertex count of each level of detail, for blender_fit's "lods" (a driver's files must
        fit the game's memory pool for it: keep each level at most this size).

    python character_mod.py build <character> <game archives> my_model.glb <mods folder>/<Mod name>
                                  [Material=Slot ...] [--texture=Slot=image.png ...] [--flat=normal]
                                  [--flat=composite | --composite=R,G,B] [--flat=emission]
        Your mesh, weighted to that armature and exported from Blender as .glb, as a mod folder
        (OCTR package with mod.json) that replaces every level of detail of the character's
        default outfit. Mods for different characters can be enabled together. Material=Slot sends a glTF material to one of the character's material
        slots; unlisted materials use their own name when it is a slot, otherwise the character's
        main slot. --texture=Slot=image.png gives the slot your colour image (8-bit RGB/RGBA PNG,
        resized to the slot's texture); --flat=normal makes its normal map flat,
        --flat=composite its material map (gloss, metal...) one plain value, --flat=height its
        height map (relief) one plain value and --flat=emission its glow map (*_e) black, so no
        detail of the original character shows.
        --composite=R,G,B flattens the material map to that value instead of the original's
        average (G gloss, B metal: Geary's metal is 0,131,112; a matte body 0,60,0 like Crash).

<character> is one of CHARACTERS; <game archives> is the game's archives folder, e.g.
...\\CUSA13795-1.21\\archives.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gltf  # noqa: E402
import importer  # noqa: E402
import pak  # noqa: E402
import texture  # noqa: E402
from igz import Igz  # noqa: E402
from model import Model  # noqa: E402


def character(model, skins, cutscene, materials, material_archive, slot, lods=range(5), lod_slot=None):
    """model: the LOD paths with {n}; LOD 0 (menus, podium) lives in the cutscene archive. The
    update archives replace some of these files; pak.effective finds the copy the game loads.
    lod_slot: the main slot of the levels of detail that lack `slot`."""
    return {'models': {model.format(n=n): cutscene if n == 0 else skins for n in lods},
            'reference': model.format(n=1), 'materials': materials,
            'material_archive': material_archive, 'slot': slot, 'lod_slot': lod_slot}




CHARACTERS = {
    'crash': character('actors_stripped/Drivers/CrashDriver_LOD_{n}_stripped.igz',
                       'drivercrash_outfit_default_skins.pak', 'drivercrash_outfit_default_cutscene_skins.pak',
                       'materialinstances/Actors/Octane/Characters/CrashDriver_materials.igz',
                       'drivercrash_outfit_default_materials.pak', 'Cloth'),
    'coco': character('actors_stripped/Drivers/DriverCoco_Lod{n}_stripped.igz',
                      'drivercoco_outfit_default_skins.pak', 'drivercoco_outfit_default_cutscene_skins.pak',
                      'materialinstances/Actors/Octane/Characters/CocoDriver_materials.igz',
                      'drivercoco_outfit_default_materials.pak', 'Coco'),
    # Hunter came with an update: his archives are entries of update2.pak.
    'hunter': character('actors_stripped/Drivers/GP3_Driver_HTR_lod{n}_stripped.igz',
                        'DriverHunter_Outfit_Default_Skins.pak', 'DriverHunter_Outfit_Default_Cutscene_Skins.pak',
                        'materialinstances/Actors/Octane/Characters/Hunter_materials.igz',
                        'DriverHunter_Outfit_Default_materials.pak', 'Body'),
    # Tawna's are entries of update.pak, with four levels of detail.
    'tawna': character('actors_stripped/Drivers/Tawna_Lod{n}_stripped.igz',
                       'DriverTawna_Outfit_Default_skins.pak', 'DriverTawna_Outfit_Default_Cutscene_skins.pak',
                       'materialinstances/Actors/Octane/Characters/TawnaDriver_materials.igz',
                       'DriverTawna_Outfit_Default_materials.pak', 'Clothes', lods=range(4)),
    # Geary has no level 2.
    'geary': character('actors_stripped/Drivers/Geary_Lod{n}_stripped.igz',
                       'DriverGeary_Outfit_Default_skins.pak', 'DriverGeary_Outfit_Default_Cutscene_skins.pak',
                       'materialinstances/Actors/Octane/Characters/Geary_materials.igz',
                       'DriverGeary_Outfit_Default_materials.pak', 'Rubber', lods=(0, 1, 3, 4)),
    'cortex': character('actors_stripped/Drivers/DriverCortex_Lod{n}_stripped.igz',
                        'drivercortex_outfit_default_skins.pak', 'drivercortex_outfit_default_cutscene_skins.pak',
                        'materialinstances/Actors/Octane/Characters/CortexDriver_materials.igz',
                        'drivercortex_outfit_default_materials.pak', 'CortexDriver_Body'),
    'pura': character('actors_stripped/Drivers/DriverPura_lod{n}_stripped.igz',
                      'driverpura_outfit_default_skins.pak', 'driverpura_outfit_default_cutscene_skins.pak',
                      'materialinstances/Actors/Octane/Characters/PuraDriver_materials.igz',
                      'driverpura_outfit_default_materials.pak', 'PuraDriver_Body', lods=range(4),
                      lod_slot='PuraDriver_Fur_Lod2'),  # level 3 has no Body (same colour map)
    # Stew (Chick and Stew), internally STW: archives in update2.pak.
    'stew': character('actors_stripped/Drivers/DriverSTW_Lod{n}_stripped.igz',
                      'DriverSTW_Outfit_Default_Skins.pak', 'DriverSTW_Outfit_Default_Cutscene_Skins.pak',
                      'materialinstances/Actors/Octane/Characters/GP6_Driver_STW_materials.igz',
                      'DriverSTW_Outfit_Default_materials.pak', 'Clothes'),
    # Ami (Nitro Squad): archives in update.pak.
    'ami': character('actors_stripped/Drivers/Ami_Lod{n}_stripped.igz',
                     'DriverAmi_Outfit_Default_skins.pak', 'DriverAmi_Outfit_Default_Cutscene_skins.pak',
                     'materialinstances/Actors/Octane/Characters/Ami_materials.igz',
                     'DriverAmi_Outfit_Default_materials.pak', 'Outfit'),
    # Megumi (Nitro Squad): archives in update.pak.
    'megumi': character('actors_stripped/Drivers/Megumi_Lod{n}_stripped.igz',
                        'DriverMegumi_Outfit_Default_skins.pak', 'DriverMegumi_Outfit_Default_Cutscene_skins.pak',
                        'materialinstances/Actors/Octane/Characters/Megumi_materials.igz',
                        'DriverMegumi_Outfit_Default_materials.pak', 'Outfit'),
    # Isabella (Nitro Squad): archives in update.pak; Boots shares the Outfit image.
    'isabella': character('actors_stripped/Drivers/Isabella_Lod{n}_stripped.igz',
                          'DriverIsabella_Outfit_Default_skins.pak', 'DriverIsabella_Outfit_Default_Cutscene_skins.pak',
                          'materialinstances/Actors/Octane/Characters/Isabella_materials.igz',
                          'DriverIsabella_Outfit_Default_materials.pak', 'Outfit'),
    # Pasadena O'Possum, internally POM: archives in update2.pak.
    'pasadena': character('actors_stripped/Drivers/DriverPOM_Lod{n}_stripped.igz',
                          'DriverPOM_Outfit_Default_Skins.pak', 'DriverPOM_Outfit_Default_Cutscene_Skins.pak',
                          'materialinstances/Actors/Octane/Characters/GP5_Driver_POM_materials.igz',
                          'DriverPOM_Outfit_Default_materials.pak', 'UpperBody'),
    # Nitrus Brio: models are DriverNBO, materials DriverNBrio; archives in update2.pak.
    'brio': character('actors_stripped/Drivers/DriverNBO_lod{n}_stripped.igz',
                      'DriverNBO_Outfit_Default_Skins.pak', 'DriverNBO_Outfit_Default_Cutscene_Skins.pak',
                      'materialinstances/NBrio_materials.igz',
                      'DriverNBrio_Outfit_Default_materials.pak', 'NBrio'),
}


def export(name, archives, target):
    c = CHARACTERS[name]
    blob, source = pak.effective(archives, c['reference'], c['models'][c['reference']])
    Path(target).write_bytes(gltf.export(Model(blob), name))
    print(f'{target}: {name} (LOD 1 from {source})')


def info(name, archives):
    """Vertex count of each level of detail: the targets for fit.json "lods"."""
    c = CHARACTERS[name]
    counts = []
    for path, archive in c['models'].items():
        model = Model(pak.effective(archives, path, archive)[0])
        counts.append(sum(model.z.u32(dc['vb'], 0x0c) for dc in model.draw_calls))
    print(f'{name}: "lods": {counts}')


def material_images(blob):
    """Material name -> the images it uses, following the material's objects to their texture
    handles (RHND entries naming an EXNM 'image')."""
    z = Igz(blob)
    starts = sorted(r for r, _ in z.objects())
    names = z.exnm()

    def span(r):
        i = starts.index(r)
        end = starts[i + 1] if i + 1 < len(starts) and starts[i + 1] >> 27 == r >> 27 else \
            (r & ~0x7FFFFFF) | len(z.data[r >> 27])
        return r, end

    def owner(ref):
        for s in starts:
            a, e = span(s)
            if a <= ref < e:
                return s
        return None

    out = {}
    for root, name in z.names().items():
        if z.type_of(root) != 'igGraphicsMaterial':
            continue
        todo, seen = [root], set()
        while todo:
            obj = todo.pop()
            if obj in seen:
                continue
            seen.add(obj)
            a, e = span(obj)
            for s in z.sites['ROFS']:
                if a <= s < e:
                    t = owner(z.u64(s))
                    if t is not None:
                        todo.append(t)
        images = set()
        for obj in seen:
            a, e = span(obj)
            for s in z.sites.get('RHND', []):
                h = z.u32(s) if a <= s < e else 0
                if h & 0x80000000 and names[h & 0x7FFFFFFF][0] == 'image':
                    images.add(names[h & 0x7FFFFFFF][1])
        out[name] = sorted(images)
    return out


def textures(c, archives, slot, png, flatten=(), composite=None):
    """Replacement texture files for a slot (see the module notes): {path: (bytes, archive the
    game loads it from)}. composite: (r, g, b) for the flat material map, else its average."""
    blob, _ = pak.effective(archives, c['materials'], c['material_archive'])
    files = {}
    for name in material_images(blob)[slot]:
        if '!default' in name or '!Common!' in name:
            continue  # engine defaults and textures other characters share
        path = f'textures/{name}.igz'
        blob, source = pak.effective(archives, path, c['material_archive'])
        tex = texture.Texture(blob)
        if name.startswith('ColorMap,'):
            files[path] = (tex.write(texture.resize(texture.read_png(png), tex.width, tex.height)), source)
        elif name.startswith('NormalMap') and tex.block == 16 and 'normal' in flatten:
            files[path] = (tex.fill(texture.flat_normal_bc5()), source)
        elif name.startswith('Composite') and tex.block == 8 and 'composite' in flatten:
            value = tuple(composite) + (255,) if composite else tex.average()
            files[path] = (tex.fill(texture.encode_bc1((value,) * 16)), source)
        elif name.startswith('HeightMap') and tex.block == 8 and 'height' in flatten:
            files[path] = (tex.fill(texture.encode_bc1((tex.average(),) * 16)), source)  # no relief
        elif name.startswith('ColorMapHalfRes') and '_e`' in name.lower() and tex.block == 8 \
                and 'emission' in flatten:
            files[path] = (tex.fill(texture.encode_bc1(((0, 0, 0, 255),) * 16)), source)  # no glow
        print(f'  {name}: {"replaced" if path in files else "kept"}')
    return files


def build(name, archives, source_glb, mod_folder, *args):
    c = CHARACTERS[name]
    slots = dict(a.split('=', 1) for a in args if not a.startswith('--'))
    images = dict(a[len('--texture='):].split('=', 1) for a in args if a.startswith('--texture='))
    flatten = [a[len('--flat='):] for a in args if a.startswith('--flat=')]
    composite = next((tuple(int(x) for x in a[len('--composite='):].split(','))
                      for a in args if a.startswith('--composite=')), None)
    if composite:
        flatten.append('composite')
    prims, hierarchy = importer.read_scene(Path(source_glb).read_bytes())
    print(f'{source_glb}: {len(prims)} parts, {sum(len(p["positions"]) for p in prims)} vertices, '
          f'{sum(len(p["indices"]) for p in prims) // 3} triangles')
    files = {}
    for n, (path, archive) in enumerate(c['models'].items()):
        blob, source = pak.effective(archives, path, archive)
        model = Model(blob)
        # A reduced mesh for this level of detail (blender_fit "lods"), when there is one.
        lod = Path(source_glb).with_name(f'{Path(source_glb).stem}_lod{n}.glb')
        lod_prims, lod_hierarchy = importer.read_scene(lod.read_bytes()) if lod.exists() else (prims, hierarchy)
        main = c['slot'] if c['slot'] in model.materials or not c['lod_slot'] else c['lod_slot']
        calls = importer.build_calls(model, lod_prims, lod_hierarchy, slots, main)
        game_vertices = sum(model.z.u32(dc['vb'], 0x0c) for dc in model.draw_calls)
        files[path] = (model.replace(calls), source)
        vertices = sum(len(call["vertices"]) for call in calls)
        print(f'  {Path(path).stem}: {len(calls)} draw calls, {vertices} vertices, {len(files[path][0])} bytes '
              f'(the game\'s: {game_vertices} vertices, {len(blob)} bytes)')
        # More than the game's overflows the driver's memory pool: the game stops when it shows it.
        if vertices > game_vertices or len(files[path][0]) > len(blob):
            sys.exit(f'{Path(path).stem} is bigger than the game\'s: reduce it ("lods" in fit.json; '
                     f'{lod.name} {"exists" if lod.exists() else "is missing"}). Nothing was written.')
    for slot, png in images.items():
        files.update(textures(c, archives, slot, png, flatten, composite))
    write_package(archives, Path(mod_folder), files, name)


def write_package(archives, folder, files, name, description=None):
    """An OCTR format 2 package (scripts/mod_format.py): one archive_asset operation per changed
    entry, in the archive the game loads it from. The launcher merges such entries from every
    enabled mod, so mods for different characters work together; a whole update3.pak would not.
    A file in an archive nested in an update archive (source '<update>!<nested>') changes the
    nested archive, rebuilt with its new files, as one entry of the update archive."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
    import hashlib
    import json
    import shutil
    import mod_format
    if folder.exists():
        shutil.rmtree(folder)
    (folder / 'assets').mkdir(parents=True)
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    entries = {}  # (archive, entry path) -> new bytes
    nested = {}
    for path, (data, source) in files.items():
        if '!' in source:
            nested.setdefault(source, {})[path] = data
        else:
            entries[(source, path)] = data
    for source, replaced in nested.items():
        container, inner = source.split('!', 1)
        arc, _ = pak.open_archive(archives, Path(inner).name)
        entries[(container, inner)] = pak.rebuild(arc, replaced)
    operations = []
    for (source, path), data in sorted(entries.items()):
        arc, _ = pak.open_archive(archives, source)
        entry = next(f for f in arc.files if f['path'] == path)
        payload = f'assets/{Path(source).stem}_{entry["index"]}{Path(path).suffix}'
        (folder / payload).write_bytes(data)
        operations.append({'kind': 'archive_asset', 'archive': source, 'asset': path, 'index': entry['index'],
                           'original_sha256': sha(arc.extract(entry)), 'patched_sha256': sha(data),
                           'payload': payload})
    (folder / mod_format.MARKER).write_bytes(mod_format.MARKER_CONTENT)
    manifest = {
        'schemaVersion': 2,
        'id': ''.join(c if c.isalnum() else '-' for c in folder.name.lower()).strip('-')[:80],
        'name': folder.name, 'version': '1.0.0', 'author': 'character_import',
        'description': description or f'Replaces the default outfit of {name} with a custom model.',
        'requiresCapabilities': ['archive-assets'],
        'compatibility': {'online': 'allowed'},
        'operations': operations,
    }
    manifest['files'] = [{'file': p.relative_to(folder).as_posix(), 'sha256': sha(p.read_bytes()),
                          'bytes': p.stat().st_size} for p in sorted(folder.rglob('*')) if p.is_file()]
    (folder / 'mod.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    mod_format.validate_folder(folder)
    print(f'{folder}: {len(operations)} entries replaced. Enable "{folder.name}" in the launcher\'s Mods page.')


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] not in ('export', 'build', 'info') or sys.argv[2] not in CHARACTERS:
        sys.exit(__doc__)
    {'export': export, 'build': build, 'info': info}[sys.argv[1]](*sys.argv[2:])
