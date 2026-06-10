# WU-TOOLS-01-F03 Slice 2 Code Review — AgentMiMo

## Review Target

- **Gate**: implementation review
- **Changed files**:
  - `utils/smoke_web_ci.py`（新增）
  - `tests/tools/web/test_smoke_web_ci.py`（新增）
  - `docs/reviews/wu-tools-01-f03-implementation-slice2-codex.md`（新增）
- **Approved plan**: `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`（Slice 2）
- **Prior slice context**: Slice 1 implementation + fix gate re-review artifacts
- **Date**: 2026-06-10

---

## Scope Boundary 验证

### 是否严格实现 Slice 2，不越界

| 边界检查 | 结论 |
|---|---|
| Slice 3 local HTTP server | **未越界**。`_execute_smoke()` 始终传 `local_cases=()`，无 server 启动逻辑。docstring 和 Slice 2 implementation artifact 均明确说明 local fixture 由 Slice 3 接入。 |
| diagnose_web_access 生产代码 | **未越界**。未修改 `utils/diagnose_web_access.py`。 |
| production Web tools / Host / Engine / ToolRuntime | **未越界**。无 import 越界，`main()` 只调用 `utils.diagnose_web_access` 子进程。 |
| Slice 4 全量 corpus | **未越界**。`--external-url-file` 默认不运行；运行时按 `--external-limit` 限制。 |

### 未 opt-in 行为

**符合要求**。`main()` 在 `not opted_in` 路径调用 `_skipped_summary()`，该函数：
- 返回 `status="skipped"`、`exit_code=0`。
- 不调用 `_execute_smoke()`，不启动 server，不调用 diagnostics runner。
- summary 含 `not_opted_in` skip item，reason 明确声明"未联网、未启动 server、未调用 diagnostics runner"。

测试 `test_not_opted_in_writes_skipped_summary_and_does_not_call_runner` 通过 monkeypatch 将 `_run_diagnostic_command` 替换为 raising stub，确认 runner 不被调用。

### Opt-in 后 local cases 未实现的表达

**可接受但有改进空间**。`_execute_smoke()` 的 docstring 明确说明"Slice 2 只提供 opt-in CLI、summary contract、子进程 artifact 映射和外部 diagnostic-only 执行框架；local HTTP fixture 由后续 Slice 3 接入"。summary 输出中 `local_cases` 为空列表，不会误导为 F03 最终 pass。

---

## Findings

### Finding 1 [MEDIUM] exit code 0/1/2 散落为魔法数字

**位置**: `utils/smoke_web_ci.py` 全文，约 15 处。

**描述**: exit code `0`、`1`、`2` 携带明确语义（pass/skip、local gate failure、schema gap / infrastructure error），但未定义为模块级常量。所有其它 bucket（`_BUCKET_PASSED`、`_BUCKET_LOCAL_REQUESTS_FAILURE` 等，共 11 个）和 status（`_STATUS_PASSED` 等，共 4 个）均已定义为 `Final[str]` 常量。exit code 是同一层级的语义标识，却直接用整数字面量。

**违反**: `CLAUDE.md` 编码硬约束："禁止魔法数字、魔法字符串"。

**建议裁决**: **accepted — required fix**。新增 `_EXIT_OK: Final[int] = 0`、`_EXIT_LOCAL_FAILURE: Final[int] = 1`、`_EXIT_SCHEMA_OR_INFRA_FAILURE: Final[int] = 2`，替换全文散落字面量。

---

### Finding 2 [LOW] `_BUCKET_NOT_OPTED_IN` 缺失

**位置**: `utils/smoke_web_ci.py:1223`。

**描述**: `"not_opted_in"` 是 `_skipped_summary()` 中 skip item 的 bucket 名称。模块内所有其它 bucket 均已定义为 `_BUCKET_*` 常量（`_BUCKET_PASSED` 到 `_BUCKET_DOCLING_INIT_SKIP`，共 11 个），唯独此 bucket 是内联字符串字面量。

**违反**: `CLAUDE.md` 编码硬约束："禁止魔法字符串"。

**建议裁决**: **accepted — required fix**。新增 `_BUCKET_NOT_OPTED_IN: Final[str] = "not_opted_in"` 并替换内联字面量。

