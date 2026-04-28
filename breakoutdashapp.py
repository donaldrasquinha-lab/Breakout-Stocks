import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import os
import gzip
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from niftystocks import ns
import yfinance as yf

# ----------------------------- Page Config ----------------------------- #
st.set_page_config(page_title="Upstox V2 Breakout Hub", page_icon="🚀", layout="wide")

# Updated to the official V2 Base URL
UPSTOX_BASE = "https://api.upstox.com/v2"

# ----------------------------- Upstox API Helpers ----------------------------- #
def upstox_headers(token: str) -> dict:
    """Standard V2 Headers."""
    return {
        "Accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {token}",
    }

def verify_token(token: str):
    """Pings the V2 profile endpoint."""
    try:
        resp = requests.get(f"{UPSTOX_BASE}/user/profile", headers=upstox_headers(token), timeout=10)
        return resp.status_code == 200
    except:
        return False

@st.cache_data(ttl=86400)
def get_upstox_master_mapping():
    """Downloads official Upstox Master for V2 Instrument Keys."""
    url = "https://upstox.com"
    try:
        response = requests.get(url, timeout=30)
        content = gzip.decompress(response.content)
        df = pd.read_json(content)
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except:
        return {}

# ----------------------------- Data Fetchers ----------------------------- #
def fetch_upstox_v2(token, key):
    """V2 Historical Candle Endpoint."""
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    safe_key = key.replace('|', '%7C')
    url = f"{UPSTOX_BASE}/historical-candle/{safe_key}/day/{to_date}/{from_date}"
    try:
        res = requests.get(url, headers=upstox_headers(token), timeout=15)
        if res.status_code == 200:
            data = res.json().get('data', {}).get('candles', [])
            df = pd.DataFrame(data, columns=["Date","Open","High","Low","Close","Volume","OI"])
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date").set_index("Date")
            return df.apply(pd.to_numeric)
        return None
    except:
        return None

def fetch_yahoo(ticker):
    try:
        df = yf.download(ticker, period='1y', interval='1d', progress=False)
        if not df.empty:
            df.columns = [c.capitalize() for c in df.columns]
            return df
        return None
    except:
        return None

# ----------------------------- Indicators & Logic ----------------------------- #
def identify_breakout(df):
    if df is None or len(df) < 50: return None
    df = df.copy()
    
    # Calculate Indicators
    df['Resist'] = df['High'].rolling(20).max().shift(1)
    df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
    
    last = df.iloc[-1]
    try:
        # Convert to float to avoid Series comparison errors
        close = float(last['Close'])
        resist = float(last['Resist'])
        vol = float(last['Volume'])
        avg_vol = float(last['Avg_Vol'])
        
        # Breakout Condition
        if close > resist and vol > (avg_vol * 1.5):
            return {
                "Price": round(close, 2),
                "Vol_Ratio": round(vol / avg_vol, 2)
            }
    except:
        pass
    return None

# ----------------------------- Sidebar ----------------------------- #
st.sidebar.title("📡 Connection Settings")
source = st.sidebar.selectbox("Select Data Provider", ["Yahoo Finance", "Upstox"])

is_connected = False
token = ""

if source == "Upstox":
    token = st.sidebar.text_input("Upstox Access Token", type="password")
    if token:
        if verify_token(token):
            st.sidebar.success("🟢 Connected to Upstox V2")
            is_connected = True
        else:
            st.sidebar.error("🔴 Token Expired or Invalid")
else:
    st.sidebar.success("🟢 Connected: Yahoo Finance")
    is_connected = True

# ----------------------------- Dashboard ----------------------------- #
st.title("📈 Smart Breakout Hub")

if st.sidebar.button("🔍 Run Nifty 500 Scan") and is_connected:
    mapping = get_upstox_master_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    
    pb = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status.text(f"Scanning {symbol}...")
        
        df = fetch_yahoo(t) if source == "Yahoo Finance" else fetch_upstox_v2(token, mapping.get(symbol))
        
        signal = identify_breakout(df)
        if signal:
            signal['Ticker'] = symbol
            results.append(signal)
            
        pb.progress((i + 1) / len(tickers))
        if source == "Yahoo Finance": time.sleep(0.3)
    
    pd.DataFrame(results, columns=["Ticker", "Price", "Vol_Ratio"]).to_csv("breakout_results.csv", index=False)
    st.rerun()

# ----------------------------- Display ----------------------------- #
if os.path.exists("breakout_results.csv"):
    df_res = pd.read_csv("breakout_results.csv")
    if not df_res.empty:
        st.subheader("Latest Detected Breakouts")
        st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
