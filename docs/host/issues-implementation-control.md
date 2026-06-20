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

每个 work unit 内的 implementation slices 在 discussion / plan 阶段再具体确定；总控阶段不预先替 work units 固定 slice。

slice 切分必须同时满足三个约束：

- 模型上下文窗口与 review 可承载复杂度：implementation agent 必须能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 必须能在一个上下文中有效审查。
- 代码依赖边界：slice 应沿稳定模块 ownership、公共契约、状态机边界、存储边界、projection 边界、issue dependency 边界或测试矩阵边界切分，避免一个 slice 同时跨越过多治理 owner。
- 可独立验证的行为闭环：slice 应大到能形成可测试的语义闭环，小到能一次实现、一次验证、一次 review。除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。

slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理。好的 slice 应当有明确输入、输出、non-goals、allowed files / modules、验证命令、issue handoff 和后续 slice 可依赖的稳定交付物。

如果一个 work unit 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 plan 中说明前后 slice 的 contract handoff。如果某个 slice 需要跨模块修改，plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## 当前状态

| 项目 | 当前值 |
|---|---|
| phase | Host issue-backed follow-up implementation backlog |
| gate | final-closeout-pass |
| implementation status | WU-ENG-02-R1 final closeout pass. Draft PR 159 is open in draft state; before this final closeout record, branch `phase/wu-eng-02-r1` was pushed through `d96dcb65`. Local gate chain completed through PR review, accepted PR review commit, follow-up push, draft-PR-pass, and final closeout. |
| active work unit | WU-ENG-02-R1 |
| default next work unit | WU-ENG-02-R1 |
| next entry point | Await user merge / PR disposition for PR 159. After merge, return to base branch and select the next active work unit from this control doc. |
| design source | `docs/host/design.md` and `docs/engine/design.md` for Host / Engine stream terminology, CLI diagnostics, logging, and UI / Service / Host / Engine ownership boundaries. |
| issue status comments | Active/backlog issue owners retained here: #63 / #70 / #34 / #119 / #71 / #27 / #72 / #75 / #43 / #36 / #78 / #156 / #96 / #38 / #91 / #87 / #88 / #20 / #89 / #90 / #92 / #80 / #115, plus residual-risk destinations #121 / #122 / #129 / #133. Completed WU history, draft PR closeout records, merged PR notes, and closed issue notes are archived in `docs/host/issues-implementation-control-archive.md`. |
| blocking open questions | None for final closeout. |

状态约定：

- `not-started`：尚未进入 plan / implementation。
- `discussion-ready`：已具备讨论和代码 / issue 核对入口，但还未形成 code-generation-ready plan。
- `blocked-by-issue`：需要等待指定 GitHub Issue / umbrella / dependency 完成。
- `obsolete`：已裁决过期失效，不作为实施入口。
- `planning`：正在形成或 review code-generation-ready plan。
- `accepted-plan`：plan / review / re-review 已通过，等待 accepted plan commit 或进入 implementation。
- `implementation`：正在实施或修复。
- `review`：正在进行 code review、re-review 或 aggregate deepreview。
- `accepted-slice`：implementation slice 已通过 code review / re-review，等待 accepted slice commit 或 aggregate deepreview。
- `ready-to-open-draft-PR`：本轮 work unit 已完成本地 gate，等待进入 draft PR gate。
- `draft-PR-pass`：draft PR gate 已通过。
- `final-closeout-pass`：draft PR、PR review、accepted PR review commit、follow-up push、issue closeout handling 和 final closeout summary 均已记录；等待用户 merge 当前 PR 后从 base branch 进入下一 work unit。

## 推进规则

