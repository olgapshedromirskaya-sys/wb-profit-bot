"""
Склеивает profit.py и diagnostics.py в одну структуру, которую
ожидает фронтенд (static/app.js). Сама по себе функция чистая —
не лезет в сеть и в БД, поэтому легко тестируется (tests/test_service.py).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from bot.diagnostics import CardDiagnosis, diagnose_cards_from_nm_report
from bot.profit import SkuProfit, aggregate_profit_by_sku, total_profit

DATA_DIR = Path(__file__).resolve().parent / "static" / "data"


def _sku_to_dict(s: SkuProfit, diag: Optional[CardDiagnosis]) -> dict:
    return {
        "nm_id": s.nm_id,
        "sa_name": s.sa_name,
        "quantity_sold": s.quantity_sold,
        "revenue": round(s.revenue_gross, 2),
        "net_profit": round(s.net_profit, 2),
        "margin_pct": round(s.margin_pct, 1),
        "drr_pct": round(s.drr_pct, 1),
        "logistics_cost": round(s.logistics_cost, 2),
        "storage_cost": round(s.storage_cost, 2),
        "penalties": round(s.penalties, 2),
        "cost_price_total": round(s.cost_price_total, 2),
        "ad_spend": round(s.ad_spend, 2),
        "has_cost_price": s.cost_price_total > 0,
        "views": diag.views if diag else None,
        "add_to_cart": diag.add_to_cart if diag else None,
        "orders": diag.orders if diag else None,
        "view_to_cart_pct": round(diag.view_to_cart * 100, 1) if diag else None,
        "cart_to_order_pct": round(diag.cart_to_order * 100, 1) if diag else None,
        "diagnosis": diag.summary() if diag else "Нет данных воронки за период — добавьте артикул в /api/cost.",
    }


def build_dashboard(report_rows: list[dict], nm_cards: list[dict], cost_prices: dict, ad_spend: dict) -> dict:
    skus = aggregate_profit_by_sku(report_rows, cost_prices, ad_spend)
    total = total_profit(skus)

    drr_by_nm = {s.nm_id: s.drr_pct for s in skus}
    diags = {d.nm_id: d for d in diagnose_cards_from_nm_report(nm_cards, drr_by_nm)}

    sku_dicts = [_sku_to_dict(s, diags.get(s.nm_id)) for s in skus]
    total_dict = _sku_to_dict(total, None)
    total_dict["diagnosis"] = None

    return {"total": total_dict, "skus": sku_dicts}


def demo_dashboard() -> dict:
    rows = json.loads((DATA_DIR / "sample_realization.json").read_text(encoding="utf-8"))
    cards = json.loads((DATA_DIR / "sample_nmreport.json").read_text(encoding="utf-8"))
    cost_prices = {"111111": 300.0, "222222": 250.0}
    ad_spend = {"222222": 7000.0}

    data = build_dashboard(rows, cards, cost_prices, ad_spend)
    data["connected"] = True
    data["demo"] = True
    return data
