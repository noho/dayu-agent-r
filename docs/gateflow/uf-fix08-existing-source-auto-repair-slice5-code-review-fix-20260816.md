# UF-FIX08 existing-source-auto-repair：Slice 5 code-review fix

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`code review fix`
- slice：`Slice 5：SEC/CN/HK workflow 与 downstream`
- 日期：2026-08-16
- baseline / current HEAD：`4812878b5a3a4884b8b8522e7113d196c4e479d9`
- review artifacts：`docs/reviews/code-review-20260816-174830.md`、`docs/reviews/code-review-20260816-175716.md`
- implementation artifact：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice5-implementation-20260816.md`
- completion status：`CODE REVIEW FIXED / awaiting re-review`
- blocking questions：无
- 下一入口：Slice 5 re-review

## Findings 裁决

### Accepted blockers

| Finding | 状态 | 直接证据与修复 |
| --- | --- | --- |
| A：fresh state owner 漏捕 `RuntimeFileLockError` | `已修复` | `RuntimeFileLockError` 直接继承 `Exception`，不属于原有 `OSError/ValueError` catches，确会穿透 async stream并进入 durable generic `str(exc)`。唯一 shared resolver现精确捕获 `(OSError, RuntimeFileLockError)`，复用 `fins_upload_prevalidation_io_failure()`，没有调用异常字符串或重新判断 integrity |
| B：SEC/CN `_resolve_fresh_filing_request` 双 owner | `已修复` | 新增 `dayu/fins/pipelines/_filing_upload_fresh_validation.py`；朴素 required keyword接口只接收 `FilingUploadStateRepositoryProtocol` 与 `ValidatedFinsUploadFilingRequest`，在同一 `try` 完成 read+validator并返回 validated request或typed failure。SEC/CN删除本地 helper与相关 imports，只机械消费同一个 resolver；两者不互相 import |

### Rejected findings

| Finding | 裁决与理由 |
| --- | --- |
| fresh usage 应扩大 durable typed schema | `rejected-with-reason`。`FinsUploadUsageError` 已由 validator usage contract拥有，必须在 structural `ValueError` 前原样抛出。durable generic exception 是既有通用 runtime boundary，当前 closed `FinsUploadFailureCode` 没有等价 usage code；本 work unit 不扩 schema、不把 usage伪装为 storage/runtime failure，也不增加兼容 projection |
| CN/HK 应复制 SEC corruption grid | `rejected-with-reason`。accepted plan §11.4只要求 CN 一个 repair success + Phase B conflict + unsafe + atomicity，以及 HK一个 repair success + unsafe/stale；当前测试精确满足。完整 corruption grid已由 shared service/storage owner与 SEC market层覆盖 |
| SEC/CN test JSON helper必须抽共享 support | `rejected-with-reason`。两个 helper仅服务各自 market filesystem fixture注入，不承诺生产语义；抽取会增加未授权跨 scope test-support owner，不改善本 blocker的 correctness |
| internal `RuntimeError` 应一并收敛 | `rejected-with-reason`。storage/validator producer invariant 与 workflow identity invariant不是可公开 I/O事实；shared resolver不捕获其它 `RuntimeError`，identity guard仍位于 resolver外，二者继续 fail-loud，避免掩盖 producer bug |

## 实现与测试变更

- shared owner精确映射：
  - `FinsUploadPrevalidationError -> exc.failure`；
  - `FinsUploadUsageError -> re-raise`；
  - `(OSError, RuntimeFileLockError) -> fins_upload_prevalidation_io_failure()`；
  - structural `ValueError -> fins_upload_prevalidation_corruption_failure()`；
  - 其它异常不捕获。
- SEC/CN workflow仅调用 `resolve_fresh_filing_request(repository=..., request=...)`，收到 `FinsUploadFailureReason` 时机械产生各自唯一 failed
  event，否则执行既有三字段 identity guard并传 fresh disposition。
- SEC参数化 fresh-read测试新增真实 `RuntimeFileLockError("private lock detail")`，断言事件序列只有 `UPLOAD_FAILED`，failure
  `kind=storage/code=storage_io`、固定 path-free message、无异常文本，且 converter/batch/company/source mutation全部为零。
- SEC/CN validator monkeypatch测试迁移到 shared owner模块，未保留 workflow module compatibility re-export；CN/HK既有 unsafe测试继续证明
  两市场通过同一个 resolver消费 typed prevalidation failure。

## Changed files

Production：

- `dayu/fins/pipelines/_filing_upload_fresh_validation.py`（Controller scope amendment）
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`

Tests：

- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`

Slice 5其余两份 allowed tests保持 implementation diff但本 fix无需追加改动：

- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_fins_ingestion_runtime.py`

Artifacts：

- 更新 `docs/gateflow/uf-fix08-existing-source-auto-repair-slice5-implementation-20260816.md`
- 新增 `docs/gateflow/uf-fix08-existing-source-auto-repair-slice5-code-review-fix-20260816.md`

两份 review artifacts由 reviewers产生并保持不改。未修改 download、README、evidence、oracle、scenario、UF-FIX10/11或Slice 1–4 owner。

## Validation

```text
direct four files:
430 passed, 3 warnings in 6.74s

accepted focused matrix:
1221 passed, 3 warnings in 45.53s

full Fins suite:
1842 passed, 1 skipped, 3 warnings in 58.70s

full Fins branch coverage:
dayu/fins/pipelines/_filing_upload_fresh_validation.py  100%
dayu/fins/pipelines/sec_upload_workflow.py               92%
dayu/fins/pipelines/cn_pipeline.py                        92%

project pyright:
0 errors, 0 warnings, 0 informations
```

唯一 skip 是仓库既有环境条件 skip；三条 warning均来自已安装 `edgar` 包 deprecated imports。所有修改生产文件逐文件 branch coverage
达到 `>=80%`。

## Scope、docs 与 residual risks

- HEAD 保持 `4812878b5a3a4884b8b8522e7113d196c4e479d9`，未 commit、未 staged、未 push、未创建 PR。
- README不更新：用户明确禁止且 accepted Slice 6拥有最终文档更新。
- frozen oracle/scenario、Host/Engine design、README均无 diff；未运行真实 evidence命令。
- 新 production模块没有 `Any`、`object`、反射、compatibility shim、目录扫描、raw meta读取或异常字符串判定。
- accepted blockers均已修复；rejected findings均有直接 owner/scope理由，没有未分类 residual risk。
- 后续 residual owner保持不变：download/README归 Slice 6；一般并发归 UF-FIX10；company warning归 UF-FIX11；material repair、旧 schema
  migration与真实 evidence分别归其独立 work unit。

## 下一入口

Slice 5 code-review fix 已完成并停在 re-review gate。下一步应独立 re-review 当前未提交 diff；本 artifact 不表示 re-review acceptance，
也不授权 commit、进入 Slice 6、创建 PR或 final closeout。
