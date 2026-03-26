"""
F1 Telemetry Dashboard — Streamlit app powered by FastF1.

A high-performance dashboard for analyzing Formula 1 telemetry data.
Includes head-to-head comparisons, speed-profiled track maps, and 
cumulative time delta analysis.

Version: 2.1 (Full Professional Edition)
"""

from __future__ import annotations

import datetime
import hmac
import os
import warnings
from pathlib import Path
from typing import Optional, Union

import fastf1
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ── Environment & Warnings ──────────────────────────────────────────────────
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── FastF1 Cache Configuration ───────────────────────────────────────────────
# Enable caching to prevent redundant API calls and speed up session loading.
CACHE_DIR = Path("f1_cache")
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

# ── Page Configuration ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 Telemetry Dashboard | Advanced Analysis",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Professional UI Styling (Dark Grey Theme) ────────────────────────────────
# Custom CSS to match the F1 aesthetics with a professional dark grey palette.
st.markdown(
    """
    <style>
    /* Global Styles */
    html, body, [data-testid="stApp"] {
        background-color: #1e1e1e;
        color: #eeeeee;
        font-family: 'Segoe UI', 'Inter', sans-serif;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #121212;
        border-right: 1px solid #333333;
    }
    [data-testid="stSidebar"] label {
        color: #bbbbbb !important;
        font-size: 0.85rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* Metric Card styling */
    [data-testid="metric-container"] {
        background: #262626;
        border: 1px solid #444444;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    [data-testid="metric-container"] label {
        color: #aaaaaa !important;
        font-size: 0.75rem;
        text-transform: uppercase;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #e10600 !important;
        font-size: 1.8rem !important;
        font-weight: 800;
    }

    /* Tabs Styling */
    button[data-baseweb="tab"] {
        color: #999999 !important;
        font-size: 0.9rem;
        font-weight: 600;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #e10600 !important;
        border-bottom: 2px solid #e10600 !important;
    }

    /* Button and Form Styling */
    .stButton > button {
        border-radius: 4px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        border-color: #e10600;
        color: #e10600;
    }
    
    /* Headers */
    h1, h2, h3 {
        font-weight: 800;
        color: #ffffff;
    }
    h1 { letter-spacing: -1px; }

    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #1e1e1e; }
    ::-webkit-scrollbar-thumb { background: #444; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #e10600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Authentication Module ────────────────────────────────────────────────────

def _check_login() -> None:
    """Blocks app execution until a valid user is authenticated via secrets."""
    if st.session_state.get("authenticated"):
        return

    st.markdown("<style>[data-testid='stVerticalBlock'] > div:first-child { max-width: 450px; margin: 10vh auto; }</style>", unsafe_allow_html=True)
    st.title("🏎️ F1 Dashboard Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Access Dashboard", use_container_width=True)

    if submitted:
        try:
            # Note: Add these to your .streamlit/secrets.toml
            valid_user = st.secrets["auth"]["username"]
            valid_pass = st.secrets["auth"]["password"]
            
            if hmac.compare_digest(username, valid_user) and hmac.compare_digest(password, valid_pass):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Invalid credentials.")
        except KeyError:
            st.error("Authentication not configured in secrets.toml.")
            st.stop()

    if not st.session_state.get("authenticated"):
        st.stop()

# Uncomment to enable login:
# _check_login()

# ── Constants & Team Metadata ────────────────────────────────────────────────
TEAM_COLORS: dict[str, str] = {
    "Red Bull Racing": "#3671C6", "Ferrari": "#E8002D", "Mercedes": "#27F4D2",
    "McLaren": "#FF8000", "Aston Martin": "#229971", "Alpine": "#FF87BC",
    "Williams": "#64C4FF", "Racing Bulls": "#6692FF", "Kick Sauber": "#52E252",
    "Haas F1 Team": "#B6BABD", "AlphaTauri": "#5E8FAA", "Alfa Romeo": "#C92D4B",
}

TEAM_LOGOS: dict[str, str] = {
    "Red Bull Racing": "https://upload.wikimedia.org/wikipedia/en/thumb/a/ae/Red_Bull_Racing_logo.svg/320px-Red_Bull_Racing_logo.svg.png",
    "Ferrari": "https://upload.wikimedia.org/wikipedia/en/thumb/d/d2/Scuderia_Ferrari_Logo.svg/320px-Scuderia_Ferrari_Logo.svg.png",
    "Mercedes": "https://upload.wikimedia.org/wikipedia/en/thumb/f/fb/Mercedes_AMG_Petronas_F1_Logo.svg/320px-Mercedes_AMG_Petronas_F1_Logo.svg.png",
    "McLaren": "https://upload.wikimedia.org/wikipedia/en/thumb/6/6b/McLaren_Racing_logo.svg/320px-McLaren_Racing_logo.svg.png",
    "Aston Martin": "https://upload.wikimedia.org/wikipedia/en/thumb/9/9f/Aston_Martin_F1_Logo.svg/320px-Aston_Martin_F1_Logo.svg.png",
    "Alpine": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/72/Alpine_F1_Team_Logo.svg/320px-Alpine_F1_Team_Logo.svg.png",
    "Williams": "https://upload.wikimedia.org/wikipedia/en/thumb/f/f3/Williams_Racing_logo.svg/320px-Williams_Racing_logo.svg.png",
    "Racing Bulls": "https://upload.wikimedia.org/wikipedia/en/thumb/4/4e/Visa_Cash_App_RB_Formula_One_Team_logo.svg/320px-Visa_Cash_App_RB_Formula_One_Team_logo.svg.png",
    "Kick Sauber": "https://upload.wikimedia.org/wikipedia/en/thumb/4/44/Stake_F1_Team_Kick_Sauber_logo.svg/320px-Stake_F1_Team_Kick_Sauber_logo.svg.png",
    "Haas F1 Team": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8d/Haas_F1_Team_logo_2018.svg/320px-Haas_F1_Team_logo_2018.svg.png",
}

# ── Plotly Theme Definitions ────────────────────────────────────────────────
PLOTLY_DARK_THEME = dict(
    paper_bgcolor="#1e1e1e",
    plot_bgcolor="#1e1e1e",
    font=dict(color="#dddddd", family="Segoe UI, Inter, sans-serif", size=12),
    xaxis=dict(gridcolor="#333333", zeroline=False, linecolor="#444444"),
    yaxis=dict(gridcolor="#333333", zeroline=False, linecolor="#444444"),
)

# ── Helper Functions ─────────────────────────────────────────────────────────

def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Converts a hex color code to an RGBA string for Plotly compatibility."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c*2 for c in hex_color])
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"

def _safe_color(team: str, fallback: str = "#e10600") -> str:
    return TEAM_COLORS.get(team, fallback)

@st.cache_data(show_spinner=False)
def load_session(year: int, event: str, session_type: str) -> fastf1.core.Session:
    """Loads and caches F1 session data."""
    session = fastf1.get_session(year, event, session_type)
    session.load(telemetry=True, weather=False, messages=False)
    return session

@st.cache_data(show_spinner=False)
def get_event_names(year: int) -> list[str]:
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    return schedule["EventName"].tolist()

def format_lap_time(td) -> str:
    if pd.isna(td): return "N/A"
    total_s = td.total_seconds() if hasattr(td, 'total_seconds') else float(td)
    minutes = int(total_s // 60)
    seconds = total_s % 60
    return f"{minutes}:{seconds:06.3f}"

def delta_str(a, b) -> str:
    try:
        diff = (a - b).total_seconds()
        return f"{'+' if diff >= 0 else ''}{diff:.3f}s"
    except: return "N/A"

def get_team_info(session, driver_abbr: str):
    try:
        info = session.get_driver(driver_abbr)
        return info.get("TeamName", "Unknown"), info.get("FullName", driver_abbr)
    except: return "Unknown", driver_abbr

# ── Track Mapping Logic ──────────────────────────────────────────────────────

def build_track_map(lap_tel: pd.DataFrame, color: str, title: str) -> go.Figure:
    """Generates a GPS-based track map colored by speed."""
    if lap_tel is None or lap_tel.empty or "X" not in lap_tel.columns:
        fig = go.Figure().update_layout(title="No GPS Data", **PLOTLY_DARK_THEME)
        return fig

    x, y, speed = lap_tel["X"].values, lap_tel["Y"].values, lap_tel["Speed"].values
    
    # Dynamic speed normalization (prevents flat colors)
    s_min, s_max = speed.min(), speed.max()
    
    fig = go.Figure()
    # Path shadow
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#111", width=10), hoverinfo="skip"))
    
    # Segments for speed coloring
    for i in range(0, len(x) - 1, 2):  # Step by 2 for performance
        norm = (speed[i] - s_min) / (s_max - s_min + 1e-6)
        r = int(255 * norm)
        g = int(255 * (1 - norm))
        fig.add_trace(go.Scatter(
            x=x[i:i+2], y=y[i:i+2], mode="lines",
            line=dict(color=f"rgb({r},{g},100)", width=5),
            hovertemplate=f"Speed: {speed[i]:.0f} km/h<extra></extra>",
            showlegend=False
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        margin=dict(l=10, r=10, t=40, b=10),
        height=400,
        **PLOTLY_DARK_THEME
    )
    return fig

# ── Telemetry Multi-Chart ────────────────────────────────────────────────────

def build_telemetry_figure(tel1, tel2, label1, label2, color1, color2, channels):
    """Creates stacked telemetry subplots with dynamic delta calculation."""
    show_delta = tel2 is not None
    rows = (2 if show_delta else 0) + len(channels)
    
    row_heights = ([0.05, 0.2] if show_delta else []) + [1.0] * len(channels)
    titles = (["Dominance", "Cumulative Delta"] if show_delta else []) + [c for c in channels]
    
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, 
                        row_heights=row_heights, subplot_titles=titles, vertical_spacing=0.03)

    dist1 = tel1["Distance"].values
    
    if show_delta:
        dist2 = tel2["Distance"].values
        s1 = tel1["Speed"].values
        s2_interp = np.interp(dist1, dist2, tel2["Speed"].values)
        
        # 1. Dominance Strip (Who is faster where?)
        faster = np.where(s1 > s2_interp, 1, 0)
        fig.add_trace(go.Scatter(x=dist1, y=faster, fill="tozeroy", mode="none", 
                                 fillcolor=hex_to_rgba(color1, 0.4), name=f"{label1} Faster"), row=1, col=1)
        fig.add_trace(go.Scatter(x=dist1, y=1-faster, fill="tozeroy", mode="none", 
                                 fillcolor=hex_to_rgba(color2, 0.4), name=f"{label2} Faster"), row=1, col=1)

        # 2. Cumulative Delta (Distance-synced)
        # Fix: Using integrated time difference to avoid 'drift'
        dt = (1/np.maximum(s1, 1) - 1/np.maximum(s2_interp, 1)) * 3.6
        delta = np.cumsum(dt * np.diff(dist1, prepend=dist1[0]))
        fig.add_trace(go.Scatter(x=dist1, y=delta, line=dict(color="#ffffff", width=2), name="Delta (s)"), row=2, col=1)

    # 3. Channels
    for i, ch in enumerate(channels):
        curr_row = i + (3 if show_delta else 1)
        
        # Handle missing channels like DRS
        if ch not in tel1.columns: continue
        
        y1 = tel1[ch].values
        if ch == "Throttle": y1 = np.clip(y1 * 100 if y1.max() <= 1.1 else y1, 0, 100)
        
        fig.add_trace(go.Scatter(x=dist1, y=y1, line=dict(color=color1, width=2), name=label1, showlegend=(i==0)), row=curr_row, col=1)
        
        if show_delta and ch in tel2.columns:
            y2 = tel2[ch].values
            if ch == "Throttle": y2 = np.clip(y2 * 100 if y2.max() <= 1.1 else y2, 0, 100)
            fig.add_trace(go.Scatter(x=dist2, y=y2, line=dict(color=color2, width=1.5, dash="dot"), name=label2, showlegend=(i==0)), row=curr_row, col=1)

    fig.update_layout(height=250 * len(channels) + 200, hovermode="x unified", **PLOTLY_DARK_THEME)
    fig.update_xaxes(title_text="Distance (m)", row=rows, col=1)
    return fig

# ── Sidebar UI ───────────────────────────────────────────────────────────────

def sidebar_controls():
    st.sidebar.markdown("<h1 style='color:#e10600; font-size: 28px;'>🏎️ F1 ENGINE</h1>", unsafe_allow_html=True)
    st.sidebar.divider()
    
    year = st.sidebar.selectbox("Season", list(range(datetime.datetime.now().year, 2018, -1)))
    
    with st.sidebar:
        with st.spinner("Fetching Schedule..."):
            events = get_event_names(year)
    
    event = st.sidebar.selectbox("Grand Prix", events)
    session_label = st.sidebar.selectbox("Session", ["Race", "Qualifying", "FP3", "FP2", "FP1", "Sprint"])
    session_map = {"Race": "R", "Qualifying": "Q", "FP1": "FP1", "FP2": "FP2", "FP3": "FP3", "Sprint": "S"}
    
    load = st.sidebar.button("LOAD DATA", use_container_width=True, type="primary")
    
    return {"year": year, "event": event, "type": session_map[session_label], "label": session_label, "load": load}

# ── Main Application ─────────────────────────────────────────────────────────

def main():
    # ── State Management ──
    if "loaded_params" not in st.session_state: st.session_state.loaded_params = None
    if "lap1" not in st.session_state: st.session_state.lap1 = None
    if "lap2" not in st.session_state: st.session_state.lap2 = None

    ctrl = sidebar_controls()
    if ctrl["load"]:
        st.session_state.loaded_params = ctrl
        # Reset laps on new session load
        st.session_state.lap1 = None
        st.session_state.lap2 = None

    if not st.session_state.loaded_params:
        st.info("👈 Select a session in the sidebar and click **LOAD DATA** to begin analysis.")
        return

    params = st.session_state.loaded_params
    with st.spinner(f"Synchronizing {params['year']} {params['event']}..."):
        try:
            session = load_session(params['year'], params['event'], params['type'])
        except Exception as e:
            st.error(f"Data Connection Error: {e}")
            return

    drivers = sorted(session.laps["Driver"].unique())

    # ── Selection Header ──
    st.markdown(f"### {params['year']} {params['event']} — {params['label']}")
    
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        # Pre-select LEC (Leclerc) as requested
        default_idx = drivers.index("LEC") if "LEC" in drivers else 0
        drv1 = st.selectbox("Primary Driver", drivers, index=default_idx)
        laps1 = session.laps.pick_drivers(drv1).pick_quicklaps()
        
        # Fastest button logic
        if st.button(f"⚡ Fastest {drv1}"):
            st.session_state.lap1 = int(laps1.pick_fastest()["LapNumber"])
        
        lap1_num = st.selectbox("Lap Selection", laps1["LapNumber"].astype(int).tolist(), 
                                key="lap1_select", index=0 if st.session_state.lap1 is None else 0)
        # Logic to sync selectbox with button
        if st.session_state.lap1: lap1_num = st.session_state.lap1

    with col2:
        compare_on = st.checkbox("Compare with another lap", value=True) # Checked by default
        if compare_on:
            # Pre-select HAM (Hamilton) as requested
            default_idx2 = drivers.index("HAM") if "HAM" in drivers else (1 if len(drivers)>1 else 0)
            drv2 = st.selectbox("Comparison Driver", drivers, index=default_idx2)
            laps2 = session.laps.pick_drivers(drv2).pick_quicklaps()
            
            if st.button(f"🏆 Fastest {drv2}"):
                st.session_state.lap2 = int(laps2.pick_fastest()["LapNumber"])
            
            lap2_num = st.selectbox("Lap Selection", laps2["LapNumber"].astype(int).tolist(), key="lap2_select")
            if st.session_state.lap2: lap2_num = st.session_state.lap2
        else:
            drv2, lap2_num = None, None

    # ── Data Processing ──
    l1_data = laps1[laps1["LapNumber"] == lap1_num].iloc[0]
    tel1 = l1_data.get_telemetry().add_distance()
    team1, full1 = get_team_info(session, drv1)
    color1 = _safe_color(team1)

    tel2, color2, label2 = None, "#ffffff", None
    if compare_on:
        l2_data = laps2[laps2["LapNumber"] == lap2_num].iloc[0]
        tel2 = l2_data.get_telemetry().add_distance()
        team2, full2 = get_team_info(session, drv2)
        color2 = _safe_color(team2)
        label2 = f"{drv2} (Lap {lap2_num})"

    # ── Display ──
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{drv1} Lap Time", format_lap_time(l1_data["LapTime"]))
    if compare_on:
        m2.metric(f"{drv2} Lap Time", format_lap_time(l2_data["LapTime"]), 
                  delta=delta_str(l2_data["LapTime"], l1_data["LapTime"]), delta_color="inverse")
    m3.metric("Tires", f"{l1_data.get('Compound', 'N/A')} ({int(l1_data.get('TyreLife', 0))}L)")
    
    # ── Logo Strip ──
    st.write("")
    l_col1, l_col2, _ = st.columns([1, 1, 4])
    for i, t in enumerate([team1, team2] if compare_on else [team1]):
        url = TEAM_LOGOS.get(t)
        if url:
            # Fix: Added styles to ensure logos load and look consistent
            (l_col1 if i==0 else l_col2).markdown(f'<img src="{url}" width="120">', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📊 Telemetry Analysis", "🗺️ Track Performance", "📋 Data Table"])
    
    with tab1:
        channels = st.multiselect("Select Channels", ["Speed", "Throttle", "Brake", "nGear", "RPM", "DRS"], 
                                  default=["Speed", "Throttle", "Brake"])
        fig_tel = build_telemetry_figure(tel1, tel2, f"{drv1} (L{lap1_num})", label2, color1, color2, channels)
        st.plotly_chart(fig_tel, use_container_width=True)

    with tab2:
        c_map1, c_map2 = st.columns(2)
        with c_map1:
            st.plotly_chart(build_track_map(tel1, color1, f"{drv1} Speed Profile"), use_container_width=True)
        with c_map2:
            if compare_on:
                st.plotly_chart(build_track_map(tel2, color2, f"{drv2} Speed Profile"), use_container_width=True)

    with tab3:
        st.dataframe(laps1[["LapNumber", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time", "Compound", "TyreLife"]], use_container_width=True)

    st.divider()
    st.markdown("<p style='text-align:center; color:#666;'>Data sourced from FastF1 API. F1 is a trademark of Formula One Licensing BV.</p>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
