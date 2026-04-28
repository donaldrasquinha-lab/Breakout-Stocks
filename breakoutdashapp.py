import streamlit as st
import pandas as pd
import yfinance as yf
import time, os, requests, gzip
from datetime import datetime, timedelta
from niftystocks import ns

# --- 1. INSTRUMENT MAPPING ---
@st.cache_data(ttl=86400)
def get_upstox_mapping():
    url = "https://upstox.com"
    try:
        response = requests.get(url)
        content = gzip.decompress(response.content)
        df = pd.read_json(content)
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except: return {}

# --- 2. DATA FETCHERS ---
def fetch_yahoo_data(ticker):
    df = yf.download(ticker, period='1y', interval='1d', progress=False)
    if not df.empty: df.columns = [c.lower() for c in df.columns]
    return df

def fetch_upstox_data(instrument_key, access_token):
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    # Use the official V2 historical endpoint
    url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
    headers = {
        'Accept': 'application/json',
        'Api-Version': '2.0',
        'Authorization': f'Bearer {access_token}'
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            candles = res.json()['data']['candles']
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            return df.iloc[::-1] # Oldest to newest
        return pd.DataFrame()
    except: return pd.DataFrame()

# --- 3. SCREENER LOGIC ---
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
    df['signal'] = (df['close'] > df['resist']) & (df['volume'] > df['avg_vol'] * 1.5) & (df['rsi'] > 50) & (df['close'] > df['sma_50']) & (df['sma_50'] > df['sma_200'])
    return df[df['signal'] == True]

# --- 4. DASHBOARD UI ---
st.set_page_config(page_title="Stock Breakout Hub", layout="wide")
st.title("🚀 Smart Stock Breakout Dashboard")

st.sidebar.header("📡 Connection Settings")
source = st.sidebar.selectbox("Data Provider", ["Yahoo Finance", "Upstox"])

token = ""
is_connected = False
mapping = {}

if source == "Upstox":
    token = st.sidebar.text_input("Access Token", type="password")
    if token:
        try:
            # Use profile endpoint to verify connection
            val_url = "https://upstox.com"
            res = requests.get(val_url, headers={'Authorization': f'Bearer {token}', 'Api-Version': '2.0'}, timeout=10)
            if res.status_code == 200:
                st.sidebar.success(f"🟢 Connected: {res.json()['data']['user_name']}")
                is_connected = True
                mapping = get_upstox_mapping()
            elif res.status_code == 401:
                st.sidebar.error("🔴 Token Expired (Daily at 3:30 AM IST)")
            else:
                st.sidebar.error(f"🔴 Error: {res.status_code}")
        except: st.sidebar.error("🔴 Network/Timeout Error")
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
        df = fetch_yahoo_data(t) if source == "Yahoo Finance" else fetch_upstox_data(mapping.get(symbol), token)
        if not df.empty:
            res = breakout_screener(df)
            if not res.empty:
                latest = res.iloc[-1]
                found.append({"Ticker": symbol, "Price": round(float(latest['close']), 2), "RSI": round(float(latest['rsi']), 2), "Vol_Ratio": round(float(latest['volume']/latest['avg_vol']), 2)})
        if source == "Yahoo Finance": time.sleep(0.4) # Rate limit
        progress_bar.progress((i + 1) / len(tickers))

    pd.DataFrame(found, columns=["Ticker", "Price", "RSI", "Vol_Ratio"]).to_csv("breakout_results.csv", index=False)
    st.rerun()

# --- 6. DISPLAY RESULTS ---
if os.path.exists("breakout_results.csv"):
    df_res = pd.read_csv("breakout_results.csv")
    if not df_res.empty:
        st.subheader(f"Detected Breakouts ({len(df_res)})")
        st.dataframe(df_res.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'), use_container_width=True)
        st.download_button("📥 Export CSV", df_res.to_csv(index=False), "breakouts.csv")
    else: st.info("No breakout stocks found today.")
else: st.warning("No data found. Start a scan from the sidebar.")
