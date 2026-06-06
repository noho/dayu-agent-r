# WU-CM-01-F04 Plan Review — AgentDS

## Verdict

**pass-with-findings** — 3 blocking, 4 non-blocking。

计划总体方向正确：根因定位准确，scope 限制在测试 seam 内，不改生产 guard/schema/contract，slice 切分合理，且已有 `test_compaction_operation.py` 和 `test_engine_ingest_mapping.py` 的 prepared manifest compactor 模式可直接参考。

但 Slice 4 迁移扫描范围定义不精确、Decision 8 对 `_StaleMutatingCompactor` 过度迁移、`_TransactionReadableCompactor` 迁移未被任何 slice 显式分配——这三项须在 implementation gate 前或 implementation 早期澄清，否则可能导致遗漏或无效迁移。

---

## Evidence Verified

### Production fail-closed guard（已确认）

| 位置 | 证据 |
|---|---|
| `dayu/host/dispatch.py:3734-3759` | `_required_compactor_manifest_ref()` / `_required_compactor_manifest_digest()` — accepted result 缺 manifest ref/digest 时抛 `RuntimeError` |
| `dayu/host/dispatch.py:1264-1269` | proactive accepted `CONTEXT_COMPACTED` 写入前必须通过上述 guard |
| `dayu/host/dispatch.py:1648-1671` | `build_context_compacted_payload` 接收 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` |
| `dayu/host/dispatch.py:2008-2018` | rejected `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 写入 `proposal_manifest_ref` / `proposal_manifest_digest` |

### Manifest 产出路径（已确认）

| 位置 | 证据 |
|---|---|
| `dayu/host/compaction_operation.py:749-776` | 只有 `isinstance(compactor, CompactorProposalPreparedCompactor)` 时才会 prepare → record manifest → run；manifest ref 绑定到 `_CompactorProposalAttempt` |
| `dayu/host/compaction_operation.py:777-784` | legacy `compact()` 路径 `proposal_manifest_reference=None` |

### 当前测试 seam 缺陷（已确认）

| 位置 | 缺陷 |
|---|---|
| `tests/host/test_dispatch_scheduler.py:536-559` | `_RequestCapturingCompactor` 只 override `compact()`，不走 prepared manifest 路径 |
| `tests/host/test_dispatch_scheduler.py:498-533` | `_QualityRejectOnceCompactor` 只 override `compact()` |
| `tests/host/test_dispatch_scheduler.py:403-430` | `_TransactionReadableCompactor` 只 override `compact()` |
| `tests/host/test_dispatch_scheduler.py:433-476` | `_StaleMutatingCompactor` 只 override `compact()` |
| `tests/host/test_dispatch_scheduler.py:479-495` | `_RaisingCompactor` 只 override `compact()` |
| `tests/host/test_dispatch_scheduler.py:3630,3773` | direct `FakeContextCompactor()` 注入，无 manifest 能力 |

### 已有 prepared manifest seam 参考（已确认）

| 位置 | 参考价值 |
|---|---|
| `tests/host/test_compaction_operation.py:490-568` | `_PreparedManifestCompactor` — 完整 `CompactorProposalPreparedCompactor` 实现，含 `fail_run` 参数、`_proposal_agent_request` helper |
| `tests/host/test_engine_ingest_mapping.py:273-353` | `_PreparedManifestReactiveCompactor` — reactive path 的 prepared manifest seam |
| `tests/host/test_engine_ingest_mapping.py:631-656,784-810` | reactive accepted/rejected event 中直接断言 manifest ref / digest |

### 设计真源对齐（已确认）

| 位置 | 对齐要点 |
|---|---|
| `docs/host/design.md:3225-3238` | proactive trigger 路径：`CONTEXT_COMPACTION_REQUESTED` → bounded compaction operation → `CONTEXT_COMPACTED` or `CONTEXT_COMPACTION_FAILED` → rebuild request → dispatch |
| `docs/host/design.md:3263-3266` | compact event 须记录 durable 信息；manifest ref/digest 是 WU-CM-01 后用于追溯 proposal runner call 的 durable 引用 |
| `docs/engine/design.md:414-423` | Engine 不做 proactive threshold compaction；Engine 只在 provider overflow 时发出 reactive compaction request |
| `docs/host/issues-implementation-control.md:540-571` | WU-CM-01-F04 明确定义为 test seam closeout，不放宽 production guard |

---

## Findings

### Finding 1 (BLOCKING) — Slice 4 迁移扫描范围定义不精确

