# WU-SEMANTIC-OWNERSHIP-01 P3-I Public Entrypoints And Terminal Watermark Plan

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Gate: plan
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Design sources:
  - `docs/host/design.md`
  - `docs/engine/design.md`
- Control sources:
  - `docs/host/issues-implementation-control.md`
  - `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-goal-confirmation.md`

## Goal

Close P3-I by making the public package command surface truthful and making the local CLI terminal display cursor advance after successful terminal rendering, independent of whether the Host Run terminal status is `succeeded`, `failed`, `cancelled`, or `lost`.

## First-Principles Judgment

The motivation is valid. This is not a cosmetic packaging cleanup.

Direct code facts I rechecked:

- `pyproject.toml` declares public scripts:
  - `dayu-web = "dayu.web.__main__:main"`
  - `dayu-wechat = "dayu.wechat.main:main"`
  - `dayu-render = "dayu.render.render:main"`
- `rg --files dayu | rg '^dayu/(web|wechat|render)'` and `find dayu -maxdepth 2` show no `dayu/web`, `dayu/wechat`, or `dayu/render` package directories.
- Root `README.md` documents `dayu-web --help`, `dayu-wechat --help`, `dayu-render --help`, `python -m dayu.web`, WeChat command usage, and render usage. The README's own update constraint says code truth is higher than historical docs and current CLI/Web/WeChat entrypoints must be verified before editing.
- `pyproject.toml` also has package-data entries for `dayu.render`, so package metadata already treats `dayu.render` as a shipped package namespace.
- `dayu/cli/session_execution.py` currently calls `advance_cli_terminal_cursor(...)` only under `render_exit_code == EXIT_SUCCESS` in `execute_prompt_on_session(...)`, `_run_existing_session_startup_reconnect(...)`, and `_run_interactive_repl(...)`.
- `dayu/cli/output.py` maps prompt terminal statuses to process-like exit codes: `SUCCEEDED -> 0`, `CANCELLED -> 130`, `FAILED/LOST -> 1`. It maps interactive turn statuses differently: `FAILED/CANCELLED -> 0` to keep the REPL usable, `LOST -> 1`.
- `dayu/cli/session_terminal_cursor.py` explicitly owns only workspace-local display delivery state: "已成功展示过的 terminal 水位"; it does not express Host durable truth.
- `docs/host/design.md` states Host `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` are canonical terminal facts, and `event_sequence` is the Host event-stream cursor. The CLI cursor is therefore a downstream local delivery watermark, not a Host state transition input.
- `docs/engine/design.md` states Engine does not provide durable cursor or replay semantics; those belong to Host/EventLog or higher delivery layers.

Root cause:

- Public package metadata and user docs declare command modules that do not exist. Installed console scripts will fail during import before they can present help or a controlled current-capability diagnostic.
- CLI display delivery conflates "terminal rendered successfully to this process" with "rendered terminal status maps to success." A failed, cancelled, or lost terminal can still have been successfully displayed and should not be re-delivered on reconnect just because the Run outcome was not success.

## Restore Vs Remove Public Entrypoints

Decision: restore minimal importable public entrypoints.

Reasons:

- Both package metadata and the final-user README already expose `dayu-web`, `dayu-wechat`, and `dayu-render` as product commands. That is stronger evidence for intended public surface than the current missing modules are evidence of intentional removal.
- The control doc explicitly allows either restoring modules with smoke coverage or removing scripts/docs, but the goal confirmation records restore as the preferred direction.
- Removing the scripts would be a larger user-visible contract break: it would require deleting or heavily rewriting multiple README sections for Web, WeChat, and render. I found no direct evidence that these products were deliberately retired.
- Restoring minimal importable entrypoints is enough to make the package contract truthful for import/help smoke without pretending to implement full Web, WeChat daemon, or Pandoc render behavior in this small ownership WU.

Implementation consequence:

