# Code Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `e5d4394a`
- Output file: `docs/reviews/wu-upload-filing-calendar-year-validation-s2-deepreview-mimo-20260814-151653.md`
- Included scope:
  - `dayu/fins/ingestion_runtime.py` — static validation, usage code enum, usage message mapping
  - `dayu/cli/commands/fins.py` — CLI direct upload_filing path
  - `dayu/fins/tools/upload_tools.py` — tool filing adapter
  - `tests/fins/test_fins_ingestion_runtime.py` — runtime validation tests
  - `tests/fins/test_fins_ingestion_tools.py` — tool validation tests
  - `tests/cli/test_fins_commands.py` — CLI validation tests
- Excluded scope: frozen registry/evidence files, UF-PF04 (not executed per plan)
- Parallel review coverage: 无

## Review Method

1. 完整阅读 S1 shared owner `dayu/fins/domain/filing_semantics.py` 中的 `parse_calendar_year` 和 `parse_iso_calendar_date`。
2. 沿真实执行路径走读：CLI `_prevalidate_upload_filing_request` → `_validate_fins_upload_filing_static` → `parse_calendar_year` / `parse_iso_calendar_date`；tool `_upload_request_from_arguments` → `_optional_raw_nullable_text` → runtime `_validate_runtime_upload_request` → `_validate_fins_upload_filing_static`。
3. 检查 `_USAGE_MESSAGES` 中三条新增消息的唯一 owner 归属。
4. 验证 material / `upload_filings_from` 路径未被改变。
5. 验证 frozen registry/evidence 未修改，UF-PF04 未执行。
6. 运行 pyright（0 errors）和相关测试（全部通过）。

## Findings

未发现实质性问题。

## Analysis

### Semantic Ownership

- `parse_calendar_year` 和 `parse_iso_calendar_date` 是 S1 accepted `dayu.fins.domain.filing_semantics` 中的共享 owner。runtime 只捕获 owner 的 `ValueError` 并映射为 field-specific typed usage code，没有重写 Gregorian/year 规则。
- 三条 LLM/CLI 共用 message 的唯一 owner 是 `ingestion_runtime._USAGE_MESSAGES`；tool 通过 runtime `FinsUploadUsageError` 原样消费，CLI 通过同一 failure 投影，不存在 channel-specific 重算。

### CLI Raw Date Preservation

- 直接 `upload_filing` 路径：`filing_date=args.filing_date`, `report_date=args.report_date` — 不 strip，不 fold blank to None。
- `upload_material` 路径：`_optional_stripped_text(args.filing_date)` — 保持原 contract。
- `upload_filings_from` 路径：`_optional_stripped_text(args.filing_date)` — 保持原 contract。
- argparse 定义 `--filing-date` / `--report-date` 为可选 string，未传时为 `None`，传时为原始字符串。

### Tool Raw Date Preservation

- filing 分支：`_optional_raw_nullable_text` — missing/null → None，string 原样返回，非 string 抛 ValueError。
- material 分支：`_optional_nullable_text` — missing/null → None，strip 后返回，空/blank 抛 ValueError。
- material contract 未改变（测试 `test_upload_tool_calendar_year_schema_and_usage_messages_are_business_neutral` 验证 padded material date 被 strip）。

### Zero-Side-Effect Guarantee

- Runtime 测试：`_ForbiddenFilingUploadStateRepository` 在 `read_filing_upload_state` 时抛 AssertionError，测试验证 `state_repository.calls == []`。
- `_HoldingExecutor.operations == []`，`_ForbiddenUploadRunner.requests == []`，`runtime._observations == {}`。
- `.dayu/fins_ingestion/jobs` 和 `portfolio` 不存在，workspace tree snapshot 在调用前后相等。
- Tool 测试：`_ForbiddenFilingUploadStateRepository` 同样验证 state read 为零；executor、observation、job store、workspace snapshot 均为零变化。

### Validation Order

