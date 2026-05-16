# Gateflow Deepreview Controller Adjudication

## Scope

- Work unit: full repository deepreview fix gate
- Branch: `fix/host-p1-p7-awaiting-production-wiring`
- Reviewer artifacts:
  - `docs/reviews/repo-review-20260516-1551.md` by AgentDS
  - `docs/reviews/repo-review-20260516-1557.md` by AgentMiMo
- Controller role: adjudicate reviewer findings using direct code evidence, accept only current correctness / contract / test gaps, and prevent broad refactors without a present failure signal.

## Accepted Findings

### DS-1-accepted-engine_ingest malformed cancel payload should not escape ingestion

- Source finding: DS finding 1
- Controller severity: medium, not critical
- Direct evidence: `dayu/host/engine_ingest.py` reads `cancel_request_event_id` from the prior `RUN_CANCELLING` event through `_required_payload_text`. If the durable event payload is malformed, ingestion raises instead of returning a governed rejected diagnostic.
- Rejected reviewer claim: DS mentions an `except Exception` path turning this into `LOST`; that path is not present in current `engine_ingest.py`, so the impact is overstated.
- Accepted fix scope: make the cancel closeout path handle missing / invalid `cancel_request_event_id` as a rejected diagnostic, and add a focused regression test.

### DS-2-accepted-SQLite busy / locked retry must handle extended error codes

- Source finding: DS finding 2
- Controller severity: high
- Direct evidence: `dayu/host/durable/transaction.py` compares `sqlite_errorcode` directly with `SQLITE_BUSY` and `SQLITE_LOCKED`. Python 3.11 can expose extended SQLite result codes, so retry classification can miss busy / locked variants.
- Accepted fix scope: compare the base SQLite result code for busy / locked retry decisions, and add a unit test using synthetic sqlite errors with extended codes.

### DS-4-accepted-ToolExecutor timeout and cancellation contract is not enforced by ToolRuntime

- Source finding: DS finding 4
- Controller severity: high
- Direct evidence: `dayu/contracts/tool_executor.py` states implementations must observe `request.context.cancellation_token` and honor `request.context.timeout_seconds` for the batch handshake. `ToolRuntimeExecutor.execute` and `_execute_one` currently call the dispatcher without a timeout / cancellation race.
- Accepted fix scope: enforce batch timeout and cooperative cancellation in ToolRuntime without changing Engine public semantics; timed out or cancelled calls must return governed tool failures rather than hanging indefinitely.

### DS-5-DS-6-accepted-ToolTruncateSpec should use the existing enum and validate field combinations

- Source findings: DS findings 5 and 6
- Controller severity: medium
- Direct evidence: `ToolTruncationStrategy` already exists, but `ToolTruncateSpec.strategy` is typed as `str | None` and permits inconsistent enabled / strategy / limits combinations.
- Accepted fix scope: make `strategy` typed as `ToolTruncationStrategy | None`, validate cross-field invariants in `__post_init__`, and update production callers and tests to use the enum.

### DS-18-accepted-TruncationManager retains used cursors indefinitely

- Source finding: DS finding 18
- Controller severity: medium
- Direct evidence: `TruncationManager._store_cursor` inserts cursors and `fetch_more` only marks single-use cursors as used; there is no removal of consumed or expired cursors in the observed code path.
- Accepted fix scope: remove consumed single-use cursors and add bounded cleanup for expired cursors with focused tests.

### MiMo-2-accepted-ToolRuntime direct tests are missing for accepted behaviors

- Source finding: MiMo finding 2
- Controller severity: medium
- Direct evidence: accepted DS findings change ToolRuntime timeout / cancellation / truncation behavior, so direct tests must cover those boundaries rather than relying only on broad integration tests.
- Accepted fix scope: add or extend `tests/host/test_toolruntime*.py` and contract tests for the accepted behavior changes.

## Deferred Findings

- DS-3 / MiMo-1 / MiMo-3: broad `tool_runtime.py` module split, recovery binding persistence, and duplicate governance bounding are valid maintainability or future recovery concerns, but not safe to fold into this fix gate without a smaller design plan. Owner: later Host ToolRuntime refactor work unit.
- DS-20: orphan dispatch recovery is a real recovery capability gap if crash recovery is in current product scope, but it requires scheduler lifecycle design and durable leasing semantics. Owner: later Host recovery work unit unless the user explicitly expands this gate.
- DS-28 / MiMo-5: runner factory injection is an extension point, not a current correctness bug. Owner: later Engine provider abstraction work unit.
- DS-31 / DS-36 / DS-41 / MiMo-7: scheduler close, WAL checkpoint, poll retry backoff, and poller concurrency are operational hardening items. Owner: later runtime / Host operations hardening work unit.

## Rejected Or Evidence-Insufficient Findings

- DS-7, DS-8, DS-9, DS-10, DS-11: Engine naming / observability / theoretical concurrency findings are not current correctness defects based on direct evidence; no fix in this gate.
- DS-12, DS-13, DS-14, DS-15, DS-16, DS-17: Host / durable findings either describe existing intentional state-machine semantics, diagnostic precision, or need stronger failure evidence before changing transactional behavior.
- DS-21, DS-22, DS-23, DS-24, DS-25, DS-26, DS-27, DS-29, DS-30, DS-32, DS-33, DS-34, DS-35, DS-37, DS-38, DS-39, DS-40, DS-42: not accepted for this gate because they are either contract-style preferences, already bounded by downstream guards, future recovery assumptions, or not directly tied to a failing current path.
- DS-43 through DS-61 and MiMo-4, MiMo-6, MiMo-8: low-severity style, documentation, performance, or test-convenience items; no current correctness impact and no fix in this gate.

## Fix Gate Requirements

- Fix only accepted findings above.
- Update or add focused tests for every production behavior change.
- Run affected tests after implementation.
- Run pyright after implementation.
- Update README files only where the accepted changes alter documented current behavior or test conventions.
- Produce fix artifact at `docs/reviews/gateflow-deepreview-fix-agentcodex-20260516.md`.
- Do not commit, push, open PR, merge, approve, or enter any other gate.
