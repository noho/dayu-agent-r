# Host Issues Implementation Control

## 文档职责

本文档是 Host follow-up 中已由 GitHub Issue、umbrella issue、依赖链或过期裁决承接的 work units 实施总控文档。

本文档只承担实施编排职责：记录 issue-backed work unit 的范围、当前状态、issue owner / destination、进入条件、交付物、验证要求、review 结果、residual risk 和下一步入口。

已完成、已关闭、已并入、已通过最终 closeout、经用户裁决算作完成，或依附于已完成 work unit 的 obsolete 历史条目归档在 `docs/host/issues-implementation-control-archive.md`；本文档只保留仍可能影响下一步实施、裁决或留痕的 active/backlog 条目。

本文档不替代 Host 设计真源，不承载新的架构决策，不作为实现细节说明书。若某个 work unit 的讨论发现需要修改架构边界、状态机、公共接口、durable schema、EventLog 语义或跨层契约，必须先更新设计真源，再更新本文档和对应 GitHub Issue。

## 设计目标

Host issue-backed follow-up 实施必须始终服务于以下目标：

- 生产级通用 Agent，具备买方财报分析能力。
- 范式是“宿主强约束下的 LLM in the loop”。
- Host 对 Agent / Runner 的生命周期、取消、恢复、等待、上下文治理、审计与 durable truth 保持强约束。
- 严格遵守 `UI -> Service -> Host -> Engine` 分层边界，禁止反向依赖和跨层泄漏实现细节。
- 已有 GitHub Issue 的 work unit 必须尊重 issue owner / destination；不得在本文档中绕过 issue scope 抢先实施。
- 依赖型 work unit 必须等待前置 issue 完成后再进入 implementation gate；不得用测试私有入口或临时桥接伪造 production-grade 验收。
- 过期失效 work unit 只保留留痕，不作为实施入口。

任何 plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项选择削弱这些目标，应停下来修正设计真源、本文档或对应 GitHub Issue 后再继续。

## 真源层级

Host issue-backed follow-up 实施遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源
  -> 约束跨层、跨 phase 的稳定术语含义

docs/host/design.md
  -> Host 架构真源
  -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、等待、上下文治理和关键治理路径

docs/engine/design.md
  -> Engine 架构真源
  -> issue 涉及 Engine provider、Runner、Agent 或 tool-calling contract 时必须同步核对

docs/host/issues-implementation-control.md
  -> issue-backed follow-up 实施编排文档
  -> 记录已由 GitHub Issue / umbrella / dependency / obsolete 裁决承接的 work units、当前状态、进入 / 退出条件、交付物、验证要求、review 结论和 residual risk

GitHub Issues
  -> 对应 work unit 的外部执行 owner / destination
  -> 记录 issue scope、讨论、PR 关联和跨文档追踪状态
```

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到设计真源，再更新本文档对应 work unit 的范围、非目标、验收信号和对应 GitHub Issue。

术语必须遵循项目级术语真源和 Host 设计真源。planning、implementation、review、fix 与 re-review 不得自行重解释 `Session`、`Run`、`Attempt`、`EventLog`、`HostEvent`、`EngineEvent`、`WAITING`、`RECOVERING`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`、`ToolRuntime`、`Conversation Memory` 等术语。若发现术语缺失或冲突，应先讨论并同步真源文档，再继续推进。

## 管理范围

本文档只管理以下类型的 work units：

- 已有独立 GitHub Issue owner / destination 的 work unit。
- 已有独立 GitHub Issue 且影响 Host / Engine 边界、provider/tool-calling contract、public product path 或后续 Host follow-up 的 cross-layer work unit。
- 已并入 umbrella issue 或 child issue 的 work unit。
- 必须等待其它 issue 完成后才能实施的依赖型 work unit。
- 已裁决过期失效，但仍需要在总控中保留留痕，避免后续误实施的 work unit。
- 经用户明确裁决要求纳入本文档留痕的 immediate residual work unit；这类条目必须在 Owner / Destination 中标明无 GitHub Issue，并记录用户裁决依据、进入条件和非目标。

除用户明确裁决的 immediate residual 记录项外，本文档不管理未建立 GitHub Issue 且可独立推进的 work unit。若某个 work unit 后续获得新的 GitHub Issue owner / destination，必须先在本文档中新增或更新对应条目，再按本文档状态进入 discussion / plan / implementation gate。

## 工作流

Host issue-backed work unit 采用以下工作流：

```text
read issues-implementation-control.md
  -> select one work unit
  -> inspect current GitHub Issue / dependency / obsolete status
  -> inspect current code and tests
  -> discuss scope, non-goals, risk, and design sufficiency with the user
  -> update docs/host/design.md first if architecture or public contract changes are needed
  -> update this control doc and the GitHub Issue if scope, status, owner, residual risk, or entry point changes
  -> generate code-generation-ready plan for the selected work unit when dependencies are satisfied
  -> review plan
  -> user confirmation
  -> implement through the current gate workflow
  -> verify tests, pyright, and relevant README/doc sync
  -> run review / re-review
  -> update current status, artifacts, commits, residual risk, GitHub Issue state, and next entry point
```

每次只推进一个 work unit。进入 plan gate 前，必须先完成 issue / dependency / code 核对和 scope discussion，确认该 work unit 仍应在当前 owner 下推进。

work unit plan 必须基于：

- Host 设计真源；
- 本文档中对应 work unit 的状态、issue owner / destination、目标、非目标、验收信号；
- 对应 GitHub Issue 的当前 scope；
- 代码核对得到的直接证据。

plan 不得从旧设计稿、旧代码路径、非真源讨论记录或 reviewer 个人偏好推导架构边界。
plan 必须避免过度设计；只能解决由 issue / dependency / 代码核对 / 设计真源直接支撑的当前 work unit 风险，不得把局部缺口扩大成通用框架、平台化能力或未来阶段能力。

plan 文档应放在 `docs/host/` 下；plan review、plan fix、plan re-review、implementation review、fix、re-review 和总控裁决 artifact 放在 `docs/reviews/` 下。

每个 work unit discussion 至少需要确认：

- work unit 目标与 success signal；
- 是否服务于本文档的设计目标；
- Host 设计真源是否足够具体；
- 对应 GitHub Issue 是否仍是正确 owner / destination；
- scope boundary、non-goals 与 stop conditions；
- 是否需要修改设计真源或 GitHub Issue；
- 是否存在会阻塞 code-generation-ready plan 的架构、状态机、公共接口、schema、持久化、依赖 issue 或测试问题。

## 仓库发布约定

Host issue-backed follow-up 实施相关分支的 GitHub remote 名称为 `github`。提交后推送当前分支时使用：

```bash
git push -u github <branch>
```

不得假设 remote 名称为 `origin`。

进入 draft PR gate 前，本文档必须更新当前 work unit 状态、plan artifact、review artifact、accepted commit、remaining risks / owners、GitHub Issue destination 和 next entry point。进入 draft PR gate 后，按既定 gate workflow 自动推进到 `draft-PR-pass`；merge、approve、mark ready for review、request reviewers、delete branch、对外 comment 或创建 / 修改外部 issue 仍需额外授权。

## Slice 切分原则

- 每个 work unit 内的 implementation slices 在 discussion / plan 阶段再具体确定；总控阶段不预先替 work units 固定 slice。
- slice 切分的初始出发点成立：单个 slice 太大时，implementation agent 容易因为上下文过长、局部约束丢失或跨边界状态过多而实现漂移。
- slice 必须控制模型一次实施和 reviewer 一次审查能够稳定承载的上下文规模。
- “上下文规模”不得粗暴等同于文件数、模块数、代码行数或 owner 数；更可靠的切分依据是语义闭环、依赖顺序、失败 / 回滚风险和验证矩阵。
- slice 必须满足模型上下文窗口与 review 可承载复杂度：implementation agent 能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 能在一个上下文中有效审查。
- slice 必须沿稳定代码依赖边界切分：公共契约、状态机边界、存储边界、projection 边界、issue dependency 边界或测试矩阵边界。
- slice 必须形成可独立验证的行为闭环：大到能形成可测试语义，小到能一次实现、一次验证、一次 review。
- 除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。
- slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理；好的 slice 必须有明确输入、输出、non-goals、allowed files / modules、验证命令、issue handoff 和后续 slice 可依赖的稳定交付物。
- 不得按模块数量、文件数量或 reviewer ownership 机械拆分。对代码量较小、语义上属于同一个 contract cleanup / config cleanup / schema cleanup 的 work unit，即使会同时触及配置、runtime、Service composition、provider、scene manifest、测试和 README，也应优先合并为少量可验证闭环 slices，而不是每个模块单独切片。
- 只有当某部分存在独立失败 / 回滚风险、需要独立设计裁决、会阻塞后续代码导入，或 review 上下文确实无法承载时，才继续拆分。
- 小型跨模块 cleanup 的默认切分上限是 3 个 implementation slices：
  - contract / config / composition slice：稳定公共语义、typed config、composition root effective config、旧字段拒绝与基础测试；
  - provider / behavior slice：业务 provider 行为、tool schema、存储 / 权限边界、provider 投影测试；
  - scene / docs / final validation slice：默认 scene 暴露面、README / design 同步、stale-field grep、pyright 与受影响测试矩阵。
- 默认 slice budget：
  - 小型同一语义 cleanup：1-3 个 implementation slices。
  - 中型跨 contract / provider / projection work：3-5 个 implementation slices。
  - 超过 5 个 implementation slices：必须有明确证据表明单个 implementation agent / reviewer 的上下文容量无法稳定承载，或存在必须隔离的 schema、状态机、持久化、外部依赖、回滚风险。
- 如果 plan 提出超过 3 个 implementation slices，必须显式说明为什么不能按上述闭环合并；仅以“涉及多个文件 / 多个模块 / 多个 owner”为理由不充分。
- 总控裁决时必须评估 gate 成本：每增加一个 slice 都会增加 implementation artifact、双路 review、controller 裁决、测试复跑和 accepted commit 成本；当流程成本明显超过实现风险时，应倾向合并 slice。
- 如果一个 work unit 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 plan 中说明前后 slice 的 contract handoff。
- 如果某个 slice 需要跨模块修改，plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## 当前状态

| 项目 | 当前值 |
|---|---|
| phase | `WU-CTX-01` Usage-Anchored Adaptive Context Sizing。 |
| active work unit | `WU-CTX-01`；类型为 GitHub Issue #20 对应的 architecture-sensitive issue / public-contract change。 |
| gate | `Slice 1 implementation re-review / pass；accepted slice commit bookkeeping` |
| blocking open questions | None。 |
| next entry point | Slice 1 fix artifact=`docs/reviews/wu-ctx-01-slice-1-implementation-review-fix-codex.md`；双路re-review=`docs/reviews/code-review-20260724-045325.md`与`docs/reviews/code-review-20260724-044856.md`均为`pass`；Controller final adjudication=`docs/reviews/wu-ctx-01-slice-1-implementation-rereview-controller-adjudication.md`，decision=`pass`。创建accepted Slice 1 protected commit后进入Slice 2 implementation。 |

## 推进规则

- 每次只推进一个 work unit。
- 先做 GitHub Issue / dependency / 代码核对，再进入方案和实现。
- Work units 必须按依赖顺序推进：底层 Engine / provider contract 优先于依赖该 contract 的 Host / Service / UI follow-up；umbrella issue 优先于其 child issue；dependent smoke 必须等待前置 production capability 完成。
- 已明确 `blocked-by-issue` 或 `obsolete` 的 work unit 不得绕过状态进入 implementation gate。
- 涉及 public contract、durable schema、状态机、跨层依赖或用户可见行为时，必须先形成明确 design decision。
- 测试优先按风险边界补齐；压力测试和长耗时测试必须与常规测试入口分开。
- 实施完成后必须更新对应测试、类型检查、稳定文档说明和对应 GitHub Issue 状态。
- 每个 work unit 进入 plan、implementation、review、ready-to-open-draft-PR 或 draft-PR-pass 时，必须更新“当前状态”中的 gate、active work unit、next entry point 和 blocking open questions；artifact、commit、review 与历史验证记录写入对应 work unit、review artifact 或 closeout artifact，不在“当前状态”表中累积流水账。

## 实施顺序

用户已明确选择并确认 `WU-CTX-01`。PR #182 已合并，目标 base merge 状态、工作树与 `main` fast-forward preflight 均已通过；`WU-CTX-01` 已激活并进入固定 gate workflow。

1. 用户手工 merge PR #182 后，先在目标 base 依次完成 merge 状态、工作树、`main` fast-forward preflight；三项全部通过后，进入 `WU-CTX-01` goal confirmation。其唯一设计入口是 `docs/host/design.md` §25 “Context Governance”中的 Usage-Anchored Adaptive Context Sizing。
2. `WU-CTX-01` 的 GitHub Issue #20 title / body 已与设计真源对齐。provider live evidence 不是进入 plan 的前置条件；usage 缺失、非法或 pairing 不可信时必须回退到当前完整输入的 conservative estimate，provider 不返回 usage 不得导致 Run 失败。
3. Tool Trace diagnostics lane 若后续被选择，先推进 `WU-OBS-00`；`WU-OBS-00A` / `WU-OBS-00B` 是其子项，`WU-OBS-01` 必须等待 analyzer 基础能力成立。
4. Retention lane 的固定顺序见“Retention Issue Dependency / Implementation Order”：`WU-RET-01` -> `WU-RET-03` -> `WU-RET-04` -> `WU-RET-02`。
5. `WU-AUDIT-01`、`WU-AUDIT-02` 与 `WU-STRESS-SQLITE-01` 等 backlog 继续等待用户或主总控后续选定，不因本文档排序自动获得优先级；`WU-GOV-01`、`WU-CLI-SMOKE-01-R2`、`WU-CM-10` 与 `WU-CM-11` 保持 deferred。

## Residual Risk / 遗留问题追踪

本章节专门追踪实施过程中发现但未在当前 work unit 内关闭的 residual risk、遗留问题、测试缺口、设计疑问、issue dependency 和后续 owner。不得把这类事项只停留在对话、review artifact、implementation report 或 GitHub Issue comment 中。

追踪规则：

