# PR #61 Review — Phase 10 Context Governance (AgentDS)

Reviewer: AgentDS
Date: 2026-05-18
PR: https://github.com/noho/dayu-agent-r/pull/61
Branch: feat/host-phase10-context-governance → main
Gate: draft PR review

## Verdict

**PASS — PR #61 可从 draft 转为 ready for review / merge。**

---

## 1. PR Diff Scope 验证

### 1.1 文件归属

PR 包含 86 个文件变更，全部落在预期域内：

| 域 | 文件数 | 说明 |
| --- | --- | --- |
| `dayu/host/` | 21 | 7 个新模块（compaction.py, compact_artifact.py, context_budget.py, context_events.py, context_governance.py, context_policy.py, fake_compaction.py）+ 14 个修改（含 README） |
| `tests/host/` | 20 | 7 个新测试文件 + 13 个修改（含 README） |
| `docs/host/` | 3 | design.md、implementation-control.md、phase10 plan |
| `docs/reviews/` | 42 | S1-S6 + aggregate review artifacts |

**无 workspace/tmp 文件。无无关文件。无 .env 或 credential 文件。**

### 1.2 修改文件与 Phase 10 目标一致性

全量 `git diff --name-only f131fb8..HEAD` 输出与 Phase 10 的 7 项交付目标逐一匹配，无越界：

| Phase 10 交付目标 | 对应文件 | 一致 |
| --- | --- | --- |
| Host-owned budget policy + conservative estimator | `context_policy.py`、`context_budget.py`、`api.py`、`command.py` | ✓ |
| Compactor typed contracts + fake compactor | `compaction.py`、`fake_compaction.py` | ✓ |
| Compact artifact + canonical events | `compact_artifact.py`、`context_events.py`、`durable/event_log.py`、`durable/schema.py` | ✓ |
| P9 memory projection consumption | `memory.py`、`durable/memory.py` | ✓ |
| Proactive governance gate | `dispatch.py`、`admission.py`、`durable/run_transition.py`、`durable/state.py` | ✓ |
| Reactive overflow recovery | `engine_ingest.py`、`dispatch.py` | ✓ |
| RunInputBuilder compact provider | `run_input.py` | ✓ |
| Production composition wiring | `command.py`、`api.py`、`_public_validation.py` | ✓ |
| Durable schema migration | `durable/schema.py` | ✓ |

### 1.3 小修改文件验证

13 个已有测试文件修改均为同一模式：在 `_options()` / `_command_options()` helper 中补充必填 `context_window_size=8192` 和 `reserved_output_tokens=1024`。这是 `HostCommandHandleOptions` 改为必填字段后的机械适配，无逻辑变更。

---

## 2. Control Doc 状态验证

### 2.1 Gate 状态

`docs/host/implementation-control.md` 当前 gate 行（line 226）：

```
当前 gate：ready-to-open-draft-PR。
```

**PASS。** Gate 已记录为 `ready-to-open-draft-PR`，与 PR 当前 draft 状态一致。

### 2.2 DS Finding 追踪

Controller 接受的 DS AG1 / AG2 / AG3 均已写入控制文档追踪区（line 1555-1562）：

| Finding | 描述 | Owner |
| --- | --- | --- |
| DS AG1 | DUPLICATE branch 未显式 stop_worker_stream | EngineEvent ingest hardening |
| DS AG2 | reactive REQUESTED 在 closeout CAS 前追加 | EngineEvent ingest hardening |
| DS AG3 | budget 压力下 pinned patch 降级 opaque ref | Phase 13 memory diagnostic owner |
| DS INFO | accepted unique index 重叠 + helper 命名 | schema / admission cleanup owner |

**PASS。** 所有 DS aggregate review findings 均已追踪且有明确 owner。

### 2.3 其它 Residual Owner 追踪

| 追踪组 | 项数 | Owner 归属 |
| --- | --- | --- |
| S4 Proactive Context Governance | 3 | compactor adapter owner、tokenizer/sizing owner、API cleanup owner |
| S5 Reactive Overflow Recovery | 2 | EngineEvent ingest owner、Phase 11 lifecycle owner |
| S6 Production Composition | 3 | composition root owner、compactor adapter owner、aggregate owner |
| Aggregate Deepreview | 4 (3 LOW + 1 INFO) | EngineEvent ingest hardening、Phase 13 memory、schema cleanup |

**PASS。** 所有 residual 均有 owner 和 destination，无无主项。

---

## 3. PR Body 验证

### 3.1 Summary 准确性

