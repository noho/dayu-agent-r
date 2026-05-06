# Host P1 Handoff Plan：EngineWorker + 最小 Run Harness

## 目标

P1 目标是落地与 Engine 最近的一层 Host capability，使调用方可以通过 Host 的最小 Run 入口启动一个
单次 run，并从 Host 侧消费由 Engine 函数式入口产生的事件流。

本阶段必须产出：

- `dayu.host` 最小公开入口：只暴露 Run 级请求、句柄、事件流与测试 harness 所需契约。
- Host 内部 `EngineWorker` wrapper：负责调用 `dayu.engine.run_agent_messages`。
- Host 内部 `LocalProxy` / `WorkerProxy` 边界：为后续 RemoteProxy 保留替换点。
- `EngineEvent -> RunEvent` 翻译薄层：只做 Host 可见事件封装，不改变 Engine 事实。
- 最小 `start_run` 测试入口：支持单调用方、单 run、内存态执行 smoke。
- P1 影响范围内测试：证明 Host 可以经 Run 入口调用 Engine，并且不暴露 `EngineWorker` /
  `ToolExecutor.execute` 为 Host public API。

## 非目标

P1 不实现以下能力：

- Remote RPC、RemoteProxy、RemoteStub。
- 完整 Session governance、同 Session active Run 仲裁、`client_request_id` 幂等。
- P1.5 的最小 EventLog / RunEventStore append-before-stream 真源。
- 持久化 schema、workspace migration、启动恢复、多进程 lease / fencing。
- Conversation Memory、ContextBuilder、timeline projection。
- ToolRuntime truncate / fetch_more、cursor、scope token、TTL。
- 完整 ToolRegistry、工具权限、工具审计、业务工具迁移。
- 完整取消治理、`cancel_run` 状态机、watchdog、强制终止。
- `docs/code_review.md` 当前事实专项更新；P1 代码事实经用户确认落地后再更新。

## 前置条件

- prepare 阶段 PR #15 已合并到 `main`，本地基线为 `4a3d101` 或其后续主线。
- `docs/host/design.md` 是 Host 接口与架构边界真源。
- `docs/host/migration-plan.md` 已明确 P1 后接 P1.5；P1 不得绕过 P1.5 先制造独立 transcript 真源。
- Engine 已提供函数式入口 `dayu.engine.run_agent_messages` 和强类型 `EngineEvent`。
- Engine 只通过 `AgentRunRequest.tool_executor: ToolExecutor` 消费工具执行器；Host 不能让普通调用方直接触达该 protocol。

## 架构边界

分层仍固定为：

```text
UI -> Service -> Host -> Engine
```

P1 只在 Host 内部建立执行装配：

```text
Host public Run harness
  -> LocalProxy
  -> EngineWorker
  -> dayu.engine.run_agent_messages
```

边界规则：

- Host public API 只能围绕 Run 入口、Run handle、Run stream、Run event。
- `EngineWorker` 是 Host capability / 内部对象，不进入 `dayu.host.__all__`。
- `LocalProxy` 是 Host 内部默认 WorkerProxy 实现，不作为 UI / Service 直接依赖对象。
- `ToolExecutor.execute` 不成为 Host public API；测试只能通过注入 fake executor 到内部装配证明链路。
- Engine 不 import Host；Host 可以 import Engine 公共契约与函数式入口。
- Host 不 import `dayu.fins`，不理解财报业务语义。

## 文件级改动清单

计划新增：

- `dayu/host/__init__.py`
  - 导出 P1 最小 public surface。
- `dayu/host/contracts.py`
  - 定义 `RunInput`、`RunOptions`、`StartRunRequest`、`RunHandle`、`RunStream`、
    `RunEvent`、`RunEventType`、`RunEventCursor`、`RunState`、`RunResult` 的 P1 最小形态。
- `dayu/host/_worker.py`
  - 内部 `EngineWorker` wrapper 与构造 `AgentRunRequest` 的纯装配逻辑。
- `dayu/host/_proxy.py`
  - 内部 `WorkerProxy` protocol 与 `LocalProxy`。
