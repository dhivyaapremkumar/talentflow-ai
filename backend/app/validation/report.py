"""Shared finding/report structures — validation_strategy.md §15 (reporting
format) and §21 (the VAL-01..VAL-16 catalog). The engine is read-only: it
only ever builds and returns these structures, never mutates data
(architecture.md §2).
"""

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class Finding:
    rule_id: str
    rule_category: str
    entity_type: str
    entity_id: str
    message: str
    severity: str  # "violation" or "warning"


def finding_sort_key(f: Finding) -> tuple:
    return (f.rule_id, f.entity_type, f.entity_id, f.message)


def build_report(findings: list[Finding], mode: str, rule_ids_run: list[str]) -> dict:
    """`mode` is "baseline" or "post_injection" — a report-labeling concept
    only (validation_strategy.md §21's "Applies to" column); the rule
    functions themselves compute the same real findings regardless of mode.
    """
    sorted_findings = sorted(findings, key=finding_sort_key)
    violations = [f for f in sorted_findings if f.severity == "violation"]
    warnings = [f for f in sorted_findings if f.severity == "warning"]

    counts_by_rule: dict[str, int] = {rule_id: 0 for rule_id in rule_ids_run}
    for f in sorted_findings:
        counts_by_rule[f.rule_id] = counts_by_rule.get(f.rule_id, 0) + 1

    return {
        "mode": mode,
        "checked_at": datetime.now().isoformat(),
        "rule_ids_run": rule_ids_run,
        "total_findings": len(sorted_findings),
        "total_violations": len(violations),
        "total_warnings": len(warnings),
        "counts_by_rule": counts_by_rule,
        "findings": [asdict(f) for f in sorted_findings],
    }


def results_only(report: dict) -> dict:
    """The deterministic-content subset of a report — everything except the
    volatile `checked_at` timestamp (data_dictionary.md §17's volatile-vs-
    deterministic split, applied to validation reports specifically,
    validation_strategy.md §13). Two reports produced from identical data
    must have identical `results_only()` output, even if their
    `checked_at` values differ.
    """
    return {k: v for k, v in report.items() if k != "checked_at"}
