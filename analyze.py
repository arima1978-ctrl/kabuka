"""Compute top-20 price decliners in TSE Prime for a given period, with dividend/revenue."""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
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
    revenue_history: list[float] | None = None  # 古い→新しい（直近4年）


def _prime_issues(client: JQuantsClient) -> pd.DataFrame:
    info = client.listed_info()
    df = pd.DataFrame(info)
    # J-Quants returns 'MarketCode' or 'MarketCodeName'; use code for reliability
    df = df[df["MarketCode"] == PRIME_MARKET_CODE].copy()
    # listed_info may return multiple historical snapshots per Code; keep the latest.
    if "Date" in df.columns:
        df = df.sort_values("Date").drop_duplicates(subset=["Code"], keep="last")
    else:
        df = df.drop_duplicates(subset=["Code"], keep="last")
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
    df = df.dropna(subset=["price"])
    # Safety: daily_quotes should be 1 row per code per date, but dedupe defensively.
    return df.drop_duplicates(subset=["code"], keep="last")


def top_decliners_growing(
    client: JQuantsClient,
    date_from: str,
    date_to: str,
    pool_size: int = 100,
) -> tuple[list[RankRow], list[RankRow]]:
    """値下がり率上位プールと、3年連続増収フィルタ後リストを返す。

    Returns:
        (pool_rows, filtered_rows) — どちらも値下がり率昇順で順位付け済み
    """
    prime = _prime_issues(client)
    p_from = _price_at(client, date_from.replace("-", ""))
    p_to = _price_at(client, date_to.replace("-", ""))

    merged = (
        prime.merge(p_from, on="code", suffixes=("", "_f"))
             .merge(p_to, on="code", suffixes=("_from", "_to"))
    )
    merged["change_pct"] = (merged["price_to"] - merged["price_from"]) / merged["price_from"] * 100
    pool = merged.sort_values("change_pct").head(pool_size).reset_index(drop=True)

    pool_rows: list[RankRow] = []
    filtered_rows: list[RankRow] = []
    for _, r in pool.iterrows():
        div_ps, div_yield, revenue, history = _enrich_financials(client, r["code"], r["price_to"])
        row = RankRow(
            rank=0,
            code=str(r["code"]),
            name=str(r["name"]),
            price_from=float(r["price_from"]),
            price_to=float(r["price_to"]),
            change_pct=round(float(r["change_pct"]), 2),
            dividend_per_share=div_ps,
            dividend_yield_pct=div_yield,
            revenue_jpy=revenue,
            revenue_history=history,
        )
        pool_rows.append(row)
        if _is_strictly_growing(history):
            filtered_rows.append(replace(row))

    for lst in (pool_rows, filtered_rows):
        lst.sort(key=lambda x: x.change_pct)
        for i, row in enumerate(lst, start=1):
            row.rank = i
    return pool_rows, filtered_rows


# Backwards-compat alias (returns top 20 unfiltered).
def top20_decliners(client: JQuantsClient, date_from: str, date_to: str) -> list[RankRow]:
    pool, _ = top_decliners_growing(client, date_from, date_to, pool_size=20)
    return pool


def _is_strictly_growing(history: list[float] | None) -> bool:
    """直近4年分の売上が y0 < y1 < y2 < y3 を満たすか。"""
    if not history or len(history) < 4:
        return False
    last4 = history[-4:]
    return all(b > a for a, b in zip(last4, last4[1:]))


def _enrich_financials(
    client: JQuantsClient, code: str, current_price: float
) -> tuple[float | None, float | None, float | None, list[float] | None]:
    """配当・売上・売上履歴を取得。Light プラン必須。"""
    try:
        stmts = client.statements(code)
    except Exception:
        return None, None, None, None
    if not stmts:
        return None, None, None, None

    df = pd.DataFrame(stmts)
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

    div_ps = _num("ForecastDividendPerShareAnnual") or _num("ResultDividendPerShareAnnual")
    revenue = _num("NetSales") or _num("Revenue") or _num("OperatingRevenue1")
    history = _annual_revenue_history(df)

    div_yield = None
    if div_ps and current_price:
        div_yield = round(div_ps / current_price * 100, 2)

    return div_ps, div_yield, revenue, history


def _annual_revenue_history(df: pd.DataFrame) -> list[float] | None:
    """開示履歴から年次売上シリーズを再構築 (古い→新しい)。

    各開示年について最大の NetSales を採用し、不完全な場合は None を返す。
    """
    if "NetSales" not in df.columns:
        return None
    work = df[["DisclosedDate", "NetSales"]].copy()
    work["NetSales"] = pd.to_numeric(work["NetSales"], errors="coerce")
    work = work.dropna(subset=["DisclosedDate", "NetSales"])
    if work.empty:
        return None
    work["year"] = work["DisclosedDate"].dt.year
    yearly = work.groupby("year")["NetSales"].max().sort_index()
    if yearly.empty:
        return None
    return [float(v) for v in yearly.tolist()]


def to_dicts(rows: Iterable[RankRow]) -> list[dict]:
    return [asdict(r) for r in rows]
