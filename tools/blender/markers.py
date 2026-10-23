import bpy,sys,json
from mathutils import Vector
a=sys.argv[sys.argv.index('--')+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=a[0])
img=bpy.data.images.load(a[1])
for m in bpy.data.materials:
    nt=m.node_tree;b=next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'),None)
    t=nt.nodes.new('ShaderNodeTexImage');t.image=img;nt.links.new(t.outputs['Color'],b.inputs['Base Color'])
red=bpy.data.materials.new('red');red.diffuse_color=(1,0,0,1)
for n,p in json.load(open(a[2])).items():
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.018,location=p);s=bpy.context.object;s.data.materials.append(red);s.show_in_front=True
sc=bpy.context.scene;sc.render.engine='BLENDER_WORKBENCH';sc.display.shading.color_type='TEXTURE';sc.display.shading.show_xray=True;sc.display.shading.xray_alpha=0.6
sc.render.resolution_x=sc.render.resolution_y=800;sc.world=bpy.data.worlds.new('w')
cam=bpy.data.objects.new('c',bpy.data.cameras.new('c'));cam.data.type='ORTHO';cam.data.ortho_scale=1.75
sc.collection.objects.link(cam);sc.camera=cam;c=Vector((0,0,0.85))
for name,off in (('front',Vector((1,0,0))),('side',Vector((0,-1,0))),('top',Vector((0,0,1)))):
    cam.location=c+off*4;cam.rotation_euler=(-off).to_track_quat('-Z','Y').to_euler()
    sc.render.filepath=a[3]+f'/m_{name}.png';bpy.ops.render.render(write_still=True)