- 每次只推进一个 work unit。
- 先做 GitHub Issue / dependency / 代码核对，再进入方案和实现。
- Work units 必须按依赖顺序推进：底层 Engine / provider contract 优先于依赖该 contract 的 Host / Service / UI follow-up；umbrella issue 优先于其 child issue；dependent smoke 必须等待前置 production capability 完成。
- 已明确 `blocked-by-issue` 或 `obsolete` 的 work unit 不得绕过状态进入 implementation gate。
- 涉及 public contract、durable schema、状态机、跨层依赖或用户可见行为时，必须先形成明确 design decision。
- 测试优先按风险边界补齐；压力测试和长耗时测试必须与常规测试入口分开。
- 实施完成后必须更新对应测试、类型检查、稳定文档说明和对应 GitHub Issue 状态。
- 每个 work unit 进入 plan、implementation、review、ready-to-open-draft-PR 或 draft-PR-pass 时，必须更新“当前状态”中的 gate、active work unit、next entry point 和 blocking open questions；artifact、commit、review 与历史验证记录写入对应 work unit、review artifact 或 closeout artifact，不在“当前状态”表中累积流水账。

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
| WU-TOOLS-01-F01-02-R1 | transferred-to-issue | GitHub Issue #129 | 设计 awaiting 两阶段启动后，才能扩展 Host wait adapter 或 Fins runtime activation contract。 |
| WU-TOOLS-01-F01-02-R2 | deferred-with-owner | WU-WAIT-03 / GitHub Issue #92；provider-specific adapter owners | 由 WU-WAIT-03 统一裁决 external job physical cancel / revoke / abandon；具体 provider/runtime 只在支持时实现物理中断，当前 WU 使用 cooperative checkpoint 与 bounded wait。 |
| WU-TOOLS-01-F03-R4 | transferred-to-issue | GitHub Issue #133 | 评估并调整 Tools Discovery spec 语义：移除 `allow_empty` / `include_read_tools`、`workspace_root` 默认值、Fins read / Doc OLD limits、upload allowlist 归属。 |

## 当前 Work Units

| Work Unit | 状态 | 主题 | Owner / Destination | 当前定位 |
|---|---|---|---|---|
| WU-ENG-02-R1 | discussion-ready | Provider debugging correlation default enablement and fallback diagnostics | GitHub Issue #63 reopened | Active work unit. PR 114 lower-level mechanism exists, but Service / CLI default path still disables `X-Client-Request-Id`; goal confirmation must confirm end-to-end default path, diagnostics, provider response header fallback, and no new config item. |
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
| WU-LIFE-03 | pending | Active cancel watchdog | GitHub Issue #91 / #87 umbrella | Host lifecycle watchdog target |
| WU-GOV-01 | pending | Host governance terminal taxonomy | GitHub Issue #88 | 引入 `REJECTED` |
| WU-CTX-01 | pending | Provider tokenizer / sizing adapter | GitHub Issue #20 | provider/model-aware context sizing；仍有效，需先收敛 budget policy 设计表述 |
| WU-WAIT-01 | pending | Callback endpoint / auth / replay | GitHub Issue #89 | wait callback adapter |
| WU-WAIT-02 | pending | Production poller loop / backoff / fencing / retry | GitHub Issue #90 | production poller loop |
| WU-WAIT-03 | pending | External job physical cancel / revoke / abandon | GitHub Issue #92 / #87 umbrella | WAITING external job lifecycle |
| WU-WAIT-04 | pending-prerequisite | UI / Service production-grade awaiting E2E smoke | depends on #89 / #90 / #92 | dependent smoke，不独立实施 |
| WU-CM-10 | deferred | Conversation Memory eval benchmark | GitHub Issue #80 / #81 follow-up | deferred behind #81；post-#81 memory semantic contract 稳定后再实施 |
| WU-CM-11 | deferred | User Profile Memory durable boundary and cross-session profile | GitHub Issue #115 / #81 child | deferred behind #81；#81 只固定 User Profile 不混入 session Conversation Memory 的边界，跨 session durable profile 独立后续实施 |

## WU-ENG-02-R1 Provider Debugging Correlation Default Enablement And Fallback Diagnostics

### 状态

GitHub Issue #63 reopened on 2026-06-20. Reopen comment:
https://github.com/noho/dayu-agent-r/issues/63#issuecomment-4756101567

本 WU 是 WU-ENG-02 / PR 114 的 reopened follow-up。WU-ENG-02 已完成 lower-level typed `RunnerRequestIdentity`、`ClientCorrelationPolicy`、OpenAI-compatible `X-Client-Request-Id` 映射能力、provider `x-request-id` 采集、Host ingest 与 Tool Trace 投影；但 reopen comment 指出真实 Service / CLI 默认路径没有启用该能力，因此 #63 不能视为端到端完成。

当前 gate 是 `final-closeout-pass`。Goal confirmation、plan gate、plan review、plan-fix、plan re-review、accepted plan commit、implementation、code review、code-review fix、code re-review、accepted slice commit、aggregate deepreview、accepted deepreview commit、push、create draft PR、PR review、accepted PR review commit、follow-up push、draft-PR-pass 和 final closeout 已完成。

Plan artifact:

- `docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md`

Plan review artifacts:

- `docs/reviews/plan-review-20260620-210618.md` by AgentDS
- `docs/reviews/plan-review-20260620-210656.md` by AgentMiMo

