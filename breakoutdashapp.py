import streamlit as st
import pandas as pd
import yfinance as yf
import time
from niftystocks import ns

# 1. Breakout Logic
def breakout_screener(df):
    df = df.copy()
    df['Resist'] = df['High'].rolling(20).max().shift(1)
    df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    df['SMA_50'] = df['Close'].rolling(50).mean()
    df['SMA_200'] = df['Close'].rolling(200).mean()

    is_break = (df['Close'] > df['Resist']) & (df['Volume'] > df['Avg_Vol'] * 1.5)
    is_trend = (df['RSI'] > 50) & (df['Close'] > df['SMA_50']) & (df['SMA_50'] > df['SMA_200'])
    
    df['Signal'] = is_break & is_trend
    return df[df['Signal'] == True]

# 2. Live Scanning Function
def run_live_scan(ticker_list):
    found = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticker in enumerate(ticker_list):
        status_text.text(f"Scanning {ticker} ({i+1}/{len(ticker_list)})...")
        try:
            time.sleep(0.2) # Faster for live feedback
            df = yf.download(ticker, period='1y', interval='1d', progress=False)
            results = breakout_screener(df)
            
            if not results.empty:
                latest = results.iloc[-1]
                found.append({
                    "Ticker": ticker,
                    "Price": round(float(latest['Close']), 2),
                    "RSI": round(float(latest['RSI']), 2),
                    "Vol_Ratio": round(float(latest['Volume'] / latest['Avg_Vol']), 2)
                })
        except: continue
        progress_bar.progress((i + 1) / len(ticker_list))
    
    status_text.text("✅ Scan Complete!")
    return pd.DataFrame(found)

# 3. UI Layout
st.set_page_config(page_title="Nifty Breakout Tracker", layout="wide")
st.title("🚀 Real-Time Breakout Screener")

# Sidebar for controls
st.sidebar.header("Controls")
if st.sidebar.button('🔍 Run Live Scan Now'):
    # Get Nifty 500 tickers (Limited to first 50 for speed in live UI)
    tickers = ns.get_nifty500_with_ns()[:50] 
    live_df = run_live_scan(tickers)
    live_df.to_csv("breakout_results.csv", index=False)
    st.sidebar.success(f"Found {len(live_df)} stocks!")

# Display Data from CSV (either from GitHub or Live Scan)
try:
    df = pd.read_csv("breakout_results.csv")
    st.subheader("Latest Detected Breakouts")
    st.dataframe(df.style.highlight_max(axis=0, subset=['Vol_Ratio']), use_container_width=True)
    
    # Download Button for the current results
    st.download_button("📥 Download Results as CSV", 
                       data=df.to_csv(index=False), 
                       file_name="breakouts.csv", 
                       mime="text/csv")
except FileNotFoundError:
    st.info("No data available. Click 'Run Live Scan' or wait for the scheduled automation.")