- 每条 tracking item 必须有稳定 id、来源 work unit、状态、owner / destination 和下一步动作。
- `ready-to-open-draft-PR` 前，所有 tracking items 必须处于 `closed`、`deferred-with-owner` 或 `transferred-to-issue`，不得保留无 owner 的 open item。
- 如果 residual risk 需要修改 Host 架构、公共契约、状态机、durable schema 或 EventLog 语义，必须先同步设计真源，再更新本表和对应 GitHub Issue。
- 如果 residual risk 已由代码核对证明不存在，应标记 `closed` 并记录关闭依据，不继续保留为模糊风险。

状态值：

- `open`：仍需当前 work unit 或本轮 phase 处理。
- `deferred-with-owner`：明确后续 owner / work unit / issue，当前 work unit 不处理。
- `transferred-to-issue`：已迁移到独立 GitHub Issue 或等价外部追踪项。
- `closed`：已通过实现、测试、设计裁决或代码核对关闭。

Residual Risk Reconciliation 后，本表只保留仍存在的 residual risk；已关闭项从 active 表删除，关闭依据保存在对应 review / reconciliation artifact 中。

| ID | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|
| WU-ENG-02-S3-R1 | transferred-to-issue | WU-OBS-00B / GitHub Issue #119 under #70 analyzer | analyzer 实施时确认 usage observation projection signal 是否需要扩展 correlation fields。 |
| WU-TOOLS-01-S1-R1 | transferred-to-issue | GitHub Issues #121 and #122 | SEC/Fins CI pipeline / smoke 与 CN/HK Docling CI pipeline / smoke 改由对应 issue 直接追踪；不再作为本文档默认 next work unit。 |
| WU-CLI-SMOKE-01-R2 | deferred-with-owner | CLI UI adapter lane / user decision；无 GitHub Issue | `CliThinkingRenderer` 当前把每个 delta 单行化并按 160 字符截断后持续追加到同一运行态行；累计行并非 160 字符总上限，也没有可展开 panel/history。仅在用户提出明确 thinking UX、累计缓冲上限与终端交互要求后进入 goal confirmation。不得修改 Host transient/durable contract、持久化 thinking、增加 replay，或改变 provider reasoning 开关。 |

## 当前 Work Units

| Work Unit | 状态 | 主题 | Owner / Destination | 当前定位 |
|---|---|---|---|---|
| WU-OBS-00 | pending | Tool Trace analyzer | GitHub Issue #70 | 前置 signal bundle 已完成；trace 文件 / 目录输入的 Host / Engine / Tool 分层诊断；WU-OBS-01 的诊断底座 |
| WU-OBS-00A | pending-parent | Tool Trace analyzer integrity and large payload diagnostics | GitHub Issue #34 / #70 child | #70 analyzer 子项；不单独实现一套 analyzer |
| WU-OBS-00B | pending-parent | Usage observation projection correlation boundary | GitHub Issue #119 / #70 child | #70 analyzer 子项；owner for residual `WU-ENG-02-S3-R1` |
| WU-OBS-01 | pending-prerequisite | Prompt-based Tool Trace diagnostics | GitHub Issue #71；GitHub Issue #27 superseded | #71 作为主 issue，吸收 #27 的 prompt / final answer 反查诉求 |
| WU-AUDIT-01 | pending | Audit Ledger viewer and integrity report | GitHub Issue #72 | read-only audit JSONL ledger viewer；审计责任链 / 完整性校验，不做 Tool Trace root-cause analyzer |
| WU-AUDIT-02 | pending | External audit delivery contract with local validation adapters | GitHub Issue #75 | async external audit delivery 语义；无真实外部系统时先用 Noop / FileMirror adapter 验证 contract |
| WU-RET-01 | pending | Tool Trace cold JSONL storage governance | GitHub Issue #36 / #43 child | Retention lane 默认第 1 项；Tool Trace cold JSONL rotation / retention / compaction / size reporting；不作为 #70 前置 |
| WU-RET-03 | pending | purge_session-driven retention cleanup | GitHub Issue #78 / #43 child | Retention lane 默认第 2 项；定义 `purge_session` 驱动的 session-scoped retention cleanup owner；解锁 WU-RET-04 |
| WU-RET-04 | pending-prerequisite | Compaction artifact retention | GitHub Issue #156 / #78 child | Retention lane 默认第 3 项；必须等待 WU-RET-03 / #78 固定 purge cleanup 边界后实施 |
| WU-RET-02 | pending | Audit JSONL storage governance | GitHub Issue #96 / #43 child | Retention lane 默认第 4 项；Audit JSONL rotation / retention / compaction / size reporting；保留 purge tombstone 可验证关联 |
| WU-STRESS-SQLITE-01 | pending | SQLite multiprocess high-spec stress | GitHub Issue #38 | 现有 SQLite 多进程压力测试链路的慢盘 / Docker Linux 高规格版本 |
| WU-GOV-01 | deferred | Host policy refusal terminal taxonomy | GitHub Issue #88 / future tool-permission work | 用户裁决：不单独推进状态 taxonomy；等具体工具权限 / 审批能力进入排期时再一并进入 goal confirmation，避免在没有真实 policy consumer 时预先设计 `REJECTED` 迁移。 |
| WU-CLI-SMOKE-01-R2 | deferred | Expandable CLI thinking runtime display | CLI UI adapter lane / user decision；无 GitHub Issue | 等待明确用户 UX 要求；先裁决累计行上限、滚动/展开语义、TTY/非 TTY 与历史保留边界，不是当前 implementation entry point。 |
| WU-CTX-04 | draft-pr-open / final-closeout-pass | Per-Session attachment ownership and proactive governance single-operation boundary | GitHub Issue #112 / draft PR #182 | accepted plan=`1f032b5e`；accepted Slice 1=`eda1d70e`；accepted Slice 2=`4ca0810b`；accepted Slice 3=`24dfcf37`；aggregate deepreview PASS；等待用户review/merge。 |
| WU-CTX-01 | pending-next-after-merge | Usage-Anchored Adaptive Context Sizing | GitHub Issue #20；外部 body 待对齐 | PR #182 手工 merge 与目标 base preflight 通过后唯一 next Work Unit；实现 usage anchor + conservative-estimated delta，并在 goal confirmation 对全部 provider family 做真实流式调用核对 |
| WU-CM-10 | deferred | Conversation Memory eval benchmark | GitHub Issue #80 / #81 follow-up | deferred behind #81；post-#81 memory semantic contract 稳定后再实施 |
| WU-CM-11 | deferred | User Profile Memory durable boundary and cross-session profile | GitHub Issue #115 / #81 child | deferred behind #81；#81 只固定 User Profile 不混入 session Conversation Memory 的边界，跨 session durable profile 独立后续实施 |

## WU-OBS-00 Tool Trace Analyzer

### 状态

GitHub Issue #70 当前为 OPEN。本条是 Tool Trace observability / debug tooling 的基础 work unit：输入已经存在的 Tool Trace 文件或目录，输出结构化 Host / Engine / Tool 分层诊断报告。它不是 #71 的重复，而是 #71 的自然前置能力；#71 负责“先按 prompt / final answer 找到 run 并导出 bundle”，本条负责“对 trace / bundle 做诊断归因”。WU-OBS-P00 / #70 + #117 与 WU-OBS-SIGNALS-01 已完成 analyzer 所需的前置核心 trace signals；本条状态为 pending，可进入 GitHub Issue / dependency / code scope 核对与 discussion gate。对 provider / model bug 报障场景，本条应消费 WU-ENG-02 / #63 已完成的 OpenAI-compatible provider debugging correlation signals；#64 的 native Anthropic / Claude Code gateway adapter-specific signals 若尚未实现，报告必须明确 limited signal。GitHub Issue #34 是本条的 analyzer integrity / large payload diagnostics 子项，不单独实现平行 analyzer。

### 设计与代码核对

- `docs/host/design.md` 明确 Tool Trace 是 committed EventLog 的派生 projection，不是 Host recovery、resume、memory 或 Run 状态迁移真源。
- `docs/host/design.md` 要求 trace / audit 能解释工具结果保留、压缩、丢弃、召回失败、证据不足、预算未纳入 RunInput 等原因。
- `dayu/host/tool_trace.py` 当前负责从 committed EventLog 投影 Tool Trace hot row 与 cold JSONL line。
- `dayu/host/durable/tool_trace.py` 当前提供按 `run_id`、`tool_call_id`、`provider_request_id`、`diagnostic_ref` 查询 hot rows 的内部 helper。
- `tests/host/test_tool_trace_projection.py` 与 `tests/host/test_tool_trace_queries.py` 已覆盖 Tool Trace 生产、冷热投影、query helper 与分页。
- `tests/host/test_tool_trace_queries.py` 已覆盖 `provider_request_id` 可查询 terminal diagnostic chain；但当前没有 analyzer report，因此尚未覆盖“报告必须展示 provider 厂商可查 request id”的输出要求。
- 代码核对未发现现有 operator-facing Tool Trace analyzer；也未发现可对 trace 文件 / 目录生成 Host / Engine / Tool 分层诊断 Markdown / structured report 的入口。
- WU-OBS-SIGNALS-01 已将 #29 / #30 / #31 / #35 的 context budget snapshot、tool latency、structured failure metadata、provider protocol partial tool-call semantics 收敛为前置 signal contract bundle；本条进入 implementation 前仍需核对当前代码与 trace fixture 的直接证据。
- GitHub Issue #34 的旧描述提到 P7 JSONL record 引用 raw payload 文件；当前 NEW / dayu-agent-r 已转为 committed EventLog -> Tool Trace hot row / cold JSONL projection，并通过 `payload_ref` / `payload_digest`、`source_payload_ref` / `source_payload_digest`、`cold_trace_ref` / `cold_trace_digest` 表达引用与完整性。因此 #34 的目标仍成立，但验收对象应更新为当前 Tool Trace hot / cold / payload descriptor 形态。

### 目标

- 新增本地 operator-facing Tool Trace analyzer，输入当前 Dayu 产生的 Tool Trace 文件或目录，输出结构化诊断报告。
- 报告按 Host / Engine / Tool 三层归因，并且每条诊断必须指向 trace 直接证据。
- 聚合 run、attempt / iteration、tool call、final response、protocol error、usage、diagnostic ref、payload digest / ref 等 trace 记录。
- 当诊断指向 provider / model bug、provider protocol error、filtering / safety signal 或 stream/non-stream 输出异常时，报告必须包含 provider/vendor debugging block：provider-native request id、client correlation id（若存在）、本地 `run_id` / iteration / attempt / tool trace refs；缺失时明确标注 limited signal。
- 识别重复调用、工具失败、异常延迟、过大 payload、截断与 fetch_more 缺失、trace 缺字段或冷热引用不一致。
- 覆盖 #34 的完整性检查：cold JSONL 行可解析性、`line_digest` / `cold_trace_digest` 一致性、hot row 与 cold line source key 一致性、`payload_ref` / `payload_digest` 可解析性或缺失报告、重复 / 缺失 ref 诊断。
- 覆盖 #34 的大 payload 诊断：large raw input、large tool result、large provider diagnostic payload、large prompt / messages 或等价 payload descriptor 的阈值告警与排名。
- 消费 WU-OBS-P01 / P02 / P03 提供的 context pressure、tool latency 和 structured failure metadata；缺失时必须在 report 中明确标注 limited signal，而不是静默降级。
- 消费 WU-OBS-P04 提供的 provider protocol partial tool-call signals；缺失时必须能区分 limited signal 与真正无 partial。
- 结合 context pressure / truncation / governance / wait / replay / projection signal，判断问题更像 Host 治理、Engine 输出 / 解析，还是 Tool schema / result contract。
- 输出 Markdown 或等价可读报告，包含问题摘要、分层归因、证据、优先级和建议动作。

### 非目标

- 不修改 Tool Trace 生产路径语义。
- 不把分析报告作为 Host durable truth。
- 不要求接入真实 provider 或外部服务。
- 不在本条重构 ToolRuntime、Engine、Host 生产模块。
- 不实现 prompt / final answer 反查；该能力由 WU-OBS-01 / GitHub Issue #71 承接。
- 不把财报业务判断写进 analyzer；只做 trace / protocol / contract / governance 层诊断。
- 不恢复旧 P7 `raw_payloads` 文件布局；analyzer 必须以当前 Dayu Tool Trace hot / cold / payload descriptor 形态为准。

### 验收信号

- 对当前 Tool Trace 文件或目录可以生成诊断报告。
- 报告明确分组 Host / Engine / Tool 问题，并给出直接 trace 证据。
- 至少覆盖重复调用、工具失败、SSE / protocol 异常、过大 payload、截断后未续读、trace 缺字段或冷热引用不一致。
- provider / model bug 相关报告必须展示厂商可查的 provider-native request id，并回链本地 `run_id` / iteration / attempt / tool trace；OpenAI-compatible path 应消费 #63 已完成的 client correlation signal；#64 native Anthropic / Claude Code gateway adapter-specific signal 尚不可用时，报告必须明确说明 limited signal，而不是静默省略。
- #34 覆盖的 integrity checks 有测试 fixture：missing cold line、corrupt JSONL line、line digest mismatch、hot / cold source key mismatch、payload ref missing / digest mismatch 或等价当前形态的不一致。
- #34 覆盖的 large payload diagnostics 有测试 fixture：large raw input、large tool result、large provider diagnostic payload、large prompt / messages 或等价 payload descriptor 超阈值。
- 核心解析、聚合逻辑和代表性诊断规则有测试。
- README 或 usage docs 说明输入、输出和典型命令。
- WU-OBS-01 能复用本条 analyzer 或其诊断规则，而不是重新实现一套分层归因。

## WU-OBS-00B Usage Observation Projection Correlation Boundary

### 状态

Pending。该 work unit 是 GitHub Issue #119 / #70 analyzer 子项，也是 residual `WU-ENG-02-S3-R1` 的 owner。

### 动机

WU-ENG-02 已完成 provider request identity 的 shared contract，但 Slice 3 review 发现 usage observation projection signal 是否需要 `client_correlation_id` 与 `provider_request_id` 还没有 analyzer 需求证据。当前 `UsageReportedData` 不包含这些字段，Host 也不能从 `iteration_id` 推断 provider request identity。这个问题应由 analyzer 需求确认，而不是在 Host payload 中提前硬塞 correlation 字段。

### 目标

