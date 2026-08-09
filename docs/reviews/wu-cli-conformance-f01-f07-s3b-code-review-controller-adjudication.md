# S3B Real-evidence Regression 双路 Code Review 总控裁决

## Gate 与证据边界

- **Gate:** S3B implementation slice code review
- **实现基线:** `eae09be97963382c49fbf71195820637a4baa948`
- **审查对象:** S3B working-tree implementation、owner tests 与实现档案；四份 S8 README 和 S8 首轮失败观察档案不属于本 gate。
- **独立审查档案:** `wu-cli-conformance-f01-f07-s3b-code-review-mimo.md`、`wu-cli-conformance-f01-f07-s3b-code-review-ds.md`
- **裁决原则:** 逐项依据 frozen F03/F04 oracle、直接代码路径和 owner boundary 裁决；双路意见相同或不同都不替代证据。

## Finding 逐项裁决

| 来源 | Finding | 裁决 | 证据与后续动作 |
|---|---|---|---|
| Mimo | READ_ONLY rejection 后 `_pending_submit_intent` 残留，后续 SIGINT 可错误绑定下一次 Run | **接受，中** | `_record_submit_intent` 在 Enter chord 同步置位；READ_ONLY rejection 结束本次 submit delivery，但现有分支没有结束该 intent。`has_pending_submit_intent()` 随后仍为真，确会改变 idle/next-turn SIGINT 的归属。修复必须位于 composer owner：新增 typed 方法，只结束 pending-delivery intent，不清空 draft/cursor/revision，也不调用会清空 draft 的 `accept_submit`；READ_ONLY rejection 分支调用它并补 owner/integration tests。 |
| DS | `TCSANOW` 到 reader thread 启动间依赖 kernel input queue，极端超过 queue 容量可能丢字节 | **拒绝为 finding** | `TCSANOW` 的目的就是不丢弃已排队输入；线程启动后读取同一 kernel queue。审查描述的唯一失败条件是启动窗口内输入超过 OS 有限缓冲区，既无当前可复现缺陷，也超出 frozen oracle 的单 chord/完整 sequence 边界。不能用不可实现的“无限输入绝不丢”扩张产品 contract。 |
| DS | terminal 已观察到而 `current = None` 前可能创建孤儿 cancel task | **拒绝为 finding** | 主循环的 `done` 是本轮 `asyncio.wait` 的固定快照；terminal 分支被同步处理到 `current = None`，此段无 `await`，新的 SIGINT task 不会插入该同步区间。即使旧快照同时含 terminal 与 SIGINT，SIGINT 分支先处理，属于 terminal 尚未被本控制流消费时的同轮输入，closeout 的 canonical-terminal guard 又保证不发第二个 terminal。所述“相邻 Python 语句间调度”不可达，且审查也确认无 Host 可见副作用。 |
| DS | `sigint_monitor.close()` 未 shield，随后扩展为 display close 未 shield | **不属于 S3B blocker；登记独立 cleanup residual** | signal close 是同步且无 await，不会在内部被 asyncio cancellation 打断；display close 是 S3B 前已有的相邻 cleanup 设计，审查未给出 F03/F04 真实失败或本 slice 引入的扩散。不得借本修复扩张为 cleanup refactor。后续 owner：CLI runtime display lifecycle。 |
| DS | 纯空白 draft 不算 pending submit intent | **拒绝为 finding** | 空白不会创建 Run，按 idle SIGINT 语义处理是 frozen contract 的正确结果；审查正文也确认行为正确。 |
| DS | reader join 超时后可能短暂访问已恢复 terminal | **拒绝为 finding** | stop flag 在每次 `select` 返回后、`os.read` 前再次检查；审查没有可观察状态污染、资源泄漏或 oracle 偏差，且该结构不是 S3B 新增。 |
| DS | pending count drain 后新 SIGINT 可在下一轮再次 drain | **拒绝为 finding** | 这是两个不同时刻的新信号，不是同一信号的重复消费。第一个请求 cancel，第二个表达 exit intent；closeout owner 的幂等状态机正是 frozen double-Ctrl+C 语义。 |

## Open question 与 residual 裁决

- `TCSANOW` 恢复保留未消费输入：属于正确的终端队列保留语义，不修改。
- `CliSigintMonitor.install()` 的跨 event-loop 重用：当前对象生命周期严格限定于一次 command invocation、同一 loop；不创建兼容性或未来调用者防御分支。
- 真实 OS signal 组合覆盖：S3B 已有两条真实 Mimo PTY 证据与 owner-level sequence matrix；最终 immutable post-fix bundle 仍必须重跑完整 F03 matrix。
- non-POSIX：当前 CLI oracle 和真实证据平台为 POSIX；不扩张 Windows 输入实现。
- Authorization 被 EventLog/SQLite 持久化：独立安全 residual，不属于 F01-F07，最终 closeout 明确 owner 和风险；本 work unit 不下游补偿。

## Gate 结论

**FIX-LOOP-REQUIRED**。只接受 Mimo finding。Fix scope 限定为 composer owner 的 typed “结束 submit-delivery intent、保留 draft/cursor/revision”动作、READ_ONLY rejection 调用点及对应 tests/档案；不修改其它 DS 建议项，不 stage/commit S8 保留文件。修复后必须由 Mimo 与 DeepSeek 复审并形成 durable artifacts，再由总控逐项裁决。
