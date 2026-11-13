"""EEX event scripts (the unpacked entries of EVENT/*.I2): parse, rebuild, list strings.

The same family as Oda Nobunaga Den / Mouri Motonari's EEX, in a later revision. Reversed from the
loader 0x800470c4, block runner 0x80047280, entry picker 0x80046e88 and the opcode dispatcher
0x80056a30 (jump table 0x8001d694, 160 opcodes) of SLPM_861.44; tools/dev/eexops.py lists the
operand tags each handler reads.

  'EEX\\0' 01 02 | chunks {u16 type, u16 len, data} ended by type 0 (len 0)
      chunk type 1 = source file name; its presence turns on the line-number prefixes (LINE below)
  u32 section offsets (absolute; count = (first offset - table position) / 4)
  section = u16 n_entries, then n x entry
  entry   = LINE, u16 len, condition statements (no LINE) ended by opcode 0, u16 body_len, block
  block   = statements {LINE, u16 opcode, operands}; the last one is LINE 0xffff, opcode 0
            opcode 1 ("if") is followed by one condition statement (no LINE), u16 len, block;
            the condition opcode 2 = "else" (true when the previous if at this level was false)
  LINE    = u16 source line counter (kept as read; the interpreter skips it)
  operand = u16 tag + value: tag 0x36 -> u32, tag 0x37 -> NUL-terminated SJIS string, other -> u16.
            A list operand ('L' in OPS) is tag, u16 count, count x u16.
            The handler fixes how many operands follow (OPS); several accept alternative tags in one
            position, so tags are stored as read. Opcode 4 takes two operands when the first tag is 1.
The only offsets are the section table and the u16 lengths, so strings can change length freely:
build() recomputes them (an entry or an if-block must stay under 64 KB).

  python3 tools/eex.py check            parse + rebuild every script byte-exact
  python3 tools/eex.py dump SEVAK/001   print statements
  python3 tools/eex.py strings SEVAK/001
  python3 tools/eex.py stats            string counts and bytes per opcode
"""
import glob, os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'extract', 'ev')
ARCHIVES = ('FEVRE', 'HEVIJ', 'HEVIS', 'MEVAP', 'SEVAK', 'WEVAR')

T_U32, T_STR = 0x36, 0x37
# opcode -> number of operands, or a string of 'o' (operand) / 'L' (list). Missing = not implemented
# by the game (dispatcher default). Checked against all 120 scripts with the line counters.
OPS = {
    0x00: 0, 0x01: 0, 0x02: 0, 0x03: 0, 0x04: 1, 0x05: 4, 0x06: 2, 0x07: 1, 0x08: 4, 0x09: 1,
    0x0a: 'LL', 0x0b: 3, 0x0c: 2, 0x0d: 1, 0x0e: 0, 0x0f: 'oL', 0x10: 3, 0x11: 2, 0x12: 2, 0x14: 1,
    0x15: 2, 0x18: 3, 0x19: 3, 0x1a: 1, 0x1b: 1, 0x1c: 4, 0x1d: 4, 0x1e: 1, 0x1f: 1, 0x20: 1,
    0x21: 3, 0x22: 2, 0x23: 2, 0x24: 1, 0x26: 3, 0x27: 2, 0x28: 2, 0x29: 1, 0x2a: 4, 0x2b: 4,
    0x2c: 1, 0x2d: 2, 0x2e: 1, 0x2f: 2, 0x30: 2, 0x31: 2, 0x32: 'LL', 0x33: 2, 0x34: 1, 0x35: 1,
    0x36: 3, 0x37: 3, 0x38: 3, 0x39: 2, 0x3a: 2, 0x3b: 1, 0x3c: 0, 0x3d: 0, 0x3e: 1, 0x3f: 0,
    0x40: 1, 0x41: 1, 0x42: 2, 0x43: 2, 0x44: 2, 0x45: 1, 0x46: 1, 0x47: 2, 0x48: 1, 0x49: 2,
    0x4a: 3, 0x4b: 2, 0x4c: 2, 0x4d: 3, 0x4e: 3, 0x4f: 2, 0x50: 0, 0x51: 3, 0x52: 3, 0x53: 4,
    0x54: 1, 0x55: 2, 0x56: 3, 0x57: 3, 0x58: 2, 0x59: 1, 0x5a: 1, 0x5b: 1, 0x5c: 5, 0x5d: 3,
    0x5e: 2, 0x5f: 2, 0x60: 3, 0x61: 1, 0x62: 1, 0x63: 0, 0x64: 2, 0x66: 2, 0x69: 4, 0x6a: 4,
    0x6c: 4, 0x6d: 3, 0x6e: 3, 0x6f: 4, 0x70: 4, 0x71: 2, 0x72: 2, 0x73: 2, 0x74: 2, 0x75: 2,
    0x76: 0, 0x77: 2, 0x78: 2, 0x79: 4, 0x7a: 1, 0x7b: 2, 0x7c: 6, 0x7d: 2, 0x7e: 3, 0x7f: 1,
    0x83: 1, 0x84: 1, 0x85: 4, 0x86: 1, 0x87: 1, 0x88: 2, 0x89: 1, 0x8a: 3, 0x8b: 0, 0x8c: 0,
    0x8d: 0, 0x8e: 1, 0x8f: 1, 0x90: 0, 0x91: 3, 0x92: 0, 0x93: 0, 0x94: 2, 0x95: 3, 0x96: 0,
    0x97: 1, 0x98: 1, 0x99: 1, 0x9a: 2, 0x9b: 1, 0x9c: 0, 0x9d: 0, 0x9e: 1, 0x9f: 2,
}
# Not in the 120 scripts (count from the handler scan only): 06 0c 0d 0e 10 23 29 41 5f 60 61 63
# 69 71 76 86 8b 90 92 97 9d.
OPS = {op: ('o' * c if isinstance(c, int) else c) for op, c in OPS.items()}
END, IF, ELSE = 0, 1, 2      # ELSE only as the condition of an IF


