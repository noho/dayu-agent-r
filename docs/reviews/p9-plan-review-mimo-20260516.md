# P9 Plan Review — Conversation Memory / Session Memory Projection

- Reviewer: AgentMiMo
- Date: 2026-05-16
- Artifact: `docs/host/phase9-conversation-memory-plan.md`
- Design truth: `docs/host/design.md` §23, §24, §26
- Control truth: `docs/host/implementation-control.md` Phase 9 条目 & P9 design refinement 追踪
- Codebase snapshot: branch `feat/host-p9-conversation-memory`, commit `f27ce8a`

---

## Verdict

**PASS with 2 blocking, 5 medium, 3 low findings.**

Plan 整体动机判断正确、scope 克制、typed contracts 设计充分、slice 切分合理、业务中立约束明确。2 个 blocking findings 均为 provider 接线策略的未决问题，不改变 plan 架构方向，但 implementation agent 若不先澄清会在 Slice 3 遇到阻塞。

---

## Findings

### B-1. SessionContinuityProvider 与 DurableMemorySnapshotProvider 接线关系未决 [BLOCKING]

**Evidence:**
- 当前 `RunInputBuilder.build()` (`run_input.py:831-845`) 在 messages 构造中同时使用 `memory.messages` 和 `continuity.messages`：
  ```python
  messages = (
      *scene_messages,
      *memory.messages,
      *compact.messages,
      *continuity.messages,
      UserMessage(...user_prompt...),
  )
  ```
- Plan §7 说 "P9 不应让 raw continuity 绕过 memory 预算无限注入。实现可以把 continuity provider 的历史 raw turns 职责收敛进 memory history pool，或让 durable memory provider 复用 EventLog continuity reader 并返回已预算的 memory messages；若保留 `SessionContinuityProvider`，其输出必须受同一 history pool 预算约束，不能绕过 memory budget。"
- 但 plan 没有做出选择：是 **替换** `SessionContinuityProvider`（memory provider 全部承担 continuity 职责），还是 **保留并约束**（两个 provider 共存但 continuity 受 memory budget 限制）。
- 当前 `create_no_tool_run_input_builder` 和 `create_tool_enabled_run_input_builder` 都硬编码 `DurableSessionContinuityProvider`。如果保留两个 provider，需要新增预算协调机制；如果替换，需要重构 factory 函数签名。

**Impact:** Implementation agent 在 Slice 3 无法确定 `RunInputBuilder` 的 provider 接线策略，可能做出与后续 slice 冲突的选择。

**Recommendation:** Plan §7 或 Slice 3 应明确选择其一并说明理由。推荐：memory provider 承担 history pool 全部职责（raw turns + episode summaries），`SessionContinuityProvider` 标记为 deprecated / Phase 10 移除；P9 factory 函数可暂时保留 continuity provider 参数但其输出应为空或受 memory provider 控制。

---

### B-2. MemorySnapshotView 扩展与 RunInputBuilder.build() 全局 messages 结构未明确 [BLOCKING]

**Evidence:**
- Plan §7 定义了 memory messages 内部顺序（用户目标与约束 → 已确认主体和口径 → tool-verified facts → open questions/assumptions → recent raw turns → episode summaries），但没有定义这些 memory messages 在 `RunInputBuilder.build()` 全局 messages 中如何与 scene messages、compact messages、continuity messages、current user prompt 交互。
- 当前 `build()` 的顺序是 `scene → memory → compact → continuity → user_prompt`。
- Plan §7 说 "P9 不重写 compact artifact、current user、guidance、tool schema 或 policy 的全局 provider 位置"，但没有明确 memory messages 是否继续用 `SystemMessage` 分块，以及当前 `USER_INPUT_ACCEPTED` 是否仍由 `CurrentRunFactProvider` 作为最后的 `UserMessage` 注入。
- `MemorySnapshotView` 当前只有 `messages` 和 `memory_snapshot_cursor`。Plan §7 说要扩展 `policy_digest` 和 `diagnostics`，但没有说明 `MemorySnapshotProvider` 协议签名是否变化、是否需要 backward-compatible。

