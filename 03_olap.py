"""STEP 3 - OLAP operations (Roll-up, Drill-down, Slice, Dice, Pivot) on the warehouse. Saves outputs/olap_results.json (+ CSVs)."""
import json, os
import db
from config import OUT
os.makedirs(OUT, exist_ok=True)
J = """FROM vw_fact_clean f JOIN dim_time t ON f.time_key=t.time_key JOIN dim_station s ON f.station_key=s.station_key
JOIN dim_location l ON s.location_key=l.location_key JOIN dim_charger c ON f.charger_key=c.charger_key"""
top_city = db.query(f"SELECT l.city, SUM(f.energy_kwh) e {J} GROUP BY l.city ORDER BY e DESC").iloc[0, 0]
peak_m = int(db.query(f"SELECT t.month, SUM(f.energy_kwh) e {J} GROUP BY t.month ORDER BY e DESC").iloc[0, 0])
last_y = int(db.query(f"SELECT MAX(t.year) y {J}").iloc[0, 0])
ops = {
 "Roll-up (Day->Month->Year): energy by year": (f"SELECT t.year, SUM(f.energy_kwh) AS energy_kwh, COUNT(*) AS sessions {J} GROUP BY t.year ORDER BY t.year", {}),
 "Drill-down (Year->Month): energy by month": (f"SELECT t.year, t.month, SUM(f.energy_kwh) AS energy_kwh {J} WHERE t.year=:y GROUP BY t.year, t.month ORDER BY t.month", {"y": last_y}),
 "Slice (Charger_Type = 'DC Fast')": (f"SELECT c.charger_type, SUM(f.energy_kwh) AS dc_fast_energy {J} WHERE c.charger_type='DC Fast' GROUP BY c.charger_type", {}),
 "Dice (DC Fast + top city + peak month)": (f"SELECT l.city, c.charger_type, t.month, SUM(f.energy_kwh) AS energy_kwh {J} WHERE l.city=:city AND c.charger_type='DC Fast' AND t.month=:m GROUP BY l.city, c.charger_type, t.month", {"city": top_city, "m": peak_m}),
 "Pivot (city rows x charger-type columns)": (f"SELECT l.city, SUM(CASE WHEN c.charger_type='DC Fast' THEN f.energy_kwh END) AS dc_fast, SUM(CASE WHEN c.charger_type='AC' THEN f.energy_kwh END) AS ac {J} GROUP BY l.city ORDER BY l.city", {}),
 "Peak hours (sessions by hour)": (f"SELECT t.hour, COUNT(*) AS sessions, SUM(f.energy_kwh) AS energy_kwh {J} GROUP BY t.hour ORDER BY t.hour", {}),
 "Top 10 stations by energy": (f"SELECT s.station_id, l.city, c.charger_type, SUM(f.energy_kwh) AS energy_kwh, COUNT(*) AS sessions {J} GROUP BY s.station_id, l.city, c.charger_type ORDER BY energy_kwh DESC LIMIT 10", {}),
 "Maintenance: downtime & cost by city": ("SELECT l.city, COUNT(*) AS events, SUM(m.downtime_hours) AS downtime_hours, SUM(m.maintenance_cost) AS cost_inr FROM fact_station_maintenance m JOIN dim_station s ON m.station_key=s.station_key JOIN dim_location l ON s.location_key=l.location_key GROUP BY l.city ORDER BY cost_inr DESC", {}),
}
res = {}
for i, (name, (sql, p)) in enumerate(ops.items(), 1):
    df = db.query(sql, p); res[name] = {"sql": " ".join(sql.split()), "params": p, "rows": json.loads(df.to_json(orient="records"))}
    df.to_csv(f"{OUT}/olap_{i}.csv", index=False)
    print(f"\n=== {name} ==="); print(df.head(12).to_string(index=False))
json.dump(res, open(f"{OUT}/olap_results.json", "w"), indent=2)