- 在 WU-OBS-00 / #70 analyzer 设计和实现时，确认 usage observation 是否需要展示 client correlation id 或 provider request id。
- 若 analyzer 需要这些字段，先扩展 Runner usage / Engine `UsageReportedData` producer contract，再补 Host payload projection 和 Tool Trace analyzer tests。
- 若 analyzer 不需要这些字段，明确关闭 `WU-ENG-02-S3-R1`，记录 usage observation 只作为 post-call observation / analyzer signal。
- 保持 provider debugging terminal 主链路与 usage observation signal 分离，避免把 provider request identity 从非同源字段推断出来。

### 非目标

- 不在 WU-OBS-00B 中实现完整 Tool Trace analyzer。
- 不通过 Host 侧 hardcode 或 `iteration_id` 推断 provider request identity。
- 不修改 WU-ENG-02 已接受的 provider request identity contract。

### 验收信号

- Analyzer plan 或 implementation 明确裁决 usage observation 是否需要 correlation fields。
- 若需要扩展，Engine producer、Host projection 与 analyzer tests 同步通过。
- 若不需要扩展，`WU-ENG-02-S3-R1` 从 active residual 表移除或标记 closed，并记录关闭依据。

## WU-OBS-01 Prompt-based Tool Trace Diagnostics

### 状态

GitHub Issue #27 与 GitHub Issue #71 高度重复。#27 的核心诉求是按 prompt / final answer 片段反查完整 Tool Trace Run；#71 是更新、更完整的 operator diagnostic entry point，覆盖按 prompt fragment 定位 session / run / iteration、导出 Tool Trace bundle，并生成 Host / Engine / Tool 分层诊断。因此本总控不把 #27 拆成独立 work unit；后续应以 #71 作为主实施入口，#27 只作为 superseded / merged 线索保留。分层诊断能力应复用 WU-OBS-00 / GitHub Issue #70 的 analyzer 或诊断规则，不另建一套平行归因逻辑。若选中的 prompt / final answer 对应 provider / model bug，#71 输出的 diagnostic bundle / report 必须保留 WU-OBS-00 生成的 vendor debugging ids。

### 设计与代码核对

- `docs/host/design.md` 明确 Tool Trace / audit / outbox / memory snapshot 都是 committed EventLog 的派生 projection，不是 Host recovery、resume、Run 状态迁移或 EventLog truth。
- `docs/host/design.md` 要求 RunInputBuilder 的上下文构造与证据纳入观测进入 tool trace / trace 体系；trace / audit 能解释保留、压缩、丢弃、召回失败和预算原因。
- `dayu/host/tool_trace.py` 当前实现 `ToolTraceProjectionConsumer`，从 committed EventLog 投影 hot row 与 cold JSONL line。
- `dayu/host/durable/tool_trace.py` 当前已有按 `run_id`、`tool_call_id`、`provider_request_id`、`diagnostic_ref` 查询 Tool Trace hot rows 的内部 helper。
- `tests/host/test_tool_trace_queries.py` 已覆盖 run / tool call / provider request / diagnostic ref 查询与分页。
- 代码中尚未看到按 prompt fragment 或 final answer fragment 反查 session / run / iteration 的 operator-facing 入口；也未看到把匹配结果、Tool Trace、prompt / response / error context 和 Host / Engine / Tool 分层诊断组装成 debug bundle 的工具。
- `USER_INPUT_ACCEPTED` payload 当前包含 `user_prompt` / `display_text`，`RUN_SUCCEEDED` payload / outbox projection 当前包含 final answer 信息；这些是 prompt / final answer 反查的自然候选数据源，但不能让 outbox、timeline 或 Tool Trace projection 反向成为 Host truth。

### 目标

- 以 #71 为主 issue，实现 operator-facing diagnostic entry point：输入 prompt 或 prompt fragment，定位候选 session / run / iteration。
- 将 #27 的 final answer fragment 反查需求纳入同一入口，而不是另建一套查询工具。
- 明确 zero-match、multi-match、ambiguous-match 的安全行为，避免误导 operator 诊断错误 run。
- 对选中的 match 导出 diagnostic bundle，包含匹配证据、prompt、final response、error / terminal context、Tool Trace events、tool calls 和 final state。
- 在 bundle 上生成 Host / Engine / Tool 分层诊断，诊断必须引用持久化记录或 trace 直接证据；该分层诊断应复用 WU-OBS-00 的 analyzer 能力或规则集。
- 当分层诊断发现 provider / model bug 或 provider protocol anomaly 时，bundle / report 必须展示 provider-native request id、client correlation id（若存在）以及本地 `run_id` / iteration / attempt / tool trace 回链，便于直接交给模型厂商定位。
- 查询与导出只能读取 persisted local data，不要求 live provider，不改变 Tool Trace production semantics。
- 明确 redaction / sensitive-data 输出策略：完整 prompt / response / trace 只能在本地 operator 显式请求下输出。

### 非目标

- 不把诊断报告写成 durable Host truth。
- 不改变 EventLog、Tool Trace、Outbox 或 Memory projection 的生产语义。
- 不在 Host / Engine 中写入财报业务语义或 policy classification。
- 不要求一次性建设大型全文搜索基础设施；可以先使用 SQLite LIKE / FTS / bounded scan / indexed projection 的 plan gate 比较后选择。
- 不把 final answer 反查单独实现成绕过 #71 bundle / layered diagnostics 的平行工具。
- 不重新实现一套与 WU-OBS-00 分离的 Host / Engine / Tool analyzer。
- 不让 UI / Service 依赖内部 durable row 作为用户功能契约；第一阶段定位为本地 operator debug tooling。

### 验收信号

- prompt fragment 与 final answer fragment 都能定位候选 session / run / iteration，并给出匹配证据。
- zero-match / multi-match / ambiguous-match 有明确输出与测试。
- 选中 match 后能导出包含 prompt、response、errors、Tool Trace rows、tool calls、terminal state 的 diagnostic bundle。
- 分层诊断覆盖 provider / model failure、filtering / safety signal when present、tool-call leakage、tool failure、repeated calls、oversized payload、trace incompleteness。
- provider / model failure 报告包含厂商可查 request id 与本地回链信息；缺失时有 explicit limited-signal 说明。
- redaction / explicit local disclosure 行为有测试，不默认泄漏完整敏感 prompt / response。
- README 或 usage docs 说明输入、输出、redaction 预期和典型命令。
- GitHub Issue #27 后续应 comment / close as duplicate 或链接到 #71，避免两条 issue 分别驱动重复实现。

## WU-AUDIT-01 Audit Ledger Viewer And Integrity Report

### 状态

GitHub Issue #72 当前为 OPEN。本条是本地 operator-facing audit ledger viewer，不是 Tool Trace analyzer，也不是 UI / Service 审计产品。它读取当前 Host `LogAuditSink(JSONL)` 输出，帮助 operator 回答“谁在什么时候、以什么身份、对什么对象、基于什么 policy / reason 做了什么治理动作”，并校验 audit JSONL 自身是否可信。Host / Engine / Tool root-cause 诊断由 WU-OBS-00 / #70 与 WU-OBS-01 / #71 承接。

### 设计与代码核对

- `docs/host/design.md` 明确 Audit 是 committed EventLog projection / sink，不是 Host truth；audit projection 不得反向成为恢复、resume 或 memory 真源。
- `docs/host/design.md` 要求 `LogAuditSink` 记录 actor / principal、source / client、request id / client request id、operation context refs / digest、session / run / attempt / execution、policy decision、reason、payload ref / digest。
- `dayu/host/audit.py` 当前普通 audit line 包含 `schema_version`、`event_sequence`、`event_id`、`event_type`、`event_class`、`occurred_at`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`actor`、`principal`、`source`、`client_request_id`、`operation_context_refs`、`operation_context_digest`、`policy_decision_ref`、`policy_decision_summary`、`reason`、`payload_ref`、`payload_digest`、`line_digest`。
- `dayu/host/audit.py` 当前 purge tombstone audit line 包含 `line_kind=purge_tombstone`、`audit_record_ref`、`purge_tombstone_ref`、`deleted_counts`、`deleted_counts_digest`、`precondition_digest`、`deleted_refs_digest`、`request_context`、`source_eventlog_facts_purged=true` 与 `line_digest` 等字段。
- `tests/host/test_audit_sink.py` 已覆盖 audit JSONL 最小字段、line digest、projection replay duplicate marker、purge tombstone audit line 幂等追加；但当前没有 read-only viewer / report 入口。
- WU-RET-02 / #96 将处理 Audit JSONL rotation / retention / compaction / size reporting；本条不实现存储治理，但 viewer 设计不得阻塞未来多 JSONL 文件或 audit directory 输入。

### 目标

- 新增 read-only Audit Ledger viewer，输入显式 audit JSONL 路径；可选支持从 artifact root 派生默认 `audit/host-audit.jsonl`。
- 输出 Markdown 和 / 或 JSON，服务本地 operator 审计 review 与 issue / debug handoff。
- 提供 Summary 视图：总行数、时间范围、event type 分布、actor / source / principal 分布、policy decision 分布、purge 行数量与 integrity 状态。
- 提供 Ledger Table 视图：按 `event_sequence` 排序展示时间、event type、session / run / attempt、actor / principal / source、client request id、operation refs、policy summary、reason、line digest。
- 提供 Detail 视图：按 `event_id`、`line_digest` 或 `purge_tombstone_ref` 展开单行 refs / digests / audit fields；默认不展开敏感 payload 内容。
- 提供 Purge View：展示 destructive-operation audit rows、purge tombstone ref、audit record ref、deleted counts、precondition / deleted refs digest、source event facts purged flag、actor / source / client request id 与 operation context refs。
- 提供 Integrity Report：JSONL parse error、schema version mismatch、line digest mismatch、duplicate `event_id`、duplicate `purge_tombstone_ref`、sequence ordering anomaly、required field omission、直接可观察的 source-key / digest conflict。
- 支持基础过滤：session / run / attempt / execution、event type / class、sequence / time range、actor / principal / source / client request id、operation context refs、line kind。

### 非目标

- 不诊断 Host / Engine / Tool root cause。
- 不分析 prompt failure、model behavior 或 tool behavior。
- 不默认 dump prompt、response、tool trace、large payload 或 payload ref 内容。
- 不修改 `LogAuditSink` 写入语义，不写 EventLog、Host DB、projection checkpoint、audit marker row 或 audit JSONL。
- 不把 viewer 输出变成 Host truth。
- 不新增 Service / UI audit product。
- 不要求 live provider、外部 audit service 或 Host public API 扩展。
- 不在本条实施 WU-RET-02 / #96 的 rotation / retention / compaction。

### 验收信号

- read-only 工具可以读取当前 Host audit JSONL 并生成 audit ledger 报告。
- 支持按审计责任链、operation、受影响 session / run / attempt、event type、line kind、time / sequence range 过滤。
- Markdown / JSON 输出至少覆盖 summary、ledger table、detail、purge view、integrity report 中的核心信息。
- digest、schema version、duplicate、required fields、sequence anomalies 有测试。
- purge tombstone audit line 有专门展示，不会把 audit JSONL alone 误判为 purge completed；完成真源仍需 SQLite tombstone 验证。
- 默认不展开敏感 payload content，redaction / explicit disclosure 行为有测试。
- README 或 usage docs 说明 viewer 用途、非用途、输入、过滤、输出、敏感数据默认值，以及与 WU-RET-02 / #96 的关系。

## WU-AUDIT-02 External Audit Delivery Contract

### 状态

GitHub Issue #75 当前为 OPEN，已 currentize 为 external audit delivery contract + local validation adapters。当前没有真实外部审计系统，因此本条不应直接实现 SIEM / S3 / Kafka / 合规平台集成；第一步应先定义异步投递语义、adapter contract、checkpoint / retry / diagnostic 行为，并用本地 Noop / FileMirror adapter 验证。

### 设计与代码核对

- `docs/host/design.md` 明确 Observer / Sink / Projection 只消费已提交 EventLog，用于派生 read model 或外部投递；外部投递不能成为 Host truth。
- `docs/host/design.md` 明确 `LogAuditSink` 写失败只更新 sink-local error / diagnostic / lag，不回滚 EventLog，不影响 Host command path。
- `dayu/host/audit.py` 当前只有本地 append-only JSONL sink 与 purge tombstone audit record 写入，没有 external delivery worker / adapter contract。
- `dayu/host/durable/audit.py` 只维护 audit sink-local marker，避免 JSONL projection retry 重复写同一个 logical audit event；它不是 external delivery checkpoint。
- WU-AUDIT-01 / #72 提供 read-only audit ledger viewer；WU-RET-02 / #96 处理 Audit JSONL rotation / retention / compaction。本条只处理异步外部投递语义，不处理 viewer 或 storage governance。

### 目标

- 定义 ExternalAuditDeliveryWorker / ExternalAuditDeliveryAdapter 的强类型 contract。
- delivery input 应来自已提交 audit ledger，例如 parsed audit JSONL record 或由 audit JSONL 派生的 typed delivery record。
- 定义幂等键：优先 `line_digest`，存在 `event_id` 或 `audit_record_ref` 时作为额外 semantic key。
- 定义 checkpoint：至少能在 retry / restart 后恢复，不漏投、不产生 semantic duplicate；具体使用 path + line offset / event_sequence / line_digest 等形态留到 plan gate 裁决。
- 定义 delivery result：`delivered`、`duplicate`、`retryable_failed`、`terminal_failed`。
- 实现 NoopAdapter，用于验证 worker flow、filtering、checkpoint、幂等、retry、disabled/default behavior 和 diagnostics。
- 实现 FileMirrorAdapter，把待投递 audit records mirror 到本地 JSONL 文件或目录，模拟外部接收端并验证 crash / retry / duplicate / purge tombstone 行为。
- 保留 purge tombstone audit line 的下游语义：外部系统必须能识别源 EventLog facts 已 purge，并能看到本地 tombstone refs / digests。

### 非目标

- 不在第一步实现真实 SIEM / S3 / Kafka / 合规平台 adapter。
- 不让 external delivery 成功成为 EventLog append、Run terminal、purge completion 或本地 audit JSONL 写入的前置条件。
- 不改变 `LogAuditSink` append-only JSONL 语义。
- 不把外部系统作为 Host governance truth。
- 不要求外部文件 watcher 成为唯一 delivery 机制；Vector / Fluent Bit / Filebeat 等 file tailer 只能作为部署选项，不是 Dayu delivery 语义真源。
- 不在本条实现 WU-RET-02 / #96 的 rotation / retention / compaction。
- 不扩散敏感 payload 内容；delivery 只投递 audit record 当前已包含的字段。

### 验收信号

