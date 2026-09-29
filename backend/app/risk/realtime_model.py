"""S7b real-time classifiers: "is this problem developing in the next 30 minutes?"

One gradient-boosted tree model per event type (scikit-learn's histogram GBDT, the LightGBM
algorithm without its system OpenMP dependency, ADR-B18), isotonic calibration fitted on
out-of-fold predictions, and occlusion attributions for the top drivers.

Trained on a SYNTHETIC field (app/synthetic/realtime.py) of wells outside any seeded field,
so the seeded wells are never in training. Honesty note (master plan §7b): scores on this
data measure recovery of planted precursors, not accuracy on Assam wells.
"""

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.model_selection import GroupKFold

from app.risk import features as feats
from app.synthetic import model as sm
from app.synthetic import realtime as rt
from app.synthetic.generator import Well, generate

MODEL_TYPES = ("LOSS", "KICK", "STUCK", "TORQUE", "OVERP", "BALLING")
HORIZON_STEPS = 180  # positive = the event starts within the next 30 min
EVAL_EVERY = 6  # one training row per minute
MODEL_VERSION = "rt-hgb-v1"
TRAINING_WELLS_FROM = 61  # well indices above any seeded field (seed --wells ≤ 60)

# What a textbook threshold on one feature would flag (the baseline for PR-AUC).
PHYSICS_BASELINE = {
    "LOSS": ("imb_5", -1.0),
    "KICK": ("imb_5", 1.0),
    "STUCK": ("torque_rel", 1.0),
    "TORQUE": ("torque_std_rel", 1.0),
    "OVERP": ("gas_rel", 1.0),
    "BALLING": ("rop_rel", -1.0),
}


@dataclass
class Row:
    well: str
    episode: int
    x: np.ndarray
    label: str | None  # event type starting within the horizon, else None
    steps_to_event: int | None


def _hole_in(label: str) -> float:
    whole, _, frac = label.partition("-")
    num, _, den = frac.partition("/")
    return float(whole) + (float(num) / float(den) if den else 0.0)


def episodes_for(n_wells: int, first_index: int, seed: int = 0) -> list[rt.Episode]:
    """Event episodes for real-time event types plus two normal windows per well."""
    fld = generate(first_index + n_wells)
    return episodes_of(fld.wells[first_index - 1 : first_index - 1 + n_wells], seed)


def episodes_of(wells: list[Well], seed: int = 0) -> list[rt.Episode]:
    out: list[rt.Episode] = []
    for w in wells:
        if w.status != "completed":
            continue
        rng = np.random.default_rng([sm.SEED, 7, w.index, seed])
        for ev in w.events:
            if ev.event_type not in rt.REALTIME_TYPES:
                continue
            out.append(
                rt.event_episode(
                    rng,
                    w.name,
                    ev.event_id,
                    ev.event_type,
                    ev.md_m,
                    datetime.fromisoformat(ev.start),
                    ev.formation,
                    _hole_in(ev.hole_size),
                    ev.mw_sg,
                )
            )
        for k in range(2):
            depth = float(rng.uniform(600, 3200))
            hole = 12.25 if depth < 2300 else 8.5
            out.append(
                rt.normal_episode(rng, w.name, depth, datetime(2015, 1, 1 + k), hole, 1.2 + 0.1 * k)
            )
    return out


def rows_of(ep: rt.Episode, episode: int) -> list[Row]:
    start = ep.planted[0].start if ep.planted else ep.n
    lead = ep.planted[0].lead_steps if ep.planted else 0
    et = ep.planted[0].event_type if ep.planted else None
    idx = []
    labels: list[tuple[str | None, int | None]] = []
    for i in range(feats.MIN_HISTORY, min(start, ep.n), EVAL_EVERY):
        to = start - i
        if et and HORIZON_STEPS < to <= lead:
            continue  # the precursor has begun but is outside the horizon: neither label
        idx.append(i)
        labels.append((et, to) if et and to <= HORIZON_STEPS else (None, None))
    if not idx:
        return []
    x = feats.compute(ep.data, np.array(idx), ep.hole_size_in)
    return [Row(ep.well, episode, x[k], labels[k][0], labels[k][1]) for k in range(len(idx))]


@dataclass
class TypeModel:
    clf: HistGradientBoostingClassifier
    iso: IsotonicRegression
    threshold: float  # calibrated probability that raises an alert
    medians: np.ndarray  # feature medians of negative rows (for occlusion attributions)

    def prob(self, x: np.ndarray) -> np.ndarray:
        raw = self.clf.predict_proba(np.atleast_2d(x))[:, 1]
        return np.asarray(self.iso.predict(raw), dtype=float)


@dataclass
class ModelBundle:
    version: str
    models: dict[str, TypeModel]
    metrics: dict[str, Any] = field(default_factory=dict)

    def score(self, x: np.ndarray) -> dict[str, float]:
        return {t: float(m.prob(x)[0]) for t, m in self.models.items()}

    def drivers(self, x: np.ndarray, event_type: str, top: int = 3) -> list[dict[str, Any]]:
        """Occlusion attribution: how much the probability drops when one feature is reset
        to its typical (negative-class median) value. Not SHAP; says so in the UI."""
        m = self.models[event_type]
        base = float(m.prob(x)[0])
        trials = np.repeat(np.atleast_2d(x), len(feats.FEATURES), axis=0)
        for j in range(len(feats.FEATURES)):
            trials[j, j] = m.medians[j]
        drops = base - m.prob(trials)
        order = np.argsort(-drops)[:top]
        return [
            {
                "feature": feats.FEATURES[j],
                "label": feats.LABELS[feats.FEATURES[j]],
                "value": None if np.isnan(x[j]) else round(float(x[j]), 3),
                "typical": round(float(m.medians[j]), 3),
                "contribution": round(float(drops[j]), 3),
            }
            for j in order
            if drops[j] > 0.005
        ]

    def dumps(self) -> bytes:
        buf = io.BytesIO()
        joblib.dump(self, buf, compress=3)
        return buf.getvalue()

    @staticmethod
    def loads(data: bytes) -> "ModelBundle":
        # Our own artefact from our own bucket (trusted input: joblib unpickles).
        bundle = joblib.load(io.BytesIO(data))
        assert isinstance(bundle, ModelBundle)
        return bundle


