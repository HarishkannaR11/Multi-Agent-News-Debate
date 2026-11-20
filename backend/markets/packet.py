"""The frozen "data packet" a market debate is built on.

A packet holds the day's numbers (a short history per series), where each series came from, and the facts computed
from them by plain code (signals.py). Agents only ever see the facts, and every figure they may quote is in a fact, so a
claim can be checked against the packet mechanically. The packet is stored with a SHA-256 of its content: the same
packet always produces the same facts, which is what makes a verdict reproducible and auditable."""
import hashlib  # SHA-256 fingerprint of the packet
import json  # canonical JSON text
from dataclasses import dataclass, field  # small record types

# Bump when the packet layout changes, so old stored packets are never misread.
SCHEMA_VERSION = 1

# Every series the packet can hold. "yahoo" is the symbol the Yahoo chart provider uses, "fred" the FRED series id.
# "session" says which market produced the value: India closes at 15:30 IST, the US session closes hours after that,
# so a US move on day D can only reach Indian prices on day D+1 (the attribution model lags those factors by one day).
SERIES: dict[str, dict] = {
    "NIFTY50": {
        "label": "NIFTY 50", "unit": "points", "kind": "index", "session": "india", "yahoo": "^NSEI",
    },
    "SENSEX": {"label": "BSE SENSEX", "unit": "points", "kind": "index", "session": "india", "yahoo": "^BSESN"},
    "USDINR": {
        "label": "USD/INR", "unit": "INR per USD", "kind": "fx", "session": "india", "yahoo": "INR=X",
        "fred": "DEXINUS",
    },
    "INDIAVIX": {
        "label": "India VIX", "unit": "points", "kind": "volatility", "session": "india", "yahoo": "^INDIAVIX",
    },
    "DXY": {
        "label": "US dollar index", "unit": "points", "kind": "index", "session": "us", "yahoo": "DX-Y.NYB",
        "fred": "DTWEXBGS",
    },
    "BRENT": {
        "label": "Brent crude", "unit": "USD per barrel", "kind": "commodity", "session": "us", "yahoo": "BZ=F",
        "fred": "DCOILBRENTEU",
    },
    "US10Y": {
        "label": "US 10-year yield", "unit": "percent", "kind": "yield", "session": "us", "yahoo": "^TNX",
        "fred": "DGS10",
    },
    "FII_NET": {"label": "FII/FPI net equity flow", "unit": "INR crore", "kind": "flow", "session": "india"},
}

# The Indian index everything is anchored to. Without it there is no market day to debate.
ANCHOR = "NIFTY50"
# How many daily points of each series are kept in the packet (enough for a 60-day window plus the lag).
HISTORY_POINTS = 90
# A series whose latest point is older than this many calendar days before the as-of date is treated as stale.
MAX_STALE_DAYS = 4


# One series as fetched from a provider.
@dataclass
class SeriesResult:
    series_id: str
    points: list[tuple[str, float]]  # (ISO date, value), oldest first
    source: str  # provider name, e.g. "yahoo"
    source_url: str = ""
    note: str = ""
    extra: dict = field(default_factory=dict)


class NoMarketData(Exception):
    """Raised when the anchor index could not be fetched, so there is no market day to build."""


# The canonical text of a packet's content (sorted keys, no spaces) so equal packets hash equally.
def canonical_json(content: dict) -> str:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# The SHA-256 fingerprint of a packet's content.
def packet_hash(content: dict) -> str:
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
