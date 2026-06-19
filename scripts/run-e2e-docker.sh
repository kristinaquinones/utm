#!/usr/bin/env sh
# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

set -eu

docker run --rm \
  -v "$(pwd):/app" \
  -w /app \
  mcr.microsoft.com/playwright/python:v1.49.1-jammy \
  sh -c "pip install -q -r requirements-e2e.txt && PYTHONPATH=. pytest tests/e2e -m e2e -v --tracing retain-on-failure"
