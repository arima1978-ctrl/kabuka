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


def format_pool_report(rows: list[RankRow], date_from: str, date_to: str) -> str:
    header = (
        "📉 *東証プライム 値下がり率上位100社*\n"
        f"期間: `{date_from}` → `{date_to}`\n"
        f"件数: *{len(rows)}社*\n"
    )
    if not rows:
        return header + "\n該当銘柄なし。"
    s = ["```", "順位 コード 企業名                値下率   利回り       売上高"]
    for r in rows:
        s.append(
            f"{r.rank:>3} {r.code}  {r.name[:14]:<14}  "
            f"{r.change_pct:>6.2f}%  "
            f"{_fmt_yield(r.dividend_yield_pct):>7}  "
            f"{_fmt_revenue(r.revenue_jpy):>12}"
        )
    s.append("```")
    return "\n".join([header, *s])


def format_report(rows: list[RankRow], date_from: str, date_to: str) -> str:
    header = (
        "📉 *東証プライム 値下がり×増収銘柄*\n"
        f"期間: `{date_from}` → `{date_to}`\n"
        "条件: 値下がり率上位100社 ∧ 直近3年連続増収\n"
        f"該当: *{len(rows)}社*\n"
    )

    if not rows:
        return header + "\n該当銘柄なし。"

    s1 = ["```", "順位 コード 企業名                値下率   利回り  年間配当       売上高"]
    for r in rows:
        s1.append(
            f"{r.rank:>2}  {r.code}  {r.name[:14]:<14}  "
            f"{r.change_pct:>6.2f}%  "
            f"{_fmt_yield(r.dividend_yield_pct):>7}  "
            f"{_fmt_div(r.dividend_per_share):>10}  "
            f"{_fmt_revenue(r.revenue_jpy):>12}"
        )
    s1.append("```")

    footer = "_データ源: J-Quants API (JPX公式)_"
    return "\n".join([header, *s1, "", footer])
