"""Hybrid search (S5): full-text + dense retrieval fused with reciprocal rank fusion.

1. Filters (well + radius, formation, event type, document type, report date) restrict
   both legs before ranking.
2. Lexical leg: PostgreSQL full text, OR over the query's lexemes, ranked by how many of
   them a chunk contains, then ``ts_rank_cd``.
3. Dense leg: cosine distance on ``chunk.embedding`` (HNSW), same embedder as the query.
4. Relevance floor: a lexical hit must contain at least half the query's lexemes; a dense
   hit must reach the provider's minimum cosine similarity. If nothing clears the floor
   the response says "no record found" rather than showing weak matches.
5. RRF (k = 60) fuses the surviving ranks. Scores are relevance, never probabilities.

Lessons are the cards of events whose evidence lies in the returned passages, so every
card shown is backed by a passage on the same screen.
"""

import math
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.api.v1.schemas.search import LessonCard, Passage, SearchResponse
from app.db.models.documents import EMBEDDING_DIM
from app.extract.evidence import event_evidence_refs
from app.geo.service import surface_offsets
from app.normalise.formations import formation_ids
from app.normalise.wells_service import get_well_or_404
from app.search.embed import get_embedder

RRF_K = 60
CANDIDATES = 50
# Minimum cosine similarity for a dense-only hit, per embedder family. The hash embedder
# scores short queries against long chunks low even when relevant; a learned model does
# not. Calibrated on the synthetic corpus (docs/BACKEND_PLAN.md, V-B14).
DENSE_FLOOR = {"hash": 0.22, "ollama": 0.45}
SNIPPET_CHARS = 480


@dataclass(frozen=True)
class SearchQuery:
    q: str
    well_id: int | None = None
    radius_km: float | None = None
    formation: str | None = None
    event_types: tuple[str, ...] = ()
    doc_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 10


def _scope_sql(sq: SearchQuery, session: Session) -> tuple[str, dict[str, Any]]:
    """SQL conditions over ``c`` (chunk) and ``d`` (document), with their parameters."""
    where = ["d.ingest_status IN ('processed', 'needs_review')"]
    params: dict[str, Any] = {}
    if sq.well_id is not None:
        get_well_or_404(session, sq.well_id)
        wells = [sq.well_id]
        if sq.radius_km:
            wells += [o.well_id for o in surface_offsets(session, sq.well_id, sq.radius_km * 1000)]
        where.append("c.well_id = ANY(:wells)")
        params["wells"] = wells
    if sq.doc_type:
        where.append("d.doc_type = :doc_type")
        params["doc_type"] = sq.doc_type.upper()
    if sq.date_from:
        where.append("d.report_date >= :date_from")
        params["date_from"] = sq.date_from
    if sq.date_to:
        where.append("d.report_date <= :date_to")
        params["date_to"] = sq.date_to
    if sq.event_types:
        where.append(
            "EXISTS (SELECT 1 FROM event_evidence ee JOIN event e ON e.id = ee.event_id"
            " WHERE ee.span_id = ANY(c.span_ids) AND e.status = 'active'"
            " AND e.event_type = ANY(:types))"
        )
        params["types"] = list(sq.event_types)
    if sq.formation:
        fids, names = formation_ids(session, sq.formation)
        where.append(
            "(EXISTS (SELECT 1 FROM event_evidence ee JOIN event e ON e.id = ee.event_id"
            " WHERE ee.span_id = ANY(c.span_ids) AND e.status = 'active'"
            " AND e.formation_id = ANY(:fids)) OR c.text ~* :fm_regex)"
        )
        params["fids"] = fids
        params["fm_regex"] = r"\m(" + "|".join(re.escape(n) for n in names) + r")\M"
    return " AND ".join(where), params


def _lexemes(session: Session, q: str) -> list[str]:
    return list(
        session.scalar(text("SELECT tsvector_to_array(to_tsvector('english', :q))"), {"q": q}) or []
    )


