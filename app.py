"""
F1 Telemetry Dashboard — Streamlit app powered by FastF1.

Displays lap-by-lap telemetry (speed, throttle, brake, gear, RPM, DRS,
delta time) for any driver/session, with an optional head-to-head
comparison and a speed-coloured track map.
"""

from __future__ import annotations

import datetime
import hmac
import os
import warnings
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

# ── FastF1 cache ────────────────────────────────────────────────────────────
CACHE_DIR = Path("f1_cache")
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 Telemetry Dashboard",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS — dark professional theme ────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── global ── */
    html, body, [data-testid="stApp"] {
        background-color: #0d0d0d;
        color: #e8e8e8;
        font-family: 'Segoe UI', 'Inter', sans-serif;
    }
    /* ── sidebar ── */
    [data-testid="stSidebar"] {
        background-color: #111111;
        border-right: 1px solid #222;
    }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stSlider label {
        color: #cccccc !important;
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    /* ── selectbox / input ── */
    .stSelectbox > div > div {
        background-color: #1a1a1a !important;
        color: #e8e8e8 !important;
        border: 1px solid #333 !important;
        border-radius: 4px;
    }
    /* ── metric cards ── */
    [data-testid="metric-container"] {
        background: #161616;
        border: 1px solid #2a2a2a;
        border-radius: 6px;
        padding: 12px 16px;
    }
    [data-testid="metric-container"] label {
        color: #888 !important;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #e10600 !important;
        font-size: 1.6rem !important;
        font-weight: 700;
    }
    [data-testid="metric-container"] [data-testid="stMetricDelta"] {
        font-size: 0.85rem !important;
    }
    /* ── headers ── */
    h1 { color: #e10600 !important; letter-spacing: -0.02em; }
    h2, h3 { color: #e8e8e8 !important; }
    /* ── divider ── */
    hr { border-color: #2a2a2a; }
    /* ── plotly chart background ── */
    .js-plotly-plot .plotly { background: transparent !important; }
    /* ── spinner ── */
    [data-testid="stSpinner"] { color: #e10600; }
    /* ── tabs ── */
    button[data-baseweb="tab"] {
        color: #888 !important;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #e10600 !important;
        border-bottom: 2px solid #e10600 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Authentication ───────────────────────────────────────────────────────────

def _check_login() -> None:
    """Show a login form and block the app until valid credentials are entered.

    Credentials are read from Streamlit secrets:

        [auth]
        username = "your_username"
        password = "your_password"

    See `.streamlit/secrets.toml` for the template.
    """
    if st.session_state.get("authenticated"):
        return

    st.markdown(
        """
        <style>
        /* centre the login card */
        [data-testid="stVerticalBlock"] > div:first-child {
            max-width: 420px;
            margin: 8vh auto 0 auto;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("🏎️ F1 Telemetry Dashboard")
    st.subheader("Please log in to continue")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        try:
            valid_user = st.secrets["auth"]["username"]
            valid_pass = st.secrets["auth"]["password"]
        except KeyError:
            st.error(
                "App credentials are not configured. "
                "Add an `[auth]` section to `.streamlit/secrets.toml`."
            )
            st.stop()

        if hmac.compare_digest(username, valid_user) and hmac.compare_digest(password, valid_pass):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid username or password.")

    if not st.session_state.get("authenticated"):
        st.stop()


_check_login()

# ── Team colours & logo URLs ─────────────────────────────────────────────────
TEAM_COLORS: dict[str, str] = {
    "Red Bull Racing": "#3671C6",
    "Ferrari": "#E8002D",
    "Mercedes": "#27F4D2",
    "McLaren": "#FF8000",
    "Aston Martin": "#229971",
    "Alpine": "#FF87BC",
    "Williams": "#64C4FF",
    "Racing Bulls": "#6692FF",
    "Kick Sauber": "#52E252",
    "Haas F1 Team": "#B6BABD",
    # legacy names used by FastF1
    "AlphaTauri": "#5E8FAA",
    "Alpha Tauri": "#5E8FAA",
    "Alfa Romeo": "#C92D4B",
    "Alfa Romeo Racing": "#C92D4B",
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
    "AlphaTauri": "https://upload.wikimedia.org/wikipedia/en/thumb/0/0d/Scuderia_AlphaTauri_logo.svg/320px-Scuderia_AlphaTauri_logo.svg.png",
    "Alpha Tauri": "https://upload.wikimedia.org/wikipedia/en/thumb/0/0d/Scuderia_AlphaTauri_logo.svg/320px-Scuderia_AlphaTauri_logo.svg.png",
    "Alfa Romeo": "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Alfa_Romeo_Racing_logo.svg/320px-Alfa_Romeo_Racing_logo.svg.png",
    "Alfa Romeo Racing": "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Alfa_Romeo_Racing_logo.svg/320px-Alfa_Romeo_Racing_logo.svg.png",
}

PLOTLY_DARK = dict(
    paper_bgcolor="#0d0d0d",
    plot_bgcolor="#111111",
    font=dict(color="#cccccc", family="Segoe UI, Inter, sans-serif", size=11),
    xaxis=dict(
        gridcolor="#1e1e1e",
        linecolor="#333",
        tickcolor="#333",
        showgrid=True,
        zeroline=False,
    ),
    yaxis=dict(
        gridcolor="#1e1e1e",
        linecolor="#333",
        tickcolor="#333",
        showgrid=True,
        zeroline=False,
    ),
)

# Delta track map: segment colours for losing / gaining time
DELTA_LOSING_COLOR = "#dc2626"   # red  — driver 1 takes more time here
DELTA_GAINING_COLOR = "#16a34a"  # green — driver 1 takes less time here

# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_color(team: str, fallback: str = "#e10600") -> str:
    return TEAM_COLORS.get(team, fallback)


@st.cache_data(show_spinner=False)
def load_session(year: int, event: str, session_type: str) -> fastf1.core.Session:
    session = fastf1.get_session(year, event, session_type)
    session.load(telemetry=True, weather=False, messages=False)
    return session


@st.cache_data(show_spinner=False)
def get_event_names(year: int) -> list[str]:
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    return schedule["EventName"].tolist()


def format_lap_time(td) -> str:
    """Format a timedelta or float (seconds) as M:SS.mmm."""
    if pd.isna(td):
        return "N/A"
    if isinstance(td, (int, float)):
        total_s = float(td)
    else:
        total_s = td.total_seconds()
    minutes = int(total_s // 60)
    seconds = total_s % 60
    return f"{minutes}:{seconds:06.3f}"


def delta_str(a, b) -> str:
    """Return signed delta string like +0.204s."""
    try:
        if isinstance(a, (int, float)):
            diff = float(a) - float(b)
        else:
            diff = (a - b).total_seconds()
        sign = "+" if diff >= 0 else ""
        return f"{sign}{diff:.3f}s"
    except Exception:
        return "N/A"


def get_team_color(session: fastf1.core.Session, driver: str) -> str:
    try:
        info = session.get_driver(driver)
        team = info.get("TeamName", "")
        return _safe_color(team)
    except Exception:
        return "#e10600"


def get_team_name(session: fastf1.core.Session, driver: str) -> str:
    try:
        info = session.get_driver(driver)
        return info.get("TeamName", "Unknown")
    except Exception:
        return "Unknown"


def get_driver_full_name(session: fastf1.core.Session, abbr: str) -> str:
    try:
        info = session.get_driver(abbr)
        return info.get("FullName", abbr)
    except Exception:
        return abbr


# ── Track map ────────────────────────────────────────────────────────────────

def build_track_map(lap_tel: pd.DataFrame, color: str, title: str) -> go.Figure:
    """Speed-coloured track map from telemetry x/y coordinates."""
    if lap_tel is None or lap_tel.empty or "X" not in lap_tel.columns:
        fig = go.Figure()
        fig.update_layout(title="Track map unavailable", **PLOTLY_DARK)
        return fig

    x = lap_tel["X"].values
    y = lap_tel["Y"].values
    speed = lap_tel["Speed"].values if "Speed" in lap_tel.columns else np.zeros_like(x)

    fig = go.Figure()
    # background (all grey)
    fig.add_trace(
        go.Scatter(
            x=x, y=y, mode="lines",
            line=dict(color="#333333", width=8),
            hoverinfo="skip", showlegend=False,
        )
    )
    # speed-coloured overlay
    for i in range(len(x) - 1):
        seg_speed = (speed[i] + speed[i + 1]) / 2
        norm = min(max((seg_speed - 80) / (330 - 80), 0), 1)
        r = int(255 * norm)
        g = int(40 * (1 - norm))
        b = int(120 * (1 - norm))
        seg_color = f"rgb({r},{g},{b})"
        fig.add_trace(
            go.Scatter(
                x=[x[i], x[i + 1]], y=[y[i], y[i + 1]],
                mode="lines",
                line=dict(color=seg_color, width=4),
                hovertemplate=f"Speed: {speed[i]:.0f} km/h<extra></extra>",
                showlegend=False,
            )
        )
    # start dot
    fig.add_trace(
        go.Scatter(
            x=[x[0]], y=[y[0]], mode="markers",
            marker=dict(color="#ffffff", size=10, symbol="circle",
                        line=dict(color="#000000", width=2)),
            name="Start/Finish", showlegend=False,
        )
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#cccccc")),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
        height=300,
        **PLOTLY_DARK,
    )
    return fig


# ── Delta track map ──────────────────────────────────────────────────────────

def build_delta_track_map(
    tel1: pd.DataFrame,
    tel2: pd.DataFrame,
    label1: str,
    label2: str,
    title: str,
) -> go.Figure:
    """
    GPS track map coloured by cumulative time delta.
    Green segments = driver 1 is gaining time.
    Red segments   = driver 1 is losing time.
    """
    if tel1 is None or tel2 is None or tel1.empty or "X" not in tel1.columns:
        fig = go.Figure()
        fig.update_layout(title="Delta track map unavailable", **PLOTLY_DARK)
        return fig

    def _dist(tel: pd.DataFrame) -> np.ndarray:
        return tel["Distance"].values if "Distance" in tel.columns else np.arange(len(tel))

    dist1 = _dist(tel1)
    dist2 = _dist(tel2)
    s1 = tel1["Speed"].values.astype(float)
    s2_interp = np.interp(dist1, dist2, tel2["Speed"].values.astype(float),
                          left=np.nan, right=np.nan)

    dd = dist1 - np.concatenate([[dist1[0]], dist1[:-1]])
    dt = np.where(
        (s1 > 0) & (~np.isnan(s2_interp)) & (s2_interp > 0),
        dd * (1 / s1 - 1 / s2_interp),
        0.0,
    )
    delta = np.cumsum(dt) * 3.6
    # Positive delta = driver 1 is slower here (1/s1 > 1/s2 ⟹ s1 < s2)

    x = tel1["X"].values
    y = tel1["Y"].values
    delta_max = max(float(np.abs(delta).max()), 1e-6)

    fig = go.Figure()
    # grey base
    fig.add_trace(
        go.Scatter(
            x=x, y=y, mode="lines",
            line=dict(color="#2a2a2a", width=10),
            hoverinfo="skip", showlegend=False,
        )
    )
    # delta-coloured overlay
    for i in range(len(x) - 1):
        d = delta[i]
        norm = float(np.clip(abs(d) / delta_max, 0, 1))
        if d > 0:   # losing time — red (drv1 slower: 1/s1 > 1/s2)
            r_base = int(220 * norm + 35 * (1 - norm))
            seg_color = f"rgb({r_base},{int(30*(1-norm))},{int(30*(1-norm))})"
        else:       # gaining time — green (drv1 faster: 1/s1 < 1/s2)
            g_base = int(200 * norm + 30 * (1 - norm))
            seg_color = f"rgb({int(30*(1-norm))},{g_base},{int(30*(1-norm))})"
        fig.add_trace(
            go.Scatter(
                x=[x[i], x[i + 1]], y=[y[i], y[i + 1]],
                mode="lines",
                line=dict(color=seg_color, width=5),
                hovertemplate=f"Δ: {delta[i]:+.3f}s<extra></extra>",
                showlegend=False,
            )
        )
    # start dot
    fig.add_trace(
        go.Scatter(
            x=[x[0]], y=[y[0]], mode="markers",
            marker=dict(color="#ffffff", size=10, symbol="circle",
                        line=dict(color="#000000", width=2)),
            showlegend=False,
        )
    )
    # legend labels
    for colour, lbl in [
        (DELTA_LOSING_COLOR, f"← {label1} losing"),
        (DELTA_GAINING_COLOR, f"← {label1} gaining"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=[None], y=[None], mode="lines",
                line=dict(color=colour, width=4),
                name=lbl, showlegend=True,
            )
        )
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#cccccc")),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
        height=300,
        legend=dict(
            orientation="h", yanchor="top", y=-0.02,
            xanchor="center", x=0.5,
            font=dict(size=10, color="#888"),
            bgcolor="rgba(0,0,0,0)",
        ),
        **PLOTLY_DARK,
    )
    return fig


# ── Telemetry charts ─────────────────────────────────────────────────────────

def build_telemetry_figure(
    tel1: pd.DataFrame,
    tel2: pd.DataFrame | None,
    label1: str,
    label2: str | None,
    color1: str,
    color2: str,
    channels: list[str],
) -> go.Figure:
    """
    Multi-row telemetry figure. Rows = selected channels.
    If tel2 is provided, a delta row is appended at top.
    """
    channel_labels = {
        "Speed": "Speed (km/h)",
        "Throttle": "Throttle (%)",
        "Brake": "Brake",
        "nGear": "Gear",
        "RPM": "RPM",
        "DRS": "DRS / Override",
    }

    show_delta = tel2 is not None
    # Rows: [dominance strip, delta] when comparing + one row per channel
    rows = (2 if show_delta else 0) + len(channels)
    if rows == 0:
        return go.Figure()

    row_heights = []
    if show_delta:
        row_heights.append(0.04)   # dominance strip — very thin
        row_heights.append(0.18)   # delta row
    for _ in channels:
        row_heights.append(1.0)
    # normalise
    total = sum(row_heights)
    row_heights = [h / total for h in row_heights]

    subplot_titles = (["", "Δ Delta (s)"] if show_delta else []) + [
        channel_labels.get(c, c) for c in channels
    ]

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
        vertical_spacing=0.04,
    )

    def _dist(tel: pd.DataFrame) -> np.ndarray:
        if "Distance" in tel.columns:
            return tel["Distance"].values
        return np.arange(len(tel))

    dist1 = _dist(tel1)

    # ── dominance strip + delta rows ────────────────────────────────────────
    delta_row_offset = 0
    if show_delta and tel2 is not None:
        delta_row_offset = 2   # row 1 = dominance, row 2 = delta
        dist2 = _dist(tel2)

        if "Speed" in tel1.columns and "Speed" in tel2.columns:
            s1 = tel1["Speed"].values.astype(float)
            s2_interp = np.interp(dist1, dist2, tel2["Speed"].values.astype(float),
                                  left=np.nan, right=np.nan)

            # ── dominance strip (row 1) ──────────────────────────────────
            faster_mask = np.where(
                (~np.isnan(s2_interp)) & (s1 > s2_interp), 1.0, 0.0
            )
            y_drv1 = np.where(faster_mask == 1.0, 1.0, np.nan)
            y_drv2 = np.where(faster_mask == 0.0, 1.0, np.nan)

            fig.add_trace(
                go.Scatter(
                    x=dist1, y=y_drv1,
                    fill="tozeroy", mode="none",
                    fillcolor=color1 + "cc",
                    name=f"{label1} faster",
                    showlegend=False, hoverinfo="skip",
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=dist1, y=y_drv2,
                    fill="tozeroy", mode="none",
                    fillcolor=color2 + "cc",
                    name=f"{label2} faster",
                    showlegend=False, hoverinfo="skip",
                ),
                row=1, col=1,
            )

            # ── cumulative delta (row 2) ─────────────────────────────────
            dd = dist1 - np.concatenate([[dist1[0]], dist1[:-1]])
            dt_speed = np.where(
                (s1 > 0) & (~np.isnan(s2_interp)) & (s2_interp > 0),
                dd * (1 / s1 - 1 / s2_interp),
                0.0,
            )
            delta = np.cumsum(dt_speed) * 3.6
        else:
            delta = np.zeros_like(dist1)

        fig.add_trace(
            go.Scatter(
                x=dist1, y=delta, mode="lines",
                line=dict(color=color2, width=1.5),
                name=f"Δ {label2}",
                hovertemplate="Distance: %{x:.0f} m<br>Delta: %{y:.3f} s<extra></extra>",
            ),
            row=2, col=1,
        )
        fig.add_hline(y=0, line=dict(color="#555", dash="dash", width=1), row=2, col=1)

    # ── telemetry channels ───────────────────────────────────────────────────
    for ch_idx, channel in enumerate(channels):
        row = ch_idx + 1 + delta_row_offset

        if channel not in tel1.columns:
            continue

        y1 = tel1[channel].values.astype(float)
        if channel == "Throttle":
            y1 = np.clip(y1 * 100 if y1.max() <= 1.0 else y1, 0, 100)

        fig.add_trace(
            go.Scatter(
                x=dist1, y=y1, mode="lines",
                line=dict(color=color1, width=1.8),
                name=label1,
                legendgroup=label1,
                showlegend=(ch_idx == 0),
                hovertemplate=f"{channel}: %{{y:.1f}}<br>Dist: %{{x:.0f}} m<extra></extra>",
            ),
            row=row, col=1,
        )

        if tel2 is not None and channel in tel2.columns:
            dist2 = _dist(tel2)
            y2 = tel2[channel].values.astype(float)
            if channel == "Throttle":
                y2 = np.clip(y2 * 100 if y2.max() <= 1.0 else y2, 0, 100)

            fig.add_trace(
                go.Scatter(
                    x=dist2, y=y2, mode="lines",
                    line=dict(color=color2, width=1.5, dash="dot"),
                    name=label2,
                    legendgroup=label2,
                    showlegend=(ch_idx == 0),
                    hovertemplate=f"{channel}: %{{y:.1f}}<br>Dist: %{{x:.0f}} m<extra></extra>",
                ),
                row=row, col=1,
            )

        # Gear: step style
        if channel == "nGear":
            for trace in fig.data[-2:]:
                trace.line.shape = "hv"  # type: ignore[attr-defined]

    # ── shared styling ───────────────────────────────────────────────────────
    # Fixed 650 px keeps the chart within one viewport even when all
    # 6 channels + dominance strip + delta row are active simultaneously.
    fig.update_layout(
        height=650,
        paper_bgcolor="#0d0d0d",
        plot_bgcolor="#111111",
        font=dict(color="#cccccc", family="Segoe UI, Inter, sans-serif", size=11),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01,
            xanchor="right", x=1,
            font=dict(size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=60, r=20, t=60, b=40),
        hovermode="x unified",
    )
    for i in range(1, rows + 1):
        fig.update_xaxes(
            gridcolor="#1e1e1e", linecolor="#333", showgrid=True, zeroline=False,
            row=i, col=1,
        )
        fig.update_yaxes(
            gridcolor="#1e1e1e", linecolor="#333", showgrid=True, zeroline=False,
            row=i, col=1,
        )
    # dominance strip: hide y-axis ticks/labels entirely
    if show_delta:
        fig.update_yaxes(showticklabels=False, showgrid=False,
                         range=[0, 1], row=1, col=1)
    # x-axis label only on last row
    fig.update_xaxes(title_text="Distance (m)", row=rows, col=1)

    # subplot title colour
    for ann in fig.layout.annotations:  # type: ignore[attr-defined]
        ann.font.color = "#888888"
        ann.font.size = 10

    return fig


# ── Lap summary table ─────────────────────────────────────────────────────────

def build_lap_table(laps: pd.DataFrame, color: str) -> go.Figure:
    cols = ["LapNumber", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time",
            "Compound", "TyreLife", "SpeedI1", "SpeedI2", "SpeedFL", "SpeedST"]
    available = [c for c in cols if c in laps.columns]

    disp = laps[available].copy()
    for col in ["LapTime", "Sector1Time", "Sector2Time", "Sector3Time"]:
        if col in disp.columns:
            disp[col] = disp[col].apply(format_lap_time)

    fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=[f"<b>{c}</b>" for c in available],
                    fill_color="#1a1a1a",
                    font=dict(color="#cccccc", size=11),
                    align="center",
                    line_color="#333",
                ),
                cells=dict(
                    values=[disp[c].tolist() for c in available],
                    fill_color=["#111111", "#141414"] * (len(available) // 2 + 1),
                    font=dict(color=["#e8e8e8"] * (len(available) - 1) + [color], size=11),
                    align="center",
                    line_color="#1e1e1e",
                ),
            )
        ]
    )
    fig.update_layout(
        paper_bgcolor="#0d0d0d",
        margin=dict(l=0, r=0, t=10, b=0),
        height=min(60 + len(disp) * 28, 500),
    )
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────

def sidebar() -> dict:
    st.sidebar.markdown(
        "<h2 style='color:#e10600;margin-bottom:4px;'>🏎️ F1 Telemetry</h2>"
        "<p style='color:#555;font-size:0.75rem;margin-top:0;'>Powered by FastF1</p>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")

    year = st.sidebar.selectbox(
        "Season",
        options=list(range(datetime.datetime.now().year, 2018, -1)),
        index=0,
    )

    with st.sidebar:
        with st.spinner("Loading schedule…"):
            try:
                events = get_event_names(year)
            except Exception:
                events = []

    event = st.sidebar.selectbox("Grand Prix", options=events) if events else None

    session_map = {
        "Race": "R",
        "Qualifying": "Q",
        "Sprint": "S",
        "Sprint Qualifying": "SQ",
        "Practice 1": "FP1",
        "Practice 2": "FP2",
        "Practice 3": "FP3",
    }
    session_label = st.sidebar.selectbox("Session", list(session_map.keys()))
    session_type = session_map[session_label]

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<p style='color:#555;font-size:0.72rem;text-transform:uppercase;"
        "letter-spacing:0.06em;'>Primary Driver</p>",
        unsafe_allow_html=True,
    )

    load_btn = st.sidebar.button("Load Session", use_container_width=True, type="primary")

    return {
        "year": year,
        "event": event,
        "session_type": session_type,
        "session_label": session_label,
        "load": load_btn,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    params = sidebar()

    # ── Hero header ──────────────────────────────────────────────────────────
    st.markdown(
        "<h1 style='font-size:2.2rem;margin-bottom:0;'>F1 Telemetry Dashboard</h1>"
        "<p style='color:#555;margin-top:4px;font-size:0.9rem;'>"
        "Real-time lap analysis · Speed · Throttle · Braking · Gear · RPM · Delta"
        "</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    if not params["load"]:
        st.info(
            "👈  Select a **Season**, **Grand Prix** and **Session** in the sidebar, "
            "then press **Load Session**."
        )
        st.markdown(
            """
            <div style='display:flex;gap:20px;flex-wrap:wrap;margin-top:24px;'>
            <div style='background:#141414;border:1px solid #2a2a2a;border-radius:8px;
                        padding:20px;flex:1;min-width:200px;'>
                <div style='color:#e10600;font-size:1.5rem;'>📊</div>
                <div style='color:#ccc;font-weight:600;margin-top:8px;'>Lap Telemetry</div>
                <div style='color:#666;font-size:0.82rem;margin-top:4px;'>
                    Speed, throttle, brake, gear and RPM for every lap of every driver.
                </div>
            </div>
            <div style='background:#141414;border:1px solid #2a2a2a;border-radius:8px;
                        padding:20px;flex:1;min-width:200px;'>
                <div style='color:#e10600;font-size:1.5rem;'>⚡</div>
                <div style='color:#ccc;font-weight:600;margin-top:8px;'>Head-to-Head</div>
                <div style='color:#666;font-size:0.82rem;margin-top:4px;'>
                    Compare any two laps with cumulative delta time overlay.
                </div>
            </div>
            <div style='background:#141414;border:1px solid #2a2a2a;border-radius:8px;
                        padding:20px;flex:1;min-width:200px;'>
                <div style='color:#e10600;font-size:1.5rem;'>🗺️</div>
                <div style='color:#ccc;font-weight:600;margin-top:8px;'>Track Map</div>
                <div style='color:#666;font-size:0.82rem;margin-top:4px;'>
                    Speed-coloured circuit map generated from GPS telemetry.
                </div>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ── Load session ─────────────────────────────────────────────────────────
    with st.spinner(f"Loading {params['year']} {params['event']} — {params['session_label']}…"):
        try:
            session = load_session(params["year"], params["event"], params["session_type"])
        except Exception as exc:
            st.error(f"Could not load session: {exc}")
            return

    drivers = sorted(session.laps["Driver"].unique())
    if not drivers:
        st.warning("No driver data found for this session.")
        return

    # ── Driver / lap selectors ────────────────────────────────────────────────
    col_a, col_b, col_c, col_d, col_e, col_f = st.columns([2, 2, 1, 2, 2, 1])

    with col_a:
        drv1 = st.selectbox("Primary Driver", drivers, key="drv1")
    laps1 = session.laps.pick_drivers(drv1)
    valid_laps1 = laps1[laps1["LapTime"].notna()]["LapNumber"].astype(int).tolist()
    with col_b:
        if valid_laps1:
            lap1_num = st.selectbox("Lap", valid_laps1, key="lap1",
                                    index=len(valid_laps1) - 1)
        else:
            st.warning("No timed laps for this driver.")
            return

    # Fastest lap shortcut
    with col_c:
        if st.button("⚡ Fastest", key="fast1", use_container_width=True):
            fl = laps1.pick_fastest()
            if fl is not None and not pd.isna(fl["LapNumber"]):
                lap1_num = int(fl["LapNumber"])

    compare_on = st.checkbox("Compare with another driver / lap", value=False)
    vs_session_best = compare_on and st.checkbox(
        "🏆 Auto: vs Session Best (entire grid)", value=False, key="vsb"
    )

    drv2, lap2_num = None, None
    if compare_on:
        if vs_session_best:
            try:
                _sb = session.laps.pick_fastest()
                drv2 = str(_sb["Driver"])
                lap2_num = int(_sb["LapNumber"])
                laps2 = session.laps.pick_drivers(drv2)
                _sb_time = format_lap_time(_sb["LapTime"])
                st.info(
                    f"🏆 Session best: **{drv2}** · Lap **{lap2_num}** · {_sb_time}"
                )
            except Exception:
                st.warning("Could not determine session fastest lap.")
                compare_on = False
        else:
            with col_d:
                drv2 = st.selectbox("Compare Driver", drivers, key="drv2",
                                    index=min(1, len(drivers) - 1))
            laps2 = session.laps.pick_drivers(drv2)
            valid_laps2 = laps2[laps2["LapTime"].notna()]["LapNumber"].astype(int).tolist()
            with col_e:
                if valid_laps2:
                    lap2_num = st.selectbox("Lap", valid_laps2, key="lap2",
                                            index=len(valid_laps2) - 1)
                else:
                    st.warning(f"No timed laps for {drv2}.")
                    compare_on = False
            with col_f:
                if compare_on and st.button("⚡ Fastest", key="fast2", use_container_width=True):
                    fl2 = laps2.pick_fastest()
                    if fl2 is not None and not pd.isna(fl2["LapNumber"]):
                        lap2_num = int(fl2["LapNumber"])

    st.markdown("---")

    # ── Resolve laps ──────────────────────────────────────────────────────────
    lap1_row = laps1[laps1["LapNumber"] == lap1_num].iloc[0] if valid_laps1 else None
    color1 = get_team_color(session, drv1)
    team1 = get_team_name(session, drv1)
    full1 = get_driver_full_name(session, drv1)

    color2 = "#ffffff"
    team2, full2, lap2_row = "", "", None
    if compare_on and drv2 and lap2_num is not None:
        laps2 = session.laps.pick_drivers(drv2)
        lap2_row = laps2[laps2["LapNumber"] == lap2_num].iloc[0] if not laps2.empty else None
        color2 = get_team_color(session, drv2)
        team2 = get_team_name(session, drv2)
        full2 = get_driver_full_name(session, drv2)

    # ── Metric cards ──────────────────────────────────────────────────────────
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        lt1 = format_lap_time(lap1_row["LapTime"]) if lap1_row is not None else "N/A"
        st.metric(f"🏁 {drv1} — Lap {lap1_num}", lt1,
                  delta=team1, delta_color="off")
    with mc2:
        if compare_on and lap2_row is not None:
            lt2 = format_lap_time(lap2_row["LapTime"])
            delta_v = delta_str(lap2_row["LapTime"], lap1_row["LapTime"]) if lap1_row is not None else "N/A"
            st.metric(f"🏁 {drv2} — Lap {lap2_num}", lt2,
                      delta=f"Δ vs {drv1}: {delta_v}", delta_color="inverse")
    with mc3:
        if lap1_row is not None and "SpeedST" in lap1_row.index:
            st.metric("Speed Trap (km/h)", f"{lap1_row.get('SpeedST', 'N/A'):.0f}" if isinstance(lap1_row.get("SpeedST"), float) else "N/A")
    with mc4:
        if lap1_row is not None and "Compound" in lap1_row.index:
            st.metric("Compound", str(lap1_row.get("Compound", "N/A")))

    # ── Team logo strip ───────────────────────────────────────────────────────
    logo_cols = [c for c in [team1, team2] if c]
    if logo_cols:
        lc = st.columns(max(len(logo_cols), 1) + 6)
        for idx, team in enumerate(logo_cols):
            logo_url = TEAM_LOGOS.get(team)
            if logo_url:
                lc[idx].markdown(
                    f"<img src='{logo_url}' style='height:48px;object-fit:contain;"
                    f"filter:drop-shadow(0 0 6px {TEAM_COLORS.get(team, '#fff')}44);'/>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # ── Channel selector ─────────────────────────────────────────────────────
    all_channels = ["Speed", "Throttle", "Brake", "nGear", "RPM", "DRS"]
    default_ch = ["Speed", "Throttle", "Brake"]
    selected_channels = st.multiselect(
        "Telemetry channels",
        options=all_channels,
        default=default_ch,
        key="channels",
    )

    # ── Load telemetry ────────────────────────────────────────────────────────
    tel1, tel2 = None, None
    with st.spinner("Fetching telemetry…"):
        try:
            if lap1_row is not None:
                tel1 = lap1_row.get_telemetry().add_distance()
        except Exception as e:
            st.warning(f"Could not load telemetry for {drv1} lap {lap1_num}: {e}")

        try:
            if compare_on and lap2_row is not None:
                tel2 = lap2_row.get_telemetry().add_distance()
        except Exception as e:
            st.warning(f"Could not load telemetry for {drv2} lap {lap2_num}: {e}")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab_tel, tab_map, tab_laps = st.tabs(["📈 Telemetry", "🗺️ Track Map", "📋 Lap Summary"])

    with tab_tel:
        if tel1 is None:
            st.warning("No telemetry data available.")
        elif not selected_channels:
            st.info("Select at least one telemetry channel above.")
        else:
            label1 = f"{drv1} · Lap {lap1_num}"
            label2 = f"{drv2} · Lap {lap2_num}" if compare_on and drv2 else None
            fig = build_telemetry_figure(
                tel1, tel2,
                label1, label2,
                color1, color2,
                selected_channels,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with tab_map:
        map_mode_cols = st.columns([2, 1]) if compare_on and tel2 is not None else [None]
        if compare_on and tel2 is not None:
            with map_mode_cols[1]:
                map_mode = st.radio(
                    "Colour by",
                    ["Speed", "Time Delta"],
                    horizontal=True,
                    key="map_mode",
                )
        else:
            map_mode = "Speed"

        if map_mode == "Time Delta" and compare_on and tel1 is not None and tel2 is not None:
            fig_delta_map = build_delta_track_map(
                tel1, tel2,
                f"{drv1}", f"{drv2}",
                f"{drv1} vs {drv2} · Lap {lap1_num} vs {lap2_num} · Time Delta Map",
            )
            st.plotly_chart(fig_delta_map, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            map_cols = st.columns(2 if compare_on and tel2 is not None else 1)
            with map_cols[0]:
                if tel1 is not None:
                    fig_map1 = build_track_map(tel1, color1,
                                               f"{drv1} · Lap {lap1_num} · Speed Map")
                    st.plotly_chart(fig_map1, use_container_width=True,
                                    config={"displayModeBar": False})
                else:
                    st.info("No telemetry for track map.")
            if compare_on and tel2 is not None and len(map_cols) > 1:
                with map_cols[1]:
                    fig_map2 = build_track_map(tel2, color2,
                                               f"{drv2} · Lap {lap2_num} · Speed Map")
                    st.plotly_chart(fig_map2, use_container_width=True,
                                    config={"displayModeBar": False})

    with tab_laps:
        st.markdown(f"#### {full1} — all laps")
        fig_tbl1 = build_lap_table(laps1, color1)
        st.plotly_chart(fig_tbl1, use_container_width=True, config={"displayModeBar": False})
        if compare_on and drv2:
            st.markdown(f"#### {full2} — all laps")
            laps2_full = session.laps.pick_drivers(drv2)
            fig_tbl2 = build_lap_table(laps2_full, color2)
            st.plotly_chart(fig_tbl2, use_container_width=True,
                            config={"displayModeBar": False})

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        "<p style='color:#333;font-size:0.72rem;text-align:center;'>"
        "Data provided by <a href='https://github.com/theOehrly/Fast-F1' "
        "style='color:#555;'>FastF1</a> · "
        "F1, Formula One and all associated marks are trademarks of "
        "Formula One Licensing BV"
        "</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
