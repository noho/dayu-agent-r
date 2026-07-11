# WU-SEMANTIC-OWNERSHIP-01 P3-K Plan Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS
- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-p3-k-test-harness-semantic-coupling-plan.md`
- **Review date**: 2026-07-11
- **Review scope**: P3-K plan only
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Goal confirmation**: `docs/reviews/wu-semantic-ownership-01-p3-k-goal-confirmation.md`
- **Source adjudication**: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- **Source evidence**: `docs/reviews/2026-07-10-semantic-ownership-drift-review.md` TF-1..TF-5

## Assumptions Tested

| # | Assumption | Verdict |
|---|---|---|
| A1 | `_POLICY_FIELDS` / `_SNAPSHOT_FIELDS` are ownerless parallel truth, not public contract | Confirmed — design doc does not promise exact field closure for `MemoryProjectionPolicy` or `ConversationMemorySnapshotVNext`; it defines semantic sections |
| A2 | Engine wire values, terminal sets, and required fields ARE public contract | Confirmed — `docs/engine/design.md` §4, §6 explicitly define `EngineEvent` stream and data shapes as public contracts; `TERMINAL_ENGINE_EVENT_TYPES` is a design-doc-level frozen set |
| A3 | `CancellationToken` protocol defines only observation surface (3 methods), not mutation | Confirmed — `dayu/contracts/cancellation.py:28-47` defines `is_cancelled()`, `cancel_reason()`, `requested_at()` only; no `request_cancel` |
| A4 | Production durable read helpers exist for the raw SQL patterns in TF-2 | Partially confirmed — `EventLogStore.count_committed_events_by_run_and_type` exists but requires `run_id`; `EventLogStore.read_events_after` exists; `HostInstanceLivenessStore.read_host_instance` exists but plan uses wrong name `read_by_host_instance_id` |
| A5 | `advance_projection_checkpoint` / `ensure_projection_checkpoint` helpers exist | Not verified by plan — plan defers discovery to implementation |
| A6 | Slices S1/S2/S3 are semantically independent and can be implemented in any order | Mostly confirmed — S1 (assertion ownership), S2 (durable diagnostic boundary), S3 (test-double consolidation) touch different file sets with minimal overlap |
| A7 | P3-K is genuinely test-only and won't require production contract changes | Confirmed — non-goals explicitly prohibit production contract changes, and the code evidence aligns |

## Findings

### P3K-F01 [中] HostInstanceLivenessStore 方法名错误 — 实施 Agent 将浪费时间查找不存在的方法

- **位置**: S2 Exact allowed changes, "For `read_host_instances(...)` in stress helpers"
- **问题类型**: 不可直接实施
- **当前写法**: `Prefer HostInstanceLivenessStore.read_by_host_instance_id(...) only when callers have specific ids.`
- **反例/失败场景**: 实施 Agent 搜索 `read_by_host_instance_id` 会发现该方法不存在。实际方法是 `dayu/host/durable/liveness.py:164` 的 `read_host_instance(self, transaction, host_instance_id) -> HostInstanceRow | None`。实施 Agent 可能：(a) 误以为需要新增该方法，(b) 错误地在 `HostInstanceLivenessStore` 上添加 wrapper，或 (c) 浪费时间 grep 确认。
- **为什么有问题**: plan 声称 code-generation-ready，但引用了不存在的 API 名称。实施 Agent 需要自行推断正确方法名，增加出错概率。
- **直接证据**: `dayu/host/durable/liveness.py:95-175` — `HostInstanceLivenessStore` 类只有 `register_current_instance`、`heartbeat_current_instance`、`mark_current_instance_stopping`、`mark_current_instance_stopped`、`read_host_instance` 五个方法，没有 `read_by_host_instance_id`。
- **影响**: 实施 Agent 跑偏 / review 不可验收
- **建议改法和验证点**: 将 `read_by_host_instance_id(...)` 改为 `read_host_instance(...)`。验证点：`grep -r "read_by_host_instance_id" dayu/ tests/` 返回空。
- **修复风险（低）**: 纯命名修正
- **严重程度（中）**: 实施阻塞 — 引用了不存在的 API

---

### P3K-F02 [中] `_diagnostic_event_type_count` 无 run_id 的跨 Run 计数在生产 helper 中不存在 — plan 未充分分析

- **位置**: S2 Exact allowed changes, "For EventLog counting / latest-sequence reads"
- **问题类型**: 契约缺失
- **当前写法**: `Prefer opening the durable store with open_host_durable_store(...) and reading via EventLogStore().read_events_after(...) or dayu.host.durable.event_log.read_events_after_matching(...) inside store.transaction_runner.run_read(...).`
- **反例/失败场景**: `tests/host/public_smoke_support.py:1505-1524` 的 `_diagnostic_event_type_count(db_path, event_type)` 执行 `SELECT COUNT(*) FROM event_log WHERE event_type = ?` — 不按 `run_id` 过滤。`EventLogStore.count_committed_events_by_run_and_type` 要求 `run_id` 参数。`read_events_after` 按 cursor 读取，做全表计数需要从 cursor=0 读到末尾，且需要 `max_event_sequence` 去重——这在语义上是"读取所有事件再计数"，不是"SQL COUNT 聚合"。plan 的"如果无 helper 则保留 raw SQL"回退逻辑正确，但未分析这个具体 case 是否有 helper，实施 Agent 需要自行判断。
- **为什么有问题**: plan 推荐了不适用于该 diagnostic 场景的 helper（需要 run_id 过滤的 count 和需要 cursor 的逐条 read），却没有明确指出这些 helper 不适用。实施 Agent 可能强行套用，导致测试效率下降或语义错误。
- **直接证据**: `_diagnostic_event_type_count` 是跨所有 Run 的全局计数；`count_committed_events_by_run_and_type` 需要 `run_id` 参数 (`event_log.py:416-439`)。
- **影响**: 实施 Agent 跑偏 / 后续返工
- **建议改法和验证点**: 在 S2 中显式标注 `_diagnostic_event_type_count` 的 raw SQL 因为需要跨 Run 无 run_id 过滤的全局计数而保留，并在 docstring 中声明为 point-in-time test diagnostic。同时明确 `read_latest_event_sequence` 的 `SELECT COALESCE(MAX(event_sequence), 0)` 也无生产等价物（生产代码从 EventLog cursor 消费，不需要 max aggregate），应同样分类。
- **修复风险（低）**: 补充分析，不改变实现路径
- **严重程度（中）**: 实施 Agent 可能套用错误 helper

---

### P3K-F03 [中] S3 `trigger()` alias 的"where feasible"条件过于宽松 — 可能保留语义漂移的 fake

- **位置**: S3 Exact allowed changes, "In `tests/host/fake_cancellation.py`"
- **问题类型**: 范围漂移
- **当前写法**: `Optional aliases such as trigger() are allowed only if they add no separate semantics and are removed from call sites in the same slice where feasible.`
- **反例/失败场景**: `tests/engine/runners/openai/_fakes.py:278` 的 `FakeCancellationToken.trigger(reason)` 使用 `datetime.now()`（naive），而 plan 要求 canonical helper 的 `requested_at()` 返回 timezone-aware UTC。如果 `trigger()` 作为 alias 被保留在 Engine runner 测试中，但被映射到使用 UTC 的实现，现有测试中对 naive datetime 的隐式依赖（如果有）会暴露。反过来说，如果 `trigger()` 被移除但"where feasible"给实施 Agent 留下了跳过某些调用点的理由，则旧的 `FakeCancellationToken` import 可能残留。
- **为什么有问题**: "where feasible" 没有定义 feasibility 条件。实施 Agent 可能以"调用点太多"或"跨目录 import 重构范围太大"为由保留 `trigger()`，使 S3 的核心目标（消除 naive datetime 语义的第二个 fake）打折扣。
- **直接证据**: `_fakes.py:278` — `self.requested = datetime.now()` 使用 naive datetime；`fake_cancellation.py:49` — `datetime.now(UTC)` 使用 aware datetime。这两个语义差异正是 TF-4 的根因。
- **影响**: 实施 Agent 跑偏 / 风险后移
- **建议改法和验证点**: 将 "where feasible" 改为硬性要求：`trigger()` alias 仅在 canonical helper 内部作为 `request_cancel` 的别名存在时允许保留（值相同、语义相同、timezone 语义相同），且所有外部调用点必须迁移到 `request_cancel`。验证点：S3 完成后 `grep -r "\.trigger(" tests/engine/ tests/host/ tests/service/` 返回空（canonical helper 自身定义除外）。
- **修复风险（低）**: 收紧约束，不改变架构
- **严重程度（中）**: 核心目标可能打折扣

---

### P3K-F04 [低] `StubCancellationToken.__init__` 的 reason 参数语义未在 plan 中澄清 — 可能在新 helper 中延续构造即取消的反模式

- **位置**: S3 Exact allowed changes, "Provide an open-token constructor/default state instead of separate fake classes"
- **问题类型**: 契约缺失
- **当前写法**: `Provide an open-token constructor/default state instead of separate fake classes.`
- **反例/失败场景**: 当前 `StubCancellationToken(reason="cancelled")` 在构造时立即设置 `_requested_at = datetime.now(UTC)`，即"构造即取消"。新 helper 如果沿用此模式（`ControllableCancellationToken(reason="x")` 在构造时取消），则 `ControllableCancellationToken()` 是 open-token 但 `ControllableCancellationToken(reason="x")` 是 pre-cancelled——这与 "Provide an open-token constructor" 的意图冲突。如果新 helper 改为构造总是 open、需要显式调用 `request_cancel()`，则现有使用 `StubCancellationToken(reason="x")` 的调用点需要一并迁移。
- **为什么有问题**: plan 只说"open-token constructor/default state"，但没有说明是否需要显式构造预取消状态。实施 Agent 可能：(a) 保留 `__init__(reason)` 的隐式取消语义，延续反模式；(b) 移除它但遗漏迁移调用点。
- **直接证据**: `fake_cancellation.py:20-25` — `self._requested_at = datetime.now(UTC) if reason is not None else None`
- **影响**: 实施 Agent 跑偏
- **建议改法和验证点**: 在 S3 中显式规定：`ControllableCancellationToken()` 构造总是 open（未取消）；需要取消时显式调用 `request_cancel(reason)`。所有现有 `StubCancellationToken(reason="x")` 调用点改为 `token = ControllableCancellationToken(); token.request_cancel("x")`。验证点：S3 完成后 `grep -r "ControllableCancellationToken(" tests/ | grep -v "()"` 确认构造调用不传参。
- **修复风险（低）**: 纯 API 设计澄清
- **严重程度（低）**: 计划已有"open-token constructor"意图，只需补充 explicit 约束

---

### P3K-F05 [低] S2 对 `advance_projection_checkpoint` / `ensure_projection_checkpoint` 的存在性未验证 — 实施 Agent 可能需要自行判断

- **位置**: S2 Exact allowed changes, "For `force_memory_projection_lag(...)`"
- **问题类型**: 不可直接实施
- **当前写法**: `First try to express the setup through ensure_projection_checkpoint(...) / advance_projection_checkpoint(...) only if the desired lag state can be created without violating their monotonic owner semantics.`
- **反例/失败场景**: plan 没有验证这些 helper 是否存在、签名如何、是否接受所需参数。如果它们不存在或签名不匹配，实施 Agent 需要自行决定是新增 helper 还是保留 raw SQL。这与 plan 的"no new production helper solely for tests"约束可能冲突。
- **为什么有问题**: plan 用"first try"将 API 发现推迟给实施 Agent，但该 Agent 的判断标准（"without violating monotonic owner semantics"）在没有看到具体 API 签名和实现时是抽象的。
- **直接证据**: plan 未引用这些 helper 的源文件位置或签名。
- **影响**: 实施 Agent 跑偏 / 后续返工
- **建议改法和验证点**: 在 plan 中补充：(a) 这些 helper 的实际源文件和签名；(b) 如果它们不存在，明确回退路径（保留 raw SQL + fault-injection docstring）。或者，plan 可以接受"实施 Agent 先发现再决定"的策略，但需要把 stop condition 从"需要新 API 则停止"放宽为"发现 helper 不存在则直接保留 raw SQL 并标注 fault injection"。
- **修复风险（低）**: 补充验证或明确回退
- **严重程度（低）**: plan 已有合理的回退逻辑，只是未验证

---

### P3K-F06 [低] `ControllableCancellationToken` 的测试覆盖要求是条件式而非强制式

- **位置**: §7 Validation Matrix, Coverage expectation
- **问题类型**: 测试缺口
- **当前写法**: `for ControllableCancellationToken, add or migrate assertions covering open state, requested UTC timestamp, reason, and idempotent cancellation if those are not already covered indirectly.`
- **反例/失败场景**: "if those are not already covered indirectly" 把判断责任推给实施 Agent，可能导致新 canonical helper 没有独立测试。如果现有测试通过 migrated call sites "间接"覆盖了这些行为，但 call sites 测试的是业务逻辑而非 helper 契约，未来 helper 修改时可能没有直接失败测试。
- **为什么有问题**: canonical test helper 应该有显式的契约测试。依赖间接覆盖意味着 helper 的 bug 可能表现为业务测试失败而非 helper 测试失败。
- **直接证据**: plan §7 "if those are not already covered indirectly"
- **影响**: review 不可验收 / 风险后移
- **建议改法和验证点**: 将条件式改为强制式：`为 ControllableCancellationToken 添加独立契约测试，至少覆盖：构造后 is_cancelled()=False, cancel_reason()=None, requested_at()=None; request_cancel("reason") 后 is_cancelled()=True, cancel_reason()="reason", requested_at() 为 aware UTC datetime; 重复 request_cancel 是幂等的。`
- **修复风险（低）**: 增加约 10 行测试
- **严重程度（低）**: 可接受但应改进

---

### P3K-F07 [低] S1 的 `_assert_resume_guidance_semantics` 语义要求中"不要重新启动相同下载/上传/处理"是生产文本的当前语义，但 helper 设计应说明这是 owner-derived 断言

- **位置**: S1 Exact allowed changes, "In `tests/host/test_run_input_builder.py`"
- **问题类型**: 最佳实践偏离
- **当前写法**: `the LLM is instructed not to restart the same download / upload / processing action for the same request.`
- **反例/失败场景**: 如果生产 resume guidance 文本将来把"下载/上传/处理"改为更通用的表述（如"外部操作"），测试将因语义不匹配而失败。但这正是语义断言的目标——测试应随 owner 文本变化而更新。当前写法没有明确标注这是"从生产 owner 派生的当前语义，随 owner 文本变化而更新"。
- **为什么有问题**: 实施 Agent 可能把 `"download / upload / processing"` 硬编码进 helper 实现中，而不是从 production text 中提取或至少标注为 owner-derived。
- **直接证据**: plan S1 line "the LLM is instructed not to restart the same download / upload / processing action for the same request"
- **影响**: 实施 Agent 跑偏
- **建议改法和验证点**: helper 的 docstring 中明确标注"本断言消费生产 resume guidance owner 的当前语义；当 owner 文本变更时本断言应同步更新"。验证点：helper 文件中有该 docstring。
- **修复风险（低）**: 加一行注释
- **严重程度（低）**: 不影响正确性，影响可维护性

---

## Architecture Boundary Review

Plan correctly identifies the architecture boundaries:

- **Engine public contract locks** (EngineEventType wire values, terminal sets, required fields) → preserved because Engine design §4, §6 explicitly treats EngineEvent stream and data shapes as public contracts.
- **Host Memory projection field closure** → NOT a public contract (design doc defines semantic sections, not exact field tuples), so exact-field locks are removed.
- **CancellationToken protocol** → plan correctly treats the 3-method observation protocol as the boundary; test-only `request_cancel()` is below the protocol line.
- **LLM-facing text** → plan correctly treats production renderers as owners and tests as semantic-content verifiers.

No boundary violations found. The plan's partial-preservation stance is architecturally sound.

## Overcoupling Review

- S1/S2/S3 slices are reasonably decoupled. The only cross-slice touch point is `test_memory_projection.py` which may appear in S1 (field-set assertions) and implicitly in S3 (memory_snapshot_factories.py is referenced as "keep as owner" but not modified). This is not a coupling issue.
- No bidirectional dependencies between slices.
- Each slice touches a bounded set of files with clear ownership boundaries.

## Overengineering Review

- Plan correctly avoids: new production APIs, new production helpers solely for tests, broad schema migrations, rewriting all `dataclasses.fields()` tests.
- The `_assert_resume_guidance_semantics` helper is minimal — just enough to encode semantic contract without over-engineering.
- The `ControllableCancellationToken` is a straightforward consolidation, not a new abstraction layer.

## Best-Practice Review

- Plan follows project conventions: semantic owner identification, stop conditions, propagation audits, focused validation commands.
- One gap: S2's "first try to express through production helpers" pattern is discovery-driven rather than plan-verified. For a test-only cleanup this is acceptable, but the plan should explicitly list which helpers are confirmed to exist vs. which need discovery.

## Optimal-Solution Review

The three-slice structure (assertion ownership → durable diagnostic boundary → test-double consolidation) is the right decomposition. Alternative considered and rejected:
- Single monolithic slice: would mix assertion, SQL, and fake concerns → harder to review and revert.
- Five TF-aligned slices: would create artificial dependencies (TF-3 and TF-4 both touch compaction/fake concerns) → three slices is better.

The plan's decision to keep Engine exact locks while removing Host memory field locks is correct based on design-source evidence.

## Open Questions

1. **S2 `advance_projection_checkpoint` / `ensure_projection_checkpoint` 是否存在？** plan 未验证，实施 Agent 需要自行发现。建议在 plan 中补充确认或明确回退路径。
2. **`read_latest_event_sequence` (stress_support.py:720-740) 的生产等价物？** `SELECT COALESCE(MAX(event_sequence), 0)` 没有生产 helper——生产代码按 cursor 消费 EventLog 不需要 max aggregate。plan 未提及此 case，应归类为"保留 raw SQL + diagnostic-only docstring"。
3. **S3 是否应包含 `test_dispatch_scheduler.py` baseline failures 的隔离验证？** plan 的 non-goals 说"不修复不相关的 baseline failures"，但如果 S3 的 cancellation fake 变更影响了 dispatch scheduler 的测试依赖，实施 Agent 需要区分"我的改动导致的失败"和"已有的 baseline 失败"。建议 S3 focused validation 列表中显式包含 `test_dispatch_scheduler.py` 以确认无回归。

## Residual Risks

| # | Risk | Severity | Suggested Tracking |
|---|---|---|---|
| R1 | LLM-facing semantic assertions 如果实现为过于模糊的子串检查可能失去防护力 | 低 | S1 实施后验证语义断言至少覆盖 5 个明确语义维度 |
| R2 | `ControllableCancellationToken` 迁移涉及大量调用点，可能遗漏个别 import | 低 | S3 完成后 `grep -r "FakeCancellationToken\|StubCancellationToken" tests/` 确认旧引用清空 |
| R3 | S2 raw SQL 保留可能被后续 work unit 视为"已处理完毕"而忽略 | 低 | raw SQL helper 的 docstring 必须显式标注 fault-injection-only 或 diagnostic-only |
| R4 | Engine exact protocol locks 保留可能在未来的设计变更中被挑战为过于严格 | 低 | 已在 plan §9 中记录为 residual risk；需要设计源变更才能解除 |

## Final Plan Review Conclusion

**PASS-WITH-FINDINGS**

The plan's partial-preservation stance is correct and well-supported by design-source evidence. The three-slice decomposition (assertion ownership → durable diagnostic boundary → test-double consolidation) is semantically coherent and code-generation-ready with the findings above addressed.

Three medium-severity findings require plan adjustment before implementation:
- **P3K-F01**: Fix `HostInstanceLivenessStore.read_by_host_instance_id` → `read_host_instance`
- **P3K-F02**: Explicitly classify `_diagnostic_event_type_count` and `read_latest_event_sequence` as cases with no production equivalent
- **P3K-F03**: Replace "where feasible" with a hard requirement to remove `trigger()` from all external call sites

Four low-severity findings are recommended improvements that do not block implementation.

No critical or high-severity findings. The plan does not overreach by adding production APIs for tests, does not under-specify to the point of requiring redesign, and correctly avoids compatibility wrappers and protocol drift. LLM-facing text tests remain strong under the proposed semantic-content approach. README trigger and validation matrices are sufficient for a test-only cleanup.

Open questions (3) and residual risks (4) are documented above and do not block plan acceptance.
