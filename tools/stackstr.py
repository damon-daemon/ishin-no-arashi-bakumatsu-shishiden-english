"""Texts that exist only as instructions: local char arrays filled by `li rX, byte` / `sb rX, off(sp)`.

The hanafuda menu and settings, the fencing mode menu and two small program labels are built on the
stack one byte at a time, so no data section holds them and progstr cannot see them
(`tools/dev/stackstr.py` lists every such run). Here the store sequence of a run is written again
for the English text, inside the same instruction slots:

  * slots = every `sb rX, off(sp)` into one of the run's arrays + every `li` whose value is used by
    such stores only (its register is redefined, or dies at a call, before any other use);
  * new code uses $at only: `li at, byte` then one `sb at, off(sp)` per position holding that byte
    (`sb zero` for the terminators), and $at is loaded again after any call inside the run;
  * only the text and its NUL are written (an empty slot gets its NUL); spare slots become nops.

The run must not contain branches. English that needs more instructions than there are slots fails
the build. Text: tl/stackstr.txt, lines `table.index<TAB>English` (TABLES below gives the layout).

  python3 tools/stackstr.py          the tables with Japanese, English and the slot budget
"""
import os, struct, sys

import progstr

TL = os.path.join(progstr.ROOT, 'tl', 'stackstr.txt')

# name: (tag, first pc, last pc of the run, sp offset, slot size, slots)
TABLES = {
    'hana_rounds': ('HANA', 0x80161640, 0x801617c4, 0x10, 20, 4),      # "How many rounds shall we play?"
    'hana_menu': ('HANA', 0x8016186c, 0x80161c80, 0x10, 40, 6),        # Hanafuda Lessons menu
    'hana_koikoi': ('HANA', 0x80162680, 0x80162780, 0x10, 15, 3),      # "Koi-koi?" choices
    'hana_set': ('HANA', 0x80163f58, 0x80164e98, 0x10, 25, 7),         # settings: labels (the last store is a delay slot)
    'hana_val': ('HANA', 0x80163f58, 0x80164e98, 0xc0, 25, 30),        # settings: values, 5 per label
    'scom_menu': ('SCOM', 0x8015caf0, 0x8015cd4c, 0x10, 25, 5),        # Fencing Drill mode menu
    'prog_dash': ('PROG', 0x80072b90, 0x80072ba8, 0x10, 7, 1),
    'prog_funds': ('PROG', 0x80072d24, 0x80072d48, 0x40, 7, 1),
}
AT = 1
TEMPS = {2, 3} | set(range(8, 16)) | {24, 25}      # v0 v1 t0-t9: dead after a call


def _f(tag, va):
    return va - 0x80010000 + 0x800 if tag == 'PROG' else va - progstr.OVL_BASES.get(tag, progstr.OVL_BASE)


def _decode(w):
    """(source registers, destination register or None, kind) kind: '' / 'call' / 'branch' / '?'"""
    op, rs, rt, rd, fn = w >> 26, w >> 21 & 31, w >> 16 & 31, w >> 11 & 31, w & 0x3f
    if w == 0:
        return set(), None, ''
    if op == 0:
        if fn in (0, 2, 3):
            return {rt}, rd, ''
        if fn == 8:
            return {rs}, None, 'branch'
        if fn == 9:
            return {rs}, rd, 'call'
        if fn in (0x10, 0x12):
            return set(), rd, ''
        if fn in (0x18, 0x19, 0x1a, 0x1b, 0x11, 0x13):
            return {rs, rt}, None, ''
        if fn in (4, 6, 7) or 0x20 <= fn <= 0x2b:
            return {rs, rt}, rd, ''
        return set(range(32)), None, '?'
    if op == 3:
        return set(), 31, 'call'
    if op == 2:
        return set(), None, 'branch'
    if op in (1, 6, 7):
        return {rs}, None, 'branch'
    if op in (4, 5):
        return {rs, rt}, None, 'branch'
    if op == 15:
        return set(), rt, ''
    if 8 <= op <= 14 or 0x20 <= op <= 0x26:
        return {rs}, rt, ''
    if 0x28 <= op <= 0x2e:
        return {rs, rt}, None, ''
    return set(range(32)), None, '?'


