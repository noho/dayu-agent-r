# Host P1.5 Handoff Plan：Minimal EventLog / RunEventStore

## 目标

P1.5 目标是在 P1 最小 Run harness 之后，固定 P2-P5 共同依赖的最小事件事实层，避免后续
ToolRuntime、Conversation Memory、context overflow 与 smoke 各自制造旁路 transcript、memory
或 timeline 真源。

本阶段必须产出：

- Host 内部 `RunEventStore` 契约：append-only、per-run cursor、exclusive replay。
- 最小 in-memory 实现：服务 P2-P5 单进程 smoke，不宣称多进程生产正确性；它是
  `RunEventStore` 的临时 adapter，不是未来需要废弃的另一套 EventLog 语义。
- `RunStream.events` 基于 store 的订阅视图：事件必须先 append，再被 stream 消费。
- canonical / preview 分层表达：P1 直接镜像 Engine 的事件必须在 P1.5 被显式归类。
- 最小 Run state 调和：terminal event 与 P1 `RunResult` 快照从同一份 store 事件推导。
- 受影响测试与文档：证明 append-before-stream、cursor、补读、终态调和和 public boundary。

## 非目标

P1.5 不实现以下能力：

- 持久化 EventLog schema、workspace migration、数据库事务或多进程 recovery。
- P6 的 observer、projection checkpoint、tool trace、audit、timeline projection、metrics 或 outbox。
- P7 的 Session / Run lifecycle governance、`client_request_id` 幂等、同 Session active Run 仲裁。
- P2 的 ToolRuntime truncation / fetch_more、cursor TTL、scope token。
- P3 的 Conversation Memory / ContextBuilder。
- P4 的 context overflow compact / retry。
- 完整取消治理、RemoteProxy、Attempt lease / fencing。
- 对 P1 public API 做兼容性 facade；若契约需要演进，直接按新设计修改。

## 前置条件

- P1 PR #16 已合入 `main`，当前基线为 `051cf20`。
- P1 已落地 `dayu.host.start_run`、内部 `LocalRunHarness -> LocalProxy -> EngineWorker` 与
  `EngineEvent -> RunEvent` 薄翻译。
- `docs/host/design.md` 第 9 节是 EventLog / RunEvent 设计真源。
- `docs/host/migration-plan.md` 明确 P1.5 必须在 P2 前完成。
- 当前 P1 cursor 只映射 Engine sequence，不具备持久补读语义；P1.5 必须收紧该语义。

## 架构边界

分层仍固定为：

```text
UI -> Service -> Host -> Engine
```

P1.5 的事实流向：

```text
EngineWorker
  -> translate EngineEvent to RunEventDraft
  -> RunEventStore.append(draft) returns cursor-bearing RunEvent
  -> RunStream.events / stream_run_events(after=cursor)
  -> RunResult snapshot derived from terminal RunEvent
```

边界规则：

- EventLog / RunEventStore 属于 Host，Engine 只产出强类型 `EngineEvent`。
- Host public API 仍围绕 Run 请求、句柄、事件流与结果快照；不暴露 EngineWorker、WorkerProxy
  或 ToolExecutor。
- 按 `docs/host/design.md`，`stream_run_events(run_id, after=cursor)` 与 `get_run_result(run_id)`
  属于 Host Run 级 public interface，P1.5 应导出。
- P1.5 的 in-memory store 是临时实现，但 `RunEventStore` 契约必须能演进到 P6 持久化实现。
- P1.5 固定的 `RunEventStore` 契约与事件语义是未来真实 EventLog 的稳定子集。P6 应替换或新增
  persistent implementation，并扩展 observer checkpoint、recovery / reconciliation 等能力；不得废弃
  P1.5 契约后另起一套事实语义。
- `RunEventStore` 只能保存 Host 通用运行事实，不承载 fins/doc/web 业务语义。
- `dayu.runtime` 不承载 EventLog 契约；EventLog 是 Host 业务层运行事实，不是层中立 runtime helper。

