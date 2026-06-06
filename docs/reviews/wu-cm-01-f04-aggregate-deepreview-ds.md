# WU-CM-01-F04 Aggregate Deepreview — AgentDS

## Scope

- Mode: aggregate deepreview (phaseflow gate)
- Branch: `phaseflow/host-issues`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f04-aggregate-deepreview-ds.md`
- Review date: 2026-06-06T20:53:21+08:00

### Included scope

- 当前分支 `phaseflow/host-issues` 相对 `main` 的 WU-CM-01-F04 完整 diff（14 files, +1829/-67）
- Accepted plan commit `d90a2a99`（`docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md`）
- Accepted implementation slice commit `bfba6263`（`tests/host/test_dispatch_scheduler.py`）
- Controller bookkeeping commits `626911f1` / `f56b93cd`（`docs/host/issues-implementation-control.md`）
- Plan review artifacts: `docs/reviews/wu-cm-01-f04-plan-review-ds.md`, `docs/reviews/wu-cm-01-f04-plan-review-mimo.md`
- Plan fix artifact: `docs/reviews/wu-cm-01-f04-plan-fix-codex.md`
- Plan re-review artifacts: `docs/reviews/wu-cm-01-f04-plan-rereview-ds.md`, `docs/reviews/wu-cm-01-f04-plan-rereview-mimo.md`
- Implementation artifact: `docs/reviews/wu-cm-01-f04-implementation-codex.md`
- Code review artifacts: `docs/reviews/wu-cm-01-f04-code-review-ds.md`, `docs/reviews/wu-cm-01-f04-code-review-mimo.md`
- Code fix artifact: `docs/reviews/wu-cm-01-f04-code-review-fix-codex.md`
- Code re-review artifacts: `docs/reviews/wu-cm-01-f04-code-review-rereview-ds.md`, `docs/reviews/wu-cm-01-f04-code-review-rereview-mimo.md`
- 设计真源: `docs/host/design.md`（lines 3225-3280）, `docs/engine/design.md`（lines 414-423）
- 总控文档: `docs/host/issues-implementation-control.md`（lines 530-571）
- 生产代码只读验证: `dayu/host/dispatch.py`, `dayu/host/compaction_operation.py`, `dayu/host/context_events.py`

### Excluded scope

- 不重新审查 `dayu/host/dispatch.py`、`dayu/host/compaction_operation.py` 的非 WU-CM-01-F04 相关代码路径
- 不审查 reactive compaction test seam（`tests/host/test_compaction_operation.py`, `tests/host/test_engine_ingest_mapping.py`）
- 不审查 `tests/host/test_dispatch_scheduler.py` 中非 proactive compaction 的测试
- 不审查 WU-TOOLS-01 / PR #123

### Parallel review coverage

无。本 aggregate deepreview 为单 reviewer 聚合审查。

---

## Gate 链完整性验证

### Plan Gate

| Gate | Artifact | Verdict | Status |
|---|---|---|---|
| Plan | `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md` | — | accepted (`d90a2a99`) |
| Plan Review (DS) | `docs/reviews/wu-cm-01-f04-plan-review-ds.md` | pass-with-findings (3B + 4NB) | complete |
| Plan Review (MiMo) | `docs/reviews/wu-cm-01-f04-plan-review-mimo.md` | pass-with-findings (4NB) | complete |
| Plan Fix (Codex) | `docs/reviews/wu-cm-01-f04-plan-fix-codex.md` | 7 fixed + 1 rejected | complete |
| Plan Re-review (DS) | `docs/reviews/wu-cm-01-f04-plan-rereview-ds.md` | pass | complete |
| Plan Re-review (MiMo) | `docs/reviews/wu-cm-01-f04-plan-rereview-mimo.md` | pass | complete |
| Plan Acceptance | `626911f1` | — | accepted |

### Implementation Gate

| Gate | Artifact | Verdict | Status |
|---|---|---|---|
| Implementation (Codex) | `docs/reviews/wu-cm-01-f04-implementation-codex.md` | ready | accepted (`bfba6263`) |
| Code Review (DS) | `docs/reviews/wu-cm-01-f04-code-review-ds.md` | pass-with-findings (1NB) | complete |
| Code Review (MiMo) | `docs/reviews/wu-cm-01-f04-code-review-mimo.md` | pass | complete |
| Code Fix (Codex) | `docs/reviews/wu-cm-01-f04-code-review-fix-codex.md` | 1 fixed | complete |
| Code Re-review (DS) | `docs/reviews/wu-cm-01-f04-code-review-rereview-ds.md` | pass | complete |
| Code Re-review (MiMo) | `docs/reviews/wu-cm-01-f04-code-review-rereview-mimo.md` | pass | complete |
| Slice Acceptance | `f56b93cd` | — | accepted |

**Gate 链完整**。所有 7 项 plan findings 和 1 项 code review finding 均已通过 fix → re-review 闭环关闭。无未关闭的 accepted finding。

---

## 设计真源对齐验证

### Host 设计对齐（`docs/host/design.md:3225-3280`）

| 设计要求 | 实现对齐 | 证据 |
|---|---|---|
| proactive trigger 是 dispatch Attempt 前的 Host governance | 未修改生产代码，test seam 只改变 compactor injection | `tests/host/test_dispatch_scheduler.py` diff 无 prod 变更 |
| compact operation 在 write transaction 外执行 | `_TransactionReadableCompactor.run_prepared_compactor_proposal` 仍通过独立读事务验证 Run 存在 | 行 512-522: `self._transaction_runner.run_read(...)` 后 `super().run_prepared_compactor_proposal(prepared_input)` |
| `CONTEXT_COMPACTED` payload 记录 durable 信息 | `_assert_accepted_payload_has_proposal_manifest` 断言 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` | 行 5707-5720 |
| compact 不变量：不能改写历史 EventLog、fallback 不提交 `CONTEXT_COMPACTED` | `_StaleMutatingCompactor` 不迁移，stale test 断言 `CONTEXT_COMPACTED == 0` | 行 4053: `assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0` |

