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
| gate | implementation |
| implementation status | CLI-01-S5 accepted; ready for CLI-01-S6 |
| active work unit | WU-CLI-01 |
| default next work unit | WU-CLI-01 |
| next entry point | implementation gate：AgentCodex 按 accepted plan 实施 CLI-01-S6 |
| design source | 由 phaseflow 调用参数提供；本文档只维护 product entrypoint 实施总控状态 |
| plan artifacts | `docs/host/wu-cli-01-cli-entrypoint-plan.md` |
| implementation commits | CLI-01-S1 `52db520c`; CLI-01-S2 `52bc7032`; CLI-01-S3 `4b28bbe5`; CLI-01-S4 `b784ff5b`; CLI-01-S5 `48a97942`; accepted plan commit `de99831f` |
| review artifacts | `docs/reviews/plan-review-20260614-130113.md`; `docs/reviews/wu-cli-01-plan-review-ds.md`; `docs/reviews/wu-cli-01-plan-review-controller-adjudication.md`; `docs/reviews/wu-cli-01-plan-fix-codex.md`; `docs/reviews/wu-cli-01-plan-rereview-mimo.md`; `docs/reviews/wu-cli-01-plan-rereview-ds.md`; `docs/reviews/wu-cli-01-plan-rereview-controller-adjudication.md`; `docs/reviews/wu-cli-01-s1-implementation-review-mimo.md`; `docs/reviews/wu-cli-01-s1-implementation-review-ds.md`; `docs/reviews/wu-cli-01-s1-implementation-review-controller-adjudication.md`; `docs/reviews/wu-cli-01-s1-implementation-fix-codex.md`; `docs/reviews/wu-cli-01-s1-implementation-rereview-mimo.md`; `docs/reviews/wu-cli-01-s1-implementation-rereview-ds.md`; `docs/reviews/wu-cli-01-s1-implementation-rereview-controller-adjudication.md`; `docs/reviews/wu-cli-01-s2-implementation-review-mimo.md`; `docs/reviews/wu-cli-01-s2-implementation-review-ds.md`; `docs/reviews/wu-cli-01-s2-implementation-review-controller-adjudication.md`; `docs/reviews/wu-cli-01-s2-implementation-fix-codex.md`; `docs/reviews/wu-cli-01-s2-implementation-rereview-mimo.md`; `docs/reviews/wu-cli-01-s2-implementation-rereview-ds.md`; `docs/reviews/wu-cli-01-s2-implementation-rereview-controller-adjudication.md`; `docs/reviews/wu-cli-01-s3-implementation-codex.md`; `docs/reviews/wu-cli-01-s3-implementation-review-mimo.md`; `docs/reviews/wu-cli-01-s3-implementation-review-ds.md`; `docs/reviews/wu-cli-01-s3-implementation-review-controller-adjudication.md`; `docs/reviews/wu-cli-01-s4-implementation-codex.md`; `docs/reviews/wu-cli-01-s4-implementation-review-mimo.md`; `docs/reviews/wu-cli-01-s4-implementation-review-ds.md`; `docs/reviews/wu-cli-01-s4-implementation-review-controller-adjudication.md`; `docs/reviews/wu-cli-01-s4-implementation-rereview-mimo.md`; `docs/reviews/wu-cli-01-s4-implementation-rereview-ds.md`; `docs/reviews/wu-cli-01-s4-implementation-rereview-controller-adjudication.md`; `docs/reviews/wu-cli-01-s5-implementation-codex.md`; `docs/reviews/wu-cli-01-s5-implementation-review-mimo.md`; `docs/reviews/wu-cli-01-s5-implementation-review-ds.md`; `docs/reviews/wu-cli-01-s5-implementation-review-controller-adjudication.md` |
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
| WU-CLI-01-RR-06 | WU-CLI-01 plan re-review / S5 review | Fins cancel responsiveness | deferred-with-owner | Fins runtime owner；CLI runtime / cross-platform signal adapter owner；CLI-01-S5 / S6 implementation validation 或后续跨平台 cancel WU | CLI 第一次 SIGINT 发 durable cancel，第二次 SIGINT 允许本地退出并打印 job id；实现时验证长事务 cancel checkpoint；若需要 Windows ProactorEventLoop 等无 `add_signal_handler` 平台支持，另设 signal adapter contract | Fins job cancel 是协作式，部分长事务可能不及时检查 cancel request；无 `add_signal_handler` 平台无法提供同等 durable cancel UX。 |
| WU-CLI-01-RR-07 | WU-CLI-01 plan re-review | Fins upload action parity | deferred-with-owner | Fins owner；CLI-01-S5 implementation slice | 只有当前 upload runtime 支持时放行 `upload_filing --action delete`，否则执行时报 unsupported | `upload_filing --action delete` 当前是否被 Fins upload runtime 支持需实现时验证。 |
| WU-CLI-01-RR-08 | WU-CLI-01 S5 review | CLI output UX | deferred-with-owner | CLI / Fins product owner；后续 CLI output polishing 或 S6 后统一 direct command result display | 当前 S5 成功输出 job id，后续按 direct command 业务摘要需求决定是否展示 `result_summary` 可读摘要 | `SUCCEEDED` direct command 输出未展示 Fins `result_summary`；不阻塞 S5 boundary / cancel / request mapping。 |

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
- Accepted plan commit: `de99831f`。
- 下一步：进入 implementation gate。

