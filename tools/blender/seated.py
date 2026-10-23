"""Renders a fitted character (out.glb or out_lod<n>.glb) in a rough kart pose, to check parts
that only show up seated (a cape through the floor).

    blender -b --python tools/blender/seated.py -- model.glb atlas.png out.png [view: side|back|quarter]

Thighs turned to point forward, calves forward-down to the pedals, upper arms forward to the
wheel. The game faces +X, left is +Y.
"""
import math
import sys

import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index('--') + 1:]
view = a[3] if len(a) > 3 else 'side'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a[0])
img = bpy.data.images.load(a[1])
for m in bpy.data.materials:
    nt = m.node_tree
    b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if b and not any(n.type == 'TEX_IMAGE' for n in nt.nodes):
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')


def turn(name, axis, degrees):
    """Turns a pose bone about a world axis through its head (children follow)."""
    pb = arm.pose.bones.get(name)
    if pb is None:
        return
    bpy.context.view_layer.update()
    head = pb.matrix.to_translation()
    r = Matrix.Translation(head) @ Matrix.Rotation(math.radians(degrees), 4, axis) @ Matrix.Translation(-head)
    pb.matrix = r @ pb.matrix


for s in 'LR':
    turn(f'Bone_{s}_Thigh', 'Y', -85)   # thigh forward (down -> +X)
    turn(f'Bone_{s}_Calf', 'Y', 45)     # calf down and forward, as on the pedals
    turn(f'Bone_{s}_UpperArm', 'Y', -45)
bpy.context.view_layer.update()
bpy.ops.object.mode_set(mode='OBJECT')

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.color_type = 'TEXTURE'
sc.display.shading.show_backface_culling = True  # as the game: a lining poking through shows
sc.render.resolution_x = sc.render.resolution_y = 600
sc.world = bpy.data.worlds.new('w')
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c'))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 2.2
sc.collection.objects.link(cam)
sc.camera = cam
target = Vector((0, 0, 0.9))
cam.location = target + {'side': Vector((0, 3, 0.2)), 'back': Vector((-3, 0, 0.3)),
                         'quarter': Vector((-2, 2.2, 0.6))}[view]
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
# The seat and floor of a kart, roughly, to see what goes through them.
bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0.95))
sc.render.filepath = a[2]
bpy.ops.render.render(write_still=True)
