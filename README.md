# EVCharge DW - EV Charging Infrastructure Data Warehouse (CSI3010)
Review 1 (DW + ETL + OLAP) -> Review 2 (K-Means) -> Review 3 (Dashboard + demo). One project, one command.

## Folder map
| File | Purpose | Review |
|---|---|---|
| `01_generate_data.py` | Puts raw CSVs in `data/raw/` (synthetic fallback if you have none) | 1 |
| `schema.sql` | Galaxy schema: 3 facts + 7 dimensions + analysis view | 1 |
| `02_etl.py` | Extract -> clean -> derive -> surrogate keys -> load (dimensions first) + quality report | 1 |
| `03_olap.py` | Roll-up, drill-down, slice, dice, pivot, peak hours, top stations | 1 |
| `04_kmeans.py` | K-Means (K=3) + elbow/silhouette, saves clusters back into the DW | 2 |
| `app.py` + `static/index.html` | Flask REST backend + 5-tab dashboard | 3 |
| `config.py`, `db.py` | Settings (DB URL, tariff) and DB access layer | - |

## Run it in Google Antigravity (step by step)
1. Install Python 3.10+ (python.org, tick "Add to PATH") and Antigravity.
2. Unzip `evcharge_dw.zip`. In Antigravity: **File > Open Folder** -> select the `evcharge_dw` folder.
3. Open the terminal (**Ctrl + `**) and run:
   ```
   python -m venv .venv
   .venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   python 00_run_all.py            # data -> ETL -> OLAP -> K-Means (about 1 minute)
   python app.py                   # then open http://127.0.0.1:5000
   ```
4. Open the dashboard in the Antigravity browser or any browser. Stop the server with Ctrl+C.
5. Optional: open the **Agent Manager** and paste the prompt in `ANTIGRAVITY_PROMPT.md` to let the agent extend or debug the project.

Run steps individually if you prefer: `python 01_generate_data.py`, `python 02_etl.py`, `python 03_olap.py`, `python 04_kmeans.py`.
Results appear in `outputs/` (CSVs, `quality_report.json`, `kmeans_clusters.png`, `kmeans_elbow_silhouette.png`, `olap_results.json`).

## Using your REAL data (important for marks)
Without real files the project runs on **synthetic** data (labelled as such). To use real data, put these in `data/raw/` BEFORE running:
- `acn_sessions.csv` - columns `sessionID, stationID, userID, connectionTime, disconnectTime, kWhDelivered` (+ optional `make, model, powertrain, segment, user_type`). Real ACN data: https://ev.caltech.edu/dataset (needs a free API token), or export from your Kaggle file.
- `charging_station.csv` - columns `id, name, city, state, country, latitude, longitude, charger_type (AC / DC Fast), power_kw, ports`; `stationID` in sessions must match `id`.
- If `payments.csv` / `maintenance.csv` are absent, they are created as **synthetic** (as declared in Review 1).
Rename your columns to these names (a 5-line pandas `rename` is enough). Delete `evcharge_dw.db` and re-run `python 00_run_all.py`.
Then re-state the real numbers in your slides - the Review 2 PPT numbers (180 stations, silhouette 0.364) came from a different synthetic run.

## Use PostgreSQL instead of SQLite (matches your Review 1 slides)
```
pip install psycopg2-binary
createdb evcharge_dw
set DB_URL=postgresql+psycopg2://postgres:YOUR_PWD@localhost:5432/evcharge_dw     (Mac/Linux: export DB_URL=...)
python 00_run_all.py && python app.py
```

## Design decisions to mention in the viva
- **Grain** of the main fact = one charging session. `fact_energy_consumption` = station x day. `fact_station_maintenance` = maintenance event.
- **Galaxy schema**: 3 facts share `dim_time`, `dim_station`, `dim_charger`. Station -> Location is snowflaked (City -> State -> Country).
- **Derived**: `Duration_Minutes` (disconnect - connect), `Amount` = kWh x tariff (AC Rs12, DC Fast Rs18 per kWh - an assumption in `config.py`).
- **Time**: UTC converted to IST; `time_key = YYYYMMDDHH`.
- **Outliers** (kWh > 150, duration > 24 h, implied power > 1.5 x charger power) are FLAGGED (`outlier_flag`) and excluded through view `vw_fact_clean`; negative kWh / non-positive duration rows are removed.
- **K-Means**: 5 scaled features, K=3 (kept from Review 2) validated with silhouette/elbow; cluster IDs are arbitrary so clusters are labelled Lower/Medium/Higher by mean total energy. Exploratory, not ground truth. `power_kw` strongly influences clusters (AC vs DC).

## Review 3 demo script (about 5 min)
1. `python 00_run_all.py` output: quality report + validation line "energy_matches_source True".
2. Dashboard **Overview**: KPIs, roll-up (year), drill-down (month), peak hours (morning and evening peaks), city/charger mix.
3. **OLAP Explorer**: click Roll-up -> Drill-down -> Slice -> Dice (pick city + DC Fast + month) -> Pivot; show the generated SQL.
4. **Data Mining**: cluster scatter, profile table, silhouette/elbow, cluster by city.
5. **Maintenance** and **Data Quality** tabs; close with limitations (synthetic payment/maintenance, K-Means is exploratory).

## Troubleshooting
- `ModuleNotFoundError` -> venv not activated or `pip install -r requirements.txt` not run.
- Charts empty / blank page -> the page loads Chart.js from cdnjs, so internet is required; check the terminal for Flask errors.
- Port busy -> change `port=5000` in `app.py`.
- Re-running ETL rebuilds all tables (schema.sql drops and recreates them).
