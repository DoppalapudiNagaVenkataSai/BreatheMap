# Testing Strategy
All unit and integration tests run offline without network access using `respx` and in-memory test doubles.
Quality gate is enforced via `python scripts/check.py`.

## BreatheRoute (`/route`) Manual Test Cases
1. **Delhi Demo Trip (Daytime & Night)**:
   - Open `/route`, click **Try Delhi sample trip**.
   - Verify 6 mode cards render (Walk, Cycle, Car, Auto-rickshaw est., Bus est., Metro est.), sorted by least pollution breathed.
   - Change Departure Time to `22:00`, confirm **"Prefer lit streets (night trip)"** checkbox appears, re-run comparison, and verify lighting percentages appear on Walk/Cycle cards.
2. **Departure Suggestion**:
   - When a cleaner departure suggestion box appears, click **Use this time** and verify the time updates and comparison re-runs.
3. **Map & Line Distinguishability**:
   - Verify Leaflet map renders with distinct dash patterns and colors per mode, plus legend and text note.
   - Click **Show on map** on a card and confirm its route highlights.
4. **Keyboard & Zoom Accessibility**:
   - Tab through all form controls, search with `Enter`, select result with `Enter`, submit with `Enter`, and confirm focus moves to `Comparison Results`.
   - Verify 200% zoom and 360px mobile viewport have no horizontal overflow.
