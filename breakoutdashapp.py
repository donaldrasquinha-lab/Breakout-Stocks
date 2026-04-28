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
st.set_page_config(page_title="Upstox Breakout Hub", page_icon="🚀", layout="wide")

UPSTOX_BASE = "https://api.upstox.com/v2"

# ----------------------------- Upstox API Helpers ----------------------------- #
def upstox_headers(token: str) -> dict:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

def verify_token(token: str):
    """Ping profile endpoint to validate token."""
    try:
        resp = requests.get(f"{UPSTOX_BASE}/user/profile", headers=upstox_headers(token), timeout=10)
        return resp.status_code == 200
    except:
        return False

@st.cache_data(ttl=86400)
def get_upstox_master_mapping():
    """Downloads official Upstox Master to map NSE Tickers to Instrument Keys."""
    url = "https://api.upstox.com/v2"
    try:
        response = requests.get(url)
        content = gzip.decompress(response.content)
        df = pd.read_json(content)
        df = df[df['segment'] == 'NSE_EQ']
        return dict(zip(df['trading_symbol'], df['instrument_key']))
    except:
        return {}

def fetch_historical_upstox(token, instrument_key, days=250):
    """Robust OHLC Fetcher from Upstox V2."""
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    safe_key = instrument_key.replace("|", "%7C")
    url = f"{UPSTOX_BASE}/historical-candle/{safe_key}/day/{to_date}/{from_date}"

    try:
        resp = requests.get(url, headers=upstox_headers(token), timeout=15)
        if resp.status_code != 200: return None
        
        data = resp.json()
        candles = data.get("data", {}).get("candles", [])
        if not candles: return None

        # Upstox returns: [timestamp, open, high, low, close, volume, oi]
        df = pd.DataFrame(candles, columns=["Date", "Open", "High", "Low", "Close", "Volume", "OI"])
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").set_index("Date")
        
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Close"])
    except:
        return None

# ----------------------------- Indicators & Logic ----------------------------- #
def add_indicators(df):
    if df is None or len(df) < 50: return df
    df = df.copy()
    # Resistance & Volume
    df['Resist'] = df['High'].rolling(20).max().shift(1)
    df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    # Moving Averages
    df['SMA_50'] = df['Close'].rolling(50).mean()
    df['SMA_200'] = df['Close'].rolling(200).mean()
    return df

def identify_breakout(df):
    df = add_indicators(df)
    if df is None or len(df) < 50: return None
    
    latest = df.iloc[-1]
    # Strategy: Price > 20-day High, Volume > 1.5x Avg, Bullish Momentum
    is_break = (latest['Close'] > latest['Resist']) & (latest['Volume'] > latest['Avg_Vol'] * 1.5)
    is_trend = (latest['RSI'] > 50) & (latest['Close'] > latest['SMA_50']) & (latest['SMA_50'] > latest['SMA_200'])
    
    if is_break and is_trend:
        return {
            "Price": round(latest['Close'], 2),
            "RSI": round(latest['RSI'], 2),
            "Vol_Ratio": round(latest['Volume'] / latest['Avg_Vol'], 2)
        }
    return None

# ----------------------------- Charting Engine ----------------------------- #
def plot_breakout_chart(df, ticker):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                       vertical_spacing=0.05, row_heights=[0.7, 0.3])
    # Candlestick
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                low=df['Low'], close=df['Close'], name='Price'), row=1, col=1)
    # SMAs
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], name='50 SMA', line=dict(color='orange')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_200'], name='200 SMA', line=dict(color='blue')), row=1, col=1)
    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI', line=dict(color='purple')), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(title=f"{ticker} Technical View", height=600, xaxis_rangeslider_visible=False)
    return fig

# ----------------------------- Sidebar & Logic ----------------------------- #
st.sidebar.title("🔑 Upstox Access")
access_token = st.sidebar.text_input("Daily Access Token", type="password")

is_connected = False
if access_token:
    if verify_token(access_token):
        st.sidebar.success("🟢 Connected")
        is_connected = True
    else:
        st.sidebar.error("🔴 Token Expired/Invalid")

# ----------------------------- Main Dashboard ----------------------------- #
st.title("📈 Smart Breakout Screener")

if st.sidebar.button("🔍 Run Nifty 500 Scan") and is_connected:
    mapping = get_upstox_master_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    
    progress_bar = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status.text(f"Scanning {symbol}...")
        key = mapping.get(symbol)
        if key:
            df = fetch_historical_upstox(access_token, key)
            signal = identify_breakout(df)
            if signal:
                signal['Ticker'] = symbol
                results.append(signal)
        progress_bar.progress((i + 1) / len(tickers))
    
    status.success(f"Scan Complete! Found {len(results)} breakouts.")
    pd.DataFrame(results, columns=["Ticker", "Price", "RSI", "Vol_Ratio"]).to_csv("breakout_results.csv", index=False)

# ----------------------------- Display Results ----------------------------- #
if os.path.exists("breakout_results.csv"):
    df_res = pd.read_csv("breakout_results.csv")
    if not df_res.empty:
        st.subheader("Latest Detected Breakouts")
        st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)

        st.divider()
        ticker_to_chart = st.selectbox("📊 Select Stock for Visual Confirmation:", df_res['Ticker'].unique())
        
        if ticker_to_chart and is_connected:
            mapping = get_upstox_master_mapping()
            key = mapping.get(ticker_to_chart)
            df_chart = fetch_historical_upstox(access_token, key)
            df_chart = add_indicators(df_chart)
            st.plotly_chart(plot_breakout_chart(df_chart, ticker_to_chart), use_container_width=True)
    else:
        st.info("No breakouts identified in the latest scan.")
else:
    st.warning("Enter token and run a scan to see data.")
