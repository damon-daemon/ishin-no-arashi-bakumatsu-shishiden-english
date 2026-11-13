"""rdiff.py ARCHIVE/NNN ... : Japanese / old / new for every string a review worker changed."""
import sys, os, subprocess, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAP = os.path.join(os.environ.get('SNAP_DIR') or os.path.dirname(os.path.abspath(__file__)), 'snap', 'ev')   # copy of tl/ev made before the wave
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import tl

def recs(path):
    if not os.path.exists(path):
        return {}
    r = tl.parse_tl(path)
    return dict(r) if not isinstance(r, dict) else r

total = 0
for name in sys.argv[1:]:
    if name == '-q':
        continue
    old = recs(os.path.join(SNAP, name + '.txt'))
    new = recs(tl.tl_path(name))
    out = subprocess.run(['python3', os.path.join(ROOT, 'tools/tl.py'), 'show', name], capture_output=True, text=True, cwd=ROOT).stdout
    jp = {}
    for blk in out.split('\n\n'):
        m = re.match(r'@(\d+) (.*)\n([\s\S]*)', blk.strip('\n'))
        if m:
            jp[int(m.group(1))] = (m.group(2), m.group(3))
    ch = [k for k in sorted(set(old) | set(new), key=int) if old.get(k) != new.get(k)]
    total += len(ch)
    print('=== %s: %d changed of %d' % (name, len(ch), len(jp)))
    if '-q' in sys.argv:
        continue
    for k in ch:
        h, j = jp.get(int(k), ('?', '?'))
        print('@%s %s\n  JP : %s\n  OLD: %s\n  NEW: %s' % (k, h, j.replace('\n', '\\n'), old.get(k), new.get(k)))
print('total changed:', total)
