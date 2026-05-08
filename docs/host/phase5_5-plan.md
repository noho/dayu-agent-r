# Host P5.5 Deferred Scope Reconciliation Plan

## 目标成立性判断

P5.5 的动机成立。P1-P5 已经把 no-full-governance 纵向链路推进到可验证状态，但每个阶段都明确后移了若干能力；如果不在 P5 之后统一核对，这些 deferred 项容易出现三类风险：

- 已由后续阶段实现却仍被文档写成未落地。
- 尚未落地但已在 P6+ phase 表中有清晰归属，后续无需新增 scope。
- 尚未落地且没有明确归属，尤其是财报可靠性相关的 OutputContract / validation replay、完整 ToolRegistry / business fins tools、context / memory governance 等能力；其中 OutputContract / validation replay 必须作为最高漏排风险独立核对，不得自然归入普通 governance 或 P15 hard-gate。

P5.5 不是实现阶段。它只做扫描、分类、排期核对与文档修订建议；不得写生产代码，不得把未落地能力写成当前事实，不得为了关闭 deferred 项临时扩大 P6+ 的实现范围。

## 背景与当前事实

- P5 已通过 PR #22 合入 `main`。当前本地 `main` 顶部为 `a825b4c Host P5 no-governance multiturn smoke (#22)`。
- P5 之后，`dayu.host` 当前已落地 no-full-governance 纵向 smoke 所需的最小 Run harness、内存态 RunEventStore、Host-owned ToolRuntime truncate / fetch_more、Conversation Memory / RunInputBuilder、context overflow deterministic compact retry，以及公共 tool declaration 契约。
- P5 已落地最小公共 `@tool` / `ToolDefinition` / `ToolBundle` 声明能力，使工具现场同源声明 LLM-facing `ToolSchema`、Host `ToolTruncateSpec`、executor binding 与 display metadata；进入 Engine / Runner 的仍只能是 `ToolSchema` projection。
- P5 已落地 LLM-facing truncation hint 与 framework `fetch_more` schema / 路由，使模型能在同一个 run 内根据截断结果发起 framework `fetch_more` tool call；这不是完整 ToolRegistry、权限治理、middleware 或业务工具迁移。
- P5 已提供 `utils/smoke_host_multiturn_no_governance.py` 与 `tests/host/test_phase5_multiturn_no_governance_smoke.py`，覆盖顺序多轮、ToolRuntime truncate / fetch_more、memory 接续、compact retry、scope token redaction 等 no-full-governance 验证面。真实 provider smoke 仍依赖外部 API key、网络与 provider tool calling 可用性；不得把“脚本存在”写成“真实 provider 每次已通过”。
- `docs/host/phase5_5-early-scan.md` 是 P5 merge 前的预扫历史材料。它可以作为线索来源，但其中关于 P5 smoke 与 LLM-facing `fetch_more` 仍待落地的旧判断已经过时；P5.5 必须以当前 `main`、当前 README / design 与当前代码事实重新判定。

## 非目标

P5.5 不实现以下能力：

- 不写、修改或删除 `dayu/`、`tests/`、`utils/` 下的生产代码、测试代码或 smoke 脚本。
- 不补实现 Remote、Outbox、持久 EventLog、observer、Session governance、Attempt lease、Wait / Suspend / Resume、audit hard-gate、ToolRegistry、business fins tools、OutputContract 或 validation replay。
- 不创建兼容 wrapper / facade，不调整 public API，不新增 schema，不新增 workspace migration。
- 不把 `docs/host/phase5_5-early-scan.md` 删除或改写成当前事实；只在新 plan / inventory 中说明它是 P5 前历史参考。
- 不把 P6+ 的 phase plan 一次性细化为实现 handoff plan；P5.5 只提出总控计划修订建议或新增 phase / issue 建议。
- 不 commit、push、创建 PR 或合并分支。

## 前置条件

