#!/usr/bin/env python3
"""
Imposition for cut-and-stack bookbinding using pikepdf.

Each output sheet has a grid of pages per side arranged in folio pairs.
The --folios flag controls folios per signature (any even number >= 2).

Grid dimensions: (F/2 × sigs_per_sheet) rows × 4 columns.

  -f 2 →  8 pages/sig, 4 sigs/sheet, 4×4 grid
  -f 4 → 16 pages/sig, 2 sigs/sheet, 4×4 grid  [default]
  -f 6 → 24 pages/sig, 1 sig/sheet,  3×4 grid
  -f 8 → 32 pages/sig, 1 sig/sheet,  4×4 grid

Print duplex (long-edge flip), cut into strips/quarters, and stack
to form signatures.
"""

import argparse
import sys
from decimal import Decimal

import pikepdf
from pikepdf import Name, Array, Dictionary, Stream, Pdf

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Imposition for cut-and-stack bookbinding."
    )
    p.add_argument("input_file", help="Input manuscript PDF (one page = one book page)")
    p.add_argument("output_file", help="Output imposed PDF")
    p.add_argument(
        "-f", "--folios", type=int, default=4,
        help="Folios per signature (default: 4). Any even number >= 2. "
             "1 folio = 4 book pages."
    )
    p.add_argument(
        "--no-marks", action="store_true",
        help="Hide all crop marks, indicators, and crosshairs."
    )
    args = p.parse_args()
    if args.folios < 2 or args.folios % 2 != 0:
        p.error("folios must be an even number >= 2")
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


