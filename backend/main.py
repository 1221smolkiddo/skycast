"""
SkyCast Backend — FastAPI + SQLite + OpenWeatherMap + AI Analysis
"""

import os
import time
import sqlite3
import httpx
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env.example"))
load_dotenv()


def env_str(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip().strip("\"'")


def env_int(name: str, default: int) -> int:
    value = env_str(name, str(default))
    try:
        return int(value)
    except ValueError:
        return default


OWM_API_KEY    = env_str("OWM_API_KEY", "YOUR_OPENWEATHERMAP_API_KEY")
ANTHROPIC_KEY  = env_str("ANTHROPIC_API_KEY", "")
DB_PATH        = env_str("DB_PATH", "skycast.db")
CACHE_TTL      = env_int("CACHE_TTL", 600)
INVALID_OWM_KEYS = {
    "",
    "YOUR_OPENWEATHERMAP_API_KEY",
    "your_openweathermap_api_key_here",
}

OWM_CURRENT    = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST   = "https://api.openweathermap.org/data/2.5/forecast"
OWM_AIR        = "https://api.openweathermap.org/data/2.5/air_pollution"
ANTHROPIC_URL  = "https://api.anthropic.com/v1/messages"

# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS searches (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            city      TEXT NOT NULL,
            country   TEXT,
            searched_at TEXT DEFAULT (datetime('now')),
            lat       REAL,
            lon       REAL
        );

        CREATE TABLE IF NOT EXISTS weather_cache (
            cache_key   TEXT PRIMARY KEY,
            data        TEXT NOT NULL,
            cached_at   REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS favorites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            city        TEXT NOT NULL UNIQUE,
            country     TEXT,
            lat         REAL,
            lon         REAL,
            added_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_searches_city ON searches(city);
        CREATE INDEX IF NOT EXISTS idx_searches_at   ON searches(searched_at);
    """)
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
#  CACHE HELPERS
# ─────────────────────────────────────────────
def cache_get(key: str):
    conn = get_db()
    row = conn.execute(
        "SELECT data, cached_at FROM weather_cache WHERE cache_key=?", (key,)
    ).fetchone()
    conn.close()
    if row and (time.time() - row["cached_at"]) < CACHE_TTL:
        return json.loads(row["data"])
    return None

def cache_set(key: str, data: dict):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO weather_cache(cache_key, data, cached_at) VALUES(?,?,?)",
        (key, json.dumps(data), time.time())
    )
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
#  OWM HELPERS
# ─────────────────────────────────────────────
def owm_icon_to_condition(icon: str, description: str) -> str:
    """Map OWM icon code to a friendly condition string."""
    mapping = {
        "01d": "Clear Sky", "01n": "Clear Night",
        "02d": "Few Clouds", "02n": "Few Clouds",
        "03d": "Scattered Clouds", "03n": "Scattered Clouds",
        "04d": "Overcast Clouds", "04n": "Overcast Clouds",
        "09d": "Shower Rain", "09n": "Shower Rain",
        "10d": "Rain", "10n": "Rain",
        "11d": "Thunderstorm", "11n": "Thunderstorm",
        "13d": "Snow", "13n": "Snow",
        "50d": "Mist", "50n": "Mist",
    }
    return mapping.get(icon, description.title())

def uv_label(uv: float) -> str:
    if uv < 3: return f"{uv:.1f} (Low)"
    if uv < 6: return f"{uv:.1f} (Moderate)"
    if uv < 8: return f"{uv:.1f} (High)"
    if uv < 11: return f"{uv:.1f} (Very High)"
    return f"{uv:.1f} (Extreme)"

def wind_direction(deg: float) -> str:
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[round(deg / 22.5) % 16]

def unix_to_time(ts: int, offset: int) -> str:
    """Convert unix timestamp + tz offset (seconds) to local HH:MM AM/PM."""
    local_ts = ts + offset
    dt = datetime.utcfromtimestamp(local_ts)
    return dt.strftime("%I:%M %p")

def get_forecast_days(forecast_list: list, tz_offset: int) -> list:
    """Extract one entry per day (12:00 local time preferred) for next 5 days."""
    days = {}
    for item in forecast_list:
        local_ts = item["dt"] + tz_offset
        dt = datetime.utcfromtimestamp(local_ts)
        day_key = dt.strftime("%Y-%m-%d")
        hour = dt.hour
        # Prefer midday reading
        if day_key not in days or abs(hour - 13) < abs(days[day_key]["_hour"] - 13):
            days[day_key] = {
                "_hour": hour,
                "day": dt.strftime("%a"),
                "condition": owm_icon_to_condition(
                    item["weather"][0]["icon"],
                    item["weather"][0]["description"]
                ),
                "high": round(item["main"]["temp_max"] - 273.15, 1),
                "low":  round(item["main"]["temp_min"] - 273.15, 1),
            }
    result = []
    for v in list(days.values())[:5]:
        v.pop("_hour", None)
        result.append(v)
    return result

# ─────────────────────────────────────────────
#  AI INSIGHT (Anthropic, optional)
# ─────────────────────────────────────────────
async def get_ai_insight(city: str, condition: str, temp_c: float,
                          humidity: int, wind: float, aqi: Optional[int]) -> str:
    if not ANTHROPIC_KEY:
        aqi_str = f", AQI {aqi}" if aqi else ""
        return (
            f"Currently {condition.lower()} in {city} with {temp_c:.0f}°C, "
            f"{humidity}% humidity and {wind:.0f} km/h winds{aqi_str}. "
            f"{'Carry an umbrella.' if 'rain' in condition.lower() or 'shower' in condition.lower() else 'Great conditions for outdoor activities.' if temp_c > 15 else 'Layer up before heading out.'}"
        )

    prompt = (
        f"Weather in {city}: {condition}, {temp_c:.1f}°C, humidity {humidity}%, "
        f"wind {wind:.0f} km/h{f', AQI {aqi}' if aqi else ''}. "
        f"Write 2 engaging, practical sentences for someone visiting today. "
        f"Be specific, atmospheric, and include a useful tip. No fluff."
    )
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 150,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            data = r.json()
            return data["content"][0]["text"].strip()
    except Exception:
        return f"{condition} in {city} — {temp_c:.0f}°C with {humidity}% humidity."

# ─────────────────────────────────────────────
#  APP LIFECYCLE
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="SkyCast API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.get("/api/weather")
async def get_weather(city: str = Query(..., min_length=1, description="City name")):
    """Main weather endpoint — current + forecast + air quality + AI insight."""
    city_clean = city.strip()
    cache_key = f"weather:{city_clean.lower()}"

    # Serve from cache if fresh
    cached = cache_get(cache_key)
    if cached:
        cached["fromCache"] = True
        return cached

    if OWM_API_KEY in INVALID_OWM_KEYS:
        raise HTTPException(
            status_code=503,
            detail="OpenWeatherMap API key not configured. Set OWM_API_KEY in backend/.env (or backend/.env.example)."
        )

    async with httpx.AsyncClient(timeout=10) as client:
        # 1. Current weather
        r_curr = await client.get(OWM_CURRENT, params={
            "q": city_clean, "appid": OWM_API_KEY, "units": "metric"
        })
        if r_curr.status_code == 404:
            raise HTTPException(status_code=404, detail=f"City '{city_clean}' not found.")
        if r_curr.status_code == 401:
            owm_message = "Invalid OpenWeatherMap API key."
            try:
                owm_message = r_curr.json().get("message", owm_message)
            except Exception:
                pass
            raise HTTPException(
                status_code=401,
                detail=f"OpenWeatherMap authentication failed: {owm_message}"
            )
        r_curr.raise_for_status()
        curr = r_curr.json()

        lat = curr["coord"]["lat"]
        lon = curr["coord"]["lon"]
        tz_offset = curr.get("timezone", 0)  # seconds from UTC

        # 2. Forecast
        r_fore = await client.get(OWM_FORECAST, params={
            "lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"
        })
        r_fore.raise_for_status()
        fore = r_fore.json()

        # 3. Air quality
        aqi_value = None
        aqi_label = "N/A"
        try:
            r_air = await client.get(OWM_AIR, params={
                "lat": lat, "lon": lon, "appid": OWM_API_KEY
            })
            if r_air.status_code == 200:
                air_data = r_air.json()
                aqi_value = air_data["list"][0]["main"]["aqi"]
                aqi_labels = {1:"Good", 2:"Fair", 3:"Moderate", 4:"Poor", 5:"Very Poor"}
                aqi_label = aqi_labels.get(aqi_value, "Unknown")
        except Exception:
            pass

    # Build condition string
    icon      = curr["weather"][0]["icon"]
    desc      = curr["weather"][0]["description"]
    condition = owm_icon_to_condition(icon, desc)

    temp_c    = round(curr["main"]["temp"], 1)
    feels_c   = round(curr["main"]["feels_like"], 1)
    temp_min  = round(curr["main"]["temp_min"], 1)
    temp_max  = round(curr["main"]["temp_max"], 1)
    humidity  = curr["main"]["humidity"]
    pressure  = curr["main"]["pressure"]
    wind_spd  = round(curr.get("wind", {}).get("speed", 0) * 3.6, 1)  # m/s → km/h
    wind_deg  = curr.get("wind", {}).get("deg", 0)
    vis_km    = round(curr.get("visibility", 10000) / 1000, 1)
    clouds    = curr.get("clouds", {}).get("all", 0)
    sunrise   = unix_to_time(curr["sys"]["sunrise"], tz_offset)
    sunset    = unix_to_time(curr["sys"]["sunset"],  tz_offset)
    local_now = unix_to_time(int(time.time()), tz_offset)

    # UTC offset string
    offset_h  = tz_offset // 3600
    offset_m  = abs(tz_offset % 3600) // 60
    tz_str    = f"UTC{'+' if offset_h >= 0 else ''}{offset_h:02d}:{offset_m:02d}"

    # Forecast days
    forecast_days = get_forecast_days(fore["list"], tz_offset)

    # Rain / Snow in last hour
    rain_1h = curr.get("rain", {}).get("1h", 0)
    snow_1h = curr.get("snow", {}).get("1h", 0)

    # AI insight
    ai_insight = await get_ai_insight(
        city_clean, condition, temp_c, humidity, wind_spd, aqi_value
    )

    response = {
        "city":        curr["name"],
        "country":     curr["sys"]["country"],
        "lat":         lat,
        "lon":         lon,
        "timezone":    tz_str,
        "localTime":   local_now,
        "condition":   condition,
        "description": desc.title(),
        "icon":        f"https://openweathermap.org/img/wn/{icon}@2x.png",
        "temperature": temp_c,
        "feelsLike":   feels_c,
        "tempMin":     temp_min,
        "tempMax":     temp_max,
        "humidity":    humidity,
        "pressure":    pressure,
        "windSpeed":   wind_spd,
        "windDir":     wind_direction(wind_deg),
        "windDeg":     wind_deg,
        "visibility":  vis_km,
        "cloudCover":  clouds,
        "rain1h":      rain_1h,
        "snow1h":      snow_1h,
        "sunrise":     sunrise,
        "sunset":      sunset,
        "aqi":         aqi_value,
        "aqiLabel":    aqi_label,
        "forecast":    forecast_days,
        "aiInsight":   ai_insight,
        "fromCache":   False,
        "fetchedAt":   datetime.now(timezone.utc).isoformat(),
    }

    # Save to cache & record search
    cache_set(cache_key, response)
    conn = get_db()
    conn.execute(
        "INSERT INTO searches(city, country, lat, lon) VALUES(?,?,?,?)",
        (curr["name"], curr["sys"]["country"], lat, lon)
    )
    conn.commit()
    conn.close()

    return response


@app.get("/api/history")
def get_history(limit: int = Query(10, le=50)):
    """Return recent unique city searches."""
    conn = get_db()
    rows = conn.execute("""
        SELECT city, country, MAX(searched_at) as last_searched, COUNT(*) as search_count
        FROM searches
        GROUP BY city
        ORDER BY last_searched DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/favorites")
def get_favorites():
    conn = get_db()
    rows = conn.execute("SELECT * FROM favorites ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/favorites")
def add_favorite(city: str = Query(...), country: str = Query(""), lat: float = Query(0), lon: float = Query(0)):
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO favorites(city, country, lat, lon) VALUES(?,?,?,?)",
            (city, country, lat, lon)
        )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
    return {"status": "added", "city": city}


@app.delete("/api/favorites/{city}")
def remove_favorite(city: str):
    conn = get_db()
    conn.execute("DELETE FROM favorites WHERE city=?", (city,))
    conn.commit()
    conn.close()
    return {"status": "removed", "city": city}


@app.get("/api/stats")
def get_stats():
    """App stats — total searches, unique cities, cache entries."""
    conn = get_db()
    total    = conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    unique   = conn.execute("SELECT COUNT(DISTINCT city) FROM searches").fetchone()[0]
    cached   = conn.execute("SELECT COUNT(*) FROM weather_cache").fetchone()[0]
    favs     = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
    top_city = conn.execute(
        "SELECT city, COUNT(*) c FROM searches GROUP BY city ORDER BY c DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "totalSearches": total,
        "uniqueCities":  unique,
        "cacheEntries":  cached,
        "favorites":     favs,
        "topCity":       dict(top_city) if top_city else None,
    }


# ─────────────────────────────────────────────
#  Serve frontend
# ─────────────────────────────────────────────
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def root():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
