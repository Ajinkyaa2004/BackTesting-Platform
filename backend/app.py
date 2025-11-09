import os
import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from typing import Optional

from .db import SessionLocal, init_db
from .models import Backtest
from .schemas import BacktestParams, BacktestCreateResponse
from .utils import validate_csv, normalize_ohlc_headers
from .strategy_adapter import run_backtest_to_outputs

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "..", "data")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = FastAPI(title="Backtesting API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

@app.post("/backtests", response_model=BacktestCreateResponse)
async def create_backtest(
    file: UploadFile = File(...),
    params_json: str = Form(None),
):
    # Store uploaded file
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    bt_id = uuid.uuid4().hex
    stored_csv = os.path.join(DOWNLOAD_DIR, f"upload_{bt_id}.csv")

    contents = await file.read()
    with open(stored_csv, "wb") as f:
        f.write(contents)

    ok, msg, rows = validate_csv(stored_csv)
    if not ok:
        os.remove(stored_csv)
        raise HTTPException(status_code=400, detail=msg)

    normalize_ohlc_headers(stored_csv)

    # Parse params
    try:
        params = BacktestParams.model_validate_json(params_json) if params_json else BacktestParams()
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Persist a record with status running
    db = SessionLocal()
    try:
        bt = Backtest(
            id=bt_id,
            original_filename=file.filename,
            stored_csv_path=stored_csv,
            params=params.model_dump(),
            status="running",
            rows=rows,
            size_bytes=len(contents),
        )
        db.add(bt)
        db.commit()
    finally:
        db.close()

    # Run backtest synchronously for now
    try:
        payload, trades_csv, metrics_csv, chart_data = run_backtest_to_outputs(
            stored_csv, params.model_dump(), DOWNLOAD_DIR
        )
    except Exception as e:
        db = SessionLocal()
        try:
            bt = db.get(Backtest, bt_id)
            if bt:
                bt.status = "failed"
                bt.error = str(e)
                db.commit()
        finally:
            db.close()
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")

    # Save results
    db = SessionLocal()
    try:
        bt = db.get(Backtest, bt_id)
        bt.status = "completed"
        bt.metrics = payload["metrics"]
        bt.equity_curve = chart_data.get("equity_curve")
        bt.monthly_returns = chart_data.get("monthly_returns")
        bt.trades_csv_path = trades_csv
        bt.metrics_csv_path = metrics_csv
        db.commit()
    finally:
        db.close()

    return {"id": bt_id}

@app.get("/backtests")
async def list_backtests():
    db = SessionLocal()
    try:
        rows = db.query(Backtest).order_by(Backtest.created_at.desc()).all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "created_at": r.created_at,
                "filename": r.original_filename,
                "status": r.status,
                "rows": r.rows,
                "size_bytes": r.size_bytes,
            })
        return out
    finally:
        db.close()

@app.get("/backtests/{bt_id}")
async def get_backtest(bt_id: str):
    db = SessionLocal()
    try:
        r = db.get(Backtest, bt_id)
        if not r:
            raise HTTPException(status_code=404, detail="Not found")
        if r.status != "completed":
            return {"status": r.status, "error": r.error}

        def dl(path: str) -> str:
            return f"/downloads/{os.path.basename(path)}"

        return {
            "trades": [],  # trades table can be large; frontend can stream/download
            "metrics": r.metrics or {},
            "chart_data": {
                "equity_curve": r.equity_curve or {"dates": [], "balance": []},
                "monthly_returns": r.monthly_returns or {"months": [], "pnl": []},
            },
            "download_links": {
                "trades_csv": dl(r.trades_csv_path) if r.trades_csv_path else None,
                "metrics_csv": dl(r.metrics_csv_path) if r.metrics_csv_path else None,
            },
        }
    finally:
        db.close()

@app.get("/downloads/{filename}")
async def download_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename)

