# WU-TOOLS-CANCEL-01 Residual Hardening Aggregate / Final Review

## Scope

- Mode: current changes (deepreview — aggregate / final review)
- Branch: `phase/wu-tools-cancel-01`
- Review range: commits `6166d0e9..HEAD` (da047a45, 7e856b05, d7541272, 4f9df113, 98cdc872, aa10ab0f)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-review-ds.md`
- Review date: 2026-07-05T16:45:13+08:00
- Reviewer: AgentDS (code-review stance)
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Plan truth: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md`
- Existing review artifacts: `docs/reviews/wu-tools-cancel-01-residual-hardening-*`
- Included scope: all files in diff (`6166d0e9..HEAD`), 76 files, +17831/-277 lines
- Excluded scope: no exclusions; all production, test, fixture, docs, and review artifact changes reviewed
- Parallel review coverage: 无。本轮为 aggregate review，由单一 reviewer 整合 S1-S4 已裁决 findings 并做全量 cross-slice 验证。

## Evidence Collected

### Independent Validation Matrix (Controller-Rerun)

```text
pytest tests/host/test_toolruntime_executor.py tests/host/test_tooling_options.py tests/host/test_public_open_host_options.py -q
  → 89 passed

pytest tests/runtime/test_interruptible_process.py -q
  → 19 passed

pytest tests/tools/web/test_web_tools_provider.py -q
  → 34 passed, 1 skipped (live browser smoke requires DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1)

pytest tests/fins/test_fins_storage_provider.py -q
  → 33 passed

pytest tests/service/test_host_assembly.py -q
  → 52 passed

pyright dayu/ tests/ utils/
  → 0 errors, 0 warnings, 0 informations

git diff --check
  → passed
```

### Architecture Boundary Verification

**dayu.runtime layer neutrality**:
```text
$ rg -n "from dayu\.(host|engine|service|ui|fins)" dayu/runtime/ --no-heading
  → (no results)
```
`dayu.runtime` has zero imports from `dayu.host`, `dayu.engine`, `dayu.service`, `dayu.ui`, or `dayu.fins`. ✓

**Host decoupling from concrete tools**:
```text
$ rg -n "from dayu\.(tools|fins)" dayu/host/tool_runtime.py --no-heading | grep -v "dayu\.host\."
  → (no results)
```
Host `tool_runtime.py` imports only from `dayu.contracts`, `dayu.runtime`, and `dayu.host.*` (same-layer). No imports from `dayu.tools`, `dayu.fins`, or concrete Doc/Web/Fins modules. ✓

**dayu.contracts layer neutrality**:
```text
$ rg -n "from dayu\.(host|engine|service|ui|fins)" dayu/contracts/ -r --no-heading
  → (no results)
```
`dayu.contracts` has zero imports from Host, Engine, Service, UI, or Fins. ✓

### Grep Verification (Plan-Required Assertions)

**Old magic constants removed from active ToolRuntime code path**:
```text
$ rg -n "_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS|_PROCESS_CAPSULE_KILL_GRACE_SECONDS" dayu/ tests/ --no-heading
dayu/host/tooling.py:28:_DEFAULT_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS: Final[float] = 0.2
dayu/host/tooling.py:29:_DEFAULT_PROCESS_CAPSULE_KILL_GRACE_SECONDS: Final[float] = 0.2
dayu/host/tooling.py:94:        _DEFAULT_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS
dayu/host/tooling.py:96:    kill_grace_seconds: float = _DEFAULT_PROCESS_CAPSULE_KILL_GRACE_SECONDS
tests/host/test_toolruntime_executor.py:1860:    assert "_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS" not in source
tests/host/test_toolruntime_executor.py:1861:    assert "_PROCESS_CAPSULE_KILL_GRACE_SECONDS" not in source
```
The old names (`_PROCESS_CAPSULE_*`) are only referenced in negative test assertions. The renamed constants (`_DEFAULT_PROCESS_CAPSULE_*`) live only as typed dataclass field defaults in `dayu/host/tooling.py`, not consumed directly by `ProcessBackedToolExecutionCapsule`. This matches the plan requirement: "if named default constants remain, they must live with the typed policy default owner rather than as separate magic constants consumed directly by `ProcessBackedToolExecutionCapsule`." ✓

