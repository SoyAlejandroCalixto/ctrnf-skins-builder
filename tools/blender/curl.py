"""Bends the fingers of a model into a fist-like grip and saves it as a new bind pose, so that the
hands close on the wheel whatever the driver's animation does with its own fingers (quadrupeds
such as Pura only have toes, other drivers' fingers barely close).

    blender -b --python tools/blender/curl.py -- <model .fbx/.glb> <out.glb> <degrees> <finger> ... [--palm=x,y,z] [--thumb=<bone>:<degrees>]

<finger> names a chain by its first bone with {s} for the side, e.g. index_01_{s} (sides l, r)
or LeftHandIndex1 written as {S}HandIndex1 (sides Left, Right): that bone and every descendant
turn <degrees> about the axis across the palm (first finger's base to the last one's), so the
whole finger curls by <degrees> times its number of joints, towards the palm: --palm is the
direction the left palm faces in model space (default 0,0,-1, palms down; mirrored in X for the
right hand). FBX bone tails are guesses, so it is not taken from the bones: check with a render.
--thumb turns the thumb chain (by its first bone) about the finger direction instead.
"""
import math
import sys

import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index('--') + 1:]
src, out, degrees = a[0], a[1], float(a[2])
fingers = [x for x in a[3:] if not x.startswith('--')]
thumb = next((x.split('=', 1)[1] for x in a[3:] if x.startswith('--thumb=')), None)
palm_hint = next((tuple(map(float, x.split('=', 1)[1].split(','))) for x in a[3:] if x.startswith('--palm=')),
                 (0, 0, -1))

bpy.ops.wm.read_factory_settings(use_empty=True)
if src.lower().endswith('.fbx'):
    bpy.ops.import_scene.fbx(filepath=src)
else:
    bpy.ops.import_scene.gltf(filepath=src)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
W = arm.matrix_world


def head(name):
    bpy.context.view_layer.update()
    return W @ arm.pose.bones[name].matrix.to_translation()


def turn(name, axis, deg, pivot=None):
    """Turns a pose bone and its children about a world axis through its head."""
    pb = arm.pose.bones[name]
    bpy.context.view_layer.update()
    p = W.inverted() @ (pivot if pivot is not None else head(name))
    ax = (W.inverted().to_3x3() @ axis).normalized()
    r = Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, ax) @ Matrix.Translation(-p)
    pb.matrix = r @ pb.matrix


def chain(first):
    out, bone = [], arm.pose.bones[first]
    while bone is not None:
        out.append(bone.name)
        kids = [c for c in bone.children if not c.name.endswith('_end')]
        bone = kids[0] if kids else None
    return out


for side, Side in (('l', 'Left'), ('r', 'Right')):
    names = [f.format(s=side, S=Side) for f in fingers]
    names = [n for n in names if n in arm.pose.bones]
    if not names:
        continue
    across = head(names[-1]) - head(names[0])
    along = sum((head(chain(n)[1]) - head(n) for n in names), Vector()).normalized()
    across = (across - along * across.dot(along)).normalized()
    palm = along.cross(across)
    ref = Vector(palm_hint) if side == 'l' else Vector((-palm_hint[0], palm_hint[1], palm_hint[2]))
    if palm.dot(ref) < 0:
        palm = -palm
    # Positive turn about axis takes `along` towards `palm`.
    axis = across if along.cross(palm).dot(across) > 0 else -across
    for n in names:
        for bone in chain(n):
            turn(bone, axis, degrees)
    if thumb:
        t, deg = thumb.rsplit(':', 1)
        t = t.format(s=side, S=Side)
        if t in arm.pose.bones:
            for bone in chain(t):
                turn(bone, along if side == 'l' else -along, float(deg))
    print(f'{Side}: along {tuple(round(x, 2) for x in along)}, palm {tuple(round(x, 2) for x in palm)}')

bpy.context.view_layer.update()
bpy.ops.object.mode_set(mode='OBJECT')
# Bake the pose into the meshes and make it the bind pose.
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    mod = next((m for m in o.modifiers if m.type == 'ARMATURE'), None)
    if mod is None:
        continue
    bpy.context.view_layer.objects.active = o
    if o.data.shape_keys:
        bpy.ops.object.shape_key_remove(all=True, apply_mix=False)
    name = mod.name
    bpy.ops.object.modifier_copy(modifier=name)
    bpy.ops.object.modifier_apply(modifier=name)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.armature_apply()
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_animations=False, export_yup=True)
print('CURL_DONE', out)
