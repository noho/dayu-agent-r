# WU-WAIT-01 Slice 1 Code Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-01 / issue-89
- Gate: Slice 1 code review
- Reviewed implementation artifact: `docs/reviews/wu-wait-01-slice1-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/code-review-20260621-224502.md` (AgentMiMo)
  - `docs/reviews/code-review-20260621-224440.md` (AgentDS)
- Base: accepted plan commit `bf359ebb`
- Reviewed scope: current uncommitted Host callback contract and adapter implementation.

## Findings Judgment

### S1-CR-F01: digest outcome JSON projection is duplicated

- Sources:
  - AgentMiMo finding 1, low severity.
  - AgentDS F1, medium severity.
- Judgment: accepted.
- Controller severity: medium.
- Direct evidence:
  - `dayu/host/wait_callback.py` defines `_resolve_outcome_json(...)` and helper JSON projection functions for callback digest calculation.
  - `dayu/host/waiting.py` defines the same outcome JSON projection shape for `_wait_resolution_digest(...)`.
  - Both digests are intended to use the same material: `wait_id`, `idempotency_key`, and outcome JSON.
- Rationale:
  - The two implementations are currently equivalent, so this is not a current behavior failure.
  - The repeated digest material projection violates the project rule against duplicated data-processing logic and creates future drift risk in the idempotency truth path.
  - The fix should extract the outcome JSON projection to a Host-owned shared helper without changing digest semantics or widening public API.
- Required fix:
  - Move the resolve-wait outcome digest material projection to a single Host durable/helper module, or otherwise make both `waiting.py` and `wait_callback.py` call the same implementation.
  - Keep the helper layer-neutral within Host and avoid exposing a new broad public contract unless necessary.
  - Add or update tests proving callback digest and resolve-wait digest remain aligned for completed and at least one non-completed outcome.

### S1-CR-F02: callback stale timestamp parser does not reuse Host timestamp helper

- Source:
  - AgentDS F2, low severity.
- Judgment: accepted.
- Controller severity: low.
- Direct evidence:
  - `dayu/host/durable/codec.py` already provides `parse_utc_timestamp(...)`.
  - `dayu/host/wait_callback.py` defines `_parse_utc_timestamp(...)` using a broader `datetime.fromisoformat(...)` parser.
  - Host durable timestamps are written through fixed UTC `Z` formatting helpers.
- Rationale:
  - The stale-boundary parser should consume Host durable timestamp truth with the same helper used by existing Host durable/read paths.
  - This is a small correctness-hardening and maintainability fix; normal stored values are expected to behave the same after the fix.
- Required fix:
  - Replace the local parser with the existing Host durable timestamp parser.
  - Preserve the current invalid boundary mapping to `INVALID_WAIT_STATE`.
  - Add or update a focused test for invalid stored boundary format if it is not already covered.

### S1-CR-F03: redundant Z to +00:00 normalization

- Source:
  - AgentDS F3, low severity.
- Judgment: accepted-as-covered-by S1-CR-F02.
- Rationale:
  - Removing the local parser through S1-CR-F02 also removes this redundant code path.
  - No separate fix or review item is needed.

## Rejected / Deferred Findings

- None.

## Required Next Gate

Dispatch AgentCodex for fix gate.

Allowed scope:

- `dayu/host/wait_callback.py`
- `dayu/host/waiting.py`
- a Host-local shared helper module if needed, preferably under `dayu/host/durable/`
- focused Host tests covering digest alignment and invalid stale timestamp boundary
- README only if public behavior or documented contract changes, which is not expected
- a fix artifact under `docs/reviews/`

Non-goals:

- Do not implement Service/Web callback route.
- Do not change durable schema.
- Do not change digest semantics.
- Do not expose `HostCommandWaitCallbackPort` from package root.
- Do not broaden issue-90 poller or issue-92 physical cancel scope.

Required validation:

- `pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
- `pyright`
