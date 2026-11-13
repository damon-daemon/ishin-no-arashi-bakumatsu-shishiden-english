#!/usr/bin/env python3
"""Lists joined by a separator placed BEFORE every item (build step after facetitle.patch).

MP2 0x8015d864.. builds the academy greeting as head (MP2:8015b888) + for every subject taught
strcat(sep MP2:8015b898) + strcat(subject) + tail (MP2:8015b89c): the separator comes before the first
subject too. With English pieces that read "This academy teaches , Confucian." The separator's strcat
(0x8015d8b8) now calls `catsep` (in progstr's string pool): it appends ", " unless the buffer ends with a
space, so the head keeps its trailing space and the first subject follows it directly.

PREFIX: the greeting rows PROG:8003466c.. ("You are <prefix><address form>") take their prefix from a
table of 3 x 4 string pointers at MP 0x801762a4 (row = how the speaker sees the listener: faction /
plain / hostile; column = the view Sabaku, Sonnō, Open, Jōi), used at MP 0x8016e80c only. Some entries
are label strings shared with other screens, so the table gets its own strings (string pool), each
ending with a space.

ROWS: the group pages of View Info > Group Info (COM 0x80164ed0.. shogunate, court, domains: posts and the
names under them) centre every name in one of three 84 px columns (x 14, 102, 190) by
x = column + (7 - strlen / 2) * 6. All paths end in one of seven tails `sll a0, a0, 1 / jal pen /
addu a0, v0, a0` with v0 = column x, a1 = y, s2 = the person. The tail now calls `namepen` (string pool):
columns of 96 px at 0, 96, 192 (same centre line, x 144), the name centred by its pixel width and kept
inside 0..ROW_W; a name that would overlap its left neighbour starts 4 px after it.
The post headings above the names (pen x as an immediate: 132 or 120 = middle column, 28 / 44 = left, 200 /
220 = right, set for words of two to five kanji) are centred on the same three lines (48, 144, 240) by the
pixel width of their English at build time (`heads`); the "----" of an empty post likewise.
"""
import struct

import asm
import progstr

STRCAT = 0x800b0380
SITES = (('MP2', 0x8015d8b8),)      # jal STRCAT with a0 = buffer (the separator in a1 is ignored)


PREFIX = ('MP', 0x801762a4, (
    "the Sabaku faction's ", "the Sonnō faction's ", "the Open faction's ", "the Jōi faction's ",
    'the Sabaku ', 'the loyalist ', 'the foreign-loving ', 'the Jōi ',
    "the shogunate's hound ", 'the Sonnō ', 'the country-opening traitor ', 'the Jōi '))


def routine(at):
    return asm.assemble(at, [
        ('addu', 't0', 'a0', 'zero'),
        'end:',
        ('lbu', 't1', 0, 't0'),
        ('addiu', 't0', 't0', 1),
        ('bnez', 't1', 'end'),
        ('nop',),
        ('lbu', 't1', -2, 't0'),            # t0 = NUL + 1
        ('addiu', 't2', 'zero', 0x20),
        ('beq', 't1', 't2', 'done'),
        ('addiu', 't1', 'zero', 0x2c),
        ('sb', 't1', -1, 't0'),
        ('sb', 't2', 0, 't0'),
        ('sb', 'zero', 1, 't0'),
        'done:',
        ('jr', 'ra'),
        ('nop',),
    ])


ROWS = (0x80165238, 0x80165574, 0x801659a0, 0x80165d00, 0x80165f70, 0x8016615c, 0x801663d0, 0x801665e0)
# COM; 0x801657c4 (the same tail, a "----" label) is left alone
ROW_COL, ROW_W = 96, 300
FULLNAME, PEN = 0x800997c8, 0x800a3ef0