**No duplicated envelope constants in tools**:
```text
$ rg -n "_DOC_PROCESS_|_FINS_PROCESS_|_WEB_PROCESS_" dayu/ tests/ --no-heading
tests/fins/test_fins_storage_provider.py:756:    assert "_FINS_PROCESS_" not in source
tests/tools/test_doc_tools_provider.py:288:    assert "_DOC_PROCESS_" not in source
tests/tools/web/test_web_tools_provider.py:484:    assert "_WEB_PROCESS_" not in source
```
All hits are negative test assertions. No production code references remain. ✓

### Contract Single-Source Verification

**Envelope contract in `dayu.contracts.tool_execution.py`**:
- Constants: `PROCESS_TOOL_ENVELOPE_STATUS_FIELD`, `PROCESS_TOOL_ENVELOPE_COMPLETED_STATUS`, `PROCESS_TOOL_ENVELOPE_FAILED_STATUS`, `PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD`, `PROCESS_TOOL_ENVELOPE_FAILED_ERROR_TYPE_FIELD`, `PROCESS_TOOL_ENVELOPE_FAILED_MESSAGE_FIELD`, `PROCESS_TOOL_ENVELOPE_FAILED_HINT_FIELD`, `PROCESS_TOOL_ENVELOPE_RESERVED_STATUSES` (lines 18-28)
- Constructor helpers: `process_tool_completed_envelope(value)` (line 86), `process_tool_failed_envelope(*, error_type, message, hint=None)` (line 99)
- Parser: `parse_process_tool_envelope(envelope) → ProcessToolEnvelopeParseResult` (line 125)
- All exported from `dayu.contracts.__init__` (lines 60-85, 177-179) ✓

**Tool consumption of contract helpers**:
- `dayu/tools/doc_tools.py`: imports `process_tool_completed_envelope`, `process_tool_failed_envelope` from `dayu.contracts` (lines 35-36) ✓
- `dayu/fins/tools/fins_tools.py`: imports `process_tool_completed_envelope`, `process_tool_failed_envelope` from `dayu.contracts.tool_execution` (lines 25-26); helper `_process_failed_envelope` (line 1309) delegates to `process_tool_failed_envelope` with hint as separate field ✓
- `dayu/tools/web/web_tools.py`: imports `process_tool_completed_envelope`, `process_tool_failed_envelope` from `dayu.contracts.tool_execution` (lines 48-49); helper `_web_process_failed_envelope` (line 1628) delegates to `process_tool_failed_envelope` with hint as separate field ✓

**Host consumption of contract parser**:
- `dayu/host/tool_runtime.py`: imports `parse_process_tool_envelope`, `ProcessToolCompletedEnvelope`, `ProcessToolFailedEnvelope`, `ProcessToolMalformedEnvelope`, `ProcessToolUnsupportedEnvelope` from `dayu.contracts.tool_execution` (lines 40-44) ✓

### Structured Hint Data Path

Complete chain verified from tool subprocess → contract → Host → `ToolResultFailure`:

1. Tool subprocess calls `process_tool_failed_envelope(error_type=..., message=..., hint=...)` → hint written to envelope JSON only when non-None/non-blank (`dayu/contracts/tool_execution.py:120-121`)
2. Host calls `parse_process_tool_envelope(envelope)` → `_parse_process_tool_failed_envelope` extracts hint, validates type, returns only non-empty hint (`dayu/contracts/tool_execution.py:192-200`)
3. Host maps `parsed.hint` → `_tool_failed_outcome(...)` → `ToolResultFailure(hint=hint)` (`dayu/host/tool_runtime.py:6573-6587, 7343-7362`)

The plan requirement "Host no longer requires tools to concatenate hint into message" is satisfied. ✓

### Process Capsule Interrupt Policy Wiring

Complete chain verified from config → ConfigLoader → Service assembly → Host:

1. `dayu/runtime/config_loader.py:477-485`: `ProcessCapsuleInterruptPolicyConfig` typed dataclass with `terminate_grace_seconds`, `kill_grace_seconds`
2. `dayu/runtime/config_loader.py:516`: `HostRuntimeProfileConfig.process_capsule_interrupt_policy: ProcessCapsuleInterruptPolicyConfig | None` — optional field; `None` means use Host typed default
3. `dayu/runtime/config_loader.py:1907-1939`: `_optional_process_capsule_interrupt_policy` parses optional config block, enforces exact fields `{"terminate_grace_seconds", "kill_grace_seconds"}`, validates via `_require_non_negative_finite_float_field`
4. `dayu/service/host_assembly.py:1745-1760`: `_process_capsule_interrupt_policy_from_config` — returns `ProcessCapsuleInterruptPolicy()` (Host typed default) when config is `None`
5. `dayu/service/host_assembly.py:1693-1697, 1737-1741`: mapped into `HostToolingOptions.process_capsule_interrupt_policy`
6. `dayu/host/tooling.py:28-29, 79-113`: `ProcessCapsuleInterruptPolicy` dataclass with `_DEFAULT_PROCESS_CAPSULE_*` as single-source defaults; `__post_init__` validates finite non-negative non-bool via `_require_non_negative_finite_number`
7. `dayu/host/tool_runtime.py:1543, 1581, 1627, 2742, 2764, 4015`: wired through `_declared_capsule_for_execution` → `ProcessBackedToolExecutionCapsule(...)` ✓