- `dayu/host/_run_harness.py`
  - P1 最小 `start_run` 入口；只支持单 run 内存执行，不承诺生产治理。
- `dayu/host/_event_translation.py`
  - `EngineEvent -> RunEvent` 薄翻译。
- `tests/host/__init__.py`
- `tests/host/test_phase1_run_harness.py`
  - 验证 start_run 纵向链路、事件翻译、终态映射。
- `tests/host/test_phase1_public_boundary.py`
  - 验证 `EngineWorker` / `LocalProxy` / `ToolExecutor.execute` 不出现在 Host public API。
- `tests/host/test_import_boundary.py`
  - 验证 `dayu.host` 不导入 UI / Service / Fins，不被 Engine 反向依赖。

计划修改：

- `dayu/host/README.md`
  - 只更新 P1 已落地事实：最小 Run harness、内部 EngineWorker / LocalProxy 边界、不具备的治理能力。
- `tests/README.md`
  - 增加 Host P1 测试分层与运行方式。

若实施中发现需要拆分 `contracts.py` 以降低 God module 风险，允许改为 `dayu/host/contracts/*.py`。
但 public export 必须仍保持最小，不允许为兼容未来形态提前 re-export 大量内部符号。

## 新增 / 修改契约

P1 新增契约必须保持最小：

- `RunInput`
  - 包含进入 Engine 的 `messages: tuple[AgentMessage, ...]`。
  - P1 可直接使用 Engine `AgentMessage`，不新增 prompt / memory 语义。
- `RunOptions`
  - 包含 P1 必需的 `runner_spec`、`runner_options`、`agent_policy`、`stream`、`disable_tools`、
    `tool_schemas`。
  - `tool_executor` 不进入 public options；由 Host 内部 harness 注入。
- `StartRunRequest`
  - 包含 `session_id`、`run_id`、`input`、`options`。
  - 经用户确认，P1 暂不包含 `client_request_id`。
  - P1 不实现创建幂等；必须在 docstring 中明确这是 P7 治理能力，不得假装支持。
- `RunStream`
  - 包含 `handle` 与 `events`。
- `RunEvent`
  - 包含 `run_id`、`session_id`、`cursor`、`type`、`occurred_at`、`data`、`source_engine_event_id`。
  - P1 cursor 可由 Engine sequence 映射，但不能声明为持久 cursor。
  - 经用户确认，P1 `RunEvent.data` 允许直接携带 Engine event data 联合；这是 P1 最小翻译策略，
    不代表 Host timeline / EventLog 的最终 data contract。
- `RunResult`
  - P1 只覆盖 final answer / failed / cancelled / suspended 的最小终态投影。

所有契约必须使用强类型 dataclass / enum / TypeAlias；禁止 `Any`、无类型参数、无类型返回值、
开放 `dict` extra payload。

## 状态机变化

P1 只实现内存态最小 Run 状态：

```text
CREATED -> RUNNING -> SUCCEEDED
CREATED -> RUNNING -> FAILED
CREATED -> RUNNING -> CANCELLED
CREATED -> RUNNING -> SUSPENDED
```

约束：

- P1 不实现 `QUEUED`、`WAITING`、`RECOVERING`、`CANCELLING`、`LOST` 的真实治理。
- 如果枚举为了后续一致性包含这些状态，必须在 README / docstring 中说明 P1 不产生这些状态。
- 终态只能由 Engine terminal event 映射得出，不得凭空制造成功结果。

## 数据持久化 / schema 变化

P1 不引入持久化 schema，不修改 workspace schema，不新增 migration。

原因：

- P1.5 才固定 Minimal EventLog / RunEventStore append-before-stream 事实层。
- P1 的 Run harness 是单进程内存态 smoke 装配，不能被文档描述为可恢复事实源。

涉及 schema 变更的两条要求在 P1 结论为：

- NEW 不涉及旧库兼容读取。
- 不需要将旧库迁移动作加入 `workspace_migrations` / `dayu-cli init`。

## 多进程并发影响

P1 不提供多进程并发正确性。

必须避免的误导：

- 不声明 `start_run` 具备跨进程幂等。
- 不声明同 Session active Run 仲裁已经落地。
- 不依赖单进程锁来模拟未来生产语义。

