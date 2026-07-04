# WU-TOOLS-CANCEL-01 S2A1 Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: `S2A1 contract / declaration / digest`
- Base commit: `8eddd26b` (`WU-TOOLS-CANCEL-01: accept typed execution plan`)
- Implementation report: `docs/reviews/wu-tools-cancel-01-s2a1-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2a1-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2a1-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-tools-cancel-01-s2a1-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2a1-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2a1-rereview-ds.md`

## Findings Adjudication

### DS F01: `utils/` direct `ToolDefinition(...)` construction sites

Decision: accepted and fixed.

The implementation correctly migrated all required `dayu/` and `tests/` construction sites from the S2A1 plan. AgentDS additionally identified three `utils/` smoke script construction sites that relied on the `ToolDefinition.execution` default. Although `utils/` was outside the plan's required scan command and pyright was already clean, accepting the advisory keeps every local direct construction site explicit and reduces future semantic drift.

Fix applied:

- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

Both AgentMiMo and AgentDS re-reviewed the fix and returned `PASS`.

### MiMo low-severity findings

Decision: recorded as non-blocking follow-up context.

- `_tool_execution_json_value(...)` currently emits stable mode strings directly instead of referencing `ToolExecutionMode.value`.
- The unknown capability `TypeError` path is not directly tested.

These do not block S2A1 because the digest shape matches the accepted plan and current tests cover all declared capability variants. S2A2 or a later cleanup may tighten these checks.

## Verdict

Controller verdict: `PASS`.

S2A1 is accepted. The implementation remains limited to contract/declaration/digest work and does not implement S2A2 Host factory wiring, production dispatch selection, or Doc/Fins/Web process-backed migration.

Next gate: S2A1 accepted slice commit, then S2A2 `Host factory wiring`.

## Validation

- `source .venv/bin/activate && pyright` -> passed, `0 errors`.
- `source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q` -> passed, `35 passed`.
- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/fins/test_fins_ingestion_tools.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_tool_runtime_schema_projection.py -q` -> passed, `115 passed`, with existing third-party `edgar` deprecation warnings.
- Direct construction scan over `dayu`, `tests`, and `utils` -> passed; all `ToolDefinition(...)` blocks include `execution=`.
- `git diff --check` -> passed.