PR body Summary 三条与 7 个 commit 的实际交付一致：

1. "Add Host-owned context budget policy..." — 对应 commits `d969404` + `05f2531`
2. "Add compaction contracts, fake compactor..." — 对应 commits `15b2815` + `6206699`
3. "Wire proactive pre-start compaction..." — 对应 commits `4e5498d` + `6b8101f` + `05f2531`

### 3.2 Validation 命令

PR body 列出的两段 pytest 命令覆盖了所有 Phase 10 新测试文件 + 核心受影响的已有测试。复现结果：81 + 180 passed、pyright 0 errors、git diff --check clean。

### 3.3 Review Artifacts 引用

PR body 引用 3 个 aggregate review artifacts，均存在于 PR diff 中：
- `docs/reviews/phase10-aggregate-deepreview-controller-adjudication-20260518.md` ✓
- `docs/reviews/phase10-aggregate-deepreview-mimo-20260518.md` ✓
- `docs/reviews/phase10-aggregate-deepreview-ds-20260518.md` ✓

### 3.4 PR Body 不足

PR body 未列出 `test_admission_queue.py`（23 passed），但该文件修改仅为机械适配必填 budget fields（第 12 个 `_options()` helper 更新），不影响 Phase 10 验证完整性。**INFO 级别，不阻塞。**

此外，AgentMiMo 已创建 PR review artifact（`docs/reviews/pr-61-review-phase10-mimo-20260518.md`），但 PR body 尚未引用。建议 PR 合入前将 MiMo PR review 也加入 review artifacts 列表。**INFO 级别，不阻塞。**

---

## 4. Aggregate Residual 阻塞评估

### 4.1 是否阻塞 Draft PR

| Residual | 级别 | 阻塞 | 理由 |
| --- | --- | --- | --- |
| Compactor 在 write transaction 内 | accepted | 否 | Fake 同步无延迟；真实 LLM compactor 接入时再设计 |
| Budget estimate 只覆盖 display_text | accepted | 否 | Conservative estimator 偏保守，不会低估导致 overrun |
| `promote_next_queued_run` 旧 helper 残留 | accepted | 否 | 无 production caller，README 已说明 |
| Composition helper 无 production caller | accepted | 否 | Public contract test 已验证 wiring |
| Production LLM compactor 未实现 | accepted | 否 | 未配置时 fail closed，不隐式用 fake |
| 多轮集成测试未串 verified fact 链路 | accepted | 否 | 分层测试覆盖（`test_memory_projection.py` + `test_run_input_builder.py`） |
| Conservative estimator 精度 | accepted | 否 | 偏保守不影响 correctness |
| DS AG1: DUPLICATE branch 无显式 stop_worker_stream | LOW | 否 | Scheduler 通过 `terminal_closeout or stop_worker_stream` 停止 |
| DS AG2: reactive REQUESTED 在 closeout CAS 前 | LOW | 否 | 同 SQLite write transaction + 前置 precondition 校验 |
| DS AG3: budget 压力 pinned patch 降级 opaque ref | LOW | 否 | 不影响 Host truth |

**PASS。** 所有 residual 均为 accepted 或 LOW，不阻塞 draft PR。

---

## 5. PR 前必须修复项检查

### 5.1 Correctness

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 主动 compact 在 Attempt 创建前触发 | PASS | `test_dispatch_scheduler.py:1918` 事件序 CONTEXT_COMPACTED < RUN_STARTED |
| 主动 compact failure → fail_unstarted（无 Attempt） | PASS | `test_dispatch_scheduler.py:1962` |
| 被动 overflow recovery 创建新 Attempt | PASS | `test_engine_ingest_mapping.py:296` |
| 被动 recovery failure 不进入 LOST | PASS | `test_engine_ingest_mapping.py:390` |
| 每 Run compact 限 1 次 | PASS | Proactive + reactive count limit |
| verified_facts 只来自 TOOL_RESULT_ACCEPTED | PASS | `test_memory_projection.py:1146` + 反面测试 |
| Compact artifact 确定性 digest | PASS | `compact_artifact.py:154-167` |
| Corrupted digest 拒绝 | PASS | `compact_artifact.py:156-159` HostDigestMismatchError |

### 5.2 State Machine

