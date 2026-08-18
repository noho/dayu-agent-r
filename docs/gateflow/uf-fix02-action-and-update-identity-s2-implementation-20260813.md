# UF-FIX02 action-and-update-identity — S2 Implementation

## 1. Gate metadata

- Work unit：`UF-FIX02 action-and-update-identity`
- Gate：`implementation`
- Slice：`S2 — Complete-set replacement, restore, and cross-market propagation`
- Decision：**IMPLEMENTATION PASS**
- Accepted plan：`docs/gateflow/uf-fix02-action-and-update-identity-plan-20260813.md`
- Accepted S1 commit / current HEAD：`08316516ca3da7f98299ee90d3fa753c32c59020`
- Branch：`codex/upload-filing-oracle`
- Preflight：工作树 clean，HEAD 精确匹配 accepted S1 commit，分支不是 protected trunk。
- Execution policy：local-only；未进入 code review，未 commit、push 或创建 PR；未执行 UF-PF02 focused-real。
- Artifact path：`docs/gateflow/uf-fix02-action-and-update-identity-s2-implementation-20260813.md`

## 2. First-principles judgment and owner

问题成立。existing full-input update 的业务含义是“同一 canonical source identity 的完整文件集合替换”，不是“在旧目录中追加新 blob 后更新 meta”。修复前 shared owner 只在 `overwrite=True` 时 reset；普通 changed update 会把新 blob 写入仍包含旧文件的 staging source，改名时 commit validator 直接以“meta files 与 physical business files 不双向一致”拒绝发布。这与 CLI、SEC/CN/HK facade 或 basename identity 无关，根因位于 filing/material 共用 publication owner。

唯一 owner 与真源：

- action/admission 与 deleted no-skip：accepted S1 的 `resolve_upload_action(...)`、`evaluate_upload_overwrite_precondition(...)`、`_can_skip_upload(...)`；S2 不重定义。
- 完整文件集合替换：`DoclingUploadService._store_upload_assets(...)`。
- exact target reset：`SourceDocumentRepositoryProtocol.reset_source_document(...)` 的既有实现。
- old-or-new publication 与 caller capability lifecycle：`begin_batch(...)`、`commit_prepared_upload_batch(...)`、`commit_batch(...)` / `rollback_batch(...)`。
- version / `first_ingested_at`：reset 前由 caller 传入并被 `_PreparedAssetMutation.previous_meta` 持有的 source meta。
- fresh authoritative action/company decision：SEC `run_upload_filing_stream(...)` 与 CN/HK `CnPipeline.upload_filing_stream(...)` 的既有 fresh validator call；S2 只补行为测试，不修改 workflow 生产代码。

## 3. Stop-condition conclusion

**PASS，未触发停止。** 直接代码证据如下：

1. `begin_batch(...)` 在取得 ticker writer authority 后把完整 published ticker tree 复制到单一 staging tree。
2. `reset_source_document(...)` 只在该 open batch 的 staging 中删除 exact `(ticker, document_id, source_kind)` 目录并同步对应 manifest 条目。
3. source reset、全部 blob 写入、final source create 与 company stage 使用同一个 caller-owned `BatchToken`。
4. `commit_batch(...)` 在 publication guard 下以目录 swap 发布整棵 ticker tree；staged mutation、最终 checkpoint 或 precommit cancellation 失败时 caller rollback 丢弃 staging，published old tree 不变。

因此现有 reset 已满足 same-batch exact-target old-or-new；实现没有引入 commit 后补偿删除、跨 batch copy/delete、ticker 级清空或同请求 second lock recheck。

## 4. Tests-first RED

先只修改/迁移 S2 owner 与 workflow tests，并删除测试对 `_resolve_upsert_mode` 的 import/pin；生产代码尚未修改时运行：

```bash
source .venv/bin/activate
pytest tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py -q
```

精确结果：**4 failed, 68 passed, 3 warnings**。

精确 RED：

