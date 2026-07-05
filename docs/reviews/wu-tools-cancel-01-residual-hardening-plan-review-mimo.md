# WU-TOOLS-CANCEL-01 Residual Hardening Plan Review (MiMo)

## Reviewed Target

- **Plan artifact**: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source**: `docs/host/issues-implementation-control.md`
- **Reopen decision**: `docs/reviews/wu-tools-cancel-01-residual-risk-reopen-controller.md`
- **Scope**: plan review only; no implementation, no code changes, no commits.

## Review Posture

Constructively adversarial. Default assumption: plan may have at least one material issue until evidence proves otherwise. Focus on failure modes, not style.

## Must-Fix Item Coverage

| Must-Fix Item | Plan Coverage | Assessment |
|---|---|---|
| Process envelope hint structure | S1 adds `hint` field to envelope contract; S3 migrates tools | ✓ Covered |
| Playwright cleanup smoke | S2 adds deterministic smoke with fake picklable worker | ✓ Covered |
| Fins XBRL fixture breadth | S3 creates AAPL fixture from downloaded filing | ✓ Covered |
| Process envelope contract single-source | S1 defines in `dayu.contracts.tool_execution` | ✓ Covered |
| Process capsule grace tuning | S1 adds typed `ProcessCapsuleInterruptPolicy` with validation | ✓ Covered |

All five user-upgraded must-fix items are addressed.

## Code Evidence Verified

1. **Envelope duplication**: `_DOC_PROCESS_*` (`doc_tools.py:77-82`), `_FINS_PROCESS_*` (`fins_tools.py:79-84`), `_WEB_PROCESS_*` (`web_tools.py:164-169`) duplicate the same field names. All three append `hint` into `message` because Host parser at `tool_runtime.py:6606` sets `hint=None`. ✓

2. **Grace constants**: `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS = 0.2` and `_PROCESS_CAPSULE_KILL_GRACE_SECONDS = 0.2` at `tool_runtime.py:325-326` are raw Host constants. ✓

3. **No process-group cleanup**: `InterruptibleProcessHandle.terminate()` (`interruptible_process.py:200`) calls `self._process.terminate()` directly. No `os.setsid`, `os.killpg`, or process-group semantics. ✓

4. **Playwright nested processes**: `_run_playwright_worker_process` (`web_playwright_backend.py:504-511`) creates raw `multiprocessing.Process` via spawn context. `_terminate_playwright_process` (`web_playwright_backend.py:418-428`) only terminates/kills the direct child. ✓

5. **AAPL fixture**: `workspace/portfolio/AAPL/filings/fil_0000320193-24-000123/` contains `meta.json`, `.xsd`, `_cal.xml`, `_def.xml`, `_htm.xml`, `_lab.xml`, `_pre.xml`, and `.htm` files. `meta.json` has `has_xbrl: true`. ✓

## Findings

### F01-unfixed-MEDIUM-Playwright cleanup reuse vs mirror is an unresolved design decision

- **位置**: S2 Exact changes
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: "Update Web Playwright worker cleanup to reuse the same minimal runtime abstraction or mirror the same typed process-group helper, not ad hoc raw constants."
- **反例/失败场景**: "Mirror" creates a second implementation of process-group cleanup in Playwright, diverging from `InterruptibleProcessHandle`. "Reuse" requires migrating Playwright from raw `multiprocessing.Process` to `InterruptibleProcessHandle`, which is a larger refactor than the plan implies.
- **为什么有问题**: `web_playwright_backend.py:504-511` creates `ctx.Process(target=_playwright_process_entry, ...)` directly, not via `InterruptibleProcessHandle`. The plan doesn't explicitly state which path to take.
- **直接证据**: Two independent process creation paths: `interruptible_process.py:131` (via `InterruptibleProcessHandle`) vs `web_playwright_backend.py:506` (raw `ctx.Process`).
- **影响**: Implementation agent must make an architectural decision the plan leaves open.
- **建议改法和验证点**: Resolve the "or" into a single directive. Preferred: extract a shared process-group cleanup helper to `dayu.runtime.interruptible_process` as a module-level function callable from both `InterruptibleProcessHandle` and Playwright's raw process path.
- **修复风险（低/中/高）**: 中
- **严重程度（中）**: Needs resolution before S2 implementation.

### F02-unfixed-LOW-Grace policy defaults defer tuning without guidance

- **位置**: S1, Process capsule policy #3
- **问题类型**: 非最优方案
- **当前写法**: "Defaults should preserve current behavior unless tests prove a larger value is required: 0.2 / 0.2 as named defaults are acceptable."
- **反例/失败场景**: Playwright browser processes may need more than 0.2s for SIGTERM cleanup. Without guidance on how to discover the right value, the implementation agent may iterate.
- **为什么有问题**: The reopen decision requires "grace tuning," not just "make constants typed." The plan's wording effectively punts tuning to implementation.
- **直接证据**: Reopen decision: "avoid raw hard-coded constants, use typed runtime policy/config with defaults and validation."
- **影响**: Low risk; typed structure is correct, but "tuning" may be under-delivered.
- **建议改法和验证点**: Add: "S2 Playwright cleanup smoke should measure SIGTERM-to-exit time and validate/adjust defaults."
- **修复风险（低/中/高）**: 低
- **严重程度（低）**

### F03-unfixed-LOW-`_validate_grace_seconds` doesn't validate NaN/infinity

