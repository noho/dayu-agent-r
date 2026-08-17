# UF-FIX01 最终独立深度审查

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `0b7dced4` (accepted plan commit)
- Output file: `docs/reviews/deep-review-uf-fix01-mimo-20260818.md`
- Included scope: 2 commits (`f6b2d04c`, `1ff79ab1`)，3 个生产文件、5 个测试文件、3 个 README、7 个 gateflow 文档
- Excluded scope: `docs/reviews/` 下的旧 review artifacts（过程文档，非生产代码）
- Parallel review coverage: 无

## 审查维度与证据

### 1. Fiscal-period 唯一 owner

**结论：通过。**

- `FiscalPeriod` 定义唯一：`dayu/fins/domain/filing_semantics.py:37` 为 `Literal["FY", "H1", "Q1", "Q2", "Q3", "Q4"]`。
- `normalize_fiscal_period` 定义唯一：同文件 `:293-314`，执行 `strip().upper()` → `FISCAL_PERIODS` 成员检查 → `ValueError` 或返回 `FiscalPeriod`。
- 本次变更删除了 `docling_upload_service.py` 中的 `normalize_cn_fiscal_period`（旧 CN-only owner），`__all__` 已同步移除。
- `ingestion_runtime.py` 改为从 `filing_semantics` 直接导入 `FiscalPeriod` 和 `normalize_fiscal_period`，不再从 `docling_upload_service` 导入 `normalize_cn_fiscal_period`。
- `build_cn_filing_ids` 和 `build_sec_filing_ids` 参数类型从 `str` 改为 `FiscalPeriod`，消除了函数内部的 `.strip().upper()` 重复规范化。
- `derive_report_kind` 参数类型从 `str` 改为 `FiscalPeriod`，内部不再调用 `normalize_cn_fiscal_period`，直接用 `==` 比较。
- `ValidatedFinsUploadFilingRequest.normalized_fiscal_period` 和 `_StaticFinsUploadFilingValidation.normalized_fiscal_period` 类型均从 `str` 改为 `FiscalPeriod`。
- `CnFiscalPeriod`（`cn_download_models.py:29`）是纯 `TypeAlias = FiscalPeriod`，不引入第二份语义。

### 2. 所有入口复用

**结论：通过。**

- CLI 入口（`test_fins_commands.py`）：新增 US (`AAPL`/`BANANA`)、CN (`600519`/`9M`)、HK (`0700.HK`/`BANANA`) 三个市场非法财期测试，均走同一 `_validate_fins_upload_filing_static` → `normalize_fiscal_period` 路径。
- CLI 合法输入规范化测试：`test_upload_filing_canonicalizes_period_before_validated_service_handoff` 覆盖 `" fy "` → `FY`、`" q2 "` → `Q2`、`" h1 "` → `H1`，验证 Service 收到 canonical 值。
- Tool 入口（`test_fins_ingestion_tools.py`）：`test_upload_tool_raw_period_is_canonical_at_runner_contract_boundary` 覆盖 US/CN/HK 三市场，验证 runner 收到 canonical `FiscalPeriod`。
- Runtime static admission（`test_fins_ingestion_runtime.py`）：`test_filing_fiscal_period_static_admission_is_market_neutral_and_canonical` 以 3 ticker × 8 period 组合验证市场中立规范化；`test_filing_fiscal_period_static_admission_rejects_every_market_before_state_read` 以 3 ticker × 3 非法 period 验证统一拒绝。
- Domain owner contract（`test_fiscal_normalization_contracts.py`）：覆盖 canonical 保留、大小写/空白规范化、缺失投影为 `None`、非法值拒绝（含字段名绑定）。

### 3. Operation/workspace mutation 前拒绝

**结论：通过。**

- CLI 测试 `test_upload_filing_usage_matrix_precedes_service_factory_and_workspace_mutation`：所有非法财期 case 均断言 `factory_calls == []`、`service.upload_filing_requests == []`、`workspace_root.exists() is seed_workspace`。
- Tool 测试 `test_upload_tool_filing_static_invalid_input_has_zero_side_effects`：断言 `state_repository.calls == []`、`state_repository.batch_calls == []`、`executor.submitted_job_ids == ()`、`runtime._observations == {}`、workspace tree 不变。
- `_ForbiddenFilingUploadStateRepository`：在 tool static admission 测试中注入，任何 state read 调用立即 `AssertionError`。

### 4. Exit 2 / 具体 reason / 无 traceback

**结论：通过。**

