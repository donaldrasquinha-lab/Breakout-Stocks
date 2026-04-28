import streamlit as st
import pandas as pd
import requests
import time
import os
import gzip
from datetime import datetime, timedelta
from niftystocks import ns

# ----------------------------- Page Config ----------------------------- #
st.set_page_config(page_title="Breakout Hub", page_icon="🚀", layout="wide")
UPSTOX_BASE = "https://upstox.com"

# ----------------------------- Helpers ----------------------------- #
def get_v2_headers(token):
    return {"Accept": "application/json", "Api-Version": "2.0", "Authorization": f"Bearer {token}"}

@st.cache_data(ttl=86400)
def get_mapping():
    url = "https://upstox.com"
    try:
        response = requests.get(url, timeout=30)
        df = pd.read_json(gzip.decompress(response.content))
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except: return {}

def fetch_upstox(token, key):
    if not key: return None
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    url = f"{UPSTOX_BASE}/historical-candle/{key.replace('|', '%7C')}/day/{to_date}/{from_date}"
    try:
        time.sleep(0.02) # Rate limit protection
        res = requests.get(url, headers=get_v2_headers(token), timeout=15)
        if res.status_code == 200:
            df = pd.DataFrame(res.json().get('data', {}).get('candles', []), 
                              columns=["Date","Open","High","Low","Close","Volume","OI"])
            return df.iloc[::-1].set_index(pd.to_datetime(df["Date"])).apply(pd.to_numeric)
        return None
    except: return None

# ----------------------------- Sidebar ----------------------------- #
st.sidebar.title("📡 Connection")
source = st.sidebar.selectbox("Data Provider", ["Upstox", "Yahoo Finance"])
token = st.sidebar.text_input("Access Token", type="password") if source == "Upstox" else ""

is_connected = False
if source == "Upstox" and token:
    is_connected = requests.get(f"{UPSTOX_BASE}/user/profile", headers=get_v2_headers(token)).status_code == 200
    if is_connected: st.sidebar.success("🟢 Connected")
    else: st.sidebar.error("🔴 Connection Failed")
elif source == "Yahoo Finance": is_connected = True

# ----------------------------- Scanner ----------------------------- #
st.title("📈 Smart Breakout Hub")

if st.sidebar.button("🔍 Run Nifty 500 Scan") and is_connected:
    mapping = get_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    headers = ["Ticker", "Price", "Vol_Ratio"] # Define headers
    
    pb = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status.text(f"Scanning {symbol} ({i+1}/{len(tickers)})...")
        df = None
        if source == "Upstox":
            key = mapping.get(symbol)
            if key: df = fetch_upstox(token, key)
        else:
            import yfinance as yf
            try:
                df = yf.download(t, period='1y', interval='1d', progress=False)
                if not df.empty: df.columns = [c.capitalize() for c in df.columns]
            except: pass
            time.sleep(0.4)

        if df is not None and not df.empty and len(df) > 50:
            df['Resist'] = df['High'].rolling(20).max().shift(1)
            df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
            last = df.iloc[-1]
            if last['Close'] > last['Resist'] and last['Volume'] > (last['Avg_Vol'] * 1.5):
                results.append({"Ticker": symbol, "Price": round(float(last['Close']), 2), "Vol_Ratio": round(float(last['Volume']/last['Avg_Vol']), 2)})
        pb.progress((i + 1) / len(tickers))
    
    # CRITICAL: Always save with headers even if empty
    pd.DataFrame(results, columns=headers).to_csv("breakout_results.csv", index=False)
    st.rerun()

# ----------------------------- Results Display ----------------------------- #
CSV_FILE = "breakout_results.csv"
if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
    try:
        df_res = pd.read_csv(CSV_FILE)
        if not df_res.empty:
            st.subheader(f"Latest Breakouts ({len(df_res)})")
            st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
        else:
            st.info("No breakouts found. Try another scan later.")
    except Exception as e:
        st.error(f"Data error: {e}")
else:
    st.warning("No data found. Start a scan from the sidebar.")