### CLI-01-S1 Implementation Gate

- Implementation report: `docs/reviews/wu-cli-01-s1-implementation-codex.md`。
- 实现范围：CLI package skeleton、parser factory、scoped command help、exit code mapping 与 placeholder command runner。
- 总控复核：改动未进入 Host / Fins 业务执行；未注册 `write`、`host`、`sessions`、`runs`、`cancel`、`conv`；`interactive --help` 包含 optional `--ticker`。
- 验证：
  - `source .venv/bin/activate && pytest tests/cli -q`：24 passed。
  - `source .venv/bin/activate && pytest tests/cli --cov=dayu.cli --cov-report=term-missing -q`：24 passed，总覆盖率 98%。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- 下一步：进入 CLI-01-S1 implementation review gate。

### CLI-01-S1 Implementation Review Gate

- Review artifacts: `docs/reviews/wu-cli-01-s1-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s1-implementation-review-ds.md`。
- Controller adjudication: `docs/reviews/wu-cli-01-s1-implementation-review-controller-adjudication.md`。
- 总控裁决：pass-with-fix。
- 审查通过项：
  - S1 范围边界：CLI package skeleton、parser、help、exit contract，未进入 Host/Fins 业务执行。
  - 命令注册范围：只注册计划要求的 10 个命令，未注册 `write`/`host`/`sessions`/`runs`/`cancel`/`conv`。
  - `interactive --help` 包含 optional `--ticker`。
  - `main(argv)` 只做 parse/dispatch/exit mapping；argparse help=0、usage/unknown=2、KeyboardInterrupt=130。
  - AGENTS.md 编码约束：中文 docstring、严格类型签名、无 Any/object/hasattr/getattr 逃逸、无兼容 wrapper、无反向依赖。
  - tests 覆盖 S1 success signal（24 passed，覆盖率 98%），README 更新符合 tests/README 约束。
  - pyproject console script `dayu-cli` import 验证通过，`python -m dayu.cli` 正确。
  - pyright 类型检查：0 errors。
- Accepted findings:
  - S1-IMPL-F01：`dayu/cli/arg_parsing.py` 多个函数签名直接暴露 `argparse._SubParsersAction[...]` 私有类型。
  - S1-IMPL-F02：`dayu/cli/main.py` 在 `COMMAND_RUNNERS` 缺失 runner 时静默返回 `EXIT_FAILURE`，缺少 stderr 诊断。
- 下一步：AgentCodex fix gate。

### CLI-01-S1 Fix Gate

- Fix report: `docs/reviews/wu-cli-01-s1-implementation-fix-codex.md`。
- 修复范围：
  - S1-IMPL-F01：新增 `CommandSubparserRegistry` Protocol，收敛 argparse subparser registry 类型；新增范围内不再暴露 `_SubParsersAction` 私有类型名。
  - S1-IMPL-F02：runner 缺失时输出 stderr 内部诊断，并补充 `test_main_reports_missing_command_runner`。
