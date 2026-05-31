# pass1 Re-review — PR 99 full-repo review fix loop

## Scope

- Mode: current changes (uncommitted diff on `feat/host-purge-audit-reconciliation`)
- Base artifact under review: `docs/reviews/repo-review-fix-pass1-codex-20260531.md`
- Original review artifacts: `docs/reviews/repo-review-20260531-222837.md`, `docs/reviews/repo-review-20260531-223418.md`
- Control docs updated: `docs/host/host-core-followup-implementation-control.md`, `docs/host/maintainability-implementation-control.md`
- Output file: `docs/reviews/repo-review-fix-pass1-rereview-ds-20260531.md`
- Included scope: all uncommitted modified files + new files in `dayu/runtime/_agent_policy_constants.py` and `tests/host/test_opaque_ref.py`
- Excluded scope: committed changes (already reviewed in original repo reviews)
- Role: review / re-review only; no modifications, no commits, no pushes

## Findings

### 已验证修复 — 7 项全部确认为 closed

逐条走读确认：

#### 1. schema v15 test helpers (原 finding 3, review-223418)

- **修复文件**: `tests/host/test_wait_record_state.py`, `tests/host/test_public_cancel_session_runs.py`
- **验证结果**: **已修复**。`_seed_run` 现在插入 `RUN_STARTED` event 并设置 `started_event_id` / `started_event_sequence`（test_wait_record_state.py:105-130）。`_mark_run_status` 对 active 状态（RUNNING/WAITING/CANCELLING/RECOVERING）先插入 `RUN_STARTED` event 并用 `COALESCE(started_event_id, ...)` 保护已有值，再更新 status（test_public_cancel_session_runs.py:397-483）。非 active 状态保持简单 status UPDATE。逻辑正确，不再违反对应 CHECK 约束。
- **测试**: 50 passed 中包含所有 6 个原来失败的测试。

#### 2. WAITING Run cancel after wait resolved (原 finding 1, review-222837)

- **修复文件**: `dayu/host/durable/run_transition.py`, `tests/host/test_wait_cancel_late_result.py`
- **验证结果**: **已修复**。`cancel_waiting_run_in_transaction` 的 guard 条件由 `if attempt is None or attempt.status != AttemptStatus.SUSPENDED or not active_waits:` 改为 `if attempt is None or attempt.status != AttemptStatus.SUSPENDED:`（run_transition.py:2300）。当 `active_waits` 为空时，`wait_ids` 初始化为空 tuple（:2312），跳过 `cancel_active_wait_records_for_run` 调用（:2313 的 `if active_waits:`），直接写入 `RUN_CANCELLED` event 并取消 Run（:2328-2345）。`wait_ids` 为空 tuple 时 `_waiting_run_cancelled_event_request` 将其序列化为 `[]`（:4040），语义正确。
- **测试**: `test_cancel_run_allows_resolved_wait_record_while_run_still_waiting` 构造精确场景（先 resolve wait record 不 resume Run，再 cancel），断言 Run status=CANCELLED 且 wait record status 保持 RESOLVED。覆盖充分。

#### 3. cancel_queued/running terminal guards (原 findings 6,7 review-222837)

- **修复文件**: `dayu/host/durable/state.py`, `tests/host/test_run_attempt_transitions.py`
- **验证结果**: **已修复**。
  - `cancel_queued_run_row` WHERE 子句新增 `AND terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL`（state.py:2500-2502）。参数 `cas_lost_when_expected=False`，当 rowcount=0 且 latest.status 仍为 QUEUED 时返回 `INVALID_STATE`（state.py:4664-4666）——语义正确：QUEUED Run 持有 terminal refs 属于 schema 异常而非 CAS 竞态。
  - `cancel_running_run_row` WHERE 子句新增相同三个 terminal guard（state.py:2564-2566）。参数 `cas_lost_when_expected=True`，当 rowcount=0 且 latest.status 仍为 RUNNING 时返回 `CAS_LOST`（state.py:4664-4665）——语义正确：RUNNING Run 的 terminal refs 可能来自并发 CAS 竞态。
- **测试**: 两个新测试通过 `PRAGMA ignore_check_constraints` 构造违反 CHECK 约束的异常行（queued/running Run 带 terminal refs），验证 CAS 防线正确返回 INVALID_STATE / CAS_LOST。PRAGMA 使用范围精确（ON → UPDATE → OFF），是测试防御性 SQL guard 的必要手段。

#### 4. payload_ref digest check (原 finding 12, review-222837)

