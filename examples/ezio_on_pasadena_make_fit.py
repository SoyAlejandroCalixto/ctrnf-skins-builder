"""Writes fit.json for Ezio (XNALara bone names) on Pasadena O'Possum."""
import json
import sys
from pathlib import Path
here = Path(__file__).resolve().parent
# Size: thickness and rigid parts (head, hands, feet); Pasadena is about 1.11 times Ezio's height
# (head joint 1.692 / 1.52), so 1.11 keeps him in proportion.
SIZE = float(sys.argv[1]) if len(sys.argv) > 1 else 1.11
OUT = sys.argv[2] if len(sys.argv) > 2 else 'fit.json'
seg = {}
def side(s, S):
    a, g = f'arm {s} ', f'leg {s} '
    seg[a + 'shoulder 02'] = {'bone': f'Bone_{S}_UpperArm', 'from': [a + 'shoulder 02', a + 'elbow'], 'to': [f'Bone_{S}_UpperArm', f'Bone_{S}_Forearm']}
    seg[a + 'elbow'] = {'bone': f'Bone_{S}_Forearm', 'from': [a + 'elbow', a + 'wrist'], 'to': [f'Bone_{S}_Forearm', f'Bone_{S}_Hand']}
    seg[a + 'wrist'] = {'bone': f'Bone_{S}_Hand', 'rigid': SIZE, 'from': [a + 'wrist'], 'to': [f'Bone_{S}_Hand'],
                        'align_from': [a + 'wrist', a + 'finger 3a'], 'align': [f'Bone_{S}_Hand', f'Bone_{S}_Middle']}
    seg[g + 'thigh'] = {'bone': f'Bone_{S}_Thigh', 'from': [g + 'thigh', g + 'knee'], 'to': [f'Bone_{S}_Thigh', f'Bone_{S}_Calf']}
    seg[g + 'knee'] = {'bone': f'Bone_{S}_Calf', 'from': [g + 'knee', g + 'ankle'], 'to': [f'Bone_{S}_Calf', f'Bone_{S}_Foot']}
    # Pasadena's feet point down (heels): the boot follows her Foot->Toe0 so its tip reaches the pedal.
    seg[g + 'ankle'] = {'bone': f'Bone_{S}_Foot', 'rigid': SIZE, 'from': [g + 'ankle'], 'to': [f'Bone_{S}_Foot'],
                        'align_from': [g + 'ankle', g + 'toes'], 'align': [f'Bone_{S}_Foot', f'Bone_{S}_Toe0']}
seg['root hips'] = {'bone': 'Bone_Pelvis', 'from': ['pelvis', 'head neck lower'], 'to': ['Bone_Pelvis', 'Bone_Neck']}
seg['head neck lower'] = {'bone': 'Bone_Neck', 'from': ['head neck lower', 'head neck upper'], 'to': ['Bone_Neck', 'Bone_Head']}
seg['head neck upper'] = {'bone': 'Bone_Head', 'rigid': SIZE, 'from': ['head neck upper'], 'to': ['Bone_Head']}
side('left', 'L')
side('right', 'R')
# The cape, seated: it follows the spine and ends at the belt (cut straight across
# by xps_import.py --cut='cape :1.08' --unweight='cape :arm left upper,arm left shoulder 02' (the arm
# pulled it into a fold when reaching for the wheel), and the sash's tails at 0.9 '--cut=belt :0.9', on the
# pelvis: below the seat they showed under it; cut by bones its two layers ended at different heights, in strips). On
# the thigh it went into the leg; down to the hip it hung through the kart's floor.
CAPE = {'cape 1a': 'Bone_Spine4', 'cape 2a': 'Bone_Spine4', 'cape 3a': 'Bone_Spine3',
        'cape 1b': 'Bone_Spine2', 'cape 2b': 'Bone_Spine2', 'cape 1c': 'Bone_Spine2', 'cape 2c': 'Bone_Spine2',
        'cape 3b': 'Bone_Spine2', 'cape 1d': 'Bone_Spine2', 'cape 2d': 'Bone_Spine2', 'cape 3c': 'Bone_Spine2'}
bones = {**CAPE, 'pelvis': 'Bone_Pelvis', 'spine lower 01': 'Bone_Spine1', 'spine lower 02': 'Bone_Spine2',
         'spine middle': 'Bone_Spine3', 'spine upper': 'Bone_Spine4', 'spine shoulders': 'Bone_Spine4',
         'head neck middle': 'Bone_Neck', 'arm left shoulder 01': 'Bone_L_Clavicle',
         'arm right shoulder 01': 'Bone_R_Clavicle', 'leg left toes': 'Bone_L_Toe0', 'leg right toes': 'Bone_R_Toe0'}
fit = {'model': (here.parent / 'ezio' / 'ezio_src_cut.glb').as_posix(), 'rotate_z': 90, 'radial_scale': SIZE,
       'by_position': ['skirt'],
       # lods: 0.9, as the per-face UVs after reduction split vertices (the build checks the counts).
       'weld': 0.00001, 'atlas': {'slot': 'UpperBody', 'size': 2048},
       'lods': [int(n * f) for n, f in zip([18550, 10340, 10152, 4962, 3059], [0.85, 0.8, 0.8, 0.76, 0.8])], 'segments': seg, 'bones': bones}
(here / OUT).write_text(json.dumps(fit, indent=1))
