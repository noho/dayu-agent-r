# UF-FIX07 Slice 3 Review Fix Artifact

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`code review fix`
- Slice：`Slice 3 — Deterministic asset identity、storage primary 与 process consumption`
- 日期：2026-08-15
- 基线：`3911c790f0147876148f1ee4d038eb14fe7becd7`
- Review inputs：
  - `docs/reviews/code-review-20260815-204338.md`
  - `docs/reviews/code-review-20260815-205240.md`
- Decision：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Blocking open question：无
- 下一入口：`re-review`
- Artifact path：`docs/gateflow/uf-fix07-slice3-review-fix-20260815.md`

## Scope 与边界

本轮只处理用户已接受的两项 LOW finding 与 portability residual：

- production：`dayu/fins/pipelines/docling_upload_service.py`
- test：`tests/fins/test_docling_upload_service.py`，以及 Slice 3 已允许测试内的 expected identity path normalization
- gateflow artifacts：本 artifact 与 Slice 3 implementation artifact

未修改两份 review artifacts、README、registry、oracle、scenario、frozen evidence、storage/processor 生产代码；未执行真实 CLI evidence；未 commit 或创建 PR。

## Finding adjudication 与 fix status

| Finding | 裁决 | 修复 | 直接证据 |
| --- | --- | --- | --- |
| LOW 1：两个生产 helper 的 `Raises` 与真实异常路径不符 | accepted | 已修复 | `_build_upload_source_fingerprint()` 明确声明 filing 缺失 `original_filename` 与 unsupported source kind 的 `ValueError`；`_build_stored_file_entry()` 明确声明 filing 缺失 `original_filename` 的 `ValueError` |
| LOW 2：fresh target blob store failure 缺少直接零发布断言 | accepted | 已修复 | `test_filing_fresh_blob_store_failure_rolls_back_once_with_zero_publication` 覆盖第 1/2/3 次 store 失败，断言 begin/commit/rollback 为 1/0/1、published tree 为空、source meta 不存在 |
| Residual：新增测试隐式依赖 pytest `tmp_path` 已 realpath | accepted | 已修复 | 新增 direct-service test paths 在 typed filing selection/expected identity 前显式 `resolve(strict=False)`；pipeline/runtime expected identity 同样显式 resolve；生产 helper 校验保持不变 |

没有 rejected、partially fixed 或 needs-more-evidence finding。

## Validation

Affected Slice 3 suites：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py -q
```

- Exit code：0
- Result：`630 passed, 1 skipped, 3 warnings`
- Skip：未启用 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION` 的 optional real Docling integration。
- Warnings：3 条第三方 `edgar` deprecation warning，与本 fix 无关。

Targeted pyright：

```bash
source .venv/bin/activate
python -m pyright dayu/fins/pipelines/docling_upload_service.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py
```

- Exit code：0
- Result：`0 errors, 0 warnings, 0 informations`

Production coverage：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  --cov=dayu.fins.pipelines.docling_upload_service --cov-report=term -q
```

- Exit code：0
- Result：`72 passed, 1 skipped`
- `dayu/fins/pipelines/docling_upload_service.py`：`477 statements / 67 missed / 86%`

Diff/scope check：

```bash
git diff --check
git diff -- docs/reviews
git status --short
git rev-parse HEAD
```

- `git diff --check`：exit 0。
- 两份 AgentDS review artifacts 无 tracked diff。
- HEAD 仍为 `3911c790f0147876148f1ee4d038eb14fe7becd7`。
- changed production/test/gateflow files 均在用户允许范围；review artifacts 保持未修改。

## Docs decision

- README 仍由 accepted Slice 4 负责，本 review fix 不更新 README。
- 两份 AgentDS review artifact 保持只读未修改。

## Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | owner / destination |
| --- | --- | --- |
| 两项 accepted LOW findings | fixed in current slice | 本 artifact 记录实现与验证 |
| 新增测试对 pytest realpath 行为的隐式依赖 | fixed in current slice | 显式 `resolve(strict=False)`，生产 contract 不放宽 |
| 旧 basename-based source schema 的兼容、首次重传或自动修复 | assigned to later work unit | `UF-FIX08` |
| 同 request/document 并发 writer | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| material basename/stem collision 与 duplicate-path 行为 | assigned to later work unit | material regression 保持现状 |
| optional real Docling、UF-PF07/UF-PF12 与 frozen evidence | assigned to later evidence work | 等待另行授权 |

所有 residual risks 已分类；无 unclassified residual risk 或 blocking open question。

## Completion status

- Status：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Gate Order 下一个未完成 entry point：`re-review`
- 按用户要求在此停止，不执行 commit、PR 或后续 gate。
