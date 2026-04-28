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
st.set_page_config(page_title="Breakout Hub", page_icon="🚀", layout="wide")

UPSTOX_BASE = "https://upstox.com"

# ----------------------------- Helpers & Mapping ----------------------------- #
def get_headers(token):
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Api-Version": "2.0"
    }

@st.cache_data(ttl=86400)
def get_mapping():
    """Downloads official Upstox Master to map Tickers to Keys."""
    url = "https://upstox.com"
    try:
        df = pd.read_json(gzip.decompress(requests.get(url).content))
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except:
        return {}

# ----------------------------- Data Fetchers ----------------------------- #
def fetch_upstox(token, key):
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    url = f"{UPSTOX_BASE}/historical-candle/{key.replace('|', '%7C')}/day/{to_date}/{from_date}"
    try:
        res = requests.get(url, headers=get_headers(token), timeout=15)
        if res.status_code == 200:
            df = pd.DataFrame(res.json()['data']['candles'], columns=["Date","Open","High","Low","Close","Volume","OI"])
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date").set_index("Date")
            return df.apply(pd.to_numeric)
        return None
    except:
        return None

def fetch_yahoo(ticker):
    import yfinance as yf
    try:
        df = yf.download(ticker, period='1y', interval='1d', progress=False)
        if not df.empty:
            df.columns = [c.capitalize() for c in df.columns]
            return df
        return None
    except:
        return None

# ----------------------------- Indicators & Logic ----------------------------- #
def add_indicators(df):
    if df is None or len(df) < 50: return df
    df = df.copy()
    df['Resist'] = df['High'].rolling(20).max().shift(1)
    df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    df['SMA_50'] = df['Close'].rolling(50).mean()
    df['SMA_200'] = df['Close'].rolling(200).mean()
    return df

# ----------------------------- Sidebar & Connectivity ----------------------------- #
st.sidebar.title("📡 Connection Settings")
source = st.sidebar.selectbox("Select Data Source", ["Yahoo Finance", "Upstox"])

is_connected = False
token = None

if source == "Upstox":
    token = st.sidebar.text_input("Upstox Access Token", type="password")
    if token:
        try:
            res = requests.get(f"{UPSTOX_BASE}/user/profile", headers=get_headers(token), timeout=10)
            if res.status_code == 200:
                user = res.json()['data']['user_name']
                st.sidebar.success(f"🟢 Connected: {user}")
                is_connected = True
            else:
                st.sidebar.error("🔴 Token Expired/Invalid")
        except:
            st.sidebar.error("🔴 Connection Error")
else:
    st.sidebar.success("🟢 Connected: Yahoo Finance")
    is_connected = True

# ----------------------------- Main UI ----------------------------- #
st.title("📈 Smart Breakout Hub")
st.markdown("Scan Nifty 500 stocks for 20-day high breakouts with volume surges.")

if st.sidebar.button("🔍 Run Nifty 500 Scan") and is_connected:
    mapping = get_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    
    pb = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status.text(f"Scanning {symbol}...")
        
        df = fetch_yahoo(t) if source == "Yahoo Finance" else fetch_upstox(token, mapping.get(symbol))
        
        if df is not None and len(df) > 50:
            df = add_indicators(df)
            last = df.iloc[-1]
            if last['Close'] > last['Resist'] and last['Volume'] > (last['Avg_Vol'] * 1.5) and last['RSI'] > 50:
                results.append({
                    "Ticker": symbol,
                    "Price": round(float(last['Close']), 2),
                    "RSI": round(float(last['RSI']), 2),
                    "Vol_Ratio": round(float(last['Volume'] / last['Avg_Vol']), 2)
                })
        
        if source == "Yahoo Finance": time.sleep(0.3)
        pb.progress((i + 1) / len(tickers))
    
    status.success(f"✅ Found {len(results)} breakouts!")
    pd.DataFrame(results, columns=["Ticker", "Price", "RSI", "Vol_Ratio"]).to_csv("breakout_results.csv", index=False)
    st.rerun()

# ----------------------------- Results & Charting ----------------------------- #
if os.path.exists("breakout_results.csv"):
    df_res = pd.read_csv("breakout_results.csv")
    if not df_res.empty:
        st.subheader("Latest Detected Breakouts")
        st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
        
        st.divider()
        ticker = st.selectbox("📊 Visual Confirmation (Select Ticker):", df_res['Ticker'].unique())
        
        if ticker and is_connected:
            mapping = get_mapping()
            key = mapping.get(ticker)
            df_chart = fetch_yahoo(ticker + ".NS") if source == "Yahoo Finance" else fetch_upstox(token, key)
            
            if df_chart is not None:
                df_chart = add_indicators(df_chart)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
                fig.add_trace(go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'], name='Price'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['SMA_50'], name='50 SMA', line=dict(color='orange')), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['RSI'], name='RSI', line=dict(color='purple')), row=2, col=1)
                fig.update_layout(height=600, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No breakouts identified in the last scan.")
else:
    st.warning("No data found. Start a scan from the sidebar.")
