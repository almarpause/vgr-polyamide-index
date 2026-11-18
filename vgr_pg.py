"""VGR database switch: local SQLite (default) or the central PostgreSQL on node01.

Every clipping tool keeps its SQL in its own db.py; this module only decides
*where* that SQL runs and makes a psycopg connection behave like the sqlite3
one the code was written for (``?`` placeholders, ``conn.execute``,
``cur.lastrowid``, rows readable by name and by index).

Environment
-----------
VGR_DB             sqlite | postgres            (default: sqlite)
VGR_DB_<SCHEMA>    per-app override, e.g. VGR_DB_EMAIL_CLIPPING=postgres
VGR_PG_DSN         libpq conninfo without user/password, e.g.
                   "host=100.77.195.48 port=5432 dbname=vgr passfile=C:/Users/pals/.pgpass"
                   The login role is <schema>_rw; the password comes from the passfile.

Only the production database of each tool (<tool>/data/<file>.db) is ever
redirected. Any other path (self-checks, offline tests in a temp dir) stays on
SQLite, so tests never touch the shared database.

Once a tool has been cut over, its data folder holds MIGRATED_TO_POSTGRES.txt.
With no VGR_DB/VGR_DB_<SCHEMA> set, the marker selects postgres (and its
"dsn=" line is the fallback for VGR_PG_DSN), so scheduled tasks keep working
even if they do not see the user environment. An explicit sqlite setting on a
migrated tool raises instead of silently creating a new, empty SQLite file.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

try:  # psycopg is only needed in postgres mode
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

# tool folder name -> (postgres schema, production SQLite file name[, data folder name])
APPS = {
    "email-clipping": ("email_clipping", "emails.db"),
    "tiktok-clipping": ("tiktok_clipping", "tracker.db"),
    "website-clipping": ("website_clipping", "newin.db"),
    "insta-clipping": ("insta_clipping", "tracker.db"),
    # Dell: closet-competitors/crossbrand/database/master.sqlite
    "crossbrand": ("closet", "master.sqlite", "database"),
    # Dell: zara-parser/layer3_consolidator/database/master.sqlite (also read by Polyamide)
    "layer3_consolidator": ("zara", "master.sqlite", "database"),
}
MARKER = "MIGRATED_TO_POSTGRES.txt"

# PG_ONLY_PATCH (2026-11-18): every app in APPS has been cut over to node01.
# Its production path always means PostgreSQL, marker or not (a fresh clone or a
# dev run has no marker), and SQLite there is refused unless a sandbox/test sets
# VGR_PG_ALLOW_SQLITE=1 together with VGR_DB=sqlite.
DEFAULT_DSN = "host=100.77.195.48 port=5432 dbname=vgr"
# schema -> project folders allowed above <tool>/<folder>/<file> (other brand
# parsers share the layout and must never land in these schemas)
REPO_NAMES = {
    "closet": {"closet-competitors", "competitors"},
    "zara": {"zara-parser", "zara"},
}


def _sqlite_allowed() -> bool:
    return os.environ.get("VGR_PG_ALLOW_SQLITE") == "1"


def _default_dsn() -> str:
    """node01 over Tailscale; the password comes from the machine's passfile."""
    dsn = DEFAULT_DSN
    home_pgpass = Path.home() / ".pgpass"
    if os.name == "nt" and not os.environ.get("PGPASSFILE") and home_pgpass.is_file():
        dsn += " passfile=" + home_pgpass.as_posix()  # minipc01 keeps it in ~/.pgpass
    return dsn

# Exceptions a caller may catch for "the database failed", whichever backend.
ERRORS: tuple = (sqlite3.Error,) + ((psycopg.Error,) if psycopg else ())


# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #
def schema_for(path: str | Path) -> str | None:
    """Postgres schema for a tool's production DB path, else None."""
    p = Path(path).resolve()
    app = APPS.get(p.parent.parent.name.lower())
    folder = app[2] if app and len(app) > 2 else "data"
    if app and p.parent.name.lower() == folder and p.name.lower() == app[1]:
        repos = REPO_NAMES.get(app[0])
        if repos and p.parent.parent.parent.name.lower() not in repos:
            return None  # same layout, another project (e.g. another brand parser)
        return app[0]
    return None


def _marker(path: str | Path | None) -> Path | None:
    if path is None or not schema_for(path):
        return None
    m = Path(path).parent / MARKER
    return m if m.exists() else None


