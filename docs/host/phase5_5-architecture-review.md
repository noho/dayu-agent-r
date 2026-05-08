# Host P5.5 独立架构 / 最佳实践 Review

## 结论

P5.5 的动机成立，而且当前 `docs/host/phase5_5-plan.md` 的总体方向基本正确：它把 P1-P5 的
deferred scope 作为一类独立治理对象来核对，而不是继续推进生产代码。这符合第一性原理：P5 已经证明
no-full-governance happy path 能串通，但 P1-P5 每一阶段都把“完整治理、业务工具、持久化、输出校验、
memory/context governance”等能力显式后移；如果这些后移项不逐条回链到后续 phase / issue，就会出现能力漏排、
重复排期或把治理缺口误报成代码 bug。

本轮 review 不修改 plan。审查结论是：P5.5 plan 可以作为 reconciliation 阶段的基础，但最终实施时必须把
OLD/NEW 对比、code review remaining risks、design/README 差异和当前代码事实全部纳入 inventory 的必填证据。
当前 plan 已经写到这些输入源，风险不在方向，而在执行时把“能力域汇总”当成“逐项核销”，从而丢掉原始 deferred
条目。

## Findings

### 1. [中] [已纳入计划] OutputContract / validation replay 仍是最高漏排风险，不能被归入普通 governance 后自然消失

`docs/host/design.md` 已把 `OutputContractRef`、`ValidationDecision`、Replay 分离、validator decision
持久化和 replay attempt 写成 Host 运行可靠性设计点；`docs/host/phase4-plan.md` 与
`docs/host/phase5-plan.md` 又明确 P4/P5 不做 replay / validation / OutputContract。当前
`docs/host/migration-plan.md` 的 P6-P13 phase 表没有单列 OutputContract / validation replay；P12
写的是取消增强、policy hard-gate、audit hard-gate 与运行治理。

这不是“完整生产治理”才需要的边角项。对财报分析 Agent 来说，输出契约和验证重试直接决定回答可靠性，和
Outbox、Remote、lease 一类部署治理不同。若 P5.5 最终只写成“P12 governance hardening 可能覆盖”，会把
非治理可靠性能力误排到治理兜底里，后续很容易没有明确验收信号。

建议：P5.5 inventory 必须把该项标为“需调整现有 P6+ phase”或“需新增 phase / issue”，并给出总控级边界。
最低要求是 migration-plan 后续明确一个可验收归属：OutputContractRef 来源、ValidationDecision fact、
replay attempt 上限、恢复后如何继续或停止。不要把 P4 compact retry 或 P12 audit hard-gate 当作等价替代。

### 2. [中] [已纳入计划] Tool declaration 已落地，但完整 ToolRegistry / business fins tools / Service catalog 仍缺清晰承接

当前代码已经落地 P5 最小公共声明：`dayu/contracts/tool_declaration.py` 明确 `ToolDefinition` /
`ToolBundle` 把 LLM-facing `ToolSchema`、Host `ToolTruncateSpec`、executor binding 与 display metadata
同源声明，并明确它不是 ToolRegistry，不负责权限治理、生命周期治理、工具发现、middleware 或业务工具迁移。
`dayu/host/README.md` 也把完整 ToolRegistry、工具发现、权限治理、middleware、业务工具迁移列为当前未落地。

这说明 P5 已实现能力不能重复排期为“恢复 LLM-facing fetch_more / tool declaration”；但反过来，财报 Agent
真正可用还需要业务工具迁移与 Service/catalog 装配入口。该能力不能塞进 Host 通用语义，也不能让 Host import
`dayu.fins`；应由业务工具 / tool boundary 通过 `dayu.fins.storage` 保证财报文档存取。

建议：P5.5 最终归属表应拆成三项，而不是合并成“ToolRegistry”：

- 已实现：最小 `@tool` / `ToolDefinition` / `ToolBundle` declaration，framework `fetch_more` schema。
- 需调整 / 新增：完整 ToolRegistry / catalog / permission / middleware / audit decision 的通用治理归属。
- 需新增业务 phase / issue：business fins tools / doc / web 工具迁移与 Service 装配边界，明确 Host / Engine 不懂财报语义。

### 3. [中] [已纳入计划] P5 已实现能力有重复排期风险，尤其是 LLM-facing `fetch_more`

P5 之后，当前代码和测试已经证明模型发起 framework `fetch_more` 的最小闭环：P5 smoke 测试断言 Engine /
Runner 只接收 `ToolSchema` 元组，模型看到 `truncation.next_action="fetch_more"` 与
`fetch_more_args={cursor, scope_token, limit?}`，并通过普通 tool call 调用 framework `fetch_more`；Host
ToolRuntime 识别该工具名并路由补读，不调用业务 executor。P5 code review 也把“脚本代调 Host public
fetch_more 不能算 success path”作为重点核查项。

因此，P5.5 不应再把 LLM-facing `fetch_more` schema、hint projection、同 run 内 framework route 作为未安排
能力。真正剩余的是它的升级边界：是否需要完整 ToolRegistry 治理、是否保留 Host public
`fetch_more_tool_result()` 作为底层 / 负例 API、是否需要 future transparent continuation。

