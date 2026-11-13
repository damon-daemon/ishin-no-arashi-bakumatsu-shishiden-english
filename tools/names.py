"""Person names (program table): dump the Japanese, insert the English from tl/names/persons.txt.

The person table of SLPM_861.44 has 599 records of 0xc0 bytes; the record number is the person
id of the event scripts (83 = Sakamoto Ryoma, 122 = Chiba Jutaro, 401 = the player's own
character). Five string pointers per record, first one at NAMES + 0xc0 * id:
    surname, given name, alias surname, alias given name, nickname ("Ryo-san": used by friends)
(alias = the false name some persons travel under; empty strings for most).
The game joins surname and given name with the format "%s%s" at FULLFMT (7 users, all name
joins of the person classes; a 12-byte slot): patched to "%s %s".

tl/names/persons.txt (our English only):   id|surname|given|alias surname|alias given|nickname
  '#' lines are comments; a field left empty keeps the Japanese string; '-' = empty string.
English strings go into POOL (the unused block of the program also used by vwf.py's code).

  python3 tools/names.py dump [from] [to]     Japanese names (tab-separated)
  python3 tools/names.py check                validate tl/names/persons.txt, pool use
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import text, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, 'extract', 'SLPM_861.44')
TL = os.path.join(ROOT, 'tl', 'names', 'persons.txt')
NAMES, COUNT, STRIDE, FIELDS = 0x800ee09c, 599, 0xc0, 5
FULLFMT = 0x8003af98
POOL = (vwf.CAVE + 0x400, 0x800d3150)       # the first 1 KB of the cave is kept for code
off = lambda va: va - 0x80010000 + 0x800


def cstr(d, va):
    if not va:                      # alias fields of most persons are null pointers
        return b''
    o = off(va)
    return d[o:d.index(b'\0', o)]


def japanese(d=None):
    """-> [[5 strings]] by person id."""
    d = d if d is not None else open(EXE, 'rb').read()
    return [[cstr(d, p).decode('cp932') for p in struct.unpack_from('<5I', d, off(NAMES + STRIDE * i))]
            for i in range(COUNT)]


def load(path=TL):
    """-> ({id: [5 fields or None]}, errors)"""
    out, errs = {}, []
    if not os.path.exists(path):
        return out, errs
    for n, ln in enumerate(open(path, encoding='utf-8'), 1):
        ln = ln.rstrip('\n')
        if not ln.strip() or ln.startswith('#'):
            continue
        f = ln.split('|')
        if len(f) != FIELDS + 1 or not f[0].strip().isdigit() or int(f[0]) >= COUNT:
            errs.append('%s:%d: expected id|surname|given|alias surname|alias given|nickname' % (path, n))
            continue
        i = int(f[0])
        if i in out:
            errs.append('%s:%d: person %d twice' % (path, n, i))
        vals = []
        for v in f[1:]:
            v = v.strip()
            es = text.check(v) if v not in ('', '-') else []
            errs += ['%s:%d: %s' % (path, n, e) for e in es]
            vals.append(None if v == '' else '' if v == '-' else v)
        out[i] = vals
    return out, errs


def patch(exe):
    """PS-X EXE bytes -> with the English names (no change without tl/names/persons.txt)."""
    recs, errs = load()
    if errs:
        sys.exit('\n'.join(errs))
    if not recs:
        return exe
    d = bytearray(exe)
    at, pool = POOL[0], {}
    assert not any(d[off(POOL[0]):off(POOL[1])]), 'name pool is not empty'
    for i, vals in sorted(recs.items()):
        for k, v in enumerate(vals):
            if v is None:
                continue
            b = text.fold(v).encode('ascii') + b'\0'
            if b not in pool:
                if at + len(b) > POOL[1]:
                    sys.exit('names: pool full (%d bytes)' % (POOL[1] - POOL[0]))
                d[off(at):off(at) + len(b)] = b
                pool[b] = at
                at += len(b)
            struct.pack_into('<I', d, off(NAMES + STRIDE * i + 4 * k), pool[b])
    assert d[off(FULLFMT):off(FULLFMT) + 12] == b'%s%s' + bytes(8)
    d[off(FULLFMT):off(FULLFMT) + 6] = b'%s %s\0'
    patch.used = at - POOL[0]
    return bytes(d)


def main(a):
    if not a:
        sys.exit(__doc__)
    if a[0] == 'dump':
        jp = japanese()
        lo, hi = (int(a[1]) if len(a) > 1 else 0), (int(a[2]) if len(a) > 2 else COUNT - 1)
        for i in range(lo, hi + 1):
            print('%d\t%s' % (i, '\t'.join(jp[i])))
    elif a[0] == 'check':
        recs, errs = load()
        if errs:
            sys.exit('\n'.join(errs))
        patch(open(EXE, 'rb').read())
        print('%d of %d persons, pool %d / %d bytes' % (len(recs), COUNT, getattr(patch, 'used', 0),
                                                         POOL[1] - POOL[0]))


if __name__ == '__main__':
    main(sys.argv[1:])
