"""The deterministic signal layer: turns a packet's raw series into numbered facts, a statistical attribution of the
index move (how much of it lines up with imported factors) and a rule-based regime label.

Everything here is plain arithmetic on the packet's numbers. No model is involved and nothing is random, so the same
series always give the same facts. That is the point: agents reason over these facts, and the validator checks their
claims against them."""
import math  # square roots for volatility
from bisect import bisect_left, bisect_right  # fast lookups in sorted date lists
from datetime import date  # calendar arithmetic on ISO dates

from .packet import ANCHOR, MAX_STALE_DAYS, SERIES

# The imported factors the attribution model uses, and how many series observations each is lagged. India closes
# before the US session, so a dollar-index, crude or US-yield move on day D shows up in Indian prices on day D+1.
# Gold (a safe-haven and import-bill signal for India) and copper (a global-growth signal) join crude and the dollar.
ATTRIBUTION_FACTORS = {"USDINR": 0, "DXY": 1, "BRENT": 1, "US10Y": 1, "GOLD": 1, "COPPER": 1}
# Trailing trading days used to fit the attribution model, and the least that makes a fit meaningful.
TRAIN_DAYS = 60
MIN_TRAIN_ROWS = 30
# Ridge penalty on the standardised factors: keeps the fit stable with few observations.
RIDGE = 1.0
# A move smaller than this (in percent) is not worth attributing.
MIN_MOVE_PCT = 0.25


# ---- small helpers ---------------------------------------------------------------------------------------------------


def _day(text: str) -> date:
    return date.fromisoformat(text)


def _fmt(value: float, places: int = 2) -> str:
    return f"{value:,.{places}f}"


def _signed(value: float, places: int = 2) -> str:
    return f"{value:+,.{places}f}"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


# Sample standard deviation (0 when there are fewer than two values).
def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


# Day-over-day change of a series as {date: change}. scale=1 gives percent for ratios when pct=True; for yields
# (pct=False) the plain difference times scale gives basis points.
def changes(points: list[tuple[str, float]], pct: bool = True, scale: float = 1.0) -> dict[str, float]:
    out: dict[str, float] = {}
    for (_, previous), (day, value) in zip(points, points[1:], strict=False):
        if pct:
            if previous:
                out[day] = (value / previous - 1.0) * 100.0
        else:
            out[day] = (value - previous) * scale
    return out


# Index of the latest point on or before a date, or None.
def _at_or_before(points: list[tuple[str, float]], day: str) -> int | None:
    index = bisect_right([p[0] for p in points], day) - 1
    return index if index >= 0 else None


# Is this series current enough to use on the as-of date? Returns the index of its latest usable point or None.
def usable_index(points: list[tuple[str, float]], as_of: str) -> int | None:
    index = _at_or_before(points, as_of)
    if index is None:
        return None
    if (_day(as_of) - _day(points[index][0])).days > MAX_STALE_DAYS:
        return None
    return index


# The change on the latest date strictly before `day` (lag 1), or exactly on `day` (lag 0).
def _factor_change(chg: dict[str, float], dates: list[str], day: str, lag: int) -> float | None:
    if lag == 0:
        return chg.get(day)
    index = bisect_left(dates, day) - 1
    return chg[dates[index]] if index >= 0 else None


# Solves A x = b for a small square system (Gaussian elimination with partial pivoting). None if singular.
def solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    n = len(vector)
    a = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for row in range(col + 1, n):
            factor = a[row][col] / a[col][col]
            for k in range(col, n + 1):
                a[row][k] -= factor * a[col][k]
    x = [0.0] * n
    for row in range(n - 1, -1, -1):
        x[row] = (a[row][n] - sum(a[row][k] * x[k] for k in range(row + 1, n))) / a[row][row]
    return x


# ---- attribution -----------------------------------------------------------------------------------------------------


