# WU-CLI-FINS-OBS-01 Fins Direct Live Events Plan

## Goal / Motivation / Success Signal

Work unit：`WU-CLI-FINS-OBS-01`

Gate：`plan`

目标：

- 为 Fins direct commands 恢复 live event stream，覆盖 `download`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material`。
- 审计 CLI command 的日志与 UI print 路径，至少覆盖 `init`、`prompt`、`interactive`、`download`、`upload_filing`、`upload_material`、`upload_filings_from`、`process`、`process_filing`、`process_material`。
- 在 Service / Fins boundary 提供可复用的 job event 消费接口，使 CLI 只是 UI consumer，未来 WeChat / GUI 可以复用 Service 能力。
- 恢复 CLI 日志装配，使 `--log-level`、`--debug`、`--verbose`、`--quiet` 符合 `dayu/README.md` 的日志级别语义。
- 保留 Fins direct cancel 语义：用户第一次中断后必须 durable `request_cancel(job_id)` 并继续观察终态；第二次中断或本地退出必须有明确、可测试的用户可见输出。

动机判断：

- 问题真实存在且严重性成立。当前 Fins direct CLI 已经变成“启动 job 后等待终态”，运行中没有 progress UI；CLI main 解析日志参数但不装配日志，导致 `--verbose` / `--debug` 对 Dayu 日志无效。
- 用户要求的修复路径需要被收敛，不能把 Fins direct job 改造成 Host Run，也不能把 prompt / interactive 的模型 token streaming 扩大为本条必做项。当前 root cause 是 Fins direct runtime 没有向 Service/CLI 暴露 job progress observation，以及 CLI 顶层日志装配缺失。

成功信号：

- 六个 Fins direct live job command 都通过同一个 Service/Fins job event 接口消费运行中事件，CLI 不直接调用底层 pipeline 或 storage。
- CLI 在运行中输出 progress，终态输出 result summary / failure / cancel；日志只承载诊断、执行骨架、错误上下文。
- `upload_filings_from` 仍只生成 batch script，不启动 live job；它被纳入 UI print / 日志装配审计。
- `init`、`prompt`、`interactive` 终态 UI 输出保持正常；本条不实现 prompt / interactive 模型 token/content streaming。
- 受影响 pytest 与 full pyright 通过；README 更新判断完成。

## Non-goals / Scope Boundary

- 不全量搬迁 OLD dayu-agent CLI 实现。
- 不把 Fins direct commands 改造成 Host run、Host wait 或 Host event stream。
- 不让 CLI、Service 或 Host 绕过 `dayu.fins.storage` 直接读取财报 storage。
- 不引入通用跨进程 event bus、WebSocket 框架或平台化观察者系统。
- 不修改 Engine stream 术语或 Engine public contract。
- 不恢复 write workflow 或旧 Fins workflow 全量实现。
- 不把 `upload_filings_from` 改造成 live job stream。
- 不把 prompt / interactive 模型 token/content streaming 纳入本条实现；只审计并保护其现有终态 UI 输出和日志装配。

## Design Document Alignment

- `docs/host/design.md` 固定 `UI -> Service -> Host -> Engine`：UI 负责展示、输入收集、流式订阅和用户动作触发；Service 负责业务入口、身份解析、场景装配和调用 Host。Fins direct command 不是 Host Run，本方案只在 Service/Fins boundary 增加 Fins job event 消费能力。
- `docs/engine/design.md` 固定 stream 术语边界：本方案中的 Fins direct live event stream 不是 `EngineEvent stream`、不是 `RunnerEvent stream`、不是 provider SSE stream、不是 `Host event stream`。
- `dayu/README.md` 固定日志职责：progress / result summary 是 UI 输出；诊断路径、执行骨架、错误上下文是日志。日志不得承担 EventLog、审计真源或 tool trace 职责，也不得输出 provider secret、完整业务 payload、财报原文或大段 tool result。
- Fins 文档存取继续只能通过 `dayu.fins.storage` 仓储协议；Service 和 CLI 只调用 `DefaultFinsRuntime` / `FinsIngestionRuntime` public boundary。

## First-principles Judgment and Direct Code Evidence

第一性原理判断：

- 用户可见 progress 属于 UI/Service 消费问题，不属于 Host/Engine 生命周期问题。Fins direct job 自身已有 durable job record 和 cancel command，因此应该在 Fins job store / runtime 附近记录 bounded job events，再由 Service 提供消费接口。
- 仅在 CLI 中轮询 `read_job()` 并合成状态文本不能形成可复用观察边界；这会让未来 WeChat / GUI 重复实现。当前 work unit 采用低风险 runtime-owned coarse progress，不在本轮强行改造同步 adapter 去消费 async pipeline stream。
- 引入通用 event bus 或 WebSocket 不成立。当前需求只要求本地 product entrypoint 消费 Fins job progress；workspace-scoped job event JSONL + Service 轮询订阅足够，且符合现有 filesystem job store 模型。
- prompt / interactive 当前已有 Host public watcher 与终态输出路径，但没有向 CLI 投影 content delta。把模型 token streaming 纳入本条会改变 Agent command UX 和 Host event 投影范围，超出本 work unit 的直接根因；本条只保护终态输出和日志装配。

直接代码证据：

- `dayu/cli/main.py:66-77` 只解析参数、查找 runner 并分发；没有调用 `dayu.runtime.log.configure(...)` 或等价装配。
- `dayu/cli/arg_parsing.py:276-312` 已解析 `--log-level`、`--debug`、`--verbose`、`--info`、`--quiet`，并把它们归一到 `args.log_level`。
- `dayu/runtime/log.py:95-174` 已提供 Dayu namespace 日志装配和 CLI 风格 level 解析；当前缺口是 CLI main 未调用。
- `dayu/service/fins_direct.py:448-460` 的 `wait_for_terminal()` 只轮询 `read_job()` 到终态，不提供运行中事件。
- `dayu/cli/commands/fins.py:220-229` 启动 direct job 后只等待 terminal；`dayu/cli/commands/fins.py:525-571` 的 SIGINT 路径围绕 terminal wait task 处理 cancel。
- `dayu/cli/output.py:120-153` 当前只输出 Fins terminal result，不输出 progress 或 result summary 明细。
- `dayu/cli/commands/fins.py:232-270` 的 `upload_filings_from` 只生成并打印/写入 batch script，不启动 Fins job。
- `dayu/fins/ingestion_runtime.py:1415-1577` 创建 durable queued job 后提交后台 thread；`read_job()` / `request_cancel()` 是 Fins job public boundary。
- `dayu/fins/ingestion_runtime.py:1703-1792` 后台 download/upload 只聚合 summary 并写 terminal record，运行中 pipeline events 没有进入 direct job 消费路径。
- `dayu/fins/pipelines/download_events.py`、`upload_filing_events.py`、`upload_material_events.py` 已定义 pipeline event models；`dayu/fins/pipelines/sec_pipeline.py` 与 `cn_pipeline.py` 已有 `download_stream`、`upload_filing_stream`、`upload_material_stream`。这些 async stream 可作为后续细粒度进度来源，本 work unit 不要求同步 adapter 消费它们。
- `tests/service/test_fins_direct.py`、`tests/cli/test_fins_commands.py` 已覆盖启动、终态、cancel，但没有 live event 消费断言。

## Affected Files / Modules

实现阶段允许修改的生产代码：

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- 可新增 `dayu/fins/ingestion_events.py`，用于放置 Fins job event dataclass / enum / bounded payload helper，避免继续膨胀 `ingestion_runtime.py`。
- `dayu/service/fins_direct.py`
- `dayu/cli/main.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/output.py`

实现阶段允许修改的测试：

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/service/test_fins_direct.py`
- `tests/cli/test_fins_commands.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_init_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_upload_filings_from_command.py`
- 本轮不要求更新 pipeline stream 既有测试，除非 implementation 发现无需协议变更且能安全复用已有同步桥接来消费 async stream；该情况必须先用测试证明不破坏同步 adapter/runner 边界。

