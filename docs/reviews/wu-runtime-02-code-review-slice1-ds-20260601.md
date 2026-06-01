# Code Review

## Scope

- Mode: current changes
- Branch: fix/wu-runtime-02-lane-clock-cancellation
- Base: main
- Output file: docs/reviews/wu-runtime-02-code-review-slice1-ds-20260601.md
- Included scope:
  - `dayu/runtime/lane.py` — `_LaneClock` 改为无 anchor、`utc_now()` 使用真实 `datetime.now(UTC)`；`_try_claim_once_sync()` / `_refresh_token_sync()` 使用真实 UTC per transaction
  - `tests/runtime/test_lane.py` — 新增 `test_lane_ttl_uses_real_utc_not_monotonic_elapsed`、`test_refresh_uses_real_utc_not_monotonic_elapsed`
  - `docs/host/design.md` — lane clock 表述同步为真实 UTC per SQLite transaction
  - `tests/README.md` — lane 测试覆盖描述补充 TTL monotonic 独立性
  - Implementation artifact: `docs/reviews/wu-runtime-02-implementation-slice1-codex-20260601.md`
- Excluded scope:
  - Slice 2 (bounded cancellation cleanup): 不在本次 review scope
  - `docs/host/host-core-followup-implementation-control.md` 未提交改动: controller bookkeeping，非 implementation finding
  - `tests/runtime/test_lane_multiprocess.py`: 未修改，仅作为回归验证参考
  - `LaneClaimToken.released` public field: plan 明确不处理
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Trace

### 1. `_LaneClock` 重构正确性

**入口**: `_LaneClock.start()` (lane.py:312-319) → `LaneController.open()` (lane.py:391-426)

**变更前**: `_LaneClock` 持有 `monotonic_anchor: float` 与 `utc_anchor: datetime` 字段，`now()` 通过 `time.monotonic() - monotonic_anchor` 推导 UTC。此设计的 root cause bug 是 NTP 校正或系统 suspend/resume 后 monotonic anchor 推导的 UTC 与实际 UTC 漂移，导致跨进程 TTL 判断不一致。

**变更后**: `_LaneClock` 无字段（frozen dataclass with `slots=True`），`utc_now()` 直接返回 `datetime.now(UTC)`（lane.py:321-327），`monotonic()` 保持委托 `time.monotonic()`（lane.py:329-335）。

**验证**:
- `utc_now()` 每调用一次即读取真实系统 UTC，不再有进程内 anchor 漂移路径 ✓
- `start()` 返回 `cls()` — 无参构造 frozen dataclass，Python 3.11 下合法 ✓
- 无 `Any` / `object` / 无类型签名；所有 docstring 为中文且覆盖参数/返回值/异常 ✓

### 2. `_try_claim_once_sync()` — 同一事务内复用 bound UTC

**入口**: `_try_claim_once_sync()` (lane.py:579-639)

关键代码路径 (lane.py:588-628):
```python
now = self._clock.utc_now()           # 一次读取真实 UTC
expires_at = now + timedelta(...)      # TTL 基于同一 now
connection.execute("BEGIN IMMEDIATE")
# stale cleanup: expires_at <= _format_datetime(now)  (line 598)
# active count: expires_at > _format_datetime(now)    (line 603)
# insert: created_at/heartbeat_at = _format_datetime(now)  (line 624-625)
#         expires_at = _format_datetime(expires_at)        (line 626)
```

**验证**:
- 同一 `now` 在 stale cleanup、active count、insert 的 `created_at` / `heartbeat_at` / `expires_at` 中复用 ✓
- 即使 wall clock 在 transaction 中途被 NTP 调变，bound value `now` 不变 ✓
- `expires_at` 基于同一 `now + ttl`，保证 stale cleanup 条件与 claim 过期时间一致 ✓
- `_format_datetime()` 保留，ISO-8601 microsecond 格式不变，text 比较语义不变 ✓

### 3. `_refresh_token_sync()` — 同一事务内复用 bound UTC

**入口**: `_refresh_token_sync()` (lane.py:679-719)