- The restored modules must be concrete public entrypoints, not compatibility re-export shims.
- `--help` must succeed and be covered by tests.
- Non-help execution may return a clear current-capability diagnostic if full behavior is not present in current code, but README must then be narrowed to match that real behavior. Do not leave README promising unavailable runtime workflows.
- If implementation discovers existing complete Web/WeChat/render code outside `dayu/` that can be moved safely, stop and ask for controller decision before widening beyond minimal import/help restoration.

## Non-Goals

- Do not implement a full Streamlit Web UI, full WeChat login/daemon/service manager, or full Pandoc/Chrome renderer unless direct existing implementation is found and can be restored without a new design decision.
- S1 must not create fake `dayu.render` CSS, HTML, Lua, DOCX, XLSX, Mermaid, or template resource files only to satisfy package-data globs. If a real renderer is not implemented in S1, package-data resource completion remains deferred render-capability work.
- Do not change Host terminal status, terminal event id, event sequence, final answer, error, cancel, or lost facts.
- Do not move CLI terminal cursor ownership into Host or Service.
- Do not change `FAILED`, `CANCELLED`, or `LOST` into `SUCCEEDED`.
- Do not make Outbox/read-model/projection special cases to hide bad CLI delivery semantics.
- Do not add compatibility wrappers for old import paths. Only the current `pyproject.toml` script targets are in scope.

## Design Alignment

- Host remains the truth owner for Run terminal facts and EventLog sequence.
- Service remains the owner of entrypoint runtime observation and terminal result objects.
- CLI display delivery owns the local workspace cursor after it successfully renders a terminal result.
- Packaging metadata and README own the public command list.
- Concrete command modules own whether those public command targets import, parse `--help`, and provide a controlled smoke behavior.

## Public Contract And State Changes

Public package entrypoints:

- Keep the current script names in `pyproject.toml` unless implementation proves a different target is required:
  - `dayu-web`
  - `dayu-wechat`
  - `dayu-render`
- Add importable modules matching those targets.
- Public help smoke must work without importing optional heavy dependencies at module import time.
- If `dayu-web` requires the `web` extra for real execution, optional dependency failure must be a user-readable runtime diagnostic, not an import-time crash.

CLI terminal watermark:

- Render result first.
- Once render returns without an output exception, call `advance_cli_terminal_cursor(...)` for that terminal event regardless of `render_exit_code`.
- Save and return the renderer's exit code. Watermark advancement must not participate in Host status classification or success/failure mapping.
- `terminal is None` local exits remain unwatermarked because no terminal was rendered.
- Render exceptions prevent cursor advancement because the terminal was not successfully displayed by the CLI process.
- Cursor write failure handling must not mutate or reinterpret Host terminal status. If `advance_cli_terminal_cursor(...)` raises an existing local cursor persistence exception, propagate that exception as a local CLI delivery persistence failure. Do not swallow it, do not return the stored render exit code instead, and do not convert it into Host terminal status.
- Cursor write failures can leave an already rendered terminal unwatermarked, so a later reconnect may display it again. That repeated display risk is more acceptable than silently hiding failed local persistence; the cursor store uses atomic writes, so corruption is not expected.

## Implementation Slices

Two slices are proposed. They are distinct semantic loops with different owners and validation:

1. Public package entrypoints and README truth.
2. CLI terminal display watermark after render.

More than two slices is not justified: each slice is small, has a single source-of-truth boundary, and can be independently tested.

## Slice S1 - Public Package Entrypoints And README Truth

### Objective

Restore importable public command targets for `dayu-web`, `dayu-wechat`, and `dayu-render`, with help/import smoke coverage and README truth aligned to the current implemented behavior.

### Expected Outcome

- `dayu.web.__main__:main`, `dayu.wechat.main:main`, and `dayu.render.render:main` are importable.
- `--help` for each entrypoint returns `0`.
- Public README no longer promises behavior that the restored modules do not provide.
- If new UI package modules change the documented `dayu/` architecture boundary, `dayu/README.md` is updated narrowly.

