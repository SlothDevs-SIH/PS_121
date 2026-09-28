"""Render synthetic Daily Drilling Reports and Well Completion Reports as PDFs.

Reports deliberately vary the way real archives do: well-name aliases, formation synonyms,
metric vs oilfield units, number formatting, sentence phrasing, and about 30% of files
"scanned" (image-only, slightly rotated and noisy) so the OCR path is exercised.
Every page carries a SYNTHETIC watermark.
"""

import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from fpdf import FPDF
from PIL import Image, ImageFilter

from app.core.units import BBL_TO_M3, FT_TO_M, PPG_PER_SG
from app.synthetic import model as sm
from app.synthetic.generator import Event, SyntheticField, Well, _rng

DOC_PURPOSE = 7
SCANNED_FRACTION = 0.3
FIXED_PDF_DATE = datetime(2026, 1, 1, tzinfo=UTC)

_CODES = {
    "LOSS": "NPT-LOSS",
    "STUCK": "NPT-STCK",
    "KICK": "NPT-WC",
    "TIGHT": "NPT-HOLE",
    "TORQUE": "NPT-HOLE",
    "INSTAB": "NPT-HOLE",
    "BALLING": "NPT-HOLE",
    "OVERP": "NPT-WC",
    "CEMENT": "NPT-CMT",
}

_PROBLEM_TEXT = {
    "LOSS": (
        "{sev} losses of {rate} while drilling at {depth} in {fm}",
        "Lost circulation ({sev}, {rate}) at {depth}, {fm}",
    ),
    "STUCK": (
        "Pipe stuck ({sub}) at {depth} in {fm}, overpull {op}",
        "String became stuck at {depth} ({fm}); {sub} sticking suspected, overpull {op}",
    ),
    "KICK": (
        "Kick taken at {depth} in {fm}: pit gain {pg}, SIDPP {sidpp}",
        "Well kicked at {depth} ({fm}), {pg} pit gain, shut in, SIDPP {sidpp}",
    ),
    "TIGHT": (
        "Tight hole at {depth} in {fm}, overpull {op}",
        "Encountered tight spot at {depth} ({fm}) with {op} overpull",
    ),
    "TORQUE": (
        "Erratic torque up to {tq} at {depth} in {fm}",
        "Torque spikes to {tq} while drilling {fm} at {depth}",
    ),
    "INSTAB": (
        "Wellbore instability at {depth} in {fm}: {sub} observed",
        "Hole instability ({sub}) at {depth} in {fm}",
    ),
    "BALLING": (
        "Bit balling at {depth} in {fm}, ROP dropped sharply",
        "Suspected bit balling in {fm} at {depth}",
    ),
    "OVERP": (
        "Overpressure indications at {depth} in {fm}: background gas {gas}%",
        "High gas ({gas}%) and connection gas at {depth}, {fm} - overpressure suspected",
    ),
    "CEMENT": (
        "Cementing problem on intermediate casing at {depth} ({fm}): {sub}",
        "Cement job at {depth} in {fm} - {sub}",
    ),
}


@dataclass
class GeneratedDoc:
    file: str
    well: str
    doc_type: str
    scanned: bool
    report_date: str
    event_ids: list[str]


class _Units:
    def __init__(self, system: str) -> None:
        self.metric = system == "metric"

    def depth(self, m: float, rng: np.random.Generator) -> str:
        v = m if self.metric else m / FT_TO_M
        s = f"{v:,.0f}" if rng.random() < 0.6 else f"{v:.0f}"
        return f"{s} m" if self.metric else f"{s} ft"

    def depth_plain(self, m: float) -> str:
        return f"{m:.0f}" if self.metric else f"{m / FT_TO_M:.0f}"

    @property
    def depth_unit(self) -> str:
        return "m" if self.metric else "ft"

    def mw(self, sg: float) -> str:
        return f"{sg:.2f} SG" if self.metric else f"{sg * PPG_PER_SG:.1f} ppg"

    def volume(self, bbl: float) -> str:
        return f"{bbl * BBL_TO_M3:.0f} m3" if self.metric else f"{bbl:.0f} bbl"

    def rate(self, bbl_hr: float) -> str:
        return f"{bbl_hr * BBL_TO_M3:.1f} m3/hr" if self.metric else f"{bbl_hr:.0f} bbl/hr"

    def flow(self, rng: np.random.Generator) -> str:
        gpm = float(rng.uniform(450, 750))
        return f"{gpm * 3.785412:.0f} lpm" if self.metric else f"{gpm:.0f} gpm"


