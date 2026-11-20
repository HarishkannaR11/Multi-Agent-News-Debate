"""Builds the frozen packet for one market day from fetched series and the stored flow history."""
from datetime import UTC, datetime

from .packet import ANCHOR, HISTORY_POINTS, SCHEMA_VERSION, SERIES, NoMarketData, SeriesResult, packet_hash
from .signals import compute_signals, usable_index


# Merges stored flow history with what was just fetched (fetched values win), oldest first.
def merge_flows(history: dict[str, float], fetched: SeriesResult | None) -> list[tuple[str, float]]:
    merged = dict(history)
    if fetched is not None:
        merged.update(dict(fetched.points))
    return sorted(merged.items())


# Returns (packet, fingerprint). The packet's `as_of` is the anchor index's last trading day on or before
# `requested`, so a weekend or holiday run describes the last session. Raises NoMarketData without the anchor index.
def build_packet(
    requested: str, fetched: dict[str, SeriesResult], flow_history: dict[str, float] | None = None
) -> tuple[dict, str]:
    anchor = fetched.get(ANCHOR)
    if anchor is None or not anchor.points:
        raise NoMarketData("the NIFTY 50 series could not be fetched from any provider")
    as_of = anchor.points[-1][0]

    series: dict[str, list[tuple[str, float]]] = {sid: list(r.points) for sid, r in fetched.items() if sid != "FII_NET"}
    flows = merge_flows(flow_history or {}, fetched.get("FII_NET"))
    if flows:
        series["FII_NET"] = flows
    series = {sid: pts[-HISTORY_POINTS:] for sid, pts in series.items()}

    signals = compute_signals(series, as_of)
    provenance = {}
    for sid, meta in SERIES.items():
        points = series.get(sid, [])
        result = fetched.get(sid)
        if not points:
            status, detail = "missing", "No provider returned data for this series."
        elif usable_index(points, as_of) is None:
            status, detail = "stale", f"Latest value is from {points[-1][0]}, too old for {as_of}."
        else:
            status, detail = "ok", ""
        provenance[sid] = {
            "label": meta["label"], "unit": meta["unit"], "status": status, "detail": detail,
            "source": result.source if result else ("stored history" if points else ""),
            "source_url": result.source_url if result else "",
            "last_date": points[-1][0] if points else "",
            "points": [[d, round(v, 4)] for d, v in points],
        }
    content = {
        "schema": SCHEMA_VERSION, "as_of": as_of, "requested_date": requested, "series": provenance,
        "facts": signals["facts"], "attribution": signals["attribution"], "regime": signals["regime"],
        "missing": signals["missing"],
    }
    return content, packet_hash(content)


# Timestamp for the stored record (kept out of the packet so it never changes the fingerprint).
def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# A few headline numbers for the archive list (so listing days never loads whole packets).
def brief(packet: dict) -> dict:
    points = packet["series"].get(ANCHOR, {}).get("points", [])
    change = None
    if len(points) >= 2 and points[-2][1]:
        change = round((points[-1][1] / points[-2][1] - 1.0) * 100.0, 2)
    attr = packet.get("attribution", {})
    return {
        "nifty_close": points[-1][1] if points else None, "nifty_pct": change,
        "regime": packet.get("regime", {}).get("label", ""),
        "attribution": attr.get("label", "") if attr.get("status") == "ok" else "",
    }