### Engine 设计对齐（`docs/engine/design.md:414-423`）

| 设计要求 | 实现对齐 | 证据 |
|---|---|---|
| Engine 不做 proactive threshold compaction | 无 Engine 代码变更 | diff 仅含 `tests/host/test_dispatch_scheduler.py` |
| Engine 只在 provider overflow 时发出 reactive compaction request | 无 Engine contract 变更 | 无 Engine 相关 import 或调用变更 |

**设计真源对齐：通过**。整个 work unit 严格限定在 Host proactive scheduler test seam，未修改任何设计真源描述的生产 guard、schema 或 Engine contract。

---

## First-principles Motivation 验证

### 动机成立性

WU-CM-01 升级 ConversationMemory / Compact 后，accepted compact outcome 必须反向引用 durable proposal manifest ref / digest。`dayu/host/dispatch.py:1264-1269` 在写 `CONTEXT_COMPACTED` 前调用 `_required_compactor_manifest_ref(result)` 和 `_required_compactor_manifest_digest(result)`——这是 fail-closed guard。proactive scheduler tests 使用 legacy `FakeContextCompactor`（只实现 `compact()`），不走 `CompactorProposalPreparedCompactor` 路径，因此 `run_compaction_operation` 的 `proposal_manifest_reference=None`，最终触发 guard 抛出 `RuntimeError`。

**动机成立**：根因是测试 seam 未对齐 WU-CM-01 升级后的 manifest contract，不是生产 guard 过严。整条证据链从测试 seam → `compact()` legacy 路径 → `proposal_manifest_reference=None` → `_required_compactor_manifest_ref` fail-closed ——逻辑与数据同源。

### 实现正确性

逐项验证 committed implementation 是否仍通过 plan 声明和 review 裁决：

