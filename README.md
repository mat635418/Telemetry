# 🏎️ F1 Telemetry Dashboard

A professional, dark-mode **Streamlit** web app that fetches real public Formula 1 telemetry data and lets you explore **every lap of every driver** across past and current F1 seasons — speed traces, throttle, braking, gear shifts, RPM, DRS, delta time comparison, and a GPS-based speed-coloured track map.

> Data is sourced entirely from the open-source [FastF1](https://github.com/theOehrly/Fast-F1) library, which pulls official F1 timing data.

---

## ✨ Features

| Feature | Details |
|---|---|
| 📅 Season / Event / Session picker | Any season from 2018 onward — Race, Qualifying, Sprint, Practice |
| 🏁 Driver & lap selector | Every driver, every lap; "⚡ Fastest" shortcut button |
| 📈 Telemetry overlay | Speed · Throttle · Brake · Gear · RPM · DRS vs. distance |
| ⚡ Head-to-head comparison | Two drivers or two laps overlaid with cumulative Δ delta row |
| 🗺️ Speed-coloured track map | GPS X/Y coordinates coloured by speed (red = fast, blue = slow) |
| 📋 Lap summary table | All laps with sector times, compounds, tyre age and speed traps |
| 🎨 Dark-mode UI | Professional #0d0d0d theme with F1 team colours and logos |
| 💾 Local caching | FastF1 caches session data to `f1_cache/` so replays are instant |

---

## 🖥️ Preview

```
Season ▾   Grand Prix ▾   Session ▾   [Load Session]

F1 Telemetry Dashboard
──────────────────────────────────────────────────
  VER · Lap 42          NOR · Lap 38
  1:17.145              1:17.289  Δ +0.144s

[📈 Telemetry]  [🗺️ Track Map]  [📋 Lap Summary]

 Speed ──────────────────────────────────────────
   km/h                               VER ── NOR ···
 300 ┤╭──╮    ╭╮   ╭──────╮   ╭╮╭─
 200 ┤│  ╰────╯╰───╯      ╰───╯╰╯
 100 ┤
     0        500       1000      1500     2000  m
```

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/mat635418/Telemetry.git
cd Telemetry
```

### 2. Create and activate a virtual environment (recommended)

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
streamlit run app.py
```

The app opens automatically at **http://localhost:8501**.

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `fastf1 ≥ 3.3` | F1 timing & telemetry data |
| `streamlit ≥ 1.35` | Web framework |
| `plotly ≥ 5.22` | Interactive charts |
| `pandas ≥ 2.1` | Data manipulation |
| `numpy ≥ 1.26` | Numerical operations |
| `matplotlib ≥ 3.8` | Fallback / colour utilities |
| `Pillow ≥ 10.3` | Image handling |
| `requests ≥ 2.31` | HTTP (logo fetching) |

---

## 🗂️ Project Structure

```
Telemetry/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── f1_cache/           # Auto-created FastF1 cache directory
```

---

## 🔧 How It Works

### Data Flow

```
User selects year / event / session
        │
        ▼
fastf1.get_event_schedule()   ← list all GPs
        │
        ▼
fastf1.get_session().load()   ← download laps + telemetry
        │
        ├── session.laps.pick_drivers(drv)
        │         └── lap_row.get_telemetry().add_distance()
        │                   → DataFrame: Time, Distance, Speed,
        │                                Throttle, Brake, nGear, RPM, DRS, X, Y
        │
        └── Plotly figures   → Streamlit st.plotly_chart()
```

### Telemetry Channels

| Channel | Unit | Description |
|---|---|---|
| Speed | km/h | Car speed from GPS / transponder |
| Throttle | % (0–100) | Throttle pedal position |
| Brake | bool/float | Brake pedal application |
| nGear | 1–8 | Current gear |
| RPM | rpm | Engine revolutions per minute |
| DRS | 0/1/8/10/12/14 | DRS status (>9 = open) |

### Delta Time Calculation

The cumulative Δ is computed by interpolating the comparison lap's speed trace onto the primary lap's distance grid and numerically integrating:

```
Δt(d) = Σ Δd · (1/v₁ − 1/v₂) × 3.6
```

A positive Δ means the comparison driver is **slower** at that point.

### Track Map

Car GPS coordinates (`X`, `Y`) from telemetry are plotted as a polyline. Each segment is coloured on a blue → red scale mapped to `[80, 330]` km/h.

---

## 🎨 Customisation

### Adding team colours / logos

Edit the `TEAM_COLORS` and `TEAM_LOGOS` dictionaries at the top of `app.py`:

```python
TEAM_COLORS["My Team"] = "#FF0000"
TEAM_LOGOS["My Team"] = "https://example.com/logo.png"
```

### Changing the cache directory

```python
CACHE_DIR = Path("/mnt/fast-ssd/f1_cache")
```

### Dark theme toggle

The entire CSS is injected via `st.markdown()` at startup. Override any colour variable there.

---

## ⚠️ Notes & Limitations

* **Data availability**: FastF1 data is available from the **2018 season** onward. Earlier events are not supported.
* **First load**: The first time a session is loaded it is downloaded from the Ergast/F1 API and cached locally. Subsequent loads are instant.
* **Cache size**: A full race weekend is typically **50–200 MB** on disk. Delete `f1_cache/` freely to reclaim space.
* **Network**: An active internet connection is required for the first load of each session.
* **Telemetry completeness**: Not every lap has full telemetry (out/in laps, pit laps, red-flag laps). These are still selectable but some channels may be empty.

---

## 📜 Licence

MIT — see [LICENSE](LICENSE) for details.

---

## 🙏 Credits

* **[FastF1](https://github.com/theOehrly/Fast-F1)** by Oehrly — the extraordinary library that makes all of this possible.
* F1 timing data © Formula One Management Ltd.
* Team logos are trademarks of their respective constructor organisations.

---

*Formula One, F1, and all associated marks are trademarks of Formula One Licensing BV.*
