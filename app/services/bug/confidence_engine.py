"""
Confidence engine.

Gemini itself generates dynamic follow-up questions when it's unsure
about part of the report (see prompt_builder.py) — this module never
hardcodes questions. Its job is purely post-processing:
  1. Decide `low_confidence` from the returned confidence_score.
  2. Guard-rail the follow_up_questions list (dedupe, cap length, drop
     empties) in case the LLM is verbose or repeats itself.
"""
from app.schemas.bug_schema import BugReportAI

LOW_CONFIDENCE_THRESHOLD = 70.0
MAX_FOLLOW_UP_QUESTIONS = 6


def apply_confidence_rules(bug_report: BugReportAI) -> tuple[BugReportAI, bool]:
    low_confidence = bug_report.confidence_score < LOW_CONFIDENCE_THRESHOLD

    cleaned_questions: list[str] = []
    seen = set()
    for q in bug_report.follow_up_questions:
        q_clean = q.strip()
        if not q_clean or q_clean.lower() in seen:
            continue
        seen.add(q_clean.lower())
        cleaned_questions.append(q_clean)
        if len(cleaned_questions) >= MAX_FOLLOW_UP_QUESTIONS:
            break

    bug_report.follow_up_questions = cleaned_questions
    return bug_report, low_confidence
