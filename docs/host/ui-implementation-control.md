# Host UI / Product Entrypoint Implementation Control

## 文档职责

本文档是 Dayu product entrypoints 的实施总控文档，负责管理 CLI、Web、GUI 三类入口如何通过 Service assembly 与 Host public API 接入 Host。

本文档只承担实施编排职责：记录 product entrypoint work units 的范围、当前状态、GitHub Issue owner / destination、进入条件、交付物、验证要求、review 结果、residual risk 和下一步入口。

本文档不替代 Host 设计真源，不承载新的架构决策，不作为实现细节说明书。若某个 work unit 的讨论发现需要修改架构边界、状态机、公共接口、durable schema、EventLog 语义或跨层契约，必须先更新设计真源，再更新本文档和对应 GitHub Issue。

## 设计目标

Product entrypoint 实施必须始终服务于以下目标：

- 生产级通用 Agent，具备买方财报分析能力。
- 范式是“宿主强约束下的 LLM in the loop”。
- 严格遵守 `UI -> Service -> Host -> Engine` 分层边界。
- CLI / Web / GUI 入口只能通过 Service assembly 与 Host public API 触达 Host。
- ConfigLoader、ScenePrepare、ToolsDiscovery、override merge、runner / agent mapping、tool bundle subset selection、prompt injection、parser / retry / replay / stop policy 保持在 Host 外。
- Product entrypoint 不得传 raw config fragment、manifest raw patch、business storage implementation detail 或 Host internal durable row 给 Host。
- Product entrypoint 不得让 Host 直接扫描业务工具，不得直接读取 Fins storage，除非通过 approved Fins / Service boundary。

任何 plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项选择削弱这些目标，应停下来修正设计真源、本文档或对应 GitHub Issue 后再继续。

## 真源层级

Product entrypoint 实施遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源
  -> 约束跨层、跨 phase 的稳定术语含义

docs/host/design.md
  -> Host 架构真源
  -> 定义 UI / Service / Host / Engine 边界、公共接口、状态机、EventLog、恢复、等待和关键治理路径

docs/host/ui-implementation-control.md
  -> product entrypoint 实施编排文档
  -> 记录 CLI / Web / GUI work units、当前状态、进入 / 退出条件、交付物、验证要求、review 结论和 residual risk

GitHub Issues
  -> 对应 entrypoint work unit 的外部执行 owner / destination
  -> 记录 issue scope、讨论、PR 关联和跨文档追踪状态
```

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到设计真源，再更新本文档对应 work unit 的范围、非目标、验收信号和对应 GitHub Issue。

术语必须遵循项目级术语真源和 Host 设计真源。planning、implementation、review、fix 与 re-review 不得自行重解释 `Session`、`Run`、`Attempt`、`EventLog`、`HostEvent`、`EngineEvent`、`Service assembly`、`Host public API`、`ToolsDiscovery`、`Fins storage` 等术语。若发现术语缺失或冲突，应先讨论并同步真源文档，再继续推进。

## 管理范围

本文档只管理以下 product entrypoint work units：

- CLI entrypoint integration aligned with `dayu-agent` CLI，GitHub Issue #83。
- Web entrypoint integration through Service assembly，GitHub Issue #84。
- GUI entrypoint integration through Service assembly，GitHub Issue #85。

本文档不管理 Host 内部治理能力、Fins 工具迁移、Conversation Memory、WAIT adapter、Context Governance 或 durable store hardening。

## 工作流

Product entrypoint work unit 采用以下工作流：

```text
read ui-implementation-control.md
  -> select one work unit
  -> inspect current GitHub Issue scope
  -> inspect current code and tests
  -> for CLI: audit dayu-agent CLI command surface before planning
  -> discuss scope, non-goals, risk, and design sufficiency with the user
  -> update docs/host/design.md first if architecture or public contract changes are needed
  -> update this control doc and the GitHub Issue if scope, status, owner, residual risk, or entry point changes
  -> generate code-generation-ready plan for the selected work unit
  -> review plan
  -> user confirmation
  -> implement through the current gate workflow
  -> verify tests, pyright, and relevant README/doc sync
  -> run review / re-review
  -> update current status, artifacts, commits, residual risk, GitHub Issue state, and next entry point
