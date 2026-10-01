# Free deployment

Everything below runs on free tiers with no credit card. The only thing you pay is your own time
(about 30 minutes, most of it waiting for the first image build).

| Piece | Host | Why this one |
|---|---|---|
| Frontend (Next.js) | **Vercel** (Hobby) | Native Next.js support, free, no sleeping |
| Backend (FastAPI + guardrails) | **Hugging Face Space** (Docker, CPU basic) | 16 GB RAM / 2 vCPU free; the guardrail models (torch + spaCy) need ~2–3 GB |
| Redis | **Upstash** (Free) | 256 MB, 500k commands/month; speaks TLS |
| Daily job + wake-up | **GitHub Actions** cron | Free hosts sleep when idle, so the in-process scheduler can't be relied on |

**Why not Render/Railway/Fly for the backend?** Render's free web service has 512 MB RAM and
0.1 CPU, which cannot load the guardrail models. The other well-known options are trials or need
a card. If you drop the guardrails (`GUARDRAILS_ENABLED=false`, not recommended: it disables the
content filtering) a 512 MB host works, but you lose the filtering.

```
 browser ──https──▶ Vercel (Next.js)
    │
    └──https / wss──▶ Hugging Face Space (FastAPI) ──TLS──▶ Upstash Redis
                              ▲
        GitHub Actions cron ──┘  wakes it, POST /internal/run-daily
                              └──▶ Groq + news API (outbound)
```

## 0. Accounts and keys

