# PR Review — WU-CM-01-F04 Proactive Compaction Manifest Test Seam Closeout

## Scope

- Mode: PR
- PR: #124
- Title: phaseflow: restore proactive compaction manifest test seam
- Author: noho
- Head branch: `phaseflow/host-issues`
- Base branch: `main`
- URL: https://github.com/noho/dayu-agent-r/pull/124
- Output file: `docs/reviews/wu-cm-01-f04-pr-review-mimo.md`
- Review date: 2026-06-06T21:04:03+08:00

### Included scope

- PR #124 相对 `main` 的完整 diff（16 files, +2322/-67）
- 关键 implementation file: `tests/host/test_dispatch_scheduler.py`
- Controller bookkeeping: `docs/host/issues-implementation-control.md`
- Plan artifact: `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md`
- Gate review artifacts: `docs/reviews/wu-cm-01-f04-*`
- 设计真源: `docs/host/design.md`, `docs/engine/design.md`
- 生产代码只读验证: `dayu/host/dispatch.py`, `dayu/host/compaction_operation.py`

### Excluded scope

- 不审查 `dayu/host/dispatch.py`、`dayu/host/compaction_operation.py` 的非 WU-CM-01-F04 相关代码路径
- 不审查 reactive compaction test seam
- 不审查 `tests/host/test_dispatch_scheduler.py` 中非 proactive compaction 的测试

### Parallel review coverage

无。本 PR review 为单 reviewer 审查。

---

## PR Body 一致性验证

PR body 声明：

| PR body 声明 | 实际验证 | 通过 |
|---|---|---|
| Implements WU-CM-01-F04: restores Host proactive scheduler tests to use a manifest-producing prepared compactor seam | `_PreparedManifestProactiveCompactor` 实现 `CompactorProposalPreparedCompactor` protocol，proactive tests 迁移到 prepared path | ✓ |
| Keeps production compact fail-closed behavior unchanged | diff 仅含 test 和 docs 变更，无生产代码修改 | ✓ |
| No Host production code, Engine code, schema, or public contract changes | `git diff main...HEAD --stat` 确认仅 `tests/` 和 `docs/` 变更 | ✓ |
| Adds accepted/rejected proposal manifest ref/digest assertions | `_assert_accepted_payload_has_proposal_manifest` 和 `_assert_rejected_payload_has_proposal_manifest` 已实现 | ✓ |
| Validation: 8 passed focused, 3 passed focused, 62 passed full, pyright 0 errors | 全部验证通过（已复现） | ✓ |

**PR body 与 implementation 一致。**

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
| Aggregate Deepreview (DS) | `docs/reviews/wu-cm-01-f04-aggregate-deepreview-ds.md` | pass-with-findings (2NB) | complete |
| Aggregate Deepreview (MiMo) | `docs/reviews/wu-cm-01-f04-aggregate-deepreview-mimo.md` | — | complete |
| Draft PR | `4a988fba` | — | opened |

**Gate 链完整。所有 plan findings 和 code review findings 均已通过 fix → re-review 闭环关闭。**

---

## 设计真源对齐验证

### Host 设计对齐（`docs/host/design.md:3225-3280`）

| 设计要求 | 实现对齐 | 证据 |
|---|---|---|
| proactive trigger 是 dispatch Attempt 前的 Host governance | 未修改生产代码，test seam 只改变 compactor injection | `tests/host/test_dispatch_scheduler.py` diff 无 prod 变更 |
| compact operation 在 write transaction 外执行 | `_TransactionReadableCompactor.run_prepared_compactor_proposal` 仍通过独立读事务验证 Run 存在 | 行 512-522: `self._transaction_runner.run_read(...)` 后 `super().run_prepared_compactor_proposal(prepared_input)` |
| `CONTEXT_COMPACTED` payload 记录 durable 信息 | `_assert_accepted_payload_has_proposal_manifest` 断言 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` | 行 5707-5720 |
| compact 不变量：不能改写历史 EventLog、fallback 不提交 `CONTEXT_COMPACTED` | `_StaleMutatingCompactor` 不迁移，stale test 断言 `CONTEXT_COMPACTED == 0` | 保持原测试语义 |

### Engine 设计对齐（`docs/engine/design.md:414-423`）

| 设计要求 | 实现对齐 | 证据 |
|---|---|---|
| Engine 不做 proactive threshold compaction | 无 Engine 代码变更 | diff 仅含 `tests/host/test_dispatch_scheduler.py` |
| Engine 只在 provider overflow 时发出 reactive compaction request | 无 Engine contract 变更 | 无 Engine 相关 import 或调用变更 |

**设计真源对齐：通过。**

---

## Correctness 验证

### Protocol Signature 对齐

`_PreparedManifestProactiveCompactor` 实现 `CompactorProposalPreparedCompactor` protocol：

```python
# Protocol 定义 (compaction_operation.py:133-167)
@runtime_checkable
class CompactorProposalPreparedCompactor(Protocol):
    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
    ) -> CompactorProposalRunInput: ...

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> ConversationCompactOutputVNext: ...
```

测试 helper 实现（`test_dispatch_scheduler.py:421-468`）：

```python
def prepare_compactor_proposal_run_input(
    self,
    request: CompactionRequest,
    cancellation_token: CancellationToken,
    *,
    compaction_operation_id: str | None,
    compaction_attempt_number: int,
) -> CompactorProposalRunInput: ...

