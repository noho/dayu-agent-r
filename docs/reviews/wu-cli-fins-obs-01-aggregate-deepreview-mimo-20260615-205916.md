# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260615-205916.md`
- Included scope: WU-CLI-FINS-OBS-01 全部 6 个 Slice 的聚合审查，覆盖 `dayu/fins/ingestion_events.py`（新增）、`dayu/fins/ingestion_runtime.py`（event sidecar append/read、progress event emission、terminal event emission）、`dayu/service/fins_direct.py`（`stream_job_events_until_terminal`、`FinsDirectJobEvent`、terminal fallback）、`dayu/cli/output.py`（`render_fins_direct_event`、path redaction、summary 有界输出）、`dayu/cli/commands/fins.py`（event stream 消费、SIGINT cancel 重构）、`dayu/cli/main.py`（runtime log 装配）、`dayu/runtime/log.py`（`log_verbose`、`bounded_payload_keys`）、全部对应 tests、README 同步、控制文档
- Excluded scope: `docs/reviews/` 下的 S1–S6 历次 review 与 adjudication artifact（已作为参考阅读，不重复审查）；`docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`（plan 文档，非代码）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 审查记录

以下按审查维度记录走读结论：

**1. Event sidecar sequence / read / terminal fallback**

- `FsFinsIngestionJobStore.append_job_event` 在同一 file lock 内完成 `read_record_locked` → `_last_event_sequence_locked` → write JSONL → flush → fsync → fsync directory。sequence 单调递增由锁内 `_last_event_sequence_locked` 保证（`ingestion_runtime.py:1421–1449`）。
- `read_job_events` 同一 file lock 内读取，按 `after_sequence` 过滤并按 `limit` 截断（`ingestion_runtime.py:1451–1478`）。
- `stream_job_events_until_terminal` 的 terminal fallback 路径：empty read → sleep → `read_job` → 检查 `_is_terminal_status` → 合成 `sequence=cursor+1` 的 synthetic terminal event（`fins_direct.py:606–629`）。由于 empty read 已消费全部已有事件，`cursor+1` 不会与真实事件 sequence 冲突。
- `_append_job_event_warn` / `_emit_progress_event` 对 event append 失败只记录 bounded WARN，不回滚 job record（`ingestion_runtime.py:2892–3029`）。Service 层 terminal fallback 正是为此容错设计的。

**2. Cancel semantics**

- `request_cancel` 链路：CLI → `FinsDirectCommandService.request_cancel` → `runtime.request_cancel` → `job_store.request_cancel` + `CANCEL_REQUESTED` event append（`fins_direct.py:631–648`；`ingestion_runtime.py:1873–1891`）。
- CLI SIGINT 路径：第一次 SIGINT → `service.request_cancel` + `cancel_requested=True` + `render_fins_direct_cancel_requested`；第二次 SIGINT → `event_task.cancel()` + `render_fins_direct_local_exit_after_cancel` + return `EXIT_KEYBOARD_INTERRUPT`（`fins.py:554–594`）。
- `cancel_requested` 是 SIGINT handler 局部变量，不跨请求泄漏。
- Service cancel 失败向上传播，CLI 不重复记录 ERROR（测试 `test_cli_cancel_failure_propagates_without_duplicate_error_log` 覆盖）。

**3. UI / log separation**

- `render_fins_direct_event` 在 terminal_result 为 None 时输出 progress → stdout；SUCCEEDED → stdout；CANCELLED → stderr；FAILED → stderr（`output.py:140–200`）。
- runtime_log 使用 `logging.StreamHandler(stream=sys.stdout)`，与 UI print 共用 stdout；但默认 INFO 级别过滤 VERBOSE 日志，仅 `--verbose` / `--debug` 时输出日志行。测试 `test_fins_direct_default_log_does_not_pollute_progress_output` 和 `test_fins_direct_verbose_log_outputs_execution_skeleton` 分别验证默认与显式场景。
- `--debug` 时 event detail 日志包含 `sequence` 和 `payload_keys`（由 `bounded_payload_keys` 只暴露 key、不暴露 value），不包含 payload value。

**4. Runtime logging helper 分层**

- `log_verbose` 显式接收调用点 logger（`runtime/log.py:181–197`），不持有模块归属。调用点使用 `_LOGGER = logging.getLogger(__name__)` 保留模块身份。
- `bounded_payload_keys` 只返回排序且数量受限的 key 元组，不读取 value（`runtime/log.py:200–210`）。
- `dayu.runtime.log` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.fins`，符合架构约束。

**5. README / LLM-facing 语义**

- `dayu/README.md` 更新了 `dayu.service.fins_direct` 描述：新增 "event observation / poll terminal fallback" 语义。
- `dayu/fins/README.md` 更新了 public contract、事件流、ingestion job store 描述，明确 event sidecar 不属于 Host durable truth。
- `dayu/service/README.md` 更新了 `stream_job_events_until_terminal` 的文档说明。
- `tests/README.md` 同步更新了测试覆盖范围描述。
- 所有 README 更新与代码实现一致，无超前或遗漏。

**6. Tests**

- `test_fins_ingestion_runtime.py`：event sidecar append/read、sequence 单调递增、bounded payload、并发 sequence、append failure WARN-and-continue。
- `test_fins_direct.py`：stream 按 sequence 输出 progress + terminal、negative after_sequence fail fast、terminal record 不一致 raise、terminal event 后 read_job 失败透传、synthetic terminal fallback、empty read sleep 防 tight loop、event store failure 透传。
- `test_fins_commands.py`：六个 live command 的 progress/terminal summary 输出、默认日志不污染 progress、`--verbose` 执行骨架、`--debug` event detail、path redaction、Service stream/cancel failure 不重复 ERROR、SIGINT cancel 路径。
- `test_arg_parsing.py`：CLI main 的 runtime log 装配参数传递。
- `test_upload_filings_from_command.py`：upload_filings_from 不启动 live event stream。
- `test_log.py`：`log_verbose` 保留调用点 logger、`bounded_payload_keys` 只暴露 key。

**7. Architecture boundary**

- `ingestion_events.py` 是 Fins 自有 event 契约，不导入 Host / Engine / Service / UI。
- `ingestion_runtime.py` 的 event append/read 通过 `FinsIngestionJobStore` 协议隔离存储实现。
- `fins_direct.py` 通过 `FinsDirectIngestionRuntime` 协议依赖 runtime，不直接依赖 store 实现。
- CLI 通过 Service 投影的 `FinsDirectJobEvent` 消费事件，不直接 import `dayu.fins.storage` 或 `dayu.fins.ingestion_runtime`。

## Open Questions

无。

## Residual Risk

- Event sidecar JSONL 文件在极端高并发 progress 场景下（如 preprocess 处理数百文档），file lock 内的 `_last_event_sequence_locked` 需要逐行扫描全部已有事件以确定下一 sequence。当前设计通过 file lock 保证正确性，但未对 sidecar 文件大小设置上限。若单 job 产生数千条 progress event，读取性能可能退化。此为已知 deferred risk（Slice S1 review 已记录），当前 work unit 范围内不阻塞。
- `render_fins_direct_terminal_result` 被从 `output.py.__all__` 中移除并替换为 `render_fins_direct_event`，属于 breaking API change。当前 branch 内全部调用方已迁移；合并到 main 后若有外部调用方使用旧函数名，会触发 ImportError。此为有意设计，非遗漏。