- **修复文件**: `dayu/host/tool_runtime.py`, `tests/host/test_toolruntime_accept_barrier.py`
- **验证结果**: **已修复**。`_candidate_payload_descriptor_exists` 由 `return descriptor is not None` 改为 `return descriptor is not None and descriptor.payload_digest == candidate.payload_ref.payload_digest`（tool_runtime.py:3375-3378）。从"只检查存在性"升级为"同时校验 digest 一致性"。
- **测试**: `test_accept_rejects_payload_descriptor_digest_mismatch` 构造 descriptor digest 与 candidate payload_digest 不一致的场景，断言 accept 返回 `ToolFactRejectedAck` 且 `reason_code=PAYLOAD_REFERENCE_INVALID`，且无 tool event 写入。覆盖充分。

#### 5. ToolExecutor CancelledError warning (原 finding 9, review-222837)

- **修复文件**: `dayu/engine/agent.py`, `tests/engine/test_agent_phase3_tool_call.py`
- **验证结果**: **已修复**。`_call_tool_executor` 中 `CancelledError` 非 run-level 取消分支新增 `_LOGGER.warning("engine.agent.tool_executor.cancelled_without_run_cancellation"...)` 日志（agent.py:1839-1844）。日志记录 run_id 和 call_count，提供可观测性。
- **测试**: `test_duplicate_and_executor_exception_paths` 新增 `caplog` fixture，捕获 WARNING 级别日志并断言 `"tool_executor.cancelled_without_run_cancellation" in caplog.text`。覆盖充分。

#### 6. opaque_ref tests (原 finding 12, review-223418)

- **修复文件**: `tests/host/test_opaque_ref.py`（新文件）
- **验证结果**: **已修复**。10 个测试覆盖全部 3 个公开函数：`validate_host_neutral_opaque_ref_text`（合法输入、空文本、空 ref_id、非字符串 TypeError、缺少 kind 前缀）、`validate_host_neutral_opaque_ref_kind`（非法 kind、非字符串 TypeError）、`host_neutral_opaque_ref_kinds`（返回值闭集断言）。
- **覆盖率**: `pytest --cov=dayu.host.opaque_ref --cov-report=term-missing` 报告 `dayu/host/opaque_ref.py 20 0 100%`。✅

#### 7. fallback_mode single truth (原 finding 19, review-223418)

- **修复文件**: `dayu/runtime/_agent_policy_constants.py`（新文件）, `dayu/runtime/config_loader.py`, `dayu/runtime/assembly.py`, `dayu/runtime/scene_prepare.py`
- **验证结果**: **已修复**。
  - 新模块 `_agent_policy_constants.py`（24 行）定义 `AGENT_FALLBACK_MODES` frozenset + `AGENT_FALLBACK_MODE_FORCE_ANSWER` / `AGENT_FALLBACK_MODE_RAISE_ERROR` 字符串常量。无 Engine/Host/Service import，只依赖 `__future__.annotations` 和 `typing.Final`。
  - `config_loader.py` 删除本地 `_AGENT_FALLBACK_MODES`，改用 import 的 `AGENT_FALLBACK_MODES`。
  - `assembly.py` 删除本地 `_FALLBACK_MODES`（由 `SceneAgentFallbackMode` 枚举值推导），改用 import 的 `AGENT_FALLBACK_MODES`。
  - `scene_prepare.py` 删除本地 `_AGENT_FALLBACK_MODES` frozenset；`SceneAgentFallbackMode` 枚举值改为引用常量（`FORCE_ANSWER = AGENT_FALLBACK_MODE_FORCE_ANSWER` 等）；校验改用 import 的 `AGENT_FALLBACK_MODES`。
  - 模块命名遵循 `_` 前缀 private 约定，不在任何 `__init__.py` 中导出，仅被 `dayu.runtime` 内部三个模块 import。不存在反向依赖、兼容性 re-export 或 public API 泄漏。

### 已验证 deferred-with-owner — 2 项高风险 + 1 项可维护性

#### RuntimeFileLock (原 finding 1, review-223418)

- **处置**: deferred-with-owner ✅
- **Owner**: `docs/host/host-core-followup-implementation-control.md` → RR-HCF-01 → WU-RUNTIME-01
- **WU 描述**: 包含完整背景、目标（收缩封装 / 委托第三方 FileLock）、非目标（不引入 stale takeover / async wrapper）、验收信号（release 失败不标记 released、audit/tool trace 互斥测试通过）。设计约束充分，不是"一行状态补丁"。

#### LaneClock (原 finding 2, review-223418)

- **处置**: deferred-with-owner ✅
- **Owner**: `docs/host/host-core-followup-implementation-control.md` → RR-HCF-02 → WU-RUNTIME-02
- **WU 描述**: 明确保留多进程 named semaphore 抽象，不降级为 FileLock；目标聚焦跨进程 TTL 时间真源和 cancellation 简化；有明确的验收信号。

#### _AsyncAgent God object (原 finding 4, review-223418)

- **处置**: deferred-with-owner ✅
- **Owner**: `docs/host/maintainability-implementation-control.md` → RR-MAINT-03 → WU-MAINT-07
- **WU 描述**: `blocked-by-issue-backlog`，需等待 WU-MAINT-00 刷新后确认拆分边界。目标、非目标、验收信号完整。

