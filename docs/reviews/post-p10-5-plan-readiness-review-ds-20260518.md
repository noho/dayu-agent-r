# P10.5 Plan Readiness Review — 能否进入 implementation-ready planning

**Reviewer**: AgentDS (challenge reviewer)
**Date**: 2026-05-18
**Gate**: P10.5 从 "public API / contract decision discussion" 进入 "implementation-ready planning" 的 readiness 判定
**命题**: 基于当前 `docs/host/design.md`、`docs/host/implementation-control.md`、`docs/host/post-p10.md` 三份文档，能否确保 implementation-ready plan 产出后，未来真实生产 Service 只调用 Host public interface / contract 即可完成普通本地多轮会话闭环？

**结论**: **命题成立，可以进入 implementation-ready planning**。0 blocking finding。存在 6 项 residual risk（non-blocking / clarification），其中 3 项需在 plan 中显式收口，3 项建议标记 owner 即可。

---

## Finding 1（non-blocking）：`open_host(options)` 的 typed options 尚无单一结构化定义，planning agent 需要从多段 prose 自行聚合

**位置**:
- `docs/host/design.md:861-869`（prose 描述 options 内容）
- `docs/host/design.md:749-760`（可注入运行参数列表）
- `docs/host/implementation-control.md:1210`（"必须确认 `open_host(options)` public handle 的 options shape"）

**问题**: 设计真源 `design.md` 中以 prose 形式分散描述了 options 必须包含的内容（durable store 路径、payload/artifact roots、runner/worker factory、全量 business ToolBundle、ToolRuntime policy、ContextCompactor、compactor execution baseline、context budget policy、memory catch-up、stream fanout/background supervisor 所需端口等），但没有任何一处给出 options 的单一结构化类型定义。`implementation-control.md:1210` 仍用"必须确认"标记该项。

**反例**: planning agent 从 prose 自行聚合时，可能漏掉某个必须的 construction-time 参数（例如 compact_artifact_root），或者把不该进 options 的 per-run 参数（例如 runner_spec 的默认值 vs per-run override）放进同一个 typed options 对象，导致 Service 接口变形。

**裁决**: non-blocking。设计已明确"底层生产运行需要哪些 construction-time 外部依赖，就通过 typed function 参数显式传入哪些"，且 scheduler/wakeup/active registry 等内部接线不暴露。planning agent 有能力从这些 prose 约束中聚合出 typed options，但 **P10.5 plan 必须在 Slice 1 产出前给出 `OpenHostOptions` 的完整 typed dataclass 定义，并在 plan review 中验证无遗漏、无越界**。

---

## Finding 2（non-blocking）：typed `HostEvent` 的 Python 类型形状在 design.md 中以字段枚举描述，但缺少完整 dataclass/Union 定义

**位置**:
- `docs/host/design.md:905-911`（`HostEvent` 边界描述）
- `docs/host/design.md:903-904`（live watch iterator 形态）
- `docs/host/implementation-control.md:1223`（"typed HostEvent 与 terminal final answer view"）

**问题**: `HostEvent` 的最小字段（`event_id`、`event_sequence`、`session_id`、`run_id?`、typed kind、dedupe identity、display payload）和 terminal `SUCCEEDED` 的 final answer view（`content`、`filtered`、`degraded`、`finish_reason`、terminal status）已明确。但 tool event、thinking delta、content delta 的 typed kind union 和 display payload 形状尚未枚举。当前代码中存在 `HostEventView`（薄 DTO）和 `HostEventClass` enum，但设计已裁决 `HostEventView` 降为内部。

**反例**: planning agent 需要自行决定完整 typed event kind union（`RUN_STARTED`、`RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED`、`TOOL_CALL`、`TOOL_RESULT`、`THINKING_DELTA`、`CONTENT_DELTA` 等），可能和未来 P13 Outbox/Tool Trace 的 event 消费口径不一致。

