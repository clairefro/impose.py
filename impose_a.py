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

PAGE_PRESETS_MM = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
    "A7": (74.0, 105.0),
    "A8": (52.0, 74.0),
    "A9": (37.0, 52.0),
    "A10": (26.0, 37.0),
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


def get_paper_size_label(spec):
    """Return preset name (lowercase) if spec is a named size, else dimensions."""
    key = spec.strip().upper()
    if key in PAPER_PRESETS_MM:
        return key.lower()
    # Custom size: return as dimensions
    w, h = _parse_wh_spec(spec, default_unit="mm")
    w_mm = _mm_label_from_pt(w)
    h_mm = _mm_label_from_pt(h)
    return f"{w_mm}x{h_mm}"


def parse_page_size(spec):
    key = spec.strip().upper()
    if key in PAGE_PRESETS_MM:
        return _mm_pair_to_pt(PAGE_PRESETS_MM[key])
    return _parse_wh_spec(spec, default_unit="mm")


def get_page_size_label(spec):
    """Return preset name (lowercase) if spec is a named size, else dimensions."""
    key = spec.strip().upper()
    if key in PAGE_PRESETS_MM:
        return key.lower()
    # Custom size: return as dimensions
    w, h = _parse_wh_spec(spec, default_unit="mm")
    w_mm = _mm_label_from_pt(w)
    h_mm = _mm_label_from_pt(h)
    return f"{w_mm}x{h_mm}"


def _mm_label_from_pt(value_pt):
    value_mm = value_pt / MM_TO_PT
    label = f"{value_mm:.1f}".rstrip("0").rstrip(".")
    return label.replace(".", "p")


def _num_label(value):
    label = f"{value:.2f}".rstrip("0").rstrip(".")
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
            help=(
                "Output PDF (default includes all settings, "
                "e.g. <input>_acc_pap297x210_pg52x74_gl1_xh2_bf1_bb1_dup0_mrk1_fcx1.pdf)"
            ),
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
        default="A8",
        help=(
            "Target accordion page size. Named sizes: A3, A4, A5, A6, A7, A8, A9, A10; "
            "or custom WxH with unit (mm/cm/in/pt), e.g. 105x148mm (default: A8)"
        ),
    )
    p.add_argument(
        "--glue-margin-cm",
        type=float,
        default=1.0,
        help="Blank margin at both strip ends for gluing (default: 1.0 cm)",
    )
    p.add_argument(
        "--fold-crosshair-leg-pt",
        type=float,
        default=8.0,
        help="Fold crosshair horizontal leg length in points (default: 8.0).",
    )
    p.add_argument(
        "--blank-front",
        type=int,
        default=1,
        help="Number of blank pages to prepend before manuscript pages (default: 1).",
    )
    p.add_argument(
        "--blank-back",
        type=int,
        default=1,
        help="Number of blank pages to append after manuscript pages (default: 1).",
    )
    p.add_argument(
        "-m",
        "--no-marks",
        action="store_true",
        help="Hide all marks (both strip cut lines and fold crosshairs).",
    )
    p.add_argument(
        "--no-fold-crosshairs",
        action="store_true",
        help="Hide fold crosshairs but keep strip cut lines.",
    )
    p.add_argument(
        "--duplex",
        action="store_true",
        help=(
            "Generate front/back pages for duplex printing, long-edge flip (default). "
            "Back content is rotated 180° to appear right-side-up after flipping."
        ),
    )
    p.add_argument(
        "--duplex-short",
        action="store_true",
        help=(
            "Generate front/back pages for duplex printing, short-edge flip. "
            "Back content is mirrored horizontally only (no rotation). "
            "Implies --duplex."
        ),
    )

    args = p.parse_args()

    if args.glue_margin_cm < 0:
        p.error("--glue-margin-cm must be >= 0")
    if args.fold_crosshair_leg_pt <= 0:
        p.error("--fold-crosshair-leg-pt must be > 0")
    if args.blank_front < 0:
        p.error("--blank-front must be >= 0")
    if args.blank_back < 0:
        p.error("--blank-back must be >= 0")
    if args.duplex_short:
        args.duplex = True

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