- 验证：
  - `source .venv/bin/activate && pytest tests/cli -q`：25 passed。
  - `source .venv/bin/activate && pytest tests/cli --cov=dayu.cli --cov-report=term-missing -q`：25 passed，总覆盖率 99%。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- 下一步：进入 CLI-01-S1 implementation re-review gate。

### CLI-01-S1 Re-Review Gate 裁决

- Re-review artifacts: `docs/reviews/wu-cli-01-s1-implementation-rereview-mimo.md`、`docs/reviews/wu-cli-01-s1-implementation-rereview-ds.md`。
- Controller adjudication: `docs/reviews/wu-cli-01-s1-implementation-rereview-controller-adjudication.md`。
- 总控裁决：pass。
- Closed findings:
  - S1-IMPL-F01：`CommandSubparserRegistry` Protocol 已隔离 argparse subparser registry，新增范围内 `_SubParsersAction` 零残留，且无 `Any` / `object` 逃逸。
  - S1-IMPL-F02：runner 缺失路径输出 stderr 内部诊断，测试覆盖退出码与诊断文本。
- 验证：
  - `source .venv/bin/activate && pytest tests/cli -q`：25 passed。
  - `source .venv/bin/activate && pytest tests/cli --cov=dayu.cli --cov-report=term-missing -q`：25 passed，总覆盖率 99%。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- Accepted implementation commit: `52db520c`。
- 下一步：进入 CLI-01-S2 implementation gate。

### CLI-01-S2 Implementation Gate

- Implementation report: `docs/reviews/wu-cli-01-s2-implementation-codex.md`。
- 实现范围：runtime location 显式 config overlay、`host_assembly` per-run override sibling helper、可复用 `dayu.service.entrypoint_runtime` Service boundary。
- 总控复核：S2 未实现 prompt / interactive CLI command、Fins direct command 或 init；新增 Service helper 不解析 CLI 参数、不写 stdout/stderr、不安装 signal handler。
- 验证：
  - `source .venv/bin/activate && pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py -q`：64 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing -q`：11 passed，`entrypoint_runtime.py` 覆盖率 95%。
  - `source .venv/bin/activate && pytest tests/runtime/test_runtime_location.py --cov=dayu.runtime.location --cov-report=term-missing -q`：8 passed，`location.py` 覆盖率 100%。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- 下一步：进入 CLI-01-S2 implementation review gate。

### CLI-01-S2 Review Gate 裁决

- Review artifacts: `docs/reviews/wu-cli-01-s2-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s2-implementation-review-ds.md`。
- Controller adjudication: `docs/reviews/wu-cli-01-s2-implementation-review-controller-adjudication.md`。
- 总控裁决：pass-with-fix。
- Accepted findings:
  - S2-IMPL-F01：`cancel_entrypoint_run_and_wait(...)` 在 `get_run` 与 watcher attach / `cancel_run` 之间存在 terminal race。
  - S2-IMPL-F02：watcher drain failure 被静默忽略，且 watcher failure -> outbox fallback 路径无测试覆盖。
  - S2-IMPL-F03：`ensure_or_create_entrypoint_session(...)` 参数校验错误路径无测试覆盖。
  - S2-IMPL-F04：`_wait_for_terminal(...)` 无内部超时，caller 责任未写清。
- Deferred finding：`_attach_watcher` 的 `cast(ClosableHostEventIterator, ...)` 属于 Host public contract typing refinement，当前不阻塞 S2；如需消除，应另行设计 Host `watch_session_events` 返回类型。
- 下一步：AgentCodex fix gate。

### CLI-01-S2 Fix Gate

- Fix report: `docs/reviews/wu-cli-01-s2-implementation-fix-codex.md`。
- 修复范围：
  - S2-IMPL-F01：初始 `get_run(...)` 已终态时跳过 `cancel_run(...)`；`cancel_run(...)` 与终态竞争失败时继续通过 public observation / outbox fallback 获取 terminal。
  - S2-IMPL-F02：watcher drain failure 进入 observation state；fallback terminal result 或 observation error 携带 watcher failure 诊断；新增 watcher failure -> outbox fallback 测试。
  - S2-IMPL-F03：补齐 `ensure_or_create_entrypoint_session(...)` 四类参数校验错误路径测试。
  - S2-IMPL-F04：docstring / README 明确 Service helper 不持有内部 timeout，调用方负责 task cancellation、`asyncio.wait_for(...)` 或显式 cancel。
- 验证：
  - `source .venv/bin/activate && pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py -q`：71 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing -q`：18 passed，`entrypoint_runtime.py` 覆盖率 97%。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- 下一步：进入 CLI-01-S2 implementation re-review gate。

