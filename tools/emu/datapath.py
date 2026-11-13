"""Make an isolated DuckStation config dir for headless tests: build/dsh/duckstation
(run with XDG_CONFIG_HOME=build/dsh). Copies the user's settings.ini (read only), changes
what automation needs, links the BIOS folder (memory cards, states and screenshots stay
inside build/dsh).

Input is the keyboard only (keys sent by tools/emu/xkeys.py to gamescope's private X display);
SDL is off, so no real or virtual gamepad of another session reaches this emulator. The GDB
server uses its own port (the other projects use 2345).

usage: datapath.py [outdir]"""
import os, re, sys
USER = os.path.expanduser('~/.config/duckstation')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'dsh')
GDB_PORT = 2351
D = os.path.join(OUT, 'duckstation')
for sub in ('memcards', 'savestates', 'screenshots'):
    os.makedirs(os.path.join(D, sub), exist_ok=True)
if not os.path.islink(os.path.join(D, 'bios')):
    os.symlink(os.path.join(USER, 'bios'), os.path.join(D, 'bios'))
KEYS = {'Up': 'Up', 'Down': 'Down', 'Left': 'Left', 'Right': 'Right', 'Circle': 'X', 'Cross': 'Z',
        'Triangle': 'S', 'Square': 'A', 'Start': 'Return', 'Select': 'Backspace', 'L1': 'Q', 'R1': 'W',
        'L2': 'E', 'R2': 'R'}
REPLACE = {'Pad1': dict({k: 'Keyboard/%s' % v for k, v in KEYS.items()}, Type='DigitalController'),
           'Pad2': {'Type': 'None'},
           'Hotkeys': {'Screenshot': 'Keyboard/F10', 'SaveSelectedSaveState': 'Keyboard/F2',
                       'LoadSelectedSaveState': 'Keyboard/F1'},
           'InputSources': {'SDL': 'false', 'XInput': 'false', 'RawInput': 'false'}}   # whole sections
SET = {'Main': {'ConfirmPowerOff': 'false', 'SaveStateOnExit': 'false', 'CreateSaveStateBackups': 'false',
                'PauseOnFocusLoss': 'false', 'StartFullscreen': 'false', 'SetupWizardIncomplete': 'false'},
       'AutoUpdater': {'CheckAtStartup': 'false'},
       'GPU': {'ResolutionScale': '1', 'Renderer': 'Software'},
       'Display': {'ScreenshotMode': 'InternalResolution', 'ScreenshotFormat': 'PNG'},
       'Debug': {'EnableGDBServer': 'true', 'GDBServerPort': str(GDB_PORT)},
       'Hacks': {'ExportSharedMemory': 'true'},
       'Audio': {'Backend': 'Null'},
       'GameList': {'RecursivePaths': '', 'Paths': ''},
       'Logging': {'LogLevel': 'Info', 'LogToFile': 'true', 'LogToConsole': 'true'}}
SET.update(REPLACE)
ini = open(os.path.join(USER, 'settings.ini'), encoding='utf-8').read()
out, sec, seen = [], None, set()
for line in ini.splitlines():
    m = re.match(r'\[(.+)\]$', line)
    if m:
        sec = m.group(1)
        seen.add(sec)
        out.append(line)
        out += ['%s = %s' % kv for kv in SET.get(sec, {}).items()]
        continue
    k = line.split('=')[0].strip()
    if sec in REPLACE or k in SET.get(sec, {}):
        continue
    out.append(line)
for s in SET:
    if s not in seen:
        out += ['', '[%s]' % s] + ['%s = %s' % kv for kv in SET[s].items()]
open(os.path.join(D, 'settings.ini'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print(D)
