import streamlit as st
import pandas as pd
import yfinance as yf
import time
import os
import requests
import gzip
from datetime import datetime, timedelta
from niftystocks import ns

# --- 1. INSTRUMENT MAPPING SYSTEM ---
@st.cache_data(ttl=86400)
def get_upstox_mapping():
    """Downloads Upstox NSE Instrument Master for faster lookups."""
    url = "https://upstox.com"
    try:
        response = requests.get(url)
        content = gzip.decompress(response.content)
        df = pd.read_json(content)
        df = df[df['segment'] == 'NSE_EQ']
        return dict(zip(df['trading_symbol'], df['instrument_key']))
    except Exception as e:
        st.error(f"Mapping Error: {e}")
        return {}

# --- 2. DATA SOURCE WRAPPERS ---
def fetch_yahoo_data(ticker):
    try:
        df = yf.download(ticker, period='1y', interval='1d', progress=False)
        if df.empty: return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        return df
    except: return pd.DataFrame()

def fetch_upstox_data(instrument_key, access_token):
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {access_token}'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            candles = res.json()['data']['candles']
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            return df.iloc[::-1]
        return pd.DataFrame()
    except: return pd.DataFrame()

# --- 3. THE SCREENER LOGIC ---
def breakout_screener(df):
    if len(df) < 50: return pd.DataFrame()
    df = df.copy()
    df['resist'] = df['high'].rolling(20).max().shift(1)
    df['avg_vol'] = df['volume'].rolling(20).mean().shift(1)
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    df['sma_50'] = df['close'].rolling(50).mean()
    df['sma_200'] = df['close'].rolling(200).mean()
    
    # Master Signal: Resistance Breakout + High Volume + RSI Momentum + Bullish Trend
    is_break = (df['close'] > df['resist']) & (df['volume'] > df['avg_vol'] * 1.5)
    is_momentum = (df['rsi'] > 50) & (df['close'] > df['sma_50']) & (df['sma_50'] > df['sma_200'])
    
    df['signal'] = is_break & is_momentum
    return df[df['signal'] == True]

# --- 4. DASHBOARD UI ---
st.set_page_config(page_title="Stock Breakout Screener", layout="wide")
st.title("🚀 Smart Stock Breakout Dashboard")

if 'last_scan_stats' not in st.session_state:
    st.session_state['last_scan_stats'] = None

# Sidebar: Connectivity
st.sidebar.header("📡 Connection Settings")
source = st.sidebar.selectbox("Data Provider", ["Yahoo Finance", "Upstox"])

token = ""
is_connected = False
mapping = {}

if source == "Upstox":
    token = st.sidebar.text_input("Access Token", type="password", help="Generated from Upstox Developer Portal")
    if token:
        try:
            val_url = "https://upstox.com"
            res = requests.get(val_url, headers={'Authorization': f'Bearer {token}'}, timeout=10)
            if res.status_code == 200:
                st.sidebar.success(f"🟢 Connected: {res.json()['data']['user_name']}")
                is_connected = True
                mapping = get_upstox_mapping()
            else: st.sidebar.error("🔴 Token Expired or Invalid")
        except: st.sidebar.error("🔴 Connection Failed")
else:
    st.sidebar.success("🟢 Connected: Yahoo Finance")
    is_connected = True

# --- 5. SCANNER EXECUTION ---
if st.sidebar.button('🔍 Run Live Scan Now') and is_connected:
    tickers = ns.get_nifty500_with_ns() # Scans all Nifty 500
    found = []
    headers = ["Ticker", "Price", "RSI", "Vol_Ratio", "Scan_Time"]
    processed = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status_text.text(f"Scanning {symbol}...")
        
        df = fetch_yahoo_data(t) if source == "Yahoo Finance" else fetch_upstox_data(mapping.get(symbol), token)
        
        if not df.empty:
            processed += 1
            res = breakout_screener(df)
            if not res.empty:
                latest = res.iloc[-1]
                found.append({
                    "Ticker": symbol, "Price": round(float(latest['close']), 2),
                    "RSI": round(float(latest['rsi']), 2), "Vol_Ratio": round(float(latest['volume']/latest['avg_vol']), 2),
                    "Scan_Time": datetime.now().strftime("%H:%M")
                })
        
        if source == "Yahoo Finance": time.sleep(0.4) # Rate limit
        progress_bar.progress((i + 1) / len(tickers))

    status_text.text("✅ Scan Complete!")
    st.session_state['last_scan_stats'] = {"processed": processed, "found": len(found), "time": datetime.now().strftime("%H:%M:%S")}
    pd.DataFrame(found, columns=headers).to_csv("breakout_results.csv", index=False)
    st.rerun()

# --- 6. DISPLAY RESULTS ---
if st.session_state['last_scan_stats']:
    stats = st.session_state['last_scan_stats']
    st.metric("Breakouts Identified", stats['found'], f"Checked {stats['processed']} stocks")

CSV_FILE = "breakout_results.csv"
if os.path.exists(CSV_FILE):
    df_res = pd.read_csv(CSV_FILE)
    if not df_res.empty:
        st.subheader("Latest Detected Breakouts")
        st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
        st.download_button("📥 Export CSV", df_res.to_csv(index=False), "breakouts.csv")
    else: st.info("No breakouts met the criteria in the last scan.")
else: st.warning("No data found. Start a scan from the sidebar.")