**裁决**: non-blocking。设计真源已冻结 terminal `SUCCEEDED` 的 final answer view 字段（这是主路径关键），且 P10.5 不要求 smoke 覆盖所有 event kind 的 display。**P10.5 plan 只需冻结 terminal `SUCCEEDED` / `FAILED` / `CANCELLED` 三种 terminal kind 的 full typed view，以及至少一个 non-terminal displayable event（如 content delta）作为连线证明**。完整 typed event kind union 可以在 implementation 中自然展开，不影响 Service contract 稳定性——因为 Service 只通过 terminal HostEvent 的 final answer 完成主闭环，其它事件 kind 是可选 display。

---

## Finding 3（clarification）：`SubmitFollowupRequest` 的 `runner_spec?` / `runner_options?` / `agent_policy?` 与 construction-time default baseline 的有效配置解析规则未完全冻结

**位置**:
- `docs/host/design.md:863`（per-run typed override 语义）
- `docs/host/design.md:1086-1099`（`SubmitFollowupRequest` 字段）
- `docs/host/post-p10.md:412-416`（Per-run execution override 接线裁决）
- `docs/host/implementation-control.md:1226`（"同一 Session 不同 Run 可使用不同执行配置"）

**问题**: 设计明确"字段省略时使用 `open_host(options)` 的默认 baseline；字段出现时使用该 Run 显式传入的 typed value"。但未明确 partial override 语义：如果请求只传 `runner_spec`（换模型）但不传 `runner_options`，`runner_options` 是 fallback 到 construction-time default baseline，还是必须三字段要么全传要么全省略？

**反例**: planning agent 可能选择"field-level merge"（单字段覆盖），也可能选择"all-or-nothing"（三字段要么全传要么全用 default）。两种选择对 Service 调用方的理解成本不同：field-level merge 更灵活但 Host 内部的 effective config resolution 更复杂；all-or-nothing 更简单但调用方切换模型时也要同时传 options 和 policy。

**裁决**: clarification。建议在进入 plan 前明确一项（不超过 1 分钟决策）。当前设计措辞"字段省略时使用 default baseline"更倾向 field-level merge，但可以更低风险地收紧为"三字段要么全 None/省略（使用 default），要么全传 typed value（完全覆盖 default）"；这样做也降低了 Host 内部 effective config resolution 的组合爆炸。无论哪种，都不影响"Service 只调 Host public contract 即可完成闭环"的一阶命题——只是 contract ergonomics 的差异。

---

## Finding 4（non-blocking）：`FollowupSnapshot` 的 command commit watermark 字段语义可以继续 defer，不影响 plan

**位置**:
- `docs/host/post-p10.md:88`（`FollowupSnapshot` watermark 不是 `watch_session_events` cursor）
- `docs/host/design.md`（没有 `FollowupSnapshot` 完整字段定义）

**问题**: post-p10.md 说 `FollowupSnapshot` 包含"command commit event sequence / durable read watermark"，并明确该 watermark 不是 `watch_session_events` 的 cursor。但 design.md 中没有 `FollowupSnapshot` 的完整 typed 字段定义（只有 `accepted_run_id`、`accepted_run_status` 的语义描述）。

**裁决**: non-blocking。`FollowupSnapshot` 当前在代码中已存在（`dayu/host/api.py`），字段可沿用现有实现。P10.5 只需确保 `SubmitFollowupRequest` 的新字段（`system_prompt`、`user_prompt`、`tool_names` 等）被 admission validation 消费，`FollowupSnapshot` 的新字段与 P10 后 `ACCEPTED / QUEUED -> scheduler governance -> RUNNING` 状态语义对齐即可。watermark 的具体字段名和类型可以在 implementation 中确定。

---

## Finding 5（non-blocking）：compactor execution baseline 的 typed options shape 缺少独立定义，与 `OpenHostOptions` 的关系需要在 plan 中显式拆分

