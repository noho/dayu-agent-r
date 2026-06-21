# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: `main` (accepted plan commit `478f5f77` through gate checkpoint `28bba810`)
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-mimo.md`
- Included scope: Host two-phase activation hook (`wait_adapter.py`, `tool_runtime.py`, `tooling.py`, `dispatch.py`), Fins prepare/activate runtime (`ingestion_runtime.py`, `observation_handle.py`, `ingestion/wait_adapter.py`), Fins tool callables (`download_tools.py`, `preprocess_tools.py`, `upload_tools.py`), Service wiring (`host_assembly.py`), design/README sync, and all corresponding tests.
- Excluded scope: Engine public contract, LLM-facing tool schema, durable Fins job schema, Host durable schema.
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下为低风险观察项，按 severity 排序：

### 01-未修复-低-standalone `build_fins_wait_activation_registry` 创建独立 runtime 实例

- **入口/函数**: `dayu/fins/ingestion/wait_adapter.py` `build_fins_wait_activation_registry(...)`
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:226-255`
- **输入场景**: 调用方使用 standalone builder 而非 production `host_assembly.py` 路径构造 activation registry
- **实际分支**: `FinsIngestionWaitActivationAdapter.from_workspace_root(workspace_root)` 内部调用 `DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()`，创建独立于 tool callable 所用 runtime 的新实例
- **预期行为**: activation adapter 与 tool callable 共享同一 `FinsIngestionRuntime` 实例（同一 `_observations` 字典）
- **实际行为**: standalone builder 创建独立 runtime 实例，其 `_observations` 字典与 tool callable 使用的不同，导致 `activate_observation(handle)` 找不到 tool callable prepare 的 observation
- **直接证据**: `build_fins_wait_activation_registry` L247 调用 `from_workspace_root`，该方法 L182 创建新 runtime；production path `host_assembly.py:1789-1798` 直接传入共享 `fins_awaiting_runtime`
- **影响**: standalone builder 构造的 registry 在实际使用时 activation 会静默失败（`_observations.get(handle.handle_id)` 返回 `None`，直接 `return`），observation 保持 PENDING 直到 poller 判定 lost。production path 不受影响
- **建议改法和验证点**: standalone builder 的 docstring 已注明 "只适用于由调用方自行保证 runtime 一致性的独立装配场景"，但方法本身未接受外部 runtime 参数。若需要 standalone builder 真正可用，应接受 `FinsObservationRuntime` 参数而非自行创建。当前 production path 正确共享 runtime，无需立即修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-activation adapter 构造 handle 时 created_at 使用当前时间

- **入口/函数**: `FinsIngestionWaitActivationAdapter.activate_accepted_wait(...)`
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:187-202`
- **输入场景**: Host accepted wait 后触发 activation
- **实际分支**: `datetime.now(timezone.utc)` 作为新 handle 的 `created_at`
- **预期行为**: handle 的 `created_at` 应与 tool callable prepare 时创建的原始 handle 一致
- **实际行为**: 新 handle 使用当前时间，而非原始 prepare 时间
- **直接证据**: L200 `created_at=datetime.now(timezone.utc)`；原始 handle 在 tool callable prepare 时创建
- **影响**: 无功能影响。`activate_observation` 内部只使用 `handle.handle_id` 做 `_observations` 字典查找，不使用 `created_at`。`created_at` 仅用于 poller 的 `_result_meta` 时间戳投影
- **建议改法和验证点**: 无需修改。若未来 activation 路径需要精确原始时间，可从 `accepted_ack` 或 resume token 解析
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- Process-local observation 仍无法在 Host 进程丢失后存活；owner 仍为 #90 / #92。
- Production poller scheduling、backoff、fencing、retry 不在本 WU 范围；owner 仍为 #90。
- External provider physical cancel / revoke / abandon 不在本 WU 范围；owner 仍为 #92。
- Callback endpoint / auth / replay 不在本 WU 范围；owner 仍为 #89。

## 验证结果

| 命令 | 结果 |
|---|---|
| `pytest tests/service/test_host_assembly.py -q` | 52 passed, 3 warnings |
| `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` | 159 passed, 3 warnings |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 无输出 |

## Review 逐项裁决

### 1. Host activation hook 是否只在 awaiting accept ack 后触发

**通过。** `_accept_awaiting()` (L2764) 在 `isinstance(accept_result, ToolAwaitingAcceptedAck)` 成立后才调用 `_activate_accepted_wait_best_effort()`。rejected ack (L2791-2801)、timeout (L2935-2980)、missing adapter binding (L2722-2734)、missing external job ref (L2736-2747)、duplicate fanout waiter (L2346-2351) 均不触发 activation。cancellation token recheck 在 activation 前执行 (L2776)。

### 2. Fins prepare / activate 是否幂等，不 double-submit

**通过。** `activate_observation()` (L2370-2414) 在 `_observation_lock` 保护下检查 `record.submitted`、`cancellation_state.is_cancelled()` 和 `_TERMINAL_OBSERVATION_STATUSES`，通过后原子设置 `record.submitted = True` 再提交 executor。重复 activation 看到 `submitted=True` 直接返回。activation 失败时在 lock 内标记 observation 为 `FAILED` (L2406-2413)。

### 3. Service assembly 是否装配到同一 workspace-scoped runtime

**通过。** `host_assembly.py:1714-1725` 中 `_fins_wait_activation_registry_from_provider_configs` 接收 `fins_awaiting_runtime` 参数，直接构造 `FinsIngestionWaitActivationAdapter(runtime=fins_awaiting_runtime)` (L1789-1798)。tool callable 和 poll adapter 也使用同一 runtime。standalone builder 创建独立 runtime 但有 docstring 警告。

### 4. Engine 边界是否未被扩大

**通过。** 无 Engine public contract 变更。`ToolAwaitingOutcome` shape 不变。`ToolExecutor.execute()` handshake 不变。activation 不暴露到 LLM-facing tool schema。`docs/engine/design.md` 无变更。

### 5. 设计/README 同步是否准确

**通过。** `docs/host/design.md` 新增两行说明 activation adapter 是 Host construction-time wiring。`dayu/host/README.md` 新增 ToolRuntime activation 和 Engine non-ownership 说明。`dayu/fins/README.md` 更新了 prepare/activate API、状态流、wait adapter 说明。无过程性 gate 文本泄漏到稳定文档。

### 6. 跨 slice 集成缺口、死代码、兼容 wrapper、过度设计或测试缺口

**通过。** 三个 slice 形成完整闭环：Slice 1 Host activation hook → Slice 2 Fins prepare/activate → Slice 3 Service wiring。`start_observed_*` 方法保留为向后兼容的 direct stream 路径（内部调用 prepare + activate）。无新增兼容 wrapper。无过度设计：只新增一个 Host-layer activation adapter，未引入 lifecycle supervisor、durable activation ledger 或新 public await contract。测试覆盖了 accepted ack activation、rejected/timeout/cancelled non-activation、idempotent activation、cancel-before-activate、activation failure terminal mapping。
