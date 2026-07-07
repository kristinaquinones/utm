#!/bin/sh
# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only
#
# Apply database migrations before starting the web server, then hand off to the
# container's command. Migrations run only for the server (not for one-off
# commands like `python -m pytest`, which use their own throwaway SQLite).
set -e

if [ "$1" = "uvicorn" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

exec "$@"