---

### Finding 3 [LOW] `_docling_init_skip()` 中 Docling 异常类型名内联字符串

**位置**: `utils/smoke_web_ci.py:654`。

**描述**: `{"DoclingRuntimeInitializationError", "ModuleNotFoundError", "ImportError"}` 作为内联 frozenset 字面量。`utils/diagnose_web_access.py:96` 已定义 `_DOCLING_DEPENDENCY_EXCEPTION_TYPES: Final[frozenset[str]]` 包含相同值。

**分析**: 模块间依赖最小化原则允许各自定义；但当前模块内已有 11 个 `_BUCKET_*` 常量、4 个 `_STATUS_*` 常量、2 个 `_CASE_*` 常量，异常类型名也应遵循同一模式。

**违反**: `CLAUDE.md` 编码硬约束："禁止魔法字符串"。

**建议裁决**: **accepted — deferred-with-owner**。建议新增 `_DOCLING_INIT_EXCEPTION_NAMES: Final[frozenset[str]]` 模块级常量，但不阻塞 Slice 2，因为：(1) 字符串值与 `diagnose_web_access.py` 一致；(2) 模块间复用需更多理由；(3) 后续 Slice 使用时可一并提取。Owner: Slice 3 或 Slice 5 implementation。

---

### Finding 4 [LOW] 默认超时值内联

**位置**: `utils/smoke_web_ci.py:1513-1514`。

**描述**: `--request-timeout` 默认 `15.0`、`--tool-timeout-budget` 默认 `30.0` 作为 argparse 参数默认值内联。这些值会在 tests 和文档中被引用，但当前只能从 argparse 定义处获取。

**分析**: 严重性低于 Finding 1/2，因为 argparse 默认值是声明式配置而非逻辑分支中的散落字面量。但为了一致性和可测试性，应提取为常量。

**违反**: `CLAUDE.md` 编码硬约束精神（"禁止魔法数字"），但 severity 较低。

**建议裁决**: **accepted — deferred-with-owner**。新增 `_DEFAULT_REQUEST_TIMEOUT: Final[float] = 15.0` 和 `_DEFAULT_TOOL_TIMEOUT_BUDGET: Final[float] = 30.0`。Owner: Slice 3 或 Slice 5 implementation。

---

### Finding 5 [Info] dataclass docstring 使用 `Args:` 而非 `Attributes:`

**位置**: `utils/smoke_web_ci.py` 所有 dataclass docstring（`SmokeOptions`、`DiagnosticChildResult`、`SmokeItem`、`SmokeCaseResult`、`SmokeSummary`，共 5 处）。

**描述**: dataclass 字段文档使用 `Args:` / `Returns:` / `Raises:` 格式，而编码硬约束要求 dataclass 字段用 `Attributes:`。

**分析**: Slice 1 review 已将此标记为 accepted-low（MiMo Finding 2）。`utils/diagnose_web_access.py` 中的 `_DoclingInvocationEvidence` dataclass 使用同样惯例，且 Slice 1 fix gate re-review 确认"不影响功能或可读性"。

**建议裁决**: **accepted（已知惯例差异）**。与 Slice 1 裁决一致。后续可在 Slice 5 统一处理。

---

### Finding 6 [Info] 日期格式字符串内联

**位置**: `utils/smoke_web_ci.py:305`。

**描述**: `"web-smoke-%Y%m%dT%H%M%SZ"` 作为 `_utc_run_label()` 内的格式字符串。

**分析**: 严重性极低。格式字符串用于生成 run label，仅在一处使用，且是纯格式化而非业务逻辑。

**建议裁决**: **accepted（极低优先级）**。可在 Slice 5 提取为 `_RUN_LABEL_FORMAT` 常量，但不阻塞任何 slice。

---

## Mapping Table 逐行验证

