"""J-Quants API client. Handles auth token refresh and data endpoints."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

BASE = "https://api.jquants.com/v1"


@dataclass
class JQuantsClient:
    email: str
    password: str
    _id_token: str | None = None
    _id_token_exp: float = 0.0

    def _refresh_token(self) -> None:
        r = requests.post(
            f"{BASE}/token/auth_user",
            json={"mailaddress": self.email, "password": self.password},
            timeout=30,
        )
        r.raise_for_status()
        refresh_token = r.json()["refreshToken"]

        r2 = requests.post(
            f"{BASE}/token/auth_refresh",
            params={"refreshtoken": refresh_token},
            timeout=30,
        )
        r2.raise_for_status()
        self._id_token = r2.json()["idToken"]
        # idToken is valid ~24h; refresh proactively at 20h
        self._id_token_exp = time.time() + 20 * 3600

    def _headers(self) -> dict[str, str]:
        if not self._id_token or time.time() >= self._id_token_exp:
            self._refresh_token()
        return {"Authorization": f"Bearer {self._id_token}"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        r = requests.get(f"{BASE}{path}", headers=self._headers(), params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def _get_paginated(self, path: str, params: dict[str, Any], key: str) -> list[dict]:
        """Follow pagination_key until exhausted."""
        out: list[dict] = []
        p = dict(params)
        while True:
            data = self._get(path, p)
            out.extend(data.get(key, []))
            pk = data.get("pagination_key")
            if not pk:
                return out
            p["pagination_key"] = pk

    # ---- endpoints ----

    def listed_info(self, date: str | None = None) -> list[dict]:
        """All listed issues. Filter by MarketCode='0111' for Prime."""
        params = {"date": date} if date else {}
        return self._get_paginated("/listed/info", params, "info")

    def daily_quotes(self, code: str | None = None, date: str | None = None,
                     from_: str | None = None, to: str | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if code:
            params["code"] = code
        if date:
            params["date"] = date
        if from_:
            params["from"] = from_
        if to:
            params["to"] = to
        return self._get_paginated("/prices/daily_quotes", params, "daily_quotes")

    def statements(self, code: str) -> list[dict]:
        """Financial statements (requires Light plan or above)."""
        return self._get_paginated("/fins/statements", {"code": code}, "statements")


def from_env() -> JQuantsClient:
    email = os.environ["JQUANTS_EMAIL"]
    password = os.environ["JQUANTS_PASSWORD"]
    return JQuantsClient(email=email, password=password)
