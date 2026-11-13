"""English text for the event scripts: character set, wrapping, box pages.

English (tl/): UTF-8 with the macron vowels ō ū Ō Ū; '\\n' forces a line break. Typographic
quotes, dashes and ellipses are folded to ASCII. The macron vowels use the codes of ^ ~ | `
(pixfont.MACRONS), so those four characters cannot be written.

Boxes (KIND by opcode; all measured in the emulator with a test script, session 4):
  talk (0x18), talk2 (0x85: speaker, listener, text): dialogue window, text rectangle 296 px,
               a name line + 3 text lines. The game prints the whole string at once and does not
               page, so build wraps at the width and cuts every 3 lines into a new box (tl.py
               repeats the statement).
  narr (0x20)  narration window, text rectangle 280 x 56 px = 3 lines; cut into boxes like talk.
  op19 (0x19)  three variants of one line of the protagonist (the game picks one by his speech
               style: Ryoma gets the second), dialogue window: 3 lines at most, no split.
  choice (0x1b) one option per line, each in a bar; the menu is as wide as the longest option
               and the options are centred in it (pixel widths: vwf.MENUS; the game counted 6 px
               per byte), so an option may be CHOICE_PX wide; the number of options is fixed by
               the script.
  label (0x94) text of the status screen (COM.BIN): slot 0 "current situation" 276 x 32 px =
               2 lines, slots 1 and 2 "current goals" printed as "%s\n%s" in 276 x 96 px =
               6 lines together (3 each here). Stored in 128-byte slots: 127 bytes at most.
  op7f (0x7f)  read and thrown away by the program (text of movie scenes): never inserted.
The printer also wraps words at run time (vwf.py). The name tokens (expander 0x8006ffb4: S1 M1
F1 P1 = surname, given name, full name, pronoun of the speaker; S2 ... of the listener; A, K)
are replaced before printing and are measured here with TOKEN_PX each.
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import vwf
from vwf import width as pixels

KIND = {0x18: 'talk', 0x19: 'op19', 0x1b: 'choice', 0x20: 'narr', 0x7f: 'op7f', 0x85: 'talk2',
        0x94: 'label'}
TALK_PX, TALK_LINES = 296, 3
BOX = {'talk': (296, 3), 'talk2': (296, 3), 'narr': (280, 3)}      # split into further boxes
SKIP = ('op7f',)                      # never shown by the game
CHOICE_PX = 288
LABEL_PX, LABEL_LINES, LABEL_BYTES = 276, {0: 2, 1: 3, 2: 3}, 127
TOKEN_PX = 48                         # assumed width of a name token
_TOKEN = re.compile(r'[SMFP][12]')
FOLD = {'‘': "'", '’': "'", '“': '"', '”': '"', '—': '--', '–': '-', '…': '...', ' ': ' '}
FOLD.update(vwf.MACRONS)


def decode(b):
    return b.decode('cp932')


def fold(en):
    return ''.join(FOLD.get(c, c) for c in en)


def check(en):
    """-> list of problems with an English string."""
    errs = []
    if re.search(r'[\^~|`]', en):
        errs.append('reserved character (^ ~ | ` are the macron letters in the font)')
    bad = sorted(set(c for c in fold(en) if not (' ' <= c <= '~')))
    if bad:
        errs.append('characters not in the font: %r' % ''.join(bad))
    if re.search(r'\\(?!n)', en):
        errs.append('backslash other than \\n')
    return errs


def px(s):
    """pixels of a folded line; name tokens count TOKEN_PX."""
    return pixels(_TOKEN.sub('', s)) + TOKEN_PX * len(_TOKEN.findall(s))


def wrap(en, width):
    """English ('\\n' = forced break) -> list of lines (folded ASCII)."""
    out = []
    for para in fold(en).split('\\n'):
        line = ''
        for w in para.split():
            if line and px(line + ' ' + w) > width:
                out.append(line)
                line = w
            else:
                line = line + ' ' + w if line else w
        out.append(line)
    return out


def boxes(en, width=TALK_PX, lines=TALK_LINES):
    """English -> list of box texts (bytes, lines joined by 0x0a)."""
    ls = wrap(en, width)
    return ['\n'.join(ls[i:i + lines]).encode('ascii') for i in range(0, len(ls), lines)]


def fit(op, en, slot=0, jp=''):
    """English of one string -> ([box bytes], [problems]). More than one box only for BOX kinds."""
    kind = KIND[op]
    if kind in BOX:
        return boxes(en, *BOX[kind]), []
    if kind == 'op19':
        ls = wrap(en, TALK_PX)
        return ['\n'.join(ls).encode('ascii')], ['%d lines (3 fit)' % len(ls)] if len(ls) > 3 else []
    if kind == 'label':
        ls = wrap(en, LABEL_PX) if en else []
        b = '\n'.join(ls).encode('ascii')
        errs = []
        if len(ls) > LABEL_LINES.get(slot, 2):
            errs.append('%d lines (%d fit in slot %d)' % (len(ls), LABEL_LINES.get(slot, 2), slot))
        if len(b) > LABEL_BYTES:
            errs.append('%d bytes (%d fit)' % (len(b), LABEL_BYTES))
        return [b], errs
    if kind == 'choice':
        b = plain(en)
        opts = b.split(b'\n')
        errs = ['option %r: %d px (%d fit)' % (o.decode(), pixels(o.decode()), CHOICE_PX)
                for o in opts if pixels(o.decode()) > CHOICE_PX]
        if len(opts) != jp.count('\n') + 1:
            errs.append('%d options, the Japanese has %d' % (len(opts), jp.count('\n') + 1))
        return [b], errs
    return [plain(en)], []


def plain(en):
    """English of an unwrapped op -> bytes."""
    return fold(en).replace('\\n', '\n').encode('ascii')


def jp_show(s):
    return s.replace('\n', '\\n')
