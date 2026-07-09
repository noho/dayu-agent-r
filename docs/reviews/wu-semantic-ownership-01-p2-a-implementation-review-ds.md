# WU-SEMANTIC-OWNERSHIP-01 P2-A Implementation Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-A`
- Gate: implementation review (post AgentCodex implementation, post controller validation)
- Accepted plan commit: `38477f63`
- Review type: adversarial code review（不改代码）

## Verdict

**pass-with-findings** — 所有 findings 均为 Low 或 Informational 级别，不阻塞合并。P2-A 已按 accepted plan 完成 S1/S2/S3 三个 slice，owner boundary 正确，DS 03/DS 10/DS 11 已关闭。

---

## Findings

### F1 [Low] `session.py` 对 prompt/interactive command 异常类的跨模块依赖

**Evidence:**
- `dayu/cli/commands/session.py:150` 捕获 `(CliCommandUsageError, CliInteractiveUsageError)`，这两个异常类型分别定义在 `dayu/cli/commands/prompt.py:64` 和 `dayu/cli/commands/interactive.py:56`。
- `dayu/cli/commands/session.py:40-43` 从 prompt/interactive command 模块 import 这些异常。

```python
except (CliCommandUsageError, CliInteractiveUsageError) as exc:
    render_cli_error(f"dayu-cli session resume: {exc}")
    return EXIT_USAGE_ERROR
```

**影响：** `session.py` 在 `run_session_command` 顶层异常处理中依赖 prompt/interactive command 模块定义的异常类型。虽然这些是 `__all__` 中导出的 public symbol（符合 plan 允许的 public import），但语义上 `CliCommandUsageError` 与 `CliInteractiveUsageError` 是 prompt/interactive command 的 usage error owner，不是 CLI 公共层的通用 usage error。未来 prompt/interactive 各自演进其 usage error 类型时，session command 的异常处理可能需要同步更新。

**Owner boundary:** Usage error 类型的语义 owner 是各自 command module；但被 session command 跨模块消费时，session command 无法不感知 prompt/interactive 的内部异常层次。

**建议修复位置:** 可在 CLI 公共层（如 `dayu/cli/exit_codes.py` 或新的 `dayu/cli/errors.py`）定义一个 CLI 公共 `CliUsageError` 基类，`CliCommandUsageError` 和 `CliInteractiveUsageError` 继承它；`session.py` 只捕获公共基类。这属于后续 cleanup，不阻塞当前 P2-A。

**Controller note:** 当前实现被 controller validation 接受；此 finding 仅标记为 residual risk，分配给后续 work unit。

---

### F2 [Low] `_cancelled_result_summary()` 在 CLI 层构造 `FinsResultSummary`

**Evidence:**
- `dayu/cli/commands/fins.py:897-911` 的 `_cancelled_result_summary()` 构造完整 `FinsResultSummary(status=CANCELLED, ...)`，包含 `error_kind=FinsErrorKind.CANCELLED` 与 `error_message="cancelled"` 等业务字段。
- Plan S2 原文："不在 CLI 构造 `FinsEvent` / `FinsResultSummary` fallback；不调用 renderer 投影一个业务 failure result。"

```python
def _cancelled_result_summary() -> FinsResultSummary:
    return FinsResultSummary(
        status=FinsResultStatus.CANCELLED,
        exit_code=FINS_RESULT_EXIT_CANCELLED,
        title="Fins direct operation cancelled",
        details=(FinsEventDetail(label="reason", value="keyboard_interrupt"),),
        error_kind=FinsErrorKind.CANCELLED,
        error_message="cancelled",
    )
```

**影响：** 与 plan S2 文字存在张力。但该函数用于 SIGINT 用户主动取消路径（`_wait_for_terminal_handling_sigint:696`），不是 S2 目标场景"Service stream 正常结束但缺少 RESULT"的 fallback。取消场景下 CLI 需要返回一个 exit code，当前通过 `FinsResultSummary.exit_code` 提取。Controller validation 已确认此状态可接受。

