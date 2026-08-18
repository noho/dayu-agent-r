# UF-FIX03-S1 implementation artifact

## Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Slice：`UF-FIX03-S1 — Publication-owned requested/stored count contract`
- Gate：`implementation`
- Baseline：`662c9ad4b234894e54c62b56368c7682a09f596e`
- Branch：`codex/upload-filing-oracle`
- Decision：**PASS — S1 IMPLEMENTATION COMPLETE**
- Next entry point：`code review`
- Commit：未创建；implementation gate 尚未通过 code review/re-review，未到 accepted slice commit entry。

## Scope and owner decisions

- `requested_file_count` 的真源是 validated `FinsUploadRequest.files`，runtime 汇合点只取 `len(request.files)`。
- `stored_file_count` 的真源是 `DoclingUploadService` 在每次成功 `store_file(...)` 返回后对 provenance 为 `original` 的资产逐次计数；
  derived Docling 资产不计数。
- `_PendingFileAsset.source` 收敛为私有 `Literal["original", "docling"]`，运行期 provenance 字符串与 fingerprint canonical payload
  保持不变。
- `commit_prepared_upload_batch(...)` 仍是 publication lifecycle owner；workflow 只消费其成功返回。`commit_batch(...)` 抛错时进入
  failed terminal builder，显式投影 `stored_file_count=0`，不消费 staged count。
- `FinsUploadPipelineResult.__post_init__()` 拥有 `ok/skipped/deleted/failed/cancelled` 的完整 stored count 矩阵；JSON parser 只读取
  required exact integer 后调用 constructor。
- `FinsUploadResultSummary.__post_init__()` 拥有 requested/stored 完整矩阵；durable JSON 与 direct RESULT details 都消费同一 summary。
- 删除全部 Python `uploaded_files` 字段、payload、constructor 参数和投影；未增加 default、alias、reader、writer、fallback 或兼容分支。
- progress 的 `_PAYLOAD_FILE_COUNT == "file_count"` 保持不变，started/preparing/completed 仍表达 requested progress unit。
- SEC/CN material 仅机械迁移 required stored count；既有 generic failure 文案与 company-first publication 行为未改。
- 未实现 S2 empty/corrupt/label，未实现 S3 CLI/docs/direct no-artifact，未运行 UF-PF03。

## Changed files

### Production

- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`

### Tests

- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`

### Artifact

- `docs/gateflow/uf-fix03-s1-implementation-20260813.md`

## Tests-first evidence

首次只运行新增 owner/count 测试，结果为预期红灯：`10 failed, 3 warnings`。直接失败证据分别是
`FinsUploadPipelineResult` 不接受 `stored_file_count`、`UploadOperationResult` 不存在该属性，以及 runtime 汇合点不能接收 pipeline
stored count。生产实现完成后，同一 targeted 集合结果为 `22 passed, 3 warnings`。

最终 S1 focused command：

```bash
source .venv/bin/activate
pytest -q \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py
```

review-fix 后最终精确结果：`286 passed, 3 warnings in 4.83s`。三个 warning 均来自 `edgar` 依赖的 deprecated import，
不是本 slice 新增失败。

## Behavioral validation

- 两个 original 输入实际发布四个资产（两个 original + 两个 Docling derived），`stored_file_count == 2`。
- upload success/delete/skip/cancelled 分别断言 stored 为 original 数/`0`；pipeline constructor 与 parser 均覆盖完整五状态矩阵。
- summary 拒绝 bool、负数、`stored > requested`、`ok stored != requested` 与 non-ok positive stored。
- durable summary 与 direct RESULT details 使用 exact `requested_file_count` / `stored_file_count`；不投影 basename 列表。
- production AST constructor audit确认：四个 `FinsUploadResultSummary(...)`、四个 `UploadOperationResult(...)` 与 pipeline 唯一 `cls(...)`
  均显式传 required count，没有 default。
- SEC filing `commit_batch` 分别注入 `OSError`、`RuntimeError`：均得到 `failed/stored=0`，既有分类分别保持
  `storage/storage_io` 与 `runtime/unexpected_runtime`，published tree SHA 保持空值，commit ownership transfer 后不发生 caller rollback。
