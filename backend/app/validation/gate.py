"""The baseline validation gate — business_rules.md §13's concrete abort
mechanism: "A non-empty violation list raises an exception caught only
at the top level, which halts the process before the anomaly-injection
module is even imported... a code path that is never reached."

`run_baseline_gate` is called synchronously by
`data_generation/generator.py`'s entrypoint, inspects the real return
value of `run_all_rules`, and raises `BaselineValidationFailed` if any
of the 16 categories reports a single violation — "zero violations"
means literally zero, not "the structural ones." There is no flag to
bypass this; the only way past it is for the report to genuinely be
clean.
"""

from sqlalchemy.orm import Session

from app.validation.runner import run_all_rules


class BaselineValidationFailed(Exception):
    """Raised by run_baseline_gate() when the generated baseline has any
    validation violation. Catching this anywhere other than the top-level
    entrypoint defeats its purpose — do not catch-and-continue."""

    def __init__(self, report: dict):
        self.report = report
        violation_count = report["total_violations"]
        first_few = report["findings"][:5]
        super().__init__(
            f"Baseline validation failed with {violation_count} violation(s) — "
            f"anomaly injection must not proceed. First findings: {first_few}"
        )


def run_baseline_gate(session: Session, dataset_mode: str) -> dict:
    report = run_all_rules(session, dataset_mode=dataset_mode, report_mode="baseline")
    if report["total_violations"] > 0:
        raise BaselineValidationFailed(report)
    return report
