# s3index

A simple Python tool that generates static HTML directory-index pages for an
S3-compatible bucket.

## Usage

- Clone the repository.
- Copy `default.env` to `.env` and set the S3 connection details.
- Run `uv run s3index.py --help` to see the available flags.
- Run `uv run s3index.py` to generate and upload the indexes.

Use `--dry-run` to build and render the indexes without writing them
anywhere, or `--output-dir <path>` to write them to a local directory
instead of uploading them.

If `S3_BUCKET_NAME` is not set and you are running in a terminal, `s3index`
prompts you to pick a bucket (and, optionally, a starting prefix) instead of
failing. Pass `--interactive`/`--no-interactive` to force this on or off.
Credentials are never prompted for; set them in `.env` first.

## Development

Install the git hooks once, after cloning:

```
uv run prek install
uv run prek install --hook-type commit-msg
```

This runs ruff, `ty check`, and a few housekeeping checks before each
commit, and checks that commit messages follow
[Conventional Commits](https://www.conventionalcommits.org/) before each
commit is finalized. Run the full check suite by hand with:

```
uv run prek run --all-files
uv run ty check
uv run pytest
```

`pytest` also reports coverage and fails if it drops below 100%.

`scripts/safe_run.py` runs the CLI with every Minio write method blocked, for
manual testing against a real bucket without risking a real upload. Prefer it
over running `s3index.py` directly during development.

### Releasing

1. `uv run cz changelog`, then review and commit the updated `CHANGELOG.md`.
2. `uv run bump-my-version bump micro` bumps the version, commits, and tags
   the release. Versions follow CalVer (`YYYY.MM.MICRO`); `micro` resets to
   `0` automatically at the start of a new month.

## TODOs

- Packaging: installable entrypoint (`uv tool install .`), instead of `uv run s3index.py`.
- CI/CD: run the checks above on every push and pull request.
