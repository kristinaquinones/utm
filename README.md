# UTM builder

A small, local app for building campaign URLs without a spreadsheet. Generate UTM links, save the ones you use often, create reusable templates, and export everything as CSV when you need a handoff.

The app runs in Docker, stores data in a local JSON file, and does not require an account.

## features

- Generate one UTM link from a base URL and parameter fields.
- Add custom key-value parameters, including custom `utm_` keys like `utm_id`.
- Save, edit, and delete generated links.
- Save reusable parameter templates.
- Apply templates to the generator form.
- Bulk-generate links by varying one parameter across multiple values.
- Export saved links as CSV.

## run locally with Docker

### First time on this machine

```sh
brew install mkcert          # macOS; see script output for Linux/Windows
./scripts/setup-local-https.sh    # mkcert root CA + ./certs/ for utm.linkbuilder
./scripts/setup-reserved-host.sh  # reserves utm.linkbuilder on a dedicated loopback alias (sudo)
docker compose up --build
```

Both setup scripts run once per machine before the first `docker compose up`. `setup-reserved-host.sh` maps `utm.linkbuilder` to a dedicated loopback alias (`127.94.0.1`) so the app owns its own `:443` and never gets shadowed by another app on `127.0.0.1:443`. See [reserved host and auto-start](#reserved-host-and-auto-start).

### Every time

```sh
docker compose up --build
```

Open **`https://utm.linkbuilder`** (HTTPS, not HTTP). There is no `http://` redirect, and `http://utm.linkbuilder` will load a *different* app, so use the `https://` URL and bookmark it. See [gotchas](#gotchas) if anything misbehaves.

If you skip the setup script, Caddy will refuse to start and print the same instructions.

Data is stored in `./data/utm-data.json`.

## reserved host and auto-start

The app answers at `https://utm.linkbuilder`, not `https://utm.localhost`. The reason is collision: browsers force every `*.localhost` name to `127.0.0.1` and ignore `/etc/hosts`, so the app had to share ports 80/443 with every other local project, and whatever bound `:443` first won.

`setup-reserved-host.sh` fixes that on macOS:

- Maps `utm.linkbuilder` to a dedicated loopback alias, `127.94.0.1`, in `/etc/hosts`. Unlike `*.localhost`, `utm.linkbuilder` is not special-cased by browsers, so the hosts entry is honored. (`.linkbuilder` is not a real public TLD, so it can never collide with real DNS; the name resolves only on this machine.)
- Installs a LaunchDaemon (`/Library/LaunchDaemons/com.utm.loopback-alias.plist`) that recreates the alias at every boot, since loopback aliases do not survive a reboot.

Docker then publishes Caddy on `127.94.0.1:443` only (see `docker-compose.yml`), an address nothing else touches, so the app's port is effectively reserved.

Port 80 is deliberately not published. A dedicated alias dodges apps bound to a specific IP, but not apps bound to `0.0.0.0` (all interfaces) on the same port, which is what a container started with `80:80` does. On this machine another container holds `0.0.0.0:80`, so port 80 is unavailable on every IP including the alias. The app needs only 443, so it skips 80 and there is no automatic `http://` to `https://` redirect: always open the HTTPS URL. (443 is free here; if a future container ever publishes `0.0.0.0:443`, move this app to a different port.)

### Auto-start on login

No extra daemon is needed. The compose services use `restart: unless-stopped`, so once they have been started, Docker restores them whenever it starts.

1. Docker Desktop → Settings → General → enable **Start Docker Desktop when you sign in**.
2. Start the stack detached once: `docker compose up -d --build`.

After that the app comes back on every login. The boot-time LaunchDaemon guarantees the `127.94.0.1` alias exists before Docker tries to bind it. To stop auto-starting, run `docker compose down`.

To undo the reserved host entirely: `sudo launchctl bootout system /Library/LaunchDaemons/com.utm.loopback-alias.plist && sudo rm /Library/LaunchDaemons/com.utm.loopback-alias.plist`, then remove the `utm.linkbuilder` line from `/etc/hosts`.

### Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `http://utm.linkbuilder` shows a *different* app | Port 80 is held by another container; only `:443` is reserved for this app | Always use the **`https://`** URL, and bookmark it |
| `setup-reserved-host.sh` exits with `sudo: a terminal is required to read the password` | It was run without an interactive terminal (for example an editor's inline shell) | Run it in a normal terminal window so sudo can prompt |
| `docker compose up` fails with `bind: can't assign requested address` | The `127.94.0.1` loopback alias is not up | Check with `ifconfig lo0 \| grep 127.94`; re-run `./scripts/setup-reserved-host.sh`, or `sudo ifconfig lo0 alias 127.94.0.1 up` |
| `docker compose up` fails with `port is already allocated` | Another container already publishes `0.0.0.0:443`, an all-interfaces bind the alias cannot dodge | Find it with `docker ps --format '{{.Names}}\t{{.Ports}}' \| grep 443`, then stop it or give utm a different port (see [Docker notes](#docker-notes)) |
| Page loads but is completely **unstyled** | Stale image without proxy headers, so assets are requested over `http://` and blocked as mixed content | `docker compose up -d --build`, then hard-refresh (Cmd+Shift+R) |
| Setup scripts do not apply on Linux | The loopback alias and LaunchDaemon are macOS-only | On Linux, bind `127.0.0.1` directly in `docker-compose.yml` and skip `setup-reserved-host.sh` |

## export links

Open `https://utm.linkbuilder/export/links.csv`, or use the export button in the app.

If no links are saved yet, the export will still download a CSV with only the header row.

## security model

This is a local, single-user tool. It has no login screen and is intended to run on your own machine.

The app still includes a few practical safeguards:

- CSRF protection for every mutating form post.
- Safe JSON embedding for template data.
- CSV formula neutralization for exported values and dynamic headers.
- Local data excluded from Git through `.gitignore`.
- Local HTTPS uses [mkcert](https://github.com/FiloSottile/mkcert); `./scripts/setup-local-https.sh` installs a machine-local root CA trusted only on that computer. Certificate files live in `./certs/` and are gitignored.

## local data

Saved links and templates live in `./data/utm-data.json`.

That file is intentionally ignored by Git. Delete it if you want to reset the app.

## development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Unit + integration (default; no browser)
PYTHONPATH=. python -m pytest

uvicorn app.main:app --reload
```

### E2E tests (local only)

E2E uses Playwright against a subprocess uvicorn server. It is optional and not part of CI.

**Python 3.12** (recommended; matches CI). On macOS with Homebrew: `/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv`

```sh
pip install -r requirements-e2e.txt
playwright install chromium
PYTHONPATH=. pytest tests/e2e -m e2e -v
```

**Docker alternative** (no local Python 3.12 or Chromium setup):

```sh
./scripts/run-e2e-docker.sh
```

Run E2E when you change routes, templates, `app.js`, export behavior, or saved-links interactions.

## Docker notes

Caddy listens on the dedicated loopback alias `127.94.0.1:443` and proxies to the app on port `8000`. TLS certificates come from [mkcert](https://github.com/FiloSottile/mkcert) in `./certs/` (gitignored). Generate them with `./scripts/setup-local-https.sh` before the first run.

If another container already publishes `0.0.0.0:443` (the one port this app needs), change the `127.94.0.1:443:443` mapping in `docker-compose.yml` to a free port, for example `127.94.0.1:8443:443`, and open `https://utm.linkbuilder:8443`. See [gotchas](#gotchas).

## license

Copyright (C) 2026 Kristina Quinones.

This project is licensed under GPL-2.0-only. See [LICENSE](LICENSE).

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). By contributing, you agree to the [DCO](DCO) and license your work under GPL-2.0-only.
