"""Unit conversions (NWS observations come in metric) and display formatting."""

from __future__ import annotations

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def c_to_f(c: float | None) -> int | None:
    return None if c is None else round(c * 9 / 5 + 32)


def kmh_to_mph(kmh: float | None) -> int | None:
    return None if kmh is None else round(kmh * 0.621371)


def pa_to_inhg(pa: float | None) -> float | None:
    return None if pa is None else pa * 0.0002953


def m_to_miles(m: float | None) -> float | None:
    return None if m is None else m / 1609.344


def cardinal(degrees: float | None) -> str | None:
    if degrees is None:
        return None
    return COMPASS[int((degrees % 360) / 22.5 + 0.5) % 16]


def fmt_visibility(miles: float | None) -> str:
    if miles is None:
        return "N/A"
    if miles >= 9.95:
        return "10+ Miles" if miles > 10.05 else "10 Miles"
    if miles < 0.25:
        return f"{round(miles * 5280, -1):.0f} ft"
    return f"{miles:.1f} Miles".replace(".0 ", " ")


def fmt_wind(direction: str | None, mph: int | None, gust: int | None = None) -> str:
    if mph is None:
        return "Not Reported"
    if mph == 0:
        return "Calm"
    text = f"{direction or 'Var'} {mph} mph"
    if gust and gust > mph:
        text += f", gusts {gust}"
    return text
