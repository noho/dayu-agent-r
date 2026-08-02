# WU-CLI-CONFORMANCE-F01-F07 S4/F04 Implementation 记录（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S4 / F04 — READ_ONLY 保留 REPL，并以 fresh attachment 重试 mutation`
- Gate：`implementation`
- Entry HEAD：`25400fbadcdb2768b3a0d5b9834f2ad727de659f`
- 分支：`codex/interactive-oracle`
- 执行日期：2026-08-02（Asia/Shanghai）
- 状态：`IMPLEMENTATION COMPLETE — next: independently dispatched code review`
- Artifact：`docs/reviews/wu-cli-conformance-f01-f07-s4-implementation-codex.md`

本记录只覆盖 accepted plan `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
§6 的 implementation 与 implementation validation。按用户约束，不执行自我 review、
deepreview、stage、commit、push 或 PR 操作，也不替代后续独立 code-review artifact。

## Preflight、第一性原理判断与语义 owner

Preflight 确认当前分支为 `codex/interactive-oracle`，entry 工作区干净且非 protected
trunk。直接代码证据证明 F04 动机成立：entry 实现收到 composer `SUBMIT` 后，在 Host
acceptance callback 之前立即调用 `composer.accept_submit(record_history=True)`，会先清
draft、写 history、切换 phase；若 Host 随后用 typed READ_ONLY detail 拒绝 mutation，
submit task 异常会冒泡并终止 interactive invocation。同时 invocation 只持有一个裸
attachment，无法表达“下一次 mutation 才先 close 旧 RO，再 fresh attach”。

owner 边界如下：

- Host attachment registry 继续唯一产生并承诺 attachment 的 immutable
  `READ_WRITE | READ_ONLY` truth，以及 typed mutation rejection；CLI 不改 Host
  production，不提升 mode，不从其它 client 退出、EventLog、错误文本或时序推断权限。
- `InteractiveComposer` 继续唯一拥有 draft、cursor 与 history。CLI 只有 Host accepted
  callback 到达后才 ack；READ_ONLY 路径不 ack，因此 composer 自身恢复 exact
  draft/cursor，history 保持不变。
- CLI interactive coordinator 只拥有 pending mutation identity 与 attachment
  close-before-open 编排。相同 draft + input revision 复用 identity；用户编辑才产生新
  turn/client request identity。

Accepted plan 描述 pending mutation “冻结 cursor”；但允许文件内的 public
`InteractiveComposerEvent` 只投影 draft 与 input revision，cursor 明确留在 composer
内部。为遵守唯一语义 owner 与禁止读取私有字段/下游反推，本实现不复制虚构 cursor
字段；通过“不 ack rejected submit”让 composer owner 原样保存 cursor。真实 composer
测试直接证明 cursor 从位置 `2` 恢复，未要求修改 composer contract，因此不构成
blocker。

## 实际 scope

production/test 修改严格限于：

- `dayu/cli/session_execution.py`
- `tests/cli/test_interactive_command.py`
- `tests/host/test_session_attachment_registry.py`

另新增本 implementation artifact。未修改 Host production、composer、Service、Engine、
README、design、registry、oracle/scenario 或其它文件；未 stage、commit、push 或操作 PR。

## 实现 contract

### Attachment controller

`_InteractiveSessionAttachmentController` 持有 invocation 唯一 current attachment、typed
fresh-open/close callbacks 与 `refresh_required`：

```text
普通 mutation                  -> 返回 current，不 open/close
typed READ_ONLY rejection      -> 只登记 refresh_required
下一次 mutation               -> shielded close B1 完成
                              -> fresh attach B2
                              -> B2 mode 仍由 Host 冻结
invocation EOF/error/terminal  -> 幂等 close 当前存活 attachment 一次
```

controller 从不写 `access_mode`，不原地 promotion，不后台 attach/poll；fresh attach 只由
下一次 mutation 触发。测试 timeline 精确为：

```text
open:B1:read_only
-> close-start:B1
-> close-complete:B1
-> open:B2:read_write
-> accepted terminal
-> close-start:B2
-> close-complete:B2
```

### Pending mutation 与 acceptance barrier

`_InteractivePendingMutation` 冻结 normalized prompt、exact raw draft、input revision、turn
index 与 `client_request_id`。TTY submit 改为两阶段：

```text
SUBMIT
-> 创建/复用 pending identity
-> attachment_for_mutation()
-> 发 Host submit，但不 ack composer

Host accepted callback
-> _ActiveTurnCloseout publish exact Run id
-> outer driver ack composer/history exactly once
-> retire pending
-> 进入既有 S3 canonical terminal closeout

