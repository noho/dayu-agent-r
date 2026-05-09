# Host P8-S7 Code Review：Deterministic Multiprocessing 与 Observer Drain 验证

- **Branch**: `migration/host-p8-attempt-lease-recovery`
- **Baseline**: `9aa8446 docs: add p8 durable memory recovery slice`
- **Review date**: 2026-05-09
- **Reviewer**: Host P8-S7 Code Review Agent (Claude)
- **Review scope**: P8-S7 entry 工作树差异（仅测试 + 三份 README/plan）

## 结论：CONDITIONALLY PASSED — F1 fixed, awaiting re-review

P8-S7 slice 严格落在测试与文档边界内，未触动任何 host 生产代码、未自动 wire
`recover_stale_attempts`、未实现 P8-S8 durable memory rebuild、未引入 observer claim/lease，
四类多进程测试与 helper 的契约语义、断言强度、隔离边界均符合 plan 与 amendment-rereview。
`pytest tests/host -q` 284 passed，`pytest tests/host/test_phase8_multiprocess_stress.py -q`
4 passed (1.54s)，`python -m pyright dayu/host tests/host` 0 errors，`git diff --check`
clean。

但仍有 1 项硬约束违反（lazy import without justification）必须先修，1 项弱覆盖建议待评估。
F1 修复后允许进入 user confirmation + commit gate。

---

## 验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 多进程压力测试 | `pytest tests/host/test_phase8_multiprocess_stress.py -q` | 4 passed in 1.54s |
| P8 既有 host 测试集 | `pytest tests/host/test_phase8_attempt_recovery.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_tool_runtime_fencing.py -q` | 23 passed |
| Host 全量回归 | `pytest tests/host -q` | 284 passed |
| 类型检查 | `python -m pyright dayu/host tests/host` | 0 errors / 0 warnings / 0 informations |
| 空白错误 | `git diff --check` | clean |

---

## Slice 边界审查（依次复核 1～8）

### 1. Slice 边界

- ✅ 工作树差异：`tests/host/_multiprocess_platform.py` (新增)、`tests/host/test_phase8_multiprocess_stress.py` (新增)、`tests/README.md`、`dayu/host/README.md`、`docs/host/migration-plan.md` 均为文档/测试。`git status --short` 无 `dayu/host/*.py` 改动。
- ✅ helper 落在 `tests/host/_multiprocess_platform.py`（下划线前缀私有）；module docstring 显式声明“不进入生产路径……不允许调用方直接持有 …… 不引入 host 生产代码”（`_multiprocess_platform.py:1-30`）。
- ✅ `recover_stale_attempts` 未被 wire 到 `build_durable_harness`：`docs/host/migration-plan.md` diff 把该项 owner 改为 `P9 / Session lifecycle`，`dayu/host/_durable_harness.py` 未变更。
- ✅ 未触动 `_conversation_memory.py`，未删除 `InMemoryConversationMemoryStore`，durable memory store 保留为 P8-S8 scope；测试场景 4 docstring 与 `tests/README.md` 显式声明“不声称 in-memory `ConversationMemoryStore` 具备生产级崩溃恢复”。
- ✅ 未实现 P9 admission / public lifecycle、未引入 observer claim / lease（搜索 `observer claim` 仅出现在文档说明中）。
- ✅ 不依赖外部 provider / 网络服务；测试只用文件 SQLite。
- ✅ owner secret 仅在测试进程之间通过 `WorkerSpec.args` 序列化传递，未写入 EventLog、未写入日志、未写入 README；payload `{"fenced": True, "reason": ...}` 仅含 typed 枚举值；`secret_a` 来自 supervisor 真实生成，`secret_b` 由 `AttemptOwnerToken.new()` 现场生成。

### 2. Multiprocessing helper

