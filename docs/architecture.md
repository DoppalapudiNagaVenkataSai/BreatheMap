# BreatheMap — Architecture

## Overview
BreatheMap is a responsive web application designed to help users minimize personal inhalation exposure to air pollution.

## Layers
1. **Browser**: Jinja2 HTML, vanilla JavaScript, Leaflet for maps.
2. **Vercel Python Function**: FastAPI application (`api/index.py` -> `app/main.py`).
3. **API Layer (`app/api/`)**: Thin HTTP endpoints with request validation and standard JSON responses.
4. **Service Layer (`app/services/`)**: Orchestration of external data and domain logic.
5. **Domain Layer (`app/domain/`)**: Pure deterministic logic (zero network I/O).
6. **Provider Layer (`app/providers/`)**: Typed external API adapters.
7. **Storage Layer (`app/storage/`)**: Abstract protocols with Memory and Firestore backends.
