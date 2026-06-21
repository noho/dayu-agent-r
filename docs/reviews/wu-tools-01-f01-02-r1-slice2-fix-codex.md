# WU-TOOLS-01-F01-02-R1 Slice 2 Code Review Fix

## Scope

- Fix gate: Slice 2 code-review fix
- Agent: AgentCodex
- Input review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r1-slice2-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-controller-adjudication.md`
- Modified files:
  - `dayu/fins/ingestion_runtime.py`
  - `dayu/fins/ingestion/wait_adapter.py`
  - `tests/fins/test_fins_ingestion_runtime.py`

## Fixes

### S2-CR-F01

Status: fixed.

`_observation_cancelled_result(...)` now applies `_safe_observation_message(...)` before writing `FinsResultSummary.error_message`. This keeps cancellation result material under the same safe-message boundary as failure result material without changing public schema or introducing compatibility behavior.

The existing pre-activation cancel path still reports the same user-visible message: `Observation was cancelled before activation.`

Focused assertion added in `test_cancel_prepared_observation_prevents_later_activation_submit`:

- cancellation snapshot status remains `CANCELLED`;
- cancellation result status remains `CANCELLED`;
- cancellation result error kind remains `CANCELLED`;
- cancellation result error message remains stable.

### S2-CR-F02

Status: fixed.

`build_fins_wait_activation_registry(...)` now has a concise comment documenting that `tool_names` is validation-only for activation assembly, because Host activation dispatch uses the single stable `FINS_INGESTION_WAIT_ADAPTER_KEY`.

Registry behavior is unchanged:

- still one `WaitActivationAdapterRegistration`;
- still keyed by `FINS_INGESTION_WAIT_ADAPTER_KEY`;
- no per-tool activation registration added.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `68 passed`
  - Notes: 3 existing upstream `edgar` deprecation warnings.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
  - Result: `51 passed`
  - Notes: 3 existing upstream `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Notes: pyright reports a newer available version `v1.1.410`; current environment is `v1.1.409`.

## README Judgment

No README update was made.

Reason: this fix does not change user-visible installation, CLI/Web/WeChat entrypoints, workspace file locations, final-user workflow, layering, Fins public behavior, or the documented prepare/activate flow. It only tightens an internal safe-message boundary and clarifies activation registry validation intent.

## Residual Risk

- Slice 3 still must verify production assembly uses the same Fins runtime instance semantics across awaiting tool runtime, poll adapter, and activation adapter.
- Process-local prepared observation TTL remains intentionally out of scope for this slice.
- Multi-thread double activation remains covered by lock plus `submitted` flag reasoning and sequential idempotence tests; no new concurrent double-activation test was added in this minimal fix pass.
