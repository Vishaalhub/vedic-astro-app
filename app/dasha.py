"""
dasha.py
--------
Vimshottari Dasha calculation, recursive through 5 levels:
    Mahadasha -> Antardasha -> Pratyantardasha -> Sookshma -> Prana (Ati-Sukshma)

Core rule (identical at every level -- this is the whole system):
    Within a period of lord L, duration D, the sub-periods cycle through the
    fixed 9-planet Vimshottari order STARTING FROM L ITSELF, and each
    sub-lord X gets: (X's_full_years / 120) * D

Two public entry points you'll actually use in an app:
    get_mahadasha_sequence()  -> the full life sequence of Mahadashas (level 1)
    get_dasha_lineage()       -> "what dasha am I in right now, at all 5 levels"
                                 for any given date (this is what 99% of software
                                 displays as 'Current Dasha')
    get_full_breakdown()      -> full drill-down list at every sub-level inside
                                 one chosen parent period (e.g. all Antardashas
                                 inside a chosen Mahadasha)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.ephemeris import NAK_SPAN

# Vimshottari fixed order + full Mahadasha years (sums to 120)
DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
FULL_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}
TOTAL_YEARS = 120
YEAR_DAYS = 365.25  # standard convention used by most Vedic software (Savana/civil approximation)

LEVEL_NAMES = ["Mahadasha", "Antardasha", "Pratyantardasha", "Sookshma", "Prana"]


@dataclass
class DashaPeriod:
    lord: str
    start: datetime
    end: datetime
    level: str          # one of LEVEL_NAMES
    duration_days: float


def _next_lord(lord: str) -> str:
    i = DASHA_ORDER.index(lord)
    return DASHA_ORDER[(i + 1) % 9]


def _years_to_timedelta(years: float) -> timedelta:
    return timedelta(days=years * YEAR_DAYS)


def moon_dasha_balance(moon_longitude: float):
    """
    Given the Moon's sidereal longitude at birth, return:
      (starting_lord, balance_years_remaining_of_that_dasha)
    Based on how far the Moon has traveled through its birth nakshatra.
    """
    nak_index = int(moon_longitude // NAK_SPAN) % 27
    fraction_elapsed = (moon_longitude % NAK_SPAN) / NAK_SPAN

    starting_lord = DASHA_ORDER[nak_index % 9]
    full_years = FULL_YEARS[starting_lord]
    balance_years = full_years * (1 - fraction_elapsed)
    return starting_lord, balance_years


def get_mahadasha_sequence(moon_longitude: float, birth_dt: datetime,
                            cycles: int = 1) -> List[DashaPeriod]:
    """
    Full Mahadasha (level-1) sequence starting at birth.
    cycles=1 covers a full 120-year span (9 Mahadashas). Increase for
    multiple lifetimes' worth if you ever need it (you won't).
    """
    starting_lord, balance_years = moon_dasha_balance(moon_longitude)

    periods: List[DashaPeriod] = []
    cursor = birth_dt
    lord = starting_lord

    # first (partial) dasha
    end = cursor + _years_to_timedelta(balance_years)
    periods.append(DashaPeriod(lord, cursor, end, "Mahadasha",
                                (end - cursor).total_seconds() / 86400))
    cursor = end
    lord = _next_lord(lord)

    total_span_years = 120 * cycles
    while (cursor - birth_dt).total_seconds() / 86400 / YEAR_DAYS < total_span_years:
        dur_years = FULL_YEARS[lord]
        end = cursor + _years_to_timedelta(dur_years)
        periods.append(DashaPeriod(lord, cursor, end, "Mahadasha",
                                    (end - cursor).total_seconds() / 86400))
        cursor = end
        lord = _next_lord(lord)

    return periods


def _sub_periods(parent_lord: str, start: datetime, duration_days: float,
                  level_name: str) -> List[DashaPeriod]:
    """
    Generic recursive step used for Antardasha, Pratyantardasha, Sookshma,
    and Prana alike -- the algorithm is identical at every level.
    """
    periods: List[DashaPeriod] = []
    cursor = start
    lord = parent_lord   # sub-period sequence always starts with the parent's own lord
    for _ in range(9):
        frac = FULL_YEARS[lord] / TOTAL_YEARS
        dur_days = duration_days * frac
        end = cursor + timedelta(days=dur_days)
        periods.append(DashaPeriod(lord, cursor, end, level_name, dur_days))
        cursor = end
        lord = _next_lord(lord)
    return periods


def get_full_breakdown(parent_lord: str, start: datetime, duration_days: float,
                        level_name: str) -> List[DashaPeriod]:
    """Public wrapper: e.g. all 9 Antardashas inside one chosen Mahadasha."""
    return _sub_periods(parent_lord, start, duration_days, level_name)


def _find_current(periods: List[DashaPeriod], target: datetime) -> Optional[DashaPeriod]:
    for p in periods:
        if p.start <= target < p.end:
            return p
    # target beyond last computed period (e.g. birth_dt cycles=1 exhausted) -> return last
    return periods[-1] if periods else None


def get_dasha_lineage(moon_longitude: float, birth_dt: datetime,
                       target_dt: datetime = None) -> dict:
    """
    THE function most apps need: "what period am I in right now (or on date X),
    at all five levels?"

    Returns a dict:
      {
        "Mahadasha":        DashaPeriod,
        "Antardasha":       DashaPeriod,
        "Pratyantardasha":  DashaPeriod,
        "Sookshma":         DashaPeriod,
        "Prana":            DashaPeriod,
      }
    Only drills down through the *one* branch containing target_dt --
    computationally cheap (no combinatorial blow-up) no matter how deep you go.
    """
    target_dt = target_dt or datetime.now(timezone.utc).replace(tzinfo=None)

    maha_seq = get_mahadasha_sequence(moon_longitude, birth_dt, cycles=1)
    current_maha = _find_current(maha_seq, target_dt)
    lineage = {"Mahadasha": current_maha}

    parent = current_maha
    for level_name in LEVEL_NAMES[1:]:  # Antardasha, Pratyantardasha, Sookshma, Prana
        children = _sub_periods(parent.lord, parent.start, parent.duration_days, level_name)
        current_child = _find_current(children, target_dt)
        lineage[level_name] = current_child
        parent = current_child

    return lineage


def format_period(p: DashaPeriod) -> str:
    return (f"{p.level:16s} {p.lord:8s} "
            f"{p.start.strftime('%Y-%m-%d %H:%M')} -> {p.end.strftime('%Y-%m-%d %H:%M')} "
            f"({p.duration_days:.2f} days)")