def namepen(at, ctr, state=0):
    """v0 = column x (14 / 102 / 190), a1 = y, s2 = person. state = two words (y << 2 | column, right end)
    of the last name drawn: a name that would start inside its left neighbour starts 4 px after it."""
    return asm.assemble(at, [
        ('addiu', 'sp', 'sp', -0x20),
        ('sw', 'ra', 0x10, 'sp'),
        ('sw', 'v0', 0x14, 'sp'),
        ('sw', 'a1', 0x18, 'sp'),
        ('jal', FULLNAME),
        ('addu', 'a0', 's2', 'zero'),
        ('addu', 'a0', 'v0', 'zero'),
        ('jal', ctr),                           # t0 = pixel width of the name
        ('addiu', 'a1', 'zero', ROW_COL),
        ('lw', 'v1', 0x14, 'sp'),
        ('lw', 'a1', 0x18, 'sp'),
        ('addiu', 'a0', 'zero', ROW_COL),
        ('subu', 'a0', 'a0', 't0'),
        ('sra', 'a0', 'a0', 1),
        ('srl', 'v1', 'v1', 6),                 # 14, 102, 190 -> column 0, 1, 2
        ('sll', 't1', 'v1', 7),
        ('sll', 't2', 'v1', 5),
        ('subu', 't1', 't1', 't2'),             # * 96
        ('addu', 'a0', 'a0', 't1'),             # centred in its column
        ('bgez', 'a0', 'c1'),
        ('sll', 't2', 'a1', 2),
        ('addu', 'a0', 'zero', 'zero'),
        'c1:',
        ('or', 't2', 't2', 'v1'),               # y << 2 | column
        ('lui', 't3', state >> 16),
        ('ori', 't3', 't3', state & 0xffff),
        ('lw', 't4', 0, 't3'),
        ('lw', 't5', 4, 't3'),
        ('xor', 't1', 't2', 't4'),
        ('sltiu', 't1', 't1', 4),               # same row as the last name
        ('beqz', 't1', 'c2'),
        ('slt', 't1', 't4', 't2'),              # and a later column
        ('beqz', 't1', 'c2'),
        ('addiu', 't5', 't5', 4),
        ('slt', 't1', 'a0', 't5'),
        ('beqz', 't1', 'c2'),
        ('nop',),
        ('addu', 'a0', 't5', 'zero'),
        'c2:',
        ('addiu', 't1', 'zero', ROW_W),
        ('subu', 't1', 't1', 't0'),
        ('slt', 't5', 't1', 'a0'),
        ('beqz', 't5', 'c3'),
        ('nop',),
        ('addu', 'a0', 't1', 'zero'),           # not past the right edge (the printer would wrap the name)
        'c3:',
        ('bgez', 'a0', 'c4'),
        ('nop',),
        ('addu', 'a0', 'zero', 'zero'),
        'c4:',
        ('sw', 't2', 0, 't3'),
        ('addu', 't1', 'a0', 't0'),
        ('jal', PEN),
        ('sw', 't1', 4, 't3'),
        ('lw', 'ra', 0x10, 'sp'),
        ('nop',),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x20),
    ])


DEBUG = False
HEAD_RANGE = (0x80164d00, 0x80166700)          # COM: the group page functions
HEAD_COL = {132: 144, 120: 144, 28: 48, 44: 48, 200: 240, 220: 240}
PUTS = 0x800ab328
HEADS = 31
DASH = (0x801657c0, 0x8fa20018, 'COM:8015cfb8')   # lw v0, 0x18(sp) = right column, then + 30 (4 bytes centred)


