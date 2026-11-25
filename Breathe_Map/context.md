# BreatheMap — Project Context for Google Antigravity

> **Purpose:** Persistent product context, architecture, locked decisions, and engineering constraints for the Antigravity builder.
>
> **Authoritative implementation specification:** `breathemap_plan.md`  
> This file is a concise project brief. It does not replace the detailed execution plan.

## 1. Instructions to the Builder

You are the engineering agent helping build **BreatheMap**.

Before changing code:

1. Inspect the repository and read `breathemap_plan.md` in full.
2. Read this `context.md` for product intent and non-negotiable decisions.
3. Treat `breathemap_plan.md` as the authoritative detailed specification. It contains exact formulas, API contracts, UI requirements, security rules, edge cases, tests, phased tasks, and Antigravity prompts.
4. Determine which execution phase is currently authorized. Implement **only that phase**.
5. If repository state, owner instructions, or the plan do not make the next action clear, stop and ask the owner. Do not guess or silently change architecture.

Do not build the entire product in one pass. Follow the phases in `breathemap_plan.md`.

At the end of each phase, report files created/changed, tests added, coverage, manual verification steps, known limitations, and commit hashes.

## 2. Product Identity

- **Name:** BreatheMap
- **Product:** Responsive website for desktop and mobile browsers
- **Competition context:** PromptWars Virtual — Urban Air Quality Assistant
- **Primary demonstration location:** Delhi, India
- **Geographic ambition:** Work for users in other supported locations
- **Language:** English

### One-line description

BreatheMap helps people reduce their estimated personal exposure to air pollution by helping them decide **when to go out, how to travel, and which route to take**, while explaining the reasoning in plain language.

### Problem

An AQI number alone does not tell a person what to do. Estimated personal exposure depends on:

- Where they are travelling.
- When they leave.
- How long the journey or activity lasts.
- Which travel mode they use.
- Which route they take.
- Air-quality conditions along the journey.
- Whether useful local information, such as street-lighting tags or community reports, is available.

BreatheMap turns environmental data into practical, understandable decision support.

### Audience

Urban residents and commuters, especially during poor-air-quality periods and winter smog. The product should also support decisions made for families that may include a child, an elderly person, or someone with asthma or another respiratory condition.

BreatheMap is **not** a medical tool. It must not diagnose, prescribe, or claim to guarantee safety.

### Core principle

**Optimize for the user's estimated pollution exposure, not simply the lowest AQI number, shortest distance, or fastest journey.**

The primary BreatheRoute metric is estimated PM2.5 inhaled during a trip. Emissions are secondary information only and must never determine route ranking.

## 3. Product Modules

BreatheMap has four connected user-facing areas.

### 3.1 Air view

The home page gives the user an understandable picture of local air quality.

It should provide:

- Current available air-quality information.
- AQI scale and band.
- Dominant pollutant and pollutant measurements where available.
- A 24-hour outlook.
- Cleanest and worst three-hour windows in the next 24 hours.
- Weather context.
- Source, observation time, retrieval time, and data-quality warnings.
- A way to ask the AI Air Assistant a question.
- Shortcuts to BreatheRoute and BreatheWatch.

For India, the default is an **indicative CPCB-style NAQI calculated from Open-Meteo modelled pollutant data**, not an official CPCB station reading. Outside India, default to US AQI. The user can switch scales.

Never label modelled data as an official station measurement or imply it is a live local sensor reading.

### 3.2 BreatheRoute — primary feature

BreatheRoute compares travel modes and available routes by estimated PM2.5 inhaled.

It should:

1. Accept origin, destination, departure time, flexibility window, selected modes, and ranking preference.
2. Retrieve candidate routes for walking, cycling, and car travel.
3. Estimate auto-rickshaw and bus journeys using car route geometry with clearly labelled estimated durations.
4. Estimate metro using a straight-line-based journey model, clearly labelled as an estimate and without invented route geometry.
5. Retrieve air-quality forecast values at the route's start, middle, and end.
6. Estimate exposure over the journey using the documented model.
7. Suggest a cleaner departure time when the estimated reduction meets the plan's threshold.
8. For night trips, optionally summarize OpenStreetMap street-lighting tags.
9. Show relevant BreatheWatch reports along a route without including those reports in the exposure score.
10. Explain trade-offs, assumptions, missing data, and uncertainty.

