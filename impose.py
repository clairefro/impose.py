#!/usr/bin/env python3
"""
16-up folio imposition for cut-and-stack bookbinding using pikepdf.

Arranges 16 manuscript pages per physical sheet (4 folios in a 2×2 grid).
Output has two PDF pages per sheet: Side A (front) and Side B (back),
laid out for duplex printing with long-edge flip.

After printing duplex, cut each sheet into 4 quarters and stack
to form signatures.
"""

import argparse
import math
import sys
from decimal import Decimal

import pikepdf
from pikepdf import Name, Array, Dictionary, Stream, Pdf

# Sensible folio-grid layouts (folio_cols × folio_rows).
# Each folio slot is 2 pages wide × 1 page tall.
FOLIO_GRIDS = {
    1: (1, 1),   #  4 pages/sheet  – quarto
    2: (2, 1),   #  8 pages/sheet  – octavo
    4: (2, 2),   # 16 pages/sheet  – sextodecimo
    8: (4, 2),   # 32 pages/sheet  – trigesimo-secundo
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="N-up folio imposition for cut-and-stack bookbinding."
    )
    p.add_argument("input_file", help="Input manuscript PDF (one page = one book page)")
    p.add_argument("output_file", help="Output imposed PDF")
    p.add_argument(
        "-f", "--folios", type=int, default=4,
        help="Folios per signature (default: 4). 1 folio = 4 book pages. "
             "e.g. 1=quarto, 2=octavo, 4=sextodecimo, 8=32mo"
    )
    args = p.parse_args()
    if args.folios < 1:
        p.error("folios must be ≥ 1")
    return args


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def page_to_xobject(out_pdf, src_pdf, page_idx):
    """Convert a source page into a Form XObject in the output PDF."""
    page = src_pdf.pages[page_idx]
    mb = page.mediabox
    bbox = [float(mb[i]) for i in range(4)]

    contents = page.obj.get(Name.Contents)
    if contents is None:
        data = b""
    elif isinstance(contents, pikepdf.Array):
        data = b"\n".join(c.read_bytes() for c in contents)
    else:
        data = contents.read_bytes()

    xobj = Stream(out_pdf, data)
    xobj[Name.Type] = Name.XObject
    xobj[Name.Subtype] = Name.Form
    xobj[Name.BBox] = Array([Decimal(str(v)) for v in bbox])

    res = page.obj.get(Name.Resources)
    if res is not None:
        xobj[Name.Resources] = out_pdf.copy_foreign(res)

    return xobj, bbox


def crop_marks_stream(sheet_w, sheet_h, v_cuts, h_cuts):
    """Return content-stream bytes for thin crop marks at all cut lines."""
    m = 36   # mark length (pt, ~0.5 in)
    g = 2    # gap from sheet edge (pt)
    ops = ["q", "0.5 0.5 0.5 RG", "0.25 w"]

    for cx in v_cuts:
        # Top and bottom edge marks
        ops.append(f"{cx:.2f} {sheet_h - g:.2f} m {cx:.2f} {sheet_h - g - m:.2f} l S")
        ops.append(f"{cx:.2f} {g:.2f} m {cx:.2f} {g + m:.2f} l S")
        # Cross marks at each horizontal cut intersection
        for cy in h_cuts:
            ops.append(f"{cx:.2f} {cy - m:.2f} m {cx:.2f} {cy + m:.2f} l S")
            ops.append(f"{cx - m:.2f} {cy:.2f} m {cx + m:.2f} {cy:.2f} l S")

    for cy in h_cuts:
        # Left and right edge marks
        ops.append(f"{g:.2f} {cy:.2f} m {g + m:.2f} {cy:.2f} l S")
        ops.append(f"{sheet_w - g:.2f} {cy:.2f} m {sheet_w - g - m:.2f} {cy:.2f} l S")

    ops.append("Q")
    return "\n".join(ops).encode()