def _clf() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=150, learning_rate=0.08, max_leaf_nodes=15, l2_regularization=1.0, random_state=0
    )


def _threshold_for(p_neg: np.ndarray, hours_normal: float, alarms_per_12h: float = 1.0) -> float:
    """Lowest probability that keeps alarms on precursor-free time at ≤ 1 per 12 h, counting
    one alarm per minute-row above it (conservative: no hysteresis credit)."""
    allowed = max(1, int(alarms_per_12h * hours_normal / 12))
    if len(p_neg) <= allowed:
        return 0.5
    return float(max(0.2, np.sort(p_neg)[-allowed - 1] + 1e-6))


def train(rows: list[Row], folds: int = 5) -> ModelBundle:
    """Grouped (by well) out-of-fold evaluation, then final models on all rows."""
    x = np.vstack([r.x for r in rows])
    groups = np.array([r.well for r in rows])
    labels = np.array([r.label or "" for r in rows])
    hours_normal = float(np.sum(labels == "")) * EVAL_EVERY * rt.DT_S / 3600
    models: dict[str, TypeModel] = {}
    metrics: dict[str, Any] = {
        "rows": len(rows),
        "wells": len(set(groups)),
        "hours_without_precursor": round(hours_normal, 1),
        "types": {},
    }
    for et in MODEL_TYPES:
        y = (labels == et).astype(int)
        if y.sum() < 10:
            continue
        oof = np.zeros(len(y))
        for tr, te in GroupKFold(n_splits=folds).split(x, y, groups):
            oof[te] = _clf().fit(x[tr], y[tr]).predict_proba(x[te])[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(oof, y)
        cal = iso.predict(oof)
        thr = _threshold_for(cal[labels == ""], hours_normal)
        feat, sign = PHYSICS_BASELINE[et]
        base_score = np.nan_to_num(sign * x[:, feats.FEATURES.index(feat)], nan=-1e9)
        metrics["types"][et] = _type_metrics(rows, labels, y, cal, base_score, thr, hours_normal)
        clf = _clf().fit(x, y)
        models[et] = TypeModel(clf, iso, thr, np.nanmedian(x[y == 0], axis=0))
    return ModelBundle(MODEL_VERSION, models, metrics)


def _type_metrics(
    rows: list[Row],
    labels: np.ndarray,
    y: np.ndarray,
    cal: np.ndarray,
    base_score: np.ndarray,
    thr: float,
    hours_normal: float,
) -> dict[str, Any]:
    """PR-AUC against chance and a one-feature physics threshold, false alarms per 12 h of
    precursor-free time, events caught inside the 30-min horizon and the median lead."""
    by_episode: dict[int, list[tuple[int, float]]] = {}
    for k in np.flatnonzero(y):
        r = rows[k]
        by_episode.setdefault(r.episode, []).append((r.steps_to_event or 0, float(cal[k])))
    leads = [
        max(to for to, p in pts if p >= thr) * rt.DT_S / 60
        for pts in by_episode.values()
        if any(p >= thr for _, p in pts)
    ]
    false_alarms = int(np.sum(cal[labels == ""] >= thr))
    other = (labels != "") & (y == 0)
    return {
        "positives": int(y.sum()),
        "pr_auc": round(float(average_precision_score(y, cal)), 4),
        "pr_auc_physics_threshold": round(float(average_precision_score(y, base_score)), 4),
        "pr_auc_chance": round(float(y.mean()), 4),
        "brier": round(float(brier_score_loss(y, cal)), 5),
        "threshold": round(thr, 4),
        "false_alarms_per_12h": round(false_alarms / max(hours_normal, 1e-9) * 12, 3),
        # Share of *other* problems' precursor minutes on which this model fires too.
        "fires_on_other_types": round(float(np.mean(cal[other] >= thr)), 4),
        "events": len(by_episode),
        "events_caught": len(leads),
        "median_lead_min": round(float(np.median(leads)), 1) if leads else None,
    }


def evaluate(bundle: ModelBundle, rows: list[Row]) -> dict[str, Any]:
    """Score a trained bundle on rows from wells it never saw, at its own thresholds."""
    x = np.vstack([r.x for r in rows])
    labels = np.array([r.label or "" for r in rows])
    hours_normal = float(np.sum(labels == "")) * EVAL_EVERY * rt.DT_S / 3600
    out: dict[str, Any] = {
        "rows": len(rows),
        "wells": len({r.well for r in rows}),
        "hours_without_precursor": round(hours_normal, 1),
        "types": {},
    }
    for et, m in bundle.models.items():
        y = (labels == et).astype(int)
        if not y.any():
            continue
        feat, sign = PHYSICS_BASELINE[et]
        base_score = np.nan_to_num(sign * x[:, feats.FEATURES.index(feat)], nan=-1e9)
        out["types"][et] = _type_metrics(
            rows, labels, y, m.prob(x), base_score, m.threshold, hours_normal
        )
    return out
