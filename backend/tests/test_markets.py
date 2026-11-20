import json  # reads fixtures and replies
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import llm, settings
from backend.main import app
from backend.markets import pipeline, providers, store
from backend.markets.build import build_packet
from backend.markets.packet import NoMarketData, SeriesResult, packet_hash
from backend.markets.providers import CsvFlowProvider, FixtureProvider, FredProvider, YahooProvider, collect
from backend.markets.signals import attribution, changes, compute_signals, regime, solve, usable_index
from backend.markets.validator import figures, validate_agent, validate_verdict
from backend.services import redis_service as redis_store

FIXTURE = Path(__file__).resolve().parents[1] / "markets" / "fixtures" / "sample_synthetic.json"
AS_OF = "2026-11-19"


def load_series() -> dict[str, list[tuple[str, float]]]:
    raw = json.loads(FIXTURE.read_text())
    return {k: [(d, v) for d, v in pts] for k, pts in raw.items() if not k.startswith("_")}


def fetched_from_fixture() -> dict[str, SeriesResult]:
    return collect(AS_OF, [FixtureProvider(FIXTURE)])


@pytest.fixture
def signals():
    return compute_signals(load_series(), AS_OF)


# ----- the signal layer ---------------------------------------------------------------------------------------------


def test_solve_known_system_and_singular():
    assert solve([[2.0, 0.0], [0.0, 4.0]], [2.0, 8.0]) == pytest.approx([1.0, 2.0])
    assert solve([[1.0, 1.0], [2.0, 2.0]], [1.0, 2.0]) is None


def test_changes_percent_and_basis_points():
    pts = [("2026-01-01", 100.0), ("2026-01-02", 101.0), ("2026-01-05", 99.99)]
    pct = changes(pts)
    assert pct["2026-01-02"] == pytest.approx(1.0)
    bps = changes([("a", 4.00), ("b", 4.08)], pct=False, scale=100.0)
    assert bps["b"] == pytest.approx(8.0)


def test_facts_are_numbered_in_order_and_cover_the_chain(signals):
    facts = signals["facts"]
    assert [f["id"] for f in facts] == [f"M{i}" for i in range(1, len(facts) + 1)]
    assert facts[0]["series"] == "NIFTY50" and facts[0]["kind"] == "level"
    series = {f["series"] for f in facts}
    assert {"NIFTY50", "SENSEX", "USDINR", "DXY", "BRENT", "US10Y", "FII_NET", "ATTRIBUTION", "REGIME"} <= series
    assert signals["missing"] == []
    nifty = facts[0]
    assert "closed at" in nifty["text"] and nifty["numbers"][1] == pytest.approx(0.9, abs=0.01)


def test_signals_are_deterministic():
    assert compute_signals(load_series(), AS_OF) == compute_signals(load_series(), AS_OF)


def test_attribution_reads_the_designed_day_as_imported(signals):
    attr = signals["attribution"]
    assert attr["status"] == "ok" and attr["label"] == "imported"
    assert attr["actual_pct"] == pytest.approx(-0.9, abs=0.01)
    assert attr["explained_pct"] < -0.4 and abs(attr["residual_pct"]) < abs(attr["explained_pct"])
    assert attr["n_obs"] >= 30 and attr["confidence"] in ("low", "moderate")
    assert attr["actual_pct"] == pytest.approx(attr["explained_pct"] + attr["residual_pct"], abs=1e-3)
    contributions = [abs(f["contribution_pct"]) for f in attr["factors"]]
    assert contributions == sorted(contributions, reverse=True)


def test_attribution_needs_enough_data():
    series = {k: v[-12:] for k, v in load_series().items()}
    result = attribution(series, AS_OF)
    assert result["status"] == "insufficient"
    facts = compute_signals(series, AS_OF)["facts"]
    assert any(f["series"] == "ATTRIBUTION" and "No attribution" in f["text"] for f in facts)


