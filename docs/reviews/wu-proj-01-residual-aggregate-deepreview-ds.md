# WU-PROJ-01 Residual Aggregate Deepreview — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview
- Reviewer: AgentDS
- Date: 2026-06-11
- Branch: `wu-proj-01`
- Base: `d0dfd7d9`
- Commits in scope: `448b70ba` (CAP-R1), `3baeef53` (S3/S4)
- Uncommitted: `docs/host/issues-implementation-control.md` gate 状态更新
- 输出 artifact: `docs/reviews/wu-proj-01-residual-aggregate-deepreview-ds.md`

## 审查输入

- 设计真源: `docs/host/design.md`, `docs/engine/design.md`
- 总控文档: `docs/host/issues-implementation-control.md`
- 必读 artifacts:
  - `docs/reviews/wu-proj-01-cap-r1-rereview-controller-adjudication.md`
  - `docs/reviews/wu-proj-01-s3-s4-code-review-controller-adjudication.md`
  - `docs/reviews/wu-proj-01-s3-s4-residual-controller-adjudication.md`
- Controller 复验: CAP-R1 focused 173 passed; S3/S4 test_dispatch_scheduler 68 passed; pyright 0; diff-check passed

## 审查结论: PASS

0 条 blocking finding。2 条非阻塞 finding（1 条 maintainability，1 条 informational）。无 active residual risk 无 owner。

---

## 审查范围确认

| 范围 | Commit | 内容 |
|---|---|---|
| CAP-R1 | `448b70ba` | 去掉 compact material / compaction evidence query 固定截断、delta/evidence caps、required/rebuild projection correctness batch budgets；保留 opportunistic one-batch 非 correctness 行为 |
| S3/S4 | `3baeef53` | dispatch checkpoint-covered happy path 测试；reactive fallback flaky lane timeout fixture hardening |
| 控制文档 | 未提交 | WU-PROJ-01 gate 状态从 `implementation` 更新为 `aggregate-deepreview` |

---

## Preflight

- 分支: `wu-proj-01` ✅
- `git diff d0dfd7d9..HEAD --stat`: 23 files, +1949/-116 ✅
- `git diff --stat`: 1 file, +1/-1 (控制文档 gate 状态更新) ✅
- Controller 复验: 173 focused tests passed, 68 S3/S4 tests passed, pyright 0, diff-check passed ✅

---

## 审查重点 1: CAP-R1 — compact material source builder caps

### 判定: ✅ PASS

#### 已删除常量清单（8 个 correctness caps）

| 常量 | 原位置 | 验证 |
|---|---|---|
| `_READABLE_QUERY_TEXT_MAX_CHARS = 1200` | `compact_material.py` | `rg` 确认 0 hits |
| `_READABLE_QUERY_TRUNCATED_MARKER` | `compact_material.py` | `rg` 确认 0 hits |
| `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS = 256` | `compact_material.py` | `rg` 确认 0 hits |
| `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS = 8` | `compact_material.py` | `rg` 确认 0 hits |
| `_READABLE_QUERY_TEXT_MAX_CHARS = 1200` | `compaction_evidence.py` | `rg` 确认 0 hits |
| `_READABLE_QUERY_TRUNCATED_MARKER` | `compaction_evidence.py` | `rg` 确认 0 hits |
| `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES = 16` | `dispatch.py` | `rg` 确认 0 hits |
| `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES = 32` | `dispatch.py` | `rg` 确认 0 hits |
| `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES = 1` | `dispatch.py` | `rg` 确认 0 hits |
| `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES = 1` | `open_host.py` | `rg` 确认 0 hits |

#### Source builder delta/evidence 完整性

直接证据 — `compact_material.py`:

- `build_pre_dispatch_compact_material_view` (line 452-548): 签名不再接受 `max_delta_events` / `max_evidence_blocks` 参数。docstring 明确 "不在 source builder 阶段用固定条数裁剪 post-compact delta 或 accepted evidence blocks"。
- `_post_compact_delta_rows` (line 1870-1928): SQL 不再包含 `LIMIT ?`，完整读取 `start_sequence` 到 `end_sequence` 的所有 canonical fact rows。不再有 `if len(rows) > limit: raise HostDurableError(...)` fail-closed 分支。
- `_pre_dispatch_delta_material_blocks` (line 1931-1965): 不再接受 `max_evidence_blocks` 参数。内部 `evidence_count` 累加器和 fail-closed 分支已删除。
- 调用点 (line 512-523): 只传 session / start / end 和 represented refs，不传任何 cap。