## 文件级改动清单

计划新增：

- `dayu/host/_event_store.py`
  - 定义内部 `RunEventStore` protocol、`InMemoryRunEventStore`、订阅与 replay 所需的强类型结构。
- `tests/host/test_phase1_5_event_store.py`
  - 验证 append-only、cursor 单调、exclusive replay、订阅先 replay 后等待新事件。
- `tests/host/test_phase1_5_run_harness_eventlog.py`
  - 验证 `start_run` 产出的事件来自 store，且 append-before-stream。

计划修改：

- `dayu/host/contracts.py`
  - 为 `RunEvent` 增加 canonical / preview 分层字段或等价强类型表达。
  - 增加内部 append 使用的 `RunEventDraft`，由 store 生成 cursor 后返回对外可消费的 `RunEvent`。
  - 新增 `RunEventSource`，并将 `source_engine_event_id` 调整为可选字段，以支持 Host-owned
    terminal failure event；Engine 来源事件必须保留 engine event id，Host 来源事件必须为 ``None``。
  - 增加 Host-owned failure data 类型，避免 worker 异常绕过 EventLog。
  - 导出 `stream_run_events` / `get_run_result` 所需的最小 public 契约。
- `dayu/host/_event_translation.py`
  - 显式把 Engine 事件翻译为 `RunEventDraft` 并分类为 canonical / preview。
  - 终态结果继续只由 terminal RunEvent 推导。
- `dayu/host/_run_harness.py`
  - `LocalRunHarness` 注入 `RunEventStore`。
  - 后台任务收到 EngineEvent 后先 append，再让订阅流可见。
  - 增加 public `stream_run_events(run_id, after=cursor)` 与最小 `get_run_result(run_id)` 路径；
    两者都是 Run 级接口，符合 Host public surface，不暴露内部 worker 或 store。
- `dayu/host/__init__.py`
  - 导出 `stream_run_events` / `get_run_result` 这两个 Run 级入口。
- `dayu/host/README.md`
  - 更新当前已落地事实：P1.5 最小 EventLog / RunEventStore、in-memory 临时边界、未落地能力。
- `tests/README.md`
  - 更新 Host 测试分层与 P1.5 验证命令。

可选新增：

- `dayu/host/_run_result_store.py`
  - 仅当把 terminal result 快照与 event store 分离能显著降低 `_event_store.py` 职责时新增。
  - 不允许变成 P6 projection 或 outbox 的提前实现。

## 新增 / 修改契约

### RunEvent 分层

新增强类型分层：

```python
class RunEventKind(StrEnum):
    CANONICAL = "canonical"
    PREVIEW = "preview"
```

`RunEventKind` 表达事件在 EventLog 里的事实层级，不表达业务类型：

- `CANONICAL` 是可恢复、可补读、可被治理或后续 projection 消费的事实。
- `PREVIEW` 是面向流式展示体验的临时片段，例如 assistant delta 或 reasoning delta。

分类原则：

- canonical：lifecycle、tool call requested、tool result accepted、usage、provider protocol error、
  final answer、failed、cancelled、suspended、context compaction requested 等可恢复或治理事实。
- preview：assistant content delta、reasoning delta 等展示型流式片段。
- preview 可以被 stream 和未来 timeline 展示消费，但不得被 ContextBuilder、Memory pool、
  RunInput replay、RunResult、outbox、replay 或 recovery 消费；不得作为运行态或治理态输入。
- 成功终态 canonical event 必须携带稳定 final answer 或等价 result payload；后续能力不能依赖从
  preview delta 拼接答案。
- `context compaction requested`、`suspended` 等只是在已有或未来事件出现时的分类规则，P1.5 不新增
  compact / retry / wait / resume 治理行为。

如果实施中发现 `RUNNER_CONTENT_COMPLETED` 需要作为回答片段合并事实，应在 plan 实施记录中明确它是
canonical 还是 preview，不允许含混。

### RunEventDraft 与 RunEvent cursor 所有权

