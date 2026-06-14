# WU-CLI-01 / CLI-01-S5 Implementation Review — DS

## Gate / Scope

- Gate: code review。
- Work unit: WU-CLI-01。
- Slice: CLI-01-S5 — Fins direct job Service boundary and direct commands。
- 设计真源: `docs/host/design.md`、`docs/engine/design.md`。
- 总控文档: `docs/host/ui-implementation-control.md`。
- Accepted plan: `docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Implementation report: `docs/reviews/wu-cli-01-s5-implementation-codex.md`。

## Review Scope

本次 review 只审查当前未提交 workspace changes 中的 CLI-01-S5 范围。按 controller 指定的 9 条 review 标准做 evidence-based 裁决。

## 验证确认

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`：22 passed。
- `source .venv/bin/activate && pytest tests/cli tests/service tests/fins/test_fins_ingestion_runtime.py -q`：195 passed。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## Review Criteria 逐条裁决

### 1. 旧代码业务逻辑迁移到新 Service/Fins boundary —— **PASS**

实现完全按 accepted plan 的 Service/Fins boundary 设计。Service helper `dayu/service/fins_direct.py` 定义了 `FinsDirectIngestionRuntime` Protocol（只表达 direct command 所需的 `start_download` / `start_preprocess` / `start_upload` / `read_job` / `request_cancel`），通过 `DefaultFinsRuntime.create(workspace_root).get_ingestion_runtime()` 获取真实 runtime。CLI 不散落调用 runtime 方法，不读取 durable job store 文件系统路径。

所有 typed request 构造（`FinsDownloadRequest`、`FinsPreprocessRequest`、`FinsUploadFilingRequest`、`FinsUploadMaterialRequest`）都收敛在 Service helper 的方法内部，CLI 只传显式参数值。

未发现旧实现搬运。旧 `dayu-agent` 的 `cli_support.py` 中任何 helper、旧目录结构、旧 label registry 均未进入本 slice。

证据：
- `dayu/service/fins_direct.py:257-296` — `start_download` 构造 `FinsDownloadRequest` 并调用 `self._runtime.start_download(request)`。
- `dayu/service/fins_direct.py:298-332` — `start_preprocess` 构造 `FinsPreprocessRequest` 并调用 `self._runtime.start_preprocess(request)`。
- `dayu/service/fins_direct.py:334-446` — `start_upload_filing` / `start_upload_material` 构造各自的 typed request 并调用 `self._runtime.start_upload(request)`，不走不存在的 runtime 方法。

### 2. Fins direct commands 经 Service/Fins boundary 触达 runtime —— **PASS**

CLI 调用链：`run_fins_direct_command` → `_run_fins_direct_command_async` → `FINS_DIRECT_SERVICE_FACTORY(workspace_root)`（实际调用 `FinsDirectCommandService.from_workspace_root`）→ `service.start_*` → `_wait_for_terminal_handling_sigint` → `service.wait_for_terminal(job_id)` / `service.request_cancel(job_id)`。

CLI 不直接 import `dayu.fins.storage`，不调用 `FinsIngestionRuntime`，不直接打开 job store 文件。`tests/cli/test_fins_commands.py:686-708` 的 AST 扫描测试验证了 CLI 源码零 `dayu.fins.storage` 引用。

证据：
- `dayu/cli/commands/fins.py:224` — `service = FINS_DIRECT_SERVICE_FACTORY(workspace_root)`。
- `dayu/cli/commands/fins.py:458` — `service.request_cancel(handle.job_id)`。
- `dayu/cli/commands/fins.py:448` — `await service.wait_for_terminal(handle.job_id)`。

### 3. Agent commands (prompt/interactive) 边界未被破坏 —— **PASS**

`dayu/cli/main.py` 的 `COMMAND_RUNNERS` 中 prompt/interactive 仍分别映射到 `run_prompt_command` / `run_interactive_command`。Fins direct 命令通过独立的 `run_fins_direct_command` runner，不经过 `entrypoint_runtime`。prompt/interactive 的 Service assembly → Host public API 路径未被本 slice 修改。