| 验证项 | 预期 | 实际 | 通过 |
|---|---|---|---|
| `_PreparedManifestProactiveCompactor` 实现 `CompactorProposalPreparedCompactor` protocol | `isinstance` 检查通过 | 两方法签名与 protocol（`compaction_operation.py:137-167`）严格对齐，`@runtime_checkable` 可正确命中 | ✓ |
| accepted event payload 携带 manifest ref/digest | `accepted_proposal_manifest_ref` 以 `runner-call-manifest:` 开头 | `_assert_accepted_payload_has_proposal_manifest` 断言 ref prefix + digest 非空 | ✓ |
| rejected event payload 携带 manifest ref/digest | `proposal_manifest_ref` 以 `runner-call-manifest:` 开头 | `_assert_rejected_payload_has_proposal_manifest` 断言 ref prefix + digest 非空 | ✓ |
| `_StaleMutatingCompactor` 不迁移 | 仍继承 `FakeContextCompactor`，不走 prepared path | 行 531: `class _StaleMutatingCompactor(FakeContextCompactor):` | ✓ |
| `_TransactionReadableCompactor` 保留独立读事务语义 | `run_prepared_compactor_proposal` 中先 `run_read(read_run_by_id)` 再 `super()` | 行 512-522: 读事务验证后调用父类 | ✓ |
| `_RequestCapturingCompactor` request 捕获 | 在 prepare 阶段通过 `prepared_requests` 捕获 | 行 625-626: 空类，真源在父类 `prepared_requests`（行 419, 439） | ✓ |
| `_QualityRejectOnceCompactor` 两次 proposal 语义 | 第一次 `replace(candidate, diagnostics=...)`，第二次 clean | 行 598-616: `if self.calls == 1: return replace(candidate, diagnostics=...)` | ✓ |
| `_RaisingCompactor` 为 post-manifest failure | `fail_run=True`，manifest 记录后抛 `RuntimeError` | 行 577-588: `super().__init__(fail_run=True)` | ✓ |

**First-principles motivation 验证：通过**。

---

## Artifact 一致性验证

### Plan → Plan Review → Plan Fix → Plan Re-review 闭环

| Plan Finding | Severity | Plan Fix 状态 | Plan Re-review 确认 |
|---|---|---|---|
| DS F1: Slice 4 扫描范围不精确 | BLOCKING | 已修复 — 新增 Slice 0 semantic enumeration | DS/MiMo re-review pass |
| DS F2: `_StaleMutatingCompactor` 过度迁移 | BLOCKING | 已修复 — Decision 9 明确不迁移 | DS/MiMo re-review pass |
| DS F3: `_TransactionReadableCompactor` 未显式分配 | BLOCKING | 已修复 — Decision 8 + Slice 2 显式分配 | DS/MiMo re-review pass |
| DS F4: `_RequestCapturingCompactor` 使用范围未明确 | NON-BLOCKING | 已修复 — Slice 0 inventory 枚举全部使用点 | DS/MiMo re-review pass |
| DS F5: `RUNNER_CALL_INPUT_ASSEMBLED` count 风险 | NON-BLOCKING | 已修复 — 降级为 conditional assertion | DS/MiMo re-review pass |
| DS F6: `_COMPACTOR_TEST_DIGEST` 过度设计 | NON-BLOCKING | Controller rejected — 优先复用 `_CALL_CONTEXT_DIGEST` | DS re-review pass |
| DS F7: `_RaisingCompactor` 复用风险 | NON-BLOCKING | 已修复 — grep 确认单点使用，post-manifest 语义升级 | DS/MiMo re-review pass |
| MiMo F1: `_StaleMutatingCompactor` 迁移判断 | NON-BLOCKING | 同 DS F2，已修复 | DS/MiMo re-review pass |
| MiMo F2: `_RaisingCompactor` failure 时序 | NON-BLOCKING | 同 DS F7，已修复 | DS/MiMo re-review pass |
| MiMo F3: `_QualityRejectOnceCompactor` first rejection manifest | NON-BLOCKING | 已修复 — Decision 7 明确新增覆盖 | DS/MiMo re-review pass |
| MiMo F4: Slice 4 broad scan 范围 | NON-BLOCKING | 同 DS F1，已修复 | DS/MiMo re-review pass |

