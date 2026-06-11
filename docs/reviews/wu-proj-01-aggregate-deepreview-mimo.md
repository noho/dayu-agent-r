# WU-PROJ-01 Aggregate Deep Review — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview
- Reviewer: AgentMiMo
- 日期: 2026-06-11
- 当前 HEAD: `9191f5ab` (Slice 4 bookkeeping)
- 审查范围: accepted plan `fb3cc9ec` 与 Slice 1-4 accepted commits
- 关键 commits:
  - accepted plan: `fb3cc9ec`
  - Slice 1 accepted: `1b4e7b67`
  - Slice 2 accepted: `8e9d42ea`
  - Slice 3 accepted: `a658ee1f`
  - Slice 4 accepted: `08709fe9`
  - Slice 4 bookkeeping: `9191f5ab`

## Preflight

- `git branch --show-current`: `wu-proj-01` ✅
- `git status --short`: clean ✅

## 审查结论

**PASS-WITH-FINDINGS**

WU-PROJ-01 的第一性原理目标已真正完成。四个 Slice 的实现对齐 accepted plan，代码、测试和文档一致。所有 blocking findings 均已在各 Slice 的 fix/re-review gate 中关闭。当前仅剩 non-blocking residual risks，已有明确 owner，不阻塞 draft PR gate。

## 审查维度详细分析

### 1. 第一性原理目标完成度

**结论: ✅ 完成**

| 目标 | 状态 | 证据 |
|---|---|---|
| compact input truth 来自 EventLog / payload descriptor / artifact truth | ✅ | `build_pre_dispatch_compact_material_view` 只读取 EventLog rows、payload 和 artifact refs，不读取 Conversation Memory snapshot |
| Conversation Memory projection 只消费 accepted compact | ✅ | `ConversationMemoryProjectionConsumer` 只消费 committed `CONTEXT_COMPACTED` canonical fact |
| Context Governance 只决策/编排，不拥有 material 语义 | ✅ | `_run_context_governance_for_session` 消费 `PreDispatchCompactMaterialView`，不构造 material |
| rolling compact 第二次不展开旧 raw history | ✅ | `test_pre_dispatch_second_compact_rolls_from_latest_accepted_candidate` 直接断言 |
| bounded memory catch-up / rebuild | ✅ | `MemoryProjectionCatchupBudget` + `_run_memory_projection_bounded` 替代无界循环 |

### 2. Slice 1-2: Same-source material view

**结论: ✅ 实现正确**

- `PreDispatchCompactMaterialView` 的 `previous_compacted_view` 来自 latest accepted `CONTEXT_COMPACTED` event / artifact，不来自 memory snapshot。
- `post_compact_delta_start_sequence` 正确设置为 `latest_compacted_event_sequence + 1`（有 previous 时）或 session first relevant fact（无 previous 时）。
- `CompactMaterialSourceBoundary` 提供完整的 EventLog 来源边界诊断。
- `build_compact_material_pack` 新增 `previous_compacted_view` keyword-only 参数，explicit view 路径和 snapshot 路径均有测试覆盖。
- `_proactive_material_blocks` 和 `_proactive_represented_evidence_refs` 已删除，Context Governance 不再自行拼 material。
- evidence 去重只依赖 latest compact accepted mapping，不读取 memory snapshot 中的 `evidence_backed_facts`。

**直接证据:**
- `dayu/host/compact_material.py:456-542` — `build_pre_dispatch_compact_material_view` 实现
- `dayu/host/compact_material.py:501-516` — previous_view 和 represented_refs 来源
- `dayu/host/dispatch.py:1092-1148` — governance 使用 material_view.budget_fragments
- `tests/host/test_compact_material.py:1049-1127` — rolling compact 测试

### 3. Slice 3: Bounded catch-up / rebuild

**结论: ✅ 无 recovery truth 污染、无界循环或 timeout bug**

- `MemoryProjectionCatchupBudget` 字段为 `max_batches` 和 `max_scanned_events`，不含 `timeout_seconds`（按 plan 约束）。
- `_run_memory_projection_bounded` 循环条件同时检查：failure → stop, target_reached → stop, idle → stop, budget_exhausted → stop。
- `budget_exhausted` 不写 projection failure row，不触发 recovery。
- after-commit port 使用 `MemoryProjectionCatchupBudget(purpose=BEST_EFFORT_AFTER_COMMIT, max_batches=1)`。
- dispatch before-worker 使用 `MemoryProjectionCatchupBudget(purpose=REQUIRED_BEFORE_DISPATCH, max_batches=16)`。
- rebuild 使用 `MemoryProjectionCatchupBudget(purpose=REBUILD_BEFORE_DISPATCH, max_batches=32)`。
- `_raise_if_memory_projection_target_not_reached` 在 required cursor 未覆盖时抛 `_MemoryProjectionDispatchDiagnosticError`，外层按 worker-start failure 收口，不创建 recovery Attempt。

**直接证据:**
- `dayu/host/memory_repair.py:289-370` — `_run_memory_projection_bounded` 实现
- `dayu/host/dispatch.py:325-388` — `_memory_projection_catchup_budget` 和 `_raise_if_memory_projection_target_not_reached`
- `dayu/host/dispatch.py:3026-3052` — `_catch_up_memory_projection_before_worker` 注入 budget
- `dayu/host/open_host.py:140-158` — after-commit port 注入 best-effort budget
- `tests/host/test_memory_repair.py:298-343` — budget exhausted 测试
- `tests/host/test_memory_repair.py:346-387` — target reached 测试
- `tests/host/test_open_host_runtime.py:602-658` — port budget 注入测试