证据：
- `dayu/cli/main.py:44-45` — `COMMAND_RUNNERS[COMMAND_INTERACTIVE] = run_interactive_command`、`COMMAND_RUNNERS[COMMAND_PROMPT] = run_prompt_command`。
- `dayu/cli/main.py:46-52` — Fins direct 命令独立映射到 `run_fins_direct_command`。

### 4. UI 和 Service 边界清晰 —— **PASS**

CLI adapter (`dayu/cli/commands/fins.py`) 负责：
- argparse 参数转换（ticker CSV 解析、文件路径 allowlist 校验、document_id 解析）。
- stdout/stderr 输出（通过 `dayu/cli/output.py` 的 `render_fins_direct_*` 函数）。
- SIGINT handler 安装 / 移除（`_FinsSigintMonitor`）。
- `asyncio.run()` 边界包装。

Service helper (`dayu/service/fins_direct.py`) 不导入 argparse、不写 stdout/stderr、不安装 signal handler。所有方法都是同步的（`start_*`、`read_job`、`request_cancel`），只有 `wait_for_terminal` 是 async（仅包含 polling loop + sleep），与 signal 处理完全解耦。

后续 WeChat / GUI 可以直接复用 `FinsDirectCommandService`，无需复制任何 CLI 专用编排。

证据：
- `dayu/service/fins_direct.py` 全文无 `argparse` / `sys.stdout` / `sys.stderr` / `signal` import。
- `dayu/cli/commands/fins.py:106-179` — `_FinsSigintMonitor` 仅存在于 CLI 层。

### 5. Fins direct cancel 行为 —— **PASS**

cancel 语义按 accepted plan 正确实现：

- **job id 前 SIGINT**：`asyncio.run()` 内部同步 `_start_direct_job` 在 handler 安装前发生 `KeyboardInterrupt`，外层的 `except KeyboardInterrupt` 捕获 → exit 130。测试覆盖：`tests/cli/test_fins_commands.py:617-660`。

- **第一次 SIGINT after job id**：`_wait_for_terminal_handling_sigint` 中 `sigint_task` 完成 → `service.request_cancel(handle.job_id)` → `cancel_requested = True` → 打印 "Fins job cancel requested: {job_id}" → 继续 poll。测试覆盖：`tests/cli/test_fins_commands.py:543-572`。

- **第二次 SIGINT after cancel request**：`sigint_task` 再次完成 → `cancel_requested` 为 True → cancel `wait_task` → 打印 "local process exiting: {job_id}" → return None → exit 130。测试覆盖：`tests/cli/test_fins_commands.py:574-615`。

- **正常终态到来（cancel 后 job 先于第二次 SIGINT 到终态）**：`wait_task` 先完成 → 取消 `sigint_task` → 返回 terminal result。测试覆盖：`tests/cli/test_fins_commands.py:543-572`。

SIGINT handler 的 install/close 生命周期正确：`install()` 在 `_wait_for_terminal_handling_sigint` 入口调用，`close()` 在 finally 块调用。当前的 `_cancel_and_await_task` 异味（S4-IMPL-F02）已在此处通过统一的 `finally` 清理模式解决。

证据：
- `dayu/cli/commands/fins.py:423-468` — 完整 `_wait_for_terminal_handling_sigint` 状态机。
- `dayu/cli/commands/fins.py:144` — `sigint_monitor.close()` 在 finally 块。

### 6. Upload wrapper 构造 request 调用 runtime.start_upload —— **PASS**

双层验证确认：

- Service helper `start_upload_filing(...)` 构造 `FinsUploadFilingRequest(ticker=..., source_kind=SourceKind.FILING, ...)` 并通过 `self._runtime.start_upload(request, cancellation_token=cancellation_token)` 提交。**不调用**不存在的 `runtime.start_upload_filing(...)` 方法。
- Service helper `start_upload_material(...)` 同样构造 `FinsUploadMaterialRequest` 后调用 `runtime.start_upload(...)`。

测试确认：
- `tests/service/test_fins_direct.py:252-323` — 断言 `runtime.upload_requests[0]` 是 `FinsUploadFilingRequest` 实例，`runtime.upload_requests[1]` 是 `FinsUploadMaterialRequest` 实例，两者都通过 `start_upload` 路径提交。

