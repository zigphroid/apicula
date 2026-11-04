#!/usr/bin/env python3
"""fsedit2.py in.fs out.fs OP... : edit a GW5AT-60B .fs, keeping its checksums right.

An OP is one of these, or @FILE for a file of them, one per line:
    clear:r,c,i,j       clear a bit (tile row, col; bit row, col)
    set:r,c,i,j         set a bit
    tile:r,c=other.fs   copy a whole tile from another .fs
    slot:N=other.fs     copy a config slot verbatim

Frame CRC16s and the footer 0x0a checksum are recomputed (gowin_pack's GW5A
formulas). A slot is copied after checking its CRC depends only on ff ff and
its own lines.
"""
import os
import sys

from apycula import bitmatrix
from apycula.bslib import bytearr, make_crc16_arc, read_bitstream

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_common import db, load, tilemap

calc = make_crc16_arc(); PAD = 2
def parse(fn):
    lines = open(fn).read().split('\n')
    idx = [k for k, l in enumerate(lines) if l and not l.startswith('//')]
    for n, k in enumerate(idx):
        ba = bytearr(lines[k])
        if ba[0] == 0x3b: frames = int.from_bytes(ba[2:], 'big'); first = n + 1; break
    hdr = [bytearr(lines[k]) for k in idx[:first]]
    return lines, idx[first:first + frames], idx[first + frames:], hdr
OFF = {}; y = 0
for r in range(db.rows):
    x = 0
    for c in range(db.cols):
        w, h, _ = tilemap(r, c); OFF[(r, c)] = (y, x, w, h); x += w
    y += h
if len(sys.argv) < 4:
    sys.exit(__doc__)
src, dst = sys.argv[1], sys.argv[2]
ops = []
for a in sys.argv[3:]:
    ops += [l.strip() for l in open(a[1:]) if l.strip()] if a.startswith('@') else [a]
_tc = {}
def tiles(fn):
    if fn not in _tc: _tc[fn] = load(fn, empty=True)
    return _tc[fn]
lines, fk, ftr_k, hdr = parse(src)
# frame-0 CRC covers the header after the preamble (found by search), less d2 lines
f0 = bytearr(lines[fk[0]]); want0 = f0[-8] | (f0[-7] << 8)
skip = next(s for s in range(0, 8) if calc(bytearray(b''.join(bytes(b) for b in hdr[s:] if b[0] != 0xd2)) + f0[:-8]) == want0)
hdrbytes = bytearray(b''.join(bytes(b) for b in hdr[skip:] if b[0] != 0xd2))
def crc_line(n, s):
    ba = bytearr(s); c = calc((hdrbytes if n == 0 else bytearray(b'\xff' * 6)) + ba[:-8])
    return s[:-64] + f'{c & 0xff:08b}{c >> 8:08b}' + s[-48:]
bad = [n for n in range(len(fk)) if crc_line(n, lines[fk[n]].strip()) != lines[fk[n]].strip()]
assert not bad, f'frame CRC model fails at {bad[:5]}'
L = len(lines[fk[0]].strip()) - PAD - 64
def setbit(r, c, i, j, v):
    yy, xx, w, h = OFF[(r, c)]; Y, X = yy + i, xx + j
    s = list(lines[fk[X]].strip()); pos = PAD + (L - 1 - Y)
    if s[pos] != str(v):
        s[pos] = str(v); lines[fk[X]] = ''.join(s); return X
changed = set(); notes = []
for op in ops:
    kind, arg = op.split(':', 1)
    if kind in ('clear', 'set'):
        r, c, i, j = map(int, arg.split(','))
        X = setbit(r, c, i, j, 0 if kind == 'clear' else 1)
        if X is not None: changed.add(X)
        notes.append(f'{kind} ({r},{c}) ({i},{j})')
    elif kind == 'tile':
        rc, other = arg.split('='); r, c = map(int, rc.split(','))
        mine, theirs = tiles(src)[(r, c)], tiles(other)[(r, c)]
        n = 0
        for i, row in enumerate(theirs):
            for j, v in enumerate(row):
                if v != mine[i][j]:
                    X = setbit(r, c, i, j, v); changed.add(X); n += 1
        notes.append(f'tile ({r},{c}) <- {other}: {n} bits changed')
    elif kind == 'slot':
        num, other = arg.split('='); num = int(num)
        ol, ofk, oftr, _ = parse(other)
        def find(L_, ks):
            for a, b in zip(ks, ks[1:]):
                ha, hb = bytearr(L_[a]), bytearr(L_[b])
                if ha[0] == 0x6a and ha[7] == num and hb[0] == 0x6b: return a, b
        ma, mb = find(lines, ftr_k); oa, ob = find(ol, oftr)
        for L_, a, b in ((lines, ma, mb), (ol, oa, ob)):     # CRC model check on both files
            h, d = bytearr(L_[a]), bytearr(L_[b]); size = d[3]
            body = d[:4 + size]; crc = d[4 + size] | (d[5 + size] << 8)
            assert calc(bytearray(b'\xff\xff') + h + body) == crc, f'slot {num} CRC model fails'
        assert bytearr(lines[mb])[3] == bytearr(ol[ob])[3], 'slot sizes differ'
        old = lines[mb]; lines[mb] = ol[ob].strip()
        notes.append(f'slot {num} <- {other}: ' + ('identical' if old.strip() == lines[mb] else 'replaced'))
for X in changed: lines[fk[X]] = crc_line(X, lines[fk[X]].strip())
open(dst, 'w').write('\n'.join(lines))
bm = read_bitstream(dst)[0]
fb = bitmatrix.packbits(bitmatrix.fliplr(bitmatrix.transpose(bm)))
cs = int(bitmatrix.bsum(fb[0::2]) * 256 + bitmatrix.bsum(fb[1::2])) & 0xffff
for k in ftr_k:
    ba = bytearr(lines[k])
    if ba[0] == 0x0a and len(ba) == 8:
        notes.append(f'footer checksum {int.from_bytes(ba, "big") & 0xffff:04x} -> {cs:04x}')
        lines[k] = f'{(0x0a << 56) | cs:064b}'; break
lines = [f'//CheckSum: 0x{cs:04X}' if l.startswith('//CheckSum:') else l for l in lines]
open(dst, 'w').write('\n'.join(lines))
print(f'frame-0 header skip {skip}; frames changed {sorted(changed)[:12]}{"…" if len(changed) > 12 else ""}')
print('\n'.join(notes))
