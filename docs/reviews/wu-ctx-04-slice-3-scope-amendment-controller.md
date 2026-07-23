# WU-CTX-04 Slice 3 Scope Amendment（Controller）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`3/3`
- baseline：accepted Slice 2 commit `4ca0810b27eded188e4f9aae54756a871eb371ed`
- source blocker：`docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`
- decision：`resume-with-narrow-test-only-amendment`
- design/public contract/schema/state machine change：None
- blocking open questions：None

## First-principles judgment

blocker成立，但不需要用户重新裁决架构。accepted plan已经明确要求
`ActiveCancelMessage.session_id`、registry exact execution identity、target-scoped caller wake
以及删除workspace-wide periodic watchdog/query。遗漏的是这些required signature/behavior的
现有测试消费者，而不是目标、owner或state machine不明确。

给production字段默认值、从`run_id`猜Session、保留无target overload、兼容wrapper或旧全局
watchdog入口都会制造第二语义owner并违反项目“无兼容逻辑”约束。因此正确处理是把直接baseline
消费者加入Slice 3 tests allowlist，做严格契约迁移；不得为了保持旧测试向production回填fallback。

## Direct baseline evidence

### 1. `tests/host/test_dispatch_scheduler.py`

该文件不在原Slice 3 allowlist，但直接消费必须改变的契约：

- `ActiveWorkerRegistry.register(...)` 无`session_id`调用：baseline lines
  `1233`、`2587`、`3140`、`4282`。
- `ActiveCancelMessage(...)` 无`session_id`构造：baseline lines
  `4146`、`4305`、`4403`、`4572`、`4741`。
- workspace-wide `tick_active_cancel_watchdog(...)` override：baseline lines
  `2253`、`2286`。
- 无target `wake_active_cancel_watchdog()` direct calls：baseline lines
  `3227`、`3265-3267`、`3295`、`3302`、`5550`。

这些不是可忽略的测试文本：required constructor/signature修改后full pyright/pytest会直接失败；
其中global watchdog tests还固化了Slice 3明确删除的旧行为。

### 2. `tests/host/test_admission_multiprocess.py`

`_RecordingAdmissionWakeupPort`额外保留无target
`wake_active_cancel_watchdog(self)`、`watchdog_wake_count`与零调用断言。虽然
`AdmissionWakeupPort`本身不要求该方法，但这套测试fake仍表达待删除的workspace-wide wake
shape。应机械迁移为target session记录（若该fake仍需表达负向断言），或删除不属于admission
contract的死接口；不得要求production保留无target入口。

Controller全仓核对后，未发现其它allowlist外的`ActiveCancelMessage(...)`或
`ActiveWorkerRegistry.register(...)`直接构造消费者。`test_terminal_post_commit.py`只冻结现有
private target tick qualified-name；只要implementation继续使用同一target helper，无需amendment。

## Amendment

在原Slice 3 allowed tests追加：

- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_admission_multiprocess.py`

允许的修改仅限：

1. 必填`session_id`/exact identity constructor与register调用迁移。
2. 无target workspace-wide tick/wake override/direct-call测试迁移到已接受的target-scoped或
   execution-owner reconcile contract；重复语义测试优先复用`test_active_cancel_dispatch.py`
   的owner矩阵，不在大文件复制第二套状态机。
3. `test_admission_multiprocess.py`中obsolete extra wake fake做机械target-shape迁移或删除，保持
   admission既有业务断言不变。
4. 因production owner变更必然失效的qualified-name/signature断言同步；不得修改与cancel owner
   无关的测试行为。

## Explicitly forbidden

- 不新增任何production/config/doc文件。
- 不改变design、public API、durable schema/table/index、Slice 3 exact state machine或non-goals。
- 不以测试便利增加production default、optional `session_id`、overload、alias、wrapper、loose
  parsing或global compatibility path。
- 不把`test_dispatch_scheduler.py`变成第二个cancel semantic owner；新strict bad-link、terminal
  status与cross-opener行为仍应落在原accepted owner tests。

## Gate decision

`resume-with-narrow-test-only-amendment`。AgentCodex可从原blocked artifact继续Slice 3实现，
并在同一`docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`中保留blocker/amendment历史、
最终改写status与完整验证结果；不得另建第二个implementation artifact。