- `_validate_fins_upload_filing_static` 中：calendar/year 验证位于 period 验证之后、file existence probes 之前。
- `_validate_runtime_upload_request` 中：`_filing_upload_request_identity` 调用 `_validate_fins_upload_filing_static` 在 `read_filing_upload_state` 之前。
- 测试 `test_filing_calendar_year_static_admission_precedes_all_side_effects` 通过 forbidden repository 证明 state read 在 static admission 之后。

### LLM-Facing Schema

- `fiscal_year` description: "财年。上传 filing 时必填，且只接受 1000..9999 的整数；上传 material 时可选。"
- `filing_date` description: "可选披露日期。上传 filing 时若填写，必须是实际存在的 YYYY-MM-DD 日期；文本不会自动去除空白，空串、纯空白或首尾空白均非法。"
- `report_date` description: "可选报告期日期。上传 filing 时若填写，必须是实际存在的 YYYY-MM-DD 日期；文本不会自动去除空白，空串、纯空白或首尾空白均非法。"
- 三条 usage message 均不含 `--` channel 语法，业务中立且自解释。

### Test Coverage

- 年份负向矩阵：`bool`, `0`, `-1`, `999`, `10000`
- 日期负向矩阵（filing_date）：`""`, `" "`, `" 2024-02-29 "`, `"2024-2-29"`, `"2023-02-29"`, `"2024-13-01"`, `"2024/02/29"`
- 日期负向矩阵（report_date）：`""`, `"\t"`, `"2024-02-29 "`, `"2024-2-29"`, `"2023-02-29"`, `"2024-00-01"`, `"2024.02.29"`
- 日期边界：`"2024-04-31"`（不存在日期）
- 正向边界：`1000`, `9999`, `"2024-02-29"`（闰日）
- Owner delegation：monkeypatch 验证 `parse_calendar_year` 和 `parse_iso_calendar_date` 被调用正确次数
- CLI matrix：exact exit/stderr、fresh/seeded workspace snapshot、factory/service stream 零调用
- Tool matrix：exact `ToolFailedOutcome(error="invalid_argument")`、state/observation/job/executor/workspace 零副作用

### Frozen Files

- `git diff e5d4394a -- docs/reviews/wu-upload-filing-calendar-year-validation-plan-accepted.md` 无输出（文件不存在于当前 workspace，非本 slice 修改）
- UF-PF04 相关文件不存在（按计划未执行）
- `git status --short` 精确列出六个 allowed production/test 文件与唯一允许新增的 S2 implementation artifact

### Type Safety

- pyright: 0 errors, 0 warnings, 0 informations on all changed files
- 所有新增函数具有完整中文 Args/Returns/Raises docstring
- `_optional_raw_nullable_text` 返回类型为 `str | None`，与 `_optional_nullable_text` 一致
- `_validate_optional_upload_iso_date` 接受 `str | None`，与 `_validate_optional_upload_text` 签名一致

## Open Questions

无。

## Residual Risk

- S3 download shared-owner consumer 与最终 README：由后续 approved slice 负责。
- 唯一 tool baseline failure `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`：pre-existing UF-FIX01 follow-up，本 slice 前后 failure set 精确相等。
- `upload_filings_from` metadata strip parity：由后续 work unit 负责。
- `_snapshot_runtime_workspace_tree` 和 `_snapshot_tool_workspace_tree` 在两个测试文件中有近似实现：test isolation 可接受，非 blocking finding。

## Conclusion

**Pass**。UF-FIX04 S2 upload strict static admission 实现正确：calendar/year 唯一 owner 真正复用 S1 shared `parse_calendar_year` / `parse_iso_calendar_date`；CLI/tool 保留 raw date 且未重复解析；非法值在 state read、operation、runner、storage mutation 前以 typed usage error 拒绝；bool/0/负数/999/10000/格式/不存在日期/闰年均有覆盖；material 与 `upload_filings_from` 未被改变；LLM-facing schema/error 业务中立；严格类型/docstring 完整；测试真实且不过拟合。