def test_attribution_small_move_is_not_attributed():
    series = load_series()
    nifty = series["NIFTY50"]
    series["NIFTY50"] = nifty[:-1] + [(nifty[-1][0], round(nifty[-2][1] * 1.001, 2))]
    assert attribution(series, AS_OF)["label"] == "no_significant_move"


def test_regime_is_global_risk_off_on_the_designed_day(signals):
    mood = signals["regime"]
    assert mood["label"] == "global_risk_off"
    assert {"stronger dollar", "higher US yields", "weaker rupee"} <= set(mood["risk_off_signals"])
    assert regime({}, AS_OF, {"status": "insufficient"})["label"] == "mixed"


def three_days(first, second, third=None):
    """Three closes ending on the as-of date, so the previous-session (lag 1) change is the second over the first."""
    return [("2026-11-17", first), ("2026-11-18", second), ("2026-11-19", third if third is not None else second)]


def test_commodities_are_facts_and_attribution_factors(signals):
    by_series = {f["series"]: f["text"] for f in signals["facts"]}
    assert "Gold closed at" in by_series["GOLD"] and "Brent crude closed at" in by_series["BRENT"]
    for name in ("WTI", "SILVER", "COPPER", "NATGAS"):
        assert name in by_series and "closed at" in by_series[name]
    used = {f["series"] for f in signals["attribution"]["factors"]}
    assert {"USDINR", "DXY", "BRENT", "US10Y", "GOLD", "COPPER"} == used


def test_attribution_still_works_without_commodity_data():
    series = {k: v for k, v in load_series().items() if k not in ("GOLD", "COPPER", "WTI", "SILVER", "NATGAS")}
    result = compute_signals(series, AS_OF)
    assert result["attribution"]["status"] == "ok"
    assert {f["series"] for f in result["attribution"]["factors"]} == {"USDINR", "DXY", "BRENT", "US10Y"}
    assert {m["series"] for m in result["missing"]} == {"WTI", "GOLD", "SILVER", "COPPER", "NATGAS"}


def test_regime_reads_gold_and_copper_and_names_signals_by_what_happened():
    flat = {"NIFTY50": three_days(100, 100)}
    safe_haven = regime({**flat, "GOLD": three_days(100, 102), "COPPER": three_days(100, 98)}, AS_OF, {})
    assert safe_haven["risk_off_signals"] == ["higher gold", "lower copper"] and safe_haven["risk_on_signals"] == []
    growth = regime({**flat, "GOLD": three_days(100, 98), "COPPER": three_days(100, 102)}, AS_OF, {})
    assert growth["risk_on_signals"] == ["lower gold", "higher copper"] and growth["risk_off_signals"] == []
    quiet = regime({**flat, "GOLD": three_days(100, 100.5), "COPPER": three_days(100, 100.5)}, AS_OF, {})
    assert quiet["risk_off_signals"] == quiet["risk_on_signals"] == []
    # A falling dollar is a risk-on sign and must not be reported as "stronger dollar".
    weaker = regime({**flat, "DXY": three_days(100, 99)}, AS_OF, {})
    assert weaker["risk_on_signals"] == ["weaker dollar"] and weaker["risk_off_signals"] == []


def test_regime_needs_three_agreeing_signals_to_call_a_global_move():
    series = {
        "DXY": three_days(100, 101), "GOLD": three_days(100, 102), "COPPER": three_days(100, 97),
        "BRENT": three_days(100, 100), "US10Y": three_days(4.0, 4.0),
    }
    assert regime(series, AS_OF, {})["label"] == "global_risk_off"
    two = {k: v for k, v in series.items() if k != "COPPER"}
    assert regime(two, AS_OF, {})["label"] == "mixed"


def test_stale_and_missing_series_are_reported_not_invented():
    series = load_series()
    series["DXY"] = [p for p in series["DXY"] if p[0] <= "2026-11-05"]
    del series["BRENT"]
    result = compute_signals(series, AS_OF)
    gone = {m["series"]: m["reason"] for m in result["missing"]}
    assert "DXY" in gone and "BRENT" in gone
    assert not any(f["series"] in ("DXY", "BRENT") for f in result["facts"])
    assert usable_index(series["DXY"], AS_OF) is None


