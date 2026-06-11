# WU-PROJ-01 PR Review — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review
- Reviewer: AgentDS
- Date: 2026-06-11
- PR: https://github.com/noho/dayu-agent-r/pull/136
- Branch: `wu-proj-01`
- Base: `main`
- Scope: PR #136 完整 diff (82 files, +12479/-278) + 本地未提交 `docs/host/issues-implementation-control.md` gate 状态更新
- 设计真源: `docs/host/design.md`, `docs/engine/design.md`
- 总控文档: `docs/host/issues-implementation-control.md`

## 审查结论: PASS

0 条 blocking finding。2 条非阻塞 finding。无 active residual risk 无 owner。

---

## Preflight

| 检查项 | 结果 |
|---|---|
| 分支 | `wu-proj-01` → `main` |
| Changed files | 82 files: 16 production + 66 docs/review/test |
| Production changes | `dayu/host/*.py` 16 files, +4308/-262 |
| Test changes | `tests/host/*.py` 7 files, +2476/-16 |
| Controller 复验 (CAP/S3/S4 focused) | 174 passed |
| Controller 复验 (S3/S4 dispatch) | 68 passed |
| Controller 复验 (aggregate fix focused) | 91 passed |
| pyright | 0 errors |
| git diff --check | passed |

---

## 审查重点 1: CAP-R1 — 固定 query truncation、delta/evidence caps、required/rebuild correctness budgets 是否完全移除且不复发

### 判定: ✅ PASS

#### 已移除的 8 个 correctness cap 常量

