import json
import os
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import STATE_FILE, CONSISTENCY_MODE, STORAGE_NODES

st.set_page_config(
    page_title="File Sharing System - Dashboard",
    layout="wide",
)

# auto-refresh every 3 seconds
st_autorefresh(interval=3000, key="dashboard_refresh")

st.title("Distributed File-Sharing Dashboard")


def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


state = load_state()

# --- top row: consistency mode + summary ---
col1, col2, col3 = st.columns(3)
with col1:
    mode_color = "green" if CONSISTENCY_MODE == "strong" else "orange"
    st.metric("Consistency Mode", CONSISTENCY_MODE.upper())
with col2:
    total_files = len(state["metadata"]) if state and "metadata" in state else 0
    st.metric("Total Uploads", total_files)
with col3:
    nodes_up = 0
    if state and "node_health" in state:
        nodes_up = sum(1 for v in state["node_health"].values() if v == "up")
    st.metric("Nodes Online", f"{nodes_up} / {len(STORAGE_NODES)}")

st.divider()

# --- node health ---
st.subheader("Node Health")
if state and "node_health" in state:
    health_cols = st.columns(len(STORAGE_NODES))
    for i, (_, port) in enumerate(STORAGE_NODES):
        status = state["node_health"].get(str(port), "unknown")
        if status == "up":
            indicator = "🟢"
        elif status == "down":
            indicator = "🔴"
        else:
            indicator = "⚪"
        with health_cols[i]:
            st.markdown(f"### {indicator} Node :{port}")
            st.caption(f"Status: {status}")
else:
    st.info("No state data yet. Start the manager and upload a file.")

st.divider()

# --- file metadata table ---
st.subheader("Upload History")
if state and "metadata" in state and len(state["metadata"]) > 0:
    rows = []
    for fid, info in state["metadata"].items():
        node_statuses = info.get("nodes", {})
        row = {
            "ID": fid[:8] + "..." if len(fid) > 8 else fid,
            "Filename": info.get("filename", "?"),
            "Timestamp": info.get("timestamp", "?"),
        }
        for _, port in STORAGE_NODES:
            row[f"Node :{port}"] = node_statuses.get(str(port), "pending")
        rows.append(row)

    st.dataframe(rows, use_container_width=True)
else:
    st.info("No files uploaded yet.")

st.divider()

# --- recent replication log ---
st.subheader("Replication Log (last 20)")
if state and "replication_log" in state and len(state["replication_log"]) > 0:
    recent = list(reversed(state["replication_log"][-20:]))
    log_rows = []
    for entry in recent:
        log_rows.append({
            "Time": entry.get("time", "?"),
            "File": entry.get("filename", "?"),
            "Node": entry.get("node", "?"),
            "Status": entry.get("status", "?"),
        })
    st.dataframe(log_rows, use_container_width=True)
else:
    st.info("No replication events yet.")
