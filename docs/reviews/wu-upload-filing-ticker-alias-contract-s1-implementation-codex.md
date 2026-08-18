# upload-filing-ticker-alias-contract — S1 implementation report

## 1. Gate 结论

- Work unit：`upload-filing-ticker-alias-contract`
- Slice：S1 `Company Ticker Identity migration checkpoint`
- Accepted plan commit：`5508d0445bd1d649fee54f4ec3d65f99e2484493`
- 工作分支：`codex/upload-filing-oracle`
- 初始基线：`git status --short` 无输出，HEAD 与 accepted plan commit 一致。
- 当前结论：S1 implementation 及 accepted F1/F2 fix 已完成，可进入 **S1 re-review**；本 checkpoint 不是可部署或可 close 状态，S2 仍为强制后续。
- 未提交、未暂存、未 push、未创建 PR。

## 2. 动机与语义 owner

问题真实存在：此前 ticker grammar、canonical/alias 去重、CompanyMeta 持久化、resolver、CLI、SEC/CN filing/material 与 storage lookup 各自推导同一业务事实，直接造成 `V.BA` grammar 不一致、fresh CompanyMeta 新 alias 被忽略，以及 material producer 可接受 alias 却不可靠写入同一 identity contract。

S1 采用以下唯一 owner 边界：

1. `dayu.fins.ticker_normalization.CompanyTickerIdentity` 与 `build_company_ticker_identity` 拥有 canonical ticker、market、exchange、accepted aliases、稳定去重和 `lookup_tickers()` 投影。
2. `CompanyMeta.ticker_identity` 是 durable company meta 中 ticker identity 的结构化真源；`CompanyMeta.to_dict/from_dict` 独占 strict flat JSON 投影与校验，canonical 不再重复写入 `ticker_aliases`。
3. FMP/SEC/CN/CLI 只负责提供声明输入或筛掉不可信外部响应中的非法 token，不再拥有 canonicalization/dedupe 规则。
4. `resolve_upload_company_meta_decision` 是 filing/material 单进程 S1 merge decision owner；fresh 新 alias 必须 stage，fresh unchanged 才 keep，stale/new 均合并既有与声明 aliases。
5. `UploadCompanyNameRequiredError` 是“new/stale company meta 缺少公司名”的唯一异常语义；ingestion runtime 只捕获该类型并投影 `COMPANY_NAME_REQUIRED`，builder/identity mismatch `ValueError` 不会被误分类。
6. storage S1 只消费 `ticker_identity.lookup_tickers()`；workspace uniqueness、authoritative commit-time merge 与 typed conflict 的 owner 仍属于 S2。

## 3. 实现内容

### 3.1 Identity、CompanyMeta 与 resolver

- 新增不可变 `CompanyTickerIdentity`、唯一 builder 和 lookup projection。
- single-section US grammar 接受 `V.BA -> V-BA` 与 `AAPL.SW -> AAPL-SW`，继续执行完整 canonical 长度上限与非法字符/多分节拒绝。
- `CompanyMeta` 删除散落的 `ticker/market/ticker_aliases` fields，切换为 `ticker_identity`；flat JSON 缺失 `ticker_aliases`、类型错误、market mismatch 或非法 alias 均 fail closed。
- FMP public result 改为 `ticker_identity + company_name`；SEC、CN download 与 CLI 全部复用 builder，删除各自 duplicate normalizer/dedupe。

### 3.2 Filing/material 与 CLI/tool

- filing 与 material 共同使用 `resolve_upload_company_meta_decision` / `stage_upload_company_meta_decision`。
- 新增稳定入口 `stage_company_meta_for_upload`，SEC/CN material 不再保留重复 fresh/alias decision；fresh meta 新增 alias 会 stage 并保留既有 name/id/version，stale/new 会 stable union aliases。
- 新增 `UploadCompanyNameRequiredError`；只有 new/stale create/update 缺少公司名时由 decision owner 抛出。`ingestion_runtime` 的 usage catch 已收窄到该专用类型，identity mismatch 与 builder `ValueError` 保持非 usage failure，等待 S2 最终 typed corruption 投影。
- CLI 三个 upload 命令的 `--ticker` help 自足说明 CSV 第一项 canonical、后续项为显式同公司 aliases、声明受信任且不联网核验、成功保存后查询同一 corpus。
- upload filing/material tool schema 自足说明单 canonical `ticker` 与 `ticker_aliases`，并明确两种 upload kind 均适用；未修改 read schema。

Material aliases 直接数据流：

```text
FinsUploadMaterialRequest.ticker_aliases
  -> service_runtime 的 SEC/CN material handoff
  -> SecPipeline/CnPipeline material producer
  -> stage_company_meta_for_upload
  -> resolve_upload_company_meta_decision
  -> stage_upload_company_meta_decision
  -> S1 CompanyMetaRepositoryProtocol.upsert_company_meta
```

对应 durable owner tests 位于 `test_sec_pipeline_upload_material_stream.py` 与 `test_cn_pipeline.py`，均从 committed CompanyMeta 和 storage route 断言 aliases，没有以 event payload 代替持久化证据。