def _marker_dsn(path) -> str | None:
    m = _marker(path)
    if m:
        for line in m.read_text(encoding="utf-8").splitlines():
            if line.startswith("dsn="):
                return line[4:].strip()
    return None


def backend_for(schema: str, path: str | Path | None = None) -> str:
    value = os.environ.get("VGR_DB_" + schema.upper()) or os.environ.get("VGR_DB")
    if not value:
        value = "postgres"  # migrated app: node01 by default (PG_ONLY_PATCH)
    value = value.strip().lower()
    if value not in ("sqlite", "postgres"):
        raise ValueError(f"VGR_DB must be sqlite or postgres, got {value!r}")
    return value


def uses_postgres(path: str | Path) -> bool:
    schema = schema_for(path)
    return bool(schema) and backend_for(schema, path) == "postgres"


def guard_sqlite(path: str | Path) -> None:
    """Refuse to open a retired production SQLite DB."""
    p = Path(path)
    if schema_for(p) and not _sqlite_allowed():
        raise RuntimeError(
            f"{p} was migrated to PostgreSQL (see {p.parent / MARKER}). "
            "It is PostgreSQL-only (node01): unset VGR_DB or set VGR_DB=postgres. "
            "Sandboxes/tests on their own copy: VGR_DB=sqlite VGR_PG_ALLOW_SQLITE=1."
        )


def available(path: str | Path) -> bool:
    """Drop-in for ``path.is_file()`` in readers: is there a database to read?"""
    if uses_postgres(path):
        return True
    guard_sqlite(path)
    return Path(path).is_file()


# --------------------------------------------------------------------------- #
# sqlite3-compatible wrapper around psycopg
# --------------------------------------------------------------------------- #
class Row:
    """Behaves like sqlite3.Row: row["col"] (case-insensitive), row[0], keys(), dict(row)."""

    __slots__ = ("_values", "_keys", "_index")

    def __init__(self, values: tuple, keys: list, index: dict):
        self._values, self._keys, self._index = values, keys, index

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return self._values[self._index[key.lower()]]
            except KeyError:
                raise IndexError("No item with that key") from None
        return self._values[key]

    def keys(self) -> list:
        return list(self._keys)

    def __len__(self):
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __eq__(self, other):
        if isinstance(other, Row):
            return self._keys == other._keys and self._values == other._values
        return NotImplemented

    def __hash__(self):
        return hash((tuple(self._keys), self._values))

    def __repr__(self):
        return f"<Row {dict(zip(self._keys, self._values))!r}>"


def to_sqlite_value(value):
    """Return what SQLite would have returned for the same stored value."""
    if isinstance(value, datetime):  # timestamptz columns, session TimeZone=UTC
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):  # aggregates: SUM(int) -> int, AVG -> float
        return int(value) if value == value.to_integral_value() and value.as_tuple().exponent >= 0 else float(value)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def _row_factory(cursor):
    keys = [d.name for d in (cursor.description or [])]
    index = {}
    for i, k in enumerate(keys):
        index.setdefault(k.lower(), i)

    def make(values):
        return Row(tuple(to_sqlite_value(v) for v in values), keys, index)

    return make


_QMARK = re.compile(r"""('(?:[^']|'')*'|"(?:[^"]|"")*")|\?""")
_INSERT = re.compile(r"^\s*INSERT\s+(?:OR\s+(IGNORE|REPLACE)\s+)?INTO\s+([A-Za-z_][\w]*)", re.I)
_NOOP = re.compile(r"^\s*(BEGIN(\s+(DEFERRED|IMMEDIATE|EXCLUSIVE))?(\s+TRANSACTION)?|PRAGMA\b.*)\s*;?\s*$", re.I | re.S)


_IS_PARAM = re.compile(r"""('(?:[^']|'')*'|"(?:[^"]|"")*")|\bIS\s+(NOT\s+)?(?=\?)""", re.I)


def translate(sql: str) -> str:
    """sqlite ``?`` placeholders -> psycopg ``%s``; literal % doubled.

    SQLite's ``x IS ?`` (null-safe equality) becomes ``IS NOT DISTINCT FROM``.
    """
    sql = sql.replace("%", "%%")
    sql = _IS_PARAM.sub(lambda m: m.group(1) or ("IS DISTINCT FROM " if m.group(2) else "IS NOT DISTINCT FROM "), sql)
    return _QMARK.sub(lambda m: m.group(1) if m.group(1) else "%s", sql)