- ✅ Spawn-only：`SPAWN_CONTEXT_NAME = "spawn"`，`get_spawn_context()` 用 `multiprocessing.get_context("spawn")` 并 `assert isinstance(ctx, SpawnContext)` 守住 (`_multiprocess_platform.py:46-152`)。
- ✅ Module-level worker：`WorkerSpec.target: Callable[..., None]` + module docstring 明确禁止 closures；测试侧四个 worker 均为模块级函数（`_worker_append_events`、`_worker_terminal_close`、`_worker_acquire_and_exit`、`_worker_recover`、`_worker_write_terminal_no_drain`、`_worker_startup_reconcile`）。
- ✅ 集中封装：start method、join timeout、terminate→kill 升级、exitcode 判定、traceback 文本回传、Queue/Barrier、temp DB path 全部收敛在 `run_workers` / `assert_clean_exit` / `temp_database_path` / `make_barrier`，测试主体没有任何 `set_start_method`、裸 `join(timeout)`、重复 cleanup 路径。
- ✅ 命名常量：`SPAWN_CONTEXT_NAME` / `DEFAULT_JOIN_TIMEOUT_SECONDS=30.0` / `_TERMINATE_GRACE_SECONDS=5.0` / `_KILL_GRACE_SECONDS=5.0` / `_RESULT_KIND_OK` / `_RESULT_KIND_ERROR` / `_DATABASE_FILE_NAME`；测试侧 `_LEASE_TTL_SECONDS=30` / `_LEASE_RENEW_INTERVAL_SECONDS=10` / `_EVENTS_PER_WORKER=5` / `_APPEND_WORKER_COUNT=4` / `_OWNER_PREFIX`；无裸魔法数字控 race 时序。
- ✅ 子进程不共享 `HostStorage` / SQLite connection / event loop：每个 worker 内部 `storage = HostStorage(database_path=...)` + `try/finally storage.close()` + `asyncio.run(_do())`，主进程的 `HostStorage` 在 `_bootstrap_database` 后 `close()`。

### 3. 跨进程 EventLog append 测试

- ✅ 真实文件 SQLite：`temp_database_path(tmp_path)` 走 `tmp_path / "host.db"`；未使用 `:memory:`。
- ✅ 4 个独立子进程，每个打开独立 `HostStorage` 与独立 `DurableRunEventStore`。
- ✅ 断言 (`test_cross_process_append_preserves_cursor_and_position` 第 263–308 行)：
  - `len(rows) == _APPEND_WORKER_COUNT * _EVENTS_PER_WORKER` （20 行）；
  - `positions == sorted(set(positions))` 严格唯一单调；
  - `sequences == list(range(20))` per-run cursor 形成 0..19 完整置换；
  - 每个 worker 自身回报的序列单调递增且无重复。
- ✅ 不靠未命名 sleep：用 spawn-context `Barrier(parties=4)` 让 worker 在 `append` 前对齐进入 race 区段；同步点确定性。

### 4. Terminal race 测试

- ✅ 真实多进程：两个进程持有相同 `attempt_id` / 相同 fencing token，但 `secret_a` / `secret_b` 是两个独立 owner secret；只有 `secret_a` 的 hash 在 `host_attempts.owner_token_hash`。
- ✅ Winner / loser：`winners = [o for o in outcomes if not o.result["fenced"]]`、`len(winners) == 1`、`len(losers) == 1`；loser payload `{"fenced": True, "reason": exc.reason.value, ...}` 收口为 typed `AttemptFencingError(OWNER_MISMATCH)`，进程不崩溃、退出码 0。
- ✅ 断言 `host_run_events` 中 `terminal=1` 行恰好 1 条，`type == FINAL_ANSWER.value`，`event_position` 与 winner payload 一致；EventLog 不残留 stale terminal。
- ✅ `host_attempts.terminal_event_position == winner.event_position`、`host_runs.terminal_event_position == winner.event_position`、`host_runs.state == SUCCEEDED`，三处同源。
- ✅ `fencing_token` 写回 `host_attempts` 严格等于 winner 的 fencing token。
- ✅ owner secret 仅在 worker 局部 `_OwnerContext` 内使用，不进入 payload 也不进入断言文本。

### 5. Stale recovery 测试

