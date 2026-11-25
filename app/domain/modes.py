"""Travel modes estimation and comparative profile evaluations."""

from datetime import datetime

from app.constants import (
    AUTO_CAR_DURATION_FACTOR,
    BUS_CAR_DURATION_FACTOR,
    BUS_WAIT_F,
    BUS_WAIT_MIN,
    BUS_WAIT_V,
    EMISSIONS_KG_PER_KM,
    F_MODE_AUTO,
    F_MODE_BUS,
    F_MODE_METRO,
    METRO_ACCESS_F,
    METRO_ACCESS_V,
    METRO_ACCESS_WALK_MIN,
    METRO_DETOUR_FACTOR,
    METRO_SPEED_KMH,
    METRO_WAIT_F,
    METRO_WAIT_MIN,
    METRO_WAIT_V,
    V_MODE_METRO,
)
from app.domain.exposure import AirPoint, concentration_at_point
from app.domain.geo import haversine_m
from app.domain.models import Mode, ModeResult


def estimate_auto(car_result: ModeResult) -> ModeResult:
    """Estimate auto-rickshaw metrics based on car route geometry."""
    duration = car_result.duration_min * AUTO_CAR_DURATION_FACTOR
    # Dose adjusts: V_mode is same (0.6), but F_mode is 1.3 vs car 0.9, duration x 1.1
    # Dose ratio = (1.3 / 0.9) * 1.1 ≈ 1.5888
    dose_ratio = (F_MODE_AUTO / 0.9) * AUTO_CAR_DURATION_FACTOR
    dose = round(car_result.dose_ug * dose_ratio, 1)
    avg_c = round(car_result.avg_pm25 * (F_MODE_AUTO / 0.9), 1)

    return ModeResult(
        mode=Mode.AUTO,
        is_estimated=True,
        duration_min=round(duration, 1),
        distance_km=car_result.distance_km,
        dose_ug=dose,
        avg_pm25=avg_c,
        emissions_kg_co2e=emissions_kg(Mode.AUTO, car_result.distance_km),
        geometry=car_result.geometry,
    )


def estimate_bus(car_result: ModeResult, avg_ambient_pm25: float) -> ModeResult:
    """Estimate bus journey based on car geometry with wait time."""
    in_transit_min = car_result.duration_min * BUS_CAR_DURATION_FACTOR
    total_duration = in_transit_min + BUS_WAIT_MIN

    # In-transit dose
    transit_ratio = (F_MODE_BUS / 0.9) * BUS_CAR_DURATION_FACTOR
    transit_dose = car_result.dose_ug * transit_ratio

    # Wait dose
    wait_h = BUS_WAIT_MIN / 60.0
    wait_dose = avg_ambient_pm25 * BUS_WAIT_F * BUS_WAIT_V * wait_h

    total_dose = round(transit_dose + wait_dose, 1)
    avg_c = round(
        (
            car_result.avg_pm25 * (F_MODE_BUS / 0.9) * in_transit_min
            + avg_ambient_pm25 * BUS_WAIT_F * BUS_WAIT_MIN
        )
        / total_duration,
        1,
    )

    return ModeResult(
        mode=Mode.BUS,
        is_estimated=True,
        duration_min=round(total_duration, 1),
        distance_km=car_result.distance_km,
        dose_ug=total_dose,
        avg_pm25=avg_c,
        emissions_kg_co2e=emissions_kg(Mode.BUS, car_result.distance_km),
        geometry=car_result.geometry,
    )


def estimate_metro(
    origin: tuple[float, float],
    destination: tuple[float, float],
    air_points: list[AirPoint],
    departure_time: datetime,
) -> ModeResult:
    """Estimate metro travel using straight-line model, access walk, and waiting periods."""
    crow_dist_km = haversine_m(origin[0], origin[1], destination[0], destination[1]) / 1000.0
    metro_dist_km = crow_dist_km * METRO_DETOUR_FACTOR

    train_h = metro_dist_km / METRO_SPEED_KMH
    train_min = train_h * 60.0
    access_h = METRO_ACCESS_WALK_MIN / 60.0
    wait_h = METRO_WAIT_MIN / 60.0
    total_min = train_min + METRO_ACCESS_WALK_MIN + METRO_WAIT_MIN

    # Midpoint ambient PM2.5
    mid = ((origin[0] + destination[0]) / 2.0, (origin[1] + destination[1]) / 2.0)
    ambient_pm25 = concentration_at_point(mid, air_points, departure_time)

    # 1. Access walk dose (outdoor ambient)
    access_dose = ambient_pm25 * METRO_ACCESS_F * METRO_ACCESS_V * access_h
    # 2. Platform wait dose (underground/station factor 0.8)
    wait_dose = ambient_pm25 * METRO_WAIT_F * METRO_WAIT_V * wait_h
    # 3. Train transit dose (filtered AC car factor 0.6)
    train_dose = ambient_pm25 * F_MODE_METRO * V_MODE_METRO * train_h

    total_dose = round(access_dose + wait_dose + train_dose, 1)
    avg_c = round(
        (
            ambient_pm25 * METRO_ACCESS_F * METRO_ACCESS_WALK_MIN
            + ambient_pm25 * METRO_WAIT_F * METRO_WAIT_MIN
            + ambient_pm25 * F_MODE_METRO * train_min
        )
        / total_min,
        1,
    )

    return ModeResult(
        mode=Mode.METRO,
        is_estimated=True,
        duration_min=round(total_min, 1),
        distance_km=round(metro_dist_km, 1),
        dose_ug=total_dose,
        avg_pm25=avg_c,
        emissions_kg_co2e=emissions_kg(Mode.METRO, metro_dist_km),
        geometry=None,  # No invented route geometry
    )


def emissions_kg(mode: Mode, distance_km: float) -> float:
    """Calculate illustrative vehicle emissions in kg CO2e."""
    factor = EMISSIONS_KG_PER_KM.get(mode.value, 0.0)
    return round(distance_km * factor, 2)
