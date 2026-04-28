import streamlit as st
import pandas as pd
import requests
import time
import os
import gzip
from datetime import datetime, timedelta
import plotly.graph_objects as go
from niftystocks import ns

# --- CONFIG ---
st.set_page_config(page_title="Breakout Hub", layout="wide")
UPSTOX_BASE = "https://api.upstox.com/v2"

# --- HELPERS ---
def get_headers(token):
    return {"Accept": "application/json", "Authorization": f"Bearer {token}"}

@st.cache_data(ttl=86400)
def get_mapping():
    url = "https://upstox.com"
    try:
        df = pd.read_json(gzip.decompress(requests.get(url).content))
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except: return {}

# --- DATA FETCHERS ---
def fetch_upstox(token, key):
    to_date, from_date = datetime.now().strftime('%Y-%m-%d'), (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    url = f"{UPSTOX_BASE}/historical-candle/{key.replace('|', '%7C')}/day/{to_date}/{from_date}"
    try:
        res = requests.get(url, headers=get_headers(token), timeout=15)
        if res.status_code == 200:
            df = pd.DataFrame(res.json()['data']['candles'], columns=["Date","Open","High","Low","Close","Volume","OI"])
            df["Date"] = pd.to_datetime(df["Date"])
            return df.sort_values("Date").set_index("Date").apply(pd.to_numeric)
        return None
    except: return None

def fetch_yahoo(ticker):
    import yfinance as yf
    try:
        df = yf.download(ticker, period='1y', interval='1d', progress=False)
        if not df.empty: df.columns = [c.capitalize() for c in df.columns]
        return df
    except: return None

# --- UI ---
st.sidebar.title("📡 Connection")
source = st.sidebar.selectbox("Source", ["Yahoo Finance", "Upstox"])
token = st.sidebar.text_input("Upstox Token", type="password") if source == "Upstox" else None

is_ready = True if source == "Yahoo Finance" else (token and requests.get(f"{UPSTOX_BASE}/user/profile", headers=get_headers(token)).status_code == 200)

if st.sidebar.button("🔍 Scan Nifty 500") and is_ready:
    mapping, tickers, results = get_mapping(), ns.get_nifty500_with_ns(), []
    pb = st.progress(0)
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS","")
        df = fetch_yahoo(t) if source == "Yahoo Finance" else fetch_upstox(token, mapping.get(symbol))
        if df is not None and len(df) > 50:
            last, prev_h, avg_v = df.iloc[-1], df['High'].rolling(20).max().shift(1).iloc[-1], df['Volume'].rolling(20).mean().shift(1).iloc[-1]
            if last['Close'] > prev_h and last['Volume'] > (avg_v * 1.5):
                results.append({"Ticker": symbol, "Price": round(last['Close'], 2), "Vol_Ratio": round(last['Volume']/avg_v, 2)})
        pb.progress((i+1)/len(tickers))
    pd.DataFrame(results).to_csv("breakout_results.csv", index=False)
    st.rerun()

# --- DISPLAY ---
if os.path.exists("breakout_results.csv"):
    df_res = pd.read_csv("breakout_results.csv")
    if not df_res.empty:
        st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
