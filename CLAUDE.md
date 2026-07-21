# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Vedic astrology **calculation** engine (not an interpretation engine). It takes birth
details (date/time/location) and produces sidereal planetary positions, divisional
(varga) charts, Vimshottari Dasha periods, and live transits — all as one structured
JSON-able dict. There is no persistence layer; it's a Python engine behind a FastAPI
wrapper, with a static no-build frontend (`frontend/index.html`) that renders the
result as North Indian diamond charts.

## Commands

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
python3 -m app.chart_builder                               # smoke test (prints sample chart JSON)
uvicorn api:app --reload --port 8000                        # run the API
```

Example request:
```bash
curl -X POST http://localhost:8000/chart -H "Content-Type: application/json" -d '{
  "name": "Test",
  "year": 1995, "month": 8, "day": 15,
  "hour": 14, "minute": 30, "second": 0,
  "latitude": 28.6139, "longitude": 77.2090,
  "tz_offset_hours": 5.5,
  "ayanamsa": "LAHIRI"
}'
```

There is no test suite yet.

`render.yaml` defines two Render free-tier services (`vedic-astro-api` for `api.py`,
`vedic-astro-frontend` for `frontend/`) — see the README's **Deployment** section for
the push/connect/deploy steps. The frontend's API base URL (`frontend/index.html`,
`DEFAULT_API_BASE`) auto-detects localhost vs. deployed and falls back to a
`REPLACE-WITH-YOUR-RENDER-BACKEND-URL` placeholder that needs a one-time manual edit
once the backend's real Render URL is known; a `?api=` query param always overrides it.

## Architecture

Data flows in one direction through four independent modules, orchestrated by a single
function:

- **`app/ephemeris.py`** — the only module that talks to Swiss Ephemeris (`pyswisseph`).
  Converts local birth time -> Julian Day UT, then returns sidereal (Lahiri by default)
  planetary longitudes, Ascendant/Lagna, house cusps, nakshatra/pada. Every other module
  consumes its output (`sign_index()`, `degree_in_sign()`, `NAK_SPAN`, etc.) rather than
  calling `swisseph` directly. Rahu is computed via `swe.MEAN_NODE`; Ketu is derived as
  `Rahu + 180°`.
- **`app/varga.py`** — divisional charts D1–D60. All 16 vargas share one algorithm
  (`compute_varga`): split the 30° sign into N equal parts (except D30, which is
  classically unequal), find which part the planet's degree-in-sign falls into, then map
  that part to a resulting sign via a starting-sign rule from `VARGA_REGISTRY`. Each rule
  is its own small function (`d9_navamsa`, `d10_dashamsa`, ...) so a single varga's rule
  can be swapped (different classical texts disagree on D16/D20/D27/D40/D45/D60) without
  touching the shared algorithm.
- **`app/dasha.py`** — Vimshottari Dasha, recursive through 5 levels (Mahadasha ->
  Antardasha -> Pratyantardasha -> Sookshma -> Prana). One rule applies at every level
  (`_sub_periods`): within a parent period of lord L and duration D, sub-periods cycle
  through the fixed 9-planet order *starting from L itself*, each getting
  `(lord's full years / 120) * D`. `get_dasha_lineage()` drills down only the branch
  containing the target date, so depth doesn't blow up combinatorially.
- **`app/transits.py`** — Gochar: computes planet positions for "now" (or any date) via
  the same `ephemeris.compute_chart`, then reports each planet's house counted from natal
  Moon (Chandra Gochara) and from natal Lagna (Lagna Gochara).
- **`app/chart_builder.py`** — `build_full_chart(...)` is the single orchestrator every
  caller (API, scripts) should use. It wires the birth input through all four modules
  above and returns one dict with `lagna`, `planets_d1`, `divisional_charts`, `dasha`,
  and `transits_gochar`.
- **`api.py`** — FastAPI wrapper, CORS-enabled for any origin. `POST /chart` calls
  `build_full_chart`. Place-name resolution is split three ways, all sharing one
  Nominatim client throttled to 1 req/sec via a module-level lock (`_nominatim_search`):
  `POST /geocode` (place name + birth date -> lat/lon/tz_offset_hours, one call, for
  direct API callers), `GET /places/search` (partial place name -> up to 5 candidates,
  name-only, what the frontend's autocomplete uses), and `POST /resolve-timezone`
  (lat/lon you already have + birth date -> tz_offset_hours, no Nominatim call). All
  timezone resolution goes through `_resolve_timezone()`: `timezonefinder` for lat/lon
  -> IANA timezone, then `pytz` to resolve the UTC offset in effect *on the given birth
  date* rather than today's — offsets have shifted historically in many countries,
  including India pre-1947. Plus `GET /health`.
- **`frontend/index.html`** — single-file, no-build vanilla JS. Place of Birth is
  autocomplete-*only*: a debounced (~400ms) dropdown against `/places/search` showing
  full `display_name`s (to disambiguate same-named places in different regions), and
  picking a result is the only way to populate `selectedPlace` — the submit button
  stays disabled (`updateSubmitState()`, gated on `isLoading || !selectedPlace`) and a
  hint is shown until then; editing the text after a pick nulls `selectedPlace` again
  so a stale lat/lon can't be submitted under different text. Submit calls
  `/resolve-timezone` with the selected coordinates, then `/chart` (never `/geocode` —
  that endpoint is for direct API callers only). Renders each divisional chart (D1-D60)
  as an inline SVG North Indian diamond chart via `renderNorthIndianChart(referenceSign,
  planetSignMap, planetsMeta)`: `HOUSE_GEOMETRY` is a fixed 12-region screen layout
  (house 1 = top kite, then counter-clockwise through corner-triangle pairs to
  left/bottom/right kites at houses 4/7/10) computed once; which *sign* lands in which
  house comes from `computeHouseAssignments(referenceSign, planetSignMap)` — for a
  divisional chart, `referenceSign` is that varga's own `lagna_sign`, so screen position
  is constant but content shifts per chart/per Lagna. The small number drawn in each
  region is the **zodiac sign number** occupying that screen position (Aries=1 ...
  Pisces=12), computed separately as `((lagnaIdx + i) % 12) + 1` for position `i` —
  *not* the house-from-Lagna count (which is only used internally, via
  `computeHouseAssignments()`, to decide which region a planet's text goes in). Degrees
  are whole-number rounded via `degreeInSign()` (clamped to a max of 29). The Current
  Transits (Gochar) card
  reuses the same `renderNorthIndianChart()` twice with the *same* function signature but
  a natal reference sign instead of a varga's: "Transits from Lagna" passes the natal
  Lagna sign (`chart.lagna.sign`) and "Transits from Moon" passes the natal Moon sign
  (`chart.planets_d1.Moon.sign`) as `referenceSign`, with each transiting planet's
  current sign as `planetSignMap` — this reproduces the backend's own
  `house_from_lagna`/`house_from_moon` numbers exactly, since both use the identical
  `((signIdx - referenceIdx) % 12) + 1` formula. The underlying data table for D1
  planets and transits is kept alongside the diamond charts as a plain-text
  cross-reference. The Current Dasha Lineage card is a one-table-at-a-time
  drill-down (`#dasha-nav`, state in the `dashaState` closure var). Row highlighting at
  any depth does NOT read `chart.dasha.current` (see below); only the top-level
  Mahadasha sequence comes from the API (`dasha.mahadasha_sequence` — it has a
  "birth-balance" first period the
  pure formula can't reproduce); every deeper level (Antardasha through Prana) is
  computed client-side via `computeSubPeriods()`, which mirrors `app/dasha.py`'s
  `_sub_periods()` exactly (9 sub-periods cycling `DASHA_ORDER` from the parent's own
  lord, each getting `full_years/120` of the parent's duration) — so no extra API call
  is needed to drill down. Highlighting the currently-active row at any depth is a
  containment check (`state.now >= p.start && state.now < p.end`) against
  `dasha.current_lineage_as_of`, rather than an exact-match compare against
  `chart.dasha.current[level]` — this sidesteps float-precision drift between the
  Python and JS reimplementations of the same fractional math, and naturally shows no
  highlight if the user drills into an off-path branch. `dashaState` tracks two things
  separately: `path` (the deepest sequence of periods ever drilled into — only grows,
  via a row click) and `viewDepth` (which level's table is on screen right now — changed
  by a tab click, and can be shallower than `path.length` without discarding the deeper
  path). Navigation is a row of 5 always-visible `DASHA_LEVEL_LABELS` tabs
  (`renderDashaTabs()`: "Maha Dasha", "Antar Dasha", "Pratyantar Dasha", "Sookshma
  Dasha", "Pran Dasha") — tab `level` is enabled once `level <= path.length` (i.e. once
  the user has actually drilled that deep) and marked active when `level === viewDepth`;
  clicking an enabled tab only changes `viewDepth`, so jumping back to an
  already-visited level re-shows it exactly as left (same rows, same highlighted
  "current" row, since that highlight is purely time-based and nothing about the
  underlying `path` changed). Clicking a row while viewing depth `d` branches from there:
  `path = path.slice(0, d).concat([clickedPeriod])`, `viewDepth = d + 1` — this discards
  any stale deeper path past the branch point, which is why tabs deeper than the new
  `path.length` go back to disabled. Below the tabs, `renderDashaSummary()` prints a
  fixed 5-line "here's where you are right now" block reading directly from
  `dasha.current` (stashed on `dashaState.current` in `buildDashaState()`) — one line
  per level, unaffected by `path`/`viewDepth` navigation, since it's the one place in
  the Dasha card that intentionally *does* trust the API's `chart.dasha.current` values
  rather than the client-side time-containment recomputation used for row highlighting.
  All dates anywhere in the frontend (birth summary, Dasha summary block, Dasha
  Start/End columns) render as `DD-Mon-YYYY` via the shared `MONTH_ABBR` array
  (`formatBirthDate()` for the birth-summary `YYYY-MM-DD` string, `formatDashaDate()`
  for the UTC-anchored `Date` objects used in Dasha rows/summary).

## Known gaps (intentional, not yet wired up)

1. **Interpretation.** Deliberately out of scope for this engine — keep deterministic
   Swiss-Ephemeris math and any LLM-based interpretive layer strictly separate. If adding
   one, feed it the structured JSON from `build_full_chart()` as grounding context; never
   let a model invent planetary positions itself.
2. **Not implemented:** Ashtakavarga, Shadbala, Yogas, Panchang (tithi/vara/karana),
   Ashtottari/Yogini/Kalachakra Dasha, KP sub-lords, combustion. These would follow the
   existing pattern of reusing `ephemeris.py`'s longitudes.

## Accuracy notes

- Uses Swiss Ephemeris's built-in Moshier model (no external data files) — accurate to a
  few arc-seconds for dates roughly 1800–2400 CE. For older dates or max precision,
  download `.se1` files from `https://www.astro.com/ftp/swisseph/ephe/` and call
  `swisseph.set_ephe_path(...)` at startup.
- Dasha durations use the 365.25-day/year convention (`YEAR_DAYS` in `app/dasha.py`). Some
  software uses the exact 360-day Savana year instead — check this constant if Dasha dates
  need to match another program exactly.
- D16/D20/D27/D40/D45/D60 rules match Jagannatha Hora's defaults; other classical texts
  vary by one sign on these. Rules are isolated per-varga in `app/varga.py` specifically
  to allow swapping conventions.
