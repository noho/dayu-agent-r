# Code Review

## Scope

- Mode: current changes
- Branch: `wu-tools-01-f03-web-ci-smoke`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f03-code-review-slice4-mimo.md`
- Included scope: `utils/smoke_web_ci.py`（unstaged diff）、`tests/tools/web/test_smoke_web_ci.py`（unstaged diff）、`docs/reviews/wu-tools-01-f03-implementation-slice4-codex.md`
- Excluded scope: `dayu/tools/web/`、`dayu/host/`、`dayu/engine/`、`utils/diagnose_web_access.py`（Slice 1-3 已完成，本次不修改）
- Parallel review coverage: 无

## Review Intent Alignment

真源：`docs/host/wu-tools-01-f03-web-ci-smoke-plan.md` Slice 4。

Slice 4 目标：让 F03 能从 F02 URL corpus 生成外部站点 diagnostic-only 摘要，但不把全量 corpus 变成 gate。

重点挑战点：

1. 默认不运行 external URL；`--external-url-file` + `--external-limit` 才采样小样本，禁止默认全量。
2. external diagnostics 默认 `--skip-playwright`；`--include-playwright` 只影响 external diagnostic-only，不影响 local HTML/PDF gate。
3. external `all_failed` / `playwright_challenge_detected` / child returncode 非 0 / artifact missing / parse failure 都不能产生 exit code 1，不能覆盖 local pass。
4. 明确传不存在或非法 external URL 文件时 exit code 2，且语义是 operator input error。
5. 测试是否 deterministic，无真实网络；未触碰 `utils/web_ci_urls.jsonl` 是否合理。
6. 无 `Any`/`object`/无类型签名/魔法数字扩散，README 判断是否成立。

## Verification Results

| 验证命令 | 结果 |
|---|---|
| `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` | 35 passed, 0.34s |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 无输出 |

## Findings

### 1-未修复-低-外部文件验证在 local smoke 之前执行，非法外部文件导致 local 结果丢失

- **入口/函数**: `main()` -> `_options_from_namespace()`
- **文件(行号)**: `utils/smoke_web_ci.py:2018-2019`
- **输入场景**: `--run-live --external-url-file /nonexistent.jsonl --external-limit 1`
- **实际分支**: `_options_from_namespace` 抛出 `ValueError("external URL 文件不存在: ...")`，`main()` 捕获后返回 `_EXIT_SCHEMA_OR_INFRA_FAILURE`（exit code 2），`_execute_smoke` 未执行
- **预期行为**: 按 plan Slice 4，非法 external URL 文件应返回 exit code 2（operator input error）——行为正确。但 `_execute_smoke` 未执行意味着 local HTML/PDF smoke 结果完全丢失，无 summary.json 写入
- **直接证据**: `utils/smoke_web_ci.py:2046-2053`，`main()` 中 `_options_from_namespace` 在 `_execute_smoke` 之前执行；`ValueError` 捕获后直接 return，不写 summary
- **影响**: 操作者传错外部文件时，无法知道 local smoke 是否会 pass。若 CI 脚本先跑 local 后加 external，需额外处理此边界
- **建议改法和验证点**: 当前行为与 plan "operator input error" 语义一致，不强制修改。若未来需要更友好的行为，可考虑在 `_options_from_namespace` 中只做文件存在性 early check，把 JSONL 解析延迟到 `_run_external_cases`，使 local smoke 能先跑并写 partial summary。但当前 plan 不要求此行为，降级为 design note
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-`_read_external_urls` docstring 语义与 `--external-limit` 默认行为存在阅读歧义

- **入口/函数**: `_read_external_urls()`
- **文件(行号)**: `utils/smoke_web_ci.py:1646-1674`
- **输入场景**: `--external-url-file utils/web_ci_urls.jsonl`（不传 `--external-limit`，默认 0）
- **实际分支**: `limit=0`，`limit >= 0` 为 True，`len(urls) >= 0` 立即为 True，循环 break，返回空列表
- **预期行为**: docstring 写 `limit: 最多返回数量；0 表示不返回样本`，实际行为确实返回空列表——一致。但 `--external-limit` 的 argparse help 写 `外部 URL 最多采样数量`，默认 `0`，语义上 0 可以理解为"零个"或"无上限"
- **直接证据**: `utils/smoke_web_ci.py:1652` docstring vs `utils/smoke_web_ci.py:1976` argparse help；`utils/smoke_web_ci.py:1665` 条件 `limit >= 0 and len(urls) >= limit`
- **影响**: 不影响运行时行为（默认 0 正确地不跑外部 URL）。但阅读代码时可能产生"0 是无上限还是零个"的歧义
- **建议改法和验证点**: 可选优化：在 argparse help 中明确 `0 表示不运行外部诊断`，或在 docstring 中补充 `默认 0 与不传 --external-url-file 等效`。不强制修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Review of Requested Challenge Points

### 1. 默认不运行 external URL；`--external-url-file` + `--external-limit` 才采样小样本

**通过。**

- `_options_from_namespace` 中 `external_url_file` 默认为 `None`（`namespace.external_url_file` 为空字符串时映射为 `None`）。
- `_run_external_cases` 在 `options.external_url_file is None` 时直接返回空列表。
- `--external-limit` 默认 `0`，`_read_external_urls` 在 `limit=0` 时返回空列表。
- 只有同时传 `--external-url-file <existing-file>` 和 `--external-limit >0` 才会实际运行外部诊断。
- 测试 `test_external_limit_and_summary_paths_are_predictable` 锁定 `--external-limit 2` 只取前 2 个 URL。

### 2. external diagnostics 默认 `--skip-playwright`；`--include-playwright` 只影响 external

**通过。**

- `_diagnostic_command` 新增 `sample_playwright` 参数，取代原来直接读 `options.include_playwright`。
- `_run_local_cases` 始终传 `sample_playwright=False`（行 1800）。
- `_run_external_cases` 传 `sample_playwright=options.include_playwright`（行 1843）。
- 测试 `test_include_playwright_only_affects_external_diagnostic_cases` 验证 local 命令含 `--skip-playwright`，external 命令在 `--include-playwright` 时不含 `--skip-playwright`。

### 3. external 失败信号不产生 exit code 1，不覆盖 local pass

**通过。**

- `_classify_child_result` 新增 early return（行 1424-1433）：`case_kind == _CASE_EXTERNAL and child_result.returncode != _EXIT_OK` 时直接返回 `_case_diagnostic_only`，bucket 为 `child_process_error`。
- artifact missing 和 parse failure 对 external case 也返回 `_case_diagnostic_only`（行 1435-1466）。
- `_summary_from_cases` 中 `local_exit_code` 只看 `local_cases`，`external_cases` 只贡献 `diagnostic_only` 列表。
- 测试覆盖：
  - `test_external_child_returncode_does_not_override_local_pass`：returncode=9 进入 diagnostic_only，exit_code=0。
  - `test_external_parse_and_artifact_gap_do_not_override_local_pass`：parse failure + artifact missing 进入 diagnostic_only，exit_code=0。
  - `test_external_failure_is_diagnostic_only_and_does_not_override_local_pass`（既有测试）：child_process_error 进入 diagnostic_only。

### 4. 不存在或非法 external URL 文件时 exit code 2

**通过。**

- `_options_from_namespace` 新增文件存在性检查（行 2018-2019）：`if external_url_file is not None and not external_url_file.is_file(): raise ValueError(...)`。
- `main()` 捕获 `ValueError` 后返回 `_EXIT_SCHEMA_OR_INFRA_FAILURE`（exit code 2）。
- 测试覆盖：
  - `test_missing_external_file_returns_operator_input_error`：文件不存在，exit_code=2，无 summary.json。
  - `test_invalid_external_file_returns_operator_input_error`：JSONL 非法，exit_code=2，无 summary.json。fake_runner 对 external URL 会 `raise AssertionError`，验证 external runner 未被调用。
- 副作用评估：local smoke 未执行、无 summary 写入。这与 "operator input error" fail-fast 语义一致，但操作者失去 local smoke 可见性。见 Finding 1。

### 5. 测试 deterministic，无真实网络，未触碰 `utils/web_ci_urls.jsonl`

**通过。**

- 所有新测试通过 `monkeypatch.setattr` 替换 `_running_local_fixture_server` 和 `_run_diagnostic_command`，不启动真实 HTTP server、不调用真实 diagnostics 子进程。
- `test_missing_external_file_returns_operator_input_error` 不需要 monkeypatch，因为 `_options_from_namespace` 在 runner 调用之前就失败了。
- 未修改 `utils/web_ci_urls.jsonl`，符合 plan "仅当需要给少量 URL 添加 metadata" 的条件——本轮不需要。
- 测试 helper `_diagnostic_payload` 构造 synthetic artifact，schema 版本固定为 `web-diagnostics-v1` revision 1。

### 6. 无 `Any`/`object`/无类型签名/魔法数字扩散

**通过。**

- 新增/修改的函数签名全部有类型注解：`_diagnostic_command` 的 `sample_playwright: bool`、`_classify_child_result` 的所有参数。
- 常量使用 `_BUCKET_CHILD_PROCESS_ERROR`、`_BUCKET_ARTIFACT_MISSING`、`_BUCKET_ARTIFACT_PARSE_FAILURE` 等 `Final[str]` 定义。
- `SmokeOptions`、`SmokeCaseResult`、`SmokeItem`、`DiagnosticChildResult` 等 dataclass 使用 `frozen=True, slots=True`。
- 未引入 `Any` 或 `object` 类型。
- README 判断：本轮只在既有 Web smoke 测试层内补 external diagnostic-only 场景，不新增测试层级，`tests/README.md` 已有 deterministic 声明仍准确，不更新 README 合理。

## Implementation vs Plan Alignment

| Plan 要求 | 实现状态 |
|---|---|
| 默认不运行 external URL | 通过：`external_url_file` 默认 None，`external_limit` 默认 0 |
| `--external-url-file` + `--external-limit` 采样小样本 | 通过：`_read_external_urls` 按 limit 截断 |
| external 默认 `--skip-playwright` | 通过：`sample_playwright=options.include_playwright`，默认 False |
| `--include-playwright` 只影响 external | 通过：local 始终 `sample_playwright=False` |
| external 失败不产生 exit code 1 | 通过：`_classify_child_result` early return + `_summary_from_cases` 只看 local |
| 非法 external 文件 exit code 2 | 通过：`_options_from_namespace` 文件存在性检查 |
| 测试 deterministic | 通过：全部 monkeypatch，无真实网络 |
| 不修改 `utils/web_ci_urls.jsonl` | 通过：未修改 |

## Open Questions

- 无。

## Residual Risk

- 本轮未运行真实外部 URL live diagnostics，只验证 deterministic tests。
- external URL 的真实失败、anti-bot、Playwright challenge、网络波动和 provider/browser gap 仍只进入 `external_cases` / `diagnostic_only`，不作为 local gate regression。
- `--external-limit` 负值被 `_options_from_namespace` 正确拒绝（`external_limit_value < 0`），但无专门测试覆盖此边界。
- Finding 1（非法外部文件导致 local 结果丢失）是设计权衡，不是 bug；若未来需要 partial summary 行为，需调整执行顺序。
