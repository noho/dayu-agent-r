# Code Review: Host Phase 6 P6-S4 — TruncationManager And fetch_more Normal Tool Path

## Scope

- Mode: current changes (workspace diff)
- Branch: feat/host-phase-6-toolruntime
- Base: main (per plan contract)
- Output file: docs/reviews/host-phase6-code-review-s4-ds-20260515.md
- Included scope: 当前未提交 diff 中 P6-S4 相关变更
  - `dayu/host/tool_runtime.py`（P6-S4 新增部分）
  - `tests/host/test_toolruntime_truncation_fetch_more.py`（新增测试）
  - `tests/host/test_toolruntime_effective_bundle.py`（补充注入测试）
  - `tests/host/test_phase6_toolruntime_integration.py`（补充集成测试）
  - `dayu/host/README.md`（同步当前事实）
  - `tests/README.md`（同步测试事实）
- Excluded scope:
  - P6-S1～P6-S3 已接受代码（不重复审查）
  - P6-S5 未实现代码
  - `docs/reviews/` 目录下的历史 review artifacts
  - 远端 remote/wire protocol 模块
  - Engine/Service/UI/Fins 层代码
- Parallel review coverage: 无（单 reviewer 全程走读）
- Review targets per user specification:
  - TruncationManager 是否 run-scoped/short-lived/ToolRuntime-local
  - 是否没有 durable cursor table/descriptor
  - cursor/scope_token 是否校验 run scope, token digest, TTL, single-use, missing cursor, remainder digest mismatch
  - fetch_more 是否作为普通 injected ToolDefinition.callable 通过 ToolExecutor/dispatcher/accept barrier/EventLog
  - schema 与 callable 是否同源 effective bundle
  - 业务 fetch_more conflict 是否仍拒绝
  - 是否越界改 Engine/Remote/duplicate governance
  - 类型纪律
  - 测试质量
  - README 是否只写当前事实

## Findings

### 未发现实质性问题

经过对 P6-S4 截断与 `fetch_more` 普通工具路径的完整走读（TruncatedRemainderRef 严格联合类型 → ToolTruncationCursor 校验 → TruncationManager 内存 cursor 存储 → 截断应用路径 → `_validate_cursor` 六项校验 → FetchMoreToolCallable 普通 dispatcher 集成 → EffectiveToolBundleBuilder 注入逻辑 → `_fetch_more_tool_definition` schema/callable 同源构造 → ToolRuntimeFactory 统一装配 → EventLog canonical path），未发现 blocking 或 non-blocking material findings。

以下按用户指定审查目标逐项确认：

#### 1. TruncationManager run-scoped / short-lived / ToolRuntime-local

**确认通过。** `TruncationManager`（`tool_runtime.py:1046`）将 cursor 存储于实例级 `self._cursors: dict[str, ToolTruncationCursor]`（`tool_runtime.py:1077`），不写任何 durable 表。cursor 生命周期与 `TruncationManager` 实例绑定，该实例在 `ToolRuntimeFactory.create_tool_runtime`（`tool_runtime.py:2006-2011`）中创建，与 `ToolRuntimeHandle` 共存亡。每次创建新 ToolRuntime 都会重新初始化空 cursor 字典。

#### 2. 没有 durable cursor table/descriptor

**确认通过。** 搜索全文件未见新的 durable 表定义、DDL、CREATE TABLE 或 cursor descriptor 持久化逻辑。cursor 完全是内存对象，不写 EventLog（cursor 不进入 EventLog payload，仅 `ToolTruncationFact` 以 metadata 形式写入 accept candidate 的 `truncation` 字段）。

#### 3. cursor/scope_token 校验

**确认通过。** `_validate_cursor`（`tool_runtime.py:1235-1280`）覆盖六项校验：

| 校验项 | 行号 | 失败返回 |
|--------|------|----------|
| run scope（session_id / run_id / attempt_id / context） | 1249-1258 | `scope_mismatch` |
| scope token digest | 1260-1263 | `scope_token_mismatch` |
| TTL expiry | 1265-1268 | `cursor_expired` |
| single-use（used_at is not None） | 1270-1273 | `cursor_already_used` |
| missing cursor（cursor not in dict） | 1172-1177 | `missing_cursor` |
| remainder digest mismatch | 1275-1278 | `remainder_digest_mismatch` |

所有失败路径均返回普通 `ToolFailedOutcome`（通过 `_truncation_failure`），不触发 recovery / wait。

`scope_token` 的生成与验证：
- 生成：`secrets.token_urlsafe(32)`（`tool_runtime.py:1215`），产生加密随机 token
- 存储：仅存 `sha256` digest（`tool_runtime.py:1219 → 3224-3231`），明文 token 返回给 LLM
- 验证：重算 `_scope_token_digest(request.scope_token)` 并与 cursor 中存储的 digest 对比（`tool_runtime.py:1260`）

#### 4. fetch_more 作为普通 injected ToolDefinition.callable 通过 ToolExecutor/dispatcher/accept barrier/EventLog

