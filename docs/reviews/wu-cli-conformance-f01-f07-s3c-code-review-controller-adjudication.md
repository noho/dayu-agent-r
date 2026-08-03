# WU CLI Conformance F01-F07 — S3C Code Review Controller Adjudication

## Gate conclusion

- Gate: S3C corrective slice code review
- PR: PR 190
- MiMo verdict: `PASS`
- DeepSeek verdict: `PASS`
- Controller verdict: `ACCEPTED-S3C-CODE-REVIEW`

本裁决独立核对两份 durable review、production diff、owner tests 与 S3C implementation
artifact；结论不是以“两路一致”代替证据。S3C 的三项 frozen F03 偏差均已在 CLI
input/composer 与 interactive driver owner boundary 收口，没有发现需要进入 fix loop 的
correctness、stability 或 semantic ownership finding。

## Finding-by-finding adjudication

### MiMo

MiMo 未提出 finding。总控复核其逐项证据后接受 `PASS`：

- Enter chord 在 composer 同步建立 `SUBMITTING` typed fact；pending document 与第二个
  PromptToolkit application 的 editable draft 分离，0/10/20ms standalone Escape 不再落入
  input-owner gap。
- `Escape + Any` 与 exact standalone Escape 判定共享唯一 ambiguity timeout；Alt+X、CSI、
  Home、Delete、bracketed paste 的完整 sequence 不产生 cancel。
- durable SIGINT count 在 active turn 与 terminal projection 后、`current` 清空前均被消费；
  `_ActiveTurnCloseout` 只创建一个 graceful cancel task，第二次 SIGINT 只升级 exit intent。

### DS-01 — handoff flush task 在 application 快速退出时被取消

- Reviewer severity: low
- Controller disposition: `REJECT-AS-NON-FINDING`
- Evidence: `_flush_submit_handoff_input` 的职责只是在第二个 live application 中解析仍处于
  ambiguity 的 ESC prefix。若该 application 已因另一个完整 typed event 退出，当前 event 已经
  确定，旧 application 的 provisional prefix 不再能合法改写该 event；`application.is_done`
  guard 与 PromptToolkit 的 background-task teardown 因而是正确生命周期边界。
- Action: 无 production change；不得在已退出 application 上补做 flush。

### DS-02 — rejection restore 被调用两次

- Reviewer severity: low
- Controller disposition: `REJECT-AS-NON-FINDING`
- Evidence: 两次写入来自两个不同 owner transition：`reject_submit_delivery()` 立即结束 delivery
  intent 并恢复 editable state；下一次 `read_event()` 终结 pending snapshot 生命周期。snapshot
  是 frozen value，重复恢复幂等，且 owner test 已断言 draft/cursor/revision/history 不漂移。
- Action: 无 production change；为消除一条幂等赋值而削弱 rejection postcondition 不成立。

### DS-03 — closeout 后 `active_sigint_count` 归零

- Reviewer severity: low
- Controller disposition: `REJECT-AS-NON-FINDING`
- Evidence: reconciliation 先把所有 durable increment 投影到同一个 completed turn 并单调升级
  `_ActiveTurnCloseout.intent`；随后 `current = None`，per-turn counter 必须归零。exit truth 已由
  closeout intent / `exit_after_closeout` 持有，不依赖归零后的计数。
- Action: 无 production change。

## Independent adversarial checks

### SIGINT count snapshot

`pending_interrupts = monitor.count - observed` 与紧随其后的 observed 更新之间没有 `await`。
POSIX asyncio handler 通过 event-loop callback 调用 `notify`；同步 fallback 也只用
`call_soon_threadsafe` 投递同一 loop。因此 production contract 下两个读取之间不存在 callback
interleaving。随后任何新 signal 会留下更大的 durable count，并由下一轮或 closeout
reconciliation 消费。这里不是 TOCTOU correctness finding；把一次读取保存为局部变量可以提升
可读性，但没有足够动机扩大本 slice。

### Pending mutation / READ_ONLY

READ_ONLY rejection 先取消 live handoff composer task，再调用 typed rejection transition；原提交
snapshot、draft、cursor 与稳定 `client_request_id` 仍由既有 F04 owner contract 持有。S3C 没有
引入 attachment promotion 或第二个 Run。

### Sequence semantics

Alt+X 的用户批准语义是：存在 continuation 时先完成 ESC-prefixed sequence resolution；只有歧义
期后没有 continuation 才按 standalone Escape。当前实现与测试覆盖同 chunk、跨 chunk、CSI、
Home、Delete 和 bracketed paste，符合该裁决。

## Validation accepted at this gate

- Focused owner/integration tests: `217 passed`
- Owner coverage: composer 89%，run_keys 93%，session_execution 85%
- Full pyright: `0 errors, 0 warnings, 0 informations`
- Changed-file Ruff: `PASS`
- `git diff --check`: `PASS`
- Frozen oracle/scenario/docs hashes: unchanged

## Residuals and next gate

- 新 target 的 full-real F01-F07 immutable evidence 尚未重跑；这是下一 S8 evidence refresh 的
  required work，不是 S3C code finding。
- resolved Authorization durable persistence 仍是独立 work unit 的 assigned residual，不在
  F01-F07 scope。

Gate marker: `ACCEPTED-S3C-CODE-REVIEW`