实现阶段按 README 触发规则检查并按需修改：

- `dayu/README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `dayu/service/README.md` 也会被 `dayu/service/` 修改触发，应检查；本 plan 的必填 docs decision 在下文单列用户点名的三份 README。

不允许修改：

- `docs/host/design.md`
- `docs/engine/design.md`
- `docs/host/issues-implementation-control.md`
- review artifact、commit、push、PR。

## Contract / Schema / State-machine / Public-interface Changes

Fins job event schema：

- 新增 Fins 自有 job event record，不属于 Host durable schema，不属于 Engine contract。
- 建议新增 `FinsIngestionJobEventType`。可以使用单个 enum，但必须用中文 docstring 或 helper 明确区分 status transition events 与 observation/progress events：
  - `JOB_QUEUED`
  - `JOB_RUNNING`
  - `PROGRESS`
  - `CANCEL_REQUESTED`
  - `JOB_SUCCEEDED`
  - `JOB_FAILED`
  - `JOB_CANCELLED`
- status transition events：`JOB_QUEUED`、`JOB_RUNNING`、`JOB_SUCCEEDED`、`JOB_FAILED`、`JOB_CANCELLED`，只表示 job record 状态已发生对应转换；状态真源仍是 terminal job record，不是 event sidecar。
- observation/progress events：`PROGRESS`、`CANCEL_REQUESTED`，只表示用户可见观察信号或 cancel 请求观察信号，不推进 job state；`CANCEL_REQUESTED` 的 durable truth 仍是 job record 的 `cancellation_requested` / `CANCELLING`。
- 建议新增 `FinsIngestionJobEventRecord`：
  - `job_id: str`
  - `sequence: int`
  - `operation_kind: FinsIngestionOperationKind`
  - `status: FinsIngestionJobStatus | None`
  - `event_type: FinsIngestionJobEventType`
  - `source_event_type: str | None`
  - `source_kind: SourceKind | None`
  - `document_id: str | None`
  - `message: str`
  - `payload: dict[str, JsonValue]`
  - `emitted_at: str`
- 建议新增 `FinsIngestionJobEventAppend`，由 runtime / adapter 提供无 `sequence` 的 append input；`FsFinsIngestionJobStore` 在同一 file lock 下分配单调递增 `sequence`。
- 事件持久化建议使用 sidecar JSONL：`.dayu/fins_ingestion/jobs/<job_id>.events.jsonl`。不嵌入 job record，避免让 job terminal summary 变成 growing payload。
- event sidecar append/read sequence allocation 必须使用 `FsFinsIngestionJobStore` 已有同一把 runtime file lock，与 job record operations 共享锁保护。除非 implementation 以并发测试证明更窄锁不会导致 sequence race、terminal/event race 或 read-after-terminal gap，否则不得引入独立 sidecar lock。
- schema 按全新 job event schema 起库处理；不写旧 event 文件兼容读取。对没有 event sidecar 的新测试 job，Service 可以通过 `read_job()` synthesize terminal event 防止等待悬挂，但这不是旧库迁移兼容。

Fins runtime public interface：

- `FinsIngestionJobStore` 增加：
  - `append_job_event(job_id: str, event: FinsIngestionJobEventAppend) -> FinsIngestionJobEventRecord`
  - `read_job_events(job_id: str, *, after_sequence: int, limit: int) -> tuple[FinsIngestionJobEventRecord, ...]`
- `FinsIngestionRuntime` 增加：
  - `read_job_events(job_id: str, *, after_sequence: int = 0, limit: int = 100) -> tuple[FinsIngestionJobEventRecord, ...]`
- 本 work unit 不修改 `FinsSourceDownloadAdapter.download(...)` protocol，不新增必填 `event_sink` 参数。
- 本 work unit 不修改 `FinsUploadRunner.run_upload(...)` protocol，不新增必填 `event_sink` 参数。
- 细粒度 async pipeline stream consumption deferred 到后续 work unit。例外：若 implementation 发现无需协议变更、无需改造 executor、且能安全复用现有同步桥接消费 async stream，则必须先用测试证明不会破坏同步 adapter/runner 边界，再作为本轮内部优化落地。

Service public interface：

- `FinsDirectIngestionRuntime` protocol 增加 `read_job_events(...)`。
- 新增 Service-facing event dataclass，例如 `FinsDirectJobEvent`：
  - `job_id: str`
  - `sequence: int`
  - `command_name: str`
  - `ticker: str`
  - `status: FinsIngestionJobStatus | None`
  - `event_label: str`
  - `message: str`
  - `payload: Mapping[str, JsonValue]`
  - `terminal_result: FinsDirectTerminalResult | None`
- `FinsDirectCommandService.stream_job_events_until_terminal(handle: FinsDirectJobHandle, *, after_sequence: int = 0) -> AsyncIterator[FinsDirectJobEvent]`
- 保留 `wait_for_terminal(job_id)`，但实现可以复用事件接口或继续作为非 UI fallback。

CLI interface：

- 不新增 CLI flag。
- 既有 `--log-level` / `--debug` / `--verbose` / `--quiet` 语义生效。
- Fins direct command 的 stdout/stderr 行为明确：
  - progress 与 success summary 输出到 stdout；
  - failure、cancel、本地退出提示输出到 stderr；
  - debug/verbose 诊断日志由 `dayu.runtime.log` handler 输出，默认不淹没 progress。

State machine：

- Fins job 状态仍为 `QUEUED -> RUNNING -> SUCCEEDED/FAILED/CANCELLED`，`request_cancel` 将 active job 推到 `CANCELLING` 并设置 `cancellation_requested=True`。
- Event sequence 是 per-job 递增游标，不是业务事实，不替代 job record 状态真源。
- `CANCEL_REQUESTED` event 是观察信号；durable cancel truth 仍是 job record 的 `cancellation_requested` / `CANCELLING`。

无变更：

- Host public contract、Host durable schema、Host EventLog、Engine public contract、Engine stream 术语均不变。
- LLM-facing prompt / tool schema 不变。

## Implementation Decisions

1. Service / Fins boundary 采用 Fins job event sidecar + polling async iterator。
   原因：匹配现有 filesystem job store 和 CLI 本地流程，可被未来 GUI / WeChat 复用；不引入跨进程 bus 或平台化 observer；也不要求 CLI 直接知道 pipeline。

2. Fins runtime 是事件产生和持久化 owner，Service 是消费和投影 owner，CLI 是 UI renderer。
   CLI 不直接读取 job event JSONL，不 import Fins storage，不调用 pipeline stream。

3. 本轮采用 runtime-owned coarse progress，不改 adapter protocol。
   `FinsIngestionRuntime` 在现有同步 adapter/runner 调用前后 emit download/upload coarse progress，并在 preprocess 现有循环内按选中文档、单文档开始、processed/skipped/failed/not_supported、完成 emit bounded progress。download/upload 现有 async pipeline stream 的细粒度事件消费 deferred 到后续 work unit，除非 implementation 证明无需协议变更且能安全复用已有同步桥接。

4. Progress event payload 必须 bounded 且业务可读。
   不写完整文件路径、财报原文、provider raw payload、大段 tool result。文件只允许用 basename 或 count；document id 可作为业务进度锚点。

5. CLI 日志装配在 `dayu/cli/main.py` 完成。
   main 是顶层入口，能保证所有 scoped commands 一致生效。main 必须调用已有 `dayu.runtime.log.set_level_from_flags(...)`，不手写 log-level precedence 映射。命令模块只使用 stdlib logger，不直接配置 handler。

6. prompt / interactive 不纳入运行中 streaming。
   直接证据显示它们已通过 `dayu/cli/output.py` 输出终态 final answer / failure / cancel，Service entrypoint runtime 当前只等待 Host terminal 和 outbox fallback。模型 token/content streaming 是 Agent command UX 扩展，不是 Fins direct residual 的 root cause；本条只增加日志装配并用现有测试保护终态 UI。

7. `upload_filings_from` 不纳入 live job stream。
   该命令只生成 batch script；验收重点是 stdout script、`--output` 写入、错误输出和日志装配。

8. 当前方案没有过度设计。
   它只新增 workspace-scoped Fins job event sidecar、Fins runtime event sink、Service async iterator 和 CLI renderer；不引入通用 bus、WebSocket、跨平台 observer registry、Host/Engine schema 或 Agent streaming 扩展。

## Small Implementation Slices

### Slice S1: Fins Job Event Contract and Store

id/name：`S1-fins-job-event-contract`

objective：新增 Fins 自有 job event record、append/read store API，并在 job 创建、running claim、cancel request、terminal 保存时产生状态事件。

allowed files/modules：

- `dayu/fins/ingestion_events.py`
- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`

