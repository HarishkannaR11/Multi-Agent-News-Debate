# Interview guide: Counterpoint (Multi-Agent News Debate)

How to present this project in an interview: the pitch, the stack, the architecture, how data flows
through the backend, the requests and responses, the code worth knowing, the bugs you fixed, and the
questions interviewers tend to ask.

> **Which code to show.** The finished project is on the branch `claude/exciting-faraday-lphld3`.
> The `main` branch still holds the original first version (it crashes when it generates a debate,
> and has none of the guardrails, tests or deployment work described here). Merge the branch into
> `main` (or show the branch) before an interviewer looks at the repository.

---

## 1. The pitch

**30 seconds**

> Counterpoint is a full-stack AI app. Every day it takes the top news story, and five AI analysts
> with different worldviews (progressive, conservative, economist, geopolitical, and a devil's
> advocate) debate it. They write opening arguments and rebuttals, a moderator writes a balanced
> verdict, and each analyst gets a bias score. Visitors can then submit their own opinion, and an
> agent agrees, challenges or extends it. The backend is FastAPI plus a LangGraph pipeline calling
> Groq-hosted LLMs, with Guardrails AI content filtering, Redis for storage, and a Next.js
> frontend. It's containerized and I wrote CI plus an AWS deployment for it.

**2 minutes**: add three things interviewers like to hear:

1. **The problem:** news is consumed through one lens. The goal is an "opinion gym" that shows
   several readings side by side and then argues with *you*.
2. **The engineering heart:** a parallel multi-agent graph with shared state, guardrail-gated
   retries, and a design that keeps LLM cost off the request path (debates are generated once a
   day, and page views only replay stored results).
3. **What you did beyond the happy path:** you audited it, found real bugs (section 9), added
   tests and CI, and containerized it.

**Resume bullets (adapt to your own words)**

- Built a multi-agent debate system with LangGraph (parallel fan-out/fan-in, guardrail-gated retry
  loop) on FastAPI, Groq LLMs and Redis; 13 LLM calls per debate, generated once daily.
- Added layered content safety (toxicity and PII guardrails on article input, every model output,
  and user input), prompt-injection fencing, per-IP and global rate limits, and fail-closed
  behavior.
- Wrote 94 automated tests (76 backend, 18 frontend), CI with Docker smoke tests, and a one-server
  AWS deployment (Docker Compose, Caddy, CloudFront, CloudFormation).

---

## 2. Tech stack, and why each piece

| Layer | Technology | Why this choice (what to say) |
|---|---|---|
| Language | Python 3.11 | Best LLM ecosystem; `asyncio` for I/O |
| API | **FastAPI** + Uvicorn | Async, Pydantic validation, automatic OpenAPI docs, first-class WebSockets |
| Orchestration | **LangGraph** (`StateGraph`) | Explicit state machine: parallel branches, conditional edges, reducers, recursion limit. Clearer and more testable than hand-rolled `asyncio.gather` plus retry loops |
| LLM | **Groq** SDK (`openai/gpt-oss-120b` main, `-20b` fast) | Very low latency inference. A "fast" model for cheap steps (topic extraction, bias scoring), the large model for arguments |
| Safety | **Guardrails AI** (ToxicLanguage via detoxify/torch, DetectPII via Presidio/spaCy, ValidLength) | Declarative validators with `on_fail` policies (`exception`, `fix`), no custom ML to maintain |
| Storage | **Redis** (`redis.asyncio`) | One store for debates (hash), an index (sorted set), locks, rate limits, opinions (list). TTLs expire old data for free |
| Scheduling | **APScheduler** (+ a protected HTTP trigger) | In-process cron for the daily job; HTTP endpoint for external cron / manual runs |
| News | NewsAPI with GNews fallback (`httpx`) | Two sources so one outage or quota limit doesn't stop the day |
| Frontend | **Next.js 14** (App Router), React 18, **TypeScript**, Tailwind | SSR-capable, typed API client, utility CSS with a small design system |
| Realtime | **WebSocket** | The debate "arrives" stage by stage; the client reconnects with backoff |
| Tests | pytest, pytest-asyncio, fakeredis; vitest | No network or API keys needed: a stubbed LLM and an in-memory Redis |
| Quality | ruff, mypy, ESLint, `tsc` | Enforced in CI |
| Packaging | Docker (multi-stage frontend, slim backend), Docker Compose | Reproducible images; models are baked in at build time |
| Edge/Infra | Caddy router, CloudFront (HTTPS), EC2, CloudFormation, Secrets Manager | One origin for site + API, so no CORS and no mixed content |
| CI | GitHub Actions | Lint, types, tests, builds both images, smoke-tests the container stack |

