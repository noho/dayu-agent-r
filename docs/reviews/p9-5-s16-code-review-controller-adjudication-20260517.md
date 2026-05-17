# P9.5 S16 Code Review Controller Adjudication

## Scope

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening
- Slice: S16 Contract Ownership Audit And Import/Public Surface Fixes
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Implementation artifact: `docs/reviews/p9-5-s16-contract-ownership-audit-implementation-20260517.md`
- Reviews:
  - `docs/reviews/p9-5-s16-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s16-code-review-ds-20260517.md`

## Controller Verdict

S16 is accepted with no blocking findings.

The implementation correctly treats S16 as an audit / guardrail slice. No production code was changed because the existing implementation had no direct Contract Ownership violation. The accepted change strengthens tests for boundaries that could otherwise drift silently: contracts cannot depend on runtime implementation, Engine cannot import tool declaration owners, Host cannot scan business tools, and `fetch_more` remains a ToolRuntime-owned attempt-local framework tool.

## Review Finding Adjudication

### AgentMiMo Review

Verdict: Accepted.

AgentMiMo reported PASS. The review confirmed that the `dayu.runtime` contracts guard, Engine `ToolCallable` / `tool_declaration` module guard, Host `importlib` / `pkgutil` scanner guard, `fetch_more` owner token scan, and attempt-local `fetch_more` factory test all match the documented Contract Ownership design. It also confirmed package exports remain stable and the new tests follow Chinese docstring / typing requirements.

### AgentDS Review

Verdict: Accepted.

AgentDS reported PASS with 0 blocking findings. The review independently checked the same boundary set and added adversarial analysis for likely overconstraint cases: contracts needing runtime log levels, Engine needing `ToolSchema`, Host needing dynamic scanning, `fetch_more` token false positives, and `FetchMoreToolCallable` symbol escape. None of those cases requires code changes under the current design.

## Controller Decisions

- The stronger `dayu.contracts` -> `dayu.runtime` prohibition is accepted. `dayu.contracts` is the lower shared contract layer; runtime may depend on contracts, not the reverse.
- The Engine `dayu.contracts.tool_declaration` module-level prohibition is accepted. Engine can still use tool schemas and tool executor contracts through their own modules; `ToolDefinition`, `ToolBundle`, and `ToolCallable` remain Host / ToolRuntime assembly inputs.
- The Host `importlib` / `pkgutil` prohibition is accepted. Host should receive already assembled `ToolBundle` inputs and must not own business tool discovery.
- The `fetch_more` token scan is accepted as a guard, not as a semantic proof. Behavior is still covered by ToolRuntime effective bundle tests; future legitimate non-owner uses must be brought back to design/controller review instead of weakening ownership silently.
- Public exports remain unchanged. No documented public contract was moved, removed, or compatibility-wrapped.

## Validation Accepted By Controller

- Baseline before S16 implementation: `pytest tests/runtime/test_import_boundary.py tests/contracts/test_import_boundary.py tests/engine/test_import_boundary.py tests/engine/contracts/test_import_boundary.py tests/host/test_import_boundary.py tests/engine/test_package_exports.py tests/host/test_package_exports.py tests/host/test_public_contracts.py tests/host/test_toolruntime_effective_bundle.py`: 71 passed.
- S16 targeted validation after implementation: `pytest tests/runtime/test_import_boundary.py tests/contracts/test_import_boundary.py tests/engine/test_import_boundary.py tests/engine/contracts/test_import_boundary.py tests/host/test_import_boundary.py tests/engine/test_package_exports.py tests/host/test_package_exports.py tests/contracts/test_package_exports.py tests/host/test_public_contracts.py tests/host/test_toolruntime_effective_bundle.py`: 77 passed.
- `python -m pyright dayu tests`: 0 errors / 0 warnings / 0 informations.
- `git diff --check`: clean.
- AgentDS additionally ran `pytest tests/host -q`: 562 passed.

## Documentation Decision

No README change is required. S16 adds tests that enforce existing architecture and Contract Ownership statements; it does not change public APIs, package exports, ToolRuntime behavior, `fetch_more` semantics, or test-running conventions.

## Residual Risk

- The `fetch_more` owner guard uses token scanning. This is intentionally conservative and may flag future non-owner mentions; such a failure should trigger controller review rather than automatic whitelist expansion.
- The Host dynamic scanning guard forbids `importlib` / `pkgutil` in Host. If future non-business infrastructure requires those modules, ownership must be re-evaluated before changing the guard.
