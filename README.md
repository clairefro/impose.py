# impose.py for katte press

PDF imposition tool for **cut-and-stack bookbinding** (sextodecimo / 16mo).

Takes a manuscript PDF (one page per book page) and produces an imposed PDF with multiple book pages arranged on each sheet. Print duplex, cut, and stack to form signatures ready for binding.

## How it works

Each output sheet has a **front** (obverse) and **back** (reverse) with book pages arranged in a grid of folio pairs. After duplex printing:

1. **Cut** each sheet along the crop marks
2. **Stack** the strips/quarters in order
3. Each pile is one **signature**

## Imposition pattern

Each signature has **F** folios. Each folio holds 4 book pages (2 per side), so a signature has **P = 4F** pages.

### Page formulas

For folio depth **d** (0-indexed, d = 0…F−1) within a signature at offset **O**:

| Side  | Position | Page (1-indexed) |
| ----- | -------- | ---------------- |
| Front | Left     | O + P − 2d       |
| Front | Right    | O + 2d + 1       |
| Back  | Left     | O + 2d + 2       |
| Back  | Right    | O + P − 2d − 1   |

Where **O = sig_index × P** (0-based offset).

The pattern: front-left counts **down** from P by 2, front-right counts **up** from 1 by 2. Back mirrors: back-left counts up from 2, back-right counts down from P−1. The innermost folio (d = F−1) always contains the 4 consecutive center pages.

Back side folio columns are **mirrored** (col 0 ↔ col 1) for long-edge duplex. Rows are unchanged.

### Grid layout

Folios are arranged in a grid of **(F/2 × sigs_per_sheet) rows × 4 columns** (2 folio-columns). Multiple signatures share a sheet when they fit:

| `-f` | Folios/sig | Pages/sig | Sigs/sheet | Grid | Pages/sheet |
| ---- | ---------- | --------- | ---------- | ---- | ----------- |
| 0    | —          | —         | —          | 4×4  | 16          |
| 2    | 2          | 8         | 4          | 4×4  | 32          |
| 4    | 4          | 16        | 2          | 4×4  | 32          |
| 6    | 6          | 24        | 1          | 3×4  | 24          |
| 8    | 8          | 32        | 1          | 4×4  | 32          |

`-f 0` is a special mode: pages are laid out in **manuscript order** (1, 2, 3, …) in a 4×4 grid, single-sided, with no imposition.

### Page ordering by folio count

**-f 2** (P=8):

```
d=0  Front: [ 8,  1]  Back: [ 2,  7]
d=1  Front: [ 6,  3]  Back: [ 4,  5]
```

**-f 4** (P=16):

```
d=0  Front: [16,  1]  Back: [ 2, 15]
d=1  Front: [14,  3]  Back: [ 4, 13]
d=2  Front: [12,  5]  Back: [ 6, 11]
d=3  Front: [10,  7]  Back: [ 8,  9]
```

**-f 6** (P=24):

```
d=0  Front: [24,  1]  Back: [ 2, 23]
d=1  Front: [22,  3]  Back: [ 4, 21]
d=2  Front: [20,  5]  Back: [ 6, 19]
d=3  Front: [18,  7]  Back: [ 8, 17]
d=4  Front: [16,  9]  Back: [10, 15]
d=5  Front: [14, 11]  Back: [12, 13]
```

**-f 8** (P=32):

```
d=0  Front: [32,  1]  Back: [ 2, 31]
d=1  Front: [30,  3]  Back: [ 4, 29]
d=2  Front: [28,  5]  Back: [ 6, 27]
d=3  Front: [26,  7]  Back: [ 8, 25]
d=4  Front: [24,  9]  Back: [10, 23]
d=5  Front: [22, 11]  Back: [12, 21]
d=6  Front: [20, 13]  Back: [14, 19]
d=7  Front: [18, 15]  Back: [16, 17]
```

## Install

