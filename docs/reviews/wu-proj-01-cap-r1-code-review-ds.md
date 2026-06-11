# WU-PROJ-01-CAP-R1 Code Review

## 元数据

- Work unit: `WU-PROJ-01`
- 审查项: CAP-R1 implementation diff（未提交）
- 审查者: AgentDS
- 日期: 2026-06-11
- 分支: `wu-proj-01`
- 审查范围: 仅 `git status --short` 中 `M` 标记的 CAP-R1 实现变更，不审查 `WU-PROJ-01-S3-R1` / `WU-PROJ-01-S4-R1`
- 前置 artifacts:
  - `docs/host/issues-implementation-control.md`（控制文档真源）
  - `docs/reviews/wu-proj-01-residual-risk-user-decision-controller.md`（用户裁决）
  - `docs/reviews/wu-proj-01-cap-r1-implementation-codex.md`（Codex 实现报告）

## 审查结论

**PASS-WITH-FINDINGS** — 0 条 blocking finding。

6 条 finding，其中 1 条 correctness（低严重度，无行为影响），2 条 maintainability，1 条 residual risk tracking，2 条 informational。没有发现需要 block PR 的问题。

## Preflight

- 分支：`wu-proj-01`
- 未提交变更：`dayu/host/compact_material.py`、`dayu/host/dispatch.py`、`dayu/host/open_host.py`、`docs/host/issues-implementation-control.md`、`tests/host/test_compact_material.py`、`tests/host/test_memory_repair.py`、`tests/host/test_open_host_runtime.py`
- Controller 复验：`pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py` → 125 passed；pyright → 0 errors；`git diff --check` → passed

## 审查重点 1：compact_material.py source builder caps

### 判定：✅ PASS

**delta event cap（旧 `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS = 256`）**

直接证据：
- `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS` 已从模块级常量删除（`git diff` 行 154）。
- `build_pre_dispatch_compact_material_view` 签名不再接受 `max_delta_events` 参数（行 458）。
- `_post_compact_delta_rows` 不再接受 `limit` 参数，SQL 查询的 `LIMIT ?` 已移除（行 1929-1931），不再有 `if len(rows) > limit: raise HostDurableError(...)` fail-closed 分支（行 1946-1947 已删除）。
- 调用处只传 `session_id`、`start_sequence`、`end_sequence`（行 512-517），不再传 `limit`。

结论：post-compact delta 完整读取从 latest compact boundary 到 current input 前的 canonical EventLog 事件，不再被任意 `256` 截断。

**evidence block cap（旧 `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS = 8`）**

直接证据：
- `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS` 已删除（行 154）。
- `_pre_dispatch_delta_material_blocks` 不再接受 `max_evidence_blocks` 参数（行 1937）。
- 内部 `evidence_count` 累加计数器与 `if evidence_count > max_evidence_blocks: raise HostDurableError(...)` 已删除（行 1964-1967 已删除）。
- 调用处只传 `rows` 和 `represented_evidence_refs`（行 518-523），不再传 `max_evidence_blocks`。

结论：accepted evidence blocks 全部纳入 material view，不再按固定 `8` 块 fail closed。

**query text truncation（旧 `_READABLE_QUERY_TEXT_MAX_CHARS = 1200`）**

直接证据：
- `_READABLE_QUERY_TEXT_MAX_CHARS` 与 `_READABLE_QUERY_TRUNCATED_MARKER` 已删除（行 152-153）。
- `_bounded_query_text` 函数体从 `normalize + truncate + append marker` 改为 `return normalized_material_text(text)`（行 2200），不再截断。
- docstring 更新为"规范化 query 文本并保留完整非空内容"（行 2192-2193）。

结论：pre-dispatch evidence query text 不再按 1200 字符截断或添加 truncated marker。

**canonical EventLog delta 完整性**

