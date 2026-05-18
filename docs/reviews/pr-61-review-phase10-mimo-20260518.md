# PR #61 Review — Phase 10 Context Governance

Reviewer: AgentMiMo
Date: 2026-05-18
PR: https://github.com/noho/dayu-agent-r/pull/61
Branch: feat/host-phase10-context-governance → main
Gate: draft PR review

## Verdict

**PASS — PR #61 可从 draft 转为 ready for review / merge。**

---

## 1. PR Diff Scope 验证

### 1.1 文件归属

PR 包含 90 个文件变更，全部落在预期域内：

| 域 | 文件数 | 说明 |
| --- | --- | --- |
| `dayu/host/` | 21 | 7 个新模块 + 14 个修改（含 README） |
| `tests/host/` | 24 | 7 个新测试文件 + 17 个修改（含 README） |
| `docs/host/` | 3 | design.md、implementation-control.md、phase10 plan |
| `docs/reviews/` | 42 | S1-S6 + aggregate review artifacts |

**无 workspace/tmp 文件。无无关文件。**

### 1.2 修改文件与 Phase 10 目标一致性

| Phase 10 目标 | 对应文件 | 一致性 |
| --- | --- | --- |
| Host-owned budget policy | `context_policy.py`、`context_budget.py`、`api.py`、`command.py` | ✅ |
| Compactor typed contracts + fake | `compaction.py`、`fake_compaction.py` | ✅ |
| Compact artifact + canonical events | `compact_artifact.py`、`context_events.py`、`durable/event_log.py`、`durable/schema.py` | ✅ |
| P9 memory projection consumption | `memory.py`、`durable/memory.py` | ✅ |
| Proactive governance gate | `dispatch.py`、`admission.py`、`durable/run_transition.py`、`durable/state.py` | ✅ |
| Reactive overflow recovery | `engine_ingest.py`、`dispatch.py` | ✅ |
| RunInputBuilder compact provider | `run_input.py` | ✅ |
| Production composition wiring | `command.py`、`api.py`、`_public_validation.py` | ✅ |

### 1.3 小修改文件验证

17 个已有 test 文件的修改全部是同一模式：在 `_options()` helper 中补充必填 `context_window_size=8192` 和 `reserved_output_tokens=1024`。这是 `HostCommandHandleOptions` 改为必填字段后的机械适配，无逻辑变更。

---

## 2. Control Doc 状态验证

### 2.1 Gate 状态

`docs/host/implementation-control.md` 当前状态：

```
当前 work unit：Phase 10. Context Governance / Compaction。
当前 gate：ready-to-open-draft-PR。
下一 gate：draft PR gate。
```

**PASS。** Gate 已记录为 `ready-to-open-draft-PR`，与 PR 当前状态一致。

### 2.2 Residual Owner 追踪

追踪区包含 4 组残余风险，全部有明确 owner：

| 追踪组 | 项数 | Owner 归属 |
| --- | --- | --- |
| S4 Proactive Context Governance | 3 | compactor adapter owner、tokenizer/sizing owner、API cleanup owner |
| S5 Reactive Overflow Recovery | 2 | EngineEvent ingest owner、Phase 11 lifecycle owner |
| S6 Production Composition | 3 | composition root owner、compactor adapter owner、aggregate owner |
| Aggregate Deepreview | 4 (3 LOW + 1 INFO) | EngineEvent ingest hardening、Phase 13 memory owner、schema cleanup owner |

**PASS。** 所有 residual 均有 owner 和 destination，无无主项。

---

## 3. Aggregate Accepted Residual 评估

### 3.1 是否阻塞 Draft PR

| Residual | 级别 | 阻塞 PR | 理由 |
| --- | --- | --- | --- |
| R1: Compactor 在 write transaction 内 | accepted | 否 | FakeContextCompactor 同步无延迟；真实 LLM compactor 接入时再设计 |
| R2: Budget estimate 只覆盖 display_text | accepted | 否 | Conservative estimator 偏保守，不会低估 |
| R3: `promote_next_queued_run` 接口面 | accepted | 否 | 无 production caller，README 已说明 |
| R4: `_start_reactive_context_recovery` 偏长 | accepted | 否 | 职责归属清晰，内部已抽 helper |
| R5: composition helper 无 production caller | accepted | 否 | public contract test 已验证 wiring |
| R6: Production LLM compactor 未实现 | accepted | 否 | 未配置时 fail closed，不隐式用 fake |
| R7: Aggregate test 未串 verified fact 链路 | accepted | 否 | 分层测试覆盖 |
| R8: Conservative estimator 精度 | accepted | 否 | 偏保守不影响 correctness |
| DS AG1: DUPLICATE branch 无显式 stop_worker_stream | LOW | 否 | scheduler 通过 terminal_closeout 停止 |
| DS AG2: reactive REQUESTED 在 closeout CAS 前 | LOW | 否 | 同事务校验保证 safety |
| DS AG3: budget 压力 pinned patch 降级 | LOW | 否 | 不影响 Host truth |

**PASS。** 所有 residual 均为 accepted/LOW，不阻塞 draft PR。

---

## 4. PR Body 验证

### 4.1 Summary 准确性

PR body Summary 三条：

1. "Add Host-owned context budget policy, conservative estimator, usage observation, and explicit composition inputs." — ✅ 对应 S1+S6
2. "Add compaction contracts, fake compactor, quality checks, deterministic compact artifacts, and canonical compact events." — ✅ 对应 S2+S3
3. "Wire proactive pre-start compaction, reactive overflow recovery, P9 memory projection consumption, RunInputBuilder compact providers, and multi-turn integration coverage." — ✅ 对应 S3+S4+S5+S6

