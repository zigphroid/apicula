#!/usr/bin/env python3
"""exact.py base.fs new.fs [ops files...] [--slots N,N --slotsrc other.fs]: did the edit do only what it meant to?

Every bit that differs from base must be one of the ops, and every op that
changes something must have happened. With --slots, those slots must equal
other.fs's.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_fs import Fs, exact, slots

args = sys.argv[1:]
want_slots, ssrc = [], None
if '--slots' in args:
    i = args.index('--slots')
    want_slots = [int(x) for x in args[i + 1].split(',')]
    ssrc = args[i + 3]
    args = args[:i]
if len(args) < 2:
    sys.exit(__doc__)
A, B = Fs(args[0], check=False), Fs(args[1], check=False)
ops = [line.strip() for fn in args[2:] for line in open(fn) if line.strip()]
got, want, eff, extra, missing = exact(A, B, ops)
print(f'bits changed {len(got)}; intended {len(want)} ({len(eff)} not already in base); '
      f'extra {len(extra)}; missing {len(missing)}')
for x in sorted(extra)[:10]:
    print('  extra', x)
for x in sorted(missing)[:10]:
    print('  missing', x)
SA, SB = slots(A), slots(B)
sd = [k for k in set(SA) | set(SB) if SA.get(k) != SB.get(k)]
ok = 'n/a'
if ssrc:
    SS = slots(Fs(ssrc, check=False))
    ok = all(SB[k] == SS[k] for k in want_slots)
print('slots differing from base', sorted(sd), '| intended', want_slots, '| equal to source:', ok)
sys.exit(1 if extra or missing or ok is False else 0)