class _Report(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__(format="A4")
        self.report_title = title
        self.set_creation_date(FIXED_PDF_DATE)  # byte-identical re-renders → SHA-256 dedupe works
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(15, 15, 15)

    def header(self) -> None:
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 7, self.report_title, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 5, sm.WATERMARK, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, f"Page {self.page_no()}", align="C")

    def section(self, text: str) -> None:
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9.5)

    def line_text(self, text: str) -> None:
        self.set_font("Helvetica", "", 9.5)
        self.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")

    def grid(self, header: list[str], rows: list[list[str]], widths: list[int]) -> None:
        self.set_font("Helvetica", "", 9)
        with self.table(col_widths=widths, text_align="LEFT", line_height=5.5) as t:
            r = t.row()
            for h in header:
                r.cell(h)
            for row in rows:
                r = t.row()
                for c in row:
                    r.cell(c)


def _alias(well: Well, rng: np.random.Generator) -> str:
    return str(rng.choice([well.name, *well.aliases], p=[0.6, 0.2, 0.2]))


def _fm(name: str, rng: np.random.Generator) -> str:
    spec = next(s for s in sm.STRATIGRAPHY if s.name == name)
    return str(rng.choice([name, *spec.synonyms])) if rng.random() < 0.5 else name


def _action_sentence(code: str, u: _Units, rng: np.random.Generator, ev: Event) -> str:
    template = str(rng.choice(sm.ACTION_TEXT[code]))
    return template.format(
        v=u.volume(float(rng.uniform(30, 80))),
        mw=u.mw(ev.mw_sg + (0.04 if code == "INCREASE_MW" else -0.04)),
        q=u.flow(rng),
        rpm=int(rng.uniform(60, 100)),
    )


def _outcome_sentence(ev: Event, ok: bool, rng: np.random.Generator) -> str:
    return (
        str(rng.choice(sm.SUCCESS_WORDS[ev.event_type])) if ok else str(rng.choice(sm.FAIL_WORDS))
    )


def _problem_sentence(ev: Event, u: _Units, rng: np.random.Generator) -> str:
    t = str(rng.choice(_PROBLEM_TEXT[ev.event_type]))
    p = ev.params
    return t.format(
        sev=(ev.subtype or "partial").capitalize(),
        sub=ev.subtype or "unspecified",
        rate=u.rate(p.get("loss_rate_bbl_hr", 0.0)) if p.get("loss_rate_bbl_hr") else "no returns",
        depth=u.depth(ev.md_m, rng),
        fm=_fm(ev.formation, rng),
        op=f"{p.get('overpull_klbf', 0):.0f} klbf",
        pg=u.volume(p.get("pit_gain_bbl", 0.0)),
        sidpp=f"{p.get('sidpp_psi', 0):.0f} psi",
        tq=f"{p.get('torque_kftlbf', 0):.1f} kft.lbf",
        gas=f"{p.get('gas_pct', 0):.1f}",
    )


