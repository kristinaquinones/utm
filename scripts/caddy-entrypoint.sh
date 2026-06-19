#!/bin/sh
# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

if [ ! -f /certs/utm.linkbuilder.pem ] || [ ! -f /certs/utm.linkbuilder-key.pem ]; then
  cat >&2 <<'EOF'

HTTPS certificates not found.

First-time setup (once per machine):
  ./scripts/setup-local-https.sh

Then start the stack again:
  docker compose up --build

EOF
  exit 1
fi

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
