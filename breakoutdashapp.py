import requests
import pandas as pd
import gzip
import json
import time
import os
from datetime import datetime, timedelta

# --- Configuration ---
# Use the Analytics Token (1-year validity) from Upstox Developer Apps
# Set this as a Secret in your GitHub Repository
ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
UPSTOX_BASE = "https://api.upstox.com/v2"

def get_complete_mapping():
    """Downloads and parses the BOD Complete Master JSON master."""
    url = "https://upstox.com"
    try:
        response = requests.get(url, stream=True, timeout=30)
        content = gzip.decompress(response.content)
        instruments = json.loads(content)
        # Filter for NSE Equity segment for breakout scanning
        return {item['trading_symbol']: item['instrument_key'] 
                for item in instruments if item.get('segment') == 'NSE_EQ'}
    except Exception as e:
        print(f"Error loading Instrument Master: {e}")
        return {}

def fetch_ohlc(instrument_key):
    """Fetches daily historical candles for the past year."""
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    
    url = f"{UPSTOX_BASE}/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            candles = resp.json()['data']['candles']
            # Upstox order: [timestamp, open, high, low, close, volume, oi]
            df = pd.DataFrame(candles, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'OI'])
            df['Date'] = pd.to_datetime(df['Date'])
            return df.sort_values('Date').set_index('Date')
        return None
    except Exception:
        return None

def scan_market():
    master_map = get_complete_mapping()
    if not master_map: return

    # Example: Scanning a target list (you can replace with Nifty 500 tickers)
    tickers_to_scan = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    results = []

    for symbol in tickers_to_scan:
        key = master_map.get(symbol)
        if not key: continue
        
        df = fetch_ohlc(key)
        if df is not None and len(df) >= 21:
            # Resistance: Max High of previous 20 sessions
            df['Resistance'] = df['High'].rolling(window=20).max().shift(1)
            df['AvgVol'] = df['Volume'].rolling(window=20).mean().shift(1)
            
            latest = df.iloc[-1]
            # Condition: Close > 20d Resistance AND Volume > 1.5x Avg
            if latest['Close'] > latest['Resistance'] and latest['Volume'] > (latest['AvgVol'] * 1.5):
                results.append({
                    "Ticker": symbol,
                    "Price": round(latest['Close'], 2),
                    "Volume_Ratio": round(latest['Volume'] / latest['AvgVol'], 2),
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
        time.sleep(0.1) # Respect standard rate limits

    if results:
        pd.DataFrame(results).to_csv("breakout_results.csv", index=False)
        print(f"Success: Found {len(results)} breakout stocks.")

if __name__ == "__main__":
    scan_market()