- ✅ 真实多进程：进程 A `_worker_acquire_and_exit` 进入 `lease_context` 抓 lease 后退出（不写 terminal），进程 B `_worker_recover` 调 `recover_stale_attempts`。
- ✅ 主进程 `_expire_attempt_lease` 直接 `UPDATE host_attempts SET lease_expires_at = ?` 把 lease 推到过去；`_expire_attempt_lease` docstring 明确“跨进程注入 fake clock 不可行……P8-S7 task brief 明确允许在测试事务内推进 ``lease_expires_at`` 字段”——deterministic trigger 标注清楚，不会被误读为生产路径。
- ✅ 断言：
  - `decision.action == "mark_recovering_and_create_attempt"`，`reason == "lease_expired_recovery_started"`；
  - `host_attempts` 共 2 行；旧 attempt `state == RECOVERING`、新 attempt `state == RUNNING`；
  - `new_row["recovered_from_attempt_id"] == old_attempt_id`；
  - `new_row["fencing_token"] > old_fencing_token`（严格更大）；
  - `new_attempt_index == old_attempt_index + 1`；
  - `host_run_events` 行数 = 0（recovery scan 不写诊断 RunEvent）；
  - 阶段 4：用 `secret_old` + `_FencingToken(value=old_fencing_token)` 构造 late append，`pytest.raises(AttemptFencingError)` 命中。
- ✅ 不 takeover 同一 attempt：新行使用全新 `attempt_id` / `attempt_index` / `fencing_token` / `recovered_from_attempt_id`。

### 6. Observer drain / startup_reconcile 测试

- ✅ 仅断言 EventLog tail / `host_projection_checkpoints.last_success_position` / `status == "caught_up"`；不读 `ConversationMemoryStore` 内容、不构造 user-facing memory snapshot 断言。
- ✅ 测试 docstring 显式列出“**不**声称、也不验证”三项均归 P8-S8（in-memory store 崩溃恢复 / durable store 实现 / checkpoint-aware rebuild）。
- ✅ 重复 `startup_reconcile` 幂等：第二次调用后 `last_success_position` 与第一次相等。
- ✅ 期望的 observer 集合：`host_memory_projection`、`host_timeline_projection`、`host_audit_projection`，且全部 `last_success_position == tail`。
- ✅ 多进程链路：进程 A 写 user_input + delta + final_answer 但不 drain；进程 B 通过 `build_durable_harness` 起 fresh harness 后 `startup_reconcile`，验证 checkpoint 在新进程内能从 EventLog tail 追平——证明既有 SQLite checkpoint CAS 已足以跨进程，无需 observer claim / lease。
- ⚠ 仅测“顺序 writer→reconciler”+“同进程内重复 reconcile 幂等”，未直接测“两个进程**并发**调用 startup_reconcile”这种最强场景；见 F2。

### 7. S7/S8 residual risk 与文档

- ✅ `docs/host/migration-plan.md`：原 `deferred-with-owner: P8-S7` 改为 `completed: P8-S7`，措辞精确（“不引入 multiprocessing launcher / process supervisor 生产代码”、“不解决 durable conversation memory read model rebuild”、“durable memory recovery 划入 P8-S8”），慢硬盘 + Docker Linux stress 仍归 issue #38。`AttemptSupervisor.recover_stale_attempts` 自动 wire 改归 `P9 / Session lifecycle`，未越界写到 P8-S7 完成项。
- ✅ `dayu/host/README.md`：在原“自动装配时机由 P8-S7 决定”一行改成“仍未在生产链路落地”，并显式列出 startup_reconcile 验证仅触达 `host_projection_checkpoints` 既有语义、durable memory recovery 仍属 P8-S8。未把 S8 / P9 写成已落地。
- ✅ `tests/README.md`：明确 helper 是 `tests/host/_multiprocess_platform.py` 私有，spawn-only / module-level worker / typed traceback / `terminate -> kill` / 不用 `time.sleep` / 不用 `:memory:`；场景 4 显式声明“仅验证 EventLog / projection checkpoint / `startup_reconcile` 既有语义……durable memory store + checkpoint-aware rebuild 已划入 P8-S8 scope”。
- ✅ S8 删除 production `InMemoryConversationMemoryStore` 的边界仍由 `migration-plan.md` `deferred-with-owner: P8-S8` 条目保留，未被 S7 文档覆盖或冲掉。

### 8. 类型、稳定性、平台兼容

