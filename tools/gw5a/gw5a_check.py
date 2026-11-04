"""Does an edited build decode right? See gcheck.py."""
import re

from gw5a_common import key, trace


def read_ports(fn):
    ports = []
    for line in open(fn):
        f = line.split()
        if f:
            ports.append((f[0], int(f[1]), int(f[2]), f[3], f[4] if len(f) > 4 else f[3]))
    return ports


def sinks(GO, REVO):
    """The loads a build routes: wires nothing reads, with an active route. {wire: (source, status)}."""
    return {k: trace(GO, k)[::2] for k, es in GO.items() if not REVO.get(k) and any(e[5] for e in es)}


def check(GN, GO, REVO, GT=None, ports=None, base_sinks=None):
    """Report lines and how many things are wrong. GN may be an Overlay of GO."""
    name = lambda s: re.sub(r'^N:', '', s or '')
    muxes = lambda p: [(e[1], e[3], e[4]) for e in p]
    out = []
    K = set()
    bad = 0
    if ports:
        same, diff = 0, []
        for lab, r, c, w, wo in ports:
            k = key(r, c, w)
            K |= {k, key(r, c, wo)}
            st, pt, tt = trace(GT, k)
            sn, pn, tn = trace(GN, k)
            if not pt:
                continue
            if muxes(pt) == muxes(pn) and st == sn:
                same += 1
            else:
                diff.append((lab, st, sn, tt, tn))
        out.append(f'ports: {len(K)} wires; path equal to SRC {same}; different {len(diff)}')
        out += [f'  DIFF {d}' for d in diff[:12]]
        bad += len(diff)
    n = ok = unres = 0
    moved = []
    for k, (so, to) in (base_sinks if base_sinks is not None else sinks(GO, REVO)).items():
        if k in K:
            continue
        if to != 'ok':
            unres += 1
            continue
        n += 1
        s2, _, t2 = trace(GN, k)
        if name(s2) == name(so):
            ok += 1
        else:
            moved.append((k, so, s2, t2))
    out.append(f'other loads: {n}; same source in NEW {ok}; changed {len(moved)}; not checked (no resolved source) {unres}')
    out += [f'  CHANGED {m}' for m in moved[:20]]
    return out, bad + len(moved)