Requires **Python 3.8+** and a system install of [qpdf](https://github.com/qpdf/qpdf) (needed by pikepdf).

### System dependencies

**macOS:**

```bash
brew install qpdf
```

**Debian / Ubuntu:**

```bash
sudo apt install qpdf
```

### Python setup

```bash
# Clone the repo
git clone https://github.com/clairefro/katte-p.git
cd katte-p

# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate    # macOS / Linux
# .venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

> **Tip:** Always activate the venv before running the script. If you see `ModuleNotFoundError: No module named 'pikepdf'`, you likely forgot to activate it:
>
> ```bash
> python impose_a.py <input.pdf> [output.pdf] [--page-size <size>] [options]
> ```

## Usage

| `--page-size` | Accordion panel size. Named sizes: `A3`, `A4`, `A5`, `A6`, `A7`, `A8`, `A9`, `A10`; or custom `WxH` with unit (`mm/cm/in/pt`). Default: `A8` |
python impose.py <input.pdf> [output.pdf] [options]

````

### Arguments

| Argument     | Description                                           |
| ------------ | ----------------------------------------------------- |
| `input.pdf`  | Manuscript PDF — one PDF page = one book page         |
| `output.pdf` | Output imposed PDF (default: `<input>_f<folios>.pdf`) |

### Options

| Option             | Description                                                                                                |
| ------------------ | ---------------------------------------------------------------------------------------------------------- |
| `-f`, `--folios`   | Folios per signature (default: 4). Any even number ≥ 2, or 0 for sequential layout. 1 folio = 4 book pages |
| `-m`, `--no-marks` | Hide all crop marks, indicators, and crosshairs                                                            |
| `-h`, `--help`     | Show help                                                                                                  |

### Examples

```bash
# Default (4 folios) → manuscript_f4.pdf
python impose.py manuscript.pdf

# 2 folios → manuscript_f2.pdf
python impose.py manuscript.pdf -f 2

# 6 folios → manuscript_f6.pdf
python impose.py manuscript.pdf -f 6

# 8 folios → manuscript_f8.pdf
python impose.py manuscript.pdf -f 8

# Sequential layout (no imposition) → manuscript_f0.pdf
python impose.py manuscript.pdf -f 0

# No crop marks
python impose.py manuscript.pdf -f 4 -m

# Custom output filename
python impose.py manuscript.pdf my_output.pdf -f 4
````

### Printing

- Print the output PDF **duplex** (long-edge flip)
- Each pair of output pages is one physical sheet (front + back)
- Cut along the crop marks and stack to assemble signatures
- A **dashed line** (`- -`) in the margins marks the end of a signature; solid lines are folio cuts inside a signature

## Notes

- If the manuscript page count is not evenly divisible by the pages-per-sheet, blank pages are appended automatically
- Thin gray crop marks are included on each sheet to guide cutting
- The original page dimensions are preserved; the output sheet size scales to fit the grid

## Accordion imposition (`impose_a.py`)

Use `impose_a.py` to impose manuscript pages as accordion-fold strips laid out along the **long side** of printer paper.

### What it does

- Places pages in reading order into strip panels
- Optimizes paper usage by packing multiple strip rows per sheet when they fit
- Leaves configurable glue margins at strip ends (default: 1 cm)
- Draws thin strip cut lines and optional faint fold crosshairs

### Basic usage

```bash
python impose_a.py <input.pdf> [output.pdf] [--page-size <size>] [options]
```

If `output.pdf` is omitted, the default is:

```text
<input>_acc_pap<name|WxH>_pg<name|WxH>_gl<cm>_xh<pt>_bf<n>_bb<n>[_dup-le|_dup-se]_mrk<0|1>_fcx<0|1>.pdf
```

Abbreviations: `pap`=paper size (name or dimensions), `pg`=page size (name or dimensions), `gl`=glue margin (cm), `xh`=crosshair leg (pt), `bf`/`bb`=blank front/back, `dup-le`=duplex long-edge, `dup-se`=duplex short-edge, `mrk`=marks enabled, `fcx`=fold crosshairs enabled.

Example with defaults (single-sided): `book_acc_papa4_pga8_gl1_xh8_bf1_bb1_mrk1_fcx1.pdf`

Example with duplex long-edge: `book_acc_papa4_pga8_gl1_xh8_bf1_bb1_dup-le_mrk1_fcx1.pdf`

Example with custom sizes: `book_acc_pap210x279_pg52x76_gl1_xh8_bf1_bb1_mrk1_fcx1.pdf`

### Defaults

When not specified, `impose_a.py` uses:

- `--paper-size A4`
- `--page-size A8`
- `--glue-margin-cm 1.0`
- `--fold-crosshair-leg-pt 8.0`
- `--blank-front 1`
- `--blank-back 1`
- `--duplex` / `--duplex-short` disabled (single-sided output)
- `--no-fold-crosshairs` disabled (fold crosshairs are shown)
- `--no-marks` disabled (strip cut lines and fold crosshairs are shown)

### Key options

| Option                    | Description                                                                                                                                  |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `--paper-size`            | Printer paper size (`A5`, `A4`, `A3`, `Letter`, `Legal`, `Tabloid`) or custom `WxH` with unit (`mm/cm/in/pt`)                                |
| `--page-size`             | Accordion panel size. Named sizes: `A3`, `A4`, `A5`, `A6`, `A7`, `A8`, `A9`, `A10`; or custom `WxH` with unit (`mm/cm/in/pt`). Default: `A8` |
| `--glue-margin-cm`        | Glue margin at both strip ends (default: `1.0`)                                                                                              |
| `--blank-front`           | Add blank pages before manuscript pages                                                                                                      |
| `--blank-back`            | Add blank pages after manuscript pages                                                                                                       |
| `--duplex`                | Front+back pages for **long-edge** duplex. Back content rotated 180° to appear right-side-up after flipping.                                 |
| `--duplex-short`          | Front+back pages for **short-edge** duplex. Back content mirrored horizontally only. Implies `--duplex`.                                     |
| `--no-fold-crosshairs`    | Hide fold crosshairs but keep strip cut lines                                                                                                |
| `--fold-crosshair-leg-pt` | Fold crosshair horizontal leg length in points (default: `8.0`)                                                                              |
| `-m`, `--no-marks`        | Hide all marks (cut lines + fold crosshairs)                                                                                                 |

### Examples

```bash
# A8 mini-book panels on A4 paper
python impose_a.py manuscript.pdf --paper-size A4 --page-size 52x74mm

# Letter paper with front/back blanks and default glue margin
python impose_a.py manuscript.pdf --paper-size Letter --page-size 52x74mm --blank-front 2 --blank-back 2

# Duplex long-edge (default flip mode) — back content rotated 180°
python impose_a.py manuscript.pdf --paper-size Letter --page-size 52x74mm --duplex

# Duplex short-edge — back content mirrored horizontally only
python impose_a.py manuscript.pdf --paper-size Letter --page-size 52x74mm --duplex-short

# Keep strip cut lines, but hide fold crosshairs
python impose_a.py manuscript.pdf --paper-size Letter --page-size 52x74mm --no-fold-crosshairs

# Subtle fold marks by shortening crosshair leg length
python impose_a.py manuscript.pdf --paper-size A4 --page-size 52x74mm --fold-crosshair-leg-pt 3.0

# Hide all marks entirely
python impose_a.py manuscript.pdf --paper-size A4 --page-size 52x74mm --no-marks

### Folding tips:

- Ensure your strips fold such that the fold aligns with the grain of your paper.
- Check every 3–4 folds to ensure drift is not occurring.
```