### Owner Boundary

- Packaging entrypoints and root README own declared public commands.
- Concrete `dayu.web`, `dayu.wechat`, and `dayu.render` modules own importable `main` functions and help/smoke behavior.
- Service/Host/Engine do not own this command declaration truth and must not be modified for this slice unless existing real implementation is discovered and a controller decision widens scope.

### Allowed Files / Modules

Implementation files:

- `pyproject.toml` only if script targets need a better current public target. Default: leave script names and target strings unchanged.
- `dayu/web/__init__.py`
- `dayu/web/__main__.py`
- `dayu/wechat/__init__.py`
- `dayu/wechat/main.py`
- `dayu/render/__init__.py`
- `dayu/render/render.py`

Test files:

- Prefer a focused new test file such as `tests/cli/test_public_package_entrypoints.py`.
- `tests/README.md` if the new smoke coverage changes the documented CLI test scope.

Docs:

- `README.md` because public command behavior is user-facing.
- `dayu/README.md` only if adding `dayu.web` / `dayu.wechat` package modules changes the documented UI/package boundary.
- `dayu/web/README.md` only if root README continues to link to it and implementation provides a real current developer/user reference. Otherwise remove or narrow the root README link.

### Concrete Implementation Steps

1. Add minimal packages for the three current `pyproject.toml` targets.
2. Each new module must have a Chinese module docstring and typed `main(argv: Sequence[str] | None = None) -> int`.
3. Use `argparse` or the existing CLI parser style for help. Avoid importing optional heavy dependencies at module import time.
4. `dayu-web`:
   - `--help` must describe current supported options only.
   - If full Streamlit app code is absent, non-help execution must return a clear diagnostic and non-zero code rather than raising `ModuleNotFoundError`.
   - Do not fabricate a working app.
5. `dayu-wechat`:
   - `--help` and subcommand help smoke must be controlled by the module.
   - If full login/run/service implementation is absent, non-help execution must return a clear current-capability diagnostic.
   - Do not fake login state or service management.
6. `dayu-render`:
   - `--help` must describe current supported behavior.
   - If no actual renderer exists, do not claim conversion works; return a controlled diagnostic for conversion requests.
   - If implementation chooses to add a minimal Pandoc wrapper, it must be treated as real product behavior and covered by argument and dependency-missing tests.
7. Add tests that parse `pyproject.toml` `[project.scripts]`, import the three targets, assert `main` is callable, and assert help returns `0` without optional runtime dependencies.
8. Add direct smoke tests for module execution where practical:
   - `python -m dayu.web --help`
   - `python -m dayu.wechat.main --help`
   - `python -m dayu.render.render --help`
9. Read `README.md` Agent update constraints before editing. Narrow root README command sections to the behavior actually implemented in this slice, using this per-command target checklist:
   - `dayu-web`: keep only true command/help facts and true extras installation facts. If S1 does not implement a Streamlit server, localhost workflow, or Web UI task workflow, delete those claims or mark them explicitly unavailable in the current version.
   - `dayu-wechat`: keep only command/help facts and the current-capability diagnostic. If S1 does not implement login, run, daemon/service management, service install/start/restart/stop/status/list/uninstall, relogin, or multi-instance workflows, delete those claims or mark them explicitly unavailable in the current version.
   - `dayu-render`: keep only command/help facts and the current-capability diagnostic. If S1 does not implement real DOCX, HTML, PDF, Pandoc, or browser conversion behavior, delete those claims or mark them explicitly unavailable in the current version.
   - After README edits, run `rg "dayu-web|dayu-wechat|dayu-render" README.md` and audit every hit against the restored module behavior. No README hit may describe a workflow that is absent from the implementation unless that hit explicitly says the workflow is unavailable.
10. Read `tests/README.md` constraints before editing. Update only if the new test category changes documented test coverage.
11. If `dayu/README.md` is touched, first read its Agent update constraints and only update cross-package boundary facts, not user command instructions.

