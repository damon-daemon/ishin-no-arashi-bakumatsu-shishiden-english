#!/usr/bin/env python3
"""Short card titles on the debate card face (build step after progstr.apply).

The debate (PERS2) draws a card's title into a window of 120 x 12 px (one line; the ideology tags and the
number are a second window right below it in VRAM, and three functions share that slot arithmetic), so a
title wider than the face was cut ("Arrival of the Black"). Lists, the name bar and the card popups show
the full title; only the face takes a short form from tl/face_titles.txt (key<TAB>short title).

How: the four face sites (0x801e1f80 / 0x801e1fb0 = the two title windows' shadow + text, 0x801e1538 /
0x801e155c = the strip drawn again by 0x801e1434) call `face` instead of the title getter 0x8009f560.
`face` calls the getter and looks the returned pointer up in a table of (full title, short title)
address pairs, ended by 0. Routine, table and strings are taken from progstr's string pool.

python3 tools/facetitle.py = check the file (every title wider than FACE_PX has a short form that fits).
"""
import os
import struct
import sys

import asm
import progstr

FILE = os.path.join(progstr.ROOT, 'tl', 'face_titles.txt')
FACE_PX = 115                       # the narrower of the two face drawings (rectangle 116 px, shadow at +1)
GETTER = 0x8009f560                 # card -> title
SITES = (0x801e1538, 0x801e155c, 0x801e1f80, 0x801e1fb0)      # PERS2: jal GETTER


def load():
    out = {}
    for n, line in enumerate(open(FILE, encoding='utf-8').read().splitlines(), 1):
        if line.strip() and not line.startswith('#'):
            k, tab, v = line.partition('\t')
            if not tab or not progstr.KEY.fullmatch(k) or k in out:
                raise ValueError('face_titles.txt line %d: expected a new key<TAB>short title: %r' % (n, line))
            out[k] = v
    return out


def titles():
    """{key: full English title} of the card / topic titles."""
    rs = [r for r in progstr.rows() if r['ui']]
    res = progstr.resolved(progstr.load_tl(), rs)
    return {r['key']: res[r['key']] for r in rs if r['tag'] == 'PROG' and progstr.DESC[0] <= r['va'] < progstr.DESC[1]
            and len(r['jp']) <= 13 and res.get(r['key'], '-') != '-'}


def check():
    short, full, errs = load(), titles(), []
    for k, en in full.items():
        if progstr.px(en) > FACE_PX and k not in short:
            errs.append('%s: %d px and no short title: %s' % (k, progstr.px(en), en))
    for k, en in short.items():
        if k not in full:
            errs.append('%s: not a card title' % k)
        elif progstr.px(en) > FACE_PX:
            errs.append('%s: short title %d px (face holds %d): %s' % (k, progstr.px(en), FACE_PX, en))
    return errs


def routine(at, table):
    return asm.assemble(at, [
        ('addiu', 'sp', 'sp', -24),
        ('sw', 'ra', 16, 'sp'),
        ('jal', GETTER),            # a0 = card: set in the caller's delay slot
        ('nop',),
        ('lui', 't0', table >> 16),
        ('ori', 't0', 't0', table & 0xffff),
        'loop:',
        ('lw', 't1', 0, 't0'),
        ('addiu', 't0', 't0', 8),
        ('beqz', 't1', 'done'),
        ('nop',),
        ('bne', 't1', 'v0', 'loop'),
        ('nop',),
        ('lw', 'v0', -4, 't0'),
        'done:',
        ('lw', 'ra', 16, 'sp'),
        ('nop',),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 24),
    ])


def patch(files, pool):
    """files = {tag: bytearray} after progstr.apply (progstr.ADDR filled); pool = its Pool."""
    errs = check()
    if errs:
        raise ValueError('\n'.join(errs))
    short = load()
    img = {i.tag: i for i in progstr.images(files)}

    def take(n, align=False):          # the pool hands out byte addresses: words and code ask for 3 more
        got = pool.take('PROG', n + 3 if align else n)
        if got is None:
            raise ValueError('facetitle: no room in the string pool for %d bytes' % n)
        return (got[1] + 3) & ~3 if align else got[1]

    pairs, placed = {}, {}
    for k, en in sorted(short.items()):
        b = progstr.encode(en) + b'\0'
        if b not in placed:
            placed[b] = take(len(b))
            img['PROG'].put(placed[b], b)
        pairs[progstr.ADDR[k]] = placed[b]
    table = take(8 * len(pairs) + 4, True)
    img['PROG'].put(table, b''.join(struct.pack('<II', a, s) for a, s in sorted(pairs.items())) + bytes(4))
    code = routine(0, table)
    at = take(len(code), True)
    img['PROG'].put(at, routine(at, table))
    jal = struct.pack('<I', 0x0c000000 | GETTER >> 2 & 0x3ffffff)
    for va in SITES:
        assert bytes(img['PERS2'].data[img['PERS2'].f(va):][:4]) == jal, 'facetitle: site %#x' % va
        img['PERS2'].put(va, asm.assemble(va, [('jal', at)]))
    return len(pairs)


if __name__ == '__main__':
    e = check()
    print('\n'.join(e) if e else 'face titles: %d short forms, all within %d px' % (len(load()), FACE_PX))
    sys.exit(bool(e))
