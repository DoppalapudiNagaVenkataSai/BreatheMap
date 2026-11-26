"""Output validator for Gemini drafts (Section 8.14)."""

import re

from app.assistant.gemini_client import AssistantDraft

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_TOKEN_NUMBER_RE = re.compile(
    r"\b(?:PM\s*2\.?5|PM\s*10|NO2|SO2|O3|CO2|K?N95|FFP2)\b", re.IGNORECASE
)
_URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
_BANNED_RE = re.compile(r"\b(safe|safest|guarantee\w*|diagnos\w*|prescri\w*|cure\w*)\b", re.I)

MAX_TOTAL_WORDS = 260
MAX_REASONS = 4
MAX_CAVEATS = 3
SMALL_ALLOWED_INT_MAX = 12


def _is_number_grounded(num_val: float, allowed_numbers: set[float]) -> bool:
    """Check if a number is <= 5 (small integer) or matches FACTS (exact or 0/1-decimal)."""
    if num_val.is_integer() and 0 <= int(num_val) <= SMALL_ALLOWED_INT_MAX:
        return True
    candidates = (num_val, round(num_val, 0), round(num_val, 1))
    return any(c in allowed_numbers for c in candidates)


def validate_draft(
    draft: AssistantDraft,
    *,
    allowed_numbers: set[float],
    valid_fact_ids: set[str],
) -> tuple[bool, str | None]:
    """Validate length, numeric grounding, banned words, fact IDs, and URLs."""
    if len(draft.reasons) > MAX_REASONS or len(draft.caveats) > MAX_CAVEATS:
        return False, "validator_list_limit"

    all_parts = [draft.summary, draft.recommendation, *draft.reasons, *draft.caveats]
    combined = " ".join(part.strip() for part in all_parts if part.strip())
    if not draft.summary.strip() or not draft.recommendation.strip():
        return False, "validator_empty_field"

    if len(combined.split()) > MAX_TOTAL_WORDS:
        return False, "validator_word_limit"

    if _URL_RE.search(combined):
        return False, "validator_url"

    if _BANNED_RE.search(combined):
        return False, "validator_banned_phrase"

    for fid in draft.used_fact_ids:
        if fid not in valid_fact_ids:
            return False, "validator_invalid_fact_id"

    sanitized_for_nums = _TOKEN_NUMBER_RE.sub("", combined)
    for match in _NUMBER_RE.findall(sanitized_for_nums):
        val = float(match)
        if not _is_number_grounded(val, allowed_numbers):
            return False, "validator_ungrounded_number"

    return True, None
