# News Debate System

A multi-agent news debate pipeline: five Claude-powered personas (left,
right, economist, geopolitical, devil's advocate) debate the day's top news,
a moderator synthesizes a bias-balanced verdict, and users can submit their
own opinion for an agree/challenge/expand response.

## Backend setup

```bash
cd news-debate
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r backend/requirements.txt

copy .env.example .env        # fill in ANTHROPIC_API_KEY, NEWSAPI_KEY or GNEWS_API_KEY, etc.

docker compose up -d redis    # or point REDIS_URL at an existing Redis instance

uvicorn backend.main:app --reload   # run from the news-debate/ root, not from inside backend/
```

Guardrails AI validators (`ToxicLanguage`, `ValidLength`, `DetectPII`) come
from the Guardrails Hub and may need `guardrails hub install` for each
validator, plus `GUARDRAILS_TOKEN` if you're using hosted validation.

## Frontend setup

```bash
cd news-debate/frontend
npm install
npm run dev   # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_WS_URL` in `.env` if the backend
isn't on `localhost:8000`.

## Design

The frontend follows a "Classical Minimalist" newspaper aesthetic (Playfair
Display + Inter + JetBrains Mono, warm off-white paper background, no
shadows/gradients/rounded corners) defined in `frontend/tailwind.config.ts`
and `frontend/app/globals.css`, with light/dark mode driven by CSS variables.

## Deploying

- **Backend → Railway**: point it at `backend/Dockerfile`, add the same env
  vars as `.env`, and attach a Redis plugin (or keep using an external one).
- **Frontend → Vercel**: import `frontend/`, set `NEXT_PUBLIC_API_URL` /
  `NEXT_PUBLIC_WS_URL` to the deployed backend's URL.

No deploy has been performed as part of this scaffold — these are the steps
to run yourself when ready.
