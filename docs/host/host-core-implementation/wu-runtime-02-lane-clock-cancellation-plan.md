# WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification Plan

## Gate / Role

- **Gate**: plan
- **Work Unit**: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- **Planning role**: planning specialist；不启动完整 Gateflow，不实现代码，不提交，不 push，不创建 PR。
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Target branch**: `fix/wu-runtime-02-lane-clock-cancellation`
- **Preflight evidence**: 当前分支为 `fix/wu-runtime-02-lane-clock-cancellation`，工作区在 plan 写入前为 clean。

## Goal

保留 `dayu.runtime.lane` 作为层中立、SQLite-backed、跨进程 named semaphore / capacity guard primitive，只收敛两个已由代码证据支撑的 runtime correctness / operability 风险：

1. 跨进程可见 TTL 判断不能继续使用进程内 monotonic anchor 推导的 UTC。
2. 外层取消后等待 shielded SQLite / `to_thread` task 的路径必须有明确上限、失败语义和诊断，不得在极端阻塞时无限等待。

本 plan 不改变 Host 架构、Host durable truth、EventLog、Attempt lifecycle、Host dispatch 使用 lane 的方式或任何财报业务语义。

## Motivation / Severity / Direct Evidence

### 动机判断

动机成立。`lane` 的核心抽象仍成立，问题不在于“是否应该用 lane”，而在于当前实现把两个本应清晰的 runtime 边界混在了一起：

- TTL 是跨进程可见的资源容量可用性判断，必须使用所有进程都能解释的时间真源。
- cancellation cleanup 是调用方取消后的收尾路径，必须能在底层 SQLite / thread 极端阻塞时返回给 caller，并留下可诊断状态。

### 严重性判断

- `_LaneClock` 风险为 **中-高**：它不会污染 Host truth，也不能造成 EventLog / Attempt owner 错误；但它可能提前清理仍被其它进程持有的 runtime capacity claim，或延迟释放已过期 claim，影响多进程 capacity availability 与 provider 并发保护。
- `_await_task_after_outer_cancellation` 风险为 **中**：当前循环中有短 sleep，不是 CPU tight loop；但 caller 已取消后仍可能无限等底层 `to_thread` / SQLite task，缺少上限、失败语义和“后续依赖 TTL cleanup”的诊断。

总控文档对风险没有高估为 Host durable correctness，也没有低估 runtime lane 的生产风险；其定位“保留多进程 named semaphore，修正跨进程 TTL 时间真源和无限等待控制流”准确。

### 直接证据

- `dayu/runtime/lane.py` 中 `_LaneClock.start()` 使用 `time.monotonic()` 与 `datetime.now(UTC)` 建立进程内 anchor，`_LaneClock.now()` 用 monotonic elapsed 推导 UTC。
- `LaneController._try_claim_once_sync()` 使用 `self._clock.now()` 计算 `created_at`、`heartbeat_at`、`expires_at`，并在同一 SQLite transaction 中执行 `expires_at <= now` stale cleanup 与 `expires_at > now` active count。
- `LaneController._refresh_token_sync()` 使用 `self._clock.now()` 更新 `heartbeat_at`、`expires_at`，并用 `expires_at > now` 判断 claim 是否仍有效。
- `_await_task_after_outer_cancellation()` 在 `while True` 中持续 `asyncio.shield(task)`，被 repeated cancel 打断时只 sleep `_OUTER_CANCELLATION_SETTLE_SLEEP_SECONDS` 后继续等待，没有最大等待时间，也没有 timeout diagnostic。
- `tests/runtime/test_lane.py` 已覆盖 repeated cancel cleanup、release / refresh cancel 后等待底层结果、close during slow acquire。
- `tests/runtime/test_lane_multiprocess.py` 已覆盖多进程 capacity invariant、non-blocking timeout、release 后 acquire、crashed holder TTL cleanup。

## Non-goals