exact changes：

- 新增 `FinsIngestionJobEventType`、`FinsIngestionJobEventAppend`、`FinsIngestionJobEventRecord` 和 bounded payload 校验 helper。
- `FinsIngestionJobEventType` 的 docstring/helper 必须把 status transition events 与 observation/progress events 分类清楚；单 enum 可接受，但不得让 `PROGRESS` / `CANCEL_REQUESTED` 被实现为 job state transition。
- `FinsIngestionJobStore` protocol 增加 `append_job_event` / `read_job_events`。
- `FsFinsIngestionJobStore` 使用 `<job_id>.events.jsonl` sidecar 追加事件；append/read sequence allocation 使用与 job record operations 相同的 `RuntimeFileLock`，在该锁下读取最后 sequence 并写入下一条。不得默认引入独立 sidecar lock，除非以并发测试证明更窄锁安全。
- `FinsIngestionRuntime` 暴露 `read_job_events(...)`。
- 在 `_create_queued_record_with_start_lock` 后 append `JOB_QUEUED`。
- 在 `_mark_job_running_or_cancelled` 后按结果 append `JOB_RUNNING` 或 `JOB_CANCELLED`。
- 在 `request_cancel` 后若 active job 被标记 cancelling，append `CANCEL_REQUESTED`。
- 在 `_save_succeeded` / `_save_failed` / `_save_cancelled` 或等价 helper 后 append terminal event。