直接证据：
- `_post_compact_delta_rows` SQL 查询的 `WHERE event_sequence >= start_sequence AND event_sequence < end_sequence` 不变，`ORDER BY event_sequence ASC` 不变，仅移除 `LIMIT ?`。
- 查询的 `start_sequence` 来自 `_delta_start_sequence_for_dispatch`，其逻辑是：有 latest compact 时从 `compacted_event_sequence + 1` 开始，无 latest compact 时从 session 第一条 `USER_INPUT_ACCEPTED` 开始（`compact_material.py` 行 470-508）。
- 查询的 `end_sequence` 为当前 input event 的 sequence（不含）。

结论：完整保留 latest compact → current input 之间的 canonical EventLog delta。

## 审查重点 2：dispatch / memory_repair / open_host correctness budgets

### 判定：✅ PASS

**旧常量删除**

直接证据（`grep -rn` 全仓搜索确认）：
- `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES = 16` — 已删除
- `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES = 32` — 已删除
- `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES = 1` — 已删除
- `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES = 1` — 已删除

**dispatch required catch-up correctness 路径**

直接证据 — `dispatch.py` `_catch_up_memory_projection_before_worker`（行 3020-3026）：
```python
result = catch_up_conversation_memory_projection(
    ...
    max_event_sequence=required_event_sequence,
    budget=None,  # ← 无预算，追到 required cursor、idle 或 failure
)
```

直接证据 — `dispatch.py` lag rebuild 路径（行 2906-2912）：
```python
rebuild_result = rebuild_conversation_memory_projection(
    ...
    max_event_sequence=exc.repair_request.required_event_sequence,
    budget=None,  # ← 无预算，追到 required cursor、idle 或 failure
)
```

**batch_size 职责收窄**

`batch_size` 在 budget=None 路径中只作为单批扫描粒度：
- `_bounded_batch_limit(batch_size, budget=None, ...)` → 直接返回 `batch_size`，不参与全局预算关闸（`memory_repair.py` 行 497-498）。
- `_budget_scanned_events_exhausted(None, ...)` → 直接返回 `False`（行 514）。
- `budget is not None and batches_used >= budget.max_batches` → 在 `budget=None` 时不触发（行 330）。

结论：required/rebuild catch-up 的终止条件只由 `target_reached`、`idle` 或 `failure` 决定，不再被 `max_batches` / `max_scanned_events` 截断。

**`_raise_if_memory_projection_target_not_reached` 行为**

直接证据（`dispatch.py` 行 347-373）：
- 判断条件为 `result.failures == 0 and result.target_reached`。
- `budget=None` 时 `target_reached` 由 `finished_cursor >= max_event_sequence` 决定（`memory_repair.py` 行 528）。
- 不再有"预算耗尽但未到 target 也算通过"的旧语义。

**memory_repair.py budget=None 支持**

直接证据：
- `_bounded_batch_limit(batch_size, None, events_scanned)` → 返回 `batch_size`（行 497-498）
- `_budget_scanned_events_exhausted(None, events_scanned)` → 返回 `False`（行 514）
- `_budget_max_batches(None)` → 返回 `None`（行 550-552）
- `_budget_max_scanned_events(None)` → 返回 `None`（行 564-566）
- `budget is not None and batches_used >= budget.max_batches` → budget=None 时不触发（行 330）
- `_bounded_batch_limit` 在 `budget=None` 时直接返回 `batch_size`，不会触发 `limit < _MIN_REPAIR_BATCH_SIZE`（行 333-336）

所有 budget-aware 守卫均正确处理 `None`，不会在无预算模式下误关闸。

## 审查重点 3：after-commit / after-compact opportunistic 命名与语义

### 判定：✅ PASS

**命名变更**

| 旧名称 | 新名称 | 位置 |
|---|---|---|
| `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES` | `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT` | `open_host.py` 行 127-128 |
| `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES` | `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT` | `dispatch.py` 行 244-245 |

新命名以 `_OPPORTUNISTIC_` 前缀明确表示非 correctness 行为。

**docstring 清晰度**

