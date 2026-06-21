# WU-CLI-FINS-OBS-01 Replacement Plan

## Gate 上下文

- Work unit：`WU-CLI-FINS-OBS-01`
- Gate：replacement plan
- 替换目标：`docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`
- 总控真源：`docs/host/issues-implementation-control.md`
- Gate 约束：本 gate 只写本文档。

本 plan 替代 PR #143 旧 plan 的 durable Fins job event sidecar 前提。旧 plan 仍可作为历史 artifact 读取，但 implementation gate 不得继续按旧 plan 的 durable job sidecar、per-job event sequence、`request_cancel(job_id)` 证明 CLI direct live events。

## 第一性原理判断

问题真实存在，但旧方案严重过度设计。

Fins direct CLI 的六个命令 `download` / `process` / `upload_filing` / `upload_material` / `process_filing` / `process_material` 是一次性本地 product entrypoint。用户在当前进程里启动命令、观察进度、等待结果或按 Ctrl+C 中断。这个需求需要的是一个普通、可取消、可消费的 `AsyncIterator[FinsEvent]`，不是可跨重启恢复的 durable job ledger。

CLI direct durable job / sidecar 过度设计的原因：

- CLI direct 没有成立的 cross-restart resume 需求。进程退出后，用户没有被要求继续追踪后台 job，也没有要求从 durable cursor 补读历史 progress。
- CLI direct 的取消语义是当前 async 执行的 cancellation / cancel checker / KeyboardInterrupt 传播，不需要把本地 Ctrl+C 转成 `request_cancel(job_id)`。
- per-job sequence、JSONL sidecar、terminal fallback synthetic event 只是在补救错误抽象：它们为 CLI 证明“可补读事件”，但用户需求是“运行中能看到进度”。
- Fins 业务真源是 `dayu.fins.storage` 下的 source / processed / upload 产物和有界 result summary；job record / sidecar 不应成为 direct path 的业务事实真源。

Tool awaiting 的动机仍然成立，但 durable job system 过重。Engine 的 `ToolExecutor.execute` handshake 有有限 timeout，LLM 工具不应阻塞等待下载、上传或预处理长事务完成，因此 `ToolAwaitingOutcome(await_kind=EXTERNAL_JOB)` 必须保留。可是 awaiting 只要求 Host wait adapter 后续能观察 completion 并调用 `resolve_wait(...)`，最小需求是轻量 observation handle。只有明确需要跨进程或跨重启恢复未完成 Fins ingestion 时，才允许另开 durable operation ledger 设计；不能用 CLI direct 或“以后可能”证明 durable job store。

## 直接代码证据

NEW 当前代码依赖 durable job handle / sidecar：

- `dayu/cli/commands/fins.py` 模块 docstring 明确描述 SIGINT 到 durable Fins job cancel 的映射；`_run_fins_direct_command_async(...)` 调用 `_start_direct_job(...)`，拿到 `FinsDirectJobHandle` 后等待 `_wait_for_terminal_handling_sigint(...)`。
- `dayu/cli/commands/fins.py` 的 `_wait_for_terminal_handling_sigint(...)` 第一次 SIGINT 调用 `service.request_cancel(handle.job_id)`，第二次 SIGINT 输出包含 job id 的本地退出文案。
- `dayu/cli/commands/fins.py` 的 `_consume_fins_direct_events(...)` 只消费 `service.stream_job_events_until_terminal(handle)`，渲染的是 `FinsDirectJobEvent`，异常文案也以 `handle.job_id` 为核心。
- `dayu/service/fins_direct.py` 模块 docstring 把 Service 边界定义为启动 job、轮询终态、请求 durable cancel；`FinsDirectIngestionRuntime` protocol 暴露 `start_download` / `start_preprocess` / `start_upload`、`read_job(...)`、`read_job_events(...)`、`request_cancel(...)`。
- `dayu/service/fins_direct.py` 定义 `FinsDirectJobHandle(job_id, initial_status, start_request)`、`FinsDirectTerminalResult(job_id, status, ...)` 与 `FinsDirectJobEvent(job_id, sequence, ...)`；`stream_job_events_until_terminal(...)` 按 `read_job_events(... after_sequence ...)` 补读 sidecar，并在 terminal event 缺失时合成 fallback。
- `dayu/fins/ingestion_runtime.py` 的 `FinsIngestionRuntime.start_download` / `start_preprocess` / `start_upload` 都先创建 durable queued job record，再提交后台 executor；runtime public API 暴露 `read_job(...)`、`read_job_events(...)`、`request_cancel(...)`。
- `dayu/fins/ingestion_runtime.py` 的 job store 使用 `<workspace_root>/.dayu/fins_ingestion/jobs/<job_id>.json` 和 `<job_id>.events.jsonl`，并在 `append_job_event(...)` 中分配 per-job sequence。
- `dayu/fins/ingestion/wait_adapter.py` 当前把 Host wait record 的 `external_job_ref.external_job_id` 当作 Fins job id，调用 `runtime.read_job(job_id)` 与 `runtime.request_cancel(job_id)`。
- `dayu/fins/tools/_ingestion_tool_helpers.py` 用 `start.job_id` 填充 `ToolAwaitSpec.resume_token`，snapshot id 也拼接 `fins-ingestion-start-{job_id}`。
- `dayu/service/host_assembly.py` 根据启用的 Fins awaiting provider 构造 `build_fins_wait_adapter_registry(...)`，把 Fins tool awaiting provider 绑定到 Host wait adapter registry。
- `tests/cli/test_fins_commands.py`、`tests/service/test_fins_direct.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/service/test_host_assembly.py` 当前大量断言 `job_id`、`read_job_events`、sidecar sequence、`request_cancel(job_id)`、`ToolAwaitingOutcome(EXTERNAL_JOB)` 的 durable job 语义。

OLD 代码证明 direct path 曾是普通 event stream：

