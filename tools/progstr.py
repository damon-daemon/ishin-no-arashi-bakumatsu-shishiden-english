"""Strings of the program and the overlays (menu labels, help lines, system messages ...).
Ported from the Genghis Khan IV project; differences are marked "Ishin".

tl/progstr/*.txt: "key<TAB>English" lines, key = <IMAGE>:<vaddr hex> with IMAGE = PROG
(SLPM_861.44) or an overlay name (COM, PERS, ... = CODE/COM.BIN ...); \\n = newline; English "-" =
keep the Japanese (a literal minus sign alone: "\\-"); '#' starts a comment line. Macron letters
are written as they are (text.fold). {C7} {M0} {N1} {B} = the printer's escapes ESC C n colour / ESC M n icon / ESC N n small digit / ESC letter (see escs, vis); they must match the Japanese. {T104} = our own escape ESC T c (vwf.py): pen x = 104 px inside the text rectangle, for list columns (a format string without Japanese, e.g. COM:8015b860, can be given English by its key). A string without English takes
the English of another string with the same Japanese (translation memory).

English that fits the string's slot (its bytes plus the compiler's zero padding to the next 4-byte
boundary) is written in place. Longer English is moved and every reference is repointed:
  - 32-bit data words equal to the address (pointer tables) in the same image (and, for a program
    string, in the overlays),
  - lui/addiu (or load/store) pairs in the code that build the address, when that lui has no other
    user (else the pair cannot be changed alone: shorten the English).
Where moved strings go (Pool): the slack of the slots (bytes after the English's NUL of strings
written in place, whole slots of moved strings; referenced strings only, never array elements),
then, for every image, the program's spare block RESIDENT (always loaded).
Ishin: the overlays have no header (read-only data, code, data; all load at OVL_BASE except PERS2)
and do NOT grow: whether the RAM behind an overlay file is its bss is unknown, and script buffer A
now starts right after the largest overlay (vwf.patch).
Blockers (the English must fit the slot): an overlay address referenced from the program (the
overlays share one load address: ambiguous), a lui with other users; gp-relative references only
reach gp +- 32 KB. A string with no reference found must fit its slot. printf conversions must match.

  progstr.py export            -> script/progstr.json (every candidate, with flags)
  progstr.py show [KEY KEY] [--todo]   strings to translate between two keys
  progstr.py review FILE...    the strings of tl files with Japanese and English (review pass)
  progstr.py apply FILE BATCH  put changed key<TAB>English lines into a tl file (checked)
  progstr.py stats | check
"""
import collections, json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import fmtlimit, iso, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'progstr')
SCRIPT = os.path.join(ROOT, 'script', 'progstr.json')
FMT = re.compile(rb'%[-+ #0]*\d*(?:\.\d+)?[hl]?[diouxXcsfeEgGp%]')


def convs(b):
    """printf conversions; a %s, %d or %u may change its pad width (column layout: fmtlimit measures it)"""
    return [re.sub(rb'-?\d+([sdu])$', rb'\1', c) for c in FMT.findall(b)]
PROG_BASE, PROG_FOFF = 0x80010000, 0x800
OVL_BASE = 0x8015b858                  # every overlay loads here (table 0x8003da58), no header ...
OVL_BASES = {'PERS2': 0x801e0000}      # ... except PERS2
OVERLAYS = ('COM', 'GATE', 'HANA', 'INIT', 'KAIWA', 'MARCH', 'MOVIE', 'MP', 'MP2', 'PERS', 'PERS2', 'SCOM',
            'STAFF', 'WAR')
GP = 0x801169e0                        # set at 0x800af298
RAM_LO, RAM_HI = 0x80010000, 0x80200000
# program areas that are not strings: the person table's string pool is names.py's business
# (pointers 0x800ee09c + 0xc0 * id; pool ~0x80036000-0x8003c000: found by reference below)
PROG_SKIP = []
RECORDS = []
NAME_TABLE = (0x800ee09c, 0x800ee09c + 599 * 0xc0)      # person records (names.py): strings used only there are not ours
SDATA = (GP - 0x8000, GP + 0x8000)     # small strings near gp: lone characters there are labels
KEY = re.compile(r'(PROG|%s):([0-9a-f]{8})' % '|'.join(OVERLAYS))
JR_RA = 0x03e00008
NO_STRINGS = ()
OVL_TABLES = {}
# spare zero block of the program data (17 KB, the twin of vwf.CAVE; no reference found by scan)
RESIDENT = [(0x8010ee90, 0x4458)]
def resident(clean_prog):
    """Free program RAM for moved strings: RESIDENT + what names.py leaves over (the rest of its
    pool in the VWF cave and the Japanese name strings no person record points at any more)."""
    import bisect, names, vwf
    d = names.patch(vwf.patch(bytes(clean_prog)))
    used = getattr(names.patch, 'used', None)
    out = list(RESIDENT)
    if used is None:
        return out
    at = (names.POOL[0] + used + 3) & ~3
    out.append((at, names.POOL[1] - at))
    ptrs = sorted(set(struct.unpack_from('<%dI' % names.FIELDS, d, names.off(names.NAMES + names.STRIDE * i))[k]
                      for i in range(names.COUNT) for k in range(names.FIELDS)))
    for r in rows():
        if r['kind'] == 'name' and r['key'].startswith('PROG:'):
            va = parse_key(r['key'])[1]
            i = bisect.bisect_left(ptrs, va)
            if i == len(ptrs) or ptrs[i] > va + r['room']:
                out.append((va, r['room'] + 1))
    return out


