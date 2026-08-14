# upload-filing-ticker-alias-contract — S1 fix report

## 1. Gate metadata

| 字段 | 值 |
| --- | --- |
| Gate | `S1 fix` |
| Work unit | `upload-filing-ticker-alias-contract` |
| Accepted plan commit | `5508d0445bd1d649fee54f4ec3d65f99e2484493` |
| Controller adjudication | `docs/reviews/wu-upload-filing-ticker-alias-contract-s1-code-review-controller-adjudication.md` |
| Review artifacts | `docs/reviews/code-review-20260814-235645.md`; `docs/reviews/code-review-20260815-000420.md` |
| Fixed findings | `F1`, `F2` |
| Completion status | `fix complete` |
| Next gate | `S1 re-review` |

本 fix 保持在同一未提交 S1 workspace 中；没有 clear、commit、stage、push 或 PR 操作。

## 2. First-principles judgment 与 owner boundary

F1/F2 动机均成立：

- F1 不是生产行为错误，但修改生产文件的逐文件 branch coverage 低于项目与 accepted plan 的硬门槛；应通过真实 owner/public-path 行为测试关闭，不能改生产逻辑或规避 coverage。
- F2 是错误原因语义漂移：`ValueError` 既代表 builder/identity failure，也被 runtime 当成“缺公司名”。以异常基类识别业务原因无法保证唯一 owner，必须由 company-meta decision owner 产生专用异常，runtime 只投影该类型。

Fix 后 owner contract：

1. `UploadCompanyNameRequiredError` 唯一表示 new/stale create/update 需要 stage 且公司名为空。
2. `resolve_upload_company_meta_decision` 仍拥有何时需要公司名的状态判断；`_require_upload_company_name` 是唯一抛出点。
3. `ingestion_runtime` 只捕获 `UploadCompanyNameRequiredError` 并映射 `COMPANY_NAME_REQUIRED`。
4. builder invalid 与 existing/incoming identity mismatch 继续抛普通 `ValueError`，不被 company-name usage branch 捕获；S2 再决定最终 storage corruption typed projection。

## 3. Finding resolution

### F1 — fixed：6-K 单文件 branch coverage

只在 `tests/fins/test_sec_pipeline_download.py` 增加行为有效测试：

- publication 前 public owner 对非 6-K、无 HTML、payload 缺失的稳定早退，以及非法 `meta.files` 的 fail-closed；
- standalone public path 对 ticker 去空/大写/稳定去重、空 ticker filter、空 document filter 的合同；
- 单文档 reconcile 异常时 caller batch rollback，published source meta 保持不变。

生产文件 `sec_6k_primary_document_repair.py` 没有为 coverage 修改任何逻辑。独立结果：

```text
116 passed
sec_6k_primary_document_repair.py: 181 statements, 60 branches, 91%
coverage report --include=dayu/fins/pipelines/sec_6k_primary_document_repair.py --fail-under=80: pass
```

### F2 — fixed：company-name typed failure owner

生产变更：

- `upload_company_meta.py` 新增 `UploadCompanyNameRequiredError(ValueError)`。
- 通用 `_require_company_meta_field` 收敛为语义明确的 `_require_upload_company_name`；只有空公司名分支抛专用异常。
- decision 的 identity mismatch 继续抛普通 `ValueError`，builder `ValueError` 也保持原类型。
- `ingestion_runtime.py` 从 `except ValueError` 收窄为 `except UploadCompanyNameRequiredError`。

测试证明：

- missing 与 stale CompanyMeta 缺公司名均抛专用异常；
- 同一 decision 中 invalid builder alias 的异常不是 `UploadCompanyNameRequiredError`；
- strict-valid published `MSFT` CompanyMeta 与 incoming `AAPL` mismatch 在 runtime 仍抛 identity `ValueError`，且不是 `FinsUploadUsageError/COMPANY_NAME_REQUIRED`；
- 原 stale company-name usage test 继续得到精确 `COMPANY_NAME_REQUIRED`。

### F3 — accepted-with-note：保持不动

保留 `read_runtime.py` 的 `company_meta.ticker_identity.market` 一行机械 consumer 迁移。没有改 read route、normalize/upper fallback、schema 或 failure projection；其余 read contract 仍由 S2 所有。

