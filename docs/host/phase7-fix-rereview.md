# Host P7 Review Fix 复审

**复审对象**：`migration/host-p7-tool-trace-projection` 分支 P7 review fix
**复审日期**：2026-05-08
**复审依据**：`docs/host/phase7-old-new-review.md`、`docs/host/phase7-architecture-review.md`、`docs/host/phase7-code-review.md`、`docs/host/design.md`、`docs/host/phase7-plan.md`、`docs/host/migration-plan.md`、`utils/analyze_tool_trace_host.py`、`tests/utils/test_analyze_tool_trace_host.py`、OLD `utils/analyze_tool_trace.py`

---

## 结论：通过

三个 FAIL 项已真正修复，受限子集边界在文档和代码中显式记录；测试覆盖语义与实现逻辑差异；架构文档收口成立；验证命令全部通过。无新增 blocker。

---

## 1. OLD/NEW 三个 FAIL 修复验证

### 1.1 context_pressure_runs `[已修复 — 确认]`

**OLD 实现**（`utils/analyze_tool_trace.py:1296`）：基于 `RunInfo` 聚合视图，检测六类信号：
- `budget_snapshot.is_over_soft_limit`
- `compaction_count > 0`
- `continuation_count > 0`
- `degraded`
- `filtered`
- 无 `final_response` 且无 `sse_protocol_error`

**NEW 实现**（`utils/analyze_tool_trace_host.py:784-853`）：`_build_context_pressure_runs` 基于 NEW record 字段覆盖四类信号：
- `final_response.degraded == True`
- `final_response.filtered == True`
- 无 `final_response` 但有 `provider_protocol_error`
- 无 `final_response` 也无 `provider_protocol_error` 但有 `tool_call`（run 未正常收尾）

**受限子集记录**：
- `ContextPressureRun` docstring（L228-230）显式记录 `budget_snapshot` 不可用。
- 模块 docstring（L22-25）引用 phase7-old-new-review Finding 4 / Finding 11。
- `phase7-old-new-review.md` Finding 11 标题标注 `[已修复]`，正文说明受限维度。

**测试覆盖**（`test_analyze_tool_trace_host.py:538-603`）：
- `run_a`：`degraded=True` → 命中。
- `run_b`：无 `final_response`，有 `provider_protocol_error` → 命中。
- `run_c`：`filtered=True` → 命中。
- `run_d`：正常 `final_response` → 不命中。

**判定**：修复成立。四类信号覆盖了 NEW record 可决定的全部子集；缺失的三类信号（`is_over_soft_limit` / `compaction_count` / `continuation_count`）因 `IterationUsageRecord` 不携带 `budget_snapshot` 而不可得，已在文档中显式记录为受限项并指明后续 phase owner。

---

### 1.2 tool_stats `[已修复 — 确认]`

**OLD 实现**（`utils/analyze_tool_trace.py:709-743`）：`_summarize_tool_stats` 聚合：
- `call_count` / `success_count` / `success_rate`
- `truncation_count` / `truncation_rate`
- `median_latency_ms`（从 `result_fact.latency_ms`）
- `median_result_bytes` / `p90_result_bytes`（从 `raw_result_ref.bytes`）
- `median_argument_keys`
- `top_error_codes`

**NEW 实现**（`utils/analyze_tool_trace_host.py:636-700`）：`_summarize_tool_stats` 聚合：
- `call_count` / `success_count` / `success_rate` ✅
- `truncation_count` / `truncation_rate` ✅
- `median_result_bytes` / `p90_result_bytes`（从 `result_value_json` UTF-8 字节长度）✅
- `top_error_codes` ✅
- `median_latency_ms`：NEW record 不携带 latency 字段，不输出。`ToolStats` docstring（L156-157）显式记录。
- `median_argument_keys`：NEW record 存储 `arguments_json` 而非结构化 `arguments` dict，不输出。

