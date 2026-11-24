"""Today's forecast from Open-Meteo (free, no key)."""

from __future__ import annotations

import requests

from .. import USER_AGENT
from ..text import esc
from . import Context, widget

# WMO weather interpretation codes, condensed.
WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Showers", 81: "Showers",
    82: "Heavy showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorms",
    96: "Thunderstorms, hail", 99: "Thunderstorms, hail",
}


@widget("weather", "Weather")
def weather(opts: dict, ctx: Context) -> str | None:
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": opts["latitude"],
            "longitude": opts["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,precipitation_sum,uv_index_max,wind_speed_10m_max",
            "hourly": "temperature_2m,precipitation_probability",
            "timezone": str(ctx.tz),
            "forecast_days": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=ctx.timeout,
    )
    r.raise_for_status()
    data = r.json()
    d = {k: v[0] for k, v in data["daily"].items()}
    place = esc(opts.get("place", ""))
    summary = WMO.get(d["weather_code"], "")
    lines = [
        f"<p><strong>{place + ': ' if place else ''}{summary}</strong>, "
        f"{d['temperature_2m_min']:.0f}–{d['temperature_2m_max']:.0f}°C. "
        f"Rain {d['precipitation_probability_max']:.0f}%"
        + (f" ({d['precipitation_sum']:.1f} mm)" if d["precipitation_sum"] else "")
        + f", UV {d['uv_index_max']:.0f}, wind up to {d['wind_speed_10m_max']:.0f} km/h.</p>"
    ]
    # A few points through the day, for "do I need a jacket this evening".
    hourly = data["hourly"]
    marks = []
    for hour in (7, 9, 12, 15, 18, 21):
        if hour < len(hourly["time"]):
            marks.append(
                f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'} "
                f"{hourly['temperature_2m'][hour]:.0f}°"
                + (f" ({hourly['precipitation_probability'][hour]}%)" if hourly["precipitation_probability"][hour] >= 30 else "")
            )
    if marks:
        lines.append(f"<p>{' · '.join(marks)}</p>")
    return "".join(lines)
