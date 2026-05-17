# P9 Plan Re-Review — Conversation Memory / Session Memory Projection

- Reviewer: AgentMiMo
- Date: 2026-05-16
- Artifact: `docs/host/phase9-conversation-memory-plan.md` (updated)
- Previous review: `docs/reviews/p9-plan-review-mimo-20260516.md`
- Design truth: `docs/host/design.md` §23, §24, §26
- Control truth: `docs/host/implementation-control.md` Phase 9 条目 & P9 design refinement 追踪
- Codebase snapshot: branch `feat/host-p9-conversation-memory`, commit `f27ce8a`

---

## Verdict

**PASS. 0 remaining blocking findings. All 2 blocking, 5 medium, 3 low findings from previous review are resolved. No new blocking issues introduced.**

---

## Previous Findings Resolution

### B-1. SessionContinuityProvider 与 DurableMemorySnapshotProvider 接线关系 — RESOLVED

**Evidence of resolution:**

Updated plan §7 新增 "明确接线决策" (lines 440-445):
- "P9 primary path 是把 historical raw turns 与 episode summaries 移入 `MemorySnapshotProvider` / history pool，由 memory policy 成为单一预算权威。"
- "`SessionContinuityProvider` 可以保留，但只允许承载非 raw history 的 continuity / resume-specific facts，例如当前 resume wait result message；或者对 raw history 返回 no-op。"
- "`SessionContinuityProvider` 不得再注入未经过 memory history pool 预算的历史 raw user / assistant turns。"

Slice 3 (lines 568-575) 补充 stop condition:
- "Historical raw user / assistant turns 只来自 memory history pool 或 no-op，不再从 `SessionContinuityProvider` 绕过预算进入 messages。"
- "`SessionContinuityProvider` 若保留，只处理 resume-specific / non-history continuity facts。"

Anti-hallucination matrix §9 (line 656) 新增:
- "`SessionContinuityProvider` 不注入未预算 historical raw turns；raw history 由 memory history pool 统一预算。"

**Assessment:** 决策清晰——memory provider 是历史 raw turns 的唯一预算权威，`SessionContinuityProvider` 收敛为 resume-specific 专用。Implementation agent 有明确指引。

---

### B-2. MemorySnapshotView 扩展与 RunInputBuilder.build() 全局 messages 结构 — RESOLVED

**Evidence of resolution:**

Updated plan §7 (lines 419-424) 明确 `MemorySnapshotView` 扩展:
- "`MemorySnapshotView`，provider protocol 仍返回 `MemorySnapshotView`，不改成 tuple / dict / extra payload"
- 字段: `messages`, `memory_snapshot_cursor`, `policy_digest: str | None`, `diagnostics: tuple[MemoryDiagnostic, ...]`

§7 (line 428) 明确 factory 函数签名:
- "`create_no_tool_run_input_builder` 与 `create_tool_enabled_run_input_builder` 增加可选 `memory_snapshot_provider` 参数，默认仍可使用 no-op provider 以支持测试和未接线场景"

§7 (lines 429-437) 明确全局 ordering:
- "RunInputBuilder 全局 message ordering 必须继续遵循 `docs/host/design.md` §23"
- "`USER_INPUT_ACCEPTED` 仍由 `CurrentRunFactProvider` 读取并按 §23 进入当前 Run canonical facts"

Slice 3 (lines 561-562) 补充测试要求:
- "`MemorySnapshotView` 保持 provider protocol 返回值，字段包含 `messages`、`memory_snapshot_cursor`、`policy_digest`、`diagnostics`；factories 支持可选 `memory_snapshot_provider`，默认 `NoopMemorySnapshotProvider`。"

**Assessment:** `MemorySnapshotView` 形状、factory 签名变化、全局 ordering 不变——三项均明确。Implementation agent 可以直接编码。

---

### M-1. History pool 预算机制 — RESOLVED

**Evidence of resolution:**

