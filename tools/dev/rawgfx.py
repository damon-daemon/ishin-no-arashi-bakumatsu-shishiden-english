"""Raw graphic viewer for the headerless .I2 containers (dev tool, needs pillow).

Most pieces are read by sector with 0x8009f47c(name, buf, sector, count): a 16-colour palette
(32 bytes) followed by 4bpp pixels, loaded with 0x800b6bbc (palette -> VRAM) and 0x800b6a70
(pixels, mode, 0, x, y, w, h).

usage: .venv/bin/python tools/dev/rawgfx.py file sector w h out.png [bpp=4] [pal=sector start] [pix=pal+32|+512] [scale]
       .venv/bin/python tools/dev/rawgfx.py strip file w out.png [first sector] [sectors]   (4bpp grey overview)
"""
import struct, sys
from PIL import Image

def rgb(c):
    return ((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3)

def decode(d, pal, pix, w, h, bpp=4):
    n = 16 if bpp == 4 else 256
    cols = [rgb(x) for x in struct.unpack_from('<%dH' % n, d, pal)]
    im = Image.new('RGB', (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            if bpp == 4:
                b = d[pix + (y * w + x) // 2] if pix + (y * w + x) // 2 < len(d) else 0
                v = (b >> 4) if x & 1 else b & 15
            else:
                v = d[pix + y * w + x] if pix + y * w + x < len(d) else 0
            px[x, y] = cols[v]
    return im

def strip(d, w, first, count):
    d = d[first * 2048:(first + count) * 2048]
    h = len(d) * 2 // w
    im = Image.new('L', (w, h))
    px = im.load()
    for i in range(w * h):
        b = d[i // 2]
        px[i % w, i // w] = ((b >> 4) if i & 1 else b & 15) * 17
    return im

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'strip':
        d = open(a[1], 'rb').read()
        first = int(a[4], 0) if len(a) > 4 else 0
        count = int(a[5], 0) if len(a) > 5 else len(d) // 2048 - first
        strip(d, int(a[2], 0), first, count).save(a[3])
    else:
        d = open(a[0], 'rb').read()
        sec, w, h = (int(x, 0) for x in a[1:4])
        bpp = int(a[5]) if len(a) > 5 else 4
        pal = int(a[6], 0) if len(a) > 6 else sec * 2048
        pix = int(a[7], 0) if len(a) > 7 else pal + (32 if bpp == 4 else 512)
        s = int(a[8]) if len(a) > 8 else 2
        im = decode(d, pal, pix, w, h, bpp)
        im.resize((w * s, h * s), Image.NEAREST).save(a[4])
