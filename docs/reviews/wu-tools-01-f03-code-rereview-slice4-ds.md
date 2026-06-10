# WU-TOOLS-01-F03 Slice 4 Fix Gate Re-Review (AgentDS)

## Scope

- Mode: current changes
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main
- Output file: docs/reviews/wu-tools-01-f03-code-rereview-slice4-ds.md
- Included scope: 仅核对 controller adjudication 中的 required fix 是否完整实现、无退化
- Inputs:
  - Controller adjudication: `docs/reviews/wu-tools-01-f03-code-review-slice4-controller-adjudication.md`
  - Codex fix report: `docs/reviews/wu-tools-01-f03-fix-slice4-codex.md`
  - Current uncommitted diff in `utils/smoke_web_ci.py` + `tests/tools/web/test_smoke_web_ci.py`

## 核对清单

Controller 裁决 Document 定义了 1 个 required fix，包含 5 个子要求：

| # | 要求 | 核对结果 |
|---|------|----------|
| 1 | external URL 文件内容非法时在参数阶段 fail-fast | pass |
| 2 | local fixture / local diagnostics 未启动 | pass |
| 3 | exit code 2 | pass |
| 4 | 无 output artifacts | pass |
| 5 | 合法文件仍按 `--external-limit` 采样 | pass |
| 6 | external diagnostic-only 分类逻辑未退化 | pass |

---

## 逐项路径追踪

### 1. external URL 文件内容非法 → 参数阶段 fail-fast

**执行入口**：`main()` (smoke_web_ci.py:2083) → `_options_from_namespace()` (line 2068-2069)

**完整路径**：

1. `_options_from_namespace()` line 2066: 文件存在性检查 → `ValueError` if missing
2. `_options_from_namespace()` line 2068-2069: 调用 `_validate_external_url_file()`
3. `_validate_external_url_file()` (line 1679): 逐行读取，`.strip()` 后跳过空行与 `#` 开头行
4. JSONL 文件 → `_url_from_jsonl_line()` 解析 JSON 对象/字符串，非法 JSON 抛出 `ValueError`
5. 非 JSONL 文件 → 每行作为纯文本 URL，传入 `_validate_external_url_text()`
6. `_validate_external_url_text()` (line 1704): `urlparse` 校验 scheme∈{http,https} 且 netloc 非空，否则 `ValueError`
7. `main()` line 2101-2103: 捕获 `ValueError`，stderr 输出错误信息，返回 `_EXIT_SCHEMA_OR_INFRA_FAILURE` (=2)

**测试证据**：

- `test_missing_external_file_returns_operator_input_error` (test_smoke_web_ci.py:748): 文件不存在 → exit_code=2, summary.json 未创建
- `test_invalid_external_file_returns_operator_input_error_before_local_diagnostics` (test_smoke_web_ci.py:775) parametrized:
  - `urls.jsonl` 含 `{not-json\n` → JSON 解析失败 → `ValueError`
  - `urls.txt` 含 `ftp://example.com/not-http\n` → scheme 非法 → `ValueError`

**结论**: 参数阶段 fail-fast 正确实现，`_options_from_namespace` 中文件存在校验与内容校验均在 `_execute_smoke` 调用前触发。

---

### 2. local fixture / local diagnostics 未启动

**测试入口**: `test_invalid_external_file_returns_operator_input_error_before_local_diagnostics` (line 775)

**路径验证**：

- `raising_server` (line 790): 若 context manager 被进入则追加 `"started"` 到 `fixture_starts` 并抛出 `AssertionError`
- `raising_runner` (line 797): 若被调用则直接抛出 `AssertionError`
- 断言 `fixture_starts == []` (line 819): 证明 `_running_local_fixture_server` 从未进入
- 断言 `not output_dir.exists()` (line 820): 证明无任何目录/文件创建

**根因链**: `_options_from_namespace` 在 `_execute_smoke` 之前抛出 `ValueError` → `main()` 直接返回 exit code 2，不进入 `_execute_smoke` → `_run_local_cases` 与 `_run_external_cases` 均未调用。

**结论**: 无误。

---

### 3. exit code 2

- `_EXIT_SCHEMA_OR_INFRA_FAILURE = 2` (line 44)
- `main()` line 2103: `return _EXIT_SCHEMA_OR_INFRA_FAILURE`
- 两个测试均断言 `assert exit_code == 2`

**结论**: 无误。

---

### 4. 无 output artifacts

- `test_missing_external_file_returns_operator_input_error`: `assert not (tmp_path / "out" / "summary.json").exists()`
- `test_invalid_external_file_returns_operator_input_error_before_local_diagnostics`: `assert not output_dir.exists()`