- 不把 lane 退化成单进程 semaphore。
- 不用 `FileLock` 替代 SQLite-backed capacity > 1 named semaphore。
- 不引入 Host truth、Host admission、lease / fencing、Attempt owner、EventLog ordering、recovery proof 或 Attempt takeover。
- 不实现 Host dispatch 对 lane 的新使用方式。
- 不改变 runtime lane DB schema。
- 不改变 `LaneConfig`、`LaneOwner`、`SQLiteLaneCoordinatorConfig`、`LaneClaimToken`、`LaneAcquireOutcome`、`LaneController.open()`、`LaneController.acquire()`、`LaneController.close()` 的 public API shape。
- 不处理 `LaneClaimToken.released` 是否仍为 public field；该项虽在 WU-RUNTIME-01 review 中被标记 deferred to WU-RUNTIME-02，但当前 WU 的设计源与用户 handoff 聚焦 clock / cancellation。若 controller 要纳入该 public field 收缩，必须另行进入 public contract 裁决。
- 不新增 callback、factory、profile、query 或 extra payload 式接口。

## Design Decision 1: Cross-process TTL Time Source

### Evaluated options

#### Option A: 真实 UTC wall clock，由 Python 在每次 SQLite 短事务开始时读取

做法：

- 保留 `_LaneClock` 作为私有 clock helper，但把 UTC 方法改为真实 `datetime.now(UTC)`，不再保存 `monotonic_anchor` / `utc_anchor`，不再用 monotonic elapsed 推导 UTC。
- `_try_claim_once_sync()` 与 `_refresh_token_sync()` 在 transaction 前读取一次 `utc_now`，同一事务内用同一个 bound value 做 stale cleanup、active count、insert / update 和 returned `expires_at`。
- `LaneController.acquire()` 的等待 timeout / deadline 继续使用 monotonic。monotonic 只用于本进程等待时长，不参与跨进程 TTL 判断。

优点：

- 直接修复当前 root cause：NTP 校正、系统 suspend / resume 后，进程不会继续使用过期 UTC anchor 推导跨进程 TTL。
- 不改 DB schema，不改 public API，不引入 Host truth。
- SQLite 中仍使用参数绑定的 UTC ISO-8601 字符串，现有索引与文本比较语义保持稳定。
- 测试可以用“monotonic 大幅跳变不影响 active claim TTL 判断”直接证明。

缺点：

- 系统 wall clock 被人为大幅调快时，runtime claim 仍可能提前过期；调慢时，stale cleanup 可能延迟。这是单机 runtime capacity primitive 可接受的 availability 风险，不是 Host truth。

#### Option B: SQLite 时间真源

做法可能包括使用 SQLite `strftime(...)` / `datetime('now', ...)` 在 SQL 内生成 `now` 与 `expires_at`。

优点：

- stale cleanup、active count、insert / update 可在同一个 DB transaction 内从 DB 侧表达时间。

缺点：

- SQLite `now` 仍来自同一台机器的系统 wall clock，不能提供比真实 UTC wall clock 更强的 truth。
- 会把时间格式、精度、TTL 加法和 Python `datetime` parse / format 逻辑推入 SQL，增加维护复杂度。
- 当前 schema 已用 Python ISO-8601 microseconds text；SQLite 时间函数默认格式与 precision 需要额外适配，容易引入 brittle SQL。
- 对本 phase 的核心目标“去掉进程内 monotonic-to-wall anchor”而言过重。

### Selected decision

当前 phase 选择 **Option A: Python 真实 UTC wall clock per SQLite transaction**。

理由：这是最小、可维护、可测试的 root cause 修复。它清除 `_LaneClock` 的进程内 UTC anchor 漂移问题，同时保留 design source 中“clock skew 只影响 runtime capacity availability，不能影响 Host truth”的边界。SQLite 时间真源没有提供足够额外 correctness，却显著增加 SQL / datetime 格式复杂度，因此不作为本 WU 的实现选择。