### Tests / Validation Commands

Focused:

```bash
source .venv/bin/activate && pytest tests/cli/test_public_package_entrypoints.py -q
source .venv/bin/activate && python -m dayu.web --help
source .venv/bin/activate && python -m dayu.wechat.main --help
source .venv/bin/activate && python -m dayu.render.render --help
rg "dayu-web|dayu-wechat|dayu-render" README.md
```

Public entrypoint smoke through package script metadata:

```bash
source .venv/bin/activate && python - <<'PY'
import importlib
import tomllib
from pathlib import Path

scripts = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
for name in ("dayu-web", "dayu-wechat", "dayu-render"):
    module_name, function_name = scripts[name].split(":")
    module = importlib.import_module(module_name)
    target = getattr(module, function_name)
    print(f"{name}: {module_name}:{function_name} -> {target}")
PY
```

If editable console scripts are installed in the active venv:

```bash
source .venv/bin/activate && dayu-web --help
source .venv/bin/activate && dayu-wechat --help
source .venv/bin/activate && dayu-render --help
```

Global validation:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

### Stop Condition

Stop and return to controller if any of these are found:

- Existing full Web/WeChat/render implementation exists outside `dayu/` and restoring it would require moving product code, adding dependencies, or changing architecture beyond import/help.
- Root README cannot be made truthful without deleting the public command contract entirely.
- Adding `dayu.web` / `dayu.wechat` conflicts with `dayu/README.md` or Host design in a way that needs a design-source update rather than a plan-local decision.

### Propagation Audit

- Fact produced: public command names and script targets in `pyproject.toml`.
- Validation owner: new import/help tests parse `pyproject.toml` and import the exact targets.
- Persistence/distribution owner: setuptools package discovery includes `dayu*`; new packages become importable in installed builds.
- Projection owner: root README describes only commands and behavior that current modules actually support.
- User/LLM visible outputs: command help and current-capability diagnostics are plain user-facing text, not Host/Engine internal facts.
- Consistency check: no README command name should point to a missing module; no module help should claim unimplemented behavior.
- Deferred render resources: if S1 does not implement real render behavior, `dayu.render` package-data resource files are not fabricated and remain a named render-capability residual for the future renderer owner.

## Slice S2 - CLI Terminal Cursor After Successful Render

### Objective

Advance the workspace-local CLI terminal cursor after a terminal result is successfully rendered, including failed, cancelled, and lost Host terminal statuses, while preserving renderer-owned exit-code semantics.

### Expected Outcome

- `execute_prompt_on_session(...)` advances cursor for rendered `FAILED`, `CANCELLED`, and `LOST` prompt terminal results.
- `_run_interactive_repl(...)` advances cursor for rendered non-success interactive terminal results, including `LOST`.
- `_run_existing_session_startup_reconnect(...)` advances cursor for rendered non-success startup terminal results before returning the renderer exit code.
- `terminal is None` local second-interrupt exits remain unwatermarked.
- Host/Service code is unchanged for terminal status semantics.

### Owner Boundary

- Host/Service own terminal status, terminal event id, terminal event sequence, final answer, error, cancel, and lost facts.
- CLI output/rendering owns terminal display delivery to stdout/stderr.
- `dayu.cli.session_terminal_cursor` owns local display watermark persistence.
- The fix must land in `dayu.cli.session_execution` or a direct CLI helper because the bug is the timing/condition of local cursor advancement after rendering.

### Allowed Files / Modules

Implementation files:

- `dayu/cli/session_execution.py`
- Optional: `dayu/cli/session_terminal_cursor.py` only for docstring wording if implementation needs to clarify "rendered terminal" semantics. Do not change store schema unless direct implementation evidence requires it.

Test files:

- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- Optional: `tests/cli/test_session_terminal_cursor.py` only if store helper semantics are directly changed.
- `tests/README.md` if the documented CLI terminal cursor coverage needs a narrow update.

### Concrete Implementation Steps

