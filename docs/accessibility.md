# Accessibility Verification (WCAG 2.1 AA)

## Static Checks (Automated in `tests/accessibility/test_pages.py`)
- [x] Language attribute declared (`<html lang="en">`).
- [x] Skip link (`<a href="#main" class="skip-link">Skip to main content</a>`) as first focusable element.
- [x] Landmark elements present (`header`, `nav aria-label="Main"`, `main id="main"`, `footer`).
- [x] Exactly one `<h1>` per page.
- [x] Text alternative for 24-hour chart (interactive toggle switching between SVG chart and structured `<table>`).
- [x] Accessible dialog for location selection with `aria-labelledby="dialog-title"`.
- [x] Color contrast ratios verified for all 6 AQI levels (>= 4.5:1 text against backgrounds).
- [x] No inline styles or script tags (strict CSP compliant).