# Splits the anchor index's move on `as_of` into the part that lines up with imported factors and the remainder.
def attribution(series: dict[str, list[tuple[str, float]]], as_of: str) -> dict:
    """A ridge regression of the index's daily % change on the lagged imported factors over the trailing window.
    'explained' is what those factors would have predicted today; 'residual' is everything else (domestic news,
    flows, noise). This is statistical association, not proof of cause, and the result says so through `confidence`."""
    anchor = series.get(ANCHOR, [])
    anchor_chg = changes(anchor)
    if as_of not in anchor_chg:
        return {"status": "insufficient", "reason": "no index move is available for the as-of date"}
    actual = anchor_chg[as_of]

    # The factors that have data for today.
    chg: dict[str, dict[str, float]] = {}
    dates: dict[str, list[str]] = {}
    today: dict[str, float] = {}
    for name, lag in ATTRIBUTION_FACTORS.items():
        points = series.get(name, [])
        if usable_index(points, as_of) is None:
            continue
        c = changes(points, pct=(name != "US10Y"), scale=100.0)
        chg[name], dates[name] = c, sorted(c)
        value = _factor_change(c, dates[name], as_of, lag)
        if value is not None:
            today[name] = value
    names = sorted(today)
    if len(names) < 2:
        return {"status": "insufficient", "reason": "fewer than two imported factors have data", "actual_pct": actual}

    # Training rows: the trailing index days before today for which every factor has a value.
    rows: list[list[float]] = []
    target: list[float] = []
    for day in [d for d in sorted(anchor_chg) if d < as_of][-TRAIN_DAYS:]:
        values = [_factor_change(chg[n], dates[n], day, ATTRIBUTION_FACTORS[n]) for n in names]
        if all(v is not None for v in values):
            rows.append([v for v in values if v is not None])
            target.append(anchor_chg[day])
    if len(rows) < MIN_TRAIN_ROWS:
        return {
            "status": "insufficient", "reason": f"only {len(rows)} usable training days", "actual_pct": actual,
            "n_obs": len(rows),
        }

    # Standardise each factor, centre the target, solve the ridge system.
    k = len(names)
    means = [_mean([r[j] for r in rows]) for j in range(k)]
    sds = [_stdev([r[j] for r in rows]) for j in range(k)]
    keep = [j for j in range(k) if sds[j] > 1e-12]
    if len(keep) < 2:
        return {"status": "insufficient", "reason": "the imported factors did not vary", "actual_pct": actual}
    z = [[(r[j] - means[j]) / sds[j] for j in keep] for r in rows]
    y_mean = _mean(target)
    yc = [t - y_mean for t in target]
    m = len(keep)
    gram = [[sum(row[a] * row[b] for row in z) + (RIDGE if a == b else 0.0) for b in range(m)] for a in range(m)]
    rhs = [sum(row[a] * yv for row, yv in zip(z, yc, strict=True)) for a in range(m)]
    beta = solve(gram, rhs)
    if beta is None:
        return {"status": "insufficient", "reason": "the model could not be fitted", "actual_pct": actual}

    sse = sum((yv - sum(b * v for b, v in zip(beta, row, strict=True))) ** 2 for row, yv in zip(z, yc, strict=True))
    sst = sum(v * v for v in yc)
    r2 = max(0.0, 1.0 - sse / sst) if sst > 0 else 0.0

    factors = []
    explained = 0.0
    for idx, j in enumerate(keep):
        today_z = (today[names[j]] - means[j]) / sds[j]
        contribution = beta[idx] * today_z
        explained += contribution
        factors.append({
            "series": names[j], "lag": ATTRIBUTION_FACTORS[names[j]], "today_change": round(today[names[j]], 4),
            "contribution_pct": round(contribution, 4),
        })
    residual = actual - explained

    if abs(actual) < MIN_MOVE_PCT:
        label = "no_significant_move"
    elif explained * actual > 0 and abs(explained) >= 2 * abs(residual):
        label = "imported"
    elif abs(residual) >= 2 * abs(explained) or (explained * actual <= 0 and abs(residual) > abs(explained)):
        label = "domestic"
    else:
        label = "mixed"
    # Never "high": a 60-day regression on a handful of factors is suggestive, not conclusive.
    confidence = "low" if (r2 < 0.10 or len(rows) < 40) else "moderate"
    return {
        "status": "ok", "label": label, "confidence": confidence, "actual_pct": round(actual, 4),
        "explained_pct": round(explained, 4), "residual_pct": round(residual, 4), "r2": round(r2, 4),
        "n_obs": len(rows), "factors": sorted(factors, key=lambda f: -abs(f["contribution_pct"])),
        "method": (
            f"Ridge regression of the daily % change in {SERIES[ANCHOR]['label']} on USD/INR (same day) and the dollar "
            f"index, Brent and the US 10-year yield (previous US session), fitted on the last {len(rows)} trading days."
        ),
    }


# ---- regime ----------------------------------------------------------------------------------------------------------


