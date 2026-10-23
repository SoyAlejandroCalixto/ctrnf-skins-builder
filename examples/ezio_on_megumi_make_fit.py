"""Writes fit.json for Ezio (XNALara bone names) on Megumi."""
import json
import sys
from pathlib import Path
here = Path(__file__).resolve().parent
# Size: thickness and rigid parts (head, hands, feet); Megumi is about 1.09 times Ezio's height
# (head joint 1.655 / 1.52), so 1.09 keeps him in proportion.
SIZE = float(sys.argv[1]) if len(sys.argv) > 1 else 1.09
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
    # Megumi's feet point down (heels): the boot follows her Foot->Toe0 so its tip reaches the pedal.
    seg[g + 'ankle'] = {'bone': f'Bone_{S}_Foot', 'rigid': SIZE, 'from': [g + 'ankle'], 'to': [f'Bone_{S}_Foot'],
                        'align_from': [g + 'ankle', g + 'toes'], 'align': [f'Bone_{S}_Foot', f'Bone_{S}_Toe0']}
seg['root hips'] = {'bone': 'Bone_Pelvis', 'from': ['pelvis', 'head neck lower'], 'to': ['Bone_Pelvis', 'Bone_Neck']}
seg['head neck lower'] = {'bone': 'Bone_Neck', 'from': ['head neck lower', 'head neck upper'], 'to': ['Bone_Neck', 'Bone_Head']}
seg['head neck upper'] = {'bone': 'Bone_Head', 'rigid': SIZE, 'from': ['head neck upper'], 'to': ['Bone_Head']}
side('left', 'L')
side('right', 'R')
bones = {'pelvis': 'Bone_Pelvis', 'spine lower 01': 'Bone_Spine1', 'spine lower 02': 'Bone_Spine2',
         'spine middle': 'Bone_Spine3', 'spine upper': 'Bone_Spine4', 'spine shoulders': 'Bone_Spine4',
         'head neck middle': 'Bone_Neck', 'arm left shoulder 01': 'Bone_L_Clavicle',
         'arm right shoulder 01': 'Bone_R_Clavicle', 'leg left toes': 'Bone_L_Toe0', 'leg right toes': 'Bone_R_Toe0'}
fit = {'model': (here.parent / 'ezio' / 'ezio_src.glb').as_posix(), 'rotate_z': 90, 'radial_scale': SIZE,
       'by_position': ['skirt', 'belt', 'cape'],  # the cape follows the thighs when seated
       # lods: 0.9, as the per-face UVs after reduction split vertices (the build checks the counts).
       # The cape's lower part (below the hip) went through the kart's floor with the game's longer torso.
       'drop_groups': ['cape 1e', 'cape 2e', 'cape 2f', 'cape 3d', 'cape 3e', 'cape 3f'], 'weld': 0.00001, 'atlas': {'slot': 'Outfit', 'size': 2048},
       'lods': [int(n * f) for n, f in zip([16768, 10692, 10443, 5611, 3505], [0.9, 0.84, 0.8, 0.76, 0.8])], 'segments': seg, 'bones': bones}
(here / OUT).write_text(json.dumps(fit, indent=1))