**Owner boundary:** 用户取消的终端状态投影仍由 CLI 拥有；但构造完整业务 DTO 只是为了取 `exit_code` 字段，存在过度构造。

**建议修复位置:** 可改为直接返回 `int` exit code，避免构造 `FinsResultSummary`；或定义一个轻量 CLI 本地 `_CancelledExit` 类型。不阻塞当前 P2-A，可在后续 cleanup 中处理。

---

### F3 [Info] 测试直接调用 `session_execution` 模块级私有 helper

**Evidence:**
- `tests/cli/test_prompt_command.py` 调用 `session_execution._submit_prompt_turn_handling_sigint`、`session_execution._cancel_prompt_turn_after_local_request`、`session_execution._PromptAcceptedRunState`、`session_execution._cancel_prompt_run_waiting_for_terminal_or_second_sigint`。
- `tests/cli/test_interactive_command.py` 调用 `session_execution._submit_interactive_turn_handling_sigint`、`session_execution._cancel_interactive_turn_after_first_sigint`、`session_execution._wait_for_run_id_or_local_exit`、`session_execution._run_interactive_repl`、`session_execution._InteractiveAcceptedRunState`、`session_execution._LocalExitRequested`、`session_execution._SubmitCompletedWhileWaitingForRunId`。

**判断：** 这些测试访问的是 `dayu.cli.session_execution` 模块内部的下划线私有符号，但 `session_execution` 本身就是这些语义的 owner module。这与 P2-A 修改前的反模式（`session.py` 跨模块导入 `prompt.py` / `interactive.py` 的私有符号）有本质区别：现在测试与实现在同一 owner module 内。Controller validation 明确判定为 "acceptable as same-owner implementation tests"。

**Residual risk:** 若未来 `session_execution` 内部状态机签名重构，这些测试需要同步更新；但这属于同一 owner 内的正常重构成本，不是跨模块边界漂移。

---

## Accepted Plan Compliance

### S1: CLI Existing-session Execution Public Helper ✅

| 检查项 | 状态 | 证据 |
|---|---|---|
| `session.py` 不再从 prompt/interactive 导入下划线私有符号 | ✅ | AST test `test_import_boundary.py` 验证通过；`session.py:36-43` 只导入 public `CliCommandUsageError`、`build_prompt_context_slot_values`、`CliInteractiveUsageError`、`build_interactive_context_slot_values` |
| 新 helper 是真实 semantic owner，不是 facade | ✅ | `session_execution.py` 直接 import `dayu.service.entrypoint_runtime`，拥有自己的 typed dataclass（`PreparedPromptSessionExecution`、`PreparedInteractiveSessionExecution`）和完整 submit/watch/cancel 编排 |
| prompt/interactive command 内部也调用新 public helper | ✅ | `prompt.py:104-115` 调用 `prepare_prompt_session_execution` + `execute_prompt_on_session`；`interactive.py:107-131` 同理 |
| 旧 `_prepare_*` / `_execute_*` 私有函数已删除，无同名转发 | ✅ | `prompt.py` 和 `interactive.py` 中已无旧私有 helper；`rg "_prepare_.*existing|_execute_.*on_existing" dayu/cli/commands/prompt.py dayu/cli/commands/interactive.py` 无命中 |
| context slot 构造仍由 command module 拥有 | ✅ | `prompt.py:193-214` 保留 `build_prompt_context_slot_values`；`interactive.py:195-202` 保留 `build_interactive_context_slot_values`；`session_execution` 的 prepare API 接受 `context_slot_values: dict[str, JsonValue]`，不按 scenario 分发 slot 规则 |
| `RuntimeDisplayController` 职责未被 shared helper 接管 | ✅ | `session_execution` 创建 `RuntimeDisplayController` 实例并调用其方法，但不替代其 thinking guard、final-before-terminal cleanup、display lifecycle close 语义 |
| `session.py` selector resolution 保留在 session command | ✅ | `_resolve_existing_session_target`（line 367-425）和 `_resolve_purge_target`（line 428-471）仍由 session.py 拥有；`session_execution` 只接受已解析的 `session_id` |