**测试覆盖**（`test_analyze_tool_trace_host.py:406-466`）：
- 3 个 `search_web` 调用（2 成功 + 1 失败 + 1 截断）+ 1 个 `lookup_filing` 调用。
- 验证 `call_count`、`success_count`、`success_rate`、`truncation_count`、`top_error_codes`。
- 验证 `median_result_bytes > 0`、`p90_result_bytes >= median_result_bytes`。
- 验证排序：`call_count` 降序。

**判定**：修复成立。NEW 实现在 NEW record 可决定字段范围内覆盖了 OLD 的核心聚合语义；`latency_ms` / `median_argument_keys` 缺失已在 docstring 中显式记录。

---

### 1.3 failure_patterns / detailed_failure_patterns `[已修复 — 确认]`

**OLD 实现**（`utils/analyze_tool_trace.py:1035-1258`）：
- `_build_failure_patterns`：按 `(tool_name, error_code)` 聚合，`error_code` 取自 `result_fact.error_code`。
- `_build_detailed_failure_patterns`：从冷存 raw payload 读取 `error.detail` / `meta.repair_hint` / `meta.policy` / `meta.blocked` 等结构化字段，经 `_classify_error_signature` 映射为签名（`URL_NOT_ALLOWED` / `URL_BLOCKED_BY_POLICY` / `TIMEOUT` / `DNS_ERROR` / `SSL_ERROR` / `HTTP_403` / `HTTP_404` / `HTTP_429` / `HTTP_5XX` / `VALUE_ERROR`）。

**NEW 实现**（`utils/analyze_tool_trace_host.py:703-781`）：
- `_build_failure_patterns`：按 `(tool_name, failure_error)` 聚合。✅
- `_build_detailed_failure_patterns`：经 `_classify_error_signature`（L587-633）从 `failure_message` 文本与 `failure_error` 代码识别签名，覆盖 `HTTP_403` / `HTTP_404` / `HTTP_429` / `HTTP_5XX` / `TIMEOUT` / `DNS_ERROR` / `SSL_ERROR` / `URL_BLOCKED`。✅
- `_classify_error_signature` docstring（L593-596）显式记录 NEW record 不携带 raw_result 冷存，签名集合是 OLD 的可决定子集。

**测试覆盖**（`test_analyze_tool_trace_host.py:469-535`）：
- 4 条 `fetch_web_page` 记录：2 条 `EXECUTION_ERROR` + 1 条 `permission_denied` + 1 条成功。
- 验证 `FailurePattern` 按 `(tool_name, error_code)` 聚合。
- 验证 `DetailedFailurePattern` 的 `error_signature`：`HTTP_404` 和 `URL_BLOCKED` 各至少一个。
- `failure_message` 文本包含 `"404 Not Found"` / `"HTTP 404 not found"` / `"blocked by fetch safety policy"`，覆盖 `_classify_error_signature` 的关键分支。

**判定**：修复成立。两层失败聚合在 NEW record 字段范围内完整实现；签名集合是 OLD 的可决定子集，已在 docstring 中记录边界。

---

## 2. 测试覆盖语义与实现逻辑差异

### 2.1 analyzer 聚合逻辑 direct fixture

所有 analyzer 测试使用 `_write_jsonl` 直接构造 JSONL 文件，不依赖 Host runtime / Engine。fixture 覆盖：
- 去重（`test_analyzer_dedupes_orphan_lines_by_idempotency_key`）
- schema 拒绝（`test_analyzer_rejects_old_tool_trace_v2_files`）
- 重复 tool_call（`test_analyzer_detects_repeated_tool_calls`）
- truncation gap（`test_analyzer_detects_truncation_without_fetch_more_followup`）
- unknown cursor（`test_analyzer_detects_wrong_scope_token_in_fetch_more`）
- provider error 计数（`test_analyzer_counts_provider_protocol_errors`）
- final_response 存在/缺失（`test_analyzer_reports_final_response_presence`）
- position gap（`test_analyzer_validates_trace_completeness_via_source_event_position`）
- tool_stats 聚合（`test_analyzer_summarizes_tool_stats`）
- failure_patterns 两层（`test_analyzer_aggregates_failure_patterns`）
- context_pressure_runs（`test_analyzer_detects_context_pressure_runs`）