Plan fix artifact:

- `docs/reviews/wu-eng-02-r1-plan-fix-codex-20260620.md` by AgentCodex

Plan re-review artifacts:

- `docs/reviews/plan-rereview-wu-eng-02-r1-ds-20260620.md` by AgentDS, conclusion `pass`, blocking findings `0`
- `docs/reviews/plan-rereview-wu-eng-02-r1-mimo-20260620.md` by AgentMiMo, conclusion `pass`, blocking findings `0`

Accepted plan commit:

- `913875da` (`docs: accept WU-ENG-02-R1 plan`)

Implementation artifact:

- `docs/reviews/implementation-wu-eng-02-r1-codex-20260620.md` by AgentCodex

Code review artifacts:

- `docs/reviews/code-review-20260620-213746.md` by AgentDS, conclusion `pass`, blocking findings `0`
- `docs/reviews/code-review-20260620-214050.md` by AgentMiMo, conclusion `pass`, blocking findings `0`

Controller code-review judgment:

- `accepted`：补充 `dayu.host._terminal_diagnostics` 直接测试，覆盖 only provider id、only client id、both ids、both absent、`message=None` 以及 id 截断，降低后续 projection helper 格式回归风险。
- `accepted`：补充双 id 同时存在时的 terminal suffix 格式测试，确保 provider id 与 client correlation id 同时输出且顺序稳定。
- `accepted`：补充 Tool Trace diagnostic 在 `provider_request_id=None`、`client_correlation_id` 存在且 `raw_payload_ref` 存在时保留 `diagnostic_ref=raw_payload_ref` 的测试。
- `accepted`：`message=""` 是当前 production call path 不应传入的边界，但 helper 签名允许 `str`；可用最小逻辑把空字符串按 no-message 处理并用测试锁定，避免 future internal caller 产生前导空行。
- `rejected-with-reason`：`_lost_host_event` 当前不追加 diagnostic suffix 不影响本 WU；direct evidence 显示 `_lost_lifecycle_plan` 当前写入 `provider_request_id=None` 与 `client_correlation_id=None`，且 accepted plan scope 是 failed terminal。该 future sync risk 不在当前 fix 中处理。

Code-review fix artifact:

- `docs/reviews/fix-wu-eng-02-r1-code-review-codex-20260620.md` by AgentCodex

Code re-review artifacts:

- `docs/reviews/code-review-20260620-214954.md` by AgentDS, conclusion `pass`, blocking findings `0`
- `docs/reviews/re-review-wu-eng-02-r1-20260620-215031.md` by AgentMiMo, conclusion `pass`, blocking findings `0`

Final slice validation:

- `pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: `53 passed, 3 warnings`
- `pytest tests/engine/runners/openai/test_request_identity.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py tests/engine/runners/openai/test_runner_diagnostics.py -q`: `38 passed`
- `pytest tests/host/test_terminal_diagnostics.py tests/host/test_read_api_terminal_policy.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q`: `51 passed`
- `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_prompt_command.py -q`: `69 passed, 3 warnings`
- `pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed

Accepted slice commit:

- `150875e9` (`fix: enable provider debugging correlation by default`)

Aggregate deepreview artifacts:

- `docs/reviews/code-review-20260620-215431.md` by AgentMiMo, conclusion `pass`, blocking findings `0`
- `docs/reviews/code-review-20260620-215556.md` by AgentDS, conclusion `pass`, blocking findings `0`

Controller aggregate deepreview judgment:

- `rejected-with-reason`：`runner.http.response` 在 `client_correlation_id=None` 时输出字面量 `None` 与同日志行既有 `provider_request_id=None` 语义一致，不影响状态、持久化或 LLM-facing material；不为可读性微调追加 fix。
- `deferred-with-owner`：`_lost_host_event` / `_cancelled_host_event` 不追加 suffix 是当前 WU scope 内的有意选择；当前 lifecycle plan 不携带 provider/client correlation ids。若后续 WU 让 lost/cancelled lifecycle payload 携带 correlation ids，由对应 WU plan reviewer 复核 terminal projection 同步。

Accepted deepreview commit:

- `c9659dce` (`docs: accept WU-ENG-02-R1 deepreview`)

Draft PR readiness:

- Status: draft PR created.
- Branch: `phase/wu-eng-02-r1`
- Remote: `github`
- PR: https://github.com/noho/dayu-agent-r/pull/159
- Remaining risks: no blocking risks. Deferred projection-sync risk for future lost/cancelled lifecycle payload correlation ids is owned by the future WU that changes those payloads.

