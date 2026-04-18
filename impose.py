#!/usr/bin/env python3
"""
Sextodecimo (16mo) imposition for cut-and-stack bookbinding using pikepdf.

Each sheet has a 4×4 grid of pages per side (16 cells obverse, 16 reverse).
8 folios per side, each folio = 1 row × 2 cells.

The --folios flag controls how many folios per signature (2, 4, or 8).
  -f 2 →  8 pages/sig, 4 sigs/sheet
  -f 4 → 16 pages/sig, 2 sigs/sheet  [default]
  -f 8 → 32 pages/sig, 1 sig/sheet

Print duplex (long-edge flip), cut into strips/quarters, and stack
to form signatures.
"""

import argparse
import sys
from decimal import Decimal

import pikepdf
from pikepdf import Name, Array, Dictionary, Stream, Pdf

VALID_FOLIOS = {2, 4, 8}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Sextodecimo (4×4) imposition for cut-and-stack bookbinding."
    )
    p.add_argument("input_file", help="Input manuscript PDF (one page = one book page)")
    p.add_argument("output_file", help="Output imposed PDF")
    p.add_argument(
        "-f", "--folios", type=int, default=4,
        help="Folios per signature (default: 4). Allowed: 2, 4, 8. "
             "1 folio = 4 book pages."
    )
    args = p.parse_args()
    if args.folios not in VALID_FOLIOS:
        p.error(f"folios must be one of {sorted(VALID_FOLIOS)}")
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