1. In `execute_prompt_on_session(...)`:
   - Keep `terminal is None -> EXIT_KEYBOARD_INTERRUPT`.
   - Call `render_prompt_terminal_result(terminal)` and store `render_exit_code`.
   - After the render call returns, call `advance_cli_terminal_cursor(...)` unconditionally for that terminal.
   - If render raises, do not advance cursor.
   - If cursor advancement raises, let that local persistence exception propagate; do not return `render_exit_code` as if delivery-state persistence succeeded.
   - Return the stored `render_exit_code`.
2. In `_run_existing_session_startup_reconnect(...)`:
   - For each `terminal` in `startup.terminal_results`, call `render_interactive_terminal_result(terminal)` and store `render_exit_code`.
   - Advance cursor after render returns.
   - If cursor advancement raises, stop the startup reconnect path by propagating that local persistence exception. Already rendered but unwatermarked terminal output may repeat on a later reconnect; this is the explicit trade-off for not hiding local cursor persistence failure.
   - Then, if `render_exit_code != EXIT_SUCCESS`, return it.
   - Continue to next startup terminal only after its cursor is advanced.
3. In `_run_interactive_repl(...)`:
   - Render through `render_interactive_terminal_result(...)` or `effective_run_view.render_terminal_result(...)` exactly as today.
   - Advance cursor after render returns.
   - If render raises, do not advance cursor. If cursor advancement raises, propagate that local persistence exception.
   - Then, if `render_exit_code != EXIT_SUCCESS`, return it.
   - Increment `turn_index` only after cursor advancement for a continuing turn.
4. Do not move this logic into Service. `EntrypointRunTerminalResult` remains a Service result; the decision "this CLI process displayed it" is CLI-owned.
5. Do not alter `render_prompt_terminal_result(...)` or `render_interactive_terminal_result(...)` status-to-exit-code mapping unless a regression test proves current mapping is wrong. Current P3-I does not require changing process exit policy.
6. Do not catch and reinterpret Host terminal facts. If cursor persistence raises an existing local cursor error, do not rewrite the terminal status or produce a fake successful terminal.
7. Add regression tests:
   - Prompt existing-session path parametrize `HostTerminalStatus.FAILED`, `CANCELLED`, `LOST`; assert rendered exit code remains the renderer's code and cursor file records the terminal event id/sequence.
   - At least one negative local-exit test must prove no cursor advancement happens when `terminal is None`; extend or add a prompt SIGINT-before-run-id or equivalent local interrupt test that asserts the cursor record remains empty.
   - Interactive turn path parametrize `FAILED`, `CANCELLED`, `LOST`; assert cursor advances after the rendered terminal. For `FAILED`/`CANCELLED`, the REPL may continue and then exit on EOF; for `LOST`, return failure after cursor advancement.
   - Startup reconnect path parametrize `FAILED`, `CANCELLED`, `LOST`; assert the startup terminal is watermarked after render, including the path that returns non-zero.
   - Existing success tests must still pass and should not be duplicated unnecessarily.
8. If tests need to compare exit codes, use public constants from `dayu.cli.exit_codes` and current renderer behavior. Do not infer exit code from Host status in test assertions where renderer policy is the owner.
9. Read `tests/README.md` Agent update constraints before deciding whether to update the documented CLI cursor coverage.

### Tests / Validation Commands

Focused:

```bash
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_terminal_cursor.py -q
```

Targeted cursor regression names should include the new cases, for example:

```bash
source .venv/bin/activate && pytest \
  tests/cli/test_prompt_command.py::test_prompt_existing_session_advances_terminal_cursor_after_rendering_non_success_terminal \
  tests/cli/test_prompt_command.py::test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor \
  tests/cli/test_interactive_command.py::test_interactive_existing_session_advances_terminal_cursor_after_rendering_non_success_turn \
  tests/cli/test_interactive_command.py::test_interactive_startup_reconnect_advances_terminal_cursor_after_rendering_non_success_terminal \
  -q
```

