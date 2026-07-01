"""
Простое хранилище на SQLite.

Для прототипа этого достаточно. Перед реальным продакшен-использованием:
  1. Шифровать wb_token (cryptography.fernet), ключ держать в переменной окружения.
  2. Не логировать токен.
  3. Дать пользователю /forget для удаления токена.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from bot.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    wb_token TEXT
);

CREATE TABLE IF NOT EXISTS cost_prices (
    telegram_id INTEGER,
    nm_id TEXT,
    cost_price REAL,
    PRIMARY KEY (telegram_id, nm_id)
);

CREATE TABLE IF NOT EXISTS ad_spend (
    telegram_id INTEGER,
    nm_id TEXT,
    period TEXT,
    spend REAL,
    PRIMARY KEY (telegram_id, nm_id, period)
);

CREATE TABLE IF NOT EXISTS subscription_cache (
    telegram_id INTEGER PRIMARY KEY,
    is_subscribed INTEGER,
    checked_at INTEGER
);

CREATE TABLE IF NOT EXISTS dashboard_cache (
    telegram_id INTEGER PRIMARY KEY,
    payload TEXT,
    cached_at INTEGER
);

CREATE TABLE IF NOT EXISTS fetch_jobs (
    telegram_id INTEGER PRIMARY KEY,
    status TEXT,
    error TEXT,
    started_at INTEGER
);
"""

# статусы фоновой загрузки данных из WB
JOB_PENDING = "pending"
JOB_DONE = "done"
JOB_ERROR = "error"


def _ensure_dir() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- users / tokens ----------

def save_token(telegram_id: int, token: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (telegram_id, wb_token) VALUES (?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET wb_token = excluded.wb_token",
            (telegram_id, token),
        )


def get_token(telegram_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT wb_token FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row[0] if row else None


def forget_token(telegram_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))


# ---------- cost prices ----------

def set_cost_price(telegram_id: int, nm_id: str, cost_price: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cost_prices (telegram_id, nm_id, cost_price) VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id, nm_id) DO UPDATE SET cost_price = excluded.cost_price",
            (telegram_id, nm_id, cost_price),
        )


def get_cost_prices(telegram_id: int) -> dict[str, float]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT nm_id, cost_price FROM cost_prices WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchall()
        return {nm_id: price for nm_id, price in rows}


# ---------- ad spend ----------

def set_ad_spend(telegram_id: int, nm_id: str, period: str, spend: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ad_spend (telegram_id, nm_id, period, spend) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(telegram_id, nm_id, period) DO UPDATE SET spend = excluded.spend",
            (telegram_id, nm_id, period, spend),
        )


def get_ad_spend(telegram_id: int, period: str) -> dict[str, float]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT nm_id, spend FROM ad_spend WHERE telegram_id = ? AND period = ?",
            (telegram_id, period),
        ).fetchall()
        return {nm_id: spend for nm_id, spend in rows}


# ---------- subscription cache ----------

def get_subscription_cache(telegram_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT is_subscribed, checked_at FROM subscription_cache WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if not row:
            return None
        return {"is_subscribed": bool(row[0]), "checked_at": row[1]}


def set_subscription_cache(telegram_id: int, is_subscribed: bool, checked_at: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO subscription_cache (telegram_id, is_subscribed, checked_at) VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET is_subscribed = excluded.is_subscribed, "
            "checked_at = excluded.checked_at",
            (telegram_id, int(is_subscribed), checked_at),
        )


# ---------- dashboard cache ----------

def get_dashboard_cache(telegram_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload, cached_at FROM dashboard_cache WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if not row:
            return None
        return {"payload": json.loads(row[0]), "cached_at": row[1]}


def set_dashboard_cache(telegram_id: int, payload: dict, cached_at: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO dashboard_cache (telegram_id, payload, cached_at) VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET payload = excluded.payload, "
            "cached_at = excluded.cached_at",
            (telegram_id, json.dumps(payload, ensure_ascii=False), cached_at),
        )


# ---------- fetch jobs (фоновая загрузка из WB) ----------

def get_fetch_job(telegram_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, error, started_at FROM fetch_jobs WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if not row:
            return None
        return {"status": row[0], "error": row[1], "started_at": row[2]}


def set_fetch_job(telegram_id: int, status: str, error: str | None = None) -> None:
    import time
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fetch_jobs (telegram_id, status, error, started_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET status = excluded.status, "
            "error = excluded.error, started_at = excluded.started_at",
            (telegram_id, status, error, int(time.time())),
        )


def clear_fetch_job(telegram_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM fetch_jobs WHERE telegram_id = ?", (telegram_id,))
