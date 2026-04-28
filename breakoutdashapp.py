import requests
import pandas as pd
import gzip
import json
import time
from datetime import datetime, timedelta

# API Configuration
UPSTOX_BASE = "https://api.upstox.com/v2"
ACCESS_TOKEN = "{your_access_token}" # Or use Analytics Token for long-lived access

def get_complete_instrument_map():
    """Downloads and parses the complete BOD JSON master."""
    url = "https://upstox.com"
    response = requests.get(url, stream=True)
    content = gzip.decompress(response.content)
    instruments = json.loads(content)
    
    # Filter for Cash Equity (NSE and BSE)
    return {f"{item['trading_symbol']}_{item['exchange']}": item['instrument_key'] 
            for item in instruments if item.get('segment') in ['NSE_EQ', 'BSE_EQ']}

def fetch_historical_ohlc(instrument_key):
    """Fetches daily historical candles for the last year."""
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    
    # format: /historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}
    url = f"{UPSTOX_BASE}/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            candles = resp.json()['data']['candles']
            df = pd.DataFrame(candles, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'OI'])
            df['Date'] = pd.to_datetime(df['Date'])
            return df.sort_values('Date').set_index('Date')
        return None
    except Exception as e:
        print(f"Error for {instrument_key}: {e}")
        return None

def scan_for_breakouts():
    master_map = get_complete_instrument_map()
    results = []
    
    # Example: Scanning a list of Nifty 50 tickers from the master map
    target_tickers = ["RELIANCE_NSE", "TCS_NSE", "INFY_NSE"] 
    
    for ticker_id in target_tickers:
        key = master_map.get(ticker_id)
        if not key: continue
        
        df = fetch_historical_ohlc(key)
        if df is not None and len(df) > 20:
            # 20-day High Breakout Logic
            df['Resist'] = df['High'].rolling(20).max().shift(1)
            df['AvgVol'] = df['Volume'].rolling(20).mean().shift(1)
            
            latest = df.iloc[-1]
            if latest['Close'] > latest['Resist'] and latest['Volume'] > (latest['AvgVol'] * 1.5):
                results.append({
                    "Ticker": ticker_id,
                    "Price": round(latest['Close'], 2),
                    "Vol_Ratio": round(latest['Volume'] / latest['AvgVol'], 2)
                })
        time.sleep(0.5) # Rate limit protection
        
    pd.DataFrame(results).to_csv("breakout_results.csv", index=False)

if __name__ == "__main__":
    scan_for_breakouts()