# Texts drawn one row per line of the string (the row's y comes from the line number, so the VWF's own
# wrap would overprint the next row): wrapped at build time to this pixel width. INIT scenario
# descriptions: box of 10 full-width characters.
# Code words changed for English layout: (tag, vaddr, clean word, new word)
LAYOUT = [
    # SCOM fencing name plates (0x80160270: window 92 px, left at x 21, right at x 216): 120 px, the right
    # one at x 188, for English full names (128 of 599 are wider than 84 px). Centring: vwf.plates.
    ('SCOM', 0x80160278, 0x2405005c, 0x24050078),
    ('SCOM', 0x801602d4, 0x240500d8, 0x240500bc),
    # WAR duel result list (0x8015fbb8: window 164 px at x 78, name at 0, status at 84, exp after it):
    # window 224 px at x 48, status at 128; the row / header strings put the exp column at {T176}.
    ('WAR', 0x8015fbbc, 0x240500a4, 0x240500e0),
    ('WAR', 0x8015fbd8, 0x2405004e, 0x24050030),
    ('WAR', 0x8015fc60, 0x24040054, 0x24040080),
    # Card / topic description boxes (text of 0x8009f6f0(card); Japanese 12 characters x 5 lines): one more
    # line for English. PERS card chooser: rectangle y 8 -> 2, h 80 -> 98 (the header row is at y 100);
    # PROG card popups 0x800a0a40 / 0x800a0c58 (window 302 x 120, pen y 4): y 16 -> 2, h 80 -> 100. The COM popup 0x8016a1d8
    # (140 x 94) already holds 6 lines. DESC_PX / DESC_LINES = the common limit, checked below.
    ('PERS', 0x80173430, 0x24050008, 0x24050002),
    ('PERS', 0x8017343c, 0x24070050, 0x24070062),
    ('PROG', 0x800a0a38, 0x24050010, 0x24050002),      # y 16 -> 2: the button legend row is at y 100
    ('PROG', 0x800a0a44, 0x24070050, 0x24070064),
    ('PROG', 0x800a0c50, 0x24050010, 0x24050002),
    ('PROG', 0x800a0c5c, 0x24070050, 0x24070064),
    # PERS debate card chooser (header 0x801734e8..): the numbers are "%3g" at 200 / 228 / 256 (24 px each);
    # labels Eff / Fresh / P: 0xd4 -> 0xcc, 0xf0 -> 0xe2 (P stays at 0x110). The ideology tags are drawn
    # right after the name (as in the Japanese): a name over ~130 px with three tags reaches the numbers.
    ('PERS', 0x801735cc, 0x240400d4, 0x240400cc),
    ('PERS', 0x801735e4, 0x240400f0, 0x240400e2),
    # PROG item list (shops, belongings to sell / give; rows 0x80058be4, 240 px wide): name 0 / type 0x68 /
    # state 0xa0 / price 0xc0 -> 0 / 0x74 / 0xa4 / 0xc8 (name 116 px, type 48; the price is "%5g" at
    # 8 px a character = 40 px and a glyph past x 240 is dropped, so 0xc8 is its limit);
    # the two headers are the row + 10
    ('PROG', 0x80058c7c, 0x24040068, 0x24040074),
    ('PROG', 0x80058ce4, 0x240400a0, 0x240400a4),
    ('PROG', 0x80058d1c, 0x240400c0, 0x240400c8),
    ('PROG', 0x80058de4, 0x24040068, 0x24040074),
    ('PROG', 0x80058e4c, 0x240400c0, 0x240400c8),
    ('PROG', 0x80059150, 0x24040072, 0x2404007e),
    ('PROG', 0x8005916c, 0x240400aa, 0x240400ae),
    ('PROG', 0x800591bc, 0x24040072, 0x2404007e),
    ('PROG', 0x800591dc, 0x240400ca, 0x240400d2),
    # PROG travel-map name box (0x800650b0: window 68 x 24 at screen 8,16, VRAM 0x200,0x40): w -> 120
    # (place names up to 106 px: Great Buddha of Nara; "Yamato-Gojō" was clipped)
    ('PROG', 0x800650b0, 0x24050044, 0x24050078),
    # PROG location bar (HUD object 0x80154088, window +0x14, set up at 0x800a8d50): w 192 -> 256,
    # x 112 -> 48 (text texture at VRAM 0x200,0x80: the menu bars start at x 0x244 = 272 px, so 256 is
    # the safe limit); the longest "town: district: building" is 247 px of 248
    ('PROG', 0x800a8d50, 0x240500c0, 0x24050100),
    ('PROG', 0x800a8d8c, 0x24050070, 0x24050030),
    # PROG facility list (0x8006ba80; rows 0x8006b9..: name, type, status): window w 252 -> 280, x 38 -> 20;
    # row width 228 -> 256, row x 46 -> 28, scroll bar x 274 -> 284 (format PROG:800228cc has column escapes)
    ('PROG', 0x8006ba98, 0x240500fc, 0x24050118),
    ('PROG', 0x8006bab8, 0x24050026, 0x24050014),
    ('PROG', 0x8006baec, 0x240200e4, 0x24020100),
    ('PROG', 0x8006bafc, 0x2402002e, 0x2402001c),
    ('PROG', 0x8006bb0c, 0x24020112, 0x2402011c),
    ('PROG', 0x8006bac8, 0x2404000a, 0x24040004),   # header pen x 10 -> 4 (the rows' x)
    # PROG district picker (Move > Go to Another District, 0x80040950): window w 72 -> 112, x 128 -> 104;
    # row width 48 -> 88 (widest name 81 px), row x 136 -> 112, scroll bar x 184 -> 200
    ('PROG', 0x80040968, 0x24050048, 0x24050070),
    ('PROG', 0x80040988, 0x24050080, 0x24050068),
    ('PROG', 0x800409bc, 0x24020030, 0x24020058),
    ('PROG', 0x800409cc, 0x24020088, 0x24020070),
    ('PROG', 0x800409dc, 0x240200b8, 0x240200c8),
    # COM town list (Area Info > Other Towns): row name 2 / region 0x3a / ruler 0x82 / status 0xb2 ->
    # 2 / 0x58 / 0x94 / 0xd4; header region 0x4c / ruler 0x84 / status 0xd8 -> 0x60 / 0x9c / 0xdc
    ('COM', 0x80171ca0, 0x2404003a, 0x24040058),
    ('COM', 0x80171e20, 0x24040082, 0x24040094),
    ('COM', 0x80171ecc, 0x240400b2, 0x240400d4),
    ('COM', 0x80172074, 0x2404004c, 0x24040060),
    ('COM', 0x80172090, 0x24040084, 0x2404009c),
    ('COM', 0x801720ac, 0x240400d8, 0x240400dc),
    # PROG second person list row (0x80061c1x, the Trusts tab): same columns as 0x800619e8
    ('PROG', 0x80061ca4, 0x240400b8, 0x240400b0),
    ('PROG', 0x80061cfc, 0x240400d0, 0x240400d8),
    ('PROG', 0x80061d50, 0x240400f0, 0x240400f6),
    # PROG status screen, Views tab: Domestic / Foreign Insight values x 0x42 -> 0x58 (the label is 82 px)
    ('PROG', 0x8005f724, 0x24040042, 0x24040058),
    ('PROG', 0x8005f75c, 0x24040042, 0x24040058),
    # COM card list (Belongings > Cards): ideology tags x 0x88 -> 0xa4 (card names get 164 px), header 0xa0 -> 0xa8
    ('COM', 0x8016fa08, 0x24040088, 0x240400a4),
    ('COM', 0x8016fc00, 0x240400a0, 0x240400a8),
    ('COM', 0x8016fe50, 0x240400a0, 0x240400a8),
    # COM Action Guide: values of Domestic Insight / Foreign Insight / Renown x 0x3a -> 0x5c
    ('COM', 0x8016c12c, 0x2404003a, 0x2404005c),
    ('COM', 0x8016c1a0, 0x2404003a, 0x2404005c),
    ('COM', 0x8016c244, 0x2404003a, 0x2404005c),
    # PROG person list row 0x800619e8 (COM Relations lists): name 2 / status 0x68 / views 0xb8 + 0xd0 (two words,
    # 24 px apart) / trust 0xf0 -> views 0xb0 + 0xd8, trust 0xf6
    ('PROG', 0x80061acc, 0x240400b8, 0x240400b0),
    ('PROG', 0x80061b28, 0x240400d0, 0x240400d8),
    ('PROG', 0x80061b7c, 0x240400f0, 0x240400f6),
    # PROG status screen. Views tab: values of Polity / Foreign Policy / Solution x 0x42 -> 0x4c;
    # Fencing tab: combat experience value 0xd6 -> 0xe2, blade and armour names 0x2a -> 0x30
    ('PROG', 0x8005f53c, 0x24040042, 0x2404004c),
    ('PROG', 0x8005f588, 0x24040042, 0x2404004c),
    ('PROG', 0x8005f5dc, 0x24040042, 0x2404004c),
    ('PROG', 0x8005ffb4, 0x240400d6, 0x240400e2),
    ('PROG', 0x80060010, 0x2404002a, 0x24040030),
    ('PROG', 0x80060180, 0x2404002a, 0x24040030),
    # COM group Military tab: 軍 事 力 at x 6 / 0x18 / 0x2a and 海 軍 力 at 0x9a / 0xac / 0xbe share the 軍 and 力
    # pieces: 軍 and 力 are blanks, 事 = "Military" drawn at x 6, 海 = "Navy"
    ('COM', 0x80166a5c, 0x24040018, 0x24040006),
    # COM Final Goal tab, trend line "%s%3g" x3: pen x 0x5e / 0x96 / 0xce (56 px pitch) -> 0x5e / 0x9e / 0xda
    ('COM', 0x8016944c, 0x24040096, 0x2404009e),
    ('COM', 0x801694b8, 0x240400ce, 0x240400da),
    # COM Group Details list: row x name 6 / type 0x5e / views 0x9e / power 0xde -> 6 / 0x56 / 0x9c / 0xe4;
    # header (drawn at two sites) type 0x6e / views 0xae / power 0xea -> 0x66 / 0xac / 0xf0
    ('COM', 0x80167a28, 0x2404005e, 0x24040056),
    ('COM', 0x80167a48, 0x2404009e, 0x2404009c),
    ('COM', 0x80167ad4, 0x240400de, 0x240400e4),
    ('COM', 0x80167bf0, 0x2404006e, 0x24040066), ('COM', 0x80167e24, 0x2404006e, 0x24040066),
    ('COM', 0x80167c0c, 0x240400ae, 0x240400ac), ('COM', 0x80167e40, 0x240400ae, 0x240400ac),
    ('COM', 0x80167c28, 0x240400ea, 0x240400f0), ('COM', 0x80167e5c, 0x240400ea, 0x240400f0),
    # COM group Basic Info page: labels at x 6, values at 0x42 -> 0x4c ("Foreign Policy" is 70 px)
    # (the group page's post headings and name columns are set by joins.py)
    ('COM', 0x80164570, 0x24040042, 0x2404004c),
    ('COM', 0x801645c0, 0x24040042, 0x2404004c),
    ('COM', 0x80164600, 0x24040042, 0x2404004c),
    ('COM', 0x80164688, 0x24040042, 0x2404004c),
    ('COM', 0x80164734, 0x24040042, 0x2404004c),
    ('COM', 0x801647d8, 0x24040042, 0x2404004c),
    # INIT character creation: the choice lists (generic list 0x800a0f80, row width at sp+0x20, list x at
    # sp+0x28; all centred on x 160) were 24 px rows (two kanji; type 48): gender 40 px, origin 64,
    # the three view pairs 52. Type: one `li 0x30` served width and height; the y value 0x4a (74) now
    # also serves as the width (li / sh order changed), x 136 -> 124.
    ('INIT', 0x8015f480, 0x24020018, 0x24020028), ('INIT', 0x8015f490, 0x24020094, 0x2402008c),
    ('INIT', 0x8015f60c, 0x24020018, 0x24020040), ('INIT', 0x8015f61c, 0x24020094, 0x24020080),
    ('INIT', 0x8015f7fc, 0xa7a20020, 0xa7a20022), ('INIT', 0x8015f800, 0xa7a20022, 0x2402007c),
    ('INIT', 0x8015f804, 0x24020088, 0xa7a20028), ('INIT', 0x8015f808, 0xa7a20028, 0x2402004a),
    ('INIT', 0x8015f80c, 0x2402004a, 0xa7a20020),
    ('INIT', 0x8015faf0, 0x24020018, 0x24020034), ('INIT', 0x8015fb00, 0x24020094, 0x24020086),
    ('INIT', 0x8015fcb4, 0x24020018, 0x24020034), ('INIT', 0x8015fcc4, 0x24020094, 0x24020086),
    ('INIT', 0x8015fe78, 0x24020018, 0x24020034), ('INIT', 0x8015fe88, 0x24020094, 0x24020086),
    # summary rows (windows 128 px at x 164): 152 px for "Views: Sabaku Open Moderate"
    ('INIT', 0x801604a0, 0x24050080, 0x24050098),
]
def layout(files):
    """Apply LAYOUT to {tag: bytearray}; fails when a clean word is not the expected one."""
    import struct
    for tag, va, old, new in LAYOUT:
        o = va - (0x80010000 - 0x800 if tag == 'PROG' else OVL_BASES.get(tag, OVL_BASE))
        if struct.unpack_from('<I', files[tag], o)[0] != old:
            raise ValueError('layout %s:%08x: unexpected word' % (tag, va))
        struct.pack_into('<I', files[tag], o, new)