- OLD `/Users/leo/workspace/dayu-agent/dayu/contracts/fins.py` 定义 `FinsEventType.PROGRESS` 与 `FinsEventType.RESULT`，`FinsEvent` 是 UI / Service / runtime 共享的财报流式事件。
- OLD `/Users/leo/workspace/dayu-agent/dayu/services/fins_service.py` 的 `FinsService.execute(...) -> FinsResult | AsyncIterator[FinsEvent]`；stream path 在 `_execute_command_stream(...)` 中直接 `async for event in result: yield event`，没有 job id、sidecar、durable cursor 或 job cancel。
- OLD `/Users/leo/workspace/dayu-agent/tests/cli/test_fins_commands.py` 的 `_consume_fins_stream` 测试直接消费 `AsyncIterator[FinsEvent]`，通过 `PROGRESS` 输出运行中进度，通过 `RESULT` 返回最终结果。

## 目标

- 恢复 Fins direct Service boundary：六个 direct command 通过普通 `AsyncIterator[FinsEvent]` 暴露运行中 progress 和最终 result。
- CLI 只是 UI consumer：解析参数、调用 Service async iterator、渲染 progress/result/failure/cancel，不直接读 storage、不直接调用 pipeline、不处理 durable job cursor。
- Fins ingestion runtime core 收敛为业务执行、事件流与 storage 产物写入能力；business result summary 保持有界、业务可读。
- Fins tools 继续快速返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`，但 await ref 轻量化，不把 Fins core runtime 固定成 durable job system。
- Host / Engine public contract 保持不变：不改 Host durable schema、EventLog、Run/Attempt 状态机、Engine `ToolExecutor`、`ToolAwaitingOutcome` union。
- README / design-adjacent docs / tests 同步清理被否定的 durable CLI direct 描述。

## 非目标

- 不全量搬迁 OLD `dayu-agent` CLI 或 Fins workflow。
- 不把 Fins direct command 改造成 Host Run、Host event stream、EngineEvent stream 或 Host wait record。
- 不为 CLI direct 保留 sidecar JSONL、per-job sequence、terminal fallback synthetic event 或 `request_cancel(job_id)`。
- 不删除 `ToolAwaitingOutcome(EXTERNAL_JOB)` 或 Host WAITING / wait adapter 方向。
- 不修改 Host durable schema、EventLog、Run/Attempt 状态机、Engine stream 术语或 Engine public contract。
- 不实现 prompt / interactive 运行中 token/content streaming。
- 不把 `upload_filings_from` 改造成 live execution stream；它仍是本地 batch script generation command。
- 不引入通用跨进程 event bus、WebSocket、后台 daemon 或平台化 observer registry。

## 成功信号

- `FinsDirectCommandService` 对 direct commands 暴露 `AsyncIterator[FinsEvent]`，不再暴露 CLI-facing `FinsDirectJobHandle`、`stream_job_events_until_terminal(...)`、`read_job_events(...)` 或 `request_cancel(...)`。
- `FinsEvent` contract 明确 PROGRESS / RESULT、success / failure / cancelled、exit code 映射和业务可读字段；事件不暴露 job id、sequence、cursor、storage path 或 raw payload。
- `dayu-cli download --ticker ...`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material` 都能在执行中输出 `PROGRESS`，并以 `RESULT` 收口最终用户可见结果。
- Ctrl+C 取消当前 async stream；取消输出不包含后台 job id 追踪语义，不要求 durable cancel record。
- Fins awaiting tools 仍返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`；Host wait adapter 仍能 poll/resolve/abandon/cancel，但 await ref 是轻量 observation handle。若 implementation 仍保留任何 durable row，必须在 Slice D0 前给出明确 cross-process / cross-restart 需求证据和最小 schema 理由。
- 旧 durable job / sidecar 证明型测试被改写为 direct stream、business result summary、lightweight await handle 语义；awaiting tests 保留但不再要求 Fins core job system。
- 每个 implementation slice 完成时都有 README impact assessment；README 可集中在 Slice E 编辑，但触发判断不能跳过。
- README 中不再把 CLI direct 或 core Fins runtime 描述为 durable job system；Host/Engine 设计边界保持不变。

## 架构边界

### CLI Direct

CLI direct 属于 UI adapter。它只负责参数解析、输出渲染、顶层取消和退出码映射。它不拥有 Fins execution、storage、job ledger、Host wait 或 Engine stream。

Implementation gate 应把 `_start_direct_job(...) -> FinsDirectJobHandle` 改为 `service.stream_<operation>(...) -> AsyncIterator[FinsEvent]` 或等价单一 `service.execute(...) -> AsyncIterator[FinsEvent]`。CLI 消费 `PROGRESS` 事件输出进度，消费 `RESULT` 事件得到 exit code 和 summary。

### Service / Fins 边界

Service 负责 product entrypoint 到 Fins typed request 的映射。Service 不处理 stdout/stderr，不读取 Fins storage，不暴露 Fins internal storage path。Service boundary 应提供普通 async iterator，并把 Fins runtime 的业务事件投影成 direct `FinsEvent` contract。

### Fins Runtime Core Execution

Fins runtime core owner 是财报业务执行和 storage 产物写入。它应区分三类输出：

- direct execution stream：运行中 progress 与 terminal result，供 CLI / GUI / WeChat 等 UI consumer 订阅；
- business result summary：有界、业务可读 summary，表示本次 download / preprocess / upload 的业务收口；
- awaiting observation handle：给 Host wait adapter 的轻量 ref，用于后续观察 completion。

Core runtime 不应默认成为 durable job status machine。若仍需要后台执行，必须说明它服务 awaiting observation 的最小语义，而不是服务 CLI direct。

### Tool Awaiting / Wait Adapter

`ToolAwaitingOutcome(EXTERNAL_JOB)` 保留。工具 handshake 只负责快速启动外部长事务或注册 observation，并返回 await spec；Engine 挂起本次 run，Host 通过 wait record 和 adapter 后续 poll/resolve。等待语义不能塞进普通 tool result meta。

Wait adapter 只能把 lightweight await ref 映射到 Fins observation source，并通过 Host `resolve_wait(...)` 收口；不得写 Host EventLog，不得直接更新 Run / Attempt，不得恢复旧 Engine generator。

### Host / Engine 不变边界

Host 仍是 Session / Run / Attempt / EventLog / wait record 真源。Engine 仍只执行一次 `AgentRunRequest`，暴露 `EngineEvent stream`，不持久化等待状态，不轮询外部 job。

## Contract 裁决

### FinsEvent 最小 typed contract

Slice A 必须先建立一个唯一 direct event contract，后续 CLI、Service 与 runtime 都以它为 handoff truth。优先复用项目内已经存在且满足下列字段语义的 contract；若不存在，新增 Fins-facing contract。不得复用旧 durable job event enum，也不得把 `JOB_QUEUED`、`JOB_RUNNING`、`CANCEL_REQUESTED`、`JOB_SUCCEEDED`、`JOB_FAILED`、`JOB_CANCELLED` 等 job lifecycle 状态投影给 CLI direct。

最小 enum：

- `FinsEventType.PROGRESS`：运行中进度事件，不能作为终态。
- `FinsEventType.RESULT`：唯一终态事件，必须恰好出现一次；stream 正常结束但未出现 RESULT 是 producer bug，CLI 必须按 failure 处理。
- `FinsResultStatus.SUCCESS`：业务操作完成。
- `FinsResultStatus.FAILURE`：业务操作失败。
- `FinsResultStatus.CANCELLED`：用户取消或 cancellation token 生效。
- `FinsOperationKind.DOWNLOAD` / `PREPROCESS` / `UPLOAD` / `UPLOAD_FILING` / `UPLOAD_MATERIAL` / `PROCESS_FILING` / `PROCESS_MATERIAL`：面向业务的操作类型；若实现已有更窄 enum，可使用等价值，但不得使用 job / ledger 命名。
- `FinsErrorKind.USER_INPUT` / `STORAGE` / `PROVIDER` / `EXECUTION` / `CANCELLED` / `UNKNOWN`：失败分类，供 CLI 输出和测试断言使用。

最小 typed shape：

```python
@dataclass(frozen=True)
class FinsEventDetail:
    label: str
    value: str