def fold_crosshair_stream(
    sheet_w,
    strip_ys,
    strip_h,
    fold_xs,
    panel_w,
    panel_h,
    include_fold_crosshairs,
    fold_crosshair_leg_pt,
    draw_glue_lines=True,
    draw_left_cut_line=True,
):
    """Return strip cut lines and optional fold crosshairs for each strip row."""
    if not fold_xs:
        return None

    # Keep guides visible on tiny formats (e.g., A10) by enforcing minimum leg lengths.
    m_h = max(1.2, fold_crosshair_leg_pt)
    m_v = max(0.35, m_h * 0.2)

    # Hairline strokes can disappear on some printers/PDF viewers at small scales.
    ops = ["q", "0.65 0.65 0.65 RG", "0.2 w"]

    strip_x0 = min(fold_xs) - panel_w
    strip_x1 = strip_x0 + panel_w * (len(fold_xs) + 1)
    flap_w = strip_x0
    flap_left_x = max(0.0, strip_x0 - flap_w)
    flap_right_x = min(sheet_w, strip_x1 + flap_w)



    for strip_y in strip_ys:
        y_bot = strip_y
        y_top = strip_y + strip_h

        # Solid thin cut guides for the strip boundaries.
        ops.append(f"{strip_x0:.2f} {y_bot:.2f} m {strip_x1:.2f} {y_bot:.2f} l S")
        ops.append(f"{strip_x0:.2f} {y_top:.2f} m {strip_x1:.2f} {y_top:.2f} l S")

        # Solid cut line on LEFT side (strip_x0), unless suppressed.
        if draw_left_cut_line:
            ops.append(f"{strip_x0:.2f} {y_bot:.2f} m {strip_x0:.2f} {y_top:.2f} l S")

    # Draw glue margin crosshairs (above and below the topmost and bottommost cut lines)
    if draw_glue_lines:
        # Above the topmost cut line
        glue_x = strip_x0  # left glue margin
        glue_x_r = strip_x1 + (flap_right_x - strip_x1)  # right glue margin (outer edge)
        crosshair_len = max(2.0, m_h)
        # Above top
        ops.append(f"{glue_x_r:.2f} {strip_ys[0] + strip_h + crosshair_len:.2f} m {glue_x_r:.2f} {strip_ys[0] + strip_h:.2f} l S")
        # Below bottom
        ops.append(f"{glue_x_r:.2f} {strip_ys[-1] - crosshair_len:.2f} m {glue_x_r:.2f} {strip_ys[-1]:.2f} l S")

    # Draw fold crosshairs as before
    if include_fold_crosshairs:
        for strip_y in strip_ys:
            y_bot = strip_y
            y_top = strip_y + strip_h
            for x in fold_xs:
                # Vertical segments only; horizontal line comes from intersection with cut lines.
                ops.append(f"{x:.2f} {y_bot - m_v:.2f} m {x:.2f} {y_bot + m_v:.2f} l S")
                ops.append(f"{x:.2f} {y_top - m_v:.2f} m {x:.2f} {y_top + m_v:.2f} l S")

    ops.append("Q")
    return "\n".join(ops).encode()