def _centre(c, px):
    return max(0, min(c - px // 2, ROW_W - px)) & ~1


def heads(com, text):
    """Centre the post headings: every `pen(x, y); puts(win, string)` of the group pages whose x is a
    column position. text = {key: English}. Returns the number of pens changed."""
    w = lambda va: struct.unpack_from('<I', com.data, com.f(va))[0]
    jal = lambda t: 0x0c000000 | t >> 2 & 0x3ffffff
    back = {a: k for k, a in progstr.ADDR.items() if k.startswith('COM:')}
    n = 0
    for va in range(HEAD_RANGE[0], HEAD_RANGE[1], 4):
        if w(va) != jal(PEN):
            continue
        key = None
        for k in range(2, 6):                   # lui a1 / addiu a1, a1 around the jal puts
            if w(va + 4 * k) >> 16 != 0x3c05:
                continue
            nxt = [w(va + 4 * k + 4), w(va + 4 * k + 8)]
            lo = [x & 0xffff for x in nxt if x >> 16 == 0x24a5]
            if lo and (jal(PUTS) in nxt or any(x >> 26 == 2 and w((x & 0x3ffffff) << 2 | 0x80000000) == jal(PUTS)
                                               for x in nxt)):     # or a jump to a shared puts
                a = (w(va + 4 * k) << 16 & 0xffffffff) + lo[0] - (0x10000 if lo[0] & 0x8000 else 0)
                key = back.get(a, 'COM:%08x' % a)   # moved strings: by their new address
            break
        if key is None or key == DASH[2]:
            continue
        for at in range(va + 4, va - 4 * 30, -4):
            if at < va and w(at) >> 26 == 3:
                raise ValueError('joins: no pen x for the heading at %#x' % va)
            if w(at) >> 16 == 0x2404:
                break
        x = w(at) & 0xffff
        if x not in HEAD_COL or key not in text:
            raise ValueError('joins: heading at %#x: x %d, %s' % (va, x, key))
        com.put(at, struct.pack('<I', 0x24040000 | _centre(HEAD_COL[x], progstr.px(text[key]))))
        n += 1
        if DEBUG:
            print('%08x %-14s x %3d -> %3d  %s' % (va, key, x, _centre(HEAD_COL[x], progstr.px(text[key])), text[key]))
    at, old, key = DASH
    assert w(at) == old, 'joins: dash site'
    com.put(at, struct.pack('<I', 0x24020000 | (_centre(240, progstr.px(text[key])) - 30) & 0xffff))
    return n


def rows(img, pool):
    import vwf
    rs = [r for r in progstr.rows() if r['ui']]
    n = heads(img['COM'], progstr.resolved(progstr.load_tl(), rs))
    assert n == HEADS, 'joins: %d headings' % n
    assert ROW_COL == 96
    ctr = vwf.blob()[1]['ctr']
    n = len(namepen(0, ctr))
    got = pool.take('PROG', n + 8 + 3)
    if got is None:
        raise ValueError('joins: no room in the string pool')
    at = (got[1] + 3) & ~3
    img['PROG'].put(at, namepen(at, ctr, at + n) + bytes(8))
    old = struct.pack('<3I', 0x00042040, 0x0c028fbc, 0x00442021)
    for va in ROWS:
        com = img['COM']
        assert bytes(com.data[com.f(va):][:12]) == old, 'joins: row tail %#x' % va
        com.put(va, asm.assemble(va, [('jal', at), ('nop',), ('nop',)]))


def patch(files, pool):
    img = {i.tag: i for i in progstr.images(files)}
    n = len(routine(0))
    got = pool.take('PROG', n + 3)
    if got is None:
        raise ValueError('joins: no room in the string pool')
    at = (got[1] + 3) & ~3
    img['PROG'].put(at, routine(at))
    jal = struct.pack('<I', 0x0c000000 | STRCAT >> 2 & 0x3ffffff)
    for tag, va in SITES:
        assert bytes(img[tag].data[img[tag].f(va):][:4]) == jal, 'joins: site %#x' % va
        img[tag].put(va, asm.assemble(va, [('jal', at)]))
    rows(img, pool)
    tag, va, words = PREFIX
    new = {}
    for i, t in enumerate(words):
        if t not in new:
            b = progstr.encode(t) + b'\0'
            got = pool.take('PROG', len(b))
            if got is None:
                raise ValueError('joins: no room in the string pool')
            img['PROG'].put(got[1], b)
            new[t] = got[1]
        img[tag].put(va + 4 * i, struct.pack('<I', new[t]))
