# Code Re-Review

## Scope

- Mode: current changes (fix gate re-review)
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main
- Output file: `docs/reviews/wu-tools-01-f03-code-rereview-slice4-mimo.md`
- Included scope: controller adjudication required fix (DS4-001) 的 Codex 实现与测试
- Excluded scope: Slice 4 原始 review 已 accepted 的项、accepted-low 未处理项
- Parallel review coverage: 无

## 输入

- Controller adjudication: `docs/reviews/wu-tools-01-f03-code-review-slice4-controller-adjudication.md`
- Codex fix: `docs/reviews/wu-tools-01-f03-fix-slice4-codex.md`
- 当前未提交 diff: `git diff` (utils/smoke_web_ci.py, tests/tools/web/test_smoke_web_ci.py)

## Required Fix 核对

### 核对项 1：external URL 文件内容非法时是否已在参数阶段 fail-fast

**结论：通过。**

- `_options_from_namespace()` 在文件存在性校验（line 2066-2067）后立即调用 `_validate_external_url_file()`（line 2068-2069）。
- `_validate_external_url_file()` 遍历全部行，跳过空行和注释行（`line.startswith("#")`），对 JSONL 文件复用 `_url_from_jsonl_line()` 解析，对纯文本文件调用 `_validate_external_url_text()` 校验 scheme。
- `main()` 中 `_options_from_namespace()` 在 `_execute_smoke()` 之前执行（line 2098 vs 2110），`ValueError` 在 line 2101-2103 被捕获并返回 `_EXIT_SCHEMA_OR_INFRA_FAILURE`（2）。
- 直接证据：`utils/smoke_web_ci.py:2066-2069`（调用点），`1679-1701`（校验逻辑），`2096-2103`（错误捕获）。

### 核对项 2：local fixture / local diagnostics 未启动

**结论：通过。**

- `_execute_smoke()` 是 `_running_local_fixture_server()` 和 `_run_diagnostic_command()` 的唯一入口（line 2110）。
- `_options_from_namespace()` 的 `ValueError` 在 line 2098 抛出，line 2101-2103 捕获并 return，不进入 `_execute_smoke()`。
- 测试 `test_invalid_external_file_returns_operator_input_error_before_local_diagnostics` 用 `raising_server` / `raising_runner` monkeypatch 验证：`fixture_starts == []`，`assert not output_dir.exists()`。
- 直接证据：`tests/tools/web/test_smoke_web_ci.py:775-820`。

### 核对项 3：exit code 2

**结论：通过。**

- `_EXIT_SCHEMA_OR_INFRA_FAILURE` 值为 2（line 42）。
- 测试 `test_missing_external_file_returns_operator_input_error` 断言 `exit_code == 2`（line 764）。
- 测试 `test_invalid_external_file_returns_operator_input_error_before_local_diagnostics` 断言 `exit_code == 2`（line 818）。
- 直接证据：`utils/smoke_web_ci.py:42`，`tests/tools/web/test_smoke_web_ci.py:764,818`。

### 核对项 4：无 output artifacts

**结论：通过。**

- `test_missing_external_file_returns_operator_input_error` 断言 `not (tmp_path / "out" / "summary.json").exists()`（line 765）。
- `test_invalid_external_file_returns_operator_input_error_before_local_diagnostics` 断言 `not output_dir.exists()`（line 820）。
- 直接证据：`tests/tools/web/test_smoke_web_ci.py:765,820`。

### 核对项 5：合法文件仍按 --external-limit 采样

**结论：通过。**

- `_validate_external_url_file()` 只做全文件校验，不做采样截断。
- `_read_external_urls()` 仍负责按 `limit` 返回样本（line 1880）。
- `test_external_limit_and_summary_paths_are_predictable` 已更新，输入包含空行、注释行（line 836-839），验证合法 JSONL 含注释/空行时仍按 `--external-limit` 正常采样。
- 直接证据：`utils/smoke_web_ci.py:1679-1701`（validate），`1660-1676`（read with limit），`tests/tools/web/test_smoke_web_ci.py:823-846`。

### 核对项 6：external diagnostic-only 分类逻辑未退化

**结论：通过。**

- `_classify_child_result()` 中 external child failure 的 diagnostic-only 分支（line 1426-1435）保持不变。
- artifact gap 和 parse failure 的 external diagnostic-only 分支（line 1436-1446）保持不变。
- `_diagnostic_command()` 新增 `sample_playwright` 参数，local cases 传 `False`，external cases 传 `options.include_playwright`，与原始逻辑一致。
- `test_include_playwright_only_affects_external_diagnostic_cases` 验证 local URL 命令包含 `--skip-playwright`，external URL 命令不包含。
- 直接证据：`utils/smoke_web_ci.py:1426-1446`，`1782`（sample_playwright 参数），`1848`（local: False），`1891`（external: options.include_playwright）。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- `_validate_external_url_text()` 对 scheme 缺省的 URL 补 `https://` 后再校验，与 `_run_external_cases()` 中 diagnostics 子进程的实际处理一致，但 `_validate_external_url_text` 与 `_read_external_urls` 中纯文本分支的校验逻辑存在轻微重复：`_read_external_urls` 的纯文本分支不做 scheme 校验，直接返回原始字符串。这是 pre-existing 行为，不在本次 required fix 范围内，不影响 correctness（diagnostics 子进程自行处理）。

## 验证结果

| 检查项 | 结果 |
|--------|------|
| `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` | 36 passed |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |

## 结论

**pass**。Required fix（DS4-001）已正确实现：external URL 文件内容非法时在参数阶段 fail-fast，返回 exit code 2，不启动 local fixture / diagnostics，不产生 output artifacts；合法文件仍按 `--external-limit` 采样；external diagnostic-only 分类逻辑未退化。
