# Code Review

## 结论：PASS-WITH-FINDINGS

## Scope

- **Mode**: current changes
- **Branch**: `phaseflow/host-issues-implementation`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-ds-20260615-205638.md`
- **Work unit**: WU-CLI-FINS-OBS-01 — Fins direct live event stream、Service event consumer、CLI UI print/log/cancel、README sync、tests 和控制文档
- **Included scope**:
  - `dayu/fins/ingestion_events.py` — 新模块：Fins ingestion job event 契约（typed record、append 输入、payload 校验）
  - `dayu/fins/ingestion_runtime.py` — 大量扩展：event sidecar（JSONL）、progress event 发射、event store protocol、sequence 管理、cancel event
  - `dayu/service/fins_direct.py` — 重构：新增 `stream_job_events_until_terminal`（替换旧 `wait_for_terminal`）、terminal fallback、event projection
  - `dayu/cli/commands/fins.py` — 重构：SIGINT 后 event stream 消费替代 poll loop、诊断日志
  - `dayu/cli/output.py` — 重构：`render_fins_direct_event` 替代 `render_fins_direct_terminal_result`、输出净化与脱敏
  - `dayu/cli/main.py` — `runtime_log.set_level_from_flags` 装配
  - `dayu/runtime/log.py` — 新模块：层中立日志装配、VERBOSE 级别、`log_verbose`/`bounded_payload_keys` helper
  - `dayu/README.md`、`dayu/fins/README.md`、`dayu/service/README.md`、`tests/README.md` — 文档同步
  - `tests/` — 全面测试覆盖
- **Excluded scope**: 已有的 `docs/reviews/` 历史 review artifacts、Gateflow control doc（仅检查一致性）
- **Parallel review coverage**: 5 个 subagent 并行审查
  - ingestion_events + ingestion_runtime（event stream/state truth/event sidecar）
  - service/fins_direct（Service 边界/cancel semantics）
  - CLI commands + output（UI/log 分离/输出净化）
  - runtime/log.py（日志 helper 分层）
  - Tests + README（测试覆盖/LLM-facing 语义）
  - 每个 subagent 沿真实代码路径走读，主 reviewer 复核证据链并裁决 severity
- **Controller 验证**: pytest 207 passed, 3 warnings；pyright 0 errors；git diff --check clean

---

## Findings

### 1-PASS-WITH-FINDINGS-中低-corrupted JSONL 导致该 job 所有 event read/append 永久失败

- **入口/函数**: `dayu/fins/ingestion_runtime.py:_iter_event_records_locked` (line 1517)
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1532-1541`
- **输入场景**: event sidecar JSONL 文件某一行在写入过程中因 crash、磁盘满或进程 kill 导致截断（例如 `append_job_event` 中 `stream.write(encoded)` 和 `os.fsync` 之间中断），文件末尾存在不完整 JSON 行
- **实际分支**: `_iter_event_records_locked` → `json.loads(stripped)` (line 1537) → 对截断行抛出 `json.JSONDecodeError`（`ValueError` 子类）→ 未捕获 → 传播到调用方
- **预期行为**: JSONL 读取出错时应跳过损坏行、记录 WARN 并继续读取后续可解析行，或至少不阻塞后续 write 路径
- **实际行为**: `json.JSONDecodeError` 从 `_iter_event_records_locked` 向上传播到 `_last_event_sequence_locked` (line 1511) 和 `read_job_events` (line 1454)，两者均无 try/except。`_last_event_sequence_locked` 被 `append_job_event` (line 1399) 调用，异常通过 `_emit_progress_event` 和 `_append_job_event_warn` 的 `except Exception` 捕获（event 写入静默失败），但后续对同一 job 的**所有** `append_job_event` 和 `read_job_events` 调用都会在 `_last_event_sequence_locked` 中再次遇到同一损坏行，进入静默失败循环——该 job 的 event sidecar 永久不可用。job record 本身不受影响（独立文件）
- **直接证据**: 
  - `ingestion_runtime.py:1537`: `payload = cast(JsonValue, json.loads(stripped))` — 无 try/except
  - `ingestion_runtime.py:1511`: `for record in self._iter_event_records_locked(event_path)` — 调用链中无异常处理
  - `ingestion_runtime.py:2970`: `_emit_progress_event` 的 `except Exception` 捕获—但仅跳过当前 event，不修复 sidecar