- 有 typed worker / adapter contract，且不依赖具体外部平台。
- NoopAdapter 与 FileMirrorAdapter 能在无真实外部系统时验证 delivery flow。
- checkpoint resume 能避免漏投和 semantic duplicate delivery。
- delivered / duplicate / retryable_failed / terminal_failed 结果有明确状态机和测试。
- delivery failure 只产生 delivery-local diagnostic / retry state，不阻塞 Host command path，不修改 Host truth。
- purge tombstone audit records 被完整投递到 FileMirrorAdapter，且保留可供下游识别 purge audit meaning 的字段。
- 测试覆盖正常投递、重复投递、retryable failure、terminal failure、checkpoint resume、malformed audit line、purge tombstone delivery。
- README 或 usage docs 说明本地 adapters、delivery contract、当前不接真实外部平台，以及未来 adapter 接入方式。

## WU-RET-01 Tool Trace Cold JSONL Storage Governance

### 状态

GitHub Issue #36 是 GitHub Issue #43 storage lifecycle umbrella 的 child，已 currentize：旧 P7 `ToolTraceJsonlSink._select_jsonl_file()` / `tool_calls_*.jsonl` 分片滚动描述已过期，当前定位改为 Tool Trace cold JSONL 长期存储治理。本条是 retention lane 默认第 1 项，不作为 WU-OBS-00 / #70 的前置；#70 analyzer 可以报告 cold JSONL 过大、重复行或完整性问题，但不负责实施 rotation / retention / compaction。GitHub Issue #79 已被本条吸收：#79 的 cold trace retention / purge 后保留边界由 #36 承接；其中 shared artifact / 跨 Session 引用的删除证明属于 #43 umbrella 下已完成的 WU-RET-00 storage lifecycle safety boundary，以及后续 WU-RET-03 / #78 的 purge cleanup owner。

### 设计与代码核对

- `docs/host/design.md` 明确 Tool Trace 是 committed EventLog 派生 projection，不是 Host recovery、resume、memory 或 Run 状态迁移真源。
- `docs/host/design.md` 允许 cold JSONL 按 run / 日期 / workspace 分片归档，但当前实现尚未落地。
- `dayu/host/tool_trace.py` 的 `ToolTraceSinkOptions` 只有 `cold_jsonl_path`、`create_parent_dirs`、`lock_path`，没有 size threshold、rotation、retention 或 compaction policy。
- `ToolTraceProjectionConsumer._append_line()` 只向 cold JSONL 幂等追加 line；默认路径由 `open_host` 派生为 `artifact_root / "tool-trace" / "tool-trace-cold.jsonl"`。
- 当前缺口不是旧实现的“单个分片超过阈值”，而是 cold JSONL 没有生产级长期存储治理，长期运行可能持续增长。
- `dayu/host/durable/tool_trace.py` hot row 持有 `cold_trace_ref` / `cold_trace_digest`，purge 删除 hot rows 后，cold JSONL 仍可能作为离线诊断 artifact 存在；retention 需要清楚区分 hot query path 与 cold diagnostic artifact。

### 目标

- 设计并实现 Tool Trace cold JSONL rotation policy，例如按大小、日期、run / workspace 或组合策略滚动。
- 设计 retention policy，明确保留窗口、最大本地占用、归档位置、删除条件和与 `purge_session` 的边界。
- 设计 compaction / dedup 行为，覆盖 projection replay / duplicate line 的可治理性；如果 compact 后生成新 artifact，必须保留可验证 digest / source key 关系。
- 增加 size reporting / maintenance diagnostics，让 operator 能看见 cold JSONL 当前占用、分片数量、最大分片、重复行或损坏行统计。
- 明确 cold trace retention 与 shared artifact / 跨 Session 引用的关系：本条不得删除仍被 EventLog、payload descriptor、projection、audit、analyzer 或 WU-RET-00 保留策略需要的 artifact。
- 保持 projection 异步语义：rotation / retention / compaction 不得进入 EventLog append、run admission、cancel、resume、terminal closeout 等 command path。

### 非目标

- 不把 cold JSONL 变成 Host durable truth。
- 不改变 EventLog canonical fact、Tool Trace hot row 或 command path 状态机语义。
- 不实现 operator-facing Tool Trace analyzer；该能力由 WU-OBS-00 / #70 跟踪。
- 不引入跨 EventLog checkpoint 与 JSONL 文件的二阶段提交。

### 验收信号

- 长期运行后 Tool Trace cold JSONL 不再无界增长，或在配置关闭 retention 时有明确 size reporting。
- rotation / retention / compaction 行为有稳定 policy、测试和文档。
- replay / duplicate append 不会导致不可解释的长期存储膨胀。
- purge 后 hot trace 不再作为普通 read path 事实来源；cold trace 缺失、归档或被保留都有明确 diagnostic / retention reason。
- cold JSONL 缺失或被归档只影响深度诊断 / 离线审计，不影响 Host 恢复、resume、memory 或 Run 状态。
- WU-OBS-00 analyzer 若读取已 rotation / archived 的 cold trace，能得到明确的 found / missing / archived / limited signal 结果，而不是静默误判。

## WU-RET-03 purge_session-driven Retention Cleanup

### 状态

GitHub Issue #78 是 GitHub Issue #43 storage lifecycle umbrella 的 child，也是 WU-RET-04 / GitHub Issue #156 的 parent。本条是 retention lane 默认第 2 项，应在 WU-RET-01 / #36 后进入 goal confirmation；它不是重新实现已完成的 `purge_session` command，而是固定 `purge_session` 驱动的 session-scoped retention cleanup owner、cleanup 触发边界、可删除对象集合、删除证明和诊断输出。

### 设计与代码核对

- `docs/host/design.md` 已定义 `purge_session` 是第一版 destructive EventLog retention exception，purge completion truth 仍是 SQLite tombstone，而不是 audit JSONL 或 projection。
- WU-RET-00 已完成 storage lifecycle safety boundary：清理不能破坏 EventLog truth、payload descriptor、projection、audit、trace、analyzer 或共享 artifact 引用。
- WU-CM-15 closeout 已把 compaction artifact retention 转移到 GitHub Issue #156 under #78，说明 #156 必须依赖 #78 的 purge cleanup ownership。
- 当前主控不应让 #156 先于 #78 实施；否则 compaction artifact retention 会缺少 session purge 删除证明、共享引用判断和 Host maintenance 边界。

### 目标

- 固定 `purge_session` 驱动的 retention cleanup owner：哪些 cleanup 属于 purge transaction 内，哪些必须是 purge 后显式 maintenance / report。
- 定义 session-scoped cleanup 对象边界：payload descriptor、SQLite payload、artifact descriptor、compact artifacts、memory projection artifacts、diagnostic payloads、tool trace hot rows、cold refs、audit refs 与其它派生数据。
- 定义 shared artifact / cross-session ref 的删除证明，禁止删除仍被其它 Session、EventLog、projection、audit、trace、analyzer 或 retention policy 需要的对象。
- 定义 cleanup report / diagnostic：已删除、保留、跳过、shared-ref blocked、missing、digest mismatch、manual action required。
- 为 WU-RET-04 / #156 输出明确 handoff：compaction artifacts 哪些受 `purge_session` cleanup 控制，哪些属于 broader artifact retention 或 operator maintenance。

### 非目标

- 不重新实现 `purge_session` command 的核心状态机。
- 不实现 Tool Trace cold JSONL rotation / compaction；该能力由 WU-RET-01 / #36 承接。
- 不实现 Audit JSONL rotation / compaction；该能力由 WU-RET-02 / #96 承接。
- 不提前实现 WU-RET-04 / #156 的 compaction artifact retention policy。
- 不新增 Host background scheduler；是否需要 scheduler 必须先由 #78 的 cleanup owner / trigger 边界证明。

### 验收信号

- `purge_session` cleanup owner、trigger boundary、deletion proof 和 diagnostic 输出有设计与测试覆盖。
- shared artifact / cross-session ref 场景不会被误删，且保留原因可诊断。
- purge tombstone 仍是 destructive purge completion truth；audit / trace / report 只是 projection 或 operator evidence。
- WU-RET-04 / #156 的 entry condition 清晰：只能在 #78 完成后基于其 cleanup boundary 实施 compaction artifact retention。

## WU-RET-04 Compaction Artifact Retention

### 状态

GitHub Issue #156 是 GitHub Issue #78 的 child，归属于 GitHub Issue #43 storage lifecycle umbrella。本条状态为 `pending-prerequisite`：必须等待 WU-RET-03 / #78 完成后才能进入 implementation gate。它处理 Conversation Memory / Context Governance compaction artifacts 的 retention 与 cleanup，不得绕过 #78 自行定义 `purge_session` cleanup owner，也不得新增无设计依据的 Host background scheduler。

### 设计与代码核对

- `docs/host/design.md` 将 Conversation Memory 定义为 EventLog 与 accepted compact projection 的 read model，不是事实真源；Context Governance 负责 compact 编排与事件收口，不直接写 memory truth。
- Compaction artifacts 服务诊断、恢复、review 和 operator closeout；它们不是 EventLog canonical truth，但删除必须尊重 EventLog refs、artifact descriptors、digest、purge tombstone 与 shared refs。
- WU-CM-15 closeout 已明确：compaction artifact retention transferred to GitHub Issue #156 under #78，且 #156 可以依赖 #78 的 purge ownership 定义 artifact retention cleanup，而不是新增 Host background scheduler。

### 目标

- 基于 WU-RET-03 / #78 的 purge cleanup boundary，定义 compaction artifact retention policy。
- 明确 accepted / rejected / failed / fallback compaction artifacts 的保留窗口、删除条件、诊断价值和 purge 后行为。
- 定义 artifact descriptor / digest / source event refs 的保留与删除证明，避免 artifact 文件与 durable refs 漂移。
- 增加 operator-visible report：compaction artifact count、size、age、source run/session、retention reason、deletion eligibility、blocked reason。
- 对 purge-driven cleanup 与非 purge maintenance cleanup 做清晰区分。

### 非目标

- 不绕过 WU-RET-03 / #78 定义 `purge_session` cleanup owner。
- 不改变 compact proposal / validation / repair / fallback 的 Host 状态机。
- 不把 compaction artifact 变成 memory truth 或 EventLog truth。
- 不实现 Tool Trace cold JSONL 或 Audit JSONL retention。
- 不新增周期后台 GC，除非 #78 已明确批准 scheduler / maintenance owner。

### 验收信号

- WU-RET-03 完成后，本条 plan 能直接引用其 purge cleanup owner、deletion proof 和 diagnostic contract。
- Compaction artifact retention 不破坏 recovery、diagnostics、review artifacts、accepted compact refs 或 fallback auditability。
- 删除、保留、shared-ref blocked、missing artifact 和 digest mismatch 场景有测试。
- Operator 能看见 compaction artifact storage usage、eligible cleanup 和保留原因。

## WU-RET-02 Audit JSONL Storage Governance

### 状态

GitHub Issue #96 是 GitHub Issue #43 storage lifecycle umbrella 的 child，跟踪 Audit JSONL 长期存储治理。本条是 retention lane 默认第 4 项。Audit 与 Tool Trace 都有 append-only JSONL 长期累积占用本地存储的问题，但 Audit 承载治理动作和责任链 projection，尤其 purge audit line 需要和 SQLite purge tombstone 形成可解释的 destructive 操作流水，因此必须单独实施。WU-RET-03 / #78 与 WU-RET-04 / #156 不阻塞本条的 JSONL-specific rotation / retention / compaction 设计，但本条必须尊重 purge tombstone / destructive cleanup 真源边界。

### 设计与代码核对

- `docs/host/design.md` 明确 `LogAuditSink` 是 projection / sink，不是 Host truth，按 committed EventLog 消费并写本地 append-only JSONL。
- `docs/host/design.md` 要求 purge 完成真源仍是 SQLite tombstone；audit JSONL 记录 destructive 操作流水，不得用只有 `purge_started` 的 audit line 证明 purge 已完成。
- `dayu/host/audit.py` 的 `LogAuditSinkOptions` 只有 `audit_jsonl_path`、`create_parent_dirs`、`lock_path`，没有 size threshold、rotation、retention 或 compaction policy。
- `default_log_audit_sink_options()` 默认路径为 `artifact_root / "audit" / "host-audit.jsonl"`。
- `_append_audit_line()` 只向 audit JSONL 幂等追加 line；`dayu/host/README.md` 明确第一版 purge 不实现 audit JSONL rotation / compaction。

### 目标

- 设计并实现 Audit JSONL rotation policy，例如按大小、日期、workspace 或组合策略滚动。
- 设计 retention policy，明确本地保留窗口、最大占用、归档位置、删除条件，以及 purge audit line 的最低保留 / tombstone 关联要求。
- 设计 compaction / archival 行为：允许压缩、归档或合并旧 audit JSONL，但必须保留 line digest、source event refs、purge tombstone refs / digest 等可验证关联。
- 增加 size reporting / maintenance diagnostics，让 operator 能看见 audit JSONL 当前占用、分片数量、最大分片、损坏行、digest mismatch、purge_started / purge_completed 不完整链路等统计。
- 保持异步 projection 语义：rotation / retention / compaction 不得拖慢 EventLog append、run admission、cancel、resume、terminal closeout 或 purge command transaction。

### 非目标

- 不实现外部 audit 系统投递保证。
- 不引入复杂 AuditPolicy 规则引擎。
- 不让 audit JSONL 成为 Session / Run / EventLog 恢复真源。
- 不删除或重写 EventLog canonical facts。
- 不把 purge 是否完成的判断从 SQLite tombstone 转移到 audit JSONL。

### 验收信号

- 长期运行后 Audit JSONL 不再无界增长，或在配置关闭 retention 时有明确 size reporting。
- rotation / retention / compaction 行为有稳定 policy、测试和文档。
- purge audit line 在 rotation / retention / compaction 后仍能和 SQLite tombstone 建立可验证关联。
- 只有 `purge_started` 而无 `purge_completed` / tombstone 的链路能被报告为 incomplete attempt，不会误报 purge 已完成。
- Audit sink 失败或 maintenance 失败只影响 audit projection / maintenance diagnostics，不影响 Host command path。

## WU-STRESS-SQLITE-01 SQLite Multiprocess High-spec Stress

### 状态