```

每次只推进一个 work unit。进入 plan gate 前，必须先完成 issue / code 核对和 scope discussion，确认该 entrypoint 的真实缺口仍存在。

work unit plan 必须基于：

- Host 设计真源；
- 本文档中对应 work unit 的状态、issue owner / destination、目标、非目标、验收信号；
- 对应 GitHub Issue 的当前 scope；
- 代码核对得到的直接证据。

plan 不得从旧设计稿、旧代码路径、非真源讨论记录或 reviewer 个人偏好推导架构边界。
plan 必须避免过度设计；只能解决由 issue / 代码核对 / 设计真源直接支撑的当前 work unit 风险，不得把局部缺口扩大成通用框架、平台化能力或未来阶段能力。

plan 文档应放在 `docs/host/` 下；plan review、plan fix、plan re-review、implementation review、fix、re-review 和总控裁决 artifact 放在 `docs/reviews/` 下。

每个 work unit discussion 至少需要确认：

- work unit 目标与 success signal；
- 是否服务于本文档的设计目标；
- Host 设计真源是否足够具体；
- 对应 GitHub Issue 是否仍是正确 owner / destination；
- scope boundary、non-goals 与 stop conditions；
- 是否需要修改设计真源或 GitHub Issue；
- 是否存在会阻塞 code-generation-ready plan 的架构、公共接口、配置、入口 contract、测试或文档问题。

## 仓库发布约定

Product entrypoint 实施相关分支的 GitHub remote 名称为 `github`。提交后推送当前分支时使用：

```bash
git push -u github <branch>
```

不得假设 remote 名称为 `origin`。

进入 draft PR gate 前，本文档必须更新当前 work unit 状态、plan artifact、review artifact、accepted commit、remaining risks / owners、GitHub Issue destination 和 next entry point。进入 draft PR gate 后，按既定 gate workflow 自动推进到 `draft-PR-pass`；merge、approve、mark ready for review、request reviewers、delete branch、对外 comment 或创建 / 修改外部 issue 仍需额外授权。

## Slice 切分原则

每个 work unit 内的 implementation slices 在 discussion / plan 阶段再具体确定；总控阶段不预先替 work units 固定 slice。

slice 切分必须同时满足三个约束：

- 模型上下文窗口与 review 可承载复杂度：implementation agent 必须能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 必须能在一个上下文中有效审查。
- 代码依赖边界：slice 应沿 product entrypoint、Service assembly、Host public contract、配置装配、UI state mapping 或测试矩阵边界切分，避免一个 slice 同时跨越过多治理 owner。
- 可独立验证的行为闭环：slice 应大到能形成可测试的语义闭环，小到能一次实现、一次验证、一次 review。除非明确是 contract-only slice，否则不得留下只有命令解析、没有 Host public path，或只有 UI shell、没有 Service boundary 测试的孤立半成品。

slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理。好的 slice 应当有明确输入、输出、non-goals、allowed files / modules、验证命令、issue handoff 和后续 slice 可依赖的稳定交付物。

如果一个 work unit 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 plan 中说明前后 slice 的 contract handoff。如果某个 slice 需要跨模块修改，plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## 当前状态

| 项目 | 当前值 |
|---|---|
| phase | Product entrypoint implementation backlog |
| gate | accepted-plan |
| implementation status | not-started |
| active work unit | WU-CLI-01 |
| default next work unit | WU-CLI-01 |
| next entry point | accepted plan commit；完成后进入 implementation gate，由 AgentCodex 按 accepted plan 实施 |
| design source | 由 phaseflow 调用参数提供；本文档只维护 product entrypoint 实施总控状态 |
| plan artifacts | `docs/host/wu-cli-01-cli-entrypoint-plan.md` |
| implementation commits | none |
| review artifacts | `docs/reviews/plan-review-20260614-130113.md`; `docs/reviews/wu-cli-01-plan-review-ds.md`; `docs/reviews/wu-cli-01-plan-review-controller-adjudication.md`; `docs/reviews/wu-cli-01-plan-fix-codex.md`; `docs/reviews/wu-cli-01-plan-rereview-mimo.md`; `docs/reviews/wu-cli-01-plan-rereview-ds.md`; `docs/reviews/wu-cli-01-plan-rereview-controller-adjudication.md` |
| aggregate review artifacts | none |
| draft PR status | not-started |
| blocking open questions | none |

状态约定：

- `not-started`：尚未进入 plan / implementation。
- `discussion-ready`：已具备讨论和代码 / issue 核对入口，但还未形成 code-generation-ready plan。
- `planning`：正在形成或 review code-generation-ready plan。
- `implementation`：正在实施或修复。
- `review`：正在进行 code review、re-review 或 aggregate deepreview。
- `ready-to-open-draft-PR`：本轮 work unit 已完成本地 gate，等待进入 draft PR gate。
- `draft-PR-pass`：draft PR gate 已通过。

## 推进规则

- 每次只推进一个 work unit。
- 先做 GitHub Issue / 代码核对，再进入方案和实现。
- CLI work unit 进入 plan 前必须先审计 `dayu-agent` CLI command surface，并记录需要对齐或明确偏离的命令、参数、帮助文本和行为。
- 涉及 public contract、配置入口、跨层依赖或用户可见行为时，必须先形成明确 design decision。
- 测试优先按风险边界补齐；端到端 smoke 和耗时测试必须与常规测试入口分开。
- 实施完成后必须更新对应测试、类型检查、稳定文档说明和对应 GitHub Issue 状态。
- 每个 work unit 进入 plan、implementation、review、ready-to-open-draft-PR 或 draft-PR-pass 时，必须更新“当前状态”中的 gate、active work unit、artifact、commit、review 和 residual risk 信息。

## Residual Risk / 遗留问题追踪

本章节专门追踪实施过程中发现但未在当前 work unit 内关闭的 residual risk、遗留问题、测试缺口、设计疑问、entrypoint dependency 和后续 owner。不得把这类事项只停留在对话、review artifact、implementation report 或 GitHub Issue comment 中。

追踪规则：

- 每条 tracking item 必须有稳定 id、来源 work unit、状态、owner / destination 和下一步动作。
- `ready-to-open-draft-PR` 前，所有 tracking items 必须处于 `closed`、`deferred-with-owner` 或 `transferred-to-issue`，不得保留无 owner 的 open item。
- 如果 residual risk 需要修改 Host 架构、公共契约、配置 schema、状态机、durable schema 或 EventLog 语义，必须先同步设计真源，再更新本表和对应 GitHub Issue。
- 如果 residual risk 已由代码核对证明不存在，应标记 `closed` 并记录关闭依据，不继续保留为模糊风险。

状态值：

- `open`：仍需当前 work unit 或本轮 phase 处理。
- `deferred-with-owner`：明确后续 owner / work unit / issue，当前 work unit 不处理。
- `transferred-to-issue`：已迁移到独立 GitHub Issue 或等价外部追踪项。
- `closed`：已通过实现、测试、设计裁决或代码核对关闭。

| ID | 来源 | 类型 | 状态 | Owner / Destination | 下一步 | 记录 |
|---|---|---|---|---|---|---|
| WU-CLI-01-RR-01 | WU-CLI-01 plan re-review | behavior parity | deferred-with-owner | Fins owner；后续 Fins alias inference WU / GitHub Issue #83 intentional deviation | WU-CLI-01 解析保留 `--infer`，执行时报 unsupported；后续单独定义 approved Fins alias inference boundary | 旧 `--infer` alias inference 当前无 approved Fins boundary，download / upload 与旧 CLI 行为不完全一致。 |
| WU-CLI-01-RR-02 | WU-CLI-01 plan re-review | behavior parity | deferred-with-owner | Fins / tooling owner；后续 CI snapshot contract WU | WU-CLI-01 解析保留 `--ci`，执行时报 unsupported；后续定义 process snapshot public contract | 旧 `--ci` process snapshot 当前无公共 contract。 |
| WU-CLI-01-RR-03 | WU-CLI-01 plan re-review | Host observability | deferred-with-owner | Host / Service owner；后续 observability / per-run governance WU | WU-CLI-01 对旧 debug / trace / duplicate governance flags fail fast；后续若需要再设计 Host public per-run contract | 旧 debug / trace / duplicate governance flags 无当前 Host public per-run contract。 |
| WU-CLI-01-RR-04 | WU-CLI-01 plan re-review | Fins batch parity | deferred-with-owner | Fins owner；CLI-01-S6 implementation slice | 在 Fins boundary 建 typed batch plan helper；若无法自洽，降级并登记 deviation | `upload_filings_from` 的旧文件识别规则可能依赖旧 Fins helper。 |
| WU-CLI-01-RR-05 | WU-CLI-01 plan re-review | model profile UX | deferred-with-owner | Config / Service owner；后续 model profile UX WU | WU-CLI-01 只在当前 model / hint 可明确映射时支持 `--thinking` / `--no-thinking`，否则 unsupported | `--thinking` / `--no-thinking` 在当前模型 schema 中不是独立布尔开关。 |
| WU-CLI-01-RR-06 | WU-CLI-01 plan re-review | Fins cancel responsiveness | deferred-with-owner | Fins runtime owner；CLI-01-S5 / S6 implementation validation | CLI 第一次 SIGINT 发 durable cancel，第二次 SIGINT 允许本地退出并打印 job id；实现时验证长事务 cancel checkpoint | Fins job cancel 是协作式，部分长事务可能不及时检查 cancel request。 |
| WU-CLI-01-RR-07 | WU-CLI-01 plan re-review | Fins upload action parity | deferred-with-owner | Fins owner；CLI-01-S5 implementation slice | 只有当前 upload runtime 支持时放行 `upload_filing --action delete`，否则执行时报 unsupported | `upload_filing --action delete` 当前是否被 Fins upload runtime 支持需实现时验证。 |

## 当前 Work Units

| Work Unit | 主题 | Owner / Destination | 当前定位 |
|---|---|---|---|
| WU-CLI-01 | CLI entrypoint integration aligned with dayu-agent CLI | GitHub Issue #83 | CLI 入口通过 Service assembly 与 Host public API 接入 |
| WU-WEB-01 | Web entrypoint integration through Service assembly | GitHub Issue #84 | Web request path 通过 Service assembly 与 Host public API 接入 |
| WU-GUI-01 | GUI entrypoint integration through Service assembly | GitHub Issue #85 | GUI command / state path 通过 Service assembly 与 Host public API 接入 |

## WU-CLI-01 CLI Entrypoint Integration Aligned With Dayu-agent CLI

### 状态

GitHub Issue #83。CLI entrypoint 需要通过 Service assembly 与 Host public API 接入，并且命令行参数、子命令、帮助文本和用户可见行为需要对齐既有 `dayu-agent` CLI；任何偏离都必须显式记录并说明理由。

### 目标

- 审计既有 `dayu-agent` CLI command surface，记录需要保留或明确改变的命令、子命令、选项、别名、位置参数、config / workspace / prompt / scene flags、输入 / 输出行为、exit code 与 help text 结构。
- 实现或迁移 `dayu-agent-r` CLI entrypoint。
- CLI 必须通过 Service assembly 和 Host public API 触达 Host。
- Contract / smoke tests 证明 CLI 不绕过 Host public API。
- 文档描述 CLI usage 以及与 `dayu-agent` 的 intentional differences。

### 非目标

- 不让 CLI 直接调用 Host internals、durable rows、Engine internals 或 Fins storage。
- 不让 CLI 把 raw config fragments、manifest raw patches 或业务仓储实现细节传给 Host。
- 不让 Host 为 CLI 增加专用分支。
- 不为了对齐旧 CLI 而破坏当前 Service / Host 分层边界。

### 验收信号

- CLI command surface 已与 `dayu-agent` 对比并形成文档或 artifact。
- CLI entrypoint works through Service assembly and Host public API。
- CLI tests 覆盖代表性 commands、options、help output，以及至少一个 real Host open / follow-up path，可使用 mocked dependencies。
- intentional deviations from `dayu-agent` CLI behavior 均被记录并解释。

### 本轮 scope 裁决

本轮纳入旧 `dayu-cli` 用户命令面中的：

- `init`。
- `prompt`。
- `interactive`。
- Fins 直接数据命令：`download`、`upload_filing`、`upload_material`、`upload_filings_from`、`process`、`process_filing`、`process_material`。

本轮不纳入：

- `write` workflow。
- 差异化 Host 管理命令，包括 `host`、`sessions`、`runs`、`cancel`、`conv` 等需要按当前 Host public API 重新裁决的管理面。
- Web / GUI / WeChat / render entrypoint。

架构裁决：

- CLI 是当前 UI adapter，不是 Service 真源；CLI interactive 所需的会话打开、follow-up、terminal observation、cancel 与错误映射能力，应沉淀在可复用的 Service 边界中，未来 WeChat / GUI 可以复用同一 Service 语义，而不是复制 CLI 专用编排。
- `prompt` 与 `interactive` 必须通过 `ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly -> Host public API` 触达 Host。
- Fins 直接数据命令不伪装成 Host run，必须走 approved Service / Fins boundary，禁止散落直接读取 Fins storage。
- Fins 直接数据命令必须支持 cancel；具体 cancel contract、触发方式、进程 / 信号处理、job cancel 映射和验证边界由 plan gate 基于现有 Fins ingestion runtime 与 service boundary 细化。
- slice 数量与切分边界由 plan gate 基于可验证闭环、上下文承载能力和代码依赖边界决定。

### Plan Gate 裁决

- Plan artifact: `docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Plan review artifacts: `docs/reviews/plan-review-20260614-130113.md`、`docs/reviews/wu-cli-01-plan-review-ds.md`、`docs/reviews/wu-cli-01-plan-review-controller-adjudication.md`。
- Plan fix artifact: `docs/reviews/wu-cli-01-plan-fix-codex.md`。
- Plan re-review artifacts: `docs/reviews/wu-cli-01-plan-rereview-mimo.md`、`docs/reviews/wu-cli-01-plan-rereview-ds.md`、`docs/reviews/wu-cli-01-plan-rereview-controller-adjudication.md`。
- 总控裁决：plan re-review pass，12 个 accepted findings 均已关闭；本轮坚持迁移旧 CLI 业务语义与用户可见行为，并适配当前 Host public contracts / API，不迁移旧代码实现。
- 下一步：创建 accepted plan commit，然后进入 implementation gate。

