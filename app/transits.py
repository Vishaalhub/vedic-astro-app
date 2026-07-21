"""
transits.py
-----------
Gochar (transit) analysis: where the planets are RIGHT NOW (or on any given
date), expressed as house-from-Moon and house-from-Lagna -- the two
reference points classical Jyotish uses for transit results (Chandra
Gochara and Lagna Gochara respectively).
"""

from __future__ import annotations
from datetime import datetime
from typing import Dict

from app.ephemeris import (
    BirthInput, compute_chart, sign_index, sign_of, is_retrograde, PLANETS
)


def _house_from(reference_sign_idx: int, planet_sign_idx: int) -> int:
    """1-indexed house count, Whole-Sign style, counting the reference sign as house 1."""
    return ((planet_sign_idx - reference_sign_idx) % 12) + 1


def get_current_transits(latitude: float, longitude: float, tz_offset_hours: float,
                          natal_moon_sign_idx: int, natal_lagna_sign_idx: int,
                          at_datetime: datetime = None, ayanamsa: str = "LAHIRI") -> Dict[str, dict]:
    """
    Computes where every planet is right now (default) or at at_datetime,
    and reports:
      - sign
      - house counted from natal Moon (Chandra Gochara)
      - house counted from natal Lagna (Lagna Gochara)
      - retrograde flag
    """
    at_datetime = at_datetime or datetime.utcnow()

    dummy_birth = BirthInput(
        name="__transit_probe__",
        year=at_datetime.year, month=at_datetime.month, day=at_datetime.day,
        hour=at_datetime.hour, minute=at_datetime.minute, second=at_datetime.second,
        tz_offset_hours=0.0,  # at_datetime is assumed already UTC; see note below
        latitude=latitude, longitude=longitude, ayanamsa=ayanamsa,
    )
    chart = compute_chart(dummy_birth)

    result = {}
    for planet in list(PLANETS.keys()) + ["Ketu"]:
        lon = chart.planet_longitudes[planet]
        s_idx = sign_index(lon)
        result[planet] = {
            "sign": sign_of(lon),
            "longitude": lon,
            "house_from_moon": _house_from(natal_moon_sign_idx, s_idx),
            "house_from_lagna": _house_from(natal_lagna_sign_idx, s_idx),
            "retrograde": is_retrograde(chart.planet_speed[planet]),
        }
    return result
