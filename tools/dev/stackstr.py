"""Strings built on the stack by immediate byte stores (li rX, byte / sb rX, off(sp)).

The compiler initialised local char arrays this way, so these texts are in no data section (hanafuda
settings and menu, kanji numerals ...). Lists every run of such stores as (first pc, last pc, sp
offset, text).

usage: python3 tools/dev/stackstr.py [TAG ...]      TAG = PROG or an overlay name (default: all)
"""
import os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import progstr

GAP = 12          # instructions without a byte store that end a run


def stores(data, base, foff=0):
    """[(pc, sp offset, value, li pc or None)] of sb reg, off(sp) with a known register value."""
    reg, out = {0: (0, None)}, []
    for o in range(foff, len(data) - 3, 4):
        w = struct.unpack_from('<I', data, o)[0]
        pc = base + o - foff
        op, rs, rt, imm = w >> 26, w >> 21 & 31, w >> 16 & 31, w & 0xffff
        if op in (9, 13) and rs == 0:                 # addiu / ori rt, zero, imm
            reg[rt] = (imm & 0xff, pc) if imm < 0x100 else None
        elif op == 0x28 and rs == 29:                 # sb rt, off(sp)
            if reg.get(rt):
                out.append((pc, imm, reg[rt][0], reg[rt][1]))
        elif op == 0 and w & 0x3f == 8 or op == 3:    # jr / jal: temporaries are gone
            reg = {0: (0, None)}
        elif op in (8, 9, 10, 11, 12, 13, 14, 15, 0x20, 0x21, 0x23, 0x24, 0x25):
            reg.pop(rt, None)
        elif op == 0:
            reg.pop(w >> 11 & 31, None)
    return out


def runs(st):
    """Group the stores into runs (one array initialisation block each)."""
    out, cur = [], []
    for s in st:
        if cur and s[0] - cur[-1][0] > 4 * GAP:
            out.append(cur)
            cur = []
        cur.append(s)
    if cur:
        out.append(cur)
    return out


def strings(run):
    """[(sp offset, bytes)] of the contiguous byte ranges of a run."""
    mem = {off: v for _, off, v, _ in run}
    out, offs = [], sorted(mem)
    i = 0
    while i < len(offs):
        j = i
        while j + 1 < len(offs) and offs[j + 1] == offs[j] + 1:
            j += 1
        out.append((offs[i], bytes(mem[o] for o in offs[i:j + 1])))
        i = j + 1
    return out


def images(tags=None):
    clean = progstr.clean_files()
    for tag, b in clean.items():
        if tags and tag not in tags:
            continue
        if tag == 'PROG':
            yield tag, b, 0x80010000, 0x800
        else:
            yield tag, b, progstr.OVL_BASES.get(tag, progstr.OVL_BASE), 0


if __name__ == '__main__':
    for tag, b, base, foff in images(sys.argv[1:]):
        for run in runs(stores(b, base, foff)):
            for off, s in strings(run):
                if len(s) < 4:
                    continue
                t = s.replace(b'\0', b'|').decode('cp932', 'replace')
                if not progstr.JP.search(t):
                    continue
                print('%s %08x-%08x sp+%04x %3d  %s' % (tag, run[0][0], run[-1][0], off, len(s), t))
