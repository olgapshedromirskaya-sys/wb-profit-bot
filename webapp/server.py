"""
Backend Mini App.

Архитектура загрузки данных из WB API (защита от блокировки токена):

  1. GET /api/dashboard — мгновенный ответ:
       - есть свежий кэш → отдаём его, WB API не вызывается вообще
       - уже идёт загрузка → {"status": "pending"}
       - нет кэша и нет активной загрузки → запускаем фоновый поток,
         возвращаем {"status": "pending"}

  2. Фоновый поток (wb_api.py) соблюдает все лимиты WB:
       - пауза 1 с между страницами постраничного отчёта
       - пауза 2 с между двумя разными API-методами
       - при 429 — ждёт Retry-After и повторяет

  3. Фронтенд опрашивает /api/dashboard каждые 3 с, пока не получит данные.

  4. POST /api/dashboard/refresh — сбрасывает кэш и запускает
     фоновую перезагрузку (не чаще раза в 5 минут).
"""
from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot import storage
from bot.config import BOT_TOKEN, DASHBOARD_CACHE_SECONDS, DEMO_ONLY
from bot.storage import JOB_DONE, JOB_ERROR, JOB_PENDING
from bot.wb_api import WBApiError, fetch_nm_report_detail, fetch_realization_report
from webapp import subscription
from webapp.auth import validate_init_data
from webapp.service import build_dashboard, demo_dashboard

app = FastAPI(title="WB Profit Mini App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Пауза между fetch_realization_report и fetch_nm_report_detail —
# два разных API-метода, WB следит за частотой по каждому отдельно.
INTER_API_PAUSE = 2.0
# Минимальный интервал между принудительными обновлениями (Refresh).
MIN_REFRESH_INTERVAL = 300


class TokenPayload(BaseModel):
    token: str


class CostPayload(BaseModel):
    nm_id: str
    cost_price: float


def _period() -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=30)).isoformat(), today.isoformat()


def _auth(x_telegram_init_data: str | None) -> int:
    if not x_telegram_init_data:
        raise HTTPException(401, "Нет данных авторизации Telegram")
    user = validate_init_data(x_telegram_init_data, BOT_TOKEN)
    if not user:
        raise HTTPException(401, "Подпись Telegram не подтвердилась — откройте приложение заново")
    return user.user_id


def _require_access(x_telegram_init_data: str | None) -> int:
    user_id = _auth(x_telegram_init_data)
    if not subscription.is_subscribed(user_id):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "subscription_required",
                "message": "Чтобы открыть доступ, подпишитесь на канал.",
                **subscription.channel_info(),
            },
        )
    return user_id


def _background_fetch(user_id: int, token: str) -> None:
    """
    Запускается в отдельном потоке. Соблюдает все паузы, не торопится.
    При любой ошибке пишет её в fetch_jobs, чтобы фронтенд мог показать
    понятное сообщение, а не просто «загрузка...» бесконечно.
    """
    try:
        date_from, date_to = _period()
        cost_prices = storage.get_cost_prices(user_id)
        ad_spend = storage.get_ad_spend(user_id, date_to)

        # Шаг 1: отчёт о реализации (с паузами между страницами внутри)
        rows = fetch_realization_report(token, date_from, date_to)

        # Пауза между двумя разными API-методами
        time.sleep(INTER_API_PAUSE)

        # Шаг 2: воронка по карточкам (с паузами между батчами внутри)
        nm_ids = sorted({int(r["nm_id"]) for r in rows}) if rows else [int(x) for x in cost_prices]
        cards = fetch_nm_report_detail(token, nm_ids, date_from, date_to) if nm_ids else []

        data = build_dashboard(rows, cards, cost_prices, ad_spend)
        data["connected"] = True
        data["demo"] = False
        data["cached"] = False

        storage.set_dashboard_cache(user_id, data, int(time.time()))
        storage.set_fetch_job(user_id, JOB_DONE)

    except WBApiError as exc:
        storage.set_fetch_job(user_id, JOB_ERROR, str(exc))
    except Exception as exc:
        storage.set_fetch_job(user_id, JOB_ERROR, f"Внутренняя ошибка: {exc}")


