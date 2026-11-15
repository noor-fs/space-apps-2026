#!/bin/sh
# Assemble the Hugging Face Space folder from the repo (run from the repo root):
#   sh server/make_space.sh <space folder>
# The space folder is a clone of the Space's git repo; this replaces its contents, then you commit and push it.
set -e
space="$1"
[ -n "$space" ] || { echo "usage: sh server/make_space.sh <space folder>"; exit 1; }
rm -rf "$space/spx" "$space/scripts" "$space/server"
mkdir -p "$space/scripts" "$space/server"
cp -r spx "$space/spx"
cp scripts/build_target.py "$space/scripts/"
cp server/app.py "$space/server/"
cp server/Dockerfile "$space/Dockerfile"
cp requirements.txt "$space/requirements.txt"
cp server/requirements.txt "$space/server_requirements.txt"
find "$space" -name __pycache__ -type d -prune -exec rm -rf {} +
cat > "$space/README.md" <<'EOF'
---
title: SPHEREx live lookup
emoji: 🔭
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

Live lookup server for the SPHEREx blink tool (NASA Space Apps 2026). Any sky position or object
name is built on request and served in the site's `data/` layout.

- `GET /api/lookup?q=<name or coordinates>&size=51`: start or find a build; returns its status
- `GET /api/status/<key>`: status of one field
- `GET /data/<key>/...`: the field's files
EOF
echo "Space folder ready: $space"