| 常量 | 文件 | 旧值 | 验证 |
|---|---|---|---|
| `_READABLE_QUERY_TEXT_MAX_CHARS` | `compact_material.py` | 1200 | 全仓 `rg` 0 hits |
| `_READABLE_QUERY_TRUNCATED_MARKER` | `compact_material.py` | `\n[truncated_query_text]` | 全仓 `rg` 0 hits |
| `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS` | `compact_material.py` | 256 | 全仓 `rg` 0 hits |
| `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS` | `compact_material.py` | 8 | 全仓 `rg` 0 hits |
| `_READABLE_QUERY_TEXT_MAX_CHARS` | `compaction_evidence.py` | 1200 | 全仓 `rg` 0 hits |
| `_READABLE_QUERY_TRUNCATED_MARKER` | `compaction_evidence.py` | — | 全仓 `rg` 0 hits |
| `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES` | `dispatch.py` | 16 | 全仓 `rg` 0 hits |
| `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES` | `dispatch.py` | 32 | 全仓 `rg` 0 hits |
| `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES` | `dispatch.py` | 1 | 已重命名为 `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT` |
| `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES` | `open_host.py` | 1 | 已重命名为 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT` |

#### Source builder 完整性

直接证据 — `compact_material.py`:

- `build_pre_dispatch_compact_material_view` (line 452): 签名不再接受 `max_delta_events` / `max_evidence_blocks`。docstring 明确"不在 source builder 阶段用固定条数裁剪 post-compact delta 或 accepted evidence blocks"。
- `_post_compact_delta_rows` (line 1870): SQL 不再包含 `LIMIT ?`，完整读取 `start_sequence` 到 `end_sequence` 的所有 canonical fact rows。不再有 `if len(rows) > limit: raise HostDurableError(...)` fail-closed 分支。
- `_pre_dispatch_delta_material_blocks` (line 1931): 不再接受 `max_evidence_blocks`，内部无 evidence block 计数器和 fail-closed 分支。
- 调用点 (line 512-523): 只传 session/start/end 和 represented refs，不传任何 cap。
- `_pre_dispatch_budget_fragments` (line 2217): 遍历全部 `previous_view` 和 `material_blocks`，无截断。

#### Query text 截断移除

- `compact_material.py` `_bounded_query_text` → `_normalized_query_text`：直接 `return normalized_material_text(text)`，完整保留非空内容。
- `compaction_evidence.py` `_bounded_query_text` → `_normalized_query_text`：同上。
- 两个文件的 `_normalized_query_text` 均为独立私有 helper，委托同源 `normalized_material_text`。
- 全仓 `rg _bounded_query_text` 0 hits。

#### 新测试直接超越旧 cap

| 测试 | 文件 | 旧 cap | 验证 |
|---|---|---|---|
| `test_pre_dispatch_reads_delta_rows_beyond_old_cap` | `test_compact_material.py` | delta 256 | 260 条 user input → 260 blocks |
| `test_pre_dispatch_keeps_evidence_blocks_beyond_old_cap` | `test_compact_material.py` | evidence 8 | 10 evidence → 10 blocks |
| `test_pre_dispatch_evidence_query_text_is_not_truncated` | `test_compact_material.py` | query 1200 | len > 1200, 完整保留 |
| `test_evidence_input_semantic_query_text_is_not_truncated` | `test_compaction_operation.py` | query 1200 | len > 1200, 不追加 truncated marker |
| `test_required_catch_up_without_budget_crosses_old_batch_cap_to_target` | `test_memory_repair.py` | batch 16 | 17 批追到 target |
| `test_rebuild_without_budget_crosses_old_batch_cap_to_target` | `test_memory_repair.py` | batch 32 | 33 批追到 target |
| `test_open_host_dispatch_memory_catchup_reaches_required_cursor` | `test_open_host_runtime.py` | 旧 monkeypatch | worker SUCCEEDED, accepted |

---

## 审查重点 2: CAP-R1 — opportunistic one-batch 是否清楚标注为非 correctness

### 判定: ✅ PASS

#### dispatch required catch-up (`budget=None`)

直接证据 — `dispatch.py` `_catch_up_memory_projection_before_worker` (line 3011-3032):

```python
result = catch_up_conversation_memory_projection(
    ...
    max_event_sequence=required_event_sequence,
    budget=None,
)
```

终止条件只由 `target_reached`、`idle` 或 `failure` 决定，无固定 batch/scanned event cap。

#### dispatch rebuild (`budget=None`)

直接证据 — `dispatch.py` lag rebuild 路径 (line 2906-2912):

```python
rebuild_result = rebuild_conversation_memory_projection(
    ...
    max_event_sequence=exc.repair_request.required_event_sequence,
    budget=None,
)
```

#### `budget=None` 的所有守卫正确

直接证据 — `memory_repair.py`:

- `_bounded_batch_limit(batch_size, None, ...)` → 返回 `batch_size`（不经 `_MIN_REPAIR_BATCH_SIZE` 裁剪）
- `_budget_scanned_events_exhausted(None, ...)` → 返回 `False`
- `_budget_max_batches(None)` → 返回 `None`
- `_budget_max_scanned_events(None)` → 返回 `None`
- 循环守卫 `budget is not None and batches_used >= budget.max_batches` — `budget=None` 时不触发

#### opportunistic 命名与语义

| 旧常量 | 新常量 | 位置 | 语义 |
|---|---|---|---|
| `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES = 1` | `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1` | `dispatch.py:244` | "compact accepted 后的非 correctness opportunistic projection catch-up 批次数" |
| `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES = 1` | `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1` | `open_host.py:127` | "open_host after-commit 非 correctness memory projection catch-up 批次数" |

`_opportunistic_memory_projection_catchup_budget` 的 docstring 明确: "worker accept 前的 required catch-up / rebuild 不共享该预算，仍追到 required cursor、idle 或 failure"。

`_after_commit_memory_projection_budget` 的 docstring 明确: "不参与 dispatch 前 required / rebuild correctness catch-up"。

旧 `_memory_projection_catchup_budget` 函数已完全删除（全仓 `rg` 0 hits），不再接受 `purpose` 参数路由。

---

## 审查重点 3: S3-R1 — dispatch checkpoint-covered happy path 测试

### 判定: ✅ PASS

新测试 `test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input` (`test_dispatch_scheduler.py:1987`):

1. **prewarm**: 用 `catch_up_conversation_memory_projection(..., budget=None)` 追到 `required_event_sequence`，验证 `prewarmed.target_reached is True`、`checkpoint_before_dispatch == required_event_sequence`。
2. **monkeypatch wrapper**: `_observed_catch_up` 只追加观察副作用，调用真实 production `catch_up_conversation_memory_projection`，不替换返回值。
3. **真实 dispatch 路径**: `_open_scheduler → wake_dispatch → drain_once`，走完整 `_catch_up_memory_projection_before_worker → _build_run_input_with_lag_repair → worker.accept`。
4. **关键断言**:
   - `dispatch_catchup.events_scanned == 0` — checkpoint 已覆盖，不重复扫描
   - `dispatch_catchup.target_reached is True` — `_raise_if_memory_projection_target_not_reached` 通过
   - `checkpoint_after_dispatch == checkpoint_before_dispatch` — checkpoint 稳定
   - `run.status == RUNNING` / `attempt.status == RUNNING` / `dispatch_record.status == DISPATCHING`
   - `factory.accepted_requests[0].disable_tools is True` — ordinary RunInput 构造正确
   - `_event_count("RUN_FAILED") == 0` / `_event_count("RUN_RECOVERING") == 0` — 不进入失败/恢复
   - `_attempt_count_for_run == 1` — 无额外的 recovery Attempt

5. **设计对齐**: 与 `docs/host/design.md` 第 24.5 节一致："若 ordinary dispatch 前 snapshot cursor 不能覆盖 required EventLog cursor，Host 必须执行 bounded memory projection catch-up / rebuild...这不是 Run crash recovery，不得把 Run 推入 RECOVERING。"

6. **与既有测试边界清晰**:
   - `test_dispatch_lag_repair_rebuild_not_reached_fails_closed`: checkpoint 未覆盖 → fail-closed
   - `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering`: lag failure 收口
   - `test_open_host_dispatch_memory_catchup_reaches_required_cursor`: open_host 层 required catch-up
   - S3-R1: checkpoint 已覆盖 → ordinary RunInput happy path

---

## 审查重点 4: S4-R1 — flaky lane timeout 测试稳定化

### 判定: ✅ PASS

`test_reactive_compact_failure_fallback_dispatch_uses_failed_view` (`test_dispatch_scheduler.py:4988`):

唯一的变更: `_open_scheduler(...)` 增加 `lane_default_timeout_seconds=1.0`（默认 0.01）。

**理由**: 该测试验证 reactive compact failure fallback dispatch 语义，不验证 lane acquire timeout。将 lane timeout 从 10ms 收紧为默认值会使 fallback 语义断言暴露给无关的宿主机调度窗口。

**断言完整性**: 所有原有断言完整保留:
- `len(factory.accepted_snapshots) == 2` — 两条 Attempt
- 第二条 Attempt `attempt_id != seeded.attempt_id` — 新 Attempt
- `_attempt_count_for_run == 2`
- `CONTEXT_COMPACTED` count == 0
- `RUN_LOST` count == 0
- `CONTEXT_COMPACTION_FAILED` payload 验证
- 第二条 request 不包含 compact artifact 文本

断言强度未降低。不修改生产 lane acquire 语义。

---

## 审查重点 5: aggregate fix 删除 enum 值 — 兼容/类型/测试风险

### 判定: ✅ PASS

#### 变更内容 (commit `bd6488df`)

```diff
 class MemoryProjectionRepairPurpose(StrEnum):
     BEST_EFFORT_AFTER_COMMIT = "best_effort_after_commit"
