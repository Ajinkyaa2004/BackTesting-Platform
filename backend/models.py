from sqlalchemy import Column, String, DateTime, JSON, Integer
from sqlalchemy.sql import func
from .db import Base

class Backtest(Base):
    __tablename__ = "backtests"

    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    original_filename = Column(String, nullable=False)
    stored_csv_path = Column(String, nullable=False)

    params = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=True)
    equity_curve = Column(JSON, nullable=True)
    monthly_returns = Column(JSON, nullable=True)

    trades_csv_path = Column(String, nullable=True)
    metrics_csv_path = Column(String, nullable=True)

    status = Column(String, default="completed")  # completed | failed | running
    error = Column(String, nullable=True)
    rows = Column(Integer, nullable=True)
    size_bytes = Column(Integer, nullable=True)
