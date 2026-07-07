# WU-CLI-SMOKE-01 Context Slot / FMP / Scene Filter S2 Fix

## Metadata

- Gate: code review fix / re-review evidence
- Work unit: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Agent: AgentCodex
- Review artifacts:
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-ds.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-mimo.md`
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-implementation-codex.md`
- Fix artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-fix-codex.md`
- Branch: `phase/host-issues-control`
- Commit/push/PR: not performed per controller instruction

## Scope

Fixed only the controller-accepted S2 code review findings:

- DS F1: FMP timeout validation order in `dayu/service/scene_context.py`
- DS F2 / MiMo 01: `_interactive_context_slot_values` return type
- MiMo 02: prompt CLI invalid ticker E2E coverage
- MiMo 03: manual prompt `EntrypointRuntimeRequest` fixtures include `current_time`
- MiMo residual coverage: FMP resolver second-hop `search-name` failure coverage

No default HTTP User-Agent change, `base_user` manifest cleanup, prompt `current_time` consumption, real FMP network smoke, commit, push, issue or PR creation was performed.

## First-Principles Judgment

The accepted findings are valid but low-risk:

- If no FMP API key is present, Service will not call FMP, so timeout is not consumed and should not be validated on that path.
- Interactive context slots share the same runtime contract as prompt/session slots, so the return annotation should use `dict[str, JsonValue]` even though the current value is a string.
- Invalid ticker behavior was already implemented as usage-error wrapping, but lacked CLI-path regression coverage.
- Tests manually constructing prompt runtime requests should mirror real CLI slot shape where they stand in for CLI-generated prompt context.
- The FMP resolver uses the same HTTP wrapper for both hops, but the second-hop failure path should have direct coverage because it is a distinct call after a successful first hop.

## Changed Files

- `dayu/service/scene_context.py`
- `dayu/cli/commands/interactive.py`
- `tests/fins/test_fmp_company_info_resolver.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/cli/test_prompt_command.py`
- `dayu/service/README.md`
- `tests/README.md`
- `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-fix-codex.md`

## Fix Details

### DS F1

Status: fixed.

`_resolve_company_name_for_subject(...)` now normalizes ticker, checks missing or blank `fmp_api_key`, and only validates `fmp_timeout_seconds` after a key is present. This preserves timeout validation for actual FMP calls while allowing no-key fallback.

Added coverage in `test_build_entrypoint_context_slot_values_falls_back_without_fmp`: `ticker="V"`, `fmp_api_key=None`, `fmp_timeout_seconds=0` returns ticker-only subject instead of raising.

### DS F2 / MiMo 01

Status: fixed.

`_interactive_context_slot_values()` now returns `dict[str, JsonValue]`, matching prompt/session slot helper semantics. Runtime behavior remains unchanged.

### MiMo 02

Status: fixed.

Added `test_prompt_invalid_ticker_exits_with_usage_error_without_traceback`, covering prompt CLI E2E behavior for invalid `--ticker`. The test asserts usage exit, clear `dayu-cli prompt` error text, the ticker validation message, and no traceback in stdout/stderr.

### MiMo 03

Status: fixed.

Manual prompt `EntrypointRuntimeRequest` fixtures that mirror real CLI-generated prompt context now include `current_time`:

- SIGINT after accepted run id fixture
- SIGINT before accepted run id fixture
- shared `_prepare_prompt_runtime(...)` helper
- service prompt-path helper and missing required slot negative fixture

### MiMo Residual Coverage

Status: fixed.

Added `test_resolve_company_info_wraps_search_name_failure_after_symbol_success`, which lets `search-symbol` succeed, fails the second `search-name` hop, and asserts wrapped `FmpCompanyInfoResolutionError`.

## Docs Decision

- Updated `dayu/service/README.md` because `dayu/service/` changed and the README stable entrypoint list should include the existing S2 `scene_context` Service boundary.
- Updated `tests/README.md` because test coverage facts changed for prompt invalid ticker, scene context no-key timeout fallback, and FMP second-hop failure wrapping.
- Root `README.md` was not changed because user-visible CLI behavior did not change; the invalid ticker path already returned a usage error, this fix only added coverage.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/fins/test_fmp_company_info_resolver.py
# 8 passed

source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
# 91 passed, 3 warnings

source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py
# 48 passed, 3 warnings

source .venv/bin/activate && pytest tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q
# 2 passed

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

Warnings are existing `edgar` deprecation warnings. `pyright` also reported that a newer pyright version is available; this is not a type failure.

## Residual Risks

- Real FMP network smoke remains not executed. Classification: assigned to later optional validation.
- Default HTTP User-Agent remains unchanged. Classification: rejected/deferred by controller as low-risk residual.
- `base_user` manifest cleanup remains S3. Classification: assigned to later work unit.
- Prompt `current_time` asset/manifest consumption remains S3. Classification: assigned to later work unit.

## Completion Status

All controller-accepted S2 code review findings are fixed locally and covered by validation. No commit, push, issue or PR was created.