### CLI-01-S2 Re-Review Gate 裁决

- Re-review artifacts: `docs/reviews/wu-cli-01-s2-implementation-rereview-mimo.md`、`docs/reviews/wu-cli-01-s2-implementation-rereview-ds.md`。
- Controller adjudication: `docs/reviews/wu-cli-01-s2-implementation-rereview-controller-adjudication.md`。
- 总控裁决：pass。
- Closed findings:
  - S2-IMPL-F01：initial `get_run(...)` 已终态时跳过 `cancel_run(...)`；`cancel_run(...)` 与终态竞争失败时继续 public terminal observation / outbox fallback。
  - S2-IMPL-F02：watcher failure 不再静默丢弃，diagnostic 进入 terminal result / observation error，且有 watcher failure -> outbox fallback 测试。
  - S2-IMPL-F03：`ensure_or_create_entrypoint_session(...)` 四类参数校验错误路径测试已补齐。
  - S2-IMPL-F04：submit / cancel wait helper docstring 和 README 均明确 caller-owned timeout contract。
- 验证：
  - `source .venv/bin/activate && pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py -q`：71 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing -q`：18 passed，`entrypoint_runtime.py` 覆盖率 97%。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- Accepted implementation commit: `52bc7032`。
- 下一步：进入 CLI-01-S3 implementation gate。

### CLI-01-S3 Implementation Gate

- Implementation report: `docs/reviews/wu-cli-01-s3-implementation-codex.md`。
- 实现范围：`dayu-cli prompt` one-shot command，经 `ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly -> Host public API` 提交单轮 Agent Run，并输出 Host terminal final answer / error / cancelled status。
- 总控复核：
  - S3 目标是迁移旧 `prompt` 的用户可见业务语义，并适配当前 Host public contract / API；不是迁移旧代码实现。
  - CLI adapter 只构造 Service / Host public DTO；未直接构造 Engine request，未读取 Host durable internals，未访问 Fins storage。
  - `--ticker` 映射为 prompt scene required context slot 与 Host business object context；未提供 ticker 时使用明确默认业务主体文本。
  - `--label` 映射为 Host session slot key；无 label 时创建 fresh session。
  - `--model-name` 与可映射执行参数通过 Service assembly override / run override 进入 Host public submit request；无当前 typed public contract 的旧执行参数 fail fast。
  - SIGINT 在 Host accepted Run 后构造 typed `CancelRunRequest` 并等待同一 Run terminal；accepted 前只做本地中断退出。
- 验证：
  - `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_arg_parsing.py tests/service/test_entrypoint_runtime.py -q`：62 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_arg_parsing.py --cov=dayu.cli.commands.prompt --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov-report=term-missing -q`：41 passed，总覆盖率 95%；`dayu/cli/arg_parsing.py` 100%，`dayu/cli/commands/prompt.py` 91%，`dayu/cli/host_context.py` 98%，`dayu/cli/output.py` 80%。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- 下一步：进入 CLI-01-S3 implementation review gate。

### CLI-01-S3 Review Gate 裁决

