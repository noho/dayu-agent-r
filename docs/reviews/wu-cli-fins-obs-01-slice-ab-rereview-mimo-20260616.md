# WU-CLI-FINS-OBS-01 Slice A/B Re-Review (MiMo)

## 范围

- Work unit：`WU-CLI-FINS-OBS-01`
- Slice：A/B review-fix re-review
- Plan 真源：`docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- Fix artifact：`docs/reviews/wu-cli-fins-obs-01-slice-ab-review-fix-codex.md`
- 原始 review artifacts：
  - `docs/reviews/code-review-20260616-111036-mimo.md`
  - `docs/reviews/code-review-20260616-111112-ds.md`

## 结论

**pass**（含 follow-up post-review changes 核对）

## 验证结果

| 验证项 | 结果 |
|---|---|
| `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q` | 129 passed, 3 warnings |
| `pyright dayu/fins/direct_events.py dayu/service/fins_direct.py dayu/fins/ingestion_runtime.py dayu/cli/commands/fins.py dayu/cli/output.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py ...` | 0 errors, 0 warnings |
| `rg` 旧 durable API 残留 | 生产代码零残留；README 旧描述留给 Slice E |

## 核对项详细结果

### 1. MiMo R1/R2：SIGINT 取消注入后 terminal RESULT 保留

**结论：pass — fix 真实覆盖**

**实现分析** (`dayu/cli/commands/fins.py:681-691`)：

```python
cancellation_token.request_cancel("keyboard_interrupt")
event_task.cancel()
render_fins_direct_cancel_requested()
try:
    terminal_result = await event_task
except asyncio.CancelledError:
    pass
else:
    return terminal_result
