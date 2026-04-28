import streamlit as st
import pandas as pd
import requests
import time
import os
import gzip
from datetime import datetime, timedelta
import plotly.graph_objects as go
from niftystocks import ns

# --- 1. CONFIG ---
st.set_page_config(page_title="Breakout Hub", page_icon="🚀", layout="wide")
UPSTOX_BASE = "https://api.upstox.com/v2"

# --- 2. ROBUST HEADERS ---
def get_v2_headers(token):
    return {
        "Accept": "application/json",
        "Api-Version": "2.0",  # MANDATORY for V2
        "Authorization": f"Bearer {token}"
    }

@st.cache_data(ttl=86400)
def get_mapping():
    url = "https://upstox.com"
    try:
        df = pd.read_json(gzip.decompress(requests.get(url, timeout=20).content))
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except:
        return {}

# --- 3. DATA FETCHERS ---
def fetch_upstox(token, key):
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    # Key must be URL encoded (e.g. | becomes %7C)
    safe_key = key.replace('|', '%7C')
    url = f"{UPSTOX_BASE}/historical-candle/{safe_key}/day/{to_date}/{from_date}"
    try:
        res = requests.get(url, headers=get_v2_headers(token), timeout=30)
        if res.status_code == 200:
            df = pd.DataFrame(res.json()['data']['candles'], columns=["Date","Open","High","Low","Close","Volume","OI"])
            df["Date"] = pd.to_datetime(df["Date"])
            return df.sort_values("Date").set_index("Date").apply(pd.to_numeric)
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

# --- 4. SIDEBAR & STATUS ---
st.sidebar.title("📡 Connection Settings")
source = st.sidebar.selectbox("Select Data Source", ["Yahoo Finance", "Upstox"])

is_connected = False
token = ""

if source == "Upstox":
    token = st.sidebar.text_input("Upstox Access Token", type="password")
    if token:
        try:
            # Check connection via the Profile endpoint
            profile_res = requests.get(f"{UPSTOX_BASE}/user/profile", headers=get_v2_headers(token), timeout=30)
            if profile_res.status_code == 200:
                user_name = profile_res.json()['data']['user_name']
                st.sidebar.success(f"🟢 Connected: {user_name}")
                is_connected = True
            elif profile_res.status_code == 401:
                st.sidebar.error("🔴 Token Expired (Generated before 3:30 AM IST?)")
            else:
                st.sidebar.error(f"🔴 Connection Failed: {profile_res.status_code}")
        except requests.exceptions.Timeout:
            st.sidebar.error("🔴 Network Timeout: Check your Internet")
        except:
            st.sidebar.error("🔴 Connection Error")
else:
    st.sidebar.success("🟢 Connected: Yahoo Finance")
    is_connected = True

# --- 5. MAIN DASHBOARD ---
st.title("📈 Smart Breakout Hub")
st.markdown("Scan Nifty 500 stocks for 20-day high breakouts with volume surges.")

if st.sidebar.button("🔍 Run Nifty 500 Scan") and is_connected:
    mapping = get_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []
    
    pb = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(tickers):
        symbol = t.replace(".NS", "")
        status_text.text(f"Scanning {symbol}...")
        
        df = fetch_yahoo(t) if source == "Yahoo Finance" else fetch_upstox(token, mapping.get(symbol))
        
        if df is not None and len(df) > 50:
            last = df.iloc[-1]
            prev_high = df['High'].rolling(20).max().shift(1).iloc[-1]
            avg_vol = df['Volume'].rolling(20).mean().shift(1).iloc[-1]
            
            if last['Close'] > prev_high and last['Volume'] > (avg_vol * 1.5):
                results.append({
                    "Ticker": symbol,
                    "Price": round(float(last['Close']), 2),
                    "Vol_Ratio": round(float(last['Volume'] / avg_vol), 2)
                })
        
        if source == "Yahoo Finance": time.sleep(0.3)
        pb.progress((i + 1) / len(tickers))
    
    status_text.success(f"✅ Found {len(results)} breakouts!")
    pd.DataFrame(results, columns=["Ticker", "Price", "Vol_Ratio"]).to_csv("breakout_results.csv", index=False)
    st.rerun()

# --- 6. DISPLAY ---
CSV_FILE = "breakout_results.csv"
if os.path.exists(CSV_FILE):
    df_res = pd.read_csv(CSV_FILE)
    if not df_res.empty:
        st.subheader("Latest Detected Breakouts")
        st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
        st.download_button("📥 Export Results as CSV", df_res.to_csv(index=False), "breakouts.csv")
    else:
        st.info("No breakout stocks found in the last scan.")
else:
    st.warning("No data found. Select a source and click 'Run Nifty 500 Scan'.")