## Design Decision 2: Outer Cancellation Cleanup Bound

### Selected decision

外层 `Task.cancel()` 已发生后，等待 shielded SQLite / `to_thread` task 的 cleanup path 必须改为 **有界等待**。

具体规则：

- 新增私有常量 `_OUTER_CANCELLATION_CLEANUP_GRACE_SECONDS: Final[float] = 0.25`。
- 新增私有 helper 计算每次 cleanup wait 上限：`coordinator.busy_timeout_seconds + _OUTER_CANCELLATION_CLEANUP_GRACE_SECONDS`。
- `_await_task_after_outer_cancellation()` 改为接收显式 `timeout_seconds: float` 参数。它在 repeated outer cancel 下继续 shield 底层 task，但总等待时间不得超过该 timeout。
- 如果底层 task 在上限内完成，保持现有语义：读取结果或异常，由调用方更新 token / release 状态，并重新抛出最初的 `asyncio.CancelledError`。
- 如果上限内仍未完成，调用方必须保留 `asyncio.CancelledError` 作为对外语义，同时记录 diagnostic，并通过 cause 或日志说明 cleanup 未确认完成。
- 对已可能插入但尚未登记的 claim，cleanup timeout 后不得假装 release 成功；后续依赖 claim TTL 过期与下一次 acquire 的 stale cleanup。
- 对 tracked release timeout，不得把 token 标记为 released；保留 held token，使后续 `release()` / `close()` 可再次尝试，最终仍有 TTL 兜底。
- 对 refresh timeout，不得把 token 标记为 lost 或 released；refresh 结果未知，保留 held token，后续 heartbeat / release / TTL 继续收口。
- 对被放弃等待的 task，必须注册 done callback 或等价 observer，消费 late result / exception，避免未取回异常；若 late claim 成功且未被 release，日志必须说明 claim 将依赖 TTL cleanup。
- cleanup timeout 的内部表达固定为抛出私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`。调用方沿用现有 `RuntimeLaneError` catch pattern 做 diagnostic / TTL fallback / token 状态保留，并始终对外重新抛出最初的 `asyncio.CancelledError`；不得改成返回 timeout outcome 或新增 public API。

### Why not infinite wait

无限等待不能成立。当前 helper 保护的是 runtime SQLite cleanup，不是 Host truth 原子性；在 caller 已取消的场景下，无限等待会把底层阻塞传播成不可取消的 public await。由于 lane claim 本来就有 TTL stale cleanup 作为 crash / orphan 兜底，cleanup timeout 后保留取消语义并记录诊断，比无限等待更符合 runtime primitive 的边界。

## Affected Files / Modules

### Allowed implementation files

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_lane_multiprocess.py`
- `docs/host/design.md`，仅同步 lane clock 表述：跨进程 TTL 使用每个 SQLite transaction 的真实 UTC，monotonic 只用于本进程等待 timeout。
- `tests/README.md`，仅当新增测试覆盖描述与当前 README 不一致时更新。
- `dayu/README.md`，仅当 runtime lane 的稳定职责描述发生变化时更新；本 plan 预期不需要更新。

### Forbidden files for implementation

- `dayu/engine/**`
- `dayu/host/**`
- `dayu/service/**`
- `dayu/ui/**`
- `dayu/fins/**`
- `dayu/config/**`
- Runtime lane 以外的 `dayu/runtime/**`，除非 implementation 发现已有层中立 helper 可直接复用且 plan review 认可。
- 根目录 `README.md`，除非 CLI、配置入口或用户使用方式实际变化；本 plan 预期不需要更新。

Planning specialist 本轮只允许写本 artifact；不得修改上述 implementation / test / README 文件。

## Contract / Schema / Public API

