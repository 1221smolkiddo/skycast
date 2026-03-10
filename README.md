# SkyCast

SkyCast is a full-stack weather app with a FastAPI backend, SQLite caching, optional AI insights, and a static HTML/CSS/JS frontend.

## Features
- Current weather, 5-day forecast, and air quality via OpenWeatherMap
- Optional AI weather summary via Anthropic
- SQLite-backed cache, search history, and favorites
- Polished single-page frontend with dynamic visuals, unit toggle, and light/dark mode

## Project Structure
- `backend/` FastAPI app, database, and environment config
- `frontend/` static frontend (served by the backend)
- `requirements.txt` Python dependencies

## Requirements
- Python 3.10+
- OpenWeatherMap API key
- (Optional) Anthropic API key for AI insights

## Setup
1. Create the backend environment file:
   - Copy `backend/.env.example` to `backend/.env`
   - Set `OWM_API_KEY` to your OpenWeatherMap key
   - Optionally set `ANTHROPIC_API_KEY`

2. Install dependencies (from repo root):

```bash
pip install -r requirements.txt
```

## Run
Start the backend (from repo root):

```bash
uvicorn backend.main:app --reload --port 8000
```

Open the app at `http://localhost:8000`.

## Environment Variables
- `OWM_API_KEY` (required): OpenWeatherMap API key
- `ANTHROPIC_API_KEY` (optional): Enables AI insights
- `CACHE_TTL` (optional, default 600): Cache TTL in seconds
- `DB_PATH` (optional, default `skycast.db`): SQLite file path

## API Endpoints
- `GET /api/weather?city=London` Current weather, forecast, AQI, AI insight
- `GET /api/history?limit=10` Recent searches
- `GET /api/favorites` List favorites
- `POST /api/favorites?city=Paris` Add favorite
- `DELETE /api/favorites/{city}` Remove favorite
- `GET /api/stats` App stats
- `GET /docs` Swagger UI

## Notes
- The backend serves the frontend from `frontend/index.html` at the root path `/`.
- SQLite data is stored in `backend/skycast.db` by default.