def make_sheet(out_pdf, sheet_w, sheet_h, placements, crop_bytes):
    """
    Build one output page (one side of a physical sheet).

    placements: [(xobj, tx, ty), ...]
        xobj  – Form XObject to draw
        tx,ty – bottom-left position on the sheet
    """
    xobj_dict = Dictionary()
    content_parts = []

    for i, (xobj, tx, ty) in enumerate(placements):
        xname = f"P{i}"
        xobj_dict[Name(f"/{xname}")] = out_pdf.make_indirect(xobj)
        content_parts.append(f"q 1 0 0 1 {tx:.4f} {ty:.4f} cm /{xname} Do Q")

    content = "\n".join(content_parts).encode()
    if crop_bytes:
        content += b"\n" + crop_bytes

    page_dict = Dictionary({
        "/Type": Name.Page,
        "/MediaBox": Array([0, 0, Decimal(str(sheet_w)), Decimal(str(sheet_h))]),
        "/Resources": Dictionary({"/XObject": xobj_dict}),
        "/Contents": Stream(out_pdf, content),
    })
    return pikepdf.Page(out_pdf.make_indirect(page_dict))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    num_folios = args.folios
    pages_per_sheet = num_folios * 4

    # Folio grid dimensions
    if num_folios in FOLIO_GRIDS:
        fcols, frows = FOLIO_GRIDS[num_folios]
    else:
        fcols = math.ceil(math.sqrt(num_folios))
        frows = math.ceil(num_folios / fcols)

    src = Pdf.open(args.input_file)
    total = len(src.pages)

    # Page dimensions from first page
    mb = src.pages[0].mediabox
    x0, y0 = float(mb[0]), float(mb[1])
    pw = float(mb[2]) - x0   # page width
    ph = float(mb[3]) - y0   # page height

    # Pad to a multiple of pages_per_sheet with blank pages
    remainder = total % pages_per_sheet
    if remainder:
        pad_count = pages_per_sheet - remainder
        for _ in range(pad_count):
            blank = Dictionary({
                "/Type": Name.Page,
                "/MediaBox": Array(list(mb)),
            })
            src.pages.append(pikepdf.Page(src.make_indirect(blank)))
        total += pad_count
        print(f"Padded {pad_count} blank page(s) → {total} total")

    # Sheet geometry: each folio slot = 2 pages wide × 1 page tall
    sheet_w = fcols * 2 * pw
    sheet_h = frows * ph

    # Cut lines
    v_cuts = [c * 2 * pw for c in range(1, fcols)]
    h_cuts = [r * ph for r in range(1, frows)]

    num_sheets = total // pages_per_sheet

    print(f"Folios/sig : {num_folios} ({pages_per_sheet} pages/sheet, {fcols}×{frows} grid)")
    print(f"Pages      : {total} ({num_sheets} sheet(s))")
    print(f"Page size  : {pw:.1f} × {ph:.1f} pt  ({pw/72:.2f}″ × {ph/72:.2f}″)")
    print(f"Sheet size : {sheet_w:.1f} × {sheet_h:.1f} pt  ({sheet_w/72:.2f}″ × {sheet_h/72:.2f}″)")

    out = Pdf.new()

    # Convert every source page to a Form XObject (once)
    xobjs = []
    for i in range(total):
        xobj, _ = page_to_xobject(out, src, i)
        xobjs.append(xobj)

    crop = crop_marks_stream(sheet_w, sheet_h, v_cuts, h_cuts)

    # Offset correction for non-zero mediabox origins
    dx, dy = -x0, -y0

    for s in range(num_sheets):
        base = s * pages_per_sheet
        p = xobjs[base : base + pages_per_sheet]

        front_placements = []
        back_placements = []

        for f in range(num_folios):
            gc = f % fcols           # grid column of this folio
            gr = f // fcols          # grid row of this folio
            fb = f * 4               # base index within this sheet's pages

            # Y position (PDF origin = bottom-left, row 0 = top)
            y_pos = (frows - 1 - gr) * ph

            # ── Side A (Front): page[fb+3] left, page[fb+0] right ──
            front_x = gc * 2 * pw
            front_placements.append((p[fb + 3], dx + front_x,      dy + y_pos))
            front_placements.append((p[fb + 0], dx + front_x + pw, dy + y_pos))

            # ── Side B (Back): page[fb+1] left, page[fb+2] right ──
            # Mirror columns horizontally for long-edge duplex
            back_gc = fcols - 1 - gc
            back_x = back_gc * 2 * pw
            back_placements.append((p[fb + 1], dx + back_x,      dy + y_pos))
            back_placements.append((p[fb + 2], dx + back_x + pw, dy + y_pos))

        out.pages.append(make_sheet(out, sheet_w, sheet_h, front_placements, crop))
        out.pages.append(make_sheet(out, sheet_w, sheet_h, back_placements, crop))

    out.save(args.output_file)
    print(f"\nDone → {args.output_file}")
    print(f"Output: {len(out.pages)} page(s) ({num_sheets} sheet(s), front + back)")


if __name__ == "__main__":
    main()
