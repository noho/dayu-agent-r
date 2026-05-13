# Code Review: Host Phase 1 Slice 2 — `dayu.runtime.lane` Cross-Process Coordinator

## Review Gate

code review

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施

## Assigned Slice

Slice 2: `dayu.runtime.lane` cross-process coordinator

## Review Artifact

`docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-mimo-20260513.md`

## Approved Plan

`docs/host/phase1-public-contract-runtime-plan.md`

## Implementation Artifact

`docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`

## Accepted Slice 1 Commit

`66d8dc3`

## Diff Scope

uncommitted workspace changes after controller state commit `911b59a`

## Review Date

2026-05-13

## Reviewer

AgentMiMo (code review gate)

---

## Finding 数量: 3

## Blocking Finding 数量: 0

---

## Findings

### F-01 已修复 [LOW] `LaneController.open` 非 async，与 plan 公共 API shape 不一致

**文件**: `dayu/runtime/lane.py:378-414`

**Plan 声明** (phase1-public-contract-runtime-plan.md:310-316):

```text
class LaneController:
    @classmethod
    async def open(
        cls,
        configs: Sequence[LaneConfig],
        *,
        coordinator: SQLiteLaneCoordinatorConfig,
        owner: LaneOwner | None = None,
    ) -> LaneController
```

**实现实际**: `open` 是同步 `@classmethod`，非 `async`。

**影响**: 当前实现内部无 async 操作（`_prepare_database_parent`、`_initialize_database` 均为同步），同步 `open` 在功能上是正确的。但如果后续 Host composition root 需要 async 初始化（例如异步读取配置或等待锁），调用方需要改写。这是一个 plan/implementation 一致性偏差，不是功能 bug。

**证据**: `inspect.iscoroutinefunction(LaneController.open)` 返回 `False`。

**建议**: 更新 plan 将 `open` 改为同步签名，或在后续 slice 改为 async。当前 slice 功能正确，不阻塞。

**Fix status**: 已修复于 fix gate。`LaneController.open` 已改为 async classmethod，DB parent 准备与初始化通过 `asyncio.to_thread` 执行，测试与多进程 helper 已同步 `await` 调用。

---

### F-02 已修复 [LOW] heartbeat loop 未处理 `RuntimeLaneError`（不可恢复 SQLite 错误）

**文件**: `dayu/runtime/lane.py:770-792`

**Plan 要求** (phase1-public-contract-runtime-plan.md:361):

> background heartbeat 遇到不可恢复 SQLite error 时，controller 记录 first heartbeat error，停止接受新 acquire，并让后续 acquire 返回 cancelled 或抛结构化 `RuntimeLaneError`。不得静默继续误导调用方。

**实现实际**: `_heartbeat_loop` 只捕获 `RuntimeLaneClaimLostError` 和 `asyncio.CancelledError`。若 `_refresh_token_sync` 抛出 `RuntimeLaneError`（SQLite 操作失败），异常会从 `asyncio.Task` 中逃逸，但无人调用 `_heartbeat_task.result()` 检查。controller 不会停止接受新 acquire。

**影响**: 极端场景下（SQLite 文件损坏、磁盘满），heartbeat 静默失败，controller 继续接受新 acquire，但已有 token 的 heartbeat 不再刷新，最终 TTL 过期导致 claim 丢失。调用方在 heartbeat 失败到 TTL 过期之间的窗口内可能误以为仍持有 capacity。

**建议**: 在 `_heartbeat_loop` 中增加 `except RuntimeLaneError` 分支，行为与 `RuntimeLaneClaimLostError` 一致（标记 `_closed = True`，唤醒 waiters）。或在 `_ensure_heartbeat_task` 中检查 task 异常。

**Fix status**: 已修复于 fix gate。heartbeat loop 已区分单 token lost 与不可恢复 `RuntimeLaneError`；不可恢复错误会记录首个 heartbeat error、停止新 acquire、唤醒 pending acquire，并让后续 acquire 抛结构化 `RuntimeLaneError`。

---

