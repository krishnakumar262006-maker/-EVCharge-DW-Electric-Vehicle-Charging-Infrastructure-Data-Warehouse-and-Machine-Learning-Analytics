"""STEP 2 - ETL: Extract raw CSVs -> Transform (clean, standardise, derive, surrogate keys) -> Load DW (dimensions first)."""
import json, os
import numpy as np, pandas as pd
from config import RAW, OUT, SCHEMA, TARIFF_INR, DEFAULT_TARIFF
import db

os.makedirs(OUT, exist_ok=True)
Q = {}  # data-quality report

# ------------------------------------------------------------------ EXTRACT
acn = pd.read_csv(f"{RAW}/acn_sessions.csv"); st = pd.read_csv(f"{RAW}/charging_station.csv")
pay = pd.read_csv(f"{RAW}/payments.csv");      mnt = pd.read_csv(f"{RAW}/maintenance.csv")
Q["raw_session_rows"], Q["raw_station_rows"], Q["raw_columns_sessions"] = len(acn), len(st), acn.shape[1]

# ------------------------------------------------------------------ TRANSFORM: stations
Q["duplicate_station_rows"] = int(st.duplicated("id").sum())
Q["missing_city_stations"] = int(st["city"].isna().sum())
st = st.drop_duplicates("id").copy()
for c in ["city", "state", "country", "name"]:
    st[c] = st[c].fillna("Unknown")
for c in ["latitude", "longitude", "power_kw", "ports"]:
    st[c] = pd.to_numeric(st[c], errors="coerce")
bad_geo = ~st.latitude.between(-90, 90) | ~st.longitude.between(-180, 180)
Q["invalid_lat_lon"] = int(bad_geo.sum()); st.loc[bad_geo, ["latitude", "longitude"]] = np.nan
st["charger_type"] = st["charger_type"].fillna("Unknown").str.strip()

# ------------------------------------------------------------------ TRANSFORM: sessions
for c in ["connectionTime", "disconnectTime"]:
    acn[c] = pd.to_datetime(acn[c], utc=True, errors="coerce", format="mixed")
acn["kWhDelivered"] = pd.to_numeric(acn["kWhDelivered"], errors="coerce")
Q["missing_kwh"] = int(acn.kWhDelivered.isna().sum())
Q["missing_timestamps"] = int(acn[["connectionTime", "disconnectTime"]].isna().any(axis=1).sum())
Q["duplicate_session_ids"] = int(acn.duplicated("sessionID").sum())
Q["missing_vehicle_info"] = int(acn["make"].isna().sum())
acn = acn.drop_duplicates("sessionID")
acn = acn.dropna(subset=["sessionID", "stationID", "connectionTime", "disconnectTime", "kWhDelivered"]).copy()
for c in ["make", "model", "powertrain", "segment", "user_type"]:
    if c not in acn: acn[c] = "Unknown"
    acn[c] = acn[c].fillna("Unknown")
for c in ["connectionTime", "disconnectTime"]:       # UTC -> local time (IST), drop tz
    acn[c] = acn[c].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
acn["Duration_Minutes"] = (acn.disconnectTime - acn.connectionTime).dt.total_seconds() / 60
bad = (acn.kWhDelivered < 0) | (acn.Duration_Minutes <= 0)
Q["invalid_rows_removed(neg kWh / duration<=0)"] = int(bad.sum()); acn = acn[~bad]
n0 = len(acn)
acn = acn.merge(st[["id", "power_kw", "charger_type"]], left_on="stationID", right_on="id", how="inner")
Q["sessions_without_station_removed"] = n0 - len(acn)
implied = acn.kWhDelivered / (acn.Duration_Minutes / 60)
acn["outlier_flag"] = ((acn.kWhDelivered > 150) | (acn.Duration_Minutes > 1440) | (implied > 1.5 * acn.power_kw)).astype(int)
Q["outliers_flagged_not_dropped"] = int(acn.outlier_flag.sum())
acn["Amount"] = (acn.kWhDelivered * acn.charger_type.map(TARIFF_INR).fillna(DEFAULT_TARIFF)).round(2)  # DERIVED (INR)
pay = pay.drop_duplicates("sessionID")
acn = acn.merge(pay, on="sessionID", how="left"); acn["Payment_Type"] = acn["Payment_Type"].fillna("Unknown")
Q["clean_session_rows"] = len(acn)

# ------------------------------------------------------------------ DIMENSIONS (surrogate keys)
y0, y1 = int(acn.connectionTime.dt.year.min()), int(acn.connectionTime.dt.year.max())
d = pd.DataFrame({"ts": pd.date_range(f"{y0}-01-01", f"{y1}-12-31 23:00", freq="h")})
dim_time = pd.DataFrame({"time_key": d.ts.dt.strftime("%Y%m%d%H").astype("int64"),
    "full_date": d.ts.dt.strftime("%Y-%m-%d"), "day": d.ts.dt.day, "month": d.ts.dt.month,
    "quarter": d.ts.dt.quarter, "year": d.ts.dt.year, "hour": d.ts.dt.hour,
    "day_of_week": d.ts.dt.dayofweek, "weekend_flag": (d.ts.dt.dayofweek >= 5).astype(int)})

dim_location = st[["city", "state", "country", "latitude", "longitude"]].drop_duplicates().reset_index(drop=True)
dim_location.insert(0, "location_key", dim_location.index + 1)

def pclass(p):
    return "Low (<=11kW)" if p <= 11 else "Medium (12-22kW)" if p <= 22 else "High (23-60kW)" if p <= 60 else "Ultra (>60kW)"