- ✅ Pyright clean：`dayu/host tests/host` 0 errors。
- ✅ macOS 上 `pytest tests/host/test_phase8_multiprocess_stress.py` 1.54s 内稳定通过；helper 强制 spawn 与 Linux 行为一致，不依赖 fork 副作用。
- ✅ `DEFAULT_JOIN_TIMEOUT_SECONDS=30.0` 给慢机充足余量；超时后 `terminate()` + 5s grace + `kill()` + 5s grace + `RuntimeError`，不会留下 zombie process。
- ✅ traceback 通过 spawn-context `Queue` 文本回传，不靠 exit code 推断；worker 内 `report_error(context, exc=exc)` 不会吞掉 traceback。
- ✅ 所有新增函数/类/模块均含完整中文 docstring（参数、返回值、异常）；`WorkerSpec` / `WorkerContext` / `WorkerOutcome` 字段级 docstring 完整；测试侧 helper（`_utc`、`_SystemUtcClock`、`_content_draft`、`_final_draft`、`_seed_run_row`、`_bootstrap_database`、`_create_running_attempt_synchronously`、`_expire_attempt_lease`、各 `_worker_*`）docstring 齐全。
- ⚠ `Any` 用法：仅出现在 `WorkerSpec.args: tuple[Any, ...]` / `WorkerOutcome.result` / `_MpQueue[tuple[str, str, Any]]` / 测试侧 worker 返回 `dict[str, Any]`。这些是 IPC payload 必须容纳异构 pickle-able 数据的合法位置；测试主体在断言侧用 `isinstance(payload, list/dict)` + 字段访问做边界收口。判定：**可接受，不形成 finding**——但如果未来 P8-S8 还要扩展 helper，建议演进为 `WorkerSpec[T]` / `WorkerOutcome[T]` 泛型，避免 `Any` 进一步扩散。

---

## Findings

### F1 — 严重: LOW｜状态: accepted — fixed｜required fix

**Evidence**

- `tests/host/test_phase8_multiprocess_stress.py:431-436` `_worker_terminal_close` 内 lazy import `AttemptOwnerContext as _OwnerContext` / `FencingToken as _FencingToken`；
- `tests/host/test_phase8_multiprocess_stress.py:822-827` 测试主体 `test_cross_process_stale_recovery_preserves_typed_decision` 阶段 4 同样 lazy import 这两个符号；
- `tests/host/test_phase8_multiprocess_stress.py:887` `_worker_write_terminal_no_drain` 内 lazy import `UserInputAcceptedData, UserInputScope`。

**Impact**

CLAUDE.md 编码硬约束明确：“禁止胶水 seam，使用lazy import必须有充分理由”。这三处 lazy import
均无技术必要：

- spawn 子进程会重新 import 该模块，模块 top-level imports 一定会执行；worker 内再 import 不会带来更小的启动开销；
- 这两个 worker 已在 top-level imports 里使用了同模块的其它符号（`AttemptOwnerToken`、`AttemptFencingError`、`AttemptLeaseConfig` 等），lazy import 没有规避循环依赖、也没有规避可选依赖；
- 阶段 4 的 lazy import 出现在测试主体 (test 函数体内)，更没有任何 spawn 边界理由。

实际效果是把符号引用从模块 top 推到调用点，制造“胶水 seam”，违反硬约束并增加阅读成本。

**Required fix**

把以下三个符号集中提升到 `tests/host/test_phase8_multiprocess_stress.py` 顶部 imports：

- `from dayu.host._attempt_lease import AttemptOwnerContext`
- `from dayu.host._internal_contracts import FencingToken`
- `from dayu.host.contracts import UserInputAcceptedData, UserInputScope`

并删除 `_worker_terminal_close` / `_worker_write_terminal_no_drain` / 阶段 4 测试体内的内嵌 import；
内部别名 `_OwnerContext` / `_FencingToken` 直接改用其原名，避免冗余 alias。修复后重跑
`pytest tests/host/test_phase8_multiprocess_stress.py -q` + `python -m pyright dayu/host tests/host`
确认仍然全绿。

