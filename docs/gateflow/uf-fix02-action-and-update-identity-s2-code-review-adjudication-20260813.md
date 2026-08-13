# UF-FIX02 action-and-update-identity — S2 Code Review Adjudication

## Gate context

- Base / accepted S1 commit：`08316516ca3da7f98299ee90d3fa753c32c59020`
- AgentMiMo review：`docs/reviews/code-review-uf-fix02-s2-mimo-20260813.md`
- AgentDS review：`docs/reviews/code-review-20260813-184708-uf-fix02-s2-ds-20260813.md`
- Both reviewer verdicts：`PASS`

## Controller decision

S2 主路径设计成立，未触发 stop condition；进入一次 bounded code-review fix，然后双路 re-review。

### DS Finding 1：reset→create 重置 `created_at`

- Decision：**accepted，blocking before S2 acceptance**。
- Severity：中。
- Owner：`DoclingUploadService._build_upsert_meta(...)` 对上传 publication meta 的派生边界。
- Reason：`created_at` 与 `first_ingested_at` 都是 durable source 首次创建事实。同库 download/rebuild owner 已明确保持
  二者稳定；S2 不能因内部 mutation 从 update 改为 reset→create 而改变业务事实。该漂移由本 diff 扩展到所有
  existing update，属于 owner-level semantic drift，而非非目标。
- Required fix：仅从 reset 前 `previous_meta` 派生稳定 `created_at`；缺失时使用本次 `now`。不得在 storage 下游
  fallback，也不得改变 batch/admission/workflow。
- Required tests：renamed update、deleted restore、material shared-owner parity 至少断言 `created_at` 保持；保留
  version / `first_ingested_at` 断言。

### MiMo Finding 1：测试 spy 保留不可达 update override

- Decision：**accepted**。
- Severity：信息。
- Owner：`tests/fins/test_docling_upload_service.py` 测试 double。
- Required fix：删除 `_FailingFinalUploadSourceRepository.update_source_document(...)` dead override；保留 create failure
  注入与 `create_failed` 断言，不增加兼容路径。

## Fix gate constraints

- tests-first：先增加 `created_at` owner assertions 并证明当前实现 RED，再修改生产 owner。
- 只允许修改 `dayu/fins/pipelines/docling_upload_service.py`、`tests/fins/test_docling_upload_service.py`、S2
  implementation artifact，以及新增 fix artifact；若 README 当前表述无需变化则不改。
- 完成后重跑 S2 focused、UF-FIX01/atomicity/cancellation regression、逐生产文件 coverage、完整 pyright、
  frozen no-touch 与 `_resolve_upsert_mode` 零命中审计。
- 不进入 UF-PF02，不 commit/push/PR。

无其它 accepted finding；UF-FIX07/08/10 等保持原 residual owner。