def crop_marks_stream(sheet_w, sheet_h, grid_cols, grid_rows, v_cuts, h_cuts, v_folds, h_folds):
    """Return content-stream bytes for crop marks.

    Crosshairs at cut-line intersections; small margin ticks on fold lines.
    """
    cell_w = sheet_w / grid_cols
    cell_h = sheet_h / grid_rows
    m = min(cell_w, cell_h) * 0.08   # crosshair length: 8% of smallest cell dim
    fm = m * 0.4                      # fold tick length (smaller)
    g = m * 0.06                      # gap from sheet edge
    ops = ["q", "0.5 0.5 0.5 RG", "0.25 w"]

    all_v = set(v_cuts) | set(v_folds)
    all_h = set(h_cuts) | set(h_folds)
    v_cut_set = set(v_cuts)
    h_cut_set = set(h_cuts)

    # ── Vertical lines: edge marks ──
    # Cut lines: marks at top and bottom edges
    # Fold lines: single mark at top center and bottom center only
    for cx in sorted(all_v):
        if cx in v_cut_set:
            ops.append(f"{cx:.2f} {sheet_h - g:.2f} m {cx:.2f} {sheet_h - g - m:.2f} l S")
            ops.append(f"{cx:.2f} {g:.2f} m {cx:.2f} {g + m:.2f} l S")

    # Fold: one tick at top-center and bottom-center of the sheet
    center_x = sheet_w / 2
    ops.append(f"{center_x:.2f} {sheet_h - g:.2f} m {center_x:.2f} {sheet_h - g - fm:.2f} l S")
    ops.append(f"{center_x:.2f} {g:.2f} m {center_x:.2f} {g + fm:.2f} l S")

    # ── Horizontal lines: edge marks ──
    # Signature-end cuts get a dashed line (- -); other cuts get a solid line.
    dash_gap = m * 0.25   # gap in dashed line
    dash_seg = m * 0.35   # dash segment length
    for cy in sorted(all_h):
        if cy in h_cut_set:
            # dashed line "- -" (end of signature) — left edge
            x0_l = g
            ops.append(f"{x0_l:.2f} {cy:.2f} m {x0_l + dash_seg:.2f} {cy:.2f} l S")
            ops.append(f"{x0_l + dash_seg + dash_gap:.2f} {cy:.2f} m {x0_l + 2*dash_seg + dash_gap:.2f} {cy:.2f} l S")
            # dashed line — right edge
            x0_r = sheet_w - g
            ops.append(f"{x0_r:.2f} {cy:.2f} m {x0_r - dash_seg:.2f} {cy:.2f} l S")
            ops.append(f"{x0_r - dash_seg - dash_gap:.2f} {cy:.2f} m {x0_r - 2*dash_seg - dash_gap:.2f} {cy:.2f} l S")
        else:
            # solid line (fold)
            ops.append(f"{g:.2f} {cy:.2f} m {g + fm:.2f} {cy:.2f} l S")
            ops.append(f"{sheet_w - g:.2f} {cy:.2f} m {sheet_w - g - fm:.2f} {cy:.2f} l S")

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
    sigs_per_sheet = max(1, 8 // F)    # signatures per sheet
    grid_rows = sigs_per_sheet * (F // 2)  # rows in output grid
    grid_cols = 4                      # always 2 folio-columns × 2 cells
    pages_per_sheet = sigs_per_sheet * P

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

    # Sheet geometry
    sheet_w = grid_cols * pw
    sheet_h = grid_rows * ph

    # Vertical: folio spines are folds (cols 1,3), cut between folio cols (col 2)
    v_cuts  = [2 * pw]
    v_folds = [pw, 3 * pw]

    # Horizontal: cut lines separate signatures, fold lines are within sigs
    rows_per_sig = F // 2
    h_cuts  = []
    h_folds = []
    for r in range(1, grid_rows):
        y = r * ph
        if r % rows_per_sig == 0:
            h_cuts.append(y)
        else:
            h_folds.append(y)

    num_sheets = total // pages_per_sheet

    print(f"Folios/sig : {F} ({P} pages/sig, {sigs_per_sheet} sig(s)/sheet)")
    print(f"Grid       : {grid_rows}×{grid_cols}")
    print(f"Pages      : {total} ({num_sheets} sheet(s))")
    print(f"Page size  : {pw:.1f} × {ph:.1f} pt  ({pw/72:.2f}″ × {ph/72:.2f}″)")
    print(f"Sheet size : {sheet_w:.1f} × {sheet_h:.1f} pt  ({sheet_w/72:.2f}″ × {sheet_h/72:.2f}″)")

    out = Pdf.new()

    # Convert every source page to a Form XObject (once)
    xobjs = []
    for i in range(total):
        xobj, _ = page_to_xobject(out, src, i)
        xobjs.append(xobj)

    crop = None if args.no_marks else crop_marks_stream(
        sheet_w, sheet_h, grid_cols, grid_rows, v_cuts, h_cuts, v_folds, h_folds
    )

    # Offset correction for non-zero mediabox origins
    dx, dy = -x0, -y0

    # ── Folio grid: grid_rows rows × 2 folio-columns ──
    # folio f → folio_row = f // 2, folio_col = f % 2
    # Each folio occupies cells [folio_col*2, folio_col*2+1] in its row.
    #
    # Signatures claim consecutive folios row-major:
    #   sig 0 → f0..f(F-1), sig 1 → f(F)..f(2F-1), etc.
    #
    # Page formulas (1-indexed, O = global_sig * P):
    #   ob_left(d)  = O + P - 2d
    #   ob_right(d) = O + 2d + 1
    #   rev_left(d) = O + 2d + 2
    #   rev_right(d)= O + P - 2d - 1
    #
    # Reverse mirror (long-edge duplex):
    #   Folio column mirrored: col 0 ↔ col 1. Row unchanged.

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
                y = (grid_rows - 1 - folio_row) * ph

                ob_placements.append((xobjs[ob_l], dx + left_col * pw,  dy + y))
                ob_placements.append((xobjs[ob_r], dx + right_col * pw, dy + y))

                # ── Reverse placement ──
                # Mirror folio column (left↔right) so the back of
                # the folio at col0 appears at col1 and vice versa.
                mirror_col = 1 - folio_col
                rev_left_col  = mirror_col * 2
                rev_right_col = mirror_col * 2 + 1
                rev_y = (grid_rows - 1 - folio_row) * ph

                rev_placements.append((xobjs[rev_l], dx + rev_left_col * pw,  dy + rev_y))
                rev_placements.append((xobjs[rev_r], dx + rev_right_col * pw, dy + rev_y))

        out.pages.append(make_sheet(out, sheet_w, sheet_h, ob_placements, crop))
        out.pages.append(make_sheet(out, sheet_w, sheet_h, rev_placements, crop))

    out.save(args.output_file)
    print(f"\nDone → {args.output_file}")
    print(f"Output: {len(out.pages)} page(s) ({num_sheets} sheet(s), obverse + reverse)")


if __name__ == "__main__":
    main()
