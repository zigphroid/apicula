#!/usr/bin/env python3
"""mkgraft.py BASE.fs SRC.fs out.ops: fsedit2 ops that give BASE the SRC's routing.

Takes from SRC every routing-mux bit (pips, clock pips, hclk pips, alone
nodes), every bit no table names (they follow the routing), and whole logic
tiles (LUT INITs and DFF config follow the routing's input permutation).
Other config bits (IOB, IOLOGIC, DQS, BSRAM, PLL, DLL, bank...) stay BASE's.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_common import db, load, ones

if len(sys.argv) != 4:
    sys.exit(__doc__)
A, B = load(sys.argv[1]), load(sys.argv[2])


def routebits(rc):
    t = db[rc]
    s = set()
    for tab in (t.pips, t.clock_pips, db.hclk_pips.get(rc, {}), db.extra_func.get(rc, {}).get('hclk_pips', {})):
        for srcs in tab.values():
            for b in srcs.values():
                s |= set(map(tuple, b))
    for tab in (getattr(t, 'alonenode', {}), getattr(t, 'alonenode_6', {})):
        for lst in tab.values():
            for _, b in lst:
                s |= set(map(tuple, b))
    return s


def cfgbits(rc):
    t = db[rc]
    s = set()
    for tabs in (db.shortval.get(t.ttyp, {}), db.longval.get(t.ttyp, {})):
        for ent in tabs.values():
            for b in ent.values():
                s |= set(map(tuple, b))
    return s


ops = []
cnt = collections.Counter()
# all-zero tiles are absent from load(), so go over both builds' tiles
for rc in sorted(set(A) | set(B)):
    sa = ones(A[rc]) if rc in A else set()
    sb = ones(B[rc]) if rc in B else set()
    if sa == sb:
        continue
    logic = 'LUT0' in db[rc].bels
    rb = None if logic else routebits(rc)
    cb = None if logic else cfgbits(rc)
    for op, bits in (('set', sb - sa), ('clear', sa - sb)):
        for b in sorted(bits):
            if logic or b in rb or b not in cb:
                ops.append(f'{op}:{rc[0]},{rc[1]},{b[0]},{b[1]}')
                cnt['logic' if logic else ('route' if b in rb else 'unnamed')] += 1
            else:
                cnt[f'kept config ({op})'] += 1
open(sys.argv[3], 'w').write('\n'.join(ops) + ('\n' if ops else ''))
print(len(ops), 'ops', dict(cnt))
