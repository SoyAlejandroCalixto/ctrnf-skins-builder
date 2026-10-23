"""Blender script: fit a rigged model onto a game character's armature.

    blender -b --factory-startup --python blender_fit.py -- reference.glb fit.json out.glb [renders/]

reference.glb comes from `character_mod.py export`. fit.json:
    {"model": "mario.fbx",                       # .fbx or .glb with its own armature
     "keep": ["mario_body", ...],                # mesh objects to use (default: all)
     "drop_objects": ["..."],                    # optional: mesh objects to leave out
     "weld": 0.00001,                            # optional: join coincident vertices
     "flip_winding": true,                       # optional with weld: turn every triangle over
     "double_sided": ["..."],                    # optional: mesh objects drawn from both sides
     "caps": [{"bone": "head", "center": [x, y, z],  # optional: plain ellipses (model space,
               "size": [rx, rz], "color": [0, 0, 0]}],  # across Y) closing see-through openings;
                                                 # "axis": "z" lies flat, "size" then [rx, ry];
                                                 # "outline": [[x, z or y], ...] a convex polygon
                                                 # instead (center then only gives the plane);
                                                 # "weights_from": ["mesh", ...] in place of
                                                 # "bone": weights of the nearest vertex
     "attach": {"pack": "spine_05"},             # optional: parent bones of a separate armature
     "by_position": ["dfrm_"],                   # optional: bones (by name prefix) that take
                                                 # the part nearest to them
     "decals": [{"object", "image", "crop",      # optional: paint images (a face) onto a mesh's
                 "center", "size"}],             # texture, projected from the front
     "rig": {"joints": {"name": [x, y, z]},      # optional, for a model with no armature: joints
             "bones": [[bone, head joint, tail joint or null, parent or null], ...]},
     "cut_below": 0.165,                         # optional with "rig": cut away a stand
     "rebake": 2048,                             # optional with "rig": new UVs + baked image
     "lods": [23648, 10546, ...],                # optional: the game's vertex count per level
                                                 # (character_mod.py info); bigger models get
                                                 # reduced copies out_lod<n>.glb
     "rotate_z": 90,                             # degrees turning the model to face +X
     "radial_scale": 0.0115,                     # thickness scale of stretched parts (a
                                                 # segment's own "radial" overrides it)
     "segments": {                               # model bone -> how its part is placed
        "left_upperarm": {"bone": "Bone_L_UpperArm",
                          "from": ["left_upperarm", "left_forearm"],   # model joints (bone heads)
                          "to": ["Bone_L_UpperArm", "Bone_L_Forearm"]},# game joints (bone heads)
        "left_hand": {"bone": "Bone_L_Hand", "rigid": 0.012,
                      "from": ["left_hand"], "to": ["Bone_L_Hand"]},   # rigid: anchor + scale
        ...},
     "bones": {"model bone": "game bone", ...},  # optional: weight target of a model bone that
                                                 # takes its placement from an ancestor segment
     "texture_dirs": ["..."],                    # optional: where to find missing images
     "drop_materials": ["rense"],                # optional: faces to delete
     "drop_groups": ["Eyelid"],                  # optional: faces weighted (> 0.5) to bones
                                                 # with these name prefixes (closed eyelids)
     "images": {"material": "colour.png"},       # optional: image of a material that links none
     "base_colors": {"material": [r, g, b]},     # optional: colour (sRGB) under a material's
                                                 # image where it is transparent (pupils)
     "atlas": {"slot": "Cloth", "size": 1024}}   # optional: bake the materials into one image

A segment's "offset": [x, y, z] moves its part in the game's bind space (game units).
A stretched part maps the model's joint-to-joint segment onto the game's: along the segment it
takes the game's length, across it radial_scale. A rigid part keeps its shape (scaled), its
anchor joint put on the game's, turned by rotate_z (or to follow "align": [game joint a, b], the
model's direction being "align_from": [model joint a, b]; with "roll_from" / "roll", also
turned about that direction so a second model direction, e.g. index to pinky, follows the game's).

A model bone not in "segments" uses the segment of its nearest listed ancestor. Each vertex is
placed by the weighted blend of its bones' placements (rigid models: one bone, one placement) and
keeps its weights, moved to the game bones ("bones" entry, else that of the nearest ancestor with
one, else the segment's "bone").

The atlas packs every material (its image, laid over its base colour, or a plain colour cell)
at its own size, saved beside out.glb as out.png, for `character_mod.py build ... --texture=Slot=out.png`.
Renders (optional) show the result over the game character from 3 sides.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index('--') + 1:]
ref_path, fit_path, out_path = args[:3]
out_path = str(Path(out_path).resolve())  # Blender saves images relative to the drive root
render_dir = Path(args[3]).resolve() if len(args) > 3 else None
fit = json.loads(Path(fit_path).read_text())
model_path = Path(fit['model'])
if not model_path.is_absolute():
    model_path = Path(fit_path).parent / model_path

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=ref_path)
game_arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
game_mesh = next(o for o in bpy.data.objects if o.type == 'MESH' and o.parent == game_arm)
for o in list(bpy.data.objects):
    if o.type == 'MESH' and o.parent is None:
        bpy.data.objects.remove(o)  # bone display shapes the importer adds
game_joint = {b.name: game_arm.matrix_world @ b.head_local for b in game_arm.data.bones}

before = set(bpy.data.objects)
if model_path.suffix.lower() == '.fbx':
    bpy.ops.import_scene.fbx(filepath=str(model_path))
else:
    bpy.ops.import_scene.gltf(filepath=str(model_path))
imported = set(bpy.data.objects) - before


def find_image(image):
    if image.packed_file or Path(bpy.path.abspath(image.filepath)).is_file():
        return image
    name = Path(image.filepath.replace('\\', '/')).name
    for d in fit.get('texture_dirs', []):
        for candidate in (Path(d) / name, Path(d) / name.replace('_1.', '.')):
            if candidate.exists():
                return bpy.data.images.load(str(candidate))
    sys.exit(f'image {image.filepath} not found; add its folder to texture_dirs')


def rebake(o, size):
    """A new UV layout of large islands (Smart UV Project) with the material's image baked onto
    it (Cycles). Scans come with UVs cut into hundreds of slivers, which reduced levels of detail
    cannot keep apart."""
    old = o.data.uv_layers.active.name  # layer references go stale when layers are added
    o.data.uv_layers.new(name='rebaked')
    o.data.uv_layers.active = o.data.uv_layers['rebaked']
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
    bpy.ops.object.mode_set(mode='OBJECT')
    image = bpy.data.images.new('rebaked', size, size)
    for mat in o.data.materials:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        tex = next(n for n in nodes if n.type == 'TEX_IMAGE' and n.image)
        tex.image = find_image(tex.image)
        coord = nodes.new('ShaderNodeUVMap')
        coord.uv_map = old
        links.new(coord.outputs['UV'], tex.inputs['Vector'])
        emit = nodes.new('ShaderNodeEmission')
        links.new(tex.outputs['Color'], emit.inputs['Color'])
        out = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
        links.new(emit.outputs['Emission'], out.inputs['Surface'])
        target = nodes.new('ShaderNodeTexImage')
        target.image = image
        nodes.active = target
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 1
    scene.render.bake.margin = 16
    bpy.ops.object.bake(type='EMIT')
    for mat in o.data.materials:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
        out = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        for n in [n for n in nodes if n.type in ('TEX_IMAGE', 'UV_MAP', 'EMISSION')]:
            nodes.remove(n)
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = image
        tex.extension = 'EXTEND'
        links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    image.filepath_raw = str(Path(out_path).with_name(Path(out_path).stem + '_rebaked.png'))
    image.file_format = 'PNG'
    image.save()
    o.data.uv_layers.remove(o.data.uv_layers[old])


def prepare_unrigged(objects):
    """For a model without a skeleton (a scan, say): cut away what lies below cut_below (a
    stand) and give it the armature described by "rig" with Blender's automatic weights.
    Returns the new armature."""
    import bmesh
    rig = fit['rig']
    meshes_ = [o for o in objects if o.type == 'MESH']
    for o in meshes_:
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
        if 'cut_below' in fit:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, fit['cut_below']), plane_no=(0, 0, 1),
                                   clear_inner=True)
            # Close the cut (the soles) so the mesh stays solid for the weighting.
            edges = [e for e in bm.edges if e.is_boundary]
            bmesh.ops.holes_fill(bm, edges=edges, sides=0)
            bm.to_mesh(o.data)
            bm.free()
        if 'rebake' in fit:
            rebake(o, fit['rebake'])
    arm_data = bpy.data.armatures.new('rig')
    arm = bpy.data.objects.new('rig', arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    joints = {k: Vector(v) for k, v in rig['joints'].items()}
    for name, head, tail, parent in rig['bones']:
        b = arm_data.edit_bones.new(name)
        b.head = joints[head]
        b.tail = joints[tail] if tail else joints[head] + Vector((0, 0, 0.02))
        b.use_deform = bool(tail)
        if parent:
            b.parent = arm_data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in meshes_:
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        # Bone heat can fail on scans; a vertex left without weights follows its nearest bone.
        deform = [b for b in arm_data.bones if b.use_deform]
        groups = {g.name: g for g in o.vertex_groups}
        for v in o.data.vertices:
            if any(g.weight > 0 for g in v.groups):
                continue
            def dist(b):
                a, c = b.head_local, b.tail_local
                t = max(0.0, min(1.0, (v.co - a).dot(c - a) / max((c - a).length_squared, 1e-12)))
                return (v.co - (a + t * (c - a))).length
            best = min(deform, key=dist)
            groups.setdefault(best.name, o.vertex_groups.get(best.name) or o.vertex_groups.new(name=best.name))
            groups[best.name].add([v.index], 1.0, 'REPLACE')
    return arm


def paint_decal(obj, decal):
    """Paint part of an image onto obj's texture where obj faces the front (-Y): a face
    drawn on a blank head (eyes, mouth). decal: {"image", "crop": [x0, y0, x1, y1] pixels of the
    image (top-left origin), "center": [x, z] and "size": [width, height] on the model, in
    metres}. The painted pixels are those the object's own UV triangles cover."""
    import numpy as np
    mat = obj.data.materials[0]
    tex = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
    target = find_image(tex.image)
    tw, th = target.size
    pixels = np.array(target.pixels[:], dtype=np.float32).reshape(th, tw, 4)
    src = bpy.data.images.load(decal['image'])
    sw, sh = src.size
    spx = np.array(src.pixels[:], dtype=np.float32).reshape(sh, sw, src.channels)
    x0, y0, x1, y1 = decal['crop']
    cx, cz = decal['center']
    w, h = decal['size']
    world = obj.matrix_world
    uv = obj.data.uv_layers.active.data
    obj.data.calc_loop_triangles()
    for tri in obj.data.loop_triangles:
        if (world.to_3x3() @ tri.normal).y > -0.2:
            continue  # faces not looking forward
        pts = [world @ obj.data.vertices[v].co for v in tri.vertices]
        uvs = np.array([uv[l].uv[:] for l in tri.loops])
        uvs = (uvs - np.floor(uvs.mean(0))) * (tw, th) - 0.5  # repeating textures: tile 0
        lo, hi = np.floor(uvs.min(0)).astype(int), np.ceil(uvs.max(0)).astype(int)
        gx, gy = np.meshgrid(np.arange(max(lo[0], 0), min(hi[0], tw - 1) + 1),
                             np.arange(max(lo[1], 0), min(hi[1], th - 1) + 1))
        (ax, ay), (bx, by), (qx, qy) = uvs
        det = (by - qy) * (ax - qx) + (qx - bx) * (ay - qy)
        if abs(det) < 1e-12 or gx.size == 0:
            continue
        l1 = ((by - qy) * (gx - qx) + (qx - bx) * (gy - qy)) / det
        l2 = ((qy - ay) * (gx - qx) + (ax - qx) * (gy - qy)) / det
        l3 = 1 - l1 - l2
        inside = (l1 >= -0.01) & (l2 >= -0.01) & (l3 >= -0.01)
        px = l1 * pts[0].x + l2 * pts[1].x + l3 * pts[2].x
        pz = l1 * pts[0].z + l2 * pts[1].z + l3 * pts[2].z
        # Position in the decal: 0..1 across, 0..1 up; the crop's rows run top-down.
        u = (px - (cx - w / 2)) / w
        v = (pz - (cz - h / 2)) / h
        inside &= (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
        if not inside.any():
            continue
        # Bilinear sample of the crop (its rows run top-down; Blender's rows bottom first).
        fx = np.clip(x0 + u[inside] * (x1 - x0) - 0.5, 0, sw - 1)
        fy = np.clip(sh - 1 - (y0 + (1 - v[inside]) * (y1 - y0) - 0.5), 0, sh - 1)
        ax, ay = np.floor(fx).astype(int), np.floor(fy).astype(int)
        bx, by_ = np.minimum(ax + 1, sw - 1), np.minimum(ay + 1, sh - 1)
        wx, wy = (fx - ax)[:, None], (fy - ay)[:, None]
        colour = (spx[ay, ax] * (1 - wx) * (1 - wy) + spx[ay, bx] * wx * (1 - wy)
                  + spx[by_, ax] * (1 - wx) * wy + spx[by_, bx] * wx * wy)
        alpha = colour[:, 3:4] if src.channels == 4 else np.ones((len(sx), 1))
        rows, cols = gy[inside], gx[inside]
        pixels[rows, cols, :3] = colour[:, :3] * alpha + pixels[rows, cols, :3] * (1 - alpha)
    painted = bpy.data.images.new(target.name + '_decal', tw, th, alpha=True)
    painted.pixels = pixels.ravel().tolist()
    painted.pack()
    tex.image = painted


for decal in fit.get('decals', []):
    paint_decal(bpy.data.objects[decal['object']], decal)


def add_cap(i, cap):
    """A plain-coloured ellipse across the model's Y (or "axis": "z") axis, weighted to one bone.
    One side here; it is made two-sided after welding (which would merge the two)."""
    cx, cy, cz = cap['center']
    if 'outline' in cap:
        outline = [(u - cx, v - (cy if cap.get('axis') == 'z' else cz)) for u, v in cap['outline']]
    else:
        r1, r2 = cap['size']
        outline = [(r1 * math.cos(a), r2 * math.sin(a)) for a in (2 * math.pi * k / 48 for k in range(48))]
    if cap.get('axis', 'y') == 'z':
        ring = [(cx + u, cy + v, cz) for u, v in outline]
    else:
        ring = [(cx + u, cy, cz + v) for u, v in outline]
    n = len(ring)
    verts = [tuple(sum(c) / n for c in zip(*ring))] + ring
    faces = [(0, 1 + k, 1 + (k + 1) % n) for k in range(n)]
    me = bpy.data.meshes.new(f'Cap{i}')
    me.from_pydata(verts, [], faces)
    me.uv_layers.new(name='UVMap')
    mat = bpy.data.materials.new(f'Cap{i}')
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                                                for c in cap.get('color', [0, 0, 0])] + [1]
    me.materials.append(mat)
    o = bpy.data.objects.new(f'Cap{i}', me)
    bpy.context.scene.collection.objects.link(o)
    if 'weights_from' not in cap:
        o.vertex_groups.new(name=cap['bone']).add(range(len(verts)), 1.0, 'REPLACE')
        return o
    # Each vertex takes the weights of the nearest vertex of the listed meshes, so the plate moves
    # with what it closes (a single bone lets it slide off a face weighted to the neck).
    from mathutils.kdtree import KDTree
    source = [(s, s.matrix_world @ v.co, v) for s in map(bpy.data.objects.get, cap['weights_from'])
              for v in s.data.vertices]
    kd = KDTree(len(source))
    for k, (_, co, _) in enumerate(source):
        kd.insert(co, k)
    kd.balance()
    for vi, co in enumerate(verts):
        s, _, v = source[kd.find(co)[1]]
        for g in v.groups:
            name = s.vertex_groups[g.group].name
            group = o.vertex_groups.get(name) or o.vertex_groups.new(name=name)
            group.add([vi], g.weight, 'REPLACE')
    return o