def _lexical(
    session: Session, lexes: list[str], where: str, params: dict[str, Any]
) -> list[tuple[int, int]]:
    """(chunk id, lexemes matched) for chunks clearing the floor, best first."""
    if not lexes:
        return []
    need = max(1, math.ceil(len(lexes) / 2))
    rows = session.execute(
        text(
            f"""
            WITH q AS (
                SELECT to_tsquery('simple', array_to_string(
                           ARRAY(SELECT quote_literal(l) FROM unnest(CAST(:lexes AS text[])) l),
                           ' | ')) AS tq
            )
            SELECT c.id,
                   (SELECT count(*) FROM unnest(CAST(:lexes AS text[])) l
                     WHERE c.tsv @@ CAST(quote_literal(l) AS tsquery)) AS hits,
                   ts_rank_cd(c.tsv, q.tq) AS rank
            FROM chunk c JOIN document d ON d.id = c.document_id, q
            WHERE c.tsv @@ q.tq AND {where}
            ORDER BY hits DESC, rank DESC, c.id
            LIMIT :n
            """  # noqa: S608 (where is built from fixed fragments; values are bound)
        ),
        {**params, "lexes": lexes, "n": CANDIDATES},
    ).all()
    return [(r.id, int(r.hits)) for r in rows if r.hits >= need]


def _dense(
    session: Session, qvec: list[float], embedder_name: str, where: str, params: dict[str, Any]
) -> list[tuple[int, float]]:
    floor = DENSE_FLOOR.get(embedder_name.split(":")[0], 0.5)
    session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    vec = "[" + ",".join(f"{v:.6f}" for v in qvec) + "]"
    rows = session.execute(
        text(
            f"""
            SELECT c.id, 1 - (c.embedding <=> CAST(:qv AS vector({EMBEDDING_DIM}))) AS sim
            FROM chunk c JOIN document d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL AND c.embedded_with = :emb AND {where}
            ORDER BY c.embedding <=> CAST(:qv AS vector({EMBEDDING_DIM}))
            LIMIT :n
            """  # noqa: S608
        ),
        {**params, "qv": vec, "emb": embedder_name, "n": CANDIDATES},
    ).all()
    return [(r.id, float(r.sim)) for r in rows if r.sim >= floor]


def highlight(snippet: str, lexes: list[str]) -> list[tuple[int, int]]:
    """[start, end) ranges of words starting with a query lexeme (stems are prefixes)."""
    if not lexes:
        return []
    pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(lx) for lx in sorted(lexes, key=len, reverse=True)) + r")\w*",
        re.I,
    )
    return [(m.start(), m.end()) for m in pattern.finditer(snippet)]


def make_snippet(full: str, lexes: list[str]) -> tuple[str, list[tuple[int, int]]]:
    hits = highlight(full, lexes)
    if len(full) <= SNIPPET_CHARS:
        return full, hits
    start = max(0, (hits[0][0] if hits else 0) - 120)
    if start:
        space = full.find(" ", start)
        start = space + 1 if 0 <= space < start + 30 else start
    end = min(len(full), start + SNIPPET_CHARS)
    snippet = ("… " if start else "") + full[start:end].strip() + (" …" if end < len(full) else "")
    return snippet, highlight(snippet, lexes)