P1.5 必须把“待落库事件”和“已落库事件”分开：

```python
@dataclass(frozen=True, slots=True)
class RunEventDraft:
    run_id: str
    session_id: str
    kind: RunEventKind
    source: RunEventSource
    type: RunEventType
    occurred_at: datetime
    data: RunEventData
    source_engine_event_id: str | None
```

`RunEventDraft` 仅供 Host 内部 append 使用，不进入 `dayu.host.__all__`。`RunEvent` 是唯一的
replay / stream 输出类型，必须携带 store 生成的 `RunEventCursor`。

cursor 所有权：

- Engine sequence 可以保留为 event data 或 diagnostic source，但不能成为 Host cursor 真源。
- `RunEventStore.append` 为同一 run 分配严格单调 cursor，并返回最终 `RunEvent`。
- `RunStream.events`、`stream_run_events`、`list_events` 与 `get_run_result` 只能消费已 append 的
  `RunEvent`。
- 禁止通过可变字段、替换 dataclass 属性或隐式修改传入事件来补 cursor。

Host-owned terminal failure：

- Engine 自身执行路径必须最终产出 terminal EngineEvent。若实施 P1.5 后发现 Engine 缺少该语义测试，
  应新增临时后续任务补 Engine 侧覆盖，不能把 Engine 终态缺失常态化为 Host 事实层责任。
- P1.5 新增 Host-owned failure data，例如 `HostRunFailedData`，用于 worker / proxy 异常导致 Host
  无法从 worker stream 获得 Engine terminal event 的路径。
- 该事件使用 canonical `RunEventType.RUN_FAILED` 或等价 Host terminal failure 类型，但必须通过
  `RunEventSource.HOST` 与 `source_engine_event_id=None` 表明它不是 Engine 原始事件。
- 这只是最小 EventLog terminal fact，不代表 P7 完整生命周期治理、取消治理或 recovery。

### RunEventStore

内部 store 契约建议：

```python
class RunEventStore(Protocol):
    async def append(self, draft: RunEventDraft) -> RunEvent: ...

    async def list_events(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> tuple[RunEvent, ...]: ...

    def subscribe(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncIterator[RunEvent]: ...
```

实施约束：

- `append` 必须保证同一 run 内 cursor 严格单调。
- `stream_run_events(after=cursor)` 使用 exclusive 语义，只返回 cursor 之后的事件。
- 订阅必须先 replay 已 append 事件，再等待新 append。
- append 后才能通知订阅者；通知不是事实真源。
- `subscribe` 必须用 cursor predicate 避免 replay 与 follow 注册之间的 lost wakeup：在同一锁 /
  condition 保护下循环检查 `last_seen_cursor` 之后是否存在事件；只有确认没有新事件时才等待。
  不能实现为“先 list 一次，随后注册 queue”等存在丢事件窗口的两段式逻辑。
- P1.5 in-memory store 可以使用 `asyncio.Condition` 或等价等待机制，但不能把该机制描述为多进程正确。
- 不引入开放 dict、`Any`、`object`、无类型参数、无类型返回值。

### RunResult 快照

P1.5 可保留 P1 `RunResult` 联合，但来源必须收紧：

- `RunResult` 只能由已 append 的 terminal RunEvent 推导或缓存。
- `get_run_result(run_id)` 若落地，必须是非阻塞快照补查；未 terminal 返回 `None`。
- 不在 P1.5 设计完整 `result_id`、artifact refs、evidence refs 或 validation status；这些属于后续阶段。

## 状态机变化

P1.5 不引入完整 P7 Run 状态机，只在 P1 状态上增加最小可调和事实：

```text
RUNNING -> SUCCEEDED
RUNNING -> FAILED
RUNNING -> CANCELLED
RUNNING -> SUSPENDED
```

调和规则：