### S2: Fins Direct RESULT Contract Assertion ✅

| 检查项 | 状态 | 证据 |
|---|---|---|
| CLI `_missing_result_event()` 已删除 | ✅ | `fins.py` 中不再包含 `_missing_result_event` 函数定义 |
| CLI 不再构造业务 failure RESULT | ✅ | `_consume_fins_direct_events`（line 727-729）在 stream 结束无 RESULT 时抛出 `FinsDirectStreamContractViolation` |
| `FinsDirectStreamContractViolation` 是 CLI 私有类型 | ✅ | `fins.py:97-98` 定义为 `class FinsDirectStreamContractViolation(RuntimeError)`，不承载 Fins 业务语义 |
| 测试迁移到 contract violation 断言 | ✅ | `test_stream_without_result_returns_contract_violation`（test_fins_commands.py:879-901）断言 stderr 包含 "Fins direct Service stream ended without RESULT"，不包含 "Fins failure" |
| Service 仍是 normal missing-result fallback 真源 | ✅ | `dayu/service/fins_direct.py` 未修改；Service test `test_stream_without_result_closes_as_failure_result` 保留 |

**注：** `FinsErrorKind`、`FinsResultStatus`、`FinsResultSummary` 等 import 在 `fins.py` 中保留，用于诊断日志（`_fins_event_verbose_diagnostic_parts`、`_fins_event_debug_diagnostic_parts`）与 `_cancelled_result_summary`（取消路径）。这些用途不涉及 S2 目标场景（Service 正常结束缺 RESULT），符合 plan 中"只为本地 missing-result event 服务的 import 才删除"的约束。

### S3: Unified CLI HostApiError Presentation ✅

| 检查项 | 状态 | 证据 |
|---|---|---|
| 统一 helper 模块存在 | ✅ | `dayu/cli/host_api_errors.py` 定义 `CliHostApiErrorTarget`、`format_host_api_error`、`host_api_error_context`、`exit_code_for_host_api_error` |
| `session.py` 删除私有重复 helper | ✅ | `_HOST_ERROR_TEMPLATE`、`_host_error_context`、`_exit_code_for_host_error` 已从 `session.py` 移除；改用 `host_api_errors` public helper |
| `prompt.py` / `interactive.py` 单独捕获 `HostApiError` | ✅ | `prompt.py:86-88` 在 `RuntimeLocationError` 之后、generic `Exception` 之前捕获 `HostApiError`；`interactive.py:82-84` 同理 |
| 核心格式统一为 `host_code=... host_message=...` | ✅ | `host_api_errors.py:16` 定义 `_HOST_ERROR_TEMPLATE`；所有错误文本包含 `host_code={code.value} host_message={message}` |
| exit-code policy 符合 accepted plan | ✅ | |
| — 显式 session id NOT_FOUND → `EXIT_USAGE_ERROR` | ✅ | `host_api_errors.py:91-96`：`explicit_session_id_selector=True` 且 `NOT_FOUND` → usage |
| — label TOCTOU NOT_FOUND → `EXIT_FAILURE` | ✅ | `host_api_errors.py:97`：默认 `EXIT_FAILURE`；label TOCTOU 场景 `explicit_session_id_selector=False` |
| — prompt/interactive NOT_FOUND → `EXIT_FAILURE` | ✅ | prompt/interactive 调用 `exit_code_for_host_api_error` 时不传 target，走默认 `EXIT_FAILURE` |
| `_purge_host_error_message` / `_resume_host_error_message` 调用统一 core formatter | ✅ | 两者都调用 `host_api_error_context(error)` 生成 `host_code=... host_message=...` 核心文本 |
| HostApiError pure function 单元测试 | ✅ | `test_host_api_error_policy_maps_explicit_selector_not_found_to_usage`、`test_host_api_error_policy_maps_label_toctou_not_found_to_failure`、`test_host_api_error_policy_maps_prompt_interactive_not_found_to_failure`、`test_host_api_error_formatter_keeps_core_code_and_message` |
| prompt/interactive HostApiError 集成测试 | ✅ | `test_prompt_host_api_error_uses_structured_presentation`、`test_interactive_host_api_error_uses_structured_presentation` |

