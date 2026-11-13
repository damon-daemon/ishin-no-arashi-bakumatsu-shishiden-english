"""Translation files of the event scripts (EVENT/*.I2 entries): show, apply, check, stats; used by build.py.

tl/ev/<ARCHIVE>/<NNN>.txt holds the English (no Japanese) of one script:

    # comment (a line starting with #)
    @<n>        string n of the script (eex.strings order)
    English text, possibly over several physical lines (joined with spaces); \\n = line break.

See text.py for the character set and the wrapping. A string without English takes the English
of a string with the same Japanese and opcode (translation memory, explicit wins); one with
neither keeps its Japanese.

usage:
    tl.py show  SEVAK/000 [from] [to] [--todo]   # Japanese strings
    tl.py show  SEVAK/000 [from] [to] --en       # Japanese + current English (EN* = taken from an identical
                                                 # string of another script by the translation memory)
    tl.py apply SEVAK/000 batch.txt              # validate a batch, merge it into tl/ev/SEVAK/000.txt
    tl.py check [SEVAK/000]                      # validate everything in tl/ (and the sizes)
    tl.py stats
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import eex, text, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL_EV = os.path.join(ROOT, 'tl', 'ev')
# script buffers (CLAUDE.md "Script buffers"): bytes a rebuilt script may have, by archive.
# A (SEVAK, HEVIJ, FEVRE) is enlarged by vwf.patch; B (HEVIS) and C (MEVAP, WEVAR) are the game's.
_A = vwf.BUF_A_END - vwf.BUF_A
MAX = {'SEVAK': _A, 'HEVIJ': _A, 'FEVRE': _A, 'HEVIS': 0x4000, 'MEVAP': 0x2000, 'WEVAR': 0x2000}
_REC = re.compile(r'@(\d+)\s*$')


class Script:
    def __init__(self, name, data=None):
        self.name = name
        self.data = data if data is not None else eex.load(name)
        self.strs = eex.strings(eex.parse(self.data)[1])
        self.jp = [text.decode(st[2][i][1]) for st, i in self.strs]
        self.op = [st[1] for st, i in self.strs]

    def fit(self, n, en):
        """-> ([box bytes], [problems]) for string n."""
        st, i = self.strs[n]
        slot = st[2][0][1] if st[1] == 0x94 else 0
        return text.fit(st[1], en, slot, self.jp[n])

    def build(self, en):
        """{n: English} -> rebuilt script bytes."""
        chunks, secs = eex.parse(self.data)
        extra = {}                              # id(statement) -> following boxes
        for n, (st, i) in enumerate(eex.strings(secs)):
            if n not in en:
                continue
            slot = st[2][0][1] if st[1] == 0x94 else 0
            bx = text.fit(st[1], en[n], slot, self.jp[n])[0]
            st[2][i] = (eex.T_STR, bx[0])
            if len(bx) > 1:
                extra[id(st)] = [[st[0], st[1], st[2][:i] + [(eex.T_STR, b)] + st[2][i + 1:], None]
                                 for b in bx[1:]]
        if extra:
            for blk in eex.blocks(secs):
                k = 0
                while k < len(blk):
                    more = extra.get(id(blk[k]))
                    if more:
                        blk[k + 1:k + 1] = more
                        k += len(more)
                    k += 1
        return eex.build(chunks, secs)


def names():
    return [n for n, _ in eex.files()]


def tl_path(name):
    return os.path.join(TL_EV, name + '.txt')


def parse_tl(path):
    """-> {n: English}"""
    out, key, buf = {}, None, []

    def flush():
        if key is not None:
            out[key] = ' '.join(x.strip() for x in buf if x.strip())
    if not os.path.exists(path):
        return out
    for ln in open(path, encoding='utf-8'):
        ln = ln.rstrip('\n')
        if ln.startswith('#'):
            continue
        m = _REC.match(ln)
        if m:
            flush()
            key, buf = int(m.group(1)), []
            if key in out:
                raise ValueError('%s: @%d twice' % (path, key))
        elif key is not None:
            buf.append(ln)
        elif ln.strip():
            raise ValueError('%s: text before the first @ line: %r' % (path, ln))
    flush()
    return out


def write_tl(name, recs):
    os.makedirs(os.path.dirname(tl_path(name)), exist_ok=True)
    with open(tl_path(name), 'w', encoding='utf-8') as f:
        for n in sorted(recs):
            f.write('@%d\n%s\n\n' % (n, recs[n]))


def load_tls():
    return {n: parse_tl(tl_path(n)) for n in names()}


def memory(scripts, tls):
    """{(op, Japanese): English} from every explicit string."""
    tm = {}
    for name, recs in tls.items():
        sc = scripts[name]
        for n, en in recs.items():
            if n < len(sc.jp):
                tm.setdefault((sc.op[n], sc.jp[n]), en)
    return tm


def english(scripts=None, tls=None):
    """-> ({name: rebuilt script bytes (changed scripts only)}, translated count, errors)"""
    scripts = scripts or {n: Script(n) for n in names()}
    tls = tls if tls is not None else load_tls()
    tm = memory(scripts, tls)
    out, errs, done = {}, [], 0
    if not tm:
        return out, 0, errs
    for name, sc in scripts.items():
        recs = tls.get(name, {})
        errs += ['%s @%d: no such string' % (name, n) for n in recs if n >= len(sc.jp)]
        en = {}
        for n, jp in enumerate(sc.jp):
            e = recs.get(n, tm.get((sc.op[n], jp)))
            if e is None or text.KIND[sc.op[n]] in text.SKIP:
                continue
            es = text.check(e) or sc.fit(n, e)[1]
            if es:
                errs += ['%s @%d: %s' % (name, n, x) for x in es]
                continue
            en[n] = e
        done += len(en)
        if en:
            d = sc.build(en)
            lim = MAX[name.split('/')[0]]
            if lim and len(d) > lim:
                errs.append('%s: %d bytes > %d (script buffer)' % (name, len(d), lim))
            out[name] = d
    return out, done, errs


_NAMES = None


def _who(pid):
    """'122 Chiba Jūtarō': person id + our English name (tl/names/persons.txt)."""
    global _NAMES
    if _NAMES is None:
        import names
        _NAMES = names.load()[0]
    f = _NAMES.get(pid)
    return '%d %s' % (pid, ' '.join(x for x in f[:2] if x and x != '-')) if f else str(pid)


def show(name, a=0, z=None, todo=False, en=False):
    scripts = {n: Script(n) for n in names()} if todo or en else {name: Script(name)}
    tls = load_tls() if todo or en else {name: parse_tl(tl_path(name))}
    sc, recs, tm = scripts[name], tls[name], memory(scripts, tls)
    for n, jp in enumerate(sc.jp):
        if n < a or (z is not None and n > z):
            continue
        if todo and (n in recs or (sc.op[n], jp) in tm or text.KIND[sc.op[n]] in text.SKIP):
            continue
        st, i = sc.strs[n]
        who = ' [%s]' % ' > '.join(_who(v) for t, v in st[2] if t == 1) if sc.op[n] in (0x18, 0x85) else ''
        if sc.op[n] == 0x94:
            who = ' [slot %d]' % st[2][0][1]
        cur = ''
        if en and text.KIND[sc.op[n]] not in text.SKIP:
            e = recs.get(n)
            cur = '    EN: %s\n' % e if e is not None else '    EN*: %s\n' % tm.get((sc.op[n], jp), '')
        print('@%d %s%s\n%s\n%s' % (n, text.KIND.get(sc.op[n], hex(sc.op[n])), who, text.jp_show(jp), cur))


def apply(name, batch):
    sc = Script(name)
    new = parse_tl(batch)
    errs = []
    for n, en in new.items():
        if n >= len(sc.jp):
            errs.append('@%d: no such string in %s' % (n, name))
        else:
            errs += ['@%d: %s' % (n, x) for x in text.check(en) or sc.fit(n, en)[1]]
    if errs:
        sys.exit('\n'.join(errs) + '\n%d errors, nothing written' % len(errs))
    recs = parse_tl(tl_path(name))
    recs.update(new)
    write_tl(name, recs)
    print('%s: %d strings merged (%d in file)' % (name, len(new), len(recs)))


def check(only=None):
    scripts = {n: Script(n) for n in names()}
    tls = load_tls()
    if only:
        tls = {n: (v if n == only else {}) for n, v in tls.items()}
    out, done, errs = english(scripts, tls)
    big = sorted(((len(d), n) for n, d in out.items()), reverse=True)[:3]
    if big:
        print('largest: ' + ', '.join('%s %d' % (n, s) for s, n in big))
    if errs:
        print('\n'.join(errs))
    print('%d strings translated, %d errors' % (done, len(errs)))
    return not errs


def stats():
    scripts = {n: Script(n) for n in names()}
    tls = load_tls()
    tm = memory(scripts, tls)
    tot = done = 0
    for n, sc in scripts.items():
        shown = [k for k in range(len(sc.jp)) if text.KIND[sc.op[k]] not in text.SKIP]
        d = sum(1 for k in shown if k in tls[n] or (sc.op[k], sc.jp[k]) in tm)
        tot, done = tot + len(shown), done + d
        if d:
            print('%s: %4d / %4d' % (n, d, len(sc.jp)))
    print('total: %d / %d strings (%.1f%%)' % (done, tot, 100.0 * done / max(tot, 1)))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == 'show':
        nums = [int(x) for x in a[2:] if not x.startswith('--')]
        show(a[1], *(nums + [0, None])[:2], todo='--todo' in a, en='--en' in a)
    elif a[0] == 'apply':
        apply(a[1], a[2])
    elif a[0] == 'check':
        sys.exit(0 if check(a[1] if len(a) > 1 else None) else 1)
    elif a[0] == 'stats':
        stats()
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
