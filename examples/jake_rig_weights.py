"""Jake: give the unrigged glb an armature with region-based weights (bone heat bleeds the arms
into the face/ears and the thighs into the belly). Usage: blender -b --python rig_jake.py -- fit.json in.glb out.glb"""
import bpy, sys, json
from mathutils import Vector
a = sys.argv[sys.argv.index('--') + 1:]
rig = json.load(open(a[0]))['rig_src']
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a[1])
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
for o in meshes:
    o.data.transform(o.matrix_world); o.matrix_world.identity(); o.parent = None
J = {k: Vector(v) for k, v in rig['joints'].items()}
arm_data = bpy.data.armatures.new('jake_rig'); arm = bpy.data.objects.new('jake_rig', arm_data)
bpy.context.scene.collection.objects.link(arm); bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
for name, h, t, p in rig['bones']:
    b = arm_data.edit_bones.new(name); b.head = J[h]; b.tail = J[t]
    if p: b.parent = arm_data.edit_bones[p]
bpy.ops.object.mode_set(mode='OBJECT')
seg = {n: (J[h], J[t]) for n, h, t, p in rig['bones']}
def d(n, p):
    h, t = seg[n]; c = t - h
    s = max(0.0, min(1.0, (p - h).dot(c) / c.length_squared)); return (p - (h + s * c)).length
def limb(p, names):
    w = {n: 1.0 / max(d(n, p), 0.05) ** 6 for n in names}; s = sum(w.values())
    return {n: x / s for n, x in w.items() if x / s > 0.02}
def ramp(x, a, b): return max(0.0, min(1.0, (x - a) / (b - a)))
def weights(p):
    # torso: pelvis below, body above
    t = ramp(p.z, 6.5, 9.0); w = {'pelvis': 1 - t, 'body': t}
    side = 'L' if p.x > 0 else 'R'
    if 9.3 < p.z < 10.35 and abs(p.x) > 2.5:      # arm, blended into the torso at its root
        k = ramp(abs(p.x), 2.5, 3.3)
        lw = limb(p, ['upperarm_' + side, 'forearm_' + side, 'hand_' + side])
        w = {n: x * (1 - k) for n, x in w.items()}
        for n, x in lw.items(): w[n] = w.get(n, 0) + x * k
    elif p.z < 5.1 and 0.4 < abs(p.x) < 2.0:      # leg, blended in at its top
        k = 1 - ramp(p.z, 4.6, 5.1)
        lw = limb(p, ['thigh_' + side, 'calf_' + side, 'foot_' + side])
        w = {n: x * (1 - k) for n, x in w.items()}
        for n, x in lw.items(): w[n] = w.get(n, 0) + x * k
    return w
for o in meshes:
    groups = {}
    main = o.name == 'Cubo'
    for v in o.data.vertices:
        w = weights(v.co) if main else {'body': 1.0}
        for n, x in w.items():
            if x <= 0: continue
            g = groups.get(n) or o.vertex_groups.new(name=n); groups[n] = g
            g.add([v.index], x, 'REPLACE')
    o.parent = arm; m = o.modifiers.new('arm', 'ARMATURE'); m.object = arm
bpy.ops.export_scene.gltf(filepath=a[2], export_format='GLB')
print('RIG_DONE', a[2])