关键代码路径 (lane.py:689-706):
```python
now = self._clock.utc_now()           # 一次读取真实 UTC
expires_at = now + timedelta(...)      # 新 TTL 基于同一 now
# UPDATE heartbeat_at = _format_datetime(now)          (line 700)
# UPDATE expires_at = _format_datetime(expires_at)     (line 701)
# WHERE expires_at > _format_datetime(now)            (line 705)
```

**验证**:
- 同一 `now` 值用于 `heartbeat_at`、新 `expires_at` 和旧 claim 有效性判断 ✓
- `expires_at > now` 判断与 `heartbeat_at` 更新使用同一时间基准，避免边界不一致 ✓

### 4. monotonic 仅用于本进程等待 timeout

**所有 monotonic 调用点** (lane.py):

| 行号 | 用途 | 是否参与跨进程 TTL |
|------|------|--------------------|
| 458 | `started_at` — acquire 开始时间 | 否，仅用于本进程 elapsed 计算 |
| 476 | `elapsed_after_claim` — 诊断耗时 | 否 |
| 489 | deadline check — 成功后超时回滚 | 否，仅本进程 |
| 504 | `elapsed_seconds` — TimedOut 诊断 | 否 |
| 507 | deadline check — 重试前超时判断 | 否，仅本进程 |
| 849 | `remaining` — poll 等待时长 | 否，仅本进程 |

**验证**: 没有任何 monotonic 值进入 `_format_datetime()`、SQLite bound parameter、或 `expires_at` 计算 ✓

### 5. 测试有效性

**`test_lane_ttl_uses_real_utc_not_monotonic_elapsed`** (test_lane.py:398-430):
- 场景: acquire 一个 token → monkeypatch `time.monotonic()` 前跳 3600s → 再次 `acquire(timeout_seconds=0)`
- 断言: 返回 `LaneAcquireTimedOut`，`_claim_count == 1`（原 claim 未被误清理）
- 关键: monkeypatch 仅影响 `time.monotonic()`，不影响 `datetime.now(UTC)`；stale cleanup 仍基于真实 UTC 判断 `expires_at`，因此 0.5s TTL 的 claim 不会在 1 小时前跳后被清理
- 验证点完整，覆盖 plan 要求的 "不能清理仍未按真实 UTC 过期的 active claim" ✓

**`test_refresh_uses_real_utc_not_monotonic_elapsed`** (test_lane.py:433-465):
- 场景: acquire token → monkeypatch `time.monotonic()` 前跳 3600s → `token.refresh()`
- 断言: refresh 不抛 `RuntimeLaneClaimLostError`，`token.released is False`，`token.expires_at.tzinfo is UTC`
- 验证点完整，覆盖 plan 要求的 "不应因为 monotonic 前跳而抛 lost" ✓

**测试隔离性**:
- 两个新测试使用 pytest `monkeypatch` fixture，自动恢复 ✓
- `timeout_seconds=0` 路径不进入 `_wait_before_retry`，monkeypatched monotonic 不影响 poll sleep ✓
- 每个测试结尾 `await controller.close(...)` 清理 heartbeat task ✓

**plan 要求保留的已有测试**:
- `test_crashed_holder_is_cleaned_by_ttl_and_other_process_can_acquire` (test_lane_multiprocess.py:283) 在验证中通过（35 passed 包含该测试）✓

### 6. design.md 同步

**变更前** (旧文本):
```
clock 使用 runtime injected / stdlib monotonic-to-wall strategy ...
```

**变更后** (新文本):
```
lane TTL 的 `created_at`、`heartbeat_at`、`expires_at` 与 stale cleanup
判断使用每个 SQLite transaction 前读取的真实 UTC；monotonic 只用于
本进程等待 timeout / deadline 等等待时长计算，不参与跨进程过期判断。
跨进程 clock skew 只能影响 runtime capacity availability，不能影响
Host truth / EventLog / Attempt lifecycle。
```