class EEXError(Exception):
    pass


class Reader:
    def __init__(self, d, p, lines):
        self.d, self.p, self.lines = d, p, lines

    def u16(self):
        v = struct.unpack_from('<H', self.d, self.p)[0]
        self.p += 2
        return v

    def line(self):
        return self.u16() if self.lines else None


def _stmt(r, line, cond=False):
    """[line, op, args, sub]; args = [(tag, int | bytes | list)]; sub = (cond stmt, block) for IF."""
    at = r.p
    op = r.u16()
    if op not in OPS:
        raise EEXError('bad opcode %#x at %#x' % (op, at))
    spec = OPS[op]
    if op == 4 and struct.unpack_from('<H', r.d, r.p)[0] == 1:
        spec = 'oo'
    args = []
    for kind in spec:
        tag = r.u16()
        if tag > 0x3f:
            raise EEXError('op %#x at %#x: bad operand tag %#x' % (op, at, tag))
        if kind == 'L':
            v = [r.u16() for _ in range(r.u16())]
        elif tag == T_U32:
            v = struct.unpack_from('<I', r.d, r.p)[0]
            r.p += 4
        elif tag == T_STR:
            q = r.d.index(b'\0', r.p)
            v = r.d[r.p:q]
            r.p = q + 1
        else:
            v = r.u16()
        args.append((tag, v))
    sub = None
    if op == IF and not cond:
        c = _stmt(r, None, True)
        ln = r.u16()
        end = r.p + ln
        sub = (c, _block(r, end))
        if r.p != end:
            raise EEXError('block at %#x: length %#x, parsed to %#x' % (at, ln, r.p))
    return [line, op, args, sub]


def _block(r, end):
    out = []
    while True:
        if r.p >= end:
            raise EEXError('block overruns %#x' % end)
        at = r.p
        st = _stmt(r, r.line())
        if st[1] == END:
            if r.lines and st[0] != 0xffff:
                raise EEXError('block end at %#x: line %#x' % (at, st[0]))
            return out
        out.append(st)


def parse(d):
    """-> (chunks [(type, data)], sections [[(line, cond stmts, body block)]])."""
    if d[:6] != b'EEX\0\x01\x02':
        raise EEXError('unexpected header')
    p, chunks = 6, []
    while True:
        t, ln = struct.unpack_from('<HH', d, p)
        p += 4
        if t == 0:
            if ln:
                raise EEXError('end chunk with data')
            break
        chunks.append((t, d[p:p + ln]))
        p += ln
    lines = any(t == 1 for t, _ in chunks)
    first = struct.unpack_from('<I', d, p)[0]
    n = (first - p) // 4
    offs = list(struct.unpack_from('<%dI' % n, d, p)) + [len(d)]
    secs = []
    for s in range(n):
        r = Reader(d, offs[s], lines)
        ents = []
        for _ in range(r.u16()):
            line = r.line()
            ln = r.u16()
            end = r.p + ln
            cond = []
            while True:
                st = _stmt(r, None, True)
                if st[1] == END:
                    break
                cond.append(st)
            bl = r.u16()
            if r.p + bl != end:
                raise EEXError('entry body length mismatch at %#x' % r.p)
            body = _block(r, end)
            if r.p != end:
                raise EEXError('entry length mismatch at %#x' % r.p)
            ents.append((line, cond, body))
        if r.p != offs[s + 1]:
            raise EEXError('section %d ends at %#x, next at %#x' % (s, r.p, offs[s + 1]))
        secs.append(ents)
    return chunks, secs


def _bstmt(st, out, lines):
    line, op, args, sub = st
    if lines and line is not None:
        out += struct.pack('<H', line)
    out += struct.pack('<H', op)
    for tag, v in args:
        out += struct.pack('<H', tag)
        if isinstance(v, list):
            out += struct.pack('<%dH' % (len(v) + 1), len(v), *v)
        elif tag == T_U32:
            out += struct.pack('<I', v)
        elif tag == T_STR:
            out += v + b'\0'
        else:
            out += struct.pack('<H', v)
    if sub:
        cond, blk = sub
        _bstmt(cond, out, lines)
        b = _bblock(blk, lines)
        if len(b) > 0xffff:
            raise EEXError('if/else block too long (%d bytes)' % len(b))
        out += struct.pack('<H', len(b)) + b