-    REQUIRED_BEFORE_DISPATCH = "required_before_dispatch"
-    REBUILD_BEFORE_DISPATCH = "rebuild_before_dispatch"
```

#### 兼容性检查

| 检查项 | 结果 |
|---|---|
| 全仓 `REQUIRED_BEFORE_DISPATCH` 残留 | 0 hits |
| 全仓 `REBUILD_BEFORE_DISPATCH` 残留 | 0 hits |
| production code import/stale reference | 0 hits (`dispatch.py`, `open_host.py` 均只使用 `BEST_EFFORT_AFTER_COMMIT`) |
| test reference | 6 处已更新为 `BEST_EFFORT_AFTER_COMMIT` |
| 序列化兼容 | `StrEnum` 是 string 子类，持久化的旧值可正常读取，不依赖具体枚举成员 |
| `isinstance(self.purpose, MemoryProjectionRepairPurpose)` 校验 | 不变 — `BEST_EFFORT_AFTER_COMMIT` 仍是合法成员 |
| pyright | 0 errors |

#### 类型风险

`MemoryProjectionRepairPurpose` 当前只有一个成员 `BEST_EFFORT_AFTER_COMMIT`，但:
- `isinstance` 校验在 `MemoryProjectionCatchupBudget.__post_init__` 中仍然有效
- 未来若需要区分 "required" 和 "best-effort" catch-up 调用语义，可重新扩展枚举
- 当前语义已由 `budget=None`（correctness 无上限）vs `budget=<bounded>`（opportunistic） 承载，"purpose" 字段退化为统一标注

---

## 审查重点 6: 控制文档 gate 状态与 Issue 86/PR 后续动作一致性

### 判定: ✅ PASS

#### 未提交控制文档变更

```diff
-| WU-PROJ-01 | accepted-deepreview-commit | ... | Next gate: PR update push. |
+| WU-PROJ-01 | PR-review | ... | Residual implementation accepted commits: CAP-R1 `448b70ba`, S3/S4 `3baeef53`, aggregate fix `bd6488df`; pushed to PR #136 branch `wu-proj-01`. ... Next gate: PR review. |
```

#### 一致性检查

| 检查项 | 结果 |
|---|---|
| gate 状态与实际状态一致 | ✅ PR 已 push，处于 PR review gate |
| accepted commits 记录完整 | ✅ 三个 residual commits 均已记录 |
| active residual risk 表无 WU-PROJ-01 条目 | ✅ CAP-R1 / S3-R1 / S4-R1 均已关闭 |
| 关闭依据可追溯 | ✅ 对应 controller adjudication / code review / aggregate deepreview artifact 均已列出 |
| Issue #86 Closes 声明 | ✅ PR body 写 `Closes #86`，本 PR 完成 #86 scope 的 residual implementation |
| next gate 指向 | ✅ "PR review" — 即本 gate |

