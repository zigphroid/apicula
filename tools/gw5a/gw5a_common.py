"""What the GW5AT-60B bitstream tools share: the chipdb, tile bitmaps and routing decodes."""
import collections, importlib.resources, json, re

from apycula import chipdb, gowin_pack
from apycula.bslib import read_bitstream
from apycula.chipdb import load_chipdb

DEVICE = 'GW5AT-60B'

with importlib.resources.path('apycula', f'{DEVICE}.msgpack.xz') as p:
    db = load_chipdb(p)


class _Pack:
    chipdb = gowin_pack.ChipDB(DEVICE)


tilemap = gowin_pack.GW5AT_60B.get_tilemap_func(_Pack())


def load(fn, empty=False):
    """A bitstream's tiles, {(row, col): bitmap}. empty=True keeps all-zero tiles."""
    return chipdb.tile_bitmap_holes(db, read_bitstream(fn)[0], tilemap, empty=empty)


def ones(tile):
    return {(i, j) for i, row in enumerate(tile) for j, v in enumerate(row) if v}


_node = {}
for _name, (_, _members) in db.nodes.items():
    for _r, _c, _w in _members:
        _node[(_r, _c, _w)] = 'N:' + _name
_HOP = {'N': (1, 0, 'SN'), 'S': (-1, 0, 'SN'), 'E': (0, -1, 'EW'), 'W': (0, 1, 'EW')}


def key(r, c, w):
    """A wire's chip-wide name. GW5A's 1-hop tracks 1/2 are named for the tile they leave."""
    m = re.match(r'([NSEW])1([12])(\d)$', w)
    if m:
        dr, dc, k = _HOP[m[1]]
        s = int(m[3])
        return f'R{r + dr * s + 1}C{c + dc * s + 1}_{k}{m[2]}0'
    return _node.get((r, c, w)) or chipdb.wire2global(r + 1, c + 1, db, w)


def load_routes(fn):
    """An rtile.py file as (graph, readers): graph[wire] lists what drives it,
    readers[wire] lists the active muxes that read it."""
    graph, readers = {}, collections.defaultdict(list)
    for rc, d in json.load(open(fn)).items():
        r, c = map(int, rc.split(','))
        for kd, (src, bits) in d.items():
            kind, dst = kd.split('|')
            if src is None:
                continue
            e = (key(r, c, src), (r, c), kind, dst, src, tuple(map(tuple, bits)))
            graph.setdefault(key(r, c, dst), []).append(e)
            if bits:
                readers[key(r, c, src)].append(((r, c), kind, dst))
    return graph, readers


def trace(graph, k):
    """Follow wire k back to its driver: (source, path, 'ok' | 'ambiguous' | 'unresolved').
    Long wires (LB/LT) have no nodes in the chipdb, so a trace stops there unresolved."""
    path, seen = [], set()
    while k in graph and k not in seen and len(path) < 40:
        seen.add(k)
        e = graph[k]
        if len({x[0] for x in e}) > 1:
            return k, path, 'ambiguous'
        e = e[0]
        path.append(e)
        k = e[0]
        if re.search(r'_(Q|F|OF)\d$', k) or k in ('VCC', 'VSS', 'N:VCC', 'N:VSS'):
            return k, path, 'ok'
    return k, path, 'unresolved'