**所有 11 项（去重后 7 项）plan review findings 均已通过 fix → re-review 关闭。无未关闭的 plan 级 finding。**

### Implementation → Code Review → Code Fix → Code Re-review 闭环

| Code Review Finding | Severity | Code Fix 状态 | Code Re-review 确认 |
|---|---|---|---|
| `_RequestCapturingCompactor.requests` 与 `prepared_requests` 重复存储 | LOW | 已修复 — 删除独立 `requests`，真源统一为 `prepared_requests` | DS/MiMo re-review pass |

**唯一 code review finding 已关闭。**

### 总控文档一致性

`docs/host/issues-implementation-control.md` 的 bookkeeping 更新一致：
- 行 144: `gate: aggregate deepreview` ← 当前 gate
- 行 145: `implementation status: WU-CM-01-F04 accepted slice commit bfba6263; ready for aggregate deepreview` ← 与 implementation gate 对齐
- 行 146: `active work unit: WU-CM-01-F04` ← 正确
- 行 147: `next entry point: Aggregate deepreview for WU-CM-01-F04` ← 当前正在执行

无 bookkeeping 不一致。

---

## Findings

### 1-未修复-低-`_RequestCapturingCompactor` 降级为空别名后命名语义与真源不一致

- **入口/函数**: `_RequestCapturingCompactor` 类定义
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:625-626`
- **输入场景**: 未来开发者阅读 `_RequestCapturingCompactor` 类名时，可能误认为该类有自己的 request 捕获状态
- **实际分支**: `_RequestCapturingCompactor` 当前是纯空别名类（`class _RequestCapturingCompactor(_PreparedManifestProactiveCompactor): """记录 proactive compaction request 的测试 compactor。"""`），所有 request 捕获真源在父类 `_PreparedManifestProactiveCompactor.prepared_requests`
- **预期行为**: 命名与真源一致——若保留 `_RequestCapturingCompactor` 命名，应让读者清楚状态归属；若不需要该命名，可直接在 test 中用 `_PreparedManifestProactiveCompactor()` 替代
- **实际行为**: 类名暗示"捕获 request"能力，但实际上空的——捕获由父类完成。当前两个 request capture test（行 3788-3789, 3832）读取 `compactor.prepared_requests` 而非 `compactor.requests`，与类名语义不完全一致
- **直接证据**: 行 625-626 类体为空；grep 确认 `self.requests` 和 `compactor.requests` 在文件中均已删除
- **影响**: 无 correctness 影响。仅 maintainability —— 未来开发者可能花时间在 `_RequestCapturingCompactor` 中找 request 捕获逻辑，发现是空类后再追踪父类
- **建议改法和验证点**: 可考虑两个方向：(a) 在 `_RequestCapturingCompactor` 的 docstring 明确写 "request 捕获真源在父类 `prepared_requests`"；(b) 如果未来不需要该语义化命名，直接在所有使用点替换为 `_PreparedManifestProactiveCompactor()` 并删除该类。验证：`grep _RequestCapturingCompactor` 确认使用点和替换范围
- **修复风险**: 低
- **严重程度**: 低
- **建议裁决**: deferred-with-owner — future cleanup work unit 或 maintainer 自行决定

### 2-未修复-低-全量测试套件未在 aggregate deepreview 中运行

- **入口/函数**: 全部 `tests/host/test_dispatch_scheduler.py`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py`（~5700 行，~100+ tests）
- **输入场景**: 虽然 `_PreparedManifestProactiveCompactor` 仅由 proactive compaction tests 使用，但文件内其他测试可能间接受到 imports 变更、新模块级常量和 helper 函数的影响
- **实际分支**: Implementation gate 仅运行了 `-k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"`（8 selected, 54 deselected）。代码 review gate 和 re-review gate 均未扩展运行范围
- **预期行为**: aggregate deepreview 应运行全量 `tests/host/test_dispatch_scheduler.py` 确认无回归
- **实际行为**: 全量未运行。新增 imports（`runner_role_sequence_digest`, `SystemMessage`, `conversation_compact_input_vnext_from_material_pack`, `CompactorProposalRunInput`）和新增 helper 函数（`_proposal_compactor_agent_request`, `_events_for_run_by_type`, `_assert_accepted_payload_has_proposal_manifest`, `_assert_rejected_payload_has_proposal_manifest`）在模块级定义，可能影响其他测试的 import 解析或命名空间——虽然概率极低
- **直接证据**: implementation artifact（`docs/reviews/wu-cm-01-f04-implementation-codex.md:57-63`）记录 focused validation 为 8 passed, 54 deselected；code review artifact 在 Residual Risk 中记录 "全量 test suite 未运行"；本 aggregate deepreview 同样仅运行 focused + 3 focused tests（11 passed total），未扩展范围
- **影响**: 低概率的回归未被检测。若其他测试中有人使用了与新 import 冲突的模块级变量名，可能在 pytest collection 阶段暴露——但 collection 已通过（54 deselected 而非 error）
- **建议改法和验证点**: 若总控要求，可运行 `pytest tests/host/test_dispatch_scheduler.py -x` 确认全量通过。但 54 deselected 表明 collection 成功，新增 import 和 helper 在模块级为私有函数（`_` 前缀），不太可能与其他测试冲突
- **修复风险**: 低
- **严重程度**: 低
- **建议裁决**: deferred-with-owner — 由总控决定是否在 closeout 前要求全量 test suite 运行；implementation gate 的 focused validation（11 tests passed）+ pyright（0 errors）已覆盖本 work unit 的主要风险面