dim_charger = st[["charger_type", "power_kw", "ports"]].drop_duplicates().reset_index(drop=True)
dim_charger.insert(0, "charger_key", dim_charger.index + 1)
dim_charger["power_class"] = dim_charger.power_kw.map(pclass)
dim_charger["fast_dc_flag"] = dim_charger.charger_type.str.contains("DC").astype(int)
dim_charger = dim_charger[["charger_key", "charger_type", "power_class", "power_kw", "ports", "fast_dc_flag"]]

s2 = st.merge(dim_location, on=["city", "state", "country", "latitude", "longitude"], how="left") \
       .merge(dim_charger[["charger_key", "charger_type", "power_kw", "ports"]], on=["charger_type", "power_kw", "ports"], how="left")
dim_station = pd.DataFrame({"station_key": range(1, len(s2) + 1), "station_id": s2["id"].values,
                            "station_name": s2["name"].values, "location_key": s2.location_key.values,
                            "charger_key": s2.charger_key.values})
vcols = ["make", "model", "powertrain", "segment"]
dim_vehicle = acn[vcols].drop_duplicates().reset_index(drop=True); dim_vehicle.insert(0, "vehicle_key", dim_vehicle.index + 1)
dim_user = acn[["userID", "user_type"]].drop_duplicates("userID").reset_index(drop=True)
dim_user.insert(0, "user_key", dim_user.index + 1); dim_user = dim_user.rename(columns={"userID": "user_id"})
dim_payment = acn[["Payment_Type"]].drop_duplicates().reset_index(drop=True)
dim_payment.insert(0, "payment_key", dim_payment.index + 1); dim_payment = dim_payment.rename(columns={"Payment_Type": "payment_type"})

# ------------------------------------------------------------------ FACTS
f = acn.merge(dim_station[["station_key", "station_id", "charger_key"]], left_on="stationID", right_on="station_id") \
       .merge(dim_vehicle, on=vcols).merge(dim_user, left_on="userID", right_on="user_id") \
       .merge(dim_payment, left_on="Payment_Type", right_on="payment_type")
f["time_key"] = f.connectionTime.dt.strftime("%Y%m%d%H").astype("int64")
fact_tx = pd.DataFrame({"transaction_key": range(1, len(f) + 1), "session_id": f.sessionID.values,
    "time_key": f.time_key.values, "vehicle_key": f.vehicle_key.values, "station_key": f.station_key.values,
    "charger_key": f.charger_key.values, "user_key": f.user_key.values, "payment_key": f.payment_key.values,
    "energy_kwh": f.kWhDelivered.round(3).values, "duration_minutes": f.Duration_Minutes.round(2).values,
    "amount": f.Amount.values, "outlier_flag": f.outlier_flag.values})

g = f[f.outlier_flag == 0].copy(); g["day_key"] = g.connectionTime.dt.strftime("%Y%m%d").astype("int64") * 100
agg = g.groupby(["day_key", "station_key"]).agg(energy_kwh=("kWhDelivered", "sum"), session_count=("sessionID", "count"),
                                                hours=("Duration_Minutes", lambda s: s.sum() / 60)).reset_index()
fact_energy = pd.DataFrame({"energy_key": range(1, len(agg) + 1), "time_key": agg.day_key.values, "station_key": agg.station_key.values,
    "energy_kwh": agg.energy_kwh.round(3).values, "session_count": agg.session_count.values,
    "avg_power_kw": (agg.energy_kwh / agg.hours).round(3).values})

mnt["date"] = pd.to_datetime(mnt["date"], errors="coerce")
mnt = mnt.dropna(subset=["date"]).merge(dim_station[["station_key", "station_id"]], left_on="stationID", right_on="station_id")
mnt = mnt[mnt.date.dt.year.between(y0, y1)]
fact_mnt = pd.DataFrame({"maintenance_key": range(1, len(mnt) + 1), "time_key": mnt.date.dt.strftime("%Y%m%d").astype("int64").values * 100,
    "station_key": mnt.station_key.values, "issue_type": mnt.issue_type.values,
    "downtime_hours": pd.to_numeric(mnt.Downtime_Hours).values, "maintenance_cost": pd.to_numeric(mnt.Maintenance_Cost).values})

# ------------------------------------------------------------------ LOAD (create schema, dimensions first, then facts)
with open(SCHEMA) as fh:
    db.run_script(fh.read())
for name, df in [("dim_time", dim_time), ("dim_location", dim_location), ("dim_charger", dim_charger), ("dim_station", dim_station),
                 ("dim_vehicle", dim_vehicle), ("dim_user", dim_user), ("dim_payment", dim_payment),
                 ("fact_charging_transaction", fact_tx), ("fact_energy_consumption", fact_energy), ("fact_station_maintenance", fact_mnt)]:
    db.write_df(df, name); Q[f"loaded_{name}"] = len(df); print(f"loaded {name:28s} {len(df):>8,} rows")

# ------------------------------------------------------------------ VALIDATE
chk = db.query("SELECT SUM(energy_kwh) AS e, COUNT(*) AS n FROM vw_fact_clean").iloc[0]
Q["validation_energy_clean_kwh"] = round(float(chk.e), 2); Q["validation_clean_sessions"] = int(chk.n)
Q["validation_energy_matches_source"] = bool(abs(float(chk.e) - g.kWhDelivered.sum()) < 1)
json.dump(Q, open(f"{OUT}/quality_report.json", "w"), indent=2)
print("\nDATA QUALITY REPORT"); [print(f"  {k:48s} {v}") for k, v in Q.items() if not k.startswith("loaded_")]