PR review artifacts:

- `docs/reviews/pr-159-review-20260620-220319.md` by AgentDS, conclusion `pass`, blocking findings `0`
- `docs/reviews/pr-159-review-20260620-220735.md` by AgentMiMo, conclusion `pass`, blocking findings `0`

Controller PR review judgment:

- `rejected-with-reason`：`client_correlation_id=None` 日志可读性观察与同一日志行既有 `provider_request_id=None` 行为一致，不影响状态、持久化或 LLM-facing material；不进入 fix。
- `deferred-with-owner`：per-model opt-out 不在本 WU 目标内；当前 reopen 要求 default enabled，若未来 provider 证明拒绝该 header，由新的 provider-specific WU 裁决 typed policy 或 opt-out。
- `deferred-with-owner`：lost/cancelled terminal suffix sync 仅在未来 lifecycle payload 携带 correlation ids 时需要，由对应 WU plan reviewer 复核。
- `accepted`：GitHub PR 当前无 reported CI checks；本轮以本地 pytest / pyright / `git diff --check` 作为验证证据，merge 前若仓库启用 CI/branch protection 再按 checks 处理。

Accepted PR review commit:

- `2d1737f1` (`docs: accept WU-ENG-02-R1 PR review`)

Draft PR pass:

- Status: pass.
- PR: https://github.com/noho/dayu-agent-r/pull/159
- Last pushed commit: `2d1737f1`

Final closeout:

- Status: final-closeout-pass.
- PR: https://github.com/noho/dayu-agent-r/pull/159
- PR state at closeout: `OPEN`, draft `true`, mergeable `UNKNOWN`, latest reviews `[]`.
- Branch: `phase/wu-eng-02-r1`
- Branch head before final closeout record: `d96dcb65`
- GitHub checks at closeout: none reported on branch.
- Issue closeout handling: PR body contains `Closes #63`; Issue #63 should close on merge if GitHub auto-close rules apply. No separate issue comment or manual close was performed in this gate.
- Validation retained from accepted slice / PR body: assembly 53 passed, runner 38 passed, Host terminal / Tool Trace 51 passed, Service / CLI 69 passed, pyright 0 errors, `git diff --check` passed.
- Remaining risks: no blocking risks. Non-blocking deferred risk remains limited to future WU changes that make lost/cancelled lifecycle payloads carry provider/client correlation ids; that future WU must re-check terminal projection suffix behavior.

Controller plan-review judgment:

- `accepted`：终端诊断可见性不能留给 implementation agent 二选一；plan 必须收敛到最小 public contract 变更方案，在 Host public projection 边界追加 bounded diagnostic suffix，不修改 durable terminal payload message / payload digest。
- `accepted`：live watcher 与 outbox fallback 是两条独立 projection path；plan 必须要求共享同一 suffix formatting helper，并测试两条路径在 `provider_request_id=None` 且 `client_correlation_id` 存在时输出一致 fallback id。
- `accepted`：用户明确要求 log 中可见，因此 Python runner log 可见性是当前 WU 验收项；plan 必须去掉 escape hatch，要求在既有 `runner.http.response` log site 和既有 log level 上携带 `client_correlation_id`，不新增日志点、日志行或日志等级。
- `accepted`：provider request id header allowlist 缺少当前 issue 直接证据；plan 必须保持当前 `x-request-id` 提取，不把 `x-trace-id`、`x-correlation-id`、`cf-ray` 等 tracing / infrastructure header 伪装为 provider request id。若需要 header diagnostic，只能记录有界安全 header name presence，不输出 header values。
- `accepted`：Tool Trace `diagnostic_ref=None` 当前 validation 允许；plan 必须删除“可能需要 event_id fallback”的过度设计风险，明确不伪造 provider request id 或 diagnostic ref。
- `accepted`：Slice 1 实施前需要基线验证受影响 assembly tests，再区分期望行为变化和 regression。

### Reopen 直接证据

- GitHub Issue #63 当前状态为 `OPEN / REOPENED`。
- Reopen comment 明确：PR 114 已实现底层机制，但真实 CLI 路径未启用；`dayu/service/host_assembly.py` 当前把 `RunnerSpec.client_correlation_policy` 固定为 `ClientCorrelationPolicy.DISABLED`。
- 本地代码核对确认：`dayu/service/host_assembly.py` 的 `_runner_spec_from_model(...)` 当前返回 `RunnerSpec(..., client_correlation_policy=ClientCorrelationPolicy.DISABLED, ...)`。
- 因此 `dayu-cli prompt` 等默认 Service assembly 路径不会向 OpenAI-compatible / mimo-v2.5-pro 发送 `X-Client-Request-Id`。
- Reopen comment 记录实际日志中 `provider_request_id=None`，说明 mimo response 没有通过当前 `x-request-id` 采集路径给出厂商侧 request id；同时因为 client correlation 默认未发送，也没有可提供给 vendor debugging 的 fallback request-level id。

