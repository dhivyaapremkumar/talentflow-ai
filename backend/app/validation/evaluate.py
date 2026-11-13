"""Phase 6 — offline ground-truth evaluation. business_rules.md §13 step
5 ("Compare detected anomalies against ground-truth labels... read-only/
diagnostic; its result never feeds back into step 4's logic"),
validation_strategy.md §17/§22.

This module is one of the small, explicitly-named exceptions to the
ground-truth non-leakage guarantee (§17: "the only code allowed to touch
ground truth, by design: validation/reconcile.py's offline evaluation
step... and the frontend's dev-only Ground Truth view") — it is the
*only* place detection output and ground truth are ever brought
together, and `validation.detect.run_detectors()` is always called and
fully finished before this module reads anything ground-truth-related,
never interleaved — a real (not aspirational) separation, since Python's
evaluation order means `run_detectors()`'s return value is already a
complete, immutable result by the time a single ground-truth row is read.

**TN is deliberately never computed.** validation_strategy.md §22 defines
TP/FP/FN/precision/recall/F1 only — no formula or "valid negative
population" for any of the five anomaly types exists anywhere in the
approved design. Constructing one (e.g., "every Interview row not
flagged and not labeled") would require choosing an unapproved
denominator — the natural candidate population for most types (all
`Interview`/`Offer`/`Application` rows) is dominated by rows that were
never at risk of that specific anomaly in the first place, so counting
them as confirmed negatives would silently invent a definition the
design never specified and produce a misleadingly inflated, imbalanced
"accuracy" figure. `tn` is reported as `None` with `TN_NOT_COMPUTABLE_NOTE`
explaining why, for every type and overall — never fabricated, never
silently omitted.
"""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnomalyLabel
from app.validation.detect import ANOMALY_TYPES, run_detectors

TN_NOT_COMPUTABLE_NOTE = (
    "Not computed. The approved evaluation design (validation_strategy.md Sec22) "
    "defines TP/FP/FN/precision/recall/F1 only - it does not define a valid negative "
    "population for any anomaly type. The natural candidate population for each type "
    "(e.g. every Interview/Offer/Application row) is dominated by rows that were never "
    "at risk of that specific anomaly, so treating them as confirmed negatives would "
    "invent an unapproved denominator and produce a misleading, inflated accuracy-like "
    "figure rather than a reliable metric."
)


@dataclass(frozen=True)
class TypeMetrics:
    anomaly_type: str
    tp: int
    fp: int
    fn: int
    tn: None
    precision: float | None
    recall: float | None
    f1: float | None
    true_positive_ids: list[str]
    false_positive_ids: list[str]
    false_negative_ids: list[str]
    tn_note: str


def _safe_div(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _f1(precision: float | None, recall: float | None) -> float | None:
    """Documented convention: F1 is undefined (None) if either precision
    or recall is itself undefined (one factor of the harmonic mean
    missing, not just zero) — except when both are defined and exactly
    zero, in which case F1 is explicitly 0.0 (not a 0/0 crash, not None)."""
    if precision is None or recall is None:
        return None
    if precision == 0 and recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _metrics_for_type(anomaly_type: str, detected_ids: set[str], truth_ids: set[str]) -> TypeMetrics:
    # Dedup by entity_id, not by Finding count — a detector that fires
    # more than once for the same entity (e.g. for two independent
    # reasons) must still count as exactly one detection of that entity,
    # never two.
    tp_ids = sorted(detected_ids & truth_ids)
    fp_ids = sorted(detected_ids - truth_ids)
    fn_ids = sorted(truth_ids - detected_ids)

    tp, fp, fn = len(tp_ids), len(fp_ids), len(fn_ids)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)

    return TypeMetrics(
        anomaly_type=anomaly_type,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=None,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
        true_positive_ids=tp_ids,
        false_positive_ids=fp_ids,
        false_negative_ids=fn_ids,
        tn_note=TN_NOT_COMPUTABLE_NOTE,
    )


def evaluate(session: Session) -> dict:
    """Runs detection (step 4), then — and only then — reads ground
    truth and compares (step 5). Returns a JSON-able report: per-type
    metrics plus an overall aggregate (micro-averaged: TP/FP/FN summed
    across all five types first, then precision/recall/F1 computed once
    over the sums — not a per-type average — so one large-count type
    cannot be diluted or amplified by averaging across types of very
    different sizes)."""
    detections = run_detectors(session)

    ground_truth_by_type: dict[str, set[str]] = {t: set() for t in ANOMALY_TYPES}
    for label in session.execute(select(AnomalyLabel)).scalars():
        if label.anomaly_type in ground_truth_by_type:
            ground_truth_by_type[label.anomaly_type].add(label.entity_id)

    per_type: list[TypeMetrics] = []
    total_tp = total_fp = total_fn = 0
    for anomaly_type in ANOMALY_TYPES:
        detected_ids = {f.entity_id for f in detections[anomaly_type]}
        metrics = _metrics_for_type(anomaly_type, detected_ids, ground_truth_by_type[anomaly_type])
        per_type.append(metrics)
        total_tp += metrics.tp
        total_fp += metrics.fp
        total_fn += metrics.fn

    overall_precision = _safe_div(total_tp, total_tp + total_fp)
    overall_recall = _safe_div(total_tp, total_tp + total_fn)

    return {
        "per_type": [asdict(m) for m in per_type],
        "overall": {
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
            "tn": None,
            "precision": overall_precision,
            "recall": overall_recall,
            "f1": _f1(overall_precision, overall_recall),
            "tn_note": TN_NOT_COMPUTABLE_NOTE,
            "aggregation_method": "micro-average (TP/FP/FN summed across all five "
            "anomaly types before computing precision/recall/F1 once over the sums)",
        },
    }


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def print_human_readable_summary(mode: str, report: dict) -> None:
    print(f"Evaluation report ({mode})")
    print(f"{'Type':<30} {'TP':>4} {'FP':>4} {'FN':>4} {'Prec':>6} {'Rec':>6} {'F1':>6}")
    for t in report["per_type"]:
        print(
            f"{t['anomaly_type']:<30} {t['tp']:>4} {t['fp']:>4} {t['fn']:>4} "
            f"{_format_metric(t['precision']):>6} {_format_metric(t['recall']):>6} "
            f"{_format_metric(t['f1']):>6}"
        )
    o = report["overall"]
    print(
        f"{'OVERALL (micro-avg)':<30} {o['tp']:>4} {o['fp']:>4} {o['fn']:>4} "
        f"{_format_metric(o['precision']):>6} {_format_metric(o['recall']):>6} "
        f"{_format_metric(o['f1']):>6}"
    )
    print(f"TN: not computed for any type or overall — {TN_NOT_COMPUTABLE_NOTE}")


def main():
    from app.db.session import make_engine

    parser = argparse.ArgumentParser(description="TalentFlow AI offline ground-truth evaluation")
    parser.add_argument("--mode", choices=["starter", "full"], required=True)
    parser.add_argument("--db-path", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    db_path = args.db_path or f"data/talentflow_{args.mode}.db"
    engine = make_engine(db_path)
    with Session(engine) as session:
        report = evaluate(session)

    output_path = Path(args.output) if args.output else Path(f"data/evaluation_reports/{args.mode}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print_human_readable_summary(args.mode, report)
    print(f"\nJSON report written to {output_path}")


if __name__ == "__main__":
    main()