## WU-WEB-01 Web Entrypoint Integration Through Service Assembly

### 状态

GitHub Issue #84。Web entrypoint 需要将 Web requests 映射到 Service assembly 与 Host public API，不能直接依赖 Host internals 或 ad hoc runtime wiring。

### 目标

- 实现或集成 Web entrypoint request / response contract。
- Web request path 必须通过 Service assembly 和 Host public API 触达 Host。
- 覆盖 opening session / run、submitting follow-up input、observing terminal or streamed status through approved public contracts。
- Error mapping 必须显式，不泄漏 Host implementation details。
- 文档描述 Web integration entrypoint 以及与 Service / Host 的边界。

### 非目标

- 不让 Web layer 直接调用 Host internals、durable rows、Engine internals 或 Fins storage。
- 不让 Web layer 把 raw config fragments、manifest raw patches 或业务仓储实现细节传给 Host。
- 不让 Host 为 Web 增加专用分支。
- 不让 UI / Web layer 创建反向依赖。

### 验收信号

- Web request path reaches Host only through Service assembly and Host public API。
- Contract / smoke tests 证明 Web entrypoint 不绕过 Host public API。
- Tests 覆盖 opening a session / run、submitting follow-up input、observing terminal or streamed status。
- Error mapping 不泄漏 Host implementation details。

