import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import os
import gzip
from datetime import datetime, timedelta
import plotly.graph_objects as go
from niftystocks import ns
import yfinance as yf

# ----------------------------- Page Config ----------------------------- #
st.set_page_config(page_title="Multi-Source Breakout Hub", page_icon="🚀", layout="wide")

UPSTOX_BASE = "https://api.upstox.com/v2"
FILE_YAHOO = "breakout_yahoo_results.csv"
FILE_UPSTOX = "breakout_upstox_results.csv"

# ----------------------------- Helpers ----------------------------- #
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
    url = "https://api.upstox.com/v2"
    try:
        response = requests.get(url, timeout=30)
        content = gzip.decompress(response.content)
        df = pd.read_json(content)
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except:
        return {}

# ----------------------------- Data Fetchers ----------------------------- #
def fetch_upstox_v2(token, key):
    if not key: return None 
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
    df['Resist'] = df['High'].rolling(20).max().shift(1)
    df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
    
    last = df.iloc[-1]
    try:
        close = float(last['Close'])
        resist = float(last['Resist'])
        vol = float(last['Volume'])
        avg_vol = float(last['Avg_Vol'])
        
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

# Determine which file to use as "memory"
current_file = FILE_YAHOO if source == "Yahoo Finance" else FILE_UPSTOX

is_connected = False
token = ""

if source == "Upstox":
    token = st.sidebar.text_input("Upstox Access Token", type="password")
    if token:
        if verify_token(token):
            st.sidebar.success("🟢 Connected to Upstox V2")
            is_connected = True
        else:
            st.sidebar.error("🔴 Token Expired/Invalid")
else:
    st.sidebar.success("🟢 Connected: Yahoo Finance")
    is_connected = True

# ----------------------------- Dashboard ----------------------------- #
st.title(f"📈 {source} Breakout Hub")
st.caption(f"Currently viewing data from: {current_file}")

if st.sidebar.button("🔍 Run Nifty 500 Scan") and is_connected:
    mapping = get_upstox_master_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    
    fixes = {"L&TFH.NS": "LTF", "IDFC.NS": "IDFCFIRSTB", "INOXLEISUR.NS": "PVRINOX"}
    
    pb = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = fixes.get(t, t.replace(".NS", ""))
        status.text(f"Scanning {symbol}...")
        
        df = None
        if source == "Yahoo Finance":
            df = fetch_yahoo(t)
            time.sleep(0.3)
        else:
            key = mapping.get(symbol)
            if key:
                df = fetch_upstox_v2(token, key)
            else:
                continue 
        
        signal = identify_breakout(df)
        if signal:
            signal['Ticker'] = symbol
            results.append(signal)
            
        pb.progress((i + 1) / len(tickers))
    
    status.success(f"✅ Found {len(results)} breakouts!")
    # Save to the specific provider memory
    pd.DataFrame(results, columns=["Ticker", "Price", "Vol_Ratio"]).to_csv(current_file, index=False)
    st.rerun()

# ----------------------------- Display Memory ----------------------------- #
import requests
import pandas as pd
import os
from datetime import datetime, timedelta

# Configuration
UPSTOX_BASE = "https://api.upstox.com/v2"
# Securely access token from environment variables
ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN") 

def fetch_upstox_data(instrument_key):
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    url = f"{UPSTOX_BASE}/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            candles = response.json().get('data', {}).get('candles', [])
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching {instrument_key}: {e}")
        return pd.DataFrame()

# Example: Pulling for a specific list
tickers = ["NSE_EQ|INE002A01018", "NSE_EQ|INE467B01029"] # Reliance, TCS
all_data = []

for ticker in tickers:
    data = fetch_upstox_data(ticker)
    if not data.empty:
        data['Ticker'] = ticker
        all_data.append(data)

if all_data:
    final_df = pd.concat(all_data)
    final_df.to_csv("upstox_stock_data.csv", index=False)
