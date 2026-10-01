#!/usr/bin/env bash
# Assemble the files a Hugging Face *Docker Space* needs from this repository.
#
# A Space is its own git repo whose root must hold a Dockerfile and a README.md with YAML front
# matter. Keeping that README out of the main repo avoids a metadata block on GitHub, so the
# Space repo is generated: backend code + this repo's Dockerfile (uid 1000, port 7860) + the card.
#
# usage: deploy/huggingface/build_bundle.sh <output-dir>
set -euo pipefail

out="${1:?usage: build_bundle.sh <output-dir>}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

rm -rf "$out"
mkdir -p "$out"
cp -r "$root/backend" "$out/backend"
find "$out/backend" -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$out/backend/tests"

# Spaces run the container as uid 1000 and route traffic to the port named by `app_port`.
sed -e 's/^ARG APP_UID=.*/ARG APP_UID=1000/' \
    -e 's/^ARG PORT=.*/ARG PORT=7860/' \
    "$root/backend/Dockerfile" > "$out/Dockerfile"
cp "$root/deploy/huggingface/README.md" "$out/README.md"

# Fail loudly if the Dockerfile's ARG lines are renamed and the substitution silently stopped working.
grep -qx 'ARG APP_UID=1000' "$out/Dockerfile" || { echo "bundle: APP_UID substitution failed" >&2; exit 1; }
grep -qx 'ARG PORT=7860' "$out/Dockerfile" || { echo "bundle: PORT substitution failed" >&2; exit 1; }
grep -qx 'app_port: 7860' "$out/README.md" || { echo "bundle: README app_port mismatch" >&2; exit 1; }

echo "Space bundle ready in $out"
