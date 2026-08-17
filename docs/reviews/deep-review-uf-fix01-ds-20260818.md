# Deep Review — UF-FIX01 fiscal-period prevalidation residual（最终独立深度审查）

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `0b7dced4`（accepted plan commit `gateflow: accept fiscal period validation plan`）
- Range: `0b7dced4..HEAD`，HEAD = `1ff79ab1`
  - S1 `f6b2d04c fix(fins): validate fiscal periods before upload`
  - S2 `1ff79ab1 test(fins): prove fiscal period entry contracts`
- Review time: 2026-08-18 03:15 +0800（本机系统时钟）
- Output file: `docs/reviews/deep-review-uf-fix01-ds-20260818.md`
- Included scope:
  - Production：`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/tools/upload_tools.py`
  - Tests：`tests/fins/test_fiscal_normalization_contracts.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_docling_upload_service.py`、`tests/cli/test_fins_commands.py`、`tests/fins/test_fins_ingestion_tools.py`
  - Docs：根 `README.md`、`dayu/fins/README.md`、`tests/README.md`、`docs/gateflow/*`、`docs/reviews/*`
- Excluded scope（按用户边界）：
  - 真实 CLI / Docling / 网络 calibration（UF-PF01/UF-PF12）未运行；
  - frozen evidence / accepted oracle / scenario registry 未触碰（位于仓库外 `/Users/leo/workspace/.dayu-cli-ci/`，两个提交的文件清单均不含此类文件）；
  - `upload_filings_from`、material fiscal metadata、download 财期别名、Host/Engine 均未修改（不在 diff 内）。
- Parallel review coverage：本 artifact 为 DS 独立审查通道；MiMo 通道 artifact 为 `docs/reviews/deep-review-uf-fix01-mimo-20260818.md`（未读取其内容，保持独立）。
- 审查方式：沿真实入口逐行读代码与测试（CLI → Service → Runtime → workflow/ID builder），独立运行受影响测试与全仓 pyright；未修改任何生产代码或测试，未运行真实 CLI calibration。

## 核对结论（对应用户要求的九项重点）

### 1. fiscal-period 唯一 owner：成立

- 业务 owner 单一：`dayu/fins/domain/filing_semantics.py` 的 `FiscalPeriod`（:37）、`FISCAL_PERIODS`（:96）、`normalize_fiscal_period`（:293），本轮未修改该 owner 文件。
- 唯一 admission 调用点：`ingestion_runtime.py:1280` 以 raw 值调用 `normalize_fiscal_period(request.fiscal_period, field_name="--fiscal-period")`，owner 完成 strip/uppercase 与闭集校验；该调用无任何 market 分支。
- duplicate parser `docling_upload_service.normalize_cn_fiscal_period` 已删除（含 `__all__` export），全仓扫描 `normalize_cn_fiscal_period` / `UNSUPPORTED_CN_FISCAL_PERIOD` / `unsupported_cn_fiscal_period` / 旧 CN/HK 文案在 `dayu`、`tests`、`utils` 及仓库内非历史文档中零命中。
- download 侧 `cn_form_utils.build_cn_filing_ids` 与 `parse_fiscal_period_filter_value` 是独立 download owner，plan 有意不收窄，本轮未触碰——不构成 owner 漂移。
- 已知 material 路径（`sec_upload_workflow.py:474`、`cn_pipeline.py:1090`）仍自行 `str(fiscal_period or "").strip().upper() or None`——pre-existing 且为 plan 明确分类的 `assigned to later work unit`，本轮未扩大该模式，反而收窄了 filing 路径，不判定为 finding。

### 2. 所有入口复用同一 admission：成立