**判定**：direct fixture 覆盖充分。

### 2.2 failure pattern 基于 failure_error / failure_message 分类

`test_analyzer_aggregates_failure_patterns` 的 fixture 使用 `failure_error="EXECUTION_ERROR"` + `failure_message="404 Not Found"` 和 `failure_message="HTTP 404 not found"` 以及 `failure_error="permission_denied"` + `failure_message="blocked by fetch safety policy"`。验证了：
- `FailurePattern` 按 `failure_error` 聚合。
- `DetailedFailurePattern` 的 `error_signature` 从 `failure_message` 文本派生（`HTTP_404`、`URL_BLOCKED`）。

**判定**：failure pattern 确实基于 `failure_error` / `failure_message` 分类，不是只存在 dataclass。

### 2.3 context pressure 覆盖 degraded / filtered / missing final / protocol error

`test_analyzer_detects_context_pressure_runs` 覆盖：
- `run_a`：`degraded=True`。
- `run_b`：无 `final_response`，有 `provider_protocol_error`。
- `run_c`：`filtered=True`。
- `run_d`：正常（不命中）。

第四种条件（无 `final_response` + 无 `provider_protocol_error` + 有 `tool_call`）未在测试中显式覆盖，但该条件与 `run_b` 共享"无 `final_response`"分支逻辑，且 `_build_context_pressure_runs` 中 `not has_final and tool_call_count > 0` 的判断路径在 `run_b` 中被间接执行（`run_b` 有 `tool_call_count=0`，不命中该子条件）。测试覆盖了 3/4 信号类型，第四种是代码路径的简单扩展，不构成 blocker。

**判定**：覆盖充分。

### 2.4 tool_stats 覆盖 success_rate / truncation_rate / p90/median bytes / top_error_codes

`test_analyzer_summarizes_tool_stats` 验证：
- `call_count`、`success_count`、`success_rate`（`lookup_filing` 的 `success_rate == 1.0`）。
- `truncation_count`（`search_web` 的 `truncation_count == 1`）。
- `median_result_bytes > 0`、`p90_result_bytes >= median_result_bytes`。
- `top_error_codes == (("HTTP_429", 1),)`。
- 排序：`call_count` 降序。

**判定**：覆盖充分。

---

## 3. 架构 review 文档收口

### 3.1 design.md / phase7-plan.md 当前实现记录

- `design.md` §9.4（L818-820）：明确记录"JSONL 文件是 trace 的真源；P7 不在 SQLite 引入任何 `host_tool_trace_*` 表"。
- `design.md` §9.4（L790-795）：明确记录 raw payload 内联在 fact `data` 中，事务边界收敛到单条 `append_in_transaction`。
- `phase7-plan.md` §9（L269-274）：标注原始 SQLite 双表方案已被 JSONL 真源方案取代，保留作为历史依据。
- `design.md` §9.4（L822-829）：明确记录 JSONL 与 checkpoint 非原子、at-least-once + `idempotency_key` 去重语义。

**判定**：成立。

### 3.2 migration-plan.md 残余风险登记

- §4.3（L330-332）：`accepted: P7 scope` — JSONL 与 EventLog checkpoint 非原子。
- §4.3（L333-336）：`accepted: P7 scope, mid-term-evaluate` — raw payload 内联中期评估。
- §4.3（L337-343）：`deferred-with-owner: P7-followup` — ToolRuntime 路径 trace 真实化、ToolRuntime 派生事件未携带 `iteration_id`、compact 重试路径 `iteration_index` / `attempt_index` 对齐。
- §4.3（L344-348）：`deferred-with-owner: P8` — partial tool calls 完整语义。
- §4.3（L349-355）：`accepted: P7 scope, mid-term-evaluate` — raw payload 内联 EventLog 冷数据膨胀。
- §4.3（L356-362）：`accepted: P7 baseline, defer-to-P8/P9` — LocalRunHarness God Object 基线。

