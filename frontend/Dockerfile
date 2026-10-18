# syntax=docker/dockerfile:1
# Build from frontend/:  docker build -t counterpoint-frontend frontend

# Multi-stage build: three stages (deps -> build -> run); only the last stage becomes the final image.
# ---- Stage 1 "deps": install the npm packages ----
# Start from a small Linux image with Node.js 22 and name this stage "deps".
FROM node:26-alpine AS deps
# Work inside /app.
WORKDIR /app
# Copy only the package files first, so this step is cached until the dependencies change.
COPY package.json package-lock.json ./
# Install exactly the versions in the lock file ("ci" = clean, reproducible install).
RUN npm ci

# ---- Stage 2 "build": compile the website ----
FROM node:26-alpine AS build
WORKDIR /app
# NEXT_PUBLIC_* values are inlined into the browser bundle at build time.
# Leave both empty to call the same origin (a load balancer routing /api and /ws to the backend).
# Build-time options (with empty defaults) for where the browser should find the API and WebSocket.
ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_WS_URL=""
# Turn them into environment variables so the build can read them, and:
#   NEXT_TELEMETRY_DISABLED=1  do not send anonymous usage data to Next.js
#   NEXT_OUTPUT=standalone     tell next.config.js to produce a small self-contained server
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_OUTPUT=standalone
# Bring in the installed packages from stage 1.
COPY --from=deps /app/node_modules ./node_modules
# Copy the rest of the frontend source code.
COPY . .
# Build the production version of the site.
RUN npm run build

# ---- Stage 3 "run": the small image that actually runs ----
FROM node:26-alpine AS run
WORKDIR /app
# Run in production mode, no telemetry, listen on port 3000 on all network interfaces (0.0.0.0).
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# Create a non-root group and user named "app" (Alpine's addgroup/adduser syntax).
RUN addgroup -S app && adduser -S app -G app
# `output: "standalone"` emits a minimal server; static assets are copied alongside it.
# Copy the compiled server from the build stage, owned by the "app" user...
COPY --from=build --chown=app:app /app/.next/standalone ./
# ...and the static files (CSS, JavaScript) that the server serves.
COPY --from=build --chown=app:app /app/.next/static ./.next/static
# Run as the unprivileged user.
USER app
# Document the port the app listens on.
EXPOSE 3000
# Every 30s fetch the home page; if it fails 3 times in a row the container is marked unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:3000/ || exit 1
# Start the standalone Next.js server.
CMD ["node", "server.js"]
