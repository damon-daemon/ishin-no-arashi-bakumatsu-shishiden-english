#!/usr/bin/env python3
"""Review-pass helpers for the program strings (as rdiff.py / tmshift.py for the events).
SNAP_DIR = folder holding snap/progstr, the copy of tl/progstr made before the wave.

  prdiff.py diff [-q] FILE...   Japanese / old / new of every changed or new line of these tl files
  prdiff.py shift [--pin]       strings covered by the translation memory whose English changed:
                                SHIFT = another string became the memory's source (--pin writes the
                                old English as the string's own line into tl/progstr/95_pins.txt),
                                edit = the source line itself was edited (all its users follow)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import progstr as p

SNAP = os.path.join(os.environ.get('SNAP_DIR', '.'), 'snap', 'progstr')


def main(a):
    old, new = p.load_tl(SNAP), p.load_tl()
    rs = [r for r in p.rows() if r['ui']]
    jp = {r['key']: r['jp'] for r in rs}
    if a[0] == 'diff':
        q = '-q' in a
        for fn in [x for x in a[1:] if x != '-q']:
            keys = [k for k in p.load_tl_file(os.path.join(p.TL, os.path.basename(fn))) if old.get(k) != new[k]]
            print('##### %s: %d changed (%d new own lines)' % (fn, len(keys), sum(k not in old for k in keys)))
            if not q:
                ro = p.resolved(old, rs)
                for k in keys:
                    print('%s\n  JP  %s\n  old %s\n  new %s' % (k, p.vis(jp.get(k, '')).replace('\n', '\\n'),
                          ro.get(k, old.get(k, '')).replace('\n', '\\n'), new[k].replace('\n', '\\n')))
    elif a[0] == 'shift':
        ro, rn = p.resolved(old, rs), p.resolved(new, rs)
        src = lambda tl: {jp[k]: k for k in reversed(list(tl)) if tl[k] != '-' and k in jp}
        so, sn = src(old), src(new)
        pins = []
        for r in rs:
            k = r['key']
            if k in new or ro.get(k) == rn.get(k):
                continue
            if so.get(jp[k]) != sn.get(jp[k]):
                print('SHIFT %s  %r\n   was %r (%s)\n   now %r (%s)' % (k, jp[k], ro.get(k), so.get(jp[k]), rn.get(k), sn.get(jp[k])))
                pins.append((k, ro[k]))
            else:
                print('edit  %s  %r: %r -> %r (%s)' % (k, jp[k], ro.get(k), rn.get(k), sn.get(jp[k])))
        if '--pin' in a and pins:
            path = os.path.join(p.TL, '95_pins.txt')
            head = '' if os.path.exists(path) else '# review pass: strings that keep their earlier shared English after another string with the same Japanese got its own line\n'
            open(path, 'a', encoding='utf-8').write(head + ''.join('%s\t%s\n' % (k, v.replace('\n', '\\n')) for k, v in pins))
            print('pinned', len(pins))


if __name__ == '__main__':
    main(sys.argv[1:]) if len(sys.argv) > 1 else print(__doc__)