### 3.3 Storage 与 consumer

- storage CompanyMeta read/write/index 改为消费 `ticker_identity` / `lookup_tickers()`，删除 storage duplicate alias normalizer。
- 按 S1 临时契约保留 `resolve_existing_ticker`、alias-to-`list[str]` index 与 read-time late multiple-owner `ValueError`，未提前实现 unique index 或 typed conflict。
- 6-K inventory consumer 机械迁移到 `entry.company_meta.ticker_identity.canonical_ticker`，并以 `reconcile_active_6k_primary_documents(..., target_tickers=None)` 的 public-path test 触达 discovery；fix gate 又补齐 publication 前非候选/非法 files、public filter normalization/empty rejection 与单文档失败 rollback 行为测试。
- `read_runtime.py` 仅将 CompanyMeta market 读取机械迁移到 `company_meta.ticker_identity.market`，以满足 strict CompanyMeta field migration 和全量 pyright；read route、fallback、schema、错误投影均未改变。Controller F3 已接受该最小必要 consumer 迁移。

## 4. Changed files

### 4.1 Production

- `dayu/fins/ticker_normalization.py`
- `dayu/fins/domain/document_models.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/resolver/fmp_company_info.py`
- `dayu/fins/pipelines/upload_company_meta.py`
- `dayu/fins/pipelines/sec_company_meta.py`
- `dayu/fins/pipelines/cn_download_company_meta.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`
- `dayu/fins/storage/_fs_company_meta_core.py`
- `dayu/fins/storage/_fs_storage_utils.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/arg_parsing.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/tools/read_runtime.py`（仅一行 CompanyMeta field projection 机械迁移；route/schema 留在 S2）

### 4.2 Tests

- 新增 `tests/fins/test_ticker_normalization.py`
- 更新 `tests/cli/test_arg_parsing.py`
- 更新 `tests/cli/test_fins_commands.py`
- 更新 `tests/cli/test_prompt_command.py`
- 更新 `tests/cli/test_upload_filings_from_command.py`
- 更新 `tests/fins/test_cn_pipeline.py`
- 更新 `tests/fins/test_fins_ingestion_runtime.py`
- 更新 `tests/fins/test_fins_ingestion_tools.py`
- 更新 `tests/fins/test_fins_storage_atomicity.py`
- 更新 `tests/fins/test_fins_storage_provider.py`
- 更新 `tests/fins/test_fmp_company_info_resolver.py`
- 更新 `tests/fins/test_processor_read_consistency.py`
- 更新 `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- 更新 `tests/fins/test_sec_pipeline_download.py`
- 更新 `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- 更新 `tests/fins/test_sec_pipeline_upload_material_stream.py`
- 更新 `tests/service/test_entrypoint_runtime.py`
- 更新 `tests/service/test_fins_direct.py`
- 更新 `tests/tools/test_combined_tools_acceptance.py`

README 未修改：accepted S1 明确把完整 public/storage/read 语义文档留到 S2，避免用 checkpoint 半契约改写最终用户说明。

## 5. 验证结果

所有命令均在 `source .venv/bin/activate` 后执行。

### 5.1 Focused 与回归

- F1/F2 定向 owner/runtime/public-path tests：`8 passed`。
- S1 focused files（排除单独记录的既有 containment 文案失败）：`1674 passed, 2 skipped, 1 deselected`。
- `pytest tests/fins -q --tb=short`：`1538 passed, 1 skipped`。
- `coverage run --branch -m pytest tests/fins tests/cli tests/service tests/tools -q --tb=short`：`3547 passed, 9 skipped, 6 failed`。

后一个回归组的 6 个失败均不在本次 changed path，且与本次 diff 无逻辑/数据同源关系：

1. `tests/cli/test_init_workspace.py::test_first_real_discovery_is_private_and_publishes_only_config`
2. `tests/cli/test_init_workspace.py::test_legal_raw_fins_roots_use_one_real_private_discovery_without_rewrite[absolute]`
3. 同一参数化用例 `[relative]`
4. 同一参数化用例 `[unconfigured]`
5. `tests/cli/test_upload_filings_from_command.py::test_upload_filings_from_usage_empty_and_write_failures`：既有 production path 把 `UploadScriptPublishError` 落入 generic safe error，测试期待 containment-specific 文案；该路径本次未修改。
6. `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`：既有 `dayu/service/fins_direct.py -> dayu.fins.download_contract` import boundary；两文件均未修改。

按用户明确边界，这些属于其它 findings，未在 S1 越界修复；交由后续 work unit/controller triage。

### 5.2 Coverage

使用 focused + `tests/fins tests/cli tests/service tests/tools` 生成 branch coverage，并对每个修改生产文件逐一执行 `coverage report --include=<file> --fail-under=80`。