- **位置**: S1, Process capsule policy #3
- **问题类型**: 测试缺口
- **当前写法**: "each field must be finite non-negative numeric, not bool. Negative, nan, and infinite values fail fast."
- **反例/失败场景**: `interruptible_process.py:327` only checks `grace_seconds < 0`. `float('nan') < 0` is `False`, so NaN passes. `float('inf') < 0` is `False`, so infinity passes.
- **为什么有问题**: Plan's validation requirement is correct, but existing code doesn't satisfy it. S1 tests must explicitly cover these cases.
- **直接证据**: `interruptible_process.py:327-328`: `if grace_seconds < 0: raise ValueError(...)`.
- **影响**: If implementation agent doesn't add NaN/infinity checks, typed policy accepts invalid values.
- **建议改法和验证点**: In S1 Tests, add explicit NaN/infinity/bool rejection cases.
- **修复风险（低/中/高）**: 低
- **严重程度（低）**

### F04-unfixed-LOW-`os.setsid` race window not designed around

- **位置**: S2, POSIX behavior description
- **问题类型**: 并发恢复风险
- **当前写法**: "child enters a new process group/session before running the target; terminate/kill sends signal to the process group"
- **反例/失败场景**: If parent sends SIGTERM before child calls `os.setsid()`, child is still in parent's process group. `os.killpg(parent_pgid, SIGTERM)` kills the parent.
- **为什么有问题**: The window is small (spawn context, microseconds) but real. The plan should specify the signaling strategy.
- **直接证据**: Both `interruptible_process.py:126` and `web_playwright_backend.py:504` use `multiprocessing.get_context("spawn")`.
- **影响**: Very low probability of parent self-kill; documenting the limitation is sufficient.
- **建议改法和验证点**: S2 should specify: "Signal child PID directly first; only use process-group signaling after confirming different pgid via `os.getpgid(child_pid)`."
- **修复风险（低/中/高）**: 低
- **严重程度（低）**

### F05-unfixed-LOW-S2 scope could be tightened

- **位置**: S2 Objective and Allowed files
- **问题类型**: 切片过粗
- **当前写法**: S2 combines runtime process-group cleanup (`dayu/runtime/interruptible_process.py`) with Playwright cleanup smoke (`dayu/tools/web/web_playwright_backend.py`).
- **反例/失败场景**: If runtime process-group hits OS-specific blocker, Playwright smoke is also blocked.
- **为什么有问题**: Plan's own rationale says "S2 may hit OS-specific limits." By the same logic, Playwright smoke should not depend on S2 runtime success.
- **直接证据**: S2 allowed files span two layers: runtime (`interruptible_process.py`) and tool (`web_playwright_backend.py`).
- **影响**: Minor; current scope is manageable.
- **建议改法和验证点**: Consider moving Playwright smoke to S3, which already touches `test_web_tools_provider.py`.
- **修复风险（低/中/高）**: 低
- **严重程度（低）**

## Layering Verification

| Boundary | Status | Evidence |
|---|---|---|
| `dayu.contracts` no reverse dependency | ✓ | `dayu/contracts/tool_execution.py` currently has no process envelope helpers; plan adds them without importing Host/Engine/Service/UI/Fins |
| Host may parse contract | ✓ | `tool_runtime.py:6544-6637` parses process envelopes |
| Tools may construct contract | ✓ | `doc_tools.py:1204-1220`, `fins_tools.py:1318-1334`, `web_tools.py:498-523` construct envelopes |
| `dayu.runtime` layer-neutral | ✓ | `interruptible_process.py` only imports `asyncio`, `multiprocessing`, `queue`, `time`, `dataclasses`, `typing`, `dayu.contracts.json_value` |
| No Host tool registry | ✓ | Plan does not introduce tool-name branching in Host |
| `tool_execution_timeout_seconds` preserved | ✓ | Plan explicitly states grace is cleanup-only, not a business deadline |

## AGENTS.md Constraints Check

| Constraint | Status |
|---|---|
| No `Any`/`object`/untyped signatures in proposed design | ✓ `ProcessCapsuleInterruptPolicy` is typed dataclass |
| No reverse dependency | ✓ Contract in `dayu.contracts`, parsed by Host, constructed by tools |
| `dayu.runtime` not importing Host/Engine/Service/UI/Fins | ✓ Process-group cleanup only needs `os`/`signal` from stdlib |
| No LLM-facing schema for envelope governance fields | ✓ Plan explicitly states contract is not LLM-facing |

## Open Questions

None.

## Residual Risks

1. **AAPL XBRL network dependency**: Stop condition exists but is a real implementation risk.
2. **Windows process-group cleanup**: Correctly marked unsupported/fallback.
3. **Playwright live browser cleanup**: Correctly deferred to environment-dependent testing.

## Verdict

**PASS**

The plan is code-generation-ready and addresses all five must-fix items. Five low-to-medium severity findings were identified, none blocking. The plan correctly maintains layering boundaries, avoids overcoupling, and follows project conventions.

**Findings summary**: 1 medium (F01: Playwright reuse vs mirror decision), 4 low (F02: grace tuning guidance, F03: NaN/infinity validation, F04: `os.setsid` race, F05: S2 scope). All can be resolved by the implementation agent with minimal clarification.

READY_FOR_CONTROLLER
Verdict: PASS
Findings: F01 (medium), F02-F05 (low)