- CLI：`dayu/cli/commands/fins.py:239` `_prevalidate_upload_filing_request` → `service_runtime.prevalidate_fins_upload_filing_request_for_workspace`（`service_runtime.py:62-95`）→ `_filing_upload_request_identity` 先跑静态校验，其后才构造 `FsFilingUploadStateRepository`（`create_directories=False`，无 mutation）与 published-state read；该调用位于 `FINS_DIRECT_SERVICE_FACTORY`（fins.py:243）之前。CLI 生产代码本轮零修改。
- tool：`upload_tools.py:102-106` `_upload_request_from_arguments` 以 raw 参数构造 `FinsUploadFilingRequest`（fiscal_period 用 `_required_text`，不做业务判断）→ `runtime.prepare_observed_upload`（`ingestion_runtime.py:3848-3885`）→ `_validate_runtime_upload_request`（:4714-4748）先做静态校验，之后才创建 observation / producer。
- runtime 直接启动：`start_upload` 同样先 `_validate_runtime_upload_request`，再 `_create_queued_record_with_start_lock` 与 `executor.submit`（:4686-4712）。
- Service/runner/workflow：`validate_fins_upload_filing_request` 首行即静态校验（:1477）；SEC/CN/HK facade 消费 `authoritative_request.normalized_fiscal_period`（`sec_upload_workflow.py:185,229,397`、`cn_pipeline.py:816,860,1862`）；`build_sec_filing_ids` / `build_cn_filing_ids` / `derive_report_kind` 参数已收窄为 `FiscalPeriod`，仅从 canonical typed 值投影，内部第二次 strip/uppercase 已删除。
- 无入口自建 period 解析；`ValidatedFinsUploadFilingRequest.normalized_fiscal_period: FiscalPeriod`（:784）与 `_StaticFinsUploadFilingValidation.normalized_fiscal_period: FiscalPeriod`（:839）使 canonical contract 由类型表达。

### 3. operation / workspace mutation 前拒绝：成立

- 代码顺序：非法 period 在 `_filing_upload_request_identity`（:1397-1413）内、published-state read（:4737）之前即以 `FinsUploadUsageError` 结束；CLI 侧在 Service factory / stream 前；tool 侧在 observation 创建前；runtime 侧在 durable job record 创建前。
- 测试证明（非日志反推）：CLI 矩阵（`tests/cli/test_fins_commands.py:1832-1840`）断言 factory_calls 空、service 零调用、workspace 树 before/after 快照一致、fresh 不创建 / seeded 不改变；tool 零副作用测试（`tests/fins/test_fins_ingestion_tools.py:1427-1437`）断言 state repository 零调用、executor 零提交、upload runner 零调用、observation registry 空、job store 无记录、workspace 树快照一致。

### 4. exit 2 / 具体 reason / 无 traceback：成立

- `dayu/cli/exit_codes.py:10` `EXIT_USAGE_ERROR = 2`；`fins.py:197-199` `FinsUploadUsageError` → 单行 `dayu-cli upload_filing: <message>` + exit 2，该分支不 log exception、不打印 traceback。
- reason 为 owner 投影的精确文案 `--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4`（`_USAGE_MESSAGES`，`ingestion_runtime.py:1044`）。
- CLI 矩阵测试逐 case 断言 `exit == 2`、`stdout == ""`、stderr 精确单行、`"Traceback" not in err`（:1832-1835）。
- tool 侧 `FinsUploadUsageError` 继承 `ValueError`（:743-762，`str` 即 `failure.message`），落入既有 `invalid_argument` envelope，测试断言精确 message 与既有 hint。
- 不变量兜底：`normalized_period is None` → `AssertionError`（:1286-1287）在 required/blank 检查先行的前提下不可达，属计划明确的 fail-closed invariant breach 信号。

### 5. US/CN/HK 一致性：成立

- admission 单一 market-neutral 分支（`ingestion_runtime.py:1274-1287`），旧 `if normalized_ticker.market in {"CN", "HK"}` 分支已删除。
- 测试三市场参数化：owner/admission 层 `tests/fins/test_fins_ingestion_runtime.py`（AAPL/600519/0700.HK × 合法 canonicalization 与非法统一 code/reason）；CLI 层 US `BANANA`、CN `9M`、HK `BANANA`；tool 层同三市场。US 从旧 exit 1（UF-A21 证据：`unexpected_runtime`）改为与 CN/HK 相同的 exit 2 静态拒绝——即本 work unit 的目标行为。

### 6. 合法行为不变：成立

- 文档 ID 稳定：`tests/fins/test_docling_upload_service.py` 新增 CN/SEC ID 精确 SHA1 锁定（`fil_cn_d43d69ac...` / `fil_sec_6aa49646...`），并证明 builder 内 form/period 归一变化不影响既有 canonical 输入输出；`ingestion_runtime.py:1327-1341` 的 ID 构造调用与 base 完全一致（含 `form_type=normalized_period` 这一 pre-existing CN 形态，base 0b7dced4 同）。
- `derive_report_kind` 六值映射与原 canonical 行为一致，测试补全 FY/H1/Q1-Q4 断言。
- missing / overlong 校验顺序与 code/message 未变（required → length → domain），既有矩阵 case（含 300 字符超长）仍通过。
- `FiscalPeriod` 六值与旧 CN/HK parser 闭集完全相同，US 合法值原来只做 strip/upper 放行，归一后对闭集内输入逐字节一致。
- action/overwrite/repair/publication 状态机、storage schema、Service 方法签名均未触碰。

