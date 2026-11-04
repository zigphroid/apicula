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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_check import check, read_ports
from gw5a_common import load_routes

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
GT = load_routes(a.src)[0] if a.src else None
lines, bad = check(GN, GO, REVO, GT, read_ports(a.ports) if a.ports else None)
print('\n'.join(lines))
sys.exit(1 if bad else 0)
