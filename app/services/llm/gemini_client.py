"""
Gemini client.

The ONLY file in the codebase that imports the `google.genai`
SDK. Every other service talks to this module through
`GeminiClient.generate_bug_json()`. To swap Gemini for a different LLM
later, implement a class with the same method signature here (or in a
sibling module) and update the one import in `bug_generator.py` — no
other file changes.

NOTE: This uses the newer `google-genai` SDK (package name "google-genai",
imported as `google.genai`) instead of the legacy `google-generativeai`
SDK. `google-genai` talks to the API over plain HTTP/REST and does not
pull in the compiled `grpc` extension, which avoids DLL-load issues on
machines where Application Control / WDAC policies block unsigned
native binaries (cygrpc.pyd).
"""
from __future__ import annotations

from google import genai
from google.genai import types
from fastapi import HTTPException, status

from app.config import settings


class GeminiClient:
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            # Fail loudly at call time (not import time) so the rest of
            # the app — including routes unrelated to AI — still boots
            # fine without a Gemini key configured.
            self._configured = False
            self._client = None
        else:
            self._client = genai.Client(api_key=settings.gemini_api_key)
            self._configured = True

        self._model_name = settings.gemini_model

    def generate_bug_json(self, *, prompt: str, image_bytes: bytes, image_mime_type: str) -> str:
        """Sends the prompt + screenshot to Gemini and returns the raw text response."""
        if not self._configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GEMINI_API_KEY is not configured on the server.",
            )

        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:  # noqa: BLE001 — surface any SDK/network error uniformly
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gemini request failed: {exc}",
            ) from exc

        text = getattr(response, "text", None)
        if not text:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned an empty response.",
            )
        return text