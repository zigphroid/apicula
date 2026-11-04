#!/usr/bin/env python3
"""exact.py base.fs new.fs [ops files...] [--slots N,N --slotsrc other.fs]: did the edit do only what it meant to?

Every bit that differs from base must be one of the ops, and every op that
changes something must have happened. With --slots, those slots must equal
other.fs's.
"""
import os
import sys

from apycula.bslib import read_bitstream

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_common import load, ones

args = sys.argv[1:]
slots, ssrc = [], None
if '--slots' in args:
    i = args.index('--slots')
    slots = [int(x) for x in args[i + 1].split(',')]
    ssrc = args[i + 3]
    args = args[:i]
if len(args) < 2:
    sys.exit(__doc__)
base, new, opsf = args[0], args[1], args[2:]
A, B = load(base, empty=True), load(new, empty=True)
got = set()
for rc in A:
    a, b = ones(A[rc]), ones(B[rc])
    got |= {('set', rc, x) for x in b - a} | {('clear', rc, x) for x in a - b}
want = set()
for fn in opsf:
    for line in open(fn):
        if line.strip():
            op, v = line.strip().split(':')
            r, c, i, j = map(int, v.split(','))
            want.add((op, (r, c), (i, j)))
eff = {w for w in want if (w[0] == 'set') != (w[2] in ones(A[w[1]]))}
print(f'bits changed {len(got)}; intended {len(want)} ({len(eff)} not already in base); '
      f'extra {len(got - want)}; missing {len(eff - got)}')
for x in sorted(got - want)[:10]:
    print('  extra', x)
for x in sorted(eff - got)[:10]:
    print('  missing', x)
SA, SB = read_bitstream(base)[3], read_bitstream(new)[3]
sd = [k for k in set(SA) | set(SB) if (SA.get(k) is None) != (SB.get(k) is None)
      or (SA.get(k) is not None and (SA[k] != SB[k]).any())]
ok = 'n/a'
if ssrc:
    SS = read_bitstream(ssrc)[3]
    ok = all((SB[k] == SS[k]).all() for k in slots)
print('slots differing from base', sorted(sd), '| intended', slots, '| equal to source:', ok)
sys.exit(1 if got - want or eff - got or ok is False else 0)