- CLI 测试断言 `exit_code == EXIT_USAGE_ERROR`（即 2），`captured.out == ""`，`captured.err` 包含精确 reason 文案。
- 新增 `assert "Traceback" not in captured.err` 断言，覆盖所有 usage matrix case。
- `UNSUPPORTED_FISCAL_PERIOD` usage message 从 `"CN/HK --fiscal-period 仅支持 Q1、Q2、Q3、Q4、H1、FY"` 改为 `"--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4"`，市场中立。
- `_USAGE_MESSAGES` 映射和 `FinsUploadUsageCode` enum 已同步更新。

### 5. US/CN/HK 一致性

**结论：通过。**

- 旧逻辑：CN/HK 走 `normalize_cn_fiscal_period`（仅 6 值），US 直接 passthrough（无校验）。
- 新逻辑：所有市场统一走 `normalize_fiscal_period`（同样 6 值），`_validate_fins_upload_filing_static` 中无 `market` 分支。
- 测试覆盖：3 ticker（US/CN/HK）× legal/illegal period 矩阵，确认行为一致。

### 6. 合法行为不变

**结论：通过。**

- `build_cn_filing_ids`：新增测试断言精确 SHA digest（`"fil_cn_d43d69ac06b7d39719b474b2a5f5a46404103b3a"`），确认 seed 格式不变（`normalized_ticker|normalized_form|fiscal_year|fiscal_period|amended`），只是 period 不再内部 `.strip().upper()`（由 caller 保证 canonical）。
- `build_sec_filing_ids`：同样断言精确 SHA，确认 seed 不变。
- `derive_report_kind`：扩展测试覆盖全部 6 值（`FY` → annual，`H1` → semi_annual，`Q1-Q4` → quarterly）。
- `cn_ids_from_normalized_form` 测试用 `" fy "` 作为 form_type 验证 form 仍由函数内部 `.strip().upper()` 处理（form 的规范化不受本次变更影响）。

### 7. README 触发

**结论：通过。**

- `README.md`：更新了 `fiscal_period` 的用户可见契约（接受值列表、US/CN/HK 一致性、exit 2 行为、mutation 前拒绝）。
- `dayu/fins/README.md`：更新了 filing 上传的财期 owner 描述（domain owner 统一处理、US/CN/HK 一致、pre-mutation 拒绝）。
- `tests/README.md`：更新了 UF-FIX01 owner coverage 描述（新增 runtime/tool/CLI 三入口财期规范化覆盖）。

### 8. 测试与 pyright 证据

**结论：通过。**

- pyright：0 errors, 0 warnings, 0 informations。
- 测试：190 个相关测试全部通过（`test_fiscal_normalization_contracts`、`test_fins_ingestion_runtime`、`test_fins_ingestion_tools`、`test_fins_commands` 中的财期相关 case）。
- 新增测试文件：`test_fiscal_normalization_contracts.py`（87 行，覆盖 domain owner contract）。
- 新增测试 case 数：CLI +3、runtime +2（参数化展开后覆盖 24+9 组合）、tool +2（参数化展开后覆盖 6+3 组合）、domain +7。

### 9. 未越界修改冻结 evidence/oracle/scenario registry

**结论：通过。**

- `docs/evidence/`、`docs/oracle/`、`docs/scenarios/` 目录不存在（无历史冻结文件）。
- `docs/gateflow/` 新增 7 个 UF-FIX01 过程文档（implementation/review/adjudication 记录），均为新增文件，非修改已有冻结内容。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `normalize_fiscal_period` 返回 `Optional[FiscalPeriod]`，在 filing context 中 `None` 输入已被前序 guard 拦截，`AssertionError` 是 belt-and-suspenders 防护。如果未来有人绕过前序 guard 直接调用，该 `AssertionError` 会暴露为 500 级错误而非用户可读 usage failure。当前无实际风险，因为调用链完整。
- `CnFiscalPeriod` alias（`cn_download_models.py`）虽然语义等价于 `FiscalPeriod`，但作为独立 symbol 存在可能在未来引入不必要的间接层。当前无实际风险。

## Conclusion

**pass。** UF-FIX01 work unit 从 plan commit `0b7dced4` 到 HEAD 的全部变更符合预期：fiscal-period 唯一 owner 收束到 `filing_semantics.normalize_fiscal_period`，US/CN/HK 三市场共享同一 admission 路径，非法值在 operation/workspace mutation 前以 exit 2 + 具体 reason + 无 traceback 拒绝，合法输入规范化后透传至 runner contract，README 已同步更新，测试覆盖充分，pyright 零错误，未越界修改冻结区域。
