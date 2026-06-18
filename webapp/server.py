"""
Backend Mini App: отдаёт статику (static/) и API для фронтенда.

Каждый запрос к /api/* (кроме /api/demo) несёт заголовок
X-Telegram-Init-Data — это сырая строка Telegram.WebApp.initData,
которую фронтенд получает прямо от Telegram. Backend проверяет её
подпись (webapp/auth.py) на КАЖДЫЙ запрос — отдельной сессии/логина
не существует, и это нормально: подпись от Telegram надёжнее куки.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot import storage
from bot.config import BOT_TOKEN, DEMO_ONLY
from bot.wb_api import WBApiError, fetch_nm_report_detail, fetch_realization_report
from webapp import subscription
from webapp.auth import validate_init_data
from webapp.service import build_dashboard, demo_dashboard

app = FastAPI(title="WB Profit Mini App")

# Разрешаем CORS свободно — нужно только для локальной разработки
# (когда фронтенд открыт не с того же домена, что backend). В проде
# Telegram грузит страницу с того же домена, что отдаёт API, так что
# CORS фактически не используется.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        raise HTTPException(401, "Нет данных авторизации Telegram (заголовок X-Telegram-Init-Data)")
    user = validate_init_data(x_telegram_init_data, BOT_TOKEN)
    if not user:
        raise HTTPException(401, "Подпись Telegram не подтвердилась — откройте приложение заново")
    return user.user_id


def _require_access(x_telegram_init_data: str | None) -> int:
    """
    _auth подтверждает, КТО пользователь. Эта функция дополнительно
    проверяет, имеет ли он ПРАВО на данные — то есть подписан ли на
    канал прямо сейчас. Используется на всех "ценных" эндпоинтах
    (дашборд, подключение токена, себестоимость), но НЕ на /api/demo
    (демо — открытая приманка) и НЕ на отключение токена (отозвать
    свои данные можно всегда, независимо от подписки).
    """
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


@app.get("/api/demo")
def api_demo() -> dict:
    return demo_dashboard()


@app.get("/api/dashboard")
def api_dashboard(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict:
    user_id = _require_access(x_telegram_init_data)
    token = storage.get_token(user_id)
    if not token:
        return {"connected": False}

    if DEMO_ONLY:
        raise HTTPException(400, "Сервер запущен в демо-режиме (DEMO_ONLY=true)")

    date_from, date_to = _period()
    cost_prices = storage.get_cost_prices(user_id)
    ad_spend = storage.get_ad_spend(user_id, date_to)

    try:
        rows = fetch_realization_report(token, date_from, date_to)
        nm_ids = sorted({int(r["nm_id"]) for r in rows}) if rows else [int(x) for x in cost_prices]
        cards = fetch_nm_report_detail(token, nm_ids, date_from, date_to) if nm_ids else []
    except WBApiError as exc:
        raise HTTPException(502, str(exc))

    data = build_dashboard(rows, cards, cost_prices, ad_spend)
    data["connected"] = True
    data["demo"] = False
    return data


@app.post("/api/subscription/recheck")
def api_recheck_subscription(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    """
    Кэш подписки живёт SUBSCRIPTION_CACHE_SECONDS, чтобы не дёргать
    Bot API на каждый запрос. Но это значит, что человек, который
    только что подписался, иначе ждал бы до получаса. Эта ручка
    принудительно обновляет кэш — её вызывает кнопка
    "Я подписался, проверить" на фронтенде.
    """
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
    return {"ok": True}


@app.delete("/api/token")
def api_forget_token(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    user_id = _auth(x_telegram_init_data)
    storage.forget_token(user_id)
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


# Статика подключается ПОСЛЕДНЕЙ: иначе она перехватит /api/* раньше,
# чем до них дойдёт очередь у роутера.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
