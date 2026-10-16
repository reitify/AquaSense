def format_sensor_value(field, value):
    """Format stored sensor values for human-readable views."""
    if value is None:
        return "—"

    if field == "ph_value":
        ph_value = value / 100 if abs(value) > 14 else value
        return f"{ph_value:.2f}"
    if field in {"temperature_c", "ambient_temperature"}:
        threshold = 125 if field == "temperature_c" else 80
        temperature = value / 100 if abs(value) > threshold else value
        return f"{temperature:.2f} °C"
    if field == "change_rate":
        return f"{value / 100:.2f} °C/min"
    if field == "thermal_anomaly":
        return "Detected" if value > 0 else "None"

    units = {
        "turbidity_ntu": " NTU",
        "particle_level": "%",
        "clarity": "%",
        "tds_ppm": " ppm",
        "conductivity": " µS/cm (est.)",
        "ionic_content": " score",
        "salinity": " ppt (est.)",
        "acidity": "% score",
        "alkalinity": "% score",
        "ph_stability": "%",
    }
    return f"{value:g}{units.get(field, '')}"


def format_sensor_delta(field, value, reference_value=None):
    """Format a trend delta using the same scale as the channel's source values."""
    if value is None:
        return "—"

    scale = 1
    if field == "ph_value":
        scale = 100 if abs(reference_value if reference_value is not None else value) > 14 else 1
    elif field == "temperature_c":
        scale = 100 if abs(reference_value if reference_value is not None else value) > 125 else 1
    elif field == "ambient_temperature":
        scale = 100 if abs(reference_value if reference_value is not None else value) > 80 else 1
    elif field == "change_rate":
        scale = 100

    return f"{value / scale:+.2f}"
