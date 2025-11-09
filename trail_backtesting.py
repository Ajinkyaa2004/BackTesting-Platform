import pandas as pd
import numpy as np
import plotly.graph_objects as go
import datetime
import os
from itertools import product
from tqdm import tqdm


CONFIG = {
    'starting_balance': 100000,
    'risk_percentage': 0.01,           # New risk parameter
    'tick_size': 0.25,
    'tick_value': 5,
    'commission_per_trade': 5,
    'slippage_ticks': 1,
    'tp_ticks': 20,
    'sl_ticks': 20,
    'trailing_stop': False,
    'trailing_stop_ticks': 5,
    'contract_margin': 13000           # Updated margin
}


def load_minute_data(filepath):
    data = pd.read_csv(filepath, parse_dates=['date_time'])
    data.rename(columns={'date_time': 'datetime'}, inplace=True)
    data['datetime'] = data['datetime'].dt.tz_localize(None)  # Optional: remove timezone info
    data.sort_values('datetime', inplace=True)
    return data


def calculate_ema(data, span=9):
    data['ema9'] = data['close'].ewm(span=span, adjust=False).mean()
    return data

def detect_signals(data):
    data['signal'] = 0  # 1 for long, -1 for short
    
    for i in range(3, len(data)):
        last3 = data.iloc[i-3:i]
        current = data.iloc[i]
        
        if all(last3['close'] < last3['open']) and all(last3['close'] < last3['ema9']):
        # if all(last3['open'] < last3['ema9']) and all(last3['close'] < last3['ema9']):
            # Now wait for candle closing above EMA9 
            if data.iloc[i]['close'] > data.iloc[i]['ema9']:
                data.at[i, 'signal'] = 1

        # Check green candles for short setup
        if all(last3['close'] > last3['open']) and all(last3['close'] > last3['ema9']):
        # if all(last3['open'] > last3['ema9']) and all(last3['close'] > last3['ema9']):
            # Now wait for candle closing below EMA9
            if data.iloc[i]['close'] < data.iloc[i]['ema9']:
                data.at[i, 'signal'] = -1

    return data

def simulate_trades(data, config):
    balance = config['starting_balance']
    open_trade = None
    trades = []
    
    for i in tqdm(range(4, len(data)), desc="Simulating Trades", leave=False):
        row = data.iloc[i]
        
        # Calculate maximum contracts based on BOTH margin and risk
        max_contracts_margin = balance // config['contract_margin']
        risk_per_trade = balance * config['risk_percentage']
        max_contracts_risk = risk_per_trade // (config['sl_ticks'] * config['tick_value'])
        # qty = min(max_contracts_margin, max_contracts_risk)
        qty = 1


        if open_trade:
            # Check for exit conditions
            if open_trade['type'] == 'long':
                tp_price = open_trade['entry_price'] + config['tp_ticks'] * config['tick_size']
                sl_price = open_trade['entry_price'] - config['sl_ticks'] * config['tick_size']

                if config['trailing_stop']:
                    max_price = max(open_trade['max_price'], row['high'])
                    new_sl = max_price - config['trailing_stop_ticks'] * config['tick_size']
                    sl_price = max(sl_price, new_sl)
                    open_trade['max_price'] = max_price

                if row['high'] >= tp_price:
                    exit_price = tp_price
                    outcome = 'TP'
                elif row['low'] <= sl_price:
                    exit_price = sl_price
                    outcome = 'SL'
                else:
                    continue  # stay in trade

            elif open_trade['type'] == 'short':
                tp_price = open_trade['entry_price'] - config['tp_ticks'] * config['tick_size']
                sl_price = open_trade['entry_price'] + config['sl_ticks'] * config['tick_size']

                if config['trailing_stop']:
                    min_price = min(open_trade['min_price'], row['low'])
                    new_sl = min_price + config['trailing_stop_ticks'] * config['tick_size']
                    sl_price = min(sl_price, new_sl)
                    open_trade['min_price'] = min_price

                if row['low'] <= tp_price:
                    exit_price = tp_price
                    outcome = 'TP'
                elif row['high'] >= sl_price:
                    exit_price = sl_price
                    outcome = 'SL'
                else:
                    continue  # stay in trade
            
            # Close trade
            qty = open_trade['quantity']
            pnl = (exit_price - open_trade['entry_price']) * qty * config['tick_value'] / config['tick_size']
            if open_trade['type'] == 'short':
                pnl = -pnl

            # Deduct commission and slippage
            total_cost = config['commission_per_trade'] + config['slippage_ticks'] * config['tick_value'] * 2
            pnl -= total_cost
            balance += pnl

            trades.append({
                'Entry Time': open_trade['entry_time'],
                'Exit Time': row['datetime'],
                'Type': open_trade['type'],
                'Entry Price': open_trade['entry_price'],
                'Exit Price': exit_price,
                'Quantity': qty,
                'PNL': pnl,
                'Outcome': outcome,
                'Balance After Trade': balance
            })
            open_trade = None

        # Open new trade if signal and no trade is open
        if row['signal'] != 0 and open_trade is None:
            if qty < 1:
                continue  # Not enough margin or risk capacity
            open_trade = {
                'entry_time': row['datetime'],
                'entry_price': row['close'],
                'quantity': qty,
                'type': 'long' if row['signal'] == 1 else 'short',
                'max_price': row['close'],
                'min_price': row['close']
            }

    trades_df = pd.DataFrame(trades)
    return trades_df