typed READ_ONLY
-> 不 publish accepted、不 ack、不清 draft/history、不 exit
-> 打印一次稳定 typed 提示
-> 保留 pending identity
-> 标记下一 mutation refresh
-> Run count 保持 0
```

同一 draft/revision retry 的两次 request id 完全相等；用户把 `draft` 编辑成
`draft edited` 后才从 `turn-1` 迁移到 `turn-2`。既有 queued follow-up 同样在 accepted
callback 后才 ack，并继续复用 S3 `_ActiveTurnCloseout`，没有建立第二套 acceptance/submit
state machine。

### Typed error dispatch

CLI 仅在 `HostApiError.detail` 是 `HostSessionMutationErrorDetail`，且同时满足：

- `kind == "session_mutation_access"`
- `reason is READ_ONLY`
- `actual_mode is READ_ONLY`

时保留 REPL。message 含误导文本但 typed reason 为 `ATTACHMENT_REQUIRED` 的对抗测试仍
原样传播 fatal `HostApiError`；实现不匹配 message 字符串，也不把其它 Host 错误一概
吞掉。

## Owner-level tests

### 真实 Host 双 attachment / 同 label

`tests/host/test_session_attachment_registry.py` 新增最小 public 双 opener case：两个真实
Host 以同一 label `f04-shared-label` 得到同一个 Session；A attachment 为 RW，B 为 RO。
B 使用稳定 request id 提交时得到精确
`session_mutation_access / READ_ONLY / actual_mode=READ_ONLY`，拒绝前后
`host_runs` 与 EventLog row count 都完全不变。A 关闭后 B1 mode 仍是 RO；B1 关闭后 fresh
B2 才取得 RW，复用相同 request id 接受并最终只新增一个 Run，EventLog 才增加。

### CLI 状态与 closeout 矩阵

CLI owner tests 覆盖：

- 真实 `PromptToolkitInteractiveComposer` 在首次 RO 后保留 draft `abc`、cursor `2`、空
  history、运行中的 REPL 与零 accepted Run；fresh RW 后 history/ack 恰好一次。
- B1 close-complete 严格先于 B2 open；B1/B2 与 outer terminal cleanup 各 close 一次。
- fresh B2 仍 RO 时重复稳定提示、相同 request id、零 Run、零 ack，随后 EOF 正常返回
  `0` 并关闭 current。
- RO 后用户编辑产生不同 request id（`turn-1` -> `turn-2`），旧 pending 不进 history，
  最终 accepted Run 恰好一个。
- RO 后 composer 异常原样传播，current attachment 无 leak/double-close。
- accepted terminal 路径只在 Host callback 后 ack，等待 canonical terminal，最终正常 EOF。
- typed reason 对抗证明不使用错误 message 字符串分派。

## 验证结果

### Focused pytest 与单文件 coverage

```bash
source .venv/bin/activate
pytest \
  tests/cli/test_run_keys.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py \
  tests/host/test_session_attachment_registry.py \
  -q \
  --cov=dayu.cli.session_execution \
  --cov-report=term-missing
```

结果：`204 passed, 3 warnings in 11.55s`。warnings 均为 `edgar` 依赖的既有
deprecation warning。`dayu/cli/session_execution.py` 为 `776 statements / 103 missing /
87%`，满足单文件 `>=80%`；未以总平均掩盖目标文件覆盖率。

### Pyright

- focused production/test allowlist：`0 errors, 0 warnings, 0 informations`。
- 全仓 `python -m pyright`：`0 errors, 0 warnings, 0 informations`。

### Integrity、format、allowlist 与 frozen truth

- `git diff --check`：通过。
- `ruff format --check`：三个 Python allowlist 文件均已格式化。
- frozen `docs/cli_ci_oracles.json` SHA-256：
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- frozen `docs/cli_ci_scenarios.json` SHA-256：
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
- `docs/cli_ci.md` SHA-256：
  `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`。
- `docs/host/design.md` SHA-256：
  `7bd4059f7f4c43dcc9e6ab1e7a650c950c9724283d568137c3d98f6e4be127a0`。
- Python working hashes：
  - `dayu/cli/session_execution.py`：
    `7042aeb61b439dbac2518c3780d5a713fe96de84ea2c97f117a03217aa4b73e5`
  - `tests/cli/test_interactive_command.py`：
    `d090b7fbbcc6074d33332878a9d5324ad88b10a322756740ef0fd0ebb155028b`
  - `tests/host/test_session_attachment_registry.py`：
    `0ccbded6ece8ffdf3efa942340859619787b2da3dde04572900b99720d7da066`
- artifact 创建前的 diff allowlist 只有上述三个 Python 文件；index 为空。

## Docs decision

用户明确禁止本 slice 修改 README/design/registry，accepted plan §6.1 也把 README 同步
延迟到 S8。本次没有用户可见 CLI 语法、安装、入口或 Host contract 变化；只按要求新增
本 implementation artifact。README/design/registry 均未修改。

## Residual risk 与未覆盖项

- `MEDIUM / covered by later approved S8 evidence`：真实两个独立 CLI 进程的 owner 退出与
  B 下一次 Enter 的 OS 调度窗口、PTY screen 文本和完整 evidence bundle，留给已批准 S8
  真实并发 CLI evidence 收敛。
- 当前 slice 已用真实双 Host opener、public attachment、durable Run/EventLog count 与
  deterministic CLI close-open barrier 覆盖语义 owner 和关键竞态；没有 Host contract、
  frozen oracle 或 design truth 冲突，没有 implementation blocker。
- 后续独立 code-review findings 尚未产生，本 artifact 不预判或裁决 review finding。

## Completion 与下一入口

S4/F04 implementation、owner tests、focused coverage、focused/full pyright、format、diff、
allowlist 与 frozen hash 检查均完成。工作树保持未 staged；未 commit、push 或操作 PR。
按用户要求在 implementation gate 停止，下一合法入口是独立 code review。