---

## 3. Architecture

```
                         ┌────────────────────────────── EC2 server (Docker Compose) ───────────────────────────┐
 Browser ──https──▶ CloudFront ──http──▶ Caddy :80 ──┬─ /api/*  /ws/*  /internal/*  /health ─▶ Backend (FastAPI)
                                                     └─ everything else ────────────────────▶ Frontend (Next.js)
                                                                                                    │
                                                                           Redis ◀─────────────────┤ (debates, index, locks,
                                                                                                    │  rate limits, opinions)
                          07:00 UTC cron / POST /internal/run-daily                                 ▼
                                      │                                              LangGraph pipeline ──▶ Groq LLM API
                                      └──────────────────────────────────────────▶   (fetch ▶ extract ▶ 5 analysts
                                                                                      ▶ rebuttals ▶ moderator)  ──▶ NewsAPI/GNews
                                                                                      Guardrails (local models) gates every text
```

**Three runtime paths** (this is the key mental model):

| Path | Trigger | Touches an LLM? |
|---|---|---|
| **Generate** | Daily cron or the admin endpoint | Yes (13+ calls), writes to Redis |
| **Read** | A visitor opens the site (REST + WebSocket) | **No**, replays stored data |
| **Opinion** | A visitor submits an opinion | Yes (1 call), rate limited |

**Design decisions worth defending**

1. **Generation is decoupled from viewing.** The first version started a full 13-call debate on
   every WebSocket connection: any visitor could burn the LLM budget, and the result was never
   saved. Now debates are generated once, saved, and replayed. Cost is bounded and pages are fast.
2. **State machine over scripts.** LangGraph makes the flow explicit, so each node returns a
   partial state update and the framework merges them.
3. **Fail closed.** If a content filter can't run, the request fails (HTTP 503). It never lets
   unchecked text through.
4. **Single origin** (Caddy + CloudFront) removes CORS and mixed-content problems entirely.
5. **Redis only**: no SQL database to run for a read-mostly workload with natural TTLs.

---

## 4. Backend data flow, step by step

### 4.1 Generating a debate (the main pipeline)

```
trigger ──▶ acquire lock `lock:daily:{date}` (SET NX EX)  ── already held? stop (idempotent)
   │
   ▼  LangGraph run (recursion_limit=25)
 [fetch]      NewsAPI → GNews; skip removed/empty/recently-used URLs; input-guard each candidate
   ▼
 [extract]    fast model: "one neutral, debatable sentence"                    (1 call)
   ▼
 [left] [right] [economist] [geopolitical]   ← run IN PARALLEL, each guard-checked   (4 calls)
   ▼  (fan-in: waits for all four)
 [devil]      reads the other four openings and attacks them                    (1 call)
   ▼
 [rebuttal]   5 rebuttals in parallel threads; each guard-checked
   │             failing ones regenerated (max 2 retries), then dropped          (5 calls)
   ├── some failed & retries left ──▶ back to [rebuttal]   (conditional edge)
   ▼
 [review]     moderator (fast model) decides: is a second round needed?         (1 call)
   ├── yes ──▶ [crossfire] 5 short closing statements on the moderator's question (5 calls, at most once)
   ▼
 [moderator]  verdict (guard-checked, fallback text if blocked)                 (1 call)
              bias scores 0–1 per analyst, JSON parsed + validated (retry once) (1 call)
   ▼
 save: Redis pipeline (hash + 30-day TTL + sorted-set index + seen-URL set) → mark lock "done" 36 h
```