**修复说明** (2026-05-09): 已将 `AttemptOwnerContext`、`FencingToken`、`UserInputAcceptedData`、
`UserInputScope` 提升到模块顶部 imports；删除了 `_worker_terminal_close`、
`test_cross_process_stale_recovery_preserves_typed_decision` 阶段 4、
`_worker_write_terminal_no_drain` 三处 lazy import；内部别名 `_OwnerContext` /
`_FencingToken` 全量替换为原名。

---

### F2 — 严重: LOW｜状态: deferred-with-owner: P8-S8 / P9｜advisory

**Evidence**

- `tests/host/test_phase8_multiprocess_stress.py:992-1094` `test_observer_drain_catches_up_after_cross_process_terminal`
  顺序运行 writer 子进程、然后单个 reconciler 子进程；reconciler 内部连续两次 `startup_reconcile`，
  第二次只验证“同进程内幂等”。
- 实际未启动 **两个 reconciler 子进程并发**调用 `startup_reconcile`；plan 第 770–783 行写
  “确认 P8 不需要 observer claim / lease”。

**Impact**

`ProjectionCoordinator.drain` 仅有进程内 `_drain_lock`（见 `dayu/host/_event_observer.py`），跨进程
serialization 必须依赖 SQLite WAL + checkpoint 行级 CAS。当前测试通过“先写 + 再起 fresh 进程
reconcile + 同进程二次幂等”间接证明跨进程 catch-up 与本进程幂等成立，但不直接覆盖
“两个进程同时进入 `drain()` 是否会双写 / 重复落 projection”。这是 plan 的弱化覆盖，不是
实施偏离 plan：S7 plan 的“四类场景”就已写成 `observer drain` 而非 `concurrent drain`。

**Deferred owner**

记录为 P8-S8 / P9 advisory：

- 若 P8-S8 落地 durable `ConversationMemoryStore` 后 drain/projection 写入面变大，应在 S8 增量补
  “两个 reconciler 并发”这一场景；
- 若 P9 把 `recover_stale_attempts` 自动 wire 进 `build_durable_harness` 起 host 时也会自动触发
  `startup_reconcile`，则在 P9 一并加并发 drain 测试。

S7 范围内不强制补；plan 已通过 amendment-rereview，不再回写 plan。

---

## Residual Risks 与 Owner

| Risk | Owner | 备注 |
|------|-------|------|
| Durable `ConversationMemoryStore` 缺失，进程崩溃后 caught-up checkpoint 仍可能丢 in-memory snapshot | P8-S8 | `migration-plan.md` 已固定为 `deferred-with-owner: P8-S8`；本 slice 测试场景 4 明确不验证此项 |
| `AttemptSupervisor.recover_stale_attempts` 未自动接入 `build_durable_harness` / Session lifecycle | P9 / Session lifecycle | `migration-plan.md` 已从 `P8-S7` 移交到 `P9 / Session lifecycle` |
| 慢硬盘 + Docker Linux 重压版多进程 stress | issue #38 | plan + migration-plan 一致保留 |
| 两个进程并发 `startup_reconcile` 是否安全 | P8-S8 / P9 advisory | 见 F2，本 slice 不强制补 |
| `tests/host/_multiprocess_platform.py` 中 `WorkerSpec.args: tuple[Any, ...]` / `WorkerOutcome.result: Any` / IPC Queue 含 `Any` | 后续 helper 演进 | 当前合理；如果 helper 被多 slice 复用，再评估 generic 化以避免 `Any` 扩散 |
| 测试 fake `_SystemUtcClock` 与生产 clock 边界 | P16 / interface freeze | 已在 P8-S6 review 中登记“`AttemptSupervisorPort` 抽 protocol”项，不再重复 |

---

## 建议

1. **先修 F1**（lazy import → module-level import），重跑 `pytest tests/host/test_phase8_multiprocess_stress.py -q` + `python -m pyright dayu/host tests/host`，确认仍然全绿后即可进入 user confirmation + commit。
2. F2 不阻塞本 slice，作为 P8-S8 / P9 advisory 记录在 residual risks。
3. 不需要回写 `phase8-plan.md` / `migration-plan.md`；本 slice 的文档同步在 `dayu/host/README.md` / `tests/README.md` / `migration-plan.md` 三处已完成。
