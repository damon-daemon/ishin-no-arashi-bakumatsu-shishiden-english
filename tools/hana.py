"""Hanafuda (HANA.BIN): fixed-slot name tables and numbers, done outside progstr.

The overlay keeps its card vocabulary in arrays of fixed-size slots, indexed by month (code computes
base + n * slot), so progstr must not move any of them (their tl/progstr lines are "-"):

    0x8016fdcc  12 x 5   flower names (short)      used by "%s (month %s)?" and "I drew %s (month %s)."
    0x80170188  12 x 15  flower names (Card Help)
    0x8017023c  24 x 15  special cards: 12 second animals (only months 8 and 11), then 12 first ones
    0x801703a4  12 x 16  yaku lines of Yaku Help (progstr writes these in place: 15 bytes at most)
    0x80170464  12 x 45  yaku descriptions of Yaku Help (5 used; the survey does not see them)

English flower names do not fit 5 bytes, so the two users of the short table are pointed at the
15-byte one (n * 5 -> n * 15). The data before 0x8016fd04 holds eight unused copies of the short table
and of an opponent name list (no references: static data of a header compiled into several objects).

Numbers: 0x8016a15c(buf, n) writes kanji numerals (months, mon, rounds); it becomes sprintf(buf, "%d", n).
"""
import struct

import progstr

FLOWERS = ['Pine', 'Plum', 'Cherry', 'Wisteria', 'Iris', 'Peony', 'Bush Clover', 'Pampas',
           'Chrysanthemum', 'Maple', 'Willow', 'Paulownia']
SECOND = {7: 'Geese', 10: 'Swallow'}
FIRST = ['Crane', 'Bush Warbler', 'Curtain', 'Cuckoo', 'Bridge', 'Butterflies', 'Boar', 'Full Moon',
         'Sake Cup', 'Deer', 'Michikaze', 'Phoenix']
LONG, CARDS, SLOT = 0x80170188, 0x8017023c, 15
YAKU, YAKU_SLOT = 0x80170464, 45
YAKU_DESC = {2: 'Michikaze and any 3 of the Shikō cards.', 3: 'Any 3 of the Shikō cards.',
             9: '5 Tane cards. +1 mon per extra card.', 10: '5 Tan cards. +1 mon per extra card.',
             11: '10 Kasu cards. +1 mon per extra card.'}
SPRINTF = 0x800b05b0
NUM = 0x8016a15c

# (vaddr, clean word, new word)
SITES = [
    # "%s (month %s)?" and "I drew %s (month %s).": sll v0, s3, 2 / addu v0, v0, s3 / lui a2 / addiu a2, a2, 0xfdcc
    (0x8016af7c, 0x00131080, 0x00131100), (0x8016af80, 0x00531021, 0x00531023), (0x8016af88, 0x24c6fdcc, 0x24c60188),
    (0x8016b0ac, 0x00131080, 0x00131100), (0x8016b0b0, 0x00531021, 0x00531023), (0x8016b0b8, 0x24c6fdcc, 0x24c60188),
    # number -> text: move a2, a1 / lui a1 / j sprintf / addiu a1, a1, lo("%d") / "%d"
    (NUM, 0x27bdffa8, 0x00a03021),
    (NUM + 4, 0xafb00038, 0x3c050000 | (NUM + 16 + 0x8000) >> 16),
    (NUM + 8, 0x00808021, 0x08000000 | (SPRINTF >> 2 & 0x3ffffff)),
    (NUM + 12, 0xafb30044, 0x24a50000 | (NUM + 16) & 0xffff),
    (NUM + 16, 0x00a09821, struct.unpack('<I', b'%d\0\0')[0]),
]


def patch(files):
    """files['HANA'] (bytearray) after progstr.apply."""
    b = files['HANA']
    for va, old, new in SITES:
        o = va - progstr.OVL_BASE
        if struct.unpack_from('<I', b, o)[0] != old:
            raise ValueError('hana %08x: unexpected word' % va)
        struct.pack_into('<I', b, o, new)
    names = [(LONG + SLOT * i, n, SLOT) for i, n in enumerate(FLOWERS)]
    names += [(CARDS + SLOT * i, n, SLOT) for i, n in SECOND.items()]
    names += [(CARDS + SLOT * (12 + i), n, SLOT) for i, n in enumerate(FIRST)]
    names += [(YAKU + YAKU_SLOT * i, n, YAKU_SLOT) for i, n in YAKU_DESC.items()]
    for va, n, size in names:
        e = progstr.encode(n)
        if len(e) >= size:
            raise ValueError('hana: %r is over %d bytes' % (n, size - 1))
        o = va - progstr.OVL_BASE
        b[o:o + size] = e + bytes(size - len(e))
