# WU-CLI-FINS-OBS-01 Slice A/B Re-review (DS)

## 结论

**PASS**

无阻塞 finding。MiMo R1/R2、DS-001、DS-002 均已正确修复并通过测试验证。direct CLI/Service 路径无旧 durable job API coupling。stdout/stderr 输出路由正确，exit code 映射固定且一致。

## 审查范围

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: A/B merged diff (replacement plan implementation)
- Plan 真源: `docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- 设计真源: `docs/host/design.md`, `docs/engine/design.md`
- 控制文档: `docs/host/issues-implementation-control.md`
- 已修复 artifact: `docs/reviews/wu-cli-fins-obs-01-slice-ab-review-fix-codex.md`
- 审查对象: 当前未提交 diff（6 files changed, 1500 insertions, 1981 deletions）

## 重点核对项

### 1. MiMo R1/R2: SIGINT 取消注入后 terminal RESULT 不被覆盖

**PASS**

`_wait_for_terminal_handling_sigint` (`dayu/cli/commands/fins.py:643-696`) 的实现正确：

- 当 SIGINT 到达并触发 `event_task.cancel()` 后（line 682），先 `await event_task`（line 685）尝试获取结果。
- 若 stream 在 cancellation 生效前已产出 terminal RESULT（generator 内 `except asyncio.CancelledError` 捕获并 yield 终态），`await event_task` 返回真实终态，直接 return（line 689），不被本地 cancel 覆盖。
- 仅在 `asyncio.CancelledError` 路径（stream 被真正中断）才 fallback 到 `_cancelled_result_summary()`（line 691）。

测试覆盖真实竞态：

- `test_cancel_race_does_not_override_terminal_result` (`tests/cli/test_fins_commands.py:801-838`)：构造 cancel 注入后 stream 仍返回 `RESULT(status=SUCCESS)` 的场景，断言 CLI 返回 `FinsResultStatus.SUCCESS`，不被覆盖；同时断言 `token.is_cancelled()` 为 True 以证明取消请求已发出。
- `test_sigint_cancels_stream_task_without_job_id` (`tests/cli/test_fins_commands.py:766-797`)：覆盖正常取消路径，stream 被中断后产出本地 `CANCELLED` 结果，stderr 不含 `job_id`。

### 2. DS-001/DS-002: 用户可见输出和 docstring 已清除旧 job 术语

**PASS**

- `dayu/cli/output.py:39`: 前缀从 `"Fins job summary"` 改为 `"Fins summary"`。
- `dayu/cli/output.py:33-36`: cancel 消息使用 `"Fins operation cancel requested"` / `"Fins operation already cancelling"`，无 job 术语。
- `dayu/cli/commands/fins.py:1-7`: 模块 docstring 更新为 "SIGINT 到当前 async stream cancellation 的映射"，无 durable Fins job cancel 描述。
- `dayu/cli/commands/fins.py:109`: `_CliFinsCancellationToken` docstring 使用 "CLI direct operation"。
- `dayu/cli/commands/fins.py:169`: `_FinsSigintMonitor` docstring 使用 "Fins direct operation"。
- `rg` 确认 `dayu/cli/output.py`, `dayu/cli/commands/fins.py`, `dayu/service/fins_direct.py` 中无 `Fins job summary`、`direct job`、`job_id` 残留。

`dayu/fins/ingestion_runtime.py:1-7` 模块 docstring 仍包含 job/job record/job store 术语。该文件属于 Slice C 范围（runtime core API convergence），Slice A 只对其做 protocol shape 的 stub method 新增（`download/preprocess/upload` async generator stub），不修改已有 docstring。非 blocking。

### 3. Direct CLI/Service 无旧 durable job API coupling

**PASS**

`rg` 扫描 `dayu/cli/commands/fins.py`, `dayu/cli/output.py`, `dayu/service/fins_direct.py`:
- `FinsDirectJobHandle`: 0 hits
- `FinsDirectJobEvent`: 0 hits
- `FinsDirectTerminalResult`: 0 hits
- `stream_job_events_until_terminal`: 0 hits
- `read_job_events` / `read_job(` / `wait_for_terminal(`: 0 hits
- `request_cancel(job_id)` 形式的调用: 0 hits（仅有的 `request_cancel` 调用是 `cancellation_token.request_cancel("keyboard_interrupt")`，为 CLI 本地 token 方法，不是 service 方法）

Service public API 已改为：
- `FinsDirectCommandService.download(...)` → `AsyncIterator[FinsEvent]`
- `FinsDirectCommandService.process(...)` → `AsyncIterator[FinsEvent]`
- `FinsDirectCommandService.process_filing(...)` → `AsyncIterator[FinsEvent]`
- `FinsDirectCommandService.process_material(...)` → `AsyncIterator[FinsEvent]`
- `FinsDirectCommandService.upload_filing(...)` → `AsyncIterator[FinsEvent]`
- `FinsDirectCommandService.upload_material(...)` → `AsyncIterator[FinsEvent]`

边界测试 `test_service_public_direct_api_does_not_export_job_handle` (`tests/service/test_fins_direct.py:547-558`) 显式断言旧类型不在 `__all__`、`dir(module)` 和 `dir(FinsDirectCommandService)` 中。

### 4. 无 stdout/stderr、exit code 或 cancel 输出问题

**PASS**

输出流路由 (`dayu/cli/output.py`):
- `PROGRESS` → `effective_stdout` (line 155)
- `RESULT(status=SUCCESS)` → `effective_stdout` + details on stdout (lines 162-167)
- `RESULT(status=CANCELLED)` → `effective_stderr` (line 171)
- `RESULT(status=FAILURE)` → `effective_stderr` + details on stderr (lines 175-183)
- Cancel requested / local exit messages → `stderr` (lines 197-200, 214-217)

路由正确：业务正常输出到 stdout，异常/取消到 stderr。

Exit code 映射 (`dayu/fins/direct_events.py:16-18`):
- `SUCCESS` → 0 (`FINS_RESULT_EXIT_SUCCESS`)
- `FAILURE` → 1 (`FINS_RESULT_EXIT_FAILURE`)
- `CANCELLED` → 130 (`FINS_RESULT_EXIT_CANCELLED`)

`_validate_result_exit_code` (`direct_events.py:290-309`) 强制执行固定映射，测试 `test_fins_result_exit_code_mapping_is_fixed` (`tests/service/test_fins_direct.py:598-612`) 参数化覆盖所有非法映射组合。

## 覆盖率核对

### 测试覆盖

| 测试文件 | 用例数 | 状态 |
|---|---|---|
| `tests/service/test_fins_direct.py` | 19 passed | 覆盖 contract 校验、exit code 映射、leakage guard、no-RESULT fallback、multiple-RESULT rejection、stream error 传播、取消关闭、旧 API 边界 |
| `tests/cli/test_fins_commands.py` | 24 passed | 覆盖 progress/result 渲染、cancel race、cancel without job_id、stream no-result、KeyboardInterrupt before stream、log 分级输出不污染 UI、路径脱敏、upload file validate、upload_filings_from 不启动 live stream、unsupported flags、import boundary |

### 关键场景覆盖

- Progress → Result 正常路径: `test_live_fins_commands_render_progress_and_terminal_summary`
- Stream 无 RESULT → failure: `test_stream_without_result_returns_failure`
- Stream 异常传播: `test_stream_failure_propagates_to_cli_error`
- Multiple RESULT rejection: Service `_ensure_result_event` 检测重复 RESULT
- Cancel with terminal result race: `test_cancel_race_does_not_override_terminal_result`
- Cancel without job_id: `test_sigint_cancels_stream_task_without_job_id`
- KeyboardInterrupt before stream: `test_keyboard_interrupt_before_stream_exits_130`
- Success/Failure/Cancelled exit code: `test_terminal_failed_and_cancelled_status_exit_mapping`
- Exit code 映射固定: `test_fins_result_exit_code_mapping_is_fixed`
- Leakage guard: `test_fins_event_leakage_guard_rejects_internal_or_sensitive_text`
- Output path redaction: `test_output_redacts_embedded_absolute_paths`
- Log/UI 分离: `test_fins_direct_default_log_does_not_pollute_progress_output`, `test_fins_direct_verbose_log_outputs_execution_skeleton`, `test_fins_direct_debug_log_outputs_event_details`
- Upload file validation: `test_upload_file_allowlist_fail_fast`
- Upload_filings_from 非 live stream: `test_upload_filings_from_does_not_start_live_stream`
- Import boundary: `test_cli_does_not_import_fins_storage_directly`
- Service 旧 API 边界: `test_service_public_direct_api_does_not_export_job_handle`

### 类型检查

```
pyright dayu/fins/direct_events.py dayu/service/fins_direct.py dayu/fins/ingestion_runtime.py \
  dayu/cli/commands/fins.py dayu/cli/output.py tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_init_command.py tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py
→ 0 errors, 0 warnings, 0 informations
```

## 非阻塞发现

### Finding DS-RR-001: ingestion_runtime.py 模块 docstring 仍保留旧 job 术语

- **文件**: `dayu/fins/ingestion_runtime.py:1-7`
- **严重度**: Low
- **阻塞**: No
- **详情**: 模块 docstring 描述为 "Fins 自有 ingestion job 的 typed 请求、结果摘要、持久化 job record、文件系统 job store..."，这是旧 durable job 系统术语。但 replacement plan 将 runtime core API convergence 分配给 Slice C，Slice A 只在此文件中新增 `download/preprocess/upload` async generator stub 方法和 `FinsDirectStreamNotImplementedError`。docstring 的更新属于 Slice C 职责，不在当前 Slice A/B 范围。
- **建议**: Slice C 实现时同步更新模块 docstring。

### Finding DS-RR-002: ingestion_runtime.py 仍保留旧 job store API

- **文件**: `dayu/fins/ingestion_runtime.py` (start_download/start_preprocess/start_upload/read_job/read_job_events/request_cancel 等方法)
- **严重度**: Low
- **阻塞**: No
- **详情**: 旧 durable job store API 仍存在于 `FinsIngestionRuntime` 类中，包括 `start_download`、`start_preprocess`、`start_upload`、`read_job`、`read_job_events`、`request_cancel` 等方法。但 replacement plan 明确将删除或降级这些 API 分配给 Slice C（前置条件：Slice D0 完成 observation handle contract-only checkpoint）。Slice A/B 只新增 direct stream 协议 stub，不删除旧 API。当前无代码路径从 CLI direct 或 Service public direct API 调用这些旧方法。
- **建议**: Slice C 按 plan 收敛 API，Slate D0 完成后移除旧 job store。

### Finding DS-RR-003: _missing_result_event 使用 PREPROCESS 作为 fallback operation_kind

- **文件**: `dayu/cli/commands/fins.py:752-776`, line 761
- **严重度**: Low
- **阻塞**: No
- **详情**: CLI 的 `_missing_result_event()` 在构造 fallback 失败事件时使用 `FinsOperationKind.PREPROCESS` 作为硬编码 operation_kind，而非基于当前命令动态设置。这与 Service 层 `_ensure_result_event` 不同（后者使用调用方传入的 `operation_kind`）。当 download/upload 命令的 stream 无 RESULT 时，CLI fallback 事件会标记为 PREPROCESS，对诊断不够精确。
- **实际影响**: 该路径仅在 stream 正常结束但无 RESULT 时触发（producer bug），生产环境极低概率。`_ensure_result_event` 已作为主保证（Service 层注入 missing-RESULT），CLI fallback 仅在 Service bug 或非标准 consumer path 中兜底。
- **建议**: 后续可考虑将 `command_name` 传入 `_missing_result_event` 做精确映射，或直接复用 Service 注入的 RESULT。不阻塞当前 Slice。

## 验证摘要

| 验证项 | 结果 | 备注 |
|---|---|---|
| pytest tests/cli/test_fins_commands.py | 24 passed | 3 条第三方 edgar deprecation warning |
| pytest tests/service/test_fins_direct.py | 19 passed | |
| pytest 全量 CLI/Service | 129 passed | 含 init/prompt/interactive/upload_filings_from/arg_parsing |
| pytest tests/fins/test_fins_ingestion_runtime.py | 55 passed | 旧 job store 测试仍全部通过 |
| pyright (12 files) | 0 errors, 0 warnings | |
| rg 旧 API coupling (生产代码) | 0 hits | 仅剩测试中的 negative assertion |
| rg 旧 job 术语 (用户可见输出) | 0 hits | |
| stdout/stderr 路由 | 正确 | PROGRESS/SUCCESS→stdout, FAILURE/CANCELLED→stderr |
| exit code 映射 | SUCCESS→0, FAILURE→1, CANCELLED→130 | 有 contract-level 校验 + 测试 |

## Slice A/B vs Replacement Plan 对照

| Plan 要求 | 当前实现状态 | 结论 |
|---|---|---|
| `FinsEvent` typed contract | `dayu/fins/direct_events.py` 完整定义，含 post_init 校验、leakage guard、exit code 映射 | ✅ |
| `FinsDirectIngestionRuntime` protocol | `dayu/service/fins_direct.py:53-102` 定义 `download/preprocess/upload → AsyncIterator[FinsEvent]` | ✅ |
| `FinsDirectCommandService` async iterator boundary | 六个方法均返回 `AsyncIterator[FinsEvent]`，无 job handle | ✅ |
| 移除 CLI-facing 旧 API | `FinsDirectJobHandle`, `FinsDirectJobEvent`, `stream_job_events_until_terminal` 等已从 public API 移除 | ✅ |
| Runtime stub methods | `ingestion_runtime.py` 新增三个 `async def download/preprocess/upload` stub，raise NotImplementedError | ✅ |
| Cancel 不走 `request_cancel(job_id)` | 使用 `_CliFinsCancellationToken` + task cancellation | ✅ |
| `_ensure_result_event` 保证 terminal RESULT | Service 层注入 missing-RESULT failure；CLI 层也有 defensive fallback | ✅ |
| `FinsResultSummary` exit code 固定映射 | contract 层 `_validate_result_exit_code` 强制校验；测试参数化覆盖 | ✅ |
| Leakage guard | contract 层禁止 internal/absolute path/payload 文本；output 层脱敏截断 | ✅ |
| Slice C 不混入 Slice A | runtime 真实实现留给 Slice C；当前只有 stub | ✅ |

## Residual Risk

无新增 residual risk。已有的 `WU-CLI-FINS-OBS-01-R6`（Slice A/C 共享 `ingestion_runtime.py` 边界风险）、`WU-CLI-FINS-OBS-01-R7`（Slice D0 scope 限制）和 `WU-CLI-FINS-OBS-01-R8`（并发安全）仍按控制文档追踪。本 re-review 未发现需要新增 tracking item 的风险。

## Follow-up: Post-re-review Changes 核对 (2026-06-16)

本次核对仅针对 re-review 后新增/修改的三个文件，不重审完整大 diff。

### 1. `tests/conftest.py` — 全局 logger 隔离 fixture

**结论: 合理，无阻塞问题。**

实现分析：

- 使用 `@pytest.fixture(autouse=True)` 在每个测试前后保存/恢复 `dayu` namespace logger 的 handlers、level、propagate、disabled。
- 在 finally 中移除所有测试后残留的 handler，只关闭测试新增但未自行清理的 handler（`if handler not in original_handlers: handler.close()`），保留原始 handler。
- 最后重新添加原始 handler，恢复 level/propagate/disabled。

对 `caplog` 的影响分析：

- `caplog` 的工作原理是将 handler 挂到 root logger，通过 propagation 捕获日志。本 fixture 只操作 `dayu` namespace logger，不触碰 root logger。
- 使用 `_attach_caplog_to_dayu(caplog)` 模式的测试（如 `test_runner_b3_extra.py:275-280`、`test_runner_diagnostics.py`、`test_stream_idle.py` 等）都在 `try/finally` 中显式添加后移除 `caplog.handler`，因此 conftest teardown 执行时 `caplog.handler` 已不在 `current_handlers` 中，不会被错误关闭。
- 仅依赖 propagation 的 `caplog` 测试不受影响——`caplog.handler` 位于 root logger，不在 `dayu` logger 的 handlers 列表中。
- 测试失败导致的 handler 泄漏边缘场景：若 `_attach_caplog_to_dayu` 和 `removeHandler` 之间的代码抛出异常，`finally` 仍确保移除。极端的 Python 级崩溃（如 segfault）不属于本 fixture 的处理范围。

对生产日志语义的影响：

- 无。本 fixture 仅影响 pytest 运行时，不在生产代码路径中。生产日志的 handler/level/propagate 由 `dayu.runtime.log.configure()` 独立装配。

### 2. `tests/README.md` — logger 隔离说明

**结论: 合理，在职责范围内。**

- `tests/README.md` 尚无显式 `Agent更新约束` 章节，按 CLAUDE.md 指示以触发规则判断。
- 触发规则：`tests/` 修改 → 检查并按需更新 `tests/README.md`。当前 diff 修改了 `tests/` 文件（`conftest.py`、`test_fins_commands.py`、`test_fins_direct.py`）→ 触发成立。
- 新增内容为一句测试基础设施说明，描述 conftest.py 的 logger 隔离行为，内容准确、简洁，不扩散到测试策略、覆盖率目标或用户可见行为描述。
- 未自行扩写 README 职责。

### 3. `docs/host/issues-implementation-control.md` — Slice A/B gate artifacts 与最终验证

**结论: 合理，符合控制文档推进规则。**

- 新增条目记录了 Slice A/B 的 implementation artifacts、review artifacts、fix artifacts、re-review artifacts、post-review fix 和最终验证摘要。
- 符合控制文档推进规则：每个 work unit 进入 review 时必须更新 artifact、commit、review 与历史验证记录。
- 最终验证数据 `184 passed / pyright dayu tests utils 0 / diff check clean` 应记录——已记录。

### 4. 最终验证确认

| 验证项 | 结果 |
|---|---|
| `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_runtime.py -q` | 184 passed, 3 warnings |
| `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings |
| `git diff --check` | clean |

### Follow-up 结论

结论维持 **PASS**。三个 post-review change 均合理：conftest.py 正确隔离 `dayu` logger 且不破坏 caplog 或生产日志语义；tests/README.md 更新在职责范围内；控制文档更新符合推进规则。无新增 blocking finding。
