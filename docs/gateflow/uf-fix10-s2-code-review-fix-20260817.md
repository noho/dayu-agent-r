# UF-FIX10 S2 code review fix

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- slice：`S2 — atomic filing activation & terminal closure`
- gate：`code-review fix`
- 日期：2026-08-17
- accepted baseline：`7e0941828c09d890ad04e3ff8f2c1cf5e28441ca`
- adjudication：`docs/gateflow/uf-fix10-s2-code-review-adjudication-20260817.md`
- completion status：`CODE REVIEW FIX COMPLETE / READY FOR INDEPENDENT RE-REVIEW`
- accepted commit：未创建
- 下一入口：两路独立 S2 code re-review

## 第一性原理与 owner 判定

两路 review 报告的问题成立。根因不是 per-ticker linearization 或 atomic swap 缺失，而是 shared
publication owner 的三个窄异常边界没有完整遵守既有 storage/validator failure contract，以及
accepted plan 要求的部分并发成功信号没有直接固定到真正的 writer-owned 边界。

修复继续由 `filing_upload_publication` 持有 batch acquire、fresh read、fresh validator、双取消
checkpoint 和 rollback 投影；没有在 SEC/CN/HK facade、runtime renderer 或测试夹具中补偿错误语义。
不同 ticker 并行、same-ticker company alias union 与 durable terminal 只增加确定性证据，不增加生产
hook、global lock、retry、sleep 或 polling。

## Accepted findings 修复

| Finding | 修复与直接证据 |
| --- | --- |
| M-F1 | cancel/skip rollback 只捕获协议声明的 `OSError`、`RuntimeFileLockError`、`ValueError`；`KeyboardInterrupt` / `SystemExit` 原样传播，owner 直测覆盖两类信号。 |
| M-F2 | batch acquire 与 writer-owned fresh read 两个窄边界分别把 `RuntimeError` 映射为既有 path-free `STORAGE_IO`；直测固定 acquire 零 token、fresh read rollback 与 exact failure。 |
| M-F3 | 只在 fresh validator 调用边界把其 `ValueError` 映射为 typed prevalidation corruption；arbitration/rebase programming invariant 仍不做通用捕获。 |
| C-F1 | 两个取消 checkpoint 都返回 initial authoritative request；新增 `MISSING -> COMPLETE`、fresh action 为 `update` 的第二 checkpoint 用例，精确断言 cancelled action 仍来自 initial `create`。 |
| M-F4 | conflict grid 显式加入 `REPAIR_REQUIRED -> MISSING` 与 `REPAIR_REQUIRED -> COMPLETE`，两行均为 `SOURCE_REVISION_STALE`。 |
| M-F5/M-F6 | 新增 runtime 竞争用例改用 holding executor 收集恰好两条 owner operation，再由两个 future 有界完成；终态只各读取一次，不调用 `_wait_terminal`，README 的无 sleep/polling 描述与事实一致。 |
| D-F1 | different-ticker 用真实 filing-state repository wrapper，在两个请求都已取得各自 batch 并进入 fresh read 后以 barrier 会合；same-ticker distinct filing 同时携带不同 aliases，最终 canonical company meta 精确包含 `MSFT` 与 `GOOG`，无丢失。 |
| D-F2(a) | runtime concurrent explicit create 持久化一条 `SUCCEEDED/ok` 与一条 `FAILED`；loser 的 durable failure summary/result failure 精确等于 `SOURCE_PUBLICATION_CONFLICT` factory JSON，请求 action 为 `create`、stored 为 `0`。 |
| D-F2(b) | SEC explicit create no-overwrite loser 精确断言 requested/resolved/filing action 均为 `create`、stored 为 `0`、非 skip、非 unexpected runtime，failure code/message 等于 canonical factory。 |
| D-F2(c) | same-ticker distinct filing 最终 company aliases 精确 union，无 consumer 从 raw fields 重算。 |

## Validation evidence

- 新增/受影响定点：publication owner `16 passed`；SEC 并发字段/union `4 passed`；runtime durable terminal `2 passed`。
- accepted focused suite 1：`421 passed`。
- accepted focused suite 2：`325 passed`。
- 完整 `pytest tests/fins -q`：`1916 passed, 1 skipped`。
- accepted focused coverage suite：`432 passed`。
- 完整 Fins coverage 复核：`1916 passed, 1 skipped`；modified production files 分别为：
  - `cn_pipeline.py`：`93%`
  - `docling_upload_service.py`：`89%`
  - `filing_upload_publication.py`：`87%`
  - `sec_upload_workflow.py`：`94%`
  - 合计：`90%`
- 全仓 `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- Black check：四个本轮直接修改的 production/test Python 文件均 unchanged。
- `git diff --check`：通过。

## README、scope 与 residual risk

`tests/README.md` 现明确记录 held runtime operation 的 bounded future 完成通知、不同 ticker
writer-owned fresh-read barrier、same-ticker aliases exact union 与 durable explicit-create conflict。
`dayu/fins/README.md` 的 shared owner 稳定契约无需因本轮窄异常与证据修复再扩写；根 README、
`dayu/README.md` 及其它 README 不命中职责触发。

工作树只包含既有 S2 allowlist、accepted plan gate sync、implementation/adjudication/fix artifacts 与
两路只读 review artifacts。未修改 review artifacts、oracle、scenario、registry、frozen evidence、
Service/CLI/tool、runtime production、material contract 或 UF-FIX11；未运行 UF-PF10/UF-PF12；未新增
generic exception fallback、compatibility、production hook、global lock、sleep、retry 或 polling；未创建 commit。

无未分类 residual risk。既有已分类的 converter nondeterminism fail-closed tradeoff 与未来 storage
operational hardening owner 不因本轮修复改变。当前 gate 仅表示 ready for independent re-review，
不预判 re-review 或 S2 acceptance。
