# WU-OBS-00 Slice 2 Implementation Re-Review

## Scope

- Mode: current changes
- Branch: `work/wu-obs-00`
- Base: `126daa02`
- Output file: `docs/reviews/wu-obs-00-slice-2-re-review-20260724-143647.md`
- Included scope:
  - `dayu/host/__init__.py` (modified — S2 public exports)
  - `dayu/host/tool_trace_analysis_contracts.py` (modified — S2 report/finding/limitation contracts)
  - `dayu/host/tool_trace_analysis.py` (new — public orchestration + JSON/Markdown renderer)
  - `dayu/host/tool_trace_analysis_rules.py` (new — deterministic aggregation + Host/Tool rules)
  - `tests/host/test_tool_trace_analysis.py` (new — orchestration/renderer tests)
  - `tests/host/test_tool_trace_analysis_rules.py` (new — rule-level tests)
  - `tests/host/test_package_exports.py` (modified — S2 export allowlist)
- Excluded scope: `docs/host/issues-implementation-control.md`, `docs/reviews/wu-obs-00-slice-2-*` (controller-owned artifacts, not implementation findings)
- Parallel review coverage: 无

## Review Context

本 re-review 验证 Controller 已 accepted 的三项 finding（CTRL-S2-IMPL-01/02/03）是否确实关闭，且 fix 未引入新回归。Controller 已拒绝的 Markdown 索引重构（DS Finding 4）和 helper 公开化（DS Finding 5）不在本 review 范围内，除非有新证据证明其必要性。

## CTRL-S2-IMPL-01 Closure Verification

**Finding**: `dayu.host.tool_trace_analysis` 缺少 `__all__`，导致内部实现符号泄漏为模块公共表面。

**Fix Verification**: ✅ 已修复

- `dayu/host/tool_trace_analysis.py:33-37` 定义了精确的静态 `__all__`，只包含三个 public functions：
  - `analyze_tool_trace`
  - `render_tool_trace_analysis_markdown`
  - `tool_trace_analysis_report_to_json`
- `tests/host/test_tool_trace_analysis.py:125-136` 的 `test_analysis_module_owner_exports_only_three_public_functions` 测试：
  - 断言 `__all__` 精确包含上述三个函数
  - 明确断言 `build_tool_trace_analysis_report` 和 `load_tool_trace_analysis_input` 不在 `__all__` 中
- 未增加 wrapper、alias、动态 export 或 package-root 新表面

**Conclusion**: Module public surface 已由 owner 明确声明，internal builder/loader 不在其中。

## CTRL-S2-IMPL-02 Closure Verification

**Finding**: `_public_payload_measure` 非 COLD_LINE 证据的来源路径与 kind 语义不一致，resolved measure 借用了 cold path/line。

**Fix Verification**: ✅ 已修复

- `dayu/host/tool_trace_analysis_rules.py:1016-1096` 的 `_public_payload_measure` 函数：
  - `COLD_LINE` 分支（第 1028-1052 行）：从 `dataset.cold_records` 匹配 cold record，使用 `_record_evidence` 构造 evidence，`measurement_source=COLD_JSONL_RECORD_BYTES`
  - 非 `COLD_LINE` 分支（第 1053-1088 行）：
    - 严格要求 `dataset.hot_store_available=True` 且 `hot_db_path is not None`
    - 从 `dataset.hot_rows` 按 `event_id` 和 `event_sequence` 匹配 hot row owner
    - 直接构造 `ToolTraceEvidence(kind=RESOLVED_PAYLOAD, source_path=hot_db_path, line_number=None)`
    - `measurement_source=RESOLVED_PAYLOAD_BYTES`
    - 缺 hot owner facts 时直接 `ValueError` fail closed，无 requested/cold fallback

- `tests/host/test_tool_trace_analysis_rules.py:701-770` 的 `test_same_event_cold_and_resolved_measures_keep_distinct_owner_evidence` 测试：
  - 同一 `event_id` 同时具有 cold-line measure 和 tool-result resolved measure
  - 逐字段断言 kind/path/line/measurement source 分离：
    - cold measure: `kind=COLD_LINE`, `source_path=cold_jsonl_path`, `line_number=1`, `measurement_source=COLD_JSONL_RECORD_BYTES`
    - resolved measure: `kind=RESOLVED_PAYLOAD`, `source_path=hot_db_path`, `line_number=None`, `measurement_source=RESOLVED_PAYLOAD_BYTES`

- `tests/host/test_tool_trace_analysis_rules.py:773-801` 的 `test_resolved_measure_without_hot_owner_facts_is_rejected` 测试：
  - synthetic resolved measure 缺 hot store 时直接 `ValueError` fail closed

**Conclusion**: Cold-line 与 resolved-payload measure 的 evidence identity 完全分离，non-cold measure 严格要求 available hot store 和 matching hot row。

## CTRL-S2-IMPL-03 Closure Verification

**Finding**: hot-only `cold_lock_path` 文档承诺漂移，contract docstring 把 expected path 描述为"实际使用的 lock path"。

**Fix Verification**: ✅ 已修复

- `dayu/host/tool_trace_analysis_contracts.py:550-552` 的 `ToolTraceAnalysisInputSummary` docstring 已更新：
  ```
  :param cold_lock_path: Host owner 从 expected ``cold_jsonl_path`` 唯一派生的
      expected lock path；只有 ``capabilities.cold=true`` 才表示本次实际获取
      该路径的锁并读取 cold snapshot。
  ```