---

## 审查重点 7: README / 测试 / pyright / hardcoding / overdesign 风险

### README

| 文件 | 变更 | 更新判定 |
|---|---|---|
| `dayu/host/README.md` | 1 行描述更新（Memory-compact 关系单向性表述） | ✅ 合理 — 属于职责范围，语义收敛 |
| `tests/README.md` | 1 行计数更新 | ✅ 合理 — 新增测试文件需同步计数 |

CAP-R1 和 S3/S4 implementation report 判断不更新 README 的理由成立：未改变 Host public API、公共契约、状态机、事件流或测试分层。

### 测试

| 测试文件 | 新增测试数 | 覆盖范围 | 判定 |
|---|---|---|---|
| `test_compact_material.py` | +1145 行 | pre-dispatch material source builder whole-path + delta/evidence/query no-cap + boundary/error | ✅ |
| `test_dispatch_scheduler.py` | +684 行 (含 +151 S3/S4) | checkpoint-covered happy path + lag repair fail-closed + opportunistic + rebuild boundary | ✅ |
| `test_memory_repair.py` | +324 行 | budget=None correctness + catch-up/rebuild cross old batch cap + budget exhausted | ✅ |
| `test_memory_projection.py` | +102 行 | regression coverage | ✅ |
| `test_open_host_runtime.py` | +141 行 | dispatch required catch-up reaches cursor | ✅ |
| `test_compaction_operation.py` | +67 行 | query text no-truncation + limited signal | ✅ |
| `test_run_input_builder.py` | +9 行 | minor | ✅ |
| `test_logging.py` | +3 行 | minor | ✅ |

所有测试均使用真实 production 路径，无测试私有入口。新测试 helper（如 `_read_memory_checkpoint_sequence`）均以 `_` 前缀保持模块级私有，有完整中文 docstring 和类型标注。

### pyright

Controller 复验 + 独立验证: 0 errors, 0 warnings, 0 informations.

### hardcoding

| 检查项 | 结果 |
|---|---|
| 旧 correctness cap 常量残留 | 0 (全仓 `rg` 验证) |
| 旧函数名残留 (`_memory_projection_catchup_budget`, `_bounded_query_text`) | 0 (全仓 `rg` 验证) |
| 新增 magic number | 0 — `_OPPORTUNISTIC_*_BATCH_COUNT = 1` 是模块级命名常量 |
| `lane_default_timeout_seconds=1.0` | ✅ 测试 fixture 参数，非生产代码 |
| 无兼容性 re-export / wrapper / facade | ✅ |

### overdesign

| 检查项 | 结果 |
|---|---|
| 无新增抽象层、框架化或平台化能力 | ✅ |
| 删除 10 个旧常量/枚举值，不新增 public API | ✅ |
| 函数签名只做删除参数，不做新增 | ✅ |
| 无 general-purpose "framework" 倾向 | ✅ |

---

## Findings

### F1（maintainability, 低严重度）: `MemoryProjectionRepairPurpose` 退化为单值枚举

