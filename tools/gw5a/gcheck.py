#!/usr/bin/env python3
"""gcheck.py NEW.rt.json BASE.rt.json [--src SRC.rt.json --ports FILE]: does an edited build decode right?

Every load BASE routes (a wire nothing reads, with an active route and a
resolved source) must keep its source in NEW, except the listed ports. Each
listed port's path in NEW must equal SRC's, mux for mux.

A ports file has one port per line: label row col wire [base_wire]. base_wire
names the wire in BASE when the port moved. The .rt.json files are rtile.py's.
Loads whose trace stops on a long wire can't be checked; their count is printed.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_common import key, load_routes, trace

ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
ap.add_argument('new')
ap.add_argument('base')
ap.add_argument('--src')
ap.add_argument('--ports')
a = ap.parse_args()
if bool(a.src) != bool(a.ports):
    ap.error('--src and --ports go together')

GN, _ = load_routes(a.new)
GO, REVO = load_routes(a.base)
name = lambda s: re.sub(r'^N:', '', s or '')
muxes = lambda p: [(e[1], e[3], e[4]) for e in p]
bad = 0
K = set()
if a.ports:
    GT, _ = load_routes(a.src)
    same, diff = 0, []
    for line in open(a.ports):
        f = line.split()
        if not f:
            continue
        lab, r, c, w = f[0], int(f[1]), int(f[2]), f[3]
        k = key(r, c, w)
        K |= {k, key(r, c, f[4] if len(f) > 4 else w)}
        st, pt, tt = trace(GT, k)
        sn, pn, tn = trace(GN, k)
        if not pt:
            continue
        if muxes(pt) == muxes(pn) and st == sn:
            same += 1
        else:
            diff.append((lab, st, sn, tt, tn))
    print(f'ports: {len(K)} wires; path equal to SRC {same}; different {len(diff)}')
    for d in diff[:12]:
        print('  DIFF', d)
    bad += len(diff)
n = ok = unres = 0
moved = []
for k, es in GO.items():
    if k in K or REVO.get(k) or not any(e[5] for e in es):
        continue
    so, _, to = trace(GO, k)
    if to != 'ok':
        unres += 1
        continue
    n += 1
    s2, _, t2 = trace(GN, k)
    if name(s2) == name(so):
        ok += 1
    else:
        moved.append((k, so, s2, t2))
print(f'other loads: {n}; same source in NEW {ok}; changed {len(moved)}; not checked (no resolved source) {unres}')
for m in moved[:20]:
    print('  CHANGED', m)
sys.exit(1 if bad or moved else 0)
