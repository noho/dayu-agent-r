# WU-SEMANTIC-OWNERSHIP-01 R06-S1 Code Re-Review Controller 裁决

## 1. 身份与结论

- work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R06-S1 cumulative checkpoint；不是新 WU。
- baseline：`d048adf7ec1135aaf575384432ebf1137f8a34f2` 到当前完整未暂存 working tree。
- 第一路：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-mimo.md`，`PASS`。
- 第二路：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-ds.md`，`PASS`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-fix-controller-validation.md`，`PASS / READY_FOR_DUAL_COMPLETE_REREVIEW`。

最终裁决：**PASS / R06-S1 CUMULATIVE CHECKPOINT ACCEPTED**。

| Ledger | 数量 / 状态 |
|---|---|
| `R06-S1-CR-F01..03` | 全部 `CLOSED` |
| new accepted material finding | `0` |
| rejected duplicate | `0` |
| blocking question | `0` |
| intermediate accepted commit | 不创建；accepted plan §7.0 要求 S1/S2/S3 累计 cutover |

## 2. Finding closure

### R06-S1-CR-F01 — CLOSED

两路均以直接代码、AST 与 owner tests 确认 maintenance public file read 已收敛为 normalize identity、获取一次 publication guard、委托 private unguarded helper、`finally` 释放。helper 唯一拥有 contained path、missing、directory 与 bytes I/O；没有 ambient marker、重入锁、public compatibility 参数或 token-layout 推导。

### R06-S1-CR-F02 — CLOSED

两路均确认 processed meta owner 只承诺和读取 published `tool_snapshot_meta.json`；实现、protocol、wrapper 与 docstring 不存在 fallback。legacy `meta.json` fixture 是 negative proof：冲突文件不被读取，唯一 tool snapshot 缺失时 fail closed，不形成兼容承诺。

### R06-S1-CR-F03 — CLOSED

protocol、wrapper、shared core 与 private impl 的返回语义统一为 `None`。`required=False`、existing target、missing target 的 no-op/副作用均有 owner-level assertion，生产调用没有返回消费者，不存在下游 shim 或第二 success contract。

## 3. 原 S1 contract 接受

两路完整 re-review 与 Controller 独立验证一致确认：

- `BatchToken` 只含 opaque `transaction_id` 与 `ticker`；测试不依赖格式或物理布局。
- registry/core/ticker/open lifecycle 是唯一 mutation authority；无 ContextVar/task/thread/auto-batch authority。
- per-ticker writer mutex 与独立 cross-process publication guard 分工、锁序和异常释放正确。
- COMMITTED durable truth 不因 publication/writer/cleanup secondary failure 被回滚或覆盖。
- 每个 public published read 使用 outer guard/private unguarded graph；无 public-to-public read self-call。
- delayed `LocalFileSource.open()` 在 fd open 成功/失败后释放 guard，不把 batch/guard state 泄漏给 source。
- journal 精确三字段；recovery containment/symlink、malformed evidence continuation 与 pre/post-commit phases 成立。
- `R06-S1-VF-01..04` 继续 closed。
- scoped pyright/Ruff、四文件测试、逐文件 coverage 与 source scans 通过；full pyright/Ruff `110/160` 未新增或扩散，只属于 S2/S3 cumulative cutover。
- filesystem containment、symlink 防护、atomic write/rename/fsync、writer fencing、publication guard 等安全行为均保留；没有统一 tool authorization framework。

## 4. Observation 与 residual 裁决

- S2 staging acknowledgement、blob 对预先 source meta 的依赖、complete-source validator：accepted R06-S2 owner，S1 不修也不豁免。
- S3 producer/callback/composition propagation 与 full pyright 110：accepted R06-S3 owner，必须在最终 cumulative tree 清零。
- R07 snapshot/revision/opaque identity/materialize：保持 R07 独占，本轮没有偷带。
- owner tests 对 `_ActiveBatchState`、private helper 与 private impl 的窄访问只服务 failure injection/owner contract，不从 public token 推导布局；不创建 public observation API。
- 既有 JSON boundary `Any`、poll 辅助断言和 private test coupling 没有当前产品缺陷证据，不授权本轮扩域。
- Issue 175/177 与统一 authorization framework 继续未实施。

## 5. 下一 gate

R06-S1 仅作为 cumulative implementation slice checkpoint 被接受，不是 R06 或 umbrella completion。按 accepted plan §7.0 不 stage/commit；S1 working tree 与完整证据链继续累积进入 R06-S2。

下一 gate 是 AgentCodex R06-S2 complete-source single-publication implementation：只在 accepted S2 production/test allowlist 内实现 blob-first staging、删除 storage ack/incomplete contract、一次 final source publication 与 storage-owned complete-source commit validator。不得进入 S3 producer propagation、R07、Issue 175/177、README final contract、commit/push/PR。
