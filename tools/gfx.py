"""Graphics redrawn in English at build time (our own lettering, tools/pixfont.py).

The .I2 graphic containers have no header: the program reads pieces by sector with
0x8009f47c(name, buf, sector, count) and sends them to VRAM (0x800b6bbc palette of 16, 0x800b6b58
palette of 256, 0x800b6a70 pixels). A 4bpp piece = 32 bytes of palette + pixels. `tools/dev/gfxcalls.py`
lists the calls, `tools/dev/rawgfx.py` shows a piece.

CG/WINFRAME.I2, the HUD glyph strips (icons of the glyph routine 0x800a2e18, codes 0x100-0x12b, written in
strings as ESC m + chr(0x30 + n)):
  sector 0   156 x 12  date digits 0-9 and 年 月 日 (icons 0x10c-0x118)
  sector 2   240 x 12  7 era names of 24 px (0x119-0x11f), 行動力 and 所持金 of 36 px (0x120, 0x121)
  sector 13   24 x 12  回戦 (0x122);  sector 94: button icons;  sector 95: the yes / no box

Date bar (0x800a8dc0): "ESC m %c %b ESC m F %4b" era + year of the era + 年 + Western year at (4, 6),
ESC m P = 行動力 at (104, 6), "%2b ESC m G %2b ESC m H" month 月 day 日 at (12, 22), "ESC m Q %6g" =
所持金 + money at (104, 22). English: the era names are drawn again in the strip with their own widths
(ERAS; the glyph routine reads (u, width) from a table in the cave and advances by the width), the
other labels are text through the formats in tl/progstr/90_columns.txt ("Ansei 4 1857", "6/6", Drive,
Funds).

Also here (see the comments at each): the six title tiles (a picture inside the INIT overlay), the name
plates of the protagonist cards (CG/INIT.I2), the scroll of the mash contest (CG/RENDA.I2) and the
district shapes of the town map (CG/SELECTOR.I2 + two tables in COM.BIN).

usage: python3 tools/gfx.py [preview.png]      (layout; needs pillow for the picture)
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, pixfont, text, vwf

AT, END = 0x800cefb0, 0x800cf010          # cave: after vwf.py's code, before grid.py's tables
PEN_X = 0x8010d730
ERAS = ['Kaei', 'Ansei', "Man'en", 'Bunkyū', 'Genji', 'Keiō', 'Meiji']      # icons 0x119..0x11f
STRIP = (2, 240, 12)                      # sector, width, height
INK, EDGE = 15, 1                         # white, opaque black (palette of the strip: grey ramp)
ERA_AT = 0x800a307c                       # era branch of the glyph routine: 15 words up to its jump
ERA_Y = 0x800a306c                        # addiu v0, v0, -2 (sprite y = pen y - 2)
_G = pixfont.glyphs()


def draw(px, w, h, x0, s, ink=INK, edge=EDGE, y0=0):
    """Draw s at (x0 + 1, y0) into px (list of rows of colour indices) with a 1 px dark edge; returns
    the width (edges included)."""
    pts, x = [], x0 + 1
    for ch in text.fold(s):
        rows, adv = _G[ch]
        for y in range(len(rows)):
            for i in range(8):
                if rows[y] & (0x80 >> i) and y0 + y < h:
                    pts.append((x + i, y0 + y))
        x += adv
    for (a, b) in pts:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if 0 <= a + dx < w and 0 <= b + dy < h:
                    px[b + dy][a + dx] = edge
    for (a, b) in pts:
        px[b][a] = ink(b) if callable(ink) else ink
    return x - x0 + 1


def pack4(px):
    out = bytearray()
    for row in px:
        for i in range(0, len(row), 2):
            out.append(row[i] | row[i + 1] << 4)
    return bytes(out)


def eras():
    """(pixel rows of the strip, [(u, width)] per era)."""
    sec, w, h = STRIP
    px = [[0] * w for _ in range(h)]
    cells, u = [], 0
    for e in ERAS:
        n = draw(px, w, h, u, e)
        n += n & 1
        cells.append((u, n))
        u += n + 2
    assert u <= w, 'era names: %d px of %d' % (u, w)
    return px, cells


def unpack4(b, w, h):
    return [[(b[(y * w + x) // 2] >> 4) if x & 1 else b[(y * w + x) // 2] & 15 for x in range(w)] for y in range(h)]


# Yes / no box of the confirmations: sector 95, two palettes (one per highlighted side) + 56 x 32 pixels.
# Two plaques of 19 x 20 px: はい (fill 7, letters 9, edge 11) and いいえ (fill 8, letters 10, edge 11).
YESNO = (95, 56, 32)
PLAQUES = (('Yes', 6, 7, 9), ('No', 31, 8, 10))      # text, x, fill, ink
PLAQUE_Y, PLAQUE_W, PLAQUE_H, PLAQUE_EDGE = 6, 19, 20, 11


def yesno(px):
    for s, x0, fill, ink in PLAQUES:
        for y in range(PLAQUE_Y, PLAQUE_Y + PLAQUE_H):
            px[y][x0:x0 + PLAQUE_W] = [fill] * PLAQUE_W
        n = vwf.width(text.fold(s)) + 1               # ink + the two edges
        assert n <= PLAQUE_W, s
        draw(px, YESNO[1], YESNO[2], x0 + (PLAQUE_W - n) // 2, s, ink, PLAQUE_EDGE, PLAQUE_Y + 5)
    return px


# Labels of the icon menus (district, building, meeting ...): sectors 60-93 = 60 pieces of 96 x 24 px, no
# palette, back to back (piece n at n * 1152; n = the menu item's field +0x14; loaders 0x800a4470 /
# 0x800a46d0 send one to VRAM 448,448). Letters: rows 7..17, colours 1..8 from top to bottom (palette in
# the program, red set when selected), edge 9.
LABELS = (60, 96, 24, 60)                 # sector, width, height, pieces
LABEL_Y, LABEL_EDGE = 7, 9
LABEL_TL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tl', 'gfx', 'labels.txt')


def label_ink(y):
    return max(1, min(8, y - LABEL_Y - 2))


def labels():
    """{number: English} of tl/gfx/labels.txt."""
    out = {}
    for line in open(LABEL_TL, encoding='utf-8').read().splitlines():
        if line.strip() and not line.startswith('#'):
            n, _, t = line.partition('\t')
            out[int(n)] = t
    return out


def label(s):
    sec, w, h, _ = LABELS
    px = [[0] * w for _ in range(h)]
    n = draw(px, w, h, 0, s, label_ink, LABEL_EDGE, LABEL_Y)
    if n > w:
        raise ValueError('label %r: %d px of %d' % (s, n, w))
    return pack4(px)


# Ideology tags of the cards (icons 0x106-0x10b: 佐幕 尊王 攘夷 開国 主戦 穏健): sector 31 = six pieces of
# 32 B palette + 24 x 12 pixels (stride 0xb0), sent side by side to one VRAM strip (u 0x60 + 24 n, v 0xf0)
# and drawn by the glyph routine with the piece's own palette. English: the strip is one 144 px canvas,
# each plaque as wide as its word (the routine reads (u, width) from a table in the cave, as the eras);
# one tag of each pair is at most 72 px together, as the three Japanese tags.
TAGS = (31, 24, 12, 0xb0, 6)              # sector, width, height, stride, pieces
TAG_TEXT = ('Sab', 'Son', 'Jōi', 'Open', 'Mil', 'Mod')
TAG_AT = 0x800a2f84                       # tag branch of the glyph routine: 10 words, then the jump
TAG_U = 0x60


def tags(data):
    """(pixel rows of the 144 px strip, [(u, width)] per tag); data = CG/WINFRAME.I2."""
    sec, w, h, stride, n = TAGS
    px = [[0] * (w * n) for _ in range(h)]
    cells, u = [], 0
    for i, s in enumerate(TAG_TEXT):
        o = sec * 2048 + i * stride + 32
        old = unpack4(data[o:o + w * h // 2], w, h)
        lit, shade = old[0][1], old[1][w - 2]         # bevel colours of the plaque
        t = text.fold(s)
        cw = vwf.width(t) - 1 + 4                     # ink + pad + border on both sides
        for y in range(h):
            for x in range(cw):
                px[y][u + x] = lit if y == 0 or x == 0 else shade if y == h - 1 or x == cw - 1 else 1
        x = u + 2
        for ch in t:
            rows, adv = _G[ch]
            for y in range(len(rows)):
                for b in range(8):
                    if rows[y] & (0x80 >> b) and 1 <= y + 1 < h - 1:
                        px[y + 1][x + b] = 15
            x += adv
        cells.append((u, cw))
        u += cw
    assert u <= w * n, 'ideology tags: %d px of %d' % (u, w * n)
    assert max(cells[0][1], cells[1][1]) + max(cells[2][1], cells[3][1]) + max(cells[4][1], cells[5][1]) <= 72
    return px, cells


# Building stamps of the district map: WINFRAME sectors 17-30, read by COM 0x80174954 = a 72 x 48 px 8bpp
# paper backdrop at +0x200, two palettes of 256 at +0x1000 / +0x1200 (red = under the cursor / brown) and
# 38 stamps of 24 x 24 px 8bpp from +0x1400 (576 bytes each). Stamp number = field +4 of the building's
# 40-byte record (table 0x800e18bc, 742 buildings). Colour 0 is transparent (the paper shows), 1..47 are a
# noisy seal texture. Every stamp with kanji is drawn again with words in a 3 x 5 letter face (lines
# divided by /; one line = letters twice as tall; a full frame when the words fit 18 px, else a rule
# above and below). '^' = keep the picture in the top 14 rows (the foreign houses: only the kanji under
# the roof go). Pictures without writing stay: bath 6 / 7, temple 17, shrine 18. As in the Japanese, some
# kinds share a stamp: 1 / 4 restaurant, 8 / 9 shop, 23 / 25 townsfolk (scholar's home, town house),
# 32-34 magistrate (gaol, execution ground, magistrate's office), 35-37 sights.
STAMPS = (17, 0x1400, 24, 38)             # sector, offset, size, pieces
STAMP_TEXT = {0: 'INN', 1: 'DINE', 2: 'EATS', 3: 'SAKE', 4: 'DINE', 5: 'TEA', 8: 'SHOP', 9: 'SHOP',
              10: 'GOODS', 11: 'SWORD', 12: 'JOBS', 13: 'DOCTOR', 14: 'PHOTO', 15: '^TRADE', 16: '^ENVOY',
              19: 'HAN/HOUSE', 20: 'CASTLE', 21: 'PALACE', 22: 'SAMU/RAI', 23: 'TOWN/FOLK', 24: 'NOBLE',
              25: 'TOWN/FOLK', 26: 'SHIN/SEN/GUMI', 27: 'KAME/YAMA', 28: 'DŌJŌ', 29: 'ACAD/EMY',
              30: 'HAN/SCHOOL', 31: 'NAVY', 32: 'MAGIS/TRATE', 33: 'MAGIS/TRATE', 34: 'MAGIS/TRATE',
              35: 'SIGHTS', 36: 'SIGHTS', 37: 'SIGHTS'}
STAMP_KEEP = 14                           # rows of picture kept by '^'
_TINY = """
A .#. #.# ### #.# #.#
B ##. #.# ##. #.# ##.
C .## #.. #.. #.. .##
D ##. #.# #.# #.# ##.
E ### #.. ##. #.. ###
F ### #.. ##. #.. #..
G .## #.. #.# #.# .##
H #.# #.# ### #.# #.#
I ### .#. .#. .#. ###
J ..# ..# ..# #.# .#.
K #.# #.# ##. #.# #.#
L #.. #.. #.. #.. ###
M #.# ### ### #.# #.#
N ##. #.# #.# #.# #.#
O .#. #.# #.# #.# .#.
P ##. #.# ##. #.. #..
R ##. #.# ##. #.# #.#
S .## #.. .#. ..# ##.
T ### .#. .#. .#. .#.
U #.# #.# #.# #.# .##
V #.# #.# #.# #.# .#.
W #.# #.# ### ### #.#
X #.# #.# .#. #.# #.#
Y #.# #.# .#. .#. .#.
"""
TINY = {l[0]: l[2:].split() for l in _TINY.strip().splitlines()}




def tiny_width(s):
    return len(s) * 4 - 1


def stamp(old, words, dark):
    """One 24 x 24 stamp (bytes). The frame takes the colours of the old stamp's own pixels in order (it
    keeps its texture); the letters take only its darkest third (dark = colour numbers sorted from dark
    to light in the brown palette), or 1 px strokes vanish on the paper."""
    n = STAMPS[2]
    keep = words.startswith('^')
    lines = words.lstrip('^').split('/')
    ink = [v for v in old if v] or [20]
    used = [v for v in dark if v in set(ink)]
    deep = set(used[:max(1, len(used) // 3)])
    deep = [v for v in ink if v in deep]
    wide = max(tiny_width(l) for l in lines)
    assert wide <= n - 1, words
    on, letters = set(), set()
    macron = any(c in 'ŌŪ' for c in words)
    tall = 2 if len(lines) == 1 and not keep else 1
    if keep:
        y = STAMP_KEEP + 3
    else:
        for x in range(n):                        # frame: 2 px rules; sides only when the words leave room
            on.update(((x, 0), (x, 1), (x, n - 2), (x, n - 1)))
        if wide <= n - 6:
            for y in range(n):
                on.update(((0, y), (1, y), (n - 2, y), (n - 1, y)))
        pitch = 8 if macron else 7 if len(lines) < 3 else 6
        high = (len(lines) - 1) * pitch + 5 * tall
        y = (n - high + 1) // 2 + (1 if macron else 0)
    for l in lines:
        x = (n - tiny_width(l) + 1) // 2
        for ch in l:
            base = {'Ō': 'O', 'Ū': 'U'}.get(ch, ch)
            if base != ch:
                letters.update((x + i, y - 2) for i in range(3))
            for r, row in enumerate(TINY[base]):
                for t in range(tall):
                    letters.update((x + i, y + r * tall + t) for i in range(3) if row[i] == '#')
            x += 4
        y += pitch if not keep else 0
    out = bytearray(n * n)
    k = 0
    for yy in range(n):
        for xx in range(n):
            if (xx, yy) in letters:
                out[yy * n + xx] = deep[k % len(deep)]
            elif keep and yy < STAMP_KEEP:
                out[yy * n + xx] = old[yy * n + xx]
            elif (xx, yy) in on:
                out[yy * n + xx] = ink[k % len(ink)]
            k += 7
    return bytes(out)


def stamps(d):
    sec, at, n, count = STAMPS
    pal = struct.unpack_from('<256H', d, sec * 2048 + 0x1200)
    dark = sorted(range(1, 256), key=lambda v: (pal[v] & 31) + (pal[v] >> 5 & 31) + (pal[v] >> 10 & 31))
    for i, words in STAMP_TEXT.items():
        assert i < count
        o = sec * 2048 + at + i * n * n
        d[o:o + n * n] = stamp(d[o:o + n * n], words, dark)


def winframe(data):
    """CG/WINFRAME.I2 with the era strip, the yes / no box and the icon labels drawn in English."""
    d = bytearray(data)
    sec, w, h = STRIP
    px, _ = eras()
    o = sec * 2048 + 32
    d[o:o + w * h // 2] = pack4(px)
    sec, w, h = YESNO
    o = sec * 2048 + 64
    d[o:o + w * h // 2] = pack4(yesno(unpack4(d[o:o + w * h // 2], w, h)))
    sec, w, h, n = LABELS
    size = w * h // 2
    for i, s in labels().items():
        assert 0 <= i < n
        o = sec * 2048 + i * size
        d[o:o + size] = label(s)
    sec, w, h, stride, n = TAGS
    px, _ = tags(data)
    for i in range(n):
        o = sec * 2048 + i * stride + 32
        d[o:o + w * h // 2] = pack4([row[i * w:(i + 1) * w] for row in px])
    stamps(d)
    return bytes(d)


# Ideology chart of the goal and person screens: INFOCOM/GRAPH.I2 = palette of 16 in sector 0, then 29
# backgrounds of 144 x 128 px 4bpp, 5 sectors each (28 group crests + a plain one; table 0x800e0560).
# Every piece carries the six axis labels (letters colour 13, edge 1) at the same places. The kanji are
# taken out (each pixel takes the nearest background pixel of its row; the axis lines are drawn again)
# and the words of the status screen are written: text, alignment (-1 left, 0 centre, 1 right), x, y.
GRAPH = (1, 144, 128, 5, 29)              # first sector, width, height, sectors per piece, pieces
GRAPH_INK, GRAPH_EDGE = 13, 1
GRAPH_BOXES = ((58, 2, 86, 15), (2, 50, 30, 63), (114, 50, 142, 63), (58, 98, 87, 111),
               (2, 112, 30, 125), (113, 112, 142, 125))
GRAPH_LINES = ((56, None, 13), (118, None, 11), (None, 72, None))     # (row, column, colour or None = as outside)
GRAPH_TEXT = (('Open', 0, 72, 2), ('Sabaku', -1, 3, 51), ('Sonnō', 1, 141, 51), ('Jōi', 0, 72, 98),
              ('Militant', -1, 3, 113), ('Moderate', 1, 141, 113))


def chart(px):
    """One chart background (rows of colour indices) with English axis labels."""
    w, h = GRAPH[1], GRAPH[2]
    for x0, y0, x1, y1 in GRAPH_BOXES:
        for y in range(y0, y1):
            bad = [x for x in range(x0, x1) if px[y][x] in (GRAPH_INK, GRAPH_EDGE)]
            row = list(px[y])
            for x in bad:
                for d in range(1, w):
                    c = [row[q] for q in (x - d, x + d) if 0 <= q < w and not (x0 <= q < x1 and q in bad)]
                    if c:
                        px[y][x] = c[0]
                        break
        for ly, lx, col in GRAPH_LINES:
            if ly is not None and y0 <= ly < y1:
                px[ly][x0:x1] = [col] * (x1 - x0)
            if lx is not None and x0 <= lx < x1:
                for y in range(y0, y1):
                    px[y][lx] = px[y0 - 1][lx] if y0 > 16 else px[y1][lx]
    for s, align, x, y in GRAPH_TEXT:
        n = vwf.width(text.fold(s)) + 1
        draw(px, w, h, x - n // 2 if align == 0 else x - n + 1 if align > 0 else x, s, GRAPH_INK, GRAPH_EDGE, y)
    return px


def graph(data):
    """INFOCOM/GRAPH.I2 with English chart labels."""
    d = bytearray(data)
    sec, w, h, step, n = GRAPH
    for i in range(n):
        o = (sec + step * i) * 2048
        d[o:o + w * h // 2] = pack4(chart(unpack4(d[o:o + w * h // 2], w, h)))
    return bytes(d)


# Debate result panels: CG/SETTOKU.I2 sectors 0-14, read by PERS2 0x801e7448: palette of 16 at 0, the
# chart panel 104 x 72 px 4bpp at +0x800 (fill 4, letters 10, edge 1; the two axes and the base line),
# then six tags of 12 x 12 px 4bpp at +0x2000 + 0x1000 n with their own palettes at +0x1800 + 0x1000 n
# (佐 尊 攘 開 主 穏, white kanji on a coloured texture; shown beside the three numbers at panel x 65:
# now three letters on one flat dark colour of the same palette, a texture hides 1 px strokes).
# The kanji around the chart are painted over and written again in the 3 x 5 face, twice as tall; the
# position dots are plotted on the lines, so the words stay outside them as the kanji did.
SETTOKU = (0x800, 104, 72)
SETTOKU_FILL, SETTOKU_INK, SETTOKU_EDGE = 4, 10, 1
SETTOKU_BOXES = ((29, 3, 43, 15), (4, 25, 19, 39), (52, 25, 65, 39), (29, 51, 43, 65), (4, 56, 19, 69),
                 (52, 56, 65, 69))
SETTOKU_LINES = ((35, 15, 35, 50), (19, 32, 51, 32), (18, 65, 50, 65))     # x0, y0, x1, y1
SETTOKU_TEXT = (('OPEN', 28, 4), ('SAB', 5, 28), ('SON', 53, 28), ('JŌI', 30, 54), ('MIL', 5, 58), ('MOD', 53, 58))
SETTOKU_TAGS = (0x2000, 0x1000, 12, ('SAB', 'SON', 'JŌI', 'OPN', 'MIL', 'MOD'))


def tiny(s, x, y, tall=2):
    """Pixels of s in the 3 x 5 face at (x, y); a macron is a bar two rows above the letter."""
    pts = set()
    for ch in s:
        base = {'Ō': 'O', 'Ū': 'U'}.get(ch, ch)
        if base != ch:
            pts.update((x + i, y - 2) for i in range(3))
        for r, row in enumerate(TINY[base]):
            for t in range(tall):
                pts.update((x + i, y + r * tall + t) for i in range(3) if row[i] == '#')
        x += 4
    return pts


def settoku(data):
    """CG/SETTOKU.I2 with English labels on the debate result panel and its six tags."""
    d = bytearray(data)
    at, w, h = SETTOKU
    px = unpack4(d[at:at + w * h // 2], w, h)
    for x0, y0, x1, y1 in SETTOKU_BOXES:
        for y in range(y0, y1):
            px[y][x0:x1] = [SETTOKU_FILL] * (x1 - x0)
    for y in range(3, h - 3):                     # the old lines go, the new ones are a little shorter
        for x in range(3, 66):
            if px[y][x] == SETTOKU_INK:
                px[y][x] = SETTOKU_FILL
    for x0, y0, x1, y1 in SETTOKU_LINES:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px[y][x] = SETTOKU_INK
    for s, x, y in SETTOKU_TEXT:
        pts = tiny(s, x, y)
        for a, b in pts:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    assert 3 <= a + dx < 65 and 3 <= b + dy < h - 3, s
                    px[b + dy][a + dx] = SETTOKU_EDGE
        for a, b in pts:
            px[b][a] = SETTOKU_INK
    d[at:at + w * h // 2] = pack4(px)
    at, step, n, words = SETTOKU_TAGS
    for i, s in enumerate(words):
        o = at + step * i
        pal = struct.unpack_from('<16H', d, o - 0x800)
        lum = lambda v: (pal[v] & 31) + (pal[v] >> 5 & 31) + (pal[v] >> 10 & 31)
        old = unpack4(d[o:o + n * n // 2], n, n)
        hue = lambda v: max(pal[v] & 31, pal[v] >> 5 & 31, pal[v] >> 10 & 31) - min(pal[v] & 31, pal[v] >> 5 & 31, pal[v] >> 10 & 31)
        dark = [v for v in range(1, 16) if 14 <= lum(v) <= 42]
        back = max(dark, key=lambda v: (hue(v), -v))      # one flat, dark colour of the tag's hue
        pts = tiny(s, 1, 2 if 'Ō' in s else 1)
        out = []
        for y in range(n):
            row = []
            for x in range(n):
                row.append(15 if (x, y) in pts else back)
            out.append(row)
        d[o:o + n * n // 2] = pack4(out)
    return bytes(d)


# Dealer marker of the hanafuda table (親): CG/HANAPS.I2, palette of 256 at 0x22000, 20 x 20 px 8bpp at
# 0x22800 (HANA 0x80167508 -> VRAM 752,?). The frame stays, the field (x 2..17, y 2..17) is filled flat and
# takes DEAL in the 3 x 5 face twice as tall.
HANAPS = (0x22800, 20, 0x19, 0x25)            # pixels, size, fill, ink


def hanaps(data):
    d = bytearray(data)
    at, n, fill, ink = HANAPS
    for y in range(2, n - 2):
        for x in range(2, n - 2):
            d[at + y * n + x] = fill
    for x, y in tiny('DEAL', 3, 5):
        assert 2 <= x < n - 2 and 2 <= y < n - 2
        d[at + y * n + x] = ink
    return bytes(d)


# Festival lanterns of Belongings > Sights (COM 0x8016eae0 / 0x8016ec80): INFOCOM/CHOTIN.I2 = palette of
# 256 in sector 0 + a 48 x 224 px 8bpp sheet in sectors 1-6 (lit: festival seen; VRAM 0x340,0x100), the same
# again in sectors 7 / 8-13 (unlit; VRAM 0x380). 14 lanterns of 24 x 32 px, number n at column n / 7, row
# n % 7, each with a festival name in brush kanji; the screen shows eleven (5, 9, 13 are never drawn). The
# kanji are painted over row by row (the paper has horizontal ribs) and the name is written in the 3 x 5 face
# twice as tall. The ink mask comes from the lit sheet (bright paper) and serves both sheets.
CHOTIN = ((0, 2048), (7 * 2048, 8 * 2048), 48, 24, 32)       # (palette, pixels) lit, unlit; sheet width; cell
CHOTIN_TEXT = ('NEPU/TA', 'KAN/TŌ', 'NAMA/HAGE', 'TANA/BATA', 'SANJA', 'FIRE/WORKS', 'ONBA/SHIRA', 'OWARA',
               'GION', 'DAI/MONJI', 'DAN/JIRI', 'SAI/DAIJI', 'AWA/ODORI', 'OKUN/CHI')
CHOTIN_BOX = (3, 4, 21, 28)                   # paper: x0, y0, x1, y1 (kanji and letters stay inside)
CHOTIN_INK = 30                               # brightness (sum of 5-bit r g b) up to which a pixel is ink


def chotin(data):
    """INFOCOM/CHOTIN.I2 with the festival names of the 14 lanterns in English."""
    d = bytearray(data)
    (pal_a, pix_a), (pal_b, pix_b), sw, cw, ch = CHOTIN
    x0, y0, x1, y1 = CHOTIN_BOX
    pal = struct.unpack_from('<256H', d, pal_a)
    lum = [(c & 31) + (c >> 5 & 31) + (c >> 10 & 31) for c in pal]
    for n, words in enumerate(CHOTIN_TEXT):
        cx, cy = n // 7 * cw, n % 7 * ch
        at = lambda pix, x, y: pix + (cy + y) * sw + cx + x
        ink = {(x, y) for y in range(y0, y1) for x in range(x0, x1)
               if d[at(pix_a, x, y)] and lum[d[at(pix_a, x, y)]] <= CHOTIN_INK}
        mask = {(x + i, y + j) for x, y in ink for i in (-1, 0, 1) for j in (-1, 0, 1)
                if x0 <= x + i < x1 and y0 <= y + j < y1}
        lines = words.split('/')
        gap = 4 if any(c in 'ŌŪ' for c in lines[-1]) else 2
        high = len(lines) * 10 + (len(lines) - 1) * gap
        y = (y0 + y1 - high + 1) // 2
        pts = set()
        for l in lines:
            pts |= tiny(l, (cw - tiny_width(l) + 1) // 2, y)
            y += 10 + gap
        assert all(2 <= a < cw - 2 and y0 <= b < y1 for a, b in pts), words     # paper = x 2..21
        halo = {(a + i, b + j) for a, b in pts for i in (-1, 0, 1) for j in (-1, 0, 1)} - pts
        for pal_at, pix in ((pal_a, pix_a), (pal_b, pix_b)):
            cols = struct.unpack_from('<256H', d, pal_at)
            lm = [(c & 31) + (c >> 5 & 31) + (c >> 10 & 31) for c in cols]
            sat = lambda v: max(cols[v] & 31, cols[v] >> 5 & 31, cols[v] >> 10 & 31) - min(cols[v] & 31, cols[v] >> 5 & 31, cols[v] >> 10 & 31)
            black = min((v for v in range(1, 256) if cols[v]), key=lambda v: lm[v])     # 0x0000 would be transparent
            paper = sorted((d[at(pix, x, y)] for y in range(y0, y1) for x in range(x0, x1)
                            if (x, y) not in mask and sat(d[at(pix, x, y)]) <= 8), key=lambda v: lm[v])
            light = paper[len(paper) * 9 // 10]           # a pale, unsaturated paper colour: outline of the letters
            for y in range(y0, y1):
                row = [d[at(pix, x, y)] for x in range(cw)]
                free = [x for x in range(cw) if row[x] and (x, y) not in mask and 2 <= x < cw - 2]
                for x in range(x0, x1):
                    if (x, y) in mask and free:
                        src = min(free, key=lambda f: (abs(f - x), (f + y) & 1))
                        d[at(pix, x, y)] = row[src]
            for a, b in halo:
                if 2 <= a < cw - 2 and y0 <= b < y1 and d[at(pix, a, b)]:
                    d[at(pix, a, b)] = light
            for a, b in pts:
                d[at(pix, a, b)] = black
    return bytes(d)


# Battle field marks (WAR): CG/HEXADD.I2 sector 297 = palette of 16 + a 256 x 160 px 4bpp sheet of 64 x 32
# cells (rings, arrows, cross; VRAM 960,256; table of {sector, count} at WAR 0x80169b8c). Three cells hold
# the attack mark 斬 in three sizes, one the retreat square 退 (dotted diamond, kept). Ink 7, shadow 6.
HEXADD = (297, 256, 160)
HEX_CUT = ((128, 64, 0), (192, 64, 1), (0, 96, 2))        # cell x, y, size (0 tiny, 1 pixfont, 2 doubled)
HEX_RETREAT = (128, 96)


def _points(s, size):
    """(set of points, width, height) of s: 3 x 5 face twice as tall, pixfont, or pixfont doubled."""
    if size == 0:
        pts = tiny(s, 0, 0)
    elif size == 2:
        px, w, h = banner(s)
        pts = {(x, y) for y in range(h) for x in range(w) if px[y][x] >= 13}
    else:
        pts, x = set(), 0
        for ch in text.fold(s):
            rows, adv = _G[ch]
            pts.update((x + i, y) for y in range(len(rows)) for i in range(8) if rows[y] & (0x80 >> i))
            x += adv
    x0, y0 = min(a for a, b in pts), min(b for a, b in pts)
    pts = {(a - x0, b - y0) for a, b in pts}
    return pts, max(a for a, b in pts) + 1, max(b for a, b in pts) + 1


def hexadd(data):
    d = bytearray(data)
    sec, w, h = HEXADD
    at = sec * 2048 + 32
    px = unpack4(d[at:at + w * h // 2], w, h)

    def put(s, cx, cy, size, shadow):
        pts, tw, th = _points(s, size)
        x0, y0 = cx + (64 - tw) // 2, cy + (32 - th) // 2
        assert tw <= 62 and th <= 30, s
        if shadow:
            for a, b in pts:
                px[y0 + b + 1][x0 + a + 1] = 6
        for a, b in pts:
            px[y0 + b][x0 + a] = 7

    for cx, cy, size in HEX_CUT:
        for y in range(cy, cy + 32):
            px[y][cx:cx + 64] = [0] * 64
        put('CUT', cx, cy, size, size > 0)
    cx, cy = HEX_RETREAT
    for y in range(cy + 7, cy + 25):              # the kanji inside the diamond
        for x in range(cx + 21, cx + 43):
            px[y][x] = 0
    put('RETREAT', cx, cy, 0, False)
    d[at:at + w * h // 2] = pack4(px)
    return bytes(d)


# Title tiles: an 8bpp picture of 120 x 96 px inside the INIT overlay (0x80163ae0; two palettes of 256 at
# 0x801636e0: selected, dimmed), sent to VRAM 512,256. Six tiles of 40 x 48: 新規 再開 環境 / 練習 閲覧 音楽.
# The field inside the frame is x 5..33, y 5..42 of a tile (gold noise; the brush letters cover its
# middle in every tile, so the field is filled again from the gold pixels around: fixed seed).
TILES_AT, TILES_W, TILES_H = 0x80163ae0 - 0x8015b858, 120, 96
TILE_W, TILE_H, FIELD = 40, 48, (5, 5, 34, 43)        # field x0, y0, x1, y1
TILE_TEXT = ('New', 'Load', 'Setup', 'Drills', 'View', 'Music')
TILE_INK, TILE_SHADE, TILE_GOLD = (0x80, 0x77, 0x6e), 2, 0xc1    # ink top / middle / bottom, shadow, first gold


def tiles(init):
    """INIT.BIN (bytes) with the six title tiles lettered in English (letters twice as tall)."""
    import random
    d = bytearray(init)
    at = lambda x, y: TILES_AT + y * TILES_W + x
    x0, y0, x1, y1 = FIELD
    for n, s in enumerate(TILE_TEXT):
        rnd = random.Random(n)
        ox, oy = n % 3 * TILE_W, n // 3 * TILE_H
        gold = {(x, y): d[at(ox + x, oy + y)] for y in range(y0, y1) for x in range(x0, x1)}
        clean = {p: v for p, v in gold.items() if v >= TILE_GOLD and all(
            gold.get((p[0] + dx, p[1] + dy), 255) >= TILE_GOLD for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2))}
        for (x, y) in gold:
            if (x, y) not in clean:
                near = [v for (a, b), v in clean.items() if abs(a - x) <= 7 and abs(b - y) <= 7] or list(clean.values())
                d[at(ox + x, oy + y)] = rnd.choice(near)
        w = vwf.width(text.fold(s))
        assert w <= x1 - x0 - 1, s
        px, x = ox + x0 + (x1 - x0 - w) // 2, 0
        py = oy + y0 + (y1 - y0 - 18) // 2
        pts = []
        for ch in text.fold(s):
            rows, adv = _G[ch]
            for y in range(len(rows)):
                for i in range(8):
                    if rows[y] & (0x80 >> i):
                        pts += [(px + x + i, py + y * 2), (px + x + i, py + y * 2 + 1)]
            x += adv
        for (a, b) in pts:
            d[at(a + 1, b + 1)] = TILE_SHADE
        for (a, b) in pts:
            d[at(a, b)] = TILE_INK[min(2, (b - py) // 6)]
    return bytes(d)


# Protagonist cards: CG/INIT.I2 sectors 34 / 43 / 52 / 61 = four 8bpp pieces of 120 x 136 px (palette of
# 256, then pixels). The name plate is rows 113..132, columns 3..116: a horizontal grey gradient (every
# column one colour, row 113 is free of letters) with the name in white, black outline.
CARDS = ((34, 'Sakamoto Ryōma'), (43, 'Hijikata Toshizō'), (52, 'Own Hero (Male)'), (61, 'Own Hero (Female)'))
CARD_W, PLATE = 120, (3, 113, 117, 133)               # plate x0, y0, x1, y1


def cards(data):
    """CG/INIT.I2 with the four name plates in English (letters struck twice: bold)."""
    d = bytearray(data)
    x0, y0, x1, y1 = PLATE
    for sec, s in CARDS:
        o = sec * 2048
        pal = struct.unpack_from('<256H', d, o)
        lum = [(c & 31) + (c >> 5 & 31) + (c >> 10 & 31) for c in pal]
        at = lambda x, y: o + 512 + y * CARD_W + x
        used = {d[at(x, y)] for y in range(y0, y1) for x in range(x0, x1)}
        ink, edge = max(used, key=lambda i: lum[i]), d[at(x0, y0 - 1)]
        for x in range(x0, x1):
            for y in range(y0 + 1, y1):
                d[at(x, y)] = d[at(x, y0)]
        t = text.fold(s)
        w = vwf.width(t) + len(t)
        assert w + 2 <= x1 - x0, s
        px, py, pts = x0 + (x1 - x0 - w) // 2, y0 + 5, []
        for ch in t:
            rows, adv = _G[ch]
            for y in range(len(rows)):
                for i in range(8):
                    if rows[y] & (0x80 >> i):
                        pts += [(px + i, py + y), (px + i + 1, py + y)]
            px += adv + 1
        for (a, b) in pts:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if y0 <= b + dy < y1:
                        d[at(a + dx, b + dy)] = edge
        for (a, b) in pts:
            d[at(a, b)] = ink
    return bytes(d)


# Mash contest of the debate: CG/RENDA.I2 = palette of 256 at 0, 8bpp 192 x 120 dōjō picture at 0x800
# (then two 4bpp sprite sheets). The scroll on the wall (連打命, read right to left) has its paper at
# x 64..127, y 20..38 (colours 245..255); the letters are painted over and MASH! is written twice as large.
RENDA_PIX, RENDA_W, SCROLL, SCROLL_TEXT = 0x800, 192, (64, 20, 128, 39), 'MASH!'
PAPER, SCROLL_INK = 245, 23


def renda(data):
    import random
    d, rnd = bytearray(data), random.Random(1)
    at = lambda x, y: RENDA_PIX + y * RENDA_W + x
    x0, y0, x1, y1 = SCROLL
    paper = [d[at(x, y)] for y in range(y0, y1) for x in range(x0, x1) if d[at(x, y)] >= PAPER]
    for y in range(y0, y1):
        for x in range(x0, x1):
            if d[at(x, y)] < PAPER:
                d[at(x, y)] = rnd.choice(paper)
    t = text.fold(SCROLL_TEXT)
    w = vwf.width(t) * 2
    assert w <= x1 - x0 - 4
    px, py = x0 + (x1 - x0 - w) // 2 + 1, y0 + (y1 - y0 - 18) // 2
    for ch in t:
        rows, adv = _G[ch]
        for y in range(9):
            for i in range(8):
                if rows[y] & (0x80 >> i):
                    for q in range(4):
                        d[at(px + i * 2 + (q & 1), py + y * 2 + (q >> 1))] = SCROLL_INK
        px += adv * 2
    return bytes(d)


# Dojo name boards: CG/MAPPOINT.I2 = 84 building pictures of 34 sectors (palette of 256 + 304 x 224 px 8bpp
# at +0x200; loader 0x8006b0b4, picture number = building record +0xe). Six of them are the same dojo gate
# with a hanging name board in brush kanji (board x 243..279, y 10..206, darker towards the bottom; each
# picture has its own palette). The ink is found against the board's brightness in the same row, painted
# over from the same column (the grain runs down the board), and the name is written down the board in
# pixfont twice as large (turned clockwise, as on a book spine).
MAPPOINT_SEC, MAPPOINT_W, MAPPOINT_H = 34, 304, 224
BOARD = (244, 14, 279, 204)                   # x0, y0, x1, y1: inside the board's edges
BOARDS = {36: 'Renpeikan', 37: 'Kōbusho', 39: 'Genbukan', 40: 'Chiba Dōjō', 41: 'Shigakukan', 42: 'Shieikan'}
BOARD_INK = 0.75                              # ink = darker than this share of the row's board brightness


def mappoint(data):
    import random
    d, rnd = bytearray(data), random.Random(2)
    x0, y0, x1, y1 = BOARD
    for n, name in BOARDS.items():
        o = n * MAPPOINT_SEC * 2048
        cols = struct.unpack_from('<256H', d, o)
        lum = [(c & 31) * 2 + (c >> 5 & 31) * 5 + (c >> 10 & 31) for c in cols]
        at = lambda x, y: o + 0x200 + y * MAPPOINT_W + x
        ink = set()
        for y in range(y0, y1):
            row = sorted(lum[d[at(x, y)]] for x in range(x0, x1))
            ref = row[len(row) * 4 // 5]
            ink.update((x, y) for x in range(x0, x1) if lum[d[at(x, y)]] < ref * BOARD_INK)
        dark = min(ink, key=lambda p: lum[d[at(*p)]])
        dark = d[at(*dark)]
        mask = {(x + i, y + j) for (x, y) in ink for i in (-1, 0, 1) for j in (-1, 0, 1)
                if x0 <= x + i < x1 and y0 <= y + j < y1}
        for (x, y) in sorted(mask):
            c = [v for v in (next(v for v in range(y - 1, -1, -1) if (x, v) not in mask),
                             next(v for v in range(y + 1, MAPPOINT_H) if (x, v) not in mask))
                 if y0 - 3 <= v < y1 + 3]
            d[at(x, y)] = d[at(x, rnd.choice(c))]
        big, w = big2x(name)
        hgt = 2 * w + 2
        assert hgt <= y1 - y0, name
        top, xc = y0 + (y1 - y0 - hgt) // 2, (x0 + x1) // 2 + 8
        for (tx, ty) in big:
            d[at(xc - ty, top + tx)] = dark
    return bytes(d)


# Fencing (SCOM overlay): CG/SCOMBAT.I2. Sector 113 = palette of 256 + the dojo picture 304 x 224 (8bpp,
# pixels at +0x800) with the score labels 一本 / 注意 beside the mark boxes (left x 8..22, right x 256..270;
# rows 192..197 and 206..213). Sector 183 = palette of 256 + the banner sheet 240 x 200 at +0x800 (VRAM
# 768,256; colour 0 = transparent, 1 = shadow, 15 = white; the 80 x 80 corner at x 160 holds the score
# marks). The banners are zoomed in to full size, centred on x 160 by their width; their rectangles are the
# table SCOM 0x8016a1b0 + 28 n: +0xc texture page, +0xe u, v, w, h (+8 frames, +0x18 sound). Ten records:
# 一本勝負 三本勝負 勝負あり はじめ 一本目 二本目 三本目 一本 注意 勝負 (the last three were parts of the others).
# All ten are drawn again (pixfont twice as large, smoothed) and packed into the sheet; the table follows.
SCOM_BG, SCOM_BG_W = 113, 304
SCOM_LABELS = (('PTS', 192), ('WARN', 208))           # text, top row
SCOM_LABEL_X, SCOM_LABEL_ROWS = (8, 256), ((190, 200), (205, 216))
SCOM_SHEET, SCOM_SHEET_W, SCOM_SHEET_H = 183, 240, 200
SCOM_TABLE, SCOM_OVL, SCOM_PAGE = 0x8016a1b0, 0x8015b858, 0x9c
SCOM_AREAS = ((0, 0, 160, 80), (0, 80, 240, 200))     # free parts of the sheet: x0, y0, x1, y1
BANNERS = ('One-Point Match', 'Three-Point Match', 'Match Over', 'Begin!', 'First Point', 'Second Point',
           'Third Point', 'Point!', 'Warning', 'Fight!')
BANNER_OLD = ((0, 0, 160, 40), (0, 40, 160, 40), (0, 80, 160, 40), (0, 120, 120, 40), (120, 120, 120, 40),
              (0, 160, 120, 40), (120, 160, 120, 40), (120, 120, 80, 40), (160, 80, 80, 40), (80, 0, 80, 40))


def big2x(s):
    """(set of points, width): s in pixfont twice as large (Scale2x); points start at (1, 1)."""
    t = text.fold(s)
    w, on = vwf.width(t), set()
    x = 0
    for ch in t:
        rows, adv = _G[ch]
        on.update((x + i, y) for y in range(len(rows)) for i in range(8) if rows[y] & (0x80 >> i))
        x += adv
    big = set()
    for y in range(-1, 13):
        for x in range(-1, w + 1):
            p = (x, y) in on
            a, b, c, e = (x, y - 1) in on, (x + 1, y) in on, (x - 1, y) in on, (x, y + 1) in on
            q = (a if c == a and c != e and a != b else p, b if a == b and a != c and b != e else p,
                 c if e == c and e != b and c != a else p, e if b == e and b != a and e != c else p)
            big.update((2 * x + (k & 1) + 1, 2 * y + (k >> 1) + 1) for k in range(4) if q[k])
    return big, w


def banner(s):
    """(rows of colour indices, width, height): s twice as large (Scale2x), white with a 1 px shadow edge."""
    big, w = big2x(s)
    W, H = (2 * w + 3) & ~1, 26
    px = [[0] * W for _ in range(H)]
    for (x, y) in big:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if 0 <= x + dx < W and 0 <= y + dy < H:
                    px[y + dy][x + dx] = 1
    for (x, y) in big:
        px[y][x] = 15 if y < 15 else 14 if y < 19 else 13
    return px, W, H


def scombat(data, scom):
    """CG/SCOMBAT.I2 with English banners and score labels; scom (bytearray of SCOM.BIN) gets the new
    banner rectangles."""
    import random
    d, rnd = bytearray(data), random.Random(2)
    o = SCOM_BG * 2048
    pal = struct.unpack_from('<256H', d, o)
    lum = [(c & 31) + (c >> 5 & 31) + (c >> 10 & 31) for c in pal]
    at = lambda x, y: o + 0x800 + y * SCOM_BG_W + x
    lit = max((d[at(x, y)] for x in range(8, 23) for y in range(190, 216)), key=lambda v: lum[v])
    dim = min((d[at(x, y)] for x in range(8, 23) for y in range(190, 216)), key=lambda v: lum[v])
    for x0 in SCOM_LABEL_X:
        for (ya, yb) in SCOM_LABEL_ROWS:
            for y in range(ya, yb):
                ref = [d[at(x, y)] for x in range(0, 7)]
                lo, hi = min(lum[v] for v in ref) - 2, max(lum[v] for v in ref) + 2
                for x in range(x0 - 1, x0 + 16):
                    if not lo <= lum[d[at(x, y)]] <= hi:
                        d[at(x, y)] = rnd.choice(ref)
        for s, y0 in SCOM_LABELS:
            assert tiny_width(s) <= 15, s
            pts = [(x0 + 4 * n + i, y0 + r) for n, ch in enumerate(s) for r, row in enumerate(TINY[ch])
                   for i in range(3) if row[i] == '#']
            for (x, y) in pts:
                d[at(x + 1, y + 1)] = dim
            for (x, y) in pts:
                d[at(x, y)] = lit
    o = SCOM_SHEET * 2048 + 0x800
    for (x, y, w, h) in BANNER_OLD:               # the table must be the one this layout was read from
        assert all(a < 160 or b >= 80 for a in (x, x + w - 1) for b in (y, y + h - 1))
    for n, r in enumerate(BANNER_OLD):
        assert struct.unpack_from('<4H', scom, SCOM_TABLE - SCOM_OVL + 28 * n + 0xe) == r or \
            (n == 8 and scom[SCOM_TABLE - SCOM_OVL + 28 * n + 0xc] == 0x9d), 'SCOM banner table'
    for (x0, y0, x1, y1) in SCOM_AREAS:
        for y in range(y0, y1):
            d[o + y * SCOM_SHEET_W + x0:o + y * SCOM_SHEET_W + x1] = bytes(x1 - x0)
    shelves = [[x0, y, x1] for (x0, y0, x1, y1) in reversed(SCOM_AREAS) for y in range(y0, y1 - 25, 26)]
    made = sorted(((banner(s), n) for n, s in enumerate(BANNERS)), key=lambda b: -b[0][1])
    for (px, w, h), n in made:
        shelf = next((f for f in shelves if f[0] + w <= f[2]), None)
        assert shelf, 'fencing banners do not fit the sheet'
        x, y = shelf[0], shelf[1]
        shelf[0] += w
        for r in range(h):
            d[o + (y + r) * SCOM_SHEET_W + x:o + (y + r) * SCOM_SHEET_W + x + w] = bytes(px[r])
        struct.pack_into('<5H', scom, SCOM_TABLE - SCOM_OVL + 28 * n + 0xc, SCOM_PAGE, x, y, w, h)
    return bytes(d)


# District shapes of the town map: CG/SELECTOR.I2 = 51 pieces of 4bpp pixels without palette, read by
# COM 0x80173e84 through the table {u16 sector, u16 count} at COM 0x8017654c and drawn at the rectangles
# {s16 x, y, w, h} from COM 0x80176618 (palettes COM 0x801767b0: normal / under the cursor). A piece is a
# rounded box (border colour 1, fill 15) with the district name in its top left corner (grey ramp 2..14).
# The kanji are painted over and the English name is written in the same place, in two lines where it
# is marked with '/'. SEL_BOX gives a district a new x / width when its name needs it (the room was
# measured against the neighbouring boxes; SEL_TAB: only the top rows); a piece that outgrows its sectors is appended to the file.
SEL_TABLE, SEL_RECT, SEL_N = 0x8017654c, 0x80176618, 51
SEL_INK, SEL_EDGE, SEL_FILL = 14, 2, 15
SEL_TEXT = (
    'Castle', 'Soto-/Sakurada', 'Banchō-Iida', 'Nihonbashi', 'Hatchō-/bori', 'Tsukiji', 'Akasaka',
    'Aoyama-/Meguro', 'Ushigome', 'Koishikawa', 'Asakusa', 'Honjo-/Fukagawa', 'Shiba-Mita',          # Edo
    'Palace', 'Kamigyō', 'Nakagyō', 'Shimogyō', 'Kawara-/machi', 'Nishijin', 'Nijō/Castle', 'Mibu',
    'Shimabara', 'Sakyō', 'Gion', 'Kiyomizu', 'Fushimi',                                             # Kyōto
    'Castle', 'Nakanoshima', 'Tosabori', 'Kitashinchi', 'Dōtonbori',                                 # Ōsaka
    'Castle', 'Kitamachi', 'Minamimachi', 'East Hagi',                                               # Hagi
    'Castle', 'Kamimachi', 'Shimomachi', 'Yamakita',                                                 # Kōchi
    'Dejima', 'Uchimachi', 'Sotomachi', 'Maruyama', 'Ōura', 'Kameyama',                              # Nagasaki
    'Shiroyama', 'Honmachi', 'Kajiya-chō',                                                           # Kagoshima
    'Old City', 'Customs House', 'The Bund')                                                         # Shanghai
SEL_BOX = {1: (140, 52), 3: (228, 60), 4: (198, 44), 6: (90, 48), 17: (194, 48), 42: (18, 60)}       # x, width
SEL_TAB = {17: 34}                        # only the top rows are widened (a neighbour lies beside the rest)
SEL_OVL = 0x8015b858                      # load address of COM.BIN


def selector(data, com):
    """New CG/SELECTOR.I2; the piece and rectangle tables in com (bytearray of COM.BIN) are updated."""
    d = bytearray(data)
    for i, name in enumerate(SEL_TEXT):
        to, ro = SEL_TABLE - SEL_OVL + 4 * i, SEL_RECT - SEL_OVL + 8 * i
        sec, cnt = struct.unpack_from('<HH', com, to)
        x, y, w, h = struct.unpack_from('<4h', com, ro)
        px = unpack4(d[sec * 2048:], w, h)
        for row in px[:15]:                       # the kanji: rows 2..13
            row[:] = [SEL_FILL if 1 < c < SEL_FILL else c for c in row]
        if i in SEL_BOX:
            x, nw = SEL_BOX[i]
            assert nw >= w and nw % 4 == 0
            wide = [row[:w // 2] + [row[w // 2]] * (nw - w) + row[w // 2:] for row in px]
            k = SEL_TAB.get(i, h)                 # rows of the wide part; below it the old width
            for r in range(k, h):
                wide[r] = px[r] + [0] * (nw - w)
            for r in range(k - 4, k if k < h else 0):         # bottom edge of the part that sticks out
                wide[r][w - 4:] = wide[h - k + r][w - 4:]
                wide[r][w - 4:w - 1] = [SEL_FILL] * 3
            if k < h:
                wide[k - 1][w - 1] = 1
            px, w = wide, nw
            struct.pack_into('<4h', com, ro, x, y, w, h)
        for n, line in enumerate(name.split('/')):
            y0 = 3 + 11 * n
            assert y0 + 12 <= h - 2, 'district %d: %r too tall' % (i, name)
            got = draw(px, w, h, 2, line, SEL_INK, SEL_EDGE, y0)
            assert 2 + got <= w - 2, 'district %d: %r is %d px in a box of %d' % (i, line, got, w)
        b = pack4(px)
        if len(b) > cnt * 2048:                   # no room in its sectors: a new piece at the end
            sec, cnt = len(d) // 2048, (len(b) + 2047) // 2048
            d += bytes(cnt * 2048)
            struct.pack_into('<HH', com, to, sec, cnt)
        d[sec * 2048:sec * 2048 + len(b)] = b
    return bytes(d)


def patch(exe, winframe_data):
    """Program (bytearray): the era and ideology tag icons take (u, width) from a table."""
    off = lambda va: va - 0x80010000 + 0x800
    assert vwf.CAVE + len(vwf.blob()[0]) <= AT, 'vwf code reaches the gfx cave'
    assert not any(exe[off(AT):off(END)]), 'gfx cave is not empty'
    tail = [
        'era:',                                   # as the common tail 0x800a3284, advance = sprite width
        ('jal', 0x800b7654),
        ('nop',),
        ('jal', 0x800b70bc),
        ('or', 'a0', 'zero', 'zero'),
        ('lhu', 'v0', asm.lo(PEN_X), 's3'),
        ('lhu', 'v1', 0x98, 'sp'),
        ('nop',),
        ('addu', 'v0', 'v0', 'v1'),
        ('j', 0x800a3944),
        ('sh', 'v0', asm.lo(PEN_X), 's3'),
    ]
    code = asm.assemble(AT, tail)
    tbl = AT + len(code)
    cells = eras()[1]
    blob = code + b''.join(bytes([u, w]) for u, w in cells)
    tagtbl = AT + len(blob)
    blob += b''.join(bytes([TAG_U + u, w]) for u, w in tags(winframe_data)[1])
    assert AT + len(blob) <= END
    exe[off(AT):off(AT) + len(blob)] = blob
    base = tbl - 2 * 0x19                         # s1 = icon number 0x19..0x1f
    assert asm.hi(base) == asm.hi(base + 2 * 0x1f + 1)
    site = [
        ('lui', 'v0', asm.hi(base)),
        ('addu', 'v0', 'v0', 's1'),
        ('addu', 'v0', 'v0', 's1'),
        ('lbu', 'v1', asm.lo(base), 'v0'),
        ('lbu', 'v0', asm.lo(base) + 1, 'v0'),
        ('sb', 'v1', 0x94, 'sp'),
        ('sh', 'v0', 0x98, 'sp'),
        ('addiu', 'v0', 'zero', 0xc),
        ('sh', 'v0', 0x9a, 'sp'),
        ('lui', 'v0', 0x8011),
        ('lhu', 'v1', -0x28e8, 'v0'),
        ('addiu', 'v0', 'zero', 0xe0),
        ('sb', 'v0', 0x95, 'sp'),
        ('j', AT),
        ('sh', 'v1', 0x96, 'sp'),
    ]
    o = off(ERA_AT)
    assert struct.unpack_from('<I', exe, o)[0] == 0x24020018 and struct.unpack_from('<I', exe, o + 52)[0] == 0x08028ca1
    exe[o:o + 60] = asm.assemble(ERA_AT, site)
    base = tagtbl - 2 * 6                         # s1 = icon number 6..0xb; a0 = s0 already, a1 = palette
    assert asm.hi(base) == asm.hi(base + 2 * 0xb + 1)
    site = [
        ('lui', 'v0', asm.hi(base)),
        ('addu', 'v0', 'v0', 's1'),
        ('addu', 'v0', 'v0', 's1'),
        ('lbu', 'v1', asm.lo(base), 'v0'),
        ('lbu', 'v0', asm.lo(base) + 1, 'v0'),
        ('sb', 'v1', 0x94, 'sp'),
        ('sh', 'v0', 0x98, 'sp'),
        ('addiu', 'v0', 'zero', 0xc),
        ('sh', 'v0', 0x9a, 'sp'),
        ('nop',),
    ]
    o = off(TAG_AT)
    assert struct.unpack_from('<I', exe, o)[0] == 0x24020018 and struct.unpack_from('<I', exe, o + 48)[0] == 0x08028ca1
    exe[o:o + 40] = asm.assemble(TAG_AT, site)
    exe[o + 48:o + 52] = asm.assemble(TAG_AT + 48, [('j', AT)])       # tail: advance = sprite width
    o = off(ERA_Y)                                # the icons are drawn 2 px above the pen: not our letters
    assert struct.unpack_from('<I', exe, o)[0] == 0x2442fffe
    struct.pack_into('<I', exe, o, 0x24420000)


if __name__ == '__main__':
    px, cells = eras()
    for e, (u, w) in zip(ERAS, cells):
        print('%-8s u %3d  width %2d' % (e, u, w))
    if len(sys.argv) > 1:
        from PIL import Image
        im = Image.new('L', (STRIP[1], STRIP[2]))
        for y, row in enumerate(px):
            for x, v in enumerate(row):
                im.putpixel((x, y), 90 if v == 0 else v * 17)
        im.resize((STRIP[1] * 3, STRIP[2] * 3), Image.NEAREST).save(sys.argv[1])