data flow：

`start_* -> create job record -> append JOB_QUEUED -> executor operation -> claim_running_or_cancelled -> append JOB_RUNNING -> terminal save -> append terminal event`

state transitions：

- event append 不改变 job status。
- job status 仍由 existing job record save methods 决定。
- event sequence 从 1 递增，`after_sequence=0` 读取全部。

error handling：

- event append payload 非 JSON-compatible 或超限时 fail fast，因为这是本地代码 bug。
- non-terminal progress / observation event append 失败不得导致 job failed；记录 bounded `WARN` 日志并继续执行业务路径。日志只能包含 job id、operation kind、event type、bounded payload keys/counts、异常类型和简短错误文本，不输出原文、绝对路径或 raw payload。
- terminal event append 失败不得回滚已经保存的 terminal job record；记录 bounded `WARN` 日志，Service terminal fallback 仍可通过 `read_job()` 结束等待。

tests/validation：

- 新增测试：创建 job 后可读取 `JOB_QUEUED`，执行后 sequence 单调递增。
- 新增测试：`request_cancel` 产生 `CANCEL_REQUESTED`，terminal cancel 产生 `JOB_CANCELLED`。
- 新增测试：event sidecar 不包含 workspace 绝对路径、完整文件路径、财报正文、raw provider payload。
- 新增测试：并发 append 或 terminal save/read 使用同一 store lock 后 sequence 不重复、不倒退。
- 新增测试：non-terminal progress event append 失败只产生 WARN，业务成功时 job 仍可 `SUCCEEDED`；terminal event append 失败产生 WARN 且不回滚 terminal job record。
- 更新 `_ClaimRaceJobStore` 或 fake store 以实现新增 protocol 方法。

