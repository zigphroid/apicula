#!/usr/bin/env python3
"""rtile.py in.fs out.json: every tile's active routing, {"r,c": {"kind|dest": [src, [[i, j], ...]]}}.

gowin_unpack's exact-match rule with default=True (no bits set means the
empty-bit source), over all four tables: pips, clock pips, hclk pips and the
extra_func hclk pips.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_common import db, load, ones

if len(sys.argv) != 3:
    sys.exit(__doc__)
out = {}
for (r, c), bm in load(sys.argv[1], empty=True).items():
    on = ones(bm)
    t = db.tiles[db.grid[r][c]]
    d = {}
    for kind, tab in (('pip', t.pips), ('cpip', t.clock_pips), ('hclk', db.hclk_pips.get((r, c), {})),
                      ('hclkx', db.extra_func.get((r, c), {}).get('hclk_pips', {}))):
        for dst, srcs in tab.items():
            allb = set().union(*[set(map(tuple, b)) for b in srcs.values()])
            used = allb & on
            best = [s for s, b in srcs.items() if set(map(tuple, b)) == used]
            if best:
                d[f'{kind}|{dst}'] = [best[0], sorted(used)]
            elif used:
                d[f'{kind}|{dst}'] = [None, sorted(used)]
    out[f'{r},{c}'] = d
json.dump(out, open(sys.argv[2], 'w'))