GitHub Issue #38 当前为 OPEN，且 issue body 已对齐当前定位：代码里已有普通 SQLite 多进程测试与压力覆盖，本条不是重新证明基础语义，而是在 Docker Linux + 外挂慢硬盘 / 高延迟文件系统上放大验证 SQLite WAL、busy timeout、write retry、fsync、文件锁、checkpoint 与 IO jitter 风险。该入口应与普通快速 pytest / 常规 workflow 分离。

### 设计与代码核对

- `docs/host/design.md` 明确 Host durable write transaction 使用短事务、WAL、busy timeout、`BEGIN IMMEDIATE` 与有限 busy / locked retry；`event_sequence` 是 Host durable store 分配的全局 cursor。
- `tests/host/test_event_log_multiprocess.py` 已覆盖多进程 EventLog append 后 `event_sequence` 全局唯一递增，以及同 `event_id` 多进程异体写入压力下的 winner / identity conflict 分类。
- `tests/host/test_admission_multiprocess.py` 已覆盖同 slot ensure、同 Session active Run 唯一性、duplicate follow-up idempotency、queued follow-up FIFO promotion、queued cancel / promotion first-committer-wins，以及 admission 后 EventLog sequence 全局唯一递增。
- `tests/host/test_recovery_multiprocess.py` 已覆盖 live owner 不被误恢复、owner crash 后 reopen recovery 并通过 public stream 产出 final answer、projection lag 不阻塞 durable recovery。
- `tests/runtime/test_lane_multiprocess.py` 已覆盖 runtime lane 跨进程 capacity invariant、non-blocking timeout、release 后其它进程可 acquire、crashed holder 经 TTL cleanup 后可 acquire。
- 因此，普通 deterministic SQLite multiprocessing tests 已足够作为日常语义回归；#38 的缺口是更高规格、更长耗时、更依赖环境的部署压力验证。

### 目标

- 定义并落地 Docker Linux + 外挂慢硬盘 / 高延迟文件系统上的 SQLite multiprocess stress 高规格入口。
- 复用或对齐现有普通 SQLite 多进程测试覆盖面：跨进程 append、同 `event_id` 竞争、admission 幂等 / active Run 唯一性、terminal race、lease expiry / renew、stale recovery、observer drain / startup reconcile、runtime lane capacity。
- 放大 WAL / busy_timeout / write retry / checkpoint / fsync / 文件锁在慢 IO 下的行为边界。
- 输出结构化摘要：进程数、运行轮数、busy_timeout、retry 配置、数据库路径、文件系统类型或挂载说明、storage latency、busy / locked 次数、fenced count、winner terminal、recovery attempts、observer lag。
- 明确失败诊断：锁超时、retry exhaustion、重复 sequence / position、event identity conflict 分类错误、terminal race 多 winner、late owner 未被 fence、observer checkpoint 不前进、WAL / checkpoint 异常增长或失败。

### 测试入口约束

- 高规格压力测试必须与常规 unit / integration / public smoke 分开。
- 必须有独立入口，例如 pytest stress marker、独立脚本或手动 workflow；具体形式在实施 gate 中裁决。
- 默认快速 pytest 和普通 GitHub workflow 可以排除该入口。
- 入口必须支持可配置参数：进程数、轮数、DB 目录、busy_timeout、总 timeout、输出摘要路径。
- 环境不满足时必须 preflight fail-fast，并说明缺少 Docker Linux、挂载目录或写入权限等具体原因；不得用 skip 掩盖真实 race。

### 非目标

- 不放进默认快速 pytest。
- 不要求普通 GitHub workflow 默认执行。
- 不依赖真实 provider / 外部服务。
- 不打印 owner token、scope token、大 prompt 或大 tool result。
- 不用 sleep 堆出偶然通过；需要明确 gate、barrier、timeout 与可诊断失败。
- 不替代 Host crash / watch / liveness 组合压力测试；本条只负责 SQLite 多进程压力链路的高规格环境版。
- 不把高规格 stress 的环境敏感失败反向解释为语义契约变化；语义契约仍以 deterministic tests 和设计真源为准。

### 验收信号

- 有文档说明如何在 Docker Linux 中把数据库目录挂到外挂慢硬盘 / 高延迟文件系统并运行 stress。
- 高规格 stress 能在指定轮数内稳定输出 pass/fail 摘要。
- 失败时能定位到 append lock、busy retry、WAL / checkpoint、terminal race、lease renew、fencing、recovery 或 observer drain 类别。
- 默认测试入口与 stress 入口清晰分离；普通快速测试不因该 stress 增加显著耗时。
- 与现有普通 SQLite 多进程测试的关系清楚：普通测试证明语义，高规格 slow-disk / Docker run 放大 IO / locking 风险。

## WU-GOV-01 Host Policy Refusal Terminal Taxonomy

### 状态

GitHub Issue #88 当前为 OPEN。已裁决长期需要引入 `RunStatus.REJECTED`，但它的动机不是 compact failure，而是生产级 Host policy refusal：权限、租户、额度、配额、速率限制、工具权限 / 审批策略、admission validation、workflow / scene / tool set policy 等在执行前或执行外明确拒绝整个 Run 的场景。

本条是后续 policy / permission / tenancy / quota / rate-limit / tool approval feature 的状态机前向约束：这些 feature 在 plan / implementation 时必须先判断拒绝是否属于 `REJECTED`，避免先落成含糊的 `FAILED` 后再迁移。

用户在 2026-07-20 裁决本 WU 不单独推进，等具体工具权限 / 审批能力进入排期时再一并进入 goal confirmation。当前状态为 `deferred`；不得在没有真实 tool-permission consumer、拒绝入口与用户动作语义时，仅为预留 taxonomy 提前修改 Run 状态机。

### 目标

- 引入 `RunStatus.REJECTED`，用于表达 Host policy gate 明确拒绝接受 / 继续整个 Run，且该拒绝不是执行、compact、recovery、外部 job 或 worker lifecycle 尝试失败的结果。
- 裁决 rejected Run 的 canonical EventLog taxonomy；优先设计独立 `RUN_REJECTED` terminal fact。若复用 `RUN_FAILED`，必须证明 public terminal status、projection、outbox 和 retry / replay 不会混淆。
- 明确应归入 `REJECTED` 的场景：admission 阶段用户输入不合法且不能自动修复；权限、租户、额度、配额、速率限制拒绝；工具权限 / 审批策略拒绝整个 Run；context hard limit 下当前输入本身不可执行且 fallback 也无法构造合法输入；policy 明确禁止某个 workflow / scene / tool set；请求与 session state 冲突且 Host 明确不应启动执行。
- 明确不应归入 `REJECTED` 的场景：Engine 已经创建 Attempt 后 runner / provider / tool 失败；reactive compact failure 后 recovery 失败；外部 job 执行失败；worker crash、orphan、lost proof；用户取消；compact proposal 被 reject 但 fallback 可以继续 dispatch；compact / fallback 尝试最终 fail closed，除非另有独立 policy gate 在 compact 前已经拒绝该目标。
- 同步 Run status、EventLog terminal taxonomy、projection、public contract、retry / replay 前置条件、outbox / HostEvent 映射、文档与测试。

### 非目标

- 不为单个 failure reason 临时增加状态。
- 不让 Attempt terminal taxonomy 承担 Run-level governance 语义。
- 不把 `REJECTED` 做成更细的 `FAILED`，也不把 compact failure、runner failure、tool failure、external job failure、recovery failure 或 worker crash 纳入 `REJECTED`。
- 不把普通 diagnostic rejected event，例如 late wait result rejected 或 EngineEvent rejected，等同于 Run terminal rejected。

### 验收信号

- Public `RunStatus` 包含 `REJECTED`，并在终态集合、public contract freeze tests、read API、HostEvent、outbox、retry / replay 和 projection 中一致处理。
- Durable transition helper 支持 attempt-free rejected Run；已有 Attempt 的执行失败路径仍使用 `FAILED`。
- 权限 / 租户 / quota / rate limit / tool approval policy 至少一个代表性 gate 能产生 `REJECTED`，并有端到端测试。
- compact failure、fallback fail-closed 和 reactive recovery failure 默认不迁移到 `REJECTED`；如未来要例外处理，必须先证明它是独立 policy refusal，而不是治理执行失败。
- 文档同步说明 `FAILED` 与 `REJECTED` 的边界、用户动作差异、retry / replay 语义，以及本 WU 对后续 feature 的前向约束。

## WU-CTX-04 Per-Session Attachment Ownership and Proactive Governance Single-operation Boundary

### 状态

GitHub Issue #112 当前为 OPEN；本条状态为 `draft-pr-open / final-closeout-pass`。PR #181 已于 2026-07-22 明确 `MERGED`，merge commit 为 `974f9e16`；本地 `main` 已从 `github/main` fast-forward 到该提交，工作树干净，并已从该基线创建 `feat/wu-ctx-04`。设计裁决已经写入 `docs/host/design.md` 的“Session attachment access ownership”与 attachment-aware “Host Lifecycle / Recovery”；本轮 goal confirmation 以该设计为真源，不得重新退回 workspace-wide read-only、自动 promotion、lease/fence 或 proxy 方案。2026-07-22 用户已确认本节既定目标、非目标、scope boundary 与验收信号。accepted plan保护提交为`1f032b5e`；Slice 1 contract-only实现及review loop已通过，受保护本地commit为`eda1d70e`。Slice 2联合implementation、initial review、review fix与双路re-review均已闭环，Controller最终acceptance decision=`pass`；zero-request orphan/unknown proactive history现由projection owner严格fail closed，recovery nested work-lease contract与Host close mandatory/best-effort文档已同步。Slice 3 implementation、initial双路review、Controller adjudication、review fix与双路re-review均已完成；3项accepted findings全部fixed，两路均为`pass`且0个新actionable findings，Controller最终acceptance decision=`pass`，accepted Slice 3保护提交为`24dfcf37`。三个implementation slices均已保护。AgentMiMo与AgentDS相对main baseline执行aggregate deepreview后均判定PASS；Controller逐项裁决9个reviewer finding编号，接受0项、驳回9项，没有deferred/needs-more-evidence/blocking question。branch-wide diff、full pyright与publish preflight通过，feature branch已推送；draft PR #182为OPEN/draft，base=`main`、head=`feat/wu-ctx-04`。final closeout=`pass`，等待用户review/merge。

### Gate artifacts

- goal confirmation：2026-07-22 用户确认；decision=`pass`；blocking open questions=None。
- plan：`docs/reviews/wu-ctx-04-plan-codex.md`；AgentCodex initial completion=`complete`；原4 slices经review fix后收敛为3 slices，其中attachment/target recovery与proactive crash resume因不存在稳定可发布checkpoint而合并为同一Slice 2原子闭环；artifact completeness、独立whitespace check与`git diff --check`通过；尚不等于accepted plan。
- plan review：`docs/reviews/plan-review-20260722-110302.md`（AgentMiMo）与 `docs/reviews/plan-review-20260722-110343.md`（AgentDS），均为 `pass-with-risks`；总控裁决 artifact=`docs/reviews/wu-ctx-04-plan-review-controller-adjudication.md`，decision=`needs-fix`，accepted=8、rejected=3、deferred=1、needs-more-evidence=0。
- plan fix：`docs/reviews/wu-ctx-04-plan-fix-codex.md`；AgentCodex completion=`complete`；7组accepted fix requirements均已逐项映射，MIMO-003保持deferred到implementation review，MIMO-005 / DS-F01 / DS-F07未扩scope；总控复读decision=`accepted-for-plan-re-review`，blocking open questions=None。
- plan re-review：`docs/reviews/plan-review-20260722-113813.md`（AgentMiMo）与`docs/reviews/plan-review-20260722-113814.md`（AgentDS），均为`pass-with-risks`且确认原7组accepted findings已修复。总控裁决artifact=`docs/reviews/wu-ctx-04-plan-re-review-controller-adjudication.md`，decision=`needs-fix`：新接受`PRR-001` Host close在scheduler lifecycle quiesce前释放mutex的恢复竞态，以及`PRR-002` reactive `engine_ingest.py`生产调用点/测试遗漏；另有2项驳回、1项证据失效、0个blocking questions。
- second plan fix：`docs/reviews/wu-ctx-04-plan-re-review-fix-codex.md`；AgentCodex completion=`complete`；`PRR-001`与`PRR-002`已分别映射到scheduler-before-unlock lifecycle barrier、cleanup fail-closed/retry contract、reactive producer/caller allowed scope与focused tests；原7组closure、3 slices及deferred/rejected裁决保持不变；总控复读decision=`accepted-for-second-plan-re-review`。
- second plan re-review：`docs/reviews/plan-review-20260722-120429.md`（AgentMiMo，`pass-with-risks`）与`docs/reviews/plan-review-20260722-120430.md`（AgentDS，`pass`）；均判定`PRR-001`/`PRR-002`已修复、原7组closure与3-slice边界无回归。最终总控artifact=`docs/reviews/wu-ctx-04-plan-acceptance-controller.md`，decision=`pass`；MiMo新增Host级测试命名观察被驳回，`pending.policy=None`观察被直接类型/路径证据判为evidence-invalid。
- accepted plan commit：`1f032b5e`（`gateflow: accept plan for WU-CTX-04`）。
- Slice 1 implementation：`docs/reviews/wu-ctx-04-slice-1-implementation-codex.md`；
  contract-only strict-native mutex、internal attachment registry与限定API value types完成；
  focused pytest初次`43 passed`、runtime suite初次`594 passed`、全量pyright`0 errors`、
  owner module coverage分别`91%`/`86%`。
- Slice 1 code review：`docs/reviews/code-review-20260722-124340.md`（AgentMiMo）与
  `docs/reviews/code-review-20260722-124418.md`（AgentDS）；总控裁决artifact=
  `docs/reviews/wu-ctx-04-slice-1-code-review-controller-adjudication.md`，decision=`needs-fix`；
  仅接受`CR-DS-001`为低风险双失败诊断链缺口，驳回4项findings并关闭recovery多lease open question。
- Slice 1 fix：`docs/reviews/wu-ctx-04-slice-1-review-fix-codex.md`；外层typed unavailable
  contract不变，以`ExceptionGroup` cause结构化保留prior native error与partial close error；
  focused pytest增至`44 passed`、owner module coverage=`92%`/`86%`、targeted pyright=`0 errors`。