| 检查项 | 结论 |
| --- | --- |
| RunStatus.ACCEPTED 创建无 Attempt | PASS |
| Cancel ACCEPTED 无 Attempt → RUN_CANCELED | PASS |
| RUN_STARTED + ATTEMPT_STARTED 联动 | PASS |
| ATTEMPT_FAILED + RUN_RECOVERING 联动 | PASS |
| RECOVERY → new Attempt + RUN_STARTED(RECOVERY) | PASS |
| RECOVERING failure → RUN_FAILED（非 LOST） | PASS |
| 旧 Attempt 不被 resume/takeover | PASS |

### 5.3 Durability

| 检查项 | 结论 |
| --- | --- |
| Schema v9 包含 'accepted' status | PASS |
| Accepted Run CHECK 约束（queued/started/current_attempt 须为 NULL） | PASS |
| Per-session accepted 唯一索引 | PASS |
| CONTEXT_COMPACTED payload 校验 | PASS |
| Proactive compact count / REQUESTED 同事务 | PASS |
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
| 261 tests passed（Controller 180 + 81） | PASS |
| pyright 0 errors / 0 warnings / 0 informations | PASS |
| git diff --check clean | PASS |
| `dayu/host/README.md` 已同步必填参数说明 | PASS |
| `tests/README.md` 已同步新测试入口 | PASS |
| `implementation-control.md` gate 状态正确 | PASS |

---

## 6. 与 AgentMiMo Review 交叉验证

AgentMiMo PR review（`docs/reviews/pr-61-review-phase10-mimo-20260518.md`）也给出 PASS verdict。以下交叉检查确认 MiMo review 与本 review 的一致性：

| 维度 | MiMo | DS | 一致 |
| --- | --- | --- | --- |
| PR Diff Scope | PASS，90 files | PASS，86 files（count diff 为计数粒度差异） | ✓ |
| Control Doc Gate | PASS，ready-to-open-draft-PR | PASS | ✓ |
| PR Body 准确性 | PASS | PASS，PR body 未引用 MiMo review artifact（INFO） | ✓ |
| Residual 阻塞评估 | PASS，均不阻塞 | PASS | ✓ |
| Correctness 矩阵 | PASS，9 项 | PASS，8 项 | ✓ |
| State Machine | PASS，8 项 | PASS，7 项 | ✓ |
| Durability | PASS，6 项 | PASS，6 项 | ✓ |
| Layering | PASS，6 项 | PASS，6 项 | ✓ |

无 MiMo 遗漏或分歧。

---

## 7. Findings Summary

**无 blocking / high / medium findings。**

- PR diff scope 干净，86 文件全部落在 Phase 10 预期域内
- Control doc 已正确记录 `ready-to-open-draft-PR` gate 与全部 residual owner
- DS AG1/AG2/AG3 均已在 control doc 追踪区有明确 owner
- Aggregate accepted residual 全部不阻塞 draft PR
- PR body 准确表达交付与验证（引用 aggregate review artifacts 略微滞后，INFO）
- Correctness、state machine、durability、layering、tests/docs 全部通过
- MiMo review 与本 review 结论一致

---

## 8. Residual 风险矩阵

| 风险 | 可能性 | 影响 | 阻塞 PR |
| --- | --- | --- | --- |
| `promote_next_queued_run` 被误用绕过 governance | 低 | 高 | 否 |
| Compactor LLM 调用阻塞 SQLite writes | N/A | 高 | 否 |
| Budget estimate 不完整导致 compact 偏早 | 中 | 低 | 否 |
| RECOVERING 状态无 cancel 路径 | 低 | 中 | 否 |
| Engine overflow → recovery 竞态（极短时间窗） | 极低 | 中 | 否 |

---

## 9. 结论

PR #61 达到 Phase 10 Context Governance / Compaction 的全部交付：

1. Host-owned `ContextBudgetPolicy` 与 conservative estimator
2. Compactor typed port、fake compactor、quality check 与 deterministic artifact
3. `CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` canonical events
4. P9 memory projection 消费 accepted compact output（pinned state patch 三态语义）
5. Proactive pre-dispatch governance gate（Attempt 创建前 budget check / compact / fail closeout）
6. Reactive overflow recovery（Engine overflow → Host identity 校验 → RECOVERING → new Attempt）
7. RunInputBuilder durable compact artifact provider + memory snapshot provider
8. Production composition wiring（`context_window_size` / `reserved_output_tokens` 必填 typed input）
9. Multi-turn aggregate integration（proactive compact → memory projection → subsequent Engine request）

261 tests passed（180 + 81），pyright 0 errors。DS AG1/AG2/AG3（LOW）+ DS INFO 均有 owner 并已写入 control doc 追踪区，不阻塞 PR。

**PR #61 可从 draft 转为 ready for review / merge。**
