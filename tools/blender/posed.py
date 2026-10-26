"""Renders game-skeleton models (the driver's export, blender_fit's out.glb) in a frame of the
driver's real animation (anims/Drivers/<driver>.hka, read by tools/hka.py): the kart pose.

    blender -b --python tools/blender/posed.py -- <archives> <character> <animation> <frame> <out.png> <view> <glb>[=atlas.png] ... [--kart=<kart.glb>]

view: side (from the left), front, back, quarter, top, or side:<ortho>:<x,y,z> to frame a part
(ortho size and target in the posed space; the game faces +X, left is +Y, up is Z). One glb
renders opaque; several render see-through, the first red, the next ones blue / green. A
glb=atlas.png renders with that image, as the game does. race_driver_idle frame 0 is the pose
at character select. --kart: a kart exported from actors/Karts (gray, unposed), the drivers
moved onto its Bone_Rider, to see the hands on the wheel and the feet on the pedals.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hka  # noqa: E402

a = sys.argv[sys.argv.index('--') + 1:]
archives, character, animation, frame, out, view = a[:6]
models = [m for m in a[6:] if not m.startswith('--')]
kart = next((m.split('=', 1)[1] for m in a[6:] if m.startswith('--kart=')), None)
skeleton, anims = hka.driver(archives, character)
anim, tracks = anims[animation]
skin = hka.skinning(skeleton, hka.pose(skeleton, anim, tracks, int(frame)))

bpy.ops.wm.read_factory_settings(use_empty=True)
rider = Vector()
if kart:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=kart)
    for o in set(bpy.data.objects) - before:
        o.color = (0.6, 0.6, 0.6, 1)
        if o.type == 'ARMATURE':
            rider = o.matrix_world @ o.data.bones['Bone_Rider'].head_local
        if o.type == 'MESH' and o.parent is None:
            bpy.data.objects.remove(o)
colors = [(1, 0.25, 0.2, 1), (0.2, 0.45, 1, 1), (0.2, 0.9, 0.3, 1)]
for k, spec in enumerate(models):
    path, _, atlas = spec.partition('=')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = set(bpy.data.objects) - before
    for o in new:
        o.color = colors[k % 3]
    if atlas:
        img = bpy.data.images.load(atlas)
        for o in new:
            for m in (o.data.materials if o.type == 'MESH' else []):
                nt = m.node_tree
                b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if b and not any(n.type == 'TEX_IMAGE' for n in nt.nodes):
                    t = nt.nodes.new('ShaderNodeTexImage')
                    t.image = img
                    nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    arm = next(o for o in new if o.type == 'ARMATURE')
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    w = arm.matrix_world
    for pb in arm.pose.bones:  # parents come first
        m = skin.get(pb.name)
        if m is None:
            continue
        pb.matrix = w.inverted() @ Matrix(m) @ w @ pb.bone.matrix_local
        bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.location += rider

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.color_type = 'TEXTURE' if len(models) == 1 and '=' in models[0] else 'OBJECT'
sc.display.shading.show_backface_culling = len(models) == 1
if len(models) > 1:
    sc.display.shading.show_xray = True
    sc.display.shading.xray_alpha = 0.55
sc.render.resolution_x = sc.render.resolution_y = 700
sc.world = bpy.data.worlds.new('w')
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c'))
cam.data.type = 'ORTHO'
sc.collection.objects.link(cam)
sc.camera = cam
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
pts = [o.matrix_world @ v.co for o in bpy.data.objects if o.type == 'MESH'
       for v in o.evaluated_get(deps).to_mesh().vertices]
lo = Vector([min(p[i] for p in pts) for i in range(3)])
hi = Vector([max(p[i] for p in pts) for i in range(3)])
name, *frame_part = view.split(':')
target, size = (lo + hi) / 2, max(hi - lo) * 1.15
if frame_part:
    size, target = float(frame_part[0]), Vector(eval('(' + frame_part[1] + ')'))
cam.data.ortho_scale = size
d = {'side': (0, 1, 0), 'front': (1, 0, 0), 'back': (-1, 0, 0), 'quarter': (1, 1, 0.5),
     'top': (0, 0, 1)}[name]
cam.location = target + Vector(d).normalized() * 5
up = 'Y' if name != 'top' else 'X'
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y' if name != 'top' else 'X').to_euler()
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