# A rule-based label for the day: is the backdrop a global risk-off/on move, domestic-led, or mixed?
def regime(series: dict[str, list[tuple[str, float]]], as_of: str, attr: dict) -> dict:
    off: list[str] = []
    on: list[str] = []

    def lagged(name: str, pct: bool, scale: float, lag: int) -> float | None:
        points = series.get(name, [])
        if usable_index(points, as_of) is None:
            return None
        c = changes(points, pct=pct, scale=scale)
        return _factor_change(c, sorted(c), as_of, lag)

    # A big enough rise votes risk-off under `up`, a big enough fall votes risk-on under `down` (each named for what
    # actually happened, so a falling dollar is never reported as a stronger one).
    def vote(value: float | None, threshold: float, up: str, down: str) -> None:
        if value is None:
            return
        if value >= threshold:
            off.append(up)
        elif value <= -threshold:
            on.append(down)

    vote(lagged("DXY", True, 1.0, 1), 0.3, "stronger dollar", "weaker dollar")
    vote(lagged("US10Y", False, 100.0, 1), 5.0, "higher US yields", "lower US yields")
    vote(lagged("USDINR", True, 1.0, 0), 0.3, "weaker rupee", "stronger rupee")
    vote(lagged("BRENT", True, 1.0, 1), 2.0, "higher crude", "lower crude")
    vote(lagged("INDIAVIX", True, 1.0, 0), 5.0, "higher India VIX", "lower India VIX")
    vote(lagged("GOLD", True, 1.0, 1), 1.0, "higher gold", "lower gold")
    # Copper is a growth signal, so its direction reads the other way: falling copper is the risk-off sign.
    copper = lagged("COPPER", True, 1.0, 1)
    if copper is not None:
        if copper >= 1.5:
            on.append("higher copper")
        elif copper <= -1.5:
            off.append("lower copper")
    flows = series.get("FII_NET", [])
    if usable_index(flows, as_of) is not None:
        recent = [v for d, v in flows if d <= as_of][-5:]
        if len(recent) >= 3:
            total = sum(recent)
            if total < 0:
                off.append("net FII selling")
            elif total > 0:
                on.append("net FII buying")

    if len(off) >= 3 and len(off) > len(on):
        label = "global_risk_off"
    elif len(on) >= 3 and len(on) > len(off):
        label = "global_risk_on"
    elif attr.get("status") == "ok" and attr.get("label") == "domestic" and abs(attr.get("actual_pct", 0)) >= 0.5:
        label = "domestic_led"
    else:
        label = "mixed"
    return {"label": label, "risk_off_signals": off, "risk_on_signals": on}


# ---- facts -----------------------------------------------------------------------------------------------------------


