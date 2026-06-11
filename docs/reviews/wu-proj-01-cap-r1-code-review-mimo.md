# WU-PROJ-01-CAP-R1 Code Review

## 元数据

- Reviewer: AgentMiMo
- Date: 2026-06-11
- Branch: `wu-proj-01`
- Diff scope: 6 modified files + 1 new (untracked) implementation artifact
- Review type: CAP-R1 implementation code review

## Preflight

- `git branch --show-current`: `wu-proj-01` ✅
- `git status --short`: 6 modified, 1 untracked ✅

## 结论

**PASS-WITH-FINDINGS**

所有 correctness 目标均已实现。无 blocking finding。1 条低严重度 finding（compaction_evidence.py 残留 truncation helper 的 owner 建议）。

## 审查逐项裁决

### 1. compact_material.py 是否真正删除 source builder 阶段截断 / cap

**PASS** ✅

直接证据：

| 旧常量 / 参数 | 状态 | 验证 |
|---|---|---|
| `_READABLE_QUERY_TEXT_MAX_CHARS = 1200` | 已删除 | diff 第 9-10 行：removed |
| `_READABLE_QUERY_TRUNCATED_MARKER` | 已删除 | diff 第 10 行：removed |
| `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS = 256` | 已删除 | diff 第 11 行：removed |
| `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS = 8` | 已删除 | diff 第 12 行：removed |
| `build_pre_dispatch_compact_material_view(max_delta_events=..., max_evidence_blocks=...)` | 参数已移除 | diff 第 20-21 行 |
| `_post_compact_delta_rows(limit=...)` | 参数已移除；SQL `LIMIT ?` 已删除 | diff 第 69-101 行 |
| `_pre_dispatch_delta_material_blocks(max_evidence_blocks=...)` | 参数已移除；evidence count check 已删除 | diff 第 104-136 行 |
| `_bounded_query_text` | 不再截断，直接委托 `normalized_material_text` | diff 第 141-157 行 |

SQL 层面：`_post_compact_delta_rows` 的 SQL 不再包含 `LIMIT ?` 子句（diff 第 88-89 行），完整读取 `start_sequence` 到 `end_sequence` 之间的所有 canonical fact rows。

docstring 更新：`build_pre_dispatch_compact_material_view` docstring 已明确 "也不在 source builder 阶段用固定条数裁剪 post-compact delta 或 accepted evidence blocks"（当前文件第 462-463 行）。

### 2. dispatch.py / open_host.py 是否去掉 required/rebuild correctness max_batches

**PASS** ✅

直接证据：

| 旧常量 | 状态 | 验证 |
|---|---|---|
| `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES = 1` | 已删除 | diff 第 168 行 |
| `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES = 16` | 已删除 | diff 第 169 行 |
| `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES = 32` | 已删除 | diff 第 170 行 |
| `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES = 1` (open_host.py) | 已重命名 | diff 第 277-279 行 |

Correctness 路径变更：

- `catch_up_before_dispatch`：`budget=None`（dispatch.py:3025）。`memory_repair.py` 中 `budget is not None` 分支跳过，循环追到 `max_event_sequence` 或 failure。
- `rebuild_before_dispatch`：`budget=None`（dispatch.py:2911）。同上。

Open_host after-commit 保留为 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1`（open_host.py:147），docstring 明确 "不参与 dispatch 前 required / rebuild correctness catch-up"（open_host.py:151）。

`_memory_projection_catchup_budget` 已重命名为 `_opportunistic_memory_projection_catchup_budget`（dispatch.py:325），docstring 明确 "worker accept 前的 required catch-up / rebuild 不共享该预算"（dispatch.py:329-331）。该函数现在只用于 compact accepted 后的轻量推进路径（dispatch.py:1019）。

### 3. after-commit / after-compact opportunistic 命名和 docstring

**PASS** ✅

- `dispatch.py`：`_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1`，模块级 docstring "compact accepted 后的非 correctness opportunistic projection catch-up 批次数"（dispatch.py:244-245）。
- `open_host.py`：`_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1`，模块级 docstring "open_host after-commit 非 correctness memory projection catch-up 批次数"（open_host.py:148-149）。
- `_opportunistic_memory_projection_catchup_budget` 函数 docstring "该预算只影响 compact 后、正式 dispatch 前的轻量投影推进；worker accept 前的 required catch-up / rebuild 不共享该预算"（dispatch.py:329-331）。
- `_after_commit_memory_projection_budget` 函数 docstring "该预算只影响 commit 后轻量投影推进，不参与 dispatch 前 required / rebuild correctness catch-up"（open_host.py:150-152）。

命名清晰度足够。opportunistic 语义与 correctness 语义有明确边界。

### 4. 新测试是否证明超过旧限制仍不 fail / 不截断

**PASS** ✅

| 测试 | 覆盖点 | 验证 |
|---|---|---|
| `test_pre_dispatch_reads_delta_rows_beyond_old_cap` | 260 delta rows > 旧 256 cap | `len(view.material_blocks) == 260`，首尾 row 断言正确 |
| `test_pre_dispatch_keeps_evidence_blocks_beyond_old_cap` | 10 evidence blocks > 旧 8 cap | `len(evidence_blocks) == 10`，最后一块 id 断言正确 |
| `test_pre_dispatch_evidence_query_text_is_not_truncated` | query > 1200 字符 | `len(query_text) > 1200`，`query_text == long_query` |
| `test_required_catch_up_without_budget_crosses_old_batch_cap_to_target` | 17 批 > 旧 16 批 | `batches_used == 17`，`target_reached is True`，`budget_exhausted is False`，`max_batches is None` |
| `test_rebuild_without_budget_crosses_old_batch_cap_to_target` | 33 批 > 旧 32 批 | `batches_used == 33`，`target_reached is True`，`budget_exhausted is False`，`max_batches is None` |
| `test_open_host_dispatch_memory_catchup_reaches_required_cursor` | dispatch 成功 | `RunStatus.SUCCEEDED`，`len(factory.accepted_snapshots) == 1` |

测试命名清晰，docstring 说明了 "跨旧 batch cap 追到目标" 的意图。每个测试都直接断言旧 cap 被突破后的正确行为。

### 5. compaction_evidence.py 中残留 query truncation helper 的裁决

**PASS（不属于 CAP-R1 当前 PR 必须修复范围）**

直接证据：

`compaction_evidence.py` 中的 `_READABLE_QUERY_TEXT_MAX_CHARS = 1200` 和 `_READABLE_QUERY_TRUNCATED_MARKER` 位于第 47-48 行，被 `_bounded_query_text()`（第 350-364 行）消费。该函数的调用链为：

```text
compaction_evidence.py:_readable_query_text()
  -> compaction_evidence.py:_bounded_query_text()  [有截断]
