"""Check your own disc image and create the working folder extract/.

extract/ holds the files of the disc and, under extract/ev/, the unpacked entries of the event
archives (EVENT/*.I2, CG/SCREEN.I2), so it is generated on each machine and never distributed.
Run this once after cloning, then tools/build.py.

usage: python3 tools/setup.py [track1.bin]
"""
import hashlib, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import iso, ls12

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACT = os.path.join(ROOT, 'extract')
CLEAN = os.path.join(ROOT, 'ishin_shishiden_track1.bin')
CLEAN_SHA1 = '3b6c5a49976b815523c039f3ece63cbdb99e11df'
# CD audio tracks 2-4: copied next to the rebuilt track 1, never patched
AUDIO = [os.path.join(ROOT, 'ishin_shishiden_track%d.bin' % t) for t in (2, 3, 4)]
AUDIO_SHA1 = ['27f677c9e3d5bcac022347801e403cc7df5a6f84', 'e68b0426c12c86b1555cb9333701f1aa1fd8fcdc',
              '7c8508996d34d2a39fd75a8fab58e2c9b766b09b']
# Ls12 archives unpacked to extract/ev/<name>/NNN.bin
ARCHIVES = ['EVENT/%s.I2' % n for n in ('FEVRE', 'HEVIJ', 'HEVIS', 'MEVAP', 'SEVAK', 'WEVAR')] + ['CG/SCREEN.I2']


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def check_clean(path, want=CLEAN_SHA1):
    digest = sha1(path)
    if digest != want:
        sys.exit('%s: SHA-1 %s does not match the clean dump (%s)' % (path, digest, want))


def extract(disc):
    n = 0
    for name, lba, size in disc.walk():
        if name.endswith(('.DA', '.STR')):
            continue                     # CD-DA entries, Form 2 movies
        p = os.path.join(EXTRACT, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(disc.read(lba, size))
        n += 1
    return n


def unpack_archives():
    n = 0
    for arc in ARCHIVES:
        d = open(os.path.join(EXTRACT, arc), 'rb').read()
        out = os.path.join(EXTRACT, 'ev', os.path.basename(arc)[:-3])
        os.makedirs(out, exist_ok=True)
        for i, e in enumerate(ls12.entries(d)):
            with open(os.path.join(out, '%03d.bin' % i), 'wb') as f:
                f.write(ls12.unpack(d, *e))
            n += 1
    return n


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else CLEAN
    check_clean(path)
    if path == CLEAN:
        for p, want in zip(AUDIO, AUDIO_SHA1):
            check_clean(p, want)
    print('extract/: %d files' % extract(iso.Disc(path)))
    print('extract/ev/: %d archive entries' % unpack_archives())
    print('ready; now run tools/build.py')


if __name__ == '__main__':
    main()
