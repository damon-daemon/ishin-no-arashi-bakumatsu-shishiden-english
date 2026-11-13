"""Static scan of the EEX opcode handlers in SLPM_861.44: which operand tags each opcode reads.

The dispatcher at 0x80056a30 reads a u16 opcode (< 0xa0) and jumps through the table at 0x8001d694.
Operands are read as: jal READ16 (tag); xori tag; bnez skip; jal READ16 / READ32 / READSTR (value).
This prints, per opcode, the tags in code order (calls into helper functions are followed), with
'L' marks where a backward branch (loop) closes: those need a look by hand.

  .venv/bin/python tools/dev/eexops.py            all opcodes
  .venv/bin/python tools/dev/eexops.py 0x32       one opcode, with addresses
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mips

TABLE, NOPS, EXIT = 0x8001d694, 0xa0, 0x80057ce4
READ8, READ16, READ32, READSTR, SKIP = 0x80047780, 0x800477a0, 0x800477dc, 0x80047858, 0x800476f4
PEEK16, PEEKB, PEEKH, PEEKW = 0x80047b7c, 0x80047890, 0x800478a8, 0x800478d0
READERS = {READ8: 'byte', READ16: 'h', READ32: 'w', READSTR: 's', SKIP: 'skip', PEEK16: 'peek', PEEKB: 'peekb', PEEKH: 'peekh', PEEKW: 'peekw'}
img = mips.Image('jp')


def jal_target(w):
    return 0x80000000 | ((w & 0x3FFFFFF) << 2) if w >> 26 == 3 else None


_reads = {}
def reads(fn, depth=0):
    """Does the function at fn (to its jr ra) call a reader, directly or through helpers?"""
    if fn in _reads:
        return _reads[fn]
    _reads[fn] = False
    if not (0x80046000 <= fn < 0x8005a000) or depth > 6:
        return False
    r = False
    for va in range(fn, fn + 0x4000, 4):
        w = img.word(va)
        t = jal_target(w)
        if t in READERS or (t and reads(t, depth + 1)):
            r = True
            break
        if w == 0x03e00008:
            break
    _reads[fn] = r
    return r


def scan(start, end, out, depth=0, verbose=False):
    """Walk [start, end) in address order; append tags / marks to out."""
    va = start
    while va < end:
        w = img.word(va)
        t = jal_target(w)
        if t == READ16:
            tag = None
            for k in range(2, 7):                       # xori $v0, $v0, tag after the delay slot
                x = img.word(va + 4 * k)
                if x >> 26 == 0x0e:
                    tag = x & 0xffff
                    break
                if jal_target(x) or x >> 26 in (4, 5, 2):
                    break
            if tag is not None:
                out.append(('%x' % tag, va))
            else:
                out.append(('v', va))                    # a value read (or an untagged word)
        elif t in READERS:
            out.append((READERS[t], va))
        elif t and reads(t):
            out.append(('(', va))
            fend = t
            while img.word(fend) != 0x03e00008:
                fend += 4
            scan(t, fend, out, depth + 1)
            out.append((')', va))
        op = w >> 26
        if op in (4, 5, 6, 7, 1):                        # backward branch = loop
            tgt = va + 4 + (mips.s16(w & 0xffff) << 2)
            if tgt <= va and tgt >= start:
                out.append(('L<%x' % tgt, va))
        if w == 0x03e00008 and depth:
            break
        va += 4
    return out


def handlers():
    t = [img.word(TABLE + 4 * i) for i in range(NOPS)]
    order = sorted(set(t) | {EXIT})
    return t, {a: order[order.index(a) + 1] for a in order if a != EXIT}


def signature(op, verbose=False):
    t, nxt = handlers()
    a = t[op]
    if a == EXIT:
        return None
    return scan(a, nxt[a], [])


if __name__ == '__main__':
    if len(sys.argv) > 1:
        for s, va in signature(int(sys.argv[1], 0)):
            print('%08x %s' % (va, s))
    else:
        for op in range(NOPS):
            s = signature(op)
            print('%02x %s' % (op, '-' if s is None else ' '.join(x for x, _ in s)))
