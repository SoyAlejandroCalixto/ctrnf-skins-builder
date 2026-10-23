import bpy,sys
a=sys.argv[sys.argv.index('--')+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=a[0])
o=next(o for o in bpy.data.objects if o.type=='MESH')
pts=[o.matrix_world@v.co for v in o.data.vertices]
def c(s):
    return '(%.3f %.3f %.3f) n%d y[%.2f %.2f] x[%.2f %.2f]'%(sum(p.x for p in s)/len(s),sum(p.y for p in s)/len(s),sum(p.z for p in s)/len(s),len(s),min(p.y for p in s),max(p.y for p in s),min(p.x for p in s),max(p.x for p in s)) if s else '-'
for z0 in [0.17+i*0.04 for i in range(0,32)]:
    s=[p for p in pts if z0<=p.z<z0+0.02]
    # split at the largest y gap
    ys=sorted(p.y for p in s);gap=max(((ys[i+1]-ys[i],(ys[i+1]+ys[i])/2) for i in range(len(ys)-1)),default=(0,0))
    if gap[0]>0.02:
        l=[p for p in s if p.y<gap[1]];r=[p for p in s if p.y>=gap[1]]
        print('z %.2f A %s | B %s'%(z0,c(l),c(r)))
    else:print('z %.2f one %s'%(z0,c(s)))