- **Public API**: 不变化。`__all__` 不新增、不删除；public dataclass / method signature 不变化。
- **Runtime DB schema**: 不变化。`runtime_lane_claims` 表字段、主键与索引保持现状。
- **Behavior contract**:
  - `LaneController.acquire()` 仍在 cancellation token 命中时返回 `LaneAcquireCancelled`，在 outer `Task.cancel()` 时透传 `asyncio.CancelledError`。
  - `timeout_seconds=0` 仍表示 non-blocking acquire；正数仍表示 acquire wait 上限；`None` 仍表示无限等待 acquire。
  - TTL stale cleanup 仍只释放 runtime capacity，不证明 Host orphan，不驱动 recovery。
- **Private implementation contract**:
  - `_LaneClock` 不再表达 monotonic-to-UTC anchor；UTC 与 monotonic 用途必须拆清。
  - `_await_task_after_outer_cancellation()` 从无限等待改为显式有界等待。

不做 public contract change 的理由：本 WU 修复的是私有 clock / cleanup control flow；调用方需要的 lane primitive 语义没有变化，改变 public API 会扩大 blast radius，并诱导 implementation agent 处理不属于本 WU 的兼容问题。

## Implementation Slices

### Slice 1: TTL 时间真源改为真实 UTC

- **Objective**: 删除进程内 monotonic anchor 对跨进程 TTL 判断的影响。
- **Allowed files**:
  - `dayu/runtime/lane.py`
  - `tests/runtime/test_lane.py`
  - `tests/runtime/test_lane_multiprocess.py`，仅在现有多进程 TTL 测试需要补强时修改。
  - `tests/README.md`，仅做测试覆盖描述同步。
- **Prerequisites**: 无。
- **Exact changes**:
  - 修改私有 `_LaneClock`：
    - 删除 `monotonic_anchor` / `utc_anchor` 字段。
    - `start()` 返回无 anchor clock。
    - 新增或改名私有 UTC 方法，例如 `utc_now()`，直接返回 `datetime.now(UTC)`。
    - `monotonic()` 保留，只用于 acquire timeout / deadline。
    - 所有新增或修改函数必须有完整中文 docstring，包含参数、返回值、异常。
  - 修改 `_try_claim_once_sync()`：
    - 用真实 UTC 方法读取一次 `now`。
    - `expires_at = now + timedelta(seconds=lane_config.claim_ttl_seconds)`。
    - stale cleanup、active count、insert 均继续使用同一个 formatted `now`。
  - 修改 `_refresh_token_sync()`：
    - 用真实 UTC 方法读取一次 `now`。
    - update 的 `heartbeat_at`、`expires_at` 和 `expires_at > now` 判断均使用同一个 `now`。
  - 保留 `_format_datetime()` 与现有 UTC ISO-8601 text 格式，不改 schema。
  - 同步更新 `docs/host/design.md` 的 lane clock 表述：
    - 将现有 monotonic-to-wall strategy 表述替换为真实 `datetime.now(UTC)` per SQLite transaction。
    - 明确 stale cleanup、active count、claim insert / refresh update 在同一 SQLite transaction 内使用同一个 UTC `now` bound value。
    - 明确 monotonic 仅用于本进程 acquire wait timeout / cleanup wait timeout 等等待时长，不参与跨进程 TTL 判断。
    - 保留“clock skew 只影响 runtime capacity availability，不影响 Host truth / EventLog / Attempt lifecycle”的边界说明。
- **Non-goals**:
  - 不使用 SQLite `CURRENT_TIMESTAMP` / `strftime` 实现 TTL。
  - 不新增可注入 public clock。
  - 不改变 acquire timeout 的 monotonic deadline。
