"""
Bug generator (orchestrator).

The single entry point the router calls. Wires together, in order:
  evidence_merger -> prompt_builder -> gemini_client -> response_parser
  -> confidence_engine

Every step above is independently swappable/testable; this file just
sequences them. This is the only place that needs to change if the
pipeline gains a step (e.g. a caching layer, or a second-pass LLM call).
"""
from app.config import settings
from app.schemas.bug_schema import GenerateBugResponse
from app.services.evidence.evidence_merger import MergedEvidence
from app.services.bug.confidence_engine import apply_confidence_rules
from app.services.llm.gemini_client import GeminiClient
from app.services.llm.prompt_builder import build_prompt
from app.services.llm.response_parser import parse_bug_report

# A single shared client instance (Gemini SDK configuration is cheap and
# stateless per-request, but this avoids re-reading settings every call).
_gemini_client = GeminiClient()


def generate_bug_report(evidence: MergedEvidence) -> GenerateBugResponse:
    prompt = build_prompt(evidence)

    raw_response = _gemini_client.generate_bug_json(
        prompt=prompt,
        image_bytes=evidence.screenshot.data,
        image_mime_type=evidence.screenshot.content_type,
    )

    bug_report = parse_bug_report(raw_response)
    bug_report, low_confidence = apply_confidence_rules(bug_report)

    return GenerateBugResponse(
        bug_report=bug_report,
        low_confidence=low_confidence,
        model_used=settings.gemini_model,
    )
