from typing import Optional
from pydantic import BaseModel, Field

class BacktestParams(BaseModel):
    starting_balance: float = 100000
    tp_ticks: int = Field(20, ge=10, le=50)
    sl_ticks: int = Field(20, ge=10, le=50)
    risk_percentage: float = Field(0.01, ge=0.005, le=0.05)
    trailing_stop: bool = False
    trailing_stop_ticks: int = Field(5, ge=3, le=20)
    tick_size: float = 0.25
    tick_value: float = 5.0
    commission_per_trade: float = 5.0
    slippage_ticks: int = 1
    contract_margin: float = 13000

class BacktestCreateResponse(BaseModel):
    id: str

class DownloadLinks(BaseModel):
    trades_csv: str
    metrics_csv: str

class ChartSeries(BaseModel):
    dates: list[str]
    balance: list[float]

class MonthlyReturns(BaseModel):
    months: list[str]
    pnl: list[float]

class Metrics(BaseModel):
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_pnl: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    risk_reward_ratio: float
    max_drawdown: float
    sharpe_ratio: float
    best_trade: float
    worst_trade: float

class Trade(BaseModel):
    entry_time: str
    position: str
    entry_price: float
    sl_price: float | None = None
    tp_price: float | None = None
    exit_time: str
    exit_reason: str
    exit_price: float
    pnl: float
    cumulative_pnl: float

class BacktestDetail(BaseModel):
    trades: list[Trade]
    metrics: Metrics
    chart_data: dict
    download_links: DownloadLinks