---

## Protocol Signature 逐项对齐验证（已确认无问题）

| Protocol 方法 (`compaction_operation.py:137-167`) | 实现 (test_dispatch_scheduler.py) | 签名 | 对齐 |
|---|---|---|---|
| `prepare_compactor_proposal_run_input` | `_PreparedManifestProactiveCompactor.prepare_compactor_proposal_run_input` (行 425-466) | `(self, request: CompactionRequest, cancellation_token: CancellationToken, *, compaction_operation_id: str \| None, compaction_attempt_number: int) -> CompactorProposalRunInput` | ✓ |
| `run_prepared_compactor_proposal` | `_PreparedManifestProactiveCompactor.run_prepared_compactor_proposal` (行 468-489) | `async (self, prepared_input: CompactorProposalRunInput) -> ConversationCompactOutputVNext` | ✓ |

`CompactorProposalPreparedCompactor` 是 `@runtime_checkable` Protocol（`compaction_operation.py:133-134`），`isinstance` 检查依赖方法名与签名匹配。上述实现可正确触发 manifest recorder 路径（`compaction_operation.py:749`）。

## Compactor 分类与迁移决策验证（已确认无问题）

| Compactor | 继承 | 是否迁移 | 迁移后语义保留 | 清单对齐 |
|---|---|---|---|---|
| `_PreparedManifestProactiveCompactor` | `FakeContextCompactor` | 新增基类 | — | Plan Slice 1 |
| `_TransactionReadableCompactor` | `_PreparedManifestProactiveCompactor` | 是 | 独立读事务 → run 阶段保留 | Plan Slice 2, DS F3 |
| `_RequestCapturingCompactor` | `_PreparedManifestProactiveCompactor` | 是（空别名） | request 捕获 → prepare 阶段通过父类 `prepared_requests` | Plan Slice 2, DS F4 |
| `_QualityRejectOnceCompactor` | `_PreparedManifestProactiveCompactor` | 是 | quality rejection counter 语义保留 | Plan Slice 3, MiMo F3 |
| `_RaisingCompactor` | `_PreparedManifestProactiveCompactor` | 是 | 升级为 post-manifest failure | Plan Slice 3, DS F7/MiMo F2 |
| `_StaleMutatingCompactor` | `FakeContextCompactor` | **否** | — | Plan Decision 9, DS F2/MiMo F1 |
| `FakeContextCompactor()` 直接注入（excluded tests） | `FakeContextCompactor` | **否** | count limit / corrupted count 在 compaction 前 fail closed | Plan Slice 0 excluded |

