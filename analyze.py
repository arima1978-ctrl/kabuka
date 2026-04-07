"""Compute top-20 price decliners in TSE Prime for a given period, with dividend/revenue."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import pandas as pd

from jquants import JQuantsClient

PRIME_MARKET_CODE = "0111"  # JPX MarketCode for Prime Market


@dataclass
class RankRow:
    rank: int
    code: str
    name: str
    price_from: float
    price_to: float
    change_pct: float          # %
    dividend_per_share: float | None   # 円/株（年間予想）
    dividend_yield_pct: float | None   # %
    revenue_jpy: float | None          # 円（最新年度売上高）


def _prime_issues(client: JQuantsClient) -> pd.DataFrame:
    info = client.listed_info()
    df = pd.DataFrame(info)
    # J-Quants returns 'MarketCode' or 'MarketCodeName'; use code for reliability
    df = df[df["MarketCode"] == PRIME_MARKET_CODE].copy()
    return df[["Code", "CompanyName"]].rename(columns={"Code": "code", "CompanyName": "name"})


def _price_at(client: JQuantsClient, date: str) -> pd.DataFrame:
    q = client.daily_quotes(date=date)
    df = pd.DataFrame(q)
    if df.empty:
        raise RuntimeError(f"No quotes for {date} (non-trading day?)")
    # AdjustmentClose accounts for splits; fall back to Close
    price_col = "AdjustmentClose" if "AdjustmentClose" in df.columns else "Close"
    df = df[["Code", price_col]].rename(columns={"Code": "code", price_col: "price"})
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    return df.dropna(subset=["price"])


def top20_decliners(client: JQuantsClient, date_from: str, date_to: str) -> list[RankRow]:
    """Return top-20 Prime decliners between two trading dates (YYYY-MM-DD)."""
    prime = _prime_issues(client)
    p_from = _price_at(client, date_from.replace("-", ""))
    p_to = _price_at(client, date_to.replace("-", ""))

    merged = (
        prime.merge(p_from, on="code", suffixes=("", "_f"))
             .merge(p_to, on="code", suffixes=("_from", "_to"))
    )
    merged["change_pct"] = (merged["price_to"] - merged["price_from"]) / merged["price_from"] * 100
    merged = merged.sort_values("change_pct").head(20).reset_index(drop=True)

    rows: list[RankRow] = []
    for i, r in merged.iterrows():
        div_ps, div_yield, revenue = _enrich_financials(client, r["code"], r["price_to"])
        rows.append(RankRow(
            rank=i + 1,
            code=str(r["code"]),
            name=str(r["name"]),
            price_from=float(r["price_from"]),
            price_to=float(r["price_to"]),
            change_pct=round(float(r["change_pct"]), 2),
            dividend_per_share=div_ps,
            dividend_yield_pct=div_yield,
            revenue_jpy=revenue,
        ))
    return rows


def _enrich_financials(client: JQuantsClient, code: str,
                       current_price: float) -> tuple[float | None, float | None, float | None]:
    """Latest annual dividend forecast + revenue. Requires Light plan."""
    try:
        stmts = client.statements(code)
    except Exception:
        return None, None, None
    if not stmts:
        return None, None, None

    df = pd.DataFrame(stmts)
    # Annual forecast rows: TypeOfDocument contains 'FinancialStatements'
    df["DisclosedDate"] = pd.to_datetime(df.get("DisclosedDate"), errors="coerce")
    df = df.sort_values("DisclosedDate", ascending=False)

    def _num(col: str) -> float | None:
        for _, row in df.iterrows():
            v = row.get(col)
            if v not in (None, "", "-"):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    # Forecast annual dividend per share (full year)
    div_ps = _num("ForecastDividendPerShareAnnual") or _num("ResultDividendPerShareAnnual")
    revenue = _num("NetSales") or _num("Revenue") or _num("OperatingRevenue1")

    div_yield = None
    if div_ps and current_price:
        div_yield = round(div_ps / current_price * 100, 2)

    return div_ps, div_yield, revenue


def to_dicts(rows: Iterable[RankRow]) -> list[dict]:
    return [asdict(r) for r in rows]
