# BreatheMap — Methodology

## Overview
BreatheMap calculates comparative personal air pollution exposure rather than single-point AQI or fastest transit routes.

## Mathematical Formulation

### 1. Inhaled Dose (µg)
For any journey partitioned into $n$ segments:

$$\text{Dose } (\mu\text{g}) = \sum_{i=1}^n C_i(t_i) \times F_{\text{mode}} \times F_{\text{road},i} \times V_{\text{mode}} \times \Delta t_i$$

### 2. Experienced Average PM2.5 (µg/m³)

$$\text{Average Experienced } (\mu\text{g/m}^3) = \frac{\sum_{i=1}^n C_i(t_i) \times F_{\text{mode}} \times F_{\text{road},i} \times \Delta t_i}{\sum_{i=1}^n \Delta t_i}$$

- $C_i(t_i)$: Ambient PM2.5 interpolated in space (Inverse Distance Weighting) and time.
- $F_{\text{mode}}$: Microenvironment factor (e.g. car: 0.9, auto: 1.3, metro: 0.6).
- $F_{\text{road},i}$: Proximity factor for the road type (e.g., highway: 1.25, quiet path: 0.95).
- $V_{\text{mode}}$: Ventilation/inhalation rate in m³/h (walk: 1.3, cycle: 1.9, drive: 0.6).
- $\Delta t_i$: Hours spent on segment $i$.

## Indicative CPCB NAQI
Sub-indices are computed using piecewise linear interpolation against official Central Pollution Control Board (CPCB) India breakpoints:

$$I = \frac{I_{\text{hi}} - I_{\text{lo}}}{\text{BP}_{\text{hi}} - \text{BP}_{\text{lo}}} \times (C - \text{BP}_{\text{lo}}) + I_{\text{lo}}$$
