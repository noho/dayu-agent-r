# WU-SEMANTIC-OWNERSHIP-01 P3-I Aggregate Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub-WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Aggregate base: `b24b0a76` (`Accept P3-H aggregate deepreview`)
- Included accepted commits:
  - Goal confirmation: `b46259f1`
  - Plan: `6eb0b3f5`
  - S1 public entrypoints: `6c6e278b`
  - S2 terminal cursor delivery: `8bba9a52`
  - S2 control-doc record: `ba09ac0a`
  - Aggregate artifact whitespace fix: `ee21bb59`

## Validation Results

- CLI test suite:
  - Command: `source .venv/bin/activate && pytest tests/cli -q`
  - Result: `294 passed, 3 warnings`
- Type check:
  - Command: `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- Range whitespace:
  - Command: `git diff --check b24b0a76..HEAD`
  - Result: passed
- Module help smoke:
  - `python -m dayu.web --help`: passed
  - `python -m dayu.wechat.main --help`: passed
  - `python -m dayu.render.render --help`: passed
- Console script help smoke:
  - `dayu-web --help`: passed
  - `dayu-wechat --help`: passed
  - `dayu-render --help`: passed

## Source Scans

- Public command surface:
  - Command: `rg -n "dayu-web|dayu-wechat|dayu-render" README.md tests/README.md dayu/README.md pyproject.toml`
  - Result: pyproject entry points and README/test documentation consistently expose the three reserved public commands as help/diagnostic-only entrypoints.
- Terminal cursor sites:
  - Command: `rg -n "if render_exit_code == EXIT_SUCCESS|advance_cli_terminal_cursor" dayu/cli/session_execution.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py`
  - Result: no remaining `if render_exit_code == EXIT_SUCCESS` cursor gate; three production cursor sites are covered by prompt/startup/interactive tests.

## README Decision

- `README.md`, `dayu/README.md`, and `tests/README.md` were already updated where the changed behavior falls within their documented responsibilities.
- No Host, Engine, Service, or Fins README was triggered by S2 because terminal facts, renderer policy, and Host/Service ownership were not moved.

## Propagation Audit

- Public package entrypoint truth:
  - `pyproject.toml` console scripts target importable modules.
  - The module entrypoints expose help and current unavailable diagnostics without importing optional heavy UI dependencies at import time.
  - README and tests describe the same reserved command surface and current non-implementation status.
- Terminal cursor truth:
  - Host/Service terminal facts remain the source of truth for terminal status, event id, event sequence, final answer, error, cancel reason, and lost diagnostic.
  - CLI renderers own terminal presentation and renderer exit code.
  - CLI cursor persistence advances only after a terminal result is successfully rendered, across success, failed, cancelled, and lost terminal statuses.
  - Local `terminal is None` interrupt paths do not advance cursor because no terminal event was delivered.
  - Cursor write failure remains an uncaught local CLI delivery persistence failure and does not rewrite Host/Service terminal facts or renderer exit policy.

## Residual Risk

- Cursor write failure after render can cause the same terminal to be displayed again on later reconnect. This is the accepted local delivery trade-off and is now covered by tests.
- `dayu-web`, `dayu-wechat`, and `dayu-render` remain intentionally diagnostic-only public entrypoints until future UI/render implementation work units provide real functionality.
