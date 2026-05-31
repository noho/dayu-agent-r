# Code Review

## Scope

- Mode: current changes (unstaged workspace changes)
- Branch: fix/wu-runtime-02-lane-clock-cancellation
- Base: main
- Output file: docs/reviews/wu-runtime-02-code-review-slice1-mimo-20260601.md
- Included scope:
  - `dayu/runtime/lane.py` - `_LaneClock` 类改动、`_try_claim_once_sync()` 和 `_refresh_token_sync()` 的 UTC 时间真源改动
  - `tests/runtime/test_lane.py` - 新增两个 monotonic 前跳回归测试
  - `docs/host/design.md` - lane clock 表述同步
  - `tests/README.md` - lane 测试覆盖描述同步
  - `docs/reviews/wu-runtime-02-implementation-slice1-codex-20260601.md` - implementation artifact
- Excluded scope:
  - `docs/host/host-core-followup-implementation-control.md` - controller bookkeeping，不在 code review scope
  - Slice 2 的 `_await_task_after_outer_cancellation` 有界等待改动

## Findings

未发现实质性问题。

### 验证结果

1. **测试验证**: `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q` - 35 passed in 1.46s
2. **类型检查**: `pyright dayu/runtime/lane.py tests/runtime/test_lane.py` - 0 errors, 0 warnings, 0 informations
3. **design.md 同步验证**:
   - `rg -n "monotonic-to-wall|monotonic.*TTL" docs/host/design.md` - 无匹配，旧表述已清除
   - `rg -n "真实 UTC|datetime.now\(UTC\)|SQLite transaction|本进程等待 timeout" docs/host/design.md` - 匹配到新增的 UTC 相关表述

### 实现正确性审查

**`_LaneClock` 类改动 (lane.py:304-336)**:
- 删除 `monotonic_anchor` / `utc_anchor` 字段，`start()` 返回空实例 ✓
- `utc_now()` 直接返回 `datetime.now(UTC)`，不再基于 monotonic elapsed 推导 ✓
- `monotonic()` 保留，语义明确为本进程 timeout / deadline 计算 ✓
- 类保持 `frozen=True, slots=True`，空 dataclass 合法 ✓

**`_try_claim_once_sync()` 改动 (lane.py:579-639)**:
- 在 SQLite 事务前读取 `now = self._clock.utc_now()` ✓
- 同一事务内复用 `now` 做 stale cleanup (`expires_at <= now`)、active count (`expires_at > now`)、insert (`created_at`, `heartbeat_at`, `expires_at`) ✓
- 符合 plan "每个 SQLite transaction 开始前通过 `datetime.now(UTC)` 读取一次真实 UTC `now`，并在同一短事务内复用同一个 bound value" ✓

**`_refresh_token_sync()` 改动 (lane.py:679-719)**:
- 在 SQLite 事务前读取 `now = self._clock.utc_now()` ✓
- 同一事务内复用 `now` 做 `heartbeat_at`、`expires_at` 更新和 `expires_at > now` 判断 ✓
- 符合 plan "每次 refresh 在 SQLite transaction 开始前读取一次真实 UTC `now`，并在同一事务内复用同一个 bound value" ✓

**单调性保证**:
- `utc_now()` 每次调用返回真实 UTC，不存在进程内 anchor 漂移风险 ✓
- monotonic 只用于 `_acquire()` 中的 `deadline = self._clock.monotonic() + timeout_seconds` 等待时长计算 ✓

### 测试有效性审查

**`test_lane_ttl_uses_real_utc_not_monotonic_elapsed` (test_lane.py:399-430)**:
- 场景: acquire 后 monkeypatch `time.monotonic()` 前跳 3600 秒
- 验证: 再次 `acquire(..., timeout_seconds=0)` 返回 `LaneAcquireTimedOut`，claim count 仍为 1
- 证明: monotonic 前跳不会误清理真实 UTC 尚未过期的 active claim ✓
- 释放验证: `held.token.release()` 后 claim count 为 0 ✓

**`test_refresh_uses_real_utc_not_monotonic_elapsed` (test_lane.py:434-465)**:
- 场景: acquire 后 monkeypatch `time.monotonic()` 前跳 3600 秒
- 验证: `token.refresh()` 不抛 `RuntimeLaneClaimLostError`
- 证明: refresh 不会因 monotonic 前跳误判 claim lost ✓
- 附加验证: `token.expires_at.tzinfo is UTC`，确认 timezone-aware ✓

**monkeypatch 隔离性**:
- `monkeypatch.setattr(lane_module.time, "monotonic", jumped_monotonic)` 只影响 `dayu.runtime.lane` 模块的 `time.monotonic` 引用，不影响其他模块 ✓

### AGENTS 约束审查

1. **中文 docstring**: 所有新增/修改函数均有完整中文 docstring，包含参数、返回值 ✓
2. **类型签名**: 无 `Any`、`object`、无类型参数或返回值 ✓
3. **runtime import boundary**: `lane.py` 只导入标准库和 `dayu.contracts.cancellation`，未导入 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` ✓
4. **schema / public API**: 无变化，`__all__` 未修改，`LaneClaimToken`、`LaneController` 等 public 接口签名不变 ✓
5. **魔法数字/字符串**: 新增常量 `_MONOTONIC_FORWARD_JUMP_SECONDS` 在测试中，命名清晰 ✓

### design.md 同步审查

- 旧表述 "monotonic-to-wall strategy" 已完全清除 ✓
- 新表述明确 "每个 SQLite transaction 开始前通过 `datetime.now(UTC)` 读取一次真实 UTC `now`" ✓
- 新表述明确 "monotonic 只用于本进程等待 timeout / deadline 等等待时长计算，不参与跨进程过期判断" ✓
- 保留 "clock skew 只影响 runtime capacity availability，不能影响 Host truth / EventLog / Attempt lifecycle" 边界说明 ✓

### tests/README.md 同步审查

- lane 测试覆盖描述已补充 "TTL 时间真源不受 monotonic elapsed 前跳影响" ✓
- 描述准确反映新增测试的覆盖范围 ✓

## Open Questions

无。

## Residual Risk

1. **系统 wall clock skew**: 真实 UTC 修复了 monotonic anchor 漂移，但系统 wall clock 被人为大幅调快/调慢仍会影响 runtime capacity availability。这是 plan 中明确接受的边界，不影响 Host truth / EventLog / Attempt lifecycle。

2. **Slice 2 未实现**: `_await_task_after_outer_cancellation` 仍使用无限等待，caller 已取消后可能无限等底层 `to_thread` / SQLite task。这是 Slice 2 的范围，不属于本次 review scope。

## Conclusion

**PASS**

Slice 1 实现完全符合 approved plan (`docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`) 的要求：
- `_LaneClock` root cause 已修复，删除进程内 monotonic-to-UTC anchor
- UTC 时间真源改为每个 SQLite transaction 前读取真实 `datetime.now(UTC)`
- monotonic 只用于本进程 timeout / deadline 等待时长计算
- 测试有效覆盖 monotonic 前跳不影响 TTL 判断和 refresh 的场景
- design.md 和 tests/README.md 已同步更新
- 未违反 AGENTS 约束
- 无 blocking finding