- Slice 1 re-review：`docs/reviews/code-review-20260722-125826.md`（AgentMiMo）与
  `docs/reviews/code-review-20260722-125901.md`（AgentDS）均判定`CR-DS-001 fixed`、无new
  findings/blocking/open questions；最终总控artifact=
  `docs/reviews/wu-ctx-04-slice-1-acceptance-controller.md`，decision=`pass`。Controller
  post-fix runtime suite=`595 passed`、全量pyright=`0 errors`。
- accepted Slice 1 commit：`eda1d70e`（`gateflow: accept WU-CTX-04 slice 1`）。
- Slice 2 initial implementation audit：`docs/reviews/wu-ctx-04-slice-2-implementation-codex.md`
  初始状态=`blocked`，production/test code未开始；B-001/B-002均为accepted plan漏列直接测试消费者。
  Controller scope amendment=`docs/reviews/wu-ctx-04-slice-2-scope-amendment-controller.md`，
  decision=`resume-with-narrow-test-only-amendment`；仅追加`test_public_host_admin.py`、
  `test_active_cancel_dispatch.py`与同rename链的`test_terminal_post_commit.py`机械迁移，blocking
  open questions=None。
- Slice 2 implementation完成后双路code review：
  `docs/reviews/code-review-20260722-161504-mimo.md`（AgentMiMo）与
  `docs/reviews/code-review-20260723-000000-ds.md`（AgentDS）；Controller独立复核artifact=
  `docs/reviews/wu-ctx-04-slice-2-code-review-controller-adjudication.md`，decision=`needs-fix`。
  blocking finding=`CTRL-S2-001`：无proactive request时orphan/unknown compaction rows在strict
  校验前被投影为`ABSENT`，可错误创建request/provider side effect；另接受recovery nested
  work-lease contract/test与Host close mandatory/best-effort docstring澄清，blocking questions=None。
- Slice 2 review fix：`docs/reviews/wu-ctx-04-slice-2-review-fix-codex.md`；
  `CTRL-S2-001`、`F-DS-01`与Controller接受的close docstring correction均完成；focused
  pytest=`153 passed`，Host suite=`2133 passed, 1 skipped, 6 deselected`，全量pyright=`0 errors`，
  targeted ruff与`git diff --check`通过；completion=`pass-for-re-review`，未提交。
- Slice 2 code re-review：`docs/reviews/wu-ctx-04-slice-2-re-review-mimo.md`（AgentMiMo）与
  `docs/reviews/wu-ctx-04-slice-2-re-review-ds.md`（AgentDS）均判定accepted findings fixed并建议
  pass；Controller最终artifact=`docs/reviews/wu-ctx-04-slice-2-acceptance-controller.md`，
  decision=`pass`。DS新增identity observation被直接控制流反证为evidence-invalid，其余新增
  observations均未形成actionable gap；blocking questions=None。
- accepted Slice 2 commit：`4ca0810b`（`gateflow: accept WU-CTX-04 slice 2`）。
- Slice 3 pre-edit audit：`docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`初始
  status=`blocked`；Controller直接核对确认严格`session_id`/target wake契约遗漏两个测试消费者。
  scope amendment=`docs/reviews/wu-ctx-04-slice-3-scope-amendment-controller.md`，decision=
  `resume-with-narrow-test-only-amendment`；仅追加`test_dispatch_scheduler.py`与
  `test_admission_multiprocess.py`做required signature/obsolete global-watchdog机械迁移。
- Slice 3 implementation：同一artifact=`docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`
  最终status=`complete`，并保留初始blocker与scope amendment历史。execution owner按本地exact
  identity快照读取strict durable cancel link并传播token/hook；target watchdog不再做workspace-wide
  scan，terminal closeout复用唯一producer。计划8.4=`325 passed`，amendment tests=`110 passed`，
  最终全量=`5590 passed, 11 skipped, 6 deselected`，全量pyright=`0 errors`；21个变更production
  Python文件逐文件coverage均>=80%，最低81%。
- Slice 3 initial code review：`docs/reviews/wu-ctx-04-slice-3-code-review-mimo.md`
  （AgentMiMo，`pass`，0 findings）与
  `docs/reviews/wu-ctx-04-slice-3-code-review-ds.md`（AgentDS，`pass`，1 Medium + 3 Low）。
  Controller adjudication=`docs/reviews/wu-ctx-04-slice-3-code-review-controller-adjudication.md`，
  decision=`needs-fix`：接受独立execution-owner poll被proactive compactor阻塞、canonical cancel
  reason被dispatch常量替代、dynamic VALUES bind可移植性3项；驳回workspace-wide safety scan、
  LRU/size guard与无失败条件的monkeypatch观察。blocking questions=None。
- Slice 3 review fix：`docs/reviews/wu-ctx-04-slice-3-review-fix-codex.md`；
  `CTRL-S3-001`以独立health-supervised execution-owner cancel periodic task解除Session
  reconcile/proactive compactor阻塞并覆盖open/failed-open/close；`CTRL-S3-002`由run-transition
  typed delivery投影canonical cancel reason，dispatch不再生成替代常量；`CTRL-S3-003`在同一
  transaction内按SQLite历史默认999 bind预算推导199条安全批次，先做完整输入校验并严格保持
  全局输入顺序。focused matrix=`438 passed`，terminal producer manifest=`1 passed`，canonical
  全量=`5593 passed, 11 skipped, 6 deselected`，全量pyright=`0 errors`；coverage测试面
  `3542 passed, 9 skipped, 6 deselected`，21个变更production Python文件逐文件均>=80%。
  Controller独立复跑4个根因反例=`4 passed`，fix相关production/tests pyright=`0 errors`；
  blocking questions=None，下一步为双路re-review。
- Slice 3 code re-review：`docs/reviews/wu-ctx-04-slice-3-re-review-mimo.md`（AgentMiMo）与
  `docs/reviews/wu-ctx-04-slice-3-re-review-ds.md`（AgentDS）均判定`CTRL-S3-001/002/003`
  已root-cause closure，verdict=`pass`，0个new actionable findings，blocking questions=None。
  AgentMiMo独立full Host=`2150 passed, 2 skipped, 6 deselected`；AgentDS独立canonical
  full suite=`5593 passed, 11 skipped, 6 deselected`，两路pyright均`0 errors`。
- Slice 3最终Controller acceptance：
  `docs/reviews/wu-ctx-04-slice-3-acceptance-controller.md`，decision=`pass`；Controller按
  production owner、根因反例、唯一terminal producer、typed canonical reason与batch order
  证据独立裁决，不按review票数接受。所有residual risk均已分类，blocking questions=None；
  允许创建accepted Slice 3保护提交并进入aggregate deepreview。
- accepted Slice 3 commit：`24dfcf37`（`gateflow: accept WU-CTX-04 slice 3`）。
- aggregate deepreview：`docs/reviews/wu-ctx-04-aggregate-deepreview-mimo.md`（AgentMiMo，
  `PASS`）与`docs/reviews/wu-ctx-04-aggregate-deepreview-ds.md`（AgentDS，`pass`）；两路均
  确认跨3个slices的attachment ownership、native mutex、proactive recovery、close barrier、
  target-only cancel/watchdog、canonical reason、terminal producer、SQLite batching、public/
  LLM-facing/README一致性无blocking regression。
- aggregate deepreview Controller adjudication：
  `docs/reviews/wu-ctx-04-aggregate-deepreview-controller-adjudication.md`，decision=`pass`；
  9个reviewer finding编号去重为7个语义观察后全部驳回。主要原因包括：与Slice 1已接受的
  mutex release fail-closed contract冲突、无当前lease泄漏producer、typed/private调用图不可达、
  already-done Future正确完成语义或纯未来假设。接受=0、deferred=0、needs-more-evidence=0、
  blocking questions=None。
- aggregate deepreview commit：`e7da8ed5`（`gateflow: pass WU-CTX-04 aggregate deepreview`）。
- publish preflight：`github/main == main == 974f9e16`，full pyright=`0 errors`，整分支
  `git diff --check`通过，工作树干净且不存在同head既有PR。review artifact纯机械whitespace
  cleanup commit=`e421e4b0`。
- draft PR：`https://github.com/noho/dayu-agent-r/pull/182`；state=`OPEN`、draft=`true`、
  base=`main`、head=`feat/wu-ctx-04`。未ready、merge、请求reviewer、评论或修改Issue #112。
- final closeout：`docs/reviews/wu-ctx-04-final-closeout-controller.md`；decision=
  `final-closeout-pass`，所有residual risk已分类，blocking questions=None。

### 已确认问题与直接代码证据

首先必须区分 watcher、Session attachment 与 execution opener：

- 多个 UI 连接同一个 `Host` 并 watch 同一 Session，只会创建多个 Session Event Delivery subscription；它们共用同一个 `HostDispatchScheduler`，watch 不会授予写权限，也不会启动 pre-start governance 或 proactive compact。这不是本 WU 的竞态来源。
- 多个 UI / Service 分别调用 `open_host(...)` 且使用同一 workspace 时，每个 opener 当前都会创建自己的 `HostDispatchScheduler`，并由 Service assembly 将同一 workspace 解析到同一 Host SQLite。当前代码还没有 per-Session attachment access mode 或 execution ownership boundary。
- 业务要求允许多个 opener 同时使用同一 workspace，并允许它们分别在不同 Session 上提交；因此 workspace-wide single writer 或把第二个 Host 整体设为 read-only 都不成立。

当前已经确认的 public 触发路径有两条：

1. **startup recovery overlap**：scheduler A 对某个 `ACCEPTED` Run 提交 proactive `CONTEXT_COMPACTION_REQUESTED` 后，在事务外等待 LLM compactor；此时 Run status 与 input cursor 保持不变。第二个 `open_host` 若在该窗口启动，其 `StartupRecoveryScanner` 会把同一 `ACCEPTED` Run 分类为 `ACCEPTED_WAKE`，并通过当前 opener 的 wakeup port 唤醒 queue promotion，使 scheduler B 对同一 Session / Run 再次进入 `_run_pre_start_governance(...)`。
2. **accepted admission replay**：另一个 opener 对同一幂等 admission 做 replay，若 durable 返回的同一 Run 仍为 `ACCEPTED`，`_wake_start_governance_if_needed(...)` 会再次唤醒该 opener 的 queue promotion；它也可能与 scheduler A 的事务外 compact 重叠。

竞态成立及配置漂移的直接代码条件如下：

- design truth明确第一版每个Run最多一个proactive operation，Host fallback常量也是`1`；但packaged `execution_profiles.json`的四个profile自引入起一直把`max_proactive_compactions_per_run`配置为`2`，没有对应的第二operation业务路径。该字段不是`max_compaction_attempts_per_operation`的别名，前者错误地暴露了operation数量，后者才拥有单operation内proposal / semantic repair总尝试预算；Runner `max_retries`另行拥有每次proposal call内部的transport retry。
- 正常scheduler路径在proactive compact accepted后直接创建Attempt / dispatch，不重新估算并启动同一Run的第二个proactive operation；现有“second proactive compact”测试覆盖的是同一Session的第二个Run，而不是同一Run第二次operation。因此packaged值`2`是config/public policy漂移，不是需求证据。
- proactive path在短transaction中统计已提交request数并追加`CONTEXT_COMPACTION_REQUESTED`，随后释放transaction等待外部compactor。scheduler A与B可先后看到count 0和1；由于packaged上限为2，二者分别追加独立request并调用provider。两次结果写回只校验Run status、input cursor与Session是否仍允许compact，没有唯一operation门禁，因此都可能追加有效`CONTEXT_COMPACTED`。
- 单纯把字段改为1仍不是root fix：loser看到既有request后会进入`proactive_compact_limit_reached`并错误把Run收口为`FAILED`。单纯删除字段但保留现有prepare逻辑也不正确，因为每次重复wake或crash recovery都会追加新的request，失去任何有界性。
- 同一`HostDispatchScheduler`的production promotion入口由单一`_promotion_drain_task`串行await queue item；公开Host command只wake该队列，不并发直调`run_queue_promotion(...)`。因此在per-Session attachment mutex确保同一Session只有一个eligible scheduler后，正常同opener wake不再需要额外compaction fence或operation mutex；重复wake在首轮完成后只做状态reconciliation。
- graceful attachment close必须drain事务外proactive operation后才释放mutex；process crash则可能留下`CONTEXT_COMPACTION_REQUESTED`而没有同operation的`CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED`。fresh`READ_WRITE` owner必须恢复或确定性收口同一个operation，并把durable proposal manifests / rejected attempts计入`max_compaction_attempts_per_operation`；不得把crash recovery伪装成第二个proactive operation。
- reactive path在request transaction内同时关闭当前Attempt并把Run推进`RECOVERING`，且真实recovery dispatch仍可能再次收到provider overflow，因此`max_reactive_compactions_per_run`有独立设计需求并保留。当前直接反例集中在proactive path，不应无证据重写reactive pipeline。

因此，准确问题定义是：**在多个execution-capable `open_host`共享SQLite的现有拓扑下，startup recovery或accepted admission replay可以让两个scheduler在同一Session的同一Run / input snapshot上并发创建本应唯一的proactive operation；根因是scheduler的Session级执行资格没有唯一owner，且proactive single-operation不变量被错误建模成可配置count。**删除该字段会收窄并澄清WU，但不会替代per-Session attachment ownership或incomplete-operation recovery。

### 用户已裁决的设计方向

语义 owner 是 Host 的 `HostSessionAttachment` registry；strict-native per-Session mutex 只提供跨 opener 的机械互斥，不承载 Run / Attempt durable truth。目标 public contract 为 `await host.attach_session(session_id) -> HostSessionAttachment`，attachment 至少暴露 `session_id`、不可变 `access_mode: READ_WRITE | READ_ONLY` 与 `aclose()`。

