"""PS1 RAM of our running headless DuckStation (shared memory export, live, no pause).

  ram.py read ADDR LEN      hex dump
  ram.py dump out.bin       whole 2 MB
  ram.py str ADDR           Shift-JIS string at ADDR
  ram.py find HEX|sjis:TEXT every address holding the bytes
The shared memory file is the one of our own process (xkeys.emus), not "the newest one".
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xkeys


def ram():
    for pid, _ in xkeys.emus():
        path = '/dev/shm/duckstation_%d' % pid
        if os.path.exists(path):
            with open(path, 'rb') as f:
                return f.read(0x200000)
    sys.exit('no /dev/shm/duckstation_<pid> of our emulator (ExportSharedMemory off, or the game has not started)')


def off(addr):
    return addr & 0x1fffff


if __name__ == '__main__':
    a = sys.argv[1:]
    m = ram()
    if a[0] == 'read':
        p, n = off(int(a[1], 0)), int(a[2], 0)
        for i in range(0, n, 16):
            row = m[p + i:p + min(i + 16, n)]
            print('%08x  %-48s %s' % (0x80000000 + p + i, row.hex(' '),
                                      ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)))
    elif a[0] == 'dump':
        open(a[1], 'wb').write(m)
    elif a[0] == 'str':
        p = off(int(a[1], 0))
        print(m[p:m.index(b'\0', p)].decode('cp932', 'replace'))
    elif a[0] == 'find':
        pat = a[1][5:].encode('cp932') if a[1].startswith('sjis:') else bytes.fromhex(a[1])
        p = m.find(pat)
        while p >= 0:
            print('%08x' % (0x80000000 + p))
            p = m.find(pat, p + 1)
