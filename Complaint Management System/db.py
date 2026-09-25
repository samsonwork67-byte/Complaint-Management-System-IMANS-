"""
Reusable PostgreSQL database connection module.
Uses psycopg2 with a thread-safe connection pool.
"""
import os
import time
import psycopg2
import psycopg2.pool
import psycopg2.extras
from psycopg2.extras import Json
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ocms_user:password@localhost:5432/ocms_db"
)

# Thread-safe connection pool (min 2, max 30 connections)
_pool = psycopg2.pool.ThreadedConnectionPool(2, 30, DATABASE_URL)


def _is_conn_alive(conn):
    """Check if connection is still alive."""
    try:
        conn.cursor().execute("SELECT 1")
        return True
    except psycopg2.OperationalError:
        return False


def _get_valid_conn():
    """Get a valid connection from pool, replacing dead ones."""
    for _ in range(3):
        conn = _pool.getconn()
        if _is_conn_alive(conn):
            return conn
        # Connection dead, discard and try next
        try:
            _pool.putconn(conn, close=True)
        except Exception:
            pass
        time.sleep(0.1)
    raise psycopg2.OperationalError("No valid database connections available")


@contextmanager
def get_conn():
    """Get a connection from the pool. Auto-returns on exit."""
    conn = _get_valid_conn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def query(sql, params=None):
    """Execute a SELECT query and return a list of dicts."""
    conn = _get_valid_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def query_one(sql, params=None):
    """Execute a SELECT query and return a single dict, or None if no rows."""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    """Execute INSERT/UPDATE/DELETE.
    Returns list of dicts if RETURNING is used, else rowcount (int).
    """
    conn = _get_valid_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if cur.description:
                result = [dict(r) for r in cur.fetchall()]
            else:
                result = cur.rowcount
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def count(sql, params=None):
    """Execute a COUNT query and return the integer result."""
    conn = _get_valid_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = cur.fetchone()[0]
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def insert_row(table, data):
    """Insert a row from a dict. Auto-wraps list/dict values as JSONB.
    Returns list of dicts (uses RETURNING *).
    """
    cols = list(data.keys())
    vals = []
    for v in data.values():
        if isinstance(v, (list, dict)):
            vals.append(Json(v))
        else:
            vals.append(v)
    col_names = ', '.join(f'"{c}"' for c in cols)
    placeholders = ', '.join(['%s'] * len(cols))
    sql = f'INSERT INTO {table} ({col_names}) VALUES ({placeholders}) RETURNING *'
    return execute(sql, vals)


def update_row(table, updates, where_clause, where_params):
    """Execute UPDATE ... SET ... WHERE ... RETURNING *.
    Auto-wraps list/dict values as JSONB.
    Returns list of dicts (the updated rows).
    """
    if not updates:
        return []
    cols = list(updates.keys())
    vals = []
    for v in updates.values():
        if isinstance(v, (list, dict)):
            vals.append(Json(v))
        else:
            vals.append(v)
    set_clause = ', '.join(f'"{c}" = %s' for c in cols)
    sql = f'UPDATE {table} SET {set_clause} WHERE {where_clause} RETURNING *'
    all_params = vals + list(where_params)
    return execute(sql, all_params)