**位置**:
- `docs/host/design.md:865`（compactor 独立 execution baseline）
- `docs/host/post-p10.md:311`（Compactor execution baseline 裁决）
- `docs/host/implementation-control.md:1228`（"Compactor 的模型、温度、max tokens、provider 选择或 compact scene policy 是独立于 ordinary Run execution override 的 opener baseline"）

**问题**: 设计明确 compactor 的 execution baseline 独立于 ordinary Run 的 `runner_spec` / `runner_options` / `agent_policy`。但 compactor 的 typed options（`compactor_runner_spec`、`compactor_runner_options`、`compactor_policy`、`compact_artifact_root`）是 `open_host(options)` 的直接字段，还是一个独立 typed sub-object（如 `CompactorExecutionBaseline`）？当前 prose 用 `context_compactor`、`compactor_runner_spec`、`compactor_runner_options`、`compactor_policy` 等描述，但没有给出 typed shape。

**裁决**: non-blocking。设计意图明确（独立 baseline、不共享 ordinary Run override），planning agent 可以合理选择把 compactor 参数打包为 typed sub-object 或展开为 `open_host(options)` 的独立字段。**P10.5 plan 必须在 Slice 1 产出前决定 typed shape，并在 plan review 中验证：`SubmitFollowupRequest.runner_spec` 省略时，compactor 的 execution config 不受影响**。

---

## Finding 6（clarification）：design.md 与 implementation-control.md 对 P10.5 gate 状态的表述存在时间差，但不造成实质矛盾

**位置**:
- `docs/host/implementation-control.md:225-227`（"当前 gate：discussion / challenge review。下一 gate：P10.5 public API / contract decision discussion"）
- `docs/host/post-p10.md:547-548`（"本文档当前仍是 P10.5 public API / contract decision discussion artifact"）

**问题**: 三份 challenge review（MiMo、DS、Codex）已提交且裁决已写入 post-p10.md 的 Challenge Review 结论 section。implementation-control.md 的 gate 状态仍写"当前 gate：discussion / challenge review"。两份材料对"challenge review 是否已完成"的状态表述不一致：post-p10.md 的结论 section 明确接受了所有 finding 并裁决为 implementation requirement，而 implementation-control.md 还没有更新 gate 状态。

**裁决**: clarification。这只是总控文档的 gate 状态更新时机问题，不影响 design decisions 的稳定性。如果用户确认本轮 review 通过，implementation-control.md 的 gate 应更新为"P10.5 public API / contract decision discussion completed；ready for implementation-ready plan"。

---

## Coverage Checklist — P10.5 Smoke Matrix 设计一致性审查

以下只检查文档层面对 smoke matrix 的要求是否一致、可实施，不检查代码中是否存在 smoke（当前无 P10.5 public-path smoke）。

| 检查项 | design.md | impl-control.md | post-p10.md | 状态 |
|---|---|---|---|---|
| S1 real-runner no-tool multi-turn | §11 (pseudo-code recipe) | Phase 10.5 Slice 5 | §S1 full checklist | **一致** |
| S2 mock-tool wiring | §11 per-run tool_names | Phase 10.5 Slice 5 | §S2 full checklist | **一致** |
| S3 real-runner matrix (4 providers) | — (不在 design.md 中出现，属于验证层) | Phase 10.5 Slice 6 | §S3 full checklist + skip rules | **一致** (design.md 不承载 smoke 细节是正确分层) |
| S4 compact smoke (real compactor) | §11 (compactor public opener contract) | Phase 10.5 Slice 5 | §S4 full checklist | **一致** |
| S5 cancel smoke | §8 (cancel state machine)、§11 (cancel_run public API) | Phase 10.5 Slice 5 | §S5 full checklist | **一致** |
| mock runner 不计入 success signal | — (属于验证约束) | Phase 10.5 进入条件 | §测试替身约束 | **一致** |
| mock tool 防作弊约束 | — (属于验证约束) | Phase 10.5 进入条件 | §测试替身约束 | **一致** |
| final answer 从 terminal HostEvent 取 | §11 (HostEvent boundary) | Phase 10.5 退出条件 | §S1 terminal event path | **一致** |
| 不走 payload internal table | §11 (no public payload reader) | Phase 10.5 不做 | §S1 terminal event path | **一致** |
| 不定义 wait_final_answer | §11 (明确排除) | Phase 10.5 不做 | §Public API 变更护栏 | **一致** |