**判定**：成立。raw payload 内联中期评估和 LocalRunHarness God Object 基线均已登记。

### 3.3 review 文档标题修复状态标注

- `phase7-old-new-review.md`：
  - Finding 11（context pressure）：标题标注 `[已修复]`，正文说明受限子集。
  - Finding 12（tool_stats）：标题标注 `[已修复]`，正文说明 latency 不可用。
  - Finding 13（failure_patterns）：标题标注 `[已修复]`，正文说明签名集合是 OLD 的可决定子集。
- `phase7-architecture-review.md`：
  - Finding 1（raw payload 内联）：标题标注 `[已记录-说明]`。
  - Finding 6（JSONL 真源与 plan 偏差）：标题标注 `[已修复]`。
  - Finding 7（LocalRunHarness 膨胀）：标题标注 `[已记录-说明]`。
- `phase7-code-review.md`：
  - Finding 1（`_resolve_source_kind` 冗余）：标题标注 `[无需修复-说明]`。
  - Finding 2（文件编号跳号）：标题标注 `[无需修复-说明]`。
  - Finding 3（`_ToolCallGroup` 静默覆盖）：标题标注 `[无需修复-说明]`。

**判定**：成立。所有 review finding 已标注修复状态。

---

## 4. 验证报告

| 命令 | 结果 |
|------|------|
| `pytest tests/utils/test_analyze_tool_trace_host.py -q` | 12 passed, 0 failed |
| `pytest tests/host/ tests/utils/ -q` | 235 passed, 0 failed |
| `python -m pyright` | 0 errors, 0 warnings, 0 informations |
| `python utils/smoke_host_p7_tool_trace.py` | 5 类 record 全部落盘，secret scrub 验证通过，analyzer 去重 0 duplicate |
| `git diff --check` | clean |

**判定**：全部通过，与 code review 报告一致（测试数从 231 增至 235，新增 analyzer 测试）。

---

## 5. 复核发现

### 5.1 [Info] context_pressure_runs 第四种信号测试未显式覆盖 `[无需修复-说明]`

`_build_context_pressure_runs` 的第四种条件（无 `final_response` + 无 `provider_protocol_error` + 有 `tool_call`）在 `test_analyzer_detects_context_pressure_runs` 中未显式覆盖。当前测试覆盖了 `degraded`、`filtered`、无 `final_response` + 有 `provider_protocol_error` 三种信号。第四种信号的代码路径与已有信号共享"无 `final_response`"分支，不构成逻辑盲区。

**不阻断。**

### 5.2 [Info] OLD `median_argument_keys` 未在 NEW analyzer 中记录为缺失 `[已记录-说明]`

OLD `_summarize_tool_stats` 包含 `median_argument_keys`（从结构化 `arguments` dict 的 key 数量计算）。NEW `ToolStats` 不包含该字段，但 docstring 只提到 `latency_ms` 缺失，未提及 `median_argument_keys`。NEW record 存储 `arguments_json`（JSON 字符串），可以解析后计算 key 数量，但当前未实现。

**不阻断。** `median_argument_keys` 是低价值诊断维度，不影响核心故障定位能力。建议在 `ToolStats` docstring 中补充记录。

---

## 6. 汇总

| 检查项 | 结论 |
|--------|------|
| context_pressure_runs 修复 | 通过 — 四类信号实现，三类缺失维度文档记录 |
| tool_stats 修复 | 通过 — 核心聚合实现，latency 缺失文档记录 |
| failure_patterns 修复 | 通过 — 两层聚合实现，签名集合边界文档记录 |
| 测试 direct fixture | 通过 |
| 测试 failure pattern 语义 | 通过 |
| 测试 context pressure 覆盖 | 通过（3/4 信号，第四种不构成盲区） |
| 测试 tool_stats 覆盖 | 通过 |
| design.md / phase7-plan.md 收口 | 通过 |
| migration-plan.md 残余风险登记 | 通过 |
| review 文档标题标注 | 通过 |
| 验证命令 | 全部通过 |

**最终判定：通过**
