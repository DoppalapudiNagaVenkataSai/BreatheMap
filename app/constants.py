"""Tunable constants, thresholds, and limits for BreatheMap."""

APP_NAME = "BreatheMap"
APP_VERSION = "0.1.0"

# Timeouts in seconds
HTTP_CONNECT_TIMEOUT = 3.0
HTTP_READ_TIMEOUT = 8.0
OVERPASS_TIMEOUT = 10.0
GEMINI_TIMEOUT = 20.0

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
