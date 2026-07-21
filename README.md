# Vedic Astrology Engine

A calculation engine (not an interpretation engine) for Vedic astrology:

- **Ephemeris** (`app/ephemeris.py`) — sidereal planetary positions, Ascendant/Lagna,
  nakshatra/pada, via Swiss Ephemeris (Lahiri ayanamsa by default, others available).
- **Divisional charts** (`app/varga.py`) — D1 through D60 (D1, D2, D3, D4, D7, D9, D10,
  D12, D16, D20, D24, D27, D30, D40, D45, D60), general algorithm + classical
  starting-sign rules per BPHS.
- **Dasha** (`app/dasha.py`) — Vimshottari Dasha, recursive through 5 levels:
  Mahadasha → Antardasha → Pratyantardasha → Sookshma → Prana (Ati-Sookshma).
- **Transits** (`app/transits.py`) — Gochar: live planetary positions vs. natal
  Moon and Lagna.
- **Orchestrator** (`app/chart_builder.py`) — `build_full_chart(...)` is the one
  function that returns everything as a single JSON-able dict.
- **API** (`api.py`) — FastAPI wrapper: `/chart` POST endpoint, plus `/geocode`,
  `/places/search`, and `/resolve-timezone` for callers that don't already
  have coordinates.
- **Frontend** (`frontend/index.html`) — a single-file, no-build vanilla-JS UI:
  collects Name/DOB/TOB/Place (place is an autocomplete dropdown — see below),
  calls `/chart`, and renders the result as North Indian diamond charts for
  D1–D60.

## Setup

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
python3 -m app.chart_builder                               # smoke test
uvicorn api:app --reload --port 8000                       # run the API
```

## Frontend

`frontend/index.html` is a single static file with no build step and no
dependencies. Place of Birth is an autocomplete-only field: typing (debounced
~400ms) queries `/places/search` and shows full place names in a dropdown —
e.g. distinguishing "Dehradun, Uttarakhand, India" from a same-named place
elsewhere — and picking a result is the *only* way to proceed (the Generate
Chart button stays disabled, with a hint message, until a result is
selected; editing the text afterward clears the selection and re-disables
it, so a stale lat/lon can never be submitted under new text). Submit then
calls `/resolve-timezone` with the selected coordinates, then `/chart`. Each
divisional chart (D1–D60) renders as an SVG North Indian-style diamond
chart, with house positions fixed on screen and sign placement driven by
that chart's own Lagna; the Current Transits (Gochar) section renders the
same way as two more diamond charts — "Transits from Lagna" (house 1 =
natal Lagna sign) and "Transits from Moon / Chandra Gochara" (house 1 =
natal Moon sign) — alongside the existing data table. The API has CORS
enabled (`fastapi.middleware.cors`) so it can be called from any origin,
including a `file://` page.

With the API running (`uvicorn api:app --reload --port 8000`), either:

- **Open it directly**: double-click `frontend/index.html`, or open it via
  `file:///path/to/vedic-astro-app/frontend/index.html` in a browser.
- **Serve it statically** (equivalent, and avoids some browsers' quirks with
  `file://` pages):
  ```bash
  cd frontend && python3 -m http.server 5500
  # then open http://localhost:5500
  ```

The frontend picks its API base URL in this order:

1. `?api=http://your-host:port` in the frontend's own URL, if present (e.g.
   `http://localhost:5500?api=http://localhost:9000`) — always wins.
2. Otherwise, if the page itself is being served from `localhost`/`127.0.0.1`
   (or opened as a local `file://` page), it defaults to
   `http://localhost:8000`.
3. Otherwise (i.e. the frontend is deployed somewhere), it defaults to
   `https://REPLACE-WITH-YOUR-RENDER-BACKEND-URL.onrender.com` — a placeholder
   you must edit in `frontend/index.html` once you have your actual Render
   backend URL (see **Deployment** below).

## Geocoding: Place of Birth → latitude/longitude/tz_offset_hours

`POST /geocode` resolves a plain place name to the coordinates and UTC offset
`/chart` needs — using OpenStreetMap Nominatim (no API key) for the name →
lat/lon lookup, `timezonefinder` for lat/lon → IANA timezone, and `pytz` to
resolve the UTC offset **that was actually in effect on the given birth
date** (not today's offset — this matters, since offsets have changed over
the decades in many countries, including India pre-1947).

```bash
curl -X POST http://localhost:8000/geocode -H "Content-Type: application/json" -d '{
  "place": "Delhi, India",
  "year": 1995, "month": 8, "day": 15,
  "hour": 14, "minute": 30
}'
# -> {"latitude": 28.6519, "longitude": 77.2315, "timezone": "Asia/Kolkata",
#     "tz_offset_hours": 5.5, "resolved_place_name": "Delhi, India"}
```

Feed that response straight into `/chart`'s `latitude`/`longitude`/
`tz_offset_hours` fields. `hour`/`minute`/`second` are optional (default to
noon) and only matter if a DST or offset transition falls within the birth
date itself.

Two more endpoints split geocoding into an autocomplete-friendly pair (this
is what the frontend uses), so a UI doesn't have to hit Nominatim on every
keystroke with a birth date attached:

- `GET /places/search?q=<partial place name>` — up to 5 candidate matches
  (`display_name`, `latitude`, `longitude`), name-only, no date needed. Meant
  for a type-ahead dropdown.