Config file `dayu/config/host_runtime.json` does not include `process_capsule_interrupt_policy` — the field is optional, and its absence correctly falls through to `ProcessCapsuleInterruptPolicy()` typed defaults. ✓

### Process Group Cleanup Verification

- `dayu/runtime/interruptible_process.py:502-515`: `enter_new_process_session_if_supported()` calls `os.setsid()` on POSIX, returns `False` on unsupported platforms or `OSError`
- `dayu/runtime/interruptible_process.py:440-499`: `interrupt_multiprocessing_process()` — shared primitive for both `InterruptibleProcessHandle` and raw `multiprocessing.Process` paths
- `dayu/runtime/interruptible_process.py:531-612`: `_resolve_safe_child_process_group()` — validates child pgid differs from current and parent pgid before allowing group signal
- `dayu/tools/web/web_playwright_backend.py`: Playwright cleanup now uses `interrupt_multiprocessing_process` from `dayu.runtime.interruptible_process` (import at line 29) ✓
- S2B synthetic nested-child test: `test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix` asserts `reason=group_signaled` and `group_signal_sent=True` ✓
- S2B live browser smoke: `test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort` behind `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1` ✓

### AAPL XBRL Fixture Verification

- Fixture directory: `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/`
- Files: `aapl-20240928.htm`, `aapl-20240928.xsd`, `aapl-20240928_cal.xml`, `aapl-20240928_def.xml`, `aapl-20240928_htm.xml`, `aapl-20240928_lab.xml`, `aapl-20240928_pre.xml`, `meta.json` ✓
- Process-backed Fins XBRL test exists in `tests/fins/test_fins_storage_provider.py` ✓

### README/Docs Consistency

- `dayu/config/README.md:147`: documents optional `process_capsule_interrupt_policy` with field descriptions, validation rules, and distinction from `tool_execution_timeout_seconds` ✓
- `dayu/host/README.md:92`: documents `process_capsule_interrupt_policy` as part of `HostToolingOptions` ✓
- `dayu/README.md`:新增 contracts summary 描述 process-backed envelope helpers ✓
- `dayu/fins/README.md`: documents structured hint behavior (S4 fix) ✓
- `docs/host/issues-implementation-control.md:158`: gate value `accepted-slice`, next entry point "Aggregate / final review" ✓
- All README/control docs do not overclaim final-closeout or PR readiness ✓

## Findings

### 01-未修复-低-`_web_process_failed_envelope` 在调用 contract helper 前静默清理空输入

- **入口/函数**: `_web_process_failed_envelope` → `process_tool_failed_envelope`
- **文件(行号)**: `dayu/tools/web/web_tools.py:1628-1652`
- **输入场景**: 调用方传入空白或仅含空格的 `error_type` 或 `message`
- **实际分支**: `error_type.strip() or "execution_error"` / `message.strip() or "Tool execution failed."` 在到达 contract helper 校验前提供 fallback
- **预期行为**: contract helper `process_tool_failed_envelope` 要求 `error_type` 和 `message` 非空，空值会触发 `ValueError`。调用方应确保传入有效值。`_web_process_failed_envelope` 的 fallback 逻辑使非法输入被静默纠正为通用错误码
- **实际行为**: 空白 `error_type` 变为 `"execution_error"`，空白 `message` 变为 `"Tool execution failed."`，不会触发 contract helper 的 `ValueError`
- **直接证据**: `web_tools.py:1648-1651` 的 `.strip() or ...` fallback 逻辑 + `tool_execution.py:111-113` 的 `ValueError` 校验
- **影响**: 低。不会产生错误结果，但会掩盖上游调用方的参数校验缺失。如果 `ToolBusinessError.code` 意外为空，调用方不会收到反馈
- **建议改法和验证点**: 可考虑在 `_web_process_failed_envelope` 中先 assert/校验 `error_type` 和 `message` 非空（fail fast），仅对 truly unknown 异常路径使用 fallback；或者在此处记录 warning 日志
- **修复风险（低）**: 纯防御性修改，不影响正确行为
- **严重程度（低）**: 不影响 correctness，属于 defensive coding 风格差异