| Production file | Branch coverage | Gate |
| --- | ---: | --- |
| `dayu/cli/arg_parsing.py` | 99% | pass |
| `dayu/cli/commands/fins.py` | 87% | pass |
| `dayu/fins/domain/document_models.py` | 93% | pass |
| `dayu/fins/ingestion_runtime.py` | 88% | pass |
| `dayu/fins/pipelines/cn_download_company_meta.py` | 83% | pass |
| `dayu/fins/pipelines/cn_pipeline.py` | 92% | pass |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 91% | pass |
| `dayu/fins/pipelines/sec_company_meta.py` | 100% | pass |
| `dayu/fins/pipelines/sec_download_workflow.py` | 87% | pass |
| `dayu/fins/pipelines/sec_pipeline.py` | 82% | pass |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 92% | pass |
| `dayu/fins/pipelines/upload_company_meta.py` | 97% | pass |
| `dayu/fins/resolver/fmp_company_info.py` | 92% | pass |
| `dayu/fins/storage/_fs_company_meta_core.py` | 86% | pass |
| `dayu/fins/storage/_fs_storage_utils.py` | 81% | pass |
| `dayu/fins/ticker_normalization.py` | 91% | pass |
| `dayu/fins/tools/read_runtime.py` | 82% | pass |
| `dayu/fins/tools/upload_tools.py` | 91% | pass |

F1 已关闭：独立执行 `coverage run --branch -m pytest -q tests/fins/test_sec_pipeline_download.py` 后，6-K 文件为 `91%`，`coverage report --include=dayu/fins/pipelines/sec_6k_primary_document_repair.py --fail-under=80` 通过。所有 18 个实际修改生产文件逐一执行 `--fail-under=80` 均通过。

### 5.3 类型、格式与残留

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- duplicate helper scan：`_canonicalize_ticker_alias`、`_normalize_company_ticker_aliases`、`_normalize_ticker_aliases`、`normalize_sec_ticker_aliases`、`_merge_ticker_aliases`、`_normalize_ticker_token`、`_dedupe_ticker_aliases` 均零命中。
- multiline old `FmpCompanyInfo(canonical_ticker=..., ticker_aliases=...)`：零命中。
- `upsert_company_meta_for_upload`：零命中。
- exact legacy `company_meta.ticker/market/ticker_aliases` 与 `existing_meta.*` field access：零命中；原计划宽 regex 命中的条目均为合法 `ticker_identity.*` 前缀。
- material scan 显示 request aliases 仍经 service runtime 进入 SEC/CN `stage_company_meta_for_upload`，并进入统一 decision/stage，未发生 accept-ignore。
- `UploadCompanyNameRequiredError` 仅在 `_require_upload_company_name` 的空名称分支抛出；`ingestion_runtime` 对 decision 的 catch 精确为 `except UploadCompanyNameRequiredError`，不再 blanket catch `ValueError`。

## 6. S1 临时允许项与 residual risk

1. **S1 route 半契约（covered by approved S2）**：`resolve_existing_ticker`、`_resolve_existing_ticker_by_company_alias`、`_build_company_alias_index`、`_build_company_alias_index_from_meta` 与 read runtime 旧 fallback 仍有命中；这是 accepted plan 明确允许的 S1 residue，不是 work unit 完成信号。
2. **Late conflict（covered by approved S2）**：alias index 仍为 `dict[str, list[str]]`，多 owner 仍在 read 时抛既有 `ValueError`；未实现 unique route 或 typed conflict。
3. **Snapshot/lost-update window（covered by approved S2）**：`UploadCompanyMetaDecision.company_meta` 与 `CompanyMetaRepositoryProtocol.upsert_company_meta` 暂存 final snapshot；尚无 commit-time authoritative merge、workspace identity lock 或 conflict-before-publication 保证。
4. **Read contract（covered by approved S2）**：read route/schema/failure projection 未修改；仅有 strict CompanyMeta 所必需的一行 field projection 迁移。
5. **F1/F2（fixed in current slice）**：6-K branch coverage 已升至 91%；company-name usage projection 已改为专用异常，identity mismatch/builder `ValueError` 不再伪装为 `COMPANY_NAME_REQUIRED`。
6. **Regression baseline failures（assigned to later work unit/controller triage）**：§5.1 的 6 项已由 controller 在 accepted baseline 隔离复现，未越界修复。
7. **F3（accepted-with-note）**：保留 `read_runtime.py` 一行机械 field projection，S2 仍拥有 read route/schema/failure projection。
8. **F4（rejected-with-reason）**：现有 upload help 已自足且不暴露内部 producer 术语，本 fix 未修改 help。
9. **明确未实施**：S2 lock/unique route/typed conflict、UF-PF05、oracle/scenario/frozen evidence、其它 findings、README；均未混入当前 diff。

## 7. Next gate

下一 gate：**S1 re-review**。

Re-review 必须重点验证：

- F1 的新增测试均为有效 owner/public-path 行为，且 6-K 独立 `--fail-under=80` 稳定通过；
- F2 只有缺公司名抛 `UploadCompanyNameRequiredError`，identity mismatch/builder `ValueError` 不会投影 `COMPANY_NAME_REQUIRED`；
- F3 保持 controller 接受的一行机械迁移，F4/help 与 S2/storage/read/README 均无扩张。

本实现到此停止，不提交。