#### Query text truncation 移除

直接证据:

- `compact_material.py` `_bounded_query_text` → `_normalized_query_text` (line 2192-2200): 函数体从 `normalize → if len > 1200 → truncate + append marker` 改为 `return normalized_material_text(text)`，完整保留非空内容。
- `compaction_evidence.py` `_bounded_query_text` → `_normalized_query_text` (line 352-360): 同上，委托给共享的 `normalized_material_text`。
- 两个文件的 `_normalized_query_text` 均为独立私有 helper，无 alias / wrapper / re-export。
- `rg` 全仓库搜索 `_bounded_query_text` 确认 0 hits。

#### 新测试覆盖

| 测试 | 文件 | 覆盖的旧 cap | 验证内容 |
|---|---|---|---|
| `test_pre_dispatch_reads_delta_rows_beyond_old_cap` | `test_compact_material.py:887` | delta 256 | 260 条 user input → 260 blocks |
| `test_pre_dispatch_keeps_evidence_blocks_beyond_old_cap` | `test_compact_material.py:952` | evidence 8 | 10 evidence → 10 blocks |
| `test_pre_dispatch_evidence_query_text_is_not_truncated` | `test_compact_material.py:1041` | query 1200 | len > 1200, 完整保留 |
| `test_evidence_input_semantic_query_text_is_not_truncated` | `test_compaction_operation.py` | query 1200 | len > 1200, 不追加 truncated marker |
| `test_required_catch_up_without_budget_crosses_old_batch_cap_to_target` | `test_memory_repair.py:390` | batch 16 | 17 批追到 target |
| `test_rebuild_without_budget_crosses_old_batch_cap_to_target` | `test_memory_repair.py:482` | batch 32 | 33 批追到 target |
| `test_open_host_dispatch_memory_catchup_reaches_required_cursor` | `test_open_host_runtime.py:661` | 旧 monkeypatch | worker SUCCEEDED, accepted |

所有旧 cap 边界均有超越测试，直接断言旧 cap 被突破后仍正确工作。

---

## 审查重点 2: CAP-R1 — dispatch / memory_repair / open_host correctness budgets

### 判定: ✅ PASS

#### dispatch required catch-up

直接证据 — `dispatch.py` `_catch_up_memory_projection_before_worker` (line 3011-3032):

```python
result = catch_up_conversation_memory_projection(
    ...
    max_event_sequence=required_event_sequence,
    budget=None,
)
```

