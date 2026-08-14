# WU upload-filing ticker alias contract — S2 code-review controller adjudication

## Gate

- Gate: S2 implementation review
- Base: `c5446b770d238aafd8c42552dadbe132cba94ad2`
- Review artifacts:
  - `docs/reviews/code-review-20260815-011944.md`（MiMo）
  - `docs/reviews/code-review-20260815-011809.md`（DS）
- Decision: **FAIL / enter S2 fix**

## Evidence rule

Controller 以直接代码、数据流和 accepted plan 的 binding test matrix 为裁决依据。MiMo 对核心 owner/锁序/路由给出 PASS；DS 同样确认大部分核心路径正确，但报告一个可导致静默数据丢失的实现缺陷、一个冻结测试矩阵缺口与一个测试断言回归。后者均与当前 work unit 直接同源，不能 defer。

## Accepted findings

### F1 — accepted / high：`publishes_new_corpus` 的存在性事实会吞掉 I/O 错误

- Direct evidence: `_FsStorageInfra.begin_batch` 使用 `target_ticker_dir.exists() or target_ticker_dir.is_symlink()`。`Path.exists()` 可把 stat 失败折叠为 `False`，从而构造全新空 staging 并冻结 `publishes_new_corpus=True`。
- Failure path: 权限/I/O 在 commit 前恢复时，authoritative scan 看见既有 same-canonical corpus；self-owner 校验通过，随后 backup/swap 会用空 staging 覆盖既有 corpus。
- Required fix: 用 storage-owned 显式 `os.lstat` helper 派生 exact missing/existing/I/O 状态；非目录、symlink、权限及普通 I/O 必须 fail closed，且不得在失败前产生 durable publication side effect。补 begin-time EACCES/EIO regression，并断言既有 published tree byte-for-byte 不变。

### F2 — accepted / high：accepted plan §11.3/§11.4 的锁、恢复与终态测试矩阵未完成

以下均为已冻结的 S2 gate 条目，不能以代码走读替代：

1. 跨进程 same-canonical lost-update，包括 changed-but-still-stale 拒绝与 material 两进程 alias union。
2. 既有 corpus document-only commit 不取得 recovery/identity global guards。
3. alias read 固定为 identity -> sorted publication guards，且无反向获取。
4. recovery/identity/current-scan/target-publication acquire failures 均在首次 backup/swap 前失败且 published SHA 不变。
5. conflict primary 加 identity/publication release failure 时保留 typed conflict 为 primary，并附有界 secondary note。
6. swap 后、COMMITTED 前 orphan recovery 与另一 ticker identity-changing commit 的交错；必须先恢复再拒绝冲突。
7. incoming meta-less canonical 与既有 alias 的双向 canonical conflict。
8. recovery-read barrier：recovery 在第一次 physical mutation 前持 identity guard，read 必须等待。
9. orphan recovery identity guard acquire/release failure 保留 journal/backup/staging evidence，mutation count 为零或符合 earliest-primary 规则。
10. meta-less canonical `list_documents` 与 healthy alias corpus 共存的双向 e2e。
11. SEC/CN filing/material conflict 的 terminal projection，以及 direct result/durable summary/awaiting observation failure JSON exact equality。

Required fix: 优先复用 `test_fins_storage_atomicity.py` 既有 spawn/barrier/rename harness；测试必须断言 owner 或 durable state，不得只断 event payload。若直接代码证据证明某一条已由等价测试完整覆盖，fix artifact 必须给出调用点与断言映射；否则补齐。

### F3 — accepted / low：upload awaiting snapshot 不透明性断言误移

- Required fix: 恢复 upload awaiting 测试的 `snapshot_id` 不包含内部 job id 断言，并删除 download 测试中的重复断言。

## Rejected findings / notes

MiMo 的四项均不构成缺陷：逐 entry publication guard 是当前无 durable cache 设计下的正确确定性扫描；`_PHASE_STARTED` orphan 尚未 publication；typed corruption 已先于宽泛 `ValueError` 捕获；无真实 CompanyMeta mutation 时保留 `updated_at` 是 owner contract。均无需修改，也不建立 compatibility/performance 工作。

## Preserved evidence

- Focused: `27 passed`。
- Storage atomicity + identity contract: `166 passed`。
- Relevant regression: `1574 passed, 1 skipped`。
- Full pyright: `0 errors, 0 warnings, 0 informations`。
- 当前修改生产文件 branch coverage 全部 `>=80%`，最低 82%。
- 旧 route/fallback/helper residue 为零。

这些证据证明已实现路径的质量，但不能关闭 F1/F2/F3。

## Scope constraints for fix

- 不重构既有正确 owner/锁图，不新增 durable index/cache。
- 不触碰 UF-PF05、oracle/scenario registry、冻结 evidence、Host/Engine 或其它 finding。
- README 仅在修复导致用户或开发 contract 变化时更新；单纯测试补齐不机械改文档。
- fix 完成后必须重新执行 focused、完整 relevant regression、逐文件 branch coverage、全量 pyright、residue 与 `git diff --check`，并进入双路 re-review；不得提交。
