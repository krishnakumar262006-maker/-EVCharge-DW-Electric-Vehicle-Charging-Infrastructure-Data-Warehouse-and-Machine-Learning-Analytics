"""STEP 5 (Review 3) - Flask backend: REST API on top of the Data Warehouse + serves the dashboard.  Run: python app.py"""
import json, os
from flask import Flask, jsonify, request, send_from_directory
import db
from config import OUT

app = Flask(__name__, static_folder="static")
FROM = """FROM vw_fact_clean f JOIN dim_time t ON f.time_key=t.time_key JOIN dim_station s ON f.station_key=s.station_key
JOIN dim_location l ON s.location_key=l.location_key JOIN dim_charger c ON f.charger_key=c.charger_key
JOIN dim_vehicle v ON f.vehicle_key=v.vehicle_key JOIN dim_payment p ON f.payment_key=p.payment_key"""
M = "SUM(f.energy_kwh) AS energy_kwh, COUNT(*) AS sessions, SUM(f.amount) AS revenue_inr, AVG(f.duration_minutes) AS avg_duration"
FILTERS = [("year", "t.year", int), ("month", "t.month", int), ("city", "l.city", str), ("charger_type", "c.charger_type", str)]
QUERIES = {
    "kpis":        f"SELECT {M}, COUNT(DISTINCT f.station_key) AS stations {{F}} {{W}}",
    "rollup":      f"SELECT t.year, {M} {{F}} {{W}} GROUP BY t.year ORDER BY t.year",
    "drilldown":   f"SELECT t.year, t.month, {M} {{F}} {{W}} GROUP BY t.year, t.month ORDER BY t.year, t.month",
    "daily":       f"SELECT t.full_date, {M} {{F}} {{W}} GROUP BY t.full_date ORDER BY t.full_date",
    "hourly":      f"SELECT t.hour, {M} {{F}} {{W}} GROUP BY t.hour ORDER BY t.hour",
    "city":        f"SELECT l.city, {M} {{F}} {{W}} GROUP BY l.city ORDER BY energy_kwh DESC",
    "charger":     f"SELECT c.charger_type, {M} {{F}} {{W}} GROUP BY c.charger_type ORDER BY energy_kwh DESC",
    "slice":       f"SELECT c.charger_type, {M} {{F}} {{W}} GROUP BY c.charger_type",
    "dice":        f"SELECT l.city, c.charger_type, t.month, {M} {{F}} {{W}} GROUP BY l.city, c.charger_type, t.month ORDER BY energy_kwh DESC LIMIT 50",
    "top_stations":f"SELECT s.station_id, l.city, c.charger_type, {M} {{F}} {{W}} GROUP BY s.station_id, l.city, c.charger_type ORDER BY energy_kwh DESC LIMIT 10",
    "vehicle":     f"SELECT v.make || ' ' || v.model AS vehicle, v.powertrain, {M} {{F}} {{W}} GROUP BY v.make, v.model, v.powertrain ORDER BY sessions DESC LIMIT 10",
    "payment":     f"SELECT p.payment_type, {M} {{F}} {{W}} GROUP BY p.payment_type ORDER BY sessions DESC",
}

def rows(sql, p=None):
    return json.loads(db.query(sql, p or {}).to_json(orient="records"))

def where(defaults=None):
    cl, p = [], {}
    for arg, col, cast in FILTERS:
        v = request.args.get(arg)
        if v in (None, "", "all"):
            v = (defaults or {}).get(arg)
        if v not in (None, "", "all"):
            cl.append(f"{col} = :{arg}"); p[arg] = cast(v)
    return ("WHERE " + " AND ".join(cl)) if cl else "", p

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/outputs/<path:f>")
def outputs(f):
    return send_from_directory(OUT, f)

@app.route("/api/meta")
def meta():
    return jsonify(years=[r["year"] for r in rows("SELECT DISTINCT year FROM dim_time ORDER BY year")],
                   cities=[r["city"] for r in rows("SELECT DISTINCT city FROM dim_location ORDER BY city")],
                   charger_types=[r["charger_type"] for r in rows("SELECT DISTINCT charger_type FROM dim_charger ORDER BY charger_type")])

@app.route("/api/q/<name>")
def q(name):
    if name not in QUERIES:
        return jsonify(error="unknown query"), 404
    w, p = where({"charger_type": "DC Fast"} if name == "slice" else None)
    sql = " ".join(QUERIES[name].format(F=FROM, W=w).split())
    return jsonify(sql=sql, params=p, rows=rows(sql, p))

@app.route("/api/pivot")
def pivot():
    types = [r["charger_type"] for r in rows("SELECT DISTINCT charger_type FROM dim_charger ORDER BY charger_type")]
    cols = ", ".join(f"SUM(CASE WHEN c.charger_type='{t.replace(chr(39), '')}' THEN f.energy_kwh END) AS \"{t}\"" for t in types)
    w, p = where()
    sql = f"SELECT l.city, {cols} {FROM} {w} GROUP BY l.city ORDER BY l.city"
    return jsonify(sql=" ".join(sql.split()), params=p, rows=rows(sql, p), columns=["city"] + types)

@app.route("/api/clusters")
def clusters():
    mfile = os.path.join(OUT, "kmeans_metrics.json")
    return jsonify(summary=rows("SELECT * FROM cluster_summary ORDER BY mean_total_energy_kwh"),
                   stations=rows("SELECT station_id, city, charger_type, power_kw, session_count, total_energy_kwh, avg_energy_kwh, avg_duration_minutes, cluster_id, cluster_label FROM station_clusters"),
                   by_city=rows("SELECT city, cluster_label, COUNT(*) AS stations FROM station_clusters GROUP BY city, cluster_label ORDER BY city"),
                   by_charger=rows("SELECT charger_type, cluster_label, COUNT(*) AS stations FROM station_clusters GROUP BY charger_type, cluster_label"),
                   metrics=json.load(open(mfile)) if os.path.exists(mfile) else {})

@app.route("/api/maintenance")
def maintenance():
    J = "FROM fact_station_maintenance m JOIN dim_time t ON m.time_key=t.time_key JOIN dim_station s ON m.station_key=s.station_key JOIN dim_location l ON s.location_key=l.location_key"
    agg = "COUNT(*) AS events, SUM(m.downtime_hours) AS downtime_hours, SUM(m.maintenance_cost) AS cost_inr"
    return jsonify(by_year=rows(f"SELECT t.year, {agg} {J} GROUP BY t.year ORDER BY t.year"),
                   by_issue=rows(f"SELECT m.issue_type, {agg} {J} GROUP BY m.issue_type ORDER BY cost_inr DESC"),
                   top_stations=rows(f"SELECT s.station_id, l.city, {agg} {J} GROUP BY s.station_id, l.city ORDER BY downtime_hours DESC LIMIT 10"))

@app.route("/api/quality")
def quality():
    tables = ["dim_time", "dim_location", "dim_charger", "dim_station", "dim_vehicle", "dim_user", "dim_payment",
              "fact_charging_transaction", "fact_energy_consumption", "fact_station_maintenance"]
    counts = {t: int(db.query(f"SELECT COUNT(*) AS n FROM {t}").iloc[0, 0]) for t in tables}
    rep = json.load(open(os.path.join(OUT, "quality_report.json")))
    return jsonify(report={k: v for k, v in rep.items() if not k.startswith("loaded_")}, table_counts=counts)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