- 当前基线必须是 P5 merge 后的 `main`，且 `git log --oneline -1` 显示 `a825b4c Host P5 no-governance multiturn smoke (#22)` 或其后续主线。
- 读取 `AGENTS.md` 并遵守中文回答、分层边界、README 同步与修改后验证要求。
- 读取并核对：
  - `docs/host/migration-plan.md`
  - `docs/host/phase5_5-early-scan.md`
  - `docs/host/phase1-plan.md`
  - `docs/host/phase1_5-plan.md`
  - `docs/host/phase2-plan.md`
  - `docs/host/phase3-plan.md`
  - `docs/host/phase4-plan.md`
  - `docs/host/phase5-plan.md`
  - 对应 plan review、OLD / NEW review、best practice review、code review 与 PR review 文档。
- 读取当前事实文档：
  - `docs/host/design.md`
  - `dayu/host/README.md`
  - 必要时读取 `dayu/README.md`、`dayu/engine/README.md`、`tests/README.md` 中与 Host 边界有关的段落。

## 扫描范围

P5.5 必须扫描以下范围，且每个 deferred item 都要能回链到直接证据：

- P1、P1.5、P2、P3、P4、P5 phase plan 中的“非目标”“不实现”“明确不做”“后移”“deferred”“暂不”“不包含”等段落。
- `docs/host/migration-plan.md` 的 phase 表、P5.5 说明、P6-P16 目标 / 明确不做 / 验收信号。
- `docs/host/design.md` 与 `dayu/host/README.md` 当前事实和“当前未落地 / 后续设计点”段落。
- review 文档中的 deferred / remaining risk / OLD-NEW mismatch / best practice 建议，尤其是 P2 LLM-facing fetch_more 后移、P3 issue #48 后移能力、P4 OutputContract / validation replay、P5 remaining risks。
- 当前代码和测试中的 TODO / FIXME / deferred / 未落地线索。只扫描，不修复。

建议使用的自查命令：

```bash
rg -n "非目标|不实现|明确不做|后移|defer|Deferred|暂不|不包含|未落地|Remaining risks|TODO|FIXME" docs/host dayu/host tests/host
rg -n "OutputContract|validation replay|ToolRegistry|tool catalog|business tool|fins|EventLog persistence|observer|projection|Session governance|client_request_id|active Run|Attempt lease|RemoteProxy|RemoteStub|Outbox|Wait|Suspend|Resume|audit hard-gate|memory governance|context governance|token estimator" docs dayu tests
sed -n '1,220p' docs/host/migration-plan.md
sed -n '1,220p' dayu/host/README.md
```

## 输出物

P5.5 实施完成后至少应产出以下文档内容。可以集中写入 `docs/host/phase5_5-plan.md` 的后续修订版，也可以在 review 通过后按用户确认拆出 inventory 文档；若拆文档，必须在本 plan 和 migration-plan 中交叉引用。

- deferred inventory：逐项列出 `source_kind`、source file、来源 phase / review、原文短摘、直接证据、当前事实判断、建议状态与后续归属；不得只按能力域合并后丢失原始 deferred 条目。
- 能力归属表：按能力域汇总归属，例如 ToolRuntime / ToolRegistry、EventLog / observers、Session / Run lifecycle、Attempt / recovery、Remote、Outbox、Wait、OutputContract / validation、memory / context governance、business fins tools；其中 OutputContract / validation replay 必须单列明确归属建议。
- 现有 phase 调整建议：指出 P6-P16 哪些目标、明确不做或验收信号需要改写，但不直接写实现细节。
- 新增 phase / issue 建议：对 migration-plan 尚未承接的能力提出新增 phase 或 issue 名称、边界、触发原因与 review 要求。
- 需用户确认关闭列表：只有当 deferred item 明确不再需要、或已被新设计替代且关闭会影响产品能力口径时，才放入此列表；不得由实施 Agent 自行关闭。
- 总控计划修订 patch 清单：列出建议改动的 `docs/host/migration-plan.md` 章节、表格行和新增段落摘要。写回 migration-plan 的 gate 统一为：先输出 patch 清单；常规 plan review 与必要专项 review 通过后仍必须停等用户人工确认；用户确认后才允许写回 `docs/host/migration-plan.md`。

