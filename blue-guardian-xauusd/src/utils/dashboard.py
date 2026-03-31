# Placeholder for dashboard utility
# src/utils/dashboard.py
"""
Streamlit monitoring dashboard.
Run with: streamlit run src/utils/dashboard.py
"""
import json
import glob
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(
    page_title="Blue Guardian Dashboard",
    page_icon="🏅",
    layout="wide"
)

st.title("🏅 Blue Guardian XAUUSD — Intelligence Dashboard")

# Load recent simulations
sim_files = sorted(glob.glob("data/processed/sim_*.json"), reverse=True)[:30]
sims = []
for f in sim_files:
    try:
        with open(f) as fp:
            sims.append(json.load(fp))
    except Exception:
        pass

if not sims:
    st.warning("No simulation data found. Run morning_run.py first.")
    st.stop()

# --- Top Metrics Row ---
col1, col2, col3, col4 = st.columns(4)

latest = sims[0]
consensus = latest.get("consensus", {})

with col1:
    signal = consensus.get("final_signal", "N/A")
    color = "🟢" if signal == "LONG" else "🔴" if signal == "SHORT" else "⚪"
    st.metric("Latest Signal", f"{color} {signal}")

with col2:
    st.metric("Consensus Score", f"{consensus.get('weighted_conviction', 0):.3f}")

with col3:
    st.metric("Quality Score", f"{consensus.get('quality_score', 0):.3f}")

with col4:
    st.metric("Agent Votes", 
              f"L:{consensus.get('long_votes', 0)} / "
              f"S:{consensus.get('short_votes', 0)} / "
              f"N:{consensus.get('neutral_votes', 0)}")

# --- Consensus History Chart ---
st.subheader("📊 Signal History")
history_data = []
for sim in reversed(sims):
    c = sim.get("consensus", {})
    history_data.append({
        "date": sim.get("timestamp", "")[:10],
        "long_pct": c.get("long_pct", 0),
        "short_pct": c.get("short_pct", 0),
        "quality_score": c.get("quality_score", 0),
        "signal": c.get("final_signal", "NO_TRADE")
    })

df = pd.DataFrame(history_data)
if not df.empty:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["date"], y=df["long_pct"], name="Long %", marker_color="green"))
    fig.add_trace(go.Bar(x=df["date"], y=df["short_pct"], name="Short %", marker_color="red"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["quality_score"], 
                             name="Quality Score", yaxis="y2", line=dict(color="orange")))
    fig.update_layout(
        barmode="group",
        yaxis2=dict(overlaying="y", side="right", range=[0, 1]),
        title="Consensus History"
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Today's Top Rationales ---
st.subheader("🧠 Today's Agent Rationales")
col1, col2 = st.columns(2)
with col1:
    st.write("**Top LONG Arguments:**")
    for r in consensus.get("top_long_rationale", ["None"]):
        st.write(f"• {r[:150]}")
with col2:
    st.write("**Top SHORT Arguments:**")
    for r in consensus.get("top_short_rationale", ["None"]):
        st.write(f"• {r[:150]}")

# --- Trade Log ---
st.subheader("📋 Trade Log")
trade_log_file = Path("data/processed/trade_log.jsonl")
if trade_log_file.exists():
    trades = []
    with open(trade_log_file) as f:
        for line in f:
            try:
                trades.append(json.loads(line))
            except Exception:
                pass
    if trades:
        df_trades = pd.DataFrame(trades)
        st.dataframe(df_trades, use_container_width=True)