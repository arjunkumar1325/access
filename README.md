# AccessAI — Intelligent Accessible Route Planning

> **Google Maps-Style Wheelchair Accessible Navigation System**  
> An independent navigation platform that prioritizes accessibility over pure distance: avoiding stairs, blocked paths, and rough surfaces while integrating community barrier reporting and AI-assisted photo classification.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/arjunkumar1325/access)

---

## ♿ Features

- **Google Maps-Inspired Navigation UI**: Clean, high-contrast, responsive interface built with HTML5, CSS3, Vanilla JS, and Leaflet.js with OpenStreetMap.
- **Intelligent Accessible Routing**:
  - Automatically calculates routes prioritizing ramps and smooth paths.
  - Applies a heavy cost penalty to mapped stairs (`highway=steps`) and `wheelchair=no` pathways.
  - Applies penalties to rough surfaces (`gravel`, `sand`, `dirt`, `cobblestone`).
  - Automatically detours around active community-reported barriers.
- **Route Comparison**:
  - Compares the **Accessible Route** against the **Standard Shortest Route**.
  - Displays walking/wheeling time, total distance in meters/kilometers, and exact count of stair flights avoided.
- **Community Barrier Reporting**:
  - Report stairs, construction, broken ramps, and blocked footpaths.
  - Click on the map to automatically capture coordinates.
  - Optional photo evidence upload.
  - Persistent SQLite storage via SQLAlchemy.
  - Real-time route recalculation when barriers are reported or marked resolved.
- **AI Accessibility Photo Scanner**:
  - On-demand zero-shot image classification (CLIP) to detect stairs, ramps, obstacles, and clear footpaths.
  - Graceful fallback when machine learning dependencies are offline.
- **Honest Accessibility Disclaimers**: Transparent warnings about unmapped curbs, slopes, and missing OpenStreetMap tags.

---

## 👥 Team Module Architecture

| Module | Team Member | Responsibility | Key Functions |
|---|---|---|---|
| `graph.py` | Member 1 | Map Data & Walking Network | `load_graph()`, `get_graph_bounds()` |
| `routing.py` | Member 2 | Accessible Routing Engine | `add_costs(G)`, `get_route(G, start, end)`, `get_route_details()` |
| `app.py`, `templates/`, `static/` | Member 3 | Web Application & Interactive UI | Flask app, REST API, Leaflet UI, modals |
| `vision.py` | Member 4 | AI Image Recognition | `analyze(path)`, `is_ai_available()` |
| `barriers.py` | Member 5 | Barrier Reporting & Penalties | `add_barrier()`, `apply_barrier()`, `apply_all()`, `resolve_barrier()` |
| `tests/` | Member 6 | Testing, Verification & Demo | Automated API and integration test suite |

---

## 🚀 Quick Start Guide (Windows PowerShell)

Follow these beginner-friendly steps to run AccessAI on Windows:

### 1. Open Project in Terminal
Open Windows PowerShell and navigate to the project directory:
```powershell
cd "c:\Users\Arjun Kumar A S\OneDrive\Desktop\ibm"
```

### 2. Activate the Virtual Environment
A Python virtual environment (`venv`) is already configured:
```powershell
.\venv\Scripts\Activate.ps1
```
*(If PowerShell displays an execution policy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and retry).*

### 3. Install Dependencies (If setting up fresh)
```powershell
pip install -r requirements.txt
```

### 4. Walking Graph Data
A pre-loaded campus walking network is already cached as `map.graphml` (383 nodes, 1042 walking edges).  
If you want to download a different campus or neighborhood, configure `ACCESSAI_PLACE` in `.env` or pass coordinates to `graph.py`:
```powershell
python graph.py
```

### 5. Start the AccessAI Web Application
```powershell
python app.py
```
You will see output similar to:
```
Loading walking graph and initializing accessibility weights...
Graph loaded successfully: 383 nodes, 1042 edges.
 * Running on http://127.0.0.1:5000 (Press CTRL+C to quit)
```

### 6. Open in Your Browser
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🧪 Running Automated Tests

Run the comprehensive integration test suite:
```powershell
.\venv\Scripts\python.exe -m unittest tests/test_api.py
```
This tests:
- `GET /api/health`: Health status & walking graph stats.
- `GET /api/barriers`: Fetching active community barriers.
- `POST /api/barriers`: Submitting and validating barrier reports.
- `PATCH /api/barriers/<id>`: Resolving barrier reports.
- `POST /api/route`: Computing accessible vs shortest routes.
- Input validation and coordinate boundary checking.

---

## 📡 REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check, graph stats, and AI readiness |
| `GET` | `/api/barriers` | Fetch active barrier reports |
| `POST` | `/api/barriers` | Submit a new barrier report (`lat`, `lon`, `category`, `note`, optional photo) |
| `PATCH` | `/api/barriers/<id>` | Update barrier status (e.g. `{"status": "resolved"}`) |
| `POST` | `/api/route` | Calculate accessible route between `start` and `end` coordinates |
| `POST` | `/api/analyze-image` | Classify uploaded obstacle photo via CLIP zero-shot model |

---

## 🤖 Optional AI Classifier Setup (Member 4)

The main route planning application runs completely independently without requiring large AI model downloads. To enable the optional zero-shot CLIP vision classifier:

```powershell
pip install transformers torch
```
On first scan, the model weights (`openai/clip-vit-base-patch32`, ~350 MB) will download and cache automatically.

---

## ⚠️ Important Accessibility Disclaimer

AccessAI uses OpenStreetMap walking data and community reports to highlight accessible routes. OpenStreetMap tags may be incomplete or outdated; not all curbs, steep grades, missing ramps, or surface irregularities are recorded. **Never guarantee a route is 100% accessible based solely on map data or AI predictions.**