- `_opportunistic_memory_projection_catchup_budget` docstring（`dispatch.py` 行 329-336）明确："该预算只影响 compact 后、正式 dispatch 前的轻量投影推进；worker accept 前的 required catch-up / rebuild 不共享该预算，仍追到 required cursor、idle 或 failure。"
- `_after_commit_memory_projection_budget` docstring（`open_host.py` 行 146-149）明确："该预算只影响 commit 后轻量投影推进，不参与 dispatch 前 required / rebuild correctness catch-up。"

**purpose 语义**

两个 opportunistic 路径均使用 `MemoryProjectionRepairPurpose.BEST_EFFORT_AFTER_COMMIT`（`dispatch.py` 行 343，`open_host.py` 行 160）。`REQUIRED_BEFORE_DISPATCH` 与 `REBUILD_BEFORE_DISPATCH` 在 `MemoryProjectionRepairPurpose` 枚举中保留定义但不再被任何生产路径使用。

结论：命名和 docstring 足够清楚地表明这些路径不影响 dispatch correctness。旧 `_memory_projection_catchup_budget` 函数已收敛为 `_opportunistic_memory_projection_catchup_budget`，不再接受 `purpose` 参数路由，消除误用可能。

## 审查重点 4：新测试验证

### 判定：✅ PASS

| 测试 | 文件 | 覆盖的旧 cap | 验证内容 |
|---|---|---|---|
| `test_pre_dispatch_reads_delta_rows_beyond_old_cap` | `test_compact_material.py` 行 887 | delta 256 | 260 条 user input → 260 blocks，首尾断言 |
| `test_pre_dispatch_keeps_evidence_blocks_beyond_old_cap` | `test_compact_material.py` 行 952 | evidence 8 | 10 条 evidence → 10 blocks，最后一条 id 断言 |
| `test_pre_dispatch_evidence_query_text_is_not_truncated` | `test_compact_material.py` 行 1041 | query 1200 | 超长 query > 1200 chars，断言完整保留且长度 > 1200 |
| `test_required_catch_up_without_budget_crosses_old_batch_cap_to_target` | `test_memory_repair.py` 行 390 | batch 16 | 17 批追到 target=17，断言 `budget_exhausted=False`，`max_batches=None`，`max_scanned_events=None` |
| `test_rebuild_without_budget_crosses_old_batch_cap_to_target` | `test_memory_repair.py` 行 482 | batch 32 | 33 批追到 target=33，断言 `budget_exhausted=False`，`max_batches=None`，`max_scanned_events=None` |
| `test_open_host_dispatch_memory_catchup_reaches_required_cursor` | `test_open_host_runtime.py` 行 661 | 旧测试 monkeypatch 了 `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES=1` | 改写为：skip after-commit catch-up 后，dispatch required catch-up 追到 target → worker accept SUCCEEDED |

**覆盖完整性评估**

- delta 超越旧 cap → ✅ 有（260 > 256）
- evidence 超越旧 cap → ✅ 有（10 > 8）
- query 超越旧 cap → ✅ 有（240段 × "segment" ≈ 2400+ chars > 1200）
- required catch-up 跨旧 batch 限制 → ✅ 有（17 > 16）
- rebuild 跨旧 batch 限制 → ✅ 有（33 > 32）
- after-commit 不追账时 dispatch required catch-up 仍追到 target → ✅ 有（改写旧测试）
- 旧 cap 不存在时不 fail → ✅ 所有新测试均未触发 cap 相关异常

## 审查重点 5：compaction_evidence.py 剩余 caps 裁决

### 判定：⚠️ OUT OF SCOPE — 建议独立 owner

**直接证据**

`dayu/host/compaction_evidence.py` 仍包含（`grep` 确认）：
- 行 47：`_READABLE_QUERY_TEXT_MAX_CHARS = 1200`
- 行 48：`_READABLE_QUERY_TRUNCATED_MARKER = "\n[truncated_query_text]"`
- 行 350-364：`_bounded_query_text` 仍执行 `normalize → if len > max → truncate + append marker`

