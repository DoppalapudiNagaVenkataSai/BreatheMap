# BreatheMap — breathe less pollution on every trip

Vertical: **Urban Air Quality Assistant** · Built with FastAPI, Leaflet, Open-Meteo, OpenStreetMap services, Google Gemini, and Firestore.

## Chosen vertical and persona
- **Vertical:** Urban Air Quality Assistant
- **Persona:** Urban residents and families navigating high-pollution episodes (such as winter smog in Delhi) — works for any city worldwide, with a built-in Delhi sample-data mode.

## The problem
An AQI number alone does not tell people what to do. Two people in the same city breathe very different amounts of pollution depending on **when** they go out, **how** they travel (walking beside traffic vs enclosed metro), **what** they are doing (resting vs jogging), and **who** is with them (children, elderly, or people with asthma).

## Approach and logic
- **Python decides, Gemini explains:** Every AQI calculation, inhaled PM2.5 dose, departure-time optimization, activity rule, and indoor tip is computed deterministically in Python. Gemini (`gemini-3.8-flash`) receives only compact `FACTS` JSON and explains them in plain English in at most one call per turn; otherwise deterministic **Quick answers** serve the exact same cards.
- **Exposure model:** Segment-by-segment inhaled PM2.5 dose ($\mu\text{g}$) combining concentration, microenvironment factor $F_{\text{mode}}$, road-proximity factor $F_{\text{road}}$, ventilation rate $V_{\text{mode}}$, and duration $\Delta t$ (see [docs/methodology.md](docs/methodology.md)).
- **Decision order:** Time of day and trip duration -> travel mode -> activity -> cautious mode.
- **Data honesty:** Clearly separates modelled data (Open-Meteo/CAMS), indicative NAQI, estimated transit modes (metro/bus/auto), volunteer OSM lighting tags, and unverified community reports.

## How the solution works
- **Air View (`/`):** Current indicative NAQI / US AQI, pollutant breakdown, cleanest & peak smog 3-hour windows, and 24-hour chart with accessible table toggle.
- **BreatheRoute (`/route`):** Multi-mode comparison (walk, cycle, car, auto, bus, metro) ranked by lowest estimated PM2.5 inhaled, night street-lighting summary, departure-time suggestion, and community reports within 200 m.
- **AI Air Assistant (`/assistant`):** Rule-based intent/slot parser, deterministic tool execution, compact `FACTS` grounding, single Gemini call with output validator, Quick-answer fallback, and quota/cache management.
- **BreatheWatch (`/watch`):** Anonymous, expiring community pollution reports with privacy filtering, 300 m / 2 h duplicate detection, "I see this too" confirmations, and 3-flag moderation.

### Request flow for an assistant question
1. `POST /api/v1/assistant/chat` validates origin, input length (1–500 chars), and per-IP rate limit.
2. `safety.py` & `parser.py` classify intent and extract time, duration, mode, activity, and destination (0 Gemini calls for static intents or missing-slot clarifications).
3. Deterministic tools (`AirService`, `RouteService`, `ReportService`, `advise`, `home_tips`, `glossary`) build response cards and a compact `FACTS` JSON payload.
4. `QuotaManager` checks daily/RPM/per-user budgets; if available, `RealGeminiClient` makes one structured-output call, verified by `validator.py` for numeric grounding and banned words.
5. On quota exhaustion, timeout, or validation failure, `fallback.py` returns a deterministic Quick answer with the same data cards.

## Problem statement alignment
| Brief element | How BreatheMap delivers it | Where |
|---|---|---|
| GenAI-powered assistant | Gemini 3.8 Flash explains decisions computed from real data, in one grounded call | `app/assistant/`, `/assistant` |
| Helps families | Cautious mode for child / elderly / asthma / pregnancy shifts advice; activity advice | `app/domain/advice.py` |
| Helps communities | BreatheWatch anonymous local reports; shown along routes and in assistant | `/watch`, `app/services/report_service.py` |
| Severe winter smog | Indicative NAQI; hourly forecast; cleanest/worst windows; Delhi demo | `/`, `app/domain/windows.py` |
| Low-emission daily routines | Mode comparison favouring lower-exposure & lower-emission choices; secondary CO2e note | `/route`, `app/domain/modes.py` |
| Indoor air quality hacks | Rule-selected home exposure tips (ventilation timing, wet mopping, filtration) | `app/domain/home_tips.py` |
| Sustainable alternatives | Metro / bus / cycle / walk alternatives compared side by side with car | `/route` cards |
| Tailored to location | Works anywhere with local timezone and AQI scale | `app/services/air_service.py` |
| Tailored to lifestyle | Activity, travel mode, time of day, trip duration, cautious mode | `app/assistant/parser.py` |
| Explains direct impact | Quantitative comparisons computed in Python and explained in plain English | `/route`, `/assistant` |

## Evaluation focus areas
| Area | Evidence |
|---|---|
| Code quality | `ruff format`, `ruff check`, `mypy --strict` on `app/` |
| Security | Strict CSP, `extra="forbid"`, same-origin POST checks, HMAC daily hashes, `firestore.rules`, `tests/security/` |
| Efficiency | L1/L2 caching, downsampled Overpass queries, single Gemini call cap, compact `FACTS` |
| Testing | 128+ offline unit, API, integration, security, and accessibility tests (`scripts/check.py`) |
| Accessibility | WCAG 2.1 AA landmarks, keyboard chips, chart/map text alternatives (`tests/accessibility/test_pages.py`) |

## Assumptions made
See [docs/assumptions.md](docs/assumptions.md) (modelled air data, indicative NAQI, illustrative exposure factors, estimated transit, incomplete OSM lighting, unverified community reports, free-tier Gemini limits, anonymous browser preferences, not medical advice).

## Data sources and attribution
- Air quality & weather: *Open-Meteo / CAMS (CC BY 4.0)*
- Routing: *© openrouteservice.org / OpenStreetMap contributors* and *FOSSGIS OSRM / OpenStreetMap contributors*
- Geocoding & lighting: *Nominatim & Overpass API / OpenStreetMap contributors*
- Map tiles: *© OpenStreetMap contributors*
- AI explanations: *Google Gemini*

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Tests
```bash
python scripts/check.py
```

## Deployment
Configured for Vercel serverless (`vercel.json` + `api/index.py`) with Google Cloud Firestore (`STORE_BACKEND=firestore`). Required production environment variables (set in Vercel, never committed): `APP_ENV`, `APP_SECRET`, `STORE_BACKEND`, `DEMO_MODE`, `NOMINATIM_CONTACT_EMAIL`, `ORS_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_ENABLED`, `GEMINI_DAILY_LIMIT`, `GEMINI_RPM_LIMIT`, `ASSISTANT_AI_PER_IP_PER_DAY`, `FIREBASE_PROJECT_ID`, `FIRESTORE_CREDENTIALS_B64`, `ADMIN_TOKEN`.

## Built with
Google Antigravity · Gemini 3.8 Flash · FastAPI · Leaflet · Open-Meteo · OpenStreetMap services · Firestore · Vercel