- Review artifacts: `docs/reviews/wu-cli-01-s3-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s3-implementation-review-ds.md`。
- Controller adjudication: `docs/reviews/wu-cli-01-s3-implementation-review-controller-adjudication.md`。
- 总控裁决：pass。
- 审查通过项：
  - `prompt` 只通过 ConfigLoader、ScenePrepare、ToolsDiscovery、Service assembly 与 Host public API，未直接构造 Engine request，未读取 Host durable internals，未访问 Fins storage。
  - CLI / Service 边界清晰：CLI 负责参数、signal、stdout/stderr、exit code；Service helper 不解析 CLI、不安装 signal handler、不写终端，后续 WeChat / GUI 可复用。
  - `--ticker`、`--label`、`--model-name`、可映射 execution overrides 与 unsupported legacy flags 均符合 accepted plan。
  - SIGINT cancel 语义符合 plan：Run accepted 前本地退出 130；accepted 后发 typed Host cancel 并等待同一 Run terminal；重复 SIGINT 不产生重复 cancel。
  - `on_run_accepted` callback 未破坏 S2 watcher attach-before-submit、terminal observation、caller-owned timeout contract。
  - AGENTS.md 编码约束、README 更新、测试覆盖率与 pyright 均通过。
- Non-blocking observations：
  - `render_prompt_terminal_result` 的 CANCELLED / LOST / SUCCEEDED-without-answer 防御分支可在后续触碰 CLI output 时补直接单测；当前 `dayu/cli/output.py` 覆盖率 80%，满足单文件覆盖率门槛，且不影响 S3 Host public path 正确性。
  - 不支持 `loop.add_signal_handler` 的事件循环环境会降级为默认 `KeyboardInterrupt`；当前目标运行环境不是 Windows ProactorEventLoop，如未来需要跨平台 typed cancel，再单独设计 signal / cancellation adapter contract。
- Accepted implementation commit: `4b28bbe5`。
- 下一步：进入 CLI-01-S4 implementation gate。

### CLI-01-S4 Implementation Gate

- Implementation report: `docs/reviews/wu-cli-01-s4-implementation-codex.md`。
- 实现范围：`dayu-cli interactive` REPL，经 `EntrypointRuntimeRequest(scene_id="interactive")`、Service helper 与 Host public API 完成 Session ensure/create、多轮 follow-up、terminal observation 与运行中 cancel。
- 总控复核：
  - S4 目标是迁移旧 `interactive` 的用户可见业务语义，并适配当前 Host public contract / API；不是迁移旧 `interactive_ui.py` 或旧 label registry。
  - CLI adapter 负责输入、输出、signal 与 Host context/id 构造；Session、turn、terminal observation 与 cancel 仍复用 `dayu.service.entrypoint_runtime`。
  - `--label` 使用 `cli.interactive.<label>` slot；`--new-session` 使用 `create_session(bind_slot=True)`；无 label 时创建当前进程 fresh session，不写旧 registry。
  - `--ticker` 映射为 `fins_default_subject`，未传时使用 `"未指定具体公司"`；`base_user` 使用 `"本地 CLI 用户"`。
  - 每轮生成新的 Host request id 与 submit `client_request_id`；同一轮 cancel 使用稳定 run-id based cancel `client_request_id`。
  - 终态策略符合 S4：`SUCCEEDED` 输出答案继续；`FAILED` / `CANCELLED` 输出状态并回到输入态；`LOST` 为 fatal exit 1。
  - Controller pre-review blocker 已在 implementation gate 内修复：第一次 SIGINT 后等待 run id 阶段若 submit task 先完成，会 `await submit_task` 返回 terminal 或透传异常，不再误映射为本地 130。
- 验证：
  - `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.commands.interactive --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov-report=term-missing -q`：63 passed，3 条 edgar deprecation warnings；`interactive.py` 88%，`host_context.py` 99%，`output.py` 83%，`arg_parsing.py` 100%，`main.py` 94%。
  - `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q`：82 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- 下一步：进入 CLI-01-S4 implementation review gate。

### CLI-01-S4 Review Gate 裁决

