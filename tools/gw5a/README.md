# GW5AT-60B bitstream tools

Command-line tools for reading, editing and checking GW5AT-60B `.fs`
bitstreams at fuse level, used to compare two builds of the same design or to
move part of one build's routing into another. They need an installed
`apycula` with the GW5AT-60B chipdb, which they find through the package;
everything else comes from their arguments.

Run them from anywhere:

    python3 tools/gw5a/rtile.py build.fs build.rt.json

Tiles and bits are numbered as in `chipdb.tile_bitmap_holes`: `r,c` is the
tile's row and column, `i,j` the bit's row and column in that tile.

## The tools

### rtile.py: decode routing

    rtile.py in.fs out.rt.json

Writes each tile's active routing as `{"r,c": {"kind|dest": [src, [[i, j], ...]]}}`,
using `gowin_unpack`'s exact-match rule with `default=True`, over the pips,
clock pips, hclk pips and `extra_func` hclk pips.

### fsedit2.py: edit bits

    fsedit2.py in.fs out.fs OP...

An OP is `clear:r,c,i,j`, `set:r,c,i,j`, `tile:r,c=other.fs`, `slot:N=other.fs`,
or `@FILE` for a file of them, one per line. Frame CRC16s and the footer
checksum are recomputed. It stops if the input's frame CRCs don't fit the model.

### mkgraft.py: ops for another build's routing

    mkgraft.py BASE.fs SRC.fs out.ops

Writes the ops that give BASE all of SRC's routing: every routing-mux bit,
every bit no table names, and whole logic tiles. Named config bits stay BASE's.

### exact.py: check an edit

    exact.py base.fs new.fs [ops files...] [--slots N,N --slotsrc other.fs]

Checks that the bits differing from base are exactly the ops. Exits 1 if not.

### gcheck.py: check an edit's decode

    gcheck.py NEW.rt.json BASE.rt.json [--src SRC.rt.json --ports FILE]

Checks that every load BASE routes keeps its source in NEW, and that each
listed port's path equals SRC's, mux for mux. A ports file has one port per
line: `label row col wire [base_wire]`. Exits 1 on any difference.

`exact.py` can pass on an edit that puts a load on the wrong net, since it
only compares bits with the ops. Run `gcheck.py` as well.

## Example: round trip

Reversing an edit should give back the base byte for byte:

    fsedit2.py base.fs new.fs @edit.ops
    mkgraft.py new.fs base.fs back.ops
    fsedit2.py new.fs back.fs @back.ops
    cmp base.fs back.fs

This holds for edits of routing and unnamed bits, and bits in logic tiles.
`mkgraft.py` leaves named config bits alone, so an edit of one won't reverse.

## Limits

- Long wires (LB, LT) have no nodes in the chipdb, so a trace stops there as
  unresolved. `gcheck.py` prints how many loads it couldn't check for this reason.
- GW5AT-60B only: `gw5a_common.py` names the device and its tile map.
