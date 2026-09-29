"""Offset Risk Brief (B5, master plan §4.14): a PDF an engineer takes into a pre-spud or
section-planning meeting.

Contents: the well's facts; a plan-view sketch of the offset wells within the radius; the
offsets table; the offset prior risk by formation with the 90% interval drawn; what worked
for the top risks nearby (the Mitigation Ledger, with its caveat); the evidence pages every
number rests on. Rendered with fpdf2 core fonts (no system font or browser needed), so the
text is restricted to Latin-1 and sanitised on the way in. Every page of a synthetic well's
brief carries the SYNTHETIC watermark.
"""

import math
from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.api.v1.schemas.knowledge import RiskProfile
from app.extract.evidence import event_evidence_refs
from app.geo.service import surface_offsets
from app.ledger.service import ledger
from app.normalise.wells_service import get_well_or_404, well_detail
from app.risk.prior import EVENT_LABELS, risk_profile

WATERMARK = "SYNTHETIC DATA - NOT OIL INDIA DATA"
_SUBS = {
    chr(c): r
    for c, r in (
        (0x2013, "-"),
        (0x2014, "-"),
        (0x2212, "-"),
        (0x2011, "-"),
        (0x2265, ">="),
        (0x2264, "<="),
        (0x00BC, " 1/4"),
        (0x00BD, " 1/2"),
        (0x00BE, " 3/4"),
        (0x201C, '"'),
        (0x201D, '"'),
        (0x2018, "'"),
        (0x2019, "'"),
        (0x2032, "'"),
        (0x2033, '"'),
        (0x2026, "..."),
        (0x2192, "->"),
        (0x00D7, "x"),
        (0x03C3, "sigma"),
        (0x03B1, "alpha"),
        (0x03B2, "beta"),
        (0x00B2, "2"),
        (0x00A0, " "),
        (0x03A3, "sum "),
        (0x221A, "sqrt"),
        (0x2248, "~"),
    )
}  # typographic characters the Latin-1 core fonts cannot draw


def latin(text: object) -> str:
    s = str(text)
    for a, b in _SUBS.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


def pct(p: float | None) -> str:
    return "-" if p is None else f"{p * 100:.0f}%"


