# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins Direct Stream Validator 实施计划

## 0. Gate 身份、结论与本轮边界

- 本计划属于既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU `R09`；不是新 WU，也不重开已裁决产品问题。
- 当前 gate 是 Controller adjudication 后的 plan-only fix。当前任务只允许修改本文件并新增指定 plan-fix artifact；不得修改产品、tests、README、design、control、既有 review/adjudication/completion artifacts，不得 stage、commit、push、创建 PR 或进入 implementation。
- 当前分支为 `phaseflow/host-issues-control`，current-evidence base 为 R08 completion accepted commit `a31ded764da0621b6e7a6c7c6a083b4bb6593d21`。
- `docs/host/issues-implementation-control.md` 的未提交 R09 transition 是 Controller 有意输入；本计划读取它但不修改、覆盖或吸收到本文件之外的 diff。
- 第一性原理结论：问题真实存在且属于 `production-high`。根因不是“多写了几段检查”，而是“direct stream 是否恰好有一个且最后一个 `RESULT`”这一协议事实没有唯一 owner；runtime、Service、CLI 可在不同位置独立判定或掩盖同一事实。
- 最佳修复边界是 Fins typed stream validator。Service 只构造 typed request 并返回 Fins 已验证 stream；CLI 只消费事件、沿用既有用户可读 error prefix/message，并使用 Fins 已证明的 terminal result。
- 本计划结束条件：`R09-PR-F01..F06` 全部关闭，plan 与 plan-fix artifact 通过 plan-only 边界及格式检查后立即停止。下一 gate 只能是 AgentMiMo、AgentDS 对新的 immutable plan target 做双路完整 re-review。

## 1. 必读真源与 temporal evidence

### 1.1 真源优先级

冲突时按以下顺序裁决：

1. 当前用户指令与 `AGENTS.md`；
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 6.5；
3. `docs/fins/design.md` §7；
4. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §7.3/7.4/7.5 与 §16；
5. `docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md` 的 gate、baseline 和 review 成本约束；
6. R08 accepted completion artifacts；
7. current tree 的实现、测试和 README，作为待修对象与直接证据，不反向覆盖设计真源。

### 1.2 current-evidence 时序规则

- 在 R09 accepted-plan local commit 产生前，本计划必须消费 umbrella 的 owner、闭集、最低验证、security、README、smoke 与 propagation baseline，并以当前代码调用链细化 exact 函数、文件和 test node。
- 只有本计划经过双路 plan review、Controller finding adjudication、AgentCodex 修复全部 accepted finding、双路完整 re-review，且 Controller 创建 accepted-plan local commit 后，该 commit 中的最终 plan 才成为 R09 implementation 的唯一 exact execution truth。
- accepted R09 plan 仍不得削弱 umbrella 的唯一 owner、逐 changed production file coverage `>=80%`、full pyright、README decision、真实 smoke、security/no-regression 和 propagation scans。
- implementation entry 前若下表 source lock 漂移，先重做 current-tree 审计。若语义 owner、依赖、production allowlist 或 accepted contract 发生实质变化，必须 stop 并回 Controller；不得用兼容分支或局部 fallback 吞掉漂移。

### 1.3 current evidence locks

| evidence | SHA-256 |
|---|---|
| `dayu/fins/direct_events.py` | `b34cb82d70205a23d1e1853c260ea0c9353567082710699bfc4000e485578cf3` |
| `dayu/fins/ingestion_runtime.py` | `176d8ab974c263f6aedc99b1d8b9a8fbd60ebed441a3aa950d5d9a718c64908a` |
| `dayu/service/fins_direct.py` | `875d5396b1d98bdc28f13480241e081529db5e9fa33416914fa6d47e9663b696` |
| `dayu/cli/commands/fins.py` | `666d9dc2793a706a5f00301f215ca324857e4593fcc4c98b18cc90fdc9e245bf` |
| `tests/fins/test_fins_ingestion_runtime.py` | `6480be571d2118648b7829714b885cd0c8a030b6499ec48625af7d207e57ebf4` |
| `tests/service/test_fins_direct.py` | `9c533d7e632762e3fe02a5ae1c58939d71bc7d8c6cb853bd21ad8b4e3a6f2e9b` |
| `tests/cli/test_fins_commands.py` | `525414da8675fdada4ad458271861cf2801c21f57544d62f436594218dafa26c` |
| current Controller transition `docs/host/issues-implementation-control.md` | `3d9403bcda79cb195e887141bbf75ffeac5e2ea6ca4d9072f9d2718d04461507` |
| `docs/fins/design.md` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| umbrella remediation plan | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` |
| R08 completion evidence | `6e43a30cd3f0409a93963625582941131f143ea8ac188b2dc657f2dac0830e84` |
| R08 completion Controller validation | `80b1a7b313417110c5a88272399ab36cf1e751e4f5b2f5bbecdb96743a500b6e` |

本计划的 immutable review target SHA-256 由本次 plan handoff 报告；两路 reviewer 必须分别记录并匹配同一值。任一 reviewer 开始后 plan 内容变化，旧 review 全部失效，必须对新 SHA 重新双路完整 review。

### 1.4 本次 plan-fix 裁决锁

- 原始 immutable plan：SHA-256 `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210`，689 行。
- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-controller-adjudication.md`，SHA-256 `f615eccf7b2b8db387b5dc1125b95ef5a479c5420cd3c42dff469779a5070643`；它是 `R09-PR-F01..F06` finding disposition 与 required action 的唯一裁决真源。
- AgentDS review：SHA-256 `0434e4766729d2d85c1ade31c767a88ffd47781e7b49b4b734d86ae8a0a53ad9`；AgentMiMo review：SHA-256 `d220c1dd7637d560c835f059841c7effaafe1027b3deb7fe5b1e0919a80b57ac`。两者只作直接证据，不覆盖 Controller 对 close precedence、producer channel、CLI presentation 或 scope 的裁决。
- 本次修订没有发现 owner、依赖或 public contract 的直接设计矛盾，因此不触发 STOP；若 re-review 发现与 Controller 已裁决 contract 冲突的新直接证据，仍必须回 Controller，不得由 implementation 自行改义。

## 2. 当前调用链与 root cause 直接证据

### 2.1 真实生产调用链

```text
dayu-cli command
  -> dayu.cli.commands.fins._open_direct_stream
  -> dayu.service.fins_direct.FinsDirectCommandService
       .download / .process* / .upload_*
  -> dayu.fins.ingestion_runtime.FinsIngestionRuntime
       .download / .preprocess / .upload
  -> FinsIngestionRuntime._run_direct_stream
  -> sync producer thread + direct queue
  -> _run_direct_stream_producer
  -> _produce_direct_download / _produce_direct_preprocess / _produce_direct_upload
  -> _emit_context_progress / _emit_direct_result
```

Production direct caller 只有 `dayu/service/fins_direct.py`；Fins awaiting tools 使用 `prepare_observed_*` / `activate_observation`，不是 Service/CLI direct stream consumer。`DefaultFinsRuntime.get_ingestion_runtime()` 只提供装配，不拥有 terminal invariant。

### 2.2 三处分散 decision 的实际形态

