"""
Confidence engine.

Its job is purely post-processing: decide `low_confidence` from the
returned confidence_score.
"""
from app.schemas.bug_schema import BugReportAI

LOW_CONFIDENCE_THRESHOLD = 70.0


def apply_confidence_rules(bug_report: BugReportAI) -> tuple[BugReportAI, bool]:
    low_confidence = bug_report.confidence_score < LOW_CONFIDENCE_THRESHOLD
    return bug_report, low_confidence