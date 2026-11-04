"""An uncompressed GW5AT-60B .fs in memory: its bits as a numpy matrix, edited with its checksums kept right."""
import numpy as np

from apycula import bitmatrix
from apycula.bslib import bytearr, make_crc16_arc

from gw5a_common import db, tilemap

PAD = 2
calc = make_crc16_arc()

OFF = {}        # (row, col) -> where the tile sits in the matrix: y, x, width, height
_y = 0
for _r in range(db.rows):
    _x = 0
    for _c in range(db.cols):
        _w, _h, _ = tilemap(_r, _c)
        OFF[(_r, _c)] = (_y, _x, _w, _h)
        _x += _w
    _y += _h
_ROWY = np.array([OFF[(r, 0)][0] for r in range(db.rows)])
_COLX = [np.array([OFF[(r, c)][1] for c in range(db.cols)]) for r in range(db.rows)]


def _bytes(s):
    return bytearray(np.packbits(np.frombuffer(s.encode(), np.uint8) - 48).tobytes())


class Fs:
    def __init__(self, fn, check=True):
        lines = open(fn).read().split('\n')
        idx = [k for k, l in enumerate(lines) if l and not l.startswith('//')]
        for n, k in enumerate(idx):
            ba = bytearr(lines[k])
            if ba[0] == 0x3b:
                frames = int.from_bytes(ba[2:], 'big')
                first = n + 1
                break
        self.lines = lines
        self.hdr = [bytearr(lines[k]) for k in idx[:first]]
        self.fk = idx[first:first + frames]
        self.ftr_k = idx[first + frames:]
        F = np.array([np.frombuffer(lines[k].strip().encode(), np.uint8) for k in self.fk]) - 48
        self.L = F.shape[1] - PAD - 64
        self.bm = np.ascontiguousarray(F[:, PAD:PAD + self.L][:, ::-1].T)
        if check:
            self._crc_model()

    def _crc_model(self):
        """Frame 0's CRC covers the header after the preamble (found by search), less d2 lines."""
        f0 = _bytes(self.lines[self.fk[0]].strip())
        want = f0[-8] | (f0[-7] << 8)
        skip = next(s for s in range(0, 8)
                    if calc(bytearray(b''.join(bytes(b) for b in self.hdr[s:] if b[0] != 0xd2)) + f0[:-8]) == want)
        self.hdrbytes = bytearray(b''.join(bytes(b) for b in self.hdr[skip:] if b[0] != 0xd2))
        bad = [n for n in range(len(self.fk)) if self._crc_line(n, self.lines[self.fk[n]].strip()) != self.lines[self.fk[n]].strip()]
        assert not bad, f'frame CRC model fails at {bad[:5]}'

    def _crc_line(self, n, s):
        ba = _bytes(s)
        c = calc((self.hdrbytes if n == 0 else bytearray(b'\xff' * 6)) + ba[:-8])
        return s[:-64] + f'{c & 0xff:08b}{c >> 8:08b}' + s[-48:]

    def on(self):
        """Every tile's set bits, {(row, col): {(i, j), ...}}."""
        return bits_by_tile(self.bm)

    def tile(self, rc):
        y, x, w, h = OFF[rc]
        return self.bm[y:y + h, x:x + w]

    def copy(self):
        n = object.__new__(Fs)
        n.__dict__.update(self.__dict__)
        n.lines = list(self.lines)
        n.bm = self.bm.copy()
        return n

    def edited(self, ops):
        """A copy with ops applied (clear:r,c,i,j, set:r,c,i,j, tile:r,c=OTHER, slot:N=OTHER, OTHER an Fs
        or a file) and its checksums recomputed, and notes on what changed."""
        n = self.copy()
        rows = {}       # frame -> its line as a list, while it's being edited
        notes = []

        def setbit(r, c, i, j, v):
            yy, xx = OFF[(r, c)][:2]
            Y, X = yy + i, xx + j
            if n.bm[Y, X] != v:
                n.bm[Y, X] = v
                s = rows.get(X)
                if s is None:
                    s = rows[X] = list(n.lines[n.fk[X]].strip())
                s[PAD + (n.L - 1 - Y)] = str(v)
                return True

        for op in ops:
            kind, arg = op.split(':', 1)
            if kind in ('clear', 'set'):
                r, c, i, j = map(int, arg.split(','))
                setbit(r, c, i, j, 0 if kind == 'clear' else 1)
                notes.append(f'{kind} ({r},{c}) ({i},{j})')
            elif kind == 'tile':
                rc, other = arg.split('=')
                r, c = map(int, rc.split(','))
                o = Fs(other, check=False).tile((r, c))
                cnt = 0
                for i, j in np.argwhere(o != self.tile((r, c))):
                    setbit(r, c, int(i), int(j), int(o[i, j]))
                    cnt += 1
                notes.append(f'tile ({r},{c}) <- {other}: {cnt} bits changed')
            elif kind == 'slot':
                num, other = arg.split('=')
                notes.append(n._slot(int(num), other))
        for X, s in rows.items():
            n.lines[n.fk[X]] = n._crc_line(X, ''.join(s))
        fb = bitmatrix.packbits(bitmatrix.fliplr(bitmatrix.transpose(n.bm)))
        cs = int(bitmatrix.bsum(fb[0::2]) * 256 + bitmatrix.bsum(fb[1::2])) & 0xffff
        for k in n.ftr_k:
            ba = bytearr(n.lines[k])
            if ba[0] == 0x0a and len(ba) == 8:
                notes.append(f'footer checksum {int.from_bytes(ba, "big") & 0xffff:04x} -> {cs:04x}')
                n.lines[k] = f'{(0x0a << 56) | cs:064b}'
                break
        n.lines = [f'//CheckSum: 0x{cs:04X}' if l.startswith('//CheckSum:') else l for l in n.lines]
        notes.insert(0, f'frames changed {sorted(rows)[:12]}{"…" if len(rows) > 12 else ""}')
        return n, notes

    def _slot(self, num, other):
        o = Fs(other, check=False)

        def find(f):
            for a, b in zip(f.ftr_k, f.ftr_k[1:]):
                ha, hb = bytearr(f.lines[a]), bytearr(f.lines[b])
                if ha[0] == 0x6a and ha[7] == num and hb[0] == 0x6b:
                    return a, b
        ma, mb = find(self)
        oa, ob = find(o)
        for f, a, b in ((self, ma, mb), (o, oa, ob)):       # CRC model check on both files
            h, d = bytearr(f.lines[a]), bytearr(f.lines[b])
            size = d[3]
            crc = d[4 + size] | (d[5 + size] << 8)
            assert calc(bytearray(b'\xff\xff') + h + d[:4 + size]) == crc, f'slot {num} CRC model fails'
        assert bytearr(self.lines[mb])[3] == bytearr(o.lines[ob])[3], 'slot sizes differ'
        old = self.lines[mb]
        self.lines[mb] = o.lines[ob].strip()
        return f'slot {num} <- {other}: ' + ('identical' if old.strip() == self.lines[mb] else 'replaced')

    def write(self, fn):
        open(fn, 'w').write('\n'.join(self.lines))