DESC = (0x80010c20, 0x8001c800)        # topic / card titles + descriptions (strings over 13 characters = descriptions)
DESC_PX, DESC_LINES = 140, 6           # narrowest description box (COM), lines after the LAYOUT patches
PREWRAP = {'INIT:8015b858': 120, 'INIT:8015b968': 120, 'INIT:8015baa0': 120}
# formats whose arguments are no longer printed (sprintf ignores extra arguments)
DROP_ARGS = set()
# formats whose icon escapes (ESC m x: kanji drawn as icons, e.g. 月 日 回戦) are replaced by text
FREE_ESC = {'PERS2:801e006c', 'PERS2:801e007c', 'PROG:8003cb2c'}


def ovl_name(tag):
    return 'CODE/%s.BIN' % tag


class Image:
    """One loaded file: data[foff + (va - base)] for va in [base, end)."""

    def __init__(self, tag, data, base, foff):
        self.tag, self.data, self.base, self.foff = tag, data, base, foff
        self.end = base + len(data) - foff
        n = (self.end - base) // 4
        ws = struct.unpack_from('<%dI' % n, data, foff)
        jr = [i for i, w in enumerate(ws) if w == JR_RA]
        self.code_end = base + 4 * jr[-1] + 8          # code: [code_start, code_end); data around it
        # code start: the lowest of the first return, the stack prologue before it and the jal targets
        starts = [base + 4 * jr[0]] + [t for t in (0x80000000 | (w & 0x3ffffff) << 2 for w in ws[jr[0]:jr[-1] + 2]
                                                    if w >> 26 == 3) if base <= t < self.end]
        i = jr[0]
        while i > 0 and not (ws[i] >> 16 == 0x27bd and ws[i] & 0x8000):
            i -= 1
        if i:
            starts.append(base + 4 * i)
        self.code_start = min(starts)
        self.data_ranges = [(base, self.code_start), (self.code_end, self.end)]
        self.skip = sorted(PROG_SKIP + RECORDS) if tag == 'PROG' else []

    def f(self, va):
        assert self.base <= va < self.end, '%s %x' % (self.tag, va)
        return va - self.base + self.foff

    def w(self, va):
        return struct.unpack_from('<I', self.data, self.f(va))[0]

    def put(self, va, b):
        o = self.f(va)
        self.data[o:o + len(b)] = b


