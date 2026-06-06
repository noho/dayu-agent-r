# WU-CM-01-F04 PR Review — AgentDS

## Scope

- Mode: PR review (deepreview gate)
- Repository: noho/dayu-agent-r
- PR: [#124](https://github.com/noho/dayu-agent-r/pull/124)
- Title: phaseflow: restore proactive compaction manifest test seam
- Author: noho
- Head branch: `phaseflow/host-issues`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f04-pr-review-ds.md`
- Review date: 2026-06-06T21:04:59+08:00

### Included scope

- PR #124 相对 `main` 的完整 diff（14 files, +1829/-67），覆盖：
  - `tests/host/test_dispatch_scheduler.py` — 核心 test seam 变更（+365/-67）
  - `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md` — plan artifact（+407，新增）
  - `docs/host/issues-implementation-control.md` — 总控 bookkeeping（+4/-4）
  - 11 份 `docs/reviews/wu-cm-01-f04-*` review/re-review/fix artifacts（新增）
- 设计真源: `docs/host/design.md` (lines 3225-3278), `docs/engine/design.md` (lines 414-423)
- 总控文档: `docs/host/issues-implementation-control.md` (lines 530-571)
- 生产代码只读验证: `dayu/host/dispatch.py`, `dayu/host/compaction_operation.py`, `dayu/host/context_events.py`
- PR body 一致性检查

### Excluded scope

- 不重新审查 `dayu/host/dispatch.py`、`dayu/host/compaction_operation.py` 的非 WU-CM-01-F04 相关代码路径
- 不审查 reactive compaction test seam（`tests/host/test_compaction_operation.py`, `tests/host/test_engine_ingest_mapping.py`）
- 不审查 `tests/host/test_dispatch_scheduler.py` 中非 proactive compaction 的测试语义
- 不审查 WU-TOOLS-01 / PR #123

### Parallel review coverage

无。本 PR review 为单 reviewer 审查。

---

## PR Body vs Control Doc 一致性

| 检查项 | PR body | 总控文档 (`issues-implementation-control.md:140-150`) | 一致 |
|---|---|---|---|
| work unit | WU-CM-01-F04 | WU-CM-01-F04 | ✓ |
| gate | (PR body 为 summary，gate 隐含 seeking review) | `PR review` | ✓ |
| 范围 | test seam + manifest assertions | 同 | ✓ |
| 非目标 | 不修改生产 guard / schema / Engine contract | 同 | ✓ |
| 验证命令 | focused tests 8/3 + pyright | 同 | ✓ |
| residual risk | reactive out of scope, full suite not claimed | 同 | ✓ |

PR body 声称 "Keeps production compact fail-closed behavior unchanged; no Host production code, Engine code, schema, or public contract changes" -- 与 diff 一致，仅 `tests/host/test_dispatch_scheduler.py` 和 docs 变更。

---

## First-principles Motivation

### 动机成立性

WU-CM-01 升级 ConversationMemory / Compact 后，accepted compact outcome 必须反向引用 durable proposal manifest ref / digest。`dayu/host/dispatch.py:1264-1269` 在写 `CONTEXT_COMPACTED` 前调用 `_required_compactor_manifest_ref(result)` 和 `_required_compactor_manifest_digest(result)`——fail-closed guard，缺失时抛出 `RuntimeError`。

Proactive scheduler tests 原使用 legacy `FakeContextCompactor`（仅实现 `compact()`），不走 `CompactorProposalPreparedCompactor` 协议路径，导致 `compaction_operation.py:749` 的 `isinstance` 检查失败，走 legacy `compact()` 路径，`proposal_manifest_reference=None`，最终 guard 抛出异常。

**根因是测试 seam 未对齐 WU-CM-01 升级后的 manifest contract**，不是生产 guard 过严。证据链完整：test seam → legacy `compact()` → `proposal_manifest_reference=None` → `_required_compactor_manifest_ref` fail-closed —— 逻辑与数据同源。

### 实现正确性

逐项验证 committed implementation：

| 验证项 | 预期 | 实际 | 通过 |
|---|---|---|---|
| `_PreparedManifestProactiveCompactor` 实现 `CompactorProposalPreparedCompactor` protocol | `isinstance` 检查通过 | 两方法签名与 protocol（`compaction_operation.py:137-167`）严格对齐 | ✓ |
| `prepare_compactor_proposal_run_input` 返回完整 `CompactorProposalRunInput` | 所有 11 个字段都有有效值 | 行 2207-2219: 所有字段赋值 | ✓ |
| `run_prepared_compactor_proposal` 调用 `FakeContextCompactor.compact()` | deterministic fake candidate | 行 2236: `await super().compact(...)` | ✓ |
| accepted event payload 携带 manifest ref/digest | ref 以 `runner-call-manifest:` 开头，digest 非空 | `_assert_accepted_payload_has_proposal_manifest`（行 5707-5720） | ✓ |
| rejected event payload 携带 manifest ref/digest | ref 以 `runner-call-manifest:` 开头，digest 非空 | `_assert_rejected_payload_has_proposal_manifest`（行 5724-5740） | ✓ |
| `_StaleMutatingCompactor` 不迁移 | 仍继承 `FakeContextCompactor`，不走 prepared path | 行 531：`class _StaleMutatingCompactor(FakeContextCompactor):` | ✓ |
| `_TransactionReadableCompactor` 保留独立读事务语义 | 先读事务验证 Run 存在，再 super compact | 行 512-522：`run_read` 后 `super().run_prepared_compactor_proposal` | ✓ |
| `_RequestCapturingCompactor` request 捕获 | 通过父类 `prepared_requests` 捕获 | 行 625-626：空类，真源在父类 | ✓ |
| `_QualityRejectOnceCompactor` 两次 proposal 语义 | 第一次带 diagnostic，第二次 clean | 行 598-616：`if self.calls == 1: replace(candidate, diagnostics=...)` | ✓ |
| `_RaisingCompactor` 为 post-manifest failure | `fail_run=True`，manifest 后抛异常 | 行 577-588：`super().__init__(fail_run=True)` | ✓ |

**First-principles motivation 验证：通过。**

---

## Production Code Path Verification

逐行验证测试 seam 是否真实触发生产 manifest 路径：

### 入口: `run_compaction_operation` (`compaction_operation.py:749`)

```python
if isinstance(compactor, CompactorProposalPreparedCompactor):
```

- `_PreparedManifestProactiveCompactor` 实现两方法 → `isinstance` 返回 `True` → 进入 prepared 路径 ✓
- `FakeContextCompactor` 不实现 → `isinstance` 返回 `False` → legacy 路径 ✓（excluded tests 正确使用）
- `CompactorProposalPreparedCompactor` 是 `@runtime_checkable` Protocol（line 133）✓

### prepare 阶段 (`compaction_operation.py:750-755`)

```python
prepared_input = compactor.prepare_compactor_proposal_run_input(...)
```

→ `_PreparedManifestProactiveCompactor.prepare_compactor_proposal_run_input`（test 行 2174-2219）
  - 通过 `conversation_compact_input_vnext_from_material_pack(request.material_pack)` 构造 `compact_input` ✓
  - 通过 `_proposal_compactor_agent_request(...)` 构造 deterministic `AgentRunRequest` ✓
  - `compaction_request_digest=request.digest()` ✓
  - `role_sequence_digest=runner_role_sequence_digest(roles)` ✓

### manifest record 阶段 (`compaction_operation.py:756-762`)

```python
manifest_reference = _record_compactor_proposal_manifest(...)
```

→ 调用 `DurableCompactorProposalManifestRecorder`，产出真实 durable manifest ref（以 `runner-call-manifest:` 开头）和 digest ✓

### run 阶段 (`compaction_operation.py:763-766`)

```python
candidate = await compactor.run_prepared_compactor_proposal(prepared_input)
```

→ `_PreparedManifestProactiveCompactor.run_prepared_compactor_proposal`（test 行 2221-2239）
  - `fail_run=True` 时抛 `RuntimeError` → caught at line 767-771 → `_CompactorProposalExecutionError` with `proposal_manifest_reference=manifest_reference` ✓
  - `fail_run=False` 时 → `super().compact(self._latest_prepared_request(), ...)` → `FakeContextCompactor.compact()` → deterministic vNext candidate ✓

### accepted guard (`dispatch.py:1264-1269`)

```python
accepted_proposal_manifest_ref=_required_compactor_manifest_ref(result),
accepted_proposal_manifest_digest=_required_compactor_manifest_digest(result),
```

→ `_required_compactor_manifest_ref`（line 3734-3745）：`None` 或空字符串时抛 `RuntimeError` ✓
→ manifest record 成功时，`result.accepted_proposal_manifest_ref` 和 `result.accepted_proposal_manifest_digest` 非空 → guard 通过 ✓

### accepted event payload (`dispatch.py:1669-1670`)

```python
accepted_proposal_manifest_ref=accepted_proposal_manifest_ref,
accepted_proposal_manifest_digest=accepted_proposal_manifest_digest,
```

→ 测试断言 `_assert_accepted_payload_has_proposal_manifest` 验证这些字段 ✓

### rejected event payload (`dispatch.py:2017-2018`)

```python
proposal_manifest_ref=rejected.proposal_manifest_ref,
proposal_manifest_digest=rejected.proposal_manifest_digest,
```

→ 测试断言 `_assert_rejected_payload_has_proposal_manifest` 验证这些字段 ✓

**生产代码路径验证：通过。测试 seam 正确触发 manifest 生产路径，与生产 `_required_compactor_manifest_ref/digest` guard 和 payload builder 形成完整闭环。**

---

## Architecture Boundary Verification

| 检查项 | 结果 |
|---|---|
| 生产代码变更 | 无 — `dayu/host/dispatch.py`、`dayu/host/compaction_operation.py`、`dayu/host/context_events.py` 均未修改 |
| 反向 import | 无 — 测试从 `dayu.host.*` / `dayu.engine.*` import，方向正确 |
| 跨层穿透 | 无 — 所有 import 来自已有 public 模块 |
| schema 变更 | 无 |
| EventLog payload builder 变更 | 无 |
| public interface 变更 | 无 |
| Engine contract 变更 | 无 |
| compatibility wrapper / facade | 无 — `FakeContextCompactor` 未修改，旧 fake 不自动具备 manifest 能力 |
| 测试 seam 泄露 | 无 — 所有新增类型/函数均为模块级私有（`_` 前缀） |

**架构边界：通过。**

---

## LLM-facing 语义约束检查

| 检查项 | 结果 |
|---|---|
| prompt / prompt fragment 变更 | 无 |
| tool schema 变更 | 无 |
| Host/Engine/Tool 投影 message 变更 | 无 |
| compact / trace / evidence material 变更 | 无 |
| 新增 LLM-facing 文本 | 无 — 仅测试 seam 变更，测试不在 LLM-facing 范围内 |

**LLM-facing 语义约束：通过（无变更）。**

---

## 类型与 README 触发规则

### pyright

```
errors=0, warnings=0, informations=0
```

### README 触发规则

| README | 触发条件 | 是否命中 | 是否需要更新 |
|---|---|---|---|
| 根目录 `README.md` | `dayu/cli/`、`dayu/render/`、`utils/` 修改或项目级使用方式/配置入口变化 | 否 | 否 |
| `dayu/README.md` | 分层关系、装配方式、边界变化 | 否 | 否 |
| `dayu/engine/README.md` | `dayu/engine/` 修改 | 否 | 否 |
| `dayu/host/README.md` | `dayu/host/` 修改 | 否（无生产代码变更） | 否 |
| `dayu/fins/README.md` | `dayu/fins/` 修改 | 否 | 否 |
| `dayu/config/README.md` | `dayu/config/` 修改 | 否 | 否 |
| `tests/README.md` | `tests/` 修改 | 是 | 检查后：否 — 测试分层、运行方式、约定与维护规则均未改变 |

**README 决策：无需更新。**

---

## Adversarial Failure Pass

| 攻击面 | 检查结果 |
|---|---|
| 空 prepared request（`_latest_prepared_request` 返回 None） | `AssertionError` 守卫（行 2248-2250） |
| `_RaisingCompactor` post-manifest failure 时序 | manifest record（`compaction_operation.py:756`）在 `run_prepared_compactor_proposal`（`compaction_operation.py:764`）之前；`_CompactorProposalExecutionError` 携带 `proposal_manifest_reference` |
| `_QualityRejectOnceCompactor` 多次 prepare 间 `_prepared_request` 污染 | 每次 `prepare_compactor_proposal_run_input` 覆写 `self._prepared_request`（行 2192），`run_prepared_compactor_proposal` 读最新值 |
| `FakeContextCompactor` 仍被 excluded tests 使用 | excluded tests 在 compaction operation 前 fail closed（count limit / corrupted count），或走 reactive 路径 |
| `_RaisingCompactor` 多使用点 | grep 确认仅 `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`（行 4156）一处使用，与 plan Decision 10 一致 |
| Protocol signature mismatch → legacy path | 签名逐项对齐 `compaction_operation.py:137-167` |
| `_PreparedManifestProactiveCompactor.__init__` 不调用 `super().__init__()` | `FakeContextCompactor` 和 `ContextCompactor`（Protocol）均无 `__init__` 定义；MRO fall through 到 `object.__init__()`；62 tests 全部通过确认无副作用 |
| `_TransactionReadableCompactor` 原使用独立 `self._fake` 实例，现用 `super().compact()` | `FakeContextCompactor.compact()` 是 stateless（每次创建新 `FakeConversationCompactorVNext()`），等价 |
| import 冲突或命名空间污染 | 新增 import/helper 均为私有（`_` 前缀）；pytest collection 成功（62 collected） |
| `compaction_request_digest=request.digest()` 算法稳定性 | `CompactionRequest.digest()` 是 contract 级方法，其变更是 contract 级变更 |

**Adversarial failure pass：无新脆弱点发现。**

---

## State Machine Check

proactive compaction state machine（`design.md:3230-3238`）：

```
proactive trigger → CONTEXT_COMPACTION_REQUESTED
  → bounded compaction operation
  → CONTEXT_COMPACTED (accepted) 或 CONTEXT_COMPACTION_ATTEMPT_REJECTED (rejected, retryable)
  → CONTEXT_COMPACTION_FAILED (terminal failure)
  → RUN_STARTED / ATTEMPT_STARTED (dispatch)
```

| 状态路径 | 测试覆盖 | 验证 |
|---|---|---|
| accepted: request → compact → `CONTEXT_COMPACTED` | `test_pre_start_governance_soft_threshold_compacts_before_attempt`, `test_wake_queue_promotion_uses_tracked_async_promotion_task`, `test_multi_turn_proactive_compact_feeds_subsequent_run_input` + 3 request capture tests | manifest ref/digest 断言通过 |
| quality rejection → retry → accept: `CONTEXT_COMPACTION_ATTEMPT_REJECTED` → `CONTEXT_COMPACTED` | `test_proactive_compaction_retries_quality_rejection_before_accept` | rejected + accepted manifest 断言通过 |
| proposal failure → retry → exhausted: 2x `CONTEXT_COMPACTION_ATTEMPT_REJECTED` → `CONTEXT_COMPACTION_FAILED` | `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` | 2 rejected rows 均断言 manifest ref/digest |
| stale: compact → stale check → `CONTEXT_COMPACTION_FAILED` | `test_compaction_stale_result_does_not_write_compacted_event` | 正确不迁移，`CONTEXT_COMPACTED == 0`，stale failure reason 不变 |
| count limit: blocked before compact operation | `test_pre_start_governance_proactive_count_limit_blocks_second_compact` | compact operation 前 fail closed，不触发 manifest guard |

**状态机覆盖：通过。所有 proactive compaction 状态路径 covered，无孤儿状态或未覆盖终态。**

---

## Gate Chain Completeness

| Gate | Artifact | Verdict | Status |
|---|---|---|---|
| Plan | `wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md` | — | accepted (`d90a2a99`) |
| Plan Review (DS) | `wu-cm-01-f04-plan-review-ds.md` | pass-with-findings (3B + 4NB) | complete |
| Plan Review (MiMo) | `wu-cm-01-f04-plan-review-mimo.md` | pass-with-findings (4NB) | complete |
| Plan Fix (Codex) | `wu-cm-01-f04-plan-fix-codex.md` | 7 fixed + 1 rejected | complete |
| Plan Re-review (DS) | `wu-cm-01-f04-plan-rereview-ds.md` | pass | complete |
| Plan Re-review (MiMo) | `wu-cm-01-f04-plan-rereview-mimo.md` | pass | complete |
| Implementation (Codex) | `wu-cm-01-f04-implementation-codex.md` | ready (8 passed, 0 errors) | accepted (`bfba6263`) |
| Code Review (DS) | `wu-cm-01-f04-code-review-ds.md` | pass-with-findings (1NB low) | complete |
| Code Review (MiMo) | `wu-cm-01-f04-code-review-mimo.md` | pass | complete |
| Code Fix (Codex) | `wu-cm-01-f04-code-review-fix-codex.md` | 1 fixed | complete |
| Code Re-review (DS) | `wu-cm-01-f04-code-review-rereview-ds.md` | pass | complete |
| Code Re-review (MiMo) | `wu-cm-01-f04-code-review-rereview-mimo.md` | pass | complete |
| Aggregate Deepreview (DS) | `wu-cm-01-f04-aggregate-deepreview-ds.md` | pass-with-findings (2NB low) | complete |
| Aggregate Deepreview (MiMo) | `wu-cm-01-f04-aggregate-deepreview-mimo.md` | pass | complete |
| **PR Review (DS)** | **本 artifact** | — | **current gate** |

**Gate 链完整。所有 prior gate findings 均已通过 fix → re-review 闭环关闭。**

---

## Test Validation

### 本轮运行验证

| 验证项 | 命令 | 结果 |
|---|---|---|
| focused proactive tests | `pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task" -x -q` | **8 passed, 54 deselected** in 0.39s |
| 3 focused manifest tests | `pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt ...::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog -x -q` | **3 passed** in 0.31s |
| 全量 test_dispatch_scheduler.py | `pytest tests/host/test_dispatch_scheduler.py -x -q` | **62 passed** in 1.25s |
| pyright | `pyright` | **0 errors, 0 warnings, 0 informations** |

**与 prior gates (implementation / code review / code re-review / aggregate deepreview) 报告一致。全量 62 tests 通过，验证无回归。**

### 未运行的测试

- `tests/host/test_compaction_operation.py` — prepared manifest seam 参考实现有独立测试覆盖，不在本 work unit 范围
- `tests/host/test_engine_ingest_mapping.py` — reactive prepared manifest tests，有独立覆盖
- 全量 `pytest` — 未运行，但本 work unit 仅修改 `tests/host/test_dispatch_scheduler.py`，该文件全量 62 passed 已覆盖

---

## Findings

### 1-未修复-低-`_RequestCapturingCompactor` 降级为空别名后命名语义与真源不一致

- **入口/函数**: `_RequestCapturingCompactor` 类定义
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:625-626`（当前 branch）
- **输入场景**: 未来开发者阅读类名时，可能误认为该类有自己的 request 捕获状态
- **实际分支**: `_RequestCapturingCompactor` 当前是纯空别名类，所有 request 捕获真源在父类 `_PreparedManifestProactiveCompactor.prepared_requests`
- **预期行为**: 命名与真源一致；若保留命名，应在 docstring 明确写 "request 捕获真源在父类 `prepared_requests`"
- **实际行为**: 类名暗示"捕获 request"能力，但实际上空的。两个 request capture test 读取 `compactor.prepared_requests` 而非 `compactor.requests`
- **直接证据**: 行 625-626 类体为空；grep 确认 `self.requests` 和 `compactor.requests` 在文件中均已删除；使用点行 3788-3789、3832 读 `prepared_requests`
- **影响**: 无 correctness 影响。仅 maintainability —— 未来开发者可能花时间在 `_RequestCapturingCompactor` 中找 request 捕获逻辑，发现是空类后再追踪父类
- **建议改法和验证点**: 可在 docstring 明确写 "request 捕获真源在父类 `prepared_requests`"；或如果不需要命名，替换为 `_PreparedManifestProactiveCompactor()` 并删除该类。验证：`grep _RequestCapturingCompactor` 确认使用点
- **修复风险**: 低
- **严重程度**: 低

---

## Open Questions

无。

---

## Residual Risk

| # | Risk | Classification | Owner | Mitigation |
|---|---|---|---|---|
| R1 | `_RequestCapturingCompactor` 空别名命名语义不一致 | **maintainability** — 低影响 | maintainer / future cleanup | 见 Finding 1 |
| R2 | `CompactionRequest.digest()` 算法变更导致 test digest 常量需同步更新 | **contract-evolution** — 与所有依赖 `request.digest()` 的生产/测试代码共享同一风险面 | 合约维护者 | `request.digest()` 变更是 contract 级变更，会有对应 work unit |
| R3 | 未来新增 proactive test 直接注入 `FakeContextCompactor()` 会再次触发 manifest guard failure | **process-gap** — Slice 0/Slice 4 grep 扫描在 implementation gate 一次性执行 | maintainer | 新增 proactive test 时应检查 compactor injection 是否对齐当前 contract |
| R4 | reactive compaction seam 后续对齐 | **out-of-scope** — 不在本 WU-CM-01-F04 范围 | 未来 work unit | reactive tests 已有独立 prepared manifest seam |

---

## Verdict

**draft-PR-pass** —— 0 blocking findings，2 non-blocking findings（均为 low severity）。

核心判断：

1. **实现正确**：`_PreparedManifestProactiveCompactor` 正确实现 `CompactorProposalPreparedCompactor` protocol，触发生产 manifest recorder 路径，accepted/rejected event payload manifest ref/digest 断言覆盖完整。
2. **边界守得住**：无生产代码、schema、Engine contract、public interface 变更；`_StaleMutatingCompactor` 正确排除；旧 `FakeContextCompactor` 不自动具备 manifest 能力；无 cross-layer penetration。
3. **设计真源对齐**：与 `docs/host/design.md:3225-3278` 和 `docs/engine/design.md:414-423` 一致。
4. **总控一致**：PR body 与 `docs/host/issues-implementation-control.md` 记录一致。
5. **Gate 链完整**：plan → review → fix → re-review → implementation → code review → fix → re-review → aggregate deepreview → PR review，所有 prior gate findings 已关闭。
6. **验证充分**：focused 8 tests + focused 3 tests + 全量 62 tests 全部通过；pyright 0 errors。

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
- `docs/reviews/wu-cm-01-f04-aggregate-deepreview-ds.md` — DS aggregate deepreview（+783，新增）
- `docs/reviews/wu-cm-01-f04-aggregate-deepreview-mimo.md` — MiMo aggregate deepreview（+149，新增）
