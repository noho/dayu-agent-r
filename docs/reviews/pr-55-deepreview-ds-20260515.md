# PR 55 Deep Review — AgentDS

- **Review type**: adversarial PR-level deep review (AgentDS independent)
- **Review date**: 2026-05-15
- **Repository**: noho/dayu-agent-r
- **PR**: [#55](https://github.com/noho/dayu-agent-r/pull/55)
- **Title**: Host Phase 6 ToolRuntime governance
- **Author**: noho
- **Branch**: `feat/host-phase-6-toolruntime`
- **Base**: `main`
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Prior aggregate review**: PASS (P6-AGG-F1 fixed, re-review DS/MiMo both PASS)
- **Verdict**: PASS — 无阻塞级发现；2 项中等发现、若干低严重度发现与残余风险

## Scope

### Changed files

| File | Role |
|------|------|
| `dayu/host/tool_runtime.py` | Phase 6 核心: EffectiveToolBundle, accept barrier, truncation/fetch_more, duplicate governance, diagnostics, ToolRuntimeExecutor, Factory |
| `dayu/host/dispatch.py` | Scheduler 集成: registry 创建/注入/清理 |
| `dayu/host/run_input.py` | RunInputBuilder provider wiring |
| `dayu/host/api.py` | `HostLocalExecutionOptions` tooling 字段 |
| `docs/host/design.md` | Run-local duplicate governance 语义澄清 |
| `docs/host/implementation-control.md` | Phase 6 exit standard |
| `dayu/README.md` | 术语表更新 (TruncationManager, cursor, scope_token, fetch_more) |
| `dayu/host/README.md` | ToolRuntime 架构文档更新 |
| `tests/README.md` | 测试覆盖文档更新 |
| `tests/host/test_toolruntime_*.py` (7 files) | 专项测试 |
| `tests/host/test_dispatch_scheduler.py` | Scheduler 集成测试 |
| `tests/host/test_run_input_builder.py` | RunInputBuilder provider 测试 |
| `tests/host/test_phase6_toolruntime_integration.py` | 跨组件集成测试 |

### Verification baseline

| Item | Result |
|------|--------|
| `pytest tests/host -q` | 349 passed |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

### Parallel review coverage

| Subagent | Scope | Coverage |
|----------|-------|----------|
| Duplicate governance registry | `tool_runtime.py:910-1712`, `dispatch.py:290-1026`, `test_toolruntime_duplicate_governance.py` | 完整覆盖 |
| Truncation/fetch_more | `tool_runtime.py:1194-1465, 3470-3847`, `test_toolruntime_truncation_fetch_more.py` | 完整覆盖 |
| Accept barrier / executor | `tool_runtime.py:1788-2503, 4105-4600`, `test_toolruntime_accept_barrier.py`, `test_toolruntime_executor.py` | 完整覆盖 |
| Architecture / overcoupling | 全模块 import 分析，README diff，边界检查 | 完整覆盖 |

---

## Findings

### PR55-DS-1-未修复-中-`_accept_with_retry` 的 `except TimeoutError` 是死代码，且 `HostTransactionRetryExhaustedError` 会未处理传播

- **入口/函数**: `ToolRuntimeExecutor._accept_with_retry`
- **文件(行号)**: `dayu/host/tool_runtime.py:2468-2476`
- **输入场景**: accept barrier 内部通过 `run_write` 提交事务，SQLite busy retry 耗尽时抛出 `HostTransactionRetryExhaustedError`（继承自 `HostDurableError`，非 `TimeoutError`）。
- **实际分支**: `tool_runtime.py:2470` 的 `except TimeoutError` 在 Python 标准库语义下只能捕获内置 `TimeoutError`，不会捕获 `HostTransactionRetryExhaustedError`。`accept_tool_fact()` 是同步方法，其内部 `run_write` 不会抛出 `TimeoutError`。
- **预期行为**: 事务重试耗尽后应产生可恢复的 `ToolFactAcceptTimedOut`，使调用方能感知超时并决定后续策略。
- **实际行为**: `HostTransactionRetryExhaustedError` 穿透 `_accept_with_retry` 向上传播至 `_execute_one:2305`，使工具执行 crash 而非返回 governed error。
- **直接证据**:
  1. `tool_runtime.py:2470` — `except TimeoutError:` 匹配的异常类型与实际 SQLite busy retry 抛出的异常类型不一致。
  2. `dayu/host/durable/transaction.py` — `HostTransactionRetryExhaustedError` 继承链为 `Exception` → `HostDurableError` → `HostTransactionRetryExhaustedError`，不是 `TimeoutError` 子类。
  3. 整个 `_accept_with_retry` 方法体中无 `except HostTransactionRetryExhaustedError` 或其他 `HostDurableError` 子类捕获。
- **影响**: 在高并发 / SQLite 竞争激烈时，accept barrier 重试无法正常降级为 timed out ack，导致工具调用异常终止。
- **建议改法和验证点**:
  1. 将 `except TimeoutError` 替换为 `except (HostDurableError, TimeoutError)` 或在 `except TimeoutError` 外增加对 `HostTransactionRetryExhaustedError` 的捕获。
  2. 新增测试用例模拟事务重试耗尽场景。
- **修复风险（低）**: 仅扩展异常捕获范围，不影响正常路径。
- **严重程度（中）**: 当前默认 `backoff_seconds=0`、`max_attempts=2`，且 SQLite busy retry 配置充足时实际不易触发；但在极端负载下可能暴露，属于防御缺失。

### PR55-DS-2-未修复-中-fetch_more 的 single-use cursor 标记存在 TOCTOU 竞态窗口

- **入口/函数**: `TruncationManager.fetch_more`
- **文件(行号)**: `dayu/host/tool_runtime.py:1358-1378`
- **输入场景**: 两个并发的 `fetch_more` 调用使用同一个 cursor。
- **实际分支**: 两个并发调用同时在 `tool_runtime.py:1358` 查找到 cursor，`tool_runtime.py:1364` 的 `_validate_cursor` 对两个调用都返回 `None`（`used_at` 仍为 `None`），两个调用随后都执行 `_fetch_more_value`，然后都在 `tool_runtime.py:1375` 写入 `used_at`（后者覆盖前者）。
- **预期行为**: 只允许一次 `fetch_more` 成功，第二次应返回 `cursor_already_used` 错误。
- **实际行为**: `_cursors` dict（`tool_runtime.py:1263`）无锁保护，查找-验证-标记是三步非原子操作。两个并发请求可能在步骤 2 都通过 `used_at` 检查。
- **直接证据**:
  1. `tool_runtime.py:1358` — `cursor = self._cursors.get(request.cursor)` 无锁。
  2. `tool_runtime.py:1364` — `validation_failure = self._validate_cursor(...)` 检查 `used_at`。
  3. `tool_runtime.py:1374-1375` — `used_at` 标记写入在验证之后，且不在同一临界区。
  4. `TruncationManager.__init__` (`tool_runtime.py:1254-1263`) 不持有任何锁实例。
- **影响**: Phase 6 当前工具调用为严格串行（`_execute_one` 逐个处理 batch），因此当前不可被实际触发。若后续 phase 引入并发工具调用，此窗口将成为真实漏洞。
- **建议改法和验证点**:
  1. 在 `fetch_more` 方法中为 cursor 查找-验证-标记引入 `threading.Lock`，或将标记逻辑改为 check-and-set 原子模式。
  2. 或在 `_validate_cursor` 返回 `None` 后立即原子标记（如在 `_cursors` 写入前再次检查 `used_at`）。
- **修复风险（低）**: 引入锁仅影响 `fetch_more` 路径，对主工具执行路径无影响。
- **严重程度（中）**: 当前不可被利用，但作为并发正确性隐患，应在引入并发工具调用前修复。

### PR55-DS-3-未修复-低-`_consume_worker_events` 中对已终态 Run 的新 Attempt 可能导致 registry state 残留

- **入口/函数**: `HostDispatchScheduler._consume_worker_events`
- **文件(行号)**: `dayu/host/dispatch.py:927-1006`
- **输入场景**: 一个已 terminal closeout 的 Run 被再次 dispatch（如竞态窗口或 admission 时序问题）。
- **实际分支**: 新 Attempt 通过 `duplicate_governance_for_run` 创建新的 `_RunLocalDuplicateGovernanceState`（`tool_runtime.py:1665-1689`）。worker event stream 中所有事件被 ingest 为 `DUPLICATE`（Run 已终态），`ingestor.close_clean_eof` 返回的 `terminal_closeout` 为 `False`（因为终端关闭事件已在上一 Attempt 中发出）。`_ingest_closed_run` 返回 `False`，`run_terminal_closed` 保持 `False`。
- **预期行为**: 新 Attempt 终态后应清理其创建的 duplicate state。
- **实际行为**: `run_terminal_closed` 为 `False`，`finally` 块中 `clear_run` 不被调用，新创建的 `_RunLocalDuplicateGovernanceState` 留在 `_states_by_run_id` 中。
- **直接证据**:
  1. `dispatch.py:927` — `run_terminal_closed = False`。
  2. `dispatch.py:958` — `close_clean_eof` 对已终态 Run 返回的 `terminal_closeout` 为 `False`（无新关闭事件）。
  3. `dispatch.py:1004-1006` — `if run_terminal_closed:` 门控跳过 `clear_run`。
  4. `dispatch.py:1016-1026` — `_ingest_closed_run` 要求 `terminal_closeout=True` 且 status 为 `ACCEPTED`/`DUPLICATE`。
- **影响**: 每个此类异常 Attempt 泄露一个 `_RunLocalDuplicateGovernanceState` 对象（含空 dict + RLock）。`scheduler.close()` 的 `clear_all()` 提供最终兜底。对于长运行期 Host 实例且 admission 反复误 dispatch 已终态 Run 的极端情况下，会缓慢累积。
- **建议改法和验证点**: 在 `finally` 块中对 `_consume_worker_events` 增加兜底逻辑：无论 `run_terminal_closed` 是否为 True，若 `_states_by_run_id` 中存在该 `run_id` 且对应 state 为空（无 entries），则清理。或保持现状，依赖 `close()` 的 `clear_all()` 兜底。
- **修复风险（低）**: 可保守处理——仅在 state 无实际 entries 时才兜底清理。
- **严重程度（低）**: 触发条件极端，且有 scheduler close 兜底；每个泄漏对象极小（空 dict + RLock）。

### PR55-DS-4-未修复-低-截断结果 target_field 为 JSON null 时被静默跳过

- **入口/函数**: `_select_truncation_value` / `_value_at_path`
- **文件(行号)**: `dayu/host/tool_runtime.py:3563-3566, 3582-3585`
- **输入场景**: 工具返回 `{"result": null, "metadata": "..."}` 且 `ToolTruncateSpec.target_field="result"`。
- **实际分支**: `value.get(spec.target_field)` 返回 `None`，`if selected is None: return None` （`tool_runtime.py:3565-3566`）将 `null` 值与 key missing 同等处理。截断跳过，完整结果直接返回给 LLM。
- **预期行为**: 应区分 "字段不存在" 与 "字段值为 JSON null"。字段值为 null 时，截断策略应能明确处理（如返回空结果或应用 `null` 语义）。
- **影响**: null 值结果未被截断，可能将完整结果暴露给 LLM（虽然 null 本身无信息泄露，但其余字段可能很大）。
- **建议改法和验证点**: 在 `_select_truncation_value` 中先检查 key 是否存在（`spec.target_field in value`），再检查值是否为 `None`/`null`。
- **修复风险（低）**: 仅改变 null 值处理分支。
- **严重程度（低）**: 触发条件罕见（target_field 值为 JSON null），且实际信息泄露风险低。

### PR55-DS-5-未修复-低-TEXT_LINES 截断标准化换行符为 LF

- **入口/函数**: `_truncate_text_lines`
- **文件(行号)**: `dayu/host/tool_runtime.py:3702-3706`
- **输入场景**: 工具结果包含 CRLF (`\r\n`) 或 CR (`\r`) 换行符。
- **实际行为**: `str.splitlines()` 在所有换行符类型上拆分，`"\n".join(lines[:limit])` 用 LF 重新组合。原始换行符约定丢失。
- **影响**: 对 LLM 语义通常透明，但如果工具结果中的换行符约定有特定含义（如 CSV 导出、带格式文本），截断后内容与原始内容在字节层面不一致。
- **建议改法和验证点**: 保留原始换行符约定，或至少记录此行为。
- **修复风险（低）**: 可仅通过文档说明。
- **严重程度（低）**: 对当前财报分析场景影响极小。

### PR55-DS-6-未修复-低-CAS_CONFLICT 等枚举值已定义但从未被产出

- **入口/函数**: `ToolAcceptRejectReason` 枚举
- **文件(行号)**: `dayu/host/tool_runtime.py:193-195` (CAS_CONFLICT), `194` (SCHEMA_MISMATCH), `195` (EXPLICIT_POLICY_REJECT)
- **输入场景**: 任何可能触发 CAS 冲突、schema 不匹配或显式 policy reject 的 accept 场景。
- **实际行为**: 三个枚举值已定义但无代码路径返回它们。accept barrier 中的 `_invalid_accept_context_reason`（`tool_runtime.py:2744`）返回 `INVALID_ATTEMPT` 或 `STALE_EXECUTION`，不使用 `CAS_CONFLICT`。schema 校验在 `ToolRuntimeHandle.__post_init__` 中通过 `ValueError` 处理，不使用 `SCHEMA_MISMATCH`。
- **影响**: 无运行时影响——枚举定义是预留的。但如果未来需要在 accept 层表达这些语义，需回头补充实现路径。
- **建议改法和验证点**: 确认这些枚举是 Phase 7+ 的预留项，在对应 phase 中实现。或在当前 phase 中移除未使用的值。
- **修复风险（低）**: 仅影响代码清洁度。
- **严重程度（低）**: 已知 gap，已在 P6-S2 controller adjudication 中记录。

### PR55-DS-7-未修复-低-`ToolFactRejectedAck.retryable` 字段已定义但从未被消费

- **入口/函数**: `_accept_with_retry`
- **文件(行号)**: `dayu/host/tool_runtime.py:430, 2485-2486`
- **输入场景**: accept barrier 返回 `ToolFactRejectedAck(retryable=True, ...)`。
- **实际行为**: `tool_runtime.py:2485-2486` 对任何 `ToolFactRejectedAck` 直接 return，不检查 `retryable` 字段。即使标记为可重试，也不会进入下一轮重试循环。
- **影响**: 当前所有 `ToolFactRejectedAck` 的 `retryable` 均为 `False`（如 `IDEMPOTENCY_CONFLICT` 返回 `retryable=False`），因此无实际行为错误。但字段语义与实现不一致。
- **建议改法和验证点**: 若未来需要 retryable 语义，应更新 `_accept_with_retry` 以检查此字段。或在当前 phase 中移除未使用的 `retryable` 字段。
- **修复风险（低）**.
- **严重程度（低）**.

### 以下目标均已满足（未发现实质性问题）

#### P6-AGG-F1 修复：Run-scoped 共享 duplicate memory

经逐路径验证（详见 aggregate re-review），修复已正确实施：
- `InMemoryRunScopedDuplicateGovernanceRegistry` (`tool_runtime.py:1648-1707`) 按 `run_id` 持有 `_RunLocalDuplicateGovernanceState`，同一 Run 的多个 ToolRuntime handle 通过同一 registry 共享 accepted fact 索引。
- 不同 `run_id` 映射到不同的 `_RunLocalDuplicateGovernanceState`，跨 Run 隔离正确。
- `dispatch.py` 中三处清理路径覆盖正常终态 (`dispatch.py:1004-1006`)、cancel (`dispatch.py:908`)、scheduler close (`dispatch.py:468`)。
- `RLock` 线程安全：`_RunLocalDuplicateGovernanceState` (`tool_runtime.py:1521`) 和 `InMemoryRunScopedDuplicateGovernanceRegistry` (`tool_runtime.py:1662`) 各自持有独立 RLock。
- 无 durable ledger、无 crash recovery 承诺——完全符合 Phase 6 exit standard。

#### ToolRuntime truncation / fetch_more

- `TruncationManager` 只持有内存 `_cursors` dict (`tool_runtime.py:1263`)，不写 durable table。
- `_validate_cursor` (`tool_runtime.py:1421-1465`) 校验 `session_id`、`run_id`、`attempt_id` 三字段与 manager scope 完全匹配，scope mismatch 返回 `scope_mismatch`。
- `scope_token` 通过 `sha256_digest_json` hash 后与 cursor 绑定 (`tool_runtime.py:1405`)，明文 token 仅通过 `secrets.token_urlsafe(32)` 生成并返回给 truncated result。
- Cursor 为 `single_use=True` (`tool_runtime.py:1415`)，使用后通过 `replace(cursor, used_at=now)` 标记 (`tool_runtime.py:1375`)。
- TTL 使用严格不等式 `>` (`tool_runtime.py:1451`)。
- `fetch_more` 作为 framework tool 注册为 `@tool`，其 `truncate=None` (`tool_runtime.py:3487`) 阻止递归截断。
- 所有截断策略 (text_chars, text_lines, list_items, binary_bytes) 均有完整测试覆盖。

#### Side-effect / paid-tool policy 未被静默绕过

- `ToolRuntimeToolPolicy.__post_init__` (`tool_runtime.py:557-564`) 在构造时拒绝 `SIDE_EFFECT`/`PAID` 工具缺 `idempotency_key_argument_name`。
- `DefaultToolRuntimePolicyPort.decide_tool_call` (`tool_runtime.py:1179-1206`) 在运行时检查：
  1. `allow_tool_calls=False` → `GOVERNED_ERROR`
  2. `SIDE_EFFECT`/`PAID` 工具缺 tool_idempotency_key → `GOVERNED_ERROR`
  3. 通过 → `ALLOW`
- `_tool_idempotency_key` (`tool_runtime.py:3997-4013`) 从工具参数提取 key，非字符串值返回 `None`。
- 测试确认 (`test_side_effect_tool_missing_idempotency_key_never_calls_callable`): callable 不可被调用。

#### Phase 7 WAITING / resolve_wait 未泄露到 Phase 6

- `_normalize_runtime_outcome` (`tool_runtime.py:2427-2452`) 明确拦截 `ToolAwaitingOutcome` 转为 `governed_error`。
- `_tool_fact_accept_candidate` (`tool_runtime.py:4287-4289`) 入口处 `raise TypeError` 防止 awaiting 直接进入 accept。
- Host 代码中无 `WAITING` Run status 推进、无 `resolve_wait` 实现、无 wait record 创建。

#### Tool schema 与 callable 同源

- `ToolRuntimeHandle.__post_init__` (`tool_runtime.py:2575`) 校验 `tool_schemas == effective_bundle.tool_schemas`。
- `StaticToolRuntimeHandleProvider` (`run_input.py`) 使用同一 handle 分别构造 schema provider 和 executor provider。
- `_validate_tool_enabled_snapshot` (`run_input.py`) 额外做 identity 检查。
- no-tool 模式下使用 `NoopToolSchemaSnapshotProvider` + `NoopToolExecutorProvider`，正确隔离。

#### 架构边界

- `tool_runtime.py` 不 import `dispatch.py`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins`。
- 依赖方向 `dispatch.py → tool_runtime.py` 正确（非反向）。
- 无 `Any` / `object` / 无类型签名新增；所有公共 dataclass 使用 `frozen=True, slots=True`。
- 无兼容性 re-export、wrapper、facade。
- README 更新与代码实现一致。

#### 测试覆盖

- 349 项 Host 测试全部通过。
- `test_scheduler_uses_toolruntime_when_tooling_is_configured` 走完整的 scheduler → ToolRuntime → accept barrier 真实路径（通过 SQLite durable store）。
- `test_same_run_runtime_handles_share_duplicate_index` 验证同 Run 多 ToolRuntime handle 共享 duplicate 记忆。
- `test_different_runs_do_not_share_duplicate_index` 验证跨 Run 隔离。
- pyright clean: 0 errors, 0 warnings, 0 informations。

---

## Open Questions

1. **`ToolRuntimeExecutor._execute_one` 的复杂度（101 行，编排 6 个 port）**：当前正确，但后续 phase (Phase 7 WAITING, Phase 9 steer) 引入新分支后是否应拆分？建议在 Phase 7 实施时自然评估，不阻塞 Phase 6 exit。

2. **`enable_truncation_manager` 默认值不一致**：`EffectiveToolBundleBuildRequest` 默认为 `False`（`tool_runtime.py:1981`），而 `HostLocalExecutionOptions` 默认为 `True`（`api.py:403`）。实际生效值来自 `HostLocalExecutionOptions`（经由 `dispatch.py:718-719`），但直接构造 `EffectiveToolBundleBuildRequest` 的调用方若依赖默认值会得到意外行为。是否应统一默认值？

3. **accept barrier idempotency 与重执行语义**：`accept_idempotency_key` 包含 `outcome_digest`，其中包含 `meta.started_at` 和 `meta.finished_at` 时间戳（`tool_runtime.py:4490-4491`）。若调用方在 `_accept_with_retry` 之外重试完整 `execute()` 流程，工具被重新执行并产生不同时间戳时，新的 `accept_idempotency_key` 不会命中已有记录，第二次 accept 会写入新事件。这是否是设计意图（"重执行应产生新事实"），还是应在某层记录"同一 tool_call_id 的首次 accept 已提交"？当前行为在 `_accept_with_retry` 内部正确（同一 candidate 永不改变 key），跨 `execute` 重试的语义需要在 Phase 7 中与 WAITING/resume 路径一并明确。

---

## Residual Risks

1. **fetch_more cursor 无淘汰策略**：TruncationManager 的 `_cursors` dict 中已过期或已使用的 cursor 从不被移除。在 Run 生命周期内 cursor 数量与截断工具调用次数成正比。对于长 Run 中大量截断结果的场景，内存使用可能逐步增长。当前由 Run 终态后 GC 自然回收——但如果 Run 异常超长（如持续数小时的大量工具调用），可能累积。建议在 Phase 7 或后续 hardening 中增加基于 TTL 的惰性清理或 LRU 上限。

2. **`_consume_worker_events` 中 `run_terminal_closed` 门控**：如 PR55-DS-3 所述，在某些竞态路径下 `clear_run` 可能被跳过。`scheduler.close()` 中的 `clear_all()` 提供兜底，但 scheduler 生命周期内可能累积少量 stale state。

3. **`_accept_with_retry` 无取消令牌检查**：当前 accept retry 循环不检查取消令牌（`tool_runtime.py:2454-2503`），如果执行上下文已被取消，retry 仍会燃尽所有重试次数后才返回。Phase 7 引入 `WAITING`/resume 时可能需要此能力。

4. **`ToolAcceptRejectReason` 预留枚举值**：`CAS_CONFLICT`、`EXPLICIT_POLICY_REJECT`、`SCHEMA_MISMATCH` 已定义但从未被产出。Phase 7+ 实现对应治理路径时需要确保这些枚举值被正确连接。

5. **跨 Attempt 工具执行 timestamps 与 idempotency**：见 Open Question 3。如果 Phase 7 `resolve_wait → resume` 导致同一 `tool_call_id` 被重新执行，不同 timestamps 会产生不同的 `accept_idempotency_key`，导致新的 EventLog 写入（而非 idempotent replay）。Phase 7 设计需显式处理此语义。

6. **未覆盖测试区域**：
   - 并发 `fetch_more` 调用（当前串行模型下不可触发）
   - SQLite 事务重试耗尽时 accept barrier 的 graceful 降级
   - TEXT_LINES 的非 LF 换行符场景
   - `target_field` 为 JSON null 的截断场景
   - `ToolCancelledOutcome` 经 `_normalize_runtime_outcome` 的路径（当前在候选构造阶段间接覆盖）

---

## Final Verdict

**PASS**

PR 55 的 Phase 6 ToolRuntime 实现质量高，架构边界清晰，所有已发现的核心问题已在 aggregate review 阶段修复（P6-AGG-F1）。本次 PR 级深审发现 2 项中等发现（死代码/异常传播缺失、TOCTOU 竞态窗口）和 5 项低严重度发现，均不构成 Phase 6 exit 阻塞。349 项测试全部通过，pyright clean，README 与代码一致。

中等发现 PR55-DS-1（`except TimeoutError` 死代码导致 `HostTransactionRetryExhaustedError` 未处理传播）建议在 Phase 6 的后续 commit 中修复，其余可推迟到 Phase 7 或相应 hardening phase。
