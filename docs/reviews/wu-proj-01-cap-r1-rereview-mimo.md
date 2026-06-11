# WU-PROJ-01-CAP-R1 Re-Review — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Review gate: CAP-R1 fix re-review
- Agent: AgentMiMo
- Date: 2026-06-11
- Branch: `wu-proj-01`
- Scope: 只审查当前未提交 diff 中与 CAP-R1 fix 相关的变更；不修改任何文件。

## 审查依据

- 设计真源：`docs/host/design.md`
- 总控文档：`docs/host/issues-implementation-control.md`
- 必读 artifacts：
  - `docs/reviews/wu-proj-01-cap-r1-implementation-codex.md`
  - `docs/reviews/wu-proj-01-cap-r1-code-review-controller-adjudication.md`
  - `docs/reviews/wu-proj-01-cap-r1-fix-codex.md`

## 逐项审查结果

### 1. `compaction_evidence.py` 是否已删除 `_READABLE_QUERY_TEXT_MAX_CHARS` / `_READABLE_QUERY_TRUNCATED_MARKER` 和固定字符截断

**PASS**

`rg` 确认 `dayu/host/` 生产代码中不再存在 `_READABLE_QUERY_TEXT_MAX_CHARS`、`_READABLE_QUERY_TRUNCATED_MARKER` 或 `_bounded_query_text`。

diff 显示：
- `compaction_evidence.py` 删除了 `_READABLE_QUERY_TEXT_MAX_CHARS = 1200` 和 `_READABLE_QUERY_TRUNCATED_MARKER = "\n[truncated_query_text]"`。
- `_bounded_query_text` 函数体从 `normalized = " ".join(text.split())` + 长度判断 + 截断拼接 marker，改为直接 `return normalized_material_text(text)`。
- `compact_material.py` 同步删除了同名常量，`_bounded_query_text` 同样改为 `_normalized_query_text` 直接调用 `normalized_material_text`。

### 2. selected compaction evidence readable_query_text 是否只规范化并完整保留 semantic query / arguments query，仍做空值校验

**PASS**

- `compaction_evidence.py` 的 `_readable_query_text` 中，semantic query 分支和 arguments fallback 分支均调用 `_normalized_query_text`，不再截断。
- `_normalized_query_text` 委托给 `compact_material.normalized_material_text`，该函数做去首尾空白 + 折叠连续空白 + 空值 `ValueError`，不做长度截断。
- `compaction_evidence.py` 正确 import 了 `normalized_material_text`（从 `dayu.host.compact_material`），规范化语义与 `compact_material.py` 同源。

### 3. `compact_material.py` 与 `compaction_evidence.py` 是否清理 stale `_bounded_query_text` 命名，且无兼容 alias / wrapper

**PASS**

- `rg` 确认 `_bounded_query_text` 在 `dayu/host/` 中零匹配。
- 两个文件均改为 `_normalized_query_text`，无兼容 alias、无 re-export、无 wrapper。
- 调用点（`_readable_query_text_from_envelope`、`_limited_signal_query_text`、`_readable_query_text`）全部同步更新。

### 4. 新测试是否覆盖 selected compaction evidence semantic query 超过旧 1200 字符完整保留

**PASS**

- `tests/host/test_compaction_operation.py` 新增 `test_evidence_input_semantic_query_text_is_not_truncated`：
  - 构造 `long_query = " ".join(("读取 MSFT FY2025 年报收入分部说明", *("segment" for _ in range(240))))`。
  - 断言 `query_text == long_query`、`len(query_text) > 1200`、`"[truncated_query_text]" not in query_text`。
- `tests/host/test_compact_material.py` 新增 `test_pre_dispatch_evidence_query_text_is_not_truncated`：
  - 构造 `long_query = " ".join(("long-query", *("segment" for _ in range(240))))`。
  - 断言 `query_text == long_query`、`len(query_text) > 1200`。

两个测试分别覆盖 `compaction_evidence.py`（selected evidence 路径）和 `compact_material.py`（pre-dispatch evidence 路径），确保两条 LLM-facing query projection 路径均不截断。

### 5. 是否误改 ordinary RunInput accepted evidence selection cap 或扩大到非目标

**PASS**

- `rg` 确认 `dayu/host/run_input.py` 中 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8` 未被修改。
- diff 中无 `run_input.py` 变更。
- Controller adjudication 已明确拒绝扩大到该路径（CAP-R1-F2 rejected-with-reason）。

### 6. 是否引入反向依赖、硬编码、过度抽象、README 漏更新、类型或测试风险

**PASS**

- **反向依赖**：`compaction_evidence.py` import `compact_material.normalized_material_text`，这是同层（`dayu/host/`）内的水平复用，不构成反向依赖。
- **硬编码**：已删除所有魔法数字常量（1200、256、8、16、32）；保留的 `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1` 和 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1` 命名自解释且 docstring 明确限定为非 correctness opportunistic 行为。
- **过度抽象**：`_normalized_query_text` 只是 `normalized_material_text` 的单行委托，用于在 `compaction_evidence.py` 中保持语义一致；不是过度抽象。
- **README 漏更新**：Fix Codex 已确认 `dayu/host/README.md` 和 `tests/README.md` 无需更新；本次 re-review 确认该判断正确——无 public API、公共契约或测试分层变更。
- **类型风险**：Controller 已复验 pyright 0 errors；diff 中无类型签名变更。
- **测试风险**：Controller 已复验 173 passed；新增测试覆盖了两条 query projection 路径和两条 memory projection correctness 路径。

## 其它观察

### dispatch.py / open_host.py 变更确认

- `dispatch.py`：required-before-dispatch catch-up 和 rebuild-before-dispatch 均改为 `budget=None`，不再有 `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES` / `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES` 预算限制。after-compact opportunistic 保留 `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1`。
- `open_host.py`：after-commit opportunistic 重命名为 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1`，docstring 明确说明不参与 correctness catch-up。

### 测试覆盖确认

- `test_required_catch_up_without_budget_crosses_old_batch_cap_to_target`：17 批无 budget 追到目标。
- `test_rebuild_without_budget_crosses_old_batch_cap_to_target`：33 批无 budget 追到目标。
- `test_open_host_dispatch_memory_catchup_reaches_required_cursor`：从 FAILED 改为 SUCCEEDED，证明 required catch-up 不再被 batch cap 阻塞。

### issues-implementation-control.md 更新确认

- CAP-R1 residual risk 条目已更新为 fix completed，记录了 artifacts 和 Controller 复验结果。
- Work Units 表 WU-PROJ-01 状态已更新。

## 结论

**PASS**

无 blocking findings。无非阻塞 findings。

CAP-R1 fix 的所有 accepted findings 已正确实现：`compaction_evidence.py` 的固定字符截断已删除，`_bounded_query_text` 命名已清理为 `_normalized_query_text`，两条 LLM-facing query projection 路径均只做规范化不做截断，新增测试覆盖了超旧 1200 字符完整保留场景，ordinary RunInput cap 未被误改，memory projection correctness path 已改为 `budget=None`。Controller 复验的 173 passed、pyright 0 errors、git diff --check passed 均可信。
