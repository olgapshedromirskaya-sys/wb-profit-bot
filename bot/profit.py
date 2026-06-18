"""
Расчёт реальной прибыли из отчёта о реализации Wildberries.

Сырой отчёт даёт продажи, возвраты, логистику, хранение и штрафы вперемешку
построчно по каждой операции. Здесь это агрегируется до одной понятной
цифры на артикул: сколько денег реально осталось продавцу после ВСЕХ
расходов площадки, себестоимости товара и расходов на рекламу.

Все функции чистые (не лезут в сеть и в БД), поэтому легко покрываются
тестами на фиксированных данных — см. tests/test_profit.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Типы строк отчёта, которые считаем продажей (а не штрафом/доплатой/логистикой).
SALE_DOC_TYPES = {"Продажа"}
RETURN_DOC_TYPES = {"Возврат"}


@dataclass
class SkuProfit:
    nm_id: str
    sa_name: str = ""
    quantity_sold: int = 0
    revenue_gross: float = 0.0      # retail_amount — сумма, которую заплатил покупатель
    payout_from_wb: float = 0.0     # ppvz_for_pay — что фактически перевёл WB продавцу
    logistics_cost: float = 0.0
    storage_cost: float = 0.0
    penalties: float = 0.0
    cost_price_total: float = 0.0   # себестоимость * количество, вводит сам продавец
    ad_spend: float = 0.0           # расходы на рекламу за период, вводит сам продавец
    net_profit: float = field(init=False, default=0.0)
    margin_pct: float = field(init=False, default=0.0)
    drr_pct: float = field(init=False, default=0.0)

    def finalize(self) -> "SkuProfit":
        after_wb_costs = self.payout_from_wb - self.logistics_cost - self.storage_cost - self.penalties
        self.net_profit = after_wb_costs - self.cost_price_total - self.ad_spend
        self.margin_pct = (self.net_profit / self.revenue_gross * 100) if self.revenue_gross else 0.0
        self.drr_pct = (self.ad_spend / self.revenue_gross * 100) if self.revenue_gross else 0.0
        return self


def aggregate_profit_by_sku(
    report_rows: list[dict],
    cost_prices: dict[str, float],
    ad_spend: dict[str, float],
) -> list[SkuProfit]:
    """
    report_rows — строки из fetch_realization_report (или тестовых данных) с полями:
        nm_id, sa_name, doc_type_name, quantity, retail_amount,
        ppvz_for_pay, delivery_rub, storage_fee, penalty
    cost_prices — {nm_id: себестоимость за штуку}, задаёт продавец.
    ad_spend — {nm_id: расход на рекламу за период}, задаёт продавец
               (или подтягивается из Advertising API в расширенной версии).
    """
    by_sku: dict[str, SkuProfit] = {}

    for row in report_rows:
        nm_id = str(row.get("nm_id", "unknown"))
        sp = by_sku.setdefault(nm_id, SkuProfit(nm_id=nm_id, sa_name=row.get("sa_name", "")))

        doc_type = row.get("doc_type_name", "")
        qty = row.get("quantity", 0) or 0
        retail_amount = row.get("retail_amount", 0.0) or 0.0
        payout = row.get("ppvz_for_pay", 0.0) or 0.0
        delivery = row.get("delivery_rub", 0.0) or 0.0
        storage = row.get("storage_fee", 0.0) or 0.0
        penalty = row.get("penalty", 0.0) or 0.0

        if doc_type in SALE_DOC_TYPES:
            sp.quantity_sold += qty
            sp.revenue_gross += retail_amount
            sp.payout_from_wb += payout
        elif doc_type in RETURN_DOC_TYPES:
            sp.quantity_sold -= qty
            sp.revenue_gross -= retail_amount
            sp.payout_from_wb -= payout

        sp.logistics_cost += delivery
        sp.storage_cost += storage
        sp.penalties += penalty

    for nm_id, sp in by_sku.items():
        cost_per_unit = cost_prices.get(nm_id, 0.0)
        sp.cost_price_total = cost_per_unit * max(sp.quantity_sold, 0)
        sp.ad_spend = ad_spend.get(nm_id, 0.0)
        sp.finalize()

    return sorted(by_sku.values(), key=lambda s: s.net_profit)


def total_profit(skus: list[SkuProfit]) -> SkuProfit:
    """Сводная строка 'итого' по всем артикулам — для шапки отчёта."""
    t = SkuProfit(nm_id="ИТОГО")
    for s in skus:
        t.quantity_sold += s.quantity_sold
        t.revenue_gross += s.revenue_gross
        t.payout_from_wb += s.payout_from_wb
        t.logistics_cost += s.logistics_cost
        t.storage_cost += s.storage_cost
        t.penalties += s.penalties
        t.cost_price_total += s.cost_price_total
        t.ad_spend += s.ad_spend
    return t.finalize()