P1 代码可以使用局部对象状态完成单 run harness，但这些状态不得成为 P2-P5 的事实真源。

## ToolRuntime / EngineWorker / Engine 边界影响

- EngineWorker 只负责把 Host 内部 run 请求装配成 `AgentRunRequest` 并调用 Engine 函数式入口。
- ToolExecutor 由 Host 内部 harness 作为 dependency 注入 EngineWorker。
- EngineWorker 不注册工具、不发现工具、不做权限、不做审计、不做 truncation。
- P1 不新增 ToolRuntime；只为 P2 保留 ToolExecutor 注入位置。
- Engine 继续只暴露 `run_agent_messages` / `run_agent_and_wait` 与 contracts，不 import Host。

## EventLog / RunEventStore / projection 影响

P1 只做事件翻译，不做 EventLog / RunEventStore。

允许：

- 将每个 `EngineEvent` 即时翻译成 `RunEvent` 并从 `RunStream.events` 产出。
- 保留 `source_engine_event_id` 和 Engine sequence，方便 P1.5 映射。

禁止：

- 把 P1 内存事件列表称为 EventLog。
- 在 P1 为 memory、timeline、trace 或 transcript 建立旁路真源。
- 让 P2-P5 依赖 P1 内存事件缓冲作为 canonical facts。

## 可接受临时实现 / 不可接受临时实现

可接受：

- 单调用方、单 run、内存态 harness。
- fake ToolExecutor 用于测试普通 no-tool / tool-call 链路。
- P1 `RunEvent` data 直接携带 Engine data 的强类型联合或明确投影后的 Host data。
- `run_id` 由测试请求显式提供，避免提前设计 id 生成策略。

不可接受：

- 暴露 `EngineWorker.run_agent_messages` 给 `dayu.host.__all__`。
- 暴露 `ToolExecutor.execute` 或要求上层直接调用 ToolExecutor。
- 使用 `Any`、无类型返回值、`extra payload`、`getattr` / `hasattr` 规避类型边界。
- lazy import Engine 来掩盖依赖方向。
- 把 reasoning / preview delta 写入运行态 memory 或 RunInput replay。
- 为旧 Host 接口创建兼容 wrapper / facade / re-export。

## runtime dependency

P1 不新增 `dayu.runtime` 能力，不涉及 lane。

如果实施中需要取消等待 helper，必须优先复用 `dayu.runtime.cancellation`，不得在 Host 内复制语义不一致的 wait/race helper。

## 测试清单

必须新增或更新：

- Host run harness happy path：fake Engine 或 monkeypatch `run_agent_messages` 产出 final answer，Host stream 返回终态 RunEvent。
- EngineWorker 真实装配边界：通过 fake Runner / fake ToolExecutor 的 Engine 现有测试素材，证明 Host 可以调用 Engine 函数式入口。
- 普通 tool-call fake executor smoke：必须覆盖 Runner tool call -> fake ToolExecutor -> Engine
  `TOOL_RESULT_ACCEPTED` -> final answer -> Host RunEvent stream 的链路。
- Engine terminal 映射：`FINAL_ANSWER`、`RUN_FAILED`、`RUN_CANCELLED`、`RUN_SUSPENDED` 映射到 Host RunEvent / RunResult。
- Event ordering：Host RunEvent cursor 与 Engine sequence 保持单调。
- Public boundary：`dayu.host.__all__` 不包含 `EngineWorker`、`LocalProxy`、`ToolExecutor`、`run_agent_messages`。
- Import boundary：`dayu.host` 不 import `dayu.fins` / `dayu.service` / `dayu.ui`；`dayu.engine` 不 import `dayu.host`。
- Weak typing guard：P1 新增 Host 源码不得出现 `Any`、无类型参数、无类型返回值、`**kwargs` extra payload。

## 验证命令

代码实施后必须运行：

```bash
source .venv/bin/activate
python -m pytest tests/host tests/engine/test_import_boundary.py tests/engine/test_package_exports.py tests/contracts
python -m pyright
```

如果只修改 P1 plan / review 文档，本阶段计划提交前只需运行：