---

## Recovery / Outbox Exclusion 验证

### Recovery（Phase 11）

| 排除项 | design.md | impl-control.md | post-p10.md | P11 owner |
|---|---|---|---|---|
| `RECOVERING` cancel | §8 cancel matrix（标记为 Recovery 路径） | Phase 10.5 不做 | §S5 Recovery exclusion | Phase 11 |
| startup recovery scan | §27 Host Lifecycle / Recovery | Phase 10.5 不做 | §G10 gap 追踪 | Phase 11 |
| positive orphan proof | §27 | Phase 10.5 不做 | §G10 | Phase 11 |
| `RUNNING`/`CANCELLING` startup classification | §27 | Phase 10.5 不做 | §G10 | Phase 11 |
| crash recovery smoke | — | Phase 10.5 不做 | §G10 | Phase 11 |
| `LOST`/`RECOVERING` retry | §21 Suspend / Resume / Retry / Replay | Phase 10.5 不做 | §G7 | Phase 11 |
| Host close 后 active worker lost/recoverable-lost | §11 (Host close shutdown) | Phase 10.5（不实现完整 Recovery） | §G16 | Phase 11 |

**验证**: Recovery 所有路径已明确排除在 P10.5 之外，且 Phase 11 的 scope（`docs/host/implementation-control.md:1275-1335`）已承接所有排除项。P11 前置条件明确"不得破坏 P10.5 已冻结的普通本地多轮 Host public interface / contract"，**不会要求 Service API rewrite**。

### Outbox（Phase 13）

| 排除项 | design.md | impl-control.md | post-p10.md | P13 owner |
|---|---|---|---|---|
| Outbox concrete read/drain API | §11（P10.5 不实现） | Phase 10.5 不做 | §G2 Outbox boundary 裁决 | Phase 13 |
| OutboxSink terminal delivery queue | §16 Read Model / Outbox | Phase 10.5 不做 | §G2 | Phase 13 |
| 离线 terminal delivery smoke | §11（P10.5 不覆盖） | Phase 10.5 不做 | §G2 | Phase 13 |
| terminal identity/dedupe | §11（冻结 recipe） | Phase 10.5 关键设计（冻结 recipe） | §G2 | Phase 13 实现 |

**验证**: Outbox concrete API 已明确排除。P10.5 冻结的 attach/reconnect recipe（`last_seen_terminal_event_sequence`、`seen_terminal_event_ids`、`terminal_event_id`/`event_sequence`/`run_id` 去重）在三个文档中一致。Phase 13 的 scope（`docs/host/implementation-control.md:1402-1458`）已承接 concrete Outbox read/drain API 与离线 terminal delivery smoke。**不会要求 Service API rewrite**——Phase 13 会在 P10.5 已冻结的 contract 上新增 Outbox API，而不是修改 `watch_session_events(...)` 或 terminal HostEvent 的语义。

---

## 不存在隐藏假设验证

