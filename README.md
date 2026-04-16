# katte-p

PDF imposition tool for **cut-and-stack bookbinding** (sextodecimo / 16mo).

Takes a manuscript PDF (one page per book page) and produces an imposed PDF with multiple book pages arranged on each sheet. Print duplex, cut, and stack to form signatures ready for binding.

## How it works

Each output sheet has a **front** (Side A) and **back** (Side B) with book pages arranged in a 2×2 grid of folios. After duplex printing:

1. **Cut** each sheet into 4 quarters along the crop marks
2. **Stack** the quarters in order
3. Each pile is one **signature**

## Install

Requires **Python 3.8+**.

```bash
# Clone the repo
git clone https://github.com/clairefro/katte-p.git
cd katte-p

# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

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

| Option           | Description                                               |
| ---------------- | --------------------------------------------------------- |
| `-f`, `--folios` | Folios per signature (default: 4). 1 folio = 4 book pages |
| `-h`, `--help`   | Show help                                                 |

### Examples

```bash
# Default sextodecimo (16 pages/sheet, 4 folios/sig)
python impose.py manuscript.pdf imposed.pdf

# Octavo (8 pages/sheet, 2 folios/sig)
python impose.py manuscript.pdf imposed.pdf -f 2

# 32mo (32 pages/sheet, 8 folios/sig)
python impose.py manuscript.pdf -f 8 imposed.pdf
```

### Printing

- Print the output PDF **duplex** (long-edge flip)
- Each pair of output pages is one physical sheet (front + back)
- Cut along the crop marks and stack to assemble signatures

## Notes

- If the manuscript page count is not evenly divisible by the pages-per-sheet, blank pages are appended automatically
- Thin gray crop marks are included on each sheet to guide cutting
- The original page dimensions are preserved; the output sheet size scales to fit the grid
