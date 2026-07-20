# WU-SEMANTIC-OWNERSHIP-01 P3-J S4 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `P3-J S4 - Legacy Config Exposure Re-Ownership`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s4-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-s4-controller-validation.md`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-j-s4-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-j-s4-code-review-ds.md`

## Decision

Decision: `accepted`

AgentMiMo and AgentDS both reported no material findings.

Accepted conclusions:

- Runtime public exposure of removed config names is closed: `_LEGACY_CONFIG_FILES` and `legacy_config_file_names()` were deleted from `dayu.runtime.config_loader`.
- No compatibility wrapper or re-export remains.
- `dayu-cli init` owns the remaining private defensive guard and limits it to top-level copied config assets.
- Runtime tests no longer import a legacy helper and now prove old files are absent from the current config file set and not read.
- CLI tests prove old top-level config assets are rejected and prompt sub-assets with old names are not rejected.
- README decision is accepted: `dayu/config/README.md` already documents current config files and old filename deletion / no compatibility read path.

## Findings

No accepted findings. No fix gate required.

DS noted a non-material style observation that `tests/cli/test_init_command.py` keeps `_REMOVED_CONFIG_FILE_NAMES` without `Final`, unlike the runtime test file. This does not affect correctness, owner boundary, or public/runtime exposure, and is not accepted as a fix-gate finding.

## Validation

Controller reran:

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/cli/test_init_command.py -q`
  - Result: `66 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- `rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu tests README.md`
  - Result: no matches.
- `rg -n 'llm_models\\.json|run\\.json' dayu tests README.md`
  - Result: remaining current-scope hits are CLI private guard and negative tests; config README documents deletion / no compatibility read. Engine historical comments/tests remain outside S4 scope.

## Residual Risk

- CLI private guard intentionally retains removed filenames for top-level init asset fail-fast.
- Historical old-name references remain in Engine comments/tests and archived design/review evidence; these are not runtime config public exposure and are outside S4 scope.

## Next Gate

S4 is ready for accepted slice commit. After commit, update `docs/host/issues-implementation-control.md` and proceed to P3-J aggregate deepreview.
