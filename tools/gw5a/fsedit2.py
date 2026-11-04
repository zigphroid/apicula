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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_fs import Fs

if len(sys.argv) < 4:
    sys.exit(__doc__)
src, dst = sys.argv[1], sys.argv[2]
ops = []
for a in sys.argv[3:]:
    ops += [l.strip() for l in open(a[1:]) if l.strip()] if a.startswith('@') else [a]
new, notes = Fs(src).edited(ops)
new.write(dst)
print('\n'.join(notes))
