# Testing Strategy
All unit and integration tests run offline without network access using `respx` and in-memory test doubles.
Quality gate is enforced via `python scripts/check.py`.