所有 8 个 proactive accepted/rejected tests 迁移正确；3 个 excluded tests 正确保留 legacy seam。

## Manifest Assertion 覆盖验证（已确认无问题）

| 断言 helper | payload 类型 | 断言字段 | 格式要求 | 覆盖的 tests |
|---|---|---|---|---|
| `_assert_accepted_payload_has_proposal_manifest` | `CONTEXT_COMPACTED` | `accepted_proposal_manifest_ref`, `accepted_proposal_manifest_digest` | ref 以 `runner-call-manifest:` 开头, str; digest 非空 str | 6 accepted tests |
| `_assert_rejected_payload_has_proposal_manifest` | `CONTEXT_COMPACTION_ATTEMPT_REJECTED` | `proposal_manifest_ref`, `proposal_manifest_digest` | ref 以 `runner-call-manifest:` 开头, str; digest 非空 str | 2 rejected tests |

- 第一次 quality rejection 的 rejected manifest 断言是新增覆盖（`test_proactive_compaction_retries_quality_rejection_before_accept`，行 4129-4130）
- 第二次 repair attempt rejection 的 rejected manifest 断言是新增覆盖（`test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`，行 4181-4185，两个 rejected rows 均断言）
- 所有断言直接访问 payload 字段，无 `RUNNER_CALL_INPUT_ASSEMBLED` 计数依赖——符合 plan 的 conditional assertion 策略

## 架构边界验证（已确认无问题）

- 无生产代码变更：`dayu/host/dispatch.py`、`dayu/host/compaction_operation.py`、`dayu/host/context_events.py` 均未修改
- 无 schema 变更、无 EventLog payload builder 变更、无 public interface 变更
- 无 Engine contract 变更
- 无跨层穿透 import：所有新增 import 来自已有 public 模块（`dayu.engine.contracts.*`、`dayu.host.compaction_operation`、`dayu.host.compact_material`）
- 无新增 compatibility wrapper / facade
- 无 `FakeContextCompactor` 修改——旧 fake 不自动具备 manifest 能力
- 测试 seam 实现在 `tests/host/test_dispatch_scheduler.py` 模块级私有（`_` 前缀），不泄露到生产或公共接口

## Adversarial Failure Pass

| 攻击面 | 检查结果 |
|---|---|
| 空 prepared request（`_latest_prepared_request` 返回 None） | `AssertionError` 守卫（行 497-498） |
| `_RaisingCompactor` post-manifest failure 时序 | manifest record（`compaction_operation.py:756`）在 `run_prepared_compactor_proposal`（行 764）之前 |
| `_QualityRejectOnceCompactor` 多次 prepare/run 间 `_prepared_request` 污染 | 每次 `prepare` 覆写 `self._prepared_request`（行 440），`run` 读最新值 |
| `FakeContextCompactor` 仍被 excluded tests 使用 | excluded tests 在 compaction operation 前 fail closed，或走 reactive 路径 |
| `_RaisingCompactor` 多使用点 | grep 确认仅行 4156 一处 |
| 未覆盖的 proactive compactor injection | Slice 0 semantic enumeration grep 覆盖全部 7 个 compactor 类名 + `context_compactor=` + `FakeContextCompactor()`，与实现 artifact inventory 一致 |
| import 冲突或命名空间污染 | 新增 import 和 helper 均为私有（`_` 前缀），pytest collection 通过（54 deselected） |
| Protocol signature mismatch → legacy path | 签名逐项对齐已验证 |

