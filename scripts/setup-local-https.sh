#!/usr/bin/env bash
# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$ROOT_DIR/certs"
CERT_FILE="$CERT_DIR/utm.localhost.pem"
KEY_FILE="$CERT_DIR/utm.localhost-key.pem"

if ! command -v mkcert >/dev/null 2>&1; then
  cat >&2 <<'EOF'
mkcert is required for local HTTPS.

Install it, then run this script again:

  macOS:   brew install mkcert
  Linux:   https://github.com/FiloSottile/mkcert#linux
  Windows: choco install mkcert

EOF
  exit 1
fi

echo "Installing mkcert root CA (once per machine; your OS may prompt for approval)..."
if ! mkcert -install; then
  cat >&2 <<'EOF'

Could not install the mkcert root CA automatically.
Run this in your terminal (outside Docker), approve the prompt, then re-run this script:

  mkcert -install

EOF
  exit 1
fi

mkdir -p "$CERT_DIR"

if [[ -f "$CERT_FILE" && -f "$KEY_FILE" ]]; then
  echo "Certificates already exist in ./certs/"
else
  echo "Generating certificates for utm.localhost..."
  mkcert -cert-file "$CERT_FILE" -key-file "$KEY_FILE" utm.localhost
fi

chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

cat <<EOF

Local HTTPS is ready.

Next step:
  docker compose up --build

Then open:
  https://utm.localhost

http://utm.localhost redirects to HTTPS. No browser certificate warnings after mkcert -install.
EOF
