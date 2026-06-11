# WU-PROJ-01-CAP-R1 Fix Re-Review — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: CAP-R1 fix re-review
- Reviewer: AgentDS
- Date: 2026-06-11
- Branch: `wu-proj-01`
- Scope: 只审查当前未提交 diff 中与 CAP-R1 fix 相关的变更；不修改文件，不 commit/push/PR

## 审查输入

- 设计真源: `docs/host/design.md`
- 总控文档: `docs/host/issues-implementation-control.md`
- Implementation artifact: `docs/reviews/wu-proj-01-cap-r1-implementation-codex.md`
- Controller adjudication: `docs/reviews/wu-proj-01-cap-r1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-proj-01-cap-r1-fix-codex.md`
- Diff: `git diff` (当前未提交变更)
- Controller 复验结果: 173 passed, pyright 0 errors, git diff --check passed

## 审查结论: PASS

CAP-R1 fix 正确完成了 Controller adjudication 要求的全部修复项，无 blocking finding，无非阻塞 finding。

---

## 逐项审查详情

### 1. compaction_evidence.py 是否已删除 _READABLE_QUERY_TEXT_MAX_CHARS / _READABLE_QUERY_TRUNCATED_MARKER 和固定字符截断

**PASS**

直接证据:

- `dayu/host/compaction_evidence.py` 第 204-205 行的 `_READABLE_QUERY_TEXT_MAX_CHARS = 1200` 和 `_READABLE_QUERY_TRUNCATED_MARKER = "\n[truncated_query_text]"` 已删除（diff line 186-187: `-_READABLE_QUERY_TEXT_MAX_CHARS = 1200` / `-_READABLE_QUERY_TRUNCATED_MARKER`）。
- 旧 `_bounded_query_text` 函数（含 `len(normalized) <= _READABLE_QUERY_TEXT_MAX_CHARS` 分支和 `normalized[:keep_chars]` 截断逻辑）已完全替换为 `_normalized_query_text`，只调用 `normalized_material_text(text)`（diff line 236-242）。
- `rg` 全仓库搜索 `_READABLE_QUERY_TEXT_MAX_CHARS` / `_READABLE_QUERY_TRUNCATED_MARKER` / `_bounded_query_text` 均无命中，确认生产代码和测试代码中无残留。

### 2. selected compaction evidence readable_query_text 是否只规范化并完整保留 semantic query / arguments query，仍做空值校验

**PASS**

直接证据:

- `_readable_query_text` (compaction_evidence.py line 283-331) 中 semantic query 路径: `return _normalized_query_text(atoms.semantic_query_text)` — 完整保留，无截断。
- arguments query 路径: `return _normalized_query_text(f"{_READABLE_ARGUMENTS_PREFIX}{canonical_json_dumps(atoms.arguments_json)}")` — 完整保留。
- limited-signal 路径同样进入 `_normalized_query_text`。
- `_normalized_query_text` 委托给 `normalized_material_text`，后者在 `compact_material.py` line 760-774 定义：执行 `" ".join(text.split())` 规范化，规范化后为空时 `raise ValueError("text must be non-empty after normalization")` — 空值校验完整。
- 复用了与 pre-dispatch compact material query 规范化相同的 `normalized_material_text`，语义同源，无重复实现。

### 3. compact_material.py 与 compaction_evidence.py 是否清理 stale _bounded_query_text 命名，且无兼容 alias / wrapper

**PASS**

直接证据:

- `compact_material.py`: `_bounded_query_text` → `_normalized_query_text`（diff line 2192-2200），调用点 `_readable_query_text_from_envelope` 和 `_limited_signal_query_text` 已同步更新。
- `compaction_evidence.py`: `_bounded_query_text` → `_normalized_query_text`（diff line 349-360），调用点 `_readable_query_text` 和 `_limited_signal_query_text` 已同步更新。
- `rg` 全仓库搜索 `_bounded_query_text` 无命中。
- 两个文件中的 `_normalized_query_text` 均为独立私有 helper，无 alias / wrapper / re-export。

### 4. 新测试是否覆盖 selected compaction evidence semantic query 超过旧 1200 字符完整保留

**PASS**

直接证据:

- `tests/host/test_compaction_operation.py::test_evidence_input_semantic_query_text_is_not_truncated` (diff line 605-669): 构造 240+ 段长 query（~2400+ 字符），断言 `query_text == long_query`、`len(query_text) > 1200`、`"[truncated_query_text]" not in query_text`。**通过**。
- `tests/host/test_compact_material.py::test_pre_dispatch_evidence_query_text_is_not_truncated` (diff line 533-591): 同样构造超长 query，断言 `query_text == long_query`、`len(query_text) > 1200`。**通过**。
- 两测试分别覆盖 selected compaction evidence 路径和 pre-dispatch evidence 路径，形成交叉验证。

### 5. 是否误改 ordinary RunInput accepted evidence selection cap 或扩大到非目标

**PASS**

直接证据:

- `dayu/host/run_input.py` 不在本次 diff 变更文件列表中。
- `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8` 仍在 `run_input.py` line 211 原样保留，ordinary RunInput builder 的 `max_evidence_blocks` 参数仍使用该常量（line 1321, 1399）。
- Controller adjudication 已明确裁决该 cap 不属于 CAP-R1 scope（rejected-with-reason），fix 严格遵守了该边界。

### 6. 是否引入反向依赖、硬编码、过度抽象、README 漏更新、类型或测试风险

**PASS** — 逐子项：

**反向依赖**: `compaction_evidence.py` 新增 `from dayu.host.compact_material import normalized_material_text`。该文件此前已从 `compact_material` 导入 `InitialEvidenceMaterial` / `InitialHistoryMaterial`，新增导入属于同层 peer import，不构成跨层反向依赖。`normalized_material_text` 是 `compact_material.py` 的公开函数（无 `_` 前缀），语义为通用文本规范化，适合被同层模块复用。

**硬编码**: 旧 `1200` 字符截断常量已删除；新代码无新增魔法数字或魔法字符串。

**过度抽象**: `_normalized_query_text` 在两端均为薄封装，委托给共享的 `normalized_material_text`。两个文件保留各自私有 helper 是合理的——各自有独立的调用上下文（limited-signal 路径、envelope 校验路径等），遵循了模块间依赖最小化原则，不属于过度抽象。

**README 漏更新**: Fix-codex 已检查 `dayu/host/README.md` 和 `tests/README.md` 并记录不更新理由：本次未改变 Host public API、公共契约、状态机、事件流、测试分层或测试运行入口。该判断合理，无需额外更新。

**类型风险**: `normalized_material_text` 有完整类型标注（`str -> str`），新增的 `_normalized_query_text` 继承相同类型语义。`compaction_evidence.py` 的 `_normalized_query_text` 从原来的手动规范化改为委托 `normalized_material_text`，额外获得了原实现缺少的 `TypeError` 守卫（`if not isinstance(text, str)`），类型安全性略微提升。pyright 0 errors 确认无类型回归。

**测试风险**: 新增 6 个测试（2 个 query text 截断回归 + 2 个 delta/evidence cap 回归 + 2 个 projection batch cap 回归），加上原有测试，173 passed 全覆盖。

---

## 附加检查

### open_host 测试变更验证

`tests/host/test_open_host_runtime.py` 的 `test_open_host_dispatch_memory_catchup_reaches_required_cursor`（原 `test_open_host_dispatch_memory_catchup_budget_exhausted_blocks_worker_accept`）变更逻辑正确：移除旧的 monkeypatch `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES` → 1 的测试，改为验证 `budget=None` 时 dispatch required catch-up 追到 required cursor 后接受 worker（`RunStatus.SUCCEEDED`）。这与 `dispatch.py` 中将 required/rebuild catch-up 改为 `budget=None` 的设计一致。

### 已删除常量最终确认

以下 8 个常量已从生产代码中完全移除，`rg` 确认无残留：

| 常量 | 原位置 |
|---|---|
| `_READABLE_QUERY_TEXT_MAX_CHARS` | compact_material.py |
| `_READABLE_QUERY_TRUNCATED_MARKER` | compact_material.py |
| `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS` | compact_material.py |
| `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS` | compact_material.py |
| `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES` | dispatch.py |
| `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES` | dispatch.py |
| `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES` | dispatch.py |
| `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES` | open_host.py |

保留并重命名的常量：

| 新常量 | 用途 | 语义限定 |
|---|---|---|
| `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1` | compact 后轻量推进 | 非 correctness |
| `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1` | commit 后轻量推进 | 非 correctness |

### _memory_projection_catchup_budget → _opportunistic_memory_projection_catchup_budget

`dispatch.py` 中的函数重命名语义准确：原函数按 `purpose` 分发不同 correctness 预算，现函数只构造 opportunistic one-batch 预算，不再接受 `purpose` 参数，内部直接使用 `MemoryProjectionRepairPurpose.BEST_EFFORT_AFTER_COMMIT`。required / rebuild catch-up 路径改为直接传 `budget=None`，语义清晰。

---

## 剩余风险

- `WU-PROJ-01-S3-R1`（dispatch before-worker catch-up happy path 独立集成测试）与 `WU-PROJ-01-S4-R1`（reactive compact failure fallback 测试 flaky 修复）仍为 open，不在 CAP-R1 scope，需后续 gate 独立处理。
- 本次 fix 不涉及 ordinary RunInput accepted evidence selection cap（`_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8`）的重设计，该常量仍在 `run_input.py` 中保持原有语义。

---

## 验证摘要

| 检查项 | 结果 |
|---|---|
| `pytest` 全量（5 文件, 173 tests） | passed |
| `pyright` | 0 errors |
| `git diff --check` | passed |
| 新增 CAP-R1 专项测试（6 tests） | passed |
| stale 常量/命名残留搜索 | 0 hits |
| 反向依赖检查 | 无新增 |
| ordinary RunInput cap 误改检查 | 未触及 |