Updated plan §4.7 (lines 259-265) 新增 "History pool 算法必须具体但克制":
- "size units 使用 memory policy 中同一个保守 estimator helper" — 统一口径。
- "`recent_raw_turns_floor` 是 count-based floor，并对单条 turn 设置 policy 定义的 per-turn safety cap" — 明确 floor 是条数，单条有上限。
- "`older_raw_turns` 与 `episode_summaries` 共享 `history_pool_size_units`，不引入任意 40/60 或其它固定比例拆分" — 拒绝固定比例。
- "降级顺序固定为：先降级 episode summaries，再降级 older raw turns" — 明确降级顺序。
- "recent raw turns floor 最后降级；若极低预算下 floor 也无法完整容纳，必须保留可解释的最小连续性片段并记录 diagnostic" — 极端情况兜底。

§4.7 (lines 268-271) 补充 canonical digest 规则:
- "tuple/list 顺序必须来自 EventLog sequence 或 policy 明确排序"
- "`built_at`、`updated_at` 等非确定性字段不得进入 digest input"

**Assessment:** 预算算法足够 implementation agent 编码，不引入过度约束。

---

### M-2. OpaqueMemoryRef 业务中立校验 — RESOLVED

**Evidence of resolution:**

Updated plan §4.3 (lines 156-161):
- `ref_kind` 改为 `HostNeutralRefKind` enum/StrEnum，列出允许值: `SOURCE`, `CHUNK`, `ENTITY`, `SUBJECT`, `TOPIC`, `EVIDENCE`, `PAYLOAD`, `EXTERNAL`。
- "不要实现脆弱的业务词 blocklist" — 拒绝 blocklist 方案。
- "测试应断言 schema / contract 不包含业务专有字段，且 Host 不解释 `ref_kind` 的财报业务语义" — 测试覆盖。

Slice 1 (line 483) 补充测试要求:
- "`OpaqueMemoryRef.ref_kind` 只接受 Host-neutral enum 值；schema / contracts 不包含业务专有字段"

Anti-hallucination matrix §9 (line 659) 补充:
- "`OpaqueMemoryRef.ref_kind` 使用 Host-neutral enum，Host 不解释业务语义"

**Assessment:** 用 enum 白名单替代 blocklist，更安全、更可维护。测试覆盖充分。

---

### M-3. PinnedStateView 子字段 — RESOLVED

**Evidence of resolution:**

Updated plan §4.1 (lines 100-110) 新增:
```text
PinnedStateView
  current_goal: str | None
  confirmed_subjects: tuple[OpaqueMemoryRef, ...]
  user_constraints: tuple[str, ...]
  open_questions: tuple[str, ...]
```
- "`open_questions` 只存放在 `PinnedStateView`，不得在 `WorkingAssumptionView` 或其它顶层字段中重复存储。"
- "Memory provider messages 中的 'open questions / working assumptions' 表示先渲染 pinned state 中的 open questions，再渲染 working assumptions。"

Slice 1 (line 482) 补充测试要求:
- "`PinnedStateView` 包含 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions`，且 open questions 不在 working assumptions 中重复存储。"

**Assessment:** 与 design §24 完全对齐，open_questions 归属明确。

---

### M-4. TOOL_RESULT_ACCEPTED payload 映射 — RESOLVED

**Evidence of resolution:**

Updated plan §4.4 (lines 186-191) 新增 "实现 guidance":
- "先检查现有 `dayu.host.tool_runtime` 与 `dayu.host.run_input` 中的 `TOOL_RESULT_ACCEPTED` payload helper，不重新发明 payload shape。"
- 映射字段列表: `event_id`, `event_sequence`, `tool_name`, `tool_call_id`, result id / accepted result ref, `payload_ref`, `payload_digest`, `outcome_digest`, `tool_identity_digest`, `normalized_arguments_digest`。
- "`tool_result_ref` 使用当前 `TOOL_RESULT_ACCEPTED` event ref"
- "缺失 summary 时使用 `tool_name + outcome_digest + payload_ref/digest` 的中立 fallback"