def _start_fetch(user_id: int, token: str) -> None:
    """Запускает фоновый поток, если он ещё не запущен."""
    job = storage.get_fetch_job(user_id)
    if job and job["status"] == JOB_PENDING:
        # уже идёт — не запускаем второй поток
        return
    storage.set_fetch_job(user_id, JOB_PENDING)
    t = threading.Thread(target=_background_fetch, args=(user_id, token), daemon=True)
    t.start()


# ---------- эндпоинты ----------

@app.get("/api/demo")
def api_demo() -> dict:
    return demo_dashboard()


@app.get("/api/dashboard")
def api_dashboard(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    user_id = _require_access(x_telegram_init_data)
    token = storage.get_token(user_id)
    if not token:
        return {"connected": False}

    if DEMO_ONLY:
        raise HTTPException(400, "Сервер запущен в демо-режиме (DEMO_ONLY=true)")

    # 1. Есть свежий кэш — отдаём его, в WB не ходим
    cached = storage.get_dashboard_cache(user_id)
    if cached and (time.time() - cached["cached_at"] < DASHBOARD_CACHE_SECONDS):
        payload = dict(cached["payload"])
        payload["cached"] = True
        return payload

    # 2. Смотрим, что с фоновой задачей
    job = storage.get_fetch_job(user_id)

    if job and job["status"] == JOB_ERROR:
        # Предыдущая попытка упала — сбрасываем и сообщаем ошибку
        error_msg = job["error"]
        storage.clear_fetch_job(user_id)
        raise HTTPException(502, error_msg)

    if job and job["status"] == JOB_DONE:
        # Поток завершился, но кэш ещё не подхватился (race) — читаем напрямую
        storage.clear_fetch_job(user_id)
        cached = storage.get_dashboard_cache(user_id)
        if cached:
            payload = dict(cached["payload"])
            payload["cached"] = False
            return payload

    # 3. Запускаем фоновый поток (или он уже идёт — _start_fetch это проверяет)
    _start_fetch(user_id, token)
    return {"status": "pending", "message": "Загружаем данные из Wildberries…"}


@app.post("/api/dashboard/refresh")
def api_dashboard_refresh(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    user_id = _require_access(x_telegram_init_data)
    token = storage.get_token(user_id)
    if not token:
        return {"connected": False}

    # Не чаще раза в MIN_REFRESH_INTERVAL секунд
    cached = storage.get_dashboard_cache(user_id)
    if cached:
        since = time.time() - cached["cached_at"]
        if since < MIN_REFRESH_INTERVAL:
            wait = int(MIN_REFRESH_INTERVAL - since)
            raise HTTPException(
                429,
                f"Данные обновлялись {int(since)} сек. назад. "
                f"Следующее обновление через {wait} сек."
            )

    _start_fetch(user_id, token)
    return {"status": "pending", "message": "Обновляем данные из Wildberries…"}


@app.post("/api/subscription/recheck")
def api_recheck_subscription(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    user_id = _auth(x_telegram_init_data)
    subscribed = subscription.is_subscribed(user_id, force_refresh=True)
    result = {"subscribed": subscribed}
    if not subscribed:
        result.update(subscription.channel_info())
    return result


@app.post("/api/token")
def api_set_token(
    payload: TokenPayload,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    user_id = _require_access(x_telegram_init_data)
    token = payload.token.strip()
    if not token:
        raise HTTPException(400, "Токен пустой")
    storage.save_token(user_id, token)
    # Сбрасываем старый кэш и задание — при следующем открытии загрузим заново
    storage.clear_fetch_job(user_id)
    return {"ok": True}


@app.delete("/api/token")
def api_forget_token(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    user_id = _auth(x_telegram_init_data)
    storage.forget_token(user_id)
    storage.clear_fetch_job(user_id)
    return {"ok": True}


@app.post("/api/cost")
def api_set_cost(
    payload: CostPayload,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    user_id = _require_access(x_telegram_init_data)
    nm_id = payload.nm_id.strip()
    if not nm_id:
        raise HTTPException(400, "nm_id обязателен")
    storage.set_cost_price(user_id, nm_id, payload.cost_price)
    return {"ok": True}


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
