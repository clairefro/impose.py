#!/usr/bin/env python3
"""
Accordion imposition for manuscript PDFs using pikepdf.

This script lays out pages in sequence along the long edge of each printer sheet,
producing strips that can be folded accordion-style.
"""

import argparse
import math
import os
import re
import sys
from decimal import Decimal

import pikepdf
from pikepdf import Array, Dictionary, Name, Pdf, Stream


MM_TO_PT = 72.0 / 25.4
CM_TO_PT = 72.0 / 2.54
IN_TO_PT = 72.0

PAPER_PRESETS_MM = {
    "A5": (148.0, 210.0),
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "LETTER": (215.9, 279.4),
    "LEGAL": (215.9, 355.6),
    "TABLOID": (279.4, 431.8),
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _mm_pair_to_pt(size_mm):
    return size_mm[0] * MM_TO_PT, size_mm[1] * MM_TO_PT


def _parse_wh_spec(spec, default_unit="mm"):
    """Parse values like 148x210mm, 5x7in, 420x297 (default unit if missing)."""
    m = re.match(
        r"^\s*([0-9]*\.?[0-9]+)\s*[xX]\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z]+)?\s*$",
        spec,
    )
    if not m:
        raise ValueError(f"Invalid size format: {spec}")

    w = float(m.group(1))
    h = float(m.group(2))
    unit = (m.group(3) or default_unit).lower()

    if w <= 0 or h <= 0:
        raise ValueError(f"Size values must be > 0: {spec}")

    if unit == "mm":
        factor = MM_TO_PT
    elif unit == "cm":
        factor = CM_TO_PT
    elif unit == "in":
        factor = IN_TO_PT
    elif unit == "pt":
        factor = 1.0
    else:
        raise ValueError(f"Unsupported unit '{unit}' in: {spec}")

    return w * factor, h * factor


def parse_paper_size(spec):
    key = spec.strip().upper()
    if key in PAPER_PRESETS_MM:
        return _mm_pair_to_pt(PAPER_PRESETS_MM[key])
    return _parse_wh_spec(spec, default_unit="mm")


def parse_page_size(spec):
    return _parse_wh_spec(spec, default_unit="mm")


def _mm_label_from_pt(value_pt):
    value_mm = value_pt / MM_TO_PT
    label = f"{value_mm:.1f}".rstrip("0").rstrip(".")
    return label.replace(".", "p")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Impose a manuscript PDF into accordion-fold strips."
    )
    p.add_argument("input_file", help="Input manuscript PDF (1 page = 1 book page)")
    p.add_argument(
        "output_file",
        nargs="?",
        default=None,
            help="Output PDF (default: <input>_accordion_<w>x<h>mm.pdf)",
    )
    p.add_argument(
        "--paper-size",
        default="A4",
        help=(
            "Printer paper size. Named sizes: A5, A4, A3, Letter, Legal, Tabloid; "
            "or custom WxH with unit (mm/cm/in/pt), e.g. 420x297mm"
        ),
    )
    p.add_argument(
        "--page-size",
        required=True,
        help="Target accordion page size WxH with unit (mm/cm/in/pt), e.g. 105x148mm",
    )
    p.add_argument(
        "--glue-margin-cm",
        type=float,
        default=1.0,
        help="Blank margin at both strip ends for gluing (default: 1.0 cm)",
    )
    p.add_argument(
        "--blank-front",
        type=int,
        default=0,
        help="Number of blank pages to prepend before manuscript pages.",
    )
    p.add_argument(
        "--blank-back",
        type=int,
        default=0,
        help="Number of blank pages to append after manuscript pages.",
    )
    p.add_argument(
        "-m",
        "--no-marks",
        action="store_true",
        help="Hide faint fold-line crosshair marks.",
    )

    args = p.parse_args()

    if args.glue_margin_cm < 0:
        p.error("--glue-margin-cm must be >= 0")
    if args.blank_front < 0:
        p.error("--blank-front must be >= 0")
    if args.blank_back < 0:
        p.error("--blank-back must be >= 0")

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
    if res is None:
        # Inherited resources: walk up page tree.
        node = page.obj.get(Name.Parent)
        while node is not None and res is None:
            res = node.get(Name.Resources)
            node = node.get(Name.Parent)
    if res is not None:
        res = src_pdf.make_indirect(res)
        xobj[Name.Resources] = out_pdf.copy_foreign(res)

    return xobj, bbox


