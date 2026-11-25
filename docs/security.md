# Security Documentation
This document outlines security controls implemented across the BreatheMap platform.
- Content Security Policy (CSP) & strict browser headers.
- Input validation with Pydantic (`extra="forbid"`).
- Origin checking for state-modifying requests.
- Anonymous daily HMAC hashing for rate limiting and reports.