Total: **13 LLM calls** (1 + 4 + 1 + 5 + 1 + 1), more only when a guardrail forces a retry.

### 4.2 Reading a debate

```
Browser ─ GET / ─▶ Next.js page ─ opens WS /ws/debate/latest ─▶ FastAPI
FastAPI: resolve_debate_id("latest")  → ZREVRANGE debates:index 0 0
         get_debate(date, slug)       → HGETALL debate:{date}:{slug}
         send 3 events: status "debating" → "rebuttal" → "done", then close
Browser: merges each event into React state; the cards, rebuttals, verdict and bias bars fill in.
```

### 4.3 Submitting an opinion

```
POST /api/opinion/{debate_id}  {user_id, opinion}
 1. rate-limit dependency: per-IP (10 / 60 s) and site-wide (300 / hour)   → 429
 2. Pydantic validation: user_id pattern, opinion 1–1000 chars              → 422
 3. resolve debate id ("latest" | "YYYY-MM-DD" | "date:slug")               → 404
 4. input guardrail (toxicity, length) in a worker thread                   → 422 / 503
 5. LLM: detect AGREE | CHALLENGE | EXPAND, reply, end with a question      → 502 on failure
 6. output guardrail on the reply (PII redacted)                            → 502 / 503
 7. RPUSH to `opinions:{date}:{slug}:{user_id}` (7-day TTL)
 8. return the stored entry
```

---

## 5. Requests and responses

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/debates?limit&offset` | Debate summaries, newest first | `limit` 1–100; summaries only (no transcript) |
| `GET /api/debate/{id}` | Full debate | `{id}` = `date:slug`, a bare date, or `latest`; bad id → 404 |
| `POST /api/opinion/{id}` | Submit an opinion | Rate limited; returns the reply |
| `GET /api/opinions/{id}?user_id=` | A user's earlier opinions | |
| `WS /ws/debate/{id}` | Replay a stored debate | Closes with code 4404 if not found |
| `POST /internal/run-daily?force=` | Generate today's debate | Requires `X-Admin-Token`; idempotent |
| `GET /health`, `/health/ready` | Liveness / Redis readiness | For load balancers and scripts |

**`GET /api/debate/latest`** (trimmed)

```json
{
  "id": "2026-10-01:should-governments-cap-ai-compute",
  "date": "2026-10-01",
  "created_at": "2026-10-01T06:17:42+00:00",
  "topic": "Should governments cap AI compute to slow frontier model training?",
  "status": "done",
  "arguments":   { "left": "...", "right": "...", "economist": "...", "geopolitical": "...", "devil": "..." },
  "rebuttals":   { "left": "...", "right": "..." },
  "verdict":     "Both sides raise serious points: ...",
  "bias_scores": { "left": 0.7, "right": 0.65, "economist": 0.2, "geopolitical": 0.3, "devil": 0.4 }
}
```

**`POST /api/opinion/latest`**

```json
// request
{ "user_id": "6c94262e-15f3-4a48-a98a-cdf6aabfeaa3", "opinion": "Compute caps are unworkable." }
// 200 response
{ "user_opinion": "Compute caps are unworkable.",
  "agent_response": "The right analyst makes a similar point about enforcement ...",
  "followup": "What evidence would change your mind?",
  "mode": "AGREE",                       // AGREE | CHALLENGE | EXPAND
  "timestamp": "2026-10-01T12:09:41+00:00" }