**验证**:
- `rg -n "monotonic-to-wall|monotonic.*TTL" docs/host/design.md` → 无匹配 ✓
- `rg -n "真实 UTC|datetime.now\(UTC\)|SQLite transaction|本进程等待 timeout" docs/host/design.md` → 4 处匹配，均在 lane 相关段落 ✓
- 三处关键更新 (line 200, 204, 222) 与实现一致 ✓

### 7. tests/README.md 同步

**变更**: lane 覆盖描述新增 "TTL 时间真源不受 monotonic elapsed 前跳影响"
**验证**: 描述准确反映新增的两个测试覆盖范围 ✓

### 8. 架构约束检查

- **Runtime import boundary**: `dayu/runtime/lane.py` 仅 import 标准库 + `dayu.contracts.cancellation.CancellationToken`；无 `dayu.engine/host/service/ui/fins` import ✓
- **Import boundary 测试**: `test_runtime_import_boundary_scan_covers_lane_module` 覆盖 lane.py ✓
- **Schema**: `_CLAIMS_TABLE` 字段、索引无变化 ✓
- **Public API**: `__all__` 无变化；public dataclass/method signature 无变化 ✓
- **中文 docstring**: 所有新增/修改函数有完整中文 docstring，包含参数、返回值、异常 ✓
- **无 Any/object/无类型签名**: `_LaneClock.utc_now() -> datetime`, `_LaneClock.monotonic() -> float`, `_LaneClock.start() -> _LaneClock` ✓
- **无 lazy import / 胶水 seam** ✓
- **无魔法数字**: `_MONOTONIC_FORWARD_JUMP_SECONDS` 作为模块级常量命名清晰 ✓

### 9. Adversarial Failure Pass

- **Wall clock 大幅调快**: claim TTL 可能提前过期 → runtime capacity availability 受影响，但不影响 Host truth。plan 已明确接受此边界 ✓
- **Wall clock 大幅调慢**: stale cleanup 延迟 → 已过期 claim 仍占用 capacity 更久，但不突破 capacity invariant（因为 stale cleanup 和 active count 使用同一 `now` 值）。plan 已明确接受此边界 ✓
- **NTP 逐步校正**: 不再有 monotonic anchor 漂移问题，每次 transaction 读取真实 UTC ✓
- **monotonic 跳变**: 不再影响 TTL 判断，仅影响 `LaneAcquireTimedOut.elapsed_seconds` 诊断值 ✓
- **系统 suspend/resume**: monotonic 不前进但 UTC 前进 → TTL 按真实时间过期，stale cleanup 正常工作 ✓（这正是本修复解决的核心场景）
- **空 claim/lost token/release 幂等**: 不变，不在 Slice 1 scope ✓
- **并发 acquire + TTL 判断**: 不变，`BEGIN IMMEDIATE` + SQLite busy timeout 保护 ✓

## Open Questions

无。

## Residual Risk

- **Wall clock skew**: 系统 wall clock 被人为大幅调快/调慢仍会影响 runtime capacity availability。这是 plan 已明确接受的边界，不属于 Slice 1 未覆盖风险。
- **Slice 2 cancellation cleanup**: 不在本次 review scope；当前外层取消后 `_await_task_after_outer_cancellation()` 仍为无限等待，需在 Slice 2 中修复。
- **`_LaneClock` 无字段后所有实例相等**: frozen dataclass with no fields 产生的 `__eq__` 使所有 clock 实例 `==` 相等。当前 `LaneController` 不依赖 clock equality，无实际影响。若未来需要区分 clock 实例（如 injectable clock），需重新考虑。

## Conclusion: PASS

Slice 1 实现正确修复了 `_LaneClock` 的 monotonic-to-UTC anchor root cause。真实 `datetime.now(UTC)` 在每次 SQLite transaction 前读取一次并在事务内复用，monotonic 仅用于本进程等待 timeout。实现不改变 public API、DB schema、`__all__` 或 runtime import boundary。新增测试有效证明 monotonic 前跳不影响 TTL 判断和 refresh。design.md 与 tests/README.md 同步准确。35 个 lane 测试全部通过，pyright 零错误零警告。未发现 blocking finding。
