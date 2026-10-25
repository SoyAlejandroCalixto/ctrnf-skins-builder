"""Kazuya (SSBU XPS): give the face cards (lashes, hairline) their own material so blender_fit's
"base_colors" can put skin under their transparent parts (hair keeps a dark base), and print the
forehead skin colour sampled from the texture under the eyebrows.
Usage: blender -b --factory-startup --python kazuya_split_face.py -- in.glb out.glb"""
import bpy, sys
from mathutils import Vector
a = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a[0])
face = next(o for o in bpy.data.objects if o.name.startswith('7_Face Part'))
mat = face.data.materials[0].copy()
mat.name = 'alp_face'
face.data.materials[0] = mat
# forehead skin: the skin mesh's texels just above the eyebrows
body = [o for o in bpy.data.objects if o.type == 'MESH' and o.data.materials and o.data.materials[0].name == 'skin_demon_001b_col']
img = next(n.image for n in body[0].data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
w, h = img.size
px = img.pixels[:]
acc, n = Vector((0, 0, 0)), 0
for o in body:
    uv = o.data.uv_layers.active.data
    for loop in o.data.loops:
        p = o.matrix_world @ o.data.vertices[loop.vertex_index].co
        if abs(p.x) < 0.03 and p.y < -0.08 and 1.44 < p.z < 1.47:
            u, v = uv[loop.index].uv
            i = (int(v % 1 * h) * w + int(u % 1 * w)) * 4
            acc += Vector(px[i:i + 3])
            n += 1
print('FOREHEAD', n, [round(c / max(n, 1), 3) for c in acc])

# The game draws no transparency: a card shows whole. Faces of the cards (eyebrows, lashes,
# hairline) that are mostly transparent go, so only the painted part of each card stays.
import bmesh
for o in bpy.data.objects:
    if not (o.name.startswith('7_Face Part') or o.name.startswith('7_Eyebrows A')):
        continue
    tex = next(n.image for n in o.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
    tw, th = tex.size
    tp = tex.pixels[:]
    def alpha(u, v):
        return tp[(int(v % 1 * th) * tw + int(u % 1 * tw)) * 4 + 3]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    layer = bm.loops.layers.uv.active
    drop = []
    for f in bm.faces:
        uvs = [l[layer].uv for l in f.loops]
        c = sum(uvs, Vector((0, 0))) / len(uvs)
        samples = [alpha(*c)] + [alpha(*(c.lerp(uv, 0.6))) for uv in uvs]
        if sum(samples) / len(samples) < 0.35:
            drop.append(f)
    bmesh.ops.delete(bm, geom=drop, context='FACES')
    bm.to_mesh(o.data)
    bm.free()
    print('CARD', o.name, 'dropped', len(drop), 'faces')
bpy.ops.export_scene.gltf(filepath=a[1], export_format='GLB')
