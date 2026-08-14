# WU upload-filing ticker alias contract — S2 final controller adjudication

## Gate result

- Final narrow re-review:
  - MiMo: PASS — `docs/reviews/code-review-20260815-022227.md`
  - DS: PASS — `docs/reviews/code-review-20260815-022428.md`
- Controller decision: **PASS / accept S2**

## Accepted evidence

1. `begin_batch` 与 commit-time backup 的存在性事实均由同一显式 `os.lstat` owner 派生：仅 `ENOENT` 表示 missing；`EACCES/EIO`、symlink 与 non-directory 均在首次 replace 前 fail closed。
2. 失败测试断言 published locator/tree、backup evidence 与内部 batch state 的 exact 不变/收口；begin-time 非目录测试还通过同 ticker retry 证明 reservation 与 writer lock 可恢复。
3. accepted plan §11.3/§11.4 的 11 组并发、锁、恢复、typed failure 与 list_documents e2e 矩阵均已由两路 reviewer 逐条确认是 owner/durable/e2e 断言。
4. SEC/CN filing/material 使用同一 typed failure mapper；canonical 与 accepted aliases 只经 storage 的 `resolve_company_ticker` 路由，旧 route、list-index 与 read fallback 已删除。
5. README 更新符合职责，未触碰 UF-PF05、oracle/scenario registry、冻结 evidence、Host/Engine 或其它 finding。

## Validation

- Final focused: `7 passed`。
- Identity + storage contract: reviewer 独立复跑 `198 passed`；implementation 组合回归 `190 passed`。
- Full relevant: `1604 passed, 1 skipped, 3 warnings`。
- 所有修改生产文件 branch coverage `>=80%`，最低 83%，`_fs_storage_infra.py` 84%。
- Full pyright: `0 errors, 0 warnings, 0 informations`。
- 修改文件 ruff/format、residue 与 `git diff --check`: 通过。

## Residual risk

- 未执行用户明确排除的 UF-PF05 真实 CLI evidence。
- ACL/NFS 等外部文件系统行为未做跨平台真实环境验证；errno 注入已覆盖 owner 分型。
- identity route 每次扫描 workspace corpus；accepted plan 已明确不增加 durable cache，暂无性能证据支持扩展。
- material pipeline-direct 缺公司名的既有 admission 投影不属于本 alias work unit，未扩展。

## Next gate

创建 accepted S2 local commit，随后对完整 work unit 执行 aggregate deepreview。aggregate pass 前不得 final closeout。