The UI compares:
- Least pollution breathed.
- Fastest.
- Balanced.

The primary metric is estimated PM2.5 inhaled in micrograms (µg). This is a comparative model estimate, **not a medical dose**.

The exact formulas, constants, route segmentation, mode factors, time-window optimization, ranking, and edge cases are specified in `breathemap_plan.md`. Do not invent replacement formulas or silently tune constants.

### 3.3 AI Air Assistant — primary feature

The AI Air Assistant is the natural-language interface to BreatheMap's actual data and deterministic calculations.

Example questions:

- “How's the air near me?”
- “When's the cleanest time to go out today?”
- “Can I jog at 6 PM for 40 minutes?”
- “I'm going to New Delhi Railway Station at 10 PM. What's the best way?”
- “How do I keep the air cleaner at home?”
- “Any smoke reported near me?”
- “What is PM2.5?”
- “What does NAQI 320 mean?”

The assistant can use BreatheMap's air, route, activity-advice, home-tip, report, and glossary services.

**Critical architecture rule: Python decides; Gemini explains.**

- Python performs calculations, exposure estimation, route ranking, rule selection, validation, and data retrieval.
- Gemini receives a compact, structured set of facts and explains those facts in plain English.
- Gemini must not calculate route scores, invent values, invent places, or make decisions unsupported by the backend.
- Response cards are generated from structured backend data, not free-form Gemini output.
- At most **one Gemini API call per user message**.
- Missing-slot clarification, greetings, help, emergency, medical, and out-of-scope responses must not call Gemini.
- If Gemini is unavailable, quota-limited, malformed, or fails validation, use a deterministic Quick answer built from the same facts.
- Cache eligible responses to conserve the free-tier quota.

The assistant is not an autonomous agent and has no permission to submit public reports or perform consequential actions. For report help, it may open a prefilled form; the user must explicitly review and submit it.

### 3.4 BreatheWatch — community reports

BreatheWatch lets anonymous users submit and discover local pollution observations.

Initial categories:

- Smoke
- Open waste burning
- Construction dust
- Road dust
- Vehicle emissions
- Industrial emissions
- Odour
- Other

Reports are text plus category and approximate location. **No photo uploads. No user accounts.**

Features:

- Submit a report through an explicit review and confirmation step.
- List and map nearby reports.
- Filter by category, time, and radius.
- “I see this too” confirmation.
- Flag a report.
- Automatic expiry.
- Admin hide endpoint.
- Show every report as an **unverified community report** unless a real verification process exists.

Reports are observations, not proof of a measured pollution exceedance. Reports along a route are displayed as context but do not affect the route exposure score.

The detailed validation, duplicate detection, rate limits, expiry periods, geohash lookup, reporter hashing, and moderation rules are in `breathemap_plan.md`.

## 4. How Context Drives Recommendations

BreatheMap must make decisions using the user's context in this order:

1. **Location:** where the user is or intends to go.
2. **Travel decisions:** departure time and trip duration first, then travel mode, then activity.
3. **Activity decisions:** time and duration first, then activity intensity.
4. **Optional cautious mode:** selected groups make recommendations one level more cautious.
5. **Data quality:** freshness, modelled versus measured status, missing data, and provider limitations affect wording and warnings.

Supported activities include walking, jogging/running, cycling, outdoor play, yoga, and general exercise.

A sensitive-group setting is optional. The user must explicitly select it. If the parser detects a possible sensitive-group hint in a message, it may offer a setting chip, but must not silently enable or persist that setting.

## 5. Locked Technical Decisions

These are deliberate product decisions. Do not replace them without asking the owner.

| Area | Decision |
|---|---|
| Product form | Responsive website for desktop and mobile browsers |
| Backend | Python 3.12 + FastAPI |
| Frontend | Server-rendered Jinja2 templates + small vanilla JavaScript modules |
| Mapping | Leaflet 1.9.x, vendored locally |
| Frontend build | No React, no npm, no bundler, no build step |
| AI | `gemini-3.8-flash` through the `google-genai` Python SDK |
| AI budget | At most one Gemini call per user message; deterministic Quick-answer fallback |
| Air quality | Open-Meteo Air Quality API |
| Weather | Open-Meteo Forecast API |
| Routing | openrouteservice primary; FOSSGIS OSRM fallback |
| Geocoding | OpenStreetMap Nominatim |
| Night lighting | OpenStreetMap `lit` tags queried through Overpass |
| Map tiles | OpenStreetMap tiles through Leaflet |
| Production storage | Firestore, Firebase Spark plan |
| Local/test storage | In-memory store |
| Hosting | Vercel Hobby, FastAPI Python Function |
| Accounts | None; anonymous usage |
| Preferences | Browser `localStorage` |
| Conversation history | Browser `sessionStorage`; only last two short turns sent with a request |
| Language | English |
| Accessibility | WCAG 2.1 AA target |
| Demo | Clearly labelled Delhi sample-data mode |