# Plates that close openings seen through in the game (behind a face sunk in a hood).
two_sided = set(fit.get('double_sided', []))
for i, cap in enumerate(fit.get('caps', [])):
    imported.add(add_cap(i, cap))
    two_sided.add(f'Cap{i}')

if 'rig' in fit:
    imported.add(prepare_unrigged(list(imported)))
# Some models split their skeleton over several armatures (one per garment); their bones are
# merged, the armature with the most bones winning where they disagree.
model_arms = sorted((o for o in imported if o.type == 'ARMATURE'), key=lambda o: -len(o.data.bones))
model_joint, model_parent = {}, {}
for arm in model_arms:
    for b in arm.data.bones:
        model_joint.setdefault(b.name, arm.matrix_world @ b.head_local)
        model_parent.setdefault(b.name, b.parent.name if b.parent else None)
# Bones of a separate armature (a backpack's) hung from a bone of the body.
model_parent.update(fit.get('attach', {}))
keep = fit.get('keep')
drop_objects = set(fit.get('drop_objects', []))
# Bone display shapes (glTF imports add icospheres) are neither weighted nor parented.
meshes = [o for o in imported if o.type == 'MESH' and (keep is None or o.name in keep) and o.name not in drop_objects
          and (o.vertex_groups or (o.parent and o.parent.type == 'ARMATURE'))]
