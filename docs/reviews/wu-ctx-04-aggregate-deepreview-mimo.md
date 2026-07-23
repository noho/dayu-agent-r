# WU-CTX-04 Aggregate Deep Review — AgentMiMo

## Scope

- **Mode**: current changes (aggregate deepreview)
- **Branch**: `feat/wu-ctx-04`
- **Base**: `974f9e16` (PR #181 merge commit, main baseline)
- **Tip**: `24dfcf37` (accepted Slice 3)
- **Output file**: `docs/reviews/wu-ctx-04-aggregate-deepreview-mimo.md`
- **Review date**: 2026-07-22
- **Commits**: 4 (`1f032b5e` plan, `eda1d70e` slice 1, `4ca0810b` slice 2, `24dfcf37` slice 3)
- **Changed files**: 124 files, +20746 / -1557 lines
- **Included scope**: All production Python under `dayu/host/`, `dayu/runtime/`, `dayu/config/`, `dayu/service/`; all test Python under `tests/`; all README and design docs; review artifacts; CLI and smoke scripts
- **Excluded scope**: Generated files, `.venv/`, `__pycache__/`, `.git/`
- **Parallel review coverage**: 3 subagents (attachment & mutex lifecycle; proactive compaction & single-operation boundary; dispatch, recovery, scheduler close barrier, cancel, terminal, canonical reason). Cross-cutting dimensions (SQLite batching, stale field removal, public/API/LLM-facing schema, README consistency, project instruction compliance) verified by main reviewer directly.

## Verified Checklist

| 维度 | 判定 | 证据摘要 |
|---|---|---|
| Attachment access ownership | PASS | `session_attachment.py:424-430` mutex acquire 决定不可变 mode；`try_acquire_new_work_lease` 对非 READ_WRITE 返回 None；所有 mutation entry points 通过 lease 或直接 mode 检查 gate |
| Native mutex lifecycle | PASS (1 finding) | `StrictNativeSessionMutex` 使用 `os.open` + `msvcrt.locking`/`fcntl.flock`；handle `close()` 释放 fd；process crash 由 OS 释放锁。host close 时 `_release_record` 在 mutex release 失败后不清理 record（见 F-01） |
| Proactive single-operation invariant | PASS | `proactive_compaction.py:394` 严格拒绝 >1 proactive request；`dispatch.py:2393` binary CREATE_NEW / RESUME_EXISTING 分支；`max_proactive_compactions_per_run` 全量删除（production + tests 零残留） |
| Incomplete-operation crash recovery | PASS | RESUME_EXISTING 路径提取原 operation_id、first_attempt_number、max_attempt_number；snapshot validation 校验 input cursor / material digest / material refs / attempt schedule 一致性 |
| Scheduler close barrier | PASS | 三阶段 close：`begin_host_close`(CLOSING + block new work) → `drain_host_close`(await all leases) → scheduler `close()`(cancel tasks + write STOPPED) → `release_host_close`(release mutex)。STOPPED 在 mutex release 前写入 |
| Target-only cancel / watchdog | PASS | `cancel_run` 写 durable CANCEL_REQUESTED；`reconcile_active_worker_cancels_once` 按 exact owned Attempt identity 传播；watchdog 只作 closeout supervisor |
| Canonical reason | PASS (1 finding) | `run_transition.py` 投影 typed cancel reason；`_cancelled_eof_candidate` 有防御性 fallback `"host_cancelled"`（见 F-02） |
| Terminal producer | PASS | `terminal_closeout_in_transaction` 检查 `_terminal_closeout_replay_result` 幂等；所有 terminal event 使用 uuid4 唯一 id |
| SQLite batching | PASS | `state.py:142-150` 以 `_SQLITE_LEGACY_DEFAULT_MAX_VARIABLE_NUMBER=999` 推导 `_OWNED_CANCEL_QUERY_BATCH_SIZE=199`；完整输入校验在先，全局顺序严格保持 |
| Stale field removal | PASS | `max_proactive_compactions_per_run` 在 production Python、test Python、execution_profiles.json 中零残留；31 处仅存于 `docs/` 历史 review artifacts |
| Public/API/LLM-facing schema | PASS | `api.py` 导出 `HostSessionAttachment` Protocol、`HostSessionAccessMode`、`HostSessionAttachmentConflictDetail`；`__init__.py` re-export 一致；README 对齐新概念 |
| README consistency | PASS | `dayu/host/README.md`、`dayu/README.md`、`dayu/service/README.md`、`tests/README.md`、`dayu/config/README.md` 均已同步 attachment、native mutex、proactive compaction single-operation 语义 |
| Type safety & docstrings | PASS | 新增 production 代码无 `Any`/`object` 类型注解；所有函数有中文 docstring 含 `:param:`/`:returns:`/`:raises:` |
| Test coverage | PASS | 21 个变更 production Python 文件逐文件 coverage 均 ≥ 80%（最低 81%）；全量 pyright `0 errors`；全量 pytest `5593 passed` |

## Findings

### F-01 · [MEDIUM] · `_release_record` mutex release 失败后 record 残留导致 `_host_close_released` 永远无法置位

- **入口/函数**: `HostSessionAttachmentRegistry.release_host_close()` → `_release_record()`
- **文件(行号)**: `dayu/host/session_attachment.py:782-793`, `590-605`
- **输入场景**: Host 正常关闭流程中，某个 Session 的 native mutex handle `close()` 抛出 `StrictNativeMutexUnavailableError`（例如 fd 已被外部关闭、内核级文件系统错误等极端场景）
- **实际分支**: `_release_record` 第 785-788 行捕获异常，设置 `record.close_error` 和 `record.close_completed`，返回错误——但 **不删除** `self._records[record.session_id]`。`release_host_close` 第 602 行 `if not self._records: self._host_close_released = True` 条件永远不满足
- **预期行为**: mutex handle 已消费（fd 关闭或 None），不会产生 stale lock。record 应从 registry 中移除，使 `_host_close_released` 可正常置位，宿主关闭流程可干净终止
- **实际行为**: record 留在 registry 中（state=CLOSING，close_error 已设置）。后续 `release_host_close` 调用重新进入 `_release_record`，命中第 774-775 行或第 778-780 行 short-circuit 返回同一 error，再次 raise。`_host_close_released` 永远为 False
- **直接证据**: 第 786-788 行 `record.close_error = exc; record.close_completed.set(); return exc`——record 未被删除。第 602 行 `if not self._records`——条件不满足
- **影响**: 宿主进程关闭路径无法干净终止信号。mutex 不会泄漏（handle 已消费），但 close 语义不完整。不会导致数据丢失或 stale lock
- **建议改法**: 在 `_release_record` 的异常处理分支（第 785-788 行）之后，增加 `if self._records.get(record.session_id) is record: del self._records[record.session_id]`，使 record 即使 release 失败也从 registry 移除。或在 `release_host_close` 循环后主动清理已 CLOSED/errored 的 record
- **修复风险**: 低
- **严重程度**: 中

### F-02 · [LOW] · `_cancelled_eof_candidate` 存在防御性 fallback reason，code-structure 层面违反"dispatch 不生成替代常量"不变量

- **入口/函数**: `_cancelled_eof_candidate()`
- **文件(行号)**: `dayu/host/dispatch.py:5014-5016`
- **输入场景**: worker stream 以 clean EOF 结束且 cancellation token 已设置，但 `cancel_reason()` 返回 None
- **实际分支**: 第 5014-5016 行 `reason = cancellation_token.cancel_reason(); if reason is None: reason = "host_cancelled"`
- **预期行为**: canonical cancel reason 应从 durable `CANCEL_REQUESTED` event payload 流入，dispatch 不生成替代常量
- **实际行为**: 当 `cancel_reason()` 为 None 时，使用硬编码字符串 `"host_cancelled"` 作为 reason
- **直接证据**: 第 5015-5016 行 `if reason is None: reason = "host_cancelled"`。正常路径下 `_HostCancellationToken.request_cancel()` 总是设置非 None reason（第 964-974 行），两个调用点（第 4760、4799 行）都在 `cancellation_token.is_cancelled()` 为 True 且 `cancel_requested_at is not None` 时才调用——因此 fallback 在当前实现中不可达
- **影响**: 当前实现下不可达。但 code-structure 层面违反"dispatch 不生成替代常量"的设计不变量；若未来注入非 `_HostCancellationToken` 子类的 token，fallback 会产生非 canonical reason
- **建议改法**: 将 fallback 改为 `raise RuntimeError("cancel_reason() 不应在 is_cancelled() 为 True 时返回 None")`，或在 docstring 中明确说明这是 intentional defensive fallback
- **修复风险**: 低
- **严重程度**: 低

### F-03 · [LOW] · `drain_host_close` 无超时保护，Host close 可能无限阻塞

- **入口/函数**: `HostSessionAttachmentRegistry.drain_host_close()`
- **文件(行号)**: `dayu/host/session_attachment.py:569-572`
- **输入场景**: Host 正常关闭流程中，某个 in-flight mutation 或 new-work 的底层 actor/worker 挂起不归还
- **实际分支**: 第 570 行 `await record.mutation_drained.wait()` 和第 572 行 `await record.new_work_drained.wait()`——均无 timeout 参数
- **预期行为**: drain 应有有界等待时间，超时后强制 set drain event 并标记 error，使宿主 close 可继续
- **实际行为**: 若底层 actor 挂起，drain 无限等待，宿主关闭流程永久卡住
- **直接证据**: 第 570 行 `await record.mutation_drained.wait()` 无 timeout。宿主 close 流程（`open_host.py`）在 drain 之后才执行 `scheduler.close()` 和 `release_host_close()`
- **影响**: 宿主进程无法干净退出。依赖 Host close 层外部 timeout（如 `asyncio.wait_for`）保护
- **建议改法**: 在 `_AttachmentRecord` 层面增加 drain 超时（如传入 close timeout），超时后强制 set drain event 并标记 record 为 error；或由 Host close 层使用 `asyncio.wait_for` 包装。建议在 Host close 层增加显式 timeout
- **修复风险**: 低
- **严重程度**: 低

### F-04 · [LOW] · `release_when_done` 未防御 already-done Future，lease 可能在 caller 预期时间点之前释放

- **入口/函数**: `_NewWorkLease.release_when_done()`
- **文件(行号)**: `dayu/host/session_attachment.py:172-173`
- **输入场景**: 传入 `release_when_done` 的 Future 在调用前已 complete（例如 executor 极快返回或 Future 来自外部已完成源）
- **实际分支**: `future.add_done_callback(self._release_after_future)`——Python 若 future 已 done，callback 立即同步调用
- **预期行为**: lease 应在 caller 预期的工作完成后释放
- **实际行为**: 若 future 已 done，callback 在 `release_when_done` 调用点同步触发，lease 立即归零
- **直接证据**: Python 文档：若 future 已 done，`add_done_callback` 立即调用。当前 `open_host.py:1076` 的 `recovery_lease.release_when_done(recovery_future)` 路径中 `submit` 返回 `wrap_future` 总是 pending，实际不触发
- **影响**: 当前实现下不可达。但 Protocol 契约未约束调用方，外部调用者传入已 done Future 会导致 drain event 提前 set
- **建议改法**: 在 `release_when_done` 中判断 `future.done()`：若已 done 则直接 `self.release()`（行为一致），并在 docstring 中明确说明该语义
- **修复风险**: 低
- **严重程度**: 低

## Open Questions

### Q-01 · `acquire_mutation_lease` 对 RECOVERING 状态的拒绝 reason 是否需要更精确？

`acquire_mutation_lease` 在 record 为 RECOVERING 时拒绝（`session_attachment.py:477-482`），返回 `ATTACHMENT_REQUIRED` 而非更精确的 `RECOVERING` reason。当前 `HostSessionMutationRejectionReason` 只有三个成员（`ATTACHMENT_REQUIRED`, `READ_ONLY`, `ATTACHMENT_CLOSING`）。RECOVERING 是临时状态，`ATTACHMENT_REQUIRED` 语义已足够覆盖"尚未就绪"的含义，但若未来需要区分"正在恢复"和"未 attach"，需要新增 reason 枚举值。当前不影响 correctness，不阻塞 ship。

### Q-02 · NFS 文件系统上 flock 语义不同，是否需要文档声明？

POSIX `flock` 在进程退出时由 kernel 释放，此行为正确。但若 lock file 在 NFS 挂载的远程文件系统上，`flock` 语义不同。当前代码未显式排除 NFS 场景。建议在 `native_mutex.py` docstring 或 README 中声明仅支持本地文件系统。当前不影响 correctness（Dayu 默认本地部署），不阻塞 ship。

## Residual Risks

1. **Host close drain 无限等待 (F-03)**: 依赖 Host close 层外部 timeout。若 Host close 层未做 timeout，进程关闭可能永久卡住。风险低——建议在 Host close 层增加显式 `asyncio.wait_for` 包装。

2. **Native mutex release error 导致 host close 语义不完整 (F-01)**: mutex handle 已消费（fd=None），不会产生 stale lock。但 host close 状态机无法干净终止。风险中等——需要在 `_release_record` 中增加 failed record 清理逻辑。

3. **Recovery timing window**: Host crash 后写入 `CONTEXT_COMPACTION_REQUESTED` 但未写 proposal manifest 时，recovery 从 attempt 1 重新开始。正确行为——frozen request 和 material snapshot 仍有效。若 recovery host 的 compactor 配置不同（如不同 model），snapshot validation 会 fail closed。风险极低。

4. **Tier recovery schedule determinism**: 代码更新后 recovery 时 attempt schedule 可能不匹配 frozen state。`_validate_proactive_resume_snapshot` 会 fail closed 并 fallback。正确 fail-closed 行为。风险极低。

5. **Heartbeat staleness during long close**: scheduler `close()` 耗时超过 30 秒 stale threshold 时，旧 instance heartbeat 可能过期。但 recovery classifier 同时检查 process liveness，live-but-closing process 会被分类为 `OwnerStillLive`。无实际 gap。风险极低。

6. **Windows `msvcrt.locking` 进程异常退出行为**: 未验证 Windows 平台下进程 SIGKILL 后锁释放行为。风险低——Windows 非主要部署平台。

## Verdict

**PASS** — 0 个 blocking findings，4 个 actionable findings（1 medium + 3 low），均为非阻塞改进项。所有关键验收维度（attachment access ownership、native mutex lifecycle、proactive single-operation invariant、incomplete-operation crash recovery、scheduler close barrier、target-only cancel/watchdog、canonical reason、terminal producer、SQLite batching、stale field removal、public/API/LLM-facing schema、README consistency）均通过直接代码证据验证。

### Actionable Findings Summary

| ID | Severity | Title | Blocking |
|---|---|---|---|
| F-01 | Medium | `_release_record` mutex release 失败后 record 残留 | No |
| F-02 | Low | `_cancelled_eof_candidate` fallback reason | No |
| F-03 | Low | `drain_host_close` 无超时保护 | No |
| F-04 | Low | `release_when_done` 未防御 already-done Future | No |

### Blocking Questions

None。
