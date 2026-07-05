# Aggregate Review — WU-TOOLS-CANCEL-01 Residual Hardening

## Scope

- Mode: current changes (aggregate/final review of reopened gate)
- Branch: `phase/wu-tools-cancel-01`
- Base: `main` (incremental reopen range `6166d0e9..HEAD`)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-review-mimo.md`
- Reviewer: AgentMiMo
- Review date: 2026-07-05T16:56:15

### Commits in scope

| Commit | Description |
|--------|-------------|
| `da047a45` | residual hardening plan |
| `7e856b05` | S1: Process Envelope Contract And Cleanup Policy |
| `d7541272` | S2A: Runtime Process Group Cleanup Primitive |
| `4f9df113` | S2B: Playwright Cleanup Smoke |
| `98cdc872` | S3: Tool Migration And Fins AAPL XBRL Fixture Breadth |
| `aa10ab0f` | S4: Docs, Control State, And Final Validation |

### Key implementation files reviewed

| File | Lines | Role |
|------|-------|------|
| `dayu/contracts/tool_execution.py` | ~363 | Process envelope contract, `ProcessCapsuleInterruptPolicy` not here (correct) |
| `dayu/contracts/__init__.py` | ~182 | Package exports, 65 symbols |
| `dayu/runtime/interruptible_process.py` | ~798 | Process-group cleanup primitives |
| `dayu/runtime/config_loader.py` | ~2560 | `ProcessCapsuleInterruptPolicyConfig` parsing |
| `dayu/host/tooling.py` | ~203 | `ProcessCapsuleInterruptPolicy` dataclass, `HostToolingOptions` |
| `dayu/host/tool_runtime.py` | ~7400 | `ProcessBackedToolExecutionCapsule`, envelope parsing |
| `dayu/host/dispatch.py` | ~3400 | Policy extraction from `HostToolingOptions` |
| `dayu/service/host_assembly.py` | ~1760 | Config-to-Host assembly wiring |
| `dayu/tools/doc_tools.py` | ~1213 | Doc tool migration |
| `dayu/tools/web/web_tools.py` | ~1900 | Web tool migration |
| `dayu/tools/web/web_playwright_backend.py` | ~583 | Playwright cleanup using shared primitives |
| `dayu/fins/tools/fins_tools.py` | ~1400 | Fins tool migration |

### Test files reviewed

| File | Key coverage |
|------|-------------|
| `tests/runtime/test_interruptible_process.py` | Process-group cleanup, all fallback paths, grace validation |
| `tests/runtime/test_config_loader.py` | Policy config parsing, invalid values |
| `tests/host/test_toolruntime_executor.py` | Capsule wiring, cancel escalation |
| `tests/host/test_tooling_options.py` | Policy dataclass validation |
| `tests/tools/web/test_web_tools_provider.py` | Playwright cleanup smoke (synthetic + optional live) |
| `tests/fins/test_fins_storage_provider.py` | AAPL XBRL fixture through capsule |
| `tests/contracts/test_package_exports.py` | Contracts symbol whitelist |

### Parallel review coverage

Subagents covered: contracts layer, host tool_runtime, runtime interruptible_process, config/assembly wiring, tool migration files, all test files, README/control doc overclaiming, Host/Runtime import boundary checks. Uncovered: none (full scope reviewed).

---

## Aggregate Review Questions

### Q1: Do the five user-mandated residuals close?

| Residual | Status | Evidence |
|----------|--------|----------|
| Process envelope hint structured | **Closed** | `ProcessToolFailedEnvelope.hint: str \| None` in contracts; all three tools pass `hint` as separate field via `process_tool_failed_envelope(..., hint=...)`; Host maps `parsed.hint` → `ToolResultFailure.hint` at `tool_runtime.py:6586` |
| Playwright cleanup smoke | **Closed** | Synthetic nested-child smoke at `test_web_tools_provider.py:1582` proves `GROUP_SIGNALED`; running-event-loop variant at line 1651; live Chromium smoke at line 1694 is opt-in (`DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`) |
| Fins XBRL fixture breadth | **Closed** | AAPL 2024 10-K XBRL fixture under `tests/fins/fixtures/aapl_xbrl/`; `query_xbrl_facts` runs through `ProcessBackedToolExecutionCapsule` at `test_fins_storage_provider.py:903`; asserts `NetIncomeLoss` concept |
| Process envelope constants single-source | **Closed** | All `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, `_WEB_PROCESS_*` constants removed; `grep` returns zero matches; tools import from `dayu.contracts.tool_execution` |
| Process capsule grace tuning | **Closed** | `ProcessCapsuleInterruptPolicy` dataclass in `tooling.py:79-113`; defaults in module constants (lines 28-29); config layer returns `None` when absent; assembly delegates to dataclass constructor; validation rejects bool/negative/NaN/infinity |

