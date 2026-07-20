# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2a Controller Adjudication

## Scope

- Batch: Round2 Batch D2a
- Type: production-high semantic ownership fix
- Owner boundary: Host public contract / durable RUN_STARTED payload / Host construction options / Service consumption
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2a-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2a-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2a-code-review-ds.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2a-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2a-rereview-ds.md`

## Accepted Findings Closed

### 144159-06

- Decision: closed.
- Fix: Host public contract now owns `TERMINAL_RUN_STATUSES` and `is_terminal_run_status(status)`. `RunSnapshot` enforces terminal status / `TerminalResultSummary` consistency. Service consumes the Host public helper instead of maintaining a duplicate terminal set. Test fakes construct terminal summaries through the same public contract.
- Verification:
  - Host/Service focused suite passed.
  - CLI fake helper regression found by review was fixed and re-reviewed.

### 144159-07

- Decision: closed.
- Fix: `RUN_STARTED.start_reason` is decoded through a required typed `RunStartedPayload` projection that reuses `RunStartReason` codec. EventLog recovery counting and RunInput resume / runner-call classification consume the typed decoder and fail closed on missing or unknown values.
- Verification:
  - Positive tests use `RunStartReason` + `serialize_run_start_reason(...)`.
  - Negative tests cover missing, empty, and unknown `start_reason`.
  - Source scan found no positive normal-path bare start-reason fixtures except out-of-scope raw SQLite tests.

### 144159-09

- Decision: closed.
- Fix: Host public construction types now expose runtime-resolvable wait registry / poller policy Protocol contracts. `HostToolingOptions` and `OpenHostOptions` validate invalid registry or policy inputs at construction time. `open_host` no longer repeats downstream type repair.
- Verification:
  - Public option tests cover `typing.get_type_hints` and invalid construction negatives.
  - pyright passed.

## Review Findings

### D2a-F1

- Source: AgentMiMo and AgentDS.
- Decision: accepted.
- Issue: CLI test `_run_snapshot` helpers passed `terminal_result_summary=None` for terminal `RunStatus.SUCCEEDED`, violating the new Host public invariant.
- Fix: `tests/cli/test_prompt_command.py` and `tests/cli/test_interactive_command.py` now use `is_terminal_run_status(status)` and construct `TerminalResultSummary` for terminal statuses.
- Re-review: AgentMiMo and AgentDS both passed; finding closed.

### D2a-F2

- Source: AgentMiMo.
- Decision: accepted as same-pattern fragility; closed by D2a-F1 fix.
- Issue: `tests/cli/test_interactive_command.py` had the same helper shape even though current calls were non-terminal.
- Fix and re-review: closed with D2a-F1.

### D2a-F3

- Source: AgentMiMo.
- Decision: rejected for current D2a fix scope.
- Reason: `_row_rules.py` terminal string set is a pre-existing low-level SQL CHECK helper with existing drift-guard tests. It was not introduced or worsened by D2a. Moving it now would expand D2a beyond the accepted public/durable/Service owner closure.
- Destination: none for current batch; reconsider only if a later durable schema cleanup finding accepts this as owner drift.

### D2a-F4

- Source: AgentMiMo.
- Decision: rejected for current D2a fix scope.
- Reason: write-side `.value` usage for `RunStartReason` is functionally equivalent for `StrEnum` and was reported informational. D2a already moved consumers and tests to typed decoder/codec where ownership drift existed. No material correctness risk was shown.
- Destination: none.

## Controller Validation

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
  - Result: `90 passed, 3 warnings`.
- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_public_open_host_options.py tests/host/test_tooling_options.py tests/host/test_state_schema.py tests/host/test_event_log_store.py tests/host/test_run_input_builder.py tests/host/test_package_exports.py tests/host/test_recovery_scan.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_wait_callback_endpoint.py -q`
  - Result: `386 passed, 3 warnings`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.

Warnings are existing `edgar` deprecation warnings and are not caused by D2a.

## README Decision

- `dayu/host/README.md` was updated because Host public `get_run` / `RunSnapshot` terminal contract changed.
- `tests/README.md` was not updated because test hierarchy, execution commands, and maintenance policy did not change.

## Residual Risk

- No open residual risk inside D2a scope.
- D2b remains open for cancelled raw tool outcome, compaction evidence kind, memory projection, and reactive compaction findings.

## Stop Status

D2a is accepted after implementation, code review, fix, re-review, controller validation, and controller adjudication.
