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
| 2    | 2          | 8         | 4          | 4×4  | 32          |
| 4    | 4          | 16        | 2          | 4×4  | 32          |
| 6    | 6          | 24        | 1          | 3×4  | 24          |
| 8    | 8          | 32        | 1          | 4×4  | 32          |

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
> source .venv/bin/activate
> ```

## Usage

```bash
python impose.py <input.pdf> <output.pdf> [options]
```

### Arguments

| Argument     | Description                                   |
| ------------ | --------------------------------------------- |
| `input.pdf`  | Manuscript PDF — one PDF page = one book page |
| `output.pdf` | Output imposed PDF                            |

### Options

| Option           | Description                                                                    |
| ---------------- | ------------------------------------------------------------------------------ |
| `-f`, `--folios` | Folios per signature (default: 4). Any even number ≥ 2. 1 folio = 4 book pages |
| `-h`, `--help`   | Show help                                                                      |

### Examples

```bash
# Default (16 pages/sig, 4×4 grid)
python impose.py manuscript.pdf imposed.pdf

# 2 folios (8 pages/sig, 4 sigs/sheet)
python impose.py manuscript.pdf imposed.pdf -f 2

# 6 folios (24 pages/sig, 3×4 grid)
python impose.py manuscript.pdf imposed.pdf -f 6

# 8 folios (32 pages/sig, 4×4 grid)
python impose.py manuscript.pdf imposed.pdf -f 8
```

### Printing

- Print the output PDF **duplex** (long-edge flip)
- Each pair of output pages is one physical sheet (front + back)
- Cut along the crop marks and stack to assemble signatures

## Notes

- If the manuscript page count is not evenly divisible by the pages-per-sheet, blank pages are appended automatically
- Thin gray crop marks are included on each sheet to guide cutting
- The original page dimensions are preserved; the output sheet size scales to fit the grid
