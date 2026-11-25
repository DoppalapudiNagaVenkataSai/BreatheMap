"""Official CPCB NAQI and US AQI calculations and scale conversions."""

from app.domain.models import AqiResult, Level, Scale

# Breakpoint table verified against CPCB Guidelines for National Air Quality Index (2014)
# (I_lo, I_hi, BP_lo, BP_hi)
NAQI_BREAKPOINTS: dict[str, list[tuple[int, int, float, float]]] = {
    "pm10": [
        (0, 50, 0.0, 50.0),
        (51, 100, 51.0, 100.0),
        (101, 200, 101.0, 250.0),
        (201, 300, 251.0, 350.0),
        (301, 400, 351.0, 430.0),
        (401, 500, 431.0, 500.0),
    ],
    "pm25": [
        (0, 50, 0.0, 30.0),
        (51, 100, 31.0, 60.0),
        (101, 200, 61.0, 90.0),
        (201, 300, 91.0, 120.0),
        (301, 400, 121.0, 250.0),
        (401, 500, 251.0, 380.0),
    ],
    "no2": [
        (0, 50, 0.0, 40.0),
        (51, 100, 41.0, 80.0),
        (101, 200, 81.0, 180.0),
        (201, 300, 181.0, 280.0),
        (301, 400, 281.0, 400.0),
        (401, 500, 401.0, 500.0),
    ],
    "o3": [
        (0, 50, 0.0, 50.0),
        (51, 100, 51.0, 100.0),
        (101, 200, 101.0, 168.0),
        (201, 300, 169.0, 208.0),
        (301, 400, 209.0, 748.0),
        (401, 500, 749.0, 1000.0),
    ],
    "co": [
        (0, 50, 0.0, 1.0),
        (51, 100, 1.1, 2.0),
        (101, 200, 2.1, 10.0),
        (201, 300, 10.1, 17.0),
        (301, 400, 17.1, 34.0),
        (401, 500, 34.1, 50.0),
    ],
    "so2": [
        (0, 50, 0.0, 40.0),
        (51, 100, 41.0, 80.0),
        (101, 200, 81.0, 380.0),
        (201, 300, 381.0, 800.0),
        (301, 400, 801.0, 1600.0),
        (401, 500, 1601.0, 2000.0),
    ],
}


def sub_index(pollutant: str, conc: float) -> int | None:
    """Calculate individual pollutant sub-index."""
    if conc < 0:
        return None
    key = pollutant.lower()
    if key not in NAQI_BREAKPOINTS:
        return None

    bps = NAQI_BREAKPOINTS[key]
    for i_lo, i_hi, bp_lo, bp_hi in bps:
        if conc <= bp_hi:
            val = (i_hi - i_lo) / (bp_hi - bp_lo) * (conc - bp_lo) + i_lo
            return max(0, min(500, round(val)))

    # Exceeded Severe band upper threshold
    return 500


def naqi(pollutants: dict[str, float | None]) -> AqiResult:
    """Calculate overall indicative CPCB NAQI with validation rules."""
    sub_indices: dict[str, int | None] = {}
    valid_subs: dict[str, int] = {}

    for pol, val in pollutants.items():
        if val is not None:
            si = sub_index(pol, val)
            sub_indices[pol] = si
            if si is not None:
                valid_subs[pol] = si
        else:
            sub_indices[pol] = None

    # CPCB rule: NAQI requires at least 3 pollutants, one of which must be PM2.5 or PM10
    has_pm = "pm25" in valid_subs or "pm10" in valid_subs
    if len(valid_subs) < 3 or not has_pm:
        pm25_si = valid_subs.get("pm25")
        level = level_for(Scale.NAQI, pm25_si if pm25_si is not None else 0)
        return AqiResult(
            index=pm25_si,
            level=level,
            band=band_name(Scale.NAQI, level),
            dominant="pm25" if pm25_si is not None else None,
            sub_indices=sub_indices,
            status="insufficient_data",
        )

    # Maximum sub-index determines AQI and dominant pollutant
    dominant = max(valid_subs, key=valid_subs.get)  # type: ignore[arg-type]
    aqi_val = valid_subs[dominant]
    level = level_for(Scale.NAQI, aqi_val)

    return AqiResult(
        index=aqi_val,
        level=level,
        band=band_name(Scale.NAQI, level),
        dominant=dominant,
        sub_indices=sub_indices,
        status="ok",
    )


def us_level(us_aqi: int) -> Level:
    """Map US EPA AQI index to Level L1-L6."""
    if us_aqi <= 50:
        return Level.L1
    elif us_aqi <= 100:
        return Level.L2
    elif us_aqi <= 150:
        return Level.L3
    elif us_aqi <= 200:
        return Level.L4
    elif us_aqi <= 300:
        return Level.L5
    return Level.L6


def level_for(scale: Scale, value: int) -> Level:
    """Get Level L1-L6 for a given scale and numerical value."""
    if scale == Scale.US:
        return us_level(value)

    # CPCB NAQI scale
    if value <= 50:
        return Level.L1
    elif value <= 100:
        return Level.L2
    elif value <= 200:
        return Level.L3
    elif value <= 300:
        return Level.L4
    elif value <= 400:
        return Level.L5
    return Level.L6


def band_name(scale: Scale, level: Level) -> str:
    """Return official band name for a scale and level."""
    if scale == Scale.NAQI:
        names = {
            Level.L1: "Good",
            Level.L2: "Satisfactory",
            Level.L3: "Moderate",
            Level.L4: "Poor",
            Level.L5: "Very Poor",
            Level.L6: "Severe",
        }
        return names[level]

    us_names = {
        Level.L1: "Good",
        Level.L2: "Moderate",
        Level.L3: "Unhealthy for Sensitive Groups",
        Level.L4: "Unhealthy",
        Level.L5: "Very Unhealthy",
        Level.L6: "Hazardous",
    }
    return us_names[level]