for o in imported:
    if o.type == 'MESH' and o not in meshes:
        bpy.data.objects.remove(o)
if keep and set(keep) - {o.name for o in meshes}:
    sys.exit(f'meshes not in the model: {sorted(set(keep) - {o.name for o in meshes})}')

turn = Matrix.Rotation(math.radians(fit.get('rotate_z', 0)), 4, 'Z')
radial = fit['radial_scale']
segments = fit['segments']


def placement(seg):
    """4x4 matrix taking a model-space point of this part to the game's bind space."""
    a = model_joint[seg['from'][0]]
    if 'rigid' in seg:
        rot = turn
        if 'align' in seg:
            src = (turn @ (model_joint[seg['align_from'][1]] - model_joint[seg['align_from'][0]])).normalized()
            dst = (game_joint[seg['align'][1]] - game_joint[seg['align'][0]]).normalized()
            rot = src.rotation_difference(dst).to_matrix().to_4x4() @ turn
            if 'roll' in seg:
                # Then turn about that direction so a second model direction (across the palm)
                # follows the game's.
                v = rot.to_3x3() @ (model_joint[seg['roll_from'][1]] - model_joint[seg['roll_from'][0]])
                g = game_joint[seg['roll'][1]] - game_joint[seg['roll'][0]]
                v, g = v - dst * v.dot(dst), g - dst * g.dot(dst)
                rot = v.rotation_difference(g).to_matrix().to_4x4() @ rot
        return Matrix.Translation(game_joint[seg['to'][0]]) @ rot @ Matrix.Scale(seg['rigid'], 4) @ Matrix.Translation(-a)
    b = model_joint[seg['from'][1]]
    src = turn @ (b - a)
    dst = game_joint[seg['to'][1]] - game_joint[seg['to'][0]]
    align = src.normalized().rotation_difference(dst.normalized()).to_matrix().to_4x4() @ turn
    # In the aligned frame: radial scale across, the game's length along the segment.
    axis = dst.normalized()
    along = dst.length / src.length
    stretch = Matrix.Identity(4)
    for i in range(3):
        for j in range(3):
            stretch[i][j] = seg.get('radial', radial) * ((1 if i == j else 0) - axis[i] * axis[j]) \
                + along * axis[i] * axis[j]
    return Matrix.Translation(game_joint[seg['to'][0]]) @ stretch @ align @ Matrix.Translation(-a)