- store 中出现 `FINAL_ANSWER` terminal event 时，Run 结果为 `SUCCEEDED`。
- store 中出现 `RUN_FAILED` terminal event 时，Run 结果为 `FAILED`。
- store 中出现 `RUN_CANCELLED` terminal event 时，Run 结果为 `CANCELLED`。
- store 中出现 `RUN_SUSPENDED` terminal event 时，Run 结果为 `SUSPENDED`。
- 如果后台 worker / proxy 异常导致 Host 无法获得 Engine terminal event，P1.5 必须 append
  Host-owned canonical failure event，再让 stream 观察到该 terminal RunEvent；不得让异常只通过
  iterator exception 绕过 RunEventStore。
- 如果异常源是 Engine 自身语义上未产出 terminal event，应记录为 Engine 语义覆盖缺口，并在当前
  phase 后安排临时任务补 Engine 测试；P1.5 不把该缺口设计成正常 Host fallback。

## 数据持久化 / schema 变化

P1.5 不引入持久化 schema，不修改 workspace schema，不新增 migration。

原因：

- 本阶段固定最小 EventLog / RunEventStore 语义，具体持久化、observer checkpoint、recovery 和
  reconciliation 留到 P6。
- P2-P5 可依赖 `RunEventStore` 契约，不依赖具体 in-memory 实现。
- P6 落地真实 EventLog 时，应复用同一组语义一致性测试验证 in-memory store 与 persistent store：
  append-before-stream、cursor exclusive replay、canonical / preview 分层、terminal fact 与订阅一致性
  必须保持一致。`InMemoryRunEventStore` 可继续作为测试 / smoke / 本地开发实现保留，但不能漂移成另一套语义。

涉及 schema 变更的两条要求在 P1.5 结论为：

- NEW 不涉及旧库兼容读取。
- 不需要将旧库迁移动作加入 `workspace_migrations` / `dayu-cli init`。

## 多进程并发影响

P1.5 不提供多进程并发正确性。

必须明确：

- in-memory store 只服务单进程、单调用方 smoke。
- per-run cursor 单调只在当前进程内保证。
- 不声明断线补读跨进程、跨重启可靠。
- 不实现 owner token、lease、fencing、stale cleanup 或 startup recovery。

但契约设计必须避免 P6 倒改：

- `RunEventStore` protocol 不应暴露进程内队列、task 或 callback。
- cursor 语义不能绑定 Engine sequence；由 Host store 生成或确认。
- append-before-stream 必须是稳定契约。
- P6 不应倒改 P2-P5 对 `RunEventStore` 的依赖；如 persistent store 需要新增全局 cursor、checkpoint、
  observer lease 或 retention 语义，应在不破坏 P1.5 per-run cursor 子集的前提下扩展。
- Host-owned failure event 只提供 worker / proxy 异常下当前 run 的 terminal fact，不提供跨进程 recovery 或 policy
  决策语义。

## ToolRuntime / EngineWorker / Engine 边界影响

- EngineWorker 仍只调用 Engine 函数式入口，不知道 EventLog。
- LocalRunHarness / Host supervisor 侧负责把 EngineEvent 翻译并 append 到 store。
- ToolExecutor 仍不进入 Host public API。
- P1.5 不实现 ToolRuntime；但 tool call 相关 EngineEvent 若被翻译为 canonical RunEvent，后续 P2
  必须复用这些事实或扩展同一 store，不得旁路写 transcript。

## EventLog / RunEventStore / projection 影响

P1.5 是最小 EventLog 契约阶段。

允许：

- in-memory append-only store。
- per-run cursor。
- canonical / preview 强类型字段。
- `stream_run_events(after=cursor)` 的补读接口。
- 最小 terminal result snapshot。

禁止：

- 实现 P6 observer、tool trace sink、audit sink、timeline projection 或 outbox projection。
- 把 preview delta 写入 Memory pool、RunInput replay 或 ContextBuilder 输入。
- 绕过 RunEventStore 为 P2-P5 单独建立 transcript、memory facts 或 smoke facts。
- 把 EventLog 契约放入 `dayu.runtime`。

