# Phase 10.5 Plan Review — implementation-ready handoff plan

**Reviewer**: MiMo
**Date**: 2026-05-18
**Gate**: Phase 10.5 plan review
**Review target**: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
**Design truth**: `docs/host/design.md`
**Control truth**: `docs/host/implementation-control.md`
**P10.5 scope/coverage input**: `docs/host/post-p10.md`
**Readiness review inputs**: `docs/reviews/post-p10-5-plan-readiness-review-mimo-20260518.md`, `docs/reviews/post-p10-5-plan-readiness-review-ds-20260518.md`, `docs/reviews/post-p10-5-plan-readiness-review-codex-20260518.md`

## Review Question

Plan 是否 handoff-ready / code-generation-ready：implementation agent 是否无需重新设计 public API、状态机、schema、file ownership、测试边界或 smoke success signal 即可进入 implementation？

## Verdict

**PASS — 0 blocking findings。Plan 可以进入 implementation gate。**

Plan 完整收口了 design.md §11 public contract、implementation-control.md Phase 10.5 目标 / scope / non-goals / 退出条件，以及三份 readiness review 的全部 non-blocking / clarification checklist。S1-S5 coverage table 逐项有 owner slice、测试名、public-path 断言、skip 条件和后续 owner。`open_host(options)`、Host public handle、`watch_session_events`、terminal HostEvent、partial merge、tool_names、close/cancel/close_session、WAITING resolve_wait、steer/retry/replay、real compactor smoke 均足够明确，implementation agent 无需重新设计。

存在 4 项 non-blocking 和 3 项 clarification，均不阻塞 implementation gate。

---

## Findings

### F1. Non-blocking: Smoke 测试全部集中在 Slice 6，实现 slices 1-5 无独立 smoke 验证

**Severity**: non-blocking
**Evidence**: Plan Unified Coverage Table 所有 11 行的测试文件均位于 `tests/host/test_public_*.py`，由 Slice 6 负责最终组装和验证。Slice 1-5 的 stop condition 只依赖 unit / integration tests 和 pyright，不包含 public-path smoke。

**Problem**: implementation-control.md §1264-1267 的验证要求明确区分 unit tests（每 slice）和 integration tests / smoke（最终验证）。Plan 的 Slice 1-5 各自有明确 stop condition（例如 Slice 2: "A deterministic no-tool local worker can complete one public `submit_followup(queue)` through `open_host` without manual scheduler wakeup"），但这些 stop condition 的验证命令只包含该 slice 的 unit tests + pyright，不包含 public-path smoke。这意味着 Slice 6 在 11 个 smoke tests 中发现的 public-path bug 可能需要回溯到 Slice 1-5 修复，增加 iteration cost。

**为什么不是 blocking**: Slice 1-5 的 stop condition 本身设计合理——它们验证的是"该 slice 的 contract 已就位"，而非"端到端 public path 可用"。端到端 smoke 集中在 Slice 6 是正确的分层，因为 smoke 依赖所有 slice 的 contract 到位。但 plan 应在 Slice 6 描述中明确："若 smoke 暴露 Slice 1-5 的 public-path bug，由 Slice 6 owner 修复，不新建 slice。"

**建议**: 在 Slice 6 "Exact allowed changes" 中增加一行："Narrow `dayu/host` fixes only if smoke exposes public path bugs owned by Slice 1-5"——实际上已有此行（line 503），确认无遗漏。当前写法已足够。

---

### F2. Non-blocking: post-p10.md 的 12 个 gap (G1-G15) 到 plan slices 的映射未显式列出

**Severity**: non-blocking
**Evidence**: `docs/host/post-p10.md` §Agent session 使用场景 gap 追踪列表 定义了 G1-G15（实际编号到 G16），plan 通过 coverage table 和 slice descriptions 隐式覆盖了所有 gap，但没有显式映射表。

**Problem**: review agent 或 implementation agent 需要逐个 gap 检查 plan 是否覆盖。隐式映射增加 review 认知负担，且容易遗漏。

**为什么不是 blocking**: Plan 的 coverage table + readiness review closure table + per-slice objectives 已经足够让 implementation agent 理解覆盖范围。G1-G15 的 gap 内容在 plan 的 goal/motivation、public contract change list、typed options shape、per-run config freeze、session-level event stream、close/cancel boundary、WAITING resume path、memory catch-up、readiness review closure 和 coverage table 中均有显式对应。显式映射表是 nice-to-have，不是 handoff blocker。

**建议**: Implementation agent 可在开始 Slice 1 前自行建立 G1-G15 → slice 快速映射，作为 implementation checklist 的一部分。不需要修改 plan。

