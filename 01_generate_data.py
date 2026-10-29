"""STEP 1 - Raw data.
If you already have the REAL data, put these files in data/raw/ and this script does nothing:
   acn_sessions.csv, charging_station.csv, payments.csv, maintenance.csv
Otherwise it generates a SYNTHETIC dataset with the same schema (58,643 sessions, 180 stations, 2020-2025)
including deliberate dirty data (duplicates, nulls, outliers) so the ETL has something to clean.
The synthetic status MUST be stated in your report/demo."""
import os, sys
import numpy as np, pandas as pd
from config import RAW

def main(force=False):
    os.makedirs(RAW, exist_ok=True)
    need = ["acn_sessions.csv", "charging_station.csv", "payments.csv", "maintenance.csv"]
    if not force and all(os.path.exists(os.path.join(RAW, f)) for f in need):
        print("Raw files already present -> skipping generation."); return
    have = lambda f: os.path.exists(os.path.join(RAW, f))
    if not force and have("acn_sessions.csv") and have("charging_station.csv"):
        # REAL sessions + stations supplied -> only create the SYNTHETIC payment & maintenance files (as in Review 1)
        r = np.random.default_rng(7)
        a = pd.read_csv(f"{RAW}/acn_sessions.csv", usecols=["sessionID"]).drop_duplicates()
        s_ = pd.read_csv(f"{RAW}/charging_station.csv").drop_duplicates("id")
        pd.DataFrame({"sessionID": a.sessionID, "Payment_Type": r.choice(["UPI","Card","Wallet","Subscription"], len(a), p=[.5,.25,.15,.10])}).to_csv(f"{RAW}/payments.csv", index=False)
        rows = [(i, (pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(r.integers(0, 2191)))).strftime("%Y-%m-%d"),
                 r.choice(["Connector fault","Network outage","Payment module","Cable wear","Software update","Cooling fault"]),
                 round(float(r.gamma(2, 4)), 2), round(float(r.lognormal(8.2, .6)), 2)) for i in s_.id for _ in range(r.poisson(8))]
        pd.DataFrame(rows, columns=["stationID","date","issue_type","Downtime_Hours","Maintenance_Cost"]).to_csv(f"{RAW}/maintenance.csv", index=False)
        print("Real sessions/stations found -> created SYNTHETIC payments.csv and maintenance.csv"); return
    rng = np.random.default_rng(42)
    N, NS = 58643, 180
    cities = [("Chennai","Tamil Nadu",13.0827,80.2707),("Bengaluru","Karnataka",12.9716,77.5946),
              ("Hyderabad","Telangana",17.3850,78.4867),("Mumbai","Maharashtra",19.0760,72.8777),
              ("Delhi","Delhi",28.6139,77.2090),("Pune","Maharashtra",18.5204,73.8567),
              ("Kolkata","West Bengal",22.5726,88.3639),("Ahmedabad","Gujarat",23.0225,72.5714)]
    cidx = rng.choice(len(cities), NS, p=[.18,.17,.13,.14,.14,.10,.07,.07])
    ctype = rng.choice(["AC", "DC Fast"], NS, p=[.55, .45])
    power = np.where(ctype == "AC", rng.choice([7.4, 11, 22], NS, p=[.5, .3, .2]),
                     rng.choice([30, 60, 120], NS, p=[.4, .4, .2]))
    areas = ["Mall","Airport","Tech Park","Metro","Highway","Hospital","Campus","Market"]
    st = pd.DataFrame({
        "id": [f"ST-{i+1:03d}" for i in range(NS)],
        "name": [f"{cities[c][0]} {areas[i % 8]} Hub {i+1}" for i, c in enumerate(cidx)],
        "city": [cities[c][0] for c in cidx], "state": [cities[c][1] for c in cidx], "country": "IN",
        "latitude": [cities[c][2] + rng.normal(0, .05) for c in cidx],
        "longitude": [cities[c][3] + rng.normal(0, .05) for c in cidx],
        "charger_type": ctype, "power_kw": power, "ports": rng.choice([1, 2, 4], NS, p=[.3, .5, .2])})
    w = rng.lognormal(0, .9, NS) * np.where(ctype == "DC Fast", 1.3, 1.0); w /= w.sum()
    sidx = rng.choice(NS, N, p=w)
    year = rng.choice(np.arange(2020, 2026), N, p=[.05, .08, .13, .19, .26, .29])
    base = pd.to_datetime(pd.Series(year).astype(str) + "-01-01")
    hp = np.array([1,1,1,1,1.5,2,3,5,7,7,5,4,4,4,4,5,6,8,9,9,8,5,3,2], float); hp /= hp.sum()
    conn = (base + pd.to_timedelta(rng.integers(0, 365, N), "D") + pd.to_timedelta(rng.choice(24, N, p=hp), "h")
            + pd.to_timedelta(rng.integers(0, 60, N), "m"))
    dc = (ctype[sidx] == "DC Fast"); pwr = power[sidx]
    kwh = np.round(np.clip(rng.gamma(2.5, np.where(dc, 10, 3.2)), 1, 90), 3)
    dur = kwh / (pwr * .85) * 60 + rng.exponential(np.where(dc, 5, 25)) + 1
    disc = conn + pd.to_timedelta(dur, "m")
    # ---- inject dirty data (to be cleaned by the ETL) ----
    n = lambda f: rng.choice(N, int(f * N), replace=False)
    bad_t = n(.004); disc.iloc[bad_t] = conn.iloc[bad_t] - pd.Timedelta(hours=1)      # disconnect before connect
    out = n(.0015); kwh[out] = kwh[out] + rng.uniform(150, 400, len(out))             # unrealistic energy
    kwh = kwh.astype(float); kwh[n(.008)] = np.nan                                      # missing kWh
    veh = [("Tata","Nexon EV","BEV","SUV"),("Tata","Tiago EV","BEV","Hatchback"),("MG","ZS EV","BEV","SUV"),
           ("MG","Comet EV","BEV","Hatchback"),("Mahindra","XUV400","BEV","SUV"),("Hyundai","Kona Electric","BEV","SUV"),
           ("BYD","Atto 3","BEV","SUV"),("Tesla","Model 3","BEV","Sedan"),("Kia","EV6","BEV","SUV"),
           ("BMW","iX","BEV","Luxury SUV"),("Volvo","XC90 Recharge","PHEV","Luxury SUV"),("Toyota","Prius Prime","PHEV","Sedan")]
    vi = rng.choice(len(veh), N, p=[.22,.17,.12,.06,.1,.05,.07,.04,.04,.04,.05,.04])
    uid = rng.integers(1, 12001, N)
    fmt = lambda s: s.dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
    acn = pd.DataFrame({
        "sessionID": [f"S{i+1:06d}" for i in range(N)], "stationID": st["id"].values[sidx], "userID": [f"U{u:05d}" for u in uid],
        "connectionTime": fmt(conn - pd.Timedelta(hours=5, minutes=30)),   # stored as UTC like ACN
        "disconnectTime": fmt(disc - pd.Timedelta(hours=5, minutes=30)),
        "kWhDelivered": kwh, "make": [veh[i][0] for i in vi], "model": [veh[i][1] for i in vi],
        "powertrain": [veh[i][2] for i in vi], "segment": [veh[i][3] for i in vi],
        "user_type": np.select([uid % 10 == 0, uid % 5 == 1], ["Fleet", "Guest"], "Registered")})
    m = n(.005); acn.loc[m, ["make", "model"]] = np.nan
    acn = acn.sort_values("connectionTime").reset_index(drop=True)
    acn = pd.concat([acn, acn.sample(int(.012 * N), random_state=1)], ignore_index=True)  # duplicates
    pay = pd.DataFrame({"sessionID": [f"S{i+1:06d}" for i in range(N)],
        "Payment_Type": rng.choice(["UPI", "Card", "Wallet", "Subscription"], N, p=[.5, .25, .15, .10])})
    rows = []
    for i in range(NS):
        for _ in range(rng.poisson(8)):
            d = pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(rng.integers(0, 2191)))
            f = 1.6 if ctype[i] == "DC Fast" else 1.0
            rows.append((st["id"][i], d.strftime("%Y-%m-%d"),
                         rng.choice(["Connector fault","Network outage","Payment module","Cable wear","Software update","Cooling fault"]),
                         round(float(rng.gamma(2, 4) * f), 2), round(float(rng.lognormal(8.2, .6) * f), 2)))
    mnt = pd.DataFrame(rows, columns=["stationID", "date", "issue_type", "Downtime_Hours", "Maintenance_Cost"])
    st = pd.concat([st, st.sample(5, random_state=2)], ignore_index=True)           # duplicate station rows
    st.loc[st.sample(4, random_state=3).index, "city"] = np.nan                      # missing city
    acn.to_csv(f"{RAW}/acn_sessions.csv", index=False); st.to_csv(f"{RAW}/charging_station.csv", index=False)
    pay.to_csv(f"{RAW}/payments.csv", index=False); mnt.to_csv(f"{RAW}/maintenance.csv", index=False)
    print(f"SYNTHETIC data written to data/raw: {len(acn)} session rows, {len(st)} station rows, {len(mnt)} maintenance rows")

if __name__ == "__main__":
    main(force="--force" in sys.argv)