placements = {g: Matrix.Translation(s.get('offset', (0, 0, 0))) @ placement(s) for g, s in segments.items()}


def nearest_segment(point):
    """The segment whose joints (a stretched part's joint-to-joint line, a rigid part's
    anchor) pass closest to a point."""
    def distance(key):
        seg = segments[key]
        a = model_joint[seg['from'][0]]
        if 'rigid' in seg or len(seg['from']) < 2:
            return (point - a).length
        b = model_joint[seg['from'][1]]
        t = max(0.0, min(1.0, (point - a).dot(b - a) / max((b - a).length_squared, 1e-12)))
        return (point - (a + t * (b - a))).length
    return min(segments, key=distance)


# Helper bones that deform a limb but hang from the spine or pelvis (Fortnite's dfrm_*
# splines): each takes the part nearest to it.
for bone in model_joint:
    if any(bone.startswith(p) for p in fit.get('by_position', [])) and bone not in segments:
        model_parent[bone] = nearest_segment(model_joint[bone])


def segment_of(bone):
    while bone is not None and bone not in segments:
        bone = model_parent.get(bone)
    return bone


def weight_target(bone):
    """The game bone a model bone's weights go to: its "bones" entry, else that of its nearest
    ancestor with one, else its segment's bone. (A coat's collar under the chest bone follows the
    chest, not the pelvis of the torso segment: on the pelvis it stretched to the seat.)"""
    mapping = fit.get('bones', {})
    while bone is not None and bone not in mapping and bone not in segments:
        bone = model_parent.get(bone)
    return mapping[bone] if bone in mapping else segments[bone]['bone']


# A mesh attached to a bone (parent type BONE) instead of weighted gets weight 1 to that bone.
for o in meshes:
    if o.parent_type == 'BONE' and o.parent_bone and not o.vertex_groups:
        o.vertex_groups.new(name=o.parent_bone).add(range(len(o.data.vertices)), 1.0, 'REPLACE')

# One mesh, in model space, as displayed in the rest pose: the armature modifiers are applied
# (a mesh bound with another pose than its object transform says sits only there).
for arm in model_arms:
    arm.data.pose_position = 'REST'
