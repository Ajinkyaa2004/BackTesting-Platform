# Trading Strategy Backtesting Backend (FastAPI)

## Quickstart

1. Create venv and install deps
```
pip install -r requirements.txt
```

2. Run API
```
uvicorn backend.app:app --reload
```

3. Endpoints
- POST /backtests (multipart: file, params_json) -> { id }
- GET /backtests -> list
- GET /backtests/{id} -> detail JSON with metrics, charts, download links
- GET /downloads/{filename} -> file download

Params JSON matches 11 inputs in `backend/schemas.py` BacktestParams.

## Notes
- Uses SQLite by default; set DATABASE_URL env for Postgres/MySQL.
- CSV must include: date_time|datetime|date time + open, high, low, close.
- Large files supported up to 100MB (configurable with MAX_UPLOAD_BYTES).

## Using existing strategy
The backend imports and wraps `trail_backtesting.py` and does not alter its core logic.
# BackTesting-Platform
