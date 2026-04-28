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

# Ensure base URL is correct for V2
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
    """Fetches historical OHLC data from Upstox V2."""
    if not key: return None
    
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    
    # URL encode the instrument key (e.g. | to %7C)
    safe_key = key.replace('|', '%7C')
    # Correct V2 historical candle endpoint
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
            # Correct V2 Profile endpoint to avoid 404
            profile_url = f"{UPSTOX_BASE}/user/profile"
            res = requests.get(profile_url, headers=get_v2_headers(token), timeout=10)
            
            if res.status_code == 200:
                user_data = res.json().get('data', {})
                user_name = user_data.get('user_name', 'Connected User')
                st.sidebar.success(f"🟢 Connected: {user_name}")
                is_connected = True
            elif res.status_code == 401:
                st.sidebar.error("🔴 Token Expired (Daily 3:30 AM IST reset)")
            elif res.status_code == 404:
                st.sidebar.error("🔴 404 Error: Incorrect API Endpoint")
            else:
                st.sidebar.error(f"🔴 Connection Failed: {res.status_code}")
        except Exception:
            st.sidebar.error("🔴 Network/Timeout Error")
else:
    st.sidebar.success("🟢 Connected: Yahoo Finance")
    is_connected = True

# ----------------------------- Main Dashboard ----------------------------- #
st.title("📈 Smart Breakout Hub")
st.markdown("Automated scan for 20-day high breakouts with volume surge.")

if st.sidebar.button("🔍 Run Nifty 500 Scan") and is_connected:
    mapping = get_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    
    pb = st.progress(0)
    status_label = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status_label.text(f"Scanning {symbol} ({i+1}/{len(tickers)})...")
        
        df = None
        if source == "Upstox":
            # Safety Check: Skip if ticker is missing from Upstox master
            key = mapping.get(symbol)
            if key:
                df = fetch_upstox(token, key)
            else:
                continue 
        else:
            df = fetch_yahoo(t)
            time.sleep(0.3) # Rate limit for Yahoo
        
        # Breakout Logic
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
    
    status_label.success(f"✅ Found {len(results)} breakouts!")
    pd.DataFrame(results, columns=["Ticker", "Price", "Vol_Ratio"]).to_csv("breakout_results.csv", index=False)
    st.rerun()

# ----------------------------- Display Results ----------------------------- #
if os.path.exists("breakout_results.csv"):
    try:
        df_res = pd.read_csv("breakout_results.csv")
        if not df_res.empty:
            st.subheader("Latest Detected Breakouts")
            st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
            st.download_button("📥 Download CSV", df_res.to_csv(index=False), "breakouts.csv")
        else:
            st.info("No breakout stocks detected in the last scan.")
    except:
        st.error("Error reading data. Please run a new scan.")
else:
    st.warning("No data found. Start a scan from the sidebar.")