### External data and honesty

Before implementing or changing an integration, read its current official documentation and record endpoint details, parameters, units, limits, policies, and attribution in `docs/providers.md`.

Expected providers:

- Open-Meteo Air Quality API: modelled air-quality data.
- Open-Meteo Forecast API: weather and forecast context.
- openrouteservice: candidate walk, cycle, and car routes.
- FOSSGIS OSRM: routing fallback.
- Nominatim: forward and reverse geocoding.
- Overpass: OpenStreetMap street-lighting tags for night trips.
- OpenStreetMap: map tiles and geographic data.
- Gemini API: explanation only.
- Firestore: reports, votes, cache, counters, and quotas.

Provider quotas and policies can change. Verify current documentation; do not rely on remembered limits.

## 6. Architecture

Use a layered architecture with clear separation of responsibilities.

```text
Browser
  HTML + Jinja2 + vanilla JavaScript + Leaflet
  |
  | Same-origin requests to /api/v1/*
  | Browser must not call external data APIs directly.
  | Exception: OpenStreetMap map tiles.
  v
Vercel Python Function
  FastAPI application
  |
  +-- api/          Thin HTTP handlers and response envelopes
  |
  +-- services/     Orchestration and provider coordination
  |     air_service
  |     route_service
  |     report_service
  |     assistant_service
  |
  +-- domain/       Pure calculations and deterministic rules
  |     aqi, exposure, modes, windows, lighting,
  |     ranking, advice, geo, home_tips, timeutils
  |
  +-- assistant/    Intent parser, safety checks, tools,
  |                 facts, prompts, Gemini client,
  |                 output validator, fallback, quota
  |
  +-- providers/    External API adapters
  |     Open-Meteo, Nominatim, ORS, OSRM, Overpass, demo
  |
  +-- storage/      Store protocols, memory store, Firestore
  |
  +-- core/         Config, errors, logging, security,
                    HTTP client, rate limits, cache
  |
  v
External services and Firestore
```

### Architecture rules

1. **Domain logic is pure.** `app/domain/` performs no network, database, or filesystem I/O. It must be testable with hand-calculated inputs.
2. **Providers are adapters.** Provider modules convert external responses into internal Pydantic models. Raw provider JSON must not leak through the application.
3. **Services orchestrate.** Services call providers, apply caching, handle fallbacks, and invoke domain logic.
4. **Gemini explains; Python decides.** The model is not the source of truth.
5. **Every data response carries provenance.** Include source, observed time, fetched time, demo status, and warnings where relevant.
6. **Graceful degradation.** Use valid cached data with a stale warning when possible. If no valid data exists, return a clear error and offer sample data. Never silently mix live and demo data.

## 7. Repository Structure

Follow the repository layout in `breathemap_plan.md` Section 7. The intended high-level structure is:

```text
breathemap/
├── breathemap_plan.md
├── context.md
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── .python-version
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── vercel.json
├── firestore.rules
├── api/
│   └── index.py
├── app/
│   ├── main.py
│   ├── config.py
│   ├── constants.py
│   ├── dependencies.py
│   ├── core/
│   ├── domain/
│   ├── providers/
│   ├── services/
│   ├── assistant/
│   ├── storage/
│   ├── api/
│   └── templates/
├── public/
│   └── static/
│       ├── css/
│       ├── js/
│       ├── img/
│       └── vendor/leaflet/
├── data/
│   ├── demo/
│   └── knowledge/
├── scripts/
├── docs/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   ├── api/
│   ├── security/
│   └── accessibility/
└── .github/workflows/ci.yml
```

Do not invent a second frontend architecture or reorganize the planned modules without owner approval. The execution plan contains the full file-by-file structure and responsibilities.

## 8. UI and Experience Direction