def run(session: Session, sq: SearchQuery) -> SearchResponse:
    t0 = time.perf_counter()
    where, params = _scope_sql(sq, session)
    lexes = _lexemes(session, sq.q)
    embedder = get_embedder()
    lexical = _lexical(session, lexes, where, params)
    dense = _dense(session, embedder.embed([sq.q])[0], embedder.name, where, params)

    ranks: dict[int, dict[str, int]] = {}
    for rank, (cid, _) in enumerate(lexical, start=1):
        ranks.setdefault(cid, {})["lexical"] = rank
    for rank, (cid, _) in enumerate(dense, start=1):
        ranks.setdefault(cid, {})["dense"] = rank
    scored = sorted(
        ((sum(1 / (RRF_K + r) for r in rr.values()), cid) for cid, rr in ranks.items()),
        key=lambda x: (-x[0], x[1]),
    )[: sq.limit]
    passages = _passages(session, scored, ranks, lexes)
    lessons = _lessons(session, [p.chunk_id for p in passages], sq, params)
    return SearchResponse(
        query=sq.q,
        passages=passages,
        lessons=lessons,
        no_record_found=not passages,
        embedding_provider=embedder.name,
        took_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


def _passages(
    session: Session,
    scored: list[tuple[float, int]],
    ranks: dict[int, dict[str, int]],
    lexes: list[str],
) -> list[Passage]:
    if not scored:
        return []
    ids = [cid for _, cid in scored]
    rows = {
        r.id: r
        for r in session.execute(
            text(
                """
                SELECT c.id, c.document_id, c.page_from, c.page_to, c.span_ids, c.text,
                       d.filename, d.doc_type, d.synthetic, c.well_id, w.canonical_name
                FROM chunk c JOIN document d ON d.id = c.document_id
                LEFT JOIN well w ON w.id = c.well_id
                WHERE c.id = ANY(:ids)
                """
            ),
            {"ids": ids},
        ).all()
    }
    out = []
    for score, cid in scored:
        r = rows[cid]
        snippet, hl = make_snippet(r.text, lexes)
        out.append(
            Passage(
                chunk_id=cid,
                document_id=r.document_id,
                filename=r.filename,
                doc_type=r.doc_type,
                well_id=r.well_id,
                well_name=r.canonical_name,
                synthetic=r.synthetic,
                page_from=r.page_from,
                page_to=r.page_to,
                span_ids=list(r.span_ids),
                snippet=snippet,
                highlights=hl,
                score=round(score, 6),
                lexical_rank=ranks[cid].get("lexical"),
                dense_rank=ranks[cid].get("dense"),
            )
        )
    return out


def _lessons(
    session: Session, chunk_ids: list[int], sq: SearchQuery, params: dict[str, Any]
) -> list[LessonCard]:
    if not chunk_ids:
        return []
    conds = ["e.status = 'active'", "e.lesson_card IS NOT NULL"]
    if sq.event_types:
        conds.append("e.event_type = ANY(:types)")
    if sq.formation:
        conds.append("e.formation_id = ANY(:fids)")
    if "wells" in params:
        conds.append("e.well_id = ANY(:wells)")
    rows = session.execute(
        text(
            f"""
            SELECT e.id, min(array_position(CAST(:chunks AS bigint[]), c.id)) AS pos
            FROM event e
            JOIN event_evidence ee ON ee.event_id = e.id
            JOIN chunk c ON ee.span_id = ANY(c.span_ids)
            WHERE c.id = ANY(:chunks) AND {" AND ".join(conds)}
            GROUP BY e.id
            ORDER BY pos, e.id
            LIMIT :n
            """  # noqa: S608
        ).bindparams(bindparam("chunks")),
        {**params, "chunks": chunk_ids, "n": sq.limit},
    ).all()
    return lesson_cards(session, [r.id for r in rows])


def lesson_cards(session: Session, ids: list[int]) -> list[LessonCard]:
    """Lesson cards for these events, in the order given (events without a card skipped)."""
    if not ids:
        return []
    details = {
        r.id: r
        for r in session.execute(
            text(
                """
                SELECT e.id, e.well_id, w.canonical_name, w.synthetic, e.event_type,
                       f.name AS formation, e.md_m, e.tvdss_m, e.lesson_card,
                       e.confidence, e.verified
                FROM event e JOIN well w ON w.id = e.well_id
                LEFT JOIN formation f ON f.id = e.formation_id
                WHERE e.id = ANY(:ids) AND e.lesson_card IS NOT NULL
                """
            ),
            {"ids": ids},
        ).all()
    }
    evidence = event_evidence_refs(session, list(details))
    out = []
    for eid in ids:
        r = details.get(eid)
        if r is None:
            continue
        card = r.lesson_card or {}
        out.append(
            LessonCard(
                event_id=eid,
                well_id=r.well_id,
                well_name=r.canonical_name,
                synthetic=r.synthetic,
                event_type=r.event_type,
                formation=r.formation,
                md_m=r.md_m,
                tvdss_m=r.tvdss_m,
                problem=card.get("problem", ""),
                likely_cause=card.get("likely_cause"),
                action_taken=card.get("action_taken"),
                outcome=card.get("outcome"),
                lesson=card.get("lesson"),
                confidence=r.confidence,
                verified=r.verified,
                evidence=evidence.get(eid, []),
            )
        )
    return out