---

## Propagation Audit

### Session execution path

```
prompt / interactive / session resume
  → command-local: args validation + context slot construction
    (prompt.py: build_prompt_context_slot_values; interactive.py: build_interactive_context_slot_values)
  → dayu.cli.session_execution: prepare_prompt_session_execution / prepare_interactive_session_execution
  → dayu.cli.session_execution: execute_prompt_on_session / execute_interactive_on_session
    (内部: RuntimeDisplayController + Service submit/watch/cancel helpers)
  → dayu.service.entrypoint_runtime: submit_entrypoint_turn_and_wait / startup_reconnect_entrypoint_session / cancel_entrypoint_run_and_wait
  → Host public API
  → CLI terminal renderer / cursor store
```

**审计结果：** ✅ 确认 `session.py` 不再从 prompt/interactive 导入下划线私有符号。AST test 固化边界。`session_execution` 直接依赖 `dayu.service.entrypoint_runtime`，不依赖 prompt/interactive command module 的实现细节。

### Fins direct RESULT path

```
Fins runtime producer
  → FinsDirectCommandService._ensure_result_event (Service owner: normal missing-result fallback)
  → CLI _consume_fins_direct_events
  → render_fins_direct_event (正常 RESULT) 或 FinsDirectStreamContractViolation (contract 被破坏)
  → run_fins_direct_command: generic Exception → stderr + EXIT_FAILURE
```

**审计结果：** ✅ 缺 RESULT 的业务 fallback 只在 Service 真源出现；CLI 不再构造业务 failure RESULT。CLI 只拥有 contract violation 的 hard assertion。

### HostApiError path

```
Host public API raises HostApiError
  → prompt.py / interactive.py / session.py catch HostApiError
  → dayu.cli.host_api_errors.format_host_api_error / exit_code_for_host_api_error
  → stderr + process exit code
```

**审计结果：** ✅ command modules 不再各自重建 HostApiError core format / exit-code mapping。`host_api_errors.py` 是唯一的 `host_code=... host_message=...` 核心格式 owner 和 exit-code policy owner。

### Durable / trace / memory / audit / LLM-facing

**审计结果：** ✅ P2-A 未修改 Host durable EventLog、trace、memory、audit、prompt/schema 或 LLM-facing material。变更仅限 CLI 层 presentation、execution composition 和 contract assertion。

---

## Test Coverage Assessment