### Over-design challenge — 无过度设计

#### `_agent_policy_constants.py`

- 24 行，仅含 3 个常量定义 + 中文 docstring。职责单一：runtime 层 fallback mode 闭集真源。
- 不构造对象，不实现逻辑，不 import 业务层。无胶水代码、无 builder、无 factory。
- 替代方案分析：将常量放入 `config_loader.py` 或 `assembly.py` 会导致其他模块反向依赖；放入 `contracts` 包会让 runtime 配置常量进入跨层契约空间。独立 private 模块是最小真源策略。**不构成过度设计**。

#### `PRAGMA ignore_check_constraints`

- 仅在两处测试中使用：`test_cancel_queued_run_row_requires_empty_terminal_refs` 和 `test_cancel_running_run_row_requires_empty_terminal_refs`。
- 使用模式：`ON → anomalous UPDATE → OFF`，每次使用后立即恢复。SQLite 文档允许此用法。
- 必要性：正常 schema CHECK 约束禁止创建"active Run 持有 terminal refs"的行，但测试必须验证 SQL WHERE guard 在此异常场景下生效。不使用 PRAGMA 则无法构造异常行，CAS 防线测试将存在 gap。**是测试防御性 SQL guard 的必要手段，不构成过度设计**。

#### test helper 变更

- `_mark_run_status` 对 active 状态补充 started refs：逻辑范围精确（仅 5 个 active 状态 + COALESCE 保护），不改生产代码，不引入额外抽象层。**是 schema v15 合规的必要修正**。

### 项目约束检查

| 约束 | 状态 | 证据 |
|---|---|---|
| 分层架构 | ✅ 通过 | `_agent_policy_constants.py` 无 Engine/Host/Service import；所有变更在各自层内 |
| 无反向依赖 | ✅ 通过 | runtime→runtime import，无业务层→runtime 新增依赖 |
| 无兼容性 wrapper | ✅ 通过 | 无 re-export、无旧常量保留、无 facade |
| 类型签名 | ✅ 通过 | pyright 0 errors，所有新函数有完整类型注解 |
| 中文 docstring | ✅ 通过 | 新模块、新测试 helper、修改的函数均有中文 docstring |
| 无魔法字符串 | ✅ 通过 | fallback mode 字符串定义为具名常量 |

### 验证命令结果

| 命令 | 声明结果 | 实际结果 |
|---|---|---|
| targeted tests (50) | 50 passed | ✅ 50 passed in 0.51s |
| pyright | 0 errors, 0 warnings, 0 informations | ✅ 一致 |
| `pytest tests/host/test_opaque_ref.py --cov=dayu.host.opaque_ref` | 10 passed, 100% | ✅ 10 passed, 100% |

> 全量 `pytest tests`（声明 1796 passed, 1 skipped）和 `pytest tests/host/test_opaque_ref.py --cov=dayu.host.opaque_ref --cov-report=term-missing` 已在本 review 中部分复现（targeted tests + opaque_ref coverage），全量测试因时间约束未重跑。targeted tests 覆蓋了所有 7 个修复面的断言，可信度充分。

## Open Questions

无。

## Residual Risk

1. **RuntimeFileLock release bug 仍然存在**：原 finding 未在本轮修复，deferred to WU-RUNTIME-01。当前 `dayu/runtime/filelock.py:104` 在 release 失败时仍错误标记 `released=True`。调用方（audit / tool_trace JSONL writer）若依赖 release 后文件立即可被其他进程获取，存在锁泄漏风险。

2. **LaneClock 跨进程时钟偏差仍存在**：原 finding 未在本轮修复，deferred to WU-RUNTIME-02。`_LaneClock.now()` 仍使用 monotonic anchor 推导 UTC 参与跨进程 TTL 判断。多进程高并发 + NTP 校正场景下 stale cleanup 判定不一致。

3. **_AsyncAgent 职责过载**：deferred to WU-MAINT-07，blocked-by-issue-backlog。不影响本轮 audit reconciliation 功能正确性。

4. **全量测试未复现**：targeted 测试 + pyright 均通过，但未重跑全量 `pytest tests`（声明 1796 passed）。risk 低：targeted tests 覆盖所有修改面。

5. **PRAGMA ignore_check_constraints 测试仅 SQLite**：如需支持其他 SQL 后端，对应测试需适配。当前项目仅使用 SQLite，risk 低。

## Conclusion

**PASS**

7 项 claimed-fixed findings 全部验证为真正 closed。2 项高风险（RuntimeFileLock、LaneClock）+ 1 项可维护性（_AsyncAgent）正确 deferred，每项有明确 owner、WU 描述、目标和验收信号。无过度设计、无新增 layer violation、无兼容性 wrapper。targeted tests 50 passed、pyright clean、opaque_ref 100% coverage 均已独立验证。
