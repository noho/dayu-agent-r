# WU-CLI-01 / CLI-01-S5 Implementation Review — AgentMiMo

## Gate / Scope

- Gate: implementation review。
- Work unit: WU-CLI-01。
- Slice: CLI-01-S5，Fins direct job Service boundary and direct commands。
- 设计真源: `docs/host/design.md`、`docs/engine/design.md`。
- 总控文档: `docs/host/ui-implementation-control.md`。
- Accepted plan: `docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Implementation report: `docs/reviews/wu-cli-01-s5-implementation-codex.md`。
- Review target: 当前未提交 workspace changes 中的 CLI-01-S5 范围。

## 审查方法

按 controller follow-up review focus 的 9 项标准逐项裁决，辅以源码逐文件审查、测试运行验证和 pyright 类型检查。

## 验证结果

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`：22 passed。
- `source .venv/bin/activate && pytest tests/cli tests/service tests/fins/test_fins_ingestion_runtime.py -q`：195 passed，无回归。
- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py --cov=dayu.service.fins_direct --cov=dayu.cli.commands.fins --cov-report=term-missing -q`：`fins_direct.py` 92%，`fins.py` 88%，总 90%。
- `source .venv/bin/activate && python -m pyright dayu/service/fins_direct.py dayu/cli/commands/fins.py dayu/cli/output.py dayu/cli/arg_parsing.py dayu/cli/main.py`：0 errors。

## 逐项裁决

### 标准 1：迁移旧业务逻辑，适配新 Host public contracts / API 与 approved Service/Fins boundary

**裁决：PASS。**

`FinsDirectCommandService` 收敛了 Fins direct job 的 start / poll / cancel / terminal mapping 语义，使用当前 `FinsIngestionRuntime` 的 typed request 和 job store，不搬运旧 CLI 实现。Upload wrapper 构造 `FinsUploadFilingRequest` / `FinsUploadMaterialRequest` 后调用 `runtime.start_upload(request)`，与旧 CLI 中分散的 upload helper 不同。CLI 参数转换逻辑是新写的显式映射，不是旧代码的逐行搬迁。

证据：
- `dayu/service/fins_direct.py:334-383`（start_upload_filing）和 `:385-446`（start_upload_material）：构造 union request 后调用 `runtime.start_upload()`。
- `dayu/cli/commands/fins.py:265-287`（_start_download）到 `:399-420`（_start_process_material）：CLI 参数到 Service 显式方法参数的映射。

### 标准 2：Fins direct commands 不伪装成 Host Run，通过 Service/Fins boundary 触达 runtime

**裁决：PASS。**

Fins direct commands 不创建 Host Run，不写 Host EventLog。CLI 通过 `FINS_DIRECT_SERVICE_FACTORY` 调用 `FinsDirectCommandService`，后者通过 `DefaultFinsRuntime.get_ingestion_runtime()` 或注入的 `FinsDirectIngestionRuntime` 协议触达 Fins runtime。CLI 源码不直接 import `dayu.fins.storage`。

证据：
- `dayu/cli/commands/fins.py:41-46`：CLI 只导入 `FinsDirectCommandService` 等 Service 类型和 `SourceKind` 枚举。
- `tests/cli/test_fins_commands.py:686-708`（test_cli_does_not_import_fins_storage_directly）：AST 扫描确认 CLI 无 `dayu.fins.storage` 直接 import。
- `dayu/service/fins_direct.py:18-31`：Service 只导入 `dayu.fins.domain.enums`、`dayu.fins.ingestion_runtime` 和 `dayu.fins.service_runtime`，属于 approved boundary。

### 标准 3：Agent commands 既有边界不被破坏

**裁决：PASS。**

`prompt` 和 `interactive` 命令的代码在本 slice 未修改。`dayu/cli/main.py` 新增 Fins direct command runner 注册，未改动 prompt / interactive 的 runner 注册。

证据：
- `dayu/cli/main.py:44-45`：`COMMAND_RUNNERS[COMMAND_INTERACTIVE]` 和 `COMMAND_RUNNERS[COMMAND_PROMPT]` 仍指向原有 runner。
- `dayu/cli/main.py:46-52`：新增的 Fins direct runner 注册不干扰已有注册。

### 标准 4：UI 和 Service 边界清晰

**裁决：PASS。**

`FinsDirectCommandService` 不依赖 CLI stdout/stderr、argparse、signal handler。`_FinsSigintMonitor` 在 CLI adapter 层（`dayu/cli/commands/fins.py`），不在 Service helper 中。`render_fins_direct_*` 输出函数在 `dayu/cli/output.py`，Service 不调用它们。

证据：
- `dayu/service/fins_direct.py`：零 import `sys`、`signal`、`argparse` 或 `dayu.cli`。
- `dayu/cli/commands/fins.py:106-179`（_FinsSigintMonitor）：signal handler 在 CLI adapter 层。
- `dayu/cli/output.py:120-205`：Fins 输出函数只在 CLI 调用。

### 标准 5：Fins direct cancel 必须成立

**裁决：PASS。**

cancel 语义完整实现：
- job id 前 KeyboardInterrupt：`run_fins_direct_command` 的 `except KeyboardInterrupt` 返回 130（`fins.py:205`）。
- job id 后第一次 SIGINT：`_wait_for_terminal_handling_sigint` 中 `service.request_cancel(handle.job_id)` 并继续 poll（`fins.py:458-459`）。
- 第二次 SIGINT：`wait_task.cancel()` 后 `render_fins_direct_local_exit_after_cancel(handle.job_id)` 并返回 `None`（`fins.py:455-457`），外层返回 130（`fins.py:232`）。

证据：
- `tests/cli/test_fins_commands.py:543-571`（test_sigint_after_job_id_requests_cancel_and_waits_terminal）：验证第一次 SIGINT 触发 `request_cancel` 并返回 terminal。
- `tests/cli/test_fins_commands.py:574-614`（test_second_sigint_after_cancel_exits_locally）：验证第二次 SIGINT 返回 `None`（本地 130）并打印 job id。
- `tests/cli/test_fins_commands.py:617-660`（test_keyboard_interrupt_before_job_id_exits_130）：验证 job id 前中断不做 durable cancel。

### 标准 6：upload wrapper 由 Service 构造 typed request 并调用 runtime.start_upload(request)

**裁决：PASS。**

`start_upload_filing` 构造 `FinsUploadFilingRequest`，`start_upload_material` 构造 `FinsUploadMaterialRequest`，二者均调用 `self._runtime.start_upload(request)`。Runtime 不存在 `start_upload_filing` 或 `start_upload_material` 方法。

证据：
- `dayu/service/fins_direct.py:368-382`：`FinsUploadFilingRequest(...)` → `self._runtime.start_upload(request)`。
- `dayu/service/fins_direct.py:427-445`：`FinsUploadMaterialRequest(...)` → `self._runtime.start_upload(request)`。
- `tests/service/test_fins_direct.py:252-322`（test_upload_wrappers_call_start_upload_with_union_requests）：断言 `isinstance(runtime.upload_requests[0], FinsUploadFilingRequest)` 和 `isinstance(runtime.upload_requests[1], FinsUploadMaterialRequest)`。

### 标准 7：unsupported 命令与 flag 行为

**裁决：PASS。**

- `upload_filings_from`：parser 保留，执行时 raise `CliFinsUsageError(_UPLOAD_FILINGS_FROM_UNSUPPORTED)`（`fins.py:220-221`）。
- `--infer`：`_raise_for_unsupported_flags` 检查 `args.infer` 并 raise（`fins.py:479-485`）。
- `--ci`：同上检查 `args.ci`（`fins.py:486-491`）。

证据：
- `tests/cli/test_fins_commands.py:489-508`（test_unsupported_flags_and_s6_command_fail_fast）：覆盖 `--infer`、`--ci` 和 `upload_filings_from` 均返回 `EXIT_USAGE_ERROR`。

### 标准 8：CLI 对 SourceKind 的依赖边界

**裁决：PASS。**

CLI 只导入 `dayu.fins.domain.enums.SourceKind`，用于 `process` / `process_filing` / `process_material` 的 `source_kind` 参数。这是 accepted plan 允许的 Fins 枚举 / domain value，不扩散为 CLI 直接依赖 Fins runtime 或 storage。

证据：
- `dayu/cli/commands/fins.py:40`：`from dayu.fins.domain.enums import SourceKind`。
- `tests/service/test_import_boundary.py:15-19`：`SERVICE_ALLOWED_IMPORTS` 包含 `dayu.fins.domain.enums`、`dayu.fins.ingestion`、`dayu.fins.ingestion_runtime`、`dayu.fins.service_runtime`。

### 标准 9：AGENTS.md 编码约束

**裁决：PASS。**

- 中文 docstring：`fins_direct.py` 和 `fins.py` 所有 public 函数、类和模块均有中文 docstring。
- 严格类型：所有函数签名使用严格类型注解，无 `Any`、`object` 或无类型参数。
- 无反向依赖：Service 不 import CLI、Host、Engine 或 UI；CLI 不 import Fins storage。
- README 触发：`dayu/README.md`、`dayu/service/README.md`、`tests/README.md` 均按 AGENTS.md 触发规则更新，内容与当前实现一致。
- 测试覆盖：`fins_direct.py` 92%，`fins.py` 88%，均 >= 80%。

## Findings

按 severity 排序。无 blocking finding。

### S5-REVIEW-F01 [Observation / Non-blocking]

**文件**: `tests/cli/test_fins_commands.py`
**位置**: 模块级（无行号）
**描述**: 测试文件缺少模块级 docstring。
**影响**: 不影响功能正确性或测试覆盖；属于编码规范一致性。
**建议修复**: 在文件头部添加 `"""dayu-cli Fins direct commands 测试。"""`。
**Severity**: observation。

### S5-REVIEW-F02 [Observation / Non-blocking]

**文件**: `dayu/cli/commands/fins.py:156`
**位置**: `_FinsSigintMonitor.notify` 方法签名
**描述**: `notify` 方法的 `_signal_number` 和 `_frame` 参数以下划线前缀标记为未使用，但未用 `del` 显式抑制。当前 pyright 不报错，但与 `test_fins_direct.py` 中 fake runtime 的 `del cancellation_token` 模式不一致。
**影响**: 不影响功能；pyright 通过。
**建议修复**: 可选择在方法体开头添加 `del _signal_number, _frame` 保持与项目其它 handler 一致；非必须。
**Severity**: observation。

## Residual Risks

| Risk | 分类 | 与 implementation report 对齐 | 备注 |
|---|---|---|---|
| `upload_filings_from` 未实施 | deferred-with-owner | 对齐，归属 CLI-01-S6 | 保留 parser，执行时报 unsupported |
| `--infer` alias inference | deferred-with-owner | 对齐，沿用总控 WU-CLI-01-RR-01 | 解析保留，执行时报 unsupported |
| `--ci` process snapshot | deferred-with-owner | 对齐，沿用总控 WU-CLI-01-RR-02 | 解析保留，执行时报 unsupported |
| Fins cancel responsiveness | deferred-with-owner | 对齐，沿用总控 WU-CLI-01-RR-06 | 协作式 cancel，取决于 runtime pipeline checkpoint |
| `upload_filing --action delete` runtime 支持 | deferred-with-owner | 沿用总控 WU-CLI-01-RR-07 | 需实现时验证 runtime 是否支持 delete action |

## 总控文档同步状态

- 当前 gate：review。
- implementation status：CLI-01-S5 implemented; awaiting implementation review。
- 本轮 review artifact：本文档。
- 无 blocking finding。
- 下一步：进入 CLI-01-S5 re-review gate 或 AgentDS review gate（取决于总控工作流）。

## 裁决

**PASS。** 无 blocking finding。S5 实现符合 accepted Service/Fins boundary，Fins direct commands 通过 `dayu.service.fins_direct` 触达 runtime，CLI 不直接读取 Fins storage，upload wrapper 使用 union API，cancel 语义完整，unsupported flags 行为正确，AGENTS.md 编码约束和测试覆盖要求均已满足。两个 observation 级别 finding 不阻塞通过。
