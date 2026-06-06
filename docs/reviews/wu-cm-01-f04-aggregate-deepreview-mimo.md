# WU-CM-01-F04 Aggregate Deepreview

## Scope

- Mode: aggregate deepreview (phaseflow gate)
- Branch: phaseflow/host-issues
- Base: main
- Output file: docs/reviews/wu-cm-01-f04-aggregate-deepreview-mimo.md
- Review target:
  - 当前分支相对 main 的完整 diff（14 files changed, +1829 / -67）
  - accepted plan commit `d90a2a99`
  - accepted implementation slice commit `bfba6263`
  - controller bookkeeping commits `626911f1` / `f56b93cd`
  - 11 artifacts under docs/host and docs/reviews for WU-CM-01-F04
- Design source: `docs/host/design.md`、`docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Included scope:
  - `tests/host/test_dispatch_scheduler.py` — implementation diff
  - `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md` — plan artifact
  - `docs/host/issues-implementation-control.md` — gate bookkeeping diff
  - 11 docs/reviews artifacts — review/re-review/fix chain
- Excluded scope:
  - 生产代码 `dayu/host/dispatch.py`、`dayu/host/compaction_operation.py` — 只读验证，不修改
  - reactive compaction test seam — 不在本 work unit 范围
- Parallel review coverage: 无

## Artifact Chain

| Gate | Agent | Artifact | Verdict |
|---|---|---|---|
| plan review (MiMo) | AgentMiMo | wu-cm-01-f04-plan-review-mimo.md | pass-with-findings (4 non-blocking) |
| plan review (DS) | AgentDS | wu-cm-01-f04-plan-review-ds.md | pass-with-findings (3 blocking + 4 non-blocking) |
| plan fix | AgentCodex | wu-cm-01-f04-plan-fix-codex.md | 7 fixed, 1 rejected |
| plan re-review (MiMo) | AgentMiMo | wu-cm-01-f04-plan-rereview-mimo.md | pass |
| plan re-review (DS) | AgentDS | wu-cm-01-f04-plan-rereview-ds.md | pass |
| implementation | AgentCodex | wu-cm-01-f04-implementation-codex.md | 8 passed, pyright 0 errors |
| code review (MiMo) | AgentMiMo | wu-cm-01-f04-code-review-mimo.md | pass (1 non-blocking low) |
| code review (DS) | AgentDS | wu-cm-01-f04-code-review-ds.md | pass-with-findings (1 non-blocking low) |
| code review fix | AgentCodex | wu-cm-01-f04-code-review-fix-codex.md | accepted finding fixed |
| code review re-review (MiMo) | AgentMiMo | wu-cm-01-f04-code-review-rereview-mimo.md | pass |
| code review re-review (DS) | AgentDS | wu-cm-01-f04-code-review-rereview-ds.md | pass |

## Design Alignment Verification

### Host 设计真源对齐

| 检查项 | 设计位置 | 验证结果 |
|---|---|---|
| proactive trigger 路径：`CONTEXT_COMPACTION_REQUESTED` → bounded compaction operation → `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` → rebuild → dispatch | `design.md:3225-3238` | 对齐 — implementation 不修改此路径 |
| compact events 记录 durable manifest ref/digest | `design.md:3263-3266` | 对齐 — test seam 现在产出 manifest |
| compact 不改写历史 EventLog、fallback 不提交 `CONTEXT_COMPACTED`、compact 有 policy 上限 | `design.md:3268-3275` | 对齐 — 未触碰这些不变量 |

### Engine 设计真源对齐

| 检查项 | 设计位置 | 验证结果 |
|---|---|---|
| Engine 不做 proactive threshold compaction、Host budget policy 或 compact/retry | `engine/design.md:414-423` | 对齐 — 未修改 Engine contract |

### 总控文档对齐

| 检查项 | 控制文档位置 | 验证结果 |
|---|---|---|
| 只修 Host proactive scheduler test seam | `issues-implementation-control.md:540-571` | 对齐 — 只改 tests/host/test_dispatch_scheduler.py |
| 不改 production guard / schema / Engine contract | non-goals (line 558-563) | 对齐 — 0 production 代码变更 |
| 7 个 manifest-ref failures 关闭 | 验收信号 (line 567) | 对齐 — 8 passed (含 1 个 wake queue promotion) |
| accepted/rejected event payload manifest assertions | 验收信号 (line 568-569) | 对齐 — `_assert_accepted_payload_has_proposal_manifest` / `_assert_rejected_payload_has_proposal_manifest` |
| pyright 0 errors | 验收信号 (line 571) | 对齐 — 0 errors |

## Implementation Verification

### Compactor Migration 一致性

| Compactor | 原路径 | 迁移后 | 语义保留 |
|---|---|---|---|
| `_PreparedManifestProactiveCompactor` | 新增 | 实现 `CompactorProposalPreparedCompactor` protocol | N/A — 新基类 |
| `_TransactionReadableCompactor` | `compact()` 中 `run_read` | `run_prepared_compactor_proposal()` 中 `run_read` + `super()` | 独立读事务语义保留 |
| `_RequestCapturingCompactor` | `compact()` 中 `self.requests.append` | 继承 `_PreparedManifestProactiveCompactor`，捕获由 `prepared_requests` 承担 | request 捕获语义保留（真源统一到父类） |
| `_QualityRejectOnceCompactor` | `compact()` 首次返回 invalid diagnostic | `run_prepared_compactor_proposal()` 首次返回 `replace(candidate, diagnostics=...)` | quality rejection 语义保留 |
| `_RaisingCompactor` | `compact()` 直接 raise | `run_prepared_compactor_proposal()` 中 `fail_run=True` raise | 语义升级：pre-manifest failure → post-manifest failure（有意） |
| `_StaleMutatingCompactor` | legacy `compact()`，不迁移 | 不变 | 不迁移正确 — stale check 在 manifest guard 前写 `CONTEXT_COMPACTION_FAILED` |

### Protocol 签名对齐

`CompactorProposalPreparedCompactor` 是 `@runtime_checkable` Protocol（`compaction_operation.py:133-134`）。

| Protocol 方法 | Protocol 签名 | `_PreparedManifestProactiveCompactor` 实现 | 匹配 |
|---|---|---|---|
| `prepare_compactor_proposal_run_input` | `(self, request, cancellation_token, *, compaction_operation_id, compaction_attempt_number) -> CompactorProposalRunInput` | 行 422-460 | 完全一致 |
| `run_prepared_compactor_proposal` | `async (self, prepared_input) -> ConversationCompactOutputVNext` | 行 462-487 | 完全一致 |

### Manifest Assertion 覆盖

| 断言 helper | 断言字段 | 格式要求 | 对应 payload builder |
|---|---|---|---|
| `_assert_accepted_payload_has_proposal_manifest` | `accepted_proposal_manifest_ref`、`accepted_proposal_manifest_digest` | ref 以 `runner-call-manifest:` 开头、str 类型；digest 非空 str | `build_context_compacted_payload` (`context_events.py:310-311`) |
| `_assert_rejected_payload_has_proposal_manifest` | `proposal_manifest_ref`、`proposal_manifest_digest` | ref 以 `runner-call-manifest:` 开头、str 类型；digest 非空 str | `build_context_compaction_attempt_rejected_payload` (`context_events.py:595-596`) |

### 排除项验证

| 排除项 | 理由 | 当前状态 | 验证 |
|---|---|---|---|
| `_StaleMutatingCompactor` | stale check 在 accepted guard 前写 `CONTEXT_COMPACTION_FAILED`，不触发 manifest guard | 仍使用 legacy `compact()` | test 断言 `CONTEXT_COMPACTED == 0`，不迁移正确 |
| proactive count limit / corrupted count tests | compaction operation 前 fail closed | 仍使用 `FakeContextCompactor()` | 不触发 manifest guard |
| reactive tests | 不在 proactive seam closeout 范围 | 仍使用 `FakeContextCompactor()` | 已有独立 reactive prepared manifest seam |

## Findings

未发现实质性问题。

prior review chain 中唯一的 finding（`_RequestCapturingCompactor.requests` 与父类 `prepared_requests` 双重存储，severity: low）已在 code review fix gate 中修复，re-review 确认 `prepared_requests` 是 request capture 唯一真源。

## Open Questions

无。

## Validation Reviewed / Run

本 aggregate deepreview gate 实际运行以下验证并确认通过：

| 验证项 | 命令 | 结果 |
|---|---|---|
| focused proactive tests | `pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"` | **8 passed, 54 deselected** |
| focused accepted/rejected tests | `pytest ...::test_pre_start_governance_soft_threshold_compacts_before_attempt ...::test_proactive_compaction_retries_quality_rejection_before_accept ...::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` | **3 passed** |
| full test file regression | `pytest tests/host/test_dispatch_scheduler.py` | **62 passed** |
| pyright | `pyright tests/host/test_dispatch_scheduler.py` | **0 errors, 0 warnings, 0 informations** |