def render_ddr(
    well: Well, ev: Event | None, report_no: int, day: datetime, rng: np.random.Generator
) -> bytes:
    u = _Units(well.units)
    pdf = _Report("DAILY DRILLING REPORT")
    pdf.add_page()
    depth = ev.md_m if ev else well.td_md_m * float(rng.uniform(0.2, 0.9))
    fm = _fm(ev.formation, rng) if ev else _fm(_formation_at(well, depth), rng)
    hole = ev.hole_size if ev else _hole_label(well, depth)
    mw = ev.mw_sg if ev else _mw_at(well, depth)
    pdf.line_text(
        f"Well: {_alias(well, rng)}    Rig: {well.rig}    Report No: {report_no}    Date: {day:%Y-%m-%d}"
    )
    pdf.line_text(
        f"Depth at 24:00: {u.depth(depth, rng)}    Hole size: {hole} in    Mud weight: {u.mw(mw)}    Formation: {fm}"
    )
    pdf.section("TIME LOG")
    rows: list[list[str]] = []
    t = day.replace(hour=0, minute=0)
    drill_h = float(rng.uniform(4, 9)) if ev else 20.0
    start_md = depth - drill_h * float(rng.uniform(4, 8))
    rows.append(
        [
            f"{t:%H:%M}",
            f"{t + timedelta(hours=drill_h):%H:%M}",
            f"{drill_h:.1f}",
            u.depth_plain(depth),
            "DRL",
            f"Drilled {hole} in hole from {u.depth_plain(start_md)} to {u.depth_plain(depth)} {u.depth_unit}",
        ]
    )
    t += timedelta(hours=drill_h)
    remarks: list[str] = []
    if ev:
        problem = _problem_sentence(ev, u, rng)
        remarks.append(problem + ".")
        rows.append(
            [
                f"{t:%H:%M}",
                f"{t + timedelta(hours=0.5):%H:%M}",
                "0.5",
                u.depth_plain(depth),
                _CODES[ev.event_type],
                problem,
            ]
        )
        t += timedelta(hours=0.5)
        for mit in ev.mitigations:
            ok = mit.outcome == "success"
            action = _action_sentence(mit.action_code, u, rng, ev)
            outcome = _outcome_sentence(ev, ok, rng)
            rows.append(
                [
                    f"{t:%H:%M}",
                    f"{t + timedelta(hours=mit.npt_hours):%H:%M}",
                    f"{mit.npt_hours:.1f}",
                    u.depth_plain(depth),
                    _CODES[ev.event_type],
                    f"{action} - {outcome}",
                ]
            )
            remarks.append(f"{action}: {outcome}.")
            t += timedelta(hours=mit.npt_hours)
        remarks.append(f"Total NPT {ev.total_npt_hours:.1f} hrs.")
    rest = max(0.5, 24 - (t - day.replace(hour=0, minute=0)).total_seconds() / 3600)
    rows.append(
        [
            f"{t:%H:%M}",
            "24:00",
            f"{rest:.1f}",
            u.depth_plain(depth),
            "CIRC",
            "Circulated and conditioned mud",
        ]
    )
    pdf.grid(
        ["From", "To", "Hrs", f"Depth ({u.depth_unit})", "Code", "Operation"],
        rows,
        [14, 14, 11, 20, 20, 101],
    )
    pdf.section("REMARKS")
    pdf.line_text(
        " ".join(remarks) if remarks else "Normal drilling operations. No problems reported."
    )
    pdf.section("MUD")
    pdf.line_text(
        f"Mud type: {_mud_type(well, depth)}    MW: {u.mw(mw)}    Funnel viscosity: {int(rng.uniform(42, 60))} s/qt"
    )
    return bytes(pdf.output())


def render_wcr(well: Well, rng: np.random.Generator) -> bytes:
    u = _Units(well.units)
    pdf = _Report("WELL COMPLETION REPORT")
    pdf.add_page()
    pdf.section("1. WELL DATA")
    for line in (
        f"Well: {well.name}",
        f"Field: {sm.FIELD_NAME}",
        f"Location (WGS84): lat {well.lat:.6f}, lon {well.lon:.6f}",
        f"Ground level elevation: {well.gl_elev_m:.1f} m above MSL    RKB elevation: {well.rkb_elev_m:.1f} m above MSL",
        f"Spud date: {well.spud}    Completion date: {well.completion or 'n/a'}    Rig: {well.rig}",
        f"Total depth: {u.depth(well.td_md_m, rng)} MD    Well type: {well.well_type}    Profile: {well.profile}",
        f"Depth reference: RKB. Units: {'metric' if u.metric else 'oilfield (ft, ppg, bbl)'}",
    ):
        pdf.line_text(line)
    pdf.section("2. FORMATION TOPS")
    pdf.grid(
        [
            "Formation",
            f"Top MD ({u.depth_unit})",
            f"Top TVD ({u.depth_unit})",
            f"Top TVDSS ({u.depth_unit})",
        ],
        [
            [
                _fm(t.formation, rng),
                u.depth_plain(t.top_md_m),
                u.depth_plain(t.top_tvd_m),
                u.depth_plain(t.top_tvdss_m),
            ]
            for t in well.tops
        ],
        [60, 40, 40, 40],
    )
    pdf.section("3. CASING AND CEMENTING")
    pdf.grid(
        [
            "Casing (in)",
            "Hole (in)",
            f"Shoe MD ({u.depth_unit})",
            f"Cement top MD ({u.depth_unit})",
            "Returns",
        ],
        [
            [
                c.od_label,
                c.hole_label,
                u.depth_plain(c.shoe_md_m),
                u.depth_plain(c.cement_top_md_m),
                c.returns,
            ]
            for c in well.casing
        ],
        [30, 30, 40, 45, 35],
    )
    pdf.section("4. MUD PROGRAMME")
    pdf.grid(
        [f"Interval ({u.depth_unit})", "Hole (in)", "Mud type", "Mud weight"],
        [
            [
                f"{u.depth_plain(m.md_from_m)} - {u.depth_plain(m.md_to_m)}",
                m.hole_label,
                m.mud_type,
                u.mw(m.mw_sg),
            ]
            for m in well.mud
        ],
        [45, 30, 55, 50],
    )
    pdf.section("5. DRILLING PROBLEMS AND LESSONS")
    if not well.events:
        pdf.line_text("No significant drilling problems were recorded.")
    for ev in well.events:
        actions = "; ".join(
            f"{_action_sentence(m.action_code, u, rng, ev)} ({_outcome_sentence(ev, m.outcome == 'success', rng)}, {m.npt_hours:.1f} hrs)"
            for m in ev.mitigations
        )
        pdf.line_text(
            f"- {ev.start[:10]}: {_problem_sentence(ev, u, rng)}. Actions: {actions}. NPT {ev.total_npt_hours:.1f} hrs."
        )
    return bytes(pdf.output())


