# UF-FIX10 final deepreview fix

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`final deepreview fix`
- 日期：2026-08-17
- base：`656b926c`
- accepted S2 commit：`047691c8`
- adjudication：`docs/gateflow/uf-fix10-final-deepreview-adjudication-20260817.md`
- completion status：`FINAL DEEPREVIEW FIX COMPLETE / READY FOR RE-REVIEW`
- accepted commit：本 gate 未创建
- 下一入口：两路独立 final deepreview re-review

## 第一性原理与修复边界

三项 accepted-low finding 均成立，但生产语义没有缺陷。根因是 workflow 并发测试使用聚合终态与
单 target `COMPLETE` 间接代替了 accepted plan 已冻结的真实 stream、ticker-level inventory、
asset union 与逐 commit durable snapshot 证据。

本轮只修改 `tests/fins/test_sec_pipeline_upload_filing_stream.py`。测试复用 production
`describe_prepared_filing_publication`、公开 `FilingUploadStateRepository`、公开
`SourceDocumentRepository.list_source_document_ids/read_source_snapshot` 与真实 batch commit；没有复制
identity、manifest、version 或 revision 业务计算，没有扫描目录或猜测 raw path，也没有修改任何生产或
README 文件。

## Findings 修复

### D-F1 — multi-file concurrent loser events / winner snapshot

- 新增最小真实 stream 并发 helper：每个 OS 线程用独立 event loop 完整收集
  `SecPipeline.upload_filing_stream()`，future 以 20 秒上限等待，不做 polling。
- test-only `DoclingUploadService` subtype 仍执行真实 `prepare_upload()`，仅在返回后调用 production
  `describe_prepared_filing_publication()` 记录 owner-produced identity。
- concurrent exact-auto 的 loser event sequence 精确为：`UPLOAD_STARTED`、每个 original 各一条
  `FILE_SKIPPED`、`UPLOAD_COMPLETED`；primary+companion 名称顺序精确，无
  `CONVERSION_STARTED`。
- 两个真实 prepared identities exact equal；durable filing-state publication identity 与 prepared
  identity exact equal。公开 source snapshot 的 revision/meta/primary/完整 asset names 与同版 durable
  state/identity 精确对照，且无额外 asset。

### D-F2 — same-ticker different-filing exact union

- 保留 canonical company aliases exact union `{MSFT, GOOG}`。
- 经公开 `list_source_document_ids("AAPL", FILING)` 读取 ticker-level inventory，精确等于 Q1/Q2
  两个 request document IDs，无额外条目。
- 对两个 document 分别读取公开 source snapshot，并与各自公开 filing-state publication identity 对照
  revision、primary、asset count 与 exact asset-name set；最终 `(document_id, asset_name)` union 精确相等，
  无丢失或额外 asset。

### D-F3 — concurrent create-overwrite durable rebase invariants

- test-only batching subtype 仍调用真实 `commit_batch()`；第一个 commit 返回后立即经公开 source snapshot
  记录 source meta 与 opaque revision，并以 `Event` 通知第二个 writer 进入真实 batch。
- converter barrier 仍保证两个 raw explicit create-overwrite request 均先在 initial view 完成 preparation；
  Event 只在两个 per-ticker commit 之间建立确定性 snapshot 边界。
- 两个 commit snapshot 精确断言同一 document ID；第二次保持第一次的 `first_ingested_at`、`created_at`、
  `source_fingerprint` 与 `document_version == "v1"`，同时由 storage owner 产生不同 opaque revision。

## Validation evidence

- 三项 SEC 定点（参数化共六 case）：`6 passed, 40 deselected`。
- UF-FIX10 accepted focused suite：`746 passed`。
- 完整 `pytest tests/fins -q`：`1916 passed, 1 skipped`。
- 全仓 `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `python -m black --check tests/fins/test_sec_pipeline_upload_filing_stream.py`：通过。
- `git diff --check`：通过。

## Scope、docs 与 residual risk

代码 diff 只有 `tests/fins/test_sec_pipeline_upload_filing_stream.py`；另同步 accepted plan gate metadata
并新增本 fix artifact。final deepreview adjudication 与两份 review artifacts 保持只读。未修改生产、README、
oracle、scenario、registry、frozen evidence 或其它测试；未运行 UF-PF10/UF-PF12；未新增 sleep、retry、
polling、目录扫描、generic exception fallback 或 production test hook；未创建 commit。

README 不更新：用户可见行为、生产 developer contract 与测试手册职责事实均未改变，本轮只是补齐已冻结的
workflow 端到端断言。无未分类 residual risk；final deepreview 已记录的存量低风险继续保留原 owner，
不因本轮 test-only fix 扩大。当前 gate 只表示 ready for independent re-review，不预判 final closeout。
