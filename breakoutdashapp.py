import streamlit as st
import pandas as pd
import requests
import time
import os
import gzip
from datetime import datetime, timedelta
import plotly.graph_objects as go
from niftystocks import ns

# ----------------------------- Page Config ----------------------------- #
st.set_page_config(page_title="Breakout Hub", page_icon="🚀", layout="wide")
UPSTOX_BASE = "https://upstox.com"

# ----------------------------- Helpers & Mapping ----------------------------- #
def get_v2_headers(token):
    """Mandatory headers for Upstox V2 API."""
    return {
        "Accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {token}"
    }

@st.cache_data(ttl=86400)
def get_mapping():
    """Downloads official Upstox Master to map NSE Tickers to Keys."""
    url = "https://upstox.com"
    try:
        response = requests.get(url, timeout=20)
        content = gzip.decompress(response.content)
        df = pd.read_json(content)
        # Filter for Cash Market (Equity) segment
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except Exception as e:
        st.error(f"Mapping Error: {e}")
        return {}

# ----------------------------- Data Fetchers ----------------------------- #
def fetch_upstox(token, key):
    """Fetches historical OHLC data from Upstox."""
    if not key: return None
    
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    
    # URL encode the instrument key (e.g. | to %7C)
    safe_key = key.replace('|', '%7C')
    url = f"{UPSTOX_BASE}/historical-candle/{safe_key}/day/{to_date}/{from_date}"
    
    try:
        res = requests.get(url, headers=get_v2_headers(token), timeout=25)
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
    """Fetches historical OHLC data from Yahoo Finance."""
    import yfinance as yf
    try:
        df = yf.download(ticker, period='1y', interval='1d', progress=False)
        if not df.empty:
            df.columns = [c.capitalize() for c in df.columns]
            return df
        return None
    except:
        return None

# ----------------------------- Sidebar & Connectivity ----------------------------- #
st.sidebar.title("📡 Connection Status")
source = st.sidebar.selectbox("Data Provider", ["Yahoo Finance", "Upstox"])

is_connected = False
token = ""

if source == "Upstox":
    token = st.sidebar.text_input("Access Token", type="password", help="Generate fresh daily after 3:30 AM IST")
    if token:
        try:
            # Pings Profile endpoint to verify connection
            res = requests.get(f"{UPSTOX_BASE}/user/profile", headers=get_v2_headers(token), timeout=10)
            if res.status_code == 200:
                user = res.json().get('data', {}).get('user_name', 'User')
                st.sidebar.success(f"🟢 Connected: {user}")
                is_connected = True
            elif res.status_code == 401:
                st.sidebar.error("🔴 Token Expired (Generated before 3:30 AM IST)")
            else:
                st.sidebar.error(f"🔴 Connection Failed: {res.status_code}")
        except:
            st.sidebar.error("🔴 Network/Timeout Error")
else:
    st.sidebar.success("🟢 Connected: Yahoo Finance (Free)")
    is_connected = True

# ----------------------------- Main Dashboard ----------------------------- #
st.title("📈 Smart Breakout Hub")
st.markdown("Identifies Nifty 500 stocks breaking 20-day high resistance with >1.5x volume surge.")

if st.sidebar.button("🔍 Run Nifty 500 Scan") and is_connected:
    mapping = get_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    
    pb = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status.text(f"Scanning {symbol} ({i+1}/{len(tickers)})...")
        
        df = None
        if source == "Upstox":
            # SAFETY FIX: Ensure key exists before passing to fetcher
            key = mapping.get(symbol)
            if key:
                df = fetch_upstox(token, key)
            else:
                continue # Skip if ticker not in Upstox list
        else:
            df = fetch_yahoo(t)
            time.sleep(0.3) # Rate limit for Yahoo
        
        # Screener Logic
        if df is not None and not df.empty and len(df) > 50:
            df['Resist'] = df['High'].rolling(20).max().shift(1)
            df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
            
            last = df.iloc[-1]
            if last['Close'] > last['Resist'] and last['Volume'] > (last['Avg_Vol'] * 1.5):
                results.append({
                    "Ticker": symbol, 
                    "Price": round(float(last['Close']), 2), 
                    "Vol_Ratio": round(float(last['Volume'] / last['Avg_Vol']), 2)
                })
        
        pb.progress((i + 1) / len(tickers))
    
    status.success(f"✅ Scan Finished! Found {len(results)} breakouts.")
    pd.DataFrame(results, columns=["Ticker", "Price", "Vol_Ratio"]).to_csv("breakout_results.csv", index=False)
    st.rerun()

# ----------------------------- Display Results ----------------------------- #
if os.path.exists("breakout_results.csv"):
    try:
        df_res = pd.read_csv("breakout_results.csv")
        if not df_res.empty:
            st.subheader("Latest Detected Breakouts")
            st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
            st.download_button("📥 Export Results as CSV", df_res.to_csv(index=False), "breakouts.csv")
        else:
            st.info("No breakout stocks detected in the latest scan.")
    except:
        st.error("Error reading data file. Try running a new scan.")
else:
    st.warning("No data found. Select a source and click 'Run Nifty 500 Scan' to begin.")