| 子进程 / artifact 信号 | Plan 要求 | 实现 | 结论 |
|---|---|---|---|
| return code 0，schema valid，requests ok，fetch ok | local pass | `_classify_loaded_artifact` 最后返回 `status=passed, exit_code=0` | **符合** |
| return code 0，schema missing/version old/required facts missing | local `diagnostic_schema_gap`, exit 2 | `_diagnostic_schema_gap()` 返回非空 → `_case_failure(exit_code=2, bucket=diagnostic_schema_gap)` | **符合** |
| return code 0，requests ok + fetch ok，Playwright skipped | pass | 逻辑走到最后 `return SmokeCaseResult(status=passed)`，不检查 Playwright | **符合** |
| return code 0，local PDF fetch ok，content-type 非 PDF | fail, exit 1 | `_classify_pdf_loaded_artifact` 检查 `"pdf" not in content_type` → `_case_failure(exit_code=1, bucket=pdf_content_type_failure)` | **符合** |
| return code 0，local PDF fetch ok，content 空/过短 | fail, exit 1 | `_classify_pdf_loaded_artifact` 检查 `raw_length <= 0` 或 `fetch_length < _PDF_FETCH_MIN_CHARS` → failure | **符合** |
| return code 0，local PDF fetch ok，`invoked` 非 True | fail, exit 1 | `_classify_pdf_loaded_artifact` 检查 `not _bool_field(evidence, "invoked") or not _bool_field(evidence, "original_completed")` → failure | **符合** |
| return code 0/非0，Docling dependency/init failure | PDF skip, exit 0 | `_docling_init_skip()` + `_case_skip(exit_code=0)`，且检查 `case_kind == _CASE_LOCAL_PDF`，不掩盖 HTML failure | **符合** |
| return code 非0，非 Docling init error | fail, exit 1 | `_case_failure(exit_code=1, bucket=child_process_error)` | **符合** |
| 子进程无 artifact / JSON parse failure | local exit 2 | `_classify_child_result` 检查 `not artifact_path.is_file()` 或 JSON 异常 → `_case_failure(exit_code=2)` | **符合** |
| external case 所有信号 | diagnostic-only, exit 0 | external branch 始终返回 `_case_diagnostic_only(exit_code=0)`，不覆盖 local gate | **符合** |

---

## Exit Code 优先级验证

`_summary_from_cases()` 的 exit code 逻辑：

```python
if any(case.exit_code == 2 for case in local_cases):
    local_exit_code = 2
elif any(case.exit_code == 1 for case in local_cases):
    local_exit_code = 1
```

schema gap（exit 2）优先于 local failure（exit 1），符合 plan 要求。external_cases 不参与 exit code 计算，符合"external 不影响 local gate"要求。

测试 `test_summary_exit_code_prefers_schema_gap_over_local_failure` 锁定了此行为。

---

## Summary Contract 验证

| Plan 字段 | 实现 | 结论 |
|---|---|---|
| `status` | `SmokeSummary.status`，值域 `passed/failed/skipped/diagnostic_only` | **符合** |
| `exit_code` | `SmokeSummary.exit_code` | **符合** |
| `run_label` | `SmokeSummary.run_label` | **符合** |
| `output_dir` | `SmokeSummary.output_dir` | **符合** |
| `failures` | `tuple[SmokeItem, ...]`，含 `bucket/evidence_path/url/suggested_next_step` | **符合** |
| `skips` | `tuple[SmokeItem, ...]`，含 `bucket/evidence_path/url/reason` | **符合** |
| `diagnostic_only` | `tuple[SmokeItem, ...]`，含 `bucket/evidence_path/url/suggested_next_step` | **符合** |
| `local_cases` | `tuple[SmokeCaseResult, ...]` | **符合** |
| `external_cases` | `tuple[SmokeCaseResult, ...]` | **符合** |

Summary JSON 与 MD 双输出，字段自解释，Codex 可读。

---

## 类型与编码规范验证

| 检查项 | 结论 |
|---|---|
| `Any` / `object` 类型注解 | **无**。使用 `JsonValue`（项目 sum type）和 `Mapping`（不可变容器）。 |
| 无类型参数 / 返回值 | **无**。所有函数签名完整类型标注。 |
| 中文 docstring | **完整**。每个函数和方法均有中文 docstring，含 Args/Returns/Raises。 |
| `hasattr` / `getattr` 滥用 | **无**。 |
| 胶水 seam / lazy import | **无**。所有 import 在模块顶部。 |
| import 越界（Host/Engine/Service/UI） | **无**。只 import `dayu.contracts.json_value`、标准库、`argparse`、`subprocess` 等。 |

