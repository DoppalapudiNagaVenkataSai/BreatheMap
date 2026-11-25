# BreatheMap — Assumptions & Parameters

All numeric parameters used in the exposure and routing models are documented defaults.

## Inhalation Rates ($V_{\text{mode}}$ in m³/h)
- Rest: 0.5
- Yoga: 0.9
- Walk: 1.3
- Outdoor play: 1.5
- Cycle: 1.9
- Jog / Run: 2.7
- Motor transit (car/auto/bus/metro passenger): 0.6

## Microenvironment Factors ($F_{\text{mode}}$)
- Walk / Cycle: 1.0 (unfiltered ambient air)
- Car: 0.9 (partial window/filter attenuation)
- Auto-rickshaw: 1.3 (open cabin in dense vehicular exhaust)
- Bus: 1.1 (open windows / frequent door opening)
- Metro: 0.6 (air conditioned and filtered train cabin)

## Transit Estimates
- **Auto-rickshaw**: Car geometry; duration = car duration $\times 1.1$.
- **Bus**: Car geometry; duration = car duration $\times 1.6 + 8\text{ min wait time}$.
- **Metro**: Straight-line distance $\times 1.3\text{ detour}$ at $32\text{ km/h} + 10\text{ min access walk} + 5\text{ min platform wait}$.