- Review artifacts: `docs/reviews/wu-cli-01-s4-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s4-implementation-review-ds.md`。
- Controller adjudication: `docs/reviews/wu-cli-01-s4-implementation-review-controller-adjudication.md`。
- 总控裁决：pass-with-fix。
- 审查通过项：
  - `interactive` 只通过 `EntrypointRuntimeRequest(scene_id="interactive")`、Service helper、`open_host(...)` 与 Host public API，未直接构造 Engine request，未访问 Host durable/internal，未读取 Fins storage。
  - CLI / Service 边界清晰：CLI 负责 REPL 输入、signal、stdout/stderr、exit code、Host context/id；Service helper 仍不依赖 CLI，可被后续 WeChat / GUI 复用。
  - `--label`、`--new-session`、`--ticker`、`--model-name`、execution overrides 与 unsupported legacy flags 的映射符合 accepted plan。
  - 多轮状态机符合 S4：两轮同 session，每轮新的 Host request id / submit client request id，每轮独立 watcher attach/close 与 terminal wait state。
  - SIGINT cancel 语义符合 S4：运行态第一次 Ctrl-C 发 typed Host cancel；第二次 Ctrl-C 本地 130；同一轮 cancel id 稳定；等待 run id 阶段 submit 先完成/失败不误映射为 130。
  - Terminal policy 符合 S4：`SUCCEEDED` 继续；`FAILED` / `CANCELLED` 继续；`LOST` / Service fatal 退出 1。
- Accepted findings：
  - S4-IMPL-F01：输入态 Ctrl-C 行为缺少明确测试覆盖。当前实现选择退出当前 command 并返回 130；accepted plan 明确要求“按实现测试固定”，因此需要补测试。
  - S4-IMPL-F02：运行态 SIGINT task cleanup 存在分支和 finally 重复 cancel / await 的代码异味。功能正确但增加状态机阅读负担，应低风险清理。
- 下一步：AgentCodex low-fix gate。

### CLI-01-S4 Low-Fix Gate

- Updated implementation report: `docs/reviews/wu-cli-01-s4-implementation-codex.md`。
- 修复范围：
  - S4-IMPL-F01：新增输入态 Ctrl-C 测试，固定为退出当前 command、返回 130，且不发 submit / cancel。
  - S4-IMPL-F02：新增 `_cancel_and_await_task(...)` 统一清理运行态 SIGINT 相关 task，移除分支与 finally 重复 cancel / await 的代码异味，语义保持不变。
- 验证：
  - `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.commands.interactive --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov-report=term-missing -q`：64 passed，3 条 edgar deprecation warnings；`interactive.py` 88%，`host_context.py` 99%，`output.py` 83%，`arg_parsing.py` 100%，`main.py` 94%。
  - `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q`：82 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- 下一步：进入 CLI-01-S4 implementation re-review gate。

### CLI-01-S4 Re-Review Gate 裁决

- Re-review artifacts: `docs/reviews/wu-cli-01-s4-implementation-rereview-mimo.md`、`docs/reviews/wu-cli-01-s4-implementation-rereview-ds.md`。
- Controller adjudication: `docs/reviews/wu-cli-01-s4-implementation-rereview-controller-adjudication.md`。
- 总控裁决：pass。
- Closed findings：
  - S4-IMPL-F01：输入态 Ctrl-C 行为已由测试固定为退出当前 command、返回 130，且不发 submit / cancel。
  - S4-IMPL-F02：运行态 SIGINT task cleanup 已集中到 `_cancel_and_await_task(...)`，重复 cancel / await 代码异味已关闭。
  - Controller pre-review blocker 仍关闭：等待 run id 阶段 submit task 先完成时返回 terminal；submit task 先失败时透传异常；不误映射为本地 130。
