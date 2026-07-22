# Host Issues Implementation Control Archive

## 文档职责

本文档归档 `docs/host/issues-implementation-control.md` 中已经完成、关闭、并入其它 work unit、已通过最终 closeout、经用户裁决算作完成，或依附于已完成 work unit 的 obsolete Host issue-backed work units。

本文档只保留历史实施、裁决、review 与验证留痕，不作为新的实施入口。需要继续推进的 work unit、dependency 和 active residual risk 仍以 `docs/host/issues-implementation-control.md` 为准。

## 归档规则

本次归档基于控制文档当前状态列和用户裁决完成。状态为 `complete`、`completed`、`completed-with-follow-up`、`completed-final-closeout-pass`、`final-closeout-pass`、`closed`、`merged-into`、`draft-pr-pass-final-closeout-passed` 或 `draft-PR-pass-final-closeout-passed` 的条目进入本文档；用户明确裁决算作 completed 的 `draft-PR-pass` 条目也进入本文档。

状态为 `obsolete` 的条目仅在其对应 work unit 已完成并已归档时进入本文档；否则继续留在主控文档作为防误实施留痕。本次归档的 obsolete 条目为 `WU-CM-07`。

状态为 `pending`、`pending-prerequisite`、`pending-parent`、`in-progress-partial`、`deferred` 或仍处于普通 `draft-PR-pass` 等待裁决的条目保留在主控文档。

## Archived Work Units

| Work Unit | 状态 | 主题 | Owner / Destination | 当前定位 |
|---|---|---|---|---|
| WU-ENG-01 | completed | provider_state 与 reasoning_content 写回策略优化 | GitHub Issue #10 | completed；PR 113 已 merge，稳定结论是 provider reasoning roundtrip 为协议要求，不进入 payload behavior change |
| WU-ENG-02 | completed-with-reopened-follow-up | Provider request identity and vendor debugging correlation | GitHub Issue #63 reopened；#64 current shared scope completed, native adapter-specific scope remains open | PR 114 completed the lower-level typed request identity / OpenAI-compatible correlation mechanism, but #63 reopened on 2026-06-20 because Service / CLI default assembly still disables client correlation; active follow-up is WU-ENG-02-R1 in the main control doc. |
| WU-CM-01 | completed | Conversation Memory overall optimization | GitHub Issue #81 closed | F01/F02/F03/F04 complete；无 active WU-CM-01 residual risk |
| WU-CM-01-F01 | completed | Conversation Memory smoke correctness closeout | GitHub Issue #81 / WU-CM-01 final closeout | one-system-message production assembly 与 final public-path validation 已完成 |
| WU-CM-01-F02 | completed | Compact evidence query readability quality closeout | GitHub Issue #81 / WU-CM-01 final closeout；depends on WU-DUR-P01 durable tool-call atoms | compact evidence readability、prompt semantic rewrite 与 production compact instruction contract rescope 已完成 |
| WU-CM-01-F03 | completed | Assistant final answer continuity fidelity closeout | GitHub Issue #81 / WU-CM-01 final closeout | Draft PR #125；无 active residual risk；等待用户 merge decision |
| WU-CM-01-F04 | completed | Proactive compaction manifest-producing test seam closeout | GitHub Issue #81 / WU-CM-01 final closeout; unblocks WU-TOOLS-01 broad Host validation | PR #124 已 merge；`WU-TOOLS-01-S6-R1` 已关闭并从 active 表移除 |
| WU-CM-02 | closed | working_assumptions 生产者语义 | GitHub Issue #81 / WU-CM-01 | 已裁决；reject 旧 `working_assumptions` 独立语义，不单独实施，删除 / 迁移旧字段由 WU-CM-01 schema / projection slice 承接 |
| WU-CM-03 | closed | fact-candidate-only validation failure 策略 | GitHub Issue #81 / WU-CM-01 | 已裁决；fact candidate invalid 必须 fail closed / whole-candidate repair retry，不 partial materialize，独立 WU closed |
| WU-CM-04 | closed | minimum preserve 与 Fins 事实边界 | GitHub Issue #81 / Fins integration | 已裁决；minimum preserve 是 bounded continuity item，不是事实真源，独立 WU closed；后续 Fins integration 继承该边界 |
| WU-TOOLS-01 | draft-pr-pass-final-closeout-passed | Fins / Web / Doc tools migration with shared document foundations | GitHub Issue #82 / #97 / #98；draft PR #123 | all active residual risks have owner / destination；等待用户 merge decision |
| WU-TOOLS-01-F01 | draft-PR-pass-final-closeout-passed | Shared Fins ingestion runtime and download / preprocess awaiting tools | GitHub Issue #82 follow-up; may depend on #89 / #90 / #92 production WAIT hardening as needed；draft PR #126 | shared Fins ingestion service/runtime 与 download / preprocess awaiting tool providers 已完成；等待用户 merge decision |
| WU-TOOLS-01-F01-01 | draft-PR-pass-final-closeout-passed | Fins filelock convergence to dayu.runtime.filelock | WU-TOOLS-01-F01 draft PR preflight follow-up；draft PR #127 | Fins filelock 已收敛到 `dayu.runtime.filelock`；无 active residual risk；等待用户 merge decision |
| WU-TOOLS-01-F01-02 | completed | Migrated tools cancellation propagation and response | WU-TOOLS-01-F01 draft PR preflight follow-up；draft PR #128 merged 2026-06-09 | CancellationToken 传递审计与取消响应已完成；active residual risks R1 / R2 / R3 已在上方 Residual Risk 表归口；PR 128 已 merge |
| WU-TOOLS-01-F01-02-R3 | completed | Retire legacy tool adapter and fix cancellation outcome projection | GitHub Issue #130；PR https://github.com/noho/dayu-agent-r/pull/135 merged 2026-06-11 | legacy adapter 退役、取消结果投影修复和 R3 residual closeout 均已完成；GitHub Issue #130 已在 2026-06-21 按 PR #135 merge 事实关闭。 |
| WU-TOOLS-01-F01-03 | completed | Production Fins CN/SEC download and upload runtime/tool migration | WU-TOOLS-01-F01 draft PR preflight follow-up; absorbs WU-TOOLS-01-F09; draft PR #131 | 已按控制文档裁决归档为 completed；final closeout 见 `docs/reviews/wu-tools-01-f01-03-final-closeout-controller.md`；Issue #129 继续追踪 `start_upload` prepare/activate 后续。 |
| WU-TOOLS-01-F02 | completed | Web CI diagnostics pipeline migration | GitHub Issue #120 under #98 follow-up; PR #132 merged 2026-06-10 https://github.com/noho/dayu-agent-r/pull/132 | Final closeout 已通过；详细历史见 `docs/reviews/wu-tools-01-f02-final-closeout-controller.md`。F02 completion 已完成，F03 前置条件已满足。 |
| WU-TOOLS-01-F03 | completed | Web CI smoke generation | GitHub Issue #120 under #98 follow-up; PR #134 merged 2026-06-10; depends on WU-TOOLS-01-F02 | Final closeout 已通过；详细历史见 `docs/reviews/wu-tools-01-f03-final-closeout-controller.md`。PR #134 已 merge，并已在 2026-06-21 按 PR #132 / #134 完成事实关闭 GitHub Issue #120；Tools Discovery spec 语义后续评估已转移到 GitHub Issue #133。 |
| WU-TOOLS-01-F08 | completed | Documents processor registry naming cleanup | WU-TOOLS-01 post-migration cleanup；PR #135 merged 2026-06-11 | documents 默认 registry builder 已收敛为 `build_documents_processor_registry(...)`，直接调用方 / 导出 / README / tests 已同步，processor 注册行为保持不变。`WU-TOOLS-01-S1-R2` 已关闭；PR #135 已 merge。 |
| WU-TOOLS-01-F09 | merged-into | Fins upload ingestion migration and upload tool | WU-TOOLS-01-F01-03 | 原 upload follow-up 已并入 `WU-TOOLS-01-F01-03`；upload 不再单独实施，CN / SEC upload 与 CN / SEC download 一起进入 shared Fins service/runtime 与 tool 可用性闭环 |
| WU-PROJ-01 | completed | Compact material truth and bounded memory catch-up | GitHub Issue #86；PR #136 merged 2026-06-11 | Residual follow-up completed and merged via PR #136, merge commit `bfdc56133122c66ddef54380b1f5aeab42fd8127`; accepted implementation, review, and closeout commits are recorded in `docs/reviews/wu-proj-01-residual-final-closeout-controller.md`. Issue #86 updated: https://github.com/noho/dayu-agent-r/issues/86#issuecomment-4679701213. Active residual risk table has no WU-PROJ-01 entries. Merge closeout is carried into WU-OBS-SIGNALS-01 preflight. |
| WU-DUR-P01 | completed | EventLog runner-call reconstruction atoms | GitHub Issue #117 closed | runner-call reconstruction atoms 已完成；follow-up 已关闭或转移到 dedicated issue owner |
| WU-OBS-P00 | completed | Runner call input reconstruction signals | GitHub Issue #70 remains open; #117 closed | runner call input reconstruction signals 已完成；full analyzer 仍由 WU-OBS-00 追踪 |
| WU-OBS-SIGNALS-01 | completed | Tool Trace analyzer prerequisite signal contract bundle | GitHub Issues #29 / #30 / #31 / #35 under #70；draft PR #137 | 已按控制文档裁决归档为 completed；前置 signal bundle 完成，WU-OBS-00 状态切换为 pending；详细流水账保留在 review artifacts。 |
| WU-OBS-P01 | merged-into | Tool Trace context budget snapshot signals | WU-OBS-SIGNALS-01；GitHub Issue #29 | Combined into WU-OBS-SIGNALS-01 as context pressure / budget snapshot signal slice. |
| WU-OBS-P02 | merged-into | Tool Trace tool latency signals | WU-OBS-SIGNALS-01；GitHub Issue #30 | Combined into WU-OBS-SIGNALS-01 as tool latency / duration signal slice. |
| WU-OBS-P03 | merged-into | Tool Trace structured failure metadata | WU-OBS-SIGNALS-01；GitHub Issue #31 | Combined into WU-OBS-SIGNALS-01 as structured failure metadata / repair hint signal slice. |
| WU-OBS-P04 | merged-into | Provider protocol partial tool-call trace signals | WU-OBS-SIGNALS-01；GitHub Issue #35 | Combined into WU-OBS-SIGNALS-01 as provider protocol partial tool-call diagnostic signal slice. |
| WU-CM-07 | obsolete | Evidence validation and pinned state cleanup | obsolete / #81 semantic model | 过期失效，不独立推进 |
| WU-CLI-FINS-OBS-01 | completed | Fins direct CLI live event stream / log / UI print residual | 用户裁决；无 GitHub Issue | Replacement implementation final closeout completed locally; residuals R3/R5 closed by WU-CLI-FINS-DIAG-01; CLI session management follow-up transferred to #145 |
| WU-CLI-FINS-DIAG-01 | completed | CLI/Fins diagnostic output policy residual closeout | 用户裁决；无 GitHub Issue | Closed WU-CLI-FINS-OBS-01-R3/R5 locally: runtime/CLI diagnostics use stderr, stdout remains UI/result, Fins output no longer redacts paths as secrets, and Fins direct diagnostics include bounded useful summaries. |
| WU-CLI-SESSION-01 | completed | CLI session management: resume / list / purge and remove `--new-session` | GitHub Issue #145 | Final closeout completed in `docs/reviews/wu-cli-session-01-final-closeout-20260616.md`; draft PR #146 open; Host formally added public `list_sessions`; issue #145 closed on 2026-06-17 after user authorization |
| WU-CLI-ACTIVITY-01 | draft-PR-pass-final-closeout-passed | Prompt / interactive user-visible activity stream UI | GitHub Issue #144 | Final closeout completed in `docs/reviews/wu-cli-activity-01-final-closeout-20260618.md`; draft PR #149 open; PR review and focused PR re-review PASS; residual `WU-CLI-ACTIVITY-01-PR-R1` closed by WU-CM-12 S5 public continuity smoke reconciliation. |
| WU-CLI-INTERACTIVE-RESUME-01 | completed | prompt / interactive existing-session startup resume semantics | 用户裁决；无 GitHub Issue | Final closeout completed locally: prompt does no startup backfill or unfinished-run wait/replay but records displayed terminal cursor; interactive existing-session entrypoints run watcher-first attach/reconnect before REPL, session-scoped Outbox backfill, idle-tail closure, active / queued barrier, and async CLI cursor store. Implementation review PASS from AgentMiMo / AgentDS; validation: `tests/service -q` 110 passed, affected CLI subset 74 passed, `pyright dayu/ tests/ utils/` 0 errors. |
| WU-RET-00 | draft-PR-pass-final-closeout-passed | Host storage lifecycle retention policy | GitHub Issue #43 umbrella | Draft PR #139 open; final closeout / draft-PR-pass recorded. Active #43 children now remain in the main control doc: #36, #78 -> #156, and #96. |
| WU-CM-05 | completed | LLM compaction proposal typed parsing | GitHub Issue #93 / #81 child | #81 已关闭；final closeout completed in `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`；accepted deepreview commit `492e5620` |
| WU-CM-06 | completed | Terminal summary text policy convergence | GitHub Issue #94 / #81 child | #81 已关闭；final closeout completed in `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`；accepted deepreview commit `246cd1c3` |
| WU-CM-08 | completed | Compaction material readability and smoke maintenance | GitHub Issue #95 / #81 child | #81 已关闭；final closeout completed in `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`；accepted deepreview commit `366d8df1` |
| WU-CM-09 | completed | Durable memory snapshot corruption policy | GitHub Issue #41 | #81 已关闭；final closeout completed in `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`；accepted deepreview commit `3e98565d` |
| WU-CM-12 | completed | Conversation Memory design refinement and implementation drift repair | 用户裁决；无 GitHub Issue | PR #150 merged on 2026-06-19. Final closeout completed again on 2026-06-19 after three-way deepreview and focused re-review; proactive recovery diagnostics, reactive recovery catch-up handling, cancellation manifest preservation, and memory projection edge cases are closed. |
| WU-CM-13 | draft-PR-pass-final-closeout-passed | Unified conversation compact pipeline convergence | WU-CM-12-S4-R1 follow-up；无 GitHub Issue | Draft PR #152 open draft. Accepted PR review commit `f2970512` pushed; final closeout recorded in `docs/reviews/wu-cm-13-final-closeout-20260619.md`; `WU-CM-12-S4-R1` and `WU-CM-13-S1-R1` closed. |
| WU-CM-14 | completed | Recent final answer preservation for ordinal follow-ups | CM semantic follow-up；无 GitHub Issue | Local phaseflow completed. Accepted slice commit `921c6219`; aggregate deepreview PASS after deleting dead `_current_only_material_blocks`. Root cause fixed by passing existing floor into compact selection, adding ordinary post-compaction protected raw tail rendering, and repairing reactive frozen material assembly for protected floor semantics. WU-CM-13 subsequently audited the preservation path into shared compact pipeline ownership. |
| WU-CM-15 | draft-PR-pass-final-closeout-passed | Conversation memory public smoke reactive compact and fallback coverage | CM smoke / eval coverage follow-up；无 GitHub Issue | Draft PR #157 open draft. Accepted plan commit `97518e93`; accepted implementation slice commit `572a88df`; pre-PR closeout commit `0fe4e910`; accepted PR review / final closeout commit `5e04a841`. PR review PASS from AgentMiMo / AgentDS with no material findings; final closeout recorded in `docs/reviews/wu-cm-15-final-closeout-20260620.md`. |
| WU-CLI-DEBUG-STREAM-01 | final-closeout-pass | CLI `--debug-stream` per-delta stream diagnostics | GitHub Issue #148 | Draft PR #158 open: https://github.com/noho/dayu-agent-r/pull/158. Final closeout pass recorded in `docs/reviews/wu-cli-debug-stream-01-final-closeout-20260620.md`; PR review PASS from AgentMiMo / AgentDS; accepted PR review commit `c563d4d6` pushed; issue #148 has closeout comment and should auto-close when PR #158 merges. |
| WU-TOOLS-01-F01-02-R1 | completed | Awaiting external job two-phase activation | GitHub Issue #129 / PR #162 | PR #162 已于 2026-06-21 merge，merge commit 为 `ab60aa4d`；Issue #129 同步关闭。本 WU 已完成，不再是 active implementation entry point。 |
| WU-TOOLS-AWAIT-FANOUT-01 | completed | Host ToolRuntime awaiting fanout governance hardening | GitHub Issue #111 / PR #161 | PR 161 merged on 2026-06-21; not an active implementation entry point. GitHub Issue #111 remains OPEN because PR #161 used `Refs #111` rather than `Closes #111`; this is issue hygiene, not a current tool governance blocker in this control doc. |
| WU-TOOLS-01-F03-R4 | completed | Tools Discovery spec semantics cleanup | GitHub Issue #133 / PR #160 | PR 160 merged on 2026-06-21 and issue #133 is closed; not an active implementation entry point. |
| WU-ENG-02-R1 | completed | Provider debugging correlation default enablement and fallback diagnostics | GitHub Issue #63 / PR #159 | PR 159 merged on 2026-06-20 and issue #63 is closed; not an active WU for this branch. |
| WU-LIFE-03 | completed | Active cancel watchdog | GitHub Issue #91 / #87 umbrella / PR #167 | PR 167 merged on 2026-07-04 and issue #91 closed automatically; not an active implementation entry point. 固定 Host-level active cancel watchdog、post-cancel timeout closeout、late terminal race 和 diagnostic 语义。只负责 Host truth / timeout closeout，不负责 tool/provider hard interrupt。 |
| WU-LIFE-04 | completed | Tool execution deadline and #87 watchdog closeout | GitHub Issue #168 / #87 umbrella / PR #169 | PR 169 merged on 2026-07-04 and issue #168 closed automatically; not an active implementation entry point. #87 umbrella follow-up 已确认 `tool_execution_timeout_seconds` 是单次工具调用最长运行时间，取消/收口机制不得覆盖或延长该 deadline。`active_cancel_timeout_seconds` 已从 Host public API 与 internal local execution options 删除。Watchdog scan query optimization 已通过专用 `CANCELLING` Run 查询与 status sequence index 修复。clock/audit diagnostics 与 shared supervisor abstraction 不构成 WU-LIFE-04 之后仍未归属的代码 residual。剩余 #87 关闭前置是 WU-TOOLS-CANCEL-01；WU-TOOLS-CANCEL-01 完成后，#87 umbrella 可关闭。 |
| WU-CLI-SMOKE-01-R1 | completed | Engine delta transient live stream remediation | Draft PR #180 | final-closeout-pass；accepted PR review commit `3900b069` 已 push，最终 Windows checks 均 PASS。PR180-F01 fixed。Post-closeout delivery ownership design 已完成三路最终 re-review；旧的两个 capacity WU 被 `WU-HOST-SESSION-EVENT-DELIVERY-01` 取代。等待用户 / maintainer 手工 merge Draft PR。 |
| WU-HOST-SESSION-EVENT-DELIVERY-01 | completed-final-closeout-pass | Host Session Event Delivery ownership、bounded mailbox 与跨 opener ordering | Draft PR #181；用户明确裁决；无 GitHub Issue | final closeout artifact=`docs/reviews/wu-host-session-event-delivery-01-final-closeout.md`；accepted PR review HEAD checks均PASS；PR保持OPEN/DRAFT，等待用户或maintainer处理。 |
| WU-WAIT-01 | completed | Callback endpoint / auth / replay | GitHub Issue #89 / PR #163 | PR 163 merged on 2026-07-01; not an active implementation entry point. 当前实现提供 Host wait callback typed boundary 与 Service framework-neutral mapper；不包含真实 HTTP route、secret backend、HMAC / bearer verifier、production poller、physical cancel、Engine contract 或 UI surface。 |
| WU-WAIT-02 | completed | Production poller loop / backoff / fencing / retry | GitHub Issue #90 / PR #165 | PR 165 merged on 2026-07-03 and issue #90 closed automatically; not an active implementation entry point. |
| WU-WAIT-03 | completed | External job physical cancel / revoke / abandon | GitHub Issue #92 / #87 umbrella / PR #166 | PR 166 merged on 2026-07-04 and issue #92 closed automatically; not an active implementation entry point. |
| WU-TOOLS-CANCEL-01 | completed | Tool/provider blocking I/O cancellation hardening | follows WU-LIFE-04 / PR #170 | WU-LIFE-04 已完成；accepted plan commit 为 `4723ec61`，S1 accepted slice commit 为 `eda4be1a`，S2 partial hardening commit 为 `29003541`，typed execution capability plan commit 为 `8eddd26b`。S2A1 `contract / declaration / digest`、S2A2 `Host factory wiring`、S2B `Doc process-backed`、S2C `Fins read process-backed`、S2D `Web sync process-backed` 和 S2E `aggregate validation` 均已通过 implementation / validation、AgentMiMo / AgentDS review 或 aggregate deepreview、controller validation 与 controller adjudication。2026-07-05 用户裁决升级的五项必修 hardening：process envelope hint 结构化、Playwright cleanup smoke、Fins XBRL fixture breadth、process envelope contract single-source、process capsule grace tuning，均已通过 residual hardening plan、S1/S2A/S2B/S3/S4、aggregate review、accepted fix、re-review 与 controller adjudication 闭环。Final closeout artifact 为 `docs/reviews/wu-tools-cancel-01-residual-hardening-final-closeout.md`；final accepted commit 为 `ddbcef5b`。PR #170 已于 2026-07-05 merge，GitHub Issue #87 已关闭；WU-WAIT-04 成为下一 implementation entry point。 |
| WU-WAIT-04 | final-closeout-pass | UI / Service production-grade awaiting E2E smoke | depends on #89 / #90 / #92 + WU-LIFE-03 + WU-LIFE-04 + WU-TOOLS-CANCEL-01 / PR #171 | dependent smoke；#89 / #90 / #92、WU-LIFE-03、WU-LIFE-04 与 WU-TOOLS-CANCEL-01 均已完成。Plan commit `35d947ea`、S1 accepted commit `503b2cf5`、S2 accepted commit `d3bdb2c3`。Final closeout artifact 为 `docs/reviews/wu-wait-04-final-closeout.md`。PR #171 was merged on 2026-07-06 with merge commit `19a600e0`; PR body has no `Closes` footer because this WU is not an independent GitHub issue owner. This work unit is no longer an active implementation entry point. |
| WU-CLI-SMOKE-01 | completed | dayu-cli core usability smoke and behavior validation | PR #172 | PR #172 已于 2026-07-09 merge，merge commit 为 `3410d742`。主 WU 已完成；其 R1 / R2 仍按上方 residual table 的独立 owner 与排期处理。 |

## WU-ENG-01 Provider State And Reasoning Content Roundtrip Policy

### 状态

completed。PR 113 已 merge，merge commit 为 `bc50e26c45296171487272ff5fc2293db67a9246`。GitHub Issue #10 当前仍为 OPEN，但 discussion / 代码 / provider API 文档核对后裁决：原先把 `AssistantMessage.reasoning_content is not None` 时写回 outbound `reasoning_content` 视为“无条件写回 bug”的动机被高估。MiMo、DeepSeek、Qwen 等 thinking + tool-call provider 要求把上一轮 assistant 的 `reasoning_content` 原样带回；Gemini 要求把 `thought_signature` 原样带回。因此当前 work unit 不进入 payload behavior change，已收敛为 issue 记录、docstring / 测试说明修正与 provider roundtrip 证据固化。

### 设计与代码核对

- `docs/host/design.md` 仅涉及 Host 如何暴露 thinking / tool events，不拥有 provider-specific reasoning roundtrip 策略。
- `docs/engine/design.md` 已定义 `ToolCallProviderState` 是封闭 provider-specific 联合，当前成员为 `GeminiToolCallState`，用于 Gemini `thought_signature` roundtrip。
- `docs/engine/migration-plan.md` 曾把 Phase 3 的 `reasoning_content` 写回标为过渡实现；本次核对后裁决为：不能在没有 provider API / 真实 smoke 证据证明当前 payload 错误时改动 request / response 行为。
- `dayu/contracts/tool_call.py` 已实现 `GeminiToolCallState` 与 `ToolCallProviderState` 强类型通道。
- `dayu/engine/runners/openai/payload.py` 在 assistant message serialization 中保留非空 `reasoning_content`，该字段来自 provider response / Engine 历史回放，不由 Host 或 payload builder 凭空生成。
- `tests/engine/runners/openai/test_payload_assistant_reasoning_content_preserved.py` 应从“OLD 兼容保留性”改写为“thinking tool-call roundtrip provider requirement”测试说明。
- Provider API 证据：MiMo / DeepSeek thinking mode 在多轮 tool-call 场景要求 assistant `reasoning_content` 原样回传；Qwen thinking tool-call 文档要求发送 tool results 时包含 assistant `reasoning_content`；Gemini thinking / function calling 要求回传 thought signature。

### 目标

- 不改变当前已能运行的 provider request / response payload；只有 API 文档、真实 smoke 或可复现 provider 行为证明当前 payload 错误时，才允许 provider-specific payload 调整。
- 固化 reasoning / thinking roundtrip 证据：MiMo / DeepSeek / Qwen 的 `reasoning_content` 与 Gemini 的 `thought_signature` 是 provider 协议的一部分，不是 Host 治理字段。
- 修正文档和测试描述，避免把正确的 provider roundtrip 行为继续写成“OLD 过渡兼容”或“待删除的无条件写回”。
- 若未来 provider 需要新增 roundtrip state，仍优先通过 `ToolCallProviderState` 封闭联合扩展，或通过 provider adapter 的显式请求投影表达。
- 保持 Runner / Agent / ToolExecutor 边界：Runner 只做 provider payload 投影，不重新执行工具，不依赖 `ToolExecutor`。
- 更新 payload builder docstring、tests 和相关 Engine README，使当前稳定行为按 provider API contract 表述。

### 非目标

- 不把 `reasoning_content` 塞进 `metadata`、裸 dict、`Any` 或 provider 字符串分支。
- 不伪造尚无证据的 provider-specific state。
- 不让 Host / EngineWorker 的治理所有权进入 `provider_state`。
- 不让 Engine 反向依赖 Host / Service / UI / Fins。
- 不在本条内实现 Host ToolRuntime、WAIT、memory、context governance 或 UI behavior。

### 验收信号

- 每个 provider 的 reasoning roundtrip 策略有明确证据来源。
- 当前已能运行的 MiMo / DeepSeek / Qwen / Gemini request / response 行为不被改变。
- MiMo / DeepSeek / Qwen 的 `reasoning_content` roundtrip 与 Gemini 的 `thought_signature` roundtrip 在 docstring / tests 中被明确为 provider API requirement。
- `ToolCallProviderState` 仍是封闭强类型联合；新增成员时所有 parser / serializer match 分支穷尽。
- 相关 tests 从“OLD 兼容保留性”改为 thinking tool-call roundtrip requirement 测试。
- pyright 不新增或扩散类型错误。

## WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation

### 状态

GitHub Issue #63 曾按 WU-ENG-02 / PR 114 accepted scope 关闭，关闭依据是 OpenAI-compatible provider debugging correlation 的 lower-level typed mechanism 已完成。2026-06-20 复查 PR 114 后，#63 reopen：真实 Service / CLI 默认路径仍把 `RunnerSpec.client_correlation_policy` 装配为 `DISABLED`，因此默认 `dayu-cli prompt` 不发送 `X-Client-Request-Id`；当 provider `x-request-id` 缺失时，用户仍拿不到可报给厂商的请求级 fallback id。该 reopened scope 不修改本归档条目的历史完成事实，后续由主控文档中的 active `WU-ENG-02-R1` 承接。GitHub Issue #64 保持 OPEN；WU-ENG-02 已完成 #64 在当前仓库可实施的 shared typed request identity / provider policy boundary scope，剩余 native Anthropic response `request-id` 与 Claude Code gateway `X-Claude-Code-Session-Id` 行为属于未来 native adapter-specific scope。两条 issue 的共同目标不是引入用户治理字段，而是：当 `tool trace analyze` 发现 provider/model 行为疑似 bug 时，分析报告里必须能给出 provider 厂商可定位的 request id，并能回链到本地 `run_id` / iteration / attempt / tool trace。

Plan gate 已完成，artifact 为 `docs/host/wu-eng-02-provider-request-identity-plan.md`，无 blocking open questions。Plan review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings` 且无 blocking open questions。Plan fix gate 已完成，artifact 为 `docs/reviews/wu-eng-02-plan-fix-codex.md`，8 条 accepted findings 均标记已修复。Plan re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条未修复 / 部分修复，无新增 blocking issue。当前 plan 已接受，accepted plan commit 为 `59f66b7`。Implementation Slice 1（Engine contract and Agent identity）已由 AgentCodex 实施，artifact 为 `docs/reviews/wu-eng-02-slice1-implementation-codex.md`；验证结果为 127 个受影响 Engine tests passed，pyright 0 errors。Slice 1 code review gate 已完成，AgentMiMo 裁决 `pass`，AgentDS 裁决 `pass-with-findings`，均无 blocking open questions。当前进入 Slice 1 fix gate。

Slice 1 code review findings 裁决：

- accepted：EngineEvent / Agent outcome 中的 `client_correlation_id` 值缺少直接断言；应在现有 Engine Agent 测试中补齐关键 emitted event 的 correlation id 断言。
- accepted：`_validate_batch_bijection` 生成的 `RunFailedData` 未携带当前 tool batch 的 `client_correlation_id`，与同一路径 duplicate 检查不一致；应传入并写入该字段。
- rejected-with-reason：`RunnerRequestIdentity.__post_init__` 与 builder 重复校验属于防御性冗余，直接构造路径需要保留，不要求修改。
- rejected-with-reason：canonical part 编码方案已由类型前缀与长度前缀证明无歧义，不要求修改。
- deferred-with-owner：OpenAI header policy、Host projection / ingest、Tool Trace、README sync 按 accepted plan 进入 Slice 2 / Slice 3 / Slice 4。

Slice 1 fix gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice1-fix-codex.md`。两个 accepted findings 均标记已修复；验证结果为 127 个受影响 Engine tests passed，pyright 0 errors。Slice 1 re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条未修复 / 部分修复，无 blocking open questions。Slice 1 accepted commit 为 `c4826e0`。Slice 2 implementation gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice2-implementation-codex.md`；验证结果为 61 个受影响 tests passed，pyright 0 errors。Slice 2 code review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，无 blocking open questions。Slice 2 fix gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice2-fix-codex.md`；已补充 `ClientCorrelationPolicy.DISABLED` 且 `request_identity=None` 时不发送 `X-Client-Request-Id` 的直接测试；验证结果为 40 个受影响 tests passed，pyright 0 errors。Slice 2 re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条 blocking findings；本地复验 `pytest tests/engine/runners/openai/test_request_identity.py tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_effective_execution_config.py` 结果为 62 passed，pyright 0 errors。Slice 2 accepted commit 为 `c3856b9`。Slice 3 implementation gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice3-implementation-codex.md`；验证结果为 184 个受影响 Host tests passed，pyright 0 errors。Slice 3 code review gate 已完成，AgentMiMo 裁决 `pass-with-findings`，AgentDS 裁决 `pass`，0 条 blocking findings；Controller 裁决无 accepted fix，新增 residual risks `WU-ENG-02-S3-R1` / `WU-ENG-02-S3-R2`。Slice 3 accepted commit 为 `5ddc4cb`。Slice 4 implementation gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice4-implementation-codex.md`；验证结果为 174 个 Engine tests passed、198 个 Host tests passed，pyright 0 errors。Slice 4 code review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条 blocking findings；Controller 裁决无 accepted fix，并关闭 `WU-ENG-02-S2-R1`。Slice 4 accepted commit 为 `896d483`。Aggregate deepreview gate 已完成，AgentMiMo 裁决 `pass-with-findings`，AgentDS 裁决 `pass`，0 条 blocking findings；Controller 裁决无 accepted fix，existing residual risks 均已有 owner。Accepted deepreview commit 为 `24af62b`。WU-ENG-02 draft PR 已创建：`https://github.com/noho/dayu-agent-r/pull/114`。PR review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条 blocking findings，PR diff 与本地 diff 一致，372 tests passed，pyright 0 errors。Accepted PR review commit 为 `824665c`。用户裁决 residual risks 若无硬性 defer 理由则在 PR 114 内关闭；residual risk fix gate 已由 AgentCodex 完成，artifact 为 `docs/reviews/wu-eng-02-residual-risk-fix-codex.md`。`WU-ENG-02-S1-R1`、`WU-ENG-02-S1-R2`、`WU-ENG-02-S2-R2`、`WU-ENG-02-S3-R2` 已改为 closed；`WU-ENG-02-S3-R1` 保留 deferred-with-owner，理由是需要 WU-OBS-00 / GitHub Issue #70 先扩展 usage observation / analyzer signal contract。Residual risk review gate 已完成，AgentMiMo 裁决 pass，AgentDS 裁决 pass-with-finding；Controller 接受 DS 低严重度测试覆盖 finding。Residual risk review fix gate 已完成，artifact 为 `docs/reviews/wu-eng-02-residual-risk-review-fix-codex.md`；已补齐第三个工具超时变体的 `client_correlation_id` 断言，验证结果为 125 tests passed，pyright 0 errors。Residual risk re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 pass，0 条 blocking findings；Controller 最终复验 125 个受影响 tests passed、71 个相关回归 tests passed、pyright 0 errors。Residual risk accepted commit 为 `8298958`。Residual Risk Reconciliation 已完成，artifact 为 `docs/reviews/wu-eng-02-residual-risk-reconciliation.md`；已关闭的 residual risk 已从 active residual 表删除，当前仅保留 `WU-ENG-02-S3-R1`，且 owner 为 WU-OBS-00 / GitHub Issue #70 analyzer。GitHub Issue #63 已关闭；GitHub Issue #64 已更新说明当前 shared contract scope 已由 PR 114 完成，native Anthropic / Claude Code gateway adapter-specific scope 继续保留。PR 114 已于 2026-06-03 09:33:38 UTC merge，merge commit 为 `58fb7a42a2a096ab279863250a9ffe63f63f0edc`。当前状态为 completed；后续入口已转入 WU-CM-01。

Slice 2 code review findings 裁决：

- accepted：补充 `ClientCorrelationPolicy.DISABLED` 且 `request_identity=None` 时不发送 `X-Client-Request-Id` 的直接测试。
- rejected-with-reason：`_has_client_request_id_header` 的 `:raises Exception: 不主动抛出异常。` 符合本仓库中文 docstring 异常说明风格，不要求修改。
- rejected-with-reason：`_build_request_headers` 的不可达 `ValueError` 是枚举扩展时的 fail-fast 防御分支，保留。
- deferred-with-owner：production assembly 默认 `DISABLED`、静态 header 冲突 `ValueError` 是否需上层结构化收口，交由 Slice 3 / aggregate review 裁决。

Slice 3 code review findings 裁决：

- deferred-with-owner：usage observation payload 不含 `client_correlation_id`。当前 `UsageReportedData` Engine contract 不含该字段，且该 projection signal 的 `provider_request_id` 是 hardcoded `None`，不属于本 Slice provider-related EngineEvent payload 主链路；若 issue-70 analyzer 需要该信号，交由 WU-OBS-00 / analyzer gate 先扩展 contract。
- rejected-with-reason：`CONTEXT_COMPACTION_REQUESTED` payload 通过 dict spread 附加 `client_correlation_id` 当前符合 plan，因为 context compaction builder / validator 负责 base payload，Host ingest 附加诊断字段不改变 base schema；未来若 builder 引入 strict whitelist，再由对应变更同步处理。
- rejected-with-reason：`_close_worker_lifecycle` 合成 `RunFailedData` 未显式传 `client_correlation_id=None` 只有风格差异，运行时语义与默认值一致，不进入 fix。
- rejected-with-reason：`_TerminalPlan` 无默认值而 `TerminalCloseoutInput` / `ContextRecoveryCloseInput` 有默认值是合理边界差异：内部 plan 强制调用方显式思考，run_transition 公共输入保持可选字段默认 `None`。
- deferred-with-owner：`ContextRecoveryCloseInput.client_correlation_id` 是否需要专用 validation / payload 单测交由 Slice 4 final validation 核对；当前间接覆盖与对称校验足以通过 Slice 3。

Plan review findings 裁决：

- accepted：force-answer / continuation / fallback 等所有 logical Runner call 都必须递增 `runner_call_index`，并补计划测试要求。
- accepted：`request_identity: RunnerRequestIdentity | None` 只允许 direct Runner / compactor 等非普通 Agent path 显式传 `None`；普通 Agent -> Runner call path 必须传 non-None identity，计划完成信号需改写。
- accepted：`AsyncRunner.call` 只新增 keyword-only `request_identity`，保留 `messages/options/tools` 位置参数以最小化变更。
- accepted：计划需避免 `_AsyncAgent` 重复散落 correlation 取值逻辑，优先模块级 helper 或 iteration state。
- accepted：`EngineRunOutcomeFailed` 应明确归类为 `AgentRunResult` outcome，不是 EngineEvent data class。
- accepted：`client_correlation_id` digest 长度需明确为完整 SHA-256 hex，即 `dayu-` + 64 hex。
- accepted：`ClientCorrelationPolicy` docstring 需说明 enum 是 provider-protocol-specific outbound mapping policy，不是 provider 名称分支。
- rejected-with-reason：`iteration_id` 与 `run_id` digest input 冗余不要求修改；冗余不影响正确性，且保留 `run_id` 作为本地根关联更贴合 issue-63 / issue-64。

### 设计与代码核对

- `docs/host/design.md` 已要求普通 Run 的 request metadata 可包含必要的 `client_request_id`、actor / source refs，但没有把 provider request identity 下沉成 Runner 公共契约。
- `AsyncRunner.call(messages, options, tools)` 当前没有 per-call request context；Agent 虽然拥有 `session_id` / `run_id` / `iteration_id`，但调用 runner 时只传 messages、options、tools。
- OpenAI-compatible runner 当前通过 response header `x-request-id` 提取 `provider_request_id`，并通过 RunnerEvent / Engine ingest / Tool Trace 热表进入本地诊断链路。
- OpenAI-compatible runner 当前构造 request headers 时只能合并 `RunnerSpec.headers`；`RunnerSpec.headers` 是 construction-time provider 配置，不适合写入 per-run / per-attempt 的动态 request id。
- 当前仓库没有 native Anthropic runner；#64 不能落成散落在 Host / Agent 里的 Anthropic 字符串分支，应先通过 provider capability / adapter policy 表达 native Anthropic 与 Claude Code gateway 的差异。
- 设计讨论记录：`run_id` 适合作为本地排障根 ID；`attempt_id` 更接近一次 Host 执行尝试，但仍不一定等于单次 provider HTTP 请求。tool calling 场景下同一 Attempt 可能包含多轮 iteration；runner transport retry 也可能产生多次 provider call。因此是否直接使用 `run_id`、`attempt_id` 或派生值，不在本总控提前定死，应在实施 plan gate 根据代码中的 Attempt / iteration / runner retry 边界确定。

### 目标

- 引入强类型 per-call Runner request identity / correlation context，由 Agent 在每次 runner call 时基于 `run_id`、iteration、attempt 或等价 execution context 构造，并传给 Runner。
- request identity 设计应保留 `run_id` 作为本地根关联，优先评估以 `attempt_id` + iteration / provider call index 派生 provider-call-level client correlation id；具体格式留到实施时结合真实 ID 约束、长度限制和 retry 语义裁决。
- 明确本地分析链路：`tool trace analyze` 输出能从 tool trace / terminal diagnostic 找到 provider-native request id，并回链到本地 `run_id` / iteration / attempt。
- OpenAI-compatible provider 在显式 capability / policy 允许时，把 per-call correlation id 映射为 `X-Client-Request-Id`，并继续采集响应 `x-request-id`。
- Anthropic native provider 的目标是采集响应 header `request-id`；Claude Code / gateway 场景只有在显式兼容模式开启时才映射 `X-Claude-Code-Session-Id`。
- 未来若公共契约显式提供 opaque end-user / actor id，可再映射 OpenAI `safety_identifier` 或 Anthropic `metadata.user_id`；当前不从内部 `session_id` 推导。

### 非目标

- 不把 `session_id`、`run_id` 或 UI / Service 用户概念伪装成 provider 的 end-user governance field。
- 不把 per-run / per-attempt 动态 ID 写进 `RunnerSpec.headers`。
- 不在 Host / Agent 中写 `if provider == "openai"` / `if provider == "anthropic"` 这类硬编码分支。
- 不要求本 work unit 同时实现 native Anthropic runner；若没有 native runner，先完成公共契约、adapter policy 与测试替身。
- 不改变 `RunnerEvent` 不携带 session/run ownership 的边界；关联应由 Agent / Host ingest 在 execution context 内完成。

### 验收信号

- Runner 公共契约有强类型 request identity / correlation 输入，且测试覆盖 Agent 传递、Runner 消费与无动态 ID 时的行为。
- 实施 plan 明确记录 client correlation id 的来源选择：裸 `run_id`、裸 `attempt_id` 或派生 provider-call-level ID，并说明为什么不会在多 iteration / retry 场景造成厂商定位歧义。
- OpenAI-compatible 请求在 policy 开启时包含合法 `X-Client-Request-Id`；值必须满足 provider 约束，例如 ASCII 与长度上限。
- provider response request id 继续被采集，并能在 tool trace analyze / diagnostic query 中与本地 run / attempt / tool trace 关联。
- Anthropic native / Claude Code gateway 的 request id / session header 语义在 adapter policy 中分开，不会误传 `metadata.user_id` 或普通 Anthropic API 不需要的 session header。
- 代码不出现新增 raw provider string 硬编码治理分支、裸 dict payload bag 或 fake user id。
- 相关 Engine / Host / Tool Trace analyzer tests 与 pyright 通过。

## WU-CM-01 Conversation Memory Overall Optimization

### 状态

GitHub Issue #81 当前是 Conversation Memory 整体优化 umbrella issue。Issue body 明确它不是 code-generation-ready implementation plan；本 work unit 是将 #81 通过 phaseflow / gateflow 转化为可实施 scope、plan、slices、review 和验收闭环的正式入口。

GitHub Issue #80 是 Conversation Memory 的评测标准真源。#80 的具体 eval 实现可以等待 #81 完成或形成稳定 post-#81 memory contract 后推进，但 #80 定义的评测维度会反过来约束 WU-CM-01 / #81 的设计：任何 WU-CM-01 design / plan 都必须说明 #80 的评测维度哪些由当前 scope 满足、哪些 deferred-with-owner、哪些是 explicit non-goal。若某个 #81 方案让 #80 的核心评测维度不可测试、不可审计或不可实现，必须先回到设计讨论修正。

WU-CM-01 的实施设计真源为 `docs/host/design.md` 的 `24. Conversation Memory` 与 `25. Context Governance`。plan、implementation、review、fix 与 re-review 不得从讨论稿、旧代码或 GitHub Issue body 重新解释 compact I/O、memory snapshot、prompt assembly、compact repair / fallback 或 context governance 边界；若发现第 24 / 25 章仍不足以生成 code-generation-ready plan，必须先回到 Host 设计真源修正，再更新本文档。

Plan gate 已完成，artifact 为 `docs/host/wu-cm-01-conversation-memory-plan.md`。Plan review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`；Controller 接受 6 组 plan fix findings，裁决 artifact 为 `docs/reviews/wu-cm-01-plan-review-controller-adjudication.md`。Plan fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-plan-fix-codex.md`；accepted fix scope 是补齐 issue-80 评测维度映射、旧 continuity / compact candidate / material section / quality checker 迁移规则，以及 slice 可编译性验证边界。Plan re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-plan-rereview-controller-adjudication.md`。Accepted plan commit 为 `14d28009`。Implementation gate 预检由 AgentCodex 停止，artifact 为 `docs/reviews/wu-cm-01-implementation-codex.md`；直接证据显示当前 plan 的概念域 Slice 1-5 不是可编译闭环，若直接实施会违反 pyright 硬约束。Plan reslice fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-plan-reslice-fix-codex.md`。Plan reslice re-review gate 已完成，AgentMiMo 裁决 `pass`，AgentDS 裁决 `pass-with-findings`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-plan-reslice-rereview-controller-adjudication.md`。Plan reslice accepted commit 为 `a92416ec`。Slice A implementation gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-a-implementation-codex.md`；验证结果为 100 focused tests passed，pyright 0 errors。Slice A code review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`，0 条 blocking finding；Controller 接受 `__all__` 导出、vNext label contract 去重、material mapping 独立测试三类 fix，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-a-code-review-controller-adjudication.md`。Slice A fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-a-fix-codex.md`；验证结果为 105 focused tests passed，pyright 0 errors。Slice A re-review gate 已完成，AgentMiMo 裁决 `pass`，AgentDS 裁决 `fix-accepted`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-slice-a-rereview-controller-adjudication.md`；Controller 复验 105 focused tests passed，pyright 0 errors。Slice A accepted commit 为 `f060853d`。Slice B implementation gate 触发 allowed-files blocker，artifact 为 `docs/reviews/wu-cm-01-slice-b-implementation-codex.md`；直接证据显示 reactive accepted compaction closeout owner 是未列入 Slice B allowed files 的 `dayu/host/engine_ingest.py`，且 proactive subsequent run input failure 属于 Slice C/D 的 memory projection / RunInputBuilder 消费边界。Controller 接受 blocker，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-blocker-controller-adjudication.md`。Slice B plan fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md`。Slice B plan fix re-review gate 已完成，AgentMiMo 裁决 `pass-with-risks`，AgentDS 裁决 `pass-with-findings`，Controller 接受 4 项 plan clarification finding，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-controller-adjudication.md`。Slice B plan fix follow-up gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-b-plan-fix-followup-codex.md`；accepted clarification 包括 `engine_ingest.py` 非 closeout 旧 import / annotation 边界、proactive subsequent run input 测试归属、vNext artifact writer shared helper 策略，以及 `tests/host/test_engine_ingest_mapping.py` 的 Slice B 受限测试范围。Controller 接受 follow-up，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-plan-fix-followup-controller-adjudication.md`。Slice B implementation gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-b-implementation-codex.md`；Controller 复验 270 focused tests passed，pyright 0 errors。Slice B code review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`，0 条 blocking finding；Controller 接受删除 `context_events.py` 旧 compact payload dead helper 与修正 vNext 测试命名 / 断言两项 fix，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-code-review-controller-adjudication.md`。Slice B fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-b-fix-codex.md`；Controller 复验 270 focused tests passed，pyright 0 errors。Slice B re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条 blocking finding；Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-rereview-controller-adjudication.md`。Slice B accepted commit 为 `74fbb5e6`。Slice C implementation gate 触发 allowed-files blocker，artifact 为 `docs/reviews/wu-cm-01-slice-c-implementation-codex.md`；直接证据显示旧 `ConversationMemorySnapshot` / `MemoryProjectionPolicy` 的 production consumers 分布在 `run_input.py`、`compact_material.py`、`dispatch.py`、`service/host_assembly.py`、`runtime/config_loader.py` 与多份非 Slice C 测试中，当前 Slice C allowed files 无法形成 pyright-clean closure 且不能通过兼容桥绕过。Controller 接受 blocker，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-c-blocker-controller-adjudication.md`。Slice C plan fix/reslice gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-fix-codex.md`；plan 选择扩大 Slice C 为 memory contract / projection / prompt assembly / dispatch / config assembly 的 pyright-clean vertical slice，直接纳入 blocker 证明的 production consumers 与 tests，禁止兼容 wrapper、re-export、old-field alias 和旧 snapshot -> vNext bridge helper。Slice C plan fix re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`，0 条 blocking finding；Controller 接受 material contract、config field inventory、config file boundary、memory repair test 与 durable fail-fast clarification，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-controller-adjudication.md`。Slice C plan fix follow-up gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-fix-followup-codex.md`；Controller 接受 follow-up，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-fix-followup-controller-adjudication.md`。Slice C plan boundary follow-up gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-boundary-followup-codex.md`；Controller 接受 boundary follow-up，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-boundary-followup-controller-adjudication.md`。Slice C implementation blocker 已由 Controller 接受，artifact 为 `docs/reviews/wu-cm-01-slice-c-implementation-blocker-controller-adjudication.md`；本次 engine ingest / context governance boundary follow-up 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-c-engine-ingest-context-governance-boundary-followup-codex.md`，只补 `engine_ingest.py`、`context_governance.py`、`test_engine_ingest_mapping.py`、context governance 现有测试覆盖说明与测试命令，未触碰 production code、tests、schema、config JSON 或 README，未创建 Slice C implementation commit。Compact contract closure plan gate 已完成，artifact 为 `docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md`；plan review gate 已完成，AgentMiMo 裁决 `pass-with-findings`，AgentDS 裁决 `pass-with-findings`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-controller-adjudication.md`；plan fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-compact-contract-closure-plan-fix-codex.md`；plan re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-compact-contract-closure-plan-rereview-controller-adjudication.md`。下一入口为 WU-CM-01 compact contract closure implementation gate。

### 目标

- 将 Conversation Memory 的语义类型与 prompt assembly / deterministic bounded selection policy 分离，避免继续把 `stable layer`、`history pool`、`recent raw turns floor` 这类预算策略当作顶层 memory 心智模型。
- 固定 Memory Truth / Store、Conversation Memory Projection、Prompt Assembly 与 Context Governance 边界：EventLog / artifacts / accepted evidence 保持真源地位，memory snapshot 保持 bounded read model，不成为新的事实真源，Context Governance 只负责编排 compact / fallback / budget governance，不直接写 memory projection。
- 裁决并实现 #81 scope 内优先级最高的语义 memory 能力，例如 Trace Memory、Evidence / Fact Memory、Session Summary Memory、Answer Anchor Memory 与 Forward Intent Memory；User Profile Memory 只在 #81 固定“不混入 session Conversation Memory”的边界，跨 session durable profile 设计与实施交给 WU-CM-11 / GitHub Issue #115。
- 将 WU-CM-02、WU-CM-03、WU-CM-04 等已并入 #81 的问题纳入统一 semantic model 裁决，不再对旧 memory shape 做局部补丁。
- 为 compact repair 固定策略：采用 whole-candidate repair retry；一次 repair attempt 可以向 LLM 提供多个 Host-neutral invalid reasons / validation issues，但必须重新产出完整 candidate。Host 不要求 LLM 返回 repair patch，不合并旧 proposal 的 valid fields 与新 patch；只有完整 candidate 通过 JSON/schema/value mapping、provenance、quality check 与必要预算闸门后，才可写 `CONTEXT_COMPACTED`。
- 明确第一阶段不做 prompt-conditioned recall、semantic search、vector recall、LLM reranker 或 recall tool；deep historical recall / semantic search 由 GitHub Issue #39 承接。
- 以 GitHub Issue #80 的分层评测标准约束语义设计，确保 Memory Truth / Store、Memory Projection、Prompt Assembly 与 Agent Outcome 都保留可审计、可断言的验证入口。
- 产出 code-generation-ready plan，明确 slices、allowed files / modules、schema / contract 变更、测试矩阵、migration strategy 和 residual risk owner。

### 非目标

- 不把 #81 issue body 直接当作 implementation plan。
- 不一次性实现所有 speculative memory 能力；必须按可验证闭环切 slice。
- 不让 assistant final answer、summary、answer anchor、user claim 或 user profile 自动升级为 evidence-backed facts。
- 不让 memory snapshot 替代 EventLog / artifacts / accepted evidence。
- 不在 WU-CM-01 内实现跨 session User Profile Memory；durable profile store、profile update event、privacy / reset / deletion、supersession、confidence、confirmation policy 和用户可见解释由 WU-CM-11 / GitHub Issue #115 独立跟踪。
- 不在 WU-CM-01 内实现 prompt-conditioned recall、semantic search、vector recall、LLM reranker 或 recall tool；deep historical recall / semantic search 由 GitHub Issue #39 承接。
- 不在 #81 内直接落地完整 #80 eval benchmark；#80 的实现等待稳定 post-#81 memory contract，但其评测标准立即约束 #81 设计。
- 不为旧 `pinned_state` / `working_assumptions` 结构保留兼容 wrapper 或局部止血。

### 验收信号

- #81 被拆成 code-generation-ready phase plan 和可 review 的 implementation slices。
- #81 的 design / plan 明确映射 #80 评测维度：每个维度必须标记为 current scope satisfied、deferred-with-owner 或 explicit non-goal。
- 设计真源明确 semantic memory categories 与 prompt assembly / deterministic bounded selection policy 的边界。
- User Profile Memory 在 #81 中被标记为 deferred-with-owner，并指向 WU-CM-11 / GitHub Issue #115；session Conversation Memory 不伪装、内嵌或兼容实现跨 session profile。
- tests 能区分 trace continuity、evidence-backed facts、session summary、answer anchors、forward intent、profile boundary 和 prompt assembly bounded behavior。
- compact repair 测试覆盖多个 invalid reasons 触发一次 whole-candidate repair retry、rejected candidate 不被部分采用、完整 candidate 重新通过全量 revalidation、repair exhausted fail closed。
- 现有 `utils/` 下的 Host public smoke 必须通过，作为 WU-CM-01 的初步验收标准；至少覆盖 `utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_conversation_memory_scenarios.py` 与 `utils/smoke_host_public_multiturn.py`，后续若 smoke 脚本新增、拆分或改名，WU-CM-01 plan 必须同步列出实际验证命令。
- deep historical recall / semantic search / recall tool 若进入后续 scope，必须由 GitHub Issue #39 先形成 research artifact 和明确 design constraints。
- WU-CM-01-F01、WU-CM-01-F02、WU-CM-02、WU-CM-03、WU-CM-04、WU-CM-05、WU-CM-06、WU-CM-08、WU-CM-11 的后续状态被更新为 closed、deferred-with-owner 或 transferred-to-issue。

## WU-CM-01-F01 Conversation Memory Smoke Correctness Closeout

### 状态

GitHub Issue #81 / WU-CM-01 final closeout follow-up。Host public smoke 用于验证 Conversation Memory 与 Host 整体设计是否在 public path 上成立；如果 smoke 输入、断言或观测点本身偏离设计真源，就无法提供有效验收信号。本条作为 WU-CM-01 的 smoke correctness 收尾追踪项，不占用已有 WU-CM-05 编号。后续若继续发现这些 smoke 自身不符合设计验证目的的问题，统一在本条追踪，而不是散落到新的编号。

### 当前已知修正项

- 2026-06-05 Host public conversation memory smoke 的 round1 final Runner-call messages dump 显示当前有两条 `system` role message：一条为 scene / behavior prompt，一条为 Host execution context。协议层面这不是非法 messages，但 smoke 作为 public conversation memory 验收入口，应收敛到一个 `system` role message，降低 provider-compatible 路径的歧义。
- 2026-06-05 round2 compact 后 Runner-call dump 发现观测闭环不一致：`workspace/tmp/smoke01.log` 中 round2 `runner_call_start` 记录 `message_count=9`，但从当前 durable DB + EventLog 重建 cursor=121 的 memory / compact 投影只能得到 7 条 messages。round2 是 Conversation Memory compact 后 public path 验收点；smoke / dump 必须能解释或直接验证这 2 条差异来自哪里，不能让 compact 后实际 LLM-facing input 只能靠日志计数间接判断。
- 2026-06-05 round2 proactive compact compactor messages dump 暴露 compactor prompt 设计问题：`dayu/config/prompts/scenes/conversation_compaction.md` / `conversation_compaction_user.md` 中存在面向内部实现者的术语和无状态 LLM 不具备的上下文，例如 `Host-owned context compaction`、`ConversationCompactOutputVNext`、`prompt-local evidence labels`、`vNext 字段`。这会增加无状态、有限上下文、偏模式匹配的 LLM 的认知负担，降低 strict JSON compaction 稳定性。`utils/smoke_host_public_conversation_memory.py` 与 `utils/smoke_host_public_conversation_memory_scenarios.py` 需确认是否都装配该 compactor prompt；当前直接 `rg` 证据显示这些术语来自 `dayu/config/prompts/scenes/conversation_compaction*.md`，不是 smoke 脚本内联字符串。
- 2026-06-05 scope review 确认本条不得只检查 `utils/smoke_host_public_conversation_memory.py`；同组 Host public smoke 入口 `utils/smoke_host_public_diagnostics.py`、`utils/smoke_host_public_conversation_memory_scenarios.py`、`utils/smoke_host_public_multiturn.py` 也必须检查是否存在相同修正项，包括多 `system` role message、compact 后 Runner-call message 观测闭环缺口、以及 LLM-facing prompt / evidence material 使用内部实现术语的问题。

### 目标

- 修正 `utils/` 下 Host public smoke 中无法有效验证 Conversation Memory / Host 设计的偏差；当前审计范围至少包括 `utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_diagnostics.py`、`utils/smoke_host_public_conversation_memory_scenarios.py`、`utils/smoke_host_public_multiturn.py`。
- 对每个新增 smoke correctness 问题，先用设计真源与代码直接证据确认 smoke 错在输入构造、断言、观测点、fixture、projection expectation 还是生产实现偏离设计；只有确认是 smoke 偏差时才纳入本条修正。
- 当前已知修正：修改 `utils/smoke_host_public_conversation_memory.py` 及必要的同组 smoke helper，使 smoke 构造的 round1 final Runner-call messages 只包含一个 `system` role message，并增加直接验收；同时审计另外三个 Host public smoke 是否经由相同 prompt assembly 路径产生多 `system` role message，若存在则一并修正并加验收。
- 当前已知修正：补齐 round2 compact 后 RunInput / Runner-call message shape 的 smoke 验收信号，使日志记录的 `message_count`、durable 可重建 messages、memory snapshot / compact artifact 投影三者能对齐；若无法完整重建，smoke 必须输出明确 limited-signal 诊断。
- 当前已知修正：审计 4 个 Host public smoke 的 compactor prompt 装配路径，并修正 `dayu/config/prompts/scenes/conversation_compaction*.md` 中面向内部实现的 prompt 表述；prompt 应以最低认知负担描述下一步动作、输入 JSON、输出 JSON、label 引用规则和禁止项，不要求 LLM 理解 Host 内部命名、Python 类型名或 vNext 历史迁移语义。
- 保持 smoke 能验证真实 public Host path，不通过测试私有入口、伪造 durable atom 或绕过 Host / Engine contract 来获得通过。

### 非目标

- 不修改 production Conversation Memory、compact、RunInputBuilder、Engine runner 或 provider payload 行为。
- 不把 production 实现偏离设计的问题伪装成 smoke 修改；若根因是生产代码，应回到对应 production work unit 或设计真源处理。
- 不通过只改 smoke prompt、测试 fixture 或 dump 脚本来掩盖 `dayu/config/prompts` 真源 prompt 的问题；如果真实 compactor prompt 是根因，必须修 prompt asset 本身并让 smoke 覆盖真实装配路径。
- 不把 smoke 可读性、输出格式美化或普通维护项纳入本条，除非它直接影响 smoke 对 Conversation Memory / Host 设计的验收能力。
- 不补 EventLog runner-call reconstruction atoms；该工作由 WU-DUR-P01 / GitHub Issue #117 承接。
- 不实现 Tool Trace analyzer 或 messages dump 工具；该工作由 WU-OBS-P00 / WU-OBS-00 承接。
- 不引入新的 smoke 私有生产入口或测试专用 durable bridge。

### 验收信号

- 每个纳入本条的 smoke correctness 问题都有直接证据说明为什么 smoke 当前无法验证对应设计点，以及修正后验证的设计点是什么。
- 当前已知项修正后，4 个 Host public smoke 入口通过，并能证明各自 final Runner-call messages 至多只有一个 `system` role message；若某个 smoke 不触发 Runner-call 或 compact，应明确记录它不适用该断言的直接原因。
- 若当前已知项修正后 smoke 仍产生多条 `system` role message，必须 fail fast，而不是只在事后 dump 中发现。
- round2 compact 后 `runner_call_start.message_count` 与 smoke / dump 可观测的 message items 数量一致；若不一致，smoke 失败或输出明确 limited-signal 诊断并指向缺失的投影来源。
- compactor prompt dump 中不再出现要求 LLM 理解内部实现身份或 Python 类型名的表达，例如 `Host-owned context compaction`、`ConversationCompactOutputVNext`、`prompt-local evidence labels`、`vNext 字段`；对应规则必须改写成面向无状态 LLM 的直接任务说明、输入字段说明、输出 JSON 字段说明与引用 label 约束。
- 4 个 Host public smoke 入口均完成 compactor prompt 装配路径审计；凡会触发 compact 的入口，都能证明它们使用的 compactor prompt 来自同一稳定 prompt asset，且该 prompt 通过上述可读性 / 可执行性检查。
- smoke 修改后，相关 Host public smoke 入口通过；pyright 0 errors。

## WU-CM-01-F02 Compact Evidence Query Readability Quality Closeout

### 状态

GitHub Issue #81 / WU-CM-01 final closeout follow-up，依赖 WU-DUR-P01 补齐 accepted tool call request durable atoms。本条处理 compact 输入质量问题，不处理 analyzer dump 可观测性本身；dump / trace 能否轻量重建仍由 WU-DUR-P01 / WU-OBS-P00 承接。

### 设计与代码核对

- 2026-06-05 round2 proactive compact messages dump 显示 `evidence_material[*].query_text` 退化为 `tool_call_id=call_5c4a39a2ea37464a82357cce`。本次 smoke 仍能 compact 成功，是因为 `response_text` 的 mock tool result 自解释且包含完整结构化 facts；但泛化场景下，compactor 会缺少“工具为什么被调用、调用参数是什么、该 evidence 对应哪个用户问题”的语义锚点。
- 当前生产路径为 `build_accepted_tool_evidence_material_blocks` -> `collect_selected_compaction_request_evidence_inputs` -> `_readable_query_text(envelope)`；`_readable_query_text` 目前只返回 `tool_call_id={envelope.tool_call_id}`。
- 根因与 WU-DUR-P01 同源：canonical `TOOL_CALL_REQUESTED` 当前没有可读取的 arguments / semantic query durable atom，因此 compact material projection 无法稳定生成 tool name + arguments / semantic query 的 LLM-readable query text。

### 目标

- 让 compact `evidence_material[*].query_text` 使用 durable tool call request atom 生成可读查询文本，至少包含 tool name 与稳定规范化 arguments；在工具提供 semantic query / readable input 时优先使用该语义文本。
- 保持 query text 是 LLM-readable material，不包含 EventLog id、payload ref、digest、cursor、artifact descriptor 或其它 Host 内部账本细节。
- 与 WU-DUR-P01 对齐：若 durable tool-call arguments / semantic query 尚未补齐，本条不得用 prompt 猜测、tool behavior 推断或当前代码 hardcode 伪造 query text。
- 覆盖 accepted evidence chunking：同一 tool result 被切成 `E1.1`、`E1.2` 等 evidence chunks 时，各 chunk 的 query text 应保持同源、稳定、简洁，不因 chunk 数量重复注入大段参数文本。
- 保持 compact quality owner 边界：本条只改善 compactor LLM-facing evidence material 的查询语义，不改变 accepted tool result truth、不改变 evidence-backed fact accept barrier、不改变 compact candidate schema。

### 非目标

- 不补 EventLog / payload durable atoms；该工作由 WU-DUR-P01 / GitHub Issue #117 承接。
- 不实现 Tool Trace analyzer 或 dump 工具；该工作由 WU-OBS-P00 / WU-OBS-00 承接。
- 不把 tool call request 原文、provider payload 或 Host 内部 refs 直接塞进 compact prompt。
- 不把业务工具 schema 特例硬编码进 compact material projection；若工具需要更好的 semantic query，应通过 typed durable atom / projection contract 表达。
- 不修改 compactor output schema 或 evidence-backed fact candidate 语义。

### 验收信号

- compact material 单元测试覆盖 accepted tool evidence query text：给定 durable tool call name + normalized arguments，`ConversationCompactInputVNext.evidence_material[*].query_text` 输出业务可读查询，而不是裸 `tool_call_id=...`。
- Host public conversation memory smoke 或 focused compact smoke 覆盖 round2 proactive compact：dump 中 `evidence_material[*].query_text` 能看到 tool name / arguments 或 semantic query；若 durable atoms 缺失，smoke 必须输出明确 limited-signal 诊断，而不是静默退化。
- query text 不包含 `event-`、`payload-`、`sha256:`、`compact-artifact:`、cursor、policy ref 等 Host 内部账本标识。
- compact 后 accepted candidate 仍只引用 prompt-local labels，不引用 `C1` 或 Host internal refs。
- 受影响 focused tests 通过；pyright 0 errors。

## WU-CM-01-F03 Assistant Final Answer Continuity Fidelity Closeout

### 状态

GitHub Issue #81 / WU-CM-01 final closeout follow-up。WU-CM-01 已落地 Conversation Memory vNext，但代码核对发现 assistant final answer continuity 的 helper contract 仍允许 `summary_text` / nested summary 作为 fallback。该 fallback 会把用户刚看到的 assistant answer 降级为摘要文本，影响 selected recent window、Answer Material 与后续 compact 输入质量。本条用于追踪实现契约收窄，不重新打开 WU-CM-01 主体设计。

### 设计与代码核对

- Host 设计真源要求 Trace Memory 数据来源包括 `RUN_SUCCEEDED.final_answer`，compact `answer_material` 只包含可读 assistant final answer / conclusion；Session Summary 只能来自 accepted `CONTEXT_COMPACTED` 的 session summary。
- 当前生产 final answer 主路径中，Engine `final_answer` 会写入 terminal summary payload 的 `content` 字段；该 `content` 可作为 assistant final answer continuity 文本。
- 当前 helper `assistant_summary_from_payload()` 会依次读取 `final_answer`、`content`、`summary_text` 与 nested `summary`。其中 `summary_text` / nested summary 作为 assistant answer fallback 与设计真源不一致。
- 风险边界：若 selected recent window 或 compact `answer_material` 消费到 `summary_text`，用户体感上的“刚才那段回答”会被摘要替代；更下一轮 compact 也会基于摘要继续滚动，造成结构、序号、措辞和细节损失。

### 目标

- 将 LLM-facing Trace / Answer material 的 assistant 文本来源收窄为 assistant final answer / conclusion：允许 canonical `final_answer` 与 terminal summary `content`，不得接受 `summary_text` 或 nested summary 作为 assistant final answer fallback。
- 保持 Session Summary Memory 的来源不变：只来自 accepted `CONTEXT_COMPACTED.session_summary`，不得借 terminal summary 或 helper fallback 伪造 session summary。
- 更新 helper 命名、调用点或策略参数，使 selected recent window、fallback recent window、compact `answer_material` 与 compaction history material 的语义一致，避免 “summary” 命名继续误导实现。
- 对缺失 assistant final answer / content 的 `RUN_SUCCEEDED` fail closed 或跳过 continuity item；不得用 ref、digest、event id、payload descriptor 或 `summary_text` 补洞。

### 非目标

- 不修改 compact output schema、Conversation Memory snapshot schema 或 section 顺序。
- 不改变 terminal summary artifact 的持久化职责；本条只规定哪些字段可进入 LLM-facing assistant continuity。
- 不把 compact `session_summary`、answer anchor、reference continuity 或 forward intent 回填成 assistant final answer。
- 不实现深历史 recall、semantic search 或 prompt-conditioned recall。

### 验收信号

- focused tests 覆盖 `RUN_SUCCEEDED` payload 同时存在 `summary_text` 与 terminal `content` 时，selected recent window / compact `answer_material` 使用 final answer content。
- focused tests 覆盖仅存在 `summary_text` / nested summary 且无 final answer / content 时，不生成 assistant continuity item，也不生成 compact answer material。
- compact 输入测试证明 `ConversationCompactInputVNext.answer_material[*].answer_text` 不来自 `summary_text` fallback。
- 现有 `utils/` 下 Host public smoke 仍通过；受影响 focused tests 通过；pyright 0 errors。

## WU-CM-01-F04 Proactive Compaction Manifest-producing Test Seam Closeout

### 状态

Completed。PR 124 已 merge，merge commit 为 `38bf01b05a26a8f7a6a8f8959abd15f6c8d26d13`。Final closeout artifact 为 `docs/reviews/wu-cm-01-f04-final-closeout-controller.md`。PR review gate：MiMo PASS，DS draft-PR-pass，0 blocking findings。DS low maintainability finding（`_RequestCapturingCompactor` 为空语义别名）裁决为后续 cleanup，不影响 correctness；全量 `tests/host/test_dispatch_scheduler.py` 与 pyright 均已通过。`WU-TOOLS-01-S6-R1` 已由本 work unit 关闭，并从 active residual risk 表删除。

### 动机

WU-TOOLS-01 S6 broad Host validation 暴露 7 个 proactive compaction 测试失败，错误都是 `accepted compaction is missing proposal manifest ref`。这不是 WU-TOOLS provider migration 的代码缺陷，也不是要把生产 guard 放宽；根因是 WU-CM-01 升级 ConversationMemory / Compact 后，accepted compact outcome 必须能反向引用 durable proposal manifest ref / digest，而 proactive scheduler tests 还在使用升级前的 legacy fake compactor seam。

### 目标

- 保持 `dayu/host/dispatch.py` 对 accepted compaction 缺少 proposal manifest ref 的 fail-closed 行为不变。
- 新增或抽取 deterministic manifest-producing Host test compactor，使它对齐当前 `CompactorProposalPreparedCompactor` contract。
- 将受影响的 proactive scheduler tests 从 legacy fake compactor seam 迁移到 manifest-producing test seam。
- 覆盖 accepted 和 rejected compact event，直接断言 proposal manifest ref / digest。
- 恢复 broad Host validation 对 proactive compaction 路径的有效验收信号。

### 非目标

- 不为旧 fake compactor seam 增加兼容 wrapper / facade。
- 不把 production compact guard 改成接受缺失 manifest ref。
- 不重开 WU-TOOLS provider migration；本条只处理 WU-CM-01 compact contract 升级后的 Host 测试 seam fallout。
- 不引入新的生产 compactor implementation。

### 验收信号

- 当前 7 个 proactive compaction manifest-ref failures 关闭。
- focused tests 证明 accepted compact event 必须携带 proposal manifest ref / digest。
- focused tests 证明 rejected compact event 的 manifest ref / digest 投影符合当前 contract。
- broad Host validation 中 proactive scheduler compact 相关测试恢复通过；若仍有其它 broad Host failure，必须单独归因并转 owner。
- pyright 0 errors。

## WU-CM-02 Working Assumptions Producer Semantics

### 状态

已裁决；独立 WU rejected / closed。`working_assumptions` 不作为 #81 第一阶段 semantic memory category 保留，不再为旧字段补生产者语义。旧 schema / snapshot / renderer 中的 `working_assumptions` 删除或迁移由 WU-CM-01 的 schema / projection / RunInputBuilder slice 承接。

### 目标

- 固定裁决：reject 旧 `working_assumptions` 独立语义，不把它作为 Trace / Evidence-Fact / Session Summary / Answer Anchor / Forward Intent 之外的第六个 session-scoped memory。
- WU-CM-01 plan 必须明确旧 `working_assumptions` 字段的删除 / 迁移边界，覆盖 schema、snapshot codec、durable projection、RunInputBuilder 与 tests。
- 后续若需要 hypotheses / candidate claims，必须另起设计并绑定 source、status、confidence 与 user-visible boundary；不得复用旧 `working_assumptions` 名称做兼容 wrapper。

### 非目标

- 不让 `working_assumptions` 承载工具事实、财报事实、任务状态或长期用户画像。
- 不绕过 evidence-backed fact 主链路。
- 不在 #81 / WU-CM-01 中为旧 memory shape 做局部修补或兼容 wrapper。

### 验收信号

- WU-CM-01 plan 明确旧 `working_assumptions` 的删除 / 迁移 slices 与测试入口。
- 字段不存在时，schema、snapshot codec、durable items、RunInputBuilder 和测试全部同步收敛。
- 若实现阶段发现仍有字段残留，必须作为 WU-CM-01 schema / projection finding 修复，不能重新打开 WU-CM-02。

## WU-CM-03 Fact-candidate-only Validation Failure Policy

### 状态

已裁决；独立 WU closed。fact-candidate-only validation failure 统一采用 fail closed / whole-candidate repair retry，不允许 partial materialize。

### 目标

- 裁决 `CONTEXT_COMPACTED` 中 fact candidates 非法但其它 compact output 合法时必须 fail closed：rejected candidate 不得 partial materialize，不得写 `CONTEXT_COMPACTED`，只允许进入 bounded whole-candidate repair retry 或最终 `CONTEXT_COMPACTION_FAILED` / fallback policy。
- 统一 quality check、payload validation、memory projection、diagnostic 与用户可见失败策略，作为 WU-CM-01 compact accept barrier / repair tests 的输入约束。

### 非目标

- 不重新开放 fact-candidate-only partial materialize 作为实现选项。
- 不让非法 fact candidates 进入 evidence-backed facts。

### 验收信号

- 测试覆盖 fact candidates invalid / non-fact compact fields invalid 两类路径，均验证 rejected candidate 不进入 memory projection。
- fail closed / whole-candidate repair retry 的策略在 projection、diagnostic 和用户可见结果上一致。

## WU-CM-04 Minimum Preserve And Fins Fact Boundary

### 状态

已裁决；独立 WU closed。Minimum Preserve 保留为 bounded continuity item，不是事实真源；后续 Fins integration 必须继承该边界。

### 目标

- 确认 `minimum preserve` 继续作为 bounded continuity item，而不是事实真源。
- 明确后续 Fins 接入时不得把 minimum preserve 文本当作财报事实引用。

### 非目标

- 不把 minimum preserve 标成 verified / sourced fact。
- 不让 UI / Service 把 continuity item 当作财报引用真源。

### 验收信号

- Fins / ToolRuntime / RunInputBuilder 文档和测试均不把 minimum preserve 当 stable fact。
- minimum preserve 的 source refs 只服务 continuity，不成为财报引用真源。

## WU-TOOLS-01 Fins / Web / Doc Tools Migration With Shared Document Foundations

### 状态

已纳入 GitHub Issue #82、#97 与 #98。三条 issue 必须作为同一个 work unit 实施，可以分 slice 推进。原因是旧 `dayu-agent/dayu/fins`、旧 Web tools 与旧 Doc tools 共享多类文档基础能力，不只是 Docling runtime：Doc tools 依赖 engine processors，Fins 也大量依赖 engine processors，Web tools 依赖 Docling conversion path。拆成多个独立 work unit 容易产生重复 processor 迁移、重复 Docling adapter、重复 package placement 决策和不一致的测试替身。

### 设计与代码核对

- 旧仓库 Fins source scope 是 `dayu-agent/dayu/fins`，不是 `dayu-agent/fins`。
- 旧仓库 Fins 通过 `dayu-agent/dayu/fins/docling_export.py` 使用共享 `dayu.docling_runtime`。
- 旧仓库 Fins processors 明确依赖 engine processors：`FinsBSProcessor -> BSProcessor`、`FinsDoclingProcessor -> DoclingProcessor`、`FinsMarkdownProcessor -> MarkdownProcessor`，并复用 `ProcessorRegistry`、`Source`、`text_utils`、`search_utils`、`table_utils` 等公共处理器基础能力。
- 旧仓库 Doc tools source scope 是 `dayu-agent/dayu/engine/tools/doc_tools.py` 与其依赖的 `dayu-agent/dayu/engine/processors/*` 文档处理器链路。
- 旧仓库 Doc tools 通过 `create_doc_file_processor(...)` 间接使用 `DoclingProcessor`；`DoclingProcessor` 读取 `*_docling.json` 时依赖 `docling-core` 的 `DoclingDocument`。
- 用户请求提到 `dayu-agent/dayu/web`；代码核对显示该路径主要是旧 UI 适配层（Streamlit / FastAPI），不是 Web tools 主实现。
- 旧仓库真正的 Web tools 代码主要出现在 `dayu-agent/dayu/engine/tools/web_*.py`，包括 `search_web`、`fetch_web_page`、search provider、challenge detection、fetch orchestrator 与 Playwright fallback 等。
- 旧仓库 Web tools 通过 `dayu-agent/dayu/engine/tools/web_fetch_orchestrator.py` 使用共享 `dayu.docling_runtime`。
- 旧仓库 Web tools 相关 typed config 分布在 `WebToolsConfig`、execution options、toolset config 与 scene / contract preparation 相关代码中；迁移时必须只做当前 `dayu-agent-r` ToolDiscovery / ToolRuntime 所需的 typed config 适配。
- `dayu-agent-r` 当前已有 `docling` / `docling-core` 依赖，但没有等价的共享 Docling runtime ownership，也没有旧仓库 engine processors / doc tool chain。
- 本条不是 UI 入口迁移；CLI / Web / GUI 入口分别由 UI 总控中的 #83 / #84 / #85 处理。

### Slice 切分

1. Shared document foundations slice：先裁决并迁移 / 建立共享文档基础能力，包括 engine processors、processor registry、document source / text / table / search utils、Docling runtime / conversion path、Docling JSON loading、package placement、import path 和测试替身。
2. Doc tools slice：从 `dayu-agent/dayu/engine/tools/doc_tools.py` 迁移长期运行验证可靠的通用文档工具，只允许做最小 `@tool` adapter、ToolDiscovery provider / entry-point adapter、import / package 位置和 package name 调整。
3. Fins slice：从 `dayu-agent/dayu/fins` 迁移长期运行验证可靠的 Fins 代码，只允许修改 `@tool` 与 ToolDiscovery 接口适配部分，不允许修改其它 Fins 业务代码。
4. Web tools slice：从核定后的旧 Web tools source files 迁移长期运行验证可靠的 Web tools 代码，只允许做最小 `@tool` adapter、ToolDiscovery provider / entry-point adapter、import / package 位置和 package name 调整。

### 迁移原则

- 三类工具迁移原则一致：Doc tools、Fins tools、Web tools 都按可靠旧代码迁移，不按新设计重写。
- 允许搬迁代码。
- 允许调整 import、package 位置和 package name。
- 允许做最小必要的 `@tool` adapter changes。
- 允许做最小必要的 ToolDiscovery provider / entry-point adapter changes。
- 禁止修改被迁移旧代码的 class / function signature。
- 禁止修改被迁移旧代码的函数实现代码。
- 如当前 `dayu-agent-r` 的 typed config、path safety、ToolRuntime 或 ToolDiscovery contract 需要适配，必须通过外层 adapter / provider / assembly code 解决，不得借机改旧函数签名或旧函数体。

### 目标

- 建立单一共享文档基础能力 owner，供 Fins、Doc tools 和 Web tools 复用，避免重复迁移 engine processors、重复实现转换、Docling JSON loading、backend fallback、device fallback、error classification 或测试替身。
- 迁移通用 Doc tools 与 processor chain，使 `list_files`、`get_file_sections`、`search_files`、`read_file`、`read_file_section` 等能力能通过当前 ToolDiscovery / ToolRuntime 使用。
- 保留 Docling JSON processor 对 `*_docling.json` 的章节、表格、section ref、table ref 与搜索行为。
- 新增或接入 `dayu.fins.storage` 下的财报仓储协议与实现。
- 财报工具 provider 通过 ToolDiscovery 进入 Host，而不是由 Host 扫描业务工具。
- 财报工具结果进入 accepted evidence 主链路。
- 核定旧仓库 Web tools 的准确 source scope，记录哪些旧文件被作为 Web tools 迁移，哪些 `dayu.web` UI 文件被明确排除。
- 将验证可靠的 Web tools 代码迁入 `dayu-agent-r` 合适包位置，并保留源行为。
- Web tools 能通过当前 ToolDiscovery 显式配置 / entry point 被发现，并通过当前 tool contract 调用。
- Web tool results 通过 ToolRuntime / Tool Trace / accepted evidence path 流转；不得绕过 Host 工具治理。
- 使用 deterministic fixtures / mocks 覆盖代表性 engine processors、Docling conversion、Docling JSON processing、Doc tools、Fins、search / fetch 行为，不能只依赖 live network 或真实 Docling heavyweight execution。

### 非目标

- 不把财报原文存取放入 Host / Service / runtime。
- 不把 minimum preserve 或 compact summary 当作财报事实真源。
- 不重写 Doc tools / processor business logic，尤其不重写章节、表格、section ref、table ref、snippet search、HTML / Markdown / Docling JSON fallback 语义。
- 不修改已长期运行验证可靠的 Fins 业务代码，除外层 `@tool` adapter 与 ToolDiscovery provider / entry-point adapter 外。
- 不重构 Web tool 业务逻辑。
- 不重写搜索、抓取、正文抽取、URL safety、private network filtering、truncation、challenge detection、Playwright fallback 或 diagnostic payload 语义。
- 不迁移旧 `dayu.web` UI / FastAPI / Streamlit entrypoints。
- 不让 Host 直接 import 或 scan Fins / Doc / Web tool implementation modules。
- 不把多套 processor / Docling runtime adapter 分别塞进 Fins、Doc tools 和 Web tools。
- 不让 `dayu.runtime` 依赖 Web tool implementation、Host、Engine、Service、UI 或 Fins；是否把 shared document foundations 的某部分放入 `dayu.runtime` 必须先经过分层设计裁决，不能因为复用方便直接下沉。
- 不把网络权限、私网访问开关或浏览器配置隐藏到全局变量 / 临时环境读取；必须走显式 typed config / policy。

### 验收信号

- 共享文档基础能力只有一个 owner，Fins、Doc tools 与 Web tools 复用同一套 processor chain、conversion / Docling JSON loading / backend fallback / device fallback 语义。
- 通用 Doc tools 与 processor chain 被迁入 `dayu-agent-r`，且 ToolDiscovery 能发现 Doc tools provider。
- Doc tools 能通过当前 tool contract 调用，并能处理 Markdown、HTML 与 `*_docling.json` deterministic fixtures。
- Fins storage、tool provider、ToolDiscovery 和 ToolRuntime accept path 有端到端测试。
- `evidence_backed_facts` 仍只由 Host-governed compact extraction 生成。
- 迁移后的 Web tools 存在于 `dayu-agent-r`，并记录 source scope 与排除的旧 UI files。
- Fins、Doc tools 和 Web tools 的旧代码只发生允许范围内的迁移变更：搬迁代码、import / package 位置 / package name 调整、最小 `@tool` adapter、最小 ToolDiscovery provider / entry-point adapter；旧 class / function signature 和函数实现代码保持不变。
- ToolDiscovery 能发现 Fins、Doc tools 与 Web tools provider，代表性 tool 可通过当前 tool contract 调用。
- ToolRuntime / Tool Trace / accepted evidence path 能接收 Fins / Doc / Web tool result。
- import-boundary tests 证明 runtime / Host / Service / UI 不获得对 Fins / Doc / Web tool implementation internals 的 forbidden direct dependency。
- deterministic tests 覆盖代表性 engine processors、Docling conversion、Docling JSON processor、Doc tools、Fins storage / provider、search / fetch / URL safety / truncation / fallback 或对应 mock 行为。
- 任何源行为偏离都被记录，并证明是当前接口适配所必需。

## WU-TOOLS-01-F01 Shared Fins Ingestion Runtime And Download / Preprocess Awaiting Tools

### 状态

Draft-PR-pass-final-closeout-passed。Draft PR 为 https://github.com/noho/dayu-agent-r/pull/126。PR review artifacts 为 `docs/reviews/wu-tools-01-f01-pr-review-mimo.md`、`docs/reviews/wu-tools-01-f01-pr-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-pr-review-controller-adjudication.md`。两路 review 均为 pass-with-findings，controller 未接受任何 PR-blocking fix；FileLock 相关 finding 按用户裁决 deferred to `WU-TOOLS-01-F01-01`。Final closeout artifact 为 `docs/reviews/wu-tools-01-f01-final-closeout-controller.md`。当前等待用户 merge PR 126；merge 后下一入口是 `WU-TOOLS-01-F01-01` goal confirmation。

Review。Accepted plan commit 为 `27f91192`。Slice S1 accepted commit 为 `f598f8a2`。Slice S2 accepted commit 为 `2e12dfb4`。Slice S3 accepted commit 为 `4b91d3af`。Slice S4 accepted commit 为 `2727b900`。Slice S5 accepted commit 为 `5336d7b2`。Slice S6 accepted commit 为 `157ec0b5`。`WU-TOOLS-01-S4-R1` 已关闭并从 active residual table 移除，关闭依据见 S6 re-review controller adjudication。当前进入 aggregate final review gate。Slice S6 implementation artifact 为 `docs/reviews/wu-tools-01-f01-s6-implementation-codex.md`；AgentCodex 报告验证 138 tests passed、pyright 0 errors、`git diff --check` 通过。Slice S6 code review artifacts 为 `docs/reviews/wu-tools-01-f01-s6-code-review-mimo.md`、`docs/reviews/wu-tools-01-f01-s6-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s6-code-review-controller-adjudication.md`，接受 read provider split identity 和 Fins wait adapter import-boundary path robustness 两项 fix。Slice S6 fix artifact 为 `docs/reviews/wu-tools-01-f01-s6-fix-codex.md`；AgentCodex 报告验证 138 tests passed、pyright 0 errors、`git diff --check` 通过。Slice S6 re-review artifacts 为 `docs/reviews/wu-tools-01-f01-s6-rereview-mimo.md`、`docs/reviews/wu-tools-01-f01-s6-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s6-rereview-controller-adjudication.md`，两项 accepted findings 均 fixed，无新增 finding；Controller 复验 138 tests passed、pyright 0 errors、`git diff --check` 通过。Slice S5 implementation artifact 为 `docs/reviews/wu-tools-01-f01-s5-implementation-codex.md`；AgentCodex 报告验证 49 tests passed、Service tests 34 passed、pyright 0 errors、`git diff --check` 通过。Slice S5 code review artifacts 为 `docs/reviews/wu-tools-01-f01-s5-code-review-mimo.md`、`docs/reviews/wu-tools-01-f01-s5-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s5-code-review-controller-adjudication.md`，接受 active-state poll 覆盖、无 Fins provider registry absent 覆盖、corrupt evidence lost 覆盖、abandon_wait defensive 覆盖、workspace_root 缺失/相对路径 fail-fast 覆盖五项 fix。Slice S5 fix artifact 为 `docs/reviews/wu-tools-01-f01-s5-fix-codex.md`；AgentCodex 报告验证 56 tests passed、Service tests 37 passed、pyright 0 errors、`git diff --check` 通过。Slice S5 re-review artifacts 为 `docs/reviews/wu-tools-01-f01-s5-rereview-mimo.md`、`docs/reviews/wu-tools-01-f01-s5-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s5-rereview-controller-adjudication.md`，五项 accepted findings 均 fixed，无新增 finding；Controller 复验 56 tests passed、Service tests 37 passed、pyright 0 errors、`git diff --check` 通过。Slice S4 implementation artifact 为 `docs/reviews/wu-tools-01-f01-s4-implementation-codex.md`；AgentCodex 报告验证 56 tests passed、pyright 0 errors。Slice S4 code review artifacts 为 `docs/reviews/wu-tools-01-f01-s4-code-review-mimo.md`、`docs/reviews/wu-tools-01-f01-s4-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s4-code-review-controller-adjudication.md`，接受 tool helper 去重、start failure path 测试覆盖、awaiting tests 等待后台 job 收口三项 fix。Slice S4 fix artifact 为 `docs/reviews/wu-tools-01-f01-s4-fix-codex.md`；AgentCodex 报告验证 60 tests passed、pyright 0 errors。Slice S4 re-review artifacts 为 `docs/reviews/wu-tools-01-f01-s4-rereview-mimo.md`、`docs/reviews/wu-tools-01-f01-s4-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s4-rereview-controller-adjudication.md`，三项 accepted findings 均 fixed，无新增 finding；Controller 复验 60 tests passed、pyright 0 errors、`git diff --check` 通过。Slice S3 implementation artifact 为 `docs/reviews/wu-tools-01-f01-s3-implementation-codex.md`；AgentCodex 报告验证 35 tests passed、pyright 0 errors。Slice S3 code review artifacts 为 `docs/reviews/wu-tools-01-f01-s3-code-review-mimo.md`、`docs/reviews/wu-tools-01-f01-s3-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s3-code-review-controller-adjudication.md`，接受 success terminalization 与 cancellation TOCTOU、terminal record early return 两项 fix。Slice S3 fix artifact 为 `docs/reviews/wu-tools-01-f01-s3-fix-codex.md`；AgentCodex 报告验证 37 tests passed、pyright 0 errors。Slice S3 re-review artifacts 为 `docs/reviews/wu-tools-01-f01-s3-rereview-mimo.md`、`docs/reviews/wu-tools-01-f01-s3-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s3-rereview-controller-adjudication.md`，两项 accepted findings 均 fixed，无新增 finding。Slice S2 implementation artifact 为 `docs/reviews/wu-tools-01-f01-s2-implementation-codex.md`；AgentCodex 报告验证 `pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py` 通过、pyright 通过。Slice S2 code review artifacts 为 `docs/reviews/wu-tools-01-f01-s2-code-review-mimo.md`、`docs/reviews/wu-tools-01-f01-s2-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s2-code-review-controller-adjudication.md`，接受 form-filter 后再执行 `_MAX_PREPROCESS_DOCUMENTS` 上限检查、以及 `_save_failed_from_exception` 二次失败可观测诊断两项 fix。Slice S2 fix artifact 为 `docs/reviews/wu-tools-01-f01-s2-fix-codex.md`；AgentCodex 报告验证 31 tests passed、pyright 0 errors。Slice S2 re-review artifacts 为 `docs/reviews/wu-tools-01-f01-s2-rereview-mimo.md`、`docs/reviews/wu-tools-01-f01-s2-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s2-rereview-controller-adjudication.md`，两项 accepted findings 均 fixed，无新增 finding。Slice S1 implementation artifact 为 `docs/reviews/wu-tools-01-f01-s1-implementation-codex.md`；Controller 复验 `pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py` 通过，pyright 通过。Slice S1 code review artifacts 为 `docs/reviews/wu-tools-01-f01-s1-code-review-mimo.md`、`docs/reviews/wu-tools-01-f01-s1-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s1-code-review-controller-adjudication.md`。Slice S1 fix artifact 为 `docs/reviews/wu-tools-01-f01-s1-fix-codex.md`；Slice S1 re-review artifacts 为 `docs/reviews/wu-tools-01-f01-s1-rereview-mimo.md`、`docs/reviews/wu-tools-01-f01-s1-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-s1-rereview-controller-adjudication.md`。Plan artifact 已生成并修复：`docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`。Plan review artifacts 已生成：`docs/reviews/wu-tools-01-f01-plan-review-mimo.md`、`docs/reviews/wu-tools-01-f01-plan-review-ds.md`。Controller adjudication 已生成：`docs/reviews/wu-tools-01-f01-plan-review-controller-adjudication.md`。Plan fix summary 已生成：`docs/reviews/wu-tools-01-f01-plan-fix-controller-summary.md`。Plan re-review artifacts 已生成：`docs/reviews/wu-tools-01-f01-plan-rereview-mimo.md`、`docs/reviews/wu-tools-01-f01-plan-rereview-ds.md`。Plan re-review controller adjudication 已生成：`docs/reviews/wu-tools-01-f01-plan-rereview-controller-adjudication.md`。裁决结论：F01 不只是迁移几个 tool name，而是先迁移 / 建立 NEW 的共享 Fins service/runtime；read、download 和 preprocess/process 都以这套 service/runtime 为业务底座。最关键约束是：CLI download 和 tool download 必须走同一套代码、同一套逻辑。Tool 侧只做当前 Host / ToolRuntime 的 awaiting adapter；未来 NEW CLI 也调用同一套 service/runtime，避免 CLI 和 tool 逻辑漂移。原 upload follow-up `WU-TOOLS-01-F09` 已并入 `WU-TOOLS-01-F01-03`，由 F01-03 和 CN / SEC download 真实可用能力一起推进。

### 动机

WU-TOOLS-01 S4 只迁移了 Fins read tools。这个残留不是因为 Host / ToolRuntime 缺少 awaiting 机制；当前 Host 已有 awaiting accept、wait record、resume / closeout、cancellation 与 late terminal governance，Engine 也以 `ToolAwaitingOutcome` 作为 suspended run 边界。真正缺口是 OLD 的共享 Fins ingestion service/runtime 尚未迁入 NEW：OLD download 与 preprocess/process 共用 `FinsIngestionService` / service runtime，CLI 和 tool 两处都应调用同一套业务逻辑，不能在 tool adapter 或未来 CLI 中各自重写一套。CLI 只能负责命令行参数解析、输出格式和退出码；tool 只能负责 schema、ToolDiscovery、ToolRuntime、awaiting / wait-resume；download / process 的参数校验、ticker / market 归一化、form/date/overwrite 语义、storage 写入、pipeline 调用、状态/result 归一化必须在 shared Fins service/runtime 中。

Ticker / market 归一化的唯一真源是 `dayu/fins/ticker_normalization.py`。所有需要归一化 ticker 或判断 market 的 read、download、preprocess/process、upload、CI runner、smoke runner 与 future CLI 入口，都必须调用该模块暴露的 `normalize_ticker(...)` / `try_normalize_ticker(...)` / `ticker_to_company_id(...)` 等公共 API；不得在 service/runtime、tool adapter、CLI、CI script、pipeline selector 或 storage 外层重新实现第二套 ticker parsing、market suffix stripping、US/HK/CN 判断、交易所推断或 company id 生成逻辑。

当前 `include_ingestion_tools=true` fail-closed 开关只是 S4 过渡期保护，不是 F01 目标形态。F01 后 Discovery 应能分别发现三组独立 Fins tool providers：read、download、preprocess，而不是通过一个 `include_ingestion_tools` 布尔开关混合启用。

### 目标

- 迁移 / 建立 NEW 的共享 Fins service/runtime，承载 read、download 与 preprocess/process 的业务底座；其中 download 与 preprocess/process 是长事务入口，未来 CLI 与 tool 必须共同调用它。
- Shared Fins service/runtime 中所有 ticker / market 归一化必须调用 `dayu.fins.ticker_normalization` 的公共 API；如需新增归一化规则，只能改该真源模块及其测试，不能在调用点复制逻辑。
- download tool provider、preprocess tool provider、read tool provider 三组独立进入 ToolDiscovery；不得继续用 `include_ingestion_tools=true` 这类混合开关作为目标形态。
- CLI download 和 tool download 必须同源调用 shared Fins service/runtime；不得存在 CLI download 一套业务代码、tool download 另一套业务代码。
- CLI process/preprocess 和 tool preprocess 必须同源调用 shared Fins service/runtime；不得存在 CI / CLI / tool 各自复制 process 逻辑。
- Tool 侧只做当前 Host / ToolRuntime 的 awaiting adapter，把共享 service/runtime 的 queued / running / cancelling / succeeded / failed / cancelled 状态映射到当前 awaiting、resume、cancel 与 terminal result 语义。
- Download 工具组覆盖财报下载长事务；preprocess 工具组覆盖文档预处理 / process 长事务。OLD 当前注册列表只暴露 download 三件套，但 preprocess/process 业务逻辑必须进入共享 service/runtime，后续是否对 LLM 暴露为工具由独立 preprocess provider 的 schema / awaiting plan 裁决。
- 未来 NEW CLI 必须调用同一套 Fins ingestion service/runtime；F01 plan 应明确 CLI 入口属于本条实现、后续 slice，还是带 owner 的后续 work unit。
- 保持财报文档存取仍只能通过 `dayu.fins.storage` 仓储协议与实现完成。
- 保持工具结果通过 Host ToolRuntime / Tool Trace / accepted evidence path 流转，不绕过 Host 工具治理。
- 关闭 `WU-TOOLS-01-S4-R1`，并移除或替换 S4 过渡期 Fins provider 对 ingestion tools 的 fail-closed 开关。

### 非目标

- 不重新设计 Host / Engine awaiting 基础 contract。
- 不在 Fins 工具内部私自实现 Host 外的轮询、等待、取消或 late terminal 治理；这些语义必须进入 Host / ToolRuntime awaiting contract。
- 不让 CLI 和 tool 分别实现 download / preprocess 业务逻辑；业务逻辑必须在共享 service/runtime 中。
- 不把 CI runner、smoke runner 或未来 CLI 作为绕过 shared Fins service/runtime 的第二套 download / process 实现。
- 不在 service/runtime、tool adapter、CLI、CI runner、smoke runner 或 pipeline selector 中再造 ticker / market 归一化逻辑；不得通过局部字符串规则替代 `dayu.fins.ticker_normalization`。
- 不修改被迁移旧 ingestion 业务函数签名或函数实现；如需适配当前 ToolRuntime / ToolDiscovery / CLI，必须通过外层 adapter / provider / assembly code 完成。
- 不在 F01 已完成范围内补迁移 upload；OLD upload 迁移、CN / SEC upload tool 与 future CLI / CI 访问同源性由 `WU-TOOLS-01-F01-03` 追踪。
- 不迁移旧 UI / FastAPI / Streamlit ingestion entrypoints。

### 验收信号

- ToolDiscovery 能分别发现 Fins read、Fins download、Fins preprocess 三组 provider；download / preprocess 不依赖 `include_ingestion_tools=true` 混合开关。
- Download 和 preprocess 代表路径可通过当前 tool contract 调用，并返回当前 `ToolAwaitingOutcome` / wait-resume contract 所需信息，不把 queued / running job 伪装成 completed business result。
- 共享 Fins service/runtime 有 focused tests，证明 CLI-facing download 与 tool-facing download 走同一业务逻辑入口；process/preprocess 同理。
- Focused tests 或静态代码检查证明 download / preprocess / read 相关入口的 ticker / market 归一化均调用 `dayu.fins.ticker_normalization`，没有第二套 parsing / market inference 逻辑。
- 若 F01 尚未实现 NEW CLI，必须提供 service/runtime 层测试和明确后续 CLI owner，证明未来 CLI 只能包 shared runtime，不能重写 download / process 逻辑。
- Host wait record、resume、cancel 与 late terminal result 路径有 deterministic tests 覆盖。
- 失败、取消、重复 start / reused job、迟到 terminal result 均有明确测试或记录为带 owner 的 residual。
- Fins README、tests README 或相关 package README 只描述当前已实现行为，不保留旧 fail-closed 或混合开关误导说明。

## WU-TOOLS-01-F01-01 Fins Filelock Convergence To dayu.runtime.filelock

### 状态

Draft-PR-pass-final-closeout-passed。该 work unit 是 `WU-TOOLS-01-F01` draft PR 前置 follow-up。当前裁决：Fins 内部重复实现 filelock 是真实的公共契约收敛问题；最优设计是优先复用 `dayu.runtime.filelock`，而不是在 `dayu.fins` 中继续维护 `_StoreFileLock` 或 `dayu.fins._file_lock`。

Plan gate 已完成，artifact 为 `docs/host/wu-tools-01-f01-01-filelock-plan.md`；Plan review artifacts 为 `docs/reviews/wu-tools-01-f01-01-plan-review-mimo.md`、`docs/reviews/wu-tools-01-f01-01-plan-review-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f01-01-plan-review-controller-adjudication.md`；Plan fix artifact 为 `docs/reviews/wu-tools-01-f01-01-plan-fix-codex.md`；Plan re-review artifacts 为 `docs/reviews/wu-tools-01-f01-01-plan-rereview-mimo.md`、`docs/reviews/wu-tools-01-f01-01-plan-rereview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f01-01-plan-rereview-controller-adjudication.md`；accepted plan commit 为 `c20ac977`。Slice 1 accepted commit 为 `7c33fb9d`，bookkeeping commit 为 `a846ed90`。Slice 2 accepted commit 为 `14cb3e97`，bookkeeping commit 为 `73d4f25a`。Slice 3 accepted commit 为 `f80bf4bc`，bookkeeping commit 为 `71a81277`。Aggregate deepreview artifacts 为 `docs/reviews/wu-tools-01-f01-01-aggregate-deepreview-mimo.md`、`docs/reviews/wu-tools-01-f01-01-aggregate-deepreview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-01-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均为 PASS，0 条 accepted findings；Controller 裁决不新增 active residual risk。Accepted deepreview commit 为 `8587cd1d`。Draft PR 已创建：`https://github.com/noho/dayu-agent-r/pull/127`。PR review artifacts 为 `docs/reviews/wu-tools-01-f01-01-pr-review-mimo.md`、`docs/reviews/wu-tools-01-f01-01-pr-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-01-pr-review-controller-adjudication.md`。Controller 裁决无 accepted PR fix，不新增 active residual risk。Accepted PR review commit 为 `a28fc027`，已推送到 PR 127。Final closeout artifact 为 `docs/reviews/wu-tools-01-f01-01-final-closeout-controller.md`；当前等待用户 merge decision，merge 后下一入口为 WU-TOOLS-01-F01-02 goal confirmation。

### 动机

`dayu.runtime.filelock` 已经是层中立公共运行时契约，Host 已在 audit / tool trace 等路径复用它。Fins 当前同时存在 ingestion job store 私有 `_StoreFileLock` 和 storage batch 私有 `dayu.fins._file_lock`，形成三套 filelock 语义并存。这会扩大跨平台行为、异常映射、timeout 语义和跨进程互斥治理的漂移风险，也违反“各层公共运行时能力优先复用 `dayu.runtime`”的架构约束。

### 目标

- 将 Fins ingestion job store 的私有 `_StoreFileLock` 收敛到 `dayu.runtime.filelock`。
- 将 Fins storage batch 的 `dayu.fins._file_lock` 收敛到 `dayu.runtime.filelock`。
- 若收敛后无生产引用，删除 `dayu.fins._file_lock` 与 `_StoreFileLock`。
- 保持现有 job store 原子写入、跨进程互斥、storage batch 同 ticker fail-fast 冲突语义不变。
- 不增加仅透传 `dayu.runtime.filelock` 的 Fins wrapper / facade。

### 实施前置要求

实施前必须先评估 `dayu.runtime.filelock` 的能力是否满足现有 Fins 要求；若不满足，先回到设计裁决，优先扩展 `dayu.runtime.filelock` 的公共能力，不得在 Fins 中再造第二套 filelock。评估至少覆盖：

- ingestion job store 当前需要的 blocking lock、锁文件父目录创建、异常传播和 `RuntimeFileLock` 生命周期语义。
- storage batch 当前需要的 non-blocking acquire、同 ticker 跨进程活动 batch 冲突、timeout / busy 异常映射与原有用户可读错误语义。
- 跨进程互斥、锁释放、进程退出 / 文件句柄关闭后的清理行为。
- macOS / Linux 运行环境下的行为一致性；不以 POSIX-only 私有实现作为 Fins 特例。
- 现有测试中 `_StoreFileLock` / `dayu.fins._file_lock` 覆盖的行为是否都能迁移到 runtime filelock 或 Fins 行为测试。

### 非目标

- 不修改 Fins job schema。
- 不修改 `dayu.fins.storage` 仓储协议。
- 不修改 atomic replace / json store 数据落盘语义。
- 不修改 Host / Engine / ToolRuntime contract。
- 不引入 async filelock 或 Host 专用 durable lock。

### 验收信号

- `dayu/fins` 生产代码不再引用 `_StoreFileLock`、`dayu.fins._file_lock`、`acquire_text_file_lock` 或 `release_text_file_lock`。
- Fins ingestion runtime 与 storage batch 相关测试证明锁语义未漂移。
- `dayu.runtime.filelock` 如需扩展，扩展发生在 runtime 公共契约层，并有 runtime tests 覆盖。
- pyright、受影响 Fins tests 与 `git diff --check` 通过。

## WU-TOOLS-01-F01-02 Migrated Tools Cancellation Propagation And Response

### 状态

Discussion-ready。该 work unit 是 `WU-TOOLS-01-F01` draft PR 前置 follow-up。当前裁决：cancel 治理真源仍在 Host；本条不重做 Host cancel，而是补齐当前已迁移 Fins / Web / Doc tools 对 Host 注入 `CancellationToken` 的传递、观察与资源释放响应。Web tools 虽未设计为 awaiting 长事务工具，但真实执行包含网络、浏览器、页面解析等长耗时外部 I/O，本 WU 必须实现取消响应。

### 动机

Host 已通过 run cancel / session cancel、active worker registry、Engine cancellation token 与 wait abandon path 建立 run-level graceful cancel 治理。当前缺口在工具迁移层：Fins download / preprocess、Web tools、Doc tools 与 Fins read tools 虽已接入当前 ToolRuntime / ToolDiscovery，但业务 callable 对 `BatchToolExecutionContext.cancellation_token` 的传递和观察不完整。结果是 UI 可以发起 run cancel，Host / Engine 也能停止未来 LLM 工作，但部分工具或后台任务仍可能继续执行网络请求、文件处理或 ingestion job，造成取消响应漂移与资源浪费。

### 目标

- 对当前已迁移 Fins / Web / Doc tools 做 cancellation propagation audit，列明每个 tool callable 是否把 `BatchToolExecutionContext.cancellation_token` 传入业务执行层，是否在关键 side-effect 前后观察 token。
- Fins download / preprocess awaiting 工具必须在本 WU 实现取消响应：start 前、durable job 创建前、后台 job checkpoint、wait abandon / `runtime.request_cancel(job_id)` 路径都要保持同源取消语义。
- Web tools 必须在本 WU 实现取消响应：网络请求、Playwright/browser path、页面解析与 fetch/search 主路径都要至少在入口、外部 I/O 前、外部 I/O 后和结果 materialize 前观察 token；阻塞 I/O 必须结合 bounded timeout，不能把 token 当成可中断系统调用的魔法开关。
- Doc tools 与 Fins read tools 至少完成 token 传递和风险分级；若实现路径存在长耗时外部 I/O、CPU 密集解析或大文件处理，本 WU 应补 checkpoint；若仅为短本地查询 / 参数解析，可记录为暂不需要细粒度响应。
- ToolRuntime 侧按需补充统一取消边界检查，覆盖 dispatch 前、等待业务工具、accept / awaiting accept retry 与 retry sleep 等路径，避免 cancel 后继续等待治理动作。
- 保持工具取消的核心语义：cancel 阻止未来工作并尽快释放资源，不撤回已 accepted facts，不伪造业务事实。

### 非目标

- 不改变 Host cancel 真源，不用工具私有 cancel 状态替代 Host durable cancel。
- 不重新设计 `CancellationToken` 公共契约；token 仍是观察面，不提供工具侧写入 Host 状态的能力。
- 不把所有 run cancel 都投影为 LLM-facing `ToolCancelledOutcome`；run-level cancel 仍由 Engine / Host 收口为 run cancellation。
- 不把 Fins download / preprocess 改成同步等待工具；长事务仍通过 `ToolAwaitingOutcome` / Host wait-resume contract 表达。
- 不要求所有短工具本 WU 都实现细粒度 checkpoint；但必须完成 token 传递审计与明确风险裁决。

### 实施前置要求

- 先审计 `dayu/fins/tools/`、`dayu/tools/web/`、`dayu/tools/documents/` 及 ToolRuntime dispatch path 的当前 token 使用情况，形成实现计划；不得直接局部加 `is_cancelled()` 作为表面修复。
- 区分 run-level cancel、tool-level cancelled outcome、tool timeout、await wait abandon 和外部 job cancel，不得混淆终态语义。
- 对阻塞网络 / 浏览器 / 文件处理路径，必须评估 token checkpoint 与 timeout 的组合；不能承诺 Python token 能中断已经进入的同步系统调用。
- 对 Fins awaiting 工具，必须覆盖 job 已创建但 awaiting accept 尚未完成时发生 run cancel 的 orphan job 窗口，至少保证同进程取消能使 job 进入 cancelling / cancelled 收口。

### 验收信号

- Focused tests 覆盖 Fins download / preprocess 在 start 前取消、job 创建后取消、wait abandon 后取消的代表路径。
- Focused tests 覆盖 Web tools 在搜索、fetch / requests path、Playwright path 或对应可用 backend 中的取消响应；测试必须证明取消不会等待长耗时操作自然完成。
- ToolRuntime tests 覆盖 cancel 命中 dispatch / accept / awaiting accept 边界时不继续无意义等待。
- 静态审计或 tests 证明当前迁移 tools 不再无条件 `del context` 丢弃 `cancellation_token`；若某工具暂不实现细粒度响应，必须有风险说明和 owner。
- Host / Engine public contract 不变，Fins / Web / Doc README 与 tests README 按触发规则更新当前实现边界。
- pyright、受影响 Fins / Web / Doc / Host ToolRuntime tests 与 `git diff --check` 通过。

## WU-TOOLS-01-F01-03 Production Fins CN/SEC Download And Upload Runtime/Tool Migration

### 状态

Completed。该 work unit 是 `WU-TOOLS-01-F01` draft PR 前置 follow-up，并吸收原 `WU-TOOLS-01-F09`。Goal confirmation artifact 为 `docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md`。当前裁决：Fins 不能只停留在抽象 download / upload contract；CN download、SEC download、CN upload、SEC upload 必须从 OLD 迁移代码并进入真实可用状态。Tool 侧当前可访问，未来 CLI / CI 也必须通过同一 shared Fins service/runtime 访问，避免 CLI / tool / CI 三套逻辑漂移。本 WU 是 OLD 可靠实现迁移与 NEW contract adaptation，不是业务逻辑重写；OLD SEC/CN/HK downloader 与 SEC/CN pipeline download/upload workflow 实现代码不能重写，接口可为 NEW 分层和契约适配。Upload 已由用户裁决为长事务，`start_upload` 已按 awaiting / durable ingestion job 方向接入 tool/provider/wait adapter/service assembly。Aggregate deepreview 已完成并提交，draft PR #131 已创建，PR review 已完成并提交，已按总控裁决归档。

### 动机

F01 已建立 shared Fins service/runtime 作为 read、download、preprocess/process 的业务底座，但真实生产能力仍取决于 source/market 适配器。当前 NEW 仓库证据显示：SEC 侧只有读取 / 解析处理器、download awaiting tool、`FinsSourceDownloadAdapter` 协议和 deterministic fake adapter test path；没有 `SecDownloader` / `SECDownloader` / `SecDownload` 或真实 SEC EDGAR network download adapter。CN download 也没有真实 production adapter。结果是 download tool 只能启动缺 adapter 的 job；没有 upload runtime/tool 时，用户已有的本地财报文件也不能通过 Host-governed tool path 进入 Fins storage。原 `WU-TOOLS-01-F09` 只追踪 upload，会把 download adapter 迁移和 upload 迁移拆成两套入口；这不利于统一 storage 写入、ticker / market 归一化、job lifecycle、cancel、wait-resume、future CLI / CI 调用方式。因此 upload 合并进 F01-03，与 CN / SEC download 一起形成完整 ingestion 可用闭环。

### 目标

- 从 OLD 迁移 CN download 与 SEC download 的真实 source adapter 代码，并接入 shared Fins service/runtime 的 download 入口。
- 从 OLD 迁移 CN upload 与 SEC upload 的真实业务代码，并通过 shared Fins service/runtime 写入 `dayu.fins.storage`。
- ToolDiscovery 暴露可用的 Fins download / upload tool provider；tool 侧只做 schema、ToolRuntime、awaiting / wait-resume 和 evidence / trace adapter，不承载业务逻辑。
- Future CLI 与 future CI 只能调用同一套 shared Fins service/runtime 入口；若本 WU 不实现 CLI / CI 外壳，也必须提供 runtime-level API 与测试证据，使未来入口不需要复制业务规则。
- 所有 CN / SEC download、upload、future CLI、future CI 中的 ticker / market 归一化必须调用 `dayu.fins.ticker_normalization` 真源。
- CN / SEC download 与 upload 的文件、blob、source document、metadata / ingest method、rejected artifact 写入必须且只能通过 `dayu.fins.storage` 仓储协议与实现完成。
- 长事务路径必须继承当前 Host / ToolRuntime awaiting、cancel、resume、late terminal governance；短事务路径也必须通过当前 tool accept path 与 Tool Trace / evidence path 流转。
- 如果本 WU 引入 awaiting external job 形态的 `start_upload`，必须同步更新 GitHub Issue #129，把 `start_upload` 与 `start_download` / `start_preprocess` 一起纳入未来 Host-governed prepare / activate 两段式启动治理；不得为 upload 单独实现私有 activation 绕路。

### 实施前置要求

- 先核对 OLD 中 SecDownloader、CnDownloader 与 upload command runtime 的真实能力、输入参数、错误处理、存储语义、metadata / ingest method、重复 / overwrite 规则和测试覆盖；download / upload 代码必须从 OLD 迁移，NEW 侧只允许做分层 contract、类型、storage、ToolRuntime、awaiting/cancel 和测试适配；若 OLD 能力缺失或不可直接迁移，必须回到 controller 裁决，不得静默重写另一套实现。
- SEC download 必须评估并实现 SEC EDGAR fair access 要求，包括明确 User-Agent 和请求控速；lane 只能治理并发，不等同于每秒请求数控速。
- CN download 必须明确数据来源、请求限制、失败 / 重试 / 编码 / 文件类型处理与本地 artifact 写入语义；不允许把 source-specific 规则散落在 tool schema 或 CLI adapter 中。
- Upload 必须先判断 CN / SEC upload 在 domain metadata、source_kind、filing/material 类型、company/ticker 归一化和文件命名上的差异；不能做成绕过 storage 的通用文件复制工具。
- 先裁决 download / upload 是复用同一个 ingestion job model，还是 upload 走短事务；若 upload 存在文件解析、blob 写入、metadata materialize 等长耗时步骤，优先按 awaiting 长事务接入。
- upload 生命周期裁决必须回写 GitHub Issue #129：若 upload 走 awaiting external job / `start_upload`，#129 必须明确后续拆分 `start_upload` 为 prepare / activate；若 upload 被证明是短事务且没有 awaiting external job，也必须在 #129 记录不适用理由。
- 若 `dayu.runtime.filelock` 或 cancellation work unit 尚未完成，F01-03 plan 必须显式声明依赖顺序或局部风险；不得在 downloader / uploader 中再造私有 runtime helper。

### 非目标

- 不迁移旧 UI / FastAPI / Streamlit ingestion entrypoints。
- 不恢复 OLD ToolRegistry、OLD `file_path_params` path safety、OLD truncation manager 或 OLD `fetch_more`。
- 不从零重写 CN / SEC download 或 upload 业务逻辑；本条是 OLD code migration + NEW contract adaptation，不是重新设计 downloader / uploader。
- 不让 CLI / CI / tool 分别实现 CN / SEC download 或 upload 业务逻辑。
- 不在 downloader、uploader、tool adapter、CLI adapter 或 CI runner 中再造 ticker / market 归一化逻辑。
- 不把 SEC 控速压到 Host lane，lane 只负责 Host 执行并发治理；source-specific rate limit 属于 Fins downloader / runtime。
- 不把 CI pipeline / smoke 的评分闭环并入本条；SEC/Fins CI pipeline / smoke 与 CN/HK Docling CI pipeline / smoke 改由 GitHub Issues #121 / #122 追踪；相关后续必须复用 F01-03 提供的 shared runtime 能力。

### 验收信号

- CN download、SEC download、CN upload、SEC upload 均有 focused tests 覆盖成功、失败、重复 / overwrite、storage 写入、metadata 与 rejected / unsupported artifact 代表路径。
- ToolDiscovery 能发现可用的 download / upload tool provider，工具调用通过当前 ToolRuntime / awaiting 或 accept path 流转。
- Runtime-level tests 证明 future CLI / CI 可以直接调用 shared Fins service/runtime 入口；不存在 CLI / tool / CI 复制业务规则的实现路径。
- 若本 WU 引入 awaiting `start_upload`，GitHub Issue #129 已更新并明确 `start_upload` 的未来 prepare / activate 拆分要求；若 upload 非 awaiting external job，#129 已记录该裁决和不适用理由。
- Tests 或静态审计证明 CN / SEC download 与 upload 的 ticker / market 归一化调用 `dayu.fins.ticker_normalization` 真源。
- SEC download tests 或 adapter contract 覆盖 User-Agent、请求控速和可诊断失败；真实网络路径必须是 explicit opt-in，不进入普通 deterministic CI。
- Fins README、tests README 和总揽 README 按触发规则说明 download / upload 的当前可用边界、shared runtime 同源原则、future CLI / CI 调用方式和 live-network opt-in 策略。
- pyright、受影响 Fins / Host ToolRuntime / tool discovery tests 与 `git diff --check` 通过。

## WU-TOOLS-01-F02 Web CI Diagnostics Pipeline Migration

### 状态

Completed。该 work unit 是 GitHub Issue #120 的第一步，已通过 PR #132 于 2026-06-10 merge。目标不是迁移一个一次性诊断脚本，而是迁移 OLD web CI diagnostics pipeline，使当前 repo 可以日常运行 web CI diagnostics，并把真实外部网站失败样本反馈给 Codex / Web tools 优化流程。Final closeout artifact 为 `docs/reviews/wu-tools-01-f02-final-closeout-controller.md`。F02 completion 已完成，F03 前置条件已满足。

### 动机

WU-TOOLS-01 S5 / S6 已迁移 Web tools，并用 deterministic mock 覆盖 search provider、requests 主路径与 Playwright fallback。剩余缺口不是 Web tools 未迁移，而是真实网络、真实搜索 API、真实网页访问、真实 Playwright 浏览器与 storage state 行为未验证。OLD 流程由 `utils/web_ci_urls.jsonl`、`utils/diag_web.sh`、`utils/diag_web_batch.sh` 和 `utils/diagnose_web_access.py` 组成：URL corpus 驱动单 URL / 批量诊断，脚本对同一个 URL 比较浏览器导航、raw `requests`、仓库 `fetch_web_page` 调用和 Playwright 网络观察，并输出诊断 bucket。它是工程化优化 Web tools 的输入链路，不是简单 smoke。

### 目标

- 将 OLD `utils/web_ci_urls.jsonl`、`utils/diag_web.sh`、`utils/diag_web_batch.sh` 和 `utils/diagnose_web_access.py` 迁移到当前 `dayu-agent-r/utils/`，作为 Web CI diagnostics pipeline。
- 用当前 Web tools contract 适配脚本调用：不得恢复 OLD `ToolRegistry`，不得迁移旧 `truncate` / `fetch_more`，不得绕过当前 ToolDiscovery / ToolRuntime 或当前 Web tool callable adapter。
- 保留诊断能力：浏览器导航摘要、raw `requests` headers / GET 结果、当前 `fetch_web_page` 结果、Playwright 网络请求摘要、storage state 输入 / 输出、批量 URL 诊断与汇总。
- 建立 explicit opt-in web CI diagnostics 入口，用 URL corpus 采集 live requests、fetch、可选 search provider API 与可选 Playwright browser path 的诊断证据。
- web CI diagnostics 必须明确 network / API key / browser installation / storage state / headed mode policy，并默认不进入普通 deterministic CI。
- 诊断输出必须能让 Codex 根据 JSON / JSONL summary 与 per-url diagnostics 分类失败 bucket，并把稳定失败拆成后续 Web tools 优化 work unit。

### 非目标

- 不把 live network / real browser web CI diagnostics 变成普通单元测试或默认 CI gate。
- 不以 web CI 替代 S5 / S6 deterministic provider tests。
- 不在 F02 定义 Web smoke 的 pass / fail gate；F02 完成后该缺口交由 WU-TOOLS-01-F03 生成 smoke 后关闭。
- 不恢复 OLD `dayu.engine.tool_registry`、OLD ToolRegistry path safety、OLD truncation manager 或 OLD `fetch_more`。
- 不重写 Web search / fetch / Playwright 业务 pipeline；只迁移诊断脚本并做当前 contract adapter。
- 不把真实网站偶发失败直接解释为生产代码 regression；web CI 结果必须输出诊断证据和可分类 failure reason。

### 验收信号

- `utils/diagnose_web_access.py`、`utils/diag_web.sh`、`utils/diag_web_batch.sh` 和 `utils/web_ci_urls.jsonl` 可在当前 repo 运行。
- web CI diagnostics 有显式 opt-in 入口和跳过条件；缺少网络、API key 或浏览器依赖时给出清晰 diagnostic，而不是让普通 CI flaky。
- 输出 JSON / JSONL summary 能区分 `all_success`、`browser_only_success`、`fetch_only_failure`、`requests_only_success`、challenge detected、provider authentication / rate limit 等诊断 bucket。
- README / tests README 只描述当前实现：deterministic tests 仍默认无 live network；web CI diagnostics pipeline 是单独显式入口；Web smoke 由 WU-TOOLS-01-F03 生成。

## WU-TOOLS-01-F03 Web CI Smoke Generation

### 状态

Completed。该 work unit 是 GitHub Issue #120 的第二步，依赖 WU-TOOLS-01-F02。F03 已基于迁移后的 diagnostics pipeline 生成直接运行的 Web smoke，固定 local HTML/PDF/Browser 默认 matrix、summary contract、external diagnostic-only 语义和 provider/API 非 gate 边界，并通过 PR #134 于 2026-06-10 merge。Slice 5 closeout artifact 为 `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md`，fix artifact 为 `docs/reviews/wu-tools-01-f03-fix-slice5-codex.md`；default matrix follow-up 验证为 `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q` 36 passed，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` passed。Controller manual smoke 已运行：`source .venv/bin/activate && python utils/smoke_web_ci.py`，exit code 0，output `workspace/output/web_smoke/web-smoke-20260610T051958Z`，summary status passed，local_html、local_pdf、local_browser 均 passed，external_cases 2 且均为 diagnostic_only；browser artifact 观察到 `fetch_web_page_profile.fetch_backend=playwright` 与 `playwright_profile.ok=true`。UI/log follow-up 已补入：`utils/smoke_web_ci.py` 直接运行时打印 `SMOKE ...` UI 输出，按 `dayu/README.md` 日志与可观测性边界输出诊断日志，并新增 `--log-level` 参数，默认 `debug`；follow-up 验证为 `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` 37 passed，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` passed，manual smoke `source .venv/bin/activate && python utils/smoke_web_ci.py` exit code 0，output `workspace/output/web_smoke/web-smoke-20260610T053054Z`，summary status passed，local_cases 3，external_cases 2，diagnostic_only 2，并在 DEBUG 日志中输出各 diagnostics 子进程 stdout/stderr 有界前缀。`WU-TOOLS-01-S5-R2` 已关闭；external site instability 已由 Slice 4 diagnostic-only 设计吸收，不作为 active residual；real browser capability 已由默认 local_browser case 吸收，不作为 active residual；provider/API availability gap 已作为 deferred-with-owner residual tracking entry 转入上方 Residual Risk 表，不是 F03 local Web smoke blocker。GitHub Issue #120 已在 2026-06-21 按 PR #132 / #134 完成事实关闭。

### 动机

日常 web CI 可以持续暴露真实网络、真实浏览器、真实搜索 provider 与真实站点差异，但 residual risk 需要一个明确的验收 smoke：哪些 URL / provider / browser path 属于 smoke 样本，哪些失败应 skip，哪些失败是 diagnostic-only，哪些失败代表 Web tools regression。没有这层 smoke contract，S5-R2 即使在 F02 后仍只能说“有诊断”，不能说“已有可执行的 live coverage gate”。

### 目标

- 基于 F02 迁移后的 `web_ci_urls.jsonl` 与诊断 summary，选取小而稳定的 smoke corpus。
- 定义 Web smoke 的 pass / fail / skip / diagnostic-only 判定规则。
- 覆盖至少 raw `requests` + `fetch_web_page` 的 live 路径；Playwright browser fallback 由默认 local browser case 覆盖，Tavily、Serper 可按配置和环境作为 diagnostic-only 子路径。
- 明确 smoke 对 network、API key、browser installation、storage state、headed / headless 的环境要求。
- 将 smoke 输出设计成 Codex 可读的摘要：失败 bucket、证据文件路径、失败 URL、建议下一步。
- 成功后关闭 `WU-TOOLS-01-S5-R2`，或把仍不稳定的外部站点 / provider 子路径转成带 owner 的新 residual。

### 非目标

- 不把完整 web CI URL corpus 全部变成 smoke gate。
- 不把真实网站偶发失败直接解释为生产代码 regression。
- 不替代 deterministic provider tests；deterministic tests 仍负责固定已知逻辑。
- 不在 F03 重迁移诊断脚本；脚本迁移属于 F02。

### 验收信号

- 存在直接运行的 Web smoke 入口，默认不进入普通 deterministic pytest。
- smoke 在缺少 live network / API key / browser 依赖时能稳定 skip，并输出原因。
- smoke 在满足环境时能运行代表性 URL，并输出 pass / fail / diagnostic-only summary。
- README / tests README 说明 deterministic tests、web CI diagnostics 和 Web smoke 三者的职责区别。
- `WU-TOOLS-01-S5-R2` 被关闭，或 remaining live coverage gap 被转移到新的 owner / issue。

### R3 复核结论

`WU-TOOLS-01-F03-R3` 不是单纯的 provider/API availability residual。代码核对后，该项暴露出两个必须在 F03 follow-up 中补齐的 smoke 面：

- Web tools config assembly：OLD `run.json.web_tools_config` 中的 `provider`、`fetch_truncate_chars`、`playwright_channel`、`playwright_storage_state_dir` 必须完整迁入当前 `tool_discovery.json`，并由 smoke 证明这些配置经 `ConfigLoader -> Service discover_service_tools -> ToolsDiscovery -> web provider -> tool callable` 闭进 `search_web` / `fetch_web_page`。
- Search provider path：smoke 必须覆盖 `search_web` 的 `auto`、Tavily、Serper、DuckDuckGo provider 路径。Tavily / Serper 的 API key 是否存在、auth 是否通过、quota 是否可用、provider 服务是否可达，都要进入 smoke artifact；成功或失败都应输出 provider、bucket、错误摘要和建议下一步。

Tavily / Serper 的 key、quota、auth 与外部 provider 可用性默认是 diagnostic-only：它们要被 smoke 观测和记录，但在没有明确 provider 环境契约前，不把外部 provider 波动升级为 local hard gate。配置装配断裂、默认配置字段缺失、或 assembly 后工具闭包未收到配置，则属于 F03 local smoke blocker。

### R3 Follow-up 方案

- 补齐 `dayu/config/tool_discovery.json` 中 `web-tools.config` 的 `provider`、`fetch_truncate_chars`、`playwright_channel` 与 `playwright_storage_state_dir` 默认值，并让默认 provider discovery 与 scene manifest tool selection 语义对齐。
- 收敛 ToolDiscovery 调用语义：provider 只消费 `discover_tools(spec)` 收到的 effective spec；raw config 与运行时参数（例如 Fins `workspace_root`）的 assembly 是 Service / 调用方职责，provider 不解析全局 runtime config。
- 增加 ConfigLoader / Service assembly 测试，证明 Web provider config 原样进入 `ToolsDiscoveryProviderSpec.config`。
- 增加 Web provider 闭包测试，证明 `provider` 进入 `search_web`，`fetch_truncate_chars` 进入 truncate spec，`playwright_channel` / `playwright_storage_state_dir` 进入 browser fallback 参数。
- 增强 `utils/smoke_web_ci.py`：新增 local assembly config case，走生产式 `ConfigLoader -> Service discover_service_tools -> ToolDefinition.callable`，验证 Web config assembly 和本地 fetch path。
- 增强 `utils/smoke_web_ci.py`：新增 search provider diagnostic cases，至少覆盖 `auto`、`tavily`、`serper`、`duckduckgo`；其中外部 provider 成功、缺 key、鉴权失败、quota/rate limit 或网络失败都写 artifact，默认不影响 local fetch hard gate exit code。

### R3 Plan Gate

Completed。Plan artifact 为 `docs/host/wu-tools-01-f03-r3-web-config-search-smoke-plan.md`。AgentMiMo 与 AgentDS plan review 均裁决 `pass-with-fixes`；review artifacts 为 `docs/reviews/wu-tools-01-f03-r3-plan-review-mimo.md` 与 `docs/reviews/wu-tools-01-f03-r3-plan-review-ds.md`。Controller adjudication 为 `docs/reviews/wu-tools-01-f03-r3-plan-review-controller-adjudication.md`。

Controller 已接受并收敛 review blocking points：`utils/smoke_web_ci.py` 可作为仓库级 smoke harness import `ConfigLoader` 与 `discover_service_tools()`；local assembly / search provider smoke 使用显式 `package_config_dir=dayu/config` 与临时 `workspace_config_dir`，只 overlay `tool_discovery.json` 并调用完整 `ConfigLoader.load()`；summary 使用 typed `search_cases`，不新增 `metadata` 弱类型字段；local assembly artifact 必须证明 `fetch_truncate_chars` 进入 provider config 与 truncate spec；pytest 不做 live network / credential。

### R3 Implementation Gate

Completed locally。Implementation artifact 为 `docs/reviews/wu-tools-01-f03-r3-implementation-codex.md`。

已完成：

- `dayu/config/tool_discovery.json` 的 `web-tools.config` 默认字段补齐，并保持默认 provider discovery 可用；private / local network URL 仍默认拒绝。
- 调用方先用 `assemble_effective_tool_provider_configs(...)` 把 raw provider config 与运行时 workspace 装配成 effective spec；`discover_service_tools(...)` 只接收 effective provider configs 并执行 discovery。Fins provider raw config 中 `workspace_root=null` 时可由 runtime workspace 注入，显式绝对 `workspace_root` 不被覆盖。
- ConfigLoader / Service assembly 测试覆盖默认 Web config typed view、Web config 原样进入 `ToolsDiscoveryProviderSpec.config`，以及完整 `ConfigLoader.load()` + `discover_service_tools()` 发现 `search_web` / `fetch_web_page`。
- Web provider deterministic tests 覆盖 search provider config 闭包、`fetch_truncate_chars` truncate spec、Playwright fallback channel 与空/非空 storage state dir。
- `utils/smoke_web_ci.py` 默认新增 local assembly config hard gate，直接走 `ConfigLoader.load()`、`assemble_effective_tool_provider_configs()`、`discover_service_tools()` 与 `ToolDefinition.callable`，artifact 证明 overlay config 与 `truncate_max_chars`。
- `utils/smoke_web_ci.py` 默认新增 `auto` / `tavily` / `serper` / `duckduckgo` search provider diagnostic-only cases，summary 使用 typed `search_cases`，`external_cases` 只保留外部 URL fetch cases，不新增 metadata 弱类型字段，不写 secret。
- `tests/README.md` 已按落地事实更新；`dayu/config/README.md` 已声明相关字段与职责，未修改。

验证结果：

- `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`：133 passed。
- `python -m pyright dayu/ tests/ utils/`：0 errors。
- `python utils/smoke_web_ci.py`：exit code 0，output `workspace/output/web_smoke/web-smoke-20260610T070642Z`，summary status passed，local_cases 4，external_cases 2，search_cases 4，diagnostic_only 6。
- `git diff --check`：passed。

下一步进入 R3 code review gate。

### R3 Code Review / Fix / Re-review Gate

Completed。Code review artifacts 为 `docs/reviews/wu-tools-01-f03-r3-code-review-mimo.md` 与 `docs/reviews/wu-tools-01-f03-r3-code-review-ds.md`。AgentDS 裁决 `pass`；AgentMiMo 裁决 `pass-with-findings`。Controller adjudication 为 `docs/reviews/wu-tools-01-f03-r3-code-review-controller-adjudication.md`。

Controller 接受 MiMo F1 / F2 / F4 进入 fix gate：Docling invocation blocker early return 时仍需运行 `search_cases`，`discovered_configs` 不能使用 `list[object]`，`_tool_context()` 中的 `cast(CancellationToken, ...)` 应移除。Fix artifact 为 `docs/reviews/wu-tools-01-f03-r3-fix-codex.md`。Re-review artifacts 为 `docs/reviews/wu-tools-01-f03-r3-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f03-r3-rereview-ds.md`，两路 re-review 均裁决 `pass`，无新增 blocking findings。

Controller 复验：`pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` 39 passed，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` passed。Implementation / fix artifacts 记录完整指定测试组合 133 passed；Controller 最终 manual smoke exit 0，output 为 `workspace/output/web_smoke/web-smoke-20260610T070642Z`，summary status passed，local_cases 4，external_cases 2，search_cases 4，diagnostic_only 6。

`WU-TOOLS-01-F03-R3` 已关闭并从 active residual table 移除。Tavily / Serper 的 key、auth、quota、rate limit 与外部 provider 可用性继续作为 smoke diagnostic-only 观测，不作为 local hard gate。

### R3 Effective Spec Follow-up

Completed。Follow-up review artifacts 为 `docs/reviews/wu-tools-01-f03-r3-effective-spec-review-mimo.md` 与 `docs/reviews/wu-tools-01-f03-r3-effective-spec-review-ds.md`。Controller adjudication 为 `docs/reviews/wu-tools-01-f03-r3-effective-spec-review-controller-adjudication.md`。

Controller 裁决：DS F1 原结论不成立。`web-tools.enabled=true` 只让 Web tools 进入 construction-time candidate `ToolBundle`；实际 per-run 可见性由 scene manifest `tool_selection` 和 Host `SubmitFollowupRequest.tool_names` 决定。`allow_empty=true` 只允许 provider 成功返回空工具集合，不吞 import failure。真实需修复的问题是 discovery 与 compose 不能各自从 raw config 独立重算 effective config。

已完成：

- `ServiceDiscoveredTools` 新增 `effective_provider_configs`，保存调用方传给 `discover_service_tools(...)` 并实际用于 `ToolsDiscovery` 的 effective provider configs。
- `compose_open_host_options(...)` 复用 `request.discovered_tools.effective_provider_configs` 构造 Host tooling / Fins wait adapter registry，避免 Fins tool closure 与 wait adapter registry 使用不同 workspace。
- Service tests 新增 Fins workspace-bound provider 识别边界、discovery -> compose effective config 复用集成测试，并更新 Host smoke assembly tests，明确 construction-time discovered tools 与 scene-selected tools 的边界。
- Web smoke tests 新增 search provider HTTP status / error text 分类、ConfigLoader hard failure、discovery hard failure、callable timeout diagnostic-only 与 empty result diagnostic-only 覆盖。
- `dayu/config/tool_discovery.json` 中默认 discovery provider 语义统一为 `enabled=true`：discovery 只暴露候选工具包，实际可见工具仍由 scene manifest 与 Host per-run `tool_names` 决定。Fins upload provider 在 `allowed_upload_roots=[]` 时返回空工具集，保持默认 discovery 可用但上传工具 fail closed。
- 默认 enabled / effective discovery 边界修正已完成：调用方显式执行 `assemble_effective_tool_provider_configs(...)`，`discover_service_tools(...)` 只接收 effective provider configs；upload 空 allowlist 不注册工具，也不会绑定 `start_fins_upload` wait adapter。AgentDS re-review artifact 为 `docs/reviews/wu-tools-01-f03-default-enabled-effective-discovery-rereview-ds.md`，裁决 pass；AgentMiMo 简短 re-review 裁决 pass-with-findings，无 blocking findings。

Re-review artifacts 为 `docs/reviews/wu-tools-01-f03-r3-effective-spec-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f03-r3-effective-spec-rereview-ds.md`；两路均裁决 pass，无新增 correctness / type / layering findings。

Controller 复验：

- `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`：179 passed。
- `pyright dayu tests utils`：0 errors。
- `python utils/smoke_web_ci.py`：exit code 0，output `workspace/output/web_smoke/web-smoke-20260610T074838Z`，summary status passed，local_cases 4，external_cases 2，search_cases 4，diagnostic_only 6。
- `git diff --check`：passed。

## WU-TOOLS-01-F08 Documents Processor Registry Naming Cleanup

### 状态

Final closeout passed；PR #135 已于 2026-06-11 merge。该 work unit 已关闭 `WU-TOOLS-01-S1-R2`，清理迁移后遗留的 OLD `engine` 命名，不改变 processor registry 行为。

Plan gate 已完成。Goal confirmation artifact 为 `docs/reviews/wu-tools-01-f08-goal-confirmation-controller.md`。Accepted plan artifact 为 `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`，accepted plan commit 为 `a0c00567`。Plan review artifacts 为 `docs/reviews/wu-tools-01-f08-plan-review-mimo.md`、`docs/reviews/wu-tools-01-f08-plan-review-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f08-plan-review-controller-adjudication.md`。Plan fix artifact 为 `docs/reviews/wu-tools-01-f08-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/wu-tools-01-f08-plan-rereview-mimo.md`、`docs/reviews/wu-tools-01-f08-plan-rereview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f08-plan-rereview-controller-adjudication.md`。两路 re-review 均裁决 pass，0 条 blocking finding。Implementation artifact 为 `docs/reviews/wu-tools-01-f08-implementation-codex.md`，accepted implementation commit 为 `f669942e`。Code review artifacts 为 `docs/reviews/wu-tools-01-f08-code-review-mimo.md`、`docs/reviews/wu-tools-01-f08-code-review-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f08-code-review-controller-adjudication.md`；两路 code review 均裁决 pass，0 条 accepted finding。Aggregate deepreview artifacts 为 `docs/reviews/wu-tools-01-f08-aggregate-deepreview-mimo.md`、`docs/reviews/wu-tools-01-f08-aggregate-deepreview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f08-aggregate-deepreview-controller-adjudication.md`；两路 aggregate deepreview 均裁决 pass，0 条 accepted finding；accepted deepreview commit 为 `12812074`。PR review artifacts 为 `docs/reviews/wu-tools-01-f08-pr-review-mimo.md`、`docs/reviews/wu-tools-01-f08-pr-review-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f08-pr-review-controller-adjudication.md`；PR body 已补齐 local validation 输出和 no-checks 说明，CI workflow 以后单独配置，不作为当前 residual 追踪。Final closeout artifact 为 `docs/reviews/wu-tools-01-f08-final-closeout-controller.md`；PR #135 已于 2026-06-11 merge。

### 动机

原旧名 builder 位于 `dayu.documents.processors.registry`，实际注册的是通用 documents processor：Docling、Markdown 与 BS。Doc tools 和 Fins 都把它作为 documents 默认 processor registry 使用；它不属于 Engine。F08 已将稳定入口收敛为 `build_documents_processor_registry(...)`，避免 `engine` 命名误导 ownership。

### 目标

- 将 documents 默认 processor registry builder 稳定命名为 `build_documents_processor_registry(...)`。
- 同步更新 `dayu.documents.processors.__all__`、`dayu.documents.processors._doc_processor_factory`、`dayu.fins.processors.registry`、测试和 README / 文档引用。
- 保持 processor 注册顺序与行为不变：DoclingProcessor、MarkdownProcessor、BSProcessor 仍按当前优先级注册。
- 证明 Fins registry 仍先加载 documents 默认 registry，再覆盖注册 Fins 专属 processor。

### 非目标

- 不重构 `ProcessorRegistry` 行为。
- 不改变 Docling / Markdown / BS / Fins processor 优先级或 fallback 规则。
- 不新增旧名兼容 re-export、wrapper 或 facade；当前代码和文档必须全量改到新名。

### 验收信号

- 旧 builder 名称在生产代码、测试和稳定 README / control doc 中无残留；历史 review artifact 可保留。
- Documents / Fins processor registry focused tests 证明行为不变。
- import-boundary tests 与 pyright 通过。
- 相关 README 只描述新命名和当前 ownership，不保留新旧术语并存。

### Implementation validation

- 稳定目标旧名清理检查：passed，无匹配。
- 历史 review artifact 检查：passed，仅历史 review / plan review artifact 保留旧名留痕。
- Focused registry tests：`pytest tests/documents/test_processors.py tests/fins/test_processor_registry.py -q`，5 passed，3 warnings。
- 相关包测试：`pytest tests/documents tests/fins -q`，263 passed，1 skipped，3 warnings；`tests/fins` 未出现 heavy fixture / environment failure。
- 类型检查：`python -m pyright dayu/ tests/ utils/`，0 errors，0 warnings，0 informations。
- Whitespace：`git diff --check`，passed。

## WU-TOOLS-01-F09 Fins Upload Ingestion Migration And Upload Tool

### 状态

Merged into `WU-TOOLS-01-F01-03`。该 work unit 不再单独实施。原 upload follow-up 的全部目标、边界和验收信号已并入 F01 draft PR 前置 follow-up `WU-TOOLS-01-F01-03`，与 CN / SEC download 真实可用能力一起推进。

### 动机

Upload 原本被拆成独立 follow-up，是为了防止 F01 已完成范围被扩大。但继续让 upload 单独排队会把 ingestion 能力拆成 download 一条线、upload 另一条线，未来 CLI / CI / tool 很容易再次分叉。现在裁决为：CN download、SEC download、CN upload、SEC upload 一起进入 F01-03 的 shared Fins service/runtime 闭环，upload 不再有独立 owner。

### 目标

- 见 `WU-TOOLS-01-F01-03`。

### 非目标

- 见 `WU-TOOLS-01-F01-03`。

### 验收信号

- `WU-TOOLS-01-F09` 在 Work Units 表中保持 `merged-into` 状态，不再作为 active / pending WU 出现。
- Upload 相关验收由 `WU-TOOLS-01-F01-03` 承接。

## WU-PROJ-01 Compact Material Truth And Bounded Memory Catch-up

### 状态

由 GitHub Issue #86 跟踪并实施。

### 第一性原理裁决

本条不是 context window token 超限修复。`soft_threshold_context_ratio` / `context_window_tokens` 触发 compact 属于 Context Governance 的预算裁决；本条修复的是 pre-dispatch compact / Conversation Memory projection 的职责错位和无界补账风险。

Compact operation 的事实闭环应为：

```text
EventLog / payload descriptor / artifact truth
  -> EventLog-backed compact material builder
  -> ConversationCompactInputVNext
  -> Host-owned compactor
  -> Host accept barrier
  -> CONTEXT_COMPACTED canonical fact
```

Conversation Memory projection 只在 accepted compact fact 提交后消费 EventLog，物化 ordinary RunInput 使用的 session read model；它不是 compact input 的前置真源。Context Governance 只负责读取同源 material view、估算预算、裁决 allow dispatch / compact / fallback / fail closed，并编排 bounded compaction operation；它不拥有 material 语义。

### 代码核对结论

- 当前 proactive Context Governance 的预算估算只使用当前用户输入文本，不能代表完整 ordinary input material，也不能覆盖 compact 后多轮 post-compact delta 再次触发 compact 的真实场景。
- 当前 proactive compact material helper 只构造 accepted tool evidence 与 current input anchor，没有完整构造 latest accepted compacted view、post-compact trace / answer delta 与 current input anchor 的 rolling compact input。
- 当前 proactive compact 构造 material pack 时没有传入 previous compacted view；第二次及后续 compact 不能稳定形成 `previous_compacted_view + post_compact_delta_material + current_input_anchor`。
- `ProjectionRunner` 的设计是每条 EventLog row 在同一个 write transaction 内完成 consumer write 与 checkpoint advance；若出现“projection runner 已成功应用 event 但 checkpoint 未推进”，应作为直接 cursor bug 修复。但当前 WU 的主要证据指向 pre-dispatch compact material 真源路径不完整，以及 ordinary memory catch-up / rebuild 无单次总预算。

### 目标

- 修复 proactive compact 的 material truth：compact input 必须从 EventLog / payload descriptor / artifact 真源构造，不得依赖 Conversation Memory projection checkpoint 作为 compact input 的前置真源。
- 为 pre-dispatch compact 建立或收敛 EventLog-backed compact material builder：latest accepted `CONTEXT_COMPACTED` 生成 `previous_compacted_view`，latest compact 之后到当前 input 之前的 committed canonical facts 生成 post-compact delta material，当前 `USER_INPUT_ACCEPTED` 生成 current input anchor。
- Context Governance 只消费同源 material view 做预算估算、segment selection 和 compact / fallback / fail-closed 裁决；不得在 Context Governance 内临时拼接不完整 material。
- 第二次及后续 compact 必须实现 rolling compact 语义：只输入 previous accepted compacted view、selected post-compact delta material 与 current input anchor；不得重新展开上一轮 accepted compact 覆盖的旧 raw history。
- accepted `CONTEXT_COMPACTED` 提交后，再由 Conversation Memory projection 消费并物化 ordinary RunInput 使用的 session summary、facts、answer anchors、forward intents 和 reference continuity items。
- ordinary dispatch 读取 Conversation Memory snapshot 时，memory projection catch-up / rebuild 必须具备总预算，而不仅是单批大小，例如 max batches、max scanned events、timeout 或等价 bounded execution policy。
- 明确 admission after-commit 的 memory catch-up 只能是 bounded best-effort 或 wake background supervisor，不得在 command path 上无上限追平。
- 明确 dispatch 前 ordinary memory catch-up / rebuild 的行为：成功追到 required cursor 时继续 dispatch；超预算或失败时产生结构化 diagnostic，且不得触发 Run recovery。

### 非目标

- 不改变 EventLog 作为投影真源的语义。
- 不把 Conversation Memory projection 提升为 compact input 真源。
- 不让 Context Governance 拥有 material 语义、memory snapshot 写入或 projection checkpoint 推进。
- 不让 projection lag 影响 recovery truth。
- 不把 Audit / Tool Trace / Outbox 纳入本条。
- 不重写 ProjectionRunner 为大型调度系统。
- 不把所有 projection sink 合并成 God runner。
- 不修复 context window token 超限本身；context budget / compaction retry / fallback 的通用策略仍按 `docs/host/design.md` 的 Context Governance 章节执行。

### 验收信号

- proactive compact 的预算估算使用完整同源 material view，不再只估当前 user prompt。
- pre-dispatch compact input 可由 EventLog / payload / artifact truth 构造 `previous_compacted_view + post_compact_delta_material + current_input_anchor`，并覆盖第二次及后续 rolling compact。
- compact material build 不依赖 Conversation Memory projection checkpoint；memory snapshot lag 不阻断 compact input 构造。
- accepted compact 后 Conversation Memory projection 消费 `CONTEXT_COMPACTED` 并推进 snapshot / checkpoint，ordinary RunInput 可读取 accepted compact 物化出的 session summary / facts / anchors / intents / reference continuity。
- memory projection catch-up 的单批大小与单次总预算边界均有明确代码或配置表达。
- admission after-commit catch-up 不会无上限同步追平大量 EventLog。
- dispatch 前 memory catch-up / rebuild 超预算或失败时有结构化 diagnostic，且不会改写 EventLog / Run / Attempt governance truth。
- 测试覆盖 rolling compact、post-compact delta 不重展旧 raw history、bounded catch-up、required cursor 已覆盖、lag / failure / rebuild 超预算不误触发 recovery，以及 Audit / Tool Trace / Outbox 不被改成 command-path blocking sink。

### Plan gate

- plan artifact: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- plan status: ready
- produced by: AgentCodex
- controller decision: accepted for plan review
- review artifacts:
  - `docs/reviews/plan-review-20260611-124757.md`
  - `docs/reviews/wu-proj-01-plan-review-ds.md`
- controller adjudication: `docs/reviews/wu-proj-01-plan-review-controller-adjudication.md`
- review verdict:
  - AgentMiMo: `pass-with-risks`
  - AgentDS: `needs-fix`
- controller decision after review: plan fix required
- accepted plan fix scope:
  - fix validation commands to use actual dispatch compact / proactive governance tests and public compact smoke.
  - clarify `build_compact_material_pack` interface path for EventLog-backed previous compacted view.
  - clarify evidence de-dup source, memory projection budget injection path, default module placement, reactive minimal adaptation boundary, no `timeout_seconds` in first version, Slice 4 fixture source, first compact cursor semantics, budget fragment mapping, and material source failure fail-closed behavior.
- plan fix artifact: `docs/reviews/wu-proj-01-plan-fix-codex.md`
- plan fix status: completed by AgentCodex; plan status is `code-generation-ready after AgentCodex plan fix`
- plan fix validation: not run; plan text fix only
- re-review artifacts:
  - `docs/reviews/wu-proj-01-plan-rereview-mimo.md`
  - `docs/reviews/wu-proj-01-plan-rereview-ds.md`
- re-review controller adjudication: `docs/reviews/wu-proj-01-plan-rereview-controller-adjudication.md`
- re-review verdict:
  - AgentMiMo: `pass`
  - AgentDS: `pass`
- controller decision after re-review: accepted plan; proceed to accepted plan commit
- deferred implementation validation note: AgentDS NF1 is deferred-with-owner to implementation gate; validation must include `python -m pytest tests/host/test_memory_repair.py`, and if `tests/host/test_memory_projection_repair.py` is added, it must also run.
- accepted plan commit: `fb3cc9ec`

### Slice 1 implementation gate

- slice: EventLog-backed pre-dispatch compact material source
- implementation artifact: `docs/reviews/wu-proj-01-slice1-implementation-codex.md`
- implemented by: AgentCodex
- changed files:
  - `dayu/host/compact_material.py`
  - `tests/host/test_compact_material.py`
  - `dayu/host/README.md`
  - `tests/README.md`
- validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py` passed, 28 tests
  - `source .venv/bin/activate && pyright` passed, 0 errors
  - `git diff --check` passed by controller
- controller decision: accepted for code review
- review artifacts:
  - `docs/reviews/wu-proj-01-slice1-code-review-mimo.md`
  - `docs/reviews/wu-proj-01-slice1-code-review-ds.md`
- review verdict:
  - AgentMiMo: `pass-with-findings`
  - AgentDS: `PASS`
- code review controller adjudication: `docs/reviews/wu-proj-01-slice1-code-review-controller-adjudication.md`
- accepted fix scope:
  - add direct negative tests for `CompactMaterialSourceBoundary` validation.
  - add direct negative tests for `PreDispatchCompactMaterialView` boundary mismatch validation.
  - clarify fallback `tool_call_event_ref` semantics when durable request atom is missing.
  - remove `_snapshot_with_goal` unused `current_goal` parameter or otherwise eliminate the misleading helper API.
  - fix `_snapshot_with_goal_and_fact` fixture provenance so it does not reference a non-existent EventLog event id.
- fix artifact: `docs/reviews/wu-proj-01-slice1-fix-codex.md`
- fix status: completed by AgentCodex
- fix validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py` passed, 31 tests
  - `source .venv/bin/activate && pyright` passed, 0 errors
  - `git diff --check` passed by controller
- re-review artifacts:
  - `docs/reviews/wu-proj-01-slice1-rereview-mimo.md`
  - `docs/reviews/wu-proj-01-slice1-rereview-ds.md`
- re-review verdict:
  - AgentMiMo: `PASS`
  - AgentDS: `PASS`
- re-review controller adjudication: `docs/reviews/wu-proj-01-slice1-rereview-controller-adjudication.md`
- controller decision after re-review: accepted; proceed to accepted slice commit
- accepted slice commit: `1b4e7b67`

### Slice 2 implementation gate

- slice: Proactive Context Governance uses same-source material view
- status: implementation completed; code review pending
- owner: AgentCodex
- entry point: WU-PROJ-01 Slice 2 implementation gate
- inherited residual risk: `WU-PROJ-01-S1-R1` requires Slice 2 to confirm `_readable_query_text_from_envelope` full query atom path coverage or add focused test if missing.
- implementation artifact: `docs/reviews/wu-proj-01-slice2-implementation-codex.md`
- changed files:
  - `dayu/host/dispatch.py`
  - `dayu/host/engine_ingest.py`
  - `tests/host/test_compact_material.py`
  - `tests/host/test_dispatch_scheduler.py`
- validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py` passed, 32 tests
  - `source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"` passed, 18 tests
  - `source .venv/bin/activate && python -m pytest tests/host/test_public_compact_smoke.py` passed, 6 tests and 1 skipped
  - `source .venv/bin/activate && pyright` passed, 0 errors
  - `git diff --check` passed by controller
- controller decision: accepted for code review
- review artifacts:
  - `docs/reviews/wu-proj-01-slice2-code-review-mimo.md`
  - `docs/reviews/wu-proj-01-slice2-code-review-ds.md`
- review verdict:
  - AgentMiMo: `APPROVE`
  - AgentDS: `PASS`
- code review controller adjudication: `docs/reviews/wu-proj-01-slice2-code-review-controller-adjudication.md`
- accepted fix scope:
  - add focused test for `_proactive_fallback_material_blocks` current input de-duplication boundary.
  - add test comment explaining why `test_multi_turn_proactive_compact_feeds_subsequent_run_input` uses a wider hard threshold after same-source material estimation.
- fix artifact: `docs/reviews/wu-proj-01-slice2-fix-codex.md`
- fix status: completed by AgentCodex
- fix validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"` passed, 19 tests
  - `source .venv/bin/activate && pyright` passed, 0 errors
  - `git diff --check` passed by controller
- re-review artifacts:
  - `docs/reviews/wu-proj-01-slice2-rereview-mimo.md`
  - `docs/reviews/wu-proj-01-slice2-rereview-ds.md`
- re-review verdict:
  - AgentMiMo: `APPROVE`
  - AgentDS: `PASS`
- re-review controller adjudication: `docs/reviews/wu-proj-01-slice2-rereview-controller-adjudication.md`
- controller decision after re-review: accepted; proceed to accepted slice commit
- accepted slice commit: `8e9d42ea`

### Slice 3 implementation gate

- slice: Bounded memory projection catch-up / rebuild
- status: implementation completed; code review pending
- owner: AgentCodex
- entry point: WU-PROJ-01 Slice 3 implementation gate
- inherited validation note: implementation validation must include `python -m pytest tests/host/test_memory_repair.py`; if `tests/host/test_memory_projection_repair.py` is added, it must also run.
- inherited residual risk: `WU-PROJ-01-S2-R1` material source failure exception taxonomy is deferred to Slice 3 diagnostic / later context governance diagnostic cleanup.
- implementation artifact: `docs/reviews/wu-proj-01-slice3-implementation-codex.md`
- changed files:
  - `dayu/host/memory_repair.py`
  - `dayu/host/dispatch.py`
  - `dayu/host/open_host.py`
  - `tests/host/test_memory_repair.py`
  - `tests/host/test_open_host_runtime.py`
  - `tests/host/test_logging.py`
- validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_memory_repair.py` passed, 9 tests
  - `source .venv/bin/activate && python -m pytest tests/host/test_open_host_runtime.py` passed, 12 tests
  - `source .venv/bin/activate && python -m pytest tests/host/test_logging.py` passed, 4 tests
  - `source .venv/bin/activate && pyright` passed, 0 errors
  - `git diff --check` passed by controller
- controller decision: accepted for code review
- review artifacts:
  - `docs/reviews/wu-proj-01-slice3-code-review-mimo.md`
  - `docs/reviews/wu-proj-01-slice3-code-review-ds.md`
- review verdict:
  - AgentMiMo: `PASS-WITH-FINDINGS`
  - AgentDS: `APPROVE`
- code review controller adjudication: `docs/reviews/wu-proj-01-slice3-code-review-controller-adjudication.md`
- controller decision after code review: accepted; no fix gate required; proceed to accepted slice commit
- accepted slice commit: `a658ee1f`

### Slice 4 implementation gate

- slice: Accepted compact -> Conversation Memory -> ordinary RunInput regression
- status: accepted
- owner: AgentCodex
- entry point: WU-PROJ-01 Slice 4 implementation gate
- inherited residual risk: `WU-PROJ-01-S3-R1` dispatch before-worker catch-up happy path may be covered here if fixture naturally touches ordinary RunInput; otherwise remains later Host dispatch test hardening.
- implementation artifact: `docs/reviews/wu-proj-01-slice4-implementation-codex.md`
- changed files:
  - `tests/host/test_memory_projection.py`
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_dispatch_scheduler.py`
- validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -k "compact_failure_is_attempt_free or compact or governance"` passed, 25 tests and 103 deselected
  - `source .venv/bin/activate && pyright` passed, 0 errors
  - `git diff --check` passed by controller
- controller decision: accepted for code review
- review artifacts:
  - `docs/reviews/wu-proj-01-slice4-code-review-mimo.md`
  - `docs/reviews/wu-proj-01-slice4-code-review-ds.md`
- review verdict:
  - AgentMiMo: `PASS-WITH-FINDINGS`
  - AgentDS: `PASS`
- code review controller adjudication: `docs/reviews/wu-proj-01-slice4-code-review-controller-adjudication.md`
- controller decision after code review: accepted; no fix gate required; proceed to accepted slice commit
- accepted slice commit: `08709fe9`
- residual risk:
  - `WU-PROJ-01-S3-R1` remains deferred-with-owner to Host dispatch test hardening.
  - `WU-PROJ-01-S4-R1` records an existing dispatch scheduler flaky observation from review; not a Slice 4 blocker.

### Aggregate deepreview gate

- status: completed
- owner: AgentMiMo / AgentDS
- entry point: WU-PROJ-01 aggregate deepreview gate
- review artifacts:
  - `docs/reviews/wu-proj-01-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-proj-01-aggregate-deepreview-ds.md`
- verdict:
  - AgentMiMo: `PASS-WITH-FINDINGS`
  - AgentDS: `PASS`
- controller adjudication: `docs/reviews/wu-proj-01-aggregate-deepreview-controller-adjudication.md`
- findings:
  - AgentMiMo NF1 (Low): `_memory_projection_catchup_budget` unsupported purpose 分支无测试 — rejected-as-nonblocking；defensive guard.
  - AgentMiMo NF2 (Low): dispatch before-worker catch-up happy path 无独立集成测试 — deferred to `WU-PROJ-01-S3-R1`.
  - AgentMiMo NF3 (Low): `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` lane timeout flaky — deferred to `WU-PROJ-01-S4-R1`.
  - AgentDS Low observations: accepted as nonblocking maintainability notes; no fix gate required.
- blocking findings: 无
- residual risks:
  - `WU-PROJ-01-S3-R1` deferred-with-owner to Host dispatch test hardening — 不阻塞 draft PR gate
  - `WU-PROJ-01-S4-R1` deferred-with-owner to Host dispatch scheduler test hardening — 不阻塞 draft PR gate
- validation:
  - 68 passed, 1 skipped, 123 deselected
  - 143 aggregate focused tests passed by AgentDS
  - pyright: 0 errors, 0 warnings, 0 informations
- controller decision: accepted; no aggregate fix gate; proceed to draft PR gate
- accepted deepreview commit: `84e40096`

### Draft PR gate

- status: completed
- branch: `wu-proj-01`
- remote: `github`
- draft PR: `https://github.com/noho/dayu-agent-r/pull/136`
- title: `WU-PROJ-01 compact material truth and bounded memory catch-up`
- PR body includes:
  - summary of compact material truth, proactive governance material view, bounded memory projection catch-up / rebuild, and regression coverage.
  - validation summary.
  - residual risks `WU-PROJ-01-S3-R1` and `WU-PROJ-01-S4-R1`.
- next gate: WU-PROJ-01 PR review gate via AgentMiMo / AgentDS

### PR review gate

- status: fix-required
- owner: AgentMiMo / AgentDS
- review artifacts:
  - `docs/reviews/wu-proj-01-pr-review-mimo.md`
  - `docs/reviews/wu-proj-01-pr-review-ds.md`
- verdict:
  - AgentMiMo: `PASS-WITH-FINDINGS`
  - AgentDS: `FAIL`
- controller adjudication: `docs/reviews/wu-proj-01-pr-review-controller-adjudication.md`
- accepted findings:
  - `PR-F1`: 3 个旧 dispatch scheduler 测试在 PR 分支失败但在 `main` 通过；更新测试断言以匹配 WU-PROJ-01 fail-closed 新设计。
  - `PR-F2`: PR body validation 描述不完整；fix 后改为报告完整受影响测试文件结果。
- next gate: WU-PROJ-01 PR review fix gate via AgentCodex

### PR review fix / re-review gate

- status: completed
- fix owner: AgentCodex
- fix artifact: `docs/reviews/wu-proj-01-pr-review-fix-codex.md`
- changed files:
  - `tests/host/test_dispatch_scheduler.py`
  - `docs/host/issues-implementation-control.md`
- PR body: updated via `gh pr edit 136`; validation now reports complete affected Host test files `185 passed`, pyright `0 errors`, and `git diff --check` pass.
- fix validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_logging.py tests/host/test_open_host_runtime.py` passed, 185 tests
  - `source .venv/bin/activate && pyright` passed, 0 errors
  - `git diff --check` passed
- re-review artifacts:
  - `docs/reviews/wu-proj-01-pr-review-rereview-mimo.md`
  - `docs/reviews/wu-proj-01-pr-review-rereview-ds.md`
- re-review verdict:
  - AgentMiMo: `PASS`
  - AgentDS: `PASS`
- re-review controller adjudication: `docs/reviews/wu-proj-01-pr-review-rereview-controller-adjudication.md`
- controller decision: accepted; proceed to accepted PR review commit
- accepted PR review commit: `10322580`
- push status: accepted PR review commit and draft-PR-pass bookkeeping pushed to PR #136 before final closeout

### Final closeout

- status: superseded-by-user-decision
- closeout artifact: `docs/reviews/wu-proj-01-final-closeout-controller.md`
- draft-PR-pass bookkeeping commit before final closeout: `171b6cd2`
- draft PR: `https://github.com/noho/dayu-agent-r/pull/136`
- issue owner: GitHub Issue #86; PR body links `Closes #86`, so issue closure should happen through PR merge.
- final validation:
  - full affected Host test files passed, 185 tests.
  - pyright passed, 0 errors.
  - `git diff --check` passed.
- residual risks:
  - `WU-PROJ-01-S3-R1` was previously deferred-with-owner to Host dispatch test hardening.
  - `WU-PROJ-01-S4-R1` was previously deferred-with-owner to Host dispatch scheduler test hardening.
- superseding decision: `docs/reviews/wu-proj-01-residual-risk-user-decision-controller.md`
- next entry point: WU-PROJ-01 residual risk implementation gate via AgentCodex.

### Residual risk user decision

- status: active
- decision artifact: `docs/reviews/wu-proj-01-residual-risk-user-decision-controller.md`
- user decision: `WU-PROJ-01-S3-R1`, `WU-PROJ-01-S4-R1`, and `WU-PROJ-01-CAP-R1` must be implemented in PR #136.
- cap / limit first-principles decision:
  - Do not solve `_READABLE_QUERY_TEXT_MAX_CHARS`, `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS`, `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS`, `_MEMORY_PROJECTION_*_MAX_BATCHES` by merely moving them to a config file.
  - Compact material source should read the complete canonical EventLog delta from latest accepted compact to current input, then let Context Governance / segment selection decide what fits the LLM-facing compact input.
  - Source builder must not silently degrade memory quality by truncating readable query text or imposing fixed evidence / event caps.
  - Required-before-dispatch and rebuild projection catch-up should run until required cursor is reached, idle, or failure; fixed max batch / max scanned event limits must not be production correctness semantics.
  - After-commit best-effort may remain bounded only as a non-correctness optimization; it must not be confused with required dispatch catch-up.
- next gate: WU-PROJ-01 residual risk implementation gate via AgentCodex.

### Residual risk implementation gate

- status: completed
- owner: AgentCodex
- implementation commits: CAP-R1 `448b70ba`, S3/S4 `3baeef53`, aggregate fix `bd6488df`
- aggregate deepreview artifacts:
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-controller-adjudication.md`
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-fix-codex.md`
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-rereview-controller-adjudication.md`
- controller verification:
  - `python -m pytest tests/host/test_memory_repair.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py` -> 91 passed
  - `pyright` -> 0 errors
  - `git diff --check` -> passed
- residual risk closures:
  - `WU-PROJ-01-CAP-R1`: fixed caps removed from compact material source; `_bounded_query_text()` replaced by `_normalized_query_text()`; dispatch required catch-up uses `budget=None` (no fixed upper bound)
  - `WU-PROJ-01-S3-R1`: dispatch before-worker catch-up happy-path coverage added; required cursor already covered -> ordinary RunInput continues without repeated catch-up
  - `WU-PROJ-01-S4-R1`: lane-timeout flaky dispatch scheduler test stabilized via timing fixture adjustment
- next gate: PR review gate via AgentMiMo / AgentDS

### Residual risk PR review gate

- status: completed and pushed
- owner: AgentMiMo / AgentDS review; AgentCodex fix
- review artifacts:
  - `docs/reviews/wu-proj-01-pr-review-residual-mimo.md`
  - `docs/reviews/wu-proj-01-pr-review-residual-ds.md`
- controller adjudication: `docs/reviews/wu-proj-01-pr-review-residual-controller-adjudication.md`
- fix artifact: `docs/reviews/wu-proj-01-pr-review-residual-fix-codex.md`
- re-review artifacts:
  - `docs/reviews/wu-proj-01-pr-review-residual-rereview-mimo.md`
  - `docs/reviews/wu-proj-01-pr-review-residual-rereview-ds.md`
  - `docs/reviews/wu-proj-01-pr-review-residual-rereview-controller-adjudication.md`
- verdict before fix: `PASS` with accepted docstring fix
- blocking findings: 0
- findings:
  - NF1: `budget=None` parameter docstring says "close-only or test-only" but production dispatch paths use it for required-catch-up; wording should clarify "no fixed upper bound for correctness-required paths"
  - NF2: reactive compact path uses broad `except Exception` for `build_pre_dispatch_compact_material_view()`; consistent with proactive path but could be narrowed later
- fix status:
  - NF1 fixed in `dayu/host/memory_repair.py`
  - NF2 deferred-with-owner to future reactive recovery hardening
- residual risk status:
  - `WU-PROJ-01-CAP-R1`: closed
  - `WU-PROJ-01-S3-R1`: closed
  - `WU-PROJ-01-S4-R1`: closed
- next gate: user merge decision for PR #136

## WU-DUR-P01 EventLog Runner-call Reconstruction Atoms

### 状态

GitHub Issue #117 当前为 OPEN。本条是 WU-OBS-P00 / WU-OBS-00 的 durable truth 前置 work unit，负责补齐 EventLog / payload / artifact 中用于还原历史 Runner 调用 LLM-facing messages 的原子字段。本条不把完整 provider request payload/messages 明文保存为新的 canonical fact；目标是让 provider request 作为派生视图，能由 durable atoms 与版本化 projector 稳定重建。

上位架构原则以 `docs/host/design.md` 为准：EventLog 是 Host durable fact 真源；tool trace、audit、usage、timeline、outbox 与 memory snapshot 都是从 committed EventLog 投影出的 read model / diagnostic view，不能反向成为 EventLog、recovery、resume、memory 或 Run 状态迁移真源。

重要约束：本条不得削弱 EventLog 原子性。补字段不是把 RunInput、provider request、messages dump、memory snapshot、compact material 或 analyzer bundle 一股脑塞进 EventLog；EventLog 仍只记录治理与恢复需要的 canonical facts、refs、digests、版本化 projector metadata 与最小必要原子。大体积 LLM-facing projection 必须走 payload descriptor / artifact ref，并保持可由 source refs / digests 校验。

### 设计与代码核对

- 2026-06-05 smoke 检查结论：当前 `USER_INPUT_ACCEPTED` 保存了 `system_prompt` / `user_prompt`，`TOOL_RESULT_ACCEPTED` 有完整 tool result payload，但 canonical `TOOL_CALL_REQUESTED` 只保存 `normalized_arguments_digest`，没有 tool call arguments 明文。GitHub Issue #117 已记录该 durable atom 缺口。
- Engine `ToolCallRequestedData` 内部包含 `arguments`，但 Host ingest preview event 只落 `argument_key_count`、`tool_name`、`tool_call_id` 和 `provider_state_present`。
- ToolRuntime accept barrier 写入的 canonical `TOOL_CALL_REQUESTED` 当前只包含 `tool_name`、`tool_call_id`、`tool_schema_digest`、`tool_identity_digest`、`normalized_arguments_digest`、`semantic_input_digest` 等摘要字段。
- `payload_descriptors` 当前没有 tool-call-arguments payload；round1 第二次 Runner call dump 只能从用户 prompt / 当前代码 / smoke 工具行为推断 arguments，不能从 durable atoms 直接读取。
- 2026-06-05 round2 proactive compact dump 显示 `evidence_material[*].query_text` 只能投影为 `tool_call_id=...`。直接代码证据是 `dayu/host/compaction_evidence.py::_readable_query_text(envelope)` 当前只返回 tool call id；根因是 durable truth 缺少可读取的 accepted tool call arguments / semantic query atom，导致 compact evidence material 无法稳定生成业务可读 query text。
- Host execution context system message 当前可由字段重建，但缺少显式 scene-message projector version / schema id。
- LLM-facing tool message content 当前依赖 Engine 投影代码；历史 dump 若不读当前代码，需要 durable projector version / schema digest 或等价 contract。
- 2026-06-05 round2 compact 后 dump 暴露更大缺口：`smoke01.log` 中 `runner_call_start` 记录 `message_count=9`，但当前 durable DB + EventLog 重建 cursor=121 的 memory / compact 投影只能得到 7 条 messages。现有 EventLog 有 `CONTEXT_COMPACTED`、compact artifact、当前 user input、terminal summary refs 等原子，但缺少“本次 Runner call 使用了哪些 LLM-facing material / memory / compact / continuity blocks、按何种 projector 版本拼成几个 message”的 durable assembly manifest。
- 2026-06-05 round2 proactive compact 内部 compactor call 也暴露同类缺口：Engine log 中 `context-compactor:vnext` run `context-compactor-vnext-10e0d9ae533d4673a430cedddac55b5d` 的 final proposal call `message_count=2`，当前可通过 EventLog / payload / compact artifact refs 与当前 compactor projector 代码重建 system+user messages，且重建 `compaction_request_digest=sha256:4013a39b85957a9463b8755976809fea47eb0ecc90ea38263ddb9ba4cb405abc` 与 artifact 一致；但 EventLog / compact artifact 没有保存 compactor runner-call input manifest、message role sequence digest 或 LLM-facing `ConversationCompactInputVNext` projection artifact ref，因此仍不能只靠轻量渲染完成历史 dump。
- `host_memory_snapshots` 当前只保留 latest snapshot row；该 smoke 完成后 snapshot cursor 已推进到 269，无法直接读取 round2 dispatch 时 cursor=121 的 historical memory read model。虽然 memory 可由 EventLog 重建，但若缺少本次 RunInput 所用 snapshot/material cursor、projector id、block ids 与 role sequence digest，历史重放仍会退化为读当前代码推断。
- 当前 Engine `ITERATION_STARTED` / verbose log 只给出 `message_count`，没有 message role sequence、message digests、source block refs、RunInput projector id 或 projection artifact ref。日志计数不能作为 durable truth，也不足以解释 9 与 7 的差异来源。

### 目标

- 实施前必须先把 EventLog 补字段的稳定 contract 写回 `docs/host/design.md`，包括新增 canonical atoms / refs / digests / projector metadata、payload descriptor / artifact ref 边界、schema 语义与不得削弱 EventLog 原子性的约束；implementation 只能按 design.md 的稳定设计落地。
- 补齐 EventLog / payload / artifact 原子字段，使历史 Runner 调用的 LLM-facing messages 可由 durable truth 与版本化 projector 重建。
- 将 accepted tool call arguments 作为可恢复、可校验的 durable atom 保存；可采用 canonical event payload 或 payload ref，但必须保留 digest/ref 链路。
- 为 compact evidence query projection 提供 durable 输入：accepted tool call request 至少要能恢复 tool name、normalized arguments 与可选 semantic query / readable input，使 `evidence_material[*].query_text` 不必退化为裸 `tool_call_id`。
- 明确 assistant tool_calls message 重建所需字段，包括 `content`、`reasoning_content`、`tool_calls`、provider state 边界与空值语义。
- 为 scene / Host execution context message 与 LLM-facing tool result projection 记录稳定 projector id、schema version 或 digest。
- 为每次 Runner call 记录 durable input assembly manifest：至少包含 `runner_call_index`、`iteration_id`、message_count、message role sequence digest、source block refs、source cursor、RunInput projector id/schema version/digest、tool schema snapshot refs、compact artifact refs、memory snapshot/material cursor refs、continuity refs 与 context fallback decision refs。
- 覆盖 Host-owned compactor 内部 Runner call：compactor 不是 Host admission 产生的用户 Run，但它仍是 Engine Runner 调用，manifest / projection refs 必须能表达 compactor system prompt、user prompt template、`ConversationCompactInputVNext` projection artifact/ref、compaction request digest、accepted compact artifact ref 与 compactor projector id/schema version。
- 区分 durable truth atoms 与派生 LLM-facing projection：EventLog 不保存完整 provider request 作为 canonical fact，但可以保存 derived projection artifact 的 ref/digest/producer projector metadata；artifact 内容必须能由 source refs/digests 校验，且不能反向成为 recovery / memory / Run 状态迁移真源。
- 保持 manifest 原子化：manifest 只列出本次 Runner call 采用的 source atom / projection artifact / digest / projector version / role-sequence 等可校验索引，不内联完整 messages、长 prompt、完整 tool result、完整 memory snapshot 或 compact material。
- 覆盖 compact 后 no-tool / empty-tool Runner call input，不只覆盖 tool call roundtrip；round2 这类 compact artifact + memory material + current large user prompt 场景必须能重建或明确报告 limited signal。
- 为 WU-OBS-P00 / WU-OBS-00 提供可消费的 durable refs / metadata，使 analyzer 不依赖当前代码或 prompt 猜测来重建 Runner call input。

### 非目标

- 不把完整 provider request payload/messages 明文作为 EventLog canonical fact 重复保存。
- 不把 EventLog 改成 messages dump store、provider request store、memory material store 或 analyzer bundle store。
- 不让 Tool Trace、Audit、Outbox、timeline 或 memory snapshot 反向成为恢复、resume、memory 或 Run 状态迁移真源。
- 不实现 Tool Trace analyzer、prompt-based diagnostics 或 operator bundle。
- 不要求 EventLog inline 大体积 LLM-facing messages；大 payload 应通过 payload descriptor / artifact ref / digest 管理。
- 不用 untyped extra payload 承载显式字段；新增字段必须是 typed canonical atom、typed ref / digest 或版本化 projector metadata。
- 不改变 ToolRuntime accept / governance 语义，除非字段补齐需要同步更新同源 contract。
- 不通过兼容 wrapper、旧字段 alias 或 extra payload 保留旧 schema。

### 验收信号

- 至少一个包含 tool call 的历史 Runner call，可只凭 EventLog + payload/artifact store + projector metadata 重建 LLM-facing messages。
- 至少一个 compact 后 follow-up Runner call，可只凭 durable input assembly manifest + source payload/artifact refs 重建 LLM-facing messages，或在历史字段不足时输出明确 limited-signal 诊断；不得出现日志 `message_count` 与 dump item 数量无法解释的状态。
- 至少一个 proactive compactor internal Runner call，可只凭 durable input assembly manifest + compactor projection artifact refs 轻量 dump 出 system/user messages，并能校验 `compaction_request_digest`、message_count 与 accepted compact artifact digest；不得要求 analyzer 重新执行 `_proactive_material_blocks` / `select_compact_segment` / `build_compact_material_pack` / compactor prompt rendering。
- EventLog 新增字段保持原子化；测试或 review 必须能证明没有把完整 provider request/messages、完整 memory snapshot、完整 compact material 或 analyzer bundle 内联进 EventLog canonical payload。
- accepted tool call arguments 可从 durable truth 读取，并能与 `normalized_arguments_digest` 校验一致。
- compact evidence query text 可由 durable tool call request atoms 生成，并能校验其 source 与 accepted evidence / tool result 同源；不得只剩 `tool_call_id=...`，除非输出明确 limited-signal 诊断。
- assistant tool_calls message 重建不依赖用户 prompt 文本推断。
- tests 覆盖 tool call -> tool result -> 第二次 Runner call messages reconstruction，以及 compact -> memory/material -> follow-up Runner call messages reconstruction 两条 durable atom 路径。
- Tool Trace / analyzer 相关字段仍只消费 refs / digest / metadata，不变成事实真源。

## WU-OBS-P00 Runner Call Input Reconstruction Signals

### 状态

GitHub Issue #70 当前为 OPEN，GitHub Issue #117 为本条的 durable atom 前置 owner。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit：在 WU-DUR-P01 补齐 EventLog 原子字段后，定义 Tool Trace analyzer 如何通过 refs / digest / projector metadata 定位并重建某次 Runner 调用的 LLM-facing messages。

上位架构原则以 `docs/host/design.md` 为准：Tool Trace / Audit 只能是 EventLog 的投影结果；它们可以服务分析、解释和 operator dump，但不能拥有或补造 Host durable truth，也不能成为恢复、resume、memory 或 Run 状态迁移依据。

重要约束：WU-OBS-P00 只能消费 WU-DUR-P01 提供的原子 refs / digests / projection artifact refs；不得反向要求 EventLog 保存完整 dump，也不得把 Tool Trace 提升为事实真源。

### 设计与代码核对

- `docs/host/issues-implementation-control.md` 已明确 WU-OBS-00 是 Tool Trace analyzer，Tool Trace 是 committed EventLog 的派生 projection，不是 Host recovery、resume、memory 或 Run 状态迁移真源。
- 当前 `tool-trace-cold.jsonl` 可投影 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`USAGE_REPORTED`、`RUN_SUCCEEDED` 等 trace 行，但没有 system/user message、tool arguments 明文、assistant tool_calls content / reasoning_content，也没有 runner call message role index。
- 当前 tool trace 有 tool result / terminal summary payload refs，但只靠 trace 文件本身不能展开 tool role message content 或 final summary。
- WU-DUR-P01 解决 durable truth 缺口后，WU-OBS-P00 仍需裁决 trace projection schema：是否在 Tool Trace 中提供足够 refs / metadata，或新增 runner-call / run-input trace artifact。
- 2026-06-05 round2 dump 显示 analyzer 若只读取当前 DB、EventLog 与当前代码，可能得到与真实运行日志 `message_count=9` 不一致的 7 条重建结果。WU-OBS-P00 必须把这种 mismatch 变成结构化诊断：指出缺少 runner-call input manifest、historical memory/material snapshot、projection artifact 或 role sequence digest，而不是静默输出看似完整的 messages dump。
- 2026-06-05 round2 compact 内部 compactor dump 显示 analyzer 若要输出 `context-compactor:vnext` final proposal call messages，目前必须重跑 compactor input projector 与 prompt rendering；这不是轻量 renderer。WU-OBS-P00 必须让 analyzer 能把 Host-owned compactor Engine call 标识为 internal runner call，并通过 trace refs / projection artifact refs dump 或报告 limited-signal，而不是把它误判为普通 Host admitted Run。
- 2026-06-05 round2 compact dump 还显示 `evidence_material[*].query_text` 退化为 `tool_call_id=...`。Analyzer 不负责修复 compact 质量，但必须能把该退化标记为 durable atoms / projection signal 不足，而不是把只有 tool_call_id 的 query_text 当作完整可读 query。

### 目标

- 定义 Tool Trace analyzer 所需的 runner-call input reconstruction signal contract。
- 明确 trace 中应暴露的 refs / digest / projector metadata，例如 `runner_call_index`、`iteration_id`、message role index、tool call arguments payload ref、tool result projection ref、scene projector id。
- 明确 analyzer 消费的 runner-call input artifact / manifest contract：message item count、role sequence、per-message source refs / digests、projection artifact ref、RunInput projector id、tool-result projector id、memory-material projector id、compact artifact projector id，以及 provider serializer id / schema version。
- 将 compactor internal runner call 纳入同一 signal contract：trace / diagnostic artifact 必须能表达 parent Host run id、`context-compactor:vnext` run id、runner_call_index、compactor projector id/schema version、compaction request digest、`ConversationCompactInputVNext` projection artifact ref、accepted compact artifact ref，以及该调用不是 Host admitted user Run 的语义边界。
- 保持信号来源同源：只能来自 EventLog canonical facts、payload descriptors、artifact refs 或 Host-owned projection metadata；不得从日志、prompt 文本或当前代码猜测补造。
- analyzer 对 compact evidence material 应报告 query readability diagnostics：当 `query_text` 只能解析为裸 `tool_call_id` 且没有 tool name / normalized arguments / semantic query projection refs 时，输出 structured limited-signal，而不是静默通过。
- 保持 trace signal 轻量化：Tool Trace 可保存 manifest ref / projection artifact ref / digest / role-sequence summary / mismatch diagnostic，但不内联长 prompt、完整 messages、完整 tool result 或完整 memory material。
- 让 WU-OBS-00 analyzer 能输出某次 Runner 调用的 messages dump，或明确报告 limited signal / mismatch reason；特别要覆盖 compact 后 follow-up 的 memory/material/compact source gap。
- 将 dump 复杂度限制为轻量 renderer：resolve refs、verify digests、expand payload/artifact、render Markdown / JSON。Analyzer 不得复刻 RunInputBuilder、Engine tool message injection、tool result projection 或 provider payload serializer。

### 非目标

- 不把 Tool Trace 变成事实真源。
- 不在本条补 EventLog 原子字段；该工作由 WU-DUR-P01 / GitHub Issue #117 承接。
- 不实现完整 Tool Trace analyzer report。
- 不默认在 hot trace 中内联大 payload、敏感 provider raw payload 或完整 tool result。
- 不要求 Tool Trace 自身保存所有 LLM-facing messages；可以保存 message projection artifact ref / manifest ref / digest，但必须让 analyzer 能定位并校验派生 artifact。
- 不借 analyzer 需求反向污染 EventLog 原子事实；若需要完整 LLM-facing projection，使用派生 artifact，并用 refs / digests 连接到 EventLog atoms。
- 不改变 ToolRuntime / Engine / Runner 执行语义。
- 不在 analyzer 中用当前生产代码、prompt 文本或工具行为反推历史 messages；若 projector version 不受支持，必须报告 limited signal。

### 验收信号

- Tool Trace analyzer fixture 能从 trace refs 回链到 durable atoms，并生成 Runner call messages dump，或在字段缺失时输出明确 limited-signal 诊断。
- trace projection tests 覆盖 tool-call roundtrip、compact 后 follow-up、proactive compactor internal runner call 的 runner_call_index / iteration / refs / projector metadata / message_count 对齐。
- analyzer 不读取日志、不依赖 prompt 猜测、不把 Tool Trace 当作 truth。
- analyzer 能检测 `runner_call_start.message_count`、manifest message_count、dump item 数量不一致，并输出缺失字段 / 缺失 projection artifact 的 structured mismatch diagnostic。
- analyzer 能检测 compact evidence `query_text` 退化为 `tool_call_id` 的情况，并指向缺失的 tool-call arguments / semantic query durable atom 或 projection ref。
- analyzer dump 路径只有轻量渲染逻辑；若仍需要重写复杂 prompt assembly / tool projection，视为本条未通过。
- WU-OBS-00 plan 可以直接消费本条 signal contract。

## WU-OBS-P01 Tool Trace Context Budget Snapshot Signals

### 状态

GitHub Issue #29 当前为 OPEN。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit，而不是 analyzer 本体。Issue 中的 NEW 指 `dayu-agent-r`，OLD 指 `dayu-agent`。当前 NEW 已有 context budget / compaction / usage observation 相关 canonical facts 与 projection signal，但 Tool Trace analyzer 所需的 OLD 等价 context pressure 信号尚未形成稳定 trace contract。

### 设计与代码核对

- `docs/host/design.md` 已要求 trace / audit 能解释 context pressure、truncation、召回失败、预算未纳入 RunInput 等原因。
- `dayu/host/context_budget.py` 已有 `BudgetEstimate`、`ContextBudgetDecision`、`UsageObservationDiagnostic` 和 post-call usage observation 诊断。
- `dayu/host/context_events.py` 已有 `budget_snapshot_ref`、`budget_reason`、`budget_after_compact`、`budget_after_attempted_compact` 等 context compaction event payload 字段。
- `dayu/host/dispatch.py` 与 `dayu/host/engine_ingest.py` 会写入 context compaction / usage observation 相关事件。
- `dayu/host/tool_trace.py` 当前只把 usage projection signal 的 `usage_observation_digest` / `estimator_digest` 放入 diagnostic refs；hot `trace_summary` 尚未直接提供 OLD analyzer 等价的 `is_over_soft_limit`、compaction count、continuation count 等 context pressure 诊断字段。
- 代码核对未发现 `IterationUsageRecord` / `budget_snapshot` analyzer parity contract；当前也没有 operator-facing Tool Trace analyzer。

### 目标

- 先定义 NEW / dayu-agent-r 的 Host-owned context pressure trace signal contract，再由 WU-OBS-00 analyzer 消费。
- 评估 context pressure 所需字段应来自 `BudgetEstimate`、context compaction events、usage observation diagnostics、Run / Attempt facts 还是 Tool Trace projection summary。
- 补齐 analyzer 所需的 `is_over_soft_limit`、hard threshold / soft threshold reason、compaction count、continuation count 或等价稳定字段。
- 字段必须能追溯到 durable EventLog facts、projection signals 或 artifact refs；不得从日志、进程内缓存或 prompt 文本旁路补造。
- 保持分层：Engine 只上报 provider usage / protocol facts；Host 负责预算治理、context pressure 解释与 Tool Trace projection。

### 非目标

- 不复刻 OLD / dayu-agent 的数据结构名称作为 NEW 稳定契约。
- 不让 Engine 理解 Host context budget policy。
- 不把 analyzer 需要的字段塞进 untyped metadata / extra payload。
- 不在本条实现完整 Tool Trace analyzer；本条只补 signal contract 与 projection / fixture。

### 验收信号

- NEW / dayu-agent-r 的 Tool Trace 或 analyzer fixture 能表达与 OLD / dayu-agent 等价或明确增强的 context pressure 诊断。
- 新增字段有 contract / serializer / projection 测试。
- analyzer fixture 能覆盖 over soft limit、hard threshold、compaction happened、continuation happened / not happened 等代表场景。
- 不使用日志、进程内缓存或 prompt 文本旁路补造 budget snapshot。

## WU-OBS-P02 Tool Trace Tool Latency Signals

### 状态

GitHub Issue #30 当前为 OPEN。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit。Issue 中的 NEW 指 `dayu-agent-r`，OLD 指 `dayu-agent`。当前 NEW 的 ToolRuntime / Tool Trace 已能表达 tool call、outcome、truncation、duplicate、diagnostic refs 和 result digest，但尚未看到稳定 tool latency projection 字段。

### 设计与代码核对

- `docs/host/design.md` 的 Tool Trace hot / cold storage 设计允许保存 duration / attempt refs / diagnostic 等可诊断字段。
- `dayu/host/tool_runtime.py` 当前治理路径有 timeout、duplicate、truncation、accept retry、diagnostic refs 等结果，但代码核对未发现稳定 `latency_ms` / `duration_ms` 进入 accepted EventLog payload 或 Tool Trace summary。
- `dayu/host/tool_trace.py` 当前 `trace_summary` 包含 schema digest、identity digest、duplicate、truncation、diagnostic refs、provider / engine refs、policy decision 和 operation context refs；未包含 tool latency。
- `tests/host/test_tool_trace_projection.py` 已覆盖 hot / cold projection、digest conflict、query helper，但未覆盖 latency 统计字段。

### 目标

- 定义 tool latency 的稳定事实来源：ToolRuntime execution boundary、Tool result meta、accepted EventLog payload 或等价 Host-owned diagnostic event。
- 在 Tool Trace projection 中加入 `latency_ms`、duration bucket 或等价可聚合耗时信号。
- WU-OBS-00 analyzer 应能基于该信号输出 median latency / latency distribution / slow tool candidates。
- latency 语义必须明确包含或排除排队、duplicate reuse、truncation、accept retry、awaiting 外部 job 等阶段。

### 非目标

- 不用 wall-clock 日志解析 latency。
- 不把 latency 写成非持久进程内统计。
- 不在本条实现完整 analyzer report。
- 不让 latency 信号改变 ToolRuntime accept / governance 语义。

### 验收信号

- Tool Trace record 字段来源可追溯到 durable EventLog facts 或 Host-owned projection signal。
- analyzer fixture 能输出工具级耗时统计。
- projection、serializer / codec、analyzer fixture 覆盖普通 success、failure、duplicate / reuse、timeout 或 awaiting 代表路径。

## WU-OBS-P03 Tool Trace Structured Failure Metadata

### 状态

GitHub Issue #31 当前为 OPEN。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit。Issue 中的 NEW 指 `dayu-agent-r`，OLD 指 `dayu-agent`。当前 NEW 已有 failure error code / diagnostic refs / governed error 等路径，但 analyzer 若只靠文本与错误码分类，会低于 OLD 冷存 `meta.repair_hint` 等结构化诊断粒度。

### 设计与代码核对

- `dayu/host/tool_runtime.py` 当前有 governed error、timeout、accept failure、awaiting configuration failure、duplicate diagnostic refs、`last_error_code` 等结构化路径。
- `dayu/host/tool_trace.py` 当前会把 provider / engine / diagnostic refs、policy decision、truncation、duplicate decision 投影进 `trace_summary`。
- 代码核对未发现稳定 `error_signature`、`repair_hint`、`policy_block_reason`、`provider_error_code` 字段进入 Tool Trace hot / cold projection。
- 现有诊断 refs 可以定位部分失败来源，但 WU-OBS-00 analyzer 若没有结构化 failure metadata，仍会倾向脆弱文本分类。

### 目标

- 设计 Host-owned tool trace failure metadata：`error_signature`、`repair_hint`、`policy_block_reason`、`provider_error_code` 或等价字段。
- 明确字段生产者：ToolRuntime、provider / Engine error classifier、tool result envelope、ToolPolicy decision 或 diagnostic event。
- analyzer 使用结构化字段优先，文本分类只作为 fallback。
- OLD / dayu-agent 可迁移的业务无关 repair hint 语义可以进入 fixture；业务语义或财报领域判断不得进入 Host / Engine。

### 非目标

- 不把字符串正则分类作为唯一真源。
- 不把财报业务 repair hint 写入 Host / Engine。
- 不在 Tool Trace projection 中保存敏感 raw provider payload。
- 不改变 ToolRuntime failure / accept governance 语义。

### 验收信号

- failure pattern / detailed failure pattern 能输出结构化签名。
- analyzer fixture 覆盖 policy block、provider error、tool exception、timeout、schema / value error、truncation failure 等代表路径。
- 文本分类只作为 fallback，有测试证明结构化字段优先。
- 字段来源、redaction 和 durable refs 边界有测试覆盖。

## WU-OBS-P04 Provider Protocol Partial Tool-call Trace Signals

### 状态

GitHub Issue #35 当前为 OPEN。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit，而不是 analyzer 本体。当前 Engine / Runner 已有 bounded partial tool-call summary contract，但 Host ingest 与 Tool Trace projection 只保留 `partial_tool_call_count`，不足以支撑 #70 analyzer 区分 provider protocol error 无 partial、partial 摘要缺失、partial tool call 存在但 malformed 等诊断。

### 设计与代码核对

- `docs/engine/design.md` 已把 `provider_protocol_error` 定义为 provider 协议解析错误。
- `docs/host/design.md` 的 EventLog matrix 已列出 `PROVIDER_PROTOCOL_ERROR`，但必需 payload 仍是 provider / error code / request ref 级别，未明确 partial tool-call summary 的 Host trace payload。
- `dayu/engine/contracts/partial_tool_call.py` 已定义 `PartialToolCallSummary`，只包含 `tool_call_index`、bounded `tool_call_id`、bounded `name_fragment`、`arguments_byte_size`、`arguments_sha256`，不包含 raw arguments。
- `dayu/engine/contracts/engine_events.py` 的 `ProviderProtocolErrorData` 已包含 `partial_tool_calls: tuple[PartialToolCallSummary, ...]`。
- `dayu/engine/runners/openai/sse_parser.py` 与 `dayu/engine/runners/openai/tool_call_aggregator.py` 会在 provider protocol error 中带上 bounded partial summaries。
- `tests/engine/runners/openai/test_protocol_error.py` 已覆盖 SSE 中途失败时携带 bounded partial tool-call 摘要、摘要条数和字段长度受限、不包含 raw arguments。
- `dayu/host/engine_ingest.py` 当前 `PROVIDER_PROTOCOL_ERROR` diagnostic payload 只写 `partial_tool_call_count`，没有写 partial summaries。
- `dayu/host/tool_trace.py` 当前 diagnostic trace summary 未投影 partial tool-call summary 或 partial malformed 分类字段。

### 目标

- 将 Engine 已提供的 bounded partial tool-call summary 作为 Host-owned diagnostic / trace signal 持久化或投影出来，供 WU-OBS-00 analyzer 消费。
- 明确 `PROVIDER_PROTOCOL_ERROR` 中 partial tool-call 的 Hot / Cold 分层：hot summary 只能保存有界、脱敏、可聚合字段；任何 raw provider payload 仍必须走 payload descriptor / artifact ref 且受 scrub 边界约束。
- 让 analyzer 能稳定区分：无 partial、partial summary missing、partial tool call 存在但 arguments malformed、partial tool name / id 已知但 arguments 不完整、provider raw payload 可用 / 不可用。
- 保持信号来源同源：只能来自 Engine `ProviderProtocolErrorData.partial_tool_calls` 或 Host committed diagnostic event / Tool Trace projection，不从 provider raw stream、日志文本或 analyzer 猜测补造事实。

### 非目标

- 不把 raw arguments 写入 hot trace、EventLog inline payload 或 analyzer report。
- 不让 Host 重新解析 provider raw stream。
- 不改变 Runner / Agent 的 tool-call 解析语义。
- 不在本条实现完整 #70 analyzer report。
- 不把 pending pairing / owner / fencing / recovery 策略混进本条；如仍有该类治理缺口，必须由对应 lifecycle / recovery work unit 承接。

### 验收信号

- `PROVIDER_PROTOCOL_ERROR` 的 Host diagnostic payload 或 Tool Trace projection 中存在可消费的 bounded partial tool-call summary 或等价结构化字段。
- 字段只包含 bounded id / name fragment、arguments size、arguments digest、index 等脱敏摘要，不包含 raw arguments。
- Tool Trace fixture 能覆盖 provider protocol error 无 partial、partial summary present、partial arguments malformed、raw payload present / absent 等代表场景。
- WU-OBS-00 analyzer 可基于该信号输出 provider protocol partial tool-call 诊断；信号缺失时必须报告 limited signal。
- pyright 不新增或扩散类型错误。

## WU-CM-07 Evidence Validation And Pinned State Cleanup

### 状态

过期失效，不再作为独立 work unit 推进。Conversation Memory semantic model cleanup 由 GitHub Issue #81 跟踪。

### 目标

- 无独立实施目标。
- 后续若 #81 仍需要 evidence validation 子任务，应按新的 semantic memory 分类重新建 issue / work unit，不复用本条。

### 非目标

- 不再围绕 `pinned_state` 做局部 cleanup。
- 不在 #81 前为 confirmed subjects、current goal、open questions 等字段预设最终 owner。

### 验收信号

- 无独立验收信号；由 #81 及其后续 scoped issues 重新定义。

## WU-CLI-ACTIVITY-01 CLI Activity Stream UI

### 状态

本 work unit 已完成 plan review / re-review。BQ-1 已由用户裁决解除：本 WU 允许修改 event 相关 contracts。Plan 方向为 contract-first：先扩展 Host public `HostEvent` activity projection，再由 Service / CLI 消费该 public activity view；CLI 不读取 Host durable internals、Tool Trace、payload ref / digest、logging 或 ToolBundle。

### Current gate artifacts

- plan: `docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md`
- plan review: `docs/reviews/plan-review-20260617-124817.md` (AgentMiMo); `docs/reviews/plan-review-20260617-124923.md` (AgentDS)
- plan review adjudication: `docs/reviews/plan-review-wu-cli-activity-01-adjudication-20260617-125229.md`
- plan re-review: `docs/reviews/plan-review-20260617-130417.md` (AgentMiMo); `docs/reviews/plan-review-20260617-130248.md` (AgentDS)
- plan gate validation: `git diff --check` clean; untracked plan artifact whitespace check clean via `git diff --no-index --check /dev/null docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md` with expected nonzero no-index exit and no whitespace output
- accepted plan commit: `012fee0a`

### Accepted plan scope

- Slice A: Host public activity event contract; `HostEvent` keeps coarse `HostEventKind` and adds existing `HostEventClass`, EventLog row `event_type`, and safe `HostActivityView`.
- Slice B: Service activity callback consumes Host public activity, without parsing durable internals.
- Slice C: Prompt activity renderer, visibility toggle, and running-state cancel behavior.
- Slice D: Interactive composer with multiline input, history search, external editor, and early prompt_toolkit compatibility validation.
- Slice E: Interactive running activity and cancel integration.
- Slice F: README/doc checks, affected tests, coverage, pyright, and validation cleanup.

### Slice A status

- implementation artifact: `docs/reviews/wu-cli-activity-01-slice-a-implementation-codex.md`
- code review: `docs/reviews/code-review-20260617-132628.md` (AgentMiMo); `docs/reviews/code-review-20260617-132508.md` (AgentDS)
- code review adjudication: `docs/reviews/code-review-wu-cli-activity-01-slice-a-adjudication-20260617-132855.md`
- fix artifact: `docs/reviews/wu-cli-activity-01-slice-a-fix-codex.md`
- re-review: `docs/reviews/code-review-wu-cli-activity-01-slice-a-re-review-20260617-133529.md` (AgentMiMo); `docs/reviews/code-review-20260617-133606.md` (AgentDS)
- validation: `pytest tests/host/test_public_host_event.py tests/host/test_public_open_host_options.py tests/host/test_package_exports.py tests/host/test_host_activity_event_projection.py tests/host/test_watch_session_events.py tests/host/test_context_compact_events.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q` passed with 149 passed and 3 third-party edgar deprecation warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean
- accepted slice commit: `992a641d`

### Slice B status

- implementation artifact: `docs/reviews/wu-cli-activity-01-slice-b-implementation-codex.md`
- code review: `docs/reviews/code-review-20260617-135557.md` (AgentMiMo); `docs/reviews/code-review-20260617-135353.md` (AgentDS)
- code review adjudication: `docs/reviews/code-review-wu-cli-activity-01-slice-b-adjudication-20260617-135835.md`
- fix artifact: `docs/reviews/wu-cli-activity-01-slice-b-fix-codex.md`
- re-review: `docs/reviews/code-review-wu-cli-activity-01-slice-b-rereview-mimo-20260617-140637.md` (AgentMiMo); `docs/reviews/code-review-wu-cli-activity-01-slice-b-rereview-ds-20260617-140637.md` (AgentDS)
- validation: `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q` passed with 32 passed and 3 third-party edgar deprecation warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean
- accepted slice commit: `152292da`

### CLI slices C/D/E/F status

- implementation artifact: `docs/reviews/wu-cli-activity-01-cli-implementation-codex.md`
- initial fix artifact: `docs/reviews/wu-cli-activity-01-cli-fix-codex.md`
- code review: `docs/reviews/code-review-wu-cli-activity-01-cli-mimo-20260617-145226.md` (AgentMiMo); `docs/reviews/code-review-wu-cli-activity-01-cli-ds-20260617-145226.md` (AgentDS)
- review fix artifact: `docs/reviews/wu-cli-activity-01-cli-review-fix-codex.md`
- targeted re-review: `docs/reviews/code-review-wu-cli-activity-01-cli-rereview-mimo-20260617-151159.md` (AgentMiMo); `docs/reviews/code-review-wu-cli-activity-01-cli-rereview-ds-20260617-151159.md` (AgentDS)
- validation: `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py -q` passed with 97 passed and 3 third-party edgar deprecation warnings; `pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q` passed with 17 passed and total coverage 89.53%; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean
- accepted slice commit: `1a6f4bb2`

### Aggregate review and final closeout

- aggregate deepreview: `docs/reviews/deepreview-wu-cli-activity-01-aggregate-mimo-20260617-153030.md` (AgentMiMo, non-blocking with CLI subagent limitation noted); `docs/reviews/deepreview-wu-cli-activity-01-aggregate-ds-20260617-151950.md` (AgentDS, non-blocking)
- final validation: `pytest tests/host/test_public_host_event.py tests/host/test_public_open_host_options.py tests/host/test_package_exports.py tests/host/test_host_activity_event_projection.py tests/host/test_watch_session_events.py tests/host/test_context_compact_events.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py -q` passed with 179 passed and 3 third-party edgar deprecation warnings; `pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q` passed with 17 passed and total coverage 89.53%; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean
- final closeout: `docs/reviews/wu-cli-activity-01-final-closeout-20260617.md`
- post-closeout fix: `docs/reviews/wu-cli-activity-01-interactive-composer-async-fix.md`; validation `pytest tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py tests/cli/test_run_keys.py -q` passed with 66 passed and 3 third-party edgar deprecation warnings; `pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q` passed with 18 passed and total coverage 90.25%; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean

### Residual risks

- `RR-ACT-01` closed by Slice A: Host admission records Host-owned `effective_tool_display_names` without durable schema migration.
- `RR-ACT-02` closed by CLI implementation and tests: prompt_toolkit composer key bindings for Ctrl+J / Ctrl+R / Ctrl+X Ctrl+E are isolated in CLI and covered by `tests/cli/test_interactive_composer.py`.
- `RR-ACT-03` closed by CLI implementation and tests: activity renderer is TTY-gated, stderr-only, line-oriented, and closed before terminal rendering; prompt / interactive tests cover stdout cleanliness.
- `RR-ACT-04` closed by CLI fix and tests: repeated Ctrl+C local exit returns local 130 without forging Host terminal facts.
- `RR-ACT-05` closed by CLI fix and tests: prompt cancel terminal race prefers terminal when cancel terminal arrives before the second Ctrl+C local exit.

### Follow-up delta EventLog / projection catch-up status

- accepted follow-up plan: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- accepted plan commit: `906c1ffa`
- current slice: follow-up implementation completed locally through aggregate deepreview and focused re-review; next gate is draft PR.
- Slice 1 scope: clarify Host default durable policy for `content_delta` / `reasoning_delta` / `tool_call_delta`, durable replay non-goal for token-level delta, memory projection catch-up cursor / idle / failure semantics, hot path no-unbounded-sync-catch-up constraint, and `memory_projection_catchup_batch_size` as internal page size.
- Slice 1 allowed files: `docs/host/design.md`, optional `docs/engine/design.md`, `docs/host/issues-implementation-control.md`, and implementation artifact under `docs/reviews/`.
- Slice 1 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-1-implementation-codex-20260618.md`
- Slice 1 validation: `git diff --check` clean; grep confirmed old catch-up budget wording is absent and new non-durable delta / page-size wording is present.
- Slice 1 accepted commit: `3cb5fcb4`.
- Slice 2 scope: Host ingest accepts `content_delta` / `reasoning_delta` / `tool_call_delta` after durable identity / stale / late governance but returns accepted no-row results by default; non-delta preview mapping remains durable preview.
- Slice 2 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-2-implementation-codex-20260618.md`.
- Slice 2 code review: `docs/reviews/code-review-20260618-065959-mimo-wu-cli-activity-01-followup-slice-2.md`; `docs/reviews/code-review-20260618-070001-ds-wu-cli-activity-01-followup-slice-2.md`.
- Slice 2 fix artifact: `docs/reviews/wu-cli-activity-01-followup-slice-2-fix-codex-20260618.md`.
- Slice 2 re-review: `docs/reviews/code-review-20260618-070713-mimo-rereview-wu-cli-activity-01-followup-slice-2.md`; `docs/reviews/code-review-20260618-070659-ds-rereview-wu-cli-activity-01-followup-slice-2.md`.
- Slice 2 validation: `pytest tests/host/test_engine_ingest_mapping.py` passed with 64 passed; `pyright dayu/host/engine_ingest.py tests/host/test_engine_ingest_mapping.py` passed with 0 errors; `git diff --check` clean.
- Slice 2 accepted commit: `8d0a06f1`.
- Slice 3 scope: add durable-neutral EventLog filtered read with covered cursor semantics; update ProjectionRunner to use consumer filter at read path, apply only matching rows, advance checkpoint over covered non-matching ranges without consumer apply, and preserve failure stop before failed matching row.
- Slice 3 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-3-implementation-codex-20260618.md`.
- Slice 3 code review: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-3-20260618-072504.md`; `docs/reviews/ds-wu-cli-activity-01-followup-slice-3-20260618-072339.md`.
- Slice 3 fix artifact: `docs/reviews/wu-cli-activity-01-followup-slice-3-fix-codex-20260618.md`.
- Slice 3 re-review: `docs/reviews/mimo-rereview-wu-cli-activity-01-followup-slice-3-20260618-073105.md`; `docs/reviews/ds-rereview-wu-cli-activity-01-followup-slice-3-20260618-073110.md`.
- Slice 3 validation: `pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py` passed with 46 passed; `pyright dayu/host/durable/event_log.py dayu/host/projection.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py` passed with 0 errors; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 3 accepted commit: `f67a55b6`.
- Slice 4 scope: remove `MemoryProjectionCatchupBudget` / `MemoryProjectionRepairPurpose` / `BUDGET_EXHAUSTED` memory repair semantics, make catch-up / rebuild loop to target / idle / failure using page size only, remove open_host after-commit and dispatch compact accepted conversation-memory catch-up hooks, and delete the residual `ConversationMemoryProjectionCatchupPort` adapter.
- Slice 4 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-4-implementation-codex-20260618.md`.
- Slice 4 code review: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-4-20260618-074855.md`; `docs/reviews/ds-wu-cli-activity-01-followup-slice-4-code-review-20260618-074930.md`.
- Slice 4 fix artifact: `docs/reviews/wu-cli-activity-01-followup-slice-4-fix-codex-20260618.md`.
- Slice 4 re-review: `docs/reviews/mimo-rereview-wu-cli-activity-01-followup-slice-4-20260618-075452.md`; `docs/reviews/ds-rereview-wu-cli-activity-01-followup-slice-4-20260618-075450.md`.
- Slice 4 validation: `pytest tests/host/test_memory_repair.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py -q` passed with 160 passed; relevant pyright passed with 0 errors; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `rg` found no `ConversationMemoryProjectionCatchupPort`, `MemoryProjectionCatchupBudget`, `MemoryProjectionRepairPurpose`, `MemoryProjectionRepairStopReason.BUDGET_EXHAUSTED`, or memory repair `budget_exhausted` in `dayu/` and `tests/`; `git diff --check` clean.
- Slice 4 accepted commit: `794d3b74`.
- Slice 5 scope: make Conversation Memory projection filter a single truth via `conversation_memory_projection_event_filter()`, reuse projection-to-EventLog read filter conversion in inline repair, remove RunInputBuilder-local memory event type filter, and use session-scoped `read_events_after_matching(...)` / covered cursor semantics for inline delta repair.
- Slice 5 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-5-implementation-codex-20260618.md`.
- Slice 5 code review: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-5-review-20260618-081119.md`; `docs/reviews/ds-wu-cli-activity-01-followup-slice-5-20260618-080958.md`.
- Slice 5 validation: `pytest tests/host/test_run_input_builder.py tests/host/test_memory_projection.py` passed with 76 passed; relevant pyright passed with 0 errors; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 5 accepted commit: `49c813a5`.
- Aggregate deepreview: `docs/reviews/mimo-aggregate-wu-cli-activity-01-followup-20260618-081816.md`; `docs/reviews/ds-aggregate-wu-cli-activity-01-followup-20260618-081532.md`.
- Aggregate fix: `docs/reviews/wu-cli-activity-01-followup-aggregate-fix-codex-20260618.md`.
- Aggregate focused re-review: `docs/reviews/mimo-aggregate-rereview-wu-cli-activity-01-followup-20260618.md`; `docs/reviews/ds-aggregate-rereview-wu-cli-activity-01-followup-20260618-082351.md`.
- Aggregate fix validation: `pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_memory_repair.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` passed with 120 passed; final follow-up validation `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` passed with 348 passed; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Draft PR: https://github.com/noho/dayu-agent-r/pull/149.
- PR review: `docs/reviews/wu-cli-activity-01-pr-review-mimo-20260618.md`; `docs/reviews/wu-cli-activity-01-pr-review-ds-20260618.md`.
- PR review fix: `docs/reviews/wu-cli-activity-01-pr-review-fix-codex-20260618.md`.
- PR review fix validation: `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q` passed with 114 passed and 3 third-party edgar deprecation warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; grep found no duplicated `_cancel_and_await_task` in `dayu/cli`.
- PR focused re-review: `docs/reviews/wu-cli-activity-01-pr-rereview-mimo-20260618.md`; `docs/reviews/wu-cli-activity-01-pr-rereview-ds-20260618.md`.
- Final closeout: `docs/reviews/wu-cli-activity-01-final-closeout-20260618.md`.
- PR checks: GitHub reports no checks for branch `wu-cli-activity-01`; closeout relies on local validation and dual-agent review.
- next entry point: WU-OBS-00 preflight / planning when requested.

## WU-CLI-INTERACTIVE-RESUME-01 Prompt / Interactive Existing-Session Startup

### 状态

本 work unit 已完成本地 final closeout。语义裁决为：`prompt` 不执行离线 terminal backfill，也不等待 / 重放历史未完成 Run；`interactive` existing-session 入口在进入 REPL 前执行 attach / reconnect startup barrier，处理 selected Session 的离线 terminal、active Run 与 queued-only 状态。

### Gate artifacts

- initial plan: `docs/reviews/wu-cli-interactive-resume-01-plan-codex-20260617.md`
- plan reviews: `docs/reviews/plan-review-20260617-183641.md`; `docs/reviews/plan-review-20260617-183910.md`
- plan adjudication: `docs/reviews/wu-cli-interactive-resume-01-plan-adjudication-20260617.md`
- revised plan: `docs/reviews/wu-cli-interactive-resume-01-plan-fix-codex-20260617.md`
- idle-tail fix artifact: `docs/reviews/wu-cli-interactive-resume-01-idle-tail-fix-codex-20260617.md`
- implementation reviews: `docs/reviews/wu-cli-interactive-resume-01-implementation-review-mimo-20260617.md`; `docs/reviews/wu-cli-interactive-resume-01-implementation-review-20260617.md`

### Implementation summary

- Service 新增 `startup_reconnect_entrypoint_session(...)`，使用 watcher-first 顺序：先 attach `watch_session_events(session_id)` 并启动 drain task，再执行 session-scoped Outbox backfill。
- Startup backfill 不按 `run_id` 过滤；`CAUGHT_UP` 且无新 terminal 是正常 idle，不复用 run-scoped terminal fallback 的异常语义。
- idle snapshot 后增加 tail closure：再次 session-scoped Outbox backfill 并 drain watcher queue，发现 terminal 或首次 watcher failure 时重新读取 Session snapshot，避免 terminal 已提交但尚未进入 watcher queue 的窗口。
- interactive existing-session 入口在首条输入前执行 startup barrier；active Run 先观察 terminal，queued-only 按 bounded promotion wait，耗尽后结构化失败，不静默进入 REPL。
- prompt existing-session 入口不读 cursor、不补读旧 terminal、不等待旧 active / queued；仅在本次 terminal 成功渲染后推进 CLI terminal cursor。
- CLI terminal cursor 是 workspace-local UI state，通过 `asyncio.to_thread()` 包裹同步 JSON / file lock / atomic replace；腐坏 JSON 与非法字段 fail fast。

### Validation

- `source .venv/bin/activate && pytest tests/service -q` passed: 110 passed, 3 third-party edgar deprecation warnings.
- `source .venv/bin/activate && pytest tests/cli/test_session_terminal_cursor.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py -q` passed: 74 passed, 3 third-party edgar deprecation warnings. This CLI subset is slow; final run completed in 360.44s.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` passed: 0 errors, 0 warnings.

### Residual risks

- `WU-CLI-INTERACTIVE-RESUME-01-R1` rejected by user裁决: workspace-local cursor is sufficient because CLI already has `--base` to select a workspace directory; no future per-client cursor identity WU is needed for this concern.
- `WU-CLI-INTERACTIVE-RESUME-01-R2` fixed immediately: `session resume --mode interactive` now catches startup `EntrypointRuntimeError` after target resolution and renders a structured CLI error containing selector, Session id, and startup message.
- Rendering success followed by cursor write crash can duplicate terminal on next startup; accepted by design because no terminal loss is preferred over false acknowledgement.

## WU-CLI-SESSION-01 CLI Session Management

### 状态

本 work unit 已完成 final closeout。PR #146 已创建并推送到 `github/wu-cli-session-01`；GitHub Issue #145 已在 2026-06-17 按用户授权关闭。

### Current gate artifacts

- plan: `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`
- plan accepted commit: `653c9966`
- slice accepted commits: S1 `8175b8cb`; S2 `f66d76e9`; S3 `cc76ff31`; S4 `07cc3010`; S5 `00b82bbb`; S6 `fc92286b`
- aggregate deepreview: `docs/reviews/deepreview-wu-cli-session-01-aggregate-ds-20260616.md`; `docs/reviews/deepreview-wu-cli-session-01-aggregate-mimo-20260616.md`
- aggregate adjudication: `docs/reviews/deepreview-wu-cli-session-01-aggregate-adjudication-20260616.md`
- aggregate accepted commit: `1ac06623`
- draft PR record commit: `5152028b`
- PR review: `docs/reviews/pr-146-review-wu-cli-session-01-mimo-20260616-222711.md`; `docs/reviews/pr-146-review-wu-cli-session-01-ds-20260616.md`
- PR review adjudication: `docs/reviews/pr-146-review-wu-cli-session-01-adjudication-20260616.md`
- PR review accepted commit: `c7f79f03`
- final closeout: `docs/reviews/wu-cli-session-01-final-closeout-20260616.md`
- final validation: `pytest tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q` 120 passed, 3 third-party edgar deprecation warnings; `python -m pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean

### Final scope decision

- `resume`、`list`、`purge` 均为本 work unit 已实施内容，不是后续项。
- Host 正式新增 public `list_sessions` API；该 API 是 Host public read contract，不是 CLI 私有临时 helper。
- `interactive --new-session` 已从 CLI surface 删除。
- `session resume` 只对已有 OPEN Session 执行，不 create / ensure Session，不使用 Host wait-resume 语义。
- `session purge` 不自动 close / cancel；Host purge precondition 是最终治理真源。

### Residual risk reconciliation

当前没有阻塞 final closeout 的 residual risk。

已分类的非阻塞风险：

- `list_sessions` 无分页 / 无 query contract：deferred-with-owner；未来真实 Session cardinality 或外部 API consumer 需要时进入 Host session-list scale / pagination hardening。
- CLI list 文本表不做列宽裁剪：deferred-with-owner；未来由 CLI UX refinement 根据 operator feedback 处理。
- `session.py` 依赖 prompt / interactive sibling module 的 existing-session 窄入口：deferred-with-owner；未来 CLI command-entrypoint refactor 或 WU-CLI-ACTIVITY-01 若改变 prompt / interactive execution ownership 时处理。
- Draft PR 无 reported CI checks：non-blocking；本地验证为本 gate controller truth，pre-merge gate / repository branch protection 继续承担外部检查。

## WU-CLI-FINS-OBS-01 Fins Direct CLI Live Event Stream / Log / UI Print

### 状态

本条是用户裁决纳入本文档留痕的 immediate residual work unit，不创建 GitHub Issue。PR #143 已打开，但 2026-06-16 用户指出并经代码核对确认两个设计更正：CLI direct live events 没有 durable job 需求，正确模型是普通 `AsyncIterator[FinsEvent]`；Fins tool awaiting 返回 `ToolAwaitingOutcome(EXTERNAL_JOB)` 的方向成立，但把 awaiting observation handle 实现成 Fins 核心 durable job system 过重。因此 PR #143 的 durable sidecar plan / slice 记录不再作为当前实施真源。2026-06-16 replacement plan gate 已完成并通过 re-review；replacement implementation 已按 `docs/host/wu-cli-fins-obs-01-replacement-plan.md` 完成 final closeout。

### 用户裁决

- 不需要创建 GitHub Issue。
- 用户已恢复 `$phaseflow` 推进；当前按本文档 accepted replacement plan 进入 implementation gate。
- `download`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material` 全部必须恢复 live event stream。
- 除 Fins direct commands 外，还必须核对所有其它 CLI commands 的 log 与 UI print 是否正常；正常的命令记录直接证据，不正常的命令纳入本条修复或明确转入后续 owner。
- 需要同时处理两个 residual：log / UI print 缺失，以及 Fins direct event stream 迁移缺失。

### 设计与代码核对

- `docs/host/design.md` 固定 `UI -> Service -> Host -> Engine` 分层边界：UI 负责展示、输入收集、流式订阅和用户动作触发；Service 负责业务入口、身份解析、场景装配和调用 Host。Fins direct command 不应伪装成 Host run，也不得让 CLI 绕过 Service / Fins boundary。
- `docs/engine/design.md` 固定 stream 术语边界：Fins direct live event stream 不是 `EngineEvent stream`，也不是 `Host event stream`；不得在设计或实现中混称。
- `dayu/README.md` 的“日志与可观测性”固定日志职责：日志用于诊断系统执行过程，不承担 UI 输出、审计真源、tool trace、EventLog canonical fact 或 projection checkpoint 职责。
- OLD `/Users/leo/workspace/dayu-agent/dayu/services/fins_service.py` 的 `FinsService.execute(...)` 返回 `FinsResult | AsyncIterator[FinsEvent]`；流式路径直接 `async for event in result: yield event`，没有 `job_id`、event sidecar 或 durable cursor。
- OLD `/Users/leo/workspace/dayu-agent/tests/cli/test_fins_commands.py` 的 `_consume_fins_stream` 测试直接消费 `AsyncIterator[FinsEvent]`，通过 `PROGRESS` / `RESULT` 事件完成 CLI live progress 与最终结果返回。
- WU-TOOLS-01-F01 引入 Fins durable job 的直接动机是 tool awaiting：LLM tool 不应阻塞在 download / upload / preprocess 长事务里，因此工具返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`，Host wait adapter 后续观察 completion。这个 awaiting 方向成立，但不要求 Fins 核心 ingestion runtime 自己成为 durable job system。
- Fins ingestion 的业务真源是 `dayu.fins.storage` 中的 source / processed / upload 产物和有界结果摘要；Fins job record 只能作为 awaiting observation handle，不能被提升为财报处理事实真源，也不应污染 CLI direct。
- NEW `dayu/cli/main.py` 已解析 `--log-level`、`--debug`、`--verbose`、`--quiet`，但当前 CLI main 未完成日志装配，导致普通 CLI 命令缺少符合 README 语义的 dayu 日志输出。
- NEW `dayu/cli/commands/fins.py` 对 Fins direct 命令启动 job 后只等待 `FinsDirectCommandService.wait_for_terminal()`，运行中没有面向用户的 progress print；Ctrl+C 后才输出 cancel 文案。
- NEW `dayu/service/fins_direct.py` 的 `wait_for_terminal()` 当前仅周期性 `read_job()` 直到终态，无法向 CLI / 未来 WeChat / GUI 提供 live progress 事件。
- NEW `dayu/cli/commands/init.py` 已在 reset、success、usage error、operation error 和 copy failure 路径输出用户可见文本；下一轮实施前应通过测试确认 init 的 UI print 仍正常，而不是把 init 误归入 Fins live stream 缺口。
- NEW `dayu/cli/commands/prompt.py` 与 `dayu/cli/commands/interactive.py` 均通过 `dayu/cli/output.py` 输出终态 final answer / failure / cancel 文本；但 `dayu/service/entrypoint_runtime.py` 当前只用 `watch_session_events()` 和 outbox read 等待 terminal，不向 CLI 投影运行中 progress 或 content delta。下一轮 plan 必须裁决这是否属于本条 UI print 缺口、应在本条修复，还是仅作为非 Fins Agent command 的后续 streaming/UI work。
- NEW `dayu/cli/commands/fins.py` 的 `upload_filings_from` 当前生成并打印 batch script，不启动 live Fins job；下一轮 plan 必须把它作为其它 CLI command 输出审计项，而不是错误地要求它恢复 live job stream。
- NEW 底层 Fins pipeline 仍保留 `DownloadEvent` / `download_stream` 等事件能力，但 direct job adapter 路径把运行中事件压成终态 summary。下一步修正应优先恢复 Service 暴露 `AsyncIterator[FinsEvent]` 的简单边界，而不是在 CLI direct 上补 durable job event sidecar。

### 2026-06-16 架构更正裁决

- CLI direct 裁决：`download` / `process` / `upload_filing` / `upload_material` / `process_filing` / `process_material` 是一次性本地命令，没有 durable job、cross-restart resume 或后台追踪需求。它们应通过 Service / Fins boundary 消费普通 `AsyncIterator[FinsEvent]`，使用 `PROGRESS` 输出运行中进度，使用 `RESULT` 收口最终结果；取消走当前执行的 async cancellation / cancel checker / KeyboardInterrupt 传播。
- Tool awaiting 裁决：`ToolAwaitingOutcome(EXTERNAL_JOB)` 仍是正确方向，因为 Engine tool handshake 不应等待长事务完成。但 awaiting 需要的是可观察、可 poll 的轻量 handle，不是 Fins 核心 runtime 的 durable job 状态机。Host wait adapter 可以用轻量 await ref 观察业务产物、执行结果或 runtime-local operation 状态；只有在明确需要跨进程 / 跨重启恢复未完成 ingestion 时，才单独设计 durable operation ledger。
- Fins runtime 裁决：Fins ingestion runtime 应优先表达业务执行、事件流和 storage 产物写入；`dayu.fins.storage` 中的财报产物和有界 result summary 才是业务真源。当前 durable job record / job store / per-job cancel / job event sidecar 组合对 CLI direct 和基础 runtime 都过重，下一轮修正必须把它收敛到 tool awaiting 所需的最小 observation handle，或在没有必要时移除。

### Replacement Plan Handoff Hints

下次以 `$phaseflow docs/host/design.md docs/host/issues-implementation-control.md` 恢复时，controller 必须把本条当作 accepted replacement plan 的 implementation，而不是 PR #143 的普通 fix。原因是现有 `docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`、PR #143 slice 记录和当前实现都以 durable Fins job event sidecar 为核心前提；该前提已经被 2026-06-16 裁决否定。当前 implementation 入口是 `docs/host/wu-cli-fins-obs-01-replacement-plan.md` 的 Slice A。

Goal confirmation 必须重新核对以下直接代码事实：

- `dayu/cli/commands/fins.py`：当前 CLI direct 仍是 `start_* -> FinsDirectJobHandle -> stream_job_events_until_terminal(...)`；SIGINT 仍映射到 `service.request_cancel(handle.job_id)`。这些是要移除的 durable job coupling，不是要保留的行为。
- `dayu/service/fins_direct.py`：当前 Service protocol 仍暴露 `FinsIngestionJobStart`、`read_job(...)`、`read_job_events(...)` 和 `request_cancel(...)`；replacement plan 应把 CLI-facing boundary 改为普通 `AsyncIterator[FinsEvent]`，避免 CLI 或 Service direct path 依赖 sidecar cursor。
- `dayu/fins/ingestion_runtime.py`：当前 `start_download` / `start_preprocess` / `start_upload` 先创建 durable queued job record 再提交后台 executor，并暴露 `read_job` / `read_job_events` / `request_cancel`。replacement plan 必须裁决哪些能力属于 tool awaiting 最小 observation handle，哪些应从 core runtime 移除或降级。
- `dayu/fins/ingestion/wait_adapter.py`、`dayu/fins/tools/*_tools.py`、`dayu/service/host_assembly.py`：tool awaiting 仍必须快速返回 `ToolAwaitingOutcome(EXTERNAL_JOB)` 并让 Host wait adapter 后续观察 completion；不能把这个裁决误读成删除 awaiting。
- `tests/cli/test_fins_commands.py`、`tests/service/test_fins_direct.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/service/test_host_assembly.py`：现有测试大量证明 durable job / sidecar 行为。replacement plan 必须明确哪些测试要改写为 `AsyncIterator[FinsEvent]` 语义，哪些 awaiting tool / wait adapter 测试仍保留但改为轻量 handle 语义。

Accepted replacement plan 按依赖边界切 slice，避免一次性大爆炸：

- Slice A：定义或复用 Fins direct `FinsEvent` typed contract / Service async iterator boundary；只固定 Service-facing runtime protocol，不做真实 runtime implementation。
- Slice B：重写 CLI direct command 消费路径和输出测试，确认六个 direct 命令不再需要 `job_id`、`read_job_events`、event sidecar 或 durable cancel。
- Slice D0：先做 lightweight observation handle contract-only checkpoint；在 Slice C 删除或降级 job store 前，固定 handle、poll / cancel / abandon API、durability / recovery 裁决。
- Slice C：收敛 Fins ingestion runtime 的 core execution API，区分 direct execution stream、business result summary 和 awaiting observation handle；删除或降级不再必要的 job event sidecar 前必须确认 D0 observation source 可支撑 wait adapter。
- Slice D：调整 Fins tool awaiting / wait adapter，使 `ToolAwaitingOutcome(EXTERNAL_JOB)` 保持非阻塞，但 await ref 轻量化；若当前需求要求任何 durable row，必须先给出 cross-process / cross-restart 恢复需求和最小 schema 理由。
- Slice E：README / design / tests 同步，清除 `dayu/README.md`、`dayu/service/README.md`、`dayu/fins/README.md`、`tests/README.md` 中把 CLI direct 或 core Fins runtime 描述成 durable job system 的文字。

Stop conditions：

- 如果 plan 需要修改 Host durable schema、EventLog、Run / Attempt 状态机、Engine `ToolExecutor` contract 或 `ToolAwaitingOutcome` union，必须停止并回到设计真源讨论；当前裁决不要求这些 Host / Engine 公共契约变更。
- 如果有人主张保留 Fins durable job store，必须说明它服务的明确需求是 tool awaiting observation、cross-process observation 还是 cross-restart recovery；不能用 CLI direct 或“以后可能有用”作为理由。
- 如果 direct CLI 修正必须依赖 sidecar JSONL、per-job sequence、`request_cancel(job_id)` 或 terminal fallback synthetic event，说明 plan 仍在沿用被否定前提，必须退回重写。
- 如果 awaiting handle 轻量化会导致 Host wait adapter 无法 poll/resolve 当前 tool awaiting path，必须在 plan gate 暴露为 blocker，不能在 implementation 中临时拼接。

### 目标

- 为 Fins direct commands 恢复 live event stream，覆盖 `download`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material`。
- 审计全部 CLI commands 的 log 与 UI print 路径，至少覆盖 `init`、`prompt`、`interactive`、`download`、`upload_filing`、`upload_material`、`upload_filings_from`、`process`、`process_filing`、`process_material`；对每个命令记录“正常 / 本条修复 / 后续 owner”的裁决依据。
- 在 Service / Fins boundary 提供可复用的普通 `AsyncIterator[FinsEvent]` 事件接口，使 CLI 只是一个 UI consumer，未来 WeChat / GUI 可以复用同一 Service 能力。
- 为 tool awaiting 保留非阻塞启动语义：工具仍可快速返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`，但 awaiting handle 必须轻量，不把 Fins runtime 核心执行模型固定成 durable job store。
- 恢复 CLI 日志装配，使 `--log-level`、`--debug`、`--verbose`、`--quiet` 符合 `dayu/README.md` 的日志级别语义。
- 明确区分 log 与 UI print：运行中 progress / result summary 是 UI 输出；诊断路径、执行骨架、错误上下文是日志。
- 保留 Fins direct command 的普通 CLI cancel 语义：用户中断后应通过 async task cancellation / cancel checker / KeyboardInterrupt 传播停止当前执行，并且本地退出行为要有明确、可测试的用户可见输出。

### 非目标

- 不全量搬迁 OLD `dayu-agent` CLI 实现。
- 不把 Fins direct commands 改造成 Host run、Host wait 或 Host event stream。
- 不把 CLI direct live events 改造成 durable Fins job、job event sidecar、per-job event sequence 或 Host wait adapter。
- 不把 `ToolAwaitingOutcome(EXTERNAL_JOB)` 等同于 Fins 核心 durable job system；awaiting 可以保留，但 durable operation ledger 只有在明确 cross-restart / cross-process 恢复需求成立时才允许单独设计。
- 不让 CLI、Service 或 Host 绕过 `dayu.fins.storage` 直接散落读取财报 storage。
- 不引入无当前需求支撑的通用跨进程 event bus、WebSocket 框架或平台化观察者系统。
- 不修改 Engine stream 术语或 Engine public contract。
- 不在本条恢复 `write` workflow 或旧 Fins workflow 全量实现。
- 不把 `upload_filings_from` 改造成 live job stream；它若继续只是脚本生成命令，验收重点是正常 UI print 和日志装配。
- 不在没有 goal confirmation / plan 裁决的情况下，把 `prompt` / `interactive` 的模型 token/content streaming 扩大成本条必做项；本条必须先基于现有 Host public event 能力和用户可见需求裁决是否纳入。

### 验收信号

- 运行 `dayu-cli download --ticker CME` 后，在下载进行中能持续看到用户可见进度输出；不需要等待 Ctrl+C 或终态才看到信息。
- `download`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material` 都通过同一类 Service / Fins boundary 暴露 `AsyncIterator[FinsEvent]` live event stream，而不是各命令在 CLI 中复制底层 storage 或 pipeline 逻辑。
- Fins tool awaiting 仍能非阻塞返回 awaiting outcome，但其 observation handle 不要求 Fins runtime 维护 durable job record / job event sidecar；若实现保留任何 durable row，plan 必须给出明确 cross-restart / cross-process 需求证据。
- 终态成功、失败、取消均有用户可见输出；输出不得依赖日志级别才能看见。
- `--verbose` / `--debug` 能显示符合 README 语义的诊断日志；默认日志不淹没 UI progress，不输出 provider secret、完整业务 payload、财报原文或大段 tool result。
- `init`、`prompt`、`interactive`、`upload_filings_from` 等非 live Fins job 命令的 UI print 经代码核对与测试分类：已正常的命令有测试或直接证据；不正常的命令已在本条修复，或被明确转入有 owner 的后续 work unit。
- `prompt` / `interactive` 的终态输出必须保持正常；若本条裁决不实现运行中 Agent progress / content streaming，plan 必须说明直接代码证据、设计依据、用户影响和后续 owner。
- Ctrl+C 触发当前 CLI 执行的普通取消路径；取消不要求 durable `job_id`，也不把本地退出伪装成后台 job 终态。
- 测试覆盖 CLI 输出审计、Service event stream、cancel、日志装配和禁止 CLI 直接 import `dayu.fins.storage` 的边界约束。

### Current gate artifacts

- replacement plan: `docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- replacement plan status: accepted; implementation next
- replacement accepted plan commit: `637d36a5`
- replacement plan review: `docs/reviews/plan-review-20260616-100941.md`; `docs/reviews/plan-review-20260616-101040.md`
- replacement plan review conclusion: both `pass-with-risks`; accepted blockers were lightweight observation handle underspecification, async bridge / cancellation underspecification, Slice A/C and C/D sequencing gaps, wait adapter recovery gap, and test coverage gaps
- replacement plan fix: integrated into `docs/host/wu-cli-fins-obs-01-replacement-plan.md` by AgentCodex
- replacement plan re-review: `docs/reviews/plan-rereview-20260616-102509-mimo.md`; `docs/reviews/plan-rereview-20260616-102606-ds.md`
- replacement plan re-review conclusion: AgentMiMo `pass`; AgentDS `pass-with-risks`; all high / medium findings fixed; no new material issues; nonblocking residual risks tracked as `WU-CLI-FINS-OBS-01-R6` / `R7` / `R8`
- implementation status: final closeout completed; Slice A/B/D0/C/D/E accepted, aggregate deepreview BF-1 fixed and re-reviewed, no blocking findings remain
- Slice A implementation: `docs/reviews/wu-cli-fins-obs-01-slice-a-implementation-codex.md`
- Slice B implementation: `docs/reviews/wu-cli-fins-obs-01-slice-b-implementation-codex.md`
- Slice A/B validation: `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q` 129 passed, 3 warnings; targeted `pyright` 0 errors
- Slice A/B code review: `docs/reviews/code-review-20260616-111036-mimo.md`; `docs/reviews/code-review-20260616-111112-ds.md`
- Slice A/B accepted findings requiring fix: MiMo R1/R2 SIGINT cancel race test and terminal result preservation; DS-001 user-visible `Fins job summary` terminology; DS-002 `_FinsSigintMonitor` docstring terminology
- Slice A/B review fix: `docs/reviews/wu-cli-fins-obs-01-slice-ab-review-fix-codex.md`
- Slice A/B re-review: `docs/reviews/wu-cli-fins-obs-01-slice-ab-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-ab-rereview-ds-20260616.md`
- Slice A/B re-review conclusion: PASS from both AgentMiMo and AgentDS; no blocking findings; nonblocking observations are deferred to existing Slice C / Slice E scope or defense-in-depth cleanup; post-review logger isolation follow-up was also checked by both reviewers and remains PASS
- Slice A/B post-review validation fix: added `tests/conftest.py` logger isolation because combined CLI -> Fins runtime test order exposed leaked `dayu` logger handlers bound to closed pytest capture streams; `tests/README.md` records this test infrastructure fact
- Slice A/B final validation: `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_runtime.py -q` 184 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; import check passed; `git diff --check` clean
- Slice D0 implementation: `docs/reviews/wu-cli-fins-obs-01-slice-d0-implementation-codex.md`
- Slice D0 validation: `pytest tests/fins/test_fins_ingestion_tools.py -q` 48 passed, 3 warnings; targeted `pyright` 0 errors
- Slice D0 code review: `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-ds-20260616.md`
- Slice D0 review conclusion: AgentMiMo `PASS`; AgentDS `PASS-WITH-FINDINGS`; no blocking findings
- Slice D0 accepted findings requiring fix: DS-D0-01 handle id alphabet ambiguity; fixed by narrowing observation handle ids to hex-only `[a-f0-9]`
- Slice D0 review fix: `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-fix-codex.md`
- Slice D0 review follow-up: both AgentMiMo and AgentDS appended follow-up PASS sections confirming DS-D0-01 fixed, `WU-CLI-FINS-OBS-01-R7` closed, and `WU-CLI-FINS-OBS-01-R9` correctly tracks Slice D retry guard / corrupt-token E2E LOST coverage
- Slice D0 final validation: `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` 103 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; import check passed; `git diff --check` clean
- Slice C implementation: `docs/reviews/wu-cli-fins-obs-01-slice-c-implementation-codex.md`
- Slice C validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 59 passed, 3 warnings; targeted `pyright` 0 errors; `git diff --check` clean
- Slice C code review: `docs/reviews/wu-cli-fins-obs-01-slice-c-review-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-c-review-ds-20260616.md`
- Slice C review conclusion: AgentMiMo `PASS`; AgentDS `PASS-WITH-FINDINGS`; no blocking findings
- Slice C accepted findings requiring fix: DS-C01 runtime direct stream should synthesize a failure RESULT if a producer exits without a RESULT; DS-C02 `_put_direct_queue` cancel branch should document intentional event discard after consumer exit
- Slice C review fix: `docs/reviews/wu-cli-fins-obs-01-slice-c-review-fix-codex.md`
- Slice C re-review: `docs/reviews/wu-cli-fins-obs-01-slice-c-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-c-rereview-ds-20260616.md`
- Slice C re-review conclusion: PASS from both AgentMiMo and AgentDS; direct runtime now guarantees no silent end, does not create durable job records or job event sidecar, and keeps the sync adapter bridge bounded/internal
- Slice C final validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 60 passed, 3 warnings; `pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py` 0 errors; `git diff --check` clean
- Slice D implementation: `docs/reviews/wu-cli-fins-obs-01-slice-d-implementation-codex.md`
- Slice D validation: `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_host_assembly.py -q` 152 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; import boundary check passed; `git diff --check` clean
- Slice D code review: `docs/reviews/wu-cli-fins-obs-01-slice-d-review-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-d-review-ds-20260616.md`
- Slice D review conclusion: PASS from both AgentMiMo and AgentDS; no blocking findings
- Slice D accepted review fix: `_FinsObservedOperationRecord` docstring now states the `_observation_lock` invariant for mutable registry snapshots
- Slice D review fix: `docs/reviews/wu-cli-fins-obs-01-slice-d-review-fix-codex.md`
- Slice D re-review: `docs/reviews/wu-cli-fins-obs-01-slice-d-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-d-rereview-ds-20260616.md`
- Slice D re-review conclusion: PASS from both AgentMiMo and AgentDS; `WU-CLI-FINS-OBS-01-R8` and `WU-CLI-FINS-OBS-01-R9` closed; slow-poller bounded queue backpressure was initially tracked as `WU-CLI-FINS-OBS-01-R10`
- Slice E implementation: `docs/reviews/wu-cli-fins-obs-01-slice-e-implementation-codex.md`
- Slice E validation: `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q` 281 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean
- Slice E code review: `docs/reviews/wu-cli-fins-obs-01-slice-e-review-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-e-review-ds-20260616.md`
- Slice E review conclusion: PASS from both AgentMiMo and AgentDS; no blocking findings
- Slice E accepted review fix: DS-E01 Fins README caller example now shows direct async stream first, separates observation handle flow, and labels legacy job-store helper example explicitly
- Slice E review fix: `docs/reviews/wu-cli-fins-obs-01-slice-e-review-fix-codex.md`
- Slice E re-review: `docs/reviews/wu-cli-fins-obs-01-slice-e-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-e-rereview-ds-20260616.md`
- Slice E re-review conclusion: PASS from both AgentMiMo and AgentDS; no blocking findings
- aggregate deepreview: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-ds-20260616.md`
- aggregate deepreview conclusion: AgentDS PASS; AgentMiMo found BF-1 blocking import-boundary test drift for `dayu.fins.direct_events`; all other direct stream / lightweight observation / runtime boundary / README / residual-risk checks passed
- aggregate fix: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex-20260616.md`
- aggregate fix validation: `pytest tests/service/test_import_boundary.py -q` 1 passed; BF-1 fixed by adding the precise Service import-boundary allowlist entry `dayu.fins.direct_events` and syncing `tests/README.md`
- aggregate fix re-review: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-ds-20260616.md`
- aggregate fix re-review conclusion: PASS from both AgentMiMo and AgentDS; BF-1 closed, `dayu.fins` prefix remains forbidden except explicit public boundary allowlist, no new findings
- final closeout: `docs/reviews/wu-cli-fins-obs-01-final-closeout-20260616.md`
- final closeout accepted local commit: `f83fd497`
- final local validation: `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/service/test_import_boundary.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q` 282 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean
- residual reconciliation: closed R6/R7/R8/R9/R10 removed from active residual table; R3/R5 closed by WU-CLI-FINS-DIAG-01 and removed from active residual table
- diagnostic output plan: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- diagnostic output plan review: `docs/reviews/wu-cli-fins-diagnostic-output-plan-review-ds-20260616.md`; `docs/reviews/plan-review-20260616-150120.md`
- diagnostic output plan fix: `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-codex-20260616.md`
- diagnostic output plan fix re-review: `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-rereview-ds-20260616.md`; `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-rereview-mimo-20260616.md`
- diagnostic output implementation: `docs/reviews/wu-cli-fins-diagnostic-output-implementation-codex-20260616.md`
- diagnostic output implementation review: `docs/reviews/wu-cli-fins-diagnostic-output-implementation-review-ds-20260616.md`; `docs/reviews/wu-cli-fins-diagnostic-output-implementation-review-mimo-20260616.md`
- diagnostic output review fix: `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-controller-20260616.md`
- diagnostic output review fix re-review: `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-rereview-ds-20260616.md`; `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-rereview-mimo-20260616.md`
- diagnostic output final validation: `pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q` 121 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean
- diagnostic output final closeout: `docs/reviews/wu-cli-fins-diagnostic-output-final-closeout-20260616.md`

### Superseded PR #143 durable sidecar artifacts

- superseded plan: `docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`
- superseded plan status: no longer current after 2026-06-16 replacement裁决
- superseded plan review: `docs/reviews/plan-review-20260615-154655.md`; `docs/reviews/plan-review-20260615-180157.md`
- superseded plan review adjudication: `docs/reviews/wu-cli-fins-obs-01-plan-review-adjudication-20260615-180440.md`
- superseded accepted findings requiring plan fix: DS-001 / MiMo-001, DS-002 / MiMo-002, DS-003 / MiMo-003, MiMo-004, DS-004 / MiMo-005, DS-005 / MiMo-006, DS-006 / MiMo-007, MiMo-008
- superseded plan review fix: `docs/reviews/wu-cli-fins-obs-01-plan-review-fix-codex.md`
- superseded plan re-review: `docs/reviews/plan-review-20260615-181139.md`; `docs/reviews/plan-review-20260615-181200.md`
- superseded plan re-review conclusion: PASS under the old durable sidecar premise; not current after replacement裁决
- superseded accepted plan commit: `f9cb56de`
- slice 1 implementation: `docs/reviews/wu-cli-fins-obs-01-s1-implementation-codex.md`
- slice 1 validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 47 passed, 3 warnings; `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` 0 errors
- slice 1 code review: `docs/reviews/code-review-20260615-183010.md`; `docs/reviews/code-review-20260615-183203.md`
- slice 1 code review adjudication: `docs/reviews/wu-cli-fins-obs-01-s1-code-review-adjudication-20260615-183453.md`
- slice 1 accepted findings requiring fix: MiMo-001 test non-terminal event append failure WARN path; DS-F002 remove event type re-export from `ingestion_runtime.__all__`; DS-F003 update `dayu/fins/README.md` and `tests/README.md`
- slice 1 deferred findings: MiMo-002 / DS-F001 sidecar sequence lookup scalability deferred to Slice S2 before high-frequency progress events
- slice 1 fix: `docs/reviews/wu-cli-fins-obs-01-s1-fix-codex.md`
- slice 1 fix validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 48 passed, 3 warnings; `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` 0 errors
- slice 1 re-review: `docs/reviews/code-review-20260615-184311.md`; `docs/reviews/code-review-20260615-184409.md`
- slice 1 re-review conclusion: PASS; accepted findings fixed 3/3; remaining blockers none
- slice 1 final local validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 48 passed, 3 warnings; `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` 0 errors
- slice 1 accepted commit: `3787f43d`
- slice 5 implementation: `docs/reviews/wu-cli-fins-obs-01-s5-implementation-codex.md`
- slice 5 validation: `pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q` 110 passed, 3 warnings; `pyright dayu/cli/main.py dayu/cli/commands/fins.py dayu/service/fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py` 0 errors
- slice 5 code review: `docs/reviews/code-review-20260615-201047.md`; `docs/reviews/code-review-20260615-201327.md`
- slice 5 code review adjudication: `docs/reviews/wu-cli-fins-obs-01-s5-code-review-adjudication-20260615-201806.md`
- slice 5 accepted findings requiring fix: S5-FIX-01 shared runtime logging helpers; S5-FIX-02 avoid duplicate ERROR logs for one exception; S5-FIX-03 direct default log-level coverage
- slice 5 fix: `docs/reviews/wu-cli-fins-obs-01-s5-fix-codex.md`
- slice 5 fix validation: `pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/runtime/test_log.py -q` 137 passed, 3 warnings; `pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/commands/fins.py dayu/service/fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/runtime/test_log.py` 0 errors
- slice 5 re-review: `docs/reviews/wu-cli-fins-obs-01-s5-rereview-mimo-20260615-203350.md`; `docs/reviews/wu-cli-fins-obs-01-s5-rereview-ds-20260615-203350.md`
- slice 5 re-review adjudication: `docs/reviews/wu-cli-fins-obs-01-s5-rereview-adjudication-20260615-204204.md`
- slice 5 re-review conclusion: PASS; accepted findings fixed 3/3; remaining blockers none
- slice 5 accepted commit: `8d93dc68`
- slice 6 implementation: `docs/reviews/wu-cli-fins-obs-01-s6-implementation-codex.md`
- slice 6 validation: `git diff --check` passed; docs-only README text verified against S1-S5 code facts; no pytest / pyright required because production and test code were unchanged
- slice 6 code review: `docs/reviews/wu-cli-fins-obs-01-s6-review-mimo-20260615-204936.md`; `docs/reviews/wu-cli-fins-obs-01-s6-review-ds-20260615-204936.md`
- slice 6 code review adjudication: `docs/reviews/wu-cli-fins-obs-01-s6-review-adjudication-20260615-205433.md`
- slice 6 review conclusion: PASS; remaining blockers none
- slice 6 accepted commit: `2d4679af`
- aggregate deepreview: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260615-205916.md`; `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-ds-20260615-205638.md`
- aggregate deepreview adjudication: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-adjudication-20260615-210618.md`
- aggregate accepted findings requiring fix: AGG-FIX-01 corrupted event sidecar line recovery; AGG-FIX-02 CLI synthetic terminal fallback rendering coverage; AGG-FIX-03 `_LOGGER` Final annotation consistency
- aggregate fix: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex.md`
- aggregate fix validation: `pytest tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py -q` 83 passed, 3 warnings; `pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py` 0 errors; `git diff --check` passed
- aggregate fix re-review: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-mimo-20260615-211431.md`; `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-ds-20260615-211431.md`
- aggregate fix re-review adjudication: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-adjudication-20260615-211921.md`
- aggregate fix re-review conclusion: PASS; accepted findings fixed 3/3; remaining blockers none
- aggregate fix accepted commit: `804b3b7d`
- final local validation: `pytest tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/runtime/test_log.py -q` 210 passed, 3 warnings; `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py dayu/service/fins_direct.py dayu/cli/main.py dayu/cli/commands/fins.py dayu/cli/output.py dayu/runtime/log.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/runtime/test_log.py` 0 errors
- closeout: `docs/reviews/wu-cli-fins-obs-01-closeout-20260615-212045.md`
- draft PR: #143 https://github.com/noho/dayu-agent-r/pull/143
- 2026-06-16 control-doc decision: PR #143 durable job event sidecar premise is invalid for CLI direct; additionally, Fins tool awaiting may keep `ToolAwaitingOutcome(EXTERNAL_JOB)` but must not force core Fins ingestion runtime into an over-heavy durable job system. Next fix gate must handle both corrections together before merge decision.

## WU-RET-00 Host Storage Lifecycle Retention Policy

### 状态

GitHub Issue #43 当前为 OPEN，已 currentize 为 Host storage lifecycle / retention umbrella。它不是已实现的 `purge_session` 本身：session-scoped destructive purge 已经完成；本条完成并归档的是 umbrella 下第一轮 storage lifecycle safety boundary。后续 active child 仍由主控文档跟踪：Tool Trace cold JSONL retention 由 WU-RET-01 / #36 承接；`purge_session`-driven retention cleanup 由 WU-RET-03 / #78 承接；compaction artifact retention 由 WU-RET-04 / #156 作为 #78 child 承接；Audit JSONL retention 由 WU-RET-02 / #96 承接。

### 设计与代码核对

- `docs/host/design.md` 明确 `purge_session` 是第一版唯一 destructive EventLog retention exception。
- `dayu/host/durable/purge.py` 已实现 `purge_session_durable(...)`，在同一 transaction 内删除目标 Session 的可恢复事实、写入 tombstone 与 purge idempotency record。
- `dayu/host/README.md` 明确第一版 purge 不实现 retention scheduler、周期 GC、DB vacuum、audit JSONL rotation / compaction、外部 audit 投递或 tool trace cold JSONL retention policy。
- purge 成功后会删除目标 Session 的 EventLog rows、payload descriptor / 本地 SQLite payload、memory snapshot、minimal read model、projection checkpoint / failure、outbox terminal projection、tool trace hot rows 和旧 command idempotency rows；共享 artifact 只在没有其它 durable ref 引用时清理。
- Host payload descriptor 当前用于把大 payload 从 EventLog inline JSON 中分离，ToolRuntime accept barrier、admission、compact artifact 等路径会写入 descriptor 或 SQLite payload；长期生命周期不能靠零散 best-effort DELETE 解决。

### 目标

- 设计 Host storage lifecycle / retention policy，明确 manual purge、scheduled retention、operator cleanup 和 DB maintenance 的边界。
- 覆盖 raw payload / payload descriptor / SQLite payload 的生命周期。
- 裁决 chat/session history 在手动 purge 之外是否支持 time-window、workspace、user、run 或 session-scope cleanup。
- 覆盖 compact artifacts、diagnostic payloads、memory snapshots、read-model snapshots 与其它派生数据的保留边界。
- 设计 operator-visible cleanup / report command 或 maintenance API。
- 设计 DB maintenance：VACUUM / incremental vacuum / WAL checkpoint / size reporting 的触发策略与非 command-path 执行边界。
- 保证 checkpoint / projection / analyzer safety：清理不能破坏 pending projection、diagnostic bundle、replay / recovery 所需事实或已经承诺保留的 audit trail。

### 非目标

- 不重新实现已完成的 `purge_session`。
- 不重复 WU-RET-01 / #36、WU-RET-03 / #78、WU-RET-04 / #156 与 WU-RET-02 / #96 的 child work unit 实施。
- 不在 command path 中做长耗时 cleanup、VACUUM 或文件扫描。
- 不静默删除仍被 EventLog、payload descriptor、projection、audit、trace 或 analyzer 需要的 artifact。
- 不把 credential scrub 与 retention / deletion 混为一谈。

### 验收信号

- storage lifecycle policy 明确区分 manual purge、scheduled retention、operator cleanup 和 DB maintenance。
- payload descriptor / SQLite payload / artifact refs 的删除证明有测试覆盖，尤其共享引用与 projection lag 场景。
- operator 能看到 storage usage report：EventLog rows、payload descriptors、SQLite payload size、artifact size、projection tables、WAL / DB size、JSONL sizes 或其它 owner 分类。
- cleanup / retention 不影响 Host recovery、retry、replay、RunInputBuilder、memory projection 或 analyzer 直接证据。
- slow maintenance 只在显式 maintenance entrypoint / scheduler 中运行，不阻塞 EventLog append、run admission、cancel、resume 或 terminal closeout。

### 当前 gate artifacts

- plan: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- plan review: `docs/reviews/wu-ret-00-plan-review-mimo.md`; `docs/reviews/wu-ret-00-plan-review-ds.md`
- plan adjudication / fix: `docs/reviews/wu-ret-00-plan-review-adjudication.md`
- plan re-review: `docs/reviews/wu-ret-00-plan-rereview-mimo.md`; `docs/reviews/wu-ret-00-plan-rereview-ds.md`
- accepted plan decision: PASS; accepted findings 12/12 fixed; DB VACUUM / SQLite space reclamation deferred to GitHub Issue #76
- accepted plan commit: `a2f94be0`
- slice 1 implementation: `docs/reviews/wu-ret-00-slice1-implementation-codex.md`
- slice 1 code review: `docs/reviews/wu-ret-00-slice1-code-review-mimo.md`; `docs/reviews/wu-ret-00-slice1-code-review-ds.md`
- slice 1 fix: `docs/reviews/wu-ret-00-slice1-fix-codex.md`
- slice 1 re-review: `docs/reviews/wu-ret-00-slice1-rereview-mimo.md`; `docs/reviews/wu-ret-00-slice1-rereview-ds.md`
- slice 1 review conclusion: PASS; accepted findings fixed 3/3; validation `pytest tests/host/test_artifact_store.py -q` 16 passed; `pyright dayu/host/durable/artifact.py tests/host/test_artifact_store.py` 0 errors; full `pyright` 0 errors
- slice 1 accepted commit: `473f1e6d`
- slice 2 implementation: `docs/reviews/wu-ret-00-slice2-implementation-codex.md`
- slice 2 validation: `pytest tests/host/test_storage_usage_report.py -q` 5 passed; `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 28 passed; target `pyright` 0 errors
- slice 2 code review: `docs/reviews/wu-ret-00-slice2-code-review-mimo.md`; `docs/reviews/wu-ret-00-slice2-code-review-ds.md`
- slice 2 finding adjudication: MiMo F01 accepted for fix; DS Finding 2 deferred in general but current public facade error mapping fixed now; all other findings accepted or deferred-with-owner by review
- slice 2 fix: `docs/reviews/wu-ret-00-slice2-fix-codex.md`
- slice 2 fix validation: `pytest tests/host/test_storage_usage_report.py -q` 7 passed; `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 28 passed; `pyright dayu/host/storage_maintenance.py tests/host/test_storage_usage_report.py` 0 errors
- slice 2 re-review: `docs/reviews/wu-ret-00-slice2-rereview-mimo.md`; `docs/reviews/wu-ret-00-slice2-rereview-ds.md`
- slice 2 review conclusion: PASS; accepted findings fixed 1/1; validation `pytest tests/host/test_storage_usage_report.py -q` 7 passed; `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 28 passed; full `pyright` 0 errors
- slice 2 accepted commit: `9c044934`
- slice 3 implementation: `docs/reviews/wu-ret-00-slice3-implementation-codex.md`
- slice 3 validation: `pytest tests/host/test_storage_orphan_proof.py tests/host/test_storage_maintenance.py -q` 10 passed; `pytest tests/host/test_storage_usage_report.py tests/host/test_artifact_store.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 51 passed; target `pyright` 0 errors
- slice 3 code review: `docs/reviews/wu-ret-00-slice3-code-review-mimo.md`; `docs/reviews/wu-ret-00-slice3-code-review-ds.md`
- slice 3 review conclusion: PASS; blocking findings 0; validation full `pyright` 0 errors
- slice 3 accepted commit: `4691ad9b`
- slice 4 implementation: `docs/reviews/wu-ret-00-slice4-implementation-codex.md`
- slice 4 validation: `pytest tests/host/test_storage_maintenance.py -q` 9 passed; `pytest tests/host/test_artifact_store.py tests/host/test_storage_usage_report.py tests/host/test_storage_orphan_proof.py tests/host/test_purge_session.py -q` 56 passed; target `pyright` 0 errors; `git diff --check` passed
- slice 4 code review: `docs/reviews/wu-ret-00-slice4-code-review-mimo.md`; `docs/reviews/wu-ret-00-slice4-code-review-ds.md`
- slice 4 review conclusion: PASS; blocking findings 0; validation full `pyright` 0 errors
- slice 4 accepted commit: `f5b1cccd`
- aggregate deepreview: `docs/reviews/wu-ret-00-aggregate-deepreview-mimo.md`; `docs/reviews/wu-ret-00-aggregate-deepreview-ds.md`
- aggregate deepreview conclusion: PASS; blocking findings 0; DS Finding 001 accepted and fixed; DS Findings 002/003 deferred as non-blocking diagnostics/defensive hardening; DS Open Question Q1 fixed; DS Open Question Q2 deferred as non-blocking consistency question
- aggregate deepreview fix: `docs/reviews/wu-ret-00-aggregate-deepreview-fix-codex.md`
- aggregate deepreview re-review: `docs/reviews/wu-ret-00-aggregate-deepreview-rereview-mimo.md`; `docs/reviews/wu-ret-00-aggregate-deepreview-rereview-ds.md`
- aggregate deepreview re-review conclusion: PASS; blocking findings 0; validation `pyright dayu/host/api.py dayu/host/open_host.py` 0 errors; `git diff --check` passed
- aggregate deepreview accepted commit: `26439cb2`
- draft PR readiness: ready; remaining risks have owners/destinations: DB VACUUM / SQLite space reclamation remains deferred to GitHub Issue #76; Tool Trace JSONL retention remains WU-RET-01 / GitHub Issue #36; `purge_session`-driven retention cleanup remains WU-RET-03 / GitHub Issue #78; compaction artifact retention remains WU-RET-04 / GitHub Issue #156 under #78; Audit JSONL retention remains WU-RET-02 / GitHub Issue #96; DS Finding 002/003 and Open Question Q2 are non-blocking diagnostics/defensive consistency items that do not change WU-RET-00 correctness and can be reconsidered with future maintenance ergonomics work.
- draft PR: https://github.com/noho/dayu-agent-r/pull/139
- PR review: `docs/reviews/wu-ret-00-pr139-review-mimo.md`; `docs/reviews/wu-ret-00-pr139-review-ds.md`
- PR review conclusion: PASS; blocking findings 0; accepted test/documentation findings fixed; DS async event-loop I/O and package-root constant export findings deferred as non-blocking maintenance ergonomics/public-surface choices; CI checks not reported on draft PR branch, local validation passed
- PR review fix: `docs/reviews/wu-ret-00-pr139-fix-codex.md`
- PR review re-review: `docs/reviews/wu-ret-00-pr139-rereview-mimo.md`; `docs/reviews/wu-ret-00-pr139-rereview-ds.md`
- PR review re-review conclusion: PASS; blocking findings 0; validation `pytest tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py -q` 18 passed; `pyright tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py` 0 errors
- PR review accepted commit: `20b1b4ac`
- post-PR-review push commit: `5f591ae4`; pushed to `github/work/wu-ret-00-retention`; PR 139 merge state CLEAN at closeout check; GitHub status check rollup empty on draft PR branch
- final validation: `pytest tests/host/test_artifact_store.py tests/host/test_storage_usage_report.py tests/host/test_storage_orphan_proof.py tests/host/test_storage_maintenance.py tests/host/test_purge_session.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 97 passed; full `pyright` 0 errors; `git diff --check` passed
- final closeout: draft-PR-pass; GitHub Issue #43 not closed because PR 139 is still draft/open and merge/issue closure requires separate authorization; after PR 139 merge, next entry point is WU-OBS-00 discussion gate

## WU-CM-05 LLM Compaction Proposal Typed Parsing

### 状态

GitHub Issue #93，作为 GitHub Issue #81 的后续子任务。#81 已关闭，本条 deferred 前置条件已解除；用户指定恢复推进。Plan artifact 已生成并完成 fix：`docs/host/host-issues/wu-cm-05-llm-compaction-proposal-typed-parsing-plan.md`。Plan review artifacts：`docs/reviews/plan-review-20260612-140624.md`、`docs/reviews/plan-review-20260612-140644.md`；plan re-review artifacts：`docs/reviews/plan-review-20260612-141710.md`、`docs/reviews/plan-review-20260612-141946.md`。AgentMiMo / AgentDS re-review 均为 pass，accepted findings 全部已修复；accepted plan commit `153c43e3`。WU-CM-05-S1 implementation report：`docs/reviews/wu-cm-05-s1-implementation-report.md`。Code review artifacts：`docs/reviews/code-review-20260612-143526.md`、`docs/reviews/code-review-20260612-143730.md`；controller decision：`docs/reviews/wu-cm-05-s1-code-review-controller.md`。WU-CM-05-S1 accepted slice commit `7f2ce2c5`。WU-CM-05-S2 implementation report：`docs/reviews/wu-cm-05-s2-implementation-report.md`。S2 code review artifacts：`docs/reviews/code-review-20260612-144954.md`、`docs/reviews/code-review-20260612-145145.md`；S2 fix re-review artifacts：`docs/reviews/code-review-20260612-145931.md`、`docs/reviews/code-review-20260612-145954.md`。AgentDS / AgentMiMo re-review 均为 PASS，accepted finding 已修复；WU-CM-05-S2 accepted slice commit `da8cda65`。WU-CM-05-S3 implementation report：`docs/reviews/wu-cm-05-s3-implementation-report.md`。S3 code review artifacts：`docs/reviews/code-review-20260612-151038.md`、`docs/reviews/code-review-20260612-151142.md`；S3 fix re-review artifacts：`docs/reviews/code-review-20260612-151919.md`、`docs/reviews/code-review-20260612-151955.md`。AgentMiMo / AgentDS re-review 均为 PASS，accepted docstring fix 已修复；WU-CM-05-S3 accepted slice commit `f3a3c0e3`。Aggregate deepreview artifacts：`docs/reviews/code-review-20260612-152820.md`、`docs/reviews/code-review-20260612-153234.md`；AgentDS / AgentMiMo aggregate deepreview 均为 PASS。Controller validation：`pytest tests/host/test_llm_compaction.py -q` 37 passed；`pytest tests/host/test_compaction_contract.py -q` 13 passed；`python -m pyright dayu/ tests/ utils/` 0 errors。Post-closeout cleanup 已为 `tests/host/fake_compaction.py` 补齐 JSON object 递归校验并移除测试 helper `cast(...)` residual。

### 目标

- 在 #81 确定新的 compact JSON shape 后，将 LLM proposal parsing 收敛为显式 typed validation。
- 消除 unchecked cast、宽 payload 和模糊错误分类。
- 固定转换边界：LLM raw final answer -> parse JSON -> typed LLM compaction proposal -> Host-owned `CompactionCandidate` 或 #81 后等价 typed contract。

### 非目标

- 不在 #81 前抢先实现。
- 不改变 compact output 的业务含义。
- 不放宽非法 proposal 的接受条件。

### 验收信号

- 每个 post-#81 proposal 字段都有直接验证路径。
- invalid proposal 的 diagnostic 能定位字段和原因。
- malformed JSON、缺必填字段、字段类型错误、未知 label / ref、数组超限、非法 enum / patch operation 都有测试。

## WU-CM-06 Terminal Summary Text Policy Convergence

### 状态

GitHub Issue #94，作为 GitHub Issue #81 的后续子任务。#81 已关闭，本条 deferred 前置条件已解除；用户指定恢复推进。Plan artifact：`docs/host/host-issues/wu-cm-06-terminal-summary-text-policy-plan.md`。Plan review artifacts：`docs/reviews/plan-review-20260612-154220.md`、`docs/reviews/plan-review-20260612-154418.md`；plan re-review artifacts：`docs/reviews/plan-review-20260612-154915.md`、`docs/reviews/plan-review-20260612-154942.md`；focused plan re-review artifacts：`docs/reviews/plan-review-20260612-155743.md`、`docs/reviews/plan-review-20260612-155955.md`。Implementation preflight found and corrected a plan evidence issue: memory consumer is inline-only, while durable projection / run-input adapters may hydrate descriptor-backed terminal artifact `content` into transient `final_answer` before memory consumption. AgentDS / AgentMiMo focused re-review 均为 PASS；controller editorial fix removed ambiguity and fixed Slice 1 read API policy tests to create `tests/host/test_read_api_terminal_policy.py` explicitly. Corrected plan commit `e9ca9288`。WU-CM-06-S1 implementation report：`docs/reviews/wu-cm-06-s1-implementation-report.md`。S1 code review artifacts：`docs/reviews/code-review-20260612-160858.md`、`docs/reviews/code-review-20260612-161139.md`；accepted low findings fixed: durable projection hydration test naming and malformed `terminal_summary_digest` coverage。S1 fix re-review artifacts：`docs/reviews/code-review-20260612-162004.md`、`docs/reviews/code-review-20260612-162045.md`；AgentDS / AgentMiMo re-review 均为 PASS。WU-CM-06-S1 accepted slice commit `c46993d0`。WU-CM-06-S2 implementation report：`docs/reviews/wu-cm-06-s2-implementation-report.md`。S2 code review artifacts：`docs/reviews/code-review-20260612-162954.md`、`docs/reviews/code-review-20260612-163025.md`；AgentMiMo / AgentDS review 均为 PASS。WU-CM-06-S2 accepted slice commit `956c5840`。Aggregate deepreview artifacts：`docs/reviews/code-review-20260612-163719.md`、`docs/reviews/code-review-20260612-164013.md`；AgentDS / AgentMiMo aggregate deepreview 均为 PASS。Controller validation：`pytest tests/host/test_terminal_summary_payload.py tests/host/test_read_api_terminal_policy.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py -q` 95 passed；`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` clean。Residual risks: caller-side overlong truncation remains explicitly out of WU-CM-06 scope and owned by caller budget/display tests；private helper / integration imports in tests are nonblocking test-scope coupling；compaction evidence explicit naming / integration coverage remains low severity because strict resolver behavior is function-tested and current docstring is not contradictory。无阻断 residual risk。WU-CM-06 accepted deepreview commit `246cd1c3`。terminal summary、assistant conclusion、episode summary、answer anchor 与 continuity 的语义边界已在现有 Host 代码中部分落地，本条以 policy matrix tests 和必要 docstring 收敛为主，不重新设计 terminal taxonomy。

### 目标

- 在 #81 后收敛 terminal summary 的来源、截断、渲染和 fallback policy。
- 避免 terminal summary 与 compact summary、assistant conclusion 语义重叠。
- 固定成功、失败、取消、lost、governance failure 与 compacted episode summary 的文本 policy 矩阵。

### 非目标

- 不重新设计 #81 已落地的 Conversation Memory 语义。
- 不把 terminal summary 变成事实引用源。
- 不改变 Run terminal taxonomy。
- 不让 compact / episode summary 冒充 terminal summary 或 final answer。
- 不借本条引入新的 public result read API。

### 验收信号

- terminal summary 在 success、failure、cancel、governance failure 下语义一致。
- 渲染测试覆盖空 summary、长 summary 和 compact 后 summary。
- memory projection 只在 policy 允许时把 terminal summary 用作 continuity，不得升级为 evidence-backed fact。

## WU-CM-08 Compaction Material Readability And Smoke Maintenance

### 状态

GitHub Issue #95，作为 GitHub Issue #81 的子任务；#81 已关闭，本条前置条件已解除，用户指定恢复推进。Issue #95 当前为 OPEN。Preflight 结论：动机成立，但 issue body 中 `stable_input` / `history_input` / `evidence_input` 是旧命名；当前设计真源和代码使用 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`。本条定位为测试可维护性和 compaction material readability cleanup，不负责裁决 Conversation Memory 语义模型。Plan artifact：`docs/host/host-issues/wu-cm-08-compaction-material-readability-smoke-plan.md`。Plan review artifacts：`docs/reviews/plan-review-20260612-164857.md`、`docs/reviews/plan-review-20260612-165055.md`；accepted findings fixed by plan amendment。Plan re-review artifacts：`docs/reviews/plan-review-20260612-165449.md`、`docs/reviews/plan-review-20260612-191500.md`；AgentMiMo / AgentDS re-review 均为 PASS。Accepted plan commit `fce2fca0`。WU-CM-08-S1 implementation report：`docs/reviews/wu-cm-08-s1-implementation-report.md`；validation `pytest tests/host/test_compact_material.py -q` 35 passed，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S1 code review artifacts：`docs/reviews/code-review-20260612-170451.md`、`docs/reviews/code-review-20260612-090406.md`；AgentMiMo / AgentDS review 均为 PASS。WU-CM-08-S1 accepted slice commit `bd3515d1`。WU-CM-08-S2 implementation report：`docs/reviews/wu-cm-08-s2-implementation-report.md`；validation `pytest tests/host/test_public_compact_smoke.py -q` 11 passed, 1 skipped，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S2 code review artifacts：`docs/reviews/code-review-20260612-171737.md`、`docs/reviews/code-review-20260612-200000.md`；AgentMiMo / AgentDS review 均为 PASS。WU-CM-08-S2 accepted slice commit `5cb68505`。Aggregate deepreview artifacts：`docs/reviews/code-review-20260612-172729.md`、`docs/reviews/code-review-20260612-202833.md`；AgentMiMo / AgentDS aggregate deepreview 均为 PASS；blocking findings 0；validation `pytest tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py -q` 46 passed, 1 skipped；`python -m pyright dayu/ tests/ utils/` 0 errors；AgentDS 额外验证相关 7 个测试文件 178 passed, 1 skipped；`compact_material.py` coverage 87%。Residual risks: `collect_selected_compaction_request_evidence_inputs` internal function name is not LLM-facing；AgentMiMo 提出的 helper 可复用性、defensive type check 深度、control-doc 引用完整性均为低严重度非阻断观察。无阻断 residual risk。Accepted deepreview commit `366d8df1`。

### 目标

- 改善 compaction material 的 chunking、可读性和测试 fixture 可维护性。
- 保持 public memory scenario smoke 覆盖关键用户路径。
- 让 smoke 失败能定位到输入构造、material pack / chunking / prompt-local labels、compactor request / proposal、memory projection 或 RunInput rendering 边界。

### 非目标

- 不改变 memory snapshot schema。
- 不裁决或实现 #81 semantic memory categories。
- 不用 snapshot 大量金文件掩盖语义测试缺失。
- 不引入新的 compactor JSON 语义。

### 验收信号

- compaction material 结构稳定、易读，且变更有小范围测试。
- smoke 失败能定位到输入构造、compaction、projection 或 rendering 边界。

## WU-CM-09 Durable Memory Snapshot Corruption Policy

### 状态

GitHub Issue #41 当前为 OPEN，原状态为 deferred behind #81；#81 已关闭，用户指定恢复推进。Preflight 结论：动机成立，但当前代码已经具备 P8.5 的保守行为，读到 corrupt / schema-mismatched / digest-mismatched memory snapshot 时 fail closed，进入 typed repair-required 或 projection failure / WARNING，不会自动覆盖损坏 row。本 WU 不修“静默吞错”，也不让 memory snapshot 成为 truth；真实缺口是 post-#81 operator-facing corruption policy、分类诊断与显式维护入口。Plan artifact：`docs/host/host-issues/wu-cm-09-durable-memory-snapshot-corruption-policy-plan.md`。Plan review artifacts：`docs/reviews/plan-review-20260612-173823.md`、`docs/reviews/plan-review-20260612-173831.md`；AgentMiMo / AgentDS review 均为 PASS-WITH-FINDINGS，无 blocker。Findings amendment：types / classifier 改为 `dayu.host.durable.memory` owner，明确 manual corruption 归入五类 failure kind，明确 `storage_read_failed` monkeypatch 目标，补充 result `__post_init__` 校验、baseline validation 与测试组织。Focused plan re-review artifacts：`docs/reviews/plan-review-20260612-174631.md`、`docs/reviews/plan-review-20260612-174632.md`；AgentMiMo / AgentDS re-review 均为 PASS，3/3 findings 已关闭，无 blocker。Accepted plan commit `e20a8a19`。WU-CM-09-S1 implementation report：`docs/reviews/wu-cm-09-s1-implementation-report.md`；validation `pytest tests/host/test_memory_projection.py -q` 26 passed，`pytest --cov=dayu.host.durable.memory --cov-report=term-missing tests/host/test_memory_projection.py -q` 26 passed / `dayu/host/durable/memory.py` 80%，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S1 code review artifacts：`docs/reviews/code-review-20260612-180244.md`、`docs/reviews/code-review-20260612-180250.md`；AgentMiMo / AgentDS review 均为 PASS，low findings fixed before accepted slice commit。S1 focused code re-review artifacts：`docs/reviews/code-review-20260612-180748.md`、`docs/reviews/code-review-20260612-180754.md`；AgentMiMo / AgentDS re-review 均为 PASS。WU-CM-09-S1 accepted slice commit `a9f77611`。WU-CM-09-S2 implementation report：`docs/reviews/wu-cm-09-s2-implementation-report.md`；validation `pytest tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` 25 passed，`pytest --cov=dayu.host.storage_maintenance --cov-report=term-missing tests/host/test_storage_maintenance.py -q` 12 passed / `dayu/host/storage_maintenance.py` 88%，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S2 code review artifacts：`docs/reviews/code-review-20260612-181714.md`、`docs/reviews/code-review-20260612-181556.md`；AgentMiMo / AgentDS review 均为 PASS。WU-CM-09-S2 accepted slice commit `77c32c32`。WU-CM-09-S3 implementation report：`docs/reviews/wu-cm-09-s3-implementation-report.md`；validation `pytest tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` 51 passed，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S3 code review artifacts：`docs/reviews/code-review-20260612-182602.md`、`docs/reviews/code-review-20260612-182356.md`；AgentMiMo / AgentDS review 均为 PASS。Aggregate deepreview artifacts：`docs/reviews/code-review-20260612-183208.md`、`docs/reviews/code-review-20260612-183054.md`；AgentMiMo / AgentDS aggregate deepreview 均为 PASS，blocking findings 0；validation `pytest tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` 51 passed；`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` clean。WU-CM-09 accepted deepreview commit `3e98565d`。Post-closeout cleanup 已补充 identity read failure defensive branch focused test；scan failure、row identity failure 与 row-level corruption classes 均已覆盖。无阻断 residual risk。当前处于 completed gate。

### 当前 gate artifacts

- plan: `docs/host/host-issues/wu-cm-09-durable-memory-snapshot-corruption-policy-plan.md`
- plan review: `docs/reviews/plan-review-20260612-173823.md`; `docs/reviews/plan-review-20260612-173831.md`
- plan re-review: `docs/reviews/plan-review-20260612-174631.md`; `docs/reviews/plan-review-20260612-174632.md`
- plan re-review conclusion: AgentMiMo / AgentDS 均为 PASS; blocking findings 0; accepted findings 3/3 closed by amendment
- accepted plan commit: `e20a8a19`
- aggregate deepreview: `docs/reviews/code-review-20260612-183208.md`; `docs/reviews/code-review-20260612-183054.md`
- aggregate deepreview conclusion: PASS; blocking findings 0; validation `pytest tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` 51 passed; `python -m pyright dayu/ tests/ utils/` 0 errors
- accepted deepreview commit: `3e98565d`
- draft PR: https://github.com/noho/dayu-agent-r/pull/140
- PR review: `docs/reviews/pr-review-20260614-mimo.md`; `docs/reviews/pr-review-20260614-ds.md`
- PR review fix: `docs/reviews/pr-review-fix-20260614.md`
- PR review re-review: `docs/reviews/pr-review-rereview-20260614-ds.md`
- accepted PR review commit: `306b9011`
- final closeout: `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`

### 设计与代码核对

- `docs/host/design.md` 明确 memory snapshot 是 EventLog 派生 read model，可重建、可修复，不是 Host truth；memory snapshot 与 projection checkpoint 使用同一 SQLite durable store transaction 提交。
- `dayu/host/durable/memory.py` 的 `write_memory_snapshot_with_checkpoint(...)` 在同一 transaction 内写入 snapshot 并推进 projection checkpoint。
- `write_memory_snapshot(...)` 写入前调用 `_validate_snapshot_digest(...)`，并在写入后读回校验。
- `read_memory_snapshot(...)`、`read_latest_memory_snapshot(...)` 与 `read_latest_memory_snapshot_at_or_before(...)` 会解析 snapshot JSON、恢复 typed snapshot、校验 digest，并校验 durable item kind。
- `tests/host/test_run_input_builder.py` 已覆盖 snapshot 缺失和损坏时进入 `MemoryProjectionRepairRequired`，且不改 Run / Attempt / EventLog。
- `dayu/host/durable/memory.py` 已在 `_validate_snapshot_item_kinds(...)` 中拒绝旧 durable `verified_fact` item kind；WU-CM-09-S1 需补齐对应 integrity classification / fail-closed 测试，不能把当前未确认测试覆盖当作已完成事实。

### 目标

- 在 #81 完成后，重新核对 post-#81 memory snapshot shape 与 durable projection contract。
- 明确 corrupt snapshot row 的失败来源分类：partial write、schema drift、manual DB edit、serializer bug、unsupported old row、storage corruption 或 digest mismatch。
- 设计是否需要 quarantine table、operator command、maintenance repair entrypoint 或自动 rebuild / overwrite policy。
- 如果允许自动 rebuild / overwrite，必须有 proof、checksum、backup / quarantine 与测试，且不能静默发生在 command path。
- 明确 projection failure rows、memory repair logs、operator reports 与 future analyzer 如何暴露 corrupt snapshot 状态。

### 非目标

- 不在 #81 前围绕旧 snapshot shape 做 repair / quarantine 实现。
- 不让 memory snapshot 成为 Host durable truth、recovery truth 或 EventLog 替代品。
- 不添加旧 corrupt payload 兼容 reader，除非后续迁移明确要求。
- 不静默覆盖 damaged snapshot rows。
- 不把 corrupt snapshot 当作普通可忽略 projection lag。

### 验收信号

- post-#81 memory snapshot corruption policy 已同步设计真源与本总控。
- 测试覆盖 invalid JSON、schema-mismatched JSON、digest mismatch、unsupported item kind、manual corruption 和 storage-read failure 分类。
- corrupt latest snapshot 不会污染 RunInputBuilder、compact material、prompt assembly、recovery 或 projection checkpoint。
- rebuild / quarantine / overwrite 如被引入，必须由显式 operator-facing command 或 maintenance entrypoint 触发，且保留诊断证据。
- diagnostics 保留足够 operator 分析信息，但不泄漏大 prompt / tool payload 内容。
- LLM-facing material 保持可读，不暴露 EventLog ledger wrapper、payload descriptor、digest 或 Host provenance internals。

## WU-CM-12 Conversation Memory Design Refinement And Implementation Drift Repair

### 状态

本条是用户裁决纳入本文档留痕的 immediate residual work unit，不创建 GitHub Issue。目标是把 `docs/host/conversation-memory-material-budget-discussion.md` 中已经裁决清楚的 Conversation Memory material / assemble / compact / fallback / five semantic memories 语义写回 Host 设计真源，并据此修复当前实现漂移。

2026-06-18 pre-plan design truth repair 已完成：`docs/host/design.md` 已写入 expanded `assemble(...)`、五类 Session Semantic Memory 映射、`post_compact_delta_material` / `current_input_anchor` / selected recent window / protected floor 边界、tier 0-5 fallback 状态机、no silent truncation / preview / summary 化约束、`memory_projection_policy` owner 边界、section-aware degrade 禁止动作与 fail closed 条件。两路 review 与 focused re-review 均 PASS；后续 plan / implementation / review 必须以更新后的 `docs/host/design.md` 为设计真源。

### Current gate artifacts

- design write-back: `docs/reviews/wu-cm-12-design-writeback-codex-20260618.md`
- design write-back review: `docs/reviews/wu-cm-12-design-writeback-review-mimo-20260618.md`; `docs/reviews/wu-cm-12-design-writeback-review-ds-20260618.md`
- accepted design write-back fix: `docs/reviews/wu-cm-12-design-writeback-fix-codex-20260618.md`
- focused re-review: `docs/reviews/wu-cm-12-design-writeback-rereview-mimo-20260618.md`; `docs/reviews/wu-cm-12-design-writeback-rereview-ds-20260618.md`
- design write-back validation: `git diff --check` PASS; targeted `rg` checks for tier 0-5, expanded `assemble(...)`, no silent truncation, `host_run_id` turn group, policy owner, section-aware degrade restrictions, and fallback fail closed conditions PASS.
- plan: `docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md`
- plan review: `docs/reviews/plan-review-20260618-135627.md`; `docs/reviews/plan-review-20260618-135902.md`
- plan review adjudication: `docs/reviews/plan-review-wu-cm-12-adjudication-20260618-140218.md`
- plan re-review: `docs/reviews/plan-review-20260618-140854.md`; `docs/reviews/plan-review-20260618-141022.md`
- plan gate validation: `git diff --check` PASS; plan artifact whitespace check PASS via `git diff --no-index --check /dev/null docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md`; WU-CLI-ACTIVITY-01 residual public smokes re-adjudicated PASS (`2 passed`).
- accepted plan commit: `8186f678`
- Slice S1 implementation: `docs/reviews/wu-cm-12-s1-implementation-codex-20260618.md`
- Slice S1 code review: `docs/reviews/code-review-20260618-142551.md`; `docs/reviews/code-review-20260618-143243.md`
- Slice S1 code review adjudication: `docs/reviews/code-review-wu-cm-12-s1-adjudication-20260618-143543.md`
- Slice S1 fix: `docs/reviews/wu-cm-12-s1-fix-codex-20260618.md`
- Slice S1 focused re-review: `docs/reviews/code-review-20260618-143944.md`; `docs/reviews/code-review-20260618-144008.md`
- Slice S1 validation: `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q` PASS (`118 passed`); `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S1 commit: `7f71c731`
- Slice S2 implementation: `docs/reviews/wu-cm-12-s2-implementation-codex-20260618.md`
- Slice S2 code review: `docs/reviews/code-review-20260618-151719.md`; `docs/reviews/code-review-20260618-151848.md`
- Slice S2 code review adjudication: `docs/reviews/code-review-wu-cm-12-s2-adjudication-20260618-152125.md`
- Slice S2 focused re-review: `docs/reviews/code-review-20260618-152833.md`; `docs/reviews/code-review-20260618-152931.md`
- Slice S2 validation: `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view tests/host/test_dispatch_scheduler.py::test_reactive_fallback_decision_uses_memory_policy_caps -q` PASS (`130 passed`); `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S2 commit: `7b239aef`
- Slice S3 implementation: `docs/reviews/wu-cm-12-s3-implementation-codex-20260618.md`
- Slice S3 code review: `docs/reviews/code-review-wu-cm-12-s3-mimo-20260618-160003.md`; `docs/reviews/code-review-wu-cm-12-s3-ds-20260618-160229.md`
- Slice S3 code review adjudication: `docs/reviews/code-review-wu-cm-12-s3-adjudication-20260618.md`
- Slice S3 focused re-review: `docs/reviews/code-review-wu-cm-12-s3-rereview-mimo-20260618-161132.md`; `docs/reviews/code-review-wu-cm-12-s3-rereview-ds-20260618-161031.md`
- Slice S3 validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` PASS (`181 passed`); `pyright dayu/host/run_input.py dayu/host/compact_material.py dayu/host/context_fallback.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S3 commit: `3bab485c`
- Slice S4 implementation: `docs/reviews/wu-cm-12-s4-implementation-codex-20260618.md`
- Slice S4 code review: `docs/reviews/code-review-wu-cm-12-s4-mimo-20260618-164733.md`; `docs/reviews/code-review-wu-cm-12-s4-ds-20260618-164407.md`
- Slice S4 code review adjudication: `docs/reviews/code-review-wu-cm-12-s4-adjudication-20260618.md`
- Slice S4 focused re-review: `docs/reviews/code-review-wu-cm-12-s4-rereview-mimo-20260618.md`; `docs/reviews/code-review-wu-cm-12-s4-rereview-ds-20260618.md`
- Slice S4 validation: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py -q` PASS (`166 passed`); `pyright dayu/host/dispatch.py dayu/host/compact_material.py dayu/host/compaction.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S4 commit: `c12e9952`
- Slice S5 implementation: `docs/reviews/wu-cm-12-s5-implementation-codex-20260618.md`
- Slice S5 code review: `docs/reviews/code-review-wu-cm-12-s5-mimo-20260618.md`; `docs/reviews/code-review-wu-cm-12-s5-ds-20260618.md`
- Slice S5 code review adjudication: `docs/reviews/code-review-wu-cm-12-s5-adjudication-20260618.md`
- Slice S5 validation: `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py -q` PASS (`312 passed`); public continuity smokes PASS (`2 passed`); `pytest tests/host/test_public_compact_smoke.py -q` PASS (`11 passed, 1 skipped`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S5 commit: `2c46631b`
- residual reconciliation: `WU-CLI-ACTIVITY-01-PR-R1` closed by passing public continuity smokes; `WU-CM-12-S1-R1` closed by root-cause fix to `_facts_from_accepted_event` and focused regression coverage; `WU-CM-12-S4-R1` remains deferred-with-owner as a future reactive compact recovery follow-up requiring explicit owner assignment before implementation.
- aggregate deepreview: `docs/reviews/deepreview-wu-cm-12-mimo-20260618.md`; `docs/reviews/deepreview-wu-cm-12-ds-20260618.md`
- aggregate deepreview focused re-review: `docs/reviews/deepreview-wu-cm-12-rereview-mimo-20260618.md`; `docs/reviews/deepreview-wu-cm-12-rereview-ds-20260618.md`
- aggregate deepreview validation: aggregate Host/public suite PASS (`330 passed, 1 skipped`); `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- final closeout: `docs/reviews/wu-cm-12-final-closeout-20260618.md`
- final closeout residuals before user review: `WU-CLI-ACTIVITY-01-PR-R1` and `WU-CM-12-S1-R1` closed; `WU-CM-12-S4-R1` deferred to WU-CM-13; accepted tool evidence material retrieval-volume audit item was initially deferred.
- draft PR #150 was opened at https://github.com/noho/dayu-agent-r/pull/150, but user review reopened WU-CM-12 before draft-PR-pass acceptance. Reopened fix scope `WU-CM-12-FIX-R1`: EventLog-derived LLM-facing input material is legal by default and must not be rejected by private compact DTO field-length guards, default evidence chunking, or `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`; shrinkage must be expressed by selected-window policy, protected floor, context budget, provenance-preserving selection, or fail-closed behavior.
- WU-CM-12-FIX-R1 accepted repair plan: `docs/host/host-issues/wu-cm-12-fix-r1-material-guard-plan.md`
- WU-CM-12-FIX-R1 plan review: `docs/reviews/plan-review-20260618-182749.md`; `docs/reviews/plan-review-20260618-182916.md`
- WU-CM-12-FIX-R1 plan review adjudication: `docs/reviews/plan-review-wu-cm-12-fix-r1-adjudication-20260618-183756.md`
- WU-CM-12-FIX-R1 focused plan re-review: `docs/reviews/plan-review-20260618-183710.md`; `docs/reviews/plan-review-20260618-183827.md`
- WU-CM-12-FIX-R1 plan gate validation: `git diff --check` PASS. Review findings accepted and closed: Slice 2 material view mapping clarified; default evidence chunk helper retention ambiguity closed by delete-if-no-production-caller; no-default-chunk test assertions specified; long-session evidence scan performance residual deferred to a future Host material source performance hardening WU, not WU-CM-13.
- accepted WU-CM-12-FIX-R1 plan commit: `d904445e`
- WU-CM-12-FIX-R1 Slice 1 implementation: `docs/reviews/wu-cm-12-fix-r1-s1-implementation-codex-20260618.md`
- WU-CM-12-FIX-R1 Slice 1 code review: `docs/reviews/code-review-20260618-184822.md`; `docs/reviews/code-review-20260618-185121.md`
- WU-CM-12-FIX-R1 Slice 1 fix: `docs/reviews/wu-cm-12-fix-r1-s1-fix-codex-20260618.md`
- WU-CM-12-FIX-R1 Slice 1 focused re-review: `docs/reviews/code-review-20260618-185732.md`; `docs/reviews/code-review-20260618-185843.md`
- WU-CM-12-FIX-R1 Slice 1 validation: `pytest tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py -q` PASS (`127 passed`); `pyright dayu/host/compaction.py dayu/host/compact_material.py tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py` PASS (`0 errors`); `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 Slice 1 commit: `21ae992b`
- WU-CM-12-FIX-R1 Slice 2 implementation: `docs/reviews/wu-cm-12-fix-r1-s2-implementation-codex-20260618.md`
- WU-CM-12-FIX-R1 Slice 2 code review: `docs/reviews/code-review-20260618-191048.md`; `docs/reviews/code-review-20260618-191823.md`
- WU-CM-12-FIX-R1 Slice 2 code review adjudication: `docs/reviews/code-review-wu-cm-12-fix-r1-s2-adjudication-20260618.md`
- WU-CM-12-FIX-R1 Slice 2 validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q` PASS (`118 passed`); `pyright dayu/host/run_input.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py` PASS (`0 errors`); old private accepted-evidence limit symbols absent from `dayu` and `tests`; `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 Slice 2 commit: `f468654c`
- WU-CM-12-FIX-R1 Slice 3 validation: `docs/reviews/wu-cm-12-fix-r1-s3-validation-codex-20260618.md`
- WU-CM-12-FIX-R1 Slice 3 code review: `docs/reviews/code-review-20260618-192722.md`; `docs/reviews/code-review-20260618-192801.md`
- WU-CM-12-FIX-R1 Slice 3 focused re-review: `docs/reviews/code-review-20260618-193123.md`; `docs/reviews/code-review-20260618-193135.md`
- WU-CM-12-FIX-R1 Slice 3 adjudication: `docs/reviews/code-review-wu-cm-12-fix-r1-s3-adjudication-20260618.md`
- WU-CM-12-FIX-R1 Slice 3 validation commands: combined Host memory/compact/run-input suite PASS (`240 passed`); repository pyright PASS (`0 errors`); old private guard symbols absent from `dayu` and `tests`; `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 Slice 3 commit: `cc30b304`
- WU-CM-12-FIX-R1 aggregate deepreview: `docs/reviews/code-review-20260618-193713.md`; `docs/reviews/code-review-20260618-195224.md`
- WU-CM-12-FIX-R1 aggregate accepted findings: DS low finding `_provenance_from_evidence_blocks` dead `evidence_blocks` parameter accepted and fixed; MiMo low finding stale chunking test name accepted and fixed. No blocking correctness findings remained.
- WU-CM-12-FIX-R1 aggregate fix: `docs/reviews/wu-cm-12-fix-r1-aggregate-fix-codex-20260618.md`
- WU-CM-12-FIX-R1 aggregate focused re-review: `docs/reviews/code-review-20260618-195017.md`; `docs/reviews/code-review-20260618-195038.md`
- WU-CM-12-FIX-R1 aggregate fix validation: `pytest tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` PASS (`90 passed`); `pyright dayu/host/compact_material.py tests/host/test_compaction_operation.py` PASS (`0 errors`); full `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 aggregate deepreview commit: `a729ab18`
- WU-CM-12-FIX-R1 local gate conclusion: implementation, slice reviews, aggregate deepreview fix and focused re-review are complete. `WU-CM-12-FIX-R1` is closed locally; next gate is push existing branch to update draft PR #150, then run PR review before draft-PR-pass / final closeout.
- WU-CM-12-FIX-R1 push to draft PR #150: branch `wu-cm-12-conversation-memory-drift` pushed through commit `5382afc7`; PR #150 remained open draft at https://github.com/noho/dayu-agent-r/pull/150.
- WU-CM-12-FIX-R1 PR review: `docs/reviews/pr-150-review-20260618-195915.md`; `docs/reviews/pr-150-review-20260618-200404.md`
- WU-CM-12-FIX-R1 PR review adjudication: core FIX-R1 material-guard objective PASS in both reviews. Accepted and fixed only local quality findings for fallback `current_input_ref` diagnostic ordering and fallback selected-window cap boundary tests. `compaction_evidence.py` cleanup and recovery-tier rejected-attempt diagnostic completeness remain deferred / non-blocking residuals for later cleanup or diagnostics owner; `_facts_from_accepted_event` old bug fix must be called out in final closeout. The earlier `_vnext_compact_candidate_semantic_lines` defensive-depth asymmetry residual was closed by the follow-up user裁决 deleting compact output `MAX_VNEXT_*` guards.
- WU-CM-12-FIX-R1 PR review fix: `docs/reviews/wu-cm-12-pr-review-fix-codex-20260618.md`
- WU-CM-12-FIX-R1 PR review focused re-review: `docs/reviews/code-review-20260618-201316.md`; `docs/reviews/code-review-20260618-201451.md`
- WU-CM-12-FIX-R1 PR review fix validation: `pytest tests/host/test_run_input_builder.py -q` PASS (`80 passed`); `pyright dayu/host/context_fallback.py tests/host/test_run_input_builder.py` PASS (`0 errors`); full `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 PR review commit: `6b66732f`
- WU-CM-12-FIX-R1 current next gate: push accepted PR review commit and control-doc record to existing draft PR #150, then complete draft-PR-pass / final closeout.
- WU-CM-12-FIX-R1 final push: branch `wu-cm-12-conversation-memory-drift` pushed to draft PR #150 through the final closeout commit; PR remains open draft with no GitHub status checks reported at closeout time.
- WU-CM-12-FIX-R1 final closeout: `docs/reviews/wu-cm-12-fix-r1-final-closeout-20260618.md`
- WU-CM-12-FIX-R1 follow-up user裁决: compact output `MAX_VNEXT_*` parser safety guards are deleted because model output size is already bounded by model/provider output limits; parser / DTO keep schema, type, non-empty, uniqueness and provenance validation only.
- WU-CM-12-FIX-R1 final closeout constant audit: no remaining production code constant acts as a private field-length cap, lossy preview / summary cap, default evidence chunk cap, accepted-evidence row cap, or compact output parser item / text cap for EventLog-derived LLM-facing material outside `memory_projection_policy`. Retained non-policy constants are fixed message-envelope estimators, diagnostics limits, projection maintenance batch size, or prompt-local label grammar constants.
- WU-CM-12-FIX-R1 final residual owners: `WU-CM-12-S4-R1` remains deferred to WU-CM-13 only when explicitly assigned; `WU-CM-12-PR-R1` compact evidence cleanup and `WU-CM-12-PR-R3` recovery-tier diagnostic completeness are deferred-with-owner and not blockers. `WU-CM-12-PR-R2` is closed by deleting compact output `MAX_VNEXT_*` guards.
- WU-CM-12-FIX-R1 final state: draft-PR-pass. PR #150 remains draft; no merge, mark-ready, reviewer request, external issue closure, or follow-up WU selection was performed.
- WU-CM-12 final closeout 2026-06-19 three-way deepreview artifacts: `docs/reviews/repo-review-20260619-164637.md`, `docs/reviews/repo-review-20260619-164912.md`, `docs/reviews/repo-review-20260619-165328.md`.
- WU-CM-12 final closeout 2026-06-19 accepted fixes: proactive compact recovery persists operation-level rejected attempts from initial and recovery tiers with continuous attempt numbers; reactive recovery catch-up failure no longer blocks recovery dispatch; reactive fail-closed propagates recovering fail rejection; proposal cancellation after manifest recording returns a cancellation rejected attempt with manifest ref when Host cancellation is active; memory projection skips missing-run-id turn-floor protection and JSON bool integer confusion is rejected.
- WU-CM-12 final closeout 2026-06-19 focused re-review: AgentCodex and AgentDS reported blocking findings closed; AgentMiMo reported high-priority coverage findings closed and only non-blocking old debt / broader design observations remaining. Accepted formatting observation in `dispatch.py` was fixed before closeout.
- WU-CM-12 final closeout 2026-06-19 validation: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` PASS (`277 passed`); focused dispatch regression after final formatting fix PASS (`2 passed`); `pyright dayu/ tests/ utils/` PASS (`0 errors`).
- WU-CM-12 final closeout 2026-06-19 artifact: `docs/reviews/wu-cm-12-final-closeout-20260619.md`.
- WU-CM-12 final closeout 2026-06-19 residual reconciliation: `WU-CM-12-PR-R3` is closed by persisted recovery-tier rejected attempts; `WU-CM-13` remains deferred and not default next entry; broader old-debt observations require separate owner assignment.

### Design source / phaseflow 启动裁决

下一轮启动 `$phaseflow` 时，推荐入口为：

```text
$phaseflow design_doc=docs/host/conversation-memory-material-budget-discussion.md control_doc=docs/host/issues-implementation-control.md
```

原因：本 WU 启动时 `docs/host/design.md` 尚未包含本轮讨论中对 normal path、five fallback tiers、展开版 `assemble(...)`、compact / dispatch fallback 输入输出、accepted compact 五类 memory 输出，以及 no silent truncation / cap ownership 的细化，因此先以讨论稿作为 phaseflow 启动设计输入完成 design truth repair。

本 WU 的 pre-plan design truth repair 已完成并通过两路 review / focused re-review。后续 plan、implementation、review 与 finding adjudication 必须以更新后的 `docs/host/design.md` 为设计真源；讨论稿只保留为 rationale / handoff reference，不再替代设计真源。

如果 plan 需要修改 Host / Engine public API、durable schema、EventLog canonical semantics、Engine provider contract 或跨层 contracts，必须在 plan gate 停下来交给用户裁决；不得在 implementation 中顺手修改。

### 目标

- 将 Conversation Memory 设计从以下源头无歧义细化到可实施层：

```text
rendered_context =
  assemble(
    latest_accepted_compacted_view,
    post_compact_delta_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

- 在 `docs/host/design.md` 中定义 normal path 与 five fallback tiers：
  - tier 0 normal；
  - tier 1 compact recovery with tighter recent window；
  - tier 2 compact recovery with section-aware compacted view degrade；
  - tier 3 compact recovery delta-only；
  - tier 4 dispatch fallback floor-only；
  - tier 5 dispatch fallback current-input-only。
- 明确 tier 1-3 送 LLM compactor，accepted output 可提交 `CONTEXT_COMPACTED` 并 projection 为五类 Session Semantic Memory；tier 4-5 不送 LLM compactor，不提交 `CONTEXT_COMPACTED`，不生成 compact artifact / memory snapshot / 五类 memory。
- 明确 accepted compact output 只能投影为：
  - `trace_memory.reference_continuity_items`；
  - `evidence_fact_memory.evidence_backed_facts`；
  - `session_summary_memory.summary_text`；
  - `answer_anchor_memory.anchors`；
  - `forward_intent_memory.intents`。
- 将 `memory_projection_policy` 在 Host 内部解释为明确分组的 typed sections，至少包括：
  - `selected_recent_window_policy`；
  - `fallback_selected_recent_window_policy`；
  - `protected_recent_floor_policy`；
  - `semantic_memory_section_caps`；
  - `projection_repair_policy`。
  JSON 结构是否保持 flat 可由 plan 裁决，但 Host 内部不得继续用零散字段和私有常量共同决定 LLM-facing material 产量。
- 强约束 Agent：`latest_accepted_compacted_view`、`post_compact_delta_material`、`current_input_anchor` 进入 LLM-facing memory / compact / RunInput material 时禁止截断、preview 化或 summary 化。上下文缩小只能通过 deterministic selection、whole-item / whole-section keep-drop、chunking with provenance 或 fail closed 表达；不能把这些源 material 改写成摘要、预览文本或字段级裁剪文本。
- 修复当前实现漂移：字段级 silent truncation、compact input DTO 私有 1200 cap、ordinary RunInput compact summary 旁路、compactor output schema cap 与 `memory_projection_policy` 双真源、fallback selected window policy 未真正生效、selection / rendering material id 空间漂移、turn floor 按 raw item 而非 `host_run_id` turn group 保护等问题。
- 覆盖 residual `WU-CLI-ACTIVITY-01-PR-R1`：重新裁决并修复 Host public multiturn / tool wiring conversation memory smoke 中 final answer / tool result continuity 相关失败，前提是修复必须对齐本 WU 写回后的 Conversation Memory 设计真源。
- 保持代码修复与设计写回同源：实现只能细化更新后的 `docs/host/design.md`，不得重新发明 compact selector、fallback selector、memory material 产量路径或 summary / preview 语义。

### 非目标

- 不引入 semantic search、vector recall、prompt-conditioned retrieval 或长期 memory retrieval framework。
- 不实现 User Profile Memory；该能力仍由 WU-CM-11 / GitHub Issue #115 承接。
- 不实现 Conversation Memory eval benchmark；该能力仍由 WU-CM-10 / GitHub Issue #80 承接。
- 不修改 UI / log / diagnostic preview 的展示截断规则，除非发现它们被错误投影进 LLM-facing memory material。
- 不修改 tool 原始输出抓取、下载、转换或 tool truncation policy。
- 不把 fallback tier / compact diagnostic / projection diagnostic 投影给 LLM 作为业务事实。
- 不把讨论稿中的 `Implementation Handoff Notes`、current code owner、current gap、allowed files、测试命令或 plan slice 参考写入 `docs/host/design.md` 作为设计真源。

### 验收信号

- `docs/host/design.md` 已写入 normal + five fallback tiers、展开版 `assemble(...)`、compact / dispatch fallback 输入输出、five semantic memory output、no silent truncation、cap ownership 与 fallback state machine。
- `docs/host/design.md` 写回内容足以让 Gateflow plan 从设计真源直接进入 implementation，不需要实施 Agent 再从讨论稿补设计。
- `dayu/config/execution_profiles.json` 中 `memory_projection_policy` 的字段在 Host 内部有单一 typed section 解释入口，至少覆盖 selected recent window、fallback selected recent window、protected floor、semantic memory section caps 与 projection repair；不再被 DTO / schema 私有 cap 改写为另一套 LLM-facing material 产量真源。
- normal RunInput、compact input、tier 1-3 compact recovery fallback、tier 4-5 dispatch fallback 共享同一个 material selection / rendering 语义，差异只在 renderer、source label、accept barrier 和 tier output。
- `protected_recent_floor_policy` 以 `host_run_id` 为 turn group 保护最近 N 个 Host admitted user Run；floor 超预算时进入 tier 5，而不是静默截断或打散 turn group。
- final closeout 必须输出一份代码常量审计清单：列出代码中仍出现、且没有在 `dayu/config/execution_profiles.json` 的 `memory_projection_policy` 中定义的 LLM-facing memory material / compact material 产量相关常量；对每个常量说明状态为“已删除 / 已迁入 policy / 保留但非 LLM-facing / 保留为 parser safety guard / deferred-with-owner”，并说明理由。
- 受影响 Host memory / compact / RunInput / fallback tests 和相关 smoke 已更新并通过；`python -m pyright dayu/ tests/ utils/` 通过且不新增类型错误。

## WU-CM-13 Unified Conversation Compact Pipeline Convergence

### 状态

Deferred destination only。当前不创建 GitHub Issue，不是默认 next entry point，不进入 implementation。它承接 `WU-CM-12-S4-R1`，但 owner 语义经代码核对后重新收敛：问题不是“reactive recovery sequencing 从零缺失”，而是 proactive / reactive 目前只共享部分 compact 内核，尚未共享从 Conversation Memory material 到 accepted compact / failed compact / fallback decision 的完整 Host compact pipeline。

当前代码事实：reactive path 已具备 Engine ingest recovery sequencing、run-local cancellation token 传递、execution / cursor commit guard、accepted compact 后 recovery Attempt 启动，以及 fallback dispatch / fail-closed ordering。`WU-CM-13` 不应再按“补 reactive 状态机”理解；它的目标是消除 compact semantic pipeline 分散在 `dispatch.py` 与 `engine_ingest.py` 后导致的语义漂移风险。

实施顺序允许 `WU-CM-14` 先于 `WU-CM-13`。若 `WU-CM-14` 先落地 recent final answer preservation 逻辑，`WU-CM-13` 后续激活时必须把该逻辑作为 compact semantic pipeline 的组成部分重新核对并纳入共享路径；不得把 `WU-CM-14` 留作 proactive-only、reactive-only 或 RunInput-only 的旁路例外。

### 背景与动机

从第一性原理看，proactive compact 与 reactive compact 的触发 envelope 不同，但 compact 语义本身应是同一套：给定同源 EventLog / material source、latest accepted compacted view、post-compact delta material 与 current input anchor，Host 应通过同一组 selection / rendering / compact operation / quality gate / accepted-or-failed result construction 得到：

- accepted `CONTEXT_COMPACTED`，由 Conversation Memory projection 物化为五类 Session Semantic Memory；
- 或 `CONTEXT_COMPACTION_FAILED`，携带 retry / repair / fallback diagnostic；
- 或 tier 4/5 fallback decision input，只影响本次 RunInput rendering，不提交 compacted memory truth。

当前实现已共享 `run_compaction_operation()`、compact material pack builder 与 context event payload builder，但 proactive 与 reactive 仍分别拥有 material-to-result orchestration、accepted compact event append、failed compact event append、fallback decision glue，以及 tier 1-3 / multi-pass / tier 4/5 的局部策略入口。若继续分散实现，五类 Session Semantic Memory、展开版 `assemble(...)`、tier 1-3 compact recovery、tier 4/5 fallback、artifact / payload descriptor、attempt_count / rejected-attempt diagnostic 和 accepted compacted view 语义都可能漂移。

`WU-CM-14` 的 recent final answer preservation 也是同一原则下的 compact / RunInput material 语义：触发方式可以不同，但给定同一段 history、同一个 current input anchor、同一个 compact candidate / fallback decision 时，preservation 结果不应因 proactive 或 reactive trigger 漂移。若 `WU-CM-14` 在 `WU-CM-13` 之前实现，`WU-CM-13` 需要把它纳入 unified pipeline audit，而不是只统一既有 compact event construction。

外层状态机仍必须分开：proactive 是 pre-dispatch input governance；reactive 是 Engine overflow 后关闭当前 Attempt、Run 进入 `RECOVERING`、再启动 recovery Attempt。`WU-CM-13` 只统一 compact semantic pipeline，不把 proactive / reactive lifecycle 强行合并。

### 目标

- 抽出一个 Host 内部 compact pipeline owner，使 proactive / reactive 共享从 material view / material blocks 到 compact result 的语义代码路径。
- 若 `WU-CM-14` 已先实施，审计其 recent final answer preservation owner，并将其纳入 proactive / reactive shared compact material、fallback material 或 RunInput assembly 路径；不得保留触发方式专属的 preservation 分支。
- 收口 `dayu/host/compaction_evidence.py` 的旧 owner 状态：若其能力已由 unified pipeline / `compact_material.py` 覆盖，则删除模块并迁移测试；若仍有必要能力，则迁入 unified pipeline，不保留无生产调用的旁路 material helper。
- 统一 compact request generation：latest accepted compacted view、post-compact delta material、current input anchor、selected material blocks、prompt-local labels、source boundary refs 与 accepted evidence mapping refs 必须同源。
- 统一 compact recovery tiers：tier 1 fallback selected recent window、tier 2 section-aware compacted view degrade、tier 3 delta-only compact input 必须对 proactive / reactive 使用同一组 request builder / renderer 规则；reactive 需要 multi-pass 时也必须建立在同一组 material block 与 provenance 语义上。
- 统一 accepted compact result construction：artifact JSON、payload descriptor、`CONTEXT_COMPACTED` payload、accepted proposal manifest refs、quality check result、budget after compact、projection signal 与 accepted compacted view 语义不得在 dispatch / engine ingest 两处重复漂移。
- 统一 failed compact / fallback result construction：`CONTEXT_COMPACTION_FAILED` payload、attempt_count、retry / repair budget exhausted、rejected attempt diagnostic refs、tier 4/5 fallback input window、fallback budget result 与 fallback action 必须由同一套 helper 生成。
- 保持五类 Session Semantic Memory projection 只消费 accepted `CONTEXT_COMPACTED`；fallback、diagnostic、Host governance state、Engine state 不得被投影为业务事实。

### 非目标

- 不新增另一套 reactive-only compact implementation。
- 不保留 `dayu/host/compaction_evidence.py` 作为无生产调用、仅测试依赖的 shadow owner。
- 不把 dispatch lifecycle、Engine ingest lifecycle、Attempt closeout、`RUN_RECOVERING`、recovery Attempt creation 合并成一个 God pipeline；这些仍由各自 outer orchestration 持有。
- 不修改 public API、durable schema、EventLog canonical semantics、Engine provider contract 或跨层 contract，除非 `WU-CM-13` 激活后在 plan gate 获得单独裁决。
- 不把 unified pipeline 用作私有 DTO 字段长度上限、preview 化、summary 化、默认 evidence 条数限制或字段级裁剪的依据。
- 不引入 semantic search、vector recall、长期 memory retrieval framework 或 User Profile Memory。
- 不改变 `WU-CM-12` 已接受的 proactive / reactive lifecycle 语义，除非后续设计真源明确修订。

### 激活条件

- 用户或 GitHub Issue 明确指定 `WU-CM-13` 为 active owner；仅有 `WU-CM-12-S4-R1` deferred row 不足以启动实现。
- 若 `WU-CM-14` 已经进入 plan 或 implementation，`WU-CM-13` preflight 必须读取其设计裁决、代码路径和测试，明确哪些 preservation helper 属于 unified compact pipeline audit 范围。
- 启动时重新核对 `docs/host/design.md`、`docs/engine/design.md` 与本总控，确认 unified compact pipeline 仍符合 Conversation Memory 的 normal / fallback state machine、five semantic memory、`assemble(...)` 与 no silent truncation 约束。
- 若计划触及 Host / Engine public API、durable schema、EventLog canonical semantics 或 provider contract，必须在 plan gate 停下交给用户裁决。

### 验收信号

- `WU-CM-13` plan 明确 shared compact pipeline owner、outer proactive / reactive lifecycle boundary、commit guard 输入、result shape、fallback ordering 与测试边界。
- `WU-CM-13` plan 明确 `WU-CM-14` recent final answer preservation 与 shared compact pipeline 的关系：若该逻辑已存在，必须说明它被迁入 / 复用 / 保持在共享 owner 下；若尚未存在，必须说明未来 `WU-CM-14` 不得绕过 shared owner。
- proactive 与 reactive 的 compact request builder 使用同一组 material selection / rendering helper；差异只来自 trigger envelope、attempt / execution identity、cancellation token 与 commit guard。
- proactive 与 reactive 下的 recent final answer preservation / fallback / RunInput assembly 语义一致；如果某一路径不适用，测试或 plan 必须用状态机证据说明它不会经过该 preservation owner。
- `dayu/host/compaction_evidence.py` 已删除并完成测试迁移，或其仍需要的能力已迁入 unified compact pipeline owner 且存在生产调用；不得留下只有测试 import 的 Host material owner。
- proactive 与 reactive 的 accepted compact artifact / payload descriptor / `CONTEXT_COMPACTED` payload 由同一组 helper 生成；测试断言同一 compact candidate 在两种触发路径下产生一致的 accepted compacted view 语义。
- proactive 与 reactive 的 `CONTEXT_COMPACTION_FAILED` / tier 4/5 fallback diagnostic 由同一组 helper 生成；测试覆盖 fallback dispatch 与 fail-closed。
- 测试覆盖 proactive tier 1、tier 2、tier 3；reactive tier 1、tier 2、tier 3；reactive multi-pass；run cancellation；execution identity mismatch；cursor mismatch；stale recovery proposal；accepted compact commit；fallback dispatch / fail-closed ordering。
- 验证 accepted compact output 仍只生成五类 Session Semantic Memory，并且 fallback / diagnostic / Host governance state / Engine state 不投影为业务事实。
- 受影响 Host dispatch / Engine ingest / compact / RunInput / memory projection tests 通过；`python -m pyright dayu/ tests/ utils/` 通过且不新增类型错误。
- `utils/smoke_host_public_conversation_memory_scenarios.py` 必须真实运行成功，作为 WU-CM-13 final acceptance 的硬门槛；不得通过修改该 smoke、降低覆盖、绕过场景、放宽断言或改成无效通过来满足验收。

### Current gate artifacts

- plan: `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`
- plan review: `docs/reviews/plan-review-20260619-194515.md`
- plan review: `docs/reviews/plan-review-20260619-194657.md`
- focused plan re-review: `docs/reviews/plan-review-20260619-195507.md`
- focused plan re-review: `docs/reviews/plan-review-20260619-195521.md`
- final focused plan re-review: `docs/reviews/plan-review-20260619-200133.md`
- final focused plan re-review: `docs/reviews/plan-review-20260619-200143.md`
- plan adjudication: `docs/reviews/plan-review-wu-cm-13-adjudication-20260619.md`
- accepted scope: thin `compact_pipeline.py` helper owner; no tier 5 current-input-only fallback implementation; lifecycle guards remain caller-owned; WU-CM-14 uses pipeline-owned audited second-read raw-tail selection; `compaction_evidence.py` must be removed or fully migrated.
- Slice 1 implementation: `dayu/host/compact_pipeline.py` helper contracts, `tests/host/test_compact_pipeline.py`, `compaction_evidence.py` deletion, migrated compact material / operation tests, and `tests/README.md` update.
- Slice 1 code review: `docs/reviews/deepreview-20260619-211229.md`; `docs/reviews/deepreview-wu-cm-13-slice-1-20260619-211311.md`.
- Slice 1 code review adjudication: `docs/reviews/code-review-wu-cm-13-slice-1-adjudication-20260619.md`.
- Slice 1 validation: `pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` PASS (`91 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS; old `compaction_evidence` helper symbols absent from `dayu` and `tests`.
- accepted Slice 1 commit: `0390c9ad`.
- Slice 1 residual reconciliation: `WU-CM-12-PR-R1` closed by deleting `dayu/host/compaction_evidence.py` and migrating useful tests to `compact_material.py` / `compact_pipeline.py`; `WU-CM-13-S1-R1` and `WU-CM-13-S1-R2` deferred to Slice 2.
- Slice 2a implementation: proactive `dispatch.py` normal request uses `build_normal_compact_request_plan(...)`; proactive tier 1-3 recovery uses `build_tier_recovery_request_plans(...)`; proactive fallback failed payload / decision input uses `build_fallback_decision_input(...)`; dispatch-owned lifecycle and EventLog writes remain in `dispatch.py`.
- Slice 2a code review: `docs/reviews/deepreview-20260619-212804.md`; `docs/reviews/deepreview-wu-cm-13-slice-2a-20260619-212944.md`.
- Slice 2a code review adjudication: `docs/reviews/code-review-wu-cm-13-slice-2a-adjudication-20260619.md`.
- Slice 2a validation: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compact_pipeline.py -q` PASS (`88 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS; old proactive fallback helper / tier 5 / `fallback_tier` symbols absent from `dayu/host/dispatch.py`.
- accepted Slice 2a commit: `b180a510`.
- Slice 2a residual reconciliation: `WU-CM-13-S1-R2` is closed for proactive dispatch; the reactive ingest half remains tracked by the same residual until Slice 2b.
- Slice 2b implementation: reactive `engine_ingest.py` request construction uses `build_normal_compact_request_plan(...)`; reactive pass queue uses `build_reactive_pass_queue_plan(...)`; reactive fallback failed payload / decision input uses `build_fallback_decision_input(...)`; reactive lifecycle, cancellation, EventLog writes, and recovery Attempt creation remain in `engine_ingest.py`.
- Slice 2b code review: `docs/reviews/deepreview-20260619-214447.md`; `docs/reviews/deepreview-wu-cm-13-slice-2b-20260619-214451.md`.
- Slice 2b code review adjudication: `docs/reviews/code-review-wu-cm-13-slice-2b-adjudication-20260619.md`.
- Slice 2b validation: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compact_pipeline.py -q` PASS (`88 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS; old reactive request / pass queue / fallback helper / tier 5 / `fallback_tier` symbols absent from `dayu/host/engine_ingest.py`.
- accepted Slice 2b commit: `7b0367ab`.
- Slice 2b residual reconciliation: `WU-CM-13-S1-R2` closed by removing proactive and reactive duplicate helper owners from `dispatch.py` / `engine_ingest.py`.
- Slice 2c implementation: `run_input.py` ordinary post-compaction protected raw-tail provider now consumes `CompactPipelineProtectedRawTailProvider`, returns `CompactPipelineOrdinaryRawTailHandoff`, and delegates protected recent group selection / memory dedup to `select_ordinary_protected_raw_tail(...)`; fallback RunInput assembly remains on `_fallback_context_messages(...)`.
- Slice 2c code review: `docs/reviews/deepreview-20260619-220450.md`; `docs/reviews/deepreview-wu-cm-13-slice-2c-20260619-220501.md`.
- Slice 2c code review adjudication: `docs/reviews/code-review-wu-cm-13-slice-2c-adjudication-20260619.md`.
- Slice 2c validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_pipeline.py -q` PASS (`107 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS; required search confirms `compact_pipeline.py` owns ordinary protected raw-tail selection and `run_input.py` retains `protected_recent_turn_group_ids_for_material_blocks` only for the explicit fallback branch non-goal.
- Slice 2c residual reconciliation: `WU-CM-14-RR-1` closed because WU-CM-14 preservation is now audited through shared proactive/reactive compact pipeline helpers plus pipeline-owned ordinary raw-tail selection; `WU-CM-14-RR-3` closed because the second EventLog read remains a durable freshness adapter, while selection semantics are shared in `compact_pipeline.py`. `WU-CM-13-S1-R1` remains deferred to aggregate deepreview / final smoke for whole-WU accepted compact quality/provenance audit.
- accepted Slice 2c commit: `7aab0f94`.
- aggregate deepreview: `docs/reviews/deepreview-wu-cm-13-aggregate-mimo-20260619.md`; `docs/reviews/deepreview-wu-cm-13-aggregate-ds-20260619.md`.
- aggregate deepreview adjudication: `docs/reviews/deepreview-wu-cm-13-aggregate-adjudication-20260619.md`.
- aggregate validation: `pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` PASS (`305 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors, 0 warnings, 0 informations`); `python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact --pressure-mode auto` PASS (`SMOKE COMPACT_ACCEPTANCE status=pass requested_proactive=4 compacted_proactive=4 failed_total=0 artifact_files=12`); `git diff --check` PASS.
- aggregate residual reconciliation: `WU-CM-12-S4-R1` closed by accepted proactive/reactive shared compact pipeline convergence; `WU-CM-13-S1-R1` closed because the old malformed compacted payload fact-ref edge is closed by the typed `ConversationCompactOutputVNext` helper boundary plus operation-level candidate rejection coverage and compact payload/material provenance tests.
- accepted deepreview commit: `00da03a3`.
- PR preflight: `gh pr status` confirmed current branch has no associated PR; `gh pr view 150 --json ...` confirmed PR #150 is merged and came from `wu-cm-12-conversation-memory-drift`, not current branch.
- draft PR: #152 https://github.com/noho/dayu-agent-r/pull/152 (`wu-cm-14-final-answer-preservation` -> `main`, draft).
- PR review: `docs/reviews/pr-152-review-mimo-20260619.md`; `docs/reviews/pr-152-review-ds-20260619.md`.
- PR review adjudication: `docs/reviews/pr-152-review-adjudication-20260619.md`.
- PR review conclusion: PASS; no fix gate required. DS low finding about duplicated internal evidence source prefix constants is rejected because ordinary/fallback rendering path separation is intentional and extracting a shared owner now would add unnecessary coupling.
- accepted PR review commit: `f2970512`, pushed to #152.
- final closeout: `docs/reviews/wu-cm-13-final-closeout-20260619.md`.
- current gate: draft-PR-pass. PR #152 remains draft; mark-ready, reviewer requests, merge, branch deletion, and issue closure require separate user authorization.
- 若引入任何新的 LLM-facing memory material / compact material 产量常量，必须在 `dayu/config/execution_profiles.json` 的 `memory_projection_policy` 或本 WU 明确批准的 policy owner 中定义；否则 final closeout 的常量审计必须列为 open residual。

## WU-CM-14 Recent Final Answer Preservation for Ordinal Follow-ups

### 状态

`discussion-ready`。当前不创建 GitHub Issue，不进入 plan / implementation。本 WU 是 CM 语义讨论中新增的独立追踪项，承接 residual `WU-CM-14-R1`。

本 WU 不修改 `WU-CM-13` 的范围。`WU-CM-13` 只统一 proactive / reactive compact pipeline；本 WU 专注 compact 后 ordinary RunInput 是否仍具备回答局部序号追问所需的最近 assistant final answer 上下文。

两者存在实现约束关联：`WU-CM-14` 的 preservation 语义一旦被裁决为需要进入 compact material、compact accept quality gate、fallback material 或 ordinary RunInput assembly，就必须落在 proactive / reactive 共享的代码路径上，不得分别实现主动触发 compact 与被动触发 compact 的两套 preservation 逻辑。

### 场景

第 N 轮 assistant final answer 列出 4 条详细内容。第 N+1 轮用户输入“详细解释第三条”，并且本轮 dispatch 前触发 compact。

需求裁决：compact 后第 N+1 轮送给 Engine 的 messages 不能只等价于 `latest_accepted_compacted_view + current user prompt`。Host 必须在 compact boundary 后继续保留既有 protected recent raw tail；该 tail 复用现有 `selected_recent_window_turn_floor` / protected recent floor 语义，不新增 WU-CM-14 专属 floor、ordinal follow-up floor 或 prompt-pattern-specific cap。

protected recent raw tail 的基本单位仍是 turn group。最近 `selected_recent_window_turn_floor` 个 turn group 中已 committed、eligible、LLM-readable 的 material 应按 whole block / whole section keep-drop 进入 ordinary RunInput / fallback RunInput，至少覆盖历史 user prompt、assistant final answer、accepted readable tool evidence 与用户可见 Run outcome material。裸 tool request 不应单独作为 evidence；若 tool interaction 需要保留，必须通过 accepted readable evidence 或成对且自解释的 material 表达，不暴露 tool_call_id、digest、EventLog id、payload ref 或 Host 内部治理状态。

### 初步代码核对结论

- Answer Anchor Memory 已有实现路径：accepted compact output 中的 `answer_anchors` 会被 Conversation Memory projection 物化，并由 RunInputBuilder 渲染为 `## Prior Answer Anchors`。
- Answer Anchor Memory 的语义是“可被后续指代的历史回答轮廓”，不是原回答全文，也不是事实证明。
- selected recent window 按设计可以承载 post-compact delta material 中的 raw user input、assistant final answer、accepted tool evidence 和用户可见 outcome material。
- 一旦第 N 轮 final answer 被 compact 覆盖，而 accepted compact output 只保留短 answer anchor，第 N+1 轮 Engine 可能只能解析“第三条指什么”，但缺少“详细解释第三条”所需的完整文本和列表上下文。

### 设计裁决与剩余讨论点

- Answer Anchor Memory 负责指代解析，不负责承载完整展开所需的原回答上下文；recent raw tail 负责最近回答、工具证据和 outcome 的原始业务语义连续性。
- WU-CM-14 不新增 memory kind、不新增 floor、不实现 ordinal parser；preservation 复用 `selected_recent_window_turn_floor` / protected recent floor。
- compact accepted 后，`latest_accepted_compacted_view` 只代表 compact 覆盖范围内的旧历史语义视图；它不得吞掉仍处于 protected recent floor 内的 raw tail。
- preservation owner 初步归属于 selected recent window / protected recent floor 与 ordinary RunInput / fallback RunInput assembly 的共享 material selection 语义；plan gate 仍需用代码证据确认当前 owner 位置和最小改动点。
- preservation owner 如何复用 proactive / reactive shared compact pipeline，确保同一段 history、同一个 current input anchor 和同一项 accepted compact candidate 在两种触发方式下得到同义的 preservation / fallback / RunInput assembly 结果。
- 若第 N 轮 final answer 本身超预算，应采用 whole-item keep-drop、chunking with provenance、section-aware degrade 还是 fail closed；不得 silent truncation、preview 化或 summary 化后伪装为完整回答。
- 是否需要在 `docs/host/design.md` 增补 Answer Anchor Memory 与 recent raw final answer preservation 的边界说明。

### 非目标

- 不并入 `WU-CM-13`；不借本 WU 重新设计 proactive / reactive compact pipeline unification。
- 不允许为 proactive compact 与 reactive compact 分别实现语义不同的 recent final answer preservation 分支；触发方式不同不应改变 preservation 结果。
- 不新增 WU-CM-14 专属 protected floor、ordinal follow-up floor、recent answer cap 或另一套 selected recent window policy；复用 `selected_recent_window_turn_floor` / protected recent floor。
- 不引入 semantic search、vector recall、prompt-conditioned reranker 或长期 memory retrieval framework。
- 不实现 deterministic final answer outline parser 或“第三条”prompt-pattern parser。
- 不把 Answer Anchor Memory 升级成事实证明、完整回答存储或替代 raw final answer 的通用机制。
- 不通过字段级截断、固定 preview、私有 DTO cap 或 summary 化来保留超长 final answer。

### Entry Conditions

- 重新核对 `docs/host/design.md` 中 latest accepted compacted view、post-compact delta material、selected recent window、protected recent floor、Answer Anchor Memory、Reference Continuity 和 Prompt Assembly 的设计真源。
- 重新核对 RunInputBuilder、Conversation Memory projection、compact material selection 与相关测试，确认第 N+1 轮触发 compact 后 ordinary Engine messages 的实际组成。
- plan gate 先验证当前 `selected_recent_window_turn_floor` / protected recent floor 是否已经跨 compact boundary 生效；若未生效，plan 必须定位 root cause 并提出最小修复，不新增平行 policy owner。

### Acceptance Signals

- 文档明确裁决 ordinal follow-up 场景下，recent assistant final answer 与 Answer Anchor Memory 的职责边界。
- 文档和实现明确复用 `selected_recent_window_turn_floor` / protected recent floor；不得新增 WU-CM-14 专属 floor 或 prompt-pattern-specific retention rule。
- 文档明确裁决 WU-CM-14 preservation 逻辑与 WU-CM-13 shared compact pipeline 的关系：策略可以独立讨论，但实现必须避免 proactive / reactive 语义漂移。
- 测试必须覆盖：第 N 轮 final answer 列 4 条详细文本，第 N+1 轮“详细解释第三条”触发 compact，最终 Engine messages 除 accepted compacted view / memory sections 与 current user prompt 外，还包含 protected recent raw tail 中足以解释第三条的完整业务上下文。
- 测试必须覆盖 protected recent raw tail 的 eligible material 边界：history user prompt、assistant final answer、accepted readable tool evidence、user-visible outcome material；裸 tool request、Host internal refs / digest / EventLog id 不进入 LLM-facing tail。
- 测试还必须覆盖 proactive 与 reactive compact 触发下的同义 preservation 结果，除非 plan gate 明确证明某一路径不会经过该 preservation owner。
- 受影响 Host memory / compact / RunInput tests 通过；若发生代码修改，`python -m pyright dayu/ tests/ utils/` 通过且不新增类型错误。

### Current gate artifacts

- plan: `docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md`
- plan review: `docs/reviews/plan-review-wu-cm-14-mimo.md`
- plan review: `docs/reviews/plan-review-wu-cm-14-ds.md`
- plan adjudication: `docs/reviews/plan-review-wu-cm-14-adjudication-20260619.md`
- plan re-review: `docs/reviews/plan-rereview-wu-cm-14-mimo.md`
- plan re-review: `docs/reviews/plan-rereview-wu-cm-14-ds.md`
- plan re-review conclusion: AgentCodex fixed the plan; AgentMiMo PASS and AgentDS PASS. Accepted findings are closed: provider / transaction contract, activation condition, reactive compact-success and fallback regression coverage, duplicate prevention, allowed test boundary cleanup, and reactive frozen material stop condition. Plan is code-generation-ready.
- plan gate validation: `git diff --check` clean
- accepted plan commit: `d4b271cb`
- implementation review: `docs/reviews/code-review-20260619-190815.md`
- implementation review: `docs/reviews/code-review-20260619-191152.md`
- implementation focused re-review: `docs/reviews/code-review-20260619-192312.md`
- implementation focused re-review: `docs/reviews/code-review-20260619-192408.md`
- code review adjudication: `docs/reviews/code-review-wu-cm-14-adjudication-20260619.md`
- implementation validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` passed 220 tests; `python -m pyright dayu/ tests/ utils/` passed 0 errors; `git diff --check` clean.
- accepted slice commit: `921c6219`
- aggregate deepreview: `docs/reviews/code-review-20260619-192740.md`
- aggregate deepreview: `docs/reviews/code-review-20260619-193018.md`
- aggregate focused re-review: `docs/reviews/code-review-20260619-193352.md`
- aggregate focused re-review: `docs/reviews/code-review-20260619-193419.md`
- aggregate adjudication: `docs/reviews/wu-cm-14-aggregate-deepreview-adjudication-20260619.md`
- aggregate validation: `rg -n "_current_only_material_blocks" dayu tests` returned no matches; `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` passed 220 tests; `python -m pyright dayu/ tests/ utils/` passed 0 errors; `git diff --check` clean.
- next gate: WU-CM-13 goal confirmation / plan gate

### Residual risks

- `WU-CM-14-RR-1` closed by WU-CM-13 Slice 2c: WU-CM-14 preservation is now audited through shared proactive/reactive compact pipeline helpers plus pipeline-owned ordinary raw-tail selection.
- `WU-CM-14-RR-3` closed by WU-CM-13 Slice 2c: the second EventLog read remains a durable freshness adapter, while protected recent group eligibility and memory dedup semantics are shared in `compact_pipeline.py`.

## WU-CM-15 Conversation Memory Public Smoke Reactive Compact And Fallback Coverage

### 状态

`draft-PR-pass`。当前不创建 GitHub Issue。Goal confirmation 已由用户裁决通过：本 WU 只是增加 public smoke 覆盖，覆盖被动 compact 和 fallback。Accepted plan commit `97518e93` 已创建；accepted implementation slice commit `572a88df` 已创建；aggregate deepreview / fix / focused re-review 已通过；closeout logging / pressure observability fix 已验证；draft PR #157 已创建；PR review PASS；final closeout 已完成。PR #157 仍为 open draft，merge / mark-ready / reviewer request / branch deletion 需要用户另行授权。

本 WU 是对 `utils/smoke_host_public_conversation_memory_scenarios.py` fresh run 后发现的 smoke coverage gap 的独立追踪项。当前 `memory-compact` suite 已覆盖真实 conversation memory 主干与 proactive compact accepted 路径，但没有显式覆盖 worker / provider overflow 触发的 reactive compact，也没有显式覆盖 compact 全部失败后的 deterministic fallback dispatch。

### 动机判断

问题真实存在，但严重性应按“smoke coverage gap”而不是“生产代码已知 bug”处理：

- fresh `memory-compact` run 通过，且观察到 `requested_proactive=4`、`compacted_proactive=4`、`failed_total=0`。
- 同一次 run 的 reactive 计数为 0，说明当前 public conversation memory smoke 没有 exercised reactive compact 主路径。
- 当前 `memory-compact` 验收把任何 `CONTEXT_COMPACTION_FAILED` 视为 hard fail，因此不能直接把 fallback 成功场景塞进同一 suite。
- 生产代码和 focused tests 已存在 reactive compact / fallback 相关覆盖，但 `utils/` public conversation memory smoke 尚未把这些路径作为一等 smoke target。

### 初步设计裁决

WU-CM-15 应新增显式 suite，而不是改变现有 `memory-compact` 的语义：

- 保持现有 `memory-compact`：继续作为 proactive compact accepted 与长会话 conversation memory 主干 smoke；不得为了 fallback 放宽 `failed_total == 0` 断言。
- 新增 reactive compact smoke suite：使用 public Host 路径，通过 deterministic worker 或等价测试 runner 在第一次 Attempt 返回 `context_compaction_requested`，模拟 provider overflow；Host 完成 reactive compact 后启动 recovery Attempt 并最终 succeeded。
- 新增 fallback smoke suite：通过 deterministic bad compactor / rejecting compactor / missing compactor 等可控方式让 compact operation 失败，触发 dispatch fallback；fallback succeeded 是该 suite 的目标行为，不得被现有 proactive acceptance 规则误判为失败。
- 不依赖真实 provider / 真实上下文窗口自然触发 reactive compact 或 fallback。真实 LLM smoke 可以保留为 `memory-compact`，reactive / fallback smoke 应优先 deterministic，避免不稳定、耗时和成本扩散。

### 目标

- `utils/smoke_host_public_conversation_memory_scenarios.py` 或相邻 public smoke 入口能够显式运行 reactive compact path。
- 同一 smoke 体系能够显式运行 deterministic fallback dispatch path。
- smoke log 能展示 reactive / fallback 的关键诊断信号，支持问题定位且不引入 per-delta stream 噪音。
- 现有 `memory-compact` suite 的 proactive compact accepted 验收保持不变。

### 非目标

- 不把 fallback 成功视为 `memory-compact` proactive acceptance 的通过条件。
- 不通过修改 smoke oracle、降低断言、跳过 compact audit 或允许 malformed compact output 来制造通过。
- 不新增 production-only hook、私有捷径或绕过 Host public path 的 smoke 实现。
- 不依赖真实 LLM / 真实 provider overflow 随机触发 reactive compact。
- 不改变 Host / Engine compact contract、EventLog canonical semantics、durable schema 或 Context Governance 状态机。
- 不把 #80 Conversation Memory benchmark 一次性并入本 WU；本 WU 只是补 public smoke 对 reactive / fallback 主路径的覆盖。

### Entry Conditions

- 重新核对 `docs/host/design.md` 中 Context Governance、reactive compact、fallback tier、Prompt Assembly 与 Conversation Memory 的设计真源。
- 核对 `docs/engine/design.md` 中 Engine 只上报 context compaction request、Host 负责 compact / recovery / fallback 的边界。
- 核对现有 `utils/smoke_host_public_conversation_memory_scenarios.py` 的 suite / pressure mode / compact audit / acceptance 结构。
- 核对 `tests/host/test_public_compact_smoke.py`、`tests/host/test_dispatch_scheduler.py` 与 `tests/host/test_run_input_builder.py` 中 reactive compact、fallback dispatch、fallback input rendering 的既有覆盖，避免重复发明测试机制。

### Acceptance Signals

- 现有 `memory-compact` suite 仍要求 proactive compact request / accepted compact / artifact files，且任何 compact failed 仍为 hard fail。
- 新增 reactive suite 至少断言：
  - `requested_reactive >= 1`。
  - `compacted_reactive >= 1`。
  - `failed_reactive == 0`。
  - recovery Attempt 被创建并最终 terminal succeeded。
  - recovery RunInput 保持 one-system-message contract、current input anchor 与 protected recent floor 语义。
- 新增 fallback suite 至少断言：
  - 观察到 `CONTEXT_COMPACTION_FAILED`。
  - failed payload 包含 `fallback_action=dispatch` 与可诊断的 fallback input window。
  - 不写 accepted `CONTEXT_COMPACTED`。
  - fallback dispatch 最终 terminal succeeded。
  - fallback RunInput 只渲染 selected recent window 与 current input，不生成或伪造五类 Session Semantic Memory。
- smoke stdout 必须打印 compact audit / operation / fallback 关键信号，但不得输出完整 pressure blob、per-delta stream log 或 Host internal refs 到 LLM-facing material。
- 受影响 smoke assembly tests / Host public compact tests / RunInput fallback tests 通过；若发生代码修改，`python -m pyright dayu/ tests/ utils/` 通过且不新增类型错误。

### 与 WU-CM-10 / GitHub Issue #80 的关系

WU-CM-15 是 public smoke coverage hardening，不替代 #80 的完整 Conversation Memory eval benchmark。它可以为 #80 提供稳定 public-path baseline：reactive compact、fallback dispatch、compact audit 与 final outcome 行为可作为后续 eval fixtures 的底层能力，但 #80 仍需单独覆盖 memory snapshot、RunInputBuilder messages、tool behavior、diagnostics、final response facts、事实更新 / 冲突和 provenance 指标。

### Implementation / Review 状态

- accepted plan: `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md`; accepted plan commit `97518e93`.
- initial plan review: `docs/reviews/plan-review-20260620-102108.md` (AgentMiMo); `docs/reviews/plan-review-20260620-102145.md` (AgentDS).
- plan review adjudication: `docs/reviews/wu-cm-15-plan-review-adjudication-20260620.md`.
- plan fix: `docs/reviews/wu-cm-15-plan-fix-codex-20260620.md`.
- focused plan re-review: `docs/reviews/plan-review-20260620-102923.md` (AgentMiMo); `docs/reviews/plan-review-20260620-102930.md` (AgentDS).
- implementation artifact: `docs/reviews/wu-cm-15-implementation-codex-20260620.md`.
- code review: `docs/reviews/code-review-20260620-112127.md` (AgentDS); `docs/reviews/code-review-20260620-112301.md` (AgentMiMo).
- code review adjudication: `docs/reviews/wu-cm-15-code-review-adjudication-20260620.md`.
- fix artifact: `docs/reviews/wu-cm-15-code-review-fix-codex-20260620.md`.
- focused re-review: `docs/reviews/code-review-20260620-115326.md` (AgentMiMo); `docs/reviews/code-review-rereview-ds-20260620.md` (AgentDS).
- focused re-review adjudication: `docs/reviews/wu-cm-15-code-review-rereview-adjudication-20260620.md`.
- accepted implementation slice commit: `572a88df`.
- aggregate deepreview: `docs/reviews/deepreview-wu-cm-15-aggregate-mimo-20260620.md` (AgentMiMo); `docs/reviews/deepreview-wu-cm-15-aggregate-ds-20260620.md` (AgentDS).
- aggregate fix: `docs/reviews/wu-cm-15-aggregate-fix-codex-20260620.md`.
- aggregate fix focused re-review: `docs/reviews/deepreview-wu-cm-15-aggregate-fix-rereview-mimo-20260620.md` (AgentMiMo); `docs/reviews/deepreview-wu-cm-15-aggregate-fix-rereview-ds-20260620.md` (AgentDS).
- aggregate adjudication: `docs/reviews/wu-cm-15-aggregate-deepreview-adjudication-20260620.md`.
- final closeout: `docs/reviews/wu-cm-15-final-closeout-20260620.md`.
- draft PR: https://github.com/noho/dayu-agent-r/pull/157.
- PR review artifacts: `docs/reviews/pr-157-review-20260620-134300.md` (AgentMiMo, PASS, no material findings); `docs/reviews/pr-157-review-20260620-134346.md` (AgentDS, PASS, no material findings).
- accepted PR review / final closeout commit: `5e04a841`.
- follow-up push: branch `phase/wu-cm-15` is pushed to PR #157 through accepted PR review commit `5e04a841` and this final hash-record update.
- Controller validation after fix: `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q` passed (`20 passed`, existing edgar deprecation warnings); `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL` passed; `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL` passed; `python -m pyright dayu/ tests/ utils/` passed (`0 errors`); `git diff --check` clean.
- Controller validation after aggregate fix: `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q` passed (`20 passed`, existing edgar deprecation warnings); `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL` passed; `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL` passed; `python -m pyright dayu/ tests/ utils/` passed (`0 errors`); `git diff --check` clean.
- Fresh full-suite smoke evaluation: `workspace/tmp/cm-smoke-fresh-20260620-125037` contains DEBUG logs for all four suites. `memory-core`, `memory-compact`, `memory-reactive-compact`, and `memory-compact-fallback` all passed after correcting the local rerun harness argument shape for the two `--pressure-mode auto` invocations. The logs are appropriate for diagnosis; high-volume per-delta stream output is assigned to GitHub Issue #148 / WU-CLI-DEBUG-STREAM-01 and is not counted as WU-CM-15 noise.
- Closeout logging / pressure fix validation: `pytest tests/host/test_compaction_operation.py::test_run_compaction_operation_logs_terminal_reject_as_warning tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py::test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` passed (`2 passed`); `pytest tests/host/test_compaction_operation.py` passed (`31 passed`); `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` passed (`20 passed`); `pyright` passed (`0 errors`); `python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level DEBUG > workspace/tmp/cm-smoke-fallback-log-fix-20260620-131005.log 2>&1` passed and emitted no `[ERROR]` lines.
- PR checks: `gh pr checks 157` reported no checks on branch `phase/wu-cm-15`; `statusCheckRollup` is empty. Local validation above is the recorded verification source for this WU.
- README trigger handled: `tests/README.md` updated only to reflect the added `memory-reactive-compact` / `memory-compact-fallback` assembly coverage and oracles.

### Residual risks

- Existing real-provider `memory-compact` smoke keeps strict proactive accepted compact semantics. The latest full four-suite run passed with the configured provider environment; future real-provider runs still require valid model / compactor provider keys as a normal smoke precondition.
- `_patched_compactor_runner` remains a smoke-local monkey patch around `dayu.host.llm_compaction._run_agent_request`; the fix adds fail-fast identity checking and `finally` restore, but future parallel smoke execution would need a different isolation strategy.
- The reactive suite uses a suite-local copied `MemoryProjectionPolicy` to bound selected recent items so that the old seed marker is truly written into r1 history but excluded from recovery dispatch; if the default selected recent turn floor grows beyond the six-round layout, the smoke fails closed instead of silently weakening the oracle.
- Deferred future smoke hardening: decide whether reactive acceptance should also reject nonzero `rejected_proactive`. Current aggregate-fix finding explicitly required requested / compacted / failed proactive zero checks; both focused re-reviews passed. If future config can emit proactive rejection without request/compacted/failed counts, add this as a small smoke hardening follow-up.
- Compaction artifact retention is tracked by GitHub Issue #156 as a child of #78. The relationship is explicit: #78 owns `purge_session`-driven session retention cleanup, and #156 can safely rely on that purge ownership to define artifact retention cleanup without adding a Host background scheduler.

Residual risk reconciliation:

- PR review found no material findings; no fix / re-review gate was required.
- `_patched_compactor_runner` risk is accepted as smoke-local and fail-closed; owner is future smoke maintenance only if parallel suite execution becomes a requirement.
- Provider key dependency is an operator/environment precondition for real-provider smoke, not a WU-CM-15 code residual.
- Per-delta DEBUG log volume is transferred to WU-CLI-DEBUG-STREAM-01 / GitHub Issue #148.
- Compaction artifact retention is transferred to GitHub Issue #156 under #78.
- Next entry point after user merges PR #157: pull latest `main` and start WU-CLI-DEBUG-STREAM-01.

## WU-CLI-DEBUG-STREAM-01 CLI `--debug-stream` Per-Delta Stream Diagnostics

### 状态

`planning`。Owner / destination is GitHub Issue #148: https://github.com/noho/dayu-agent-r/issues/148.

本 WU 是 WU-CM-12 final closeout 后新增的 issue-backed follow-up。Goal-confirmation、plan gate、plan review adjudication、plan fix、plan re-review、accepted plan commit 与 Slice 1 implementation 已完成；当前进入 Slice 1 code review gate。

Current gate artifacts:

- plan: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- plan review: `docs/reviews/plan-review-wu-cli-debug-stream-01-mimo-20260620.md` (AgentMiMo); `docs/reviews/plan-review-wu-cli-debug-stream-01-ds-20260620.md` (AgentDS)
- plan review adjudication: `docs/reviews/plan-review-wu-cli-debug-stream-01-adjudication-20260620.md`
- plan fix: `docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md`
- plan re-review: `docs/reviews/plan-rereview-wu-cli-debug-stream-01-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/plan-rereview-wu-cli-debug-stream-01-ds-20260620.md` (AgentDS PASS)
- accepted plan commit: `61bc9a9d`
- Slice 1 implementation: `docs/reviews/implementation-wu-cli-debug-stream-01-slice1-20260620.md`
- Slice 1 validation: `pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py -q` passed with 88 passed and 3 existing dependency warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 1 code review: `docs/reviews/code-review-wu-cli-debug-stream-01-slice1-mimo-20260620.md` (AgentMiMo APPROVED with deferred nits); `docs/reviews/code-review-wu-cli-debug-stream-01-slice1-ds-20260620.md` (AgentDS findings)
- Slice 1 code review adjudication: `docs/reviews/code-review-wu-cli-debug-stream-01-slice1-adjudication-20260620.md`
- Slice 1 fix: `docs/reviews/fix-wu-cli-debug-stream-01-slice1-20260620.md`
- Slice 1 fix validation: `pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py -q` passed with 90 passed and 3 existing dependency warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 1 re-review: `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice1-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice1-ds-20260620.md` (AgentDS PASS)
- accepted Slice 1 commit: `f53762a5`
- Slice 2 implementation: `docs/reviews/implementation-wu-cli-debug-stream-01-slice2-20260620.md`
- Slice 2 validation: `pytest tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py -q` passed with 13 passed; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 2 code review: `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-mimo-20260620.md` (AgentMiMo findings); `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-ds-20260620.md` (AgentDS PASS with info findings)
- Slice 2 code review adjudication: `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-adjudication-20260620.md`
- Slice 2 fix: `docs/reviews/fix-wu-cli-debug-stream-01-slice2-20260620.md`
- Slice 2 fix validation: `pytest tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py -q` passed with 13 passed; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean; diff scan confirms no newly added `type: ignore`, `Any`, or `object` in changed Slice 2 code/test lines.
- Slice 2 re-review: `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice2-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice2-ds-20260620.md` (AgentDS PASS)
- Slice 2 re-review adjudication: `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice2-adjudication-20260620.md`
- accepted Slice 2 commit: `67ca96fb`
- Slice 3 implementation: `docs/reviews/implementation-wu-cli-debug-stream-01-slice3-20260620.md`
- Slice 3 validation: `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q` passed with 56 passed and 3 existing dependency warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 3 code review: `docs/reviews/code-review-wu-cli-debug-stream-01-slice3-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/code-review-wu-cli-debug-stream-01-slice3-ds-20260620.md` (AgentDS PASS)
- Slice 3 code review adjudication: `docs/reviews/code-review-wu-cli-debug-stream-01-slice3-adjudication-20260620.md`
- accepted Slice 3 commit: `928281bd`
- Slice 4 implementation: `docs/reviews/implementation-wu-cli-debug-stream-01-slice4-20260620.md`
- Slice 4 validation: `git diff --check` clean; `git diff --check README.md tests/README.md` clean; `python -m pyright dayu/ tests/ utils/` passed with 0 errors.
- Slice 4 code review: `docs/reviews/code-review-wu-cli-debug-stream-01-slice4-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/code-review-wu-cli-debug-stream-01-slice4-ds-20260620.md` (AgentDS PASS)
- Slice 4 code review adjudication: `docs/reviews/code-review-wu-cli-debug-stream-01-slice4-adjudication-20260620.md`
- accepted Slice 4 commit: `f084a340`
- aggregate deepreview: `docs/reviews/aggregate-deepreview-wu-cli-debug-stream-01-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/aggregate-deepreview-wu-cli-debug-stream-01-ds-20260620.md` (AgentDS PASS)
- final closeout: `docs/reviews/wu-cli-debug-stream-01-final-closeout-20260620.md`
- final validation: `pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q` passed with 160 passed and 3 existing dependency warnings after the user follow-up fix; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- draft PR: #158 https://github.com/noho/dayu-agent-r/pull/158
- user follow-up: future-site reminder residual removed as unnecessary; `--log-level critical` parser mismatch fixed by accepting `critical` in CLI parser choices and covering it in `tests/cli/test_arg_parsing.py`.
- PR review: `docs/reviews/pr-review-wu-cli-debug-stream-01-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/pr-review-wu-cli-debug-stream-01-ds-20260620.md` (AgentDS PASS)
- PR review adjudication: `docs/reviews/pr-review-wu-cli-debug-stream-01-adjudication-20260620.md`
- accepted PR review commit: `c563d4d6`
- follow-up push after accepted PR review commit: complete
- PR body issue association: `Closes #148`; merge of PR #158 is expected to auto-close issue #148
- issue closeout comment: https://github.com/noho/dayu-agent-r/issues/148#issuecomment-4757794264
- final closeout pass: recorded; next entry point after merge is to pull `github/main` and start WU-OBS-00 goal confirmation unless user selects a different active/backlog work unit
- plan gate validation: `git diff --check` clean; untracked plan artifact whitespace check clean via `git diff --no-index --check /dev/null docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md` with expected nonzero no-index exit and no whitespace output.
- plan fix validation: `git diff --check` clean; untracked fix artifact whitespace check clean via `git diff --no-index --check /dev/null docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md` with expected nonzero no-index exit and no whitespace output.

### Issue Scope

Issue #148 要求把普通 `--debug` 与高噪音 stream delta diagnostics 分离：

- `--debug` 保持常规诊断级别，不输出大量 per `reasoning_delta` / `content_delta` ingest 日志。
- 新增显式 `--debug-stream`，仅在该开关启用时输出 stream delta / SSE / per-delta accepted / committed diagnostics。
- `--debug-stream` 可与 `--debug` 组合；具体日志级别和 handler owner 必须在 plan gate 核对当前 CLI / runtime log 装配后确定。
- `--help`、README 或对应 CLI 用户可见说明需要解释 `--debug` 与 `--debug-stream` 的差异。
- 需要覆盖 CLI parsing / logging switch tests，验证 `--debug` 不再开启海量 per-delta ingest 日志，`--debug-stream` 可开启这些诊断。

Issue comment 还要求核对 best-effort after-commit `host.memory_repair.catch_up.budget_exhausted` 的普通 `--debug` warning 噪音。Plan gate 已按当前代码证据和用户裁决确认：这是已修复 bug，不是本 WU 的噪音优化项；当前代码已无 `budget_exhausted` stop reason，required catch-up / rebuild / projection failures 仍应 warning，本 WU 只保留 no-regression verification。

### Non-goals

- 不改变 Host / Engine EventLog canonical fact contract。
- 不改变 activity stream 用户可见行为。
- 不把 final answer、业务正文或大块 LLM content 复制进 debug 日志，除非当前日志 contract 已允许且 `--debug-stream` 明确限定。
- 不借本 WU 重构整个 CLI logging subsystem；仅处理 Issue #148 直接支撑的开关、日志分类和测试。

### Entry Conditions

- 先核对 Issue #148 当前状态和评论。
- 核对 CLI parser、runtime logging、Engine / Host stream delta ingest logging sites、memory repair logging sites、现有 CLI tests 和 README 更新触发范围。
- 若发现需要新的 public CLI contract 或 README 用户说明，先在 plan 中明确。

### Acceptance Signals

- `--debug` 不再输出 massive per-delta reasoning/content ingest logs。
- `--debug-stream` 明确启用 stream delta / SSE / per-delta accepted / committed diagnostics。
- `--debug-stream` 可与 `--debug` 组合且行为可测试。
- CLI help / relevant README 更新完成并符合各 README 的更新约束。
- CLI parsing / logging switch tests 覆盖上述行为；pyright 通过；必要的 affected tests 通过。

## 2026-07-22 Completed / Final Closeout 归档批次

本批次以迁移前主总控“当前 Work Units”表的状态列为唯一判定源。共归档 14 个唯一 WU、16 个详细历史 section；重复 section 来自同一 WU 在不同时期保留的入口与最终实施记录，原文一并保存。

### 已完成推进顺序（历史）

本节记录用户在 2026-06-21 裁决的工具调用治理推进顺序。该顺序只约束当前 Host tool-call governance follow-up lane；如果后续 discussion 发现设计真源、GitHub Issue scope 或代码直接证据与本节冲突，必须先更新设计真源、本文档和对应 GitHub Issue，再调整顺序。

1. 先清理已完成 WU 与 GitHub 状态不一致：PR 160 已 merge 且 #133 已关闭，PR 159 已 merge 且 #63 已关闭，PR 135 已 merge 后 #130 已关闭。上述条目不得再作为 active implementation entry point。
2. 以执行正确性为默认下一步，优先推进 WU-TOOLS-AWAIT-FANOUT-01 / #111。目标是在现有 attempt-scoped duplicate governance 与 awaiting accept barrier 之上，先设计重复 awaiting owner / waiter 的单 wait owner 与 fanout follower 语义，再进入 implementation gate。
3. #111 形成稳定设计和验收边界后，再推进 #129 的 awaiting external job two-phase activation。#129 需要修 submit-before-accept 窗口，不能用 Fins-only workaround 绕过 Host awaiting activation contract；如果 #111 改变 wait record alias / follower 表达，#129 plan 必须消费该结论。
4. #129 之后推进 production WAIT hardening：#89 callback endpoint / auth / replay、#90 production poller loop / backoff / fencing / retry、#92 external job physical cancel / revoke / abandon。#92 继续归属 #87 lifecycle watchdog / supervisor umbrella，不另建第二套 watchdog runtime。
5. #89 / #90 / #92 完成后，先推进 WU-LIFE-03 / GitHub Issue #91，固定 active cancel watchdog、post-cancel timeout、Run / Attempt closeout、late terminal race 和 diagnostic 语义。WU-LIFE-03 必须只定义 Host-level cancel governance 和 timeout closeout：cancel command 接受后 Host truth 不等待 worker / provider 配合，超时后有明确终态或 diagnostic，迟到 terminal first-committer-wins / rejection 可验证；不得把 provider-specific kill API 硬编码进 Host 核心。
6. WU-LIFE-03 完成后，先推进 WU-LIFE-04 / GitHub Issue #168，固定 tool execution deadline 与 Host watchdog closeout 的边界：`tool_execution_timeout_seconds` 是单次工具调用最长运行时间，取消 / 收口不得覆盖或延长原始 tool deadline；裁决独立 `active_cancel_timeout_seconds` 的移除、降级或 derived deadline 处理，并为 #87 umbrella 的 scan query optimization、clock skew、diagnostics / audit hooks 和 shared supervisor 验收指定 owner / destination。
7. WU-LIFE-04 完成后，再推进 WU-TOOLS-CANCEL-01，补齐 tool/provider runtime 的实际 interrupt boundary 与 escalation 能力：cooperative token、request / stream abort、subprocess / process-group / sandbox termination、hard-kill diagnostic closeout。目标是获得 Codex / Claude Code 类似的用户体感：取消后 Host 迅速回到可交互状态，旧 tool/provider 结果不得污染已取消 Run，且不得延长 WU-LIFE-04 固定的单次工具执行 deadline。若 tool/provider 在 Host 不可抢占的同进程 blocking I/O 中执行，本 WU 必须迁移到可中断 execution capsule 或明确禁止该执行形态进入 production-grade cancel path。
8. WU-LIFE-03、WU-LIFE-04 与 WU-TOOLS-CANCEL-01 完成后，WU-WAIT-04 才能进入 implementation gate，用 UI / Service production-grade awaiting E2E smoke 验证 public watcher、WAITING 展示、production wait resolution、terminal event、outbox 补读，以及取消后的可交互恢复体验。不得用 manual resolve、测试私有 durable wait id 或只靠 cooperative tool 配合伪造 production-grade 验收。
9. #70 / #34 / #119 / #71 作为 Tool Trace diagnostics lane 可以并行做 discussion / design，但不得替代 #111 / #129 / #89-#92 / #91 / #168 / WU-TOOLS-CANCEL-01 的 ToolRuntime、wait lifecycle 与 cancel root-cause 修复。诊断 lane 的输出可以反向补充验收信号，例如重复调用、awaiting fanout、late result、oversized payload、limited-signal report 和 post-cancel stale output。

## WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation

### 状态

当前 authoritative 状态为 `completed`：PR #172 已于 2026-07-09 merge，merge commit 为 `3410d742`。下方长段落保留为当时的 gate / final-closeout 历史证据，其中 `final-closeout-pass`、draft PR 等措辞不再表示当前状态。

`final-closeout-pass`。本 WU 是 2026-07-06 用户裁决要求加入的 immediate residual WU，当前没有独立 GitHub Issue owner；用户已确认无需新建 GitHub Issue。Draft PR #172 已创建：https://github.com/noho/dayu-agent-r/pull/172；PR body 不包含 `Closes` footer。Goal confirmation artifact 为 `docs/reviews/wu-cli-smoke-01-goal-confirmation.md`，其中包含自动 / 手工验证矩阵。Plan artifact 为 `docs/host/wu-cli-smoke-01-dayu-cli-core-usability-plan.md`；auto-validation artifact 为 `docs/reviews/wu-cli-smoke-01-auto-validation-codex.md`；raw evidence directory 为 `workspace/tmp/wu-cli-smoke-01-auto/`。Plan review artifacts 为 `docs/reviews/plan-review-20260706-163952.md` 与 `docs/reviews/plan-review-20260706-164108.md`；controller adjudication 为 `docs/reviews/wu-cli-smoke-01-plan-review-controller-adjudication.md`；plan fix artifact 为 `docs/reviews/wu-cli-smoke-01-plan-fix-codex.md`；plan re-review artifacts 为 `docs/reviews/plan-review-20260706-164905.md` 与 `docs/reviews/plan-review-20260706-164908.md`；plan re-review controller adjudication 为 `docs/reviews/wu-cli-smoke-01-plan-rereview-controller-adjudication.md`；accepted plan commit 为 `c0b79339`。AgentCodex 自动复现 `dayu-cli interactive` 在 idle `dayu>` prompt 下单次 Ctrl+C 直接退出的行为失败。Slice S1 implementation artifact 为 `docs/reviews/wu-cli-smoke-01-slice-s1-implementation-codex.md`；code review artifacts 为 `docs/reviews/code-review-20260706-170636.md` 与 `docs/reviews/code-review-20260706-170940.md`；controller adjudication 为 `docs/reviews/wu-cli-smoke-01-slice-s1-code-review-controller-adjudication.md`；accepted Slice S1 commit 为 `52e4fcd3`。Aggregate deepreview artifacts 为 `docs/reviews/code-review-20260706-171635.md` 与 `docs/reviews/code-review-20260706-171806.md`；controller adjudication 为 `docs/reviews/wu-cli-smoke-01-aggregate-deepreview-controller-adjudication.md`。Manual validation evidence artifact 为 `docs/reviews/wu-cli-smoke-01-manual-validation-evidence.md`：MANUAL-01 和 MANUAL-02 已部分通过，但 MANUAL-F01 blocked final closeout。MANUAL-F01 root-cause fix artifact 为 `docs/reviews/wu-cli-smoke-01-manual-validation-fix-codex.md`，记录 Host awaiting snapshot digest 修复、Python durable row codec invariant hardening、focused Host tests `94 passed`、真实 `dayu-cli prompt "下载Visa财报"` awaiting validation、pyright 和 `git diff --check` 通过；implementation review artifacts `docs/reviews/wu-cli-smoke-01-manual-fix-implementation-review-mimo.md` 与 `docs/reviews/wu-cli-smoke-01-manual-fix-implementation-review-ds.md` 均为 pass，controller adjudication `docs/reviews/wu-cli-smoke-01-manual-fix-controller-adjudication.md` accepted MANUAL-F01，accepted MANUAL-F01 fix commit 为 `164072b0`。Display semantics follow-up implementation / fix artifact 为 `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`；review artifacts 为 `docs/reviews/wu-cli-smoke-01-display-semantics-review-mimo.md` 与 `docs/reviews/wu-cli-smoke-01-display-semantics-review-ds.md`；re-review artifacts 为 `docs/reviews/wu-cli-smoke-01-display-semantics-rereview-mimo.md`、`docs/reviews/wu-cli-smoke-01-display-semantics-rereview-ds.md`、`docs/reviews/wu-cli-smoke-01-display-semantics-final-rereview-mimo.md`、`docs/reviews/wu-cli-smoke-01-display-semantics-final-rereview-ds.md`、`docs/reviews/wu-cli-smoke-01-display-semantics-prompt-lifecycle-rereview-mimo.md` 和 `docs/reviews/wu-cli-smoke-01-display-semantics-prompt-lifecycle-rereview-ds.md`，最终均为 pass；accepted display semantics commit 为 `c1b546ac`。PR review artifacts 为 `docs/reviews/pr-172-review-20260706-210832.md` 与 `docs/reviews/pr-172-review-ds.md`；PR review fix artifact 为 `docs/reviews/pr-172-review-fix-codex.md`；PR re-review artifacts 为 `docs/reviews/pr-172-rereview-mimo.md` 与 `docs/reviews/pr-172-rereview-ds.md`，均为 pass；accepted PR review commit 为 `632c1f34`，并已 push。Final closeout artifact 为 `docs/reviews/wu-cli-smoke-01-final-closeout.md`。该 WU 必须作为 WU-WAIT-04 之后的独立 PR 推进，不得混入 PR #171；用户 merge PR #172 后，应从 `main` 拉取最新代码，再按本文档 next entry point 选择下一 active backlog work unit。

### 代码与 Issue 核对

- 代码核对显示 `dayu-cli prompt` 与 `dayu-cli interactive` 都通过 `prepare_entrypoint_runtime(...)` 执行 runtime location、ConfigLoader、ToolsDiscovery、ScenePrepare 与 Service Host assembly，再通过 `open_host(...)` 和 Host public session / submit / wait API 执行；CLI 不直接构造 Engine request。
- 代码核对显示 `prepare_entrypoint_runtime(...)` 会用当前 `workspace_root` 装配 effective Fins provider config；包内默认 Fins provider 不应让财报仓储落到 `workspace/workspace/portfolio`。
- 代码核对显示 Host / Engine 设计真源支持当前 CLI 主路径判断：Host 是 Session / Run / Attempt / tool governance 真源；Engine 不拥有配置、持久化、等待恢复或外部长事务 lifecycle。
- GitHub open issue 核对显示 #70 / #34 / #119 / #71 仍追踪 Tool Trace / diagnostics lane，#72 / #75 仍追踪 audit lane，#43 / #36 / #78 / #156 / #96 仍追踪 retention lane，#80 / #115 及相关 memory issues 仍追踪 memory 强化；这些不阻塞本 WU 判断 dayu-cli 主路径基本可用。
- GitHub open issue #151 明确 `write` 命令尚未迁移。因此本 WU 不得宣称 dayu-cli 全部功能完成；结论只能是 dayu-cli core 投研问答 / Fins direct / interactive 主路径基本可用。
- GitHub open issues #84 / #85 / #147 分别追踪 Web、GUI、WeChat entrypoint；用户已裁决 Web UI 和 GUI 先不管，本 WU 也不处理 WeChat，除非后续 goal confirmation 明确扩 scope。

### 目标

- 固化 dayu-cli core usability 的最小 smoke / behavior validation matrix，覆盖 `init`、help surface、`prompt`、`interactive`、session label / resume、Fins direct upload-download-process/session 主路径，以及工具治理相关用户可见行为。
- 真实环境验证是本 WU 的硬约束。自动化 fake / mock 测试只能补充回归覆盖，不能替代真实 `dayu-cli` 命令的 UI 输出与 debug log 证据。具体自动验证命令由 AgentCodex 执行并产出 artifact，总控只裁决证据。
- 将 public-contract smoke 纳入 WU 验收：Host public awaiting entrypoint smoke 必须继续只使用 public contracts，不读取或修改 durable 私有表来伪造通过。
- 验证 default workspace path 不再产生 `workspace/workspace/.dayu` 或 `workspace/workspace/portfolio`；Host durable、runtime lane、compaction artifact 与 Fins portfolio 默认都应落在当前 CLI workspace root 下。
- 验证 dayu-cli 行为与用户文档一致：stdout / stderr / log-file 分离、错误提示可读、fresh workspace 可启动、interactive 可进入输入循环、工具调用 / awaiting / duplicate governance 的基本体感可观察。
- 在独立 PR 中补齐必要 smoke 脚本、CLI 行为测试或 README / tests README 同步。

### 非目标

- 不实现 `dayu-cli write`；该命令继续由 GitHub Issue #151 追踪。
- 不实现 Web UI、GUI 或 WeChat entrypoint；#84 / #85 / #147 保持独立 owner。
- 不实现 Tool Trace analyzer、prompt-based trace diagnostics、Audit viewer / external audit delivery、retention cleanup、长期存储治理或 memory benchmark / memory 强化；对应 issue lane 继续独立推进。
- 不扩大 Host / Engine public contract，不修改 durable schema，不引入 GUI / Web 测试框架，不用测试私有 Host / durable 入口伪造 CLI 行为验证。

### 验收信号

- `dayu-cli --help`、`dayu-cli interactive --help`、`dayu-cli prompt --help`、Fins direct 命令 help surface 与 README 当前说明一致。
- Fresh workspace 下 `dayu-cli interactive` 不再因旧 schema path 或 nested workspace path 失败；默认生成路径不得包含 `workspace/workspace/.dayu` 或 `workspace/workspace/portfolio`。
- Public awaiting smoke 通过，例如 `python utils/smoke_host_public_awaiting_entrypoint.py`，并继续只通过 `open_host -> ensure_session -> submit_entrypoint_turn_and_wait` 等 public contracts 验收 production poller path。
- dayu-cli 行为验证覆盖至少一条 prompt / interactive Host public path，能观察工具治理基本行为；如依赖真实模型或外部网络，应明确标记为 manual smoke，并提供可重复的命令、预期输出与失败诊断。
- 受影响 pytest、pyright 和 `git diff --check` 通过；README / `tests/README.md` 按 AGENTS 触发规则同步。

### Slice S1 Implementation Evidence

- AgentCodex 按 accepted plan 修复 `dayu-cli interactive` 输入态 Ctrl+C 语义：空 `dayu>` 下第一次 Ctrl+C 重绘 prompt，连续第二次 Ctrl+C 退出；中间提交正常输入会重置本地退出待确认状态。该实现只修改 CLI-local `_run_interactive_repl(...)` 状态，不修改 `InteractiveComposer` 协议、Service、Host、Engine、durable schema、EventLog 或 Fins storage。
- 改动文件为 `dayu/cli/commands/interactive.py`、`tests/cli/test_interactive_command.py`、`README.md`、`tests/README.md` 和 implementation artifact `docs/reviews/wu-cli-smoke-01-slice-s1-implementation-codex.md`。
- AgentCodex reported validation: focused interactive tests `36 passed, 3 warnings`; real PTY probe `prompt_seen=True`, `exited_after_first_ctrl_c=False`, `exited_after_second_ctrl_c=True`, `decision=pass`; broader CLI / Service tests `236 passed, 3 warnings`; public awaiting smoke pass; `git diff --check` pass; pyright `0 errors, 0 warnings, 0 informations`。
- Controller reran validation for gate evidence with the same pass results: focused interactive tests `36 passed`; PTY Ctrl+C probe pass; broader CLI / Service tests `236 passed`; public awaiting smoke pass with marker `SMOKE PASS Host public awaiting entrypoint`; `git diff --check` pass; pyright `0 errors`。
- Remaining manual evidence before final closeout: real provider `dayu-cli prompt`, real provider `dayu-cli interactive` running-state Ctrl+C during an accepted live run, and optional real Fins download / process if user chooses to include external-network validation in this WU.

### Display Semantics Follow-up Evidence

- AgentCodex 修复 `prompt` / `interactive` display semantics：`--thinking` / `--no-thinking` 仅控制 CLI 运行态 thinking 展示，不进入 model / runner / provider execution config；`prompt` 与 `interactive` 默认 `--thinking --detail`；`interactive` 补齐 `--detail` / `--no-detail`。
- Host 将 `EngineEventType.REASONING_DELTA` 投影为独立 `HostThinkingView`，Service 通过 `EntrypointThinking` / `on_thinking` 回调转交 CLI renderer；thinking 只作为运行态 stderr 展示，不进入 final answer、activity、interactive final transcript、outbox terminal projection 或 canonical replay。
- Accepted review findings 已修复：`--thinking` dead param、README/help 与实现不符、thinking on/off 缺测试、`REASONING_DELTA` 双重分类、interactive `--no-detail` 冗余 run view、interactive / prompt cancel path thinking renderer lifecycle，以及 prompt cancel caller wiring integration coverage。
- AgentCodex reported validation：`tests/cli` `225 passed, 3 warnings`，Host / Service focused suite `126 passed, 3 warnings`，prompt / interactive / thinking renderer focused suite `66 passed, 3 warnings`，pyright `0 errors, 0 warnings, 0 informations`，`git diff --check` pass。
- Controller reran final validation：`source .venv/bin/activate && pytest tests/cli -q` -> `225 passed, 3 warnings`；`source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/host/test_engine_ingest_mapping.py tests/host/test_host_activity_event_projection.py -q` -> `126 passed, 3 warnings`；`source .venv/bin/activate && pyright` -> `0 errors, 0 warnings, 0 informations`；`git diff --check` pass。
- Display semantics follow-up 已按 owner 收敛：R1 以 Host-owned transient live contract 取代 EventLog watcher 对 per-chunk delta 的持久化；原先分拆的 Host / Service capacity 条目已由统一 `WU-HOST-SESSION-EVENT-DELIVERY-01` 取代，Service relay删除、Host mailbox容量与全部measurement在同一WU闭环。CLI当前是“每个delta单行化并按160字符截断后累计追加”，其可展开面板、历史与累计上限仍由 `WU-CLI-SMOKE-01-R2` 在明确UX要求后进入goal confirmation。

## WU-CLI-SMOKE-01-R1 Engine Delta Transient Live Stream Remediation

### 状态

用户在 2026-07-20 将本项选定为 PR #179 merge 后的下一 WU，并裁决为高严重度 EventLog amplification bug。用户随后明确裁决完整目标不是 reasoning 专用旁路，而是 `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA` 三类 per-chunk delta 共用 Host-owned transient live contract，全部不写 EventLog；后续不得重新收窄为只处理 thinking。PR #179 已于 2026-07-20 merge，本地 `main` 已同步到 merge commit `bd1d3e94`，当前工作分支为 `phaseflow/wu-cli-smoke-01-r1`。Goal confirmation、plan review/fix/re-review、两个 implementation slices、Slice 1 accepted finding fix/re-review、全 WU aggregate deepreview、Draft PR、PR review/fix/re-review、accepted PR review commit、最终远端 Windows checks 与 final closeout 均已完成。Accepted commits 为 plan `929691ea`、Slice 1 `70ccda60`、Slice 2 `d58014cf`、aggregate deepreview `2d38abad` 与 PR review `3900b069`。Aggregate 与 PR review 两路均 PASS；唯一 PR metadata finding `PR180-F01` 已修复并由双路 re-review 关闭。Final closeout artifact 为 `docs/reviews/wu-cli-smoke-01-r1-final-closeout.md`。

Post-closeout 代码裁决最初把 Host 与 Service 固定容量拆成两个 evidence-gated WU；用户随后从第一性原理指出：慢 UI 无权暂停 Agent，Service 不应拥有第二个 event-copy relay，mailbox / capacity / overflow / iterator lifecycle 应由 Host Session Event Delivery 统一拥有。`docs/host/design.md` 已据此完成多轮 design review/fix/re-review，并进一步关闭单 opener terminal notice 无法覆盖跨进程 watcher、同步 factory pending cursor 无真实线性化点等高严重度反例。Controller 最终裁决 artifact 为 `docs/reviews/wu-transient-delivery-ownership-design-controller-adjudication.md`；最终 AgentCodex / AgentMiMo / AgentDS 三路 re-review 均 PASS，0 material finding、0 design residual、0 未归属 residual、0 open question。旧 `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 已被统一的 `WU-HOST-SESSION-EVENT-DELIVERY-01` 取代并从 active residual 表删除；所有可实施项和测量项均进入新 WU acceptance。Draft PR #180 保持 open / draft，等待用户或 maintainer 手工处理；该 WU 无独立 Issue owner，PR body 未添加 closing directive。未经明确授权不得 mark ready、merge、request reviewers、close issue、发布外部 closeout comment或 delete branch。

### 直接证据与动机

- `f17ffcc8` / WU-CLI-ACTIVITY-01 follow-up 已明确三类 per-delta EngineEvent（`CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA`）只服务即时展示，默认 accepted 但不写 EventLog；其直接动机是避免 token/chunk 级 durable rows 放大 EventLog、拖慢 projection catch-up，并错误暗示 token-level durable replay。
- 当前代码中 `CONTENT_DELTA`、`TOOL_CALL_DELTA` 已经 accepted-without-row，但 Host 没有把它们投影到公共 transient live delivery；`REASONING_DELTA` 是三类 delta 中唯一仍写 EventLog 的特例。
- `c1b546ac` 为实现 `--thinking` 展示，把 `REASONING_DELTA` 从 transient 分支移出并改为每个 delta 追加一条 `PREVIEW` EventLog row。当前 `watch_session_events` 又通过 EventLog cursor 轮询读取，因此持久化只是复用现有 watcher 的局部最小实现，不是实时 thinking 的业务要求，也不能成为为 reasoning 单独保留第二套 delivery contract 的理由。
- 一次模型 Attempt 可以产生大量 reasoning chunks；当前是一条 delta 对应一条 SQLite EventLog row，并同时带来 event id、sequence、payload、索引和后续扫描成本。该放大随 token/chunk 数增长，不应等待 retention/purge 再清理。
- `docs/host/design.md` 已承认未来多客户端 live token 展示需要另行设计 transient fanout，不能把主 EventLog durable replay 改成 token-level 保真。

### 已裁决目标（下轮 goal confirmation 负责代码/设计复核）

- `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA` 统一由一个 Host-owned transient delta contract 接受、校验并 live fanout；三者任意数量的 delta 均不追加 `PREVIEW`、canonical、diagnostic 或其它替代 EventLog row。
- 删除 `REASONING_DELTA` 当前 durable `PREVIEW` 特例并恢复 accepted non-durable ingest；保留 content/tool-call 现有 non-durable 语义，但把三者一并接入公共 transient live delivery，不得把 accepted-without-row 等同于已经完成 live stream。
- 已 attach 的 Service / UI / CLI 可以按需消费三类 delta，例如 CLI thinking renderer 只选择 reasoning；不得让 Service 绕过 Host 直接消费 raw EngineEvent，也不得建立 reasoning 专用持久化或专用旁路。
- 明确 transient event 的运行态 identity、ordering、multi-watcher fanout、slow-consumer、detach 与 Host close 语义；不得伪造 durable `event_sequence`，不得把 transient cursor 解释为离线 replay cursor。
- 保持 final answer、durable activity、outbox terminal、Conversation Memory、audit、Tool Trace 与 durable recovery 不消费 raw delta；断线或重启后不补放任何 token/chunk-level delta。

### CLI 功能保持与切换约束

- R1 不是“删掉 `REASONING_DELTA` EventLog append”这一项孤立改动；如果 CLI 仍只通过 durable `watch_session_events` 读取 thinking，直接删 row 会让实时 `--thinking` 消失，属于未完成且不可接受的实现。
- 实现必须先具备 Host-owned transient delta delivery，并让 Service / CLI 在 Host 公共边界上消费它，再移除 reasoning durable `PREVIEW` 特例。plan 可以按依赖边界切 slice，但任何 accepted slice commit、PR head 或最终组合状态都不得存在“reasoning 已不落库、attached CLI 却收不到 live thinking”的窗口。
- `dayu-cli prompt` 与 `dayu-cli interactive` 在 attached 运行期间继续实时展示 reasoning；`--no-thinking` 继续抑制 thinking；final answer、activity/detail、stdout/stderr 分工、Ctrl+C 取消、renderer close 和普通 durable event 补读均不得回归。
- content/tool-call delta 接入统一 transient contract 只增加 Host-owned live delivery 能力；CLI/UI 未选择的 delta 不得被强制渲染，不得造成 final answer、tool activity 或 thinking 的重复输出。
- 唯一有意的用户可观察变化是：断线重连、CLI 进程重启或 Host 重启后不补放此前的 content/reasoning/tool-call per-chunk delta。这是 live-only contract，不是 CLI 功能丢失；terminal final answer 与其它 durable facts 仍按既有 EventLog 路径恢复和补读。

### 非目标

- 不实现任何 delta 的 durable replay、历史 token/thinking 查询、断线补放或跨 Host restart 恢复。
- 不把 R1 下放给 retention / purge，也不通过缩短 retention、批量删除或 EventLog 压缩掩盖写入放大。
- 不顺带实现 `WU-CLI-SMOKE-01-R2` 可展开 thinking panel，不修改模型是否启用 reasoning 的 provider / runner 配置。
- 不删除整个 `PREVIEW` event class；iteration、content-completed、tool-batch 等非 per-chunk 粗粒度 preview 是否 durable 继续遵循各自既有 owner contract。
- 不重写普通 canonical HostEvent、outbox terminal delivery、durable activity projection、Tool Trace、audit 或 Conversation Memory。

### 验收信号

- 构造单个 Attempt 分别产生大量 `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA`，断言 durable EventLog 中三类 delta row 均为 `0`，且 final answer / terminal canonical facts 正常提交。
- 已 attach 的一个或多个 live watcher 能按同一 Host-defined transient contract 接收三类 delta，消费者可按 type 选择；CLI `prompt` / `interactive` 的 `--thinking` 实时展示、`--no-thinking` 抑制、final answer、activity/detail、stdout/stderr、取消和 renderer close 行为保持正确，且不产生重复输出。
- 慢 watcher、提前 detach、Host close 与 worker terminal 不反压 EventLog append、不泄漏 task、不取消 Run、不产生伪 terminal fact。
- 断线重连、Host restart 与离线 reader 不重放三类 delta；transient identity/order 不混入 durable `HostEvent.event_sequence` cursor，既有粗粒度 preview/canonical 补读不回归。
- 受影响 Host / Service / CLI tests、单文件 coverage、pyright、`git diff --check`、README 触发检查与 EventLog source/propagation scans 通过。

## WU-HOST-SESSION-EVENT-DELIVERY-01 Host Session Event Delivery Ownership and Bounded Mailbox

### 最终状态

`final-closeout-pass`。Final closeout artifact为`docs/reviews/wu-host-session-event-delivery-01-final-closeout.md`。Accepted PR review commit=`3439a1a1`已push，`windows-init-transaction`与`windows-upload-script`均PASS；Draft PR #181保持OPEN/DRAFT。当前无active implementation、blocking open question、unclassified residual risk或自动下一Work Unit；未经授权不得mark ready、merge或删除分支。

### 历史推进记录（以下状态以当时 gate 为准）

当前有效 gate=`draft-PR-pass`。Slice 3 implementation与首次code review/fix artifacts沿用前述记录；AgentMiMo与AgentDS re-review artifacts为 `docs/reviews/wu-host-session-event-delivery-01-slice3-code-rereview-mimo.md`、`docs/reviews/wu-host-session-event-delivery-01-slice3-code-rereview-ds.md`，两路确认 `S3-CR-F01/F02` closed。Controller re-review adjudication为 `docs/reviews/wu-host-session-event-delivery-01-slice3-code-rereview-controller-adjudication.md`，accepted `S3-RR-F01`；AgentCodex narrow fix artifact为 `docs/reviews/wu-host-session-event-delivery-01-slice3-rereview-fix-codex.md`。原reviewers narrow re-review artifacts为 `docs/reviews/wu-host-session-event-delivery-01-slice3-narrow-rereview-mimo.md`、`docs/reviews/wu-host-session-event-delivery-01-slice3-narrow-rereview-ds.md`；Controller adjudication为 `docs/reviews/wu-host-session-event-delivery-01-slice3-narrow-rereview-controller-adjudication.md`。两路确认`S3-RR-F01` closed、0 new material finding；accepted Slice 3 commit=`24efe9bd`。Slice 4 implementation artifact=`docs/reviews/wu-host-session-event-delivery-01-slice4-implementation-codex.md`；AgentMiMo与AgentDS code review artifacts为`docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-mimo.md`、`docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-ds.md`；Controller adjudication=`docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-controller-adjudication.md`，接受coverage、prompt cancel race与consumer projection failure三项，拒绝新增startup log与bounded durable recovery两项。AgentCodex fix artifact=`docs/reviews/wu-host-session-event-delivery-01-slice4-fix-codex.md`；focused `3 passed`、S4 matrix `196 passed`、隔离`dayu/cli/session_execution.py` coverage=`80.56%`、完整pyright=`0 errors`，且未实施两项rejected findings。原reviewers re-review artifacts为`docs/reviews/wu-host-session-event-delivery-01-slice4-code-rereview-mimo.md`、`docs/reviews/wu-host-session-event-delivery-01-slice4-code-rereview-ds.md`；Controller adjudication为`docs/reviews/wu-host-session-event-delivery-01-slice4-code-rereview-controller-adjudication.md`。两路确认`S4-CR-F01/F02/F05`closed、`S4-CR-F03/F04`拒绝边界保持、0 new material finding；accepted Slice 4 commit=`035d0035`。Full-WU aggregate deepreview artifacts为`docs/reviews/wu-host-session-event-delivery-01-aggregate-deepreview-mimo.md`、`docs/reviews/code-review-20260722-034010.md`与`docs/reviews/wu-host-session-event-delivery-01-aggregate-deepreview-ds.md`；Controller adjudication为`docs/reviews/wu-host-session-event-delivery-01-aggregate-deepreview-controller-adjudication.md`。两路均PASS、0 material finding，完整affected suites=`3443 passed, 9 skipped, 6 deselected`、stress=`6 passed`、核心coverage=`84%`–`95%`、完整pyright=`0 errors`；accepted deepreview commit=`0a72396d`。分支已push，Draft PR #181=`https://github.com/noho/dayu-agent-r/pull/181`，PR body不含Issue closing directive。PR review artifacts为`docs/reviews/wu-host-session-event-delivery-01-pr-181-review-mimo.md`与`docs/reviews/wu-host-session-event-delivery-01-pr-181-review-ds.md`；Controller adjudication为`docs/reviews/wu-host-session-event-delivery-01-pr-181-review-controller-adjudication.md`。两路均PASS、0 material finding；accepted PR review commit=`3439a1a1`且已push。Windows checks尚未最终PASS，因此尚未宣告draft-PR-pass或final closeout。

`active-implementation-slice-3`。PR #180 已 merge；本地 `main` 已 fast-forward 到 merge commit `2c02079a82c049b49914be412178006ccd354049`，独立分支为 `phaseflow/wu-host-session-event-delivery-01`。用户已确认 goal confirmation；当前无独立 GitHub Issue，owner / destination 为用户明确裁决。goal confirmation artifact 为 `docs/reviews/wu-host-session-event-delivery-01-goal-confirmation.md`；plan artifact 为 `docs/host/wu-host-session-event-delivery-01-plan.md`，共4个语义闭环slices；accepted plan commit=`8b29462c`。Slice 1 stop condition 的 plan amendment 已通过原 reviewers 双路 re-review 与 Controller accepted，accepted plan amendment commit=`33af05fa`。Slice 1 implementation artifact 为 `docs/reviews/wu-host-session-event-delivery-01-slice1-implementation-codex.md`；AgentCodex报告focused `317 passed`、Service/CLI `142 passed`、affected suites `3405 passed, 8 skipped, 6 deselected`、stress `6 passed`、coverage `83.59%`–`96%`、完整pyright `0 errors`、diff/scans通过。Slice 1 code review artifacts 为 `docs/reviews/code-review-20260721-203720.md`（AgentMiMo，PASS）与 `docs/reviews/code-review-20260721-203851.md`（AgentDS）；Controller adjudication 为 `docs/reviews/wu-host-session-event-delivery-01-slice1-code-review-controller-adjudication.md`。Controller 逐项裁决后只接受 `DS-F02`：single-pop 丢失旧 terminal fence 过滤，durable read await 期间进入 mailbox 的同 Run transient 可能在 terminal 后交付。AgentCodex fix artifact 为 `docs/reviews/wu-host-session-event-delivery-01-slice1-fix-codex.md`；reported owner/integration `29 passed`、S1 focused `318 passed`、`transient_delta.py` coverage `92.09%`、完整 pyright `0 errors`、diff check通过。原 reviewers continuity artifacts 为 `docs/reviews/wu-host-session-event-delivery-01-slice1-code-rereview-mimo.md` 与 `docs/reviews/wu-host-session-event-delivery-01-slice1-code-rereview-ds.md`；两路 `$deepreview` artifacts 为 `docs/reviews/code-review-20260721-210025.md` 与 `docs/reviews/code-review-20260721-210135.md`；Controller re-review adjudication 为 `docs/reviews/wu-host-session-event-delivery-01-slice1-code-rereview-controller-adjudication.md`。两路确认 `DS-F02` closed、0 new material finding。Accepted Slice 1 commit=`64383186`。Slice 2 implementation artifact 为 `docs/reviews/wu-host-session-event-delivery-01-slice2-implementation-codex.md`；AgentCodex报告focused `159 passed`、affected suites `3410 passed, 8 skipped, 6 deselected`、stress `6 passed`、production single-file coverage `84.28%`–`92.00%`、完整pyright `0 errors`、diff/source/scope audit通过。Slice 2 code review artifacts 为 `docs/reviews/code-review-20260721-221210.md`（AgentMiMo，PASS）与 `docs/reviews/code-review-20260721-221029.md`（AgentDS，PASS）；Controller adjudication 为 `docs/reviews/wu-host-session-event-delivery-01-slice2-code-review-controller-adjudication.md`。Controller逐项裁决 DS-F1/F2/F3，无 accepted current fix；DS-F1 multi-terminal regression 与真实 owner-path post-terminal barrier作为 Slice 3 显式验证输入，不得推迟出本 WU。Accepted Slice 2 commit=`5ac328f0`。Slice 3 partial implementation的第一次scope stop由 `docs/reviews/wu-host-session-event-delivery-01-slice3-stop-condition-controller-adjudication.md` 裁决；required port caller测试范围已通过双路plan review并以commit `6c1cf62a` accepted。第二次scope stop由 `docs/reviews/wu-host-session-event-delivery-01-slice3-second-stop-controller-adjudication.md` 裁决；双opener回归必须从全局hook计数改为opener实例隔离证据，R2 plan review artifacts为 `docs/reviews/plan-review-20260722-000527.md` 与 `docs/reviews/plan-review-20260722-000355.md`，Controller rereview裁决为 `docs/reviews/wu-host-session-event-delivery-01-slice3-second-stop-plan-rereview-controller-adjudication.md`，accepted R2 commit=`b33bb80b`。当前恢复Slice 3；新授权只允许调整目标双opener测试的方法内setup、`_TerminalWatermarkHookCallCounter`与断言，必须证明A本地hook触发/水位推进、C水位保持pre-action、A不会调用C hook、C watcher在C reconciliation前保持pending且无page read，并保留Slice 2全部共享DB/fence/多页/A先于B/timeout/cleanup断言。blocking open questions=`None`。

进入条件已全部满足。设计真源 `docs/host/design.md` 的 async attach、Host-only delivery ownership、durable causal fence、terminal coordinator 与 exact-five contract沿用此前三路设计 re-review 结论；用户随后删除 byte dimension，并冻结 packaged defaults items=`512`、subscriptions=`4`。修订后的完整 contract 必须由本 WU 双路独立 plan review 验证，不得把旧的两个 capacity WU 恢复为独立入口。

### 语义 owner 与实施目标

- 对外保留统一可关闭 iterator 外观，但 factory 改为 `await host.watch_session_events(session_id) -> HostSessionEventIterator`。successful return 是调用方可依赖的生效边界；Host 先 reserve、await 实际 durable start cursor transaction，再在 owner loop 无 `await` 注册 subscription并返回。
- Session Event Delivery 是 live fanout、每订阅唯一 mailbox、唯一 in-flight retained accounting、per-Session subscription admission、overflow / detach、readiness、durable/transient merge与 iterator lifecycle 的唯一 owner。Service 删除 `_WatchAndWaitRuntime.queue` / drain relay，不得保留第二份 event queue、event list或 task-exception side channel。
- runtime composer / operator 显式提供 `transient_mailbox_max_items` 与 `max_subscriptions_per_session`；每个 subscription 使用同一 policy snapshot，packaged defaults 固定为 `512` 与 `4`。Host 只承诺 mailbox + 唯一 in-flight 的 retained item 上界，不承诺 logical bytes 或 Python resident heap 上界。
- EngineEvent ingest 仍只拥有 durable identity / late-state validation与 non-blocking typed handoff；同一 validation transaction 已读取并确认的当前 `Attempt.started_event_sequence` 是 `durable_causal_fence_event_sequence` 的唯一真源。publisher只把该 Host-internal fence 原样复制到每个 mailbox entry；不得暴露为 public payload、第三 sequence domain或 post-commit latest/max readback。
- iterator在 pop transient entry 前必须按 bounded pages把 durable cursor追到该 entry fence；遇前序 Run terminal 时先交付同 Run prefix与 durable terminal，并把后继 Run entry保留在同一 counted Host mailbox。mailbox为空时仍执行 bounded periodic durable reconciliation，使跨 opener / 跨进程 terminal correctness不依赖本地 notice。
- `TerminalPostCommitNotice(session_id, terminal_event_sequence, wake_queue_promotion)` 与单一 `TerminalPostCommitPort` 只负责 producer所属 opener的本地 terminal-ready低延迟 wake和optional queue-promotion协调。所有当前 terminal producer必须从同一 transaction result携带 exact sequence并走该 port；它不承担跨 opener广播或全局 correctness。
- Service仅保留 sole `anext()` consumer与容量一、generation-tagged、exact-five `ServiceObservationResult` slot；五类 caller disposition、fatal sticky、ack / clear / rebind、stop / cancellation仲裁和 cleanup exception precedence按设计真源实施。

### 实施授权与验收

- 实施范围至少覆盖 Host public Protocol / exports、`transient_delta.py`、新 terminal post-commit contract、`open_host.py`、`engine_ingest.py`、`admission.py`、`waiting.py`、`recovery.py`、`dispatch.py`、`command.py`、必要 durable transition/result types、runtime config / assembly、Service entrypoint runtime、受影响 CLI adapters、README 与对应 tests；不得以文件清单为理由拆成互不闭环的 Host/Service capacity WU。
- owner tests冻结 items / subscriptions 双字段校验、先 reserve 后 allocation、所有 release路径、mailbox + in-flight统一 retained item accounting，以及 `511` 后下一项可接受、`512` 后下一项 typed overflow且不入队。overflow / admission必须使用各自 typed public error，不能复用 Host availability错误；不增加恒定容量分类字段、byte dimension或对应 metric。
- static qualified-callsite manifest + runtime fake port +本地 A/B barriers证明所有 terminal producer接入本地 port且无 session-id-only terminal promotion旁路；AST manifest不宣称证明跨 opener correctness。
- 双 opener共享同一 DB 的 deterministic barrier必须覆盖：watcher与后继 B在 opener C，前序 A terminal由 opener A提交且 C无本地notice，B entry经多页catch-up仍先交付A terminal、保留B，Service ack / rebind后的下一次`anext()`才交付B。另测 mailbox空时 periodic reconciliation。
- delayed-cursor deterministic barriers必须覆盖 cursor transaction被阻塞、并发 terminal、cursor完成后到subscription attach / return之间的 durable提交、factory cancellation、Host close与partial allocation failure；每条路径精确一次释放reservation和资源，successful return后不得因attach未完成丢失本地transient。
- 删除 Host batch `drain_nowait()` tuple retention与Service event-copy relay；删除逐事件 logical-byte / resident-heap accounting 与相关 helper。metrics只使用低基数 event / outcome，不记录payload正文、Session/Run identity或不存在的容量维度。
- Service / UI activity / thinking callback必须快速、同步、非阻塞返回；慢 I/O、重 CPU与renderer由Service/UI owner显式解耦，不能依赖Host mailbox吸收callback延迟，也不能建立新的event-copy relay。
- 运行全部受影响测试、单文件覆盖率检查（目标 `>=80%`）、完整pyright、`git diff --check`、旧术语/source propagation scans与README trigger audit。item/subscription defaults、低基数 metrics、callback约束与所有上述测试均是本 WU acceptance，不得降级为 residual。

### 非目标与 residual 裁决

- 不持久化、重放、断线补放或跨 Host restart恢复任何 delta；不建立 durable/transient跨域总序、第三 sequence domain、terminal marker history或跨进程 terminal广播。
- 不修改 Engine public contract，不让Service/UI绕过Host消费 raw `EngineEvent`，不让慢 UI / Service暂停Agent、Engine、promotion或其它watcher。
- 不增加Host-global跨Session总内存quota；当前 contract 只要求per-subscription retained item cap及per-Session subscription cap，不承诺logical-byte、resident-heap或跨Session总内存上界。若未来出现独立的全局SLO/租户隔离需求，必须重新走design gate。
- 不实施 `WU-CLI-SMOKE-01-R2` thinking panel / history / expandable UI。

本 WU 的 design residual=`0`、未归属 residual=`0`。用户已明确接受不提供logical-byte / resident-heap上界的风险；该风险不得在 plan 中重新伪装为 byte-cap acceptance。所有当前已知可实施项已进入上述 acceptance；完成前不得把其中任一项重新标记为 deferred residual。

## WU-WAIT-03 External Job Physical Cancel / Revoke / Abandon

### 状态

GitHub Issue #92 当前为 OPEN，归属 #87 Host Lifecycle Watchdog / Supervisor umbrella。WU-WAIT-01 / GitHub Issue #89 已通过 PR #163 于 2026-07-01 merge 到 `main`；WU-WAIT-02 / GitHub Issue #90 已通过 PR #165 于 2026-07-03 merge 到 `main`。Goal confirmation 已由用户确认。Plan artifact 为 `docs/host/wu-wait-03-external-job-lifecycle-plan.md`。Plan、Slice 1、Slice 2、aggregate deepreview、README sync fix、aggregate re-review、draft PR、PR review 和 final closeout gate 均已完成；完整 artifact 记录见本文档后续 WU-WAIT-03 active section 以及 `docs/reviews/wu-wait-03-*`。Draft PR #166 已创建：https://github.com/noho/dayu-agent-r/pull/166。PR body 使用 `Closes #92`，merge 会自动关闭 #92。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/92#issuecomment-4880126795。当前进入 final-closeout-pass，等待用户 / maintainer 处理 draft PR #166；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。

### 设计与代码核对

- Host 设计真源规定 Host 是 Session / Run / Attempt / EventLog / wait record 的治理真源；provider lifecycle 动作不得成为 Host cancellation correctness 的前置条件。
- Engine 设计真源规定 Engine 不轮询外部长事务、不持久化 wait record、不恢复旧 Agent / Runner，也不拥有 external job lifecycle。
- 代码核对显示 `cancel_run` / `cancel_session_runs` 取消 `WAITING` Run 时只走 Host durable cancel 收口；external job lifecycle 当前落点是 wait poller 对 cancelled wait 调用 `WaitPollAdapter.abandon_wait(...)`。
- 当前 `WaitPollAdapter.abandon_wait(...)` 只能通过返回 `None` 或抛异常表达结果，尚不能区分 physical cancel / revoke / abandon、unsupported、noop、timeout 或 transient failure。

### 目标

- 固化 WAITING external job physical cancel / revoke / abandon 的 typed adapter capability 与 best-effort diagnostic 语义。
- Host-side `RUN_CANCELLED` 正确性不得依赖外部 cancel 成功；external lifecycle failure / timeout 不得 reopen 或改写已 cancelled Run。
- late callback / poll / manual result 仍必须通过 common `resolve_wait(...)` path，被 late-result diagnostic 拒绝，不创建 resume Attempt。

### 非目标

- 不修改 Engine awaiting public model。
- 不让 Engine 拥有等待、取消、轮询、恢复或 external job lifecycle。
- 不把 external job id 变成 Host durable primary key。
- 不要求所有 provider 支持 physical cancel。
- 不绕过 `resolve_wait(...)` / late-result rejection。
- 不创建 #87 之外的第二套 watchdog/runtime。
- 不做 WU-WAIT-04 UI / Service production-grade awaiting E2E smoke。

### Plan Review Gate 约束

- Review 必须审查 plan 是否 code-generation-ready，是否从直接代码证据定位 root cause，是否存在把 Host cancel correctness 绑定到 provider cancel 成功的设计错误。
- Review 必须审查 Slice 切分是否符合本文档 Slice 切分原则；本 WU 当前 plan 为 2 个 implementation slices，超过 3 个 slices 的替代建议必须有明确上下文容量、失败/回滚风险或依赖顺序证据。
- Review 必须审查 plan 是否误引入新的 public Host API、Engine contract、durable schema、provider capability registry、第二套 watchdog 或过度设计。
- Review findings 必须能裁决为 `accepted`、`rejected-with-reason`、`deferred-with-owner` 或 `needs-more-evidence`。

## WU-WAIT-02 Production Poller Loop / Backoff / Fencing / Retry

### 状态

GitHub Issue #90 当前为 OPEN。WU-WAIT-01 / GitHub Issue #89 已通过 PR #163 于 2026-07-01 merge 到 `main`，本文档先前记录的 “等待 PR #163 后进入 WU-WAIT-02” 前置条件已满足。Goal confirmation 已由用户确认。Plan artifact 为 `docs/host/wu-wait-02-production-poller-plan.md`。Plan review artifacts 为 `docs/reviews/plan-review-20260701-135815.md` 与 `docs/reviews/plan-review-20260701-140124.md`，controller adjudication 为 `docs/reviews/wu-wait-02-plan-review-controller-adjudication.md`。Plan-fix artifact 为 `docs/reviews/wu-wait-02-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/plan-review-20260701-141039.md` 与 `docs/reviews/plan-review-20260701-141200.md`，controller adjudication 为 `docs/reviews/wu-wait-02-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，所有 accepted findings 已修复。Accepted plan commit 为 `350e1dbf`。Slice 1 implementation artifact 为 `docs/reviews/wu-wait-02-slice1-implementation-codex.md`；AgentCodex reported focused Host durable / wait adapter tests 102 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same focused tests with 102 passed, pyright with 0 errors, and `git diff --check` passed. Slice 1 code review artifacts 为 `docs/reviews/code-review-20260701-143921.md` 与 `docs/reviews/code-review-20260701-144036.md`；controller adjudication 为 `docs/reviews/wu-wait-02-slice1-code-review-controller-adjudication.md`。两路 code review 均通过，无 required current fix；DS low-severity items 已裁决为 non-blocking / Slice 2 optional coverage。Accepted Slice 1 commit 为 `b7447316`。Slice 2 implementation artifact 为 `docs/reviews/wu-wait-02-slice2-implementation-codex.md`；AgentCodex reported wait poller runtime focused tests 20 passed, schema / wait record tests 57 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same focused test sets with 20 passed and 57 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code review artifacts 为 `docs/reviews/code-review-20260701-150341.md` 与 `docs/reviews/code-review-20260701-150525.md`；controller adjudication 为 `docs/reviews/wu-wait-02-slice2-code-review-controller-adjudication.md`。Controller accepted S2-CR-F01 unsafe default direct factory, S2-CR-F02 constructor dead parameters, S2-CR-F03 self-close contract gap, S2-CR-F04 double-close transient state, and S2-CR-F05 close drain timeout `None` contract mismatch. Fix artifact 为 `docs/reviews/wu-wait-02-slice2-fix-codex.md`；AgentCodex reported wait poller runtime focused tests 24 passed, schema / wait record tests 57 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same focused test sets with 24 passed and 57 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code re-review artifacts 为 `docs/reviews/code-review-20260701-151948.md` 与 `docs/reviews/code-review-20260701-152140.md`；controller adjudication 为 `docs/reviews/wu-wait-02-slice2-code-rereview-controller-adjudication.md`。两路 code re-review 均通过，S2-CR-F01 / F02 / F03 / F04 / F05 均已关闭，无新增 material defect。Accepted Slice 2 commit 为 `2974b5a2`。Slice 3 implementation artifact 为 `docs/reviews/wu-wait-02-slice3-implementation-codex.md`；AgentCodex reported open_host / poller / resolve focused tests 51 passed, public lifecycle smoke 2 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 51 passed, 2 passed, pyright 0 errors, and `git diff --check` passed. Slice 3 code review artifacts 为 `docs/reviews/code-review-20260701-154721.md` 与 `docs/reviews/code-review-20260701-154834.md`；controller adjudication 为 `docs/reviews/wu-wait-02-slice3-code-review-controller-adjudication.md`。两路 code review 均通过，无 required current fix。Accepted Slice 3 commit 为 `1486e5a9`。Aggregate deepreview artifacts 为 `docs/reviews/code-review-20260701-155500.md` 与 `docs/reviews/code-review-20260701-160040.md`；controller adjudication 为 `docs/reviews/wu-wait-02-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均通过，无 blocking finding；residual risks 已归属 Service composition / WU-WAIT-03 / WU-WAIT-04 或 accepted design tradeoff。Accepted aggregate deepreview commit 为 `346b5ae7`。Draft PR #165 已创建：https://github.com/noho/dayu-agent-r/pull/165。PR review artifacts 为 `docs/reviews/pr-165-review-20260701-164627.md` 与 `docs/reviews/pr-165-review-20260701-164858.md`；AgentCodex fix artifact 为 `docs/reviews/wu-wait-02-pr-review-fix-codex.md`；PR re-review artifacts 为 `docs/reviews/pr-165-re-review-20260701-170000.md` 与 `docs/reviews/pr-165-re-review-20260701-170022.md`；controller adjudication 为 `docs/reviews/wu-wait-02-pr-review-controller-adjudication.md`。DS Finding 01 已接受并修复，两路 re-review 均裁决已修复；DS Finding 02 已裁决为 rejected-with-reason；MiMo findings 均为 non-blocking notes / design confirmations。Accepted PR review commit 为 `0bfedacf`，并已 push 到 draft PR #165。`gh pr checks 165` reported no checks on branch `work/wu-wait-02-issue-90`。Final closeout artifact 为 `docs/reviews/wu-wait-02-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/90#issuecomment-4852470129。PR body 使用 `Closes #90`，merge 会自动关闭 #90。当前进入 final-closeout-pass gate，等待用户 / maintainer 处理 draft PR #165；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #165 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-WAIT-03 / GitHub Issue #92。Review / implementation / fix / re-review artifact 放在 `docs/reviews/` 下。

### 设计与代码核对

- Host 设计真源规定：wait poller 是 background runtime 中的 trigger / adapter。它观察 wait record 与外部 job，但只能通过 `resolve_wait` command path 提交结果；不得持有 EventLog appender，不得直接更新 Run / Attempt / wait record terminal state。
- Host 设计真源规定：`poll`、`callback`、`manual` 只是发现等待结果已经到达的 adapter；稳定核心是共同的 Host `resolve_wait` pipeline。
- Host 设计真源规定：poll adapter 从 wait record 读取 `external_job_id` / `await_spec` 后继续轮询，并在完成时调用同一个 `resolve_wait`；`cancelled` / `lost` wait record 的迟到结果不得作为 canonical fact 进入 EventLog。
- Engine 设计真源规定：Engine 不等待外部长事务完成，不轮询 job，不持久化 wait record，不保留可恢复的 Agent / Runner；长事务 awaiting、orphan cleanup 和工具级取消属于 Host / ToolRuntime。
- GitHub Issue #90 明确当前已有最小 `WaitPoller.poll_once()`：读取 active poll / cancelled wait records，在 Host transaction 外调用 adapter，ready / lost 结果通过 `resolve_wait`，not-ready 不动作，cancelled 调用 `abandon_wait`，adapter 异常按单条 wait 隔离。
- 代码核对显示 `dayu/host/wait_adapter.py` 当前 `WaitPoller` 是同步单轮 primitive，返回 `WaitPollOnceResult(observed, not_ready, resolved, lost, abandoned, adapter_errors)`；当前没有后台循环、生命周期 start / stop / close drain、退避策略、in-flight claim / fencing、运行状态诊断或 supervisor 集成。
- 代码核对显示 `tests/host/test_wait_adapter_polling.py` 已覆盖 ready、not-ready、lost、cancelled abandon-once、missing adapter、adapter error isolation、resolve_wait error isolation 与 abandon failure retry；尚未覆盖 production loop lifecycle、backoff、concurrent poller claim conflict、resolve retry / idempotency 与 shutdown behavior。

### 目标

- 在 Host 层设计并实现 production wait poller loop，围绕现有 `poll_once` / batch poll 语义提供可启动、可停止、可关闭收尾的后台 runtime。
- 引入 bounded backoff，覆盖 adapter exception、rate limit / provider busy、重复 not-ready、cancelled wait abandon failure 与 transient `resolve_wait` failure，避免 tight loop。
- 引入最小 in-flight claim / fencing，防止多个 poller 或 Host 进程并发处理同一 wait record；claim 只防重复 polling / duplicate resolve，不表达 Attempt ownership、EventLog truth、外部 job ownership、旧 Attempt takeover 或重 lease。
- poller ready / lost 结果必须继续走共同 Host `resolve_wait` pipeline；不得直接 append EventLog、更新 Run / Attempt / wait record terminal state、创建 resume Attempt 或绕过幂等检查。
- 提供可测试、可观测的 poll loop diagnostics：running / stopped、observed / claimed / skipped、ready / lost / not-ready、adapter errors、resolve failures、backoff decisions、claim expiration / conflict。
- 通过 existing `watch_session_events(...)` / outbox 观察 Host 状态推进，不把 poller 设计成 UI event iterator。

### 非目标

- 不实现 HTTP callback auth / replay；该能力已由 WU-WAIT-01 / GitHub Issue #89 处理。
- 不实现 external job physical cancel / revoke / abandon 的完整 provider lifecycle；该能力归 WU-WAIT-03 / GitHub Issue #92。
- 不实现 UI / Service production-grade awaiting E2E smoke；该验收归 WU-WAIT-04，必须等待 #89 / #90 / #92 完成。
- 不把 poller 变成通用 scheduler、watcher、UI event iterator、lifecycle supervisor 或分布式 lease / Attempt takeover 系统。
- 不让 backoff state 成为 Host durable truth，除非 plan 基于直接代码证据证明某个最小 durable 字段是 claim / multi-process correctness 必需。
- 不改变 Engine awaiting 公共模型，不让 Engine 拥有 wait record、poller、activation 或 external job lifecycle truth。

### Plan Gate 约束

- Plan 必须先裁决 claim / fencing 放置位置：是扩展 wait record durable row、增加独立 poll claim 表，还是使用其它最小 Host durable primitive；必须说明为什么该选择不是 lease / takeover。
- Plan 必须明确 poll loop 的 lifecycle API、Host opener / close 集成方式、sleep cancellation、in-flight adapter 调用边界、close drain 和异常上报。
- Plan 必须明确 backoff policy 的 owner、状态存储位置、重试节奏、上限、诊断表达和测试注入点；不得用魔法数字散落实现。
- Plan 必须明确 resolve retry / idempotency 语义：poller 失败重试不得 double-resolve，必须复用稳定 poll idempotency key 或明确新的幂等键策略。
- Plan 必须明确 diagnostics 是否只是 runtime read view / log / result summary，还是需要进入 EventLog diagnostic；若进入 EventLog，必须先对齐 Host 设计真源。
- Plan 必须按本文档 Slice 切分原则控制 gate 成本。当前属于中型 Host durable/runtime work，默认优先 2-3 个可验证 implementation slices；超过 3 个 slices 必须说明不能合并的独立失败 / 回滚风险。

### 验收信号

- Production poller loop 可以后台运行并在 Host close / explicit stop 时干净停止，不留下 sleep 或 in-flight wait 悬挂。
- 多个 poller 不会并发 resolve 同一 wait；claim conflict / expiration 行为可测试。
- Adapter 间歇失败、重复 not-ready、abandon failure 和 transient `resolve_wait` failure 不会丢失 wait，也不会 tight-loop。
- Ready / lost outcomes 仍通过共同 `resolve_wait` 管线推进 Host EventLog、wait record、Run / Attempt 与 resume dispatch。
- UI / Service 通过现有 Host event watch / outbox 能观察 poller 推进后的状态；poller 不直接返回 UI events。
- 受影响 Host tests、Service assembly tests、pyright 通过；涉及 Host public contract、durable schema、状态机或 README 职责范围的变化必须同步设计真源与对应 README。

## WU-TOOLS-01-F01-02-R1 Awaiting External Job Two-Phase Activation

### 状态

当前 authoritative 状态为 `completed`：PR #162 已于 2026-06-21 merge，merge commit 为 `ab60aa4d`；GitHub Issue #129 同步关闭。下方长段落保留为 merge 前的 gate / final-closeout 历史证据，其中 Issue OPEN、draft PR 和等待 merge 等措辞不再表示当前状态。

GitHub Issue #129 当前为 OPEN。本条来自 `WU-TOOLS-01-F01-02` residual risk：Fins awaiting external job 当前存在 submit-before-accept 窗口。PR 161 / WU-TOOLS-AWAIT-FANOUT-01 已 merge，#111 的单 owner / fanout 语义已可作为本条设计依据。用户在 2026-06-21 goal confirmation 中确认本条进入 plan gate，并补充裁决：本 WU 必须一次到位实现 Host two-phase activation 支持，并让当前 Fins download / preprocess / upload awaiting tools 直接使用 two-phase；禁止引入过度设计。Plan artifact 为 `docs/host/wu-tools-01-f01-02-r1-plan.md`。Plan review artifacts 为 `docs/reviews/plan-review-20260621-180827.md` 与 `docs/reviews/plan-review-20260621-181350.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-plan-review-controller-adjudication.md`。Plan-fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/plan-review-20260621-182034.md` 与 `docs/reviews/plan-review-20260621-182047.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，所有 accepted findings 已修复。Accepted plan commit 为 `478f5f77`。Slice 1 implementation artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-implementation-codex.md`；focused test reported `34 passed` and pyright reported 0 errors. Slice 1 code review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-controller-adjudication.md`。Fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-fix-codex.md`；focused test reported `37 passed` and pyright reported 0 errors. Slice 1 code re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-rereview-controller-adjudication.md`。Accepted Slice 1 commit 为 `e10f2e99`。Slice 2 implementation artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-implementation-codex.md`；Fins focused tests reported `51 passed` and `68 passed`, pyright reported 0 errors. Slice 2 code review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-controller-adjudication.md`。Fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-fix-codex.md`；Fins focused tests reported `68 passed` and `51 passed`, pyright reported 0 errors. Slice 2 code re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-rereview-controller-adjudication.md`。Accepted Slice 2 commit 为 `4f45f8de`。Slice 3 implementation artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-implementation-codex.md`；Service test reported `52 passed`, focused Host/Fins tests reported `159 passed`, pyright reported 0 errors. Slice 3 code review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-controller-adjudication.md`。Fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-fix-codex.md`；Service test reported `52 passed`, focused Host/Fins tests reported `159 passed`, pyright reported 0 errors. Slice 3 code re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-controller-adjudication.md`。Narrow fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-rereview-fix-codex.md`；narrow code re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-narrow-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice3-narrow-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-narrow-rereview-controller-adjudication.md`。两路 narrow re-review 均通过，S3-RR-F01 已关闭。Accepted Slice 3 commit 为 `80ab56ab`。Aggregate deepreview artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-ds.md`；aggregate fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-fix-codex.md`；aggregate fix narrow re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-controller-adjudication.md`。AGG-F01 已关闭，controller 裁决无当前 WU 未归属 residual risk。Accepted deepreview commit 为 `95f652de`。Draft PR #162 已创建：https://github.com/noho/dayu-agent-r/pull/162。`gh pr checks 162` reported no checks on branch `phase/wu-tools-01-f01-02-r1`。PR review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-pr-review-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-pr-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-pr-review-controller-adjudication.md`。两路 PR review 均通过，无 accepted current fix。Accepted PR review commit 为 `50431ab2` 并已 push 到 draft PR #162。Final closeout artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/129#issuecomment-4762165431。PR body 使用 `Closes #129`，merge 会自动关闭 #129。当前进入 final-closeout-pass gate，等待用户 / maintainer 处理 draft PR #162；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #162 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-WAIT-01 / GitHub Issue #89。

### 设计与代码核对

- Engine 设计真源规定：Engine 只消费 `ToolExecutor.execute(...)` 的 bounded handshake outcome；长事务 awaiting、orphan cleanup、工具级取消和 batch 内执行策略属于 Host / ToolRuntime，不属于 Engine。
- Host 设计真源规定：`ToolAwaitingOutcome` 只能经 ToolRuntime Host awaiting accept path 写入 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` 与 wait record；Engine `tool_awaiting` / `run_suspended` 只能作为确认或诊断，不创建 wait record。
- `dayu/fins/tools/download_tools.py`、`dayu/fins/tools/preprocess_tools.py` 与 `dayu/fins/tools/upload_tools.py` 当前在工具 callable 内调用 `runtime.start_observed_download(...)`、`runtime.start_observed_preprocess(...)`、`runtime.start_observed_upload(...)`，随后才返回 `ToolAwaitingOutcome`。
- `dayu/fins/ingestion_runtime.py` 当前 `start_observed_*` 会注册 process-local observation，并立即调用 `executor.submit(...)`。Host wait record 写入发生在 `dayu/host/tool_runtime.py` 的 `_accept_awaiting(...)` 之后，因此存在 external job 已启动但 Host wait truth 尚未 durable accepted 的窗口。
- `FinsIngestionJobStatus` 当前只有 `queued / running / cancelling / succeeded / failed / cancelled`，没有 prepared / activated 语义；`claim_running_or_cancelled(...)` 是 executor operation 内部进入 running 的 claim，不等价于 Host accepted-wait 后 activation。
- Fins wait adapter 当前已覆盖 `start_fins_download`、`start_fins_preprocess`、`start_fins_upload`，通过 lightweight observation handle poll completion；仅调整 poller 不能关闭 submit-before-accept root cause。

### 目标

- 设计并实现最小 two-phase activation：Fins awaiting tool 先 prepare / 登记可观察长事务，不 submit 后台 executor；Host awaiting accept 成功后通过 activation hook 触发 activate / submit。
- Host / ToolRuntime 必须只在 awaiting accept ack 成立后触发 activation；accept rejected、accept timeout、pre-accept cancellation 或 stale execution 不得启动外部长事务。
- Fins download / preprocess / upload awaiting tools 本轮直接迁移到 prepare / activate，不能只预留 Host hook。
- Activation 必须幂等；同一 prepared operation 重试 activation 不得 double-submit。
- Cancellation between prepare and activate 必须能关闭 prepared operation，不启动后台执行。
- Poller / wait adapter 对 prepared-but-not-active 状态必须有明确行为，不误报 terminal 或 lost；activation failure after accepted wait 必须有结构化收口。

### 非目标

- 不改变 Engine awaiting 公共模型，不让 Engine 拥有 activation、wait record 或 external job lifecycle truth。
- 不把 activation、execution context、cancellation token 或 Host governance id 暴露到 LLM-facing tool schema。
- 不为未来所有 provider 设计通用 lifecycle supervisor、durable follower ledger、跨 Attempt duplicate table、通用 wait alias schema 或新的 public await contract。
- 不在本条实现 #89 callback endpoint / auth / replay、#90 production poller loop / backoff / fencing / retry，或 #92 external job physical cancel / revoke / abandon 全量能力。
- 不用 Fins-only workaround 绕过 Host awaiting accept barrier；如新增 Host hook，必须是当前 ToolRuntime accepted-wait 后 activation 所需的最小层内契约。

### Plan Gate 约束

- Plan 必须明确 Host activation hook 放置位置、调用时机、失败收口、幂等语义和不暴露 LLM-facing schema 的证据。
- Plan 必须明确 Fins runtime prepare / activate API、prepared 状态表达、activation 幂等、pre-activation cancel、activation failure 和 poller prepared 状态行为。
- Plan 必须覆盖 download / preprocess / upload 三类 awaiting tools，不能只覆盖其中一个。
- Plan 必须按本文档 Slice 切分原则控制 gate 成本。小型跨模块 cleanup 默认上限为 3 个 implementation slices；若超过 3 个 slices，必须证明不能合并为更少的语义闭环。
- Plan 必须说明为什么没有过度设计，尤其是为什么没有引入通用 lifecycle supervisor、跨 provider activation 平台或新的 public await contract。

### 验收信号

- 受控测试能证明 awaiting accept 成功前不会 submit / activate Fins background job。
- Accept rejected / timeout / stale execution / pre-accept cancel 不会 activate prepared operation。
- Accepted wait 后 activation 成功会进入当前 Fins observation / poll / resolve path，download / preprocess / upload 均覆盖。
- Activation retry 不 double-submit；prepared operation 被取消或 abandoned 时不启动执行。
- Activation failure after accepted wait 有结构化 failed / lost / diagnostic 收口，且不让 Run 永久卡在无法解释的 WAITING。
- 受影响 Host / Fins tests、pyright 通过；涉及 Host / Engine contract 或 Fins runtime contract 的设计变化同步到设计真源和必要 README。

## WU-TOOLS-AWAIT-FANOUT-01 Host ToolRuntime Awaiting Fanout Governance Hardening

### 状态

GitHub Issue #111 当前为 OPEN。用户在 2026-06-21 裁决将本条作为工具调用治理执行正确性的默认下一步。Goal confirmation 已完成。Plan gate artifact 为 `docs/host/wu-tools-await-fanout-01-plan.md`。Plan review artifacts 为 `docs/reviews/wu-tools-await-fanout-01-plan-review-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-plan-review-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-plan-review-controller-adjudication.md`。Plan-fix artifact 为 `docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/wu-tools-await-fanout-01-plan-rereview-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-plan-rereview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，0 个未修复 accepted finding，0 个新增 blocking finding。Accepted plan commit 为 `29b211d7`。Implementation artifact 为 `docs/reviews/wu-tools-await-fanout-01-implementation-codex.md`，唯一 implementation slice `S1 轻量 awaiting cleanup terminal marker` 已完成，focused tests 报告 `182 passed`，pyright 报告 0 errors。Code review artifacts 为 `docs/reviews/wu-tools-await-fanout-01-code-review-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-code-review-ds.md`。Controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-code-review-controller-adjudication.md`。Fix artifact 为 `docs/reviews/wu-tools-await-fanout-01-fix-codex.md`，accepted findings DS-F01 与 DS-F03 已由 AgentCodex 处理，focused tests 报告 `184 passed`，pyright 报告 0 errors。Code re-review artifacts 为 `docs/reviews/wu-tools-await-fanout-01-code-rereview-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-code-rereview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-code-rereview-controller-adjudication.md`。两路 code re-review 均通过，0 个未修复 accepted finding，0 个新增 blocking finding。Accepted slice commit 为 `2e5791c9`。Aggregate deepreview artifacts 为 `docs/reviews/wu-tools-await-fanout-01-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-aggregate-deepreview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均通过，0 个 blocking finding；MiMo 的低风险 WU 表格状态同步 finding 已由本文档更新关闭。Accepted deepreview commit 为 `cf125c4c`。Draft PR #161 已创建：https://github.com/noho/dayu-agent-r/pull/161。`gh pr checks` reported no checks on branch `phase/wu-tools-await-fanout-01`。Final closeout artifact 为 `docs/reviews/wu-tools-await-fanout-01-final-closeout.md`，裁决无当前 #111 active residual risk；`AWAITING_FANOUT` production reachability 与 DS-F02 diagnostic visibility 仅作为 future-change guardrails 留痕，不作为本 WU residual 或后续 owner。当前进入 final-closeout-pass gate，等待用户 / maintainer 处理 draft PR #161；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。

### 设计与代码核对

- Host 设计真源规定 ToolRuntime / TruncationManager 是工具执行治理、截断、`fetch_more`、等待与重复调用治理 owner；工具事实必须走 Host accept barrier。
- Engine 设计真源规定 Engine 只通过 `ToolExecutor.execute(...)` 做 bounded handshake；batch 内执行策略、权限、审批、限流、内部 timeout、审计、长事务 awaiting、orphan cleanup 和工具级取消属于 Host / ToolRuntime。
- 当前 attempt-scoped duplicate governance 已覆盖同一 Attempt 内重复工具调用的 in-flight owner / waiter 基本窗口，但 #111 指出 awaiting 路径缺少 fanout 设计。
- 当前 Host waiting 状态迁移要求 awaiting canonical facts 由 ToolRuntime Host accept path 拥有；Engine `tool_awaiting` / `run_suspended` 只能作为 preview、diagnostic 或 idempotent confirmation，不能创建 wait record 或关闭 Attempt。
- #111 的直接问题是：duplicate owner 返回 `ToolAwaitingOutcome` 并创建 durable wait record 后，重复 waiter 不能简单再创建第二个 wait record，也不能没有 durable owner 地返回 waiting；否则 external job、resolve、cancel、late result 和 idempotency conflict 语义都会分裂。
- 2026-06-21 goal confirmation 补充约束：awaiting / Fins ingestion 方向刚从较重的 durable 设计收缩到当前薄 wait record + lightweight observation handle 实现。本 WU 的 plan 必须优先在 attempt-local duplicate governance、已有 awaiting accept ack、现有 wait record 与 RunInputBuilder resume material 上补齐 fanout 语义；不得重新引入重型 durable follower ledger、通用 wait alias schema、跨 Attempt durable duplicate table、外部 job activation 两阶段协议或新的 Host public await contract，除非代码直接证据证明没有轻量方案可满足 #111。

### 目标

- 设计并实现重复 awaiting owner / waiter 的单 owner fanout 语义。
- 同一 duplicate key 的 awaiting owner 只创建一个 durable wait record / external job owner；waiter 不重复启动外部 job。
- 明确 waiter 的 follower / alias / diagnostic 表达，或明确由 resume input / RunInputBuilder material 把 shared waiting result 表示为共享事实。
- `resolve_wait` 后，resume input 必须能让模型看到等待结果足以覆盖重复调用语义，不依赖模型天然记住上一 Attempt 的 tool call。
- 明确 cancel、late result、idempotency conflict、owner lost、external job lost 和 awaiting accept rejected / timeout 的收口规则。
- 增加 focused tests 覆盖重复 awaiting owner / waiter 并发、owner accepted waiting、owner awaiting accept rejected / timeout、resolve_wait 成功、cancel / late result。

### 非目标

- 不把 `ToolAwaitingOutcome` 简单当作 completed result 写入 duplicate accepted index。
- 不绕过 Host awaiting accept barrier。
- 不让 Engine、wait adapter 或 provider runtime 直接拥有 Host durable truth。
- 不在本条实现 #129 的 external job two-phase activation；本条只固定 duplicate awaiting fanout 语义。
- 不在本条实现 #89 / #90 / #92 的 production callback、poller 或 physical cancel 能力。
- 不重新扩大刚收缩过的 awaiting durable 设计；禁止以“未来通用 fanout”为理由新增重型 wait follower 表、durable duplicate ledger、跨进程等待者队列或新的 public await lifecycle contract。

### 依赖与后续

- 本条依赖现有 attempt-scoped duplicate governance、ToolRuntime awaiting accept barrier 和 wait record durable truth。
- 本条完成后，#129 two-phase activation plan 必须消费本条对 wait owner / follower / alias 的设计结论。
- #89 / #90 / #92 的 production WAIT hardening 不应先行定义与本条冲突的 wait owner 或 external job fanout 语义。
- #70 Tool Trace analyzer 可以并行 discussion，但 analyzer 只能报告 duplicate awaiting / fanout 证据或 limited signal，不能替代本条的 Host governance 修复。

### 验收信号

- 同一 Attempt 内重复 awaiting call 不会启动多个 external jobs，也不会创建语义冲突的多个 wait records。
- waiter 有可恢复、可审计、可诊断的 fanout 表达；不是只存在于内存里的临时等待者。
- wait resolution 后的 resume material 能表达 shared waiting result，且不泄漏 Host internal refs 到 LLM-facing 文本。
- cancel、late result、owner lost、accept rejected / timeout 都有结构化 diagnostic 或 governed outcome。
- 受影响 tests 与 pyright 通过；若修改 Host / Engine public contract 或 EventLog / wait schema，先更新 `docs/host/design.md` 和必要 README。

## WU-TOOLS-01-F03-R4 Tools Discovery Spec Semantics Cleanup

### 状态

GitHub Issue #133 已 CLOSED，PR 160 已于 2026-06-21 merge。本 WU 从 WU-TOOLS-01-F03 final closeout residual risk 转入独立实施入口，goal confirmation 已由用户确认，plan gate 已完成，plan review completed with blocking findings，plan-fix gate 已完成，plan re-review passed，accepted plan commit 已创建，Slice 1 implementation / code review / accepted slice commit 已完成，Slice 2 已由 controller 裁决为 covered by Slice 1，Slice 3 implementation / code review / accepted slice commit 已完成，Slice 4 implementation / code review / accepted slice commit 已完成，Slice 5 implementation / code review / fix / re-review / accepted slice commit 已完成，Slice 6 implementation / code review / accepted slice commit 已完成，Slice 7 final validation 已完成，aggregate deepreview 已完成且无阻塞 finding，accepted deepreview commit 已创建，ready-to-open-draft-PR gate 已完成，push gate 已完成，draft PR 160 已创建，PR review 已完成且无需当前修复，accepted PR review commit 已创建并推送，draft-PR-pass 已达成，final closeout comment 已发布，当前已完成，不再作为 active implementation entry point。

Plan artifact:

- `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`

Plan review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-plan-review-mimo.md` by AgentMiMo, verdict `pass-with-findings`, blocking findings `1`
- `docs/reviews/wu-tools-01-f03-r4-plan-review-ds.md` by AgentDS, verdict `pass-with-findings`, blocking findings `2`

Controller plan-review judgment:

- `accepted`：MiMo F01 — plan 必须明确 `_fins_wait_adapter_registry_from_provider_configs` 使用 effective provider configs，或复用同一 relative-to-absolute workspace 解析逻辑；否则 packaged `workspace/` 会让 wait adapter 构造直接失败。
- `accepted`：MiMo F02 / DS F6 — plan 必须明确 `workspace/` 的解析基准为 Service request/runtime `workspace_root` 下的 `workspace/`，并给出具体测试断言；不得把该决策留给 implementation owner 猜测。
- `accepted`：MiMo F03 / DS F5 — upload 默认注册后可能扩大 scene tool exposure，plan 必须加入默认 scene manifest / tool selection 验证步骤。
- `accepted`：DS F1 — Doc provider 决策必须收敛为单一路径：packaged `doc-tools.enabled=false`，且 Doc provider 在 enabled + empty `allowed_paths` 时 fail fast with business-specific error；implementation agent 不得在两个方案之间自行裁决。
- `accepted`：DS F2 — `ToolsDiscoveryProviderSpec.allow_empty` 删除与 `host_assembly.py` 映射删除必须位于同一可独立验证 slice，避免 slice 间代码库不可导入。
- `accepted`：DS F3 — plan 必须读取并记录 Web provider 是否存在空输出路径；若存在，需在 plan 中裁决处理方式。
- `accepted`：DS F4 — plan 必须显式确认 Fins download / preprocess providers 在有效 config 下是否返回非空 definitions。

Plan-fix artifact:

- `docs/reviews/wu-tools-01-f03-r4-plan-fix-codex.md` by AgentCodex

Plan-fix summary:

- MiMo F01：已修复，plan 要求 wait adapter construction 消费与 discovery 同一 effective provider config tuple，raw packaged `workspace/` 不得进入 `_fins_wait_adapter_registry_from_provider_configs(...)`。
- MiMo F02 / DS F6：已修复，plan 固定相对 Fins `workspace_root` 语义：Service request/runtime `workspace_root=/path/to/project` 加 packaged `workspace/` 解析为 `/path/to/project/workspace`。
- MiMo F03 / DS F5：已修复，plan 将默认 scene upload exposure 纳入当前 WU implementation item，要求默认非 upload scenes 不再通过 broad `fins` tag 选中 `start_fins_upload`。
- DS F1：已修复，Doc provider 单一路径为 packaged `doc-tools.enabled=false`，且 enabled Doc provider missing / empty `allowed_paths` 必须 Doc-specific fail fast。
- DS F2：已修复，plan 合并 provider-level `allow_empty` config 删除、`ToolsDiscoveryProviderSpec.allow_empty` 删除与 `host_assembly.py` mapping 删除到同一个可独立验证 Slice 1。
- DS F3：已修复，plan 记录 Web provider 直接证据：`dayu.tools.web:discover_tools` 到 `dayu/tools/web/provider.py`，definitions 必须为 `search_web` / `fetch_web_page`，无正常空输出路径。
- DS F4：已修复，plan 记录 Fins download / preprocess provider 在有效 absolute `workspace_root` 下各返回一个 awaiting tool definition。

Plan re-review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-plan-rereview-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-plan-rereview-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Plan re-review final finding status:

- MiMo F01：已修复。
- MiMo F02 / DS F6：已修复。
- MiMo F03 / DS F5：已修复。
- DS F1：已修复。
- DS F2：已修复。
- DS F3：已修复。
- DS F4：已修复。
- MiMo F04：non-blocking low severity；implementation 时核对 scene manifest 显式 `tool_names` 完整性，Slice 4 验证命令可捕获遗漏，不阻塞 accepted plan commit。

Accepted plan commit:

- `fe212365` (`gateflow: accept plan for WU-TOOLS-01-F03-R4`)

Slice 1 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice1-implementation-codex.md` by AgentCodex

Slice 1 implementation validation:

- `pytest tests/runtime/test_config_loader.py -q`: `41 passed`
- `pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q`: `19 passed`
- `pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: `54 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/tools/test_combined_tools_acceptance.py -q`: `8 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Slice 1 code review focus:

- Verify whether implementing Fins relative `workspace_root` effective resolution in `dayu/service/host_assembly.py` is an acceptable Slice 1 dependency needed to keep Service discovery callable after packaged `"workspace/"`, or a scope overrun that must be split / adjusted before acceptance.
- Verify whether updating `utils/diagnose_web_access.py` is an acceptable signature-update fallout from `ToolsDiscoveryProviderSpec.allow_empty` removal, despite `utils/` not being part of production/test allowed files in the original dispatch.
- Verify packaged `financial-upload-tools.enabled=false` is acceptable as a temporary Slice 1 bridge until the later upload provider slice removes `allowed_upload_roots` behavior and restores intended default registration.

Slice 1 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice1-code-review-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice1-code-review-ds.md` by AgentDS, verdict `pass-with-findings`, blocking findings `0`

Controller Slice 1 code-review judgment:

- `accepted`：DS-F01 — `_effective_fins_workspace_root_config_value()` 的非字符串、空字符串 / 全空白字符串、相对路径但缺少 runtime `workspace_root` 三条错误边界应由直接测试锁定。Controller 已在 `tests/service/test_host_assembly.py` 补测试并关闭。
- `rejected-with-reason`：DS-F02 — `workspace_root: null` 且 runtime `workspace_root=None` 时保留原始 config、由 provider / wait adapter fail fast 是 accepted plan 的有意决策，不作为 Slice 1 缺陷。
- `deferred-with-owner`：DS-F03 — packaged `financial-upload-tools.enabled=false` 是 Slice 1 临时桥接，owner 为本 WU Slice 4；Slice 4 必须移除 upload provider 内部 `allowed_upload_roots` 行为并恢复默认注册。
- `informational`：DS-F04 — `dict()` 浅复制与 frozen dataclass `replace(...)` 行为正确，已有测试覆盖原始 config 未被修改。
- `informational`：DS-F05 — `utils/diagnose_web_access.py` 修改是 `ToolsDiscoveryProviderSpec.allow_empty` 构造参数删除后的签名 fallout，可接受。
- `accepted`：MiMo review — 无实质性问题；Slice 1 可进入 accepted slice commit gate。

Slice 1 code-review fix validation:

- `pytest tests/service/test_host_assembly.py -q`: `51 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Accepted Slice 1 commit:

- `c785f218` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 1`)

Slice 2 controller closure:

- `closed-covered-by-slice-1`：Accepted Slice 1 commit `c785f218` already implemented Service effective Fins workspace path resolution, `_effective_fins_workspace_root_config_value(...)`, wait adapter construction through the same effective provider config tuple, packaged `"workspace/"` resolution tests, raw config immutability tests, and direct error-boundary tests. No separate Slice 2 implementation dispatch is needed; next implementation slice is Slice 3.

Slice 3 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice3-implementation-codex.md` by AgentCodex

Slice 3 implementation validation:

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`: `77 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `rg -n "include_read_tools|_CONFIG_INCLUDE_READ_TOOLS_FIELD|_parse_bool_default" -g '*.py' dayu tests utils`: no production or test Python references

Slice 3 code review focus:

- Verify `dayu/fins/tools/provider.py` no longer has any internal read-provider disable path and enabled provider always requires explicit absolute `workspace_root`, parses limits, builds `DefaultFinsRuntime`, and returns exactly nine read tool definitions.
- Verify deleting the explicit `tests/runtime/test_config_loader.py` string assertion for `include_read_tools` is acceptable because Slice 3 completion requires no production or test code references to that removed field, while Slice 1 already asserted packaged config cleanup.
- Verify minimal updates to `dayu/fins/README.md` and `tests/README.md` are required by AGENTS README triggers and are not an uncontrolled docs-slice overrun; stale `dayu/config/README.md` content remains intentionally deferred to the later docs slice.
- Verify remaining `include_read_tools` grep hits are only historical plans/review artifacts, current WU control/plan text, or deferred docs content; no active production/test Python path still consumes the field.

Slice 3 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice3-code-review-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice3-code-review-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Controller Slice 3 code-review judgment:

- `accepted`：AgentMiMo and AgentDS both confirmed the read provider no longer has an `include_read_tools` branch, enabled provider parses limits / absolute workspace root, creates `DefaultFinsRuntime`, validates definitions, and returns exactly nine read tools.
- `accepted`：Deleting the explicit `tests/runtime/test_config_loader.py` string assertion for `include_read_tools` is acceptable. Slice 1 already covered packaged config cleanup, and Slice 3 completion requires no production/test Python references to the removed field.
- `accepted`：Minimal `dayu/fins/README.md` and `tests/README.md` updates are required by AGENTS README triggers and directly match the changed Fins read provider semantics.
- `deferred-with-owner`：`dayu/config/README.md` still contains old config text; owner is WU-TOOLS-01-F03-R4 Slice 6 docs synchronization.
- `deferred-with-owner`：DS noted non-string / blank-string `workspace_root` provider parse boundaries are not directly tested; existing guard covers them and severity is low. Owner is Slice 7 final validation if broader provider parse boundary hardening is still needed.

Slice 3 controller validation:

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py tests/runtime/test_config_loader.py -q`: `118 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Accepted Slice 3 commit:

- `3f7fd44a` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 3`)

Slice 4 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice4-implementation-codex.md` by AgentCodex

Slice 4 implementation validation:

- `pytest tests/fins/test_fins_ingestion_tools.py -q`: `47 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: `38 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/tools/test_combined_tools_acceptance.py -q`: `8 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_config_loader.py -q`: `41 passed`
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: no output
- `rg -n "allowed_upload_roots|_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD|parse_allowed_upload_roots_config" dayu tests utils`: only expected negative assertion in `tests/runtime/test_config_loader.py`

Slice 4 code review focus:

- Verify `dayu/fins/tools/upload_provider.py` no longer has an empty-output branch or `allowed_upload_roots` parser and always registers `start_fins_upload` after parsing absolute effective `workspace_root`.
- Verify `dayu/fins/tools/upload_tools.py` removed allowlist containment but still validates action/file count, existing regular file, and non-empty file before starting observation; delete still forbids files.
- Verify repository/write boundary was not weakened: local file path is source input only, output path remains governed by `FinsIngestionRuntime` / repository-backed runtime; new tests should not rely on obsolete job-store internals.
- Verify packaged `financial-upload-tools.enabled=true` is correct after removing provider allowlist behavior and no `allowed_upload_roots` returns to config.
- Verify default manifests no longer select `start_fins_upload` via broad `"fins"` / `"ingestion"` tags, while intended read/download/preprocess and web tools remain selected. Scene `tool_selection.allow_empty` must remain unchanged.
- Verify LLM-facing upload schema text no longer claims configured upload roots and remains self-explanatory.
- Verify README updates are minimal direct-trigger sync, not uncontrolled docs-slice overrun.

Slice 4 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice4-code-review-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice4-code-review-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Controller Slice 4 code-review judgment:

- `accepted`：AgentMiMo and AgentDS both confirmed upload provider no longer parses `allowed_upload_roots`, no longer has an empty-output branch, and enabled provider registers `start_fins_upload` after valid absolute effective `workspace_root`.
- `accepted`：Upload tool no longer applies provider-local allowlist containment, but still validates action/file count, existing regular file, non-empty file, and delete-with-files before observation start.
- `accepted`：Packaged `financial-upload-tools.enabled=true` is correct after removing the temporary Slice 1 bridge; packaged upload config still has no `allowed_upload_roots`.
- `accepted`：Default manifests no longer select upload through broad `"fins"` / `"ingestion"` tags, and `tool_selection.allow_empty` remains unchanged.
- `accepted`：LLM-facing upload schema text no longer mentions configured upload roots and remains self-explanatory.
- `accepted`：README updates are AGENTS-triggered minimal factual sync for changed config / Fins / tests behavior.
- `deferred-with-owner`：DS-F1 symlink path behavior has no direct test. Current implementation follows symlinks through `Path.resolve(...)`, which is acceptable. Owner is Slice 7 final validation / future provider path-boundary hardening if needed.
- `deferred-with-owner`：DS-F2 scene test uses a hardcoded default scene id list. Current package manifests are covered and grep-confirmed; owner is Slice 7 final validation if dynamic manifest discovery becomes necessary.
- `rejected-with-reason`：DS-F3 asks for deeper repository write-boundary penetration in the new source-side upload test. This is not a Slice 4 defect: the test intentionally proves local source path acceptance/no source-side governance side effects, while destination repository writes remain covered by existing Fins upload pipeline / storage tests.

Slice 4 controller validation:

- `pytest tests/fins/test_fins_ingestion_tools.py tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/tools/test_combined_tools_acceptance.py tests/runtime/test_config_loader.py -q`: `134 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `rg -n "allowed_upload_roots|_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD|parse_allowed_upload_roots_config" dayu tests utils`: only `tests/runtime/test_config_loader.py` negative assertion
- `rg -n '"fins"|fins-upload|"ingestion"|start_fins_upload' dayu/config/prompts/manifests`: no matches

Accepted Slice 4 commit:

- `4514f550` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 4`)

Slice 5 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice5-implementation-codex.md` by AgentCodex

Slice 5 implementation validation:

- `pytest tests/runtime/test_config_loader.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py -q`: `97 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/tools/test_combined_tools_acceptance.py -q`: `8 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Slice 5 code review focus:

- Verify enabled Doc provider with missing or empty `allowed_paths` raises the Doc-specific `ValueError` at provider boundary and no longer returns empty `definitions`.
- Verify Doc provider limits parsing remains provider-owned, ConfigLoader does not parse provider-specific limits, and packaged config values remain explicitly asserted.
- Verify new Doc explicit limits test actually checks schema maximums and truncate specs produced from config, not dataclass defaults.
- Verify new Fins explicit limits test checks all ToolDefinition-visible limits and correctly treats `processor_cache_max_entries` as runtime cache input that is not visible in `ToolDefinition`.
- Verify README update is minimal tests README sync and not a docs/design Slice 6 overrun.

Slice 5 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-mimo.md` by AgentMiMo, verdict `accept-with-conditions`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Controller Slice 5 code-review judgment:

- `accepted`：MiMo F1 — Fins explicit limits test should assert `processor_cache_max_entries` is not projected into any ToolDefinition truncate limits. This directly matches Slice 5 focus on treating that field as runtime-only.
- `accepted`：MiMo F2 — Partial limits fallback to dataclass defaults is a plan invariant and should have a focused test. Low risk but cheap to cover in the same fix.
- `accepted`：DS review — no blocking findings; DS residual risks are informational and consistent with the accepted fix items.

Slice 5 fix artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice5-fix-codex.md` by AgentCodex

Slice 5 fix validation:

- `pytest tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py -q`: `57 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py -q`: `49 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Slice 5 fix re-review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice5-fix-rereview-mimo.md` by AgentMiMo, verdict `accept`, F1 closed, F2 closed
- `docs/reviews/wu-tools-01-f03-r4-slice5-fix-rereview-ds.md` by AgentDS, verdict `pass`, F1 closed, F2 closed

Controller Slice 5 final judgment:

- `closed`：MiMo F1 — fixed by asserting `processor_cache_max_entries` is absent from every Fins ToolDefinition `truncate.limits` while preserving all visible limit assertions.
- `closed`：MiMo F2 — fixed by adding partial Doc limits fallback coverage: explicit `list_files_max=99` overrides default, missing visible Doc limits fall back to `DocToolLimits()` defaults.
- `accepted`：No production code was changed by the fix; review agents found no regressions.

Slice 5 controller validation:

- `pytest tests/runtime/test_config_loader.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py -q`: `106 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Accepted Slice 5 commit:

- `ee5f2e19` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 5`)

Slice 6 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice6-implementation-codex.md` by AgentCodex

Slice 6 implementation validation:

- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`
- `git diff --check -- dayu/config/README.md dayu/fins/README.md docs/host/design.md tests/README.md docs/reviews/wu-tools-01-f03-r4-slice6-implementation-codex.md`: no output
- Active README/design grep: remaining `allow_empty` hits are scene `tool_selection.allow_empty` independent semantics or old provider-level field rejection tests; `include_read_tools` and `allowed_upload_roots` no longer appear as current active config.

Slice 6 code review focus:

- Verify `docs/host/design.md` no longer describes provider-level `allow_empty` as current `tool_discovery.json` field and accurately states enabled provider empty output is configuration error.
- Verify `dayu/config/README.md` documents packaged `workspace/` relative default, Service effective absolute resolution, explicit Doc/Fins limits, `doc-tools.enabled=false`, no `include_read_tools`, no upload `allowed_upload_roots`, and scene selection avoiding broad Fins tag upload exposure.
- Verify `dayu/fins/README.md` describes all four Fins providers requiring effective absolute `workspace_root`, provider-level `enabled` as read switch, upload local source file authorization not being provider-owned, and repository writes staying under `dayu.fins.storage`.
- Verify `tests/README.md` coverage descriptions match current tests and do not describe old allowlist / empty-output behavior as current.
- Verify no README/design process/gate/PR status leaked into stable docs.

Slice 6 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice6-code-review-mimo.md` by AgentMiMo, verdict `accept`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice6-code-review-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Controller Slice 6 code-review judgment:

- `accepted`：Design and README text now match implemented facts for provider fields, empty provider output, Fins `workspace/` effective resolution, Doc/Fins limits, `doc-tools.enabled=false`, upload allowlist removal, and scene selection separation.
- `accepted`：Remaining active `allow_empty` mentions are scene `tool_selection.allow_empty` independent semantics or old provider-level field rejection test coverage. `include_read_tools` and `allowed_upload_roots` are absent from active current README/design descriptions.
- `accepted`：No process/gate/PR status leaked into stable README/design documents.

Slice 6 controller validation:

- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `git diff --check` on Slice 6 docs/review files: no output
- Active docs grep for `allow_empty|include_read_tools|allowed_upload_roots`: remaining matches are allowed scene/test-rejection classifications only.

Accepted Slice 6 commit:

- `d8db0b49` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 6`)

Slice 7 final validation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice7-final-validation-codex.md` by AgentCodex

Slice 7 final validation changes:

- `tests/runtime/test_scene_assets_migration.py` fake tool catalog updated to include the current explicit default-scene Fins read / download / preprocess tool names after Slice 4 removed broad `"fins"` / `"ingestion"` default selection.

Slice 7 final validation:

- `pytest tests/runtime/test_config_loader.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q`: `60 passed`
- `pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: `58 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py -q`: `70 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_scene_prepare.py -q`: `31 passed`
- `pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q`: `42 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_scene_assets_migration.py -q`: `7 passed`
- `pytest tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q`: `1 passed`
- `pytest tests/runtime tests/service tests/fins tests/tools -q --ignore=tests/tools/web/test_smoke_web_ci.py`: `866 passed, 1 skipped, 3 upstream edgar deprecation warnings`
- Historical `pytest tests/tools/web -q` result before web smoke reconciliation: `75 passed, 1 failed, 3 upstream edgar deprecation warnings`; failing test was `tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases`, where the test asserted diagnostic log text in stdout instead of pytest captured log.
- Post-reconciliation `python utils/smoke_web_ci.py --output-dir workspace/output/web_smoke/manual-wu-tools-f03-r4-final --run-label manual-wu-tools-f03-r4-final`: `SMOKE STATUS passed`, `SMOKE EXIT_CODE 0`, `SMOKE FAILURES 0`.
- Post-reconciliation `pytest tests/tools/web -q`: `76 passed, 3 upstream edgar deprecation warnings`.
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `rg -n "include_read_tools|allowed_upload_roots" dayu tests README.md`: only `allowed_upload_roots` hit is the packaged config negative assertion in `tests/runtime/test_config_loader.py`; `include_read_tools` has no active production/test/README hits.
- `rg -n "workspace_root\": null" dayu/config/tool_discovery.json tests`: no matches.
- `rg -n "\"allow_empty\"|allow_empty" dayu/config dayu/runtime dayu/service dayu/fins dayu/tools tests README.md`: remaining hits are scene `tool_selection.allow_empty`, runtime internal `ToolBundle._allow_empty`, direct event string validation, and old provider-level field rejection tests / documentation.

Slice 7 residual risk:

- No active WU-TOOLS-01-F03-R4 residual risk remains after reconciliation. Fresh web smoke passed after removing the obsolete smoke overlay `allow_empty` field, and the web smoke test now asserts diagnostic logs through pytest log capture instead of stdout.

Aggregate deepreview artifacts:

- `docs/reviews/wu-tools-01-f03-r4-aggregate-deepreview-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-aggregate-deepreview-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Aggregate deepreview validation:

- AgentMiMo reran focused tests, broad affected suite excluding the then-classified web smoke caveat, pyright, and stale-field grep; result `pass`.
- AgentDS reran focused tests, web smoke caveat confirmation, broad affected suite excluding the then-classified web smoke caveat, pyright, stale-field grep, and scene manifest grep; result `pass`.

Controller aggregate deepreview judgment:

- `accepted`：AgentMiMo found no substantive issues and confirmed all seven WU success dimensions: provider-level `allow_empty` removal, `include_read_tools` removal, Fins `workspace/` effective resolution, Doc/Fins packaged limits, upload `allowed_upload_roots` removal, default scene upload non-exposure, and docs/tests/control semantic consistency.
- `rejected-with-reason`：AgentDS F-01 notes `ToolBundle._allow_empty=True` has insufficient semantic distinction. This is not a current defect: `_allow_empty=True` is only used to construct the legitimate zero-enabled-provider empty bundle, while enabled provider output still passes `_validate_provider_output(...)` and cannot return empty definitions. No code change is warranted in this WU.
- `rejected-with-reason`：AgentDS F-02 notes double `enabled` filtering in `ToolsDiscovery.discover(...)` and `discover_from_bindings(...)`. This is an intentional defensive boundary for the public `discover_from_bindings(...)` method and does not create incorrect behavior or maintenance risk requiring a fix.
- `accepted`：No active WU-TOOLS-01-F03-R4 residual risk remains after residual reconciliation.

Accepted deepreview commit:

- `3463ae9d` (`gateflow: accept deepreview for WU-TOOLS-01-F03-R4`)

Draft PR readiness artifact:

- `docs/reviews/wu-tools-01-f03-r4-draft-pr-readiness-codex.md` by AgentCodex

Draft PR readiness decision:

- Branch `phase/wu-tools-01-f03-r4` contains only WU-TOOLS-01-F03-R4 gate commits from `fe212365` through `3463ae9d`.
- All approved slices and aggregate deepreview are complete; no accepted finding requires fix / re-review.
- Validation is recorded: focused WU suites passed, `pyright dayu tests utils` passed, broad affected suite excluding the historical web smoke caveat passed, and post-reconciliation `tests/tools/web` plus fresh web smoke passed.
- No active WU-TOOLS-01-F03-R4 residual risk remains after residual reconciliation.
- GitHub issue-133 is CLOSED after PR 160 merged on 2026-06-21. The six requested Tools Discovery spec items were implemented, tested, and documented; the PR body used `Closes #133` and listed deferred owners.

Draft PR:

- PR 160: `https://github.com/noho/dayu-agent-r/pull/160`
- Branch pushed: `github/phase/wu-tools-01-f03-r4`
- Base: `main`
- Draft status: draft
- Issue association: PR body uses `Closes #133` and lists deferred owners.

PR review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-pr-review-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-pr-review-ds.md` by AgentDS, verdict `pass-with-findings`, blocking findings `0`

Controller PR review judgment:

- `accepted`：AgentMiMo verified PR 160 metadata, body, issue-133 completion, residual owners, diff scope, validation claims, and stale-field grep; no issues found.
- `rejected-with-reason`：AgentDS F01 notes `start_fins_upload.files` description no longer carries path authorization semantics. This is not a current defect. The accepted design deliberately removed provider-local upload allowlists, and the current tool schema truthfully states the active tool boundary: files must be existing non-empty regular files. Adding generic "system administrator controls allowed directories" wording before Host / policy owns a concrete contract would create an implicit rule with no enforcement source.
- `accepted`：PR body `Closes #133` is correct because all six issue-133 requested Tools Discovery spec changes are implemented, tested, and documented. Deferred risks are separately owned and do not leave issue-133 partially implemented.
- `accepted`：No active WU-TOOLS-01-F03-R4 residual risk remains after residual reconciliation; the historical web smoke caveat has been rechecked and fixed by aligning the smoke overlay and test assertions with current logging/config semantics.
- `accepted`：User-requested process improvement was written into the Slice 切分原则 section: small cross-module cleanup work should default to 2-3 semantic slices and any plan exceeding 3 implementation slices must justify why the work cannot be merged into those verification loops.

Accepted PR review commit and final push:

- `ecf83c5f` (`gateflow: accept PR review for WU-TOOLS-01-F03-R4`)
- Pushed to `github/phase/wu-tools-01-f03-r4`; PR 160 head after PR review pass was `ecf83c5f13d4b74d7f58f120c46bac3fa389c64f`.

Final closeout artifact:

- `docs/reviews/wu-tools-01-f03-r4-final-closeout-codex.md` by AgentCodex

Final closeout status:

- Draft PR URL: `https://github.com/noho/dayu-agent-r/pull/160`
- Issue link status: PR body uses `Closes #133`, correctly closing issue-133 on merge because all six requested spec changes are complete.
- Issue closeout comment status: posted to GitHub issue-133 at `https://github.com/noho/dayu-agent-r/issues/133#issuecomment-4760536817`.
- Work unit completion status: completed; PR 160 merged on 2026-06-21 and issue #133 is closed.

当前裁决来自 controller 对 `docs/host/design.md`、`docs/engine/design.md`、`dayu/config/tool_discovery.json`、`dayu/runtime/tools_discovery.py`、`dayu/runtime/config_loader.py`、`dayu/service/host_assembly.py`、Fins / Doc provider、Fins upload tool、Fins storage repository 与 OLD `/Users/leo/workspace/dayu-agent` 配置的代码核对。

### 目标

- 收敛 Tools Discovery spec 语义，删除 provider-level `allow_empty` 字段。空工具输出不再由通用 runtime 布尔开关授权；provider 是否启用由 `enabled` 表达，provider 自身业务配置必须直接决定是否暴露工具或 fail fast。
- 删除 Fins read provider 的 `include_read_tools` 字段。`financial-read-tools` 是独立 provider，启停必须只通过 provider-level `enabled` 表达，不保留 provider 内二级开关。
- 将 Fins workspace root packaged 默认值从 `null` 改为显式 `workspace/`。ConfigLoader 只原样读取配置；Service / composition root 负责把相对 workspace path 解析为 effective absolute path；Fins provider 继续只接收 absolute path，不自行猜 cwd、环境变量或 workspace。
- 将 OLD `doc_tool_limits` 与 `fins_tool_limits` 的默认值迁移到 `dayu/config/tool_discovery.json` 的 `doc-tools.config.limits` 与 `financial-read-tools.config.limits`，让 packaged config 自解释；provider dataclass 默认值只能作为代码层 fallback / 测试构造便利，不作为 packaged 默认配置唯一真源。
- 删除 `financial-upload-tools.config.allowed_upload_roots` 与上传工具本地文件 allowlist 限制。当前裁决为：本地文件读取暂不由 tool provider 自行授权或限制，未来权限治理统一进入 Host / policy 设计，不在工具内部保留一套并行 allowlist。
- 保持 Fins repository 写入目标边界：上传写入仍必须通过 `dayu.fins.storage` 仓储协议和 repository implementation；LLM / tool caller 不得指定仓储写入目录或绕过 repository。
- 同步更新相关测试、README 和设计 / 总控文档，使默认配置、typed config、Service effective config、provider 行为和文档语义一致。

### 非目标

- 不实现 Host 统一权限系统、文件访问策略、sandbox、capability token 或 per-tool authorization policy；upload 本地文件读取权限治理只作为后续 Host / policy 方向记录，不在本 WU 落地。
- 不把工具发现、业务工具注册、provider lifecycle 或 Fins workspace 推断放进 Host / Engine。Host / Engine 仍不读取 `tool_discovery.json`，不 import Fins / Doc / Web provider。
- 不保留旧 schema 兼容读取；本 WU 按全新 `tool_discovery.json` schema 起库处理，除非后续用户明确要求兼容迁移。
- 不修改 scene manifest 的 `tool_selection.allow_empty` 语义；该字段属于 scene 工具选择空匹配控制，不是 ToolsDiscovery provider 空输出控制。
- 不改变 Host public request / response dataclass、Engine `AgentRunRequest`、ToolRuntime callable dispatch 或 framework tool 注入契约。
- 不实现 SEC/Fins CI pipeline、CN/HK Docling CI pipeline、Web smoke 扩展或 Issue #121 / #122 范围。
- 不重新设计 upload ingestion workflow、Docling upload conversion、Fins repository schema 或 DocumentRepository 存储布局。

### 直接代码证据

- `dayu/runtime/tools_discovery.py` 当前用 `ToolsDiscoveryProviderSpec.allow_empty` 判断 provider 空输出是否允许通过。
- `dayu/config/tool_discovery.json` 当前所有 packaged providers 均携带 `allow_empty`，Fins providers 的 `workspace_root` 仍为 `null`，`financial-read-tools` 仍携带 `include_read_tools`，Doc / Fins read limits 仍为空 object，upload provider 仍携带 `allowed_upload_roots`。
- `dayu/fins/tools/provider.py` 当前在 `include_read_tools=false` 时返回空工具集并跳过 `workspace_root` 解析；这与独立 `financial-read-tools.enabled` 职责重复。
- `dayu/service/host_assembly.py` 当前只在 raw config `workspace_root is None` 且调用方传入 runtime workspace root 时注入 absolute path；改为 packaged `workspace/` 后需要明确相对 path effective resolution。
- OLD `/Users/leo/workspace/dayu-agent/dayu/config/run.json` 中 `doc_tool_limits` 与 `fins_tool_limits` 已给出默认业务 limits，当前 dataclass 默认值与其基本一致，但 packaged config 未显式承载。
- `dayu/fins/tools/upload_provider.py` 当前用 `allowed_upload_roots=[]` 返回空工具集；`dayu/fins/tools/upload_tools.py` 当前用 allowlist 校验工具参数中的本地 `files` 路径；`dayu.fins.storage` repository 写入仍由 `SourceHandle` / `ProcessedHandle` 与 filename 派生目标，不允许调用方指定任意仓储写入目录。

### 成功信号

- Packaged `tool_discovery.json` 不再包含 provider-level `allow_empty`、Fins read `include_read_tools` 或 upload `allowed_upload_roots`。
- ConfigLoader typed view、ToolsDiscovery provider spec、Service assembly 和 provider tests 均对新 schema 通过；旧字段在当前 schema 下 fail fast 或不再被接受。
- Fins workspace relative default `workspace/` 能通过 Service effective assembly 解析为 absolute path，并被 Fins read / download / preprocess / upload provider 一致消费。
- Fins read / Doc limits 在 packaged config 中显式出现，测试覆盖它们进入 tool definitions / truncate specs。
- Upload provider 不再因空 allowlist 返回空工具集；上传工具不再拒绝 allowlist 外本地路径，但仍校验文件存在、普通文件、非空与上传动作约束，并继续通过 Fins repository 写入。
- `pytest` 覆盖受影响 runtime / service / tools / fins 测试，`pyright dayu tests utils` 无新增或扩散错误。

### Gate 入口

Plan gate 交给 AgentCodex，计划 artifact 应写入 `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`，并明确 implementation slices、allowed files、测试命令、README 更新决策和 residual risks。

## WU-ENG-02-R1 Provider Debugging Correlation Default Enablement And Fallback Diagnostics

### 状态

GitHub Issue #63 reopened on 2026-06-20 and was closed after PR 159 merged on 2026-06-20. Reopen comment:
https://github.com/noho/dayu-agent-r/issues/63#issuecomment-4756101567

本 WU 是 WU-ENG-02 / PR 114 的 reopened follow-up。WU-ENG-02 已完成 lower-level typed `RunnerRequestIdentity`、`ClientCorrelationPolicy`、OpenAI-compatible `X-Client-Request-Id` 映射能力、provider `x-request-id` 采集、Host ingest 与 Tool Trace 投影；reopen comment 指出真实 Service / CLI 默认路径没有启用该能力。本 WU 已通过 PR 159 修复默认启用路径，当前已完成，不再作为 active WU。

当前 gate 是 `completed`。Goal confirmation、plan gate、plan review、plan-fix、plan re-review、accepted plan commit、implementation、code review、code-review fix、code re-review、accepted slice commit、aggregate deepreview、accepted deepreview commit、push、create draft PR、PR review、accepted PR review commit、follow-up push、draft-PR-pass、final closeout 和 PR merge 已完成。

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
- PR state after user disposition: merged on 2026-06-20.
- Branch: `phase/wu-eng-02-r1`
- Branch head before final closeout record: `d96dcb65`
- GitHub checks at closeout: none reported on branch.
- Issue closeout handling: PR body contained `Closes #63`; Issue #63 closed after PR 159 merged.
- Validation retained from accepted slice / PR body: assembly 53 passed, runner 38 passed, Host terminal / Tool Trace 51 passed, Service / CLI 69 passed, pyright 0 errors, `git diff --check` passed.
- Remaining risks: no blocking risks. Non-blocking deferred risk remains limited to future WU changes that make lost/cancelled lifecycle payloads carry provider/client correlation ids; that future WU must re-check terminal projection suffix behavior.
- Post-closeout user-requested PR update: OpenAI-compatible Runner `runner.http.response` log now labels the protocol fields as `x-request-id` and `X-Client-Request-Id` instead of semantic internal field names, preserving the same log site, same log level, and same log line. Validation: OpenAI runner focused tests 22 passed, pyright 0 errors, `git diff --check` passed.
- Post-closeout user-requested PR update: OpenAI-compatible Runner now maps DeepSeek `x-ds-trace-id` into `provider_request_id` when standard `x-request-id` is absent. The existing response DEBUG line logs only present provider request id headers, falls back to `x-request-id=None` when none exist, and continues logging `X-Client-Request-Id` without dumping full response headers. Validation: OpenAI runner focused tests 23 passed, pyright 0 errors, `git diff --check` passed.

Controller plan-review judgment:

- `accepted`：终端诊断可见性不能留给 implementation agent 二选一；plan 必须收敛到最小 public contract 变更方案，在 Host public projection 边界追加 bounded diagnostic suffix，不修改 durable terminal payload message / payload digest。
- `accepted`：live watcher 与 outbox fallback 是两条独立 projection path；plan 必须要求共享同一 suffix formatting helper，并测试两条路径在 `provider_request_id=None` 且 `client_correlation_id` 存在时输出一致 fallback id。
- `accepted`：用户明确要求 log 中可见，因此 Python runner log 可见性是当前 WU 验收项；plan 必须去掉 escape hatch，要求在既有 `runner.http.response` log site 和既有 log level 上携带 `client_correlation_id`，不新增日志点、日志行或日志等级。
- `accepted`：provider request id header allowlist 缺少当前 issue 直接证据；plan 必须保持当前 `x-request-id` 提取，不把 `x-trace-id`、`x-correlation-id`、`cf-ray` 等 tracing / infrastructure header 伪装为 provider request id。若需要 header diagnostic，只能记录有界安全 header name presence，不输出 header values。
- `accepted`：Tool Trace `diagnostic_ref=None` 当前 validation 允许；plan 必须删除“可能需要 event_id fallback”的过度设计风险，明确不伪造 provider request id 或 diagnostic ref。
- `accepted`：Slice 1 实施前需要基线验证受影响 assembly tests，再区分期望行为变化和 regression。

### Reopen 直接证据

- GitHub Issue #63 曾在 2026-06-20 进入 `OPEN / REOPENED`，PR 159 merge 后当前已关闭。
- Reopen comment 明确：PR 114 已实现底层机制，但当时真实 CLI 路径未启用；reopen-time 代码中 `dayu/service/host_assembly.py` 把 `RunnerSpec.client_correlation_policy` 固定为 `ClientCorrelationPolicy.DISABLED`。
- Reopen-time 本地代码核对确认：`dayu/service/host_assembly.py` 的 `_runner_spec_from_model(...)` 返回 `RunnerSpec(..., client_correlation_policy=ClientCorrelationPolicy.DISABLED, ...)`。
- 因此 reopen-time 的 `dayu-cli prompt` 等默认 Service assembly 路径不会向 OpenAI-compatible / mimo-v2.5-pro 发送 `X-Client-Request-Id`；PR 159 已修复该默认路径。
- Reopen comment 记录实际日志中 `provider_request_id=None`，说明 mimo response 没有通过当时的 `x-request-id` 采集路径给出厂商侧 request id；同时因为 client correlation 默认未发送，也没有可提供给 vendor debugging 的 fallback request-level id。PR 159 关闭了默认 client correlation 未发送的问题，后续 provider-native header coverage 仍按 provider-specific WU 裁决。

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

## WU-LIFE-03 Active Cancel Watchdog And Post-cancel Timeout

### 状态

已纳入 GitHub Issue #91；GitHub Issue #87 是 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 active Attempt cancel watchdog target，不单独引入第二套 watchdog runtime。PR #166 已于 2026-07-04 merge，GitHub Issue #92 已自动关闭，本条已进入当前 implementation entry point。Goal confirmation 已由用户确认。Plan artifact 为 `docs/host/wu-life-03-active-cancel-watchdog-plan.md`，plan decision 为 ready。Plan review artifacts 为 `docs/reviews/plan-review-20260704-105429.md` 与 `docs/reviews/plan-review-20260704-105503.md`；controller adjudication 为 `docs/reviews/wu-life-03-plan-review-controller-adjudication.md`。Controller accepted recovery scanner / watchdog ordering, late terminal race, watchdog scheduling, clock policy, diagnostic payload mapping, projection compatibility, and scan strategy findings。Plan fix artifact 为 `docs/reviews/wu-life-03-plan-fix-codex.md`；AgentCodex reported all accepted findings fixed and `git diff --check` passed。Plan re-review artifacts 为 `docs/reviews/plan-review-20260704-110623.md` 与 `docs/reviews/plan-review-20260704-110719.md`；controller adjudication 为 `docs/reviews/wu-life-03-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，F01-F07 均已修复，无 blocking open question。Accepted plan commit 为 `50d34e52`。Slice 1 implementation artifact 为 `docs/reviews/wu-life-03-slice1-implementation-codex.md`；AgentCodex reported focused tests 122 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 122 passed, pyright 0 errors, and `git diff --check` passed. Slice 1 code review artifacts 为 `docs/reviews/code-review-20260704-112548.md` 与 `docs/reviews/code-review-20260704-112608.md`；controller adjudication 为 `docs/reviews/wu-life-03-slice1-code-review-controller-adjudication.md`。Controller accepted parser reuse, timestamp normalization, optional diagnostic payload test, malformed payload test, and timeout self-replay test findings。Slice 1 fix artifact 为 `docs/reviews/wu-life-03-slice1-fix-codex.md`；AgentCodex reported all accepted findings fixed, focused tests 123 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 123 passed, pyright 0 errors, and `git diff --check` passed. Slice 1 code re-review artifacts 为 `docs/reviews/code-review-20260704-113656.md` 与 `docs/reviews/code-review-20260704-113657.md`；controller adjudication 为 `docs/reviews/wu-life-03-slice1-code-rereview-controller-adjudication.md`。两路 re-review 均通过，S1-CR-F01 / F02 / F03 / F04 / F05 均已关闭，无 blocking open question。Accepted Slice 1 commit 为 `ef2d3644`。Slice 2 implementation artifact 为 `docs/reviews/wu-life-03-slice2-implementation-codex.md`；AgentCodex reported lifecycle watchdog focused tests 140 passed, transition / ingest regression tests 123 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 140 passed and 123 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code review artifacts 为 `docs/reviews/wu-life-03-slice2-code-review-mimo.md` 与 `docs/reviews/wu-life-03-slice2-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-life-03-slice2-code-review-controller-adjudication.md`。Controller accepted malformed `RUN_CANCELLING` recovery payload handling and watchdog loop transient exception resilience as current fixes；Protocol location and overlapping precondition notes are non-blocking. Slice 2 fix artifact 为 `docs/reviews/wu-life-03-slice2-fix-codex.md`；AgentCodex reported lifecycle watchdog focused tests 142 passed, transition / ingest regression tests 123 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 142 passed and 123 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code re-review artifacts 为 `docs/reviews/wu-life-03-slice2-code-rereview-mimo.md` 与 `docs/reviews/wu-life-03-slice2-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-life-03-slice2-code-rereview-controller-adjudication.md`。两路 re-review 均通过，S2-CR-F01 / S2-CR-F02 均已关闭，无新增 material defect。Accepted Slice 2 commit 为 `3ff42b15`。Aggregate deepreview artifacts 为 `docs/reviews/wu-life-03-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-life-03-aggregate-deepreview-ds.md`；controller adjudication 为 `docs/reviews/wu-life-03-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均通过，无 blocking finding；watchdog scan SQL optimization 已归属 #87 umbrella 后续 tuning（非 #91 / WU-LIFE-03 closeout blocker），provider/tool physical cleanup 已归属 WU-TOOLS-CANCEL-01，theoretical `payload_json=None` boundary 已裁决为 accepted risk。Accepted aggregate deepreview commit 为 `e42346d7`。Draft PR #167 已创建：https://github.com/noho/dayu-agent-r/pull/167。PR body 使用 `Closes #91`，merge 会自动关闭 #91；#87 仅作为 umbrella follow-up owner 保留。`gh pr checks 167` reported no checks on branch `phase/host-engine-next`。PR review artifacts 为 `docs/reviews/wu-life-03-pr-167-review-mimo.md` 与 `docs/reviews/wu-life-03-pr-167-review-ds.md`；controller adjudication 为 `docs/reviews/wu-life-03-pr-167-review-controller-adjudication.md`。两路 PR review 均通过，无 blocking finding；watchdog scan optimization 继续归属 #87 umbrella 后续 tuning，非当前 #91 blocker。Accepted PR review commit 为 `4f3d9d81`，并已 push 到 draft PR #167。Final closeout artifact 为 `docs/reviews/wu-life-03-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/91#issuecomment-4880685816。当前进入 final-closeout-pass，等待用户 / maintainer 处理 draft PR #167；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #167 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-LIFE-04。

### 目标

- 复用 #87 的 Host lifecycle watchdog / supervisor，不另建 active cancel 专属 watchdog。
- 裁决 active cancel watchdog owner、timeout policy、Run / Attempt 终态、diagnostic payload、late terminal race 与 session cancel replay 语义。
- 明确 post-cancel timeout 后 Run / Attempt / diagnostic 的收敛路径，以及 first-committer-wins / late rejection 规则。
- 保证 active cancel 被 Host 接受后，Host durable truth 不等待 worker / provider 配合；即使 worker stream 不结束、provider 不返回、worker task 不响应 token，也必须有可测试的 timeout closeout 或 diagnostic 收敛。
- 为 WU-TOOLS-CANCEL-01 提供稳定输入契约：哪些状态进入 timeout closeout、哪些迟到事件被接受 / 拒绝 / quarantine、哪些 diagnostic 字段用于定位不配合的 execution boundary。

### 非目标

- 不直接 kill 不属于 Host 管理的外部进程。
- 不把 provider-specific cancel API 硬编码进 Host 核心。
- 不把 scheduler close 设计成 active cancel timeout closeout。
- 不设计 tool/provider execution capsule、不定义 subprocess / process-group / sandbox kill 策略；这些归 WU-TOOLS-CANCEL-01。

### 验收信号

- provider 卡死、stream 不结束、worker task 不响应 cancellation 时，Host truth 都有可测试 closeout 或 diagnostic 收敛。
- terminal event 与 diagnostic 不重复、不互相矛盾。
- active cancel command replay、session-scope cancel replay 与 late terminal race 都符合 first-committer-wins。
- WU-TOOLS-CANCEL-01 可以直接消费本条输出的 timeout closeout / diagnostic contract，不需要重新裁决 Host terminal 语义。
- GitHub Issue #87 明确跟踪设计问题、非目标和验收测试；实施前需要先回到 design gate。

## WU-LIFE-04 Tool Execution Deadline And #87 Watchdog Closeout

### 状态

已纳入 GitHub Issue #168；GitHub Issue #87 是 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 的 umbrella closeout follow-up，当前为 WU-LIFE-03 merge 后的 pending-next implementation entry point，并且必须在 WU-TOOLS-CANCEL-01 之前完成。当前讨论已确认：`tool_execution_timeout_seconds` 是单次工具调用最长运行时间，任何取消 / 收口机制不得覆盖或延长单个 tool call 的原始 deadline。

### 目标

- 固定业务语义：`tool_execution_timeout_seconds` 是单次工具调用最长运行时间，配置真源继续是 `execution_profiles.json -> agent_policy.tool_execution_timeout_seconds`，不迁移到 `host_runtime.json`。
- 裁决 Host cancel watchdog 如何消费已有 execution deadlines；用户 Esc 取消不得重置、覆盖或延长正在运行 tool call 的原始 deadline。
- 避免引入第二套 active cancel timeout；若现有实现已暴露或默认化 `active_cancel_timeout_seconds`，本 WU 必须裁决移除、降级为内部过渡实现或改为 derived deadline 逻辑。
- 收敛 #87 shared supervisor 验收语义：接受共享 lifecycle governance 概念加 target-specific runtime，或要求抽取共享 supervisor runtime abstraction。
- 评估 active watchdog scan query optimization 是否进入本 WU，或转交更窄的 performance follow-up。
- 为 clock skew、diagnostics / audit hooks 和其他 #87 umbrella residual 指定明确 owner / destination。

### 非目标

- 不实现 tool/provider physical interruption、request abort、process-group termination 或 hard-kill；这些仍归 WU-TOOLS-CANCEL-01。
- 不修改 Engine awaiting 或 tool-calling public contract。
- 不新增 `active_cancel_timeout_seconds` 作为取消后的额外预算。
- 不把 `tool_execution_timeout_seconds` 放入 `host_runtime.json`；它属于 execution profile / Agent policy 执行策略。
- 不为了形式一致抽取 generic supervisor；只有直接正确性、可运维性或可维护性证据成立时才进入设计。

### Discussion Gate 约束

- 必须先确认 Host cancel watchdog 在 tool call 执行期如何取得并遵守本次 tool execution deadline，再决定是否修改设计真源、本文档、GitHub Issue 或进入 plan gate。
- 必须基于代码直接证据确认当前配置链路：`execution_profiles.json` 配置 `AgentPolicy.tool_execution_timeout_seconds`，并将其作为单次工具调用最长运行时间的业务真源。
- 必须明确本 WU 与 WU-TOOLS-CANCEL-01 的顺序关系；不得用本 WU 替代 tool/provider interrupt boundary。

## WU-TOOLS-CANCEL-01 Tool/provider Blocking I/O Cancellation Hardening

### 状态

等待 WU-LIFE-04 固定 tool execution deadline 与 Host watchdog closeout 边界后实施。本条是 tool/provider runtime 的实际 interrupt boundary 与 escalation 能力，不是 WU-WAIT-03 / GitHub Issue #92 residual，也不是 WU-WAIT-04 smoke。当前代码已有 Host cancellation token、部分工具 cooperative checkpoint、局部 Playwright process terminate / kill，但缺少通用 ToolRuntime / worker-owned interruptible capsule；本条必须补齐该通用边界，并不得延长 WU-LIFE-04 固定的单次工具执行 deadline。

### 目标

- 设计 Host-owned tool/provider execution interrupt boundary，使取消后 Host 能迅速回到可交互状态。
- 定义取消升级链路：cooperative cancellation token、request / stream abort、subprocess / process-group / sandbox termination、hard-kill diagnostic closeout。
- 固化旧 tool/provider 迟到结果的拒绝 / quarantine 语义，确保已取消 Run 不被旧结果污染。
- 为不配合的 blocking tool/provider 提供可测试 fixture，验证取消体感接近 Codex / Claude Code interrupt：用户取消后不继续输出旧执行结果，且新输入可继续推进。
- 明确哪些 tool/provider 必须进入 interruptible execution capsule；不可抢占的同进程 blocking I/O 不得作为 production-grade cancel path 的默认执行形态。
- 复用 WU-LIFE-03 的 Host terminal / diagnostic contract，不重新定义 Run / Attempt 终态。
- 消费 WU-LIFE-04 固定的 tool execution deadline contract；用户取消、执行中断、迟到结果 quarantine 或 hard-kill diagnostic 均不得延长单次工具调用的原始 `tool_execution_timeout_seconds` deadline。

### 非目标

- 不把 provider-specific kill / cancel API 硬编码进 Host 核心。
- 不承诺外部 provider 已接收的远端任务一定物理停止；若 provider 不支持 cancel API，本条只保证本地执行边界停止等待、迟到结果不污染 Host truth，并记录诊断。
- 不替代 WU-LIFE-03 的 Host-level timeout closeout；本条消费 WU-LIFE-03 的 Run / Attempt / diagnostic 语义。
- 不重新裁决 WU-LIFE-04 的 tool execution deadline 语义，也不引入取消后的第二套工具执行预算。
- 不重新实现 WU-WAIT-03 的 WAITING external job lifecycle contract。
- 不把“工具自愿检查 cancellation token”当作唯一 production 方案；cooperative checkpoint 只是升级链路第一层。

### 验收信号

- 至少一个不配合的 blocking tool/provider fixture 可被 cancel 后快速释放 Host 可交互路径。
- cancellation escalation 的每个阶段都有 typed diagnostic 或明确 terminal closeout。
- 被 hard interrupt 或迟到返回的 tool/provider 不得写入已取消 Run 的 terminal fact、final answer 或 accepted tool result。
- smoke 必须证明 cancel 后可以提交并推进新的用户输入；旧执行即使稍后返回也只能进入 diagnostic / quarantine。
- 对 subprocess / process-group / sandbox 型执行边界，测试覆盖 graceful interrupt、terminate 和 hard kill 至少两级升级。
- WU-WAIT-04 可把本条能力作为 production-grade awaiting smoke 的前置取消体验能力。

## WU-WAIT-01 Callback Endpoint / Auth / Replay

### 状态

GitHub Issue #89 当前为 OPEN。research 已写入 issue；本条后续按 callback adapter -> common `resolve_wait` pipeline 的方向实施。Claude Code 的 background subagent / lifecycle completion 行为可作为参考；Codex 具备 subagent orchestration，但公开 callback / hook surface 不应被假设为稳定生产 primitive。

2026-06-21 goal confirmation 已完成。PR #162 已 merge，本地 `main` 已包含 WU-TOOLS-01-F01-02-R1 two-phase activation 前置能力。代码核对显示 `resolve_wait` 已覆盖幂等重放、同 key 不同 outcome conflict、late result rejection、completed / failed / cancelled / lost outcome 和 poller 共用路径；`dayu/host/wait_adapter.py` 当前明确不实现 callback endpoint。Plan artifact 已创建：`docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`。Plan review artifacts 为 `docs/reviews/plan-review-20260621-220834.md` 与 `docs/reviews/plan-review-20260621-221033.md`；controller adjudication 为 `docs/reviews/wu-wait-01-plan-review-controller-adjudication.md`。Controller 接受全部 material findings。Plan fix artifact 为 `docs/reviews/wu-wait-01-plan-fix-codex.md`，记录 F01-F09 已全部修复。Plan re-review artifacts 为 `docs/reviews/plan-review-20260621-222106.md` 与 `docs/reviews/plan-review-20260621-222241.md`；controller adjudication 为 `docs/reviews/wu-wait-01-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，F01-F09 最终状态均为已修复。Accepted plan commit 为 `bf359ebb`。Slice 1 implementation artifact 为 `docs/reviews/wu-wait-01-slice1-implementation-codex.md`；AgentCodex reported `tests/host/test_wait_callback.py` 11 passed, focused Host wait callback / resolve / late-result / package-export / import-boundary tests 54 passed, pyright 0 errors, and `git diff --check` passed. Controller reran focused tests with 54 passed and pyright with 0 errors. Slice 1 code review artifacts 为 `docs/reviews/code-review-20260621-224502.md` 与 `docs/reviews/code-review-20260621-224440.md`；controller adjudication 为 `docs/reviews/wu-wait-01-slice1-code-review-controller-adjudication.md`。Controller accepted S1-CR-F01 digest material projection deduplication and S1-CR-F02 Host timestamp helper reuse; S1-CR-F03 is covered by S1-CR-F02. Fix artifact 为 `docs/reviews/wu-wait-01-slice1-fix-codex.md`；AgentCodex reported focused tests 56 passed, pyright 0 errors, and `git diff --check` passed. Controller reran focused tests with 56 passed, pyright with 0 errors, and `git diff --check` passed. Slice 1 code re-review artifacts 为 `docs/reviews/code-review-20260621-225901.md` 与 `docs/reviews/code-review-20260621-225831.md`；controller adjudication 为 `docs/reviews/wu-wait-01-slice1-code-rereview-controller-adjudication.md`。两路 re-review 均通过，无 material finding；S1-CR-F01 / S1-CR-F02 / S1-CR-F03 均关闭。Accepted Slice 1 commit 为 `6f919bb7`。Slice 2 implementation artifact 为 `docs/reviews/wu-wait-01-slice2-implementation-codex.md`；AgentCodex reported Service focused tests 28 passed, Service focused plus weak typing 29 passed, Host callback focused tests 56 passed, pyright 0 errors, and `git diff --check` passed. Controller reran Service focused plus weak typing tests with 29 passed, Host callback focused tests with 56 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code review artifacts 为 `docs/reviews/code-review-20260621-231602.md` 与 `docs/reviews/code-review-20260621-231811.md`；controller adjudication 为 `docs/reviews/wu-wait-01-slice2-code-review-controller-adjudication.md`。Controller accepted S2-CR-F01 missing request id sentinel rejection and S2-CR-F02 fail-closed mapper branch tests. Slice 2 fix artifact 为 `docs/reviews/wu-wait-01-slice2-fix-codex.md`；AgentCodex reported Service focused tests 47 passed, Host callback focused tests 56 passed, pyright 0 errors, and `git diff --check` passed. Controller reran Service focused tests with 47 passed, Host callback focused tests with 56 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code re-review artifacts 为 `docs/reviews/code-review-20260621-232753.md` 与 `docs/reviews/code-review-20260621-232916.md`；controller adjudication 为 `docs/reviews/wu-wait-01-slice2-code-rereview-controller-adjudication.md`。两路 re-review 均通过，无 material finding；S2-CR-F01 / S2-CR-F02 均关闭。Accepted Slice 2 commit 为 `9d77e641`。Aggregate deepreview artifacts 为 `docs/reviews/code-review-20260621-234334.md` 与 `docs/reviews/code-review-20260621-233742.md`；controller adjudication 为 `docs/reviews/wu-wait-01-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均通过，无 material finding；controller accepted all residual risks as non-blocking. Accepted deepreview commit 为 `ab2a6997`。Draft PR #163 已创建：https://github.com/noho/dayu-agent-r/pull/163。`gh pr checks 163` reported no checks on branch `phase/wu-wait-01-issue-89`。PR review artifacts 为 `docs/reviews/wu-wait-01-pr-review-mimo.md` 与 `docs/reviews/wu-wait-01-pr-review-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-01-pr-review-controller-adjudication.md`。两路 PR review 均通过，无 material finding。Accepted PR review commit 为 `36eda549` 并已 push 到 draft PR #163。Final closeout artifact 为 `docs/reviews/wu-wait-01-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/89#issuecomment-4762516139。PR body 使用 `Closes #89`，merge 会自动关闭 #89。当前进入 final-closeout-pass gate，等待用户 / maintainer 处理 draft PR #163；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #163 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-WAIT-02 / GitHub Issue #90。

### 设计与代码核对

- `docs/host/design.md` 规定 Host 是 Session / Run / Attempt / EventLog / wait governance 真源；callback transport 不得拥有 Host durable state transition。
- `docs/engine/design.md` 规定 Engine 不持久化 wait record，不等待外部长事务完成；恢复由调用方构造新 `AgentRunRequest`，Host 负责等待治理。
- `dayu/host/api.py` 已有 `WaitResolutionSource.CALLBACK`，但缺少 callback adapter 的 typed envelope、auth source、payload digest 校验和错误分类契约。
- `dayu/host/waiting.py` 的 `DefaultHostResolveWaitService.resolve_wait(...)` 是当前 wait completion 的状态迁移 owner；callback 必须调用该路径，不得直接 append EventLog 或修改 Run / Attempt / wait record。
- `dayu/host/wait_adapter.py` 已有 poller adapter 和 activation adapter 边界，模块 docstring 明确当前不实现 callback endpoint；callback adapter 应与 poller/manual converge 到同一 `ResolveWaitRequest`。
- `tests/host/test_resolve_wait_command.py` 已覆盖 resolve wait replay、idempotency conflict、failed/lost terminal、cancelled outcome 和 late rejection；plan 应复用这些测试边界，不重复设计状态机。

### Plan Gate 约束

- Plan 必须明确 callback endpoint 的形式：Host core 提供框架无关 typed callback contract / adapter；Service / Web 层负责真实 HTTP route、header/body 读取和 transport status mapping。不得把 FastAPI、Flask 或其它 HTTP framework 放入 Host core。
- Plan 必须定义 callback request envelope 的字段语义：auth source / claims、wait id、idempotency key、payload digest、observed/completed timestamp、typed outcome refs/payload，以及哪些字段属于 transport 诊断而不是 Host durable truth。
- Plan 必须说明认证失败、malformed payload、payload digest mismatch、unknown wait id、cancelled/lost late callback、同 key 不同 outcome digest conflict、successful replay 分别如何映射为 typed result / HostApiError / diagnostic / HTTP adapter status。
- Plan 必须证明 endpoint adapter 不直接写 EventLog、Run、Attempt 或 wait record；所有 terminal state changes 只能通过 `resolve_wait`。
- Plan 必须控制 slice 成本。小型同一语义 cleanup 默认 1-3 个 implementation slices；如果超过 3 个 slices，必须证明不能按 callback contract / adapter mapping / Service route or tests 的闭环合并。
- Plan 不得实现 #90 production poller loop、#92 physical cancel / revoke / abandon、Claude Code / Codex UI parity、Engine awaiting model 变更或新的 public wait lifecycle。

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

Goal confirmation 已由用户确认。Plan artifact 为 `docs/host/wu-wait-03-external-job-lifecycle-plan.md`。Plan review artifacts 为 `docs/reviews/wu-wait-03-plan-review-mimo.md` 与 `docs/reviews/wu-wait-03-plan-review-ds.md`，controller adjudication 为 `docs/reviews/wu-wait-03-plan-review-controller-adjudication.md`。Plan-fix artifact 为 `docs/reviews/wu-wait-03-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/wu-wait-03-plan-rereview-mimo.md` 与 `docs/reviews/wu-wait-03-plan-rereview-ds.md`，controller adjudication 为 `docs/reviews/wu-wait-03-plan-rereview-controller-adjudication.md`。Accepted plan commit 为 `6be72997`。Slice 1 implementation artifact 为 `docs/reviews/wu-wait-03-slice1-implementation-codex.md`；code review artifacts 为 `docs/reviews/wu-wait-03-slice1-code-review-mimo.md` 与 `docs/reviews/wu-wait-03-slice1-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-slice1-code-review-controller-adjudication.md`。Slice 1 fix artifact 为 `docs/reviews/wu-wait-03-slice1-fix-codex.md`；code re-review artifacts 为 `docs/reviews/wu-wait-03-slice1-code-rereview-mimo.md` 与 `docs/reviews/wu-wait-03-slice1-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-slice1-code-rereview-controller-adjudication.md`。Accepted Slice 1 commit 为 `4e661cee`。Slice 2 implementation artifact 为 `docs/reviews/wu-wait-03-slice2-implementation-codex.md`；AgentCodex reported Fins focused tests 125 passed, Host focused tests 35 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 125 passed and 35 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code review artifacts 为 `docs/reviews/wu-wait-03-slice2-code-review-mimo.md` 与 `docs/reviews/wu-wait-03-slice2-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-slice2-code-review-controller-adjudication.md`。Controller accepted one current-slice test coverage fix for cancel-side non-transient observation errors. Fix artifact 为 `docs/reviews/wu-wait-03-slice2-fix-codex.md`；AgentCodex reported Fins focused tests 126 passed, Host focused tests 35 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 126 passed and 35 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code re-review artifacts 为 `docs/reviews/wu-wait-03-slice2-code-rereview-mimo.md` 与 `docs/reviews/wu-wait-03-slice2-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-slice2-code-rereview-controller-adjudication.md`。两路 code re-review 均通过，accepted finding 已关闭，无 current-slice fix remaining。Accepted Slice 2 commit 为 `04fadb84`。Aggregate deepreview artifacts 为 `docs/reviews/wu-wait-03-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-wait-03-aggregate-deepreview-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均无 blocking finding；controller accepted README sync fixes for `dayu/host/README.md` and `tests/README.md`。Aggregate fix artifact 为 `docs/reviews/wu-wait-03-aggregate-fix-codex.md`；AgentCodex reported `git diff --check` passed and no code/config/test logic changed。Controller reran `git diff --check` with pass。Aggregate re-review artifacts 为 `docs/reviews/wu-wait-03-aggregate-rereview-mimo.md` 与 `docs/reviews/wu-wait-03-aggregate-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-aggregate-rereview-controller-adjudication.md`。两路 aggregate re-review 均通过，README sync findings 已关闭，无 aggregate fix remaining。Accepted aggregate commit 为 `848839e9`。Draft PR #166 已创建：https://github.com/noho/dayu-agent-r/pull/166。PR body 使用 `Closes #92`，merge 会自动关闭 #92。PR review artifacts 为 `docs/reviews/wu-wait-03-pr-166-review-mimo.md` 与 `docs/reviews/wu-wait-03-pr-166-review-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-pr-166-review-controller-adjudication.md`。两路 PR review 均通过，无 blocking finding；DS low-severity stale control-doc gate text finding 已接受并修复。Final closeout artifact 为 `docs/reviews/wu-wait-03-final-closeout.md`。Residual risk reconciliation artifact 为 `docs/reviews/wu-wait-03-residual-risk-reconciliation.md`；provider best-effort、future `CANCEL` / `REVOKE` diagnostics、missing GitHub checks 和 tool/provider blocking I/O hard interruption 均已裁决为非当前 residual；production poller composition validation 由 WU-WAIT-04 追踪，generic tool/provider hardening 由普通 deferred WU `WU-TOOLS-CANCEL-01` 追踪。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/92#issuecomment-4880126795。当前进入 final-closeout-pass，等待用户 / maintainer 处理 draft PR #166；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。

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

已达 final-closeout-pass。依赖 WU-WAIT-01 / GitHub Issue #89、WU-WAIT-02 / GitHub Issue #90、WU-WAIT-03 / GitHub Issue #92、WU-LIFE-03、WU-LIFE-04 与 WU-TOOLS-CANCEL-01 均已满足。Goal confirmation 明确要求 smoke 只能使用 public contracts；Plan commit 为 `35d947ea`，S1 accepted commit 为 `503b2cf5`，S2 accepted commit 为 `d3bdb2c3`。Final closeout artifact 为 `docs/reviews/wu-wait-04-final-closeout.md`。Draft PR #171 已创建：https://github.com/noho/dayu-agent-r/pull/171。

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
