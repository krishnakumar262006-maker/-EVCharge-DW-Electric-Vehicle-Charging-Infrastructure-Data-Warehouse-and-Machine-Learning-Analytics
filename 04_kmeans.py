"""STEP 4 (Review 2) - K-Means clustering of stations on station-level features. K=3 (as presented) + elbow/silhouette validation."""
import json, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
import db
from config import OUT, K_CLUSTERS, RANDOM_STATE
os.makedirs(OUT, exist_ok=True)
df = db.query("""SELECT s.station_key, s.station_id, l.city, c.charger_type, c.power_kw,
  COUNT(*) AS session_count, SUM(f.energy_kwh) AS total_energy_kwh, AVG(f.energy_kwh) AS avg_energy_kwh,
  AVG(f.duration_minutes) AS avg_duration_minutes
  FROM vw_fact_clean f JOIN dim_station s ON f.station_key=s.station_key JOIN dim_location l ON s.location_key=l.location_key
  JOIN dim_charger c ON s.charger_key=c.charger_key GROUP BY s.station_key, s.station_id, l.city, c.charger_type, c.power_kw""")
FEATURES = ["session_count", "total_energy_kwh", "avg_energy_kwh", "avg_duration_minutes", "power_kw"]
X = df[FEATURES].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
ok = X.notna().all(axis=1); df, X = df[ok].copy(), X[ok]
Xs = StandardScaler().fit_transform(X)
print(f"Valid station records: {len(df)} | features: {FEATURES}")

# validate K (elbow + silhouette)
ks, inertia, sil = list(range(2, 9)), [], []
for k in ks:
    m = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit(Xs)
    inertia.append(float(m.inertia_)); sil.append(float(silhouette_score(Xs, m.labels_)))
best_k = ks[int(np.argmax(sil))]
model = KMeans(n_clusters=K_CLUSTERS, random_state=RANDOM_STATE, n_init=10).fit(Xs)
df["cluster_id"] = model.labels_; final_sil = float(silhouette_score(Xs, model.labels_))
rank = df.groupby("cluster_id").total_energy_kwh.mean().sort_values().index.tolist()   # IDs are arbitrary -> label by activity
names = ["Lower activity", "Medium activity", "Higher activity"] if K_CLUSTERS == 3 else [f"Level {i+1}" for i in range(K_CLUSTERS)]
df["cluster_label"] = df.cluster_id.map({cid: names[i] for i, cid in enumerate(rank)})
summ = df.groupby(["cluster_id", "cluster_label"]).agg(stations=("station_key", "count"), **{f"mean_{c}": (c, "mean") for c in FEATURES}).round(2).reset_index()
summ = summ.sort_values("mean_total_energy_kwh")
df.round(3).to_csv(f"{OUT}/station_clusters.csv", index=False); summ.to_csv(f"{OUT}/cluster_summary.csv", index=False)
db.run_script("DROP TABLE IF EXISTS station_clusters; DROP TABLE IF EXISTS cluster_summary")
db.write_df(df.round(3), "station_clusters"); db.write_df(summ, "cluster_summary")
json.dump({"k_used": K_CLUSTERS, "silhouette_k_used": round(final_sil, 3), "best_k_by_silhouette": best_k,
           "k_values": ks, "inertia": inertia, "silhouette": sil, "features": FEATURES, "n_stations": len(df)},
          open(f"{OUT}/kmeans_metrics.json", "w"), indent=2)
print(f"\nK={K_CLUSTERS}  silhouette={final_sil:.3f}   (best K by silhouette = {best_k})\n"); print(summ.to_string(index=False))
colors = ["#d95f02", "#1b9e77", "#7570b3", "#e7298a", "#66a61e"]
fig, ax = plt.subplots(figsize=(8, 5.5))
for i, cid in enumerate(rank):
    s = df[df.cluster_id == cid]; ax.scatter(s.session_count, s.total_energy_kwh, c=colors[i], label=f"{names[i]} (n={len(s)})", alpha=.8, edgecolor="k", lw=.3)
ax.set(xlabel="Session count", ylabel="Total energy (kWh)", title=f"K-Means (K={K_CLUSTERS}) - EV charging stations"); ax.legend(); fig.tight_layout()
fig.savefig(f"{OUT}/kmeans_clusters.png", dpi=150); plt.close(fig)
fig, a = plt.subplots(1, 2, figsize=(10, 4)); a[0].plot(ks, inertia, "o-"); a[0].set(title="Elbow", xlabel="K", ylabel="Inertia")
a[1].plot(ks, sil, "o-", c="g"); a[1].set(title="Silhouette", xlabel="K"); fig.tight_layout(); fig.savefig(f"{OUT}/kmeans_elbow_silhouette.png", dpi=150)
print("\nSaved CSVs + PNGs to outputs/ and tables station_clusters / cluster_summary to the DW.")