1. `test_execute_upload_existing_full_input_replaces_exact_complete_set[filing-update-False-old-report.txt-renamed-report.txt]`
   - commit validator 抛出 `ValueError: source files 与 physical business files 不双向一致: filing_replace`。
   - 证明 non-overwrite renamed update 未 reset，旧业务文件残留在 staging。
2. `test_execute_upload_update_failure_keeps_previous_document[False]`
   - 记录到 `update_failed`，预期 `create_failed`。
   - 证明 non-overwrite update 的 final mutation 仍走 update，而不是 reset 后 create。
3. `test_upload_filing_stream_renamed_update_without_overwrite_replaces_complete_set`
   - SEC result `status=failed`，底层同样由 physical/meta 双向不一致触发。
4. `test_upload_filing_stream_auto_resolves_create_update_skip`
   - CN result `status=failed`，底层同样由 physical/meta 双向不一致触发。

四个 RED 由同一 shared owner 根因产生，没有通过 workflow fallback、测试 fixture 特例或下游补偿修复。

## 5. Implementation changes

### 5.1 Production

`dayu/fins/pipelines/docling_upload_service.py`

- `DoclingUploadService._store_upload_assets(...)`
  - existing `update` 不再依赖 overwrite；existing `create` 仅在 admission 已允许 overwrite 时进入替换。
  - 在 caller-owned batch 内先 reset exact source，再按既有顺序写入全部 original + Docling blobs。
  - reset 前的 `previous_meta` 保持在 prepared mutation 中，不在 reset 后重读 missing state。
- `DoclingUploadService._create_source_document(...)`
  - 由原 `_upsert_source_document(...)` 收敛为 create-only final mutation。
  - final meta/manifest 只在全部 blob 写入与 cancellation checkpoint 通过后创建。
- `_resolve_upsert_mode(...)`
  - 完整删除；未保留 re-export、wrapper、compat shim 或 missing-update→create 分支。

没有修改 storage protocol/implementation、SEC/CN/HK workflow 生产代码、material workflow/typed usage、CLI、Service、Host、Engine、runtime、config、registry、oracle、evidence 或 design document。

### 5.2 Owner tests

`tests/fins/test_docling_upload_service.py`

- 同名 changed filing update：新 bytes、meta、version 与 complete integrity 同源。
- 改名且 `overwrite=False` 的 filing update：只剩新 original + 新 Docling 文件。
- existing material create-overwrite：共享 exact reset + complete create owner。
- filing deleted equal/changed input 与 material 最小 deleted-equal parity：均重新转换并发布 active、`deleted_at=None`、integrity complete；equal 保持 version，changed 递增 version，全部保持 `first_ingested_at`。
- reset 后第一个/第二个 blob store failure：整棵 published ticker tree SHA 不变。
- reset 后 blob checkpoint、final checkpoint、precommit cancellation：整棵 published ticker tree SHA 不变。
- final create failure：两种 overwrite 值均进入 create failure，旧 meta/files/tree SHA 不变。
- 删除 `_resolve_upsert_mode` import 与 upsert pin。

### 5.3 Workflow tests

`tests/fins/test_sec_pipeline_upload_filing_stream.py`

- renamed update 不传 overwrite，document ID 与 create 相同，只发布新完整文件集合。
- 同一次成功替换保持非目标 filing meta/files 与 company meta 不变。
- fresh create-existing 丢弃 stale create decision，在 converter 与 batch 前抛 typed `CREATE_TARGET_EXISTS`，published tree SHA 不变。
- delete 后 equal/changed 输入 auto 均返回 uploaded/update，public state active。
- 保留既有 stale auto=create → fresh update 测试。

`tests/fins/test_cn_pipeline.py`

- CN/HK shared facade 的 changed renamed update 发布完整新集合，随后 identical replay skip。
- preflight existing、fresh missing 的 explicit update 在 overwrite false/true 下均于 converter/batch 前抛 typed `UPDATE_TARGET_MISSING`，published tree SHA 不变。
- 保留既有 fresh stale-action discard 与 HK typed-request/fresh-snapshot 测试。