---

### F3. Non-blocking: 真实 compactor adapter 的代码位置未在 plan 中指定

**Severity**: non-blocking
**Evidence**: Plan Slice 1 定义了 `CompactorExecutionBaseline` typed shape（line 109-114），Slice 6 要求 "S4 compact smoke using explicit real compactor adapter, not `FakeContextCompactor`"（line 511），但未指定真实 compactor adapter 代码放在哪里。

**Problem**: `post-p10.md` 要求 "使用显式注入的真实 compactor adapter；该 adapter 可以作为 tests smoke support 存在，但必须真实调用 runner / provider"（line 239）。Plan 未指定这个 adapter 的 module path。Implementation agent 可能需要自行决定是放在 `tests/host/` 下、`dayu/host/` 下、还是 `dayu/runtime/` 下。

**为什么不是 blocking**: Plan 的 non-goals 明确 "不实现 ConfigLoader；真实 runner smoke 可使用受控硬编码 runner parameters"。compactor adapter 类似——它是一个 tests support module，不是 production `dayu.host` 代码。Plan 在 Slice 6 的 "Allowed files / modules" 中列出了 "Test support under `tests/host/` only, including real-runner and real-compactor smoke helpers"（line 500），这已隐式指定了 adapter 位置：`tests/host/` 下的 smoke helper。Implementation agent 可以合理选择 `tests/host/support/real_compactor_adapter.py` 或等价路径。

**建议**: 不需要修改 plan。Implementation agent 在 Slice 6 开始前确认 adapter 位置即可。若 adapter 必须放入 production `dayu.host`（例如 provider-specific compactor module），则属于 plan 的 "Blocking Questions For Controller" 触发条件（line 577: "真实 compactor adapter 必须放入 production `dayu.host` provider-specific module 才能完成 smoke，且该选择会改变 Host 与 Engine / provider 的依赖边界"），需停下交 Controller 裁决。

---

### F4. Non-blocking: `HostClosedError` 继承层级只写了 "standalone lifecycle exception class"，未指定是否继承 `HostApiError`

**Severity**: non-blocking
**Evidence**: Plan line 153: "新增 public standalone lifecycle exception class，例如 `HostClosedError(Exception)` 或项目内更窄的 lifecycle base class"。MiMo readiness review F3 已提出此问题。

**Problem**: `HostClosedError(Exception)` 意味着不继承 `HostApiError`；但如果 project 内有更通用的 lifecycle base class，implementation agent 需要判断。Plan 给出了两个候选但未决策。

**为什么不是 blocking**: Plan 已明确 "不要把 handle closed 映为 command-level `HostApiErrorCode.INVALID_STATE`"（line 153），语义边界清晰。Implementation agent 可以选择 `HostClosedError(Exception)` 作为最简单方案，且不影响任何 public contract。如果后续发现需要与 `HostApiError` 统一 catch，可以在不改 public contract 的前提下调整继承层级。

**建议**: 不需要修改 plan。Implementation agent 在 Slice 1 中自行决策即可。推荐 `HostClosedError(Exception)` 作为第一版，保持最窄继承。

---

### F5. Clarification: `HostEventStream` 在 plan 中未显式写为 "返回类型别名 / Protocol"

**Severity**: clarification
**Evidence**: Plan line 90: "`HostEventStream` 若保留，只能是内部实现或返回类型别名 / Protocol"。MiMo readiness review F2 和 Codex readiness review F2 均要求 plan 收敛此术语。Plan 的 resolution table（line 252）写 "Slice 4 冻结 terminal `SUCCEEDED` / `FAILED` / `CANCELLED` typed view，`HostEventStream` 只作 internal/type alias"。

**Problem**: Plan 在 Public Contract Change List（line 90）和 Readiness Review Closure（line 252）中都提到了 `HostEventStream` 的定位，但 Slice 4 的 "Exact allowed changes"（line 416-421）未显式列出 "`HostEventStream` 若保留，必须定义为 `AsyncIterator[HostEvent]` 的类型别名或 Protocol，不添加额外 public 方法"。

**为什么不是 blocking**: Slice 4 的 objective 明确 "demote run-level stream / `HostEventView` to internal diagnostic use"（line 405），且 "Exact allowed changes" 中列出了 "Remove ordinary public docs / exports for `HostEventView` and `stream_run_events`"（line 421）。Implementation agent 可以从 plan 的 public contract change list（line 90）和 readiness review closure（line 252）推断 `HostEventStream` 的处理方式。但显式在 Slice 4 中加一行会更清晰。