@dataclass(frozen=True)
class FinsProgress:
    stage: str
    completed_units: int | None
    total_units: int | None

@dataclass(frozen=True)
class FinsResultSummary:
    status: FinsResultStatus
    exit_code: int
    title: str
    details: tuple[FinsEventDetail, ...]
    error_kind: FinsErrorKind | None
    error_message: str | None

@dataclass(frozen=True)
class FinsEvent:
    event_type: FinsEventType
    operation_kind: FinsOperationKind
    message: str
    emitted_at: datetime
    ticker: str | None
    filing_kind: str | None
    document_label: str | None
    progress: FinsProgress | None
    result: FinsResultSummary | None
```

字段规则：

- `PROGRESS` 必须满足 `progress is not None` 且 `result is None`。
- `RESULT` 必须满足 `progress is None` 且 `result is not None`。
- `RESULT.status == SUCCESS` 时 `exit_code == 0`。
- `RESULT.status == FAILURE` 时 `exit_code == 1`，除非现有 CLI policy 已有更具体非零码；若使用更具体码，必须在 contract 测试中固定映射。
- `RESULT.status == CANCELLED` 时 `exit_code == 130`，对应 Ctrl+C / KeyboardInterrupt 语义。
- `details` 只能包含业务可读 label/value，例如 ticker、filing kind、processed count、uploaded count、provider name；不得包含 job id、event sequence、cursor、resume token、tool_call_id、absolute storage path、raw provider payload、财报正文或大块 tool result。
- `document_label` 是用户可理解的短标签，不是 storage path。需要引用仓储产物时，只能用业务摘要或 repository 返回的安全 display label。
- 允许把实现中的 `datetime` 序列化为 ISO-8601 字符串给 CLI 输出，但 contract 内部应保持 typed `datetime`，避免让字符串格式成为业务事实。

### Async 与取消裁决

目标实现是 native async / cooperative async execution。Direct stream 的公共契约必须是 `AsyncIterator[FinsEvent]`，runtime 内部优先通过 async adapter、async runner、显式 cancellation token / checker 传播取消。

`asyncio.to_thread`、producer thread、thread-owned queue bridge 不能写成首选设计，也不能成为 Service 或 runtime public contract。只有在现有 sync blocking adapter 短期不能改 protocol、且单个 blocking 调用边界已经清楚时，才允许在 `dayu.fins` runtime 内部使用有界 blocking bridge：

- bridge 必须是 runtime implementation detail，不出现在 Service protocol、tool schema、Host wait adapter contract 或 README 用户语义中。
- bridge 必须有 bounded queue / bounded lifecycle，不得变成 job sidecar、daemon、durable event bus 或无界后台 worker。
- bridge 不能证明强取消语义；取消仍必须靠 operation-scoped `CancellationToken` / cancellation checker 在 adapter 可检查点生效。
- 如果 blocking 调用本身没有检查点，取消语义只能声明为 best-effort：CLI 立即停止等待并输出 cancelled，但底层 blocking call 可能到下一个检查点或自然返回才停止。
- 如果 implementation 需要为多数 adapter 引入大量 thread bridge，或者 bridge 需要跨 operation 共享复杂状态，必须停止并重新评估 adapter async 化，而不是把 `to_thread` / producer thread 固化为架构。

### Lightweight observation handle 最小 typed contract

Tool awaiting 的 replacement 不是 durable Fins job，而是 observation handle。该 handle 只服务 Host wait adapter 观察外部长事务，不是 CLI direct truth，不是业务事实，不得投影给 LLM 作为财报结论。

默认裁决：本 WU 不因 CLI direct 引入 durable handle。Tool awaiting 默认使用 process-local lightweight observation source；它不保证 Host 重启或 runtime crash 后恢复未完成 Fins ingestion。Host restart / runtime crash 后，如果 wait adapter 无法通过 observation source 找回 handle，必须把该 wait resolve 为 `LOST`，不得无限 pending。若产品要求跨进程或跨重启恢复，implementation 必须在删除/降级旧 job store 前停止，补充最小 durable ledger mini-design，并得到 controller / design 裁决。

最小类型：

```python
@dataclass(frozen=True)
class FinsObservationHandle:
    handle_id: str
    operation_kind: FinsOperationKind
    created_at: datetime

class FinsObservationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"

class FinsObservationPollErrorKind(Enum):
    TRANSIENT_UNAVAILABLE = "transient_unavailable"
    PERMANENT_NOT_FOUND = "permanent_not_found"
    PERMANENT_CORRUPT_HANDLE = "permanent_corrupt_handle"

