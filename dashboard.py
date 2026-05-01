import streamlit as st
import pandas as pd
import json, os, time

st.set_page_config(page_title="Invading Edge Paper Trader", layout="wide")
st.title("📊 Live Paper Trading Dashboard")
st.markdown("*Auto-refreshes every 30s. Data sourced from private GitHub repo.*")

@st.cache_data(ttl=30)
def load_data():
    state = json.load(open('state.json')) if os.path.exists('state.json') else {}
    trades = pd.read_csv('trades.csv') if os.path.exists('trades.csv') else pd.DataFrame()
    return state, trades

def run():
    state, trades = load_data()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Account", f"₹{state.get('account',5000):,.2f}")
    col2.metric("Daily P&L", f"₹{state.get('daily_pnl',0):,.2f}")
    col3.metric("Open Positions", len(state.get('open_positions',[])))
    col4.metric("Consecutive SL", state.get('consecutive_sl',0))
    
    st.subheader("🟢 Active Positions")
    if state.get('open_positions'):
        st.dataframe(pd.DataFrame(state['open_positions']), use_container_width=True)
    else:
        st.info("Scanning for setups...")
        
    st.subheader("📈 Trade Journal")
    if not trades.empty:
        st.dataframe(trades[['ticker','action','price','pnl','time']].tail(20), use_container_width=True)
        
    st.subheader("✅ Compliance Checklist")
    checks = [
        ("Max 2 Trades Open", "✅" if len(state.get('open_positions',[]))<=2 else "❌"),
        ("Daily Loss < ₹200", "✅" if state.get('daily_pnl',0) > -200 else "⛔ HALTED"),
        ("Consecutive SL < 2", "✅" if state.get('consecutive_sl',0)<2 else "⛔ HALTED"),
        ("VIX < 20", "✅" if state.get('vix',15)<20 else "⚠️ Reduced Size"),
        ("1:2 Min R:R Enforced", "✅ (Code Locked)"),
        ("No Averaging Down", "✅ (Code Locked)")
    ]
    for k,v in checks: st.markdown(f"**{k}**: {v}")

run()
time.sleep(30); st.rerun()
