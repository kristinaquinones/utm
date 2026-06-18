# UTM link builder

A small local app for generating, saving, editing, deleting, templating, bulk-generating, and exporting UTM links.

## run locally with Docker

```sh
docker compose up --build
```

Open `http://utm.localhost`.

Data is stored in `./data/utm-data.json`.

## features

- Generate one UTM link from a base URL and parameter fields.
- Add custom key-value parameters.
- Save, edit, and delete generated links.
- Save reusable parameter templates.
- Apply templates to the generator form.
- Bulk-generate links by varying one parameter across multiple values.
- Export saved links as CSV.

## development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest
uvicorn app.main:app --reload
```