class _Facts:
    """Collects facts and hands out their ids (M1, M2, ...) in a fixed order."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, series: str, kind: str, text: str, numbers: list[float], as_of: str) -> None:
        self.items.append({
            "id": f"M{len(self.items) + 1}", "series": series, "kind": kind, "text": text,
            "numbers": [round(n, 4) for n in numbers], "as_of": as_of,
        })


# Builds everything the agents get to see from the packet's series. Pure: same input, same output.
def compute_signals(series: dict[str, list[tuple[str, float]]], as_of: str) -> dict:
    facts = _Facts()
    missing: list[dict] = []

    def level_fact(name: str, pct: bool = True) -> None:
        label, unit = SERIES[name]["label"], SERIES[name]["unit"]
        points = series.get(name, [])
        index = usable_index(points, as_of)
        if index is None:
            missing.append({"series": name, "reason": "no recent data" if points else "not available"})
            return
        day, value = points[index]
        if index == 0:
            facts.add(name, "level", f"{label} closed at {_fmt(value)} {unit} on {day}.", [value], day)
            return
        previous = points[index - 1][1]
        if name == "US10Y":
            bps = (value - previous) * 100.0
            direction = "up" if bps >= 0 else "down"
            text = f"{label} closed at {_fmt(value)}% on {day}, {direction} {_fmt(abs(bps), 1)} bps on the day."
            facts.add(name, "level", text, [value, abs(bps), previous], day)
            return
        change = (value / previous - 1.0) * 100.0 if previous else 0.0
        direction = "up" if change >= 0 else "down"
        extra = ""
        if name == "USDINR":
            extra = " (a weaker rupee)" if change >= 0 else " (a stronger rupee)"
        if SERIES[name]["session"] == "us" and day < as_of:
            extra += f" in the US session on {day}, before the Indian close on {as_of}"
        text = (f"{label} closed at {_fmt(value)} on {day}, {direction} {_fmt(abs(change))}% from the previous "
                f"close ({_fmt(previous)}){extra}.")
        facts.add(name, "level", text, [value, abs(change), previous], day)

    # The anchor first: level, the size of the move compared with its normal range, and the 5 and 20 day picture.
    level_fact(ANCHOR)
    anchor = series.get(ANCHOR, [])
    anchor_chg = changes(anchor)
    if as_of in anchor_chg:
        today = anchor_chg[as_of]
        history = [v for d, v in sorted(anchor_chg.items()) if d < as_of][-60:]
        sd = _stdev(history)
        if len(history) >= 20 and sd > 0:
            sigma = today / sd
            facts.add(
                ANCHOR, "move_size",
                f"The {SERIES[ANCHOR]['label']} move of {_signed(today)}% is {_fmt(abs(sigma), 1)} standard deviations "
                f"from zero against its last {len(history)} daily moves (typical daily move {_fmt(sd)}%).",
                [abs(today), abs(sigma), sd], as_of,
            )
        index = usable_index(anchor, as_of)
        windows = []
        for n in (5, 20):
            if index is not None and index - n >= 0:
                windows.append((n, (anchor[index][1] / anchor[index - n][1] - 1.0) * 100.0))
        if windows:
            parts = " and ".join(f"{_signed(v)}% over the last {n} trading days" for n, v in windows)
            text = f"{SERIES[ANCHOR]['label']} changed {parts}."
            facts.add(ANCHOR, "trend", text, [abs(v) for _, v in windows], as_of)
        recent = [v for d, v in sorted(anchor_chg.items()) if d <= as_of][-20:]
        if len(recent) >= 15:
            vol = _stdev(recent) * math.sqrt(252)
            facts.add(ANCHOR, "volatility", f"{SERIES[ANCHOR]['label']} 20-day realised volatility is {_fmt(vol, 1)}% "
                      "annualised.", [vol], as_of)

    # The other Indian series, then the global drivers.
    level_fact("SENSEX")
    sensex_chg = changes(series.get("SENSEX", []))
    if as_of in anchor_chg and as_of in sensex_chg:
        gap = sensex_chg[as_of] - anchor_chg[as_of]
        facts.add(
            "SENSEX", "divergence",
            f"SENSEX and {SERIES[ANCHOR]['label']} differed by {_fmt(abs(gap))} percentage points on the day "
            f"(SENSEX {_signed(sensex_chg[as_of])}%, {SERIES[ANCHOR]['label']} {_signed(anchor_chg[as_of])}%).",
            [abs(gap), abs(sensex_chg[as_of]), abs(anchor_chg[as_of])], as_of,
        )
    for name in ("USDINR", "INDIAVIX", "DXY", "BRENT", "WTI", "GOLD", "SILVER", "COPPER", "NATGAS", "US10Y"):
        level_fact(name)

    # Foreign flows.
    flows = series.get("FII_NET", [])
    flow_index = usable_index(flows, as_of)
    if flow_index is None:
        missing.append({"series": "FII_NET", "reason": "no recent data" if flows else "not available"})
    else:
        day, value = flows[flow_index]
        values = [v for _, v in flows[: flow_index + 1]]
        text = f"FII/FPI net equity flow was {_signed(value)} INR crore on {day}"
        numbers = [abs(value)]
        for n in (5, 20):
            if len(values) >= n:
                total = sum(values[-n:])
                text += f"; the {n}-day total is {_signed(total)} INR crore"
                numbers.append(abs(total))
        facts.add("FII_NET", "flow", text + ".", numbers, day)

    # The attribution and the regime, as facts the agents can cite.
    attr = attribution(series, as_of)
    if attr["status"] == "ok":
        top = attr["factors"][0]
        facts.add(
            "ATTRIBUTION", "attribution",
            f"Statistical attribution of the {SERIES[ANCHOR]['label']} move of {_signed(attr['actual_pct'])}%: "
            f"imported factors line up with {_signed(attr['explained_pct'])} percentage points and "
            f"{_signed(attr['residual_pct'])} percentage points remain unexplained (domestic or noise). Reading: "
            f"{attr['label']}. Model fit R-squared {_fmt(attr['r2'])} over {attr['n_obs']} days, confidence "
            f"{attr['confidence']}. Largest factor: {SERIES[top['series']]['label']} "
            f"({_signed(top['contribution_pct'])} percentage points). This is association, not proof of cause.",
            [abs(attr["actual_pct"]), abs(attr["explained_pct"]), abs(attr["residual_pct"]), attr["r2"],
             abs(top["contribution_pct"])],
            as_of,
        )
    else:
        facts.add("ATTRIBUTION", "attribution",
                  f"No attribution was computed: {attr.get('reason', 'insufficient data')}.", [], as_of)
    mood = regime(series, as_of, attr)
    signals = ", ".join(mood["risk_off_signals"] + mood["risk_on_signals"]) or "none"
    facts.add("REGIME", "regime",
              f"Regime reading: {mood['label'].replace('_', ' ')} (signals: {signals}).", [], as_of)

    return {"facts": facts.items, "attribution": attr, "regime": mood, "missing": missing}
