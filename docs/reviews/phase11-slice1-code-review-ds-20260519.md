# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase-11-recovery
- Base: 9223cbf (Phase 11 accepted plan commit)
- Output file: docs/reviews/phase11-slice1-code-review-ds-20260519.md
- Included scope: Phase 11 Slice 1 uncommitted workspace changes (5 modified files + 2 new files)
- Excluded scope: Engine/, Service/, UI/, Fins/, schema changes (all confirmed untouched)
- Parallel review coverage: 无
- Review date: 2026-05-19
- Reference plan: docs/host/phase11-host-lifecycle-recovery-plan.md Slice 1
- Reference implementation artifact: docs/reviews/phase11-slice1-implementation-codex-20260519.md

### Changed files

- `dayu/host/durable/liveness.py` — tightened `_REGISTER_RUNNING_SOURCE_STATUSES` to `(RUNNING,)` only
- `dayu/host/recovery_process.py` — new: typed process probe, orphan classifier foundation
- `dayu/host/dispatch.py` — Host instance identity, heartbeat lifecycle, close ordering
- `tests/host/test_host_instance_liveness.py` — removed STOPPING→RUNNING assertion, added STOPPING conflict test, added token entropy test
- `tests/host/test_recovery_orphan_classifier.py` — new: 12 classifier tests + 2 stdlib probe tests
- `dayu/host/README.md` — narrow docs update for liveness + classifier semantics
- `docs/host/implementation-control.md` — gate fact append only

## Findings

### 1-未修复-中-heartbeat close 场景下的竞态误导错误日志

- **入口/函数**: `HostDispatchScheduler._host_instance_heartbeat_loop` → `heartbeat_current_instance`
- **文件(行号)**: `dayu/host/dispatch.py:1610-1622`、`dayu/host/durable/liveness.py:274-299`
- **输入场景**: `close()` 的 `_best_effort_mark_host_instance_stopping` 已将 host instance row 推进到 `STOPPING`，但 heartbeat task 尚未被 cancel（即 heartbeat task 从 `asyncio.sleep` 唤醒时 `_closed` 仍为 `False`，随后在 `_refresh_current_host_instance_heartbeat` 的 sync 执行期间 `close()` 将 `_closed` 设为 `True` 并标记 `STOPPING`）。
- **实际分支**: `heartbeat_current_instance` 的 `UPDATE WHERE status IN ('running')` 命中 0 行 → `_require_single_liveness_update` → `_raise_liveness_update_conflict` → `current.status not in _HEARTBEAT_SOURCE_STATUSES` → 抛出 `HostInstanceLifecycleConflictError` → 被 heartbeat loop 的 `except Exception` 捕获（行 1610），日志写为 `"dispatch.host_instance_heartbeat.fatal_exit"` 并再次调用 `_best_effort_mark_host_instance_stopping("heartbeat_fatal_exit")`。
- **预期行为**: 同一 event loop 内，`close()` 在 `_closed = True` 后第一个 `await` 之前不会 yield，heartbeat task 不可能在 `close()` 标记 STOPPING 和 cancel heartbeat task 之间得到执行机会。因此这个分支在当前 asyncio 单线程模型下实际不可达。
- **实际行为**: 代码路径不可达，但存在防御性代码将正常的生命周期冲突误标记为 `fatal_exit`。若未来重构为多线程或 `run_in_executor`，死代码会被激活并产生误导性错误日志。
- **直接证据**: `close()` 行 1537-1551：`self._closed = True`（sync）后紧接着 `self._best_effort_mark_host_instance_stopping("scheduler_close")`（sync），两者之间的 Python bytecode 执行不包含 yield point；heartbeat task 的 `asyncio.sleep` 在同一个 event loop 上，在 close() yield 之前不可能被调度。
- **影响**: 当前行为正确，但 `except Exception` 的 catch-all 语义过宽，将逻辑上不应在此出现的 `HostInstanceLifecycleConflictError` 当作 fatal 处理。如果未来 heartbeat 的 refresh 因其他合法原因抛出非 retryable 异常（如 identity conflict），也会被错误地标记为 STOPPING 并终止 heartbeat loop。
- **建议改法和验证点**: 将 `heartbeat_current_instance` 可能抛出的已知生命周期异常（`HostInstanceLifecycleConflictError`、`HostInstanceNotRegisteredError`）与真正未知 fatal 异常区分处理。在 except 分支中，对已知 lifecycle 异常仅 log warning 并 continue（不终止 loop），对未知异常保持当前 fatal-exit 行为。同时建议缩小 `except Exception` 为更具体的异常类型。
- **修复风险（低）**: 改动只影响 heartbeat loop 的异常分类，不改变 durable write 语义。
- **严重程度（中）**: 当前行为正确但异常分类语义不精确，死代码路径在架构演进时可能激活。

### 2-未修复-低-heartbeat 间隔硬编码为模块级私有常量

