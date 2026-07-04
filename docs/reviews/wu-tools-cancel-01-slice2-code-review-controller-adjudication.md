# WU-TOOLS-CANCEL-01 Slice S2 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening`
- Slice: `WU-TOOLS-CANCEL-01-S2 production tools interrupt adapters`
- Base accepted slice: `eda4be1a` (`WU-TOOLS-CANCEL-01: accept S1 interrupt capsule`)
- Implementation report: `docs/reviews/wu-tools-cancel-01-slice2-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-cancel-01-slice2-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-slice2-code-review-ds.md`

## Findings Adjudication

### F01: Missing typed execution capability blocks production process-backed migration

Decision: accepted as blocking for S2 completion and #87 closeout.

AgentCodex, AgentMiMo, and AgentDS all identify the same direct evidence chain:

- `ToolDefinition` does not carry a typed execution capability.
- `BatchToolExecutionContext` does not carry a typed execution capability.
- S1's process-backed capsule exists in Host internals, but production dispatch has no typed way to select it for Doc, Fins, or Web sync tools.
- Doc, Fins, and Web sync paths still use `asyncio.to_thread(...)` around synchronous blocking work.
- Letting tools import Host capsules would violate layering; selecting by hard-coded tool names would violate the plan and AGENTS.md constraints.

This matches the plan's global stop condition: key production paths cannot be classified as production-grade non-cooperative cancel without a design/contract decision. Therefore S2 cannot be accepted as complete and issue #87 cannot be closed.

### F02: Web search/fetch timeout budget propagation remains cooperative-only

Decision: accepted as a non-blocking partial hardening, not a closeout.

Passing `context.timeout_seconds` into Web HTTP timeout budgeting is correct because it binds synchronous HTTP requests to the tool deadline. It does not make the underlying `asyncio.to_thread(...)` request physically interruptible, so it cannot satisfy the production-grade interrupt requirement by itself.

### F03: Playwright unpicklable worker fail-closed

Decision: accepted as correct partial hardening.

Failing closed when the Playwright worker is not picklable removes the unsafe same-process fallback and matches the S2 plan. The result remains a bounded failure rather than a non-interruptible production path.

### F04: MiMo low-severity test assertion breadth

Decision: accepted and fixed.

The unpicklable-worker test now requires `reason == "playwright_worker_not_picklable"` instead of also accepting `playwright_not_installed`, so it verifies the intended branch directly.

## Verdict

Controller verdict: `PASS_TO_DESIGN_GATE_WITH_PARTIAL_HARDENING`.

The current Web and Playwright changes are safe to keep and commit as partial hardening, but WU-TOOLS-CANCEL-01 must return to design/contract gate before any claim that S2 is complete or that #87 is ready for closeout.

Required next design question:

- Define a typed execution capability declaration that lets production ToolRuntime select `async_direct`, `thread_backed`, or `process_backed` without Host tool-name branching and without business tools importing Host internals.

After the design/contract gate is accepted, S2 must resume and migrate Doc, Fins read, and Web sync production paths to `process_backed` or request-abort-capable `async_direct`, with focused interrupt tests for each production path.

## Validation

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py -q` -> passed, `34 passed`.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q` -> passed, `56 passed`, with existing edgar deprecation warnings.
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q` -> passed, `23 passed`.
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q` -> passed, `42 passed`.
- `source .venv/bin/activate && pyright` -> passed, `0 errors`.
- `git diff --check` -> passed.