material 增量仅包含 shared owner 的 existing create-overwrite 与 deleted-equal publication parity；未修改 material workflow 生产代码、typed usage/public error projection，也未扩入 focused-real。

## 6. GREEN and validation

### 6.1 Focused S2

```text
pytest tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py -q
74 passed, 3 warnings
```

### 6.2 Full focused owner/boundary set

```text
pytest tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/cli/test_fins_commands.py -q
321 passed, 3 warnings
```

### 6.3 UF-FIX01 / atomicity / cancellation regressions

```text
pytest tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_docling_process_converter.py \
  tests/fins/test_fins_service_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_import_boundary.py -q
343 passed, 3 warnings
```

warnings 均为已安装 `edgar` 包的三条 deprecation warning，不是测试失败或本 slice 新增 warning。

### 6.4 Per-production-file coverage

使用 `mktemp -d` 下的独立 coverage data file，未在仓库写入 coverage 产物：

```text
dayu/fins/ingestion_runtime.py                   2134    193    91%
dayu/fins/pipelines/docling_upload_service.py     389     50    87%
TOTAL                                            2523    243    90%
```

S2 唯一修改生产文件 `docling_upload_service.py` 为 **87%**，满足逐文件 `>=80%`；同时按 accepted plan 复核 S1 相关 `ingestion_runtime.py` 为 **91%**。

### 6.5 Full pyright

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

## 7. README decision

- `dayu/fins/README.md`：已按开发文档边界更新 shared action/publication owner、exact reset、reset 前 meta 真源、complete-set replacement 与 rollback contract。
- `tests/README.md`：已记录当前已实现的 S2 owner/workflow coverage，不写未来测试计划。
- `README.md`：已按 Controller S1 rereview adjudication 一次性写明：
  - update 只作用于 existing target；
  - overwrite 不是 upsert；
  - auto 恢复 logical deleted source；
  - existing update 原子替换完整文件集合，改名不残留旧文件。
- `dayu/README.md`：未更新；分层、装配和 Fins 在整体架构中的位置未变化。

## 8. Diff/static/no-touch audit

