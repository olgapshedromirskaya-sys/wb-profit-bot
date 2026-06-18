"""
Тонкий клиент над официальным API Wildberries.

Все методы кидают WBApiError с понятным сообщением, если WB ответил
ошибкой (просроченный/неверный токен, не хватает прав на категорию
"Статистика" / "Аналитика", превышен лимит запросов и т.п.).

Это сетевой слой: он НИЧЕГО не считает и не интерпретирует — только
ходит в API и отдаёт чистые данные. Вся бизнес-логика — в profit.py
и diagnostics.py, что делает их легко тестируемыми без сети.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from bot.config import WB

REQUEST_TIMEOUT = 30


class WBApiError(RuntimeError):
    pass


def _headers(token: str) -> dict:
    return {"Authorization": token}


def _get(url: str, token: str, params: dict[str, Any]) -> Any:
    try:
        resp = requests.get(url, headers=_headers(token), params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise WBApiError(f"Сеть/таймаут при запросе к WB API: {exc}") from exc

    if resp.status_code == 401:
        raise WBApiError("Токен недействителен или просрочен. Создайте новый в Личном кабинете WB.")
    if resp.status_code == 403:
        raise WBApiError(
            "Токену не хватает прав. Нужны права 'Статистика' и 'Аналитика' "
            "при создании токена в разделе Доступ к API."
        )
    if resp.status_code == 429:
        raise WBApiError("Слишком много запросов к WB API, попробуйте через минуту.")
    if not resp.ok:
        raise WBApiError(f"WB API вернул ошибку {resp.status_code}: {resp.text[:300]}")

    return resp.json()


def fetch_realization_report(token: str, date_from: str, date_to: str) -> list[dict]:
    """
    Детальный отчёт о реализации за период.
    Содержит по каждой операции: nm_id, sa_name, doc_type_name,
    retail_amount, ppvz_for_pay, delivery_rub, storage_fee, penalty,
    quantity и т.д. — то, из чего считается реальная прибыль.
    """
    rows: list[dict] = []
    rrdid = 0
    while True:
        params = {"dateFrom": date_from, "dateTo": date_to, "limit": 1000, "rrdid": rrdid}
        chunk = _get(WB.realization_report, token, params)
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        rrdid = chunk[-1].get("rrd_id", rrdid)
        time.sleep(0.2)  # вежливая пауза между страницами, чтобы не упереться в лимит
    return rows


def fetch_nm_report_detail(token: str, nm_ids: list[int], date_from: str, date_to: str) -> list[dict]:
    """
    Воронка по карточкам товара: openCardCount (переходы в карточку),
    addToCartCount (добавления в корзину), ordersCount (заказы) и
    готовые конверсии за период.
    """
    body = {
        "nmIDs": nm_ids,
        "period": {"begin": date_from, "end": date_to},
        "page": 1,
    }
    try:
        resp = requests.post(WB.nm_report_detail, headers=_headers(token), json=body, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise WBApiError(f"Сеть/таймаут при запросе к WB API: {exc}") from exc

    if resp.status_code == 401:
        raise WBApiError("Токен недействителен или просрочен.")
    if resp.status_code == 403:
        raise WBApiError("Токену не хватает прав 'Аналитика'.")
    if not resp.ok:
        raise WBApiError(f"WB API вернул ошибку {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    return data.get("data", {}).get("cards", [])