def _params(params):
    """sqlite stores Python bools as 0/1; the migrated schemas use integer columns."""
    return [int(v) if isinstance(v, bool) else v for v in params] if params is not None else []


class Cursor:
    def __init__(self, cur=None, lastrowid=None, prefetched=None):
        self._cur, self.lastrowid, self._pre = cur, lastrowid, prefetched

    @property
    def rowcount(self):
        return self._cur.rowcount if self._cur is not None else -1

    @property
    def description(self):
        return self._cur.description if self._cur is not None else None

    def fetchone(self):
        if self._pre is not None:
            return self._pre.pop(0) if self._pre else None
        if self._cur is None or self._cur.description is None:
            return None
        return self._cur.fetchone()

    def fetchall(self):
        if self._pre is not None:
            out, self._pre = self._pre, []
            return out
        if self._cur is None or self._cur.description is None:
            return []
        return self._cur.fetchall()

    def fetchmany(self, size=1):
        rows = []
        for _ in range(size):
            r = self.fetchone()
            if r is None:
                break
            rows.append(r)
        return rows

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        if self._cur is not None:
            self._cur.close()


_TABLE_INFO: dict = {}


class Connection:
    """The subset of sqlite3.Connection the VGR tools use, on PostgreSQL."""

    backend = "postgres"

    def __init__(self, raw, schema: str):
        self._raw, self.schema = raw, schema
        self.row_factory = None  # accepted and ignored: rows are always Row
        if schema not in _TABLE_INFO:
            _TABLE_INFO[schema] = self._load_table_info()
        self._info = _TABLE_INFO[schema]

    def _load_table_info(self) -> dict:
        info: dict = {}
        with self._raw.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (self.schema,))
            for t, c in cur.fetchall():
                info.setdefault(t, {"cols": [], "conflict": None})["cols"].append(c)
            # conflict target for INSERT OR REPLACE: the first unique constraint
            # that is not the id primary key, else the primary key
            cur.execute(
                "SELECT tc.table_name, tc.constraint_type, "
                "       array_agg(kcu.column_name::text ORDER BY kcu.ordinal_position) "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema "
                "WHERE tc.table_schema = %s AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE') "
                "GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type "
                "ORDER BY tc.table_name, tc.constraint_type DESC, tc.constraint_name", (self.schema,))
            for t, kind, cols in cur.fetchall():
                if t in info and info[t]["conflict"] is None and not (kind == "PRIMARY KEY" and cols == ["id"]):
                    info[t]["conflict"] = list(cols)
            for t in info:
                if info[t]["conflict"] is None and "id" in info[t]["cols"]:
                    info[t]["conflict"] = ["id"]
        return info

    def _rewrite_insert(self, sql: str):
        """Return (sql, wants_id) for INSERT statements; mimics sqlite lastrowid."""
        m = _INSERT.match(sql)
        if not m:
            return sql, False
        mode, table = (m.group(1) or "").upper(), m.group(2).lower()
        body = sql.rstrip().rstrip(";")
        if mode:
            body = re.sub(r"^\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO", "INSERT INTO", sql.rstrip().rstrip(";"), flags=re.I)
            if mode == "IGNORE":
                body += " ON CONFLICT DO NOTHING"
            else:
                target = (self._info.get(table) or {}).get("conflict")
                if not target:
                    raise NotImplementedError(f"INSERT OR REPLACE into {table}: no unique key")
                cols_m = re.search(r"INTO\s+\w+\s*\(([^)]*)\)", body, re.I)
                # "INSERT OR REPLACE INTO t VALUES (...)" has no column list: all columns, in table order
                cols = ([c.strip() for c in cols_m.group(1).split(",")] if cols_m
                        else list((self._info.get(table) or {}).get("cols", [])))
                sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in target)
                body += f" ON CONFLICT ({', '.join(target)}) DO " + (f"UPDATE SET {sets}" if sets else "NOTHING")
        wants_id = "id" in (self._info.get(table) or {}).get("cols", []) and not re.search(r"\bRETURNING\b", body, re.I)
        if wants_id:
            body += " RETURNING id"
        return body, wants_id

    def execute(self, sql: str, params=()):
        if _NOOP.match(sql):
            return Cursor()
        sql, wants_id = self._rewrite_insert(sql)
        cur = self._raw.cursor(row_factory=_row_factory)
        cur.execute(translate(sql), _params(params))
        if wants_id:
            row = cur.fetchone()
            return Cursor(cur, lastrowid=(row[0] if row else None), prefetched=[])
        return Cursor(cur)

    def executemany(self, sql: str, seq):
        sql, _ = self._rewrite_insert(sql)
        sql = re.sub(r"\s+RETURNING id$", "", sql)
        with self._raw.cursor() as cur:
            cur.executemany(translate(sql), [_params(p) for p in seq])
        return Cursor()

    def cursor(self):
        """sqlite3-style cursor: cur.execute(...) then cur.fetchone()/fetchall()/iterate."""
        return _CursorShim(self)

    def executescript(self, script: str):
        raise NotImplementedError("executescript is SQLite-only; the Postgres schema is created by the migration")

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # sqlite3 semantics: commit/rollback, stay open
        if exc_type is None:
            self._raw.commit()
        else:
            self._raw.rollback()
        return False