def images(files):
    """[Image] over {tag: bytearray} (PROG and the overlays)."""
    out = []
    for tag, b in files.items():
        out.append(Image(tag, b, PROG_BASE, PROG_FOFF) if tag == 'PROG' else Image(tag, b, OVL_BASES.get(tag, OVL_BASE), 0))
    return out


def _s16(x):
    return x - 0x10000 if x & 0x8000 else x


def _writes(w):
    """Register written by instruction w (None if none / unknown)."""
    op = w >> 26
    if op in (0, 0x10, 0x12):
        return (w >> 11) & 31 if op == 0 else None
    if op in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F) or 0x20 <= op <= 0x26:
        return (w >> 16) & 31
    if op == 0x03:
        return 31
    return None


def _is_jump(w):
    op = w >> 26
    return op in (2, 3) or (op == 0 and (w & 0x3F) in (8, 9))


def code_pairs(img):
    """({target: [(lui va, user va)]}, {lui va: number of users}, {target: [gp user va]})
    for the image's code. A lui register is followed until it is overwritten or a jump's
    delay slot ends; any other read of it counts as a user too (so such a lui is never
    changed)."""
    pairs, users, gps = collections.defaultdict(list), collections.Counter(), collections.defaultdict(list)
    lui, end_after = {}, None
    for va in range(img.code_start, img.code_end, 4):
        w = img.w(va)
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if rs == 28 and (op == 0x09 or 0x20 <= op <= 0x3F):
            gps[(GP + _s16(imm)) & 0xFFFFFFFF].append(va)
        if op == 0x0F:
            lui[rt] = (imm << 16, va)
        else:
            if rs in lui and (op in (0x09, 0x0D) or 0x20 <= op <= 0x3F):
                t = (lui[rs][0] + (imm if op == 0x0D else _s16(imm))) & 0xFFFFFFFF
                pairs[t].append((lui[rs][1], va))
                users[lui[rs][1]] += 1
                if 0x28 <= op <= 0x3F and rt in lui and rt != rs:     # stores the lui value
                    users[lui[rt][1]] += 2
            else:
                for r in {rs, rt}:
                    if r in lui:
                        users[lui[r][1]] += 2
            wr = _writes(w)
            if wr in lui:
                del lui[wr]
        if end_after is not None and va >= end_after:
            lui.clear()
            end_after = None
        if _is_jump(w):
            end_after = va + 4
    return pairs, users, gps


def data_words(img):
    """{value: [vaddr]} of the aligned words of the image's data pointing into RAM."""
    out = collections.defaultdict(list)
    for lo, hi in img.data_ranges:
        for va in range(lo, hi - 3, 4):
            v = img.w(va)
            if RAM_LO <= v < RAM_HI:
                out[v].append(va)
    return out


class Refs:
    """Every reference to a string of each image, by image tag."""

    def __init__(self, imgs):
        self.imgs = {i.tag: i for i in imgs}
        self.code = {i.tag: code_pairs(i) for i in imgs}
        self.words = {i.tag: data_words(i) for i in imgs}

    def of(self, tag, va):
        """(code pairs [(img tag, lui, user)], data words [(img tag, at)], blockers [text])."""
        code, data, block = [], [], []
        if tag == 'PROG':
            srcs = list(self.imgs)
        else:
            srcs = [tag]
            own = [at for at in self.words['PROG'].get(va, [])
                   if any(lo <= at < hi for lo, hi in OVL_TABLES.get(tag, []))]
            data += [('PROG', at) for at in own]
            if self.code['PROG'][0].get(va) or len(self.words['PROG'].get(va, [])) > len(own):
                block.append('referenced from the program (ambiguous overlay address)')
        for s in srcs:
            for l, u in self.code[s][0].get(va, []):
                code.append((s, l, u))
                if self.code[s][1][l] != 1:
                    block.append('lui %s:%x has other users' % (s, l))
            for at in self.words[s].get(va, []):
                data.append((s, at))
            if self.code[s][2].get(va):
                block.append('gp-relative reference %s:%x' % (s, self.code[s][2][va][0]))
        return code, data, block

    def gp_users(self, tag, va):
        """[(img tag, instruction va)] of the gp-relative references to va."""
        srcs = list(self.imgs) if tag == 'PROG' else [tag]
        return [(s, u) for s in srcs for u in self.code[s][2].get(va, [])]


