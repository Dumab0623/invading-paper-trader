import yfinance as yf
import pandas as pd
import json, os, math
from datetime import datetime, time
import pytz

IST = pytz.timezone('Asia/Kolkata')
NOW = datetime.now(IST)

# Load persistent state
STATE_FILE = 'state.json'
TRADES_FILE = 'trades.csv'
WATCHLIST = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ITC.NS", "RVNL.NS", "IRFC.NS"]

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f: return json.load(f)
    return {
        "account": 5000.0, "daily_pnl": 0.0, "weekly_pnl": 0.0,
        "consecutive_sl": 0, "open_positions": [], "trades_today": 0,
        "last_reset": NOW.strftime('%Y-%m-%d')
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=2)

def append_trade(trade):
    df = pd.DataFrame([trade])
    header = not os.path.exists(TRADES_FILE)
    df.to_csv(TRADES_FILE, mode='a', header=header, index=False)

def is_market_hours():
    t = NOW.time()
    return (time(9,30) <= t <= time(11,30)) or (time(13,30) <= t <= time(15,0))

def fetch_data(ticker):
    try:
        df = yf.download(ticker, period="5d", interval="5m", progress=False)
        if df.empty: return None
        return df
    except: return None

def apply_filters(df, ticker, state):
    if df is None or df.shape[0] < 20: return False, "Insufficient data"
    close = df['Close']
    vol = df['Volume']
    
    # Layer 1 & 8: VIX & Ban check (simplified)
    if state.get('vix', 15) > 20: return False, "VIX > 20"
    # Layer 2.1: Volume Shock
    avg_vol = vol.rolling(20).mean().iloc[-1]
    if vol.iloc[-1] < 3 * avg_vol: return False, "Low volume"
    # Layer 2.2: Price Structure
    if close.iloc[-1] <= close.iloc[-2]: return False, "No higher high"
    if close.iloc[-1] <= close.rolling(20).mean().iloc[-1]: return False, "Below 20SMA"
    # Layer 2.3: Relative Strength (vs Nifty proxy)
    nifty = yf.download("^NSEI", period="1d", interval="5m", progress=False)['Close']
    if not nifty.empty:
        stock_chg = (close.iloc[-1]/close.iloc[-2])-1
        nifty_chg = (nifty.iloc[-1]/nifty.iloc[-2])-1 if len(nifty)>1 else 0
        if stock_chg < 2 * max(nifty_chg, 0.001): return False, "Weak RS"
    # Layer 2.7: Liquidity (~10Cr)
    if (vol.iloc[-1] * close.iloc[-1]) < 5e7: return False, "Low turnover"
    return True, "Pass"

def manage_positions(state):
    for pos in state['open_positions'][:]:
        price = pos.get('current_price')
        if price is None: continue
        
        # Layer 5: Trailing SL
        pnl_pct = (price - pos['entry']) / pos['entry'] * 100
        if pnl_pct >= 3: pos['trail_sl'] = max(pos['trail_sl'], pos['entry'])
        if pnl_pct >= 5: pos['trail_sl'] = max(pos['trail_sl'], pos['entry'] * 1.02)
        if pnl_pct >= 8: pos['trail_sl'] = max(pos['trail_sl'], pos['entry'] * 1.05)
        
        # Layer 6: Partial Booking & Exit
        if not pos['partial_booked'] and price >= (pos['entry'] + (pos['entry'] - pos['sl'])):
            pos['partial_booked'] = True
            booked_shares = pos['size'] // 2
            pnl = (price - pos['entry']) * booked_shares
            state['daily_pnl'] += pnl; state['weekly_pnl'] += pnl; state['account'] += pnl
            pos['size'] = booked_shares
            append_trade({**pos, 'action':'PARTIAL', 'price':price, 'pnl':pnl, 'time':str(NOW)})
            
        if price <= pos['trail_sl'] or (pos['partial_booked'] and price <= pos['trail_sl']):
            pnl = (price - pos['entry']) * pos['size']
            state['daily_pnl'] += pnl; state['weekly_pnl'] += pnl; state['account'] += pnl
            state['consecutive_sl'] += 1 if price <= pos['trail_sl'] else 0
            state['trades_today'] += 1
            append_trade({**pos, 'action':'CLOSE', 'price':price, 'pnl':pnl, 'time':str(NOW)})
            state['open_positions'].remove(pos)

def main():
    state = load_state()
    if NOW.strftime('%Y-%m-%d') != state['last_reset']:
        state['daily_pnl'], state['trades_today'], state['consecutive_sl'] = 0, 0, 0
        state['last_reset'] = NOW.strftime('%Y-%m-%d')
        
    # Daily/Weekly limits (Layer 9)
    if state['daily_pnl'] <= -200 or state['consecutive_sl'] >= 2:
        save_state(state); return
        
    manage_positions(state)
    
    if is_market_hours() and len(state['open_positions']) < 2:
        for ticker in WATCHLIST:
            df = fetch_data(ticker)
            passed, msg = apply_filters(df, ticker, state)
            if passed:
                entry = df['Close'].iloc[-1]
                sl = entry * 0.97
                target = entry + 2*(entry - sl)
                size = max(1, int(100 / (entry - sl)))
                if size * entry <= 2500:  # Layer 4: Max 50% capital
                    state['open_positions'].append({
                        'ticker': ticker, 'entry': entry, 'sl': sl, 'target': target,
                        'size': size, 'trail_sl': sl, 'partial_booked': False,
                        'entry_time': str(NOW)
                    })
                    break  # Max 2 trades enforced by loop limit
                    
        # Update current prices for open positions
        for pos in state['open_positions']:
            df = fetch_data(pos['ticker'])
            if df is not None: pos['current_price'] = df['Close'].iloc[-1]
            
    # Fetch VIX for next run
    vix = yf.download("^INDIAVIX", period="1d", interval="5m", progress=False)
    state['vix'] = vix['Close'].iloc[-1] if not vix.empty else 15
    
    save_state(state)
    print(f"Run complete. Open: {len(state['open_positions'])}, P&L: {state['daily_pnl']}")

if __name__ == '__main__':
    main()