The interface should feel calm, clear, and trustworthy. It is an information and decision-support tool, not a flashy chatbot demo.

### Visual language

- Off-white background.
- Dark slate text.
- Teal accent, approximately `#0F766E`, after contrast checks.
- AQI colors: green, yellow, orange, red, purple, maroon.
- Cards with approximately 12 px corner radius.
- Generous spacing.
- 16 px base font and approximately 1.5 line height.
- System font stack; no external web fonts.
- Mobile-first responsive layout.
- Breakpoints around 640 px and 1024 px.
- On desktop, route and watch pages can show a list beside the map.
- On mobile, put the list before the map.

### Navigation

Global navigation: Air · Route · Assistant · Watch · About

Pages:

- `/` — Air/home
- `/route` — BreatheRoute
- `/assistant` — AI Air Assistant
- `/watch` — BreatheWatch
- `/about` — methodology, data sources, assumptions, privacy, accessibility
- Custom 404 page

### UX rules

- Ask for geolocation only after the user clicks **Use my location**. Never trigger the browser permission prompt on page load.
- Offer place search and Delhi sample data if location access is denied.
- Always identify demo/sample data.
- Keep data lists and text alternatives available; maps are supplementary.
- Use explicit labels, keyboard-operable controls, visible focus, accessible status announcements, and accessible dialogs.
- No install prompts, service-worker install banners, or add-to-home-screen messaging.
- No inline scripts or styles. Keep JS and CSS in static files.

## 9. Data Integrity and Product Language

These rules are non-negotiable.

### Never fabricate data

Every number shown to the user must come from:

1. A real provider response.
2. A documented constant in `app/constants.py`.
3. A calculation performed from those values.

Sample data must always be labelled **Sample data**. Never mix sample and live data in one response.

### Distinguish data types

The UI and assistant must clearly distinguish:

- Measured data.
- Modelled data.
- Estimated values.
- User-submitted community reports.
- Unknown or unavailable information.

Do not imply that Open-Meteo modelled values are street-level sensor readings. Do not imply that an OSM lighting tag confirms a working streetlight. Unknown lighting coverage is not equivalent to lit or unlit.

### Required language

Never use **“safe”**, **“safest”**, or **“guaranteed”** to describe a route, place, time, or activity. Use terms such as:

- “Lower estimated exposure”
- “Estimated”
- “Modelled”
- “About”
- “Data unavailable”
- “Lighting information is incomplete”

Always include units and local timezone labels for times. Explain terms such as PM2.5 and NAQI in plain English.

## 10. Security, Privacy, and Safety

BreatheMap is anonymous and location-aware. Privacy must be designed in.

- No user accounts or login.
- Do not store raw IP addresses. Use the plan's daily HMAC reporter hash where needed for abuse controls.
- Store location only at the precision defined in the execution plan.
- Ask for geolocation only after explicit user action.
- Preferences stay in `localStorage`.
- Conversation history stays in browser `sessionStorage`; the server stores no conversations.
- Send only the last two short conversation turns to the assistant.
- Display a notice that Gemini free-tier messages are processed by Google and users should not include personal information.
- Keep API keys and credentials in environment variables.
- Never commit `.env`, service-account JSON, API keys, or other secrets.
- Use same-origin APIs; do not enable broad CORS.
- Validate request bodies with strict Pydantic schemas.
- Escape user-generated content. In JavaScript use DOM creation and `textContent`, never `innerHTML` with untrusted data.
- Apply security headers, origin checks, rate limits, and request-size limits as specified in the plan.
- Treat user reports as untrusted data, never as instructions to the AI.
- Gemini has no tools and cannot perform actions.
- The assistant never submits BreatheWatch reports.
- Medical and emergency messages receive static responses, not generated medical advice.
- Emergency response uses 112 in India and “your local emergency number” elsewhere.

Follow the detailed security and privacy requirements in `breathemap_plan.md` Section 9 and the edge-case matrix in Section 17.

## 11. Engineering Standards

These standards apply to every phase.

- Python 3.12.
- Exact dependency versions pinned in requirements files.
- Type hints throughout.
- `mypy --strict` for `app/`.
- Ruff formatting and linting.
- Public functions and classes have docstrings.
- Keep functions small and single-purpose; ideally no more than 40 lines.
- Avoid magic numbers. Put tunable constants in `app/constants.py`.
- No dead code.
- Do not add dependencies beyond those approved in Section 5 of the plan without asking the owner.
- Keep provider adapters isolated.
- Keep tests deterministic and offline.
- Use `respx` to mock HTTP.
- Use a fake Gemini client.
- Use the in-memory store for tests.
- No test may access the network.

