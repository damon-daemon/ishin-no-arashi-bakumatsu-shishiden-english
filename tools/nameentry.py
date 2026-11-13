"""English name entry for the player's own character (INIT.BIN, character creation).

The game's screen (0x8015ee20(dest, max)): a 10 x 5 kana grid (cell = column * 5 + row, row
strings through the pointer table 0x801667f0, cursor sprite at x = column * 24 + 0x18,
y = row * 16 + 0x8a) with the buttons OK (cell 0x32) / Cancel (0x33) on the right. Circle on a
cell opened a candidate window (0x8015e358(cell): kana variants + the kanji read that way) and
the pick was stored as a 3-byte entry (2-byte character + NUL) in the buffer 0x80166bb8 at
slot `pos` (0x801667ec; max 0x801667e8 = 3 characters, 6 for the nickname); OK joins the
entries into dest. The five names end in 13-byte fields of the game state (+0x160 surname,
+0x16d given, +0x17a / +0x187 alias, +0x194 nickname; the setters 0x8009cc58.. refuse 13 bytes
or more), and the creation function keeps them in 13-byte stack buffers.

English: the grid holds letters and Circle appends the cell's letter at once (no candidate
window). Names are up to MAX letters (one byte each: 10 fit the entry buffer, 30 of 32 bytes,
and the 13-byte fields). Upper case at the start and after a space, lower case otherwise; the
`Aa` cell switches the case of the last letter. Cross deletes the last letter. The name is
drawn with our proportional font, so the cursor mark is placed at the pen position of slot
`pos` when the name window is redrawn.

All new code and data replace the candidate window function (dead once its only call is ours):
  pick  0x8015e358(cell)  append / toggle case
  del                     delete the last letter
  draw                    print the entries, place the cursor mark
  UP / LO                 52 bytes each: upper / lower code per cell (0 = empty cell: skipped by
                          the cursor; 1 = the Aa cell; cells 0x32 / 0x33 = 1 for the skip test)
  the five row strings ({T} columns of vwf.py)
"""
import struct

import asm
import text
import vwf

BASE = 0x8015b858                       # INIT.BIN load address
MAX = 10                                # letters per name
AREA = (0x8015e358, 0x8015ea88)         # the candidate window function
ROWS_PTR = 0x801667f0                   # 5 row string pointers
STATE_MAX, STATE_POS = 0x801667e8, 0x801667ec
BUF = 0x80166bb8                        # entries, 3 bytes each
NAME_WIN = 0x80166bd8                   # window object of the name line
CURSOR = 0x80166b84                     # sprite of the cursor mark under the name
PUTS, PLACE = 0x800ab328, 0x800447f4    # puts(window, str); place(sprite, x, y)
PEN_X = 0x8010d730
TOGGLE = 1

# rows of 10 cells: (label, upper, lower) or None
def _letters(s):
    return [(c, c, c.lower()) for c in s]

GRID = [
    _letters('ABCDEFGHIJ'),
    _letters('KLMNOPQRST'),
    _letters('UVWXYZ') + [('Ō', 'Ō', 'ō'), ('Ū', 'Ū', 'ū'), ("'", "'", "'"), ('-', '-', '-')],
    [None] * 10,
    [('Aa', TOGGLE, TOGGLE), None, ('Space', ' ', ' ')] + [None] * 7,
]


def _code(c):
    return c if isinstance(c, int) else ord(text.fold(c))


def tables():
    up, lo_ = bytearray(52), bytearray(52)
    for r, row in enumerate(GRID):
        for c, cell in enumerate(row):
            if cell:
                up[c * 5 + r], lo_[c * 5 + r] = _code(cell[1]), _code(cell[2])
    up[50] = up[51] = lo_[50] = lo_[51] = 1
    return bytes(up), bytes(lo_)


