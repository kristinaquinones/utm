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
./scripts/setup-local-https.sh
docker compose up --build
```

`setup-local-https.sh` installs mkcert's root CA and generates `./certs/` for `utm.localhost`. Run it once per machine before the first `docker compose up`.

### Every time

```sh
docker compose up --build
```

Open `https://utm.localhost`. `http://` redirects to HTTPS.

If you skip the setup script, Caddy will refuse to start and print the same instructions.

Data is stored in `./data/utm-data.json`.

## export links

Open `https://utm.localhost/export/links.csv`, or use the export button in the app.

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
python -m pytest
uvicorn app.main:app --reload
```

## Docker notes

Caddy listens on `127.0.0.1` ports `80` and `443`, redirects HTTP to HTTPS, and proxies to the app on port `8000`. TLS certificates come from [mkcert](https://github.com/FiloSottile/mkcert) in `./certs/` (gitignored). Generate them with `./scripts/setup-local-https.sh` before the first run.

If ports `80` or `443` are already in use, change the `127.0.0.1:` port mappings in `docker-compose.yml` and use the matching local URL.

## license

Copyright (C) 2026 Kristina Quinones.

This project is licensed under GPL-2.0-only. See [LICENSE](LICENSE).

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). By contributing, you agree to the [DCO](DCO) and license your work under GPL-2.0-only.
