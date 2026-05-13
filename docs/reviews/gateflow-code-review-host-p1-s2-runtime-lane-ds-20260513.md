# Gateflow Code Review — Host Phase 1 Slice 2: `dayu.runtime.lane`

## Review Metadata

- **Review role**: AgentDS
- **Gate**: code review
- **Work unit**: Host Phase 1 公共契约与 runtime 基础设施
- **Assigned slice**: Slice 2: `dayu.runtime.lane` cross-process coordinator
- **Approved plan**: `docs/host/phase1-public-contract-runtime-plan.md`
- **Implementation artifact**: `docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`
- **Accepted Slice 1 commit**: `66d8dc3`
- **Diff scope**: uncommitted workspace changes after controller state commit `911b59a`
- **Review artifact**: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-ds-20260513.md`
- **Review date**: 2026-05-13

## Files Reviewed

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_lane_multiprocess.py`
- `tests/runtime/test_import_boundary.py`
- `dayu/README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`

## Review Criteria

对比实现与 `docs/host/phase1-public-contract-runtime-plan.md` 中 Slice 2 和 Cross-Process `dayu.runtime.lane` Decisions，逐项核查公共 API 形状、SQLite coordinator 语义、timeout/cancel/close 语义、heartbeat/lost claim 语义、多进程测试覆盖、import boundary 与弱类型守卫、README 同步。

## Validation Re-run

```bash
source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q
# 14 passed in 1.10s

source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py -q
# 3 passed in 0.03s

source .venv/bin/activate && python -m pyright dayu/runtime/lane.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py
# 0 errors, 0 warnings, 0 informations
```

## Passed Criteria

### Public API Shape

