"""List the graphic loading calls with their constant arguments (dev tool).

read  0x8009f47c(name, buf, sector, count)      file piece -> RAM
clut  0x800b6bbc(pal, x, y)  16 colours -> VRAM;  0x800b6b58(pal, x, y) 256 colours
tpage 0x800b6a70(pix, mode, abr, x, y, w, h)    pixels -> VRAM (mode 0 = 4bpp, 1 = 8bpp, 2 = 16bpp)

usage: python3 tools/dev/gfxcalls.py [TAG ...]     (PROG, COM, ... default all)
"""
import os, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OVL = 'COM GATE HANA INIT KAIWA MARCH MOVIE MP MP2 PERS PERS2 SCOM STAFF WAR'.split()
FUN = {0x8009f47c: ('read', 4), 0x800b6bbc: ('clut', 3), 0x800b6b58: ('clut256', 3), 0x800b6a70: ('tpage', 7)}
exe = open(os.path.join(ROOT, 'extract/SLPM_861.44'), 'rb').read()[0x800:]

def cstr(a, d=None, base=0):
    o, src = a - 0x80010000, exe
    if d is not None and 0 <= a - base < len(d):
        o, src = a - base, d
    if 0 <= o < len(src):
        e = src.find(b'\0', o)
        s = src[o:e]
        if 3 < len(s) < 40 and all(32 <= c < 127 for c in s):
            return s.decode()

def scan(tag):
    if tag == 'PROG':
        d, base = exe, 0x80010000
    else:
        d = open(os.path.join(ROOT, 'extract/CODE/%s.BIN' % tag), 'rb').read()
        base = 0x801e0000 if tag == 'PERS2' else 0x8015b858
    n = len(d) // 4
    W = struct.unpack('<%dI' % n, d[:n * 4])
    for i, w in enumerate(W):
        if w >> 26 != 3 or ((w & 0x3ffffff) << 2 | 0x80000000) not in FUN:
            continue
        name, na = FUN[(w & 0x3ffffff) << 2 | 0x80000000]
        reg, stk = {0: 0}, {}
        lo = i - 1
        while lo > 0 and i - lo < 40 and W[lo - 1] >> 26 != 3:      # back to the previous call
            lo -= 1
        for j in list(range(lo, i)) + [i + 1]:
            x = W[j]; op = x >> 26; rs = (x >> 21) & 31; rt = (x >> 16) & 31; im = x & 0xffff
            sim = im - 0x10000 if im & 0x8000 else im
            if op == 0xf: reg[rt] = im << 16
            elif op == 9 and rs in reg: reg[rt] = (reg[rs] + sim) & 0xffffffff
            elif op == 9: reg.pop(rt, None)
            elif op == 0xd and rs in reg: reg[rt] = reg[rs] | im
            elif op == 0 and (x & 0x7ff) in (0x21, 0x25) and rt == 0 and rs in reg: reg[(x >> 11) & 31] = reg[rs]
            elif op == 0 and (x & 0x3f) not in (0, 8) : reg.pop((x >> 11) & 31, None)
            elif op == 0x2b and rs == 29: stk[im] = reg.get(rt)
            elif op in (0x23, 0x21, 0x25, 0x20, 0x24): reg.pop(rt, None)
        args = [reg.get(4 + k) for k in range(min(na, 4))] + [stk.get(0x10 + 4 * k) for k in range(na - 4)]
        out = []
        for k, a in enumerate(args):
            s = cstr(a, d, base) if a is not None and k == 0 and name == 'read' else None
            out.append(s or ('?' if a is None else hex(a) if a > 0xffff else str(a)))
        print('%-5s %08x %-7s %s' % (tag, base + i * 4, name, ', '.join(out)))

for t in sys.argv[1:] or ['PROG'] + OVL:
    scan(t)
