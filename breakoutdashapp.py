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

# ----------------------------- Page Config ----------------------------- #
st.set_page_config(page_title="Smart Breakout Hub", page_icon="🚀", layout="wide")

UPSTOX_BASE = "https://api.upstox.com/v2"

# ----------------------------- API Helpers ----------------------------- #
def upstox_headers(token: str) -> dict:
    return {
        "Accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {token}",
    }

def verify_token(token: str):
    try:
        resp = requests.get(f"{UPSTOX_BASE}/user/profile", headers=upstox_headers(token), timeout=10)
        return resp.status_code == 200
    except:
        return False

@st.cache_data(ttl=86400)
def get_upstox_master_mapping():
    url = "https://upstox.com"
    try:
        response = requests.get(url, timeout=30)
        content = gzip.decompress(response.content)
        df = pd.read_json(content)
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except:
        return {}

def fetch_historical_upstox(token, instrument_key, days=250):
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    safe_key = instrument_key.replace("|", "%7C")
    url = f"{UPSTOX_BASE}/historical-candle/{safe_key}/day/{to_date}/{from_date}"

    try:
        # Respecting Rate Limits: 50 requests/sec
        time.sleep(0.02) 
        resp = requests.get(url, headers=upstox_headers(token), timeout=15)
        
        if resp.status_code == 429:
            return "RATE_LIMIT_ERROR"
        if resp.status_code != 200:
            return f"ERROR_{resp.status_code}"
            
        data = resp.json().get("data", {}).get("candles", [])
        if not data: return "NO_DATA"
        
        df = pd.DataFrame(data, columns=["Date", "Open", "High", "Low", "Close", "Volume", "OI"])
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").set_index("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Close"])
    except Exception as e:
        return f"EXCEPTION_{str(e)}"

# ----------------------------- Dashboard UI ----------------------------- #
st.sidebar.title("🔐 Authentication")
source = st.sidebar.selectbox("Data Provider", ["Upstox", "Yahoo Finance"])
access_token = st.sidebar.text_input("Access Token", type="password", help="Generate daily after 3:30 AM IST")

is_connected = False
if access_token and source == "Upstox":
    if verify_token(access_token):
        st.sidebar.success("🟢 Connected")
        is_connected = True
    else:
        st.sidebar.error("🔴 Invalid/Expired Token")
elif source == "Yahoo Finance":
    is_connected = True

# ----------------------------- Scanner Logic ----------------------------- #
st.title("📈 Smart Breakout Hub")

if st.sidebar.button("🔍 Start Nifty 500 Scan") and is_connected:
    mapping = get_upstox_master_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    logs = [] # Status Log
    
    # Manual overrides for known symbol changes
    fixes = {"L&TFH.NS": "LTF", "IDFC.NS": "IDFCFIRSTB", "INOXLEISUR.NS": "PVRINOX"}
    
    progress_bar = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = fixes.get(t, t.replace(".NS", ""))
        status.text(f"Scanning {symbol} ({i+1}/{len(tickers)})...")
        
        df = None
        if source == "Upstox":
            key = mapping.get(symbol)
            if key:
                df = fetch_historical_upstox(access_token, key)
                if isinstance(df, str): # Handle logged errors
                    logs.append({"Ticker": symbol, "Status": df})
                    df = None
            else:
                logs.append({"Ticker": symbol, "Status": "MISSING_KEY"})
        else:
            import yfinance as yf
            try:
                # Add headers to avoid Yahoo rate limits
                df = yf.download(t, period='1y', interval='1d', progress=False, timeout=10)
                if not df.empty:
                    df.columns = [c.capitalize() for c in df.columns]
                else: logs.append({"Ticker": symbol, "Status": "YAHOO_NO_DATA"})
            except: logs.append({"Ticker": symbol, "Status": "YAHOO_FAILED"})
            time.sleep(0.5)

        if df is not None and not df.empty and len(df) > 50:
            last = df.iloc[-1]
            prev_high = df['High'].rolling(20).max().shift(1).iloc[-1]
            avg_vol = df['Volume'].rolling(20).mean().shift(1).iloc[-1]
            
            if last['Close'] > prev_high and last['Volume'] > (avg_vol * 1.5):
                results.append({"Ticker": symbol, "Price": round(float(last['Close']), 2), "Vol_Ratio": round(float(last['Volume']/avg_v), 2)})
        
        progress_bar.progress((i + 1) / len(tickers))
    
    status.success(f"Found {len(results)} Breakouts.")
    pd.DataFrame(results).to_csv("breakout_results.csv", index=False)
    pd.DataFrame(logs).to_csv("scan_log.csv", index=False)
    st.rerun()

# ----------------------------- Display & Logging ----------------------------- #
if os.path.exists("breakout_results.csv"):
    df_res = pd.read_csv("breakout_results.csv")
    if not df_res.empty:
        st.subheader("Latest Detected Breakouts")
        st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
    
    if os.path.exists("scan_log.csv"):
        with st.expander("📝 Detailed Scan Log (Failures/Skips)"):
            st.dataframe(pd.read_csv("scan_log.csv"), use_container_width=True)