- 验证：
  - `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.commands.interactive --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov-report=term-missing -q`：64 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q`：82 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- Accepted implementation commit: `b784ff5b`。
- 下一步：进入 CLI-01-S5 implementation gate。

### CLI-01-S5 Implementation Gate

- Implementation report: `docs/reviews/wu-cli-01-s5-implementation-codex.md`。
- 实现范围：Fins direct job Service boundary 与 `download`、`upload_filing`、`upload_material`、`process`、`process_filing`、`process_material` direct command runner。
- 总控复核：
  - S5 目标是迁移旧 Fins direct commands 的业务语义，并适配当前 Fins runtime / Service public boundary；不是迁移旧 CLI 实现。
  - Fins direct commands 不创建 Host Run，不写 Host EventLog，不伪装成 Host wait；CLI 经 `dayu.service.fins_direct` 启动 durable Fins ingestion job、轮询 `read_job(job_id)`、通过 `request_cancel(job_id)` 取消。
  - CLI adapter 只负责 argparse 参数转换、轻量用户输入校验、stdout/stderr 与 SIGINT 映射；typed Fins download / preprocess / upload request 构造收敛到 Service helper。
  - upload wrapper 只调用 `FinsIngestionRuntime.start_upload(...)` union API，不要求 runtime 存在 `start_upload_filing(...)` / `start_upload_material(...)`。
  - `upload_filings_from` 属于 CLI-01-S6，当前只保留 parser 并执行时报 unsupported；`--infer` / `--ci` 继续按已登记 residual risk fail fast。
  - 更新 `tests/service/test_import_boundary.py` 属于 accepted Service/Fins boundary 同步，不表示允许 Service 任意导入 Fins 非公共实现或直接读取 Fins storage。
- 验证：
  - `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`：22 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && pytest tests/cli tests/service tests/fins/test_fins_ingestion_runtime.py -q`：195 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py --cov=dayu.service.fins_direct --cov=dayu.cli.commands.fins --cov-report=term-missing -q`：22 passed；`dayu/service/fins_direct.py` 92%，`dayu/cli/commands/fins.py` 88%。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- Controller follow-up review focus：
  - 裁决重点是旧业务逻辑是否迁移到新 Service/Fins boundary，而不是旧实现是否被搬运。
  - 明确检查 CLI 对 `dayu.fins.domain.enums.SourceKind` 的依赖是否仍属于 accepted plan 允许的 Fins 枚举 / domain value，不能扩散为 CLI 直接依赖 Fins runtime 或 storage。
  - 明确检查 SIGINT 后 task cleanup、first / second SIGINT、job id 前 KeyboardInterrupt、terminal mapping 和 unsupported flags。
- 下一步：进入 CLI-01-S5 implementation review gate。

### CLI-01-S5 Review Gate 裁决

- Review artifacts: `docs/reviews/wu-cli-01-s5-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s5-implementation-review-ds.md`。
- Controller adjudication: `docs/reviews/wu-cli-01-s5-implementation-review-controller-adjudication.md`。
- 总控裁决：pass。
- 审查通过项：
  - 实现迁移的是 Fins direct data command 业务语义，并适配当前 Service/Fins boundary；未搬迁旧 CLI 实现。
  - Fins direct commands 不创建 Host Run，不写 Host EventLog，不伪装 Host wait；CLI 经 `dayu.service.fins_direct` 触达 Fins ingestion runtime。
  - CLI 不直接 import `dayu.fins.storage`；`SourceKind` 依赖属于 accepted plan 允许的 Fins 枚举 / domain value。
  - Service helper 不依赖 CLI stdout/stderr、argparse 或 signal handler，可被后续 WeChat / GUI 复用。
  - Upload wrapper 构造 `FinsUploadFilingRequest` / `FinsUploadMaterialRequest` 并调用 `runtime.start_upload(request)` union API。
  - Fins cancel 语义符合 S5：job id 前本地 130；job id 后第一次 SIGINT 发 `request_cancel(job_id)` 并继续 poll；第二次 SIGINT 本地 130 并打印 job id。
  - `upload_filings_from`、`--infer`、`--ci` 按 accepted plan fail fast / deferred。
  - README 触发、测试覆盖率、pyright 与 diff check 均通过。
- Finding 裁决：
  - MiMo `tests/cli/test_fins_commands.py` 缺少模块级 docstring：rejected-with-reason；源码第 1 行已有模块 docstring。
  - MiMo `_FinsSigintMonitor.notify` 未 `del` 未使用参数：rejected-with-reason；下划线参数用于兼容 signal handler，pyright 0 errors，不构成当前 fix。
  - DS `SUCCEEDED` 输出未展示 `result_summary`：deferred-with-owner；新增 `WU-CLI-01-RR-08`。
  - DS 无 `add_signal_handler` 平台无法提供 durable cancel UX：deferred-with-owner；归入 `WU-CLI-01-RR-06`。
- 验证：
  - `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`：22 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && pytest tests/cli tests/service tests/fins/test_fins_ingestion_runtime.py -q`：195 passed，3 条 edgar deprecation warnings。
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
  - `git diff --check`：clean。
- Accepted implementation commit: `48a97942`。
- 下一步：进入 CLI-01-S6 implementation gate。

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