### 目标

- 默认启用 OpenAI-compatible client correlation：不新增配置项，Service / CLI default assembly 不再把 `client_correlation_policy` 硬编码为 `DISABLED`。
- 保持 typed provider policy 边界：default enablement 应通过现有 `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID` 或等价 typed policy 进入 RunnerSpec，不在 Host / Agent / Service 中写 provider 字符串治理分支。
- 保证真实 CLI / Service path 的普通 Agent -> Runner call 默认发送合法 `X-Client-Request-Id`，且仍不传 `safety_identifier`、fake `user_id` 或 UI / Service 用户概念。
- 现有日志 / 诊断 / Tool Trace / terminal diagnostic 中应能看到 `client_correlation_id`；当 `provider_request_id=None` 时，`client_correlation_id` 至少可作为向厂商报障的 fallback id。不得为此新增日志点，也不得为此修改日志等级；实现只能让现有日志或诊断输出携带 / 展示同源字段。
- 若 mimo 或 OpenAI-compatible provider 使用非 `x-request-id` 响应 header，应在 plan gate 核对当前 response header access path 后，补充 provider request id 提取策略或输出有界响应头诊断摘要，避免漏采无法定位。

### 非目标

- 不新增用户配置项或 profile switch 来控制 #63 的默认行为；reopen comment 要求 default enabled。
- 不把 `session_id`、Service 用户身份、UI 用户身份或内部治理 id 伪装成 provider end-user / safety governance field。
- 不改变 WU-ENG-02 已接受的 per-call identity derivation、RunnerRequestIdentity schema 或 provider-call-level correlation id 格式，除非代码核对证明当前格式无法满足 provider header 约束。
- 不在本 WU 实现完整 Tool Trace analyzer；WU-OBS-00 / #70 仍负责 analyzer。
- 不在本 WU 处理 usage observation 是否需要 correlation fields；该 residual 仍由 WU-OBS-00B / #119 裁决。
- 不实现 native Anthropic / Claude Code gateway adapter-specific request id semantics；该 scope 仍属于 #64 或后续 adapter-specific work unit。
- 不为 `client_correlation_id` 新增专用日志事件、额外日志行或提高日志等级；日志可见性必须复用已有 runner / Host / CLI diagnostics 输出边界。

### 验收信号

- Service / CLI default assembly path 的 `RunnerSpec.client_correlation_policy` 默认启用 OpenAI-compatible `X-Client-Request-Id` 映射。
- 受影响 tests 覆盖 default Service assembly 不再产生 `ClientCorrelationPolicy.DISABLED`。
- OpenAI-compatible Runner 在 policy 默认启用且 request identity 存在时发送合法 `X-Client-Request-Id`；policy 显式 disabled 的底层契约测试仍能表达 direct Runner / special path 的关闭行为。
- 现有日志输出能看见 `client_correlation_id`，但不新增日志点、不新增额外日志行、不调整日志等级。
- Tool Trace hot / cold projection 能看见 `client_correlation_id`，且测试覆盖 `provider_request_id=None` 时仍保留 fallback `client_correlation_id`。
- Host ingest / Tool Trace / diagnostics 能保留并展示 `client_correlation_id`；当 `provider_request_id=None` 时，诊断输出明确给出 fallback `client_correlation_id`，而不是只显示空 provider id。
- 若响应 header 中存在 provider request id 的非 `x-request-id` 形式，提取或有界 header diagnostic 能证明是否漏采；不得把完整敏感 header 无界输出到日志或 LLM-facing material。
- README / CLI help / diagnostics docs 按触发规则检查并按需更新。
- 受影响测试、pyright 和 `git diff --check` 通过。

### 初始 allowed files / modules for plan gate

