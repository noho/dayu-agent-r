# WU-SEMANTIC-OWNERSHIP-01 P3-K Plan Review

- **Reviewed target:** `docs/host/wu-semantic-ownership-01-p3-k-test-harness-semantic-coupling-plan.md`
- **Review scope:** P3-K plan only (test harness semantic coupling cleanup)
- **Reviewer:** AgentMiMo (adversarial plan review)
- **Review date:** 2026-07-11
- **Design sources:** `docs/host/design.md`, `docs/engine/design.md`
- **Control doc:** `docs/host/issues-implementation-control.md`
- **Goal confirmation:** `docs/reviews/wu-semantic-ownership-01-p3-k-goal-confirmation.md`
- **Source adjudication:** `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- **Source evidence:** `docs/reviews/2026-07-10-semantic-ownership-drift-review.md` TF-1..TF-5

---

## Assumptions Tested

| # | Assumption | Verdict | Evidence |
|---|-----------|---------|----------|
| A1 | TF-1 memory projection tuple locks are ownerless parallel truth | **Confirmed** | `test_memory_projection.py:694,700-703` uses `tuple(field.name ...) == _TUPLE` — strictest form of field lock (identity + ordering). These are not wire-serialized types; `MemoryProjectionPolicy` and `ConversationMemorySnapshotVNext` are internal Host projection types. |
| A2 | TF-1 tool result envelope locks are legitimate public contract | **Confirmed** | `test_tool_result_envelope.py:123-126` uses set equality + `isdisjoint` against await fields. `ToolResultSuccess`/`ToolResultFailure` are wire-serialized. The plan correctly preserves these. |
| A3 | TF-1 Engine event contract locks are legitimate public contract | **Confirmed** | `test_engine_event_contract.py` uses set equality for wire values, frozenset for terminal set, set for dataclass fields. All are `EngineEvent` stream contracts. The plan correctly preserves these. |
| A4 | TF-2 raw SQL reads can be replaced by production helpers | **Partially false** | Most raw SQL reads are global aggregates (global event_type count, total event count, MAX sequence, all-instance list) that no production helper exposes. `projection_checkpoint_sequence` is replaceable via `read_projection_checkpoint()` but needs `HostTransaction`. Only `event_type_count` in `recovery_support.py:712` has a partial production equivalent (`count_committed_events_by_run_and_type` scopes by run). |
| A5 | TF-4 cancellation fakes have divergent semantics | **Confirmed** | `StubCancellationToken` subclasses protocol, uses UTC-aware timestamps, idempotent `request_cancel()`. `FakeCancellationToken` uses naive `datetime.now()`, non-idempotent `trigger()`. `_FakeCancellationToken` is a never-cancelled stub with no mutation. |
| A6 | TF-5 resume guidance assertions pin non-contract wording | **Partially false** | Lines 546-548 (tool name, status, result) are already owner-derived semantic assertions. Lines 545, 549 pin hardcoded prose from `run_input.py:3524,3528`. The positive assertions are a mix of semantic content and hardcoded prose — not uniformly "non-contract wording." |
| A7 | The three slices are semantically coherent | **Confirmed** | S1 (assertion style), S2 (raw SQL boundary), S3 (test double consolidation) separate cleanly along ownership boundaries. No cross-slice file conflicts. |
| A8 | Stop conditions are well-defined | **Confirmed** | Each slice has a clear stop condition that triggers return to plan review. |

---

## Findings

### 01-未修复-中-S1 resume guidance helper 混淆语义内容断言与硬编码散文断言

- **位置**: S1 `tests/host/test_run_input_builder.py` 部分，`_assert_resume_guidance_semantics` helper 设计
- **问题类型**: 最佳实践偏离 / 非最优方案
- **当前写法**: Plan 提出用一个 helper 替换"exact non-contract wording checks"，helper 必须断言 5 个语义事实（prior waiting step completed, tool name visible, completion status visible, result payload visible, instruction not to restart）。Plan 声称目标是"protect required semantics and leakage boundaries without requiring exact prose"。
- **反例/失败场景**: 当前测试的 5 个正向断言中，3 个（lines 546-548）已经是 owner-derived 语义断言——它们检查 `_required_payload_text(payload, field_name=...)` 和 `projection.status.value` 产出的动态内容，而非固定散文。另外 2 个（lines 545, 549）断言的子串 `"上一轮被等待中断的外部工具步骤已经完成"` 和 `"不要为了同一次请求再次启动相同下载、上传或处理"` 来自 `run_input.py:3524,3528` 的硬编码常量。这些硬编码散文是 `run_input` 模块对 LLM 的具体指令承诺——它们不是"非契约措辞"，而是 resume guidance 的实际 contract content。用一个检查"语义事实"的 helper 替换这些断言，要么 helper 仍然需要精确子串检查（与当前写法等价），要么 helper 变成模糊的 substring-in-content 检查（弱化覆盖）。
- **为什么有问题**: Plan 把所有 5 个正向断言统一归类为"non-contract wording checks"，但实际代码中只有 2 个是硬编码散文，3 个已经是 owner-derived 语义断言。这种混淆会导致 implementation agent 不知道哪些断言需要保留精确子串、哪些可以放松。
- **直接证据**:
  - `run_input.py:3524`: `_RESUME_WAIT_FALLBACK_INTRO = "上一轮被等待中断的外部工具步骤已经完成。"` — 硬编码常量
  - `run_input.py:3528`: `_RESUME_WAIT_FALLBACK_NO_REPEAT = "不要为了同一次请求再次启动相同下载、上传或处理"` — 硬编码常量
  - `test_run_input_builder.py:546`: `assert "完成的工具：fake_tool" in message.content` — owner-derived（tool name from payload）
  - `test_run_input_builder.py:547`: `assert "完成状态：completed" in message.content` — owner-derived（status from projection）
- **影响**: Implementation agent 可能将 owner-derived 语义断言也替换为模糊 helper，实际弱化覆盖；或者将硬编码散文断言替换后，无法检测到 `run_input.py` 中 resume guidance 指令的回归。
- **建议改法和验证点**:
  1. 明确区分两类断言：(a) owner-derived 语义断言（tool name, status, result）——保持不变或用 helper 包装但保留精确检查；(b) 硬编码散文断言（intro, no-repeat instruction）——要么保留精确子串检查（因为它们是 `run_input` 模块的 contract content），要么改为检查 `_RESUME_WAIT_FALLBACK_INTRO` / `_RESUME_WAIT_FALLBACK_NO_REPEAT` 常量的 presence（将断言绑定到 production 常量而非字面量）。
  2. Helper 的 docstring 必须说明它断言的是哪些具体的 production-owned 语义事实，而非泛泛的"semantic content"。
  3. 验证：故意修改 `run_input.py:3524` 的常量值，确认测试仍然能捕获回归。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 02-未修复-中-S2 raw SQL 替换策略高估了可替换范围

- **位置**: S2 "Exact allowed changes" 和 "Completion signal"
- **问题类型**: 不可直接实施
- **当前写法**: Plan 声称"Replace raw reads with production durable read helpers where available"，completion signal 说"Replaceable raw SQL reads are gone or routed through owner helpers"。
- **反例/失败场景**: 经过代码验证，S2 涉及的 8 个 raw SQL helper 中，大部分无法被 production helper 替换：
  - `_diagnostic_event_type_count`（全局 event_type count）：production `count_committed_events_by_run_and_type` 需要 `run_id`，语义不同。
  - `event_type_count`（同上）。
  - `read_latest_event_sequence`（全局 MAX sequence）：production 无等价 helper。
  - `read_event_log_count`（全局 count）：production 无等价 helper。
  - `read_host_instances`（全实例 list）：production `read_host_instance` 只按 ID 读单行。
  - `projection_checkpoint_sequence`：可被 `read_projection_checkpoint()` 替换，但需要 `HostTransaction` 依赖。
  - 2 个 WRITE helper（fault injection）：plan 已正确识别为保留。
  实际可替换的只有 `projection_checkpoint_sequence` 一个。Plan 的 completion signal "Replaceable raw SQL reads are gone" 暗示有多个可替换项，但实际几乎全部需要保留为 raw SQL。
- **为什么有问题**: Implementation agent 可能花费大量时间尝试替换实际不可替换的 raw SQL，最终发现必须保留大部分。Plan 应明确哪些 helper 可替换、哪些保留为 diagnostic-only。
- **直接证据**:
  - `EventLogStore.count_committed_events_by_run_and_type(event_log.py:416)` 需要 `run_id` 参数
  - `HostInstanceLivenessStore.read_host_instance(liveness.py:164)` 按 ID 读单行
  - `read_projection_checkpoint(projection.py:87)` 返回 `ProjectionCheckpointRow`，需要 `HostTransaction`
- **影响**: Implementation agent 实施时间浪费；可能强行引入不合适的 production helper 调用来"完成"替换目标。
- **建议改法和验证点**:
  1. 在 S2 中明确列出每个 raw SQL helper 的替换决策：可替换（用 production helper）、保留为 diagnostic-only（raw SQL + docstring）、保留为 fault injection（raw SQL + docstring）。
  2. 预期结果应改为："Raw SQL reads that have exact production equivalents are replaced; remaining raw SQL is explicitly documented as diagnostic-only or fault-injection-only."
  3. 对于 `projection_checkpoint_sequence`，明确需要引入 `HostTransaction` 依赖，或决定保留 raw SQL。
  4. 验证：列出 S2 实施后的 raw SQL 行数，确认只减少合理数量。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 03-未修复-低-ControllableCancellationToken 未明确 never-cancelled 构造方式

- **位置**: S3 `tests/host/fake_cancellation.py` 设计
- **问题类型**: 契约缺失
- **当前写法**: Plan 提出 `ControllableCancellationToken` 需要实现 `CancellationToken` 协议，有 `request_cancel(reason)` mutation 方法，并提供"an open-token constructor/default state instead of separate fake classes"。
- **反例/失败场景**: `tests/service/test_fins_direct.py` 的 `_FakeCancellationToken` 是一个 never-cancelled stub——`is_cancelled()` 始终返回 `False`，没有 mutation 方法。Plan 说"If a local never-cancelled stub remains, it must be named as an open observation stub and must not have mutation semantics"，但这意味着 `ControllableCancellationToken` 默认状态应该是 open（not cancelled），且 caller 可以选择不暴露 mutation 方法。如果 `ControllableCancellationToken` 的默认构造就是 open 状态且有 `request_cancel` 方法，那么 `test_fins_direct.py` 可以用 `ControllableCancellationToken()` 替代 `_FakeCancellationToken`——但 plan 没有明确这一点。
- **为什么有问题**: S3 涉及 3 个不同的 fake（controllable、never-cancelled、naive-timestamp），plan 对 controllable 的设计足够具体，但对 never-cancelled case 的处理只有一句话，implementation agent 需要自行决定是否用 `ControllableCancellationToken()` 替代 `_FakeCancellationToken`。
- **直接证据**: `test_fins_direct.py:45-73` — `_FakeCancellationToken` 无 mutation，always not cancelled。
- **影响**: Implementation agent 可能保留 `_FakeCancellationToken` 作为独立类（plan 允许），或替换为 `ControllableCancellationToken()`（plan 也允许），导致 S3 产出不一致。
- **建议改法和验证点**:
  1. 在 S3 中明确：`ControllableCancellationToken()` 默认构造为 open state（not cancelled），caller 可选调用 `request_cancel()` 触发取消。`test_fins_direct.py` 中的 never-cancelled case 直接用 `ControllableCancellationToken()` 替代，不保留 `_FakeCancellationToken`。
  2. 或者明确：`_FakeCancellationToken` 保留为 open observation stub，不导入 canonical helper。
  3. 验证：S3 完成后，`test_fins_direct.py` 中 cancellation token 的来源和语义。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 04-未修复-低-README 触发决策矩阵缺少"无需更新"显式声明

- **位置**: Section 6 "README / Docs Decision"
- **问题类型**: 契约缺失
- **当前写法**: Plan 列出 3 个条件（S1 引入新 LLM assertion helper、S2 引入 shared durable diagnostic helper、S3 重命名/consolidation helper），但没有说明当所有条件都不满足时的行为。
- **反例/失败场景**: 如果 S1 不引入新 helper 文件（只修改现有测试），S2 不引入新共享 helper，S3 不改变 README 已文档化的 helper 名称，那么 plan 没有显式声明"tests/README.md 无需更新"。Implementation agent 可能不确定是否需要检查 README。
- **为什么有问题**: Goal confirmation 的 success signal 包含"README trigger decision is recorded"。如果 implementation agent 不记录 decision（因为 plan 没说"无条件满足时记录 no-update"），completion report 可能遗漏此项。
- **直接证据**: Section 6 列出条件但无 else 分支。
- **影响**: Completion report 遗漏 README trigger decision 记录。
- **建议改法和验证点**:
  1. 在 Section 6 末尾添加："If none of the above conditions are met, implementation must record 'tests/README.md: no update needed' in the completion report."
  2. 验证：completion report 包含 README trigger decision。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## Open Questions

### OQ-1: S1 `_assert_resume_guidance_semantics` helper 是否需要引用 production 常量？

Plan 说"Replace exact non-contract wording checks with semantic-content helper assertions"，但当前的"exact wording"断言来自 `run_input.py` 的硬编码常量。如果 helper 断言的是"the content tells the LLM a prior waiting external tool step has completed"，它需要检查什么？是检查 `_RESUME_WAIT_FALLBACK_INTRO` 常量的 presence（绑定到 production 常量）？还是检查任意包含"等待"和"完成"的子串（太 loose）？Implementation agent 需要 plan 给出具体的 helper 实现策略。

**建议目的地**: 在 plan 中补充 helper 实现策略说明。

### OQ-2: `tests/host/llm_text_assertions.py` 是否真的需要？

Plan 列为"Optional helper file if needed for assertion reuse"。S1 的 LLM-facing 断言只涉及 `test_run_input_builder.py` 和 `test_memory_projection.py`，且两者的断言模式不同（前者是 resume guidance，后者是 evidence text）。是否真的需要一个共享 helper 文件？还是各自在测试文件中定义私有 helper 即可？

**建议目的地**: Implementation agent 在 S1 实施时决定，但 plan 应明确这是 optional。

### OQ-3: S3 Engine runner tests 迁移是否需要同步修改 test assertions？

S3 将 Engine runner tests 从 `FakeCancellationToken`（naive datetime）迁移到 `ControllableCancellationToken`（UTC-aware datetime）。如果现有测试断言了 `requested_at()` 的 timezone-naive 值，迁移后这些断言会失败。Plan 没有提到需要更新 Engine runner test assertions。

**建议目的地**: Implementation agent 在 S3 实施前检查 Engine runner tests 的 timestamp assertions。

---

## Residual Risks

| # | Risk | Severity | Tracking destination |
|---|------|----------|---------------------|
| R1 | S1 resume guidance helper 可能弱化 hardcoded prose 覆盖 | 中 | Plan 中补充 helper 实现策略 |
| R2 | S2 raw SQL 替换范围远小于 plan 暗示的范围 | 中 | Plan 中明确每个 helper 的替换决策 |
| R3 | S3 迁移 cancellation fakes 可能触发 Engine runner test timestamp 断言失败 | 低 | Implementation agent 在 S3 实施前检查 |
| R4 | LLM-facing semantic assertions 如果实现为 vague substring checks 会弱化覆盖 | 低 | Plan 已在 Residual Risks 中记录，S1 必须 assert concrete required semantic facts |
| R5 | Keeping Engine exact protocol locks 可被挑战为 over-strict | 低 | Plan 已在 Residual Risks 中记录，当前 design treats these as public contracts |

---

## Final Plan Review Conclusion

**pass-with-risks**

Plan 的整体方向正确：partial-preservation stance 合理，三个 slices 语义清晰，stop conditions 完善，non-goals 明确。主要风险集中在：

1. S1 的 resume guidance helper 设计需要更具体的实现策略，避免混淆 owner-derived 语义断言与硬编码散文断言（Finding 01，中等严重度）。
2. S2 的 raw SQL 替换策略高估了可替换范围，需要明确每个 helper 的具体决策（Finding 02，中等严重度）。

这两个 finding 不构成 blocker，但需要在 implementation 前补充说明，否则 implementation agent 容易跑偏。建议 controller 裁决后，由 plan author 补充相关说明，再进入 implementation gate。
