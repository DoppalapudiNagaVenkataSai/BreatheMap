# Accessibility Verification (WCAG 2.1 AA)

## Automated Checks
- `tests/accessibility/test_pages.py` verifies on all 5 pages (`/`, `/route`, `/assistant`, `/watch`, `/about`):
  - `<html lang="en">`
  - Skip-to-main link (`<a href="#main" class="skip-link">`)
  - `<main id="main">` landmark and `<nav aria-label="Main">`
  - Exactly one `<h1>` per page
  - Zero inline `<script>` or `<style>` blocks
  - Interactive regions with explicit `role` and `aria-label` (`/route` map, `/watch` map & `<dialog>`, `/assistant` `role="log"` `aria-live="polite"`)

## Keyboard & Screen Reader Design
- All chips and filters are native `<button>` or `<select>` elements with visible focus rings.
- Every map and chart has a text/table equivalent (hourly table toggle on `/`, route mode cards on `/route`, primary accessible list on `/watch`, structured reply + cards on `/assistant`).
- Live regions announce status updates without re-reading the entire chat log (new nodes appended to `#assistant-chat-log`).