def rows():
    """the five row strings: every label at its cell (pen x = 8 + 24 * column, narrow labels 4 px in)."""
    out = []
    for row in GRID:
        b = b''
        for c, cell in enumerate(row):
            if not cell:
                continue
            lab = text.fold(cell[0])
            px = 8 + 24 * c + (4 if vwf.width(lab) <= 4 else 0)
            if px != 8:                 # the pen starts at 8; the tab escape would add its 4 px gap
                assert px % 4 == 0 and px != 20
                b += b'\x1bT' + bytes([0x20 + px // 4])
            b += lab.encode('ascii')
        out.append(b + b'\0')
    return out


def listing():
    hi, lo = asm.hi, asm.lo
    slot = [                            # t4 -> state page, t5 = pos, t7 -> slot of pos
        ('lui', 't4', hi(STATE_POS)),
        ('lw', 't5', lo(STATE_POS), 't4'),
        ('lui', 't6', hi(BUF)),
        ('addiu', 't6', 't6', lo(BUF)),
        ('sll', 't7', 't5', 1),
        ('addu', 't7', 't7', 't5'),
        ('addu', 't7', 't7', 't6'),
    ]
    return [
        'pick:',
        ('andi', 'a0', 'a0', 0xff),
        ('lui', 't0', 'UPHI'),
        ('addiu', 't0', 't0', 'UPLO'),
        *slot,
        ('addu', 't1', 't0', 'a0'),
        ('lbu', 't2', 0, 't1'),
        ('lbu', 't3', 52, 't1'),
        ('addiu', 'v0', 'zero', TOGGLE),
        ('beq', 't2', 'v0', 'toggle'),
        ('nop',),
        ('beqz', 't5', 'store'),        # first letter: upper case
        ('nop',),
        ('lbu', 'v0', -3, 't7'),
        ('addiu', 'v1', 'zero', 0x20),
        ('beq', 'v0', 'v1', 'store'),   # after a space: upper case
        ('nop',),
        ('or', 't2', 't3', 'zero'),
        'store:',
        ('sb', 't2', 0, 't7'),
        ('sb', 'zero', 1, 't7'),
        ('lw', 'v0', lo(STATE_MAX), 't4'),
        ('addiu', 't5', 't5', 1),
        ('sltu', 'v0', 't5', 'v0'),
        ('beqz', 'v0', 'ret'),          # the last slot is overwritten
        ('nop',),
        ('sw', 't5', lo(STATE_POS), 't4'),
        'ret:',
        ('jr', 'ra'),
        ('nop',),
        'toggle:',                      # the letter at pos, or the one before it
        ('lbu', 'v0', 0, 't7'),
        ('nop',),
        ('bnez', 'v0', 'tscan'),
        ('nop',),
        ('beqz', 't5', 'ret'),
        ('nop',),
        ('addiu', 't7', 't7', -3),
        ('lbu', 'v0', 0, 't7'),
        ('nop',),
        'tscan:',
        ('addiu', 't1', 't0', 49),
        'tloop:',
        ('lbu', 't2', 0, 't1'),
        ('lbu', 't3', 52, 't1'),
        ('nop',),
        ('beq', 't2', 't3', 'tnext'),
        ('nop',),
        ('beq', 'v0', 't2', 'tset'),
        ('or', 'v1', 't3', 'zero'),
        ('beq', 'v0', 't3', 'tset'),
        ('or', 'v1', 't2', 'zero'),
        'tnext:',
        ('bne', 't1', 't0', 'tloop'),
        ('addiu', 't1', 't1', -1),
        ('jr', 'ra'),
        ('nop',),
        'tset:',
        ('jr', 'ra'),
        ('sb', 'v1', 0, 't7'),

        'del:',                         # clear the slot at pos, or step back and clear that one
        *slot,
        ('lbu', 'v0', 0, 't7'),
        ('nop',),
        ('bnez', 'v0', 'dclr'),
        ('nop',),
        ('beqz', 't5', 'dret'),
        ('nop',),
        ('addiu', 't5', 't5', -1),
        ('sw', 't5', lo(STATE_POS), 't4'),
        ('addiu', 't7', 't7', -3),
        'dclr:',
        ('sb', 'zero', 0, 't7'),
        'dret:',
        ('jr', 'ra'),
        ('nop',),

        'draw:',                        # print the entries; cursor mark at the pen x of slot pos
        ('addiu', 'sp', 'sp', -0x20),
        ('sw', 'ra', 0x1c, 'sp'),
        ('sw', 's0', 0x10, 'sp'),
        ('sw', 's1', 0x14, 'sp'),
        ('sw', 's2', 0x18, 'sp'),
        ('lui', 's0', hi(BUF)),
        ('addiu', 's0', 's0', lo(BUF)),
        ('or', 's1', 'zero', 'zero'),
        ('addiu', 's2', 'zero', 8),
        'dloop:',
        ('lui', 'v0', hi(STATE_POS)),
        ('lw', 'v1', lo(STATE_POS), 'v0'),
        ('lui', 'a0', hi(PEN_X)),
        ('bne', 's1', 'v1', 'dput'),
        ('nop',),
        ('lh', 's2', lo(PEN_X), 'a0'),
        'dput:',
        ('lui', 'a0', hi(NAME_WIN)),
        ('addiu', 'a0', 'a0', lo(NAME_WIN)),
        ('jal', PUTS),
        ('or', 'a1', 's0', 'zero'),
        ('lui', 'v0', hi(STATE_MAX)),
        ('lw', 'v0', lo(STATE_MAX), 'v0'),
        ('addiu', 's1', 's1', 1),
        ('sltu', 'v0', 's1', 'v0'),
        ('bnez', 'v0', 'dloop'),
        ('addiu', 's0', 's0', 3),
        ('lui', 'v0', hi(CURSOR)),
        ('lw', 'a0', lo(CURSOR), 'v0'),
        ('addiu', 'a1', 's2', 0x10),
        ('jal', PLACE),
        ('addiu', 'a2', 'zero', 0x1f),
        ('lw', 'ra', 0x1c, 'sp'),
        ('lw', 's0', 0x10, 'sp'),
        ('lw', 's1', 0x14, 'sp'),
        ('lw', 's2', 0x18, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x20),
        'UP:',
    ]


def blob():
    """(bytes at AREA[0], labels incl. the row strings ROW0..ROW4)"""
    lines = listing()
    labels = asm.labels(AREA[0], lines)
    up = labels['UP']
    res = [tuple((asm.hi(up) if x == 'UPHI' else asm.lo(up) if x == 'UPLO' else x) for x in ln)
           if isinstance(ln, tuple) else ln for ln in lines]
    out = asm.assemble(AREA[0], res) + b''.join(tables())
    for i, r in enumerate(rows()):
        labels['ROW%d' % i] = AREA[0] + len(out)
        out += r
    assert AREA[0] + len(out) <= AREA[1]
    return out, labels


# (address, clean words, replacement lines)
def _sites(L):
    return [
        # redraw of the name line: the loop over the entries -> draw
        (0x8015f040, (0x3c038016, 0x8c6267e8), [('jal', L['draw']), ('nop',), ('j', 0x8015f07c), ('nop',)]),
        # Cross: memset of the slot, pos - 1, cursor -> del
        (0x8015f0a8, (0x00002821, 0x24060003, 0x3c108016, 0x8e0267ec),
         [('jal', L['del']), ('addiu', 's4', 'zero', 1), ('j', 0x8015f100), ('nop',)]),
        # cursor movement skipped the cells 3, 4, 0xb, 0xd -> every cell with UP[cell] == 0
        (0x8015ed18, (0x2482fffd, 0x304200ff, 0x2c420002, 0x1440fff8, 0x308200ff, 0x1056fff6, 0x00000000,
                      0x1051fff5, 0x308400ff),
         [('andi', 'v0', 'a0', 0xff), ('lui', 'at', asm.hi(L['UP'])), ('addu', 'at', 'at', 'v0'),
          ('lbu', 'at', asm.lo(L['UP']), 'at'), ('nop',), ('beqz', 'at', 0x8015ed08), ('nop',),
          ('nop',), ('nop',)]),
        (0x8015ee30, (0x2416002d,), [('addiu', 's6', 'zero', 0)]),          # first cell: A
        (0x8015ee74, (0x24060012,), [('addiu', 'a2', 'zero', 3 * MAX)]),    # entry buffer cleared
        (0x8015f254, (0x24030003,), [('addiu', 'v1', 'zero', MAX)]),        # 3 characters
        (0x8015f25c, (0x24020006,), [('addiu', 'v0', 'zero', MAX)]),        # 6 (nickname)
    ]


def patch(prog):
    """Patch prog['INIT'] (bytearray)."""
    d = prog['INIT']
    o = lambda va: va - BASE
    w = lambda va: struct.unpack_from('<I', d, o(va))[0]
    jal = 0x0c000000 | AREA[0] >> 2 & 0x3ffffff
    calls = [BASE + i for i in range(0, len(d) - 3, 4) if struct.unpack_from('<I', d, i)[0] == jal]
    assert calls == [0x8015f188], [hex(x) for x in calls]
    assert 3 * MAX <= NAME_WIN - BUF and MAX < 13
    code, L = blob()
    d[o(AREA[0]):o(AREA[0]) + len(code)] = code
    for va, old, new in _sites(L):
        assert tuple(w(va + 4 * i) for i in range(len(old))) == old, hex(va)
        b = asm.assemble(va, new)
        d[o(va):o(va) + len(b)] = b
    for i in range(5):
        assert BASE <= w(ROWS_PTR + 4 * i) < BASE + len(d)
        struct.pack_into('<I', d, o(ROWS_PTR + 4 * i), L['ROW%d' % i])
    return len(code)


if __name__ == '__main__':
    code, L = blob()
    print('%d of %d bytes; %s' % (len(code), AREA[1] - AREA[0], ', '.join('%s %#x' % kv for kv in L.items())))
    for r in rows():
        print(r)
