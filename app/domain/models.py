"""Pure domain data models and enums for BreatheMap."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Scale(StrEnum):
    NAQI = "naqi"
    US = "us"


class Level(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    L6 = "L6"


class Mode(StrEnum):
    WALK = "walk"
    CYCLE = "cycle"
    CAR = "car"
    AUTO = "auto"
    BUS = "bus"
    METRO = "metro"


class Activity(StrEnum):
    WALK = "walk"
    JOG = "jog"
    CYCLE = "cycle"
    PLAY = "play"
    YOGA = "yoga"
    REST = "rest"


class SensitiveGroup(StrEnum):
    CHILD = "child"
    ELDERLY = "elderly"
    ASTHMA = "asthma"
    PREGNANCY = "pregnancy"


class SortOption(StrEnum):
    LEAST_POLLUTION = "least_pollution"
    FASTEST = "fastest"
    BALANCED = "balanced"


class ReportCategory(StrEnum):
    SMOKE = "smoke"
    OPEN_BURNING = "open_burning"
    CONSTRUCTION_DUST = "construction_dust"
    ROAD_DUST = "road_dust"
    VEHICLE_EMISSIONS = "vehicle_emissions"
    INDUSTRIAL_EMISSIONS = "industrial_emissions"
    ODOUR = "odour"
    OTHER = "other"


class LatLon(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class PollutantSeries(BaseModel):
    times: list[datetime]
    values: list[float | None]


class AirSnapshot(BaseModel):
    pm25: float | None = None
    pm10: float | None = None
    no2: float | None = None
    so2: float | None = None
    o3: float | None = None
    co: float | None = None  # in mg/m3
    us_aqi: int | None = None


class AqiResult(BaseModel):
    index: int | None
    level: Level
    band: str
    dominant: str | None = None
    sub_indices: dict[str, int | None] = Field(default_factory=dict)
    status: str = "ok"  # "ok" or "insufficient_data"


class RouteGeometry(BaseModel):
    coordinates: list[tuple[float, float]]  # (lat, lon) pairs
    waytypes: list[str] | None = None


class LightingSummary(BaseModel):
    lit_pct: float
    unlit_pct: float
    unknown_pct: float
    coverage_pct: float
    description: str


class ModeResult(BaseModel):
    mode: Mode
    is_estimated: bool
    duration_min: float
    distance_km: float
    dose_ug: float
    avg_pm25: float
    pct_vs_best: float = 0.0
    is_best: bool = False
    is_about_same: bool = False
    flags: list[str] = Field(default_factory=list)
    lighting: LightingSummary | None = None
    emissions_kg_co2e: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    geometry: RouteGeometry | None = None
    status: str = "available"  # "available" or "unavailable"


class Window(BaseModel):
    start_time: datetime
    end_time: datetime
    avg_pm25: float
    label: str


class Advice(BaseModel):
    level: Level
    summary: str
    advice: str
    cautious_note: str | None = None
    disclaimer: str = "General guidance, not medical advice."


class HomeTip(BaseModel):
    id: str
    title: str
    text: str
    applies_min_level: Level
    mechanism: str
    cost: str
