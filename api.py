"""
api.py
------
Minimal REST API around the astrology engine.

Run:
    uvicorn api:app --reload --port 8000

Then POST to /chart, e.g.:
    curl -X POST http://localhost:8000/chart -H "Content-Type: application/json" -d '{
      "name": "Test",
      "year": 1995, "month": 8, "day": 15,
      "hour": 14, "minute": 30, "second": 0,
      "latitude": 28.6139, "longitude": 77.2090,
      "tz_offset_hours": 5.5,
      "ayanamsa": "LAHIRI"
    }'

If you only have a place name (not lat/lon/tz_offset), call /geocode first --
see its docstring below -- and feed its response straight into the /chart
request above.
"""

import threading
import time
from datetime import datetime
from typing import Optional, Tuple

import pytz
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from timezonefinder import TimezoneFinder

from app.chart_builder import build_full_chart

app = FastAPI(title="Vedic Astrology Engine")

# Allow the static frontend to call this API directly from the browser --
# from a file:// page, localhost during dev, or a deployed origin (e.g. the
# Render static site URL) once this API is hosted. "*" works everywhere
# because no cookies/auth headers are involved (allow_credentials is left at
# its default False, which is what makes a wildcard origin valid at all --
# browsers reject "*" together with credentialed requests). If you want to
# lock this down once you know your deployed frontend's exact URL, replace
# allow_origins=["*"] with allow_origins=["https://your-frontend.onrender.com"].
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Geocoding: place name -> (latitude, longitude, tz_offset_hours as of a
# specific historic date).
# ---------------------------------------------------------------------------
_timezone_finder = TimezoneFinder()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "vedic-astro-app (contact: set-a-real-contact-here)"
NOMINATIM_MIN_INTERVAL_SECONDS = 1.0  # Nominatim usage policy: max 1 req/sec

_nominatim_lock = threading.Lock()
_last_nominatim_call = 0.0


class GeocodeRequest(BaseModel):
    place: str  # e.g. "Delhi, India"
    year: int
    month: int
    day: int
    # Birth time, if known -- only matters for the (rare) case where a UTC
    # offset or DST transition falls within the birth date itself. Defaults
    # to noon, which is a safe representative offset for the date otherwise.
    hour: int = 12
    minute: int = 0
    second: int = 0


class ResolveTimezoneRequest(BaseModel):
    latitude: float
    longitude: float
    year: int
    month: int
    day: int
    hour: int = 12
    minute: int = 0
    second: int = 0


def _nominatim_search(query: str, limit: int) -> list:
    """Query Nominatim for up to `limit` matches, throttled to 1 request/second."""
    global _last_nominatim_call
    with _nominatim_lock:
        elapsed = time.monotonic() - _last_nominatim_call
        if elapsed < NOMINATIM_MIN_INTERVAL_SECONDS:
            time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS - elapsed)
        response = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": limit},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        _last_nominatim_call = time.monotonic()

    response.raise_for_status()
    return response.json()


def _resolve_timezone(latitude: float, longitude: float, year: int, month: int, day: int,
                       hour: int, minute: int, second: int) -> Tuple[str, float]:
    """
    Resolve (timezone name, UTC offset in hours) for a coordinate, where the
    offset is the one actually in effect on the given date -- not today's
    offset. This matters: many countries' offsets have changed over the
    decades (e.g. India used UTC+5:53:20 before 1906, and other offsets
    before settling on UTC+5:30 in 1947).
    """
    tz_name = _timezone_finder.timezone_at(lat=latitude, lng=longitude)
    if tz_name is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not resolve a timezone for ({latitude}, {longitude})",
        )
    naive_dt = datetime(year, month, day, hour, minute, second)
    localized_dt = pytz.timezone(tz_name).localize(naive_dt)
    offset_hours = localized_dt.utcoffset().total_seconds() / 3600.0
    return tz_name, offset_hours


@app.get("/places/search")
def search_places(q: str = Query(..., min_length=1)):
    """
    Autocomplete-style place lookup: up to 5 candidate matches for a partial
    place name, name-only (no birth date/timezone resolution here -- pair
    a chosen result with POST /resolve-timezone once you also have a date).
    """
    results = _nominatim_search(q, limit=5)
    return [
        {
            "display_name": r.get("display_name", q),
            "latitude": float(r["lat"]),
            "longitude": float(r["lon"]),
        }
        for r in results
    ]


@app.post("/resolve-timezone")
def resolve_timezone(req: ResolveTimezoneRequest):
    """
    Given coordinates you already have (e.g. from /places/search) plus a
    birth date, return just the timezone + historically-correct UTC offset.
    No Nominatim call needed since no place-name lookup is involved.
    """
    tz_name, tz_offset_hours = _resolve_timezone(
        req.latitude, req.longitude, req.year, req.month, req.day,
        req.hour, req.minute, req.second,
    )
    return {"timezone": tz_name, "tz_offset_hours": round(tz_offset_hours, 6)}


@app.post("/geocode")
def geocode(req: GeocodeRequest):
    """
    Resolve a place name to (latitude, longitude, tz_offset_hours). Feed the
    response straight into POST /chart's latitude/longitude/tz_offset_hours
    fields. See _resolve_timezone() for why tz_offset_hours is date-specific.
    """
    results = _nominatim_search(req.place, limit=1)
    if not results:
        raise HTTPException(status_code=404, detail=f"Place not found: {req.place!r}")
    place_result = results[0]
    latitude = float(place_result["lat"])
    longitude = float(place_result["lon"])

    tz_name, tz_offset_hours = _resolve_timezone(
        latitude, longitude, req.year, req.month, req.day,
        req.hour, req.minute, req.second,
    )

    return {
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "timezone": tz_name,
        "tz_offset_hours": round(tz_offset_hours, 6),
        "resolved_place_name": place_result.get("display_name", req.place),
    }


class BirthRequest(BaseModel):
    name: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int = 0
    latitude: float
    longitude: float
    tz_offset_hours: float
    ayanamsa: str = "LAHIRI"
    dasha_target_dt: Optional[datetime] = None  # omit = "as of right now"


@app.post("/chart")
def chart(req: BirthRequest):
    return build_full_chart(
        name=req.name, year=req.year, month=req.month, day=req.day,
        hour=req.hour, minute=req.minute, second=req.second,
        latitude=req.latitude, longitude=req.longitude,
        tz_offset_hours=req.tz_offset_hours, ayanamsa=req.ayanamsa,
        dasha_target_dt=req.dasha_target_dt,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
