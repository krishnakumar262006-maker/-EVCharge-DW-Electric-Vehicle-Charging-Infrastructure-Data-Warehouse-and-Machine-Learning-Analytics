"""Run the whole pipeline: data -> ETL -> OLAP -> K-Means.  Then start the dashboard with: python app.py"""
import subprocess, sys
for s in ["01_generate_data.py", "02_etl.py", "03_olap.py", "04_kmeans.py"]:
    print(f"\n{'='*70}\n>>> {s}\n{'='*70}", flush=True)
    if subprocess.call([sys.executable, s]) != 0:
        sys.exit(f"FAILED at {s}")
print("\nPipeline finished.  Now run:  python app.py   ->  http://127.0.0.1:5000")