- **Tests**:
  - 新增 `test_lane_ttl_uses_real_utc_not_monotonic_elapsed`：
    - acquire 一个 TTL 尚未过期的 token。
    - monkeypatch `time.monotonic()` 为大幅前跳。
    - 再次 `acquire(..., timeout_seconds=0)` 必须返回 `LaneAcquireTimedOut`，不能清理仍未按真实 UTC 过期的 active claim。
    - release 后 claim count 为 0。
  - 新增 `test_refresh_uses_real_utc_not_monotonic_elapsed`：
    - acquire token 后 monkeypatch `time.monotonic()` 大幅前跳。
    - `token.refresh()` 不应因为 monotonic 前跳而抛 `RuntimeLaneClaimLostError`。
    - refresh 后 `token.expires_at` 必须是 timezone-aware UTC datetime，且 release 正常。
  - 保留并运行现有 `test_crashed_holder_is_cleaned_by_ttl_and_other_process_can_acquire`，证明真实 UTC 仍支持 crash TTL cleanup。
- **Validation commands**:
  - `source .venv/bin/activate`
  - `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
  - `python -m pyright dayu/ tests/ utils/`
- **Docs decision**:
  - `docs/host/design.md` 必须跟随本 WU 实现同步更新 lane clock 表述，避免设计真源继续描述旧的 monotonic-to-wall strategy。
  - `dayu/README.md` 不预期更新，因为 lane 稳定职责未变。
  - `tests/README.md` 若新增测试让 lane 覆盖描述不完整，应把“TTL 时间真源不受 monotonic elapsed 影响”补入 runtime lane 测试说明。
- **Stop condition**:
  - 如果 implementation 发现必须修改 DB schema、public API 或 Host 使用方式才能完成本 slice，停止并交回 controller。

### Slice 2: 外层取消后的 shielded task 等待改为有界等待

- **Objective**: 让 cancellation cleanup path 在底层 thread / SQLite 极端阻塞时有上限、诊断和 TTL fallback，不再无限等待。
- **Allowed files**:
  - `dayu/runtime/lane.py`
  - `tests/runtime/test_lane.py`
  - `tests/README.md`，仅做测试覆盖描述同步。
- **Prerequisites**: Slice 1 完成并通过 lane tests。
- **Exact changes**:
  - 新增私有常量：
    - `_OUTER_CANCELLATION_CLEANUP_GRACE_SECONDS: Final[float] = 0.25`
    - 稳定日志消息常量，例如 claim / release / refresh cleanup timeout 的 warning / error 文案；禁止散落魔法字符串。
  - 新增私有 helper，例如 `_outer_cancellation_cleanup_timeout_seconds(coordinator: SQLiteLaneCoordinatorConfig) -> float`：
    - 返回 `coordinator.busy_timeout_seconds + _OUTER_CANCELLATION_CLEANUP_GRACE_SECONDS`。
    - 完整中文 docstring。
  - 修改 `_await_task_after_outer_cancellation(task, *, timeout_seconds)`：
    - 显式接收 timeout。
    - 使用 monotonic deadline 计算总等待时间。
    - repeated cancel 时继续短 sleep / yield，但不得超过 deadline。
    - timeout 时抛出私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`。
    - 调用方必须沿用现有 `RuntimeLaneError` catch pattern 处理该私有错误，记录 diagnostic / 保留 token 状态 / 依赖 TTL fallback，并重新抛出最初的 `asyncio.CancelledError`。
    - 不得把 timeout 表达为返回 outcome、`None`、布尔值或 extra payload；不得新增 public API。
    - 不取消底层 shielded task。
  - 新增私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`：
    - 仅在 `_await_task_after_outer_cancellation()` 超过 cleanup deadline 时抛出。
    - 类必须提供中文 docstring。
    - 不加入 `__all__`，不向 public contract 暴露。
  - 为被放弃等待的底层 task 添加 private observer：
    - 消费 late result / exception，避免未取回异常。
    - 对 late acquired claim 记录 claim id / lane name，并说明将依赖 TTL cleanup。
    - 对 late release / refresh failure 记录 operation、lane name、claim id 与 error type。
  - 更新调用点：
    - `_try_claim_once()`：claim cleanup wait timeout 后，对外仍抛最初 `CancelledError`；若 claim 可能已插入且未释放，日志说明依赖 TTL cleanup。
    - `_refresh_token()`：refresh cleanup wait timeout 后，对外仍抛最初 `CancelledError`；不标记 token released / lost；记录 diagnostic。
    - `_release_token()`：release cleanup wait timeout 后，对外仍抛最初 `CancelledError`；不标记 token released；保留 held token 供后续 release / close 重试。
    - `_release_untracked_claim()`：release cleanup wait timeout 后，对外仍抛最初 `CancelledError`；记录 TTL fallback diagnostic。
  - 现有“底层在上限内完成”的成功 / lost / RuntimeLaneError 语义保持不变。
- **Non-goals**:
  - 不实现强制杀死 Python thread。
  - 不新增后台 recovery worker。
  - 不把 cleanup timeout 提升成 Host cancel / recovery 事件。
  - 不在 cleanup timeout 后假装 DB release 成功。
- **Tests**:
  - 更新 `test_await_task_after_outer_cancellation_yields_before_retry`，传入显式 timeout，并保留 repeated cancel 下先 yield 再读取最终结果的断言。
  - 新增 helper-level timeout 测试：
    - 底层 task 不完成，outer waiter 被取消，helper 必须在显式 timeout 后结束并暴露 cleanup timeout 语义。
    - 测试不得留下 pending task；测试结束前释放底层 task 或确认 observer 已消费 late result。
  - 新增 public-path claim cleanup timeout 测试：
    - monkeypatch `_try_claim_once_sync` 阻塞超过 cleanup timeout。
    - cancel acquire task。
    - acquire task 必须在有界时间内以 `asyncio.CancelledError` 完成。
    - 日志必须包含 cleanup timeout 与 TTL fallback 文案。
    - 释放阻塞线程后，若 late claim 已插入，后续通过 TTL stale cleanup 或显式检查证明不会永久占用 capacity。
  - 新增 tracked release cleanup timeout 测试：
    - monkeypatch `_release_claim_sync` 阻塞超过 cleanup timeout。
    - cancel `token.release()`。
    - `token.released` 保持 `False`，日志包含 release cleanup timeout。
    - 释放阻塞线程后再次 `token.release()` 或 controller `close()` 能收口；若 DB row 已删除，release 幂等。
  - 保留现有 refresh / release 在底层成功后更新状态的测试，确保有界等待不破坏正常 cleanup。
- **Validation commands**:
  - `source .venv/bin/activate`
  - `pytest tests/runtime/test_lane.py -q`
  - `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
  - `python -m pyright dayu/ tests/ utils/`
  - `! rg -n "monotonic-to-wall|monotonic.*TTL" docs/host/design.md`
  - `rg -n "真实 UTC|datetime.now\\(UTC\\)|SQLite transaction|本进程等待 timeout" docs/host/design.md`