**Impact:** Implementation agent 在 Slice 3 无法确定 `MemorySnapshotView` 的最终形状和 `build()` 的 messages 拼装逻辑。

**Recommendation:** Slice 3 应明确：
1. `MemorySnapshotView` 新增字段列表（`policy_digest: str | None`, `diagnostics: tuple[MemoryDiagnostic, ...]`）。
2. `build()` 全局 messages 顺序不变（scene → memory → compact → continuity → user_prompt），memory messages 内部按 plan §7 顺序用 `SystemMessage` 分块。
3. `create_no_tool_run_input_builder` / `create_tool_enabled_run_input_builder` 新增可选 `memory_snapshot_provider` 参数，默认 `NoopMemorySnapshotProvider`。

---

### M-1. History pool 预算机制未具体化 [MEDIUM]

**Evidence:**
- Plan §4.6 定义了 `MemoryProjectionPolicy` 的预算参数（`history_pool_size_units`, `stable_layer_size_units`, `recent_raw_turns_floor`），§4.7 定义了 `OVER_HISTORY_POOL_LIMIT`, `OLDER_RAW_TURN_DEGRADED`, `EPISODE_SUMMARY_DEGRADED` 等 excluded reasons。
- 但 plan 没有说明 history pool 的具体预算算法：如何计算单个 raw turn / episode summary 的 size units？降级顺序是先 episode summary 后 older raw turns，还是按时间倒序逐条降级？recent raw turns floor 是按条数还是按 size units？
- Plan §4.6 说 "第一版 size units 可以是保守字符数或简化 token estimator"，但没有给出默认 safety margin 比例。

**Impact:** Slice 2 的 stable layer / history pool builder 缺少具体算法指引，implementation agent 可能做出与设计意图不一致的降级行为。

**Recommendation:** Slice 2 应补充：
1. Size unit 计算方式（字符数 × 1.5 或等价保守 estimator）。
2. 降级顺序：先降级 episode summaries（按时间倒序），再降级 older raw turns（按时间倒序），recent raw turns floor 按条数保底。
3. 默认 safety margin（例如 stable layer 占总预算 40%，history pool 占 60%）。

---

### M-2. OpaqueMemoryRef 业务中立校验规则未明确 [MEDIUM]

**Evidence:**
- Plan §4.3 定义 `OpaqueMemoryRef` 只允许 `ref_kind: str`, `ref_id: str`, `digest: str | None`，并说 "`ref_kind` 不能编码财报业务类型，例如 company、business_line、technology_release"。
- 但 plan 没有给出校验机制：是在 contract `__post_init__` 中硬编码禁止列表？还是只靠 code review 约束？禁止列表如何维护？
- Anti-hallucination test matrix §9 最后一条提到 "Host memory schema 不出现 company、business_line、technology_release 等业务字段"，但没有提到 `OpaqueMemoryRef.ref_kind` 的校验测试。

**Impact:** 若 implementation agent 不主动实现校验，业务语义可能通过 `ref_kind` 泄漏进 Host schema。

**Recommendation:** Slice 1 typed contract 应在 `OpaqueMemoryRef.__post_init__` 中实现 `ref_kind` 禁止列表校验（`_HOST_NEUTRAL_REF_KIND_BLOCKLIST`），并在 test 中覆盖。

---

### M-3. PinnedStateView 子字段与 design §24 不完全对齐 [MEDIUM]

**Evidence:**
- Design §24 定义 `pinned_state` 至少包含 `current_goal`, `confirmed_subjects`, `user_constraints`, `open_questions`。
- Plan §4.1 的 `ConversationMemorySnapshot` 将 `pinned_state` 和 `working_assumptions` 作为 peer fields，但 `open_questions` 在设计中是 `pinned_state` 的子字段。
- Plan §4.1 没有定义 `PinnedStateView` 的具体字段结构，implementation agent 可能把 `open_questions` 放在 `working_assumptions` 或单独的 view 中。