**建议**: Implementation agent 在 Slice 4 中确保 `HostEventStream` 不从 `dayu.host` public namespace 导出，且若保留则仅为 `type HostEventStream = AsyncIterator[HostEvent]` 或内部 class。不需要修改 plan——plan 的 guidance 已足够。

---

### F6. Clarification: S1 per-run execution override 测试的 "effective config freeze 可读 / 可诊断" 断言方式未指定

**Severity**: clarification
**Evidence**: Coverage table line 264: "effective config freeze 可读 / 可诊断"。Plan line 175: "admission / dispatch 必须把本 Run effective config freeze 到 Run / Attempt 可解释 snapshot、source refs 或 diagnostic refs"。

**Problem**: "可读 / 可诊断" 的具体断言方式未指定：是通过 `get_run()` 的 `RunSnapshot` 字段读取？还是通过 EventLog 的 diagnostic refs？还是通过 internal dispatch record？Coverage table 的 public-path assertion 写 "只传 `runner_options` 时 runner spec / policy 来自 opener baseline"，但未说明如何在不读 internal tables 的情况下证明这一点。

**为什么不是 blocking**: 这是 implementation 细节，不是 contract 设计问题。Implementation agent 可以选择通过 `RunSnapshot` 的 typed fields（如果 plan 要求暴露 effective config refs）或通过 mock runner 捕获的 `AgentRunRequest` 字段（在 low-level integration test 中）来证明。Plan 已在 line 175 给出 "Run / Attempt 可解释 snapshot、source refs 或 diagnostic refs" 的方向。

**建议**: Implementation agent 在 Slice 3 中决定 effective config 的 observable surface：是 `RunSnapshot` 新增 typed fields，还是 internal diagnostic path。若选择前者，需确保 `RunSnapshot` 的新字段属于 plan 已允许的 "public request / snapshot / event 类型" 变更范围（line 44）。不需要修改 plan。

---

### F7. Clarification: Slice 顺序是否诱导 "future-slice work" 在当前 slice 中提前实施

**Severity**: clarification
**Evidence**: Plan 6 slices 的 dependency: Slice 1 → Slice 2 → Slice 3 → Slice 4 → Slice 5 → Slice 6。Slice 5 依赖 Slice 1-4，Slice 6 依赖所有。

**Problem**: Implementation agent 在实施 Slice 2（composition root）时，可能会预见到 Slice 5（steer/retry/replay）需要的 scheduler wakeup 路径，从而在 Slice 2 中提前实现 steer/retry/replay 的 wakeup 接线。Plan 的 Slice 2 "Non-goals"（line 339）明确 "Do not expose scheduler wakeup or dispatch control on public handle"，但未明确 "Do not pre-wire steer/retry/replay wakeup paths"。

**为什么不是 blocking**: Slice 2 的 stop condition（line 358）只要求 "A deterministic no-tool local worker can complete one public `submit_followup(queue)` through `open_host` without manual scheduler wakeup"，不要求 steer/retry/replay 路径。Implementation agent 应聚焦 stop condition，不提前实现后续 slice 的 contract。

**建议**: Implementation agent 在每个 slice 中严格遵循 stop condition，不提前实现后续 slice 的能力。不需要修改 plan。

---

## Design.md Alignment Check

| 设计要求 | Plan 对应 | 一致 |
| --- | --- | --- |
| Host 是 Session/Run/Attempt/EventLog/admission/cancel/resume/retry/steer/replay/memory/tool governance 真源 (§2) | Plan 全文围绕 Host public contract，不绕过 Host 直接操作 internals | ✓ |
| Engine 只执行单次 AgentRunRequest (§2) | Plan non-goals: "Engine 不得理解 Host 状态" (line 51) | ✓ |
| 依赖方向 UI→Service→Host→Engine (§2) | Plan 以 Service 只调用 Host public contract 为核心命题 | ✓ |
| `open_host(options)` async context manager (§11) | Plan line 77, 94, 98-144 | ✓ |
| Host handle 不暴露 internals (§11) | Plan line 78, 88, 339, 341 | ✓ |
| `start_run` 降为内部 `_start_run` (§10.1, §11) | Plan line 86, 293-294 | ✓ |
| `watch_session_events(session_id) → AsyncIterator[HostEvent]` (§11) | Plan line 85, 191-207 | ✓ |
| terminal HostEvent inline final answer view (§11) | Plan line 197-198 | ✓ |
| per-run field-level partial merge (§11) | Plan line 168-176 | ✓ |
| compactor baseline independent of ordinary Run override (§11) | Plan line 109-114, 240-242 | ✓ |
| scheduler wakeup 由 Host 内部 ownership (§11) | Plan line 344-345 | ✓ |
| close_session ≠ cancel ≠ opener close (§11) | Plan line 209-215 | ✓ |
| HostClosedError lifecycle exception (§11) | Plan line 153 | ✓ |
| HostEventView 降为内部 (§11) | Plan line 89, 421 | ✓ |
| stream_run_events 降为内部 (§11) | Plan line 89, 421 | ✓ |
| 不定义 wait_final_answer (§11) | Plan non-goals line 35 | ✓ |
| 不定义 public payload reader (§11) | Plan non-goals line 35 | ✓ |

