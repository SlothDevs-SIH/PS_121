"""Page extraction: text lines with bounding boxes, from the PDF text layer or from OCR.

Output bboxes are normalised to the page ([x0, y0, x1, y1] in 0..1, origin top-left), so
they are independent of the resolution of the stored page image.
"""

import io
import statistics
from dataclasses import dataclass, field
from itertools import pairwise

import pypdfium2 as pdfium
import pytesseract
from PIL import Image

from app.ingest.imageprep import remove_rules

DISPLAY_DPI = 150
OCR_DPI = 200
MIN_TEXT_LAYER_CHARS = 20  # fewer characters than this → treat the page as scanned


@dataclass
class Line:
    text: str
    bbox: list[float]
    conf: float | None = None


@dataclass
class PageContent:
    page_no: int
    width_px: int
    height_px: int
    png: bytes
    ocr_used: bool
    mean_conf: float | None
    lines: list[Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("L").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _join_words(words: list[tuple[float, float, str]], wide_gap: float) -> str:
    """Join (x0, x1, text) words left to right; wide gaps become double spaces (table cells)."""
    words.sort()
    out = words[0][2]
    for (_, prev_x1, _), (x0, _, txt) in pairwise(words):
        out += ("  " if x0 - prev_x1 > wide_gap else " ") + txt
    return out


def _text_layer_lines(page: pdfium.PdfPage) -> list[Line]:
    width, height = page.get_size()
    tp = page.get_textpage()
    segments: list[tuple[float, float, float, float, str]] = []
    for i in range(tp.count_rects()):
        left, bottom, right, top = tp.get_rect(i)
        txt = tp.get_text_bounded(left, bottom, right, top).strip()
        if txt:
            segments.append((left, bottom, right, top, " ".join(txt.split())))
    tp.close()
    # Group segments whose vertical centres are close into lines, top of page first.
    segments.sort(key=lambda s: (-(s[1] + s[3]) / 2, s[0]))
    lines: list[list[tuple[float, float, float, float, str]]] = []
    for seg in segments:
        cy, h = (seg[1] + seg[3]) / 2, seg[3] - seg[1]
        if lines:
            last = lines[-1][0]
            if abs((last[1] + last[3]) / 2 - cy) < max(h, last[3] - last[1]) * 0.5:
                lines[-1].append(seg)
                continue
        lines.append([seg])
    out: list[Line] = []
    for group in lines:
        x0 = min(s[0] for s in group)
        x1 = max(s[2] for s in group)
        top = max(s[3] for s in group)
        bottom = min(s[1] for s in group)
        text = _join_words([(s[0], s[2], s[4]) for s in group], wide_gap=6.0)
        out.append(Line(text, [x0 / width, 1 - top / height, x1 / width, 1 - bottom / height]))
    return out


def ocr_lines(img: Image.Image) -> tuple[list[Line], float | None]:
    """OCR an image into lines with bboxes and mean word confidence (0..100)."""
    clean = remove_rules(img, dpi=OCR_DPI)
    data = pytesseract.image_to_data(clean, config="--psm 6", output_type=pytesseract.Output.DICT)
    w, h = clean.size
    groups: dict[tuple[int, int, int], list[int]] = {}
    # Scanner noise next to rules/edges comes back as stray "_", "|" or "~" characters.
    data["text"] = [t.strip("_|~") for t in data["text"]]
    for i, txt in enumerate(data["text"]):
        if txt.strip() and float(data["conf"][i]) >= 0:
            groups.setdefault(
                (data["block_num"][i], data["par_num"][i], data["line_num"][i]), []
            ).append(i)
    lines: list[Line] = []
    all_conf: list[float] = []
    for idx in groups.values():
        x0 = min(data["left"][i] for i in idx)
        y0 = min(data["top"][i] for i in idx)
        x1 = max(data["left"][i] + data["width"][i] for i in idx)
        y1 = max(data["top"][i] + data["height"][i] for i in idx)
        confs = [float(data["conf"][i]) for i in idx]
        all_conf += confs
        words = [
            (float(data["left"][i]), float(data["left"][i] + data["width"][i]), data["text"][i])
            for i in idx
        ]
        text = _join_words(words, wide_gap=w * 0.02)
        lines.append(
            Line(text, [x0 / w, y0 / h, x1 / w, y1 / h], round(statistics.fmean(confs), 1))
        )
    lines.sort(key=lambda ln: (ln.bbox[1], ln.bbox[0]))
    return lines, (round(statistics.fmean(all_conf), 1) if all_conf else None)


def extract_pdf(data: bytes) -> list[PageContent]:
    doc = pdfium.PdfDocument(data)
    try:
        pages: list[PageContent] = []
        for n, page in enumerate(doc, start=1):
            lines = _text_layer_lines(page)
            display = page.render(scale=DISPLAY_DPI / 72).to_pil()
            ocr_used = sum(len(ln.text) for ln in lines) < MIN_TEXT_LAYER_CHARS
            mean_conf = None
            if ocr_used:
                lines, mean_conf = ocr_lines(page.render(scale=OCR_DPI / 72).to_pil())
            pages.append(
                PageContent(
                    n, display.width, display.height, _png(display), ocr_used, mean_conf, lines
                )
            )
            page.close()
        return pages
    finally:
        doc.close()


def extract_image(data: bytes) -> list[PageContent]:
    img = Image.open(io.BytesIO(data))
    pages: list[PageContent] = []
    for n in range(getattr(img, "n_frames", 1)):
        img.seek(n)
        frame = img.convert("L")
        lines, mean_conf = ocr_lines(frame)
        pages.append(
            PageContent(n + 1, frame.width, frame.height, _png(frame), True, mean_conf, lines)
        )
    return pages
