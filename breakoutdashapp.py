import streamlit as st
import pandas as pd

st.set_page_config(page_title="Nifty Breakout Tracker", layout="wide")

st.title("🚀 Breakout Stocks Dashboard")
st.write("Data updates daily after market close (3:30 PM IST)")

try:
    df = pd.read_csv("breakout_results.csv")
    
    # Sidebar Filters
    st.sidebar.header("Filters")
    min_rsi = st.sidebar.slider("Minimum RSI", 50, 80, 50)
    df = df[df['RSI'] >= min_rsi]

    # Display Metrics
    st.metric("Stocks Identified", len(df))
    
    # Data Table
    st.dataframe(df.style.highlight_max(axis=0, subset=['Vol_Ratio']), use_container_width=True)

except FileNotFoundError:
    st.warning("No data found yet. The first scan will run at 3:30 PM IST.")