def scan(pdf_bytes: bytes, rng: np.random.Generator, dpi: int = 200) -> bytes:
    """Rasterise every page, add slight rotation, blur and noise, and re-save image-only."""
    doc = pdfium.PdfDocument(pdf_bytes)
    images: list[Image.Image] = []
    for page in doc:
        img = page.render(scale=dpi / 72).to_pil().convert("L")
        img = img.rotate(
            float(rng.uniform(-0.8, 0.8)), resample=Image.Resampling.BILINEAR, fillcolor=255
        )
        arr = np.asarray(img, dtype=np.float32) + rng.normal(0, 9, size=(img.height, img.width))
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(0.5)
        )
        images.append(img)
    doc.close()
    out = io.BytesIO()
    images[0].save(
        out,
        "PDF",
        resolution=dpi,
        save_all=True,
        append_images=images[1:],
        creationDate=FIXED_PDF_DATE.timetuple(),
        modDate=FIXED_PDF_DATE.timetuple(),
    )
    return out.getvalue()


def write_documents(
    field: SyntheticField, out_dir: Path, max_event_ddrs_per_well: int = 6
) -> list[GeneratedDoc]:
    out_dir.mkdir(parents=True, exist_ok=True)
    docs: list[GeneratedDoc] = []
    for well in field.wells:
        if well.status == "planned":
            continue
        rng = _rng(well.index, DOC_PURPOSE)
        spud = datetime.fromisoformat(well.spud)
        report_no = 1
        items: list[tuple[str, Event | None, datetime]] = [
            ("DDR", None, spud + timedelta(days=int(rng.integers(2, 8))))
        ]
        for event in well.events[:max_event_ddrs_per_well]:
            items.append(("DDR", event, datetime.fromisoformat(event.start)))
        for kind, ev, day in items:
            data = render_ddr(well, ev, report_no, day, rng)
            docs.append(
                _save(
                    out_dir,
                    well,
                    f"{kind}-R{report_no:02d}",
                    day.date().isoformat(),
                    data,
                    [ev.event_id] if ev else [],
                    rng,
                )
            )
            report_no += 1
        if well.status == "completed":
            data = render_wcr(well, rng)
            docs.append(
                _save(
                    out_dir,
                    well,
                    "WCR",
                    well.completion or well.spud,
                    data,
                    [e.event_id for e in well.events],
                    rng,
                )
            )
    (out_dir / "documents.json").write_text(json.dumps([d.__dict__ for d in docs], indent=1))
    return docs


def _save(
    out: Path,
    well: Well,
    kind: str,
    day: str,
    data: bytes,
    event_ids: list[str],
    rng: np.random.Generator,
) -> GeneratedDoc:
    scanned = bool(rng.random() < SCANNED_FRACTION)
    if scanned:
        data = scan(data, rng)
    # The report number keeps two reports from the same well and day from sharing a name.
    name = f"{well.name}_{kind}_{day}{'_scan' if scanned else ''}.pdf"
    (out / name).write_bytes(data)
    return GeneratedDoc(name, well.name, kind.split("-")[0], scanned, day, event_ids)


def _formation_at(well: Well, md: float) -> str:
    name = well.tops[0].formation
    for t in well.tops:
        if t.top_md_m <= md:
            name = t.formation
    return name


def _hole_label(well: Well, md: float) -> str:
    for m in well.mud:
        if m.md_from_m <= md <= m.md_to_m:
            return m.hole_label
    return well.mud[-1].hole_label


def _mw_at(well: Well, md: float) -> float:
    for m in well.mud:
        if m.md_from_m <= md <= m.md_to_m:
            return m.mw_sg
    return well.mud[-1].mw_sg


def _mud_type(well: Well, md: float) -> str:
    for m in well.mud:
        if m.md_from_m <= md <= m.md_to_m:
            return m.mud_type
    return well.mud[-1].mud_type
