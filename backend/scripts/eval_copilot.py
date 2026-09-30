"""Score the copilot (S10) on a question set generated from the SYNTHETIC ground truth
(master plan §13.3 shape: 20 lookup, 15 multi-well aggregation, 5 ledger, 10 unanswerable).

Gold answers come from the generator's truth file (events, the reports that describe them,
planted treatment success rates), not from the copilot's own tools. Automatic scoring:

- **lookup** (20): "What <problem> did <well> have in the <formation>?" Correct when the
  answer names the event's depth (± 15 m) and cites a report that describes it.
  **Retrieval Recall@5** (document level): the search tool, given the question text alone
  with no filters, returns a report describing the event among its top five pages.
- **aggregation** (15): "Which wells had <problem> in the <formation>?" Precision and recall
  of the well names in the answer against the truth; correct when both are 1.
- **ledger** (5): "What worked for <problem> (in <formation>)?" Correct when the first action
  named is the ledger's top-ranked action; also reported: whether that is the *planted*
  best among the actions ranked.
- **unanswerable** (10): wells that do not exist, off-topic questions, problems never
  recorded in a formation, and facts the records do not hold. Correct = the answer refuses
  or says "no record".
- **citation faithfulness**: every cited report page in every answer line that names a
  well must come from that well, and its text must mention the problem the line states.

Needs the seeded stack (database + object storage). Deterministic (rules engine).

    cd backend && uv run python scripts/eval_copilot.py
"""

import json
import random
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.copilot.engine import run
from app.copilot.planner import extract, vocab
from app.copilot.tools import EVENT_LABELS, search_documents
from app.core.auth import DEV_USER
from app.db.models import Document, Page, Well
from app.db.session import session_scope
from app.risk.assets import get_object

OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"
SEED = 121
# Words a report page uses for each problem (for the faithfulness check).
PAGE_WORDS = {
    "LOSS": r"lost circulation|losses|loss",
    "KICK": r"kick|influx|well control",
    "STUCK": r"stuck|sticking",
    "TIGHT": r"tight|overpull",
    "TORQUE": r"torque",
    "INSTAB": r"instabil|cavings|sloughing",
    "BALLING": r"ball",
    "OVERP": r"overpressure|gas",
    "GAS": r"gas",
    "CEMENT": r"cement",
}
LABEL_TO_TYPE = {v: k for k, v in EVENT_LABELS.items()} | {"kicks": "KICK"}


def ask(session: Any, q: str) -> dict[str, Any]:
    out: dict[str, Any] = {"question": q, "tools": []}
    for ev in run(session, DEV_USER, q):
        if ev["type"] == "plan":
            out["intent"] = ev["intent"]
        elif ev["type"] == "tool":
            out["tools"].append(ev["name"])
        elif ev["type"] == "citations":
            out["citations"] = ev["items"]
        elif ev["type"] == "done":
            out.update(answer=ev["answer"], refused=ev["refused"], took_ms=ev["took_ms"])
    return out