Broader CLI validation:

```bash
source .venv/bin/activate && pytest tests/cli -q
```

Global validation:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

### Stop Condition

Stop and return to controller if any implementation path requires:

- Changing Host/Service terminal status semantics.
- Writing the CLI terminal cursor from Host/Service.
- Treating `FAILED`, `CANCELLED`, or `LOST` as `SUCCEEDED`.
- Advancing cursor before render returns.
- Creating display dedupe special cases in outbox/read-model/projection instead of the CLI cursor owner.

### Propagation Audit

- Fact produced: Host terminal result contains `terminal_status`, `terminal_event_id`, and `event_sequence`.
- Service projection: `dayu.service.entrypoint_runtime` returns `EntrypointRunTerminalResult` without changing terminal facts.
- CLI display: `dayu.cli.output` or `InteractiveRunView` renders the terminal and returns renderer-owned exit code.
- CLI local persistence: `dayu.cli.session_execution` advances `dayu.cli.session_terminal_cursor` after render returns.
- Startup projection: future interactive startup reconnect reads the cursor and `seen_terminal_event_ids`, preventing duplicate display of already rendered terminals.
- User-visible output: exit code and stdout/stderr remain determined by renderer policy, not by watermark advancement.

## README Trigger Decision

Implementation must read target README constraints before editing:

- `README.md`: triggered by public command entrypoints and user-visible CLI/Web/WeChat/render behavior. I already rechecked its Agent update constraints for this plan; implementation must re-read before editing.
- `tests/README.md`: triggered if new tests alter documented CLI/public entrypoint coverage. I already rechecked its constraints for this plan; implementation must re-read before editing.
- `dayu/README.md`: triggered only if adding `dayu.web` / `dayu.wechat` changes documented package/layer boundary. If touched, read its Agent update constraints first and keep changes to stable architecture facts.
- `dayu/host/README.md`, `dayu/engine/README.md`, `dayu/service/README.md`: not expected to be triggered because S2 must not change Host/Engine/Service ownership or behavior. If implementation unexpectedly touches those packages, stop and reassess README triggers.

## Aggregate Validation Matrix

After both slices:

```bash
source .venv/bin/activate && pytest tests/cli/test_public_package_entrypoints.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_terminal_cursor.py -q
source .venv/bin/activate && pytest tests/cli -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
source .venv/bin/activate && python -m dayu.web --help
source .venv/bin/activate && python -m dayu.wechat.main --help
source .venv/bin/activate && python -m dayu.render.render --help
git diff --check
```

If console scripts are installed in the active environment:

```bash
source .venv/bin/activate && dayu-web --help
source .venv/bin/activate && dayu-wechat --help
source .venv/bin/activate && dayu-render --help
```

## Risks And Residuals

- Minimal entrypoint restoration reduces import/help failure but does not deliver full Web/WeChat/render product functionality. README must be narrowed so this is not hidden from users.
- S1 does not create fake `dayu.render` package-data resources. If real render behavior is not restored, completing CSS/HTML/Lua/template and conversion resource files remains deferred render-capability work.
- If console scripts are not installed in the local venv, script-name smoke may need an editable reinstall or a metadata/import smoke fallback. The import/help tests remain required either way.
- Cursor write failures after render remain local delivery persistence errors. This WU must not disguise them as Host terminal status changes, must not swallow them, and must not convert them into the renderer's stored exit code. Repeated terminal display after such a failure is an accepted local-delivery trade-off.
- `RUN_LOST` may not always produce public outbox items per Host design. This slice only handles terminal results that Service/CLI already receives and renders.

## Completion Report Format

Implementation closeout must report:

- Changed files and slice id.
- Tests and pyright commands run with results.
- Public entrypoint import/help smoke results.
- Terminal cursor non-success regression results.
- README decisions and files updated or explicitly not updated.
- Propagation audit result.
- Residual risks or uncovered areas.
