"""Dry-run of what the OCTR launcher does at launch with the enabled mods: scans the mods
folder, enables every mod found (patches.json) and prepares the overlays for the game in the
launcher's game_dir (launcher.ini), without starting the game. Uses the portable's own Python
and scripts.

    python check_launcher.py <portable folder> [--no-enable]

Prints the mods found, any error and the mod session line. Fails ("A mod session is already
running") while the game is open.
"""
import subprocess
import sys
from pathlib import Path

CODE = r'''
import sys, os, json
sys.path.insert(0, '.')
from pathlib import Path
import mod_library as L, mod_packages, game_check
r = L.scan(Path('../mods'), Path('../patches'))
print('Mods:', list(r['entries']), 'messages:', r['messages'])
if ENABLE:
    p = Path('../patches.json')
    d = json.loads(p.read_text()) if p.exists() else {'enabled': [], 'disabled': []}
    d['enabled'] = sorted(set(d['enabled']) | {'OCTR-Mod-Library.xml/Mod: ' + k for k in r['entries']})
    d['disabled'] = [k for k in d.get('disabled', []) if k not in d['enabled']]
    p.write_text(json.dumps(d, indent=2))
port = Path('..').resolve()
ini = port / 'launcher.ini'
dirs = [l.split('=', 1)[1].strip() for l in (ini.read_text(encoding='utf-8').splitlines() if ini.exists() else [])
        if l.startswith('game_dir=')]
game = Path(dirs[0]) if dirs else next(d for d in port.iterdir() if d.is_dir() and (d / 'eboot.bin').exists())
title = 'CUSA13795'
env = dict(os.environ)
mod_packages.prepare(port, port, env, game, port / 'bbport.ini', prepare_only=True,
                     title_id=title, app_version='01.21')
plan = json.loads(Path(env['BB_MOD_ARCHIVE_PLAN']).read_text())
print('OK:', len(plan), 'archive entries replaced')
'''


def main(portable, *flags):
    portable = Path(portable)
    code = CODE.replace('ENABLE', 'False' if '--no-enable' in flags else 'True')
    out = subprocess.run([str(portable / 'python' / 'python.exe'), '-I', '-c', code],
                         cwd=portable / 'scripts', capture_output=True, text=True, encoding='utf-8',
                         errors='replace')
    lines = (out.stdout + out.stderr).splitlines()
    keep = [l for l in lines if l.startswith(('Mods:', 'OK:', 'OCTR mod session', 'Traceback'))
            or 'Error' in l or 'error' in l]
    print('\n'.join(keep) or '\n'.join(lines[-20:]))
    sys.exit(out.returncode)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:])