class _CursorShim:
    """What ``sqlite3.Connection.cursor()`` returns, for code written against it."""

    def __init__(self, conn: "Connection"):
        self._conn, self._cur = conn, Cursor()

    def execute(self, sql: str, params=()):
        self._cur = self._conn.execute(sql, params)
        return self

    def executemany(self, sql: str, seq):
        self._cur = self._conn.executemany(sql, seq)
        return self

    @property
    def description(self):
        return self._cur.description

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=1):
        return self._cur.fetchmany(size)

    def __iter__(self):
        return iter(self._cur.fetchall())

    def close(self):
        self._cur.close()


def connect_pg(schema: str, readonly: bool = False, dsn: str | None = None,
               role: str | None = None) -> Connection:
    """``role`` defaults to ``<schema>_rw``; a reader of another app's schema
    (Polyamide reading zara) passes its own role, e.g. ``polyamide_rw``."""
    if psycopg is None:
        raise RuntimeError("VGR_DB=postgres needs psycopg: pip install 'psycopg[binary]'")
    dsn = os.environ.get("VGR_PG_DSN") or dsn or _default_dsn()
    if not dsn:
        raise RuntimeError("VGR_DB=postgres but VGR_PG_DSN is not set")
    options = f"-c search_path={schema} -c TimeZone=UTC"
    if readonly:
        options += " -c default_transaction_read_only=on"
    raw = psycopg.connect(dsn, user=role or f"{schema}_rw", options=options,
                          application_name=role or schema, connect_timeout=15)
    return Connection(raw, schema)


def stream(conn, sql: str, params=(), itersize: int = 20000):
    """Yield (column_names, row_iterator) without loading the whole result.

    SQLite: a plain cursor (already lazy). Postgres: a server-side cursor, values
    converted to what SQLite would have returned. Used for the big CSV mirrors.
    """
    if not is_postgres(conn):
        cur = conn.execute(sql, params)
        return [d[0] for d in cur.description], cur
    global _STREAMS
    _STREAMS += 1
    cur = conn._raw.cursor(name=f"vgr_stream_{_STREAMS}")
    cur.itersize = itersize
    cur.execute(translate(sql), _params(params))
    cols = [d.name for d in cur.description]

    def rows():
        try:
            for r in cur:
                yield tuple(to_sqlite_value(v) for v in r)
        finally:
            cur.close()

    return cols, rows()


_STREAMS = 0


def connect_path(path: str | Path, readonly: bool = False, role: str | None = None):
    """Open a tool's database by its SQLite path, honouring VGR_DB.

    Returns a sqlite3.Connection (row_factory=sqlite3.Row) or a Connection.
    ``role`` (Postgres only) overrides the login role, see connect_pg.
    """
    schema = schema_for(path)
    if schema and backend_for(schema, path) == "postgres":
        return connect_pg(schema, readonly=readonly, dsn=_marker_dsn(path), role=role)
    guard_sqlite(path)
    p = Path(path)
    if readonly:
        con = sqlite3.connect("file:" + p.as_posix() + "?mode=ro", uri=True)
    else:
        con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    return con


def is_postgres(conn) -> bool:
    return isinstance(conn, Connection)
