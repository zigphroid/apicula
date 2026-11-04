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
from gw5a_fs import Fs, decode

if len(sys.argv) != 3:
    sys.exit(__doc__)
json.dump(decode(Fs(sys.argv[1], check=False)), open(sys.argv[2], 'w'))
