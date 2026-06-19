# contributing

Thanks for improving UTM builder. Keep changes small, tested, and easy to review.

## setup

Run the app with Docker:

```sh
./scripts/setup-local-https.sh   # once per machine
docker compose up --build
```

Open `https://utm.localhost`.

For local Python development:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m pytest
uvicorn app.main:app --reload
```

## license

By submitting a pull request, you certify that your contribution is your original work (or you have the rights to submit it) and that you license it under **GPL-2.0-only**, the same license as this project. See [LICENSE](LICENSE).

You cannot re-license this project to a proprietary or incompatible license without consent from all copyright holders.

## Developer Certificate of Origin (DCO)

Every commit must include a `Signed-off-by` line that matches the commit author:

```text
Signed-off-by: Full Name <email@example.com>
```

This certifies your contribution under the [Developer Certificate of Origin](DCO). Use:

```sh
git commit -s -m "feat: describe your change"
```

If CI fails the DCO check, amend your commits to add sign-off or add sign-off to new commits before pushing again.

This project uses the DCO, not a Contributor License Agreement (CLA). That is intentional: contributions stay under GPL-2.0-only, and contributors keep copyright in their work. A CLA would only be worth considering if the project needed relicensing or centralized copyright assignment later.

## copyright headers

New source files should include the standard header from `app/main.py`:

```text
Copyright (C) 2026 Kristina Quinones
SPDX-License-Identifier: GPL-2.0-only
```

Do not remove existing copyright headers. Git history records authorship for modified files.

## before you make a change

- Check whether similar logic already exists before adding new code.
- Reuse shared helpers in `app/utm.py` and `app/store.py` before creating new paths.
- Keep UI behavior in `app/static/app.js` and styling in `app/static/styles.css`.
- Keep templates focused on markup and simple presentation logic.
- Do not commit local data from `./data`.
- Read [claude.md](claude.md) for architecture, security rules, and engineering principles.

## before you open a pull request

Open pull requests as **draft** by default. CI does not run on drafts. Run tests locally while you iterate:

```sh
PYTHONPATH=. python -m pytest
```

Before marking **Ready for review**, also run:

```sh
docker compose run --rm utm python -m pytest
```

Mark **Ready for review** when you want CI (`test` and `dco` jobs) and maintainer review. CI runs on ready-for-review and on each subsequent push while the PR is non-draft.

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