def analyze_performance(trades_df, initial_balance=CONFIG['starting_balance']):
    if trades_df.empty:
        return {}

    # Calculate win rate
    win_rate = (trades_df['PNL'] > 0).mean()

    # Total trades
    total_trades = len(trades_df)

    # Average profit per trade
    avg_profit = trades_df['PNL'].mean()

    # Total profit
    total_profit = trades_df['PNL'].sum()

    # Profit percentage (based on starting balance)
    profit_percentage = (total_profit / initial_balance) * 100

    # Cumulative performance
    trades_df['cumulative_pnl'] = trades_df['PNL'].cumsum()
    trades_df['cumulative_balance'] = initial_balance + trades_df['cumulative_pnl']

    # Max drawdown
    max_drawdown = (trades_df['cumulative_balance'].cummax() - trades_df['cumulative_balance']).max()

    # Returns (to calculate Sharpe ratio)
    returns = trades_df['PNL'] / initial_balance

    # Sharpe ratio
    sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252*24*60) if returns.std() != 0 else np.nan

    return {
        'Total Trades': total_trades,
        'Win Rate': win_rate,
        'Average Profit per Trade': avg_profit,
        'Total Profit': total_profit,
        'Profit Percentage': profit_percentage,
        'Max Drawdown': max_drawdown,
        'Sharpe Ratio': sharpe_ratio
    }

def save_trades(trades_df, path='trades.csv'):
    trades_df.to_csv(path, index=False)

def save_metrics(metrics, path='metrics.csv'):
    df = pd.DataFrame([metrics])
    df.to_csv(path, index=False)


