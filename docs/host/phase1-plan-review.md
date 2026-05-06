# Host P1 Plan Review

## Review 范围

- 审查文件：`docs/host/phase1-plan.md`
- 设计真源：`docs/host/design.md`
- 总控计划：`docs/host/migration-plan.md`
- 相关 Engine 事实：`dayu.engine.run_agent_messages`、`AgentRunRequest`、`EngineEvent`、
  `ToolExecutor`

## 结论

P1 plan 当前可以作为迁移 Agent handoff plan 使用。它把 P1 限定在 EngineWorker + LocalProxy +
最小 Run harness，明确不做 P1.5 EventLog / RunEventStore、不做 P7 生产治理，也把
`EngineWorker` / `ToolExecutor.execute` 不得暴露为 Host public API 写成 plan 与 code review gate。

阻塞问题：无。

用户已确认 `docs/host/phase1-plan.md` 中的 P1 设计选项：

- P1 `StartRunRequest` 暂不包含 `client_request_id`。
- P1 `RunEvent.data` 允许直接携带 Engine event data 联合。
- P1 必须包含普通 tool-call fake executor smoke。

用户已确认允许 commit phase plan / review 文档，并进入 P1 代码实施。

## Gate 检查

### 1. P1 输出覆盖

结论：通过。

证据：

- plan 的“目标”覆盖 `dayu.host` 最小入口、EngineWorker wrapper、LocalProxy / WorkerProxy、
  `EngineEvent -> RunEvent` 翻译薄层、最小 `start_run` 测试入口。
- plan 的“文件级改动清单”细化到 `dayu/host/__init__.py`、contracts、worker、proxy、run harness、
  event translation 和 `tests/host`。

### 2. P1 非目标收束

结论：通过。

证据：

- plan 明确不做 Remote、完整 Session governance、P1.5 EventLog、持久化 schema、memory、
  truncate/fetch_more、完整 ToolRegistry、取消治理。
- plan 明确不更新 `docs/code_review.md`，避免把迁移过程写进日常 review prompt。

### 3. EngineWorker public boundary gate

结论：通过。

证据：

- plan 在“架构边界”“ToolRuntime / EngineWorker / Engine 边界影响”“review gate”中重复固定：
  `EngineWorker` 是 Host 内部 capability，不进入 `dayu.host.__all__`。
- plan 明确 `ToolExecutor.execute` 不成为 Host public API，普通调用方只能走 Host Run 入口。
- 测试清单包含 public boundary 测试。

### 4. P1 / P1.5 EventLog 边界

结论：通过。

证据：

- plan 在“EventLog / RunEventStore / projection 影响”明确 P1 只做事件翻译，不做 EventLog。
- plan 禁止把 P1 内存事件列表称为 EventLog，禁止建立旁路 transcript / memory facts。
- plan 明确 P1.5 才固定 append-before-stream 事实层。

### 5. P7 治理边界

结论：通过。

证据：

- plan 明确 P1 不实现 `client_request_id` 幂等、同 Session active Run 仲裁、多进程治理。
- plan 的状态机只覆盖内存态 `CREATED -> RUNNING -> terminal`，不把 `QUEUED` / `RECOVERING`
  等状态写成 P1 真实行为。

### 6. 类型与 import 边界

结论：通过。

证据：

- plan 要求新增契约使用强类型 dataclass / enum / TypeAlias，禁止 `Any`、无类型参数、
  无类型返回值、开放 extra payload。
- plan 要求新增 import boundary 与 weak typing guard 测试。
- plan 明确 Host 不 import `dayu.fins` / `dayu.service` / `dayu.ui`，Engine 不 import Host。

### 7. 验证与 README 触发

结论：通过。

证据：

- plan 给出代码实施后的 pytest 与 pyright 命令。
- plan 给出只改 plan / review 文档时的 pyright 命令。
- plan 按 AGENTS.md 触发规则列出 `dayu/host/README.md` 与 `tests/README.md` 更新条件。

## Findings

无阻塞 finding。

### 建议 1-低-代码实施时优先拆小 contracts 模块，避免 `contracts.py` 成为早期 God module

plan 允许在实施中将 `contracts.py` 拆为 `dayu/host/contracts/*.py`。P1 代码实施时如果
`RunEvent`、`RunResult`、`RunInput`、状态枚举集中在单文件后显著膨胀，应直接拆分，而不是等后续阶段再搬迁。

修复状态：无需修改 plan；实施阶段关注。

### 建议 2-低-如果 P1 直接携带 Engine data，必须把它写成 P1 临时契约

用户已确认允许 `RunEvent.data` 直接携带 Engine event data 联合。P1 代码与 README 必须明确这是
P1 的最小翻译策略，不代表 Host timeline / EventLog 的最终 data contract。

修复状态：已写回 `docs/host/phase1-plan.md`。

## 修复状态

本轮 review 未发现阻塞 finding，不需要修 plan。

## 用户人工 review 停止点

按 `docs/host/migration-plan.md`，P1 plan review 已通过后应停止，等待用户人工 review。
用户已确认三项 P1 设计选项，并已确认可以 commit
`docs/host/phase1-plan.md` 与 `docs/host/phase1-plan-review.md`。commit 后进入 P1 代码实施。