- `docs/host/issues-implementation-control.md`
- `docs/engine/design.md`
- `docs/host/design.md`
- `dayu/service/host_assembly.py`
- Service / runtime assembly tests covering `ServiceOpenHostAssemblyResult` / default RunnerSpec assembly
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/runners/openai/*`
- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- CLI / runtime diagnostics modules and tests if needed for fallback diagnostic display
- README files only if their local update constraints say this user-visible diagnostics/default behavior change belongs there

### Stop conditions

- 如果 goal confirmation 发现 default enablement conflicts with a provider contract, security boundary, or existing config schema invariant, stop before plan and update design/control docs with the evidence.
- 如果 provider response header access is unavailable or would require leaking sensitive headers, plan must define a bounded diagnostic alternative before implementation.
- 如果 implementation would require changing public schema, durable EventLog semantics, or LLM-facing diagnostics wording, plan must call out exact contract and README/doc updates before implementation.

## Retention Issue Dependency / Implementation Order

GitHub Issue #43 是 storage lifecycle umbrella。`WU-RET-00` 已完成并归档，它不再作为 active implementation 入口；当前 active retention children 必须按以下关系裁决依赖和默认实施顺序：

```text
#43 storage lifecycle umbrella
├─ #36 Tool Trace cold JSONL retention
├─ #78 purge_session-driven retention cleanup
│  └─ #156 compaction artifact retention
└─ #96 Audit JSONL retention
```

默认实施顺序：

1. `WU-RET-01` / GitHub Issue #36：先处理 Tool Trace cold JSONL retention。它是 #43 child，不是 WU-OBS-00 / #70 analyzer 前置；analyzer 只能报告 cold trace retention limited signal，不能代替 retention 实施。
2. `WU-RET-03` / GitHub Issue #78：再处理 `purge_session` 驱动的 session-scoped retention cleanup。它定义 purge cleanup owner、可删除对象边界和 destructive cleanup 证明。
3. `WU-RET-04` / GitHub Issue #156：在 WU-RET-03 完成后处理 compaction artifact retention。#156 是 #78 child，不能绕过 purge cleanup 边界独立实现 artifact retention 或新增 Host background scheduler。
4. `WU-RET-02` / GitHub Issue #96：最后处理 Audit JSONL retention，保留 purge tombstone / audit ledger 可验证关联，并避免把 audit JSONL 误用为 purge completion truth。

只有 `WU-RET-04` 对 `WU-RET-03` 有硬前置依赖。`WU-RET-01` 与 `WU-RET-02` 是 #43 下的 sibling storage-governance work units；除非后续 issue / code 核对发现新的共享 contract，二者不互相阻塞。

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

## WU-LIFE-03 Active Cancel Watchdog And Post-cancel Timeout

### 状态

已纳入 GitHub Issue #91；GitHub Issue #87 是 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 active Attempt cancel watchdog target，不单独引入第二套 watchdog runtime。

### 目标

- 复用 #87 的 Host lifecycle watchdog / supervisor，不另建 active cancel 专属 watchdog。
- 裁决 active cancel watchdog owner、timeout policy、Run / Attempt 终态、diagnostic payload、late terminal race 与 session cancel replay 语义。
- 明确 post-cancel timeout 后 Run / Attempt / diagnostic 的收敛路径，以及 first-committer-wins / late rejection 规则。

### 非目标

- 不直接 kill 不属于 Host 管理的外部进程。
- 不把 provider-specific cancel API 硬编码进 Host 核心。
- 不把 scheduler close 设计成 active cancel timeout closeout。

### 验收信号

- provider 卡死、stream 不结束、worker task 不响应 cancellation 时都有可测试 closeout。
- terminal event 与 diagnostic 不重复、不互相矛盾。
- GitHub Issue #87 明确跟踪设计问题、非目标和验收测试；实施前需要先回到 design gate。

## WU-GOV-01 Host Governance Terminal Taxonomy

### 状态

已裁决需要引入 `REJECTED`；后续由 GitHub Issue #88 跟踪设计与实施。

### 目标

- 引入 `RunStatus.REJECTED`，用于表达 Host governance 在执行前或执行外拒绝 Run，而不是复用执行失败语义。
- 裁决 rejected Run 的 canonical EventLog taxonomy，例如是否新增 `RUN_REJECTED`。
- 明确 hard threshold / compact failure / pre-dispatch governance failure 等场景哪些进入 `REJECTED`，哪些仍保留为 `FAILED`。
- 同步 Run status、EventLog reason、projection、public contract、retry / replay 前置条件、outbox / HostEvent 映射、文档与测试。

### 非目标

- 不为单个 failure reason 临时增加状态。
- 不让 Attempt terminal taxonomy 承担 Run-level governance 语义。

### 验收信号

- 用户可见 terminal status 与治理失败 reason 单一、不重叠。
- public contract freeze test 同步更新。

## WU-CTX-01 Provider Tokenizer / Sizing Adapter

### 状态

GitHub Issue #20 当前仍为 OPEN，且 issue body 已对齐 WU-CTX-01 当前 scope。代码核对显示 Host 仍只有 conservative estimator，没有 provider/model-aware sizing adapter；本条仍有效。

### 设计与代码核对

- `docs/host/design.md` 明确 provider tokenizer adapter 是 Host 预算治理的后续精确能力，第一版使用 conservative estimator 与 provider-aware configured limits。
- `docs/host/design.md` 目前存在一处待收敛表述：配置章节说明 `ContextBudgetPolicy` 不暴露 `reserved_output_tokens`，但 Context Governance 章节仍写 `reserved_output_tokens` 是 Host context policy 的显式 typed input。当前代码实际是 ratio-first policy，没有 `reserved_output_tokens` 字段；进入 #20 plan 前必须先裁决并修正设计表述。
- `dayu/host/context_budget.py` 当前模块 docstring 明确是 conservative estimator，不读取 Engine spec、provider overflow payload、metadata 或 extra payload。
- `estimate_context_budget(...)` 当前按文本长度、canonical JSON byte length、message overhead 和 tool schema overhead 估算 token。
- `ContextBudgetPolicy` 当前只包含 `context_window_size`、soft / hard threshold ratio、compaction 次数上限和 `policy_ref`，没有 provider/model-aware tokenizer 或 sizing adapter 字段。
- Engine README 明确 Engine 不做 proactive threshold compaction、provider-aware tokenizer 或 Host budget policy。

### 目标

- 为不同 provider / model 的 token / context sizing 建立 typed adapter 或 compatible estimator boundary。
- 让 proactive compact、reactive compact、RunInputBuilder budget material、compact before / after estimate 和 usage-observation diagnostics 使用同一 sizing abstraction。
- 支持 provider / model dimension selection，但不得在 Context Governance policy code 中硬编码 provider 名称分支。
- 保留 conservative fallback estimator，并在 diagnostics / compact facts / budget traces 中记录 estimator / sizing adapter id 与版本。
- 覆盖中文 / 英文混合财报文本、JSON / table-like excerpts、tool facts、citation / source refs、memory material、compact artifacts 和 tool schema overhead。

### 非目标

- 不在 Context Governance 中硬编码 provider 名称分支。
- 不让 Engine provider 实现反向依赖 Host。
- 不把 compact / retry / proactive threshold governance 移入 Engine。
- 不移除 conservative fallback behavior。
- 不用 metadata 或 extra payload 夹带 sizing decision。

### 验收信号

- Host 有 typed provider/model-aware sizing adapter boundary，并保留 conservative fallback。
- Proactive / reactive compact decisions 使用同一 sizing entrypoint。
- RunInputBuilder budget material、compact before / after estimates 和 usage-observation diagnostics 能引用 estimator id / version。
- Provider / model selection 与 fallback behavior 有明确测试。
- 至少覆盖一个 provider-specific 或 provider-compatible sizing implementation 加 fallback。
- 测试覆盖中文 / 英文混合财报文本、JSON / table-like excerpts、tool facts、citation / source refs 和 tool schema overhead。
- Host / Engine layering tests 继续证明无反向依赖、无 Engine-owned Host compact policy。

## WU-WAIT-01 Callback Endpoint / Auth / Replay

### 状态

research 已写入 GitHub Issue #89；本条后续按 callback adapter -> common `resolve_wait` pipeline 的方向实施。Claude Code 的 background subagent / lifecycle completion 行为可作为参考；Codex 具备 subagent orchestration，但公开 callback / hook surface 不应被假设为稳定生产 primitive。

### 目标

- 设计 callback endpoint 的认证、幂等 replay、payload digest 和错误分类。
- 将 callback 与现有 wait resolve / idempotent replay 语义对齐。
- 明确 callback endpoint 只是 transport adapter：认证、解析、校验 envelope 后调用 Host `resolve_wait`；不得直接写 EventLog、Run、Attempt 或 wait record。
- callback / poller / manual resolve 必须共用同一个 durable wait resolution pipeline。

### 非目标

- 不把 HTTP framework 细节放入 Host 核心。
- 不绕过 durable wait state。
- 不追求 Claude Code background subagent UI parity；本条只跟踪 Host wait completion callback 语义。

### 验收信号

- callback 重放、乱序、摘要不匹配、未知 wait id 都有测试。
- endpoint 层只映射输入，状态裁决仍由 Host wait 语义完成。
- 认证失败、cancelled / lost wait 的迟到 callback、同 key 不同 outcome digest 的 idempotency conflict 都有明确 diagnostic。

## WU-WAIT-02 Production Poller Loop / Backoff / Fencing / Retry

### 状态

已确认是较大的 production feature，并已用 GitHub Issue #90 跟踪。本条实施前仍需回到 design gate 讨论并更新设计真源；当前文档只冻结问题定位与实施方向。

### 目标

- 实现或接入 production poller loop。
- 为 adapter error、rate limit、cancelled abandon 和 repeated not-ready 设计 backoff。
- 防止同一 wait 被并发 poller 重复处理。
- 明确 poller loop 只负责推进 Host wait 状态，不直接向 UI 返回事件；UI / Service 仍通过 `watch_session_events` 观察 `resolve_wait` 产生的 Host events。
- 设计短生命周期 in-flight claim / fencing，防止多 poller 同时 poll / resolve 同一 wait；该 claim 不是 Attempt owner、不是 EventLog truth、不是外部 job owner。

### 非目标

- 不把 poller 做成通用 scheduler God object。
- 不让 backoff 状态污染 wait durable contract。
- 不在本条内实现 callback auth / replay。
- 不在未完成 design gate 前修改设计真源的 poller production 细节。

### 验收信号

- 同一 wait 在多 poller 下不会并发 resolve。
- adapter intermittent failure 不会丢 wait，也不会 tight loop。
- production loop 能后台运行并可被 Host close / supervisor clean stop。
- ready / lost outcome 仍必须通过 common `resolve_wait` pipeline，事件由现有 Host watch path 观察。

## WU-WAIT-03 External Job Physical Cancel / Revoke / Abandon

### 状态

已纳入 GitHub Issue #92；GitHub Issue #87 是共享 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 WAITING external job cancel / revoke / abandon target，不单独引入第二套 watchdog runtime。

### 目标

- 为外部 job 定义 best-effort cancel / revoke / abandon 协议。
- 明确外部取消失败、超时、重复取消和晚到结果的处理方式。
- 复用 #87 的 Host lifecycle watchdog / supervisor，外部 job 作为 WAITING-state watch target；target-specific adapter 只负责 provider cancel / revoke / abandon 能力。

### 非目标

- 不要求所有 provider 都支持 physical cancel。
- 不把外部 job id 当作 Host durable 主键。
- 不另建独立 wait-job watchdog；不得与 #91 的 active Attempt watchdog target 形成两套 runtime。

### 验收信号

- 支持取消和不支持取消的 adapter 都有契约测试。
- late result 与已 abandon / cancelled wait 的 diagnostic 一致。

## WU-WAIT-04 UI / Service Production-grade Awaiting E2E Smoke

### 状态

依赖 WU-WAIT-01 / GitHub Issue #89、WU-WAIT-02 / GitHub Issue #90、WU-WAIT-03 / GitHub Issue #92；不是可独立实施的 work unit。前置能力完成后，本条才作为 production-grade end-to-end smoke 进入 implementation gate。

### 目标

- 增加一条 production-grade public E2E smoke，冻结 UI / Service 正常接入 Host wait governance 的生产工作流。
- 流程覆盖 `open_host` 装配、`ensure_session`、`submit_followup(queue)`、记录 `accepted_run_id`、watch / `get_run` 观察 `WAITING`、生产 poller 或 callback 入口完成 wait resolution、同一 Run 最终产生 terminal `HostEvent` / outbox item。
- 验证 UI / Service 不直接依赖 ToolRuntime、EngineEvent、dispatch row、scheduler internals 或 wait record durable row 作为展示契约。

### 非目标

- 不在本条重新实现 callback endpoint、production poller loop、backoff、fencing 或外部 job physical cancel。
- 不新增 UI 专用 Host 分支。
- 不把 wait record 列表查询提升为普通 UI 必需契约。
- 不接受仅用 manual resolve 或测试私有 durable wait id 桥接完成的 smoke 作为 production-grade 验收。

### 验收信号

- smoke 测试能证明同一个 public watcher 在 Run 进入 `WAITING` 后继续接收由生产 poller / callback 恢复后的 terminal event。
- smoke 测试断言 `get_run(run_id).status == WAITING` 时 UI 可展示等待态，生产 wait resolution 后 Run 继续推进并最终成功。
- offline / reconnect 场景至少通过 outbox 证明 terminal item 可补读。
- 测试代码不从 UI / Service 路径导入 Host 内部 ToolRuntime、dispatch、scheduler 或 durable wait mutation API。

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