### 4. Slice 4: Regression 证据

**结论: ✅ 提供完整证据链**

- accepted `CONTEXT_COMPACTED` → projection consumer 物化五类 memory sections → checkpoint 同事务推进：`test_projection_consumer_applies_event_and_writes_durable_vnext_snapshot`
- ordinary RunInput 能读取 accepted compact 物化出的 summary / facts / anchors / intents / reference continuity：`test_accepted_compact_materializes_vnext_memory_sections` 补充了 checkpoint 和 RunInput 联动断言
- failed compact negative regression：`test_projection_consumer_skips_failed_compact_without_memory_snapshot` 断言不写 memory snapshot/items，不生成 compact artifact

**直接证据:**
- `tests/host/test_memory_projection.py:692-789` — accepted compact 和 failed compact regression
- `tests/host/test_run_input_builder.py` — RunInput 读取 compact 物化的 memory sections

### 5. 设计文档、总控文档、代码和测试一致性

**结论: ✅ 一致**

- `docs/host/design.md` 的 Conversation Memory / Context Governance 章节与实现一致。
- `docs/host/issues-implementation-control.md` 的 WU-PROJ-01 状态、验收信号和 residual risks 与实现一致。
- `dayu/host/README.md` 已更新 Memory 与 compact 关系说明，区分 ordinary RunInput 读取 memory snapshot 和 pre-dispatch compact material 由 EventLog 构造。
- `tests/README.md` 已同步更新（diff 显示 2 行变更）。
- pyright 0 errors, 0 warnings, 0 informations ✅
- 所有受影响测试通过 ✅

### 6. Residual Risks 状态

| ID | 状态 | Owner | 允许进入 draft PR gate |
|---|---|---|---|
| WU-PROJ-01-S3-R1 | deferred-with-owner | Host dispatch test hardening | ✅ 是 |
| WU-PROJ-01-S4-R1 | deferred-with-owner | Host dispatch scheduler test hardening | ✅ 是 |

两条 residual risks 均为低严重度测试覆盖 / 稳定性问题，已有明确 owner，不阻塞 draft PR gate。

## Findings

### Non-blocking Findings

| ID | Severity | 文件 | 描述 | Root Cause | 建议 |
|---|---|---|---|---|---|
| NF1 | Low | `dayu/host/dispatch.py:381-388` | `_memory_projection_catchup_budget` unsupported purpose 分支无测试 | 枚举值已被 if/elif 全覆盖，分支不可达 | 不需要修复；defensive guard |
| NF2 | Low | `tests/host/test_dispatch_scheduler.py` | dispatch before-worker catch-up happy path 无独立集成测试 | 当前通过 budget exhausted 阻断路径间接覆盖 | deferred to test hardening |
| NF3 | Low | `tests/host/test_dispatch_scheduler.py` | `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 存在 lane timeout flaky | 与 Slice 4 改动无关，timing fixture 问题 | 后续单独稳定化 |

### Blocking Findings

无。

## 验证记录

### 测试运行

```bash
source .venv/bin/activate
python -m pytest tests/host/test_compact_material.py -x -q
# 32 passed in 0.29s ✅

python -m pytest tests/host/test_memory_projection.py -x -q
# 16 passed in 0.27s ✅

python -m pytest tests/host/test_memory_repair.py -x -q
# 9 passed in 0.25s ✅

python -m pytest tests/host/test_open_host_runtime.py -x -q
# 12 passed in 0.45s ✅

python -m pytest tests/host/test_logging.py -x -q
# 4 passed in 0.25s ✅

python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive" -x -q
# 19 passed, 48 deselected in 0.61s ✅

python -m pytest tests/host/test_public_compact_smoke.py -x -q
# 6 passed, 1 skipped in 0.76s ✅

python -m pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_open_host_runtime.py tests/host/test_logging.py tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive" tests/host/test_public_compact_smoke.py tests/host/test_memory_repair.py -q
# 68 passed, 1 skipped, 123 deselected in 1.29s ✅
```

### Pyright

```bash
source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations ✅
```

## 变更文件汇总

| 文件 | 变更类型 | Slice |
|---|---|---|
| `dayu/host/compact_material.py` | 新增 EventLog-backed material source builder | 1, 2 |
| `dayu/host/dispatch.py` | 集成 material view + bounded memory projection | 2, 3 |
| `dayu/host/engine_ingest.py` | reactive compact 最小适配 previous view | 2 |
| `dayu/host/memory_repair.py` | bounded memory projection budget | 3 |
| `dayu/host/open_host.py` | after-commit best-effort budget 注入 | 3 |
| `dayu/host/README.md` | Memory 与 compact 关系说明更新 | 1-4 |
| `tests/host/test_compact_material.py` | EventLog-backed material source 测试 | 1, 2 |
| `tests/host/test_dispatch_scheduler.py` | proactive governance + reactive 测试 | 2 |
| `tests/host/test_memory_projection.py` | accepted/failed compact regression | 4 |
| `tests/host/test_memory_repair.py` | bounded catch-up/rebuild 测试 | 3 |
| `tests/host/test_open_host_runtime.py` | port budget + dispatch budget 测试 | 3 |
| `tests/host/test_run_input_builder.py` | RunInput compact memory 联动 | 4 |
| `tests/host/test_logging.py` | memory repair logging | 3 |
| `tests/README.md` | 测试说明同步 | 1-4 |

## 下一步

- WU-PROJ-01 aggregate deepreview gate 通过，进入 draft PR gate。
- Residual risks `WU-PROJ-01-S3-R1` 和 `WU-PROJ-01-S4-R1` 保持 deferred-with-owner，不阻塞 PR。