终止条件只由 `target_reached`、`idle` 或 `failure` 决定。`

#### dispatch rebuild

直接证据 — `dispatch.py` lag rebuild 路径 (line 2906-2912):

```python
rebuild_result = rebuild_conversation_memory_projection(
    ...
    max_event_sequence=exc.repair_request.required_event_sequence,
    budget=None,
)
```

#### memory_repair.py budget=None 支持

直接证据 (`memory_repair.py`):

- `_bounded_batch_limit(batch_size, None, ...)` → 返回 `batch_size` (line 497-498)
- `_budget_scanned_events_exhausted(None, ...)` → 返回 `False` (line 514)
- `_budget_max_batches(None)` → 返回 `None` (line 550-552)
- `_budget_max_scanned_events(None)` → 返回 `None` (line 564-566)
- 循环守卫 `budget is not None and batches_used >= budget.max_batches` (line 330) — `budget=None` 时不触发

所有 budget-aware 守卫均正确处理 `None`。

#### opportunistic 命名与语义

| 旧名称 | 新名称 | 位置 |
|---|---|---|
| `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES` | `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT` | `open_host.py:127` |
| `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES` | `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT` | `dispatch.py:244` |

两个新常量 docstring 明确标注非 correctness 语义:
- `dispatch.py:244-245`: "compact accepted 后的非 correctness opportunistic projection catch-up 批次数"
- `open_host.py:127-128`: "open_host after-commit 非 correctness memory projection catch-up 批次数"

`_opportunistic_memory_projection_catchup_budget` (dispatch.py:324-344): docstring 明确 "worker accept 前的 required catch-up / rebuild 不共享该预算，仍追到 required cursor、idle 或 failure"。函数不再接受 `purpose` 参数路由。

`_after_commit_memory_projection_budget` (open_host.py:143-161): docstring 明确 "不参与 dispatch 前 required / rebuild correctness catch-up"。

#### 旧 `_memory_projection_catchup_budget` 函数

已完全重命名为 `_opportunistic_memory_projection_catchup_budget`，不再接受 `purpose` 参数。`rg` 搜索确认旧函数名 0 hits。

---

## 审查重点 3: S3-R1 — dispatch checkpoint-covered happy path 测试

### 判定: ✅ PASS

#### 测试结构与语义

`test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input` (test_dispatch_scheduler.py:1987-2099):

1. **prewarm 阶段**: 使用 `catch_up_conversation_memory_projection(..., budget=None)` 将 memory projection 追到 `required_event_sequence = attempt.started_event_sequence - 1`，模拟 checkpoint 已覆盖 required cursor。
2. **验证 prewarm**: `prewarmed.target_reached is True`，`prewarmed.finished_cursor == required_event_sequence`，`checkpoint_before_dispatch == required_event_sequence` — 确认 checkpoint 与 required cursor 一致。
3. **dispatch 阶段**: 通过 monkeypatch `catch_up_conversation_memory_projection` 录制 dispatch 内部调用。`lane_default_timeout_seconds=1.0` 避免无关 lane acquire 风险。
4. **断言**: 
   - `len(observed_catchups) == 1` — dispatch 只做了一次 catch-up 调用
   - `dispatch_catchup.events_scanned == 0` — checkpoint 已覆盖，不需要扫描新事件
   - `dispatch_catchup.target_reached is True` — 确认 required cursor 已覆盖
   - `factory.accepted_snapshots == 1` — worker 被接受
   - `checkpoint_after_dispatch == checkpoint_before_dispatch` — checkpoint 未变化
   - `run.status == RunStatus.RUNNING` — run 正常进行
   - `_event_count("RUN_FAILED") == 0` — 无失败事件
   - `_event_count("RUN_RECOVERING") == 0` — 无恢复事件
   - `_attempt_count_for_run == 1` — 只有一个 attempt（无 lag rebuild 触发额外 attempt）
   - `factory.accepted_requests[0].disable_tools is True` — 正确构造了 ordinary RunInput
   - `accepted_contents[-1] == "dispatch prompt"` — prompt 正确传递

#### 与现有测试的边界

该测试与现有测试的边界清晰:
- `test_dispatch_lag_repair_rebuild_not_reached_fails_closed`: 覆盖 lag 触发 rebuild 但未达 target 的 fail-closed 路径
- `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering`: 覆盖 pre-dispatch lag failure 的收口
- `test_open_host_dispatch_memory_catchup_reaches_required_cursor`: 覆盖 open_host after-commit skip 后 dispatch required catch-up 追到 target
- S3-R1 覆盖的是 checkpoint 已覆盖 required cursor 的 dispatch-level happy path — 不重复扫描、不进入 RUN_FAILED / RUN_RECOVERING、正常构造 ordinary RunInput

#### _read_memory_checkpoint_sequence helper

存在于 `test_dispatch_scheduler.py:6130`，有完整类型标注和中文 docstring。命名直接表达"读取 memory checkpoint sequence"的测试意图，与测试 helper 风格一致。

---

## 审查重点 4: S4-R1 — reactive fallback flaky lane timeout fixture hardening

### 判定: ✅ PASS

#### 变更内容

`test_reactive_compact_failure_fallback_dispatch_uses_failed_view` (test_dispatch_scheduler.py:4988-5042):

唯一的变更: `_open_scheduler(...)` 调用增加了 `lane_default_timeout_seconds=1.0` 参数。其余所有断言保持不变。

#### 变更理由

直接证据 — `_open_scheduler` helper 默认 `lane_default_timeout_seconds=0.01`（即 10ms）。该测试不验证 lane timeout 语义，将 reactive compact failure fallback 语义测试暴露给 10ms lane acquire 窗口的无关 timing 风险。历史 review 记录该测试曾因 lane timeout 偶发失败。

#### 断言完整性确认

所有原有断言完整保留:
- `len(factory.accepted_snapshots) == 2` — 两个 attempt
- 第二个 attempt 的 `attempt_id != seeded.attempt_id` — 新 attempt
- `_attempt_count_for_run == 2` — 总共 2 个 attempt
- `_event_count(CONTEXT_COMPACTED) == 0` — 无 compact artifact
- `_event_count("RUN_LOST") == 0` — 无 worker lost
- `CONTEXT_COMPACTION_FAILED` payload: `fallback_action == "dispatch"`，`fallback_policy_decision == "deterministic_recent_window"`
- 第二个 attempt messages 不包含 "Accepted compact artifact is available for this run."
- 第二个 attempt messages 以 "dispatch prompt" 结尾

断言强度未降低。

#### 与 S3 的 lane_default_timeout_seconds 共用

S3 与 S4 都是 dispatch scheduler 集成测试，都使用 `lane_default_timeout_seconds=1.0` 作为测试专用 lane acquire 稳定窗口。两者都不验证 lane timeout 语义，使用相同值的理由一致且合理。

---

## 审查重点 5: 控制文档 gate 状态更新

### 判定: ✅ PASS

#### 未提交 diff

```diff
-| WU-PROJ-01 | implementation | ... | 用户裁决 ... 等待 residual risk implementation gate |
+| WU-PROJ-01 | aggregate-deepreview | ... | Residual implementation accepted commits: CAP-R1 `448b70ba`, S3/S4 `3baeef53`. Active residual risk table has no WU-PROJ-01 entries. Controller复验：CAP-R1 focused tests -> 173 passed; S3/S4 `python -m pytest tests/host/test_dispatch_scheduler.py` -> 68 passed; `pyright` -> 0 errors; `git diff --check` passed. Next gate: aggregate deepreview before PR update push. |
```

#### 变更验证

1. **状态变更**: `implementation` → `aggregate-deepreview` — 正确反映当前 gate。
2. **当前定位**: 明确记录了两个 accepted commits 的 hash、active residual risk 表状态、Controller 复验结果和 next gate。
3. **CAP-R1/S3-R1/S4-R1 residual risks**: 已从 active residual risk 表移除（通过 controller adjudication `wu-proj-01-cap-r1-rereview-controller-adjudication.md` 和 `wu-proj-01-s3-s4-code-review-controller-adjudication.md`）。
4. **active residual risk 表**: 当前无 WU-PROJ-01 条目 — 符合事实，三个 residual risks 已全部关闭。

---

## 审查重点 6: 综合检查

### correctness: ✅ PASS

- compact material source builder 不再截断 canonical EventLog delta
- dispatch required catch-up / rebuild 不再被固定 batch/scanned event budget 截断
- opportunistic one-batch 行为明确标注为非 correctness
- S3 测试正确覆盖 checkpoint-covered happy path，断言 worker accepted 且不进入失败/恢复
- S4 测试断言完整保留，仅增加 lane timeout 稳定参数

### design alignment: ✅ PASS

- 变更与 `docs/host/design.md` 的 compact material / memory projection / context governance 边界一致
- source builder 只读取 EventLog durable truth，不做 selection/policy/budget 决策
- projection catch-up correctness 路径追到 required cursor、idle 或 failure
- 未触及 `docs/engine/design.md` Engine 边界

### overdesign/hardcoding regression: ✅ PASS

- 已删除 8 个旧 correctness cap 常量
- 保留的 `_OPPORTUNISTIC_*` 常量语义收敛且标注为非 correctness
- 无新增 magic number、magic string 或硬编码 correctness 约束
- 无兼容性 re-export、wrapper、facade 或胶水 seam

### LLM-facing material semantics: ✅ PASS

- `_normalized_query_text` 完整保留 semantic query / arguments query，不截断
- query text 不包含 `event-`、`payload-`、`digest`、`cursor`、internal ref 等治理标识
- `limited_signal_query_text` 原因/说明使用业务中性文本，不含 Host 内部 refs
- `normalized_material_text` 被 `compact_material.py` 和 `compaction_evidence.py` 共享复用，规范化语义同源

### projection catch-up correctness: ✅ PASS

- `budget=None` 时终止条件只由 `target_reached`、`idle` 或 `failure` 决定
- `_bounded_batch_limit` 在 `budget=None` 时直接返回 `batch_size`，不触发 `limit < _MIN_REPAIR_BATCH_SIZE`
- `_budget_scanned_events_exhausted(None, ...)` 返回 `False`
- 循环守卫 `budget is not None and batches_used >= budget.max_batches` 在 `budget=None` 时不触发
- `max_event_sequence` 由 `attempt.started_event_sequence - 1` 设定，自然上界

### test robustness: ✅ PASS

- S3 测试: 通过 prewarm + monkeypatch 录制 dispatch 内部调用，对 catch-up 行为做可观察断言
- S4 测试: `lane_default_timeout_seconds=1.0` 消除无关 timing 风险
- 所有新测试直接断言旧 cap 被突破后的正确行为
- Controller 复验: 68 tests passed, 无 flaky

### README/doc status: ✅ PASS

- CAP-R1 implementation 已记录不更新 README 的理由：未改变 Host public API、公共契约、状态机、事件流、测试分层或测试运行入口
- S3/S4 只补现有 `tests/host/` 文件内的测试，不改变测试分类
- 控制文档已同步更新 WU-PROJ-01 状态

### active residual risk 无 owner: ✅ PASS

- `WU-PROJ-01-CAP-R1` 已从 active residual risk 表移除（controller adjudication: CAP-R1 re-review accepted）
- `WU-PROJ-01-S3-R1` 已从 active residual risk 表移除（controller adjudication: S3/S4 code review accepted）
- `WU-PROJ-01-S4-R1` 已从 active residual risk 表移除（同上）
- active residual risk 表中无 WU-PROJ-01 条目
- 所有已关闭项有对应的关闭依据（controller adjudication artifacts）

---

## Findings

### F1（maintainability, 低严重度）: `MemoryProjectionRepairPurpose` 枚举保留不再使用的值

- **入口/函数**: `MemoryProjectionRepairPurpose` 枚举定义
- **文件(行号)**: `dayu/host/memory_repair.py:33-38`
- **输入场景**: 任何阅读该枚举的开发者
- **实际分支**: `REQUIRED_BEFORE_DISPATCH` 和 `REBUILD_BEFORE_DISPATCH` 枚举值仍存在，但不再被任何生产代码路径使用
- **预期行为**: 如果枚举值确实不再使用，应删除或标注为保留
- **实际行为**: 两个枚举值仍在 `StrEnum` 中定义，但 `rg` 搜索 `REQUIRED_BEFORE_DISPATCH|REBUILD_BEFORE_DISPATCH` 在 `dayu/host/` 生产代码中仅命中枚举定义本身（`memory_repair.py:37-38`），无任何 consumer
- **直接证据**: 
  - `memory_repair.py:37`: `REQUIRED_BEFORE_DISPATCH = "required_before_dispatch"`
  - `memory_repair.py:38`: `REBUILD_BEFORE_DISPATCH = "rebuild_before_dispatch"`
  - 旧 consumer `_memory_projection_catchup_budget` 已在 `dispatch.py` 中重命名为 `_opportunistic_memory_projection_catchup_budget`，不再接受 `purpose` 参数
  - `rg` 全仓搜索确认无其他 production consumer
- **影响**: 纯死代码，无运行时行为影响。可能让后续维护者困惑是否有路径仍在使用这两个枚举值
- **建议改法和验证点**: 在枚举 docstring 中标注 "当前 production 路径未使用"；或直接删除。如删除，需确认 `MemoryProjectionCatchupBudget.__post_init__` 中的 `isinstance(self.purpose, MemoryProjectionRepairPurpose)` 校验不受影响（该校验只检查类型，不依赖具体枚举值）
- **修复风险（低）**: 仅删除未使用的枚举值，不影响任何生产行为
- **严重程度（低）**: 纯维护性清理，不影响 correctness

### F2（informational）: opportunistic one-batch 行为极度保守

- **入口/函数**: `_opportunistic_memory_projection_catchup_budget` / `_after_commit_memory_projection_budget`
- **文件(行号)**: `dispatch.py:324-344`, `open_host.py:143-161`
- **输入场景**: compact accepted 或 commit 后，EventLog 中积累了超过 1 批（默认 batch_size）的新事件
- **实际分支**: `max_batches=1` 且 `max_scanned_events=batch_size * 1`
- **预期行为**: 当前设计正确 — opportunistic catch-up 只做 1 批轻量推进。如果该批内有更多事件未被覆盖，后续 dispatch required catch-up（`budget=None`）会补追
- **实际行为**: opportunistic catch-up 可能只推进了 `batch_size` 个事件，剩余事件留给后续 required catch-up
- **直接证据**: `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1`, `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1`
- **影响**: 无 correctness 影响。opportunistic catch-up 不是 correctness 前置条件，required catch-up 会补追。但 1 批可能过于保守，导致大部分事件都留给 required catch-up 处理
- **建议改法和验证点**: 当前值正确且安全。后续如果发现 required catch-up 耗时过长，可考虑将 opportunistic batch count 调整为 2-3，但必须在明确的数据支撑下进行，不能盲目扩大
- **修复风险（低）**: 无需修改
- **严重程度（低/信息）**: 仅为 informational，不构成 finding

---

## Open Questions

无。

---

## Residual Risk

| 风险 | 状态 | 说明 |
|---|---|---|
| `MemoryProjectionRepairPurpose.REQUIRED_BEFORE_DISPATCH` / `REBUILD_BEFORE_DISPATCH` 死代码 | deferred-with-owner | 见 F1。建议由后续 WU-PROJ-01 或 memory_repair 维护 clean up 处理，不阻塞当前 PR |
| opportunistic batch count = 1 的保守性 | informational | 见 F2。当前值安全，不构成 active risk |
| 极端 post-compact delta 场景（如数千个 events）的 SQL 查询性能 | noted | source builder 不再截断 delta，完整读取所有 canonical EventLog events。在极端场景下 SQL 查询可能返回大量 rows，但这是正确的 source builder 行为 — selection/policy/budget 决策属于下游 Context Governance 和 material selection 层。当前 Host public smoke 和 focused tests 未覆盖此极端场景，但也不应将 source builder 重设计为带 caps |

---

## 验证摘要

| 检查项 | 结果 |
|---|---|
| CAP-R1 focused tests (5 files, 173 tests) | passed |
| S3/S4 dispatch scheduler tests (1 file, 68 tests) | passed |
| pyright | 0 errors |
| git diff --check | passed |
| 全仓 stale 常量残留搜索 | 0 hits (`_bounded_query_text`, `_READABLE_QUERY_TEXT_MAX_CHARS`, `_READABLE_QUERY_TRUNCATED_MARKER`, `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES`, `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES`, `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES`, `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES`) |
| 全仓 `_memory_projection_catchup_budget` 残留搜索 | 0 hits |
| 反向依赖检查 | 无新增 |
| ordinary RunInput cap 误改检查 | 未触及 |
| 复合 material query text 路径交叉验证 | 两路径均使用 `_normalized_query_text`，委托同源 `normalized_material_text` |

---

## 总结

WU-PROJ-01 的三项 residual implementation（CAP-R1、S3-R1、S4-R1）均已完成并经过 code review、fix、re-review 和 controller adjudication。CAP-R1 正确移除了所有 correctness path 上的固定截断/上限；S3-R1 正确补了 checkpoint-covered happy path 测试；S4-R1 正确修复了 flaky lane timeout。控制文档 gate 状态更新准确。无 blocking finding，无 active residual risk 无 owner。可以进入 draft PR update push。