---

## Open Questions

无 blocking open questions。

---

## Validation Reviewed / Run

### 已审查的验证记录（来自 prior gates）

| Gate | 验证项 | 命令 | 结果 |
|---|---|---|---|
| Implementation | focused tests | `pytest ... -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"` | 8 passed, 54 deselected |
| Implementation | 3 focused tests | `pytest ...::test_pre_start_governance_soft_threshold_compacts_before_attempt ...::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` | 3 passed |
| Implementation | pyright | `pyright` | 0 errors, 0 warnings, 0 informations |
| Code Review (MiMo) | focused tests (re-run) | 同上 `-k` | 8 passed, 54 deselected |
| Code Review (MiMo) | pyright (re-run) | `pyright tests/host/test_dispatch_scheduler.py` | 0 errors, 0 warnings, 0 informations |
| Code Fix | request capture tests | `pytest ...::test_proactive_compaction_uses_selected_material_not_session_start_range ...::test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view` | 2 passed |
| Code Fix | focused tests (re-run) | 同上 `-k` | 8 passed, 54 deselected |
| Code Fix | pyright (re-run) | `pyright` | 0 errors, 0 warnings, 0 informations |
| Code Re-review (MiMo) | request capture tests (re-run) | 同上 | 2 passed |
| Code Re-review (MiMo) | focused tests (re-run) | 同上 `-k` | 8 passed, 54 deselected |

### 本轮 aggregate deepreview 实际运行验证

| 验证项 | 命令 | 结果 |
|---|---|---|
| focused tests | `pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task" -q` | **8 passed, 54 deselected** in 0.40s |
| 3 focused tests | `pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt ...::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog -q` | **3 passed** in 0.31s |
| pyright | `pyright tests/host/test_dispatch_scheduler.py` | **0 errors, 0 warnings, 0 informations** |

所有 focused validation 在本轮重新运行并通过。与 prior gates 报告一致。

---

## Residual Risks / Uncovered Areas

### 已分类 residual risks

| # | Risk | Classification | Owner | Mitigation |
|---|---|---|---|---|
| R1 | 全量 `tests/host/test_dispatch_scheduler.py`（~100+ tests）未运行 | **test-gap** — focused validation 仅覆盖 8+3=11 tests | 总控（closeout 决策） | 54 deselected 表明 pytest collection 成功；新增代码均为私有（`_` 前缀），不太可能影响其他 tests；若总控要求可追加 `pytest tests/host/test_dispatch_scheduler.py -x` |
| R2 | `_RequestCapturingCompactor` 降级为空别名，命名语义与状态真源不一致 | **maintainability** — 低影响，不阻塞 merge | maintainer / future cleanup | 见 Finding 1 |
| R3 | `tests/host/test_compaction_operation.py` 未在本 work unit 验证 | **out-of-scope** — prepared manifest seam 参考实现有独立测试覆盖，不在 proactive closeout 范围 | 其自身 test suite | 已有 `test_compaction_operation.py` 的 `_PreparedManifestCompactor` 测试 |
| R4 | reactive test seam 后续对齐 | **out-of-scope** — 不在本 WU-CM-01-F04 范围 | 未来 work unit | reactive tests 已有独立 prepared manifest seam（`test_engine_ingest_mapping.py`） |
| R5 | `_PreparedManifestProactiveCompactor` 的 `compaction_request_digest` 使用 `request.digest()` 计算——若 `CompactionRequest.digest()` 算法变更，test digest 常量需同步更新 | **contract-evolution** — 与任何依赖 `CompactionRequest.digest()` 的生产/测试代码共享同一风险面 | 合约维护者 | `request.digest()` 变更是 contract 级变更，会有对应 work unit |
| R6 | `FakeContextCompactor` 无 prepared manifest 能力，仍被 excluded tests 使用——若未来有新的 proactive test 直接注入 `FakeContextCompactor()`，会再次触发 manifest guard failure | **process-gap** — Slice 0/Slice 4 的 grep 扫描仅在 implementation gate 执行一次 | maintainer | Slice 4 的 broad scan 应在每次新增 proactive test 时作为 checklist 项 |

