# WU-SEMANTIC-OWNERSHIP-01 R07-S2 code-review fix Controller validation

## 1. Gate 与结论

- Active WU：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Internal remediation sub-WU：R07；checkpoint：累计 S1+S2 code-review fix。
- Accepted finding：`R07-S2-CR-F01`。
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-fix-codex.md`。
- 结论：**PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_S1+S2_RE-REVIEW**。
- 本结论只授权双路 re-review；不授权 S1/S2 commit、S3、R08+、deferred Issues、统一 authorization、push 或 PR。

## 2. Owner 与实现复核

Controller 逐段复核了 protocol、private implementation、三个 consumer 与新增测试：

- `SourceSnapshotProtocol` 只新增标准 `__enter__` / `__exit__` resource lifecycle；`__exit__` 返回 `Literal[False]`，类型和运行时均明确不压制 lifecycle body exception。
- private `_FsSourceSnapshot.__exit__` 复用 storage owner 的 `_append_secondary_error_note(...)`：
  - 无 active primary 时，`close()` failure 保持 path-free 主失败并正常传播；
  - 有 active primary 时，保留同一 primary exception identity，close failure 只追加固定 action/type/errno note；raw close message、cause、context、traceback 与 locator 不进入最终 graph。
- 显式 `close()` 的幂等、关闭后不可读、cleanup 失败后保留 temp-root locator 供后续重试语义未改变。
- preprocess、SEC fiscal、active 6-K 三个 consumer 全部改为 `with snapshot`，没有 `sys.exc_info()`、consumer-local exception helper、fallback、facade 或 compatibility branch。
- preprocess 仍在 context 正常退出后才设置 `commit_started=True` 并 commit；close failure 仍走 pre-commit rollback。6-K source mutation 仍发生在 context 退出后。Fiscal acquisition-only best-effort 边界和提取算法不变。
- 没有进入 S3 read/cache/borrow/citation/file-kind migration；security、containment、symlink、atomic/recovery、opaque identity/revision 与 LLM-facing scope均未改变。

## 3. Controller 独立验证

### 3.1 Owner-level 双失败节点

Controller 独立运行：

- `test_snapshot_context_preserves_active_primary_when_close_fails`
- `test_snapshot_context_propagates_close_failure_without_active_primary`

结果：

```text
2 passed in 0.35s
```

前者断言顶层仍是同一个业务主异常、exception graph 仅含该节点、secondary note 只含 action/type/errno；后者断言无 active primary 时 path-free close failure 不被吞且显式 close 可在清理恢复后重试。

### 3.2 五文件累计测试

Controller 独立运行五个 cumulative test files，结果：

```text
401 passed, 3 warnings in 23.53s
```

三条 warning 均是既有 `edgar` deprecated import。

AgentCodex coverage run 为 `401 passed, 3 warnings`；15 个累计 changed production files line coverage 为 `80.00%`–`100.00%`，snapshot owner `90.20%`、protocol `100.00%`。

### 3.3 静态、传播与安全验证

- full `pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 15 production + 5 cumulative test files scoped Ruff：`All checks passed!`。
- `git diff --check`：通过。
- consumer scan：三个目标文件无 `snapshot.close()`、`sys.exc_info` 或 `_append_secondary_error_note`，均由统一 context lifecycle 持有退出语义。
- accepted plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`，匹配。
- temp-root scan：无 `dayu-source-snapshot-*` 残留。
- README trigger：本 fix 未改变已记录的稳定用户/业务 contract，不新增 README 修改的裁决成立。

## 4. Finding 状态与 next gate

`R07-S2-CR-F01` 已实现关闭，等待 AgentMiMo / AgentDS 双路完整累计 S1+S2 re-review 独立确认。S1 `R07-S1-CR-F01..03` / `R07-S1-CR-CV-F01` 与 S2 `R07-S2-CV-F01..03` 在本修复后仍保持关闭。当前无 Controller 新增 finding、无 blocker。