- **Severity**: blocking
- **Evidence**: plan Slice 4 描述 "扫描 `tests/host/test_dispatch_scheduler.py` 内所有 `context_compactor=FakeContextCompactor()` proactive compaction usages"
- **Analysis**: 该文本搜索无法匹配以下需要迁移的 compactor：
  - `_TransactionReadableCompactor(store.transaction_runner)` — line 3901
  - `_RaisingCompactor()` — line 4035
  - `_QualityRejectOnceCompactor()` — line 3972
  - `_RequestCapturingCompactor()` — 若被 proactive tests 使用
  - 任何通过变量间接注入的 compactor

  这些都不是 `FakeContextCompactor()` 字面量。Slice 4 若机械执行该文本搜索，会遗漏 `test_proactive_compaction_calls_llm_outside_write_transaction`（使用 `_TransactionReadableCompactor`，期望写 `CONTEXT_COMPACTED`）。

- **影响**: 当前 7 个 manifest-ref failure 中可能有部分不在 Slice 2-3 范围、且被 Slice 4 遗漏。
- **建议裁决**: **accepted** — Slice 4 描述改为基于语义扫描：枚举所有 proactive path 中注入 compactor 的 test，按 "是否期望写 `CONTEXT_COMPACTED`" 分类迁移，而非文本搜索 `FakeContextCompactor()`。

### Finding 2 (BLOCKING) — Decision 8 对 `_StaleMutatingCompactor` 过度迁移

- **Severity**: blocking
- **Evidence**: 
  - `tests/host/test_dispatch_scheduler.py:3919-3963` `test_compaction_stale_result_does_not_write_compacted_event` 使用 `_StaleMutatingCompactor`
  - 该测试期望 `CONTEXT_COMPACTED` = 0，断言 `CONTEXT_COMPACTION_FAILED` 且 `failure_reason == "stale_compaction_result"`
  - `dayu/host/dispatch.py:1264-1269` 的 manifest guard 只在写 `CONTEXT_COMPACTED` 前触发
- **Analysis**: `_StaleMutatingCompactor` 的 `compact()` 返回合法 candidate，但 Host staleness check 在 manifest guard 之前捕获，直接写 `CONTEXT_COMPACTION_FAILED`，不经过 `_required_compactor_manifest_ref`。该测试在当前 production guard 下不会失败，**不需要迁移**。迁移它反而引入风险：prepared manifest 路径会先 record manifest（产生 `RUNNER_CALL_INPUT_ASSEMBLED` event），改变 test store 的 event count，可能干扰 `CONTEXT_COMPACTION_FAILED` payload 断言。
- **影响**: 若强行迁移 `_StaleMutatingCompactor`，可能引入无关 event 干扰原有断言；若不迁移（正确行为），plan 中 Decision 8 的描述需要修正。
- **建议裁决**: **accepted** — Decision 8 改为仅迁移 `_TransactionReadableCompactor`（其测试期望 `CONTEXT_COMPACTED` = 1，确实会触发 manifest guard）；`_StaleMutatingCompactor` 明确列为不迁移项并说明理由。

### Finding 3 (BLOCKING) — `_TransactionReadableCompactor` 迁移未在任何 slice 显式分配

- **Severity**: blocking
- **Evidence**: 
  - Plan Decision 8 承认 `_TransactionReadableCompactor` 需要迁移
  - `tests/host/test_dispatch_scheduler.py:3890-3916` `test_proactive_compaction_calls_llm_outside_write_transaction` 使用 `_TransactionReadableCompactor`，期望 `CONTEXT_COMPACTED` = 1
  - Slice 2 分配 "将直接注入 `FakeContextCompactor()` 且期望写 `CONTEXT_COMPACTED` 的 proactive tests" — `_TransactionReadableCompactor` 不是 `FakeContextCompactor()` 直接注入
  - Slice 4 分配 "扫描 `context_compactor=FakeContextCompactor()` usages" — 同上
- **Analysis**: `_TransactionReadableCompactor` 是一个有额外构造参数（`transaction_runner`）的 `FakeContextCompactor` 子类，其测试在 `-k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"` 范围内（名称含 "proactive"），会因 manifest guard 失败。但没有任何 slice 显式覆盖它。
- **影响**: implementation 可能在 Slice 2-4 完成后仍有 `test_proactive_compaction_calls_llm_outside_write_transaction` 失败。
- **建议裁决**: **accepted** — 在 Slice 1 的 helper 设计中预留 `transaction_runner` 注入点，或 Slice 2 显式包含 `_TransactionReadableCompactor` 迁移；迁移后保持 "compactor 调用期可开启独立读事务" 的原有断言语义。

### Finding 4 (NON-BLOCKING) — `_RequestCapturingCompactor` 使用范围未明确

