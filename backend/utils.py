import os
import pandas as pd
from typing import Tuple

REQUIRED_COL_SETS = [
    {"date_time", "open", "high", "low", "close"},
    {"datetime", "open", "high", "low", "close"},
    {"date time", "open", "high", "low", "close"},
]

MAX_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 220 * 1024 * 1024))


def validate_csv(file_path: str) -> Tuple[bool, str, int]:
    size = os.path.getsize(file_path)
    if size > MAX_SIZE_BYTES:
        return False, f"File too large. Limit {MAX_SIZE_BYTES} bytes.", 0

    # Read a small chunk to validate headers and get row count efficiently
    try:
        df_head = pd.read_csv(file_path, nrows=10)
    except Exception as e:
        return False, f"Unable to read CSV: {e}", 0

    cols = set(c.strip().lower() for c in df_head.columns)
    if not any(req.issubset(cols) for req in REQUIRED_COL_SETS):
        return False, "Missing required columns: date_time/date time, open, high, low, close", 0

    # Count rows quickly
    try:
        total_rows = sum(1 for _ in open(file_path, "rb")) - 1  # minus header
    except Exception:
        total_rows = 0

    return True, "ok", max(total_rows, 0)


def normalize_ohlc_headers(file_path: str) -> str:
    # Ensure downstream expects 'date_time'
    df_iter = pd.read_csv(file_path)
    lower = {c.lower(): c for c in df_iter.columns}
    rename_map = {}
    if "date time" in lower:
        rename_map[lower["date time"]] = "date_time"
    if "datetime" in lower:
        rename_map[lower["datetime"]] = "date_time"
    # Standardize case for prices as well
    for k in ["open", "high", "low", "close", "volume", "symbol"]:
        if k in lower:
            rename_map[lower[k]] = k
    if rename_map:
        df_iter.rename(columns=rename_map, inplace=True)
        df_iter.to_csv(file_path, index=False)
    return file_path