---

## Implementation-control.md Phase 10.5 Compliance Check

| 控制要求 | Plan 对应 | 一致 |
| --- | --- | --- |
| 冻结普通本地多轮 public contract (line 1174-1176) | Plan Goal section (line 10-21) | ✓ |
| async-only `open_host(options)` (line 1178) | Plan line 77 | ✓ |
| Session acquisition 与 Run interaction 分离 (line 1180) | Plan line 79 | ✓ |
| Command mutation 与 event observation 分离 (line 1182) | Plan line 85 | ✓ |
| steer/retry/replay 本地语义 (line 1183) | Plan Slice 5 (line 443-491) | ✓ |
| memory catch-up / compactor public opener (line 1184) | Plan Slice 1 typed options (line 98-144) | ✓ |
| Smoke 覆盖矩阵 (line 1239) | Plan Unified Coverage Table (line 260-272) | ✓ |
| S1-S5 + WAITING + steer/retry/replay + cancel + close (line 1239) | Coverage table 11 rows 全覆盖 | ✓ |
| mock runner 不计入 success signal (line 1206) | Plan non-goals, coverage table skip rules | ✓ |
| 不实现 Recovery (line 1213) | Plan non-goals line 27 | ✓ |
| 不实现 Outbox concrete read/drain (line 1220) | Plan non-goals line 30 | ✓ |
| 不定义 wait_final_answer (line 1222) | Plan non-goals line 35 | ✓ |
| readiness review checklist 收口 (line 1257-1262) | Plan Readiness Review Closure table (line 246-256) | ✓ |
| 退出条件 (line 1271-1278) | Plan Stop conditions 各 slice + Blocking Questions + Residual Risks | ✓ |

---

## post-p10.md Correct Usage Check

| 使用方式 | 正确性 |
| --- | --- |
| 作为 P10.5 目标、任务、coverage、gap 输入 | ✓ Plan 引用 post-p10.md 的 S1-S5 matrix、G1-G15 gap、test constraints |
| 不作为设计真源 | ✓ Plan 以 design.md 为设计真源，post-p10.md 为 discussion artifact |
| 不作为 plan 替代品 | ✓ Plan 有独立的 slice、coverage table、typed shapes |
| readiness review checklist 收口 | ✓ Plan line 246-256 逐项映射到 slices |

---

## Readiness Review Closure Verification

### MiMo readiness review (post-p10-5-plan-readiness-review-mimo-20260518.md)

| Finding | Plan Resolution | Verified |
| --- | --- | --- |
| F1: Smoke naming gap | Plan line 248, 260-272 unified coverage table | ✓ |
| F2: `open_host(options)` typed shape | Plan line 98-144 concrete dataclass definitions | ✓ |
| F3: `HostClosedError` identity | Plan line 153 standalone exception, with Controller escalation path | ✓ |
| F4: S5/WAITING checklist | Coverage table lines 265-272 with per-sub-requirement owners | ✓ |

### DS readiness review (post-p10-5-plan-readiness-review-ds-20260518.md)

| Finding | Plan Resolution | Verified |
| --- | --- | --- |
| F1: `OpenHostOptions` typed shape | Plan line 98-144 `OpenHostOptions` + sub-objects | ✓ |
| F2: `HostEvent` typed shape | Plan line 197-199, Slice 4 line 416 terminal kinds frozen | ✓ |
| F3: Per-run partial merge | Plan line 168-176 field-level partial merge explicitly stated | ✓ |
| F4: FollowupSnapshot watermark | Plan line 175 "command commit sequence / watermark; watermark is not watch cursor" | ✓ |
| F5: Compactor typed options | Plan line 109-114 `CompactorExecutionBaseline` sub-object | ✓ |
| F6: Gate state sync | Plan line 256 "Controller 后续 gate bookkeeping 更新" | ✓ |

### Codex readiness review (post-p10-5-plan-readiness-review-codex-20260518.md)

| Finding | Plan Resolution | Verified |
| --- | --- | --- |
| F1: S4 compact / WAITING resume / close-session owner | Coverage table lines 269, 265, 272 with named slices | ✓ |
| F2: `HostEventStream` 非 handle 语义 | Plan line 90, 252 convergence to type alias / Protocol | ✓ |

