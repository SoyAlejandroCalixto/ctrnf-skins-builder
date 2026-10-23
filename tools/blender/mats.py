import bpy,sys
a=sys.argv[sys.argv.index('--')+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=a[0])
keep=[o.name for o in bpy.data.objects if o.type=='MESH']
for m in bpy.data.materials:
    nt=m.node_tree;b=next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'),None)
    img=[n.image for n in nt.nodes if n.type=='TEX_IMAGE' and n.image]
    links=[(l.from_node.type,l.from_socket.name,l.to_socket.name) for l in nt.links]
    print('MAT',m.name,'base',[round(x,3) for x in b.inputs['Base Color'].default_value] if b else None,'alpha',b.inputs['Alpha'].default_value if b else None,'img',[(i.name,tuple(i.size),i.channels) for i in img],'links',links,'blend',m.blend_method)
for o in bpy.data.objects:
    if o.name not in keep: continue
    me=o.data;uv=me.uv_layers.active.data
    per={}
    for p in me.polygons:
        mn=me.materials[p.material_index].name
        for li in p.loop_indices:
            u,v=uv[li].uv;r=per.setdefault(mn,[9,9,-9,-9]);r[0]=min(r[0],u);r[1]=min(r[1],v);r[2]=max(r[2],u);r[3]=max(r[3],v)
    print('OBJ',o.name,{k:[round(x,2) for x in v] for k,v in per.items()}, 'colattr',[c.name for c in me.color_attributes])