证据：
- `dayu/service/fins_direct.py:368-383` — `request = FinsUploadFilingRequest(...)` → `self._runtime.start_upload(request, ...)`。
- `dayu/service/fins_direct.py:427-446` — `request = FinsUploadMaterialRequest(...)` → `self._runtime.start_upload(request, ...)`。

### 7. Unsupported flags 和 S6 command —— **PASS**

- `upload_filings_from`：在 `_run_fins_direct_command_async:220-221` 中明确检查并抛出 `CliFinsUsageError`，cli error exit 2。
- `--infer`：`_raise_for_unsupported_flags:479-485` 中 fail fast，exit 2，包含原因 "当前没有 approved Fins alias inference boundary"。
- `--ci`：`_raise_for_unsupported_flags:486-492` 中 fail fast，exit 2，包含原因 "当前没有 public CI snapshot contract"。

三个路径均无"静默忽略"或"警告后继续"。测试覆盖：`tests/cli/test_fins_commands.py:489-507`。

证据：
- `dayu/cli/commands/fins.py:220-221`、`dayu/cli/commands/fins.py:471-492`。

### 8. CLI 对 Fins 枚举/domain value 的依赖 —— **PASS**

CLI 当前对 `dayu.fins` 的依赖：
- `dayu/cli/commands/fins.py:40` — `from dayu.fins.domain.enums import SourceKind`：用于 `start_preprocess` 的 `source_kind=SourceKind.FILING` / `SourceKind.MATERIAL` 参数。属于 accepted plan 允许的"Fins 枚举 / domain value"。
- `dayu/cli/output.py:163` — `from dayu.fins.ingestion_runtime import FinsIngestionJobStatus`：用于 `render_fins_direct_terminal_result` 的终态 display 对比。`FinsIngestionJobStatus` 是枚举，不是 runtime 调用能力。

CLI **未**直接导入：
- `dayu.fins.ingestion_runtime` 的 `FinsIngestionRuntime` 类或任何 runtime 方法。
- `dayu.fins.service_runtime` 的 `DefaultFinsRuntime`。
- `dayu.fins.storage` 任何模块。

CLI 对 `FinsIngestionJobStatus` 的使用仅限 display 路径的 `is` 身份比较，不调用任何 runtime 方法，不读取 job store。见 `dayu/cli/output.py:137-148` 的 `if result.status is FinsIngestionJobStatus.SUCCEEDED`。

`FinsIngestionJobStatus` 当前定义在 `dayu.fins.ingestion_runtime` 中（而非 `dayu.fins.domain.enums`），这是 Fins 模块自身组织选择。CLI 的 import 只取枚举符号用于 display，不扩散为 CLI 直接依赖 runtime 实现或 storage。

### 9. AGENTS.md 约束 —— **PASS**

#### 中文 docstring
所有新增/修改的函数、类、模块均有完整中文 docstring，包含参数、返回值、异常说明。验证通过。

#### 严格类型签名
- 无 `Any` / `object` 逃逸。
- 无 `hasattr` / `getattr` 使用。
- Protocol `FinsDirectIngestionRuntime` 的方法签名与真实 `FinsIngestionRuntime` 兼容。
- `FinsDirectCommandService` 的 `_sleep` 使用 `Callable[[float], Awaitable[None]]`，类型完整。

#### 无反向依赖
- `dayu.service.fins_direct` → `dayu.fins.*`（正确方向：Service → Fins）。
- `dayu.cli.commands.fins` → `dayu.service.fins_direct`（正确方向：UI → Service）。
- `dayu.cli.output` → `dayu.service.fins_direct` / `dayu.fins.ingestion_runtime`（仅取 enum/result 类型用于 display）。

#### README 触发
按 AGENTS.md 触发规则验证：
- `dayu/service/` 修改 → `dayu/service/README.md` 已更新：新增 `dayu.service.fins_direct` 说明和 upload wrapper 边界说明。✅
- `dayu/README.md` 已更新：稳定边界补充 Fins direct job 说明，工具与 Fins 节补充 CLI direct 命令路径。✅
- `tests/` 修改 → `tests/README.md` 已更新：新增 Fins direct command 测试覆盖说明和 import boundary 变化。✅
- `dayu/fins/` 未新增文件（S6 的 `upload_batch.py` 尚未创建），不需要更新 `dayu/fins/README.md`。✅