- 每个 `open_host` 保留正常 scheduler；读写能力按 Session attachment 独立决定，而不是按 workspace 或整个 Host 决定。同一 opener 可以对 Session 1 为 `READ_WRITE`、对 Session 2 为 `READ_ONLY`，另一个 opener可以相反。
- fresh attach 以 non-blocking strict-native per-Session mutex acquire 决定不可变 mode：成功为 `READ_WRITE`，mutex busy 为 `READ_ONLY`。strict-native lock 不可用时 fail closed；不得退化为 soft lock。
- `READ_ONLY` attachment 只能做 durable read、Outbox read与 Session event observation；不得 submit、cancel、retry/replay、start governance、proactive compaction、queue promotion、recovery 或新 dispatch，也不接收其它 opener 的 transient delta。
- 既有 `READ_ONLY` attachment 在 owner release 后不自动升级，不做 leader election、通知或 live handoff。用户必须关闭并重新 attach，fresh attachment 才能重新竞争 `READ_WRITE`。
- `READ_WRITE` attachment close 必须先 gate 该 Session 的新命令，并 drain 已进入但尚无稳定 Run / Attempt owner 的 command / pre-start governance，包括 transaction 外 proactive compaction，然后释放 mutex。已经 durable-owned 的 active Run / Attempt 可继续由旧 scheduler治理，但旧 scheduler释放后不得再为该 Session 启动无 owner 的新 Run或推进下一个 Run。
- fresh `READ_WRITE` attach 只对目标 Session 做 bounded attachment-aware recovery，再 successful return；`READ_ONLY` attach 和单纯 `open_host` startup 都不做 workspace-wide recovery。mutex availability 不能替代 positive orphan proof，不能授权接管旧 Attempt。
- watcher / subscription 与 attachment mode 正交；watch 从不授予写权限。跨 opener transient delta 不持久化、不重放、不转发，observer 通过 bounded durable reconciliation / Outbox 看到 durable progress与 terminal。
- mutex 不代表 Run / Attempt owner，不替代 SQLite transaction / CAS、`owner_host_instance_id`、Attempt / execution identity 或 positive orphan proof。cancel完全服从统一attachment access rule：任意live `READ_WRITE` attachment可取消该Session中任意满足既有状态前置的Run，不按originating / admitting opener或execution owner过滤；`READ_ONLY`在durable write前拒绝。durable commit后由当前Attempt execution owner scheduler有界reconcile并作用于自己的worker，caller本地registry直达只作低延迟fast path；这不是独立的跨opener业务语义。
- 本方案不引入 Session generation / epoch fence、lease、TTL / heartbeat takeover、自动 promotion、跨进程 command/event proxy 或 workspace-wide leader。只要所有 scheduler entry point 都严格受 live `READ_WRITE` attachment资格约束，就不需要再为 WU-CTX-04 增加 compaction fence。
- 删除`max_proactive_compactions_per_run`的config、typed config、Host public policy、assembly、fallback constant、count-limit failure branch、tests与文档。每Run/input snapshot最多一个proactive operation改为不可配置的Host状态机不变量；既有request表示该operation已经存在，不得触发第二个operation或`proactive_compact_limit_reached`失败。`max_compaction_attempts_per_operation`继续表达同operation内的proposal / semantic repair总预算，Runner`max_retries`继续表达transport retry；`max_reactive_compactions_per_run`保持独立且不受本次删除影响。

用户体感必须固定为：UI A fresh attach Session 1 获得 `READ_WRITE`，UI B attach 同一 Session 1 获得 `READ_ONLY`；UI A通过该attachment提交Run X后detach Session 1并转到Session 2，UI B的既有attachment仍为`READ_ONLY`；UI B关闭并fresh reattach Session 1后，在mutex已释放时获得`READ_WRITE`，随后可按普通cancel contract取消Run X，不区分Run X由A提交或其active worker仍由A持有。与此同时，UI B对其它没有owner的Session可以独立获得`READ_WRITE`并正常submit。

### 目标

- 建立显式、可关闭、mode 不可变的 public Session attachment contract，并让所有用户 mutation 与 scheduler entry point 使用同一个 Host-owned access truth。
- 提供 strict-native per-Session mutex 与进程内 attachment registry；确保 partial allocation failure、factory cancellation、Host close 与 attachment close 都不泄漏 mutex 或 eligibility。
- 将 startup recovery 改成 fresh `READ_WRITE` attach 后的 target-Session bounded recovery，消除 unrelated opener 对同一 Session 的 accepted wake / governance overlap。
- 通过 attachment eligibility 从根因上消除双 scheduler proactive compact，而不向 EventLog、compact artifact 或 reactive pipeline引入无关 ownership 语义。
- 删除无业务owner的`max_proactive_compactions_per_run`配置面，把同一Run/input snapshot唯一proactive operation及incomplete-operation recovery固定为Host状态机contract；crash后复用原operation id和剩余semantic attempt预算，不追加第二条request。
- 让cancel授权只复用统一`READ_WRITE` truth，并让每个execution scheduler有界reconcile自己owned active Attempt的durable cancel；不得以originating opener分支或caller本地registry命中作为correctness条件。
- 更新 runtime assembly、Service / UI 调用点、typed errors、tests与 README，使 public 命令、取消、观察和生命周期边界一致。

### 非目标

- 不建立 workspace-wide single writer，也不把第二个 `open_host` 整体设为 read-only。
- 不让既有 `READ_ONLY` attachment 自动升级，不实现 live handoff、leader election、通知或 proxy。
- 不引入 Session generation / epoch fence、lease、TTL / heartbeat takeover或 EventLog lock 语义。
- 不持久化、重放或跨进程转发 transient delta；不实现跨进程 command/event proxy。
- 不把 compact artifact 改成 `run_id` 唯一覆盖文件；compact artifact 仍是内容寻址、不可变、可审计材料。
- 不在 dispatch 或 engine_ingest 单侧增加只能覆盖单进程的 in-memory lock。
- 不用新的proactive operation count、retry count、lease或fence字段替代被删除的`max_proactive_compactions_per_run`；不把crash recovery建模为第二个operation。
- 不在缺少直接反例时改写 reactive compaction pipeline。

### 验收信号

- 两个真实 public `open_host` 使用同一 workspace SQLite 与同一 Session：A 获得 `READ_WRITE`，B 获得 `READ_ONLY`；B 的 submit / cancel / retry / replay 在任何 durable write、provider call 或 scheduler wake 前收到 typed read-only rejection，B 仍可观察 durable progress / terminal，但不收到 A 的 transient delta。
- A detach Session 1 后，B 的既有 attachment 不升级；B close / fresh reattach 后获得 `READ_WRITE`。A 与 B 分别 attach 不同 Session 时可同时获得 `READ_WRITE` 并并行提交，证明不是 workspace-wide lock。
- A detach 时若仍有 transaction 外 proactive compaction或其它无稳定 Run / Attempt owner 的 pre-start work，mutex 必须在它们取消 / drain 后才释放；fresh owner 不启动第二个 provider call、不产生重复 `CONTEXT_COMPACTED`、不错误消耗 policy budget或把 Run 收口为 `FAILED`。
- A detach 时若存在已 durable-owned active Run / Attempt，旧 execution owner 可继续治理它；B fresh attach 后的新输入按 durable admission 进入 `QUEUED`，B 不接管旧 Attempt，A terminal 后旧 scheduler不得 promotion 下一个 Run，future work由当前 `READ_WRITE` attachment scheduler 推进。
- startup recovery overlap 与 accepted admission replay 的既有 public reproduction 都必须变成确定性反例：`READ_ONLY` opener 无法进入 recovery / accepted wake / pre-start governance / proactive compact；只构造内部 scheduler 不能替代 public-path 回归。
- packaged与workspace config schema拒绝`max_proactive_compactions_per_run`旧字段；runtime typed config、Host `ContextBudgetPolicy`、assembly、fallback constant、count helper、`proactive_compact_limit_reached`错误分支和相关旧测试全部删除，stale-field grep为零。`max_compaction_attempts_per_operation`与`max_reactive_compactions_per_run`行为不回归。
- 对同一Run/input snapshot，正常wake、重复accepted admission wake与恢复reconciliation最多只有一条proactive`CONTEXT_COMPACTION_REQUESTED`。已有incomplete request时不得创建第二个operation、不得因为“budget reached”失败Run；graceful detach先drain原operation，process crash后的fresh`READ_WRITE` attach按原operation id恢复剩余proposal attempts，或在无法可信重建时以原operation确定性fail / fallback。
- opener crash 后 native mutex 由 OS 释放；fresh attach 仍须按 positive orphan proof 判断旧 Attempt，不得因 mutex 可用直接 takeover。strict-native lock不支持时 fail closed，测试证明没有 soft-lock fallback。
- A通过`READ_WRITE` attachment提交Run X后detach，B从既有`READ_ONLY` attachment close / fresh attach取得`READ_WRITE`并cancel Run X时，必须走与本openerRun完全相同的public cancel、幂等与durable状态迁移，不读取或比较originating opener。若X的active worker仍由A持有，A的execution scheduler必须在有界时间内观察durable cancel并作用于本地worker；caller registry未命中不得影响cancel acceptance或最终物理传播，watchdog只作既有closeout supervisor而非替代owner传播。
- attachment factory cancellation、Host close、attachment close、partial allocation failure、重复 close和并发 close 都有确定性 cleanup；已返回 attachment 的 mode 终身不变。
- `max_compaction_attempts_per_operation`与Runner`max_retries`的owner、默认值、字段说明和测试互不混淆；前者是同一durable compaction operation内所有semantic proposal attempts总预算，后者是每次Runner call的transport retry。不存在proactive operation count配置。
- 受影响文件单文件覆盖率目标 `>=80%`，完整 pyright 与受影响测试通过；按触发规则完成 Host、Service/UI、runtime、config、tests与分层 README audit。

## WU-CTX-01 Usage-Anchored Adaptive Context Sizing

### 状态

GitHub Issue #20 当前为 OPEN，title / body 已与 `docs/host/design.md` §25 的 Usage-Anchored Adaptive Context Sizing 对齐，并明确 provider live evidence 不是 work unit 前置条件；usage 缺失时走 conservative fallback。

本条状态是 `active / Slice 1 implementation re-review pass；accepted slice commit bookkeeping`。PR #182 已于 2026-07-23 合并，merge commit=`5afe71fe`；goal confirmation artifact=`docs/reviews/wu-ctx-01-goal-confirmation-controller.md`，decision=`pass`。AgentCodex plan artifact=`docs/reviews/wu-ctx-01-plan-codex.md`，采用 3 个语义闭环 slices。双路 plan review/fix/re-review artifacts 与 Controller adjudications 已完成，accepted plan commit=`06c143f2`。第一次Slice 1 blocker修订由accepted plan amendment protected commit=`ff28cbc4`保护。第二次reactive blocker由accepted reactive plan amendment protected commit=`3f4190ed`保护，冻结4-stage/12-cell、exact catch-up、source frozen candidate复用、candidate/manifest-before-recovery-start与transaction-local strict loader。恢复实现后AgentCodex focused suite=`596 passed`、full pyright=`0 errors`，但full Host diagnostic=`2166 passed, 18 failed, 1 skipped, 6 deselected`，blocked artifact=`docs/reviews/wu-ctx-01-slice-1-implementation-blocked-codex.md`：strict actual-request loader证明startup recovery、running/waiting steer、wait resume等new Attempt producer也必须在自己的start transaction内写exact candidate/manifest。Controller stop adjudication=`docs/reviews/wu-ctx-01-slice-1-attempt-producer-stop-controller-adjudication.md`，decision=`reopen-plan`；拒绝loader fallback、start后补写、当前config重选或仅改fixture。第三次amendment初审两路均为`pass-with-risks`；Controller在`docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-review-controller-adjudication.md`裁决为`needs-fix`。AgentCodex随后消除startup strict policy source循环、彻底删除direct queue promotion durable bypass、将wait continuation闭集收紧为completed/cancelled，并澄清5-stage显式穷举、typed wait projection、Engine limited manifest及Slice 1/2/3边界。定向re-review `docs/reviews/plan-review-20260724-021259.md`与`docs/reviews/plan-review-20260724-021306.md`均为`pass`，Controller最终裁决`docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-rereview-controller-adjudication.md`为`pass`。accepted first-call producer plan protected commit=`ed43bcf2`。AgentCodex Slice 1 implementation handoff=`docs/reviews/wu-ctx-01-slice-1-implementation-resume-codex.md`，focused=`986 passed`、full Host=`2173 passed, 2 skipped, 6 deselected`、full pyright=`0 errors, 0 warnings`、changed production coverage均`>=86%`。双路implementation reviews=`docs/reviews/code-review-20260724-035007.md`与`docs/reviews/code-review-20260724-034122.md`；Controller在`docs/reviews/wu-ctx-01-slice-1-implementation-review-controller-adjudication.md`裁决为`needs-fix`，接受durable effective tool facts漂移、no-budget真实stage丢失、continuation unavailable reason误分类、manifest EventLog/hot identity不同源、15-cell缺3格、compactor proposal COMPLETE invariant缺口及同gate dead-code/docstring清理。AgentCodex fix artifact=`docs/reviews/wu-ctx-01-slice-1-implementation-review-fix-codex.md`，修复后focused=`397 passed`、full Host=`2202 passed, 2 skipped, 6 deselected`、full pyright=`0 errors, 0 warnings`、18个changed production files branch coverage全部`>=80%`。双路implementation re-review=`docs/reviews/code-review-20260724-045325.md`与`docs/reviews/code-review-20260724-044856.md`均为`pass`且无新增actionable finding；Controller final adjudication=`docs/reviews/wu-ctx-01-slice-1-implementation-rereview-controller-adjudication.md`，decision=`pass`。下一步创建accepted Slice 1 protected commit，然后进入Slice 2 independent canonical fact与Host→Service typed projection implementation。

### 设计与代码核对

- `docs/host/design.md` §25 已固定 usage-anchored 算法、owner、anchor compatibility / invalidation、durable pairing、fallback、threshold semantics、reactive 边界、非目标与确定性要求；provider tokenizer / provider count adapter 不再是目标。
- `dayu/host/context_budget.py` 当前模块 docstring 明确是 conservative estimator，不读取 Engine spec、provider overflow payload、metadata 或 extra payload。
- `estimate_context_budget(...)` 当前按文本长度、canonical JSON byte length、message overhead 和 tool schema overhead 估算 token。
- `ContextBudgetPolicy` 是 ratio-first policy：`context_window_size`、soft / hard threshold ratio、compaction 次数上限和 `policy_ref` 继续由既有 owner 管理；新算法不动态改写 ratio。
- PR #182 建立的 `RUNNER_CALL_INPUT_ASSEMBLED` + `RUNNER_CALL_INPUT_ITERATION_LINKED` 与 iteration-scoped usage 是 pairing 的唯一直接证据入口。goal confirmation 已确认现有 manifest / link 提供 lineage 基础，但尚未冻结 estimator identity / version、`E_anchor` 与同 iteration `prompt_tokens` 的直接配对 contract；这是 WU-CTX-01 的目标实现范围，不得从 provider request id、时间戳或 `USER_INPUT_ACCEPTED.display_text` 推断。
- `RunnerSpec.supports_stream_usage` 只门控是否发送 OpenAI `stream_options.include_usage=true` 扩展，不是 usage availability predicate。Engine / Host 必须按实际合法 `USAGE_REPORTED` presence 建立 anchor；例如 MiMo 流式 chunk 可以自动返回 nullable usage，且不要求发送 `include_usage`，不需要 provider-name branch。
- 当前 `USAGE_REPORTED` 已 durable 保存 `prompt_tokens` / `completion_tokens` / `total_tokens` 等内部 signal，但 Host public activity allowlist 没有 usage projection，Service 会丢弃 `activity=None` 的事件；当前 UI 至多能看到 compact activity，不能读取 typed context utilization。WU-CTX-01 必须修复 public contract 缺口，但不得把 raw `USAGE_REPORTED` payload、`payload_ref` 或 EventLog reader 泄漏给 UI。