Before every commit, run:

```bash
python scripts/check.py
```

The check script must run the quality gates defined in the plan: Ruff format check, Ruff lint, mypy, pytest with coverage, and repository-size validation. Do not weaken or disable a check merely to make it pass.

## 12. Git and Repository Rules

- Use the single branch `main` only.
- Do not create, push, or merge other branches.
- Commit after each logical task group using Conventional Commits, for example:
  - `feat: add air quality provider`
  - `fix: handle stale air data`
  - `test: cover route exposure calculation`
  - `docs: document provider limits`
- Push at the end of each phase.
- Never commit secrets.
- Keep the complete repository, including Git history, under 10 MB.
- Do not commit binaries, virtual environments, `node_modules`, `__pycache__`, screenshots, videos, or large fixtures.
- Each fixture file must be no larger than 150 KB. Use small fixtures; the detailed plan gives a stricter target for test fixtures.
- Use small SVG assets only.

## 13. Implementation Sequence

Follow the phases in `breathemap_plan.md` Section 18. Do not skip ahead.

Broad sequence:

1. **Owner setup:** accounts, API keys, GitHub repository, local environment.
2. **Foundation:** FastAPI application, configuration, core infrastructure, quality checks, and deployment skeleton.
3. **Domain logic:** pure calculations and tests for AQI, exposure, modes, time windows, ranking, advice, and geography.
4. **External providers:** Open-Meteo, routing, geocoding, Overpass, and demo adapters, with provider documentation.
5. **Air view:** air-quality API, weather context, AQI presentation, and cleanest/worst windows.
6. **BreatheRoute:** mode comparison, exposure calculation, departure-time optimization, lighting summary, and route UI.
7. **BreatheWatch:** storage, report rules, endpoints, and watch page.
8. **AI Assistant engine:** intent parsing, slots, tools, facts, Gemini explanation, validation, fallback, cache, and quota.
9. **AI Assistant interface:** chat UI and integrations with Air, Route, and Watch.
10. **Finalization:** About/methodology, README, tests, security/accessibility review, and Vercel deployment.

This list is a summary only. The phase prompts, exact dependencies, acceptance criteria, tests, manual verification, commits, and recovery notes in `breathemap_plan.md` are authoritative.

## 14. Definition of Done

A feature is not complete merely because its happy path works.

Before considering a phase complete:

- All tasks and acceptance criteria for that phase are implemented.
- Tests cover normal behavior, failure cases, and relevant edge cases.
- Tests run offline.
- `python scripts/check.py` passes.
- No secrets or generated/binary clutter have been committed.
- UI work meets accessibility and security requirements.
- Provider data has correct units, attribution, and provenance.
- Missing or stale data is represented honestly.
- Demo data is clearly labelled and never silently mixed with live data.
- Manual verification steps have been completed by the owner.
- Changes are committed and pushed to `main`.
- The end-of-phase summary is provided.

## 15. What Not to Build

Do not add these features unless the owner explicitly changes the scope:

- Native mobile app.
- PWA installation or offline mode.
- React, npm, or a frontend build pipeline.
- User accounts, login, email, or push notifications.
- Photo uploads or image moderation for BreatheWatch.
- Medical diagnosis, medication advice, or health profiles.
- Real public-transport routing.
- Model training, vector databases, RAG pipelines, or Gemini Search/Maps grounding.
- Autonomous AI agents or model-controlled tools.
- Any claim that a route or activity is safe.
- Any feature that requires invented measurements or unsupported assumptions.

## 16. Final Builder Reminder

BreatheMap is not “an AQI dashboard with a chatbot.” It is a personal air-exposure decision-support website.

Its core value comes from combining:

- **Air:** what the available environmental data says.
- **BreatheRoute:** how time, travel mode, route, and duration change estimated PM2.5 inhaled.
- **BreatheWatch:** what people nearby are observing.
- **AI Air Assistant:** a natural-language interface that explains actual computed results.

Keep the system honest, explainable, privacy-conscious, accessible, and small enough to finish. Follow `breathemap_plan.md` phase by phase. If a requirement is unclear, ask instead of improvising.