- **Severity**: non-blocking
- **Evidence**: `tests/host/test_dispatch_scheduler.py:536-559` 定义了 `_RequestCapturingCompactor`，但 plan 未列出哪些 proactive tests 使用它。
- **Analysis**: `_RequestCapturingCompactor` 继承 `FakeContextCompactor`，只 override `compact()`。若它在任何 proactive accepted compact test 中使用，同样会因 manifest guard 失败。Plan Decision 6 说要迁移它，但未分配到具体 slice。
- **建议裁决**: **deferred** — implementation gate 第一步先 grep `_RequestCapturingCompactor` 的所有使用点，若在 proactive accepted path 中，归入 Slice 2；若仅在未被 `-k` 选中的 test 中使用，可延后处理。

### Finding 5 (NON-BLOCKING) — `RUNNER_CALL_INPUT_ASSEMBLED` event count 断言风险

- **Severity**: non-blocking
- **Evidence**: Plan Slice 2 建议 "需要时断言 `RUNNER_CALL_INPUT_ASSEMBLED` event count 与 compaction accepted attempt 数一致"；Slice 3 建议对 `max_compaction_attempts_per_operation=2` 断言 count 为 2。
- **Analysis**: `RUNNER_CALL_INPUT_ASSEMBLED` 是 `DurableCompactorProposalManifestRecorder` 写入的内部 event。该 event 是否出现在 test 的 EventLog store 中取决于 `_open_scheduler` 配置的 `compact_artifact_root` 与 recorder 路径。需确认该 event type 常量在测试中可引用，且 count 不会被同一 store 的其它 test 污染。
- **建议裁决**: **deferred** — implementation 时先用单个 focused test 验证 `RUNNER_CALL_INPUT_ASSEMBLED` event 确实出现在 EventLog 中，再决定是否在所有 test 中断言 count。

### Finding 6 (NON-BLOCKING) — `_COMPACTOR_TEST_DIGEST` 常量引入不必要的抽象

- **Severity**: non-blocking
- **Evidence**: Plan Slice 1 建议 `_COMPACTOR_TEST_DIGEST = sha256_digest_json({"test": "proactive_compactor"})`
- **Analysis**: 参考 `test_compaction_operation.py:490-568` 的 `_PreparedManifestCompactor`，现有模式直接在 `CompactorProposalRunInput` 构造中使用 `_DIGEST` 常量（模块级已有）。新增独立 `_COMPACTOR_TEST_DIGEST` 常量未增加语义区分度——它和已有的 `_DIGEST` 用途相同（占位 digest）。不建议新增常量增加认知负担。
- **建议裁决**: **rejected** — 直接使用测试文件已有 digest 常量或内联字面量，避免为单点使用引入新模块级常量。

### Finding 7 (NON-BLOCKING) — Plan 未覆盖 `_RaisingCompactor` 被非 `-k` 范围内 test 复用的风险

- **Severity**: non-blocking
- **Evidence**: `_RaisingCompactor` 定义在 `tests/host/test_dispatch_scheduler.py:479`，plan Slice 3 将其改为 prepared proposal failure。该 compactor 可能在文件内其他非 proactive test 中也被使用。
- **Analysis**: 若 `_RaisingCompactor` 仅被 `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` 使用，迁移安全。若被其他 test 共享，迁移可能影响那些 test 的行为预期（例如预期 `compact()` 直接抛错 vs `prepare` 成功后再抛错）。
- **建议裁决**: **deferred** — implementation 前 grep `_RaisingCompactor` 所有使用点，确认迁移范围。若仅一处使用，直接内联迁移后的 prepared helper 到该 test，删除 `_RaisingCompactor` 类。

---

## Blocking Open Questions

无。上述 3 个 blocking findings 已给出具体裁决建议，无需额外信息即可在 implementation gate 前或早期解决。

---

## Plan Readiness Assessment

| 维度 | 评估 |
|---|---|
| 目标成立性 | **通过** — 根因是测试 seam 未对齐 WU-CM-01 升级后的 manifest contract，不是生产 guard 过严或 provider migration 缺陷 |
| Scope 正确性 | **通过** — 严格限定在 `tests/host/test_dispatch_scheduler.py`，不改生产代码/schema/contract |
| Slice 切分合理性 | **通过** — 4 个 slice 从基础 helper → accepted tests → rejected tests → broad sweep，依赖关系正确 |
| 架构边界 | **通过** — 不触碰 Engine、不修改 `FakeContextCompactor`、不新增 compatibility wrapper |
| 测试策略 | **条件通过** — accepted/rejected manifest ref/digest 断言覆盖完整；Slice 4 扫描范围需修正（见 Finding 1） |
| Fail-closed guard | **通过** — 明确不改 `_required_compactor_manifest_ref` / `_required_compactor_manifest_digest` |
| 设计真源对齐 | **通过** — 与 `docs/host/design.md` 和 `docs/engine/design.md` 一致 |

