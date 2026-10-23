import bpy,sys
from mathutils import Vector
a=sys.argv[sys.argv.index('--')+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a[0])
img=bpy.data.images.load(a[1])
for m in bpy.data.materials:
    nt=m.node_tree;b=next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if b and not any(n.type=='TEX_IMAGE' for n in nt.nodes):
        t=nt.nodes.new('ShaderNodeTexImage');t.image=img;nt.links.new(t.outputs['Color'],b.inputs['Base Color'])
sc=bpy.context.scene;sc.render.engine='BLENDER_WORKBENCH';sc.display.shading.color_type=a[5]
sc.render.resolution_x=sc.render.resolution_y=600;sc.world=bpy.data.worlds.new('w')
cam=bpy.data.objects.new('c',bpy.data.cameras.new('c'));cam.data.type='ORTHO';cam.data.ortho_scale=float(a[3])
sc.collection.objects.link(cam);sc.camera=cam
t=Vector(eval(a[4]));cam.location=t+Vector((1.5,0.4,0.1));cam.rotation_euler=(t-cam.location).to_track_quat('-Z','Y').to_euler()
sc.render.filepath=a[2];bpy.ops.render.render(write_still=True)
