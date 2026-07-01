"""
Конфигурация проекта.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class WBEndpoints:
    # Новый финансовый API (с июня 2026, старый отключается 15 июля 2026).
    # Токен должен иметь категорию «Финансы» (Finance).
    realization_report: str = "https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed"

    # Список отчётов за период (нужен для получения reportId).
    realization_report_list: str = "https://finance-api.wildberries.ru/api/finance/v1/sales-reports/list"

    # Воронка продаж по карточкам товара (Analytics API, категория «Аналитика»).
    nm_report_detail: str = "https://seller-analytics-api.wildberries.ru/api/v2/nm-report/detail"

    # Заказы и продажи — вспомогательные (для будущего расширения).
    orders: str = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
    sales: str = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"


WB = WBEndpoints()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "./data/users.db")
DEMO_ONLY = os.getenv("DEMO_ONLY", "false").lower() == "true"
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com")

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "")
CHANNEL_URL = os.getenv("CHANNEL_URL", "")
SUBSCRIPTION_CACHE_SECONDS = int(os.getenv("SUBSCRIPTION_CACHE_SECONDS", "1800"))
DASHBOARD_CACHE_SECONDS = int(os.getenv("DASHBOARD_CACHE_SECONDS", "1800"))

TELEGRAM_API_BASE = "https://api.telegram.org"

# Ориентиры конверсии воронки для диагностики карточек.
BENCHMARKS = {
    "view_to_cart_min": 0.06,
    "view_to_cart_good": 0.12,
    "cart_to_order_min": 0.25,
    "cart_to_order_good": 0.45,
    "drr_warning": 0.15,
    "drr_critical": 0.25,
}