**结论**: 无误。

---

### 5. 合法文件仍按 `--external-limit` 采样

**测试**: `test_external_limit_and_summary_paths_are_predictable` (line 823)

**测试数据**（JSONL 文件）:
```
# comment

{"url": "https://example.com/a"}
  # another comment
{"url": "https://example.com/b"}
{"url": "https://example.com/c"}
```

**参数**: `--external-limit 2`

**验证**:
- `called_urls == ["https://example.com/a", "https://example.com/b"]` — 注释行（含前导空格的 `  # another comment` 经 `.strip()` 后正确跳过）、空行正确跳过，仅采样前 2 条有效 URL
- `summary["status"] == "passed"`, `exit_code == 0`

**实现路径**: `_read_external_urls()` (line 1648) 仍负责按 `limit` 返回样本，`_validate_external_url_file()` 只做全文件 dry-run 校验，两者不耦合。`limit=0` 行为不变（不运行外部诊断）。

**结论**: 无误。

---

### 6. external diagnostic-only 分类逻辑未退化

**修改点**:

| 位置 | 修改 | 影响 |
|------|------|------|
| `_classify_child_result` line 1426 | 新增 `_CASE_EXTERNAL` + 非零 returncode 早期返回 → `diagnostic_only` (`child_process_error`) | 填补 external child 非零 exit 的分类缺口 |
| `_classify_loaded_artifact` line 1090 | 同样新增 returncode 检查 | belt-and-suspenders，与 line 1426 功能重叠但无害 |
| `_diagnostic_command` line 1776 | 新增 `sample_playwright: bool` 参数，替代从 `options.include_playwright` 读取 | 实现 local/external Playwright 隔离 |
| `_run_local_cases` line 1848 | 传入 `sample_playwright=False` | local 永远跳过 Playwright |
| `_run_external_cases` line 1891 | 传入 `sample_playwright=options.include_playwright` | external 仅在 `--include-playwright` 时采样 |

**退化检查**（逐条走读原有分类路径）:

- `_classify_child_result` line 1436 (`not artifact_path.is_file()`): external → `diagnostic_only` (`artifact_missing`)，**未改**
- `_classify_child_result` line 1456 (`_load_json_artifact` 异常): external → `diagnostic_only` (`artifact_parse_failure`)，**未改**
- `_classify_loaded_artifact` line 1101 (schema gap): external → `diagnostic_only` (`diagnostic_schema_gap`)，**未改**
- `_classify_loaded_artifact` line 1112 (observed bucket): external → `diagnostic_only` (observed bucket)，**未改**

**测试证据**:

- `test_external_child_returncode_does_not_override_local_pass` (line 524): external child returncode=9 → `diagnostic_only`(`child_process_error`)，local pass 保持 exit_code=0
- `test_external_parse_and_artifact_gap_do_not_override_local_pass` (line 593): external parse/artifact gaps → `diagnostic_only` 的 `artifact_parse_failure`/`artifact_missing` buckets
- `test_include_playwright_only_affects_external_diagnostic_cases` (line 670): `--include-playwright` 仅影响 external 命令，local 始终 `--skip-playwright`
- 所有 Slice 2-3 已有测试均通过（`test_external_failure_is_diagnostic_only_and_does_not_override_local_pass` 等）

**结论**: 现有分类逻辑无退化，新增 early return 补齐了原 external child returncode 分类缺口。

---

## 验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 测试 | `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` | 36 passed |
| 类型 | `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings |
| 空白 | `git diff --check` | passed |

---

## Findings

未发现实质性问题。

**附注 — 无害冗余**:

- `_classify_loaded_artifact` line 1090-1100 的 external returncode 检查与 `_classify_child_result` line 1426-1435 功能重叠。`_classify_child_result` 在调用 `_classify_loaded_artifact` 前已拦截同一条件，使后者不可达。此为 belt-and-suspenders 安全网，不造成行为错误。
- `_validate_external_url_file` line 1693 的文件存在检查与 `_options_from_namespace` line 2066 重复，同为防御性编程，不造成行为错误。

---

## Open Questions

无。

---

## Residual Risk

- `test_missing_external_file_returns_operator_input_error` 只校验 exit code=2 和 summary 不存在，未校验 local fixture/runner 未被调用（与 `test_invalid_external_file_returns_operator_input_error_before_local_diagnostics` 对比）。但由于两条路径共享 `main()` 中的同一 `ValueError` 捕获分支，实际风险极低。

---

## 结论

**pass** — 所有 required fix 正确实现且经测试验证，无退化。