for o in meshes:
    bpy.context.view_layer.objects.active = o
    for m in list(o.modifiers):
        if m.type == 'ARMATURE' and m.object:
            with bpy.context.temp_override(object=o, active_object=o):
                bpy.ops.object.modifier_apply(modifier=m.name)
        else:
            o.modifiers.remove(m)
    world = o.matrix_world.copy()
    o.parent = None
    o.data.transform(world)
    o.matrix_world = Matrix.Identity(4)
    if fit.get('weld'):
        # Models ripped with every triangle on its own vertices: join coincident vertices
        # (their UVs stay per corner).
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=fit['weld'])
        # Such rips may wind every triangle inside out (their stored normals hid it); the game
        # culls by winding. Turning them all over (not each surface on its own guess) keeps the
        # insides of thick parts, like a hood's lining, facing inward.
        if fit.get('flip_winding'):
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
            # Pieces that were wound right are now wrong: a face with the surface in front of it
            # and open space behind looks the wrong way, so it turns back.
            from mathutils.bvhtree import BVHTree
            bm.normal_update()
            tree = BVHTree.FromBMesh(bm)
            wrong = []
            for f in bm.faces:
                c, n = f.calc_center_median(), f.normal
                if tree.ray_cast(c + n * 1e-4, n)[0] is not None and tree.ray_cast(c - n * 1e-4, -n)[0] is None:
                    wrong.append(f)
            bmesh.ops.reverse_faces(bm, faces=wrong)
        bm.to_mesh(o.data)
        bm.free()
        # The imported custom normals no longer match the joined vertices: smooth ones instead.
        with bpy.context.temp_override(object=o, active_object=o):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        for p in o.data.polygons:
            p.use_smooth = True
    if o.name in two_sided:
        # Thin shells whose winding no rule gets right (a hood's lining around the face): a copy
        # of every face turned over, on its own vertices, so the game draws it from both sides.
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(o.data)
        copy = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
        bmesh.ops.reverse_faces(bm, faces=[g for g in copy['geom'] if isinstance(g, bmesh.types.BMFace)])
        bm.to_mesh(o.data)
        bm.free()
    # Joining merges UV maps by name: give every mesh's active map the same name, drop the rest.
    layers = o.data.uv_layers
    if layers.active:
        for layer in [l for l in layers if l != layers.active]:
            layers.remove(layer)
        layers.active.name = 'UVMap'
bpy.ops.object.select_all(action='DESELECT')
for index, o in enumerate(meshes):
    o.select_set(True)
    # Each face remembers its mesh, so a reduced face takes its UVs from its own mesh only
    # (reduced(): a hood's peak sinks towards the hair under it).
    part = o.data.attributes.new('_part', 'INT', 'FACE')
    part.data.foreach_set('value', [index] * len(o.data.polygons))
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
mesh = bpy.context.view_layer.objects.active
mesh.name = 'Character'

drop = set(fit.get('drop_materials', []))
if drop:
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    names = [m.name if m else '' for m in mesh.data.materials]
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if names[f.material_index] in drop], context='FACES')
    bm.to_mesh(mesh.data)
    bm.free()

drop_groups = fit.get('drop_groups', [])
if drop_groups:
    # Faces whose every vertex hangs mostly from these bones (by name prefix): closed eyelids.
    import bmesh
    dropped = {g.index for g in mesh.vertex_groups if g.name.startswith(tuple(drop_groups))}
    share = [sum(g.weight for g in v.groups if g.group in dropped) for v in mesh.data.vertices]
    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if all(share[v.index] > 0.5 for v in f.verts)], context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(mesh.data)
    bm.free()

group_names = {g.index: g.name for g in mesh.vertex_groups}
targets = {}
unplaced = 0
lost = set()
for v in mesh.data.vertices:
    infl = [(g.weight, group_names[g.group]) for g in v.groups if g.weight > 0 and segment_of(group_names[g.group])]
    if not any(g.weight > 0 for g in v.groups):
        infl = [(1.0, nearest_segment(v.co))]  # a stray vertex with no weights at all
    total = sum(w for w, _ in infl)
    if total <= 0:
        unplaced += 1
        lost.update(group_names[g.group] for g in v.groups if g.weight > 0)
        continue
    co = v.co.copy()
    pos = Vector((0, 0, 0))
    for w, name in infl:
        seg = segment_of(name)
        pos += (w / total) * (placements[seg] @ co)
        bone = weight_target(name)
        targets.setdefault(bone, {})
        targets[bone][v.index] = targets[bone].get(v.index, 0) + w / total
    v.co = pos
if unplaced:
    chains = {b: [b] for b in sorted(lost)}
    for b, chain in chains.items():
        while model_parent.get(chain[-1]):
            chain.append(model_parent[chain[-1]])
    sys.exit(f'{unplaced} vertices have no weight to a placed bone; their bones and parents: '
             + '; '.join(' < '.join(c) for c in chains.values()))
for g in list(mesh.vertex_groups):
    mesh.vertex_groups.remove(g)
for bone, weights in targets.items():
    group = mesh.vertex_groups.new(name=bone)
    for vi, w in weights.items():
        group.add([vi], w, 'REPLACE')
for arm in model_arms:
    bpy.data.objects.remove(arm)
mesh.data.update()


# --- atlas -----------------------------------------------------------------------------------
def to_srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def material_source(mat):
    """(base colour sRGB, image or None, mapping node or None, extension)."""
    base, image, mapping, extension = (1.0, 1.0, 1.0), None, None, 'REPEAT'
    if mat and mat.node_tree:
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf:
            base = tuple(to_srgb(c) for c in bsdf.inputs['Base Color'].default_value[:3])
        base = tuple(fit.get('base_colors', {}).get(mat.name, base))
        tex = next((n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), None)
        if not tex and mat.name in fit.get('images', {}):
            image = bpy.data.images.load(fit['images'][mat.name], check_existing=True)
        if tex:
            image, extension = find_image(tex.image), tex.extension
            link = next((l for l in mat.node_tree.links if l.to_node == tex and l.from_node.type == 'MAPPING'), None)
            mapping = link.from_node if link else None
    return base, image, mapping, extension


def pack(sizes, size):
    """Shelf packing: {key: (w, h)} -> {key: (x, y)} or None if they do not fit."""
    order = sorted(sizes, key=lambda k: (-sizes[k][1], -sizes[k][0]))
    out, x, y, shelf = {}, 0, 0, 0
    for k in order:
        w, h = sizes[k]
        if x + w > size:
            x, y, shelf = 0, y + shelf, 0
        if w > size or y + h > size:
            return None
        out[k] = (x, y)
        x += w
        shelf = max(shelf, h)
    return out


