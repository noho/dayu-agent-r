# UF-FIX10 S2 Implementation

## Gate metadata

- work unit：`UF-FIX10 same-request-concurrency`
- slice：`UF-FIX10-S2`
- gate：`implementation`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 基线提交：`7e0941828c09d890ad04e3ff8f2c1cf5e28441ca`
- completion status：`IMPLEMENTATION PASS / READY FOR CODE REVIEW`
- next entry point：`S2 code review`
- commit：未创建
- blocking open questions：无

## Motivation 与 owner decision

问题成立：filing preparation 的 early identical skip 位于 per-ticker writer 之外，两个从同一
`MISSING` observation 准备的相同请求会在 writer 串行后重复发布；旧 workflow 没有在
writer-owned fresh view 上把第二个 candidate 收敛为 canonical skip。该问题会产生不必要的
revision/publication，并可能把 derived 或 company 事实不同的 candidate 错误当作同一请求。

语义 owner 固定为 `filing_upload_publication`：preparation owner 只产生 exact candidate identity
和 closed initial skip disposition；storage owner 只产生 batch fresh company/source state；shared
publication owner 在同一个 per-ticker batch 中调用同一 validator并完成 closed arbitration、双取消
checkpoint、company stage 与 existing commit/rollback owner 的 capability 交接。SEC/CN/HK 只机械
调用并投影 fresh authoritative action，不复制 state table。material 与 filing delete 不进入该 identity
arbitration，保持既有行为。

## Implemented scope

- `docling_upload_service.py`：filing identical 不再 preparation early terminal；继续转换 primary，
  并把 `IDENTICAL_PUBLICATION` 或 `NOT_ELIGIBLE` 接入 required prepared subtype。material identical
  仍 early skip。canonical skip result只包含 originals 的 `file_skipped`，不投影未发布 conversion event。
- `filing_upload_publication.py`：实现唯一 shared lifecycle：begin、checkpoint1、batch fresh read、同一
  validator、closed arbitration、checkpoint2、fresh company stage、prepared/rebase publish，或空 batch
  rollback skip/cancel/conflict。state-dependent usage映射 publication conflict；unsafe、revision stale、
  storage I/O/corruption 与 rollback primary/secondary 保持 typed owner reason。
- `sec_upload_workflow.py` / `cn_pipeline.py`：filing upsert直接调用 shared owner；completed action来自
  fresh outcome，failed action仍来自 initial prepared request。material路径未修改；delete保留既有 route。
- tests：覆盖 SEC single/multi exact auto、explicit create no-overwrite/overwrite、derived/company mismatch、
  same ticker different filing union、different ticker、CN、HK、spawn process、explicit update stable/changed、
  durable runtime terminal、writer-wait checkpoint1三分支、checkpoint2三分支、rollback failure 与 late-cancel
  既有边界。所有并发同步只使用 Event/Barrier/Queue/future/join 的有界等待；未新增 sleep、retry或 polling。
- README：Fins 开发契约同步 shared owner、exact equality、取消/rollback 与 event/count 语义；测试手册同步
  focused command及真实线程/进程矩阵。

## Validation evidence

- 第一 focused（writer-wait cases加入前）：`409 passed`；新增三项定点：`3 passed`。
- 第二 focused：`325 passed`。
- 最终五个 allowed focused files：`512 passed`。
- 最终完整 Fins suite：`1907 passed, 1 skipped`。
- accepted coverage suite：`421 passed`。
- 完整 Fins coverage复核（writer-wait cases加入前）：`1904 passed, 1 skipped`；modified production files：CN `93%`、
  Docling upload `89%`、shared publication `84%`、SEC workflow `94%`，合计 `90%`。
- full pyright：`0 errors, 0 warnings, 0 informations`；writer-wait test加入后该文件定点 pyright同为 `0`。
- `git diff --check`：通过。

## Scope audit 与 residual risk

工作树只包含 accepted S2 production/test/README files、本文 artifact 与 accepted plan gate metadata；
未修改 root/dayu README、oracle、scenario、registry、frozen evidence、Service/CLI/tool、runtime production、
material contract、UF-PF10 或 UF-PF12，未创建 commit。

无已知 correctness blocker。非阻塞 residual 是 Docling converter 本身若对同一 original 产生不同 bytes，
exact identity owner会让 concurrent loser typed conflict而不是近似 skip；这是明确的 fail-closed contract，
已由 derived mismatch test与 Fins README记录。下一 gate 必须执行 S2 code review；本 artifact不预判 review
结论或 acceptance。