- **影响**: 单个 job 的 event sidecar 永久损坏后，UI 将无法通过 event stream 观察该 job 进展；Service 层依靠 `read_job` 的 terminal fallback 仍能正常收口（state truth 不受影响），但用户失去中间进度可见性。恢复需要手动删除 `.events.jsonl` 文件
- **建议改法和验证点**: 
  1. `_iter_event_records_locked` 中用 try/except 包裹 `json.loads`，损坏行记录 WARN 并跳过
  2. 或引入 JSONL 写入的事务性：先写 tmp 文件，成功后再 rename（类似 `_write_record_locked` 的原子替换模式）
- **修复风险（低）**: 跳过损坏行意味着永久丢失该行 event，但被跳过的是已损坏数据；原子写入模式需要处理已有损坏 sidecar 的迁移
- **严重程度（中低）**: 触发条件罕见（crash/disk-full 时恰好截断 JSONL）；job record 不受影响、终态收口正确；但事件可观测性丢失

### 2-PASS-WITH-FINDINGS-低-CLI 层 synthetic terminal fallback 集成测试缺失

- **入口/函数**: `dayu/cli/commands/fins.py:_consume_fins_direct_events` (line 597)
- **文件(行号)**: `tests/cli/test_fins_commands.py:360-382`
- **输入场景**: 当 event sidecar 缺失 terminal event 但 job record 已终端时（如 runtime 写入 terminal event 失败、event sidecar 文件损坏），Service 层在 `stream_job_events_until_terminal` (fins_direct.py:624-628) 合成一个 `event_label="job_terminal_fallback"` 的 terminal event，并 yield 给 CLI 消费方
- **实际分支**: Service 层的 synthetic terminal event 通过 `render_fins_direct_event` (output.py:143-200) 进入 `if terminal_result.status is FinsIngestionJobStatus.SUCCEEDED/CANCELLED` 或 fallthrough FAILED 分支（output.py:170/181/188）
- **预期行为**: CLI 渲染应该正确处理合成 terminal event，错误/成功/取消三类终态都能正确走 stdout/stderr 并返回正确退出码
- **实际行为**: Service 层测试 (`test_stream_job_events_synthesizes_terminal_after_missing_terminal_event`, test_fins_direct.py:537) 已覆盖合成逻辑。但 CLI 层 `test_live_fins_commands_render_progress_and_terminal_summary` 仅使用 `SUCCEEDED` terminal status，未验证 synthetic event 的渲染行为，也未覆盖 FAILED/CANCELLED synthetic terminal 路径
- **直接证据**: `tests/cli/test_fins_commands.py:360` — 所有 6 个 parametrized 命令仅验证 progress + succeeded summary 的 stdout 输出，`fake_service.terminal_status` 仅使用 `SUCCEEDED`
- **影响**: 如果合成 terminal event 的 `terminal_result` 结构在某些边界条件下与真实 terminal event 不同（例如 `result_summary` 或 `failure_summary` 为空但渲染代码期望非空），可能导致静默失败或错误的渲染输出，但由于 Service 层已严格测试合成逻辑且 `FinsDirectTerminalResult` 是 frozen dataclass，风险较低
- **建议改法和验证点**: 在 `test_live_fins_commands_render_progress_and_terminal_summary` 或其对应 fixture 中增加一个 parametrized case，让 fake service 的 `stream_job_events_until_terminal` 返回合成 terminal event（`event_label="job_terminal_fallback"`），或至少增加 FAILED terminal 的渲染验证
- **修复风险（低）**:
- **严重程度（低）**:

### 3-PASS-WITH-FINDINGS-低-`_is_summary_key_allowed` 子串匹配过度宽泛

- **入口/函数**: `dayu/cli/output.py:_is_summary_key_allowed` (line 312)
- **文件(行号)**: `dayu/cli/output.py:312-323`
- **输入场景**: 业务 payload 中包含 key 如 `withdrawal_count`、`nobody_checked`、`contentment_score` 等，key 的某段恰好包含敏感子串
- **实际分支**: `any(part in lowered for part in _FINS_SENSITIVE_KEY_PARTS)` 使用 Python 字符串 `in` 操作符做子串匹配
- **预期行为**: 只应屏蔽 key 本身是敏感字段或以已知敏感前缀命名的字段（如 `file_path`、`raw_data`）；不影响包含敏感词子串但不相关的业务 key
- **实际行为**: `"raw" in "withdrawal"` → `True`，导致 `withdrawal_count` 被屏蔽；`"body" in "nobody_checked"` → `True`；`"path" in "filepath_timestamp"` → `True`
- **直接证据**: `_FINS_SENSITIVE_KEY_PARTS = ("payload", "raw", "body", "content", "path")` (line 261-267)，`return not any(part in lowered for part in _FINS_SENSITIVE_KEY_PARTS)` (line 323)
- **影响**: 部分合法业务字段在 UI 终端摘要行中不显示，降低用户可见信息量。不涉及数据安全风险（是过度屏蔽而不是泄漏），但可能造成诊断困难
- **建议改法和验证点**: 将子串匹配改为更精确的匹配方式，例如：
  1. 使用词边界或前缀匹配 —— `lowered.startswith(part)` 或 `lowered == part` 按具体场景选择
  2. 或保留当前宽匹配，在 docstring 中注明这是有意偏保守的屏蔽策略
  3. 增加对 "message" 以外的常规业务 key（如 counter、summary、count、total 等后缀）的精细化判断
- **修复风险（低）**: 任何修改都需要审计当前所有 event payload key 的使用，确保不引入敏感信息泄漏
- **严重程度（低）**:

### 4-PASS-WITH-FINDINGS-低-`_LOGGER` 类型注解不一致