## 分类规则

每个 deferred item 必须且只能落入以下状态之一：

| 状态 | 含义 | 证据要求 |
| --- | --- | --- |
| 已实现 | P5 当前 main 已落地该能力或等价替代能力 | 指向当前代码 / README / 测试 / review 证据，且不得夸大生产治理级别 |
| 已安排到 P6+ | migration-plan 的 P6-P16 已明确承接 | 指向 phase 表或具体段落，说明目标、非目标、验收信号是否足够 |
| 需调整现有 P6+ phase | 已有 phase 承接方向相近，但目标、非目标、验收信号或顺序不够准确 | 指出建议修改哪一行、为什么现有表述会漏排或误排 |
| 需新增 phase / issue | 当前 main 未实现，migration-plan 也无明确承接 | 给出新增 phase / issue 的最小边界和 review gate，不写生产设计细节 |
| 需用户确认关闭 | 能力可能不再需要、被新设计替代或属于产品取舍 | 必须说明关闭影响、替代方案和为什么不能由 Agent 单方面关闭 |

禁止状态：

- “暂时忽略”。
- “后面再说”。
- “可能已实现但未核实”。
- “文档已提到所以算安排”，除非能指出具体 phase 目标 / 验收信号。

## 初始关注清单

以下清单来自当前 migration-plan、phase plan、design、README、review 与 P5 前预扫。它只是 P5.5 扫描的起点，不是最终 deferred inventory；实施 Agent 必须逐项回到源文档与当前代码核证。