**模块归属分析**

| 模块 | 调用者 | 用途 | CAP-R1 范围？ |
|---|---|---|---|
| `compact_material.py` | `build_pre_dispatch_compact_material_view` | pre-dispatch source builder | ✅ 已修复 |
| `compaction_evidence.py` | `run_input.py` `DurableAcceptedToolEvidenceMaterialProvider` | compactor RunInput evidence material 读取 | ❌ 不在 source builder 路径 |

直接证据：
- `grep -rn 'compaction_evidence' dayu/host/ --include='*.py'` 显示只有 `run_input.py` 导入 `compaction_evidence`。
- `compact_material.py` 不导入 `compaction_evidence`（`grep` 空输出）。
- `compact_material.py` 有自己的独立 `_bounded_query_text`（行 2192），不再截断。

**裁决理由**

1. `compaction_evidence.py` 是 compactor RunInput 的证据材料读取器，不是 pre-dispatch source builder。CAP-R1 用户裁决的原文是"compact source builder 不截断 query"——source builder 指 `build_pre_dispatch_compact_material_view`，已完全修复。
2. `compaction_evidence.py` 的 `_bounded_query_text` 截断的是 compactor LLM 看到的 evidence query text。compactor 是 LLM，其输入需要 context budget 管理；这里的 1200 字符截断是 compactor prompt 预算约束，不是 source truth 丢失。
3. 该文件不在 Codex 实现报告列出的 allowed files 中（报告已明确："该文件不在本次用户给定 allowed files 内"）。
4. 同类关注项 `run_input.py` 的 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8`（行 211）也保留，同样是 compactor 输入预算约束而非 source builder cap。

**裁决建议**

- 建议由 `WU-CM-01-F02`（Compact Evidence Query Readability Quality Closeout）或新的 compactor evidence quality work unit 承接。
- 如果后续裁决认为 compactor 输入的 query text 也不应截断，应作为独立的 compactor context budget 设计决策，同时处理 `compaction_evidence.py` 的 `_READABLE_QUERY_TEXT_MAX_CHARS` 与 `run_input.py` 的 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`。
- 该问题不影响 CAP-R1 的 PASS 结论。

## 审查重点 6：新硬编码、过度抽象、兼容 wrapper、README

### 判定：✅ PASS — 2 条 maintainability finding，无 blocking

### Finding 1（maintainability, 低严重度）：`_bounded_query_text` 函数名不再准确

- 文件：`dayu/host/compact_material.py` 行 2192
- 问题：`_bounded_query_text` 函数名暗示"有界/截断"，但函数体现在只做 `return normalized_material_text(text)`，不再做任何截断。
- docstring 已更新为"保留完整非空内容"，语义正确，但函数名与实现不一致。
- 影响：阅读代码时需要多看 docstring 一眼才能确认不再截断。不影响运行时行为。
- 建议：后续重命名为 `_normalized_query_text` 或 `_readable_query_text`，但非阻塞项。

### Finding 2（maintainability, 低严重度）：`dispatch.py` 中 `REQUIRED_BEFORE_DISPATCH` / `REBUILD_BEFORE_DISPATCH` 枚举值仍存在

- 文件：`dayu/host/memory_repair.py` 行 37-38
- `MemoryProjectionRepairPurpose.REQUIRED_BEFORE_DISPATCH` 和 `REBUILD_BEFORE_DISPATCH` 枚举值保留，但不再被任何生产代码路径使用（唯一引用已移除的 `_memory_projection_catchup_budget` 的 `purpose` 路由分支）。
- 影响：纯死代码，无运行时行为影响。保留它们不违反正确性，但可能让后续读者困惑是否有路径仍在使用。
- 建议：若确认 `dispatch.py` 和 `open_host.py` 以外的模块也没有使用这两个枚举值，可删除；或保留并在枚举 docstring 中标注"保留但当前生产路径未使用"。

