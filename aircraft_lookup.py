"""
Aircraft lookup backed by SQLite instead of in-memory dicts.

The FlightAware CSV has ~1.5M rows. Loading it into Python dicts costs
~650 MB of RAM. Here it is imported once into db/aircraft.db (indexed by
ICAO24) and each lookup is a single indexed query, so the app only keeps
a few MB in memory.

The DB is rebuilt automatically when any source CSV is newer than it.
Precedence matches the old {**flightaware, **vrs} merge, with community
contributions applied on top.
"""
import csv
import os
import sqlite3
import threading

DB_PATH = 'db/aircraft.db'
FLIGHTAWARE_CSV = 'db/flightaware-20220928.csv'
VRS_CSV = 'db/vrs.csv'
CONTRIB_CSV = 'db/contributions.csv'
COUNTRY_CSV = 'db/reg-country.csv'

_local = threading.local()


def _conn():
    """One read connection per thread (Flask threads + scheduler thread)."""
    c = getattr(_local, 'conn', None)
    if c is None:
        c = sqlite3.connect(DB_PATH)
        _local.conn = c
    return c


def _needs_rebuild():
    if not os.path.exists(DB_PATH):
        return True
    db_mtime = os.path.getmtime(DB_PATH)
    return any(os.path.exists(p) and os.path.getmtime(p) > db_mtime
               for p in (FLIGHTAWARE_CSV, VRS_CSV))


def _rows(path, mapper):
    with open(path, 'r', newline='') as f:
        for row in csv.DictReader(f):
            yield mapper(row)


def _apply_contributions(cur):
    if not os.path.exists(CONTRIB_CSV):
        return
    with open(CONTRIB_CSV, 'r', newline='') as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        rows = ((r[0].strip().upper(), r[1].strip(), r[2].strip(), r[3].strip())
                for r in reader if len(r) >= 4 and r[0].strip())
        cur.executemany(
            "INSERT OR REPLACE INTO aircraft (icao24, r, t, desc) VALUES (?, ?, ?, ?)", rows)


def build(force=False):
    if not force and not _needs_rebuild():
        return
    print("Building aircraft lookup DB (one-time, a few seconds)...")
    tmp = DB_PATH + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    with sqlite3.connect(tmp) as c:
        cur = c.cursor()
        cur.execute("PRAGMA journal_mode=OFF")
        cur.execute("PRAGMA synchronous=OFF")
        cur.execute("""CREATE TABLE aircraft (
                           icao24 TEXT PRIMARY KEY,
                           r TEXT, t TEXT, desc TEXT
                       ) WITHOUT ROWID""")
        cur.executemany(
            "INSERT OR REPLACE INTO aircraft VALUES (?, ?, ?, ?)",
            _rows(FLIGHTAWARE_CSV, lambda r: (r['icao24'].upper(), r['r'], r['t'], r['desc'])))
        # VRS overrides FlightAware (same as the old dict merge, desc becomes '')
        cur.executemany(
            "INSERT OR REPLACE INTO aircraft VALUES (?, ?, ?, '')",
            _rows(VRS_CSV, lambda r: (r['icao24'].upper(), r['r'], r['t'])))
        _apply_contributions(cur)
    os.replace(tmp, DB_PATH)
    print("Aircraft lookup DB ready.")


def lookup(icao24):
    """Return {'r','t','desc'} or None."""
    row = _conn().execute(
        "SELECT r, t, desc FROM aircraft WHERE icao24 = ?", (icao24.upper(),)).fetchone()
    if row is None:
        return None
    return {'r': row[0] or '', 't': row[1] or '', 'desc': row[2] or ''}


def add_contribution(icao24, r, t, desc):
    """Persist a user contribution so it survives restarts."""
    with sqlite3.connect(DB_PATH) as c:
        c.execute("INSERT OR REPLACE INTO aircraft (icao24, r, t, desc) VALUES (?, ?, ?, ?)",
                  (icao24.upper(), r, t, desc))


def load_countries():
    """Small table (~250 rows), fine to keep in memory."""
    out = {}
    with open(COUNTRY_CSV, 'r', newline='') as f:
        for row in csv.DictReader(f):
            out[row['prefix']] = {'country': row['Country'], 'code': row['Alpha-2']}
    return out
