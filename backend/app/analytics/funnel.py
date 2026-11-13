"""Recruitment pipeline analytics — Phase 9, implementation_plan.md's
Phase 9 row and workflow.md §8 ("Pandas jobs in analytics/ query the
SQLite DB directly (read-only session)"). Every function here takes an
already-open `Session` and only ever reads — `architecture.md` §2:
"analytics/ never writes to the database." No function in this module
ever imports or reads `AnomalyLabel` (anomaly_summary.py is the one place
ground truth is handled, and only in its separate, explicitly-labeled
evaluation path).

**Calculation definitions used, and where each comes from:**

- **Funnel conversion rate** = count reaching stage N / count reaching
  stage N-1 (`implementation_plan.md`'s "Dashboard metrics, defined
  calculations"). "Reached stage X" means: for `Applied`, every
  `Application` row for the scope (every application starts there by
  construction); for every later stage, the count of *distinct*
  applications with at least one `ApplicationStageHistory` row whose
  `to_stage` is X — this is an "ever reached," not "currently at,"
  count, so a later `Withdrawn`/`Rejected` application still counts at
  every stage it actually passed through (workflow.md §8: "Requisition
  funnel (Applied→Screening→Interviewing→Offer→Hired per
  requisition/dept)").
- **Time-in-stage** = mean(`changed_at` deltas per `ApplicationStageHistory`
  pair), per `implementation_plan.md`'s definition verbatim. For each
  application, consecutive history rows (ordered by `changed_at`) are
  paired; the delta between a pair is attributed to the *first* row's
  `to_stage` (the stage occupied during that interval), in days. An
  application's current (most recent) stage contributes no delta — it
  hasn't left that stage yet, so "time in stage" for it isn't known.
- **Offer acceptance rate** = count(`Accepted`) / count(`Extended`)
  (`implementation_plan.md`, verbatim). **Interpretive clarification,
  flagged (not silent):** `Offer.status` is mutually exclusive — an
  offer that reached `Accepted` no longer has `status == "Extended"`, so
  a literal current-status count of `"Extended"` would exclude exactly
  the offers the numerator counts, making the ratio self-defeating. The
  structurally equivalent, persistent proxy for "ever reached Extended"
  is `Offer.extended_at IS NOT NULL` (required and permanently set once
  `status` first reaches `Extended`, `Accepted`, or `Declined` —
  `ck_offer_extended_at_required`); that is what "count(Extended)" means
  here.
- **Interviewer load** and **duplicate-submission rate** are named only
  narratively in `workflow.md` §8 ("interviews per interviewer per week
  vs. availability"; "`ApplicationSubmissionAttempt` rows per canonical
  `Application`, by department/requisition") with no prior-approved exact
  formula — unlike the three above, no phase previously froze a formula
  for these two. The definitions below are this phase's own reasonable,
  explicitly-flagged implementation of that narrative, not an invented
  departure from an existing approved formula: interviewer load buckets
  `Interview.scheduled_start`/`InterviewerAvailabilitySlot.start_datetime`
  into ISO `(year, week)` and reports
  `interview_count / availability_slot_count` per interviewer per week
  (`None` when that week has zero availability slots, to avoid a
  divide-by-zero or a misleading infinite load); duplicate-submission
  rate is literally `count(ApplicationSubmissionAttempt) /
  count(canonical Application)` per requisition (and rolled up by
  department), exactly as the narrative names it.

All grouping/division handles an empty dataset or a zero denominator by
returning an empty list/`None` rather than raising (requirement 6) —
covered by `tests/test_analytics.py`'s empty-database cases.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    ApplicationSubmissionAttempt,
    Interview,
    InterviewerAvailabilitySlot,
    JobRequisition,
    Offer,
)
from app.db.models.history import ApplicationStageHistory

FUNNEL_STAGES = ("Applied", "Screening", "Interviewing", "Offer", "Hired")


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def compute_requisition_funnel(session: Session, group_by: str | None = None) -> list[dict]:
    """Returns one funnel row per group (`group_by="requisition"`,
    `group_by="department"`, or `None` for one overall row), each with
    per-stage reached-counts and stage-to-stage conversion rates.
    """
    if group_by not in (None, "requisition", "department"):
        raise ValueError(f"unknown group_by {group_by!r}")

    applications = list(session.execute(select(Application)).scalars())
    requisitions = {r.requisition_id: r for r in session.execute(select(JobRequisition)).scalars()}

    def _group_key(app: Application) -> str | None:
        if group_by is None:
            return "ALL"
        if group_by == "requisition":
            return app.requisition_id
        req = requisitions.get(app.requisition_id)
        return req.department_id if req is not None else None

    apps_by_group: dict[str, list[Application]] = defaultdict(list)
    for app in applications:
        key = _group_key(app)
        if key is not None:
            apps_by_group[key].append(app)

    app_ids_by_group = {key: {a.application_id for a in apps} for key, apps in apps_by_group.items()}

    history_to_stage_by_app: dict[str, set[str]] = defaultdict(set)
    for h in session.execute(select(ApplicationStageHistory)).scalars():
        history_to_stage_by_app[h.application_id].add(h.to_stage)

    rows = []
    for key, apps in sorted(apps_by_group.items()):
        app_ids = app_ids_by_group[key]
        reached = {"Applied": len(app_ids)}
        for stage in FUNNEL_STAGES[1:]:
            reached[stage] = sum(
                1 for app_id in app_ids if stage in history_to_stage_by_app.get(app_id, set())
            )

        conversion_rates = {}
        for i in range(1, len(FUNNEL_STAGES)):
            prev_stage, stage = FUNNEL_STAGES[i - 1], FUNNEL_STAGES[i]
            conversion_rates[f"{prev_stage}->{stage}"] = _safe_ratio(reached[stage], reached[prev_stage])

        rows.append({
            "group_by": group_by,
            "group_key": key,
            "reached_counts": reached,
            "conversion_rates": conversion_rates,
        })

    return rows


def compute_requisition_status_distribution(session: Session) -> list[dict]:
    """Returns `{"status": str, "count": int}` for every `JobRequisition.
    status` value present — added this phase (10) to power the Executive
    Dashboard's requisition-status chart; a pure count-by-status read,
    same category as every other function in this module, not a new
    business rule."""
    counts: dict[str, int] = defaultdict(int)
    for req in session.execute(select(JobRequisition)).scalars():
        counts[req.status] += 1
    return [{"status": status, "count": count} for status, count in sorted(counts.items())]


def compute_time_in_stage(session: Session) -> dict:
    """Returns `{stage: {"mean_days": float, "sample_size": int}}` for
    every stage that has at least one measurable interval. A stage with
    zero completed intervals is omitted, not reported as `0.0` (which
    would misleadingly claim "instant" rather than "unmeasured")."""
    rows_by_app: dict[str, list[ApplicationStageHistory]] = defaultdict(list)
    for h in session.execute(select(ApplicationStageHistory)).scalars():
        rows_by_app[h.application_id].append(h)

    deltas_by_stage: dict[str, list[float]] = defaultdict(list)
    for rows in rows_by_app.values():
        ordered = sorted(rows, key=lambda r: r.changed_at)
        for prev, nxt in zip(ordered, ordered[1:]):
            delta_days = (nxt.changed_at - prev.changed_at).total_seconds() / 86400.0
            deltas_by_stage[prev.to_stage].append(delta_days)

    return {
        stage: {"mean_days": sum(deltas) / len(deltas), "sample_size": len(deltas)}
        for stage, deltas in sorted(deltas_by_stage.items())
    }


def compute_interviewer_load(session: Session) -> list[dict]:
    """Returns one row per `(interviewer_id, iso_year, iso_week)` that has
    at least one scheduled interview or one availability slot, with
    `interview_count`, `availability_slot_count`, and `load_ratio`
    (`None` when `availability_slot_count == 0`)."""
    interviews_by_key: dict[tuple[str, int, int], int] = defaultdict(int)
    for iv in session.execute(select(Interview)).scalars():
        iso = iv.scheduled_start.isocalendar()
        interviews_by_key[(iv.interviewer_id, iso[0], iso[1])] += 1

    slots_by_key: dict[tuple[str, int, int], int] = defaultdict(int)
    for slot in session.execute(select(InterviewerAvailabilitySlot)).scalars():
        iso = slot.start_datetime.isocalendar()
        slots_by_key[(slot.interviewer_id, iso[0], iso[1])] += 1

    all_keys = set(interviews_by_key) | set(slots_by_key)
    rows = []
    for interviewer_id, iso_year, iso_week in sorted(all_keys):
        interview_count = interviews_by_key.get((interviewer_id, iso_year, iso_week), 0)
        slot_count = slots_by_key.get((interviewer_id, iso_year, iso_week), 0)
        rows.append({
            "interviewer_id": interviewer_id,
            "iso_year": iso_year,
            "iso_week": iso_week,
            "interview_count": interview_count,
            "availability_slot_count": slot_count,
            "load_ratio": _safe_ratio(interview_count, slot_count),
        })
    return rows


def compute_offer_acceptance_rate(session: Session, group_by: str | None = None) -> list[dict]:
    """Returns one row per group (`group_by="department"`,
    `group_by="level"`, or `None` for one overall row) with
    `accepted_count`, `extended_count` (see module docstring for the
    `extended_at IS NOT NULL` proxy), and `acceptance_rate`."""
    if group_by not in (None, "department", "level"):
        raise ValueError(f"unknown group_by {group_by!r}")

    applications = {a.application_id: a for a in session.execute(select(Application)).scalars()}
    requisitions = {r.requisition_id: r for r in session.execute(select(JobRequisition)).scalars()}
    offers = list(session.execute(select(Offer)).scalars())

    def _group_key(offer: Offer) -> str | None:
        if group_by is None:
            return "ALL"
        app = applications.get(offer.application_id)
        if app is None:
            return None
        req = requisitions.get(app.requisition_id)
        if req is None:
            return None
        return req.department_id if group_by == "department" else req.level

    accepted_by_group: dict[str, int] = defaultdict(int)
    extended_by_group: dict[str, int] = defaultdict(int)
    for offer in offers:
        key = _group_key(offer)
        if key is None:
            continue
        if offer.extended_at is not None:
            extended_by_group[key] += 1
        if offer.status == "Accepted":
            accepted_by_group[key] += 1

    rows = []
    for key in sorted(set(accepted_by_group) | set(extended_by_group)):
        accepted = accepted_by_group.get(key, 0)
        extended = extended_by_group.get(key, 0)
        rows.append({
            "group_by": group_by,
            "group_key": key,
            "accepted_count": accepted,
            "extended_count": extended,
            "acceptance_rate": _safe_ratio(accepted, extended),
        })
    return rows


def compute_duplicate_submission_rate(session: Session, group_by: str = "requisition") -> list[dict]:
    """Returns one row per requisition (`group_by="requisition"`) or
    department (`group_by="department"`) with `attempt_count`,
    `canonical_application_count`, and `attempts_per_application`."""
    if group_by not in ("requisition", "department"):
        raise ValueError(f"unknown group_by {group_by!r}")

    applications = list(session.execute(select(Application)).scalars())
    attempts = list(session.execute(select(ApplicationSubmissionAttempt)).scalars())
    requisitions = {r.requisition_id: r for r in session.execute(select(JobRequisition)).scalars()}

    def _key_for_requisition_id(requisition_id: str) -> str | None:
        if group_by == "requisition":
            return requisition_id
        req = requisitions.get(requisition_id)
        return req.department_id if req is not None else None

    app_counts: dict[str, int] = defaultdict(int)
    for app in applications:
        key = _key_for_requisition_id(app.requisition_id)
        if key is not None:
            app_counts[key] += 1

    attempt_counts: dict[str, int] = defaultdict(int)
    for attempt in attempts:
        key = _key_for_requisition_id(attempt.requisition_id)
        if key is not None:
            attempt_counts[key] += 1

    rows = []
    for key in sorted(set(app_counts) | set(attempt_counts)):
        apps = app_counts.get(key, 0)
        atts = attempt_counts.get(key, 0)
        rows.append({
            "group_by": group_by,
            "group_key": key,
            "attempt_count": atts,
            "canonical_application_count": apps,
            "attempts_per_application": _safe_ratio(atts, apps),
        })
    return rows


def build_funnel_report(session: Session) -> dict:
    """Bundles every metric in this module into one deterministic,
    JSON-serializable dict — the shape `export_funnel_report()` writes to
    disk. Pure computation, no I/O."""
    return {
        "requisition_funnel_overall": compute_requisition_funnel(session, group_by=None),
        "requisition_funnel_by_requisition": compute_requisition_funnel(session, group_by="requisition"),
        "requisition_funnel_by_department": compute_requisition_funnel(session, group_by="department"),
        "requisition_status_distribution": compute_requisition_status_distribution(session),
        "time_in_stage": compute_time_in_stage(session),
        "interviewer_load": compute_interviewer_load(session),
        "offer_acceptance_rate_overall": compute_offer_acceptance_rate(session, group_by=None),
        "offer_acceptance_rate_by_department": compute_offer_acceptance_rate(session, group_by="department"),
        "offer_acceptance_rate_by_level": compute_offer_acceptance_rate(session, group_by="level"),
        "duplicate_submission_rate_by_requisition": compute_duplicate_submission_rate(session, group_by="requisition"),
        "duplicate_submission_rate_by_department": compute_duplicate_submission_rate(session, group_by="department"),
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def export_funnel_report(session: Session, output_dir: Path) -> dict:
    """Writes `build_funnel_report()`'s output to `output_dir`:
    `funnel_report.json` (the full bundle) plus one CSV per tabular
    (list-of-dict) metric, for spreadsheet-friendly review alongside the
    dataset exports `data_generation/export.py` already produces
    (requirement 5 — "documented CSV, JSON ... export functionality").
    Returns the same dict that was written, for callers that want it
    in-process without re-reading the file.

    **Limitation, flagged:** `requisition_funnel_*`'s `reached_counts`/
    `conversion_rates` fields are nested dicts — the CSV writer renders
    them as a Python-repr string in one cell (still valid, comma-safe
    CSV; just not a per-stage-column breakdown). The JSON file is the
    complete, structured source; the CSVs are a convenience export, not
    the authoritative format.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = build_funnel_report(session)
    (output_dir / "funnel_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    for key, value in report.items():
        if isinstance(value, list):
            _write_csv(output_dir / f"{key}.csv", value)

    return report