```

**Error contract** (always `{"detail": "..."}`): `404` unknown debate, `422` invalid or filtered
input, `429` rate limited, `502` LLM or filtered reply, `503` content filter or Redis unavailable.

**WebSocket messages** (three, then close): `{debate_id, topic, status, data (arguments), rebuttals,
verdict, bias_scores}` for `status` = `debating`, `rebuttal`, `done`. Unknown debate:
`{"error":"not_found","message":...}` then close code `4404`.

---

## 6. Data model (Redis)

| Key | Type | Content | TTL |
|---|---|---|---|
| `debate:{date}:{slug}` | hash | topic, verdict, `arguments`/`rebuttals`/`bias_scores` as JSON, `created_at`, `source_url` | 30 days |
| `debates:index` | sorted set | member `date:slug`, score = created-at epoch | pruned by score |
| `seen:urls` | sorted set | recently debated article URLs | 14 days |
| `opinions:{date}:{slug}:{user_id}` | list | JSON entries | 7 days |
| `lock:daily:{date}` | string | `SET NX EX` guard for the daily run | 30 min, then 36 h once done |
| `rate:{bucket}` | counter | fixed-window rate limit | window length |

Why the sorted-set index: the first version listed debates with `SCAN` plus one `GET` per key
(O(N) round trips). `ZREVRANGE` plus one pipelined fetch is two round trips and gives pagination.

---

## 7. The code worth knowing

### 7.1 Shared state with a reducer (`graph/state.py`)

```python
def merge_dicts(left, right):
    return {**(left or {}), **(right or {})}

class DebateState(TypedDict, total=False):
    arguments: Annotated[dict, merge_dicts]   # parallel nodes each add one key
    rebuttal_retries: int                     # must be in the schema or LangGraph drops it
    ...
```

*Say:* parallel branches write to the same key in the same step; LangGraph rejects that unless the
key has a **reducer**. Nodes return only the keys they changed.

### 7.2 Graph wiring (`graph/graph.py`)

```python
for persona in PARALLEL_PERSONAS:            # fan-out: 4 analysts at once
    g.add_edge("extract", persona)
g.add_edge(list(PARALLEL_PERSONAS), "devil") # fan-in: devil waits for ALL four
g.add_edge("devil", "rebuttal")
g.add_conditional_edges("rebuttal", route_after_rebuttal,
                        {"review": "review", "rebuttal": "rebuttal"})
g.add_conditional_edges("review", route_after_review,
                        {"crossfire": "crossfire", "moderator": "moderator"})  # the moderator steers the flow
g.add_edge("crossfire", "moderator")        # no edge back to review: the extra round runs at most once
# run with config={"recursion_limit": 25}   ← a stuck loop fails fast instead of burning LLM calls
```

### 7.3 Guardrail-gated retry (`graph/nodes/rebuttal.py`)

```python
kept = dict(state.get("rebuttals") or {})
todo = [k for k in PERSONAS if k in state["arguments"] and k not in kept]
with ThreadPoolExecutor(max_workers=max(1, len(todo))) as pool:      # LLM calls are I/O: parallelize
    drafts = dict(zip(todo, pool.map(lambda k: _generate(k, state), todo), strict=True))
failed = []
for key, draft in drafts.items():                                      # check sequentially (torch)
    result = check_output(draft)
    if result.passed:
        kept[key] = result.text                                        # guard-fixed (PII-redacted) text
    else:
        failed.append(key)
retries = state.get("rebuttal_retries", 0)
retry = bool(failed) and retries < settings.MAX_REBUTTAL_RETRIES
return {"rebuttals": kept, "rebuttal_retries": retries + 1 if retry else retries,
        "guardrail_output_pass": not retry, ...}
```

*Say:* only failing rebuttals are regenerated; passing ones are kept. After the retry cap the
failures are **dropped, never published**. The conditional edge loops back only while `retry`.

### 7.4 Generate, then validate (`graph/guarded.py`)

```python
for attempt in range(1, retries + 2):
    result = check_output(llm.invoke(system=system, user=user, max_tokens=max_tokens, fast=fast))
    if result.passed:
        return result.text          # PII-redacted text from the guard
return None                          # the caller decides how to degrade
```

### 7.5 A guard that never silently passes (`graph/guardrails/common.py`)

```python
try:
    if self._guard is None:
        self._guard = self._factory()          # lazy: torch models load on first use, not at import
    outcome = self._guard.validate(text)
except ValidationError as exc:
    return GuardResult(False, text, str(exc))  # content was blocked: a normal result
except Exception as exc:
    raise GuardUnavailable(...) from exc       # the guard is broken: fail CLOSED