class Brief(FPDF):
    def __init__(self, title: str, synthetic: bool) -> None:
        super().__init__(format="A4")
        self.brief_title = title
        self.synthetic = synthetic
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(14, 14, 14)

    def header(self) -> None:
        if self.synthetic:
            self.set_font("Helvetica", "B", 30)
            self.set_text_color(235, 225, 225)
            with self.rotation(35, x=105, y=150):
                self.text(30, 170, WATERMARK)
            self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, latin(self.brief_title), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(110, 110, 110)
        note = (
            "Advisory: offset priors and recorded outcomes from history, not predictions or "
            "proven causes. " + (WATERMARK + ". " if self.synthetic else "")
        )
        self.cell(0, 5, latin(note) + f"Page {self.page_no()}/{{nb}}", align="C")
        self.set_text_color(0, 0, 0)

    def h1(self, text: str) -> None:
        self.set_font("Helvetica", "B", 16)
        self.multi_cell(0, 8, latin(text), new_x="LMARGIN", new_y="NEXT")

    def h2(self, text: str) -> None:
        self.ln(2)
        self.set_font("Helvetica", "B", 11.5)
        self.set_fill_color(236, 240, 246)
        self.cell(0, 7, latin(text), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def para(self, text: str, size: float = 9) -> None:
        self.set_font("Helvetica", "", size)
        self.multi_cell(0, 4.6, latin(text), new_x="LMARGIN", new_y="NEXT")

    def grid(self, head: list[str], rows: list[list[str]], widths: list[float]) -> None:
        self.set_font("Helvetica", "B", 8.5)
        for h, w in zip(head, widths, strict=True):
            self.cell(w, 6, latin(h), border="B")
        self.ln()
        self.set_font("Helvetica", "", 8.5)
        for r in rows:
            if self.will_page_break(5.5):
                self.add_page()
            for v, w in zip(r, widths, strict=True):
                self.cell(w, 5.5, latin(v)[: int(w / 1.55)])
            self.ln()


def _plan_view(pdf: Brief, well: Any, offsets: list[Any], radius_km: float) -> None:
    """Offsets around the well in plan (north up), scaled to the radius."""
    size, x0, y0 = 70.0, pdf.l_margin + 55, pdf.get_y() + 38
    k = (size / 2) / (radius_km * 1000)
    pdf.set_draw_color(160, 160, 160)
    pdf.circle(x=x0, y=y0, radius=size / 2)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.text(x0 + 1, y0 - size / 2 - 1, "N")
    pdf.line(x0, y0 - size / 2, x0, y0 - size / 2 + 3)
    cos = math.cos(math.radians(well.lat))
    # Wells on one pad sit metres apart: draw one dot per 150 m cluster, labelled with its count.
    clusters: list[list[tuple[float, float]]] = [[(0.0, 0.0)]]  # the subject's pad first
    for o in offsets:
        p = ((o.lon - well.lon) * cos * 111_320, (o.lat - well.lat) * 110_540)
        for c in clusters:
            cx, cy = c[0]
            if math.hypot(p[0] - cx, p[1] - cy) <= 300:
                c.append(p)
                break
        else:
            clusters.append([p])
    pdf.set_font("Helvetica", "", 6.5)
    for c in clusters[1:]:
        cx = sum(x for x, _ in c) / len(c)
        cy = sum(y for _, y in c) / len(c)
        px, py = x0 + cx * k, y0 - cy * k
        pdf.set_fill_color(70, 110, 170)
        pdf.circle(x=px, y=py, radius=1.0, style="F")
        pdf.text(px + 1.8, py + 1, f"{len(c)}")
    on_pad = len(clusters[0]) - 1
    pdf.set_fill_color(220, 90, 40)
    pdf.circle(x=x0, y=y0, radius=1.6, style="F")
    pdf.set_font("Helvetica", "B", 7)
    pad = f" (+{on_pad} on its pad)" if on_pad else ""
    pdf.text(x0 + 2.5, y0 + 1, latin(well.canonical_name + pad))
    pdf.set_font("Helvetica", "", 7)
    pdf.text(
        x0 - size / 2,
        y0 + size / 2 + 5,
        latin(f"Circle = {radius_km:g} km. Blue: offset wells (number per pad)."),
    )
    pdf.set_y(y0 + size / 2 + 8)


def _risk_chart(pdf: Brief, profile: RiskProfile) -> None:
    """One row per formation: the highest prior as a bar with its 90% interval whisker."""
    x_label, x0, w = pdf.l_margin, pdf.l_margin + 48, 100.0
    pdf.set_font("Helvetica", "", 7)
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        pdf.text(x0 + t * w - 2, pdf.get_y() + 3, pct(t))
    pdf.ln(4)
    for iv in profile.intervals:
        if not iv.risks:
            continue
        r = iv.risks[0]
        y = pdf.get_y()
        pdf.set_font("Helvetica", "", 7.5)
        name = iv.formation + (" (prognosed)" if iv.prognosed else "")
        pdf.text(x_label, y + 3.2, latin(name)[:30])
        pdf.set_fill_color(235, 238, 242)
        pdf.rect(x0, y + 0.8, w, 3.4, style="F")
        shade = 255 - int(min(1.0, r.probability / 0.6) * 150)
        pdf.set_fill_color(230, shade, shade - 30 if shade > 30 else 0)
        pdf.rect(x0, y + 0.8, w * r.probability, 3.4, style="F")
        pdf.set_draw_color(40, 40, 40)
        pdf.line(x0 + w * r.ci90_low, y + 2.5, x0 + w * r.ci90_high, y + 2.5)
        pdf.text(
            x0 + w + 2,
            y + 3.2,
            latin(f"{EVENT_LABELS.get(r.event_type, r.event_type)} {pct(r.probability)}"),
        )
        pdf.ln(5)


def build(session: Session, well_id: int, radius_km: float = 5.0) -> bytes:
    well = get_well_or_404(session, well_id)
    detail = well_detail(session, well_id)
    profile = risk_profile(session, well_id)  # the app's default radius, as on Well 360
    offsets = [
        o for o in surface_offsets(session, well_id, radius_km * 1000) if o.status != "planned"
    ]
    now = datetime.now(tz=UTC)
    pdf = Brief(f"SMRITI Offset Risk Brief - {well.canonical_name}", well.synthetic)
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.h1(f"Offset Risk Brief: {well.canonical_name}")
    pdf.para(
        f"Generated {now:%Y-%m-%d %H:%M} UTC by SMRITI (eRTMAC-NWIS). Offsets within "
        f"{radius_km:g} km; priors from offsets within {profile.radius_km:g} km weighted by "
        f"distance (sigma {profile.sigma_km:g} km) and similarity."
        + (f" {WATERMARK}." if well.synthetic else "")
    )
    pdf.h2("1. The well")
    td = f"{detail.td_md_m:,.0f} m MD" if detail.td_md_m else "-"
    pdf.grid(
        ["Field", "Status", "Type", "Profile", "TD", "Spud", "Location"],
        [[detail.field, detail.status, detail.well_type or "-", detail.profile or "-", td,
          str(detail.spud_date or "-"), f"{detail.lat:.4f}, {detail.lon:.4f}"]],
        [46, 18, 24, 16, 22, 20, 36],
    )  # fmt: skip

    pdf.h2(f"2. Offset wells within {radius_km:g} km ({len(offsets)})")
    _plan_view(pdf, well, offsets, radius_km)
    pdf.grid(
        ["Well", "Distance (surface)", "Status", "Fluid", "TD (m MD)"],
        [
            [o.name, f"{o.distance_m:,.0f} m", o.status, o.fluid_type or "-",
             f"{o.td_md_m:,.0f}" if o.td_md_m else "-"]
            for o in offsets[:25]
        ],
        [40, 36, 30, 24, 30],
    )  # fmt: skip
    if len(offsets) > 25:
        pdf.para(f"... and {len(offsets) - 25} more.", 8)

    pdf.h2("3. Offset prior risk by formation")
    pdf.para(
        "Highest prior per formation (bar) with its 90% credible interval (line). Prognosed "
        "formations are below a drilling well's TD: their tops are estimated from offsets.",
        8,
    )
    _risk_chart(pdf, profile)
    rows, top_types = [], []
    for iv in profile.intervals:
        for r in iv.risks[:2]:
            if r.probability < 0.1:
                continue
            rows.append(
                [
                    iv.formation + (" *" if iv.prognosed else ""),
                    EVENT_LABELS.get(r.event_type, r.event_type),
                    pct(r.probability),
                    f"{pct(r.ci90_low)}-{pct(r.ci90_high)}",
                    f"{r.offsets_with_event}/{r.offsets_total}",
                    f"{r.n_eff:.1f}",
                ]
            )
            top_types.append((r.probability, r.event_type, iv.formation, iv))
    pdf.grid(
        ["Formation", "Problem", "Prior", "90% CI", "Offsets", "n_eff"],
        rows or [["-", "no problem reaches 10%", "", "", "", ""]],
        [48, 36, 18, 28, 22, 18],
    )
    pdf.para("* prognosed top. " + profile.method, 7)

    pdf.h2("4. What worked nearby (Mitigation Ledger)")
    seen: set[str] = set()
    cited_events: list[int] = []
    for _, et, fm, iv in sorted(top_types, key=lambda t: -t[0]):
        if et in seen or len(seen) >= 3:
            continue
        seen.add(et)
        led = ledger(session, event_type=et, formation=fm)
        label = f"{EVENT_LABELS.get(et, et)} in the {fm}"
        if not led.ranked:
            led = ledger(session, event_type=et)
            label = f"{EVENT_LABELS.get(et, et)} (all formations: too few records in the {fm})"
        pdf.set_font("Helvetica", "B", 9)
        pdf.multi_cell(0, 5, latin(label), new_x="LMARGIN", new_y="NEXT")
        if not led.ranked:
            pdf.para("Too few recorded outcomes to rank treatments.", 8.5)
            continue
        for e in led.ranked[:3]:
            pdf.para(f"- {e.summary}", 8.5)
            cited_events += [c.event_id for c in e.cases[:2]]
        for o in iv.offsets:
            cited_events += o.events.get(et, [])[:2]
    pdf.para(
        "Observational records: a higher-ranked action is associated with better recorded "
        "outcomes, not proven to cause them.",
        7.5,
    )

    pdf.h2("5. Evidence")
    refs = event_evidence_refs(session, list(dict.fromkeys(cited_events))[:40])
    ev_rows = sorted(
        {(r.filename or f"document {r.document_id}", r.page_no) for rs in refs.values() for r in rs}
    )
    pdf.para("Report pages behind the numbers above (open them in SMRITI's document viewer):", 8.5)
    pdf.grid(["Report", "Page"], [[f, str(p)] for f, p in ev_rows[:40]] or [["-", "-"]], [150, 20])
    out = pdf.output()
    return bytes(out)
