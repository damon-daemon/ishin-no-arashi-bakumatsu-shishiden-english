"""Variable-width English text: our proportional font (pixfont.py) inside the game's kana font,
a per-character advance and word wrap in the string printer.

The game's fonts are VRAM images: CG/KANA.FNT is 240x60 px, 4 bits per pixel, and every bit
plane is a separate 1-bit font, so it holds 20 x 5 cells x 4 planes = 400 glyphs of 12x12
(glyph index = cell * 4 + plane; 338 are used). The glyph routine 0x800a2e18(code) draws one
glyph at the pen (x 0x8010d730, y 0x8010d732, relative to the text rectangle x0, y0, w, h at
0x8010d728) and moves the pen 12 px; before drawing it starts a new line (x = 0, y += 16) when
x + 12 > w, unless the flag 0x8010d738 is set (the game sets it after closing punctuation).
The string printer 0x800a3964 sends 2-byte codes as they are, ASCII 0x20-0x7e through the code
table 0x8010d7dc (u16 per character: the full-width forms), 0x0a = new line, 0x1b = escapes
(ESC C n = colour).

Patches:
  * our letters and digits are drawn into the cells of the full-width ones (the table already
    points there); punctuation and the macron vowels go to the unused glyphs 338-399, reached by
    the new codes 0x8397+ (glyph routine: range check 0x257 -> 0x295 and the last range's end
    0x8396 -> 0x83d4; index = code - 0x8380 + 315)
  * printer hook at 0x800a3a88 (ASCII branch) -> `vwf` in the cave:
      space      measures the next word; if the pen is not at the line start and the word does
                 not fit in w, starts a new line instead, else moves the pen SPACE_ADV px
      other      sets the no-wrap flag, draws, then moves the pen back to x + width
  The cave 0x800ced10 is part of a 17 KB zero block in the program's data that no instruction
  addresses (checked by scan; watched in the emulator).

  width(text) -> pixels; kana_font(data) -> CG/KANA.FNT with our glyphs; patch(exe) -> exe
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, pixfont

_G = pixfont.glyphs()
SPACE_ADV = pixfont.SPACE_ADV
WIDTHS = bytes(_G[chr(c)][1] for c in range(0x20, 0x7f))
MACRONS = pixfont.MACRONS                     # {'ō': '^', ...}: text.FOLD

GLYPH, PRINT_RET = 0x800a2e18, 0x800a3b58
HOOK_AT = 0x800a3a88                          # addu v0, v0, s4 (v1 = character, s0 -> it, s4 = table);
                                              # 0x800a3a84 is the delay slot of the range branch: kept
FW_AT = 0x800a39d0                            # two-byte path: lui v1, 0x8004 / lbu v0, 1(s0)
RANGE_AT = 0x800a3390                         # sltiu v0, v0, 0x257
LAST_AT = 0x800a34a8                          # ori v0, zero, 0x8396 (last code of the last range)
TABLE = 0x8010d7dc                            # u16 code per character (index = character)
PEN_X, PEN_Y, RECT_W, NOWRAP = 0x8010d730, 0x8010d732, 0x8010d72c, 0x8010d738
CAVE, CAVE_END = 0x800ced10, 0x800d3150
TOK_AT, TOK_PLAIN = 0x8007003c, 0x800701a4    # expander: addiu v1, v1, -0xa + sltiu v0, v1, 0x4a;
                                              # its "ordinary byte" path (s1 = 0)
ESC_TABLE = 0x8003c7a0                        # the printer's jump table for ESC + letter ('C'..'n')
LINE_H, CELL = 16, 12
FIRST_FREE = 338                              # first unused glyph of the kana font
PUNCT = [chr(c) for c in range(0x21, 0x7f) if not chr(c).isalnum()]


def glyph_index(ch):
    """glyph number in the kana font of an ASCII character (not the space)."""
    if ch.isdigit():
        return 0x6b + ord(ch) - 0x30
    if 'A' <= ch <= 'Z':
        return 0x75 + ord(ch) - 0x41
    if 'a' <= ch <= 'z':
        return 0x8f + ord(ch) - 0x61
    return FIRST_FREE + PUNCT.index(ch)


def code(ch):
    """the 2-byte code the glyph routine maps to glyph_index(ch)."""
    i = glyph_index(ch)
    if i >= 0x13b:
        return 0x8380 + i - 0x13b
    if i >= 0x8f:
        return 0x8281 + i - 0x8f
    if i >= 0x75:
        return 0x8260 + i - 0x75
    return 0x824f + i - 0x6b


def width(s):
    """pixels of an ASCII string as the hook draws it."""
    return sum(WIDTHS[ord(c) - 0x20] for c in s)


def kana_font(data):
    """CG/KANA.FNT with our glyphs in their cells (one bit plane each)."""
    d = bytearray(data)
    assert len(d) == 240 * 60 // 2
    for c in range(0x21, 0x7f):
        ch = chr(c)
        i = glyph_index(ch)
        assert i < 400
        cell, bit = i // 4, 1 << (i % 4)
        x0, y0 = cell % 20 * CELL, cell // 20 * CELL
        rows = _G[ch][0]
        for y in range(CELL):
            for x in range(CELL):
                p = (y0 + y) * 120 + (x0 + x) // 2
                m = bit << 4 if (x0 + x) & 1 else bit
                if x < 8 and rows[y] & (0x80 >> x):
                    d[p] |= m
                else:
                    d[p] &= ~m & 0xff
    return bytes(d)


def listing():
    """the hook code; data label W (95 widths) follows the code."""
    hi, lo = asm.hi, asm.lo
    return [
        'vwf:',
        ('addiu', 's0', 's0', 1),
        ('addiu', 'v0', 'zero', 0x20),
        ('bne', 'v1', 'v0', 'draw'),
        ('lui', 't3', hi(CAVE)),
        # space: t0 = SPACE_ADV + pixels of the next word
        ('addiu', 't0', 'zero', SPACE_ADV),
        ('or', 't1', 's0', 'zero'),
        'word:',
        ('lbu', 't2', 0, 't1'),
        ('nop',),
        ('addiu', 'v0', 't2', -0x21),
        ('sltiu', 'v0', 'v0', 0x5e),
        ('beqz', 'v0', 'measured'),
        ('addu', 'v0', 't3', 't2'),
        ('lbu', 'v0', 'W-0x20', 'v0'),
        ('addiu', 't1', 't1', 1),
        ('b', 'word'),
        ('addu', 't0', 't0', 'v0'),
        'measured:',
        ('lui', 't4', hi(PEN_X)),
        ('lh', 'v0', lo(PEN_X), 't4'),
        ('lh', 'v1', lo(RECT_W), 't4'),
        ('beqz', 'v0', 'advance'),              # line start: nothing to gain from a new line
        ('addu', 't0', 't0', 'v0'),
        ('slt', 'v1', 'v1', 't0'),
        ('beqz', 'v1', 'advance'),
        ('nop',),
        ('lhu', 'v1', lo(PEN_Y), 't4'),
        ('sh', 'zero', lo(PEN_X), 't4'),
        ('addiu', 'v1', 'v1', LINE_H),
        ('j', PRINT_RET),
        ('sh', 'v1', lo(PEN_Y), 't4'),
        'advance:',
        ('addiu', 'v0', 'v0', SPACE_ADV),
        ('j', PRINT_RET),
        ('sh', 'v0', lo(PEN_X), 't4'),
        'draw:',
        ('lui', 't4', hi(NOWRAP)),
        ('addiu', 'v0', 'zero', 1),
        ('sw', 'v0', lo(NOWRAP), 't4'),
        ('sll', 'v0', 'v1', 1),
        ('addu', 'v0', 'v0', 's4'),
        ('lhu', 'a0', 0, 'v0'),
        ('jal', GLYPH),
        ('nop',),
        ('lbu', 'v1', -1, 's0'),
        ('lui', 't3', hi(CAVE)),
        ('addu', 'v1', 't3', 'v1'),
        ('lbu', 'v1', 'W-0x20', 'v1'),
        ('lui', 't4', hi(PEN_X)),
        ('lhu', 'v0', lo(PEN_X), 't4'),
        ('addiu', 'v1', 'v1', -CELL),
        ('addu', 'v0', 'v0', 'v1'),
        ('j', PRINT_RET),
        ('sh', 'v0', lo(PEN_X), 't4'),
        # ESC T c: pen x = (c - 0x20) * 4 (our own escape for list columns; progstr writes it {T104}).
        # The printer's escape table sends the letter T here with s0 on the byte after it.
        'tab:',
        ('lbu', 'v0', 0, 's0'),
        ('addiu', 's0', 's0', 1),
        ('addiu', 'v0', 'v0', -0x20),
        ('sll', 'v0', 'v0', 2),
        ('lui', 't4', hi(PEN_X)),
        # a column never starts closer than 4 px to the text before it: a long name pushes the
        # next column right instead of being overprinted
        ('lh', 'v1', lo(PEN_X), 't4'),
        ('nop',),
        ('addiu', 'v1', 'v1', 4),
        ('slt', 't0', 'v0', 'v1'),
        ('beqz', 't0', 'tabset'),
        ('nop',),
        ('or', 'v0', 'v1', 'zero'),
        'tabset:',
        ('j', PRINT_RET),
        ('sh', 'v0', lo(PEN_X), 't4'),
        # Name-token guard. The expander 0x8006ffb4 takes every ASCII S M F K A P as a token
        # (S1 surname, P2 "you" ...) without looking at the digit: fine for Japanese, but English
        # words begin with those letters ("Pleased" came out as "youeased"; S / M / F index the
        # stack with the next byte). A letter is a token only when 1 or 2 follows; '%' as before.
        'tok:',
        ('addiu', 'v0', 'zero', 0x25 - 0xa),
        ('beq', 'v1', 'v0', 'tokok'),
        ('nop',),
        ('lbu', 't1', 1, 's0'),
        ('nop',),
        ('addiu', 't1', 't1', -0x31),
        ('sltiu', 't1', 't1', 2),
        ('bnez', 't1', 'tokok'),
        ('nop',),
        ('j', TOK_PLAIN),
        ('or', 's1', 'zero', 'zero'),
        'tokok:',
        ('j', TOK_AT + 8),
        ('sltiu', 'v0', 'v1', 0x4a),
        # Full-width digits (0x824f-0x8258: numbers the game converts itself, e.g. "trust rose by ４")
        # take the two-byte path with a 12 px advance: draw them with the width of our digits.
        # Entered from FW_AT with v1 = first byte, v0 = second byte (delay slot).
        'fw:',
        ('addiu', 't0', 'v1', -0x82),
        ('bnez', 't0', 'fwback'),
        ('addiu', 't0', 'v0', -0x4f),
        ('sltiu', 't0', 't0', 10),
        ('beqz', 't0', 'fwback'),
        ('lui', 't4', hi(NOWRAP)),
        ('addiu', 's0', 's0', 2),
        ('addiu', 't0', 'zero', 1),
        ('sw', 't0', lo(NOWRAP), 't4'),
        ('addiu', 'v0', 'v0', -0x1f),
        ('sll', 'v0', 'v0', 1),
        ('addu', 'v0', 'v0', 's4'),
        ('lhu', 'a0', 0, 'v0'),
        ('jal', GLYPH),
        ('nop',),
        ('lbu', 'v1', -1, 's0'),
        ('lui', 't3', hi(CAVE)),
        ('addu', 'v1', 't3', 'v1'),
        ('lbu', 'v1', 'W-0x3f', 'v1'),
        ('lui', 't4', hi(PEN_X)),
        ('lhu', 'v0', lo(PEN_X), 't4'),
        ('addiu', 'v1', 'v1', -CELL),
        ('addu', 'v0', 'v0', 'v1'),
        ('j', PRINT_RET),
        ('sh', 'v0', lo(PEN_X), 't4'),
        'fwback:',
        ('j', FW_AT + 8),
        ('lui', 'v1', 0x8004),
        # Centred labels: v0 = max(0, (a1 - pixels of the string a0) / 2), t0 = pixels of the string
        # (uses a0, t0, t2, t3). The game centres by 6 px per byte ((14 - strlen) * 3 in the fencing name
        # plates): wrong for our widths, negative for long names.
        'ctr:',
        ('lui', 't3', hi(CAVE)),
        ('or', 't0', 'zero', 'zero'),
        'ctrl:',
        ('lbu', 't2', 0, 'a0'),
        ('nop',),
        ('beqz', 't2', 'ctrend'),
        ('addiu', 'v0', 't2', -0x20),
        ('sltiu', 'v0', 'v0', 0x5f),
        ('beqz', 'v0', 'ctr2'),
        ('addu', 'v0', 't3', 't2'),
        ('lbu', 'v0', 'W-0x20', 'v0'),
        ('addiu', 'a0', 'a0', 1),
        ('b', 'ctrl'),
        ('addu', 't0', 't0', 'v0'),
        'ctr2:',
        ('addiu', 'a0', 'a0', 2),
        ('b', 'ctrl'),
        ('addiu', 't0', 't0', CELL),
        'ctrend:',
        ('subu', 'v0', 'a1', 't0'),
        ('bgez', 'v0', 'ctrok'),
        ('sra', 'v0', 'v0', 1),
        ('or', 'v0', 'zero', 'zero'),
        'ctrok:',
        ('jr', 'ra'),
        ('nop',),
        'W:',
    ]


def blob():
    """(bytes at CAVE, labels)"""
    lines = listing()
    labels = asm.labels(CAVE, lines)
    w = labels['W']
    res = [tuple((asm.lo(w - 0x20) if x == 'W-0x20' else asm.lo(w - 0x3f) if x == 'W-0x3f' else x) for x in ln)
           if isinstance(ln, tuple) else ln
           for ln in lines]
    assert asm.hi(w - 0x3f) == asm.hi(CAVE) and asm.hi(w + 0x7f) == asm.hi(CAVE)
    out = asm.assemble(CAVE, res) + WIDTHS
    assert CAVE + len(out) <= CAVE_END
    return out + bytes(-len(out) % 4), labels


# Script buffer A (SEVAK / HEVIJ / FEVRE scripts) is 0x8017cca0..0x80184ca0 (32 KB; the largest
# Japanese script has 27,893 bytes). The overlays at 0x8015b858 end at 0x80177058 at most (PERS.BIN,
# whole sectors), and nothing refers to the gap up to the buffer, so the buffer starts lower:
# four sites load the address as lui a3, 0x8017 (earlier) + ori a3, a3, 0xcca0.
BUF_A, BUF_A_END = 0x80177800, 0x80184ca0
BUF_A_SITES = (0x80045430, 0x80045d10, 0x80065c9c, 0x8006a094)


def patch(exe):
    """PS-X EXE bytes -> patched (hook, cave, code table, range check)."""
    d = bytearray(exe)
    off = lambda va: va - 0x80010000 + 0x800
    code_, labels = blob()
    assert not any(d[off(CAVE):off(CAVE) + len(code_)]), 'cave is not empty'
    d[off(CAVE):off(CAVE) + len(code_)] = code_
    assert struct.unpack_from('<I', d, off(HOOK_AT))[0] == 0x00541021
    d[off(HOOK_AT):off(HOOK_AT) + 8] = asm.assemble(HOOK_AT, [('j', labels['vwf']), ('nop',)])
    assert struct.unpack_from('<I', d, off(RANGE_AT))[0] == 0x2c420257
    struct.pack_into('<I', d, off(RANGE_AT), 0x2c420257 + 400 - FIRST_FREE)
    assert struct.unpack_from('<I', d, off(LAST_AT))[0] == 0x34028396
    struct.pack_into('<I', d, off(LAST_AT), 0x34028396 + 400 - FIRST_FREE)
    for ch in PUNCT:
        struct.pack_into('<H', d, off(TABLE) + 2 * ord(ch), code(ch))
    assert struct.unpack_from('<I', d, off(ESC_TABLE + 4 * (ord('T') - 0x43)))[0] == PRINT_RET
    struct.pack_into('<I', d, off(ESC_TABLE + 4 * (ord('T') - 0x43)), labels['tab'])
    assert struct.unpack_from('<II', d, off(TOK_AT)) == (0x2463fff6, 0x2c62004a)
    d[off(TOK_AT):off(TOK_AT) + 8] = asm.assemble(TOK_AT, [('j', labels['tok']), ('addiu', 'v1', 'v1', -0xa)])
    assert struct.unpack_from('<II', d, off(FW_AT)) == (0x3c038004, 0x92020001)
    d[off(FW_AT):off(FW_AT) + 8] = asm.assemble(FW_AT, [('j', labels['fw']), ('lbu', 'v0', 1, 's0')])
    for va in BUF_A_SITES:
        assert struct.unpack_from('<I', d, off(va))[0] == 0x34e7cca0
        struct.pack_into('<I', d, off(va), 0x34e70000 | (BUF_A & 0xffff))
    for m in MENUS:
        _menu(d, off, labels['ctr'], *m)
    return bytes(d)


# Bar menus: 0x800a48c0.. (command menus: items {text, enabled, ...} of 12 bytes) and 0x800a4f04 (the
# choices of script op 0x1b). Both keep the longest strlen in s6, make every bar s6 * 6 + 8 px wide (cursor
# frame s6 * 6 + 12) and print each text at (s6 - strlen) * 3. With our font the text sat left of centre in
# a bar that was too wide. Patched: s6 = the widest text in pixels (made even, +1), bar = s6 + 8, frame =
# s6 + 12, pen = (s6 - pixels) / 2, all through `ctr` (its t0 = pixels). Same instruction slots.
#   (measure site, width site, register that takes the width, frame site, centring sites)
MENUS = ((0x800a4960, 0x800a49a0, 'v0', 0x800a4af4, (0x800a4a0c, 0x800a4d0c, 0x800a4dc4)),
         (0x800a4f8c, 0x800a4fd4, 's7', 0x800a50bc, (0x800a5020, 0x800a5214, 0x800a5264)))
STRLEN = 0x800b0480


def _menu(d, off, ctr, measure, width, wreg, frame, centres):
    def put(va, old, new):
        new = asm.assemble(va, new)
        assert d[off(va):off(va) + len(new)] == asm.assemble(va, old), hex(va)
        d[off(va):off(va) + len(new)] = new
    put(measure, [('jal', STRLEN)], [('jal', ctr)])
    put(measure + 8, [('addu', 'v1', 'v0', 'zero')], [('or', 'v1', 't0', 'zero')])
    put(width, [('sll', 'v0', 's6', 1), ('addu', 'v0', 'v0', 's6'), ('sll', wreg, 'v0', 1)],
        [('ori', 's6', 's6', 1), ('addiu', 's6', 's6', 1), ('or', wreg, 's6', 'zero')])
    put(frame, [('sll', 'a1', 's6', 1), ('addu', 'a1', 'a1', 's6'), ('sll', 'a1', 'a1', 1)],
        [('nop',), ('nop',), ('or', 'a1', 's6', 'zero')])
    for va in centres:                        # the delay slot after the jal stays as it is
        put(va, [('jal', STRLEN)], [('jal', ctr)])
        put(va + 8, [('subu', 'v0', 's6', 'v0'), ('sll', 'a0', 'v0', 1), ('addu', 'a0', 'a0', 'v0')],
            [('subu', 'v0', 's6', 't0'), ('sra', 'a0', 'v0', 1), ('nop',)])


# Fencing (SCOM.BIN) name plates: three sites compute x = (14 - strlen(name)) * 3 before the pen call.
#   jal strlen / move a0, v0 / addiu a0, zero, 0xe / subu / sll / addu / jal pen
# -> move a0, v0 / jal ctr / addiu a1, zero, PLATE_PX / move a0, v0 / nop / nop / jal pen
# The plate windows are widened by progstr.LAYOUT (92 -> 120 px; the text rectangle is 8 px less).
PLATE_SITES = (0x801602f0, 0x80161170, 0x80161b18)
PLATE_PX = 112
SCOM_BASE = 0x8015b858


def plates(scom):
    """Patch the name plate centring of SCOM.BIN (bytearray) to call `ctr`."""
    labels = blob()[1]
    for va in PLATE_SITES:
        o = va - SCOM_BASE
        old = struct.unpack_from('<6I', scom, o)
        assert old == (0x0c02c120, 0x00402021, 0x2404000e, 0x00822023, 0x00041040, 0x00442021), hex(va)
        scom[o:o + 24] = asm.assemble(va, [
            ('or', 'a0', 'v0', 'zero'), ('jal', labels['ctr']), ('addiu', 'a1', 'zero', PLATE_PX),
            ('or', 'a0', 'v0', 'zero'), ('nop',), ('nop',)])


# The same centring in the overlays: jal strlen / <delay> / x = (K - strlen) * 3 + C ... / jal pen.
# The jal goes to `ctr` (its a1 is not set, so its v0 is unused) and the arithmetic becomes
#   addiu a0, zero, K * 6 + 2 * C / subu a0, a0, t0 / sra a0, a0, 1        (t0 = pixels from ctr)
# in the same slots; the jal and its delay slot stay where they are (two of the sites sit inside a run of
# stack-string stores that stackstr.py rewrites). No clamp: a text wider than K * 6 + 2 * C px gets a
# negative x, as a long text did before.
#   (overlay, jal site, K * 6 + 2 * C, words of the old arithmetic, instructions kept at its end)
CENTRES = (
    ('HANA', 0x801617c0, 78, 4, ()),                                   # "how many rounds" choices
    ('HANA', 0x80161c7c, 84 + 20, 5, ()),                              # lessons menu (shadow)
    ('HANA', 0x80161cb8, 84 + 18, 5, (('addiu', 's1', 's1', 1),)),     # lessons menu
    ('HANA', 0x8016c808, 60 + 24, 5, ()),                              # Card Help: first special card
    ('HANA', 0x8016c850, 36 + 0x98, 5, ()),                            # Card Help: second special card
    ('PERS', 0x801643c0, 96 + 10, 4, ()),                              # debate round panel: names
    ('PERS', 0x80164438, 96 + 0x12a, 4, ()),
    ('PERS', 0x80164490, 96 + 8, 4, ()),
    ('PERS', 0x801644e8, 96 + 0x128, 4, ()),
    ('PERS', 0x80164c04, 96 + 24, 4, ()),
    ('PERS2', 0x801e6d70, 96, 4, ()),
    ('PERS2', 0x801e8940, 132, 4, ()),
    ('SCOM', 0x8015cd48, 90, 4, ()),                                   # fencing mode menu
    ('STAFF', 0x8015cb10, 180, 9, ()),                                 # staff roll
    ('STAFF', 0x8015cf2c, 180, 10, (('lh', 'a1', 0, 's1'),)),
)
PEN = 0x800a3ef0


def centres(prog):
    """Patch the strlen-based centring sites of the overlays (dict tag -> bytearray)."""
    ctr = blob()[1]['ctr']
    for tag, va, px, n, keep in CENTRES:
        d, o = prog[tag], va - (0x801e0000 if tag == 'PERS2' else SCOM_BASE)
        assert d[o:o + 4] == asm.assemble(va, [('jal', STRLEN)]), hex(va)
        assert d[o + 8 + 4 * n:o + 12 + 4 * n] == asm.assemble(va + 8 + 4 * n, [('jal', PEN)]), hex(va)
        if keep:
            assert d[o + 8 + 4 * (n - len(keep)):o + 8 + 4 * n] == asm.assemble(0, list(keep)), hex(va)
        new = [('addiu', 'a0', 'zero', px), ('subu', 'a0', 'a0', 't0'), ('sra', 'a0', 'a0', 1)]
        new += [('nop',)] * (n - 3 - len(keep)) + list(keep)
        d[o:o + 4] = asm.assemble(va, [('jal', ctr)])
        d[o + 8:o + 8 + 4 * n] = asm.assemble(va + 8, new)


if __name__ == '__main__':
    b, labels = blob()
    print('cave %#x: %d bytes; %s' % (CAVE, len(b), ', '.join('%s %#x' % kv for kv in labels.items())))
    print('glyphs: %d punctuation at %d..%d' % (len(PUNCT), FIRST_FREE, FIRST_FREE + len(PUNCT) - 1))
