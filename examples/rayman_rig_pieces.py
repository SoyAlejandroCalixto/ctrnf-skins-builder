"""Rayman (SFM FBX, no skin): bake the node transforms, scale to metres with the feet on the
floor, and give each loose piece one bone (head, hands, feet; torso blended pelvis->chest).
OFF, the scale, J and piece() are this model's: measure another model's pieces first.
Usage: blender -b --factory-startup --python rayman_rig_pieces.py -- in.fbx textures_dir out.glb"""
import bpy, bmesh, sys, os
from mathutils import Vector, Matrix
a = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=a[0])
for img in bpy.data.images:
    img.filepath = os.path.join(a[1], os.path.basename(img.filepath.replace('\\', '/')))
    img.reload()
OFF = Vector((1.642, 0.91, 1.681))
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
for o in meshes:
    o.data.transform(Matrix.Translation(OFF) @ Matrix.Scale(1000, 4) @ o.matrix_world)
    o.parent = None
    o.matrix_world = Matrix.Identity(4)
for o in [o for o in bpy.data.objects if o.type != 'MESH']:
    bpy.data.objects.remove(o)

J = {'pelvis': (0, 0, 0.60), 'chest': (0, 0, 0.85), 'neck': (0, 0, 1.13), 'headtop': (0, 0, 1.80),
     'wrist_L': (0.48, -0.11, 0.77), 'handtip_L': (0.83, -0.11, 0.52),
     'wrist_R': (-0.48, -0.11, 0.77), 'handtip_R': (-0.83, -0.11, 0.52),
     'ankle_L': (0.165, -0.1, 0.13), 'toe_L': (0.165, -0.5, 0.06),
     'ankle_R': (-0.165, -0.1, 0.13), 'toe_R': (-0.165, -0.5, 0.06)}
J = {k: Vector(v) for k, v in J.items()}
BONES = [('pelvis', 'pelvis', 'chest', None), ('chest', 'chest', 'neck', 'pelvis'),
         ('head', 'neck', 'headtop', 'chest'), ('headtop', 'headtop', None, 'head')]
for s in 'LR':
    BONES += [(f'hand_{s}', f'wrist_{s}', f'handtip_{s}', 'chest'), (f'handtip_{s}', f'handtip_{s}', None, f'hand_{s}'),
              (f'foot_{s}', f'ankle_{s}', f'toe_{s}', 'pelvis'), (f'toe_{s}', f'toe_{s}', None, f'foot_{s}')]
arm_data = bpy.data.armatures.new('rayman_rig')
arm = bpy.data.objects.new('rayman_rig', arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
for name, h, t, p in BONES:
    b = arm_data.edit_bones.new(name)
    b.head = J[h]
    b.tail = J[t] if t else J[h] + Vector((0, 0, 0.02))
    if p:
        b.parent = arm_data.edit_bones[p]
bpy.ops.object.mode_set(mode='OBJECT')


def piece(c):
    """Bone of a loose piece by its centre."""
    side = 'L' if c.x > 0 else 'R'
    if c.z < 0.3:
        return 'foot_' + side
    if abs(c.x) > 0.4 and c.z < 0.9:
        return 'hand_' + side
    if c.z > 1.12:
        return 'head'
    return None  # torso


for o in meshes:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.verts.ensure_lookup_table()
    groups = {}

    def add(name, i, w):
        g = groups.get(name) or o.vertex_groups.new(name=name)
        groups[name] = g
        g.add([i], w, 'REPLACE')
    seen = set()
    for v in bm.verts:
        if v.index in seen:
            continue
        comp, st = [], [v]
        seen.add(v.index)
        while st:
            x = st.pop()
            comp.append(x)
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index)
                    st.append(y)
        c = sum((x.co for x in comp), Vector()) / len(comp)
        bone = piece(c)
        for x in comp:
            if bone:
                add(bone, x.index, 1.0)
            else:
                t = max(0.0, min(1.0, (x.co.z - 0.65) / 0.30))
                if t < 1:
                    add('pelvis', x.index, 1 - t)
                if t > 0:
                    add('chest', x.index, t)
    bm.free()
    o.parent = arm
    m = o.modifiers.new('arm', 'ARMATURE')
    m.object = arm
    print('PIECES', o.name, {k: len([1 for v in o.data.vertices if any(g.group == gg.index for g in v.groups)]) for k, gg in groups.items()})
bpy.ops.export_scene.gltf(filepath=a[2], export_format='GLB')
print('RIG_DONE', a[2])