completion signal：

- `tests/fins/test_fins_ingestion_runtime.py` 中 job event contract tests 通过。

stop condition：

- 如果发现 job event sidecar 会破坏现有 job store atomicity 或必须引入跨进程 bus 才能实现，停止并回到设计裁决。

### Slice S2: Wire Runtime-Owned Progress into Fins Ingestion Runtime

id/name：`S2-fins-runtime-progress-events`

objective：在不修改 adapter/runner protocol 的前提下，把 download/upload 同步调用边界和 preprocess runtime progress 映射为 bounded Fins job `PROGRESS` events。

allowed files/modules：

- `dayu/fins/ingestion_events.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- 默认不修改 `dayu/fins/pipelines/sec_pipeline.py`、`dayu/fins/pipelines/cn_pipeline.py` 或 pipeline stream tests。只有在无需 protocol 变更且测试证明现有同步桥接安全时，才允许把细粒度 stream consumption 作为本轮内部优化；否则 deferred。

exact changes：

- 新增 runtime 私有 progress helper，例如 `_emit_progress_event(record, source_event_type, message, document_id, payload) -> None`，内部调用 `FsFinsIngestionJobStore.append_job_event` 并执行 bounded WARN + continue 策略。
- 不修改 `FinsSourceDownloadAdapter.download(...)` 签名；不要求 `SecDownloadAdapter` / `CnDownloadAdapter` 消费 `download_stream(...)`。
- `_execute_download_request` 在调用现有同步 `adapter.download(request)` 前 emit download started，在返回 summary 后 emit download completed / completed with failures coarse progress。若现有 request/summary 已能提供 bounded counts/source/ticker 等字段，可加入 payload；不得输出原始路径或 filing 原文。
- 不修改 `FinsUploadRunner.run_upload(...)` 签名；不要求 `ProductionFinsUploadRunner` 消费 `upload_filing_stream(...)` / `upload_material_stream(...)`。
- `_run_upload_job` 在调用现有同步 `upload_runner.run_upload(...)` 前 emit upload started，在返回 summary 后 emit upload completed / completed with failures coarse progress。
- `_execute_preprocess_request` 在文档选择和每个文档处理结果处 emit progress。
- Fake adapters / fake upload runner 测试替身不因本轮 protocol 变更而更新；只按新增 runtime event store/read 能力补齐测试支撑。

data flow：

`FinsIngestionRuntime sync call boundary / preprocess loop -> private progress helper -> FsFinsIngestionJobStore.append_job_event -> Service poll -> CLI renderer`

state transitions：

- Progress event 不改变 job status。
- 若 cancellation checker 命中，后续状态仍由 existing cancel closeout 写 `CANCELLED`。
- adapter/runner protocol 保持同步；本 work unit 不改变 `FinsIngestionThreadExecutor` threading model，也不引入 event loop ownership 变更。

error handling：

- 单个 progress event 映射或写入失败不得使对应 job failed；这类事件是观测/UI 信号，不是业务 terminal truth。runtime 记录 bounded `WARN` 并继续执行业务路径。
- terminal job record 仍是业务状态真源。terminal event append 失败也只记录 bounded `WARN`，Service terminal fallback 仍可结束等待。
- cancellation checker 异常按现有路径写 failed/cancelled terminal。

tests/validation：

- download fake adapter / production adapter 同步调用边界能读到 started/completed coarse `PROGRESS` event。
- upload production runner 同步调用边界能读到 started/completed coarse `PROGRESS` event。
- preprocess 路径能读到 selected / document started / processed or skipped / completed events。
- event payload bounded，不含绝对路径或原文。
- progress event append failure 后，如果业务 adapter/runner 成功，job 仍按业务结果成功或失败，不因 progress 写入失败被强制 failed；测试必须断言 WARN 存在。

completion signal：

- Fins runtime live event tests 覆盖 download、preprocess、upload 三类 operation。

stop condition：

- 如果实现 coarse progress 都必须修改 adapter/runner protocol、改造 executor 或让 CLI 直接调用 pipeline，停止并报告 blocked；不得在本 work unit 引入该类重构。
- 细粒度 async pipeline stream consumption 只允许在无需协议变更、无需 executor 重构且已有同步桥接可安全复用并有测试证明时落地；否则 deferred 到后续 work unit。

### Slice S3: Service Fins Direct Event Subscription

id/name：`S3-service-fins-direct-subscription`

objective：在 `dayu.service.fins_direct` 暴露 reusable async event consumer，使 CLI / GUI / WeChat 可共享。

allowed files/modules：

- `dayu/service/fins_direct.py`
- `tests/service/test_fins_direct.py`

exact changes：

- `FinsDirectIngestionRuntime` protocol 增加 `read_job_events(...)`。
- 新增 `FinsDirectJobEvent` dataclass 和必要常量。
- 新增 `stream_job_events_until_terminal(handle, after_sequence=0)` async generator：
  - 轮询 runtime `read_job_events(handle.job_id, after_sequence=cursor, limit=100)`。
  - 每条 event 投影为 `FinsDirectJobEvent`，补入 `handle.start_request.command_name` 和 `ticker`。
  - 遇到 terminal job event 时附带 `FinsDirectTerminalResult` 并停止。
  - 若本轮 `read_job_events` empty，必须 `await asyncio.sleep(self.poll_interval_seconds)` 后再读，复用 `FinsDirectCommandService.poll_interval_seconds`，默认值与现有 `wait_for_terminal` 一致。
  - 若 `read_job()` 已 terminal 但尚未看到 terminal event，写一条 bounded `WARN` 日志后合成 terminal `FinsDirectJobEvent` 并停止，防止事件 sidecar 写入失败导致 UI 悬挂。
- `wait_for_terminal(job_id)` 保留原语义；可以继续轮询 job record，或内部复用 terminal fallback。

data flow：

`CLI handle -> service.stream_job_events_until_terminal(handle) -> runtime.read_job_events/read_job -> FinsDirectJobEvent`

state transitions：

- Service 不写 job state，只消费 event/job record。
- Terminal fallback 不改变 store。

error handling：

- `read_job_events` / `read_job` 抛错时向调用方抛出，CLI 将输出 error 并返回失败。
- 非法 poll interval 继续 fail fast。
- synthesized terminal fallback 必须 WARN，日志只包含 job id、terminal status 和 fallback 原因，不输出业务 payload。

tests/validation：

- service stream 按 sequence 输出 progress 并返回 terminal。
- service 在没有 terminal event 但 job record terminal 时合成 terminal，并产生 bounded WARN。
- service 在 empty read 后按 `poll_interval_seconds` sleep，测试证明没有 tight loop。
- service stream 对 unknown job / store failure 透传异常。
- `wait_for_terminal` 既有 exit mapping tests 保持通过。

completion signal：

- `tests/service/test_fins_direct.py` 覆盖新 event API，原有 terminal/cancel tests 通过。

stop condition：

- 如果 Service event API 需要 Host public API 或 Host EventLog 才能表达，应停止；这会违反 Fins direct 非目标。

### Slice S4: CLI Fins Event Consumer, UI Print, and Cancel Semantics

id/name：`S4-cli-fins-live-ui`

objective：让 Fins direct CLI command 消费 Service event stream，输出 progress / summary，同时保留 durable cancel 和二次中断本地退出语义。

allowed files/modules：

- `dayu/cli/commands/fins.py`
- `dayu/cli/output.py`
- `tests/cli/test_fins_commands.py`
- `tests/cli/test_upload_filings_from_command.py`

exact changes：

- 新增 `render_fins_direct_event(event: FinsDirectJobEvent, ...) -> None`：
  - progress/status 输出到 stdout；
  - failure/cancel terminal 输出到 stderr；
  - success terminal 输出到 stdout；
  - result summary 以 bounded `key=value` / 简短 JSON 行输出，不能输出原文、绝对路径或 raw payload。
- `_wait_for_terminal_handling_sigint` 改为等待一个 event-consumer task：
  - task 内 `async for event in service.stream_job_events_until_terminal(handle)`，逐条 render，遇到 terminal 返回 `terminal_result`。
  - 第一次 SIGINT 调用 `service.request_cancel(handle.job_id)`，立即 `render_fins_direct_cancel_requested(...)`，继续等 event-consumer terminal。
  - 第二次 SIGINT cancel event-consumer task，`render_fins_direct_local_exit_after_cancel(...)`，返回 `None`。
- CLI 不直接调用 `read_job_events`，只调用 Service stream。
- `upload_filings_from` 保持只生成 batch script；测试只确认脚本 stdout / `--output` / error stderr / 日志装配不被 live event 改动影响。

data flow：

`run_fins_direct_command -> start job -> service stream -> render progress -> terminal result -> exit code`

state transitions：

- CLI 不改变 job status，除 SIGINT 时调用 durable `request_cancel(job_id)`。
- 二次 SIGINT 只影响本地进程，不假装 job 已终态。

error handling：

- start 前 KeyboardInterrupt 仍返回 130 且不 durable cancel。
- start 后 event stream error 输出 CLI error 并返回 failure，除非已经由 SIGINT 二次本地退出。
- first SIGINT 后 `request_cancel` 失败则输出 error 并返回 failure，因为 durable cancel 未落盘。

tests/validation：

- 参数化测试六个 live Fins commands：fake service 产出 progress + terminal，CLI stdout 包含 progress 和 terminal summary。
- failed terminal 输出 stderr，exit code 为 failure。
- cancelled terminal 输出 stderr，exit code 为 130。
- 第一次 SIGINT 仍调用 `request_cancel(job_id)` 并继续等待 terminal。
- 第二次 SIGINT 输出本地退出提示，返回 130，且 cancel 只请求一次。
- `upload_filings_from` 不调用 event stream。

completion signal：

- `tests/cli/test_fins_commands.py` 和 `tests/cli/test_upload_filings_from_command.py` 覆盖 UI print 与 cancel 语义。

stop condition：

- 如果 fake service 需要暴露 Fins storage 或 pipeline 细节给 CLI 才能测试 progress，停止并修正 Service boundary。

### Slice S5: CLI Logging Assembly and Command UI/Log Audit

id/name：`S5-cli-log-assembly-and-audit`

objective：恢复 CLI 顶层日志装配，并完成所有 scoped commands 的 UI print / log 路径审计。

allowed files/modules：

- `dayu/cli/main.py`
- `dayu/cli/commands/fins.py`
- `dayu/service/fins_direct.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_init_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_fins_commands.py`
- `tests/cli/test_upload_filings_from_command.py`

exact changes：

- `dayu/cli/main.py` 在 `parse_cli_args(argv)` 成功后、runner 执行前调用 `dayu.runtime.log.set_level_from_flags(log_level=args.log_level, debug=..., verbose=..., info=..., quiet=...)`。
- main 不手写 `debug` / `verbose` / `quiet` / `--log-level` precedence 映射；log-level 解析与装配真源仍是 `dayu.runtime.log`。
- main 只导入 `dayu.runtime.log` 这个层中立装配入口；Engine 和业务层仍只用 stdlib logger。
- Fins CLI / Service 增加少量 stdlib logger：
  - VERBOSE：command start、job started、event received、terminal closeout、cancel requested。
  - DEBUG：event sequence、source event type、bounded payload keys/counts。
  - ERROR/WARN：Service stream failure、cancel request failure、render fallback。
- 不把 progress 写日志代替 UI print；不把诊断日志写成用户可见业务结果。
- 审计并记录测试结论：
  - `init`：已有 reset / success / usage / operation / copy failure UI 输出，补或更新测试确认日志装配不破坏。
  - `prompt`：终态 final answer / failure / cancel 仍通过 `dayu/cli/output.py` 输出；不新增 token streaming。
  - `interactive`：每轮终态输出与二次 SIGINT 本地退出保持。
  - Fins direct 六命令：progress + terminal summary。
  - `upload_filings_from`：脚本 stdout / `--output` 写入；不 live stream。

data flow：

`parse_cli_args -> configure dayu logger -> runner -> UI print via output helpers + diagnostics via logging`

state transitions：

- 无状态机变更。

error handling：

- 如果日志 level 字符串非法，理论上 argparse 已拦截；`set_level_from_flags` 仍 fail fast 并返回 failure 或 usage error，测试锁定。
- 日志装配不得吞掉命令异常。

tests/validation：

- CLI main 测试 monkeypatch `dayu.runtime.log.set_level_from_flags` 或等价 spy，验证 main 调用已有 helper，且 `--debug`、`--verbose`、`--quiet`、`--log-level warn` 参数进入 helper；不在 main 中重复断言手写映射。
- `prompt` / `interactive` 既有终态 UI tests 通过。
- `init` 既有 UI tests 通过，必要时增加 log assembly 不影响 stdout/stderr 的断言。
- Fins direct command tests 验证默认日志不污染 progress 输出；verbose/debug 下可以捕获诊断日志。

completion signal：

- 所有 scoped commands 至少有“正常 / 本条修复 / 后续 owner”的测试或直接代码证据；本条没有未分类 CLI UI/log residual。

stop condition：

- 如果 prompt / interactive 的运行中 content streaming 被证明是用户可见必需且已有 Host public event 能力可直接支持，应停止并请求用户裁决是否扩大 scope；不得在本条自行实现。

### Slice S6: README Sync

id/name：`S6-docs-sync`

objective：按 AGENTS.md README 触发规则同步稳定开发手册，不写 work unit 流水账。

allowed files/modules：

- `dayu/README.md`
- `dayu/fins/README.md`
- `dayu/service/README.md`
- `tests/README.md`

exact changes：

- `dayu/README.md`：把 Service / Fins direct 能力从 start / poll / cancel 更新为 start / event observation / poll terminal fallback / cancel；保持总览级边界，不写实现细节。
- `dayu/fins/README.md`：在 ingestion runtime 接口中加入 job event read/stream 能力和事件 sidecar 边界；说明 Fins job event 不是 Host EventLog。
- `dayu/service/README.md`：更新 `dayu.service.fins_direct` 的 reusable boundary 描述，加入 event stream consumer。
- `tests/README.md`：更新 `tests/cli`、`tests/service`、`tests/fins` 覆盖说明，加入 live Fins job events、CLI log assembly、UI/log distinction。

data flow：

代码实现稳定后再更新 README，README 只描述已落地事实。

tests/validation：

- README 无独立测试；通过人工核对章节职责和触发规则。

completion signal：

- README 描述与代码事实一致，不写未来计划。

stop condition：

- 如果实现中未落地某项事件能力，不得把它写入 README。

## Tests / Validation Commands and Expected Assertions

实现完成后必须运行：

```bash
source .venv/bin/activate && pytest \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_init_command.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py \
  -q
