#!/bin/sh
# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only
#
# Apply database migrations before starting the web server, then hand off to the
# container's command. Migrations run only for the server (not for one-off
# commands like `python -m pytest`, which use their own throwaway SQLite).
#
# On platforms that run migrations as a separate release step (Fly.io's
# release_command), set RUN_MIGRATIONS_ON_START=0 so app machines don't each
# re-run them on boot. Defaults to on, so local docker-compose keeps working.
set -e

if [ "$1" = "uvicorn" ] && [ "${RUN_MIGRATIONS_ON_START:-1}" != "0" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

exec "$@"
