# WU-CLI-CONFORMANCE-F01-F07 S2/F02 Code Review 总控裁决

## Gate 元数据

- Gate：`S2 implementation slice review`
- Base/HEAD：`a41526ecbf5c1d16c24a19114b0d0e21208d1dd0`
- Implementation artifact：`docs/reviews/wu-cli-conformance-f01-f07-s2-implementation-codex.md`
- Review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-ds.md`
- 裁决结论：`FIX REQUIRED — 3 项 accepted code finding，修复后必须双路 re-review`

## 独立证据裁决

两路 reviewer 都认为主路径符合 F02，但总控没有用结论一致性代替证据，而是逐项回到 frozen F02、accepted plan §4、生产 diff 与 owner tests。

| ID | 来源 | 裁决 | 严重度 | 直接证据与处置 |
|---|---|---|---|---|
| `S2-C01` | MiMo 001、DS 1 | `accepted` | 中 | `dayu/cli/composer.py:811-819` 的 `finally` 在 unlink 也失败时会用 `CLEANUP_FAILED` 覆盖正在传播的 `SPAWN_FAILED`/`READBACK_FAILED`。composer 是错误原因唯一 owner，不能投影错误根因。修复须始终尝试 cleanup，但双故障时保留 primary failure；不得引入事务回滚或下游补偿，并增加组合失败 owner test。 |
| `S2-C02` | 总控新增 | `accepted` | 中 | accepted plan §4.2 明确要求打开 editor 前冻结 original public `Buffer.document`；当前 `_open_explicit_editor()` 仅 `create_task`，到 coroutine 首次调度的 `_run_explicit_editor_round_trip()` 才读取 `buffer.document`。按键处理返回到 event loop 与 task 首次执行之间存在输入/teardown 竞态。须在 synchronous binding call path 冻结 `Document` 并作为显式参数传给 round trip，测试证明 task 调度前后 buffer 变化不能改变 original snapshot。 |
| `S2-C03` | 总控新增；DS Open Question 2 | `accepted` | 中 | accepted plan §4.3 的状态机只有一个 `EDITOR_PENDING`；当前 handler 每次有效 Ctrl-X Ctrl-E 都创建 task，`editor_tasks` 是无上限集合。重复快捷键可产生多个 subprocess，完成顺序可覆盖同一 buffer，违反单一 editor action owner。须在 owner 边界禁止 pending 时再次 launch，并以 owner test 断言只有一个 task/process、无第二次 buffer write。 |
| `S2-C04` | DS 2 | `accepted as cleanup` | 低 | `updated_text is None` 分支由当前控制流证明不可达。随 fix 删除该 dead branch并保持严格类型，不增加兼容路径。 |
| `S2-R01` | MiMo 002 | `rejected` | 低 | `editor_tasks=set()` 被 returned bindings 的 handler closure 与 done callback 持有，并非 reviewer 所称“无外部引用”；完成 task仍被消费。该 public binding builder 不拥有 application teardown，生产入口使用 `PromptToolkitInteractiveComposer` 的共享集合与 `read_event finally`。不为未承诺的独立 application lifecycle 增加第二 owner；`S2-C03` 会同时阻止该路径重复 launch。 |
| `S2-R02` | DS 3 | `not a defect` | 低 | `_write_editor_diagnostic` 的 broad `Exception` 位于 diagnostic sink 最外层，且不捕获 `BaseException`；它防止 background callback 产生第二个 traceback，符合 frozen“无 traceback”与 AGENTS owner边界。无需修改。 |

## Cross-slice pyright 分类纠正

两路 review 与 implementation artifact 都把全仓 pyright 的两处 `utils/...explicit_config_dir` 残留称为 “existing debt / covered by S8”。该分类不准确：两个 call site 在 S1 entry HEAD 可通过，删除 request field 后才报错，因此是 **S1 引入的 cross-slice regression**，不是既有 debt，也不能拖到 S8 aggregate closure。

S2 fix 只修本 slice allowlist并在 implementation artifact 中纠正文字；S2 accepted commit 后、进入 S3 前，必须建立独立的 S1 corrective fix/review/re-review/commit gate，机械删除：

- `utils/smoke_cli_init_provider_matrix.py:2386` 的旧 keyword；
- `utils/smoke_host_public_awaiting_entrypoint.py:808` 的旧 keyword。

该独立 gate 必须以 full `python -m pyright` 零错误为 acceptance signal，不得恢复兼容字段。

## Residual risk disposition

- 真实 PTY terminal suspend/resume：`covered by later approved slice S8`；必须进入最终 immutable evidence bundle。
- Windows text-mode newline：`out of scope`；当前 interactive/PTY contract 与现有 tests 明确为 POSIX，本 work unit 不扩张平台语义。
- filesystem 双故障：只修 primary-error ownership；不新增竞态模型、rollback 或 filesystem product contract。
- 当前三项 accepted code finding 未收口，S2 gate 不通过。

## Fix gate allowlist 与验证要求

只允许修改：

- `dayu/cli/composer.py`
- `tests/cli/test_interactive_composer.py`
- `tests/cli/test_interactive_command.py`（只有 owner integration 断言确有需要时）
- `docs/reviews/wu-cli-conformance-f01-f07-s2-implementation-codex.md`（追加 fix 记录并纠正 pyright 分类）
- 新增 `docs/reviews/wu-cli-conformance-f01-f07-s2-fix-codex.md`

验证至少包括 focused pytest + composer 单文件 coverage `>=80%`、focused pyright、`git diff --check`、registry JSON/hash不变、index为空。Fix 后 MiMo/DS 必须分别用 `/deepreview` 写 durable re-review artifact，总控再逐项关闭 `S2-C01`–`S2-C04`。
