# UTM link builder

Project guide for contributors and AI assistants. This file is the source of truth for conventions in this repository.

## Project overview

UTM link builder is a local, single-user campaign tooling app for generating, saving, and exporting UTM-tagged URLs. It runs in Docker, stores data in a JSON file, and does not require an account.

**Stack:** FastAPI, Jinja2 templates, vanilla JavaScript, CSS design tokens. No frontend framework.

**Data:** `./data/utm-data.json` (ignored by Git).

**Local URL:** `http://utm.localhost` (Docker maps port 80 to 8000).

## Architecture map

| Path | Role |
|------|------|
| [`app/main.py`](app/main.py) | FastAPI routes, CSRF, form handling, CSV export, render helpers |
| [`app/utm.py`](app/utm.py) | URL building, param merging, bulk link generation |
| [`app/store.py`](app/store.py) | Thread-safe JSON persistence (`JsonStore`) |
| [`app/templates/`](app/templates/) | Jinja markup (`base.html`, `index.html`, `edit_link.html`, macros, icons) |
| [`app/static/app.js`](app/static/app.js) | Client behavior: tabs, dark mode, filter, selection, fetch saves |
| [`app/static/styles.css`](app/static/styles.css) | Design tokens, components, responsive layout |
| [`tests/`](tests/) | Pytest coverage for routes, UTM logic, and store |

```text
Browser → FastAPI routes → utm.py (URL logic) + store.py (JSON)
                         → Jinja templates + static JS/CSS
```

## Run and test

**Docker (primary):**

```sh
docker compose up --build
```

**Local Python:**

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m pytest
uvicorn app.main:app --reload
```

**Docker test (run before marking a PR ready for review):**

```sh
docker compose run --rm utm python -m pytest
```

## Security invariants

These are non-negotiable. Every change must preserve them.

- **CSRF:** Every mutating route uses `Depends(require_csrf)`. Every form includes the hidden CSRF field from `macros.html`.
- **Safe JSON in templates:** Embed data with `{{ data|tojson }}` in `<script type="application/json">` blocks. Never use `|safe` on user content.
- **CSV formula neutralization:** Use `csv_cell()` in `main.py` for exported values and dynamic headers. Client-side CSV export in `app.js` must apply the same prefix rule for formula characters.
- **Template escaping:** User strings render through normal Jinja escaping unless explicitly reviewed.
- **Local tool scope:** No auth layer. Do not add login, sessions, or multi-tenant isolation unless requirements change fundamentally.

## UI conventions

- Design tokens and components live in `styles.css`. Dark mode uses `[data-theme="dark"]` on `<html>`.
- Tab navigation (Builder / Saved links) and mode toggle (Single / Bulk) are client-side in `app.js`, persisted in `localStorage`.
- Keep markup in templates, behavior in `app.js`, styling in CSS. Reuse icon macros from `icons.html`.
- Match existing patterns: CSRF meta tag, fetch saves with `X-Requested-With: fetch`, inline success feedback.

## Engineering principles

### DRY

Before adding code, check for existing helpers in `app/utm.py`, `app/store.py`, `app/main.py`, and shared template macros (`macros.html`, `icons.html`). Consolidate duplicate URL logic, form state handling, and CSV escaping rather than copying patterns across routes, templates, or JS.

### YAGNI

This is a local single-user tool. Do not add auth, accounts, databases, REST APIs, or abstractions for hypothetical scale. Prefer the smallest change that satisfies the current requirement. No speculative config, feature flags, or "just in case" error handling for impossible states.

### Adversarial review

Treat every change as if a reviewer is actively looking for regressions. Before marking a PR ready for review, explicitly check:

- **Security:** CSRF on new mutating routes, template injection via `|safe` or raw JSON, CSV formula injection, missing validation on destructive actions (bulk delete).
- **Data integrity:** Race conditions in JsonStore writes, partial bulk saves, stale client state after fetch saves.
- **UX edge cases:** Empty filter results, indeterminate select-all, mode toggle with existing preview, dark mode flash, broken tab persistence.
- **Test gaps:** If behavior is new or risky, add or extend a pytest case rather than relying on manual checks alone.

Document findings in the PR test plan. Fix issues or call out accepted risks.

## Git workflow

- Branch from `main`: `feature/description`, `fix/description`, `chore/description`.
- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `chore:`, etc.
- **DCO required:** Every commit must include sign-off:

```sh
git commit -s -m "feat: add example"
```

- Keep PRs small and focused. Open PRs as **draft** by default.

## Copyright and licensing

- **License:** GPL-2.0-only. See [LICENSE](LICENSE).
- **Contributions:** Certified under the [DCO](DCO). See [CONTRIBUTING.md](CONTRIBUTING.md).
- **No CLA:** This project does not use a Contributor License Agreement. DCO is sufficient for GPL-2.0-only contributions at this scale.
- **New file header:**

```text
Copyright (C) 2026 Kristina Quinones
SPDX-License-Identifier: GPL-2.0-only
```

Do not remove existing headers. Git history records authorship for modified files.

## CI expectations

CI is cheap and PR-only. It does **not** run on pushes to `main` or on draft PRs.

| Job | When | What |
|-----|------|------|
| `test` | Ready PR + sync | `PYTHONPATH=. pytest` on Python 3.12 |
| `dco` | Ready PR + sync | Verifies `Signed-off-by` on all commits |

**Workflow:**

1. Open PR as draft.
2. Run tests locally while iterating.
3. Mark **Ready for review** to trigger CI.
4. Fix DCO or test failures before merge.

Docker test is manual/local before marking ready. CI does not build Docker images (saves Actions minutes).

## Maintainer settings (GitHub)

After merging CI workflow, enable in repo settings:

1. **Settings → General → Pull Requests → Require contributors to sign off on web-based commits** (DCO).
2. **Settings → Branches → Branch protection on `main`:** Require status checks `test` and `dco` before merge.

## Scope discipline

- Reuse `app/utm.py` and `app/store.py` before adding parallel logic.
- Do not commit `./data/` or design handoff artifacts (`d/`).
- Do not duplicate guidance in `AGENTS.md` or `.cursorrules`; update this file instead.