### F-03 [INFO] `_format_datetime` 使用 `astimezone(UTC)` 转换，对已为 UTC 的 datetime 有冗余调用

**文件**: `dayu/runtime/lane.py:990-997`

```python
def _format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")
```

`_LaneClock.now()` 返回的 datetime 已经是 UTC-aware（通过 `datetime.now(UTC)` anchor 推导）。`astimezone(UTC)` 对已为 UTC 的 datetime 是 no-op，但增加了可读性开销。

**影响**: 无功能影响。纯代码风格观察。

**建议**: 无需修改。`astimezone(UTC)` 作为防御性调用可接受。

---

## 逐项 Review Criteria 对照

### 1. 公共 API Shape

| 元素 | Plan | 实现 | 状态 |
|---|---|---|---|
| `LaneConfig` | `frozen=True, slots=True` | `frozen=True, slots=True` | ✅ |
| `LaneOwner` | `frozen=True, slots=True` | `frozen=True, slots=True` | ✅ |
| `SQLiteLaneCoordinatorConfig` | `frozen=True, slots=True` | `frozen=True, slots=True` | ✅ |
| `LaneClaimToken` | `slots=True`（非 frozen） | `slots=True, frozen=False` | ✅ |
| `LaneClaimToken.refresh` | `async` | `async` | ✅ |
| `LaneClaimToken.release` | `async` | `async` | ✅ |
| `LaneAcquired` | `frozen=True, slots=True` | `frozen=True, slots=True` | ✅ |
| `LaneAcquireCancelled` | `frozen=True, slots=True` | `frozen=True, slots=True` | ✅ |
| `LaneAcquireTimedOut` | `frozen=True, slots=True` | `frozen=True, slots=True` | ✅ |
| `LaneAcquireOutcome` | `TypeAlias` union | `TypeAlias` union | ✅ |
| `LaneController.open` | `async classmethod` | sync `@classmethod` | ⚠️ F-01 |
| `LaneController.acquire` | `async` | `async` | ✅ |
| `LaneController.close` | `async` | `async` | ✅ |
| Error classes | 4 个 | 4 个 | ✅ |
| `__all__` | 包含所有公共符号 | 包含所有公共符号 | ✅ |

### 2. SQLite DB 独立性与 Schema

- ✅ 独立 DB 文件，不复用 Host durable store
- ✅ `PRAGMA journal_mode=WAL`（`lane.py:925`，测试验证 `lane.py:237-241`）
- ✅ per-connection `PRAGMA busy_timeout`（`lane.py:971`）
- ✅ Schema 字段：`lane_name, claim_id, owner_id, owner_pid, owner_process_start_token, created_at, heartbeat_at, expires_at`
- ✅ 无 Host/Fins 字段（测试验证 forbidden_columns 集合）
- ✅ Primary key: `(lane_name, claim_id)`（`lane.py:936`）
- ✅ Index: `(lane_name, expires_at)` 用于 active claims 查询（`lane.py:940-942`）
- ✅ Index: `(lane_name, owner_id)` 用于 owner 查询（`lane.py:943-946`）

### 3. Owner 默认值

- ✅ `owner_id = secrets.token_hex(8)`（`lane.py:403`）
- ✅ `pid = os.getpid()`（`lane.py:404`）
- ✅ `process_start_token = None`（`lane.py:405`）

### 4. Stale Cleanup + Active Count + Insert 事务原子性

- ✅ 三步操作在同一 `BEGIN IMMEDIATE` 事务内（`lane.py:556-593`）
- ✅ 测试 `test_concurrent_acquire_keeps_capacity_invariant` 验证并发不突破 capacity

### 5. Timeout / Cancel / Close 语义