def bits_by_tile(m):
    """The set cells of a bit matrix as {(row, col): {(i, j), ...}}."""
    out = {}
    Y, X = np.nonzero(m)
    R = np.searchsorted(_ROWY, Y, 'right') - 1
    for r in np.unique(R):
        sel = R == r
        ys, xs = Y[sel], X[sel]
        Cc = np.searchsorted(_COLX[r], xs, 'right') - 1
        for y, x, c in zip(ys.tolist(), xs.tolist(), Cc.tolist()):
            ty, tx, w, h = OFF[(int(r), c)]
            if y - ty < h and x - tx < w:
                out.setdefault((int(r), c), set()).add((y - ty, x - tx))
    return out


def decode(fs):
    """Every tile's active routing, {"r,c": decoded tile}, in tile order."""
    from gw5a_common import decode_tile
    on = fs.on()
    empty = frozenset()
    return {f'{r},{c}': decode_tile(r, c, on.get((r, c), empty)) for r in range(db.rows) for c in range(db.cols)}


def slots(fs):
    """A file's config slots, {number: data line}."""
    out = {}
    for a, b in zip(fs.ftr_k, fs.ftr_k[1:]):
        ha, hb = bytearr(fs.lines[a]), bytearr(fs.lines[b])
        if ha[0] == 0x6a and ha[7] != 0xff and hb[0] == 0x6b:
            out[ha[7]] = fs.lines[b].strip()
    return out


def exact(base, new, ops):
    """Compare two builds' bits with the set:/clear: ops: (changed, wanted, effective, extra, missing)."""
    got = set()
    for op, m in (('set', (new.bm == 1) & (base.bm == 0)), ('clear', (new.bm == 0) & (base.bm == 1))):
        for rc, bits in bits_by_tile(m).items():
            got |= {(op, rc, b) for b in bits}
    want = set()
    for line in ops:
        op, v = line.split(':')
        r, c, i, j = map(int, v.split(','))
        want.add((op, (r, c), (i, j)))
    eff = set()
    for w in want:
        y, x = OFF[w[1]][:2]
        if (w[0] == 'set') != bool(base.bm[y + w[2][0], x + w[2][1]]):
            eff.add(w)
    return got, want, eff, got - want, eff - got
