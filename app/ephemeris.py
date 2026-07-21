"""
ephemeris.py
------------
Thin wrapper around the Swiss Ephemeris (pyswisseph) that gives back
SIDEREAL (Nirayana) planetary longitudes, the Ascendant/Lagna, and house
cusps for a given birth moment + location.

No external ephemeris data files are required: swisseph falls back to its
built-in "Moshier" analytical model, which is accurate to within a few
arc-seconds for the 1800-2400 CE range -- more than enough for horoscopy.
If you want JPL/DE-level precision, download the .se1 files from
https://www.astro.com/ftp/swisseph/ephe/ and point swe.set_ephe_path() at
that folder.
"""

from __future__ import annotations
import swisseph as swe
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict


# ---------------------------------------------------------------------------
# Ayanamsa options -- Lahiri is the Government-of-India / most-used standard.
# ---------------------------------------------------------------------------
AYANAMSA_MODES = {
    "LAHIRI": swe.SIDM_LAHIRI,
    "RAMAN": swe.SIDM_RAMAN,
    "KP": swe.SIDM_KRISHNAMURTI,
    "TRUE_CHITRA": swe.SIDM_TRUE_CITRA,
    "FAGAN_BRADLEY": swe.SIDM_FAGAN_BRADLEY,
}

# swisseph planet constants. Rahu/Ketu are lunar nodes (Ketu = Rahu + 180).
PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
    "Rahu": swe.MEAN_NODE,   # use swe.TRUE_NODE for "true node" instead
}

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

NAK_SPAN = 360.0 / 27.0          # 13deg20'
PADA_SPAN = NAK_SPAN / 4.0       # 3deg20'


@dataclass
class BirthInput:
    name: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int = 0
    tz_offset_hours: float = 5.5     # e.g. IST = +5.5. Convert local civil time to this.
    latitude: float = 28.6139        # decimal degrees, +N
    longitude: float = 77.2090       # decimal degrees, +E
    ayanamsa: str = "LAHIRI"
    house_system: str = "W"          # 'W' = Whole Sign (standard for Vedic). 'P' = Placidus, etc.


@dataclass
class ChartData:
    jd_ut: float
    ascendant_deg: float               # sidereal longitude 0-360
    planet_longitudes: Dict[str, float]  # sidereal longitude 0-360, per planet incl. Ketu
    planet_speed: Dict[str, float]        # deg/day (negative = retrograde)
    house_cusps: list = field(default_factory=list)


def to_julian_day_ut(b: BirthInput) -> float:
    """Convert local civil birth time -> Julian Day in Universal Time."""
    local_dt = datetime(b.year, b.month, b.day, b.hour, b.minute, b.second)
    ut_dt = local_dt - timedelta(hours=b.tz_offset_hours)
    hour_decimal = ut_dt.hour + ut_dt.minute / 60.0 + ut_dt.second / 3600.0
    jd_ut = swe.julday(ut_dt.year, ut_dt.month, ut_dt.day, hour_decimal)
    return jd_ut


def compute_chart(b: BirthInput) -> ChartData:
    """Main entry point: given birth details, return sidereal Lagna + all planets."""
    swe.set_sid_mode(AYANAMSA_MODES.get(b.ayanamsa.upper(), swe.SIDM_LAHIRI))

    jd_ut = to_julian_day_ut(b)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

    # --- Houses / Ascendant (sidereal) ---
    hsys = b.house_system.encode() if isinstance(b.house_system, str) else b.house_system
    cusps, ascmc = swe.houses_ex(jd_ut, b.latitude, b.longitude, hsys,
                                  flags=swe.FLG_SIDEREAL)
    ascendant_deg = ascmc[0] % 360.0

    # --- Planets ---
    longitudes: Dict[str, float] = {}
    speeds: Dict[str, float] = {}
    for name, code in PLANETS.items():
        xx, _ = swe.calc_ut(jd_ut, code, flags)
        longitudes[name] = xx[0] % 360.0
        speeds[name] = xx[3]

    # Ketu = Rahu + 180 deg, always "retrograde" by convention (nodes move backward)
    longitudes["Ketu"] = (longitudes["Rahu"] + 180.0) % 360.0
    speeds["Ketu"] = speeds["Rahu"]

    return ChartData(
        jd_ut=jd_ut,
        ascendant_deg=ascendant_deg,
        planet_longitudes=longitudes,
        planet_speed=speeds,
        house_cusps=list(cusps),
    )


def sign_of(longitude: float) -> str:
    return SIGNS[int(longitude // 30) % 12]


def sign_index(longitude: float) -> int:
    """0 = Aries ... 11 = Pisces"""
    return int(longitude // 30) % 12


def degree_in_sign(longitude: float) -> float:
    return longitude % 30.0


def nakshatra_of(longitude: float) -> dict:
    idx = int(longitude // NAK_SPAN) % 27
    pos_in_nak = longitude % NAK_SPAN
    pada = int(pos_in_nak // PADA_SPAN) + 1
    return {
        "name": NAKSHATRAS[idx],
        "index": idx,
        "pada": pada,
        "degree_in_nakshatra": pos_in_nak,
    }


def is_retrograde(speed: float) -> bool:
    return speed < 0
