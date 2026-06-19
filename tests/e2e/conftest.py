# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright")


@pytest.fixture(scope="session")
def e2e_data_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    return str(tmp_path_factory.mktemp("e2e") / "utm-data.json")


@pytest.fixture(scope="session")
def live_server(e2e_data_path: str) -> Iterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env["DATA_PATH"] = e2e_data_path
    env["PYTHONPATH"] = os.getcwd()

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"uvicorn exited early: {stderr}")
        try:
            with urllib.request.urlopen(base_url, timeout=1) as response:
                if response.status == 200:
                    break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    else:
        proc.terminate()
        raise RuntimeError(f"Server did not start at {base_url}")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def browser_context_args(live_server: str) -> dict[str, str]:
    return {"base_url": live_server}


@pytest.fixture(autouse=True)
def reset_e2e_data(e2e_data_path: str) -> None:
    Path(e2e_data_path).write_text(
        json.dumps({"links": [], "templates": []}, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def fresh_client_state(page, live_server: str) -> None:
    page.goto("/")
    page.evaluate("() => localStorage.clear()")
    page.reload()


@pytest.fixture(autouse=True)
def grant_clipboard(context) -> None:
    context.grant_permissions(["clipboard-read", "clipboard-write"])
