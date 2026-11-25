"""Compact FACTS JSON and USER_REPORTS builder for grounded Gemini prompts."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_FACTS_TOKEN_BUDGET = 1500
MAX_USER_REPORTS_COUNT = 5
MAX_USER_REPORT_CHARS = 140
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class FactsBundle:
    """Structured deterministic facts passed to Gemini and the validator."""

    facts: list[dict[str, Any]] = field(default_factory=list)
    user_reports: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    emergency_number: str = "112"

    def add_fact(
        self,
        label: str,
        value: Any,
        *,
        unit: str = "",
        source: str = "modelled",
        is_estimated: bool = False,
    ) -> str:
        """Append a fact entry with sequential F-id and return its id."""
        fid = f"F{len(self.facts) + 1}"
        entry: dict[str, Any] = {
            "id": fid,
            "label": label,
            "value": value,
            "source": source,
            "is_estimated": is_estimated,
        }
        if unit:
            entry["unit"] = unit
        self.facts.append(entry)
        return fid

    def valid_ids(self) -> set[str]:
        """Return set of all valid fact IDs."""
        return {str(f["id"]) for f in self.facts}


def estimate_tokens(text: str) -> int:
    """Simple character-based token count heuristic (~4 chars per token)."""
    return (len(text) + 3) // 4


def build_facts_json(bundle: FactsBundle) -> str:
    """Serialize FactsBundle into compact JSON within the ~1,500 token budget."""
    payload: dict[str, Any] = {
        "emergency_number": bundle.emergency_number,
        "facts": list(bundle.facts),
        "warnings": list(bundle.warnings[:5]),
    }
    serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    while estimate_tokens(serialized) > MAX_FACTS_TOKEN_BUDGET and len(payload["facts"]) > 1:
        payload["facts"].pop()
        serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return serialized


def build_user_reports_block(reports: list[dict[str, Any]]) -> str:
    """Format up to 5 unverified community reports truncated to 140 chars each."""
    if not reports:
        return "none"
    lines: list[str] = []
    for rep in reports[:MAX_USER_REPORTS_COUNT]:
        cat = str(rep.get("category", "other"))
        desc = str(rep.get("description", "")).replace("\n", " ").strip()
        snippet = f"[{cat}] {desc} (Unverified community report)"
        if len(snippet) > MAX_USER_REPORT_CHARS:
            snippet = snippet[: MAX_USER_REPORT_CHARS - 1] + "…"
        lines.append(snippet)
    return "\n".join(lines)


def extract_allowed_numbers(facts_json: str) -> set[float]:
    """Extract all numeric values (plus 0/1-decimal rounded variants) from FACTS JSON."""
    allowed: set[float] = set()
    for match in _NUMBER_RE.findall(facts_json):
        val = float(match)
        allowed.add(val)
        allowed.add(round(val, 0))
        allowed.add(round(val, 1))
    return allowed