Prior gate 验证记录汇总：

| Gate | 验证 | 结果 |
|---|---|---|
| implementation (Codex) | focused proactive (8) + focused 3 + pyright | 8 passed + 3 passed + 0 errors |
| code review (MiMo) | focused proactive (8) + pyright (test file) | 8 passed + 0 errors |
| code review (DS) | focused proactive (8) + focused 2 + pyright | 8 passed + 2 passed + 0 errors |
| code review fix (Codex) | focused proactive (8) + focused 2 + pyright | 8 passed + 2 passed + 0 errors |
| code review re-review (MiMo) | focused proactive (8) + focused 2 | 8 passed + 2 passed |
| code review re-review (DS) | focused proactive (8) + focused 2 + pyright | 8 passed + 2 passed + 0 errors |

## Residual Risks / Uncovered Areas

| 风险 | 分类 | 说明 |
|---|---|---|
| reactive compaction test seam 后续对齐 | out-of-scope | reactive tests 仍使用 `FakeContextCompactor()`，已有独立 prepared manifest seam 覆盖；若未来 reactive manifest contract 升级需类似迁移，但不属于本 work unit |
| `_RequestCapturingCompactor` 命名与捕获真源分离 | deferred cleanup | 类为空壳，capture 真源在父类 `prepared_requests`；命名保留减少测试阅读迁移成本，不影响 correctness |
| `_StaleMutatingCompactor` 若未来 production contract 要求 stale attempt 也记录 manifest | deferred future work | 当前 stale check 在 manifest guard 前，不迁移正确；若 contract 变更需单独 work unit |
| `RUNNER_CALL_INPUT_ASSEMBLED` event count 断言未加入 | accepted design decision | 按 plan conditional assertion 策略，核心验收为 compacted/rejected payload manifest ref/digest，不依赖脆弱计数 |

## Verdict

**pass** — 整个 work unit 符合 design source 和 control doc：只修改 Host proactive scheduler test seam，不改 production guard / schema / Engine contract。committed implementation 通过 first-principles motivation：manifest-producing prepared compactor seam 正确触发 durable manifest recorder，accepted/rejected event payload 直接断言 manifest ref/digest，`_StaleMutatingCompactor` 正确排除，`_TransactionReadableCompactor` / `_RequestCapturingCompactor` / `_QualityRejectOnceCompactor` / `_RaisingCompactor` 语义保留。plan/review/fix/re-review artifacts 一致，无未分类 residual risk。focused validation（8 passed）和 full file regression（62 passed）均通过，pyright 0 errors。无 blocking findings。
