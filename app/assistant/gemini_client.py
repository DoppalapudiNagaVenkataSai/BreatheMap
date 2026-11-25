"""Gemini client protocol, real google-genai async implementation, and offline fake."""

import asyncio
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.assistant.prompts import SYSTEM_INSTRUCTION
from app.constants import GEMINI_TIMEOUT


class AssistantDraft(BaseModel):
    """Structured JSON output schema returned by Gemini."""

    summary: str
    recommendation: str
    reasons: list[str]
    caveats: list[str]
    used_fact_ids: list[str]


@runtime_checkable
class GeminiClient(Protocol):
    """Protocol for single-shot structured Gemini generation."""

    async def generate(self, user_content: str) -> tuple[AssistantDraft | None, str | None]:
        """Return (draft, error_reason_code). Never raises on provider failure."""
        ...


class RealGeminiClient:
    """Async Google GenAI SDK client with 20s timeout and no retries."""

    def __init__(self, api_key: str, model: str = "gemini-3.8-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate(self, user_content: str) -> tuple[AssistantDraft | None, str | None]:
        """Perform a single async generate_content call with structured output."""
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=AssistantDraft,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            max_output_tokens=1024,
        )
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=user_content,
                    config=config,
                ),
                timeout=GEMINI_TIMEOUT,
            )
            raw_text = response.text or ""
            draft = AssistantDraft.model_validate_json(raw_text)
            return draft, None
        except TimeoutError:
            return None, "gemini_timeout"
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg or "resource_exhausted" in msg:
                return None, "gemini_rate_limited"
            if "json" in msg or "validation" in msg:
                return None, "gemini_invalid_json"
            return None, "gemini_error"


class FakeGeminiClient:
    """Offline deterministic Gemini fake tracking exact call count."""

    def __init__(
        self,
        *,
        draft: AssistantDraft | None = None,
        error_code: str | None = None,
        handler: Callable[[str], tuple[AssistantDraft | None, str | None]] | None = None,
    ) -> None:
        self.call_count = 0
        self.last_user_content: str | None = None
        self._draft = draft
        self._error_code = error_code
        self._handler = handler

    async def generate(self, user_content: str) -> tuple[AssistantDraft | None, str | None]:
        self.call_count += 1
        self.last_user_content = user_content
        if self._handler is not None:
            return self._handler(user_content)
        if self._error_code is not None:
            return None, self._error_code
        if self._draft is not None:
            return self._draft, None
        return (
            AssistantDraft(
                summary="Estimated air conditions are available in the summary card.",
                recommendation="Check the cleanest window before heading outdoors.",
                reasons=[],
                caveats=["Modelled data; conditions can vary locally."],
                used_fact_ids=["F1"],
            ),
            None,
        )