- `dayu/host/tool_trace_analysis.py:404-411` 的 Markdown 渲染：
  - 显示 "expected cold lock path（由 Host owner 从 expected cold JSONL 路径唯一派生）"
  - 显示 "cold capability：`{value}`；只有 `true` 表示本次实际获取上述 lock 并读取 cold snapshot"

- `tests/host/test_tool_trace_analysis_rules.py:804-828` 的 `test_hot_only_summary_keeps_expected_lock_path_without_claiming_lock_use` 测试：
  - hot-only 时 `cold_lock_path` 稳定非空（与 `source.cold_jsonl_path.with_name(... + ".lock")` 一致）
  - `capabilities.cold=False`
  - Markdown 包含 "expected cold lock path"
  - Markdown 包含 "cold capability：`false`"
  - Markdown 包含 "只有 `true` 表示本次实际获取上述 lock"

**Conclusion**: Contract 与 Markdown 明确该字段是 expected owner-derived path，只有 `capabilities.cold=true` 才证明本次实际获取锁并读取 cold snapshot。

## Fix Regression Check

### Correctness

- 三个 accepted finding 的 fix 均发生在正确 owner boundary：
  - CTRL-S2-IMPL-01: `dayu.host.tool_trace_analysis` module `__all__`
  - CTRL-S2-IMPL-02: `dayu.host.tool_trace_analysis_rules._public_payload_measure`
  - CTRL-S2-IMPL-03: `dayu.host.tool_trace_analysis_contracts.ToolTraceAnalysisInputSummary` docstring + `dayu.host.tool_trace_analysis._render_input_and_coverage` Markdown
- 未修改 producer、schema、CLI、provider/vendor
- 未实施 Controller 拒绝的 Markdown 索引重构或 helper 公开化

### Strict Invariant

- Frozen dataclass 字段类型未改变（`cold_lock_path` 保持 `Path`，非 `Path | None`）
- JSON key/shape 与 `_input_summary` owner-derived path 行为保持不变
- `__post_init__` 校验逻辑未改变

### Fixture Realism

- 测试 fixture 改为显式 workspace hot owner facts
- 新增反例测试使用真实 owner 事件（同一 `event_id` 同时具有 cold-line 和 resolved measure）

### Public Schema

- Package exports 未扩大
- Module `__all__` 已收紧
- Report schema 未改变

### Determinism

- JSON/Markdown renderer 行为未改变
- Finding ordering/id assignment 未改变

### Scope/Forbidden Changes

- 未修改 producer、schema、CLI、provider/vendor
- 未修改 `docs/host/issues-implementation-control.md`、Controller adjudication 或两路 review artifacts
- 未 commit、push、创建/修改 PR 或 Issue

## Validation

### Focused Tests

```bash
pytest -q tests/host/test_tool_trace_analysis.py tests/host/test_tool_trace_analysis_rules.py tests/host/test_package_exports.py
```

结果：`37 passed in 0.36s`

### Full Host Tests

```bash
pytest -q tests/host
```

结果：`2318 passed, 2 skipped, 6 deselected in 70.19s`

### Targeted Pyright

```bash
python -m pyright dayu/host/tool_trace_analysis.py dayu/host/tool_trace_analysis_rules.py dayu/host/tool_trace_analysis_contracts.py tests/host/test_tool_trace_analysis.py tests/host/test_tool_trace_analysis_rules.py
```

结果：`0 errors, 0 warnings, 0 informations`

### Full Pyright

```bash
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

### Branch Coverage

| File | Branch | BrPart | Cover |
|---|---:|---:|---:|
| `dayu/host/__init__.py` | 0 | 0 | 100% |
| `dayu/host/tool_trace_analysis.py` | 34 | 0 | 100% |
| `dayu/host/tool_trace_analysis_contracts.py` | 168 | 49 | 80% |
| `dayu/host/tool_trace_analysis_rules.py` | 142 | 26 | 91% |

所有 Slice 2 production diff 文件均达到逐文件 `>=80%`。

### Ruff

```bash
ruff check dayu/host/tool_trace_analysis.py dayu/host/tool_trace_analysis_rules.py dayu/host/tool_trace_analysis_contracts.py tests/host/test_tool_trace_analysis.py tests/host/test_tool_trace_analysis_rules.py
```

结果：`All checks passed!`

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- Engine/provider/protocol rules 和 vendor debugging block instances 仍按 accepted plan 归属 Slice 3；不是本 re-review 未覆盖缺陷。
- `tool_trace_analysis_contracts.py` branch coverage 在 80% 边界；部分 `__post_init__` 类型错误分支缺少直接单元测试。这些是防御性 raise，低风险。
- No real workspace smoke test for S2 rules (S1 live workspace remediation produced clean data with zero findings/limitations, which is expected for a healthy trace). S3 integration with real workspace data will exercise the full rule chain.

## Conclusion

**PASS**。三项 accepted finding（CTRL-S2-IMPL-01/02/03）均已关闭，fix 未引入新回归。Controller 拒绝的 Markdown 索引重构和 helper 公开化均未实施。所有验证通过。