def bleed(mesh, pixels, size, steps=96):
    """The atlas with colour spread from the pixels the mesh's UV triangles cover into the
    pixels around them (gutters, background), so UVs a little off an island (reduced levels of
    detail, filtering, mipmaps) still read the island's colour."""
    import numpy as np
    image = np.array(pixels, dtype=np.float32).reshape(size, size, 4)
    covered = np.zeros((size, size), bool)
    uv = mesh.data.uv_layers.active.data
    mesh.data.calc_loop_triangles()
    for tri in mesh.data.loop_triangles:
        p = np.array([uv[l].uv[:] for l in tri.loops]) * size - 0.5
        x0, y0 = np.floor(p.min(0)).astype(int)
        x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        (ax, ay), (bx, by), (cx, cy) = p
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-12:
            covered[int(round(ay)) if 0 <= ay < size else y0, int(round(ax)) if 0 <= ax < size else x0] = True
            continue
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / det
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / det
        inside = (l1 >= -0.5 / size * 4) & (l2 >= -0.02) & (1 - l1 - l2 >= -0.02)
        covered[y0:y1 + 1, x0:x1 + 1] |= inside
    for _ in range(steps):
        total = np.zeros_like(image)
        count = np.zeros((size, size), np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            shifted = np.roll(covered, (dy, dx), (0, 1))
            total += np.roll(image, (dy, dx), (0, 1)) * shifted[..., None]
            count += shifted
        grow = ~covered & (count > 0)
        image[grow] = total[grow] / count[grow][:, None]
        covered |= grow
    return image.ravel().tolist()


def make_atlas(mesh, size, slot, path):
    """Each material's image, cropped to the part its UVs use (a plain part shrunk to a few
    pixels), laid over its base colour, packed into one image; UVs move into the cells."""
    import numpy as np
    used = sorted({p.material_index for p in mesh.data.polygons})
    sources = {i: material_source(mesh.data.materials[i]) for i in used}
    uv = mesh.data.uv_layers.active.data
    mapped = {}
    for poly in mesh.data.polygons:
        _, _, mapping, _ = sources[poly.material_index]
        for li in poly.loop_indices:
            u, v = uv[li].uv
            if mapping and mapping.vector_type == 'POINT':
                s, loc = mapping.inputs['Scale'].default_value, mapping.inputs['Location'].default_value
                u, v = u * s[0] + loc[0], v * s[1] + loc[1]
            mapped[li] = (u, v)
    # A repeating texture whose UVs sit in another tile (-1..0, say): move all of the material's
    # UVs by whole tiles so their middle lands in 0..1, keeping the layout intact.
    shift = {}
    loops_of = {i: [li for p in mesh.data.polygons if p.material_index == i for li in p.loop_indices] for i in used}
    for i in used:
        if sources[i][3] != 'REPEAT':
            continue
        coords = [mapped[li] for li in loops_of[i]]
        mid_u = (min(c[0] for c in coords) + max(c[0] for c in coords)) / 2
        mid_v = (min(c[1] for c in coords) + max(c[1] for c in coords)) / 2
        shift[i] = (math.floor(mid_u), math.floor(mid_v))
    final = {}
    for i in used:
        du, dv = shift.get(i, (0, 0))
        for li in loops_of[i]:
            u, v = mapped[li]
            final[li] = (min(max(u - du, 0.0), 1.0), min(max(v - dv, 0.0), 1.0))
    # A plain colour gets a 32-pixel cell and every UV at its centre, where filtering and mip
    # levels cannot reach the neighbouring cells.
    arrays, keys, crops, cells, plain = {}, {}, {}, {}, set()
    for i in used:
        base, image, _, _ = sources[i]
        flat = False
        if image is None:
            crop, cell, flat = None, (32, 32), True
        else:
            if image.name not in arrays:
                w, h = image.size
                arrays[image.name] = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, image.channels)
            sw, sh = image.size
            us = [final[li][0] for li in loops_of[i]]
            vs = [final[li][1] for li in loops_of[i]]
            margin_u, margin_v = 2 / sw, 2 / sh
            crop = (max(min(us) - margin_u, 0.0), max(min(vs) - margin_v, 0.0),
                    min(max(us) + margin_u, 1.0), min(max(vs) + margin_v, 1.0))
            cell = (max(8, int((crop[2] - crop[0]) * sw)), max(8, int((crop[3] - crop[1]) * sh)))
            part = arrays[image.name][int(crop[1] * sh):int(crop[3] * sh) + 1, int(crop[0] * sw):int(crop[2] * sw) + 1]
            if part.size and part[..., :3].std(axis=(0, 1)).max() < 0.01:
                cell, flat = (32, 32), True
        key = (tuple(round(c, 4) for c in base), image.name if image else None,
               tuple(round(c, 4) for c in crop) if crop else None)
        keys[i], crops[key], cells[key] = key, crop, cell
        if flat:
            plain.add(key)
    scale = 1.0
    while True:
        # Plain cells keep their few pixels and painted faces (decals) their full resolution;
        # the rest shrink to fit.
        sized = {k: (w, h) if k in plain or (k[1] or '').endswith('_decal')
                 else (max(16, int(w * scale)), max(16, int(h * scale)))
                 for k, (w, h) in cells.items()}
        spots = pack(sized, size)
        if spots:
            break
        scale *= 0.9
    pad = 2
    pixels = np.zeros((size, size, 4), np.float32)
    drawn = set()
    for i in used:
        k = keys[i]
        if k in drawn:
            continue  # an identical material's cell
        drawn.add(k)
        base, image, _, _ = sources[i]
        (x0, y0), (cw, ch) = spots[k], sized[k]
        colour = np.empty((ch, cw, 3), np.float32)
        colour[:] = base
        if image is not None:
            src = arrays[image.name]
            sh, sw = src.shape[:2]
            c0u, c0v, c1u, c1v = crops[k]
            u = c0u + np.clip((np.arange(cw) - pad + 0.5) / max(cw - 2 * pad, 1), 0, 1) * (c1u - c0u)
            v = c0v + np.clip((np.arange(ch) - pad + 0.5) / max(ch - 2 * pad, 1), 0, 1) * (c1v - c0v)
            # Bilinear sample (Blender pixel rows run bottom first, as v does).
            x = np.clip(u * sw - 0.5, 0, sw - 1)
            y = np.clip(v * sh - 0.5, 0, sh - 1)
            xa, ya = np.floor(x).astype(int), np.floor(y).astype(int)
            xb, yb = np.minimum(xa + 1, sw - 1), np.minimum(ya + 1, sh - 1)
            fx, fy = (x - xa)[None, :, None], (y - ya)[:, None, None]
            t = (src[ya][:, xa] * (1 - fx) * (1 - fy) + src[ya][:, xb] * fx * (1 - fy)
                 + src[yb][:, xa] * (1 - fx) * fy + src[yb][:, xb] * fx * fy)
            # The image's alpha lays it over the base colour (N64 eyes over skin). Over a white
            # base the alpha is usually not coverage (BotW stores other data there): ignored.
            a = t[..., 3:4] if src.shape[2] == 4 and any(c < 0.95 for c in base) else 1.0
            colour = t[..., :3] * a + colour * (1 - a)
        pixels[y0:y0 + ch, x0:x0 + cw, :3] = colour
        pixels[y0:y0 + ch, x0:x0 + cw, 3] = 1.0
    for poly in mesh.data.polygons:
        k = keys[poly.material_index]
        (x0, y0), (cw, ch) = spots[k], sized[k]
        c0u, c0v, c1u, c1v = crops[k] or (0.0, 0.0, 1.0, 1.0)
        for li in poly.loop_indices:
            if k in plain:
                uv[li].uv = ((x0 + cw / 2) / size, (y0 + ch / 2) / size)
                continue
            u, v = final[li]
            u = (u - c0u) / max(c1u - c0u, 1e-9)
            v = (v - c0v) / max(c1v - c0v, 1e-9)
            uv[li].uv = ((x0 + pad + u * (cw - 2 * pad)) / size, (y0 + pad + v * (ch - 2 * pad)) / size)
    img = bpy.data.images.new('atlas', size, size, alpha=True)
    img.pixels = bleed(mesh, pixels.ravel(), size)
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    mat = bpy.data.materials.new(slot)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
    tex.image = img
    mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    mesh.data.materials.clear()
    mesh.data.materials.append(mat)
    for poly in mesh.data.polygons:
        poly.material_index = 0
    print('ATLAS', path, 'scale', round(scale, 3), len(cells), 'cells')


