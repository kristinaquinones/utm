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

Data is stored in Postgres (the `db` service in `docker-compose.yml`), in the `db-data` volume.

**Signing in locally.** The app now has accounts and magic-link login. `docker-compose.yml` seeds an admin (`ADMIN_EMAILS=admin@localhost`) and uses the console email backend, so the sign-in link is printed to the logs. To sign in:

```sh
# open https://utm.linkbuilder, enter admin@localhost, then grab the link:
docker compose logs -f utm | grep auth/callback
```

Paste that link into the browser. Other people request access at `/signup`; an admin approves them at `/admin`.

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

The app is multi-tenant with passwordless authentication. Each approved user gets a private workspace; no user can see another's links, templates, or branding.

- **Magic-link login.** No passwords. Requesting a link always responds "check your email" regardless of whether the account exists or is approved, to resist account enumeration; tokens are hashed at rest, single-use, and short-lived.
- **Approval-gated signup.** New signups are `pending` until an admin approves them at `/admin`. The first admin is seeded from `ADMIN_EMAILS`; admin rights are granted only by that seed, never through the UI.
- **Tenant isolation.** Every data query is scoped to the authenticated user (`app/repository.py`); there is no un-scoped read or write path.
- **Sessions** are signed (not encrypted) cookies holding only an id, an epoch, and a CSRF token; `HttpOnly`, `SameSite=Lax`, and `Secure` in production. Bumping a user's session epoch revokes their sessions.
- **CSRF** is per-session (issued to anonymous visitors too, so login/signup are protected) on every mutating route.
- Plus: safe JSON embedding, CSV formula neutralization, per-tenant accent colors sanitized to a parsed hex before reaching any `<style>` block, and rate limiting on `/auth/request-link` and `/signup`.

Local HTTPS uses [mkcert](https://github.com/FiloSottile/mkcert); `./scripts/setup-local-https.sh` installs a machine-local root CA. Certificate files live in `./certs/` and are gitignored.

## local data

Data lives in Postgres. Docker Compose runs a `db` service and stores it in the `db-data` volume; reset with `docker compose down -v`.

For the plain-Python path (`uvicorn --reload`), `DATABASE_URL` defaults to a local SQLite file at `./data/utm.db` (gitignored) so you can run without standing up Postgres. Schema for SQLite is created automatically; for Postgres, run `alembic upgrade head`.

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

## Deploy to Fly.io

The hosted target is [Fly.io](https://fly.io): it runs the repo's Dockerfile directly and offers managed Postgres, so a Dockerized FastAPI app deploys with almost no glue. `fly.toml` is included and configured; change the `app` name and `BASE_URL` first.

### One-time setup

```sh
fly auth login
fly apps create utm-link-builder            # match the `app` name in fly.toml

# Managed Postgres, attached (sets the DATABASE_URL secret automatically):
fly postgres create --name utm-link-builder-db
fly postgres attach utm-link-builder-db

# Secrets (never commit these):
fly secrets set SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
fly secrets set ADMIN_EMAILS="you@example.com"      # the first admin
fly secrets set POSTMARK_TOKEN="..."                # or SMTP_* for the SMTP backend
fly secrets set EMAIL_FROM="UTM link builder <no-reply@yourdomain.com>"
```

`fly attach` provides `DATABASE_URL` as a `postgres://` URL; the app rewrites it to the `postgresql+psycopg://` driver automatically (`app/config.py`).

### Deploy

```sh
fly deploy
```

Each deploy runs `alembic upgrade head` once in a release machine (`release_command` in `fly.toml`) before the new version goes live, so migrations never race across app machines (`RUN_MIGRATIONS_ON_START=0` keeps app boots from re-running them). Fly terminates TLS and forwards `X-Forwarded-*`; the container already runs uvicorn with `--proxy-headers`, and `SESSION_HTTPS_ONLY=1` makes session cookies `Secure`.

Fly's health checks poll `GET /healthz`, which verifies database connectivity (503 when the DB is unreachable).

### First admin and approving users

The address in `ADMIN_EMAILS` is seeded as an approved admin on every boot (additive: it never demotes anyone). Sign in at `/login`, then approve new signups at `/admin`. Others request access at `/signup`.

### Email deliverability (do this before real users)

Magic-link login makes email a hard dependency: if links land in spam, users are locked out. On a cold sending domain, configure DNS auth for whatever provider you use (Postmark or SMTP):

- **SPF** — authorize the provider's servers to send for your domain.
- **DKIM** — add the provider's signing keys (Postmark shows the exact records).
- **DMARC** — publish a policy (start at `p=none` to monitor, then tighten).

Warm the domain up with low volume first. Until this is in place, expect links to hit spam.

### Backup and restore

```sh
# On-demand logical backup:
fly postgres connect -a utm-link-builder-db
# ...or dump via a proxy:
fly proxy 5432 -a utm-link-builder-db &
pg_dump "$DATABASE_URL" > backup.sql          # restore with: psql "$DATABASE_URL" < backup.sql
```

Fly Postgres also keeps automatic daily snapshots; see the Fly docs for point-in-time restore.

## license

Copyright (C) 2026 Kristina Quinones.

This project is licensed under GPL-2.0-only. See [LICENSE](LICENSE).

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). By contributing, you agree to the [DCO](DCO) and license your work under GPL-2.0-only.
