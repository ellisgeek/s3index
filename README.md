# s3index

A simple Python tool that generates static HTML directory-index pages for an
S3-compatible bucket.

## Usage

- Clone the repository.
- Run `uv tool install .` to install the `s3index` command.
- Copy `default.env` to `.env` and set the S3 connection details.
- Run `s3index --help` to see the available flags.
- Run `s3index` to generate and upload the indexes.

Use `--dry-run` to build and render the indexes without writing them
anywhere, or `--output-dir <path>` to write them to a local directory
instead of uploading them.

If `S3_BUCKET_NAME` is not set and you are running in a terminal, `s3index`
prompts you to pick a bucket (and, optionally, a starting prefix) instead of
failing. Pass `--interactive`/`--no-interactive` to force this on or off.
Credentials are never prompted for; set them in `.env` first.

## Development

[`just`](https://github.com/casey/just) is the task runner for this project.
It is a `uv` dev dependency, so run recipes as `uv run just <recipe>`, or
install `just` yourself (`cargo install just`, `brew install just`, etc.) to
drop the `uv run` prefix. Run `just` with no arguments to list recipes; the
same recipes back both local development and CI, so there is one place to
change a command.

Install the git hooks once, after cloning:

```
uv run just install-hooks
```

This runs ruff, `ty check`, and a few housekeeping checks before each
commit, and checks that commit messages follow
[Conventional Commits](https://www.conventionalcommits.org/) before each
commit is finalized. Run the full check suite by hand with:

```
uv run just check
```

`just test` reports coverage and fails if it drops below 100%.

`scripts/safe_run.py` runs the CLI with every Minio write method blocked, for
manual testing against a real bucket without risking a real upload. Prefer
`uv run just safe-run` over running `uv run python3 -m s3index` directly
during development.

### Releasing

1. `uv run just changelog` regenerates and stages `CHANGELOG.md`. Review the
   staged diff.
2. `uv run just release` bumps the version and commits the version bump
   together with the staged changelog, then tags the release. Versions
   follow CalVer (`YYYY.MM.MICRO`); `micro` resets to `0` automatically at
   the start of a new month.
3. `git push --follow-tags` pushes the commit and the new tag.

Pushing a `v*` tag triggers the release workflow, which builds the sdist and
wheel and publishes them to a GitHub Release.

GitHub Actions runs `just lint`, `just test` (on Python 3.10 and 3.13), and
`just smoke` on every push to `main` and every pull request. Each test run
publishes a test result summary and a coverage report to the job summary.