---

## Tests Deterministic 验证

| 测试 | 覆盖场景 | live network | 结论 |
|---|---|---|---|
| `test_not_opted_in_writes_skipped_summary_and_does_not_call_runner` | 未 opt-in 路径 | 无。monkeypatch env + raising stub。 | **确定性** |
| `test_synthetic_diagnostics_results_map_to_pass_fail_skip_diagnostic_only_and_schema_gap` | 分类逻辑 5 种场景 | 无。synthetic payload + `_classify_child_result`。 | **确定性** |
| `test_summary_exit_code_prefers_schema_gap_over_local_failure` | exit code 优先级 | 无。构造 `SmokeCaseResult` 直接调用 `_summary_from_cases`。 | **确定性** |
| `test_external_failure_is_diagnostic_only_and_does_not_override_local_pass` | external 不覆盖 local | 无。同上。 | **确定性** |
| `test_external_limit_and_summary_paths_are_predictable` | external-limit + summary 路径 | 无。monkeypatch env + fake runner + synthetic artifact。 | **确定性** |

所有 5 个测试均 deterministic，无 live network。覆盖了 plan 要求的所有 expected assertions。

---

## Residual Risks

| 风险 | 严重性 | 说明 |
|---|---|---|
| `_execute_smoke()` 的 `local_cases=()` 不表达"Slice 2 未实现 local" | Low | docstring 已说明；但 summary JSON 中无显式标记，Codex 需要结合 Slice 文档理解。Slice 3 接入后此风险消失。 |
| Docling init exception 字符串匹配与 `diagnose_web_access.py` 重复定义 | Low | 值一致，模块间分离合理，但长期应考虑共享常量。 |
| `_read_external_urls()` 未覆盖 plain text 文件路径测试 | Low | JSONL 路径已覆盖；plain text 分支逻辑简单（`urls.append(line)`），Slice 4 可补充。 |
| 默认超时值无常量 | Very Low | 行为正确，仅可发现性/可测试性改进。 |
| dataclass docstring `Args:` vs `Attributes:` 惯例 | Info | Slice 1 已 accepted-low，不影响功能。 |

---

## Final Recommendation: **pass-with-fixes**

### 理由

Slice 2 实现整体质量高：

1. **严格遵守 Slice 边界**：未越界到 Slice 3 local HTTP server、production 代码或 Host/Engine。
2. **opt-in 行为正确**：未 opt-in 时不联网、不启动 server、不调用 diagnostics runner。
3. **mapping table 逐行符合**：所有分类、exit code、diagnostic-only 语义均正确实现。
4. **summary contract 完整**：JSON + MD 双输出，字段自解释。
5. **类型安全**：无 `Any`/`object`/无类型签名。
6. **测试 deterministic**：5 个测试全部无 live network，覆盖核心路径。
7. **无 import 越界**：不触碰 Host/Engine/Service/UI。

### Required Fixes（2 项）

| # | Finding | 修复要求 |
|---|---|---|
| 1 | Finding 1 [MEDIUM] exit code 魔法数字 | 新增 `_EXIT_OK`/`_EXIT_LOCAL_FAILURE`/`_EXIT_SCHEMA_OR_INFRA_FAILURE` 常量，替换全文约 15 处字面量。 |
| 2 | Finding 2 [LOW] `_BUCKET_NOT_OPTED_IN` 缺失 | 新增 `_BUCKET_NOT_OPTED_IN` 常量，替换 `_skipped_summary()` 内联字面量。 |

### Deferred Findings（2 项）

| # | Finding | Owner |
|---|---|---|
| 3 | Finding 3 [LOW] Docling 异常类型名内联 | Slice 3 或 Slice 5 |
| 4 | Finding 4 [LOW] 默认超时值内联 | Slice 3 或 Slice 5 |

### Accepted Without Changes（2 项）

| # | Finding | 理由 |
|---|---|---|
| 5 | Finding 5 [Info] dataclass `Args:` vs `Attributes:` | Slice 1 已 accepted-low |
| 6 | Finding 6 [Info] 日期格式字符串内联 | 极低优先级 |
