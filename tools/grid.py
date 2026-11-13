"""Name grids of the Belongings > Sights tabs (COM.BIN), laid out again for English.

The Japanese screens put short names at fixed positions: hot springs 7 in a row (x 66 + 32 n, y 138),
sights 9 in 3 columns of 72 px (x 74, y 30 + 16 row), specialities 25 at hand-set (x, y) pairs built on
the stack (0x8016f3e0..0x8016f62c). English names are 2-4 times wider, so each grid gets a table of
(x / 2, y) bytes made here by flowing the names into rows, and the three pen calls go through a routine
in the program's code cave (after the VWF code, before names.py's pool):

    stub_n:  lui a1 / ori a1 = table n ; (falls into) gridpen
    gridpen: x = table[2 a0] * 2, y = table[2 a0 + 1] ; j pen setter 0x800a3ef0     (a0 = item number)

Also here: a "%s %s" string for the two view words of the Group Details list (the game's "%s%s" at
COM:8015d294 is shared with these grids, where the first %s is a colour escape).
"""
import struct

import asm
import progstr
import vwf

AT = vwf.CAVE + 0x300            # 0x800cf010 .. names.POOL (0x800cf110)
END = vwf.CAVE + 0x400
PEN = 0x800a3ef0
GAP = 10                         # pixels between two names in a row
WIDTH = 288                      # right edge of the text rectangle used by the Japanese layout

# (name, keys, first row x, other rows x, first y, rows allowed)
HOT = ['COM:%08x' % (0x8015e660 + 8 * i) for i in range(7)]
SIGHTS = ['COM:%08x' % (0x8015e6b8 + 12 * i) for i in range(9)]
SPEC = ['COM:%08x' % a for a in (
    0x8015e724, 0x8015e734, 0x8015e73c, 0x8015e744, 0x8015e74c, 0x8015e754, 0x8015e75c, 0x8015e764,
    0x8015e770, 0x8015e780, 0x8015e788, 0x8015e798, 0x8015e7a0, 0x8015e7a8, 0x8015e7b0, 0x8015e7bc,
    0x8015e7c8, 0x8015e7d4, 0x8015e7dc, 0x8015e7e4, 0x8015e7ec, 0x8015e7f8, 0x8015e800, 0x8015e80c,
    0x8015e814)]
GRIDS = [
    ('hot', HOT, 66, 66, 0x8a, 2),
    ('sights', SIGHTS, 62, 62, 0x1e, 4),          # the "Specialities" label is at y 0x66
    ('spec', SPEC, 66, 18, 0x66, 7),
]

# COM sites: (vaddr, clean word, new) with 'jal:<stub>' resolved to the cave address
SITES = [
    # hot springs 0x8016efe8: move a0, s0 / jal pen / addiu a1, zero, 0x8a
    (0x8016efe8, 0x02002021, 0),
    (0x8016efec, 0x0c028fbc, 'jal:hot'),
    (0x8016eff0, 0x2405008a, 0x02402021),          # move a0, s2
    # sights 0x8016f374: jal pen / addiu a1, a1, 0x1e (x and y computed before: unused now)
    (0x8016f374, 0x0c028fbc, 'jal:sights'),
    (0x8016f378, 0x24a5001e, 0x02402021),
    # specialities 0x8016f62c: lh a0 / lh a1 / jal pen / nop
    (0x8016f62c, 0x860400f8, 0),
    (0x8016f630, 0x860500fa, 0),
    (0x8016f634, 0x0c028fbc, 'jal:spec'),
    (0x8016f638, 0x00000000, 0x02402021),
    # Group Details row 0x80167ac0: lui a0, 0x8016 / addiu a0, a0, 0xd294 ("%s%s") -> our "%s %s"
    (0x80167ac0, 0x3c048016, 'lui:fmt'),
    (0x80167ac4, 0x2484d294, 'lo:fmt'),
]


def english():
    rows = progstr.rows()
    return progstr.resolved(progstr.load_tl(), rows), {r['key']: r['jp'] for r in rows}


def flow(keys, x0, x1, y0, rows, en, jp):
    """[(x, y)] for the names in order; raises when they need more rows than allowed."""
    out, x, row = [], x0, 0
    for k in keys:
        if k not in jp:
            raise ValueError('grid: %s is not a program string' % k)
        w = progstr.px(en[k]) if k in en else 12 * len(jp[k])
        if x + w > WIDTH and x > (x1 if row else x0):
            row, x = row + 1, x1
        if row >= rows or x + w > WIDTH:
            raise ValueError('grid: %r does not fit (%s)' % (en.get(k, jp[k]), k))
        out.append((x & ~1, y0 + 16 * row))
        x += w + GAP
    return out


def blob():
    """(bytes at AT, labels)"""
    en, jp = english()
    tables = [(name, flow(keys, x0, x1, y0, rows, en, jp)) for name, keys, x0, x1, y0, rows in GRIDS]
    code_len = 4 * (3 * len(tables) + 6)
    labels, data, at = {}, b'', AT + code_len
    for name, pos in tables:
        labels['T' + name] = at + len(data)
        data += bytes(b for x, y in pos for b in (x >> 1, y))
    labels['fmt'] = at + len(data)
    data += b'%s %s\0'
    lines = []
    for name, _ in tables:
        t = labels['T' + name]
        lines += [name + ':', ('lui', 'a1', t >> 16), ('j', 'gridpen'), ('ori', 'a1', 'a1', t & 0xffff)]
    lines += ['gridpen:', ('sll', 't0', 'a0', 1), ('addu', 't0', 't0', 'a1'), ('lbu', 'a0', 0, 't0'),
              ('lbu', 'a1', 1, 't0'), ('j', PEN), ('sll', 'a0', 'a0', 1)]
    labels.update(asm.labels(AT, lines))
    out = asm.assemble(AT, lines)
    assert len(out) <= code_len, (len(out), code_len)
    out = out + bytes(code_len - len(out)) + data
    assert AT + len(out) <= END
    return out + bytes(-len(out) % 4), labels


def patch(files):
    """Write the cave routine into files['PROG'] and the call sites into files['COM'] (bytearrays)."""
    code, labels = blob()
    prog, com = files['PROG'], files['COM']
    o = AT - 0x80010000 + 0x800
    assert not any(prog[o:o + len(code)]), 'grid cave is not empty'
    prog[o:o + len(code)] = code
    for va, old, new in SITES:
        o = va - progstr.OVL_BASE
        if struct.unpack_from('<I', com, o)[0] != old:
            raise ValueError('grid COM:%08x: unexpected word' % va)
        if isinstance(new, str):
            kind, name = new.split(':')
            a = labels[name]
            new = {'jal': 0x0c000000 | (a >> 2 & 0x3ffffff), 'lui': 0x3c040000 | asm.hi(a),
                   'lo': 0x24840000 | (a & 0xffff)}[kind]
        struct.pack_into('<I', com, o, new)


if __name__ == '__main__':
    en, jp = english()
    for name, keys, x0, x1, y0, rows in GRIDS:
        print(name)
        for k, (x, y) in zip(keys, flow(keys, x0, x1, y0, rows, en, jp)):
            print('  %3d %3d  %s' % (x, y, en.get(k, jp[k])))
    b, labels = blob()
    print('%d bytes at %#x; %s' % (len(b), AT, ', '.join('%s %#x' % kv for kv in labels.items())))
