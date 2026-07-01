"""
Клиент к API Wildberries.

Изменения июль 2026:
  - Отчёт о реализации: переехал на finance-api.wildberries.ru,
    метод стал POST /api/finance/v1/sales-reports/detailed,
    требует токен категории «Финансы».
  - Воронка nm-report: пока остаётся на старом эндпоинте.
  - Все запросы: retry при 429, паузы между страницами.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from bot.config import WB

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_PAUSE_DEFAULT = 60
PAGE_PAUSE = 1.0
INTER_API_PAUSE = 2.0


class WBApiError(RuntimeError):
    pass


def _headers(token: str) -> dict:
    return {"Authorization": token, "Content-Type": "application/json"}


def _handle_status(resp: requests.Response, context: str = "") -> None:
    if resp.status_code == 401:
        raise WBApiError(
            "Токен недействителен или просрочен. Создайте новый в Личном кабинете WB."
        )
    if resp.status_code == 403:
        raise WBApiError(
            "Токену не хватает прав. Для отчёта о реализации нужна категория «Финансы», "
            "для воронки — «Аналитика». Создайте новый токен с нужными правами."
        )
    if not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:300]
        raise WBApiError(f"WB API вернул ошибку {resp.status_code}: {detail}")


def _post_with_retry(url: str, token: str, body: dict) -> Any:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                headers=_headers(token),
                json=body,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise WBApiError(f"Сеть/таймаут при запросе к WB API: {exc}") from exc

        if resp.status_code == 429:
            if attempt == MAX_RETRIES:
                raise WBApiError(
                    "WB API возвращает 429 (слишком много запросов). "
                    "Попробуйте открыть дашборд через несколько минут."
                )
            wait = int(resp.headers.get("Retry-After", RETRY_PAUSE_DEFAULT))
            time.sleep(wait)
            continue

        if resp.status_code == 204:
            return []

        _handle_status(resp)
        return resp.json()


def _get_with_retry(url: str, token: str, params: dict[str, Any]) -> Any:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers=_headers(token),
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise WBApiError(f"Сеть/таймаут при запросе к WB API: {exc}") from exc

        if resp.status_code == 429:
            if attempt == MAX_RETRIES:
                raise WBApiError(
                    "WB API возвращает 429 (слишком много запросов). "
                    "Попробуйте через несколько минут."
                )
            wait = int(resp.headers.get("Retry-After", RETRY_PAUSE_DEFAULT))
            time.sleep(wait)
            continue

        if resp.status_code == 204:
            return []

        _handle_status(resp)
        return resp.json()


def _normalize_realization_row(row: dict) -> dict:
    """
    Новый API вернул поля с другими именами — приводим к виду,
    который ожидает profit.py (имена из старого API).
    Маппинг составлен по таблице в журнале изменений WB.
    """
    # Определяем тип документа
    doc_type = row.get("docTypeName") or row.get("doc_type_name", "")

    return {
        "nm_id": row.get("nmId") or row.get("nm_id", 0),
        "sa_name": row.get("saName") or row.get("sa_name", ""),
        "doc_type_name": doc_type,
        "quantity": row.get("quantity", 0),
        # Выручка (розничная цена × количество)
        "retail_amount": (
            row.get("retailAmount")
            or row.get("retail_amount")
            or row.get("retailPrice", 0)
        ),
        # Выплата от WB продавцу
        "ppvz_for_pay": (
            row.get("ppvzForPay")
            or row.get("ppvz_for_pay")
            or row.get("forPay", 0)
        ),
        # Логистика
        "delivery_rub": (
            row.get("deliveryRub")
            or row.get("delivery_rub")
            or row.get("deliveryCost", 0)
        ),
        # Хранение
        "storage_fee": (
            row.get("storageFee")
            or row.get("storage_fee")
            or row.get("storageCost", 0)
        ),
        # Штрафы
        "penalty": row.get("penalty", 0),
        # ID строки для пагинации
        "rrd_id": row.get("rrdId") or row.get("rrd_id", 0),
    }


def fetch_realization_report(token: str, date_from: str, date_to: str) -> list[dict]:
    """
    Детальный отчёт о реализации. Новый эндпоинт (POST, Finance API).
    Токен должен иметь категорию «Финансы».
    """
    rows: list[dict] = []
    cursor = None

    while True:
        body: dict = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "limit": 1000,
        }
        if cursor:
            body["cursor"] = cursor

        data = _post_with_retry(WB.realization_report, token, body)

        if not data:
            break

        # Новый API может вернуть {"data": [...], "cursor": "..."}
        # или просто список — обрабатываем оба варианта
        if isinstance(data, dict):
            items = data.get("data") or data.get("items") or []
            cursor = data.get("cursor") or data.get("nextCursor")
        else:
            items = data
            cursor = None

        if not items:
            break

        for item in items:
            rows.append(_normalize_realization_row(item))

        if not cursor or len(items) < 1000:
            break

        time.sleep(PAGE_PAUSE)

    return rows


def fetch_nm_report_detail(token: str, nm_ids: list[int], date_from: str, date_to: str) -> list[dict]:
    """
    Воронка по карточкам: переходы в карточку, корзина, заказы.
    Токен должен иметь категорию «Аналитика».
    Запросы батчами по 20 артикулов.
    """
    BATCH = 20
    result: list[dict] = []

    for i in range(0, len(nm_ids), BATCH):
        batch = nm_ids[i: i + BATCH]
        body = {
            "nmIDs": batch,
            "period": {"begin": date_from, "end": date_to},
            "page": 1,
        }
        data = _post_with_retry(WB.nm_report_detail, token, body)
        if isinstance(data, dict):
            cards = data.get("data", {}).get("cards", [])
        else:
            cards = []
        result.extend(cards)
        if i + BATCH < len(nm_ids):
            time.sleep(PAGE_PAUSE)

    return result