- `LaneConfig` — frozen slots dataclass, 字段、校验、中文 docstring 均符合 plan。✅
- `LaneOwner` — frozen slots dataclass, `owner_id`/`pid`/`process_start_token` 字段与校验符合 plan。✅
- `SQLiteLaneCoordinatorConfig` — frozen slots dataclass, 显式 `db_path`、`create_parent_dirs`、`busy_timeout_seconds`、`poll_interval_seconds`。✅
- `LaneClaimToken` — slots dataclass, `refresh()`/`release()` 均为 `async`。✅
- `LaneAcquired` / `LaneAcquireCancelled` / `LaneAcquireTimedOut` — frozen slots dataclass, 字段与语义符合 plan。✅
- `LaneAcquireOutcome` — `typing.TypeAlias`, 定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`，未创建新 dataclass/wrapper class。✅
- `LaneController` — class with `acquire()`/`close()` async methods。✅
- Error classes — `RuntimeLaneError`、`RuntimeLaneConfigError`、`RuntimeLaneClosedError`、`RuntimeLaneClaimLostError` 齐全且层次正确。✅
- `__all__` — 精确列出所有公共类型，无泄漏。✅

### SQLite DB Independence

- 独立 SQLite runtime lane DB，不复用 Host durable store。✅
- `LaneController.open()` 显式接收 `SQLiteLaneCoordinatorConfig(db_path=...)`，无隐式默认路径。✅
- DB 初始化设置 `PRAGMA journal_mode=WAL`；per-connection 设置 `PRAGMA busy_timeout`。✅
- Schema 只保存 runtime capacity claim 字段（`lane_name`, `claim_id`, `owner_id`, `owner_pid`, `owner_process_start_token`, `created_at`, `heartbeat_at`, `expires_at`）。✅
- 测试断言 schema 不包含 Host/Fins 字段（`session_id`, `run_id`, `attempt_id`, `event_sequence`, `event_id`, `tool_name`, `fins_document_id`）。✅
- Stale cleanup（`DELETE WHERE expires_at <= ?`）、active count（`SELECT COUNT(*) WHERE expires_at > ?`）与 insert 在同一个 `BEGIN IMMEDIATE` 短事务内完成。✅
- 等待 acquire 使用 poll/event wakeup，不持有长事务。✅

### Owner Defaults

- `owner=None` 时 `owner_id=secrets.token_hex(8)`、`pid=os.getpid()`、`process_start_token=None`。✅
- 调用方可显式传入 `LaneOwner` 覆盖。✅

### Timeout / Cancel / Close Semantics

- `timeout_seconds=None` → 使用 lane 默认 timeout；两者都 `None` → 无限等待。✅
- `timeout_seconds=0` → non-blocking，capacity 满时返回 `LaneAcquireTimedOut`，不占容量。✅
- 正 timeout → 最多等待对应秒数，超时返回 `LaneAcquireTimedOut`，不占容量。✅
- `CancellationToken` 取消 → 返回 `LaneAcquireCancelled(reason=token.cancel_reason())`，不得创建 claim。✅
- `asyncio.Task.cancel()` → 透传 `asyncio.CancelledError`，且通过 `asyncio.shield` + best-effort release 保护，不泄漏额外 claim。测试覆盖。✅
- `LaneController.close(reason)` — 幂等，停止新 acquire，唤醒 pending acquire 返回 `LaneAcquireCancelled`，best-effort release 当前 tokens，停止 heartbeat task。✅
- close 后新 acquire 抛 `RuntimeLaneClosedError`。✅

### Heartbeat / Lost Claim Semantics

- Controller-managed heartbeat task，按最小 `heartbeat_interval_seconds` 调度。✅
- `_LaneClock` 使用 `time.monotonic()` + UTC anchor 生成进程内一致的 UTC datetime。✅
- `LaneClaimToken.refresh()` 支持显式调用。✅
- `LaneClaimToken.release()` 幂等，按 `(lane_name, claim_id, owner_id)` 删除。✅
- 重复 release 不影响其它 claim。测试覆盖。✅
- Claim row 被外部删除后 `refresh()` 抛 `RuntimeLaneClaimLostError`，`release()` 仍保持幂等。测试覆盖。✅

### Multi-Process Tests

- 父进程用 `tmp_path` 创建共享 DB 路径，通过 CLI 参数传给子进程。✅
- 容量 invariant：`test_capacity_invariant_across_processes` — 5 个子进程竞争 capacity=2，acquired 不超过 2。✅
- Non-blocking timed out：`test_nonblocking_timeout_when_held_and_release_allows_other_process` — 持有 claim 时其它进程 non-blocking timed out，release 后可 acquire。✅
- Crash/stale cleanup：`test_crashed_holder_is_cleaned_by_ttl_and_other_process_can_acquire` — 子进程 `os._exit()` 崩溃后，父进程 TTL stale cleanup 后可 acquire。✅
- 不断言 acquire ordering。✅
- 不使用真实 `workspace/` 路径。✅

### Import Boundaries & Weak Typing

- `dayu.runtime.lane` 只依赖标准库 + `dayu.contracts.cancellation.CancellationToken`。✅
- 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。✅
- 不 import Phase 0 禁止的 HTTP 库。✅
- Import boundary 测试覆盖新增 `lane.py`。✅
- 无 `Any` / `object` / 无类型参数 / 无类型返回值。✅
- 全部中文 docstring。✅

### README Updates

- `dayu/README.md`：runtime lane 从设计要求同步为当前已实现层中立能力，内容准确。✅
- `tests/README.md`：增加 runtime lane 单进程/多进程测试命令与覆盖范围，内容准确。✅
- 未更新根目录 `README.md`、`dayu/runtime/__init__.py`（符合 plan non-goals）。✅

## Findings

### Finding 1 已修复 [Low] — `LaneController.open` 为同步方法，plan 指定为 `async`

- **File**: `dayu/runtime/lane.py:378-414`
- **Plan reference**: `docs/host/phase1-public-contract-runtime-plan.md`, Cross-Process `dayu.runtime.lane` Decisions > Public API，明确声明 `@classmethod async def open(...)`。
- **Observation**: 实现中 `open` 为同步 `@classmethod`。且 `open` 内部所有操作（目录创建、DB 初始化）均为同步，不存在需要 `await` 的路径。
- **Impact**: 不影响正确性。若后续需要在 `open` 中增加异步操作（如 async DB init），需改为 async 并更新所有调用方。
- **Recommendation**: 在 plan 中明确 `open` 为 sync（反思 spec 合理性），或在实现 artifact 中显式记录此偏差及其理由。当前实现 artifact 未提及此偏差。
- **Fix status**: 已修复于 fix gate。`LaneController.open` 已改为 async classmethod，DB parent 准备与初始化通过 `asyncio.to_thread` 执行，所有测试与子进程 helper 调用点已同步 await。

### Finding 2 已修复 [Medium] — Heartbeat loop 在单个 claim 丢失时关闭整个 controller

- **File**: `dayu/runtime/lane.py:783-790`
- **Plan reference**: `docs/host/phase1-public-contract-runtime-plan.md`, Time / heartbeat ownership 区分了两个场景：
  - (a) "heartbeat update 若发现对应 (lane_name, claim_id, owner_id) row 不存在或已过期，token 标记为 released / lost" — 单个 claim → 标记 lost。
  - (b) "background heartbeat 遇到不可恢复 SQLite error 时，controller 记录 first heartbeat error，停止接受新 acquire" — 不可恢复 SQLite error → 停止新 acquire。
- **Observation**: 实现中 heartbeat loop 在 catch `RuntimeLaneClaimLostError`（场景 a）时直接 `self._closed = True`，关闭整个 controller。这导致：若 controller 持有多个 claim，其中一个丢失，所有 claim 的服务都被终止，同时 pending acquire 被取消。
- **Secondary effect**: `_heartbeat_loop` 设 `_closed = True` 后直接 `return`，不 release 其余 held tokens。后续调用 `controller.close()` 在 `_closed` 已为 `True` 时直接返回（line 508），其余 held tokens 仅靠 TTL 过期释放，而非主动 release。
- **Impact**: 过度保守。单个 claim 丢失应只标记该 token 为 lost，继续刷新其余 tokens；只有不可恢复 SQLite error（`RuntimeLaneError`，非 `RuntimeLaneClaimLostError`）才应停止新 acquire。
- **Recommendation**: 将 heartbeat loop 的错误处理分层——`RuntimeLaneClaimLostError` 只调用 `_mark_token_lost` 并 continue 下一个 token；新增 `RuntimeLaneError` catch 路径以执行当前的 `_closed = True` 停止逻辑。同时，即使 `_closed` 已被 heartbeat 设置，`close()` 仍应遍历并 release 剩余 held tokens。
- **Fix status**: 已修复于 fix gate。`RuntimeLaneClaimLostError` 现在只标记对应 token lost/released 并继续刷新其它 token；不可恢复 `RuntimeLaneError` 才停止新 acquire；`close()` 即使 controller 已因 heartbeat error 进入 closed 状态，仍会 best-effort release 剩余 held tokens。

### Finding 3 [Info] — CancellationToken 在 `_wait_before_retry` 期间不被观察

- **File**: `dayu/runtime/lane.py:729-759`
- **Plan reference**: "等待期间传入的 CancellationToken 取消时返回 LaneAcquireCancelled"。
- **Observation**: `_wait_before_retry` 在入口处检查一次 token（line 743），但 `waiter.wait()` 阻塞期间不观察 token。取消检测延迟上限为一个 `poll_interval_seconds`（默认 0.05s）。
- **Impact**: 不影响正确性。协作式取消模型下，一个 poll interval 的检测延迟可接受。
- **Recommendation**: 无需修改。记录为已知设计权衡。

## Summary

| Category | Count |
|---|---|
| **Total findings** | 3 |
| **Blocking findings** | 0 |
| **Medium findings** | 1 (Finding 2) |
| **Low findings** | 1 (Finding 1) |
| **Info** | 1 (Finding 3) |

## Recommendation

**Proceed** — 无 blocking finding。

Finding 2（heartbeat loop 过度关闭 controller）是唯一的 medium finding，但由于：
1. 当前 `RuntimeLaneClaimLostError` 在 heartbeat loop 中只会在 claim_row 被外部删除或已过期时触发——这本身就表示异常状态。
2. 过度关闭的行为是保守的（fail-closed），不会导致 capacity invariant 被破坏或数据不一致。
3. 修复需要错误处理分层，属于 behavior refinement 而非 correctness fix。

建议在后续 Host dispatch integration 或 multi-process hardening phase 中一并修复 Finding 2。Finding 1 可在 plan 中标注为 spec 澄清。

## Open Questions / Residual Risks

1. **Workspace runtime lane DB cleanup policy** — 当前未定义。计划中列为后续 Host composition root / workspace lifecycle phase 负责。低风险，因为 lane DB 只保存 runtime capacity claims。

2. **跨进程 clock skew** — 影响 stale cleanup 精确时间。计划中列为后续 multi-process hardening phase 覆盖。当前只断言 eventual cleanup，可接受。

3. **SQLite 高并发 busy 抖动** — 当前 slice 已验证 capacity invariant 不破坏，但实际生产压力下的 acquire latency 仍待观察。
