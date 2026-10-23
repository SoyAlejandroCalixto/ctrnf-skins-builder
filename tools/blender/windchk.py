import bpy,sys,mathutils,bmesh
a=sys.argv[sys.argv.index('--')+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a[0])
o=next(o for o in bpy.data.objects if o.type=='MESH' and o.data.uv_layers and o.parent)
me=o.data
# ray test: from far outside along normal; a face is outward if a ray cast from slightly outside along -normal hits it first
from mathutils.bvhtree import BVHTree
bvh=BVHTree.FromObject(o,bpy.context.evaluated_depsgraph_get())
out=inw=0
import random
ps=list(me.polygons);random.seed(1)
for p in random.sample(ps,min(3000,len(ps))):
    n=p.normal;c=p.center
    hit=bvh.ray_cast(c+n*1e-4,n)  # anything in front of the face along its normal?
    hit2=bvh.ray_cast(c-n*1e-4,-n)
    if hit[0] is None: out+=1
    elif hit2[0] is None: inw+=1
print('faces facing open space:',out,'facing inward (open behind):',inw)