def crop_marks_stream(sheet_w, sheet_h, v_cuts, h_cuts, v_folds, h_folds):
    """Return content-stream bytes for crop marks.

    Crosshairs at cut-line intersections; small margin ticks on fold lines.
    """
    cell_w = sheet_w / 4
    cell_h = sheet_h / 4
    m = min(cell_w, cell_h) * 0.08   # crosshair length: 8% of smallest cell dim
    fm = m * 0.4                      # fold tick length (smaller)
    g = m * 0.06                      # gap from sheet edge
    ops = ["q", "0.5 0.5 0.5 RG", "0.25 w"]

    all_v = set(v_cuts) | set(v_folds)
    all_h = set(h_cuts) | set(h_folds)
    v_cut_set = set(v_cuts)
    h_cut_set = set(h_cuts)

    # ── Vertical lines: edge marks ──
    for cx in sorted(all_v):
        t = m if cx in v_cut_set else fm
        ops.append(f"{cx:.2f} {sheet_h - g:.2f} m {cx:.2f} {sheet_h - g - t:.2f} l S")
        ops.append(f"{cx:.2f} {g:.2f} m {cx:.2f} {g + t:.2f} l S")

    # ── Horizontal lines: edge marks ──
    for cy in sorted(all_h):
        t = m if cy in h_cut_set else fm
        ops.append(f"{g:.2f} {cy:.2f} m {g + t:.2f} {cy:.2f} l S")
        ops.append(f"{sheet_w - g:.2f} {cy:.2f} m {sheet_w - g - t:.2f} {cy:.2f} l S")

    # ── Crosshairs only where TWO cut lines intersect ──
    for cx in v_cuts:
        for cy in h_cuts:
            ops.append(f"{cx:.2f} {cy - m:.2f} m {cx:.2f} {cy + m:.2f} l S")
            ops.append(f"{cx - m:.2f} {cy:.2f} m {cx + m:.2f} {cy:.2f} l S")

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
    F = args.folios                    # folios per signature
    P = 4 * F                          # pages per signature
    sigs_per_sheet = 8 // F            # signatures per sheet
    pages_per_sheet = 32               # always 4×4×2 sides

    src = Pdf.open(args.input_file)
    total = len(src.pages)

    # Page dimensions from first page
    mb = src.pages[0].mediabox
    x0, y0 = float(mb[0]), float(mb[1])
    pw = float(mb[2]) - x0   # page width
    ph = float(mb[3]) - y0   # page height

    # Pad to a multiple of 32 with blank pages
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

    # Sheet geometry: 4×4 grid of pages per side
    sheet_w = 4 * pw
    sheet_h = 4 * ph

    # Vertical: folio spines are folds (cols 1,3), cut between folio cols (col 2)
    v_cuts  = [2 * pw]
    v_folds = [pw, 3 * pw]

    # Horizontal: cut lines separate signatures, fold lines are within sigs
    rows_per_sig = F // 2
    h_cuts  = []
    h_folds = []
    for r in range(1, 4):
        y = r * ph
        if r % rows_per_sig == 0 and r < 4:
            h_cuts.append(y)
        else:
            h_folds.append(y)

    num_sheets = total // pages_per_sheet

    print(f"Folios/sig : {F} ({P} pages/sig, {sigs_per_sheet} sig(s)/sheet)")
    print(f"Pages      : {total} ({num_sheets} sheet(s))")
    print(f"Page size  : {pw:.1f} × {ph:.1f} pt  ({pw/72:.2f}″ × {ph/72:.2f}″)")
    print(f"Sheet size : {sheet_w:.1f} × {sheet_h:.1f} pt  ({sheet_w/72:.2f}″ × {sheet_h/72:.2f}″)")

    out = Pdf.new()

    # Convert every source page to a Form XObject (once)
    xobjs = []
    for i in range(total):
        xobj, _ = page_to_xobject(out, src, i)
        xobjs.append(xobj)

    crop = crop_marks_stream(sheet_w, sheet_h, v_cuts, h_cuts, v_folds, h_folds)

    # Offset correction for non-zero mediabox origins
    dx, dy = -x0, -y0

    # ── Folio grid: 4 rows × 2 folio-columns (8 folios per side) ──
    # folio f → folio_row = f // 2, folio_col = f % 2
    # Each folio occupies cells [folio_col*2, folio_col*2+1] in its row.
    #
    # Signatures claim consecutive folios row-major:
    #   sig 0 → f0..f(F-1), sig 1 → f(F)..f(2F-1), etc.
    #
    # Page formulas (1-indexed, O = global_sig_index * P):
    #   ob_left(d)  = O + P - 2d
    #   ob_right(d) = O + 2d + 1
    #   rev_left(d) = O + P//2 - 2d
    #   rev_right(d)= O + P//2 + 2d + 1
    #
    # Reverse mirror (long-edge duplex):
    #   mirror_col = 1 - folio_col
    #   mirror_local_row = (rows_per_sig - 1) - local_row
    #   mirror_folio_row = sig_start_row + mirror_local_row

    rows_per_sig = F // 2   # folio rows per signature (2 folios per row)

    for sheet_idx in range(num_sheets):
        ob_placements = []
        rev_placements = []

        for local_sig in range(sigs_per_sheet):
            global_sig = sheet_idx * sigs_per_sheet + local_sig
            O = global_sig * P          # 1-indexed offset base

            sig_start_folio = local_sig * F
            sig_start_row = sig_start_folio // 2

            for d in range(F):
                global_folio = sig_start_folio + d
                folio_row = global_folio // 2
                folio_col = global_folio % 2

                # 1-indexed page numbers → 0-indexed
                ob_l  = (O + P - 2 * d) - 1
                ob_r  = (O + 2 * d + 1) - 1
                rev_l = (O + 2 * d + 2) - 1
                rev_r = (O + P - 2 * d - 1) - 1

                # ── Obverse placement ──
                left_col  = folio_col * 2
                right_col = folio_col * 2 + 1
                y = (3 - folio_row) * ph

                ob_placements.append((xobjs[ob_l], dx + left_col * pw,  dy + y))
                ob_placements.append((xobjs[ob_r], dx + right_col * pw, dy + y))

                # ── Reverse placement ──
                # Mirror folio column (left↔right) so the back of
                # the folio at col0 appears at col1 and vice versa.
                mirror_col = 1 - folio_col
                rev_left_col  = mirror_col * 2
                rev_right_col = mirror_col * 2 + 1
                rev_y = (3 - folio_row) * ph

                rev_placements.append((xobjs[rev_l], dx + rev_left_col * pw,  dy + rev_y))
                rev_placements.append((xobjs[rev_r], dx + rev_right_col * pw, dy + rev_y))

        out.pages.append(make_sheet(out, sheet_w, sheet_h, ob_placements, crop))
        out.pages.append(make_sheet(out, sheet_w, sheet_h, rev_placements, crop))

    out.save(args.output_file)
    print(f"\nDone → {args.output_file}")
    print(f"Output: {len(out.pages)} page(s) ({num_sheets} sheet(s), obverse + reverse)")


if __name__ == "__main__":
    main()