def main() -> None:
    rnd = random.Random(SEED)  # noqa: S311 (sampling questions, not cryptography)
    truth = json.loads(get_object("synthetic/truth.json"))
    wells = {w["name"]: w for w in truth["wells"] if w["status"] == "completed"}
    doc_by_event: dict[str, list[str]] = defaultdict(list)
    for d in truth["documents"]:
        for eid in d["event_ids"]:
            doc_by_event[eid].append(d["file"])
    events = [
        (w["name"], e) for w in wells.values() for e in w["events"] if doc_by_event[e["event_id"]]
    ]
    questions: list[dict[str, Any]] = []

    # Lookup: one event of a type in a formation, in a well that had only that one there.
    count: dict[tuple[str, str, str], int] = defaultdict(int)
    for wn, e in events:
        count[(wn, e["event_type"], e["formation"])] += 1
    single = [(wn, e) for wn, e in events if count[(wn, e["event_type"], e["formation"])] == 1]
    for wn, e in rnd.sample(single, 20):
        what = EVENT_LABELS[e["event_type"]]
        questions.append(
            {
                "category": "lookup",
                "q": f"What {what} did {wn} have in the {e['formation']}?",
                "gold_md": e["md_m"],
                "gold_docs": doc_by_event[e["event_id"]],
                "gold_well": wn,
            }
        )

    # Aggregation: which wells had a problem in a formation.
    combos: dict[tuple[str, str], set[str]] = defaultdict(set)
    for wn, e in events:
        combos[(e["event_type"], e["formation"])].add(wn)
    # The synthetic field has 14 (problem, formation) pairs with events: all of them, plus
    # one radius question below.
    for et, fm in sorted(combos):
        questions.append(
            {
                "category": "aggregation",
                "q": f"Which wells had {EVENT_LABELS[et]} in the {fm}?",
                "gold_wells": sorted(combos[(et, fm)]),
            }
        )

    radius_q = {
        "category": "aggregation",
        "q": "Which wells within 5 km of SYN-ASM-41 had stuck pipe?",
    }

    # Ledger.
    for et, fm in [("LOSS", "Tipam Sandstone"), ("LOSS", None), ("STUCK", "Barail"),
                   ("STUCK", None), ("BALLING", None)]:  # fmt: skip
        where = f" in the {fm}" if fm else ""
        questions.append(
            {
                "category": "ledger",
                "q": f"What worked for {EVENT_LABELS[et]}{where}?",
                "event_type": et,
                "formation": fm,
            }
        )

    # Unanswerable.
    never = sorted(
        {(et, fm["name"]) for et in ("KICK", "BALLING") for fm in truth["formations"]} - set(combos)
    )
    unans = [
        "What happened on SYN-ASM-77?",
        "Did SYN-ASM-58 have losses in the Tipam?",
        "Which treatments worked on well XYZ-ABC-1?",
        "What is the oil price today?",
        "Will it rain at the rig tomorrow?",
        "Write a poem about drilling rigs",
        f"Which wells had {EVENT_LABELS[never[0][0]]} in the {never[0][1]}?",
        f"Which wells had {EVENT_LABELS[never[-1][0]]} in the {never[-1][1]}?",
        "Who was the company man on SYN-ASM-05?",
        "What brand of drill bit did SYN-ASM-12 use?",
    ]
    questions += [{"category": "unanswerable", "q": q} for q in unans]
    # Held out: written after the search-coverage rule was added (because of two failures
    # above) but before running it, to check that the rule generalises both ways.
    heldout_answerable = [
        ("Which reports mention a pipe release pill?", "pipe release pill"),
        ("Show reports where detergent was pumped", "detergent"),
        ("Where was lubricant added to the mud?", "lubricant"),
        ("Find reports describing a squeeze job", "squeeze"),
        ("Which reports describe using the driller's method?", "driller"),
    ]
    questions += [
        {"category": "heldout_answerable", "q": q, "phrase": ph} for q, ph in heldout_answerable
    ]
    questions += [
        {"category": "heldout_unanswerable", "q": q}
        for q in (
            "Which contractor supplied the mud chemicals?",
            "What was the rig cost per day on SYN-ASM-20?",
            "Who was the toolpusher on the night shift at SYN-ASM-03?",
            "What was the ambient temperature at the rig site during the cement job report?",
            "How many people were in the drilling crew on SYN-ASM-10?",
        )
    ]
    # Held out 2 (Part 7, written 2026-09-30 BEFORE the cross-intent coverage rule was coded;
    # the first held-out set above had already been diagnosed, so it is development data now).
    # Answerable ones span every intent and are scored "answered with a citation".
    questions += [
        {"category": "heldout2_answerable", "q": q}
        for q in (
            "Which wells used a cement plug to cure losses?",
            "Where was jarring needed to free stuck pipe?",
            "Which reports mention reduced mud weight after losses?",
            "Show reports where LCM was pumped in the Tipam",
            "What happened on SYN-ASM-12?",
            "What are the drilling risks in the Barail for SYN-ASM-41?",
            "What worked for stuck pipe in the Barail?",
            "Which wells within 5 km of SYN-ASM-41 had losses?",
        )
    ]
    questions += [
        {"category": "heldout2_unanswerable", "q": q}
        for q in (
            "What was the daily mud cost on SYN-ASM-08?",
            "Which service company ran the wireline logs on SYN-ASM-15?",
            "What was the wind speed during the rig move to SYN-ASM-22?",
            "How many litres of diesel did the rig burn on SYN-ASM-30?",
            "What was the name of the drilling supervisor on SYN-ASM-14 during the losses?",
            "What was the contract day rate for the rig that drilled SYN-ASM-02?",
            "Which hospital treated injuries on SYN-ASM-19?",
            "What was the humidity in the mud lab on SYN-ASM-11?",
        )
    ]

    with session_scope() as s:
        doc_ids = {f: i for f, i in s.execute(select(Document.filename, Document.id))}
        doc_well = {
            d: w
            for d, w in s.execute(
                select(Document.id, Well.canonical_name).join(Well, Well.id == Document.well_id)
            )
        }
        voc = vocab(s)
        page_text = {
            (d, p): t for d, p, t in s.execute(select(Page.document_id, Page.page_no, Page.text))
        }
        from app.geo.service import surface_offsets
        from app.ledger.service import ledger

        wid41 = s.scalar(select(Well.id).where(Well.canonical_name == "SYN-ASM-41"))
        near = {o.name for o in surface_offsets(s, wid41, 5000)} if wid41 else set()
        stuck = {wn for wn, e in events if e["event_type"] == "STUCK"}
        radius_q["gold_wells"] = sorted(near & stuck)
        questions.insert(20 + len(combos), radius_q)

        rows: list[dict[str, Any]] = []
        faithful = checked = 0
        unfaithful: list[str] = []
        for qd in questions:
            a = ask(s, qd["q"])
            row: dict[str, Any] = {
                **qd,
                **{k: a.get(k) for k in ("intent", "tools", "refused", "took_ms")},
            }
            answer = a.get("answer", "")
            cites = {c["n"]: c for c in a.get("citations", [])}
            cat = qd["category"]
            if cat == "lookup":
                gold_ids = {doc_ids[f] for f in qd["gold_docs"] if f in doc_ids}
                depths = [float(x.replace(",", "")) for x in re.findall(r"([\d,]+) m MD", answer)]
                cited_docs = {c["document_id"] for c in cites.values() if c["document_id"]}
                row["correct"] = bool(
                    any(abs(d - qd["gold_md"]) <= 15 for d in depths) and cited_docs & gold_ids
                )
                hits = search_documents(s, qd["q"]).data.get("top_pages", [])
                row["recall_at_5"] = any(d in gold_ids for d, _ in hits[:5])
                # As the copilot searches: with the well and formation it read from the question.
                ent = extract(qd["q"], voc)
                hits_f = search_documents(
                    s,
                    qd["q"],
                    well_id=ent.wells[0][0] if ent.wells else None,
                    formation=ent.formation,
                ).data.get("top_pages", [])
                row["recall_at_5_filtered"] = any(d in gold_ids for d, _ in hits_f[:5])
            elif cat == "aggregation":
                named = set(re.findall(r"SYN-ASM-\d+", answer.split("\n")[0]))
                gold = set(qd["gold_wells"])
                row["precision"] = round(len(named & gold) / len(named), 3) if named else 0.0
                row["recall"] = round(len(named & gold) / len(gold), 3)
                row["correct"] = named == gold
            elif cat == "ledger":
                led = ledger(s, event_type=qd["event_type"], formation=qd["formation"])
                top = led.ranked[0].action_label if led.ranked else None
                first = re.search(r"\n([^:\n]+): worked", answer)
                row["correct"] = bool(top and first and first.group(1) == top)
                planted = truth["planted_success"][qd["event_type"]]
                ranked = [e.action_code for e in led.ranked]
                best = max(
                    (c for c in ranked if c in planted), key=lambda c: planted[c], default=None
                )
                row["top_is_planted_best_of_ranked"] = bool(ranked and ranked[0] == best)
            elif cat == "heldout_answerable":
                row["correct"] = not a.get("refused") and qd["phrase"] in answer.lower()
            elif cat == "heldout2_answerable":
                row["correct"] = not a.get("refused") and bool(cites)
            else:
                row["correct"] = bool(a.get("refused")) or answer.lower().startswith("no record")
            # Faithfulness of cited pages, line by line.
            for line in answer.split("\n"):
                m = re.match(r"(SYN-ASM-\d+): (.+?) at ", line)
                if not m or m.group(2) not in LABEL_TO_TYPE:
                    continue
                et = LABEL_TO_TYPE[m.group(2)]
                for n in (int(x) for x in re.findall(r"\[(\d+)\]", line)):
                    c = cites.get(n)
                    if not c or c["kind"] != "page":
                        continue
                    checked += 1
                    text = page_text.get((c["document_id"], c["page_no"]), "")
                    ok = doc_well.get(c["document_id"]) == m.group(1) and re.search(
                        PAGE_WORDS[et], text, re.I
                    )
                    if ok:
                        faithful += 1
                    else:
                        unfaithful.append(f"{qd['q']} → [{n}] {c['label']} doc {c['document_id']}")
            rows.append(row)

    def rate(cat: str, key: str = "correct") -> float:
        rs = [r for r in rows if r["category"] == cat]
        return round(sum(bool(r[key]) for r in rs) / len(rs), 3)

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (developer tool on PATH)
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    agg = [r for r in rows if r["category"] == "aggregation"]
    result = {
        "what": "Copilot (S10, rules engine) on a question set generated from SYNTHETIC truth",
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "commit": commit or None,
        "engine": "rules",
        "questions": len(rows),
        "scores": {
            "lookup_correct": rate("lookup"),
            "retrieval_recall_at_5_doc_level": rate("lookup", "recall_at_5"),
            "retrieval_recall_at_5_with_planner_filters": rate("lookup", "recall_at_5_filtered"),
            "aggregation_exact": rate("aggregation"),
            "aggregation_precision_mean": round(statistics.mean(r["precision"] for r in agg), 3),
            "aggregation_recall_mean": round(statistics.mean(r["recall"] for r in agg), 3),
            "ledger_top_action_matches_ledger": rate("ledger"),
            "ledger_top_is_planted_best_of_ranked": rate("ledger", "top_is_planted_best_of_ranked"),
            "unanswerable_correct_refusal": rate("unanswerable"),
            "heldout_unanswerable_correct_refusal": rate("heldout_unanswerable"),
            "heldout_answerable_answered_with_the_phrase": rate("heldout_answerable"),
            "heldout2_unanswerable_correct_refusal": rate("heldout2_unanswerable"),
            "heldout2_answerable_answered_with_citation": rate("heldout2_answerable"),
            "citation_faithfulness": round(faithful / checked, 4) if checked else None,
            "citations_checked": checked,
        },
        "targets_master_plan_13_3": {
            "recall_at_5": 0.85,
            "citation_faithfulness": 0.95,
            "correct_refusal": 0.90,
        },
        "latency_ms": {
            "median": round(statistics.median(r["took_ms"] for r in rows), 1),
            "max": round(max(r["took_ms"] for r in rows), 1),
        },
        "unfaithful_examples": unfaithful[:10],
        "failures": [
            {k: r.get(k) for k in ("category", "q", "intent", "tools", "refused")}
            for r in rows
            if not r["correct"]
        ],
        "rows": rows,
        "notes": [
            "SYNTHETIC: questions and gold answers are generated from the seeded field's "
            "truth; report phrasing is our generator's fixed vocabulary, so these are upper "
            "bounds, not the §13.3 manual evaluation on real reports.",
            "Answer correctness is scored automatically against structured gold (depth, well "
            "sets, ledger order), not on the 3-point manual scale of §13.3.",
            "Unanswerable: the search-coverage rule was added after the first run failed two "
            "questions of the original ten (1.0 on those ten is therefore tuned); the five "
            "held-out questions were written before re-running and are the honest estimate.",
            "Part 7 (V-B34): a scope check refuses questions whose focus (what/which/how "
            "many/who + noun phrase) names something the reports never mention; it applies to "
            "every intent, not only search. The first held-out set was diagnosed and so became "
            "development data. held-out 2 (8 unanswerable, 8 answerable) was committed in "
            "cac2c41 before the check was coded and run once after; the questions were written "
            "by the same developer, knowing the kind of fix planned, and n = 8 per side is small.",
            "Recall@5 without filters searches the question text alone; with planner filters "
            "is how the copilot actually searches (the well and formation it read).",
            "Faithfulness is checked for event lines (the cited page belongs to the named well "
            "and mentions the problem); quoted passages are the page text itself.",
            "The optional LLM engine is not evaluated here (no model server in the sandbox).",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"copilot_synthetic_{datetime.now(tz=UTC):%Y-%m-%d}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n")
    print(
        json.dumps(
            {k: result[k] for k in ("scores", "latency_ms", "failures", "unfaithful_examples")},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
