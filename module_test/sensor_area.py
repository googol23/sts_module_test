"""Nominal strip-area approximation; dimensions in mm, areas in mm²."""
from math import cos, radians, isclose, isfinite

STRIP_PITCH_MM = 0.058
CHANNELS_PER_ASIC = 128
NOMINAL_SENSOR_WIDTH_MM = 62.0
STEREO_ANGLE_DEG = {"N": 0.0, "P": 7.5}


def nominal_sensor_length_mm(sensor_size):
    """Match the test's SENSOR_SIZE length to the shared nominal geometry."""
    from sts_geo_layout import SensorType

    unit = (sensor_size.unit or "").strip().lower()
    scale = {"cm": 10.0, "mm": 1.0}.get(unit)
    if scale is None:
        raise ValueError(f"Unsupported sensor size unit: {unit!r}")
    length = float(sensor_size.value) * scale
    if not isfinite(length):
        raise ValueError("Non-finite sensor length")
    for sensor_id in (1, 2, 3, 4):
        _, nominal = SensorType(sensor_id).size_xy()
        if isclose(length, nominal, rel_tol=0, abs_tol=0.01):
            return float(nominal)
    raise ValueError(f"Unsupported sensor length: {length} mm")


def strip_area_mm2(length_mm: float, side: str) -> float:
    """Full-length strip model, with pitch measured normal to the strip."""
    if not isfinite(length_mm) or length_mm <= 0:
        raise ValueError("Sensor length must be finite and positive")
    return STRIP_PITCH_MM * length_mm / cos(radians(STEREO_ANGLE_DEG[side]))


def inactive_area_percent(count: int, length_mm: float, side: str) -> float:
    """Estimated inactive strip area as a percentage of the full sensor face."""
    return 100.0 * count * strip_area_mm2(length_mm, side) / (
        NOMINAL_SENSOR_WIDTH_MM * length_mm)
