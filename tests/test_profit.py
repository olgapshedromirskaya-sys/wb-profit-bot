import json
from pathlib import Path

from bot.profit import aggregate_profit_by_sku, total_profit

DATA = Path(__file__).resolve().parent.parent / "data" / "sample_realization.json"


def load_rows():
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_profit_without_cost_price_equals_payout_minus_wb_costs():
    rows = load_rows()
    skus = aggregate_profit_by_sku(rows, cost_prices={}, ad_spend={})
    by_id = {s.nm_id: s for s in skus}

    sku = by_id["111111"]
    assert sku.quantity_sold == 167
    assert sku.revenue_gross == 90800
    # без себестоимости и рекламы прибыль = выплата WB - логистика - хранение - штрафы
    expected = 71500 - 13360 - 980 - 0
    assert round(sku.net_profit, 2) == expected


def test_return_reduces_quantity_and_revenue():
    rows = load_rows()
    skus = aggregate_profit_by_sku(rows, cost_prices={}, ad_spend={})
    by_id = {s.nm_id: s for s in skus}

    sku = by_id["222222"]
    # 247 продано - 12 возврат = 235
    assert sku.quantity_sold == 235
    assert sku.revenue_gross == 143500 - 6960


def test_cost_price_and_ad_spend_reduce_profit():
    rows = load_rows()
    skus = aggregate_profit_by_sku(
        rows,
        cost_prices={"111111": 300.0},
        ad_spend={"111111": 5000.0},
    )
    by_id = {s.nm_id: s for s in skus}
    sku = by_id["111111"]

    base = 71500 - 13360 - 980 - 0
    expected = base - (300.0 * 167) - 5000.0
    assert round(sku.net_profit, 2) == round(expected, 2)


def test_missing_cost_price_flagged_by_caller_not_by_function():
    # функция не должна падать, если себестоимость не задана — просто считает 0
    rows = load_rows()
    skus = aggregate_profit_by_sku(rows, cost_prices={}, ad_spend={})
    assert all(s.cost_price_total == 0 for s in skus)


def test_total_profit_sums_all_skus():
    rows = load_rows()
    skus = aggregate_profit_by_sku(rows, cost_prices={}, ad_spend={})
    total = total_profit(skus)
    assert round(total.net_profit, 2) == round(sum(s.net_profit for s in skus), 2)
    assert total.quantity_sold == sum(s.quantity_sold for s in skus)