**确认通过。** 完整执行路径：

1. 注入：`EffectiveToolBundleBuilder._inject_framework_definitions`（`tool_runtime.py:1650-1654`）在 `FETCH_MORE` policy 启用且 `enable_truncation_manager=True` 时创建 `FetchMoreToolCallable` 并通过 `_fetch_more_tool_definition` 构造普通 `ToolDefinition`
2. Schema/callable 同源注入到 `EffectiveToolBundle`（`tool_runtime.py:1603-1628`）
3. RunInputBuilder 通过同一 `ToolRuntimeHandle` 暴露 schema 与 executor（`tool_runtime.py:2037-2041`）
4. Engine 调用 `tool_executor.execute()` → `ToolRuntimeExecutor.execute()` → 对每个 call 执行 `policy_port.decide_tool_call()` → `duplicate_governance.decide_duplicate()` → `dispatcher.dispatch()`（查找 `definitions_by_name["fetch_more"]`） → `callable(call, context)` → `FetchMoreToolCallable.__call__` → `TruncationManager.fetch_more`
5. `fetch_more` 结果经过与普通业务工具完全相同的 accept barrier（`tool_runtime.py` 中 `ToolRuntimeExecutor._accept_single_call_outcome`）
6. 接受后写入 EventLog canonical facts（`TOOL_CALL_REQUESTED` → `TOOL_CALL_GOVERNED` → `TOOL_RESULT_ACCEPTED`）

**没有 Host/Engine 特化分支。** `DefaultToolDispatcher`（`tool_runtime.py` 中）通过 `definitions_by_name` 统一查找 callable，不对 `fetch_more` 做特殊处理。集成测试 `test_fetch_more_uses_same_toolruntime_accept_eventlog_path` 通过 EventLog payload 断言 `fetch_more` 产生了与普通业务工具相同的 canonical event 序列。

#### 5. schema 与 callable 同源 effective bundle

**确认通过。** `_fetch_more_tool_definition`（`tool_runtime.py:2868-2903`）返回的 `ToolDefinition` 包含 `schema`（`ToolSchema`）和 `callable`（`FetchMoreToolCallable` 实例），两者通过同一个 `ToolDefinition` 对象绑定。`EffectiveToolBundleBuilder.build()` 将注入的定义与业务定义合并为统一的 `definitions_by_name`（`tool_runtime.py:1604`），然后从同一 `definitions` 列表投影 `tool_schemas`（`tool_runtime.py:1605-1607`）。`ToolRuntimeFactory.create_tool_runtime` 将同一个 `EffectiveToolBundle` 传给 `DefaultToolDispatcher`（用于 callable lookup）和 `ToolRuntimeHandle.tool_schemas`（用于 Engine schema）。

测试 `test_enabled_fetch_more_injects_schema_and_callable_when_truncation_enabled` 通过 identity 断言（`fetch_more.callable is handle.effective_bundle.fetch_more_callable`）证明 schema 与 callable 同源。

#### 6. 业务 fetch_more conflict 仍拒绝

**确认通过。** 双层防御：

1. `HostToolingOptions.__post_init__`（`tooling.py:149-154`）：业务 `ToolBundle` 中任何定义名与 `reserved_framework_tool_names`（默认包含 `FETCH_MORE`，`tooling.py:115`）冲突时抛出 `ValueError`
2. `EffectiveToolBundleBuilder.build()` 调用 `_validate_reserved_name_conflicts`（`tool_runtime.py:1593-1596 → 2828-2837`），再次校验业务工具没有占用预留名

P6-S4 未修改此校验逻辑。测试 `test_business_fetch_more_is_rejected`（`test_toolruntime_effective_bundle.py`，P6-S1 已有）持续保护此 invariant。

#### 7. 是否越界改 Engine/Remote/duplicate governance

**确认通过。** P6-S4 变更：

- 仅修改 `dayu/host/tool_runtime.py` 一个生产文件
- import 边界：不导入 `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` / `dayu.remote`
- 未修改 `dayu/contracts/` 下 Engine 公共契约
- 未修改 Remote proxy/stub/wire protocol
- duplicate governance 仍使用 P6-S3 的 `PassThroughDuplicateGovernance`（`tool_runtime.py:2028`），P6-S4 未新增或修改 duplicate 逻辑
- `dayu/host/run_input.py` 未在本次 diff 中修改（plan 规定仅 P6-S1/S3/S4 可改）

#### 8. 类型纪律

**确认通过。**
- `TruncatedRemainderRef` 为封闭强类型联合（`TextCharsRemainderRef | TextLinesRemainderRef | ListItemsRemainderRef | BinaryBytesRemainderRef`），无 `Any` / `object`
- `ToolTruncationCursor` 使用 strict `@dataclass(frozen=True, slots=True)`，所有字段有明确类型
- `FetchMoreRequest` / `FetchMoreResult` 有明确类型
- 所有新增函数有完整中文 docstring 含 params/returns/raises
- 模块级常量使用下划线前导命名（`_FETCH_MORE_*`），不泄漏到公共接口
- pyright 验证：`0 errors, 0 warnings, 0 informations`

