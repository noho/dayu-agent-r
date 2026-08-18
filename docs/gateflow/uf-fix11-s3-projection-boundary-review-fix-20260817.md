# UF-FIX11 S3 Projection Boundary Plan Review Fix

## Gate metadata

- gate：`S3 projection boundary plan review-fix`
- 日期：2026-08-17
- initial reviews：
  - `docs/reviews/uf-fix11-s3-projection-boundary-review-mimo-20260817.md`
  - `docs/reviews/uf-fix11-s3-projection-boundary-review-ds-20260817.md`
- completion status：`READY FOR RE-REVIEW`
- implementation status：`PAUSED`

## Controller adjudication and fixes

- DS F-01：`ACCEPT / FIXED`。补齐两个 summary 的 exact-element、at-most-one、non-success + nonempty
  constructor 红测；pin upload summary 仅 `ok`/`skipped` 可携带，并增加 uploaded 空值与 deleted 空值投影。
- DS F-02：`ACCEPT / FIXED`。AST contract 必须穷举全部 `_direct_result_event` callsites，exact 两个且实参分别
  为 `summary.warnings` 与 `()`；第三个 callsite 必须红。
- DS F-03：`ACCEPT / FIXED`。pin `FinsUploadResultSummary.warnings=()`；service owner仍显式复制 pipeline tuple，
  默认值不授权漏传。
- DS F-04：`ACCEPT / FIXED`。runtime helper/AST tests 落在 `test_fins_ingestion_runtime.py`；
  `test_fins_direct_stream.py` 只拥有 public result/stream contract。
- DS F-05：`REJECTED-WITH-REASON`。CANCELLED + nonempty warning 是非法 typed producer 组合，必须由 public
  constructor fail closed；helper 静默清空会掩盖 owner violation。计划增加直接拒绝红测，不修改 helper 归一化。
- MiMo Finding-001：`ACCEPT / FIXED`。stop/static checks 显式冻结三个 observation helpers；它们保持自然空默认，
  不纳入 S3 symbol 白名单。

## Boundary and residuals

本 fix 只修改 plan/amendment 并新增本 artifact。production、test、README、S1+S2 parser/codec、Host、Engine、
material、oracle、scenario 与 frozen evidence 均无 diff。所有 initial review findings 已分类为 fixed 或
rejected-with-reason；未分类 residual risk 为零。S3 implementation 继续暂停，下一入口为 MiMo/DS 双路定向
re-review。