## 可接受临时实现 / 不可接受临时实现

可接受：

- 单进程 in-memory store。
- 基于 `asyncio.Condition` 或等价 cursor predicate 的等待通知。
- Host store 生成 per-run cursor，并在 tests 中验证 exclusive replay。
- 为测试暴露内部 harness 依赖注入点，但不扩大包根 public API。

不可接受：

- 继续让 `RunStream.events` 直接消费 worker 内存队列而不经过 store。
- 以 Engine sequence 作为长期 cursor 契约。
- 为旧 P1 事件流行为写兼容 wrapper。
- 使用 `Any`、`object`、开放 `dict` extra payload、`getattr` / `hasattr` 逃避类型设计。
- 在 P1.5 中提前实现 memory、timeline、trace、audit 或 outbox 的业务事实表。

## runtime dependency

P1.5 不新增 `dayu.runtime` 能力，不涉及 lane。

如果事件订阅需要取消等待 helper，应优先复用 `dayu.runtime.cancellation`；不得在 Host 内复制语义不一致的
race / wait helper。若只是 `asyncio.Condition` 驱动 store 内部等待，不需要新增 runtime helper。

## 测试清单

必须新增或更新：

- EventStore append-only：同一 run 多次 append 后 cursor 严格递增。
- Exclusive replay：`list_events(run_id, after=cursor)` 不返回 cursor 对应事件，只返回之后事件。
- Subscribe replay-then-follow：订阅先返回历史事件，再返回订阅后 append 的新事件。
- Subscribe lost-wakeup race：事件在 replay 与 follow 注册边界 append 时不能丢；实现必须通过
  cursor predicate 循环等待证明这一点。
- Append-before-stream：`start_run` 产出的每个 RunEvent 都能从 store 补读到，stream 不能先于 append。
- Store conformance：将 append-before-stream、exclusive replay、subscribe lost-wakeup、canonical /
  preview、terminal result 等语义整理为可复用测试；P6 persistent store 必须复用这些测试，证明真实
  EventLog 与 in-memory adapter 语义一致。
- Canonical / preview 分类：至少覆盖 final answer、failed、cancelled、suspended、content delta、
  reasoning delta、tool call、tool result。
- Host-owned failure：worker / proxy 异常导致 Host 无法获得 Engine terminal event 时，store 中存在 canonical
  failure RunEvent，`get_run_result` 返回失败快照。
- Engine terminal coverage：实施完成后检查 Engine 是否已有“正常 / 失败 / 取消 / suspend 路径均产生
  terminal EngineEvent”的语义测试；若没有，记录临时后续任务补测。
- Terminal result snapshot：terminal event append 后 `get_run_result` 或内部快照返回对应 `RunResult`。
- Public boundary：`dayu.host.__all__` 仍不包含 EngineWorker、LocalProxy、ToolExecutor 或 store 实现类。
- Import boundary：`dayu.host` 不 import `dayu.fins` / `dayu.service` / `dayu.ui`；Engine 不 import Host。
- Weak typing guard：Host 新增源码不得出现 `Any`、`object`、无类型签名与裸容器注解。

## 验证命令

代码实施后必须运行：

```bash
source .venv/bin/activate
python -m pytest tests/host tests/engine/test_import_boundary.py tests/engine/test_package_exports.py tests/contracts -q
python -m pyright
```

如果只修改 P1.5 plan / review 文档，本阶段计划提交前只需运行：

```bash
source .venv/bin/activate
python -m pyright
```

并在最终说明中明确未运行 pytest 的原因是本提交未改生产代码或测试代码。

## README / docs 触发判断

P1.5 代码实施触发：

- 修改 `dayu/host/` 后必须检查并更新 `dayu/host/README.md`。
- 新增或修改 `tests/host/` 后必须检查并更新 `tests/README.md`。
- Host public API 会增加 `stream_run_events` / `get_run_result`；必须检查 `dayu/README.md` 是否需要更新。
  预计仍不影响整体分层总览，因为它们只是 Host 包内 Run 级开发接口，不是项目级用户入口。
