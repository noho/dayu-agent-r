# WU-SEMANTIC-OWNERSHIP-01 P3-J S4 Implementation - AgentCodex

## Scope

- Slice: P3-J S4 - Legacy Config Exposure Re-Ownership.
- Gate: implementation.
- Design sources read:
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `docs/host/issues-implementation-control.md`
  - `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
  - `dayu/config/README.md`
- Branch: `phaseflow/host-issues-control`.
- Pre-existing unrelated dirty / untracked files were not modified:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `docs/cli_ci.md`
  - `docs/cli_ci_oracles.json`
  - `docs/cli_ci_scenarios.json`
  - `docs/reviews/code-review-20260710-135625.md`
  - `docs/reviews/code-review-20260710-141049.md`

## First-Principles Judgment

The source finding is valid. The current config schema owner is `dayu.runtime.config_loader`, but the old names `llm_models.json` and `run.json` are not current runtime config schema facts. Host design explicitly says the schema does not keep old compatibility paths. Exposing removed names through a runtime public helper gives a deleted schema artifact a runtime owner it should not have.

The only current production caller found was `dayu-cli init`, where the behavior is a narrow filesystem bootstrap guard. That semantic belongs to the CLI command, not to runtime ConfigLoader. No stop condition was hit.

## Changed Files

- `dayu/runtime/config_loader.py`
  - Removed `_LEGACY_CONFIG_FILES`.
  - Removed public `legacy_config_file_names()`.
  - Kept `config_file_names()` as the current schema file source of truth.
- `dayu/cli/commands/init.py`
  - Removed import of `legacy_config_file_names()`.
  - Added CLI-private `_LEGACY_CONFIG_FILE_NAMES`.
  - Re-owned the guard as `_raise_if_legacy_top_level_config_asset_selected(...)`.
  - Limited the guard to direct children of `workspace/config`; prompt assets named `run.json` or `llm_models.json` in subdirectories are not rejected.
- `tests/runtime/test_config_loader.py`
  - Removed runtime helper import.
  - Kept current behavior proof through `config_file_names()` and `load_runtime_config(...)`: old workspace files are ignored because they are not current schema inputs.
- `tests/cli/test_init_command.py`
  - Removed runtime helper import.
  - Kept init no-old-file generation assertions with test-local removed-name constants.
  - Added guard regression for a mistakenly selected old top-level config file.
  - Added regression that prompt sub-assets with removed config filenames are allowed.

## Legacy Exposure Decision

- Runtime public exposure: removed.
- Runtime owner of old filenames: removed.
- CLI private guard: retained, because `dayu-cli init` is the only current path that may need fail-closed protection against old names entering copied top-level config assets.
- Compatibility behavior: none added. The loader still reads only current `config_file_names()` files and does not read old workspace files.

## Stop Condition Check

- `legacy_config_file_names()` production dependencies outside CLI: none found.
- Design requirement to keep `legacy_config_file_names()` as public API: none found.
- Result: proceed.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/cli/test_init_command.py -q
```

Result: `66 passed, 3 warnings`.

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: passed.

Source scan:

```bash
rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES|llm_models\.json|run\.json' dayu tests docs README.md
```

Result classification:

- No `legacy_config_file_names` or `_LEGACY_CONFIG_FILES` remains in `dayu/` or `tests/`.
- `dayu/cli/commands/init.py` retains only CLI-private `_LEGACY_CONFIG_FILE_NAMES`.
- `tests/runtime/test_config_loader.py` and `tests/cli/test_init_command.py` retain old filename strings only as negative regression assertions.
- `dayu/config/README.md` retains old filename references to document they are deleted and not compatibility-read.
- `docs/host/design.md` and P3-J plan retain old filename references as design / gate evidence.
- Existing historical docs and reviews retain old filename references as archive evidence.
- `dayu/engine/contracts/runner_spec.py` retains a historical docstring note about OLD `llm_models.json`; this is outside S4 allowed files and not a runtime config exposure.
- `tests/engine/test_smoke_async_agent_providers.py` and `tests/engine/test_config_models.py` retain historical migration / negative assertions outside this slice.

## README Decision

- `dayu/config/README.md` was read. No update needed: it already states `dayu-cli init` generates only current schema files and old `llm_models.json` / `run.json` are deleted with no compatibility read path.
- Root `README.md` was not changed: user-visible init/config behavior did not change. The only behavior refinement is a private guard boundary for hypothetical prompt asset names.
- `tests/README.md` was not changed: no stable test command group or maintenance guidance changed.

## Residual Risks

- No current-scope residual risk remains for S4.
- Historical old-name references remain in design, archive, review, and migration evidence documents by intent. Cleaning historical documentation is outside this slice and would not change runtime exposure.
- The CLI private guard still contains removed filenames by design; it is not a runtime public API and only protects copied top-level config assets.

## Completion Status

Implementation gate for P3-J S4 is complete and ready for code review.
