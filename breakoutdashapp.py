import streamlit as st
import pandas as pd
import yfinance as yf
import time
import os
from datetime import datetime
from niftystocks import ns

# --- 1. THE SCREENER LOGIC ---
def breakout_screener(df):
    """Calculates technical levels and identifies breakouts."""
    df = df.copy()
    # Resistance & Volume Avg (20-day)
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

    # Conditions
    is_break = (df['Close'] > df['Resist']) & (df['Volume'] > df['Avg_Vol'] * 1.5)
    is_trend = (df['RSI'] > 50) & (df['Close'] > df['SMA_50']) & (df['SMA_50'] > df['SMA_200'])
    
    df['Signal'] = is_break & is_trend
    return df[df['Signal'] == True]

# --- 2. THE SCANNER ENGINE ---
def run_live_scan(ticker_list):
    """Scans provided tickers and updates session stats."""
    found = []
    headers = ["Ticker", "Price", "RSI", "Vol_Ratio", "Scan_Time"]
    processed_count = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticker in enumerate(ticker_list):
        status_text.text(f"Scanning {ticker} ({i+1}/{len(ticker_list)})...")
        try:
            time.sleep(0.4) # Rate limiting to avoid Yahoo Finance blocks
            df = yf.download(ticker, period='1y', interval='1d', progress=False)
            processed_count += 1
            
            # Ensure enough data for 200-day Moving Average
            if len(df) >= 200:
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
    
    # Store results in Session State for the Log
    st.session_state['last_scan_stats'] = {
        "processed": processed_count,
        "found": len(found),
        "time": datetime.now().strftime("%H:%M:%S")
    }
    
    # Always return DataFrame with headers to prevent "No columns to parse" error
    return pd.DataFrame(found, columns=headers)

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Nifty Breakout Tracker", layout="wide")
st.title("🚀 Nifty 500 Breakout Screener")

# Initialize Session State
if 'last_scan_stats' not in st.session_state:
    st.session_state['last_scan_stats'] = None

# Sidebar Controls
st.sidebar.header("Control Panel")
st.sidebar.write("Manual scan targets Nifty 500 stocks.")

if st.sidebar.button('🔍 Run Live Scan Now'):
    with st.spinner("Fetching data from Yahoo Finance..."):
        # For a full scan, use ns.get_nifty500_with_ns()
        # Using first 50 for faster demonstration/testing
        all_tickers = ns.get_nifty500_with_ns()
        live_results = run_live_scan(all_tickers)
        live_results.to_csv("breakout_results.csv", index=False)
        st.rerun()

# --- 4. STATUS LOG SECTION ---
if st.session_state['last_scan_stats']:
    stats = st.session_state['last_scan_stats']
    with st.expander("📊 Scan Status Log", expanded=True):
        col1, col2, col3 = st.columns(3)
        col1.metric("Stocks Processed", stats['processed'])
        col2.metric("Breakouts Found", stats['found'])
        col3.metric("Last Run Time", stats['time'])

# --- 5. DATA DISPLAY ---
CSV_FILE = "breakout_results.csv"

if os.path.exists(CSV_FILE):
    try:
        # Load CSV and handle potential empty file issues
        df = pd.read_csv(CSV_FILE)
        
        if not df.empty:
            st.subheader(f"Latest Detected Breakouts ({len(df)})")
            
            # Display Table with Highlighting on Volume Ratio
            st.dataframe(
                df.style.background_gradient(subset=['Vol_Ratio'], cmap='Greens'),
                use_container_width=True
            )
            
            # Download Button
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv_data,
                file_name=f"breakouts_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("The data file is empty. No stocks currently meet the breakout criteria.")
            
    except pd.errors.EmptyDataError:
        st.error("The data file exists but is empty. Please run a new scan.")
    except Exception as e:
        st.error(f"Error loading dashboard: {e}")
else:
    st.warning("⚠️ No breakout data found. Please run a 'Live Scan' from the sidebar to generate the first report.")

st.divider()
st.caption("Note: This tool uses a 20-day high breakout strategy with RSI and Volume confirmation.")
