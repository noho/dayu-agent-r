# Phase 10.5 Slice 3 Implementation Artifact

## Gate

P10.5 implementation Slice 3.

## Slice

Public Request Contract, Effective Config And Tool Set Freeze.

## Changed Files

- `dayu/host/api.py`
- `dayu/host/admission.py`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `dayu/host/run_input.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/README.md`
- `tests/README.md`
- `tests/host/test_submit_followup_public_contract.py`
- `tests/host/test_per_run_tool_selection.py`
- `tests/host/test_effective_execution_config.py`
- Existing focused/boundary tests updated for the migrated `SubmitFollowupRequest` shape:
  `tests/host/test_admission_multiprocess.py`,
  `tests/host/test_admission_queue.py`,
  `tests/host/test_command_handle.py`,
  `tests/host/test_open_host_runtime.py`,
  `tests/host/test_projection_read_model.py`,
  `tests/host/test_public_cancel_session_runs.py`,
  `tests/host/test_public_contracts.py`,
  `tests/host/test_public_lifecycle_smoke.py`,
  `tests/host/test_public_run_api.py`.

## Implemented Plan Items

- Migrated `SubmitFollowupRequest` from `HostInput` envelope to typed fields:
  `system_prompt`, `user_prompt`, `tool_names`, `runner_spec`,
  `runner_options`, and `agent_policy`.
- Kept ordinary first prompt and follow-up prompt on the same public
  `submit_followup(queue)` path under `open_host`.
- Implemented field-level partial merge for runner config: each of
  `runner_spec`, `runner_options`, and `agent_policy` independently defaults to
  opener ordinary baseline when omitted and uses the complete typed request
  value when provided.
- Implemented `tool_names` semantics:
  `None` means all construction-time business tools, empty `frozenset()` means
  no business tools, and non-empty `frozenset[str]` selects a subset.
- Added admission-time unknown tool rejection before durable canonical facts are
  written.
- Froze effective execution config and effective business tool set into the
  `USER_INPUT_ACCEPTED` EventLog payload, then made dispatch read that frozen
  view before constructing `AgentRunRequest`.
- Wired `AttemptDispatchSnapshot.policy_snapshot_ref` to the frozen policy ref
  instead of the local fallback ref.
- Added effective business tool filtering to `EffectiveToolBundleBuildRequest`
  and `EffectiveToolBundleBuilder`.
- Made `RunInputBuilder` consume the frozen `system_prompt` and include it as a
  system message.
- Renamed `FollowupSnapshot.current_cursor` to `command_watermark` and kept it
  as the command commit durable read watermark, not a watch cursor.

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q`
  - Passed: 9 tests.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Passed: 0 errors, 0 warnings.

## Docs Decision

- Updated `dayu/host/README.md` because the public request shape, per-run tool
  selector semantics, and `FollowupSnapshot` watermark wording changed.
- Updated `tests/README.md` because new focused Host public contract tests were
  added.

## Residual Risks / Open Questions

- No durable schema change was required; effective refs are stored in existing
  EventLog payload JSON and consumed through existing Run input event refs.
- `submit_followup(steer)`, retry, replay, live session event fanout, recovery,
  and real runner smoke remain outside Slice 3.
- Low-level `create_host_command_handle` does not provide an opener ordinary
  baseline; public production Slice 3 behavior is through `open_host(options)`.

## Stop Status

Slice 3 implementation complete. Stopped before Slice 4/5/6. No commit, no
push, no PR.