def fold_crosshair_stream(sheet_w, strip_ys, strip_h, fold_xs, panel_w, panel_h):
    """Return faint crosshairs at each fold line for each strip row."""
    if not fold_xs:
        return None

    m = min(panel_w, panel_h) * 0.06
    ops = ["q", "0.78 0.78 0.78 RG", "0.2 w"]

    for strip_y in strip_ys:
        y_bot = strip_y
        y_top = strip_y + strip_h

        for x in fold_xs:
            ops.append(f"{x:.2f} {y_bot - m:.2f} m {x:.2f} {y_bot + m:.2f} l S")
            ops.append(f"{x - m:.2f} {y_bot:.2f} m {x + m:.2f} {y_bot:.2f} l S")

            ops.append(f"{x:.2f} {y_top - m:.2f} m {x:.2f} {y_top + m:.2f} l S")
            ops.append(f"{x - m:.2f} {y_top:.2f} m {x + m:.2f} {y_top:.2f} l S")

    ops.append("Q")
    return "\n".join(ops).encode()


def make_sheet(out_pdf, sheet_w, sheet_h, placements, marks_bytes):
    """
    Build one output page (one printer sheet).

    placements: [(xobj, tx, ty, sx, sy), ...]
    """
    xobj_dict = Dictionary()
    content_parts = []

    for i, (xobj, tx, ty, sx, sy) in enumerate(placements):
        xname = f"P{i}"
        xobj_dict[Name(f"/{xname}")] = out_pdf.make_indirect(xobj)
        content_parts.append(
            f"q {sx:.8f} 0 0 {sy:.8f} {tx:.8f} {ty:.8f} cm /{xname} Do Q"
        )

    content = "\n".join(content_parts).encode()
    if marks_bytes:
        content += b"\n" + marks_bytes

    page_dict = Dictionary(
        {
            "/Type": Name.Page,
            "/MediaBox": Array([0, 0, Decimal(str(sheet_w)), Decimal(str(sheet_h))]),
            "/Resources": Dictionary({"/XObject": xobj_dict}),
            "/Contents": Stream(out_pdf, content),
        }
    )
    return pikepdf.Page(out_pdf.make_indirect(page_dict))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    paper_w, paper_h = parse_paper_size(args.paper_size)
    target_page_w, target_page_h = parse_page_size(args.page_size)
    glue_margin = args.glue_margin_cm * CM_TO_PT

    if args.output_file is None:
        base, _ = os.path.splitext(args.input_file)
        w_label = _mm_label_from_pt(target_page_w)
        h_label = _mm_label_from_pt(target_page_h)
        args.output_file = f"{base}_accordion_{w_label}x{h_label}mm.pdf"

    # Force landscape so pages run along the paper's long side.
    sheet_w = max(paper_w, paper_h)
    sheet_h = min(paper_w, paper_h)

    usable_w = sheet_w - (2 * glue_margin)
    if usable_w <= 0:
        print("Error: glue margins consume all horizontal space.", file=sys.stderr)
        sys.exit(2)

    if target_page_h > sheet_h:
        print(
            (
                "Error: target page height does not fit on selected paper in long-side "
                f"layout ({target_page_h / MM_TO_PT:.1f} mm > {sheet_h / MM_TO_PT:.1f} mm)."
            ),
            file=sys.stderr,
        )
        sys.exit(2)

    rows_per_sheet = int(sheet_h // target_page_h)
    if rows_per_sheet < 1:
        print(
            "Error: paper/page settings allow fewer than 1 strip row per sheet.",
            file=sys.stderr,
        )
        sys.exit(2)

    panels_per_sheet = int(usable_w // target_page_w)
    if panels_per_sheet < 2:
        print(
            "Error: paper/page/margin settings allow fewer than 2 accordion panels per sheet.",
            file=sys.stderr,
        )
        sys.exit(2)

    pages_per_sheet = panels_per_sheet * rows_per_sheet

    src = Pdf.open(args.input_file)
    source_pages = len(src.pages)
    page_slots = (
        [None] * args.blank_front
        + list(range(source_pages))
        + [None] * args.blank_back
    )
    total_pages = len(page_slots)

    if total_pages == 0:
        print("Error: no pages to impose (input is empty and no blank pages requested).", file=sys.stderr)
        sys.exit(2)

    num_sheets = math.ceil(total_pages / pages_per_sheet)

    y_offset = (sheet_h - (rows_per_sheet * target_page_h)) / 2.0
    strip_ys = [
        y_offset + ((rows_per_sheet - 1 - row) * target_page_h)
        for row in range(rows_per_sheet)
    ]
    fold_xs = [glue_margin + (i * target_page_w) for i in range(1, panels_per_sheet)]
    marks = None if args.no_marks else fold_crosshair_stream(
        sheet_w, strip_ys, target_page_h, fold_xs, target_page_w, target_page_h
    )

    print("Mode       : accordion strip")
    print(f"Paper size : {sheet_w / MM_TO_PT:.1f} x {sheet_h / MM_TO_PT:.1f} mm (landscape)")
    print(f"Page size  : {target_page_w / MM_TO_PT:.1f} x {target_page_h / MM_TO_PT:.1f} mm")
    print(f"Glue margin: {args.glue_margin_cm:.2f} cm each end")
    print(f"Rows       : {rows_per_sheet} strip row(s) per sheet")
    print(f"Panels     : {panels_per_sheet} per row")
    print(f"Capacity   : {pages_per_sheet} page(s) per sheet")
    print(f"Input pages: {source_pages}")
    print(f"Blanks     : front={args.blank_front}, back={args.blank_back}")
    print(f"Total pages: {total_pages}")
    print(f"Sheets     : {num_sheets}")

    out = Pdf.new()

    # Convert source pages once for reuse.
    xobjs = []
    bboxes = []
    for i in range(source_pages):
        xobj, bbox = page_to_xobject(out, src, i)
        xobjs.append(xobj)
        bboxes.append(bbox)

    for sheet_idx in range(num_sheets):
        placements = []

        for row_idx, strip_y in enumerate(strip_ys):
            for panel_idx in range(panels_per_sheet):
                local_idx = row_idx * panels_per_sheet + panel_idx
                page_idx = sheet_idx * pages_per_sheet + local_idx
                if page_idx >= total_pages:
                    continue

                src_idx = page_slots[page_idx]
                if src_idx is None:
                    continue

                bbox = bboxes[src_idx]
                src_w = bbox[2] - bbox[0]
                src_h = bbox[3] - bbox[1]
                if src_w <= 0 or src_h <= 0:
                    continue

                # Preserve aspect ratio and center content within the target panel.
                scale = min(target_page_w / src_w, target_page_h / src_h)
                draw_w = src_w * scale
                draw_h = src_h * scale

                panel_x = glue_margin + (panel_idx * target_page_w)
                tx = panel_x + (target_page_w - draw_w) / 2.0 - (bbox[0] * scale)
                ty = strip_y + (target_page_h - draw_h) / 2.0 - (bbox[1] * scale)

                placements.append((xobjs[src_idx], tx, ty, scale, scale))

        out.pages.append(make_sheet(out, sheet_w, sheet_h, placements, marks))

    out.save(args.output_file)
    print(f"\nDone -> {args.output_file}")
    print(f"Output: {len(out.pages)} page(s)")


if __name__ == "__main__":
    main()
