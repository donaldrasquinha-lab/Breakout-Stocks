import streamlit as st
import pandas as pd
import yfinance as yf
import time
import os
from datetime import datetime
from niftystocks import ns

# --- 1. THE SCREENER LOGIC ---
def breakout_screener(df):
    df = df.copy()
    # 20-day Resistance & Volume Average
    df['Resist'] = df['High'].rolling(20).max().shift(1)
    df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
    
    # RSI (14-day)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    # Moving Averages
    df['SMA_50'] = df['Close'].rolling(50).mean()
    df['SMA_200'] = df['Close'].rolling(200).mean()

    # Master Condition: Price > Resistance + High Vol + RSI > 50 + Upward Trend
    is_break = (df['Close'] > df['Resist']) & (df['Volume'] > df['Avg_Vol'] * 1.5)
    is_trend = (df['RSI'] > 50) & (df['Close'] > df['SMA_50']) & (df['SMA_50'] > df['SMA_200'])
    
    df['Signal'] = is_break & is_trend
    return df[df['Signal'] == True]

# --- 2. THE SCANNER ENGINE ---
def run_live_scan(ticker_list):
    found = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticker in enumerate(ticker_list):
        status_text.text(f"Scanning {ticker} ({i+1}/{len(ticker_list)})...")
        try:
            # Rate limiting for Yahoo Finance
            time.sleep(0.5) 
            df = yf.download(ticker, period='1y', interval='1d', progress=False)
            
            if len(df) < 200: continue
            
            results = breakout_screener(df)
            
            if not results.empty:
                latest = results.iloc[-1]
                found.append({
                    "Ticker": ticker,
                    "Price": round(float(latest['Close']), 2),
                    "RSI": round(float(latest['RSI']), 2),
                    "Vol_Ratio": round(float(latest['Volume'] / latest['Avg_Vol']), 2),
                    "Scan_Time": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
        except Exception:
            continue
        progress_bar.progress((i + 1) / len(ticker_list))
    
    status_text.text("✅ Scan Complete!")
    return pd.DataFrame(found)

# --- 3. THE DASHBOARD UI ---
st.set_page_config(page_title="Nifty Breakout Tracker", layout="wide")
st.title("🚀 Nifty 500 Breakout Screener")

# Sidebar Controls
st.sidebar.header("Control Panel")
st.sidebar.info("Scheduled scans run at 3:30 PM IST. Use the button below for a live check.")

if st.sidebar.button('🔍 Run Live Scan Now'):
    # Using Nifty 500 list
    tickers = ns.get_nifty500_with_ns()
    # Speed tip: For testing, use tickers[:50]
    live_results = run_live_scan(tickers)
    live_results.to_csv("breakout_results.csv", index=False)
    st.rerun()

# --- 4. DATA DISPLAY & ERROR HANDLING ---
CSV_FILE = "breakout_results.csv"

if os.path.exists(CSV_FILE):
    try:
        df = pd.read_csv(CSV_FILE)
        
        if not df.empty:
            # Stats
            total_found = len(df)
            st.metric("Total Breakouts Found", total_found)
            
            # Formatting and Display
            st.subheader("Detected Stocks")
            styled_df = df.style.highlight_max(axis=0, subset=['Vol_Ratio'], color='#1d3557')
            st.dataframe(styled_df, use_container_width=True)
            
            # Download link
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results CSV", data=csv_data, file_name="breakouts.csv", mime="text/csv")
        else:
            st.info("No stocks currently meet the breakout criteria.")
            
    except Exception as e:
        st.error(f"Error reading data: {e}")
else:
    st.warning("⚠️ No breakout data found. Please run a 'Live Scan' from the sidebar to generate results.")