#### 测试覆盖
- `dayu/service/fins_direct.py`：92%，≥ 80%。✅
- `dayu/cli/commands/fins.py`：88%，≥ 80%。✅
- Service boundary 测试：typed request 构造、upload wrapper union API、poll sleep、cancel、terminal mapping。✅
- CLI 测试：六个 command 参数转换、unsupported flags、cancel path、SIGINT 两次行为、file allowlist、no direct storage import。✅

## Findings

### S5-RV-O01 — SUCCEEDED 终端输出未使用 result_summary（Observation）

- **Severity**: Low / Observation。
- **文件/行号**: `dayu/cli/output.py:137-148`（`render_fins_direct_terminal_result` 的 SUCCEEDED 分支）。
- **证据**: 当 `result.status is FinsIngestionJobStatus.SUCCEEDED` 时，函数只打印 `"Fins job succeeded: {job_id}"` 模板字符串到 stdout，然后返回 `result.exit_code`。`result.result_summary` 字段（`Mapping[str, JsonValue]`）携带了 `FinsIngestionJobRecord.result_summary` 中的结构化业务结果（如 download 的下载数量、preprocess 的处理文档数），完全未被使用。
- **影响**: 用户执行 `dayu-cli download --ticker AAPL` 成功后只能看到 "Fins job succeeded: finsjob_xxxx"，无法了解下载了多少文件、跳过了哪些已存在的文件。对于数据入口命令来说，成功输出缺少业务摘要降低可用性。
- **建议**: 后续 slice 中对 `result_summary` 的主要字段做易读输出（至少输出 key count 或 summary 中可读文本），但不阻塞当前 S5 pass。

### S5-RV-O02 — SIGINT monitor 在无 add_signal_handler 平台静默降级（Observation）

- **Severity**: Low / Observation（已在 plan 和 residual risk 中登记）。
- **文件/行号**: `dayu/cli/commands/fins.py:136-141`（`_FinsSigintMonitor.install` 的 except 分支）。
- **证据**: 当 `loop.add_signal_handler(signal.SIGINT, self.notify)` 抛出 `NotImplementedError` 或 `RuntimeError` 时（如 Windows ProactorEventLoop），`install()` 静默设置 `_installed=False`。此后 `wait_next()` 中的 `await self._event.wait()` 永远无法被唤醒，因为没有任何代码会调用 `notify()`。Fins direct job 的 cancel 路径（第一次 SIGINT → `request_cancel` + poll、第二次 SIGINT → local exit）在此平台完全不可用。
- **影响**: 降级行为是 `KeyboardInterrupt` 仍然可能通过 `asyncio.run()` 触发外层 catch → exit 130，但用户无法触发 durable cancel、也无法看到第一次/第二次 SIGINT 的区分行为。此场景已在 `docs/host/ui-implementation-control.md` 的 WU-CLI-01-RR-06 中登记为 `deferred-with-owner`，当前目标平台（macOS/Linux SelectorEventLoop）不受影响。
- **建议**: 建议在 `except` 分支增加 `logging.getLogger(__name__).warning(...)` 输出诊断信息，使排查时有可见信号。不阻塞当前 S5 pass。

## Adversarial Pass / 反例检查

### 反例 1：如果 FinsIngestionRuntime.start_upload 变成 async，Service helper 会怎样？

当前 `FinsDirectIngestionRuntime` Protocol 声明 `start_upload` 为 sync。如果未来真实 `FinsIngestionRuntime.start_upload` 变成 async，`FinsDirectCommandService.__init__` 的 `self._runtime = runtime.get_ingestion_runtime()` 会返回类型兼容的 runtime（因为真实 runtime 使用 `async def`，与 Protocol 的 sync signature 不兼容），pyright 会报错。这是期望的 fail-early 行为。Service helper 本身可以通过升级 Protocol 到 async 来适配，不影响 CLI 层。

### 反例 2：如果 poll 循环中 read_job 持续抛出异常，会发生什么？

