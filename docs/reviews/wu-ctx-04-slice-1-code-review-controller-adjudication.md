# WU-CTX-04 Slice 1 code review controller adjudication

## Gate metadata

- work unit：`WU-CTX-04`
- gate：implementation Slice 1 首轮 code review adjudication
- accepted plan commit：`1f032b5e2d1aba974304ee4537be76ed4a1174e6`
- implementation artifact：`docs/reviews/wu-ctx-04-slice-1-implementation-codex.md`
- AgentMiMo review：`docs/reviews/code-review-20260722-124340.md`
- AgentDS review：`docs/reviews/code-review-20260722-124418.md`
- controller independent verification：focused pytest `43 passed`；全量 pyright `0 errors`
- decision：`needs-fix`
- blocking open questions：None

## Finding adjudication

### CR-MIMO-001 — rejected-with-reason

AgentMiMo 认为 Windows nonblocking contention 的真实 errno 是 `EDEADLK`，因而
测试 fake 使用 `EACCES` 不代表真实路径。该前提不成立。Microsoft `_locking`
文档把“file already locked or unlocked”的 locking violation 明确定义为
`EACCES`；`EDEADLOCK` 只对应阻塞 `_LK_LOCK` / `_LK_RLCK` 在十次重试后仍失败。
当前实现使用 `_LK_NBLCK`，所以 `tests/runtime/test_native_mutex.py` 的 `EACCES`
fake 正确覆盖主要真实 contention 路径。生产白名单额外接受 `EDEADLK` 仍是保守的
contention closed set，不构成本 Slice defect。

证据：

- `dayu/runtime/native_mutex.py:278-279` 使用 `LK_NBLCK`。
- `dayu/runtime/native_mutex.py:298` 同时接受 `EACCES` / `EDEADLK`。
- Microsoft `_locking` reference：
  <https://learn.microsoft.com/en-us/previous-versions/8054ew2f%28v%3Dvs.140%29>。

### CR-MIMO-002 — rejected-with-reason

finding 自身已经确认行为正确、幂等且开销可忽略，并未给出可静态证明的性能问题。
此外第一次 release 后成功 record 已从 `_records` 删除，后续重试只遍历仍 fail-closed
的 record，并非重复处理全部原始 record。增加额外状态只会扩大状态机，不是当前必要修复。

### CR-MIMO-OQ-001 — rejected-with-reason

RECOVERING 允许多个 recovery work lease 是计数式 drain contract 的有意能力；target
recovery 可以包含多个真实 Future/task，只有全部底层工作收口后
`new_work_lease_count == 0` 才能 activate。该行为与 accepted plan 的 work lease
计数和“target recovery work 已收口”一致，不需要把 recovery 人为限制成单 Future。

### CR-DS-001 — accepted（severity 调整为低）

直接证据成立：native prepare/lock 已失败且 partial `os.close` 再失败时，当前外层
`StrictNativeMutexUnavailableError` 以 close 异常为 cause，只把 prior error 的类名写入
note；原始错误 message 与 traceback 不可达。安全语义仍然 fail closed，所以不评为中等
correctness defect，但生产诊断信息确实不完整。

修复要求：

1. 保持外层异常类型仍为 `StrictNativeMutexUnavailableError`，不得改变 busy / unavailable
   contract。
2. 当 prior native error 与 partial close error 同时存在时，异常 cause 必须结构化保留
   两个原始异常及 traceback；不得只拼接字符串或只保留类型名。
3. 新增精确单测同时触发 native lock failure 与 partial FD close failure，断言两个原始
   exception 都可从异常链访问；同时保持普通 busy + close failure fail closed。
4. 复跑 Slice 1 focused pytest、targeted pyright、coverage、ruff 与 whitespace audit。

### CR-DS-002 — rejected-with-reason

`release_host_close` 的资源安全 owner 已保证所有 record 都执行 cleanup，首个错误作为
稳定 typed failure 返回；其余失败仍缓存于各自 CLOSING record，不会被误标成功或删除。
review 没有证明 caller contract 要求聚合多个 release 错误，也没有证明当前行为会隐藏
成功、提前解锁或破坏重试。引入 `ExceptionGroup` 到 Host close API 会扩大错误契约，当前
不做。

### CR-DS-003 — rejected-with-reason

当 `_host_closing=True` 时，关闭的是整个 Host attachment registry gate，而不只是某个
已有 record。此时对 never-attached Session 返回 `ATTACHMENT_REQUIRED` 会暗示 caller
可以先 attach，但 `begin_attachment` 已必然返回 `HostClosedError`；
`ATTACHMENT_CLOSING` 更准确表达当前全局不可受理状态。Slice 2 public mutation 还会同时
经过 Host health admission，因此不存在等待某个虚构 attachment 的生产路径。

## Residual risk adjudication

- 真实 Windows 环境验证：保留，owner=`Slice 3 final matrix / CI`。
- `dayu/host/api.py` 全文件 coverage：按 accepted plan 保留到 Slice 3；本 Slice 新增分支已执行。
- `_release_record` cached close error：属于有意 fail-closed；raw descriptor 已被消费，禁止
  不安全重试。Slice 2/3 需在 Host close failure matrix 继续覆盖。
- `"\t"` / `"\n"` Session id：`str.strip()` 与已测纯空格走同一直接分支，不构成独立风险。
- MIMO-003：本轮仅依据实际 diff 复核；未发现测试为实现便利弱化 contract 的证据，关闭。

## Next gate

由 AgentCodex 仅修复 `CR-DS-001` 并补测试/implementation-fix artifact；随后 AgentMiMo 与
AgentDS 对 accepted finding 做独立 re-review。不得进入 Slice 2。