**Impact:** Memory view 的结构可能与设计 §24 不一致，影响后续 Phase 10 Context Governance 的预算分配。

**Recommendation:** Slice 1 应明确 `PinnedStateView` 包含 `current_goal: str | None`, `confirmed_subjects: tuple[OpaqueMemoryRef, ...]`, `user_constraints: tuple[str, ...]`, `open_questions: tuple[str, ...]`。

---

### M-4. TOOL_RESULT_ACCEPTED payload 映射到 VerifiedFactView 的具体路径未明确 [MEDIUM]

**Evidence:**
- Plan §4.4 定义了 fact summary 来源优先级（payload summary → tool result descriptor summary → neutral fallback），但没有说明 `TOOL_RESULT_ACCEPTED` payload 的具体字段结构。
- 当前 `run_input.py` 中 `_resume_wait_message_from_current_start` 读取 `TOOL_RESULT_ACCEPTED` payload 的 `wait_id`, `tool_call_id`, `tool_name`, `resolution_kind`, `tool_fact_kind`, `result` 字段。
- Plan 没有说明哪些 payload 字段映射到 `VerifiedFactView.fact_summary`、哪些映射到 `provenance.tool_result_ref`、哪些映射到 `subject_refs`。

**Impact:** Slice 2 的 verified fact extraction 实现可能与 ToolRuntime 的 payload 结构不匹配。

**Recommendation:** Slice 2 应参考 `tool_runtime.py` 中 `TOOL_RESULT_ACCEPTED` 的 payload 结构，明确字段映射关系。

---

### M-5. After-commit catch-up hook 注入点未明确 [MEDIUM]

**Evidence:**
- Plan §6 说 "P9 可以在 Host command / dispatch composition root 中注册 memory consumer 的 catch-up hook"。
- Plan Slice 4 允许修改 `dayu/host/command.py` or scheduler/composition root。
- 但当前 `dispatch.py` 是主要 composition root，没有 `command.py`。Plan 没有说明 hook 注入在 dispatch 的哪个生命周期点（commit 后？worker accept 后？attempt terminal 后？）。

**Impact:** Slice 4 的实现可能选择错误的 hook 点，导致 catch-up 时机不当。

**Recommendation:** Slice 4 应明确 hook 注入在 `dispatch.py` 的 `_after_commit_projection_catch_up` 或等价位置，且 hook 在 EventLog append commit 之后、Run terminal 之前执行。

---

### L-1. ClaimStatus 新增值超出设计范围 [LOW]

**Evidence:**
- Plan §4.2 定义了 6 个 `MemoryClaimStatus`：`TOOL_VERIFIED`, `ASSUMPTION`, `CANDIDATE`, `CONFLICTED`, `STALE`, `SUPERSEDED`。
- Design §24 只提到 "verified facts" vs "working assumptions" vs "candidate"，以及 stale / conflict 的概念。
- `CONFLICTED`, `STALE`, `SUPERSEDED` 是 plan 新增的状态，设计中没有显式定义。

**Impact:** 扩展 claim status 是合理的，但可能增加后续 maintenance surface。

**Recommendation:** 保留，但在 plan 中标注这些状态是 P9 对 design §24 的合理扩展，后续 issue 39 可能进一步扩展。

---

### L-2. MemoryDiagnostic 与 projection failure 的关系未明确 [LOW]

**Evidence:**
- Plan §4.7 定义了 included / excluded reasons，§4.1 的 `ConversationMemorySnapshot` 包含 `diagnostics: tuple[MemoryDiagnostic, ...]`。
- Plan §6 说 "projection failure 使用现有 `host_projection_failures`"。
- 但没有说明 `MemoryDiagnostic` 是写入 `host_memory_diagnostics` 表还是写入 `host_projection_failures` 表，或者两者都写。