- 不更新根目录 `README.md`，除非新增用户可运行 CLI 或项目级使用方式；P1.5 预计不新增。
- 不更新 `docs/code_review.md`，直到 P1.5 代码事实经用户确认落地。

## Review Gate

plan review 必须检查：

- P1.5 是否只固定最小 EventLog / RunEventStore，没有偷做 P6 observer。
- append-before-stream 是否成为稳定契约。
- cursor 是否是 per-run exclusive 语义，不再绑定 Engine sequence。
- canonical / preview 是否足以保护 P3 memory 与 P4 compact 不消费展示 delta。
- in-memory 临时实现是否被清楚标注为非多进程生产能力。
- public boundary 是否仍不暴露 EngineWorker / ToolExecutor / store 实现类。
- 类型与 import boundary 是否满足 AGENTS.md。

code review 必须检查：

- 所有事件先 append 后 stream。
- 补读与订阅不丢事件，不重复返回 `after` 对应事件。
- 终态结果只来自已 append terminal event。
- worker / proxy 异常路径也必须进入 EventLog，不能只通过 iterator exception 暴露；EngineEvent 到
  Host RunEvent 的翻译边界必须符合 `docs/host/design.md`。
- 新增测试覆盖 plan 中列出的关键行为。
- README 与 tests 文档只描述当前已落地事实。

## 停止条件

出现以下情况必须停止并回到用户确认：

- 发现 P1 `RunEvent.data` 直接携带 Engine data 联合无法支持 canonical / preview 分类，需要较大契约重写。
- 实施需要引入持久化 schema 或 workspace migration。
- 需要改变 EngineEvent 契约或 Engine 函数式入口。
- 需要把 EventLog 契约放入 `dayu.runtime` 才能继续。

## 风险与回滚

主要风险：

- P1.5 public surface 过大，提前承诺 P7 治理能力。
- in-memory store 的行为被误读为生产 EventLog。
- P6 若把真实 EventLog 当作全新语义重写，会导致 P2-P5 事实来源倒改；plan 与测试必须把
  `RunEventStore` 语义一致性作为 review gate。
- canonical / preview 分类过粗，导致 P3 或 P4 误消费展示型 delta。
- Host-owned failure event 被误读为完整治理失败状态；README 与 docstring 必须写清它只是 P1.5
  最小 terminal fact。

回滚策略：

- P1.5 代码应集中在 `_event_store.py`、`_run_harness.py`、`_event_translation.py` 与 tests；
  回滚时不影响 Engine。
- 如果 public `stream_run_events` 在人工 review 中被否决，回滚到仅内部 harness 暴露 store 订阅；
  代码实现前不得擅自改回内部-only。

## 用户确认项

- 用户已确认：P1.5 按 `docs/host/design.md` 将 `stream_run_events(run_id, after=cursor)` 与
  `get_run_result(run_id)` 作为包根 Run 级 public API 落地。
- 用户已确认：`RunEventKind` 只表达 EventLog 事实层级，P1.5 使用它区分 `CANONICAL / PREVIEW`。
- 用户已确认：worker / proxy 异常肯定会发生，P1.5 需要生成 Host-owned canonical failure RunEvent；
  该能力不包含 P7 完整生命周期治理。
- 用户已确认：Engine 自身执行路径不应缺失 terminal EngineEvent；若 Engine 侧缺少相关语义测试，
  当前 phase 实施后增加临时任务补覆盖。

## 迁移 Agent 实施完成汇报格式

实施完成后必须汇报：

- 改了哪些文件。
- `RunEventStore` 契约与 in-memory 实现的边界。
- append-before-stream 如何保证。
- cursor exclusive 语义如何验证。
- canonical / preview 分类清单。
- terminal result snapshot 如何从 store 事件推导。
- README / docs 触发判断与实际更新。
- 测试与 pyright 命令结果。
- 已知风险、未覆盖项与是否需要用户确认。