- `POST /resolve-timezone` — given coordinates you already have (e.g. from
  `/places/search`) plus a birth date, returns just `timezone` +
  `tz_offset_hours`. No Nominatim call, so no rate-limit wait.

All Nominatim-backed lookups (`/geocode`, `/places/search`) share the same
1-request/second throttle.

## What this does NOT do yet (intentionally left for you / Claude Code to wire up)

1. **Interpretation / natural-language readings.** The engine is pure
   calculation — it does not generate predictions or remedies. If you want an
   LLM-generated interpretation layer on top (using the persona/system-prompt
   style you already have), call the Claude API with the structured JSON from
   `build_full_chart()` as context, e.g.:

   ```python
   result = build_full_chart(...)
   # then send result (as JSON) + your astrologer system prompt to Claude,
   # asking it to interpret THIS specific structured data —
   # never let the model invent planetary positions itself.
   ```

   This separation matters: keep the deterministic Swiss-Ephemeris math in
   this engine, and only use the LLM for the *interpretive* layer on top of
   verified data. Otherwise you'll get hallucinated planetary positions.

2. **Ashtakavarga, Shadbala, Yogas, Panchang (tithi/vara/karana/yoga-of-the-day),
   Ashtottari/Yogini/Kalachakra Dasha, KP sub-lords.** Not implemented here —
   the ones you asked for (all vargas through D60, Vimshottari through Prana,
   Gochar) are done. These others follow the same general pattern (reuse
   `ephemeris.py`'s longitudes) if you want Claude Code to extend the engine.

## Deployment

`render.yaml` in the project root defines two [Render](https://render.com) free-tier
services: a Python web service for `api.py` (`vedic-astro-api`) and a static
site for `frontend/` (`vedic-astro-frontend`).

1. **Push this project to a GitHub repo.**
   ```bash
   git init                      # if not already a git repo
   git add .
   git commit -m "Initial commit"
   gh repo create vedic-astro-app --source=. --public --push
   # or manually: create an empty repo on GitHub, then
   #   git remote add origin https://github.com/<you>/vedic-astro-app.git
   #   git push -u origin main
   ```

2. **Connect the repo to Render.**
   - Go to the [Render dashboard](https://dashboard.render.com) → **New** →
     **Blueprint**.
   - Pick the GitHub repo you just pushed. Render detects `render.yaml` and
     proposes both services (`vedic-astro-api` and `vedic-astro-frontend`).
   - Click **Apply** to create and deploy both. The first deploy takes a few
     minutes (installing `pyswisseph` etc.). Free-tier web services spin down
     after inactivity, so the API's first request after idling will be slow
     (~30-60s cold start) — this is normal on Render's free plan, not a bug.
   - If you'd rather not use the Blueprint flow, create the two services by
     hand in the dashboard instead, using the same build/start commands from
     `render.yaml`.

3. **Get your backend's live URL.** Once `vedic-astro-api` finishes deploying,
   Render shows its URL, something like
   `https://vedic-astro-api-xxxx.onrender.com`. Open it in a browser and
   confirm `/health` returns `{"status": "ok"}`.

4. **Point the frontend at that URL.** Edit `frontend/index.html` and replace
   the placeholder:
   ```js
   const DEFAULT_API_BASE = isLocalHost
     ? "http://localhost:8000"
     : "https://REPLACE-WITH-YOUR-RENDER-BACKEND-URL.onrender.com";   // <- change this
   ```
   with your actual backend URL from step 3, then commit and push — Render
   auto-redeploys the static site on every push to the connected branch.
   (Alternatively, skip editing the file and just always append
   `?api=https://your-backend-url.onrender.com` to the frontend URL — the
   query param overrides the default either way, which is handy for testing
   before you commit the change.)

5. **Verify.** Open the deployed frontend URL (shown on the
   `vedic-astro-frontend` service page), fill in the form, and confirm a
   chart renders — this exercises the deployed frontend calling the deployed
   backend end-to-end, including CORS (see below) and Nominatim geocoding.

**CORS**: `api.py` already sets `allow_origins=["*"]`, so the deployed
frontend (or any origin) can call the deployed backend without further
changes — no code edits are needed for this step. That's safe here because
the API takes no credentials/cookies (`allow_credentials` is left at its
default `False`); if you later add auth, tighten this to
`allow_origins=["https://your-frontend-url.onrender.com"]` instead of `"*"`.

## Accuracy notes

- Uses Swiss Ephemeris's built-in Moshier model (no external data files needed) —
  accurate to a few arc-seconds for any date roughly 1800–2400 CE. For older
  dates or maximum precision, download the `.se1` files from
  `https://www.astro.com/ftp/swisseph/ephe/` and call
  `swisseph.set_ephe_path("/path/to/ephe")` once at startup.
- Vimshottari Dasha durations use the 365.25-day/year convention used by most
  Vedic software. A few programs use the exact 360-day Savana year instead —
  if your Dasha dates need to match a specific software exactly, check
  `YEAR_DAYS` in `app/dasha.py`.
- D16/D20/D27/D40/D45/D60 have more than one classical variant across texts
  and software; the rules used here match Jagannatha Hora's defaults and are
  isolated in `app/varga.py` specifically so you can swap a rule without
  touching the core engine.
