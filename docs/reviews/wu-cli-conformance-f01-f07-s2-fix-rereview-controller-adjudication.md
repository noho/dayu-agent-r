# WU-CLI-CONFORMANCE-F01-F07 S2/F02 Fix Re-review 总控裁决

## Gate 元数据

- Gate：`S2 code-review fix re-review`
- Base/HEAD：`a41526ecbf5c1d16c24a19114b0d0e21208d1dd0`
- Fix artifact：`docs/reviews/wu-cli-conformance-f01-f07-s2-fix-codex.md`
- Re-review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s2-fix-rereview-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s2-fix-rereview-ds.md`
- 裁决结论：`PASS — S2-C01..S2-C04 全部关闭，无新增 accepted finding`

## Accepted finding 关闭裁决

| ID | 最终状态 | 总控直接证据 |
|---|---|---|
| `S2-C01` | `closed` | `_run_explicit_editor_round_trip` 以单一 `primary_failure` 标记包住整个 round trip，任何在途 `BaseException` 原样重抛，`finally` 始终尝试 unlink，只有无 primary 时 cleanup failure 才成为 `CLEANUP_FAILED`。spawn/readback + cleanup 以及 cancellation + cleanup 组合测试均通过。 |
| `S2-C02` | `closed` | `_open_explicit_editor` 在同步 handler call path、`create_task` 前读取完整 public `Buffer.document`，并把必填 snapshot 传入 async round trip；调度前修改 live buffer 的测试仍观察到原 snapshot。 |
| `S2-C03` | `closed` | handler 入口以同一 `_EditorTask` set 作为 `0..1` pending 真源；显式与 unset system task 都占用该 slot，done/teardown 释放。重复 chord 测试精确断言一个 task、一个 process、一次 buffer write。 |
| `S2-C04` | `closed` | `updated_text` 为严格 `str`，不可达 `None` branch 与对应 `RuntimeError` 已删除；pyright 证明所有到达回填点的路径均已赋值。 |

## 首审其余 finding 与新风险裁决

- MiMo `S2-R01`：维持 `rejected`。bindings closure 与 done callback 持有 set，task 并非无引用；application teardown只由完整 composer拥有，不建立第二 lifecycle owner。
- DS `S2-R02`：维持 `not a defect`。diagnostic sink 最外层 `except Exception` 不吞 `BaseException`，避免 background callback 产生 traceback。
- 新 `_EditorTask` union：`accepted as correct`。它只描述显式 outcome task 与 public system editor `Task[None]`，module-private 且 focused pyright 零错误。
- `except BaseException` + bare re-raise：`accepted as necessary owner invariant`。需要覆盖 `asyncio.CancelledError` 并保持原始异常身份；catch 后不消费、不转换，只设置 cleanup 优先级标记并原样重抛。
- nonzero editor + unlink failure：`accepted as documented non-risk`。nonzero 本身仍是 silent cancel；若同一 action 的 sensitive tempfile 无法删除，cleanup 是唯一真实失败并由 composer owner 报告。该双故障不改变普通 nonzero oracle，也不引入 filesystem rollback/竞态需求。
- 两路 re-review 都没有新增 material finding，当前无未分类 S2 residual risk。

## Validation snapshot

- Focused pytest：`104 passed, 3 warnings`；warnings 为既有第三方 deprecation。
- `dayu/cli/composer.py` coverage：`373 statements / 35 missing / 90.62%`（报告取整 91%，达到 `>=80%`）。
- Focused pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- Registry JSON：均可解析且无 diff。
- Registry SHA-256：
  - oracle：`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
  - scenarios：`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- Index：为空。

## Cross-slice release blocker

Full pyright 的两个 `utils/...explicit_config_dir` 错误是 S1 accepted commit 删除 request field 后引入的 cross-slice regression，不是 existing debt，也不属于 S8。它不否定 S2 owner acceptance，但在 S2 commit 后、S3 前必须通过独立 S1 corrective fix/review/re-review/commit gate 收口，且不得恢复兼容字段。

## Accepted slice commit boundary

只允许按显式路径 stage S2 三个 production/test 文件，以及 implementation、首审、首轮总控、fix、双路 re-review 与本裁决共八个 durable artifacts。不得 stage `utils/`、README、design、registry、Host/Service/Engine 或其它文件；commit 后不 push，立即进入 S1 corrective gate。