- **入口/函数**: 模块级常量
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:79`
- **输入场景**: 静态类型检查或人类读者对比各模块 `_LOGGER` 声明
- **实际分支**: 不适用（类型注解问题，无运行时影响）
- **预期行为**: 所有 `_LOGGER` 声明应统一使用 `Final[logging.Logger]`，防止意外重新赋值
- **实际行为**: `ingestion_runtime.py:79` 声明为 `_LOGGER: logging.Logger = logging.getLogger(__name__)`（缺少 `Final`），而 `fins.py:80`、`fins_direct.py:43` 均声明为 `_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)`
- **直接证据**: 
  - `ingestion_runtime.py:79`: `_LOGGER: logging.Logger = logging.getLogger(__name__)`
  - `fins.py:80`: `_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)`
  - `fins_direct.py:43`: `_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)`
- **影响**: 无运行时影响；pyright 对模块级常量的重新赋值检测差异极小；仅影响代码一致性和可读性
- **建议改法和验证点**: 将 `ingestion_runtime.py:79` 的 `_LOGGER` 声明改为 `_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)`
- **修复风险（低）**:
- **严重程度（低）**:

### 5-PASS-WITH-FINDINGS-低-`request_cancel` 为同步调用，在 SIGINT handler 路径上可能阻塞 event loop

- **入口/函数**: `dayu/cli/commands/fins.py:_wait_for_terminal_handling_sigint` (line 584)
- **文件(行号)**: `dayu/cli/commands/fins.py:578-584`
- **输入场景**: 用户第一次 Ctrl+C 触发 `sigint_task.done()`，在 event loop 的 coroutine 内同步调用 `service.request_cancel(handle.job_id)`
- **实际分支**: SIGINT 到达 → `sigint_task.done()` → `cancel_requested=False` 分支 → `service.request_cancel(handle.job_id)` (line 584)
- **预期行为**: cancel request 应快速完成（job store 的 file lock + 原子写入），不会长时间阻塞
- **实际行为**: `FinsDirectCommandService.request_cancel` → `self._runtime.request_cancel(job_id)` → `FsFinsIngestionJobStore.request_cancel`，后者需要获取全局 file lock、读写 job record 文件、fsync 目录。在磁盘 I/O 拥塞、NFS 延迟或 file lock 竞争严重时，此同步调用可能阻塞 event loop 数秒，导致第二次 SIGINT 无法被 event loop 处理
- **直接证据**: 
  - `fins.py:584`: `service.request_cancel(handle.job_id)` — 在 coroutine 内直接同步调用
  - `ingestion_runtime.py:1869-1892`: `FinsIngestionRuntime.request_cancel` → `self.job_store.request_cancel(job_id, updated_at=_utc_now())`
  - `ingestion_runtime.py:1345-1373`: `FsFinsIngestionJobStore.request_cancel` — 获取 `file_lock`、读写 record、`_write_record_locked`（含 `os.fsync`）、`_fsync_directory`
- **影响**: 在极端 I/O 延迟场景下，第一次 SIGINT 后的 cancel 可能阻塞 event loop，用户即便按第二次 Ctrl+C 也无法本地退出（默认 SIGINT handler 已被 `_FinsSigintMonitor` 替换为 `notify()`，而 `notify()` 依赖 event loop 处理信号）。如果 I/O 永久阻塞（如 NFS hard mount hang），进程可能无法正常退出
- **建议改法和验证点**: 
  1. 将 `request_cancel` 包装为 `loop.run_in_executor(None, service.request_cancel, handle.job_id)` 在单独线程中执行，避免阻塞 event loop
  2. 或增加 request_cancel 的超时保护
  3. 或在 `_FinsSigintMonitor` 中保留默认 SIGINT 行为作为 fallback（当 event loop 被阻塞时，第二次 SIGINT 仍能触发 KeyboardInterrupt）
- **修复风险（中）**: `run_in_executor` 引入 threading 需要考虑 job store 的线程安全性（当前 `file_lock` 已跨线程安全）
- **严重程度（低）**: 仅在极端 I/O 延迟场景下可触发；正常本地文件系统下 `request_cancel` 在毫秒级完成

### 6-PASS-WITH-FINDINGS-低-`claim_running_or_cancelled` 未验证当前状态为 QUEUED

- **入口/函数**: `dayu/fins/ingestion_runtime.py:claim_running_or_cancelled` (line 1279)
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1279-1324`
- **输入场景**: executor 对同一 job 重复提交后台任务（buggy caller），`_mark_job_running_or_cancelled` 被调用两次
- **实际分支**: 第一次调用：QUEUED → RUNNING（line 1317-1324）；第二次调用：`record.status not in _TERMINAL_STATUSES`（RUNNING 不是终态）→ 再次执行 `replace(record, status=RUNNING, started_at=record.started_at or started_at, updated_at=updated_at)`（line 1317-1324），**覆盖** `started_at` 和 `updated_at`
- **预期行为**: RUNNING 状态应该幂等——重复 claim 不应修改已持久化的 `started_at` 和 `updated_at`
- **实际行为**: `started_at` 被保留（`record.started_at or started_at` — 如果已有值则不变），但 `updated_at` 被无条件覆盖为新的时间戳。不产生状态错误（仍是 RUNNING），但丢失首次 claim 的精确时间记录
- **直接证据**: `ingestion_runtime.py:1305-1324` — guard 仅检查 `in _TERMINAL_STATUSES`（line 1305），不区分 QUEUED/RUNNING/CANCELLING
- **影响**: 低。正常流程中 `_start_lock` + 单次 `executor.submit` 保证不会重复调用。仅在代码演进中 executor 实现出错时才可能触发
- **建议改法和验证点**: 增加断言或显式检查 `record.status is FinsIngestionJobStatus.QUEUED`，在 RUNNING/CANCELLING 状态下直接返回原 record
- **修复风险（低）**:
- **严重程度（低）**:

### 7-PASS-WITH-FINDINGS-低-`_last_event_sequence_locked` 每次 append 扫描全文件

- **入口/函数**: `dayu/fins/ingestion_runtime.py:append_job_event` (line 1375) → `_last_event_sequence_locked` (line 1494)
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1494-1515`
- **输入场景**: 长时间运行的 preprocess job 产生数百个 progress event 后，每次追加新 event 仍需扫描整个 JSONL 文件以找到最后 sequence
- **实际分支**: `append_job_event` (line 1375) → `sequence = self._last_event_sequence_locked(event_path) + 1` (line 1399)
- **预期行为**: event sidecar 应当高效追加（O(1)）
- **实际行为**: `_last_event_sequence_locked` 调用 `_iter_event_records_locked` 打开 JSONL 文件、逐行解析 JSON、收集全部 record 到 list（line 1531-1541），每行都 JSON 反序列化，最后返回最后一条 sequence。对于有 N 条 event 的 sidecar，每次 append 是 O(N)
- **直接证据**: 
  - `ingestion_runtime.py:1511`: `for record in self._iter_event_records_locked(event_path)` — 遍历全部 event record
  - `ingestion_runtime.py:1531-1541`: `_iter_event_records_locked` 把整个 JSONL 读入 list 再转 tuple
- **影响**: 对于单 job 内 event 数较大的场景（如批量 preprocess 50 个文档、每个文档有 3-4 个 progress event = 150-200 条），每次 append 的 O(N) 扫描不会成为瓶颈（200 条 × ~4KB/条 = 800KB，扫描耗时 < 1ms）。但 `_iter_event_records_locked` 同时把全文件解析到内存 list 中，随 event 累积内存压力线性增长。当前上限为 `_MAX_JOB_EVENT_READ_LIMIT=1000` 条读取限制，但 sidecar 写入无上限
- **建议改法和验证点**: 
  1. 用 `_last_event_sequence_locked` 改为只读最后一行的轻量方案（反向 seek 从文件尾读一行）
  2. 或在 `FsFinsIngestionJobStore` 中维护内存 last sequence cache（每次 append 后更新）
  3. 或在 job record 中维护 `last_event_sequence` 字段，append 时读取并递增，避免扫描 sidecar
- **修复风险（低）**: 反向 seek 读最后一行在 JSONL 格式下可行，需处理空行尾和文件不存在的情况
- **严重程度（低）**: 当前 job 的 event 数在合理范围内不会成为瓶颈；未来若支持数千条精细 progress event 则需关注

### 8-PASS-WITH-FINDINGS-低-`FINS_DIRECT_SERVICE_FACTORY` 模块级可变全局状态

- **入口/函数**: `dayu/cli/commands/fins.py:FINS_DIRECT_SERVICE_FACTORY` (line 177)
- **文件(行号)**: `dayu/cli/commands/fins.py:176-179`
- **输入场景**: 多个测试或调用方同时修改 `FINS_DIRECT_SERVICE_FACTORY` 全局变量
- **实际分支**: 不适用（设计选择，非运行时 bug）
- **预期行为**: 测试可以注入 mock service factory
- **实际行为**: `FINS_DIRECT_SERVICE_FACTORY` 是模块级可变变量，任何 import 该模块的代码可以随时修改它。在当前 CLI 单进程、单线程环境中无实际问题，但违反了不可变性最佳实践
- **直接证据**: `fins.py:176-179`:
  ```python
  FinsDirectServiceFactory = Callable[[Path], FinsDirectCommandService]
  FINS_DIRECT_SERVICE_FACTORY: FinsDirectServiceFactory = (
      FinsDirectCommandService.from_workspace_root
  )
  ```
- **影响**: CLI 测试中 `monkeypatch.setattr` 会在测试结束时自动恢复，不存在残留风险。若未来 `run_fins_direct_command` 被多线程并发调用，存在竞态条件
- **建议改法和验证点**: 当前实现已满足 CLI 使用场景。若未来需要并发安全，将 factory 作为参数传入而非模块级全局。无需立即修改
- **修复风险（低）**:
- **严重程度（低）**:

---

## Architecture & Layering 检查（无 finding）

以下关键架构约束均已验证通过：

| 约束 | 现状 |
|------|------|
| `dayu.runtime.log` 不 import `dayu.engine/host/service/ui/fins` | ✅ 通过 — 仅依赖 stdlib `logging`/`sys` 与 `dayu.runtime.log_levels`（纯常量模块） |
| `dayu.fins.ingestion_runtime` 不泄漏 Host/Engine 内部 | ✅ 通过 — 不 import Host EventLog、Engine stream、tool provider 或 CLI |
| `dayu.service.fins_direct` 通过 Protocol 抽象 runtime | ✅ 通过 — `FinsDirectIngestionRuntime` Protocol 定义清晰的 6 方法边界；`DefaultFinsRuntime` 通过 `get_ingestion_runtime()` 剥离后符合协议 |
| CLI 不直接 import Fins storage | ✅ 通过 — `tests/cli/test_fins_commands.py:1012` 已验证 |
| UI(log) 分离：render 写 stdout/stderr，logging 走 VERBOSE/DEBUG | ✅ 通过 — `test_fins_direct_default_log_does_not_pollute_progress_output` 已验证默认 level 下 VERBOSE 日志不污染 stdout |
| 输出净化路径脱敏 | ✅ 通过 — 绝对路径（Unix/Windows）在 `_safe_text_value` 中脱敏，消息通过 `_failure_message_or_fallback` 安全截断 |
| LLM-facing 文本自足性（README） | ✅ 通过 — README 中 internal terms（sequence/cursor/event sidecar）均在上下文中自解释，不依赖隐式规则；README 是开发者文档，不进入 LLM context |

---

## State Machine Correctness（无 finding）

`FinsIngestionJobStatus` 状态机验证：

- **终态吸收**: `_TERMINAL_STATUSES = {SUCCEEDED, FAILED, CANCELLED}` — 所有 `save_*_or_cancelled` 方法对已终态 record 返回原值（幂等）
- **CANCELLING → CANCELLED**: `claim_running_or_cancelled`/`save_succeeded_or_cancelled`/`save_failed_or_cancelled_if_active` 均在持锁状态下原子检查 `cancellation_requested or CANCELLING`，统一转为 `CANCELLED`
- **终态不可回退**: 无代码路径允许 CANCELLED/SUCCEEDED/FAILED → QUEUED/RUNNING 的逆向转换
- **并发安全**: 全局 `file_lock` 序列化所有 job record 与 event 写入，`save_succeeded_or_cancelled` 先读后写在线程安全锁保护下
- **Event sidecar 与 record 时序**: terminal event 在 record 已保存为终态后写入（`_append_terminal_job_event_warn` 在 `save_*` 之后调用），event append 失败不影响 record 终态
- **状态观察 vs 真源一致性**: `is_status_transition_job_event` vs `is_observation_job_event` 清晰二分：`JOB_QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED` 是状态转换观察，`PROGRESS/CANCEL_REQUESTED` 仅是观察信号；job record 始终是状态真源

## Cancel Semantics（无 finding）

完整 cancel 链路验证：

1. **CLI SIGINT → durable cancel**: `_FinsSigintMonitor.notify()` → `_wait_for_terminal_handling_sigint` → `service.request_cancel(handle.job_id)` → `FsFinsIngestionJobStore.request_cancel` (持锁写 `CANCELLING` + `cancellation_requested=True`)
2. **第一次 SIGINT**: 调用 `request_cancel`、打印 "Fins job cancel requested: {job_id}" 到 stderr、继续等待 terminal
3. **第二次 SIGINT**: 取消 event_task、打印 "Fins job cancel already requested; local process exiting: {job_id}" 到 stderr、返回 `None` → `EXIT_KEYBOARD_INTERRUPT`
4. **Job 在 cancel 前已终态**: `request_cancel` 在 store 层检查 `record.status in _TERMINAL_STATUSES` → 原样返回 → 不 emit `CANCEL_REQUESTED` event → CLI 终态渲染照常执行
5. **Durable cancel 后的 background job 收口**: `_RuntimeJobCancellationChecker` → 后台 job 检查到取消 → 调用 `save_failed_or_cancelled_if_active` → 原子转为 `CANCELLED` → 写入 `JOB_CANCELLED` terminal event
6. **Event sidecar 中的 cancel 时序**: `CANCEL_REQUESTED`（观察信号）+ `JOB_CANCELLED`（状态转换）= 完整的 event sidecar 记录

## Terminal Fallback（无 finding）

`stream_job_events_until_terminal` 的 terminal fallback 逻辑验证：

- **触发条件**: `read_job_events` 返回空 → sleep → `read_job` 发现 record 已终端 → terminal event sidecar 缺失
- **WARN 日志**: `"Fins direct job terminal record observed without terminal event; ... reason=missing_terminal_event"` (fins_direct.py:617-623)
- **合成 event**: `FinsDirectJobEvent(event_label="job_terminal_fallback", sequence=cursor+1, terminal_result=<从 record 构造>)` (fins_direct.py:624-628)
- **cursor+1 语义正确**: `cursor` 是最后读取的 event sequence；若 sidecar 为空（cursor=0），合成 event 得 sequence=1；若已有 N 条 event（cursor=N），合成 event 得 sequence=N+1
- **窄竞态窗口**: terminal record 写入与 terminal event 写入在同一 `file_lock` 保护下，但 `read_job_events` 加锁读后释放，`read_job` 再加锁读——之间可插入 event append。此窗口由 `return` 后的 WARN 覆盖，不产生错误行为

---

## Event Sidecar Sequence / Read（无 finding）

- **单调递增**: `append_job_event` 在 `file_lock` 下调用 `_last_event_sequence_locked` + 1，写入后 `os.fsync` + `_fsync_directory`。并发 append 由全局锁序列化，保证 monotonic sequence
- **游标读取**: `read_job_events(after_sequence=N)` 筛选 `record.sequence > N` 的事件，`after_sequence=0` 读取全部。游标由 `stream_job_events_until_terminal` 的 `cursor` 变量追踪，只在事件 yield 后更新
- **空 sidecar**: `_iter_event_records_locked` 对不存在的文件返回空 tuple；`read_job_events` 返回空 tuple；触发 terminal fallback
- **单事件写入耐久性**: `append_job_event` 中 `os.fsync(stream.fileno())` + `_fsync_directory(self.root_dir)` 保证 POSIX 耐久性
- **event payload 校验**: `validate_bounded_job_event_payload` 在 `_event_record_to_json` 中被调用（即每次 `append_job_event` 时调用），递归校验 JSON-compatible、非 NaN/Inf 浮点数、≤4096 bytes JSON 编码

---

## Tests & Residual Risk

### 测试覆盖总结

| 模块 | 测试数 | 覆盖领域 |
|------|--------|---------|
| `tests/runtime/test_log.py` | 19 | configure 幂等、root logger 隔离、VERBOSE 级别、caplog 契约、bounded_payload_keys |
| `tests/service/test_fins_direct.py` | 15 | typed request 构造、event stream、terminal fallback、异常传播、poll interval 校验、exit mapping |
| `tests/fins/test_fins_ingestion_runtime.py` | 53 | job lifecycle、event sidecar CRUD、cancel race、concurrent sequence、payload 校验、append failure 容错 |
| `tests/cli/test_fins_commands.py` | 20 | CLI→Service 参数映射、event 渲染、SIGINT 处理、路径脱敏、cancel failure 传播 |
| `tests/cli/test_arg_parsing.py` | 新增 | CLI arg parsing |
| `tests/cli/test_upload_filings_from_command.py` | 新增 | upload_filings_from 本地模式不启动 event stream |

**正向发现**:
- 测试质量高：state transition verification（断言确切事件序列）、cursor advancement verification、anti-leakage assertion（敏感内容不应出现在 event sidecar/job record/CLI 输出中）、duplicate-logging defense（monkeypatch logger.exception 验证 CLI 不重复 log）
- 并发测试使用真实 `file_lock`、`threading.Thread` 和 `monkeypatch` 注入竞态，不做 mock 假设

### Residual Risk

| 风险 | 严重程度 | 说明 |
|------|---------|------|
| CLI 层 synthetic terminal fallback 集成测试缺失 | 低 | Service 测试已覆盖；CLI 渲染对所有 `FinsDirectTerminalResult` 使用统一路径，渲染不会失败 |
| Event sequence gap 场景未测试 | 低 | 正常操作下 `file_lock` + 单调分配保证无 gap；唯一 gap 源是 sidecar 文件损坏，此时 read 返回 ValueError 向上传播（fail-fast） |
| UNC 路径和相对路径脱敏未覆盖 | 低 | 业务 payload 不包含文件路径（`validate_bounded_job_event_payload` 前置过滤 + `_is_summary_key_allowed` 屏蔽 "path" key）；唯一路径出现在已解析的绝对路径上下文中 |
| Event sidecar 写入无上限 | 低 | 每个 job 内 event 数量受 `_MAX_PREPROCESS_DOCUMENTS=50` 等业务上限约束；写入速率受 daemon thread 单线程限制 |
| `_FinsSigintMonitor` 依赖 `asyncio.Event` 的线程安全性 | 低 | CPython 中 `asyncio.Event.set()` 从 signal handler 调用时通过 `call_soon_threadsafe` 安全桥接到 event loop |

---

## Open Questions

1. `stream_job_events_until_terminal` 是否需要在未来支持 `CancellationToken` 参数？当前 CLI 仅依赖 double-SIGINT 模式；若 Service 被其他非 CLI product entrypoint（如 Web API）复用，可能需要在 stream 层面直接接受取消信号而不依赖外层 task cancellation。当前设计的选择是合理的（Service 不拥有取消策略，由调用方通过 task lifecycle 管理），但应在 README 中记录此设计决策。

2. `_last_event_sequence_locked` 的 O(N) 行为是否需要优化？当前单 job event 数 < 1000 时无实际问题；若未来支持高达 10000+ event 的长时间 job，可考虑反向 seek 读取最后一行 JSONL 的轻量实现。

---

## Residual Risk

- 所有引用 severity 均为 **低**；无 CRITICAL、HIGH 或 MEDIUM 级别 finding
- pytest 207 passed, 3 warnings（均为非项目代码的 deprecation warning）；pyright 0 errors；git diff --check clean
- 所有关键架构约束、状态机正确性、取消语义、terminal fallback、event sidecar 和 UI/log 分离均已逐路径验证通过
- 建议修复优先级：Finding 1（CLI synthetic fallback 集成测试）和 Finding 2（敏感 key 子串匹配）为最值得关注的改进项，其余均为代码质量微调