```bash
source .venv/bin/activate
python -m pyright
```

并在最终说明中明确未运行 pytest 的原因是本提交未改生产代码或测试代码。

## README / docs 触发判断

P1 代码实施触发：

- 修改 `dayu/host/` 后必须检查并更新 `dayu/host/README.md`。
- 新增 `tests/host/` 后必须检查并更新 `tests/README.md`。
- 若 Host public API 或装配方式影响整体分层表述，检查 `dayu/README.md`；P1 预计不需要更新。
- 不更新根目录 `README.md`，除非 P1 新增用户可运行 CLI 或项目级使用方式；P1 预计不新增。
- 不更新 `docs/code_review.md`，直到 P1 代码事实经用户确认落地。

P1 plan / review 文档本身不触发 README 更新。

## review gate

P1 plan review 必须判定：

- 是否覆盖 migration-plan 的 P1 输出、非目标和 P1 EngineWorker public boundary gate。
- 是否明确 P1 与 P1.5 EventLog / RunEventStore 的边界。
- 是否避免把 ToolExecutor / EngineWorker 暴露为 Host public API。
- 是否避免把 P7 幂等、active Run 仲裁、多进程治理提前写成已落地目标。
- 是否给出足够具体的文件级改动、测试清单和验证命令。

P1 code review 必须判定：

- `EngineWorker.run_agent_messages` 没有成为 Host public API。
- `ToolExecutor.execute` 没有成为 Host public API。
- 调用方只能通过 Host Run 入口或测试 harness 触达 Engine。
- EngineWorker 只能作为 Host capability / 内部 protocol 被装配和测试。
- Host 没有 import `dayu.fins` / `dayu.service` / `dayu.ui`。
- Engine 没有 import Host。
- 新增类型签名没有 `Any`、无类型参数、无类型返回值或开放 extra payload。
- P1 没有引入旁路 transcript / memory facts。

## 停止条件

必须停止并等待用户确认：

- P1 plan review 通过后，等待用户人工 review，再 commit phase plan 与 review 文档。
- P1 代码 review 通过后，等待用户人工 review，再 commit 代码、测试和必要 README。
- 如果发现 P1 必须提前实现 EventLog append-before-stream 才能保证链路正确，停止并把范围调整为 P1/P1.5 边界问题。
- 如果实现需要 schema 变更，停止并重新写明 migration 与 `dayu-cli init` 影响。

## 风险与回滚

风险：

- P1 为了快速 smoke 暴露内部 EngineWorker / ToolExecutor，破坏 Host public surface。
- P1 内存事件缓冲被误用为后续 canonical facts，导致 P1.5 倒改。
- P1 契约过大，提前承诺 P7 生产治理。
- Host contracts 直接复用 Engine data 太多，导致上层依赖 Engine 细节。

回滚：

- P1 只新增 Host 包和测试，回滚可通过删除 P1 新增文件与 README 增量完成。
- 若 public surface 设计不通过，优先回滚 `dayu.host.__all__` 与 contracts，而不是增加兼容 re-export。

## 待用户确认项

已确认：

- `StartRunRequest` 暂不包含 `client_request_id`，创建幂等完整推迟到 P7。
- `RunEvent.data` 允许直接携带 Engine event data 联合；P1 README / docstring 必须说明这是 P1
  最小翻译策略，不代表 Host timeline / EventLog 的最终 data contract。
- P1 必须包含普通 tool-call fake executor smoke。

仍需用户确认：

- P1 plan / review 文档已允许 commit。commit 后进入 P1 代码实施。
- P1 plan review 通过后，是否允许进入代码实施。

## 迁移 Agent 实施完成汇报格式

实施完成时必须汇报：

- 改了什么：按文件列出 Host 入口、内部 worker/proxy、事件翻译、测试、README。
- 边界证明：说明 EngineWorker / ToolExecutor 未进入 Host public API 的证据。
- 验证了什么：列出 pytest 与 pyright 命令及结果。
- README / docs：说明哪些 README 更新了，哪些检查后无需更新。
- 风险或未覆盖项：明确 P1 不覆盖 EventLog、持久化、多进程、幂等、memory、truncate/fetch_more。
