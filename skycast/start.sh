#!/bin/bash
# SkyCast — start backend server
set -e

cd "$(dirname "$0")/backend"

# Load .env if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
  echo "✅ Loaded .env"
else
  echo "⚠️  No .env found. Copying .env.example → .env"
  cp .env.example .env
  echo "👉 Edit backend/.env and add your OWM_API_KEY, then re-run this script."
  exit 1
fi

# Install deps if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "📦 Installing dependencies..."
  pip install -r requirements.txt --break-system-packages -q
fi

echo ""
echo "  ☁️  SkyCast backend starting..."
echo "  → API:      http://localhost:8000/api/weather?city=London"
echo "  → Frontend: http://localhost:8000"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
