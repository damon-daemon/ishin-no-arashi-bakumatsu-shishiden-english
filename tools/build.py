"""Build the patched disc image from the clean one and tl/.

Output: build/ishin_shishiden_en_track1.bin, copies of the audio tracks 2-4 and a .cue next to
it, and build/ishin_shishiden_en.xdelta (track 1 only). With nothing to insert the image is
identical to the clean one (same SHA-1).

usage: python3 tools/build.py [--stored] [clean track1.bin] [out track1.bin]
  --stored   test build: every event script goes back uncompressed (stored archive entries),
             contents unchanged; checks that the game reads stored entries and moved files
"""
import os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
import eex, facetitle, gfx, grid, hana, iso, joins, ls12, nameentry, names, progstr, setup, stackstr, tl, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'build', 'ishin_shishiden_en_track1.bin')
PATCH = 'ishin_shishiden_en.xdelta'
FIXED = (iso.EXE_NAME, 'SYSTEM.CNF', 'LICENSEJ.DAT')     # must keep their place
EVENTS = ['EVENT/%s.I2' % n for n in eex.ARCHIVES]


def event_files(disc, recs, stored=False):
    """{iso path: archive bytes} for the event archives that change."""
    out = {}
    en, done, errs = tl.english()
    if errs:
        sys.exit('\n'.join(errs) + '\n%d errors in tl/' % len(errs))
    if done:
        print('%d strings in English, %d scripts changed' % (done, len(en)))
    for arc in EVENTS:
        d = disc.file(arc, recs)
        changed = {}
        for i, e in enumerate(ls12.entries(d)):
            raw = ls12.unpack(d, *e)
            if raw[:4] != b'EEX\0':
                continue
            name = '%s/%03d' % (os.path.basename(arc)[:-3], i)
            new = en.get(name) or eex.build(*eex.parse(raw))
            if new != raw or (stored and e[0] != e[1]):
                changed[i] = new
        if changed:
            out[arc] = ls12.rebuild(d, changed)
    return out


def build_files(disc, recs, stored=False):
    files = event_files(disc, recs, stored)
    if files and not stored:
        # English text needs our font and the printer hook (vwf.py)
        clean = progstr.disc_files(disc, recs)
        prog = {t: bytearray(b) for t, b in clean.items()}
        prog['PROG'] = bytearray(names.patch(vwf.patch(clean['PROG'])))
        progstr.layout(prog)
        grid.patch(prog)
        vwf.plates(prog['SCOM'])                      # fencing name plates: centred by pixel width
        n, moved, pool = progstr.apply(prog, clean, progstr.resident(clean['PROG']))       # program + overlay strings
        print('progstr: %d strings (%d moved, free %s)' % (n, moved, pool.room().get('PROG')))
        print('face titles: %d short forms' % facetitle.patch(prog, pool))   # debate card face (one line)
        joins.patch(prog, pool)                       # separator-before-item lists (academy subjects)
        hana.patch(prog)                              # hanafuda tables and numbers
        print('stackstr: %d texts' % stackstr.patch(prog, clean))    # texts built by instructions
        vwf.centres(prog)                             # other strlen-centred labels of the overlays (after stackstr)
        nameentry.patch(prog)                         # English name entry (own character)
        gfx.patch(prog['PROG'], disc.file('CG/WINFRAME.I2', recs))                       # era names of the date bar: own widths
        prog['INIT'] = bytearray(gfx.tiles(bytes(prog['INIT'])))     # title tiles
        files['CG/WINFRAME.I2'] = gfx.winframe(disc.file('CG/WINFRAME.I2', recs))
        files['INFOCOM/GRAPH.I2'] = gfx.graph(disc.file('INFOCOM/GRAPH.I2', recs))  # ideology chart labels
        files['CG/INIT.I2'] = gfx.cards(disc.file('CG/INIT.I2', recs))      # protagonist name plates
        files['CG/RENDA.I2'] = gfx.renda(disc.file('CG/RENDA.I2', recs))    # mash contest scroll
        files['CG/SELECTOR.I2'] = gfx.selector(disc.file('CG/SELECTOR.I2', recs), prog['COM'])  # town map districts
        files['CG/SCOMBAT.I2'] = gfx.scombat(disc.file('CG/SCOMBAT.I2', recs), prog['SCOM'])  # fencing banners, score labels
        files['CG/SETTOKU.I2'] = gfx.settoku(disc.file('CG/SETTOKU.I2', recs))  # debate result panel, tags
        files['CG/HANAPS.I2'] = gfx.hanaps(disc.file('CG/HANAPS.I2', recs))    # hanafuda dealer marker
        files['CG/HEXADD.I2'] = gfx.hexadd(disc.file('CG/HEXADD.I2', recs))    # battle field marks
        files['INFOCOM/CHOTIN.I2'] = gfx.chotin(disc.file('INFOCOM/CHOTIN.I2', recs))  # festival lanterns
        files['CG/MAPPOINT.I2'] = gfx.mappoint(disc.file('CG/MAPPOINT.I2', recs))  # dojo name boards
        files[iso.EXE_NAME] = bytes(prog['PROG'])
        files.update((progstr.ovl_name(t), bytes(b)) for t, b in prog.items() if t != 'PROG' and b != clean[t])
        files['CG/KANA.FNT'] = vwf.kana_font(disc.file('CG/KANA.FNT', recs))
    return files


def write(clean, out, files):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    moved = iso.write_image(clean, out, files)
    print('rebuilt %s%s' % (out, ' (moved: %s)' % ', '.join(moved) if moved else ''))
    if set(moved) & set(FIXED):
        sys.exit('%s moved on the disc' % ', '.join(set(moved) & set(FIXED)))
    iso.verify(out, files)
    audio = []
    for t, src in enumerate(setup.AUDIO, 2):
        dst = out.replace('_track1.bin', '_track%d.bin' % t)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
        audio.append(dst)
    iso.write_cue(out.replace('_track1.bin', '.cue'), out, audio)
    patch = os.path.join(os.path.dirname(out), PATCH)
    try:
        subprocess.run(['xdelta3', '-e', '-f', '-9', '-S', 'djw', '-B', str(1 << 28), '-s', clean, out, patch], check=True)
        print('patch %s (%d bytes)' % (patch, os.path.getsize(patch)))
    except FileNotFoundError:
        print('xdelta3 not installed; skipped patch')
    return moved


def main():
    args = sys.argv[1:]
    stored = '--stored' in args
    args = [a for a in args if a != '--stored']
    clean = args[0] if args else setup.CLEAN
    out = args[1] if len(args) > 1 else OUT
    disc = iso.Disc(clean)
    files = build_files(disc, disc.records(), stored)
    write(clean, out, files)
    if not files:
        same = setup.sha1(out) == setup.CLEAN_SHA1
        print('identity build: SHA-1 %s the clean image' % ('matches' if same else 'DIFFERS from'))


if __name__ == '__main__':
    main()
