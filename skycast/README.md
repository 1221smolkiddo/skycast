# ☁️ SkyCast — AI Weather App

A production-ready weather app with a FastAPI backend, SQLite database,
real OpenWeatherMap data, optional Anthropic AI insights, and a polished HTML frontend.

---

## 🗂 Project Structure

```
skycast/
├── backend/
│   ├── main.py              ← FastAPI app (all endpoints)
│   ├── requirements.txt
│   ├── .env.example         ← Copy to .env and add your keys
│   └── skycast.db           ← SQLite DB (auto-created on first run)
├── frontend/
│   └── index.html           ← Full frontend (open directly or served by backend)
├── start.sh                 ← One-command startup
└── README.md
```

---

## 🚀 Quick Start

### 1. Get your API key

Sign up free at [openweathermap.org/api](https://openweathermap.org/api)
and copy your API key (activates within a few minutes).

### 2. Configure environment

```bash
cd backend
cp .env.example .env
# Open .env and set:
#   OWM_API_KEY=your_actual_key_here
```

### 3. Install & run

```bash
# Option A — use the start script (recommended)
bash start.sh

# Option B — manual
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Open the app

Visit **http://localhost:8000** in your browser.

---

## 🔑 Environment Variables

| Variable          | Required | Default      | Description                            |
|-------------------|----------|--------------|----------------------------------------|
| `OWM_API_KEY`     | ✅ Yes   | —            | OpenWeatherMap API key                 |
| `ANTHROPIC_API_KEY` | No     | —            | Enables real AI weather insights       |
| `CACHE_TTL`       | No       | `600`        | Seconds to cache each city's weather   |
| `DB_PATH`         | No       | `skycast.db` | SQLite database file path              |

---

## 📡 API Endpoints

| Method | Endpoint                    | Description                          |
|--------|-----------------------------|--------------------------------------|
| GET    | `/api/weather?city=London`  | Current weather + forecast + AI      |
| GET    | `/api/history?limit=10`     | Recent city searches from DB         |
| GET    | `/api/favorites`            | Saved favorite cities                |
| POST   | `/api/favorites?city=Paris` | Add a favorite                       |
| DELETE | `/api/favorites/{city}`     | Remove a favorite                    |
| GET    | `/api/stats`                | App usage statistics                 |
| GET    | `/docs`                     | Swagger UI (interactive API docs)    |

---

## 🌦 Features

- **Real weather data** — OpenWeatherMap (current + 5-day forecast + air quality)
- **AI insights** — Anthropic Claude writes a practical weather summary (optional)
- **Smart caching** — SQLite caches results for 10 min to save API calls
- **Search history** — All searches logged to DB, shown as quick-access pills
- **Favorites** — Save cities with one click, persisted in SQLite
- **Dynamic UI** — Background sky, animated SVG clouds, rain/snow particles change per condition
- **Dark / Light mode** — Toggle anytime
- **°C / °F toggle** — Instant conversion, no re-fetch needed
- **Air Quality Index** — Colour-coded AQI from OWM pollution API
- **Wind compass** — Direction arrow rotates to actual wind bearing

---

## 🛠 Tech Stack

| Layer     | Technology                       |
|-----------|----------------------------------|
| Backend   | Python 3.10+, FastAPI, Uvicorn   |
| Database  | SQLite via Python `sqlite3`      |
| Weather   | OpenWeatherMap API (free tier)   |
| AI        | Anthropic Claude Haiku (optional)|
| Frontend  | Vanilla HTML / CSS / JS          |
| Fonts     | Google Fonts (Syne + DM Sans)    |
