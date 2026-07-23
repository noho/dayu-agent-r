# WU-CTX-04 Aggregate Deepreview Controller 裁决

## Gate metadata

- work unit：`WU-CTX-04`
- base：`974f9e1686f6e26f96830cd3478edc9d0d686c45`
- accepted tip：`24dfcf37`
- AgentMiMo：`docs/reviews/wu-ctx-04-aggregate-deepreview-mimo.md`
- AgentDS：`docs/reviews/wu-ctx-04-aggregate-deepreview-ds.md`
- Controller decision：`pass`
- accepted findings：0
- rejected findings：9 个 reviewer finding 编号，去重后 7 个语义观察
- deferred findings：0
- needs-more-evidence：0
- blocking questions：None

## Outcome

WU-CTX-04 aggregate deepreview 通过。两路 reviewer 均确认 attachment ownership、native
mutex、proactive single-operation/recovery、scheduler close barrier、target-only
cancel/watchdog、canonical reason、terminal producer、SQLite batching、public contract、
LLM-facing 与 README 一致性无 blocking failure。

两路列出的 finding 都不成立为当前 actionable defect：部分是已由 Slice 1 明确裁决的
fail-closed contract，部分反例前提在当前 typed/private 调用图中不可达，部分把正确的 Future
完成语义描述成提前释放，另有纯未来调用方假设。Controller 不按数量接受 finding，也不为没有
当前 failure path 的防御性建议扩大 runtime policy 或 public close contract。

## Finding adjudication

### MIMO-F01 / DS-F03 — rejected-with-direct-contract-evidence

两项都要求 native mutex release 失败后删除 attachment record 并让
`_host_close_released` 置位。该改法与已接受的 strict fail-closed contract 冲突。

- `StrictNativeMutexHandle.close()` 在 unlock/descriptor close 结果不确定时消费 fd，并缓存同一
  typed unavailable error；禁止对可能已复用的 fd 做重试。
- registry 保留 errored CLOSING record，使重复 `release_host_close()` 稳定重抛同一错误，Host
  不会在 mandatory mutex release 未被证明成功时宣称 close complete。
- Slice 1 已在 `wu-ctx-04-slice-1-code-review-controller-adjudication.md` 驳回同一
  `CR-MIMO-002`，`wu-ctx-04-slice-1-review-fix-codex.md` 与最终 acceptance 明确记录
  cached close error 是有意 fail-closed 行为。

删除 record 会让后续调用把失败资源误标为已释放，破坏语义 owner；没有修复。

### MIMO-F03 / DS-F01 — rejected-no-current-failure-and-unsafe-remedy

两项要求 `drain_host_close()` 自带 timeout，甚至在 timeout 后强制设置 drain event。没有 reviewer
给出当前任一 mutation/new-work lease producer 泄漏计数或工作已完成但 event 未置位的直接路径。
现有 contract 正是等待已接受 work 的真实 Future/task 收口后才允许 scheduler quiesce 与 mutex
release；强制 drain 会在 work 尚活跃时释放唯一 execution ownership，制造本 WU 要消除的并发。

超时的 owner、时长、诊断与超时后行为均未设计。若未来产品要求有界 shutdown，应作为独立 Host
shutdown policy 工作进入 goal confirmation；当前不是 correctness fix，也不形成 deferred
implementation obligation。

### MIMO-F02 — rejected-pre-existing-and-semantically-distinct

`_cancelled_eof_candidate()` 的 `"host_cancelled"` fallback 由 baseline commit `914a698d7`
引入，不是 WU-CTX-04 变更。它产生 Engine cancel-EOF observation 的诊断 reason，不是
`CANCEL_REQUESTED.reason` 的 durable/cross-opener 替代真源；当前参数是具体
`_HostCancellationToken`，其 `is_cancelled()` 与 `cancel_reason()` 由同一 `_reason` 字段及
同一锁派生，因此当前调用前提下 fallback 不可达。CTRL-S3-002 未回归。

### MIMO-F04 — rejected-correct-completion-semantics

`release_when_done()` 接收的 Future 若已经完成，`add_done_callback` 立即安排/执行 callback 并
释放 lease，正是“work 已完成后释放”的 contract，不是提前释放。当前 production callers 也都
绑定真实 submitted Future/task。建议增加 `future.done()` 后直接 `release()` 只会重述同一语义，
没有修复任何 failure。

### DS-F02 — rejected-invalid-safety-impact

Windows `_lock_file_descriptor()` 把 `lseek` 与 `msvcrt.locking` 放在同一 `try` 内不会绕过 mutex
取得 RW：即使假设 private-owned fd 被外部破坏且 `lseek` 产生 `EACCES`，返回 `False` 只会让
Host attachment 获得 `READ_ONLY`，仍是保守拒绝 new work。正常 fd 的 byte preparation 已在
独立 `_prepare_windows_lock_file()` fail-closed；reviewer 没有提供受支持调用图中的真实误分类
路径。

### DS-F04 — rejected-invalid-cancellation-path

`_close_attachment()` 使用 `asyncio.shield(record.close_task)`；caller waiter 被取消不会取消共享
cleanup task，已有 `test_cancelled_recovering_allocation_close_does_not_cancel_cleanup` 直接证明
再次 close 可 join 同一 task。reviewer 假设 event-loop shutdown 直接取消 private task；该场景下
同一 loop 不再承诺继续服务重试，process exit 由 OS 释放 native mutex，Host close 路径又直接
调用 `_release_record()`，不存在当前 public retry failure。

### DS-F05 — rejected-future-hypothesis

`_acquire_lease()` 是模块私有 helper；三个当前调用点均先校验 exact record identity、host gate、
lifecycle state 与 RW access。以“未来调用方可能绕过”为前提不能证明当前 bug。把所有 caller
policy 复制进 helper 还会把不同 mutation/new-work/recovery state contract 过度耦合到一个通用
计数 primitive。

## Observation adjudication

- DS 关于 `compact_pipeline.py` tier 2 缺直接测试的观察证据失效：
  `tests/host/test_compact_pipeline.py::test_tier_recovery_request_plans_are_ordered_and_bounded`
  直接断言 tier 2 `segment_selection == tier_1.segment_selection` 且不等于 root selection。
- NFS mutex、Windows 实机验证、provider physical exactly-once、poll cadence、定制 SQLite
  `<999` variable limit 与 artifact orphan GC 都是既有支持/外部/retention 边界，已有 owner 或
  后续 work unit，不阻塞本 WU。
- fresh schema 对旧 persisted proactive payload fail-closed 符合用户明确的全新 schema 起库约束。

## Aggregate closure evidence

- accepted plan commit：`1f032b5e`
- accepted Slice 1：`eda1d70e`
- accepted Slice 2：`4ca0810b`
- accepted Slice 3：`24dfcf37`
- AgentMiMo aggregate verdict：`PASS`
- AgentDS aggregate verdict：`pass`
- canonical full suite：`5593 passed, 11 skipped, 6 deselected`
- full pyright：`0 errors, 0 warnings, 0 informations`
- 21 个 modified production Python 文件逐文件 coverage：全部 `>=80%`
- blocking questions：None

## Final decision

`pass`。不进入 aggregate review fix；WU-CTX-04 可进入 draft PR readiness。所有 reviewer
findings 已逐项裁决，没有未分类风险或未解决 blocking question。不得据此自动 merge、ready PR、
请求 reviewer、评论/关闭 Issue。
