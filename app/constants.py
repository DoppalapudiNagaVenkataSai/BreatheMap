"""Constants, factors, and tunable parameters for BreatheMap."""

APP_NAME = "BreatheMap"
APP_VERSION = "0.1.0"

# Timeouts in seconds
HTTP_CONNECT_TIMEOUT = 3.0
HTTP_READ_TIMEOUT = 8.0
OVERPASS_TIMEOUT = 10.0
GEMINI_TIMEOUT = 12.0

# Rate limits
API_RATE_LIMIT_PER_MINUTE = 60
ROUTE_COMPARE_PER_HOUR = 20

# Cache TTLs in seconds
AIR_WEATHER_CACHE_TTL = 1200  # 20 minutes
GEOCODE_CACHE_TTL = 604800  # 7 days
ROUTE_CACHE_TTL = 21600  # 6 hours
LIGHTING_CACHE_TTL = 604800  # 7 days
ASSISTANT_CACHE_TTL = 1200  # 20 minutes
HOME_TIPS_CACHE_TTL = 86400  # 24 hours

# Body limits
MAX_JSON_BODY_BYTES = 16384  # 16 KB

# --- Exposure Model Default Factors (Section 8.4) ---
# Inhalation ventilation rates in m³/h
V_MODE_WALK = 1.3
V_MODE_CYCLE = 1.9
V_MODE_CAR = 0.6
V_MODE_AUTO = 0.6
V_MODE_BUS = 0.6
V_MODE_METRO = 0.6

# Microenvironment factors (in-transit vs ambient)
F_MODE_WALK = 1.0
F_MODE_CYCLE = 1.0
F_MODE_CAR = 0.9
F_MODE_AUTO = 1.3
F_MODE_BUS = 1.1
F_MODE_METRO = 0.6

# Metro transit estimation parameters
METRO_DETOUR_FACTOR = 1.3
METRO_SPEED_KMH = 32.0
METRO_ACCESS_WALK_MIN = 10.0
METRO_ACCESS_V = 1.3
METRO_ACCESS_F = 1.0
METRO_WAIT_MIN = 5.0
METRO_WAIT_V = 0.6
METRO_WAIT_F = 0.8

# Bus transit estimation parameters
BUS_CAR_DURATION_FACTOR = 1.6
BUS_WAIT_MIN = 8.0
BUS_WAIT_V = 0.6
BUS_WAIT_F = 1.1

# Auto-rickshaw estimation parameters
AUTO_CAR_DURATION_FACTOR = 1.1

# Activity inhalation rates (m³/h)
ACTIVITY_VENTILATION: dict[str, float] = {
    "rest": 0.5,
    "yoga": 0.9,
    "walk": 1.3,
    "play": 1.5,
    "cycle": 1.9,
    "jog": 2.7,
    "run": 2.7,
}

# Road proximity factors by waytype
ROAD_FACTORS: dict[str, float] = {
    "major": 1.25,
    "state": 1.25,
    "street": 1.10,
    "path": 0.95,
    "track": 0.95,
    "cycleway": 0.95,
    "footway": 0.95,
    "steps": 0.95,
    "ferry": 1.00,
    "construction": 1.00,
    "unknown": 1.00,
}

# Illustrative emissions in kg CO2e per passenger-km
EMISSIONS_KG_PER_KM: dict[str, float] = {
    "car": 0.17,
    "auto": 0.08,
    "bus": 0.07,
    "metro": 0.03,
    "cycle": 0.0,
    "walk": 0.0,
}

# Route thresholds and optimization
DEPARTURE_OPTIMIZE_THRESHOLD_PCT = 15.0  # Min % reduction to recommend alternate time
TIE_DIFFERENCE_PCT = 10.0  # Within 10% considered about the same
MAX_ROUTE_DISTANCE_KM = 100.0
MIN_ROUTE_DISTANCE_M = 100.0
MAX_WALK_DURATION_MIN = 60.0
MAX_WALK_DISTANCE_KM = 5.0
MAX_CYCLE_DISTANCE_KM = 20.0

# --- BreatheWatch Community Reports (Section 8.13) ---
REPORT_CATEGORIES: tuple[str, ...] = (
    "smoke",
    "open_burning",
    "construction_dust",
    "road_dust",
    "vehicle_emissions",
    "industrial_emissions",
    "odour",
    "other",
)

REPORT_TTL_HOURS: dict[str, int] = {
    "smoke": 12,
    "open_burning": 12,
    "odour": 12,
    "vehicle_emissions": 6,
    "construction_dust": 24,
    "road_dust": 24,
    "industrial_emissions": 48,
    "other": 24,
}

REPORT_DESC_MIN_LEN = 10
REPORT_DESC_MAX_LEN = 280
REPORT_MAX_USER_DISTANCE_KM = 50.0
REPORT_DUPLICATE_RADIUS_M = 300.0
REPORT_DUPLICATE_WINDOW_HOURS = 2
REPORT_ROUTE_RADIUS_M = 200.0
REPORT_FLAG_HIDE_THRESHOLD = 3
REPORT_CREATE_PER_HOUR = 3
REPORT_CREATE_PER_DAY = 10
REPORT_VOTE_PER_DAY = 20
REPORT_DEFAULT_RADIUS_KM = 3.0
REPORT_MAX_RADIUS_KM = 10.0
REPORT_DEFAULT_HOURS = 24
REPORT_MAX_RESULTS = 50
REPORT_STATUS_LABEL = "Unverified community report"
