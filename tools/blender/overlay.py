"""blender -b --python tools/blender/overlay.py -- game.glb model.glb out.png view ortho "(x,y,z)" [rotY]
Overlays the game character (red) and the fitted model (blue), x-ray, in bind pose turned rotY
degrees about Y (Pura sits with -80)."""
import bpy, sys, math
from mathutils import Vector, Matrix
a = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
rot = float(a[6]) if len(a) > 6 else 0
for path, col in ((a[0], (1, 0.2, 0.2, 1)), (a[1], (0.2, 0.4, 1, 1))):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    for o in set(bpy.data.objects) - before:
        o.color = col
        if o.parent is None:
            o.matrix_world = Matrix.Rotation(math.radians(rot), 4, 'Y') @ o.matrix_world
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.color_type = 'OBJECT'
sc.display.shading.show_xray = True
sc.display.shading.xray_alpha = 0.55
sc.render.resolution_x = sc.render.resolution_y = 700
sc.world = bpy.data.worlds.new('w')
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c'))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = float(a[4])
sc.collection.objects.link(cam)
sc.camera = cam
t = Vector(eval(a[5]))
cam.location = t + {'side': Vector((0, 3, 0)), 'front': Vector((3, 0, 0)), 'top': Vector((0, 0, 3)),
                    'quarter': Vector((2, 2, 0.8))}[a[3]]
cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.render.filepath = a[2]
bpy.ops.render.render(write_still=True)
