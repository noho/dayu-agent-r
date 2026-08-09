# WU-CLI-CONFORMANCE-F01-F07 S2/F02 Code-review Fix 记录（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S2 / F02 — external editor`
- Gate：`code-review fix`
- Base/HEAD：`a41526ecbf5c1d16c24a19114b0d0e21208d1dd0`
- Controller adjudication：
  `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-controller-adjudication.md`
- 状态：`FIX COMPLETE — next: S2 dual re-review`
- Artifact：`docs/reviews/wu-cli-conformance-f01-f07-s2-fix-codex.md`

## Scope 与 owner 决策

本 fix 只关闭总控 accepted `S2-C01`–`S2-C04`。错误身份、草稿/cursor snapshot、
`EDITOR_PENDING` 与 task lifecycle 的唯一 owner 均为 `dayu.cli.composer`，因此生产
修复只落在 `dayu/cli/composer.py`，owner tests 只落在
`tests/cli/test_interactive_composer.py`。既有 integration contract 没有变化，未修改
`tests/cli/test_interactive_command.py` 的 fix 内容。

实际 fix gate changed files：

- `dayu/cli/composer.py`
- `tests/cli/test_interactive_composer.py`
- `docs/reviews/wu-cli-conformance-f01-f07-s2-implementation-codex.md`
- `docs/reviews/wu-cli-conformance-f01-f07-s2-fix-codex.md`

未修改 `utils/`、registry、README、design、Host、Service、Engine、依赖或其它产品
文件；未 stage、commit、push 或操作 PR。

## Accepted findings 与修复

### S2-C01 — primary exception ownership

状态：`已修复`。

`_run_explicit_editor_round_trip` 使用单一 `primary_failure` 控制流状态。round trip
body 的任何在途 `BaseException` 都先标记为 primary 再原样重抛；`finally` 无论成功、
失败或取消仍尝试一次 `temporary_path.unlink(missing_ok=True)`。unlink 的 `OSError`
只有在不存在 primary 时才形成既有 `CLEANUP_FAILED`；否则不得覆盖 typed tempfile、
`SPAWN_FAILED`、`READBACK_FAILED`、`CancelledError` 或未知 primary identity。

该修复没有增加 cleanup retry、rollback、临时文件恢复、路径暴露、额外 diagnostic
或新 filesystem 产品语义。

Owner tests 参数化覆盖 spawn/readback primary + cleanup 双故障，并额外覆盖
`CancelledError` + cleanup 双故障；均断言 cleanup 被尝试且 primary identity 保留。

### S2-C02 — synchronous public Document snapshot

状态：`已修复`。

同步 `_open_explicit_editor` 在 `asyncio.create_task(...)` 前冻结完整 public
`buffer.document`，并把它作为必填 `original_document: Document` 参数显式传给
`_run_explicit_editor_round_trip`。async body 不再读取 original buffer state，消除了
按键 handler 返回到 task 首调度之间的竞态。

Owner test 在 task 创建后、首次调度前替换 buffer document，并断言 round trip 收到
的仍是原始 text + cursor snapshot。

### S2-C03 — one EDITOR_PENDING per composer

状态：`已修复`。

复用现有 editor task set 作为唯一 pending 真源，不新增状态枚举、flag 或第二状态机。
handler 入口在 set 非空时直接 no-op；显式 `_EditorProcessOutcome` task 与 unset public
`Buffer.open_in_editor(...)` task 都进入同一 typed set，done callback 或 composer
teardown 负责消费并释放 slot。因此每个 composer 的集合大小保持 `0..1`。

Owner test 在第一个 round trip 被 barrier 阻塞时同步重复触发快捷键，断言只有一个
round trip task、一次 public `run_in_terminal`、一个 process call 和一次 public
`Buffer.document` write。

### S2-C04 — strict updated text type

状态：`已修复`。

`updated_text` 使用严格 `str` 局部类型；所有能离开 `try/finally` 的成功路径都已完成
UTF-8 readback，nonzero 提前返回，失败路径抛出 typed error。删除不可达
`updated_text is None` 与对应 `RuntimeError`，没有兼容分支或默认值。

## Validation

### Focused pytest 与 composer coverage

```bash
source .venv/bin/activate
pytest tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py \
  --cov=dayu.cli.composer --cov-report=term-missing --cov-fail-under=80 -q
```

结果：`104 passed, 3 warnings in 8.05s`。三条 warning 均来自 `edgar` 依赖的既有
deprecation warning。`dayu/cli/composer.py` 为 `373 statements / 35 missing / 91%`
（精确 total `90.62%`），满足单文件 `>=80%`。

### Focused pyright

```bash
source .venv/bin/activate
python -m pyright dayu/cli/composer.py \
  tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### Full pyright cross-slice 分类

额外执行 `python -m pyright`，结果仅有：

- `utils/smoke_cli_init_provider_matrix.py:2386`：不存在参数
  `explicit_config_dir`；
- `utils/smoke_host_public_awaiting_entrypoint.py:808`：同一错误。

直接比较 S1 accepted commit `a41526ec` 及其 parent：parent 的 request type 仍声明
该字段，S1 删除字段，同时没有修改两个 `utils` call site。因此两错是 **S1 引入的
cross-slice regression**，不是 existing debt，也不归 S8。按总控裁决，本 S2 fix
不修改 `utils/`；S2 accepted 后、S3 前由独立 S1 corrective gate 收口，并以 full
pyright 零错误为 acceptance signal。

### Diff、registry 与 index

- `git diff --check`：通过。
- `docs/cli_ci_oracles.json`：JSON 解析通过；SHA-256
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- `docs/cli_ci_scenarios.json`：JSON 解析通过；SHA-256
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
- `git diff --cached --name-only`：无输出，index 为空。

## Docs decision

本 fix 没有新增测试层级、用户入口、分层关系、依赖或最终用户工作流；
`tests/README.md` 已覆盖 interactive composer/editor owner test 边界。按本 gate
allowlist 不修改 README、design、registry 或 `docs/cli_ci.md`。Implementation artifact
只追加 fix 记录并纠正 full pyright 分类。

## Residual risks 与未覆盖项

- `fixed in current slice`：`S2-C01`–`S2-C04` 的 owner contract 与组合故障测试。
- `covered by later approved slice S8`：真实 PTY 下不同 editor 的 terminal
  suspend/resume 与最终 immutable CLI evidence bundle。
- `assigned to S1 corrective gate before S3`：两处 `utils` 旧 keyword 与 full pyright
  closure；明确不属于 S2 或 S8。
- Windows text-mode newline：`out of scope`；当前 frozen F02/PTY contract 为 POSIX，
  本 fix 不扩张平台 filesystem 语义。

没有未分类 residual risk，没有 blocking open question。

## Completion 与下一入口

`S2-C01`–`S2-C04` fix complete；所有 accepted finding 当前状态均为`已修复`。
代码、测试与 artifacts 均未 stage。按用户指令本 gate 完成后停止，不执行 commit、
push 或 PR 操作。下一合法入口为 **S2 dual re-review**；MiMo/DS 应分别产出 durable
re-review artifact，再由总控逐项裁决关闭 findings。
