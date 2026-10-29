"""Tiny DB layer: SQLAlchemy (as in Review 1). Falls back to built-in sqlite3 if SQLAlchemy is missing."""
import re, sqlite3
import pandas as pd
from config import DB_URL
try:
    from sqlalchemy import create_engine, text
    _SA = True
except ImportError:
    _SA = False
_engine = None

def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL)
    return _engine

def _path():
    if not DB_URL.startswith("sqlite:///"):
        raise RuntimeError("Run: pip install -r requirements.txt  (SQLAlchemy needed for " + DB_URL + ")")
    return DB_URL.replace("sqlite:///", "", 1)

def run_script(sql):
    stmts = [s.strip() for s in re.sub(r"--.*", "", sql).split(";") if s.strip()]
    if _SA:
        with engine().begin() as c:
            for s in stmts:
                c.execute(text(s))
    else:
        con = sqlite3.connect(_path())
        for s in stmts:
            con.execute(s)
        con.commit(); con.close()

def write_df(df, table):
    if _SA:
        df.to_sql(table, engine(), if_exists="append", index=False, chunksize=5000)
    else:
        con = sqlite3.connect(_path()); df.to_sql(table, con, if_exists="append", index=False); con.close()

def query(sql, params=None):
    params = params or {}
    if _SA:
        with engine().connect() as c:
            return pd.read_sql(text(sql), c, params=params)
    con = sqlite3.connect(_path())
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()
