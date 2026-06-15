# WU-CLI-01 / CLI-01-S1 Implementation Report

## Gate / Scope

- Gate: implementation.
- Slice: CLI-01-S1 only.
- Accepted plan: `docs/host/wu-cli-01-cli-entrypoint-plan.md`.
- Scope boundary: only CLI package skeleton, parser, help and exit contract.
- Non-goals honored: no Host / Service / Fins business execution, no old CLI implementation copy, no S2-S7 implementation.

## Changed Files

- Added `dayu/cli/__init__.py` as CLI UI adapter package overview.
- Added `dayu/cli/__main__.py` for `python -m dayu.cli`.
- Added `dayu/cli/main.py` for parse / dispatch / exit-code mapping.
- Added `dayu/cli/arg_parsing.py` with parser factory and scoped command registration:
  - registered: `init`, `prompt`, `interactive`, `download`, `upload_filing`, `upload_material`, `upload_filings_from`, `process`, `process_filing`, `process_material`;
  - intentionally not registered: `write`, `host`, `sessions`, `runs`, `cancel`, `conv`.
- Added `dayu/cli/exit_codes.py` with stable CLI exit code constants.
- Added `dayu/cli/commands/__init__.py` with S1 not-implemented placeholder runner.
- Added `tests/cli/test_arg_parsing.py` for help, parse, excluded command, placeholder, SIGINT and module-entry tests.
- Updated `tests/README.md` because adding `tests/cli/` creates a new test layer.

## Behavior Implemented

- `main(argv: Sequence[str] | None = None) -> int` only parses arguments, dispatches to the placeholder runner and maps exit codes.
- argparse help / usage exits are normalized through `SystemExit` handling:
  - help -> `0`;
  - usage error / unknown command -> `2`;
  - `KeyboardInterrupt` -> `130`.
- Registered command dispatch returns clear not-implemented text and exit `1`.
- `interactive --help` includes optional `--ticker`.
- Global args are available before and after subcommands without child parser defaults overwriting explicit values.

## Validation

- `source .venv/bin/activate && pytest tests/cli -q`
  - Result: `24 passed`.
- `source .venv/bin/activate && pytest tests/cli --cov=dayu.cli --cov-report=term-missing -q`
  - Result: `24 passed`.
  - Coverage: total `98%`; `arg_parsing.py` `100%`, `main.py` `88%`, `__main__.py` `83%`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: clean.

## README Decision

- `tests/README.md`: updated. Reason: this slice adds a new `tests/cli/` test layer, and the README explicitly requires synchronization when adding a new test layer.
- `dayu/README.md`: not updated. Reason: S1 adds a CLI skeleton under an already accepted entrypoint plan but does not change the project-level layering relationship or assembly boundary.
- `dayu/host/README.md`, `dayu/fins/README.md`, `dayu/config/README.md`, `dayu/engine/README.md`: not triggered; this slice did not modify those package trees.

## Residual Risks / Uncovered Areas

- Command execution is intentionally not implemented in S1. Real `init`, `prompt`, `interactive` and Fins direct behavior is deferred to approved later slices.
- Unsupported legacy execution flags are only parsed in S1; fail-fast execution behavior is deferred to S3/S4/S5 as planned.
- No Host / Fins cancel behavior is exercised in S1 because no Host / Fins job is started in this slice.
- `dayu-cli` console-script behavior is represented by importing `dayu.cli.main:main` and by `python -m dayu.cli`; installed package wrapper testing is deferred to packaging or smoke validation.

## Completion Status

CLI-01-S1 implementation is complete within the requested file scope. No commit, push or PR was performed.
