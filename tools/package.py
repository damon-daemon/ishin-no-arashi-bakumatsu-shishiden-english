"""Package a release: release/<Name>_v<version>.zip with the xdelta patch, a .cue and README.txt.

usage: .venv/bin/python tools/package.py 0.9.0

Run tools/build.py first. The patch turns the clean track 1 into the English track 1;
tracks 2-4 (CD audio) are not changed, so the zip carries a .cue that pairs the patched
track 1 with the player's own tracks 2-4. README.txt is generated from README.md (the
notices, the "What's translated", "Known issues" and "Credits" sections) plus patching
instructions and checksums. No disc data is ever packaged.
"""
import hashlib, os, re, sys, textwrap, zipfile, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLE = 'Ishin no Arashi: Bakumatsu Shishiden - English Translation'
ZIP_NAME = 'Ishin_no_Arashi_Bakumatsu_Shishiden_English'
CLEAN = 'ishin_shishiden_track1.bin'
CLEAN_AUDIO = ['ishin_shishiden_track%d.bin' % t for t in (2, 3, 4)]
BUILT = os.path.join('build', 'ishin_shishiden_en_track1.bin')
PATCH = os.path.join('build', 'ishin_shishiden_en.xdelta')
GAME_CODE = 'SLPM-86144'
# Redump file names of the Japanese disc, and the names the patched disc gets
JP_TRACK1 = 'Ishin no Arashi - Bakumatsu Shishiden (Japan) (Track 1).bin'
JP_AUDIO = ['Ishin no Arashi - Bakumatsu Shishiden (Japan) (Track %d).bin' % t for t in (2, 3, 4)]
# (the version goes in with % version)
EN_TRACK1 = 'Ishin no Arashi - Bakumatsu Shishiden (English v%s) (Track 1).bin'
EN_CUE = 'Ishin no Arashi - Bakumatsu Shishiden (English v%s).cue'


def sums(path):
    """Checksums, read in chunks."""
    md5, sha1, crc, n = hashlib.md5(), hashlib.sha1(), 0, 0
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 24):
            md5.update(chunk); sha1.update(chunk); crc = zlib.crc32(chunk, crc); n += len(chunk)
    return [('Size', '{:,} bytes'.format(n)), ('CRC32', '%08X' % (crc & 0xFFFFFFFF)),
            ('MD5', md5.hexdigest()), ('SHA-1', sha1.hexdigest())]


def section(md, name):
    m = re.search(r'^## %s\n(.*?)(?=^## |\Z)' % re.escape(name), md, re.S | re.M)
    return m.group(1).strip() if m else ''


def plain(text):
    """Markdown -> readable plain text (bold, code, links, quotes)."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    text = re.sub(r'^> ?', '', text, flags=re.M)
    return text


def heading(t):
    return '%s\n%s\n' % (t, '-' * len(t))


def cue(en_track1):
    out = 'FILE "%s" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n' % en_track1
    for t, name in enumerate(JP_AUDIO, 2):
        out += 'FILE "%s" BINARY\n  TRACK %02d AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n' % (name, t)
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit('usage: tools/package.py VERSION   (e.g. 0.9.0)')
    version = sys.argv[1]
    clean, built, patch = (os.path.join(ROOT, p) for p in (CLEAN, BUILT, PATCH))
    audio = [os.path.join(ROOT, p) for p in CLEAN_AUDIO]
    for p in [clean, built, patch] + audio:
        if not os.path.exists(p):
            sys.exit('missing %s (run tools/build.py first)' % p)
    if os.path.getmtime(patch) < os.path.getmtime(built):
        sys.exit('patch is older than the built image; re-run tools/build.py')
    md = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    patch_name = 'ishin_shishiden_en_v%s.xdelta' % version
    en_track1, en_cue = EN_TRACK1 % version, EN_CUE % version
    table = lambda rows: '\n'.join('  %-6s %s' % r for r in rows)

    out = [TITLE, 'Version %s' % version, '=' * max(len(TITLE), 20), '']
    for pat in (r'^> \*\*This is a full machine translation.*?(?=\n\n)', r'^> \*\*This is a beta.*?(?=\n\n)'):
        m = re.search(pat, md, re.S | re.M)
        if m:
            out += [textwrap.fill(' '.join(plain(m.group(0)).split()), 78), '']
    out += [heading("What's translated"), plain(section(md, "What's translated")), '']
    out += [heading('How to patch'),
            'You need your own unmodified image of the Japanese disc (serial %s): four' % GAME_CODE,
            '.bin files (Track 1 to Track 4). Only track 1 is patched.', '',
            '1. Make a copy of your Track 1 .bin file and name the copy exactly:', '',
            '     %s' % en_track1, '',
            '   Keep the original file as it is.', '',
            '2. Open Delta Patcher (https://github.com/marco-calautti/DeltaPatcher).',
            '   Under "Original file" choose the copy, under "XDelta patch" choose',
            '   %s, and click "Apply patch".' % patch_name,
            '   A checksum error means your disc image is not the one the patch was',
            '   made for (compare with the values below).', '',
            '3. Tracks 2, 3 and 4 (CD audio, not changed) must be named exactly:', '',
            '\n'.join('     %s' % n for n in JP_AUDIO), '',
            '4. Put the patched track 1, tracks 2-4 and',
            '   "%s"' % en_cue,
            '   (in this zip) in one folder and open the .cue in your emulator.', '',
            'Command line instead of steps 1 and 2:', '',
            '  xdelta3 -d -s "%s" %s "%s"' % (JP_TRACK1, patch_name, en_track1), '',
            'The original track 1 should match:', '',
            '  %s' % JP_TRACK1, table(sums(clean)), '',
            'The patched track 1 should match:', '', table(sums(built)), '',
            'Audio tracks (size, CRC32):', '',
            '\n'.join('  Track %d  %s, %s' % (t, s[0][1], s[1][1]) for t, s in enumerate(map(sums, audio), 2)), '']
    out += [heading('Known issues'), plain(section(md, 'Known issues')), '']
    out += [heading('Credits'), plain(section(md, 'Credits')), '']
    readme = '\n'.join(out).replace('\n\n\n', '\n\n')

    os.makedirs(os.path.join(ROOT, 'release'), exist_ok=True)
    zpath = os.path.join(ROOT, 'release', '%s_v%s.zip' % (ZIP_NAME, version))
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(patch, patch_name)
        z.writestr(en_cue, cue(en_track1).replace('\n', '\r\n'))
        z.writestr('README.txt', readme.replace('\n', '\r\n'))
    print('%s (%s, %s, README.txt)' % (zpath, patch_name, en_cue))


if __name__ == '__main__':
    main()
