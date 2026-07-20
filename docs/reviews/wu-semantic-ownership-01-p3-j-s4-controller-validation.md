# WU-SEMANTIC-OWNERSHIP-01 P3-J S4 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `P3-J S4 - Legacy Config Exposure Re-Ownership`
- Gate: controller validation after AgentCodex implementation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s4-implementation-codex.md`
- Selected review base: `7eb3c339`

## Owner Boundary

- Current runtime config file set owner: `dayu.runtime.config_loader.config_file_names()`.
- Removed config filename guard owner: `dayu.cli.commands.init`, only for `dayu-cli init` copied top-level config assets.
- Runtime is no longer an owner for `llm_models.json` / `run.json` legacy filename diagnostics.

## Controller Checks

Direct diff inspection confirmed:

- `dayu/runtime/config_loader.py` deletes `_LEGACY_CONFIG_FILES` and public `legacy_config_file_names()`.
- `dayu/cli/commands/init.py` imports only `config_file_names()` from runtime config loader and keeps a CLI-private `_LEGACY_CONFIG_FILE_NAMES`.
- CLI guard checks only assets whose destination parent is the workspace top-level `config` directory. Prompt sub-assets named `run.json` or `llm_models.json` are not blocked.
- Runtime tests no longer import a legacy public helper and prove old workspace files are ignored because they are absent from `config_file_names()`.
- CLI init tests still prove old files are not generated, top-level old config assets are rejected, and prompt sub-assets with removed names are allowed.

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/cli/test_init_command.py -q`
  - Result: `66 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- `rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu tests README.md`
  - Result: no matches.
- `rg -n 'llm_models\\.json|run\\.json' dayu tests README.md`
  - Result: remaining current-scope matches are CLI private guard and negative tests; `dayu/config/README.md` documents deletion / no compatibility read. Remaining Engine comments/tests are historical Engine config-migration assertions and not runtime public exposure.

## README Decision

Read:

- `dayu/config/README.md`

Decision: no README update. The README already states `dayu-cli init` generates only current config schema files and that old `llm_models.json` / `run.json` are deleted with no compatibility read path. Root `README.md` and `tests/README.md` are not triggered because user-visible init behavior, config file list, and test command guidance did not change.

## Residual Risk

- `dayu/engine/contracts/runner_spec.py` still contains a historical docstring note mentioning old `llm_models.json`; this is not a runtime config loader public exposure and is outside S4 allowed files.
- `tests/engine/test_smoke_async_agent_providers.py` and `tests/engine/test_config_models.py` retain old-name assertions as Engine migration / negative coverage outside S4 scope.
- CLI private guard intentionally retains removed filenames for top-level init asset fail-fast.
