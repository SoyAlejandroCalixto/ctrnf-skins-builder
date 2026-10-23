"""Blender: Ezio's hood colour map (FaceAcc4) all white, and the cape's lining brown.

    blender -b --python white_hood.py -- model.mesh in.tga out.tga

1. The red lining (top-left of the image) painted the white of the cloth, keeping the shading,
   and its dark patches plain white.
2. Every texel the hood's UVs do not cover takes the colour of the nearest covered one (24 px
   of padding): the reduced levels of detail move UVs a little past their island's border, and
   the dark texels around the hood showed as a dark red line along its seams.
"""
import sys
from pathlib import Path

import bpy
import numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import xps  # noqa: E402

a = sys.argv[sys.argv.index('--') + 1:]
im = bpy.data.images.load(a[1])
w, h = im.size
p = numpy.array(im.pixels[:]).reshape(h, w, 4)  # rows bottom first

region = p[int(h * 0.59):, :int(w * 0.62)]      # the image's top 41 %, left 62 %: the hood
r, g, b = region[..., 0], region[..., 1], region[..., 2]
red = (r > 1.8 * g) & (r > 1.8 * b) & (r > 0.05)
cloth = region[(abs(r - g) < 0.04) & (abs(g - b) < 0.04) & (r > 0.3)][:, :3]
lum = 0.3 * r + 0.59 * g + 0.11 * b
grey = numpy.clip(cloth.mean() + (lum - lum[red].mean()) * 1.5, 0, 1)
for k in range(3):
    region[..., k][red] = grey[red]
print('lining pixels', int(red.sum()))
# The lining's dark parts (the brown patch in its middle, the notch at the peak: image rows
# 0-30 %, columns 3-33 %) show through the hood's seams on the reduced levels of detail.
inner = p[int(h * 0.70):, int(w * 0.03):int(w * 0.33)]
dark = (0.3 * inner[..., 0] + 0.59 * inner[..., 1] + 0.11 * inner[..., 2]) < 0.35
inner[..., :3][dark] = cloth.mean(0) * 0.85
print('dark lining pixels', int(dark.sum()))
# The cape's red lining (the image's lower 58 %) the brown of its outside: the two layers lie so
# close that the lining showed through the back in red cracks.
cape = p[:int(h * 0.58)]
r, g, b = cape[..., 0], cape[..., 1], cape[..., 2]
lining = (r > 1.6 * g) & (r > 1.6 * b) & (r > 0.08)
outside = cape[~lining & (r > g) & (g > b) & (r < 0.6) & (r > 0.1)][:, :3]
lum = 0.3 * r + 0.59 * g + 0.11 * b
tone = numpy.clip(1 + (lum - lum[lining].mean()) * 2, 0.6, 1.3)
for k in range(3):
    cape[..., k][lining] = (outside[:, k].mean() * tone)[lining]
print('cape lining pixels', int(lining.sum()), 'brown', outside.mean(0))

# Texels covered by the meshes that use this image.
model = xps.read(Path(a[0]).read_bytes())
covered = numpy.zeros((h, w), bool)
ys, xs = numpy.mgrid[0:h, 0:w]
for m in model['meshes']:
    if not m['textures'] or m['textures'][0][0] != Path(a[1]).name:
        continue
    uv = numpy.array(m['uvs'][0])
    # The texture repeats (these UVs lie in -16..-15); XPS v runs down, image rows run up.
    uv = numpy.stack([(uv[:, 0] % 1) * w, ((1 - uv[:, 1]) % 1) * h], 1)
    for t in m['triangles']:
        (x0, y0), (x1, y1), (x2, y2) = uv[list(t)]
        lo_x, hi_x = int(max(min(x0, x1, x2) - 1, 0)), int(min(max(x0, x1, x2) + 2, w))
        lo_y, hi_y = int(max(min(y0, y1, y2) - 1, 0)), int(min(max(y0, y1, y2) + 2, h))
        if lo_x >= hi_x or lo_y >= hi_y:
            continue
        px, py = xs[lo_y:hi_y, lo_x:hi_x] + 0.5, ys[lo_y:hi_y, lo_x:hi_x] + 0.5
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-9:
            continue
        l0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / d
        l1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / d
        inside = (l0 >= -0.02) & (l1 >= -0.02) & (1 - l0 - l1 >= -0.02)
        covered[lo_y:hi_y, lo_x:hi_x] |= inside
print('covered', round(covered.mean(), 3))

# Padding: grow the covered texels outwards, one ring at a time.
filled = covered.copy()
for _ in range(24):
    acc = numpy.zeros((h, w, 3))
    n = numpy.zeros((h, w))
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        f = numpy.roll(filled, (dy, dx), (0, 1))
        acc += numpy.roll(p[..., :3], (dy, dx), (0, 1)) * f[..., None]
        n += f
    ring = ~filled & (n > 0)
    p[..., :3][ring] = acc[ring] / n[ring][:, None]
    filled |= ring
print('padded', int((filled & ~covered).sum()))

im.pixels[:] = p.ravel()
im.filepath_raw = a[2]
im.file_format = 'TARGA'
im.save()