@dataclass(frozen=True)
class FinsObservationSnapshot:
    handle: FinsObservationHandle
    status: FinsObservationStatus
    message: str
    result: FinsResultSummary | None
    error_kind: FinsErrorKind | None
    retry_after_seconds: float | None
```

最小 runtime protocol：

```python
class FinsObservationRuntime(Protocol):
    def start_observed_download(
        self,
        request: FinsDownloadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle: ...

    def start_observed_preprocess(
        self,
        request: FinsPreprocessRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle: ...

    def start_observed_upload(
        self,
        request: FinsUploadRequest,
        cancellation_token: CancellationToken,
    ) -> FinsObservationHandle: ...

    async def poll_observation(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot: ...

    async def cancel_observation(
        self,
        handle: FinsObservationHandle,
    ) -> FinsObservationSnapshot: ...

    async def abandon_observation(
        self,
        handle: FinsObservationHandle,
    ) -> None: ...
```

API 语义：

- 创建者：Fins runtime。Tool helper 只能调用 `start_observed_*` 并把 opaque `handle_id` 序列化到 `ToolAwaitSpec.resume_token`；不得把 `handle_id` 写成 job id 或业务事实。
- 消费者：Fins wait adapter。Adapter 从 wait record 的 resume token 解析 `FinsObservationHandle`，调用 `poll_observation` / `cancel_observation` / `abandon_observation`。
- observation source：默认是 runtime-owned process-local registry，保存 operation status、terminal summary、cancel signal 和 bounded diagnostic message。它不是 durable storage，不写 Host EventLog，不写 `.dayu/fins_ingestion/jobs/*.events.jsonl`。
- terminal 状态：`SUCCEEDED` 映射 `ResolveWaitCompletedOutcome`；`FAILED` 映射 `ResolveWaitFailedOutcome`；`CANCELLED` 映射 `ResolveWaitCancelledOutcome`；`LOST`、`PERMANENT_NOT_FOUND`、`PERMANENT_CORRUPT_HANDLE` 映射 `ResolveWaitLostOutcome`。
- transient poll failure：`TRANSIENT_UNAVAILABLE` 或 snapshot `retry_after_seconds` 表示保持 wait pending 并重试，不 resolve。
- abandon：表示 Host 不再等待该 handle；它可以释放 process-local observation record，但不得删除已经通过 `dayu.fins.storage` 写入的业务产物。
- cancel：表示 wait owner 请求取消 operation-scoped token；若底层 blocking call 无检查点，返回值必须反映 best-effort 限制，不能声称强取消。

Durable mini-design 触发条件：

- Host restart 后必须继续等待未完成 Fins ingestion，而不是标记 LOST。
- Fins runtime 与 Host wait adapter 明确处于不同进程，且没有共享 process-local registry。
- 业务要求用户或 LLM 在进程重启后继续追踪同一 ingestion operation。

若触发 durable mini-design，只允许设计最小 ledger 字段：`handle_id`、`operation_kind`、`status`、`created_at`、`updated_at`、terminal `FinsResultSummary`、安全错误分类、cleanup deadline。不得恢复 job event sidecar、per-job sequence、durable cursor 或 CLI direct job handle。

### Slice ownership 与 sequencing

实施顺序必须按以下 handoff 执行：

1. Slice A owns：`FinsEvent` typed contract、Service direct `AsyncIterator[FinsEvent]` boundary、Service-facing runtime protocol。Slice A 可以用 fake runtime 完成 Service tests；不得删除 runtime job store，不得设计 observation source。
2. Slice B owns：CLI direct consumer、output、Ctrl+C 到 async cancellation / token 的映射。Slice B 只消费 Slice A 的 contract。
3. Slice D0 owns：lightweight observation handle contract-only checkpoint，也就是上文 `FinsObservationHandle` / `FinsObservationRuntime` / recovery semantics。D0 必须在 Slice C 删除或降级 job store 前完成；如果 D0 发现需要 durable mini-design，先停下裁决。
4. Slice C owns：`dayu.fins` runtime implementation 收敛，实现 Slice A 的 direct stream protocol，并在 D0 contract 已成立后移除或降级旧 direct job store。
5. Slice D owns：tools 和 wait adapter 迁移到 D0 handle contract。
6. Slice E owns：README closeout 与 cross-README consistency check。

禁止 A、C 两个 slice 同时临场设计 `ingestion_runtime.py` 的同一层 API。Service contract、runtime protocol、runtime implementation 的 handoff 以上述 ownership 为准。

## Replacement Slices

### Slice A: Direct FinsEvent contract and Service AsyncIterator boundary

允许文件 / 模块：

- `dayu/service/fins_direct.py`
- `dayu/fins/ingestion_runtime.py`
- 可新增 `dayu/fins/ingestion_events.py` 或 `dayu/fins/direct_events.py`，但必须是 Fins 业务事件 contract，不是 job sidecar contract。
- `tests/service/test_fins_direct.py`
- 必要时 `tests/fins/test_fins_ingestion_runtime.py`

实施步骤：

1. 定义或复用上文 `FinsEvent` 最小 typed contract。该 contract 是 Slice A/B/C 的共享真源；不得让 Service fake、CLI fake 和 runtime implementation 各自定义 shape。
2. 把 `FinsDirectIngestionRuntime` protocol 的 Service-facing direct path 从 `start_* + read_job/read_job_events/request_cancel` 改为 direct streaming methods，例如 `download(...) -> AsyncIterator[FinsEvent]`、`preprocess(...) -> AsyncIterator[FinsEvent]`、`upload(...) -> AsyncIterator[FinsEvent]`，或等价按六个 command 命名的方法。Slice A 只 owns protocol shape 与 Service 调用边界；真实 runtime implementation 留给 Slice C。
3. `FinsDirectCommandService` 提供六个 command 对应的 async iterator boundary；方法名可按现有 direct command 命名，但返回值必须是 `AsyncIterator[FinsEvent]`。
4. 移除 CLI-facing `FinsDirectJobHandle`、`FinsDirectJobEvent`、`stream_job_events_until_terminal(...)` 和 `wait_for_terminal(job_id)` 的 Service public direct path 依赖。若旧 helper 暂时仍在 runtime 内部存在，不能被 CLI direct 或 Service public direct API 使用。
5. direct stream 的 terminal `RESULT` 必须携带 `FinsResultSummary`，并按上文映射 success / failure / cancelled / exit code。失败可以产出 `RESULT(status=FAILURE)` 或显式抛出异常，但不得静默结束，也不能依赖 terminal job fallback。
6. 取消应通过 async iterator 关闭 / task cancellation / operation-scoped cancellation token 传播到 runtime；不要引入 `request_cancel(job_id)`。如果 Slice A 使用 fake runtime，测试必须先固定 token/checker 被调用的边界，真实 blocking 限制在 Slice C 验证。

预期测试：

- `tests/service/test_fins_direct.py` 改写为直接消费 `AsyncIterator[FinsEvent]`：progress -> result、failure、异常透传、取消关闭、不暴露 job handle。
- 覆盖 `FinsEvent` contract 校验：PROGRESS 不能携带 result，RESULT 不能缺 result，RESULT success/failure/cancelled 到 exit code 的映射固定。
- 删除或改写证明 `read_job_events(...)`、negative `after_sequence`、terminal fallback synthetic event、poll interval 的测试。
- 增加 Service 不导出 job id / sequence 给 direct CLI consumer 的边界测试。
- 增加 stream no-result 测试：fake runtime 只产出 PROGRESS 后正常结束时，Service / CLI consumer 必须以清晰 failure 收口。
- 增加基础 redaction/leakage guard：event message、details、document_label 不包含 absolute path、raw provider payload、财报正文、大块 tool result、job id、sequence、cursor。

Pyright 目标：

- `pyright dayu/service/fins_direct.py dayu/fins/ingestion_runtime.py tests/service/test_fins_direct.py`

README 触发：

- 修改 `dayu/service/` 时检查 `dayu/service/README.md`。
- 修改 `dayu/fins/` 时检查 `dayu/fins/README.md`。
- 修改 `tests/` 时检查 `tests/README.md`。
- Slice 完成时必须记录 README impact assessment：哪些 README 被检查、是否命中目标读者职责、是否需要 Slice E 集中编辑。实际 README 编辑可集中在 Slice E，但触发判断不能跳过。

停止条件：

- 如果实现必须修改 Host public API、Host wait record schema 或 Engine `ToolAwaitingOutcome`，停止并回到 design discussion。
- 如果 Service direct API 仍要求 `job_id`、`read_job_events`、sidecar cursor 或 terminal fallback，停止并重写 slice。
- 如果 Slice A 需要真实 runtime 大改才能让 Service tests 通过，改用 Service fake 固定 contract，不能把 Slice C runtime implementation 混入 Slice A。

### Slice B: CLI direct command consumption, output, and cancel tests

允许文件 / 模块：

- `dayu/cli/commands/fins.py`
- `dayu/cli/output.py`
- `dayu/cli/main.py`，仅当 implementation gate 仍把日志装配纳入本 WU 时修改
- `tests/cli/test_fins_commands.py`
- `tests/cli/test_upload_filings_from_command.py`
- `tests/cli/test_init_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_arg_parsing.py`，仅当日志 flag 断言需要更新时修改

实施步骤：

1. 用 direct async stream consumption 替换 `_start_direct_job(...)` 和 `_wait_for_terminal_handling_sigint(...)`。
2. 实现类似 `_consume_fins_stream(...)` 的 helper：渲染每个 `PROGRESS`，记录/返回 terminal `RESULT`，stream 结束但没有 result 时失败。
3. 第一次 Ctrl+C 按现有 CLI exit-code policy 取消当前 stream task，并以 keyboard interrupt 语义或 `RESULT(status=CANCELLED, exit_code=130)` 收口；不得调用 `service.request_cancel(handle.job_id)`。
4. 用有界用户可见文本渲染 progress/result/failure/cancel；输出不能依赖日志级别才可见。
5. 保持 `upload_filings_from` 只生成脚本；测试应断言它不启动 direct live stream。
6. 保持 `init`、`prompt`、`interactive` 终态 UI 输出测试覆盖。运行中 content/token streaming 仍是非目标，owner 是 `WU-CLI-FINS-OBS-01-R5`；不得新增、修改或删除 streaming 相关断言来扩大本 WU。
7. 如果 implementation gate 把日志装配纳入范围，应从 CLI main 调用已有 runtime logging helper；不得手写 precedence 映射。

预期测试：

- 重写 `tests/cli/test_fins_commands.py`，使用返回 `AsyncIterator[FinsEvent]` 的 fake Service 方法。
- 移除 job id cancel 断言，替换为 async cancellation / stream close 断言。
- 覆盖六个 direct command：progress 渲染、result 退出码、failure 输出、cancellation 输出。
- 覆盖 stream no-result：stream 只产出 PROGRESS 后结束时 CLI 返回 failure exit code，并输出清晰错误。
- 覆盖 cancel race：terminal RESULT 已产出但 CLI 尚未消费时收到 Ctrl+C，最终结果不得被 cancel 覆盖；Ctrl+C 先到且 token/checker 生效时才按 cancelled 收口。
- 保留 / 更新 unsupported flags、upload file validation、ticker parsing、`upload_filings_from` script output 测试。
- 保留 `tests/cli/test_prompt_command.py` 与 `tests/cli/test_interactive_command.py` 作为终态输出保护；只允许为日志装配或终态输出做必要断言，不新增 token streaming 期望，不削弱已有终态 final answer / failure / cancel 断言。
- 覆盖 CLI output redaction：progress/result/failure/cancel 文本不打印 storage absolute path、job id、sequence、cursor、raw provider payload 或财报正文。

Pyright 目标：

- `pyright dayu/cli/commands/fins.py dayu/cli/output.py dayu/cli/main.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py`

README 触发：

- CLI files 没有专属 README 触发，但 tests 更新会触发 `tests/README.md`。
- 如果日志语义触及或改变 `dayu/README.md` 的描述，编辑前必须先阅读 `dayu/README.md` 的 Agent 更新约束。
- Slice 完成时必须记录 README impact assessment；实际 README 编辑可集中在 Slice E。

停止条件：

- 不得用 sidecar JSONL、per-job sequence、durable terminal fallback 或 `request_cancel(job_id)` 证明 CLI direct。
- 不得把 prompt / interactive token streaming 扩大进本 WU。

### Slice D0: Lightweight observation handle contract-only checkpoint

允许文件 / 模块：

- `dayu/fins/ingestion/observation_handle.py` 或等价 Fins ingestion contract module
- `dayu/fins/ingestion_runtime.py`，仅用于声明 `FinsObservationRuntime` protocol 或导入 contract
- `tests/fins/test_fins_ingestion_tools.py` 或 `tests/fins/test_fins_ingestion_runtime.py`，仅用于 contract-level fake tests

实施步骤：

1. 按上文定义 `FinsObservationHandle`、`FinsObservationStatus`、`FinsObservationPollErrorKind`、`FinsObservationSnapshot` 与 `FinsObservationRuntime` protocol。
2. 明确 `ToolAwaitSpec.resume_token` 只承载 opaque `handle_id` 或等价 token；若需要从 token 恢复 typed handle，提供显式 parser，并把 corrupt token 映射为 `LOST`。
3. 明确默认 observation source 是 process-local registry，不 durable。Host restart / runtime crash 后找不到 handle 时，wait adapter 必须 resolve LOST；不得无限重试。
4. 在 contract 注释和测试中明确：CLI direct 不消费 handle，Service direct API 不返回 handle，handle 不包含 job id、sequence、cursor 或 storage path。
5. 如果 D0 判断 process-local registry 不足以满足当前 tool awaiting requirement，停止并写 durable mini-design；不要让 Slice C 删除旧 job store。

预期测试：

- handle token 解析成功 / corrupt token -> LOST 分类。
- process-local observation source 找不到 handle -> LOST 分类。
- `FinsObservationSnapshot` terminal status 到 completed / failed / cancelled / lost 的映射表固定。
- contract 不允许把 job id、sequence、cursor、storage path 放进 LLM-facing wait description。

Pyright 目标：

- `pyright dayu/fins/ingestion/observation_handle.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py`

README 触发：

- 修改 `dayu/fins/` 触发检查 `dayu/fins/README.md`。
- 修改 `tests/` 触发检查 `tests/README.md`。
- Slice 完成时必须记录 README impact assessment；实际 README 编辑可集中在 Slice E。

停止条件：

- 如果当前 Host wait recovery requirement 要求跨重启继续等待，必须先做 durable mini-design，不能用 process-local handle 假装可恢复。
- 如果 handle contract 需要改 Host wait record schema，停止并回到 design discussion。

### Slice C: Fins ingestion runtime core API convergence

允许文件 / 模块：

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/ingestion_events.py` 或 Slice A 选定的 replacement event module
- `dayu/fins/ingestion/observation_handle.py` 或等价 module，仅当 D0 contract 需要新增独立 contract module
- `tests/fins/test_fins_ingestion_runtime.py`

前置条件：

- Slice A 已固定 `FinsEvent` contract 和 Service-facing runtime stream protocol。
- Slice D0 已固定 lightweight observation handle contract、observation source 生命周期和 Host restart / runtime crash 收口语义。
- 如果 D0 触发 durable mini-design，本 slice 不能删除/降级旧 job store，必须等 controller / design 裁决。

实施步骤：

1. 拆分 runtime API 语义：
   - direct execution stream：供 CLI / Service direct consumers 消费；
   - business result summary：供 terminal result 使用；
   - lightweight observation handle：供 tool awaiting 使用。
2. 实现 Slice A 的 direct stream protocol。优先 native async / cooperative async execution；若当前 sync adapter 短期不能改 protocol，只允许 runtime 内部有界 blocking bridge，并按上文 async 裁决暴露 best-effort cancellation 限制。
3. 从 core runtime 移除或降级 job event sidecar。删除前必须确认 Slice D0 的 observation source 已能支撑 wait adapter poll/resolve/abandon；否则只能先让 direct path 不再使用旧 job store，不能实际删除 poll 真源。
4. 用 stream execution APIs 替代 `start_download` / `start_preprocess` / `start_upload` 的 direct-path 使用。tool awaiting path 可以继续调用 `start_observed_*` / `poll_observation` / `cancel_observation` / `abandon_observation`，命名和返回类型必须表达 observation handle 语义，而不是 CLI job handle 语义。
5. Runtime direct stream 必须保证每次正常业务完成产出唯一 `RESULT`。adapter/runner 异常可以转成 `RESULT(status=FAILURE)` 或抛出显式异常；不得静默 StopAsyncIteration。
6. 确保所有 storage writes 仍只通过 `dayu.fins.storage` repositories。
7. 保留 bounded result summaries 和 leakage guards：user-facing events 不得包含 absolute upload paths、raw provider payload、financial document body 或 large tool result。
8. 明确裁决是否保留任何 durable row。默认 core runtime 不保留 durable job store；若 awaiting 需要保留 row，必须先完成 durable mini-design，说明最小字段和理由。

预期测试：

- 改写 runtime 测试，不再证明 queued job persistence、per-job event sidecar、sequence allocation、sidecar append failure WARN 和 `read_job_events(...)` cursor 行为。
- 保留 ticker normalization、download/upload/preprocess storage side effects、bounded summaries、cancellation checks、unsupported source/runner failures、record leakage boundaries 和 import boundaries 测试。
- 新增 direct stream 的 progress/result 顺序和协作取消测试。
- 新增 adapter 异常测试：runtime 产出 `RESULT(status=FAILURE)` 或抛出显式异常，不允许静默结束。
- 新增 storage repository boundary 测试：direct stream 路径写入 source / processed / upload 产物时只能经 `dayu.fins.storage` repository/protocol，不在 CLI 或 Service 侧直接散落文件读写。
- 新增 blocking bridge limitation 测试（如适用）：当 sync adapter 在检查点前阻塞时，CLI cancellation 只能标记 token 并停止等待；测试必须断言不会声称强取消，且下一个 checker 到达后 operation 收口为 cancelled。
- 新增 leakage guard：progress/result summary 不包含 absolute path、raw payload、document body 或 large result。

Pyright 目标：

- `pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py`

README 触发：

- 修改 `dayu/fins/` 触发检查 `dayu/fins/README.md`。
- 修改 `tests/` 触发检查 `tests/README.md`。
- Slice 完成时必须记录 README impact assessment；实际 README 编辑可集中在 Slice E。

停止条件：

- 如果移除 job store 会破坏 awaiting poll/resolve 且 D0 lightweight replacement 尚未成立，删除前必须停止并升级到 controller / design 裁决。
- 如果实现需要大量 `asyncio.to_thread`、producer thread 或共享 bridge state 才能成立，停止并重新评估 adapter async 化。
- 不得为了保留旧测试硬编码业务规则；测试必须迁移到新边界。

### Slice D: Fins tool awaiting and wait adapter lightweight handle

允许文件 / 模块：

- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/tools/_ingestion_tool_helpers.py`
- `dayu/fins/ingestion/observation_handle.py` 或 D0 选定的 contract module
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/service/host_assembly.py`，仅当 adapter binding 字段变化时修改
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_host_assembly.py`

前置条件：

- Slice D0 contract-only checkpoint 已通过。
- Slice C 没有在 observation source 未成立前删除 wait adapter poll 真源。

实施步骤：

1. 保留 `ToolAwaitingOutcome(await_spec=ToolAwaitSpec(await_kind=EXTERNAL_JOB, ...))`。
2. 用 lightweight observation handle 替代 `resume_token=start.job_id`。该 handle 必须是不透明引用，只标识 wait adapter 观察 completion 所需的信息；它不是业务事实，也不是用户可见结论。
3. 更新 wait adapter，使其调用 `poll_observation`、`cancel_observation`、`abandon_observation`，并把 terminal completion 映射为 Host `ResolveWaitCompletedOutcome` / `ResolveWaitFailedOutcome` / `ResolveWaitCancelledOutcome` / `ResolveWaitLostOutcome`。
4. 保持 adapter registry assembly 显式且确定；Service assembly 可以继续按 configured workspace root 绑定 Fins awaiting providers，但不得暗示 CLI direct durable jobs。
5. 显式实现 Host restart / runtime crash recovery 收口：如果 wait record 持有的 handle 在当前 observation source 中不存在，返回 LOST；如果 poll 只是暂时不可用，保持 pending 并按 retry hint 继续 poll。
6. 如果 implementation 提议保留任何 durable row，coding 前必须补一个 mini-design：
   - 精确的 cross-process 或 cross-restart 需求；
   - 最小 schema 字段；
   - cleanup / retention owner；
   - 证明该 row 不是 CLI direct truth，也不是 Host EventLog truth。
7. Tool schemas 必须继续保持 LLM-facing 且自解释。如果 description 提到 durable job，改写为 "returns an external-job wait state" 或等价轻量表述。

预期测试：

- 保留 awaiting callable 返回 `ToolAwaitingOutcome(EXTERNAL_JOB)` 的测试。
- 将 `resume_token == job_id` 断言改为 opaque lightweight await ref 语义断言。
- 保留启动边界取消返回 `ToolCancelledOutcome` 的测试。
- 将 wait adapter 测试从 `read_job(job_id)` / `request_cancel(job_id)` 改写为 lightweight observation polling / cancel / abandon 语义。
- 覆盖 wait adapter 状态转换：pending -> completed、pending -> failed、pending -> cancelled、pending -> lost、abandon 后不再 poll。
- 覆盖 poll failure 分类：transient unavailable 保持 pending 并重试；permanent not found / corrupt handle resolve LOST；execution failure resolve failed。
- 覆盖 Host restart / runtime crash recovery 收口：process-local registry 找不到 handle 时 resolve LOST，或在 durable mini-design 已获裁决时按最小 ledger 恢复。
- 覆盖 cancel limitation（如 runtime 使用 blocking bridge）：cancel 只触发 explicit token/checker，不声称能中断不可取消 blocking call。
- 如果 provider-based adapter registry binding 和 workspace-root validation 仍属于 observation handle 装配，保留 `tests/service/test_host_assembly.py` 覆盖。

Pyright 目标：

- `pyright dayu/fins/tools/download_tools.py dayu/fins/tools/preprocess_tools.py dayu/fins/tools/upload_tools.py dayu/fins/tools/_ingestion_tool_helpers.py dayu/fins/ingestion/wait_adapter.py dayu/service/host_assembly.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py`

README 触发：

- 修改 `dayu/fins/` 触发检查 `dayu/fins/README.md`。
- 修改 `dayu/service/` 触发检查 `dayu/service/README.md`。
- 修改 `tests/` 触发检查 `tests/README.md`。
- 如果分层关系或 assembly boundary 文案变化，检查 `dayu/README.md`。
- Slice 完成时必须记录 README impact assessment；实际 README 编辑可集中在 Slice E。

停止条件：

- 不得因为移除 CLI durable jobs 而删除 awaiting。
- 不得把 awaiting 语义塞进普通 tool result `meta`。
- 没有明确当前需求证据和 controller / design 裁决时，不得引入 durable operation ledger。
- 不得在无法 poll/resolve/abandon 的情况下删除旧 wait adapter 真源；必须先补 observation source 或停止裁决。

### Slice E: README, design-adjacent docs, and tests synchronization

允许文件 / 模块：

- `dayu/README.md`
- `dayu/service/README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- Slices A-D0-D 已列出的受影响测试

实施步骤：

1. 汇总 Slices A-D0-D 的 README impact assessment，确认每个触发 README 都已判断目标读者与职责范围。
2. 编辑每个 README 前，先阅读其 `Agent更新约束` / README update boundary。
3. 移除声称 CLI direct 启动 durable Fins jobs、消费 job events、使用 terminal fallback 或通过 `request_cancel(job_id)` 取消的描述。
4. 更新 Fins docs，区分 direct stream、business result summary 和 lightweight awaiting observation handle；不得把 process-local handle 描述成 durable recovery 能力。
5. 除非 implementation 实际改变 public boundaries，否则保持 Host/Engine design 文案不变。本 plan 预期不编辑 `docs/host/design.md` 或 `docs/engine/design.md`。
6. 更新 `tests/README.md`，描述新的测试 ownership：direct stream tests、CLI output/cancel tests、awaiting handle tests、stream no-result tests、poll failure tests、redaction/leakage tests。

预期测试：

- 除非仓库已有 docs lint，否则不需要 README 专项测试。implementation gate 必须运行 Slices A-D0-D 的受影响 pytest targets。

Pyright 目标：

- README 没有 pyright target。最终 pyright 命令应包含全部 touched Python files。

README 触发：

- 本 slice 是 README trigger closeout，但不是首次触发判断；每个前置 slice 已经完成 impact assessment。

停止条件：

- 如果 README update boundary 表明目标读者不需要实现细节，不得机械同步实现细节。
- 不得修改 `docs/host/issues-implementation-control.md`；controller 拥有总控文档更新权。

## 测试迁移计划

需要从 durable direct job 改写为 `AsyncIterator[FinsEvent]` 的测试：

- `tests/cli/test_fins_commands.py`：用 fake async event streams 和 cancellation assertions 替换 fake job handles 与 `request_cancel(job_id)` 断言。
- `tests/service/test_fins_direct.py`：用 Service stream contract tests 替换 `read_job_events(...)`、terminal fallback、poll interval、sequence 和 job handle tests。
- `tests/fins/test_fins_ingestion_runtime.py`：移除或改写 sidecar JSONL、per-job sequence、event append WARN、`read_job_events(...)`、queued job persistence tests，除非 D0 durable mini-design 已明确保留最小 awaiting ledger。
- `tests/service/test_fins_direct.py` 或 contract module tests：覆盖 FinsEvent enum/status/字段校验、RESULT success/failure/cancelled 到 exit code 映射、stream no-result 收口。
- `tests/cli/test_fins_commands.py`：覆盖 cancel race、stream no-result、CLI output redaction/leakage guard。
- `tests/fins/test_fins_ingestion_runtime.py`：覆盖 storage repository boundary、runtime leakage guard、blocking bridge cancellation limitation（如适用）。

保留但改语义的 awaiting tests：

- `tests/fins/test_fins_ingestion_tools.py`：保留 `ToolAwaitingOutcome(EXTERNAL_JOB)` 和 start-boundary cancellation；将 `resume_token` 期望从 durable job id 改为 lightweight await ref。
- `tests/fins/test_fins_ingestion_tools.py`：保留 wait adapter terminal/lost/abandon 覆盖，但改为 poll 新的 lightweight observation source；新增 poll transient/permanent failure、poll/resolve/abandon/cancel 状态转换和 Host restart / runtime crash LOST 收口。
- `tests/service/test_host_assembly.py`：如果 adapter lookup 仍需要 explicit Fins awaiting provider binding 和 workspace-root validation，则保留覆盖；移除它服务 CLI direct 的任何暗示。

作为 non-Fins command UI print guards 保留的测试：

- `tests/cli/test_init_command.py`：init UI print 保持正常。
- `tests/cli/test_prompt_command.py`：terminal final answer / failure / cancel output 保持正常；不增加 running token streaming 期望。
- `tests/cli/test_interactive_command.py`：terminal output 保持正常；不增加 running token streaming 期望。
- `tests/cli/test_upload_filings_from_command.py`：script generation output 保持正常，且不启动 live stream。

## 验证计划

本 docs-only gate：

- `git diff --check`

implementation gate 先运行 slice-local tests，再聚合运行：

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -q`
- 当 CLI main/output/log code 被修改时，追加 `tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_upload_filings_from_command.py tests/cli/test_arg_parsing.py`。
- `source .venv/bin/activate && pyright <all touched Python files>`

## 全局停止条件

- 不得修改 Host durable schema、EventLog、Run / Attempt 状态机、Engine `ToolExecutor` contract 或 `ToolAwaitingOutcome` union。
- 不得继续依赖 sidecar JSONL、per-job sequence、`request_cancel(job_id)` 来证明 CLI direct live events。
- 不得用 CLI direct 或“以后可能”证明 durable Fins job store。
- 不得把 Fins direct stream 命名或描述成 `EngineEvent stream`、`Host event stream` 或 Host wait stream。
- 不得让 CLI 或 Service 绕过 `dayu.fins.storage` 仓储协议直接散落读取财报文件。
- 不得为保住旧测试在生产代码中堆兼容 wrapper、compat re-export 或旧路径 facade。
- 如果 lightweight await handle 不能支撑当前 Host wait adapter poll/resolve/abandon/cancel，必须停止并要求 controller 裁决，而不是在 implementation 中临时恢复 durable job system。

## Residual Risks 与 Owner

- UI output redaction：owner `WU-CLI-FINS-OBS-01-R3` / future CLI/Fins UI output redaction policy work unit。当前 plan 只要求 bounded progress/result，不放宽 path/raw/body/content 泄漏限制；系统性 redaction policy 仍需后续审计。
- Prompt / interactive streaming：owner `WU-CLI-FINS-OBS-01-R5` / future Agent command streaming UI work unit。当前 WU 只保护终态 final answer / failure / cancel 输出，不实现运行中 token/content streaming。
- Lightweight await handle durability：owner controller + Slice D0 implementation gate。默认 process-local handle 在 Host restart / runtime crash 后标记 LOST；如果产品要求跨重启继续等待，必须先做最小 durable ledger mini-design。
- Blocking adapter cancellation：owner Slice C implementation gate。若现有 sync adapter 没有可检查取消点，只能提供 best-effort cancellation；如果需要大量 bridge 或强取消语义，必须重新评估 adapter async 化。
- Durable operation ledger possibility：owner controller/design discussion。只有 cross-process / cross-restart 恢复未完成 Fins ingestion 的需求明确成立时，才允许单独设计；不得夹带进 CLI direct replacement。

## 是否需要 Controller 裁决

当前 replacement 方向不需要追加 controller 裁决即可进入 implementation gate。后续只有两类情况必须停下请求 controller / design 裁决：D0 证明 process-local lightweight handle 无法满足当前 Host wait adapter requirement；或 Slice C 证明 native async / cooperative execution 需要被大量 blocking bridge 替代。