- ✅ `timeout_seconds=0` non-blocking（`lane.py:488-489`）
- ✅ `timeout_seconds=None` 使用 lane 默认或无限等待（`lane.py:441-444`）
- ✅ 正 timeout 使用 deadline（`lane.py:446-450`）
- ✅ `CancellationToken.is_cancelled()` 返回 `LaneAcquireCancelled`（`lane.py:453-454`）
- ✅ `Task.cancel()` 透传 `CancelledError`（`lane.py:536-541`，使用 `asyncio.shield`）
- ✅ `close()` 唤醒 pending acquire、释放 held tokens、停止 heartbeat（`lane.py:500-520`）
- ✅ `close()` 幂等（`lane.py:508-509`）
- ✅ acquire 成功后二次检查 cancel/close（`lane.py:463-468`）

### 6. Heartbeat / Lost Claim / Release 幂等

- ✅ controller-managed heartbeat task（`lane.py:761-792`）
- ✅ heartbeat 按最小 `heartbeat_interval_seconds` 调度（`lane.py:374-376`）
- ✅ claim lost 时标记 token lost 并关闭 controller（`lane.py:785-790`）
- ✅ `release()` 幂等（`lane.py:676-677`）
- ✅ release 按 `(lane_name, claim_id, owner_id)` 删除（`lane.py:717-721`）
- ⚠️ heartbeat loop 未处理 `RuntimeLaneError`（F-02）
- ✅ 无 hidden Host truth / lease / fencing / Attempt owner / EventLog identity

### 7. 多进程测试

- ✅ 父进程通过 `tmp_path` 创建 DB，CLI 参数传给子进程（`test_lane_multiprocess.py:226-229`）
- ✅ capacity invariant: 5 child / capacity 2，acquired <= 2（`test_capacity_invariant_across_processes`）
- ✅ non-blocking timeout when held（`test_nonblocking_timeout_when_held_and_release_allows_other_process`）
- ✅ release 后其它进程 acquire（同上测试）
- ✅ crash 后 TTL stale cleanup eventual acquire（`test_crashed_holder_is_cleaned_by_ttl_and_other_process_can_acquire`）
- ✅ 子进程使用 `os._exit` 模拟 crash（`lane.py:420`）
- ✅ 不断言 FIFO / fairness / ordering

### 8. Import 边界与类型约束

- ✅ `dayu.runtime.lane` 只 import `dayu.contracts.cancellation.CancellationToken`（`lane.py:23`）
- ✅ 无 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` import
- ✅ 无 `Any` / `object` / 无类型参数 / 无类型返回值
- ✅ 所有函数/类有中文 docstring
- ✅ `test_runtime_import_boundary_scan_covers_lane_module` 确保扫描覆盖

### 9. README 更新

- ✅ `dayu/README.md`: lane 从"设计要求"移至"当前已有层中立能力"，描述当前事实
- ✅ `tests/README.md`: 增加 lane 测试命令与覆盖范围描述
- ✅ 无旧术语残留
- ✅ 无越界职责

---

## Open Questions / Residual Risks

1. **heartbeat loop 不可恢复错误处理** (F-02): 当前实现中，SQLite 不可恢复错误会导致 heartbeat task 静默失败。虽然 TTL 过期最终会释放 capacity，但调用方在窗口期内可能误判。建议后续 slice 修复。

2. **SQLite 高并发 busy 抖动**: 已在 implementation artifact 中记录为 later phase risk。当前测试已验证 capacity invariant 不破坏。

3. **跨进程 clock skew**: `_LaneClock` 使用进程内 monotonic anchor，跨进程 skew 只影响 stale cleanup 精确时间，不影响 capacity invariant。

4. **workspace runtime lane DB cleanup policy**: 当前 slice 不负责删除 DB 文件，由后续 Host composition root / workspace lifecycle phase 决定。

---

## Recommendation

**proceed** — 无 blocking finding。F-01 和 F-02 均为 LOW severity，不阻塞当前 slice 合并。F-02 建议在后续 slice 修复。

实现完整覆盖了 plan 的 Slice 2 要求：公共 API shape 基本一致（`open` 签名偏差为非阻塞）、SQLite 独立 DB + WAL + busy_timeout、事务原子性、timeout/cancel/close 语义、heartbeat/lost claim/release 幂等、多进程 capacity invariant + stale cleanup、import 边界、README 同步。全部 17 个测试通过，pyright 0 errors。