render_fins_direct_local_exit_after_cancel()
return _cancelled_result_summary()
```

SIGINT 触发后：
1. 设置 cancellation token。
2. 取消 event task。
3. `await event_task`：若 stream 在被取消前或取消 catch 中产出了 terminal `FinsResultSummary`，task 返回该结果，`else` 分支返回真实终态。
4. 若 task 确实被取消（`CancelledError`），`except` 分支 fall through 到本地 cancelled summary。

**测试分析** (`tests/cli/test_fins_commands.py:800-838`)：

`test_cancel_race_does_not_override_terminal_result` 构造了一个精确的竞态场景：
- stream 产出 progress 后 `await asyncio.Event().wait()` 阻塞。
- SIGINT 注入触发 `event_task.cancel()`。
- stream 的 `except asyncio.CancelledError` 分支产出 `_result_event(status=FinsResultStatus.SUCCESS)`。
- 测试断言 `result.status is FinsResultStatus.SUCCESS`（不是 CANCELLED）。
- 同时断言 `token.is_cancelled()` 为 True（token 确实被设置）。

该测试真实覆盖了"取消注入后 stream 仍返回 terminal RESULT"的竞态，不是仅验证正常取消路径。

### 2. DS-001/DS-002：旧 job 术语清除

**结论：pass — 全部清除**

| 位置 | 旧术语 | 新术语 | 状态 |
|---|---|---|---|
| `dayu/cli/output.py` prefix 常量 | `Fins job summary` / `Fins job progress` / ... | `Fins summary` / `Fins progress` / ... | ✅ |
| `dayu/cli/output.py` cancel 模板 | `Fins job cancel requested: {job_id}` | `Fins operation cancel requested.` | ✅ |
| `dayu/cli/output.py` local exit 模板 | `Fins job cancel already requested; local process exiting: {job_id}` | `Fins operation already cancelling; local process exiting.` | ✅ |
| `dayu/cli/output.py` failed fallback | `Fins job failed: {job_id}` | `Fins operation failed.` | ✅ |
| `dayu/cli/commands/fins.py` 模块 docstring | `SIGINT 到 durable Fins job cancel 的映射` | `SIGINT 到当前 async stream cancellation 的映射` | ✅ |
| `dayu/cli/commands/fins.py` `_FinsSigintMonitor` docstring | `Fins direct job 运行阶段` | `Fins direct operation 运行阶段` | ✅ |
| `dayu/service/fins_direct.py` 模块 docstring | `Fins direct job 的 Service 边界` | `Fins direct command 的 Service 流式边界` | ✅ |

### 3. direct CLI/Service 无旧 durable coupling

**结论：pass — 零耦合**

`rg` 扫描 `dayu/cli`、`dayu/service`、`tests/cli`、`tests/service` 结果：

- `FinsDirectJobHandle`：仅在 `tests/service/test_fins_direct.py:550-553` 作为 **反向断言**（`assert not in dir(...)`）。
- `FinsDirectJobEvent`：同上。
- `FinsDirectTerminalResult`：同上。
- `stream_job_events_until_terminal`：仅在 `tests/service/test_fins_direct.py:556` 反向断言。
- `request_cancel(`：仅在 `dayu/cli/commands/fins.py:127,681` 为 `_CliFinsCancellationToken.request_cancel(reason)`，是新的 operation-scoped 取消方法，不是旧 `service.request_cancel(job_id)`。
- `Fins job summary`：零匹配。
- `direct job`：零匹配（仅 README 中残留，留给 Slice E）。

`dayu/service/README.md` 仍包含旧 durable job 描述，fix artifact 已声明留给 Slice E 集中清理。不影响当前 Slice A/B 代码正确性。

### 4. 新引入的 stdout/stderr、exit code、cancel 输出或类型问题

**结论：pass — 无新问题**

- **stdout/stderr 路由**：SUCCESS → stdout；FAILURE / CANCELLED → stderr。与旧实现一致。
- **exit code 映射**：`FinsResultSummary.__post_init__` 强制校验 SUCCESS=0, FAILURE=1, CANCELLED=130。contract 测试 `test_fins_result_exit_code_mapping_is_fixed` 覆盖非法映射。
- **cancel 输出**：`render_fins_direct_cancel_requested()` 不再接受 `job_id` 参数，输出 `"Fins operation cancel requested."`，无 job id 泄漏。
- **类型安全**：pyright 0 errors。`_CliFinsCancellationToken` 满足 `CancellationToken` protocol duck typing（`is_cancelled`、`cancel_reason`、`requested_at` 三方法齐备）。
- **`_ensure_result_event` defense-in-depth**：Service 层保证 stream 正常结束时有 RESULT；CLI 层 `_missing_result_event()` 兜底 Service bug。两者互不冲突。
- **`ingestion_runtime.py` async generator stubs**：`raise FinsDirectStreamNotImplementedError` + `yield` 是 Python async generator 返回类型标注的必要写法，不引入运行时问题。

## Findings

无阻塞 findings。

### Non-blocking observations

| ID | 严重度 | 文件:行号 | 描述 | 阻塞 |
|---|---|---|---|---|
| OBS-1 | info | `dayu/cli/commands/fins.py:740` | `_missing_result_event()` 硬编码 `FinsOperationKind.PREPROCESS`，而实际 operation 可能是 download/upload。该值仅用于 `FinsEvent` 构造，CLI 渲染不依赖 `operation_kind`，Service 层的 `_missing_result_event()` 正确传入 `operation_kind`。CLI 层 fallback 极低概率触发，不阻塞。 | 否 |
| OBS-2 | info | `dayu/service/README.md:13,25` | README 仍包含旧 durable job 描述（`stream_job_events_until_terminal`、`request_cancel(job_id)`、`job handle` 等）。fix artifact 已声明留给 Slice E。 | 否 |

## 阻塞项

无。

## Follow-up: Post-Review Changes

re-review 结论发出后，实施方追加了四项 post-review changes。本章节只核对这些增量变更。

### Follow-up 结论

**pass** — 增量变更合理，不阻塞，不违反 AGENTS.md。

### F1. `tests/conftest.py` 全局 logger 隔离 fixture

**结论：pass — 正确修复，不破坏 caplog 或生产日志语义**

**动机**：CLI 测试调用真实 `dayu-cli` 入口会装配 `dayu` namespace logger，把 handler 绑定到 pytest 捕获流。测试结束后捕获流关闭，但 handler 仍挂在 logger 上，导致后续测试日志写入失败或 `caplog` 无法观察 `dayu.*` 记录。

**实现分析** (`tests/conftest.py`)：

- `autouse=True` + 默认 function scope：每个测试前后都执行。
- 测试前快照 `dayu` logger 的 handlers、level、propagate、disabled。
- 测试后移除所有当前 handler，关闭新增 handler（`not in original_handlers`），恢复原始 handler 和属性。

**与 caplog 的兼容性**：

- `caplog` 在测试期间向 logger 添加自己的 handler，teardown 时调用 `logger.removeHandler(handler)`。
- pytest teardown 按 LIFO 顺序执行：`restore_dayu_namespace_logger` 后进先出，teardown 先于 caplog 执行。
- `restore_dayu_namespace_logger` teardown 会先移除 caplog 的 handler（因为它不在 `original_handlers` 中）并 `close()` 它。
- 随后 caplog teardown 调用 `logger.removeHandler(handler)` 对已移除的 handler 是 no-op（Python logging 规范）。
- caplog teardown 不使用 handler 对象本身，只调用 `removeHandler`，因此提前 `close()` 不引发异常。
- 受影响测试文件（`test_fins_commands.py`、`test_fins_direct.py` 等）当前无 `caplog` 使用，风险更低。

**AGENTS.md 合规**：

- 完整中文 docstring：✅
- 类型标注：`Generator[None, None, None]`、`Final[str]`：✅
- 无 `Any`、无 `object`：✅
- 无魔法字符串：`_DAYU_LOGGER_NAME` 为 `Final` 常量：✅
- 不改变生产日志装配策略：✅（只操作测试期间的 logger 状态）

### F2. `tests/README.md` 更新

**结论：pass — 在职责范围内**

新增三行说明 `tests/conftest.py` 的隔离夹具用途和原因。内容准确，不超出 README 读者（测试维护者）需要知道的范围。触发规则：`tests/` 修改 → 检查 `tests/README.md`，命中。

### F3. `docs/host/issues-implementation-control.md` 验证补记

**结论：pass — 符合总控文档职责**

在 WU-CLI-FINS-OBS-01 gate artifacts 区新增 implementation status、Slice A/B validation、review、fix、re-review 和 final validation 记录。内容与实际 artifact 路径和验证数字一致。总控文档由 controller 维护，补记不引入架构决策或新 scope。

### F4. `docs/reviews/wu-cli-fins-obs-01-slice-ab-review-fix-codex.md` 未变更

`git diff` 确认该文件无增量变更。

### Follow-up 验证结果

| 验证项 | 结果 |
|---|---|
| `pytest ... tests/fins/test_fins_ingestion_runtime.py -q`（扩展套件含 ingestion runtime） | 184 passed, 3 warnings |
| `pyright dayu/ tests/ utils/`（全量） | 0 errors, 0 warnings |
| `git diff --check` | clean |
| `rg caplog` 受影响测试文件 | 零使用，无干扰风险 |

## README Impact

- 本 re-review 不引入新代码变更。README 仍按 replacement plan Slice E 集中清理。
