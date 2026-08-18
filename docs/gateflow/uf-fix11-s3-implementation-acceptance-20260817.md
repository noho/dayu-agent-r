# UF-FIX11 S3 implementation acceptance

## Gate metadata

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- gate：`S3 implementation acceptance`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- controller verdict：`ACCEPTED`
- next entry point：aggregate `$deepreview`

## Accepted implementation

S3 将 S1+S2 publication-final authoritative decision 产生的
`CompanyMetadataWarning` 作为 typed tuple 机械传播到 runtime summary、durable summary JSON、direct public
result、CLI stderr 与 completed wait result。CLI、wait adapter、renderer 与 service runtime 均不读取原始参数、
日志文本、字段 diff、disposition 或文件状态来重新判断 ignored change。

接受的关键边界：

- `FinsUploadResultSummary` 只允许 `ok` / `skipped` 携带 exact、at-most-one warning；
- `FinsResultSummary` 只允许 `SUCCESS` 携带 exact、at-most-one warning；
- `_direct_result_event` 的 `warnings` 为无默认值的 keyword-only 参数，生产调用点全集恰为两处：upload 显式复制
  `summary.warnings`，generic path 显式传入自然空 tuple；
- CLI success 保持原 stdout 摘要与退出码，只把 canonical business warning 写入 stderr；
- completed wait result 恒包含 `warnings` 数组，非 upload 为自然空值 `[]`；failed/cancelled 不投影或推断 warning；
- durable JSON 与 public result 均从同一 typed warning 值派生，repository save/re-read 由既有真实 job-store 测试关闭。

## Review adjudication

首轮独立实现审查：

- MiMo：`PASS`，无 blocker/medium/high finding；
- DS：`PASS`，提出 3 个 low finding。

Controller 将 DS 的 3 项 low finding 全部要求本轮关闭：

1. 补全 `_completed_result_value` 对 completed `warnings` schema 的中文 docstring；
2. 增加 uploaded/skipped 两种真正经过 `cli_main.main()` production command loop 的 mocked CLI 测试；
3. 增加真实 `ProductionFinsUploadRunner.run_upload` 的 pipeline JSON → typed parser → runner summary → canonical
   durable serializer 复合链测试。

定向 re-review：

- MiMo：`PASS`，确认 F-01/F-02/F-03 全部关闭；
- DS：`PASS`，确认 F-01/F-02/F-03 全部关闭，且 serializer 与 repository save/re-read 的职责措辞没有混淆。

对应证据：

- `docs/reviews/uf-fix11-s3-implementation-review-mimo-20260817.md`
- `docs/reviews/uf-fix11-s3-implementation-review-ds-20260817.md`
- `docs/gateflow/uf-fix11-s3-implementation-review-fix-20260817.md`
- `docs/reviews/uf-fix11-s3-implementation-rereview-mimo-20260817.md`
- `docs/reviews/uf-fix11-s3-implementation-rereview-ds-20260817.md`

## Validation accepted

- 最小 review-fix tests：`26 passed, 3 warnings`；
- S3 focused：`546 passed, 3 warnings`；
- combined regression：`2155 passed, 1 skipped, 3 warnings`；
- branch coverage：`ingestion_runtime` 89%、`service_runtime` 88%、`direct_events` 83%、`output` 82%、
  `fins_wait_adapter` 91%；
- full pyright：`0 errors, 0 warnings, 0 informations`；
- `git diff --check`：通过；
- `_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed`：零 diff；
- Host、Engine、pipeline/storage owner、frozen oracle/scenario/registry：零 diff；
- 未运行真实 CLI、network、calibration 或 frozen evidence，符合本 work unit 非目标。

## Residual risk classification

- accepted tradeoff：completed wait 对非 upload 返回 `warnings: []`；
- bounded uncovered area：没有新增单一 fixture 贯穿 production runner 到 direct private execution context；真实
  runner handoff 与 summary→direct typed copy 已分别由 owner-level tests 关闭；
- later work units：name-only metadata batch writer lock/physical swap 成本、material upload 类似行为、真实
  CLI/network/scenario evidence、post-commit cleanup 可见性；
- blocking 或未分类 residual risk：无。

## Gate decision

S3 implementation 与 review-fix 被接受。语义 owner、success-only invariant、机械投影、用户可见双流行为、
LLM-facing completed result、durable serializer、README 与验证证据一致，可以进入 aggregate `$deepreview`。