- **入口/函数**: `HostDispatchScheduler._host_instance_heartbeat_loop`
- **文件(行号)**: `dayu/host/dispatch.py:189`（`_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS = 1.0`）
- **输入场景**: 所有 scheduler open 路径。
- **实际分支**: 始终生效。
- **预期行为**: heartbeat 间隔应可由上层策略或 recovery stale threshold 反推，而不是硬编码 1 秒。
- **实际行为**: 每秒执行一次 durable write transaction 刷新 heartbeat row。
- **直接证据**: 行 189 `_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS = 1.0`，行 1594 `await asyncio.sleep(_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS)`。
- **影响**: 每秒 1 次 durable write；若 stale threshold 在 Slice 2 设为 30s，1s 间隔过于激进；若 threshold 设为 3s，1s 间隔合理。当前无法根据部署场景调整。
- **建议改法和验证点**: Slice 2 实现 stale threshold 时同步引入 interval 的可配置性（如从 `HostLocalExecutionOptions` 或 policy 派生），当前 Slice 1 不作为 blocker。
- **修复风险（低）**: 属于参数化，不影响语义。
- **严重程度（低）**: Plan 明确将 heartbeat interval 与 stale threshold 的关系留给后续 slice，当前硬编码值符合 "小于 stale threshold" 的约束。

### 3-未修复-低-`_validate_policy` 中 timezone 检查冗余

- **入口/函数**: `classify_orphan_candidate` → `_validate_policy`
- **文件(行号)**: `dayu/host/recovery_process.py:377-378`
- **输入场景**: 所有 classifier 调用路径。
- **实际分支**: 始终生效。
- **预期行为**: 单一、非冗余的 timezone 检查。
- **实际行为**: `policy.now.tzinfo is None or policy.now.utcoffset() is None` —— `utcoffset()` 在 `tzinfo is None` 时一定返回 `None`，第二个条件在该场景下完全冗余。
- **直接证据**: 行 377-378。CPython `datetime.utcoffset()` 实现：若 `tzinfo is None`，返回 `None`。
- **影响**: 不影响行为；代码可读性轻微下降。
- **建议改法和验证点**: 移除 `or policy.now.utcoffset() is None`，或改为单独检查 `policy.now.tzinfo is None`。若目的是防御非标准 tzinfo 实现，应在注释中说明。
- **修复风险（低）**: 纯清理。
- **严重程度（低）**: 不影响正确性，不阻塞 merge。

## Focus Area Verification

### Liveness STOPPING 不可重新注册 RUNNING

**PASS** — `_REGISTER_RUNNING_SOURCE_STATUSES` 已从 `(RUNNING, STOPPING)` 收紧为 `(RUNNING,)`（`dayu/host/durable/liveness.py:42-44`）。`register_current_instance` 的 CAS UPDATE 只匹配 `status IN ('running')`（行 225-231），STOPPING 行会命中 0 行 → `_raise_liveness_update_conflict` 检测 `current.status not in allowed_source_statuses` → `HostInstanceLifecycleConflictError`。测试 `test_stopping_instance_register_does_not_revert_to_running` 直接验证：register 在 STOPPING 行上抛出 `HostInstanceLifecycleConflictError`，且 durable row 保持 `STOPPING`。terminal status (`STOPPED`, `CRASHED_SUSPECTED`) 同样被 `_TERMINAL_STATUSES` 检查拦截（行 220-223）。

### process_start_token 高熵且与 host_instance_id 分离

**PASS** — `_new_dispatch_host_instance_identity`（`dayu/host/dispatch.py:3111-3128`）使用 `uuid4().hex` 生成 `process_start_token`，与 `host_instance_id=host_handle_id` 完全分离。LaneOwner 的 `process_start_token` 同步使用该 token（行 577）。测试 `test_dispatch_host_instance_identity_uses_high_entropy_token` 验证：token 不等于 handle_id、不等于旧 `dispatch-{handle_id}` 模式、两次调用生成不同值、长度 32 字符、合法 hex。

### heartbeat task 失败/关闭行为

**PASS with observation** — Heartbeat loop（`dayu/host/dispatch.py:1585-1630`）：
- `HostTransactionRetryExhaustedError` → warning log + continue（行 1599-1609）：符合 plan "单次 refresh 异常可按 policy 继续重试"
- 非 retry Exception → error log + best-effort mark STOPPING + return（行 1610-1622）：符合 plan "heartbeat task fatal exit 必须 best-effort 标记 STOPPING"
- `asyncio.CancelledError` → debug log + re-raise（行 1623-1630）
- close() 顺序：`_closed=True` → mark STOPPING → cancel heartbeat task → cancel drain/promotion → cancel workers → close lane → mark STOPPED：符合 plan "close 先 mark stopping，关闭 scheduler / lane / workers 后 best-effort mark stopped"
- 见 Finding 1 关于 `except Exception` catch-all 语义的观察。

### orphan classifier truth source 与 typed outputs

