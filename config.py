"""Central configuration. Change DB_URL (env var) to switch from SQLite to PostgreSQL/MySQL."""
import os
BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data", "raw")
OUT = os.path.join(BASE, "outputs")
SCHEMA = os.path.join(BASE, "schema.sql")
# Default = zero-setup SQLite file. PostgreSQL example:
#   set DB_URL=postgresql+psycopg2://postgres:pwd@localhost:5432/evcharge_dw
DB_URL = os.environ.get("DB_URL", "sqlite:///" + os.path.join(BASE, "evcharge_dw.db"))
TARIFF_INR = {"AC": 12.0, "DC Fast": 18.0}   # Rs per kWh (tariff assumption, state it in your report)
DEFAULT_TARIFF = 15.0
K_CLUSTERS = 3
RANDOM_STATE = 42
