# UF-FIX03 S1 review-fix artifact

## Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Slice：`UF-FIX03-S1 — Publication-owned requested/stored count contract`
- Gate：`code review -> fix`
- Branch：`codex/upload-filing-oracle`
- Baseline：`662c9ad4b234894e54c62b56368c7682a09f596e`
- 输入裁决：`docs/gateflow/uf-fix03-s1-code-review-adjudication-20260813.md`
- Review 输入：`docs/reviews/code-review-20260813-214459.md`
- Decision：**PASS — 两个 accepted findings 已修复，等待 S1 re-review**
- Next entry point：`S1 re-review`
- Commit：未创建；controller 的 review-fix gate 要求先完成双路 re-review，再进入 accepted slice commit。
- Artifact path：`docs/gateflow/uf-fix03-s1-review-fix-20260813.md`

## Scope and owner decisions

- cancellation 语义 owner 保持在 `DoclingUploadService.prepare_upload(...)`：converter 的
  `DoclingConversionCancelledError` 在该边界被投影为 typed cancelled `UploadOperationResult`；SEC/CN workflow 不再维护不可达的
  第二套 catch 与 inline result constructor。
- service early-cancelled summary 由 `ProductionFinsUploadRunner.run_upload(...)` 直接拥有，行为测试证明
  `requested_file_count=len(request.files)` 且 `stored_file_count=0`。
- direct runner-unavailable summary 由 `FinsIngestionRuntime._produce_direct_upload(...)` 直接拥有，integration 行为测试证明
  RESULT details 的 requested 等于请求文件数、stored 为 `0`，并保持 runtime-unavailable 文案。
- `FinsUploadResultSummary.__post_init__()` 继续唯一拥有 summary 状态矩阵；参数化 owner 测试新增
  `skipped + requested_file_count=0 + stored_file_count=0` 拒绝场景。
- production `UploadOperationResult(...)` inventory 从六点收紧为四点，四点全部位于
  `dayu/fins/pipelines/docling_upload_service.py`，均显式传入 `stored_file_count`。
- 未新增 fallback、兼容分支、重复 cancellation mapper 或下游 count 重算。

## Changed files in this fix gate

### Production

- `dayu/fins/pipelines/sec_upload_workflow.py`
  - 删除不可达的 workflow-level `DoclingConversionCancelledError` catch、对应 exception import 与 inline
    `UploadOperationResult(...)` 构造。
- `dayu/fins/pipelines/cn_pipeline.py`
  - 删除同形不可达 catch、对应 exception import 与 inline constructor。

### Tests

- `tests/fins/test_fins_service_runtime.py`
  - 新增 production runner early-cancelled count 行为测试。
- `tests/fins/test_fins_ingestion_runtime.py`
  - 新增 direct runner-unavailable count/文案 integration 测试；补 summary skipped-zero-request 拒绝；AST inventory 改为四点。

### Artifacts

- `docs/gateflow/uf-fix03-s1-implementation-20260813.md`
  - 纠正 S1 修改路径 coverage 与 implementation gate 未 commit 原因的失真表述，并同步 review-fix 后验证数据。
- `docs/gateflow/uf-fix03-s1-review-fix-20260813.md`
  - 记录本 fix gate 的 scope、finding 状态、验证、docs decision 与 residual risks。

## Finding status

### F1：S1 修改分支缺少 owner 行为覆盖

- 裁决：`accepted`
- Fix 状态：**已修复**
- 直接证据：三个缺失场景均新增 owner/integration 行为断言；coverage missing 集不再包含原 service early-cancelled、direct
  runner-unavailable 与 skipped-zero-request 分支。implementation artifact 已明确纠正 review 前的错误 coverage 声明。

### F2：workflow 级 conversion-cancelled catch 不可达

- 裁决：`accepted`
- Fix 状态：**已修复**
- 直接证据：SEC/CN workflow 均已删除 catch 与 exception import；production `UploadOperationResult(...)` 静态 inventory 只剩
  `docling_upload_service.py` 四点，focused AST audit 通过。

## Validation

### Targeted behavior and AST audit

```text
11 passed, 3 warnings in 1.13s
```

覆盖新增的三个行为场景与 production constructor inventory；warnings 均来自 `edgar` 依赖弃用提示。

### Focused pytest

```text
286 passed, 3 warnings in 4.83s
```

命令覆盖六个 accepted S1 focused test files；未运行 S2/S3 tests 或 UF-PF03。

### Pyright

`python -m pyright dayu/ tests/ utils/` 完成且无类型诊断；仅额外提示可升级 pyright 版本，不是项目错误。

### Coverage

| Production file | Statements | Miss | Coverage |
| --- | ---: | ---: | ---: |
| `dayu/fins/ingestion_runtime.py` | 2167 | 198 | 91% |
| `dayu/fins/pipelines/cn_pipeline.py` | 413 | 130 | 69% |
| `dayu/fins/pipelines/docling_upload_service.py` | 398 | 51 | 87% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 145 | 7 | 95% |
| `dayu/fins/service_runtime.py` | 124 | 14 | 89% |
| **Total** | **3247** | **400** | **88%** |

`cn_pipeline.py` 的 remaining missing 为既有、未修改的 conversion-error/download/facade/helper 路径；本次裁决指出的不可达
conversion-cancelled catch 已删除，保留的 S1 owner 路径已有行为或 integration coverage。

### Static/no-touch audits

- `git diff --check`：通过。
- `rg -n '\buploaded_files\b' dayu tests --glob '*.py'`：零命中。
- `rg -n 'UploadOperationResult\(' dayu/fins --glob '*.py'`：恰四个 production constructor，全部位于
  `docling_upload_service.py`。
- SEC/CN workflow 中 `DoclingConversionCancelledError`：零命中。
- progress `_PAYLOAD_FILE_COUNT == "file_count"` 与对应回归仍存在；未迁移或双写 progress count。
- frozen SHA-256：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`
- Host、Engine、runtime、config、storage、Service production、CLI、README、冻结 JSON/evidence 均未修改。

## Documentation decision

- 已修正 S1 implementation artifact，因为它是本 finding 的直接错误陈述 owner。
- 不修改 README：本轮没有新增 accepted S1 用户可见 contract，只删除不可达重复分支并补 owner 测试；accepted plan 已把最终
  README 同步明确分配给 S3，本 gate 保持 no-touch boundary。

## Residual risks and uncovered areas

- `cn_pipeline.py` 整文件 coverage 69%，remaining missing 位于既有、未修改的 conversion-error/download/facade/helper 路径；分类为
  **assigned to later work unit**，owner 为 CN pipeline 后续测试覆盖工作，不阻塞当前 S1 review-fix。
- 真实 Docling 多平台差异；分类为 **assigned to later work unit**（UF-PF03 evidence work）。本轮按约束未运行或登记 UF-PF03。
- empty/corrupt/label 与 CLI/direct no-artifact/README；分类为 **covered by later approved slice**（S2/S3），本轮未实现或验证。
- material generic raw failure/company-first publication；分类为 **assigned to later work unit**，本轮仅保留 S1 shared count 机械迁移。
- 无 unclassified residual risk；无 blocking open question。

## Completion status

S1 review-fix gate 完成，两个 accepted findings 均为“已修复”。尚未执行 AgentMiMo/AgentDS re-review，因此没有进入 accepted slice
commit；严格停在 `S1 re-review`，未进入 S2/S3、UF-PF03、push 或 PR。
