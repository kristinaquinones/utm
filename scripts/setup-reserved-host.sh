#!/usr/bin/env bash
# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only
#
# Reserves a dedicated host + loopback alias for the UTM app so it always answers
# at https://utm.linkbuilder, regardless of what else is bound to 127.0.0.1:443.
#
# What it does (once per machine, needs sudo):
#   1. Maps utm.linkbuilder -> 127.94.0.1 in /etc/hosts.
#   2. Installs a LaunchDaemon that creates the 127.94.0.1 loopback alias at boot.
#   3. Brings the alias up now so you don't have to reboot.
#
# macOS only. Linux/Docker users can bind 127.0.0.1 directly without an alias.

set -euo pipefail

ALIAS_IP="127.94.0.1"
HOSTNAME="utm.linkbuilder"
LABEL="com.utm.loopback-alias"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SRC="$ROOT_DIR/scripts/$LABEL.plist"
PLIST_DEST="/Library/LaunchDaemons/$LABEL.plist"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script is macOS-only. On Linux, bind 127.0.0.1 in docker-compose.yml instead." >&2
  exit 1
fi

echo "This needs administrator rights to edit /etc/hosts and install a LaunchDaemon."
sudo -v

# 1. /etc/hosts entry (idempotent).
if grep -qE "^[[:space:]]*${ALIAS_IP//./\\.}[[:space:]]+${HOSTNAME//./\\.}([[:space:]]|$)" /etc/hosts; then
  echo "hosts: $ALIAS_IP $HOSTNAME already present"
else
  echo "hosts: adding $ALIAS_IP $HOSTNAME"
  printf '%s\t%s\n' "$ALIAS_IP" "$HOSTNAME" | sudo tee -a /etc/hosts >/dev/null
fi

# 2. Install + (re)load the LaunchDaemon that recreates the alias at every boot.
echo "daemon: installing $PLIST_DEST"
sudo cp "$PLIST_SRC" "$PLIST_DEST"
sudo chown root:wheel "$PLIST_DEST"
sudo chmod 644 "$PLIST_DEST"
sudo launchctl bootout system "$PLIST_DEST" 2>/dev/null || true
sudo launchctl bootstrap system "$PLIST_DEST"

# 3. Bring the alias up now (the daemon also does this at boot; this avoids a reboot).
echo "alias: ensuring $ALIAS_IP is up on lo0"
sudo ifconfig lo0 alias "$ALIAS_IP" up

cat <<EOF

Reserved host is ready.

  $HOSTNAME -> $ALIAS_IP (dedicated loopback alias, recreated at every boot)

Start the stack:
  docker compose up --build

Then open:
  https://$HOSTNAME

The app now owns ${ALIAS_IP}:443, so nothing on 127.0.0.1:443 can shadow it.
EOF