### F4 — rejected-with-reason：不修改

未修改 upload help。Controller 已裁决现有 upload-only help 在 `upload_material --help` 语境下自足；增加“material CompanyMeta producer”等内部术语反而违反 LLM-facing 文本约束。

## 4. Fix changed files

### Production

- `dayu/fins/pipelines/upload_company_meta.py`
- `dayu/fins/ingestion_runtime.py`

### Tests

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_sec_pipeline_download.py`

### Artifacts

- 更新 `docs/reviews/wu-upload-filing-ticker-alias-contract-s1-implementation-codex.md`
- 新增本 artifact：`docs/reviews/wu-upload-filing-ticker-alias-contract-s1-fix-codex.md`

README 不更新：S1 checkpoint 仍保留 route/snapshot 半契约，完整语义文档按 accepted plan 留到 S2。

## 5. Validation

所有命令均在 `source .venv/bin/activate` 后执行。

### Tests

- F1/F2 定向 tests：`8 passed`。
- S1 focused：`1674 passed, 2 skipped, 1 deselected`；deselected 为 controller 已验证的 baseline CLI containment failure。
- `pytest tests/fins -q --tb=short`：`1538 passed, 1 skipped`。
- coverage regression `tests/fins tests/cli tests/service tests/tools`：`3547 passed, 9 skipped, 6 failed`。

6 个失败与 controller 隔离基线验证完全一致，本 fix 不处理：

1. `test_first_real_discovery_is_private_and_publishes_only_config`
2. `test_legal_raw_fins_roots_use_one_real_private_discovery_without_rewrite[unconfigured]`
3. 同一参数化用例 `[absolute]`
4. 同一参数化用例 `[relative]`
5. `test_upload_filings_from_usage_empty_and_write_failures`
6. `test_service_does_not_import_forbidden_layers`

### Coverage

- 6-K 独立测试文件采集：`91%`，`--fail-under=80` 通过。
- 覆盖率回归数据上，18 个实际修改生产文件逐一执行 `coverage report --include=<file> --fail-under=80`，全部通过。
- 最低文件为 `_fs_storage_utils.py: 81%`；本 fix 新增修改的 `ingestion_runtime.py: 88%`、`upload_company_meta.py: 97%`。

### Type、format 与 residue

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- duplicate ticker normalizer/dedupe helpers：零命中。
- exact legacy CompanyMeta fields：零命中。
- old multiline `FmpCompanyInfo(canonical_ticker=..., ticker_aliases=...)`：零命中。
- `upsert_company_meta_for_upload`：零命中。
- material aliases 仍由 request 经 service runtime 贯通 SEC/CN `stage_company_meta_for_upload` 与统一 decision/stage，未 accept-ignore。
- `UploadCompanyNameRequiredError` 生产抛出点唯一；ingestion decision catch 精确为该 typed exception。
- S1 临时 route/list-index/fallback symbols 仍按 accepted S2 residual 保留。

## 6. Residual risk classification

| Risk / finding | Classification | 状态 / owner |
| --- | --- | --- |
| F1 6-K coverage | fixed in current slice | 91%，独立门槛通过 |
| F2 company-name 错误投影 | fixed in current slice | typed owner + runtime exact catch |
| F3 read runtime 一行迁移 | covered by later approved slice | 当前机械迁移 accepted-with-note；S2 完成 read contract |
| F4 help finding | rejected-with-reason | controller 已关闭，不修改 |
| S1 snapshot/lost-update window | covered by later approved slice | S2 commit intent/authoritative merge |
| S1 late alias conflict/list index | covered by later approved slice | S2 unique route/typed conflict |
| read fallback/schema/failure projection | covered by later approved slice | S2 |
| 6 个 baseline failures | assigned to later work unit/controller triage | controller 已隔离复现，不属于本 WU |

没有未分类 residual risk。没有实现 S2/storage corruption/route/lock、README、UF-PF05、oracle/scenario/frozen evidence 或其它 finding。

## 7. Next gate

下一 gate：**S1 re-review**。

Re-review 应验证 F1/F2 的直接证据、全部 coverage gate 与 scope containment；两路 re-review 无 blocker 后才可创建 accepted S1 local commit并进入 S2。本 fix 按用户要求在此停止，不提交。