`wait_for_terminal` 不捕获异常，异常会透传到 `_wait_for_terminal_handling_sigint` → `wait_task` 异常 → `asyncio.wait()` 看到 `wait_task.done()` → `await wait_task` 透传异常 → 最终到 `_run_fins_direct_command_async` → `run_fins_direct_command` 的 `except Exception` → exit 1。行为合理。

### 反例 3：SIGINT 在 install() 和 asyncio.wait() 之间到达？

`install()` 和 `asyncio.create_task(sigint_monitor.wait_next(...))` 之间没有 `await` 点（`create_task` 只是调度，不挂起）。SIGINT 在这段同步代码中无法被 Python 信号机制触发。`create_task` 之后立即进入 `asyncio.wait(...)`，此时 handler 已注册。无 race。

### 反例 4：wait_task 和 sigint_task 同时完成？

`asyncio.wait(..., return_when=FIRST_COMPLETED)` 在多个 task 同时完成时可能随机返回一个。代码先检查 `wait_task.done()`——如果 wait_task 已完成（job 已到终态），优先返回 terminal result，忽略 sigint_task 的完成。如果 sigint_task 先进 `done()` 检查但 wait_task 也已完成，`wait_task.done()` 仍为 True → 返回 terminal。正确，无"cancel 吞掉 terminal"的风险。

### 反例 5：直接调用 `python -m dayu.cli download --ticker AAPL`，Handler 何时安装？

`_FinsSigintMonitor.install()` 在 `_wait_for_terminal_handling_sigint` 开始时调用，该函数在所有 sync 前置操作（`_raise_for_unsupported_flags`、`_resolve_workspace_root`、`FINS_DIRECT_SERVICE_FACTORY`、`_start_direct_job`）之后。前置操作全部是 sync，运行在 `asyncio.run()` 的事件循环线程上。如果 SIGINT 在前置操作期间到达，`asyncio.run()` 会 raise `KeyboardInterrupt`，由 `run_fins_direct_command` 的 `except KeyboardInterrupt` 捕获 → exit 130。符合"job id 前 SIGINT → 130"语义。

## Residual Risks

| Risk | Owner / Destination | Status |
|---|---|---|
| Fins cancel responsiveness（长事务可能不及时检查 cancel checkpoint） | Fins runtime owner；`WU-CLI-01-RR-06` | `deferred-with-owner` |
| `--infer` alias inference 未实施 | Fins owner；`WU-CLI-01-RR-01` | `deferred-with-owner` |
| `--ci` process snapshot 未实施 | Fins/tooling owner；`WU-CLI-01-RR-02` | `deferred-with-owner` |
| `upload_filings_from` 未实施 | CLI-01-S6 | `deferred-with-owner` |
| Windows ProactorEventLoop 下 SIGINT handler 不可用 | Cross-platform signal adapter；`WU-CLI-01-RR-06` | `deferred-with-owner` |
| `upload_filing --action delete` 当前是否被 upload runtime 支持 | Fins runtime owner；`WU-CLI-01-RR-07` | `deferred-with-owner` |
| SUCCEEDED 终端输出不展示 result_summary | CLI output follow-up | 低风险，按需后续 touch |

## 总评

**Verdict: PASS**。无 blocking finding。

9 条 review criteria 全部通过。实现严格按 accepted plan 的 Service/Fins boundary 设计，CLI 只做参数转换、用户输入校验和 SIGINT 映射，typed request 构造收敛在 `FinsDirectCommandService`。upload wrapper 正确通过 `runtime.start_upload(...)` union API 提交，不要求不存在的 `start_upload_filing` / `start_upload_material`。cancel 语义完整实现（第一次 SIGINT → durable cancel + poll，第二次 SIGINT → local 130 + job id），测试覆盖两次行为和边界情况。Agent commands 的边界未被破坏。所有 AGENTS.md 约束（中文 docstring、严格类型、无反向依赖、README 触发、测试覆盖率 ≥ 80%）均通过。pyright 0 errors。

两项 observation（SUCCEEDED 输出未用 result_summary、无 add_signal_handler 平台静默降级）均为非阻塞级别，不影响 correct pass。
