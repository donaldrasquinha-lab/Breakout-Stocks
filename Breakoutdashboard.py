import streamlit as st
import pandas as pd

st.set_page_config(page_title="Stock Breakout Dashboard", layout="wide")
st.title("🚀 Live Breakout Screener")

try:
    df = pd.read_csv("breakout_results.csv")
    
    # Summary Metrics
    col1, col2 = st.columns(2)
    col1.metric("Total Breakouts Found", len(df))
    
    # Interactive Table
    st.subheader("Detected Stocks")
    st.dataframe(df, use_container_width=True)

    # Optional: Highlight high-volume surges
    if "Vol_Ratio" in df.columns:
        st.subheader("Top Volume Surges")
        st.bar_chart(df.set_index("Ticker")["Vol_Ratio"])

except FileNotFoundError:
    st.error("No breakout data found. Run the scanner first!")
