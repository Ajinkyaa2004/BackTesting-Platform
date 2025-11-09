from __future__ import annotations
import os
import uuid
from datetime import datetime
import pandas as pd
from typing import Dict, Any
from trail_backtesting import (
    load_minute_data,
    calculate_ema,
    detect_signals,
    simulate_trades,
    analyze_performance,
)

# Prepare outputs per spec

def run_backtest_to_outputs(csv_path: str, params: Dict[str, Any], out_dir: str) -> tuple[dict, str, str, dict]:
    os.makedirs(out_dir, exist_ok=True)

    # Build config for strategy
    config = {
        'starting_balance': params['starting_balance'],
        'risk_percentage': params['risk_percentage'],
        'tick_size': params['tick_size'],
        'tick_value': params['tick_value'],
        'commission_per_trade': params['commission_per_trade'],
        'slippage_ticks': params['slippage_ticks'],
        'tp_ticks': params['tp_ticks'],
        'sl_ticks': params['sl_ticks'],
        'trailing_stop': params['trailing_stop'],
        'trailing_stop_ticks': params['trailing_stop_ticks'],
        'contract_margin': params['contract_margin'],
    }

    data = load_minute_data(csv_path)
    data = calculate_ema(data)
    data = detect_signals(data)
    trades_df = simulate_trades(data, config)

    # Metrics extended to match required fields
    metrics_base = analyze_performance(trades_df, initial_balance=config['starting_balance'])

    if trades_df.empty:
        # Ensure required columns exist
        trades_df = pd.DataFrame(columns=[
            'Entry Time','Type','Entry Price','Exit Time','Exit Price','Quantity','PNL','Outcome','Balance After Trade'
        ])

    # Enhance trades_df with cumulative_pnl for equity curve
    trades_df = trades_df.copy()
    trades_df['cumulative_pnl'] = trades_df['PNL'].cumsum()
    trades_df['cumulative_balance'] = config['starting_balance'] + trades_df['cumulative_pnl']

    # Map to required trades json
    trades_json = []
    for _, r in trades_df.iterrows():
        trades_json.append({
            "entry_time": r.get('Entry Time').strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(r.get('Entry Time')) else "",
            "position": r.get('Type',''),
            "entry_price": float(r.get('Entry Price', 0) or 0),
            "sl_price": None,
            "tp_price": None,
            "exit_time": r.get('Exit Time').strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(r.get('Exit Time')) else "",
            "exit_reason": r.get('Outcome',''),
            "exit_price": float(r.get('Exit Price', 0) or 0),
            "pnl": float(r.get('PNL', 0) or 0),
            "cumulative_pnl": float(r.get('cumulative_pnl', 0) or 0),
        })

    # Compute more metrics per spec
    total_trades = int(len(trades_df))
    wins = int((trades_df['PNL'] > 0).sum()) if total_trades else 0
    losses = total_trades - wins
    avg_pnl = float(trades_df['PNL'].mean()) if total_trades else 0.0
    total_pnl = float(trades_df['PNL'].sum()) if total_trades else 0.0
    avg_win = float(trades_df.loc[trades_df['PNL']>0, 'PNL'].mean()) if wins else 0.0
    avg_loss = float(trades_df.loc[trades_df['PNL']<0, 'PNL'].mean()) if losses else 0.0
    rr = abs(avg_win/avg_loss) if avg_loss != 0 else 0.0
    max_dd = float(trades_df['cumulative_balance'].cummax().sub(trades_df['cumulative_balance']).max()) if total_trades else 0.0
    # reuse sharpe if present else 0
    sharpe = float(metrics_base.get('Sharpe Ratio') or 0.0) if metrics_base else 0.0
    best = float(trades_df['PNL'].max()) if total_trades else 0.0
    worst = float(trades_df['PNL'].min()) if total_trades else 0.0

    metrics_json = {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": float(wins/total_trades) if total_trades else 0.0,
        "avg_pnl": avg_pnl,
        "total_pnl": total_pnl,
        "avg_win": avg_win if avg_win==avg_win else 0.0,
        "avg_loss": avg_loss if avg_loss==avg_loss else 0.0,
        "risk_reward_ratio": rr if rr==rr else 0.0,
        "max_drawdown": max_dd if max_dd==max_dd else 0.0,
        "sharpe_ratio": sharpe if sharpe==sharpe else 0.0,
        "best_trade": best if best==best else 0.0,
        "worst_trade": worst if worst==worst else 0.0,
    }

    # Chart data: equity curve and monthly returns
    equity_dates = [d.strftime('%Y-%m-%d %H:%M:%S') for d in trades_df['Exit Time'].dt.to_pydatetime()] if total_trades else []
    equity_balance = trades_df['cumulative_balance'].astype(float).tolist() if total_trades else []
    equity_curve = {"equity_curve": {"dates": equity_dates, "balance": equity_balance}}

    # Monthly returns from trades cumulative pnl diffs by month
    monthly = []
    months = []
    if total_trades:
        tmp = trades_df.copy()
        tmp['month'] = tmp['Exit Time'].dt.to_period('M').astype(str)
        grp = tmp.groupby('month')['PNL'].sum()
        months = list(grp.index)
        monthly = [float(v) for v in grp.values]
    monthly_returns = {"monthly_returns": {"months": months, "pnl": monthly}}

    # Write CSV outputs
    uid = uuid.uuid4().hex
    trades_csv = os.path.join(out_dir, f"trades_{uid}.csv")
    metrics_csv = os.path.join(out_dir, f"metrics_{uid}.csv")

    # Format trades.csv per spec
    export_df = trades_df.rename(columns={
        'Entry Time':'Entry Time',
        'Type':'Position',
        'Entry Price':'Entry Price',
        'Exit Time':'Exit Time',
        'Exit Price':'Exit Price',
        'PNL':'P&L'
    })
    # Add required columns with defaults
    if 'SL Price' not in export_df.columns:
        export_df['SL Price'] = None
    if 'TP Price' not in export_df.columns:
        export_df['TP Price'] = None
    if 'Outcome' in export_df.columns:
        export_df.rename(columns={'Outcome':'Exit Reason'}, inplace=True)

    # Reorder columns
    order = ['Entry Time','Position','Entry Price','SL Price','TP Price','Exit Time','Exit Reason','Exit Price','P&L','cumulative_pnl']
    for c in order:
        if c not in export_df.columns:
            export_df[c] = None
    export_df = export_df[order]

    export_df.to_csv(trades_csv, index=False)
    pd.DataFrame([metrics_json]).to_csv(metrics_csv, index=False)

    chart_data = {**equity_curve, **monthly_returns}

    payload = {
        "trades": trades_json,
        "metrics": metrics_json,
        "chart_data": chart_data,
    }

    return payload, trades_csv, metrics_csv, chart_data