**PASS** — `classify_orphan_candidate`（`dayu/host/recovery_process.py:200-257`）接受 `DurableOrphanCandidate`（durable owner + liveness row）、`ProcessEvidence | None` 和 `OrphanClassificationPolicy`，返回 `PositiveOrphanProof | OwnerStillLive | OrphanProofInconclusive` 的 typed union。所有返回类型均为 `@dataclass(frozen=True, slots=True)`。分类决策树覆盖 13 条分支：missing owner、missing liveness、owner not RUNNING、heartbeat parse fail、heartbeat recent、stale + no evidence、stale + pid mismatch、stale + probe error、stale + pid missing → positive proof、stale + start_token mismatch → positive proof、stale + boot_id mismatch → positive proof、stale + start_token match → still live、stale + pid live without identity → inconclusive。heartbeat stale 单独不构成 positive proof（行 156-168 测试直接验证）。Plan §5 "classifier 不写数据库" 已确认——classifier 无任何 DB 访问。

### 无 DB writes in classifier

**PASS** — `recovery_process.py` 的所有函数（`classify_orphan_candidate`、`_classify_stale_owner`、`_positive_orphan_proof`、`_validate_policy`）只进行参数校验、时间比较和 dataclass 构造，无任何 DB 读写。模块 import 仅限于 `dayu.host.durable.codec.parse_utc_timestamp` 和 `dayu.host.durable.liveness.HostInstanceRow/HostInstanceStatus`。

### 无 Engine/public API/schema 变更

**PASS** — 变更文件全部在 `dayu/host/` 和 `tests/host/` 内。`recovery_process.py` 不 import Engine/Service/UI。`dispatch.py` 已有的 Engine import（`dayu.engine.contracts.engine_events`）为 dispatch 既有依赖，本次未新增。`HostInstanceIdentity`、`HostInstanceRow`、`HostInstanceStatus` 的 dataclass 定义未变更字段。无 public API 新增。public `HostDispatchScheduler.open()` signature 未变。`open_host` 未修改。

### 测试/文档充分性

**PASS** — 30 个 focused tests（17 liveness + 13 orphan classifier）+ 1 个 regression test 全部通过。测试覆盖：STOPPING 不可回刷 RUNNING、terminal 不可复活、RUNNING 幂等刷新、classifier 全部 13 条分支、stdlib probe 正常/异常路径、token 高熵验证。`dayu/host/README.md` 新增 2 句精确描述 liveness heartbeat 与只读 orphan classifier 语义，不超前描述 Slice 2/3 内容。`docs/host/implementation-control.md` gate 事实追加仅记录进度，不修改设计。

### pyright/docstring/type 约束

**PASS** — `pyright dayu/host tests/host` 返回 `0 errors, 0 warnings, 0 informations`。所有新增函数/方法提供完整中文 docstring（含 param/returns/raises）。所有新增类型为 `@dataclass(frozen=True, slots=True)` 或 `Protocol`。无 `Any`、无 `object`、无 `hasattr`/`getattr`。`git diff --check` 无输出。

## Open Questions

无。

## Residual Risk

- **heartbeat 间隔可配置性**（Finding 2）：当前硬编码 1.0s，在 stale threshold 较大的部署场景下产生不必要的 durable write 压力。Slice 2 引入 stale threshold 时应同步解决。
- **classifier 的 pid-reuse proof 依赖平台能力**：`StdlibPidLivenessProbe` 只能证明 pid 是否存在，无法观察 `start_token` 或 `boot_id`。在 pid 复用且旧 owner 与新 owner pid 相同的场景下，classifier 返回 `OrphanProofInconclusive`（行 333-339），正确但不完整。plan 明确将此列为 deferred，需要平台级 process fingerprint 能力。
- **heartbeat loop 异常分类精度**（Finding 1）：`except Exception` catch-all 过于宽泛，未来若新增合法非 retryable 异常类型可能被误终止。
- **heartbeat task 仅在 `open()` 时创建**：若未来有 `open()` 之外的 scheduler 激活路径（如 reopen after close），`_start_host_instance_heartbeat` 需要被显式调用。当前 `close()` 不可逆，不构成实际风险。
- **recovery_process.py 的 `ProcessLivenessProbe` Protocol**：当前只有 `StdlibPidLivenessProbe` 一个实现，且不提供 `observed_start_token`/`observed_boot_id`。classifier 的分支 10/11（start_token mismatch / boot_id mismatch）在当前实现中不可达，仅在更强的 probe 实现接入后可激活。这不影响正确性，classifier 的设计预留了扩展点。

## Conclusion

PASS — blocking count 0。

Phase 11 Slice 1 实现与 accepted plan (`9223cbf` + `docs/host/phase11-host-lifecycle-recovery-plan.md` Slice 1) 精确对齐。五项 correctness 逐项验证通过：STOPPING 不可回刷 RUNNING、`process_start_token` 高熵且独立、heartbeat close 顺序正确、orphan classifier truth source 正确且 typed outputs 完整、无 DB writes in classifier、无 Engine/public API/schema 变更。30 focused tests + 1 regression test 全部通过，pyright 0 errors，docstring/type 约束满足 CLAUDE.md 要求。

3 项 non-blocking findings 均为低/中严重度，不影响 Slice 1 merge。建议在 Slice 2 实现时同步收口 heartbeat interval 可配置性和异常分类精度。