Slice 2 (line 522) 补充测试要求:
- "`TOOL_RESULT_ACCEPTED` 字段映射覆盖现有 payload 中的 `tool_name`、`tool_call_id`、result id / result ref、`payload_ref` / digest、`outcome_digest` 等可用字段；字段缺失时写中立 fallback diagnostic。"

**Assessment:** Implementation agent 有明确的 payload 字段映射指引和 fallback 策略。

---

### M-5. After-commit catch-up hook 注入点 — RESOLVED

**Evidence of resolution:**

Updated plan §6 (lines 409-411):
- "不要在 plan 中假设一个当前不存在的具体 hook 名称；implementation agent 应优先复用现有 projection notification / catch-up extension point。若现有扩展点不足，只能新增最小通用 projection catch-up extension，不得写 memory 专用旁路。"

Slice 4 (lines 602-603) 补充测试要求:
- "implementation 复用现有 projection notification / catch-up extension point；若必须新增，只能新增最小通用 extension，不使用 memory 专用旁路。"

**Assessment:** 不假设不存在的 hook 名，指引 implementation agent 先探索现有扩展点。比之前建议的 "在 `dispatch.py` 的 `_after_commit_projection_catch_up`" 更务实。

---

### L-1. ClaimStatus 新增值 — RESOLVED

**Evidence of resolution:**

Updated plan §4.2 (lines 125-130) 新增:
- "P9 projection 主动产生的 claim status 只有两类: `TOOL_VERIFIED` 和 `ASSUMPTION`"
- "`CANDIDATE`、`CONFLICTED`、`STALE`、`SUPERSEDED` 是为 issue 39 / 后续长期 memory 与 query-time retrieval 预留的 enum 值；P9 不主动合成 conflict / stale / supersede。"
- "只有当前 canonical fact 已显式携带 Host 中立 claim status 时，P9 才能按该中立状态投影，不得自行推断业务冲突、陈旧或替代关系。"
- "测试必须覆盖 P9 不合成 `CONFLICTED`、`STALE`、`SUPERSEDED`。"

Anti-hallucination matrix §9 (line 650) 新增:
- "P9 不合成 `CONFLICTED`、`STALE`、`SUPERSEDED` claim status。"

**Assessment:** 明确 P9 只产生 2 类 status，reserved statuses 有 test 覆盖。

---

### L-2. MemoryDiagnostic 与 projection failure 关系 — RESOLVED

**Evidence of resolution:**

Updated plan §5 (line 373):
- "`MemoryDiagnostic` 写入 `host_memory_diagnostics` 并可同时进入 snapshot diagnostics；projection consumer 抛出的异常、EventLog row 无法投影等 runner-level failure 写入既有 `host_projection_failures`。两者职责不得混用：diagnostic 描述 memory item / budget / lag 决策，projection failure 描述 consumer 处理失败。"

Slice 1 (line 484) 补充:
- "`MemoryDiagnostic` 写入 memory diagnostics contract；projection exceptions 仍归 `host_projection_failures`。"

**Assessment:** 职责边界清晰，无歧义。

---

### L-3. Snapshot stability 测试方法 — RESOLVED

**Evidence of resolution:**

Updated plan Slice 2 (line 528):
- "固定 EventLog fixtures + 固定 policy 多次 rebuild / catch-up 产生相同 snapshot digest，且 digest 不受 `built_at` / `updated_at` 影响。"

**Assessment:** 测试方法明确，implementation agent 可直接编码。

---

## New Additions Review

### 新增 §4.5 ConversationContinuityItem

Plan 新增 `ConversationContinuityItem` typed contract (lines 193-214)，明确 `RUN_SUCCEEDED` / assistant final answer 只产生 continuity item，不进入 verified facts。字段包括 `item_kind`, `producer_kind`, `summary_text`, `payload_ref` 等。

**Assessment:** 合理扩展。与 design §24 "final_answer 只能作为 raw turn / assistant conclusion 参与连续性" 一致。优先保留 payload ref / digest 而非复制大文本，符合 Host 业务中立原则。

### 新增 canonical digest 规则

§4.7 (lines 268-271) 补充了 canonical JSON digest 的具体规则：UTF-8、sorted keys、稳定 tuple/list 顺序、确定性 null 处理、无非确定性 whitespace。