### Finding 3（residual risk tracking）：compaction_evidence.py 剩余 caps

- 见审查重点 5 的详细裁决。建议写入 control doc 的 residual risk 表。

### Finding 4（informational）：没有引入新的硬编码 correctness 常量

- 新增的两个常量 `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1` 和 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1` 是 opportunistic 预算，命名以 `_OPPORTUNISTIC_` 前缀明确非 correctness 语义，docstring 完整。它们替代了旧的 `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES` 和 `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES`，语义收敛而非新增约束。

### Finding 5（informational）：没有引入兼容 wrapper 或过度抽象

- 全 diff 内无兼容性 re-export、兼容性 wrapper/facade、胶水 seam、lazy import 或不必要的抽象层。
- `_opportunistic_memory_projection_catchup_budget` 替代了旧的 `_memory_projection_catchup_budget`，是一个更收敛、职责更清晰的 helper，不是过度抽象。

### Finding 6（informational）：README 不需要更新

- `dayu/host/README.md` 行 88 提到"memory catch-up batch size"但不提及内部常量名（如 `max_batches`、`_MEMORY_PROJECTION_*_MAX_BATCHES`）。本次变更不改变 `OpenHostOptions` 公共字段、Host public API、测试层级或分层边界。
- `tests/README.md` 不涉及：新测试是现有 `tests/host` 文件内的 CAP-R1 回归测试，不改变测试分类。
- 与 Codex 实现报告的 README 决策一致（报告行 72-83）。

## 验证结果

- Controller 复验：`pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py` → 125 passed
- Controller 复验：`pyright` → 0 errors, 0 warnings
- Controller 复验：`git diff --check` → passed

## Findings 汇总

| # | 严重度 | 类别 | 文件 | 描述 | 建议 |
|---|---|---|---|---|---|
| F1 | 低 | maintainability | `compact_material.py:2192` | `_bounded_query_text` 函数名暗示截断但不再截断 | 后续重命名为 `_normalized_query_text` |
| F2 | 低 | maintainability | `memory_repair.py:37-38` | `REQUIRED_BEFORE_DISPATCH` / `REBUILD_BEFORE_DISPATCH` 枚举值不再被生产路径使用 | 删除或标注为保留 |
| F3 | — | residual risk | `compaction_evidence.py:47-48,350-364` | compactor evidence query 仍有 1200 字符截断 | 写入 control doc residual risk 表，由 WU-CM-01-F02 或新 work unit 承接 |
| F4 | — | informational | `dispatch.py` + `open_host.py` | 新增 `_OPPORTUNISTIC_*` 常量，语义从 correctness 收敛为 opportunistic | 无需处理 |
| F5 | — | informational | 全 diff | 无兼容 wrapper、过度抽象或胶水 seam | 无需处理 |
| F6 | — | informational | `dayu/host/README.md` | README 无需更新 | 无需处理 |

## 总体评价

CAP-R1 实现正确且彻底地完成了用户裁决的目标：

1. **source builder 清除了所有 correctness caps**：delta 事件、evidence blocks、query text 均不再在 source builder 阶段被固定常量截断。
2. **dispatch correctness 路径不再有 batch 预算**：required catch-up 和 rebuild 都追到 target/idle/failure，不再被 `max_batches` / `max_scanned_events` 提前截断。
3. **opportunistic 路径命名和文档正确**：after-commit/after-compact 的 1 批轻量推进明确标注为非 correctness opportunistic 行为。
4. **测试覆盖充分**：所有旧 cap 边界均有超越测试，required/rebuild 跨 batch 测试直接断言 `budget_exhausted=False` 和 `max_batches=None`。
5. **compaction_evidence.py 剩余 caps**：不属于 CAP-R1 source builder 范围，建议独立 tracking。
6. **无新增硬编码、过度抽象或兼容 wrapper**：代码变更量最小化，删除多于新增，命名收敛清晰。
