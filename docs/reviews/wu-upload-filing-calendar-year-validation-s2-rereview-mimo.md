# UF-FIX04 S2 re-review（AgentMiMo）

## Gate record

- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S2-upload-strict-static-admission`
- Base: `e5d4394a`
- Review input: controller adjudication accepted AgentDS F1；AgentCodex review-fix artifact
- Review action: 只读。未修改代码/测试，未 stage、未 commit

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `e5d4394a`
- Verified files:
  - `tests/fins/test_fins_ingestion_runtime.py` — F1 fix 所在文件
  - `dayu/fins/ingestion_runtime.py` — 生产 validation 顺序（只读核对）
- Excluded scope: frozen oracle/scenario/evidence，CLI/tool tests（未被 fix 修改）

## 验证复核

| 声明 | 复核命令 | 复核结果 | 一致 |
| --- | --- | --- | --- |
| 优先级测试 | `pytest tests/fins/test_fins_ingestion_runtime.py::test_validate_fins_upload_filing_request_preserves_validation_priority -q` | `8 passed, 3 warnings` | ✅ |
| 零副作用测试 | `pytest tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_precedes_all_side_effects -q` | `19 passed, 3 warnings` | ✅ |
| 委托边界测试 | `pytest tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates -q` | `2 passed, 3 warnings` | ✅ |
| runtime 完整文件 | `pytest tests/fins/test_fins_ingestion_runtime.py -q` | `258 passed, 3 warnings` | ✅ |
| 定向 pyright | `python -m pyright ...`（6 文件） | `0 errors, 0 warnings, 0 informations` | ✅ |
| 冻结 registry/evidence | `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` | 无输出 | ✅ |
| 未 stage/commit | `git diff --cached --name-status` | 无输出 | ✅ |

## F1 修复验证

### 修复内容

在 `test_validate_fins_upload_filing_request_preserves_validation_priority` 矩阵中新增两个 case：

1. `filing_date="2024-13-01"` + `files=(Path("missing.pdf"),)` → 期望 `INVALID_FILING_DATE`
2. `report_date="2024-13-01"` + `files=(Path("missing.pdf"),)` → 期望 `INVALID_REPORT_DATE`

### 日期字段对称性

- 两个日期字段共用 `_validate_optional_upload_iso_date`（`ingestion_runtime.py:971`），委托同一 owner `parse_iso_calendar_date`
- 两个新 case 结构完全对称：相同的 ticker/year/period/files，仅日期字段不同
- 两个 case 各自断言对应的 field-specific code，不共享

### 缺失文件确定性

- `tmp_path / upload_request.files[0].name` 使用 pytest 临时目录，`assert not missing_file.exists()` 显式确认文件不存在
- 不依赖仓库当前目录状态，跨运行 deterministic

### 断言区分 date error 与 FILE_NOT_FOUND

- 生产顺序：`_validate_optional_upload_iso_date`（line 911-912）在 file existence probes（line 916-920）之前
- 两个新 case 同时包含非法日期与缺失文件，断言 `exc_info.value.failure.code is expected_code`（`INVALID_FILING_DATE` / `INVALID_REPORT_DATE`）
- 若 date check 被误移到 file probes 之后，这些 case 将返回 `FILE_NOT_FOUND`，`is` 断言失败

### 生产/其它测试/frozen scope

- 生产代码零修改（`dayu/fins/ingestion_runtime.py` 未被 fix 触碰）
- CLI tests、tool tests 未被 fix 修改
- frozen oracle/scenario/evidence 未改
- `tmp_path` 参数被注入所有 parametrized case，但只有带 `files` 的 case 使用；对无 `files` 的 case 无影响（`if upload_request.files` 为 False 时跳过）

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `UF-PF04` 真实 CLI evidence：未执行（按计划），owner=`UF-PF04` later work unit。
- `upload_filings_from` metadata strip parity：deferred 项，owner 不变。
- tool baseline failure `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`：pre-existing，本 slice 前后 failure set 精确相等。

## Conclusion

**Pass**。AgentDS F1 已正确关闭：两个对称优先级 case 让日期错误与 `FILE_NOT_FOUND` 形成直接竞争，`tmp_path` 保证文件确定性不存在，`is` 断言锁定 typed code 优先级。修复仅触及测试，生产代码、其它测试与 frozen scope 未变。pyright 0 errors，全部测试通过且计数与 fix artifact 一致。S2 可 accepted。
