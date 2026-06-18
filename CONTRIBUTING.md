# contributing

Thanks for improving UTM builder. Keep changes small, tested, and easy to review.

## setup

Run the app with Docker:

```sh
docker compose up --build
```

Open `http://utm.localhost`.

For local Python development:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest
uvicorn app.main:app --reload
```

## before you make a change

- Check whether similar logic already exists before adding new code.
- Reuse shared helpers in `app/utm.py` and `app/store.py` before creating new paths.
- Keep UI behavior in `app/static/app.js` and styling in `app/static/styles.css`.
- Keep templates focused on markup and simple presentation logic.
- Do not commit local data from `./data`.

## before you open a pull request

Run:

```sh
docker compose run --rm utm python -m pytest
```

Also check the app manually when a change touches routes, templates, JavaScript, CSS, export behavior, or persistence.

## security expectations

- Every mutating route must require CSRF validation.
- Every form that posts data must include the CSRF hidden field.
- Template data embedded in JavaScript must use safe JSON rendering.
- CSV exports must neutralize spreadsheet formulas in values and dynamic headers.
- User-provided strings should render through normal template escaping unless there is a clear, reviewed reason.

## style

- Use sentence case for headings.
- Use the oxford comma.
- Keep docs direct, conversational, and useful.
- Avoid em dashes in documentation and code comments.
- Prefer clear names over comments. Add comments only when the code is not self-explanatory.