### Q2: Host decoupled from concrete tools?

**Yes.** `grep` for `from dayu.tools` and `from dayu.fins` in `dayu/host/*.py` returns zero matches. Host gives normative contract through `dayu.contracts` envelope types; tools construct envelopes, Host parses them.

### Q3: dayu.runtime stays layer-neutral?

**Yes.** `dayu/runtime/interruptible_process.py` imports only `dayu.contracts.json_value.JsonValue`. Zero imports from `dayu.host`, `dayu.engine`, `dayu.service`, `dayu.ui`, `dayu.fins`. `dayu/runtime/config_loader.py` imports from `dayu.runtime.*` sibling modules and `dayu.contracts.*` only.

### Q4: Cancellation robustness claim honest?

**Yes.** Verified:
- Host interactivity isolation is immediate (cancel → terminal closeout for pre-dispatch states, `RUN_CANCELLING` + WorkerProxy for active Attempts).
- Process-backed cleanup uses `terminate()` → grace → `kill()` → grace → `close()` chain.
- `tool_execution_timeout_seconds` (from `AgentPolicy`) is the only business deadline; cleanup grace values bound post-cancel cleanup only and never extend it.
- Web cold-start remains performance-only residual (documented in plan).

### Q5: README/control docs consistent?

**Yes.** Reviewed all six modified READMEs (`dayu/`, `dayu/host/`, `dayu/engine/`, `dayu/fins/`, `dayu/config/`, `tests/`). No overclaiming found. Control doc `issues-implementation-control.md` correctly tracks S1-S4 as completed with aggregate review as next gate. PR #170 correctly remains draft.

### Q6: Validation matrices and skipped/manual smoke adequate?

**Adequate with minor gaps.** Full validation matrix covers: all affected test suites, pyright, `git diff --check`. Skipped classifications are honest (live Chromium smoke is opt-in). See findings below for remaining test gaps.

---

## Findings

### 001-未修复-低-Config process_capsule_interrupt_policy 未知字段无专项测试

- **入口/函数**: `dayu/runtime/config_loader.py:_optional_process_capsule_interrupt_policy`
- **文件(行号)**: `tests/runtime/test_config_loader.py` — 无 `process_capsule_interrupt_policy` 块内未知字段的测试
- **输入场景**: `host_runtime.json` 的 `process_capsule_interrupt_policy` 块中包含拼写错误的字段（如 `terminate_grace_second`）或额外未知字段
- **实际分支**: `_require_exact_fields` (line 1923) 会拒绝未知字段，抛出 `ConfigFieldError`
- **预期行为**: 未知字段应被拒绝，配置加载失败
- **实际行为**: 代码逻辑正确（`_require_exact_fields` 调用已存在），但无测试覆盖此路径
- **直接证据**: `config_loader.py:1923-1926` 调用 `_require_exact_fields(policy, allowed=frozenset({"terminate_grace_seconds", "kill_grace_seconds"}), ...)`；`tests/runtime/test_config_loader.py` 的 `test_host_runtime_process_capsule_policy_invalid_grace_fails_fast` (line 517) 只测非法值，不测未知字段
- **影响**: 如果 `_require_exact_fields` 调用被意外移除或修改，未知字段将静默通过，配置可能被误用
- **建议改法和验证点**: 在 `test_config_loader.py` 中增加一个测试，传入 `{"terminate_grace_seconds": 0.2, "kill_grace_seconds": 0.2, "unknown_field": 1}`，断言 `ConfigFieldError` 且消息包含 `"unknown fields"`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-Factory wiring path 无端到端测试