### 02-未修复-低-`ProcessCapsuleInterruptPolicy._require_non_negative_finite_number` 的类型检查接受 `int`

- **入口/函数**: `_require_non_negative_finite_number`
- **文件(行号)**: `dayu/host/tooling.py:130`
- **输入场景**: `ProcessCapsuleInterruptPolicy(terminate_grace_seconds=2)` — 传入 Python `int`
- **实际分支**: `isinstance(value, int | float)` 接受 `int`，后续存储到 `float` 类型字段
- **预期行为**: 字段注解为 `float`，校验函数应至少检查类型一致性，或显式接受 `int` 并在 docstring 中说明
- **实际行为**: `int` 被接受，Python 隐式转换到 `float` 存储。行为正确但类型精度与注释不完全一致
- **直接证据**: `tooling.py:93` 注解 `terminate_grace_seconds: float` + `tooling.py:130` 检查 `isinstance(value, int | float)`
- **影响**: 极低。Python `int` → `float` 隐式转换在正常范围内（0, 1, 2 等）无精度损失。仅影响类型严格性
- **建议改法和验证点**: 将 `int | float` 改为仅 `float`，或保留现状并在 docstring 中说明 `int` 会被接受并转换
- **修复风险（低）**: 若改为仅 `float`，现有通过 `int` 传参的调用方需要在调用侧显式转换
- **严重程度（低）**: 类型注解精度，非行为缺陷

### 03-未修复-低-Doc generic exception 路径不发出结构化 hint

- **入口/函数**: Doc process target `__call__` 的 generic `except Exception` 分支
- **文件(行号)**: `dayu/tools/doc_tools.py` (generic exception handler)
- **输入场景**: Doc 子进程发生未预期异常
- **实际分支**: generic `except Exception` 调用 `process_tool_failed_envelope` 时不传 `hint`
- **预期行为**: `hint` 是可选字段，contract 允许缺省
- **实际行为**: generic exception 路径不发出 hint，LLM 没有结构化恢复提示
- **直接证据**: S3 controller adjudication (`wu-tools-cancel-01-residual-hardening-s3-controller-adjudication.md:25-28`) 已裁决 DS-01 为 rejected: "Doc generic exception path has no concrete business recovery action; adding a vague LLM-facing hint would add noise rather than improve correctness."
- **影响**: 无。已在 S3 控制器裁决中 rejected-with-reason。此处仅为 aggregate 记录
- **建议改法和验证点**: 无需修改
- **修复风险（低）**: N/A
- **严重程度（低）**: 已裁决 rejected，不阻塞

## Aggregate Review Questions — Answers

### 1. Do the five user-mandated residuals close in code/docs/tests?

**YES.** All five residuals are closed:

| Residual | Status | Evidence |
|---|---|---|
| process envelope hint structured | CLOSED | `hint` field in `dayu/contracts/tool_execution.py`, parsed by Host into `ToolResultFailure.hint`, emitted by all three tool packages as separate field |
| Playwright cleanup smoke | CLOSED | S2B added synthetic nested-child cleanup test (`group_signaled`), live browser smoke (manual, `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`), and Playwright uses shared `interrupt_multiprocessing_process` primitive |
| Fins XBRL fixture breadth | CLOSED | S3 added AAPL 10-K XBRL fixture (`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/`) and process-backed `query_xbrl_facts` test |
| process envelope constants single-source | CLOSED | All `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, `_WEB_PROCESS_*` constants removed; tools use `dayu.contracts` helpers exclusively; grep assertions confirm |
| process capsule grace tuning | CLOSED | `ProcessCapsuleInterruptPolicy` typed dataclass with defaults single-source; wired config_loader → host_assembly → HostToolingOptions → ToolRuntime; old magic constants removed from active code path |

### 2. Does Host remain decoupled from concrete tools while giving a normative contract through dayu.contracts?

**YES.** Host imports envelope contract types (`parse_process_tool_envelope`, `ProcessToolCompletedEnvelope`, `ProcessToolFailedEnvelope`, etc.) from `dayu.contracts.tool_execution`. Host has zero imports from `dayu.tools`, `dayu.fins`, or concrete Doc/Web/Fins modules. The process-backed envelope contract in `dayu.contracts` is the single normative contract consumed by both Host (parser) and tools (constructors).

### 3. Does dayu.runtime stay layer-neutral and avoid Host/Engine/Service/UI/Fins imports?

**YES.** `rg -n "from dayu\.(host|engine|service|ui|fins)" dayu/runtime/ --no-heading` returns zero results. `dayu.runtime` imports only from `dayu.contracts` and standard library. Process-group cleanup primitives (`enter_new_process_session_if_supported`, `interrupt_multiprocessing_process`) are generic and callable by both `InterruptibleProcessHandle` and Playwright's raw `multiprocessing.Process` path without encoding Web or Playwright names.

### 4. Does cancellation robustness claim remain honest?

**YES**, with one honest residual:

- **Immediate Host interactivity/stale-result isolation**: Process-backed tool execution with bounded cleanup ensures Host can terminate subprocesses and return to interactive state without waiting for tool completion. Stale results from cancelled processes are isolated by the process capsule boundary.
- **Process-backed cleanup**: Shared `interrupt_multiprocessing_process` primitive with POSIX process-group cleanup validates child pgid safety before group signaling. Synthetic nested-child cleanup is proven; live Chromium cleanup is environment-dependent (manual smoke only).
- **No extension of `tool_execution_timeout_seconds`**: `ProcessCapsuleInterruptPolicy` is documented as cleanup-only, not a business deadline. The typed policy defaults (0.2s/0.2s) are cleanup grace values after cancel/timeout, not tool execution deadlines.
- **Web cold-start remains performance-only**: No S2B evidence showed it weakens cancellation robustness. This is an honest residual.

### 5. Are README/control docs consistent and not overclaiming final-closeout / PR readiness?

**YES.** All READMEs accurately describe implemented behavior:
- `dayu/config/README.md:147`: documents optional `process_capsule_interrupt_policy`
- `dayu/host/README.md:92`: documents `process_capsule_interrupt_policy` as part of `HostToolingOptions`
- `dayu/README.md`:新增 contracts summary for process-backed envelope helpers
- `dayu/fins/README.md`: documents structured hint behavior
- `docs/host/issues-implementation-control.md`: gate=`accepted-slice`, next entry point="Aggregate / final review", PR #170 explicitly "不得 mark ready 或 merge"

No document claims final-closeout or PR readiness.

### 6. Are validation matrices and skipped/manual smoke classifications adequate?

**YES.** The full validation matrix passes:
- Host ToolRuntime/tooling/public options: 89 passed
- Runtime interruptible process: 19 passed
- Web provider: 34 passed, 1 skipped (live browser smoke)
- Fins provider: 33 passed
- Service host assembly: 52 passed
- pyright: 0 errors, 0 warnings, 0 informations

The one skipped test (`test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort`) is correctly classified as optional/manual behind `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`. The skip reason (environment-dependent Chromium binary availability) is honest and documented in the S2B controller adjudication.

## Open Questions

无。

## Residual Risk

- **Live Chromium cleanup**: Environment-dependent (OS, Chromium build). S2B provides synthetic nested-child proof and manual live smoke behind env var; always-on CI coverage is not claimed. This is an honest residual recorded in the plan and all S2B/S4 review artifacts.
- **Web process cold-start**: Deferred as performance-only per user/controller decision. No S2B evidence showed cancellation robustness weakening.
- **PID/PGID reuse**: Same POSIX limitation recorded by S2A. S2B does not expand this risk. Process-group cleanup is bounded by safe pgid validation.
- **AAPL XBRL fixture**: Self-contained for current processor path. Future edgartools or XBRL processor changes may require taxonomy file additions.
- **`_web_process_failed_envelope` blank-input sanitization** (Finding 01): masks upstream parameter validation gaps but produces correct output. Low risk.
- **`_require_non_negative_finite_number` type precision** (Finding 02): `int | float` check accepts `int` for `float` field. No behavioral impact. Low risk.

## Conclusion

**PASS**

All five user-mandated residuals are closed with code, tests, and docs evidence. Layer boundaries (runtime neutrality, Host-tool decoupling, contracts single-source) are maintained with zero violations. The full validation matrix passes (227 tests, pyright 0 errors). Three low-severity findings are identified; none are blocking. README/control docs are consistent and do not overclaim. Cancellation robustness claims are honest with one acknowledged residual (live Chromium cleanup environment-dependency).

The branch `phase/wu-tools-cancel-01` is ready for aggregate/final review gate completion.