### 7. README 触发：成立

- 根 `README.md`：命中用户可见 CLI 行为（闭集、normalization、exit 2、mutation 前拒绝），已最小更新，且对 tool 侧表述准确（tool 无 exit code，只承诺两入口 mutation 前拒绝）。
- `dayu/fins/README.md`：命中 Fins domain owner / static admission 段，已更新 period 同源与 market-neutral 契约。
- `tests/README.md`：命中测试职责段，已更新 UF-FIX01 覆盖说明。
- 未触发项正确未动：`dayu/engine`、`dayu/host`、`dayu/config` 目录零修改 → 对应 README 未动；分层/装配未变 → `dayu/README.md` 未动。

### 8. 测试与 pyright 证据：成立（本轮独立运行）

- `pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_docling_upload_service.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_service_runtime.py -q` → **822 passed**（27.28s，仅第三方 edgar deprecation warning）。
- `python -m pyright dayu/ tests/ utils/` → **0 errors, 0 warnings, 0 informations**（全仓）。
- `git diff 0b7dced4...HEAD --check` → 通过。
- 测试断言质量：绑定 owner 级 contract（canonical 值、field-name reason、closed code set）、入口级 contract（exit 2 / 单行 stderr / 无 traceback / 零调用 / 树快照）、runner 边界 canonical handoff（CLI fake 记录 `request.normalized_fiscal_period`，`test_fins_commands.py:397`；tool 测试经 `activate_observation` + holding executor 断言 runner 收到 typed canonical 请求），无“没有日志”式弱断言。
- 精确 production coverage 91% / 89% / 93%（合计 91%，≥80%）记录于 S2 artifact 并经两路 review 裁决；本轮未独立复跑 coverage，以文档证据为准。

### 9. 未越界修改冻结 evidence/oracle/scenario registry：成立

- 两个提交的完整文件清单均只含 allowlist（S1：2 个 production + 4 个测试 + gateflow/review docs；S2：1 个 production + 3 个 README + 测试 + gateflow/review docs）。
- frozen evidence 位于仓库外 `/Users/leo/workspace/.dayu-cli-ci/`；diff 中无任何 `workspace/`、evidence、oracle、scenario 相关文件。

## Findings

未发现实质性问题。

无 security、correctness、stability 或 maintainability 方面的证据型 defect。语义 owner 唯一且未扩散；所有入口共享同一 admission；拒绝先于一切 read/mutation；US/CN/HK 同规则同文案；合法输入行为逐字节保持；文档触发项与未触发项均处理正确。

## Open Questions

- 全量回归 15 个失败与本 work unit 的归因：见 Residual Risk 第 1 条。按用户指示终止了基线探针，未做 base 对比运行，无法给出 100% 排除证明，只能给出“无关联证据”判定。

## Residual Risk

1. **全量 suite（HEAD）15 failed / 8006 passed**：已捕获的失败中 ≥7 例位于 `tests/tools/test_combined_tools_acceptance.py`（truncate/fetch_more、provider 工具 acceptance、scene tags、web 并发串行策略），该文件及其生产模块（`dayu/tools`）不在本 diff 内；本 work unit 涉及的 `tests/fins`、`tests/cli` 全部通过（822/822）。判定：现有证据不支持与本 work unit 相关；未做基线复跑，不能 100% 排除。
2. 真实 CLI / Docling / 网络 calibration（UF-PF01/UF-PF12）未运行，frozen evidence/oracle/scenario 未刷新——按用户边界分配给后续 calibration 流程。
3. material fiscal metadata 与 download 财期别名仍宽于 filing 闭集——plan 已分类为 `assigned to later work unit` / 独立 filter owner 有意承诺。
4. 精确 coverage 数字（91/89/93）本轮未独立复跑，依据 S2 artifact 与两路 review 裁决。
5. 审查过程中的工作树插曲（探针误 pop 既有 stash）已恢复：HEAD 仍为 `1ff79ab1`，原 stash `stash@{0}` 保留，tracked 工作树 clean（仅存在 MiMo 通道的 untracked artifact）。

## Conclusion

**PASS**（无 blocking 或 material findings）。