### 目标

- 对成功 ordinary runner call，在 dispatch 前用现有 conservative estimator 冻结同源完整 input 的 `E_anchor`，再把同一 iteration 实际出现并由 Engine 归一化的 `usage.prompt_tokens` durable 配对为 `U_anchor`。
- 下一候选完整 input 使用同一 estimator / version 计算 `E_current`，预算预测固定为 `P_current = U_anchor + (E_current - E_anchor)`；signed delta 必须来自可证明的完整 input / manifest lineage。
- proactive compact、hard budget decision、compact / fallback 前后 sizing 与相关 diagnostics 使用同一 sizing contract。动态的是 estimate anchoring，不是 `soft_threshold_context_ratio` / `hard_threshold_context_ratio`。
- usage 缺失、非法、无法唯一关联，或 anchor 因 provider / model / context window / estimator / request semantics / accepted compact / lineage gap 不兼容时，对当前完整输入使用现有 conservative estimator。
- 若较旧 compatible anchor 之后的全部输入变化仍可从 durable lineage 重建，允许继续从该 anchor 累计 delta；任一变化不可证明则整体 fallback。
- 保持 provider-neutral：Host 只按 typed identity、manifest lineage 与实际 `USAGE_REPORTED` presence 判断，不硬编码 provider 名称。
- 对每个 ordinary / post-compact / dispatch-fallback 候选输入的 dispatch-relevant sizing result，先 durable append canonical `CONTEXT_BUDGET_EVALUATED`，再执行由该 decision 驱动的 proactive compact 或 dispatch。Host 从该同一 result 投影 `HostActivityKind.CONTEXT_USAGE` + typed `HostContextUsageView`，Service 原样投影为 `EntrypointContextUsage` 并通过既有 activity callback 交付，供未来 UI 展示当前上下文占用。
- typed public context-usage view 至少包含 `predicted_input_tokens`、`context_window_size`、未 clamp 的 `utilization_basis_points`、soft / hard threshold tokens、`estimate_method=usage_anchored|conservative_fallback` 与 `pressure_level=normal|soft_threshold_exceeded|hard_threshold_exceeded`。Host 拥有这些派生值；UI 只拥有“上下文约使用 62%”之类展示格式。

### Goal confirmation 进入条件与证据

- PR #182 merge、工作树与 `main` fast-forward preflight 均已通过。
- GitHub Issue #20 当前 scope 已与本节及 `docs/host/design.md` §25 对齐。
- goal confirmation 已从代码直接确认 complete runner-call manifest / accepted iteration link 提供 lineage 基础，同时确认冻结 estimator contract 与同 iteration usage 的直接配对仍是本 Work Unit 的实现目标；不得侵入 WU-OBS-00B / GitHub Issue #119 的 analyzer correlation owner，也不得通过 provider request identity、时间戳或 display text 推断关系。
- provider live probe 不作为 plan 前置条件。provider-neutral contract 以实际合法 `USAGE_REPORTED` presence 判断；usage 缺失、非法或 pairing 不可信时，当前完整输入严格 fallback 到既有 conservative estimator。
- `CONTEXT_BUDGET_EVALUATED` / typed public projection 与 usage-anchored 估算算法是两个独立修改；二者可以复用同一 Host-owned typed sizing result，但 plan、实现和测试必须分别描述 owner、顺序、失败边界与验收。

### 非目标

- 不引入 provider tokenizer、provider/model sizing adapter、远程 token-count endpoint、tokenizer 下载或运行时 tokenizer 版本管理。
- 不在 Context Governance 中硬编码 provider 名称分支。
- 不让 Engine provider 实现反向依赖 Host。
- 不把 compact / retry / proactive threshold governance 移入 Engine。
- 不移除 conservative fallback behavior。
- 不用 metadata 或 extra payload 夹带 sizing decision。
- 不训练全局 correction model，不跨 provider / model 共享学习系数，不动态修改 soft / hard ratio。
- 不按“上一次 usage 已超过 ratio，下一 Run 才 compact”的滞后规则执行；下一候选输入差量必须进入 dispatch 前预测。
- 不让 compactor proposal usage 污染 ordinary anchor，不用 reactive overflow 或 compact 后另一份输入的 usage 伪造失败输入的精确误差。
- 不实现具体 CLI / Web / WeChat 的进度条、颜色、文案、小数位或历史图表；本 Work Unit 只把 typed Host -> Service public contract 和既有 activity callback 交付路径准备完整。
- 不把 raw provider usage、anchor refs / digests、provider request id、完整 messages、policy internal ref 或 estimator diagnostic 暴露给 UI，也不让 UI 从 `USAGE_REPORTED`、EventLog payload 或 summary 文本自行计算百分比。

### 验收信号

- 直接公式测试证明 compatible anchor 使用 `P_current = U_anchor + (E_current - E_anchor)`，包括 signed positive / negative delta；同源关系无法证明时不使用该公式。
- `U_anchor / context_window_size = 62%` 且下一输入 delta 使 `P_current` 跨过 65% soft threshold 时，下一 Run 在 dispatch 前主动 compact；不能等到上一次 usage 自身越过 ratio。
- usage 可用时建立 / 刷新 compatible anchor；usage 缺失、nullable、非法、iteration pairing 缺失或 manifest mismatch 时，对当前完整输入执行 deterministic conservative fallback，Run 不因 usage 缺失失败。
- 较旧 compatible anchor 在中间一次或多次 usage 缺失、但全部输入变化可 durable 重建时继续累计 delta；任一 lineage gap 立即 fallback。
- provider / model / context window / estimator id 或 version / request serialization semantics 切换使 anchor 失效；accepted compact 使旧基线失效，post-compact immediate sizing 先走完整 fallback，后续成功 ordinary call 才建立新 anchor。
- compactor proposal usage 永不成为 ordinary anchor；reactive provider overflow 只触发现有 recovery / fallback，不生成伪造的 token delta 或 calibration sample。
- dispatch 前 `E_anchor`、`RUNNER_CALL_INPUT_ASSEMBLED`、accepted `RUNNER_CALL_INPUT_ITERATION_LINKED` 与同 iteration `USAGE_REPORTED` 可以在 crash / replay 后 durable 重建并得到相同预测和 decision；不得从 display text、时间戳或 provider request id 反推。
- soft / hard ratios 与由其派生的 thresholds 不被 usage 动态修改；usage 不回写已经完成的 dispatch decision。
- anchored 路径的 public `predicted_input_tokens` 等于同一 decision 的 `P_current`；fallback 路径等于当前完整输入的 conservative estimate。两条路径的 `utilization_basis_points` 都严格按 `floor(predicted_input_tokens * 10000 / context_window_size)` 计算且不 clamp，pressure level 与真正驱动 compact / dispatch 的 soft / hard decision 一致。
- `CONTEXT_BUDGET_EVALUATED` 在 durable event sequence 中先于由它驱动的 `CONTEXT_COMPACTION_REQUESTED` 或 `RUN_STARTED` / `ATTEMPT_STARTED`；stable identity / idempotency 绑定 Run、候选 input snapshot / digest、sizing stage、policy snapshot 与 estimator contract，重复 watch / reconciliation 不生成互相矛盾的 utilization activity。internal compactor proposal sizing 和刚返回但尚未形成下一候选输入的历史 usage 不产生 public context-usage activity。
- Host public projection tests 覆盖 `HostActivityKind.CONTEXT_USAGE`、typed `HostContextUsageView`、anchored / fallback method、normal / soft / hard pressure、超过 100% 不 clamp、缺 policy 时 unavailable；Service tests 覆盖 `EntrypointContextUsage` 字段无重算透传和既有 activity callback 交付。raw `USAGE_REPORTED` 继续没有 public activity，UI 无需且不得读取 EventLog payload。
- provider-neutral tests 覆盖实际合法 usage presence、usage 缺失 / 非法、`supports_stream_usage` 仅门控请求扩展，以及 conservative fallback 不泄漏 secret / sensitive raw payload。
- Host / Engine layering tests 继续证明无反向依赖、无 Engine-owned Host compact policy、无 provider-name branch；完整 conservative fallback 继续覆盖中文 / 英文混合财报文本、JSON / table-like excerpts、tool facts、citation / source refs、memory / compact material与 tool schema overhead。
- 实现改动触发的 Host、Service、CLI/UI、tests 与分层 README 必须按各自 README 约束审计；即使具体 UI 暂不渲染，也必须保证新增可选 typed 字段不会破坏既有 CLI activity formatter。

## WU-CM-10 Conversation Memory Eval Benchmark

### 状态

GitHub Issue #80 当前为 OPEN，定位为 Conversation Memory 的评测标准真源，也是 #81 Conversation Memory overall optimization 的后续 eval implementation work。#80 的评测实现不在 #81 前落地；它要评估的是 post-#81 的 memory semantic contract、compact shape、answer anchor、evidence refs、prompt assembly / budget policy 和 RunInputBuilder 行为，而不是锁定当前旧 memory snapshot shape。但 #80 定义的评测维度会反过来约束 #81：#81 design / plan 必须说明各评测维度如何被满足、延期或排除。

### 设计与代码核对

- #81 会先裁决 Conversation Memory 的语义类型、prompt assembly / budget policy、compact JSON shape、answer anchor、trace recall / evidence refs 等核心边界。
- 当前 #80 讨论借鉴 LongMemEval / PersonaMem，但 Dayu 的核心评测目标不是通用聊天长期记忆分数，而是财报分析中的 evidence-backed facts、answer anchors、forward intent、session summaries、tool provenance 与 context governance 协同。
- 如果在 #81 前按旧 `stable layer`、`history pool`、`working_assumptions` shape 写 eval，会反过来把旧设计固化为测试 truth。

### 目标

- 在 #81 完成或形成稳定 post-#81 memory contract 后，建立 Dayu Conversation Memory 评测体系；在 #81 设计与 plan 阶段，先用 #80 作为行为 oracle 与验收约束。
- 评测覆盖跨轮事实保留、证据链完整性、任务状态延续、回答锚点 / 上下文指代、重复工具调用治理、上下文压力与 compact、财报分析专属场景。
- 第一版优先做 deterministic offline eval：固定 multi-turn scenario fixture、mock finance tool、可控长 tool result、冲突 / 更新事实、Host public scenario harness。
- 检查 memory snapshot、RunInputBuilder messages、tool call counts、diagnostics 和 final response facts。
- 指标可以包括 fact recall accuracy、unsupported fact rate、provenance coverage、anchor resolution accuracy、tool reuse efficiency、update correctness、compact robustness、diagnostic precision。

### 非目标

- 不在 #81 前绑定旧 memory snapshot shape、旧 compact JSON shape 或旧 `working_assumptions` 语义。
- 不要求引入 long-term retrieval、向量索引、public memory edit / forget API。
- 不把 LongMemEval / PersonaMem 原始任务集直接当作 Dayu 评测真源。
- 不把 LLM judge 作为第一版唯一评分真源。

### 验收信号

- #81 已完成，或已形成稳定 post-#81 memory contract，足以定义 eval fixture 和 assertions。
- 明确 Dayu Conversation Memory eval 的 scope、non-goals 与目录边界。
- 至少落地三类核心 scenario：跨轮事实保留、compact / 长上下文压力、事实更新或冲突。
- 每个 scenario 至少验证 memory snapshot、RunInputBuilder memory messages、tool call behavior、diagnostics 中两类输出。
- 文档说明如何运行 eval，以及 eval 与普通单元测试 / smoke test 的关系。

## WU-CM-11 User Profile Memory Durable Boundary And Cross-session Profile

### 状态

GitHub Issue #115，作为 GitHub Issue #81 的后续子任务；deferred behind #81。User Profile Memory 是跨 session 用户画像能力，治理边界独立于 session Conversation Memory，不应被塞进 WU-CM-01 第一阶段。

### 目标

- 设计并实现独立的 durable User Profile Memory，而不是把用户画像伪装成 `pinned_state`、`working_assumptions`、answer anchor、episode summary 或 `evidence_backed_fact`。
- 明确 profile identity boundary：workspace、account、organization、user、subject partition 或其它显式 owner。
- 明确 profile item schema、source refs、observed_at / valid_from、supersedes、confidence、confirmation policy、撤销 / 过期状态和 current preference resolution。
- 明确 privacy / control：用户可见解释、reset、delete、export、disable 边界。
- 明确 prompt assembly 边界：User Profile 可以影响风格、优先级和偏好，但不能压过本轮明确用户输入或财报 evidence。
- 映射 GitHub Issue #80 的 dynamic profile 评测维度。

### 非目标

- 不在 WU-CM-01 / #81 第一阶段内实施 durable User Profile Memory。
- 不把跨 session profile 写入 session memory snapshot 作为捷径。
- 不让 profile entries 自动升级为 evidence-backed financial facts。
- 不让 profile memory 自动驱动工具执行。
- 不在未裁决 scope 前引入长期 retrieval、向量索引或 public memory edit API。

### 验收信号

- #81 设计真源和 WU-CM-01 plan 明确 User Profile Memory 是 deferred-with-owner，owner 为 WU-CM-11 / GitHub Issue #115。
- WU-CM-11 后续 plan 能定义 durable store / projection / prompt assembly / privacy controls / tests。
- tests 或 eval scenarios 能覆盖动态偏好更新、supersession、当前偏好选择、source refs，以及不能覆盖本轮用户输入或财报 evidence。
- GitHub Issue #80 dynamic profile 评测维度被映射为 current-scope behavior、deferred owner 或 explicit non-goal。