def make_sheet(out_pdf, sheet_w, sheet_h, placements, marks_bytes):
    """
    Build one output page (one printer sheet).

    placements: [(xobj, tx, ty, sx, sy, rotate180), ...]
    rotate180: if True, rotate content 180° in place (for duplex back side)
    """
    xobj_dict = Dictionary()
    content_parts = []

    for i, (xobj, tx, ty, sx, sy, rotate180) in enumerate(placements):
        xname = f"P{i}"
        xobj_dict[Name(f"/{xname}")] = out_pdf.make_indirect(xobj)
        if rotate180:
            # 180° rotation: [-sx 0 0 -sy] with translation adjusted so content
            # stays within its panel cell (translate to far corner then flip).
            bbox = xobj[Name.BBox]
            bx0, by0, bx1, by1 = (float(bbox[j]) for j in range(4))
            bw = (bx1 - bx0) * sx
            bh = (by1 - by0) * sy
            e = tx + bw + bx0 * sx
            f = ty + bh + by0 * sy
            content_parts.append(
                f"q {-sx:.8f} 0 0 {-sy:.8f} {e:.8f} {f:.8f} cm /{xname} Do Q"
            )
        else:
            content_parts.append(
                f"q {sx:.8f} 0 0 {sy:.8f} {tx:.8f} {ty:.8f} cm /{xname} Do Q"
            )

    content = "\n".join(content_parts).encode()
    if marks_bytes:
        content += b"\n" + marks_bytes

    # Ensure font resource for glue label
    resources = Dictionary({"/XObject": xobj_dict})
    # Add Helvetica font as /F1 if glue label is present
    if b"/F1" in content:
        font_dict = Dictionary({"/F1": Dictionary({"/Type": Name.Font, "/Subtype": Name.Type1, "/BaseFont": Name.Helvetica})})
        resources[Name("/Font")] = font_dict

    page_dict = Dictionary(
        {
            "/Type": Name.Page,
            "/MediaBox": Array([0, 0, Decimal(str(sheet_w)), Decimal(str(sheet_h))]),
            "/Resources": resources,
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
        paper_label = get_paper_size_label(args.paper_size)
        page_label = get_page_size_label(args.page_size)
        glue_cm = _num_label(args.glue_margin_cm)
        cross_pt = _num_label(args.fold_crosshair_leg_pt)
        args.output_file = (
            f"{base}_acc"
            f"_paper-{paper_label}"
            f"_pg-{page_label}"
            f"_gl-{glue_cm}"
            + (f"_xh-{cross_pt}" if not args.no_fold_crosshairs else "")
            + (f"_bf-{args.blank_front}" if args.blank_front != 1 else "")
            + (f"_bb-{args.blank_back}" if args.blank_back != 1 else "")
            + ("_duplex-lng" if args.duplex and not args.duplex_short else
               "_duplex-sht" if args.duplex_short else "")
            + ("_nomark" if args.no_marks else "")
            + ("_noxh" if args.no_fold_crosshairs else "")
            + ".pdf"
        )

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

    pages_per_side = panels_per_sheet * rows_per_sheet

    src = Pdf.open(args.input_file)
    source_pages = len(src.pages)

    if args.duplex:
        # Source pages are split: first half on front, second half on back.
        # Short-edge duplex keeps blank offsets aligned by slot index.
        # Long-edge duplex shifts back-side leading blanks to the opposite edge.
        n_front_content = math.ceil(source_pages / 2)
        n_back_content = source_pages - n_front_content
        min_side_len = args.blank_front + max(n_front_content, n_back_content) + args.blank_back
        num_sheets = max(1, math.ceil(min_side_len / pages_per_side)) if (source_pages + args.blank_front + args.blank_back) > 0 else 0
        total_side_pages = num_sheets * pages_per_side
        front_slots = (
            [None] * args.blank_front
            + list(range(n_front_content))
            + [None] * (total_side_pages - args.blank_front - n_front_content)
        )
        back_leading_blanks = args.blank_front if args.duplex_short else args.blank_back
        back_slots = (
            [None] * back_leading_blanks
            + list(range(n_front_content, source_pages))
            + [None] * (total_side_pages - back_leading_blanks - n_back_content)
        )
        back_blank_rule = (
            "short-edge: align with front leading blanks"
            if args.duplex_short
            else "long-edge: use front trailing blanks on back leading edge"
        )
        total_pages = total_side_pages
    else:
        front_slots = (
            [None] * args.blank_front
            + list(range(source_pages))
            + [None] * args.blank_back
        )
        back_slots = []
        back_leading_blanks = 0
        back_blank_rule = "single-sided"
        total_pages = len(front_slots)
        num_sheets = math.ceil(total_pages / pages_per_side) if total_pages > 0 else 0

    if total_pages == 0:
        print("Error: no pages to impose (input is empty and no blank pages requested).", file=sys.stderr)
        sys.exit(2)

    y_offset = (sheet_h - (rows_per_sheet * target_page_h)) / 2.0
    strip_ys = [
        y_offset + ((rows_per_sheet - 1 - row) * target_page_h)
        for row in range(rows_per_sheet)
    ]
    fold_xs = [glue_margin + (i * target_page_w) for i in range(1, panels_per_sheet)]
    # Precompute marks for front and back (if duplex), else just one.
    marks = None
    marks_back = None
    if not args.no_marks:
        marks = fold_crosshair_stream(
            sheet_w,
            strip_ys,
            target_page_h,
            fold_xs,
            target_page_w,
            target_page_h,
            include_fold_crosshairs=(not args.no_fold_crosshairs),
            fold_crosshair_leg_pt=args.fold_crosshair_leg_pt,
            draw_glue_lines=True,
            draw_left_cut_line=True,
        )
        if args.duplex:
            marks_back = fold_crosshair_stream(
                sheet_w,
                strip_ys,
                target_page_h,
                fold_xs,
                target_page_w,
                target_page_h,
                include_fold_crosshairs=(not args.no_fold_crosshairs),
                fold_crosshair_leg_pt=args.fold_crosshair_leg_pt,
                draw_glue_lines=False,
                draw_left_cut_line=False,
            )

    print("Mode       : accordion strip")
    print(f"Paper size : {sheet_w / MM_TO_PT:.1f} x {sheet_h / MM_TO_PT:.1f} mm (landscape)")
    print(f"Page size  : {target_page_w / MM_TO_PT:.1f} x {target_page_h / MM_TO_PT:.1f} mm")
    print(f"Glue margin: {args.glue_margin_cm:.2f} cm each end")
    duplex_mode = ("long-edge" if not args.duplex_short else "short-edge") if args.duplex else "no"
    print(f"Duplex     : {duplex_mode}")
    print(f"Rows       : {rows_per_sheet} strip row(s) per sheet")
    print(f"Panels     : {panels_per_sheet} per row")
    if args.duplex:
        print(
            f"Capacity   : {pages_per_side} page(s)/side, "
            f"{pages_per_side * 2} page(s)/sheet"
        )
    else:
        print(f"Capacity   : {pages_per_side} page(s) per sheet")
    print(f"Input pages: {source_pages}")
    print(f"Blanks     : front={args.blank_front}, back={args.blank_back}")
    if args.duplex:
        print(f"Total pages: {total_pages} per side ({total_pages * 2} front+back)")
        print(
            "Debug      : "
            f"back-leading-blanks={back_leading_blanks} ({back_blank_rule})"
        )
    else:
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

    def build_side_placements(slots, sheet_idx, rotate180, reverse_rows=False):
        placements = []
        side_base = sheet_idx * pages_per_side

        for row_idx, strip_y in enumerate(strip_ys):
            slot_row_idx = (rows_per_sheet - 1 - row_idx) if reverse_rows else row_idx
            for panel_idx in range(panels_per_sheet):
                local_idx = slot_row_idx * panels_per_sheet + panel_idx
                page_idx = side_base + local_idx
                if page_idx >= len(slots):
                    continue

                src_idx = slots[page_idx]
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

                placements.append((xobjs[src_idx], tx, ty, scale, scale, rotate180))

        return placements

    for sheet_idx in range(num_sheets):
        # In duplex mode, only put glue guides on front (odd) sheets
        if args.duplex:
            front = build_side_placements(front_slots, sheet_idx, rotate180=False)
            out.pages.append(make_sheet(out, sheet_w, sheet_h, front, marks))

            back = build_side_placements(
                back_slots,
                sheet_idx,
                rotate180=not args.duplex_short,
                reverse_rows=(not args.duplex_short),
            )
            out.pages.append(make_sheet(out, sheet_w, sheet_h, back, marks_back))
        else:
            # Single-sided: always show glue guides
            front = build_side_placements(front_slots, sheet_idx, rotate180=False)
            out.pages.append(make_sheet(out, sheet_w, sheet_h, front, marks))

    out.save(args.output_file)
    print(f"\nDone -> {args.output_file}")
    if args.duplex:
        print(
            f"Output: {len(out.pages)} page(s) "
            f"({num_sheets} sheet(s), obverse + reverse)"
        )
    else:
        print(f"Output: {len(out.pages)} page(s)")


if __name__ == "__main__":
    main()
