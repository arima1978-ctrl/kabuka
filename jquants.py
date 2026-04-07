"""J-Quants V2 client; returns V1-compat field names."""
from __future__ import annotations
import os
from dataclasses import dataclass
import requests

BASE = "https://api.jquants.com/v2"

def _c4(c):
    return c[:-1] if isinstance(c, str) and len(c) == 5 else c

def _c5(c):
    return c + "0" if isinstance(c, str) and len(c) == 4 else c

@dataclass
class JQuantsClient:
    api_key: str
    def _h(self):
        return {"x-api-key": self.api_key}
    def _g(self, p, params=None):
        r = requests.get(f"{BASE}{p}", headers=self._h(), params=params, timeout=60)
        r.raise_for_status()
        return r.json()
    def _gp(self, p, params):
        out = []
        q = dict(params)
        while True:
            d = self._g(p, q)
            out.extend(d.get("data", []))
            pk = d.get("pagination_key")
            if not pk:
                return out
            q["pagination_key"] = pk
    def listed_info(self, date=None):
        params = {"date": date} if date else {}
        return [{"Code": _c4(r.get("Code")), "CompanyName": r.get("CoName"), "MarketCode": r.get("Mkt"), "MarketCodeName": r.get("MktNm"), "Sector17Code": r.get("S17"), "Sector33Code": r.get("S33"), "ScaleCategory": r.get("ScaleCat")} for r in self._gp("/equities/master", params)]
    def daily_quotes(self, code=None, date=None, from_=None, to=None):
        def n(d):
            return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and len(d) == 8 and "-" not in d else d
        params = {}
        if code: params["code"] = _c5(code)
        if date: params["date"] = n(date)
        if from_: params["from"] = n(from_)
        if to: params["to"] = n(to)
        return [{"Code": _c4(r.get("Code")), "Date": r.get("Date"), "Close": r.get("C"), "AdjustmentClose": r.get("AdjC"), "Open": r.get("O"), "High": r.get("H"), "Low": r.get("L"), "Volume": r.get("Vo")} for r in self._gp("/equities/bars/daily", params)]
    def statements(self, code):
        return [{"DisclosedDate": r.get("DiscDate"), "NetSales": r.get("Sales"), "ResultDividendPerShareAnnual": r.get("DivAnn"), "ForecastDividendPerShareAnnual": r.get("FDivAnn") or r.get("NxFDivAnn"), "OperatingProfit": r.get("OP"), "Profit": r.get("NP"), "EarningsPerShare": r.get("EPS")} for r in self._gp("/fins/summary", {"code": _c5(code)})]

def from_env():
    k = os.environ.get("JQUANTS_API_KEY")
    if not k:
        raise RuntimeError("JQUANTS_API_KEY not set")
    return JQuantsClient(api_key=k)
