# Security & Privacy Controls

| Control | Implementation | Verification |
|---|---|---|
| Secrets | Environment variables only; `.env` git-ignored; `.env.example` placeholders | `git ls-files \| grep -i env` |
| Security headers | Strict CSP (`script-src 'self'`, `style-src 'self'`, `frame-ancestors 'none'`), `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `COOP`, `HSTS` (prod) | `tests/security/test_headers.py` |
| No inline JS/CSS | All scripts/styles in `public/static/`; `textContent` DOM creation only | `tests/accessibility/test_pages.py` |
| Input validation | Pydantic `extra="forbid"`, numeric bounds, 16 KB body limit, 500-char chat limit | `tests/api/test_assistant_chat.py`, `tests/api/test_reports_and_admin.py` |
| CSRF / origin | `verify_same_origin` on all state-changing POSTs; no auth cookies | `tests/security/test_reports_security.py`, `tests/api/test_assistant_chat.py` |
| Privacy & IP | `HMAC-SHA256(APP_SECRET, ip + UTC date)`; raw IPs never stored; URLs/emails/phones rejected in reports | `tests/security/test_reports_security.py`, `tests/unit/test_report_service.py` |
| Prompt injection | Delimited `USER_MESSAGE` and `USER_REPORTS` blocks, system rules, output grounding validator | `tests/unit/test_assistant_service.py`, `tests/unit/test_assistant_components.py` |
| Admin auth | `Authorization: Bearer <ADMIN_TOKEN>` via `hmac.compare_digest`; 404 if unset | `tests/security/test_reports_security.py` |
| Firestore rules | Server-only service account; `firestore.rules` denies all client reads/writes | `firestore.rules`, `tests/unit/test_firestore_store.py` |
| Logging | Structured JSON metadata only (`intent`, `answer_mode`, `latency_ms`); never logs message/report text or raw IP | `app/services/assistant_service.py` |