### 4.2 Validation 命令

PR body 列出的 validation 命令：

```
pytest tests/host/test_public_contracts.py tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q
pytest tests/host/test_context_budget.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py -q
pyright
git diff --check
```

复现结果：81 passed + 180 passed + pyright 0 errors + git diff --check clean。**全部通过。**

### 4.3 Review Artifacts 引用

PR body 引用 3 个 aggregate review artifacts，均存在于 PR diff 中：

- `docs/reviews/phase10-aggregate-deepreview-controller-adjudication-20260518.md` ✅
- `docs/reviews/phase10-aggregate-deepreview-mimo-20260518.md` ✅
- `docs/reviews/phase10-aggregate-deepreview-ds-20260518.md` ✅

### 4.4 PR Body 不足

PR body 未列出 `test_admission_queue.py`（23 passed），但该文件修改仅为机械适配必填 budget fields，不影响 Phase 10 验证完整性。**INFO 级别，不阻塞。**

---

## 5. PR 前必须修复项检查

### 5.1 Correctness

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 主动 compact 在 Attempt 前触发 | PASS | `test_dispatch_scheduler.py:1918` 事件序 |
| 主动 compact failure 无 Attempt | PASS | `test_dispatch_scheduler.py:1962` |
| 被动 overflow recovery 创建新 Attempt | PASS | `test_engine_ingest_mapping.py:296` |
| 被动 recovery failure 不进入 LOST | PASS | `test_engine_ingest_mapping.py:390` |
| 每 Run compact 限 1 次 | PASS | proactive + reactive count limit tests |
| verified_facts 只来自 TOOL_RESULT_ACCEPTED | PASS | `test_memory_projection.py:1146` + 反面测试 |
| Compact artifact 确定性 digest | PASS | `compact_artifact.py:154-167` |
| Corrupted digest 拒绝 | PASS | `compact_artifact.py:156-159` HostDigestMismatchError |

### 5.2 State Machine

| 检查项 | 结论 |
| --- | --- |
| RunStatus.ACCEPTED 创建无 Attempt | PASS |
| cancel ACCEPTED 无 Attempt | PASS |
| RUN_STARTED + ATTEMPT_STARTED 联动 | PASS |
| ATTEMPT_FAILED + RUN_RECOVERING 联动 | PASS |
| RECOVERY → new Attempt + RUN_STARTED(RECOVERY) | PASS |
| RECOVERING failure → RUN_FAILED（非 LOST） | PASS |
| 旧 Attempt 不被 resume/takeover | PASS |

### 5.3 Durability

| 检查项 | 结论 |
| --- | --- |
| Schema v9 包含 'accepted' status | PASS |
| Accepted Run CHECK 约束 | PASS |
| Per-session accepted 唯一索引 | PASS |
| CONTEXT_COMPACTED payload 校验 | PASS |
| Proactive compact count 与 REQUESTED 同事务 | PASS |
| Memory catch-up 在 RUN_STARTED 前 | PASS |

### 5.4 Layering

| 检查项 | 结论 |
| --- | --- |
| Context Governance 不直接写 memory snapshot | PASS |
| Engine 不拥有 budget/memory/recovery | PASS |
| Budget 参数仅来自 typed Host policy | PASS |
| Memory projection 仅消费 committed canonical facts | PASS |
| 7 个新模块无反向依赖 | PASS |
| FakeContextCompactor 不在 production 路径 | PASS |

### 5.5 Tests / Docs

| 检查项 | 结论 |
| --- | --- |
| 261 tests passed | PASS |
| pyright 0 errors | PASS |
| git diff --check clean | PASS |
| README 覆盖 P10 核心内容 | PASS |
| implementation-control.md gate 状态正确 | PASS |

---

## 6. Findings Summary

**无 blocking / high / medium / low / info findings。**

PR diff scope 干净，与 Phase 10 目标完全一致。control doc 已正确记录 gate 状态与 residual owner。aggregate accepted residual 全部不阻塞 draft PR。PR body 准确表达交付与验证。correctness、state machine、durability、layering、tests/docs 全部通过。

---

## 7. Residual 风险矩阵（沿用 aggregate review）

| 风险 | 可能性 | 影响 | 阻塞 PR |
| --- | --- | --- | --- |
| `promote_next_queued_run` 被误用绕过 governance | 低 | 高 | 否 |
| Compactor LLM 调用阻塞 SQLite writes | N/A | 高 | 否 |
| Budget estimate 不完整导致 compact 偏早 | 中 | 低 | 否 |
| RECOVERING 状态无 cancel 路径 | 低 | 中 | 否 |

---

## 8. 结论

PR #61 达到了 Phase 10 设计目标的全部交付：

1. Host-owned `ContextBudgetPolicy` 与 conservative estimator
2. Compactor typed port、fake compactor、quality check 与 deterministic artifact
3. `CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` canonical events
4. P9 memory projection 消费 accepted compact output（pinned state patch 三态语义、episode summary continuity）
5. Proactive pre-dispatch governance gate（Attempt 前触发）
6. Reactive overflow recovery（Engine overflow → Host identity 校验 → RECOVERING → new Attempt）
7. RunInputBuilder durable compact artifact provider + memory snapshot provider
8. Production composition wiring（`context_window_size` / `reserved_output_tokens` 必填）
9. Multi-turn aggregate integration（proactive compact → memory projection → subsequent Engine request）

261 tests passed，pyright 0 errors。8 项 accepted residual + 4 项 DS LOW/INFO 均有 owner，不阻塞 PR。

**PR #61 可从 draft 转为 ready for review / merge。**