- `git diff --check`：通过。
- `_resolve_upsert_mode`：`rg -n '_resolve_upsert_mode' --glob '*.py' .` 零命中。
- frozen registry SHA-256 保持 accepted plan 基线：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`
- `git diff --exit-code` 对两个 frozen registry、`docs/host/design.md`、`docs/engine/design.md`：通过。
- production diff 未新增 `hasattr/getattr`、`Any/object`、lazy import、compat wrapper/re-export、字符串异常分类、`str(exc)` public projection、默认 deleted state、下游 fallback、补偿删除、跨 batch replacement 或 ticker 级清空。
- production 中唯一 `.stem` 命中是既有 Docling 输出文件名派生，不参与 filing identity，且本 slice 未修改该行。
- 未触及 UF-FIX03–08/10/11、UF-PF03–12、registry/oracle/evidence/design；未做 same-request second lock recheck。

实现 gate changed paths：

- `README.md`
- `dayu/fins/README.md`
- `dayu/fins/pipelines/docling_upload_service.py`
- `tests/README.md`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- 本 artifact

## 9. Residual risks and uncovered areas

| Residual / uncovered area | Classification / owner |
| --- | --- |
| prevalidation/fresh recheck 后到 publication 前的同请求竞争 | assigned to later work unit `UF-FIX10`；本 slice 不做 second lock recheck |
| existing source corruption 与 auto repair | assigned to `UF-FIX08` |
| multi-file basename/stem collision 与 primary 选择 | assigned to `UF-FIX07` |
| format/XBRL companion capability | assigned to `UF-FIX06` |
| summary/stored counts 与 broader bounded errors | assigned to `UF-FIX03` |
| fresh company name/alias ignored warning | assigned to `UF-FIX11` |
| full upload_filing conformance | assigned to existing `UF-PF12` |
| `UF-A08` frozen observed evidence 与修复后行为不一致 | assigned to later unified conformance refresh；本 slice intentionally no-touch |
| material broader typed projection / full-real coverage | assigned to `UF-PF12` 或后续明确 work unit；本 slice 只有 shared owner parity |
| UF-PF02 focused-real | covered by later approved Gateflow entry；用户明确要求 S2 implementation 后停止，本 gate 未执行 |

没有未分类 residual risk，没有 blocking open question。

## 10. Completion status

- S2 implementation：**PASS**
- Stop condition：**PASS，same-batch exact-target old-or-new 已由既有 storage owner 支持**
- Tests-first：**RED 4 / GREEN all**
- Review：**未进入**
- Commit / push / PR：**均未执行**
- Current HEAD：`08316516ca3da7f98299ee90d3fa753c32c59020`
- Next possible Gateflow entry：`code review`；按用户要求本次在 S2 implementation artifact 完成后停止。

## 11. Code-review fix addendum（2026-08-13）

Controller 在
`docs/gateflow/uf-fix02-action-and-update-identity-s2-code-review-adjudication-20260813.md`
裁决两个 accepted findings 后，本地执行了一次 bounded code-review fix；本 addendum 只补记该 fix，不改写前述 implementation
gate 的历史结果。独立 fix artifact：
`docs/gateflow/uf-fix02-action-and-update-identity-s2-code-review-fix-20260813.md`。

### 11.1 Owner judgment and changes

- `created_at` 与 `first_ingested_at` 同属 durable source 首次创建事实；reset 后 storage 已失去旧 meta，不能作为保持该事实的
  owner。唯一正确修复边界是 reset 前已持有 `previous_meta` 的
  `DoclingUploadService._build_upsert_meta(...)`。
- 先在 renamed update、deleted restore、material shared-owner parity 的 owner tests 增加 `created_at` 保持断言，并用两个确定
  时钟阶段避免秒级时钟造成假绿。最终测试版本在未改生产 owner 时精确得到 **6 failed**，六项都只显示
  `2020-01-01T00:00:00+00:00` 漂移为 `2020-01-02T00:00:00+00:00`。
- 生产修复只让 `_build_upsert_meta(...)` 从 `previous_meta["created_at"]` 派生稳定值；旧值不存在时才使用本次
  `now`。没有增加 storage/downstream fallback，没有修改 batch、admission 或 workflow。
- 删除 `_FailingFinalUploadSourceRepository.update_source_document(...)` dead override；保留 final create failure 注入和
  `events[-1] == "create_failed"` 断言。

### 11.2 GREEN and validation

- 精确 owner/failure GREEN：`8 passed`。
- S2 focused：`74 passed, 3 warnings`。
- 完整 owner/boundary focused：`321 passed, 3 warnings`。
- UF-FIX01 / atomicity / cancellation regressions：`343 passed, 3 warnings`。
- 修改生产文件 coverage：`dayu/fins/pipelines/docling_upload_service.py` **87%**（391 statements，50 missed）。
- 完整 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`、frozen no-touch、design no-touch 均通过；两个 frozen registry SHA-256 仍为计划基线。
- `rg -n '_resolve_upsert_mode' --glob '*.py' .` exit `1` 且无输出，即 Python 源码零命中。
- production added-lines static audit 未发现 `hasattr/getattr`、`Any/object`、`str(exc)`、lazy/compat 或 basename/stem
  identity；未增加 fallback、补偿删除、跨 batch replacement 或 ticker 级清空。

三条 warning 仍全部来自已安装 `edgar` 包的既有 deprecation warning。README 当前语义已经覆盖 reset 前 meta 的首次创建
事实真源，本 fix 没有改变用户可见行为边界或测试能力边界，因此未修改 README。

### 11.3 Status

- 两个 accepted findings 的 fix 实现状态：**已修复，等待独立 re-review**。
- 原 §9 residual risks 及 owner/destination 不变，没有新增未分类 residual risk。
- 未修改既有 review/adjudication artifacts；未 commit、push、创建 PR、进入 re-review 或执行 UF-PF02。
- 本次按 Controller 指令在 code-review fix gate 完成后停止。