| 假设 | 检查结论 |
|---|---|
| Service/CLI/WeChat/GUI 真实入口接入 | 已明确排除（post-p10.md §当前讨论暂不考虑），P10.5 只冻结 contract，不做真实接入 |
| 业务工具发现/注册 | 已明确排除，归 Phase 12；P10.5 可用 mock ToolBundle |
| 动态 ScenePrepare | 已明确排除，归 Phase 12；P10.5 可写死 scene inputs |
| web tools 迁移 | 已明确排除（post-p10.md §当前讨论暂不考虑） |
| ConfigLoader | 已明确排除，P10.5 硬编码 runner 参数 |
| provider-specific 实现 | 已明确排除，真实 runner 只做 connectivity smoke，不做 correctness 证明 |
| 薄 Service 是 Host 特殊接口类型 | 已明确拒绝（post-p10.md:33 "薄 Service 只是最小 consumer 证明样例，不是 Host 需要特殊识别或特殊支持的一类调用方"） |
| HostEventView 进入 Service-facing contract | 已明确拒绝，降为内部 DTO |
| stream_run_events 进入 Service-facing contract | 已明确拒绝，降为内部 diagnostic |
| start_run 进入 Service-facing API | 已明确拒绝，改名为 `_start_run` |

---

## 三份文档中 Public API 决策一致性矩阵

| 决策项 | design.md | impl-control.md | post-p10.md | 一致 |
|---|---|---|---|---|
| opener 名称 = `open_host(options)` | §11 | Phase 10.5 目标 | §缺失清单 #1 + 建议目标 | ✓ |
| async-only handle | §11 | Phase 10.5 目标 | §建议目标 | ✓ |
| `start_run` → `_start_run` | §10.1 | Phase 10.5 目标 | §G1 gap | ✓ |
| `create_host_command_handle` 降为内部 | §11 | Phase 10.5 目标 | §建议目标 | ✓ |
| `HostLocalRuntime`/`HostLocalExecutionOptions` 内部 | §11 | Phase 10.5 目标 | §建议目标 | ✓ |
| `watch_session_events(session_id) -> AsyncIterator[HostEvent]` | §11 | Phase 10.5 退出条件 | §G4 gap + 建议目标 | ✓ |
| `HostEventView` 内部 DTO | §11 | Phase 10.5 不做 | §G4 gap + 建议目标 | ✓ |
| no `wait_final_answer(...)` | §11 | Phase 10.5 不做 | §Public API 变更护栏 | ✓ |
| no public payload reader | §11 | Phase 10.5 不做 | §Public API 变更护栏 | ✓ |
| scheduler/wakeup 不暴露 | §10.1 + §11 | Phase 10.5 目标 | §缺失清单 #2 | ✓ |
| `SubmitFollowupRequest` 新 shape | §11 (typed fields) | Phase 10.5 关键设计 | §G5 gap + Per-run 裁决 | ✓ |
| per-run `tool_names` selector | §10.1 (P10.5 语义) | Phase 10.5 关键设计 | §G14 gap | ✓ |
| per-run typed execution override | §11 | Phase 10.5 关键设计 | §缺失清单 #7 + Per-run 裁决 | ✓ |
| compactor execution baseline 独立 | §11 | Phase 10.5 关键设计 | §G13 gap + 裁决 | ✓ |
| Host opener close ≠ cancel ≠ close_session | §11 | Phase 10.5 关键设计 | §G11 gap + 边界 | ✓ |
| Outbox concrete API → Phase 13 | §11 | Phase 10.5 不做 | §G2 boundary 裁决 | ✓ |
| Recovery → Phase 11 | §27 | Phase 10.5 不做 | §G10 | ✓ |
| multi-client no write lock / attach token | §11 | Phase 10.5 关键设计 | §G3 | ✓ |

**全矩阵 17 项决策在三个文档中一致，0 矛盾。**

---

## 当前代码与 P10.5 决策的差距（FYI — 不构成 blocking）

以下差距是已知的 implementation gap，由 P10.5 implementation 负责修复，不阻塞 plan 生成：