- **Docs decision**:
  - `docs/host/design.md` 的 lane clock 表述应已同步为真实 UTC per SQLite transaction，并明确 monotonic 只用于本进程等待 timeout。
  - `tests/README.md` 应补充 lane 测试覆盖“取消后 cleanup timeout 与 TTL fallback diagnostic”。
  - `dayu/README.md` 不预期更新，因为 runtime lane public capability 未变。
- **Stop condition**:
  - 如果无法在不新增 public API 的前提下表达 cleanup timeout，停止并交回 controller。
  - 如果测试必须依赖不可控 sleep 或留下悬挂 thread / task，停止并重新设计测试同步方式。

## Validation Plan

Implementation 完成后必须在激活虚拟环境后运行：

```bash
source .venv/bin/activate
pytest tests/runtime/test_lane.py -q
pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q
python -m pyright dayu/ tests/ utils/
```

若 implementation 触及 import boundary 或新增 runtime helper 文件，还必须运行：

```bash
source .venv/bin/activate
pytest tests/runtime/test_import_boundary.py -q
```

README 触发判断：

- 修改 runtime lane clock 语义后，必须更新 `docs/host/design.md` 中对应 design source 文字：跨进程 TTL 使用真实 UTC per SQLite transaction；monotonic 只用于本进程等待 timeout；保留 clock skew 仅影响 runtime capacity availability 的边界。
- 修改 `tests/runtime/test_lane.py` / `tests/runtime/test_lane_multiprocess.py` 后，检查 `tests/README.md` 的 lane 覆盖说明；若新增行为未描述，更新该 README。
- 修改 `dayu/runtime/lane.py` 但不改变 runtime lane 稳定职责、public API 或分层关系时，不更新 `dayu/README.md`。
- 不修改根目录 `README.md`，因为本 WU 不改变 CLI、配置入口或用户工作流。