def plot_trades(data, trades_df, output_folder='plots', months_per_plot=3):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    start_date = data['datetime'].min()
    end_date = data['datetime'].max()
    
    current_start = start_date
    plot_idx = 1
    
    while current_start < end_date:
        current_end = current_start + pd.DateOffset(months=months_per_plot)
        
        chunk_data = data[(data['datetime'] >= current_start) & (data['datetime'] < current_end)]
        chunk_trades = trades_df[(trades_df['Entry Time'] >= current_start) & (trades_df['Entry Time'] < current_end)]
        
        fig = go.Figure()

        # Add candlestick plot
        fig.add_trace(go.Candlestick(
            x=chunk_data['datetime'],
            open=chunk_data['open'],
            high=chunk_data['high'],
            low=chunk_data['low'],
            close=chunk_data['close'],
            name='Candles'
        ))

        # Add EMA9 line
        fig.add_trace(go.Scatter(
            x=chunk_data['datetime'], 
            y=chunk_data['ema9'], 
            mode='lines',
            line=dict(color='orange', width=1),
            name='EMA9'
        ))

        # Mark trades
        for _, trade in chunk_trades.iterrows():
            color = 'green' if trade['Type'] == 'long' else 'red'
            fig.add_trace(go.Scatter(
                x=[trade['Entry Time']], 
                y=[trade['Entry Price']],
                mode='markers',
                marker=dict(color=color, size=10, symbol='arrow-up' if trade['Type']=='long' else 'arrow-down'),
                name=f"Entry ({trade['Type']})"
            ))
            fig.add_trace(go.Scatter(
                x=[trade['Exit Time']], 
                y=[trade['Exit Price']],
                mode='markers',
                marker=dict(color='blue', size=8, symbol='x'),
                name="Exit"
            ))

        fig.update_layout(
            title=f"Strategy Backtest ({current_start.date()} to {current_end.date()})",
            xaxis_title="Time",
            yaxis_title="Price",
            xaxis_rangeslider_visible=False,
            template="plotly_dark"
        )
        
        filename = f"{output_folder}/strategy_candles_{plot_idx:03d}.html"
        fig.write_html(filename)
        print(f"Saved: {filename}")

        plot_idx += 1
        current_start = current_end

    print("All plots saved.")


def optimize_parameters(filepath, tp_range, sl_range, trailing_range, config):
    results = []
    
    for tp_ticks, sl_ticks, trailing_ticks in product(tp_range, sl_range, trailing_range):
        # Update config for this run
        config['tp_ticks'] = tp_ticks
        config['sl_ticks'] = sl_ticks
        
        if trailing_ticks == 0:
            config['trailing_stop'] = False
            config['trailing_stop_ticks'] = 0
        else:
            config['trailing_stop'] = True
            config['trailing_stop_ticks'] = trailing_ticks
        
        print(f"Testing TP={tp_ticks} SL={sl_ticks} TSL={trailing_ticks}")
        
        try:
            data = load_minute_data(filepath)
            data = calculate_ema(data)
            data = detect_signals(data)
            trades_df = simulate_trades(data, config)
            metrics = analyze_performance(trades_df)

            if metrics:  # Only if any trades occurred
                results.append({
                    'TP_Ticks': tp_ticks,
                    'SL_Ticks': sl_ticks,
                    'Trailing_Ticks': trailing_ticks,
                    'Total Profit': metrics['Total Profit'],
                    'Win Rate': metrics['Win Rate'],
                    'Sharpe Ratio': metrics['Sharpe Ratio'],
                    'Max Drawdown': metrics['Max Drawdown'],
                    'Total Trades': metrics['Total Trades'],
                    'Average Profit per Trade': metrics['Average Profit per Trade']
                })

        except Exception as e:
            print(f"Error at TP={tp_ticks}, SL={sl_ticks}, TSL={trailing_ticks}: {e}")
    
    results_df = pd.DataFrame(results)
    results_df.to_csv('optimization_results.csv', index=False)
    
    if not results_df.empty:
        best_row = results_df.sort_values(by='Sharpe Ratio', ascending=False).iloc[0]
        print("\nBest Parameters Found:")
        print(best_row)
        return best_row, results_df
    else:
        print("No trades found in any configuration.")
        return None, None




def run_backtest(filepath):
    data = load_minute_data(filepath)
    data = calculate_ema(data)
    data = detect_signals(data)
    trades_df = simulate_trades(data, CONFIG)
    metrics = analyze_performance(trades_df)

    save_trades(trades_df)
    save_metrics(metrics)
    plot_trades(data, trades_df)
    
    return trades_df, metrics

if __name__ == "__main__":
    input_data = "nq_ohlcv_minute_combined_2020_2025.csv"
    trades, stats = run_backtest(input_data)
    print(stats)


#     cd /Users/ajinkya/Desktop/Backtesting_platform
#     source backtest_env/bin/activate
#     uvicorn backend.app:app --reload --port 8000


#     cd /Users/ajinkya/Desktop/Backtesting_platform
#     python3 -m http.server 3000 --directory web