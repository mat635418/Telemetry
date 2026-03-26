"""
F1 Telemetry Dashboard — Streamlit app powered by FastF1.

Displays lap-by-lap telemetry (speed, throttle, brake, gear, RPM, DRS,
delta time) for any driver/session, with an optional head-to-head
comparison and a speed-coloured track map.
"""

from __future__ import annotations

import datetime
import hmac
import warnings
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

# ── FastF1 cache ─────────────────────────────────────────────────────────────
CACHE_DIR = Path("f1_cache")
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 Telemetry Dashboard",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global light theme CSS ────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── global ── */
    html, body, [data-testid="stApp"] {
        background-color: #f4f4f5;
        color: #1a1a1a;
        font-family: 'Segoe UI', 'Inter', sans-serif;
    }

    /* ── sidebar — grey ── */
    [data-testid="stSidebar"] {
        background-color: #e8e8ec !important;
        border-right: 1px solid #d0d0d8;
    }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] p {
        color: #444444 !important;
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    [data-testid="stSidebar"] h2 {
        color: #e10600 !important;
    }

    /* ── main content area ── */
    [data-testid="stMain"] {
        background-color: #f4f4f5;
    }

    /* ── metric cards ── */
    [data-testid="metric-container"] {
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 14px 18px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    [data-testid="metric-container"] label {
        color: #888 !important;
        font-size: 0.73rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #e10600 !important;
        font-size: 1.55rem !important;
        font-weight: 700;
    }
    [data-testid="metric-container"] [data-testid="stMetricDelta"] {
        font-size: 0.82rem !important;
    }

    /* ── headers ── */
    h1 { color: #e10600 !important; letter-spacing: -0.02em; }
    h2, h3, h4 { color: #1a1a1a !important; }

    /* ── dividers ── */
    hr { border-color: #dcdcdc; }

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

    /* ── login page: left-aligned, compact ── */
    div[data-testid="stForm"] {
        max-width: 400px;
        margin-left: 0 !important;
        margin-right: auto !important;
    }
    div[data-testid="stForm"] input {
        background: #ffffff;
        border: 1px solid #d0d0d8;
        border-radius: 6px;
    }

    /* ── primary button ── */
    button[kind="primary"] {
        background-color: #e10600 !important;
        border: none !important;
        color: #ffffff !important;
        border-radius: 6px !important;
    }
    button[kind="primary"]:hover {
        background-color: #b30500 !important;
    }

    /* ── checkbox ── */
    [data-testid="stCheckbox"] label {
        color: #333 !important;
        font-size: 0.88rem;
    }

    /* ── multiselect ── */
    [data-testid="stMultiSelect"] label {
        color: #555 !important;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* ── info / warning boxes ── */
    [data-testid="stAlert"] {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Plotly light theme ────────────────────────────────────────────────────────
PLOTLY_THEME = dict(
    paper_bgcolor="#ffffff",
    plot_bgcolor="#f8f8f8",
    font=dict(color="#333333", family="Segoe UI, Inter, sans-serif", size=11),
    xaxis=dict(
        gridcolor="#e8e8e8",
        linecolor="#cccccc",
        tickcolor="#cccccc",
        showgrid=True,
        zeroline=False,
    ),
    yaxis=dict(
        gridcolor="#e8e8e8",
        linecolor="#cccccc",
        tickcolor="#cccccc",
        showgrid=True,
        zeroline=False,
    ),
)

# ── Team colours & logos ──────────────────────────────────────────────────────
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

DELTA_LOSING_COLOR  = "#dc2626"
DELTA_GAINING_COLOR = "#16a34a"

DEFAULT_DRIVER_1 = "LEC"
DEFAULT_DRIVER_2 = "HAM"


# ── Authentication ────────────────────────────────────────────────────────────

def _check_login() -> None:
    """
    Left-aligned login form.  Blocks until valid credentials are entered.
    Credentials live in .streamlit/secrets.toml under [auth].
    """
    if st.session_state.get("authenticated"):
        return

    # Title + subtitle — left-aligned naturally
    st.markdown(
        "<h1 style='margin-bottom:4px;'>🏎️ F1 Telemetry Dashboard</h1>"
        "<p style='color:#666;font-size:0.92rem;margin-top:0;margin-bottom:28px;'>"
        "Sign in to access live lap analysis</p>",
        unsafe_allow_html=True,
    )

    # The CSS above constrains the form to 400 px left-aligned
    with st.form("login_form"):
        st.markdown(
            "<p style='font-size:0.8rem;color:#888;text-transform:uppercase;"
            "letter-spacing:0.06em;margin-bottom:2px;'>Username</p>",
            unsafe_allow_html=True,
        )
        username = st.text_input("Username", label_visibility="collapsed")

        st.markdown(
            "<p style='font-size:0.8rem;color:#888;text-transform:uppercase;"
            "letter-spacing:0.06em;margin-bottom:2px;margin-top:10px;'>Password</p>",
            unsafe_allow_html=True,
        )
        password = st.text_input("Password", type="password", label_visibility="collapsed")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Log in →", use_container_width=False, type="primary")

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


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    try:
        diff = float(a) - float(b) if isinstance(a, (int, float)) else (a - b).total_seconds()
        sign = "+" if diff >= 0 else ""
        return f"{sign}{diff:.3f}s"
    except Exception:
        return "N/A"


def get_team_color(session: fastf1.core.Session, driver: str) -> str:
    try:
        return _safe_color(session.get_driver(driver).get("TeamName", ""))
    except Exception:
        return "#e10600"


def get_team_name(session: fastf1.core.Session, driver: str) -> str:
    try:
        return session.get_driver(driver).get("TeamName", "Unknown")
    except Exception:
        return "Unknown"


def get_driver_full_name(session: fastf1.core.Session, abbr: str) -> str:
    try:
        return session.get_driver(abbr).get("FullName", abbr)
    except Exception:
        return abbr


def _best_lap_num(laps: pd.DataFrame) -> int | None:
    """Return lap number of the fastest timed lap, or None."""
    try:
        fl = laps.pick_fastest()
        if fl is not None and not pd.isna(fl["LapNumber"]):
            return int(fl["LapNumber"])
    except Exception:
        pass
    timed = laps[laps["LapTime"].notna()]
    return int(timed["LapNumber"].iloc[0]) if not timed.empty else None


def _driver_index(drivers: list[str], abbr: str) -> int:
    """Return index of abbr in drivers list, defaulting to 0."""
    return drivers.index(abbr) if abbr in drivers else 0


# ── Track map ─────────────────────────────────────────────────────────────────

def build_track_map(lap_tel: pd.DataFrame, color: str, title: str) -> go.Figure:
    if lap_tel is None or lap_tel.empty or "X" not in lap_tel.columns:
        fig = go.Figure()
        fig.update_layout(title="Track map unavailable", **PLOTLY_THEME)
        return fig

    x, y = lap_tel["X"].values, lap_tel["Y"].values
    speed = lap_tel["Speed"].values if "Speed" in lap_tel.columns else np.zeros_like(x)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines",
        line=dict(color="#cccccc", width=8),
        hoverinfo="skip", showlegend=False,
    ))
    for i in range(len(x) - 1):
        norm = min(max(((speed[i] + speed[i + 1]) / 2 - 80) / 250, 0), 1)
        seg = f"rgb({int(255*norm)},{int(40*(1-norm))},{int(120*(1-norm))})"
        fig.add_trace(go.Scatter(
            x=[x[i], x[i + 1]], y=[y[i], y[i + 1]],
            mode="lines", line=dict(color=seg, width=4),
            hovertemplate=f"Speed: {speed[i]:.0f} km/h<extra></extra>",
            showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=[x[0]], y=[y[0]], mode="markers",
        marker=dict(color="#ffffff", size=10, symbol="circle",
                    line=dict(color="#000000", width=2)),
        showlegend=False,
    ))
    fig.update_layout(
        **PLOTLY_THEME,
        title=dict(text=title, font=dict(size=13, color="#555555")),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
        height=320,
    )
    return fig


# ── Delta track map ───────────────────────────────────────────────────────────

def build_delta_track_map(
    tel1: pd.DataFrame,
    tel2: pd.DataFrame,
    label1: str,
    label2: str,
    title: str,
) -> go.Figure:
    if tel1 is None or tel2 is None or tel1.empty or "X" not in tel1.columns:
        fig = go.Figure()
        fig.update_layout(title="Delta track map unavailable", **PLOTLY_THEME)
        return fig

    dist1 = tel1["Distance"].values if "Distance" in tel1.columns else np.arange(len(tel1))
    dist2 = tel2["Distance"].values if "Distance" in tel2.columns else np.arange(len(tel2))
    s1 = tel1["Speed"].values.astype(float)
    s2i = np.interp(dist1, dist2, tel2["Speed"].values.astype(float), left=np.nan, right=np.nan)

    dd = dist1 - np.concatenate([[dist1[0]], dist1[:-1]])
    dt = np.where((s1 > 0) & (~np.isnan(s2i)) & (s2i > 0), dd * (1 / s1 - 1 / s2i), 0.0)
    delta = np.cumsum(dt) * 3.6
    delta_max = max(float(np.abs(delta).max()), 1e-6)

    x, y = tel1["X"].values, tel1["Y"].values
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines",
        line=dict(color="#cccccc", width=10),
        hoverinfo="skip", showlegend=False,
    ))
    for i in range(len(x) - 1):
        d = delta[i]
        norm = float(np.clip(abs(d) / delta_max, 0, 1))
        if d > 0:
            seg = f"rgb({int(220*norm+35*(1-norm))},{int(30*(1-norm))},{int(30*(1-norm))})"
        else:
            seg = f"rgb({int(30*(1-norm))},{int(200*norm+30*(1-norm))},{int(30*(1-norm))})"
        fig.add_trace(go.Scatter(
            x=[x[i], x[i + 1]], y=[y[i], y[i + 1]],
            mode="lines", line=dict(color=seg, width=5),
            hovertemplate=f"Δ: {delta[i]:+.3f}s<extra></extra>",
            showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=[x[0]], y=[y[0]], mode="markers",
        marker=dict(color="#ffffff", size=10, symbol="circle",
                    line=dict(color="#000000", width=2)),
        showlegend=False,
    ))
    for colour, lbl in [
        (DELTA_LOSING_COLOR, f"{label1} losing"),
        (DELTA_GAINING_COLOR, f"{label1} gaining"),
    ]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="lines",
            line=dict(color=colour, width=4),
            name=lbl, showlegend=True,
        ))
    fig.update_layout(
        **PLOTLY_THEME,
        title=dict(text=title, font=dict(size=13, color="#555555")),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
        height=320,
        legend=dict(
            orientation="h", yanchor="top", y=-0.02,
            xanchor="center", x=0.5,
            font=dict(size=10, color="#555"),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


# ── Telemetry figure ──────────────────────────────────────────────────────────

def build_telemetry_figure(
    tel1: pd.DataFrame,
    tel2: pd.DataFrame | None,
    label1: str,
    label2: str | None,
    color1: str,
    color2: str,
    channels: list[str],
) -> go.Figure:
    channel_labels = {
        "Speed": "Speed (km/h)",
        "Throttle": "Throttle (%)",
        "Brake": "Brake",
        "nGear": "Gear",
        "RPM": "RPM",
        "DRS": "DRS",
    }

    show_delta = tel2 is not None
    rows = (2 if show_delta else 0) + len(channels)
    if rows == 0:
        return go.Figure()

    row_heights = ([0.04, 0.18] if show_delta else []) + [1.0] * len(channels)
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
        return tel["Distance"].values if "Distance" in tel.columns else np.arange(len(tel))

    dist1 = _dist(tel1)
    delta_row_offset = 0

    if show_delta and tel2 is not None:
        delta_row_offset = 2
        dist2 = _dist(tel2)

        if "Speed" in tel1.columns and "Speed" in tel2.columns:
            s1 = tel1["Speed"].values.astype(float)
            s2i = np.interp(dist1, dist2, tel2["Speed"].values.astype(float),
                            left=np.nan, right=np.nan)

            # Dominance strip (row 1)
            y_drv1 = np.where((~np.isnan(s2i)) & (s1 > s2i), 1.0, np.nan)
            y_drv2 = np.where((~np.isnan(s2i)) & (s1 <= s2i), 1.0, np.nan)
            for y_vals, col, grp in [(y_drv1, color1, label1), (y_drv2, color2, label2)]:
                fig.add_trace(go.Scatter(
                    x=dist1, y=y_vals, fill="tozeroy", mode="none",
                    fillcolor=col + "bb",
                    name=grp, showlegend=False, hoverinfo="skip",
                ), row=1, col=1)

            # Cumulative delta (row 2)
            dd = dist1 - np.concatenate([[dist1[0]], dist1[:-1]])
            dt = np.where((s1 > 0) & (~np.isnan(s2i)) & (s2i > 0),
                          dd * (1 / s1 - 1 / s2i), 0.0)
            delta = np.cumsum(dt) * 3.6
        else:
            delta = np.zeros_like(dist1)

        fig.add_trace(go.Scatter(
            x=dist1, y=delta, mode="lines",
            line=dict(color=color2, width=1.8),
            name=f"Δ {label2}",
            hovertemplate="Dist: %{x:.0f} m<br>Δ: %{y:.3f}s<extra></extra>",
        ), row=2, col=1)
        fig.add_hline(y=0, line=dict(color="#aaaaaa", dash="dash", width=1), row=2, col=1)

    # Telemetry channels
    for ch_idx, channel in enumerate(channels):
        row = ch_idx + 1 + delta_row_offset
        if channel not in tel1.columns:
            continue

        y1 = tel1[channel].values.astype(float)
        if channel == "Throttle":
            y1 = np.clip(y1 * 100 if y1.max() <= 1.0 else y1, 0, 100)

        fig.add_trace(go.Scatter(
            x=dist1, y=y1, mode="lines",
            line=dict(color=color1, width=2.0),
            name=label1, legendgroup=label1,
            showlegend=(ch_idx == 0),
            hovertemplate=f"{channel}: %{{y:.1f}}<br>Dist: %{{x:.0f}} m<extra></extra>",
        ), row=row, col=1)

        if tel2 is not None and channel in tel2.columns:
            dist2 = _dist(tel2)
            y2 = tel2[channel].values.astype(float)
            if channel == "Throttle":
                y2 = np.clip(y2 * 100 if y2.max() <= 1.0 else y2, 0, 100)
            fig.add_trace(go.Scatter(
                x=dist2, y=y2, mode="lines",
                line=dict(color=color2, width=1.6, dash="dot"),
                name=label2, legendgroup=label2,
                showlegend=(ch_idx == 0),
                hovertemplate=f"{channel}: %{{y:.1f}}<br>Dist: %{{x:.0f}} m<extra></extra>",
            ), row=row, col=1)

        if channel == "nGear":
            for trace in fig.data[-2:]:
                trace.line.shape = "hv"  # type: ignore[attr-defined]

    # Layout
    fig.update_layout(
        height=680,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8f8f8",
        font=dict(color="#333333", family="Segoe UI, Inter, sans-serif", size=11),
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
        fig.update_xaxes(gridcolor="#e8e8e8", linecolor="#cccccc",
                         showgrid=True, zeroline=False, row=i, col=1)
        fig.update_yaxes(gridcolor="#e8e8e8", linecolor="#cccccc",
                         showgrid=True, zeroline=False, row=i, col=1)
    if show_delta:
        fig.update_yaxes(showticklabels=False, showgrid=False, range=[0, 1], row=1, col=1)
    fig.update_xaxes(title_text="Distance (m)", row=rows, col=1)
    for ann in fig.layout.annotations:  # type: ignore[attr-defined]
        ann.font.color = "#777777"
        ann.font.size = 10

    return fig


# ── Lap table ─────────────────────────────────────────────────────────────────

def build_lap_table(laps: pd.DataFrame, color: str) -> go.Figure:
    cols = ["LapNumber", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time",
            "Compound", "TyreLife", "SpeedI1", "SpeedI2", "SpeedFL", "SpeedST"]
    available = [c for c in cols if c in laps.columns]
    disp = laps[available].copy()
    for col in ["LapTime", "Sector1Time", "Sector2Time", "Sector3Time"]:
        if col in disp.columns:
            disp[col] = disp[col].apply(format_lap_time)

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=[f"<b>{c}</b>" for c in available],
            fill_color="#f0f0f0",
            font=dict(color="#333333", size=11),
            align="center",
            line_color="#dddddd",
        ),
        cells=dict(
            values=[disp[c].tolist() for c in available],
            fill_color=["#ffffff", "#f8f8f8"] * (len(available) // 2 + 1),
            font=dict(color=["#333333"] * (len(available) - 1) + [color], size=11),
            align="center",
            line_color="#eeeeee",
        ),
    )])
    fig.update_layout(
        paper_bgcolor="#ffffff",
        margin=dict(l=0, r=0, t=10, b=0),
        height=min(60 + len(disp) * 28, 500),
    )
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────

def sidebar() -> dict:
    st.sidebar.markdown(
        "<h2 style='color:#e10600;margin-bottom:2px;'>🏎️ F1 Telemetry</h2>"
        "<p style='color:#666;font-size:0.73rem;margin-top:0;margin-bottom:12px;'>"
        "Powered by FastF1</p>",
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
    load_btn = st.sidebar.button("Load Session ›", use_container_width=True, type="primary")

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

    # Hero
    st.markdown(
        "<h1 style='font-size:2.1rem;margin-bottom:0;'>F1 Telemetry Dashboard</h1>"
        "<p style='color:#888;margin-top:4px;font-size:0.9rem;'>"
        "Lap analysis · Speed · Throttle · Braking · Gear · RPM · Delta"
        "</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    if params["load"]:
        st.session_state["loaded_params"] = {
            "year": params["year"],
            "event": params["event"],
            "session_type": params["session_type"],
            "session_label": params["session_label"],
        }
        # Clear cached driver/lap choices when a new session is loaded
        for k in ("drv1", "drv2", "lap1_num", "lap2_num"):
            st.session_state.pop(k, None)

    loaded = st.session_state.get("loaded_params")

    if not loaded:
        st.info("👈  Select a **Season**, **Grand Prix** and **Session** in the sidebar, then press **Load Session**.")
        st.markdown(
            """
            <div style='display:flex;gap:16px;flex-wrap:wrap;margin-top:24px;'>
            <div style='background:#fff;border:1px solid #e0e0e0;border-radius:8px;
                        padding:20px;flex:1;min-width:180px;box-shadow:0 1px 4px rgba(0,0,0,0.05);'>
                <div style='color:#e10600;font-size:1.5rem;'>📊</div>
                <div style='color:#333;font-weight:600;margin-top:8px;'>Lap Telemetry</div>
                <div style='color:#888;font-size:0.82rem;margin-top:4px;'>
                    Speed, throttle, brake, gear and RPM for every lap of every driver.
                </div>
            </div>
            <div style='background:#fff;border:1px solid #e0e0e0;border-radius:8px;
                        padding:20px;flex:1;min-width:180px;box-shadow:0 1px 4px rgba(0,0,0,0.05);'>
                <div style='color:#e10600;font-size:1.5rem;'>⚡</div>
                <div style='color:#333;font-weight:600;margin-top:8px;'>Head-to-Head</div>
                <div style='color:#888;font-size:0.82rem;margin-top:4px;'>
                    Compare any two laps with cumulative delta time overlay.
                </div>
            </div>
            <div style='background:#fff;border:1px solid #e0e0e0;border-radius:8px;
                        padding:20px;flex:1;min-width:180px;box-shadow:0 1px 4px rgba(0,0,0,0.05);'>
                <div style='color:#e10600;font-size:1.5rem;'>🗺️</div>
                <div style='color:#333;font-weight:600;margin-top:8px;'>Track Map</div>
                <div style='color:#888;font-size:0.82rem;margin-top:4px;'>
                    Speed-coloured circuit map generated from GPS telemetry.
                </div>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ── Load session ──────────────────────────────────────────────────────────
    with st.spinner(f"Loading {loaded['year']} {loaded['event']} — {loaded['session_label']}…"):
        try:
            session = load_session(loaded["year"], loaded["event"], loaded["session_type"])
        except Exception as exc:
            st.error(f"Could not load session: {exc}")
            st.info("Try a different season/event/session, or check your internet connection.")
            return

    drivers = sorted(session.laps["Driver"].unique())
    if not drivers:
        st.warning("No driver data found for this session.")
        return

    # ── Driver / lap selectors ────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns([2, 2, 1])

    with col_a:
        drv1_default = _driver_index(drivers, DEFAULT_DRIVER_1)
        drv1 = st.selectbox("Primary Driver", drivers, index=drv1_default, key="drv1_sel")

    laps1 = session.laps.pick_drivers(drv1)
    valid_laps1 = laps1[laps1["LapTime"].notna()]["LapNumber"].astype(int).tolist()
    if not valid_laps1:
        st.warning(f"No timed laps found for {drv1}.")
        return

    # Initialise lap1 from session state or best lap default
    if "lap1_num" not in st.session_state:
        st.session_state["lap1_num"] = _best_lap_num(laps1) or valid_laps1[-1]

    # Clamp to valid range (new session may have different laps)
    if st.session_state["lap1_num"] not in valid_laps1:
        st.session_state["lap1_num"] = valid_laps1[-1]

    with col_b:
        lap1_num = st.selectbox(
            "Lap",
            valid_laps1,
            index=valid_laps1.index(st.session_state["lap1_num"]),
            key="lap1_sel",
        )
        st.session_state["lap1_num"] = lap1_num

    with col_c:
        if st.button("⚡ Best", key="fast1", use_container_width=True):
            best = _best_lap_num(laps1)
            if best:
                st.session_state["lap1_num"] = best
                st.rerun()

    # Comparison controls
    compare_on = st.checkbox("Compare with another driver / lap", value=True, key="cmp_on")

    drv2, lap2_num = None, None
    if compare_on:
        col_d, col_e, col_f = st.columns([2, 2, 1])

        with col_d:
            drv2_default = _driver_index(drivers, DEFAULT_DRIVER_2)
            drv2 = st.selectbox("Compare Driver", drivers, index=drv2_default, key="drv2_sel")

        laps2 = session.laps.pick_drivers(drv2)
        valid_laps2 = laps2[laps2["LapTime"].notna()]["LapNumber"].astype(int).tolist()

        if not valid_laps2:
            st.warning(f"No timed laps found for {drv2}.")
            compare_on = False
        else:
            # Initialise lap2 from session state or best lap default
            if "lap2_num" not in st.session_state:
                st.session_state["lap2_num"] = _best_lap_num(laps2) or valid_laps2[-1]
            if st.session_state["lap2_num"] not in valid_laps2:
                st.session_state["lap2_num"] = valid_laps2[-1]

            with col_e:
                lap2_num = st.selectbox(
                    "Lap",
                    valid_laps2,
                    index=valid_laps2.index(st.session_state["lap2_num"]),
                    key="lap2_sel",
                )
                st.session_state["lap2_num"] = lap2_num

            with col_f:
                if st.button("⚡ Best", key="fast2", use_container_width=True):
                    best2 = _best_lap_num(laps2)
                    if best2:
                        st.session_state["lap2_num"] = best2
                        st.rerun()

    st.markdown("---")

    # ── Resolve laps ──────────────────────────────────────────────────────────
    lap1_row = laps1[laps1["LapNumber"] == lap1_num].iloc[0]
    color1   = get_team_color(session, drv1)
    team1    = get_team_name(session, drv1)
    full1    = get_driver_full_name(session, drv1)

    color2, team2, full2, lap2_row, laps2 = "#888888", "", "", None, pd.DataFrame()
    if compare_on and drv2 and lap2_num is not None:
        laps2   = session.laps.pick_drivers(drv2)
        lap2_df = laps2[laps2["LapNumber"] == lap2_num]
        lap2_row = lap2_df.iloc[0] if not lap2_df.empty else None
        color2  = get_team_color(session, drv2)
        team2   = get_team_name(session, drv2)
        full2   = get_driver_full_name(session, drv2)

    # ── Metric cards ──────────────────────────────────────────────────────────
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.metric(
            f"🏁 {drv1} — Lap {lap1_num}",
            format_lap_time(lap1_row["LapTime"]),
            delta=team1, delta_color="off",
        )
    with mc2:
        if compare_on and lap2_row is not None:
            st.metric(
                f"🏁 {drv2} — Lap {lap2_num}",
                format_lap_time(lap2_row["LapTime"]),
                delta=f"Δ vs {drv1}: {delta_str(lap2_row['LapTime'], lap1_row['LapTime'])}",
                delta_color="inverse",
            )
    with mc3:
        speed_trap = lap1_row.get("SpeedST") if lap1_row is not None else None
        st.metric("Speed Trap (km/h)",
                  f"{speed_trap:.0f}" if isinstance(speed_trap, float) else "N/A")
    with mc4:
        compound = lap1_row.get("Compound", "N/A") if lap1_row is not None else "N/A"
        st.metric("Compound", str(compound))

    # ── Team logo strip ───────────────────────────────────────────────────────
    teams_to_show = [(team1, color1)]
    if compare_on and team2:
        teams_to_show.append((team2, color2))

    if teams_to_show:
        logo_cols = st.columns(len(teams_to_show) + 6)
        for idx, (team, col) in enumerate(teams_to_show):
            logo_url = TEAM_LOGOS.get(team)
            if logo_url:
                logo_cols[idx].markdown(
                    f"<img src='{logo_url}' style='height:44px;object-fit:contain;"
                    f"filter:drop-shadow(0 0 4px {col}55);'/>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # ── Channel selector ──────────────────────────────────────────────────────
    all_channels = ["Speed", "Throttle", "Brake", "nGear", "RPM", "DRS"]
    selected_channels = st.multiselect(
        "Telemetry channels",
        options=all_channels,
        default=["Speed", "Throttle", "Brake"],
        key="channels",
    )

    # ── Fetch telemetry ───────────────────────────────────────────────────────
    tel1, tel2 = None, None
    with st.spinner("Fetching telemetry…"):
        try:
            tel1 = lap1_row.get_telemetry().add_distance()
        except Exception as e:
            st.warning(f"Telemetry unavailable for {drv1} lap {lap1_num}: {e}")
        try:
            if compare_on and lap2_row is not None:
                tel2 = lap2_row.get_telemetry().add_distance()
        except Exception as e:
            st.warning(f"Telemetry unavailable for {drv2} lap {lap2_num}: {e}")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_tel, tab_map, tab_laps = st.tabs(["📈 Telemetry", "🗺️ Track Map", "📋 Lap Summary"])

    with tab_tel:
        if tel1 is None:
            st.warning("No telemetry data available for the selected lap.")
        elif not selected_channels:
            st.info("Select at least one telemetry channel above.")
        else:
            label1 = f"{drv1} · Lap {lap1_num}"
            label2 = f"{drv2} · Lap {lap2_num}" if compare_on and drv2 else None
            fig = build_telemetry_figure(
                tel1, tel2, label1, label2, color1, color2, selected_channels
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with tab_map:
        if compare_on and tel2 is not None:
            map_mode = st.radio(
                "Colour by", ["Speed", "Time Delta"],
                horizontal=True, key="map_mode",
            )
        else:
            map_mode = "Speed"

        if map_mode == "Time Delta" and compare_on and tel1 is not None and tel2 is not None:
            st.plotly_chart(
                build_delta_track_map(
                    tel1, tel2, drv1, drv2,
                    f"{drv1} vs {drv2} · Laps {lap1_num}/{lap2_num} · Time Delta",
                ),
                use_container_width=True, config={"displayModeBar": False},
            )
        else:
            map_cols = st.columns(2 if compare_on and tel2 is not None else 1)
            with map_cols[0]:
                if tel1 is not None:
                    st.plotly_chart(
                        build_track_map(tel1, color1, f"{drv1} · Lap {lap1_num} · Speed"),
                        use_container_width=True, config={"displayModeBar": False},
                    )
                else:
                    st.info("No telemetry available for track map.")
            if compare_on and tel2 is not None and len(map_cols) > 1:
                with map_cols[1]:
                    st.plotly_chart(
                        build_track_map(tel2, color2, f"{drv2} · Lap {lap2_num} · Speed"),
                        use_container_width=True, config={"displayModeBar": False},
                    )

    with tab_laps:
        st.markdown(f"#### {full1} — all laps")
        st.plotly_chart(build_lap_table(laps1, color1),
                        use_container_width=True, config={"displayModeBar": False})
        if compare_on and drv2 and not laps2.empty:
            st.markdown(f"#### {full2} — all laps")
            st.plotly_chart(build_lap_table(laps2, color2),
                            use_container_width=True, config={"displayModeBar": False})

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        "<p style='color:#aaa;font-size:0.72rem;text-align:center;'>"
        "Data via <a href='https://github.com/theOehrly/Fast-F1' style='color:#bbb;'>FastF1</a> · "
        "F1 and Formula One are trademarks of Formula One Licensing BV"
        "</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
