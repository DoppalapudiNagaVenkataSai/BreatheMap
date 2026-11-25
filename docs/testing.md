# BreatheMap Testing Guide

## Automated Quality Gates
Run all checks in one command:
```bash
python scripts/check.py
```
This runs:
1. `ruff format --check`
2. `ruff check`
3. `mypy --strict app`
4. `pytest --cov=app --cov-branch --cov-fail-under=85` (all offline: `respx` mocks, `MemoryStore`, `FakeGeminiClient`, `FakeAsyncFirestoreClient`)
5. `scripts/repo_size.py` (enforces < 9.5 MB)

## 5-Step Assistant Demo Script (Phase 9)
Enable **Delhi demo** mode in the top bar and visit `/assistant`:
1. *"Is it OK to jog at 6 PM for 40 minutes?"* -> Returns activity advice card + cleanest window.
2. Click the **Cautious** chip (or toggle child cautious mode) -> Advice shifts one level more cautious.
3. *"I'm going to New Delhi Railway Station at 10 PM — best way?"* -> Returns route comparison card with mini-map, night lighting, and departure suggestion.
4. *"How do I keep the air cleaner at home?"* -> Returns indoor air tips card.
5. *"Any smoke reported near me?"* -> Returns nearby demo community reports card.

## Provider Failure & Resilience Tests
- Air/routing/overpass outages, timeouts, and 429s are tested offline in `tests/api/test_air_and_geo.py`, `tests/integration/test_routing_providers.py`, and `tests/unit/test_assistant_service.py`.
- Firestore `StorageUnavailableError` fallback behaviour (empty read list + warning; 2 calls/min quota fallback) is tested in `tests/unit/test_firestore_store.py` and `tests/unit/test_assistant_components.py`.
