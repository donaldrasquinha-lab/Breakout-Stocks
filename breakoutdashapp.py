import requests
import pandas as pd
import gzip
import json
import time
import os
from datetime import datetime, timedelta
from niftystocks import ns

UPSTOX_BASE = "https://upstox.com"

def get_v2_headers(token):
    return {"Accept": "application/json", "Api-Version": "2.0", "Authorization": f"Bearer {token}"}

def get_mapping():
    url = "https://upstox.com"
    try:
        df = pd.read_json(gzip.decompress(requests.get(url).content))
        return dict(zip(df[df['segment'] == 'NSE_EQ']['trading_symbol'], df['instrument_key']))
    except: return {}

def fetch_upstox(token, key):
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    url = f"{UPSTOX_BASE}/historical-candle/{key.replace('|', '%7C')}/day/{to_date}/{from_date}"
    try:
        res = requests.get(url, headers=get_v2_headers(token), timeout=15)
        if res.status_code == 200:
            df = pd.DataFrame(res.json()['data']['candles'], columns=["Date","Open","High","Low","Close","Volume","OI"])
            return df.iloc[::-1].set_index(pd.to_datetime(df["Date"])).apply(pd.to_numeric)
    except: return None

def run_automated_scan():
    token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token: return
    
    mapping = get_mapping()
    tickers = ns.get_nifty500_with_ns()
    results = []

    for t in tickers:
        symbol = t.replace(".NS", "")
        key = mapping.get(symbol)
        if key:
            df = fetch_upstox(token, key)
            if df is not None and len(df) > 50:
                df['Resist'] = df['High'].rolling(20).max().shift(1)
                df['Avg_Vol'] = df['Volume'].rolling(20).mean().shift(1)
                last = df.iloc[-1]
                if float(last['Close']) > float(last['Resist']) and float(last['Volume']) > (float(last['Avg_Vol']) * 1.5):
                    results.append({"Ticker": symbol, "Price": round(float(last['Close']), 2), "Vol_Ratio": round(float(last['Volume']/last['Avg_Vol']), 2)})
    
    pd.DataFrame(results).to_csv("breakout_results.csv", index=False)

if __name__ == "__main__":
    run_automated_scan()
