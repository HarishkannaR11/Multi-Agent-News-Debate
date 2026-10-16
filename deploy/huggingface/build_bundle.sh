#!/usr/bin/env bash
# Assemble the files a Hugging Face *Docker Space* needs from this repository.
#
# A Space is its own git repo whose root must hold a Dockerfile and a README.md with YAML front
# matter. Keeping that README out of the main repo avoids a metadata block on GitHub, so the
# Space repo is generated: backend code + this repo's Dockerfile (uid 1000, port 7860) + the card.
#
# usage: deploy/huggingface/build_bundle.sh <output-dir>

# Stop on the first error, on unset variables, and on failures inside pipelines.
set -euo pipefail

# The output folder is the first argument; stop with a usage message if it is missing.
out="${1:?usage: build_bundle.sh <output-dir>}"
# The repository root: two folders above this script's own folder.
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Start from a clean, empty output folder.
rm -rf "$out"
mkdir -p "$out"
# Copy the backend code into it.
cp -r "$root/backend" "$out/backend"
# Remove Python's cache folders from the copy (-prune stops find from entering what it deletes).
find "$out/backend" -type d -name __pycache__ -prune -exec rm -rf {} +
# The tests are not needed inside the Space.
rm -rf "$out/backend/tests"

# Spaces run the container as uid 1000 and route traffic to the port named by `app_port`.
# Copy the Dockerfile, replacing its "ARG APP_UID=..." and "ARG PORT=..." lines with the values Spaces needs.
sed -e 's/^ARG APP_UID=.*/ARG APP_UID=1000/' \
    -e 's/^ARG PORT=.*/ARG PORT=7860/' \
    "$root/backend/Dockerfile" > "$out/Dockerfile"
# Add the Space's README (it carries the metadata block Hugging Face reads).
cp "$root/deploy/huggingface/README.md" "$out/README.md"

# Fail loudly if the Dockerfile's ARG lines are renamed and the substitution silently stopped working.
# (grep -qx: quiet, and the whole line must match exactly.)
grep -qx 'ARG APP_UID=1000' "$out/Dockerfile" || { echo "bundle: APP_UID substitution failed" >&2; exit 1; }
grep -qx 'ARG PORT=7860' "$out/Dockerfile" || { echo "bundle: PORT substitution failed" >&2; exit 1; }
grep -qx 'app_port: 7860' "$out/README.md" || { echo "bundle: README app_port mismatch" >&2; exit 1; }

echo "Space bundle ready in $out"
