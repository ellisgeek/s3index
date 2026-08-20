## v2026.08.0 (2026-08-20)

### Feat

- package s3index as an installable CLI
- add an interactive bucket and prefix picker
- skip unchanged uploads and report per-run counts
- switch console output to Rich, confine typer/rich to cli.py
- convert CLI to Typer, add local/dry-run modes and a write guard
- add devcontainer with uv feature
- support writing indexes for all folders and navigating the tree
- initial work

### Fix

- stop the progress bar before printing a render error
- correctness bugs found by type checking
- handle S3 and config errors with clear messages and exit codes

### Refactor

- split s3index.py into src/s3index package modules

### Perf

- resolve content types by extension first, upload concurrently