```

*Say:* distinguish "the content was bad" from "the checker is broken". The original code caught
both as one `except Exception` and treated them the same.

### 7.6 Idempotent daily job (`scheduler.py` + `redis_service.py`)

```python
if not await acquire_daily_lock(date):      # SET lock:daily:{date} 1 NX EX 1800
    return None                              # another replica / earlier trigger owns today
...retry up to DAILY_RUN_ATTEMPTS...
await mark_daily_done(date)                  # keep the lock 36 h on success
await release_daily_lock(date)               # after the final failure, allow a later retry
```

*Say:* `SET NX` is an atomic distributed lock; the TTL means a crashed worker can't block forever.

### 7.7 Rate limiting and client IP (`routers/deps.py`)

```python
hops = x_forwarded_for.split(",")
ip = hops[-TRUSTED_PROXY_HOPS]               # count from the RIGHT: left entries are client-controlled
allowed = await rate_limit_allow(f"opinion:{ip}", limit, window)   # SET NX EX, then INCR
# plus a site-wide hourly cap that protects the LLM quota even if every client looks like one IP
```

*Say:* never trust the first `X-Forwarded-For` entry; take the Nth from the right, where N is the
number of proxies you control. Create the key with its TTL **before** `INCR` so a crash can't leave
an immortal counter.

### 7.8 WebSocket replay (`routers/ws.py`)

Accept, resolve the id, load the debate, send three stage events, close. No LLM call, so opening
the page costs nothing.

### 7.9 Error mapping that survives CORS (`routers/opinion.py`)

```python
try:
    result = await run_in_threadpool(handle_opinion, debate, screened.text)   # sync LLM off the event loop
except Exception:
    raise HTTPException(502, "The debate agents are unavailable. Try again later.") from None
```

*Say:* an unhandled 500 is produced *outside* the CORS middleware, so a cross-origin browser
reports a network error. Converting it to an `HTTPException` keeps the CORS headers and the
message.

### 7.10 Resilient WebSocket client (`frontend/lib/api.ts`)

Reconnect with exponential backoff (1, 2, 4, 8, 15 s, max 5 tries); stop retrying once the debate
is `done` or the server says `not_found`; derive `wss://` from the page protocol so an https page
never opens `ws://`.

### 7.11 Defensive parsing of LLM output (`graph/nodes/moderator.py`)

`parse_bias_scores` regex-extracts the JSON, drops unknown keys and non-numbers, rejects booleans
(`True` is an `int` in Python), clamps to 0–1, and the node retries once. *Never trust model output
as structured data.*

---

## 8. Cross-cutting topics

**Security (layered):**
1. Input guardrail on fetched articles (toxicity, length), and a rejected article is *skipped*.
2. Prompt-injection fencing: untrusted text goes inside `<article>` / `<user_opinion>` tags and the
   system prompt says to treat it as data, never instructions.
3. Output guardrail on every model output (toxicity, PII redaction).
4. Input validation (Pydantic): length limits, `user_id` regex.
5. Per-IP and global rate limits; token-protected admin endpoint (constant-time compare).
6. Fail-closed behavior when a guard or Redis is down.
7. Deployment: no SSH, secrets in Secrets Manager, non-root containers, Guardrails telemetry off.

**Reliability:** idempotent daily job with a lock; retries around the whole run; Groq client retries
with backoff; two news sources; health endpoints; graph `recursion_limit`; guard-failure degradation
(drop a rebuttal, fallback verdict) instead of failing the whole debate.

**Testing:** 76 backend tests (stubbed LLM, `fakeredis`) cover the graph, retry loop, parsing, API,
WebSocket, rate limits, scheduler retries and an end-to-end run. 18 frontend tests cover URL
derivation, error handling and the reconnect logic. CI also builds the images, runs the guardrails
offline, and tests the whole container stack through the proxy.

**Observability:** structured JSON logs (`LOG_FORMAT=json`); optional LangSmith tracing, with each
run named and tagged by date.

**Frontend:** App Router pages `/`, `/debate/[id]`, `/archive`; components `AgentCard`,
`AgentStatusDots`, `VerdictPanel`, `BiasChart`, `OpinionBox`; an anonymous per-browser id in
`localStorage`; accessible status regions and error/loading pages.

