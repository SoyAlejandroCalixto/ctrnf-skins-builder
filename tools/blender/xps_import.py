"""XNALara / XPS .mesh to .glb (armature, weights, UVs, colour textures), for blender_fit.

    blender -b --factory-startup --python tools/blender/xps_import.py -- model.mesh out.glb [keep]
                [--cut=prefix:height ...] [--unweight=prefix:other,other ...]

--unweight=prefix:a,b takes the weights to bones named a... / b... off the vertices weighted
more than 0.3 to bones named prefix... (a cape pulled by the arm folds when the arm reaches out).

--cut=prefix:height cuts the faces weighted more than half to bones named prefix... straight
across at that height (metres, Z up) and drops what is below: a cape shortened with a clean hem
(dropping it by bones in blender_fit ends each layer of cloth at a different height, in strips).

keep: regular expression of the meshes to keep (default: all). XPS mesh names start with a render
group ("24_", "27_"...); Fortnite rips repeat the meshes in group 27 for reflections, and "-name"
meshes are hidden alternatives. The first texture of a mesh is its colour map. XPS is Y up, its
triangles clockwise.
"""
import re
import sys
from pathlib import Path

import bpy
import numpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import xps  # noqa: E402

args = sys.argv[sys.argv.index('--') + 1:]
cuts = [a[len('--cut='):].rsplit(':', 1) for a in args if a.startswith('--cut=')]
unweights = [a[len('--unweight='):].split(':', 1) for a in args if a.startswith('--unweight=')]
args = [a for a in args if not a.startswith(('--cut=', '--unweight='))]
src, out = Path(args[0]).resolve(), Path(args[1]).resolve()
keep = re.compile(args[2]) if len(args) > 2 else None
model = xps.read(src.read_bytes())


def to_blender(p):
    return (p[0], -p[2], p[1])


def unweighted(joints, weights, joint):
    """--unweight: whether this vertex's weight to `joint` is dropped (the rest is normalised by
    the armature)."""
    name = model['bones'][joint][0]
    for prefix, others in unweights:
        part = sum(w for j, w in zip(joints, weights) if model['bones'][j][0].startswith(prefix))
        if part > 0.3 and name.startswith(tuple(others.split(','))):
            return True
    return False


def cut(ob, prefix, height):
    """--cut: the part weighted to bones `prefix...` cut at `height`, the rest below dropped."""
    import bmesh
    chosen = {g.index for g in ob.vertex_groups if g.name.startswith(prefix)}
    if not chosen:
        return
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    deform = bm.verts.layers.deform.verify()

    def part(v):
        return sum(w for g, w in v[deform].items() if g in chosen) > 0.5

    faces = [f for f in bm.faces if all(part(v) for v in f.verts)]
    if not faces:
        bm.free()
        return
    geom = list({v for f in faces for v in f.verts}) + list({e for f in faces for e in f.edges}) + faces
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, height), plane_no=(0, 0, 1))
    below = [f for f in bm.faces if all(part(v) for v in f.verts) and f.calc_center_median().z < height]
    bmesh.ops.delete(bm, geom=below, context='FACES')
    # The cut leaves quads and n-gons; the rest is triangles, as the reductions expect.
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(ob.data)
    bm.free()
    print(f'  {ob.name}: {prefix}* cut at {height}, {len(below)} faces below dropped')


bpy.ops.wm.read_factory_settings(use_empty=True)
arm_data = bpy.data.armatures.new('Armature')
arm = bpy.data.objects.new('Armature', arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
bones = []
for name, parent, pos in model['bones']:
    b = arm_data.edit_bones.new(name)
    b.head = to_blender(pos)
    bones.append(b)
children = {}
for i, (_, parent, _) in enumerate(model['bones']):
    if parent >= 0:
        bones[i].parent = bones[parent]
        children.setdefault(parent, []).append(i)
for i, b in enumerate(bones):
    # Tail at the children's mean, else continuing the parent's direction, else up.
    kids = [bones[k].head for k in children.get(i, [])]
    tail = sum(kids, Vector()) / len(kids) if kids else None
    if tail is None or (tail - b.head).length < 1e-4:
        away = b.head - b.parent.head if b.parent else Vector()
        tail = b.head + (away.normalized() if away.length > 1e-4 else Vector((0, 0, 1))) * 0.02
    b.tail = tail
bpy.ops.object.mode_set(mode='OBJECT')

materials = {}
for m in model['meshes']:
    if keep and not keep.search(m['name']):
        continue
    me = bpy.data.meshes.new(m['name'])
    # XPS triangles turn clockwise seen from outside; Blender and the game want counter-clockwise.
    me.from_pydata([to_blender(p) for p in m['positions']], [], [(a, c, b) for a, b, c in m['triangles']])
    uv = me.uv_layers.new(name='UVMap')
    for loop in me.loops:
        u, v = m['uvs'][0][loop.vertex_index]
        uv.data[loop.index].uv = (u, 1 - v)
    me.normals_split_custom_set_from_vertices([to_blender(n) for n in m['normals']])
    tex = m['textures'][0][0] if m['textures'] else None
    if tex not in materials:
        mat = bpy.data.materials.new(Path(tex).stem if tex else 'none')
        mat.use_nodes = True
        if tex and (src.parent / tex).exists():
            node = mat.node_tree.nodes.new('ShaderNodeTexImage')
            image = node.image = bpy.data.images.load(str(src.parent / tex))
            # The alpha of XPS colour maps is a mask (specular, emission...), not transparency.
            pixels = numpy.array(image.pixels[:])
            pixels[3::4] = 1.0
            image.pixels[:] = pixels
            image.alpha_mode = 'NONE'
            image.pack()
            mat.node_tree.links.new(node.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
        materials[tex] = mat
    me.materials.append(materials[tex])
    ob = bpy.data.objects.new(m['name'], me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = arm
    groups = {}
    for v, (js, ws) in enumerate(zip(m['joints'], m['weights'])):
        for j, w in zip(js, ws):
            if w > 0 and not unweighted(js, ws, j):
                if j not in groups:
                    groups[j] = ob.vertex_groups.new(name=model['bones'][j][0])
                groups[j].add([v], w, 'ADD')
    ob.modifiers.new('Armature', 'ARMATURE').object = arm
    for prefix, height in cuts:
        cut(ob, prefix, float(height))
    print(f'{m["name"]}: {len(m["positions"])} vertices, texture {tex}')

bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB')
print('wrote', out)
