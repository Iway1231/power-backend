# Contributing

Thanks for taking the time to improve Power Backend.

## Development Setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
python -m pytest -q
```

## Workflow

1. Open an issue for bugs, parser gaps, new upstream sources, or larger design changes.
2. Fork the repository or create a branch from `main`.
3. Keep changes focused and add tests for parser, API, or deployment behavior.
4. Run:

```powershell
ruff check .
ruff format --check .
python -m pytest -q
```

5. Open a pull request using the template.

## Parser Changes

Parser changes should include at least one of:

- a representative text fixture,
- a regression test for a previously broken message,
- an OCR image fixture when the behavior depends on image layout.

Avoid committing personal data, Telegram session files, local OCR debug output, cache files, or images that are not intended as test fixtures.

## Commit Style

Use short imperative commit messages:

```text
Add water outage parser
Fix LOE building normalization
Document Docker deployment
```

## Release Process

The project uses semantic versioning. Update `CHANGELOG.md` before release tags.