| 能力域 | 初始判断方向 | 首选归属 / 动作 |
| --- | --- | --- |
| 已落地的最小 tool declaration / framework `fetch_more` | P5 已落地最小 `@tool` / `ToolDefinition` / `ToolBundle` declaration、LLM-facing fetch_more hint / schema / framework route | 标为 P5 最小闭环已实现；只核对升级边界、public fetch_more API 收敛和旧文档过时判断，不得重复排期 |
| 完整 ToolRegistry / tool catalog / display metadata 治理 / permission / middleware | P5 只落地最小 declaration 与 framework `fetch_more`，完整 registry / catalog / permission / middleware 未落地 | P10 已安排；核对 P10 是否只做通用 ToolRegistry，不迁移 business fins / doc / web 工具 |
| business fins tools / doc / web 工具迁移 / Service catalog | P2 / P3 / P5 明确非目标，当前 Host 不承载财报业务语义，完整 Service catalog 与业务工具装配未落地 | 建议新增业务工具迁移 issue 或 phase；必须守住 `dayu.fins.storage` 边界，并拆分于 Host 通用 ToolRegistry 治理 |
| OutputContract / validation replay | P4 / P5 明确不做，design 有设计点，P5.5 后已单列 P11 | P11 已安排；核对 OutputContractRef、ValidationDecision、replay attempt 上限、恢复 / 失败收口，不得自然归入普通 governance、P4 compact retry 或 P15 audit hard-gate |
| EventLog persistence / projection / observers | P1.5 / P2 / P3 / P4 / P5 多次后移 | P6 已安排；核对是否覆盖多进程安全 atomic append / cursor allocation、observer / sink 基础、audit、timeline、memory projection 重建、metrics、checkpoint、required projection；具体 tool trace schema 由 P7 承接 |
| tool trace projection / sink | OLD tool trace 从 Engine 私有 recorder/store 移出后尚未落地 NEW Host 派生能力 | P7 已安排；核对是否基于 P6 observer / sink，从 Engine / ToolRuntime canonical events 派生，并对齐 OLD tool trace schema |
| Session lifecycle / admission / idempotency / public interface | P1-P5 多次后移；当前 `dayu.host.__init__` 仍是 no-full-governance smoke surface | P9 已安排；核对 `client_request_id`、同 Session active Run、cancel 基础治理、状态机，并确认依赖 P8 attempt ownership。P9 必须调查 OLD wechat / web / prompt / interactive 对 Host public interface 的真实需求，再固定 `docs/host/design.md` 第 5 节和 `dayu.host` public exports |
| Attempt lease / recovery / fencing | P1.5 / P3 / P4 / P5 后移 | P8 已安排且优先于 lifecycle；核对 owner token、lease、startup recovery、orphan / stale、late write fencing |
| RemoteProxy / RemoteStub | P1-P5 后移 | P13 已安排；核对 cursor / ack / reconnect / remote cancel 与“远端执行工具”边界 |
| Reply Outbox | P3 / P4 / P5 后移 | P12 已安排；核对 delivery key、claim / retry / reconcile、final answer projection |
| Wait / Suspend / Resume | P1.5 / P3 / P5 后移 | P14 已安排；核对 WaitRecord、awaiting outcome、auto resume、取消 / 超时 |
| audit hard-gate / required projection | P2 / P4 / P5 后移 | P15 或 P6+P15；核对 observer 与 hard-gate 状态机是否分清 |
| Engine / Host interface freeze | P16 后不能再随意修改 Engine / Host public contracts | P16 已安排；核对是否产出 interface freeze 方案、契约变更治理规则、package export / import boundary / event contract 守护测试 |
| memory governance | P3 / P5 后移 | 同 session memory 结构已由 P3 落地；多进程场景需要 P6 durable EventLog / projection 重建 session memory read model。长期记忆、跨 scope memory、public edit/reset/forget 不阻塞 Full-Governance Multi-Turn，已由 GitHub issue #24 跟踪 |
| context governance | P4 明确只做最小 compact retry | 不阻塞 Full-Governance Multi-Turn 主迁移，已由 GitHub issue #23 跟踪；P5.5 只需确认 P6+ 不把它误写成阻塞项 |
| provider token estimator issue | P4 已落地 Host 内部估算口径，但不是 provider tokenizer 真源 | 已由 GitHub issue #20 跟踪，避免把相对估算写成生产预算真源 |
| transparent fetch_more / Host-side continuation | P5 已落地 LLM-facing framework `fetch_more`，未落地 Host-side transparent continuation | LLM-facing framework `fetch_more` 标为已实现；Host-side transparent continuation 不是 Full-Governance Multi-Turn 必需项，后续如需改善 UX 再单独讨论 |
| public memory edit / reset / forget | P3 / P5 后移 | 不阻塞 Full-Governance Multi-Turn，已由 GitHub issue #24 跟踪 |
| episode summary / durable retrieval index | P3 / design 后移 | 需核对 context / memory governance 归属 |
| cancellation hardening / watchdog / force terminate | P1 / P5 后移 | P15 与 GitHub issue #3 已安排；核对 P9 基础 cancel 与 P15 增强边界 |

## 工作步骤

1. 确认基线与工作树：
   - 运行 `git status --short`，记录是否已有用户改动。
   - 运行 `git log --oneline -1`，确认 P5 merge 基线。
   - 若存在与本任务无关的用户改动，不得回退；若影响文档写入，先向用户说明。

2. 建立 deferred 原始清单：
   - 对 P1、P1.5、P2、P3、P4、P5 phase plan 分别扫描“非目标 / 不实现 / 后移 / deferred”段落。
   - 每个条目保留 `source_kind`、来源文件、行号、原文短摘和所属能力域。
   - 不能只扫标题；review finding 和 “Remaining risks / deferred scope” 也必须纳入。

3. 与当前事实核对：
   - 用 `dayu/host/README.md`、`docs/host/design.md`、当前代码 / 测试 / smoke 脚本核对 P5 已落地事实。
   - 对 P5 前预扫中已经过时的判断标记为“历史线索已被 P5 改写”，不得继续作为当前事实。
   - 对真实 provider smoke、生产治理、多进程能力等依赖外部环境或未实现治理的能力，必须写清楚证据边界。
   - 对 LLM-facing `fetch_more` / hint / framework route，必须核对 P5 最小闭环已落地事实；P5.5 只判断升级边界和旧文档过时口径，不得把它重新列为未安排能力。
   - 对真实 provider smoke，只记录“人工证据 / 环境依赖边界”，不得写成 CI 必过项、P6+ 能力缺口或 P5 每次已通过事实。