async def run_prepared_compactor_proposal(
    self,
    prepared_input: CompactorProposalRunInput,
) -> ConversationCompactOutputVNext: ...
```

**签名严格对齐，`isinstance(compactor, CompactorProposalPreparedCompactor)` 可正确命中。**

### Manifest Ref/Digest 断言验证

- `_assert_accepted_payload_has_proposal_manifest`: 断言 `accepted_proposal_manifest_ref` 以 `runner-call-manifest:` 开头，`accepted_proposal_manifest_digest` 非空
- `_assert_rejected_payload_has_proposal_manifest`: 断言 `proposal_manifest_ref` 以 `runner-call-manifest:` 开头，`proposal_manifest_digest` 非空

**断言覆盖完整：accepted 和 rejected payload 均有 manifest ref/digest 断言。**

### Compactor 迁移完整性

| Compactor | 迁移状态 | 保留语义 | 验证 |
|---|---|---|---|
| `_PreparedManifestProactiveCompactor` | 新增 | prepared manifest producing | ✓ |
| `_TransactionReadableCompactor` | 迁移 | 独立读事务可读 Run | ✓ |
| `_RaisingCompactor` | 迁移 | post-manifest proposal failure | ✓ |
| `_QualityRejectOnceCompactor` | 迁移 | 第一次 quality rejection + 第二次 accepted | ✓ |
| `_RequestCapturingCompactor` | 迁移 | request 捕获（真源在父类 `prepared_requests`） | ✓ |
| `_StaleMutatingCompactor` | 不迁移 | `CONTEXT_COMPACTED == 0`，stale check 在 accepted guard 前 | ✓ |

**迁移完整性：通过。**

---

## Host/Engine 边界验证

- 无 Engine 代码变更
- 无 Engine contract 变更
- test seam 只在 Host proactive scheduler 层
- proactive compaction 是 Host governance，不涉及 Engine state machine

**Host/Engine 边界：未违反。**

---

## LLM-facing 语义约束验证

- 本次变更仅涉及测试 seam 和测试断言
- 无 tool schema、prompt、memory、compact、trace、evidence material 变更
- 无 LLM-facing 文本变更

**LLM-facing 语义约束：不适用（无 LLM-facing 内容变更）。**

---

## 类型与 README 触发规则验证

### Pyright 验证

```
source .venv/bin/activate && pyright tests/host/test_dispatch_scheduler.py
=> 0 errors, 0 warnings, 0 informations
```

### README 触发规则

- 修改仅限 `tests/host/test_dispatch_scheduler.py` → 触发 `tests/README.md` 检查
- `tests/README.md` 无变更（`git diff main...HEAD -- tests/README.md` 无输出）
- 本变更不改变测试分层、运行方式、约定或维护规则 → **无需更新 README**

**类型检查与 README 触发规则：通过。**

---

## 测试验证

### Focused Validation

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"
=> 8 passed, 54 deselected
```

### 补充 Focused Validation

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt tests/host/test_dispatch_scheduler.py::test_proactive_compaction_retries_quality_rejection_before_accept tests/host/test_dispatch_scheduler.py::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog
=> 3 passed
```

### Full Suite Validation

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py
=> 62 passed in 1.24s
```

**全量测试通过，无回归。**

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

---

## Residual Risk

- reactive compaction test seam 不在本 work unit 范围内，已有独立 manifest seam 覆盖。
- `_RequestCapturingCompactor` 降级为空别名类，命名语义与真源不完全一致（父类 `prepared_requests`），但无 correctness 影响，可由后续 cleanup work unit 处理。

---

## Verdict

**PASS — PR 可进入 draft-PR-pass。**

### Blocking Findings

无。

### Nonblocking Findings

无。

### 验证命令证据

```bash
# Focused validation
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"
=> 8 passed, 54 deselected

# Full suite
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py
=> 62 passed in 1.24s

# Type check
source .venv/bin/activate && pyright tests/host/test_dispatch_scheduler.py
=> 0 errors

# README check
git diff main...HEAD -- tests/README.md
=> (empty, no changes needed)
```

### 残余风险

- reactive compaction seam 不在范围内（已有覆盖）
- `_RequestCapturingCompactor` 命名语义可后续 cleanup（无 correctness 影响）
