# WU CLI Interactive 02 / S3 Code Review 裁决

## Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice：S3 / F10
- Base HEAD：`057b5b9b`
- Implementation artifact：`docs/reviews/gateflow-wu-cli-interactive-02-s3-implementation-20260801-192426.md`
- AgentMiMo review：`docs/reviews/code-review-20260801-193115.md`
- AgentDS review：`docs/reviews/code-review-20260801-192742.md`
- Gate decision：`RE_REVIEW_REQUIRED`
- Next gate：S3 双路只读 procedural re-review

## Controller 独立结论

Controller 逐段核对了 classifier、scanner aggregate、public attachment task owner、
new-work lease、actor future、managed attachment close、Host close、positive orphan proof / CAS
以及真实 SIGKILL test。当前生产实现与批准 plan §7 的 owner 和 bounded one-shot 设计一致：

- stale 边界为 `elapsed < stale_after`；仅 `owner_heartbeat_recent` 同源产生
  `heartbeat_at + stale_after`；
- initial RW target scan 激活后至多登记一个 Session-local delayed task；deadline 只做一次
  UTC 到 monotonic delay 换算，唤醒后用 fresh UTC now 提交一次相同 target scan；
- durable mutation 仍只发生在 scanner 的 positive orphan proof + 既有 CAS 内；恢复事件序列与
  new Attempt/execution owner 未下沉到 CLI；
- attachment close 与正常 Host close 都在释放 attachment/停止 actor 前取消并 join task；已提交
  actor future 与 new-work lease 绑定，不由 caller 重发文本或修补 SQLite；
- 当前 diff 未发现 scope expansion、secret 泄漏或 formatting-only churn。

上述代码结论尚不能直接把本 gate 标为通过，因为两名 reviewer 都在 review 期间擅自执行了
`git stash` / `git stash pop`。用户明确禁止擅自 stash，且 review 任务要求只读生产工作树。
Controller 已在两次操作后重新核验：8 个 modified 文件的 stat 仍为 `+1349/-7`，普通 diff
与 `-w` diff stat 相同，index 为空，`git diff --check` 通过，stash 列表只剩 review 前既有的
其它分支 stash；没有观察到净内容丢失。但过程违规使本轮不能作为最终 clean review 证据，必须
从 `/clear` 后补做双路只读复审。

## Findings 裁决

| Finding | 来源 | 裁决 | 依据与处置 |
|---|---|---|---|
| S3-MIMO-000：未发现实质代码问题 | MiMo | `accepted-as-review-observation` | 静态 owner、CAS、close ordering 与测试证据可复核；但受 process violation 影响，不能单独关闭 gate。 |
| S3-DS-001：一次 watchdog exact-count 失败由 S3 monkeypatch 污染导致 | DS | `rejected-as-causal-finding / retained-as-validation-observation` | 直接证据只证明一次 `token_threads` 重复和后续同命令通过；没有定位哪个 task、fixture 或 monkeypatch 越过 teardown。`sys.modules` 取 module 后使用 pytest `monkeypatch.setattr` 是自动回滚的常规写法，不能据此推出污染。Controller 随后完整运行六个允许测试文件得到 `116 passed in 35.10s`。本项不授权猜测式测试改写；clean re-review 必须再次运行同一套件并记录是否复现。若复现，需先给出 leak/task 的直接证据再接受修复。 |
| S3-DS-002：`_close_task` 在未来多 event-loop 共享时可能竞态 | DS | `rejected-non-goal` | 当前 attachment 属于单一 opener event loop；检查与 `create_task` 之间没有 `await`，在现有 asyncio contract 下无竞态。为未设计的跨 event-loop 共享增加锁会扩大范围。 |
| S3-PROC-001：reviewer 临时 stash 工作树 | Controller | `accepted-process-finding` | 两路均违反用户和 review 只读约束。无需修改产品代码；处置是 `/clear` 后双路重新 discovery、同时执行只读 deepreview，禁止任何 stash/index/worktree mutation。 |

## Validation

- Controller net-state：8 个 production/test modified 文件，`+1349/-7`；无 staged change；
  `git diff --check` 通过；仅有 review/implementation artifacts 未跟踪。
- Controller affected suite：
  `tests/host/test_recovery_orphan_classifier.py`、`test_recovery_scan.py`、
  `test_recovery_multiprocess.py`、`test_public_session_attachment.py`、
  `test_open_host_runtime.py`、`test_session_attachment_registry.py`：
  `116 passed in 35.10s`。
- 两路已分别观察真实 POSIX SIGKILL smoke 通过；implementation 记录为
  `1 passed in 30.73s`，DS 记录为 `1 passed in 30.78s`。
- 全仓 pyright 由 implementation 与两路 review 分别得到 `0 errors`。

## Residual risks

- 一次 watchdog exact-count 失败尚无可复核 root cause，分类为 validation observation，
  不是已接受代码 finding。clean re-review 若再现，gate 必须继续保持未通过并定位 owner；若不
  再现，仍在最终 S3 artifact 如实保留单次观察，不伪装为从未发生。
- delayed rescan 按批准设计是 one-shot；第二次 scan 再得到 recent heartbeat 不形成 polling。
  这是批准的 bounded invariant，不在 S3 扩成后台 supervisor。
- Windows SIGKILL 不在本 slice 的批准验证范围；POSIX smoke 是 F10 的正式高风险证据。

## Next gate

重新 discovery 两个 reviewer pane，分别 `/clear`，再次 discovery 确认实际 CLI 后，同时发送
`/deepreview --base HEAD`。两路只能执行只读检查、测试与各自新建 artifact；不得 stash、修改
production/tests/index 或改写已有 artifact。Controller 读取两份新 artifact 后重新裁决；除非
出现 accepted finding，否则不派发 AgentCodex 猜测式修复。