| 层与函数 | 当前 decision | 当前 error/code | 当前关闭/取消行为 | 必须删除/迁移的精确分支 |
|---|---|---|---|---|
| Fins `FinsIngestionRuntime._run_direct_stream` | 缓存首个 `RESULT`；第二个 `RESULT` 抛 duplicate；producer done 无 `RESULT` 抛 missing；done 后才 yield 缓存结果 | 新建 `FinsDirectStreamProtocolError`，`reason` 为 `DUPLICATE_RESULT` 或 `MISSING_RESULT` | `finally` 只调用 `_DirectStreamCancellationState.request_cancel()`；public `download/preprocess/upload` 另用一层 `async for ... yield` 包裹 | 删除 `_run_direct_stream` 内 `result_event`、duplicate/missing 构造和终态 yield 分支；raw bridge 只消费现有 event/done queue item、只 yield raw event，bridge 的 native async error/cancel自然传播，再交给唯一 validator |
| Service `_ensure_result_event` | 对 runtime stream 再次缓存首个 `RESULT`，重复判定 duplicate/missing，再 yield 缓存结果 | 重新构造同类型 error；`operation_kind` 来自 Service command，因此 `process_filing/material` 可与 runtime `PREPROCESS` 来源不同 | 无 catch；当前取消测试证明 task cancellation 会退出 wrapper 并关闭 fake runtime generator | 整个删除 `_ensure_result_event`；六个 public method 删除包装调用和只为 wrapper 服务的 `operation_kind/ticker/filing_kind/document_label` 参数；Service 不再 import error kind 或事件类型用于校验 |
| CLI `_consume_fins_direct_events` | 遇到首个 `event.result is not None` 立即返回；正常耗尽则自行判定 missing | CLI 自行构造 `MISSING_RESULT`；CLI **当前没有 duplicate checker** | `_wait_for_terminal_handling_sigint` 请求 operation token cancel、cancel event task；收到 terminal race 时保留 terminal，否则本地 130；finally 关闭 signal monitor 并取消未完成 task | 删除正常耗尽时构造 missing 的 fallback；删除仅为该 fallback 传递的 `operation_kind` 参数及 `_direct_operation_kind`；不新增 duplicate/event-after fallback |

umbrella 对“CLI scans again”的命名只能解释为 CLI 对 terminal existence 的第三次 decision；actual evidence 不支持“CLI 还检查 duplicate”。R09 必须按上述实际形态修复，不能为了匹配旧叙述给 CLI 新增 duplicate 分支。

### 2.3 当前缺陷的反例

- runtime 与 Service 都会在首个 `RESULT` 后继续接受 progress，并最终把该 progress 排到缓存 `RESULT` 前面；无一层产生 `EVENT_AFTER_RESULT`。无效序列因此被重排成表面合法序列。
- missing/duplicate error 可以由 runtime、Service 或 CLI 中不同函数创建；同一 code 的 object、message 与 `operation_kind` 来源不唯一。
- CLI 在首个 result 返回，因此它的正确性依赖上游已经 drain 完成；该依赖目前由两层重复 wrapper 偶然保证，而非一个 typed owner contract 明示保证。
- producer callees 当前没有 `FinsDirectStreamProtocolError` origin；`_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone` 已完整表达真实 producer 数据流。producer 的 generic execution exception 继续映射为有界 business failure `RESULT`，raw queue bridge 自身的 native async error/cancellation 则由 async generator 自然传播。
- 外层 async-generator wrapper 的 `aclose()` 不构成一个显式的 raw-source close contract；唯一 validator 必须直接拥有 raw source lifecycle，不能依赖 Service/CLI wrapper 的偶然 finalization。

## 3. 唯一语义 owner 与 public contract

### 3.1 owner 定义

唯一 owner 是新增的 `dayu.fins.direct_stream.ValidatedFinsEventStream`。它独占：

- 判断 direct stream 是否恰好有一个 `RESULT`；
- 判断该 `RESULT` 是否为最后一个 event；
- 缓存首个 `RESULT` 直到 raw upstream clean EOF；
- 产生全部三种 typed protocol error；
- 持有 raw async generator 的 `aclose` 生命周期；
- 在 clean exhaustion 后提供同一个 `FinsResultSummary` 实例给机械 consumer。

`dayu/fins/direct_events.py` 只拥有事件、结果和 error data contract；`ingestion_runtime.py` 负责 producer/queue 接入；Service/CLI 均不是 validator owner。

新增 `direct_stream.py` 有充分证据：`direct_events.py` 已是 495 行纯契约/校验模块，`ingestion_runtime.py` 是 6,932 行并同时承载 direct、observation、legacy runtime；把可独立测试的 async 状态机继续塞入任一文件都会混合 contract 或扩大 God runtime。新模块只承载一个状态机与其私有状态，不建立 framework、factory、profile 或兼容层。

### 3.2 精确接口

```python
class ValidatedFinsEventStream(AsyncIterator[FinsEvent]):
    def __init__(
        self,
        source: AsyncGenerator[FinsEvent, None],
        *,
        operation_kind: FinsOperationKind,
    ) -> None: ...

    def __aiter__(self) -> ValidatedFinsEventStream: ...

    async def __anext__(self) -> FinsEvent: ...

    async def aclose(self) -> None: ...

    @property
    def terminal_result(self) -> FinsResultSummary: ...
```

- 不增加仅透传构造器的 factory/wrapper，不在 `dayu.fins.__init__` 做兼容 re-export。
- `source` 是 runtime 自己创建且支持 `aclose()` 的 `AsyncGenerator[FinsEvent, None]`，不使用 `hasattr/getattr` 或 loose close probing。
- `terminal_result` 返回 validator 缓存的同一 result object，不重算、不复制、不从最后事件之外推断；只允许在 clean exhaustion 后读取。OPEN、RESULT_BUFFERED 或 consumer/error/cancel 导致的 abortive close 后读取，统一抛普通 `RuntimeError`，消息固定来自 `direct_stream.py` 模块私有常量 `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE = "Fins direct terminal result is not available before clean stream exhaustion"`。这属于调用方 programmer-contract violation，不是 missing/duplicate/event-after stream protocol error；不新增 public 或 private error class。
- `FinsIngestionRuntime.download/preprocess/upload`、Service protocol 与 Service public methods 的精确返回类型改为 `ValidatedFinsEventStream`；CLI stream helpers 接收/返回同一类型，不把强 contract 降回无语义的裸 `AsyncIterator`。
- 新/改模块、类、函数、方法全部提供中文 docstring，完整写明参数、返回值与异常；签名不使用 `Any`、`object`、裸容器或无类型返回值。

### 3.3 typed error/code contract

- 继续使用唯一 error object `FinsDirectStreamProtocolError` 与唯一 enum `FinsDirectStreamProtocolErrorKind`，不另建 parallel error schema。
- enum 增加 `EVENT_AFTER_RESULT = "event_after_result"`；既有 code 保持 `missing_result`、`duplicate_result`。
- 三个 owner message 使用 `direct_stream.py` 模块私有常量：missing 固定为 `"Fins direct stream ended without RESULT"`，duplicate 固定为 `"Fins direct stream produced multiple RESULT events"`，event-after 固定为 `"Fins direct stream produced an event after RESULT"`。消息不拼接 provider payload、path、ticker、document id 或 raw exception text。
- canonical typed reason 是 `exc.reason`，其序列化值仍由 enum 的 `reason.value` 唯一给出；不增加 `code` alias/property，不保留旧名字 wrapper。该 typed reason 是 Fins owner/test contract，不因此成为新的 CLI public error-code format。
- error 同时携带 Fins runtime 输入的 `operation_kind` 和 Fins owner 产生的有界 `message`。
- Fins validator 是三种 protocol error 的唯一构造点。Service 不 catch、不重建、不改 `reason/operation_kind/message/object`；CLI 只在最终 presentation boundary catch 同一类型，沿用现有 `dayu-cli {command_name}: {exc.message}` 与 `EXIT_FAILURE=1`。
- CLI 不 import/枚举 typed reason、不读取 `reason.value`、不从消息文本判断 reason，也不重建 error；Fins owner tests 直接断言 enum，Service/CLI propagation tests 断言同源字段、object identity 与既有 presentation，而不是让上层取得 semantic ownership。

### 3.4 exact old/new signature 与 call-site cutover（R09-PR-F01）

下表中的 callable 参数列表除显式删除的 CLI `operation_kind` 外保持原样；“plain `def`”表示调用立即得到 stream object，不产生 coroutine。表内列出的每个 Service public method 均保持 plain `def`，且不得通过 `async for`、`yield`、`await` 或 wrapper 重建 stream。

