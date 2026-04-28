import streamlit as st
import pandas as pd
import yfinance as yf
import time
import os
import requests
import gzip
from datetime import datetime
from niftystocks import ns

# --- 1. INSTRUMENT MAPPING SYSTEM ---
@st.cache_data(ttl=86400) # Cache for 24 hours
def get_upstox_mapping():
    """Downloads and filters the Upstox NSE Instrument Master list."""
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    try:
        response = requests.get(url)
        content = gzip.decompress(response.content)
        df = pd.read_json(content)
        # Filter only for Equity (EQ) segment to speed up lookups
        df = df[df['segment'] == 'NSE_EQ']
        # Create a mapping of trading_symbol (e.g. RELIANCE) to instrument_key
        return dict(zip(df['trading_symbol'], df['instrument_key']))
    except Exception as e:
        st.error(f"Failed to load Upstox mapping: {e}")
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
    from_date = (datetime.now() - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
    url = f"https://upstox.com{instrument_key}/day/{to_date}/{from_date}"
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {access_token}'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            candles = res.json()['data']['candles']
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            return df.iloc[::-1] # Newest to oldest -> Oldest to newest
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
    df['signal'] = (df['close'] > df['resist']) & (df['volume'] > df['avg_vol'] * 1.5) & (df['rsi'] > 50) & (df['close'] > df['sma_50'])
    return df[df['signal'] == True]

# --- 4. DASHBOARD UI ---
st.set_page_config(page_title="Stock Breakout Hub", layout="wide")
st.title("🚀 Smart Breakout Screener")

st.sidebar.header("📡 Connection Settings")
source = st.sidebar.selectbox("Data Provider", ["Yahoo Finance", "Upstox"])

token = ""
is_connected = False
mapping = {}

if source == "Upstox":
    token = st.sidebar.text_input("Upstox Access Token", type="password")
    if token:
        try:
            res = requests.get("https://upstox.com", headers={'Authorization': f'Bearer {token}'})
            if res.status_code == 200:
                st.sidebar.success(f"🟢 Connected: {res.json()['data']['user_name']}")
                is_connected = True
                mapping = get_upstox_mapping() # Load keys only after connection
            else: st.sidebar.error("🔴 Invalid Token")
        except: st.sidebar.error("🔴 Connection Error")
else:
    st.sidebar.success("🟢 Connected: Yahoo Finance")
    is_connected = True

# --- 5. SCANNER EXECUTION ---
if st.sidebar.button('🔍 Run Live Scan Now') and is_connected:
    tickers = ns.get_nifty500_with_ns()
    found = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status_text.text(f"Scanning {symbol}...")
        
        if source == "Yahoo Finance":
            df = fetch_yahoo_data(t)
            time.sleep(0.3)
        else:
            key = mapping.get(symbol)
            df = fetch_upstox_data(key, token) if key else pd.DataFrame()
        
        if not df.empty:
            res = breakout_screener(df)
            if not res.empty:
                latest = res.iloc[-1]
                found.append({"Ticker": symbol, "Price": round(float(latest['close']), 2), "RSI": round(float(latest['rsi']), 2), "Vol_Ratio": round(float(latest['volume']/latest['avg_vol']), 2)})
        
        progress_bar.progress((i + 1) / len(tickers))

    pd.DataFrame(found, columns=["Ticker", "Price", "RSI", "Vol_Ratio"]).to_csv("breakout_results.csv", index=False)
    st.rerun()

# --- 6. DISPLAY ---
if os.path.exists("breakout_results.csv"):
    df = pd.read_csv("breakout_results.csv")
    if not df.empty:
        st.subheader(f"Breakouts Detected ({len(df)})")
        st.dataframe(df.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
    else: st.info("No breakouts found in the latest scan.")
else: st.warning("No data found. Click 'Run Live Scan' to begin.")