**Assessment:** 消除了 digest 实现的歧义空间，implementation agent 不需要自行猜测。

---

## Potential Non-blocking Concerns

### NB-1. MemorySnapshotView Protocol 扩展兼容性

`MemorySnapshotView` 新增 `policy_digest` 和 `diagnostics` 字段。现有 `NoopMemorySnapshotProvider` 返回 `MemorySnapshotView(messages=(), memory_snapshot_cursor=None)`，需要同步更新构造调用以包含新字段。

**Risk:** 低。更新 `NoopMemorySnapshotProvider` 是 trivial 改动，且 Slice 3 测试要求已覆盖 "Existing no-op provider tests 仍可通过"。

### NB-2. SessionContinuityProvider resume facts 边界

Plan 说 `SessionContinuityProvider` "只允许承载非 raw history 的 continuity / resume-specific facts"。当前 `_resume_wait_message_from_current_start` 是唯一的 resume-specific 逻辑，implementation agent 需要确认该逻辑不被 memory provider 重复处理。

**Risk:** 低。Slice 3 stop condition 明确 "SessionContinuityProvider 若保留，只处理 resume-specific / non-history continuity facts"。

---

## Conformance Checklist (Updated)

| 检查项 | 结果 | 变化 |
|--------|------|------|
| B-1 provider 接线 | **RESOLVED** | §7 新增明确接线决策 |
| B-2 MemorySnapshotView 扩展 | **RESOLVED** | §7 明确字段、factory 签名、全局 ordering |
| M-1 history pool 预算 | **RESOLVED** | §4.7 新增具体算法 |
| M-2 OpaqueMemoryRef 校验 | **RESOLVED** | §4.3 改用 HostNeutralRefKind enum |
| M-3 PinnedStateView 字段 | **RESOLVED** | §4.1 新增完整字段定义 |
| M-4 payload 映射 | **RESOLVED** | §4.4 新增实现 guidance |
| M-5 hook 注入点 | **RESOLVED** | §6 改为复用现有扩展点 |
| L-1 ClaimStatus 范围 | **RESOLVED** | §4.2 明确 P9 只产生 2 类 |
| L-2 Diagnostic 关系 | **RESOLVED** | §5 明确职责边界 |
| L-3 stability 测试 | **RESOLVED** | Slice 2 明确测试方法 |
| Plan 满足 P9 目标 | PASS | 不变 |
| "财报分析工作台状态投影"定位 | PASS | 不变 |
| Host 业务中立边界 | PASS | §4.3 enum 方案更安全 |
| RunInputBuilder provider boundary | **PASS** | B-1/B-2 resolved |
| Projection lag 不触发 Run recovery | PASS | 不变 |
| Slice 切分合理 | PASS | Slice 2/3 补充了更多测试要求 |
| Anti-hallucination 矩阵 | **PASS** | 新增 3 项测试覆盖 |
| 新增 ConversationContinuityItem | PASS | 合理扩展 |
| 新增 canonical digest 规则 | PASS | 消除实现歧义 |

---

## Summary

Updated plan 全部解决了前一轮 review 的 2 blocking + 5 medium + 3 low findings。关键改进：

1. **Provider 接线策略明确**：memory provider 是历史 raw turns 唯一预算权威，`SessionContinuityProvider` 收敛为 resume-only。
2. **MemorySnapshotView 形状确定**：4 字段（messages, cursor, policy_digest, diagnostics），factory 支持可选注入。
3. **History pool 算法具体化**：统一 estimator、count-based floor、共享预算、episode-first 降级。
4. **OpaqueMemoryRef 用 enum 白名单**：`HostNeutralRefKind` StrEnum 替代 blocklist。
5. **ClaimStatus 范围收窄**：P9 只产生 TOOL_VERIFIED 和 ASSUMPTION，reserved statuses 有 test 约束。
6. **Diagnostic 职责分离**：memory diagnostic vs projection failure 边界清晰。

Plan 可以进入 implementation dispatch gate。