| boundary / exact callable | old signature shape | new signature shape | exact call-site contract |
|---|---|---|---|
| runtime `download(self, request: FinsDownloadRequest, *, cancellation_token: CancellationToken | None = None)` | `async def ... -> AsyncIterator[FinsEvent]`，方法体含 `yield`，调用结果是 async generator | `def ... -> ValidatedFinsEventStream` | public method 直接构造并返回 `ValidatedFinsEventStream(source=self._run_direct_stream(...), operation_kind=FinsOperationKind.DOWNLOAD)`；无外层 `async for/yield` |
| runtime `preprocess(self, request: FinsPreprocessRequest, *, cancellation_token: CancellationToken | None = None)` | `async def ... -> AsyncIterator[FinsEvent]`，方法体含 `yield` | `def ... -> ValidatedFinsEventStream` | 直接传入 runtime owner 值 `FinsOperationKind.PREPROCESS`；Service command alias 不得替换该值 |
| runtime `upload(self, request: FinsUploadRequest, *, cancellation_token: CancellationToken | None = None)` | `async def ... -> AsyncIterator[FinsEvent]`，方法体含 `yield` | `def ... -> ValidatedFinsEventStream` | 直接传入 `_direct_upload_operation_kind(normalized_request)` 的 Fins owner 值 |
| raw bridge `_run_direct_stream(self, *, operation_kind: FinsIngestionOperationKind, direct_operation_kind: FinsOperationKind, normalized: NormalizedTicker, source: str | None, source_kind: SourceKind | None, cancellation_token: CancellationToken | None, producer: Callable[[_FinsIngestionExecutionContext], None])` | `async def ... -> AsyncIterator[FinsEvent]`，async generator 内含 terminal checker | `async def ... -> AsyncGenerator[FinsEvent, None]`，仍是 concrete raw async generator | 只转发现有 `FinsEvent` / producer done，native async error/cancel 自然传播，并在 `finally` 请求 cancellation；不再判断 terminal protocol |
| Service protocol `download(self, request: FinsDownloadRequest, *, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | 只收窄返回 contract，不变成 coroutine |
| Service protocol `preprocess(self, request: FinsPreprocessRequest, *, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | 只收窄返回 contract，不变成 coroutine |
| Service protocol `upload(self, request: FinsUploadRequest, *, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | 只收窄返回 contract，不变成 coroutine |
| Service public `download(self, *, ticker: str, form_types: tuple[str, ...] = (), filed_after: str | None = None, filed_before: str | None = None, overwrite_existing: bool = False, rebuild_processed: bool = False, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | typed request/log 后直接 return runtime stream identity |
| Service public `process(self, *, ticker: str, source_kind: SourceKind, document_ids: tuple[str, ...] = (), form_types: tuple[str, ...] = (), rebuild_processed: bool = False, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | 经 typed request helper 直接 return runtime stream identity |
| Service public `process_filing(self, *, ticker: str, document_ids: tuple[str, ...] = (), form_types: tuple[str, ...] = (), rebuild_processed: bool = False, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | entry alias 不替换 runtime validator 的 `PREPROCESS` provenance |
| Service public `process_material(self, *, ticker: str, document_ids: tuple[str, ...] = (), form_types: tuple[str, ...] = (), rebuild_processed: bool = False, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | entry alias 不替换 runtime validator 的 `PREPROCESS` provenance |
| Service public `upload_filing(self, *, ticker: str, action: str, files: tuple[Path, ...], fiscal_year: int | None = None, fiscal_period: str | None = None, amended: bool = False, filing_date: str | None = None, report_date: str | None = None, company_name: str | None = None, ticker_aliases: tuple[str, ...] = (), overwrite: bool = False, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | typed request/log 后直接 return runtime stream identity |
| Service public `upload_material(self, *, ticker: str, action: str, files: tuple[Path, ...], form_type: str | None = None, material_name: str | None = None, document_id: str | None = None, internal_document_id: str | None = None, fiscal_year: int | None = None, fiscal_period: str | None = None, amended: bool = False, filing_date: str | None = None, report_date: str | None = None, company_name: str | None = None, ticker_aliases: tuple[str, ...] = (), overwrite: bool = False, cancellation_token: CancellationToken | None = None)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | typed request/log 后直接 return runtime stream identity |
| Service private `_preprocess(self, *, operation_kind: FinsOperationKind, ticker: str, source_kind: SourceKind, document_ids: tuple[str, ...], form_types: tuple[str, ...], rebuild_processed: bool, cancellation_token: CancellationToken | None)` | plain `def ... -> AsyncIterator[FinsEvent]`，经 `_ensure_result_event` 包装 | plain `def ... -> ValidatedFinsEventStream` | `operation_kind` 如保留只用于 command 日志；直接 return `self._runtime.preprocess(...)`，不 await/iterate/wrap；error provenance 只能来自 runtime validator 输入 |
| CLI plain helpers `_open_direct_stream/_download_stream/_upload_filing_stream/_upload_material_stream/_process_stream/_process_filing_stream/_process_material_stream`，共同参数均为 `(*, args: ParsedCliArgs, service: FinsDirectCommandService, cancellation_token: _CliFinsCancellationToken)` | plain `def ... -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | `stream = _open_direct_stream(...)` 保持无 `await`；六路 Service call 均无新增 `await` |
| CLI `async def _wait_for_terminal_handling_sigint(*, events: AsyncIterator[FinsEvent], cancellation_token: _CliFinsCancellationToken, sigint_monitor: CliSigintMonitor, command_name: str, operation_kind: FinsOperationKind) -> FinsResultSummary | _CliDirectLocalExit` | 左列当前签名 | `async def _wait_for_terminal_handling_sigint(*, events: ValidatedFinsEventStream, cancellation_token: _CliFinsCancellationToken, sigint_monitor: CliSigintMonitor, command_name: str) -> FinsResultSummary | _CliDirectLocalExit` | 仍由既有 async caller `await`；只删除 fallback 所需参数，不新增 await |
| CLI `async def _consume_fins_direct_events(events: AsyncIterator[FinsEvent], *, operation_kind: FinsOperationKind) -> FinsResultSummary` | 左列当前签名 | `async def _consume_fins_direct_events(events: ValidatedFinsEventStream) -> FinsResultSummary` | `async for` 渲染完整 validated stream，clean loop 后直接读 `events.terminal_result`；不解析/枚举/rebuild error |

Service 的 `process_filing/process_material` 名称与 runtime validator 的 `PREPROCESS` 值有意不同：前者只是入口/日志语义，后者才是 direct stream error provenance。R09-S2 tests 必须用这个反例证明返回类型收窄与机械透传没有把 Service alias 变成新的 semantic owner。

## 4. 完整状态机与生命周期

```text
OPEN
  PROGRESS
    -> yield 原 event
    -> OPEN
  first RESULT
    -> buffer event 与其中同一 FinsResultSummary
    -> RESULT_BUFFERED
  clean upstream EOF
    -> FinsDirectStreamProtocolError(MISSING_RESULT)
    -> CLOSED
  upstream error / cancellation
    -> 记录其同一 object 为 primary semantic error
    -> cleanup close raw source at most once
    -> cleanup 失败时作为 primary 的显式 exception cause 保留
    -> primary 原 object 原样传播
    -> CLOSED

RESULT_BUFFERED
  second RESULT
    -> 构造 FinsDirectStreamProtocolError(DUPLICATE_RESULT) 作为 primary
    -> cleanup close raw source at most once
    -> cleanup 失败时作为 primary 的显式 exception cause 保留
    -> primary typed error 原 object 传播
    -> CLOSED
  any later PROGRESS
    -> 构造 FinsDirectStreamProtocolError(EVENT_AFTER_RESULT) 作为 primary
    -> cleanup close raw source at most once
    -> cleanup 失败时作为 primary 的显式 exception cause 保留
    -> primary typed error 原 object 传播
    -> CLOSED
  upstream error / cancellation
    -> 丢弃 buffered RESULT
    -> 记录其同一 object 为 primary semantic error
    -> cleanup close raw source at most once
    -> cleanup 失败时作为 primary 的显式 exception cause 保留
    -> primary 原 object 原样传播
    -> CLOSED
  clean upstream EOF
    -> yield buffered RESULT exactly once
    -> RESULT_YIELDED

RESULT_YIELDED
  next __anext__
    -> StopAsyncIteration
    -> CLOSED

any non-CLOSED state + consumer aclose()
  -> 没有 pre-existing semantic error
  -> attempt close raw source at most once
  -> discard buffered RESULT if not yielded
  -> source close error 按同一 object 原样传播
  -> subsequent aclose() 不再次调用底层 close，包括首次 close 已失败的情况
  -> CLOSED
```

不变量：

1. 只有 clean upstream EOF 能证明首个 `RESULT` 唯一且最后，进而允许 yield。
2. `result -> error` 不得先发布 success；buffered result 被丢弃，原 error 传播。
3. primary semantic error 的唯一优先级 contract 是：upstream exception/cancellation 的原 object，或 validator 已构造的 duplicate/event-after typed error，始终是最终传播的 type/object/reason/operation_kind/message；cleanup `aclose()` failure 不得覆盖它。cleanup failure 通过显式 chaining（`raise primary from cleanup_error`，因此 `primary.__cause__ is cleanup_error`）保留，不另建 aggregate/wrapper，也不改变 CLI exit mapping。
4. 显式 consumer `aclose()` 时若没有 pre-existing semantic error，底层 close failure 必须以同一 exception object 原样传播。validator 以私有 close-attempted guard 保证底层 `aclose()` 最多调用一次；首次成功或失败后，重复 `aclose()` 均不得重试。该 guard 不引入 `CLOSED_CLEAN/CLOSED_ABORTED` 新状态；terminal availability 仍由单独的 clean-exhaustion flag 唯一表达。
5. validator 不 catch 后转写 producer/upstream exception，不把 cancel、close 或 protocol error 合成为 business `RESULT`。现有 producer 显式产生的 `FinsResultSummary(status=FAILURE|CANCELLED)` 仍是合法业务 terminal，不属于 protocol error；不得把这些合法结果反向改成 exception。
6. `_run_direct_stream_producer` 对既有 generic execution exception 的有界 business-failure `RESULT` 映射保持现状；`_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone` 保持不变。raw bridge 的 native async error/cancellation 由 async generator 自然传播，validator 是 missing/duplicate/event-after 三种 protocol error 的唯一构造 owner。共享 observed path 只做其既有 failed snapshot 映射，不取得 direct terminal invariant ownership。
7. `terminal_result` 只有 clean exhaustion 后可读；OPEN、RESULT_BUFFERED 和所有 abortive close 路径使用 §3.2 的同一 module-owned safe message 抛普通 `RuntimeError`。clean exhaustion 后返回 buffered result 中的同一 `FinsResultSummary` object。
8. CLI SIGINT 仍由 operation-scoped cancellation token + event task cancellation 驱动；validator 的 cancellation/close 只负责 raw stream lifecycle，不新增 job id cancel、Host state 或线程强杀。

## 5. 实施闭集与逐文件改动

### 5.1 production allowlist（闭集）

1. `dayu/fins/direct_events.py`
2. `dayu/fins/direct_stream.py`（新增，且必须真正执行上述状态机）
3. `dayu/fins/ingestion_runtime.py`
4. `dayu/service/fins_direct.py`
5. `dayu/cli/commands/fins.py`

若真实 producer 接入需要上述集合外任何 production/config/package 文件，立即触发 plan-review stop，由 Controller 决定是否调整 R09 scope；implementation 不得现场扩域。

### 5.2 test allowlist（精确闭集）

1. `tests/fins/test_fins_direct_stream.py`（新增 owner contract tests）
2. `tests/fins/test_fins_ingestion_runtime.py`
3. `tests/service/test_fins_direct.py`
4. `tests/cli/test_fins_commands.py`

### 5.3 README allowlist 与 trigger decision

plan-fix gate 已 fresh scan 下列 README；本轮只记录 decision，不修改任何 README：

| README | fresh SHA-256 / direct evidence | implementation decision |
|---|---|---|
| 根 `README.md` | `2f5cebfd3bf82b7099ff11f94e7a1e0df3840ca13fc41324a9d4ae99a02a6e6a`；面向最终用户，当前没有 Fins direct protocol reason/error-code format 章节，也没有 `missing_result/duplicate_result/event_after_result` literal | **no update**。R09 保持 command/参数、现有 `dayu-cli {command}: {message}`、success/failure/cancel exit `0/1/130`、输出通道、工作区位置与用户工作流，不新增 `[reason.value]` public format |
| `dayu/README.md` | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367`；只拥有总揽分层与跨包稳定边界，当前 `AsyncIterator[FinsEvent]` 叙述仍由 concrete validated subtype满足 | **no update**。`UI -> Service -> Host -> Engine`、Fins 装配和 direct/awaiting 边界均不变 |
| `dayu/fins/README.md` | `50c07ae625188c470c2818405d445772d073bc67496dcb58f57362720479dd4f`；当前 line 511 明确写 plain `AsyncIterator` 且只覆盖 missing/duplicate | **implementation 必须更新**。按其 Agent 约束，在代码落地后写当前 concrete validator、buffer-until-clean-EOF、event-after 与唯一 Fins owner |
| `dayu/service/README.md` | `8d7d7680e82642a769da9a3acc28ea429f8ff32550dff732e6a0478c7aabb2d5`；当前 lines 15/35 明确把 terminal 收口与 missing/duplicate error 归给 Service | **implementation 必须更新**。改为 typed request + concrete validated stream identity pass-through；不声称 Service 校验 protocol |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454`；当前 lines 149/196 将 missing/duplicate checker 归给 Service/runtime | **implementation 必须更新**。owner tests 归 Fins validator，Service/CLI 只覆盖 provenance identity 与 presentation |

若 implementation 实际改变根 README 或 `dayu/README.md` 职责内的用户工作流、已有 public presentation/exit contract或分层，先 stop 重做 README trigger；不得用 README 扩写为无产品依据的 CLI raw enum format。

### 5.4 逐 production 文件改动

#### `dayu/fins/direct_events.py`

- 向 `FinsDirectStreamProtocolErrorKind` 增加唯一 `EVENT_AFTER_RESULT` code。
- 保留 `FinsDirectStreamProtocolError(reason, operation_kind, message)`、现有 result/error/event schema 与 leakage guards；不新增 alias、默认值、兼容 parser 或 message-to-code 映射。

#### `dayu/fins/direct_stream.py`（新增）

- 提供中文模块概览 docstring。
- 实现私有有限状态枚举和 `ValidatedFinsEventStream`；所有 protocol decision、三种 protocol message 常量与 `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE` 只在本模块。
- `__anext__` 实现 §4 状态机；`StopAsyncIteration` 只用于 clean EOF 判定。其他 upstream `BaseException` 仅为执行一次 cleanup 而临时截获，随后以同一 primary object 原样重抛；cleanup failure 按 §4 chaining，不做类型/消息转换。
- duplicate/event-after 构造 typed primary error 后 cleanup close source；cleanup failure 作为同一 primary 的显式 cause 保留，不覆盖 type/object/reason/operation_kind/message。
- upstream error/cancellation 同样保持原 object 为 primary；cleanup close failure 只进入 chaining。`aclose()` 以 close-attempted guard 保证底层至多调用一次，不 yield/synthesize result。
- 没有 pre-existing semantic error 的显式 consumer `aclose()` 以同一 object 传播 source close failure；重复 close 不重试。
- `terminal_result` 只返回 clean exhaustion 后已证明的同一 result object；其余状态按 §3.2 抛普通 `RuntimeError`，不新增 error class。

#### `dayu/fins/ingestion_runtime.py`

- 将 `download/preprocess/upload` 按 §3.4 从含 `yield` 的 `async def` async generator 改为 plain `def -> ValidatedFinsEventStream`，删除三处外层 `async for ... yield` 包装；三个方法直接组合 existing raw bridge 与 validator，不新增 factory/wrapper。
- `_run_direct_stream` 保持 raw queue async generator，返回类型收窄为 `AsyncGenerator[FinsEvent, None]`；只转发 existing `FinsEvent` / producer done 并在 `finally` 请求 cancellation，bridge 自身 native async error/cancel 自然传播。
- 删除现 `_run_direct_stream` 的 `result_event`、duplicate、missing 和 buffered yield 分支。
- `_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone` 与 `_run_direct_stream_producer` 的 generic execution-exception-to-bounded-business-failure-`RESULT` mapping 原样保留，不修改其类型或 control flow。
- 保留 generic producer exception 的既有 bounded failure-result mapping、operation cancellation checker、queue backpressure、consumer-close cancellation state、daemon producer 与 storage behavior。

#### `dayu/service/fins_direct.py`

- `FinsDirectIngestionRuntime` protocol 和全部 public direct methods 改为返回 `ValidatedFinsEventStream`。
- 六个 public method直接返回 runtime stream；仍负责 typed request 构造和日志，不读取 storage、不碰 CLI。
- 整体删除 `_ensure_result_event` 及其所有调用。
- 删除只为重复 checker 服务的 imports/参数/分支；Service 不构造或 catch protocol error。

#### `dayu/cli/commands/fins.py`

- stream opener/helper、`_wait_for_terminal_handling_sigint`、`_consume_fins_direct_events` 使用 `ValidatedFinsEventStream`。
- `_consume_fins_direct_events` 渲染整个已验证流，循环结束后直接返回 `events.terminal_result`；删除首个 result 即返回所承担的终态 decision 和 end-of-stream missing fallback。
- 删除 `_direct_operation_kind` 及只为 fallback 传递的 `operation_kind` 参数。
- 保留 SIGINT race、operation token cancellation、本地 130、event rendering 与 result exit code mapping。
- `run_fins_direct_command` catch owner error时严格沿用现有 `render_cli_error(f"dayu-cli {args.command_name}: {exc.message}")`，返回既有 `EXIT_FAILURE`；不得展示 raw `reason.value`，不得 import/枚举 reason、解析 message 或重建 error。

### 5.5 精确删除清单

- `dayu/service/fins_direct.py::_ensure_result_event` 全函数及六处调用。
- `dayu/cli/commands/fins.py::_direct_operation_kind` 全函数。
- `dayu/cli/commands/fins.py::_consume_fins_direct_events` 尾部 `FinsDirectStreamProtocolError(MISSING_RESULT, ...)` fallback。
- CLI `_wait_for_terminal_handling_sigint` / `_consume_fins_direct_events` 的 `operation_kind` 参数与调用参数。
- `dayu/fins/ingestion_runtime.py::_run_direct_stream` 内本地 `result_event`、duplicate/missing error 构造、done 后 terminal yield。
- Service/CLI 对 `FinsDirectStreamProtocolErrorKind`、`FinsEventType` 等仅为 checker 存在的 imports。
- 旧 Service/CLI tests 中让 fake/mock 自己固化“Service/CLI 应验证 missing/duplicate”的断言与命名。

### 5.6 不得修改清单

- `docs/host/issues-implementation-control.md`、`docs/fins/design.md`、umbrella plan、R08 plan/review/completion/prior artifacts。
- R06 transaction/publication、R07 snapshot/citation/opaque identity、R08 financial/XBRL production/test paths。
- `dayu/fins/direct_event_text.py`、`dayu/cli/output.py`、`dayu/fins/service_runtime.py`、`dayu/fins/ingestion/observation_handle.py`。
- Fins storage、downloaders、pipelines、processors、tools、Host/Engine/runtime/config、Web/WeChat/render。
- 根 README、`dayu/README.md`、其它 README。
- 不新增 compatibility re-export/wrapper、旧 schema、fallback、loose parsing、`hasattr/getattr`、默认 terminal、通用 authorization/error framework。

## 6. Slices、依赖与 cutover

### 6.1 R09-S1 — Fins validator owner

范围：

- `dayu/fins/direct_events.py`
- `dayu/fins/direct_stream.py`
- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_direct_stream.py`
- `tests/fins/test_fins_ingestion_runtime.py`

交付：Fins owner 状态机、runtime raw producer 接入、typed upstream error/cancel/close 传播、owner/integration tests。S1 结束时现有 Service checker 仍可能重复观察已经验证的流，但不允许删除 Fins owner；这是未接受的工作树 checkpoint，不是可发布 contract。

### 6.2 R09-S2 — Service/CLI mechanical consumer

依赖：R09-S1 同一未提交树。

范围：

- `dayu/service/fins_direct.py`
- `dayu/cli/commands/fins.py`
- `tests/service/test_fins_direct.py`
- `tests/cli/test_fins_commands.py`
- `dayu/fins/README.md`
- `dayu/service/README.md`
- `tests/README.md`

交付：删除 Service/CLI duplicate/missing decision，传播 typed stream contract，保留 presentation/cancellation，完成 README 同步。

### 6.3 acceptance 与 zero-validator 防线

- R09 采用 **cumulative single sub-WU acceptance**，不是独立 slice acceptance。
- S1 只形成 implementation checkpoint/artifact与 focused validation，不 stage、不 commit、不进入独立 accepted slice review。
- S2 必须叠加在同一 S1 tree；完成后对 S1+S2 immutable cumulative diff做双路完整 code review、fix、双路完整 rereview、aggregate/completion，再形成一个 R09 accepted implementation commit。
- accepted history 从“旧 runtime+Service+CLI 分散 decision”一次切换为“Fins 唯一 validator + mechanical Service/CLI”。任何可 accepted tree 均不得出现 zero-validator；也不得把 S2 删除 checker 的 commit 放在 S1 owner 之前。
- 最终 tree 不得保留 Service/CLI fallback、duplicate checker、旧 schema、compatibility wrapper 或旧 fake-only validator。

## 7. Test migration 与精确 nodes

以下标为“current”的 node 已在 current tree 核验；标为“新增/替换”的 node 是 implementation 必须创建的 output contract，不冒充当前已存在 node。

### 7.1 R09-S1 owner tests

新增 `tests/fins/test_fins_direct_stream.py`：

- `[新增] test_validated_stream_yields_progress_then_buffered_result_only_after_clean_end`
- `[新增] test_validated_stream_missing_result_uses_fins_owned_typed_code`
- `[新增] test_validated_stream_duplicate_result_is_primary_and_closes_source_once`
- `[新增] test_validated_stream_event_after_result_is_primary_and_closes_source_once`
- `[新增] test_validated_stream_upstream_error_identity_is_primary_and_closes_source_once`
- `[新增] test_validated_stream_upstream_cancellation_identity_is_primary_and_closes_source_once`
- `[新增] test_validated_stream_duplicate_error_stays_primary_when_cleanup_close_fails`
- `[新增] test_validated_stream_event_after_result_error_stays_primary_when_cleanup_close_fails`
- `[新增] test_validated_stream_upstream_error_stays_primary_when_cleanup_close_fails`
- `[新增] test_validated_stream_upstream_cancellation_stays_primary_when_cleanup_close_fails`
- `[新增] test_validated_stream_result_then_error_propagates_same_error_without_result`
- `[新增] test_validated_stream_explicit_aclose_propagates_same_close_error_without_primary`
- `[新增] test_validated_stream_repeated_aclose_closes_source_once`
- `[新增] test_validated_stream_repeated_aclose_after_close_failure_does_not_retry_source`
- `[新增] test_validated_stream_terminal_result_in_open_raises_owned_runtime_error`
- `[新增] test_validated_stream_terminal_result_while_result_buffered_raises_owned_runtime_error`
- `[新增] test_validated_stream_terminal_result_after_abortive_close_raises_owned_runtime_error`
- `[新增] test_validated_stream_terminal_result_after_clean_exhaustion_is_same_object`

上述 close/error tests 的 exact assertion contract：duplicate/event-after 的 `reason/operation_kind/message/object` 保持 primary；upstream exception 与 `asyncio.CancelledError` 以 `is` 保持 primary；cleanup failure 时 `captured.value is primary` 且 `captured.value.__cause__ is close_error`；显式 consumer close 没有 primary 时 `captured.value is close_error`；成功或失败后的重复 `aclose()` 均断言 raw source close call count 恰为 `1`。terminal availability 四个 tests 均断言普通 `RuntimeError` 与 `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE`，clean case 断言 `terminal_result is buffered_result`，不新增 error subclass。

迁移 `tests/fins/test_fins_ingestion_runtime.py`：

- 删除 current `test_direct_stream_missing_result_raises_protocol_error`、`test_direct_stream_duplicate_result_raises_protocol_error`、`test_direct_stream_drains_to_done_before_yielding_result` 中对 runtime 私有重复状态机的固化；其协议断言由新 owner test承接。
- 保留并纳入 S1 回归：
  - current `test_direct_download_stream_writes_storage_and_does_not_create_job_record`
  - current `test_direct_download_unsupported_source_returns_failure_result`
  - current `test_direct_download_uses_operation_scoped_cancellation_token`
  - current `test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text`

S1 精确 pytest 命令：

```bash
source .venv/bin/activate
pytest -q \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py::test_direct_download_stream_writes_storage_and_does_not_create_job_record \
  tests/fins/test_fins_ingestion_runtime.py::test_direct_download_unsupported_source_returns_failure_result \
  tests/fins/test_fins_ingestion_runtime.py::test_direct_download_uses_operation_scoped_cancellation_token \
  tests/fins/test_fins_ingestion_runtime.py::test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text
```

### 7.2 R09-S2 Service tests

`tests/service/test_fins_direct.py`：

- current `test_download_stream_builds_request_and_yields_progress_result`
- current `test_process_methods_build_preprocess_requests`
- current `test_upload_methods_build_union_requests`
- current `test_failure_result_is_passed_through`
- current `test_stream_exception_is_propagated_without_synthetic_result`
- `[替换] test_fins_owned_protocol_error_fields_and_object_are_propagated_by_identity`，替代 current `test_stream_without_result_raises_protocol_error` 与 `test_duplicate_result_fails_fast` 的 Service-owned checker 断言；Service 返回的必须是同一个 owner stream/error，不重建字段或 object。
- `[新增] test_process_filing_keeps_runtime_preprocess_protocol_error_provenance`
- `[新增] test_process_material_keeps_runtime_preprocess_protocol_error_provenance`
- current `test_task_cancellation_closes_runtime_stream`
- current `test_service_public_direct_api_does_not_export_job_handle`
- current `test_fins_event_contract_rejects_invalid_progress_and_result_shapes`
- current `test_fins_result_exit_code_mapping_is_fixed`
- current `test_fins_event_leakage_guard_rejects_internal_or_sensitive_text`

```bash
source .venv/bin/activate
pytest -q \
  tests/service/test_fins_direct.py::test_download_stream_builds_request_and_yields_progress_result \
  tests/service/test_fins_direct.py::test_process_methods_build_preprocess_requests \
  tests/service/test_fins_direct.py::test_upload_methods_build_union_requests \
  tests/service/test_fins_direct.py::test_failure_result_is_passed_through \
  tests/service/test_fins_direct.py::test_stream_exception_is_propagated_without_synthetic_result \
  tests/service/test_fins_direct.py::test_fins_owned_protocol_error_fields_and_object_are_propagated_by_identity \
  tests/service/test_fins_direct.py::test_process_filing_keeps_runtime_preprocess_protocol_error_provenance \
  tests/service/test_fins_direct.py::test_process_material_keeps_runtime_preprocess_protocol_error_provenance \
  tests/service/test_fins_direct.py::test_task_cancellation_closes_runtime_stream
```

### 7.3 R09-S2 CLI tests

`tests/cli/test_fins_commands.py`：

- current `test_live_fins_commands_render_progress_and_terminal_summary`
- current `test_download_command_maps_args_to_service`
- current `test_upload_commands_map_args_and_validate_files`
- current `test_process_commands_map_to_service`
- current `test_terminal_failed_and_cancelled_status_exit_mapping`
- `[替换] test_fins_owned_missing_result_uses_existing_cli_error_presentation`，替代 current `test_stream_without_result_returns_protocol_error` 的 CLI-owned fallback；断言 exact 既有 prefix/message 与 exit 1，不展示/断言 raw `reason.value`。
- `[替换] test_fins_owned_duplicate_result_uses_existing_cli_error_presentation`，由 Fins validator 注入，不让 fake Service 自建 checker；替代/收紧 current `test_direct_stream_protocol_error_surfaces_without_business_result`，同样只断言既有 prefix/message 与 exit 1。
- `[新增] test_fins_owned_protocol_error_object_reaches_cli_consumer_unchanged`
- `[新增] test_process_filing_keeps_runtime_preprocess_protocol_error_provenance_through_cli`
- `[新增] test_process_material_keeps_runtime_preprocess_protocol_error_provenance_through_cli`
- current `test_stream_failure_propagates_to_cli_error`
- current `test_sigint_cancels_stream_task_without_job_id`
- current `test_cancel_race_does_not_override_terminal_result`
- current `test_keyboard_interrupt_before_stream_exits_130`

```bash
source .venv/bin/activate
pytest -q \
  tests/cli/test_fins_commands.py::test_live_fins_commands_render_progress_and_terminal_summary \
  tests/cli/test_fins_commands.py::test_download_command_maps_args_to_service \
  tests/cli/test_fins_commands.py::test_upload_commands_map_args_and_validate_files \
  tests/cli/test_fins_commands.py::test_process_commands_map_to_service \
  tests/cli/test_fins_commands.py::test_terminal_failed_and_cancelled_status_exit_mapping \
  tests/cli/test_fins_commands.py::test_fins_owned_missing_result_uses_existing_cli_error_presentation \
  tests/cli/test_fins_commands.py::test_fins_owned_duplicate_result_uses_existing_cli_error_presentation \
  tests/cli/test_fins_commands.py::test_fins_owned_protocol_error_object_reaches_cli_consumer_unchanged \
  tests/cli/test_fins_commands.py::test_process_filing_keeps_runtime_preprocess_protocol_error_provenance_through_cli \
  tests/cli/test_fins_commands.py::test_process_material_keeps_runtime_preprocess_protocol_error_provenance_through_cli \
  tests/cli/test_fins_commands.py::test_stream_failure_propagates_to_cli_error \
  tests/cli/test_fins_commands.py::test_sigint_cancels_stream_task_without_job_id \
  tests/cli/test_fins_commands.py::test_cancel_race_does_not_override_terminal_result \
  tests/cli/test_fins_commands.py::test_keyboard_interrupt_before_stream_exits_130
```

### 7.4 fixture 纪律

- raw invalid event sequence 的算法 contract 只在 `tests/fins/test_fins_direct_stream.py` 完整枚举。Service/CLI provenance integration test 可把最小 invalid raw sequence 交给 production `ValidatedFinsEventStream`，但 fake/helper 不得自行检查、缓存、排序或构造 missing/duplicate/event-after error。
- Service fake runtime 必须返回同一个 `ValidatedFinsEventStream`，或抛一个由 Fins owner test fixture 预先取得的 typed error以验证 identity pass-through；不得在 Service test helper 重写 protocol algorithm。`process_filing/material` 反例必须断言返回 stream identity、error `reason/operation_kind/message/object`，并证明 `operation_kind is PREPROCESS` 而不是 `PROCESS_FILING/PROCESS_MATERIAL`。
- CLI fake Service 必须返回同一个 production validator stream/error；不得用裸 tuple 正常耗尽迫使 CLI 重建 missing。CLI internal consumer/provenance tests断言同一 object 与 Fins fields；public presentation tests只断言既有 prefix/message 和 exit 1，不把 `reason.value` 变成输出 contract。
- owner tests 断言 `reason is FinsDirectStreamProtocolErrorKind.*`、operation provenance、object identity、event顺序、yield计数、source close事实和 exception cause；不得用 error message解析 reason。

## 8. 可执行 complete-tree validation matrix

### 8.1 owner/consumer/adversarial tests

```bash
source .venv/bin/activate
pytest -q \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py
```

该集合必须显式覆盖：clean success、missing、duplicate、event-after-result、result-then-error、upstream exception/cancellation identity、primary-vs-cleanup chaining、consumer task cancel、validator explicit/repeated `aclose()`、source close success/failure、terminal_result OPEN/RESULT_BUFFERED/abortive/clean availability、generic producer exception的既有 bounded business failure `RESULT`、Service/CLI provenance、SIGINT race，以及 failure/cancelled business result不被改写。

R06/R08 no-regression：

```bash
source .venv/bin/activate
pytest -q tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py
pytest -q \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_processor_read_consistency.py
pytest -q tests/fins
```

### 8.2 changed production file 单文件 coverage

以 complete-tree owner/consumer suite 生成一次 cumulative data：

```bash
source .venv/bin/activate
coverage erase --data-file=workspace/tmp/.coverage-r09
coverage run --data-file=workspace/tmp/.coverage-r09 -m pytest -q \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py
coverage report --data-file=workspace/tmp/.coverage-r09 --include=dayu/fins/direct_events.py --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r09 --include=dayu/fins/direct_stream.py --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r09 --include=dayu/fins/ingestion_runtime.py --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r09 --include=dayu/service/fins_direct.py --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r09 --include=dayu/cli/commands/fins.py --fail-under=80
coverage json --data-file=workspace/tmp/.coverage-r09 -o workspace/tmp/coverage-r09.json
```

每个实际 changed production file 必须单独 `>=80.00%`；不得以五文件合计覆盖率、历史 R08 coverage 或只覆盖新增行替代。若 allowlist 中某 production file最终无 diff，可从 changed-file coverage ledger移除，但必须用 diff证明；任何实际 changed file不得遗漏。

### 8.3 type、lint、diff 与边界

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
python -m ruff check \
  dayu/fins/direct_events.py \
  dayu/fins/direct_stream.py \
  dayu/fins/ingestion_runtime.py \
  dayu/service/fins_direct.py \
  dayu/cli/commands/fins.py \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py
git diff --check
```

- full pyright 必须 `0 errors`；不得新增、扩散、ignore、cast-away 或配置排除。触及旧错误必须修复。
- scoped Ruff 必须覆盖所有实际 changed Python files并为零；若 review fix改变列表，命令同步扩展。
- implementation base 由 accepted-plan commit 固定；`git diff --name-only <implementation-base> -- dayu tests README.md` 必须逐项等于 §5 allowlist 中实际修改子集。
- staged tree 在 Controller 授权 commit 前必须为空；临时 coverage只放 `workspace/tmp/`，不得进入 diff。

### 8.4 owner/source/propagation scans

```bash
rg -n '_ensure_result_event|Fins direct Service stream ended without RESULT|_direct_operation_kind' \
  dayu/service/fins_direct.py dayu/cli/commands/fins.py \
  tests/service/test_fins_direct.py tests/cli/test_fins_commands.py

rg -n 'raise FinsDirectStreamProtocolError|FinsDirectStreamProtocolErrorKind|reason\.value' \
  dayu/service/fins_direct.py dayu/cli/commands/fins.py

rg -n 'FinsDirectStreamProtocolError' \
  dayu/fins/ingestion_runtime.py dayu/service/fins_direct.py

rg -n 'MISSING_RESULT|DUPLICATE_RESULT|EVENT_AFTER_RESULT' \
  dayu/fins/direct_events.py dayu/fins/direct_stream.py \
  dayu/fins/ingestion_runtime.py dayu/service/fins_direct.py dayu/cli/commands/fins.py

rg -n 'ValidatedFinsEventStream' \
  dayu/fins/direct_stream.py dayu/fins/ingestion_runtime.py \
  dayu/service/fins_direct.py dayu/cli/commands/fins.py \
  tests/fins/test_fins_direct_stream.py tests/fins/test_fins_ingestion_runtime.py \
  tests/service/test_fins_direct.py tests/cli/test_fins_commands.py
```

判定：

- 第一、二、三组 production scan 预期零命中；CLI 只允许 catch error class，不允许 import enum、读取 `reason.value` 或 raise protocol error；ingestion runtime 与 Service 不 import/catch/传递 protocol error class。
- 三个 enum literal 只允许出现在 `direct_events.py` 定义与 `direct_stream.py` decision；ingestion runtime、Service、CLI 均为零 literal。
- validator 的所有 production consumer 必须直接使用同一 class，不得另建 wrapper/checker。
- 对所有命中逐行分类；`rg` exit 1表示预期零命中，不是失败。

新增行兼容/弱类型 scan：

```bash
git diff -U0 <implementation-base> -- \
  dayu/fins/direct_events.py dayu/fins/direct_stream.py dayu/fins/ingestion_runtime.py \
  dayu/service/fins_direct.py dayu/cli/commands/fins.py \
  | rg '^\+.*(hasattr|getattr|compat|fallback|Any|object)'
```

预期零命中；命中 docstring 中“无 fallback”也必须人工分类，不能机械删正确说明。

## 9. 真实 smoke 与 test injection 边界

### 9.1 可真实运行的 success smoke

使用三个 fresh、非复用目录放在 `workspace/tmp/`，走真实 `python -m dayu.cli -> Service -> DefaultFinsRuntime -> producer -> validator`：

```bash
source .venv/bin/activate
python -m dayu.cli --base workspace/tmp/r09-real-download download \
  --ticker AAPL --forms 10-K --start 2025-01-01 --end 2025-12-31

python -m dayu.cli --base workspace/tmp/r09-real-download process --ticker AAPL

python -m dayu.cli --base workspace/tmp/r09-real-upload upload_filing \
  --ticker AAPL --action create \
  --files tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm \
  --fiscal-year 2024 --fiscal-period FY \
  --filing-date 2024-11-01 --report-date 2024-09-28 \
  --company-name 'Apple Inc.'
```

通过信号：三条 command exit `0`；真实 download/upload/preprocess 各输出 progress 与一个 terminal success；CLI 没有 protocol error；workspace 产物可由现有 Fins repository/read tests验证。download 依赖真实 SEC 网络，upload/preprocess 依赖真实 Docling/processor 环境；缺依赖、网络失败、skip 或未实际进入 producer都阻塞 R09 completion，不能用 mock 或 residual 代替。

### 9.2 只能 test injection 的 adversarial smoke

missing、duplicate、event-after-result、result-then-error 不是合法真实 producer成功场景，必须通过 test injection，不伪称真实运行：

- Fins owner tests直接注入 raw sequence，断言唯一 enum code、object identity和零 synthetic result。
- Service test让 injected typed error穿过 `FinsDirectCommandService`，断言同一 object `is`。
- CLI missing/duplicate tests让 Fins validator产生 error；internal consumer/provenance test断言同一 error object及其 `reason/operation_kind/message`，public presentation test只断言既有 `dayu-cli {command}: {message}` 与返回 1，不输出 raw enum value，也不出现 business failure result。

最终 evidence 必须分栏记录“真实 success smoke”与“test-injected protocol failure”，不能把 pytest fake当 real upload/download/preprocess。

## 10. No-regression、非目标与安全边界

### 10.1 R06/R08 no-regression

- R06：不改 batch token、transaction、complete source publication、rollback、atomic swap或任何 storage/pipeline文件；storage atomicity/provider tests全绿。
- R08：不改 financial/XBRL contract、processor、read runtime/projection、`fact_count`、citation或对应 README 语义；full Fins与R08 focused tests全绿。
- 合法 `FinsResultSummary` 的 success/failure/cancelled、exit `0/1/130`、详情与 error kind保持不变；protocol error不伪装成 financial/business fact。

### 10.2 明确不实施

- R10、R11、R12；
- Issue 142、151、175、177、178；
- Web、WeChat、render；
- Topic 8 的 Engine 240 字符 redacted/truncated exception policy；
- Topic 9 或任何统一 tool authorization framework；
- observed/legacy ingestion lifecycle redesign、process isolation、线程强杀、durable schema、Host wait状态机；
- 旧 schema、旧导入路径、兼容 wrapper/re-export、Service/CLI fallback、test-only shim。

### 10.3 retained security

- direct event safe-text/leakage guard、job id/path/raw payload/body禁入保持不变；
- operation-scoped cancellation checker、consumer-close cancellation state、queue backpressure与late producer publication防线不弱化；
- storage containment、symlink、atomic publication、R06 transaction、Host/ToolRuntime authorization和process fencing不修改；
- CLI generic error handling与日志通道不放宽；typed protocol code来自enum，不解析或回显 raw provider payload。

任一 retained security test失败均为 R09 release blocker，不能以 Topic 9 不实施为由删除防御。

## 11. Baseline failure registry

- 当前 plan gate不运行并重定义 baseline；只继承 Controller control doc与R08 completion的时序证据。
- R08 final truth为 aggregate `392 passed`、full Fins `859 passed / 1 existing Docling environment skip`、15/15 changed production coverage、full pyright零、Ruff零。它只证明R08 accepted tree，不替代R09 fresh validation。
- implementation 中只有“命令、node、错误类型、首个稳定栈帧/pyright rule、文本指纹、baseline SHA”六项全部相同且与R09 changed owner/source scans无交集，才可标 inherited。
- R09真实 upload/preprocess smoke不得继承或接受Docling skip；该 smoke要求真实成功。
- 任何失败数增加、node变化、错误进入changed owner、指纹变化或warning升级为error都视为新增/扩散并立即stop；不得私建平行 registry。

## 12. Immutable review、finding closure 与完整 gate

固定顺序：

```text
本 code-generation-ready plan
  -> AgentMiMo + AgentDS 对同一 plan SHA 双路完整 review
  -> Controller 逐 finding adjudication
  -> AgentCodex plan fix（全部 accepted，不限 severity）
  -> AgentMiMo + AgentDS 对最终完整 plan 双路 rereview
  -> Controller accepted-plan decision + exact-scope local commit
  -> R09-S1 checkpoint（不独立 accept）
  -> R09-S2 cumulative implementation
  -> complete-tree validation + immutable cumulative diff locks
  -> AgentMiMo + AgentDS 双路完整 code review
  -> Controller 逐 finding adjudication
  -> AgentCodex code fix（全部 accepted，不限 severity）
  -> complete-tree revalidation
  -> AgentMiMo + AgentDS 对最终完整 cumulative diff 双路 rereview
  -> cumulative aggregate/deepreview + Controller adjudication
  -> 必要 fix 后重复完整 code rereview 与 aggregate review
  -> one accepted R09 implementation commit
  -> R09 completion evidence + Controller validation + exact-scope completion commit
  -> handoff to R10 plan gate
```

- 每个 review target锁定 base SHA、sorted changed-path manifest SHA-256、binary diff SHA-256、每个 changed file blob/content SHA-256、相关 implementation/fix artifact SHA和 staged-empty状态。
- 两路 reviewer只能并发读取同一 target，不得并发修改共享工作区；任一 target变化使两路旧review失效。
- 每个 finding只能由Controller裁决为 `accepted`、`rejected-with-reason`、`deferred-with-owner` 或 `needs-more-evidence`。
- AgentCodex只修 accepted；但任何severity的accepted actionable finding都必须在R09内关闭。不得把accepted finding延期给R10、Issue或umbrella residual。
- 零accepted finding也必须有zero-change fix evidence和双路完整rereview；不能用conversation-only pass。
- R09 aggregate residual可以记录已裁决且不属于R09 accepted contract的外部风险，但不得用residual替代本sub-WU finding closure。

建议 artifact stem 固定为 `wu-semantic-ownership-01-r09-fins-direct-stream-validator-*`，后续不得换名。accepted plan、implementation、review/fix/rereview、aggregate、completion与Controller artifacts按umbrella §7.3闭集产生。

## 13. Stop conditions 与 residual owner/destination

| condition/risk | 处理 | owner / destination |
|---|---|---|
| 需要 §5.1 外 production path | implementation 不扩域，plan-review stop | umbrella Controller scope decision |
| 无法让 Fins validator直接拥有 closable raw source，必须依赖 Service/CLI probing | stop；不得 `hasattr/getattr` 或 callback seam | R09 Fins owner + Controller |
| accepted plan后owner/allowlist/contract source lock material drift | 旧plan不执行 | Controller重新plan/review |
| Service/CLI仍构造missing/duplicate/event-after或保留fallback | release blocker | R09-S2，必须本sub-WU删除 |
| zero-validator intermediate可能被accept/commit | 禁止接受；回到cumulative cutover | R09 Controller |
| real download/upload/preprocess smoke未真实成功 | completion blocker，不可skip/residual | R09 completion gate |
| new/spread pytest、coverage、pyright、Ruff、安全或README failure | stop并在owner边界修复 | R09；若确属外部baseline由Controller裁决 |
| R10-R12、Issue 142/151/175/177/178、Web/WeChat/render或Topic8/9需求出现 | 不实施 | 各既有owner/destination |

已知外部风险“Fins thread-backed长事务不可物理取消”仍归 Issue 175；R09只保证取消/close后不发布synthetic terminal和late queue event，不借机迁移executor。该风险不是R09 accepted finding。

## 14. Completion definition 与 handoff

R09只有全部满足才可 completion：

- Fins validator是missing/duplicate/event-after唯一decision owner；Service/CLI扫描为零；
- §4全部状态、error identity、cancel、aclose、result-then-error tests通过；
- S1/S2 cumulative tree无zero-validator、无compatibility、无旧checker fixture；
- focused、complete-tree、R06/R08、full Fins tests通过；
- 五个实际 changed production file逐文件coverage `>=80%`；full pyright零；scoped Ruff零；diff/scans通过；
- 真实download/preprocess/upload direct success全部通过；injected missing/duplicate/event-after 在 Fins/Service/CLI 观察同源 `reason/operation_kind/message/object`，CLI public output仍为既有 prefix/message且 exit 1；
- Fins/Service/tests README按职责同步，根/dayu README no-update decision有证据；
- retained security全绿；非目标无diff；
- 双plan review/fix/rereview、双code review/fix/rereview、aggregate/deepreview中全部accepted finding关闭；
- one accepted R09 implementation commit与completion evidence/Controller validation/completion commit exact scope成立；
- residual均有owner/destination且不包含任何未关闭R09 accepted finding。

handoff 必须报告：current/accepted base与commit SHA、immutable locks、精确changed paths、owner/error/terminal availability/close precedence contract、删除清单、逐命令测试结果、逐文件coverage、pyright/Ruff、source/propagation/security scans、真实与injected smoke分栏、README decision、baseline delta、全部finding final disposition、residual owner/destination及下一入口。完成后umbrella仍active，只能进入R10独立plan gate，不能直接implementation、push或PR。

## 15. Code-generation-ready 自检表

- [x] owner、状态机、error code/object、close/cancel语义明确。
- [x] current三处decision按真实函数证据列出，未虚构CLI duplicate checker。
- [x] production/test/README闭集与逐文件改动、删除/不得改清单明确。
- [x] S1/S2依赖、cumulative acceptance与zero-validator cutover明确。
- [x] current nodes与planned new/replacement nodes分开标记。
- [x] per-slice与complete-tree pytest、逐文件coverage、pyright、Ruff、diff、scan、README、real/injected smoke可直接执行。
- [x] R06/R08、R10-R12、Issues、Web/WeChat/render、Topic8/9与安全边界明确。
- [x] baseline temporal rule、immutable locks、完整双review/fix/rereview/aggregate/completion gate和finding closure明确。
- [x] stop/residual均有owner/destination；没有把accepted finding延后。
- [x] `R09-PR-F01` exact runtime/bridge/Service/CLI signature 与无新增 await cutover 已固定。
- [x] `R09-PR-F02` primary semantic error、cleanup chaining、显式 close failure 与底层至多一次 close 的 exact contract/tests 已固定。
- [x] `R09-PR-F03` speculative producer protocol-error queue/catch/test 已从 root cause、state machine、file changes、tests、scans、residual 删除；既有 generic business failure 与 raw native propagation 保留。
- [x] `R09-PR-F04` terminal_result 的普通 RuntimeError、module-owned safe message 与四类 availability/object tests 已固定。
- [x] `R09-PR-F05` CLI 保持既有 prefix/message/exit 1，不展示 raw reason；README fresh scan 与 no-update/update decision 已记录。
- [x] `R09-PR-F06` Fins `reason/operation_kind/message/object` 经 Service/CLI 同源传播及 process alias vs runtime PREPROCESS 反例 tests 已固定。

本文件完成后立即停在plan gate；不得据此直接修改实现。
