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
_shape = {}     # wire name -> how key() names it, worked out once per name


def _wire_shape(w):
    m = re.match(r'([NSEW])1([12])(\d)$', w)
    if m:
        dr, dc, k = _HOP[m[1]]
        s = int(m[3])
        return dr * s, dc * s, f'_{k}{m[2]}0'
    if w in ('VCC', 'VSS'):
        return w
    return None if re.match(r'[NESW][128]\d\d', w) else f'_{w}'


def key(r, c, w):
    """A wire's chip-wide name. GW5A's 1-hop tracks 1/2 are named for the tile they leave."""
    n = _node.get((r, c, w))
    if n:
        sh = _shape.get(w, 0)
        if sh == 0:
            sh = _shape[w] = _wire_shape(w)
        if type(sh) is not tuple:
            return n
    else:
        sh = _shape.get(w, 0)
        if sh == 0:
            sh = _shape[w] = _wire_shape(w)
        if sh is None:
            return chipdb.wire2global(r + 1, c + 1, db, w)
        if type(sh) is str:
            return sh if sh[0] != '_' else f'R{r + 1}C{c + 1}{sh}'
    return f'R{r + sh[0] + 1}C{c + sh[1] + 1}{sh[2]}'


_tabs = {}      # tile type -> its muxes, with what doesn't change from tile to tile


def _mux_rows(kind, tab):
    rows = []
    for dst, srcs in tab.items():
        look = {}
        for s, b in srcs.items():
            look.setdefault(frozenset(map(tuple, b)), s)
        rows.append((f'{kind}|{dst}', frozenset().union(*look), look))
    return rows


def decode_tile(r, c, on):
    """A tile's active routing, {"kind|dest": [src, bits]}, from its set bits: gowin_unpack's
    exact-match rule with default=True, so no bits set means the empty-bit source."""
    ty = db.grid[r][c]
    if ty not in _tabs:
        t = db.tiles[ty]
        rows = _mux_rows('pip', t.pips) + _mux_rows('cpip', t.clock_pips)
        _tabs[ty] = rows, {k: [look[frozenset()], []] for k, _, look in rows if frozenset() in look}
    rows, default = _tabs[ty]
    extra = _mux_rows('hclk', db.hclk_pips.get((r, c), {})) + \
        _mux_rows('hclkx', db.extra_func.get((r, c), {}).get('hclk_pips', {}))
    if not on and not extra:
        return default
    d = {}
    for k, allb, look in rows + extra:
        used = allb & on
        s = look.get(used)
        if s is not None:
            d[k] = [s, sorted(used)]
        elif used:
            d[k] = [None, sorted(used)]
    return d


def tile_entries(rc, d):
    """A decoded tile as graph entries: (source wire, tile, kind, dest, source, bits), with the dest's key."""
    r, c = rc
    names = {}
    for kd, (src, bits) in d.items():
        if src is None:
            continue
        kind, dst = kd.split('|')
        ks = names.get(src) or names.setdefault(src, key(r, c, src))
        kt = names.get(dst) or names.setdefault(dst, key(r, c, dst))
        yield kt, (ks, rc, kind, dst, src, tuple(map(tuple, bits)))


def routes_graph(rt):
    """Decoded tiles as (graph, readers): graph[wire] lists what drives it, readers[wire] the active
    muxes that read it. rt is {"r,c": decoded tile}."""
    graph, readers = {}, collections.defaultdict(list)
    for rc, d in rt.items():
        rc = tuple(map(int, rc.split(',')))
        for kt, e in tile_entries(rc, d):
            graph.setdefault(kt, []).append(e)
            if e[5]:
                readers[e[0]].append((rc, e[2], e[3]))
    return graph, readers


def load_routes(fn):
    """An rtile.py file as (graph, readers)."""
    return routes_graph(json.load(open(fn)))


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