# ----- the packet and its fingerprint --------------------------------------------------------------------------------


def test_packet_hash_is_stable_and_sensitive():
    fetched = fetched_from_fixture()
    packet, first = build_packet(AS_OF, fetched)
    again, second = build_packet(AS_OF, fetched_from_fixture())
    assert first == second == packet_hash(packet) and len(first) == 64
    changed = fetched_from_fixture()
    nifty = changed["NIFTY50"]
    changed["NIFTY50"] = SeriesResult("NIFTY50", nifty.points[:-1] + [(AS_OF, nifty.points[-1][1] + 1)], "fixture")
    assert build_packet(AS_OF, changed)[1] != first


def test_packet_uses_the_last_trading_day_and_labels_every_series():
    packet, _ = build_packet("2026-11-22", fetched_from_fixture())  # a Sunday
    assert packet["requested_date"] == "2026-11-22" and packet["as_of"] == AS_OF
    assert set(packet["series"]) >= {
        "NIFTY50", "SENSEX", "USDINR", "DXY", "BRENT", "US10Y", "FII_NET", "INDIAVIX", "WTI", "GOLD", "SILVER",
        "COPPER", "NATGAS",
    }
    assert all(s["status"] == "ok" for s in packet["series"].values())


def test_packet_without_the_index_is_refused_and_gaps_are_labelled():
    with pytest.raises(NoMarketData):
        build_packet(AS_OF, {})
    fetched = fetched_from_fixture()
    del fetched["DXY"]
    packet, _ = build_packet(AS_OF, fetched)
    assert packet["series"]["DXY"]["status"] == "missing" and packet["series"]["NIFTY50"]["status"] == "ok"


def test_flow_history_is_merged_with_the_fetched_day():
    flow = SeriesResult("FII_NET", [(AS_OF, -999.0)], "nse")
    fetched = {"NIFTY50": fetched_from_fixture()["NIFTY50"], "FII_NET": flow}
    history = {"2026-11-16": -100.0, "2026-11-17": -200.0, "2026-11-18": -300.0}
    packet, _ = build_packet(AS_OF, fetched, history)
    assert [p[1] for p in packet["series"]["FII_NET"]["points"]] == [-100.0, -200.0, -300.0, -999.0]


# ----- providers (network calls are replaced by canned responses) ---------------------------------------------------


class Reply:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_yahoo_parses_closes_and_uses_the_exchange_offset(monkeypatch):
    # 2026-11-19 03:45 UTC is 09:15 in India (offset 19800 s): the trading day is still the 19th.
    stamp = int(datetime(2026, 11, 19, 3, 45, tzinfo=UTC).timestamp())
    payload = {"chart": {"result": [{"meta": {"gmtoffset": 19800}, "timestamp": [stamp - 86400, stamp, stamp + 1],
                                     "indicators": {"quote": [{"close": [24500.5, None, 24400.25]}]}}]}}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Reply(payload))
    result = YahooProvider().fetch("NIFTY50", AS_OF)
    assert result is not None and result.source == "yahoo"
    assert result.points == [("2026-11-18", 24500.5), ("2026-11-19", 24400.25)]
    assert YahooProvider().fetch("FII_NET", AS_OF) is None


def test_commodity_symbols_map_to_the_right_yahoo_contracts(monkeypatch):
    asked = []

    def record(url, **kwargs):
        asked.append(url)
        raise httpx.ConnectError("not needed")

    monkeypatch.setattr(httpx, "get", record)
    for series_id in ("GOLD", "SILVER", "COPPER", "WTI", "NATGAS", "BRENT"):
        YahooProvider().fetch(series_id, AS_OF)
    assert [u.rsplit("/", 1)[1] for u in asked] == ["GC=F", "SI=F", "HG=F", "CL=F", "NG=F", "BZ=F"]


