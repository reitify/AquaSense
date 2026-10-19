import re
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import current_app


def format_app_datetime(value, format_string):
    """Format a UTC timestamp in the configured application timezone."""
    if value is None:
        return "—"

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    local_value = value.astimezone(
        ZoneInfo(current_app.config.get("APP_TIMEZONE", "UTC"))
    )
    formatted = re.sub(
        r"(?<= )0(?=\d)",
        "",
        local_value.strftime(format_string),
    )
    return formatted