if 'atlas' in fit:
    make_atlas(mesh, fit['atlas'].get('size', 1024), fit['atlas'].get('slot', 'Cloth'),
               Path(out_path).with_suffix('.png'))

mesh.parent = game_arm
mod = mesh.modifiers.new('Armature', 'ARMATURE')
mod.object = game_arm

if render_dir:
    render_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.color_type = 'TEXTURE' if 'atlas' in fit else 'MATERIAL'
    scene.render.resolution_x, scene.render.resolution_y = 900, 900
    scene.world = bpy.data.worlds.new('w')
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    cam.data.type = 'ORTHO'
    top = max((game_mesh.matrix_world @ v.co).z for v in game_mesh.data.vertices)
    cam.data.ortho_scale = 1.15 * top
    scene.collection.objects.link(cam)
    scene.camera = cam
    centre = Vector((0, 0, top / 2))
    views = {'front': Vector((3, 0, 0)), 'side': Vector((0, 3, 0)), 'quarter': Vector((2.1, 2.1, 0.8))}
    for name, offset in views.items():
        cam.location = centre + offset
        cam.rotation_euler = (-offset).to_track_quat('-Z', 'Y').to_euler()
        for show_game in (False, True):
            game_mesh.hide_render = not show_game
            mesh.hide_render = show_game
            scene.render.filepath = str(render_dir / f'{name}_{"game" if show_game else "model"}.png')
            bpy.ops.render.render(write_still=True)
bpy.data.objects.remove(game_mesh)
bpy.ops.export_scene.gltf(filepath=out_path, export_format='GLB', export_skins=True,
                          export_animations=False, export_yup=True, use_selection=False)


