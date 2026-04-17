#!/usr/bin/env python3
"""
impose.py - Sexidecimo page imposition tool

Usage:
    impose.py -f <folios_per_sig> -p <num_pages>

Args:
    -f  folios per signature (2, 4, or 8)
    -p  total manuscript pages (must be divisible by 4*f)

Output:
    Obverse and reverse sheet layouts showing manuscript page numbers
    in each cell position.

Cell layout per side (0-indexed):
    Obverse: cells  0-15  (4x4 grid, 2 cells per folio, 2 folios per row)
    Reverse: cells 16-31  (mirrored left-right due to long-side duplex flip)

Folio layout:
    [f_left: bottom, top] | [f_right: bottom, top]

Page formula for signature at depth d, with P pages per sig, offset O:
    ob_left  = O + P - 2d        (bottom of sig if d==0)
    ob_right = O + 2d + 1        (top of sig if d==0)
    rev_left = O + P//2 - 2d
    rev_right= O + P//2 + 2d + 1

Reverse physical layout mirrors obverse left<->right due to long-side flip,
so reverse of f0 appears in physical right position and vice versa.
"""

import argparse
import math


def compute_sheet(folios_per_sig: int, num_pages: int):
    """
    Compute obverse and reverse cell->manuscript_page mappings.

    Returns:
        obverse: list of 16 manuscript page numbers (cells 0-15), 0 = blank
        reverse: list of 16 manuscript page numbers (cells 16-31), 0 = blank
    """
    P = 4 * folios_per_sig          # pages per signature
    num_sigs = math.ceil(num_pages / P)
    total_pages = num_sigs * P      # padded page count (blank pages at end)

    obverse = [0] * 16
    reverse = [0] * 16

    for sig_idx in range(num_sigs):
        O = sig_idx * P             # page offset for this signature

        for depth in range(folios_per_sig):
            # folio index within the sheet (row-major across obverse grid)
            folio = sig_idx * folios_per_sig + depth

            # row and column of this folio in the 4-row x 2-col folio grid
            folio_row = folio // 2
            folio_col = folio % 2   # 0=left, 1=right

            # obverse cell indices for this folio (left=bottom, right=top)
            ob_left_cell  = folio_row * 4 + folio_col * 2
            ob_right_cell = ob_left_cell + 1

            # manuscript pages for obverse
            ob_left_page  = O + P - 2 * depth
            ob_right_page = O + 2 * depth + 1

            # clamp to num_pages (0 = blank)
            obverse[ob_left_cell]  = ob_left_page  if ob_left_page  <= num_pages else 0
            obverse[ob_right_cell] = ob_right_page if ob_right_page <= num_pages else 0

            # reverse pages belong to the MIRROR folio (f ^ 1 within the row)
            # mirror flips left<->right within the same folio row
            mirror_folio_col = 1 - folio_col
            # for reverse, the folio row is mirrored within the signature too
            sig_start_row = sig_idx * (folios_per_sig // 2)
            local_row = folio_row - sig_start_row
            mirror_row = sig_start_row + (folios_per_sig // 2 - 1 - local_row)
            rev_left_cell  = mirror_row * 4 + mirror_folio_col * 2
            rev_right_cell = rev_left_cell + 1

            rev_left_page  = O + P // 2 - 2 * depth
            rev_right_page = O + P // 2 + 2 * depth + 1

            reverse[rev_left_cell]  = rev_left_page  if rev_left_page  <= num_pages else 0
            reverse[rev_right_cell] = rev_right_page if rev_right_page <= num_pages else 0

    return obverse, reverse


def format_page(p: int, width: int = 3) -> str:
    """Format a page number, using '---' for blank pages."""
    if p == 0:
        return '-' * width
    return str(p).rjust(width)


def print_grid(cells: list[int], folios_per_sig: int, label: str):
    """Print a 4-row x 4-col grid with folio and signature separators."""
    print(f"=== {label} ===")
    num_sigs = 8 // folios_per_sig  # signatures per sheet side (4 folio-rows / folios_per_sig rows per sig)

    for folio_row in range(4):
        sig_idx = folio_row // (folios_per_sig // 2) if folios_per_sig > 2 else folio_row

        # print signature separator
        if folios_per_sig > 2 and folio_row > 0 and folio_row % (folios_per_sig // 2) == 0:
            print()

        # cell indices for this folio row
        base = folio_row * 4
        c = [cells[base + i] for i in range(4)]

        row_str = f"[{format_page(c[0])}][{format_page(c[1])}] | [{format_page(c[2])}][{format_page(c[3])}]"
        print(row_str)

        # print folio-row separator within a signature
        if folios_per_sig > 2:
            local_row = folio_row % (folios_per_sig // 2)
            if local_row < (folios_per_sig // 2) - 1:
                print("-" * len(row_str))
        else:
            if folio_row < 3:
                print("-" * len(row_str))

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Sexidecimo page imposition tool"
    )
    parser.add_argument(
        "-f", "--folios",
        type=int,
        choices=[2, 4, 8],
        required=True,
        help="Folios per signature (2, 4, or 8)"
    )
    parser.add_argument(
        "-p", "--pages",
        type=int,
        required=True,
        help="Total manuscript pages"
    )
    args = parser.parse_args()

    f = args.folios
    p = args.pages

    # validate
    if p <= 0:
        print(f"Error: page count must be positive")
        return
    if p % (4 * f) != 0:
        padded = math.ceil(p / (4 * f)) * (4 * f)
        print(f"Note: {p} pages not evenly divisible by {4*f} (pages per sheet).")
        print(f"      Padding to {padded} pages (blank pages will show as '---').")
        print()
        p = padded

    obverse, reverse = compute_sheet(f, args.pages)

    print(f"Imposition: {args.folios}-folio signatures, {args.pages} manuscript pages")
    print(f"Sheet: {8 // f} signatures, {4 * f} pages each")
    print()

    print_grid(obverse, f, "OBVERSE")
    print_grid(reverse, f, "REVERSE (long-side flip)")


if __name__ == "__main__":
    main()