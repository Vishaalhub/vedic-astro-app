"""
chart_builder.py
----------------
The single function your UI/API layer should call. Takes birth details in,
returns one structured dict with everything: D1 Lagna chart, all divisional
charts, planetary details (sign/nakshatra/retrograde), full Dasha lineage as
of "now" (or any date you pass), and live Gochar (transits).

This is intentionally framework-agnostic (no Flask/FastAPI here) so you (or
Claude Code) can wrap it in whatever API/UI shape you want.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from app.ephemeris import BirthInput, compute_chart, sign_of, sign_index, nakshatra_of, is_retrograde
from app.varga import compute_all_vargas, VARGA_REGISTRY
from app.dasha import get_dasha_lineage, get_mahadasha_sequence, format_period
from app.transits import get_current_transits


def build_full_chart(name: str, year: int, month: int, day: int,
                      hour: int, minute: int, second: int,
                      latitude: float, longitude: float, tz_offset_hours: float,
                      ayanamsa: str = "LAHIRI",
                      dasha_target_dt: Optional[datetime] = None) -> dict:
    """
    latitude/longitude: decimal degrees (+N, +E). You must geocode the
    'Place of Birth' string to these yourself (e.g. via a geocoding API of
    your choice) before calling this -- no geocoding is done here since it
    needs an external service/API key.
    """
    birth = BirthInput(
        name=name, year=year, month=month, day=day, hour=hour, minute=minute, second=second,
        tz_offset_hours=tz_offset_hours, latitude=latitude, longitude=longitude, ayanamsa=ayanamsa,
    )
    chart = compute_chart(birth)

    # --- D1 planetary table ---
    planets_d1 = {}
    for planet, lon in chart.planet_longitudes.items():
        nak = nakshatra_of(lon)
        planets_d1[planet] = {
            "longitude": round(lon, 4),
            "sign": sign_of(lon),
            "sign_index": sign_index(lon),
            "nakshatra": nak["name"],
            "pada": nak["pada"],
            "retrograde": is_retrograde(chart.planet_speed[planet]),
        }

    lagna_sign_idx = sign_index(chart.ascendant_deg)

    # --- All divisional charts, for every planet ---
    all_vargas = compute_all_vargas(chart.planet_longitudes)
    # Also compute Lagna's own placement in every varga (needed for whole-chart display)
    lagna_vargas = {key: compute_varga_for_lagna(chart.ascendant_deg, key) for key in VARGA_REGISTRY}

    # --- Dasha ---
    moon_longitude = chart.planet_longitudes["Moon"]
    birth_dt = datetime(year, month, day, hour, minute, second)
    mahadasha_sequence = get_mahadasha_sequence(moon_longitude, birth_dt, cycles=1)
    dasha_lineage = get_dasha_lineage(moon_longitude, birth_dt, dasha_target_dt)

    # --- Live transits (Gochar) ---
    now = dasha_target_dt or datetime.now(timezone.utc).replace(tzinfo=None)
    transits = get_current_transits(
        latitude=latitude, longitude=longitude, tz_offset_hours=0.0,
        natal_moon_sign_idx=sign_index(moon_longitude),
        natal_lagna_sign_idx=lagna_sign_idx,
        at_datetime=now, ayanamsa=ayanamsa,
    )

    return {
        "name": name,
        "birth_details": {
            "date": f"{year:04d}-{month:02d}-{day:02d}",
            "time": f"{hour:02d}:{minute:02d}:{second:02d}",
            "tz_offset_hours": tz_offset_hours,
            "latitude": latitude,
            "longitude": longitude,
            "ayanamsa": ayanamsa,
        },
        "lagna": {
            "degree": round(chart.ascendant_deg, 4),
            "sign": sign_of(chart.ascendant_deg),
            "sign_index": lagna_sign_idx,
        },
        "planets_d1": planets_d1,
        "divisional_charts": {
            key: {
                "label": VARGA_REGISTRY[key]["label"],
                "lagna_sign": lagna_vargas[key]["sign"],
                "planets": {p: v["sign"] for p, v in all_vargas[key].items()},
            }
            for key in VARGA_REGISTRY
        },
        "dasha": {
            "mahadasha_sequence": [
                {"lord": p.lord, "start": p.start.isoformat(), "end": p.end.isoformat()}
                for p in mahadasha_sequence
            ],
            "current_lineage_as_of": now.isoformat(),
            "current": {
                level: {"lord": period.lord, "start": period.start.isoformat(),
                        "end": period.end.isoformat()}
                for level, period in dasha_lineage.items()
            },
        },
        "transits_gochar": transits,
    }


def compute_varga_for_lagna(ascendant_deg: float, varga_key: str) -> dict:
    from app.varga import compute_varga
    return compute_varga(ascendant_deg, varga_key)


if __name__ == "__main__":
    # quick smoke test -- replace with a real birth detail to sanity check
    result = build_full_chart(
        name="Test Person",
        year=1995, month=8, day=15, hour=14, minute=30, second=0,
        latitude=28.6139, longitude=77.2090, tz_offset_hours=5.5,
        ayanamsa="LAHIRI",
    )
    import json
    print(json.dumps(result, indent=2, default=str)[:3000])