**Deployment:** two Dockerfiles; compose runs Redis, backend, frontend and Caddy; CloudFront gives
HTTPS; a CloudFormation template creates the server, IAM role, secret, Elastic IP and budget alert.

---

## 9. Bugs you found and fixed: your best interview stories

Use the **STAR** shape: situation, what you found, how you proved it, the fix.

| # | Problem | How it was found | Fix |
|---|---|---|---|
| 1 | The graph **crashed on every run** (`InvalidUpdateError`): five parallel nodes each returned the whole state | Ran the graph with a stubbed LLM | Nodes return partial updates; `arguments` got a merge reducer |
| 2 | A guardrail failure looped **until LangGraph's default recursion limit of ~10,000 steps** (tens of thousands of LLM calls, since each step regenerated five rebuttals): the retry counter wasn't in the state schema, so LangGraph discarded it | Forced the guard to fail in a test | Counter is a schema field, only failing rebuttals retry, hard `recursion_limit`; mutation test confirms it |
| 3 | Every page view started a **paid 13-call debate** and never saved it | Code review | Decoupled generation from viewing; WebSocket replays stored data |
| 4 | Default Groq models were **deprecated** | Checked provider docs | New defaults; reasoning-model token headroom; empty-reply check |
| 5 | The input guard result was **computed and ignored**; broken guards silently passed | Code review | Enforced it; `GuardUnavailable` fails closed |
| 6 | An LLM failure showed in the browser as **"network error"**: an unhandled 500 skips CORS headers | Driving the real UI in a headless browser | Map failures to `HTTPException` (502) |
| 7 | CI's Docker build failed: NLTK data (`punkt_tab`) missing, **so the real toxicity guard would have failed on every call** | CI on the real container | Download data into a shared dir at build time; offline smoke test |
| 8 | The library **sent telemetry** to a third-party endpoint by default | Read the CI log, then proved an in-process switch did *not* stop it | Config file in the image, a warning in the app, and a test |
| 9 | Secrets file kept loose permissions on re-run | Wrote a test for the bootstrap step | `fchmod 600` every time |

*The pattern interviewers value:* you didn't just write code, you **tested adversarially**, proved
the failure, then fixed the root cause.

---

## 10. What interviewers expect, and likely questions

**What they are judging**

- Can you **explain the whole system** at several depths (30 s, 2 min, whiteboard)?
- Do you know **why** you chose each tool and the **trade-offs**?
- Can you reason about **failure, cost, scale and security**, not just the happy path?
- Is it **your** code: can you walk through any file and defend it?
- Are you honest about **limits** and what you would do next?

### LLM / agents
- **Why LangGraph instead of plain async code?** Explicit state, parallel branches with reducers,
  conditional retry edges, recursion limits, tracing hooks. Plain code works, but the control flow
  gets implicit and harder to test.
- **How do you handle bad or unsafe model output?** Guard every output, retry the failing item,
  drop it after the cap, degrade gracefully (fallback verdict), never publish unchecked text.
- **How do you stop prompt injection?** Fence untrusted text, instruct the model to treat it as
  data, validate output, never give the model tools or secrets. It reduces risk; it can't eliminate it.
- **How do you control LLM cost?** Generate once per day, replay from storage, a fast model for
  cheap steps, rate limits plus a global cap, retry caps, a recursion limit.
- **How would you evaluate output quality?** Today: bias scores and structural tests. Next: a fixed
  evaluation set, LLM-as-judge with human spot checks, and tracing.

### Backend / system design
- **Why Redis and not Postgres?** Read-mostly data with natural TTLs and tiny records; a sorted-set
  index covers listing. I'd add Postgres if I needed queries, users or analytics.
- **How do you scale it?** The app is stateless apart from Redis: add replicas behind a load
  balancer; the Redis lock keeps the daily job single-run; the guardrail models are per-process
  (~2–3 GB), so I would split the content filter into its own service or use a hosted moderation API.
