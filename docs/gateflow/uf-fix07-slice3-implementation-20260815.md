# UF-FIX07 Slice 3 Implementation Artifact

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`implementation`
- Slice：`Slice 3 — Deterministic asset identity、storage primary 与 process consumption`
- 日期：2026-08-15
- 基线：`3911c790f0147876148f1ee4d038eb14fe7becd7`
- Decision：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Blocking open question：无
- 下一入口：`re-review`
- Artifact path：`docs/gateflow/uf-fix07-slice3-implementation-20260815.md`

## Scope 与 changed files

实际修改严格位于 Slice 3 allowed files：

- production：`dayu/fins/pipelines/docling_upload_service.py`
- tests：
  - `tests/fins/test_docling_upload_service.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/fins/test_sec_pipeline_upload_filing_stream.py`
  - `tests/fins/test_cn_pipeline.py`
  - `tests/fins/test_processor_read_consistency.py`
- artifact：`docs/gateflow/uf-fix07-slice3-implementation-20260815.md`

未修改 storage、processor、Host、Engine、runtime、README、registry、oracle 或 frozen evidence 生产文件；allowed tests 中无需行为迁移的文件保持未修改。

## Owner、contract 与 data flow 决策

1. 语义 owner 保持在 `DoclingUploadService` 的 typed filing asset preparation/publication projection：
   - filing original identity 使用 `fins-upload-asset-v1 + NUL + normalized_path.as_posix()` 的完整 SHA-256，形状为
     `original-<64-hex><lower-suffix>`；不含绝对路径明文、请求 index、时间或随机值。
   - 同次 request 对 generated original identities 做唯一性 fail-closed 检查，发生 collision 时在 converter/batch 前失败。
2. `_PendingFileAsset` 显式携带 `original_filename` 与 `derived_from`：
   - filing original：path identity、basename、`derived_from=None`；
   - filing derived：`<exact-original-identity>_docling.json`、继承 basename、exact `derived_from`；
   - material 两字段均显式为 `None`。
3. filing converter 只绑定 authoritative primary 对应的 exact original asset，一次转换、一个 derived；companions 仅保留 originals。
4. filing blob key、`files[].name`、URI 与 `primary_document` 使用 storage identity；original/derived 都投影 `original_filename`，仅 derived 投影 `derived_from`；用户事件继续只显示 basename。
5. filing source fingerprint 使用 `original_filename/sha256/size/source`，排除 path-derived identity 与请求顺序；material 继续使用原 `name/sha256/size/source` 公式。
6. storage/snapshot/process/read 生产代码保持不变：测试证明 snapshot、preprocess registry 与 read registry 都只消费 exact published primary derived bytes，不扫描 original 或 companion。
7. 所有 allowed tests 内遗留的 filing `from_upsert_paths()` 已迁移到 explicit `for_upsert(primary=..., companions=...)`；未增加 shim 或首项推断 helper。

## Tests 与关键 assertions

Affected suites：

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
- Skip：`DAYU_RUN_DOCLING_UPLOAD_INTEGRATION` 未启用的 optional real Docling integration，符合 Slice 3 env gate。
- Warnings：3 条第三方 `edgar` deprecation warning，不属于本 slice regression。

Owner coverage：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  --cov=dayu.fins.pipelines.docling_upload_service --cov-report=term -q
```

- Exit code：0
- Result：`72 passed, 1 skipped`
- `dayu/fins/pipelines/docling_upload_service.py`：`477 statements / 67 missed / 86%`

覆盖的 Slice 3 correctness facts：

- 不同目录同 basename、同 stem 异后缀、explicit primary 位于非首项；
- identity 稳定、请求顺序无关、完整 64 hex digest、不泄漏绝对路径明文；
- original/derived exact 三字段、URI、metadata、用户事件与 primary association；
- 移目录同 basename/content identical-skip，改 basename update/version increment，改内容继续 increment；
- N originals + 1 derived、stored count 只计 originals、100 inputs 只转换一次；
- conversion failure 在 batch 前零发布，generated identity collision 在 converter/batch 前 fail closed；
- blob/final source/commit failure 的 rollback/ownership 与 fresh/existing tree 原子性；
- snapshot、preprocess 与 read runtime 精确消费 derived primary；
- material name、derived、metadata、fingerprint、event、failure 与逐项 converter 行为回归不变。

## Type check

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

## Docs decision

- 本 slice 不更新 README：用户明确要求只执行 Slice 3 且不要 README；accepted plan 将 README 同步归属 Slice 4。
- 只创建本 implementation artifact；未修改 plan、goal、registry、oracle 或 evidence。

## Accepted review fix update

- AgentDS LOW 1：已修复。`_build_upload_source_fingerprint()` 与
  `_build_stored_file_entry()` 的中文 docstring 现在明确声明 filing 缺失
  `original_filename` 时抛出 `ValueError`；前者同时声明 unsupported source kind 的既有 `ValueError`。
- AgentDS LOW 2：已修复。新增 fresh filing 第 1/2/3 次 blob store failure 直接测试，精确断言
  `begin=1`、`commit=0`、`rollback=1`、published tree 为空且 source meta 不存在。
- Portability residual：已修复。新增 direct-service tests 在构造 typed filing selection 或计算 expected identity 前显式执行
  `resolve(strict=False)`；pipeline/runtime tests 计算 expected identity 时也显式 resolve。生产 normalized-path fail-closed contract 未放宽。
- Fix artifact：`docs/gateflow/uf-fix07-slice3-review-fix-20260815.md`。

## Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | owner / destination |
| --- | --- | --- |
| 旧 basename-based source schema 的兼容、首次重传或自动修复 | assigned to later work unit | `UF-FIX08`；本 slice 按 fresh schema，不增加兼容读取 |
| 同 request/document 并发 writer | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| frozen registry/oracle/evidence 与真实 UF-PF07/UF-PF12 | assigned to later evidence work | 当前未修改、未执行，等待另行授权 |
| material basename/stem collision 与 duplicate-path 行为 | assigned to later work unit | material regression 明确保持现状 |
| optional real Docling integration 未启用 | assigned to later evidence work | deterministic fake-converter owner tests已通过；真实 evidence 需另行授权 |
| SHA-256 理论 collision | fixed in current slice | 完整 digest + request-local uniqueness fail-closed |
| 新增测试依赖 pytest `tmp_path` 已 realpath | fixed in current slice | 测试拥有路径在 typed request/expected identity 前显式 resolve |

所有 residual risks 已分类；无 unclassified residual risk、blocking finding 或 uncovered current-slice acceptance criterion。

## 禁止动作确认与 completion status

- 未执行 UF-PF07、UF-PF12 或真实 CLI evidence。
- 未修改 README、registry、oracle、scenario 或 frozen evidence。
- 未 commit、push、创建 PR 或推进 PR。
- 当前 completion status：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`。
- Gate Order 下一个未完成 entry point：`re-review`；按用户要求在 review fix 完成后停止。