| 代码事实 | P10.5 决策 | 差距 |
|---|---|---|
| `start_run` 仍在 `__all__`（`__init__.py:185`） | 从 public namespace 移除 | 待 P10.5 Slice 1 清理 |
| `HostLocalExecutionOptions` 仍在 `__all__`（`__init__.py:133`） | 改为内部 contract | 待 P10.5 Slice 1 降级 |
| `HostEventView` 仍在 `__all__`（`__init__.py:136`） | 内部 DTO | 待 P10.5 Slice 2 降级 |
| `stream_run_events` 仍在 `__all__`（`__init__.py:186`） | 内部 diagnostic | 待 P10.5 Slice 2 降级 |
| `create_host_command_handle` 仍在 `__all__`（`__init__.py:175`） | 内部/测试 primitive | 待 P10.5 Slice 1 降级 |
| `open_host()` 不存在 | Service-facing entry point | 待 P10.5 Slice 1 实现 |
| `watch_session_events()` 不存在 | 主事件流入口 | 待 P10.5 Slice 2 实现 |
| typed `HostEvent` 不存在（只有 `HostEventView` 薄 DTO） | terminal final answer view | 待 P10.5 Slice 2 实现 |
| `HostEventStream` 存在但只用于 run-scoped 补读 | session-level live iterator | 待 P10.5 Slice 2 改造或新增 |

---

## Residual Risks 与建议 Owner

| # | Risk | Severity | Owner |
|---|---|---|---|
| R1 | `open_host(options)` typed options 从多段 prose 聚合时遗漏参数 | 低 | P10.5 plan review 验证 |
| R2 | typed `HostEvent` kind union 在 P10.5 与 P13 之间口径不一致 | 低 | P10.5 只冻结 terminal kinds；P13 扩展时 review |
| R3 | per-run `runner_spec`/`runner_options`/`agent_policy` partial override 语义未冻结 | 中 | P10.5 plan 前用户确认（见 Finding 3） |
| R4 | compactor typed options sub-object vs flat fields 的 shape 选择 | 低 | P10.5 plan Slice 1 产出前决定（见 Finding 5） |
| R5 | `FollowupSnapshot` 新字段（P10 后 `ACCEPTED`/`QUEUED` 语义）与旧测试的矛盾 | 低 | P10.5 implementation（已知，见 post-p10.md:162-165） |
| R6 | S3 real-runner matrix smoke 的 provider 不可用时 skip 规则在 plan 的退出条件中需显式复述 | 低 | P10.5 plan validation section（Codex N1 已指出） |

---

## 最终判定

**0 blocking finding。P10.5 可以进入 implementation-ready planning。**

三个文档在 P10.5 的 goal、scope、non-goals、public API、runtime opener、event stream、final answer path、runner/tool/compactor options、cancel/close/session lifecycle、wait/resolve、retry/replay/steer、multi-client、Outbox 与 Recovery 排除、以及 smoke coverage 要求上**一致、无矛盾**。

三份 challenge review（MiMo、DS、Codex）的 blocking findings 已全部被接受并转化为 implementation requirement，写回 `post-p10.md` Challenge Review 结论 section。P10.5 需要新增的 public API（`open_host(options)`、`watch_session_events(...)`、typed `HostEvent`、per-run `tool_names`、per-run typed execution override）已全部完成 public API discussion；需要降级/移除的旧接口（`start_run`、`create_host_command_handle`、`HostLocalRuntime`、`HostLocalExecutionOptions`、`HostEventView`、`stream_run_events`）已全部裁决。

P10.5 不包括 Recovery/Outbox concrete API，但三份文档均已明确这些能力归 Phase 11/Phase 13，且 Phase 11/Phase 13 的前置条件已写明"不得破坏 P10.5 冻结 contract"，**不会要求后续 Service API rewrite**。

**planning agent 可以基于这三份文档撰写 implementation-ready plan，但需在 plan 中显式处理 R1-R6（特别是 R3 — per-run execution override 的 partial vs all-or-nothing 语义，建议在 plan 开始前用 1 分钟向用户确认）。**
