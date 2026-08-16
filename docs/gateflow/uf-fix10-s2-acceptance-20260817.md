# UF-FIX10 S2 acceptance

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- slice：`S2 — atomic filing activation & terminal closure`
- gate：`accepted slice`
- 日期：2026-08-17
- completion status：`S2 ACCEPTED / READY TO COMMIT`
- artifact path：`docs/gateflow/uf-fix10-s2-acceptance-20260817.md`
- accepted baseline：`7e0941828c09d890ad04e3ff8f2c1cf5e28441ca`
- accepted commit：待创建；下一 gate 按用户要求在当前分支提交
- blocking open questions：无
- 下一入口：`S2 accepted slice commit`，然后进入整分支 final deepreview

## Scope 与结论

S2 在单一原子 slice 内完成 filing identical 继续 conversion、typed initial disposition、
writer-owned batch fresh validation、closed publish/skip/conflict arbitration、SEC/CN/HK shared
route 与 canonical terminal 投影。两路独立 re-review 均为 pass：

- `docs/reviews/code-review-20260817-031615.md`：逐项确认 M-F1..6、D-F1..2、C-F1 全部
  根因关闭，无新回归。
- `docs/reviews/code-review-20260817-032141.md`：独立复跑 publication/SEC/CN-HK/runtime
  focused tests，并从 typed failure、rollback signal、cancel action、runtime completion、batch 段
  并行、alias union、durable conflict 与 single terminal 八个方向完成 adversarial pass；无 finding。

本 slice 没有新增 workspace/global lock、retry、sleep/polling 竞争证明、目录扫描、字符串错误
分类、`FileExistsError` fallback 或 market-specific arbitration。material、Host/Engine/Service/CLI
production、oracle/scenario/registry/frozen evidence 均未修改。

## 语义 owner 验收

- 线性化 owner：existing per-ticker `begin_batch` writer；fresh read 与 closed arbitration 均在
  token 保护下，且发生于任何 company/source mutation 前。
- request/action owner：fresh validator 重放同一 raw request；publish/skip success 使用 fresh
  authoritative request，typed failure 与 cancelled terminal 使用 initial request，避免竞争时机
  改写 action。
- 等价 publication owner：prepared/durable 共用严格 path-free identity，覆盖完整 source
  fingerprint、primary/companions role、全部 asset metadata 与 company keep durable requirement。
- publication terminal owner：shared route 对 SKIP/CONFLICT/cancel 先 rollback，再返回或抛 typed
  failure；PUBLISH 才 stage company/source 并转交既有 atomic commit owner。
- projection owner：winner 报告实际 stored originals；converged skip 保留 requested count、stored=0，
  只投影 `FILE_SKIPPED`，不把 prepared conversion events 误报为 stored/processed。

## Findings closure

| Finding | 最终状态 | Closure evidence |
| --- | --- | --- |
| M-F1 rollback 捕获 `BaseException` | `已修复` | catch 集收窄到仓储协议普通异常；`KeyboardInterrupt`/`SystemExit` 原样传播直测 |
| M-F2 acquire/read `RuntimeError` 裸漏 | `已修复` | 两个窄边界均映射 path-free typed `STORAGE_IO`，read failure 单次 rollback |
| M-F3 fresh validator `ValueError` 裸漏 | `已修复` | 仅 validator corruption 边界映射 typed failure；arbitration/rebase invariant 不被吞 |
| C-F1 checkpoint2 cancelled action 漂移 | `已修复` | 两 checkpoint 均携 initial request；`MISSING -> COMPLETE` changed observation 精确断言 create |
| M-F4 repair transition grid 缺口 | `已修复` | `REPAIR_REQUIRED -> MISSING/COMPLETE` 均为 `SOURCE_REVISION_STALE` |
| M-F5/M-F6 runtime polling 与 README | `已修复` | held operation + bounded future 完成通知，单次读 job；publication matrix 无 sleep/retry/polling |
| D-F1 different-ticker 并行证据 | `已修复` | 两个独立 writer 在 batch fresh-read 内 barrier 会合并各自 ok |
| D-F2(a) durable conflict terminal | `已修复` | exact code/message/action/stored=0 在 runtime durable record 固定 |
| D-F2(b) create conflict 字段 | `已修复` | requested/resolved/filing 均为 create，stored=0，非 skip/非 unexpected |
| D-F2(c) same-ticker alias union | `已修复` | 两个不同 filing 携不同 aliases，canonical company meta 为 exact union |

无 accepted finding 未闭合，无 blocking open question。

## Validation acceptance

- owner/SEC/runtime 定点修复测试：`16 + 4 + 2 passed`。
- accepted focused suites：`421 passed` 与 `325 passed`。
- 完整 `pytest tests/fins -q`：`1916 passed, 1 skipped`。
- accepted focused coverage：`432 passed`；完整 Fins coverage 同样
  `1916 passed, 1 skipped`。
- modified production files coverage：CN `93%`、Docling `89%`、shared publication owner
  `87%`、SEC workflow `94%`，合计 `90%`。
- 全仓 `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- black check、`git diff --check`：通过。
- 两路 re-review 中 DS 独立 focused 复核：publication `27 passed`、SEC `13 passed`、CN/HK
  `2 passed`、runtime `2 passed`。

未运行 UF-PF10/UF-PF12 或真实 CLI evidence；未刷新 oracle/scenario registry；未修改冻结
evidence。

## README decision

- `dayu/fins/README.md`：已按职责记录 writer-owned fresh validation、closed state table、双取消、
  skip 零 mutation、same-ticker union 与 different-ticker keyed parallel。
- `tests/README.md`：已记录 focused 命令与 filesystem/barrier/spawn/held-future 并发矩阵。
- 根 `README.md`、`dayu/README.md`、Host/Engine README：职责与用户工作流未变化，不更新。

## Residual risks

- `test_fins_service_runtime.py` 的动态 monkeypatch fake 当前不进入 batch-read call path；未来调用
  路径或 required protocol 变化时由 fixture owner 同步。
- same-ticker different-filing union 的端到端证明位于 SEC；CN/HK 已证明 identical-auto shared
  route，未在当前冻结矩阵重复 market-specific union case。
- 跨进程只覆盖 exact-auto winner/skip；explicit create/cancel/rollback failure 已由线程与 owner
  级确定性测试覆盖。
- 既有非 publication-matrix runtime tests 仍使用 legacy `_wait_terminal` polling；本 slice 新增的
  concurrency evidence 已完全使用 held operation + bounded future，不扩大为全仓测试框架重写。
- oracle/scenario/frozen evidence 与 UF-PF10/UF-PF12 由后续 evidence work unit 负责。

以上 residual 均已分类且不影响当前 correctness closure；无未分类 residual risk。

## Acceptance decision

S2 implementation/review/fix/re-review loop 已闭合，全部 required semantics、tests、coverage、
pyright、README 与 scope audit 通过，故裁决：`S2 ACCEPTED / READY TO COMMIT`。

下一 gate 仅在当前分支创建 S2 accepted slice commit；提交后执行整分支 final deepreview，按用户
指示跳过 PR 创建，并在 final closeout 前复核工作树清洁与完整验证证据。