| 测试范围 | 文件 | 评估 |
|---|---|---|
| Import boundary (AST) | `tests/cli/test_import_boundary.py` | ✅ 1 test，覆盖 `session.py` 不从 prompt/interactive import 下划线私有符号 |
| HostApiError pure functions | `tests/cli/test_session_command.py` (4 tests) | ✅ 覆盖 NOT_FOUND explicit selector → usage、label TOCTOU → failure、prompt/interactive → failure、core format |
| prompt HostApiError integration | `tests/cli/test_prompt_command.py` | ✅ `test_prompt_host_api_error_uses_structured_presentation` 覆盖 `NOT_FOUND` in create phase |
| interactive HostApiError integration | `tests/cli/test_interactive_command.py` | ✅ `test_interactive_host_api_error_uses_structured_presentation` 覆盖 `NOT_FOUND` in create phase |
| prompt existing-session execution | `tests/cli/test_prompt_command.py` | ✅ `test_prompt_existing_session_execution_does_not_create_or_ensure` 验证不调用 create/ensure，只 submit |
| interactive existing-session execution | `tests/cli/test_interactive_command.py` | ✅ `test_interactive_existing_session_execution_does_not_create_or_ensure` 验证不调用 create/ensure，正确的 watcher/read_outbox/get_session 调用序列 |
| session resume routing | `tests/cli/test_session_command.py` | ✅ 覆盖 prompt/interactive resume by session id / label，展示参数传递，CLOSED/missing fail fast |
| session purge HostApiError | `tests/cli/test_session_command.py` | ✅ 覆盖 INVALID_STATE 前置条件说明、label TOCTOU 错误上下文 |
| Fins contract violation | `tests/cli/test_fins_commands.py` | ✅ `test_stream_without_result_returns_contract_violation` 断言 contract violation 文本，无业务 failure RESULT |
| Controller 建议的补充测试 | `tests/cli/test_runtime_display.py` 等 | ✅ 156 passed（controller validation 已跑） |
| **未覆盖**：prompt/interactive 在 submit 阶段（非 create 阶段）的 HostApiError 集成测试 | — | 当前测试只在 create 阶段注入 `HostApiError`。submit 阶段的 HostApiError 处理路径未被集成测试覆盖（但被 `session.py` 的 resume TOCTOU 测试间接覆盖了同类路径） |

---

## Controller Validation Notes 回应

Controller validation 提出的五个 review focus：

1. **`session_execution` 是真实 semantic owner，不是 facade** → ✅ 确认。模块直接依赖 `dayu.service.entrypoint_runtime`，拥有自己的 typed dataclass 和完整执行编排，不包裹 prompt/interactive。

2. **测试直接覆盖 `session_execution` 内部下划线状态机 helper 可接受** → ✅ 确认。属于同一 owner 内的 implementation test，不构成跨模块私有 import。参见 F3。

3. **`session resume` context slot 构造保持 command-semantic** → ✅ 确认。`session.py` 在 resume prompt mode 调用 `build_prompt_context_slot_values(ticker=..., fmp_api_key=...)`，在 resume interactive mode 调用 `build_interactive_context_slot_values()`。不经过 `session_execution` 分发 slot 规则。

4. **`HostApiError` exit-code policy 符合 accepted plan** → ✅ 确认。参见 S3 合规表。

5. **Fins direct missing-result 不再从 CLI 投影 fake business failure** → ✅ 确认。参见 S2 合规表。

---

## Residual Risks

| Risk | Severity | Owner | 说明 |
|---|---|---|---|
| `session.py` 跨模块依赖 `CliCommandUsageError` / `CliInteractiveUsageError` | Low | 后续 WU | 参见 F1。当前 public import 合法，但增加了 session command 对 prompt/interactive 异常层次的耦合 |
| `_cancelled_result_summary` 在 CLI 构造 `FinsResultSummary` | Low | 后续 cleanup | 参见 F2。取消路径构造业务 DTO 仅用于提取 exit code，存在过度构造 |
| prompt/interactive submit 阶段 `HostApiError` 缺少集成测试 | Low | 后续 WU | 当前测试只在 create 阶段注入 `HostApiError`；submit 阶段路径未被 prompt/interactive 集成测试直接覆盖（session resume TOCTOU 测试间接覆盖了同类路径） |
| `_resume_host_error_message` 未使用 `format_host_api_error` | Info | 后续 cleanup | `session.py:637-654` 自行构造 "dayu-cli session resume: selector=... session_id=..." 前缀而非调用 `format_host_api_error` 传入 target；虽调用了 `host_api_error_context` 公共 core formatter，但与 `format_host_api_error` 存在轻微重复 |

---

## 验证命令（本 review 未执行，引用已报告结果）

根据 implementation artifact 与 controller validation：

```
source .venv/bin/activate && pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py
# → 128 passed, 3 warnings

source .venv/bin/activate && pytest tests/cli/test_import_boundary.py
# → 1 passed

source .venv/bin/activate && pyright
# → 0 errors, 0 warnings, 0 informations

git diff --check
# → passed
```