def _li(w):
    op, rs, rt, imm = w >> 26, w >> 21 & 31, w >> 16 & 31, w & 0xffff
    return rt if op in (9, 13) and rs == 0 and rt else None


class Run:
    """One store run of a file: the arrays in it, the slots, the Japanese."""

    def __init__(self, tag, pc0, pc1, data):
        self.tag, self.pc0, self.pc1 = tag, pc0, pc1
        self.arrays = sorted((off, size * n) for t, a, b, off, size, n in TABLES.values() if (t, a) == (tag, pc0))
        # the first loads come before the first store: take the straight-line code in front of it too
        # (back to the function's stack adjustment, a call or a branch; at most 64 instructions)
        self.start = pc0
        for _ in range(64):
            w = struct.unpack_from('<I', data, _f(tag, self.start - 4))[0]
            if w >> 16 == 0x27bd or _decode(w)[2] or AT in _decode(w)[0] or _decode(w)[1] == AT:
                break
            self.start -= 4
        seed = {0: 0}
        if self.start < pc0 and _decode(struct.unpack_from('<I', data, _f(tag, self.start - 4))[0])[2]:
            w = struct.unpack_from('<I', data, _f(tag, self.start))[0]
            if _li(w) and w & 0xffff < 0x100:
                seed[_li(w)] = w & 0xff           # a delay slot: its value counts, the instruction stays
            self.start += 4
        o = _f(tag, self.start)
        self.words = list(struct.unpack_from('<%dI' % ((pc1 - self.start) // 4 + 1), data, o))
        tail = struct.unpack_from('<64I', data, o + 4 * len(self.words))
        self.mem, self.slots, self.calls = {}, [], []
        reg = seed
        for i, w in enumerate(self.words):
            src, dst, kind = _decode(w)
            if kind in ('branch', '?') or AT in src or dst == AT:
                raise ValueError('stackstr %s:%08x: instruction %08x inside the run' % (tag, self.start + 4 * i, w))
            if kind == 'call':
                self.calls.append(i)
                reg = {0: 0}
            if self._store(w):
                rt = w >> 16 & 31
                if rt not in reg:
                    raise ValueError('stackstr %s:%08x: store of an unknown value at %08x' % (tag, pc0, self.start + 4 * i))
                self.mem[w & 0xffff] = reg[rt]
                self.slots.append(i)
            elif _li(w) and w & 0xffff < 0x100:
                reg[_li(w)] = w & 0xff
                if self._dead(i, _li(w), self.words + list(tail)):
                    self.slots.append(i)
            elif dst is not None:
                reg.pop(dst, None)
        self.slots.sort()

    def _store(self, w):
        return w >> 26 == 0x28 and w >> 21 & 31 == 29 and any(a <= w & 0xffff < a + n for a, n in self.arrays)

    def _dead(self, i, r, words):
        """The value loaded at i reaches string stores only."""
        for j in range(i + 1, len(words)):
            w = words[j]
            if j < len(self.words) and self._store(w):
                if w >> 16 & 31 == r:
                    continue
            src, dst, kind = _decode(w)
            if r in src:
                return False
            if dst == r:
                return True
            if kind == 'call':                    # the delay slot still runs before the call
                s2, d2, _ = _decode(words[j + 1]) if j + 1 < len(words) else (set(range(32)), None, '')
                return r not in s2 and (r in TEMPS or d2 == r)
            if kind:
                return False
        return False

    def text(self, off, size):
        b = bytes(self.mem.get(off + k, 0) for k in range(size))
        return b.split(b'\0')[0].decode('cp932', 'replace')

    def emit(self, mem):
        """New words for {sp offset: byte}; raises when the slots do not suffice."""
        by = {}
        for off, v in sorted(mem.items()):
            by.setdefault(v, []).append(off)
        ops = [(0, off) for off in by.pop(0, [])]            # sb zero: no load needed
        for v, offs in sorted(by.items()):
            ops += [(v, off) for off in offs]
        out, k, cur = list(self.words), 0, None

        def put(w):
            nonlocal k
            if k >= len(self.slots):
                raise ValueError('stackstr %s:%08x: English needs more than the %d instruction slots'
                                 % (self.tag, self.pc0, len(self.slots)))
            out[self.slots[k]] = w
            k += 1
        for v, off in ops:
            if v == 0:
                put(0xa3a00000 | off)                         # sb zero, off(sp)
                continue
            while True:
                if k >= len(self.slots):
                    put(0)
                # a call between the load and this store would clobber $at
                last = self.slots[k - 1] if k else -1
                if cur == v and not any(last < c <= self.slots[k] + 1 for c in self.calls):
                    break
                put(0x24010000 | v)                           # li at, v
                cur = v
            put(0xa3a10000 | off)                             # sb at, off(sp)
        used = k
        while k < len(self.slots):
            put(0)
        return out, used


def load_tl():
    tl = {}
    if os.path.exists(TL):
        for line in open(TL, encoding='utf-8'):
            line = line.rstrip('\n')
            if line and not line.startswith('#'):
                key, en = line.split('\t', 1)
                name, _, idx = key.rpartition('.')
                if name not in TABLES or not 0 <= int(idx) < TABLES[name][5]:
                    raise ValueError('stackstr: unknown key %s' % key)
                tl[(name, int(idx))] = en
    return tl


def patch(files, clean):
    """files / clean: {tag: bytes}; rewrites the runs that have English. Returns the number of texts."""
    tl = load_tl()
    runs = {}
    for (name, idx), en in tl.items():
        tag, pc0, pc1, off, size, n = TABLES[name]
        b = progstr.encode(en)
        if len(b) >= size:
            raise ValueError('stackstr %s.%d: %r is over %d bytes' % (name, idx, en, size - 1))
        runs.setdefault((tag, pc0, pc1), {})[(off + size * idx, size)] = b
    for (tag, pc0, pc1), texts in runs.items():
        run = Run(tag, pc0, pc1, clean[tag])
        mem = {}
        for t, a, _, off, size, n in TABLES.values():
            if (t, a) != (tag, pc0):
                continue
            for i in range(n):                    # untranslated slots keep their Japanese
                at = off + size * i
                b = texts.get((at, size))
                if b is None:
                    b = bytes(run.mem.get(at + k, 0) for k in range(size)).split(b'\0')[0]
                mem.update({at + k: c for k, c in enumerate(b + b'\0')})
        words, used = run.emit(mem)
        o = _f(tag, run.start)
        if files[tag][o:o + 4 * len(words)] != clean[tag][o:o + 4 * len(words)]:
            raise ValueError('stackstr %s:%08x: the run was already patched' % (tag, pc0))
        files[tag][o:o + 4 * len(words)] = struct.pack('<%dI' % len(words), *words)
    return len(tl)


if __name__ == '__main__':
    clean, tl = progstr.clean_files(), load_tl()
    seen = {}
    for name, (tag, pc0, pc1, off, size, n) in TABLES.items():
        run = seen.setdefault((tag, pc0), Run(tag, pc0, pc1, clean[tag]))
        print('%s  %s:%08x sp+%#x  %d x %d bytes  (%d slots in the run, %d calls)'
              % (name, tag, pc0, off, n, size, len(run.slots), len(run.calls)))
        for i in range(n):
            jp = run.text(off + size * i, size)
            if jp or (name, i) in tl:
                print('  %s.%d\t%s\t=> %s' % (name, i, jp, tl.get((name, i), '')))
    files = {t: bytearray(b) for t, b in clean.items()}
    print('%d texts' % patch(files, clean))
