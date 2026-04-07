"""Format analysis results as Telegram-friendly Markdown tables."""
from __future__ import annotations

from analyze import RankRow


def _fmt_revenue(v: float | None) -> str:
    if v is None:
        return "—"
    oku = v / 1e8
    if abs(oku) >= 10000:
        return f"{oku / 10000:.2f}兆円"
    return f"{oku:,.0f}億円"


def _fmt_yield(v: float | None) -> str:
    return f"{v:.2f}%" if v is not None else "—"


def _fmt_div(v: float | None) -> str:
    return f"{v:.2f}円" if v is not None else "—"


def format_report(rows: list[RankRow], date_from: str, date_to: str) -> str:
    header = f"📉 *東証プライム 値下がり率ランキング*\n期間: `{date_from}` → `{date_to}`\n"

    # ① 値下がり率順
    s1 = ["\n*① 値下がり率 上位20社*", "```", "順位 コード 企業名                値下率"]
    for r in rows:
        s1.append(f"{r.rank:>2}  {r.code}  {r.name[:14]:<14}  {r.change_pct:>6.2f}%")
    s1.append("```")

    # ② 配当順
    by_div = sorted(
        rows,
        key=lambda r: (r.dividend_yield_pct if r.dividend_yield_pct is not None else -1),
        reverse=True,
    )
    s2 = ["*② 配当利回り順（上位20社内）*", "```", "①順 コード 企業名                利回り  年間配当"]
    for r in by_div:
        s2.append(
            f"{r.rank:>2}  {r.code}  {r.name[:14]:<14}  {_fmt_yield(r.dividend_yield_pct):>7}  {_fmt_div(r.dividend_per_share):>10}"
        )
    s2.append("```")

    # ③ 売上順
    by_rev = sorted(
        rows,
        key=lambda r: (r.revenue_jpy if r.revenue_jpy is not None else -1),
        reverse=True,
    )
    s3 = ["*③ 売上高順（上位20社内）*", "```", "①順 コード 企業名                売上高"]
    for r in by_rev:
        s3.append(f"{r.rank:>2}  {r.code}  {r.name[:14]:<14}  {_fmt_revenue(r.revenue_jpy):>12}")
    s3.append("```")

    footer = "_データ源: J-Quants API (JPX公式)_"
    return "\n".join([header, *s1, "", *s2, "", *s3, "", footer])
