# BreatheMap Assumptions

1. Air-quality data is **modelled** (Open-Meteo / CAMS), not station measurements. Its grid is coarse outside Europe, so within-city route differences come mainly from mode, duration, timing, and road type.
2. NAQI is **indicative**: calculated with CPCB-style breakpoints from modelled concentrations, not an official CPCB value.
3. Exposure factors (inhalation rates, microenvironment and road factors, transit speeds and overheads) are **illustrative defaults**, documented in `app/constants.py` and tunable.
4. Metro, bus, and auto results are **estimates**; no free source provides reliable transit routing.
5. Street-lighting information comes from **volunteer OpenStreetMap tags** and is often incomplete; missing tags are shown as "unknown".
6. Community reports are **unverified** observations.
7. Emissions factors are **illustrative** and only a secondary note.
8. The AI runs on the **Gemini free tier** with a small daily quota; Quick answers keep the site useful when the quota is used up. Free-tier inputs may be used by Google to improve its products, so users are told not to share personal details.
9. The site is **anonymous**; preferences stay in the browser; reports expire; raw IPs are never stored.
10. Recommendations are **general guidance, not medical advice**.