---

## S1-S5 Coverage Table Verification

| Coverage | Owner slice | Test name | Public-path assertions | Skip condition | Follow-up owner | Verified |
| --- | --- | --- | --- | --- | --- | --- |
| S1 real-runner no-tool multi-turn | Slice 6 | `test_real_runner_no_tool_two_turn_public_path` | `open_host`, `submit_followup(queue)`, memory catch-up, terminal `HostEvent.final_answer.content` | Provider secret/network unavailable | None | ✓ |
| S1 multi-client watch / queue idempotency | Slice 3+4+6 | `test_two_watchers_observe_same_terminal_event`, `test_concurrent_queue_uses_client_request_id_idempotency` | Two watchers, durable accepted order, idempotency | None for deterministic | None | ✓ |
| S1 per-run execution override | Slice 3+6 | `test_submit_followup_field_level_execution_override_freezes_effective_config` | Field-level partial merge, effective config freeze | None for unit; real provider may skip | None | ✓ |
| S1 WAITING public resume | Slice 5 | `test_resolve_wait_resumes_through_open_host_and_terminal_event` | Public `resolve_wait`, after-commit wakeup, terminal HostEvent | None for mock waiting tool | Callback/poller to later | ✓ |
| S1 steer/retry/replay controls | Slice 5 | `test_steer_running_run_...`, `test_retry_failed_run_...`, `test_replay_succeeded_run_...` | Public handle, event visible, source relation, replay no-tool | None for deterministic | LOST/RECOVERING to P11 | ✓ |
| S2 mock-tool wiring | Slice 3+6 | `test_mock_tool_fact_enters_memory_and_next_run_input`, `test_tool_names_subset_and_empty_freeze` | ToolBundle from opener, tool_names subset/empty, accept barrier, memory | None | Real tools to P12 | ✓ |
| S3 real-runner matrix | Slice 6 | `test_public_real_runner_matrix_smoke.py::{mimo,deepseek,gemini,qwen}` | Same `open_host`/`submit_followup`/`watch_session_events` path | Provider API key/network unavailable | If all skipped, Controller | ✓ |
| S4 compact real compactor | Slice 1+6 | `test_real_compactor_public_opener_compacts_and_preserves_continuity` | Real compactor, canonical compact events, memory projection, continuity | Compactor provider unavailable | Provider hardening later | ✓ |
| S5 cancel accepted/queued/pre-dispatch | Slice 5 | `test_cancel_accepted_and_queued_runs_public_path`, `test_pre_dispatch_cancel_visible_in_watch` | Public cancel commands, `get_run` and watch see cancel | None | Active cancel watchdog to P11 | ✓ |
| S5 active/session-scope cancel visibility | Slice 5+6 | `test_active_cancel_emits_public_cancel_event`, `test_cancel_session_runs_scoped_to_session` | Shared registry, cancel event visible, session scope | Long-running active cancel may skip | Phase 11 stuck active | ✓ |
| S5 close boundary | Slice 2+5 | `test_close_session_opener_close_and_cancel_are_distinct` | `close_session` ≠ opener close ≠ cancel | None | Purge to P15 | ✓ |

**Coverage table 结论**: 11 项全部有 owner slice、测试名、public-path 断言、skip 条件和后续 owner。无遗漏。无用 mock runner / internal durable table / scheduler internals 凑 success signal 的空间。

---

## Blocking Questions For Controller

当前没有阻塞 implementation-ready plan 的 material open question。

Plan 的 "Blocking Questions For Controller"（line 569-579）列出了 implementation agent 必须停下的触发条件，与 implementation-control.md Phase 10.5 的 constraints 一致。

---

## Residual Risks

| # | Risk | Severity | Owner |
| --- | --- | --- | --- |
| R1 | S3 real-runner matrix 全部 provider 不可用导致零 coverage | 中 | Slice 6 validation; Controller 决定是否接受 residual |
| R2 | S4 real compactor 依赖 provider/网络，不可用时 compact smoke 无法执行 | 中 | Slice 6; mock compactor 不能替代 success signal |
| R3 | Implementation agent 在 Slice 2 中提前实现 Slice 5 的 steer/retry/replay wakeup 接线 | 低 | Implementation discipline; stop condition 已约束 |
| R4 | `HostClosedError` 继承层级选择可能需要与 project 内其它 lifecycle exception 统一 | 低 | Slice 1; 不影响 public contract |

---

## Artifact Path

`docs/reviews/phase10-5-plan-review-mimo-20260518.md`