```

`_readable_query_text()` 被 `collect_selected_compaction_request_evidence_inputs()`（第 231 行）消费，该函数被 `run_input.py` 的 `RunInputBuilder` 导入（run_input.py:61-63, 1435）。

而 CAP-R1 修改的是 `compact_material.py` 中的 pre-dispatch source builder 路径：

```text
compact_material.py:_readable_query_text_from_envelope()
  -> compact_material.py:_bounded_query_text()  [已去截断]
```

两条路径的消费者不同：

| 路径 | 模块 | 消费者 | CAP-R1 状态 |
|---|---|---|---|
| Pre-dispatch source builder | `compact_material.py` | `build_pre_dispatch_compact_material_view` | ✅ 已去截断 |
| Compaction request evidence inputs | `compaction_evidence.py` | `RunInputBuilder` → `CompactionRequest` | 未修改（不同路径） |

`compaction_evidence.py` 的截断作用于 compactor LLM 看到的 evidence query text，不是 pre-dispatch source builder 的 EventLog delta 读取。两者的职责边界不同。

**裁决建议**：`compaction_evidence.py` 的 query truncation 可作为独立 owner 处理。它不影响 CAP-R1 的 correctness 目标（source builder 不截断、不 cap）。如果后续要统一删除所有 query truncation，应由独立 work unit 或 issue 承接，理由是：
1. `compaction_evidence.py` 不在当前 CAP-R1 allowed files 内。
2. 它的截断作用于 compaction request 输入，不是 pre-dispatch source builder。
3. 当前 CAP-R1 scope 用户明确定义为 "compact source builder 不截断 query、不限制 delta event / evidence block"。

### 6. 新硬编码、过度抽象、兼容 wrapper、README 漏更新

**PASS** ✅

- **新硬编码**：无。已删除的常量全部是旧的 correctness cap。保留的 `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1` 和 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1` 有明确 docstring 说明非 correctness 语义。
- **过度抽象**：无。`_opportunistic_memory_projection_catchup_budget` 是对原有 `_memory_projection_catchup_budget` 的简化（去掉了 purpose switch），不是新增抽象层。
- **兼容 wrapper**：无。所有旧常量直接删除，无 re-export 或兼容 alias。
- **README 漏更新**：无。implementation artifact 已记录 README 决策理由（不更新 `dayu/host/README.md` 和 `tests/README.md`），理由成立：无新增公共 API、测试层级或分层边界变更。

## 其它观察

### _CURRENT_INPUT_TRUNCATED_MARKER 保留

`compact_material.py` 中 `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS = 1200` 和 `_CURRENT_INPUT_TRUNCATED_MARKER` 仍然保留（第 87、93 行），用于 current input anchor text 截断（第 2361-2366 行）。这是 current input anchor 的 LLM-facing 文本预算，不是 source builder delta/evidence cap，不在 CAP-R1 范围内。保留正确。

### memory_repair.py budget=None 语义确认

`memory_repair.py` 的 `_run_projection_catchup` 循环（第 329-330 行）：`if budget is not None and batches_used >= budget.max_batches` — 当 `budget=None` 时条件为 `False`，循环追到 `max_event_sequence` 或 runner failure/idle。这是正确的 correctness 语义。

### issues-implementation-control.md 更新

控制文档已同步更新 WU-PROJ-01-CAP-R1 条目（第 204 行），记录 implementation completed、验证结果和 compaction_evidence.py 裁决待 review。WU-PROJ-01 work unit 状态已更新（第 230 行）。更新正确。

## 验证确认

- pytest 125 passed ✅（controller 已复验）
- pyright 0 errors ✅（controller 已复验）
- git diff --check passed ✅（controller 已复验）

## Summary

CAP-R1 实现干净、完整、无 regression 风险。所有旧 correctness cap（256 delta rows、8 evidence blocks、1200 query chars、16 required batches、32 rebuild batches）均已从 source builder 和 dispatch correctness 路径中移除。opportunistic 一批行为保留并有清晰命名和 docstring 边界。新测试直接证明旧 cap 被突破后仍正确工作。唯一 finding 是 `compaction_evidence.py` 的同名 query truncation helper 可由独立 owner 处理，不阻塞当前 PR。