Create free accounts at GitHub (you have one), [Hugging Face](https://huggingface.co),
[Vercel](https://vercel.com), [Upstash](https://upstash.com) and [Groq](https://console.groq.com).
You also need one news API key: [NewsAPI](https://newsapi.org) (free "developer" plan, intended for
development use) or [GNews](https://gnews.io) (free plan). Either works; set whichever you have.

Generate a long random admin token (any strong random string works):

```bash
openssl rand -hex 32
```

## 1. Redis (Upstash)

1. Create a Redis database (Free plan, any nearby region).
2. Copy its connection details and build a **`rediss://`** URL (note the double *s* = TLS):

   ```
   rediss://default:<password>@<endpoint>:6379
   ```

   This is your `REDIS_URL`.

## 2. Backend (Hugging Face Space)

1. On Hugging Face: **New Space** → name it (e.g. `counterpoint-api`) → SDK **Docker** → template
   **Blank** → hardware **CPU basic (free)** → **Public**.
2. **Settings → Variables and secrets** on the Space. Add these as **Secrets**:

   | Name | Value |
   |---|---|
   | `GROQ_API_KEY` | your Groq key |
   | `NEWSAPI_KEY` *or* `GNEWS_API_KEY` | your news key |
   | `REDIS_URL` | the `rediss://…` URL from step 1 |
   | `ADMIN_TOKEN` | the token you generated |

   and these as **Variables**:

   | Name | Value |
   |---|---|
   | `CORS_ORIGINS` | your Vercel site origin, e.g. `https://counterpoint.vercel.app` (add after step 3; no trailing slash; comma-separate several) |
   | `SCHEDULER_ENABLED` | `false` (GitHub Actions triggers the run instead) |
   | `TRUST_PROXY_HEADERS` | `true` |
   | `TRUSTED_PROXY_HOPS` | `1` |

3. Create a Hugging Face **access token** with **write** access (Settings → Access Tokens).
4. In your GitHub repo: **Settings → Secrets and variables → Actions**, add:
   - `HF_TOKEN` = that token
   - `HF_SPACE` = `your-username/counterpoint-api`
5. Run **Actions → Deploy backend (Hugging Face Space) → Run workflow** (it also runs on every push
   to `main` that touches `backend/`). The Space then builds the image. **The first build takes
   10–15 minutes** (it downloads torch and the guardrail models); later builds are faster.
6. When the Space shows *Running*, open `https://<your-username>-<space-name>.hf.space/health`. You
   should see `{"status":"ok"}`, and `/health/ready` should say `ready` (that one checks Redis).

The Space's address is `https://<username>-<space-name>.hf.space` (lowercase). That is your
**backend URL**.

## 3. Frontend (Vercel)

1. **Add New → Project** → import this GitHub repo.
2. Set **Root Directory** to `frontend`. Leave the framework preset as Next.js.
3. Add an environment variable: `NEXT_PUBLIC_API_URL` = your backend URL from step 2 (no trailing
   slash). The WebSocket address is derived from it automatically (`https` → `wss`).
4. Deploy. Copy the resulting site URL into the Space's `CORS_ORIGINS` variable (step 2.2); the
   Space restarts when variables change.

`NEXT_PUBLIC_*` values are baked in at build time, so changing the API URL later needs a redeploy.

## 4. Daily debate (GitHub Actions)

In the same GitHub secrets page add:

- `BACKEND_URL` = the backend URL (the `.hf.space` address)
- `ADMIN_TOKEN` = the same token as on the Space

Then run **Actions → Daily debate → Run workflow** once to generate the first debate immediately.
The script (`deploy/scripts/trigger_daily.sh`) wakes the Space if it is asleep, triggers the run,
and waits until a new debate is saved; if that does not happen it fails, and GitHub emails you.
After that it runs by itself every day at 06:17 UTC.

Open your Vercel site: you should see today's debate.

## What to expect on free tiers

- **Cold starts.** A Space that has been idle goes to sleep and takes about a minute to wake. The
  daily job keeps it warm in practice, and the site retries its connection, but the first visitor
  after a long idle spell may see "Reconnecting…" for a while.
- **Upstash quota.** 500k commands a month is far more than this app needs (a page view is a few
  commands, a debate generation about a dozen, an opinion about eight, and an archive page load
  up to ~100, one per listed debate).
- **Groq rate limits.** A debate makes about 13+ LLM calls, five in parallel. Free tiers may answer
  429; the client retries with backoff (`GROQ_MAX_RETRIES`). If runs still fail, lower the load by
  using a smaller `GROQ_MODEL_MAIN` or retry later. Opinion replies are also capped site-wide by
  `OPINION_GLOBAL_LIMIT_PER_HOUR` (default 300) so visitors cannot burn your quota.
- **Scheduled workflows pause** after 60 days of repository inactivity; re-enable them from the
  Actions tab.
- **Vercel Hobby** is for non-commercial use.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Site says "Could not reach the server" | Space asleep or still building; check `…hf.space/health`. Also check `NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` |
| Browser console shows a CORS error | `CORS_ORIGINS` on the Space doesn't exactly match the site's origin |
| Site says "No debate found" | No debate generated yet; run the *Daily debate* workflow |
| *Daily debate* fails: "backend not ready" | Space asleep/building, or `REDIS_URL` wrong (`/health/ready` shows it) |
| *Daily debate* fails: "admin token rejected" | `ADMIN_TOKEN` differs between GitHub and the Space |
| *Daily debate* fails: "no new debate" | See the Space's **Logs**: Groq key/quota or news API key |
| Opinions always return 503 | The content filter couldn't load; see the Space logs for the guardrail error |
| Opinions get "Too many requests" for everyone | The proxy hides client IPs so everyone shares one bucket; raise `OPINION_RATE_LIMIT`, or fix `TRUSTED_PROXY_HOPS` |

## Known unknowns

These depend on Hugging Face's infrastructure and could not be verified from CI:

- How many proxy hops sit in front of a Space, hence whether `TRUSTED_PROXY_HOPS=1` yields real
  client IPs. The global hourly cap protects your quota either way.
- The exact idle time before a Space sleeps (documented only as "a period of time").

## Moving to a paid host later

Nothing here is specific to the free stack: the backend is one Docker image
(`backend/Dockerfile`) plus a Redis URL, and the frontend is a standard Next.js app (or the
`frontend/Dockerfile` image). Set `SCHEDULER_ENABLED=true` to use the built-in scheduler on a host
that doesn't sleep.