def slot(img, va):
    """(Japanese bytes, room) of the string at va: room = bytes up to the next 4-byte
    boundary after its NUL (the compiler's padding), never past the next non-zero byte,
    minus one for the NUL."""
    b = img.data
    o = img.f(va)
    assert b[o - 1] == 0 or va % 4 == 0, '%s:%x is not the start of a string' % (img.tag, va)
    e = b.index(b'\0', o)
    k = e
    while k < len(b) and b[k] == 0:
        k += 1
    end = min(k, (va + (e - o) + 1 + 3) // 4 * 4 - va + o)
    return bytes(b[o:e]), end - o - 1


def parse_key(k):
    m = KEY.fullmatch(k)
    return m.group(1), int(m.group(2), 16)


def load_tl(d=TL):
    """{key: English} of every tl/progstr file ('-' entries included)."""
    out = {}
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith('.txt'):
            continue
        path = os.path.join(d, fn)
        for n, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
            if line.strip() and not line.startswith('#'):
                k, tab, v = line.partition('\t')
                if not (tab and KEY.fullmatch(k)):
                    raise ValueError('%s line %d: expected key<TAB>English: %r' % (fn, n, line))
                if k in out:
                    raise ValueError('%s line %d: %s given twice' % (fn, n, k))
                out[k] = v.replace('\\n', '\n').replace('\\t', '\t')
    return out


def load_tl_file(path):
    """Keys of one tl file."""
    return [l.partition('\t')[0] for l in open(path, encoding='utf-8').read().splitlines()
            if l.strip() and not l.startswith('#')]


def resolved(tl, rows):
    """{key: English} to write: explicit English, else translation memory by Japanese;
    '-' entries dropped. rows = export rows (key, jp, ui)."""
    jp = {r['key']: r['jp'] for r in rows}
    mem = {}
    for k, v in tl.items():
        if v != '-' and k in jp:
            mem.setdefault(jp[k], v)
    out = {k: v for k, v in tl.items() if v != '-'}
    for r in rows:
        if r['ui'] and r['key'] not in tl and r['jp'] in mem:
            out[r['key']] = mem[r['jp']]
    return out


def fmt_error(key, en, jp, sites):
    """Error text if the English format can overflow a sprintf target of known size
    (fmtlimit.py): its longest output must fit, or at least not exceed the Japanese's."""
    name = fmtlimit.SHORT_S.get(key, fmtlimit.NAME)
    n, j = fmtlimit.expand(en, name), fmtlimit.expand(jp, name)
    for site, size in sites:
        if size is not None and n > max(size - 1, j):
            return 'progstr %s: sprintf at %s writes up to %d bytes into a %d-byte buffer (Japanese %d)' % (key, site, n, size, j)
    return None


def fmt_unknown(tl):
    """[(key, en bytes, jp bytes, sites)] of formats longer than the Japanese whose target
    size is unknown (check in the emulator, or trace the buffer)."""
    rs = {r['key']: r for r in rows()}
    imgs = images({t: bytearray(b) for t, b in clean_files().items() if t not in NO_STRINGS})
    out = []
    for key, sites in sorted(fmtlimit.limits(imgs).items()):
        en = tl.get(key)
        if en and en != '-' and key in rs and any(s is None for _, s in sites):
            n, j = fmtlimit.expand(encode(en)), fmtlimit.expand(rs[key]['jp'].encode('cp932'))
            if n > j:
                out.append((key, n, j, [x for x, s in sites if s is None]))
    return out


FW = '{fw}'    # English prefix: write the text as full-width Shift-JIS (memory card titles: the BIOS shows no ASCII)
SJ = '{sj}'    # prefix: the rest as Shift-JIS symbols (in-game font: full-width letters draw as blank boxes)


ESC = re.compile(rb'\x1b(?:[CMNcmn]\d|T.|[A-Za-z])')


def escs(b):
    """The printer's escape codes of a string, in order (ESC C/M/N + digit: colour / icon / small digit;
    ESC + another letter, e.g. B: skipped by the string printer)."""
    return [e for e in ESC.findall(b) if e[1:2] != b'T']      # {T..} is ours (column position): free


def vis(t):
    t = re.sub('\x1bT(.)', lambda m: '{T%d}' % ((ord(m.group(1)) - 0x20) * 4), t)
    """Text with the escape codes written as {C7} {B} {M0} (what encode() takes)."""
    return re.sub('\x1b(?:([CMNcmn])(\\d)|([A-Za-z]))', lambda m: '{%s}' % (m.group(1) + m.group(2) if m.group(1) else m.group(3)), t)


def prewrap(en, width):
    """English with '\n' put where a line would pass width pixels (macrons kept: folded only to measure)."""
    out = []
    for para in en.split('\n'):
        line = ''
        for w in para.split():
            if line and text.px(text.fold(line + ' ' + w)) > width:
                out.append(line)
                line = w
            else:
                line = line + ' ' + w if line else w
        out.append(line)
    return '\n'.join(out)


def encode(en):
    errs = text.check(en.replace('\\-', '-').replace('\n', ' '))
    if errs:
        raise UnicodeEncodeError('ascii', en, 0, 1, '; '.join(errs))
    def tab(m):
        px = int(m.group(1))
        if px % 4 or not 0 <= px <= 376 or px == 20:      # 20 would be the byte '%'
            raise UnicodeEncodeError('ascii', en, 0, 1, '{T%d}: pen x must be a multiple of 4, 0..376, not 20' % px)
        return b'\x1bT' + bytes([0x20 + px // 4])
    b = re.sub(rb'\{T(\d+)\}', tab, text.fold(en.replace('\\-', '-')).encode('ascii'))
    return re.sub(rb'\{([A-Za-z])(\d?)\}', lambda m: b'\x1b' + m.group(1) + m.group(2), b)


class Pool:
    """Free space for moved strings: [va, n] ranges per image (slot slack, freed slots,
    RESIDENT for the program) and the growable tail of each overlay."""

    def __init__(self, imgs, refs, resident=()):
        self.free = collections.defaultdict(list)
        self.free['PROG'] += [[va, n] for va, n in resident]
        self.tail = {i.tag: (i.end + 3) & ~3 for i in imgs if i.tag != 'PROG'}
        self.limit = {t: tail_limit(refs, e) for t, e in self.tail.items()}
        self.grown = {}

    def add(self, tag, va, n):
        if n > 0:
            self.free[tag].append([va, n])

    def merge(self):
        for tag, fr in self.free.items():
            out = []
            for va, n in sorted(fr):
                if out and out[-1][0] + out[-1][1] == va:
                    out[-1][1] += n
                else:
                    out.append([va, n])
            self.free[tag] = out

    def take(self, tag, n, near_gp=False):
        """(space tag, va) of n free bytes for a string of image tag, or None."""
        ok = (lambda va: GP - 0x8000 <= va and va + n <= GP + 0x8000) if near_gp else (lambda va: True)
        for space in [tag, 'PROG'] if tag != 'PROG' else ['PROG']:
            for f in self.free[space]:
                if f[1] >= n and ok(f[0]):
                    va = f[0]
                    f[0] += n; f[1] -= n
                    return space, va
            if space != 'PROG' and not near_gp and self.tail[space] + n <= self.limit[space]:
                va = self.tail[space]
                self.tail[space] += n
                self.grown[space] = self.tail[space]
                return space, va
        return None

    def room(self):
        return {t: sum(n for _, n in fr) for t, fr in self.free.items()}


def tail_limit(refs, end):
    """Ishin: overlays do not grow (see the module docstring)."""
    return end


ADDR = {}      # key -> address of its English after apply() (facetitle.py)


def apply(files, clean, resident=(), tl=None):
    """Write tl/progstr into files ({tag: bytearray}; overlays may grow); clean = {tag: bytes};
    resident = [(va, bytes)] of free program RAM. Returns (strings, moved, pool)."""
    cimgs = images({t: bytearray(b) for t, b in clean.items()})
    rs = {r['key']: r for r in survey(cimgs)}
    tl = resolved(load_tl() if tl is None else tl, list(rs.values()))
    refs = Refs(cimgs)
    pool = Pool(cimgs, refs, resident)
    if not tl:
        return 0, 0, pool
    imgs = {i.tag: i for i in images(files)}
    lims = fmtlimit.limits([i for i in cimgs if i.tag not in NO_STRINGS]) if fmtlimit.SPRINTF else {}
    ctag = {i.tag: i for i in cimgs}
    errors, moving = [], []
    for key, en in sorted(tl.items()):
        tag, va = parse_key(key)
        jp, room = slot(ctag[tag], va)
        own = key in rs and rs[key]['kind'] == 'ui'       # referenced: its slot slack is ours
        try:
            if key in PREWRAP:        # one screen row per '\n'-separated line: wrap here, not in the game
                en = prewrap(en, PREWRAP[key])
            b = encode(en)
        except UnicodeEncodeError:
            errors.append('progstr %s: not ASCII: %r' % (key, en))
            continue
        if convs(b) != convs(jp) and not (key in DROP_ARGS and not FMT.findall(b)):
            errors.append('progstr %s: conversions %s, Japanese has %s' % (key, FMT.findall(b), FMT.findall(jp)))
            continue
        if escs(b) != escs(jp) and b'\x1bT' not in b and key not in FREE_ESC:      # a line laid out again with {T..} is free
            errors.append('progstr %s: escape codes %s, Japanese has %s' % (
                key, vis(b''.join(escs(b)).decode()), vis(b''.join(escs(jp)).decode())))
            continue
        err = fmt_error(key, b, jp, lims.get(key, []))
        if err:
            errors.append(err)
            continue
        if len(b) <= room:
            imgs[tag].put(va, b + bytes(room + 1 - len(b)))
            ADDR[key] = va
            if own:
                pool.add(tag, va + len(b) + 1, room - len(b))
            continue
        code, data, block = refs.of(tag, va)
        if not code and not data and not block:
            errors.append('progstr %s: %d bytes, room %d and no reference to repoint' % (key, len(b), room))
            continue
        if [x for x in block if not x.startswith('gp-relative')]:
            errors.append('progstr %s: %d bytes, room %d; %s' % (key, len(b), room, '; '.join(block)))
            continue
        imgs[tag].put(va, bytes(room + 1))
        pool.add(tag, va, room + 1)
        moving.append((key, tag, b, code, data, refs.gp_users(tag, va)))
    pool.merge()
    placed = {}                                  # (space, English) -> va; gp-reachable ones first, longest first
    for key, tag, b, code, data, gps in sorted(moving, key=lambda m: (not m[5], -len(m[2]))):
        new = next((va for (sp, e), va in placed.items() if e == b and (sp == tag or sp == 'PROG')
                    and (not gps or GP - 0x8000 <= va < GP + 0x8000 - len(b))), None)
        if new is None:
            got = pool.take(tag, len(b) + 1, bool(gps))
            if got is None:
                errors.append('progstr %s: %d bytes, no free space left%s (space)' % (key, len(b), ' near gp' if gps else ''))
                continue
            space, new = got
            if space != 'PROG' and False:     # overlay tail
                files[space] += bytes(new + len(b) + 1 - OVL_BASE - len(files[space]))
                imgs[space] = images({space: files[space]})[0]
            imgs[space].put(new, b + b'\0')
            placed[(space, b)] = new
        _repoint(imgs, ctag, key, new, code, data)
        ADDR[key] = new
        for s, u in gps:
            uw = ctag[s].w(u)
            assert imgs[s].w(u) == uw, 'progstr %s: gp reference at %s:%x already patched' % (key, s, u)
            imgs[s].put(u, struct.pack('<I', (uw & 0xFFFF0000) | ((new - GP) & 0xFFFF)))
    if errors:
        raise ValueError('\n'.join(errors))
    return len(tl), len(moving), pool


def _repoint(imgs, ctag, key, new, code, data):
    """Point the data words and lui/user code pairs of a string at new."""
    for s, at in data:
        imgs[s].put(at, struct.pack('<I', new))
    for s, l, u in code:
        lw, uw = ctag[s].w(l), ctag[s].w(u)
        assert (imgs[s].w(u) == uw), 'progstr %s: code at %s:%x already patched' % (key, s, u)
        hi = (new + 0x8000) >> 16 & 0xFFFF
        lo = (new - (hi << 16)) & 0xFFFF
        if uw >> 26 == 0x0D:                                  # ori: unsigned low half
            hi, lo = new >> 16, new & 0xFFFF
        imgs[s].put(l, struct.pack('<I', (lw & 0xFFFF0000) | hi))
        imgs[s].put(u, struct.pack('<I', (uw & 0xFFFF0000) | lo))


# ---------------------------------------------------------------- survey

JP = re.compile('[぀-ヿ一-鿿！-～　-〿｡-ﾟ]')
JP_FULL = re.compile('[぀-ヿ一-鿿！-～　-〿]')


def _is_text(b):
    i, jp = 0, 0
    while i < len(b):
        c = b[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            if i + 1 >= len(b) or not (0x40 <= b[i + 1] <= 0xFC and b[i + 1] != 0x7F):
                return False
            jp += 1
            i += 2
            continue
        if 0xA1 <= c <= 0xDF:
            jp += 1
        elif not (0x20 <= c < 0x7F or c in (0x0A, 0x1B, 0x09)):
            return False
        i += 1
    return jp > 0


GAIJI_STRINGS = {}
def candidates(img):
    """[(vaddr, bytes)] of the Shift-JIS strings in the image's data (mostly Japanese)."""
    out, b = [], img.data
    for va in GAIJI_STRINGS.get(img.tag, ()):
        out.append((va, bytes(b[img.f(va):b.index(b'\0', img.f(va))])))
    for d_lo, d_hi in img.data_ranges:
        lo = d_lo
        for s_lo, s_hi in [x for x in img.skip if d_lo <= x[0] < d_hi] + [(d_hi, d_hi)]:
            if s_lo > lo:
                out += _scan(img, img.f(lo), img.f(s_lo - 1) + 1)
            lo = max(lo, s_hi)
    return sorted(out)


def _scan(img, o, hi):
    out, b = [], img.data
    while o < hi:
        if b[o] == 0:
            o += 1
            continue
        e = b.find(b'\0', o)
        if e < 0:
            break
        # a string starts after a NUL or, right after a pointer word, at a 4-aligned address
        starts = [o] if b[o - 1] == 0 else []
        starts += [p for p in range(o + 1, e) if (p - img.foff + img.base) % 4 == 0]
        # alignment padding is not always zero (linker leftovers such as '(' or 'ort' before a string):
        # 1-3 ASCII bytes between a NUL and a 4-aligned address are skipped (S7: MP "Sword skill rose")
        if len(starts) > 1 and starts[1] - o < 4 and (o - img.foff + img.base) % 4 and \
                all(0x20 <= c < 0x7f or c in (9, 10) for c in b[o:starts[1]]) and b[starts[1]] != 0:
            starts[0], starts[1] = starts[1], starts[0]
        for p in starts:
            s = bytes(b[p:e])
            if _is_text(s):
                t = s.decode('cp932', 'replace')
                fw = len(JP.findall(t))
                if '�' not in t and (fw >= 2 or JP_FULL.search(t)) and (fw * 2 >= len(t.strip(" ")) * 0.5 or FMT.search(s)):
                    out.append((p - img.foff + img.base, s))
                break
        o = e + 1
    return out


_FMT_S = re.compile(r'%[-+ #0]*\d*[hl]?[dsxuc]')
# likely debug output (never shown): workers still see these, flagged
# (S5: padded button labels start with spaces and multi-line texts end with \n: not debug signs here)
DEBUG = re.compile(r'Algo|－.*処理|処理$|\*\*\*|===|<<|>>|\$\$|->|Phase|Buffer|Error|[:：]%d')


def _junk(t):
    """One kanji + ASCII bytes: an instruction or a number that looks like text."""
    rest = _FMT_S.sub('', t)
    # labels like ' 金', '金:%d', '残  %3d' are text: only stray letters make it an instruction
    return (len(JP.findall(t)) == 1 and len(rest) > 1 and all(c.isascii() for c in rest if not JP.match(c))
            and any(c.isalpha() and c.isascii() for c in rest))


GRID = re.compile('あいうえお|アイウエオ')       # name-entry kana grids (names phase)


def _array(t, va, tag):
    """A string without a reference that looks like real text (an array element);
    lone kanji outside the program are data words."""
    return va % 4 == 0 and (len(t) > 1 or SDATA[0] <= va < SDATA[1]) and all(JP_FULL.match(c) or c in ' \n%d' for c in t)


def survey(imgs):
    """[row] of every candidate string: key, tag, va, room, code, data, block, jp (text),
    ui (to translate), debug (flag), kind (ui / noref / junk)."""
    refs = Refs(imgs)
    rows = []
    for img in imgs:
        if img.tag in NO_STRINGS:
            continue
        for va, s in candidates(img):
            jp, room = slot(img, va)
            code, data, block = refs.of(img.tag, va)
            t = jp.decode('cp932')
            gp = any('gp-relative' in x for x in block)
            if data and not code and not gp and all(g == 'PROG' and NAME_TABLE[0] <= at < NAME_TABLE[1] for g, at in data):
                kind = 'name'                         # person table strings: tools/names.py
            elif code or data or gp:
                kind = 'junk' if _junk(t) else 'ui'
            elif _array(t, va, img.tag):
                kind = 'grid' if GRID.search(t) else 'array'
                block = block + ['no reference (element of a fixed-size array?)']
            else:
                kind = 'noref'
            rows.append({'key': '%s:%08x' % (img.tag, va), 'tag': img.tag, 'va': va, 'room': room,
                         'code': len(code), 'data': len(data), 'block': block, 'jp': t,
                         'ui': kind in ('ui', 'array'), 'debug': kind == 'ui' and bool(DEBUG.search(t)),
                         'kind': kind})
    return rows


def disc_files(disc, recs=None):
    """{tag: bytes} of the program and the overlays from the disc."""
    recs = recs or disc.records()
    out = {'PROG': disc.file(iso.EXE_NAME, recs)}
    for t in OVERLAYS:
        out[t] = disc.file(ovl_name(t), recs)
    return out


def clean_files():
    import setup
    return disc_files(iso.Disc(setup.CLEAN))


def export():
    rows = survey(images({t: bytearray(b) for t, b in clean_files().items()}))
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return rows


def rows():
    if not os.path.exists(SCRIPT):
        export()
    return json.load(open(SCRIPT, encoding='utf-8'))


def _order(key):
    tag, va = parse_key(key)
    return (('PROG',) + OVERLAYS).index(tag), va


def show(lo=None, hi=None, todo=False):
    """Print the strings to translate in [lo, hi] (keys), address order:
    key  room  M (movable if the English is longer) / F (fixed: must fit room)  D (debug?)  Japanese  => English"""
    tl = load_tl()
    rs = [r for r in rows() if r['ui']]
    res = resolved(tl, rs)
    for r in rs:
        if lo and _order(r['key']) < _order(lo) or hi and _order(r['key']) > _order(hi):
            continue
        en = tl.get(r['key'])
        if todo and en is not None:
            continue
        mark = '' if en is not None else '[tm] ' + res[r['key']] if r['key'] in res else ''
        print('%s\t%d\t%s%s\t%s%s' % (r['key'], r['room'], 'F' if r['block'] else 'M', ' D' if r['debug'] else '',
                                    vis(r['jp']).replace('\n', '\\n'), '\t=> ' + (en.replace('\n', '\\n') if en is not None else mark) if en is not None or mark else ''))


SCATTERED = ('02', '29', '90')      # files whose keys are not one address range


def owners():
    """{key: tl file} for every ui string: the file with its English, or, for a string covered by the
    translation memory, the file of the nearest explicit key before it (address order)."""
    own = {}
    for fn in sorted(os.listdir(TL)):
        if fn.endswith('.txt'):
            for k in load_tl_file(os.path.join(TL, fn)):
                own[k] = fn
    out, last = {}, None
    for r in rows():
        if not r['ui']:
            continue
        k = r['key']
        if k in own:
            out[k] = own[k]
            if own[k][:2] not in SCATTERED:
                last = own[k]
        elif last:
            out[k] = last
    for k, fn in own.items():
        out.setdefault(k, fn)
    return out


def review(names):
    """Print the strings of the given tl files (basename) for a review: key, slot, Japanese, English
    (EN = this file's own line, EN* = taken from an identical Japanese string elsewhere)."""
    tl = load_tl()
    rs = {r['key']: r for r in rows()}
    res = resolved(tl, [r for r in rs.values() if r['ui']])
    own = owners()
    for fn in names:
        fn = os.path.basename(fn)
        print('##### %s' % fn)
        for k in sorted((k for k, f in own.items() if f == fn), key=_order):
            r = rs.get(k)
            en = tl.get(k, res.get(k))
            if r is None:                       # a format without Japanese given English by key
                print('%s\t(no Japanese: layout format, do not change)\n    EN: %s' % (k, en.replace('\n', '\\n')))
                continue
            jp = vis(r['jp']).replace('\n', '\\n')
            w = '' if en in (None, '-') or '\n' in r['jp'] or len(r['jp']) > 12 else '  [label %d px, Japanese %d px]' % (px(en), px(r['jp'], True))
            print('%s\t%s%s\n    JP: %s\n    %s %s' % (k, 'FIXED %d bytes' % r['room'] if r['block'] else 'room %d' % r['room'], w, jp,
                                                  'EN:' if k in tl else 'EN*:', (en or '').replace('\n', '\\n')))


def apply_batch(fn, batch):
    """Put the key<TAB>English lines of a batch file into tl file fn (replace the key's line, or append
    it when the string had only shared English); checked, and undone when the check fails."""
    fn = os.path.basename(fn)
    path = os.path.join(TL, fn)
    own = owners()
    new = {}
    for n, line in enumerate(open(batch, encoding='utf-8').read().splitlines(), 1):
        if not line.strip() or line.startswith('#'):
            continue
        k, tab, v = line.partition('\t')
        if not (tab and KEY.fullmatch(k) and v.strip()):
            sys.exit('batch line %d: expected key<TAB>English: %r' % (n, line))
        if own.get(k) != fn:
            sys.exit('batch line %d: %s does not belong to %s (it belongs to %s)' % (n, k, fn, own.get(k)))
        new[k] = v
    old = open(path, encoding='utf-8').read()
    out, seen = [], set()
    for line in old.splitlines():
        k = line.partition('\t')[0]
        if k in new and not line.startswith('#'):
            out.append(k + '\t' + new[k])
            seen.add(k)
        else:
            out.append(line)
    rest = [k for k in new if k not in seen]
    if rest:
        if '# review: own English for strings that shared another string\'s line' not in out:
            out.append('# review: own English for strings that shared another string\'s line')
        out += [k + '\t' + new[k] for k in rest]
    open(path, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    try:
        ok = check(set(new))
    except Exception as e:
        ok = False
        print('error:', e)
    if not ok:
        open(path, 'w', encoding='utf-8').write(old)
        sys.exit('NOT applied: fix the errors above and apply again')
    print('applied: %d changed, %d new own lines in %s' % (len(seen), len(rest), fn))


def stats():
    tl = load_tl()
    rs = rows()
    ui = [r for r in rs if r['ui']]
    res = resolved(tl, ui)
    done = sum(r['key'] in tl or r['key'] in res for r in ui)
    print('candidates %d (%s)' % (len(rs), ', '.join('%s %d' % kv for kv in sorted(collections.Counter(r['kind'] for r in rs).items()))))
    for tag in ('PROG',) + OVERLAYS:
        t = [r for r in ui if r['tag'] == tag]
        print('  %-8s ui %4d  fixed %4d  chars %5d' % (tag, len(t), sum(bool(r['block']) for r in t), sum(len(r['jp']) for r in t)))
    print('ui strings %d: done %d (%d explicit, %d kept Japanese "-"), todo %d; debug-flagged %d'
          % (len(ui), done, sum(r['key'] in tl and tl[r['key']] != '-' for r in ui), sum(tl.get(r['key']) == '-' for r in ui),
             len(ui) - done, sum(r['debug'] for r in ui)))
    keys = {r['key'] for r in ui}
    stray = [k for k in tl if k not in keys]
    if stray:
        print('keys not in the ui list:', ' '.join(stray[:20]))


_W = None


def px(t, jp=False):
    """Pixel width of the widest line: English with the VWF font (tools/pixfont.py),
    Japanese 12 per full-width and 6 per half-width character (Ishin: 12x12 font)."""
    global _W
    if t.startswith(FW):
        return 16 * len(t) - 16 * len(FW)
    if _W is None:
        import pixfont
        _W = {c: g[1] for c, g in pixfont.glyphs().items()}
    if not jp:
        return max(text.pixels(text.fold(line)) for line in t.split('\n'))
    return max(sum(6 if c.isascii() or '\uff61' <= c <= '\uff9f' else 12 for c in line) for line in t.split('\n'))


def wide(tl=None):
    """[(key, en px, jp px, en, jp)] of English wider than its Japanese (labels may be cut)."""
    tl = load_tl() if tl is None else tl
    out = []
    for r in rows():
        en = tl.get(r['key'])
        if r['ui'] and en and en != '-' and px(en) > px(r['jp'], True):
            out.append((r['key'], px(en), px(r['jp'], True), en, r['jp']))
    return out


def check(only=None):
    """Dry-run apply on the clean files; prints errors (only: report just these keys). True if clean."""
    # a partial set has little slot slack yet: free space is only judged over the whole set (build)
    keep = lambda line: only is None or any(k in line for k in only) and not line.endswith('(space)')
    clean = clean_files()
    files = {t: bytearray(b) for t, b in clean.items()}
    try:
        n, moved, pool = apply(files, clean, resident(clean['PROG']))
        print('progstr: %d strings OK (%d moved); free left %s; overlays grown %s' % (
            n, moved, pool.room(), pool.grown))
    except ValueError as e:
        errs = [x for x in str(e).split('\n') if keep(x)]
        if only is None or errs:
            print('\n'.join(errs))
            return False
        print('progstr: your strings OK')
    u = [] if not fmtlimit.SPRINTF else [x for x in fmt_unknown(resolved(load_tl(), [r for r in rows() if r['ui']])) if keep(x[0])]
    if u:
        print('%d formats longer than the Japanese with an unknown sprintf target (check):' % len(u))
        for k, n, j, sites in u:
            print('  %s %d > %d bytes  sprintf at %s' % (k, n, j, ' '.join(sites)))
    tl = load_tl()
    long = [(r['key'], len(text.wrap(tl[r['key']], DESC_PX))) for r in rows()
            if r['tag'] == 'PROG' and DESC[0] <= r['va'] < DESC[1] and len(r['jp']) > 13 and tl.get(r['key'], '-') != '-']
    long = [x for x in long if x[1] > DESC_LINES and keep(x[0])]
    for k, n in long:
        print('  %s card description: %d lines at %d px (box holds %d)' % (k, n, DESC_PX, DESC_LINES))
    if long:
        return False
    w = [x for x in wide() if keep(x[0])]
    if w:
        print('%d strings wider than the Japanese (may be cut or wrapped; shorten labels where possible):' % len(w))
        for k, a, b, en, jp in w:
            print('  %s %d > %d px  %s  (%s)' % (k, a, b, en.replace('\n', '\\n'), jp.replace('\n', '\\n')))
    return True


if __name__ == '__main__':
    a = sys.argv[1:]
    if a == ['export']:
        print(len(export()), 'strings ->', SCRIPT)
    elif a and a[0] == 'show':
        todo = '--todo' in a
        a = [x for x in a[1:] if x != '--todo']
        show(a[0] if a else None, a[1] if len(a) > 1 else None, todo)
    elif a and a[0] == 'review' and len(a) > 1:
        review(a[1:])
    elif len(a) == 3 and a[0] == 'apply':
        apply_batch(a[1], a[2])
    elif a == ['stats']:
        stats()
    elif a and a[0] == 'check':
        only = set(load_tl_file(a[1])) if len(a) > 1 else None
        sys.exit(0 if check(only) else 1)
    else:
        print(__doc__)