- **文件**: `dayu/host/memory_repair.py:33-36`
- **内容**: 删除 `REQUIRED_BEFORE_DISPATCH` 和 `REBUILD_BEFORE_DISPATCH` 后，`MemoryProjectionRepairPurpose` 仅剩 `BEST_EFFORT_AFTER_COMMIT` 一个成员。`StrEnum` 单值枚举仍可通过 `isinstance` 提供类型安全，但 signal/noise 比偏低。
- **影响**: 纯设计 tidiness。不影响 correctness、类型安全或运行时行为。
- **建议**: 后续 WU-PROJ-01 或 memory_repair 维护时可评估是否将 `purpose` 字段收敛为 sentinel `None`（当不再需要区分调用意图时），或将枚举保留但加 docstring 说明当前简化状态。当前状态可接受，不阻塞 PR。
- **严重程度**: 低

### F2（informational）: `run_input.py` 的 compactor 侧 `max_evidence_blocks=8` 独立存在

- **文件**: `dayu/host/run_input.py:211` (`_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8`)
- **内容**: 该 cap 属于 compactor input path 的 `AcceptedToolEvidenceMaterial`，不是 pre-dispatch compact material source builder 的 cap。它在 material selection 层（compactor 输入），不在 source builder 层（EventLog → material blocks）。
- **影响**: 无 CAP-R1 回归风险。两个 cap 分属不同治理层：source builder 构建完整 canonical view，material selection 在 compactor 输入侧做 relevance-based bounded selection。
- **建议**: 无需修改。但后续若审查 compactor input governance 时，可评估该 limit 是否仍合理或应改为 policy-driven。
- **严重程度**: 信息性

---

## 剩余风险

| 风险 | 状态 | 说明 |
|---|---|---|
| 极端 post-compact delta 场景 SQL 性能 | noted | source builder 不再截断 delta，极端场景可能返回大量 rows。但这是 source builder 的正确行为 — selection/policy/budget 属于下游 Context Governance 层。当前无阻塞证据 |
| `MemoryProjectionRepairPurpose` 单值枚举 | deferred-with-owner | 见 F1，后续维护清理 |
| `run_input.py` evidence material limit | noted | 见 F2，不属于 CAP-R1 scope |

无 active residual risk 无 owner。`WU-PROJ-01-CAP-R1`、`WU-PROJ-01-S3-R1`、`WU-PROJ-01-S4-R1` 已在 aggregate deepreview 和本 PR review 中关闭。

---

## 验证摘要

| 检查项 | 结果 |
|---|---|
| CAP-R1 focused tests (5 files) | 174 passed |
| S3/S4 dispatch scheduler tests (1 file) | 68 passed |
| Aggregate fix focused tests (3 files) | 91 passed |
| pyright | 0 errors |
| git diff --check | passed |
| 全仓 stale 常量搜索 | 0 hits (`_bounded_query_text`, `_READABLE_QUERY_TEXT_MAX_CHARS`, `_READABLE_QUERY_TRUNCATED_MARKER`, `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS`, `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS`, `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES`, `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES`, `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES`, `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES`, `_memory_projection_catchup_budget`) |
| 全仓 deleted enum 值搜索 | 0 hits (`REQUIRED_BEFORE_DISPATCH`, `REBUILD_BEFORE_DISPATCH`) |
| 控制文档与 PR/Issue 一致性 | ✅ |
| README 更新 | ✅ 合理，语义收敛 |
| 反向依赖 | 无新增 |
| overdesign/hardcoding | 无新增 |

---

## 总结

WU-PROJ-01 PR #136 完整关闭了 WU-PROJ-01 CAP-R1 / S3-R1 / S4-R1 residual risks：

- **CAP-R1**: 移除了 compact material source builder 的全部固定截断（query truncation、delta cap、evidence cap）和 dispatch/repair 的 correctness batch budget（required/rebuild paths 使用 `budget=None`）；opportunistic one-batch 明确标注为非 correctness。
- **S3-R1**: 新增 `test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input`，覆盖 checkpoint 已覆盖 required cursor 时 dispatch 直接接受 ordinary worker 的 happy path。
- **S4-R1**: 为 `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 增加 `lane_default_timeout_seconds=1.0`，消除无关 lane acquire timeout 对 fallback 语义断言的影响。
- **Aggregate fix**: 删除 `MemoryProjectionRepairPurpose.REQUIRED_BEFORE_DISPATCH` / `REBUILD_BEFORE_DISPATCH` 枚举值，全仓 0 残留。

0 条 blocking finding。2 条非阻塞 finding（单值枚举 cleanup、compactor 侧 evidence limit 标注）。无 active residual risk 无 owner。PR 可进入下一 gate（draft → ready for review / merge）。