#### 9. 测试质量

**确认通过。** `tests/host/test_toolruntime_truncation_fetch_more.py`（534 行）覆盖：

| 测试 | 覆盖路径 |
|------|----------|
| `test_truncated_result_exposes_only_cursor_and_scope_token` | 正常截断的 cursor/scope_token 暴露、truncation fact 写入 accept candidate |
| `test_fetch_more_dispatches_as_normal_tool_and_is_single_use` | fetch_more 经 executor/accept 路径、single-use 拒绝第二次使用、accept candidate 序列含 fetch_more |
| `test_fetch_more_missing_cursor_returns_ordinary_tool_error` | 不存在 cursor → `missing_cursor` |
| `test_fetch_more_rejects_token_mismatch` | scope token 不匹配 → `scope_token_mismatch` |
| `test_fetch_more_rejects_ttl_expiry` | TTL 过期 → `cursor_expired` |
| `test_fetch_more_rejects_scope_mismatch` | cursor.run_id 不匹配 → `scope_mismatch` |
| `test_fetch_more_rejects_remainder_digest_mismatch` | 剩余内容被篡改 → `remainder_digest_mismatch` |

补充 effective bundle 测试：
- `test_enabled_fetch_more_injects_schema_and_callable_when_truncation_enabled`：schema 与 callable 同源注入 + identity 验证
- `test_enabled_fetch_more_policy_without_truncation_does_not_inject`：未启用 truncation 时不注入 fetch_more

补充集成测试：
- `test_fetch_more_uses_same_toolruntime_accept_eventlog_path`：fetch_more 经 durable accept port 写 EventLog，EventLog event_type 序列含 `TOOL_CALL_REQUESTED` / `TOOL_CALL_GOVERNED` / `TOOL_RESULT_ACCEPTED` 各两次（业务工具 + fetch_more 各一次）

测试覆盖：happy path（截断、补读）、所有六种 cursor 错误路径、注入/不注入边界、EventLog canonical path。未覆盖场景（cross-run cursor leak、concurrent batch）在当前 P6-S4 架构下不可达（每个 ToolRuntime 持有独立 cursor 字典；执行是顺序的）。

#### 10. README 只写当前事实

**确认通过。** `dayu/host/README.md` 新增内容：
- "P6-S1 到 P6-S4" 版本范围更新
- 明确 `TruncationManager` 是 ToolRuntime-local 内存能力，不写 durable cursor 表
- 明确 `fetch_more` 走普通工具路径
- 明确 cursor 校验覆盖的六种失败
- 未实现项更新为 `完整重复工具事实治理算法、policy provider resolution、attempt tool snapshot durability、真实 HostDispatchScheduler tool-enabled composition wiring 与长耗时 external job / wait record`
- 没有声称 P7/P11/P13/P14 能力已实现

`tests/README.md` 新增：
- 收窄运行命令 `pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py -q`
- 测试覆盖清单同步增加 `run-scoped truncation cursor / scope token、fetch_more 普通工具注入、single-use / TTL / scope / token / missing cursor / remainder digest 错误路径`

## Open Questions

- 无。

## Residual Risk

- **TextLines 截断丢失末尾换行信息**：`str.splitlines()` 不保留行尾换行符。如果原始文本以 `\n` 结尾，通过 `fetch_more` 补读拼回的内容会与原始内容不一致。digest 计算使用相同的中间表示（tuple of lines），因此不触发 digest mismatch，但内容无法精确还原。此行为对所有基于 `splitlines()` 的实现是普遍特征；当前截断声明的 field_path/target_field 语义不承诺精确还原原始字节流。风险等级：低。P6-S4 plan 已将此列为 `更复杂业务 payload projection` 的 non-goal。
- **single-use cursor 的 check-update 原子性**：`_validate_cursor` 检查 `used_at` 和 `fetch_more` 中设置 `used_at` 之间无 `await` 点（两个方法均为同步方法）。在当前 ToolRuntimeExecutor 顺序执行模型下安全。若未来 slices 引入批内并发执行，需要将 check-update 对改为原子操作或加锁。当前架构下不可达。
- **cursor TTL 依赖系统时钟**：`datetime.now(UTC) > cursor.expires_at` 使用系统时钟比较。若系统时钟被大幅回拨，已过期 cursor 可能重新可用。这是 TTL 机制的通用局限，非本实现特有问题。

## Verification Results

```text
source .venv/bin/activate && pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py -q
→ 14 passed in 0.17s

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ (clean, no whitespace errors)
```

## Verdict

**P6-S4 implementation is fit for acceptance.** 所有审查目标（TruncationManager locality、cursor validation、fetch_more normal tool path、schema/callable 同源、business conflict 拒绝、边界纪律、类型纪律、测试质量、README 事实性）均验证通过。未发现 blocking 或 material non-blocking findings。