Design source validation:

- `docs/host/design.md` 不得继续把 lane TTL 描述为 monotonic-to-wall strategy。
- `docs/host/design.md` 必须说明 lane TTL 的 `created_at` / `heartbeat_at` / `expires_at` 与 stale cleanup 判断使用真实 UTC per SQLite transaction。
- `docs/host/design.md` 必须说明 monotonic clock 只用于本进程等待 timeout，不参与跨进程 TTL 判断。

## Risks

- **Wall clock jump residual risk**: 真实 UTC 修复 monotonic anchor 漂移，但系统 wall clock 被大幅手动调快 / 调慢仍会影响 runtime capacity availability。该风险符合 design source：lane TTL 不是 Host truth、lease 或 fencing。
- **Cleanup timeout residual risk**: timeout 后底层 thread 可能稍后成功或失败。实现必须通过 observer 消费 late result / exception，并用 TTL cleanup 兜底可能插入但未释放的 claim。
- **Test flakiness risk**: 新 cancellation tests 必须使用 `threading.Event` / explicit timeout config，不得依赖随机 sleep。所有阻塞线程必须在测试结束前释放。
- **Over-scope risk**: 不应顺手重构 `LaneController` 为多个类，也不应处理 `LaneClaimToken.released` public field，除非 controller 重新裁决 scope。

## Open Questions

Blocking open questions: **none**。

Non-blocking note:

- `LaneClaimToken.released` 是否应收缩为非 public lifecycle truth 是独立 public contract 问题；本 plan 明确不处理。若 controller 认为该项必须在 WU-RUNTIME-02 关闭，应先补充 design / control decision，再进入 plan fix。

## Review Gates / Stop Conditions

Plan review 应重点检查：

- 是否真实修复 `_LaneClock` root cause，而不是只改测试或文案。
- 是否避免 SQLite time source 的过度复杂化。
- 是否给 cancellation cleanup 提供了明确上限、失败语义、diagnostic 和 TTL fallback。
- 是否保持 runtime import boundary，不引入 Host / Engine / Service / UI / Fins 依赖。
- 是否没有 public API / schema drift。
- 是否测试覆盖 failure path，而不只覆盖 happy path。

Implementation agent 必须停止并报告 controller 的情况：

- 需要修改 public API、DB schema、Host usage 或 README 职责边界。
- 新增 pyright error 或触及已有 pyright error 且无法一并修复。
- cancellation cleanup timeout 设计无法避免 pending task exception 泄漏。
- 多进程 TTL test 暴露 capacity invariant 回归。

## Completion Report Format

Implementation / fix 完成时按以下格式报告：

```markdown
## WU-RUNTIME-02 Completion Report

- Gate:
- Slice:
- Changed files:
- Implemented plan items:
- Contract / schema / public API changes:
- Tests updated:
- README decision:
- Validation:
  - `pytest tests/runtime/test_lane.py -q`:
  - `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`:
  - `python -m pyright dayu/ tests/ utils/`:
- Residual risks:
- Open questions:
- Stop status:
```