- material success/failure 仅增加 count 断言；既有 raw generic failure message 与 company-first 行为回归通过。
- fingerprint fixture digest 保持
  `099dc9636e306c75f1d5d64dd0210123956ba73888e968088c7279baab1d7fdd`；provenance bytes/schema 未改。
- progress 两个 count 新字段均未出现，既有 `file_count` 在 request 与 terminal progress 中保持为 requested 单位。

## Coverage

Coverage command：

```bash
source .venv/bin/activate
coverage erase
coverage run -m pytest -q \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py
coverage report -m \
  --include='dayu/fins/pipelines/docling_upload_service.py,dayu/fins/pipelines/sec_upload_workflow.py,dayu/fins/pipelines/cn_pipeline.py,dayu/fins/ingestion_runtime.py,dayu/fins/service_runtime.py'
```

精确结果：

| Production file | Statements | Miss | Coverage |
| --- | ---: | ---: | ---: |
| `dayu/fins/ingestion_runtime.py` | 2167 | 198 | 91% |
| `dayu/fins/pipelines/cn_pipeline.py` | 413 | 130 | 69% |
| `dayu/fins/pipelines/docling_upload_service.py` | 398 | 51 | 87% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 145 | 7 | 95% |
| `dayu/fins/service_runtime.py` | 124 | 14 | 89% |
| **Total** | **3247** | **400** | **88%** |

review 时发现原 implementation coverage 表述不准确：当时 service early-cancelled、direct runner-unavailable、
`skipped + requested_file_count=0` 拒绝以及两个 workflow conversion-cancelled catch 均未被执行，不能声称全部 S1 修改路径已有
owner/integration coverage。review-fix 已新增前三个 owner/integration 行为测试，并删除当前生产拓扑不可达的两个 workflow catch；
这些保留的 S1 owner 分支现已进入 coverage。`cn_pipeline.py` 仍未达到单文件 80% 目标，其 missing 主要集中在既有、未修改的
conversion-error、download/facade/helper 分支 `907-909, 1309-1336, 1381-1398, 1428-1493, 1514-1527, 1553-1739`；
未为提升整文件数字而越界增加非 S1 测试。

## Type and static validation

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过，无 whitespace error。
- `rg -n '\buploaded_files\b' dayu tests --glob '*.py'`：零命中。
- `_PAYLOAD_FILE_COUNT` 与 progress `file_count`：仍存在，并由 focused regression 覆盖。
- frozen SHA：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`
- no-touch：Host、Engine、runtime、config、storage、Service production、CLI、README、冻结 JSON/evidence 均未修改。

## Documentation decision

用户把本 slice 写入范围冻结为 S1 production/test 文件与本 implementation artifact，因此本 gate 不修改 README。根 README、
`dayu/fins/README.md` 与 `tests/README.md` 的用户可见文档更新属于 accepted plan 的 S3，本轮明确不实施。

## Findings and residual risks

- accepted finding：request basename 被误当 publication fact；**已修复**，count 从唯一 owner 链贯通。
- accepted finding：derived asset 可能被总资产数误计；**已修复**，只在 successful original store 后累计。
- accepted finding：commit failure 可能暴露 staged count；**已修复**，terminal builder 固定 stored `0`，有 OSError/RuntimeError 回归。
- residual risk：`cn_pipeline.py` 整文件 coverage 为 69%；分类为 **assigned to later work unit**，owner 为 CN pipeline 的既有
  conversion-error/download/facade/helper 测试覆盖。review-fix 已补齐或删除本轮裁决指出的 S1 uncovered 路径；该表述不追溯掩盖
  implementation review 前确实存在的 coverage 缺口。
- residual risk：真实 Docling 平台差异、empty/corrupt/label、CLI bounded stderr 与 direct no-artifact；分类为
  **covered by later approved slice**（S2/S3）或 UF-PF03，本轮未运行、未伪报。

## Completion status

S1 implementation gate 完成后进入 code review；当时未创建 commit 的原因是 Gateflow 要求先完成 review/fix/re-review，再进入
accepted slice commit，而不是用户禁止 implementation gate commit。review-fix 仍未进入 accepted slice commit、S2、S3、UF-PF03、
push 或 PR。
