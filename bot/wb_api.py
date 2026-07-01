"""
Тонкий клиент над официальным API Wildberries.

Главные изменения по сравнению с первой версией:
  - При ответе 429 (Too Many Requests) ждём Retry-After из заголовка
    (или фиксированную паузу) и повторяем — до MAX_RETRIES попыток.
  - Пауза между страницами постраничного отчёта увеличена с 0.2 до 1 с,
    чтобы не вылетать за лимит 60 запросов/минуту по отчёту о реализации.
  - Лимиты WB API (актуальны на момент написания):
      * reportDetailByPeriod — не чаще 1 запроса в секунду
      * nm-report/detail     — не чаще 1 запроса в секунду
    Эти числа могут меняться — проверяйте на https://dev.wildberries.ru/
"""
from __future__ import annotations

import time
from typing import Any

import requests

from bot.config import WB

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3          # сколько раз повторять при 429
RETRY_PAUSE_DEFAULT = 60 # секунд ждать при 429, если нет заголовка Retry-After
PAGE_PAUSE = 1.0         # пауза между страницами постраничного отчёта


class WBApiError(RuntimeError):
    pass


def _headers(token: str) -> dict:
    return {"Authorization": token}


def _handle_status(resp: requests.Response) -> None:
    if resp.status_code == 401:
        raise WBApiError("Токен недействителен или просрочен. Создайте новый в Личном кабинете WB.")
    if resp.status_code == 403:
        raise WBApiError(
            "Токену не хватает прав. Нужны права «Статистика» и «Аналитика» "
            "при создании токена в разделе Доступ к API."
        )
    if not resp.ok:
        raise WBApiError(f"WB API вернул ошибку {resp.status_code}: {resp.text[:300]}")


def _get_with_retry(url: str, token: str, params: dict[str, Any]) -> Any:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url, headers=_headers(token), params=params, timeout=REQUEST_TIMEOUT
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

        _handle_status(resp)
        return resp.json()


def _post_with_retry(url: str, token: str, body: dict) -> Any:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url, headers=_headers(token), json=body, timeout=REQUEST_TIMEOUT
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

        _handle_status(resp)
        return resp.json()


def fetch_realization_report(token: str, date_from: str, date_to: str) -> list[dict]:
    """
    Детальный отчёт о реализации за период (постраничный).
    Лимит WB: ~1 запрос/сек — соблюдается паузой PAGE_PAUSE между страницами.
    """
    rows: list[dict] = []
    rrdid = 0
    while True:
        params = {"dateFrom": date_from, "dateTo": date_to, "limit": 1000, "rrdid": rrdid}
        chunk = _get_with_retry(WB.realization_report, token, params)
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        rrdid = chunk[-1].get("rrd_id", rrdid)
        time.sleep(PAGE_PAUSE)
    return rows


def fetch_nm_report_detail(token: str, nm_ids: list[int], date_from: str, date_to: str) -> list[dict]:
    """
    Воронка по карточкам: переходы в карточку, корзина, заказы.
    WB принимает до 20 nmID за раз — делаем батчинг по 20 с паузой между батчами.
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
        cards = data.get("data", {}).get("cards", [])
        result.extend(cards)
        if i + BATCH < len(nm_ids):
            time.sleep(PAGE_PAUSE)
    return result