```

期望断言：

- Fins job event sidecar sequence 单调递增，progress/terminal 可读取。
- event sidecar append/read sequence allocation 使用 `FsFinsIngestionJobStore` 同一 runtime file lock；并发 append 不产生重复 sequence。
- download / upload 产生 runtime-owned started/completed coarse bounded progress events；preprocess 在现有循环内产生 selected / per-document / completed bounded progress events。
- progress event append failure 只记录 bounded WARN 并继续；业务成功时 job 不因 progress 写入失败而 failed。
- terminal event append failure 记录 bounded WARN，不回滚 terminal job record。
- Service event stream 输出 progress 并在 terminal 停止。
- Service event stream 在 empty read 后按 `poll_interval_seconds` sleep，测试证明没有 tight loop。
- Service synthesized terminal fallback 产生 bounded WARN。
- Fins direct CLI 六个 live commands 输出 progress 与 terminal summary。
- SIGINT 后 durable `request_cancel(job_id)`；二次 SIGINT 本地退出有明确 stderr。
- `upload_filings_from` 不启动 live job。
- `init` / `prompt` / `interactive` 终态 UI 输出未回退。
- CLI main 调用 `dayu.runtime.log.set_level_from_flags`，不手写 log-level precedence 映射。
- 若 implementation 安全复用已有同步桥接消费 async pipeline stream，必须额外运行并更新相关 pipeline stream tests；默认粗粒度路径不要求修改这些 tests。

完整类型检查：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

期望断言：

- 无新增或扩散 pyright 报错。
- 新增 dataclass/protocol/helper 无 `Any`、`object`、无类型签名或裸容器注解。

README 判断：

- 代码触发 `dayu/fins/`、`dayu/service/`、`tests/`、跨包 Service/Fins/CLI 边界说明更新；必须核对并按需更新对应 README。

本 plan gate validation：

- 只做静态核对，不运行测试。

## Docs Decision

- `dayu/README.md`：需要更新。原因是顶层稳定边界当前描述 Fins direct 为 start / poll / cancel，implementation 后会新增 Service/Fins event observation 能力，并恢复 CLI 日志装配语义。
- `dayu/fins/README.md`：需要更新。原因是 `dayu.fins.ingestion_runtime` public boundary 将新增 job event read/sidecar contract。
- `tests/README.md`：需要更新。原因是 `tests/cli`、`tests/service`、`tests/fins` 覆盖范围将新增 Fins direct live events 与 CLI log assembly。
- `dayu/service/README.md`：实现阶段也应更新，虽然用户未点名，但 `dayu/service/` 修改触发 README 检查，且 `fins_direct` reusable boundary 会改变。

## Risks / Open Questions / Residual Risk Owner

Blocking open questions：无。

Risks：

- R1：细粒度 async pipeline stream consumption 当前 deferred；runtime-owned coarse progress 可能不如 per-filing/per-file stream 细。
  owner：后续 Fins pipeline live-event refinement work unit；当前 implementation 只在无需协议变更且有测试证明安全时可复用已有同步桥接。
- R2：Event sidecar 增加 Fins job store schema，可能影响现有 fake job stores 和 tests。
  owner：当前 work unit S1；按全新 schema 更新测试，不写旧 schema 兼容。
- R3：Progress payload 可能误带路径或过大业务材料。
  owner：当前 work unit S1/S2；用 bounded payload helper 和泄漏边界测试收口。
- R4：CLI 日志 handler 输出到 stdout 可能与 UI progress 混杂。
  owner：当前 work unit S5；默认 INFO 不输出 progress 诊断，verbose/debug 测试明确日志/print 区分。
- R5：progress event sidecar append 失败会造成 UI progress gap，但不应改变业务终态。
  owner：当前 work unit S1/S2；bounded WARN + terminal job record truth + Service terminal fallback 收口。
- R6：Service poll interval 过短会 tight loop、过长会进度迟滞。
  owner：当前 work unit S3；复用 `FinsDirectCommandService.poll_interval_seconds` 并测试 empty read 后 sleep。
- R7：prompt / interactive 运行中 streaming 被排除后仍可能被用户期待。
  owner：后续独立 Agent command streaming/UI work unit；本条只保护终态输出和日志装配。

## Completion Report Format

最终 completion report 必须使用：

- artifact path
- plan status: ready / blocked
- key decisions
- blocking open questions
- validation performed
- files changed

## Plan Status

`ready after fix`

本 plan 已按 plan review adjudication 修复 accepted findings，可进入后续实现 gate；不得在未确认前进入 implementation。