- **Why WebSocket if it only replays?** It gives the "debate unfolding" experience and a place to
  stream real per-node updates later; REST alone would also work.
- **What happens if the LLM or news API is down?** Client retries with backoff, the second news
  source, whole-run retries (3×), the lock is released so a later trigger can retry, and the old
  debate stays visible.
- **How do you make a job idempotent / safe with several replicas?** Atomic `SET NX EX` lock plus a
  "done" marker; compare with a DB unique constraint.
- **Sync vs async?** FastAPI is async; blocking LLM and torch calls run in worker threads so the
  event loop stays free.

### Security
- Where does untrusted input enter? (news text, user opinions.) How is each handled? (section 8.)
- Why count `X-Forwarded-For` from the right? (spoofing.) What if the server is reached directly?
  (a limitation: the global cap and admin token still hold; lock the security group down.)

### Frontend
- Why Next.js? Why a WebSocket client with backoff? How do you avoid `ws://` on an https page?
  How is the anonymous user id stored, and what are its limits (no auth, so not private)?

### DevOps
- Why bake the models into the image? Fast start, offline runtime, a reproducible build.
- What does your CI prove, and what doesn't it? (It builds, tests and smoke-tests the container
  stack; it does not prove cloud creation or real LLM behavior.)
- Why one EC2 server and not ECS or EKS? Cheapest and simplest for a demo; ECS is the natural next
  step; EKS is overkill for one small app.

### "What would you improve?" (have a short list ready)
1. Real authentication (user ids are client-supplied today).
2. True streaming of per-node results to the browser during generation.
3. Replace the local content filter with a lighter service, or move it out of process.
4. Evaluation pipeline and observability dashboards (token cost per run, guardrail pass rates).
5. Multiple topics per day, and full article text instead of a short summary.
6. Move off in-process scheduling to a managed scheduler with alerts.

---

## 11. Be honest about the limits

Say it plainly; interviewers respect it and probe overclaims:

- **Tested** with a stubbed LLM and news source plus a real Redis and a real browser, and with the
  real content-filter models inside the container in CI.
- **Not run in production**, and not exercised against live Groq/news keys in my tests. The
  AWS template is validated by linters and CI but not created on a real account.
- It's a **learning project**: no user accounts, and one topic per day.

**Good phrasing:** "I validated the pipeline end to end with a stubbed model and found and fixed
nine real defects. The remaining risk is real-provider behavior and cloud deployment, which I
planned to verify at first deploy."

---

## 12. Numbers to remember

| Fact | Value |
|---|---|
| Analysts / LLM calls per debate | 5 / **13** (1 extract + 4 openings + 1 devil + 5 rebuttals + verdict + bias) |
| Guardrail retries | 2 per item; then drop (rebuttal), fallback (verdict) or skip (opening) |
| Graph recursion limit | 25 |
| Rate limits | 10 / 60 s per client; 300 / hour site-wide |
| Opinion length | 1–1000 characters |
| Data retention | debates 30 days, opinions 7 days, seen-URL window 14 days |
| Daily run | 07:00 UTC; lock 30 min, then 36 h once done |
| Models | `openai/gpt-oss-120b` main, `openai/gpt-oss-20b` fast |
| Code size | ~1,400 lines backend, ~1,060 lines frontend, ~720 lines of tests |
| Tests | 76 backend + 18 frontend |

---

## 13. A 3-minute live demo script

1. Open the site: show the topic, the five analyst cards, then the rebuttals and the verdict with
   the bias bars. *"Each card is one agent with its own system prompt."*
2. Submit an opinion: show the mode (agree/challenge/expand) and the follow-up question; reload and
   show the thread persists.
3. Open `/api/docs` (FastAPI's OpenAPI page) and show `GET /api/debate/latest`.
4. Show `graph/graph.py`: *"This is the whole pipeline: fan-out, fan-in, retry edge."*
5. Show one test: the always-failing guardrail terminates (`test_graph.py`). *"This test would have
   caught the infinite loop I found."*
6. Show the CI run and the compose stack: *"Tests, lint, type checks, and a container smoke test."*

Practice saying the *why* for each step, not only the *what*.