建议：final inventory 对 P2/P5 旧口径必须加“历史线索已被 P5 改写”的证据标记。`phase5_5-early-scan.md`
只能作为 P5 前预扫，不能直接继承其中“P5 smoke 缺失”“LLM-facing fetch_more 未落地”的旧判断。

### 4. [中] [已纳入计划] 代码扫描和 review findings 必须作为 inventory 输入，否则会漏掉“非 plan 文本”的 deferred 项

P5.5 plan 已要求扫描 phase plan、migration-plan、design、README、review 文档和代码 TODO；这个范围是必要的。
抽查显示，review 文档里确实存在 plan 正文不容易显式保留的 deferred / remaining risk：

- P5 code review 剩余风险：真实 provider smoke 未运行，P2 public handle / public `fetch_more_tool_result()`
  后续是否收敛需要单独决定。
- P3/P4 OLD/NEW review：memory reset/correction/scope clear、episode summary、evidence/source cursor 保真、
  provider token estimator 近似口径等，很多不是 P6-P13 phase 表的一行能自然覆盖。
- P1.5 / P2 code review：多进程 cursor store、lease / fencing、observer、audit / timeline projection均后移。

建议：P5.5 实施时不要只靠 `phase*-plan.md` 的“非目标”段落。每个 inventory item 应记录 `source_kind`
（plan / review / code / README / design）、来源文件和短摘；若同一能力有多个来源，也要保留至少一个原始
source item，避免能力域合并后丢失具体约束。

### 5. [低] [已纳入计划] 真实 provider smoke 是证据边界，不应被误判为能力缺口或已实现事实

P5 code review 明确未运行 `mimo-v2.5-pro-plan` 真实 provider smoke；P5 plan 与 README 把真实 provider case
定位为手工 smoke 主目标，但不是 CI 必跑。当前测试能证明 fake provider / scripted runner 下的架构路径，
不能证明外部 provider 在 2026-05-08 的真实网络、API key、tool calling 行为稳定。

建议：P5.5 只记录“真实 provider smoke 证据待人工验证 / 环境依赖”，不要把它升级成 P6+ 能力，也不要把它写成
P5 已每次通过。若总控需要运营级信心，应新增人工 smoke evidence 记录，而不是改 Host migration scope。

## 第一性原理判断

P5.5 作为 deferred scope reconciliation 能防止漏排，但前提是它核对的是“原始承诺项”，不是“当前脑中想到的能力域”。
正确闭环应满足四个条件：

1. 每个 P1-P5 非目标 / 后移 / review remaining risk 都能回链到直接证据。
2. 每项只能落入固定状态：已实现、已安排到 P6+、需调整现有 P6+ phase、需新增 phase / issue、需用户确认关闭。
3. 已实现项必须用当前代码 / README / 测试证明，并标清 no-full-governance 边界。
4. 未实现项不能因为属于“治理”就自动塞进 P12；OutputContract、business tools、memory/context governance 等需要按产品能力性质独立判断。

按这个标准，当前 P5.5 plan 的动机和框架成立；需要重点防的是实施阶段的证据折叠。

## 抽查事实

- P5 merge 基线：本地 `git log --oneline -1` 为 `a825b4c Host P5 no-governance multiturn smoke (#22)`。
- 当前 `dayu.host` README 声明已落地 P5 no-full-governance smoke 所需的最小 Run harness、内存态
  RunEventStore、ToolRuntime truncate / fetch_more、Conversation Memory / RunInputBuilder、compact retry 与
  tool declaration；同时列出 `client_request_id` 幂等、Session governance、持久化、多进程、完整
  ToolRegistry、业务工具迁移、public memory edit/reset/forget、Remote/Outbox 等未落地。
- `StartRunRequest` 当前仍不包含 `client_request_id`，代码注释明确完整创建幂等与同 Session active Run 仲裁在
  P7 落地。
- 默认 public `start_run` 仍使用 `_NoopToolExecutor` 构造默认 harness；真实工具接入依赖内部 harness /
  组合装配，不代表完整 Service 工具 catalog 已完成。
- Engine / Runner 只消费 `ToolExecutor.execute` 与 `ToolSchema` projection，不持有 Host cursor store、
  ToolRuntime、ToolRegistry、财报业务语义或 context compact policy。
- Host import boundary 仍应继续守住：财报文档访问只能由业务工具通过 `dayu.fins.storage` 保证，不能进入 Host /
  Engine 通用运行语义。

## 建议的 P5.5 输出重点

- 对 migration-plan P6-P13 给出 patch 清单，而不是直接修 plan。
- 对 OutputContract / validation replay 给出明确归属建议，这是本轮最高优先级。
- 对 ToolRegistry / business fins tools 分别给出归属，避免把业务工具迁移伪装成 Host runtime 治理。
- 对 P5 已实现的 LLM-facing `fetch_more`、tool declaration、P5 fake-provider smoke 标为已实现但限定为最小实现。
- 对真实 provider smoke、public fetch_more API 收敛、provider tokenizer adapter、transparent continuation 标为证据 / 产品决策项，而不是当前代码 bug。

## 验证边界

本轮只做文档与代码抽查，未修改 plan，未修改生产代码，未运行 pytest 或 pyright。由于仅新增 review 文档，后续只需对本文进行文本自查。
