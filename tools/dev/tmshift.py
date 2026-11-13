"""tmshift.py [--pin]: shared (translation-memory) lines whose English changed because a string
earlier in the script order was given its own English. --pin writes the old English into every
affected string (batch files in pins/, applied with tl.py apply)."""
import sys, os, subprocess, collections
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.environ.get('SNAP_DIR') or os.path.dirname(os.path.abspath(__file__))   # folder holding snap/ev (a copy of tl/ev made before the wave)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import tl
names = tl.names()
scripts = {n: tl.Script(n) for n in names}
new = tl.load_tls()
old = {n: tl.parse_tl(os.path.join(HERE, 'snap', 'ev', n + '.txt')) for n in names}

def owners(tls):
    tm = {}
    for name, recs in tls.items():
        sc = scripts[name]
        for n, en in recs.items():
            if n < len(sc.jp):
                tm.setdefault((sc.op[n], sc.jp[n]), (en, name, n))
    return tm
to, tn = owners(old), owners(new)
keep = set(a for a in sys.argv[1:] if not a.startswith('--'))   # Japanese keys whose new shared line is accepted
pins = collections.defaultdict(dict)
rows = []
for key in tn:
    if key not in to or to[key][0] == tn[key][0]:
        continue
    oe, on, oi = to[key]; ne, nn, ni = tn[key]
    shifted = (nn, ni) != (on, oi)          # a new owner, not an edit of the old owner's line
    aff = [(n, i) for n in names for i, jp in enumerate(scripts[n].jp)
           if (scripts[n].op[i], jp) == key and i not in new[n]]
    rows.append((shifted, key[1], oe, on, oi, ne, nn, ni, aff))
    if shifted and key[1] not in keep:
        for n, i in aff:
            pins[n][i] = oe
for sh, jp, oe, on, oi, ne, nn, ni, aff in sorted(rows, key=lambda r: (not r[0], -len(r[8]))):
    print('%s %r x%d\n   old %s@%d: %s\n   new %s@%d: %s' % ('SHIFT' if sh else 'edit ', jp, len(aff), on, oi, oe, nn, ni, ne))
print(len(rows), 'keys;', sum(len(v) for v in pins.values()), 'strings to pin')
if '--pin' in sys.argv:
    os.makedirs(os.path.join(HERE, 'pins'), exist_ok=True)
    for n, d in pins.items():
        p = os.path.join(HERE, 'pins', n.replace('/', '_') + '.txt')
        open(p, 'w', encoding='utf-8').write(''.join('@%d\n%s\n\n' % (i, e) for i, e in sorted(d.items())))
        r = subprocess.run(['python3', 'tools/tl.py', 'apply', n, p], cwd=ROOT, capture_output=True, text=True)
        print(r.stdout.strip(), r.stderr.strip())
