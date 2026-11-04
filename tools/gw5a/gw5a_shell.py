#!/usr/bin/env python3
"""gw5a_shell.py [--socket PATH] [--plugin FILE.py ...]: the tools as one long-lived process.

Loading the chipdb and decoding a build takes seconds, so this keeps them in
memory and takes commands, one per line, from stdin or from each connection
to a unix socket:

    load NAME FILE.fs              read a build and decode its routing
    edit NAME BASE OPS.ops         a new build: BASE with the ops applied (only changed tiles re-decoded)
    write NAME FILE.fs             write it out
    exact BASE NAME OPS.ops [FILE.fs]  the bits against the ops; FILE.fs reads the written file back
    check NAME BASE [SRC PORTS]    gcheck on NAME against BASE; PORTS is gcheck's ports file
    drop NAME                      forget a build
    stats                          the builds held, and peak memory
    quit

Each command's output ends with a line `.`. A plugin file defines
register(shell), and adds commands by shell.commands[name] = function(args).
"""
import argparse
import importlib.util
import os
import resource
import socketserver
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gw5a_check import check, read_ports, sinks
from gw5a_common import routes_graph, tile_entries
from gw5a_common import decode_tile
from gw5a_fs import Fs, bits_by_tile, decode, exact


class Overlay:
    """A routing graph with some wires replaced: all a check of an edited build needs."""

    def __init__(self, base, over):
        self.base, self.over = base, over

    def __contains__(self, k):
        return k in self.over or k in self.base

    def __getitem__(self, k):
        return self.over[k] if k in self.over else self.base[k]


class Build:
    def __init__(self, fs, rt=None, graph=None, readers=None):
        self.fs, self.rt, self.graph, self.readers = fs, rt, graph, readers
        self._sinks = None

    def sinks(self):
        if self._sinks is None:
            self._sinks = sinks(self.graph, self.readers)
        return self._sinks


def edited_graph(base, new_fs):
    """base's graph with only the tiles new_fs changes decoded again."""
    touched = bits_by_tile(base.fs.bm != new_fs.bm)
    over = {}
    for rc in touched:
        yy, xx = rc
        on = {(int(i), int(j)) for i, j in zip(*new_fs.tile(rc).nonzero())}
        new = {}
        for kt, e in tile_entries(rc, decode_tile(yy, xx, frozenset(on))):
            new.setdefault(kt, []).append(e)
        old = {kt for kt, _ in tile_entries(rc, base.rt[f'{yy},{xx}'])}
        for kt in old | set(new):
            es = [e for e in over.get(kt, base.graph.get(kt, [])) if e[1] != rc] + new.get(kt, [])
            over[kt] = sorted(es, key=lambda e: e[1])
    return Overlay(base.graph, over), len(touched)


class Shell:
    def __init__(self):
        self.builds = {}
        self.commands = {'load': self.load, 'edit': self.edit, 'write': self.write, 'exact': self.exact,
                         'check': self.check, 'drop': self.drop, 'stats': self.stats}

    def load(self, a):
        fs = Fs(a[1])
        rt = decode(fs)
        self.builds[a[0]] = Build(fs, rt, *routes_graph(rt))
        return [f'{a[0]}: loaded']

    def edit(self, a):
        base = self.builds[a[1]]
        ops = [line.strip() for line in open(a[2]) if line.strip()]
        fs, notes = base.fs.edited(ops)
        g, n = edited_graph(base, fs)
        self.builds[a[0]] = Build(fs, base.rt, g, base.readers)
        return [notes[-1], f'{a[0]}: {len(ops)} ops, {n} tiles decoded again']

    def write(self, a):
        self.builds[a[0]].fs.write(a[1])
        return [f'{a[1]}: written']

    def exact(self, a):
        base = self.builds[a[0]].fs
        new = Fs(a[3], check=False) if len(a) > 3 else self.builds[a[1]].fs
        ops = [line.strip() for line in open(a[2]) if line.strip()]
        got, want, eff, extra, missing = exact(base, new, ops)
        out = [f'bits changed {len(got)}; intended {len(want)} ({len(eff)} not already in base); '
               f'extra {len(extra)}; missing {len(missing)}']
        out += [f'  extra {x}' for x in sorted(extra)[:10]] + [f'  missing {x}' for x in sorted(missing)[:10]]
        return out

    def check(self, a):
        new, base = self.builds[a[0]], self.builds[a[1]]
        src = self.builds[a[2]].graph if len(a) > 2 else None
        ports = read_ports(a[3]) if len(a) > 3 else None
        return check(new.graph, base.graph, base.readers, src, ports, base.sinks())[0]

    def drop(self, a):
        del self.builds[a[0]]
        return []

    def stats(self, a):
        return [f'builds {sorted(self.builds)}; peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.2f} GB']

    def run(self, line):
        f = line.split()
        if not f:
            return []
        t = time.time()
        try:
            out = self.commands[f[0]](f[1:])
        except Exception:
            out = traceback.format_exc().splitlines()
        return list(out) + [f'[{f[0]}: {time.time() - t:.2f} s]']


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--socket')
    ap.add_argument('--plugin', action='append', default=[])
    a = ap.parse_args()
    sh = Shell()
    for fn in a.plugin:
        sp = importlib.util.spec_from_file_location(os.path.basename(fn)[:-3], fn)
        mod = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(mod)
        mod.register(sh)
    if a.socket:
        class H(socketserver.StreamRequestHandler):
            def handle(self):
                for raw in self.rfile:
                    line = raw.decode().strip()
                    if line == 'quit':
                        self.server.quitting = True
                        return
                    self.wfile.write(('\n'.join(sh.run(line) + ['.']) + '\n').encode())
        if os.path.exists(a.socket):
            os.unlink(a.socket)
        srv = socketserver.UnixStreamServer(a.socket, H)
        srv.quitting = False
        while not srv.quitting:
            srv.handle_request()
        os.unlink(a.socket)
        return
    for line in sys.stdin:
        if line.strip() == 'quit':
            break
        print('\n'.join(sh.run(line) + ['.']), flush=True)


if __name__ == '__main__':
    main()
