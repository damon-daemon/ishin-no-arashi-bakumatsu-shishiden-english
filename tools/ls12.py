"""Koei 'Ls12' archives (EVENT/*.I2, CG/SCREEN.I2): first try = the PC 'LS11' layout.

16-byte magic, 256-byte dictionary, entries of 3 big-endian u32 (packed size, size, offset)
ended by a zero word, then the packed data. Bit stream, MSB first: a code is read as a
unary-length prefix + the same number of extra bits; code < 256 = dictionary byte, else
offset = code - 256 followed by a second code = length - 3 (copy from the output).

The game's reader (SLPM_861.44 0x8005be38) copies an entry as it is when packed size == size,
so rebuild() stores changed entries uncompressed (no packer needed).

usage: python3 tools/ls12.py list|extract file [outdir]
       python3 tools/ls12.py test file      (rebuild checks: unchanged = identical, all stored = same contents)
"""
import os, struct, sys

def entries(d):
    out, p = [], 0x110
    while True:
        psize, size, off = struct.unpack_from('>III', d, p)
        if psize == 0:
            break
        out.append((psize, size, off))
        p += 12
    return out

class Bits:
    def __init__(self, d, pos):
        self.d, self.pos, self.bit = d, pos, 0
    def get(self):
        b = (self.d[self.pos] >> (7 - self.bit)) & 1
        self.bit += 1
        if self.bit == 8:
            self.bit, self.pos = 0, self.pos + 1
        return b
    def code(self):
        n, a = 0, 0
        while True:
            b = self.get()
            a = a * 2 + b
            n += 1
            if not b:
                break
        v = 0
        for _ in range(n):
            v = v * 2 + self.get()
        return a + v

def unpack(d, psize, size, off):
    if psize == size:
        return d[off:off + size]
    dic, bits, out = d[0x10:0x110], Bits(d, off), bytearray()
    while len(out) < size:
        c = bits.code()
        if c < 256:
            out.append(dic[c])
        else:
            o, n = c - 256, bits.code() + 3
            for _ in range(n):
                out.append(out[-o])
    return bytes(out[:size])

def rebuild(d, changed):
    """New archive with the entries in changed {index: bytes} stored uncompressed (each starting on a
    sector boundary); the others keep their packed bytes. With nothing changed the result is the original file."""
    ents = entries(d)
    start = min(off for _, _, off in ents)
    head, body, pos = bytearray(d[:0x110]), bytearray(), start
    for i, (psize, size, off) in enumerate(ents):
        if i in changed:
            blob = bytes(changed[i])
            if not blob:
                raise ValueError('entry %d: empty' % i)
            psize = size = len(blob)
            # A stored entry must start on a sector boundary: the game's reader (0x8005bf98) copies the
            # part up to the next sector through its buffer and then reads whole sectors straight to
            # the destination, and that CD read rounds an odd destination address down (seen: SEVAK/001
            # lost the byte before the boundary, every later byte shifted, the interpreter hung).
            pad = -pos % 2048
            body += bytes(pad)
            pos += pad
        else:
            blob = d[off:off + psize]
        head += struct.pack('>III', psize, size, pos)
        body += blob
        pos += len(blob)
    head += d[0x110 + 12 * len(ents):start]            # the zero word ending the table
    end = max(off + psize for psize, _, off in ents)
    return bytes(head) + bytes(body) + d[end:]


def unpack_all(d):
    return [unpack(d, *e) for e in entries(d)]


if __name__ == '__main__':
    d = open(sys.argv[2], 'rb').read()
    if sys.argv[1] == 'test':
        orig = unpack_all(d)
        same = rebuild(d, {}) == d
        stored = rebuild(d, dict(enumerate(orig)))
        print('%s: %d entries, unchanged rebuild %s, stored rebuild %s (%d -> %d bytes)' % (
            sys.argv[2], len(orig), 'identical' if same else 'DIFFERS',
            'same contents' if unpack_all(stored) == orig else 'DIFFERS', len(d), len(stored)))
        sys.exit(0)
    for i, (psize, size, off) in enumerate(entries(d)):
        print('%3d packed %7d size %7d at %7x' % (i, psize, size, off))
        if sys.argv[1] == 'extract':
            os.makedirs(sys.argv[3], exist_ok=True)
            open(os.path.join(sys.argv[3], '%03d.bin' % i), 'wb').write(unpack(d, psize, size, off))
