"""Where the numbers come from. Each provider turns one public source into a SeriesResult; none of them ever raises
(a failed or empty fetch returns None), so one broken source leaves a labelled gap in the packet instead of stopping
the day.

The live providers are written against each source's documented response format but cannot be exercised from every
environment, so the fixture provider and the recorded sample in fixtures/ keep tests and offline demos working."""
import csv  # reads a hand-supplied flows file
import json  # reads recorded fixtures
import logging  # the app's logger
from datetime import UTC, date, datetime, timedelta  # date arithmetic for the request window
from pathlib import Path  # file paths

import httpx  # the HTTP client

from ..config import settings  # the shared app settings
from .packet import SERIES, SeriesResult

logger = logging.getLogger(__name__)

# A browser-like header: some public endpoints refuse requests with no user agent.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CounterpointMarkets/1.0; +educational)", "Accept": "application/json",
}
# How long one request may take.
TIMEOUT = 15.0
# Days of history requested (the packet keeps the last HISTORY_POINTS of them).
LOOKBACK_DAYS = 160


# The first step of a provider chain: base class with the one method every provider has.
class Provider:
    name = "base"

    def fetch(self, series_id: str, end: str) -> SeriesResult | None:  # pragma: no cover - interface
        raise NotImplementedError


# Yahoo Finance's public chart endpoint: no key, but unofficial, so it may change or rate-limit. Covers the indices,
# USD/INR, the dollar index, Brent, the US 10-year yield and India VIX.
class YahooProvider(Provider):
    name = "yahoo"
    url = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def fetch(self, series_id: str, end: str) -> SeriesResult | None:
        symbol = SERIES.get(series_id, {}).get("yahoo")
        if not symbol:
            return None
        end_day = date.fromisoformat(end) + timedelta(days=1)
        start_day = end_day - timedelta(days=LOOKBACK_DAYS)
        params: dict[str, str | int] = {
            "period1": int(datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC).timestamp()),
            "period2": int(datetime(end_day.year, end_day.month, end_day.day, tzinfo=UTC).timestamp()),
            "interval": "1d",
        }
        try:
            response = httpx.get(self.url.format(symbol=symbol), params=params, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            result = response.json()["chart"]["result"][0]
            offset = int(result.get("meta", {}).get("gmtoffset", 0))
            closes = result["indicators"]["quote"][0]["close"]
            points: dict[str, float] = {}
            for stamp, close in zip(result["timestamp"], closes, strict=False):
                if close is None:
                    continue
                # The bar's timestamp is the exchange's open time: shift by its offset to get the local trading day.
                day = datetime.fromtimestamp(int(stamp) + offset, tz=UTC).date().isoformat()
                points[day] = float(close)
        except Exception as exc:
            logger.warning("Yahoo fetch for %s failed: %s", series_id, exc)
            return None
        return _result(series_id, points, self.name, f"https://finance.yahoo.com/quote/{symbol}", end)


# FRED (St. Louis Fed): official and stable but needs a free API key, and values lag by about a day.
class FredProvider(Provider):
    name = "fred"
    url = "https://api.stlouisfed.org/fred/series/observations"

    def fetch(self, series_id: str, end: str) -> SeriesResult | None:
        fred_id = SERIES.get(series_id, {}).get("fred")
        if not fred_id or not settings.FRED_API_KEY:
            return None
        start = (date.fromisoformat(end) - timedelta(days=LOOKBACK_DAYS)).isoformat()
        params = {
            "series_id": fred_id, "api_key": settings.FRED_API_KEY, "file_type": "json",
            "observation_start": start, "observation_end": end,
        }
        try:
            response = httpx.get(self.url, params=params, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            points = {o["date"]: float(o["value"]) for o in response.json()["observations"] if o["value"] != "."}
        except Exception as exc:
            logger.warning("FRED fetch for %s failed: %s", series_id, exc)
            return None
        return _result(series_id, points, self.name, f"https://fred.stlouisfed.org/series/{fred_id}", end)


# NSE's published FII/DII statistics. The endpoint needs a session cookie from the home page, may block automated
# clients, and only returns the latest day, so history is accumulated by the pipeline (see pipeline.py).
class NseFlowProvider(Provider):
    name = "nse"
    home = "https://www.nseindia.com"
    url = "https://www.nseindia.com/api/fiidiiTradeReact"

    def fetch(self, series_id: str, end: str) -> SeriesResult | None:
        if series_id != "FII_NET":
            return None
        try:
            with httpx.Client(headers={**HEADERS, "Referer": self.home}, timeout=TIMEOUT) as client:
                client.get(self.home)  # sets the cookie the API checks
                rows = client.get(self.url).json()
            for row in rows:
                if str(row.get("category", "")).upper().startswith("FII"):
                    day = datetime.strptime(row["date"], "%d-%b-%Y").date().isoformat()
                    return SeriesResult("FII_NET", [(day, float(str(row["netValue"]).replace(",", "")))], self.name,
                                        self.url, "latest day only")
        except Exception as exc:
            logger.warning("NSE flow fetch failed: %s", exc)
        return None


# Reads a CSV you maintain yourself (columns: date,fii_net_cr). Use it to back-fill flow history or when the live
# source is blocked. Set MARKETS_FLOWS_CSV to its path.
class CsvFlowProvider(Provider):
    name = "csv"

    def __init__(self, path: str) -> None:
        self.path = path

    def fetch(self, series_id: str, end: str) -> SeriesResult | None:
        if series_id != "FII_NET" or not self.path or not Path(self.path).is_file():
            return None
        try:
            with open(self.path, newline="", encoding="utf-8") as handle:
                points = {r["date"]: float(r["fii_net_cr"]) for r in csv.DictReader(handle) if r.get("fii_net_cr")}
        except Exception as exc:
            logger.warning("Flows CSV %s unreadable: %s", self.path, exc)
            return None
        return _result(series_id, points, self.name, self.path, end)


# Recorded series from a JSON file ({"NIFTY50": [["2026-11-17", 24500.1], ...], ...}). Used by tests and demos.
class FixtureProvider(Provider):
    name = "fixture"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch(self, series_id: str, end: str) -> SeriesResult | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8")).get(series_id)
        except Exception as exc:
            logger.warning("Fixture %s unreadable: %s", self.path, exc)
            return None
        if not raw:
            return None
        return _result(series_id, {d: float(v) for d, v in raw}, self.name, str(self.path), end)


# Keeps points up to the requested date, oldest first, and wraps them. None when nothing is left.
def _result(series_id: str, points: dict[str, float], source: str, url: str, end: str) -> SeriesResult | None:
    kept = sorted((d, v) for d, v in points.items() if d <= end)
    if not kept:
        return None
    return SeriesResult(series_id, kept, source, url)


# The providers named in MARKETS_PROVIDERS, in order, plus the optional CSV and fixture files.
def configured_providers() -> list[Provider]:
    available: dict[str, Provider] = {"yahoo": YahooProvider(), "fred": FredProvider(), "nse": NseFlowProvider()}
    chain: list[Provider] = []
    if settings.MARKETS_FIXTURE_FILE:
        chain.append(FixtureProvider(settings.MARKETS_FIXTURE_FILE))
    if settings.MARKETS_FLOWS_CSV:
        chain.append(CsvFlowProvider(settings.MARKETS_FLOWS_CSV))
    for name in settings.MARKETS_PROVIDERS:
        if name in available:
            chain.append(available[name])
    return chain


# Fetches every series, trying each provider in order until one returns data. Never raises.
def collect(end: str, providers: list[Provider]) -> dict[str, SeriesResult]:
    found: dict[str, SeriesResult] = {}
    for series_id in SERIES:
        for provider in providers:
            result = provider.fetch(series_id, end)
            if result is not None:
                found[series_id] = result
                break
    return found
