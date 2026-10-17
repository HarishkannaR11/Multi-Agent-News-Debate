# Code walkthrough: every file in the project

Read this with the code open. For each file you get **what it does**, **how it works**, and
**what to say about it** in an interview. Files are grouped the way a request travels through the
system, so you can follow one story from the browser to the database and back.

**Contents**
1. [Repo map and reading order](#1-repo-map-and-reading-order)
2. [Backend: entry point, config, helpers](#2-backend-entry-point-config-helpers)
3. [Backend: HTTP layer (`routers/`)](#3-backend-http-layer-routers)
4. [Backend: the daily job (`scheduler.py`)](#4-backend-the-daily-job-schedulerpy)
5. [Backend: storage (`services/redis_service.py`)](#5-backend-storage-servicesredis_servicepy)
6. [Backend: the debate pipeline (`graph/`)](#6-backend-the-debate-pipeline-graph)
7. [Backend: the safety layer (`graph/guardrails/`)](#7-backend-the-safety-layer-graphguardrails)
8. [Frontend (`frontend/`)](#8-frontend-frontend)
9. [Tests (`backend/tests/`, `frontend/lib/api.test.ts`)](#9-tests)
10. [Docker, CI and deployment](#10-docker-ci-and-deployment)
11. [One request, end to end](#11-one-request-end-to-end)
12. [Cheat sheet: any file in 20 seconds](#12-cheat-sheet-any-file-in-20-seconds)

---

## 1. Repo map and reading order

```
backend/                      Python API + debate pipeline
  main.py                     app setup (start here)
  config.py                   settings + the LLM client
  scheduler.py                daily job
  routers/                    HTTP endpoints
  services/redis_service.py   all Redis access
  graph/                      the LangGraph pipeline, prompts, safety
  tests/                      pytest suite
  scripts/warm_models.py      downloads content-filter models at image build
frontend/                     Next.js site
  app/                        pages  ·  components/  UI pieces  ·  lib/  API client
deploy/                       AWS stack, Hugging Face bundle, trigger script
docs/                         guides (deploy, interview, this file)
.github/workflows/            CI, daily-debate cron, HF deploy
```

**Suggested reading order (about 45 minutes):** `graph/state.py` → `graph/graph.py` →
`graph/nodes/agents.py` → `graph/guarded.py` → `graph/nodes/rebuttal.py` → `scheduler.py` →
`services/redis_service.py` → `routers/opinion.py` → `frontend/components/DebateStream.tsx` →
`frontend/lib/api.ts`.

---

## 2. Backend: entry point, config, helpers

### `backend/main.py`: the application object
**Does:** creates the FastAPI app and wires everything together.

| Part | What it does |
|---|---|
| `configure_logging()` | Sets up logging once, at import time |
| `lifespan(...)` | Runs on start-up and shutdown. On start: rebuild the Redis index if it is empty, then start the scheduler. On shutdown: stop the scheduler. A Redis failure at start-up is **logged, not fatal**, so the app still boots and `/health/ready` reports the problem |
| `CORSMiddleware` | Allows only the configured origins, only `GET`/`POST`/`OPTIONS`, and only the `Content-Type` header |
| `include_router(...)` | Mounts the four routers (debate, opinion, ws, admin) |
| `@app.exception_handler(RedisError)` | Any Redis error becomes a clean **503** instead of a raw 500 |
| `/health` | **Liveness**: the process is up. Always cheap |
| `/health/ready` | **Readiness**: also pings Redis. Load balancers and scripts use it |

**Say:** liveness vs readiness is a standard distinction: liveness restarts a dead process,
readiness decides whether to send traffic.

### `backend/config.py`: settings and the LLM client
**`Settings`** is a plain class that reads environment variables once. `_bool()` parses `true/1/yes/on`.
Notable groups:
- **LLM:** `GROQ_MODEL_MAIN` / `GROQ_MODEL_FAST`, timeout, `GROQ_MAX_RETRIES`, `REASONING_TOKEN_HEADROOM`.
- **Job:** scheduler hour/minute/timezone, `DAILY_RUN_ATTEMPTS`, `ADMIN_TOKEN`.
- **Safety/limits:** `GUARDRAILS_ENABLED`, `MAX_REBUTTAL_RETRIES`, `GRAPH_RECURSION_LIMIT`,
  `MAX_OPINION_CHARS`, rate limits, `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_HOPS`.
- **Retention:** debates 30 days, opinions 7 days.

**`PERSONA_KEYS`**: the five analyst names, used to validate model output.

**`_LLMWrapper` / `llm`**: a thin wrapper over the Groq SDK.
- The client is created on **first use** (`_get_client`), so importing the module needs no API key.
  This is why tests can import everything without credentials.
- `invoke(system, user, max_tokens, fast)` picks the fast or main model.
- For `gpt-oss` models it sets `reasoning_effort="low"`, turns off returning the reasoning text, and
  **adds token headroom**, because these models spend part of `max_tokens` thinking, and a small
  budget could return an empty answer.
- It raises if the reply is empty rather than returning `""`.

**Say:** one choke-point for every LLM call means retries, timeouts, model choice and testing (swap
`llm.invoke` for a stub) all live in one place.

### `backend/timeutil.py`
`today_iso()` returns today's date **in the scheduler's timezone**, so the job's lock name and the
debate's saved date always agree.

### `backend/logging_config.py`
`JsonFormatter` writes one JSON object per log line (time, level, logger, message, exception).
`configure_logging()` picks JSON or plain text from `LOG_FORMAT`. JSON logs are what CloudWatch and
other log tools parse best.

---

## 3. Backend: HTTP layer (`routers/`)

The routers only translate HTTP to function calls and back. No business logic lives here.

### `routers/debate.py`
- `GET /api/debates?limit&offset` → `list_debates(...)`. `Query(ge=1, le=100)` validates limits.
- `GET /api/debate/{debate_id}` → resolves the id (`date:slug`, a bare date, or `latest`), loads the
  debate, returns it with its id, or **404**. Malformed ids are a 404, never a 500.

### `routers/opinion.py`: the busiest endpoint
`OpinionRequest` (Pydantic) enforces `user_id` matches `^[A-Za-z0-9_-]{1,64}$` and the opinion is
1–1000 characters.

`POST /api/opinion/{debate_id}` runs this chain (each step can stop the request):
1. **Rate-limit dependency** (`enforce_opinion_rate_limit`) → 429.
2. `_load()` → resolves the id and fetches the debate → 404.
3. `check_input` (content filter) **in a worker thread** → 422 if blocked, 503 if the filter is broken.
4. `handle_opinion` (the LLM call) in a worker thread → **502** with a friendly message on failure.
5. `check_output` on the reply → 502 if blocked.
6. `append_opinion` to Redis, return the entry.

`GET /api/opinions/{debate_id}?user_id=` returns that user's earlier opinions.

**Say:** `run_in_threadpool` keeps blocking work (LLM, torch) off the event loop. Failures are raised as
`HTTPException`, because an unhandled 500 skips the CORS middleware and the browser would only see a
"network error".

### `routers/deps.py`: rate limiting
- `client_ip(request)`: if proxy headers are trusted, take the **Nth entry from the right** of
  `X-Forwarded-For` (N = `TRUSTED_PROXY_HOPS`); entries further left are client-controlled and can be
  spoofed. Otherwise use the socket address.
- `enforce_opinion_rate_limit`: per-IP counter first (`10` per `60` s), then a **site-wide hourly cap**
  (`300`) that protects the LLM quota even if all visitors look like one IP.

### `routers/ws.py`: the WebSocket
`/ws/debate/{debate_id}` accepts the connection, resolves and loads the debate, then sends **three
messages**: status `debating` (openings), `rebuttal` (openings + rebuttals), `done` (everything +
verdict + bias scores), and closes. Unknown id → `{"error":"not_found"}` and close code **4404**.
**It never calls an LLM**, so opening a page cannot cost money.

### `routers/admin.py`: `POST /internal/run-daily`
- Disabled (503) if `ADMIN_TOKEN` is unset; 401 if the `X-Admin-Token` header is wrong. The compare
  uses `hmac.compare_digest` (**constant time**, so response time can't leak the token).
- Unless `force=true`, it tries to take the daily lock; if held it returns **200 `already_ran`**.
- Otherwise it returns **202 `accepted`** immediately and runs `generate_debate` as a **background
  task**: the caller doesn't wait for 13 LLM calls.

---

## 4. Backend: the daily job (`scheduler.py`)

| Function | Purpose |
|---|---|
| `_slugify(topic)` | Turns the topic into a URL-safe id: lowercase, non-alphanumerics → `-`, max 60 chars, `"topic"` if empty |
| `generate_debate(date)` | **Caller must hold the lock.** Up to `DAILY_RUN_ATTEMPTS` times: load recent URLs → run the graph → save → mark the lock done. Failure → log, sleep, retry. After the last failure it **releases the lock** so a later trigger can try again |
| `run_daily_debate()` | The cron entry: take the lock (skip if held), then `generate_debate` |
| `start_scheduler()` / `stop_scheduler()` | APScheduler cron at 07:00 (configurable) with `coalesce=True` (missed runs merge into one) and a 1-hour `misfire_grace_time` |

**Say:** the lock makes the job **idempotent**: a second server, a retry, or a double trigger is a
harmless no-op. `SET NX EX` is atomic, and the TTL stops a crashed worker blocking forever.

---

## 5. Backend: storage (`services/redis_service.py`)

All Redis access is in this one file. Keys (see the table in the interview guide): a **hash** per
debate, a **sorted set** index, a sorted set of seen URLs, a **list** of opinions per user, a lock
string and rate-limit counters.

| Function | What it does |
|---|---|
| `get_redis()` | Lazily creates the async client (so importing needs no Redis), `decode_responses=True` |
| `_strs()` | Normalizes Redis return types to `str` (satisfies the type checker) |
| `parse_debate_id()` | Validates `YYYY-MM-DD:slug` with a regex → `(date, slug)` or `None` |
| `_decode()` | Turns the stored hash back into a dict, parsing the JSON fields |
| `save_debate()` | One **transaction pipeline**: write the hash, set a 30-day TTL, add to the index, prune old index entries, record the source URL as "seen". Atomic and one round trip |
| `get_debate()` | `HGETALL` + decode |
| `resolve_debate_id()` | `latest` → newest in the index; a bare date → newest that day; a full id → check it exists |
| `list_debates()` | `ZREVRANGE` for ids, **one pipelined fetch** for all hashes, drops expired ones and cleans the index |
| `rebuild_index_if_empty()` | Back-fills the index from old data after an upgrade |
| `recent_source_urls()` | URLs debated in the last 14 days (so the fetcher avoids repeats) |
| `acquire_daily_lock()` / `release_…` / `mark_daily_done()` | The idempotency lock: 30 min while running, 36 h once done |
| `rate_limit_allow()` | Fixed-window limiter: `SET key 0 EX window NX` then `INCR`. The TTL is set **first**, so a crash can't leave a counter that never expires |
| `append_opinion()` / `get_opinions()` | `RPUSH` / `LRANGE` on the user's list, with a 7-day TTL |

**Say:** why a sorted-set index? The first version used `SCAN` + one `GET` per key. `ZREVRANGE` +
one pipeline is two round trips and gives pagination.

---

## 6. Backend: the debate pipeline (`graph/`)

### `graph/state.py`: the shared state
`DebateState` is a `TypedDict` (all keys optional). Two details matter:
- `arguments: Annotated[dict, merge_dicts]`, a **reducer**. Four analysts run in parallel, each
  returning `{"arguments": {"left": "..."}}`; the reducer **merges** them. Without it, LangGraph raises
  "can receive only one value per step".
- `rebuttal_retries` must be **declared**: LangGraph silently drops undeclared keys, which once made
  the retry counter always 0 (an unbounded loop).

### `graph/graph.py`: wiring the graph
- `new_debate_state(seen_urls)`: the initial state.
- `run_config(date)`: `recursion_limit` (a hard cap on graph steps), plus a run name and tags for tracing.
- `route_after_rebuttal(state)`: the conditional edge: go to `review` if `guardrail_output_pass`,
  else back to `rebuttal`.
- `route_after_review(state)`: go to `crossfire` if the moderator asked for another round, else `moderator`.
- `_build()`: adds nodes; `fetch → extract`; **fan-out** `extract →` four analysts; **fan-in** four
  analysts `→ devil` (waits for all four); `devil → rebuttal`; conditional edge; `review`; optional `crossfire`; `moderator` is the end.
- `build_graph()` is `lru_cache`d: compile once, reuse.

### `graph/prompts.py`: prompt-injection fencing
`UNTRUSTED_NOTE` is appended to system prompts: text inside `<article>`/`<user_opinion>` is data,
never instructions. `article_block()`/`opinion_block()` wrap text in those tags **and strip any copy of
the tags inside the text**, so an attacker can't close the fence early. `format_arguments()` renders
other analysts' text as `[left] ...`.

### `graph/guarded.py`: generate, then validate
`generate_guarded(system, user, max_tokens, retries, label)` loops `retries + 1` times: call the LLM,
run `check_output`, return the **validated text** if it passes. After the last failure it returns
`None` and lets the **caller decide** how to degrade.

### `graph/nodes/`: one file per step

**`fetcher.py`: `fetch_news_node`**
- `_get_json`: HTTP GET with a 10 s timeout and 2 attempts.
- `_fetch_newsapi` / `_fetch_gnews`: return `[]` if no key is configured.
- `_usable`: rejects `[Removed]` titles, empty articles and URLs already used.
- `_build_context`: joins title, description and content, strips NewsAPI's `[+N chars]` marker, caps
  length.
- `_candidates`: the first source that yields usable articles wins; an HTTP error just moves on to the
  next source.
- `fetch_news_node`: runs the **input guardrail** on up to 5 candidates, **skips** any that fail, and
  returns the first clean one. Raises if there is none (the scheduler retries).

**`extractor.py`: `topic_extractor_node`**: one **fast-model** call producing a neutral, debatable
one-sentence topic. Returns `{"topic", "status": "debating"}`.

**`agents.py`: the five analysts**
- `PERSONAS`: five system prompts (left, right, economist, geopolitical, devil).
- `PARALLEL_PERSONAS`: the four that run together.
- `make_debate_node(persona_key)`: a **factory/closure**. One function produces all five graph nodes;
  each captures its own system prompt. The node builds a prompt from the topic, the fenced article and
  the other analysts' arguments, then calls `generate_guarded`. If the opening never passes the
  filter, the node returns `{}` and **that analyst sits out** (no rebuttal, no bias score).

**`second_round.py`: `review_node` and `crossfire_node`**: the moderator's optional extra round.
`parse_review()` accepts only a real JSON `true` plus a non-empty question (anything else means "no").
`review_node` asks the fast model, runs the question through the output guard, and never fails the
debate (a model error just skips the round). `crossfire_node` has each analyst answer the question
in ≤80 words; blocked answers are dropped. There is no edge from `crossfire` back to `review`, so
the round happens at most once. Switch: `SECOND_ROUND_ENABLED`.

**`rebuttal.py`: `rebuttal_node`**: the most interesting node.
1. `kept` = rebuttals that already passed (from an earlier loop).
2. `todo` = analysts that have an opening but no kept rebuttal.
3. A `ThreadPoolExecutor` runs the LLM calls **in parallel** (I/O-bound).
4. Each draft goes through `check_output`, **sequentially** (the torch model isn't made for
   concurrent use). Passing text (PII-redacted) goes into `kept`; failures go into `failed`.
5. `retry = failed and retries < MAX_REBUTTAL_RETRIES`.
6. Returns the merged `rebuttals`, the updated counter and `guardrail_output_pass = not retry`.
   Failures that exhaust the retries are **dropped, never published**.

**`moderator.py`: `moderator_node`**
- Refuses to run if **no** analyst argument passed (nothing to moderate).
- `debate_transcript` renders openings, rebuttals and (if present) closing statements.
- The verdict uses `generate_guarded`; if blocked every time, it publishes `VERDICT_FALLBACK`.
- Bias scores: **fast model**, parsed by `parse_bias_scores` (regex for the JSON, rejects non-objects,
  keeps only known persona keys, rejects booleans because `True` is an `int` in Python, clamps to
  0–1); up to 2 attempts, else an empty dict.

**`opinion.py`: `handle_opinion`** (outside the graph)
- Builds one prompt containing the debate and the fenced opinion, asking the model to detect
  AGREE/CHALLENGE/EXPAND, reply, and end with a question.
- Regex extracts the `[Mode: …]` tag (default `EXPAND`), removes it, and splits the **last sentence**
  off as the follow-up question if it ends in `?`.

---

## 7. Backend: the safety layer (`graph/guardrails/`)

### `common.py`
- **`GuardResult(passed, text, reason)`**: the outcome of a check. `text` is the validated, possibly
  *fixed* text (PII redacted).
- **`GuardUnavailable`**: raised when the checker itself is broken. Callers must **fail**, never pass.
- **`LazyGuard`**: builds the guard on first use (so importing the app doesn't load torch models).
  `check()` has three outcomes:
  1. disabled by config → pass;
  2. `ValidationError` from the library → `GuardResult(passed=False)`, the **content was bad**, a
     normal result;
  3. any other exception → `GuardUnavailable`, the **checker is broken**, fail closed.
- `_warn_if_telemetry_enabled()` logs a warning if the library's third-party telemetry is on.

### `input_guard.py` / `output_guard.py`
Each defines a `_build()` that creates a Guardrails `Guard` and a thin `check_input` / `check_output`.
- **Input:** `ToxicLanguage(threshold=0.3, on_fail="exception")` + `ValidLength(max=2000, on_fail="fix")`.
- **Output:** `ToxicLanguage(threshold=0.4, on_fail="exception")` + `DetectPII(on_fail="fix")`. `fix`
  means "redact and continue", `exception` means "block".

### `backend/scripts/warm_models.py`
Runs **at Docker build time**: downloads NLTK data, primes the public-suffix cache, and runs both
guards once so every model is baked into the image. The runtime container then needs no network.

---

## 8. Frontend (`frontend/`)

**Stack:** Next.js 14 App Router, React 18, TypeScript, Tailwind.

### Pages (`app/`)
| File | Role |
|---|---|
| `layout.tsx` | Root layout: three Google fonts (serif, sans, mono) exposed as CSS variables, page metadata, a centered content column |
| `page.tsx` | Home: header + `<DebateStream debateId="latest">` |
| `debate/[id]/page.tsx` | Same, for a specific debate. Decodes the id (the `:` can arrive percent-encoded) |
| `archive/page.tsx` | Client component: fetches summaries, **client-side pagination (15 per page)**, loading / error / retry states, links with `encodeURIComponent` |
| `error.tsx`, `loading.tsx`, `not-found.tsx` | Next.js special files for errors, loading and 404 |
| `globals.css`, `tailwind.config.ts` | Design tokens as CSS variables, light/dark via `prefers-color-scheme`, small animations disabled for reduced-motion users |
| `icon.svg` | Favicon |

### Components (`components/`)
| File | Role |
|---|---|
| **`DebateStream.tsx`** | The client component that **owns the debate state**. On mount it opens the WebSocket, merges each event into state (arguments, rebuttals, verdict, bias scores, topic, resolved id), tracks connection state, and shows a not-found message if the server says so. Derives each analyst's dot state. Shows `OpinionBox` only once the debate is `done` |
| `AgentCard.tsx` | One analyst's card: colored stripe, opening, and nested rebuttal / closing statement when present |
| `AgentStatusDots.tsx` | Five progress dots (waiting / writing / done) with screen-reader text |
| `VerdictPanel.tsx` | The moderator's verdict plus `BiasChart` |
| `BiasChart.tsx` | Horizontal bars; width = score × 100 |
| `OpinionBox.tsx` | Textarea (max 1000, live counter, Ctrl/Cmd+Enter), loads earlier opinions, submits, shows the thread newest first, and shows server error messages |
| `OpinionResponse.tsx` | Renders the mode label, reply and follow-up question |
| `Header.tsx` | Title and nav (Latest / Archive); date and topic count are optional |

### `lib/api.ts`: the typed API client (the file to know)
- Types for `Debate`, `DebateSummary`, `OpinionResponse`, stream events.
- `apiBase()` / `wsBase()`: derive URLs. Production default is **same origin**; the WebSocket URL is
  derived from the API URL or the page origin, and `ws://` is **upgraded to `wss://`** on https pages.
- `request()`: `fetch` with a 60 s timeout; network failures become an `ApiError(0, ...)`; server
  `detail` messages (including FastAPI validation errors) are surfaced.
- `fetchDebates`, `fetchDebate`, `submitOpinion`, `fetchOpinions`.
- **`connectDebateStream()`**: opens the socket, parses messages safely, and **reconnects with
  exponential backoff** (1, 2, 4, 8, 15 s; max 5). It stops once the debate is `done` or the server
  reports not found, and `close()` cancels everything.

### `lib/user.ts`
`getAnonymousUserId()` stores a random UUID in `localStorage` as the per-browser id (with a fallback
if storage is blocked). **It is not authentication**: it only separates threads.

### Config
`next.config.js` (standalone output only for the Docker image), `package.json` scripts
(`dev/build/start/lint/typecheck/test`), `.eslintrc.json`, `vitest.config.ts`, `tsconfig.json`.

---

## 9. Tests

**Shared setup, `backend/tests/conftest.py`**
- `isolated_settings` (autouse): guardrails off, scheduler off, no retry delay, an admin token set.
- `fake_redis`: an in-memory Redis (`fakeredis`) swapped in for the real client.
- `LLMRecorder` / `fake_llm`: a fake LLM that returns canned text per persona and **records every
  call**, so tests can assert what was asked.
- `fake_news`: two canned articles.

| File | What it proves |
|---|---|
| `test_graph.py` | The full graph completes; the devil sees the other four openings; seen URLs are skipped; an always-failing guard **terminates** and drops rebuttals; only failing rebuttals are regenerated |
| `test_guarded_outputs.py` | Retry-then-pass, give up after retries, a blocked opening sits out, a blocked verdict uses the fallback, the moderator refuses to run with no arguments |
| `test_guards.py` | `ValidationError` is a failed result, a broken guard raises `GuardUnavailable`, guards are built lazily and once, disabled mode works, the telemetry warning |
| `test_nodes.py` | Bias-score parsing edge cases; fetcher: guard rejections, fallback to GNews, junk articles |
| `test_redis_service.py` | Id parsing; save/get/list/resolve; expiry pruning; index rebuild; locks; rate-limit windows |
| `test_scheduler.py` | Slugify; retries then saves; a second run the same day is a no-op; the lock is released after a final failure |
| `test_api.py` | Health, id variants and 404s, pagination limits, WebSocket replay and 4404, opinion validation / rate limits / filters, the admin endpoint, Redis outage → 503, LLM failure → 502 **with CORS headers** |
| `test_integration.py` | End to end: trigger → real graph → Redis → REST + WebSocket → opinion |
| `test_logging.py` | The JSON formatter |
| `frontend/lib/api.test.ts` | URL derivation, `ws→wss`, error messages, and the reconnect/backoff behavior |

**Mutation checks:** I temporarily re-introduced two original bugs (missing retry field; missing
reducer) and confirmed the tests fail, so they would have caught them.

---

## 10. Docker, CI and deployment

| File | What it does |
|---|---|
| `backend/Dockerfile` | `python:3.11-slim`; installs **CPU** torch, then the locked requirements; writes `~/.guardrailsrc` (telemetry off); runs `warm_models.py`; creates a **non-root** user (`APP_UID`, `PORT` build args); `HEALTHCHECK`; runs uvicorn with one worker |
| `frontend/Dockerfile` | 3 stages (deps → build → run); builds with `NEXT_OUTPUT=standalone`; runs the small standalone server as a non-root user |
| `backend/requirements.in` / `.txt` / `-torch.txt` / `-dev.txt` | Top-level deps → a **pinned lock** (without torch/CUDA) → CPU torch separately → pinned dev tools |
| `docker-compose.yml` (+ `.override.yml`) | Local stack: Redis, backend, frontend; the override adds hot reload |
| `deploy/aws/docker-compose.yml` | Server stack: Redis (capped), backend, frontend, **Caddy** router |
| `deploy/aws/Caddyfile` | Routes `/api`, `/ws`, `/internal`, `/health` to the backend; the rest to the frontend; keeps the `X-Forwarded-For` chain |
| `deploy/aws/cloudformation.yaml` | Creates the EC2 server, IAM role (no SSH), Secrets Manager secret, security group, Elastic IP, CloudFront (HTTPS), and a budget alert |
| `deploy/aws/bootstrap.sh` | First boot: install Docker, add swap, write `.env` from Secrets Manager (mode 600), `docker compose up --build`, wait until ready |
| `deploy/aws/update.sh`, `run-daily.sh`, `smoke_test.sh` | Redeploy; generate a debate now; test the running stack through the proxy |
| `deploy/scripts/trigger_daily.sh` | Wake the backend, call `run-daily`, wait until a new debate is saved, fail loudly otherwise |
| `deploy/huggingface/*`, `deploy-backend.yml` | Builds and pushes a Hugging Face Space bundle (note: Docker Spaces now need a paid plan) |
| `.github/workflows/ci.yml` | **backend** (ruff, mypy, pytest) · **frontend** (typecheck, lint, vitest, build) · **docker** (build both images; run unprivileged; guardrails offline; `/health`; the compose stack through Caddy) |
| `.github/workflows/daily-debate.yml` | Cron + manual trigger of the daily run |
| `pyproject.toml`, `pytest.ini` | ruff and mypy settings; pytest settings (async mode, paths) |

---

## 11. One request, end to end

**A visitor opens the site and submits an opinion.**

1. Browser → `GET /` → Caddy → Next.js renders `app/page.tsx` → `DebateStream` mounts.
2. `connectDebateStream("latest")` opens `wss://…/ws/debate/latest` → Caddy → `routers/ws.py`.
3. `ws.py` → `resolve_debate_id("latest")` → `get_debate()` (Redis) → sends 3 events → closes.
4. `DebateStream` merges events; `AgentCard`, `VerdictPanel`, `BiasChart` render; `OpinionBox` appears.
5. The user submits → `submitOpinion()` → `POST /api/opinion/latest`.
6. `deps.py` rate limit → `opinion.py` validates → `check_input` → `handle_opinion` (Groq) →
   `check_output` → `append_opinion` (Redis) → JSON reply.
7. `OpinionBox` appends the entry to the thread; `fetchOpinions` restores it on reload.

**The daily generation (no browser involved).**
cron or `POST /internal/run-daily` → `scheduler.generate_debate` → lock → `graph.ainvoke` (fetch →
extract → analysts → devil → rebuttals → moderator) → `save_debate` → lock marked done.

---

## 12. Cheat sheet: any file in 20 seconds

| File | One-liner | Interview hook |
|---|---|---|
| `main.py` | App wiring, lifespan, health, Redis→503 | Liveness vs readiness |
| `config.py` | Env settings + lazy LLM wrapper | One choke-point for every LLM call |
| `scheduler.py` | Locked, retried daily run | Idempotent job via `SET NX EX` |
| `routers/opinion.py` | Validate → filter → LLM → filter → store | Errors as `HTTPException` keep CORS headers |
| `routers/deps.py` | Per-IP + global rate limit | Take `X-Forwarded-For` from the right |
| `routers/ws.py` | Replay stored debate | Viewing never costs LLM money |
| `routers/admin.py` | Token-protected trigger | Constant-time compare; 202 + background task |
| `redis_service.py` | All storage logic | Pipeline transactions, sorted-set index |
| `graph/state.py` | Shared state + reducer | Parallel writes need a reducer |
| `graph/graph.py` | Fan-out, fan-in, retry edge | `recursion_limit` stops runaway loops |
| `graph/guarded.py` | Generate → validate → retry | Caller chooses how to degrade |
| `graph/nodes/rebuttal.py` | Parallel LLM calls, guarded, partial retry | Only failures retry; leftovers dropped |
| `graph/nodes/moderator.py` | Verdict + parsed bias scores | Never trust model output as JSON |
| `guardrails/common.py` | `LazyGuard`, `GuardResult` | "Blocked" vs "checker broken" |
| `graph/prompts.py` | Injection fencing | Strip the closing tag so the fence can't be closed early |
| `frontend/lib/api.ts` | Typed client + reconnecting WebSocket | `wss` upgrade, backoff, stop conditions |
| `DebateStream.tsx` | Owns debate state | Merge-by-event makes replays idempotent |
| `backend/Dockerfile` | Models baked in, non-root | Offline-capable, reproducible |
| `cloudformation.yaml` | One-form AWS stack | Secrets Manager, no SSH, budget alert |
| `tests/conftest.py` | Fake LLM + fake Redis | Whole system testable with no network |
