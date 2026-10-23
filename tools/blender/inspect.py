import bpy, sys
from mathutils import Vector
argv = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
for path in argv:
    if path.endswith('.fbx'):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
for o in bpy.data.objects:
    print('OBJ', o.name, o.type, 'parent', o.parent.name if o.parent else None, 'loc', tuple(round(x, 3) for x in o.location),
          'rot', tuple(round(x, 3) for x in o.rotation_euler), 'scale', tuple(round(x, 3) for x in o.scale))
    if o.type == 'MESH':
        me = o.data
        ws = [o.matrix_world @ v.co for v in me.vertices]
        lo = [min(w[i] for w in ws) for i in range(3)]; hi = [max(w[i] for w in ws) for i in range(3)]
        print('   verts', len(me.vertices), 'faces', len(me.polygons), 'bbox', [round(x, 3) for x in lo], [round(x, 3) for x in hi])
        print('   materials', [m.name if m else None for m in me.materials])
        print('   uv', [u.name for u in me.uv_layers], 'colors', [c.name for c in me.color_attributes])
        print('   groups', [g.name for g in o.vertex_groups][:80])
        print('   modifiers', [(m.type, getattr(m, 'object', None) and m.object.name) for m in o.modifiers])
    if o.type == 'ARMATURE':
        for b in o.data.bones:
            h = o.matrix_world @ b.head_local; t = o.matrix_world @ b.tail_local
            print('   BONE', b.name, 'parent', b.parent.name if b.parent else None, 'head', [round(x, 3) for x in h], 'tail', [round(x, 3) for x in t])
for m in bpy.data.materials:
    imgs = []
    if m.use_nodes:
        imgs = [n.image.filepath for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]
    print('MAT', m.name, imgs)