4. 与 migration-plan P6+ 排期核对：
   - 对每个 item 查找 P6-P16 是否已有承接。
   - 若已有承接，检查 phase 名称、目标、明确不做和验收信号是否足以覆盖该 item。
   - 若承接不清，提出“调整现有 phase”的 patch 建议；若完全缺失，提出新增 phase / issue。
   - OutputContract / validation replay 必须独立判断归属；不能因为 P15 有 governance hardening / audit hard-gate 字样就视为已安排。
   - Tool declaration、完整 ToolRegistry / catalog / permission / middleware、business fins tools / Service catalog 必须拆分判断；Host / Engine 不得承载财报业务语义。

5. 写出 deferred inventory 与能力归属表：
   - 使用固定状态枚举，不允许模糊状态。
   - 对风险较高的财报可靠性项单独标注：OutputContract、validation replay、business fins tools、ToolRegistry、audit hard-gate、provider token estimator。
   - 对已实现项写清楚“最小实现”或“no-full-governance 实现”的边界，不得升级成生产治理事实。
   - 对每个能力域保留至少一个原始 source item；同一能力有多个来源时，能力归属表可以汇总，但 deferred inventory 不得丢失 source_kind / source file / 短摘。

6. 准备 migration-plan 修订 patch 清单：
   - 先列 patch 清单，不直接大改总控计划。
   - 常规 plan review 与必要专项 review 通过后，仍必须停等用户人工确认；用户确认后才允许写回 `docs/host/migration-plan.md`。
   - 用户确认后若写回 migration-plan，优先只改：
     - 当前状态中 P5 已 merge 的事实。
     - P5.5 输出物与验收信号。
     - P6-P16 phase 表中确实漏排或误排的目标 / 明确不做 / 验收信号。
   - 不把 phase handoff 细节塞进 migration-plan；migration-plan 只保留总控节奏、阶段顺序、阶段边界和必须产物。

7. 接受 review：
   - 常规 plan review 检查扫描范围、分类规则、输出物、停止点、README / docs 触发判断是否完整。
   - 至少增加一个 OLD / NEW 或最佳实践 / 架构边界 review。
   - review finding 修复后，必须在对应 review 文档 finding 标题标注修复状态，再复审。

8. 停止：
   - plan review 通过后停下来等用户人工 review。
   - 用户确认前不得实施 inventory 扫描结果的 migration-plan 写回，不得 commit / push。

## 文件级改动清单

本 plan 编写阶段只新增 / 修改：

- `docs/host/phase5_5-plan.md`
  - 固定 P5.5 的目标、非目标、扫描范围、输出物、分类规则、工作步骤、验收标准、review gate 与停止点。

P5.5 后续实施阶段允许在 review / 用户确认后修改：

- `docs/host/phase5_5-plan.md`
  - 填入 deferred inventory、能力归属表、phase 调整建议、新增 phase / issue 建议、需用户确认关闭列表和 patch 清单。
- `docs/host/migration-plan.md`
  - 仅在常规 plan review 与必要专项 review 通过、且用户人工确认后，写回经确认的总控计划修订。
- 可选新增 review 文档：
  - `docs/host/phase5_5-plan-review.md`
  - `docs/host/phase5_5-old-new-review.md` 或 `docs/host/phase5_5-best-practice-review.md`

不得修改生产代码、测试代码、schema 或 smoke 脚本。

## 契约、状态机与持久化影响

- 新增 / 修改契约：无生产契约变更。P5.5 只定义文档 inventory 字段与分类状态。
- 状态机变化：无。
- 数据持久化 / schema 变化：无。
- 多进程并发影响：无生产影响；只核对 P6-P9 是否已经覆盖持久化、admission、lease、fencing、recovery。
- ToolRuntime / EngineWorker / Engine 边界影响：无代码影响；只核对完整 ToolRegistry / business tools 的后续归属是否清晰，并确认 P5 已落地的 framework `fetch_more` 最小闭环不被重复排期。
- EventLog / RunEventStore / projection 影响：无代码影响；只核对 P6 persistence / projection / observers / required projection 的后续归属是否清晰。
- runtime dependency：无新增 runtime helper；不得因扫描任务新增 `dayu.runtime` 代码。

