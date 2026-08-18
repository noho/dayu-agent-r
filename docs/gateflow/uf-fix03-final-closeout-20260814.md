# UF-FIX03 final closeout

## Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Branch：`codex/upload-filing-oracle`
- Design documents：`docs/host/design.md`、`docs/engine/design.md`
- Frozen findings/predicates：`UF-FIX03`、`upload_filing.irrelevant-and-repeated-options`、`upload_filing.direct-boundary-and-summary`、`upload_filing.malformed-and-empty-input`
- Gate result：`final closeout pass`
- Draft PR gate：按用户明确要求跳过；本 work unit 不创建 PR。
- UF-PF03：按用户明确要求未执行。

## Goal confirmation

问题动机成立。修复前存在两类同源缺陷：

1. `upload_filing` 终态把请求文件数误当作已存储文件数，无法表达 rejected/skipped/deleted/failed 的零 publication 事实。
2. 已知失败在多个下游边界重新从异常或字符串推断，导致 code、公开 reason、文件标签与 stderr 安全缺少唯一 owner。

正确语义 owner 已收敛为：

- publication owner 产生 `stored_file_count`，只统计成功提交的 original filing；请求 owner 产生 `requested_file_count`。
- `FinsUploadFailureReason` 及其 mapper/canonical label helper 产生唯一五字段 typed failure projection。
- Service、direct runtime、durable summary 与 CLI 只消费 typed summary/failure，不根据异常字符串重新分类。
- filing content admission 在 publication 前完成 empty/corrupt/mixed fail-fast；workflow 只消费 typed admission failure。

## Accepted implementation

### S1：summary count owner

- 新增并贯通 `requested_file_count` / `stored_file_count`，删除旧 `uploaded_files` 语义。
- `stored_file_count` 只在 original asset 成功存储后累计；derived asset 不计数。
- `ok` 要求 stored 等于 requested；`skipped/deleted/cancelled/failed` 的 stored 恒为 0。
- durable 与 direct terminal summary 消费同一 typed summary。
- Accepted commit：`607bfa4f`。

### S2：typed failure 与原子 admission

- 建立 exact 五字段 `FinsUploadFailureReason` contract 与 canonical public file label owner。
- empty filing 在 converter/batch/publication 前以 `empty_input_file` 拒绝。
- corrupt PDF、corrupt DOCX 与 valid+corrupt mixed batch 在 SEC/CN/direct 路径均 fail-fast，整批零 publication、stored 为 0。
- known failure 只由 typed owner 映射稳定 kind/code/message/retry hint；raw cause 仅保留在 operator log。
- Accepted commit：`a65cec93`。

### S3：CLI/direct boundary

- CLI generic unknown failure 仅输出固定、可行动的 `--log-file PATH` 指引；traceback、绝对路径、异常 repr 与底层文本不进入普通 stderr。
- terminal detail 顺序保证 renderer 的 8 项上限内包含 requested/stored、kind/code、canonical file label 与 bounded reason。
- direct `upload_filing` 正向集成测试先读回真实 Fins assets，再证明未创建 Host Run、EventLog、Memory、Tool Trace、runtime lane 或 legacy ingestion job。
- README 按职责更新；未改变 direct Fins command boundary。
- Accepted commit：`c54a4fd8`。

### Aggregate review F1 fix

- 删除 SEC/CN filing workflow 两个不可达的 `except DoclingConversionError` 及未使用 import，避免未来形成 `file_label=None` 的第二个退化 projection owner。
- 新增 AST owner guard，锁定 filing handler 为 `FinsUploadFailureError -> OSError -> Exception`，并确认 material handler 边界不变。
- Fix artifact：`docs/gateflow/uf-fix03-aggregate-review-fix-20260814.md`。

## Review result

- S1、S2、S3 均完成 implementation review、finding adjudication、fix 与 re-review。
- Aggregate deep review：AgentMiMo `PASS`；AgentDS `PASS`，AgentDS 提出的低严重度 F1 被 controller 接受并修复。
- Aggregate post-F1 re-review：AgentMiMo `PASS`；AgentDS `PASS`，无新的 correctness/stability finding。
- MiMo 首轮关于 deleted/cancelled requested 可大于 0 的 LOW 观察不升级：accepted plan 明确规定 `requested>=0 && stored==0`；CLI delete 的 `files=()` 由 request validator owner 保证，未发现 production correctness 反例。

## Final validation

- Final affected regression：
  `pytest -q tests/fins tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -k 'not test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect'`
  -> `1544 passed, 1 skipped, 1 deselected, 3 warnings`。
- Full pyright：`python -m pyright dayu/ tests/ utils/` -> `0 errors, 0 warnings, 0 informations`。
- S1-S3 focused regression：`473 passed, 3 warnings`；aggregate coverage `88%`。
- Aggregate F1 affected regression：`334 passed, 3 warnings`。
- Modified production coverage：broader `cn_pipeline.py 94%`、`sec_upload_workflow.py 95%`；S3 modified `commands/fins.py 86%`、`ingestion_runtime.py 91%`。
- `git diff --check`：pass。
- 三个 warning 均为既有 `edgar` 第三方 deprecation warning。

精确 deselect 的既有测试 `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 的 fixture 缺少当前 contract 必填的 `company_name`。该问题在本 work unit 基线已存在，属于 upload-tool test/contract owner；本修复未添加生产 fallback、兼容 shim 或 fixture 补偿。

## Frozen and no-touch audit

- `docs/cli_ci_scenarios.json` SHA-256：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`。
- `docs/cli_ci_oracles.json` SHA-256：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`。
- 两个 frozen JSON、第一轮 evidence 与 UF-PF03 evidence 均未修改。
- `dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/service/**` production、`dayu/fins/storage/**` 未修改。
- 未创建 Host/Engine/runtime/legacy ingestion 补偿路径；未创建 PR、未 push。

## Explicit exclusions and residual risks

- 日期/年份、ticker alias、格式 capability、multi-file primary/collision、existing-source repair、并发和 company meta warning 未进入本 work unit。
- 真实 Docling 多平台损坏样本差异保留给 UF-PF03；本轮只执行自动化真实 CLI subprocess 测试，不将其登记为 UF-PF03 evidence。
- material generic failure 的公开文本边界不属于三个 frozen `upload_filing` predicates，保留给独立 material failure-semantics work unit。
- AST owner guard 对外层 `try` 结构较严格；这是防止 typed owner 漂移的显式合同锁，未来结构性重构需同步审查该合同。

## Closeout decision

实现、测试、双路 review、finding fix/re-review、README 检查、frozen/no-touch audit 均完成。目标范围内无未分类 blocker，work unit 可以在当前分支本地提交并关闭。
