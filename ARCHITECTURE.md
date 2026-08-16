# Architecture

`s3index` lists objects in an S3-compatible bucket and generates static HTML
directory-index pages, uploading each page back to the bucket.

This document describes the stack, package layout, and conventions. Keep it in sync with
the code: when a change diverges from what is written here, update this file as part of
that change.

## Stack

### Runtime

- `minio`: S3-compatible client used to list, fetch, and upload objects.
- `jinja2`: HTML templating for generated directory-index pages.
- `magika`: content-type sniffing fallback for a file extension that does not resolve to a
  known MIME type.
- `pydantic-settings`: typed configuration loaded from `.env`/environment variables.
- `humanize`: human-readable byte sizes (for example `12.3 MB`) in rendered pages.
- `yarl`: URL construction for object links.
- `typer`: CLI framework wrapping the entrypoint in commands and options.
- `rich`: console output and progress bars.
- `questionary`: interactive bucket/prefix picker for interactive mode.

### Dev

- `ruff`: lint and format.
- `ty`: type checking.
- `prek`: git hook runner (drop-in `pre-commit` replacement).
- `commitizen`: Conventional Commits enforcement and changelog generation.
- `bump-my-version`: CalVer version bumping.
- `pytest`: tests.

### Build

- `hatchling`: build backend, invoked by `uv build`.

## Layout

```
src/s3index/
├── __init__.py      # re-exports `app` from cli.py so the `s3index:app` entrypoint resolves
├── __main__.py       # `app()`, for `python -m s3index`
├── models.py         # S3Object dataclass and tree-building (from_minio, compute_totals, virtual dirs)
├── storage.py         # Minio wrapper: listing, uploads, content-sniffing, bucket/prefix browsing
├── render.py           # Jinja2 Environment and render_directory logic
├── settings.py          # Settings (pydantic-settings)
├── cli.py                # Typer app + interactive-mode wiring
└── templates/              # Jinja2 templates, packaged as package data
```

Each module is importable and unit-testable on its own. The layout isolates S3 I/O
(`storage.py`) from pure tree and render logic (`models.py`, `render.py`).

## Conventions

### Versioning

CalVer, `YYYY.MM.MICRO` (for example `2026.08.0`). `MICRO` starts at `0` each new month
and increments for each additional release within that month. Git tags mirror the version
(`v2026.08.0`). `pyproject.toml`'s `[project] version` field is the source of truth.
`bump-my-version` updates this field. No one edits it by hand.

Commitizen has no built-in support for CalVer. The commitizen project has rejected this
feature explicitly. For this reason, version bumps use `bump-my-version`, not `cz bump`.

### Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`,
`docs:`, `refactor:`, `test:`, `ci:`, optionally scoped, for example `feat(cli): ...`).
Commitizen's `commit-msg` hook enforces this format at commit time and uses it to generate
`CHANGELOG.md`.

### Docstrings

[Google Python Style Guide §3.8](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings),
kept concise:

- One-line summary in the imperative, ending in a period. Add a short elaboration only if
  the one-liner is not enough on its own.
- Function and method docstrings get `Args:`, `Returns:`, `Yields:`, and `Raises:` sections
  in the guide's format (`name: description`). Omit argument types, since the type hints
  already give them. Include a section only when it adds information beyond the signature.
- Class docstrings get an `Attributes:` section for non-obvious public attributes.
- Module docstrings are a single line describing the module's purpose.

### Comments

Keep comments minimal and single-line. The default is no comment. Add one only where
genuine confusion is possible: a non-obvious constraint, a workaround, or a surprising
edge case. Do not add a comment that restates what the code already says.
