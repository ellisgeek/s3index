# Task runner for local development and CI. Run `just` to list recipes.

set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    just --list

# Install git hooks (prek + commitizen).
install-hooks:
    prek install
    prek install --hook-type commit-msg

# Run lint, type checks, and housekeeping hooks over the whole tree.
lint:
    prek run --all-files

# Run the type checker directly (also covered by `just lint`).
typecheck:
    ty check

# Run the test suite with coverage.
test:
    pytest

# Run lint and tests together.
check: lint test

# Build the sdist and wheel.
build: check
    uv build

# Smoke-test the built CLI: package installs and the entrypoint runs.
smoke: build
    python -m s3index --help

# Run the CLI with every Minio write blocked, for manual testing against a real bucket.
safe-run *args:
    python3 scripts/safe_run.py {{ args }}

# Regenerate CHANGELOG.md under the exact version about to be released, then
# bump the CalVer version, commit, and tag it.
release:
    #!/usr/bin/env bash
    set -euo pipefail
    next_version="$(bump-my-version show --increment micro new_version)"
    cz changelog --unreleased-version "v${next_version}"
    git add CHANGELOG.md
    bump-my-version bump --allow-dirty --new-version "${next_version}"
