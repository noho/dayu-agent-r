# Phase 12 Slice 3 Code Review Controller Adjudication

## Scope

- Work unit: Phase 12 ToolsDiscovery / ScenePrepare / ConfigLoader runtime assembly
- Gate: Phase 12 Slice 3 code review adjudication
- Implementation artifact: `docs/reviews/phase12-slice3-implementation-codex-20260521.md`
- Review artifacts:
  - `docs/reviews/phase12-slice3-code-review-mimo-20260521.md`
  - `docs/reviews/phase12-slice3-code-review-ds-20260521.md`

## Verdict

Both reviewers returned PASS with blocking findings count = 0. The implementation satisfies the Phase 12 design boundary: `ConfigLoader` is layer-neutral, old config files are removed without compatibility reads, config values are preserved raw, and Host public interface is unchanged.

Controller decision: enter a narrow Slice 3 fix for test hardening only. No production schema redesign is required.

## Findings Adjudication

### P12-S3-F1: missing-parent `extends` branch lacks regression coverage

- Sources: MiMo finding 1, DS finding 1.
- Decision: accepted-current-fix.
- Rationale: The implementation appears correct, but missing-parent inheritance is a core ConfigLoader fail-fast path. A focused test is cheap and prevents future regressions in the schema boundary.

### P12-S3-F2: `test_default_models_do_not_use_extra_payloads_bag` assertion does not match its name

- Source: MiMo finding 2.
- Decision: accepted-current-fix.
- Rationale: The test currently asserts `provider_request_extension is not None`, which is not equivalent to "no extra payload bag" and may incorrectly constrain valid future raw provider extension values. The test should assert the typed model view has no `extra_payloads` field or otherwise match its name.

### P12-S3-F3: non-map top-level workspace overlay lacks regression coverage

- Source: MiMo finding 3.
- Decision: accepted-current-fix.
- Rationale: Non-map top-level overlay is part of the explicit overlay contract, for example `default_profile_id`. It should have direct coverage because Service selection depends on these top-level defaults.

### P12-S3-F4: additional validation branches lack focused tests

- Source: DS findings 2 and 3 plus residual risk notes.
- Decision: accepted-current-fix for narrow tests covering invalid `extends` type and lane TTL / heartbeat ordering. Other residuals are deferred as non-blocking coverage expansion.
- Rationale: Invalid `extends` shape and lane TTL / heartbeat ordering are explicit ConfigLoader validation behavior. They can be covered without changing production code.

## Required Fix Scope

Fix should be limited to:

- `tests/runtime/test_config_loader.py`
- `tests/engine/test_config_models.py`
- `docs/reviews/phase12-slice3-implementation-codex-20260521.md` addendum if useful

No production code changes are expected unless a new test reveals a real implementation defect.

## Validation Required After Fix

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/engine/test_config_models.py -q`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime tests/engine/test_config_models.py`
- `git diff --check`