---

## Over-design / Under-design Check

### Over-design

- `_COMPACTOR_TEST_DIGEST` 新常量 → **over-design**（Finding 6）
- Decision 8 对 `_StaleMutatingCompactor` 的迁移建议 → **over-design**（Finding 2）

### Under-design

- Slice 4 扫描范围定义不精确，缺少基于语义的迁移清单 → **under-design**（Finding 1）
- `_TransactionReadableCompactor` 迁移未被任何 slice 显式分配 → **under-design**（Finding 3）
- `_RequestCapturingCompactor` 使用范围未提前枚举 → **mild under-design**（Finding 4）

### 正确拒绝的过度设计

- 不抽取 shared production abstraction ✓
- 不修改 `FakeContextCompactor` 使其自动具备 manifest ✓
- 不新增 compatibility facade ✓
- 不改 schema/EventLog builder/dispatch guard ✓

---

## Residual Risks / Uncovered Areas

1. **`_TransactionReadableCompactor` 迁移复杂度**: 该 compactor 在 `compact()` 中通过 `self._transaction_runner.run_read()` 开启独立读事务验证 Run 存在性。迁移到 prepared manifest 路径时，`prepare_compactor_proposal_run_input` 和 `run_prepared_compactor_proposal` 都需要此事务能力。Slab 需要在 prepared helper 中保留 `transaction_runner` 注入。

2. **`_QualityRejectOnceCompactor` 迁移后诊断语义**: 当前 quality rejection 通过 `replace(candidate, diagnostics=...)` 在 `compact()` 返回后修改 candidate。迁移到 prepared path 后，quality check 逻辑需在 `run_prepared_compactor_proposal` 中完成，且 counter 状态需正确管理——两次 `prepare` + 两次 `run` 的调用顺序必须保证第一次 run 返回带 diagnostic 的 candidate、第二次 run 返回 clean candidate。

3. **`_RequestCapturingCompactor` 捕获时机**: Plan Decision 6 说 "捕获发生在 prepare 阶段"。但原 `_RequestCapturingCompactor.compact()` 捕获的是 `request` 参数。迁移后若在 `prepare_compactor_proposal_run_input` 中捕获，语义一致；若需要同时捕获 prepared input，需明确声明。

4. **pyright 协议签名对齐**: `CompactorProposalPreparedCompactor` 是 `@runtime_checkable` Protocol。新增 helper 的方法签名（参数名、类型、返回类型）必须严格匹配协议定义，否则 `isinstance(compactor, CompactorProposalPreparedCompactor)` 在 `compaction_operation.py:749` 将返回 `False`，走 legacy 路径。

5. **wake queue promotion timeout**: 当前 `test_wake_queue_promotion_uses_tracked_async_promotion_task` 因 promotion task 记录 manifest exception 后 timeout。修复 manifest seam 后若仍有 timeout，需检查 promotion task 是否记录了新的异常——不能自动归因为"已修复"。

---

## Validation Performed

- 读取 `dayu/host/dispatch.py` production guard（lines 1255-1275, 1640-1676, 1975-2023, 3725-3759）→ 确认 fail-closed 行为
- 读取 `dayu/host/compaction_operation.py` manifest 路径（lines 749-784）→ 确认只有 `CompactorProposalPreparedCompactor` 产出 manifest
- 读取 `CompactorProposalRunInput` dataclass 定义（lines 85-112）→ 确认所有必填字段
- 读取 `tests/host/test_dispatch_scheduler.py` 所有受影响的 compactor 类定义和使用点 → 确认迁移缺口
- 读取 `tests/host/test_compaction_operation.py` `_PreparedManifestCompactor`（lines 490-568）→ 确认参考实现模式
- 读取 `tests/host/test_engine_ingest_mapping.py` `_PreparedManifestReactiveCompactor`（lines 273-353）→ 确认 reactive 参考
- 读取 `docs/host/design.md` proactive compaction 设计（lines 3220-3279）→ 确认设计真源对齐
- 读取 `docs/engine/design.md` context compaction 边界（lines 411-427）→ 确认 Engine 不参与 proactive compaction
- 读取 `docs/host/issues-implementation-control.md` WU-CM-01-F04 定义（lines 540-571）→ 确认总控范围
- 读取 plan artifact 全文 → 完成逐项审查