def _bblock(blk, lines):
    out = bytearray()
    for st in blk:
        _bstmt(st, out, lines)
    out += b'\xff\xff\0\0' if lines else b'\0\0'
    return bytes(out)


def build(chunks, secs):
    lines = any(t == 1 for t, _ in chunks)
    hdr = bytearray(b'EEX\0\x01\x02')
    for t, data in chunks:
        hdr += struct.pack('<HH', t, len(data)) + data
    hdr += b'\0\0\0\0'
    body = []
    for ents in secs:
        out = bytearray(struct.pack('<H', len(ents)))
        for line, cond, blk in ents:
            c = bytearray()
            for st in cond:
                _bstmt(st, c, lines)
            b = _bblock(blk, lines)
            if len(b) > 0xffff:
                raise EEXError('entry body too long (%d bytes)' % len(b))
            e = bytes(c) + b'\0\0' + struct.pack('<H', len(b)) + b
            if len(e) > 0xffff:
                raise EEXError('entry too long (%d bytes)' % len(e))
            if lines:
                out += struct.pack('<H', line)
            out += struct.pack('<H', len(e)) + e
        body.append(bytes(out))
    off = len(hdr) + 4 * len(secs)
    for b in body:
        hdr += struct.pack('<I', off)
        off += len(b)
    return bytes(hdr) + b''.join(body)


def walk(secs):
    """Yield every statement in file order (conditions and nested blocks included)."""
    def blk(b):
        for st in b:
            yield st
            if st[3]:
                yield st[3][0]
                yield from blk(st[3][1])
    for ents in secs:
        for _, cond, body in ents:
            yield from cond
            yield from blk(body)


def blocks(secs):
    """Yield every statement list (entry bodies and nested if-blocks), for inserting statements."""
    def blk(b):
        yield b
        for st in b:
            if st[3]:
                yield from blk(st[3][1])
    for ents in secs:
        for _, _, body in ents:
            yield from blk(body)


def strings(secs):
    """[(statement, arg index)] for every string operand, in file order (index = string number)."""
    return [(st, i) for st in walk(secs) for i, (t, v) in enumerate(st[2]) if t == T_STR]


def files():
    """Unpacked archive entries that are EEX scripts: [(name 'SEVAK/001', path)]."""
    out = []
    for a in ARCHIVES:
        for f in sorted(glob.glob(os.path.join(SRC, a, '*.bin'))):
            with open(f, 'rb') as h:
                if h.read(4) == b'EEX\0':
                    out.append(('%s/%s' % (a, os.path.basename(f)[:-4]), f))
    return out


def load(name):
    return open(os.path.join(SRC, name + '.bin'), 'rb').read()


def _text(v):
    return v.decode('cp932', 'replace').replace('\n', '\\n')


def main(argv):
    cmd = argv[0] if argv else 'check'
    if cmd == 'check':
        n = bad = 0
        for name, f in files():
            d = open(f, 'rb').read()
            try:
                if build(*parse(d)) != d:
                    print('MISMATCH', name)
                    bad += 1
            except EEXError as e:
                print('ERROR', name, e)
                bad += 1
            n += 1
        print('%d scripts checked, %d bad' % (n, bad))
        return 1 if bad else 0
    if cmd == 'dump':
        def fmt(st):
            a = ' '.join('%x:%s' % (t, '"%s"' % _text(v) if t == T_STR else v if isinstance(v, list)
                         else hex(v)) for t, v in st[2])
            return '%02x %s' % (st[1], a)

        def show(b, ind):
            for st in b:
                print('%s%4s %s' % (ind, '' if st[0] is None else st[0], fmt(st)))
                if st[3]:
                    print('%s     ? %s' % (ind, fmt(st[3][0])))
                    show(st[3][1], ind + '    ')
        chunks, secs = parse(load(argv[1]))
        for t, data in chunks:
            print('chunk %d: %s' % (t, _text(data.rstrip(b'\0'))))
        for s, ents in enumerate(secs):
            for e, (line, cond, body) in enumerate(ents):
                print('== section %d entry %d (line %s)' % (s, e, line))
                for st in cond:
                    print('  when %s' % fmt(st))
                show(body, '  ')
    elif cmd == 'strings':
        for i, (st, k) in enumerate(strings(parse(load(argv[1]))[1])):
            print('%5d %02x %s' % (i, st[1], _text(st[2][k][1])))
    elif cmd == 'stats':
        cnt, size, uniq = {}, {}, {}
        for name, f in files():
            for st, k in strings(parse(open(f, 'rb').read())[1]):
                op, v = st[1], st[2][k][1]
                cnt[op] = cnt.get(op, 0) + 1
                size[op] = size.get(op, 0) + len(v)
                uniq.setdefault(op, set()).add(v)
        for op in sorted(cnt):
            print('op %02x: %6d strings, %8d bytes, %6d unique (%d bytes)' % (
                op, cnt[op], size[op], len(uniq[op]), sum(map(len, uniq[op]))))
        print('total : %6d strings, %8d bytes' % (sum(cnt.values()), sum(size.values())))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
