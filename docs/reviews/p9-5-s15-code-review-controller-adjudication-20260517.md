# P9.5 S15 Code Review Controller Adjudication

## Scope

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening
- Slice: S15 Engine / Host Necessary Logs By Level
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Implementation artifact: `docs/reviews/p9-5-s15-necessary-logs-implementation-20260517.md`
- Reviews:
  - `docs/reviews/p9-5-s15-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s15-code-review-ds-20260517.md`

## Controller Verdict

S15 is accepted with no blocking findings.

The implementation satisfies the first-principles goal of S15: add only necessary diagnostic logs for implemented Engine / Host paths, while preserving Host durable truth boundaries and avoiding sensitive payload logging. The accepted scope is Host-heavy because the audit found concrete missing observability in Host command, admission, EngineEvent ingest, LocalProxy, ToolRuntime accept barrier, wait resolution, memory projection catch-up, and projection catch-up failure level semantics. Engine agent and OpenAI runner already had substantial run / iteration / runner / protocol diagnostics, so mechanically changing Engine files would add noise without direct evidence of a missing diagnostic path.

## Review Finding Adjudication

### AgentMiMo F1: Engine-side logs missing

Verdict: Rejected as a blocking finding; recorded as an audit decision.

S15 allowed Engine files, but the plan also required auditing existing log calls before adding new ones and adding only necessary logs. The implementation artifact records that `dayu.engine.agent` already has `VERBOSE` run / iteration / runner call / tool loop / terminal coverage and that OpenAI runner/parser/SSE/HTTP modules already have provider diagnostics and warning paths. No reviewer provided a concrete Engine path that is currently unobservable or mis-leveled. Changing Engine only because the file was listed as allowed would violate the "only necessary logs" constraint and increase logging noise / leakage surface.

### AgentMiMo F2: `dispatch.py` state-advance logs missing

Verdict: Rejected as a blocking finding; no S15 code change required.

`dispatch.py` already had warning/debug diagnostics before S15. The accepted implementation added Host command/admission/LocalProxy/ingest logs around dispatch-adjacent boundaries and `admission.promotion_committed` for queue promotion outcome. No concrete missing dispatch transition with production diagnosis value was identified. This remains safe to revisit only if a later review cites a specific dispatch transition that cannot be diagnosed from EventLog/state rows and existing logs.

### AgentMiMo F9: caplog coverage limited

Verdict: Rejected as inaccurate for current diff; accepted only as residual low-risk note.

The current diff includes `tests/host/test_logging.py`, which covers command, LocalProxy, and memory catch-up logging; `tests/host/test_resolve_wait_command.py` covers resolve_wait logging; `tests/host/test_toolruntime_accept_barrier.py` covers ToolRuntime accept and projection catch-up warning level. Engine ingest logging does not yet have a dedicated caplog assertion, but its fields are bounded typed ids/status/counts and the broader ingest test suite passed. This is not a blocking gap for S15.

### AgentDS Review

Verdict: Accepted.

AgentDS independently reviewed level semantics, redaction, truth boundaries, accepted/committed transaction naming, architecture dependencies, and caplog coverage. It reported PASS with 0 blocking findings and validated `pytest tests/host`, pyright, and `git diff --check`.

## Validation Accepted By Controller

- `pytest tests/host/test_logging.py tests/host/test_toolruntime_accept_barrier.py -k "log or logging" tests/host/test_resolve_wait_command.py -k "log or logging"`: 5 passed.
- `pytest tests/engine tests/host -k "log or logging or diagnostics or dispatch or ingest or projection or toolruntime"`: 293 passed, 632 deselected.
- `pytest tests/host/test_logging.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_memory_projection.py tests/host/test_projection_runner.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_executor.py`: 163 passed.
- `pytest tests/host`: 559 passed.
- `python -m pyright dayu tests`: 0 errors / 0 warnings / 0 informations.
- `git diff --check`: clean.

## Documentation Decision

No README change is required. The stable logging semantics, field vocabulary, redaction rules, and "logs are not truth" constraints are already documented in `dayu/README.md`. S15 implements those existing rules; it does not change public Host APIs, durable state semantics, ToolRuntime contracts, wait semantics, or testing conventions.

## Residual Risk

- S15 deliberately does not implement audit / tool trace / outbox sinks. Stable querying or compliance audit must be handled by the future owner of those mechanisms, not by expanding runtime logging.
- Engine agent / OpenAI runner remain as-is after audit. If a future review identifies a concrete missing Engine diagnostic path, it should be fixed narrowly with a dedicated caplog test.
- Projection catch-up failure now records `error_type` rather than full exception traceback to avoid payload leakage. More detailed failure attribution should come from projection-local failure rows or a future trace/audit owner.