## README / docs 触发判断

本 plan 编写阶段只修改 `docs/host/phase5_5-plan.md`，不触发 `dayu/host/README.md`、`tests/README.md` 或根 README 的当前事实同步。

P5.5 后续实施若只修改 `docs/host/migration-plan.md` 与 P5.5 inventory / review 文档，也不应机械更新 README。只有当 P5.5 发现并修正当前事实文档中的过时描述，且该描述属于对应 README 的目标读者职责时，才按 `AGENTS.md` 的 README 触发规则更新。

## 测试与验证命令

本阶段不写生产代码或测试代码，不运行 pytest 作为必需项。文档修改后必须至少运行以下自查：

```bash
sed -n '1,260p' docs/host/phase5_5-plan.md
PHASE55_FORBIDDEN='真实 provider 已通''过|完整治理已落''地|生产级.*已落''地|删除.*earl''y'
rg -n "$PHASE55_FORBIDDEN" docs/host/phase5_5-plan.md docs/host/phase5_5-early-scan.md
rg -n "^## " docs/host/phase5_5-plan.md
git diff -- docs/host/phase5_5-plan.md
```

如果后续 P5.5 实施阶段实际修改 `docs/host/migration-plan.md` 或 README，还必须对修改文件运行 `sed` / `rg` 自查，确认没有把未落地能力写成已落地事实。

## 验收标准

- P1、P1.5、P2、P3、P4、P5 的 deferred / 非目标 item 均被逐项覆盖，没有只按能力域粗略合并后丢失原始条目。
- deferred inventory 每项均记录 `source_kind`、source file 和原文短摘，能力域汇总不得替代原始 deferred 条目。
- 每个 deferred item 都有明确状态：已实现、已安排到 P6+、需调整现有 P6+ phase、需新增 phase / issue、需用户确认关闭。
- 每个状态判断都有直接证据；root cause / 当前事实判断必须逻辑与数据同源，不用间接迹象替代。
- `docs/host/phase5_5-early-scan.md` 被明确标记为 P5 前预扫历史参考，过时判断不得进入当前事实。
- 不把未落地能力写成已落地事实；尤其不得把 no-full-governance smoke 写成完整生产治理。
- OutputContract / validation replay 被作为最高漏排风险独立核对，并给出明确归属建议；不得自然归入普通 governance、P4 compact retry 或 P15 audit hard-gate。
- Tool declaration、完整 ToolRegistry / catalog / permission / middleware、business fins tools / Service catalog 被拆分归属；不得重复排期 P5 已落地的最小 `@tool` / `ToolDefinition` / framework `fetch_more`。
- 真实 provider smoke 只作为环境依赖的人工证据边界记录，不得写成 CI 必过项、能力缺口或 P5 已每次通过事实。
- 不改生产代码、不改测试代码、不改 schema、不新增 workspace migration。
- 若建议调整 migration-plan，必须先输出 patch 清单；常规 plan review 与必要专项 review 通过后仍必须停等用户人工确认；用户确认后才允许写回 `docs/host/migration-plan.md`。
- Review 通过后停等用户人工 review，不实施后续 phase，也不 commit / push。

## Review gate

P5.5 至少需要以下 review：

- 常规 plan review：检查目标、非目标、扫描范围、输出物、分类规则、验收标准、验证命令和停止点。
- OLD / NEW 或最佳实践 / 架构边界 review 至少一个：核对 deferred 分类是否符合 Host / Engine 分层、EventLog 真源、ToolRuntime 边界、财报业务中立边界和 OLD 语义继承 / 后移判断。

专项检查要求：