**Impact:** Implementation agent 可能做出不一致的 diagnostic 持久化选择。

**Recommendation:** Slice 1 应明确 `MemoryDiagnostic` 写入 `host_memory_diagnostics` 表（plan §5 已定义），projection-level failure 写入 `host_projection_failures`。

---

### L-3. Snapshot stability 测试方法未具体化 [LOW]

**Evidence:**
- Plan §9 anti-hallucination test matrix 要求 "同一 EventLog + 同一 policy digest 生成稳定 snapshot digest 和 stable messages"。
- 但没有说明如何测试：是构造固定 EventLog fixtures 然后多次 rebuild？还是通过 projection runner 多次 catch-up 比较 digest？

**Impact:** Slice 2 测试可能遗漏 stability 测试的具体实现路径。

**Recommendation:** Slice 2 测试应使用固定 EventLog fixtures + 固定 policy，多次 rebuild 后断言 `snapshot_digest` 相同。

---

## Conformance Checklist

| 检查项 | 结果 | 说明 |
|--------|------|------|
| Plan 满足 P9 目标 | PASS | session-level memory projection, stable layer, history pool, provider 接线, repair path 均在 scope 内 |
| Plan 满足 P9 success signal | PASS | RunInputBuilder 可稳定消费 memory snapshot；projection lag 不改变 Run 状态 |
| "财报分析工作台状态投影"定位 | PASS | §1 动机判断正确，§2 scope 明确 non-goals |
| 四类 memory view 清晰 | PASS | §4.1 定义完整，§4.4 verified facts provenance 充分 |
| Verified facts provenance | PASS | §4.3 provenance refs 设计详细，event_id/event_sequence/tool_result_ref 均保留 |
| Working assumptions 边界 | PASS | §4.2 claim status 区分 TOOL_VERIFIED vs ASSUMPTION vs CANDIDATE |
| Conversation continuity | PASS | §7 明确 recent raw turns floor + episode summaries 导航 |
| Host 业务中立边界 | PASS | §2 non-goals 明确禁止 fins import、业务字段、业务原文 |
| 不实现长期 retrieval | PASS | §2 non-goals 明确 |
| 不实现业务 signal ledger | PASS | §2 non-goals 明确 |
| 不实现 signal-to-outcome verification | PASS | §2 non-goals 明确 |
| 不实现 public edit/reset/forget API | PASS | §2 non-goals 明确 |
| RunInputBuilder provider boundary | PASS with caveats | §7 正确保持 typed boundary，但 B-1/B-2 需澄清 |
| 全局 message order | PASS | §7 引用 §23 顺序，memory 内部顺序独立定义 |
| USER_INPUT_ACCEPTED 事实入口 | PASS | §7 明确 "当前 USER_INPUT_ACCEPTED 仍由 CurrentRunFactProvider 读取" |
| Projection lag 不触发 Run recovery | PASS | §4.8 和 §6 明确 repair path 不修改 Run/Attempt 状态 |
| Slice 切分合理 | PASS | 5 slices 渐进式，依赖关系清晰 |
| Typed contracts 充分 | PASS | §4 定义 10+ dataclass/enum/protocol |
| Tests 覆盖充分 | PASS | §9 anti-hallucination matrix 12 项 |
| Pyright 要求 | PASS | §10 verification commands 包含 pyright |
| README 触发规则 | PASS | §11 明确 |
| Residual risks 有 owner | PASS | §12 每项有明确 owner |

---

## Summary

Plan 是 implementation-ready 的，架构方向正确、scope 克制、typed contracts 设计充分。2 个 blocking findings（provider 接线策略、MemorySnapshotView 扩展）是 Slice 3 的前置澄清项，不改变 plan 架构。建议 controller 在 dispatch implementation 前要求 planning agent 补充 B-1 和 B-2 的明确决策。