## WU-GUI-01 GUI Entrypoint Integration Through Service Assembly

### 状态

GitHub Issue #85。GUI entrypoint 需要将 GUI interactions 映射到 Service assembly 与 Host public API，并保持明确的 state、command 和 error 边界。

### 目标

- 实现或集成 GUI entrypoint command / state / error boundary。
- GUI command path 必须通过 Service assembly 和 Host public API 触达 Host。
- 覆盖 opening session / run、submitting follow-up input、cancellation or close behavior where applicable、observing terminal or streamed status through approved public contracts。
- GUI state mapping 必须显式，不泄漏 Host implementation details。
- 文档描述 GUI integration entrypoint 以及与 Service / Host 的边界。

### 非目标

- 不让 GUI layer 直接调用 Host internals、durable rows、Engine internals 或 Fins storage。
- 不让 GUI layer 把 raw config fragments、manifest raw patches 或业务仓储实现细节传给 Host。
- 不让 Host 为 GUI 增加专用分支。
- 不让 GUI layer 创建反向依赖。

### 验收信号

- GUI command path reaches Host only through Service assembly and Host public API。
- Contract / smoke tests 证明 GUI entrypoint 不绕过 Host public API。
- Tests 覆盖 opening a session / run、submitting follow-up input、cancellation or close behavior where applicable、observing terminal or streamed status。
- GUI state mapping 不泄漏 Host implementation details。