- **入口/函数**: `dayu/host/tool_runtime.py:DeclaredToolExecutionCapsuleFactory.create_capsule` → `_declared_capsule_for_execution`
- **文件(行号)**: `tests/host/test_toolruntime_executor.py:1785`
- **输入场景**: 通过 `HostToolingOptions(process_capsule_interrupt_policy=custom)` → `DefaultToolRuntimeFactory.create_tool_runtime` → `DeclaredToolExecutionCapsuleFactory` → `ProcessBackedToolExecutionCapsule` 的完整 wiring 路径
- **实际分支**: 测试 `test_process_backed_capsule_close_uses_interrupt_policy_kill_grace` (line 1785) 直接构造 `ProcessBackedToolExecutionCapsule(target, interrupt_policy=custom_policy)`，绕过了 `DefaultToolRuntimeFactory` → `DeclaredToolExecutionCapsuleFactory` 的 wiring 路径
- **预期行为**: 应有测试从 `HostToolingOptions` 开始，经过 factory 路径，验证 policy 值到达 capsule
- **实际行为**: capsule 级别测试存在（直接构造），但 factory wiring 路径未被端到端覆盖
- **直接证据**: `test_toolruntime_executor.py:1785` 直接调用 `ProcessBackedToolExecutionCapsule(recording_handle, interrupt_policy=ProcessCapsuleInterruptPolicy(kill_grace_seconds=0.73))`；`tool_runtime.py:4010-4016` 的 `DeclaredToolRuntimeFactory` 创建路径未被测试覆盖
- **影响**: 如果 `dispatch.py` 或 `tool_runtime.py` 中的 wiring 链断裂（如 policy 未传递到 factory），不会被现有测试捕获
- **建议改法和验证点**: 增加测试：构造 `HostToolingOptions(process_capsule_interrupt_policy=custom)` → 通过 `DefaultToolRuntimeFactory` 创建 `ToolRuntime` → 对 process-backed capsule 执行 close → 断言 handle 收到的 `close_kill_grace_seconds` 匹配自定义值
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-Fins 通用异常 catch 的 hint 与 Doc/Web 不一致

- **入口/函数**: `_FinsReadProcessTarget.__call__` vs `_DocProcessTarget.__call__` vs `_WebProcessTarget.__call__`
- **文件(行号)**: `dayu/fins/tools/fins_tools.py:281-285`, `dayu/tools/doc_tools.py:381-384`, `dayu/tools/web/web_tools.py:512-515`
- **输入场景**: 子进程内发生未预期的通用 `Exception`
- **实际分支**: `fins_tools.py` 的 `except Exception` 分支传递 `hint=_UNEXPECTED_FAILURE_HINT`；`doc_tools.py` 和 `web_tools.py` 的等价分支不传递 `hint`
- **预期行为**: 三个 tool 的通用异常 catch 应使用一致的 hint 策略
- **实际行为**: `fins_tools.py:281-285` 有 `hint=_UNEXPECTED_FAILURE_HINT`；`doc_tools.py:381-384` 和 `web_tools.py:512-515` 无 `hint`
- **直接证据**: `fins_tools.py:284` (`hint=_UNEXPECTED_FAILURE_HINT`) vs `doc_tools.py:381-384` (无 hint 参数) vs `web_tools.py:512-515` (无 hint 参数)
- **影响**: 风格不一致，非功能性 bug。`hint` 是可选字段，缺失时 Host 正确收到 `None`
- **建议改法和验证点**: 统一三个 tool 的通用异常 catch 的 hint 策略：要么都提供 hint（如 `"Unexpected error during child process execution."`），要么都不提供。建议都提供以保持一致
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## Open Questions

- 无。

## Residual Risk

1. **Live Chromium process-tree cleanup**: 确定性合成嵌套子进程 smoke 只证明合成场景。真实 Chromium 清理依赖环境，通过 `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1` 可选手动 smoke 验证。已在 plan 中正确分类为 residual。
2. **Web cold-start 性能**: 作为 performance-only residual 正确保留，不削弱取消健壮性声明。
3. **Windows 平台**: 进程组清理在 Windows 上静默降级为直接子进程清理（`_PROCESS_GROUP_CLEANUP_SUPPORTED = os.name == "posix"`）。已在 plan 中正确标记为 unsupported/fallback。
4. **AAPL XBRL fixture 离线可用性**: fixture 已添加到 `tests/fins/fixtures/aapl_xbrl/`，`query_xbrl_facts` 测试通过（`test_fins_storage_provider.py:903`），确认离线可用。

---

## Conclusion

**PASS_WITH_FINDINGS**

五个用户指定的 residual 均已在代码/文档/测试中正确关闭。Host 与具体工具解耦、dayu.runtime 层中立、取消健壮性声明诚实、README/control doc 一致且未过度声明。进程信封契约单一来源、清理策略 typed dataclass、进程组清理共享原语、Playwright 清理 smoke、Fins XBRL fixture 均按设计落地。

三个 findings 均为低严重程度：config 未知字段缺少专项测试、factory wiring 路径缺少端到端测试、三个 tool 通用异常 catch 的 hint 策略不一致。无 correctness 或 stability 缺陷。
