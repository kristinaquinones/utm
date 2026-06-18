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

```sh
docker compose up --build
```

Open `http://utm.localhost`.

Data is stored in `./data/utm-data.json`.

## export links

Open `http://utm.localhost/export/links.csv`, or use the export button in the app.

If no links are saved yet, the export will still download a CSV with only the header row.

## security model

This is a local, single-user tool. It has no login screen and is intended to run on your own machine.

The app still includes a few practical safeguards:

- CSRF protection for every mutating form post.
- Safe JSON embedding for template data.
- CSV formula neutralization for exported values and dynamic headers.
- Local data excluded from Git through `.gitignore`.

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

Docker maps host port `80` to the app's internal port `8000` so `http://utm.localhost` works without editing `/etc/hosts`.

If port `80` is already in use, change the port mapping in `docker-compose.yml` and use the matching local URL.

## license

This project is licensed under GPL-2.0. See [LICENSE](LICENSE).
