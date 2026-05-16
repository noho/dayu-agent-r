# PR 58 Review Controller Adjudication - 2026-05-16

## Gate

当前 gate：PR 58 deepreview。

PR：

- `https://github.com/noho/dayu-agent-r/pull/58`
- title: `Host Phase 8 Projection Core and Event Stream`
- branch: `feat/host-phase8-projection-core-event-stream`

Review artifacts：

- `docs/reviews/pr-58-review-mimo-20260516.md`
- `docs/reviews/pr-58-review-ds-20260516.md`

## Controller Verdict

PR 58 暂不进入 `draft-PR-pass`。接受 1 个 blocking finding，进入 PR review fix gate。

## Accepted Current Fix

### PR58-F1: `RuntimeFileLock.__exit__` release failure clears active token too early

来源：AgentDS F1。

裁决：accepted current fix。

理由：`RuntimeFileLock.__exit__` 当前先执行 `self._active_token = None`，再调用 `token.release()`。如果底层 release
失败并抛出 `RuntimeFileLockError`，实例会表现为没有 active token，但底层锁可能仍未释放；后续 `acquire()` 无法通过
active-token guard 感知旧 token，可能进入阻塞等待。该问题位于 `dayu.runtime.filelock`，修复只需保证 release 成功后再清
active token，并补充 release failure 测试。

修复要求：

- `__exit__` 必须先调用 `token.release()`。
- 只有 release 成功后才能清空 `_active_token`。
- 新增测试模拟 release 失败，断言 `_active_token` 保留且同实例再次 `acquire(timeout_seconds=0)` fail fast。

允许修改：

- `dayu/runtime/filelock.py`
- `tests/runtime/test_filelock.py`
- `docs/reviews/pr-58-fix-codex-20260516.md`

禁止修改：

- Host projection/read model/event stream 逻辑。
- Engine/Fins/Service/UI。
- schema / DDL。
- Git commit / push / PR。

## Rejected / Non-Blocking Findings

- MiMo low findings：marker restore 异常吞掉与 `_ensure_lock_file_marker_exists` 冗余。当前 marker restore 是 release
  成功后的 best-effort，且不参与 Host durable truth；不作为 PR blocker。
- DS F2 `_record_failure` 失败覆盖 consumer error：accepted-as-non-blocking / deferred to projection diagnostics
  hardening owner。当前 checkpoint 不推进，状态一致性不受影响。
- DS F3 `reset_minimal_read_model_projection` 单 consumer data table reset：rejected-as-current-defect；Phase 8 设计中
  minimal read model 是单 consumer 投影，multi-consumer ownership 属后续 projection scale design。
- DS F4 `_ensure_checkpoint` 使用 write transaction：performance hardening，非 correctness blocker。
- DS F5 `clear_projection_failure` rowcount guard：defensive hardening，非 correctness blocker。
- DS F6 `_utc_now_text` 重复：低价值 cleanup，不作为 PR blocker。

## Deferred Test Gaps

- DS TG1 空 EventLog runner 测试：deferred to projection test hardening owner；当前 `read_events_after` 空返回路径简单且已有
  cursor/no-event semantics 在 public stream 层覆盖。
- DS TG2 terminal event `run_id=None`：deferred / needs design guard。terminal facts 按设计必须关联 Run；该场景更适合作为
  invalid event payload / invariant hardening。
- DS TG3 concurrent checkpoint runner：deferred to multi-instance projection scale owner。
- DS TG4 invalid cursor：rejected；`HostStreamCursor` 构造期已拒绝负数。
- DS TG5 valid `run_id=None` timeline 投影：deferred to session-level timeline expansion owner。

## Required Validation

```bash
source .venv/bin/activate
pytest tests/runtime/test_filelock.py -q
pytest tests/host tests/runtime -q
python -m pyright dayu/ tests/ utils/
git diff --check
```
