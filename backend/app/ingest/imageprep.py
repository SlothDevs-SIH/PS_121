"""Image preparation for OCR: binarisation and table-rule removal.

Scanned reports are full of ruled tables. Tesseract reads the rules as characters
("[", "|", "~") and often drops whole rows, so long horizontal/vertical dark runs are
erased before OCR. Runs much longer than any character stroke are treated as rules.
"""

import numpy as np
from numpy.typing import NDArray
from PIL import Image


def _long_runs_mask(dark: NDArray[np.bool_], min_len: int) -> NDArray[np.bool_]:
    """Mask of pixels that belong to runs of True of length >= min_len along axis 1."""
    h, w = dark.shape
    padded = np.zeros((h, w + 2), dtype=np.int8)
    padded[:, 1:-1] = dark
    diff = np.diff(padded, axis=1)
    mask = np.zeros_like(dark)
    rows_s, cols_s = np.nonzero(diff == 1)
    _, cols_e = np.nonzero(diff == -1)
    # Starts and ends come out in the same row-major order, so they pair up.
    lengths = cols_e - cols_s
    for r, c0, c1 in zip(
        rows_s[lengths >= min_len],
        cols_s[lengths >= min_len],
        cols_e[lengths >= min_len],
        strict=True,
    ):
        mask[r, c0:c1] = True
    return mask


def remove_rules(img: Image.Image, dpi: int = 200) -> Image.Image:
    gray = np.asarray(img.convert("L"), dtype=np.uint8)
    dark = gray < 150
    horiz = _long_runs_mask(dark, int(dpi * 0.9))  # >= ~23 mm long
    vert = _long_runs_mask(dark.T, int(dpi * 0.35)).T  # >= ~9 mm tall (text is ~3 mm)
    # Grow the mask by 1 px so anti-aliased rule edges go too.
    rules = horiz | vert
    grown = rules.copy()
    grown[1:, :] |= rules[:-1, :]
    grown[:-1, :] |= rules[1:, :]
    grown[:, 1:] |= rules[:, :-1]
    grown[:, :-1] |= rules[:, 1:]
    out = gray.copy()
    out[grown] = 255
    return Image.fromarray(out)