- 如果涉及 OutputContract、validation replay、ToolRegistry、business fins tools、provider token estimator、audit hard-gate、context governance 或 memory governance，review 必须明确检查是否漏排、误排或被错误归类为生产治理；OutputContract / validation replay 必须作为最高漏排风险单独检查，不能自然归入普通 governance、P4 compact retry 或 P15 audit hard-gate。
- 如果涉及 tool 能力，review 必须检查 P5 已落地的最小 `@tool` / `ToolDefinition` / `ToolBundle`、LLM-facing `fetch_more` hint / schema / framework route 没有被重复排期，并检查完整 ToolRegistry / catalog / permission / middleware 与 business fins tools / Service catalog 的归属是否拆分。
- 如果涉及 `dayu.fins.storage`，review 必须检查财报文档存取边界是否仍由业务工具保证，没有进入 Host / Engine 通用语义。
- 如果涉及 EventLog persistence / projection，review 必须检查 P6 observer / sink 基础、P7 tool trace 派生与 P15 audit hard-gate 的边界是否分清。
- 如果涉及 lifecycle / recovery，review 必须检查 P9 Session / Run governance 与 P8 Attempt lease / recovery 是否分清。

review finding 修复规则：

- finding 修复后必须在 review 文档 finding 标题标注 `已修复` / `已处理` 等状态。
- 复审通过前，不得声称 P5.5 plan review 完成。
- review 通过后停等用户人工 review。

## 风险与回滚

- 风险：把 P5 前 early scan 的旧判断当作当前事实。缓解：所有判断必须回到当前 main、README、design、代码 / 测试核证。
- 风险：把 P5 最小 tool declaration 误判为完整 ToolRegistry。缓解：分类时显式区分 declaration / bundle、framework `fetch_more` 与生产 registry / permission / middleware / catalog。
- 风险：把 OutputContract / validation replay 混入 P4 compact 或 P15 audit hard-gate 后漏排。缓解：作为财报可靠性专项检查，若 migration-plan 无清晰归属则新增 phase / issue 建议。
- 风险：migration-plan 修订过重，变成后续 phase handoff 细节。缓解：只写总控级目标、边界、验收信号和产物。
- 回滚：本阶段只改文档；若 review 不认可，按 review finding 修订 `docs/host/phase5_5-plan.md`，不得回退用户已有改动。

## 待用户确认项

- P5.5 deferred inventory 是集中留在 `docs/host/phase5_5-plan.md`，还是 review 后拆成独立 `docs/host/phase5_5-deferred-inventory.md`。
- OutputContract / validation replay 已单列 P11；后续用户 review 需确认 P11 是否作为独立 phase 保留，还是调整某个现有 P6+ phase 并把验收信号写清楚；不得仅以 P15 Governance Hardening / audit hard-gate 兜底。
- 完整 ToolRegistry / catalog / permission / middleware 已单列 P10；business fins / doc / web 工具迁移不属于 Host 迁移主线，后续如需执行应单独创建业务工具迁移 issue / phase。
- LLM-facing framework `fetch_more` 已由 P5 落地；Host-side transparent continuation 不是 Full-Governance Multi-Turn 必需项，后续如需改善 UX 再单独讨论。
- provider token estimator / tokenizer adapter 已由 GitHub issue #20 跟踪；context governance 已由 GitHub issue #23 跟踪。

## 停止点

P5.5 plan review 通过后必须停止，等待用户人工 review。用户确认前不得：

- 实施 deferred inventory 的 migration-plan 写回。
- 写生产代码或测试代码。
- commit / push / 创建 PR。
- 关闭任何 deferred item。

## 实施完成汇报格式

P5.5 plan 编写 Agent 最终汇报必须包含：

- 修改了哪些文件。
- 自查运行了哪些 `sed` / `rg` / `git diff` 命令。
- 哪些内容刻意未修改，例如 early scan 未删除、migration-plan 未写回、生产代码未改。
- 未决问题和需要用户确认的事项。

P5.5 后续实施 Agent 最终汇报还必须包含：

- deferred item 总数与各状态数量。
- 建议调整的 P6+ phase 列表。
- 建议新增 phase / issue 列表。
- 需用户确认关闭列表。
- review 状态与停止点。
