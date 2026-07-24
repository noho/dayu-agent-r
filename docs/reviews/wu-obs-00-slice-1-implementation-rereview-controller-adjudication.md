# WU-OBS-00 Slice 1 Implementation Re-Review Controller Adjudication

```text
status=code-pass-acceptance-blocked
work_unit=WU-OBS-00
slice=S1
review_mimo=docs/reviews/code-review-20260724-125106.md
review_ds=docs/reviews/code-review-20260724-125418.md
new_actionable_findings=0
accepted_fix_closed=1
accepted_slice_commit=none
next=user decision for live workspace validation prerequisite
```

## Re-review verdicts

- AgentMiMo：`PASS — 0 new actionable findings`。
- AgentDS：`PASS — 0 new actionable findings`。

两路均确认：

- `CTRL-S1-IMPL-01` 已由 `tests/host/test_package_exports.py` 精准关闭；
- fix gate 未修改 production；
- `CTRL-S1-IMPL-02` 保持 rejected；
- Slice 1 focused tests、完整 Host tests 与 targeted/full pyright 全部通过；
- 没有新的 correctness、stability、maintainability 或 semantic ownership finding。

## Code acceptance

Slice 1 implementation 与 review fix 的代码正确性通过。验证证据：

- package export owner test：`1 passed`；
- Slice 1 focused tests：`111 passed`；
- complete Host tests：`2296 passed, 2 skipped, 6 deselected`；
- targeted/full pyright：`0 errors, 0 warnings, 0 informations`；
- 8 个修改 production Python 文件 branch coverage 均 `>=81%`；
- `git diff --check` 与 scope audit 通过。

## Acceptance blocker

accepted plan §13 Slice 1 与 §14 明确要求：

- read-only opener 能在 live WAL current workspace 上读取一致 current schema；
- current workspace read-only smoke 成功；
- smoke 前后 cold/DB hash、mtime、size 与 row count 不变。

当前真实 `workspace/.dayu/host/dayu_host.sqlite3` 的 schema=`20`，当前代码 fresh schema=`24`。
strict owner 正确抛出
`HostSchemaMismatchError(expected fresh schema 24, got 20)`，Analyzer fail closed 为
`hot_store_read_failed`。输入前后保持不变，但 success smoke 无法完成。

该 blocker 不能用 compatibility reader、raw SQLite、跳过 schema validation、cold-only
fallback、修改 producer/schema 语义或 Controller 单方面改成 fixture-only 验收来关闭。

## Final decision

`code-pass-acceptance-blocked`。不得创建 accepted Slice 1 commit，不得进入 Slice 2。

下一步需要用户明确选择真实 workspace 的处置方式。推荐做法是先将现有
`workspace/.dayu` 完整备份到明确、可恢复的位置，再按当前代码重建 fresh schema 24 的
workspace、生成 current-schema Tool Trace 样本并重跑只读 smoke。该动作会改变真实 workspace
状态，Controller 不在未获授权时执行。