def reduced(source, target):
    """A copy of the mesh with about `target` vertices. The collapse keeps the surface closed
    but blends UVs across island borders, so each face then takes its UVs again from the
    original surface: from the one original triangle nearest to its centre, extended to its
    corners (one island per face; the atlas bleeds colour past island borders for the rest)."""
    from mathutils.bvhtree import BVHTree
    from mathutils.geometry import barycentric_transform
    import bmesh
    obj = source.copy()
    obj.data = source.data.copy()
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    # Flat areas first (within UV islands): a model of many thin layers (straps, flaps) then
    # keeps its shape when collapsed to a few thousand vertices.
    mod = obj.modifiers.new('planar', 'DECIMATE')
    mod.decimate_type, mod.angle_limit, mod.delimit = 'DISSOLVE', math.radians(4), {'UV', 'SEAM', 'MATERIAL'}
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    # Vertices on UV seams are kept while that still reaches the target: a face that collapses
    # across a seam stretches one island's border over its whole width (a visible stripe).
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layer = bm.loops.layers.uv.active
    seam = set()
    for e in bm.edges:
        if len(e.link_loops) == 2:
            x, y = e.link_loops
            if (x[layer].uv - y.link_loop_next[layer].uv).length > 1e-5 or \
               (x.link_loop_next[layer].uv - y[layer].uv).length > 1e-5:
                seam.update(v.index for v in e.verts)
    bm.free()
    keep = obj.vertex_groups.new(name='_seams')
    keep.add(list(seam), 1.0, 'REPLACE')
    def exported():
        """Vertices as exported: glTF (and the game) split a vertex once per distinct UV."""
        uv = obj.data.uv_layers.active.data
        return len({(l.vertex_index, round(uv[l.index].uv[0], 6), round(uv[l.index].uv[1], 6))
                    for l in obj.data.loops})

    # The collapse slows down near borders and seams: repeat while it still makes progress.
    for protect in (True, False):
        for _ in range(12):
            count = exported()
            if count <= target:
                break
            mod = obj.modifiers.new('decimate', 'DECIMATE')
            mod.ratio = max(0.05, 0.97 * target / count)
            if protect:
                mod.vertex_group, mod.invert_vertex_group, mod.vertex_group_factor = keep.name, True, 10
            with bpy.context.temp_override(object=obj, active_object=obj):
                bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=0)
                bpy.ops.object.modifier_apply(modifier=mod.name)
            if exported() > 0.98 * count:
                break
    obj.vertex_groups.remove(obj.vertex_groups['_seams'])
    src = source.data
    src.calc_loop_triangles()
    tris = list(src.loop_triangles)
    src_uv = src.uv_layers.active.data
    coords = [v.co for v in src.vertices]
    # UV islands of the original: triangles joined where they share a vertex with the same UV.
    parent = list(range(len(tris)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first = {}
    for ti, t in enumerate(tris):
        for vi, li in zip(t.vertices, t.loops):
            key = (vi, round(src_uv[li].uv[0], 5), round(src_uv[li].uv[1], 5))
            if key in first:
                parent[root(ti)] = root(first[key])
            else:
                first[key] = ti
    islands = {}
    for ti in range(len(tris)):
        islands.setdefault(root(ti), []).append(ti)
    trees = {k: (BVHTree.FromPolygons(coords, [tris[i].vertices for i in members]), members)
             for k, members in islands.items()}
    # A face picks its island among the big ones: scans strew slivers of a few triangles along
    # their seams, and a face that picked one would take the sliver's colour all over.
    big = [ti for k, members in islands.items() if len(members) >= 50 for ti in members] or list(range(len(tris)))
    # ... and only among its own mesh's (the "_part" each face carries from before the join).
    src_part = src.attributes.get('_part')
    me = obj.data
    part = me.attributes.get('_part')
    parts = {}
    for ti in big:
        parts.setdefault(src_part.data[tris[ti].polygon_index].value if src_part else 0, []).append(ti)
    wholes = {k: (BVHTree.FromPolygons(coords, [tris[i].vertices for i in members]), members)
              for k, members in parts.items()}
    everything = (BVHTree.FromPolygons(coords, [tris[i].vertices for i in big]), big)
    uv = me.uv_layers.active.data
    for poly in me.polygons:
        whole, chosen = wholes.get(part.data[poly.index].value if part else 0, everything)
        _, normal, index, dist = whole.find_nearest(poly.center)
        if index is None:
            continue
        # Layers close together face the same way only on the face's own layer: take the
        # nearest original face that does, if there is one nearby.
        if normal.dot(poly.normal) < 0.5:
            near = [hit for hit in whole.find_nearest_range(poly.center, dist + 0.02)
                    if hit[1].dot(poly.normal) >= 0.5]
            if near:
                index = min(near, key=lambda hit: hit[3])[2]
        tree, members = trees[root(chosen[index])]
        corners = {}
        for li in poly.loop_indices:
            p = me.vertices[me.loops[li].vertex_index].co
            # Each corner reads the nearest point of the face's own island (never past its border),
            # moved a little into its triangle: scanned textures fringe their islands.
            near, _, local, _ = tree.find_nearest(p)
            t = tris[members[local]]
            a, b, c = (coords[i] for i in t.vertices)
            near = near.lerp((a + b + c) / 3, 0.2)
            ua, ub, uc = (Vector((*src_uv[l].uv, 0)) for l in t.loops)
            corners[li] = barycentric_transform(near, a, b, c, ua, ub, uc).xy
        # An island that meets itself along a seam (a hood's two halves) can send the corners to
        # its opposite edges: the face would cross the whole texture between them. Such a face
        # takes the mapping of its centre's triangle for every corner instead.
        t = tris[chosen[index]]
        a, b, c = (coords[i] for i in t.vertices)
        ua, ub, uc = (Vector((*src_uv[l].uv, 0)) for l in t.loops)
        scale = max((ub - ua).length / max((b - a).length, 1e-9), (uc - ua).length / max((c - a).length, 1e-9))
        span = max((corners[x] - corners[y]).length for x in corners for y in corners)
        size = max((me.vertices[me.loops[x].vertex_index].co - me.vertices[me.loops[y].vertex_index].co).length
                   for x in corners for y in corners)
        if span > 2 * scale * size + 0.005:
            for li in corners:
                p = me.vertices[me.loops[li].vertex_index].co
                corners[li] = barycentric_transform(p, a, b, c, ua, ub, uc).xy
        for li, value in corners.items():
            uv[li].uv = value
    return obj


# Reduced copies for the levels of detail ("lods": the game's vertex count per level, from
# `character_mod.py info`): out_lod<n>.glb, used by `character_mod.py build` for level n.
for n, target in enumerate(fit.get('lods', [])):
    lod_path = Path(out_path).with_name(f'{Path(out_path).stem}_lod{n}.glb')
    if lod_path.exists():
        lod_path.unlink()
    if len(mesh.data.vertices) <= target:
        continue
    obj = reduced(mesh, target)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    game_arm.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(lod_path), export_format='GLB', export_skins=True,
                              export_animations=False, export_yup=True, use_selection=True)
    print('LOD', n, len(obj.data.vertices), 'vertices', lod_path)
    bpy.data.objects.remove(obj)
print('FIT_DONE', out_path, {b: len(v) for b, v in targets.items()})