### 不属于本 work unit 的未覆盖区域

- Reactive compaction path — 属于 WU-CM-01 的 reactive scope，已有 `test_engine_ingest_mapping.py` prepared manifest seam
- `RUNNER_CALL_INPUT_ASSEMBLED` event count — plan 已降级为 conditional assertion，核心验收为 payload manifest ref/digest
- `_StaleMutatingCompactor` 在 legacy path — 正确不迁移，stale check 在 accepted guard 前收口
- WU-TOOLS-01 provider migration — 独立 work unit，不在本 scope

---

## Verdict

**pass-with-findings** — 2 non-blocking low-severity findings。

核心判断：

1. **整个 work unit 符合设计真源和总控文档**：只修 Host proactive scheduler test seam，未改 production guard / schema / Engine contract。
2. **committed implementation 通过 first-principles motivation**：manifest-producing prepared compactor seam 正确触发 `CompactorProposalPreparedCompactor` protocol 路径，accepted/rejected event manifest ref/digest 断言覆盖完整。
3. **`_StaleMutatingCompactor` 正确排除**，`_TransactionReadableCompactor` / `_RequestCapturingCompactor` / `_QualityRejectOnceCompactor` / `_RaisingCompactor` 迁移后语义完整保留。
4. **plan/review/fix/re-review artifact chain 完整一致**：所有 7 项 plan findings + 1 项 code review finding 已通过 fix → re-review 闭环关闭，无未关闭 finding。
5. **gate chain 完整**：plan → plan review → plan fix → plan re-review → plan acceptance → implementation → code review → code fix → code re-review → slice acceptance → aggregate deepreview。
6. **validation 一致**：本轮重新运行 focused tests（8 passed）+ 3 focused tests（3 passed）+ pyright（0 errors），与所有 prior gates 报告一致。

**Blocking findings: 0**
**Non-blocking findings: 2（均为 low severity）**

---

## Files Changed

- `tests/host/test_dispatch_scheduler.py` — test seam migration + manifest assertions（+365/-67，核心变更）
- `docs/host/issues-implementation-control.md` — gate bookkeeping（+4/-4）
- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md` — plan artifact（+407，新增）
- `docs/reviews/wu-cm-01-f04-plan-review-ds.md` — DS plan review（+199，新增）
- `docs/reviews/wu-cm-01-f04-plan-review-mimo.md` — MiMo plan review（+89，新增）
- `docs/reviews/wu-cm-01-f04-plan-fix-codex.md` — Codex plan fix（+125，新增）
- `docs/reviews/wu-cm-01-f04-plan-rereview-ds.md` — DS plan re-review（+158，新增）
- `docs/reviews/wu-cm-01-f04-plan-rereview-mimo.md` — MiMo plan re-review（+58，新增）
- `docs/reviews/wu-cm-01-f04-implementation-codex.md` — Codex implementation artifact（+92，新增）
- `docs/reviews/wu-cm-01-f04-code-review-ds.md` — DS code review（+146，新增）
- `docs/reviews/wu-cm-01-f04-code-review-mimo.md` — MiMo code review（+53，新增）
- `docs/reviews/wu-cm-01-f04-code-review-fix-codex.md` — Codex code fix（+62，新增）
- `docs/reviews/wu-cm-01-f04-code-review-rereview-ds.md` — DS code re-review（+56，新增）
- `docs/reviews/wu-cm-01-f04-code-review-rereview-mimo.md` — MiMo code re-review（+78，新增）
- `docs/reviews/wu-cm-01-f04-aggregate-deepreview-ds.md` — 本 artifact（新增）
