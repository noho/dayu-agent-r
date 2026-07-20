# WU-SEMANTIC-OWNERSHIP-01 P3-E S1 Controller Validation

## Scope

Validated AgentCodex S1 implementation artifact:

- `docs/reviews/wu-semantic-ownership-01-p3-e-s1-implementation-codex.md`

S1 covers only:

- `ToolResultSuccess.ok` / `ToolResultFailure.ok` runtime invariant enforcement.
- ToolRuntime synthetic governed / truncation / accept / awaiting-accept failures no longer encode governance reason codes, `last_error_code`, `accept_rejected:*`, or diagnostic refs in LLM-facing `ToolResultFailure.hint`.
- Diagnostics remain in owner-owned message, failure metadata, Tool Trace, or existing diagnostic fields.

S2 and S3 remain unimplemented.

## Files Changed

- `dayu/contracts/tool_result.py`
- `dayu/host/tool_runtime.py`
- `tests/contracts/test_tool_result_envelope.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/fins/test_fins_storage_provider.py`
- `docs/reviews/wu-semantic-ownership-01-p3-e-s1-implementation-codex.md`

## Controller Validation

Focused required tests:

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py -q
```

Result: `151 passed, 3 warnings`.

Pyright:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

Hidden hint / diagnostic scan:

```bash
rg -n "last_error_code|_hint_with_diagnostic_refs|_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY|_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR|accept_rejected:|hidden-hint" dayu/host/tool_runtime.py tests/host
```

Result: hidden hint helper/constants, `accept_rejected:`, and `hidden-hint` have no hits. Remaining `last_error_code` hits are contract fields, accept retry state, diagnostic/message preservation code, and wait-state/read-model tests outside this hidden-hint path.

Whitespace:

```bash
git diff --check
```

Result: pass.

Coverage:

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py --cov=dayu.contracts.tool_result --cov=dayu.host.tool_runtime --cov-report=term-missing -q -k 'not process_backed and not process_capsule and not process_backed_capsule'
```

Result: `136 passed, 17 deselected`; `dayu/contracts/tool_result.py` 100%, `dayu/host/tool_runtime.py` 84%.

The earlier all-in-one coverage command including process-backed tests failed under pytest-cov because multiprocessing spawn could not pickle the patched `multiprocessing.connection.rebuild_connection`; the same test set without coverage passed. The successful coverage command excludes those process-backed cases and broadens ToolRuntime accept/diagnostic coverage.

## README Decision

No README update required for S1. The implementation changes hidden governance hints for ToolRuntime synthetic failures and runtime discriminator validation; it does not change public user workflow, CLI flags, storage paths, Host architecture contract, or test-layer organization. Business-authored process-backed failed envelope hints remain unchanged.

## Propagation Audit

- Contract discriminator truth now fails at `dayu.contracts.tool_result` construction before Host / Engine consumers branch on `ok`.
- ToolRuntime governance strings no longer travel through `ToolResultFailure.hint` into Engine LLM-facing tool messages.
- `last_error_code` is preserved in message text where it was otherwise only LLM-hint-visible, and Tool Trace diagnostics / failure metadata remain the owner-owned diagnostic paths.
- Hidden diagnostic-ref hint string protocol helper and constants are removed.

## Decision

S1 implementation is ready for independent code review.