def test_providers_never_raise(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(httpx, "get", boom)
    assert YahooProvider().fetch("NIFTY50", AS_OF) is None
    monkeypatch.setattr(settings, "FRED_API_KEY", "k")
    assert FredProvider().fetch("USDINR", AS_OF) is None


def test_fred_needs_a_key_and_skips_missing_values(monkeypatch):
    payload = {"observations": [{"date": "2026-11-18", "value": "."}, {"date": "2026-11-19", "value": "84.5"}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Reply(payload))
    monkeypatch.setattr(settings, "FRED_API_KEY", "")
    assert FredProvider().fetch("USDINR", AS_OF) is None
    monkeypatch.setattr(settings, "FRED_API_KEY", "k")
    assert FredProvider().fetch("USDINR", AS_OF).points == [("2026-11-19", 84.5)]
    assert FredProvider().fetch("NIFTY50", AS_OF) is None  # no FRED id for it


def test_csv_flows_and_provider_order(tmp_path, monkeypatch):
    path = tmp_path / "flows.csv"
    path.write_text("date,fii_net_cr\n2026-11-18,-120.5\n2026-11-19,-300\n")
    result = CsvFlowProvider(str(path)).fetch("FII_NET", AS_OF)
    assert result is not None and result.points[-1] == ("2026-11-19", -300.0)
    assert CsvFlowProvider(str(tmp_path / "nope.csv")).fetch("FII_NET", AS_OF) is None
    monkeypatch.setattr(settings, "MARKETS_FIXTURE_FILE", str(FIXTURE))
    monkeypatch.setattr(settings, "MARKETS_FLOWS_CSV", str(path))
    monkeypatch.setattr(settings, "MARKETS_PROVIDERS", ["yahoo", "bogus"])
    assert [p.name for p in providers.configured_providers()] == ["fixture", "csv", "yahoo"]
    found = collect(AS_OF, [CsvFlowProvider(str(path)), FixtureProvider(FIXTURE)])
    assert found["FII_NET"].source == "csv" and found["NIFTY50"].source == "fixture"


# ----- the validator ------------------------------------------------------------------------------------------------


@pytest.fixture
def facts(signals):
    return {f["id"]: f for f in signals["facts"]}


@pytest.fixture
def attr_id(facts):
    return next(fid for fid, f in facts.items() if f["series"] == "ATTRIBUTION")


def agent(claims, **extra):
    return {"stance": "A view on the day", "thesis": "Because of the facts.", "claims": claims, "caveats": [], **extra}


def claim(text, ids, kind="observation"):
    return {"text": text, "kind": kind, "fact_ids": ids}


def test_figures_ignore_dates_ids_and_small_integers():
    assert figures("On 2026-11-19 the 5-day move in M12 was two points") == []
    shown = {s.strip(): v for s, v in figures("NIFTY fell 0.9% to 23,751.45 after USD/INR rose 8.0 bps")}
    assert shown["0.9%"] == 0.9 and shown["23,751.45"] == 23751.45 and shown["8.0 bps"] == 8.0


def test_a_grounded_answer_is_accepted_and_claims_get_ids(facts):
    answer = agent([claim("NIFTY 50 fell 0.9% on the day.", ["M1"]), claim("The index closed near 23,751.", ["M1"])])
    clean, rejections = validate_agent(answer, "bull", facts, {})
    assert rejections == [] and clean is not None
    assert [c["id"] for c in clean["claims"]] == ["bull-1", "bull-2"]
    assert "attribution" not in clean


@pytest.mark.parametrize(
    ("claims", "code"),
    [
        ([claim("It fell.", []), claim("It fell again.", ["M1"])], "NO_CITATION"),
        ([claim("It fell.", ["M999"]), claim("It fell again.", ["M1"])], "UNKNOWN_FACT"),
        ([claim("NIFTY 50 fell 2.5% on the day.", ["M1"]), claim("Fine.", ["M1"])], "FIGURE_MISMATCH"),
        ([claim("NIFTY 50 will reach 25,000 next week.", ["M1"]), claim("Fine.", ["M1"])], "PREDICTION"),
        ([claim("Only one claim.", ["M1"])], "CLAIM_COUNT"),
    ],
)
def test_the_validator_rejects_each_kind_of_bad_claim(facts, claims, code):
    clean, rejections = validate_agent(agent(claims), "bull", facts, {})
    assert clean is None and code in {r["code"] for r in rejections}


def test_figure_rejection_names_the_nearest_real_figure(facts):
    answer = agent([claim("NIFTY 50 fell 2.5%.", ["M1"]), claim("Ok.", ["M1"])])
    _, rejections = validate_agent(answer, "bull", facts, {})
    assert "does not appear in the facts it cites" in rejections[0]["message"] and "0.9" in rejections[0]["message"]


def test_a_malformed_answer_is_rejected_with_a_reason(facts):
    clean, rejections = validate_agent({"stance": "x"}, "bull", facts, {})
    assert clean is None and rejections[0]["code"] == "BAD_SHAPE"


def test_skeptic_rules(facts, attr_id, signals):
    ok_claims = [claim("The attribution fact reads the move as imported.", [attr_id], "inference"),
                 claim("NIFTY 50 fell 0.9%.", ["M1"])]
    attribution_fact = signals["attribution"]

    clean, rejections = validate_agent(agent(ok_claims, attribution="imported", attribution_reasoning="Dollar."),
                                       "skeptic", facts, attribution_fact)
    assert rejections == [] and clean["attribution"] == "imported"

    _, missing = validate_agent(agent(ok_claims), "skeptic", facts, attribution_fact)
    assert missing[0]["code"] == "MISSING_ATTRIBUTION"

    _, uncited = validate_agent(
        agent([claim("NIFTY 50 fell 0.9%.", ["M1"]), claim("Also 0.9%.", ["M1"])], attribution="imported",
              attribution_reasoning="x"), "skeptic", facts, attribution_fact)
    assert "NO_ATTRIBUTION_CITATION" in {r["code"] for r in uncited}

    _, contradicts = validate_agent(agent(ok_claims, attribution="domestic", attribution_reasoning="x"),
                                    "skeptic", facts, attribution_fact)
    assert "ATTRIBUTION_CONTRADICTS" in {r["code"] for r in contradicts}
    # Disagreeing is allowed when the skeptic says so openly.
    for label in ("unclear", "mixed"):
        accepted, rej = validate_agent(agent(ok_claims, attribution=label, attribution_reasoning="Model is weak."),
                                       "skeptic", facts, attribution_fact)
        assert rej == [] and accepted is not None


def verdict(**over):
    base = {
        "summary": "A weak session led by the dollar.", "attribution_view": "Mostly imported, low confidence.",
        "key_drivers": [{"text": "NIFTY 50 fell 0.9%.", "fact_ids": ["M1"]}],
        "bull_strongest": "Valuations are supportive.", "bear_strongest": "Flows are negative.",
        "what_would_change": ["A reversal in the dollar index"], "data_gaps": [], "conclusion": "Cautious.",
    }
    return {**base, **over}


def test_verdict_validation_and_confidence_cap(facts, signals):
    clean, rejections = validate_verdict(verdict(), facts, [], signals["attribution"])
    assert rejections == [] and clean["confidence"] == signals["attribution"]["confidence"] == "moderate"
    weak, _ = validate_verdict(verdict(), facts, [], {"status": "ok", "confidence": "low"})
    assert weak["confidence"] == "low"  # a weak attribution fit caps confidence, whatever the model says
    insufficient, _ = validate_verdict(verdict(), facts, [], {"status": "insufficient"})
    assert insufficient["confidence"] == "low"
    assert any("not investment advice" in x for x in clean["limitations"])
    _, bad = validate_verdict(verdict(key_drivers=[{"text": "x", "fact_ids": ["M404"]}]), facts, [], {})
    assert bad[0]["code"] == "UNKNOWN_FACT"
    _, wrong = validate_verdict(verdict(conclusion="NIFTY 50 will hit 99,999."), facts, [], {})
    assert wrong
    strong = {"status": "ok", "confidence": "moderate"}
    gaps, _ = validate_verdict(verdict(), facts, [{"series": "BRENT", "reason": "x"}], strong)
    assert gaps["confidence"] == "low" and "BRENT" in gaps["limitations"][-1]
    ok, _ = validate_verdict(verdict(), facts, [], strong)
    assert ok["confidence"] == "moderate"


# ----- the pipeline: agents, the retry edge, freezing, resuming -------------------------------------------------------


class StubLLM:
    """Answers each market prompt with valid, grounded JSON, and can be told to misbehave for one agent."""

    def __init__(self):
        self.calls: list[dict] = []
        self.script: dict[str, list[dict]] = {}  # role -> replies to use before behaving normally

    def role(self, system: str) -> str:
        if "bull analyst" in system:
            return "bull"
        if "bear analyst" in system:
            return "bear"
        if "macro skeptic" in system:
            return "skeptic"
        return "moderator"

    def good(self, role: str, user: str) -> dict:
        attr = next((m.group(1) for m in __import__("re").finditer(r"\[(M\d+)\] \(ATTRIBUTION\)", user)), "M1")
        if role == "moderator":
            return verdict()
        data = agent([claim("NIFTY 50 fell 0.9% on the day.", ["M1"]),
                      claim("The attribution fact frames the move.", [attr], "inference")])
        if role == "skeptic":
            data.update(attribution="imported", attribution_reasoning="The dollar and the rupee line up with the fall.")
        return data

    def __call__(self, system, user, max_tokens=1024, fast=False):
        role = self.role(system)
        self.calls.append({"role": role, "user": user})
        queue = self.script.get(role, [])
        if queue:
            reply = queue.pop(0)
            return reply if isinstance(reply, str) else json.dumps(reply)
        return json.dumps(self.good(role, user))

    def count(self, role: str) -> int:
        return sum(1 for c in self.calls if c["role"] == role)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(settings, "PERSPECTIVE_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(settings, "MARKETS_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "MARKETS_ENABLED", True)
    monkeypatch.setattr(pipeline, "configured_providers", lambda: [FixtureProvider(FIXTURE)])


@pytest.fixture
def stub(monkeypatch):
    model = StubLLM()
    monkeypatch.setattr(llm, "invoke", model)
    return model


async def test_a_full_day_runs_and_is_stored(fake_redis, stub):
    assert await pipeline.run_market_day(AS_OF) == AS_OF
    record = await store.get(AS_OF)
    assert record["status"] == "done" and record["stage"] == "finished"
    statuses = {r: a["status"] for r, a in record["agents"].items()}
    assert statuses == dict.fromkeys(("bull", "bear", "skeptic"), "completed")
    assert record["verdict"]["based_on"] == {"analysts": 3, "of": 3, "facts": len(record["packet"]["facts"])}
    assert record["agents"]["skeptic"]["content"]["attribution"] == "imported"
    assert len(record["packet_sha256"]) == 64
    assert [c["role"] for c in stub.calls].count("moderator") == 1 and len(stub.calls) == 4  # 3 agents + moderator
    # The skeptic saw the other analysts' accepted positions.
    assert "accepted positions" in next(c["user"] for c in stub.calls if c["role"] == "skeptic")
    assert (await store.list_dates(10, 0)) == [AS_OF] and await store.latest_date() == AS_OF


async def test_the_retry_edge_sends_the_rejection_reason_back(fake_redis, stub):
    stub.script["bear"] = [agent([claim("NIFTY 50 fell 7.5%.", ["M1"]), claim("Ok.", ["M1"])])]
    await pipeline.run_market_day(AS_OF)
    bear = (await store.get(AS_OF))["agents"]["bear"]
    assert bear["status"] == "completed" and bear["attempts"] == 2
    assert [a["outcome"] for a in bear["audit"]] == ["rejected", "accepted"]
    assert bear["audit"][0]["rejections"][0]["code"] == "FIGURE_MISMATCH"
    retry_prompt = [c["user"] for c in stub.calls if c["role"] == "bear"][1]
    assert "REJECTED by the validator" in retry_prompt and "7.5%" in retry_prompt


async def test_unusable_and_provider_failures_use_up_attempts_then_fail_cleanly(fake_redis, stub):
    stub.script["bear"] = ["not json at all", "still { not json", "{}"]
    await pipeline.run_market_day(AS_OF)
    record = await store.get(AS_OF)
    bear = record["agents"]["bear"]
    assert bear["status"] == "failed" and bear["attempts"] == 3 and record["status"] == "partial"
    assert [a["outcome"] for a in bear["audit"]] == ["unusable", "unusable", "rejected"]
    assert record["verdict"]["based_on"]["analysts"] == 2  # the verdict uses only validated agents
    assert record["agents"]["bull"]["status"] == "completed"


async def test_a_stubborn_skeptic_that_contradicts_the_computation_fails_after_bounded_retries(fake_redis, stub):
    bad = stub.good("skeptic", "")
    bad.update(attribution="domestic")
    stub.script["skeptic"] = [bad, bad, bad, bad]
    await pipeline.run_market_day(AS_OF)
    record = await store.get(AS_OF)
    assert stub.count("skeptic") == 3  # MARKETS_MAX_ATTEMPTS, no more
    assert record["agents"]["skeptic"]["status"] == "failed" and record["status"] == "partial"
    assert "ATTRIBUTION_CONTRADICTS" in str(record["agents"]["skeptic"]["audit"][-1]["rejections"])


async def test_provider_errors_are_retried_and_recorded(fake_redis, stub, monkeypatch):
    calls = {"n": 0}

    def flaky(system, user, max_tokens=1024, fast=False):
        calls["n"] += 1
        if calls["n"] <= 1:
            raise RuntimeError("rate limited")
        return stub(system, user, max_tokens, fast)

    monkeypatch.setattr(llm, "invoke", flaky)
    await pipeline.run_market_day(AS_OF)
    audits = [a["audit"] for a in (await store.get(AS_OF))["agents"].values()]
    assert any(e["outcome"] == "provider_error" for audit in audits for e in audit)


async def test_all_agents_failing_marks_the_day_failed_with_no_verdict(fake_redis, stub):
    for role in ("bull", "bear", "skeptic"):
        stub.script[role] = ["x", "y", "z"]
    await pipeline.run_market_day(AS_OF)
    record = await store.get(AS_OF)
    assert record["status"] == "failed" and record["verdict"] == {} and stub.count("moderator") == 0


async def test_a_finished_day_is_not_regenerated_but_force_does(fake_redis, stub):
    await pipeline.run_market_day(AS_OF)
    first = (await store.get(AS_OF))["packet_sha256"]
    calls = len(stub.calls)
    await pipeline.run_market_day(AS_OF)
    assert len(stub.calls) == calls  # idempotent: no new LLM calls
    await pipeline.run_market_day(AS_OF, force=True)
    assert len(stub.calls) == calls + 4 and (await store.get(AS_OF))["packet_sha256"] == first  # same data, same hash


async def test_resuming_reuses_the_frozen_packet_and_only_reruns_what_failed(fake_redis, stub, monkeypatch):
    stub.script["bear"] = ["x", "y", "z"]
    await pipeline.run_market_day(AS_OF)
    before = await store.get(AS_OF)
    assert before["status"] == "partial"
    # The data changes between runs; the stored packet must not.
    changed = load_series()
    changed["NIFTY50"][-1] = (AS_OF, changed["NIFTY50"][-1][1] + 50)
    monkeypatch.setattr(pipeline, "collect", lambda *_: {
        k: SeriesResult(k, v, "other") for k, v in changed.items()})
    calls = len(stub.calls)
    await pipeline.run_market_day(AS_OF)
    after = await store.get(AS_OF)
    assert after["packet_sha256"] == before["packet_sha256"] and after["status"] == "done"
    assert [c["role"] for c in stub.calls[calls:]].count("bull") == 0  # completed agents were not asked again
    assert stub.count("bear") == 3 + 1 and after["verdict"]["based_on"]["analysts"] == 3


async def test_no_data_creates_nothing(fake_redis, stub, monkeypatch):
    monkeypatch.setattr(pipeline, "collect", lambda *_: {})
    assert await pipeline.run_market_day(AS_OF) is None
    assert await store.latest_date() is None and stub.calls == []


async def test_a_second_worker_does_not_start_the_same_day(fake_redis, stub):
    assert await redis_store.acquire_job_lock(store.lock_id(AS_OF))
    assert await pipeline.run_market_day(AS_OF) == AS_OF
    assert stub.calls == [] and await store.get(AS_OF) is None


async def test_flows_accumulate_across_days(fake_redis, stub, monkeypatch):
    fixture = load_series()
    monkeypatch.setattr(pipeline, "collect", lambda *_: {
        "NIFTY50": SeriesResult("NIFTY50", fixture["NIFTY50"], "x"),
        "FII_NET": SeriesResult("FII_NET", [(AS_OF, -500.0)], "nse")})
    await store.save_flows([("2026-11-17", -100.0), ("2026-11-18", -200.0)])
    await pipeline.run_market_day(AS_OF)
    assert (await store.get_flows())[AS_OF] == -500.0
    assert [p[1] for p in (await store.get(AS_OF))["packet"]["series"]["FII_NET"]["points"]] == [-100.0, -200.0, -500.0]


async def test_a_stalled_generating_day_is_repaired_on_read(fake_redis, stub):
    packet, fingerprint = build_packet(AS_OF, fetched_from_fixture())
    await store.create(AS_OF, packet, fingerprint, "2026-11-19T12:00:00+00:00")
    record = await pipeline.reconcile_stalled(await store.get(AS_OF))
    assert record["status"] == "failed" and all(a["status"] == "failed" for a in record["agents"].values())
    assert "interrupted" in record["agents"]["bull"]["error"]


# ----- the API ------------------------------------------------------------------------------------------------------


@pytest.fixture
def client(fake_redis):
    with TestClient(app) as c:
        yield c


def test_admin_trigger_runs_the_day_and_the_read_api_serves_it(client, stub):
    assert client.post("/internal/run-markets").status_code == 401
    headers = {"X-Admin-Token": "secret"}
    response = client.post(f"/internal/run-markets?date={AS_OF}", headers=headers)
    assert response.status_code == 202 and response.json()["requested_date"] == AS_OF

    listing = client.get("/api/markets").json()
    assert listing["total"] == 1 and listing["items"][0]["date"] == AS_OF
    item = listing["items"][0]
    assert item["status"] == "done" and item["completed"] == 3 and item["regime"] == "global_risk_off"
    assert item["nifty_pct"] == pytest.approx(-0.9, abs=0.01) and item["attribution"] == "imported"

    latest = client.get("/api/markets/latest").json()
    assert latest["date"] == AS_OF and latest["status"] == "done"
    assert all(len(s["points"]) <= 40 for s in latest["packet"]["series"].values())
    assert latest == client.get(f"/api/markets/{AS_OF}").json()
    assert {"packet", "agents", "verdict", "packet_sha256"} <= set(latest)


def test_read_api_errors(client, stub):
    assert client.get("/api/markets/latest").status_code == 404
    assert client.get("/api/markets/not-a-date").status_code == 404
    assert client.get("/api/markets/2026-01-01").status_code == 404
    assert client.post("/internal/run-markets?date=nope", headers={"X-Admin-Token": "secret"}).status_code == 422


def test_the_feature_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(settings, "MARKETS_ENABLED", False)
    assert client.get("/api/markets").status_code == 503
    assert client.post("/internal/run-markets", headers={"X-Admin-Token": "secret"}).status_code == 503


async def test_the_evening_job_runs_for_the_current_india_date(monkeypatch):
    from backend import scheduler

    seen = []

    async def fake(day, force=False):
        seen.append(day)
        return day

    import backend.markets.pipeline as module

    monkeypatch.setattr(module, "run_market_day", fake)
    await scheduler.run_daily_markets()
    assert len(seen[0]) == 10 and seen[0][4] == "-"
