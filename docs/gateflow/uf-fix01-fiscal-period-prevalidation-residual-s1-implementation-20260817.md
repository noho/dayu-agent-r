# UF-FIX01 fiscal-period prevalidation residual — S1 Implementation

## Gate metadata

- work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- slice：`S1-owner-admission`
- implementation agent：AgentCodex
- artifact completion：controller（AgentCodex 完成代码与验证后，在 artifact 写入阶段无工具产出停滞）
- status：`implementation-complete / awaiting code review`
- accepted plan commit：`0b7dced4`
- next entry point：S1 parallel code review

## Owner and root-cause evidence

- 唯一业务 owner 保持为 `dayu.fins.domain.filing_semantics.FiscalPeriod`、`FISCAL_PERIODS` 与
  `normalize_fiscal_period`；本 slice 未修改 owner production 文件。
- 根因位于 `ingestion_runtime._validate_fins_upload_filing_static`：原实现仅对 CN/HK 调用 pipeline
  duplicate parser，US 仅执行 `strip().upper()` 后放行。
- 修复位于 owner 的直接上游 admission projection：所有市场统一调用 domain owner，并将 owner
  `ValueError` 投影为 closed `UNSUPPORTED_FISCAL_PERIOD` usage failure。

## Changed files and contracts

- `dayu/fins/ingestion_runtime.py`
  - 删除 market-specific parser 分支，所有市场共享 owner validation。
  - 新 closed code/value 为 `UNSUPPORTED_FISCAL_PERIOD / unsupported_fiscal_period`，精确 reason 为
    `--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4`。
  - static/validated request 的 canonical 字段收窄为 `FiscalPeriod`。
- `dayu/fins/pipelines/docling_upload_service.py`
  - 删除 duplicate `normalize_cn_fiscal_period` 与 export。
  - upload-only CN/SEC ID builders 和 `derive_report_kind` 只消费 `FiscalPeriod`；删除 fiscal-period
    的第二次 strip/uppercase。
  - CN `form_type.strip().upper()` 保持不变；canonical 合法输入的 ID 用精确旧输出锁定。
- `tests/fins/test_fiscal_normalization_contracts.py`
  - 新增六个合法值、大小写/首尾空白、optional missing 和非法值/field-name owner contract。
- `tests/fins/test_fins_ingestion_runtime.py`
  - 新增 US/CN/HK 合法 canonicalization 与非法值统一 code/reason、static identity 前失败 contract。
  - 更新 closed code/message contract。
- `tests/fins/test_docling_upload_service.py`
  - 删除 duplicate parser 测试，补齐六值 report-kind 与 canonical ID 不变断言。
- `tests/cli/test_fins_commands.py`
  - 仅同步既有 UF-024 精确 reason；未新增 S2 entry cases。

## Validation

- focused contract tests：owner `87 passed`；admission 选择集 `34 passed`（其中新增市场参数化 33 cases，
  另含既有 closed mapping contract 1 case）；ID/report-kind `1 passed`；既有 CLI usage matrix `43 passed`。
- S1 affected suite：`702 passed, 3 warnings`；warnings 为既有第三方 edgar deprecation。
- S1 seven-path pyright：`0 errors, 0 warnings, 0 informations`。
- `rg`：旧 duplicate parser、CN/HK 专用 enum/value/message 以及 upload builder 财期重复 normalization 无命中。
- `git diff --check`：通过。
- allowlist：仅六个 S1 code/test 文件与本 artifact。

## Docs decision and residual risks

- README 更新属于 S2，S1 不提前修改行为文档。
- 未运行真实 CLI/Docling/network calibration；未修改 frozen evidence、accepted oracle 或 scenario registry。
- S2 仍需补 CLI/tool entry、exit 2、no-start/no-mutation/no-traceback、schema description、README 与覆盖率证明。
- AgentCodex 在 artifact 写入前出现无工具产出停滞；controller 仅根据其已完成 diff 与验证记录补写本 durable
  handoff，未改变实现。
